# 多Agent系统实现指南

## 📋 文档信息

- **文档版本**: v1.0
- **创建日期**: 2026-06-10
- **关联文档**: DESIGN.md

---

## 🚀 快速开始

### 开发环境准备

```bash
# 确保在项目根目录
cd /Users/steve/PycharmProjects/ollama-qwen-coder-rag-lib-agent

# 创建新的模块目录
mkdir -p agents collaboration

# 安装必要的依赖（如有新增）
pip install -r requirements.txt
```

### 最小化原型

首先实现一个最小化原型，验证核心概念：

```python
# agents/base_agent.py
class BaseAgent:
    def __init__(self, agent_id: str):
        self.agent_id = agent_id
    
    def process(self, task: str) -> str:
        return f"Agent {self.agent_id} processed: {task}"

# 测试
agent = BaseAgent("test")
print(agent.process("hello"))  # Agent test processed: hello
```

---

## 📁 详细实现步骤

### Step 1: 实现基础数据结构

创建 `agent_types.py` 文件：

```python
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from enum import Enum

class CollaborationMode(Enum):
    """协作模式枚举"""
    HIERARCHY = "hierarchy"      # 层级协作
    PARALLEL = "parallel"        # 并行协作
    SEQUENTIAL = "sequential"   # 顺序协作
    COMPETITIVE = "competitive" # 竞争协作

class AgentType(Enum):
    """Agent类型枚举"""
    MASTER = "master"
    CODE = "code"
    RAG = "rag"
    TEST = "test"
    DOC = "doc"
    AUDIT = "audit"

@dataclass
class AgentTask:
    """Agent任务"""
    task_id: str
    task_type: str
    description: str
    required_capabilities: List[str]
    input_data: Dict[str, Any]
    dependencies: List[str] = field(default_factory=list)
    priority: int = 5
    timeout: int = 300
    metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass
class AgentResult:
    """Agent执行结果"""
    task_id: str
    agent_id: str
    success: bool
    output: str
    metadata: Dict[str, Any]
    execution_time: float
    error_message: str = ""

@dataclass
class AgentMessage:
    """Agent间消息"""
    from_agent: str
    to_agent: str
    message_type: str
    content: Dict[str, Any]
    timestamp: float
```

### Step 2: 实现Agent基类

创建 `agents/base_agent.py` 文件：

```python
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
import time
from .agent_types import AgentTask, AgentResult, AgentType

class BaseAgent(ABC):
    """Agent基类"""
    
    def __init__(self, agent_id: str, agent_type: AgentType, 
                 capabilities: List[str]):
        self.agent_id = agent_id
        self.agent_type = agent_type
        self.capabilities = capabilities
        self.message_handlers = {}
    
    @abstractmethod
    def process_task(self, task: AgentTask) -> AgentResult:
        """处理任务（子类必须实现）"""
        pass
    
    def can_handle(self, task: AgentTask) -> bool:
        """判断是否能处理该任务"""
        required = set(task.required_capabilities)
        available = set(self.capabilities)
        return required.issubset(available)
    
    def get_capability(self) -> List[str]:
        """获取能力列表"""
        return self.capabilities
    
    def register_message_handler(self, message_type: str, handler):
        """注册消息处理器"""
        self.message_handlers[message_type] = handler
    
    def handle_message(self, message: AgentMessage):
        """处理接收到的消息"""
        handler = self.message_handlers.get(message.message_type)
        if handler:
            handler(message)
```

### Step 3: 实现消息总线

创建 `collaboration/message_bus.py` 文件：

