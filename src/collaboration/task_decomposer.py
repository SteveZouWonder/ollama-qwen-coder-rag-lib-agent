"""
任务分解器 - 将复杂任务分解为可管理的子任务

分解策略：先调用一次 LLM（``think=False``、``num_predict≤512``）输出 JSON 子任务
列表；解析失败 / 超时 / 未开启 LLM 时回退到关键词表。``last_method`` 记录本次
实际使用的方法（``"llm"`` / ``"rules"``），供协调层如实展示进度文案。
"""
from typing import List, Dict, Any, Optional, Callable
import uuid
import logging
from agents.agent_types import AgentTask
from .llm_helper import complete_json, truncate


# 子任务类型 → (required_capabilities, priority)
TASK_TYPE_SPECS: Dict[str, Dict[str, Any]] = {
    "code_generation": {"capabilities": ["code_generation"], "priority": 7},
    "testing": {"capabilities": ["testing"], "priority": 6},
    "documentation": {"capabilities": ["documentation"], "priority": 5},
    "knowledge_retrieval": {"capabilities": ["knowledge_retrieval"], "priority": 8},
    "audit": {"capabilities": ["audit"], "priority": 4},
    "general": {"capabilities": ["general"], "priority": 5},
}

DECOMPOSE_PROMPT = """把用户请求拆成可独立执行的子任务，只输出 JSON，不要解释。
type 只能取: code_generation|testing|documentation|knowledge_retrieval|audit|general
纯问答/查资料/总结/比较 → 只给 1 个 knowledge_retrieval；单一意图不要拆，最多 5 个。
depends_on 填被依赖子任务的序号（从 0 开始），如测试依赖代码。
{{"subtasks":[{{"type":"...","description":"独立可执行的描述","depends_on":[]}}]}}
用户请求：{request}"""

MAX_SUBTASKS = 5


class TaskDecomposer:
    """任务分解器，将复杂任务分解为子任务"""
    
    def __init__(self, complete: Optional[Callable[[str], str]] = None,
                 use_llm: bool = True, llm_timeout: int = 60):
        """初始化任务分解器

        Args:
            complete: 可注入的 LLM 补全函数（测试用）；None 时用全局模型。
            use_llm: 是否先尝试 LLM 分解；False 则只用关键词表。
            llm_timeout: LLM 分解调用超时（秒）。
        """
        self.logger = logging.getLogger("TaskDecomposer")
        self._complete = complete
        self.use_llm = use_llm
        self.llm_timeout = llm_timeout
        self.last_method: str = "rules"
    
    def decompose(self, request: str, available_agents: List[Any] = None) -> List[AgentTask]:
        """
        分解用户请求为子任务：LLM 优先，失败回退关键词表。
        
        Args:
            request: 用户请求
            available_agents: 可用的Agent列表
            
        Returns:
            List[AgentTask]: 分解后的子任务列表
        """
        self.logger.info(f"Decomposing request: {request[:100]}...")

        tasks: List[AgentTask] = []
        if self.use_llm and (request or "").strip():
            tasks = self._decompose_with_llm(request, available_agents)
        if tasks:
            self.last_method = "llm"
        else:
            self.last_method = "rules"
            tasks = self._analyze_and_decompose(request, available_agents)
        
        self.logger.info(f"Decomposed into {len(tasks)} subtasks via {self.last_method}")
        return tasks

    # ---------- LLM 分解 ----------

    @staticmethod
    def _available_capabilities(available_agents: Optional[List[Any]]) -> set:
        caps = set()
        for agent in available_agents or []:
            caps.update(getattr(agent, "capabilities", []) or [])
        return caps

    def _decompose_with_llm(self, request: str, available_agents: Optional[List[Any]]) -> List[AgentTask]:
        """一次 LLM 调用得到子任务 JSON；任何异常/不合法输出返回 []（触发回退）。"""
        prompt = DECOMPOSE_PROMPT.format(request=truncate(request, 1500))
        data = complete_json(prompt, complete=self._complete, num_predict=512,
                             timeout=self.llm_timeout)
        if not data:
            return []
        raw_items = data.get("subtasks")
        if not isinstance(raw_items, list) or not raw_items:
            return []

        caps = self._available_capabilities(available_agents)
        specs: List[Dict[str, Any]] = []
        for item in raw_items[:MAX_SUBTASKS]:
            if not isinstance(item, dict):
                continue
            ttype = str(item.get("type", "")).strip().lower()
            desc = str(item.get("description", "")).strip()
            if ttype not in TASK_TYPE_SPECS or not desc:
                continue
            # 该类型所需能力无可用 Agent 时降级为 general（由 RAGAgent 兜底）
            need = TASK_TYPE_SPECS[ttype]["capabilities"]
            if available_agents and not set(need).issubset(caps):
                if "general" not in caps:
                    continue
                ttype = "general"
            deps = item.get("depends_on") or []
            deps = [int(d) for d in deps if isinstance(d, (int, float)) and int(d) >= 0]
            specs.append({"type": ttype, "description": desc, "depends_on": deps})

        if not specs:
            return []

        tasks: List[AgentTask] = []
        for spec in specs:
            spec_def = TASK_TYPE_SPECS[spec["type"]]
            tasks.append(AgentTask(
                task_id=str(uuid.uuid4()),
                task_type=spec["type"],
                description=spec["description"],
                required_capabilities=list(spec_def["capabilities"]),
                input_data={"request": spec["description"], "original_request": request},
                priority=spec_def["priority"],
                metadata={"decomposed_by": "llm"},
            ))
        # 依赖：序号 → task_id（忽略越界与自引用）
        for idx, spec in enumerate(specs):
            deps = [tasks[d].task_id for d in spec["depends_on"] if d < len(tasks) and d != idx]
            tasks[idx].dependencies = deps
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
                input_data={"request": request, "original_request": request},
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
                input_data={"request": request, "original_request": request},
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
                input_data={"request": request, "original_request": request},
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
                input_data={"request": request, "original_request": request},
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
                input_data={"request": request, "original_request": request},
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
                input_data={"request": request, "original_request": request},
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
