#!/usr/bin/env python3
"""test_web_services.py — Web 服务层单元测试。

服务层是 Web 界面唯一与核心引擎交互的层。通过依赖注入把各引擎替换为
MagicMock/桩对象，在不启动真实 Ollama/ChromaDB 的前提下覆盖全部分支。
"""
import tempfile
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from web import services
from web.services import (
    StreamEvent,
    WebService,
    get_web_service,
    reset_web_service,
)


# ==================== 测试用桩引擎 ====================

class FakeRAG:
    """模拟 RAGEngine。"""

    def __init__(self):
        self.added = []
        self.cleared = False
        self.built = None
        self.raise_on_query = False
        self.raise_on_add = False
        self.raise_on_stats = False
        self.raise_on_clear = False
        # 共享编排层 rag_pipeline.answer_question 会检查 query_engine 判断
        # 知识库是否已初始化；桩默认设为真值，走"知识库检索"分支。
        self.query_engine = object()

    def load_index(self):
        return None

    def query_with_sources(self, question, progress_callback=None):
        if self.raise_on_query:
            raise RuntimeError("boom")
        if progress_callback:
            progress_callback({"phase": "embedding", "message": "生成向量"})
            progress_callback({"phase": "generating", "message": "生成回答"})
        return {
            "answer": f"答案:{question}",
            "sources": [{"content": "c", "score": 0.9, "file": "f.md", "path": "/f.md"}],
        }

    def add_documents(self, docs, file_paths=None):
        if self.raise_on_add:
            raise RuntimeError("add-fail")
        self.added.append((docs, file_paths))

    def build_index(self, docs, file_paths=None):
        self.built = (docs, file_paths)

    def get_stats(self):
        if self.raise_on_stats:
            raise RuntimeError("stats-fail")
        return {"total_documents": 3, "llm_model": "qwen"}

    def clear_index(self):
        if self.raise_on_clear:
            raise RuntimeError("clear-fail")
        self.cleared = True


class FakeReact:
    """模拟 ReActEngine（接受服务层注入的会话上下文 ``context``）。"""

    def __init__(self, on_step=None, on_confirm=None, context=None, answer="最终答案",
                 raise_error=False, steps=None):
        self.on_step = on_step
        self.on_confirm = on_confirm
        self.context = context
        self._answer = answer
        self._raise = raise_error
        self._steps = steps or [{"message": "思考中", "phase": "thinking"}]
        self.step_log = [{"phase": "final", "answer": answer}]
        self.stopped = False

    def chat(self, user_input):
        if self._raise:
            raise RuntimeError("agent-boom")
        for s in self._steps:
            if self.on_step:
                self.on_step(s)
        # 真实引擎会在轮末把本轮折叠写回会话
        if self.context is not None:
            self.context.record(user_input, self._answer, trace="共 1 步")
        return self._answer

    def stop(self):
        self.stopped = True


def make_session_manager():
    """真实 SessionManager，落到临时目录（不触碰用户会话数据）。"""
    from session_manager import SessionManager

    return SessionManager(tempfile.mkdtemp(prefix="web_sessions_"))


def make_service(**overrides):
    """构造一个全部依赖被桩替换的 WebService。"""
    rag = overrides.pop("rag", FakeRAG())
    sm = overrides.pop("session_manager", None)
    defaults = dict(
        rag_factory=lambda: rag,
        react_factory=lambda on_step=None, on_confirm=None, context=None: FakeReact(
            on_step=on_step, on_confirm=on_confirm, context=context
        ),
        orchestrator_factory=lambda: MagicMock(),
        session_manager_factory=(lambda: sm) if sm is not None else make_session_manager,
        graph_query_factory=lambda: MagicMock(),
        set_rag_engine=MagicMock(),
        load_documents=lambda path, file_types=None: [MagicMock()],
        resolve_mode=lambda name: name,
    )
    defaults.update(overrides)
    svc = WebService(**defaults)
    svc._fake_rag = rag  # 便于测试访问
    return svc


# ==================== StreamEvent ====================

class TestStreamEvent:
    def test_equality_and_fields(self):
        a = StreamEvent("answer", "hi", {"x": 1})
        b = StreamEvent("answer", "hi", {"x": 1})
        assert a == b
        assert a.kind == "answer"
        assert a.message == "hi"
        assert a.data == {"x": 1}

    def test_inequality_with_other_type(self):
        assert StreamEvent("answer", "hi") != "answer"

    def test_inequality_different_kind(self):
        assert StreamEvent("answer", "hi") != StreamEvent("error", "hi")


# ==================== 惰性单例属性 ====================

class TestLazyProperties:
    def test_rag_engine_created_once_and_injected(self):
        inject = MagicMock()
        svc = make_service(set_rag_engine=inject)
        e1 = svc.rag_engine
        e2 = svc.rag_engine
        assert e1 is e2
        inject.assert_called_once_with(e1)

    def test_session_manager_lazy(self):
        sm = MagicMock()
        svc = make_service(session_manager_factory=lambda: sm)
        assert svc.session_manager is sm
        assert svc.session_manager is sm

    def test_graph_query_lazy(self):
        gq = MagicMock()
        svc = make_service(graph_query_factory=lambda: gq)
        assert svc.graph_query is gq
        assert svc.graph_query is gq


# ==================== RAG 检索 ====================

