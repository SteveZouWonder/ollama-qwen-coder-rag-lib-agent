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


class TestHandleAddGraphPrompt:
    """/add 派生构建图谱后的提示文案（不再推荐手动 /graph-build）。"""

    def _ctx(self, last_graph_derived, docs=None):
        rag = MagicMock()
        rag.last_graph_derived = last_graph_derived
        console = MagicMock()
        ctx = h.CLIContext(
            console=console,
            has_rich=False,
            rag_engine=rag,
            load_documents=MagicMock(return_value=docs if docs is not None else [MagicMock()]),
            record_command=MagicMock(),
        )
        return ctx, console, rag

    def _parsed_add(self, path="doc.md"):
        return ParsedCommand("add", f"/add {path}", path)

    def _printed(self, console):
        return " ".join(str(c.args[0]) for c in console.print.call_args_list if c.args)

    def test_success_with_graph_derived_shows_synced_message(self):
        ctx, console, rag = self._ctx(last_graph_derived=True)
        assert h.handle_add(ctx, self._parsed_add()) is True
        rag.add_documents.assert_called_once()
        out = self._printed(console)
        assert "已同步更新知识图谱" in out
        # 不应再推荐手动 /graph-build
        assert "/graph-build" not in out

    def test_success_without_graph_derived_suggests_manual(self):
        ctx, console, rag = self._ctx(last_graph_derived=False)
        assert h.handle_add(ctx, self._parsed_add()) is True
        out = self._printed(console)
        assert "/graph-build" in out
        assert "手动补建" in out

    def test_no_documents_skips_add_and_graph_message(self):
        ctx, console, rag = self._ctx(last_graph_derived=True, docs=[])
        assert h.handle_add(ctx, self._parsed_add()) is True
        rag.add_documents.assert_not_called()
        out = self._printed(console)
        assert "未找到可加载的文档" in out
        assert "知识图谱" not in out


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


_OVERVIEW = {
    "is_repo": True, "branch": "main", "last_commit_at": "2026-09-08 10:00:00 +0800",
    "changed": [{"status": "M", "label": "修改", "path": "a.py"}],
    "commits": [{"hash7": "abc1234", "author": "T", "date": "2026-09-08", "subject": "feat: x"}],
    "authors": [{"name": "T", "commits": 1}],
}


class TestGitAnalyze:
    """/git-analyze（F9 P3-5：共享层 ``get_overview`` + rich 表格）与 /git-commit-gen handler 测试。

    详细的表头 / 行数 / 空态断言见 ``test_cli_handlers_rich_tables.py``；这里只覆盖分发与容错。
    """

    def _ctx(self, overview=None, has_rich=False):
        ctx = h.CLIContext(console=MagicMock(), has_rich=has_rich, registry=MagicMock(), record_command=MagicMock())
        return ctx

    def _pq(self, arg):
        return ParsedCommand("git_analyze", f"/git-analyze {arg}", arg)

    def _patch(self, monkeypatch, overview=_OVERVIEW):
        calls = []

        def fake(repo_path=".", max_commits=10):
            calls.append((repo_path, max_commits))
            return dict(overview)

        monkeypatch.setattr(h, "_git_overview", fake)
        return calls

    def test_no_arg_defaults_to_history(self, monkeypatch):
        calls = self._patch(monkeypatch)
        ctx = self._ctx()
        assert h.handle_git_analyze(ctx, self._pq("")) is True
        assert calls == [(".", 10)]
        ctx.record_command.assert_called_once_with("git_analyze", "history")
        ctx.registry.execute.assert_not_called()  # 不再经 registry

    def test_status_type(self, monkeypatch):
        self._patch(monkeypatch)
        ctx = self._ctx()
        h.handle_git_analyze(ctx, self._pq("status"))
        ctx.record_command.assert_called_once_with("git_analyze", "status")
        printed = "\n".join(str(c.args[0]) for c in ctx.console.print.call_args_list)
        assert "修改 a.py" in printed

    def test_author_alias_maps_to_authors(self, monkeypatch):
        self._patch(monkeypatch)
        ctx = self._ctx()
        h.handle_git_analyze(ctx, self._pq("author"))
        ctx.record_command.assert_called_once_with("git_analyze", "authors")

    def test_unknown_type_returns_false_without_tool(self, monkeypatch):
        calls = self._patch(monkeypatch)
        ctx = self._ctx()
        assert h.handle_git_analyze(ctx, self._pq("bogus")) is False
        assert calls == []

    def test_non_repo_hint(self, monkeypatch):
        self._patch(monkeypatch, {"is_repo": False, "branch": "", "changed": [], "commits": [], "authors": [],
                                  "last_commit_at": ""})
        ctx = self._ctx()
        assert h.handle_git_analyze(ctx, self._pq("history")) is True
        assert ctx.console.print.call_args.kwargs.get("style") == "dim"

    def test_exception_recorded(self, monkeypatch):
        def boom(repo_path=".", max_commits=10):
            raise RuntimeError("git-boom")

        monkeypatch.setattr(h, "_git_overview", boom)
        ctx = self._ctx()
        assert h.handle_git_analyze(ctx, self._pq("history")) is True
        assert ctx.record_command.call_args.args[2] == "failed"
        assert ctx.console.print.call_args.kwargs.get("style") == "red"

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


