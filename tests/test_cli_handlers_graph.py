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


class TestGraphQueryRouting:
    """/graph-query 前缀解析与 query_type 路由"""

    def _ctx(self, result="找到 1 个实体和 0 个关系\n\n置信度: 0.80"):
        reg = MagicMock()
        reg.execute.return_value = result
        ctx = h.CLIContext(console=MagicMock(), has_rich=False,
                           registry=reg, record_command=MagicMock())
        return ctx, reg

    def _pq(self, arg):
        return ParsedCommand("graph_query", f"/graph-query {arg}", arg)

    def test_no_arg_shows_usage(self):
        ctx, reg = self._ctx()
        assert h.handle_graph_query(ctx, self._pq("")) is False
        reg.execute.assert_not_called()

    def test_default_is_entity_text_match(self):
        ctx, reg = self._ctx()
        h.handle_graph_query(ctx, self._pq("cloudflare"))
        name, params = reg.execute.call_args.args
        assert name == "knowledge_graph_query"
        assert params == {"query": "cloudflare", "query_type": "entity"}

    def test_type_prefix_routes_to_type(self):
        ctx, reg = self._ctx()
        h.handle_graph_query(ctx, self._pq("type:tool"))
        _, params = reg.execute.call_args.args
        assert params == {"query": "tool", "query_type": "type"}

    def test_neighbors_prefix(self):
        ctx, reg = self._ctx()
        h.handle_graph_query(ctx, self._pq("neighbors:DNS"))
        _, params = reg.execute.call_args.args
        assert params == {"query": "DNS", "query_type": "neighbors"}

    def test_path_prefix_keeps_arrow(self):
        ctx, reg = self._ctx()
        h.handle_graph_query(ctx, self._pq("path:A->B"))
        _, params = reg.execute.call_args.args
        assert params == {"query": "A->B", "query_type": "path"}

    def test_similar_prefix(self):
        ctx, reg = self._ctx()
        h.handle_graph_query(ctx, self._pq("similar:DNS"))
        _, params = reg.execute.call_args.args
        assert params == {"query": "DNS", "query_type": "similar"}

    def test_unknown_prefix_treated_as_entity_text(self):
        # 含冒号但非已知前缀（如 URL）应整体作为实体文本
        ctx, reg = self._ctx()
        h.handle_graph_query(ctx, self._pq("http://example.com"))
        _, params = reg.execute.call_args.args
        assert params == {"query": "http://example.com", "query_type": "entity"}


class TestGitAnalyze:
    """/git-analyze 与 /git-commit-gen handler 测试（修复静默无输出）"""

    def _ctx(self, result="OK"):
        reg = MagicMock()
        reg.execute.return_value = result
        ctx = h.CLIContext(console=MagicMock(), has_rich=False,
                           registry=reg, record_command=MagicMock())
        return ctx, reg

    def _pq(self, arg):
        return ParsedCommand("git_analyze", f"/git-analyze {arg}", arg)

    def test_no_arg_defaults_to_history(self):
        ctx, reg = self._ctx("最近 1 次提交")
        assert h.handle_git_analyze(ctx, self._pq("")) is True
        _, params = reg.execute.call_args.args
        assert params == {"repo_path": ".", "analysis_type": "history"}

    def test_status_type(self):
        ctx, reg = self._ctx("当前分支: main")
        h.handle_git_analyze(ctx, self._pq("status"))
        _, params = reg.execute.call_args.args
        assert params["analysis_type"] == "status"

    def test_author_alias_maps_to_authors(self):
        ctx, reg = self._ctx("作者统计:")
        h.handle_git_analyze(ctx, self._pq("author"))
        _, params = reg.execute.call_args.args
        assert params["analysis_type"] == "authors"

    def test_unknown_type_returns_false_without_tool(self):
        ctx, reg = self._ctx()
        assert h.handle_git_analyze(ctx, self._pq("bogus")) is False
        reg.execute.assert_not_called()

    def test_tool_error_surfaced(self):
        ctx, reg = self._ctx("[错误] Git 集成模块未安装")
        assert h.handle_git_analyze(ctx, self._pq("history")) is False

    def test_commit_gen_invokes_tool(self):
        reg = MagicMock()
        reg.execute.return_value = "建议的提交信息:\n标题: feat: x"
        ctx = h.CLIContext(console=MagicMock(), has_rich=False,
                           registry=reg, record_command=MagicMock())
        r = h.handle_git_commit_gen(
            ctx, ParsedCommand("git_commit_gen", "/git-commit-gen", "")
        )
        assert r is True
        name, params = reg.execute.call_args.args
        assert name == "git_commit_gen"
        assert params == {"repo_path": ".", "use_ai": True}

    def test_commands_registered_in_table(self):
        from cli_handlers import COMMAND_HANDLERS
        assert "git_analyze" in COMMAND_HANDLERS
        assert "git_commit_gen" in COMMAND_HANDLERS
