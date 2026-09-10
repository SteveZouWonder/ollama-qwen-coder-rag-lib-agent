#!/usr/bin/env python3
"""test_web_services.py — Web 服务层单元测试。

服务层是 Web 界面唯一与核心引擎交互的层。通过依赖注入把各引擎替换为
MagicMock/桩对象，在不启动真实 Ollama/ChromaDB 的前提下覆盖全部分支。
"""
import os
import subprocess
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

# conftest 的 autouse fixture 会把 subprocess.run 全局 Mock 掉；Git 概览测试需要真实 git，
# 在模块导入（collection）阶段先把真实实现留存，用例内通过 monkeypatch 临时还原。
_REAL_SUBPROCESS_RUN = subprocess.run
_REAL_SUBPROCESS_POPEN = subprocess.Popen

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
        # 共享编排层 rag_pipeline.answer_question 会检查 retriever 判断
        # 知识库是否已初始化；桩默认设为真值，走"知识库检索"分支。
        self.retriever = object()

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

    def add_documents(self, docs, file_paths=None, progress_callback=None):
        if self.raise_on_add:
            raise RuntimeError("add-fail")
        self.added.append((docs, file_paths))
        if progress_callback:
            progress_callback({"stage": "chunk", "message": "切分 a (1/1)", "current": 1, "total": 1})
            progress_callback({"stage": "embed", "message": "生成向量 2/2", "current": 2, "total": 2})
        # 模拟 P4 的按文件统计
        self.last_ingest_stats = getattr(self, "ingest_stats", None) or {}

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

    def chat(self, user_input, on_token=None):
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
    @pytest.fixture(autouse=True)
    def _synth(self, stub_synthesis):
        """F9 P0-1：检索层不再生成答案，综合由打桩的 llm_direct_answer 产出 ``答案:<问题>``。"""

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

        seen = {}

        def fake_process(request, mode, progress=None, context=None, on_token=None):
            seen["context"] = context
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
        # 无 answer 字段时退回 summary
        assert events[-1].message == "协作完成"
        assert events[-1].data["success"] is True
        # 会话上下文透传给编排器（RAGAgent 追问改写）
        assert seen["context"] is not None
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

    def test_web_cache_status_calls_tool(self, monkeypatch):
        reg = _FakeRegistry("状态")
        self._patch_registry(monkeypatch, reg)
        svc = make_service()
        assert svc.web_cache_status() == "状态"
        assert reg.calls[0] == ("web_cache_status", {}, False)

    def test_web_cache_clear_auto_confirm(self, monkeypatch):
        reg = _FakeRegistry("cleared")
        self._patch_registry(monkeypatch, reg)
        svc = make_service()
        svc.web_cache_clear()
        assert reg.calls[0][2] is True  # auto_confirm

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
        assert svc.db_query("")["error"] == "请输入 SQL 查询语句"

    def test_db_connect_calls_tool(self, monkeypatch):
        reg = _FakeRegistry("connected")
        self._patch_registry(monkeypatch, reg)
        svc = make_service()
        svc.db_connect("/tmp/a.db")
        assert reg.calls[0] == ("database_connect", {"db_type": "sqlite", "database": "/tmp/a.db"}, False)
        assert svc.db_connect("  ").startswith("[提示]")

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

    def test_rag_stream_rewrites_followup_with_history(self, monkeypatch, stub_synthesis):
        """会话有历史 + 追问句式 → 改写为独立问题用于检索，并透出 rewritten。"""
        import conversation_context as cc

        svc = make_service()
        sid = svc.ensure_session()
        self._ctx_with_history(svc, sid)
        monkeypatch.setattr(cc, "_default_complete", lambda prompt: "DJI OSMO 360 多少钱")
        events = list(svc.rag_query_stream("它多少钱", enable_web_search=False, session_id=sid))
        answer = events[-1]
        assert answer.data["rewritten"] == "DJI OSMO 360 多少钱"
        # 检索用的是改写后的问题（综合桩把 prompt 中的问题回显进答案）
        assert "DJI OSMO 360 多少钱" in answer.message
        assert any(e.kind == "progress" and "结合上下文" in e.message for e in events)
        # 会话中记录的是原问题，并附带改写结果
        session = svc.session_manager.get_session(sid)
        user_msgs = [m for m in session.messages if m["role"] == "user"]
        assert user_msgs[-1]["content"] == "它多少钱"
        assert user_msgs[-1]["rewritten"] == "DJI OSMO 360 多少钱"

    def test_rag_stream_challenge_flag_in_answer_event(self, monkeypatch, stub_synthesis):
        """F9 P1-2：质疑追问 → answer 事件 data["challenge"] 为 True，进度事件文案为「重新核对」。"""
        import conversation_context as cc

        svc = make_service()
        sid = svc.ensure_session()
        self._ctx_with_history(svc, sid)
        monkeypatch.setattr(cc, "_default_complete", lambda prompt: "重新核对：DJI OSMO 360 售价（用户认为：3999）")
        events = list(svc.rag_query_stream("不对，应该是 3999 吧", enable_web_search=False, session_id=sid))
        answer = events[-1]
        assert answer.data["challenge"] is True
        assert answer.data["rewritten"].startswith("重新核对：")
        assert any(e.kind == "progress" and "用户质疑，重新核对" in e.message for e in events)

    def test_rag_stream_records_warn_notices_in_session(self, monkeypatch):
        """F9 P0-5：会话记录 = 正文 + warn 级 notice 各一行 ``[code] text``；answer 事件带 notices 等字段。"""
        import rag_pipeline

        svc = make_service()
        sid = svc.ensure_session()
        monkeypatch.setattr(rag_pipeline, "answer_question", lambda *a, **k: {
            "kind": "fallback", "answer": "模型自答", "kb_sources": [], "web_sources": [], "meta": None,
            "rewritten": None, "fallback_question": "冷门", "citation_check": None, "model": "m",
            "notices": [
                {"level": "warn", "code": "no_evidence", "text": "无资料依据 · 模型自身知识 · 请自行核实", "position": "before"},
                {"level": "info", "code": "fallback", "text": "建议：/agent 冷门", "position": "after"},
            ],
        })
        events = list(svc.rag_query_stream("冷门", enable_web_search=False, session_id=sid))
        answer = events[-1]
        assert answer.message == "模型自答"
        assert answer.data["notices"][0]["code"] == "no_evidence"
        assert answer.data["citation_check"] is None and answer.data["model"] == "m"
        history = svc.chat_history(sid)
        recorded = history[-1]["content"]
        assert recorded.startswith("模型自答")
        assert "[no_evidence] 无资料依据 · 模型自身知识 · 请自行核实" in recorded
        assert "[fallback]" not in recorded  # info 级不入会话

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

        def fake_process(request, mode, progress=None, context=None, on_token=None):
            seen["request"] = request
            return {"success": True, "summary": "执行了 1 个任务", "answer": "综合回答：优点是…",
                    "results": []}

        orch.process_request.side_effect = fake_process
        svc = make_service(orchestrator_factory=lambda: orch)
        sid = svc.ensure_session()
        self._ctx_with_history(svc, sid)
        monkeypatch.setattr(cc, "_default_complete", lambda prompt: "帮我总结 DJI OSMO 360 的优缺点")
        events = list(svc.multi_agent_stream("总结一下它", session_id=sid))
        assert events[-1].kind == "answer"
        assert events[-1].message == "综合回答：优点是…"
        assert seen["request"] == "帮我总结 DJI OSMO 360 的优缺点"
        assert events[-1].data["rewritten"] == "帮我总结 DJI OSMO 360 的优缺点"
        assert events[-1].data["context"]["turns"] == 2
        history = svc.chat_history(sid)
        assert history[-2]["content"] == "总结一下它"
        # 会话记录综合回答 answer，而不是统计句 summary
        assert history[-1]["content"] == "综合回答：优点是…"

    def test_multi_agent_failure_recorded_with_marker(self):
        orch = MagicMock()
        orch.process_request.return_value = {"success": False, "summary": "协作失败", "error": "x"}
        svc = make_service(orchestrator_factory=lambda: orch)
        sid = svc.ensure_session()
        list(svc.multi_agent_stream("任务", session_id=sid))
        assert svc.chat_history(sid)[-1]["content"].startswith("[协作失败]")

    def test_multi_agent_non_dict_result_wrapped(self):
        class Weird:
            def process_request(self, request, mode, progress=None, context=None, on_token=None):
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
        ctx = svc._context(sid)
        ctx.recent_turns = 1
        ctx.record("DJI OSMO 360 是什么", "一款全景相机")
        ctx.record("它多少钱", "2999 元")
        ctx.compact()  # 产生滚动摘要
        new_sid = svc.create_session("新会话", carry_summary=True, from_session_id=sid)
        assert new_sid != sid
        m = svc.context_metrics(new_sid)
        assert "承接自上一会话" in m["summary"]
        assert "上一会话摘要" in m["summary"]
        # 只承接已折叠的滚动摘要，不带 live 原文
        assert "2999" not in m["summary"]
        assert svc.carried_summary(new_sid) == "上一会话摘要"
        assert svc.chat_history(new_sid) == []

    def test_create_session_with_carry_but_no_summary_is_clean(self):
        """回归：上一会话没有滚动摘要时，携带摘要新建的会话必须完全干净。"""
        svc = make_service()
        sid = svc.ensure_session()
        svc._context(sid).record("DJI OSMO 360 是什么", "一款全景相机")
        new_sid = svc.create_session(None, carry_summary=True, from_session_id=sid)
        assert new_sid != sid
        assert svc.context_metrics(new_sid).get("summary", "") == ""
        assert svc.carried_summary(new_sid) == ""
        assert svc._context(new_sid).has_history() is False
        assert svc.chat_history(new_sid) == []
        # 旧会话不受影响
        assert [m["content"] for m in svc.chat_history(sid)] == ["DJI OSMO 360 是什么", "一款全景相机"]

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


# ==================== 交互式确认（单 Agent 危险操作审批）====================

class _ConfirmingReact(FakeReact):
    """执行中调用 on_confirm 一次，把结果写入答案。"""

    def chat(self, user_input, on_token=None):
        ok = self.on_confirm({"tool": "execute_command", "command": "rm x", "message": "确认?"})
        return f"confirmed={ok}"


