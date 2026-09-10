"""CLI ``/multi`` 多 Agent 协作命令（P0-8）。"""
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import cli_handlers
from cli_handlers import COMMAND_HANDLERS, handle_multi, parse_multi_args
from query_interface import ParsedCommand, parse_command, classify_mode, print_help, TUTORIAL_TEXT


def _printed(console):
    return "\n".join(str(c.args[0]) for c in console.print.call_args_list if c.args)


def _ctx(factory=None, rag_engine=None, has_rich=False):
    return SimpleNamespace(
        console=MagicMock(), has_rich=has_rich, rag_engine=rag_engine, react_engine=None,
        record_command=MagicMock(), record_conversation=MagicMock(),
        orchestrator_factory=factory,
    )


class _Orch:
    def __init__(self, result=None, raise_exc=None):
        self.result = result if result is not None else {
            "success": True, "summary": "执行了 2 个任务，成功 2 个。", "answer": "综合回答",
            "results": [{"agent_id": "code_agent_1", "success": True, "output": "x", "metadata": {}}],
        }
        self.raise_exc = raise_exc
        self.calls = []
        self.shutdown_called = 0

    def process_request(self, request, mode, progress=None, context=None, on_token=None):
        self.calls.append({"request": request, "mode": mode, "context": context})
        if progress:
            progress({"stage": "decompose", "message": "🧩 分解任务（模型推理）..."})
            progress({"stage": "agent_step", "message": "[code_agent_1] Step 1", "transient": True})
            progress({"stage": "agent_step", "message": "[code_agent_1] Step 1: read_file 执行完成"})
        if self.raise_exc:
            raise self.raise_exc
        return self.result

    def shutdown(self):
        self.shutdown_called += 1


class TestParse:
    def test_parse_command_multi(self):
        p = parse_command("/multi 写快排 --mode parallel")
        assert p.cmd_type == "multi" and p.arg == "写快排 --mode parallel"
        assert parse_command("/multi").cmd_type == "unknown_cmd" or parse_command("/multi").cmd_type == "multi"

    def test_classify_mode_is_cmd(self):
        assert classify_mode(True, ParsedCommand("multi", "/multi x", "x")) == "cmd"
        assert classify_mode(False, ParsedCommand("multi", "/multi x", "x")) == "cmd"

    def test_registered_in_handlers(self):
        assert COMMAND_HANDLERS["multi"] is handle_multi

    @pytest.mark.parametrize("arg,task,mode", [
        ("写快排 --mode parallel", "写快排", "parallel"),
        ("--mode=competitive 审计 a.py", "审计 a.py", "competitive"),
        ("写快排并测试", "写快排并测试", None),
        ("写 --mode Sequential 测试", "写 测试", "sequential"),
        ("", "", None),
    ])
    def test_parse_multi_args(self, arg, task, mode):
        assert parse_multi_args(arg) == (task, mode)

    def test_help_and_tutorial_mention_multi(self):
        import inspect
        from cli.help_text import print_help as help_impl  # F10 P2-2：/help 文案随实现迁至 cli.help_text
        assert "/multi <task>" in inspect.getsource(help_impl)
        assert "/multi" in TUTORIAL_TEXT


