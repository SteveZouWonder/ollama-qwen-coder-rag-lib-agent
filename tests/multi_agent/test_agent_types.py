"""
测试agent_types模块的数据类型
"""
import pytest
from datetime import datetime
from agents.agent_types import (
    CollaborationMode, AgentType, TaskStatus, AgentState,
    AgentTask, AgentResult, AgentMessage, AgentConfig, OrchestratorConfig
)


class TestCollaborationMode:
    """测试CollaborationMode枚举"""
    
    def test_collaboration_mode_values(self):
        """测试协作模式枚举值"""
        assert CollaborationMode.HIERARCHY.value == "hierarchy"
        assert CollaborationMode.PARALLEL.value == "parallel"
        assert CollaborationMode.SEQUENTIAL.value == "sequential"
        assert CollaborationMode.COMPETITIVE.value == "competitive"
    
    def test_collaboration_mode_str(self):
        """测试协作模式的字符串表示"""
        assert str(CollaborationMode.HIERARCHY) == "hierarchy"
        assert str(CollaborationMode.PARALLEL) == "parallel"


class TestAgentType:
    """测试AgentType枚举"""
    
    def test_agent_type_values(self):
        """测试Agent类型枚举值"""
        assert AgentType.MASTER.value == "master"
        assert AgentType.CODE.value == "code"
        assert AgentType.RAG.value == "rag"
        assert AgentType.TEST.value == "test"
        assert AgentType.DOC.value == "doc"
        assert AgentType.AUDIT.value == "audit"


class TestTaskStatus:
    """测试TaskStatus枚举"""
    
    def test_task_status_values(self):
        """测试任务状态枚举值"""
        assert TaskStatus.PENDING.value == "pending"
        assert TaskStatus.ASSIGNED.value == "assigned"
        assert TaskStatus.RUNNING.value == "running"
        assert TaskStatus.COMPLETED.value == "completed"
        assert TaskStatus.FAILED.value == "failed"
        assert TaskStatus.CANCELLED.value == "cancelled"


class TestAgentState:
    """测试AgentState枚举"""
    
    def test_agent_state_values(self):
        """测试Agent状态枚举值"""
        assert AgentState.IDLE.value == "idle"
        assert AgentState.BUSY.value == "busy"
        assert AgentState.ERROR.value == "error"
        assert AgentState.OFFLINE.value == "offline"


class TestAgentTask:
    """测试AgentTask数据类"""
    
    def test_agent_task_creation(self):
        """测试创建AgentTask"""
        task = AgentTask(
            task_id="task_001",
            task_type="code_generation",
            description="实现用户登录功能",
            required_capabilities=["code_generation", "file_operations"],
            input_data={"requirements": "用户名密码登录"}
        )
        
        assert task.task_id == "task_001"
        assert task.task_type == "code_generation"
        assert task.description == "实现用户登录功能"
        assert task.required_capabilities == ["code_generation", "file_operations"]
        assert task.input_data == {"requirements": "用户名密码登录"}
        assert task.priority == 5  # 默认值
        assert task.timeout == 300  # 默认值
        assert task.status == TaskStatus.PENDING  # 默认值
        assert len(task.dependencies) == 0  # 默认值
    
    def test_agent_task_to_dict(self):
        """测试AgentTask转换为字典"""
        task = AgentTask(
            task_id="task_001",
            task_type="code_generation",
            description="测试任务",
            required_capabilities=["code_generation"],
            input_data={}
        )
        
        task_dict = task.to_dict()
        
        assert task_dict["task_id"] == "task_001"
        assert task_dict["task_type"] == "code_generation"
        assert task_dict["status"] == "pending"
        assert "created_at" in task_dict
        assert isinstance(task_dict["created_at"], str)
    
    def test_agent_task_from_dict(self):
        """测试从字典创建AgentTask"""
        task_dict = {
            "task_id": "task_001",
            "task_type": "code_generation",
            "description": "测试任务",
            "required_capabilities": ["code_generation"],
            "input_data": {},
            "status": "pending",
            "created_at": datetime.now().isoformat(),
            "dependencies": [],
            "priority": 5,
            "timeout": 300,
            "metadata": {},
            "assigned_agent": None,
            "started_at": None,
            "completed_at": None
        }
        
        task = AgentTask.from_dict(task_dict)
        
        assert task.task_id == "task_001"
        assert task.task_type == "code_generation"
        assert task.status == TaskStatus.PENDING
    
    def test_agent_task_with_dependencies(self):
        """测试带依赖关系的AgentTask"""
        task = AgentTask(
            task_id="task_002",
            task_type="testing",
            description="测试任务",
            required_capabilities=["testing"],
            input_data={},
            dependencies=["task_001"]
        )
        
        assert len(task.dependencies) == 1
        assert "task_001" in task.dependencies
    
    def test_agent_task_custom_priority(self):
        """测试自定义优先级的AgentTask"""
        task = AgentTask(
            task_id="task_003",
            task_type="code_generation",
            description="高优先级任务",
            required_capabilities=["code_generation"],
            input_data={},
            priority=10
        )
        
        assert task.priority == 10


