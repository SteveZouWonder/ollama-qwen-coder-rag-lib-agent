"""MasterAgent 执行策略：真并行、依赖波次、上游传递、超时、竞争评审、进度文案（P0-4/5/8）。"""
import threading
import time

import pytest

from agents.agent_types import AgentTask, AgentResult, AgentType, AgentState, CollaborationMode
from agents.base_agent import BaseAgent
from agents.code_agent import CodeAgent
from agents import TestAgent
from agents.rag_agent import RAGAgent
from master_agent import MasterAgent


class SlowAgent(BaseAgent):
    """可控耗时的 Agent，记录并发峰值与收到的 input_data。"""
    lock = threading.Lock()
    running = 0
    peak = 0

    def __init__(self, agent_id, caps, delay=0.0, fail=False, output="ok"):
        super().__init__(agent_id=agent_id, agent_type=AgentType.CODE, capabilities=caps)
        self.delay = delay
        self.fail = fail
        self.output = output
        self.seen_inputs = []
        self.cancelled = False

    def cancel(self):
        self.cancelled = True

    def process_task(self, task):
        with SlowAgent.lock:
            SlowAgent.running += 1
            SlowAgent.peak = max(SlowAgent.peak, SlowAgent.running)
        try:
            self.seen_inputs.append(dict(task.input_data))
            if self.delay:
                time.sleep(self.delay)
            if self.fail:
                raise RuntimeError("boom")
            return AgentResult(task_id=task.task_id, agent_id=self.agent_id, success=True,
                               output=f"{self.output} by {self.agent_id}", metadata={}, execution_time=0)
        finally:
            with SlowAgent.lock:
                SlowAgent.running -= 1


@pytest.fixture(autouse=True)
def _reset_peak():
    SlowAgent.peak = 0
    SlowAgent.running = 0
    yield


def _decompose(items):
    import json
    return json.dumps({"subtasks": items}, ensure_ascii=False)


def _master(complete, agents, max_parallel=5):
    m = MasterAgent(config={"llm_complete": complete, "max_parallel_tasks": max_parallel})
    m.set_specialized_agents(agents)
    return m


class TestParallel:
    def test_independent_tasks_run_concurrently(self, scripted_complete):
        complete = scripted_complete(decompose=_decompose([
            {"type": "code_generation", "description": "a"},
            {"type": "testing", "description": "b"},
            {"type": "documentation", "description": "c"},
        ]))
        agents = [SlowAgent("c", ["code_generation"], 0.3), SlowAgent("t", ["testing"], 0.3),
                  SlowAgent("d", ["documentation"], 0.3)]
        m = _master(complete, agents)
        start = time.time()
        out = m.coordinate_task("r", CollaborationMode.PARALLEL)
        assert out["success"] is True
        assert time.time() - start < 0.8  # 串行需 0.9s
        assert SlowAgent.peak == 3
        assert out["mode"] == "parallel"
        assert out["answer"] == "综合回答"

    def test_dependency_waves_and_upstream(self, scripted_complete):
        complete = scripted_complete(decompose=_decompose([
            {"type": "code_generation", "description": "写代码"},
            {"type": "testing", "description": "写测试", "depends_on": [0]},
        ]))
        code = SlowAgent("c", ["code_generation"], 0.1, output="qs.py 已写")
        test = SlowAgent("t", ["testing"], 0.0)
        m = _master(complete, [code, test])
        out = m.coordinate_task("r", CollaborationMode.PARALLEL)
        assert out["success"] is True
        assert SlowAgent.peak == 1  # 有依赖：不同波次
        up = test.seen_inputs[0]["upstream"]
        assert up[0]["description"] == "写代码" and "qs.py 已写" in up[0]["output"]
        # 结果按依赖顺序排列
        assert [r["agent_id"] for r in out["results"]] == ["c", "t"]

    def test_max_parallel_respected(self, scripted_complete):
        complete = scripted_complete(decompose=_decompose([
            {"type": "general", "description": f"g{i}"} for i in range(4)]))
        agents = [SlowAgent(f"g{i}", ["general"], 0.15) for i in range(4)]
        m = _master(complete, agents, max_parallel=2)
        m.coordinate_task("r", CollaborationMode.PARALLEL)
        assert SlowAgent.peak <= 2

    def test_failed_task_marks_partial_failure_and_agent_idle(self, scripted_complete):
        complete = scripted_complete(decompose=_decompose([
            {"type": "code_generation", "description": "a"}, {"type": "testing", "description": "b"}]))
        bad = SlowAgent("c", ["code_generation"], fail=True)
        m = _master(complete, [bad, SlowAgent("t", ["testing"])])
        out = m.coordinate_task("r", CollaborationMode.PARALLEL)
        assert out["success"] is False
        assert out["failed_results"] == 1
        assert bad.get_state() == AgentState.IDLE
        failed = [r for r in out["results"] if not r["success"]][0]
        assert "boom" in failed["error_message"]