class TestHandleMulti:
    def test_runs_and_renders(self):
        orch = _Orch()
        ctx = _ctx(factory=lambda: orch)
        ok = handle_multi(ctx, ParsedCommand("multi", "", "写快排并测试 --mode parallel"))
        assert ok is True
        call = orch.calls[0]
        assert call["request"] == "写快排并测试"
        assert call["mode"].value == "parallel"
        assert call["context"] is not None
        out = _printed(ctx.console)
        assert "多 Agent 协作（模式: parallel）" in out
        assert "分解任务（模型推理）" in out
        assert "read_file 执行完成" in out
        assert "Step 1\n" not in out  # transient 心跳不打印
        assert "综合回答" in out and "code_agent_1" in out
        ctx.record_conversation.assert_called_once_with("写快排并测试", "综合回答")
        ctx.record_command.assert_called_once_with("multi", "写快排并测试", "success")
        assert orch.shutdown_called == 1

    def test_default_mode_none(self):
        orch = _Orch()
        ctx = _ctx(factory=lambda: orch)
        handle_multi(ctx, ParsedCommand("multi", "", "任务"))
        assert orch.calls[0]["mode"] is None
        assert "模式: 默认" in _printed(ctx.console)

    def test_unknown_mode_warns(self):
        orch = _Orch()
        ctx = _ctx(factory=lambda: orch)
        handle_multi(ctx, ParsedCommand("multi", "", "任务 --mode turbo"))
        assert orch.calls[0]["mode"] is None
        assert "未知模式 turbo" in _printed(ctx.console)

    def test_empty_task_usage(self):
        ctx = _ctx(factory=lambda: _Orch())
        assert handle_multi(ctx, ParsedCommand("multi", "", "  --mode parallel")) is False
        assert "用法" in _printed(ctx.console)

    def test_failure_recorded_with_marker(self):
        orch = _Orch(result={"success": False, "summary": "失败", "error": "e"})
        ctx = _ctx(factory=lambda: orch)
        handle_multi(ctx, ParsedCommand("multi", "", "任务"))
        ctx.record_conversation.assert_called_once_with("任务", "[协作失败] 失败")
        ctx.record_command.assert_called_once_with("multi", "任务", "failed")

    def test_exception_handled(self):
        orch = _Orch(raise_exc=RuntimeError("boom"))
        ctx = _ctx(factory=lambda: orch)
        assert handle_multi(ctx, ParsedCommand("multi", "", "任务")) is False
        assert "协作执行失败: boom" in _printed(ctx.console)
        assert orch.shutdown_called == 1

    def test_keyboard_interrupt(self):
        orch = _Orch(raise_exc=KeyboardInterrupt())
        ctx = _ctx(factory=lambda: orch)
        assert handle_multi(ctx, ParsedCommand("multi", "", "任务")) is False
        assert "用户中断" in _printed(ctx.console)

    def test_non_dict_result(self):
        orch = _Orch(result="plain")
        ctx = _ctx(factory=lambda: orch)
        handle_multi(ctx, ParsedCommand("multi", "", "任务"))
        ctx.record_conversation.assert_called_once_with("任务", "[协作失败] plain")

    def test_rag_engine_injected_and_rich_render(self, monkeypatch):
        import agent_tools
        injected = {}
        monkeypatch.setattr(agent_tools, "set_rag_engine", lambda e: injected.setdefault("e", e))
        engine = object()
        orch = _Orch()
        ctx = _ctx(factory=lambda: orch, rag_engine=engine, has_rich=True)
        handle_multi(ctx, ParsedCommand("multi", "", "任务"))
        assert injected["e"] is engine
        # rich 路径：Markdown 对象被打印
        printed_types = {type(c.args[0]).__name__ for c in ctx.console.print.call_args_list if c.args}
        assert "Markdown" in printed_types

    def test_record_conversation_error_swallowed(self):
        orch = _Orch()
        ctx = _ctx(factory=lambda: orch)
        ctx.record_conversation = MagicMock(side_effect=RuntimeError("x"))
        assert handle_multi(ctx, ParsedCommand("multi", "", "任务")) is True

    def test_default_factory_builds_orchestrator(self, monkeypatch):
        created = {}

        class FakeOrch:
            def __init__(self, cfg):
                created["cfg"] = cfg

        import agent_orchestrator
        monkeypatch.setattr(agent_orchestrator, "AgentOrchestrator", FakeOrch)
        orch = cli_handlers._default_orchestrator()
        assert isinstance(orch, FakeOrch) and created["cfg"] is not None

    def test_context_unavailable(self, monkeypatch):
        import conversation_context as cc

        def boom():
            raise RuntimeError("no ctx")
        monkeypatch.setattr(cc, "get_conversation_context", boom)
        orch = _Orch()
        ctx = _ctx(factory=lambda: orch)
        handle_multi(ctx, ParsedCommand("multi", "", "任务"))
        assert orch.calls[0]["context"] is None
