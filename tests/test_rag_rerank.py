#!/usr/bin/env python3
"""test_rag_rerank.py — 逐片段相关性筛选（F8 P2-1）单元测试。

覆盖：llm rerank 的 prompt/解析（keep/notes、越界/重复/非法 JSON）、解析失败回退
整体判定（保守保留）、高分跳过、cross-encoder 缺依赖回退 llm 并有提示、
cross-encoder 打分保留/排序。
"""
import sys
import types

import pytest

import rag_rerank


def _srcs(n=3, score=0.5):
    return [{"content": f"片段{i} " * 10, "file": f"f{i}.md", "score": score} for i in range(1, n + 1)]


def _events():
    evts = []
    return evts, (lambda e: evts.append(e))


# ==================== prompt / 解析 ====================

class TestPromptAndParse:
    def test_prompt_numbers_and_truncates(self):
        srcs = [{"content": "x" * 1000, "file": "a.md"}, {"content": "短", "file": "b.md"}]
        p = rag_rerank.build_rerank_prompt("问题", srcs)
        assert "[1]（a.md）" in p and "[2]（b.md）" in p
        assert "问题：问题" in p and '"keep"' in p
        # 每片段截 400 字
        assert "x" * 401 not in p and "x" * 400 in p

    def test_parse_keep_and_notes(self):
        out = rag_rerank.parse_rerank_output('{"keep":[2,1],"notes":{"1":"提到售价","2":"提到型号"}}', 3)
        assert out == {"keep": [2, 1], "notes": {1: "提到售价", 2: "提到型号"}}

    def test_parse_drops_out_of_range_and_duplicates(self):
        out = rag_rerank.parse_rerank_output('{"keep":[1,1,5,"2","x",0],"notes":{"9":"无","2":"ok"}}', 3)
        assert out["keep"] == [1, 2]
        assert out["notes"] == {2: "ok"}

    def test_parse_tolerates_fence_and_think(self):
        raw = "<think>思考</think>```json\n{\"keep\": [3]}\n```"
        assert rag_rerank.parse_rerank_output(raw, 3) == {"keep": [3], "notes": {}}

    def test_parse_invalid_returns_none(self):
        assert rag_rerank.parse_rerank_output("relevant", 3) is None
        assert rag_rerank.parse_rerank_output('{"notes":{}}', 3) is None
        assert rag_rerank.parse_rerank_output('{"keep":"1"}', 3) is None
        assert rag_rerank.parse_rerank_output("", 3) is None

    def test_llm_rerank_call_failure_returns_none(self):
        def boom(prompt):
            raise TimeoutError("timeout")
        assert rag_rerank.llm_rerank("q", _srcs(), complete=boom) is None

    def test_llm_rerank_empty_sources(self):
        assert rag_rerank.llm_rerank("q", [], complete=lambda p: pytest.fail("不应调用")) == {"keep": [], "notes": {}}


# ==================== rerank 统一入口（llm）====================

