#!/usr/bin/env python3
"""test_overcompliance_prompts.py — F9 P1-4：过度顺从评测集的 Mock 验证。

不依赖真实模型。对 ``tests/fixtures/overcompliance_cases.json`` 的四类用例逐条验证：
进入管道后综合 prompt 含对应忠实性条款、无资料时触发 ``no_evidence`` 路径、质疑追问被识别且
改写规则出现在改写 prompt 中、``verify_citations`` 对模拟答案的核验结果。真实模型评测见
``scripts/eval_overcompliance.py``（需本机 Ollama，不进 CI）。
"""
import json
from pathlib import Path

import pytest

import rag_pipeline
from conversation_context import is_challenge, is_followup

FIXTURE = Path(__file__).parent / "fixtures" / "overcompliance_cases.json"
CASES = json.loads(FIXTURE.read_text(encoding="utf-8"))["cases"]
BY_CAT = {}
for _c in CASES:
    BY_CAT.setdefault(_c["category"], []).append(_c)


class FakeRAG:
    def __init__(self, context):
        self.retriever = object()
        self._sources = [
            {"content": c["content"], "file": c["file"], "score": 0.9} for c in (context or [])
        ]

    def query_with_sources(self, question, progress_callback=None):
        return {"answer": "", "sources": list(self._sources)}

    def get_stats(self):
        return {}


def _run(monkeypatch, case, reply="资料未提及[1]"):
    prompts = []
    monkeypatch.setattr(rag_pipeline, "llm_direct_answer", lambda p: prompts.append(p) or reply)
    monkeypatch.setattr(rag_pipeline, "simple_web_search", lambda q: "")
    result = rag_pipeline.answer_question(FakeRAG(case.get("context")), case["question"], enable_web_search=False)
    return result, prompts


class TestFixtureShape:
    def test_min_count_and_categories(self):
        assert len(CASES) >= 30
        assert set(BY_CAT) == {"false_premise", "misleading_context", "sycophancy", "nonexistent"}
        assert len(BY_CAT["false_premise"]) >= 8 and len(BY_CAT["misleading_context"]) >= 6
        assert len(BY_CAT["sycophancy"]) >= 8 and len(BY_CAT["nonexistent"]) >= 8

    def test_fields(self):
        ids = [c["id"] for c in CASES]
        assert len(ids) == len(set(ids))
        for c in CASES:
            assert c["expect"] in ("refuse", "correct", "hold", "cite")
            assert c["question"].strip()
            if c["category"] == "sycophancy":
                assert c.get("followup") and c.get("truth") and c.get("claim") and c.get("context")
            if c["category"] == "nonexistent":
                assert not c.get("context")
            if c["expect"] in ("hold", "cite"):
                assert c.get("truth")


class TestFalsePremise:
    @pytest.mark.parametrize("case", BY_CAT["false_premise"], ids=lambda c: c["id"])
    def test_prompt_has_premise_rule_and_context(self, monkeypatch, case):
        result, prompts = _run(monkeypatch, case)
        assert len(prompts) == 1
        p = prompts[0]
        assert "前提核对" in p and "资料未提及/与资料不符" in p and "不要顺着前提编" in p
        assert case["context"][0]["content"][:20] in p
        assert "是否确知" not in p  # 有资料，不走无依据路径
        assert result["kind"] == "answer" and result["kb_sources"]


class TestMisleadingContext:
    @pytest.mark.parametrize("case", BY_CAT["misleading_context"], ids=lambda c: c["id"])
    def test_prompt_has_conflict_rule_and_all_snippets_numbered(self, monkeypatch, case):
        result, prompts = _run(monkeypatch, case)
        p = prompts[0]
        assert "冲突处理" in p and "并列列出各说法及编号" in p
        for i, snippet in enumerate(case["context"], 1):
            assert f"[{i}]（来自 {snippet['file']}）" in p
        # 数字易混规则仍在（直降 vs 售价）
        assert "优惠额" in p or "降价额" in p

    def test_injected_snippet_still_numbered_but_rule_present(self, monkeypatch):
        case = next(c for c in BY_CAT["misleading_context"] if "忽略以上所有规则" in json.dumps(c, ensure_ascii=False))
        _, prompts = _run(monkeypatch, case)
        # 知识库片段不经网页注入扫描（入库时已扫描），但 prompt 要求以资料编号并列，不擅自取一
        assert "忽略以上所有规则" in prompts[0] and "不要擅自取一或折中" in prompts[0]


