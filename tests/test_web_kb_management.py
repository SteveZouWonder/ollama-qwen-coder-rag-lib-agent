#!/usr/bin/env python3
"""test_web_kb_management.py — Web 端「文件删除 / 快照管理 / 图谱可视化」的服务层与处理器测试。"""
from unittest.mock import MagicMock, patch

import pytest

from web import app as web_app
from web.app import (
    build_graph_figure,
    build_handlers,
    format_file_action_bar,
    format_file_delete_prompt,
    format_graph_summary_cards,
    format_graph_view_stats,
    format_prune_preview,
    format_restore_result,
    format_snapshot_info,
    snapshot_doc_rows,
)
from web.services import StreamEvent, WebService


# ==================== 服务层 ====================

def _svc(rag=None, **kw):
    rag = rag if rag is not None else MagicMock()
    return WebService(
        rag_factory=lambda: rag, react_factory=MagicMock(), orchestrator_factory=MagicMock(),
        session_manager_factory=MagicMock(), graph_query_factory=MagicMock(),
        set_rag_engine=MagicMock(), load_documents=kw.pop("load_documents", MagicMock()),
        resolve_mode=lambda n: n, model_switcher_factory=MagicMock(),
    )


class TestRemoveFileService:
    def test_success_message(self):
        rag = MagicMock()
        rag.remove_file.return_value = {"file_name": "a.md", "chunks_deleted": 42, "graph_updated": True, "note": ""}
        assert _svc(rag).remove_file("/x/a.md") == "[成功] 已删除 a.md：42 个片段，图谱已更新"

    def test_note_when_graph_kept(self):
        rag = MagicMock()
        rag.remove_file.return_value = {"chunks_deleted": 1, "graph_updated": False, "note": "图谱保留：另有同名文件 a.md"}
        assert "图谱保留" in _svc(rag).remove_file("/x/a.md")
        rag.remove_file.return_value = {"chunks_deleted": 1, "graph_updated": False, "note": ""}
        assert _svc(rag).remove_file("/x/a.md").endswith("图谱未变更")

    def test_errors(self):
        rag = MagicMock()
        assert _svc(rag).remove_file("  ").startswith("[提示]")
        rag.remove_file.side_effect = FileNotFoundError("文件不在知识库中: /x")
        assert _svc(rag).remove_file("/x") == "[错误] 文件不在知识库中: /x"
        rag.remove_file.side_effect = RuntimeError("boom")
        assert "boom" in _svc(rag).remove_file("/x")

    def test_preview(self):
        rag = MagicMock()
        rag.file_delete_preview.return_value = {"chunk_count": 3}
        svc = _svc(rag)
        assert svc.file_delete_preview("/x")["chunk_count"] == 3
        assert svc.file_delete_preview("")["error"]
        rag.file_delete_preview.side_effect = RuntimeError("x")
        assert svc.file_delete_preview("/x")["error"] == "x"


