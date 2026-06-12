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