class TestTimeout:
    def test_execute_task_with_timeout_really_times_out(self):
        agent = SlowAgent("s", ["general"], delay=1.0)
        task = AgentTask(task_id="t", task_type="general", description="d",
                         required_capabilities=["general"], input_data={}, timeout=0.2)
        start = time.time()
        result = agent.execute_task_with_timeout(task)
        assert time.time() - start < 0.8
        assert result.success is False
        assert result.error_message == "timeout"
        assert result.metadata["timeout"] == 0.2
        assert agent.cancelled is True
        assert agent.get_state() == AgentState.IDLE

    def test_agent_config_timeout_wins_over_task_default(self):
        agent = SlowAgent("s", ["general"], delay=0.6)
        agent.config["timeout"] = 0.1
        task = AgentTask(task_id="t", task_type="general", description="d",
                         required_capabilities=["general"], input_data={})
        result = agent.execute_task_with_timeout(task)
        assert result.error_message == "timeout"

    def test_timeout_in_coordination(self, scripted_complete):
        complete = scripted_complete(decompose=_decompose([{"type": "general", "description": "g"}]))
        slow = SlowAgent("s", ["general"], delay=1.0)
        slow.config["timeout"] = 0.1
        m = _master(complete, [slow])
        out = m.coordinate_task("r", CollaborationMode.HIERARCHY)
        assert out["success"] is False
        assert out["results"][0]["error_message"] == "timeout"

    def test_process_task_returning_none(self):
        class NoneAgent(BaseAgent):
            def process_task(self, task):
                return None
        a = NoneAgent("n", AgentType.CODE, ["x"])
        task = AgentTask(task_id="t", task_type="x", description="d", required_capabilities=["x"], input_data={})
        r = a.execute_task_with_timeout(task)
        assert r.success is False and "未返回结果" in r.error_message

    def test_cancel_default_noop_and_stops_engine(self):
        a = SlowAgent("s", ["x"])
        BaseAgent.cancel(a)  # 无 _active_engine：不抛

        class Eng:
            stopped = False

            def stop(self):
                self.stopped = True
        a._active_engine = Eng()
        BaseAgent.cancel(a)
        assert a._active_engine.stopped is True


class TestSequentialAndHierarchy:
    def test_hierarchy_respects_dependency_order_and_upstream(self, scripted_complete):
        complete = scripted_complete(decompose=_decompose([
            {"type": "testing", "description": "写测试", "depends_on": [1]},
            {"type": "code_generation", "description": "写代码"},
        ]))
        code = SlowAgent("c", ["code_generation"], output="code done")
        test = SlowAgent("t", ["testing"])
        m = _master(complete, [code, test])
        out = m.coordinate_task("r", CollaborationMode.HIERARCHY)
        assert [r["agent_id"] for r in out["results"]] == ["c", "t"]
        assert "code done" in test.seen_inputs[0]["upstream"][0]["output"]
        assert out["decompose_method"] == "llm"

    def test_sequential_mode(self, scripted_complete):
        complete = scripted_complete(decompose=_decompose([
            {"type": "code_generation", "description": "a"}, {"type": "testing", "description": "b"}]))
        m = _master(complete, [SlowAgent("c", ["code_generation"]), SlowAgent("t", ["testing"])])
        out = m.coordinate_task("r", CollaborationMode.SEQUENTIAL)
        assert out["success"] is True and out["mode"] == "sequential"

    def test_unassigned_task_reported(self, scripted_complete):
        complete = scripted_complete(decompose=_decompose([
            {"type": "code_generation", "description": "a"}, {"type": "audit", "description": "b"}]))
        # audit 能力缺失但存在 general → 降级为 general；再让 general agent 忙碌导致未分配
        busy = SlowAgent("g", ["general"])
        busy.set_state(AgentState.BUSY)
        m = _master(complete, [SlowAgent("c", ["code_generation"]), busy])
        out = m.coordinate_task("r", CollaborationMode.HIERARCHY)
        assert out["success"] is False
        unassigned = [r for r in out["results"] if r["agent_id"] == "(未分配)"]
        assert unassigned and "general" in unassigned[0]["error_message"]

    def test_cyclic_dependency_does_not_hang(self, scripted_complete):
        complete = scripted_complete(decompose=_decompose([
            {"type": "code_generation", "description": "a", "depends_on": [1]},
            {"type": "testing", "description": "b", "depends_on": [0]},
        ]))
        m = _master(complete, [SlowAgent("c", ["code_generation"]), SlowAgent("t", ["testing"])])
        for mode in (CollaborationMode.HIERARCHY, CollaborationMode.PARALLEL):
            out = m.coordinate_task("r", mode)
            assert out["total_results"] == 2


