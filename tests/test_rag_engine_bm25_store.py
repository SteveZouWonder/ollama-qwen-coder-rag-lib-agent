"""RAGEngine × BM25Store 集成（F10 P2-1-a/b）：增量 upsert / remove 与全量重建一致、
save → load 无需重建、版本变化触发重建、损坏回退、旧库首查生成 store、超限可观测。

用 ``tmp_path`` 作 ``persist_dir``，Chroma 集合用内存假实现（记录 ``get`` 调用次数）。
"""
import gzip
import json
import logging
import sys
from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("rank_bm25")

from llama_index.core.schema import TextNode  # noqa: E402

import bm25_store  # noqa: E402


def _rag_module():
    """运行时取当前的 rag_engine 模块：test_rag_engine.py 会删除并重载该模块，
    模块级 ``from rag_engine import RAGEngine`` 会拿到过期的类对象（patch 打不到）。"""
    import importlib
    return importlib.import_module("rag_engine")


class FakeCollection:
    """最小 Chroma 集合：ids / documents / metadatas 三列，支持 count / get / delete。"""

    def __init__(self):
        self.ids, self.docs, self.metas = [], [], []
        self.get_calls = 0

    # -- 写 --
    def add_nodes(self, nodes):
        for n in nodes:
            self.ids.append(n.node_id)
            self.docs.append(n.get_content())
            self.metas.append(dict(n.metadata))

    def delete(self, where=None, ids=None):
        keep = []
        for i, (doc_id, meta) in enumerate(zip(self.ids, self.metas)):
            hit = (ids is not None and doc_id in ids) or (
                where is not None and all(meta.get(k) == v for k, v in where.items()))
            if not hit:
                keep.append(i)
        self.ids = [self.ids[i] for i in keep]
        self.docs = [self.docs[i] for i in keep]
        self.metas = [self.metas[i] for i in keep]

    # -- 读 --
    def count(self):
        return len(self.ids)

    def get(self, where=None, include=None, **_):
        self.get_calls += 1
        idx = range(len(self.ids))
        if where:
            idx = [i for i in idx if all(self.metas[i].get(k) == v for k, v in where.items())]
        out = {"ids": [self.ids[i] for i in idx], "metadatas": [self.metas[i] for i in idx]}
        if include and "documents" in include:
            out["documents"] = [self.docs[i] for i in idx]
        return out


def _nodes(spec):
    """spec: [(id, text, file_name)] → TextNode 列表（metadata 与真实入库一致的关键字段）。"""
    return [
        TextNode(id_=i, text=t, metadata={"file_name": f, "file_path": f"/kb/{f}"})
        for i, t, f in spec
    ]


BASE = [
    ("n1", "Cloudflare Tunnel 内网穿透配置指南", "cf.md"),
    ("n2", "DJI Osmo 360 售价 2999 元，支持 8K 全景", "dji.md"),
    ("n3", "def _ensure_bm25(self):\n    return True", "rag.py"),
    ("n4", "Python 递归示例：斐波那契", "py.md"),
]
EXTRA = [
    ("n5", "HTTP/3 对 Java 后端开发的影响", "http3.md"),
    ("n6", "DJI Mic 3 售价 1899 元", "mic.md"),
]


@pytest.fixture
def make_engine(tmp_path):
    """构造以 tmp_path 为 persist_dir 的引擎（Ollama / Embedding / Chroma 客户端全部打桩）。"""
    created = []

    def _make(collection: FakeCollection, sub="idx"):
        rag = _rag_module()
        with patch.object(rag, "Ollama"), patch.object(rag, "OllamaEmbedding"), \
                patch.object(rag.chromadb, "PersistentClient") as mock_chroma:
            mock_chroma.return_value.get_or_create_collection.return_value = collection
            engine = rag.RAGEngine(persist_dir=str(tmp_path / sub), enable_auto_snapshot=False, enable_security=False)
        engine.hybrid_enabled = True
        engine.metadata_manager = None
        engine._derive_knowledge_graph = lambda docs: False
        engine._persist_index = lambda: None
        engine.retriever = MagicMock()
        engine.retriever.retrieve.return_value = []
        created.append(engine)
        return engine

    return _make


def _ingest(engine, collection, spec):
    """模拟 add_documents：切分器返回给定节点，index.insert_nodes 写入假集合。"""
    nodes = _nodes(spec)
    engine.index = MagicMock()
    engine.index.insert_nodes.side_effect = collection.add_nodes
    engine._split_documents = lambda docs, cb=None: (nodes, {})
    engine.add_documents([MagicMock()], file_paths=None)
    return nodes


def _hits(engine, q, k=10):
    assert engine._ensure_bm25() is True
    return [(h["file"], round(h["bm25_score"], 6)) for h in engine._bm25_search(q, k)]


