#!/usr/bin/env python3
"""
test_streaming_p1_1.py — F10 P1-1 真流式输出（引擎层 / 共享层 / Web 服务层 / Web 呈现层 / CLI）

Mock ``requests.post`` 返回带 ``iter_lines()`` 的 NDJSON 序列，不触碰真实 Ollama。
"""
import json
from unittest.mock import MagicMock, patch

import pytest

import react_engine
from react_engine import FinalAnswerStream, ReActEngine

from tests.test_react_engine import FakeContext


def ndjson_response(chunks, done=True, error=None):
    """构造一个流式 ``requests.Response`` 替身：``iter_lines()`` 逐行给出 NDJSON。"""
    lines = [json.dumps({"message": {"role": "assistant", "content": c}, "done": False}).encode()
             for c in chunks]
    if error is not None:
        lines.append(json.dumps({"error": error}).encode())
    elif done:
        lines.append(b"")  # 空行应被忽略
        lines.append(json.dumps({"message": {"role": "assistant", "content": ""}, "done": True}).encode())
    resp = MagicMock()
    resp.iter_lines.return_value = iter(lines)
    return resp


def make_engine(**kwargs):
    ctx = kwargs.pop("context", None) or FakeContext()
    return ReActEngine(context=ctx, **kwargs), ctx


def set_stream(monkeypatch, value: bool) -> None:
    """同时改 ``sys.modules["config"].Config``（llm_helper / rag_pipeline 按需 import）与
    ``react_engine.Config``（模块级引用）：其它测试可能 reload 过 config，两者未必是同一个类对象。"""
    import config as cfg_mod
    monkeypatch.setattr(cfg_mod.Config, "LLM_STREAM", value)
    monkeypatch.setattr(react_engine.Config, "LLM_STREAM", value)


# ==================== 引擎层：_call_model ====================

class TestCallModelStreaming:
    @patch("react_engine.requests.post")
    def test_no_on_token_request_unchanged(self, mock_post):
        """无 on_token 时请求体 stream=False、不带 stream 关键字，与此前完全一致。"""
        resp = MagicMock()
        resp.json.return_value = {"message": {"content": "hi"}}
        mock_post.return_value = resp
        engine, _ = make_engine()
        assert engine._call_model([{"role": "user", "content": "q"}]) == "hi"
        kwargs = mock_post.call_args.kwargs
        assert kwargs["json"]["stream"] is False
        assert "stream" not in kwargs
        resp.iter_lines.assert_not_called()

    @patch("react_engine.requests.post")
    def test_stream_tokens_concat_equals_return(self, mock_post, monkeypatch):
        set_stream(monkeypatch, True)
        mock_post.return_value = ndjson_response(["Final", " Answer:", " 你好", "，世界"])
        seen = []
        engine, _ = make_engine()
        out = engine._call_model([{"role": "user", "content": "q"}], on_token=seen.append)
        assert out == "Final Answer: 你好，世界"
        assert "".join(seen) == out
        assert len(seen) == 4
        kwargs = mock_post.call_args.kwargs
        assert kwargs["json"]["stream"] is True and kwargs["stream"] is True
        mock_post.return_value.close.assert_called()

    @patch("react_engine.requests.post")
    def test_stream_disabled_single_callback(self, mock_post, monkeypatch):
        """LLM_STREAM=false：非流式请求，on_token 只被调一次且为完整文本。"""
        set_stream(monkeypatch, False)
        resp = MagicMock()
        resp.json.return_value = {"message": {"content": "整段文本"}}
        mock_post.return_value = resp
        seen = []
        engine, _ = make_engine()
        assert engine._call_model([{"role": "user", "content": "q"}], on_token=seen.append) == "整段文本"
        assert seen == ["整段文本"]
        assert mock_post.call_args.kwargs["json"]["stream"] is False
        assert "stream" not in mock_post.call_args.kwargs

    @patch("react_engine.requests.post")
    def test_stop_stops_callbacks_and_closes_response(self, mock_post, monkeypatch):
        """取消标志置位后不再回调，且 response.close() 被调用。"""
        set_stream(monkeypatch, True)
        resp = ndjson_response(["a", "b", "c", "d"])
        mock_post.return_value = resp
        engine, _ = make_engine()
        seen = []

        def on_token(delta):
            seen.append(delta)
            if len(seen) == 2:
                engine.stop()

        out = engine._call_model([{"role": "user", "content": "q"}], on_token=on_token)
        assert seen == ["a", "b"]
        assert out == "ab"
        assert resp.close.call_count >= 1
        assert engine._active_response is None

    @patch("react_engine.requests.post")
    def test_stop_closes_active_response_immediately(self, mock_post, monkeypatch):
        """stop() 在读取过程中直接关闭底层响应（模拟另一线程点停止）。"""
        set_stream(monkeypatch, True)
        engine, _ = make_engine()
        resp = MagicMock()

        def lines():
            yield json.dumps({"message": {"content": "x"}, "done": False}).encode()
            # 另一线程调用 stop()：应关闭 resp；随后底层读错误被按中断吞掉
            engine.stop()
            assert resp.close.called
            raise ConnectionResetError("closed")

        resp.iter_lines.return_value = lines()
        mock_post.return_value = resp
        out = engine._call_model([{"role": "user", "content": "q"}], on_token=lambda d: None)
        assert out == "x"

    @patch("react_engine.requests.post")
    def test_stream_error_line_returns_error(self, mock_post, monkeypatch):
        set_stream(monkeypatch, True)
        mock_post.return_value = ndjson_response(["部分"], error="model not found")
        engine, _ = make_engine()
        out = engine._call_model([{"role": "user", "content": "q"}], on_token=lambda d: None)
        assert out.startswith("[错误]") and "model not found" in out

    @patch("react_engine.requests.post")
    def test_stream_read_error_without_stop_is_reported(self, mock_post, monkeypatch):
        set_stream(monkeypatch, True)
        resp = MagicMock()

        def lines():
            yield json.dumps({"message": {"content": "x"}, "done": False}).encode()
            raise OSError("broken pipe")

        resp.iter_lines.return_value = lines()
        mock_post.return_value = resp
        engine, _ = make_engine()
        out = engine._call_model([{"role": "user", "content": "q"}], on_token=lambda d: None)
        assert out.startswith("[错误]") and "broken pipe" in out
        resp.close.assert_called()

    @patch("react_engine.requests.post")
    def test_stream_ignores_garbage_lines(self, mock_post, monkeypatch):
        set_stream(monkeypatch, True)
        resp = MagicMock()
        resp.iter_lines.return_value = iter([
            b"not json", b"[1,2]",
            json.dumps({"message": {"content": "ok"}, "done": True}).encode(),
        ])
        mock_post.return_value = resp
        engine, _ = make_engine()
        assert engine._call_model([{"role": "user", "content": "q"}], on_token=lambda d: None) == "ok"


