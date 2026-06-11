# 多Agent系统开发文档

## 📋 文档信息

- **文档版本**: v1.0
- **创建日期**: 2026-06-10
- **关联文档**: DESIGN.md, IMPLEMENTATION_GUIDE.md
- **目标读者**: 开发者、实施工程师

---

## 🚀 快速开始

### 开发环境准备

#### 1. 系统要求

- **操作系统**: macOS, Linux, Windows
- **Python版本**: Python 3.8+
- **内存**: 至少 8GB RAM（推荐 16GB）
- **存储**: 至少 10GB 可用空间
- **Ollama**: 已安装并运行 Ollama 服务

#### 2. 环境检查

```bash
# 检查Python版本
python --version  # 应该是 Python 3.8+

# 检查Ollama服务
ollama list      # 确保Ollama服务正常运行

# 检查项目依赖
pip list | grep -E "(llama-index|chromadb|ollama)"
```

#### 3. 依赖安装

```bash
# 进入项目目录
cd /Users/steve/PycharmProjects/ollama-qwen-coder-rag-lib-agent

# 安装基础依赖
pip install -r requirements.txt

# 安装多Agent系统新增依赖
pip install asyncio aiohttp pydantic
```

#### 4. 创建开发目录结构

```bash
# 创建必要的目录
mkdir -p agents collaboration tests/multi_agent

# 创建__init__.py文件
touch agents/__init__.py
touch collaboration/__init__.py
touch tests/multi_agent/__init__.py
```

---

## 📁 详细开发步骤

### 第一步：基础数据结构实现

#### 1.1 创建 agent_types.py

**文件路径**: `agents/agent_types.py`

```python
"""
多Agent系统基础数据类型定义
"""
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Callable
from enum import Enum
from datetime import datetime
import json

class CollaborationMode(Enum):
    """协作模式枚举"""
    HIERARCHY = "hierarchy"      # 层级协作
    PARALLEL = "parallel"        # 并行协作
    SEQUENTIAL = "sequential"   # 顺序协作
    COMPETITIVE = "competitive" # 竞争协作

    def __str__(self):
        return self.value

class AgentType(Enum):
    """Agent类型枚举"""
    MASTER = "master"
    CODE = "code"
    RAG = "rag"
    TEST = "test"
    DOC = "doc"
    AUDIT = "audit"

    def __str__(self):
        return self.value

class TaskStatus(Enum):
    """任务状态枚举"""
    PENDING = "pending"
    ASSIGNED = "assigned"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

class AgentState(Enum):
    """Agent状态枚举"""
    IDLE = "idle"
    BUSY = "busy"
    ERROR = "error"
    OFFLINE = "offline"

@dataclass
class AgentTask:
    """Agent任务定义"""
    task_id: str
    task_type: str
    description: str
    required_capabilities: List[str]
    input_data: Dict[str, Any]
    dependencies: List[str] = field(default_factory=list)
    priority: int = 5
    timeout: int = 300
    status: TaskStatus = TaskStatus.PENDING
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    assigned_agent: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    def to_dict(self) -> Dict:
        """转换为字典"""
        return {
            "task_id": self.task_id,
            "task_type": self.task_type,
            "description": self.description,
            "required_capabilities": self.required_capabilities,
            "input_data": self.input_data,
            "dependencies": self.dependencies,
            "priority": self.priority,
            "timeout": self.timeout,
            "status": self.status.value,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
            "assigned_agent": self.assigned_agent,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None
        }

    @classmethod
    def from_dict(cls, data: Dict) -> 'AgentTask':
        """从字典创建"""
        return cls(
            task_id=data["task_id"],
            task_type=data["task_type"],
            description=data["description"],
            required_capabilities=data["required_capabilities"],
            input_data=data["input_data"],
            dependencies=data.get("dependencies", []),
            priority=data.get("priority", 5),
            timeout=data.get("timeout", 300),
            status=TaskStatus(data.get("status", "pending")),
            metadata=data.get("metadata", {}),
            created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else datetime.now(),
            assigned_agent=data.get("assigned_agent"),
            started_at=datetime.fromisoformat(data["started_at"]) if data.get("started_at") else None,
            completed_at=datetime.fromisoformat(data["completed_at"]) if data.get("completed_at") else None
        )

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
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict:
        """转换为字典"""
        return {
            "task_id": self.task_id,
            "agent_id": self.agent_id,
            "success": self.success,
            "output": self.output,
            "metadata": self.metadata,
            "execution_time": self.execution_time,
            "error_message": self.error_message,
            "timestamp": self.timestamp.isoformat()
        }

@dataclass
class AgentMessage:
    """Agent间消息"""
    from_agent: str
    to_agent: str
    message_type: str
    content: Dict[str, Any]
    timestamp: datetime = field(default_factory=datetime.now)
    message_id: str = field(default_factory=lambda: f"msg_{datetime.now().timestamp()}")

    def to_dict(self) -> Dict:
        """转换为字典"""
        return {
            "message_id": self.message_id,
            "from_agent": self.from_agent,
            "to_agent": self.to_agent,
            "message_type": self.message_type,
            "content": self.content,
            "timestamp": self.timestamp.isoformat()
        }

@dataclass
class AgentConfig:
    """Agent配置"""
    agent_id: str
    agent_type: AgentType
    model: str
    host: str
    capabilities: List[str]
    specialized_tools: List[str]
    max_iterations: int = 50
    timeout: int = 300
    enabled: bool = True
    config_data: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        """转换为字典"""
        return {
            "agent_id": self.agent_id,
            "agent_type": self.agent_type.value,
            "model": self.model,
            "host": self.host,
            "capabilities": self.capabilities,
            "specialized_tools": self.specialized_tools,
            "max_iterations": self.max_iterations,
            "timeout": self.timeout,
            "enabled": self.enabled,
            "config_data": self.config_data
        }

@dataclass
class OrchestratorConfig:
    """编排器配置"""
    master_agent_config: AgentConfig
    agent_configs: List[AgentConfig]
    default_collaboration_mode: CollaborationMode
    max_parallel_tasks: int = 5
    task_timeout: int = 600
    enable_logging: bool = True
    log_level: str = "INFO"
    log_file: Optional[str] = None

    def to_dict(self) -> Dict:
        """转换为字典"""
        return {
            "master_agent_config": self.master_agent_config.to_dict(),
            "agent_configs": [config.to_dict() for config in self.agent_configs],
            "default_collaboration_mode": self.default_collaboration_mode.value,
            "max_parallel_tasks": self.max_parallel_tasks,
            "task_timeout": self.task_timeout,
            "enable_logging": self.enable_logging,
            "log_level": self.log_level,
            "log_file": self.log_file
        }
```

#### 1.2 单元测试

**文件路径**: `tests/multi_agent/test_agent_types.py`

```python
"""
测试基础数据类型
"""
import pytest
from datetime import datetime
from agents.agent_types import (
    CollaborationMode, AgentType, TaskStatus, AgentState,
    AgentTask, AgentResult, AgentMessage, AgentConfig, OrchestratorConfig
)

class TestAgentTypes:
    """测试Agent类型定义"""

    def test_collaboration_mode_enum(self):
        """测试协作模式枚举"""
        assert CollaborationMode.HIERARCHY.value == "hierarchy"
        assert CollaborationMode.PARALLEL.value == "parallel"
        assert len(CollaborationMode) == 4

    def test_agent_type_enum(self):
        """测试Agent类型枚举"""
        assert AgentType.MASTER.value == "master"
        assert AgentType.CODE.value == "code"
        assert len(AgentType) == 6

    def test_agent_task_creation(self):
        """测试Agent任务创建"""
        task = AgentTask(
            task_id="test_task",
            task_type="code_generation",
            description="Test task",
            required_capabilities=["code"],
            input_data={"test": "data"}
        )
        assert task.task_id == "test_task"
        assert task.status == TaskStatus.PENDING
        assert len(task.required_capabilities) == 1

    def test_agent_task_serialization(self):
        """测试Agent任务序列化"""
        task = AgentTask(
            task_id="test_task",
            task_type="code_generation",
            description="Test task",
            required_capabilities=["code"],
            input_data={"test": "data"}
        )
        
        # 转换为字典
        task_dict = task.to_dict()
        assert "task_id" in task_dict
        assert task_dict["status"] == "pending"
        
        # 从字典创建
        restored_task = AgentTask.from_dict(task_dict)
        assert restored_task.task_id == task.task_id
        assert restored_task.task_type == task.task_type

    def test_agent_result_creation(self):
        """测试Agent结果创建"""
        result = AgentResult(
            task_id="test_task",
            agent_id="test_agent",
            success=True,
            output="Test output",
            metadata={},
            execution_time=1.5
        )
        assert result.task_id == "test_task"
        assert result.success is True
        assert result.execution_time == 1.5

    def test_agent_message_creation(self):
        """测试Agent消息创建"""
        message = AgentMessage(
            from_agent="agent1",
            to_agent="agent2",
            message_type="test",
            content={"data": "test"}
        )
        assert message.from_agent == "agent1"
        assert message.to_agent == "agent2"
        assert message.message_id.startswith("msg_")

    def test_agent_config_creation(self):
        """测试Agent配置创建"""
        config = AgentConfig(
            agent_id="test_agent",
            agent_type=AgentType.CODE,
            model="qwen2.5-coder:7b",
            host="http://localhost:11434",
            capabilities=["code", "test"],
            specialized_tools=["code_analysis"]
        )
        assert config.agent_id == "test_agent"
        assert config.agent_type == AgentType.CODE
        assert config.enabled is True

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
```

