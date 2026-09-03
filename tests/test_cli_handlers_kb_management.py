#!/usr/bin/env python3
"""test_cli_handlers_kb_management.py — /file-delete、/snapshot-info|delete|prune|restore --apply、
/graph-summary、/graph-export 命令处理器与解析测试。"""
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import cli_handlers as h
from query_interface import ParsedCommand, classify_mode, parse_command


def _ctx(**kw):
    console = MagicMock()
    console.input.return_value = kw.pop("answer", "y")
    ctx = h.CLIContext(
        console=console, has_rich=False, record_command=MagicMock(),
        knowledge_management_available=kw.pop("km", True), **kw,
    )
    return ctx


def _printed(ctx):
    return "\n".join(str(c.args[0]) for c in ctx.console.print.call_args_list if c.args)


@pytest.fixture(autouse=True)
def _no_auto_confirm(monkeypatch):
    from config import Config
    monkeypatch.setattr(Config, "AUTO_CONFIRM", False, raising=False)


# ==================== 解析 ====================

class TestParse:
    @pytest.mark.parametrize("raw,cmd_type,arg", [
        ("/file-delete /a/b.md", "file_delete", "/a/b.md"),
        ("/snapshot-info s1", "snapshot_info", "s1"),
        ("/snapshot-delete s1", "snapshot_delete", "s1"),
        ("/snapshot-prune", "snapshot_prune", ""),
        ("/snapshot-prune 5", "snapshot_prune", "5"),
        ("/snapshot-restore s1 --apply --replace", "snapshot_restore", "s1 --apply --replace"),
        ("/graph-summary", "graph_summary", ""),
        ("/graph-export out.html --2d --focus Python", "graph_export", "out.html --2d --focus Python"),
    ])
    def test_new_commands(self, raw, cmd_type, arg):
        parsed = parse_command(raw)
        assert parsed == ParsedCommand(cmd_type, raw, arg)
        assert classify_mode(True, parsed) == "cmd"
        assert cmd_type in h.COMMAND_HANDLERS


# ==================== /file-delete ====================

class TestFileDelete:
    def _rag(self, exists=True, shared=False, nodes=2, edges=1):
        rag = MagicMock()
        rag.file_delete_preview.return_value = {
            "exists": exists, "file_name": "a.md", "chunk_count": 5,
            "graph_shared_basename": shared, "graph_nodes": nodes, "graph_edges": edges,
        }
        rag.remove_file.return_value = {"file_name": "a.md", "chunks_deleted": 5, "graph_updated": True, "note": ""}
        return rag

    def test_requires_arg_and_engine(self):
        ctx = _ctx()
        assert h.handle_file_delete(ctx, ParsedCommand("file_delete", "", "")) is False
        ctx = _ctx()
        assert h.handle_file_delete(ctx, ParsedCommand("file_delete", "", "/a.md")) is False
        assert "未初始化" in _printed(ctx)

    def test_confirm_and_delete(self):
        rag = self._rag()
        ctx = _ctx(rag_engine=rag)
        assert h.handle_file_delete(ctx, ParsedCommand("file_delete", "", "/x/a.md")) is True
        out = _printed(ctx)
        assert "5 个" in out and "2 个节点 / 1 条边" in out and "不会被删除" in out
        assert "已删除 a.md" in out and "/stats" in out
        rag.remove_file.assert_called_once_with("/x/a.md")
        ctx.record_command.assert_called_with("file_delete", "/x/a.md", "success")

    def test_cancel(self):
        rag = self._rag()
        ctx = _ctx(rag_engine=rag, answer="n")
        assert h.handle_file_delete(ctx, ParsedCommand("file_delete", "", "/x/a.md")) is True
        rag.remove_file.assert_not_called()
        assert "已取消" in _printed(ctx)

    def test_shared_and_no_graph_hints(self):
        ctx = _ctx(rag_engine=self._rag(shared=True))
        h.handle_file_delete(ctx, ParsedCommand("file_delete", "", "/x/a.md"))
        assert "另有同名文件" in _printed(ctx)
        ctx = _ctx(rag_engine=self._rag(nodes=0, edges=0))
        h.handle_file_delete(ctx, ParsedCommand("file_delete", "", "/x/a.md"))
        assert "图谱: 无变更" in _printed(ctx)

    def test_not_found_and_errors(self):
        ctx = _ctx(rag_engine=self._rag(exists=False))
        assert h.handle_file_delete(ctx, ParsedCommand("file_delete", "", "/x/a.md")) is False
        rag = self._rag()
        rag.remove_file.side_effect = FileNotFoundError("gone")
        ctx = _ctx(rag_engine=rag)
        assert h.handle_file_delete(ctx, ParsedCommand("file_delete", "", "/x/a.md")) is False
        rag.remove_file.side_effect = RuntimeError("boom")
        ctx = _ctx(rag_engine=rag)
        assert h.handle_file_delete(ctx, ParsedCommand("file_delete", "", "/x/a.md")) is True
        assert "boom" in _printed(ctx)