```python
from collections import defaultdict
from queue import Queue
from threading import Lock
from typing import Callable, Dict, List
import time
from ..agents.agent_types import AgentMessage

class MessageBus:
    """Agent间通信消息总线"""
    
    def __init__(self):
        self.subscribers: Dict[str, List[Callable]] = defaultdict(list)
        self.message_queue = Queue()
        self.lock = Lock()
    
    def subscribe(self, agent_id: str, callback: Callable[[AgentMessage], None]):
        """Agent订阅消息"""
        with self.lock:
            self.subscribers[agent_id].append(callback)
    
    def unsubscribe(self, agent_id: str, callback: Callable):
        """取消订阅"""
        with self.lock:
            if callback in self.subscribers[agent_id]:
                self.subscribers[agent_id].remove(callback)
    
    def publish(self, message: AgentMessage):
        """发布消息（广播）"""
        with self.lock:
            subscribers = self.subscribers.get(message.to_agent, [])
            for callback in subscribers:
                try:
                    callback(message)
                except Exception as e:
                    print(f"Message handler error: {e}")
    
    def send_direct(self, from_agent: str, to_agent: str, 
                   message_type: str, content: Dict):
        """点对点发送消息"""
        message = AgentMessage(
            from_agent=from_agent,
            to_agent=to_agent,
            message_type=message_type,
            content=content,
            timestamp=time.time()
        )
        self.publish(message)
    
    def broadcast(self, from_agent: str, message_type: str, content: Dict):
        """广播消息给所有订阅者"""
        with self.lock:
            for agent_id, callbacks in self.subscribers.items():
                if agent_id != from_agent:
                    message = AgentMessage(
                        from_agent=from_agent,
                        to_agent=agent_id,
                        message_type=message_type,
                        content=content,
                        timestamp=time.time()
                    )
                    for callback in callbacks:
                        try:
                            callback(message)
                        except Exception as e:
                            print(f"Broadcast error: {e}")
```

### Step 4: 实现Agent注册中心

创建 `agent_registry.py` 文件：

```python
from typing import Dict, List, Optional
from agents import BaseAgent
from agents.agent_types import AgentType


class AgentRegistry:
    """Agent注册中心"""

    def __init__(self):
        self.agents: Dict[str, BaseAgent] = {}
        self.capabilities_index: Dict[str, List[str]] = {}

    def register(self, agent: BaseAgent):
        """注册Agent"""
        self.agents[agent.agent_id] = agent

        # 更新能力索引
        for capability in agent.capabilities:
            if capability not in self.capabilities_index:
                self.capabilities_index[capability] = []
            self.capabilities_index[capability].append(agent.agent_id)

    def unregister(self, agent_id: str):
        """注销Agent"""
        if agent_id in self.agents:
            agent = self.agents[agent_id]

            # 更新能力索引
            for capability in agent.capabilities:
                if capability in self.capabilities_index:
                    self.capabilities_index[capability].remove(agent_id)

            del self.agents[agent_id]

    def get_agent(self, agent_id: str) -> Optional[BaseAgent]:
        """获取Agent实例"""
        return self.agents.get(agent_id)

    def find_agents_by_capability(self, capability: str) -> List[BaseAgent]:
        """根据能力查找Agent"""
        agent_ids = self.capabilities_index.get(capability, [])
        return [self.agents[aid] for aid in agent_ids if aid in self.agents]

    def find_agents_by_type(self, agent_type: AgentType) -> List[BaseAgent]:
        """根据类型查找Agent"""
        return [agent for agent in self.agents.values()
                if agent.agent_type == agent_type]

    def get_all_agents(self) -> List[BaseAgent]:
        """获取所有Agent"""
        return list(self.agents.values())

    def get_agent_count(self) -> int:
        """获取Agent数量"""
        return len(self.agents)
```

### Step 5: 实现任务分解器

创建 `collaboration/task_decomposer.py` 文件：