#### 1.3 运行测试

```bash
# 运行基础数据类型测试
python -m pytest tests/multi_agent/test_agent_types.py -v

# 应该看到所有测试通过
```

---

### 第二步：Agent基类实现

#### 2.1 创建 base_agent.py

**文件路径**: `agents/base_agent.py`

```python
"""
Agent基类实现
"""
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, Callable
import time
import logging
import threading
from .agent_types import AgentTask, AgentResult, AgentMessage, AgentType, AgentState, AgentConfig

logger = logging.getLogger(__name__)

class BaseAgent(ABC):
    """Agent基类，所有专业Agent都应继承此类"""

    def __init__(self, config: AgentConfig):
        """
        初始化Agent
        
        Args:
            config: Agent配置
        """
        self.config = config
        self.agent_id = config.agent_id
        self.agent_type = config.agent_type
        self.capabilities = config.capabilities
        self.state = AgentState.IDLE
        self.message_handlers: Dict[str, Callable] = {}
        self.current_task: Optional[AgentTask] = None
        self.task_history: List[AgentResult] = []
        self._lock = threading.Lock()
        self._stop_event = threading.Event()

        # 初始化日志
        self._setup_logging()

    def _setup_logging(self):
        """设置Agent日志"""
        self.logger = logging.getLogger(f"Agent.{self.agent_id}")
        self.logger.setLevel(logging.INFO)

    @abstractmethod
    def process_task(self, task: AgentTask) -> AgentResult:
        """
        处理任务（子类必须实现）
        
        Args:
            task: 要处理的任务
            
        Returns:
            AgentResult: 处理结果
        """
        pass

    def can_handle(self, task: AgentTask) -> bool:
        """
        判断是否能处理该任务
        
        Args:
            task: 要检查的任务
            
        Returns:
            bool: 是否能处理
        """
        required = set(task.required_capabilities)
        available = set(self.capabilities)
        can_handle = required.issubset(available)
        
        self.logger.debug(
            f"Agent {self.agent_id} can handle task {task.task_id}: {can_handle}"
        )
        return can_handle

    def get_capability(self) -> List[str]:
        """获取能力列表"""
        return self.capabilities

    def get_state(self) -> AgentState:
        """获取Agent状态"""
        return self.state

    def register_message_handler(self, message_type: str, handler: Callable[[AgentMessage], None]):
        """
        注册消息处理器
        
        Args:
            message_type: 消息类型
            handler: 处理函数
        """
        self.message_handlers[message_type] = handler
        self.logger.info(f"Registered handler for message type: {message_type}")

    def handle_message(self, message: AgentMessage):
        """
        处理接收到的消息
        
        Args:
            message: 接收到的消息
        """
        self.logger.info(f"Received message from {message.from_agent}: {message.message_type}")
        
        handler = self.message_handlers.get(message.message_type)
        if handler:
            try:
                handler(message)
            except Exception as e:
                self.logger.error(f"Error handling message: {e}")
        else:
            self.logger.warning(f"No handler for message type: {message.message_type}")

    def execute_task(self, task: AgentTask) -> AgentResult:
        """
        执行任务（带状态管理）
        
        Args:
            task: 要执行的任务
            
        Returns:
            AgentResult: 执行结果
        """
        with self._lock:
            if self.state == AgentState.BUSY:
                self.logger.warning(f"Agent {self.agent_id} is busy, cannot accept new task")
                return AgentResult(
                    task_id=task.task_id,
                    agent_id=self.agent_id,
                    success=False,
                    output="Agent is busy",
                    metadata={},
                    execution_time=0,
                    error_message="Agent is busy"
                )

            self.state = AgentState.BUSY
            self.current_task = task
            task.status = TaskStatus.RUNNING
            task.started_at = time.time()

        try:
            self.logger.info(f"Starting task {task.task_id}")
            start_time = time.time()
            
            # 调用子类实现的处理方法
            result = self.process_task(task)
            
            execution_time = time.time() - start_time
            
            # 更新任务状态
            with self._lock:
                task.status = TaskStatus.COMPLETED if result.success else TaskStatus.FAILED
                task.completed_at = time.time()
                self.state = AgentState.IDLE
                self.current_task = None
                self.task_history.append(result)
            
            self.logger.info(
                f"Task {task.task_id} completed. Success: {result.success}, Time: {execution_time:.2f}s"
            )
            
            return result

        except Exception as e:
            execution_time = time.time() - task.started_at.timestamp() if task.started_at else 0
            
            error_result = AgentResult(
                task_id=task.task_id,
                agent_id=self.agent_id,
                success=False,
                output="",
                metadata={},
                execution_time=execution_time,
                error_message=str(e)
            )
            
            with self._lock:
                task.status = TaskStatus.FAILED
                task.completed_at = time.time()
                self.state = AgentState.ERROR
                self.current_task = None
                self.task_history.append(error_result)
            
            self.logger.error(f"Task {task.task_id} failed: {e}")
            return error_result

    def stop(self):
        """停止Agent"""
        self._stop_event.set()
        with self._lock:
            if self.state == AgentState.BUSY and self.current_task:
                self.current_task.status = TaskStatus.CANCELLED
                self.current_task.completed_at = time.time()
            self.state = AgentState.OFFLINE
            self.current_task = None

    def reset(self):
        """重置Agent状态"""
        self._stop_event.clear()
        with self._lock:
            self.state = AgentState.IDLE
            self.current_task = None

    def get_task_history(self, limit: int = 10) -> List[AgentResult]:
        """
       获取任务历史
        
        Args:
            limit: 返回的历史记录数量限制
            
        Returns:
            List[AgentResult]: 任务历史
        """
        return self.task_history[-limit:]

    def get_status(self) -> Dict[str, Any]:
        """
        获取Agent状态信息
        
        Returns:
            Dict: 状态信息字典
        """
        return {
            "agent_id": self.agent_id,
            "agent_type": self.agent_type.value,
            "state": self.state.value,
            "capabilities": self.capabilities,
            "current_task": self.current_task.to_dict() if self.current_task else None,
            "task_count": len(self.task_history),
            "success_rate": self._calculate_success_rate()
        }

    def _calculate_success_rate(self) -> float:
        """计算任务成功率"""
        if not self.task_history:
            return 0.0
        
        successful = sum(1 for result in self.task_history if result.success)
        return successful / len(self.task_history)

    def __repr__(self) -> str:
        return f"BaseAgent(id={self.agent_id}, type={self.agent_type.value}, state={self.state.value})"
```

#### 2.2 单元测试

**文件路径**: `tests/multi_agent/test_base_agent.py`

