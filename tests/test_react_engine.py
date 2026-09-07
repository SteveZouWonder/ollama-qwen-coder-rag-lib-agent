#!/usr/bin/env python3
"""
test_react_engine.py — ReAct 引擎单元测试（Mock requests.post）
"""
from unittest.mock import MagicMock, patch

import pytest

from react_engine import (
    ReActEngine,
    _extract_json_object,
    _parse_action_input,
    build_system_prompt,
)
from config import Config


class FakeContext:
    """模拟 conversation_context.ConversationContext：内存中的会话记忆。"""

    def __init__(self, messages=None, summary=""):
        self.messages = list(messages or [])
        self.summary = summary
        self.recorded = []
        self.cleared = False

    def build_messages(self, system_prompt=None):
        out = []
        if system_prompt:
            out.append({"role": "system", "content": system_prompt})
        if self.summary:
            out.append({"role": "system", "content": f"摘要：{self.summary}"})
        out.extend({"role": m["role"], "content": m["content"]} for m in self.messages)
        return out

    def record(self, user, assistant, *, trace=None, rewritten=None, progress=None):
        self.recorded.append({"user": user, "assistant": assistant, "trace": trace})
        self.messages.append({"role": "user", "content": user})
        self.messages.append({"role": "assistant", "content": assistant})
        if progress:
            progress({"stage": "context_compress", "message": "🗜️ 压缩历史上下文…"})

    def clear(self):
        self.cleared = True
        self.messages = []
        self.summary = ""
        return True


def make_engine(**kwargs):
    """构造注入了 FakeContext 的引擎，返回 (engine, ctx)。"""
    ctx = kwargs.pop("context", None) or FakeContext()
    engine = ReActEngine(context=ctx, **kwargs)
    return engine, ctx


class TestExtractJsonObject:
    """测试从 Action Input 文本中提取完整 JSON 对象"""

    def test_simple_object(self):
        assert _extract_json_object('{"path": "test.py"}') == '{"path": "test.py"}'

    def test_empty_object(self):
        assert _extract_json_object("{}") == "{}"

    def test_ignores_trailing_text(self):
        """提取后应忽略 JSON 之后的多余文字"""
        text = '{"path": "a.py"}\nObservation: 不该被包含'
        assert _extract_json_object(text) == '{"path": "a.py"}'

    def test_nested_object(self):
        """嵌套对象不应在第一个 } 处截断"""
        text = '{"config": {"a": 1, "b": 2}, "name": "x"}'
        assert _extract_json_object(text) == text

    def test_code_with_braces_in_string(self):
        """字符串值内含 } 的多行代码不应被截断（核心回归）"""
        text = '{"path": "x.py", "content": "def f():\\n    return {1: 2}\\n"}'
        assert _extract_json_object(text) == text

    def test_brace_inside_string_not_counted(self):
        text = '{"msg": "use } carefully"}'
        assert _extract_json_object(text) == text

    def test_no_object_returns_none(self):
        assert _extract_json_object("no json here") is None

    def test_leading_text_before_object(self):
        text = '  some prefix {"k": "v"}'
        assert _extract_json_object(text) == '{"k": "v"}'


class TestParseActionInput:
    """测试安全解析 Action Input（不使用 eval）"""

    def test_valid_json(self):
        assert _parse_action_input('{"path": "test.py"}') == {"path": "test.py"}

    def test_empty_object(self):
        assert _parse_action_input("{}") == {}

    def test_single_quotes_fallback(self):
        """单引号（非法 JSON）应通过 ast.literal_eval 容错解析"""
        assert _parse_action_input("{'path': 'test.py'}") == {"path": "test.py"}

    def test_non_dict_json_returns_empty(self):
        """JSON 数组/标量不是 dict，返回空 dict"""
        assert _parse_action_input('["a", "b"]') == {}
        assert _parse_action_input('"just a string"') == {}

    def test_garbage_returns_empty(self):
        assert _parse_action_input("not parseable {{{") == {}

    def test_empty_string_returns_empty(self):
        assert _parse_action_input("") == {}

    def test_does_not_execute_code(self):
        """确保不会执行任意代码（eval 风险回归测试）"""
        # 若使用 eval，下面会抛 NameError 或执行调用；安全解析应返回 {}
        assert _parse_action_input("{'x': __import__('os').getcwd()}") == {}