class TestSnapshotService:
    def _mgr(self):
        mgr = MagicMock()
        patcher = patch("knowledge_snapshot.KnowledgeSnapshotManager", return_value=mgr)
        return mgr, patcher

    def test_info_delete_prune(self):
        mgr, p = self._mgr()
        svc = _svc()
        with p:
            mgr.snapshot_info.return_value = {"snapshot_id": "s"}
            assert svc.snapshot_info("s") == {"snapshot_id": "s"}
            mgr.snapshot_info.return_value = None
            assert "不存在" in svc.snapshot_info("s")["error"]
            assert svc.snapshot_info("")["error"]
            mgr.delete_snapshot.return_value = True
            assert svc.snapshot_delete("s").startswith("[成功]")
            mgr.delete_snapshot.return_value = False
            assert svc.snapshot_delete("s").startswith("[错误]")
            assert svc.snapshot_delete("").startswith("[提示]")
            mgr.prune_preview.return_value = [{"snapshot_id": "a"}]
            assert svc.snapshot_prune_preview(3) == [{"snapshot_id": "a"}]
            mgr.prune_preview.assert_called_with(keep=3, auto_only=True)
            mgr.prune.return_value = ["a", "b"]
            assert svc.snapshot_prune(3) == "[成功] 已清理 2 个自动快照，保留最近 3 个"
            mgr.prune.return_value = []
            assert svc.snapshot_prune(3).startswith("[提示]")
            mgr.snapshot_info.side_effect = RuntimeError("e1")
            assert svc.snapshot_info("s")["error"] == "e1"
            mgr.delete_snapshot.side_effect = RuntimeError("e2")
            assert "e2" in svc.snapshot_delete("s")
            mgr.prune_preview.side_effect = RuntimeError("e3")
            assert svc.snapshot_prune_preview(1)[0]["snapshot_id"].startswith("[错误]")
            mgr.prune.side_effect = RuntimeError("e4")
            assert "e4" in svc.snapshot_prune(1)

    def test_restore_apply_and_stream(self):
        mgr, p = self._mgr()
        rag = MagicMock()
        loader = MagicMock()
        svc = _svc(rag, load_documents=loader)
        svc.heartbeat_interval = 0.05

        def fake_restore(sid, engine, mode="append", load_documents=None, progress=None):
            if progress:
                progress({"stage": "load", "message": "加载 a.md", "current": 1, "total": 1})
            return {"ok": True, "restored": 1, "skipped": 0, "failed": 0, "mode": mode}

        with p:
            mgr.restore_apply.side_effect = fake_restore
            result = svc.snapshot_restore_apply("s", mode="replace")
            assert result["ok"] and result["mode"] == "replace"
            assert mgr.restore_apply.call_args.kwargs["load_documents"] is loader
            events = list(svc.snapshot_restore_stream("s", mode="append"))
        kinds = [e.kind for e in events if e.kind != "heartbeat"]
        assert kinds == ["progress", "answer"]
        assert events[-1].message.startswith("恢复完成") and events[-1].data["restored"] == 1

    def test_restore_stream_errors(self):
        mgr, p = self._mgr()
        svc = _svc()
        assert list(svc.snapshot_restore_stream(""))[0].kind == "error"
        assert svc.snapshot_restore_apply("")["ok"] is False
        with p:
            mgr.restore_apply.return_value = {"ok": False, "error": "快照不存在: s"}
            events = list(svc.snapshot_restore_stream("s"))
            assert events[-1].kind == "error" and "不存在" in events[-1].message
            mgr.restore_apply.side_effect = RuntimeError("boom")
            assert svc.snapshot_restore_apply("s")["error"] == "boom"
            events = list(svc.snapshot_restore_stream("s"))
            assert events[-1].kind == "error" and "boom" in events[-1].message


class TestGraphViewService:
    def test_view_data_and_types(self):
        builder = MagicMock()
        builder.subgraph_for_view.return_value = {"nodes": [{"id": "a"}], "edges": [], "total_nodes": 1,
                                                  "total_edges": 0, "truncated": False}
        builder.layout_positions.return_value = {"a": (0.0, 0.0, 0.0)}
        stats = MagicMock()
        stats.entity_types = {"tool": 2, "concept": 5}
        builder.get_statistics.return_value = stats
        svc = _svc()
        with patch("knowledge_graph.get_graph_builder", return_value=builder):
            view = svc.graph_view_data(types=["tool"], max_nodes=10, dim=2)
            assert view["positions"] == {"a": (0.0, 0.0, 0.0)} and view["dim"] == 2
            builder.layout_positions.assert_called_with(["a"], dim=2)
            assert svc.graph_entity_types() == ["concept", "tool"]
        with patch("knowledge_graph.get_graph_builder", side_effect=RuntimeError("nx missing")):
            view = svc.graph_view_data()
            assert view["nodes"] == [] and view["error"] == "nx missing"
            assert svc.graph_entity_types() == []


# ==================== 格式化 ====================