def _full_rebuild_hits(collection, make_engine, q, sub="fresh"):
    """另一目录的新引擎：无 store → 全量重建，作为"标准答案"。"""
    fresh = make_engine(collection, sub=sub)
    return _hits(fresh, q)


class TestIncrementalEqualsFullRebuild:
    def test_add_then_search_matches_full_rebuild_without_reading_chroma(self, make_engine, tmp_path):
        coll = FakeCollection()
        engine = make_engine(coll)
        _ingest(engine, coll, BASE)
        assert coll.get_calls == 0  # 入库路径拿到节点 → 纯增量，不读 Chroma
        assert (tmp_path / "idx" / "bm25" / "store.json.gz").is_file()  # 入库后即落盘

        inc = _hits(engine, "DJI 售价")
        assert coll.get_calls == 0  # 查询也不读 Chroma
        assert inc and inc[0][0] == "dji.md"
        assert inc == _full_rebuild_hits(coll, make_engine, "DJI 售价")  # 对照引擎全量读一次
        assert coll.get_calls == 1

        # 第二批追加：原引擎仍增量（get 次数只由对照引擎贡献）
        _ingest(engine, coll, EXTRA)
        assert coll.get_calls == 1
        for i, q in enumerate(("DJI 售价", "ensure bm25", "HTTP/3 Java")):
            assert _hits(engine, q) == _full_rebuild_hits(coll, make_engine, q, sub=f"fresh-{i}")
        assert coll.get_calls == 4
        assert {f for f, _ in _hits(engine, "DJI 售价")[:2]} == {"dji.md", "mic.md"}

    def test_remove_file_matches_full_rebuild(self, make_engine):
        coll = FakeCollection()
        engine = make_engine(coll)
        _ingest(engine, coll, BASE + EXTRA)
        engine.index = None  # 直接经 collection.delete 删除
        engine.remove_file("/kb/dji.md")
        assert "/kb/dji.md" not in [m["file_path"] for m in coll.metas]
        assert engine._bm25 is None  # 就位缓存失效
        get_before = coll.get_calls
        inc = _hits(engine, "DJI 售价")
        assert coll.get_calls == get_before  # 删除后重建只用 store，不全量拉取
        assert [f for f, _ in inc] == ["mic.md"]
        assert inc == _full_rebuild_hits(coll, make_engine, "DJI 售价")
        assert len(engine.bm25_store) == coll.count() == 5

    def test_fallback_ingest_path_marks_stale_and_rebuilds_once(self, make_engine):
        coll = FakeCollection()
        engine = make_engine(coll)
        _ingest(engine, coll, BASE)
        # 切分失败 → 回退 index.insert(doc)：拿不到节点 → stale → 下次查询全量重建一次
        coll.add_nodes(_nodes(EXTRA))
        engine.index = MagicMock()
        engine._split_documents = lambda docs, cb=None: (None, {})
        engine.add_documents([MagicMock()])
        assert engine.bm25_store.stale is True
        assert coll.get_calls == 0
        hits = _hits(engine, "HTTP/3 Java")
        assert coll.get_calls == 1 and hits[0][0] == "http3.md"
        assert engine.bm25_store.stale is False and len(engine.bm25_store) == 6
        _hits(engine, "HTTP/3 Java")
        assert coll.get_calls == 1  # 重建后恢复增量

    def test_count_mismatch_triggers_full_rebuild(self, make_engine):
        coll = FakeCollection()
        engine = make_engine(coll)
        _ingest(engine, coll, BASE)
        # 绕过引擎往向量库塞了一条（如外部工具写入）→ 片段数不一致 → 全量重建兜底
        coll.add_nodes(_nodes(EXTRA[:1]))
        hits = _hits(engine, "HTTP/3 Java")
        assert coll.get_calls == 1 and hits[0][0] == "http3.md"