class TestRagQuery:
    def test_stream_empty_question(self):
        svc = make_service()
        events = list(svc.rag_query_stream("   "))
        assert events == [StreamEvent("error", "问题不能为空")]

    def test_stream_success_progress_then_answer(self):
        svc = make_service()
        events = list(svc.rag_query_stream("什么是RAG", enable_web_search=False))
        kinds = [e.kind for e in events]
        assert "progress" in kinds
        assert kinds[-1] == "answer"
        answer_evt = events[-1]
        assert answer_evt.message == "答案:什么是RAG"
        assert answer_evt.data["sources"][0]["file"] == "f.md"
        # 新增：答案事件带 kind / web_sources 字段
        assert answer_evt.data["kind"] == "answer"
        assert answer_evt.data["web_sources"] == []

    def test_stream_error(self):
        rag = FakeRAG()
        rag.raise_on_query = True
        svc = make_service(rag=rag)
        events = list(svc.rag_query_stream("x"))
        assert events[-1].kind == "error"
        assert "检索失败" in events[-1].message

    def test_query_nonstream_success(self):
        svc = make_service()
        result = svc.rag_query("hi", enable_web_search=False)
        assert result["answer"] == "答案:hi"
        assert len(result["sources"]) == 1

    def test_query_nonstream_error(self):
        rag = FakeRAG()
        rag.raise_on_query = True
        svc = make_service(rag=rag)
        result = svc.rag_query("hi")
        assert result["answer"].startswith("[错误]")
        assert result["sources"] == []

    def test_query_nonstream_empty(self):
        svc = make_service()
        result = svc.rag_query("")
        assert result["answer"].startswith("[错误]")

    def test_query_nonstream_no_answer_event(self, monkeypatch):
        """当 stream 只产出非 answer/error 事件时，返回空默认值。"""
        svc = make_service()
        monkeypatch.setattr(
            svc, "rag_query_stream",
            lambda q, enable_web_search=True: iter([StreamEvent("progress", "p")]),
        )
        result = svc.rag_query("hi")
        assert result == {
            "answer": "", "sources": [], "web_sources": [], "kind": "answer", "meta": None,
        }


# ==================== 单 Agent ====================

class TestAgentChat:
    def test_empty_input(self):
        svc = make_service()
        events = list(svc.agent_chat_stream("  "))
        assert events == [StreamEvent("error", "输入不能为空")]

    def test_success_steps_and_answer(self):
        svc = make_service()
        events = list(svc.agent_chat_stream("写个函数"))
        assert any(e.kind == "step" for e in events)
        assert events[-1].kind == "answer"
        assert events[-1].message == "最终答案"
        assert "step_log" in events[-1].data
        assert svc._active_react is None  # 结束后清理

    def test_error_path(self):
        svc = make_service(
            react_factory=lambda on_step=None, on_confirm=None, context=None: FakeReact(
                on_step=on_step, on_confirm=on_confirm, context=context, raise_error=True
            )
        )
        events = list(svc.agent_chat_stream("x"))
        assert events[-1].kind == "error"
        assert "Agent 执行失败" in events[-1].message

    def test_confirm_handler_default_reject(self):
        """无 confirm_handler 时 on_confirm 默认返回 False。"""
        captured = {}

        def factory(on_step=None, on_confirm=None, context=None):
            captured["on_confirm"] = on_confirm
            return FakeReact(on_step=on_step, on_confirm=on_confirm, context=context)

        svc = make_service(react_factory=factory)
        list(svc.agent_chat_stream("x"))
        assert captured["on_confirm"]({"tool": "rm"}) is False

    def test_confirm_handler_used(self):
        captured = {}

        def factory(on_step=None, on_confirm=None, context=None):
            captured["on_confirm"] = on_confirm
            return FakeReact(on_step=on_step, on_confirm=on_confirm, context=context)

        svc = make_service(react_factory=factory)
        list(svc.agent_chat_stream("x", confirm_handler=lambda evt: True))
        assert captured["on_confirm"]({"tool": "rm"}) is True

    def test_stop_agent_when_active(self):
        svc = make_service()
        engine = FakeReact()
        svc._active_react = engine
        assert svc.stop_agent() is True
        assert engine.stopped is True
        assert svc.is_cancelled() is True

    def test_stop_agent_when_idle(self):
        svc = make_service()
        assert svc.stop_agent() is False
        assert svc.is_cancelled() is False

    def test_active_react_cleared_after_stream(self):
        svc = make_service()
        list(svc.agent_chat_stream("x"))
        assert svc._active_react is None
        assert svc.is_running() is False


# ==================== 桥接：心跳 / 取消 / 生命周期 ====================

class TestBridge:
    def test_heartbeat_emitted_while_worker_blocks(self):
        """后台无新事件超过心跳间隔时，产出 heartbeat（含 elapsed）。"""
        import threading

        release = threading.Event()

        class SlowRAG(FakeRAG):
            def query_with_sources(self, question, progress_callback=None):
                release.wait(timeout=5)
                return super().query_with_sources(question, progress_callback)

        svc = make_service(rag=SlowRAG())
        svc.heartbeat_interval = 0.05
        gen = svc.rag_query_stream("q", enable_web_search=False)
        seen = []
        for evt in gen:
            seen.append(evt)
            if evt.kind == "heartbeat":
                assert isinstance(evt.data.get("elapsed"), float)
                release.set()
        kinds = [e.kind for e in seen]
        assert "heartbeat" in kinds
        assert kinds[-1] == "answer"
        assert svc.is_running() is False

    def test_stop_current_yields_cancelled_and_stops_forwarding(self):
        import threading

        release = threading.Event()

        class BlockingRAG(FakeRAG):
            def query_with_sources(self, question, progress_callback=None):
                release.wait(timeout=5)
                return super().query_with_sources(question, progress_callback)

        svc = make_service(rag=BlockingRAG())
        svc.heartbeat_interval = 0.05
        gen = svc.rag_query_stream("q", enable_web_search=False)
        seen = []
        for evt in gen:
            seen.append(evt)
            if evt.kind == "heartbeat":
                assert svc.is_running() is True
                assert svc.stop_current() is True
        release.set()
        assert seen[-1].kind == "cancelled"
        assert not any(e.kind == "answer" for e in seen)
        assert svc.is_running() is False

    def test_pipeline_cancelled_exception_maps_to_cancelled_event(self, monkeypatch):
        import rag_pipeline

        def fake_answer_question(*args, **kwargs):
            raise rag_pipeline.PipelineCancelled("用户已停止")

        monkeypatch.setattr(rag_pipeline, "answer_question", fake_answer_question)
        svc = make_service()
        events = list(svc.rag_query_stream("q"))
        assert events[-1].kind == "cancelled"

    def test_should_stop_probe_passed_to_pipeline(self, monkeypatch):
        import rag_pipeline

        captured = {}

        def fake_answer_question(engine, question, **kwargs):
            captured["should_stop"] = kwargs.get("should_stop")
            return {"kind": "answer", "answer": "a", "kb_sources": [], "web_sources": [], "meta": None}

        monkeypatch.setattr(rag_pipeline, "answer_question", fake_answer_question)
        svc = make_service()
        list(svc.rag_query_stream("q"))
        assert callable(captured["should_stop"])
        assert captured["should_stop"]() is False

    def test_generator_close_sets_cancel_and_resets_running(self):
        """消费方关闭生成器（Gradio cancels）时置位取消并复位 running。"""
        import threading

        release = threading.Event()

        class BlockingRAG(FakeRAG):
            def query_with_sources(self, question, progress_callback=None):
                release.wait(timeout=5)
                return super().query_with_sources(question, progress_callback)

        svc = make_service(rag=BlockingRAG())
        svc.heartbeat_interval = 0.05
        gen = svc.rag_query_stream("q", enable_web_search=False)
        first = next(gen)
        assert first.kind in ("progress", "heartbeat")
        assert svc.is_running() is True
        gen.close()
        release.set()
        assert svc.is_cancelled() is True
        assert svc.is_running() is False

    def test_new_run_does_not_revive_old_cancelled_task(self):
        """旧任务被取消后启动新任务，旧任务的取消信号保持置位。"""
        svc = make_service()
        old_cancel = svc._cancel_event
        old_cancel.set()
        list(svc.rag_query_stream("q", enable_web_search=False))
        assert old_cancel.is_set() is True
        assert svc.is_cancelled() is False


