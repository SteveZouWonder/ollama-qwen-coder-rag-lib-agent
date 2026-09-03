#!/usr/bin/env python3
"""test_conversation_context.py — 连续对话上下文核心层单元测试。

覆盖：token 估算、追问/话题漂移启发式、ContextBuilder（系统提示 + 滚动摘要 +
最近 K 轮）、自动/手动压缩（LLM 与启发式回退）、问题改写、health() 建议规则、
携带摘要新建会话、旧历史文件迁移、单例。全部使用临时目录的真实 SessionManager
与注入的假 LLM，不触碰 Ollama 与用户数据。
"""
import json
import os
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

import conversation_context as cc
from conversation_context import (
    ConversationContext,
    estimate_messages_tokens,
    estimate_tokens,
    format_context_status,
    format_suggest_hint,
    format_tokens,
    is_followup,
    merge_health,
    migrate_legacy_history,
    topic_drift,
)
from session_manager import SessionManager


@pytest.fixture
def manager(tmp_path):
    return SessionManager(str(tmp_path / "sessions"))


def make_ctx(manager, complete=None, **kw):
    kw.setdefault("num_ctx", 4000)
    kw.setdefault("ratio", 0.3)  # budget = 1200
    return ConversationContext(manager, complete=complete or (lambda p: "LLM摘要"), **kw)


# ==================== token 估算 ====================

class TestTokenEstimate:
    def test_empty(self):
        assert estimate_tokens("") == 0
        assert estimate_tokens(None) == 0

    def test_cjk_ratio(self):
        # 15 个中文字 ≈ 10 token
        assert estimate_tokens("一二三四五六七八九十一二三四五") == 10

    def test_ascii_ratio(self):
        assert estimate_tokens("abcdefgh") == 2  # 8 字符 / 4

    def test_mixed_is_conservative(self):
        t = estimate_tokens("中文abcd")
        assert t == 2 + 1

    def test_messages_overhead(self):
        msgs = [{"role": "user", "content": "abcd"}, {"role": "assistant", "content": "中文"}]
        assert estimate_messages_tokens(msgs) == (1 + 4) + (2 + 4)
        assert estimate_messages_tokens([None, "x"]) == 0

    def test_format_tokens(self):
        assert format_tokens(950) == "950"
        assert format_tokens(3200) == "3.2K"
        assert format_tokens(-5) == "0"


# ==================== 启发式 ====================

class TestFollowupHeuristics:
    @pytest.mark.parametrize("q", [
        "它多少钱", "这个怎么配置", "刚才那个文件呢", "继续", "还有别的吗", "为什么",
        "why is that", "what about the price", "tell me more about it", "短问题",
    ])
    def test_followup_true(self, q):
        assert is_followup(q) is True

    @pytest.mark.parametrize("q", [
        "请介绍一下 Cloudflare Tunnel 的完整配置方法和常见故障排查步骤",
        "How do I configure a Cloudflare Tunnel for a local service",
    ])
    def test_followup_false(self, q):
        assert is_followup(q) is False

    def test_followup_empty(self):
        assert is_followup("") is False
        assert is_followup("   ") is False

    def test_topic_drift_detects_new_topic(self):
        recent = [
            {"role": "user", "content": "DJI OSMO 360 的售价是多少"},
            {"role": "assistant", "content": "DJI OSMO 360 官方售价 2999 元起"},
        ]
        assert topic_drift("请介绍一下 Cloudflare Tunnel 的完整配置方法和排错流程", recent) is True
        assert topic_drift("DJI OSMO 360 与 Insta360 X4 相比哪个更值得买呢请详细比较", recent) is False

    def test_topic_drift_false_for_followup_or_empty(self):
        recent = [{"role": "user", "content": "DJI OSMO 360 售价"}]
        assert topic_drift("它多少钱", recent) is False
        assert topic_drift("", recent) is False
        assert topic_drift("完全不同的话题关于云计算架构设计", []) is False
        assert topic_drift("？？？！！！……", recent) is False
        assert topic_drift("完全不同的话题关于云计算架构设计", [{"role": "user", "content": "…"}]) is False


# ==================== ContextBuilder ====================

