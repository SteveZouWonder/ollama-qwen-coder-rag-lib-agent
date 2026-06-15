"""
消息总线 - Agent间通信的核心机制
"""
from collections import defaultdict
from queue import Queue
from threading import Lock
from typing import Callable, Dict, List
import logging
from agents.agent_types import AgentMessage


class MessageBus:
    """Agent间通信消息总线"""
    
    def __init__(self, enable_persistence: bool = False, persistence_file: str = None):
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
        self.logger = logging.getLogger("MessageBus")
        
        if enable_persistence and persistence_file:
            self._load_persistence()
    
    def subscribe(self, agent_id: str, callback: Callable[[AgentMessage], None]):
        """
        Agent订阅消息
        
        Args:
            agent_id: Agent ID
            callback: 消息处理回调函数
        """
        with self.lock:
            self.subscribers[agent_id].append(callback)
            self.logger.debug(f"Agent {agent_id} subscribed to message bus")
    
    def unsubscribe(self, agent_id: str, callback: Callable = None):
        """
        取消订阅
        
        Args:
            agent_id: Agent ID
            callback: 要取消的回调函数，如果为None则取消所有该Agent的订阅
        """
        with self.lock:
            if callback:
                if callback in self.subscribers[agent_id]:
                    self.subscribers[agent_id].remove(callback)
                    self.logger.debug(f"Agent {agent_id} unsubscribed specific callback")
            else:
                self.subscribers[agent_id] = []
                self.logger.debug(f"Agent {agent_id} unsubscribed all callbacks")
    
    def publish(self, message: AgentMessage):
        """
        发布消息（点对点）
        
        Args:
            message: 消息对象
        """
        with self.lock:
            # 记录消息历史
            self.message_history.append(message)
            
            # 持久化
            if self.enable_persistence:
                self._persist_message(message)
            
            # 获取订阅者
            subscribers = self.subscribers.get(message.to_agent, [])
            
            self.logger.debug(
                f"Publishing message {message.message_id} from {message.from_agent} to {message.to_agent}"
            )
            
            # 调用订阅者回调
            for callback in subscribers:
                try:
                    callback(message)
                except Exception as e:
                    self.logger.error(f"Message handler error for {message.message_type}: {e}")
    
    def send_direct(self, from_agent: str, to_agent: str, 
                   message_type: str, content: Dict):
        """
        点对点发送消息
        
        Args:
            from_agent: 发送者Agent ID
            to_agent: 接收者Agent ID
            message_type: 消息类型
            content: 消息内容
        """
        message = AgentMessage(
            from_agent=from_agent,
            to_agent=to_agent,
            message_type=message_type,
            content=content,
            timestamp=None
        )
        self.publish(message)
    
    def broadcast(self, from_agent: str, message_type: str, content: Dict):
        """
        广播消息给所有订阅者（除发送者外）
        
        Args:
            from_agent: 发送者Agent ID
            message_type: 消息类型
            content: 消息内容
        """
        with self.lock:
            for agent_id, callbacks in self.subscribers.items():
                if agent_id != from_agent:
                    message = AgentMessage(
                        from_agent=from_agent,
                        to_agent=agent_id,
                        message_type=message_type,
                        content=content,
                        timestamp=None
                    )
                    
                    # 记录消息历史
                    self.message_history.append(message)
                    
                    # 持久化
                    if self.enable_persistence:
                        self._persist_message(message)
                    
                    # 调用订阅者回调
                    for callback in callbacks:
                        try:
                            callback(message)
                        except Exception as e:
                            self.logger.error(f"Broadcast error for {agent_id}: {e}")
            
            self.logger.debug(f"Broadcast message from {from_agent} to all subscribers")
    
    def get_subscribers(self) -> Dict[str, List[Callable]]:
        """获取所有订阅者"""
        with self.lock:
            return {k: list(v) for k, v in self.subscribers.items()}
    
    def get_subscriber_count(self, agent_id: str = None) -> int:
        """
        获取订阅者数量
        
        Args:
            agent_id: Agent ID，如果为None则返回总订阅数
        """
        with self.lock:
            if agent_id:
                return len(self.subscribers.get(agent_id, []))
            else:
                return sum(len(callbacks) for callbacks in self.subscribers.values())
    
    def get_message_history(self, limit: int = 100) -> List[AgentMessage]:
        """
        获取消息历史
        
        Args:
            limit: 返回的最大消息数
        """
        with self.lock:
            return self.message_history[-limit:] if limit else self.message_history.copy()
    
    def clear_history(self):
        """清空消息历史"""
        with self.lock:
            self.message_history.clear()
            self.logger.debug("Message history cleared")
    
    def _persist_message(self, message: AgentMessage):
        """持久化消息到文件"""
        if self.persistence_file:
            try:
                with open(self.persistence_file, 'a') as f:
                    f.write(message.to_dict().__str__() + '\n')
            except Exception as e:
                self.logger.error(f"Failed to persist message: {e}")
    
    def _load_persistence(self):
        """从文件加载持久化消息"""
        if self.persistence_file:
            try:
                # 简化的加载逻辑，实际可以根据需要实现更复杂的恢复机制
                pass
            except Exception as e:
                self.logger.error(f"Failed to load persistence: {e}")
    
    def shutdown(self):
        """关闭消息总线"""
        with self.lock:
            self.subscribers.clear()
            self.message_history.clear()
            self.logger.debug("Message bus shutdown")