# ==================== 快照 ====================

@pytest.fixture
def snap_mgr():
    mgr = MagicMock()
    with patch("knowledge_snapshot.KnowledgeSnapshotManager", return_value=mgr):
        yield mgr


class TestSnapshotInfo:
    def test_prints_details(self, snap_mgr):
        snap_mgr.snapshot_info.return_value = {
            "snapshot_id": "s1", "timestamp": "t", "trigger": "manual", "document_count": 2,
            "total_chunks": 4, "missing_count": 1, "model_config": {"llm_model": "q", "embed_model": "e"},
            "documents": [{"file_name": "a.md", "file_path": "/a.md", "chunk_count": 2, "exists": True},
                          {"file_name": "b.md", "file_path": "/b.md", "chunk_count": 2, "exists": False}],
        }
        ctx = _ctx()
        assert h.handle_snapshot_info(ctx, ParsedCommand("snapshot_info", "", "s1")) is True
        out = _printed(ctx)
        assert "s1" in out and "✓ a.md" in out and "✗ b.md" in out and "将被跳过" in out

    def test_missing_arg_unknown_and_error(self, snap_mgr):
        assert h.handle_snapshot_info(_ctx(), ParsedCommand("snapshot_info", "", "")) is False
        assert h.handle_snapshot_info(_ctx(km=False), ParsedCommand("snapshot_info", "", "s")) is False
        snap_mgr.snapshot_info.return_value = None
        assert h.handle_snapshot_info(_ctx(), ParsedCommand("snapshot_info", "", "s")) is False
        snap_mgr.snapshot_info.side_effect = RuntimeError("x")
        ctx = _ctx()
        assert h.handle_snapshot_info(ctx, ParsedCommand("snapshot_info", "", "s")) is True
        assert "失败" in _printed(ctx)


class TestSnapshotDelete:
    def test_confirm_delete(self, snap_mgr):
        snap_mgr.load_snapshot.return_value = MagicMock(timestamp="t", documents=[1])
        snap_mgr.delete_snapshot.return_value = True
        ctx = _ctx()
        assert h.handle_snapshot_delete(ctx, ParsedCommand("snapshot_delete", "", "s1")) is True
        snap_mgr.delete_snapshot.assert_called_once_with("s1")
        assert "已删除" in _printed(ctx)

    def test_cancel_and_failures(self, snap_mgr):
        snap_mgr.load_snapshot.return_value = MagicMock(timestamp="t", documents=[])
        ctx = _ctx(answer="n")
        h.handle_snapshot_delete(ctx, ParsedCommand("snapshot_delete", "", "s1"))
        snap_mgr.delete_snapshot.assert_not_called()
        snap_mgr.delete_snapshot.return_value = False
        ctx = _ctx()
        h.handle_snapshot_delete(ctx, ParsedCommand("snapshot_delete", "", "s1"))
        assert "删除失败" in _printed(ctx)
        snap_mgr.load_snapshot.return_value = None
        assert h.handle_snapshot_delete(_ctx(), ParsedCommand("snapshot_delete", "", "s1")) is False
        assert h.handle_snapshot_delete(_ctx(), ParsedCommand("snapshot_delete", "", "")) is False
        snap_mgr.load_snapshot.side_effect = RuntimeError("x")
        assert h.handle_snapshot_delete(_ctx(), ParsedCommand("snapshot_delete", "", "s1")) is True


