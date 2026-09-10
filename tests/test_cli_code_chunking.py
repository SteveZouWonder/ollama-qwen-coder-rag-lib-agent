#!/usr/bin/env python3
"""test_cli_code_chunking.py — F8 P4：CLI /add 入库摘要、/file-list、/file-info 分块策略、/sources 符号行号。"""
from unittest.mock import MagicMock, patch

import pytest

import cli_handlers as h
import code_chunker
from query_interface import ParsedCommand


def _ctx(rag=None, docs=None):
    console = MagicMock()
    ctx = h.CLIContext(
        console=console, has_rich=False, rag_engine=rag or MagicMock(),
        load_documents=MagicMock(return_value=docs if docs is not None else [MagicMock()]),
        record_command=MagicMock(),
    )
    return ctx


def _printed(ctx):
    return "\n".join(str(c.args[0]) for c in ctx.console.print.call_args_list if c.args)


@pytest.fixture(autouse=True)
def _reset_hint():
    code_chunker.reset_hint()
    code_chunker.reset_availability_cache()
    yield
    code_chunker.reset_hint()
    code_chunker.reset_availability_cache()


class TestHandleAddSummary:
    def test_summary_with_code_files(self):
        rag = MagicMock()
        rag.last_graph_derived = True
        rag.last_ingest_stats = {
            "/k/a.py": {"chunk_count": 20, "symbol_count": 15, "chunk_strategy": "code(python)"},
            "/k/b.md": {"chunk_count": 5, "symbol_count": 0, "chunk_strategy": "text"},
        }
        ctx = _ctx(rag)
        assert h.handle_add(ctx, ParsedCommand("add", "/add k", "k")) is True
        out = _printed(ctx)
        assert "✅ 已入库 2 个文件 · 25 个片段（其中 1 个代码文件按函数/类切分，共 15 个符号）" in out
        # MagicMock console 不渲染进度条，仍传入 progress_callback
        assert rag.add_documents.call_args.kwargs.get("progress_callback") is not None or rag.add_documents.called

    def test_hint_once_when_disabled_and_code_present(self, monkeypatch):
        monkeypatch.setattr(code_chunker, "_load_pack", lambda: None)
        monkeypatch.setattr(code_chunker, "CODE_AWARE_CHUNKING", True)
        rag = MagicMock()
        rag.last_ingest_stats = {"/k/a.py": {"chunk_count": 2, "symbol_count": 0, "chunk_strategy": "text"}}
        ctx = _ctx(rag)
        h.handle_add(ctx, ParsedCommand("add", "/add a.py", "a.py"))
        assert "💡 代码感知分块未启用" in _printed(ctx)
        ctx2 = _ctx(rag)
        h.handle_add(ctx2, ParsedCommand("add", "/add a.py", "a.py"))
        assert "代码感知分块未启用" not in _printed(ctx2)

    def test_no_hint_for_non_code_files(self, monkeypatch):
        monkeypatch.setattr(code_chunker, "_load_pack", lambda: None)
        rag = MagicMock()
        rag.last_ingest_stats = {"/k/b.md": {"chunk_count": 2, "symbol_count": 0, "chunk_strategy": "text"}}
        ctx = _ctx(rag)
        h.handle_add(ctx, ParsedCommand("add", "/add b.md", "b.md"))
        assert "代码感知分块未启用" not in _printed(ctx)
        assert "✅ 已入库 1 个文件 · 2 个片段" in _printed(ctx)

    def test_legacy_message_without_stats(self):
        rag = MagicMock()
        rag.last_ingest_stats = {}
        ctx = _ctx(rag)
        h.handle_add(ctx, ParsedCommand("add", "/add x", "x"))
        assert "✅ 文档已添加到知识库" in _printed(ctx)

    def test_progress_with_real_console(self):
        from rich.console import Console
        rag = MagicMock()
        rag.last_ingest_stats = {}

        def fake_add(docs, paths, progress_callback=None):
            progress_callback({"stage": "chunk", "message": "切分 a (1/2)", "current": 1, "total": 2})
            progress_callback({"stage": "embed", "message": "生成向量 3/6", "current": 3, "total": 6})
            progress_callback({"phase": "other", "message": "忽略"})
            progress_callback({"stage": "embed", "message": "生成向量 6/6", "current": 6, "total": 6})

        rag.add_documents.side_effect = fake_add
        console = Console(file=MagicMock(), force_terminal=False, width=80)
        ctx = h.CLIContext(console=console, has_rich=True, rag_engine=rag,
                           load_documents=MagicMock(return_value=[MagicMock()]), record_command=MagicMock())
        assert h.handle_add(ctx, ParsedCommand("add", "/add a", "a")) is True
        assert rag.add_documents.call_args.kwargs["progress_callback"] is not None

    def test_make_ingest_progress_non_console(self):
        assert h._make_ingest_progress(MagicMock()) == (None, None)