```python
from typing import List, Dict, Tuple
import re
from agents.agent_types import AgentTask, AgentType


class TaskDecomposer:
    """任务分解器"""

    def __init__(self):
        self.decomposition_patterns = {
            "code_generation": [
                r"实现|开发|编写|创建.*功能",
                r"写一个.*函数|类|模块"
            ],
            "testing": [
                r"测试|单元测试|集成测试",
                r"验证|检查.*正确性"
            ],
            "documentation": [
                r"文档|说明|指南",
                r"生成.*文档"
            ],
            "analysis": [
                r"分析|评估|审查",
                r"优化|重构"
            ]
        }

    def decompose(self, request: str, context: Dict = None) -> List[AgentTask]:
        """分解复杂任务为子任务"""
        context = context or {}
        tasks = []

        # 简单实现：基于关键词匹配
        if self._contains_keywords(request, ["代码", "功能", "实现"]):
            tasks.append(self._create_code_task(request, context))

        if self._contains_keywords(request, ["测试", "验证"]):
            tasks.append(self._create_test_task(request, context))

        if self._contains_keywords(request, ["文档", "说明"]):
            tasks.append(self._create_doc_task(request, context))

        # 如果没有匹配到任何模式，返回单一任务
        if not tasks:
            tasks.append(self._create_generic_task(request, context))

        return tasks

    def _contains_keywords(self, text: str, keywords: List[str]) -> bool:
        """检查文本是否包含关键词"""
        return any(keyword in text for keyword in keywords)

    def _create_code_task(self, request: str, context: Dict) -> AgentTask:
        """创建代码任务"""
        return AgentTask(
            task_id=f"code_{hash(request)}",
            task_type="code_generation",
            description=f"代码生成: {request}",
            required_capabilities=["code_generation", "file_operations"],
            input_data={"request": request, "context": context},
            priority=5
        )

    def _create_test_task(self, request: str, context: Dict) -> AgentTask:
        """创建测试任务"""
        return AgentTask(
            task_id=f"test_{hash(request)}",
            task_type="testing",
            description=f"测试: {request}",
            required_capabilities=["testing", "code_analysis"],
            input_data={"request": request, "context": context},
            priority=4,
            dependencies=["code_generation"]  # 依赖代码生成
        )

    def _create_doc_task(self, request: str, context: Dict) -> AgentTask:
        """创建文档任务"""
        return AgentTask(
            task_id=f"doc_{hash(request)}",
            task_type="documentation",
            description=f"文档: {request}",
            required_capabilities=["documentation", "writing"],
            input_data={"request": request, "context": context},
            priority=3,
            dependencies=["code_generation"]  # 依赖代码生成
        )

    def _create_generic_task(self, request: str, context: Dict) -> AgentTask:
        """创建通用任务"""
        return AgentTask(
            task_id=f"generic_{hash(request)}",
            task_type="generic",
            description=f"通用任务: {request}",
            required_capabilities=["general"],
            input_data={"request": request, "context": context},
            priority=5
        )

    def detect_dependencies(self, tasks: List[AgentTask]) -> Dict[str, List[str]]:
        """检测任务依赖关系"""
        dependency_map = {}
        for task in tasks:
            dependency_map[task.task_id] = task.dependencies
        return dependency_map

    def estimate_complexity(self, task: AgentTask) -> int:
        """评估任务复杂度（1-10）"""
        # 简单实现：基于任务类型
        complexity_map = {
            "code_generation": 7,
            "testing": 5,
            "documentation": 4,
            "analysis": 6,
            "generic": 5
        }
        return complexity_map.get(task.task_type, 5)
```

### Step 6: 实现任务调度器

创建 `collaboration/task_scheduler.py` 文件：

