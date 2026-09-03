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
        out = format_sessions([])
        assert "会话列表" in out and "暂无会话" in out

    def test_current_marker(self):
        out = format_sessions([
            {"session_id": "abcdefgh12345", "title": "会话A", "messages": 3, "is_current": True,
             "status": "active", "updated_at": "2026-09-03 15:12", "preview": "DJI 多少钱|换行\n测试"},
            {"session_id": "zzz", "title": "会话B", "messages": 0, "is_current": False, "status": "archived"},
        ])
        assert "共 2 个" in out
        # Markdown 表格：表头 + 分隔行 + 2 行数据
        rows = [ln for ln in out.splitlines() if ln.startswith("|")]
        assert len(rows) == 4
        assert "| ▶ | **会话A** | 🟢 活跃 | 3 | 2026-09-03 15:12 |" in rows[2]
        assert "`abcdefgh`" in rows[2]
        # 预览中的竖线/换行被转义，不破坏表格
        assert "DJI 多少钱／换行 测试" in rows[2]
        assert "|  | 会话B | 📦 已归档 | 0 | — | — | `zzz` |" == rows[3]
        assert "▶ 为当前会话" in out

    def test_unknown_status_and_no_current(self):
        out = format_sessions([{"session_id": "id1", "title": "T", "messages": 1, "status": "weird"}])
        assert "| weird |" in out
        assert "▶ 为当前会话" not in out


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
        svc.list_sessions.return_value = [{"session_id": "newid123", "title": "标题", "messages": 0, "is_current": True}]
        svc.session_choices.return_value = [("标题（0 条）· newid123", "newid123")]
        h = build_handlers(svc)
        msg, sessions, choices, current = h["on_create_session"]("标题", True)
        assert "newid123"[:8] in msg and "携带" in msg
        assert current == "newid123" and choices[0][1] == "newid123"
        svc.create_session.assert_called_once_with("标题", carry_summary=True)
        h["on_create_session"]("", False)
        svc.create_session.assert_called_with(None, carry_summary=False)

    def test_session_page_handlers(self):
        svc = make_service_mock()
        svc.list_sessions.return_value = [{"session_id": "id1", "title": "T", "messages": 0, "is_current": False}]
        svc.session_choices.return_value = [("T", "id1")]
        h = build_handlers(svc)
        # 刷新
        msg, table, choices, current = h["on_sessions_refresh"]()
        assert msg == "" and "T" in table and current is None
        # 切换
        svc.switch_session.return_value = True
        assert "已切换" in h["on_switch_session"]("id1")[0]
        svc.switch_session.return_value = False
        assert "切换失败" in h["on_switch_session"]("id1")[0]
        assert "请先" in h["on_switch_session"]("")[0]
        # 删除 / 归档：服务层前缀换成图标
        svc.delete_session.return_value = "[提示] 不能删除当前会话，请先切换到其他会话"
        assert h["on_delete_session"]("id1")[0].startswith("💡")
        svc.delete_session.return_value = "[成功] 已删除会话 id1"
        assert h["on_delete_session"]("id1")[0].startswith("✅")
        svc.archive_session.return_value = "[错误] 会话不存在: x"
        assert h["on_archive_session"]("x")[0].startswith("❌")
        svc.archive_session.return_value = "plain"
        assert h["on_archive_session"]("x")[0] == "plain"

    def test_on_search_sessions(self):
        svc = make_service_mock()
        h = build_handlers(svc)
        assert h["on_search_sessions"]("  ") == ""
        svc.search_sessions.return_value = []
        assert "未找到" in h["on_search_sessions"]("x")
        svc.search_sessions.return_value = [{"session_id": "abcdefgh1", "title": "命中"}]
        out = h["on_search_sessions"]("x")
        assert "1 个" in out and "**命中**" in out and "`abcdefgh`" in out

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
    """``on_chat_stream`` yield 六元组 (history, status, process, sources, hint, confirm)。

    ``history`` 为 Chatbot（messages 格式）的完整多轮列表：既有会话历史 + 本轮
    用户消息，完成后追加助手回答。
    """

    def _collect(self, gen):
        out = list(gen)
        for item in out:
            assert len(item) == 6, f"应为六元组: {item!r}"
            assert isinstance(item[0], list)
        return out

    @staticmethod
    def _last_assistant(history):
        return history[-1]["content"] if history and history[-1]["role"] == "assistant" else None

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
        svc.chat_history.return_value = [
            {"role": "user", "content": "旧问"}, {"role": "assistant", "content": "旧答"},
        ]
        svc.rag_query_stream.return_value = iter([
            StreamEvent("progress", "检索知识库...", {"stage": "kb_retrieving"}),
            _rag_answer("答案"),
        ])
        h = build_handlers(svc)
        out = self._collect(h["on_chat_stream"]("问题", "RAG 检索", True, False, "sid1"))
        # 第一条即为带耗时的状态行，历史 = 既有 2 条 + 本轮用户消息
        assert out[0][1].startswith("⏳")
        assert "已用时" in out[0][1]
        assert [m["content"] for m in out[0][0]] == ["旧问", "旧答", "问题"]
        # 最终一条：追加助手回答 + 完成状态 + 已完成的处理过程
        history, status, process, _, hint, _ = out[-1]
        assert self._last_assistant(history) == "答案"
        assert len(history) == 4
        assert status.startswith("✅ 完成")
        assert "检索知识库" in process and "已完成" in process
        assert hint == ""
        # 会话 id 透传给服务层
        _, kwargs = svc.rag_query_stream.call_args
        assert kwargs["session_id"] == "sid1"

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
        assert self._last_assistant(out[-1][0]) == "ok"

    def test_history_load_failure_tolerated(self):
        svc = make_service_mock()
        svc.chat_history.side_effect = RuntimeError("no session")
        svc.rag_query_stream.return_value = iter([_rag_answer("ok")])
        h = build_handlers(svc)
        out = self._collect(h["on_chat_stream"]("问题", "RAG 检索"))
        assert out[0][0] == [{"role": "user", "content": "问题"}]

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
        assert any("网络搜索中" in process for _, _, process, _, _, _ in out)
        history, _, _, sources, _, _ = out[-1]
        assert self._last_assistant(history) == "最终"
        assert "f.md" in sources and "http://x" in sources

    def test_rag_rewritten_question_shown_and_context_status(self):
        """追问被改写：回答前注明"已理解为"，状态行追加上下文用量与压缩次数。"""
        svc = make_service_mock()
        svc.rag_query_stream.return_value = iter([
            StreamEvent("progress", "🔗 结合上下文理解问题…", {"stage": "context_rewrite"}),
            _rag_answer(
                "2999 元",
                rewritten="DJI OSMO 360 多少钱",
                context={"history_tokens": 3200, "budget": 4800, "compressions": 1,
                         "suggest_new_session": False, "reasons": []},
            ),
        ])
        h = build_handlers(svc)
        out = self._collect(h["on_chat_stream"]("它多少钱", "RAG 检索"))
        history, status, process, _, hint, _ = out[-1]
        content = self._last_assistant(history)
        assert content.startswith("> 🔗 已理解为：DJI OSMO 360 多少钱")
        assert content.endswith("2999 元")
        assert "上下文 3.2K / 4.8K" in status and "已压缩 1 次" in status
        assert "结合上下文理解问题" in process
        assert hint == ""
        svc.mark_suggested.assert_not_called()

    def test_rag_health_suggests_new_session_once(self):
        svc = make_service_mock()
        svc.rag_query_stream.return_value = iter([
            _rag_answer(
                "ok",
                context={"history_tokens": 4500, "budget": 4800, "compressions": 2,
                         "suggest_new_session": True, "reasons": ["compressions"]},
            ),
        ])
        h = build_handlers(svc)
        out = self._collect(h["on_chat_stream"]("q", "RAG 检索", True, False, "sid9"))
        hint = out[-1][4]
        assert hint.startswith("💡") and "已压缩 2 次" in hint and "建议新建会话" in hint
        svc.mark_suggested.assert_called_once_with("sid9")

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
        assert "知识库概览" in self._last_assistant(out[-1][0])

    def test_rag_error(self):
        svc = make_service_mock()
        svc.rag_query_stream.return_value = iter([StreamEvent("error", "检索炸了")])
        h = build_handlers(svc)
        out = self._collect(h["on_chat_stream"]("q", "RAG 检索"))
        history, status, _, _, _, _ = out[-1]
        assert "检索炸了" in self._last_assistant(history)
        assert status.startswith("❌")

    def test_rag_cancelled(self):
        svc = make_service_mock()
        svc.rag_query_stream.return_value = iter([
            StreamEvent("progress", "规划搜索", {"stage": "web_plan"}),
            StreamEvent("cancelled", "已停止"),
        ])
        h = build_handlers(svc)
        out = self._collect(h["on_chat_stream"]("q", "RAG 检索"))
        history, status, process, _, _, _ = out[-1]
        assert "已停止" in status
        assert "规划搜索" in process
        # 未产出回答：历史只到用户消息
        assert history[-1]["role"] == "user"

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
            StreamEvent("answer", "完成", {"step_log": [], "context": {"history_tokens": 10, "budget": 100}}),
        ])
        h = build_handlers(svc)
        out = self._collect(h["on_chat_stream"]("做事", "单 Agent", True, True, "sid2"))
        assert any("第一步" in process for _, _, process, _, _, _ in out)
        # 心跳出现在状态行，但不进入执行过程列表
        assert any("模型推理中" in status for _, status, _, _, _, _ in out)
        assert not any("模型推理中" in process for _, _, process, _, _, _ in out)
        history, status, process, _, _, _ = out[-1]
        assert self._last_assistant(history) == "完成"
        assert "执行过程" in process
        assert "上下文 10 / 100" in status
        # auto_confirm=True 时传入确认处理器；会话 id 透传
        _, kwargs = svc.agent_chat_stream.call_args
        assert kwargs["confirm_handler"] is not None
        assert kwargs["session_id"] == "sid2"

    def test_single_agent_default_rejects_confirm(self):
        svc = make_service_mock()
        svc.agent_chat_stream.return_value = iter([StreamEvent("answer", "x")])
        h = build_handlers(svc)
        self._collect(h["on_chat_stream"]("做事", "单 Agent"))
        _, kwargs = svc.agent_chat_stream.call_args
        assert kwargs["confirm_handler"] is None
        assert kwargs["session_id"] is None

    def test_multi_agent_stream(self):
        svc = make_service_mock()
        svc.multi_agent_stream.return_value = iter([
            StreamEvent("progress", "🧩 分解任务", {"stage": "decompose"}),
            StreamEvent("progress", "⚙️ 执行子任务 1/2", {"stage": "execute", "current": 1, "total": 2}),
            StreamEvent("answer", "协作完成", {"success": True, "summary": "协作完成",
                                              "rewritten": "帮我总结 X"}),
        ])
        h = build_handlers(svc)
        out = self._collect(h["on_chat_stream"]("任务", "多 Agent 协作"))
        # 中间能看到分解/执行阶段
        assert any("分解任务" in process for _, _, process, _, _, _ in out)
        assert any("执行子任务" in process for _, _, process, _, _, _ in out)
        history, status, process, _, _, _ = out[-1]
        content = self._last_assistant(history)
        assert "协作完成" in content and "已理解为：帮我总结 X" in content
        assert status.startswith("✅")
        assert "协作过程" in process
        svc.multi_agent_run.assert_not_called()

    def test_multi_agent_answer_without_dict(self):
        svc = make_service_mock()
        svc.multi_agent_stream.return_value = iter([StreamEvent("answer", "x", None)])
        h = build_handlers(svc)
        out = self._collect(h["on_chat_stream"]("任务", "多 Agent 协作"))
        assert "协作失败" in self._last_assistant(out[-1][0])


