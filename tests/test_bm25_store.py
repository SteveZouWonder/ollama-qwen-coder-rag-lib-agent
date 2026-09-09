"""bm25_store.BM25Store 单元测试（F10 P2-1-a）：持久化 / 增量 / 惰性构建 / 版本 / 损坏回退。"""
import gzip
import json
import logging

import pytest

import bm25_store
from bm25_store import BM25Store, SCHEMA_VERSION, STORE_FILENAME, TOKENIZER_VERSION, tokenize

pytest.importorskip("rank_bm25")

DOCS = [
    ("a", "Cloudflare Tunnel 配置指南", {"file": "cf.md", "path": "/d/cf.md"}),
    ("b", "DJI Osmo 360 售价 2999 元", {"file": "dji.md", "path": "/d/dji.md"}),
    ("c", "def _ensure_bm25(self): pass", {"file": "rag.py", "path": "/d/rag.py", "start_line": 3}),
]


def _filled(tmp_path) -> BM25Store:
    store = BM25Store(tmp_path / "bm25")
    for doc_id, text, meta in DOCS:
        store.upsert(doc_id, text, meta)
    return store


class TestTokenize:
    def test_mixed_and_identifiers(self):
        toks = tokenize("DJI Osmo 售价 def _ensure_bm25 getUserName")
        assert {"dji", "osmo", "售", "价", "售价", "_ensure_bm25", "ensure", "bm25",
                "getusername", "get", "user", "name"} <= set(toks)
        assert tokenize("") == [] and tokenize(None) == []  # type: ignore[arg-type]
        assert tokenize("hello").count("hello") == 1

    def test_rag_engine_delegates_to_store_tokenizer(self):
        from rag_engine import RAGEngine
        text = "HTTPServer _ensure_bm25 售价"
        assert RAGEngine._bm25_tokenize(text) == tokenize(text)
        assert RAGEngine.BM25_TOKENIZER_VERSION == TOKENIZER_VERSION