# ==================== 引擎层：Final Answer 过滤与 chat 透传 ====================

class TestFinalAnswerStream:
    def test_forwards_only_after_marker(self):
        seen = []
        f = FinalAnswerStream(seen.append)
        for d in ["Thought: 想", "一下\nFinal", " Answer:", " 结果", "A"]:
            f(d)
        assert "".join(seen) == "结果A"
        assert f.forwarded == 2

    def test_action_round_drops_everything(self):
        seen = []
        f = FinalAnswerStream(seen.append)
        for d in ["Thought: x\n", "Action: read_file\n", "Action Input: {}", "Final Answer: 不应出现"]:
            f(d)
        assert seen == []

    def test_empty_delta_ignored(self):
        seen = []
        f = FinalAnswerStream(seen.append)
        f("")
        f("Final Answer: a")
        f("")
        assert seen == ["a"]

    def test_whole_text_single_callback(self):
        """LLM_STREAM=false 的整段回调也能正确抽出 Final Answer。"""
        seen = []
        FinalAnswerStream(seen.append)("Thought: t\nFinal Answer: 完整答案")
        assert seen == ["完整答案"]


class TestChatTokenPassthrough:
    @patch("react_engine.requests.post")
    def test_chat_streams_final_answer_only(self, mock_post, monkeypatch):
        set_stream(monkeypatch, True)
        engine, _ = make_engine()
        mock_post.return_value = ndjson_response(["Thought: 直接回答\n", "Final Answer:", " 答", "案"])
        seen = []
        assert engine.chat("q", on_token=seen.append) == "答案"
        assert seen == ["答", "案"]

    @patch("react_engine.requests.post")
    def test_chat_tool_round_then_final(self, mock_post, monkeypatch):
        """工具调用轮不产生 token，最终轮只流出 Final Answer。"""
        set_stream(monkeypatch, True)
        engine, _ = make_engine(on_token=None)
        r1 = ndjson_response(["Thought: 看目录\n", "Action: list_directory\n", 'Action Input: {"path": "."}'])
        r2 = ndjson_response(["Thought: 够了\nFinal Answer: ", "完成"])
        mock_post.side_effect = [r1, r2]
        seen = []
        with patch.object(react_engine.registry, "execute", return_value="a.py"):
            out = engine.chat("q", on_token=seen.append)
        assert out == "完成"
        assert seen == ["完成"]

    def test_constructor_on_token_used_when_chat_arg_missing(self):
        seen = []
        engine, _ = make_engine(on_token=seen.append)
        with patch.object(engine, "_call_model") as cm:
            def fake(*a, **k):
                k["on_token"]("Final Answer: ok")
                return "Final Answer: ok"
            cm.side_effect = fake
            assert engine.chat("q") == "ok"
        assert seen == ["ok"]
        assert "on_token" in cm.call_args.kwargs

    def test_no_on_token_calls_call_model_without_kwargs(self):
        engine, _ = make_engine()
        with patch.object(engine, "_call_model", return_value="Final Answer: ok") as cm:
            assert engine.chat("q") == "ok"
        assert cm.call_args.kwargs == {}

    @patch("react_engine.requests.post")
    def test_stop_during_stream_returns_interrupted(self, mock_post, monkeypatch):
        set_stream(monkeypatch, True)
        engine, ctx = make_engine()
        resp = ndjson_response(["Final Answer: 半", "截", "文本"])
        mock_post.return_value = resp

        def on_token(delta):
            engine.stop()

        assert engine.chat("q", on_token=on_token) == "[用户中断] 任务已停止。"
        assert ctx.recorded == []

    def test_forced_summary_uses_streaming_wrapper(self):
        engine, _ = make_engine()
        seen = []
        engine._turn_on_token = seen.append
        with patch.object(engine, "_call_model") as cm:
            def fake(*a, **k):
                k["on_token"]("Final Answer: 已完成 1 步")
                return "Final Answer: 已完成 1 步"
            cm.side_effect = fake
            engine._load_context("task")
            out = engine._forced_summary("task", 3, reason="max_iterations")
        assert "已完成 1 步" in out and seen == ["已完成 1 步"]