class TestBuildMessages:
    def test_empty_session_only_system(self, manager):
        ctx = make_ctx(manager)
        assert ctx.build_messages("SYS") == [{"role": "system", "content": "SYS"}]
        assert ctx.build_messages() == []
        assert ctx.has_history() is False
        assert ctx.all_messages() == []
        assert ctx.history_text() == ""

    def test_record_creates_session_and_orders_messages(self, manager):
        ctx = make_ctx(manager)
        ctx.record("问", "答", trace="共 2 步，调用 read_file", rewritten="独立问题")
        session = manager.get_current_session()
        assert session is not None
        assert [m["role"] for m in session.messages] == ["user", "assistant"]
        assert session.messages[0]["rewritten"] == "独立问题"
        assert session.messages[1]["trace"] == "共 2 步，调用 read_file"
        built = ctx.build_messages("SYS")
        assert built[0]["role"] == "system"
        assert built[1] == {"role": "user", "content": "问"}
        assert "[执行摘要: 共 2 步" in built[2]["content"]
        assert ctx.has_history() is True

    def test_rewritten_same_as_question_not_stored(self, manager):
        ctx = make_ctx(manager)
        ctx.record("问", "答", rewritten="问")
        assert "rewritten" not in manager.get_current_session().messages[0]

    def test_keeps_only_recent_k_turns(self, manager):
        ctx = make_ctx(manager, recent_turns=2, ratio=10)  # 超大预算，不触发压缩
        for i in range(5):
            ctx.record(f"q{i}", f"a{i}")
        built = ctx.build_messages()
        assert [m["content"] for m in built] == ["q3", "a3", "q4", "a4"]

    def test_long_message_truncated(self, manager):
        ctx = make_ctx(manager, ratio=10)
        ctx.record("q", "x" * 5000)
        built = ctx.build_messages()
        assert built[1]["content"].endswith("…（已截断）")
        assert len(built[1]["content"]) < 5000

    def test_budget_hard_cap_drops_oldest_recent_turn(self, manager):
        """最近 K 轮本身就超预算时，从最旧一轮起裁掉，至少保留 1 轮。"""
        ctx = make_ctx(manager, num_ctx=1000, ratio=0.3, recent_turns=3)  # budget 300
        # 关闭自动压缩阈值影响：直接操作消息
        ctx.record("q1", "中" * 300)
        ctx.record("q2", "中" * 300)
        ctx.record("q3", "中" * 300)
        built = ctx.build_messages()
        contents = [m["content"] for m in built if m["role"] == "user"]
        assert contents[-1] == "q3"
        assert len(contents) >= 1
        assert estimate_messages_tokens(built) <= 300 + 220  # 单轮可略超，但不会累积

    def test_summary_injected_as_system(self, manager):
        ctx = make_ctx(manager)
        ctx.record("q", "a")
        session = manager.get_current_session()
        session.metadata["context"]["summary"] = "早前摘要"
        built = ctx.build_messages("SYS")
        assert built[1]["role"] == "system" and "早前摘要" in built[1]["content"]
        assert "[更早对话摘要] 早前摘要" in ctx.history_text()
        assert "用户: q" in ctx.history_text() and "助手: a" in ctx.history_text()

    def test_history_text_truncates(self, manager):
        ctx = make_ctx(manager, ratio=10)
        ctx.record("q", "长" * 600)
        text = ctx.history_text(turns=1, max_chars=50)
        assert "…" in text and len(text) < 200

    def test_bound_session_id(self, manager):
        s1 = manager.create_session("A")
        s2 = manager.create_session("B")
        ctx1 = make_ctx(manager, session_id=s1.session_id)
        ctx1.record("q1", "a1")
        ctx2 = make_ctx(manager, session_id=s2.session_id)
        assert ctx2.all_messages() == []
        assert [m["content"] for m in ctx1.all_messages()] == ["q1", "a1"]

    def test_bound_missing_session_falls_back_to_current(self, manager):
        s1 = manager.create_session("A")
        ctx = make_ctx(manager, session_id="missing")
        assert ctx.session().session_id == s1.session_id
        assert ctx.session_id == s1.session_id

    def test_session_none_without_create(self, manager):
        ctx = make_ctx(manager)
        assert ctx.session(create=False) is None
        assert ctx.live_messages() == []
        assert ctx.clear() is False
        assert ctx.compact() is None
        assert ctx.maybe_compress() is False
        assert ctx.carry_summary_text() == ""
        ctx.mark_suggested()
        ctx.continue_current()
        m = ctx.metrics()
        assert m["session_id"] is None and m["turns"] == 0

    def test_manager_without_get_session(self, manager):
        """兼容没有 get_session 的旧管理器：从 sessions 字典取。"""
        s = manager.create_session("A")
        legacy = MagicMock(spec=["get_current_session", "create_session", "save_session", "sessions"])
        legacy.sessions = {s.session_id: s}
        legacy.get_current_session.return_value = None
        ctx = ConversationContext(legacy, session_id=s.session_id, num_ctx=1000, complete=lambda p: "x")
        assert ctx.session() is s

    def test_metadata_not_dict_is_reset(self, manager):
        ctx = make_ctx(manager)
        ctx.record("q", "a")
        session = manager.get_current_session()
        session.metadata = "garbage"
        assert ctx.metrics()["turns"] == 1
        session.metadata["context"] = "bad"
        assert ctx.metrics()["compressions"] == 0


