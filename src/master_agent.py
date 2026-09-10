"""
MasterAgent - 主控Agent，负责任务分解和协调
"""
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable, Dict, List, Optional
import threading
import time
from agents import BaseAgent
from agents.agent_types import AgentTask, AgentResult, AgentType, CollaborationMode
from collaboration import TaskDecomposer
from collaboration.task_scheduler import TaskScheduler
from collaboration import ResultIntegrator


class MasterAgent(BaseAgent):
    """主控Agent，负责任务分解、调度和结果整合"""
    
    def __init__(self, agent_id: str = "master_agent", config: Dict[str, Any] = None):
        """
        初始化MasterAgent
        
        Args:
            agent_id: Agent ID
            config: 配置字典
        """
        capabilities = [
            "task_decomposition",
            "task_scheduling",
            "result_integration",
            "coordination"
        ]
        
        super().__init__(
            agent_id=agent_id,
            agent_type=AgentType.MASTER,
            capabilities=capabilities,
            config=config or {}
        )
        
        # 初始化组件（config 可注入 use_llm / llm_complete，便于测试与离线运行）
        cfg = config or {}
        use_llm = bool(cfg.get("use_llm", True))
        complete = cfg.get("llm_complete")
        self.task_decomposer = TaskDecomposer(complete=complete, use_llm=use_llm)
        self.task_scheduler = TaskScheduler(
            max_parallel_tasks=cfg.get("max_parallel_tasks", 5)
        )
        self.result_integrator = ResultIntegrator(complete=complete, use_llm=use_llm)
        
        # 存储专业Agent的引用
        self.specialized_agents: List[BaseAgent] = []
    
    def set_specialized_agents(self, agents: List[BaseAgent]):
        """设置专业Agent列表"""
        self.specialized_agents = agents
        self.logger.info(f"Set {len(agents)} specialized agents")
    
    def process_task(self, task: AgentTask) -> AgentResult:
        """
        处理任务（MasterAgent主要负责协调，不直接处理业务任务）
        
        Args:
            task: 任务对象
            
        Returns:
            AgentResult: 执行结果
        """
        start_time = time.time()
        
        try:
            # MasterAgent主要处理协调任务
            if task.task_type == "coordination":
                result = self._handle_coordination(task)
            else:
                # 其他类型的任务，返回说明信息
                result = AgentResult(
                    task_id=task.task_id,
                    agent_id=self.agent_id,
                    success=True,
                    output="MasterAgent主要负责任务协调，不处理业务任务。",
                    metadata={"role": "coordinator"},
                    execution_time=0
                )
            
            execution_time = time.time() - start_time
            result.execution_time = execution_time
            result.task_id = task.task_id
            result.agent_id = self.agent_id
            
            return result
            
        except Exception as e:
            execution_time = time.time() - start_time
            self.logger.error(f"Error processing task: {e}")
            
            return AgentResult(
                task_id=task.task_id,
                agent_id=self.agent_id,
                success=False,
                output="",
                metadata={},
                execution_time=execution_time,
                error_message=str(e)
            )
    
    @staticmethod
    def _emit(progress: Optional[Callable[[Dict[str, Any]], None]],
              stage: str, message: str, **extra: Any) -> None:
        """安全地发出一条协作进度事件；回调为空或抛错都不影响主流程。"""
        if progress is None:
            return
        try:
            event = {"stage": stage, "message": message}
            event.update(extra)
            progress(event)
        except Exception:  # noqa: BLE001 - 进度回调失败不应中断协作
            pass

    def coordinate_task(
        self,
        request: str,
        mode: CollaborationMode,
        progress: Optional[Callable[[Dict[str, Any]], None]] = None,
        context=None,
        on_token: Optional[Callable[[str], None]] = None,
    ) -> Dict[str, Any]:
        """
        协调任务的完整流程
        
        Args:
            request: 用户请求
            mode: 协作模式
            progress: 可选进度回调，接收 ``{"stage", "message", ...}``。
                stage 取值：``decompose`` | ``decomposed`` | ``schedule`` |
                ``execute`` | ``agent_step`` | ``task_done`` | ``integrate``。
                用于 CLI/Web 实时展示"分解 → 调度 → 执行 → 整合"各阶段。
            context: 可选会话上下文，注入给 RAGAgent 用于追问改写/历史注入。
            on_token: 整合阶段（模型综合最终回答）的增量回调（F10 P1-1）；子任务执行
                不流式。
            
        Returns:
            Dict[str, Any]: 协调结果
        """
        self.logger.info(f"Coordinating task with mode: {mode}")
        emit = lambda stage, msg, **kw: self._emit(progress, stage, msg, **kw)  # noqa: E731

        # 把进度回调与会话上下文注入到各专业 Agent
        def agent_progress(evt: Dict[str, Any]) -> None:
            self._emit(progress, evt.get("stage", "agent_step"), evt.get("message", ""),
                       **{k: v for k, v in evt.items() if k not in ("stage", "message")})

        for agent in self.specialized_agents:
            agent.on_progress = agent_progress if progress is not None else None
            agent.conversation_context = context
        # 整合阶段的流式回调只在本次协作期间生效
        if hasattr(self.result_integrator, "on_token"):
            self.result_integrator.on_token = on_token
        
        try:
            # 1. 任务分解
            llm_first = bool(getattr(self.task_decomposer, "use_llm", False))
            emit("decompose", "🧩 分解任务（模型推理）..." if llm_first else "🧩 分解任务（规则匹配）...")
            subtasks = self.task_decomposer.decompose(request, self.specialized_agents)
            method = getattr(self.task_decomposer, "last_method", "rules")
            if llm_first and method != "llm":
                emit("decompose", "🧩 分解任务（规则回退）...", method=method)
            
            if not subtasks:
                return {
                    "success": False,
                    "error": "No subtasks generated",
                    "summary": "Failed to decompose task"
                }
            
            self.logger.info(f"Decomposed into {len(subtasks)} subtasks")
            method_label = "模型推理" if method == "llm" else "规则回退"
            emit("decomposed",
                 f"✅ 已分解为 {len(subtasks)} 个子任务（{method_label}）："
                 + "；".join(t.description[:40] for t in subtasks),
                 count=len(subtasks), method=method,
                 subtasks=[{"type": t.task_type, "description": t.description} for t in subtasks])
            
            # 2. 调度 + 3. 执行
            emit("schedule", "📋 调度子任务到专业 Agent...")
            if mode == CollaborationMode.COMPETITIVE:
                return self._run_competitive(request, subtasks, progress)

            if mode == CollaborationMode.PARALLEL:
                task_assignments = self.task_scheduler.schedule_parallel(
                    subtasks, self.specialized_agents)
                results = self._execute_parallel(subtasks, task_assignments, progress)
            elif mode == CollaborationMode.SEQUENTIAL:
                schedule_steps = self.task_scheduler.schedule_sequential(
                    subtasks, self.specialized_agents)
                task_assignments = {}
                for step in schedule_steps:
                    task_assignments.update(step)
                results = self._execute_sequential(subtasks, task_assignments, progress)
            else:  # HIERARCHY or default
                task_assignments = self.task_scheduler.schedule(
                    subtasks, self.specialized_agents)
                results = self._execute_sequential(subtasks, task_assignments, progress)

            unassigned = [t for t in subtasks if t.task_id not in task_assignments]
            for t in unassigned:
                results.append(AgentResult(
                    task_id=t.task_id, agent_id="(未分配)", success=False, output="",
                    metadata={"task_type": t.task_type}, execution_time=0,
                    error_message=f"没有具备能力 {t.required_capabilities} 的 Agent",
                ))
            
            # 4. 整合结果
            emit("integrate", "🧷 整合各 Agent 结果（模型综合）..."
                 if getattr(self.result_integrator, "use_llm", False) and len(results) > 1
                 else "🧷 整合各 Agent 结果...")
            if mode == CollaborationMode.PARALLEL:
                integrated_result = self.result_integrator.integrate_parallel(
                    results, subtasks, request=request)
            elif mode == CollaborationMode.SEQUENTIAL:
                integrated_result = self.result_integrator.integrate_sequential(
                    results, subtasks, request=request)
            else:
                integrated_result = self.result_integrator.integrate(
                    results, subtasks, request=request)
            integrated_result.setdefault("mode", mode.value)
            integrated_result["decompose_method"] = method
            return integrated_result
            
        except Exception as e:
            self.logger.error(f"Coordination failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "summary": "Task coordination failed"
            }
        finally:
            for agent in self.specialized_agents:
                agent.on_progress = None
                agent.conversation_context = None
            if hasattr(self.result_integrator, "on_token"):
                self.result_integrator.on_token = None

    # ---------- 执行策略 ----------

    @staticmethod
    def _dependency_order(subtasks: List[AgentTask], assigned: Dict[str, BaseAgent]) -> List[AgentTask]:
        """按依赖拓扑排序（保持原有先后作为次序），只保留已分配的任务。"""
        by_id = {t.task_id: t for t in subtasks if t.task_id in assigned}
        ordered: List[AgentTask] = []
        done = set()
        remaining = list(by_id.values())
        while remaining:
            progressed = False
            for t in list(remaining):
                deps = [d for d in t.dependencies if d in by_id]
                if all(d in done for d in deps):
                    ordered.append(t)
                    done.add(t.task_id)
                    remaining.remove(t)
                    progressed = True
            if not progressed:  # 循环依赖：剩余任务按原顺序追加
                ordered.extend(remaining)
                break
        return ordered

    @staticmethod
    def _attach_upstream(task: AgentTask, subtasks: List[AgentTask],
                         done: Dict[str, AgentResult]) -> None:
        """把依赖子任务的输出以 ``input_data["upstream"]`` 传给下游。"""
        desc = {t.task_id: t.description for t in subtasks}
        upstream = []
        for dep in task.dependencies:
            r = done.get(dep)
            if r is not None and r.success:
                upstream.append({"description": desc.get(dep, ""), "output": (r.output or "")[:1500]})
        if upstream:
            task.input_data["upstream"] = upstream

    def _run_one(self, task: AgentTask, agent: BaseAgent) -> AgentResult:
        self.task_scheduler.mark_task_running(task.task_id)
        try:
            result = agent.execute_task_with_timeout(task)
        except Exception as e:  # noqa: BLE001
            self.logger.error(f"Task execution failed: {e}")
            result = AgentResult(
                task_id=task.task_id, agent_id=agent.agent_id, success=False,
                output="", metadata={}, execution_time=0, error_message=str(e),
            )
        if result.success:
            self.task_scheduler.mark_task_completed(task.task_id, result)
        else:
            self.task_scheduler.mark_task_failed(task.task_id, result.error_message)
        return result

    def _execute_sequential(self, subtasks: List[AgentTask], assigned: Dict[str, BaseAgent],
                            progress) -> List[AgentResult]:
        """按依赖顺序逐个执行，下游任务可见上游输出。"""
        ordered = self._dependency_order(subtasks, assigned)
        total = len(ordered)
        results: List[AgentResult] = []
        done: Dict[str, AgentResult] = {}
        for idx, task in enumerate(ordered, 1):
            agent = assigned[task.task_id]
            self._attach_upstream(task, subtasks, done)
            self._emit(progress, "execute",
                       f"⚙️ 执行子任务 {idx}/{total}：{agent.agent_id} — {task.description[:60]}",
                       current=idx, total=total, agent_id=agent.agent_id)
            result = self._run_one(task, agent)
            results.append(result)
            done[task.task_id] = result
            self._emit_task_done(progress, idx, total, result)
        return results

    def _execute_parallel(self, subtasks: List[AgentTask], assigned: Dict[str, BaseAgent],
                          progress) -> List[AgentResult]:
        """真正并行：无依赖的子任务同一波内用线程池并发，依赖满足后进入下一波。"""
        ordered = self._dependency_order(subtasks, assigned)
        total = len(ordered)
        max_workers = max(1, int(getattr(self.task_scheduler, "max_parallel_tasks", 5) or 1))
        results_by_id: Dict[str, AgentResult] = {}
        pending = list(ordered)
        counter = {"n": 0}
        lock = threading.Lock()

        def run(task: AgentTask) -> AgentResult:
            agent = assigned[task.task_id]
            with lock:
                counter["n"] += 1
                idx = counter["n"]
            self._emit(progress, "execute",
                       f"⚙️ 并行执行子任务 {idx}/{total}：{agent.agent_id} — {task.description[:60]}",
                       current=idx, total=total, agent_id=agent.agent_id)
            result = self._run_one(task, agent)
            self._emit_task_done(progress, idx, total, result)
            return result

        while pending:
            wave = [t for t in pending
                    if all(d in results_by_id or d not in assigned for d in t.dependencies)]
            if not wave:  # 循环依赖兜底
                wave = list(pending)
            for t in wave:
                self._attach_upstream(t, subtasks, results_by_id)
            with ThreadPoolExecutor(max_workers=max_workers) as pool:
                futures = {pool.submit(run, t): t for t in wave}
                for fut in as_completed(futures):
                    t = futures[fut]
                    try:
                        results_by_id[t.task_id] = fut.result()
                    except Exception as e:  # noqa: BLE001
                        results_by_id[t.task_id] = AgentResult(
                            task_id=t.task_id, agent_id=assigned[t.task_id].agent_id,
                            success=False, output="", metadata={}, execution_time=0,
                            error_message=str(e),
                        )
            pending = [t for t in pending if t.task_id not in results_by_id]
        return [results_by_id[t.task_id] for t in ordered]

    def _run_competitive(self, request: str, subtasks: List[AgentTask], progress) -> Dict[str, Any]:
        """竞争模式：同一任务并行交给所有能胜任的 Agent，再由 LLM 评审选优。"""
        if len(subtasks) != 1:
            return {
                "success": False,
                "error": "Competitive mode requires exactly one task",
                "summary": f"竞争模式要求单一任务，当前分解出 {len(subtasks)} 个子任务",
            }
        task = subtasks[0]
        assigned_agents = self.task_scheduler.schedule_competitive(task, self.specialized_agents)
        if not assigned_agents:
            return {
                "success": False,
                "error": "No agent can handle the task",
                "summary": "没有能胜任该任务的 Agent",
            }
        total = len(assigned_agents)
        max_workers = max(1, int(getattr(self.task_scheduler, "max_parallel_tasks", 5) or 1))
        results: List[Optional[AgentResult]] = [None] * total

        def run(idx: int, agent: BaseAgent) -> AgentResult:
            self._emit(progress, "execute", f"⚙️ 竞争执行 {idx}/{total}：{agent.agent_id}",
                       current=idx, total=total, agent_id=agent.agent_id)
            # 每个 Agent 用独立的任务副本，避免并发修改同一对象
            own = AgentTask(
                task_id=task.task_id, task_type=task.task_type, description=task.description,
                required_capabilities=list(task.required_capabilities),
                input_data=dict(task.input_data), dependencies=list(task.dependencies),
                priority=task.priority, timeout=task.timeout, metadata=dict(task.metadata),
            )
            try:
                result = agent.execute_task_with_timeout(own)
            except Exception as e:  # noqa: BLE001
                result = AgentResult(task_id=task.task_id, agent_id=agent.agent_id, success=False,
                                     output="", metadata={}, execution_time=0, error_message=str(e))
            self._emit_task_done(progress, idx, total, result)
            return result

        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = {pool.submit(run, i + 1, a): i for i, a in enumerate(assigned_agents)}
            for fut in as_completed(futures):
                results[futures[fut]] = fut.result()

        self._emit(progress, "integrate", "🧷 评审各候选结果（模型评审）..."
                   if getattr(self.result_integrator, "use_llm", False) else "🧷 选择最佳结果...")
        integrated = self.result_integrator.integrate_competitive(
            [r for r in results if r is not None], request=request)
        integrated["decompose_method"] = getattr(self.task_decomposer, "last_method", "rules")
        return integrated
    
    def _emit_task_done(self, progress, idx: int, total: int, result: AgentResult) -> None:
        """上报单个子任务完成/失败。"""
        ok = bool(getattr(result, "success", False))
        agent_id = getattr(result, "agent_id", "?")
        marker = "✅" if ok else "❌"
        detail = "" if ok else f"：{getattr(result, 'error_message', '') or '失败'}"
        self._emit(
            progress, "task_done",
            f"{marker} 子任务 {idx}/{total} 完成（{agent_id}）{detail}",
            current=idx, total=total, agent_id=agent_id, success=ok,
        )

    def _handle_coordination(self, task: AgentTask) -> AgentResult:
        """处理协调任务"""
        request = task.input_data.get("request", "")
        mode_str = task.input_data.get("mode", "hierarchy")
        
        try:
            mode = CollaborationMode(mode_str)
        except ValueError:
            mode = CollaborationMode.HIERARCHY
        
        result = self.coordinate_task(request, mode)
        
        return AgentResult(
            task_id=task.task_id,
            agent_id=self.agent_id,
            success=result.get("success", False),
            output=str(result),
            metadata={"coordination_result": result},
            execution_time=0
        )
    
    def get_status(self) -> Dict[str, Any]:
        """获取MasterAgent状态"""
        return {
            "agent_id": self.agent_id,
            "state": self.get_state().value,
            "specialized_agents_count": len(self.specialized_agents),
            "scheduler_stats": self.task_scheduler.get_statistics()
        }