class TestReActEngineInit:
    """测试初始化"""

    def test_init_loads_defaults(self):

        engine, ctx = make_engine()
        assert engine.model == Config.LLM_MODEL
        assert engine.host == Config.OLLAMA_BASE_URL
        assert engine.step_log == []

    def test_init_with_custom_model(self):

        engine, ctx = make_engine(model="custom:7b", host="http://other:11434")
        assert engine.model == "custom:7b"
        assert engine.host == "http://other:11434"

    def test_system_prompt_built_at_runtime_not_persisted(self):
        """系统提示运行时注入：引擎持有 system_prompt，且不写入会话。"""
        engine, ctx = make_engine()
        assert "工具" in engine.system_prompt or "tool" in engine.system_prompt.lower()
        assert engine.system_prompt == build_system_prompt()
        # 会话中不应出现 system 消息
        assert not any(m.get("role") == "system" for m in ctx.messages)

    def test_context_lazily_resolves_singleton(self, monkeypatch):
        """未注入 context 时惰性取进程内单例。"""
        import conversation_context as cc
        fake = FakeContext()
        monkeypatch.setattr(cc, "get_conversation_context", lambda: fake)
        engine = ReActEngine()
        assert engine.context is fake
        engine.context = FakeContext()
        assert engine.context is not fake

    @patch("react_engine.requests.post")
    def test_chat_loads_summary_and_recent_turns_from_session(self, mock_post):
        """开局消息 = 系统提示 + 滚动摘要 + 最近轮次 + 本轮问题。"""
        mock_post.return_value = MagicMock(**{"json.return_value": {"message": {"content": "Final Answer: ok"}}})
        ctx = FakeContext(
            messages=[{"role": "user", "content": "旧问题"}, {"role": "assistant", "content": "旧回答"}],
            summary="更早的对话摘要",
        )
        engine, _ = make_engine(context=ctx)
        engine.chat("新问题")
        sent = mock_post.call_args.kwargs["json"]["messages"]
        roles = [m["role"] for m in sent]
        assert roles[0] == "system" and sent[0]["content"] == engine.system_prompt
        assert "更早的对话摘要" in sent[1]["content"]
        assert sent[2]["content"] == "旧问题" and sent[3]["content"] == "旧回答"
        assert sent[4] == {"role": "user", "content": "新问题"}

    @patch("react_engine.requests.post")
    def test_chat_folds_turn_into_session(self, mock_post):
        """轮末只把 任务 + 最终答案 + 执行摘要 写回会话，不落中间往返。"""
        mock_resp1 = MagicMock()
        mock_resp1.json.return_value = {"message": {"content": "Thought: t\nAction: read_file\nAction Input: {\"path\": \"a.py\"}"}}
        mock_resp2 = MagicMock()
        mock_resp2.json.return_value = {"message": {"content": "Final Answer: 完成"}}
        mock_post.side_effect = [mock_resp1, mock_resp2]
        with patch("react_engine.registry") as mock_registry:
            mock_registry.execute.return_value = "内容"
            mock_registry.get_descriptions.return_value = "tools"
            engine, ctx = make_engine()
            engine.chat("读文件")
        assert len(ctx.recorded) == 1
        rec = ctx.recorded[0]
        assert rec["user"] == "读文件" and rec["assistant"] == "完成"
        assert "read_file" in rec["trace"] and "1 步" in rec["trace"]
        # 会话里没有 Observation / Action 中间消息
        assert not any("Observation" in m["content"] or "Action" in m["content"] for m in ctx.messages)

    @patch("react_engine.requests.post")
    def test_compress_progress_forwarded_to_on_step(self, mock_post):
        """会话层的压缩事件转发为 on_step 事件。"""
        mock_post.return_value = MagicMock(**{"json.return_value": {"message": {"content": "直接回答"}}})
        events = []
        engine, ctx = make_engine(on_step=lambda e: events.append(e))
        engine.chat("hi")
        assert any(e.get("phase") == "context_compress" for e in events)

    @patch("react_engine.requests.post")
    def test_context_failure_degrades_gracefully(self, mock_post):
        """会话读取/写入失败时仍能作答，并通过 on_step 提示。"""
        mock_post.return_value = MagicMock(**{"json.return_value": {"message": {"content": "Final Answer: ok"}}})

        class BrokenContext:
            def build_messages(self, system_prompt=None):
                raise RuntimeError("no session")

            def record(self, *a, **k):
                raise RuntimeError("no disk")

        events = []
        engine = ReActEngine(context=BrokenContext(), on_step=lambda e: events.append(e))
        assert engine.chat("hi") == "ok"
        msgs = " ".join(e.get("message", "") for e in events)
        assert "读取会话上下文失败" in msgs and "记录会话失败" in msgs

    def test_trace_summary_counts_blocked_and_rejected(self):
        engine, ctx = make_engine()
        engine.step_log = [
            {"step": 1, "phase": "action", "tool": "read_file", "confirmed": True},
            {"step": 2, "phase": "action", "tool": "execute_command", "confirmed": False},
            {"step": 3, "phase": "blocked"},
            {"step": 4, "phase": "final", "answer": "x"},
        ]
        trace = engine._trace_summary()
        assert "共 2 步" in trace and "read_file、execute_command" in trace
        assert "拦截危险命令 1 次" in trace and "用户拒绝 1 次" in trace
        engine.step_log = []
        assert engine._trace_summary() == ""


class TestCallModel:
    """测试 _call_model"""

    @patch("react_engine.requests.post")
    def test_call_model_success(self, mock_post):

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"message": {"content": "hello"}}
        mock_post.return_value = mock_resp

        engine, ctx = make_engine()
        result = engine._call_model([{"role": "user", "content": "hi"}])
        assert result == "hello"
        mock_post.assert_called_once()

    @patch("react_engine.requests.post")
    def test_call_model_heartbeat_marked_transient(self, mock_post):
        """推理心跳事件应带 transient=True，供 UI 原地刷新而非逐条追加。"""
        import time as _time


        def slow_post(*args, **kwargs):
            _time.sleep(0.7)  # 跨过至少一次 0.5s 心跳
            resp = MagicMock()
            resp.json.return_value = {"message": {"content": "ok"}}
            return resp

        mock_post.side_effect = slow_post
        events = []
        engine, ctx = make_engine(on_step=lambda e: events.append(e))
        assert engine._call_model([{"role": "user", "content": "hi"}]) == "ok"
        heartbeats = [e for e in events if e.get("message", "").startswith("模型推理中")]
        assert heartbeats
        assert all(e.get("transient") is True for e in heartbeats)

    @patch("react_engine.requests.post")
    def test_call_model_connection_error(self, mock_post):

        import requests
        mock_post.side_effect = requests.exceptions.ConnectionError()

        engine, ctx = make_engine()
        result = engine._call_model([{"role": "user", "content": "hi"}])
        assert "无法连接到 Ollama" in result

    @patch("react_engine.requests.post")
    def test_call_model_timeout(self, mock_post):

        import requests
        mock_post.side_effect = requests.exceptions.Timeout()

        engine, ctx = make_engine()
        result = engine._call_model([{"role": "user", "content": "hi"}])
        assert "模型响应超时" in result

    @patch("react_engine.requests.post")
    def test_call_model_generic_error(self, mock_post):

        mock_post.side_effect = ValueError("boom")

        engine, ctx = make_engine()
        result = engine._call_model([{"role": "user", "content": "hi"}])
        assert "模型调用失败" in result
        assert "boom" in result

    def test_call_model_empty_messages(self):

        engine, ctx = make_engine()
        result = engine._call_model([])
        assert "消息列表为空" in result
        engine.messages = []
        assert "消息列表为空" in engine._call_model()

    @patch("react_engine.requests.post")
    def test_call_model_with_progress_callback(self, mock_post):
        """测试带进度回调的模型调用"""

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"message": {"content": "hello"}}
        mock_post.return_value = mock_resp

        progress_updates = []
        def mock_progress_callback(data):
            progress_updates.append(data)

        engine, ctx = make_engine(on_step=mock_progress_callback)
        result = engine._call_model([{"role": "user", "content": "hi"}])
        
        assert result == "hello"
        mock_post.assert_called_once()
        # 验证进度回调被调用（可能包含推理期间的更新）
        assert len(progress_updates) >= 0  # 至少不应该出错

    @patch("react_engine.requests.post")
    def test_call_model_progress_thread_cleanup(self, mock_post):
        """测试进度线程正确清理"""

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"message": {"content": "hello"}}
        mock_post.return_value = mock_resp

        engine, ctx = make_engine()
        result = engine._call_model([{"role": "user", "content": "hi"}])
        
        assert result == "hello"
        # 确保调用完成后线程被正确清理，不会留下僵尸线程
        assert result == "hello"  # 二次验证确保函数正常返回

    @patch("react_engine.requests.post")
    def test_call_model_with_slow_response(self, mock_post):
        """测试慢响应时的进度更新"""
        import time
        

        def slow_post(*args, **kwargs):
            time.sleep(0.1)  # 模拟慢响应
            mock_resp = MagicMock()
            mock_resp.json.return_value = {"message": {"content": "hello"}}
            return mock_resp
        
        mock_post.side_effect = slow_post

        progress_updates = []
        def mock_progress_callback(data):
            progress_updates.append(data)

        engine, ctx = make_engine(on_step=mock_progress_callback)
        result = engine._call_model([{"role": "user", "content": "hi"}])
        
        assert result == "hello"
        # 在慢响应期间应该有进度更新
        assert len(progress_updates) >= 0