# ==================== 压缩 ====================

class TestCompression:
    def test_auto_compress_when_over_threshold(self, manager):
        calls = []

        def fake(prompt):
            calls.append(prompt)
            return "  <think>思考</think>合并后的摘要  "

        ctx = make_ctx(manager, complete=fake, num_ctx=1000, ratio=0.3, recent_turns=1)  # budget 300
        events = []
        for i in range(4):
            ctx.record(f"问题{i}", "答案内容" * 30, progress=lambda e: events.append(e))
        m = ctx.metrics()
        assert m["compressions"] >= 1
        assert m["summary"] == "合并后的摘要"
        assert calls and "已有摘要" in calls[0] and "问题0" in calls[0]
        stages = [e["stage"] for e in events]
        assert "context_compress" in stages and "context_compressed" in stages
        assert any("压缩历史上下文" in e["message"] for e in events)
        # 原始消息仍完整保留在会话中（非破坏性）
        assert len(manager.get_current_session().messages) == 8

    def test_no_compress_under_threshold(self, manager):
        ctx = make_ctx(manager)
        ctx.record("q", "a")
        assert ctx.maybe_compress() is False
        assert ctx.metrics()["compressions"] == 0

    def test_manual_compact_folds_older_turns(self, manager):
        ctx = make_ctx(manager, ratio=10, recent_turns=2)
        for i in range(5):
            ctx.record(f"q{i}", f"a{i}")
        result = ctx.compact()
        assert result["folded_messages"] == 6 and result["compressions"] == 1
        assert result["summary"] == "LLM摘要"
        assert [m["content"] for m in ctx.live_messages()] == ["q3", "a3", "q4", "a4"]
        # 再次 compact：没有超过 K 轮的内容可折叠
        assert ctx.compact() is None
        # 再加一轮后可继续折叠，摘要串起来
        ctx.record("q5", "a5")
        result = ctx.compact()
        assert result["folded_messages"] == 2 and result["compressions"] == 2

    def test_llm_failure_falls_back_to_heuristic(self, manager):
        def boom(prompt):
            raise RuntimeError("ollama down")

        ctx = make_ctx(manager, complete=boom, ratio=10, recent_turns=1)
        ctx.record("DJI OSMO 360 是什么", "一款全景相机")
        ctx.record("q2", "a2")
        result = ctx.compact()
        assert "用户问：DJI OSMO 360 是什么" in result["summary"]
        assert "助手答：一款全景相机" in result["summary"]

    def test_llm_empty_falls_back_and_truncates(self, manager):
        ctx = make_ctx(manager, complete=lambda p: "", ratio=10, recent_turns=1)
        for i in range(30):
            ctx.record("问" * 50, "答" * 100)
        result = ctx.compact()
        assert result["summary"].endswith("…")
        assert len(result["summary"]) <= cc.SUMMARY_MAX_CHARS + 1

    def test_llm_output_too_long_truncated(self, manager):
        ctx = make_ctx(manager, complete=lambda p: "长" * 2000, ratio=10, recent_turns=1)
        ctx.record("q1", "a1")
        ctx.record("q2", "a2")
        assert len(ctx.compact()["summary"]) == cc.SUMMARY_MAX_CHARS + 1

    def test_compact_covers_pointer_when_target_missing(self, manager):
        """summary_covers 指针推进：被折叠消息对象不在列表中时按数量推进。"""
        ctx = make_ctx(manager, ratio=10, recent_turns=1)
        ctx.record("q1", "a1")
        ctx.record("q2", "a2")
        session = manager.get_current_session()
        with patch.object(ConversationContext, "_turns", side_effect=lambda msgs: [[dict(m) for m in msgs[:2]], [dict(m) for m in msgs[2:]]]):
            ctx.compact()
        assert session.metadata["context"]["summary_covers"] == 2