class TestPersistenceAcrossInstances:
    def test_new_instance_loads_store_and_needs_no_rebuild(self, make_engine, tmp_path):
        coll = FakeCollection()
        engine = make_engine(coll)
        _ingest(engine, coll, BASE)
        expected = _hits(engine, "ensure bm25")

        again = make_engine(coll, sub="idx")  # 同一 persist_dir → 读到 store
        assert again._bm25_store is None  # 惰性
        assert _hits(again, "ensure bm25") == expected
        assert coll.get_calls == 0  # 全程未全量拉取
        assert again.bm25_store.loaded is True

    def test_tokenizer_version_change_rebuilds_and_rewrites(self, make_engine, tmp_path, monkeypatch):
        coll = FakeCollection()
        engine = make_engine(coll)
        _ingest(engine, coll, BASE)
        path = tmp_path / "idx" / "bm25" / "store.json.gz"
        with gzip.open(path, "rt", encoding="utf-8") as fh:
            data = json.load(fh)
        data["tokenizer_version"] = data["tokenizer_version"] + 1  # 模拟旧进程用新分词写的库 / 或本版本升级
        with gzip.open(path, "wt", encoding="utf-8") as fh:
            json.dump(data, fh)

        again = make_engine(coll, sub="idx")
        hits = _hits(again, "DJI 售价")
        assert coll.get_calls == 1 and hits[0][0] == "dji.md"  # 版本不匹配 → 全量重建一次
        with gzip.open(path, "rt", encoding="utf-8") as fh:
            assert json.load(fh)["tokenizer_version"] == bm25_store.TOKENIZER_VERSION  # 已按当前版本重写

    def test_corrupt_store_falls_back_with_warning(self, make_engine, tmp_path, caplog):
        coll = FakeCollection()
        engine = make_engine(coll)
        _ingest(engine, coll, BASE)
        path = tmp_path / "idx" / "bm25" / "store.json.gz"
        path.write_bytes(b"\x00garbage")

        again = make_engine(coll, sub="idx")
        with caplog.at_level(logging.WARNING, logger="bm25_store"):
            hits = _hits(again, "DJI 售价")
        assert hits[0][0] == "dji.md" and coll.get_calls == 1
        assert any("损坏" in r.getMessage() for r in caplog.records)
        assert bm25_store.BM25Store(path.parent).load() is True  # 坏文件已被重建结果覆盖

    def test_legacy_library_without_store_generates_it_on_first_query(self, make_engine, tmp_path):
        coll = FakeCollection()
        coll.add_nodes(_nodes(BASE))  # 旧库：向量库有内容、没有 bm25/ 目录
        engine = make_engine(coll)
        assert not (tmp_path / "idx" / "bm25").exists()
        hits = _hits(engine, "Cloudflare Tunnel")
        assert hits[0][0] == "cf.md" and coll.get_calls == 1
        store_path = tmp_path / "idx" / "bm25" / "store.json.gz"
        assert store_path.is_file()
        with gzip.open(store_path, "rt", encoding="utf-8") as fh:
            data = json.load(fh)
        assert set(data["docs"]) == {"n1", "n2", "n3", "n4"}  # 用 Chroma 的 id
        assert data["docs"]["n1"]["metadata"]["path"] == "/kb/cf.md"
        # 之后入库走增量
        _ingest(engine, coll, EXTRA)
        _hits(engine, "HTTP/3")
        assert coll.get_calls == 1

    def test_clear_index_removes_store_file(self, make_engine, tmp_path):
        coll = FakeCollection()
        engine = make_engine(coll)
        _ingest(engine, coll, BASE)
        path = tmp_path / "idx" / "bm25" / "store.json.gz"
        assert path.is_file()
        engine.chroma_client = MagicMock()
        engine.clear_index()
        assert not path.exists() and len(engine.bm25_store) == 0 and engine._bm25 is None

    def test_store_write_failure_does_not_break_ingest(self, make_engine, monkeypatch, caplog):
        coll = FakeCollection()
        engine = make_engine(coll)

        def boom(self):
            raise OSError("disk full")

        monkeypatch.setattr(bm25_store.BM25Store, "save", boom)
        with caplog.at_level(logging.WARNING, logger="rag_engine"):
            _ingest(engine, coll, BASE)
        assert any("BM25 store 写入失败" in r.getMessage() for r in caplog.records)
        # 内存中的 store 仍可用于本进程查询
        assert _hits(engine, "DJI 售价")[0][0] == "dji.md"