class TestWebCacheClearConfirm:
    """/web-cache clear 需交互确认，不再泄露 [CONFIRM_REQUIRED] 协议串"""

    def _ctx(self, result="[成功] 搜索缓存已清空", input_value="y"):
        reg = MagicMock()
        reg.execute.return_value = result
        console = MagicMock()
        console.input.return_value = input_value
        ctx = h.CLIContext(console=console, has_rich=False,
                           registry=reg, record_command=MagicMock())
        return ctx, reg, console

    def _pq(self, arg="clear"):
        return ParsedCommand("web_cache", f"/web-cache {arg}", arg)

    def test_confirm_yes_executes_with_auto_confirm(self):
        ctx, reg, console = self._ctx(input_value="y")
        assert h.handle_web_cache(ctx, self._pq("clear")) is True
        # 以 auto_confirm=True 调用，避免返回协议串
        assert reg.execute.call_args.kwargs.get("auto_confirm") is True
        # 输出中不得包含内部协议串
        outs = [c.args[0] for c in console.print.call_args_list if c.args]
        assert all("CONFIRM_REQUIRED" not in str(o) for o in outs)

    def test_reject_no_cancels_without_execute(self):
        ctx, reg, console = self._ctx(input_value="n")
        assert h.handle_web_cache(ctx, self._pq("clear")) is False
        reg.execute.assert_not_called()

    def test_eof_cancels(self):
        ctx, reg, console = self._ctx()
        console.input.side_effect = EOFError()
        assert h.handle_web_cache(ctx, self._pq("clear")) is False
        reg.execute.assert_not_called()

    def test_auto_confirm_config_skips_prompt(self):
        from config import Config
        old = getattr(Config, "AUTO_CONFIRM", False)
        Config.AUTO_CONFIRM = True
        try:
            ctx, reg, console = self._ctx()
            assert h.handle_web_cache(ctx, self._pq("clear")) is True
            console.input.assert_not_called()
            assert reg.execute.called
        finally:
            Config.AUTO_CONFIRM = old

    def test_status_does_not_require_confirm(self):
        ctx, reg, console = self._ctx(result="缓存状态: 空")
        assert h.handle_web_cache(ctx, self._pq("status")) is True
        console.input.assert_not_called()
        assert reg.execute.called

    def test_clear_tool_error_surfaced(self):
        ctx, reg, console = self._ctx(result="[错误] 清空失败", input_value="y")
        assert h.handle_web_cache(ctx, self._pq("clear")) is False