```python
"""
测试Agent基类
"""
import pytest
import time
from agents.agent_types import (
    AgentTask, AgentResult, AgentConfig, AgentType, TaskStatus, AgentState
)
from agents.base_agent import BaseAgent

class MockAgent(BaseAgent):
    """用于测试的Mock Agent"""

    def process_task(self, task: AgentTask) -> AgentResult:
        """简单的任务处理实现"""
        if "fail" in task.description.lower():
            raise Exception("Task failed as requested")
        
        return AgentResult(
            task_id=task.task_id,
            agent_id=self.agent_id,
            success=True,
            output=f"Processed task: {task.description}",
            metadata={},
            execution_time=0.1
        )

class TestBaseAgent:
    """测试Agent基类"""

    @pytest.fixture
    def agent_config(self):
        """创建测试用的Agent配置"""
        return AgentConfig(
            agent_id="test_agent",
            agent_type=AgentType.CODE,
            model="qwen2.5-coder:7b",
            host="http://localhost:11434",
            capabilities=["code", "test"],
            specialized_tools=[]
        )

    @pytest.fixture
    def agent(self, agent_config):
        """创建测试用的Agent实例"""
        return MockAgent(agent_config)

    @pytest.fixture
    def sample_task(self):
        """创建测试用的任务"""
        return AgentTask(
            task_id="test_task",
            task_type="code_generation",
            description="Test task",
            required_capabilities=["code"],
            input_data={}
        )

    def test_agent_creation(self, agent):
        """测试Agent创建"""
        assert agent.agent_id == "test_agent"
        assert agent.agent_type == AgentType.CODE
        assert agent.state == AgentState.IDLE
        assert "code" in agent.capabilities

    def test_can_handle(self, agent, sample_task):
        """测试任务处理能力判断"""
        assert agent.can_handle(sample_task) is True
        
        # 测试不能处理的任务
        sample_task.required_capabilities = ["unknown_capability"]
        assert agent.can_handle(sample_task) is False

    def test_execute_task_success(self, agent, sample_task):
        """测试成功执行任务"""
        result = agent.execute_task(sample_task)
        
        assert result.success is True
        assert result.agent_id == "test_agent"
        assert agent.state == AgentState.IDLE
        assert len(agent.task_history) == 1

    def test_execute_task_failure(self, agent, sample_task):
        """测试任务执行失败"""
        sample_task.description = "fail this task"
        result = agent.execute_task(sample_task)
        
        assert result.success is False
        assert "Task failed as requested" in result.error_message
        assert agent.state == AgentState.ERROR

    def test_agent_state_management(self, agent, sample_task):
        """测试Agent状态管理"""
        # 初始状态
        assert agent.state == AgentState.IDLE
        
        # 执行任务时的状态
        def delayed_execution():
            time.sleep(0.1)
            agent.process_task(sample_task)
        
        import threading
        thread = threading.Thread(target=delayed_execution)
        thread.start()
        time.sleep(0.05)
        
        # 任务执行中应该是BUSY状态
        assert agent.state == AgentState.BUSY
        
        thread.join()
        # 任务完成后应该是IDLE状态
        assert agent.state == AgentState.IDLE

    def test_message_handling(self, agent):
        """测试消息处理"""
        received_messages = []
        
        def test_handler(message):
            received_messages.append(message)
        
        agent.register_message_handler("test", test_handler)
        
        from agents.agent_types import AgentMessage
        message = AgentMessage(
            from_agent="other_agent",
            to_agent="test_agent",
            message_type="test",
            content={"data": "test"}
        )
        
        agent.handle_message(message)
        
        assert len(received_messages) == 1
        assert received_messages[0].message_type == "test"

    def test_task_history(self, agent, sample_task):
        """测试任务历史记录"""
        # 执行多个任务
        for i in range(5):
            task = AgentTask(
                task_id=f"task_{i}",
                task_type="test",
                description=f"Task {i}",
                required_capabilities=["code"],
                input_data={}
            )
            agent.execute_task(task)
        
        history = agent.get_task_history(limit=3)
        assert len(history) == 3
        assert history[0].task_id == "task_2"  # 最后3个任务

    def test_get_status(self, agent, sample_task):
        """测试获取状态信息"""
        agent.execute_task(sample_task)
        
        status = agent.get_status()
        assert status["agent_id"] == "test_agent"
        assert status["state"] == "idle"
        assert status["task_count"] == 1
        assert status["success_rate"] == 1.0

    def test_stop_and_reset(self, agent, sample_task):
        """测试停止和重置"""
        agent.execute_task(sample_task)
        assert agent.state == AgentState.IDLE
        
        agent.stop()
        assert agent.state == AgentState.OFFLINE
        
        agent.reset()
        assert agent.state == AgentState.IDLE

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
```

#### 2.3 运行测试

```bash
# 运行Agent基类测试
python -m pytest tests/multi_agent/test_base_agent.py -v

# 应该看到所有测试通过
```

---

### 第三步：消息总线实现

#### 3.1 创建 message_bus.py

**文件路径**: `collaboration/message_bus.py`

```python
"""
消息总线实现 - Agent间通信机制
"""
from collections import defaultdict
from queue import Queue, Empty
from threading import Lock, Thread
from typing import Callable, Dict, List, Optional
import logging
import time
from agents.agent_types import AgentMessage

logger = logging.getLogger(__name__)

class MessageBus:
    """
    Agent间通信消息总线
    
    功能：
    - 发布/订阅模式
    - 点对点消息
    - 广播消息
    - 消息持久化（可选）
    """

    def __init__(self, enable_persistence: bool = False, persistence_file: Optional[str] = None):
        """
        初始化消息总线
        
        Args:
            enable_persistence: 是否启用消息持久化
            persistence_file: 持久化文件路径
        """
        self.subscribers: Dict[str, List[Callable]] = defaultdict(list)
        self.message_queue = Queue()
        self.lock = Lock()
        self.enable_persistence = enable_persistence
        self.persistence_file = persistence_file
        self.message_history: List[AgentMessage] = []
        self._running = False
        self._worker_thread: Optional[Thread] = None

        if self.enable_persistence and persistence_file:
            self._load_persisted_messages()

        logger.info("MessageBus initialized")

    def subscribe(self, agent_id: str, callback: Callable[[AgentMessage], None]):
        """
        Agent订阅消息
        
        Args:
            agent_id: Agent ID
            callback: 消息处理回调函数
        """
        with self.lock:
            self.subscribers[agent_id].append(callback)
            logger.info(f"Agent {agent_id} subscribed to message bus")

    def unsubscribe(self, agent_id: str, callback: Callable):
        """
        取消订阅
        
        Args:
            agent_id: Agent ID
            callback: 要取消的回调函数
        """
        with self.lock:
            if callback in self.subscribers[agent_id]:
                self.subscribers[agent_id].remove(callback)
                logger.info(f"Agent {agent_id} unsubscribed from message bus")

    def publish(self, message: AgentMessage):
        """
        发布消息（点对点）
        
        Args:
            message: 要发布的消息
        """
        with self.lock:
            self.message_history.append(message)
            if self.enable_persistence:
                self._persist_message(message)

        # 将消息放入队列进行处理
        self.message_queue.put(message)
        logger.debug(f"Message published: {message.message_id} from {message.from_agent} to {message.to_agent}")

    def send_direct(self, from_agent: str, to_agent: str, 
                   message_type: str, content: Dict) -> str:
        """
        点对点发送消息
        
        Args:
            from_agent: 发送者Agent ID
            to_agent: 接收者Agent ID
            message_type: 消息类型
            content: 消息内容
            
        Returns:
            str: 消息ID
        """
        message = AgentMessage(
            from_agent=from_agent,
            to_agent=to_agent,
            message_type=message_type,
            content=content,
            timestamp=time.time()
        )
        
        self.publish(message)
        return message.message_id

    def broadcast(self, from_agent: str, message_type: str, content: Dict):
        """
        广播消息给所有订阅者（除了发送者）
        
        Args:
            from_agent: 发送者Agent ID
            message_type: 消息类型
            content: 消息内容
        """
        with self.lock:
            subscribers = list(self.subscribers.keys())
        
        for agent_id in subscribers:
            if agent_id != from_agent:
                message = AgentMessage(
                    from_agent=from_agent,
                    to_agent=agent_id,
                    message_type=message_type,
                    content=content,
                    timestamp=time.time()
                )
                self.publish(message)
        
        logger.info(f"Broadcast message from {from_agent} to {len(subscribers)-1} subscribers")

    def start(self):
        """启动消息处理线程"""
        if self._running:
            logger.warning("MessageBus is already running")
            return
        
        self._running = True
        self._worker_thread = Thread(target=self._process_messages, daemon=True)
        self._worker_thread.start()
        logger.info("MessageBus worker thread started")

    def stop(self):
        """停止消息处理线程"""
        if not self._running:
            return
        
        self._running = False
        if self._worker_thread:
            self._worker_thread.join(timeout=5.0)
        logger.info("MessageBus stopped")

    def _process_messages(self):
        """消息处理工作线程"""
        while self._running:
            try:
                message = self.message_queue.get(timeout=1.0)
                self._deliver_message(message)
            except Empty:
                continue
            except Exception as e:
                logger.error(f"Error processing message: {e}")

    def _deliver_message(self, message: AgentMessage):
        """投递消息给订阅者"""
        with self.lock:
            callbacks = self.subscribers.get(message.to_agent, []).copy()
        
        for callback in callbacks:
            try:
                callback(message)
            except Exception as e:
                logger.error(f"Error in message handler for {message.to_agent}: {e}")

    def _persist_message(self, message: AgentMessage):
        """持久化消息"""
        if self.persistence_file:
            try:
                import json
                with open(self.persistence_file, 'a') as f:
                    f.write(json.dumps(message.to_dict()) + '\n')
            except Exception as e:
                logger.error(f"Error persisting message: {e}")

    def _load_persisted_messages(self):
        """加载持久化的消息"""
        if self.persistence_file:
            try:
                import json
                if os.path.exists(self.persistence_file):
                    with open(self.persistence_file, 'r') as f:
                        for line in f:
                            if line.strip():
                                message_dict = json.loads(line)
                                message = AgentMessage(
                                    from_agent=message_dict["from_agent"],
                                    to_agent=message_dict["to_agent"],
                                    message_type=message_dict["message_type"],
                                    content=message_dict["content"],
                                    timestamp=datetime.fromisoformat(message_dict["timestamp"])
                                )
                                self.message_history.append(message)
            except Exception as e:
                logger.error(f"Error loading persisted messages: {e}")

    def get_message_history(self, limit: int = 100) -> List[AgentMessage]:
        """
        获取消息历史
        
        Args:
            limit: 返回的消息数量限制
            
        Returns:
            List[AgentMessage]: 消息历史
        """
        return self.message_history[-limit:]

    def get_statistics(self) -> Dict:
        """
        获取消息总线统计信息
        
        Returns:
            Dict: 统计信息
        """
        with self.lock:
            return {
                "total_subscribers": len(self.subscribers),
                "total_messages": len(self.message_history),
                "queue_size": self.message_queue.qsize(),
                "subscribers": {
                    agent_id: len(callbacks) 
                    for agent_id, callbacks in self.subscribers.items()
                }
            }

    def clear_history(self):
        """清空消息历史"""
        with self.lock:
            self.message_history.clear()
        logger.info("Message history cleared")
```