# ==================== 共享层：llm_helper.complete_text ====================

class TestCompleteTextStreaming:
    @patch("requests.post")
    def test_no_on_token_unchanged(self, mock_post):
        from collaboration.llm_helper import complete_text
        resp = MagicMock()
        resp.json.return_value = {"message": {"content": " x "}}
        mock_post.return_value = resp
        assert complete_text("p") == "x"
        assert mock_post.call_args.kwargs["json"]["stream"] is False
        assert "stream" not in mock_post.call_args.kwargs

    @patch("requests.post")
    def test_streaming_concat(self, mock_post, monkeypatch):
        from collaboration.llm_helper import complete_text
        set_stream(monkeypatch, True)
        mock_post.return_value = ndjson_response(["a", "b", "c"])
        seen = []
        assert complete_text("p", on_token=seen.append) == "abc"
        assert seen == ["a", "b", "c"]
        assert mock_post.call_args.kwargs["json"]["stream"] is True

    @patch("requests.post")
    def test_stream_disabled_single_callback(self, mock_post, monkeypatch):
        from collaboration.llm_helper import complete_text
        set_stream(monkeypatch, False)
        resp = MagicMock()
        resp.json.return_value = {"message": {"content": "full"}}
        mock_post.return_value = resp
        seen = []
        assert complete_text("p", on_token=seen.append) == "full"
        assert seen == ["full"]

    @patch("requests.post")
    def test_should_stop_breaks_and_closes(self, mock_post, monkeypatch):
        from collaboration.llm_helper import complete_text
        set_stream(monkeypatch, True)
        resp = ndjson_response(["a", "b", "c"])
        mock_post.return_value = resp
        flag = {"stop": False}
        seen = []

        def on_token(d):
            seen.append(d)
            flag["stop"] = True

        assert complete_text("p", on_token=on_token, should_stop=lambda: flag["stop"]) == "a"
        assert seen == ["a"]
        resp.close.assert_called()

    def test_abort_response_shuts_down_socket_then_closes(self):
        import socket
        from collaboration.llm_helper import abort_response
        resp = MagicMock()
        abort_response(resp)
        resp.raw._fp.fp.raw._sock.shutdown.assert_called_once_with(socket.SHUT_RDWR)
        resp.close.assert_called_once()

    def test_abort_response_without_socket_still_closes(self):
        from collaboration.llm_helper import abort_response

        class Resp:
            raw = object()
            closed = False

            def close(self):
                self.closed = True

        r = Resp()
        abort_response(r)
        assert r.closed
        abort_response(None)  # 空值安全

    def test_engine_stop_aborts_active_response(self):
        engine, _ = make_engine()
        resp = MagicMock()
        engine._active_response = resp
        engine.stop()
        resp.raw._fp.fp.raw._sock.shutdown.assert_called_once()
        resp.close.assert_called_once()

    def test_consume_stream_error_raises(self):
        from collaboration.llm_helper import consume_ndjson_stream
        resp = ndjson_response(["a"], error="boom")
        with pytest.raises(RuntimeError, match="boom"):
            consume_ndjson_stream(resp, lambda d: None)
        resp.close.assert_called()

    def test_consume_stream_read_error_swallowed_when_stopped(self):
        from collaboration.llm_helper import consume_ndjson_stream
        resp = MagicMock()

        def lines():
            yield json.dumps({"message": {"content": "a"}}).encode()
            raise OSError("closed")

        resp.iter_lines.return_value = lines()
        flag = {"stop": False}

        def on_token(d):
            flag["stop"] = True

        assert consume_ndjson_stream(resp, on_token, should_stop=lambda: flag["stop"]) == "a"


