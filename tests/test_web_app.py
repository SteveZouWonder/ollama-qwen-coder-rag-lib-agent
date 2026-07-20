#!/usr/bin/env python3
"""test_web_app.py — Web 界面 UI 层的纯函数与处理器测试。

只测试不依赖 gradio 的部分：格式化辅助函数与 build_handlers 生成的处理器。
build_app / launch / main 是 gradio 装配代码，标注 pragma: no cover，不在此测试。
"""
from unittest.mock import MagicMock

from web import app
from web.app import (
    build_handlers,
    format_graph_result,
    format_multi_agent_result,
    format_sessions,
    format_sources,
    format_stats,
    serve_blocking,
)
from web.services import StreamEvent


# ==================== 格式化函数 ====================

class TestFormatSources:
    def test_empty(self):
        assert format_sources([]) == "_无引用来源_"

    def test_with_score_and_content(self):
        out = format_sources([
            {"file": "a.md", "score": 0.912, "content": "hello"},
        ])
        assert "a.md" in out
        assert "0.912" in out
        assert "hello" in out

    def test_without_score(self):
        out = format_sources([{"file": "a.md", "score": None, "content": ""}])
        assert "a.md" in out
        assert "相似度" not in out


class TestFormatStats:
    def test_error(self):
        assert format_stats({"error": "boom"}).startswith("[错误]")

    def test_normal(self):
        out = format_stats({
            "total_documents": 5, "llm_model": "qwen",
            "embed_model": "nomic", "chunk_size": 1024,
            "chunk_overlap": 200, "top_k": 10,
        })
        assert "**5**" in out
        assert "qwen" in out

    def test_missing_keys_use_defaults(self):
        out = format_stats({})
        assert "**0**" in out


class TestFormatMultiAgent:
    def test_failure(self):
        out = format_multi_agent_result({"success": False, "error": "e", "summary": "失败了"})
        assert "失败了" in out
        assert "e" in out

    def test_failure_default_summary(self):
        out = format_multi_agent_result({"success": False})
        assert "协作失败" in out

    def test_success_with_results(self):
        out = format_multi_agent_result({
            "success": True,
            "summary": "完成",
            "successful_results": 1,
            "total_results": 2,
            "results": [
                {"success": True, "agent_id": "code", "output": "done"},
                {"success": False, "agent_id": "test", "output": ""},
            ],
        })
        assert "完成" in out
        assert "code" in out
        assert "done" in out
        assert "test" in out

    def test_success_no_results(self):
        out = format_multi_agent_result({"success": True})
        assert "协作完成" in out


class TestFormatSessions:
    def test_empty(self):
        assert format_sessions([]) == "_暂无会话_"

    def test_current_marker(self):
        out = format_sessions([
            {"session_id": "abcdefgh12345", "title": "会话A", "messages": 3, "is_current": True},
            {"session_id": "zzz", "title": "会话B", "messages": 0, "is_current": False},
        ])
        assert "▶" in out
        assert "会话A" in out
        assert "会话B" in out


class TestFormatGraph:
    def test_empty_with_explanation(self):
        out = format_graph_result({"entities": [], "relations": [], "explanation": "无数据"})
        assert out == "无数据"

    def test_empty_no_explanation(self):
        out = format_graph_result({"entities": [], "relations": []})
        assert "未找到" in out

    def test_entities_and_relations(self):
        out = format_graph_result({
            "entities": [{"text": "Python", "entity_type": "language"}],
            "relations": [{
                "source": {"text": "Django"},
                "target": {"text": "Python"},
                "relation_type": "uses",
            }],
            "explanation": "说明",
        })
        assert "Python" in out
        assert "language" in out
        assert "Django" in out
        assert "uses" in out
        assert "说明" in out

    def test_only_entities(self):
        out = format_graph_result({
            "entities": [{"text": "X", "entity_type": "concept"}],
            "relations": [],
        })
        assert "X" in out
        assert "关系" not in out


# ==================== 处理器 ====================

def make_service_mock():
    svc = MagicMock()
    return svc