#### 3.2 单元测试

**文件路径**: `tests/multi_agent/test_message_bus.py`

```python
"""
测试消息总线
"""
import pytest
import time
import threading
from agents.agent_types import AgentMessage
from collaboration.message_bus import MessageBus

class TestMessageBus:
    """测试消息总线"""

    @pytest.fixture
    def message_bus(self):
        """创建消息总线实例"""
        bus = MessageBus()
        bus.start()
        yield bus
        bus.stop()

    def test_subscribe_unsubscribe(self, message_bus):
        """测试订阅和取消订阅"""
        received_messages = []
        
        def handler(message):
            received_messages.append(message)
        
        message_bus.subscribe("agent1", handler)
        assert "agent1" in message_bus.subscribers
        
        message_bus.unsubscribe("agent1", handler)
        # 应该没有处理器了
        assert len(message_bus.subscribers.get("agent1", [])) == 0

    def test_publish_and_receive(self, message_bus):
        """测试消息发布和接收"""
        received_messages = []
        
        def handler(message):
            received_messages.append(message)
        
        message_bus.subscribe("agent1", handler)
        
        message = AgentMessage(
            from_agent="agent2",
            to_agent="agent1",
            message_type="test",
            content={"data": "test"}
        )
        
        message_bus.publish(message)
        
        # 等待消息被处理
        time.sleep(0.1)
        
        assert len(received_messages) == 1
        assert received_messages[0].message_type == "test"

    def test_send_direct(self, message_bus):
        """测试点对点发送"""
        received_messages = []
        
        def handler(message):
            received_messages.append(message)
        
        message_bus.subscribe("agent1", handler)
        
        message_id = message_bus.send_direct(
            from_agent="agent2",
            to_agent="agent1",
            message_type="direct_test",
            content={"key": "value"}
        )
        
        # 等待消息被处理
        time.sleep(0.1)
        
        assert len(received_messages) == 1
        assert received_messages[0].message_type == "direct_test"
        assert received_messages[0].content["key"] == "value"

    def test_broadcast(self, message_bus):
        """测试广播消息"""
        received_count = {"agent1": 0, "agent2": 0, "agent3": 0}
        
        def handler1(message):
            received_count["agent1"] += 1
        
        def handler2(message):
            received_count["agent2"] += 1
        
        def handler3(message):
            received_count["agent3"] += 1
        
        message_bus.subscribe("agent1", handler1)
        message_bus.subscribe("agent2", handler2)
        message_bus.subscribe("agent3", handler3)
        
        message_bus.broadcast("agent1", "broadcast_test", {"data": "test"})
        
        # 等待消息被处理
        time.sleep(0.1)
        
        # agent1不应该收到自己的广播
        assert received_count["agent1"] == 0
        assert received_count["agent2"] == 1
        assert received_count["agent3"] == 1

    def test_message_history(self, message_bus):
        """测试消息历史"""
        message_bus.subscribe("agent1", lambda m: None)
        
        for i in range(5):
            message_bus.send_direct(
                from_agent="agent2",
                to_agent="agent1",
                message_type=f"test_{i}",
                content={"index": i}
            )
        
        time.sleep(0.2)
        
        history = message_bus.get_message_history(limit=3)
        assert len(history) == 3

    def test_statistics(self, message_bus):
        """测试统计信息"""
        message_bus.subscribe("agent1", lambda m: None)
        message_bus.subscribe("agent2", lambda m: None)
        
        stats = message_bus.get_statistics()
        assert stats["total_subscribers"] == 2
        assert "agent1" in stats["subscribers"]
        assert "agent2" in stats["subscribers"]

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
```

#### 3.3 运行测试

```bash
# 运行消息总线测试
python -m pytest tests/multi_agent/test_message_bus.py -v

# 应该看到所有测试通过
```

---

### 第四步：Agent注册中心实现

#### 4.1 创建 agent_registry.py

**文件路径**: `agent_registry.py`

```python
"""
Agent注册中心实现
"""
from typing import Dict, List, Optional
import logging
from agents.base_agent import BaseAgent
from agents.agent_types import AgentType

logger = logging.getLogger(__name__)

class AgentRegistry:
    """
    Agent注册中心
    
    功能：
    - Agent注册和注销
    - 按ID查找Agent
    - 按能力查找Agent
    - 按类型查找Agent
    - 状态监控
    """

    def __init__(self):
        """初始化注册中心"""
        self.agents: Dict[str, BaseAgent] = {}
        self.capabilities_index: Dict[str, List[str]] = {}
        self.type_index: Dict[AgentType, List[str]] = {}
        self._lock = threading.Lock()
        logger.info("AgentRegistry initialized")

    def register(self, agent: BaseAgent) -> bool:
        """
        注册Agent
        
        Args:
            agent: 要注册的Agent实例
            
        Returns:
            bool: 注册是否成功
        """
        with self._lock:
            if agent.agent_id in self.agents:
                logger.warning(f"Agent {agent.agent_id} already registered")
                return False
            
            self.agents[agent.agent_id] = agent
            
            # 更新能力索引
            for capability in agent.capabilities:
                if capability not in self.capabilities_index:
                    self.capabilities_index[capability] = []
                self.capabilities_index[capability].append(agent.agent_id)
            
            # 更新类型索引
            if agent.agent_type not in self.type_index:
                self.type_index[agent.agent_type] = []
            self.type_index[agent.agent_type].append(agent.agent_id)
            
            logger.info(f"Agent {agent.agent_id} registered successfully")
            return True

    def unregister(self, agent_id: str) -> bool:
        """
        注销Agent
        
        Args:
            agent_id: 要注销的Agent ID
            
        Returns:
            bool: 注销是否成功
        """
        with self._lock:
            if agent_id not in self.agents:
                logger.warning(f"Agent {agent_id} not found")
                return False
            
            agent = self.agents[agent_id]
            
            # 更新能力索引
            for capability in agent.capabilities:
                if capability in self.capabilities_index:
                    self.capabilities_index[capability].remove(agent_id)
                    if not self.capabilities_index[capability]:
                        del self.capabilities_index[capability]
            
            # 更新类型索引
            if agent.agent_type in self.type_index:
                self.type_index[agent.agent_type].remove(agent_id)
                if not self.type_index[agent.agent_type]:
                    del self.type_index[agent.agent_type]
            
            del self.agents[agent_id]
            logger.info(f"Agent {agent_id} unregistered successfully")
            return True

    def get_agent(self, agent_id: str) -> Optional[BaseAgent]:
        """
        获取Agent实例
        
        Args:
            agent_id: Agent ID
            
        Returns:
            Optional[BaseAgent]: Agent实例，如果不存在返回None
        """
        return self.agents.get(agent_id)

    def find_agents_by_capability(self, capability: str) -> List[BaseAgent]:
        """
        根据能力查找Agent
        
        Args:
            capability: 能力名称
            
        Returns:
            List[BaseAgent]: 匹配的Agent列表
        """
        agent_ids = self.capabilities_index.get(capability, [])
        agents = []
        
        with self._lock:
            for agent_id in agent_ids:
                if agent_id in self.agents:
                    agents.append(self.agents[agent_id])
        
        return agents

    def find_agents_by_type(self, agent_type: AgentType) -> List[BaseAgent]:
        """
        根据类型查找Agent
        
        Args:
            agent_type: Agent类型
            
        Returns:
            List[BaseAgent]: 匹配的Agent列表
        """
        agent_ids = self.type_index.get(agent_type, [])
        agents = []
        
        with self._lock:
            for agent_id in agent_ids:
                if agent_id in self.agents:
                    agents.append(self.agents[agent_id])
        
        return agents

    def get_all_agents(self) -> List[BaseAgent]:
        """
        获取所有Agent
        
        Returns:
            List[BaseAgent]: 所有Agent列表
        """
        with self._lock:
            return list(self.agents.values())

    def get_agent_count(self) -> int:
        """
        获取Agent数量
        
        Returns:
            int: Agent数量
        """
        with self._lock:
            return len(self.agents)

    def get_all_capabilities(self) -> List[str]:
        """
        获取所有能力列表
        
        Returns:
            List[str]: 能力列表
        """
        with self._lock:
            return list(self.capabilities_index.keys())

    def get_statistics(self) -> Dict:
        """
        获取注册中心统计信息
        
        Returns:
            Dict: 统计信息
        """
        with self._lock:
            agent_states = {}
            for agent in self.agents.values():
                status = agent.get_status()
                agent_states[agent.agent_id] = status["state"]
            
            return {
                "total_agents": len(self.agents),
                "total_capabilities": len(self.capabilities_index),
                "capabilities": self.capabilities_index,
                "agent_states": agent_states,
                "agents_by_type": {
                    agent_type.value: len(agent_ids)
                    for agent_type, agent_ids in self.type_index.items()
                }
            }

    def shutdown_all(self):
        """关闭所有Agent"""
        with self._lock:
            for agent in self.agents.values():
                try:
                    agent.stop()
                except Exception as e:
                    logger.error(f"Error stopping agent {agent.agent_id}: {e}")
        
        logger.info("All agents shut down")
```