# ==================== 共享层：rag_pipeline 综合阶段 ====================

class TestRagPipelineStreaming:
    @staticmethod
    def _install(monkeypatch, llm):
        """把 ``llama_index.core.Settings.llm`` 替换为桩（沿用 test_rag_pipeline 的 sys.modules 手法）。"""
        import sys
        import types
        monkeypatch.setitem(sys.modules, "llama_index.core",
                            types.SimpleNamespace(Settings=types.SimpleNamespace(llm=llm)))

    def _fake_llm(self, deltas, thinking=""):
        class Block:
            block_type = "thinking"

            def __init__(self, content):
                self.content = content

        class Msg:
            def __init__(self):
                self.blocks = [Block(thinking)] if thinking else []

        class Chunk:
            def __init__(self, delta):
                self.delta = delta
                self.message = Msg()
                self.raw = {}
                self.additional_kwargs = {}

        class LLM:
            closed = False
            complete_calls = 0

            def stream_chat(self, messages):
                assert len(messages) == 1
                llm = self

                def gen():
                    try:
                        for d in deltas:
                            yield Chunk(d)
                    finally:
                        llm.closed = True

                return gen()

            def complete(self, prompt):
                self.complete_calls += 1
                return "非流式"

        return LLM()

    def test_complete_streams_via_stream_chat(self, monkeypatch):
        import rag_pipeline
        set_stream(monkeypatch, True)
        llm = self._fake_llm(["你", "好"])
        self._install(monkeypatch, llm)
        seen = []
        assert rag_pipeline._complete("p", on_token=seen.append) == "你好"
        assert seen == ["你", "好"]
        assert llm.closed and llm.complete_calls == 0

    def test_complete_without_on_token_uses_complete(self, monkeypatch):
        import rag_pipeline
        llm = self._fake_llm(["x"])
        self._install(monkeypatch, llm)
        assert rag_pipeline._complete("p") == "非流式"
        assert llm.complete_calls == 1

    def test_complete_stream_disabled_single_callback(self, monkeypatch):
        import rag_pipeline
        set_stream(monkeypatch, False)
        llm = self._fake_llm(["x"])
        self._install(monkeypatch, llm)
        seen = []
        assert rag_pipeline._complete("p", on_token=seen.append) == "非流式"
        assert seen == ["非流式"]

    def test_stream_should_stop_breaks_and_closes(self, monkeypatch):
        import rag_pipeline
        set_stream(monkeypatch, True)
        llm = self._fake_llm(["a", "b", "c"])
        self._install(monkeypatch, llm)
        flag = {"stop": False}
        seen = []

        def on_token(d):
            seen.append(d)
            flag["stop"] = True

        assert rag_pipeline._complete("p", on_token=on_token, should_stop=lambda: flag["stop"]) == "a"
        assert seen == ["a"] and llm.closed

    def test_stream_emits_thinking_from_last_chunk(self, monkeypatch):
        import rag_pipeline
        set_stream(monkeypatch, True)
        llm = self._fake_llm(["答"], thinking="思路")
        self._install(monkeypatch, llm)
        events = []
        token = rag_pipeline._THINKING_SINK.set(lambda e: events.append(e))
        try:
            rag_pipeline._complete("p", on_token=lambda d: None)
        finally:
            rag_pipeline._THINKING_SINK.reset(token)
        assert any(e.get("stage") == "thinking" and "思路" in e.get("message", "") for e in events)

    def test_llm_without_stream_chat_falls_back(self, monkeypatch):
        import rag_pipeline
        set_stream(monkeypatch, True)

        class Plain:
            def complete(self, prompt):
                return "plain"

        self._install(monkeypatch, Plain())
        seen = []
        assert rag_pipeline._complete("p", on_token=seen.append) == "plain"
        assert seen == ["plain"]

    def test_llm_direct_answer_passthrough(self, monkeypatch):
        import rag_pipeline
        calls = []

        def fake_complete(prompt, on_token=None, should_stop=None):
            calls.append((on_token is not None, should_stop is not None))
            return "ok"

        monkeypatch.setattr(rag_pipeline, "_complete", fake_complete)
        assert rag_pipeline.llm_direct_answer("p") == "ok"
        assert rag_pipeline.llm_direct_answer("p", on_token=lambda d: None, should_stop=lambda: False) == "ok"
        assert calls == [(False, False), (True, True)]

    def test_answer_question_forwards_on_token_to_synthesis(self, monkeypatch):
        """answer_question(on_token=) 只在最终综合调用上生效，且 prompt 为综合 prompt。"""
        import rag_pipeline
        seen = {}

        def fake_direct(prompt, on_token=None, should_stop=None):
            seen["on_token"] = on_token
            on_token("综合")
            return "综合"

        monkeypatch.setattr(rag_pipeline, "llm_direct_answer", fake_direct)
        monkeypatch.setattr(rag_pipeline, "kb_ready", lambda e: False)
        monkeypatch.setattr(rag_pipeline, "plan_retrieval", lambda q, progress=None: {"complex": False})
        tokens = []

        def sink(d):
            tokens.append(d)

        out = rag_pipeline.answer_question(MagicMock(), "问题", enable_web_search=False, on_token=sink)
        assert out["answer"] == "综合"
        assert tokens == ["综合"] and seen["on_token"] is sink

    def test_answer_question_without_on_token_calls_single_arg(self, monkeypatch):
        """无 on_token 时综合调用保持单参形态（现有 lambda p: 桩全部兼容）。"""
        import rag_pipeline
        monkeypatch.setattr(rag_pipeline, "llm_direct_answer", lambda p: "单参")
        monkeypatch.setattr(rag_pipeline, "kb_ready", lambda e: False)
        monkeypatch.setattr(rag_pipeline, "plan_retrieval", lambda q, progress=None: {"complex": False})
        out = rag_pipeline.answer_question(MagicMock(), "问题", enable_web_search=False)
        assert out["answer"] == "单参"