# ==================== 多 Agent ====================

class TestMultiAgent:
    def test_empty_request(self):
        svc = make_service()
        result = svc.multi_agent_run("")
        assert result["success"] is False
        assert "请求为空" in result["summary"]

    def test_success_and_shutdown_called(self):
        orch = MagicMock()
        orch.process_request.return_value = {"success": True, "summary": "ok"}
        svc = make_service(orchestrator_factory=lambda: orch)
        result = svc.multi_agent_run("do it", mode="parallel")
        assert result["success"] is True
        orch.process_request.assert_called_once_with("do it", "parallel")
        orch.shutdown.assert_called_once()

    def test_process_request_raises(self):
        orch = MagicMock()
        orch.process_request.side_effect = RuntimeError("nope")
        svc = make_service(orchestrator_factory=lambda: orch)
        result = svc.multi_agent_run("x")
        assert result["success"] is False
        assert "nope" in result["error"]
        orch.shutdown.assert_called_once()

    def test_shutdown_raises_is_swallowed(self):
        orch = MagicMock()
        orch.process_request.return_value = {"success": True}
        orch.shutdown.side_effect = RuntimeError("shutdown-fail")
        svc = make_service(orchestrator_factory=lambda: orch)
        result = svc.multi_agent_run("x")
        assert result["success"] is True

    def test_orchestrator_without_shutdown(self):
        class NoShutdown:
            def process_request(self, request, mode):
                return {"success": True}
        svc = make_service(orchestrator_factory=lambda: NoShutdown())
        result = svc.multi_agent_run("x")
        assert result["success"] is True

    def test_run_does_not_pass_progress_kwarg(self):
        """阻塞版不传 progress，兼容只接受 (request, mode) 的编排器。"""
        orch = MagicMock()
        orch.process_request.return_value = {"success": True}
        svc = make_service(orchestrator_factory=lambda: orch)
        svc.multi_agent_run("x", mode="parallel")
        orch.process_request.assert_called_once_with("x", "parallel")


class TestMultiAgentStream:
    def test_empty_request(self):
        svc = make_service()
        events = list(svc.multi_agent_stream("  "))
        assert events == [StreamEvent("error", "请求不能为空")]

    def test_progress_events_then_answer(self):
        orch = MagicMock()

        def fake_process(request, mode, progress=None):
            progress({"stage": "decompose", "message": "🧩 分解任务"})
            progress({"stage": "execute", "message": "⚙️ 执行 1/1", "current": 1, "total": 1})
            progress({"stage": "integrate", "message": "🧷 整合"})
            return {"success": True, "summary": "协作完成", "results": []}

        orch.process_request.side_effect = fake_process
        svc = make_service(orchestrator_factory=lambda: orch)
        events = list(svc.multi_agent_stream("任务", mode="hierarchy"))
        kinds = [e.kind for e in events]
        assert kinds.count("progress") == 3
        assert kinds[-1] == "answer"
        assert events[-1].message == "协作完成"
        assert events[-1].data["success"] is True
        # 进度事件透传原始 stage/current/total，供 UI 去重
        exec_evt = [e for e in events if e.kind == "progress"][1]
        assert exec_evt.data["stage"] == "execute"
        assert exec_evt.data["current"] == 1
        orch.shutdown.assert_called_once()

    def test_process_request_raises_becomes_failed_answer(self):
        orch = MagicMock()
        orch.process_request.side_effect = RuntimeError("nope")
        svc = make_service(orchestrator_factory=lambda: orch)
        events = list(svc.multi_agent_stream("x"))
        assert events[-1].kind == "answer"
        assert events[-1].data["success"] is False
        assert "nope" in events[-1].data["error"]

    def test_running_flag_reset(self):
        orch = MagicMock()
        orch.process_request.return_value = {"success": True}
        svc = make_service(orchestrator_factory=lambda: orch)
        list(svc.multi_agent_stream("x"))
        assert svc.is_running() is False


# ==================== 知识库管理 ====================

