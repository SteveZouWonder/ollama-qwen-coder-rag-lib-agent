"""F10 P2-1-c/d：注册中心与调度器的锁、LLM 并发信号量、子任务超时剔除排队时间。"""
from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import List
from unittest.mock import MagicMock

import pytest
import requests

import llm_client
from agent_registry import AgentRegistry
from agents.agent_types import AgentResult, AgentState, AgentTask, AgentType, CollaborationMode
from agents.base_agent import BaseAgent, ReActDelegateAgent
from collaboration.task_scheduler import TaskScheduler
from master_agent import MasterAgent


class Dummy(BaseAgent):
    def __init__(self, agent_id, caps, agent_type=AgentType.CODE):
        super().__init__(agent_id=agent_id, agent_type=agent_type, capabilities=caps)

    def process_task(self, task):
        return AgentResult(task_id=task.task_id, agent_id=self.agent_id, success=True,
                           output="ok", metadata={}, execution_time=0)


def _run_threads(n, fn):
    errors: List[BaseException] = []
    barrier = threading.Barrier(n)

    def wrapped(i):
        try:
            barrier.wait(timeout=5)
            fn(i)
        except BaseException as e:  # noqa: BLE001
            errors.append(e)

    threads = [threading.Thread(target=wrapped, args=(i,)) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)
    assert not errors, errors
    assert not any(t.is_alive() for t in threads)


class TestRegistryLock:
    def test_lock_is_rlock_and_reentrant(self):
        reg = AgentRegistry()
        assert isinstance(reg.lock, type(threading.RLock()))
        with reg.lock:
            with reg.lock:  # 可重入
                assert reg.register(Dummy("a", ["x"])) is True
        assert "a" in reg

    def test_16_threads_register_distinct_agents(self):
        reg = AgentRegistry()
        types = [AgentType.CODE, AgentType.TEST, AgentType.DOC]

        def work(i):
            a = Dummy(f"agent-{i}", [f"cap-{i}", "shared"], agent_type=types[i % 3])
            assert reg.register(a) is True
            # 注册同时读：不得抛 RuntimeError（字典大小变化）
            reg.get_all_agents(); reg.find_agents_by_capability("shared"); reg.get_statistics(); list(reg)

        _run_threads(16, work)
        assert len(reg) == 16 and reg.get_agent_count() == 16
        assert len(reg.find_agents_by_capability("shared")) == 16
        assert sum(len(v) for v in reg.type_index.values()) == 16
        assert sorted(reg.get_all_capabilities()) == sorted([f"cap-{i}" for i in range(16)] + ["shared"])
        stats = reg.get_statistics()
        assert stats["total_agents"] == 16 and stats["capabilities_index"]["shared"] == 16
        assert sum(stats["agents_by_type"].values()) == 16

    def test_16_threads_register_same_id_only_one_wins(self):
        reg = AgentRegistry()
        wins = []
        lock = threading.Lock()

        def work(i):
            ok = reg.register(Dummy("dup", ["x"]))
            with lock:
                wins.append(ok)

        _run_threads(16, work)
        assert wins.count(True) == 1 and len(reg) == 1
        assert reg.capabilities_index["x"] == ["dup"]

    def test_16_threads_unregister_and_clear(self):
        reg = AgentRegistry()
        for i in range(16):
            reg.register(Dummy(f"a{i}", ["x", f"c{i}"]))

        def work(i):
            assert reg.unregister(f"a{i}") is True
            assert reg.unregister(f"a{i}") is False

        _run_threads(16, work)
        assert len(reg) == 0 and reg.capabilities_index == {} and reg.type_index == {}
        reg.register(Dummy("z", ["x"]))
        reg.clear()
        assert len(reg) == 0

    def test_iter_and_state_queries_take_snapshot(self):
        reg = AgentRegistry()
        for i in range(4):
            reg.register(Dummy(f"a{i}", ["x"]))
        it = iter(reg)
        reg.unregister("a0")  # 迭代中修改不抛
        assert len(list(it)) == 4
        assert len(reg.find_agents_by_state(AgentState.IDLE)) == 3
        assert len(reg.find_available_agents(["x"])) == 3
        assert reg.find_agents_by_type(AgentType.CODE)[0].agent_id == "a1"
        reg.shutdown_all()