# ==================== 多 Agent：整合阶段透传 ====================

class TestMultiAgentIntegrationStreaming:
    def test_result_integrator_uses_on_token(self, monkeypatch):
        from collaboration import result_integrator as ri
        from agents.agent_types import AgentResult

        calls = {}

        def fake_complete_text(prompt, num_predict=512, timeout=None, on_token=None, **kw):
            calls["on_token"] = on_token
            if on_token:
                on_token("综合")
            return "综合"

        monkeypatch.setattr(ri, "complete_text", fake_complete_text)
        integ = ri.ResultIntegrator(use_llm=True)
        tokens = []

        def sink(d):
            tokens.append(d)

        integ.on_token = sink
        results = [
            AgentResult(task_id="1", agent_id="a", success=True, output="x", metadata={}, execution_time=0.1),
            AgentResult(task_id="2", agent_id="b", success=True, output="y", metadata={}, execution_time=0.1),
        ]
        out = integ.integrate(results, request="r")
        assert out["answer"] == "综合" and tokens == ["综合"]
        assert calls["on_token"] is sink

    def test_result_integrator_without_on_token_unchanged(self, monkeypatch):
        from collaboration import result_integrator as ri
        from agents.agent_types import AgentResult

        def fake_complete_text(prompt, num_predict=512, timeout=None):
            return "综合"

        monkeypatch.setattr(ri, "complete_text", fake_complete_text)
        integ = ri.ResultIntegrator(use_llm=True)
        results = [
            AgentResult(task_id="1", agent_id="a", success=True, output="x", metadata={}, execution_time=0.1),
            AgentResult(task_id="2", agent_id="b", success=True, output="y", metadata={}, execution_time=0.1),
        ]
        assert integ.integrate(results, request="r")["answer"] == "综合"

    def test_master_agent_injects_and_resets_on_token(self):
        from master_agent import MasterAgent
        from agents.agent_types import CollaborationMode

        master = MasterAgent()
        master.task_decomposer = MagicMock()
        master.task_decomposer.decompose.return_value = []  # 无子任务 → 早退，但注入已发生
        seen = {}
        original = master.result_integrator

        class Spy:
            on_token = None

            def __setattr__(self, k, v):
                if k == "on_token" and v is not None:
                    seen["set"] = v
                object.__setattr__(self, k, v)

        master.result_integrator = Spy()
        sink = lambda d: None  # noqa: E731
        master.coordinate_task("r", CollaborationMode.HIERARCHY, on_token=sink)
        assert seen["set"] is sink
        assert master.result_integrator.on_token is None  # finally 复位
        master.result_integrator = original

    def test_orchestrator_forwards_on_token(self):
        from agent_config import AgentConfigManager
        from agent_orchestrator import AgentOrchestrator

        orch = AgentOrchestrator(AgentConfigManager.get_default_config())
        orch.master_agent = MagicMock()
        orch.master_agent.coordinate_task.return_value = {"success": True}
        sink = lambda d: None  # noqa: E731
        orch.process_request("r", on_token=sink)
        assert orch.master_agent.coordinate_task.call_args.kwargs["on_token"] is sink
        orch.process_request("r")
        assert "on_token" not in orch.master_agent.coordinate_task.call_args.kwargs
        orch.shutdown()


