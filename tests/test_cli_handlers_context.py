#!/usr/bin/env python3
"""test_cli_handlers_context.py — CLI 连续对话接线：

- ``/context`` / ``/compact`` / ``/session-compress``（别名）/ ``/session-new --carry``；
- ``/ask`` 与自然语言输入共用带会话上下文的 ``_run_ask``（改写提示、落库、健康度提示）；
- ``/reset`` 清空当前会话上下文；``/agent`` 不再重复落库；
- ``rag_pipeline.answer_question(context=...)`` 的改写/历史注入与 ``record_conversation`` 委托。
"""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import cli_handlers
import conversation_context as cc
import query_interface as qi
import rag_pipeline
from conversation_context import ConversationContext
from query_interface import ParsedCommand, parse_command, classify_mode
from session_manager import SessionManager


@pytest.fixture
def conv(tmp_path, monkeypatch):
    """把进程内单例上下文重定向到临时目录的真实 SessionManager。"""
    manager = SessionManager(str(tmp_path / "sessions"))
    ctx = ConversationContext(manager, num_ctx=4000, ratio=0.3, complete=lambda p: "LLM摘要")
    monkeypatch.setattr(cc, "_context_singleton", ctx)
    monkeypatch.setattr(cc, "get_conversation_context", lambda: ctx)
    return ctx


def _printed(mock_console):
    return "\n".join(str(c.args[0]) for c in mock_console.print.call_args_list if c.args)


def _cli_ctx(**kw):
    console = MagicMock()
    ns = SimpleNamespace(
        console=console, has_rich=False, rag_engine=kw.pop("rag_engine", None),
        react_engine=kw.pop("react_engine", None), last_rag_sources=[], last_web_sources=[],
        record_command=MagicMock(), record_conversation=MagicMock(),
    )
    for k, v in kw.items():
        setattr(ns, k, v)
    return ns


# ==================== 解析 / 分类 ====================

class TestParse:
    def test_new_commands_parsed(self):
        assert parse_command("/context").cmd_type == "context"
        assert parse_command("/compact").cmd_type == "compact"
        p = parse_command("/session-new --carry 新标题")
        assert p.cmd_type == "session_new" and p.arg == "--carry 新标题"

    def test_new_commands_are_pure_cmds(self):
        for ct in ("context", "compact"):
            assert classify_mode(True, ParsedCommand(ct, "")) == "cmd"

    def test_dispatch_table_has_new_handlers(self):
        assert cli_handlers.COMMAND_HANDLERS["context"] is cli_handlers.handle_context
        assert cli_handlers.COMMAND_HANDLERS["compact"] is cli_handlers.handle_compact
        assert cli_handlers.COMMAND_HANDLERS["session_compress"] is cli_handlers.handle_session_compress

    def test_parse_session_new_args(self):
        assert cli_handlers._parse_session_new_args("") == (None, False)
        assert cli_handlers._parse_session_new_args("--carry") == (None, True)
        assert cli_handlers._parse_session_new_args("我的 会话 -c") == ("我的 会话", True)
        assert cli_handlers._parse_session_new_args("标题") == ("标题", False)

    def test_help_mentions_context_commands(self):
        with patch("query_interface.console") as console, patch.object(qi, "HAS_RICH", False), \
                patch("builtins.print") as mock_print:
            qi.print_help()
        text = "\n".join(str(c.args[0]) for c in mock_print.call_args_list)
        assert "/context" in text and "/compact" in text and "--carry" in text


# ==================== /context /compact ====================