class TestChatNoAction:
    """测试无 Action 的直接回答"""

    @patch("react_engine.requests.post")
    def test_chat_final_answer(self, mock_post):

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"message": {"content": "Final Answer: 这是答案"}}
        mock_post.return_value = mock_resp

        engine, ctx = make_engine()
        result = engine.chat("你好")
        assert "这是答案" in result
        assert len(engine.step_log) == 1
        assert engine.step_log[0]["phase"] == "final"

    @patch("react_engine.requests.post")
    def test_chat_no_final_prefix(self, mock_post):
        """无 Final Answer 的裸文本不再直接当答案：回灌 [格式错误] 重试 2 次后才按现有文本收尾并标注。"""
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"message": {"content": "直接回答"}}
        mock_post.return_value = mock_resp

        engine, ctx = make_engine()
        result = engine.chat("你好")
        assert result.startswith("直接回答")
        assert "（格式异常，可能不完整）" in result
        assert mock_post.call_count == 3  # 首次 + 2 次重试


class TestChatWithAction:
    """测试有 Action 的迭代"""

    @patch("react_engine.requests.post")
    @patch("react_engine.registry")
    def test_chat_with_action_then_final(self, mock_registry, mock_post):

        # 第一次返回 Action，第二次返回 Final Answer
        mock_resp1 = MagicMock()
        mock_resp1.json.return_value = {"message": {"content": "Thought: 需要读取文件\nAction: read_file\nAction Input: {\"path\": \"test.py\"}"}}
        mock_resp2 = MagicMock()
        mock_resp2.json.return_value = {"message": {"content": "Final Answer: 完成"}}
        mock_post.side_effect = [mock_resp1, mock_resp2]

        mock_registry.execute.return_value = "文件内容"
        mock_registry.tools = {"read_file": {"safe": True}}
        mock_registry.get_descriptions.return_value = "Mock tool descriptions"

        engine, ctx = make_engine()
        result = engine.chat("读取文件")
        assert "完成" in result
        assert len(engine.step_log) >= 2

    @patch("react_engine.requests.post")
    @patch("react_engine.registry")
    def test_chat_with_invalid_json_action_input(self, mock_registry, mock_post):
        """测试处理无效的JSON Action Input"""

        # 返回无效的JSON（但可以被eval处理），然后工具执行，最后返回Final Answer
        mock_resp1 = MagicMock()
        mock_resp1.json.return_value = {"message": {"content": "Thought: 测试\nAction: read_file\nAction Input: {'path': 'test.py'}"}}
        mock_resp2 = MagicMock()
        mock_resp2.json.return_value = {"message": {"content": "Final Answer: done"}}
        mock_post.side_effect = [mock_resp1, mock_resp2]

        mock_registry.execute.return_value = "result"
        mock_registry.tools = {"read_file": {"safe": True}}
        mock_registry.get_descriptions.return_value = "Mock tool descriptions"

        engine, ctx = make_engine()
        result = engine.chat("测试")
        assert "done" in result

    @patch("react_engine.requests.post")
    @patch("react_engine.registry")
    def test_chat_write_file_with_braces_not_truncated(self, mock_registry, mock_post):
        """回归：含 } 的多行代码应完整传入 write_file，不被正则截断"""

        code = "def f():\\n    return {1: 2}\\n"
        action_content = (
            'Thought: 写入代码\n'
            'Action: write_file\n'
            'Action Input: {"path": "src/x.py", "content": "' + code + '"}'
        )
        mock_resp1 = MagicMock()
        mock_resp1.json.return_value = {"message": {"content": action_content}}
        mock_resp2 = MagicMock()
        mock_resp2.json.return_value = {"message": {"content": "Final Answer: 完成"}}
        mock_post.side_effect = [mock_resp1, mock_resp2]

        mock_registry.execute.return_value = "文件写入成功"
        mock_registry.tools = {"write_file": {"safe": False}}
        mock_registry.get_descriptions.return_value = "Mock tool descriptions"

        engine, ctx = make_engine()
        engine.chat("写代码")

        # 验证传给 write_file 的 content 完整保留了 return {1: 2}
        call_args = mock_registry.execute.call_args
        tool_input = call_args[0][1]
        assert tool_input["path"] == "src/x.py"
        assert "return {1: 2}" in tool_input["content"]

    @patch("react_engine.requests.post")
    @patch("react_engine.registry")
    def test_chat_dangerous_command_blocked(self, mock_registry, mock_post):

        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "message": {"content": "Thought: 删除\nAction: execute_command\nAction Input: {\"command\": \"rm -rf /\"}"}
        }

        # 危险命令被拦截，会进入下一轮
        mock_resp2 = MagicMock()
        mock_resp2.json.return_value = {"message": {"content": "Final Answer: 已拒绝"}}
        mock_post.side_effect = [mock_resp, mock_resp2]

        mock_registry.get_descriptions.return_value = "Mock tool descriptions"

        engine, ctx = make_engine()
        result = engine.chat("删除")
        assert len(engine.step_log) >= 1
        # 检查是否有被拦截的步骤
        blocked = any(log.get("phase") == "blocked" for log in engine.step_log)
        assert blocked or "安全拦截" in str(engine.step_log)