class TestSchedulerLock:
    def test_lock_is_rlock(self):
        s = TaskScheduler()
        assert isinstance(s.lock, type(threading.RLock()))

    def _task(self, i):
        return AgentTask(task_id=f"t{i}", task_type="x", description="d", required_capabilities=["x"], input_data={})

    def test_16_threads_schedule_and_mark_complete(self):
        s = TaskScheduler(max_parallel_tasks=32)
        agents = [Dummy(f"a{i}", ["x"]) for i in range(4)]

        def work(i):
            task = self._task(i)
            assigned = s.schedule_parallel([task], agents)
            assert task.task_id in assigned
            assert s.get_task_status(task.task_id) == "scheduled"
            s.mark_task_running(task.task_id)
            assert s.get_task_status(task.task_id) == "running"
            s.get_statistics()
            res = AgentResult(task_id=task.task_id, agent_id="a0", success=True, output="", metadata={}, execution_time=0)
            s.mark_task_completed(task.task_id, res)

        _run_threads(16, work)
        stats = s.get_statistics()
        assert stats == {"scheduled": 0, "running": 0, "completed": 16, "total": 16}
        assert all(s.get_task_status(f"t{i}") == "completed" for i in range(16))

    def test_16_threads_greedy_schedule_and_fail_path(self):
        s = TaskScheduler(max_parallel_tasks=32)
        agents = [Dummy("a", ["x"])]

        def work(i):
            task = self._task(i)
            assert s.schedule([task], agents) == {task.task_id: agents[0]}
            s.mark_task_running(task.task_id)
            s.mark_task_failed(task.task_id, "boom")
            s.mark_task_running("missing")  # 不存在：静默

        _run_threads(16, work)
        assert s.get_statistics()["total"] == 0
        assert s.get_task_status("t0") == "unknown"
        # sequential / competitive 同样在锁内登记
        seq = [self._task(100), self._task(101)]
        seq[1].dependencies = ["t100"]
        steps = s.schedule_sequential(seq, agents)
        assert [list(st)[0] for st in steps] == ["t100", "t101"]
        assert s.schedule_competitive(self._task(200), agents) == agents
        assert s.get_statistics()["scheduled"] == 3
        s.reset()
        assert s.get_statistics()["total"] == 0


# ---------------------------------------------------------------------------
# P2-1-d：LLM 并发信号量
# ---------------------------------------------------------------------------

@pytest.fixture
def slow_ollama(monkeypatch):
    """替换 requests.post：每次调用睡 ``delay`` 秒并返回一条 Ollama chat 响应，记录并发峰值。"""
    state = {"running": 0, "peak": 0, "calls": 0, "delay": 0.3}
    lock = threading.Lock()

    def fake_post(url, json=None, timeout=None, **kwargs):
        with lock:
            state["running"] += 1
            state["calls"] += 1
            state["peak"] = max(state["peak"], state["running"])
        try:
            time.sleep(state["delay"])
        finally:
            with lock:
                state["running"] -= 1
        resp = MagicMock()
        resp.status_code = 200
        resp.ok = True
        resp.json.return_value = {"message": {"content": "Final Answer: 完成"}}
        resp.text = "{}"
        return resp

    monkeypatch.setattr(requests, "post", fake_post)
    monkeypatch.setattr(llm_client.requests, "post", fake_post)
    return state


@pytest.fixture(autouse=True)
def _reset_concurrency():
    llm_client.set_max_concurrency(None)
    llm_client.set_queue_listener(None)
    yield
    llm_client.set_max_concurrency(None)
    llm_client.set_queue_listener(None)


class TestFairSemaphore:
    def test_fifo_order(self):
        sem = llm_client.FairSemaphore(1)
        assert sem.acquire() is True
        order = []
        started = threading.Barrier(4)
        ready = []

        def waiter(i):
            started.wait(timeout=5)
            time.sleep(0.02 * i)  # 错开到达顺序
            ready.append(i)
            with sem:
                order.append(i)
                time.sleep(0.02)

        threads = [threading.Thread(target=waiter, args=(i,)) for i in range(3)]
        for t in threads:
            t.start()
        started.wait(timeout=5)
        time.sleep(0.2)  # 三个都已排队
        assert sem.acquire(blocking=False) is False
        sem.release()
        for t in threads:
            t.join(timeout=5)
        assert order == ready == [0, 1, 2]

    def test_non_blocking_and_over_release(self):
        sem = llm_client.FairSemaphore(2)
        assert sem.acquire(blocking=False) and sem.acquire(blocking=False)
        assert sem.acquire(blocking=False) is False
        sem.release(); sem.release()
        with pytest.raises(ValueError):
            sem.release()
        with pytest.raises(ValueError):
            llm_client.FairSemaphore(0)

    def test_waiter_interrupted_is_removed(self):
        """等待中抛异常（如被 KeyboardInterrupt）时票据出队，后来者不被卡死。"""
        sem = llm_client.FairSemaphore(1)
        sem.acquire()
        cond = sem._cond
        orig_wait = cond.wait

        def boom(*a, **k):
            raise RuntimeError("interrupted")

        cond.wait = boom
        with pytest.raises(RuntimeError):
            sem.acquire()
        cond.wait = orig_wait
        assert not sem._waiters
        sem.release()
        assert sem.acquire(blocking=False) is True