class TestAgentResult:
    """测试AgentResult数据类"""
    
    def test_agent_result_creation(self):
        """测试创建AgentResult"""
        result = AgentResult(
            task_id="task_001",
            agent_id="agent_001",
            success=True,
            output="任务完成",
            metadata={"key": "value"},
            execution_time=1.5
        )
        
        assert result.task_id == "task_001"
        assert result.agent_id == "agent_001"
        assert result.success is True
        assert result.output == "任务完成"
        assert result.metadata == {"key": "value"}
        assert result.execution_time == 1.5
        assert result.error_message == ""  # 默认值
    
    def test_agent_result_failure(self):
        """测试失败的AgentResult"""
        result = AgentResult(
            task_id="task_001",
            agent_id="agent_001",
            success=False,
            output="",
            metadata={},
            execution_time=0.5,
            error_message="任务执行失败"
        )
        
        assert result.success is False
        assert result.error_message == "任务执行失败"
    
    def test_agent_result_to_dict(self):
        """测试AgentResult转换为字典"""
        result = AgentResult(
            task_id="task_001",
            agent_id="agent_001",
            success=True,
            output="完成",
            metadata={},
            execution_time=1.0
        )
        
        result_dict = result.to_dict()
        
        assert result_dict["task_id"] == "task_001"
        assert result_dict["agent_id"] == "agent_001"
        assert result_dict["success"] is True
        assert "timestamp" in result_dict


class TestAgentMessage:
    """测试AgentMessage数据类"""
    
    def test_agent_message_creation(self):
        """测试创建AgentMessage"""
        message = AgentMessage(
            from_agent="agent_001",
            to_agent="agent_002",
            message_type="coordination",
            content={"data": "test"}
        )
        
        assert message.from_agent == "agent_001"
        assert message.to_agent == "agent_002"
        assert message.message_type == "coordination"
        assert message.content == {"data": "test"}
        assert message.message_id.startswith("msg_")
    
    def test_agent_message_to_dict(self):
        """测试AgentMessage转换为字典"""
        message = AgentMessage(
            from_agent="agent_001",
            to_agent="agent_002",
            message_type="test",
            content={}
        )
        
        message_dict = message.to_dict()
        
        assert message_dict["from_agent"] == "agent_001"
        assert message_dict["to_agent"] == "agent_002"
        assert message_dict["message_type"] == "test"
        assert "message_id" in message_dict
        assert "timestamp" in message_dict


