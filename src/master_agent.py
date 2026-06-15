"""
MasterAgent - 主控Agent，负责任务分解和协调
"""
from typing import List, Dict, Any
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
        
        # 初始化组件
        self.task_decomposer = TaskDecomposer()
        self.task_scheduler = TaskScheduler(
            max_parallel_tasks=config.get("max_parallel_tasks", 5) if config else 5
        )
        self.result_integrator = ResultIntegrator()
        
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
    
    def coordinate_task(self, request: str, mode: CollaborationMode) -> Dict[str, Any]:
        """
        协调任务的完整流程
        
        Args:
            request: 用户请求
            mode: 协作模式
            
        Returns:
            Dict[str, Any]: 协调结果
        """
        self.logger.info(f"Coordinating task with mode: {mode}")
        
        try:
            # 1. 任务分解
            subtasks = self.task_decomposer.decompose(request, self.specialized_agents)
            
            if not subtasks:
                return {
                    "success": False,
                    "error": "No subtasks generated",
                    "summary": "Failed to decompose task"
                }
            
            self.logger.info(f"Decomposed into {len(subtasks)} subtasks")
            
            # 2. 任务调度
            if mode == CollaborationMode.PARALLEL:
                task_assignments = self.task_scheduler.schedule_parallel(
                    subtasks, self.specialized_agents
                )
            elif mode == CollaborationMode.SEQUENTIAL:
                schedule_steps = self.task_scheduler.schedule_sequential(
                    subtasks, self.specialized_agents
                )
                # 顺序执行
                task_assignments = {}
                results = []
                for step in schedule_steps:
                    for task_id, agent in step.items():
                        task = next(t for t in subtasks if t.task_id == task_id)
                        result = agent.execute_task_with_timeout(task)
                        results.append(result)
                
                # 整合结果
                integrated_result = self.result_integrator.integrate_sequential(results)
                return integrated_result
            
            elif mode == CollaborationMode.COMPETITIVE:
                if len(subtasks) == 1:
                    task = subtasks[0]
                    assigned_agents = self.task_scheduler.schedule_competitive(
                        task, self.specialized_agents
                    )
                    
                    # 竞争执行
                    results = []
                    for agent in assigned_agents:
                        result = agent.execute_task_with_timeout(task)
                        results.append(result)
                    
                    # 整合结果
                    integrated_result = self.result_integrator.integrate_competitive(results)
                    return integrated_result
                else:
                    return {
                        "success": False,
                        "error": "Competitive mode requires exactly one task",
                        "summary": "Invalid task count for competitive mode"
                    }
            
            else:  # HIERARCHY or default
                task_assignments = self.task_scheduler.schedule(
                    subtasks, self.specialized_agents
                )
            
            # 3. 执行任务
            results = []
            for task_id, agent in task_assignments.items():
                task = next(t for t in subtasks if t.task_id == task_id)
                
                self.task_scheduler.mark_task_running(task_id)
                
                try:
                    result = agent.execute_task_with_timeout(task)
                    results.append(result)
                    
                    if result.success:
                        self.task_scheduler.mark_task_completed(task_id, result)
                    else:
                        self.task_scheduler.mark_task_failed(task_id, result.error_message)
                
                except Exception as e:
                    self.logger.error(f"Task execution failed: {e}")
                    self.task_scheduler.mark_task_failed(task_id, str(e))
                    
                    error_result = AgentResult(
                        task_id=task.task_id,
                        agent_id=agent.agent_id,
                        success=False,
                        output="",
                        metadata={},
                        execution_time=0,
                        error_message=str(e)
                    )
                    results.append(error_result)
            
            # 4. 整合结果
            if mode == CollaborationMode.PARALLEL:
                integrated_result = self.result_integrator.integrate_parallel(results)
            else:
                integrated_result = self.result_integrator.integrate(results, subtasks)
            
            return integrated_result
            
        except Exception as e:
            self.logger.error(f"Coordination failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "summary": "Task coordination failed"
            }
    
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