class TestLLMSlot:
    def test_default_limit_from_config(self, monkeypatch):
        from config import Config
        monkeypatch.setattr(Config, "OLLAMA_MAX_CONCURRENCY", 3)
        assert llm_client.max_concurrency() == 3
        assert llm_client.slot_stats() == {"limit": 3, "in_flight": 0, "queued": 0}
        assert llm_client.describe_backend()["max_concurrency"] == 3
        llm_client.set_max_concurrency(7)
        assert llm_client.max_concurrency() == 7
        llm_client.set_max_concurrency(None)
        assert llm_client.max_concurrency() == 3

    def test_semaphore_limits_in_flight_requests(self, slow_ollama):
        llm_client.set_max_concurrency(1)
        client = llm_client.OllamaClient("http://x")
        slow_ollama["delay"] = 0.2
        start = time.time()
        with ThreadPoolExecutor(max_workers=3) as pool:
            outs = list(pool.map(lambda _: client.chat([{"role": "user", "content": "hi"}]), range(3)))
        elapsed = time.time() - start
        assert outs == ["Final Answer: 完成"] * 3
        assert slow_ollama["peak"] == 1 and elapsed >= 0.55
        assert llm_client.slot_stats()["in_flight"] == 0 and llm_client.slot_stats()["queued"] == 0

    def test_limit_two_allows_two_in_flight(self, slow_ollama):
        llm_client.set_max_concurrency(2)
        client = llm_client.OllamaClient("http://x")
        slow_ollama["delay"] = 0.2
        start = time.time()
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(lambda _: client.chat([{"role": "user", "content": "hi"}]), range(4)))
        assert slow_ollama["peak"] == 2 and 0.35 <= time.time() - start < 0.8

    def test_zero_means_unlimited(self, slow_ollama):
        llm_client.set_max_concurrency(0)
        client = llm_client.OllamaClient("http://x")
        slow_ollama["delay"] = 0.15
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(lambda _: client.chat([{"role": "user", "content": "hi"}]), range(4)))
        assert slow_ollama["peak"] == 4
        assert llm_client.slot_stats()["limit"] == 0

    def test_slot_released_on_error(self, monkeypatch):
        llm_client.set_max_concurrency(1)

        def boom(*a, **k):
            raise requests.exceptions.ConnectionError("down")

        monkeypatch.setattr(llm_client.requests, "post", boom)
        client = llm_client.OllamaClient("http://x")
        for _ in range(3):  # 槽位若泄漏第二次就会永久阻塞
            with pytest.raises(requests.exceptions.ConnectionError):
                client.chat([{"role": "user", "content": "hi"}])
        assert llm_client.slot_stats()["in_flight"] == 0
        with llm_client.llm_slot():
            assert llm_client.slot_stats()["in_flight"] == 1
        assert llm_client.slot_stats()["in_flight"] == 0

    def test_openai_client_shares_semaphore(self, monkeypatch):
        llm_client.set_max_concurrency(1)
        peak = {"running": 0, "peak": 0}
        lock = threading.Lock()

        def fake_post(url, json=None, headers=None, timeout=None, **kwargs):
            with lock:
                peak["running"] += 1
                peak["peak"] = max(peak["peak"], peak["running"])
            time.sleep(0.15)
            with lock:
                peak["running"] -= 1
            resp = MagicMock()
            resp.status_code = 200
            resp.ok = True
            if "chat/completions" in url:
                resp.json.return_value = {"choices": [{"message": {"content": "ok"}}]}
            else:
                resp.json.return_value = {"message": {"content": "ok"}}
            return resp

        monkeypatch.setattr(llm_client.requests, "post", fake_post)
        oa = llm_client.OpenAICompatClient("http://x", api_key="k")
        ol = llm_client.OllamaClient("http://x")
        with ThreadPoolExecutor(max_workers=2) as pool:
            f1 = pool.submit(oa.chat, [{"role": "user", "content": "a"}], think=True)
            f2 = pool.submit(ol.chat, [{"role": "user", "content": "b"}])
            assert f1.result() == "ok" and f2.result() == "ok"
        assert peak["peak"] == 1

    def test_queue_tracker_records_wait_and_notifies(self, slow_ollama):
        llm_client.set_max_concurrency(1)
        client = llm_client.OllamaClient("http://x")
        slow_ollama["delay"] = 0.3
        events = []
        tracker = llm_client.QueueWaitTracker(on_change=lambda w, t: events.append((w, round(t, 3))))

        def holder():
            client.chat([{"role": "user", "content": "long"}])

        def waiter():
            llm_client.set_queue_listener(tracker)
            try:
                client.chat([{"role": "user", "content": "queued"}])
            finally:
                llm_client.set_queue_listener(None)

        t1 = threading.Thread(target=holder)
        t1.start()
        time.sleep(0.05)
        t2 = threading.Thread(target=waiter)
        t2.start()
        time.sleep(0.1)
        assert tracker.waiting is True and tracker.total() >= 0.05  # 进行中的等待实时可见
        assert llm_client.slot_stats()["queued"] == 1
        t1.join(); t2.join()
        assert tracker.waiting is False and tracker.queue_count == 1
        assert 0.15 <= tracker.waited <= 0.6 and abs(tracker.total() - tracker.waited) < 1e-6
        assert events[0][0] is True and events[-1][0] is False and events[-1][1] == round(tracker.waited, 3)

    def test_tracker_callback_errors_are_swallowed(self):
        def bad(w, t):
            raise RuntimeError("x")

        tr = llm_client.QueueWaitTracker(on_change=bad)
        tr.on_queue_start(); tr.on_queue_end()
        tr.on_queue_end()  # 未在等待时调用：无副作用
        assert tr.queue_count == 1 and tr.waited >= 0