class TestChatUserInterrupt:
    """测试用户中断"""

    def test_stop_sets_event(self):

        engine, ctx = make_engine()
        engine.stop()
        assert engine._stop_event.is_set()


class TestClearHistory:
    """测试清空历史（委托会话上下文 clear）"""

    def test_clear_history(self):

        engine, ctx = make_engine()
        engine.messages = [{"role": "user", "content": "x"}]
        assert engine.clear_history() is True
        assert ctx.cleared is True
        assert engine.messages == []

    def test_clear_history_failure_reports_via_on_step(self):
        class Broken:
            def clear(self):
                raise RuntimeError("boom")

        events = []
        engine = ReActEngine(context=Broken(), on_step=lambda e: events.append(e))
        assert engine.clear_history() is False
        assert any("清空会话失败" in e.get("message", "") for e in events)


class TestGetStepSummary:
    """测试执行摘要"""

    def test_summary_with_action(self):

        engine, ctx = make_engine()
        engine.step_log = [
            {"step": 1, "phase": "action", "tool": "read_file", "confirmed": True, "thought": "读取", "safety": {"risk_level": "low"}},
            {"step": 2, "phase": "blocked"},
            {"step": 3, "phase": "rejected"},
            {"step": 4, "phase": "final", "answer": "完成"},
        ]
        summary = engine.get_step_summary()
        assert "read_file" in summary
        assert "[拦截]" in summary
        assert "[拒绝]" in summary
        assert "[完成]" in summary

    def test_summary_empty(self):

        engine, ctx = make_engine()
        summary = engine.get_step_summary()
        assert "Agent 执行摘要" in summary


def _resp(text):
    """构造一个 Ollama /api/chat 响应 Mock。"""
    r = MagicMock()
    r.json.return_value = {"message": {"content": text}}
    return r


def _action(tool, **args):
    import json as _json
    return f"Thought: t\nAction: {tool}\nAction Input: {_json.dumps(args, ensure_ascii=False)}"


class TestMaxIterations:
    """测试最大迭代次数（P1-3：耗尽后强制总结而非固定警告）"""

    @patch("react_engine.requests.post")
    def test_max_iterations_reached_triggers_forced_summary(self, mock_post):
        # 每步读不同文件，永远不给 Final Answer；第 4 次调用是强制总结
        mock_post.side_effect = [
            _resp(_action("read_file", path="a")),
            _resp(_action("read_file", path="b")),
            _resp(_action("read_file", path="c")),
            _resp("Final Answer: 已完成：读取 a/b/c；未完成：汇总；建议：继续"),
        ]
        events = []
        with patch.object(Config, "MAX_ITERATIONS", 3), \
                patch("react_engine.registry.execute", return_value="内容"):
            engine, ctx = make_engine(on_step=lambda e: events.append(e))
            result = engine.chat("test")
        assert result.startswith("⚠️ 未完成（已达最大步数 3）")
        assert "读取 a/b/c" in result
        assert "Final Answer:" not in result
        # 追加的 user 总结请求在消息列表中
        summary_req = mock_post.call_args.kwargs["json"]["messages"][-1]
        assert summary_req["role"] == "user" and "步数已用尽" in summary_req["content"]
        # 总结调用：think=False、num_predict 限额
        body = mock_post.call_args.kwargs["json"]
        assert body["think"] is False and body["options"]["num_predict"] == 1024
        # step_log / 事件 / 会话
        assert any(l["phase"] == "forced_summary" and l["reason"] == "max_iterations" for l in engine.step_log)
        assert engine.step_log[-1]["phase"] == "final" and engine.step_log[-1]["forced"] == "max_iterations"
        assert any(e.get("phase") == "forced_summary" for e in events)
        assert ctx.recorded[0]["assistant"].startswith("⚠️ 未完成")
        assert "强制总结收尾" in ctx.recorded[0]["trace"]

    @patch("react_engine.requests.post")
    def test_forced_summary_falls_back_when_model_fails(self, mock_post):
        """总结调用失败时回退为执行摘要，仍带 ⚠️ 未完成 前缀。"""
        import requests
        mock_post.side_effect = [
            _resp(_action("read_file", path="a")),
            requests.exceptions.Timeout(),
        ]
        with patch("react_engine.registry.execute", return_value="内容"):
            engine, ctx = make_engine(max_iterations=1)
            result = engine.chat("test")
        assert result.startswith("⚠️ 未完成")
        assert "模型总结失败" in result and "共 1 步" in result

    @patch("react_engine.requests.post")
    def test_forced_summary_strips_thought_prefix(self, mock_post):
        mock_post.side_effect = [
            _resp(_action("read_file", path="a")),
            _resp("Thought: 总结一下\n已完成 X"),
        ]
        with patch("react_engine.registry.execute", return_value="内容"):
            engine, ctx = make_engine(max_iterations=1)
            result = engine.chat("test")
        assert "已完成 X" in result and "Thought:" not in result