class TestInteractiveConfirm:
    def _svc(self):
        return make_service(
            react_factory=lambda on_step=None, on_confirm=None, context=None: _ConfirmingReact(
                on_step=on_step, on_confirm=on_confirm, context=context
            )
        )

    def test_confirm_event_then_resolve_true(self):
        svc = self._svc()
        gen = svc.agent_chat_stream("x", interactive_confirm=True)
        evt = next(gen)
        assert evt.kind == "confirm"
        assert evt.data["command"] == "rm x"
        assert svc.pending_confirm()["tool"] == "execute_command"
        assert svc.resolve_confirm(True) is True
        rest = list(gen)
        assert rest[-1].kind == "answer"
        assert rest[-1].message == "confirmed=True"
        assert svc.pending_confirm() is None

    def test_resolve_false(self):
        svc = self._svc()
        gen = svc.agent_chat_stream("x", interactive_confirm=True)
        assert next(gen).kind == "confirm"
        svc.resolve_confirm(False)
        assert list(gen)[-1].message == "confirmed=False"

    def test_resolve_without_pending(self):
        assert make_service().resolve_confirm(True) is False

    def test_timeout_rejects(self):
        svc = self._svc()
        svc.confirm_timeout = 0.05
        events = list(svc.agent_chat_stream("x", interactive_confirm=True))
        assert events[0].kind == "confirm"
        assert events[-1].message == "confirmed=False"

    def test_stop_releases_pending_confirm(self):
        svc = self._svc()
        gen = svc.agent_chat_stream("x", interactive_confirm=True)
        assert next(gen).kind == "confirm"
        assert svc.stop_current() is True
        events = list(gen)
        assert any(e.kind == "cancelled" for e in events)

    def test_not_interactive_defaults_reject(self):
        svc = self._svc()
        events = list(svc.agent_chat_stream("x"))
        assert not any(e.kind == "confirm" for e in events)
        assert events[-1].message == "confirmed=False"

    def test_explicit_handler_wins(self):
        svc = self._svc()
        events = list(svc.agent_chat_stream("x", confirm_handler=lambda e: True, interactive_confirm=True))
        assert not any(e.kind == "confirm" for e in events)
        assert events[-1].message == "confirmed=True"


# ==================== CLI 对齐：新增服务方法 ====================

class TestCollaborationModes:
    def test_first_is_auto_and_contains_enum(self):
        modes = make_service().collaboration_modes()
        assert modes[0][1] == ""
        values = {v for _, v in modes}
        assert {"hierarchy", "parallel", "sequential", "competitive"} <= values

    def test_multi_agent_stream_passes_mode(self):
        orch = MagicMock()
        orch.process_request.return_value = {"success": True, "summary": "ok", "results": []}
        svc = make_service(orchestrator_factory=lambda: orch)
        list(svc.multi_agent_stream("任务", mode="parallel"))
        assert orch.process_request.call_args[0][1] == "parallel"


class TestAddPath:
    def test_empty(self):
        assert make_service().add_path("").startswith("[提示]")

    def test_append_success_with_types(self):
        calls = []

        def loader(path, file_types=None):
            calls.append((path, file_types))
            return [MagicMock(), MagicMock()]

        svc = make_service(load_documents=loader)
        svc._fake_rag.last_graph_derived = True
        out = svc.add_path("/docs", ".pdf, .md")
        assert out.startswith("[成功]") and "2 个片段" in out and "已同步更新知识图谱" in out
        assert calls == [("/docs", [".pdf", ".md"])]
        assert svc._fake_rag.added[0][1] == ["/docs"]

    def test_no_docs(self):
        svc = make_service(load_documents=lambda p, t=None: [])
        assert "未找到" in svc.add_path("/x")

    def test_load_error(self):
        def loader(p, t=None):
            raise ValueError("路径不存在")

        assert "[错误] 加载失败" in make_service(load_documents=loader).add_path("/x")

    def test_add_error(self):
        svc = make_service()
        svc._fake_rag.raise_on_add = True
        assert "[错误] 入库失败" in svc.add_path("/x")


class TestSessionInfo:
    def test_current_and_fields(self):
        svc = make_service()
        s = svc.session_manager.create_session("标题")
        info = svc.session_info("")
        assert info["session_id"] == s.session_id
        assert info["title"] == "标题"
        assert info["status"] == "active"
        assert info["created_at"] and info["updated_at"]
        assert info["messages"] == 0 and info["tags"] == [] and info["metadata"] == {}

    def test_substring_match(self):
        svc = make_service()
        s = svc.session_manager.create_session("A")
        assert svc.session_info(s.session_id[:6])["session_id"] == s.session_id

    def test_not_found(self):
        assert "error" in make_service().session_info("nope")


class TestGraphTyped:
    def _svc(self, monkeypatch, reg):
        import sys as _sys
        fake_at = MagicMock()
        fake_at.registry = reg
        monkeypatch.setitem(_sys.modules, "agent_tools", fake_at)
        return make_service()

    def test_prefix_overrides_type(self, monkeypatch):
        reg = _FakeRegistry("找到 1 个实体")
        svc = self._svc(monkeypatch, reg)
        out = svc.graph_query_typed("type:tool", "entity")
        assert out["query_type"] == "type" and out["query"] == "tool"
        assert reg.calls[0][1] == {"query": "tool", "query_type": "type"}

    def test_unknown_prefix_kept_as_entity_text(self, monkeypatch):
        reg = _FakeRegistry("x")
        svc = self._svc(monkeypatch, reg)
        out = svc.graph_query_typed("http://a", "neighbors")
        assert out["query_type"] == "neighbors" and out["query"] == "http://a"

    def test_empty(self):
        assert make_service().graph_query_typed("")["text"].startswith("[提示]")

    def test_build_file(self, monkeypatch, tmp_path):
        monkeypatch.setenv("READ_ALLOWED_DIRS", str(tmp_path))  # F10 P0-1：读边界
        reg = _FakeRegistry("built")
        svc = self._svc(monkeypatch, reg)
        f = tmp_path / "a.py"
        f.write_text("def f(): pass", encoding="utf-8")
        assert svc.graph_build_file(f"@{f}") == "built"
        assert reg.calls[0][1]["doc_type"] == "code" and reg.calls[0][1]["doc_id"] == "a.py"
        assert "[错误] 文件不存在" in svc.graph_build_file(str(tmp_path / "nope.txt"))
        # 越界用例见 TestWorkspaceReadBoundary（此处 agent_tools 被替换为 MagicMock，边界不生效）
        empty = tmp_path / "e.txt"
        empty.write_text("", encoding="utf-8")
        assert "[提示] 文件内容为空" in svc.graph_build_file(str(empty))
        assert svc.graph_build_file("").startswith("[提示]")


class TestDbStructured:
    """F9 P1-2/3/4：Web 数据库操作作用于共享层「当前连接」，并返回结构化结果。"""

    @pytest.fixture(autouse=True)
    def _clean(self):
        from database_tools import session

        session.clear_current()
        yield
        session.clear_current()

    def _connected(self, tmp_path, name="w.db"):
        svc = make_service()
        out = svc.db_connect(str(tmp_path / name))
        assert out.startswith("[成功]")
        return svc

    def test_not_connected_errors(self):
        svc = make_service()
        assert svc.db_current() == {"connected": False, "db_type": "", "database": "", "label": ""}
        assert "尚未连接" in svc.db_tables()["error"]
        assert "尚未连接" in svc.db_table_schema("t")["error"]
        assert "尚未连接" in svc.db_query("select 1")["error"]
        assert "尚未连接" in svc.db_execute("create table t(x)")["error"]

    def test_connect_then_query_uses_connected_db(self, tmp_path):
        svc = self._connected(tmp_path)
        cur = svc.db_current()
        assert cur["connected"] and cur["database"].endswith("w.db") and "sqlite" in cur["label"]
        r = svc.db_execute("CREATE TABLE t(id INTEGER PRIMARY KEY, name TEXT NOT NULL DEFAULT 'x')")
        assert "error" not in r
        assert svc.db_execute("INSERT INTO t(name) VALUES ('a'), ('b')")["affected_rows"] == 2
        q = svc.db_query("SELECT id, name FROM t ORDER BY id")
        assert q["columns"] == ["id", "name"] and q["rows"] == [[1, "a"], [2, "b"]]
        assert q["row_count"] == 2 and q["truncated"] is False and "error" not in q
        # 另一个 WebService 实例也看到同一当前连接（进程级）
        assert make_service().db_tables() == {"tables": ["t"]}

    def test_tables_and_schema(self, tmp_path):
        svc = self._connected(tmp_path)
        assert svc.db_tables() == {"tables": []}
        svc.db_execute("CREATE TABLE b(x INTEGER)")
        svc.db_execute("CREATE TABLE a(id INTEGER PRIMARY KEY, n TEXT NOT NULL, d REAL DEFAULT 1.5)")
        assert svc.db_tables()["tables"] == ["a", "b"]
        sc = svc.db_table_schema("a")
        assert sc["table"] == "a" and [c["name"] for c in sc["columns"]] == ["id", "n", "d"]
        assert sc["columns"][0]["primary_key"] is True and sc["columns"][1]["not_null"] is True
        assert sc["columns"][2]["default_value"] == "1.5"
        assert "不存在" in svc.db_table_schema("zzz")["error"]
        assert svc.db_table_schema("")["error"] == "请选择表"

    def test_query_rejects_write_and_reports_sql_error(self, tmp_path):
        svc = self._connected(tmp_path)
        assert "只接受 SELECT" in svc.db_query("DELETE FROM t")["error"]
        r = svc.db_query("SELECT * FROM nope")
        assert "no such table" in r["error"] and r["rows"] == []
        e = svc.db_execute("INSERT INTO nope VALUES (1)")
        assert "no such table" in e["error"]
        assert svc.db_execute("")["error"] == "请输入 SQL 语句"

    def test_query_truncates_rows(self, tmp_path, monkeypatch):
        svc = self._connected(tmp_path)
        monkeypatch.setattr(WebService, "DB_MAX_ROWS", 3)
        svc.db_execute("CREATE TABLE n(x INTEGER)")
        svc.db_execute("INSERT INTO n VALUES (1),(2),(3),(4),(5)")
        q = svc.db_query("SELECT x FROM n")
        assert len(q["rows"]) == 3 and q["row_count"] == 5 and q["truncated"] is True

    def test_read_prefixes_accept_with_and_pragma(self, tmp_path):
        svc = self._connected(tmp_path)
        assert "error" not in svc.db_query("WITH c AS (SELECT 1 AS v) SELECT v FROM c")
        assert "error" not in svc.db_query("PRAGMA table_info(sqlite_master)")

    def test_disconnect(self, tmp_path):
        svc = self._connected(tmp_path)
        assert svc.db_disconnect().startswith("[成功]")
        assert svc.db_current()["connected"] is False

    def test_db_schema_text_passthrough(self, monkeypatch):
        reg = _FakeRegistry("[表] t")
        import sys as _sys
        fake_at = MagicMock()
        fake_at.registry = reg
        monkeypatch.setitem(_sys.modules, "agent_tools", fake_at)
        svc = make_service()
        assert svc.db_schema(" t ") == "[表] t"
        assert reg.calls[0] == ("database_get_schema", {"table": "t"}, False)

    def test_errors_wrapped(self, monkeypatch):
        svc = make_service()
        monkeypatch.setattr(svc, "_db_executor", lambda: (_ for _ in ()).throw(RuntimeError("boom")))
        assert svc.db_tables()["error"] == "boom"
        assert svc.db_table_schema("t")["error"] == "boom"
        assert svc.db_query("select 1")["error"] == "boom"
        assert svc.db_execute("delete from t")["error"] == "boom"
        monkeypatch.setattr(svc, "_db_session", lambda: (_ for _ in ()).throw(RuntimeError("s-boom")))
        assert svc.db_current()["error"] == "s-boom"
        assert svc.db_disconnect().startswith("[错误]")