# ==================== Web 服务层 ====================

class TestWebServiceTokenEvents:
    def _svc(self, **kw):
        from tests.test_web_services import make_service
        return make_service(**kw)

    def test_agent_chat_stream_tokens_then_answer_done(self):
        from tests.test_web_services import FakeReact

        class Streaming(FakeReact):
            def chat(self, user_input, on_token=None):
                for d in ["你", "好", "！"]:
                    on_token(d)
                return "你好！"

        svc = self._svc(react_factory=lambda on_step=None, on_confirm=None, context=None: Streaming(
            on_step=on_step, on_confirm=on_confirm, context=context))
        svc.heartbeat_interval = 5.0
        events = list(svc.agent_chat_stream("q"))
        kinds = [e.kind for e in events]
        tokens = [e.message for e in events if e.kind == "token"]
        assert tokens == ["你", "好", "！"]
        assert kinds.count("token") >= 2
        assert kinds.index("answer") > kinds.index("token")
        assert events[-1].kind == "answer" and events[-1].message == "你好！"
        assert "heartbeat" not in kinds

    def test_tokens_after_cancel_are_dropped(self):
        from tests.test_web_services import FakeReact

        class Streaming(FakeReact):
            def chat(self, user_input, on_token=None):
                on_token("a")
                svc.stop_current()
                on_token("b")  # 取消后应被丢弃
                return "ab"

        svc = self._svc(react_factory=lambda on_step=None, on_confirm=None, context=None: Streaming(
            on_step=on_step, on_confirm=on_confirm, context=context))
        events = list(svc.agent_chat_stream("q"))
        tokens = [e.message for e in events if e.kind == "token"]
        assert tokens == ["a"]
        assert events[-1].kind == "cancelled"

    def test_rag_stream_emits_tokens(self, monkeypatch):
        import rag_pipeline

        def fake_answer_question(engine, question, **kwargs):
            for d in ["答", "案"]:
                kwargs["on_token"](d)
            return {"kind": "answer", "answer": "答案", "kb_sources": [], "web_sources": [],
                    "meta": None, "rewritten": None, "notices": [], "citation_check": None, "model": "m"}

        monkeypatch.setattr(rag_pipeline, "answer_question", fake_answer_question)
        svc = self._svc()
        events = list(svc.rag_query_stream("q", enable_web_search=False))
        assert [e.message for e in events if e.kind == "token"] == ["答", "案"]
        assert events[-1].kind == "answer" and events[-1].message == "答案"

    def test_multi_agent_stream_emits_tokens(self):
        orch = MagicMock()

        def fake_process(request, mode, progress=None, context=None, on_token=None):
            on_token("综")
            on_token("合")
            return {"success": True, "summary": "ok", "answer": "综合", "results": []}

        orch.process_request.side_effect = fake_process
        svc = self._svc(orchestrator_factory=lambda: orch)
        events = list(svc.multi_agent_stream("r"))
        assert [e.message for e in events if e.kind == "token"] == ["综", "合"]
        assert events[-1].kind == "answer" and events[-1].message == "综合"

    def test_auto_stream_passes_tokens_through(self, monkeypatch):
        from tests.test_web_services import FakeReact

        class Streaming(FakeReact):
            def chat(self, user_input, on_token=None):
                on_token("x")
                return "x"

        svc = self._svc(react_factory=lambda on_step=None, on_confirm=None, context=None: Streaming(
            on_step=on_step, on_confirm=on_confirm, context=context))
        monkeypatch.setattr(svc, "classify_intent", lambda m: ("agent", "测试"))
        events = list(svc.chat_auto_stream("修改 a.py", auto_confirm=True))
        assert any(e.kind == "token" and e.message == "x" for e in events)
        assert events[-1].kind == "answer" and events[-1].data["routed_mode"] == "agent"

    def test_token_sink_ignores_empty(self):
        import queue
        import threading
        from web.services import WebService
        q = queue.Queue()
        sink = WebService._token_sink(q, threading.Event())
        sink("")
        sink("a")
        assert q.qsize() == 1 and q.get().kind == "token"


# ==================== Web 呈现层 ====================