#### 4.2 单元测试

**文件路径**: `tests/multi_agent/test_agent_registry.py`

```python
"""
测试Agent注册中心
"""
import pytest
from agents.agent_types import AgentConfig, AgentType
from agents.base_agent import BaseAgent
from agent_registry import AgentRegistry

class MockAgent(BaseAgent):
    """用于测试的Mock Agent"""
    def process_task(self, task):
        from agents.agent_types import AgentResult
        return AgentResult(
            task_id=task.task_id,
            agent_id=self.agent_id,
            success=True,
            output="Mock result",
            metadata={},
            execution_time=0.1
        )

class TestAgentRegistry:
    """测试Agent注册中心"""

    @pytest.fixture
    def registry(self):
        """创建注册中心实例"""
        return AgentRegistry()

    @pytest.fixture
    def mock_agent(self):
        """创建Mock Agent"""
        config = AgentConfig(
            agent_id="test_agent",
            agent_type=AgentType.CODE,
            model="qwen2.5-coder:7b",
            host="http://localhost:11434",
            capabilities=["code", "test"],
            specialized_tools=[]
        )
        return MockAgent(config)

    def test_register_and_get(self, registry, mock_agent):
        """测试注册和获取"""
        # 注册
        result = registry.register(mock_agent)
        assert result is True
        
        # 获取
        retrieved = registry.get_agent("test_agent")
        assert retrieved is not None
        assert retrieved.agent_id == "test_agent"

    def test_register_duplicate(self, registry, mock_agent):
        """测试重复注册"""
        registry.register(mock_agent)
        
        # 尝试重复注册
        result = registry.register(mock_agent)
        assert result is False

    def test_unregister(self, registry, mock_agent):
        """测试注销"""
        registry.register(mock_agent)
        
        # 注销
        result = registry.unregister("test_agent")
        assert result is True
        
        # 确认已删除
        retrieved = registry.get_agent("test_agent")
        assert retrieved is None

    def test_find_by_capability(self, registry):
        """测试按能力查找"""
        # 创建多个Agent
        config1 = AgentConfig(
            agent_id="agent1",
            agent_type=AgentType.CODE,
            model="qwen2.5-coder:7b",
            host="http://localhost:11434",
            capabilities=["code", "test"],
            specialized_tools=[]
        )
        config2 = AgentConfig(
            agent_id="agent2",
            agent_type=AgentType.TEST,
            model="qwen2.5-coder:7b",
            host="http://localhost:11434",
            capabilities=["test", "debug"],
            specialized_tools=[]
        )
        
        agent1 = MockAgent(config1)
        agent2 = MockAgent(config2)
        
        registry.register(agent1)
        registry.register(agent2)
        
        # 查找具有code能力的Agent
        code_agents = registry.find_agents_by_capability("code")
        assert len(code_agents) == 1
        assert code_agents[0].agent_id == "agent1"
        
        # 查找具有test能力的Agent
        test_agents = registry.find_agents_by_capability("test")
        assert len(test_agents) == 2

    def test_find_by_type(self, registry):
        """测试按类型查找"""
        config1 = AgentConfig(
            agent_id="agent1",
            agent_type=AgentType.CODE,
            model="qwen2.5-coder:7b",
            host="http://localhost:11434",
            capabilities=["code"],
            specialized_tools=[]
        )
        config2 = AgentConfig(
            agent_id="agent2",
            agent_type=AgentType.CODE,
            model="qwen2.5-coder:7b",
            host="http://localhost:11434",
            capabilities=["code"],
            specialized_tools=[]
        )
        
        agent1 = MockAgent(config1)
        agent2 = MockAgent(config2)
        
        registry.register(agent1)
        registry.register(agent2)
        
        code_agents = registry.find_agents_by_type(AgentType.CODE)
        assert len(code_agents) == 2

    def test_statistics(self, registry, mock_agent):
        """测试统计信息"""
        registry.register(mock_agent)
        
        stats = registry.get_statistics()
        assert stats["total_agents"] == 1
        assert stats["total_capabilities"] == 2
        assert "test_agent" in stats["agent_states"]

    def test_shutdown_all(self, registry):
        """测试关闭所有Agent"""
        config = AgentConfig(
            agent_id="agent1",
            agent_type=AgentType.CODE,
            model="qwen2.5-coder:7b",
            host="http://localhost:11434",
            capabilities=["code"],
            specialized_tools=[]
        )
        agent = MockAgent(config)
        registry.register(agent)
        
        registry.shutdown_all()
        
        # 验证Agent已停止
        assert agent.state.value == "offline"

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
```

#### 4.3 运行测试

```bash
# 运行Agent注册中心测试
python -m pytest tests/multi_agent/test_agent_registry.py -v

# 应该看到所有测试通过
```

---

### 第五步：任务分解器实现

#### 5.1 创建 task_decomposer.py

**文件路径**: `collaboration/task_decomposer.py`