class TestAgentConfig:
    """测试AgentConfig数据类"""
    
    def test_agent_config_creation(self):
        """测试创建AgentConfig"""
        config = AgentConfig(
            agent_id="agent_001",
            agent_type=AgentType.CODE,
            model="qwen2.5-coder:7b",
            host="http://localhost:11434",
            capabilities=["code_generation"],
            specialized_tools=["analyzer"]
        )
        
        assert config.agent_id == "agent_001"
        assert config.agent_type == AgentType.CODE
        assert config.model == "qwen2.5-coder:7b"
        assert config.host == "http://localhost:11434"
        assert config.capabilities == ["code_generation"]
        assert config.specialized_tools == ["analyzer"]
        assert config.enabled is True  # 默认值
        assert config.max_iterations == 50  # 默认值
    
    def test_agent_config_to_dict(self):
        """测试AgentConfig转换为字典"""
        config = AgentConfig(
            agent_id="agent_001",
            agent_type=AgentType.CODE,
            model="qwen2.5-coder:7b",
            host="http://localhost:11434",
            capabilities=["code_generation"],
            specialized_tools=[]
        )
        
        config_dict = config.to_dict()
        
        assert config_dict["agent_id"] == "agent_001"
        assert config_dict["agent_type"] == "code"
        assert config_dict["model"] == "qwen2.5-coder:7b"
    
    def test_agent_config_disabled(self):
        """测试禁用的AgentConfig"""
        config = AgentConfig(
            agent_id="agent_001",
            agent_type=AgentType.CODE,
            model="qwen2.5-coder:7b",
            host="http://localhost:11434",
            capabilities=["code_generation"],
            specialized_tools=[],
            enabled=False
        )
        
        assert config.enabled is False


class TestOrchestratorConfig:
    """测试OrchestratorConfig数据类"""
    
    def test_orchestrator_config_creation(self):
        """测试创建OrchestratorConfig"""
        master_config = AgentConfig(
            agent_id="master",
            agent_type=AgentType.MASTER,
            model="qwen2.5-coder:7b",
            host="http://localhost:11434",
            capabilities=["coordination"],
            specialized_tools=[]
        )
        
        agent_config = AgentConfig(
            agent_id="agent_001",
            agent_type=AgentType.CODE,
            model="qwen2.5-coder:7b",
            host="http://localhost:11434",
            capabilities=["code_generation"],
            specialized_tools=[]
        )
        
        orchestrator_config = OrchestratorConfig(
            master_agent_config=master_config,
            agent_configs=[agent_config],
            default_collaboration_mode=CollaborationMode.PARALLEL
        )
        
        assert orchestrator_config.master_agent_config == master_config
        assert len(orchestrator_config.agent_configs) == 1
        assert orchestrator_config.default_collaboration_mode == CollaborationMode.PARALLEL
        assert orchestrator_config.max_parallel_tasks == 5  # 默认值
    
    def test_orchestrator_config_to_dict(self):
        """测试OrchestratorConfig转换为字典"""
        master_config = AgentConfig(
            agent_id="master",
            agent_type=AgentType.MASTER,
            model="qwen2.5-coder:7b",
            host="http://localhost:11434",
            capabilities=["coordination"],
            specialized_tools=[]
        )
        
        orchestrator_config = OrchestratorConfig(
            master_agent_config=master_config,
            agent_configs=[],
            default_collaboration_mode=CollaborationMode.HIERARCHY
        )
        
        config_dict = orchestrator_config.to_dict()
        
        assert "master_agent_config" in config_dict
        assert "agent_configs" in config_dict
        assert config_dict["default_collaboration_mode"] == "hierarchy"
    
    def test_orchestrator_config_custom_settings(self):
        """测试自定义OrchestratorConfig"""
        master_config = AgentConfig(
            agent_id="master",
            agent_type=AgentType.MASTER,
            model="qwen2.5-coder:7b",
            host="http://localhost:11434",
            capabilities=["coordination"],
            specialized_tools=[]
        )
        
        orchestrator_config = OrchestratorConfig(
            master_agent_config=master_config,
            agent_configs=[],
            default_collaboration_mode=CollaborationMode.SEQUENTIAL,
            max_parallel_tasks=10,
            task_timeout=1200,
            enable_logging=False
        )
        
        assert orchestrator_config.max_parallel_tasks == 10
        assert orchestrator_config.task_timeout == 1200
        assert orchestrator_config.enable_logging is False
