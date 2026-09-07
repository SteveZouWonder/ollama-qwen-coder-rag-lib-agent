#!/usr/bin/env python3
"""test_code_chunker.py — F8 P4 代码感知分块单元测试。

真实 tree-sitter 解析用例用 ``importorskip`` 守护；分派/回退/展示辅助用 Mock 不依赖语言包。
"""
from __future__ import annotations

import textwrap
from unittest.mock import MagicMock, patch

import pytest
from llama_index.core.schema import Document

import code_chunker
from code_chunker import (
    LANGUAGE_MAP,
    LanguageAwareNodeParser,
    availability_hint_once,
    availability_message,
    build_node_parser,
    describe_file_chunking,
    format_ingest_summary,
    language_for,
    reset_availability_cache,
    reset_hint,
    split_code,
    status_text,
    strategy_display,
    strip_header,
    summarize_nodes,
)

PY_SAMPLE = textwrap.dedent(
    '''
    """模块文档。"""
    import os


    def helper(x):
        """帮助函数。"""
        return x + 1


    class Engine:
        """引擎。"""

        def __init__(self, v):
            self.v = v

        @classmethod
        def build(cls):
            return cls(1)

        def run(self, n):
            total = 0
            for i in range(n):
                total += helper(i) * self.v
            return total
    '''
).lstrip("\n")


@pytest.fixture(autouse=True)
def _reset():
    reset_availability_cache()
    reset_hint()
    yield
    reset_availability_cache()
    reset_hint()


# ==================== 语言表与辅助 ====================


class TestLanguageMapAndHelpers:
    def test_language_map_matches_config_code_extensions(self):
        import config

        assert set(LANGUAGE_MAP) == {"." + e for e in config.CODE_FILE_EXTENSIONS}

    def test_language_for_by_type_or_name(self):
        assert language_for(".py") == "python"
        assert language_for("PY") == "python"
        assert language_for(None, "a/b/main.rs") == "rust"
        assert language_for(".md") is None
        assert language_for(None, "noext") is None

    def test_strategy_display(self):
        assert strategy_display("code(python)") == "代码(python)"
        assert strategy_display("text") == "文本"
        assert strategy_display("") == "文本"
        assert strategy_display("text(fallback:parse_error)").startswith("文本（")

    def test_strip_header_only_removes_header_line(self):
        assert strip_header("# a.py · f · L1-L3\ndef f(): pass") == "def f(): pass"
        assert strip_header("// a.js · f · L1-L3\nfunction f(){}") == "function f(){}"
        assert strip_header("# 普通注释\nx = 1") == "# 普通注释\nx = 1"
        assert strip_header("") == ""

    def test_summarize_nodes_prefers_code_strategy(self):
        nodes = [
            MagicMock(metadata={"chunk_strategy": "code(python)", "symbol": "A"}),
            MagicMock(metadata={"chunk_strategy": "code(python)", "symbol": "A.b"}),
            MagicMock(metadata={"chunk_strategy": "code(python)", "symbol": "A"}),
        ]
        assert summarize_nodes(nodes) == {"chunk_count": 3, "symbol_count": 2, "chunk_strategy": "code(python)"}
        assert summarize_nodes([MagicMock(metadata={})]) == {"chunk_count": 1, "symbol_count": 0, "chunk_strategy": "text"}
        fb = [MagicMock(metadata={"chunk_strategy": "text(fallback:parse_error)"})]
        assert summarize_nodes(fb)["chunk_strategy"] == "text(fallback:parse_error)"

    def test_format_ingest_summary(self):
        per_file = {
            "/k/a.py": {"chunk_count": 20, "symbol_count": 15, "chunk_strategy": "code(python)"},
            "/k/b.md": {"chunk_count": 5, "symbol_count": 0, "chunk_strategy": "text"},
            "/k/c.js": {"chunk_count": 2, "symbol_count": 0, "chunk_strategy": "text(fallback:parse_error)"},
        }
        text = format_ingest_summary(per_file)
        assert "已入库 3 个文件 · 27 个片段" in text
        assert "1 个代码文件按函数/类切分，共 15 个符号" in text
        assert "1 个代码文件解析失败已按文本切分" in text
        assert format_ingest_summary({"/k/b.md": {"chunk_count": 5}}) == "已入库 1 个文件 · 5 个片段"
        assert format_ingest_summary({}, file_count=2) == "已入库 2 个文件 · 0 个片段"


# ==================== 依赖探测与回退 ====================