class TestSessionHandlers:
    """对话页会话控件处理器（每个标签页绑定自己的会话）。"""

    def test_session_init(self):
        svc = make_service_mock()
        svc.ensure_session.return_value = "sid1"
        svc.session_choices.return_value = [("会话A（2 条）· sid1", "sid1")]
        svc.chat_history.return_value = [{"role": "user", "content": "q"}]
        svc.context_metrics.return_value = {"turns": 1, "history_tokens": 20, "budget": 4915, "compressions": 0}
        h = build_handlers(svc)
        choices, sid, history, ctx_md = h["on_session_init"]()
        assert sid == "sid1" and choices[0][1] == "sid1"
        assert history[0]["content"] == "q"
        assert "1 轮" in ctx_md and "4.9K" in ctx_md

    def test_session_select_and_empty(self):
        svc = make_service_mock()
        svc.chat_history.return_value = []
        svc.context_metrics.return_value = {"turns": 0, "history_tokens": 0, "budget": 100}
        h = build_handlers(svc)
        assert h["on_session_select"]("")[0] == ""
        sid, history, ctx_md, hint = h["on_session_select"](" sid2 ")
        assert sid == "sid2" and history == [] and hint == ""
        assert "0 轮" in ctx_md

    def test_context_status_error_tolerated(self):
        svc = make_service_mock()
        svc.chat_history.return_value = []
        svc.context_metrics.side_effect = RuntimeError("x")
        h = build_handlers(svc)
        assert h["on_session_select"]("s")[2] == ""

    def test_new_session_with_carry(self):
        svc = make_service_mock()
        svc.create_session.return_value = "new1"
        svc.session_choices.return_value = [("x", "new1")]
        svc.chat_history.return_value = []
        svc.context_metrics.return_value = {"turns": 0, "history_tokens": 60, "budget": 100,
                                            "summary": "（承接自上一会话）要点"}
        h = build_handlers(svc)
        choices, sid, history, ctx_md, hint = h["on_new_session"](True, "old1")
        assert sid == "new1" and hint == ""
        svc.create_session.assert_called_once_with(None, carry_summary=True, from_session_id="old1")
        assert "承接自上一会话" in ctx_md

    def test_clear_context(self):
        svc = make_service_mock()
        svc.clear_context.return_value = True
        svc.chat_history.return_value = []
        svc.context_metrics.return_value = {}
        h = build_handlers(svc)
        history, msg, ctx_md, hint = h["on_clear_context"]("sid")
        assert history == [] and "已清空" in msg and hint == ""
        svc.clear_context.return_value = False
        assert "没有可清空" in h["on_clear_context"]("")[1]

    def test_compact_context_variants(self):
        svc = make_service_mock()
        svc.context_metrics.return_value = {}
        h = build_handlers(svc)
        svc.compact_context.return_value = {"error": "boom"}
        assert "压缩失败" in h["on_compact_context"]("s")[0]
        svc.compact_context.return_value = {"folded_messages": 0}
        assert "无需压缩" in h["on_compact_context"]("s")[0]
        svc.compact_context.return_value = {"folded_messages": 4, "compressions": 2}
        msg, _ = h["on_compact_context"]("s")
        assert "折叠 4 条" in msg and "第 2 次" in msg

    def test_continue_session(self):
        svc = make_service_mock()
        h = build_handlers(svc)
        assert h["on_continue_session"]("sid") == ""
        svc.continue_session.assert_called_once_with("sid")