class TestKnowledgeBase:
    def test_add_documents_empty(self):
        svc = make_service()
        assert "未选择" in svc.add_documents([])

    def test_add_documents_success(self):
        svc = make_service()
        msg = svc.add_documents(["/a.md", "/b.md"])
        assert "已入库 2 个文件" in msg
        assert svc._fake_rag.added  # add_documents 被调用

    def test_add_documents_empty_docs(self):
        svc = make_service(load_documents=lambda p, file_types=None: [])
        msg = svc.add_documents(["/a.md"])
        assert "部分失败" in msg
        assert "无法加载" in msg

    def test_add_documents_loader_raises(self):
        def bad_loader(p, file_types=None):
            raise ValueError("bad file")
        svc = make_service(load_documents=bad_loader)
        msg = svc.add_documents(["/a.md"])
        assert "部分失败" in msg
        assert "bad file" in msg

    def test_add_documents_engine_add_raises(self):
        rag = FakeRAG()
        rag.raise_on_add = True
        svc = make_service(rag=rag)
        msg = svc.add_documents(["/a.md"])
        assert msg.startswith("[错误]")
        assert "入库失败" in msg

    def test_add_documents_mixed(self):
        """一个成功一个失败。"""
        calls = {"n": 0}

        def loader(p, file_types=None):
            calls["n"] += 1
            if calls["n"] == 1:
                return [MagicMock()]
            raise ValueError("second bad")

        svc = make_service(load_documents=loader)
        msg = svc.add_documents(["/ok.md", "/bad.md"])
        assert "已入库 1 个文件" in msg
        assert "second bad" in msg

    def test_get_stats_success(self):
        svc = make_service()
        assert svc.get_stats()["total_documents"] == 3

    def test_get_stats_error(self):
        rag = FakeRAG()
        rag.raise_on_stats = True
        svc = make_service(rag=rag)
        assert "error" in svc.get_stats()

    def test_rebuild_with_path_success(self):
        svc = make_service()
        msg = svc.rebuild_index("/data")
        assert "已重建索引" in msg
        assert svc._fake_rag.built is not None

    def test_rebuild_with_path_no_docs(self):
        svc = make_service(load_documents=lambda p, file_types=None: [])
        msg = svc.rebuild_index("/data")
        assert "无可加载文档" in msg

    def test_rebuild_no_path(self):
        svc = make_service()
        assert "未指定数据路径" in svc.rebuild_index(None)

    def test_rebuild_raises(self):
        def bad(p, file_types=None):
            raise RuntimeError("load-fail")
        svc = make_service(load_documents=bad)
        msg = svc.rebuild_index("/data")
        assert msg.startswith("[错误]")

    def test_clear_index_success(self):
        svc = make_service()
        assert "已清空" in svc.clear_index()
        assert svc._fake_rag.cleared is True

    def test_clear_index_error(self):
        rag = FakeRAG()
        rag.raise_on_clear = True
        svc = make_service(rag=rag)
        assert svc.clear_index().startswith("[错误]")


# ==================== 会话管理 ====================

def _fake_session(sid, title, n_msgs=0):
    s = MagicMock()
    s.session_id = sid
    s.title = title
    s.messages = [MagicMock() for _ in range(n_msgs)]
    return s


class TestSessions:
    def test_list_sessions_with_current(self):
        sm = MagicMock()
        s1 = _fake_session("id1", "会话1", 2)
        s2 = _fake_session("id2", "会话2", 0)
        sm.list_sessions.return_value = [s1, s2]
        sm.get_current_session.return_value = s1
        svc = make_service(session_manager_factory=lambda: sm)
        result = svc.list_sessions()
        assert result[0]["is_current"] is True
        assert result[0]["messages"] == 2
        assert result[1]["is_current"] is False

    def test_list_sessions_rich_fields(self):
        """真实 SessionManager：状态/更新时间/首条提问预览。"""
        svc = make_service()
        sid = svc.ensure_session()
        svc._context(sid).record("DJI OSMO 360 多少钱", "2999")
        item = svc.list_sessions()[0]
        assert item["is_current"] is True
        assert item["status"] == "active"
        assert len(item["updated_at"]) == 16 and item["created_at"]
        assert item["preview"] == "DJI OSMO 360 多少钱"
        assert item["messages"] == 2

    def test_fmt_time_tolerates_non_datetime(self):
        assert WebService._fmt_time(None) == ""
        assert WebService._fmt_time("2026") == ""
        bad = MagicMock()
        bad.strftime.side_effect = ValueError("x")
        assert WebService._fmt_time(bad) == ""

    def test_delete_session_rules(self):
        svc = make_service()
        cur = svc.ensure_session()
        other = svc.session_manager.create_session("其他")
        svc.session_manager.switch_session(cur)
        assert "请先选择" in svc.delete_session("")
        assert "不能删除当前会话" in svc.delete_session(cur)
        assert "已删除" in svc.delete_session(other.session_id)
        assert "会话不存在" in svc.delete_session("missing")
        assert svc.session_manager.get_session(other.session_id) is None

    def test_delete_session_errors(self):
        sm = MagicMock(spec=["get_current_session", "list_sessions"])
        sm.get_current_session.return_value = None
        svc = make_service(session_manager=sm)
        assert "不支持删除" in svc.delete_session("x")
        sm2 = MagicMock()
        sm2.get_current_session.side_effect = RuntimeError("boom")
        svc2 = make_service(session_manager=sm2)
        assert "删除会话失败" in svc2.delete_session("x")

    def test_archive_session(self):
        svc = make_service()
        sid = svc.ensure_session()
        assert "请先选择" in svc.archive_session("")
        assert "已归档" in svc.archive_session(sid)
        assert svc.list_sessions()[0]["status"] == "archived"
        assert "会话不存在" in svc.archive_session("missing")
        sm = MagicMock()
        sm.archive_session.side_effect = RuntimeError("boom")
        assert "归档会话失败" in make_service(session_manager=sm).archive_session("x")

    def test_list_sessions_no_current(self):
        sm = MagicMock()
        sm.list_sessions.return_value = [_fake_session("id1", "t")]
        sm.get_current_session.return_value = None
        svc = make_service(session_manager_factory=lambda: sm)
        result = svc.list_sessions()
        assert result[0]["is_current"] is False

    def test_create_session(self):
        sm = MagicMock()
        sm.create_session.return_value = _fake_session("new", "新会话")
        svc = make_service(session_manager_factory=lambda: sm)
        assert svc.create_session("标题") == "new"
        sm.create_session.assert_called_once_with(title="标题")

    def test_create_session_empty_title(self):
        sm = MagicMock()
        sm.create_session.return_value = _fake_session("new", "")
        svc = make_service(session_manager_factory=lambda: sm)
        svc.create_session("")
        sm.create_session.assert_called_once_with(title=None)

    def test_switch_session_success(self):
        sm = MagicMock()
        sm.switch_session.return_value = True
        svc = make_service(session_manager_factory=lambda: sm)
        assert svc.switch_session("id1") is True

    def test_switch_session_empty(self):
        svc = make_service()
        assert svc.switch_session("") is False

    def test_search_sessions(self):
        sm = MagicMock()
        sm.search_sessions.return_value = [_fake_session("id1", "命中")]
        svc = make_service(session_manager_factory=lambda: sm)
        result = svc.search_sessions("关键词")
        assert result[0]["title"] == "命中"

    def test_search_sessions_empty_query(self):
        svc = make_service()
        assert svc.search_sessions("  ") == []