```python
from typing import List, Dict, Optional
import time
from agents.agent_types import AgentTask, AgentResult, CollaborationMode
from agents import BaseAgent
from agent_registry import AgentRegistry


class TaskScheduler:
    """任务调度器"""

    def __init__(self, registry: AgentRegistry):
        self.registry = registry
        self.active_tasks: Dict[str, AgentTask] = {}
        self.task_results: Dict[str, AgentResult] = {}

    def schedule(self, tasks: List[AgentTask],
                 mode: CollaborationMode) -> Dict[str, BaseAgent]:
        """根据协作模式调度任务"""
        assignment = {}

        if mode == CollaborationMode.PARALLEL:
            assignment = self._schedule_parallel(tasks)
        elif mode == CollaborationMode.SEQUENTIAL:
            assignment = self._schedule_sequential(tasks)
        elif mode == CollaborationMode.HIERARCHY:
            assignment = self._schedule_hierarchy(tasks)
        elif mode == CollaborationMode.COMPETITIVE:
            assignment = self._schedule_competitive(tasks)
        else:
            assignment = self._schedule_parallel(tasks)

        return assignment

    def _schedule_parallel(self, tasks: List[AgentTask]) -> Dict[str, BaseAgent]:
        """并行调度"""
        assignment = {}
        for task in tasks:
            agent = self._assign_agent(task)
            if agent:
                assignment[task.task_id] = agent
        return assignment

    def _schedule_sequential(self, tasks: List[AgentTask]) -> Dict[str, BaseAgent]:
        """顺序调度（考虑依赖）"""
        assignment = {}
        # 拓扑排序
        sorted_tasks = self._topological_sort(tasks)
        for task in sorted_tasks:
            agent = self._assign_agent(task)
            if agent:
                assignment[task.task_id] = agent
        return assignment

    def _schedule_hierarchy(self, tasks: List[AgentTask]) -> Dict[str, BaseAgent]:
        """层级调度"""
        # 优先级调度
        sorted_tasks = sorted(tasks, key=lambda t: t.priority, reverse=True)
        assignment = {}
        for task in sorted_tasks:
            agent = self._assign_agent(task)
            if agent:
                assignment[task.task_id] = agent
        return assignment

    def _schedule_competitive(self, tasks: List[AgentTask]) -> Dict[str, BaseAgent]:
        """竞争调度（同一任务分配给多个Agent）"""
        assignment = {}
        for task in tasks:
            # 为每个任务找到所有能处理的Agent
            capable_agents = []
            for agent in self.registry.get_all_agents():
                if agent.can_handle(task):
                    capable_agents.append(agent)

            # 竞争模式下，分配给所有能处理的Agent
            if capable_agents:
                assignment[task.task_id] = capable_agents[0]  # 简化：只分配第一个
        return assignment

    def _assign_agent(self, task: AgentTask) -> Optional[BaseAgent]:
        """为任务分配最合适的Agent"""
        capable_agents = []
        for agent in self.registry.get_all_agents():
            if agent.can_handle(task):
                capable_agents.append(agent)

        if not capable_agents:
            return None

        # 简单策略：选择第一个
        return capable_agents[0]

    def _topological_sort(self, tasks: List[AgentTask]) -> List[AgentTask]:
        """拓扑排序（基于依赖关系）"""
        task_map = {task.task_id: task for task in tasks}
        in_degree = {task.task_id: 0 for task in tasks}

        # 计算入度
        for task in tasks:
            for dep_id in task.dependencies:
                if dep_id in in_degree:
                    in_degree[task.task_id] += 1

        # 拓扑排序
        queue = [task_id for task_id, degree in in_degree.items() if degree == 0]
        result = []

        while queue:
            current_id = queue.pop(0)
            result.append(task_map[current_id])

            # 减少依赖任务的入度
            for task in tasks:
                if current_id in task.dependencies:
                    in_degree[task.task_id] -= 1
                    if in_degree[task.task_id] == 0:
                        queue.append(task.task_id)

        return result

    def execute_task(self, task: AgentTask, agent: BaseAgent) -> AgentResult:
        """执行单个任务"""
        start_time = time.time()
        try:
            output = agent.process_task(task)
            execution_time = time.time() - start_time
            return AgentResult(
                task_id=task.task_id,
                agent_id=agent.agent_id,
                success=True,
                output=output,
                metadata={},
                execution_time=execution_time
            )
        except Exception as e:
            execution_time = time.time() - start_time
            return AgentResult(
                task_id=task.task_id,
                agent_id=agent.agent_id,
                success=False,
                output="",
                metadata={},
                execution_time=execution_time,
                error_message=str(e)
            )
```

### Step 7: 实现结果整合器

创建 `collaboration/result_integrator.py` 文件：