class TestContextFormatting:
    def test_format_context_metrics_empty_and_error(self):
        assert app.format_context_metrics({}) == ""
        assert "不可用" in app.format_context_metrics({"error": "x"})

    def test_format_context_metrics_with_summary(self):
        md = app.format_context_metrics({
            "turns": 3, "history_tokens": 3200, "budget": 4800, "compressions": 1,
            "summary": "很长的摘要" * 40,
        })
        assert "3 轮" in md and "3.2K / 4.8K" in md and "已压缩 1 次" in md
        assert "📝 摘要" in md and md.endswith("…")

    def test_with_context_status(self):
        assert app.with_context_status("✅ 完成", None) == "✅ 完成"
        assert app.with_context_status("✅ 完成", {"error": "x"}) == "✅ 完成"
        out = app.with_context_status("✅ 完成", {"history_tokens": 500, "budget": 4915, "compressions": 0})
        assert out == "✅ 完成 · 上下文 500 / 4.9K"


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


# ==================== 新增格式化函数 ====================

class TestNewFormatters:
    def test_format_step_log(self):
        out = app.format_step_log([
            {"step": 1, "phase": "action", "tool": "read_file", "confirmed": True, "thought": "先看看"},
            {"step": 2, "phase": "action", "tool": "execute_command", "confirmed": False,
             "safety": {"risk_level": "high"}},
            {"step": 3, "phase": "blocked"}, {"step": 4, "phase": "rejected"}, {"step": 5, "phase": "final"},
            "not-a-dict",
        ])
        assert "执行摘要" in out and "`read_file`" in out and "先看看" in out
        assert "⛔ 调用 `execute_command`（风险 high）" in out
        assert "危险命令被拦截" in out and "用户拒绝执行" in out and "最终答案" in out
        assert app.format_step_log([]) == ""
        assert app.format_step_log([{"phase": "thinking"}]) == ""

    def test_format_confirm_request(self):
        out = app.format_confirm_request({
            "tool": "execute_command", "command": "rm -r build", "safety": {"risk_level": "high"},
        })
        assert "execute_command" in out and "rm -r build" in out and "cb-risk-high" in out and "高" in out
        out2 = app.format_confirm_request({"tool": "write_file", "args": {"path": "a"}})
        assert "```json" in out2 and '"path"' in out2
        assert app.format_confirm_request({}) == ""

    def test_format_exec_analysis(self):
        assert app.format_exec_analysis({}) == ""
        assert app.format_exec_analysis({"error": "x"}).startswith("❌")
        assert "拦截" in app.format_exec_analysis({"is_dangerous": True, "risk_level": "critical", "danger_reasons": ["r"]})
        assert "需确认" in app.format_exec_analysis({"needs_confirm": True, "risk_level": "medium"})
        assert "只读" in app.format_exec_analysis({"needs_confirm": False, "risk_level": "low"})

    def test_format_session_info(self):
        assert app.format_session_info({}) == ""
        assert "没找到" in app.format_session_info({"error": "没找到"})
        out = app.format_session_info({
            "session_id": "abc", "title": "T", "status": "active", "created_at": "c", "updated_at": "u",
            "messages": 3, "tags": ["x"], "metadata": {"k": 1},
        })
        assert "`abc`" in out and "🟢 活跃" in out and "x" in out and "'k'" in out

    def test_format_file_info(self):
        assert app.format_file_info({}) == ""
        assert app.format_file_info({"error": "e"}) == "_e_"
        out = app.format_file_info({"path": "/a", "size": "1 KB", "type": "permanent", "chunk_count": 2, "tags": ["t"]})
        assert "`/a`" in out and "permanent" in out and "| 片段数 | 2 |" in out and "t" in out

    def test_format_env_info(self):
        assert app.format_env_info({}) == ""
        assert "读取配置失败" in app.format_env_info({"error": "x"})
        out = app.format_env_info({"ollama_url": "http://h", "think": True, "cwd": "/w", "app_version": "1.0"})
        assert "http://h" in out and "| 思考模式 | 开 |" in out and "/w" in out and "1.0" in out

    def test_format_stats_cards(self):
        assert "获取统计失败" in app.format_stats_cards({"error": "x"})
        out = app.format_stats_cards({"total_documents": 5, "embed_model": "e", "chunk_size": 1, "chunk_overlap": 0, "top_k": 3}, file_count=2)
        assert out.count('class="cb-card"') == 5 and ">5<" in out and ">2<" in out
        assert app.format_stats_cards({"total_documents": 1}).count('class="cb-card"') == 4

    def test_format_model_chip(self):
        assert "连接失败" in app.format_model_chip({"model": "m", "error": "x"})
        loaded = app.format_model_chip({"model": "m", "loaded": True, "size_bytes": 2 * 1024 ** 3, "num_ctx": 8, "think": True,
                                        "loaded_models": ["m", "o"]})
        assert "已加载 2.0 GB" in loaded and "思考 开" in loaded and "另驻留 1 个模型" in loaded and 'class="dot"' in loaded
        assert "dot off" in app.format_model_chip({"model": "m", "loaded": False})

    def test_format_kv_table(self):
        assert app.format_kv_table([]) == ""
        assert "| a | 1 |" in app.format_kv_table([("a", 1), ("b", "")])
        assert "| b | — |" in app.format_kv_table([("b", "")])


