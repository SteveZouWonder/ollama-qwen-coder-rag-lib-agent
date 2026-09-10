"""
bm25_store.py — BM25 稀疏索引的持久化增量存储（F10 P2-1-a）

此前 ``RAGEngine._ensure_bm25`` 在每次入库 / 删除后置空缓存，下一次查询把 Chroma
里的全部片段拉回内存重新分词、重建 ``BM25Okapi``：千级文档库每次入库后首查卡顿数秒。

本模块把"分词结果 + 来源元数据"按 Chroma 的 chunk id 持久化到
``<index_dir>/bm25/store.json.gz``，入库 / 删除只做增量 ``upsert`` / ``remove``，
``BM25Okapi`` 只在首次查询或有变更（``dirty``）时惰性重建——重建不再读 Chroma、
不再分词，只是把已有 token 列表喂给 ``BM25Okapi``。

文件格式（gzip JSON）::

    {
      "schema_version": 1,
      "tokenizer_version": 1,
      "docs": {"<chunk_id>": {"tf": {"<token>": 次数, ...}, "len": 词数, "metadata": {...}}, ...}
    }

内存布局：每个片段只保留 **词频字典**（token → 次数，token 经 ``sys.intern`` 跨片段共享）与词数，
不保留 token 列表；文档频次 ``df`` 随 upsert / remove 增量维护。``build()`` 直接用这些字典
装配 ``BM25Okapi``（``doc_freqs`` 与 store 共享同一批字典对象，不复制），因此常驻内存≈
``rank_bm25`` 自身的索引大小，比"保留 token 列表再建索引"小一个数量级。

约定：
- ``TOKENIZER_VERSION``：**改动 ``tokenize`` 的任何逻辑都必须递增**，否则旧库的 token
  与新查询分词不一致；版本不匹配时 ``load()`` 返回 False，调用方全量重建并 ``save()``。
- 文件损坏 / 结构不对 → ``load()`` 记 warning、返回 False、``load_error`` 记录原因，
  调用方全量重建（不会因为一个坏文件让混合检索失效）。
- 本模块不依赖 Chroma / LlamaIndex；``rank_bm25`` 只在 ``build()`` 时导入。
"""
from __future__ import annotations

import gzip
import json
import logging
import os
import re
import sys
import tempfile
import threading
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

logger = logging.getLogger(__name__)

# 文件结构版本（字段增删时递增）
SCHEMA_VERSION = 1
# 分词逻辑版本：改 ``tokenize`` 必须递增（见模块说明）
TOKENIZER_VERSION = 1

STORE_FILENAME = "store.json.gz"

_WORD_RE = re.compile(r"[a-zA-Z0-9_]+")
_SUBWORD_RE = re.compile(r"[A-Z]+[0-9]*(?![a-z])|[A-Z]?[a-z]+[0-9]*|[0-9]+")


def tokenize(text: str) -> List[str]:
    """BM25 轻量分词：英文 / 数字按词（小写），中文按单字 + 相邻二字组。

    标识符额外拆分：``snake_case`` / ``camelCase`` / ``PascalCase`` 在保留原词的同时
    追加其子词（``_ensure_bm25`` → ``ensure``、``bm25``；``getUserName`` → ``get``、
    ``user``、``name``），使代码问答中"问 ensure bm25 命中 _ensure_bm25"成为可能。

    **改动此函数必须递增 ``TOKENIZER_VERSION``。**
    """
    if not text:
        return []
    words = _WORD_RE.findall(text)
    tokens: List[str] = []
    for w in words:
        tokens.append(w.lower())
        parts = [p for p in w.split("_") if p]
        sub: List[str] = []
        for p in parts:
            sub.extend(_SUBWORD_RE.findall(p))
        if len(sub) > 1 or (sub and sub[0] != w):
            tokens.extend(s.lower() for s in sub if s.lower() != w.lower())
    cjk = [ch for ch in text if "\u4e00" <= ch <= "\u9fff"]
    tokens.extend(cjk)
    tokens.extend(a + b for a, b in zip(cjk, cjk[1:]))
    return tokens