class TestHandlers:
    def test_on_chat_empty(self):
        h = build_handlers(make_service_mock())
        answer, side = h["on_chat"]("  ", "RAG 检索")
        assert answer == ""
        assert "请输入内容" in side

    def test_on_chat_rag_mode(self):
        svc = make_service_mock()
        svc.rag_query.return_value = {
            "answer": "回答", "sources": [{"file": "f", "score": 0.5, "content": "c"}],
        }
        h = build_handlers(svc)
        answer, side = h["on_chat"]("问题", "RAG 检索")
        assert answer == "回答"
        assert "f" in side

    def test_on_chat_single_agent(self):
        svc = make_service_mock()
        svc.agent_chat_stream.return_value = iter([
            StreamEvent("step", "思考中"),
            StreamEvent("answer", "最终答案"),
        ])
        h = build_handlers(svc)
        answer, side = h["on_chat"]("写代码", "单 Agent")
        assert answer == "最终答案"
        assert "执行过程" in side
        assert "思考中" in side

    def test_on_chat_single_agent_error(self):
        svc = make_service_mock()
        svc.agent_chat_stream.return_value = iter([StreamEvent("error", "炸了")])
        h = build_handlers(svc)
        answer, side = h["on_chat"]("x", "单 Agent")
        assert answer == ""
        assert "炸了" in side

    def test_on_chat_single_agent_no_steps(self):
        svc = make_service_mock()
        svc.agent_chat_stream.return_value = iter([StreamEvent("answer", "答案")])
        h = build_handlers(svc)
        answer, side = h["on_chat"]("x", "单 Agent")
        assert answer == "答案"
        assert side == ""

    def test_on_chat_multi_agent(self):
        svc = make_service_mock()
        svc.multi_agent_run.return_value = {"success": True, "summary": "ok"}
        h = build_handlers(svc)
        answer, side = h["on_chat"]("任务", "多 Agent 协作")
        assert answer == ""
        assert "ok" in side

    def test_on_upload(self):
        svc = make_service_mock()
        svc.add_documents.return_value = "已入库"
        svc.get_stats.return_value = {"total_documents": 1}
        h = build_handlers(svc)
        msg, stats = h["on_upload"](["/a.md"])
        assert msg == "已入库"
        assert "**1**" in stats

    def test_on_upload_none(self):
        svc = make_service_mock()
        svc.add_documents.return_value = "未选择"
        svc.get_stats.return_value = {"total_documents": 0}
        h = build_handlers(svc)
        msg, _ = h["on_upload"](None)
        svc.add_documents.assert_called_once_with([])

    def test_on_refresh_stats(self):
        svc = make_service_mock()
        svc.get_stats.return_value = {"total_documents": 7}
        h = build_handlers(svc)
        assert "**7**" in h["on_refresh_stats"]()

    def test_on_clear_index(self):
        svc = make_service_mock()
        svc.clear_index.return_value = "已清空"
        svc.get_stats.return_value = {"total_documents": 0}
        h = build_handlers(svc)
        msg, stats = h["on_clear_index"]()
        assert msg == "已清空"

    def test_on_list_sessions(self):
        svc = make_service_mock()
        svc.list_sessions.return_value = [
            {"session_id": "id1", "title": "T", "messages": 1, "is_current": True},
        ]
        h = build_handlers(svc)
        assert "T" in h["on_list_sessions"]()

    def test_on_create_session(self):
        svc = make_service_mock()
        svc.create_session.return_value = "newid123"
        svc.list_sessions.return_value = []
        h = build_handlers(svc)
        msg, sessions = h["on_create_session"]("标题")
        assert "newid123"[:8] in msg

    def test_on_query_graph(self):
        svc = make_service_mock()
        svc.query_graph_entity.return_value = {
            "entities": [{"text": "Y", "entity_type": "concept"}],
            "relations": [],
        }
        h = build_handlers(svc)
        assert "Y" in h["on_query_graph"]("Y")

    def test_on_stop_active(self):
        svc = make_service_mock()
        svc.stop_agent.return_value = True
        h = build_handlers(svc)
        assert "停止信号" in h["on_stop"]()

    def test_on_stop_idle(self):
        svc = make_service_mock()
        svc.stop_agent.return_value = False
        h = build_handlers(svc)
        assert "没有运行中" in h["on_stop"]()


# ==================== 优雅退出 ====================

class TestServeBlocking:
    def test_wait_returns_then_close_called(self):
        fake_app = MagicMock()
        calls = []
        serve_blocking(fake_app, wait=lambda: calls.append("waited"))
        assert calls == ["waited"]
        fake_app.close.assert_called_once()

    def test_keyboard_interrupt_still_closes(self):
        fake_app = MagicMock()

        def wait():
            raise KeyboardInterrupt()

        # 不应向外抛出 KeyboardInterrupt
        serve_blocking(fake_app, wait=wait)
        fake_app.close.assert_called_once()

    def test_close_error_is_swallowed(self):
        fake_app = MagicMock()
        fake_app.close.side_effect = RuntimeError("close-fail")
        # close 抛错不应影响退出流程
        serve_blocking(fake_app, wait=lambda: None)
        fake_app.close.assert_called_once()

    def test_app_without_close_is_ok(self):
        class NoClose:
            pass

        # app 没有 close 方法也不应报错
        serve_blocking(NoClose(), wait=lambda: None)


# ==================== 模块导出 ====================

def test_module_exports():
    assert hasattr(app, "build_app")
    assert hasattr(app, "launch")
    assert hasattr(app, "main")
    assert hasattr(app, "serve_blocking")