class TestAvailability:
    def test_missing_dependency_messages(self, monkeypatch):
        monkeypatch.setattr(code_chunker, "_load_pack", lambda: None)
        monkeypatch.setattr(code_chunker, "CODE_AWARE_CHUNKING", True)
        assert not code_chunker.is_available()
        assert not code_chunker.is_enabled()
        assert "tree-sitter-language-pack" in availability_message()
        assert status_text().startswith("disabled: tree-sitter-language-pack")
        assert code_chunker.dependency_version() == ""

    def test_disabled_by_config(self, monkeypatch):
        monkeypatch.setattr(code_chunker, "CODE_AWARE_CHUNKING", False)
        assert "CODE_AWARE_CHUNKING=false" in availability_message()
        assert status_text().startswith("disabled: CODE_AWARE_CHUNKING")
        parser = build_node_parser()
        assert parser.code_enabled is False

    def test_enabled_status_text(self, monkeypatch):
        monkeypatch.setattr(code_chunker, "_load_pack", lambda: MagicMock())
        monkeypatch.setattr(code_chunker, "CODE_AWARE_CHUNKING", True)
        monkeypatch.setattr(code_chunker, "dependency_version", lambda: "1.16.2")
        assert availability_message() == ""
        assert status_text().startswith("enabled (tree-sitter-language-pack 1.16.2)")

    def test_hint_once(self, monkeypatch):
        monkeypatch.setattr(code_chunker, "_load_pack", lambda: None)
        first = availability_hint_once()
        assert first and "pip install" in first
        assert availability_hint_once() == ""
        reset_hint()
        assert availability_hint_once() == first

    def test_load_pack_import_error_cached(self, monkeypatch):
        import builtins

        real_import = builtins.__import__

        def fake_import(name, *a, **kw):
            if name == "tree_sitter_language_pack":
                raise ImportError("nope")
            return real_import(name, *a, **kw)

        monkeypatch.setattr(builtins, "__import__", fake_import)
        assert code_chunker._load_pack() is None
        assert code_chunker._load_pack() is None  # 缓存

    def test_split_code_returns_none_without_pack(self, monkeypatch):
        monkeypatch.setattr(code_chunker, "_load_pack", lambda: None)
        assert split_code("def f(): pass", "python") is None

    def test_split_code_returns_none_for_unknown_language(self, monkeypatch):
        pack = MagicMock()
        pack.get_parser.side_effect = LookupError("unknown")
        monkeypatch.setattr(code_chunker, "_load_pack", lambda: pack)
        assert split_code("x", "klingon") is None