```python
from typing import List, Dict
from agents.agent_types import AgentResult


class ResultIntegrator:
    """结果整合器"""

    def __init__(self):
        self.integration_strategies = {
            "concatenate": self._concatenate_results,
            "merge": self._merge_results,
            "vote": self._vote_results,
            "select_best": self._select_best_result
        }

    def integrate(self, results: List[AgentResult],
                  strategy: str = "merge") -> Dict:
        """整合多个Agent的结果"""
        strategy_func = self.integration_strategies.get(strategy, self._merge_results)
        return strategy_func(results)

    def _concatenate_results(self, results: List[AgentResult]) -> Dict:
        """拼接结果"""
        combined_output = "\n\n".join([
            f"=== {result.agent_id} ===\n{result.output}"
            for result in results
        ])

        return {
            "success": all(r.success for r in results),
            "output": combined_output,
            "details": [self._result_to_dict(r) for r in results],
            "total_time": sum(r.execution_time for r in results)
        }

    def _merge_results(self, results: List[AgentResult]) -> Dict:
        """合并结果"""
        # 简单实现：合并成功的结果
        successful_results = [r for r in results if r.success]

        if not successful_results:
            return {
                "success": False,
                "output": "所有任务执行失败",
                "details": [self._result_to_dict(r) for r in results],
                "total_time": sum(r.execution_time for r in results)
            }

        merged_output = "\n\n".join([r.output for r in successful_results])

        return {
            "success": True,
            "output": merged_output,
            "details": [self._result_to_dict(r) for r in results],
            "total_time": sum(r.execution_time for r in results)
        }

    def _vote_results(self, results: List[AgentResult]) -> Dict:
        """投票机制（用于竞争模式）"""
        from collections import Counter

        if not results:
            return {"success": False, "output": "无结果"}

        # 简单实现：选择最常见的输出
        outputs = [r.output for r in results if r.success]
        if not outputs:
            return {"success": False, "output": "无成功结果"}

        counter = Counter(outputs)
        most_common = counter.most_common(1)[0][0]

        return {
            "success": True,
            "output": most_common,
            "vote_counts": dict(counter),
            "details": [self._result_to_dict(r) for r in results],
            "total_time": sum(r.execution_time for r in results)
        }

    def _select_best_result(self, results: List[AgentResult]) -> Dict:
        """选择最佳结果"""
        successful_results = [r for r in results if r.success]

        if not successful_results:
            return {
                "success": False,
                "output": "无成功结果",
                "details": [self._result_to_dict(r) for r in results]
            }

        # 简单实现：选择执行时间最短的成功结果
        best = min(successful_results, key=lambda r: r.execution_time)

        return {
            "success": True,
            "output": best.output,
            "selected_agent": best.agent_id,
            "execution_time": best.execution_time,
            "details": [self._result_to_dict(r) for r in results]
        }

    def _result_to_dict(self, result: AgentResult) -> Dict:
        """将结果转换为字典"""
        return {
            "task_id": result.task_id,
            "agent_id": result.agent_id,
            "success": result.success,
            "output": result.output,
            "execution_time": result.execution_time,
            "error_message": result.error_message,
            "metadata": result.metadata
        }
```

### Step 8: 实现MasterAgent

创建 `master_agent.py` 文件：