class TestRerankLLM:
    def test_keeps_selected_with_notes_in_original_order(self, monkeypatch):
        monkeypatch.setattr(rag_rerank, "_reranker_kind", lambda: "llm")
        calls = []

        def fake(prompt):
            calls.append(prompt)
            return '{"keep":[3,1],"notes":{"1":"含价格","3":"含型号"}}'

        evts, cb = _events()
        kept = rag_rerank.rerank("q", _srcs(3), progress=cb, complete=fake)
        assert len(calls) == 1
        assert [s["file"] for s in kept] == ["f1.md", "f3.md"]
        assert kept[0]["rerank_note"] == "含价格" and kept[1]["rerank_note"] == "含型号"
        stages = [e["stage"] for e in evts]
        assert "rerank" in stages and "rerank_done" in stages
        done = next(e for e in evts if e["stage"] == "rerank_done")
        assert done["kept"] == 2 and done["total"] == 3 and done["method"] == "llm"

    def test_all_irrelevant_returns_empty(self):
        evts, cb = _events()
        kept = rag_rerank.rerank("q", _srcs(2), progress=cb, complete=lambda p: '{"keep":[]}', kind="llm")
        assert kept == []
        assert any(e["stage"] == "rerank_done" and e["kept"] == 0 for e in evts)

    def test_invalid_json_falls_back_to_judge_conservative(self, monkeypatch):
        """非法 JSON → 回退 judge_kb_relevance；判定器不可用时保守保留全部。"""
        import rag_pipeline
        monkeypatch.setattr(rag_pipeline, "judge_kb_relevance", lambda q, s: True)
        evts, cb = _events()
        srcs = _srcs(2)
        kept = rag_rerank.rerank("q", srcs, progress=cb, complete=lambda p: "这不是JSON", kind="llm")
        assert kept == srcs
        assert any(e["stage"] == "rerank_fallback" for e in evts)

    def test_invalid_json_fallback_respects_judge_false(self, monkeypatch):
        import rag_pipeline
        monkeypatch.setattr(rag_pipeline, "judge_kb_relevance", lambda q, s: False)
        kept = rag_rerank.rerank("q", _srcs(2), complete=lambda p: "garbage", kind="llm")
        assert kept == []

    def test_timeout_falls_back_conservative(self, monkeypatch):
        import rag_pipeline
        monkeypatch.setattr(rag_pipeline, "judge_kb_relevance", lambda q, s: (_ for _ in ()).throw(RuntimeError("x")))

        def slow(prompt):
            raise TimeoutError("timeout")

        kept = rag_rerank.rerank("q", _srcs(2), complete=slow, kind="llm")
        assert len(kept) == 2  # 判定器也失败 → 保守保留

    def test_default_llm_blocked_in_tests_falls_back(self, monkeypatch):
        """默认 LLM（conftest 已拦截）不可用时也不抛异常。"""
        import rag_pipeline
        monkeypatch.setattr(rag_pipeline, "judge_kb_relevance", lambda q, s: True)
        assert len(rag_rerank.rerank("q", _srcs(2), kind="llm")) == 2

    def test_high_score_skips_llm(self):
        evts, cb = _events()
        srcs = _srcs(2, score=0.75)
        kept = rag_rerank.rerank("q", srcs, progress=cb, complete=lambda p: pytest.fail("不应调用"))
        assert kept == srcs
        assert any(e["stage"] == "rerank" and e.get("skipped") for e in evts)

    def test_empty_sources(self):
        assert rag_rerank.rerank("q", []) == []

    def test_kind_from_config(self, monkeypatch):
        import config
        monkeypatch.setattr(config, "RERANKER", "LLM ")
        assert rag_rerank._reranker_kind() == "llm"
        monkeypatch.setattr(config, "RERANKER_MODEL", "m")
        assert rag_rerank._reranker_model() == "m"

    def test_default_llm_complete_uses_helper(self, monkeypatch):
        """_llm_complete 走 llm_helper.complete_text（think=False、限 num_predict）。"""
        import collaboration.llm_helper as h
        seen = {}

        def fake(prompt, num_predict=512, timeout=None, temperature=0.2):
            seen.update(prompt=prompt, num_predict=num_predict)
            return "{}"

        monkeypatch.setattr(h, "complete_text", fake)
        # conftest 已把模块属性替换为拦截器；reload 取回原函数（模块对象不变，
        # 夹具结束时仍会把属性恢复为其保存的原对象）
        import importlib
        importlib.reload(rag_rerank)
        assert rag_rerank._llm_complete("p") == "{}"
        assert seen["num_predict"] == rag_rerank.NUM_PREDICT and seen["prompt"] == "p"


# ==================== cross-encoder ====================

class TestCrossEncoder:
    def test_missing_dependency_falls_back_to_llm_with_hint(self, monkeypatch):
        monkeypatch.setitem(sys.modules, "sentence_transformers", None)  # import → ImportError
        rag_rerank._CE_MODEL_CACHE.clear()
        evts, cb = _events()
        kept = rag_rerank.rerank(
            "q", _srcs(2), progress=cb, complete=lambda p: '{"keep":[2]}', kind="cross-encoder",
        )
        assert [s["file"] for s in kept] == ["f2.md"]
        fb = [e for e in evts if e["stage"] == "rerank_fallback"]
        assert fb and fb[0]["reason"] == "missing_dependency"
        assert "sentence-transformers" in fb[0]["message"]

    def test_cross_encoder_scores_and_sorts(self, monkeypatch):
        class FakeCE:
            def __init__(self, name):
                self.name = name

            def predict(self, pairs):
                # logits：第 1 个负（丢弃），第 2 个高，第 3 个中
                return [-3.0, 4.0, 0.5]

        fake_mod = types.SimpleNamespace(CrossEncoder=FakeCE)
        monkeypatch.setitem(sys.modules, "sentence_transformers", fake_mod)
        rag_rerank._CE_MODEL_CACHE.clear()
        evts, cb = _events()
        kept = rag_rerank.rerank("q", _srcs(3), progress=cb, kind="cross-encoder")
        assert [s["file"] for s in kept] == ["f2.md", "f3.md"]
        assert kept[0]["rerank_score"] > kept[1]["rerank_score"] >= rag_rerank.CE_KEEP_THRESHOLD
        assert any(e["stage"] == "rerank_done" and e["method"] == "cross-encoder" for e in evts)
        # 模型被缓存
        assert rag_rerank._CE_MODEL_CACHE

    def test_cross_encoder_probability_passthrough(self):
        assert rag_rerank._to_probability(0.7) == 0.7
        assert 0.5 < rag_rerank._to_probability(2.0) < 1.0
        assert rag_rerank._to_probability(-1000.0) == pytest.approx(0.0)

    def test_cross_encoder_runtime_error_falls_back_llm(self, monkeypatch):
        class BadCE:
            def __init__(self, name):
                raise RuntimeError("no gpu")

        monkeypatch.setitem(sys.modules, "sentence_transformers", types.SimpleNamespace(CrossEncoder=BadCE))
        rag_rerank._CE_MODEL_CACHE.clear()
        evts, cb = _events()
        kept = rag_rerank.rerank("q", _srcs(2), progress=cb, complete=lambda p: '{"keep":[1]}', kind="cross-encoder")
        assert [s["file"] for s in kept] == ["f1.md"]
        assert any(e["stage"] == "rerank_fallback" and "no gpu" in e["message"] for e in evts)