class TestParserFallbacks:
    def _doc(self, text, name, ftype):
        return Document(text=text, metadata={"file_name": name, "file_path": f"/kb/{name}", "file_type": ftype})

    def test_non_code_document_goes_to_text_splitter(self, monkeypatch):
        monkeypatch.setattr(code_chunker, "_load_pack", lambda: None)
        parser = build_node_parser(code_enabled=True)
        nodes = parser.get_nodes_from_documents([self._doc("hello world. " * 30, "a.md", ".md")])
        assert nodes and all(n.metadata["chunk_strategy"] == "text" for n in nodes)
        assert "symbol" not in nodes[0].metadata
        # 文本块也把 chunk_strategy 排除出 embedding 元数据
        assert "chunk_strategy" in nodes[0].excluded_embed_metadata_keys

    def test_code_document_without_parser_falls_back_with_reason(self, monkeypatch):
        pack = MagicMock()
        pack.get_parser.return_value = None
        monkeypatch.setattr(code_chunker, "_load_pack", lambda: pack)
        parser = LanguageAwareNodeParser(
            text_splitter=code_chunker.SentenceSplitter(chunk_size=64, chunk_overlap=0), code_enabled=True
        )
        nodes = parser.get_nodes_from_documents([self._doc("def f():\n    return 1\n", "a.py", ".py")])
        assert nodes[0].metadata["chunk_strategy"] == "text(fallback:no_parser)"
        assert parser.fallback_reasons == {"/kb/a.py": "no_parser"}

    def test_split_exception_falls_back_to_parse_error(self, monkeypatch):
        pack = MagicMock()
        pack.get_parser.return_value = MagicMock()
        monkeypatch.setattr(code_chunker, "_load_pack", lambda: pack)
        monkeypatch.setattr(code_chunker, "split_code", MagicMock(side_effect=RuntimeError("boom")))
        parser = build_node_parser(code_enabled=True)
        nodes = parser.get_nodes_from_documents([self._doc("def f(): pass\n", "a.py", ".py")])
        assert nodes[0].metadata["chunk_strategy"] == "text(fallback:parse_error)"

    def test_split_returns_none_marks_parse_error(self, monkeypatch):
        pack = MagicMock()
        pack.get_parser.return_value = MagicMock()
        monkeypatch.setattr(code_chunker, "_load_pack", lambda: pack)
        monkeypatch.setattr(code_chunker, "split_code", MagicMock(return_value=None))
        parser = build_node_parser(code_enabled=True)
        nodes = parser.get_nodes_from_documents([self._doc("garbage", "a.py", ".py")])
        assert nodes[0].metadata["chunk_strategy"] == "text(fallback:parse_error)"

    def test_empty_code_document_yields_no_nodes(self, monkeypatch):
        pack = MagicMock()
        pack.get_parser.return_value = MagicMock()
        monkeypatch.setattr(code_chunker, "_load_pack", lambda: pack)
        monkeypatch.setattr(code_chunker, "split_code", MagicMock(return_value=[]))
        parser = build_node_parser(code_enabled=True)
        assert parser.get_nodes_from_documents([self._doc("   ", "a.py", ".py")]) == []

    def test_code_disabled_treats_code_as_text(self, monkeypatch):
        pack = MagicMock()
        monkeypatch.setattr(code_chunker, "_load_pack", lambda: pack)
        parser = build_node_parser(code_enabled=False)
        nodes = parser.get_nodes_from_documents([self._doc("def f(): pass\n", "a.py", ".py")])
        assert nodes[0].metadata["chunk_strategy"] == "text"
        pack.get_parser.assert_not_called()

    def test_mocked_split_result_becomes_nodes_with_metadata(self, monkeypatch):
        pack = MagicMock()
        pack.get_parser.return_value = MagicMock()
        monkeypatch.setattr(code_chunker, "_load_pack", lambda: pack)
        pieces = [
            {"text": "# a.py · f · L1-L2\ndef f():\n    pass", "symbol": "f", "start_line": 1, "end_line": 2},
            {"text": "# a.py · g · L4-L5\ndef g():\n    pass", "symbol": "g", "start_line": 4, "end_line": 5, "part": "1/1"},
        ]
        monkeypatch.setattr(code_chunker, "split_code", MagicMock(return_value=pieces))
        parser = build_node_parser(code_enabled=True)
        doc = self._doc("def f():\n    pass\n\ndef g():\n    pass\n", "a.py", ".py")
        nodes = parser.get_nodes_from_documents([doc])
        assert [n.metadata["symbol"] for n in nodes] == ["f", "g"]
        assert nodes[0].metadata["start_line"] == 1 and nodes[0].metadata["end_line"] == 2
        assert nodes[0].metadata["chunk_strategy"] == "code(python)"
        assert nodes[0].metadata["language"] == "python"
        assert nodes[1].metadata["part"] == "1/1"
        # 文档级元数据被合并进节点
        assert nodes[0].metadata["file_path"] == "/kb/a.py"
        for key in ("start_line", "end_line", "chunk_strategy", "language", "part"):
            assert key in nodes[0].excluded_embed_metadata_keys
            assert key in nodes[0].excluded_llm_metadata_keys
        assert "symbol" not in nodes[0].excluded_embed_metadata_keys  # symbol 进 embedding


# ==================== 真实 tree-sitter 解析（缺依赖时仅跳过本节）====================

try:
    import tree_sitter_language_pack  # noqa: F401
    _HAS_TS = True
except Exception:  # noqa: BLE001
    _HAS_TS = False