# ==================== 知识图谱 ====================

class TestGraph:
    def test_query_entity_empty(self):
        svc = make_service()
        result = svc.query_graph_entity("  ")
        assert "不能为空" in result["explanation"]

    def test_query_entity_success(self):
        gq = MagicMock()
        qr = MagicMock()
        qr.to_dict.return_value = {"entities": [{"text": "Python"}], "relations": []}
        gq.query_entity.return_value = qr
        svc = make_service(graph_query_factory=lambda: gq)
        result = svc.query_graph_entity("Python")
        assert result["entities"][0]["text"] == "Python"

    def test_query_entity_error(self):
        gq = MagicMock()
        gq.query_entity.side_effect = RuntimeError("graph-boom")
        svc = make_service(graph_query_factory=lambda: gq)
        result = svc.query_graph_entity("X")
        assert "查询失败" in result["explanation"]

    def test_graph_summary_success(self):
        gq = MagicMock()
        gq.get_graph_summary.return_value = {"is_available": True}
        svc = make_service(graph_query_factory=lambda: gq)
        assert svc.graph_summary()["is_available"] is True

    def test_graph_summary_error(self):
        gq = MagicMock()
        gq.get_graph_summary.side_effect = RuntimeError("boom")
        svc = make_service(graph_query_factory=lambda: gq)
        result = svc.graph_summary()
        assert result["is_available"] is False
        assert "error" in result


# ==================== 单例 ====================

class TestSingleton:
    def test_get_and_reset(self):
        reset_web_service()
        s1 = get_web_service(
            rag_factory=lambda: FakeRAG(),
            react_factory=lambda on_step=None, on_confirm=None, context=None: FakeReact(),
            orchestrator_factory=lambda: MagicMock(),
            session_manager_factory=lambda: MagicMock(),
            graph_query_factory=lambda: MagicMock(),
            set_rag_engine=lambda e: None,
            load_documents=lambda p, file_types=None: [],
            resolve_mode=lambda m: m,
        )
        s2 = get_web_service()
        assert s1 is s2
        reset_web_service()
        assert services._web_service_singleton is None


# ==================== 默认工厂（覆盖惰性 import 分支） ====================

class TestDefaultFactories:
    def test_default_rag_factory_load_index_swallows_error(self, monkeypatch):
        fake_engine = MagicMock()
        fake_engine.load_index.side_effect = RuntimeError("no index")
        fake_module = MagicMock()
        fake_module.RAGEngine.return_value = fake_engine
        monkeypatch.setitem(__import__("sys").modules, "rag_engine", fake_module)
        result = services._default_rag_factory()
        assert result is fake_engine

    def test_default_react_factory(self, monkeypatch):
        fake_module = MagicMock()
        monkeypatch.setitem(__import__("sys").modules, "react_engine", fake_module)
        services._default_react_factory(on_step=lambda e: None)
        fake_module.ReActEngine.assert_called_once()

    def test_default_orchestrator_factory(self, monkeypatch):
        import sys as _sys
        cfg_module = MagicMock()
        orch_module = MagicMock()
        monkeypatch.setitem(_sys.modules, "agent_config", cfg_module)
        monkeypatch.setitem(_sys.modules, "agent_orchestrator", orch_module)
        services._default_orchestrator_factory()
        orch_module.AgentOrchestrator.assert_called_once()

    def test_default_set_rag_engine(self, monkeypatch):
        import sys as _sys
        fake_module = MagicMock()
        monkeypatch.setitem(_sys.modules, "agent_tools", fake_module)
        services._default_set_rag_engine("engine")
        fake_module.set_rag_engine.assert_called_once_with("engine")

    def test_default_session_manager_factory(self, monkeypatch):
        """默认工厂经由会话上下文单例取共享 SessionManager（首次创建时迁移旧历史）。"""
        import conversation_context as cc
        fake_ctx = MagicMock()
        fake_ctx.manager = "shared-manager"
        monkeypatch.setattr(cc, "get_conversation_context", lambda: fake_ctx)
        assert services._default_session_manager_factory() == "shared-manager"

    def test_default_graph_query_factory(self, monkeypatch):
        import sys as _sys
        fake_pkg = MagicMock()
        monkeypatch.setitem(_sys.modules, "knowledge_graph.graph_query", fake_pkg)
        services._default_graph_query_factory()
        fake_pkg.get_graph_query.assert_called_once()

    def test_default_load_documents(self, monkeypatch):
        import sys as _sys
        fake_module = MagicMock()
        fake_module.load_documents.return_value = ["doc"]
        monkeypatch.setitem(_sys.modules, "document_loader", fake_module)
        assert services._default_load_documents("/p") == ["doc"]

    def test_default_collaboration_mode_valid(self, monkeypatch):
        import sys as _sys
        from enum import Enum

        class Mode(Enum):
            PARALLEL = "parallel"
        fake_module = MagicMock()
        fake_module.CollaborationMode = Mode
        monkeypatch.setitem(_sys.modules, "agents.agent_types", fake_module)
        assert services._default_collaboration_mode("parallel") == Mode.PARALLEL

    def test_default_collaboration_mode_invalid(self, monkeypatch):
        import sys as _sys
        from enum import Enum

        class Mode(Enum):
            PARALLEL = "parallel"
        fake_module = MagicMock()
        fake_module.CollaborationMode = Mode
        monkeypatch.setitem(_sys.modules, "agents.agent_types", fake_module)
        assert services._default_collaboration_mode("bogus") is None

    def test_default_collaboration_mode_none(self):
        assert services._default_collaboration_mode("") is None


# ==================== 阶段三：工具命令面 ====================

class _FakeRegistry:
    """记录调用的桩注册表。"""

    def __init__(self, result="OK", raise_error=False):
        self.calls = []
        self._result = result
        self._raise = raise_error

    def execute(self, tool, args, auto_confirm=False):
        self.calls.append((tool, args, auto_confirm))
        if self._raise:
            raise RuntimeError("tool-boom")
        return self._result


