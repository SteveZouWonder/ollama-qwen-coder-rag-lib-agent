"""ResultIntegrator 的 LLM 综合 answer / sources / 竞争评审（P0-3、P0-5、P0-6）。"""
import pytest

from agents.agent_types import AgentResult, AgentTask
from collaboration.result_integrator import ResultIntegrator


def _r(agent, output, success=True, task_id="t1", err="", sources=None, et=1.0):
    return AgentResult(task_id=task_id, agent_id=agent, success=success, output=output,
                       metadata={}, execution_time=et, error_message=err, sources=sources or [])


def _t(task_id, desc, ttype="general"):
    return AgentTask(task_id=task_id, task_type=ttype, description=desc,
                     required_capabilities=[ttype], input_data={"request": desc})


class TestIntegrateAnswer:
    def test_llm_answer_and_prompt_content(self):
        seen = {}

        def complete(prompt):
            seen["p"] = prompt
            return "<think>x</think>最终：快排已实现并通过测试。"

        integ = ResultIntegrator(complete=complete)
        results = [_r("code", "已写 qs.py", task_id="a"), _r("test", "3 passed", task_id="b")]
        tasks = [_t("a", "写快排", "code_generation"), _t("b", "写测试", "testing")]
        out = integ.integrate(results, tasks, request="写快排并测试")
        assert out["answer"] == "最终：快排已实现并通过测试。"
        assert out["answer_method"] == "llm"
        assert out["summary"].startswith("执行了 2 个任务")
        assert "写快排并测试" in seen["p"]
        assert "写快排" in seen["p"] and "已写 qs.py" in seen["p"]
        assert "[子任务 2] 写测试" in seen["p"]
        assert out["tasks"][0]["description"] == "写快排"

    def test_failed_subtask_in_prompt_and_output(self):
        seen = {}

        def complete(prompt):
            seen["p"] = prompt
            return "部分完成"
        integ = ResultIntegrator(complete=complete)
        results = [_r("code", "ok", task_id="a"), _r("test", "", success=False, err="timeout", task_id="b")]
        out = integ.integrate(results, request="r")
        assert out["success"] is False
        assert "失败（timeout）" in seen["p"]
        assert out["answer"] == "部分完成"

    def test_single_success_is_direct_without_llm(self):
        calls = []
        integ = ResultIntegrator(complete=lambda p: calls.append(p) or "x")
        out = integ.integrate([_r("rag", "  直接答案 ")], request="q")
        assert out["answer"] == "直接答案"
        assert out["answer_method"] == "direct"
        assert calls == []

    def test_llm_failure_falls_back_to_concat(self):
        def boom(p):
            raise RuntimeError("down")
        integ = ResultIntegrator(complete=boom)
        results = [_r("code", "输出A", task_id="a"), _r("test", "", success=False, err="E", task_id="b")]
        tasks = [_t("a", "任务A"), _t("b", "任务B")]
        out = integ.integrate(results, tasks, request="r")
        assert out["answer_method"] == "concat"
        assert "**任务A**（code）" in out["answer"] and "输出A" in out["answer"]
        assert "**任务B**（test）❌ 失败：E" in out["answer"]

    def test_llm_empty_output_falls_back(self):
        integ = ResultIntegrator(complete=lambda p: "   ")
        out = integ.integrate([_r("a", "x", task_id="1"), _r("b", "y", task_id="2")])
        assert out["answer_method"] == "concat"
        assert "子任务 1" in out["answer"]  # 无任务描述时用序号

    def test_use_llm_false(self):
        calls = []
        integ = ResultIntegrator(complete=lambda p: calls.append(p) or "x", use_llm=False)
        out = integ.integrate([_r("a", "x", task_id="1"), _r("b", "y", task_id="2")])
        assert calls == [] and out["answer_method"] == "concat"

    def test_default_complete_network_blocked(self):
        integ = ResultIntegrator()
        out = integ.integrate([_r("a", "x", task_id="1"), _r("b", "y", task_id="2")])
        assert out["answer_method"] == "concat"

    def test_long_outputs_truncated_in_prompt(self):
        seen = {}
        integ = ResultIntegrator(complete=lambda p: seen.setdefault("p", p) and "ok")
        results = [_r(f"a{i}", "x" * 5000, task_id=str(i)) for i in range(4)]
        integ.integrate(results, request="r")
        assert "已截断" in seen["p"]
        assert len(seen["p"]) < 4 * 5000

    def test_parallel_and_sequential_carry_mode_and_answer(self):
        integ = ResultIntegrator(complete=lambda p: "综合")
        rs = [_r("a", "x", task_id="1"), _r("b", "y", task_id="2")]
        p = integ.integrate_parallel(rs, request="r")
        s = integ.integrate_sequential(rs, request="r")
        assert p["mode"] == "parallel" and p["answer"] == "综合"
        assert s["mode"] == "sequential" and s["answer"] == "综合"