# ==================== 对话流：审批卡片 / 执行摘要 / 协作模式 ====================

class TestChatStreamConfirmAndSummary:
    def test_confirm_event_shows_card_then_hides(self):
        svc = make_service_mock()
        svc.agent_chat_stream.return_value = iter([
            StreamEvent("confirm", "确认?", {"tool": "execute_command", "command": "rm x", "safety": {"risk_level": "high"}}),
            StreamEvent("heartbeat", "", {"elapsed": 1.0}),
            StreamEvent("step", "继续", {"phase": "action"}),
            StreamEvent("answer", "done", {"step_log": [{"step": 1, "phase": "final"}], "context": {}}),
        ])
        h = build_handlers(svc)
        out = list(h["on_chat_stream"]("做事", "单 Agent", True, False, "s1"))
        confirm_frames = [o for o in out if o[5]]
        assert len(confirm_frames) == 2  # confirm + heartbeat 保持卡片
        assert "rm x" in confirm_frames[0][5] and "等待你确认" in confirm_frames[0][1]
        assert out[-1][5] == ""
        assert "执行摘要" in out[-1][2] and "最终答案" in out[-1][2]
        _, kwargs = svc.agent_chat_stream.call_args
        assert kwargs["interactive_confirm"] is True and kwargs["confirm_handler"] is None

    def test_auto_confirm_disables_interactive(self):
        svc = make_service_mock()
        svc.agent_chat_stream.return_value = iter([StreamEvent("answer", "x", {})])
        h = build_handlers(svc)
        list(h["on_chat_stream"]("做事", "单 Agent", True, True))
        _, kwargs = svc.agent_chat_stream.call_args
        assert kwargs["interactive_confirm"] is False and kwargs["confirm_handler"] is not None

    def test_collab_mode_passed(self):
        svc = make_service_mock()
        svc.multi_agent_stream.return_value = iter([StreamEvent("answer", "ok", {"success": True, "summary": "ok"})])
        h = build_handlers(svc)
        list(h["on_chat_stream"]("任务", "多 Agent 协作", True, False, "", "parallel"))
        _, kwargs = svc.multi_agent_stream.call_args
        assert kwargs["mode"] == "parallel"
        list(h["on_chat_stream"]("任务", "多 Agent 协作", True, False, "", ""))
        assert svc.multi_agent_stream.call_args[1]["mode"] is None

    def test_on_resolve_confirm(self):
        svc = make_service_mock()
        h = build_handlers(svc)
        svc.resolve_confirm.return_value = False
        assert "没有等待确认" in h["on_resolve_confirm"](True)
        svc.resolve_confirm.return_value = True
        assert h["on_resolve_confirm"](True).startswith("✅")
        assert h["on_resolve_confirm"](False).startswith("⛔")