# ==================== 问题改写 ====================

class TestRewrite:
    def test_no_history_no_llm_call(self, manager):
        calls = []
        ctx = make_ctx(manager, complete=lambda p: calls.append(p) or "x")
        r = ctx.rewrite_question("它多少钱")
        assert r == {"question": "它多少钱", "original": "它多少钱", "changed": False}
        assert calls == []

    def test_standalone_question_no_llm_call(self, manager):
        calls = []
        ctx = make_ctx(manager, complete=lambda p: calls.append(p) or "x")
        ctx.record("DJI OSMO 360 是什么", "全景相机")
        q = "请详细介绍一下 Cloudflare Tunnel 的配置方法与排错"
        assert ctx.rewrite_question(q)["changed"] is False
        assert calls == []

    def test_followup_rewritten(self, manager):
        events = []
        ctx = make_ctx(manager, complete=lambda p: '改写后的问题："DJI OSMO 360 多少钱"\n多余说明')
        ctx.record("DJI OSMO 360 是什么", "全景相机")
        r = ctx.rewrite_question("它多少钱", progress=lambda e: events.append(e))
        assert r["changed"] is True and r["question"] == "DJI OSMO 360 多少钱"
        assert r["original"] == "它多少钱"
        assert [e["stage"] for e in events] == ["context_rewrite", "context_rewritten"]
        assert "已理解为" in events[1]["message"]

    def test_rewrite_unchanged_when_llm_echoes_or_fails(self, manager):
        ctx = make_ctx(manager, complete=lambda p: "它多少钱")
        ctx.record("q", "a")
        assert ctx.rewrite_question("它多少钱")["changed"] is False

        def boom(p):
            raise RuntimeError("x")
        ctx2 = make_ctx(manager, complete=boom)
        assert ctx2.rewrite_question("它多少钱")["changed"] is False

        ctx3 = make_ctx(manager, complete=lambda p: "")
        assert ctx3.rewrite_question("它多少钱")["changed"] is False

        ctx4 = make_ctx(manager, complete=lambda p: "长" * 400)
        assert ctx4.rewrite_question("它多少钱")["changed"] is False
        assert ctx4.rewrite_question("")["changed"] is False

    def test_rewrite_with_only_summary_history(self, manager):
        ctx = make_ctx(manager, complete=lambda p: "DJI 多少钱")
        ctx.record("q", "a")
        session = manager.get_current_session()
        session.metadata["context"]["summary"] = "摘要"
        session.metadata["context"]["summary_covers"] = 2
        assert ctx.has_history() is True
        assert ctx.rewrite_question("它多少钱")["changed"] is True


# ==================== health / 建议新会话 ====================