# ---------------------------------------------------------------------------
# P2-1-d：子任务超时从获得信号量后计时 + "排队中"进度
# ---------------------------------------------------------------------------

class LLMAgent(ReActDelegateAgent):
    """子 Agent：每个任务经 llm_client 发一次（慢）请求。"""
    ROLE_PROMPT = "x"
    ALLOWED_TOOLS = ("read_file",)
    ESSENTIAL_TOOLS = ()
    TASK_TYPE_HINTS = {}

    def __init__(self, agent_id, caps):
        super().__init__(agent_id=agent_id, agent_type=AgentType.CODE, capabilities=caps,
                         config={"engine_factory": self._factory, "prompt_mode": "builtin"})

    @staticmethod
    def _factory(**kwargs):
        eng = MagicMock()
        eng.step_log = []

        def chat(prompt):
            return llm_client.OllamaClient("http://x").chat([{"role": "user", "content": prompt}])

        eng.chat.side_effect = chat
        return eng


def _decompose(items):
    import json
    return json.dumps({"subtasks": items}, ensure_ascii=False)


class TestSerialSubAgentsNoTimeout:
    def test_three_parallel_subagents_with_semaphore_one_finish_serially_without_timeout(
            self, slow_ollama, scripted_complete):
        llm_client.set_max_concurrency(1)
        slow_ollama["delay"] = 0.3
        complete = scripted_complete(decompose=_decompose([
            {"type": "code_generation", "description": "a"},
            {"type": "testing", "description": "b"},
            {"type": "documentation", "description": "c"},
        ]))
        agents = [LLMAgent("c", ["code_generation"]), LLMAgent("t", ["testing"]), LLMAgent("d", ["documentation"])]
        for a in agents:
            a.config["timeout"] = 0.5  # 小于串行总耗时 0.9s：不剔除排队时间就会超时
        m = MasterAgent(config={"llm_complete": complete, "max_parallel_tasks": 5})
        m.set_specialized_agents(agents)
        events = []
        start = time.time()
        out = m.coordinate_task("r", CollaborationMode.PARALLEL, progress=events.append)
        elapsed = time.time() - start
        assert out["success"] is True, out
        assert all(r["success"] for r in out["results"])
        assert not any(r.get("error_message") == "timeout" for r in out["results"])
        assert slow_ollama["peak"] == 1 and slow_ollama["calls"] == 3
        assert elapsed >= 0.85  # 串行完成
        queued = [e for e in events if e.get("phase") == "queued"]
        assert queued and any("排队等待模型空闲" in e["message"] and "并发上限 1" in e["message"] for e in queued)
        assert queued[0].get("transient") is None  # 首次排队追加一行
        done = [e for e in events if e.get("phase") == "queued_done"]
        assert done and all(e.get("transient") for e in done)
        # 排队时间写入 metadata；至少两个子任务排过队
        queued_secs = [r["metadata"].get("queued_seconds", 0) for r in out["results"]]
        assert sum(1 for q in queued_secs if q and q > 0) >= 2

    def test_timeout_still_fires_for_real_slowness(self, slow_ollama):
        """排队时间剔除后，真正的执行时间仍受超时约束。"""
        llm_client.set_max_concurrency(1)
        slow_ollama["delay"] = 0.6
        agent = LLMAgent("c", ["code_generation"])
        agent.config["timeout"] = 0.2
        task = AgentTask(task_id="t", task_type="code_generation", description="d",
                         required_capabilities=["code_generation"], input_data={})
        start = time.time()
        r = agent.execute_task_with_timeout(task)
        assert r.error_message == "timeout" and time.time() - start < 0.55
        assert "queued_seconds" not in r.metadata  # 没排队
        assert agent.get_state() == AgentState.IDLE

    def test_queued_time_excluded_from_timeout_single_agent(self, slow_ollama):
        llm_client.set_max_concurrency(1)
        slow_ollama["delay"] = 0.4
        agent = LLMAgent("c", ["code_generation"])
        agent.config["timeout"] = 0.6
        task = AgentTask(task_id="t", task_type="code_generation", description="d",
                         required_capabilities=["code_generation"], input_data={})
        # 先用另一线程占住唯一槽位 0.4s
        blocker = threading.Thread(target=lambda: llm_client.OllamaClient("http://x").chat([{"role": "user", "content": "x"}]))
        blocker.start()
        time.sleep(0.05)
        events = []
        agent.on_progress = events.append
        r = agent.execute_task_with_timeout(task)
        blocker.join()
        assert r.success is True, r.error_message
        assert r.metadata["queued_seconds"] >= 0.2
        assert any(e.get("phase") == "queued" for e in events)

    def test_second_queue_event_is_transient(self, slow_ollama):
        """同一任务多次排队：只有第一次追加进度行，之后只刷新状态。"""
        llm_client.set_max_concurrency(1)
        slow_ollama["delay"] = 0.15

        class TwoCalls(LLMAgent):
            @staticmethod
            def _factory(**kwargs):
                eng = MagicMock()
                eng.step_log = []

                def chat(prompt):
                    c = llm_client.OllamaClient("http://x")
                    c.chat([{"role": "user", "content": "1"}])
                    return c.chat([{"role": "user", "content": "2"}])

                eng.chat.side_effect = chat
                return eng

        agent = TwoCalls("c", ["code_generation"])
        stop = threading.Event()

        def hog():
            c = llm_client.OllamaClient("http://x")
            while not stop.is_set():
                c.chat([{"role": "user", "content": "hog"}])

        t = threading.Thread(target=hog, daemon=True)
        t.start()
        time.sleep(0.03)
        events = []
        agent.on_progress = events.append
        task = AgentTask(task_id="t", task_type="code_generation", description="d",
                         required_capabilities=["code_generation"], input_data={}, timeout=5)
        r = agent.execute_task_with_timeout(task)
        stop.set()
        t.join(timeout=2)
        assert r.success is True
        queued = [e for e in events if e.get("phase") == "queued"]
        if len(queued) >= 2:
            assert queued[0].get("transient") is None and all(e.get("transient") for e in queued[1:])

    def test_without_llm_client_tracker_falls_back_to_plain_join(self, monkeypatch):
        agent = Dummy("a", ["x"])
        monkeypatch.setattr(BaseAgent, "_make_queue_tracker", lambda self: None)
        task = AgentTask(task_id="t", task_type="x", description="d", required_capabilities=["x"], input_data={}, timeout=1)
        r = agent.execute_task_with_timeout(task)
        assert r.success is True and "queued_seconds" not in r.metadata
        task2 = AgentTask(task_id="t2", task_type="x", description="d", required_capabilities=["x"], input_data={}, timeout=0)
        assert agent.execute_task_with_timeout(task2).success is True  # timeout 0 → 无限等待路径