class TestCompetitive:
    def test_parallel_execution_and_llm_review(self, scripted_complete):
        complete = scripted_complete(
            decompose=_decompose([{"type": "general", "description": "g"}]),
            review='{"best": 1, "reason": "更完整"}')
        agents = [SlowAgent("a", ["general"], 0.3, output="A"), SlowAgent("b", ["general"], 0.3, output="B")]
        m = _master(complete, agents)
        start = time.time()
        events = []
        out = m.coordinate_task("r", CollaborationMode.COMPETITIVE, progress=events.append)
        assert time.time() - start < 0.8
        assert SlowAgent.peak == 2
        assert out["best_result"]["agent_id"] == "b"
        assert out["selection_criteria"] == "LLM 评审选优：更完整"
        assert out["decompose_method"] == "llm"
        stages = [e["stage"] for e in events]
        assert stages.count("execute") == 2 and stages.count("task_done") == 2
        assert any("模型评审" in e["message"] for e in events if e["stage"] == "integrate")

    def test_competitive_requires_single_task(self, scripted_complete):
        complete = scripted_complete(decompose=_decompose([
            {"type": "code_generation", "description": "a"}, {"type": "testing", "description": "b"}]))
        m = _master(complete, [SlowAgent("c", ["code_generation"]), SlowAgent("t", ["testing"])])
        out = m.coordinate_task("r", CollaborationMode.COMPETITIVE)
        assert out["success"] is False and "2 个子任务" in out["summary"]

    def test_competitive_no_capable_agent(self, scripted_complete):
        complete = scripted_complete(decompose=_decompose([{"type": "general", "description": "g"}]))
        m = _master(complete, [SlowAgent("c", ["code_generation"])])
        out = m.coordinate_task("r", CollaborationMode.COMPETITIVE)
        assert out["success"] is False and "没有能胜任" in out["summary"]

    def test_competitive_agent_exception(self, scripted_complete):
        complete = scripted_complete(decompose=_decompose([{"type": "general", "description": "g"}]))

        class Raising(SlowAgent):
            def execute_task_with_timeout(self, task, timeout=None):
                raise RuntimeError("crash")
        m = _master(complete, [Raising("x", ["general"]), SlowAgent("y", ["general"])])
        out = m.coordinate_task("r", CollaborationMode.COMPETITIVE)
        assert out["best_result"]["agent_id"] == "y"
        failed = [r for r in out["all_results"] if not r["success"]][0]
        assert "crash" in failed["error_message"]