class TestSnapshotPrune:
    def test_preview_confirm_prune(self, snap_mgr):
        snap_mgr.prune_preview.return_value = [{"snapshot_id": "a", "timestamp": "t", "trigger": "document_added"}]
        snap_mgr.prune.return_value = ["a"]
        ctx = _ctx()
        assert h.handle_snapshot_prune(ctx, ParsedCommand("snapshot_prune", "", "3")) is True
        snap_mgr.prune_preview.assert_called_with(keep=3, auto_only=True)
        snap_mgr.prune.assert_called_with(keep=3, auto_only=True)
        assert "已清理 1 个" in _printed(ctx)

    def test_default_keep_nothing_cancel_bad_arg(self, snap_mgr):
        snap_mgr.prune_preview.return_value = []
        ctx = _ctx()
        h.handle_snapshot_prune(ctx, ParsedCommand("snapshot_prune", "", ""))
        snap_mgr.prune_preview.assert_called_with(keep=10, auto_only=True)
        assert "无需清理" in _printed(ctx)
        snap_mgr.prune_preview.return_value = [{"snapshot_id": "a", "timestamp": "t", "trigger": "x"}]
        h.handle_snapshot_prune(_ctx(answer="n"), ParsedCommand("snapshot_prune", "", ""))
        snap_mgr.prune.assert_not_called()
        assert h.handle_snapshot_prune(_ctx(), ParsedCommand("snapshot_prune", "", "abc")) is False
        snap_mgr.prune_preview.side_effect = RuntimeError("x")
        assert h.handle_snapshot_prune(_ctx(), ParsedCommand("snapshot_prune", "", "")) is True


class TestSnapshotRestore:
    def _snapshot(self, tmp_path):
        present = tmp_path / "a.md"
        present.write_text("a", encoding="utf-8")
        snap = MagicMock()
        snap.documents = [MagicMock(file_path=str(present)), MagicMock(file_path=str(tmp_path / "gone.md"))]
        return snap

    def test_default_generates_script(self, snap_mgr, tmp_path):
        snap_mgr.load_snapshot.return_value = self._snapshot(tmp_path)
        with patch("knowledge_snapshot.RestoreHelper") as helper_cls:
            helper_cls.return_value.generate_restore_script.return_value = "restore.py"
            ctx = _ctx()
            assert h.handle_snapshot_restore(ctx, ParsedCommand("snapshot_restore", "", "s1")) is True
        assert "restore.py" in _printed(ctx) and "--apply" in _printed(ctx)

    def test_apply_append(self, snap_mgr, tmp_path):
        snap_mgr.load_snapshot.return_value = self._snapshot(tmp_path)
        snap_mgr.restore_apply.return_value = {"ok": True, "restored": 1, "skipped": 1, "failed": 0, "chunks": 2,
                                               "errors": []}
        rag = MagicMock()
        ctx = _ctx(rag_engine=rag, load_documents=MagicMock())
        assert h.handle_snapshot_restore(ctx, ParsedCommand("snapshot_restore", "", "s1 --apply")) is True
        kwargs = snap_mgr.restore_apply.call_args.kwargs
        assert kwargs["mode"] == "append" and kwargs["load_documents"] is ctx.load_documents
        # 进度回调可用
        kwargs["progress"]({"stage": "load", "message": "加载 a.md", "current": 1, "total": 1})
        kwargs["progress"]({"stage": "plan", "message": "计划"})
        out = _printed(ctx)
        assert "将跳过" in out and "gone.md" in out and "恢复完成（append）" in out and "/stats" in out
        ctx.console.input.assert_not_called()

    def test_apply_replace_confirms(self, snap_mgr, tmp_path):
        snap_mgr.load_snapshot.return_value = self._snapshot(tmp_path)
        snap_mgr.restore_apply.return_value = {"ok": True, "restored": 1, "skipped": 1, "failed": 1, "chunks": 2,
                                               "errors": ["/b: bad"]}
        ctx = _ctx(rag_engine=MagicMock())
        h.handle_snapshot_restore(ctx, ParsedCommand("snapshot_restore", "", "s1 --apply --replace"))
        assert snap_mgr.restore_apply.call_args.kwargs["mode"] == "replace"
        assert "/b: bad" in _printed(ctx)
        ctx = _ctx(rag_engine=MagicMock(), answer="n")
        snap_mgr.restore_apply.reset_mock()
        h.handle_snapshot_restore(ctx, ParsedCommand("snapshot_restore", "", "s1 --apply --replace"))
        snap_mgr.restore_apply.assert_not_called()
        assert "已取消" in _printed(ctx)

    def test_apply_errors(self, snap_mgr, tmp_path):
        snap_mgr.load_snapshot.return_value = self._snapshot(tmp_path)
        assert h.handle_snapshot_restore(_ctx(), ParsedCommand("snapshot_restore", "", "s1 --apply")) is False
        snap_mgr.restore_apply.return_value = {"ok": False, "error": "bad"}
        ctx = _ctx(rag_engine=MagicMock())
        assert h.handle_snapshot_restore(ctx, ParsedCommand("snapshot_restore", "", "s1 --apply")) is True
        assert "bad" in _printed(ctx)
        assert h.handle_snapshot_restore(_ctx(), ParsedCommand("snapshot_restore", "", "--apply")) is False
        snap_mgr.load_snapshot.return_value = None
        assert h.handle_snapshot_restore(_ctx(), ParsedCommand("snapshot_restore", "", "s1")) is False