class TestHealth:
    def test_fresh_session_no_suggestion(self, manager):
        ctx = make_ctx(manager)
        h = ctx.health("第一个问题")
        assert h["suggest_new_session"] is False and h["reasons"] == []
        ctx.record("第一个问题", "答")
        h = ctx.health()
        assert h["suggest_new_session"] is False

    def test_compressions_threshold(self, manager):
        ctx = make_ctx(manager, ratio=10, recent_turns=1)
        for i in range(3):
            ctx.record(f"q{i}", f"a{i}")
            ctx.compact()
        h = ctx.health()
        assert "compressions" in h["reasons"] and h["suggest_new_session"] is True
        assert format_suggest_hint(h).startswith("💡 对话较长（已压缩")
        # 展示后不再提示
        ctx.mark_suggested()
        assert ctx.health()["suggest_new_session"] is False
        # 继续当前会话：阈值 = 当前压缩数 + 2
        ctx.continue_current()
        meta = manager.get_current_session().metadata["context"]
        assert meta["suggest_after_compressions"] == meta["compressions"] + 2
        assert ctx.health()["suggest_new_session"] is False
        ctx.record("q", "a"); ctx.compact()
        assert ctx.health()["suggest_new_session"] is False
        ctx.record("q", "a"); ctx.compact()
        assert ctx.health()["suggest_new_session"] is True

    def test_usage_rule_requires_prior_compression(self, manager):
        ctx = make_ctx(manager, num_ctx=1000, ratio=0.3, recent_turns=3)
        ctx.record("q", "中" * 500)
        h = ctx.health()
        assert h["usage_ratio"] >= 0.9
        assert "usage" not in h["reasons"]
        manager.get_current_session().metadata["context"]["compressions"] = 1
        assert "usage" in ctx.health()["reasons"]

    def test_topic_drift_rule(self, manager):
        ctx = make_ctx(manager)
        ctx.record("DJI OSMO 360 的售价是多少", "官方售价 2999 元起")
        h = ctx.health("请介绍一下 Cloudflare Tunnel 的完整配置方法和排错流程")
        assert "topic_drift" in h["reasons"] and h["suggest_new_session"] is True
        assert "话题似乎已切换" in format_suggest_hint(h)
        # 追问不算漂移
        assert "topic_drift" not in ctx.health("它多少钱")["reasons"]
        # 已记录为最后一轮的问题：与其之前的轮次比较
        q = "请介绍一下 Cloudflare Tunnel 的完整配置方法和排错流程"
        ctx.record(q, "见文档")
        assert "topic_drift" in ctx.health(q)["reasons"]

    def test_idle_rule(self, manager):
        ctx = make_ctx(manager)
        ctx.record("q", "a")
        session = manager.get_current_session()
        old = (datetime.now() - timedelta(hours=7)).isoformat()
        for m in session.messages:
            m["timestamp"] = old
        h = ctx.health("新问题来了吗")
        assert "idle" in h["reasons"] and h["idle_hours"] >= 6.9
        assert "小时" in format_suggest_hint(h)
        # 当前问题已被记录（时间为现在）时，排除它来衡量空闲
        ctx.record("新问题来了吗", "答")
        assert "idle" in ctx.health("新问题来了吗")["reasons"]

    def test_bad_timestamp_ignored(self, manager):
        ctx = make_ctx(manager)
        ctx.record("q", "a")
        session = manager.get_current_session()
        session.messages[-1]["timestamp"] = "not-a-date"
        session.messages[0]["timestamp"] = (datetime.now() - timedelta(hours=8)).isoformat()
        assert "idle" in ctx.health("x")["reasons"]
        for m in session.messages:
            m.pop("timestamp", None)
        assert ctx.health("x")["idle_hours"] == 0.0

    def test_only_compressions_after_continue(self, manager):
        ctx = make_ctx(manager)
        ctx.record("DJI OSMO 360 售价", "2999")
        ctx.continue_current()
        h = ctx.health("请介绍一下 Cloudflare Tunnel 的完整配置方法和排错流程")
        assert h["reasons"] == []

    def test_merge_health(self):
        pre = {"reasons": ["idle"], "suggest_new_session": True, "idle_hours": 7.5}
        post = {"reasons": ["compressions"], "suggest_new_session": False, "compressions": 2}
        merged = merge_health(pre, post)
        assert merged["reasons"] == ["idle", "compressions"]
        assert merged["suggest_new_session"] is True
        assert merged["idle_hours"] == 7.5 and merged["compressions"] == 2
        assert merge_health({}, {})["suggest_new_session"] is False
        assert merge_health(None, None)["reasons"] == []

    def test_format_helpers(self):
        assert format_suggest_hint({}) == ""
        assert format_suggest_hint({"suggest_new_session": True, "reasons": ["usage"], "compressions": 0}) == \
            "💡 对话较长，建议新建会话以获得更好的回答质量"
        assert format_context_status({}) == ""
        assert format_context_status({"history_tokens": 3200, "budget": 4800, "compressions": 0}) == "上下文 3.2K / 4.8K"
        assert "已压缩 2 次" in format_context_status({"history_tokens": 1, "budget": 2, "compressions": 2})