class TestFormatters:
    def test_file_delete_prompt(self):
        assert format_file_delete_prompt({}) == ""
        assert format_file_delete_prompt({"error": "x"}).startswith("❌")
        assert "不在知识库" in format_file_delete_prompt({"exists": False, "file_name": "a.md"})
        p = format_file_delete_prompt({"exists": True, "file_name": "a.md", "chunk_count": 5, "graph_nodes": 2, "graph_edges": 1})
        assert "**5 个片段**" in p and "2 个节点 / 1 条边" in p and "不删除磁盘文件" in p
        assert "另有同名" in format_file_delete_prompt({"exists": True, "graph_shared_basename": True})
        assert "无变更" in format_file_delete_prompt({"exists": True, "file_path": "/a"})

    def test_action_bar(self):
        assert format_file_action_bar("") == ""
        html = format_file_action_bar("/x/y/a.md")
        assert "<b>a.md</b>" in html and 'title="/x/y/a.md"' in html
        assert "<b>a.md</b>" in format_file_action_bar("a.md")

    def test_snapshot_info_and_rows(self):
        assert format_snapshot_info({}) == ""
        assert format_snapshot_info({"error": "e"}) == "_e_"
        info = {
            "snapshot_id": "s1", "timestamp": "2026-01-01T10:00:00.123", "trigger": "batch_added",
            "document_count": 2, "total_chunks": 7, "missing_count": 1,
            "model_config": {"llm_model": "qwen", "embed_model": "nomic"},
            "documents": [
                {"file_name": "a.md", "file_type": ".md", "chunk_count": 3, "file_path": "/a.md", "exists": True},
                {"file_name": "b.md", "file_type": "", "chunk_count": 4, "file_path": "/b.md", "exists": False},
            ],
        }
        md = format_snapshot_info(info)
        assert "`s1`" in md and "2026-01-01 10:00:00" in md and "自动（批量入库）" in md
        assert "2 / 7" in md and "`qwen`" in md and "1 个文件已不在磁盘上" in md
        rows = snapshot_doc_rows(info)
        assert rows[0][0].startswith("✅") and rows[0][1] == "a.md" and rows[0][2] == ".md"
        assert "❌" in rows[1][0] and "#dc2626" in rows[1][1] and rows[1][2] == "—"
        assert snapshot_doc_rows({}) == []

    def test_restore_result(self):
        assert format_restore_result({}) == ""
        assert format_restore_result({"ok": False, "error": "x"}) == "❌ x"
        out = format_restore_result({"ok": True, "snapshot_id": "s", "mode": "replace", "restored": 2, "skipped": 1,
                                     "failed": 1, "chunks": 9, "missing": [f"/m{i}" for i in range(25)],
                                     "errors": ["/e: bad"]})
        assert "替换" in out and "**2**" in out and "共 25 个" in out and "/e: bad" in out
        assert "追加" in format_restore_result({"ok": True, "mode": "append"})

    def test_prune_preview(self):
        assert format_prune_preview([], 10).startswith("✅")
        assert format_prune_preview([{"snapshot_id": "[错误] x"}], 1).startswith("❌")
        out = format_prune_preview([{"snapshot_id": f"s{i}", "timestamp": "2026-01-01T00:00:00"} for i in range(20)], 3)
        assert "**20**" in out and "保留最近 3 个" in out and "共 20 个" in out

    def test_graph_view_stats(self):
        assert format_graph_view_stats({}) == ""
        assert format_graph_view_stats({"error": "e"}).startswith("❌")
        assert "图谱为空" in format_graph_view_stats({"nodes": [], "total_nodes": 0})
        view = {"nodes": [{"entity_type": "tool"}, {"entity_type": "tool"}, {"entity_type": "concept"}],
                "edges": [{}], "total_nodes": 10, "total_edges": 5, "truncated": True, "dim": 2,
                "focus": "Python", "hops": 2}
        out = format_graph_view_stats(view)
        assert "**3** / 10 节点" in out and "**1** / 5 边" in out and "2D" in out
        assert "tool 2 · concept 1" in out and "已按度数截取" in out and "`Python`（2 跳）" in out

    def test_graph_summary_cards(self):
        assert "不可用" in format_graph_summary_cards({"is_available": False, "error": "e"})
        html = format_graph_summary_cards({"is_available": True, "statistics": {
            "total_nodes": 171, "total_edges": 1458, "entity_types": {"a": 1, "b": 2}, "relation_types": {"r": 1},
            "connected_components": 3, "average_degree": 17.05, "density": 0.0501,
        }})
        assert "cb-cards" in html and ">171<" in html and ">1458<" in html and ">2<" in html
        assert "17.05 / 0.0501" in html
        assert "cb-cards" in format_graph_summary_cards({})


# ==================== build_graph_figure ====================

_NODES = [
    {"id": "tool_a", "text": "A", "entity_type": "tool", "degree": 3, "confidence": 0.9, "documents": ["x.md"]},
    {"id": "concept_b", "text": "B", "entity_type": "concept", "degree": 1, "confidence": 0.5,
     "documents": [f"d{i}.md" for i in range(8)]},
    {"id": "weird", "text": "W", "entity_type": "alien", "degree": 0, "confidence": 0.1, "documents": []},
]
_EDGES = [
    {"source": "tool_a", "target": "concept_b", "relation_type": "uses", "confidence": 0.8, "documents": ["x.md"]},
    {"source": "tool_a", "target": "ghost", "relation_type": "uses", "confidence": 0.8, "documents": []},
]


