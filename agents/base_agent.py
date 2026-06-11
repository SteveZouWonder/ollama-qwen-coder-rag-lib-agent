"""
Agent基类 - 多Agent系统的核心抽象
"""
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, Callable
import time
import logging
from .agent_types import AgentTask, AgentResult, AgentMessage, AgentType, AgentState


class BaseAgent(ABC):
    """Agent基类，定义所有Agent的通用接口和行为"""
    
    def __init__(self, agent_id: str, agent_type: AgentType, 
                 capabilities: List[str], config: Dict[str, Any] = None):
        """
        初始化Agent
        
        Args:
            agent_id: Agent唯一标识符
            agent_type: Agent类型
            capabilities: Agent能力列表
            config: 额外配置
        """
        self.agent_id = agent_id
        self.agent_type = agent_type
        self.capabilities = capabilities
        self.config = config or {}
        self.state = AgentState.IDLE
        self.message_handlers: Dict[str, Callable] = {}
        self.message_bus = None
        self.logger = logging.getLogger(f"Agent.{agent_id}")
        
    def set_message_bus(self, message_bus):
        """设置消息总线"""
        self.message_bus = message_bus
        
    @abstractmethod
    def process_task(self, task: AgentTask) -> AgentResult:
        """
        处理任务（子类必须实现）
        
        Args:
            task: 要处理的任务
            
        Returns:
            AgentResult: 执行结果
        """
        pass
    
    def can_handle(self, task: AgentTask) -> bool:
        """
        判断是否能处理该任务
        
        Args:
            task: 任务对象
            
        Returns:
            bool: 是否能处理
        """
        if self.state != AgentState.IDLE:
            return False
            
        required = set(task.required_capabilities)
        available = set(self.capabilities)
        return required.issubset(available)
    
    def get_capabilities(self) -> List[str]:
        """获取能力列表"""
        return self.capabilities.copy()
    
    def get_state(self) -> AgentState:
        """获取Agent状态"""
        return self.state
    
    def set_state(self, state: AgentState):
        """设置Agent状态"""
        self.state = state
        self.logger.debug(f"Agent {self.agent_id} state changed to {state}")
    
    def register_message_handler(self, message_type: str, handler: Callable[[AgentMessage], None]):
        """
        注册消息处理器
        
        Args:
            message_type: 消息类型
            handler: 处理函数
        """
        self.message_handlers[message_type] = handler
        self.logger.debug(f"Registered handler for message type: {message_type}")
    
    def handle_message(self, message: AgentMessage):
        """
        处理接收到的消息
        
        Args:
            message: 消息对象
        """
        handler = self.message_handlers.get(message.message_type)
        if handler:
            try:
                handler(message)
            except Exception as e:
                self.logger.error(f"Error handling message {message.message_type}: {e}")
        else:
            self.logger.warning(f"No handler registered for message type: {message.message_type}")
    
    def send_message(self, to_agent: str, message_type: str, content: Dict[str, Any]):
        """
        发送消息给其他Agent
        
        Args:
            to_agent: 目标Agent ID
            message_type: 消息类型
            content: 消息内容
        """
        if self.message_bus:
            message = AgentMessage(
                from_agent=self.agent_id,
                to_agent=to_agent,
                message_type=message_type,
                content=content
            )
            self.message_bus.publish(message)
        else:
            self.logger.warning("Message bus not set, cannot send message")
    
    def execute_task_with_timeout(self, task: AgentTask, timeout: int = None) -> AgentResult:
        """
        执行任务并处理超时
        
        Args:
            task: 任务对象
            timeout: 超时时间（秒），如果为None则使用任务的timeout
            
        Returns:
            AgentResult: 执行结果
        """
        timeout = timeout or task.timeout
        start_time = time.time()
        
        self.set_state(AgentState.BUSY)
        task.status = task.status.__class__.RUNNING
        task.started_at = None
        
        try:
            # 执行任务
            result = self.process_task(task)
            
            execution_time = time.time() - start_time
            result.execution_time = execution_time
            
            if result.success:
                task.status = task.status.__class__.COMPLETED
                task.completed_at = None
                self.set_state(AgentState.IDLE)
            else:
                task.status = task.status.__class__.FAILED
                self.set_state(AgentState.ERROR)
                
            return result
            
        except Exception as e:
            execution_time = time.time() - start_time
            self.logger.error(f"Task execution failed: {e}")
            
            task.status = task.status.__class__.FAILED
            self.set_state(AgentState.ERROR)
            
            return AgentResult(
                task_id=task.task_id,
                agent_id=self.agent_id,
                success=False,
                output="",
                metadata={},
                execution_time=execution_time,
                error_message=str(e)
            )
    
    def __repr__(self):
        return f"BaseAgent(id={self.agent_id}, type={self.agent_type}, state={self.state})"