class TestWebAppTokenRendering:
    def _handlers(self, events):
        from web.app import build_handlers
        from web.services import StreamEvent

        svc = MagicMock()
        svc.is_running.return_value = False
        svc.ensure_session.return_value = "sid"
        svc.chat_history.return_value = []
        svc.current_model.return_value = {"model": "m", "think": False}
        svc.agent_chat_stream.return_value = iter([StreamEvent(*e) for e in events])
        svc.rag_query_stream.return_value = iter([StreamEvent(*e) for e in events])
        svc.context_status.return_value = {}
        return build_handlers(svc)

    def test_tokens_appended_incrementally_then_replaced_by_answer(self):
        handlers = self._handlers([
            ("step", "Step 1", {"phase": "thinking", "step": 1, "total": 3}),
            ("token", "你", None),
            ("token", "好", None),
            ("answer", "你好！", {"step_log": [], "context": {}}),
        ])
        frames = list(handlers["on_chat_stream"]("q", "单 Agent", True, True, "sid"))
        bubbles = [f[0][-1]["content"] for f in frames if f[0] and f[0][-1]["role"] == "assistant"]
        assert bubbles[:2] == ["你", "你好"]
        assert bubbles[-1] == "你好！"
        # 生成中状态行
        assert any("生成回答中" in f[1] for f in frames)

    def test_new_round_resets_partial(self):
        handlers = self._handlers([
            ("token", "半截", None),
            ("step", "Step 2", {"phase": "thinking", "step": 2, "total": 3}),
            ("token", "重来", None),
            ("answer", "重来", {"step_log": [], "context": {}}),
        ])
        frames = list(handlers["on_chat_stream"]("q", "单 Agent", True, True, "sid"))
        bubbles = [f[0][-1]["content"] for f in frames if f[0] and f[0][-1]["role"] == "assistant"]
        assert "半截" in bubbles and "半截重来" not in bubbles and bubbles[-1] == "重来"

    def test_transient_thinking_does_not_reset_partial(self):
        handlers = self._handlers([
            ("token", "a", None),
            ("step", "模型推理中.", {"phase": "thinking", "transient": True}),
            ("token", "b", None),
            ("answer", "ab", {"step_log": [], "context": {}}),
        ])
        frames = list(handlers["on_chat_stream"]("q", "单 Agent", True, True, "sid"))
        bubbles = [f[0][-1]["content"] for f in frames if f[0] and f[0][-1]["role"] == "assistant"]
        assert "ab" in bubbles
        # 心跳不覆盖「生成回答中」状态
        assert all("模型推理中" not in f[1] for f in frames)

    def test_cancelled_keeps_partial_with_note(self):
        handlers = self._handlers([
            ("token", "部分", None),
            ("cancelled", "已停止", {}),
        ])
        frames = list(handlers["on_chat_stream"]("q", "RAG 检索", True, False, "sid"))
        last = frames[-1]
        assert last[0][-1]["role"] == "assistant" and "部分" in last[0][-1]["content"]
        assert "已停止" in last[0][-1]["content"] and "已停止" in last[1]

    def test_starts_new_round_helper(self):
        from web.app import _starts_new_round
        assert _starts_new_round("step", {"phase": "thinking"})
        assert not _starts_new_round("step", {"phase": "thinking", "transient": True})
        assert not _starts_new_round("progress", {"phase": "thinking"})
        assert not _starts_new_round("step", None)
        assert not _starts_new_round("step", {"phase": "executing"})


# ==================== CLI ====================

class TestLiveAnswer:
    def _console(self):
        from io import StringIO
        from rich.console import Console
        return Console(file=StringIO(), force_terminal=False, width=60)

    def test_no_rich_is_noop(self):
        from cli_handlers import LiveAnswer
        live = LiveAnswer(MagicMock(), has_rich=False)
        live.on_token("x")
        assert live.buffer == "" and live.finish() is False and not live.active

    def test_live_starts_on_first_token_and_finishes(self):
        from cli_handlers import LiveAnswer
        live = LiveAnswer(self._console(), has_rich=True, title="T")
        assert not LiveAnswer.streaming()
        live.on_token("你")
        assert live.active and LiveAnswer.streaming()
        live.on_token("好")
        assert live.buffer == "你好" and live.tokens == 2
        assert live.finish() is True
        assert not live.active and not LiveAnswer.streaming()
        assert live.finish() is True  # 幂等

    def test_render_failure_stops_live_quietly(self):
        from cli_handlers import LiveAnswer
        live = LiveAnswer(self._console(), has_rich=True)
        live.on_token("a")
        live._live.update = MagicMock(side_effect=RuntimeError("x"))
        live.on_token("b")
        assert not live.active and live.buffer == "ab"

    def test_empty_delta_ignored(self):
        from cli_handlers import LiveAnswer
        live = LiveAnswer(self._console(), has_rich=True)
        live.on_token("")
        assert not live.active