def _init_git_repo(path, commits=2, author="Tester"):
    def git(*args):
        subprocess.run(["git", *args], cwd=path, check=True, capture_output=True, text=True)

    git("init", "-q", "-b", "main")
    git("config", "user.email", "t@example.com")
    git("config", "user.name", author)
    for i in range(commits):
        (path / f"f{i}.txt").write_text(f"v{i}\n", encoding="utf-8")
        git("add", ".")
        git("commit", "-q", "-m", f"commit {i}")
    return git


class TestGitOverview:
    @pytest.fixture(autouse=True)
    def _real_git(self, monkeypatch):
        monkeypatch.setattr(subprocess, "run", _REAL_SUBPROCESS_RUN)
        monkeypatch.setattr(subprocess, "Popen", _REAL_SUBPROCESS_POPEN)

    def test_overview_fields(self, tmp_path):
        git = _init_git_repo(tmp_path, commits=3)
        (tmp_path / "f0.txt").write_text("changed\n", encoding="utf-8")   # 修改
        (tmp_path / "new.txt").write_text("n\n", encoding="utf-8")        # 未跟踪
        svc = make_service()
        ov = svc.git_overview(str(tmp_path))
        assert ov["is_repo"] is True and ov["branch"] == "main"
        assert len(ov["commits"]) == 3 and ov["commits"][0]["subject"] == "commit 2"
        assert set(ov["commits"][0]) == {"hash7", "author", "date", "subject"}
        assert len(ov["commits"][0]["hash7"]) >= 7
        assert ov["authors"] == [{"name": "Tester", "commits": 3}]
        assert ov["last_commit_at"]
        changed = {c["path"]: c["label"] for c in ov["changed"]}
        assert changed == {"f0.txt": "修改", "new.txt": "未跟踪"}

    def test_overview_rename_uses_new_path(self, tmp_path):
        git = _init_git_repo(tmp_path, commits=1)
        git("mv", "f0.txt", "renamed.txt")
        ov = make_service().git_overview(str(tmp_path))
        assert ov["changed"] == [{"status": "R", "label": "重命名", "path": "renamed.txt"}]

    def test_overview_max_commits(self, tmp_path):
        _init_git_repo(tmp_path, commits=5)
        ov = make_service().git_overview(str(tmp_path), max_commits=2)
        assert len(ov["commits"]) == 2 and ov["authors"][0]["commits"] == 5

    def test_non_repo(self, tmp_path):
        ov = make_service().git_overview(str(tmp_path))
        assert ov == {"is_repo": False, "branch": "", "changed": [], "commits": [], "authors": [], "last_commit_at": ""}

    def test_empty_repo_without_commits(self, tmp_path):
        subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
        ov = make_service().git_overview(str(tmp_path))
        assert ov["is_repo"] is True and ov["commits"] == [] and ov["last_commit_at"] == ""

    def test_exception_wrapped(self, monkeypatch):
        import sys as _sys

        broken = MagicMock()
        broken.GitAnalyzer.side_effect = RuntimeError("git-boom")
        monkeypatch.setitem(_sys.modules, "git_integration.git_analyzer", broken)
        ov = make_service().git_overview(".")
        assert ov["is_repo"] is False and ov["error"] == "git-boom"


class TestAiExplain:
    def test_prompt_by_kind(self):
        svc = make_service()
        p = svc.build_explain_prompt("db", "SELECT 1", "为什么")
        assert p.startswith("解读下面的 SQL") and "SELECT 1" in p and "问题：为什么" in p and "≤300 字" in p
        assert svc.build_explain_prompt("unknown", "x").startswith("解读下面的代码分析结果")
        assert "问题：" not in svc.build_explain_prompt("git", "x")

    def test_payload_truncated(self):
        svc = make_service()
        p = svc.build_explain_prompt("file", "a" * 10000)
        assert p.count("a") == WebService.AI_EXPLAIN_MAX_PAYLOAD

    def test_stream_answer_and_done(self):
        calls = []

        def fake_complete(prompt, **kw):
            calls.append((prompt, kw))
            return "  这是解读  "

        svc = make_service(complete_text=fake_complete)
        events = list(svc.ai_explain_stream("git", "log…"))
        kinds = [e.kind for e in events]
        assert kinds[0] == "progress" and kinds[-2:] == ["answer", "done"]
        answer = events[-2]
        assert answer.message == "这是解读" and answer.data == {"kind": "git"}
        assert calls[0][1] == {"num_predict": WebService.AI_EXPLAIN_NUM_PREDICT}
        assert not svc.is_running()

    def test_stream_empty_payload(self):
        svc = make_service(complete_text=lambda p, **k: pytest.fail("不应调用"))
        events = list(svc.ai_explain_stream("code", "   "))
        assert events == [StreamEvent("error", "没有可解读的内容，请先执行一次操作")]

    def test_stream_busy(self):
        svc = make_service(complete_text=lambda p, **k: pytest.fail("不应调用"))
        svc._running = True
        events = list(svc.ai_explain_stream("code", "x"))
        assert len(events) == 1 and events[0].kind == "error" and "进行中" in events[0].message

    def test_stream_llm_error_and_empty(self):
        def boom(p, **k):
            raise RuntimeError("ollama down")

        svc = make_service(complete_text=boom)
        events = list(svc.ai_explain_stream("shell", "ls"))
        assert events[-1].kind == "error" and "ollama down" in events[-1].message
        svc = make_service(complete_text=lambda p, **k: "")
        events = list(svc.ai_explain_stream("shell", "ls"))
        assert events[-1] == StreamEvent("error", "模型没有返回内容")

    def test_stream_cancel(self):
        import threading

        started = threading.Event()
        release = threading.Event()

        def slow(p, **k):
            started.set()
            release.wait(5)
            return "late"

        svc = make_service(complete_text=slow)
        svc.heartbeat_interval = 0.01
        gen = svc.ai_explain_stream("db", "sql")
        first = next(gen)
        assert first.kind == "progress"
        started.wait(2)
        assert svc.stop_current()
        rest = list(gen)
        release.set()
        assert any(e.kind == "cancelled" for e in rest)
        assert not any(e.kind == "answer" for e in rest)


class TestShellAndFiles:
    def _svc(self, monkeypatch, reg, analyze=None):
        import sys as _sys
        fake_at = MagicMock()
        fake_at.registry = reg
        fake_at.CommandSafetyChecker.analyze = analyze or (lambda cmd: {
            "command": cmd, "is_dangerous": "rm -rf" in cmd, "danger_reasons": ["危险"] if "rm -rf" in cmd else [],
            "needs_confirm": not cmd.startswith("ls"), "risk_level": "low" if cmd.startswith("ls") else "high",
        })
        monkeypatch.setitem(_sys.modules, "agent_tools", fake_at)
        return make_service()

    def test_exec_analyze_and_run(self, monkeypatch):
        reg = _FakeRegistry("out")
        svc = self._svc(monkeypatch, reg)
        assert svc.exec_analyze("ls")["risk_level"] == "low"
        assert "error" in svc.exec_analyze("")
        assert svc.exec_run("ls") == "out"
        assert reg.calls[0] == ("execute_command", {"command": "ls"}, True)
        assert "[错误] 该命令被安全系统拦截" in svc.exec_run("rm -rf /")
        assert svc.exec_run("").startswith("[提示]")

    def test_write(self, monkeypatch):
        reg = _FakeRegistry("content")
        svc = self._svc(monkeypatch, reg)
        svc.write_file("b.txt", "hi", append=True)
        assert reg.calls[-1] == ("write_file", {"path": "b.txt", "content": "hi", "append": True}, True)
        assert svc.write_file("", "x").startswith("[提示]")

    def test_cwd_chdir(self, tmp_path, monkeypatch):
        import os
        svc = make_service()
        old = os.getcwd()
        try:
            assert svc.chdir(str(tmp_path)).startswith("[成功]")
            assert svc.cwd() == str(tmp_path.resolve()) or svc.cwd().endswith(tmp_path.name)
            assert "[错误] 目录不存在" in svc.chdir("/definitely/not/here")
            assert svc.chdir("").startswith("[提示]")
        finally:
            os.chdir(old)

    def test_list_tools(self, monkeypatch):
        import sys as _sys
        fake_at = MagicMock()
        fake_at.registry.tools = {"read_file": {"safe": True, "description": "读", "parameters": {"path": "p"}}}
        monkeypatch.setitem(_sys.modules, "agent_tools", fake_at)
        tools = make_service().list_tools()
        assert tools == [{"name": "read_file", "safe": True, "description": "读", "parameters": {"path": "p"}}]

    def test_env_info_has_keys(self):
        info = make_service().env_info()
        assert "ollama_url" in info and "cwd" in info and "app_version" in info

    def test_env_info_exposes_allowed_dirs(self, tmp_path, monkeypatch):
        """F10 P0-1-d：service 暴露读 / 写允许目录，供系统页展示。"""
        proj = tmp_path / "proj"
        extra = tmp_path / "ro"
        proj.mkdir()
        extra.mkdir()
        monkeypatch.chdir(proj)
        monkeypatch.delenv("WRITE_ALLOWED_DIRS", raising=False)
        monkeypatch.setenv("READ_ALLOWED_DIRS", str(extra))
        info = make_service().env_info()
        assert str(proj.resolve()) in info["write_allowed_dirs"]
        assert str(extra.resolve()) in info["read_allowed_dirs"]
        assert set(info["write_allowed_dirs"]) <= set(info["read_allowed_dirs"])


class _FakeFM:
    def __init__(self, path, size=100, h=None, ptype="permanent"):
        self.file_path = path
        self.file_size = size
        self.file_hash = h
        self.persistence_type = ptype
        self.upload_time = "2026-09-03T10:00:00.123"
        self.last_access = None
        self.access_count = 1
        self.document_count = 1
        self.chunk_count = 3
        self.tags = ["t"]


class _FakeFileManager:
    def __init__(self, files):
        self.files = files
        self.removed = []
        self.cleaned = False

    def list_files(self):
        return list(self.files)

    def get_file_metadata(self, path):
        return next((f for f in self.files if f.file_path == path), None)

    def get_files_to_cleanup(self):
        return [f for f in self.files if f.persistence_type == "temporary"]

    def cleanup_files(self):
        self.cleaned = True
        return [f.file_path for f in self.get_files_to_cleanup()]

    def remove_file(self, path):
        self.removed.append(path)

    @staticmethod
    def _format_size(n):
        return f"{n} B"