```python
"""
任务分解器实现
"""
from typing import List, Dict, Tuple
import re
import logging
from agents.agent_types import AgentTask, CollaborationMode

logger = logging.getLogger(__name__)

class TaskDecomposer:
    """
    任务分解器
    
    功能：
    - 将复杂任务分解为子任务
    - 检测任务依赖关系
    - 评估任务复杂度
    - 优化任务分解策略
    """

    def __init__(self):
        """初始化任务分解器"""
        # 任务类型识别模式
        self.decomposition_patterns = {
            "code_generation": [
                r"实现|开发|编写|创建|generate|implement|develop|write",
                r"函数|类|模块|功能|function|class|module"
            ],
            "testing": [
                r"测试|单元测试|集成测试|test|unittest|integration",
                r"验证|检查|verify|check"
            ],
            "documentation": [
                r"文档|说明|指南|document|doc|guide|readme",
                r"生成.*文档|generate.*doc"
            ],
            "analysis": [
                r"分析|评估|审查|analyze|review|audit",
                r"优化|重构|optimize|refactor"
            ],
            "debugging": [
                r"调试|debug|修复|fix|bug",
                r"错误|异常|error|exception"
            ]
        }

        # 依赖关系规则
        self.dependency_rules = {
            "testing": ["code_generation"],
            "documentation": ["code_generation"],
            "deployment": ["testing", "documentation"]
        }

        logger.info("TaskDecomposer initialized")

    def decompose(self, request: str, context: Dict = None) -> List[AgentTask]:
        """
        分解复杂任务为子任务
        
        Args:
            request: 用户请求
            context: 上下文信息
            
        Returns:
            List[AgentTask]: 分解后的子任务列表
        """
        context = context or {}
        tasks = []
        
        logger.info(f"Decomposing request: {request}")
        
        # 分析请求，识别需要的任务类型
        detected_types = self._detect_task_types(request)
        logger.info(f"Detected task types: {detected_types}")
        
        # 为每种类型创建任务
        for task_type in detected_types:
            task = self._create_task_by_type(task_type, request, context)
            if task:
                tasks.append(task)
        
        # 设置任务依赖关系
        self._set_dependencies(tasks)
        
        # 如果没有检测到任何任务类型，创建通用任务
        if not tasks:
            logger.warning("No specific task types detected, creating generic task")
            tasks.append(self._create_generic_task(request, context))
        
        logger.info(f"Decomposed into {len(tasks)} tasks")
        return tasks

    def _detect_task_types(self, request: str) -> List[str]:
        """
        检测请求中包含的任务类型
        
        Args:
            request: 用户请求
            
        Returns:
            List[str]: 检测到的任务类型列表
        """
        detected = []
        
        for task_type, patterns in self.decomposition_patterns.items():
            for pattern in patterns:
                if re.search(pattern, request, re.IGNORECASE):
                    if task_type not in detected:
                        detected.append(task_type)
                    break
        
        return detected

    def _create_task_by_type(self, task_type: str, request: str, context: Dict) -> AgentTask:
        """
        根据任务类型创建任务
        
        Args:
            task_type: 任务类型
            request: 用户请求
            context: 上下文信息
            
        Returns:
            AgentTask: 创建的任务
        """
        task_id = f"{task_type}_{hash(request) % 10000}"
        
        task_configs = {
            "code_generation": {
                "description": f"代码生成: {request}",
                "required_capabilities": ["code_generation", "file_operations"],
                "priority": 7
            },
            "testing": {
                "description": f"测试: {request}",
                "required_capabilities": ["testing", "code_analysis"],
                "priority": 6,
                "dependencies": ["code_generation"]
            },
            "documentation": {
                "description": f"文档: {request}",
                "required_capabilities": ["documentation", "writing"],
                "priority": 5,
                "dependencies": ["code_generation"]
            },
            "analysis": {
                "description": f"分析: {request}",
                "required_capabilities": ["analysis", "code_review"],
                "priority": 6
            },
            "debugging": {
                "description": f"调试: {request}",
                "required_capabilities": ["debugging", "code_analysis"],
                "priority": 8
            }
        }
        
        config = task_configs.get(task_type, {})
        
        return AgentTask(
            task_id=task_id,
            task_type=task_type,
            description=config.get("description", f"{task_type}: {request}"),
            required_capabilities=config.get("required_capabilities", ["general"]),
            input_data={
                "request": request,
                "context": context,
                "task_type": task_type
            },
            dependencies=config.get("dependencies", []),
            priority=config.get("priority", 5),
            timeout=self._estimate_timeout(task_type)
        )

    def _create_generic_task(self, request: str, context: Dict) -> AgentTask:
        """
        创建通用任务
        
        Args:
            request: 用户请求
            context: 上下文信息
            
        Returns:
            AgentTask: 通用任务
        """
        return AgentTask(
            task_id=f"generic_{hash(request) % 10000}",
            task_type="generic",
            description=f"通用任务: {request}",
            required_capabilities=["general"],
            input_data={"request": request, "context": context},
            priority=5,
            timeout=300
        )

    def _set_dependencies(self, tasks: List[AgentTask]):
        """
        设置任务间的依赖关系
        
        Args:
            tasks: 任务列表
        """
        # 创建任务ID到任务的映射
        task_map = {task.task_type: task for task in tasks}
        
        for task in tasks:
            # 根据规则设置依赖
            for task_type, deps in self.dependency_rules.items():
                if task.task_type == task_type:
                    for dep_type in deps:
                        if dep_type in task_map:
                            dep_task_id = task_map[dep_type].task_id
                            if dep_task_id not in task.dependencies:
                                task.dependencies.append(dep_task_id)

    def _estimate_timeout(self, task_type: str) -> int:
        """
        估算任务超时时间（秒）
        
        Args:
            task_type: 任务类型
            
        Returns:
            int: 超时时间（秒）
        """
        timeout_map = {
            "code_generation": 600,
            "testing": 300,
            "documentation": 200,
            "analysis": 400,
            "debugging": 500,
            "generic": 300
        }
        return timeout_map.get(task_type, 300)

    def detect_dependencies(self, tasks: List[AgentTask]) -> Dict[str, List[str]]:
        """
        检测任务依赖关系
        
        Args:
            tasks: 任务列表
            
        Returns:
            Dict[str, List[str]]: 依赖关系映射
        """
        dependency_map = {}
        for task in tasks:
            dependency_map[task.task_id] = task.dependencies
        return dependency_map

    def estimate_complexity(self, task: AgentTask) -> int:
        """
        评估任务复杂度（1-10）
        
        Args:
            task: 要评估的任务
            
        Returns:
            int: 复杂度评分
        """
        # 基于任务类型的基础复杂度
        base_complexity = {
            "code_generation": 7,
            "testing": 5,
            "documentation": 4,
            "analysis": 6,
            "debugging": 8,
            "generic": 5
        }
        
        complexity = base_complexity.get(task.task_type, 5)
        
        # 根据依赖数量调整
        complexity += len(task.dependencies) * 0.5
        
        # 根据优先级调整
        complexity += (task.priority - 5) * 0.3
        
        # 确保在1-10范围内
        return max(1, min(10, int(complexity)))

    def optimize_task_order(self, tasks: List[AgentTask]) -> List[AgentTask]:
        """
        优化任务执行顺序
        
        Args:
            tasks: 任务列表
            
        Returns:
            List[AgentTask]: 优化后的任务列表
        """
        # 拓扑排序
        return self._topological_sort(tasks)

    def _topological_sort(self, tasks: List[AgentTask]) -> List[AgentTask]:
        """
        拓扑排序（基于依赖关系）
        
        Args:
            tasks: 任务列表
            
        Returns:
            List[AgentTask]: 排序后的任务列表
        """
        task_map = {task.task_id: task for task in tasks}
        in_degree = {task.task_id: len(task.dependencies) for task in tasks}
        
        # 队列：存储入度为0的任务
        queue = [task_id for task_id, degree in in_degree.items() if degree == 0]
        result = []
        
        while queue:
            # 按优先级排序
            queue.sort(key=lambda tid: task_map[tid].priority, reverse=True)
            current_id = queue.pop(0)
            result.append(task_map[current_id])
            
            # 更新依赖任务的入度
            for task in tasks:
                if current_id in task.dependencies:
                    in_degree[task.task_id] -= 1
                    if in_degree[task.task_id] == 0:
                        queue.append(task.task_id)
        
        # 检查是否有循环依赖
        if len(result) != len(tasks):
            logger.warning("Circular dependency detected, returning original order")
            return tasks
        
        return result
```

#### 5.2 单元测试

**文件路径**: `tests/multi_agent/test_task_decomposer.py`

```python
"""
测试任务分解器
"""
import pytest
from collaboration.task_decomposer import TaskDecomposer
from agents.agent_types import AgentTask

class TestTaskDecomposer:
    """测试任务分解器"""

    @pytest.fixture
    def decomposer(self):
        """创建任务分解器实例"""
        return TaskDecomposer()

    def test_simple_code_task(self, decomposer):
        """测试简单代码任务分解"""
        request = "实现一个用户登录功能"
        tasks = decomposer.decompose(request)
        
        assert len(tasks) >= 1
        assert any("code" in task.task_type for task in tasks)

    def test_complex_task_with_test_and_doc(self, decomposer):
        """测试包含测试和文档的复杂任务"""
        request = "实现用户认证功能，编写测试，并生成文档"
        tasks = decomposer.decompose(request)
        
        # 应该包含代码、测试、文档任务
        task_types = [task.task_type for task in tasks]
        assert "code_generation" in task_types or "code" in str(task_types)
        assert "testing" in task_types or "test" in str(task_types)
        assert "documentation" in task_types or "doc" in str(task_types)

    def test_dependency_detection(self, decomposer):
        """测试依赖关系检测"""
        request = "实现功能并编写测试"
        tasks = decomposer.decompose(request)
        
        # 测试任务应该依赖代码生成任务
        test_tasks = [t for t in tasks if "test" in t.task_type]
        code_tasks = [t for t in tasks if "code" in t.task_type]
        
        if test_tasks and code_tasks:
            # 检查依赖关系
            dependencies = decomposer.detect_dependencies(tasks)
            assert len(dependencies) > 0

    def test_complexity_estimation(self, decomposer):
        """测试复杂度评估"""
        task = AgentTask(
            task_id="test",
            task_type="code_generation",
            description="Test",
            required_capabilities=["code"],
            input_data={},
            dependencies=["dep1", "dep2"],
            priority=8
        )
        
        complexity = decomposer.estimate_complexity(task)
        assert 1 <= complexity <= 10
        assert complexity >= 7  # 基础复杂度

    def test_topological_sort(self, decomposer):
        """测试拓扑排序"""
        tasks = [
            AgentTask("task1", "code", "Code", ["code"], {}, dependencies=[]),
            AgentTask("task2", "test", "Test", ["test"], {}, dependencies=["task1"]),
            AgentTask("task3", "doc", "Doc", ["doc"], {}, dependencies=["task1"])
        ]
        
        sorted_tasks = decomposer.optimize_task_order(tasks)
        
        # task1应该在task2和task3之前
        task1_index = next(i for i, t in enumerate(sorted_tasks) if t.task_id == "task1")
        task2_index = next(i for i, t in enumerate(sorted_tasks) if t.task_id == "task2")
        task3_index = next(i for i, t in enumerate(sorted_tasks) if t.task_id == "task3")
        
        assert task1_index < task2_index
        assert task1_index < task3_index

    def test_generic_task_fallback(self, decomposer):
        """测试通用任务回退"""
        request = "这是一个无法识别的请求"
        tasks = decomposer.decompose(request)
        
        # 应该创建通用任务
        assert len(tasks) == 1
        assert tasks[0].task_type == "generic"

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
```