class TestCliStreamingWiring:
    def test_run_ask_passes_on_token_and_handles_ctrl_c(self, monkeypatch):
        import query_interface as qi
        import rag_pipeline
        from tests.test_cli_handlers_context import _cli_ctx

        seen = {}

        def fake_answer(engine, question, **kwargs):
            seen["on_token"] = kwargs.get("on_token")
            raise KeyboardInterrupt

        monkeypatch.setattr(rag_pipeline, "answer_question", fake_answer)
        monkeypatch.setattr(qi, "_health_before", lambda q: {})
        monkeypatch.setattr(qi, "_conversation", lambda: None)
        ctx = _cli_ctx()
        printed = []
        monkeypatch.setattr(qi, "console", MagicMock(print=lambda *a, **k: printed.append(str(a[0]) if a else "")))
        assert qi._run_ask(ctx, "问题") is False
        assert callable(seen["on_token"])
        assert any("已中断" in p for p in printed)

    def test_handle_agent_sets_engine_on_token_and_restores(self, monkeypatch):
        import query_interface as qi
        from tests.test_cli_handlers_context import _cli_ctx

        engine = MagicMock()
        engine.on_token = None
        engine.step_log = []
        state = {}

        def chat(task):
            state["sink"] = engine.on_token
            return "完成"

        engine.chat.side_effect = chat
        monkeypatch.setattr(qi, "_health_before", lambda q: {})
        monkeypatch.setattr(qi, "_print_health_hint", lambda *a, **k: None)
        monkeypatch.setattr(qi, "record_command_execution", lambda *a, **k: None)
        monkeypatch.setattr(qi, "console", MagicMock())
        from query_interface import ParsedCommand
        assert qi.handle_agent(_cli_ctx(react_engine=engine), ParsedCommand("agent", "/agent 做事", "做事")) is True
        engine.chat.assert_called_once_with("做事")
        assert callable(state["sink"])
        assert engine.on_token is None  # 结束后恢复

    def test_handle_agent_ctrl_c_stops_engine(self, monkeypatch):
        import query_interface as qi
        from tests.test_cli_handlers_context import _cli_ctx

        engine = MagicMock()
        engine.chat.side_effect = KeyboardInterrupt
        monkeypatch.setattr(qi, "_health_before", lambda q: {})
        printed = []
        monkeypatch.setattr(qi, "console", MagicMock(print=lambda *a, **k: printed.append(str(a[0]) if a else "")))
        from query_interface import ParsedCommand
        assert qi.handle_agent(_cli_ctx(react_engine=engine), ParsedCommand("agent", "/agent x", "x")) is False
        engine.stop.assert_called_once()
        assert any("已中断" in p for p in printed)

    def test_on_step_callback_silences_heartbeat_while_streaming(self, monkeypatch):
        import query_interface as qi
        from cli_handlers import LiveAnswer

        monkeypatch.setattr(qi.Config, "SHOW_PROGRESS", True)
        printed = []
        monkeypatch.setattr(qi, "console", MagicMock(print=lambda *a, **k: printed.append(a)))
        monkeypatch.setattr(LiveAnswer, "streaming", classmethod(lambda cls: True))
        qi.on_step_callback({"step": "?", "total": "?", "phase": "thinking", "transient": True, "message": "模型推理中."})
        assert printed == []
        qi.on_step_callback({"step": 1, "total": 3, "phase": "executing", "message": "执行 read_file"})
        assert printed

    def test_handle_multi_passes_on_token(self):
        from cli_handlers import handle_multi
        from tests.test_cli_handlers_multi import _ctx, _Orch

        seen = {}

        class Orch(_Orch):
            def process_request(self, request, mode, progress=None, context=None, on_token=None):
                seen["on_token"] = on_token
                return super().process_request(request, mode, progress=progress, context=context)

        ctx = _ctx(factory=lambda: Orch())
        parsed = MagicMock(arg="做事")
        assert handle_multi(ctx, parsed) is True
        assert callable(seen["on_token"])

    def test_help_and_tutorial_mention_streaming(self):
        import query_interface as qi
        assert "LLM_STREAM" in qi.TUTORIAL_TEXT and "流式" in qi.TUTORIAL_TEXT
        import inspect
        assert "流式" in inspect.getsource(qi.print_help)


class TestConfigStream:
    def test_default_true(self):
        import config
        assert config.LLM_STREAM is True and config.Config.LLM_STREAM is True

    def test_env_false_parsed_in_fresh_module(self, monkeypatch):
        """把 config.py 作为独立模块对象重新执行（不 reload 全局 config，避免污染 Config 类对象）。"""
        import importlib.util
        import os
        monkeypatch.setenv("LLM_STREAM", "false")
        src = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src", "config.py")
        spec = importlib.util.spec_from_file_location("_config_fresh_for_stream_test", src)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        assert mod.LLM_STREAM is False and mod.Config.LLM_STREAM is False