# ==================== 图谱 ====================

class TestGraphSummary:
    def test_prints_stats(self):
        builder = MagicMock()
        stats = builder.get_statistics.return_value
        stats.total_nodes, stats.total_edges = 171, 1458
        stats.connected_components, stats.average_degree, stats.density = 3, 17.05, 0.05
        stats.entity_types = {"tool": 100, "concept": 71}
        stats.relation_types = {"uses": 1458}
        ctx = _ctx()
        with patch("knowledge_graph.get_graph_builder", return_value=builder):
            assert h.handle_graph_summary(ctx, ParsedCommand("graph_summary", "", "")) is True
        out = _printed(ctx)
        assert "节点: 171" in out and "tool" in out and "uses" in out and "/graph-export" in out

    def test_empty_and_unavailable(self):
        builder = MagicMock()
        stats = builder.get_statistics.return_value
        stats.total_nodes = stats.total_edges = 0
        stats.entity_types = {}
        stats.relation_types = {}
        stats.connected_components, stats.average_degree, stats.density = 0, 0.0, 0.0
        ctx = _ctx()
        with patch("knowledge_graph.get_graph_builder", return_value=builder):
            h.handle_graph_summary(ctx, ParsedCommand("graph_summary", "", ""))
        assert "图谱为空" in _printed(ctx)
        with patch("knowledge_graph.get_graph_builder", return_value=MagicMock(graph=None)):
            assert h.handle_graph_summary(_ctx(), ParsedCommand("graph_summary", "", "")) is False
        with patch("knowledge_graph.get_graph_builder", side_effect=RuntimeError("x")):
            assert h.handle_graph_summary(_ctx(), ParsedCommand("graph_summary", "", "")) is True


class TestGraphExportArgs:
    def test_parse_all(self):
        o = h.parse_graph_export_args("out.html --2d --types tool,concept --max 50 --focus Python 3 --hops 2")
        assert o == {"path": "out.html", "dim": 2, "types": ["tool", "concept"], "max_nodes": 50,
                     "focus": "Python 3", "hops": 2, "error": ""}
        assert h.parse_graph_export_args("")["dim"] == 3
        assert h.parse_graph_export_args("--3d")["path"] == ""

    @pytest.mark.parametrize("arg", ["--types", "--max x", "--hops", "--focus", "--weird", "--max"])
    def test_parse_errors(self, arg):
        assert h.parse_graph_export_args(arg)["error"]