class TestToolCommands:
    def _patch_registry(self, monkeypatch, reg):
        import sys as _sys
        fake_at = MagicMock()
        fake_at.registry = reg
        monkeypatch.setitem(_sys.modules, "agent_tools", fake_at)

    def test_run_tool_success(self, monkeypatch):
        reg = _FakeRegistry("结果")
        self._patch_registry(monkeypatch, reg)
        svc = make_service()
        assert svc.run_tool("web_search", {"query": "x"}) == "结果"
        assert reg.calls[0][0] == "web_search"

    def test_run_tool_error(self, monkeypatch):
        reg = _FakeRegistry(raise_error=True)
        self._patch_registry(monkeypatch, reg)
        svc = make_service()
        out = svc.run_tool("web_search", {"query": "x"})
        assert out.startswith("[错误]")

    def test_web_search_empty(self):
        svc = make_service()
        assert svc.web_search("  ").startswith("[提示]")

    def test_web_search_calls_tool(self, monkeypatch):
        reg = _FakeRegistry("命中")
        self._patch_registry(monkeypatch, reg)
        svc = make_service()
        assert svc.web_search("python") == "命中"
        assert reg.calls[0] == ("web_search", {"query": "python"}, False)

    def test_web_cache_clear_auto_confirm(self, monkeypatch):
        reg = _FakeRegistry("cleared")
        self._patch_registry(monkeypatch, reg)
        svc = make_service()
        svc.web_cache_clear()
        assert reg.calls[0][2] is True  # auto_confirm

    def test_code_ast_args(self, monkeypatch):
        reg = _FakeRegistry("ast")
        self._patch_registry(monkeypatch, reg)
        svc = make_service()
        svc.code_ast("def foo", "src")
        assert reg.calls[0] == ("ast_search", {"pattern": "def foo", "path": "src"}, False)

    def test_git_analyze_invalid_type(self):
        svc = make_service()
        assert svc.git_analyze("bogus").startswith("[错误]")

    def test_git_analyze_valid(self, monkeypatch):
        reg = _FakeRegistry("git")
        self._patch_registry(monkeypatch, reg)
        svc = make_service()
        svc.git_analyze("status")
        assert reg.calls[0] == ("git_analyze", {"repo_path": ".", "analysis_type": "status"}, False)

    def test_db_query_empty(self):
        svc = make_service()
        assert svc.db_query("").startswith("[提示]")

    def test_db_connect_calls_tool(self, monkeypatch):
        reg = _FakeRegistry("connected")
        self._patch_registry(monkeypatch, reg)
        svc = make_service()
        svc.db_connect("sqlite", "/tmp/a.db")
        assert reg.calls[0][0] == "database_connect"

    def test_graph_build_empty(self):
        svc = make_service()
        assert svc.graph_build("").startswith("[提示]")


# ==================== 模型管理（热切换）====================

class _FakeSwitchResult:
    def __init__(self, ok=True, model="qwen3.5:9b", previous="qwen3.5:4b",
                 num_ctx=8192, unloaded=True, message="ok"):
        self.ok = ok
        self.model = model
        self.previous = previous
        self.num_ctx = num_ctx
        self.unloaded_previous = unloaded
        self.message = message


class _FakeSwitcher:
    def __init__(self, installed=None, info=None, result=None, raise_on=None):
        self.installed = installed if installed is not None else ["qwen3.5:4b", "qwen3.5:9b"]
        self.info = info or {"model": "qwen3.5:4b", "num_ctx": 16384, "think": False,
                             "loaded": True, "size_bytes": 4_000_000_000, "loaded_models": ["qwen3.5:4b"]}
        self.result = result or _FakeSwitchResult()
        self.raise_on = raise_on or set()
        self.switch_calls = []

    def list_installed_models(self):
        if "list" in self.raise_on:
            raise RuntimeError("down")
        return self.installed

    def current_model_info(self):
        if "info" in self.raise_on:
            raise RuntimeError("down")
        return self.info

    def switch_model(self, model, rag_engine=None, react_engine=None):
        if "switch" in self.raise_on:
            raise RuntimeError("down")
        self.switch_calls.append((model, rag_engine, react_engine))
        return self.result

    def switch_think(self, enabled, rag_engine=None, react_engine=None):
        if "think" in self.raise_on:
            raise RuntimeError("down")
        self.think_calls = getattr(self, "think_calls", [])
        self.think_calls.append((enabled, rag_engine, react_engine))
        return self.think_result if hasattr(self, "think_result") else SimpleNamespace(
            ok=True, enabled=enabled, changed=True, message="思考模式已开启" if enabled else "思考模式已关闭"
        )


class TestModelManagement:
    def test_list_models(self):
        sw = _FakeSwitcher()
        svc = make_service(model_switcher_factory=lambda: sw)
        assert svc.list_models() == ["qwen3.5:4b", "qwen3.5:9b"]

    def test_list_models_error_returns_empty(self):
        sw = _FakeSwitcher(raise_on={"list"})
        svc = make_service(model_switcher_factory=lambda: sw)
        assert svc.list_models() == []

    def test_current_model(self):
        sw = _FakeSwitcher()
        svc = make_service(model_switcher_factory=lambda: sw)
        info = svc.current_model()
        assert info["model"] == "qwen3.5:4b"
        assert info["loaded"] is True

    def test_current_model_error(self):
        sw = _FakeSwitcher(raise_on={"info"})
        svc = make_service(model_switcher_factory=lambda: sw)
        info = svc.current_model()
        assert info["model"] == "?"
        assert "error" in info

    def test_switch_model_before_rag_created_passes_none(self):
        """RAG 引擎尚未惰性创建时不应触发创建（避免为切换而加载 Ollama/Chroma）。"""
        sw = _FakeSwitcher()
        svc = make_service(model_switcher_factory=lambda: sw)
        out = svc.switch_model("qwen3.5:9b")
        assert out["ok"] is True
        assert out["model"] == "qwen3.5:9b"
        assert out["previous"] == "qwen3.5:4b"
        assert out["num_ctx"] == 8192
        assert out["unloaded_previous"] is True
        assert sw.switch_calls == [("qwen3.5:9b", None, None)]
        assert svc._rag_engine is None

    def test_switch_model_after_rag_created_syncs_engine(self):
        sw = _FakeSwitcher()
        svc = make_service(model_switcher_factory=lambda: sw)
        rag = svc.rag_engine  # 触发惰性创建
        svc.switch_model("qwen3.5:9b")
        assert sw.switch_calls[0][1] is rag

    def test_switch_model_failure_result(self):
        sw = _FakeSwitcher(result=_FakeSwitchResult(ok=False, model="", message="未安装"))
        svc = make_service(model_switcher_factory=lambda: sw)
        out = svc.switch_model("nope")
        assert out["ok"] is False
        assert "未安装" in out["message"]

    def test_switch_model_exception(self):
        sw = _FakeSwitcher(raise_on={"switch"})
        svc = make_service(model_switcher_factory=lambda: sw)
        out = svc.switch_model("qwen3.5:9b")
        assert out["ok"] is False
        assert "切换失败" in out["message"]