#### 5.3 运行测试

```bash
# 运行任务分解器测试
python -m pytest tests/multi_agent/test_task_decomposer.py -v

# 应该看到所有测试通过
```

---

### 第六步：配置管理

#### 6.1 创建配置文件

**文件路径**: `config/multi_agent_config.json`

```json
{
  "master_agent": {
    "agent_id": "master",
    "agent_type": "master",
    "model": "qwen2.5-coder:7b",
    "host": "http://localhost:11434",
    "capabilities": [
      "task_decomposition",
      "coordination",
      "integration"
    ],
    "specialized_tools": [],
    "max_iterations": 50,
    "timeout": 600,
    "enabled": true
  },
  "agents": [
    {
      "agent_id": "code_agent",
      "agent_type": "code",
      "model": "qwen2.5-coder:7b",
      "host": "http://localhost:11434",
      "capabilities": [
        "code_generation",
        "code_refactoring",
        "bug_fixing",
        "code_review",
        "file_operations"
      ],
      "specialized_tools": [
        "code_analyzer",
        "refactor_helper",
        "syntax_checker"
      ],
      "max_iterations": 30,
      "timeout": 300,
      "enabled": true
    },
    {
      "agent_id": "rag_agent",
      "agent_type": "rag",
      "model": "qwen2.5-coder:7b",
      "host": "http://localhost:11434",
      "capabilities": [
        "knowledge_retrieval",
        "document_analysis",
        "semantic_search",
        "content_extraction"
      ],
      "specialized_tools": [
        "vector_search",
        "document_parser",
        "knowledge_graph"
      ],
      "max_iterations": 20,
      "timeout": 200,
      "enabled": true
    },
    {
      "agent_id": "test_agent",
      "agent_type": "test",
      "model": "qwen2.5-coder:7b",
      "host": "http://localhost:11434",
      "capabilities": [
        "test_generation",
        "test_execution",
        "coverage_analysis",
        "quality_assurance"
      ],
      "specialized_tools": [
        "test_generator",
        "coverage_analyzer",
        "mock_generator"
      ],
      "max_iterations": 25,
      "timeout": 300,
      "enabled": true
    },
    {
      "agent_id": "doc_agent",
      "agent_type": "doc",
      "model": "qwen2.5-coder:7b",
      "host": "http://localhost:11434",
      "capabilities": [
        "documentation",
        "api_docs",
        "user_guides",
        "technical_writing"
      ],
      "specialized_tools": [
        "doc_generator",
        "markdown_formatter",
        "api_extractor"
      ],
      "max_iterations": 20,
      "timeout": 200,
      "enabled": true
    },
    {
      "agent_id": "audit_agent",
      "agent_type": "audit",
      "model": "qwen2.5-coder:7b",
      "host": "http://localhost:11434",
      "capabilities": [
        "security_audit",
        "compliance_check",
        "performance_audit",
        "best_practice_check"
      ],
      "specialized_tools": [
        "security_scanner",
        "dependency_checker",
        "performance_profiler"
      ],
      "max_iterations": 15,
      "timeout": 250,
      "enabled": true
    }
  ],
  "orchestrator": {
    "default_collaboration_mode": "sequential",
    "max_parallel_tasks": 5,
    "task_timeout": 600,
    "enable_logging": true,
    "log_level": "INFO",
    "log_file": "~/.multi_agent.log"
  }
}
```

#### 6.2 创建配置加载器

**文件路径**: `agent_config.py`

```python
"""
多Agent系统配置管理
"""
import json
import os
from typing import Dict, List, Optional
from pathlib import Path
import logging
from agents.agent_types import AgentConfig, OrchestratorConfig, CollaborationMode, AgentType

logger = logging.getLogger(__name__)

class MultiAgentConfigLoader:
    """多Agent配置加载器"""

    DEFAULT_CONFIG_PATH = Path(__file__).parent / "config" / "multi_agent_config.json"

    @classmethod
    def load_config(cls, config_path: Optional[str] = None) -> OrchestratorConfig:
        """
        加载配置文件
        
        Args:
            config_path: 配置文件路径，如果为None则使用默认路径
            
        Returns:
            OrchestratorConfig: 编排器配置
        """
        if config_path is None:
            config_path = cls.DEFAULT_CONFIG_PATH
        else:
            config_path = Path(config_path)

        if not config_path.exists():
            logger.warning(f"Config file not found at {config_path}, using default config")
            return cls._get_default_config()

        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config_data = json.load(f)

            return cls._parse_config(config_data)

        except Exception as e:
            logger.error(f"Error loading config: {e}")
            return cls._get_default_config()

    @classmethod
    def _parse_config(cls, config_data: Dict) -> OrchestratorConfig:
        """
        解析配置数据
        
        Args:
            config_data: 配置数据字典
            
        Returns:
            OrchestratorConfig: 编排器配置
        """
        # 解析Master Agent配置
        master_config_data = config_data.get("master_agent", {})
        master_config = AgentConfig(
            agent_id=master_config_data.get("agent_id", "master"),
            agent_type=AgentType(master_config_data.get("agent_type", "master")),
            model=master_config_data.get("model", "qwen2.5-coder:7b"),
            host=master_config_data.get("host", "http://localhost:11434"),
            capabilities=master_config_data.get("capabilities", []),
            specialized_tools=master_config_data.get("specialized_tools", []),
            max_iterations=master_config_data.get("max_iterations", 50),
            timeout=master_config_data.get("timeout", 600),
            enabled=master_config_data.get("enabled", True),
            config_data=master_config_data
        )

        # 解析专业Agent配置
        agent_configs = []
        for agent_data in config_data.get("agents", []):
            agent_config = AgentConfig(
                agent_id=agent_data.get("agent_id"),
                agent_type=AgentType(agent_data.get("agent_type")),
                model=agent_data.get("model", "qwen2.5-coder:7b"),
                host=agent_data.get("host", "http://localhost:11434"),
                capabilities=agent_data.get("capabilities", []),
                specialized_tools=agent_data.get("specialized_tools", []),
                max_iterations=agent_data.get("max_iterations", 30),
                timeout=agent_data.get("timeout", 300),
                enabled=agent_data.get("enabled", True),
                config_data=agent_data
            )
            agent_configs.append(agent_config)

        # 解析编排器配置
        orchestrator_data = config_data.get("orchestrator", {})
        orchestrator_config = OrchestratorConfig(
            master_agent_config=master_config,
            agent_configs=agent_configs,
            default_collaboration_mode=CollaborationMode(
                orchestrator_data.get("default_collaboration_mode", "sequential")
            ),
            max_parallel_tasks=orchestrator_data.get("max_parallel_tasks", 5),
            task_timeout=orchestrator_data.get("task_timeout", 600),
            enable_logging=orchestrator_data.get("enable_logging", True),
            log_level=orchestrator_data.get("log_level", "INFO"),
            log_file=orchestrator_data.get("log_file")
        )

        return orchestrator_config

    @classmethod
    def _get_default_config(cls) -> OrchestratorConfig:
        """
        获取默认配置
        
        Returns:
            OrchestratorConfig: 默认编排器配置
        """
        master_config = AgentConfig(
            agent_id="master",
            agent_type=AgentType.MASTER,
            model="qwen2.5-coder:7b",
            host="http://localhost:11434",
            capabilities=["task_decomposition", "coordination", "integration"],
            specialized_tools=[],
            max_iterations=50,
            timeout=600,
            enabled=True
        )

        # 默认只启用一个Code Agent
        code_config = AgentConfig(
            agent_id="code_agent",
            agent_type=AgentType.CODE,
            model="qwen2.5-coder:7b",
            host="http://localhost:11434",
            capabilities=["code_generation", "file_operations"],
            specialized_tools=[],
            max_iterations=30,
            timeout=300,
            enabled=True
        )

        return OrchestratorConfig(
            master_agent_config=master_config,
            agent_configs=[code_config],
            default_collaboration_mode=CollaborationMode.SEQUENTIAL,
            max_parallel_tasks=3,
            task_timeout=600,
            enable_logging=True,
            log_level="INFO",
            log_file=None
        )

    @classmethod
    def save_config(cls, config: OrchestratorConfig, config_path: Optional[str] = None):
        """
        保存配置到文件
        
        Args:
            config: 要保存的配置
            config_path: 保存路径，如果为None则使用默认路径
        """
        if config_path is None:
            config_path = cls.DEFAULT_CONFIG_PATH
        else:
            config_path = Path(config_path)

        # 确保目录存在
        config_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            config_data = config.to_dict()
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(config_data, f, indent=2, ensure_ascii=False)

            logger.info(f"Config saved to {config_path}")

        except Exception as e:
            logger.error(f"Error saving config: {e}")
            raise
```