class BM25Store:
    """按 chunk id 组织的 BM25 语料存储：增量维护、gzip JSON 持久化、惰性构建索引。

    线程安全：所有公开方法持 ``RLock``（入库线程 upsert 与查询线程 build 可能并发）。
    """

    # gzip 压缩级别（见 save）
    COMPRESS_LEVEL = 1

    def __init__(
        self,
        persist_dir: os.PathLike | str,
        tokenizer: Callable[[str], List[str]] = tokenize,
        tokenizer_version: int = TOKENIZER_VERSION,
    ):
        self.persist_dir = Path(persist_dir)
        self.path = self.persist_dir / STORE_FILENAME
        self.tokenizer = tokenizer
        self.tokenizer_version = int(tokenizer_version)
        # doc_id -> {"tf": {token: count}, "len": int, "metadata": {...}}
        self.docs: Dict[str, Dict[str, Any]] = {}
        # token -> 含该 token 的片段数（随 upsert / remove 增量维护，build 时直接算 idf）
        self._df: Dict[str, int] = {}
        # 内存内容与磁盘不一致（需要 save）
        self.dirty = False
        # 由调用方标记：内存内容可能与向量库不一致（如走了无法拿到 chunk id 的回退路径），
        # 下次 ensure 时应全量重建
        self.stale = False
        # load() 是否已尝试过，以及最近一次失败原因
        self.load_attempted = False
        self.loaded = False
        self.load_error: Optional[str] = None
        self._lock = threading.RLock()
        # 惰性构建的索引及与其对齐的 id / metadata 列表
        self._index = None
        self._ids: List[str] = []
        self._metas: List[Dict[str, Any]] = []

    # ------------------------------------------------------------------ 基本信息

    def __len__(self) -> int:
        with self._lock:
            return len(self.docs)

    def __contains__(self, doc_id: object) -> bool:
        with self._lock:
            return str(doc_id) in self.docs

    def exists(self) -> bool:
        """磁盘上是否已有 store 文件。"""
        return self.path.is_file()

    def is_usable(self) -> bool:
        """内存内容可直接用于构建索引（已成功 load 或本进程内已写入，且未被标记 stale）。"""
        with self._lock:
            return bool(self.docs) and not self.stale

    # ------------------------------------------------------------------ 持久化

    def load(self) -> bool:
        """从磁盘读取。返回 True 表示读到了版本匹配、结构合法的 store。

        - 文件不存在 → False（``load_error`` 为 None）；
        - 版本不匹配 → False（``load_error`` 说明版本，调用方应全量重建）；
        - 损坏 / 结构非法 → False + warning（``load_error`` 记录异常）。
        任何 False 都会清空内存 docs。
        """
        with self._lock:
            self.load_attempted = True
            self.loaded = False
            self.load_error = None
            self.docs = {}
            self._invalidate_index()
            if not self.path.is_file():
                return False
            try:
                with gzip.open(self.path, "rt", encoding="utf-8") as fh:
                    data = json.load(fh)
                if not isinstance(data, dict):
                    raise ValueError("顶层不是对象")
                schema = int(data.get("schema_version", -1))
                tok_ver = int(data.get("tokenizer_version", -1))
                if schema != SCHEMA_VERSION or tok_ver != self.tokenizer_version:
                    self.load_error = (
                        f"版本不匹配（schema {schema}/{SCHEMA_VERSION}，tokenizer {tok_ver}/{self.tokenizer_version}）"
                    )
                    logger.info("BM25 store %s：%s，将全量重建", self.path, self.load_error)
                    return False
                docs = data.get("docs")
                if not isinstance(docs, dict):
                    raise ValueError("docs 不是对象")
                cleaned: Dict[str, Dict[str, Any]] = {}
                df: Dict[str, int] = {}
                for doc_id, entry in docs.items():
                    if not isinstance(entry, dict):
                        raise ValueError(f"docs[{doc_id!r}] 不是对象")
                    tf = entry.get("tf")
                    meta = entry.get("metadata")
                    if not isinstance(tf, dict) or not isinstance(meta, dict):
                        raise ValueError(f"docs[{doc_id!r}] 缺少 tf / metadata")
                    freqs = {sys.intern(str(t)): int(c) for t, c in tf.items()}
                    length = int(entry.get("len", sum(freqs.values())))
                    cleaned[str(doc_id)] = {"tf": freqs, "len": length, "metadata": dict(meta)}
                    for t in freqs:
                        df[t] = df.get(t, 0) + 1
                self.docs = cleaned
                self._df = df
                self.loaded = True
                self.dirty = False
                self.stale = False
                return True
            except Exception as exc:  # noqa: BLE001 - 任何损坏都回退全量重建
                self.load_error = f"{type(exc).__name__}: {exc}"
                logger.warning("BM25 store %s 损坏或无法读取（%s），将全量重建", self.path, self.load_error)
                self.docs = {}
                self._df = {}
                return False

    def save(self) -> None:
        """原子写入 gzip JSON（先写临时文件再替换）。"""
        with self._lock:
            self.persist_dir.mkdir(parents=True, exist_ok=True)
            payload = {
                "schema_version": SCHEMA_VERSION,
                "tokenizer_version": self.tokenizer_version,
                "docs": self.docs,
            }
            fd, tmp_name = tempfile.mkstemp(prefix=".store-", suffix=".tmp", dir=str(self.persist_dir))
            try:
                with os.fdopen(fd, "wb") as raw:
                    # 每次入库都会落盘：压缩级别 1 比默认 9 快约 15 倍（1 万块 0.19s vs 2.8s），体积只大 ~50%
                    with gzip.GzipFile(fileobj=raw, mode="wb", compresslevel=self.COMPRESS_LEVEL) as gz:
                        gz.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
                os.replace(tmp_name, self.path)
            except Exception:
                try:
                    os.unlink(tmp_name)
                except OSError:
                    pass
                raise
            self.dirty = False
            self.stale = False
            self.loaded = True

    def save_if_dirty(self) -> bool:
        """有变更才写盘；返回是否写了。"""
        with self._lock:
            if not self.dirty:
                return False
            self.save()
            return True

    def delete_file(self) -> None:
        """删除磁盘文件（清空知识库时用）。"""
        with self._lock:
            try:
                if self.path.is_file():
                    self.path.unlink()
            except OSError as exc:
                logger.debug("删除 BM25 store 失败: %s", exc)

    # ------------------------------------------------------------------ 增量维护

    @staticmethod
    def _term_freqs(tokens: Iterable[str]) -> Dict[str, int]:
        freqs: Dict[str, int] = {}
        for t in tokens:
            t = sys.intern(str(t))
            freqs[t] = freqs.get(t, 0) + 1
        return freqs

    def _df_add(self, freqs: Dict[str, int]) -> None:
        df = self._df
        for t in freqs:
            df[t] = df.get(t, 0) + 1

    def _df_sub(self, freqs: Dict[str, int]) -> None:
        df = self._df
        for t in freqs:
            n = df.get(t, 0) - 1
            if n <= 0:
                df.pop(t, None)
            else:
                df[t] = n

    def upsert(self, doc_id: str, text: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        """新增或覆盖一个片段（分词在此完成，只保留词频与词数）。"""
        with self._lock:
            doc_id = str(doc_id)
            tokens = list(self.tokenizer(str(text or "")))
            old = self.docs.get(doc_id)
            if old is not None:
                self._df_sub(old["tf"])
            freqs = self._term_freqs(tokens)
            self.docs[doc_id] = {"tf": freqs, "len": len(tokens), "metadata": dict(metadata or {})}
            self._df_add(freqs)
            self.dirty = True
            self._invalidate_index()

    def upsert_many(self, items: Iterable[Tuple[str, str, Optional[Dict[str, Any]]]]) -> int:
        """批量 upsert；返回条数。"""
        n = 0
        with self._lock:
            for doc_id, text, meta in items:
                self.upsert(doc_id, text, meta)
                n += 1
        return n

    def remove(self, doc_id: str) -> bool:
        """删除一个片段；返回是否存在。"""
        with self._lock:
            entry = self.docs.pop(str(doc_id), None)
            if entry is None:
                return False
            self._df_sub(entry["tf"])
            self.dirty = True
            self._invalidate_index()
            return True

    def remove_many(self, doc_ids: Iterable[str]) -> int:
        with self._lock:
            return sum(1 for d in list(doc_ids) if self.remove(d))

    def remove_where(self, predicate: Callable[[str, Dict[str, Any]], bool]) -> int:
        """删除所有 ``predicate(doc_id, metadata)`` 为真的片段；返回删除数。"""
        with self._lock:
            victims = [d for d, e in self.docs.items() if predicate(d, e.get("metadata") or {})]
            for d in victims:
                self._df_sub(self.docs.pop(d)["tf"])
            if victims:
                self.dirty = True
                self._invalidate_index()
            return len(victims)

    def replace_all(self, items: Iterable[Tuple[str, str, Optional[Dict[str, Any]]]]) -> int:
        """全量替换（迁移旧库 / 损坏回退 / 内容不一致时）；返回条数。"""
        with self._lock:
            self.docs = {}
            self._df = {}
            n = self.upsert_many(items)
            self.dirty = True
            self.stale = False
            self._invalidate_index()
            return n

    def clear(self) -> None:
        with self._lock:
            self.docs = {}
            self._df = {}
            self.dirty = True
            self.stale = False
            self._invalidate_index()

    def mark_stale(self) -> None:
        """调用方无法精确增量（如走了拿不到 chunk id 的回退路径）时标记，下次 ensure 全量重建。"""
        with self._lock:
            self.stale = True
            self._invalidate_index()

    # ------------------------------------------------------------------ 索引

    def _invalidate_index(self) -> None:
        self._index = None
        self._ids = []
        self._metas = []

    @property
    def index_built(self) -> bool:
        with self._lock:
            return self._index is not None

    # BM25Okapi 默认超参（与 ``BM25Okapi(corpus)`` 一致）
    K1, B, EPSILON = 1.5, 0.75, 0.25

    def build(self):
        """惰性构建并返回 ``BM25Okapi``（无片段时返回 None）。

        只在首次或内容变化后真正构建；``rank_bm25`` 未安装抛 ``ImportError`` 交调用方处理。
        用 store 已有的词频字典直接装配索引（不重新分词、不复制词频），与
        ``BM25Okapi(token_lists)`` 得到的分数逐位一致；装配失败（rank_bm25 内部结构变化）
        时回退到标准构造。
        """
        with self._lock:
            if self._index is not None:
                return self._index
            if not self.docs:
                return None
            from rank_bm25 import BM25Okapi  # type: ignore

            ids: List[str] = []
            metas: List[Dict[str, Any]] = []
            doc_freqs: List[Dict[str, int]] = []
            doc_len: List[int] = []
            for doc_id, entry in self.docs.items():
                ids.append(doc_id)
                metas.append(entry.get("metadata") or {})
                doc_freqs.append(entry["tf"])
                doc_len.append(int(entry.get("len") or 0))
            try:
                index = self._assemble_okapi(BM25Okapi, doc_freqs, doc_len)
            except Exception as exc:  # noqa: BLE001 - 兜底：按 token 列表标准构造
                logger.debug("BM25Okapi 直接装配失败（%s），回退标准构造", exc)
                corpus = [[t for t, c in tf.items() for _ in range(c)] for tf in doc_freqs]
                index = BM25Okapi(corpus)
            self._index = index
            self._ids = ids
            self._metas = metas
            return self._index

    def _assemble_okapi(self, cls, doc_freqs: List[Dict[str, int]], doc_len: List[int]):
        """不经 ``__init__`` 装配 ``BM25Okapi``：``doc_freqs`` 直接引用 store 的词频字典。"""
        bm = cls.__new__(cls)
        bm.k1, bm.b, bm.epsilon = self.K1, self.B, self.EPSILON
        bm.tokenizer = None
        bm.corpus_size = len(doc_freqs)
        bm.avgdl = (sum(doc_len) / len(doc_len)) if doc_len else 0.0
        bm.doc_freqs = doc_freqs
        bm.doc_len = doc_len
        bm.idf = {}
        bm._calc_idf(dict(self._df))
        # 自检：必须具备打分所需的全部属性
        for attr in ("get_scores", "idf", "average_idf", "doc_freqs", "doc_len", "avgdl", "corpus_size"):
            if not hasattr(bm, attr):
                raise AttributeError(attr)
        return bm

    def search(self, query: str, top_k: int) -> List[Tuple[str, Dict[str, Any], float]]:
        """检索前 ``top_k`` 条（分数 >0），返回 ``[(doc_id, metadata, score)]``。"""
        with self._lock:
            index = self.build()
            if index is None:
                return []
            tokens = self.tokenizer(str(query or ""))
            if not tokens:
                return []
            scores = index.get_scores(tokens)
            ranked = sorted(range(len(scores)), key=lambda i: float(scores[i]), reverse=True)
            out: List[Tuple[str, Dict[str, Any], float]] = []
            for i in ranked[: max(0, int(top_k))]:
                score = float(scores[i])
                if score <= 0:
                    break
                out.append((self._ids[i], self._metas[i], score))
            return out

    # ------------------------------------------------------------------ 诊断

    def describe(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "path": str(self.path),
                "exists": self.exists(),
                "docs": len(self.docs),
                "dirty": self.dirty,
                "stale": self.stale,
                "loaded": self.loaded,
                "load_error": self.load_error,
                "tokenizer_version": self.tokenizer_version,
                "index_built": self._index is not None,
                "vocab": len(self._df),
            }