class TestBuildGraphFigure:
    def test_3d_figure(self):
        fig = build_graph_figure(_NODES, _EDGES, dim=3, title="T")
        names = [type(t).__name__ for t in fig.data]
        assert names[:2] == ["Scatter3d", "Scatter3d"]  # 边线 + 边中点
        assert len(fig.data) == 2 + 3  # 三种类型各一条
        node_trace = next(t for t in fig.data if t.name.startswith("tool"))
        assert node_trace.marker.color == web_app.GRAPH_TYPE_COLORS["tool"]
        assert "来源: x.md" in node_trace.hovertext[0]
        assert fig.layout.title.text == "T" and fig.layout.scene is not None
        # 未知类型回落到 other 色
        alien = next(t for t in fig.data if t.name.startswith("alien"))
        assert alien.marker.color == web_app.GRAPH_TYPE_COLORS["other"]
        # 边 hover 含关系类型；悬空边被忽略
        edge_mid = fig.data[1]
        assert len(edge_mid.hovertext) == 1 and "[uses]" in edge_mid.hovertext[0]

    def test_2d_with_edge_labels_and_positions(self):
        pos = {"tool_a": (0.0, 0.0), "concept_b": (1.0, 1.0), "weird": (2.0, 0.5)}
        fig = build_graph_figure(_NODES, _EDGES, dim=2, positions=pos, edge_labels=True)
        assert type(fig.data[0]).__name__ == "Scatter"
        assert fig.data[1].mode == "markers+text" and list(fig.data[1].text) == ["uses"]
        assert tuple(fig.data[1].x) == (0.5,)  # 中点用传入坐标
        fig2 = build_graph_figure(_NODES, _EDGES, dim=2, positions=pos, edge_labels=False)
        assert fig2.data[1].mode == "markers"

    def test_partial_positions_recomputed(self):
        fig = build_graph_figure(_NODES, _EDGES, dim=2, positions={"tool_a": (0, 0)})
        assert len(fig.data) == 5

    def test_empty(self):
        fig = build_graph_figure([], [], dim=3)
        assert not fig.data and "暂无图谱数据" in fig.layout.annotations[0].text

    def test_no_edges(self):
        fig = build_graph_figure(_NODES[:1], [], dim=3)
        assert len(fig.data) == 1

    def test_hover_docs_truncation(self):
        assert web_app._hover_docs([]) == "—"
        assert web_app._hover_docs([f"d{i}" for i in range(8)]).endswith("等 8 个")
        assert web_app._node_size(0, 3) < web_app._node_size(50, 3)
        assert web_app._node_size(60, 3) == web_app._node_size(600, 3)


# ==================== 处理器 ====================

def _mock_service():
    svc = MagicMock()
    svc.file_list.return_value = [{"path": "/x/a.md", "size": "1 KB", "type": "permanent",
                                   "upload_time": "t", "chunk_count": 2, "access_count": 0}]
    svc.get_stats.return_value = {"total_documents": 2}
    svc.snapshot_list_data.return_value = [{"snapshot_id": "s", "timestamp": "t", "document_count": 1,
                                            "total_chunks": 2, "trigger": "manual"}]
    return svc


class TestFileHandlers:
    def test_action_bar_preview_delete(self):
        svc = _mock_service()
        svc.file_delete_preview.return_value = {"exists": True, "file_name": "a.md", "chunk_count": 2}
        svc.remove_file.return_value = "[成功] 已删除 a.md：2 个片段，图谱已更新"
        h = build_handlers(svc)
        assert "<b>a.md</b>" in h["on_file_action_bar"]("/x/a.md")
        assert "**2 个片段**" in h["on_file_delete_preview"]("/x/a.md")
        msg, rows, cards = h["on_file_delete"]("/x/a.md")
        assert msg.startswith("✅") and rows[0][0] == "a.md" and "cb-cards" in cards
        svc.remove_file.assert_called_with("/x/a.md")