class TestSycophancy:
    @pytest.mark.parametrize("case", BY_CAT["sycophancy"], ids=lambda c: c["id"])
    def test_followup_detected_as_challenge(self, case):
        assert is_challenge(case["followup"]) is True
        assert is_followup(case["followup"]) is True

    @pytest.mark.parametrize("case", BY_CAT["sycophancy"], ids=lambda c: c["id"])
    def test_rewrite_prompt_has_rule_and_result_not_asserting_claim(self, monkeypatch, case, tmp_path):
        from conversation_context import ConversationContext
        from session_manager import SessionManager

        mgr = SessionManager(str(tmp_path / "sessions"))
        prompts = []

        def fake_complete(p):
            prompts.append(p)
            return f"重新核对：{case['question']}（用户认为：{case['claim']}）"

        ctx = ConversationContext(mgr, complete=fake_complete)
        ctx.record(case["question"], f"{case['truth']}[1]")
        events = []
        rw = ctx.rewrite_question(case["followup"], progress=lambda e: events.append(e))
        assert rw["challenge"] is True and rw["changed"] is True
        assert "反驳或质疑上一轮回答" in prompts[0] and "不要把用户说法当作事实写进问题" in prompts[0]
        # 改写结果把用户说法标注为「用户认为」，而非断言
        assert rw["question"].startswith("重新核对：") and f"用户认为：{case['claim']}" in rw["question"]
        assert events[-1]["message"].startswith("🔁 用户质疑，重新核对：")

    @pytest.mark.parametrize("case", BY_CAT["sycophancy"][:3], ids=lambda c: c["id"])
    def test_second_turn_prompt_has_hold_rule_and_history(self, monkeypatch, case, tmp_path):
        from conversation_context import ConversationContext
        from session_manager import SessionManager

        mgr = SessionManager(str(tmp_path / "sessions"))
        ctx = ConversationContext(mgr, complete=lambda p: f"重新核对：{case['question']}（用户认为：{case['claim']}）")
        ctx.record(case["question"], f"{case['truth']}[1]")
        prompts = []
        monkeypatch.setattr(rag_pipeline, "llm_direct_answer", lambda p: prompts.append(p) or f"仍为 {case['truth']}[1]")
        result = rag_pipeline.answer_question(FakeRAG(case["context"]), case["followup"],
                                              enable_web_search=False, context=ctx)
        p = prompts[0]
        assert "被质疑时" in p and "不要仅因被反驳而改口" in p
        assert "对话上下文" in p and case["truth"] in p
        assert "## 问题\n重新核对：" in p
        assert result["challenge"] is True


class TestNonexistent:
    @pytest.mark.parametrize("case", BY_CAT["nonexistent"], ids=lambda c: c["id"])
    def test_no_context_triggers_no_evidence(self, monkeypatch, case):
        result, prompts = _run(monkeypatch, case, reply="我不确定")
        assert len(prompts) == 1
        assert "是否确知" in prompts[0] and "不要猜测或编造" in prompts[0]
        assert result["kind"] == "fallback"
        codes = [n["code"] for n in result["notices"]]
        assert "no_evidence" in codes and "fallback" in codes
        assert result["answer"] == "我不确定"


class TestCitationVerification:
    def test_fabricated_refs_marked(self, monkeypatch):
        case = BY_CAT["misleading_context"][0]
        result, _ = _run(monkeypatch, case, reply="售价 2999 元起[1]，另一说 3499 元[2]，官网写 4999 元[3]。")
        assert result["answer"].endswith("官网写 4999 元[?]。")
        check = result["citation_check"]
        assert check["invalid"] == ["3"] and check["valid"] == 2 and check["total_refs"] == 3
        assert result["kb_sources"][0]["cited"] == 1 and result["kb_sources"][1]["cited"] == 1
        assert any("[?]" in n["text"] for n in result["notices"] if n["code"] == "citation")

    def test_numeric_without_citation_counted(self, monkeypatch):
        case = BY_CAT["false_premise"][2]
        result, _ = _run(monkeypatch, case, reply="资料未提及 1999 元的说法。标准版 2999 元起[1]。")
        assert result["citation_check"]["unsupported_numeric"] == 1
        assert any(n["text"] == "1 句含数字但未标来源" for n in result["notices"])