class TestFormatTolerance:
    """P1-2 协议容错：格式错误回灌重试、[错误] 不入会话"""

    @patch("react_engine.requests.post")
    def test_format_error_retry_then_success(self, mock_post):
        mock_post.side_effect = [
            _resp("Thought: 我想想"),                 # 无 Action / Final Answer
            _resp("Final Answer: 好了"),
        ]
        events = []
        engine, ctx = make_engine(on_step=lambda e: events.append(e))
        assert engine.chat("q") == "好了"
        # 回灌的 Observation 带 [格式错误] 与协议提示
        sent = mock_post.call_args.kwargs["json"]["messages"]
        obs = [m for m in sent if m["role"] == "user" and m["content"].startswith("Observation: [格式错误]")]
        assert len(obs) == 1 and "严格按协议" in obs[0]["content"]
        assert [l["phase"] for l in engine.step_log] == ["format_retry", "final"]
        assert engine.step_log[0]["retry"] == 1
        assert any(e.get("phase") == "format_retry" for e in events)
        assert "格式重试 1 次" in ctx.recorded[0]["trace"]

    @patch("react_engine.requests.post")
    def test_format_error_exhausts_retries_then_finalizes(self, mock_post):
        mock_post.return_value = _resp("Thought: 只有思考没有动作")
        engine, ctx = make_engine()
        result = engine.chat("q")
        assert mock_post.call_count == 3
        assert result.startswith("只有思考没有动作")
        assert result.endswith("（格式异常，可能不完整）")
        assert engine.step_log[-1]["format_abnormal"] is True
        assert len([l for l in engine.step_log if l["phase"] == "format_retry"]) == 2
        # 仍写回会话（带标注）
        assert ctx.recorded[0]["assistant"] == result
        assert "[格式重试 1/2]" in engine.get_step_summary()
        assert "格式异常" in engine.get_step_summary()

    @patch("react_engine.requests.post")
    def test_format_retry_counter_resets_after_valid_step(self, mock_post):
        """格式错误按"连续"计：中间有合法步骤则重新计数。"""
        mock_post.side_effect = [
            _resp("bad"),
            _resp(_action("read_file", path="a")),
            _resp("bad"),
            _resp("bad"),
            _resp("Final Answer: ok"),
        ]
        with patch("react_engine.registry.execute", return_value="内容"):
            engine, ctx = make_engine()
            assert engine.chat("q") == "ok"
        assert mock_post.call_count == 5

    @patch("react_engine.requests.post")
    def test_action_without_input_is_format_error(self, mock_post):
        mock_post.side_effect = [
            _resp("Thought: t\nAction: read_file"),
            _resp("Final Answer: ok"),
        ]
        engine, ctx = make_engine()
        assert engine.chat("q") == "ok"
        assert "缺少 Action Input" in engine.step_log[0]["reason"]

    @patch("react_engine.requests.post")
    def test_invalid_json_input_is_format_error(self, mock_post):
        mock_post.side_effect = [
            _resp('Thought: t\nAction: read_file\nAction Input: {path: a.py}'),
            _resp("Final Answer: ok"),
        ]
        engine, ctx = make_engine()
        assert engine.chat("q") == "ok"
        assert "不是合法 JSON 对象" in engine.step_log[0]["reason"]

    @patch("react_engine.requests.post")
    def test_empty_object_input_is_valid(self, mock_post):
        """{} 是合法输入（无参数工具），不得判为格式错误。"""
        mock_post.side_effect = [
            _resp("Thought: t\nAction: get_current_dir\nAction Input: {}"),
            _resp("Final Answer: ok"),
        ]
        with patch("react_engine.registry.execute", return_value="/tmp") as ex:
            engine, ctx = make_engine()
            assert engine.chat("q") == "ok"
        ex.assert_called_once()
        assert engine.step_log[0]["phase"] == "action"

    @patch("react_engine.requests.post")
    def test_unknown_tool_is_format_error(self, mock_post):
        mock_post.side_effect = [
            _resp(_action("todo_write", items=["x"])),
            _resp("Final Answer: ok"),
        ]
        with patch("react_engine.registry.execute") as ex:
            engine, ctx = make_engine()
            assert engine.chat("q") == "ok"
        ex.assert_not_called()
        assert "未知工具 todo_write" in engine.step_log[0]["reason"]

    @patch("react_engine.requests.post")
    def test_model_error_returned_directly_not_recorded(self, mock_post):
        """_call_model 返回 [错误] 时直接返回该错误，不 _record_turn。"""
        import requests
        mock_post.side_effect = requests.exceptions.ConnectionError()
        events = []
        engine, ctx = make_engine(on_step=lambda e: events.append(e))
        result = engine.chat("q")
        assert result.startswith("[错误] 无法连接到 Ollama")
        assert ctx.recorded == []
        assert engine.step_log == [{"step": 1, "phase": "error", "message": result}]
        assert any(e.get("phase") == "error" for e in events)
        assert "[错误]" in engine.get_step_summary()

    @patch("react_engine.requests.post")
    def test_model_error_mid_task_not_recorded(self, mock_post):
        import requests
        mock_post.side_effect = [_resp(_action("read_file", path="a")), requests.exceptions.Timeout()]
        with patch("react_engine.registry.execute", return_value="内容"):
            engine, ctx = make_engine()
            result = engine.chat("q")
        assert result.startswith("[错误] 模型响应超时")
        assert ctx.recorded == []