# ==================== 新增处理器 ====================

class TestNewHandlers:
    def test_session_list_state_fallback(self):
        svc = make_service_mock()
        svc.session_choices.return_value = [("A", "a"), ("B", "b")]
        svc.ensure_session.return_value = "a"
        h = build_handlers(svc)
        assert h["on_session_list_state"]("b") == ([("A", "a"), ("B", "b")], "b")
        assert h["on_session_list_state"]("gone")[1] == "a"

    def test_session_filter(self):
        svc = make_service_mock()
        svc.session_choices.return_value = [("会话一（2 条）", "a"), ("Other", "b")]
        svc.search_sessions.return_value = [{"session_id": "b"}]
        h = build_handlers(svc)
        assert h["on_session_filter"]("") == svc.session_choices.return_value
        assert h["on_session_filter"]("会话") == [("会话一（2 条）", "a"), ("Other", "b")]

    def test_sidebar_archive_delete(self):
        svc = make_service_mock()
        svc.session_choices.return_value = [("A", "a")]
        svc.ensure_session.return_value = "a"
        svc.archive_session.return_value = "[成功] 已归档"
        svc.delete_session.return_value = "[成功] 已删除"
        h = build_handlers(svc)
        msg, choices, sid = h["on_sidebar_archive"]("a")
        assert msg.startswith("✅") and sid == "a"
        msg, choices, sid = h["on_sidebar_delete"]("b")
        assert msg.startswith("✅") and sid == "a"
        svc.delete_session.return_value = "[提示] 不能删除当前会话"
        assert h["on_sidebar_delete"]("a")[0].startswith("💡")

    def test_session_info_handler(self):
        svc = make_service_mock()
        svc.session_info.return_value = {"session_id": "x", "title": "T", "status": "active", "messages": 1}
        assert "`x`" in build_handlers(svc)["on_session_info"]("x")

    def test_stats_cards_and_add_path(self):
        svc = make_service_mock()
        svc.get_stats.return_value = {"total_documents": 1}
        svc.file_list.return_value = [{"path": "/a"}, {"path": "[错误] x"}]
        svc.add_path.return_value = "[成功] 已追加入库 3 个片段"
        h = build_handlers(svc)
        assert ">1<" in h["on_stats_cards"]()
        msg, cards = h["on_add_path"]("/docs", ".md")
        assert msg.startswith("✅") and "cb-cards" in cards
        svc.add_path.assert_called_with("/docs", ".md")

    def test_file_table_and_info(self):
        svc = make_service_mock()
        svc.file_list.return_value = [{"path": "/x/a.md", "size": "1 KB", "type": "permanent",
                                       "upload_time": "t", "chunk_count": 2, "access_count": 0}]
        svc.file_info.return_value = {"path": "/x/a.md", "size": "1 KB"}
        h = build_handlers(svc)
        rows = h["on_file_table"]()
        assert rows[0][0] == "a.md" and rows[0][-1] == "/x/a.md"
        assert h["headers"]["files"][0] == "文件"
        assert "`/x/a.md`" in h["on_file_info"]("/x/a.md")

    def test_file_stats_md(self):
        svc = make_service_mock()
        svc.file_stats.return_value = {"total_files": 2, "total_size": 10, "total_size_formatted": "10 B"}
        out = build_handlers(svc)["on_file_stats_md"]()
        assert "| 文件总数 | 2 |" in out and "10 B" in out and "total_size" not in out
        svc.file_stats.return_value = {"error": "e"}
        assert build_handlers(svc)["on_file_stats_md"]().startswith("❌")

    def test_cleanup_and_dedupe(self):
        svc = make_service_mock()
        svc.file_cleanup_preview.return_value = []
        svc.file_duplicates.return_value = []
        svc.file_list.return_value = []
        h = build_handlers(svc)
        assert "没有需要清理" in h["on_file_cleanup_preview"]()
        assert "没有发现重复" in h["on_file_dedupe_preview"]()
        svc.file_cleanup_preview.return_value = [{"path": "/t", "type": "temporary"}]
        svc.file_duplicates.return_value = [{"path": "/b", "duplicate_of": "/a"}]
        assert "/t" in h["on_file_cleanup_preview"]() and "磁盘删除" in h["on_file_cleanup_preview"]()
        assert "/b" in h["on_file_dedupe_preview"]() and "/a" in h["on_file_dedupe_preview"]()
        svc.file_cleanup_preview.return_value = [{"path": "[错误] x"}]
        svc.file_duplicates.return_value = [{"path": "[错误] y"}]
        assert h["on_file_cleanup_preview"]().startswith("❌") and h["on_file_dedupe_preview"]().startswith("❌")
        svc.file_cleanup.return_value = "[成功] 已清理 1 个文件"
        svc.file_deduplicate.return_value = "[成功] 已移除 1 个重复登记"
        assert h["on_file_cleanup"]()[0].startswith("✅") and h["on_file_dedupe"]()[0].startswith("✅")

    def test_snapshot_and_summary_tables(self):
        svc = make_service_mock()
        svc.snapshot_list_data.return_value = [{"snapshot_id": "s", "timestamp": "t", "document_count": 1, "total_chunks": 2, "trigger": "manual"}]
        svc.snapshot_create.return_value = "[成功] ok"
        svc.knowledge_summary_data.return_value = [{"file_name": "a", "kind": "通用", "confidence": 0.5, "chunk_count": 1, "topics": "x"}]
        h = build_handlers(svc)
        assert h["on_snapshot_table"]() == [["s", "t", 1, 2, "手动"]]
        msg, rows = h["on_snapshot_create_table"]()
        assert msg.startswith("✅") and rows
        assert h["on_knowledge_summary_table"]() == [["a", "通用", "0.50", 1, "x"]]

    def test_graph_typed_and_build(self):
        svc = make_service_mock()
        svc.graph_query_typed.return_value = {"text": "[提示] 空"}
        svc.graph_build.return_value = "built-text"
        svc.graph_build_file.return_value = "built-file"
        h = build_handlers(svc)
        assert h["on_graph_query_typed"]("type", "tool").startswith("💡")
        assert h["on_graph_build_any"]("文本", "abc") == "built-text"
        assert h["on_graph_build_any"]("文件路径", "/a.py") == "built-file"

    def test_db_write_handlers(self):
        svc = make_service_mock()
        svc.db_create_table.return_value = "[成功] ok"
        svc.db_insert.return_value = "[错误] bad"
        h = build_handlers(svc)
        assert h["on_db_create_table"]("t", "{}").startswith("✅")
        assert h["on_db_insert"]("t", "{}").startswith("❌")

    def test_exec_handlers(self):
        svc = make_service_mock()
        h = build_handlers(svc)
        assert h["on_exec_analyze"]("") == ("", False, False)
        svc.exec_analyze.return_value = {"risk_level": "low", "needs_confirm": False}
        md, can, needs = h["on_exec_analyze"]("ls")
        assert can and not needs and "只读" in md
        svc.exec_analyze.return_value = {"risk_level": "high", "needs_confirm": True}
        assert h["on_exec_analyze"]("rm x")[1:] == (False, True)
        svc.exec_analyze.return_value = {"risk_level": "critical", "is_dangerous": True, "danger_reasons": []}
        assert h["on_exec_analyze"]("rm -rf /")[1:] == (False, False)
        svc.exec_run.return_value = "hello"
        assert h["on_exec_run"]("echo hi") == "```\nhello\n```"
        svc.exec_run.return_value = "[错误] 拦截"
        assert h["on_exec_run"]("rm -rf /").startswith("❌")

    def test_file_rw_and_cwd(self):
        svc = make_service_mock()
        svc.read_file.return_value = "line"
        svc.write_file.return_value = "[成功] 写入"
        svc.cwd.return_value = "/w"
        svc.chdir.return_value = "[成功] 已切换"
        h = build_handlers(svc)
        assert h["on_read_file"]("a", 0, 10) == "```\nline\n```"
        svc.read_file.assert_called_with("a", 0, 10)
        svc.read_file.return_value = "[提示] 请输入文件路径"
        assert h["on_read_file"]("").startswith("💡")
        assert h["on_write_file"]("a", "c", True).startswith("✅")
        svc.write_file.assert_called_with("a", "c", True)
        assert "`/w`" in h["on_cwd"]()
        msg, cwd = h["on_chdir"]("/w")
        assert msg.startswith("✅") and "/w" in cwd

    def test_env_tools_models(self):
        svc = make_service_mock()
        svc.env_info.return_value = {"ollama_url": "http://h", "cwd": "/w"}
        svc.list_tools.return_value = [{"name": "t", "safe": False, "description": "d", "parameters": {"a": "x"}}]
        svc.model_table.return_value = [{"name": "m", "current": True, "loaded": False}]
        svc.collaboration_modes.return_value = [("自动", "")]
        h = build_handlers(svc)
        assert "http://h" in h["on_env_info"]()
        assert h["on_tools_table"]() == [["t", "需确认（会修改系统）", "d", "a"]]
        assert h["on_model_table"]() == [["m", "✔", ""]]
        assert h["on_collab_choices"]() == [("自动", "")]
        assert "cb-status-chip" in h["on_model_chip"]()