# ==================== 清空 / 新建 / 携带摘要 ====================

class TestClearAndNewSession:
    def test_clear_keeps_session(self, manager):
        ctx = make_ctx(manager)
        ctx.record("q", "a")
        sid = manager.get_current_session().session_id
        assert ctx.clear() is True
        assert manager.get_current_session().session_id == sid
        assert ctx.all_messages() == [] and ctx.metrics()["compressions"] == 0

    def test_new_session_without_carry(self, manager):
        ctx = make_ctx(manager)
        ctx.record("q", "a")
        s = ctx.new_session(title="新")
        assert s.title == "新" and ctx.session_id == s.session_id
        assert ctx.build_messages() == []

    def test_new_session_with_carry(self, manager):
        ctx = make_ctx(manager, ratio=10, recent_turns=1)
        ctx.record("DJI OSMO 360 是什么", "全景相机")
        ctx.record("它多少钱", "2999 元")
        ctx.compact()  # 摘要 = "LLM摘要"，live = 最近 1 轮
        carried = ctx.carry_summary_text()
        assert carried.startswith("LLM摘要") and "2999" in carried
        s = ctx.new_session(carry_summary=True)
        built = ctx.build_messages()
        assert len(built) == 1 and built[0]["role"] == "system"
        assert "承接自上一会话" in built[0]["content"] and "LLM摘要" in built[0]["content"]
        assert ctx.has_history() is True
        assert manager.get_current_session().session_id == s.session_id

    def test_carry_summary_truncated(self, manager):
        ctx = make_ctx(manager, ratio=10, recent_turns=6)
        for _ in range(6):
            ctx.record("问" * 300, "答" * 300)
        carried = ctx.carry_summary_text()
        assert carried.endswith("…") and len(carried) <= 451


# ==================== 旧历史迁移 ====================

class TestMigrateLegacy:
    def test_missing_file(self, tmp_path, manager):
        assert migrate_legacy_history(str(tmp_path / "nope.json"), manager) == 0

    def test_bad_json(self, tmp_path, manager):
        f = tmp_path / "h.json"
        f.write_text("{bad", encoding="utf-8")
        assert migrate_legacy_history(str(f), manager) == 0
        assert f.exists()

    def test_migrates_and_archives(self, tmp_path, manager):
        f = tmp_path / "h.json"
        f.write_text(json.dumps([
            {"role": "system", "content": "SYS"},
            {"role": "user", "content": "读取 a.py"},
            {"role": "assistant", "content": "Thought: x\nAction: read_file\nAction Input: {}"},
            {"role": "user", "content": "Observation: 内容\n请继续"},
            {"role": "assistant", "content": "Final Answer: 文件里是 hello"},
            "garbage",
        ], ensure_ascii=False), encoding="utf-8")
        prev = manager.create_session("我的会话")
        n = migrate_legacy_history(str(f), manager)
        assert n == 2
        assert not f.exists() and (tmp_path / "h.json.migrated").exists()
        migrated = [s for s in manager.sessions.values() if "迁移" in s.title][0]
        assert [m["content"] for m in migrated.messages] == ["读取 a.py", "文件里是 hello"]
        # 不抢占用户正在使用的会话
        assert manager.current_session_id == prev.session_id

    def test_migrates_without_prior_current(self, tmp_path, manager):
        f = tmp_path / "h.json"
        f.write_text(json.dumps([{"role": "user", "content": "hi"}, {"role": "assistant", "content": "hello"}]), encoding="utf-8")
        assert migrate_legacy_history(str(f), manager) == 2
        assert "迁移" in manager.get_current_session().title

    def test_empty_content_archives_only(self, tmp_path, manager):
        f = tmp_path / "h.json"
        f.write_text(json.dumps([{"role": "system", "content": "SYS"}]), encoding="utf-8")
        assert migrate_legacy_history(str(f), manager) == 0
        assert (tmp_path / "h.json.migrated").exists()
        assert manager.sessions == {}

    def test_manager_failure_returns_zero(self, tmp_path):
        f = tmp_path / "h.json"
        f.write_text(json.dumps([{"role": "user", "content": "hi"}]), encoding="utf-8")
        bad = MagicMock()
        bad.create_session.side_effect = RuntimeError("x")
        assert migrate_legacy_history(str(f), bad) == 0

    def test_default_path_from_config(self, tmp_path, manager, monkeypatch):
        from config import Config
        monkeypatch.setattr(Config, "HISTORY_FILE", str(tmp_path / "none.json"))
        assert migrate_legacy_history(None, manager) == 0