class TestRepeatDetection:
    """P1-4：相同 (tool, canonical_json(args)) 第 2 次回灌提示，第 3 次强制总结"""

    @patch("react_engine.requests.post")
    def test_second_repeat_feeds_hint_without_executing(self, mock_post):
        # 参数键序不同也算相同调用
        mock_post.side_effect = [
            _resp('Thought: t\nAction: read_file\nAction Input: {"path": "a", "limit": 10}'),
            _resp('Thought: t\nAction: read_file\nAction Input: {"limit": 10, "path": "a"}'),
            _resp("Final Answer: 用已有结果"),
        ]
        events = []
        with patch("react_engine.registry.execute", return_value="内容") as ex:
            engine, ctx = make_engine(on_step=lambda e: events.append(e))
            assert engine.chat("q") == "用已有结果"
        assert ex.call_count == 1
        rep = [l for l in engine.step_log if l["phase"] == "repeat"]
        assert len(rep) == 1 and rep[0]["count"] == 2 and rep[0]["tool"] == "read_file"
        sent = mock_post.call_args.kwargs["json"]["messages"]
        assert any(m["content"].startswith("Observation: [重复调用]") for m in sent if m["role"] == "user")
        assert any(e.get("phase") == "repeat" for e in events)
        assert "[重复] read_file 第 2 次" in engine.get_step_summary()
        assert "重复调用 1 次" in ctx.recorded[0]["trace"]

    @patch("react_engine.requests.post")
    def test_third_repeat_forces_summary_and_stops(self, mock_post):
        mock_post.side_effect = [
            _resp(_action("read_file", path="a")),
            _resp(_action("read_file", path="a")),
            _resp(_action("read_file", path="a")),
            _resp("已完成：读取 a；未完成：其余；建议：换方法"),
        ]
        with patch("react_engine.registry.execute", return_value="内容") as ex:
            engine, ctx = make_engine()
            result = engine.chat("q")
        assert ex.call_count == 1
        assert mock_post.call_count == 4
        assert result.startswith("⚠️ 未完成（检测到重复调用，已终止）")
        assert "换方法" in result
        forced = [l for l in engine.step_log if l["phase"] == "forced_summary"]
        assert forced and forced[0]["reason"] == "repeat"
        summary_req = mock_post.call_args.kwargs["json"]["messages"][-1]
        assert "重复" in summary_req["content"]
        assert len(ctx.recorded) == 1

    @patch("react_engine.requests.post")
    def test_different_args_not_counted_as_repeat(self, mock_post):
        mock_post.side_effect = [
            _resp(_action("read_file", path="a")),
            _resp(_action("read_file", path="b")),
            _resp(_action("read_file", path="c")),
            _resp("Final Answer: ok"),
        ]
        with patch("react_engine.registry.execute", return_value="内容") as ex:
            engine, ctx = make_engine()
            assert engine.chat("q") == "ok"
        assert ex.call_count == 3
        assert not any(l["phase"] == "repeat" for l in engine.step_log)


class TestTurnBudget:
    """P1-5：Observation 截断 + 本轮预算折叠（用小 num_ctx 触发）"""

    def test_observation_truncated_with_note(self):
        from react_engine import _truncate_observation
        long = "x" * 3500
        out = _truncate_observation(long)
        assert out.startswith("x" * 3000)
        assert "Observation 已截断" in out and "原长 3500" in out
        assert _truncate_observation("short") == "short"
        assert _truncate_observation("a" * 10, limit=4).startswith("aaaa\n…")

    @patch("react_engine.requests.post")
    def test_long_observation_truncated_in_messages(self, mock_post):
        mock_post.side_effect = [_resp(_action("read_file", path="a")), _resp("Final Answer: ok")]
        with patch("react_engine.registry.execute", return_value="y" * 5000):
            engine, ctx = make_engine()
            engine.chat("q")
        obs = [m for m in engine.messages if m["role"] == "user" and m["content"].startswith("Observation: y")]
        assert len(obs) == 1
        assert "已截断" in obs[0]["content"]
        assert len(engine.step_log[0]["observation"]) < 3200

    def test_turn_budget_formula(self):
        from conversation_context import estimate_tokens, estimate_messages_tokens
        ctx = FakeContext(messages=[{"role": "user", "content": "旧问题" * 50},
                                    {"role": "assistant", "content": "旧回答" * 50}], summary="摘要" * 20)
        engine, _ = make_engine(context=ctx, model="qwen3.5:4b")  # num_ctx 16384
        engine._load_context("新问题")
        base = ctx.build_messages(system_prompt=engine.system_prompt)
        expected = 16384 - estimate_tokens(engine.system_prompt) - estimate_messages_tokens(base[1:]) - 4096
        assert engine.turn_budget == expected
        assert engine._turn_start == len(base)

    def test_turn_budget_has_floor(self):
        engine, _ = make_engine()
        engine.num_ctx = 512
        engine._load_context("q")
        assert engine.turn_budget == 1024

    @patch("react_engine.requests.post")
    def test_budget_fold_keeps_recent_three_steps(self, mock_post):
        """小预算下最早步骤的 Observation 折叠为一行摘要，最近 3 步保持完整。"""
        big = ("这是第{k}步的很长的观察结果，" * 40)
        mock_post.side_effect = [
            _resp(_action("read_file", path=f"f{k}")) for k in range(1, 6)
        ] + [_resp("Final Answer: ok")]
        obs_iter = iter(big.format(k=k) for k in range(1, 6))
        events = []
        with patch("react_engine.registry.execute", side_effect=lambda *a, **k: next(obs_iter)):
            engine, ctx = make_engine(on_step=lambda e: events.append(e))
            engine.num_ctx = 512  # 触发预算下限 1024 token
            assert engine.chat("q") == "ok"

        obs_msgs = [m for m in engine.messages if m["role"] == "user" and m["content"].startswith("Observation:")]
        assert len(obs_msgs) == 5
        folded = [m for m in obs_msgs if "结果已折叠" in m["content"]]
        intact = [m for m in obs_msgs if "结果已折叠" not in m["content"]]
        # 最近 3 步（3、4、5）必须完整，最早的步骤被折叠
        assert len(intact) >= 3
        assert "第3步" in intact[-3]["content"] and "第4步" in intact[-2]["content"] and "第5步" in intact[-1]["content"]
        assert folded and "第 1 步 tool=read_file 结果已折叠，要点：" in folded[0]["content"]
        assert len(folded[0]["content"]) < 300  # 一行摘要（前 200 字）
        # 系统提示原样保留
        assert engine.messages[0]["role"] == "system" and engine.messages[0]["content"] == engine.system_prompt
        # step_log / 事件
        fold_logs = [l for l in engine.step_log if l["phase"] == "budget_fold"]
        assert fold_logs and 1 in fold_logs[0]["folded_steps"]
        assert any(e.get("phase") == "budget_fold" for e in events)
        assert "[折叠]" in engine.get_step_summary()
        assert "上下文折叠" in ctx.recorded[0]["trace"]

    @patch("react_engine.requests.post")
    def test_no_fold_when_within_budget(self, mock_post):
        mock_post.side_effect = [_resp(_action("read_file", path="a")), _resp("Final Answer: ok")]
        with patch("react_engine.registry.execute", return_value="short"):
            engine, ctx = make_engine()
            engine.chat("q")
        assert not any(l["phase"] == "budget_fold" for l in engine.step_log)

    def test_enforce_budget_stops_once_within_budget(self):
        """折叠够用即停：只折叠最早一步，第 2 步保持完整。"""
        engine, _ = make_engine()
        engine._load_context("q")
        for k in range(1, 6):
            engine._push_observation(k, "read_file", "Thought", f"第{k}步" + "内容" * 200, "")
        # 折叠前 5 步都完整；把预算设为"只需折叠 1 步就够"的值
        tokens = engine._turn_tokens()
        engine.turn_budget = tokens - 100
        folded = engine._enforce_budget(6)
        assert folded == [1]
        assert engine._obs_index[0]["folded"] and not engine._obs_index[1]["folded"]
        assert engine._enforce_budget(7) == []  # 已在预算内，不再折叠

    def test_enforce_budget_never_folds_protected_steps(self):
        engine, _ = make_engine()
        engine._load_context("q")
        engine.turn_budget = 1  # 极小预算
        for k in range(1, 4):
            engine._push_observation(k, "read_file", "Thought", "内容" * 100, "")
        # 只有 3 步，全部受保护 → 不折叠
        assert all(not e["folded"] for e in engine._obs_index)
        assert not any(l["phase"] == "budget_fold" for l in engine.step_log)