class TestFileManagement:
    def _patch(self, monkeypatch, files):
        import sys as _sys
        mgr = _FakeFileManager(files)
        fake = MagicMock()
        fake.get_global_metadata_manager = lambda: mgr
        monkeypatch.setitem(_sys.modules, "file_metadata", fake)
        return mgr

    def test_list_and_info(self, monkeypatch):
        self._patch(monkeypatch, [_FakeFM("/a.md")])
        svc = make_service()
        rows = svc.file_list()
        assert rows[0]["path"] == "/a.md" and rows[0]["size"] == "100 B"
        assert rows[0]["upload_time"] == "2026-09-03 10:00:00" and rows[0]["chunk_count"] == 3
        assert svc.file_info("/a.md")["tags"] == ["t"]
        assert "error" in svc.file_info("/missing")
        assert "error" in svc.file_info("")

    def test_cleanup(self, monkeypatch):
        mgr = self._patch(monkeypatch, [_FakeFM("/a", ptype="temporary"), _FakeFM("/b")])
        svc = make_service()
        assert [p["path"] for p in svc.file_cleanup_preview()] == ["/a"]
        assert svc.file_cleanup() == "[成功] 已清理 1 个文件" and mgr.cleaned
        mgr.files = [_FakeFM("/b")]
        assert svc.file_cleanup().startswith("[提示]")

    def test_dedupe(self, monkeypatch):
        mgr = self._patch(monkeypatch, [_FakeFM("/a", h="h1"), _FakeFM("/b", h="h1"), _FakeFM("/c", h=None)])
        svc = make_service()
        dups = svc.file_duplicates()
        assert [d["path"] for d in dups] == ["/b"] and dups[0]["duplicate_of"] == "/a"
        assert svc.file_deduplicate() == "[成功] 已移除 1 个重复登记"
        assert mgr.removed == ["/b"]
        mgr.files = [_FakeFM("/a", h="h1")]
        assert svc.file_deduplicate().startswith("[提示]")

    def test_errors(self, monkeypatch):
        import sys as _sys
        fake = MagicMock()
        fake.get_global_metadata_manager = MagicMock(side_effect=RuntimeError("fm-boom"))
        monkeypatch.setitem(_sys.modules, "file_metadata", fake)
        svc = make_service()
        assert svc.file_list()[0]["path"].startswith("[错误]")
        assert svc.file_cleanup_preview()[0]["path"].startswith("[错误]")
        assert svc.file_duplicates()[0]["path"].startswith("[错误]")
        assert svc.file_cleanup().startswith("[错误]")
        assert svc.file_deduplicate().startswith("[错误]")
        assert "error" in svc.file_info("/x")


class TestStructuredLists:
    def test_snapshot_list_data(self, monkeypatch):
        import sys as _sys
        fake = MagicMock()
        fake.KnowledgeSnapshotManager.return_value.list_snapshots.return_value = [
            {"snapshot_id": "s1", "timestamp": "t", "document_count": 2, "total_chunks": 5, "trigger": "manual"},
        ]
        monkeypatch.setitem(_sys.modules, "knowledge_snapshot", fake)
        rows = make_service().snapshot_list_data()
        assert rows == [{"snapshot_id": "s1", "timestamp": "t", "document_count": 2, "total_chunks": 5, "trigger": "manual"}]

    def test_snapshot_list_data_error(self, monkeypatch):
        import sys as _sys
        fake = MagicMock()
        fake.KnowledgeSnapshotManager.side_effect = RuntimeError("no")
        monkeypatch.setitem(_sys.modules, "knowledge_snapshot", fake)
        assert make_service().snapshot_list_data()[0]["snapshot_id"].startswith("[错误]")

    def test_knowledge_summary_data(self, monkeypatch):
        import sys as _sys
        fake = MagicMock()
        fake.KnowledgeToSkillsEngine.return_value.get_document_summary.return_value = [
            {"file_name": "a.md", "file_path": "/a.md", "is_generic": True, "confidence": 0.5,
             "chunk_count": 2, "topics": ["x", "y"]},
        ]
        monkeypatch.setitem(_sys.modules, "knowledge_to_skills", fake)
        rows = make_service().knowledge_summary_data()
        assert rows[0]["kind"] == "通用" and rows[0]["topics"] == "x, y"

    def test_knowledge_summary_data_error(self, monkeypatch):
        import sys as _sys
        fake = MagicMock()
        fake.KnowledgeToSkillsEngine.side_effect = RuntimeError("no")
        monkeypatch.setitem(_sys.modules, "knowledge_to_skills", fake)
        assert make_service().knowledge_summary_data()[0]["file_name"].startswith("[错误]")

    def test_model_table(self):
        switcher = MagicMock()
        switcher.current_model_info.return_value = {
            "model": "b", "num_ctx": 1, "think": False, "loaded": True, "size_bytes": 1,
            "loaded_models": ["b"],
        }
        switcher.list_installed_models.return_value = ["a", "b"]
        rows = make_service(model_switcher_factory=lambda: switcher).model_table()
        assert rows == [{"name": "a", "current": False, "loaded": False},
                        {"name": "b", "current": True, "loaded": True}]


class TestRagStreamFallbackKind:
    """F8 P2-5：``kind="fallback"`` 与 ``fallback_question`` 透传到 answer 事件。"""

    def test_fallback_kind_and_question_passthrough(self, monkeypatch):
        import rag_pipeline

        def fake_answer_question(engine, question, **kwargs):
            return {
                "kind": "fallback", "answer": "无… 建议：/agent q 让 Agent 用工具进一步查找",
                "kb_sources": [], "web_sources": [], "meta": None, "rewritten": None,
                "fallback_question": "q",
            }

        monkeypatch.setattr(rag_pipeline, "answer_question", fake_answer_question)
        svc = make_service()
        events = list(svc.rag_query_stream("q"))
        answer = [e for e in events if e.kind == "answer"][-1]
        assert answer.data["kind"] == "fallback" and answer.data["fallback_question"] == "q"
        assert "/agent q" in answer.message

    def test_refs_passthrough_in_sources(self, monkeypatch):
        import rag_pipeline

        def fake_answer_question(engine, question, **kwargs):
            return {
                "kind": "answer", "answer": "a[1][W1]", "meta": None, "rewritten": None,
                "kb_sources": [{"file": "f", "content": "c", "score": 0.5, "ref": "1"}],
                "web_sources": [{"title": "t", "url": "u", "ref": "W1"}],
            }

        monkeypatch.setattr(rag_pipeline, "answer_question", fake_answer_question)
        svc = make_service()
        result = svc.rag_query("q")
        assert result["sources"][0]["ref"] == "1" and result["web_sources"][0]["ref"] == "W1"
        assert result["kind"] == "answer"


# ==================== F8 P3-3：自动路由 chat_auto_stream ====================

def _fake_rag_answer(monkeypatch, answer="回答"):
    import rag_pipeline

    calls = []

    def fake_answer_question(engine, question, **kwargs):
        calls.append((question, kwargs))
        return {
            "kind": "answer", "answer": answer, "kb_sources": [{"file": "f", "content": "c", "score": 0.5}],
            "web_sources": [], "meta": None, "rewritten": None,
        }

    monkeypatch.setattr(rag_pipeline, "answer_question", fake_answer_question)
    return calls


class TestChatAutoStream:
    def test_empty_input(self):
        assert list(make_service().chat_auto_stream("  ")) == [StreamEvent("error", "输入不能为空")]

    def test_rag_intent_dispatches_to_rag_with_routed_mode(self, monkeypatch):
        calls = _fake_rag_answer(monkeypatch)
        svc = make_service()
        events = list(svc.chat_auto_stream("什么是 RAG？", enable_web_search=False))
        route = events[0]
        assert route.kind == "progress" and route.message.startswith("🧭 自动路由：按 RAG 处理")
        assert route.data["phase"] == "route" and route.data["routed_mode"] == "rag"
        answer = [e for e in events if e.kind == "answer"][-1]
        assert answer.message == "回答"
        assert answer.data["routed_mode"] == "rag" and answer.data["route_reason"].startswith("规则：")
        # P2 字段透传不变
        assert answer.data["kind"] == "answer" and answer.data["sources"][0]["file"] == "f"
        assert "fallback_question" in answer.data
        assert calls and calls[0][1]["enable_web_search"] is False

    def test_agent_intent_dispatches_to_agent(self, monkeypatch):
        import rag_pipeline
        monkeypatch.setattr(rag_pipeline, "answer_question",
                            MagicMock(side_effect=AssertionError("RAG 不应被调用")))
        svc = make_service()
        events = list(svc.chat_auto_stream("修改 main.py 加日志"))
        assert events[0].message.startswith("🧭 自动路由：按 Agent 处理")
        assert any(e.kind == "step" for e in events)
        answer = events[-1]
        assert answer.kind == "answer" and answer.message == "最终答案"
        assert answer.data["routed_mode"] == "agent" and "动词" in answer.data["route_reason"]
        assert "step_log" in answer.data and "context" in answer.data

    def test_agent_confirm_policy_auto_confirm(self):
        captured = {}

        def factory(on_step=None, on_confirm=None, context=None):
            captured["on_confirm"] = on_confirm
            return FakeReact(on_step=on_step, on_confirm=on_confirm, context=context)

        svc = make_service(react_factory=factory)
        list(svc.chat_auto_stream("修改 main.py", auto_confirm=True))
        assert captured["on_confirm"]({"tool": "rm"}) is True

    def test_agent_confirm_policy_default_reject_when_not_interactive(self):
        captured = {}

        def factory(on_step=None, on_confirm=None, context=None):
            captured["on_confirm"] = on_confirm
            return FakeReact(on_step=on_step, on_confirm=on_confirm, context=context)

        svc = make_service(react_factory=factory)
        list(svc.chat_auto_stream("修改 main.py", auto_confirm=False, interactive_confirm=False))
        assert captured["on_confirm"]({"tool": "rm"}) is False

    def test_agent_confirm_interactive_pushes_confirm_event(self):
        svc = make_service(
            react_factory=lambda on_step=None, on_confirm=None, context=None: _ConfirmingReact(
                on_step=on_step, on_confirm=on_confirm, context=context
            )
        )
        import threading
        events = []

        def consume():
            for e in svc.chat_auto_stream("删除 tmp.txt", interactive_confirm=True):
                events.append(e)
                if e.kind == "confirm":
                    svc.resolve_confirm(True)

        t = threading.Thread(target=consume)
        t.start()
        t.join(timeout=10)
        assert not t.is_alive()
        assert any(e.kind == "confirm" for e in events)
        assert events[-1].kind == "answer" and events[-1].data["routed_mode"] == "agent"

    def test_ambiguous_uses_intent_llm_once_and_falls_back(self, monkeypatch):
        import intent_router
        calls = []

        def fake_llm(prompt, num_predict=4, timeout=5):
            calls.append((num_predict, timeout))
            raise TimeoutError("slow")

        monkeypatch.setattr(intent_router, "_llm_complete", fake_llm)
        _fake_rag_answer(monkeypatch)
        svc = make_service()
        events = list(svc.chat_auto_stream("helloworld"))
        assert calls == [(4, 5)]
        assert events[-1].data["routed_mode"] == "rag" and "默认 RAG" in events[-1].data["route_reason"]

    def test_kb_unavailable_ambiguous_goes_agent_without_llm(self, monkeypatch):
        import intent_router
        monkeypatch.setattr(intent_router, "_llm_complete",
                            MagicMock(side_effect=AssertionError("不应调用 LLM")))
        rag = FakeRAG()
        rag.retriever = None
        svc = make_service(rag=rag)
        assert svc.kb_available() is False
        events = list(svc.chat_auto_stream("helloworld"))
        assert events[-1].kind == "answer" and events[-1].data["routed_mode"] == "agent"

    def test_kb_available_and_engine_failure(self):
        def boom():
            raise RuntimeError("no engine")
        svc = make_service(rag_factory=boom)
        assert svc.kb_available() is False

    def test_classify_intent_error_falls_back_rag(self, monkeypatch):
        import intent_router
        monkeypatch.setattr(intent_router, "classify_intent", MagicMock(side_effect=RuntimeError("x")))
        svc = make_service()
        mode, reason = svc.classify_intent("修改 main.py")
        assert mode == "rag" and "判定失败" in reason

    def test_session_id_passthrough(self, monkeypatch):
        _fake_rag_answer(monkeypatch)
        sm = make_session_manager()
        svc = make_service(session_manager=sm)
        sid = svc.create_session("t")
        events = list(svc.chat_auto_stream("什么是 RAG？", session_id=sid))
        assert events[-1].data["context"]  # 已写入会话并带上下文指标
        assert [m["content"] for m in svc.chat_history(sid)] == ["什么是 RAG？", "回答"]