class TestContextCommands:
    def test_context_without_session(self, conv):
        ctx = _cli_ctx()
        assert cli_handlers.handle_context(ctx, ParsedCommand("context", "/context")) is True
        assert "没有会话" in _printed(ctx.console)

    def test_context_shows_metrics_and_summary(self, conv):
        conv.record("DJI OSMO 360 是什么", "全景相机")
        conv.session().metadata["context"]["summary"] = "早前摘要"
        ctx = _cli_ctx()
        cli_handlers.handle_context(ctx, ParsedCommand("context", "/context"))
        out = _printed(ctx.console)
        assert "轮数: 1" in out and "预算" in out and "压缩次数: 0" in out
        assert "早前摘要" in out
        ctx.record_command.assert_called_with("context")

    def test_context_no_summary(self, conv):
        conv.record("q", "a")
        ctx = _cli_ctx()
        cli_handlers.handle_context(ctx, ParsedCommand("context", "/context"))
        assert "（无）" in _printed(ctx.console)

    def test_context_error(self, conv, monkeypatch):
        monkeypatch.setattr(conv, "metrics", lambda: (_ for _ in ()).throw(RuntimeError("boom")))
        ctx = _cli_ctx()
        cli_handlers.handle_context(ctx, ParsedCommand("context", "/context"))
        assert "失败" in _printed(ctx.console)

    def test_compact_no_history(self, conv):
        ctx = _cli_ctx()
        cli_handlers.handle_compact(ctx, ParsedCommand("compact", "/compact"))
        assert "没有可压缩" in _printed(ctx.console)

    def test_compact_short_history(self, conv):
        conv.record("q", "a")
        ctx = _cli_ctx()
        cli_handlers.handle_compact(ctx, ParsedCommand("compact", "/compact"))
        assert "无需压缩" in _printed(ctx.console)

    def test_compact_folds(self, conv):
        for i in range(5):
            conv.record(f"q{i}", f"a{i}")
        ctx = _cli_ctx()
        cli_handlers.handle_compact(ctx, ParsedCommand("compact", "/compact"))
        out = _printed(ctx.console)
        assert "折叠 4 条" in out and "LLM摘要" in out
        ctx.record_command.assert_called_with("compact")

    def test_compact_error(self, conv, monkeypatch):
        monkeypatch.setattr(conv, "has_history", lambda: (_ for _ in ()).throw(RuntimeError("x")))
        ctx = _cli_ctx()
        cli_handlers.handle_compact(ctx, ParsedCommand("compact", "/compact"))
        assert "压缩失败" in _printed(ctx.console)

    def test_session_compress_is_alias(self, conv):
        for i in range(5):
            conv.record(f"q{i}", f"a{i}")
        ctx = _cli_ctx()
        cli_handlers.handle_session_compress(ctx, ParsedCommand("session_compress", "/session-compress"))
        assert "折叠 4 条" in _printed(ctx.console)


# ==================== /session-new --carry ====================

class TestSessionNewCarry:
    def test_plain_new_session(self, conv, monkeypatch):
        monkeypatch.setattr(cli_handlers, "_get_session_manager", lambda: conv.manager)
        ctx = _cli_ctx()
        cli_handlers.handle_session_new(ctx, ParsedCommand("session_new", "/session-new 标题", "标题"))
        out = _printed(ctx.console)
        assert "新会话已创建" in out and "标题" in out and "携带" not in out

    def test_carry_summary(self, conv, monkeypatch):
        monkeypatch.setattr(cli_handlers, "_get_session_manager", lambda: conv.manager)
        conv.record("DJI OSMO 360 是什么", "全景相机")
        ctx = _cli_ctx()
        cli_handlers.handle_session_new(ctx, ParsedCommand("session_new", "/session-new --carry", "--carry"))
        out = _printed(ctx.console)
        assert "已携带上一会话的摘要" in out
        assert "承接自上一会话" in conv.metrics()["summary"]
        assert conv.all_messages() == []

    def test_carry_failure(self, conv, monkeypatch):
        monkeypatch.setattr(conv, "new_session", lambda **k: (_ for _ in ()).throw(RuntimeError("x")))
        ctx = _cli_ctx()
        cli_handlers.handle_session_new(ctx, ParsedCommand("session_new", "/session-new --carry", "--carry"))
        assert "创建会话失败" in _printed(ctx.console)


# ==================== /reset ====================

class TestReset:
    @patch("query_interface.record_command_execution")
    @patch("query_interface.console")
    def test_reset_clears_session_via_engine(self, mock_console, _rec, conv):
        conv.record("q", "a")
        engine = MagicMock()
        engine.clear_history.return_value = True
        ctx = _cli_ctx(react_engine=engine)
        assert qi.handle_reset(ctx, ParsedCommand("reset", "/reset")) is True
        engine.clear_history.assert_called_once()
        assert "已清空" in _printed(mock_console)

    @patch("query_interface.record_command_execution")
    @patch("query_interface.console")
    def test_reset_without_engine_uses_context(self, mock_console, _rec, conv):
        conv.record("q", "a")
        with patch.object(qi, "react_engine", None):
            qi.handle_reset(_cli_ctx(), ParsedCommand("reset", "/reset"))
        assert conv.all_messages() == []
        assert "已清空" in _printed(mock_console)

    @patch("query_interface.record_command_execution")
    @patch("query_interface.console")
    def test_reset_nothing_to_clear(self, mock_console, _rec, conv):
        engine = MagicMock()
        engine.clear_history.return_value = False
        qi.handle_reset(_cli_ctx(react_engine=engine), ParsedCommand("reset", "/reset"))
        assert "没有可清空" in _printed(mock_console)


# ==================== /ask 与自然语言输入 ====================

def _answer(**kw):
    base = {"kind": "answer", "answer": "回答", "kb_sources": [], "web_sources": [],
            "meta": None, "rewritten": None}
    base.update(kw)
    return base