class TestHybridObservability:
    def test_query_meta_reports_disabled_reason_when_over_limit(self, make_engine, monkeypatch):
        rag_module = _rag_module()
        coll = FakeCollection()
        coll.add_nodes(_nodes(BASE))
        engine = make_engine(coll)
        monkeypatch.setattr(rag_module, "RAG_HYBRID_MAX_CHUNKS", 3)
        events = []
        res = engine.query_with_sources("DJI", progress_callback=events.append)
        assert res["hybrid"] is False and res["meta"]["hybrid_requested"] is True
        reason = res["meta"]["hybrid_disabled_reason"]
        assert "4" in reason and "3" in reason and "RAG_HYBRID_MAX_CHUNKS" in reason
        off = [e for e in events if e.get("phase") == "hybrid_off"]
        assert off and off[0]["reason"] == reason
        assert coll.get_calls == 0

        stats = engine.get_stats()
        assert stats["hybrid_disabled_reason"] == reason
        assert stats["hybrid"].startswith("已关闭：") and stats["hybrid_max_chunks"] == 3
        status = engine.hybrid_status()
        assert status["enabled"] and status["chunks"] == 4 and status["max_chunks"] == 3 and not status["ready"]

    def test_query_meta_none_when_hybrid_applied_or_not_requested(self, make_engine):
        coll = FakeCollection()
        engine = make_engine(coll)
        _ingest(engine, coll, BASE)
        res = engine.query_with_sources("DJI 售价")
        assert res["hybrid"] is True and res["meta"] == {"hybrid_requested": True, "hybrid_disabled_reason": None}
        stats = engine.get_stats()
        assert stats["hybrid"].startswith("开（") and stats["hybrid_disabled_reason"] is None

        res = engine.query_with_sources("DJI 售价", hybrid=False)
        assert res["meta"] == {"hybrid_requested": False, "hybrid_disabled_reason": None}

        engine.hybrid_enabled = False
        assert engine.get_stats()["hybrid"].startswith("关（RAG_HYBRID=false")
        assert engine.hybrid_status()["disabled_reason"] is None

    def test_stats_ignore_empty_library_reason_but_surface_missing_dependency(self, make_engine, monkeypatch):
        coll = FakeCollection()
        engine = make_engine(coll)
        engine.query_with_sources("x")  # 空库 → "向量库为空"，不算故障
        assert engine._bm25_disabled_reason == "向量库为空"
        assert engine.get_stats()["hybrid_disabled_reason"] is None

        engine.invalidate_bm25()
        monkeypatch.setitem(sys.modules, "rank_bm25", None)
        res = engine.query_with_sources("x")
        assert res["meta"]["hybrid_disabled_reason"] == "rank_bm25 未安装"
        assert engine.get_stats()["hybrid_disabled_reason"] == "rank_bm25 未安装"

    def test_default_limit_is_50000_and_in_config_dataclass(self):
        import config
        assert config.RAG_HYBRID_MAX_CHUNKS == 50000 or config.RAG_HYBRID_MAX_CHUNKS == int(
            __import__("os").environ.get("RAG_HYBRID_MAX_CHUNKS", "50000"))
        assert config.Config.RAG_HYBRID_MAX_CHUNKS == config.RAG_HYBRID_MAX_CHUNKS
        assert config.Config.RAG_HYBRID == config.RAG_HYBRID


class TestSurfaces:
    """CLI /stats 与 Web 知识库页对 hybrid 字段的呈现（P2-1-b）。"""

    def test_web_format_stats_and_cards_show_hint(self):
        from web.app import format_stats, format_stats_cards
        reason = "文档块数 60000 超过上限 50000，混合检索已关闭（仅向量检索）；可调大 RAG_HYBRID_MAX_CHUNKS"
        stats = {"total_documents": 60000, "hybrid": "已关闭：" + reason, "hybrid_disabled_reason": reason}
        md = format_stats(stats)
        assert "- 混合检索: 已关闭：" in md and "> ⚠️ " + reason in md
        html = format_stats_cards(stats)
        assert html.count('class="cb-card"') == 4  # 卡片数不变，提示在卡片下方
        assert "cb-empty" in html and "RAG_HYBRID_MAX_CHUNKS" in html
        # 可用时无提示
        ok = {"total_documents": 5, "hybrid": "开（向量 + BM25 关键词，上限 50000 块）", "hybrid_disabled_reason": None}
        assert "cb-empty" not in format_stats_cards(ok) and "- 混合检索: 开（" in format_stats(ok)
        # 非超限原因补前缀
        dep = {"hybrid_disabled_reason": "rank_bm25 未安装"}
        assert "混合检索已关闭：rank_bm25 未安装" in format_stats_cards(dep)

    def test_cli_print_knowledge_stats_hides_none_and_prints_hint(self, monkeypatch, capsys):
        import query_interface as qi
        engine = MagicMock()
        engine.get_stats.return_value = {
            "total_documents": 60000,
            "hybrid": "已关闭：文档块数 60000 超过上限 50000",
            "hybrid_disabled_reason": "文档块数 60000 超过上限 50000，可调大 RAG_HYBRID_MAX_CHUNKS",
        }
        monkeypatch.setattr(qi, "rag_engine", engine)
        monkeypatch.setattr(qi, "HAS_RICH", False)
        qi.print_knowledge_stats()
        out = capsys.readouterr().out
        assert "total_documents: 60000" in out and "hybrid: 已关闭" in out
        assert "hybrid_disabled_reason:" not in out  # 不重复出现在表格
        assert "⚠️ 文档块数 60000 超过上限 50000" in out

        engine.get_stats.return_value = {"total_documents": 5, "hybrid": "开", "hybrid_disabled_reason": None}
        qi.print_knowledge_stats()
        out = capsys.readouterr().out
        assert "None" not in out and "⚠️" not in out