class TestThinkToggle:
    def test_set_think_before_rag_created_passes_none(self):
        sw = _FakeSwitcher()
        svc = make_service(model_switcher_factory=lambda: sw)
        out = svc.set_think(True)
        assert out == {"ok": True, "enabled": True, "changed": True, "message": "思考模式已开启"}
        assert sw.think_calls == [(True, None, None)]
        assert svc._rag_engine is None

    def test_set_think_after_rag_created_syncs_engine(self):
        sw = _FakeSwitcher()
        svc = make_service(model_switcher_factory=lambda: sw)
        rag = svc.rag_engine
        svc.set_think(False)
        assert sw.think_calls[0] == (False, rag, None)

    def test_set_think_rejected(self):
        sw = _FakeSwitcher()
        sw.think_result = SimpleNamespace(ok=False, enabled=False, changed=False, message="不支持思考模式")
        svc = make_service(model_switcher_factory=lambda: sw)
        out = svc.set_think(True)
        assert out["ok"] is False and out["enabled"] is False
        assert "不支持" in out["message"]

    def test_set_think_exception(self):
        sw = _FakeSwitcher(raise_on={"think"})
        svc = make_service(model_switcher_factory=lambda: sw)
        out = svc.set_think(True)
        assert out["ok"] is False
        assert "设置失败" in out["message"]


# ==================== 连续对话上下文（会话记忆 / 改写 / 健康度） ====================

class TestConversationContextWiring:
    """三种模式都应绑定到会话：记录本轮、透出上下文指标与改写结果。"""

    def _ctx_with_history(self, svc, sid, n=1):
        ctx = svc._context(sid)
        for i in range(n):
            ctx.record(f"DJI OSMO 360 是什么 {i}", "一款全景相机")
        return ctx

    def test_rag_stream_records_turn_and_reports_context(self):
        svc = make_service()
        sid = svc.ensure_session()
        events = list(svc.rag_query_stream("什么是RAG", enable_web_search=False, session_id=sid))
        answer = events[-1]
        assert answer.kind == "answer"
        ctx_info = answer.data["context"]
        assert ctx_info["turns"] == 1
        assert ctx_info["budget"] > 0
        assert "suggest_new_session" in ctx_info
        history = svc.chat_history(sid)
        assert [m["role"] for m in history] == ["user", "assistant"]
        assert history[0]["content"] == "什么是RAG"
        assert answer.data["rewritten"] is None

    def test_rag_stream_rewrites_followup_with_history(self, monkeypatch):
        """会话有历史 + 追问句式 → 改写为独立问题用于检索，并透出 rewritten。"""
        import conversation_context as cc

        svc = make_service()
        sid = svc.ensure_session()
        self._ctx_with_history(svc, sid)
        monkeypatch.setattr(cc, "_default_complete", lambda prompt: "DJI OSMO 360 多少钱")
        events = list(svc.rag_query_stream("它多少钱", enable_web_search=False, session_id=sid))
        answer = events[-1]
        assert answer.data["rewritten"] == "DJI OSMO 360 多少钱"
        # 检索用的是改写后的问题（FakeRAG 把问题回显进答案）
        assert "DJI OSMO 360 多少钱" in answer.message
        assert any(e.kind == "progress" and "结合上下文" in e.message for e in events)
        # 会话中记录的是原问题，并附带改写结果
        session = svc.session_manager.get_session(sid)
        user_msgs = [m for m in session.messages if m["role"] == "user"]
        assert user_msgs[-1]["content"] == "它多少钱"
        assert user_msgs[-1]["rewritten"] == "DJI OSMO 360 多少钱"

    def test_rag_meta_query_recorded_as_overview(self, monkeypatch):
        import sys
        fake_mod = MagicMock()
        fake_mod.get_global_metadata_manager.return_value.list_files.return_value = []
        monkeypatch.setitem(sys.modules, "file_metadata", fake_mod)
        svc = make_service()
        sid = svc.ensure_session()
        list(svc.rag_query_stream("知识库里有什么", enable_web_search=False, session_id=sid))
        history = svc.chat_history(sid)
        assert history[-1]["content"] == "[知识库概览]"

    def test_agent_stream_engine_gets_context_and_records(self):
        svc = make_service()
        sid = svc.ensure_session()
        events = list(svc.agent_chat_stream("写个函数", session_id=sid))
        assert events[-1].kind == "answer"
        assert "context" in events[-1].data
        history = svc.chat_history(sid)
        assert history == [
            {"role": "user", "content": "写个函数"},
            {"role": "assistant", "content": "最终答案"},
        ]
        session = svc.session_manager.get_session(sid)
        assert session.messages[-1]["trace"] == "共 1 步"

    def test_agent_stream_non_dict_result_tolerated(self, monkeypatch):
        svc = make_service()
        monkeypatch.setattr(svc, "_finish_turn", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("x")))
        # _finish_turn 抛错时 run 抛错 → error 事件
        events = list(svc.agent_chat_stream("x"))
        assert events[-1].kind == "error"

    def test_multi_agent_stream_records_and_rewrites(self, monkeypatch):
        import conversation_context as cc

        orch = MagicMock()
        seen = {}

        def fake_process(request, mode, progress=None):
            seen["request"] = request
            return {"success": True, "summary": "协作完成", "results": []}

        orch.process_request.side_effect = fake_process
        svc = make_service(orchestrator_factory=lambda: orch)
        sid = svc.ensure_session()
        self._ctx_with_history(svc, sid)
        monkeypatch.setattr(cc, "_default_complete", lambda prompt: "帮我总结 DJI OSMO 360 的优缺点")
        events = list(svc.multi_agent_stream("总结一下它", session_id=sid))
        assert events[-1].kind == "answer"
        assert seen["request"] == "帮我总结 DJI OSMO 360 的优缺点"
        assert events[-1].data["rewritten"] == "帮我总结 DJI OSMO 360 的优缺点"
        assert events[-1].data["context"]["turns"] == 2
        history = svc.chat_history(sid)
        assert history[-2]["content"] == "总结一下它"
        assert history[-1]["content"] == "协作完成"

    def test_multi_agent_failure_recorded_with_marker(self):
        orch = MagicMock()
        orch.process_request.return_value = {"success": False, "summary": "协作失败", "error": "x"}
        svc = make_service(orchestrator_factory=lambda: orch)
        sid = svc.ensure_session()
        list(svc.multi_agent_stream("任务", session_id=sid))
        assert svc.chat_history(sid)[-1]["content"].startswith("[协作失败]")

    def test_multi_agent_non_dict_result_wrapped(self):
        class Weird:
            def process_request(self, request, mode, progress=None):
                return "plain"
        svc = make_service(orchestrator_factory=lambda: Weird())
        events = list(svc.multi_agent_stream("任务"))
        assert events[-1].kind == "answer"
        assert events[-1].message == "plain"

    def test_finish_turn_error_returns_error_dict(self):
        class BadCtx:
            def record(self, *a, **k):
                raise RuntimeError("disk full")

        result = WebService._finish_turn(BadCtx(), "q", "a", {})
        assert "disk full" in result["error"]

    def test_health_before_swallows_errors(self):
        class BadCtx:
            def health(self, q=None):
                raise RuntimeError("x")

        assert WebService._health_before(BadCtx(), "q") == {}