class TestSources:
    def test_merge_sources_dedup_and_agent(self):
        rs = [
            _r("rag", "a", task_id="1", sources=[
                {"kind": "kb", "file": "a.md", "score": 0.7},
                {"kind": "web", "url": "https://x", "title": "X"},
            ]),
            _r("rag2", "b", task_id="2", sources=[
                {"kind": "kb", "file": "a.md", "score": 0.6},
                {"kind": "kb", "file": "b.md"},
                "bad",
            ]),
        ]
        merged = ResultIntegrator.merge_sources(rs)
        assert [s.get("file") or s.get("url") for s in merged] == ["a.md", "https://x", "b.md"]
        assert merged[0]["agent_id"] == "rag"
        assert merged[2]["agent_id"] == "rag2"

    def test_integrate_exposes_sources(self):
        integ = ResultIntegrator(use_llm=False)
        out = integ.integrate([_r("rag", "a", sources=[{"kind": "kb", "file": "a.md"}])])
        assert out["sources"] == [{"kind": "kb", "file": "a.md", "agent_id": "rag"}]


class TestCompetitiveReview:
    def _cands(self):
        return [
            _r("a1", "短答案", et=1.0, sources=[{"kind": "kb", "file": "a.md"}]),
            _r("a2", "一个更长但未必更好的答案", et=5.0),
        ]

    def test_llm_picks_best(self):
        seen = {}

        def complete(prompt):
            seen["p"] = prompt
            return '{"best": 0, "reason": "更准确"}'
        out = ResultIntegrator(complete=complete).integrate_competitive(self._cands(), request="任务X")
        assert out["best_result"]["agent_id"] == "a1"
        assert out["selection_criteria"] == "LLM 评审选优：更准确"
        assert out["answer"] == "短答案"
        assert out["sources"] == [{"kind": "kb", "file": "a.md", "agent_id": "a1"}]
        assert "任务X" in seen["p"] and "[候选 1]" in seen["p"]
        assert "a1" in out["summary"] and "LLM 评审选优" in out["summary"]

    @pytest.mark.parametrize("bad", ["", "nope", '{"best": 7}', '{"best": "x"}', '{"reason": "r"}'])
    def test_bad_review_falls_back_to_longest(self, bad):
        out = ResultIntegrator(complete=lambda p: bad).integrate_competitive(self._cands())
        assert out["best_result"]["agent_id"] == "a2"
        assert "最长" in out["selection_criteria"]

    def test_review_exception_falls_back(self):
        def boom(p):
            raise RuntimeError("x")
        out = ResultIntegrator(complete=boom).integrate_competitive(self._cands())
        assert out["best_result"]["agent_id"] == "a2"

    def test_single_success_skips_review(self):
        calls = []
        cands = [_r("a1", "ok"), _r("a2", "", success=False, err="e")]
        out = ResultIntegrator(complete=lambda p: calls.append(p) or "{}").integrate_competitive(cands)
        assert calls == []
        assert out["best_result"]["agent_id"] == "a1"
        assert out["selection_criteria"] == "唯一成功候选"
        assert out["success"] is True

    def test_only_successful_are_candidates(self):
        seen = {}
        cands = [_r("bad", "", success=False, err="e"), _r("g1", "x"), _r("g2", "yy")]

        def complete(prompt):
            seen["p"] = prompt
            return '{"best": 1}'
        out = ResultIntegrator(complete=complete).integrate_competitive(cands)
        assert "bad" not in seen["p"]
        assert out["best_result"]["agent_id"] == "g2"
        assert out["selection_criteria"] == "LLM 评审选优"

    def test_use_llm_false_uses_longest(self):
        out = ResultIntegrator(use_llm=False).integrate_competitive(self._cands())
        assert out["best_result"]["agent_id"] == "a2"

    def test_empty(self):
        out = ResultIntegrator().integrate_competitive([])
        assert out["success"] is False
