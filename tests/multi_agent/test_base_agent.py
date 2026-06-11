"""
测试base_agent模块
"""
import pytest
from agents.base_agent import BaseAgent
from agents.agent_types import AgentTask, AgentResult, AgentType, AgentState, TaskStatus


class MockAgent(BaseAgent):
    """用于测试的Mock Agent"""
    
    def process_task(self, task: AgentTask) -> AgentResult:
        """模拟处理任务"""
        return AgentResult(
            task_id=task.task_id,
            agent_id=self.agent_id,
            success=True,
            output=f"Task {task.task_id} processed by {self.agent_id}",
            metadata={"mock": True},
            execution_time=0.1
        )


class TestBaseAgent:
    """测试BaseAgent基类"""
    
    def test_base_agent_creation(self):
        """测试创建BaseAgent"""
        agent = MockAgent(
            agent_id="test_agent",
            agent_type=AgentType.CODE,
            capabilities=["code_generation", "file_operations"]
        )
        
        assert agent.agent_id == "test_agent"
        assert agent.agent_type == AgentType.CODE
        assert agent.capabilities == ["code_generation", "file_operations"]
        assert agent.get_state() == AgentState.IDLE
    
    def test_base_agent_can_handle(self):
        """测试can_handle方法"""
        agent = MockAgent(
            agent_id="test_agent",
            agent_type=AgentType.CODE,
            capabilities=["code_generation", "file_operations"]
        )
        
        # 可以处理的任务
        task1 = AgentTask(
            task_id="task_001",
            task_type="code_generation",
            description="测试任务",
            required_capabilities=["code_generation"],
            input_data={}
        )
        assert agent.can_handle(task1) is True
        
        # 可以处理的任务（需要多个能力）
        task2 = AgentTask(
            task_id="task_002",
            task_type="complex",
            description="复杂任务",
            required_capabilities=["code_generation", "file_operations"],
            input_data={}
        )
        assert agent.can_handle(task2) is True
        
        # 不能处理的任务（缺少能力）
        task3 = AgentTask(
            task_id="task_003",
            task_type="testing",
            description="测试任务",
            required_capabilities=["testing"],
            input_data={}
        )
        assert agent.can_handle(task3) is False
    
    def test_base_agent_can_handle_when_busy(self):
        """测试Agent忙碌时不能处理任务"""
        agent = MockAgent(
            agent_id="test_agent",
            agent_type=AgentType.CODE,
            capabilities=["code_generation"]
        )
        
        agent.set_state(AgentState.BUSY)
        
        task = AgentTask(
            task_id="task_001",
            task_type="code_generation",
            description="测试任务",
            required_capabilities=["code_generation"],
            input_data={}
        )
        
        assert agent.can_handle(task) is False
    
    def test_base_agent_get_capabilities(self):
        """测试获取能力列表"""
        capabilities = ["code_generation", "file_operations", "bug_fixing"]
        agent = MockAgent(
            agent_id="test_agent",
            agent_type=AgentType.CODE,
            capabilities=capabilities
        )
        
        assert agent.get_capabilities() == capabilities
        # 确保返回的是副本，不是原始列表的引用
        agent.get_capabilities().append("new_capability")
        assert "new_capability" not in agent.capabilities
    
    def test_base_agent_get_state(self):
        """测试获取Agent状态"""
        agent = MockAgent(
            agent_id="test_agent",
            agent_type=AgentType.CODE,
            capabilities=["code_generation"]
        )
        
        assert agent.get_state() == AgentState.IDLE
        
        agent.set_state(AgentState.BUSY)
        assert agent.get_state() == AgentState.BUSY
    
    def test_base_agent_set_state(self):
        """测试设置Agent状态"""
        agent = MockAgent(
            agent_id="test_agent",
            agent_type=AgentType.CODE,
            capabilities=["code_generation"]
        )
        
        agent.set_state(AgentState.BUSY)
        assert agent.get_state() == AgentState.BUSY
        
        agent.set_state(AgentState.ERROR)
        assert agent.get_state() == AgentState.ERROR
        
        agent.set_state(AgentState.IDLE)
        assert agent.get_state() == AgentState.IDLE
    
    def test_base_agent_register_message_handler(self):
        """测试注册消息处理器"""
        agent = MockAgent(
            agent_id="test_agent",
            agent_type=AgentType.CODE,
            capabilities=["code_generation"]
        )
        
        def handler(message):
            pass
        
        agent.register_message_handler("test_type", handler)
        assert "test_type" in agent.message_handlers
        assert agent.message_handlers["test_type"] == handler
    
    def test_base_agent_handle_message(self):
        """测试处理消息"""
        agent = MockAgent(
            agent_id="test_agent",
            agent_type=AgentType.CODE,
            capabilities=["code_generation"]
        )
        
        handled_messages = []
        
        def handler(message):
            handled_messages.append(message.message_type)
        
        agent.register_message_handler("test_type", handler)
        
        from agents.agent_types import AgentMessage
        message = AgentMessage(
            from_agent="other_agent",
            to_agent="test_agent",
            message_type="test_type",
            content={}
        )
        
        agent.handle_message(message)
        
        assert len(handled_messages) == 1
        assert handled_messages[0] == "test_type"
    
    def test_base_agent_handle_message_unregistered_type(self):
        """测试处理未注册的消息类型"""
        agent = MockAgent(
            agent_id="test_agent",
            agent_type=AgentType.CODE,
            capabilities=["code_generation"]
        )
        
        from agents.agent_types import AgentMessage
        message = AgentMessage(
            from_agent="other_agent",
            to_agent="test_agent",
            message_type="unregistered_type",
            content={}
        )
        
        # 不应该抛出异常
        agent.handle_message(message)
    
    def test_base_agent_set_message_bus(self):
        """测试设置消息总线"""
        agent = MockAgent(
            agent_id="test_agent",
            agent_type=AgentType.CODE,
            capabilities=["code_generation"]
        )
        
        mock_bus = "mock_message_bus"
        agent.set_message_bus(mock_bus)
        
        assert agent.message_bus == mock_bus
    
    def test_base_agent_send_message_without_bus(self):
        """测试在没有消息总线时发送消息"""
        agent = MockAgent(
            agent_id="test_agent",
            agent_type=AgentType.CODE,
            capabilities=["code_generation"]
        )
        
        # 不设置消息总线
        # 不应该抛出异常
        agent.send_message("other_agent", "test_type", {})
    
    def test_base_agent_execute_task_with_timeout_success(self):
        """测试执行任务成功"""
        agent = MockAgent(
            agent_id="test_agent",
            agent_type=AgentType.CODE,
            capabilities=["code_generation"]
        )
        
        task = AgentTask(
            task_id="task_001",
            task_type="code_generation",
            description="测试任务",
            required_capabilities=["code_generation"],
            input_data={}
        )
        
        result = agent.execute_task_with_timeout(task)
        
        assert result.success is True
        assert result.agent_id == "test_agent"
        assert result.task_id == "task_001"
        assert agent.get_state() == AgentState.IDLE
        assert task.status == TaskStatus.COMPLETED
    
    def test_base_agent_execute_task_with_timeout_failure(self):
        """测试执行任务失败"""
        
        class FailingAgent(BaseAgent):
            def process_task(self, task: AgentTask) -> AgentResult:
                raise Exception("Simulated failure")
        
        agent = FailingAgent(
            agent_id="failing_agent",
            agent_type=AgentType.CODE,
            capabilities=["code_generation"]
        )
        
        task = AgentTask(
            task_id="task_001",
            task_type="code_generation",
            description="测试任务",
            required_capabilities=["code_generation"],
            input_data={}
        )
        
        result = agent.execute_task_with_timeout(task)
        
        assert result.success is False
        assert result.error_message == "Simulated failure"
        assert agent.get_state() == AgentState.ERROR
        assert task.status == TaskStatus.FAILED
    
    def test_base_agent_execute_task_with_timeout_custom_timeout(self):
        """测试使用自定义超时时间"""
        agent = MockAgent(
            agent_id="test_agent",
            agent_type=AgentType.CODE,
            capabilities=["code_generation"]
        )
        
        task = AgentTask(
            task_id="task_001",
            task_type="code_generation",
            description="测试任务",
            required_capabilities=["code_generation"],
            input_data={}
        )
        
        result = agent.execute_task_with_timeout(task, timeout=100)
        
        assert result.success is True
    
    def test_base_agent_repr(self):
        """测试Agent的字符串表示"""
        agent = MockAgent(
            agent_id="test_agent",
            agent_type=AgentType.CODE,
            capabilities=["code_generation"]
        )
        
        repr_str = repr(agent)
        
        assert "test_agent" in repr_str
        assert "code" in repr_str  # 使用小写
        assert "IDLE" in repr_str
    
    def test_base_agent_send_message_with_bus(self):
        """测试通过消息总线发送消息"""
        agent = MockAgent(
            agent_id="test_agent",
            agent_type=AgentType.CODE,
            capabilities=["code_generation"]
        )
        
        # 创建一个mock消息总线
        class MockMessageBus:
            def __init__(self):
                self.published_messages = []
            
            def publish(self, message):
                self.published_messages.append(message)
        
        mock_bus = MockMessageBus()
        agent.set_message_bus(mock_bus)
        
        agent.send_message("other_agent", "test_type", {"key": "value"})
        
        assert len(mock_bus.published_messages) == 1
        assert mock_bus.published_messages[0].from_agent == "test_agent"
        assert mock_bus.published_messages[0].to_agent == "other_agent"
    
    def test_base_agent_handle_message_with_error(self):
        """测试处理消息时回调出错"""
        agent = MockAgent(
            agent_id="test_agent",
            agent_type=AgentType.CODE,
            capabilities=["code_generation"]
        )
        
        def failing_handler(message):
            raise Exception("Handler error")
        
        agent.register_message_handler("error_type", failing_handler)
        
        from agents.agent_types import AgentMessage
        message = AgentMessage(
            from_agent="other_agent",
            to_agent="test_agent",
            message_type="error_type",
            content={}
        )
        
        # 不应该抛出异常，应该记录错误
        agent.handle_message(message)
    
    def test_base_agent_execute_task_timeout(self):
        """测试任务执行超时"""
        agent = MockAgent(
            agent_id="test_agent",
            agent_type=AgentType.CODE,
            capabilities=["code_generation"]
        )
        
        task = AgentTask(
            task_id="task_001",
            task_type="code_generation",
            description="测试任务",
            required_capabilities=["code_generation"],
            input_data={},
            timeout=0  # 设置为0秒超时
        )
        
        result = agent.execute_task_with_timeout(task, timeout=0.001)  # 使用极短的超时
        
        # 应该返回结果
        assert result is not None
        assert result.task_id == "task_001"
