#!/usr/bin/env python3
"""test_web_app.py — Web 界面 UI 层的纯函数与处理器测试。

只测试不依赖 gradio 的部分：格式化辅助函数与 build_handlers 生成的处理器。
build_app / launch / main 是 gradio 装配代码，标注 pragma: no cover，不在此测试。
"""
from unittest.mock import MagicMock

from web import app
from web.app import (
    ProgressTracker,
    build_handlers,
    format_elapsed,
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
    # 流式对话入口会先询问是否已有任务在跑；MagicMock 默认返回真值，需显式置 False
    svc.is_running.return_value = False
    # current_model 返回非 dict 时按"无状态提示"处理
    svc.current_model.return_value = {"model": "qwen", "loaded": True, "think": False}
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


# ==================== 进度跟踪器 ====================

class FakeClock:
    def __init__(self, t=0.0):
        self.t = t

    def __call__(self):
        return self.t


class TestFormatElapsed:
    def test_seconds(self):
        assert format_elapsed(0) == "0 秒"
        assert format_elapsed(42.7) == "42 秒"

    def test_minutes(self):
        assert format_elapsed(65) == "1 分 05 秒"
        assert format_elapsed(600) == "10 分 00 秒"

    def test_negative_clamped(self):
        assert format_elapsed(-3) == "0 秒"


class TestProgressTracker:
    def test_initial_status_shows_placeholder_and_elapsed(self):
        clock = FakeClock()
        t = ProgressTracker(clock=clock)
        clock.t = 12
        s = t.render_status()
        assert "准备中" in s
        assert "12 秒" in s
        assert t.render_steps() == ""

    def test_hint_appended_while_running_only(self):
        t = ProgressTracker(clock=FakeClock(), hint="思考模式已开")
        assert "思考模式已开" in t.render_status()
        assert "思考模式已开" not in t.render_status("done")

    def test_regular_events_append(self):
        t = ProgressTracker(clock=FakeClock())
        t.add("A", {"stage": "x"})
        t.add("B", {"stage": "y"})
        assert t.steps == ["A", "B"]
        assert t.current == "B"
        md = t.render_steps("处理过程")
        assert "1. A" in md and "2. B" in md

    def test_transient_events_do_not_append(self):
        """单 Agent 的 0.5s 推理心跳只刷新当前活动，不刷屏。"""
        t = ProgressTracker(clock=FakeClock())
        t.add("Step 1: 模型推理中...", {"phase": "thinking"})
        for i in range(10):
            t.add(f"模型推理中{'.' * (i % 4)}", {"phase": "thinking", "transient": True})
        assert t.steps == ["Step 1: 模型推理中..."]
        assert t.current.startswith("模型推理中")
        assert "模型推理中" in t.render_status()

    def test_counter_events_replace_last_line(self):
        """评分文档 1/5 … 5/5 原地刷新为一行。"""
        t = ProgressTracker(clock=FakeClock())
        t.add("检索知识库", {"stage": "kb_retrieving"})
        for i in range(1, 6):
            t.add(f"评分文档 {i}/5", {"phase": "scoring", "current": i, "total": 5})
        assert t.steps == ["检索知识库", "评分文档 5/5"]

    def test_counter_events_with_different_key_append(self):
        t = ProgressTracker(clock=FakeClock())
        t.add("执行子任务 1/2", {"stage": "execute", "current": 1, "total": 2})
        t.add("子任务 1/2 完成", {"stage": "task_done", "current": 1, "total": 2})
        t.add("执行子任务 2/2", {"stage": "execute", "current": 2, "total": 2})
        assert len(t.steps) == 3

    def test_same_key_without_counter_appends(self):
        """两条不同的搜索查询（同 stage、无计数）都应保留。"""
        t = ProgressTracker(clock=FakeClock())
        t.add("🔍 搜索查询: A", {"stage": "web_query", "query": "A"})
        t.add("🔍 搜索查询: B", {"stage": "web_query", "query": "B"})
        assert t.steps == ["🔍 搜索查询: A", "🔍 搜索查询: B"]

    def test_empty_message_ignored(self):
        t = ProgressTracker(clock=FakeClock())
        t.add("", {"stage": "x"})
        t.add("   ")
        assert t.steps == []

    def test_terminal_states(self):
        clock = FakeClock()
        t = ProgressTracker(clock=clock)
        clock.t = 70
        assert t.render_status("done") == "✅ 完成 · 用时 1 分 10 秒"
        assert "已停止" in t.render_status("cancelled")
        err = t.render_status("error", "未获得回答")
        assert "出错" in err and "未获得回答" in err

    def test_render_steps_done_marker(self):
        t = ProgressTracker(clock=FakeClock())
        t.add("A")
        assert "（已完成）" in t.render_steps("处理过程", done=True)
        assert "（已完成）" not in t.render_steps("处理过程")


# ==================== 流式对话处理器（点击后立即反馈）====================

def _rag_answer(msg="答案", **data):
    base = {"kind": "answer", "sources": [], "web_sources": []}
    base.update(data)
    return StreamEvent("answer", msg, base)


class TestChatStream:
    """``on_chat_stream`` yield 四元组 (answer, status, process, sources)。"""

    def _collect(self, gen):
        out = list(gen)
        for item in out:
            assert len(item) == 4, f"应为四元组: {item!r}"
        return out

    def test_empty_message(self):
        h = build_handlers(make_service_mock())
        out = self._collect(h["on_chat_stream"]("  ", "RAG 检索"))
        assert "请输入内容" in out[-1][1]

    def test_busy_service_rejects_new_request(self):
        svc = make_service_mock()
        svc.is_running.return_value = True
        h = build_handlers(svc)
        out = self._collect(h["on_chat_stream"]("问题", "RAG 检索"))
        assert len(out) == 1
        assert "已有任务在运行" in out[0][1]
        svc.rag_query_stream.assert_not_called()

    def test_rag_first_yield_is_status_with_elapsed(self):
        svc = make_service_mock()
        svc.rag_query_stream.return_value = iter([
            StreamEvent("progress", "检索知识库...", {"stage": "kb_retrieving"}),
            _rag_answer("答案"),
        ])
        h = build_handlers(svc)
        out = self._collect(h["on_chat_stream"]("问题", "RAG 检索"))
        # 第一条即为带耗时的状态行，而非静态"正在处理"
        assert out[0][1].startswith("⏳")
        assert "已用时" in out[0][1]
        # 最终一条：答案 + 完成状态 + 已完成的处理过程
        answer, status, process, _ = out[-1]
        assert answer == "答案"
        assert status.startswith("✅ 完成")
        assert "检索知识库" in process and "已完成" in process

    def test_rag_model_not_loaded_hint(self):
        svc = make_service_mock()
        svc.current_model.return_value = {"model": "qwen3.5:4b", "loaded": False, "think": True}
        svc.rag_query_stream.return_value = iter([_rag_answer("ok")])
        h = build_handlers(svc)
        out = self._collect(h["on_chat_stream"]("问题", "RAG 检索"))
        first_status = out[0][1]
        assert "首次加载模型" in first_status and "qwen3.5:4b" in first_status
        assert "思考模式已开" in first_status

    def test_rag_current_model_not_dict_is_tolerated(self):
        svc = make_service_mock()
        svc.current_model.return_value = MagicMock()
        svc.rag_query_stream.return_value = iter([_rag_answer("ok")])
        h = build_handlers(svc)
        out = self._collect(h["on_chat_stream"]("问题", "RAG 检索"))
        assert "准备中" in out[0][1]
        assert out[-1][0] == "ok"

    def test_rag_progress_then_answer_with_sources(self):
        svc = make_service_mock()
        svc.rag_query_stream.return_value = iter([
            StreamEvent("progress", "🌐 网络搜索中", {"stage": "web_search_start"}),
            _rag_answer(
                "最终",
                sources=[{"file": "f.md", "score": 0.9, "content": "c"}],
                web_sources=[{"title": "T", "url": "http://x"}],
            ),
        ])
        h = build_handlers(svc)
        out = self._collect(h["on_chat_stream"]("q", "RAG 检索", True, False))
        assert any("网络搜索中" in process for _, _, process, _ in out)
        answer, _, _, sources = out[-1]
        assert answer == "最终"
        assert "f.md" in sources and "http://x" in sources

    def test_rag_heartbeat_refreshes_status(self):
        svc = make_service_mock()
        svc.rag_query_stream.return_value = iter([
            StreamEvent("progress", "规划搜索", {"stage": "web_plan"}),
            StreamEvent("heartbeat", "", {"elapsed": 3.0}),
            StreamEvent("heartbeat", "", {"elapsed": 4.0}),
            _rag_answer("ok"),
        ])
        h = build_handlers(svc)
        out = self._collect(h["on_chat_stream"]("q", "RAG 检索"))
        # 首条状态 + 进度 + 两次心跳 + 最终 = 5 次 yield
        assert len(out) == 5
        # 心跳只刷新状态行，处理过程不新增条目
        assert out[2][2] == out[3][2]
        assert "规划搜索" in out[2][1]

    def test_rag_meta_query(self):
        svc = make_service_mock()
        svc.rag_query_stream.return_value = iter([
            StreamEvent("answer", "[知识库概览]", {"kind": "meta", "meta": {"files": [], "stats": {}}}),
        ])
        h = build_handlers(svc)
        out = self._collect(h["on_chat_stream"]("知识库里有什么", "RAG 检索"))
        assert "知识库概览" in out[-1][0]

    def test_rag_error(self):
        svc = make_service_mock()
        svc.rag_query_stream.return_value = iter([StreamEvent("error", "检索炸了")])
        h = build_handlers(svc)
        out = self._collect(h["on_chat_stream"]("q", "RAG 检索"))
        answer, status, _, _ = out[-1]
        assert "检索炸了" in answer
        assert status.startswith("❌")

    def test_rag_cancelled(self):
        svc = make_service_mock()
        svc.rag_query_stream.return_value = iter([
            StreamEvent("progress", "规划搜索", {"stage": "web_plan"}),
            StreamEvent("cancelled", "已停止"),
        ])
        h = build_handlers(svc)
        out = self._collect(h["on_chat_stream"]("q", "RAG 检索"))
        _, status, process, _ = out[-1]
        assert "已停止" in status
        assert "规划搜索" in process

    def test_rag_no_answer_event(self):
        svc = make_service_mock()
        svc.rag_query_stream.return_value = iter([StreamEvent("progress", "p")])
        h = build_handlers(svc)
        out = self._collect(h["on_chat_stream"]("q", "RAG 检索"))
        assert "未获得回答" in out[-1][1]

    def test_single_agent_stream(self):
        svc = make_service_mock()
        svc.agent_chat_stream.return_value = iter([
            StreamEvent("step", "第一步", {"phase": "thinking"}),
            StreamEvent("step", "模型推理中.", {"phase": "thinking", "transient": True}),
            StreamEvent("step", "模型推理中..", {"phase": "thinking", "transient": True}),
            StreamEvent("answer", "完成"),
        ])
        h = build_handlers(svc)
        out = self._collect(h["on_chat_stream"]("做事", "单 Agent", True, True))
        assert any("第一步" in process for _, _, process, _ in out)
        # 心跳出现在状态行，但不进入执行过程列表
        assert any("模型推理中" in status for _, status, _, _ in out)
        assert not any("模型推理中" in process for _, _, process, _ in out)
        answer, status, process, _ = out[-1]
        assert answer == "完成"
        assert "执行过程" in process
        # auto_confirm=True 时传入确认处理器
        _, kwargs = svc.agent_chat_stream.call_args
        assert kwargs["confirm_handler"] is not None

    def test_single_agent_default_rejects_confirm(self):
        svc = make_service_mock()
        svc.agent_chat_stream.return_value = iter([StreamEvent("answer", "x")])
        h = build_handlers(svc)
        self._collect(h["on_chat_stream"]("做事", "单 Agent"))
        _, kwargs = svc.agent_chat_stream.call_args
        assert kwargs["confirm_handler"] is None

    def test_multi_agent_stream(self):
        svc = make_service_mock()
        svc.multi_agent_stream.return_value = iter([
            StreamEvent("progress", "🧩 分解任务", {"stage": "decompose"}),
            StreamEvent("progress", "⚙️ 执行子任务 1/2", {"stage": "execute", "current": 1, "total": 2}),
            StreamEvent("answer", "协作完成", {"success": True, "summary": "协作完成"}),
        ])
        h = build_handlers(svc)
        out = self._collect(h["on_chat_stream"]("任务", "多 Agent 协作"))
        # 中间能看到分解/执行阶段
        assert any("分解任务" in process for _, _, process, _ in out)
        assert any("执行子任务" in process for _, _, process, _ in out)
        answer, status, process, _ = out[-1]
        assert "协作完成" in answer
        assert status.startswith("✅")
        assert "协作过程" in process
        svc.multi_agent_run.assert_not_called()

    def test_multi_agent_answer_without_dict(self):
        svc = make_service_mock()
        svc.multi_agent_stream.return_value = iter([StreamEvent("answer", "x", None)])
        h = build_handlers(svc)
        out = self._collect(h["on_chat_stream"]("任务", "多 Agent 协作"))
        assert "协作失败" in out[-1][0]


class TestStopHandler:
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


class TestModelStatusFormatting:
    def test_loaded_with_others(self):
        out = app.format_model_status({
            "model": "qwen3.5:4b", "num_ctx": 16384, "think": False, "loaded": True,
            "size_bytes": 4 * 1024 ** 3, "loaded_models": ["qwen3.5:4b", "qwen3.5:9b"],
        })
        assert "`qwen3.5:4b`" in out
        assert "4.0 GB" in out
        assert "num_ctx=16384" in out
        assert "思考模式 关" in out
        assert "`qwen3.5:9b`" in out  # 提示其他驻留模型

    def test_not_loaded(self):
        out = app.format_model_status({
            "model": "qwen3.5:4b", "num_ctx": 16384, "think": True, "loaded": False,
            "size_bytes": 0, "loaded_models": [],
        })
        assert "未加载" in out
        assert "思考模式 开" in out
        assert "驻留:" not in out

    def test_error(self):
        out = app.format_model_status({"model": "x", "error": "down"})
        assert "[错误]" in out

    def test_switch_result(self):
        assert app.format_switch_result({"ok": True, "message": "done"}).startswith("✅")
        assert app.format_switch_result({"ok": False, "message": "bad"}).startswith("❌")

    def test_format_stats_shows_num_ctx(self):
        out = app.format_stats({"total_documents": 1, "llm_model": "m", "llm_num_ctx": 8192})
        assert "num_ctx=8192" in out


class TestModelHandlers:
    def test_on_model_status(self):
        svc = make_service_mock()
        svc.current_model.return_value = {
            "model": "qwen3.5:4b", "num_ctx": 16384, "think": False, "loaded": False,
            "size_bytes": 0, "loaded_models": [],
        }
        h = build_handlers(svc)
        assert "`qwen3.5:4b`" in h["on_model_status"]()

    def test_on_model_choices_prepends_current_if_missing(self):
        svc = make_service_mock()
        svc.list_models.return_value = ["a:1", "b:2"]
        svc.current_model.return_value = {"model": "c:3"}
        h = build_handlers(svc)
        choices, current = h["on_model_choices"]()
        assert choices == ["c:3", "a:1", "b:2"]
        assert current == "c:3"

    def test_on_model_choices_current_in_list(self):
        svc = make_service_mock()
        svc.list_models.return_value = ["a:1", "b:2"]
        svc.current_model.return_value = {"model": "b:2"}
        h = build_handlers(svc)
        choices, current = h["on_model_choices"]()
        assert choices == ["a:1", "b:2"]
        assert current == "b:2"

    def test_on_switch_model_empty(self):
        svc = make_service_mock()
        svc.current_model.return_value = {"model": "x", "num_ctx": 1, "think": False,
                                          "loaded": False, "size_bytes": 0, "loaded_models": []}
        h = build_handlers(svc)
        result, status = h["on_switch_model"]("  ")
        assert result.startswith("❌")
        svc.switch_model.assert_not_called()
        assert "`x`" in status

    def test_on_switch_model_ok(self):
        svc = make_service_mock()
        svc.switch_model.return_value = {"ok": True, "message": "已切换到 qwen3.5:9b"}
        svc.current_model.return_value = {"model": "qwen3.5:9b", "num_ctx": 8192, "think": False,
                                          "loaded": False, "size_bytes": 0, "loaded_models": []}
        h = build_handlers(svc)
        result, status = h["on_switch_model"]("qwen3.5:9b")
        assert result.startswith("✅")
        assert "`qwen3.5:9b`" in status
        svc.switch_model.assert_called_once_with("qwen3.5:9b")


class TestThinkHandler:
    def _status(self, think):
        return {"model": "qwen3.5:4b", "num_ctx": 16384, "think": think, "loaded": False,
                "size_bytes": 0, "loaded_models": []}

    def test_toggle_on_ok(self):
        svc = make_service_mock()
        svc.set_think.return_value = {"ok": True, "enabled": True, "changed": True, "message": "思考模式已开启"}
        svc.current_model.return_value = self._status(True)
        h = build_handlers(svc)
        result, status, value = h["on_toggle_think"](True)
        assert result.startswith("✅")
        assert "思考模式 开" in status
        assert value is True
        svc.set_think.assert_called_once_with(True)

    def test_toggle_on_rejected_bounces_back(self):
        svc = make_service_mock()
        svc.set_think.return_value = {"ok": False, "enabled": False, "changed": False, "message": "不支持思考模式"}
        svc.current_model.return_value = self._status(False)
        h = build_handlers(svc)
        result, status, value = h["on_toggle_think"](True)
        assert result.startswith("❌")
        assert "思考模式 关" in status
        assert value is False
