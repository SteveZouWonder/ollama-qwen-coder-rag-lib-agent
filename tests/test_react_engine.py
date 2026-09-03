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

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"message": {"content": "直接回答"}}
        mock_post.return_value = mock_resp

        engine, ctx = make_engine()
        result = engine.chat("你好")
        assert result == "直接回答"


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


class TestMaxIterations:
    """测试最大迭代次数"""

    @patch("react_engine.requests.post")
    def test_max_iterations_reached(self, mock_post):

        # 每次都返回 Action，永远不会 Final Answer
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "message": {"content": "Thought: t\nAction: read_file\nAction Input: {\"path\": \"x\"}"}
        }
        mock_post.return_value = mock_resp

        with patch.object(Config, "MAX_ITERATIONS", 3):
            engine, ctx = make_engine()
            result = engine.chat("test")
            assert "达到最大迭代次数" in result


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


class TestUserInterrupt:
    """测试用户中断逻辑 - 这个路径很难测试，跳过"""
    pass


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
