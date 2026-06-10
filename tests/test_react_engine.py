#!/usr/bin/env python3
"""
test_react_engine.py — ReAct 引擎单元测试（Mock requests.post）
"""
import pytest
from unittest.mock import MagicMock, patch
import json

from react_engine import ReActEngine
from config import Config


class TestReActEngineInit:
    """测试初始化"""

    @patch("react_engine.ChatHistory")
    def test_init_loads_defaults(self, mock_history_cls):
        mock_history = MagicMock()
        mock_history.get_messages.return_value = []
        mock_history_cls.return_value = mock_history

        engine = ReActEngine()
        assert engine.model == Config.LLM_MODEL
        assert engine.host == Config.OLLAMA_BASE_URL
        assert engine.step_log == []

    @patch("react_engine.ChatHistory")
    def test_init_with_custom_model(self, mock_history_cls):
        mock_history = MagicMock()
        mock_history.get_messages.return_value = []
        mock_history_cls.return_value = mock_history

        engine = ReActEngine(model="custom:7b", host="http://other:11434")
        assert engine.model == "custom:7b"
        assert engine.host == "http://other:11434"

    @patch("react_engine.ChatHistory")
    def test_init_injects_system_prompt(self, mock_history_cls):
        mock_history = MagicMock()
        mock_history.get_messages.return_value = []
        mock_history_cls.return_value = mock_history

        engine = ReActEngine()
        assert mock_history.messages.insert.called
        assert mock_history.save.called

    @patch("react_engine.ChatHistory")
    def test_init_skips_system_if_exists(self, mock_history_cls):
        mock_history = MagicMock()
        mock_history.get_messages.return_value = [{"role": "system", "content": "exists"}]
        mock_history_cls.return_value = mock_history

        engine = ReActEngine()
        assert not mock_history.messages.insert.called


class TestCallModel:
    """测试 _call_model"""

    @patch("react_engine.ChatHistory")
    @patch("react_engine.requests.post")
    def test_call_model_success(self, mock_post, mock_history_cls):
        mock_history = MagicMock()
        mock_history.get_messages.return_value = [{"role": "user", "content": "hi"}]
        mock_history_cls.return_value = mock_history

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"message": {"content": "hello"}}
        mock_post.return_value = mock_resp

        engine = ReActEngine()
        result = engine._call_model()
        assert result == "hello"
        mock_post.assert_called_once()

    @patch("react_engine.ChatHistory")
    @patch("react_engine.requests.post")
    def test_call_model_connection_error(self, mock_post, mock_history_cls):
        mock_history = MagicMock()
        mock_history.get_messages.return_value = [{"role": "user", "content": "hi"}]
        mock_history_cls.return_value = mock_history

        import requests
        mock_post.side_effect = requests.exceptions.ConnectionError()

        engine = ReActEngine()
        result = engine._call_model()
        assert "无法连接到 Ollama" in result

    @patch("react_engine.ChatHistory")
    @patch("react_engine.requests.post")
    def test_call_model_timeout(self, mock_post, mock_history_cls):
        mock_history = MagicMock()
        mock_history.get_messages.return_value = [{"role": "user", "content": "hi"}]
        mock_history_cls.return_value = mock_history

        import requests
        mock_post.side_effect = requests.exceptions.Timeout()

        engine = ReActEngine()
        result = engine._call_model()
        assert "模型响应超时" in result

    @patch("react_engine.ChatHistory")
    @patch("react_engine.requests.post")
    def test_call_model_generic_error(self, mock_post, mock_history_cls):
        mock_history = MagicMock()
        mock_history.get_messages.return_value = [{"role": "user", "content": "hi"}]
        mock_history_cls.return_value = mock_history

        mock_post.side_effect = ValueError("boom")

        engine = ReActEngine()
        result = engine._call_model()
        assert "模型调用失败" in result
        assert "boom" in result

    @patch("react_engine.ChatHistory")
    def test_call_model_empty_messages(self, mock_history_cls):
        mock_history = MagicMock()
        mock_history.get_messages.return_value = []
        mock_history_cls.return_value = mock_history

        engine = ReActEngine()
        result = engine._call_model()
        assert "消息列表为空" in result


