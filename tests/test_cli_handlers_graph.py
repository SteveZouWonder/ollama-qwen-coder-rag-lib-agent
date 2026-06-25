#!/usr/bin/env python3
"""
test_cli_handlers_graph.py — /graph-build 命令处理器测试

回归背景：knowledge_graph_build 工具已注册且对 Agent 可见，但 /graph-build
此前是死胡同（只提示去用 Agent）。现已让其直接可用：支持内联文本与 @文件。
"""
from unittest.mock import MagicMock

import cli_handlers as h
from query_interface import ParsedCommand


def _make_ctx(tool_result="知识图谱构建成功\n节点数: 5\n边数: 3"):
    reg = MagicMock()
    reg.execute.return_value = tool_result
    ctx = h.CLIContext(
        console=MagicMock(),
        has_rich=False,
        registry=reg,
        record_command=MagicMock(),
    )
    return ctx, reg


def _parsed(arg):
    return ParsedCommand("graph_build", f"/graph-build {arg}", arg)


class TestGraphBuild:
    def test_no_arg_shows_usage_and_skips_tool(self):
        ctx, reg = _make_ctx()
        result = h.handle_graph_build(ctx, _parsed(""))
        assert result is False
        reg.execute.assert_not_called()

    def test_inline_text_builds_graph(self):
        ctx, reg = _make_ctx()
        result = h.handle_graph_build(ctx, _parsed("张三在北京工作"))
        assert result is True
        reg.execute.assert_called_once()
        name, params = reg.execute.call_args.args
        assert name == "knowledge_graph_build"
        assert params["text"] == "张三在北京工作"
        assert params["doc_type"] == "text"
        assert params["doc_id"] == "manual"

    def test_file_text_uses_filename_and_text_type(self, tmp_path):
        ctx, reg = _make_ctx()
        f = tmp_path / "note.md"
        f.write_text("北京是中国的首都。", encoding="utf-8")
        result = h.handle_graph_build(ctx, _parsed(f"@{f}"))
        assert result is True
        _, params = reg.execute.call_args.args
        assert params["doc_type"] == "text"
        assert params["doc_id"] == "note.md"
        assert "北京" in params["text"]

    def test_file_code_uses_code_type(self, tmp_path):
        ctx, reg = _make_ctx(tool_result="知识图谱构建成功\n节点数: 2\n边数: 1")
        f = tmp_path / "mod.py"
        f.write_text("def foo():\n    return bar()\n", encoding="utf-8")
        result = h.handle_graph_build(ctx, _parsed(f"@{f}"))
        assert result is True
        _, params = reg.execute.call_args.args
        assert params["doc_type"] == "code"

    def test_missing_file_returns_false_without_tool(self):
        ctx, reg = _make_ctx()
        result = h.handle_graph_build(ctx, _parsed("@/definitely/not/exist.txt"))
        assert result is False
        reg.execute.assert_not_called()

    def test_empty_file_returns_false_without_tool(self, tmp_path):
        ctx, reg = _make_ctx()
        f = tmp_path / "empty.txt"
        f.write_text("   \n", encoding="utf-8")
        result = h.handle_graph_build(ctx, _parsed(f"@{f}"))
        assert result is False
        reg.execute.assert_not_called()

    def test_tool_error_is_surfaced(self):
        ctx, reg = _make_ctx(tool_result="[错误] 知识图谱模块未安装")
        result = h.handle_graph_build(ctx, _parsed("一些文本"))
        assert result is False
