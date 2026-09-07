"""TaskDecomposer 的 LLM 分解路径与回退（P0-2）。"""
import json

import pytest

from collaboration.task_decomposer import TaskDecomposer, TASK_TYPE_SPECS, MAX_SUBTASKS


class _Agent:
    def __init__(self, caps):
        self.capabilities = caps


ALL_AGENTS = [
    _Agent(["code_generation"]), _Agent(["testing"]), _Agent(["documentation"]),
    _Agent(["knowledge_retrieval", "general"]), _Agent(["audit"]),
]


def _llm(payload):
    text = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)
    return lambda prompt: text


class TestLLMDecompose:
    def test_llm_two_subtasks_with_dependency(self):
        d = TaskDecomposer(complete=_llm({"subtasks": [
            {"type": "code_generation", "description": "实现快排到 qs.py", "depends_on": []},
            {"type": "testing", "description": "为 qs.py 写并运行测试", "depends_on": [0]},
        ]}))
        tasks = d.decompose("写一个快速排序并写测试", ALL_AGENTS)
        assert d.last_method == "llm"
        assert [t.task_type for t in tasks] == ["code_generation", "testing"]
        # 每个子任务的 request 是独立描述，并带 original_request
        assert tasks[0].input_data["request"] == "实现快排到 qs.py"
        assert tasks[1].input_data["request"] == "为 qs.py 写并运行测试"
        assert tasks[1].input_data["original_request"] == "写一个快速排序并写测试"
        assert tasks[1].dependencies == [tasks[0].task_id]
        assert tasks[0].dependencies == []
        assert tasks[0].required_capabilities == ["code_generation"]
        assert tasks[0].priority == TASK_TYPE_SPECS["code_generation"]["priority"]
        assert tasks[0].metadata["decomposed_by"] == "llm"

    def test_single_intent_question_gives_one_task(self):
        """'检查一下这个 PDF 的价格' 由 LLM 判为纯问答，不再触发关键词 audit。"""
        d = TaskDecomposer(complete=_llm({"subtasks": [
            {"type": "knowledge_retrieval", "description": "查询 PDF 中的价格", "depends_on": []}]}))
        tasks = d.decompose("检查一下这个 PDF 的价格", ALL_AGENTS)
        assert len(tasks) == 1
        assert tasks[0].task_type == "knowledge_retrieval"

    def test_prompt_includes_request(self):
        seen = {}

        def complete(prompt):
            seen["p"] = prompt
            return '{"subtasks":[{"type":"general","description":"d"}]}'

        TaskDecomposer(complete=complete).decompose("我的请求", ALL_AGENTS)
        assert "我的请求" in seen["p"]
        assert "只输出 JSON" in seen["p"]

    def test_unknown_type_and_empty_description_skipped(self):
        d = TaskDecomposer(complete=_llm({"subtasks": [
            {"type": "magic", "description": "x"},
            {"type": "audit", "description": ""},
            {"type": "AUDIT", "description": "审计 a.py"},
            "not a dict",
        ]}))
        tasks = d.decompose("审计", ALL_AGENTS)
        assert d.last_method == "llm"
        assert [t.task_type for t in tasks] == ["audit"]

    def test_capability_missing_downgrades_to_general(self):
        d = TaskDecomposer(complete=_llm({"subtasks": [
            {"type": "audit", "description": "审计 a.py"}]}))
        tasks = d.decompose("审计", [_Agent(["knowledge_retrieval", "general"])])
        assert tasks[0].task_type == "general"
        assert tasks[0].required_capabilities == ["general"]

    def test_capability_missing_without_general_falls_back(self):
        d = TaskDecomposer(complete=_llm({"subtasks": [
            {"type": "audit", "description": "审计 a.py"}]}))
        tasks = d.decompose("实现代码", [_Agent(["code_generation"])])
        assert d.last_method == "rules"
        assert tasks[0].task_type == "code_generation"

    def test_max_subtasks_capped(self):
        items = [{"type": "general", "description": f"d{i}"} for i in range(10)]
        tasks = TaskDecomposer(complete=_llm({"subtasks": items})).decompose("many", ALL_AGENTS)
        assert len(tasks) == MAX_SUBTASKS

    def test_dependency_out_of_range_and_self_ignored(self):
        d = TaskDecomposer(complete=_llm({"subtasks": [
            {"type": "code_generation", "description": "a", "depends_on": [0, 9, -1, "x"]},
            {"type": "testing", "description": "b", "depends_on": [0, 1.0]},
        ]}))
        tasks = d.decompose("x", ALL_AGENTS)
        assert tasks[0].dependencies == []
        assert tasks[1].dependencies == [tasks[0].task_id]

    def test_no_agents_keeps_types(self):
        d = TaskDecomposer(complete=_llm({"subtasks": [{"type": "audit", "description": "a"}]}))
        tasks = d.decompose("x", None)
        assert tasks[0].task_type == "audit"


class TestFallback:
    @pytest.mark.parametrize("bad", ["", "not json", '{"subtasks": "x"}', '{"subtasks": []}', '{"other": 1}'])
    def test_bad_llm_output_falls_back_to_rules(self, bad):
        d = TaskDecomposer(complete=lambda p: bad)
        tasks = d.decompose("实现一个用户登录功能", ALL_AGENTS)
        assert d.last_method == "rules"
        assert tasks and tasks[0].task_type == "code_generation"
        assert tasks[0].input_data["original_request"] == "实现一个用户登录功能"

    def test_llm_exception_falls_back(self):
        def boom(p):
            raise TimeoutError("slow")
        d = TaskDecomposer(complete=boom)
        tasks = d.decompose("检索相关资料", ALL_AGENTS)
        assert d.last_method == "rules"
        assert tasks[0].task_type == "knowledge_retrieval"

    def test_use_llm_false_never_calls(self):
        calls = []

        def complete(p):
            calls.append(p)
            return "{}"
        d = TaskDecomposer(complete=complete, use_llm=False)
        d.decompose("实现代码", ALL_AGENTS)
        assert calls == []
        assert d.last_method == "rules"

    def test_empty_request_skips_llm(self):
        calls = []
        d = TaskDecomposer(complete=lambda p: calls.append(p) or "{}")
        tasks = d.decompose("   ", ALL_AGENTS)
        assert calls == []
        assert tasks[0].task_type == "general"

    def test_default_network_blocked_falls_back(self):
        """默认 complete（真实网络）被 conftest 拦截 → 规则回退。"""
        d = TaskDecomposer()
        tasks = d.decompose("中国国内DJI Action6的售价", ALL_AGENTS)
        assert d.last_method == "rules"
        assert len(tasks) == 1 and tasks[0].task_type == "general"