class TestRunAsk:
    @patch("query_interface.record_command_execution")
    @patch("query_interface.console")
    def test_ask_passes_context_and_records(self, mock_console, _rec, conv):
        captured = {}

        def fake_answer(engine, question, **kwargs):
            captured.update(kwargs)
            captured["question"] = question
            return _answer(answer="2999 元", rewritten="DJI OSMO 360 多少钱")

        rag = MagicMock(query_engine=object())
        with patch.object(rag_pipeline, "answer_question", fake_answer), \
                patch.object(qi, "rag_engine", rag), patch.object(qi, "HAS_RICH", False), \
                patch("builtins.print"):
            ctx = _cli_ctx(rag_engine=rag)
            assert qi.handle_ask(ctx, ParsedCommand("ask", "/ask 它多少钱", "它多少钱")) is True
        assert captured["context"] is conv
        assert captured["question"] == "它多少钱"
        out = _printed(mock_console)
        assert "已理解为：DJI OSMO 360 多少钱" in out
        msgs = conv.all_messages()
        assert [m["content"] for m in msgs] == ["它多少钱", "2999 元"]
        assert conv.session().messages[0]["rewritten"] == "DJI OSMO 360 多少钱"

    @patch("query_interface.record_command_execution")
    @patch("query_interface.console")
    def test_natural_input_uses_same_path_and_records(self, mock_console, _rec, conv):
        rag = MagicMock(query_engine=None)
        with patch.object(rag_pipeline, "answer_question", lambda *a, **k: _answer()), \
                patch.object(qi, "rag_engine", rag), patch.object(qi, "HAS_RICH", False), \
                patch("builtins.print"):
            ctx = _cli_ctx(rag_engine=rag)
            assert qi.handle_natural(ctx, ParsedCommand("natural", "你好啊", "你好啊")) is True
        assert "知识库未初始化" in _printed(mock_console)
        assert [m["content"] for m in conv.all_messages()] == ["你好啊", "回答"]
        _rec.assert_called_with("natural", "你好啊")

    @patch("query_interface.record_command_execution")
    @patch("query_interface.console")
    def test_meta_query_recorded(self, mock_console, _rec, conv):
        rag = MagicMock(query_engine=object())
        with patch.object(rag_pipeline, "answer_question",
                          lambda *a, **k: _answer(kind="meta", answer="[知识库概览]", meta={})), \
                patch.object(qi, "rag_engine", rag):
            qi.handle_ask(_cli_ctx(rag_engine=rag), ParsedCommand("ask", "/ask 知识库里有什么", "知识库里有什么"))
        assert conv.all_messages()[-1]["content"] == "[知识库概览]"

    @patch("query_interface.record_command_execution")
    @patch("query_interface.console")
    def test_health_hint_printed_once(self, mock_console, _rec, conv):
        # 预置 2 次压缩 → 触发建议
        conv.record("q", "a")
        conv.session().metadata["context"]["compressions"] = 2
        conv.manager.save_session(conv.session())
        rag = MagicMock(query_engine=object())
        with patch.object(rag_pipeline, "answer_question", lambda *a, **k: _answer()), \
                patch.object(qi, "rag_engine", rag), patch.object(qi, "HAS_RICH", False), \
                patch("builtins.print"):
            qi.handle_ask(_cli_ctx(rag_engine=rag), ParsedCommand("ask", "/ask x", "新的问题一"))
            first = _printed(mock_console)
            mock_console.reset_mock()
            qi.handle_ask(_cli_ctx(rag_engine=rag), ParsedCommand("ask", "/ask x", "新的问题二"))
            second = _printed(mock_console)
        assert "建议新建会话" in first and "/session-new" in first
        assert "建议新建会话" not in second

    @patch("query_interface.record_command_execution")
    @patch("query_interface.console")
    def test_context_unavailable_degrades(self, mock_console, _rec, monkeypatch):
        def boom():
            raise RuntimeError("no ctx")
        monkeypatch.setattr(cc, "get_conversation_context", boom)
        captured = {}

        def fake_answer(engine, question, **kwargs):
            captured.update(kwargs)
            return _answer()

        rag = MagicMock(query_engine=object())
        with patch.object(rag_pipeline, "answer_question", fake_answer), \
                patch.object(qi, "rag_engine", rag), patch.object(qi, "HAS_RICH", False), \
                patch("builtins.print"):
            assert qi.handle_ask(_cli_ctx(rag_engine=rag), ParsedCommand("ask", "/ask q", "q")) is True
        assert captured["context"] is None

    @patch("query_interface.record_command_execution")
    @patch("query_interface.console")
    def test_agent_does_not_double_record(self, mock_console, _rec, conv):
        engine = MagicMock()
        engine.chat.return_value = "完成"
        engine.step_log = [{"phase": "final"}]
        with patch.object(qi, "react_engine", engine), patch.object(qi, "HAS_RICH", False), \
                patch("builtins.print"):
            assert qi.handle_agent(_cli_ctx(react_engine=engine), ParsedCommand("agent", "/agent 做事", "做事")) is True
        # 引擎（此处为 Mock）负责落库；handler 不再额外写入
        assert conv.all_messages() == []
        _rec.assert_called_with("agent", "做事")

    def test_health_hint_swallows_errors(self, monkeypatch):
        monkeypatch.setattr(cc, "get_conversation_context", lambda: (_ for _ in ()).throw(RuntimeError("x")))
        qi._print_health_hint({}, "q")  # 不抛
        assert qi._health_before("q") == {}