# ==================== F8 P4：代码感知分块（入库文案 / 进度流 / 文件元数据 / 系统页）====================

class TestCodeAwareIngest:
    def test_add_documents_summary_uses_ingest_stats(self):
        rag = FakeRAG()
        rag.ingest_stats = {
            "/a.py": {"chunk_count": 10, "symbol_count": 8, "chunk_strategy": "code(python)"},
            "/b.md": {"chunk_count": 3, "symbol_count": 0, "chunk_strategy": "text"},
        }
        svc = make_service(rag=rag)
        msg = svc.add_documents(["/a.py", "/b.md"])
        assert msg.startswith("[成功] 已入库 2 个文件 · 13 个片段")
        assert "1 个代码文件按函数/类切分，共 8 个符号" in msg

    def test_add_documents_hint_once_when_code_chunking_disabled(self, monkeypatch):
        import code_chunker
        code_chunker.reset_hint()
        monkeypatch.setattr(code_chunker, "_load_pack", lambda: None)
        monkeypatch.setattr(code_chunker, "CODE_AWARE_CHUNKING", True)
        rag = FakeRAG()
        rag.ingest_stats = {"/a.py": {"chunk_count": 2, "symbol_count": 0, "chunk_strategy": "text"}}
        svc = make_service(rag=rag)
        first = svc.add_documents(["/a.py"])
        assert "💡" in first and "tree-sitter-language-pack" in first
        second = svc.add_documents(["/a.py"])
        assert "💡" not in second
        # 非代码文件不提示
        code_chunker.reset_hint()
        rag.ingest_stats = {"/b.md": {"chunk_count": 2, "symbol_count": 0, "chunk_strategy": "text"}}
        assert "💡" not in svc.add_documents(["/b.md"])
        code_chunker.reset_hint()
        code_chunker.reset_availability_cache()

    def test_add_path_summary_and_graph_note(self):
        rag = FakeRAG()
        rag.ingest_stats = {"/d/x.py": {"chunk_count": 4, "symbol_count": 3, "chunk_strategy": "code(python)"}}
        rag.last_graph_derived = True
        svc = make_service(rag=rag)
        msg = svc.add_path("/d")
        assert msg.startswith("[成功] 已入库 1 个文件 · 4 个片段（其中 1 个代码文件")
        assert "已同步更新知识图谱" in msg

    def test_add_path_without_stats_keeps_legacy_text(self):
        svc = make_service()
        msg = svc.add_path("/d")
        assert "已入库 1 个文件，共 1 个片段" in msg

    def test_ingest_stream_upload_emits_progress_then_answer(self):
        rag = FakeRAG()
        rag.ingest_stats = {"/a.py": {"chunk_count": 2, "symbol_count": 1, "chunk_strategy": "code(python)"}}
        svc = make_service(rag=rag)
        events = list(svc.ingest_stream(file_paths=["/a.py"]))
        kinds = [e.kind for e in events]
        assert kinds.count("progress") == 2 and kinds[-1] == "answer"
        stages = [e.data.get("stage") for e in events if e.kind == "progress"]
        assert stages == ["chunk", "embed"]
        assert events[-1].message.startswith("[成功]")
        assert rag.added[0][1] == ["/a.py"]

    def test_ingest_stream_path_mode_and_error(self):
        svc = make_service()
        events = list(svc.ingest_stream(path="/docs", file_types=".md"))
        assert events[-1].kind == "answer" and "[成功]" in events[-1].message
        rag = FakeRAG()
        rag.raise_on_add = True
        svc = make_service(rag=rag)
        events = list(svc.ingest_stream(path="/docs"))
        assert events[-1].kind == "answer" and events[-1].message.startswith("[错误]")

    def test_ingest_stream_worker_exception_becomes_error_event(self):
        def bad_loader(p, file_types=None):
            raise SystemExit("boom")
        svc = make_service(load_documents=bad_loader)
        events = list(svc.ingest_stream(path="/docs"))
        # add_path 捕获 BaseException 返回 [错误]；此处验证流不会中断
        assert events[-1].kind in ("answer", "error")

    def test_file_meta_dict_includes_chunking_fields(self):
        from web.services import _describe_chunking
        manager = MagicMock()
        manager._format_size.return_value = "1 KB"
        fm = MagicMock(file_path="/k/a.py", file_size=10, persistence_type="permanent", upload_time="2026-01-01T00:00:00",
                       last_access="", access_count=1, document_count=1, chunk_count=9, tags=[], file_hash="h",
                       chunk_strategy="code(python)", symbol_count=7)
        d = WebService._file_meta_dict(manager, fm)
        assert d["chunk_strategy"] == "code(python)" and d["symbol_count"] == 7
        assert d["chunking"] == "代码(python) · 7 个符号" and d["chunking_short"] == "代码"
        fm2 = MagicMock(file_path="/k/a.md", chunk_strategy="text", symbol_count=0)
        assert _describe_chunking(fm2, short=True) == "文本"
        assert _describe_chunking(fm2) == "文本"

    def test_env_info_has_self_check(self, monkeypatch):
        import config
        monkeypatch.setattr(config, "RAG_SELF_CHECK", True, raising=False)
        assert make_service().env_info()["self_check"] is True
        monkeypatch.setattr(config, "RAG_SELF_CHECK", False, raising=False)
        assert make_service().env_info()["self_check"] is False

    def test_env_info_has_code_chunking(self):
        svc = make_service()
        info = svc.env_info()
        assert "code_chunking" in info
        assert info["code_chunking"].startswith("启用") or info["code_chunking"].startswith("未启用")

    def test_code_chunking_env_text_disabled(self, monkeypatch):
        import code_chunker
        from web.services import _code_chunking_env_text
        monkeypatch.setattr(code_chunker, "_load_pack", lambda: None)
        code_chunker.reset_availability_cache()
        assert _code_chunking_env_text().startswith("未启用：")
        code_chunker.reset_availability_cache()


# ==================== F9 P2：AI 主入口（服务层） ====================

class _KwReact(FakeReact):
    """记录工厂收到的全部关键字参数（断言 allowed_tools / max_iterations 透传）。"""

    captured = []

    def __init__(self, on_step=None, on_confirm=None, context=None, **kw):
        super().__init__(on_step=on_step, on_confirm=on_confirm, context=context,
                         answer=kw.pop("answer", "助手答案"), steps=kw.pop("steps", None))
        self.kwargs = kw
        _KwReact.captured.append({"context": context, **kw})


class TestReactFactoryPassthrough:
    def test_default_factory_passes_restrictions(self, monkeypatch):
        import sys as _sys
        created = {}

        class FakeEngine:
            def __init__(self, **kw):
                created.update(kw)

        monkeypatch.setitem(_sys.modules, "react_engine", SimpleNamespace(ReActEngine=FakeEngine))
        services._default_react_factory(on_step="s", on_confirm="c", context="ctx",
                                        allowed_tools=["read_file"], system_prompt_extra="X", max_iterations=12)
        assert created == {"on_step": "s", "on_confirm": "c", "context": "ctx", "allowed_tools": {"read_file"},
                           "system_prompt_extra": "X", "max_iterations": 12}
        created.clear()
        services._default_react_factory()
        assert created == {"on_step": None, "on_confirm": None, "context": None}

    def test_scratch_context(self):
        ctx = services.ScratchContext()
        assert ctx.build_messages("sys") == [{"role": "system", "content": "sys"}]
        assert ctx.build_messages() == []
        assert ctx.record("q", "a", trace="t") is None and ctx.clear() is True