class TestFileListAndInfo:
    def _meta(self, **kw):
        m = MagicMock()
        m.file_path = kw.get("file_path", "/k/a.py")
        m.file_size = 10
        m.persistence_type = "permanent"
        m.upload_time = "2026-01-01T00:00:00"
        m.access_count = 0
        m.document_count = 1
        m.chunk_count = kw.get("chunk_count", 9)
        m.chunk_strategy = kw.get("chunk_strategy", "code(python)")
        m.symbol_count = kw.get("symbol_count", 7)
        m.last_access = None
        m.tags = []
        return m

    def test_file_list_shows_strategy_line(self):
        manager = MagicMock()
        manager.list_files.return_value = [self._meta(), self._meta(file_path="/k/b.md", chunk_strategy="text", symbol_count=0, chunk_count=3)]
        manager._format_size.return_value = "10 B"
        ctx = _ctx()
        with patch("file_metadata.get_global_metadata_manager", return_value=manager):
            assert h.handle_file_list(ctx, ParsedCommand("file_list", "", "")) is True
        out = _printed(ctx)
        assert "🧩 片段: 9 · 分块: 代码(python) · 7 个符号" in out
        assert "🧩 片段: 3 · 分块: 文本" in out

    def test_file_list_old_code_file_suggests_reingest(self):
        manager = MagicMock()
        manager.list_files.return_value = [self._meta(chunk_strategy="text", symbol_count=0)]
        manager._format_size.return_value = "10 B"
        ctx = _ctx()
        with patch("file_metadata.get_global_metadata_manager", return_value=manager), \
             patch.object(code_chunker, "is_enabled", return_value=True):
            h.handle_file_list(ctx, ParsedCommand("file_list", "", ""))
        assert "文本（重新入库可启用代码分块）" in _printed(ctx)

    def test_file_info_shows_strategy(self):
        manager = MagicMock()
        manager.get_file_metadata.return_value = self._meta()
        manager._format_size.return_value = "10 B"
        ctx = _ctx()
        with patch("file_metadata.get_global_metadata_manager", return_value=manager):
            assert h.handle_file_info(ctx, ParsedCommand("file_info", "", "/k/a.py")) is True
        out = _printed(ctx)
        assert "🧩 Chunk数: 9" in out and "🧬 分块策略: 代码(python) · 7 个符号" in out


class TestSourcesLocation:
    def test_plain_output_shows_symbol_and_lines(self, capsys):
        import query_interface as qi
        with patch("cli.state.HAS_RICH", False):
            qi.print_rag_sources([
                {"file": "rag_engine.py", "score": 0.7, "content": "def _ensure_bm25", "ref": "1",
                 "symbol": "RAGEngine._ensure_bm25", "start_line": 534, "end_line": 581},
                {"file": "a.md", "score": 0.5, "content": "文本", "ref": "2"},
            ])
        out = capsys.readouterr().out
        assert "[1] rag_engine.py · RAGEngine._ensure_bm25 · L534-581 (0.700)" in out
        assert "[2] a.md (0.500)" in out

    def test_rich_table_includes_location_cell(self):
        import query_interface as qi
        with patch("cli.state.HAS_RICH", True), patch("cli.state.console") as console:
            qi.print_rag_sources([{"file": "a.py", "score": 0.7, "content": "x", "ref": "1",
                                   "symbol": "f", "start_line": 1, "end_line": 3, "part": "1/2"}])
            table = console.print.call_args.args[0]
        cells = [str(c) for col in table.columns for c in col._cells]
        assert any("f · L1-3 · (1/2)" in c for c in cells)

    def test_helpers(self):
        import query_interface as qi
        assert qi._source_code_location({"symbol": "f", "start_line": 1}) == "f · L1-1"
        assert qi._source_code_location({"file": "a.md"}) == ""
        assert qi.count_code_sources([{"symbol": "a"}, {"file": "b"}, "junk"]) == 1
