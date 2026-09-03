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
    """``on_chat_stream`` yield 五元组 (history, status, process, sources, hint)。

    ``history`` 为 Chatbot（messages 格式）的完整多轮列表：既有会话历史 + 本轮
    用户消息，完成后追加助手回答。
    """

    def _collect(self, gen):
        out = list(gen)
        for item in out:
            assert len(item) == 5, f"应为五元组: {item!r}"
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
        history, status, process, _, hint = out[-1]
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
        assert any("网络搜索中" in process for _, _, process, _, _ in out)
        history, _, _, sources, _ = out[-1]
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
        history, status, process, _, hint = out[-1]
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
        history, status, _, _, _ = out[-1]
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
        history, status, process, _, _ = out[-1]
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
        assert any("第一步" in process for _, _, process, _, _ in out)
        # 心跳出现在状态行，但不进入执行过程列表
        assert any("模型推理中" in status for _, status, _, _, _ in out)
        assert not any("模型推理中" in process for _, _, process, _, _ in out)
        history, status, process, _, _ = out[-1]
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
        assert any("分解任务" in process for _, _, process, _, _ in out)
        assert any("执行子任务" in process for _, _, process, _, _ in out)
        history, status, process, _, _ = out[-1]
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