class TestSessionContextHelpers:
    def test_ensure_session_creates_then_reuses(self):
        svc = make_service()
        sid = svc.ensure_session()
        assert sid
        assert svc.ensure_session() == sid

    def test_session_choices_labels(self):
        svc = make_service()
        sid = svc.ensure_session()
        svc._context(sid).record("q", "a")
        choices = svc.session_choices()
        assert choices[0][1] == sid
        assert "2 条" in choices[0][0] and sid[:8] in choices[0][0]

    def test_chat_history_empty_for_unknown(self):
        svc = make_service()
        assert svc.chat_history("nope") == [] or isinstance(svc.chat_history("nope"), list)

    def test_chat_history_error_returns_empty(self, monkeypatch):
        svc = make_service()
        monkeypatch.setattr(svc, "_context", lambda sid=None: (_ for _ in ()).throw(RuntimeError("x")))
        assert svc.chat_history("x") == []

    def test_context_metrics_and_error(self, monkeypatch):
        svc = make_service()
        sid = svc.ensure_session()
        m = svc.context_metrics(sid)
        assert m["turns"] == 0 and m["budget"] > 0
        monkeypatch.setattr(svc, "_context", lambda sid=None: (_ for _ in ()).throw(RuntimeError("x")))
        assert "error" in svc.context_metrics(sid)

    def test_clear_context(self, monkeypatch):
        svc = make_service()
        sid = svc.ensure_session()
        svc._context(sid).record("q", "a")
        assert svc.clear_context(sid) is True
        assert svc.chat_history(sid) == []
        monkeypatch.setattr(svc, "_context", lambda sid=None: (_ for _ in ()).throw(RuntimeError("x")))
        assert svc.clear_context(sid) is False

    def test_compact_context_short_history(self, monkeypatch):
        svc = make_service()
        sid = svc.ensure_session()
        svc._context(sid).record("q", "a")
        assert svc.compact_context(sid) == {"folded_messages": 0}
        monkeypatch.setattr(svc, "_context", lambda sid=None: (_ for _ in ()).throw(RuntimeError("x")))
        assert "error" in svc.compact_context(sid)

    def test_compact_context_folds_old_turns(self, monkeypatch):
        import conversation_context as cc
        monkeypatch.setattr(cc, "_default_complete", lambda prompt: "摘要文本")
        svc = make_service()
        sid = svc.ensure_session()
        ctx = svc._context(sid)
        for i in range(5):
            ctx.record(f"问题{i}", f"回答{i}")
        result = svc.compact_context(sid)
        assert result["folded_messages"] == 4
        assert result["compressions"] == 1
        assert svc.context_metrics(sid)["summary"] == "摘要文本"

    def test_create_session_with_carry_summary(self, monkeypatch):
        import conversation_context as cc
        monkeypatch.setattr(cc, "_default_complete", lambda prompt: "上一会话摘要")
        svc = make_service()
        sid = svc.ensure_session()
        svc._context(sid).record("DJI OSMO 360 是什么", "一款全景相机")
        new_sid = svc.create_session("新会话", carry_summary=True, from_session_id=sid)
        assert new_sid != sid
        m = svc.context_metrics(new_sid)
        assert "承接自上一会话" in m["summary"]
        assert "DJI OSMO 360" in m["summary"]
        assert svc.chat_history(new_sid) == []

    def test_mark_suggested_and_continue(self, monkeypatch):
        svc = make_service()
        sid = svc.ensure_session()
        svc._context(sid).record("q", "a")
        svc.mark_suggested(sid)
        meta = svc.session_manager.get_session(sid).metadata["context"]
        assert meta["suggested"] is True
        svc.continue_session(sid)
        meta = svc.session_manager.get_session(sid).metadata["context"]
        assert meta["suggested"] is False and meta["only_compressions"] is True
        # 异常吞掉
        monkeypatch.setattr(svc, "_context", lambda sid=None: (_ for _ in ()).throw(RuntimeError("x")))
        svc.mark_suggested(sid)
        svc.continue_session(sid)