class TestCodeAssist:
    @pytest.fixture(autouse=True)
    def _reset(self, tmp_path, monkeypatch):
        _KwReact.captured = []
        monkeypatch.setenv("READ_ALLOWED_DIRS", str(tmp_path))  # F10 P0-1：读边界
        yield

    def _svc(self, **kw):
        return make_service(react_factory=lambda **k: _KwReact(**k, **kw))

    def test_prompt_by_action(self):
        svc = make_service()
        p = svc.build_code_assist_prompt("review", "src/x.py", "看异常")
        assert p.startswith("角色：代码助手。目标路径：src/x.py。用户补充：看异常") and "动作 = review" in p
        assert "严重度" in p and "只读" in p and "文件内容" not in p
        p2 = svc.build_code_assist_prompt("explain", "a.py", "", content="print(1)")
        assert "内容已给出，勿再 read_file" in p2 and p2.endswith("文件内容：\nprint(1)")
        assert "用户补充：无" in p2
        assert "动作 = bogus" in svc.build_code_assist_prompt("bogus", "a", "")

    def test_stream_inlines_small_file_and_passes_restrictions(self, tmp_path):
        f = tmp_path / "m.py"
        f.write_text("def f():\n    return 1\n", encoding="utf-8")
        svc = self._svc(steps=[{"message": "读取中", "phase": "thinking"}])
        events = list(svc.code_assist_stream("explain", str(f), "简短"))
        kinds = [e.kind for e in events]
        assert "step" in kinds and kinds[-2:] == ["answer", "done"]
        ans = events[-2]
        assert ans.message == "助手答案" and ans.data["action"] == "explain" and ans.data["path"] == str(f)
        assert ans.data["step_log"]
        cap = _KwReact.captured[0]
        assert cap["allowed_tools"] == set(WebService.CODE_ASSIST_TOOLS)
        assert cap["max_iterations"] == 12
        assert "def f()" in cap["system_prompt_extra"] and "勿再 read_file" in cap["system_prompt_extra"]
        assert isinstance(cap["context"], services.ScratchContext)
        assert not svc.is_running() and svc._active_react is None

    def test_stream_directory_not_inlined(self, tmp_path):
        (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
        svc = self._svc()
        events = list(svc.code_assist_stream("review", str(tmp_path)))
        assert events[-1].kind == "done"
        assert "文件内容" not in _KwReact.captured[0]["system_prompt_extra"]

    def test_stream_large_file_not_inlined(self, tmp_path):
        f = tmp_path / "big.py"
        f.write_text("x = 1\n" * 2000, encoding="utf-8")
        svc = self._svc()
        list(svc.code_assist_stream("docs", str(f)))
        assert "文件内容" not in _KwReact.captured[0]["system_prompt_extra"]

    def test_stream_errors(self, tmp_path):
        svc = self._svc()
        assert list(svc.code_assist_stream("explain", str(tmp_path / "nope.py"))) == [
            StreamEvent("error", f"路径不存在: {tmp_path / 'nope.py'}")]
        bad = list(svc.code_assist_stream("fly", str(tmp_path)))
        assert bad[0].kind == "error" and "未知动作" in bad[0].message
        svc._running = True
        busy = list(svc.code_assist_stream("explain", str(tmp_path)))
        assert busy == [StreamEvent("error", "有任务进行中，请先停止或等待完成")]
        assert _KwReact.captured == []

    def test_stream_engine_failure_and_empty(self, tmp_path):
        svc = make_service(react_factory=lambda **k: _KwReact(**k, answer="", steps=[]))
        events = list(svc.code_assist_stream("tests", str(tmp_path)))
        assert events[-1] == StreamEvent("error", "模型没有返回内容")

        class Boom(FakeReact):
            def __init__(self, **k):
                super().__init__(raise_error=True)

        svc = make_service(react_factory=lambda **k: Boom(**k))
        events = list(svc.code_assist_stream("tests", str(tmp_path)))
        assert events[-1].kind == "error" and "agent-boom" in events[-1].message

    def test_stream_confirm_always_rejected(self, tmp_path):
        seen = {}

        class Asking(FakeReact):
            def __init__(self, on_step=None, on_confirm=None, context=None, **k):
                super().__init__(on_step=on_step, on_confirm=on_confirm, context=context)

            def chat(self, user_input):
                seen["confirm"] = self.on_confirm({"tool": "write_file"})
                seen["task"] = user_input
                return "ok"

        svc = make_service(react_factory=lambda **k: Asking(**k))
        list(svc.code_assist_stream("refactor", str(tmp_path), "  少改  "))
        assert seen["confirm"] is False and "重构建议" in seen["task"] and "补充：少改" in seen["task"]


class TestCodeSymbolsAndQuality:
    @pytest.fixture(autouse=True)
    def _allow_tmp(self, tmp_path, monkeypatch):
        monkeypatch.setenv("READ_ALLOWED_DIRS", str(tmp_path))  # F10 P0-1：读边界

    @pytest.fixture
    def proj(self, tmp_path):
        (tmp_path / "a.py").write_text(
            "class Base:\n    pass\n\n"
            "class Child(Base):\n    def run(self, size: int) -> str:\n        if size:\n            return 'x'\n        return ''\n\n"
            "def helper(size, name) -> int:\n    return 1\n",
            encoding="utf-8",
        )
        (tmp_path / "b.py").write_text("def other(x):\n    return x\n", encoding="utf-8")
        return tmp_path

    def test_symbols_by_name_file_and_dir(self, proj):
        svc = make_service()
        out = svc.code_symbols("helper", str(proj / "a.py"))
        assert [s["name"] for s in out["symbols"]] == ["helper"]
        s = out["symbols"][0]
        assert s["kind"] == "函数" and s["line"] == 10 and s["complexity"] == 1 and s["file"].endswith("a.py")
        out = svc.code_symbols("Base", str(proj))
        assert {(s["name"], s["kind"]) for s in out["symbols"]} == {("Base", "类")}
        out = svc.code_symbols("o", str(proj))  # 目录：跨文件
        assert {s["name"] for s in out["symbols"]} >= {"other"}

    def test_symbols_respect_search_by(self, proj):
        svc = make_service()
        by_param = svc.code_symbols("size", str(proj), "parameter")
        assert {s["name"] for s in by_param["symbols"]} == {"run", "helper"}
        by_base = svc.code_symbols("Base", str(proj), "base")
        assert [s["name"] for s in by_base["symbols"]] == ["Child"]
        assert by_base["symbols"][0]["complexity"] == 2  # run 的圈复杂度
        by_method = svc.code_symbols("run", str(proj), "method")
        assert [s["name"] for s in by_method["symbols"]] == ["Child"]
        by_ret = svc.code_symbols("int", str(proj / "a.py"), "return")
        assert [s["name"] for s in by_ret["symbols"]] == ["helper"]
        # search_by 生效：按名称搜 "size" 不命中任何符号
        assert svc.code_symbols("size", str(proj), "name")["symbols"] == []

    def test_symbols_errors_and_truncation(self, proj, monkeypatch):
        svc = make_service()
        assert svc.code_symbols("", str(proj))["error"] == "请输入搜索模式"
        assert "路径不存在" in svc.code_symbols("x", str(proj / "zz"))["error"]
        monkeypatch.setattr(WebService, "CODE_SYMBOLS_MAX", 1)
        out = svc.code_symbols("e", str(proj))
        assert len(out["symbols"]) == 1 and out["truncated"] is True

    def test_symbols_analyzer_failure(self, proj, monkeypatch):
        import sys as _sys
        monkeypatch.setitem(_sys.modules, "code_analyzer", SimpleNamespace(
            get_ast_analyzer=lambda: (_ for _ in ()).throw(RuntimeError("ast down"))))
        svc_err = make_service().code_symbols("x", str(proj))
        assert "ast down" in svc_err["error"]

    def test_quality_report_file_and_dir(self, proj):
        svc = make_service()
        rep = svc.code_quality_report(str(proj / "a.py"))
        assert "error" not in rep and rep["files"] == 1 and 0 <= rep["score"] <= 100
        assert set(rep["severity"]) == {"critical", "error", "warning", "info"}
        assert rep["total_issues"] == len(rep["issues"]) or rep["truncated"]
        for issue in rep["issues"]:
            assert {"severity", "file", "line", "message"} <= set(issue)
        rep_dir = svc.code_quality_report(str(proj))
        assert rep_dir["files"] == 2 and rep_dir["path"] == str(proj)

    def test_quality_report_errors(self, tmp_path):
        svc = make_service()
        assert "路径不存在" in svc.code_quality_report(str(tmp_path / "no"))["error"]
        empty = tmp_path / "empty"
        empty.mkdir()
        assert "没有可检查" in svc.code_quality_report(str(empty))["error"]

    def test_quality_report_sorted_and_truncated(self, proj, monkeypatch):
        from code_analyzer.quality_checker import QualityIssue, QualityReport, Severity
        svc = make_service()

        class FakeChecker:
            def check_file(self, path):
                rep = QualityReport(file_path=path)
                rep.add_issue(QualityIssue(path, 5, 0, Severity.INFO, "i", "t"))
                rep.add_issue(QualityIssue(path, 2, 0, Severity.CRITICAL, "c", "t"))
                rep.add_issue(QualityIssue(path, 9, 0, Severity.WARNING, "w", "t"))
                return rep

            def get_project_summary(self, reports):
                return {"total_files": 1, "total_issues": 3, "average_score": 77.5,
                        "severity_breakdown": {"critical": 1, "warning": 1, "info": 1}}

        import sys as _sys
        monkeypatch.setitem(_sys.modules, "code_analyzer", SimpleNamespace(get_quality_checker=lambda: FakeChecker()))
        rep = svc.code_quality_report(str(proj / "a.py"))
        assert [i["severity"] for i in rep["issues"]] == ["critical", "warning", "info"]
        assert rep["score"] == 77.5 and rep["severity"]["error"] == 0 and rep["truncated"] is False
        monkeypatch.setattr(WebService, "CODE_QUALITY_MAX_ISSUES", 2)
        rep = svc.code_quality_report(str(proj / "a.py"))
        assert len(rep["issues"]) == 2 and rep["truncated"] is True


class TestDbNl2Sql:
    @pytest.fixture(autouse=True)
    def _clean(self):
        from database_tools import session

        session.clear_current()
        yield
        session.clear_current()

    def _connected(self, tmp_path, complete):
        svc = make_service(complete_text=complete)
        assert svc.db_connect(str(tmp_path / "n.db")).startswith("[成功]")
        svc.db_execute("CREATE TABLE users(id INTEGER PRIMARY KEY, name TEXT NOT NULL)")
        svc.db_execute("CREATE TABLE orders(id INTEGER PRIMARY KEY, uid INTEGER, amount REAL)")
        return svc

    def test_sql_kind(self):
        k = WebService.sql_kind
        assert k("SELECT 1") == "select" and k("  with x as (select 1) select * from x") == "select"
        assert k("(SELECT 1)") == "select" and k("PRAGMA table_info(t)") == "select"
        assert k("insert into t values (1)") == "write" and k("DROP TABLE t") == "write"
        assert k("") == "invalid" and k("hello world") == "invalid"

    def test_schema_text(self, tmp_path):
        svc = self._connected(tmp_path, lambda p, **k: "")
        text = svc.db_schema_text()
        assert text.splitlines() == ["orders(id INTEGER PRIMARY KEY, uid INTEGER, amount REAL)",
                                     "users(id INTEGER PRIMARY KEY, name TEXT)"]
        assert len(svc.db_schema_text(max_chars=10)) == 10
        svc.db_disconnect()
        assert svc.db_schema_text() == ""

    def test_nl2sql_select_with_fence(self, tmp_path):
        calls = []

        def fake(prompt, **kw):
            calls.append((prompt, kw))
            return "```sql\nSELECT COUNT(*) FROM users;\n```"

        svc = self._connected(tmp_path, fake)
        out = svc.db_nl2sql("用户有多少")
        assert out == {"sql": "SELECT COUNT(*) FROM users;", "kind": "select", "note": ""}
        prompt, kw = calls[0]
        assert prompt.startswith("你是 SQLite 专家") and "users(id INTEGER PRIMARY KEY" in prompt
        assert prompt.endswith("问题：用户有多少")
        assert kw == {"num_predict": WebService.DB_NL2SQL_NUM_PREDICT, "temperature": 0}

    def test_nl2sql_write_and_dangerous_notes(self, tmp_path):
        svc = self._connected(tmp_path, lambda p, **k: "INSERT INTO users(name) VALUES ('a')")
        out = svc.db_nl2sql("加个用户 a")
        assert out["kind"] == "write" and out["note"] == "这是写操作，运行前需确认"
        svc = self._connected(tmp_path, lambda p, **k: "DELETE FROM users WHERE id = 1")
        out = svc.db_nl2sql("删掉 1 号")
        assert out["kind"] == "write" and "高危" in out["note"]

    def test_nl2sql_invalid_and_failures(self, tmp_path):
        svc = self._connected(tmp_path, lambda p, **k: "抱歉，我不知道")
        out = svc.db_nl2sql("？")
        assert out["kind"] == "invalid" and out["sql"] == "抱歉，我不知道" and "未生成可识别" in out["note"]

        def boom(p, **k):
            raise RuntimeError("down")

        svc = self._connected(tmp_path, boom)
        out = svc.db_nl2sql("x")
        assert out == {"sql": "", "kind": "invalid", "note": "生成失败: down"}
        assert svc.db_nl2sql("  ")["note"] == "请输入自然语言描述"
        svc.db_disconnect()
        assert "尚未连接" in svc.db_nl2sql("x")["note"]

    def test_nl2sql_keeps_first_statement(self, tmp_path):
        svc = self._connected(tmp_path, lambda p, **k: "SELECT 1; SELECT 2;")
        assert svc.db_nl2sql("q")["sql"] == "SELECT 1;"
        svc = self._connected(tmp_path, lambda p, **k: "```\nselect name from users\n```\n说明：…")
        assert svc.db_nl2sql("q")["sql"] == "select name from users"

    def test_sql_kind_ignores_leading_comments(self):
        k = WebService.sql_kind
        assert k("-- 在此手写 SQL\nSELECT 1") == "select" and k("-- only comment") == "invalid"
        assert k("-- c\n\n  insert into t values(1)") == "write"
        assert WebService._sql_head("") == "" and WebService._sql_head("-- a\n-- b") == ""

    def test_db_query_with_leading_comment(self, tmp_path):
        svc = self._connected(tmp_path, lambda p, **k: "")
        r = svc.db_query("-- 注释\nSELECT COUNT(*) AS n FROM users")
        assert "error" not in r and r["rows"] == [[0]]
        assert svc.db_query("-- 仅注释")["error"] == "请输入 SQL 查询语句"

    def test_strip_fences(self):
        s = WebService._strip_fences
        assert s("```sql\nSELECT 1\n```") == "SELECT 1"
        assert s("SELECT 1") == "SELECT 1" and s("") == ""
        assert s("```\nls -la\n```") == "ls -la"


class TestWorkspaceBrowse:
    @pytest.fixture(autouse=True)
    def _allow_tmp(self, tmp_path, monkeypatch):
        monkeypatch.setenv("READ_ALLOWED_DIRS", str(tmp_path))  # F10 P0-1：读边界

    @pytest.fixture
    def tree(self, tmp_path):
        (tmp_path / "src").mkdir()
        (tmp_path / "docs").mkdir()
        (tmp_path / ".git").mkdir()
        (tmp_path / "README.md").write_text("hello world\nsecond needle line\n", encoding="utf-8")
        (tmp_path / ".hidden").write_text("x", encoding="utf-8")
        (tmp_path / "src" / "main.py").write_text("needle = 1\nprint(needle)\n", encoding="utf-8")
        (tmp_path / "src" / "data.bin").write_bytes(b"needle")
        (tmp_path / "docs" / "note.txt").write_text("nothing\n", encoding="utf-8")
        return tmp_path

    def test_list_dir_sorted_dirs_first_and_hidden(self, tree):
        svc = make_service()
        out = svc.list_dir(str(tree))
        assert out["path"] == str(tree) and out["parent"] == str(tree.parent) and "error" not in out
        assert [(e["kind"], e["name"]) for e in out["entries"]] == [("dir", "docs"), ("dir", "src"), ("file", "README.md")]
        readme = out["entries"][-1]
        # 用 stat 而非 len(文本)：Windows 文本模式写入把 \n 转成 \r\n，磁盘字节数与字符数不等
        assert readme["size"] == (tree / "README.md").stat().st_size and len(readme["mtime"]) == 16
        assert out["entries"][0]["size"] == 0
        with_hidden = svc.list_dir(str(tree), show_hidden=True)
        assert {e["name"] for e in with_hidden["entries"]} == {".git", "docs", "src", ".hidden", "README.md"}
        assert with_hidden["entries"][0]["name"] == ".git"

    def test_list_dir_errors_and_root(self, tree):
        svc = make_service()
        out = svc.list_dir(str(tree / "nope"))
        assert out["entries"] == [] and "路径不存在" in out["error"]
        out = svc.list_dir(str(tree / "README.md"))
        assert "不是目录" in out["error"]
        fs_root = os.path.abspath(os.sep)  # POSIX 为 /，Windows 为当前盘根（如 D:\\）
        root = svc.list_dir(fs_root)
        assert root["path"] == fs_root and root["parent"] == fs_root
        assert "路径超出允许范围" in root["error"] and root["entries"] == []  # F10 P0-1：根目录越界
        assert svc.list_dir("")["path"] == __import__("os").getcwd()

    def test_list_dir_truncated(self, tree, monkeypatch):
        monkeypatch.setattr(WebService, "DIR_MAX_ENTRIES", 2)
        out = make_service().list_dir(str(tree))
        assert len(out["entries"]) == 2 and out["truncated"] is True

    def test_file_preview_pages(self, tmp_path):
        f = tmp_path / "f.txt"
        f.write_text("".join(f"L{i}\n" for i in range(1, 451)), encoding="utf-8")
        svc = make_service()
        p0 = svc.file_preview(str(f))
        assert p0["pages"] == 3 and p0["total_lines"] == 450 and p0["start"] == 0 and p0["end"] == 200
        assert p0["content"].startswith("L1\n") and p0["content"].endswith("L200\n")
        p2 = svc.file_preview(str(f), 2)
        assert p2["page"] == 2 and p2["start"] == 400 and p2["end"] == 450 and p2["content"].endswith("L450\n")
        assert svc.file_preview(str(f), 99)["page"] == 2  # 越界收敛到最后一页
        assert svc.file_preview(str(f), -3)["page"] == 0
        assert svc.file_preview(str(f), 0, page_size=1000)["pages"] == 1
        empty = tmp_path / "e.txt"
        empty.write_text("", encoding="utf-8")
        pe = svc.file_preview(str(empty))
        assert pe["pages"] == 1 and pe["total_lines"] == 0 and pe["content"] == ""

    def test_file_preview_errors(self, tmp_path):
        svc = make_service()
        assert svc.file_preview("")["error"] == "请选择文件"
        assert "文件不存在" in svc.file_preview(str(tmp_path / "no.txt"))["error"]
        assert "是目录" in svc.file_preview(str(tmp_path))["error"]

    def test_search_in_dir(self, tree):
        svc = make_service()
        hits = svc.search_in_dir("needle", str(tree))
        assert [(Path(h["file"]).name, h["line"]) for h in hits] == [("README.md", 2), ("main.py", 1), ("main.py", 2)]
        assert hits[0]["text"] == "second needle line"
        # rel 为 OS 原生相对路径（Windows 反斜杠），比较时统一成 POSIX 形式
        assert [Path(h["rel"]).as_posix() for h in hits] == ["README.md", "src/main.py", "src/main.py"]
        assert all(h["file"].startswith(str(tree)) for h in hits)
        assert svc.search_in_dir("needle", str(tree), max_results=2) == hits[:2]
        assert svc.search_in_dir("", str(tree)) == [] and svc.search_in_dir("x", str(tree / "no")) == []
        assert svc.search_in_dir("zzz", str(tree)) == []

    def test_search_skips_git_and_long_lines(self, tree):
        (tree / ".git" / "cfg.txt").write_text("needle\n", encoding="utf-8")
        (tree / "long.md").write_text("needle " + "x" * 500 + "\n", encoding="utf-8")
        hits = make_service().search_in_dir("needle", str(tree))
        assert all(".git" not in h["file"] for h in hits)
        long_hit = next(h for h in hits if h["file"].endswith("long.md"))
        assert len(long_hit["text"]) == WebService.SEARCH_MAX_LINE


class TestShellGenerate:
    def test_first_line_and_fences(self):
        calls = []

        def fake(prompt, **kw):
            calls.append((prompt, kw))
            return "```bash\n$ ls -lS | head -5\necho done\n```"

        svc = make_service(complete_text=fake)
        assert svc.shell_generate("列出最大的 5 个文件") == {"command": "ls -lS | head -5", "note": ""}
        prompt, kw = calls[0]
        assert prompt.startswith("把需求转成一条") and "当前目录：" in prompt and prompt.endswith("需求：列出最大的 5 个文件")
        assert "rm -rf" in prompt and kw == {"num_predict": WebService.SHELL_GEN_NUM_PREDICT, "temperature": 0}

    def test_dollar_prefix_and_blank_lines(self):
        svc = make_service(complete_text=lambda p, **k: "\n\n$git status\n")
        assert svc.shell_generate("看状态")["command"] == "git status"

    def test_empty_and_failure(self):
        assert make_service(complete_text=lambda p, **k: "   ").shell_generate("x") == {"command": "", "note": "未生成"}
        assert make_service(complete_text=lambda p, **k: "```\n```").shell_generate("x")["note"] == "未生成"
        assert make_service(complete_text=lambda p, **k: "x").shell_generate("  ")["note"] == "请输入需求描述"

        def boom(p, **k):
            raise RuntimeError("down")

        assert make_service(complete_text=boom).shell_generate("x") == {"command": "", "note": "生成失败: down"}



# ==================== F9 P3：连接记忆 / 命令历史 / 提交增强 ====================

class TestToolsStateIntegration:
    """P3-1 / P3-2：``db_connect`` 成功后记最近库；``exec_run`` 成功后记命令；读失败回退空。"""

    @pytest.fixture(autouse=True)
    def _clean(self):
        from database_tools import session

        session.clear_current()
        yield
        session.clear_current()

    def _svc(self, tmp_path):
        from web.tools_state import ToolsState

        svc = make_service()
        svc._tools_state = ToolsState(tmp_path / "state" / "web_tools_state.json")
        return svc

    def test_default_state_path_via_runtime_paths(self, tmp_path):
        import runtime_paths as rp

        rp.set_app_state_root(tmp_path / "root")
        try:
            svc = make_service()
            assert svc.tools_state.path == tmp_path / "root" / "web_tools_state.json"
            assert svc.recent_databases() == [] and svc.shell_history() == []
        finally:
            rp.set_app_state_root(None)

    def test_db_connect_remembers_only_on_success(self, tmp_path):
        svc = self._svc(tmp_path)
        assert svc.db_connect(str(tmp_path / "a.db")).startswith("[成功]")
        assert svc.db_connect(str(tmp_path / "b.db")).startswith("[成功]")
        assert svc.recent_databases() == [str(tmp_path / "b.db"), str(tmp_path / "a.db")]
        assert svc.db_connect(str(tmp_path / "a.db")).startswith("[成功]")
        assert svc.recent_databases() == [str(tmp_path / "a.db"), str(tmp_path / "b.db")]  # 去重、最新在前
        assert svc.db_connect(":memory:").startswith("[成功]")
        assert ":memory:" not in svc.recent_databases()
        assert svc.db_connect("").startswith("[提示]")
        assert len(svc.recent_databases()) == 2
        assert (tmp_path / "state" / "web_tools_state.json").exists()

    def test_db_connect_failure_not_remembered(self, tmp_path, monkeypatch):
        svc = self._svc(tmp_path)
        monkeypatch.setattr(svc, "run_tool", lambda *a, **k: "[错误] 连接失败")
        assert svc.db_connect("/nope.db").startswith("[错误]")
        assert svc.recent_databases() == []

    def test_exec_run_remembers_successful_commands(self, tmp_path, monkeypatch):
        import sys as _sys

        svc = self._svc(tmp_path)
        outputs = {"ls": "a\nb", "pwd": "/x", "false": "[退出码] 1", "cat nope": "[错误] 执行失败"}
        reg = MagicMock()
        reg.execute.side_effect = lambda name, args, auto_confirm=False: outputs[args["command"]]
        fake_at = MagicMock()
        fake_at.registry = reg
        fake_at.CommandSafetyChecker.analyze = lambda cmd: {"is_dangerous": False, "needs_confirm": False,
                                                          "risk_level": "low", "danger_reasons": []}
        monkeypatch.setitem(_sys.modules, "agent_tools", fake_at)
        svc.exec_run("ls")
        svc.exec_run("pwd")
        svc.exec_run("false")      # 非零退出码不记
        svc.exec_run("cat nope")   # 工具层错误不记
        svc.exec_run("ls")         # 去重并提前
        assert svc.shell_history() == ["ls", "pwd"]

    def test_exec_succeeded(self):
        assert WebService.exec_succeeded("ok") is True
        assert WebService.exec_succeeded("") is True
        assert WebService.exec_succeeded("[错误] x") is False
        assert WebService.exec_succeeded("[提示] x") is False
        assert WebService.exec_succeeded("out\n[退出码] 2") is False
        assert WebService.exec_succeeded("[退出码] 1") is False

    def test_read_failures_fall_back_to_empty(self):
        svc = make_service()
        broken = MagicMock()
        broken.recent_databases.side_effect = RuntimeError("io")
        broken.shell_history.side_effect = RuntimeError("io")
        broken.remember_database.side_effect = RuntimeError("io")
        broken.remember_command.side_effect = RuntimeError("io")
        svc._tools_state = broken
        assert svc.recent_databases() == [] and svc.shell_history() == []
        # 记录失败不影响主流程返回值
        assert svc.db_connect(":memory:").startswith("[成功]")


class TestGitCommitFlow:
    """P3-3：暂存预览 / AI 生成提交信息 / 提交（真实临时仓库）。"""

    @pytest.fixture(autouse=True)
    def _real_git(self, monkeypatch):
        monkeypatch.setattr(subprocess, "run", _REAL_SUBPROCESS_RUN)
        monkeypatch.setattr(subprocess, "Popen", _REAL_SUBPROCESS_POPEN)

    def test_preview_empty_and_staged(self, tmp_path):
        git = _init_git_repo(tmp_path, commits=1)
        svc = make_service()
        pv = svc.git_commit_preview(str(tmp_path))
        assert pv["is_repo"] is True and pv["has_staged"] is False and pv["staged_files"] == []
        (tmp_path / "f0.txt").write_text("changed\nmore\n", encoding="utf-8")
        (tmp_path / "new.txt").write_text("n\n", encoding="utf-8")
        git("add", ".")
        pv = svc.git_commit_preview(str(tmp_path))
        assert pv["has_staged"] is True
        assert {f["path"]: f["label"] for f in pv["staged_files"]} == {"f0.txt": "修改", "new.txt": "新增"}
        assert pv["files_changed"] == 2 and pv["insertions"] == 3 and pv["deletions"] == 1
        assert "2 files changed" in pv["diff_stat"]

    def test_preview_rename_and_non_repo(self, tmp_path, tmp_path_factory):
        git = _init_git_repo(tmp_path, commits=1)
        git("mv", "f0.txt", "renamed.txt")
        pv = make_service().git_commit_preview(str(tmp_path))
        assert pv["staged_files"][0]["path"] == "renamed.txt" and pv["staged_files"][0]["label"] == "重命名"
        other = tmp_path_factory.mktemp("plain")  # 独立目录（tmp_path 子目录仍在仓库工作区内）
        pv = make_service().git_commit_preview(str(other))
        assert pv["is_repo"] is False and pv["has_staged"] is False

    def test_preview_exception_wrapped(self, monkeypatch):
        import sys as _sys

        broken = MagicMock()
        broken.GitAnalyzer.side_effect = RuntimeError("git-boom")
        monkeypatch.setitem(_sys.modules, "git_integration.git_analyzer", broken)
        pv = make_service().git_commit_preview(".")
        assert pv["is_repo"] is False and pv["error"] == "git-boom"

    def test_commit_message_paths(self, tmp_path, monkeypatch):
        import sys as _sys

        git = _init_git_repo(tmp_path, commits=1)
        svc = make_service()
        r = svc.git_commit_message(str(tmp_path))
        assert "暂存区为空" in r["error"] and r["message"] == ""
        (tmp_path / "f0.txt").write_text("changed\n", encoding="utf-8")
        git("add", ".")
        fake_mod = MagicMock()
        fake_mod.CommitMessageGenerator.return_value.generate_commit_message.return_value = SimpleNamespace(
            title=" feat: 改动 ", body=" 说明 ", conventional_type="feat")
        monkeypatch.setitem(_sys.modules, "git_integration.commit_generator", fake_mod)
        r = svc.git_commit_message(str(tmp_path))
        assert r == {"title": "feat: 改动", "body": "说明", "message": "feat: 改动\n\n说明"}
        fake_mod.CommitMessageGenerator.return_value.generate_commit_message.assert_called_with(use_ai=True)
        fake_mod.CommitMessageGenerator.return_value.generate_commit_message.return_value = SimpleNamespace(
            title="fix: x", body="", conventional_type=None)
        assert svc.git_commit_message(str(tmp_path))["message"] == "fix: x"
        fake_mod.CommitMessageGenerator.return_value.generate_commit_message.return_value = SimpleNamespace(
            title="No changes staged", body="…")
        assert "暂存区为空" in svc.git_commit_message(str(tmp_path))["error"]
        fake_mod.CommitMessageGenerator.side_effect = RuntimeError("down")
        assert "生成提交信息失败: down" in svc.git_commit_message(str(tmp_path))["error"]

    def test_commit_message_non_repo_and_error(self, tmp_path_factory, monkeypatch):
        other = tmp_path_factory.mktemp("plain")
        assert "不是 Git 仓库" in make_service().git_commit_message(str(other))["error"]
        svc = make_service()
        monkeypatch.setattr(svc, "git_commit_preview", lambda p=".": {"error": "boom"})
        assert svc.git_commit_message(".")["error"] == "boom"

    def test_commit_end_to_end(self, tmp_path):
        git = _init_git_repo(tmp_path, commits=1)
        svc = make_service()
        assert svc.git_commit("", str(tmp_path)).startswith("[提示]")
        assert "暂存区为空" in svc.git_commit("feat: x", str(tmp_path))
        (tmp_path / "f0.txt").write_text("changed\n", encoding="utf-8")
        git("add", ".")
        out = svc.git_commit("feat: 提交测试\n\n正文", str(tmp_path))
        assert out.startswith("[成功] 已提交 ") and "feat: 提交测试" in out
        ov = svc.git_overview(str(tmp_path))
        assert len(ov["commits"]) == 2 and ov["commits"][0]["subject"] == "feat: 提交测试" and ov["changed"] == []
        assert svc.git_commit_preview(str(tmp_path))["has_staged"] is False

    def test_commit_non_repo_and_failures(self, tmp_path_factory, monkeypatch):
        other = tmp_path_factory.mktemp("plain")
        assert "不是 Git 仓库" in make_service().git_commit("x", str(other))
        import sys as _sys

        broken = MagicMock()
        broken.GitAnalyzer.side_effect = RuntimeError("git-boom")
        monkeypatch.setitem(_sys.modules, "git_integration.git_analyzer", broken)
        assert make_service().git_commit("x", ".") == "[错误] 提交失败: git-boom"
        failing = MagicMock()
        failing.GitAnalyzer.return_value.commit.return_value = {"ok": False, "error": ""}
        monkeypatch.setitem(_sys.modules, "git_integration.git_analyzer", failing)
        assert make_service().git_commit("x", ".") == "[错误] 提交失败: 未知错误"

    def test_commit_safety_check(self, monkeypatch):
        import sys as _sys

        fake_at = MagicMock()
        fake_at.CommandSafetyChecker.analyze.return_value = {"is_dangerous": True, "risk_level": "critical"}
        monkeypatch.setitem(_sys.modules, "agent_tools", fake_at)
        assert make_service().git_commit("rm -rf /", ".") == "[错误] 提交信息包含危险内容，已拒绝"
        # 安全分析本身异常 → 按 medium 继续，走到 GitAnalyzer
        fake_at.CommandSafetyChecker.analyze.side_effect = RuntimeError("no checker")
        ok = MagicMock()
        ok.GitAnalyzer.return_value.commit.return_value = {"ok": True, "hash7": "abc1234", "subject": "s"}
        monkeypatch.setitem(_sys.modules, "git_integration.git_analyzer", ok)
        assert make_service().git_commit("msg", ".") == "[成功] 已提交 abc1234 · s"


class TestWorkspaceReadBoundary:
    """F10 P0-1 后续 #4b：Web「工具」页直接读文件 / 目录的 7 个入口与 Agent 共用同一读边界。

    此前 Agent 读 ``~/.ssh`` 被拦，但 Web 工作区输入同一路径可直接预览——两端不一致。
    """

    @pytest.fixture(autouse=True)
    def _scoped(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("WRITE_ALLOWED_DIRS", raising=False)
        monkeypatch.delenv("READ_ALLOWED_DIRS", raising=False)
        (tmp_path / "ok.py").write_text("def f():\n    return 1\n", encoding="utf-8")
        return tmp_path

    def test_path_read_error_helper(self, tmp_path):
        svc = make_service()
        assert svc.path_read_error("ok.py") is None
        err = svc.path_read_error("/etc/hosts")
        assert err and err.startswith("路径超出允许范围") and "READ_ALLOWED_DIRS" in err

    def test_list_dir_and_preview_and_search(self):
        svc = make_service()
        listing = svc.list_dir("/etc")
        assert "路径超出允许范围" in listing["error"] and listing["entries"] == []
        preview = svc.file_preview("/etc/hosts")
        assert "路径超出允许范围" in preview["error"] and preview["content"] == ""
        assert svc.search_in_dir("root", "/etc") == []
        # 范围内正常
        assert any(e["name"] == "ok.py" for e in svc.list_dir(".")["entries"])
        assert "return 1" in svc.file_preview("ok.py")["content"]
        assert svc.search_in_dir("return", ".")

    def test_code_symbols_and_quality(self):
        svc = make_service()
        assert "路径超出允许范围" in svc.code_symbols("f", "/etc")["error"]
        assert "路径超出允许范围" in svc.code_quality_report("/etc")["error"]
        assert svc.code_symbols("f", "ok.py")["symbols"]

    def test_graph_build_file(self):
        assert make_service().graph_build_file("@/etc/hosts").startswith("[错误] 路径超出允许范围")

    def test_code_assist_stream(self):
        events = list(make_service().code_assist_stream("explain", "/etc/hosts"))
        assert len(events) == 1 and events[0].kind == "error"
        assert "路径超出允许范围" in events[0].message

    def test_env_grants_access(self, tmp_path, monkeypatch):
        outside = tmp_path.parent / f"{tmp_path.name}_ws"
        outside.mkdir(exist_ok=True)
        (outside / "n.txt").write_text("needle\n", encoding="utf-8")
        svc = make_service()
        assert "路径超出允许范围" in svc.file_preview(str(outside / "n.txt"))["error"]
        monkeypatch.setenv("READ_ALLOWED_DIRS", str(outside))
        assert "needle" in svc.file_preview(str(outside / "n.txt"))["content"]
        assert svc.search_in_dir("needle", str(outside))