class TestProgressWording:
    def test_llm_decompose_wording(self, scripted_complete):
        complete = scripted_complete(decompose=_decompose([{"type": "general", "description": "g"}]))
        events = []
        m = _master(complete, [SlowAgent("g", ["general"])])
        m.coordinate_task("r", CollaborationMode.HIERARCHY, progress=events.append)
        msgs = [e["message"] for e in events]
        assert msgs[0] == "🧩 分解任务（模型推理）..."
        decomposed = [e for e in events if e["stage"] == "decomposed"][0]
        assert "模型推理" in decomposed["message"] and decomposed["method"] == "llm"
        assert decomposed["subtasks"] == [{"type": "general", "description": "g"}]
        assert not any("规则回退" in m_ for m_ in msgs)

    def test_rules_fallback_wording(self, scripted_complete):
        complete = scripted_complete(decompose="garbage")
        events = []
        m = _master(complete, [SlowAgent("c", ["code_generation"])])
        m.coordinate_task("实现代码", CollaborationMode.HIERARCHY, progress=events.append)
        msgs = [e["message"] for e in events if e["stage"] == "decompose"]
        assert msgs == ["🧩 分解任务（模型推理）...", "🧩 分解任务（规则回退）..."]
        decomposed = [e for e in events if e["stage"] == "decomposed"][0]
        assert "规则回退" in decomposed["message"]

    def test_use_llm_false_wording(self):
        m = MasterAgent(config={"use_llm": False})
        m.set_specialized_agents([SlowAgent("c", ["code_generation"])])
        events = []
        m.coordinate_task("实现代码", CollaborationMode.HIERARCHY, progress=events.append)
        msgs = [e["message"] for e in events if e["stage"] == "decompose"]
        assert msgs == ["🧩 分解任务（规则匹配）..."]
        integrate = [e for e in events if e["stage"] == "integrate"][0]
        assert "模型综合" not in integrate["message"]

    def test_integrate_wording_with_llm_and_multiple(self, scripted_complete):
        complete = scripted_complete(decompose=_decompose([
            {"type": "code_generation", "description": "a"}, {"type": "testing", "description": "b"}]))
        events = []
        m = _master(complete, [SlowAgent("c", ["code_generation"]), SlowAgent("t", ["testing"])])
        m.coordinate_task("r", CollaborationMode.HIERARCHY, progress=events.append)
        integrate = [e for e in events if e["stage"] == "integrate"][0]
        assert "模型综合" in integrate["message"]

    def test_agent_steps_forwarded_and_context_injected(self, scripted_complete, fake_engine_factory):
        complete = scripted_complete(decompose=_decompose([{"type": "code_generation", "description": "a"}]))
        code = CodeAgent(config={"engine_factory": fake_engine_factory()})
        rag = RAGAgent()
        m = _master(complete, [code, rag])
        events = []
        m.coordinate_task("r", CollaborationMode.HIERARCHY, progress=events.append, context="CTX")
        steps = [e for e in events if e["stage"] == "agent_step"]
        assert steps and steps[0]["agent_id"] == "code_agent_1"
        # 执行期间注入，结束后清理
        assert code.on_progress is None and rag.conversation_context is None

    def test_no_subtasks(self):
        class EmptyDecomposer:
            use_llm = False
            last_method = "rules"

            def decompose(self, request, agents):
                return []
        m = MasterAgent(config={"use_llm": False})
        m.task_decomposer = EmptyDecomposer()
        out = m.coordinate_task("r", CollaborationMode.HIERARCHY)
        assert out["success"] is False and out["error"] == "No subtasks generated"

    def test_exception_in_flow(self):
        class BadDecomposer:
            use_llm = False

            def decompose(self, request, agents):
                raise RuntimeError("bad")
        m = MasterAgent(config={"use_llm": False})
        m.task_decomposer = BadDecomposer()
        out = m.coordinate_task("r", CollaborationMode.HIERARCHY)
        assert out["success"] is False and out["error"] == "bad"


class TestOrchestratorConfigPassthrough:
    def test_agent_config_fields_reach_instances(self):
        from agent_config import AgentConfigManager, CODE_AGENT_TOOLS
        from agent_orchestrator import AgentOrchestrator
        cfg = AgentConfigManager.get_default_config()
        for a in cfg.agent_configs:
            a.model = "m-x"
            a.timeout = 42
            a.max_iterations = 9
        orch = AgentOrchestrator(cfg)
        code = orch.get_agent("code_agent_1")
        assert code.config["model"] == "m-x"
        assert code.config["timeout"] == 42
        assert code.config["max_iterations"] == 9
        assert set(code.config["allowed_tools"]) == set(CODE_AGENT_TOOLS)
        assert code.allowed_tools() == set(CODE_AGENT_TOOLS)
        orch.shutdown()

    def test_specialized_tools_are_real_tool_names(self):
        from agent_config import AgentConfigManager
        from agent_tools import registry
        cfg = AgentConfigManager.get_default_config()
        for a in cfg.agent_configs:
            for tool in a.specialized_tools:
                assert tool in registry.tools, (a.agent_id, tool)

    def test_process_request_passes_context(self, monkeypatch):
        from agent_config import AgentConfigManager
        from agent_orchestrator import AgentOrchestrator
        orch = AgentOrchestrator(AgentConfigManager.get_minimal_config())
        seen = {}

        def fake(request, mode, **kw):
            seen.update(kw)
            return {"success": True}
        monkeypatch.setattr(orch.master_agent, "coordinate_task", fake)
        orch.process_request("r", context="CTX")
        assert seen == {"context": "CTX"}
        orch.shutdown()