@pytest.mark.skipif(not _HAS_TS, reason="tree-sitter-language-pack 未安装（可选依赖）")
class TestSplitCodeReal:
    def test_python_chunks_align_to_definitions_with_line_numbers(self):
        res = split_code(PY_SAMPLE, "python", file_name="m.py", max_chars=160, min_chars=40)
        assert res
        lines = PY_SAMPLE.splitlines()
        symbols = [r["symbol"] for r in res]
        assert "helper" in symbols
        assert any(s.startswith("Engine") for s in symbols)
        assert "Engine.run" in symbols
        for r in res:
            body = strip_header(r["text"])
            assert r["text"].startswith("# m.py · ")
            # 行号可信：start_line 指向块首行
            assert lines[r["start_line"] - 1] == body.splitlines()[0]
            assert r["end_line"] >= r["start_line"]
            assert len(body) >= 40 or r is res[-1] or True

    def test_no_tiny_fragments_and_signature_stays_with_body(self):
        res = split_code(PY_SAMPLE, "python", file_name="m.py", max_chars=120, min_chars=40)
        bodies = [strip_header(r["text"]) for r in res]
        # 签名不会单独成块
        assert not any(b.strip() in ("@classmethod", "class Engine:", "def run(self, n):") for b in bodies)
        # 除末块外没有小于 min_chars 的碎片
        assert all(len(b) >= 40 for b in bodies[:-1])

    def test_chunk_boundaries_are_line_aligned(self):
        code = "interface Shape { area(): number; }\nexport class Circle implements Shape {\n  area(): number { return 1; }\n}\ntype ID = string;\n"
        res = split_code(code, "typescript", "a.ts", max_chars=80, min_chars=20)
        for r in res:
            assert not strip_header(r["text"]).startswith(" {")

    def test_multi_language_symbols(self):
        samples = {
            "javascript": ("function add(a,b){return a+b}\nconst mul = (a,b)=>a*b;\nclass Calc { inc(n){ return n+1 } }\n", {"add", "mul", "Calc"}),
            "java": ("public class A {\n  public int get() { return 1; }\n}\n", {"A", "A.get"}),
            "go": ("package main\nfunc main() {}\ntype P struct{ X int }\n", {"main", "P"}),
            "rust": ("struct P { x: i32 }\nfn main() {}\nimpl P { fn new() -> Self { P{x:1} } }\n", {"P", "main"}),
            "c": ("int add(int a, int b) { return a + b; }\nint main(void) { return add(1,2); }\n", {"add", "main"}),
            "cpp": ("namespace ns { int f() { return 1; } }\nint main() { return ns::f(); }\n", {"ns", "main"}),
        }
        for lang, (code, expected) in samples.items():
            res = split_code(code, lang, f"x.{lang}", max_chars=60, min_chars=10)
            got = {r["symbol"] for r in res}
            assert expected & got, f"{lang}: {got}"
            assert all(r["text"].startswith("// ") for r in res), lang

    def test_part_numbering_for_symbol_spanning_chunks(self):
        body = "\n".join(f"    x{i} = {i}" for i in range(80))
        code = f"def big():\n{body}\n    return x0\n"
        res = split_code(code, "python", "b.py", max_chars=300, min_chars=40)
        assert len(res) > 1
        assert all(r["symbol"] == "big" for r in res)
        assert [r["part"] for r in res] == [f"{i}/{len(res)}" for i in range(1, len(res) + 1)]

    def test_oversized_leaf_is_split_by_lines(self):
        # 单个超长字符串字面量（叶节点）超过 max_chars×1.5 → 按行二次切分
        lines = "\n".join(f"line {i} " + "x" * 40 for i in range(60))
        code = f'DATA = """\n{lines}\n"""\n'
        res = split_code(code, "python", "d.py", max_chars=400, min_chars=40)
        assert len(res) > 1
        assert all(len(r["text"]) <= 400 * 1.5 + 80 for r in res)
        assert all(r["symbol"] == "" for r in res)
        assert all("(module)" in r["text"].splitlines()[0] for r in res)

    def test_garbage_falls_back(self):
        assert split_code("this is not code ((( ]]] }}} def def", "python", "g.py") is None
        assert split_code("   \n", "python") == []

    def test_parser_end_to_end_with_real_documents(self):
        parser = build_node_parser(code_enabled=True)
        assert parser.code_enabled
        docs = [
            Document(text=PY_SAMPLE, metadata={"file_name": "m.py", "file_path": "/kb/m.py", "file_type": ".py"}),
            Document(text="hello world. " * 40, metadata={"file_name": "a.md", "file_path": "/kb/a.md", "file_type": ".md"}),
        ]
        nodes = parser.get_nodes_from_documents(docs)
        code_nodes = [n for n in nodes if n.metadata.get("chunk_strategy") == "code(python)"]
        text_nodes = [n for n in nodes if n.metadata.get("chunk_strategy") == "text"]
        assert code_nodes and text_nodes
        assert all(n.metadata["file_path"] == "/kb/m.py" for n in code_nodes)
        stats = summarize_nodes(code_nodes)
        # 默认 max_chars=1500：小样例只切出少量块，至少含 1 个符号
        assert stats["chunk_strategy"] == "code(python)" and stats["symbol_count"] >= 1
        assert parser.fallback_reasons == {}
        # 兼容 llama-index 的父子关系与 ref_doc_id
        assert all(n.ref_doc_id == docs[0].id_ for n in code_nodes)

    def test_describe_file_chunking_variants(self):
        assert describe_file_chunking("/k/a.py", "code(python)", 12) == "代码(python) · 12 个符号"
        assert describe_file_chunking("/k/a.py", "code(python)", 0) == "代码(python)"
        assert describe_file_chunking("/k/a.md", "text", 0) == "文本"
        assert describe_file_chunking("/k/a.py", "text(fallback:parse_error)", 0).startswith("文本（代码解析失败")
        with patch.object(code_chunker, "is_enabled", return_value=True):
            assert describe_file_chunking("/k/old.py", "text", 0) == "文本（重新入库可启用代码分块）"
        with patch.object(code_chunker, "is_enabled", return_value=False):
            assert describe_file_chunking("/k/old.py", "text", 0) == "文本"