#### 6.3 创建配置目录和测试

```bash
# 创建配置目录
mkdir -p config

# 创建配置测试
touch tests/multi_agent/test_agent_config.py
```

**文件路径**: `tests/multi_agent/test_agent_config.py`

```python
"""
测试配置管理
"""
import pytest
import json
import tempfile
from pathlib import Path
from agent_config import MultiAgentConfigLoader
from agents.agent_types import AgentConfig, OrchestratorConfig, CollaborationMode, AgentType

class TestMultiAgentConfigLoader:
    """测试配置加载器"""

    def test_load_default_config(self):
        """测试加载默认配置"""
        config = MultiAgentConfigLoader.load_config()
        
        assert isinstance(config, OrchestratorConfig)
        assert config.master_agent_config.agent_id == "master"
        assert len(config.agent_configs) >= 1

    def test_save_and_load_config(self):
        """测试保存和加载配置"""
        # 创建临时配置文件
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            temp_path = f.name
        
        try:
            # 创建测试配置
            master_config = AgentConfig(
                agent_id="test_master",
                agent_type=AgentType.MASTER,
                model="qwen2.5-coder:7b",
                host="http://localhost:11434",
                capabilities=["test"],
                specialized_tools=[]
            )
            
            orchestrator_config = OrchestratorConfig(
                master_agent_config=master_config,
                agent_configs=[],
                default_collaboration_mode=CollaborationMode.SEQUENTIAL
            )
            
            # 保存配置
            MultiAgentConfigLoader.save_config(orchestrator_config, temp_path)
            
            # 加载配置
            loaded_config = MultiAgentConfigLoader.load_config(temp_path)
            
            assert loaded_config.master_agent_config.agent_id == "test_master"
            
        finally:
            # 清理临时文件
            Path(temp_path).unlink(missing_ok=True)

    def test_config_serialization(self):
        """测试配置序列化"""
        config = AgentConfig(
            agent_id="test",
            agent_type=AgentType.CODE,
            model="qwen2.5-coder:7b",
            host="http://localhost:11434",
            capabilities=["code"],
            specialized_tools=[]
        )
        
        # 转换为字典
        config_dict = config.to_dict()
        assert "agent_id" in config_dict
        assert config_dict["agent_type"] == "code"

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
```

#### 6.4 运行测试

```bash
# 首先创建config目录
mkdir -p config

# 复制示例配置文件
cp config/app_config.json config/multi_agent_config.json 2>/dev/null || echo "{}" > config/multi_agent_config.json

# 运行配置测试
python -m pytest tests/multi_agent/test_agent_config.py -v
```

---

## 🧪 集成测试

创建端到端集成测试

**文件路径**: `tests/multi_agent/test_integration.py`

```python
"""
多Agent系统集成测试
"""
import pytest
import time
from agent_config import MultiAgentConfigLoader
from agent_registry import AgentRegistry
from collaboration.message_bus import MessageBus
from collaboration.task_decomposer import TaskDecomposer
from agents.agent_types import AgentTask, CollaborationMode

class TestMultiAgentIntegration:
    """测试多Agent系统集成"""

    @pytest.fixture
    def config(self):
        """加载配置"""
        return MultiAgentConfigLoader.load_config()

    @pytest.fixture
    def registry(self):
        """创建注册中心"""
        return AgentRegistry()

    @pytest.fixture
    def message_bus(self):
        """创建消息总线"""
        bus = MessageBus()
        bus.start()
        yield bus
        bus.stop()

    @pytest.fixture
    def task_decomposer(self):
        """创建任务分解器"""
        return TaskDecomposer()

    def test_full_workflow(self, config, registry, task_decomposer):
        """测试完整工作流程"""
        # 1. 加载配置
        assert config.master_agent_config is not None
        assert len(config.agent_configs) > 0

        # 2. 任务分解
        request = "实现用户登录功能并编写测试"
        tasks = task_decomposer.decompose(request)
        
        assert len(tasks) >= 1
        task_types = [task.task_type for task in tasks]
        assert any("code" in t for t in task_types)

        # 3. 依赖关系检查
        dependencies = task_decomposer.detect_dependencies(tasks)
        assert isinstance(dependencies, dict)

    def test_message_bus_integration(self, message_bus):
        """测试消息总线集成"""
        received_messages = []
        
        def handler(message):
            received_messages.append(message)
        
        message_bus.subscribe("test_agent", handler)
        message_bus.send_direct("sender", "test_agent", "test", {"data": "test"})
        
        time.sleep(0.1)
        
        assert len(received_messages) == 1

    def test_collaboration_modes(self, task_decomposer):
        """测试不同协作模式"""
        request = "测试请求"
        tasks = task_decomposer.decompose(request)
        
        # 测试所有协作模式
        for mode in CollaborationMode:
            assert mode is not None
            assert isinstance(mode.value, str)

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
```

运行集成测试：

```bash
# 运行集成测试
python -m pytest tests/multi_agent/test_integration.py -v
```

---

## 📊 部署指南

### 开发环境部署

```bash
# 1. 确保所有测试通过
python -m pytest tests/multi_agent/ -v

# 2. 检查代码质量
flake8 agents/ collaboration/
black agents/ collaboration/

# 3. 类型检查
mypy agents/ collaboration/
```

### 生产环境部署

```bash
# 1. 创建生产配置
cp config/multi_agent_config.json config/multi_agent_config.prod.json

# 2. 修改生产配置
# 编辑 config/multi_agent_config.prod.json
# 调整日志级别、超时时间等参数

# 3. 启动服务
python -m multi_agent.orchestrator --config config/multi_agent_config.prod.json
```

---

## 🔧 故障排除

### 常见问题

#### 1. Agent无法启动

**症状**: Agent启动失败或立即崩溃

**解决方案**:
```bash
# 检查配置文件
python -c "from agent_config import MultiAgentConfigLoader; print(MultiAgentConfigLoader.load_config())"

# 检查日志
tail -f ~/.multi_agent.log

# 检查Ollama服务
ollama list
```

#### 2. 消息传递失败

**症状**: Agent间无法通信

**解决方案**:
```python
# 检查消息总线状态
from collaboration.message_bus import MessageBus
bus = MessageBus()
print(bus.get_statistics())
```

#### 3. 任务执行超时

**症状**: 任务长时间执行不完成

**解决方案**:
- 增加任务超时时间
- 检查Agent性能
- 优化任务分解策略

---

## 📚 开发规范

### 代码规范

1. **命名规范**
   - 类名使用PascalCase: `TaskScheduler`
   - 函数名使用snake_case: `schedule_tasks`
   - 常量使用UPPER_SNAKE_CASE: `MAX_TIMEOUT`

2. **注释规范**
   - 所有公共函数必须有docstring
   - 复杂逻辑需要行内注释
   - 使用类型提示

3. **测试规范**
   - 每个模块必须有对应测试
   - 测试覆盖率 > 80%
   - 使用pytest框架

### 提交规范

```bash
# 提交格式
git commit -m "feat: add message bus implementation"
git commit -m "fix: resolve agent registration issue"
git commit -m "docs: update configuration guide"
```

---

**开发文档结束**
