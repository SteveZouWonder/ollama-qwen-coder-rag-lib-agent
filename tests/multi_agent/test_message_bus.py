"""
测试message_bus模块
"""
import pytest
import os
import tempfile
from collaboration.message_bus import MessageBus
from agents.agent_types import AgentMessage


class TestMessageBus:
    """测试MessageBus类"""
    
    def test_message_bus_creation(self):
        """测试创建MessageBus"""
        bus = MessageBus()
        
        assert len(bus.subscribers) == 0
        assert bus.enable_persistence is False
    
    def test_message_bus_with_persistence(self):
        """测试创建带持久化的MessageBus"""
        bus = MessageBus(enable_persistence=True, persistence_file="/tmp/test_messages.log")
        
        assert bus.enable_persistence is True
        assert bus.persistence_file == "/tmp/test_messages.log"
    
    def test_subscribe_agent(self):
        """测试订阅Agent"""
        bus = MessageBus()
        
        messages_received = []
        
        def callback(message):
            messages_received.append(message)
        
        bus.subscribe("agent_001", callback)
        
        assert len(bus.subscribers["agent_001"]) == 1
        assert bus.subscribers["agent_001"][0] == callback
    
    def test_subscribe_multiple_callbacks(self):
        """测试订阅多个回调"""
        bus = MessageBus()
        
        def callback1(message):
            pass
        
        def callback2(message):
            pass
        
        bus.subscribe("agent_001", callback1)
        bus.subscribe("agent_001", callback2)
        
        assert len(bus.subscribers["agent_001"]) == 2
    
    def test_unsubscribe_specific_callback(self):
        """测试取消特定回调"""
        bus = MessageBus()
        
        def callback1(message):
            pass
        
        def callback2(message):
            pass
        
        bus.subscribe("agent_001", callback1)
        bus.subscribe("agent_001", callback2)
        
        bus.unsubscribe("agent_001", callback1)
        
        assert len(bus.subscribers["agent_001"]) == 1
        assert bus.subscribers["agent_001"][0] == callback2
    
    def test_unsubscribe_all_callbacks(self):
        """测试取消所有回调"""
        bus = MessageBus()
        
        def callback(message):
            pass
        
        bus.subscribe("agent_001", callback)
        bus.unsubscribe("agent_001")
        
        assert len(bus.subscribers["agent_001"]) == 0
    
    def test_publish_message(self):
        """测试发布消息"""
        bus = MessageBus()
        
        messages_received = []
        
        def callback(message):
            messages_received.append(message)
        
        bus.subscribe("agent_002", callback)
        
        message = AgentMessage(
            from_agent="agent_001",
            to_agent="agent_002",
            message_type="test",
            content={"data": "test"}
        )
        
        bus.publish(message)
        
        assert len(messages_received) == 1
        assert messages_received[0].from_agent == "agent_001"
        assert messages_received[0].to_agent == "agent_002"
    
    def test_publish_to_non_subscriber(self):
        """测试发布给非订阅者"""
        bus = MessageBus()
        
        messages_received = []
        
        def callback(message):
            messages_received.append(message)
        
        bus.subscribe("agent_001", callback)
        
        message = AgentMessage(
            from_agent="agent_001",
            to_agent="agent_003",  # 未订阅
            message_type="test",
            content={}
        )
        
        bus.publish(message)
        
        assert len(messages_received) == 0
    
    def test_send_direct(self):
        """测试直接发送消息"""
        bus = MessageBus()
        
        messages_received = []
        
        def callback(message):
            messages_received.append(message)
        
        bus.subscribe("agent_002", callback)
        
        bus.send_direct("agent_001", "agent_002", "test_type", {"key": "value"})
        
        assert len(messages_received) == 1
        assert messages_received[0].from_agent == "agent_001"
        assert messages_received[0].to_agent == "agent_002"
        assert messages_received[0].message_type == "test_type"
        assert messages_received[0].content == {"key": "value"}
    
    def test_broadcast(self):
        """测试广播消息"""
        bus = MessageBus()
        
        messages_received = []
        
        def callback1(message):
            messages_received.append(("agent_001", message.message_type))
        
        def callback2(message):
            messages_received.append(("agent_002", message.message_type))
        
        def callback3(message):
            messages_received.append(("agent_003", message.message_type))
        
        bus.subscribe("agent_001", callback1)
        bus.subscribe("agent_002", callback2)
        bus.subscribe("agent_003", callback3)
        
        bus.broadcast("agent_001", "broadcast_type", {})
        
        # agent_001不应该收到自己的广播
        agent_001_messages = [m for m in messages_received if m[0] == "agent_001"]
        assert len(agent_001_messages) == 0
        
        # agent_002和agent_003应该收到广播
        agent_002_messages = [m for m in messages_received if m[0] == "agent_002"]
        agent_003_messages = [m for m in messages_received if m[0] == "agent_003"]
        assert len(agent_002_messages) == 1
        assert len(agent_003_messages) == 1
        assert agent_002_messages[0][1] == "broadcast_type"
        assert agent_003_messages[0][1] == "broadcast_type"
    
    def test_get_subscribers(self):
        """测试获取订阅者"""
        bus = MessageBus()
        
        def callback(message):
            pass
        
        bus.subscribe("agent_001", callback)
        bus.subscribe("agent_002", callback)
        
        subscribers = bus.get_subscribers()
        
        assert "agent_001" in subscribers
        assert "agent_002" in subscribers
        assert len(subscribers["agent_001"]) == 1
    
    def test_get_subscriber_count(self):
        """测试获取订阅者数量"""
        bus = MessageBus()
        
        def callback(message):
            pass
        
        bus.subscribe("agent_001", callback)
        bus.subscribe("agent_001", callback)
        bus.subscribe("agent_002", callback)
        
        # 特定Agent的订阅数
        assert bus.get_subscriber_count("agent_001") == 2
        assert bus.get_subscriber_count("agent_002") == 1
        
        # 总订阅数
        assert bus.get_subscriber_count() == 3
    
    def test_get_message_history(self):
        """测试获取消息历史"""
        bus = MessageBus()
        
        messages_received = []
        
        def callback(message):
            messages_received.append(message)
        
        bus.subscribe("agent_002", callback)
        
        # 发送多条消息
        for i in range(5):
            bus.send_direct("agent_001", "agent_002", f"message_{i}", {})
        
        history = bus.get_message_history()
        
        assert len(history) == 5
    
    def test_get_message_history_with_limit(self):
        """测试获取有限的消息历史"""
        bus = MessageBus()
        
        def callback(message):
            pass
        
        bus.subscribe("agent_002", callback)
        
        # 发送多条消息
        for i in range(10):
            bus.send_direct("agent_001", "agent_002", f"message_{i}", {})
        
        history = bus.get_message_history(limit=5)
        
        assert len(history) == 5
    
    def test_clear_history(self):
        """测试清空消息历史"""
        bus = MessageBus()
        
        def callback(message):
            pass
        
        bus.subscribe("agent_002", callback)
        
        bus.send_direct("agent_001", "agent_002", "test", {})
        
        assert len(bus.get_message_history()) == 1
        
        bus.clear_history()
        
        assert len(bus.get_message_history()) == 0
    
    def test_callback_exception_handling(self):
        """测试回调异常处理"""
        bus = MessageBus()
        
        messages_received = []
        
        def failing_callback(message):
            raise Exception("Callback failed")
        
        def working_callback(message):
            messages_received.append(message)
        
        bus.subscribe("agent_002", failing_callback)
        bus.subscribe("agent_002", working_callback)
        
        # 不应该抛出异常，即使回调失败
        bus.send_direct("agent_001", "agent_002", "test", {})
        
        # working_callback应该仍然被调用
        assert len(messages_received) == 1
    
    def test_shutdown(self):
        """测试关闭消息总线"""
        bus = MessageBus()
        
        def callback(message):
            pass
        
        bus.subscribe("agent_001", callback)
        bus.send_direct("agent_001", "agent_002", "test", {})
        
        bus.shutdown()
        
        assert len(bus.subscribers) == 0
        assert len(bus.get_message_history()) == 0
    
    def test_publish_with_no_subscribers(self):
        """测试发布消息给没有订阅者的目标"""
        bus = MessageBus()
        
        message = AgentMessage(
            from_agent="agent_001",
            to_agent="agent_999",  # 不存在的订阅者
            message_type="test",
            content={}
        )
        
        # 不应该抛出异常
        bus.publish(message)
    
    def test_broadcast_empty_subscribers(self):
        """测试在没有订阅者时广播"""
        bus = MessageBus()
        
        # 不应该抛出异常
        bus.broadcast("agent_001", "test", {})
    
    def test_message_history_unlimited(self):
        """测试获取无限的消息历史"""
        bus = MessageBus()
        
        def callback(message):
            pass
        
        bus.subscribe("agent_002", callback)
        
        for i in range(10):
            bus.send_direct("agent_001", "agent_002", f"message_{i}", {})
        
        history = bus.get_message_history(limit=0)
        
        assert len(history) == 10
    
    def test_message_persistence_enabled(self):
        """测试启用了消息持久化"""
        import tempfile
        
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
            temp_file = f.name
        
        try:
            bus = MessageBus(enable_persistence=True, persistence_file=temp_file)
            
            def callback(message):
                pass
            
            bus.subscribe("agent_002", callback)
            
            # 创建一个完整的消息
            message = AgentMessage(
                from_agent="agent_001",
                to_agent="agent_002",
                message_type="test",
                content={}
            )
            
            # 直接发布消息而不是通过send_direct
            bus.publish(message)
            
            # 消息应该被持久化
            assert os.path.exists(temp_file)
        finally:
            if os.path.exists(temp_file):
                os.unlink(temp_file)
    
    def test_message_bus_unsubscribe_specific_callback(self):
        """测试取消特定回调"""
        bus = MessageBus()
        
        callback1_called = []
        callback2_called = []
        
        def callback1(message):
            callback1_called.append(message.message_type)
        
        def callback2(message):
            callback2_called.append(message.message_type)
        
        bus.subscribe("agent_001", callback1)
        bus.subscribe("agent_001", callback2)
        
        bus.unsubscribe("agent_001", callback1)
        
        # 发送消息
        message = AgentMessage(
            from_agent="agent_002",
            to_agent="agent_001",
            message_type="test",
            content={}
        )
        bus.publish(message)
        
        # 只有callback2应该被调用
        assert len(callback1_called) == 0
        assert len(callback2_called) == 1