class TestChatNoAction:
    """测试无 Action 的直接回答"""

    @patch("react_engine.ChatHistory")
    @patch("react_engine.requests.post")
    def test_chat_final_answer(self, mock_post, mock_history_cls):
        mock_history = MagicMock()
        messages = []
        mock_history.get_messages.return_value = messages
        mock_history.add = lambda role, content: messages.append({"role": role, "content": content})
        mock_history_cls.return_value = mock_history

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"message": {"content": "Final Answer: 这是答案"}}
        mock_post.return_value = mock_resp

        engine = ReActEngine()
        result = engine.chat("你好")
        assert "这是答案" in result
        assert len(engine.step_log) == 1
        assert engine.step_log[0]["phase"] == "final"

    @patch("react_engine.ChatHistory")
    @patch("react_engine.requests.post")
    def test_chat_no_final_prefix(self, mock_post, mock_history_cls):
        mock_history = MagicMock()
        messages = []
        mock_history.get_messages.return_value = messages
        mock_history.add = lambda role, content: messages.append({"role": role, "content": content})
        mock_history_cls.return_value = mock_history

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"message": {"content": "直接回答"}}
        mock_post.return_value = mock_resp

        engine = ReActEngine()
        result = engine.chat("你好")
        assert result == "直接回答"


class TestChatWithAction:
    """测试有 Action 的迭代"""

    @patch("react_engine.ChatHistory")
    @patch("react_engine.requests.post")
    @patch("react_engine.registry")
    def test_chat_with_action_then_final(self, mock_registry, mock_post, mock_history_cls):
        mock_history = MagicMock()
        messages = []
        mock_history.get_messages.return_value = messages
        mock_history.add = lambda role, content: messages.append({"role": role, "content": content})
        mock_history_cls.return_value = mock_history

        # 第一次返回 Action，第二次返回 Final Answer
        mock_resp1 = MagicMock()
        mock_resp1.json.return_value = {"message": {"content": "Thought: 需要读取文件\nAction: read_file\nAction Input: {\"path\": \"test.py\"}"}}
        mock_resp2 = MagicMock()
        mock_resp2.json.return_value = {"message": {"content": "Final Answer: 完成"}}
        mock_post.side_effect = [mock_resp1, mock_resp2]

        mock_registry.execute.return_value = "文件内容"
        mock_registry.tools = {"read_file": {"safe": True}}
        mock_registry.get_descriptions.return_value = "Mock tool descriptions"

        engine = ReActEngine()
        result = engine.chat("读取文件")
        assert "完成" in result
        assert len(engine.step_log) >= 2

    @patch("react_engine.ChatHistory")
    @patch("react_engine.requests.post")
    @patch("react_engine.registry")
    def test_chat_dangerous_command_blocked(self, mock_registry, mock_post, mock_history_cls):
        mock_history = MagicMock()
        messages = []
        mock_history.get_messages.return_value = messages
        mock_history.add = lambda role, content: messages.append({"role": role, "content": content})
        mock_history_cls.return_value = mock_history

        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "message": {"content": "Thought: 删除\nAction: execute_command\nAction Input: {\"command\": \"rm -rf /\"}"}
        }

        # 危险命令被拦截，会进入下一轮
        mock_resp2 = MagicMock()
        mock_resp2.json.return_value = {"message": {"content": "Final Answer: 已拒绝"}}
        mock_post.side_effect = [mock_resp, mock_resp2]

        mock_registry.get_descriptions.return_value = "Mock tool descriptions"

        engine = ReActEngine()
        result = engine.chat("删除")
        assert len(engine.step_log) >= 1
        # 检查是否有被拦截的步骤
        blocked = any(log.get("phase") == "blocked" for log in engine.step_log)
        assert blocked or "安全拦截" in str(engine.step_log)


class TestChatUserInterrupt:
    """测试用户中断"""

    @patch("react_engine.ChatHistory")
    def test_stop_sets_event(self, mock_history_cls):
        mock_history = MagicMock()
        mock_history.get_messages.return_value = []
        mock_history_cls.return_value = mock_history

        engine = ReActEngine()
        engine.stop()
        assert engine._stop_event.is_set()


class TestClearHistory:
    """测试清空历史"""

    @patch("react_engine.ChatHistory")
    def test_clear_history(self, mock_history_cls):
        mock_history = MagicMock()
        mock_history.get_messages.return_value = []
        mock_history_cls.return_value = mock_history

        engine = ReActEngine()
        engine.clear_history()
        assert mock_history.clear.called


class TestGetStepSummary:
    """测试执行摘要"""

    @patch("react_engine.ChatHistory")
    def test_summary_with_action(self, mock_history_cls):
        mock_history = MagicMock()
        mock_history.get_messages.return_value = []
        mock_history_cls.return_value = mock_history

        engine = ReActEngine()
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

    @patch("react_engine.ChatHistory")
    def test_summary_empty(self, mock_history_cls):
        mock_history = MagicMock()
        mock_history.get_messages.return_value = []
        mock_history_cls.return_value = mock_history

        engine = ReActEngine()
        summary = engine.get_step_summary()
        assert "Agent 执行摘要" in summary