class TestIncremental:
    def test_upsert_remove_dirty_and_len(self, tmp_path):
        store = BM25Store(tmp_path / "bm25")
        assert len(store) == 0 and not store.dirty and not store.is_usable()
        store.upsert("a", "hello world", {"file": "a"})
        assert len(store) == 1 and store.dirty and "a" in store and store.is_usable()
        # 覆盖同 id
        store.upsert("a", "hello again", {"file": "a2"})
        assert len(store) == 1 and store.docs["a"]["metadata"] == {"file": "a2"}
        assert store.remove("a") is True and store.remove("a") is False
        assert len(store) == 0

    def test_remove_where_and_many(self, tmp_path):
        store = _filled(tmp_path)
        assert store.remove_where(lambda _id, m: m.get("path") == "/d/cf.md") == 1
        assert store.remove_where(lambda _id, m: False) == 0
        assert store.remove_many(["b", "zzz"]) == 1
        assert list(store.docs) == ["c"]

    def test_replace_all_and_clear(self, tmp_path):
        store = _filled(tmp_path)
        store.mark_stale()
        assert store.stale and not store.is_usable()
        n = store.replace_all([("x", "只有一条", {})])
        assert n == 1 and list(store.docs) == ["x"] and not store.stale and store.dirty
        store.clear()
        assert len(store) == 0 and store.build() is None and store.search("x", 5) == []

    def test_build_is_lazy_and_invalidated_on_change(self, tmp_path):
        store = _filled(tmp_path)
        assert not store.index_built
        idx = store.build()
        assert idx is not None and store.index_built and store.build() is idx  # 复用
        store.upsert("d", "新的片段", {})
        assert not store.index_built
        assert store.build() is not idx

    def test_search_returns_ids_meta_scores(self, tmp_path):
        store = _filled(tmp_path)
        hits = store.search("DJI Osmo 售价", 5)
        assert hits and hits[0][0] == "b" and hits[0][1]["file"] == "dji.md" and hits[0][2] > 0
        assert all(score > 0 for _, _, score in hits)
        # 标识符子词命中代码片段
        assert store.search("ensure bm25", 5)[0][0] == "c"
        assert store.search("", 5) == [] and store.search("x", 0) == []

    def test_upsert_many_counts(self, tmp_path):
        store = BM25Store(tmp_path / "bm25")
        assert store.upsert_many(DOCS) == 3 and len(store) == 3

    def test_scores_identical_to_standard_bm25okapi(self, tmp_path):
        """直接装配的索引与 ``BM25Okapi(token_lists)`` 逐位一致（含增量覆盖 / 删除后）。"""
        import numpy as np
        from rank_bm25 import BM25Okapi
        store = _filled(tmp_path)
        store.upsert("d", "Cloudflare Tunnel 售价 未知 售价 售价", {})
        store.upsert("a", "覆盖后的 Cloudflare 文本", {})  # 覆盖：df 需先减旧词再加新词
        store.remove("b")
        texts = {"a": "覆盖后的 Cloudflare 文本", "c": DOCS[2][1], "d": "Cloudflare Tunnel 售价 未知 售价 售价"}
        ref = BM25Okapi([tokenize(texts[i]) for i in store.docs])
        idx = store.build()
        for q in ("Cloudflare 售价", "ensure bm25", "文本", "不存在的词"):
            np.testing.assert_allclose(idx.get_scores(tokenize(q)), ref.get_scores(tokenize(q)), rtol=0, atol=1e-12)
        assert idx.doc_freqs[0] is store.docs["a"]["tf"]  # 共享词频字典，不复制
        assert store.describe()["vocab"] == len(ref.idf)
        # 落盘再读回：df 重算后分数仍一致
        store.save()
        again = BM25Store(tmp_path / "bm25")
        assert again.load()
        np.testing.assert_allclose(again.build().get_scores(tokenize("Cloudflare 售价")),
                                   ref.get_scores(tokenize("Cloudflare 售价")), atol=1e-12)

    def test_build_falls_back_to_standard_constructor(self, tmp_path, monkeypatch):
        import numpy as np
        from rank_bm25 import BM25Okapi
        store = _filled(tmp_path)
        monkeypatch.setattr(BM25Store, "_assemble_okapi", lambda self, cls, f, l: (_ for _ in ()).throw(RuntimeError("x")))
        idx = store.build()
        ref = BM25Okapi([tokenize(t) for _, t, _ in DOCS])
        np.testing.assert_allclose(idx.get_scores(tokenize("DJI 售价")), ref.get_scores(tokenize("DJI 售价")), atol=1e-12)

    def test_interned_tokens_shared_across_docs(self, tmp_path):
        import sys as _sys
        store = BM25Store(tmp_path / "bm25")
        store.upsert("a", "cloudflare tunnel", {})
        store.upsert("b", "cloudflare 隧道", {})
        ka = next(k for k in store.docs["a"]["tf"] if k == "cloudflare")
        kb = next(k for k in store.docs["b"]["tf"] if k == "cloudflare")
        assert ka is kb is _sys.intern("cloudflare")
        assert store._df == {"cloudflare": 2, "tunnel": 1, "隧": 1, "道": 1, "隧道": 1}
        store.remove("a")
        assert store._df == {"cloudflare": 1, "隧": 1, "道": 1, "隧道": 1}


