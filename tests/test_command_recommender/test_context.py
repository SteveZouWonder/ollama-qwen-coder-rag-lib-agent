#!/usr/bin/env python3
"""
测试上下文管理器
"""
import unittest
from datetime import datetime
from src.command_recommender.context import ContextManager
from src.command_recommender.types import CommandContext


class TestContextManager(unittest.TestCase):
    """测试ContextManager类"""
    
    def setUp(self):
        """设置测试环境"""
        self.context_manager = ContextManager()
    
    def test_initialization(self):
        """测试初始化"""
        self.assertIsNotNone(self.context_manager.current_context)
        self.assertIsInstance(self.context_manager.current_context, CommandContext)
        self.assertEqual(len(self.context_manager.context_history), 0)
    
    def test_update_context(self):
        """测试更新上下文"""
        self.context_manager.update_context(
            last_command="/ask",
            command_count=5
        )
        
        self.assertEqual(self.context_manager.current_context.last_command, "/ask")
        self.assertEqual(self.context_manager.current_context.command_count, 5)
    
    def test_record_command(self):
        """测试记录命令"""
        self.context_manager.record_command(
            command="/ask",
            args="test query",
            result="success"
        )
        
        self.assertEqual(self.context_manager.current_context.last_command, "/ask")
        self.assertEqual(self.context_manager.current_context.last_command_args, "test query")
        self.assertEqual(self.context_manager.current_context.last_result, "success")
        self.assertEqual(self.context_manager.current_context.command_count, 1)
    
    def test_record_command_increments_count(self):
        """测试记录命令增加计数"""
        self.context_manager.record_command("/ask")
        self.assertEqual(self.context_manager.current_context.command_count, 1)
        
        self.context_manager.record_command("/stats")
        self.assertEqual(self.context_manager.current_context.command_count, 2)
    
    def test_record_error(self):
        """测试记录错误"""
        self.context_manager.record_error("Error 1")
        self.assertEqual(len(self.context_manager.current_context.recent_errors), 1)
        
        self.context_manager.record_error("Error 2")
        self.assertEqual(len(self.context_manager.current_context.recent_errors), 2)
    
    def test_error_limit(self):
        """测试错误数量限制"""
        # 添加超过限制的错误
        for i in range(10):
            self.context_manager.record_error(f"Error {i}")
        
        # 应该只保留最近的5个
        self.assertEqual(len(self.context_manager.current_context.recent_errors), 5)
        self.assertEqual(self.context_manager.current_context.recent_errors[-1], "Error 9")
    
    def test_clear_errors(self):
        """测试清空错误"""
        self.context_manager.record_error("Error 1")
        self.context_manager.record_error("Error 2")
        
        self.context_manager.clear_errors()
        
        self.assertEqual(len(self.context_manager.current_context.recent_errors), 0)
    
    def test_set_rag_engine_status(self):
        """测试设置RAG引擎状态"""
        self.context_manager.set_rag_engine_status(available=True, empty=False)
        
        self.assertTrue(self.context_manager.current_context.rag_engine_available)
        self.assertFalse(self.context_manager.current_context.knowledge_base_empty)
    
    def test_set_snapshot_status(self):
        """测试设置快照状态"""
        self.context_manager.set_snapshot_status(has_snapshots=True)
        
        self.assertTrue(self.context_manager.current_context.has_snapshots)
    
    def test_set_mode(self):
        """测试设置模式"""
        self.context_manager.set_mode("manual")
        
        self.assertEqual(self.context_manager.current_context.current_mode, "manual")
    
    def test_add_metadata(self):
        """测试添加元数据"""
        self.context_manager.add_metadata("key1", "value1")
        self.context_manager.add_metadata("key2", 42)
        
        self.assertEqual(self.context_manager.current_context.metadata["key1"], "value1")
        self.assertEqual(self.context_manager.current_context.metadata["key2"], 42)
    
    def test_get_context(self):
        """测试获取上下文"""
        context = self.context_manager.get_context()
        
        self.assertIsInstance(context, CommandContext)
        self.assertEqual(context, self.context_manager.current_context)
    
    def test_reset_session(self):
        """测试重置会话"""
        # 设置一些状态
        self.context_manager.record_command("/ask")
        self.context_manager.record_error("Error")
        self.context_manager.set_rag_engine_status(True, False)
        
        # 重置会话
        self.context_manager.reset_session()
        
        # 检查重置后的状态
        self.assertEqual(self.context_manager.current_context.command_count, 0)
        self.assertEqual(len(self.context_manager.current_context.recent_errors), 0)
        self.assertEqual(self.context_manager.current_context.last_command, "")
    
    def test_reset_session_preserves_system_state(self):
        """测试重置会话保留系统状态"""
        # 设置系统状态
        self.context_manager.set_rag_engine_status(True, False)
        self.context_manager.set_snapshot_status(True)
        
        # 重置会话
        self.context_manager.reset_session()
        
        # 系统状态应该保留
        self.assertTrue(self.context_manager.current_context.rag_engine_available)
        self.assertFalse(self.context_manager.current_context.knowledge_base_empty)
        self.assertTrue(self.context_manager.current_context.has_snapshots)
    
    def test_context_snapshot_creation(self):
        """测试上下文快照创建"""
        self.context_manager.record_error("Error")
        self.context_manager.record_command("/ask")
        
        # 应该创建快照
        self.assertGreater(len(self.context_manager.context_history), 0)
        
        snapshot = self.context_manager.context_history[0]
        self.assertEqual(snapshot.last_command, "/ask")
        # 快照是在命令记录时创建的，应该在record_error之后
        # 所以应该包含错误
        self.assertEqual(len(snapshot.recent_errors), 1)
    
    def test_context_history_limit(self):
        """测试上下文历史限制"""
        # 添加超过限制的命令
        for i in range(150):
            self.context_manager.record_command(f"/command_{i}")
        
        # 应该限制历史大小
        self.assertLessEqual(len(self.context_manager.context_history), 100)
    
    def test_get_session_duration(self):
        """测试获取会话持续时间"""
        duration = self.context_manager.get_session_duration()
        
        self.assertIsInstance(duration, float)
        self.assertGreaterEqual(duration, 0)
    
    def test_get_activity_summary(self):
        """测试获取活动摘要"""
        self.context_manager.record_command("/ask")
        self.context_manager.set_rag_engine_status(True, False)
        
        summary = self.context_manager.get_activity_summary()
        
        self.assertIn("session_duration", summary)
        self.assertIn("command_count", summary)
        self.assertIn("current_mode", summary)
        self.assertIn("rag_available", summary)
        self.assertEqual(summary["command_count"], 1)
        self.assertTrue(summary["rag_available"])
    
    def test_restore_context(self):
        """测试恢复上下文"""
        # 设置初始状态
        self.context_manager.record_command("/ask")
        self.context_manager.set_rag_engine_status(True, False)
        
        # 修改状态
        self.context_manager.record_command("/stats")
        
        # 恢复到第一个快照
        self.context_manager.restore_context(0)
        
        # 应该恢复到之前的状态
        self.assertEqual(self.context_manager.current_context.last_command, "/ask")
    
    def test_restore_context_invalid_index(self):
        """测试恢复无效索引"""
        # 不应该抛出异常
        self.context_manager.restore_context(999)
        
        # 上下文应该保持不变
        self.assertIsNotNone(self.context_manager.current_context)
    
    def test_restore_context_empty_history(self):
        """测试恢复空历史"""
        # 不应该抛出异常
        self.context_manager.restore_context(-1)
        
        # 上下文应该保持不变
        self.assertIsNotNone(self.context_manager.current_context)
    
    def test_metadata_persistence(self):
        """测试元数据持久性"""
        self.context_manager.add_metadata("persistent_key", "persistent_value")
        
        # 记录命令
        self.context_manager.record_command("/ask")
        
        # 元数据应该在快照中
        if self.context_manager.context_history:
            snapshot = self.context_manager.context_history[0]
            self.assertIn("persistent_key", snapshot.metadata)


if __name__ == '__main__':
    unittest.main()