# ==================== 默认 LLM 调用 / 单例 / 配置 ====================

class TestDefaultsAndSingleton:
    def test_default_complete_forces_think_false(self, monkeypatch):
        captured = {}

        class Resp:
            def raise_for_status(self):
                pass

            def json(self):
                return {"message": {"content": " 结果 "}}

        def fake_post(url, json=None, timeout=None):
            captured["url"] = url
            captured["json"] = json
            return Resp()

        monkeypatch.setattr("requests.post", fake_post)
        assert cc._default_complete("prompt") == "结果"
        assert captured["json"]["think"] is False
        assert captured["json"]["stream"] is False
        assert captured["url"].endswith("/api/chat")
        assert captured["json"]["options"]["num_ctx"] == cc.resolve_num_ctx()

    def test_resolve_num_ctx_and_budget_follow_config(self, monkeypatch):
        import config
        monkeypatch.setattr(config, "LLM_NUM_CTX", 16384)
        ctx = ConversationContext(MagicMock(), complete=lambda p: "")
        assert ctx.num_ctx == 16384
        assert ctx.budget == int(16384 * config.CONTEXT_HISTORY_RATIO)
        monkeypatch.setattr(config, "CONTEXT_HISTORY_RATIO", 0.5)
        assert ctx.budget == 8192

    def test_budget_floor(self):
        ctx = ConversationContext(MagicMock(), num_ctx=100, ratio=0.1, complete=lambda p: "")
        assert ctx.budget == 256

    def test_singleton_migrates_once(self, tmp_path, monkeypatch):
        import session_manager as sm
        cc.reset_conversation_context()
        manager = SessionManager(str(tmp_path / "s"))
        monkeypatch.setattr(sm, "_session_manager_singleton", manager)
        calls = []
        monkeypatch.setattr(cc, "migrate_legacy_history", lambda **kw: calls.append(kw) or 0)
        a = cc.get_conversation_context()
        b = cc.get_conversation_context()
        assert a is b and a.manager is manager
        assert len(calls) == 1
        cc.reset_conversation_context()
        assert cc._context_singleton is None

    def test_singleton_migration_error_swallowed(self, tmp_path, monkeypatch):
        import session_manager as sm
        cc.reset_conversation_context()
        monkeypatch.setattr(sm, "_session_manager_singleton", SessionManager(str(tmp_path / "s")))

        def boom(**kw):
            raise RuntimeError("x")
        monkeypatch.setattr(cc, "migrate_legacy_history", boom)
        assert cc.get_conversation_context() is not None
        cc.reset_conversation_context()

    def test_cfg_helper_fallback(self, monkeypatch):
        assert cc._cfg("NOT_EXIST_XYZ", 7) == 7

    def test_emit_swallows_callback_errors(self):
        def bad(evt):
            raise RuntimeError("x")
        cc._emit(bad, "s", "m")
        cc._emit(None, "s", "m")

    def test_clean_single_line(self):
        assert cc._clean_single_line('\n\n"改写: 你好"\n') == "你好"
        assert cc._clean_single_line("") == ""

    def test_config_context_defaults(self):
        import config
        assert config.CONTEXT_HISTORY_RATIO == 0.30
        assert config.CONTEXT_RECENT_TURNS == 3
        assert config.CONTEXT_SUGGEST_NEW_AFTER_COMPRESSIONS == 2
        assert config.CONTEXT_SUGGEST_IDLE_HOURS == 6