```python
from typing import List, Dict, Optional
from agents import BaseAgent
from agents.agent_types import AgentTask, AgentResult, AgentType, CollaborationMode
from collaboration import TaskDecomposer
from collaboration.task_scheduler import TaskScheduler
from collaboration import ResultIntegrator
from agent_registry import AgentRegistry


class MasterAgent(BaseAgent):
    """主控Agent"""

    def __init__(self, agent_id: str = "master",
                 registry: Optional[AgentRegistry] = None):
        super().__init__(
            agent_id=agent_id,
            agent_type=AgentType.MASTER,
            capabilities=["task_decomposition", "coordination", "integration"]
        )
        self.registry = registry or AgentRegistry()
        self.decomposer = TaskDecomposer()
        self.scheduler = TaskScheduler(self.registry)
        self.integrator = ResultIntegrator()

    def process_task(self, task: AgentTask) -> AgentResult:
        """处理任务（MasterAgent的特殊实现）"""
        try:
            # 1. 分解任务
            subtasks = self.decomposer.decompose(
                task.input_data.get("request", ""),
                task.input_data.get("context", {})
            )

            # 2. 调度任务
            collaboration_mode = task.input_data.get(
                "collaboration_mode",
                CollaborationMode.SEQUENTIAL
            )
            assignment = self.scheduler.schedule(subtasks, collaboration_mode)

            # 3. 执行任务
            results = []
            for subtask in subtasks:
                agent = assignment.get(subtask.task_id)
                if agent:
                    result = self.scheduler.execute_task(subtask, agent)
                    results.append(result)

            # 4. 整合结果
            integration_strategy = task.input_data.get("integration_strategy", "merge")
            final_result = self.integrator.integrate(results, integration_strategy)

            return AgentResult(
                task_id=task.task_id,
                agent_id=self.agent_id,
                success=final_result["success"],
                output=final_result["output"],
                metadata=final_result,
                execution_time=final_result.get("total_time", 0)
            )

        except Exception as e:
            return AgentResult(
                task_id=task.task_id,
                agent_id=self.agent_id,
                success=False,
                output="",
                metadata={},
                execution_time=0,
                error_message=str(e)
            )

    def coordinate_agents(self, request: str,
                          mode: CollaborationMode = CollaborationMode.SEQUENTIAL) -> str:
        """协调多个Agent处理请求"""
        task = AgentTask(
            task_id="master_task",
            task_type="coordination",
            description=f"协调任务: {request}",
            required_capabilities=["coordination"],
            input_data={
                "request": request,
                "collaboration_mode": mode,
                "context": {}
            }
        )

        result = self.process_task(task)
        return result.output if result.success else f"执行失败: {result.error_message}"
```

### Step 9: 集成到现有系统

修改 `query_interface.py`，添加多Agent支持：

```python
# 在现有导入的基础上添加
from master_agent import MasterAgent
from agent_registry import AgentRegistry
from agents.agent_types import CollaborationMode

# 初始化多Agent系统
agent_registry = AgentRegistry()
master_agent = None


def initialize_multi_agent():
    """初始化多Agent系统"""
    global master_agent, agent_registry

    # 创建MasterAgent
    master_agent = MasterAgent(registry=agent_registry)

    # 注册专业Agent（后续实现）
    # code_agent = CodeAgent(...)
    # agent_registry.register(code_agent)

    agent_registry.register(master_agent)


# 在CLI命令中添加多Agent相关命令
def handle_multi_agent_command(command_parts):
    """处理多Agent相关命令"""
    if command_parts[0] == "/multi":
        if len(command_parts) < 2:
            console.print("[yellow]用法: /multi <请求> [模式][/yellow]")
            return

        request = " ".join(command_parts[1:])
        mode = CollaborationMode.SEQUENTIAL

        if len(command_parts) > 2:
            mode_str = command_parts[2].upper()
            try:
                mode = CollaborationMode[mode_str]
            except KeyError:
                console.print(f"[yellow]未知模式: {mode_str}，使用默认模式[/yellow]")

        result = master_agent.coordinate_agents(request, mode)
        console.print(f"[green]{result}[/green]")
```

---

## 🧪 测试指南

### 单元测试

创建测试文件 `tests/test_multi_agent.py`：