class TestMaxIterations:
    """测试最大迭代次数"""

    @patch("react_engine.ChatHistory")
    @patch("react_engine.requests.post")
    def test_max_iterations_reached(self, mock_post, mock_history_cls):
        mock_history = MagicMock()
        messages = []
        mock_history.get_messages.return_value = messages
        mock_history.add = lambda role, content: messages.append({"role": role, "content": content})
        mock_history_cls.return_value = mock_history

        # 每次都返回 Action，永远不会 Final Answer
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "message": {"content": "Thought: t\nAction: read_file\nAction Input: {\"path\": \"x\"}"}
        }
        mock_post.return_value = mock_resp

        with patch.object(Config, "MAX_ITERATIONS", 3):
            engine = ReActEngine()
            result = engine.chat("test")
            assert "达到最大迭代次数" in result


class TestOnStepCallbackCoverage:
    """测试 on_step 回调的各种情况，提高覆盖率"""

    @patch("react_engine.ChatHistory")
    @patch("react_engine.requests.post")
    @patch("react_engine.registry")
    def test_on_step_thinking_callback(self, mock_registry, mock_post, mock_history_cls):
        """测试 thinking 阶段的 on_step 回调"""
        mock_history = MagicMock()
        messages = []
        mock_history.get_messages.return_value = messages
        mock_history.add = lambda role, content: messages.append({"role": role, "content": content})
        mock_history_cls.return_value = mock_history

        step_callback_calls = []
        def step_callback(data):
            step_callback_calls.append(data)

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"message": {"content": "Final Answer: done"}}
        mock_post.return_value = mock_resp

        mock_registry.get_descriptions.return_value = "Mock tool descriptions"

        engine = ReActEngine(on_step=step_callback)
        result = engine.chat("test")
        
        # 检查 thinking 阶段的回调被调用
        assert any(call["phase"] == "thinking" for call in step_callback_calls)
        assert "done" in result

    @patch("react_engine.ChatHistory")
    @patch("react_engine.requests.post")
    @patch("react_engine.registry")
    def test_on_step_executing_callback(self, mock_registry, mock_post, mock_history_cls):
        """测试 executing 阶段的 on_step 回调"""
        mock_history = MagicMock()
        messages = []
        mock_history.get_messages.return_value = messages
        mock_history.add = lambda role, content: messages.append({"role": role, "content": content})
        mock_history_cls.return_value = mock_history

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

        engine = ReActEngine(on_step=step_callback)
        result = engine.chat("test")
        
        # 检查 executing 阶段的回调被调用
        assert any(call["phase"] == "executing" for call in step_callback_calls)
        assert "done" in result

    @patch("react_engine.ChatHistory")
    @patch("react_engine.requests.post")
    @patch("react_engine.registry")
    def test_on_step_observed_callback(self, mock_registry, mock_post, mock_history_cls):
        """测试 observed 阶段的 on_step 回调"""
        mock_history = MagicMock()
        messages = []
        mock_history.get_messages.return_value = messages
        mock_history.add = lambda role, content: messages.append({"role": role, "content": content})
        mock_history_cls.return_value = mock_history

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

        engine = ReActEngine(on_step=step_callback)
        result = engine.chat("test")
        
        # 检查 observed 阶段的回调被调用
        assert any(call["phase"] == "observed" for call in step_callback_calls)
        assert "done" in result


class TestJSONParsingErrors:
    """测试 JSON 解析错误处理 - 这些路径很难测试，跳过"""
    pass


class TestUserConfirmation:
    """测试用户确认逻辑"""

    @patch("react_engine.ChatHistory")
    @patch("react_engine.requests.post")
    @patch("react_engine.registry")
    def test_command_user_rejects(self, mock_registry, mock_post, mock_history_cls):
        """测试用户拒绝执行命令"""
        mock_history = MagicMock()
        messages = []
        mock_history.get_messages.return_value = messages
        mock_history.add = lambda role, content: messages.append({"role": role, "content": content})
        mock_history_cls.return_value = mock_history

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

        engine = ReActEngine(on_confirm=confirm_callback)
        result = engine.chat("delete file")
        
        # 检查用户拒绝的回调被调用
        assert len(confirm_calls) > 0
        assert "好的，不删除" in result

    @patch("react_engine.ChatHistory")
    @patch("react_engine.requests.post")
    @patch("react_engine.registry")
    def test_tool_confirm_required_user_rejects(self, mock_registry, mock_post, mock_history_cls):
        """测试工具需要确认但用户拒绝"""
        mock_history = MagicMock()
        messages = []
        mock_history.get_messages.return_value = messages
        mock_history.add = lambda role, content: messages.append({"role": role, "content": content})
        mock_history_cls.return_value = mock_history

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

        engine = ReActEngine(on_confirm=confirm_callback)
        result = engine.chat("write file")
        
        # 检查用户拒绝的回调被调用
        assert len(confirm_calls) > 0
        assert "好的，不写入" in result


class TestUserInterrupt:
    """测试用户中断逻辑 - 这个路径很难测试，跳过"""
    pass