# ==================== rag_pipeline 上下文接线 ====================

class FakeRAG:
    def __init__(self):
        self.query_engine = object()
        self.seen = []

    def query_with_sources(self, question, progress_callback=None):
        self.seen.append(question)
        return {"answer": f"答:{question}", "sources": [{"content": "c", "file": "f.md", "score": 0.9}]}


class TestPipelineContext:
    def test_no_context_keeps_behaviour(self):
        result = rag_pipeline.answer_question(FakeRAG(), "问题", enable_web_search=False)
        assert result["rewritten"] is None

    def test_followup_rewritten_and_history_injected(self, conv, monkeypatch):
        conv.record("DJI OSMO 360 是什么", "全景相机")
        conv._complete = lambda p: "DJI OSMO 360 多少钱"
        rag = FakeRAG()
        # 让综合路径被触发（网络补充存在），以检查 history 注入
        monkeypatch.setattr(rag_pipeline, "augment_with_web_search", lambda q, **k: "1. 标题\n   URL: http://x\n   摘要: 2999")
        prompts = []
        monkeypatch.setattr(rag_pipeline, "llm_direct_answer", lambda p: prompts.append(p) or "综合回答")
        events = []
        result = rag_pipeline.answer_question(
            rag, "它多少钱", enable_web_search=True, context=conv,
            progress=lambda e: events.append(e),
        )
        assert result["rewritten"] == "DJI OSMO 360 多少钱"
        assert rag.seen == ["DJI OSMO 360 多少钱"]
        assert any(e["stage"] == "context_rewritten" for e in events)
        assert "对话上下文" in prompts[0] and "DJI OSMO 360 是什么" in prompts[0]
        assert "## 问题\nDJI OSMO 360 多少钱" in prompts[0]

    def test_context_failure_ignored(self, monkeypatch):
        bad = MagicMock()
        bad.rewrite_question.side_effect = RuntimeError("x")
        result = rag_pipeline.answer_question(FakeRAG(), "它多少钱", enable_web_search=False, context=bad)
        assert result["rewritten"] is None and result["answer"] == "答:它多少钱"

    def test_meta_query_skips_context(self, conv, monkeypatch):
        import sys
        fake_mod = MagicMock()
        fake_mod.get_global_metadata_manager.return_value.list_files.return_value = []
        monkeypatch.setitem(sys.modules, "file_metadata", fake_mod)
        conv.record("q", "a")
        conv._complete = lambda p: (_ for _ in ()).throw(AssertionError("不应调用"))
        result = rag_pipeline.answer_question(FakeRAG(), "知识库里有什么", enable_web_search=False, context=conv)
        assert result["kind"] == "meta" and result["rewritten"] is None

    def test_synthesize_prompt_history_section(self):
        p = rag_pipeline.synthesize_prompt("q", "kb", "web", history="用户: 早前问题")
        assert "对话上下文" in p and "用户: 早前问题" in p
        assert p.index("对话上下文") < p.index("## 问题")
        assert "对话上下文" not in rag_pipeline.synthesize_prompt("q", "kb", "web")

    def test_record_conversation_delegates(self, conv):
        rag_pipeline.record_conversation("u", "a", trace="共 1 步")
        assert conv.session().messages[-1]["trace"] == "共 1 步"
        other = MagicMock()
        rag_pipeline.record_conversation("u2", "a2", context=other, rewritten="r")
        other.record.assert_called_once_with("u2", "a2", trace=None, rewritten="r", progress=None)

    def test_record_conversation_swallows_errors(self, monkeypatch):
        monkeypatch.setattr(cc, "get_conversation_context", lambda: (_ for _ in ()).throw(RuntimeError("x")))
        rag_pipeline.record_conversation("u", "a")  # 不抛