```python
import pytest
from agents.agent_types import AgentTask, CollaborationMode
from agents import BaseAgent
from agent_registry import AgentRegistry
from collaboration import TaskDecomposer
from collaboration.task_scheduler import TaskScheduler
from collaboration import ResultIntegrator


class TestBaseAgent:
    def test_agent_creation(self):
        agent = BaseAgent("test", None, ["test_capability"])
        assert agent.agent_id == "test"
        assert "test_capability" in agent.capabilities

    def test_can_handle(self):
        agent = BaseAgent("test", None, ["code", "test"])
        task = AgentTask(
            task_id="test_task",
            task_type="code",
            description="test",
            required_capabilities=["code"],
            input_data={}
        )
        assert agent.can_handle(task) is True


class TestAgentRegistry:
    def test_register_and_get(self):
        registry = AgentRegistry()
        agent = BaseAgent("agent1", None, ["test"])
        registry.register(agent)

        retrieved = registry.get_agent("agent1")
        assert retrieved is not None
        assert retrieved.agent_id == "agent1"

    def test_find_by_capability(self):
        registry = AgentRegistry()
        agent1 = BaseAgent("agent1", None, ["code", "test"])
        agent2 = BaseAgent("agent2", None, ["doc"])
        registry.register(agent1)
        registry.register(agent2)

        code_agents = registry.find_agents_by_capability("code")
        assert len(code_agents) == 1
        assert code_agents[0].agent_id == "agent1"


class TestTaskDecomposer:
    def test_simple_decomposition(self):
        decomposer = TaskDecomposer()
        tasks = decomposer.decompose("实现用户登录功能并编写测试")

        assert len(tasks) >= 2  # 至少包含代码和测试任务
        task_types = [task.task_type for task in tasks]
        assert "code_generation" in task_types or "code" in task_types
        assert "testing" in task_types or "test" in task_types


class TestResultIntegrator:
    def test_merge_results(self):
        integrator = ResultIntegrator()
        from agents.agent_types import AgentResult

        results = [
            AgentResult("task1", "agent1", True, "Result 1", {}, 1.0),
            AgentResult("task2", "agent2", True, "Result 2", {}, 2.0)
        ]

        integrated = integrator.integrate(results, "merge")
        assert integrated["success"] is True
        assert "Result 1" in integrated["output"]
        assert "Result 2" in integrated["output"]
```

### 集成测试

创建 `tests/test_multi_agent_integration.py`：

```python
import pytest
from master_agent import MasterAgent
from agent_registry import AgentRegistry
from agents.agent_types import CollaborationMode


class TestMultiAgentIntegration:
    def test_end_to_end_flow(self):
        registry = AgentRegistry()
        master = MasterAgent(registry=registry)

        # 测试简单任务
        result = master.coordinate_agents(
            "分析当前代码",
            CollaborationMode.SEQUENTIAL
        )

        assert result is not None
        assert isinstance(result, str)

    def test_collaboration_modes(self):
        registry = AgentRegistry()
        master = MasterAgent(registry=registry)

        modes = [
            CollaborationMode.SEQUENTIAL,
            CollaborationMode.PARALLEL,
            CollaborationMode.HIERARCHY
        ]

        for mode in modes:
            result = master.coordinate_agents("测试任务", mode)
            assert result is not None
```

---

## 🔧 调试指南

### 日志配置

在 `config.py` 中添加多Agent日志配置：

```python
# 多Agent系统日志配置
MULTI_AGENT_LOG_LEVEL = os.getenv("MULTI_AGENT_LOG_LEVEL", "INFO")
MULTI_AGENT_LOG_FILE = os.path.expanduser("~/.multi_agent.log")
```

### 调试技巧

1. **启用详细日志**:
```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

2. **监控Agent状态**:
```python
registry = AgentRegistry()
for agent in registry.get_all_agents():
    print(f"Agent: {agent.agent_id}, Capabilities: {agent.capabilities}")
```

3. **跟踪任务执行**:
```python
scheduler = TaskScheduler(registry)
# 在execute_task中添加日志
```

---

## 📚 最佳实践

1. **错误处理**: 始终处理Agent执行失败的情况
2. **超时控制**: 为每个任务设置合理的超时时间
3. **资源管理**: 限制并发Agent数量，避免资源耗尽
4. **日志记录**: 详细记录Agent间通信和任务执行
5. **测试覆盖**: 确保核心组件有充分的测试覆盖

---

## 🚀 性能优化建议

1. **Agent池化**: 复用Agent实例，避免频繁创建销毁
2. **异步执行**: 使用异步IO提高并发性能
3. **结果缓存**: 缓存相似任务的结果
4. **智能调度**: 基于历史数据优化任务分配

---

**实现指南结束**