class TestPersistence:
    def test_save_then_load_without_rebuild(self, tmp_path):
        store = _filled(tmp_path)
        assert store.save_if_dirty() is True and store.exists() and not store.dirty
        assert store.save_if_dirty() is False
        other = BM25Store(tmp_path / "bm25")
        assert other.load() is True and other.loaded and len(other) == 3 and other.load_error is None
        # 加载即可查询，且与原实例结果一致（不需要重新分词）
        assert [h[0] for h in other.search("DJI Osmo 售价", 5)] == [h[0] for h in store.search("DJI Osmo 售价", 5)]
        assert other.docs == store.docs

    def test_file_format(self, tmp_path):
        store = _filled(tmp_path)
        store.save()
        with gzip.open(tmp_path / "bm25" / STORE_FILENAME, "rt", encoding="utf-8") as fh:
            data = json.load(fh)
        assert data["schema_version"] == SCHEMA_VERSION and data["tokenizer_version"] == TOKENIZER_VERSION
        assert set(data["docs"]) == {"a", "b", "c"}
        assert data["docs"]["c"]["metadata"]["start_line"] == 3
        assert data["docs"]["c"]["tf"]["ensure"] == 1 and data["docs"]["c"]["len"] == len(tokenize(DOCS[2][1]))
        # 无临时文件残留
        assert [p.name for p in (tmp_path / "bm25").iterdir()] == [STORE_FILENAME]

    def test_missing_file(self, tmp_path):
        store = BM25Store(tmp_path / "nope")
        assert store.load() is False and store.load_attempted and store.load_error is None and not store.loaded

    def test_tokenizer_version_mismatch_forces_rebuild(self, tmp_path):
        store = _filled(tmp_path)
        store.save()
        other = BM25Store(tmp_path / "bm25", tokenizer_version=TOKENIZER_VERSION + 1)
        assert other.load() is False and "版本不匹配" in (other.load_error or "") and len(other) == 0
        # 同一实例换回匹配版本可读
        assert BM25Store(tmp_path / "bm25").load() is True

    def test_schema_version_mismatch(self, tmp_path):
        d = tmp_path / "bm25"
        d.mkdir()
        with gzip.open(d / STORE_FILENAME, "wt", encoding="utf-8") as fh:
            json.dump({"schema_version": SCHEMA_VERSION + 1, "tokenizer_version": TOKENIZER_VERSION, "docs": {}}, fh)
        store = BM25Store(d)
        assert store.load() is False and "schema" in (store.load_error or "")

    @pytest.mark.parametrize("payload", [
        b"not gzip at all",
        gzip.compress(b"{not json"),
        gzip.compress(json.dumps([1, 2, 3]).encode()),
        gzip.compress(json.dumps({"schema_version": SCHEMA_VERSION, "tokenizer_version": TOKENIZER_VERSION, "docs": []}).encode()),
        gzip.compress(json.dumps({"schema_version": SCHEMA_VERSION, "tokenizer_version": TOKENIZER_VERSION,
                                  "docs": {"a": "bad"}}).encode()),
        gzip.compress(json.dumps({"schema_version": SCHEMA_VERSION, "tokenizer_version": TOKENIZER_VERSION,
                                  "docs": {"a": {"tf": "x", "metadata": {}}}}).encode()),
    ])
    def test_corrupt_file_warns_and_returns_false(self, tmp_path, payload, caplog):
        d = tmp_path / "bm25"
        d.mkdir()
        (d / STORE_FILENAME).write_bytes(payload)
        store = BM25Store(d)
        with caplog.at_level(logging.WARNING, logger="bm25_store"):
            assert store.load() is False
        assert store.load_error and not store.loaded and len(store) == 0
        assert any("损坏" in r.getMessage() for r in caplog.records)
        # 损坏后仍可增量写入并覆盖坏文件
        store.upsert("a", "重建", {})
        store.save()
        assert BM25Store(d).load() is True

    def test_save_failure_cleans_tmp_and_raises(self, tmp_path, monkeypatch):
        store = _filled(tmp_path)

        def boom(*a, **k):
            raise OSError("disk full")

        monkeypatch.setattr(bm25_store.os, "replace", boom)
        with pytest.raises(OSError):
            store.save()
        assert store.dirty is True
        assert not any(p.name.startswith(".store-") for p in (tmp_path / "bm25").iterdir())

    def test_delete_file_and_describe(self, tmp_path):
        store = _filled(tmp_path)
        store.save()
        info = store.describe()
        assert info["docs"] == 3 and info["exists"] is True and info["loaded"] is True and info["index_built"] is False
        store.delete_file()
        assert not store.exists()
        store.delete_file()  # 不存在时不抛

    def test_load_clears_previous_memory(self, tmp_path):
        store = _filled(tmp_path)
        assert store.load() is False  # 无文件
        assert len(store) == 0