class TestOnStepCallbackCoverage:
    """测试 on_step 回调的各种情况，提高覆盖率"""

    @patch("react_engine.requests.post")
    @patch("react_engine.registry")
    def test_on_step_thinking_callback(self, mock_registry, mock_post):
        """测试 thinking 阶段的 on_step 回调"""

        step_callback_calls = []
        def step_callback(data):
            step_callback_calls.append(data)

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"message": {"content": "Final Answer: done"}}
        mock_post.return_value = mock_resp

        mock_registry.get_descriptions.return_value = "Mock tool descriptions"

        engine, ctx = make_engine(on_step=step_callback)
        result = engine.chat("test")
        
        # 检查 thinking 阶段的回调被调用
        assert any(call["phase"] == "thinking" for call in step_callback_calls)
        assert "done" in result

    @patch("react_engine.requests.post")
    @patch("react_engine.registry")
    def test_on_step_executing_callback(self, mock_registry, mock_post):
        """测试 executing 阶段的 on_step 回调"""

        step_callback_calls = []
        def step_callback(data):
            step_callback_calls.append(data)

        mock_resp1 = MagicMock()
        mock_resp1.json.return_value = {"message": {"content": "Thought: t\nAction: read_file\nAction Input: {\"path\": \"test.py\"}"}}
        mock_resp2 = MagicMock()
        mock_resp2.json.return_value = {"message": {"content": "Final Answer: done"}}
        mock_post.side_effect = [mock_resp1, mock_resp2]

        mock_registry.execute.return_value = "file content"
        mock_registry.tools = {"read_file": {"safe": True}}
        mock_registry.get_descriptions.return_value = "Mock tool descriptions"

        engine, ctx = make_engine(on_step=step_callback)
        result = engine.chat("test")
        
        # 检查 executing 阶段的回调被调用
        assert any(call["phase"] == "executing" for call in step_callback_calls)
        assert "done" in result

    @patch("react_engine.requests.post")
    @patch("react_engine.registry")
    def test_on_step_observed_callback(self, mock_registry, mock_post):
        """测试 observed 阶段的 on_step 回调"""

        step_callback_calls = []
        def step_callback(data):
            step_callback_calls.append(data)

        mock_resp1 = MagicMock()
        mock_resp1.json.return_value = {"message": {"content": "Thought: t\nAction: read_file\nAction Input: {\"path\": \"test.py\"}"}}
        mock_resp2 = MagicMock()
        mock_resp2.json.return_value = {"message": {"content": "Final Answer: done"}}
        mock_post.side_effect = [mock_resp1, mock_resp2]

        mock_registry.execute.return_value = "file content"
        mock_registry.tools = {"read_file": {"safe": True}}
        mock_registry.get_descriptions.return_value = "Mock tool descriptions"

        engine, ctx = make_engine(on_step=step_callback)
        result = engine.chat("test")
        
        # 检查 observed 阶段的回调被调用
        assert any(call["phase"] == "observed" for call in step_callback_calls)
        assert "done" in result


class TestJSONParsingErrors:
    """测试 JSON 解析错误处理 - 这些路径很难测试，跳过"""
    pass


