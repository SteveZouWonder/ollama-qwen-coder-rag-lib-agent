#!/usr/bin/env python3
"""test_web_services.py — Web 服务层单元测试。

服务层是 Web 界面唯一与核心引擎交互的层。通过依赖注入把各引擎替换为
MagicMock/桩对象，在不启动真实 Ollama/ChromaDB 的前提下覆盖全部分支。
"""
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
    """模拟 ReActEngine。"""

    def __init__(self, on_step=None, on_confirm=None, answer="最终答案",
                 raise_error=False, steps=None):
        self.on_step = on_step
        self.on_confirm = on_confirm
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
        return self._answer

    def stop(self):
        self.stopped = True


def make_service(**overrides):
    """构造一个全部依赖被桩替换的 WebService。"""
    rag = overrides.pop("rag", FakeRAG())
    defaults = dict(
        rag_factory=lambda: rag,
        react_factory=lambda on_step=None, on_confirm=None: FakeReact(
            on_step=on_step, on_confirm=on_confirm
        ),
        orchestrator_factory=lambda: MagicMock(),
        session_manager_factory=lambda: MagicMock(),
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
        events = list(svc.rag_query_stream("什么是RAG"))
        kinds = [e.kind for e in events]
        assert "progress" in kinds
        assert kinds[-1] == "answer"
        answer_evt = events[-1]
        assert answer_evt.message == "答案:什么是RAG"
        assert answer_evt.data["sources"][0]["file"] == "f.md"

    def test_stream_error(self):
        rag = FakeRAG()
        rag.raise_on_query = True
        svc = make_service(rag=rag)
        events = list(svc.rag_query_stream("x"))
        assert events[-1].kind == "error"
        assert "检索失败" in events[-1].message

    def test_query_nonstream_success(self):
        svc = make_service()
        result = svc.rag_query("hi")
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
            lambda q: iter([StreamEvent("progress", "p")]),
        )
        result = svc.rag_query("hi")
        assert result == {"answer": "", "sources": []}


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
            react_factory=lambda on_step=None, on_confirm=None: FakeReact(
                on_step=on_step, on_confirm=on_confirm, raise_error=True
            )
        )
        events = list(svc.agent_chat_stream("x"))
        assert events[-1].kind == "error"
        assert "Agent 执行失败" in events[-1].message

    def test_confirm_handler_default_reject(self):
        """无 confirm_handler 时 on_confirm 默认返回 False。"""
        captured = {}

        def factory(on_step=None, on_confirm=None):
            captured["on_confirm"] = on_confirm
            return FakeReact(on_step=on_step, on_confirm=on_confirm)

        svc = make_service(react_factory=factory)
        list(svc.agent_chat_stream("x"))
        assert captured["on_confirm"]({"tool": "rm"}) is False

    def test_confirm_handler_used(self):
        captured = {}

        def factory(on_step=None, on_confirm=None):
            captured["on_confirm"] = on_confirm
            return FakeReact(on_step=on_step, on_confirm=on_confirm)

        svc = make_service(react_factory=factory)
        list(svc.agent_chat_stream("x", confirm_handler=lambda evt: True))
        assert captured["on_confirm"]({"tool": "rm"}) is True

    def test_stop_agent_when_active(self):
        svc = make_service()
        engine = FakeReact()
        svc._active_react = engine
        assert svc.stop_agent() is True
        assert engine.stopped is True

    def test_stop_agent_when_idle(self):
        svc = make_service()
        assert svc.stop_agent() is False


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
            react_factory=lambda on_step=None, on_confirm=None: FakeReact(),
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
        import sys as _sys
        fake_module = MagicMock()
        monkeypatch.setitem(_sys.modules, "session_manager", fake_module)
        services._default_session_manager_factory()
        fake_module.get_session_manager.assert_called_once()

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