class TestSnapshotHandlers:
    def test_info_delete_prune(self):
        svc = _mock_service()
        svc.snapshot_info.return_value = {"snapshot_id": "s", "trigger": "manual", "documents": [
            {"file_name": "a.md", "exists": True, "file_path": "/a.md", "chunk_count": 1}]}
        svc.snapshot_delete.return_value = "[成功] 已删除快照 s"
        svc.snapshot_prune_preview.return_value = [{"snapshot_id": "x", "timestamp": "t"}]
        svc.snapshot_prune.return_value = "[成功] 已清理 1 个自动快照，保留最近 5 个"
        h = build_handlers(svc)
        md, rows = h["on_snapshot_info"]("s")
        assert "`s`" in md and rows[0][1] == "a.md"
        assert h["headers"]["snapshot_docs"][0] == "状态"
        msg, table = h["on_snapshot_delete"]("s")
        assert msg.startswith("✅") and table[0][0] == "s"
        assert "**1**" in h["on_snapshot_prune_preview"](5.0)
        svc.snapshot_prune_preview.assert_called_with(5)
        msg, table = h["on_snapshot_prune"](5.0)
        assert msg.startswith("✅")
        svc.snapshot_prune.assert_called_with(5)

    def test_restore_stream_success(self):
        svc = _mock_service()
        svc.snapshot_restore_stream.return_value = iter([
            StreamEvent("progress", "加载 a.md", {"stage": "load", "current": 1, "total": 2}),
            StreamEvent("heartbeat", "", {"elapsed": 1}),
            StreamEvent("progress", "加载 b.md", {"stage": "load", "current": 2, "total": 2}),
            StreamEvent("answer", "恢复完成", {"ok": True, "snapshot_id": "s", "mode": "append",
                                             "restored": 2, "skipped": 0, "failed": 0, "chunks": 4}),
        ])
        outs = list(build_handlers(svc)["on_snapshot_restore_stream"]("s", "append"))
        assert outs[0][0].startswith("⏳") and outs[-1][0].startswith("✅")
        assert "**2**" in outs[-1][1]
        # 计数类事件原地刷新：恢复进度只保留一行
        assert outs[-2][1].count("加载") == 1
        svc.snapshot_restore_stream.assert_called_with("s", mode="append")

    def test_restore_stream_edge_cases(self):
        svc = _mock_service()
        h = build_handlers(svc)
        assert list(h["on_snapshot_restore_stream"](""))[0][0] == "_请先选中一个快照_"
        svc.snapshot_restore_stream.return_value = iter([StreamEvent("error", "快照不存在: s")])
        assert list(h["on_snapshot_restore_stream"]("s"))[-1][1].startswith("❌")
        svc.snapshot_restore_stream.return_value = iter([StreamEvent("cancelled", "已停止")])
        assert "已停止" in list(h["on_snapshot_restore_stream"]("s"))[-1][0]
        svc.snapshot_restore_stream.return_value = iter([])
        assert "未获得结果" in list(h["on_snapshot_restore_stream"]("s"))[-1][0]


class TestGraphViewHandlers:
    def test_view_renders_figure(self):
        svc = _mock_service()
        svc.graph_view_data.return_value = {
            "nodes": _NODES, "edges": _EDGES, "positions": {}, "total_nodes": 3, "total_edges": 2,
            "truncated": False,
        }
        svc.graph_summary.return_value = {"is_available": True, "statistics": {"total_nodes": 3}}
        svc.graph_entity_types.return_value = ["tool"]
        h = build_handlers(svc)
        fig, stats, cards = h["on_graph_view"]("2D", ["tool"], 0.2, 100, " Python ", 2, True)
        assert fig is not None and type(fig.data[0]).__name__ == "Scatter"
        assert "**3** / 3 节点" in stats and "`Python`（2 跳）" in stats and "cb-cards" in cards
        kwargs = svc.graph_view_data.call_args.kwargs
        assert kwargs == {"types": ["tool"], "min_confidence": 0.2, "max_nodes": 100, "focus": "Python",
                          "hops": 2, "dim": 2}
        fig, _, _ = h["on_graph_view"]("3D", [], 0, 500, "", 1, False)
        assert type(fig.data[0]).__name__ == "Scatter3d"
        assert svc.graph_view_data.call_args.kwargs["types"] is None
        assert h["on_graph_type_choices"]() == ["tool"]

    def test_view_errors(self):
        svc = _mock_service()
        svc.graph_view_data.return_value = {"nodes": [], "edges": [], "total_nodes": 0}
        svc.graph_summary.return_value = {}
        h = build_handlers(svc)
        with patch.object(web_app, "build_graph_figure", side_effect=ImportError("no plotly")):
            fig, stats, _ = h["on_graph_view"]()
            assert fig is None and "plotly" in stats
        with patch.object(web_app, "build_graph_figure", side_effect=RuntimeError("bad")):
            fig, stats, _ = h["on_graph_view"]()
            assert fig is None and stats.startswith("❌ 渲染失败")