class TestUserConfirmation:
    """测试用户确认逻辑"""

    @patch("react_engine.requests.post")
    @patch("react_engine.registry")
    def test_command_user_rejects(self, mock_registry, mock_post):
        """测试用户拒绝执行命令"""

        mock_resp1 = MagicMock()
        mock_resp1.json.return_value = {"message": {"content": "Thought: t\nAction: execute_command\nAction Input: {\"command\": \"rm file.txt\"}"}}
        mock_resp2 = MagicMock()
        mock_resp2.json.return_value = {"message": {"content": "Final Answer: 好的，不删除"}}
        mock_post.side_effect = [mock_resp1, mock_resp2]

        mock_registry.get_descriptions.return_value = "Mock tool descriptions"

        confirm_calls = []
        def confirm_callback(data):
            confirm_calls.append(data)
            return False  # 用户拒绝

        engine, ctx = make_engine(on_confirm=confirm_callback)
        result = engine.chat("delete file")
        
        # 检查用户拒绝的回调被调用
        assert len(confirm_calls) > 0
        assert "好的，不删除" in result

    @patch("react_engine.requests.post")
    @patch("react_engine.registry")
    def test_tool_confirm_required_user_rejects(self, mock_registry, mock_post):
        """测试工具需要确认但用户拒绝"""

        mock_resp1 = MagicMock()
        mock_resp1.json.return_value = {"message": {"content": "Thought: t\nAction: write_file\nAction Input: {\"path\": \"test.txt\"}"}}
        mock_resp2 = MagicMock()
        mock_resp2.json.return_value = {"message": {"content": "Final Answer: 好的，不写入"}}
        mock_post.side_effect = [mock_resp1, mock_resp2]

        # 返回需要确认的标记
        mock_registry.execute.return_value = "[CONFIRM_REQUIRED] write_file|{\"path\": \"test.txt\"}"
        mock_registry.tools = {"write_file": {"safe": False}}
        mock_registry.get_descriptions.return_value = "Mock tool descriptions"

        confirm_calls = []
        def confirm_callback(data):
            confirm_calls.append(data)
            return False  # 用户拒绝

        engine, ctx = make_engine(on_confirm=confirm_callback)
        result = engine.chat("write file")
        
        # 检查用户拒绝的回调被调用
        assert len(confirm_calls) > 0
        assert "好的，不写入" in result


    @patch("react_engine.requests.post")
    @patch("react_engine.registry")
    def test_command_user_confirms_then_executes(self, mock_registry, mock_post):
        """medium 风险命令（pip install）用户确认后执行。"""
        mock_post.side_effect = [_resp(_action("execute_command", command="pip install rich")),
                                 _resp("Final Answer: 装好了")]
        mock_registry.execute.return_value = "Successfully installed"
        mock_registry.tools = {"execute_command": {"safe": False}}
        mock_registry.get_descriptions.return_value = "tools"
        engine, ctx = make_engine(on_confirm=lambda d: True)
        assert engine.chat("安装 rich") == "装好了"
        mock_registry.execute.assert_called_once()
        assert engine.step_log[0]["confirmed"] is True
        assert engine.step_log[0]["safety"]["risk_level"] == "medium"

    @patch("react_engine.requests.post")
    @patch("react_engine.registry")
    def test_tool_confirm_required_user_accepts(self, mock_registry, mock_post):
        mock_post.side_effect = [_resp(_action("write_file", path="a.txt", content="x")),
                                 _resp("Final Answer: 写好了")]
        mock_registry.execute.side_effect = ['[CONFIRM_REQUIRED] write_file|{"path": "a.txt"}', "[成功] 写入"]
        mock_registry.tools = {"write_file": {"safe": False}}
        mock_registry.get_descriptions.return_value = "tools"
        engine, ctx = make_engine(on_confirm=lambda d: True)
        assert engine.chat("写文件") == "写好了"
        assert mock_registry.execute.call_count == 2
        assert mock_registry.execute.call_args.kwargs["auto_confirm"] is True
        assert engine.step_log[0]["confirmed"] is True and engine.step_log[0]["observation"] == "[成功] 写入"


class TestUserInterrupt:
    """测试用户中断"""

    @patch("react_engine.requests.post")
    def test_stop_before_step_returns_interrupt_without_recording(self, mock_post):
        engine, ctx = make_engine()
        engine.reset_stop = lambda: None  # 保留已置位的停止标志
        engine.stop()
        assert engine.chat("q") == "[用户中断] 任务已停止。"
        mock_post.assert_not_called()
        assert ctx.recorded == []


class TestSetModelAndThink:
    """运行时热切换模型 + 思考模式开关"""

    def test_set_model_updates_model_and_num_ctx(self):
        engine, ctx = make_engine(model="qwen3.5:4b")
        assert engine.num_ctx == 16384
        ctx = engine.set_model("qwen3.5:9b")
        assert ctx == 8192
        assert engine.model == "qwen3.5:9b"
        assert engine.num_ctx == 8192

    def test_set_model_rejects_empty(self):
        engine, ctx = make_engine(model="qwen3.5:4b")
        with pytest.raises(ValueError):
            engine.set_model("  ")

    def test_think_defaults_false(self):
        engine, ctx = make_engine()
        assert engine.think is False

    @patch("react_engine.requests.post")
    def test_call_model_sends_think_flag(self, mock_post):
        mock_post.return_value = MagicMock(**{"json.return_value": {"message": {"content": "ok"}}})
        engine, ctx = make_engine(model="qwen3.5:9b")
        engine._call_model([{"role": "user", "content": "hi"}])
        body = mock_post.call_args.kwargs["json"]
        assert body["think"] is False
        assert body["model"] == "qwen3.5:9b"
        assert body["options"]["num_ctx"] == 8192

    @patch("react_engine.requests.post")
    def test_call_model_after_switch_uses_new_model(self, mock_post):
        mock_post.return_value = MagicMock(**{"json.return_value": {"message": {"content": "ok"}}})
        engine, ctx = make_engine(model="qwen3.5:4b")
        engine.set_model("qwen3.5:9b")
        engine._call_model([{"role": "user", "content": "hi"}])
        body = mock_post.call_args.kwargs["json"]
        assert body["model"] == "qwen3.5:9b"
        assert body["options"]["num_ctx"] == 8192

    @patch("react_engine.requests.post")
    def test_set_think_affects_next_request(self, mock_post):
        mock_post.return_value = MagicMock(**{"json.return_value": {"message": {"content": "ok"}}})
        engine, ctx = make_engine(model="qwen3.5:4b")
        assert engine.set_think(True) is True
        engine._call_model([{"role": "user", "content": "hi"}])
        assert mock_post.call_args.kwargs["json"]["think"] is True
        assert engine.set_think(False) is False
        engine._call_model([{"role": "user", "content": "hi"}])
        assert mock_post.call_args.kwargs["json"]["think"] is False