class TestGraphExport:
    def _builder(self, nodes=2):
        builder = MagicMock()
        builder.subgraph_for_view.return_value = {
            "nodes": [{"id": f"n{i}", "text": f"N{i}", "entity_type": "tool", "degree": 1, "documents": []}
                      for i in range(nodes)],
            "edges": [{"source": "n0", "target": "n1", "relation_type": "uses", "confidence": 1, "documents": []}]
            if nodes > 1 else [],
            "total_nodes": nodes, "total_edges": 1, "truncated": nodes > 1,
        }
        builder.layout_positions.return_value = {f"n{i}": (0.0, float(i), 0.0) for i in range(nodes)}
        return builder

    def test_exports_html_and_opens(self, tmp_path):
        opener = MagicMock()
        out = tmp_path / "g"
        ctx = _ctx()
        with patch("knowledge_graph.get_graph_builder", return_value=self._builder()):
            assert h.handle_graph_export(
                ctx, ParsedCommand("graph_export", "", f"{out} --3d --focus N0"), open_browser=opener,
            ) is True
        html = out.with_suffix(".html")
        assert html.exists() and "plotly" in html.read_text(encoding="utf-8")[:200000].lower()
        opener.assert_called_once_with(html.resolve().as_uri())
        assert "已导出 3D 图谱" in _printed(ctx) and "已按度数截断" in _printed(ctx)
        ctx.record_command.assert_called_with("graph_export", str(html), "success")

    def test_default_filename_in_cwd(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        ctx = _ctx()
        with patch("knowledge_graph.get_graph_builder", return_value=self._builder()):
            h.handle_graph_export(ctx, ParsedCommand("graph_export", "", "--2d"), open_browser=MagicMock())
        assert list(tmp_path.glob("knowledge_graph_*.html"))

    def test_open_failure_is_warning(self, tmp_path):
        ctx = _ctx()
        with patch("knowledge_graph.get_graph_builder", return_value=self._builder()):
            h.handle_graph_export(
                ctx, ParsedCommand("graph_export", "", str(tmp_path / "x.html")),
                open_browser=MagicMock(side_effect=RuntimeError("no browser")),
            )
        assert "无法自动打开浏览器" in _printed(ctx)

    def test_default_opener_uses_webbrowser(self, tmp_path):
        ctx = _ctx()
        with patch("knowledge_graph.get_graph_builder", return_value=self._builder()), \
                patch("webbrowser.open") as wb:
            h.handle_graph_export(ctx, ParsedCommand("graph_export", "", str(tmp_path / "x.html")))
        wb.assert_called_once()

    def test_empty_bad_args_unavailable(self, tmp_path):
        assert h.handle_graph_export(_ctx(), ParsedCommand("graph_export", "", "--max q")) is False
        ctx = _ctx()
        with patch("knowledge_graph.get_graph_builder", return_value=self._builder(nodes=0)):
            assert h.handle_graph_export(ctx, ParsedCommand("graph_export", "", "")) is True
        assert "没有可导出" in _printed(ctx)
        with patch("knowledge_graph.get_graph_builder", return_value=MagicMock(graph=None)):
            assert h.handle_graph_export(_ctx(), ParsedCommand("graph_export", "", "")) is False
        with patch("knowledge_graph.get_graph_builder", side_effect=RuntimeError("x")):
            assert h.handle_graph_export(_ctx(), ParsedCommand("graph_export", "", "")) is True

    def test_missing_plotly(self, tmp_path):
        ctx = _ctx()
        with patch("knowledge_graph.get_graph_builder", return_value=self._builder()), \
                patch("web.app.build_graph_figure", side_effect=ImportError("no plotly")):
            assert h.handle_graph_export(ctx, ParsedCommand("graph_export", "", str(tmp_path / "x"))) is False
        assert "plotly" in _printed(ctx)
