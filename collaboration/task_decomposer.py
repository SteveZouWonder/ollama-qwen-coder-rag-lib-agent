"""
任务分解器 - 将复杂任务分解为可管理的子任务
"""
from typing import List, Dict, Any
import uuid
import logging
from agents.agent_types import AgentTask, TaskStatus
from agents.agent_types import AgentType


class TaskDecomposer:
    """任务分解器，将复杂任务分解为子任务"""
    
    def __init__(self):
        """初始化任务分解器"""
        self.logger = logging.getLogger("TaskDecomposer")
    
    def decompose(self, request: str, available_agents: List[Any] = None) -> List[AgentTask]:
        """
        分解用户请求为子任务
        
        Args:
            request: 用户请求
            available_agents: 可用的Agent列表
            
        Returns:
            List[AgentTask]: 分解后的子任务列表
        """
        self.logger.info(f"Decomposing request: {request[:100]}...")
        
        # 简化的任务分解逻辑
        # 实际应用中可以使用LLM来智能分解任务
        tasks = self._analyze_and_decompose(request, available_agents)
        
        self.logger.info(f"Decomposed into {len(tasks)} subtasks")
        return tasks
    
    def _analyze_and_decompose(self, request: str, available_agents: List[Any] = None) -> List[AgentTask]:
        """
        分析请求并生成子任务
        
        Args:
            request: 用户请求
            available_agents: 可用的Agent列表
            
        Returns:
            List[AgentTask]: 子任务列表
        """
        tasks = []
        
        # 获取可用的能力
        available_capabilities = set()
        if available_agents:
            for agent in available_agents:
                available_capabilities.update(agent.capabilities)
        
        # 基于关键词的简单任务分解
        request_lower = request.lower()
        
        # 代码相关任务
        if any(keyword in request_lower for keyword in ['代码', 'code', '实现', 'implement', '开发', 'develop']):
            task = AgentTask(
                task_id=str(uuid.uuid4()),
                task_type="code_generation",
                description=f"代码相关任务: {request}",
                required_capabilities=["code_generation"],
                input_data={"request": request},
                priority=7
            )
            if "code_generation" in available_capabilities or not available_agents:
                tasks.append(task)
        
        # 测试相关任务
        if any(keyword in request_lower for keyword in ['测试', 'test', '单元测试', 'unittest', '验证', 'verify']):
            task = AgentTask(
                task_id=str(uuid.uuid4()),
                task_type="testing",
                description=f"测试相关任务: {request}",
                required_capabilities=["testing"],
                input_data={"request": request},
                priority=6
            )
            if "testing" in available_capabilities or not available_agents:
                tasks.append(task)
        
        # 文档相关任务
        if any(keyword in request_lower for keyword in ['文档', 'document', 'doc', '说明', 'explain', '文档化']):
            task = AgentTask(
                task_id=str(uuid.uuid4()),
                task_type="documentation",
                description=f"文档相关任务: {request}",
                required_capabilities=["documentation"],
                input_data={"request": request},
                priority=5
            )
            if "documentation" in available_capabilities or not available_agents:
                tasks.append(task)
        
        # 知识库相关任务
        if any(keyword in request_lower for keyword in ['检索', 'search', '查询', 'query', '知识库', 'knowledge']):
            task = AgentTask(
                task_id=str(uuid.uuid4()),
                task_type="knowledge_retrieval",
                description=f"知识库检索任务: {request}",
                required_capabilities=["knowledge_retrieval"],
                input_data={"request": request},
                priority=8
            )
            if "knowledge_retrieval" in available_capabilities or not available_agents:
                tasks.append(task)
        
        # 审计相关任务
        if any(keyword in request_lower for keyword in ['审计', 'audit', '检查', 'check', '安全', 'security']):
            task = AgentTask(
                task_id=str(uuid.uuid4()),
                task_type="audit",
                description=f"审计相关任务: {request}",
                required_capabilities=["audit"],
                input_data={"request": request},
                priority=4
            )
            if "audit" in available_capabilities or not available_agents:
                tasks.append(task)
        
        # 如果没有匹配到任何特定任务，创建一个通用任务
        if not tasks:
            task = AgentTask(
                task_id=str(uuid.uuid4()),
                task_type="general",
                description=f"通用任务: {request}",
                required_capabilities=["general"],
                input_data={"request": request},
                priority=5
            )
            tasks.append(task)
        
        # 设置任务依赖关系（简化版）
        if len(tasks) > 1:
            # 假设测试任务依赖于代码任务
            code_tasks = [t for t in tasks if t.task_type == "code_generation"]
            test_tasks = [t for t in tasks if t.task_type == "testing"]
            
            if code_tasks and test_tasks:
                for test_task in test_tasks:
                    test_task.dependencies = [code_tasks[0].task_id]
        
        return tasks
    
    def decompose_by_pattern(self, pattern: str, request: str, 
                            available_agents: List[Any] = None) -> List[AgentTask]:
        """
        根据特定模式分解任务
        
        Args:
            pattern: 分解模式 (parallel, sequential, hierarchy)
            request: 用户请求
            available_agents: 可用的Agent列表
            
        Returns:
            List[AgentTask]: 分解后的子任务列表
        """
        tasks = self._analyze_and_decompose(request, available_agents)
        
        if pattern == "parallel":
            # 并行模式：移除依赖关系
            for task in tasks:
                task.dependencies = []
        elif pattern == "sequential":
            # 顺序模式：添加顺序依赖
            for i in range(1, len(tasks)):
                tasks[i].dependencies = [tasks[i-1].task_id]
        elif pattern == "hierarchy":
            # 层级模式：保持默认的依赖关系
            pass
        
        return tasks
    
    def validate_task(self, task: AgentTask, available_capabilities: List[str]) -> bool:
        """
        验证任务是否可执行
        
        Args:
            task: 任务对象
            available_capabilities: 可用的能力列表
            
        Returns:
            bool: 任务是否可执行
        """
        required = set(task.required_capabilities)
        available = set(available_capabilities)
        return required.issubset(available)
    
    def estimate_complexity(self, task: AgentTask) -> str:
        """
        估计任务复杂度
        
        Args:
            task: 任务对象
            
        Returns:
            str: 复杂度等级 (low, medium, high)
        """
        # 简化的复杂度估计
        if len(task.required_capabilities) <= 1:
            return "low"
        elif len(task.required_capabilities) <= 3:
            return "medium"
        else:
            return "high"
    
    def create_task_from_template(self, template: Dict[str, Any], 
                                  params: Dict[str, Any]) -> AgentTask:
        """
        从模板创建任务
        
        Args:
            template: 任务模板
            params: 参数
            
        Returns:
            AgentTask: 创建的任务
        """
        task_data = template.copy()
        task_data.update(params)
        task_data['task_id'] = str(uuid.uuid4())
        
        return AgentTask(**task_data)
