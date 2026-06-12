"""
任务调度器 - 分配任务给合适的Agent
"""
from typing import List, Dict, Any, Optional
import logging
import heapq
from agents.agent_types import AgentTask, AgentResult, AgentState
from agents.base_agent import BaseAgent


class TaskScheduler:
    """任务调度器，负责任务分配和调度"""
    
    def __init__(self, max_parallel_tasks: int = 5):
        """
        初始化任务调度器
        
        Args:
            max_parallel_tasks: 最大并行任务数
        """
        self.max_parallel_tasks = max_parallel_tasks
        self.task_queue = []
        self.lock = None  # 简化实现，实际可以使用threading.Lock
        self.logger = logging.getLogger("TaskScheduler")
        self.scheduled_tasks: Dict[str, AgentTask] = {}
        self.running_tasks: Dict[str, AgentTask] = {}
        self.completed_tasks: Dict[str, AgentResult] = {}
    
    def schedule(self, tasks: List[AgentTask], available_agents: List[BaseAgent]) -> Dict[str, BaseAgent]:
        """
        调度任务到合适的Agent
        
        Args:
            tasks: 待调度的任务列表
            available_agents: 可用的Agent列表
            
        Returns:
            Dict[str, BaseAgent]: 任务ID到Agent的映射
        """
        self.logger.info(f"Scheduling {len(tasks)} tasks to {len(available_agents)} agents")
        
        # 按优先级排序任务
        sorted_tasks = sorted(tasks, key=lambda t: t.priority, reverse=True)
        
        # 任务到Agent的映射
        task_assignments = {}
        
        # 简单的贪心调度算法
        for task in sorted_tasks:
            # 查找最合适的Agent
            best_agent = self._find_best_agent(task, available_agents, task_assignments)
            
            if best_agent:
                task_assignments[task.task_id] = best_agent
                task.assigned_agent = best_agent.agent_id
                self.scheduled_tasks[task.task_id] = task
                self.logger.debug(
                    f"Task {task.task_id} assigned to agent {best_agent.agent_id}"
                )
            else:
                self.logger.warning(f"No suitable agent found for task {task.task_id}")
                task.assigned_agent = None
        
        return task_assignments
    
    def _find_best_agent(self, task: AgentTask, available_agents: List[BaseAgent], 
                        current_assignments: Dict[str, BaseAgent]) -> Optional[BaseAgent]:
        """
        查找最适合处理任务的Agent
        
        Args:
            task: 任务对象
            available_agents: 可用的Agent列表
            current_assignments: 当前任务分配情况
            
        Returns:
            Optional[BaseAgent]: 最适合的Agent，如果没有合适的返回None
        """
        suitable_agents = []
        
        for agent in available_agents:
            # 检查Agent是否能处理该任务
            if not agent.can_handle(task):
                continue
            
            # 检查Agent是否空闲
            if agent.get_state() != AgentState.IDLE:
                continue
            
            # 检查并行任务限制
            current_load = sum(1 for assigned_agent in current_assignments.values() 
                             if assigned_agent.agent_id == agent.agent_id)
            if current_load >= self.max_parallel_tasks:
                continue
            
            suitable_agents.append(agent)
        
        if not suitable_agents:
            return None
        
        # 简单的选择第一个合适的Agent
        # 实际中可以使用更复杂的负载均衡策略
        return suitable_agents[0]
    
    def schedule_parallel(self, tasks: List[AgentTask], 
                        available_agents: List[BaseAgent]) -> Dict[str, BaseAgent]:
        """
        并行调度任务
        
        Args:
            tasks: 任务列表
            available_agents: 可用的Agent列表
            
        Returns:
            Dict[str, BaseAgent]: 任务到Agent的映射
        """
        self.logger.info("Scheduling tasks in parallel mode")
        
        # 并行调度：尽可能多地分配任务
        task_assignments = {}
        
        for task in tasks:
            # 查找任何可用的Agent
            for agent in available_agents:
                if agent.can_handle(task) and agent.get_state() == AgentState.IDLE:
                    task_assignments[task.task_id] = agent
                    task.assigned_agent = agent.agent_id
                    self.scheduled_tasks[task.task_id] = task
                    break
            
            if task.task_id not in task_assignments:
                self.logger.warning(f"No agent available for task {task.task_id}")
        
        return task_assignments
    
    def schedule_sequential(self, tasks: List[AgentTask], 
                          available_agents: List[BaseAgent]) -> List[Dict[str, BaseAgent]]:
        """
        顺序调度任务（按依赖关系）
        
        Args:
            tasks: 任务列表
            available_agents: 可用的Agent列表
            
        Returns:
            List[Dict[str, BaseAgent]]: 按顺序的调度步骤
        """
        self.logger.info("Scheduling tasks in sequential mode")
        
        # 构建依赖图
        dependency_graph = self._build_dependency_graph(tasks)
        
        # 拓扑排序
        ordered_tasks = self._topological_sort(tasks, dependency_graph)
        
        # 按顺序分配
        schedule_steps = []
        for task in ordered_tasks:
            best_agent = self._find_best_agent(task, available_agents, {})
            if best_agent:
                schedule_steps.append({task.task_id: best_agent})
                task.assigned_agent = best_agent.agent_id
                self.scheduled_tasks[task.task_id] = task
            else:
                self.logger.warning(f"No agent available for task {task.task_id}")
        
        return schedule_steps
    
    def schedule_competitive(self, task: AgentTask, 
                           available_agents: List[BaseAgent]) -> List[BaseAgent]:
        """
        竞争调度：将同一任务分配给多个Agent
        
        Args:
            task: 任务对象
            available_agents: 可用的Agent列表
            
        Returns:
            List[BaseAgent]: 分配的Agent列表
        """
        self.logger.info(f"Scheduling task {task.task_id} in competitive mode")
        
        assigned_agents = []
        for agent in available_agents:
            if agent.can_handle(task) and agent.get_state() == AgentState.IDLE:
                assigned_agents.append(agent)
                task.assigned_agent = agent.agent_id  # 会被覆盖，但记录最后一个
        
        self.scheduled_tasks[task.task_id] = task
        return assigned_agents
    
    def _build_dependency_graph(self, tasks: List[AgentTask]) -> Dict[str, List[str]]:
        """构建任务依赖图"""
        graph = {}
        for task in tasks:
            graph[task.task_id] = task.dependencies
        return graph
    
    def _topological_sort(self, tasks: List[AgentTask], 
                         graph: Dict[str, List[str]]) -> List[AgentTask]:
        """拓扑排序任务"""
        task_map = {task.task_id: task for task in tasks}
        in_degree = {task.task_id: 0 for task in tasks}
        
        # 计算入度
        for task_id, dependencies in graph.items():
            for dep_id in dependencies:
                if dep_id in in_degree:
                    in_degree[task_id] += 1
        
        # 从入度为0的任务开始
        queue = [task_id for task_id, degree in in_degree.items() if degree == 0]
        result = []
        
        while queue:
            task_id = queue.pop(0)
            result.append(task_map[task_id])
            
            # 减少依赖任务的入度
            for other_task_id, dependencies in graph.items():
                if task_id in dependencies:
                    in_degree[other_task_id] -= 1
                    if in_degree[other_task_id] == 0:
                        queue.append(other_task_id)
        
        return result
    
    def mark_task_running(self, task_id: str):
        """标记任务为运行中"""
        if task_id in self.scheduled_tasks:
            task = self.scheduled_tasks[task_id]
            self.running_tasks[task_id] = task
            task.status = task.status.__class__.RUNNING
            del self.scheduled_tasks[task_id]  # 从scheduled_tasks中移除
            self.logger.debug(f"Task {task_id} marked as running")
    
    def mark_task_completed(self, task_id: str, result: AgentResult):
        """标记任务为完成"""
        if task_id in self.running_tasks:
            del self.running_tasks[task_id]
        
        if task_id in self.scheduled_tasks:
            del self.scheduled_tasks[task_id]
        
        self.completed_tasks[task_id] = result
        self.logger.info(f"Task {task_id} completed with success={result.success}")
    
    def mark_task_failed(self, task_id: str, error: str):
        """标记任务为失败"""
        if task_id in self.running_tasks:
            del self.running_tasks[task_id]
        
        if task_id in self.scheduled_tasks:
            del self.scheduled_tasks[task_id]
        
        self.logger.error(f"Task {task_id} failed: {error}")
    
    def get_task_status(self, task_id: str) -> str:
        """获取任务状态"""
        if task_id in self.completed_tasks:
            return "completed"
        elif task_id in self.running_tasks:
            return "running"
        elif task_id in self.scheduled_tasks:
            return "scheduled"
        else:
            return "unknown"
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取调度统计信息"""
        return {
            "scheduled": len(self.scheduled_tasks),
            "running": len(self.running_tasks),
            "completed": len(self.completed_tasks),
            "total": len(self.scheduled_tasks) + len(self.running_tasks) + len(self.completed_tasks)
        }
    
    def reset(self):
        """重置调度器"""
        self.task_queue.clear()
        self.scheduled_tasks.clear()
        self.running_tasks.clear()
        self.completed_tasks.clear()
        self.logger.debug("Task scheduler reset")
