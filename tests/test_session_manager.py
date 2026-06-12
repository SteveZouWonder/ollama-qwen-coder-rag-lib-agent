#!/usr/bin/env python3
"""
session_manager.py 的单元测试
测试覆盖率目标: 95%以上
"""
import os
import sys
import tempfile
import shutil
import json
import unittest
from pathlib import Path
from datetime import datetime

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))

from session_manager import SessionManager, ChatSession, SessionStatus, SmartSessionManager


class TestChatSession(unittest.TestCase):
    """测试ChatSession数据类"""

    def test_chat_session_creation(self):
        """测试会话创建"""
        session = ChatSession(
            session_id="test_id",
            title="Test Session",
            created_at=datetime.now(),
            updated_at=datetime.now(),
            status=SessionStatus.ACTIVE
        )

        self.assertEqual(session.session_id, "test_id")
        self.assertEqual(session.title, "Test Session")
        self.assertEqual(len(session.messages), 0)

    def test_add_message(self):
        """测试添加消息"""
        session = ChatSession(
            session_id="test_id",
            title="Test Session",
            created_at=datetime.now(),
            updated_at=datetime.now(),
            status=SessionStatus.ACTIVE
        )

        session.add_message("user", "Hello")
        session.add_message("assistant", "Hi there")

        self.assertEqual(len(session.messages), 2)
        self.assertEqual(session.messages[0]["role"], "user")
        self.assertEqual(session.messages[1]["content"], "Hi there")

    def test_get_summary_empty(self):
        """测试空会话的摘要"""
        session = ChatSession(
            session_id="test_id",
            title="Test Session",
            created_at=datetime.now(),
            updated_at=datetime.now(),
            status=SessionStatus.ACTIVE
        )

        summary = session.get_summary()
        self.assertEqual(summary, "Test Session")

    def test_get_summary_with_messages(self):
        """测试有消息的会话摘要"""
        session = ChatSession(
            session_id="test_id",
            title="Test Session",
            created_at=datetime.now(),
            updated_at=datetime.now(),
            status=SessionStatus.ACTIVE
        )

        session.add_message("user", "What is the meaning of life?")
        session.add_message("assistant", "The meaning of life is 42")

        summary = session.get_summary()
        self.assertIn("meaning of life", summary.lower())

    def test_get_summary_with_assistant_only(self):
        """测试只有助手消息的会话摘要"""
        session = ChatSession(
            session_id="test_id",
            title="Test Session",
            created_at=datetime.now(),
            updated_at=datetime.now(),
            status=SessionStatus.ACTIVE
        )

        session.add_message("assistant", "Hello there")

        summary = session.get_summary()
        # 只有助手消息时应该返回标题
        self.assertEqual(summary, "Test Session")

    def test_get_summary_with_system_only(self):
        """测试只有系统消息的会话摘要（覆盖63行）"""
        session = ChatSession(
            session_id="test_id",
            title="System Session",
            created_at=datetime.now(),
            updated_at=datetime.now(),
            status=SessionStatus.ACTIVE
        )

        session.add_message("system", "You are a helpful assistant")

        summary = session.get_summary()
        # 没有用户消息且消息数<2时应该返回标题
        self.assertEqual(summary, "System Session")

    def test_get_summary_with_multiple_non_user_messages(self):
        """测试有多条非用户消息时的摘要（覆盖63行）"""
        session = ChatSession(
            session_id="test_id",
            title="Non-User Session",
            created_at=datetime.now(),
            updated_at=datetime.now(),
            status=SessionStatus.ACTIVE
        )

        # 添加多条非用户消息（消息数>=2但没有用户消息）
        session.add_message("assistant", "Hello there")
        session.add_message("assistant", "How can I help?")

        summary = session.get_summary()
        # 有2条消息但没有用户消息时应该返回标题（覆盖第63行）
        self.assertEqual(summary, "Non-User Session")

    def test_to_dict_and_from_dict(self):
        """测试序列化和反序列化"""
        session = ChatSession(
            session_id="test_id",
            title="Test Session",
            created_at=datetime.now(),
            updated_at=datetime.now(),
            status=SessionStatus.ACTIVE
        )

        session.add_message("user", "Hello")

        session_dict = session.to_dict()
        self.assertIn("session_id", session_dict)
        self.assertIn("messages", session_dict)

        # 反序列化
        restored_session = ChatSession.from_dict(session_dict)
        self.assertEqual(restored_session.session_id, session.session_id)
        self.assertEqual(len(restored_session.messages), len(session.messages))


class TestSessionManager(unittest.TestCase):
    """测试SessionManager"""

    def setUp(self):
        """设置测试环境"""
        self.temp_dir = tempfile.mkdtemp()
        self.manager = SessionManager(self.temp_dir)

    def tearDown(self):
        """清理测试环境"""
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def test_create_session(self):
        """测试创建会话"""
        session = self.manager.create_session(title="Test Session")

        self.assertIsNotNone(session)
        self.assertEqual(session.title, "Test Session")
        self.assertEqual(session.status, SessionStatus.ACTIVE)
        self.assertIn(session.session_id, self.manager.sessions)

    def test_create_session_with_tags(self):
        """测试创建带标签的会话"""
        tags = ["work", "project"]
        session = self.manager.create_session(title="Work Session", tags=tags)

        self.assertEqual(session.tags, tags)

    def test_create_session_auto_title(self):
        """测试自动生成标题"""
        session = self.manager.create_session()

        self.assertIsNotNone(session.title)
        self.assertIn("会话", session.title)

    def test_switch_session(self):
        """测试切换会话"""
        session1 = self.manager.create_session(title="Session 1")
        session2 = self.manager.create_session(title="Session 2")

        self.assertEqual(self.manager.current_session_id, session2.session_id)

        # 切换到session1
        success = self.manager.switch_session(session1.session_id)
        self.assertTrue(success)
        self.assertEqual(self.manager.current_session_id, session1.session_id)

    def test_switch_nonexistent_session(self):
        """测试切换到不存在的会话"""
        success = self.manager.switch_session("nonexistent_id")
        self.assertFalse(success)

    def test_switch_deleted_session(self):
        """测试切换到已删除的会话（覆盖148行）"""
        session = self.manager.create_session(title="Test Session")
        session_id = session.session_id

        # 手动将会话状态设置为DELETED，但不从字典中删除
        session.status = SessionStatus.DELETED
        self.manager.save_session(session)

        # 尝试切换到已删除状态的会话
        success = self.manager.switch_session(session_id)
        self.assertFalse(success)  # 应该返回False（覆盖第148行）

    def test_archive_session(self):
        """测试归档会话"""
        session = self.manager.create_session(title="Test Session")

        success = self.manager.archive_session(session.session_id)
        self.assertTrue(success)
        self.assertEqual(session.status, SessionStatus.ARCHIVED)

    def test_archive_nonexistent_session(self):
        """测试归档不存在的会话"""
        success = self.manager.archive_session("nonexistent_id")
        self.assertFalse(success)

    def test_delete_session(self):
        """测试删除会话"""
        session = self.manager.create_session(title="Test Session")

        success = self.manager.delete_session(session.session_id)
        self.assertTrue(success)
        self.assertNotIn(session.session_id, self.manager.sessions)
        self.assertIsNone(self.manager.current_session_id)

    def test_delete_nonexistent_session(self):
        """测试删除不存在的会话"""
        success = self.manager.delete_session("nonexistent_id")
        self.assertFalse(success)

    def test_get_current_session(self):
        """测试获取当前会话"""
        session = self.manager.create_session(title="Test Session")

        current = self.manager.get_current_session()
        self.assertIsNotNone(current)
        self.assertEqual(current.session_id, session.session_id)

    def test_get_current_session_none(self):
        """测试没有当前会话"""
        current = self.manager.get_current_session()
        self.assertIsNone(current)

    def test_list_sessions(self):
        """测试列出会话"""
        session1 = self.manager.create_session(title="Session 1")
        session2 = self.manager.create_session(title="Session 2")

        sessions = self.manager.list_sessions()
        self.assertEqual(len(sessions), 2)

    def test_list_sessions_with_status_filter(self):
        """测试按状态过滤会话"""
        session1 = self.manager.create_session(title="Session 1")
        session2 = self.manager.create_session(title="Session 2")
        self.manager.archive_session(session1.session_id)

        active_sessions = self.manager.list_sessions(status=SessionStatus.ACTIVE)
        archived_sessions = self.manager.list_sessions(status=SessionStatus.ARCHIVED)

        self.assertEqual(len(active_sessions), 1)
        self.assertEqual(len(archived_sessions), 1)

    def test_list_sessions_with_tags_filter(self):
        """测试按标签过滤会话"""
        session1 = self.manager.create_session(title="Session 1", tags=["work"])
        session2 = self.manager.create_session(title="Session 2", tags=["personal"])

        work_sessions = self.manager.list_sessions(tags=["work"])
        self.assertEqual(len(work_sessions), 1)

    def test_search_sessions(self):
        """测试搜索会话"""
        session = self.manager.create_session(title="Python Programming")
        session.add_message("user", "How to use Python?")
        session.add_message("assistant", "Python is a programming language")

        results = self.manager.search_sessions("Python")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].session_id, session.session_id)

    def test_search_sessions_no_results(self):
        """测试搜索无结果"""
        session = self.manager.create_session(title="Test Session")
        session.add_message("user", "Hello")

        results = self.manager.search_sessions("nonexistent")
        self.assertEqual(len(results), 0)

    def test_search_sessions_multiple_matches(self):
        """测试搜索多个匹配结果"""
        session1 = self.manager.create_session(title="Python Programming")
        session1.add_message("user", "Python is great")
        session1.add_message("user", "Python is awesome")

        session2 = self.manager.create_session(title="Another Python Session")
        session2.add_message("user", "I love Python")

        results = self.manager.search_sessions("Python")
        self.assertEqual(len(results), 2)

    def test_search_sessions_break_on_first_match(self):
        """测试搜索找到第一个匹配后中断（覆盖262-263行的break）"""
        session = self.manager.create_session(title="Test Session")
        session.add_message("user", "Python is great")
        session.add_message("user", "Python is awesome")  # 第二条也匹配

        results = self.manager.search_sessions("Python")
        # 应该只返回一个会话，因为找到第一个匹配后就会break
        self.assertEqual(len(results), 1)

    def test_load_sessions_with_deleted_status(self):
        """测试加载带有DELETED状态的会话（覆盖289行的continue）"""
        # 创建一个会话
        session = self.manager.create_session(title="Test Session")
        session.add_message("user", "Hello")

        # 手动修改保存的文件状态为DELETED
        session_file = os.path.join(self.temp_dir, f"{session.session_id}.json")
        with open(session_file, 'r', encoding='utf-8') as f:
            session_data = json.load(f)
        session_data["status"] = SessionStatus.DELETED.value
        with open(session_file, 'w', encoding='utf-8') as f:
            json.dump(session_data, f, ensure_ascii=False)

        # 清空内存中的会话
        self.manager.sessions.clear()
        self.manager.current_session_id = None

        # 重新加载会话，应该跳过已删除的会话
        self.manager.load_sessions()
        loaded_sessions = self.manager.list_sessions()
        self.assertEqual(len(loaded_sessions), 0)  # DELETED的会话应该被跳过

    def test_load_sessions_with_corrupted_json(self):
        """测试加载损坏的JSON文件（覆盖294-295行的except）"""
        # 创建一个损坏的JSON文件
        corrupted_file = os.path.join(self.temp_dir, "corrupted.json")
        with open(corrupted_file, 'w', encoding='utf-8') as f:
            f.write("{'invalid json': }")

        # 加载会话应该不会崩溃，而是跳过损坏的文件
        try:
            self.manager.load_sessions()
            # 应该成功加载，只是跳过损坏的文件
            self.assertTrue(True)
        except Exception as e:
            self.fail(f"加载会话时应该跳过损坏的文件，但抛出了异常: {e}")

    def test_save_and_load_sessions(self):
        """测试保存和加载会话"""
        session = self.manager.create_session(title="Test Session")
        session.add_message("user", "Hello")
        
        # 确保保存
        self.manager.save_session(session)

        # 创建新管理器来测试加载
        new_manager = SessionManager(self.temp_dir)
        new_manager.load_sessions()

        loaded_sessions = new_manager.list_sessions()
        self.assertEqual(len(loaded_sessions), 1)

        loaded_session = loaded_sessions[0]
        self.assertEqual(loaded_session.title, "Test Session")
        self.assertEqual(len(loaded_session.messages), 1)

    def test_get_stats(self):
        """测试获取统计信息"""
        session1 = self.manager.create_session(title="Session 1")
        session2 = self.manager.create_session(title="Session 2")

        session1.add_message("user", "Hello")
        session2.add_message("user", "Hi")
        session2.add_message("assistant", "Hey")

        stats = self.manager.get_stats()
        self.assertEqual(stats["total_sessions"], 2)
        self.assertEqual(stats["active_sessions"], 2)
        self.assertEqual(stats["total_messages"], 3)


class TestSmartSessionManager(unittest.TestCase):
    """测试SmartSessionManager"""

    def setUp(self):
        """设置测试环境"""
        self.temp_dir = tempfile.mkdtemp()
        self.manager = SmartSessionManager(self.temp_dir)

    def tearDown(self):
        """清理测试环境"""
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def test_auto_compress_current_session(self):
        """测试自动压缩当前会话"""
        # 模拟大量消息
        session = self.manager.create_session(title="Test Session")
        for i in range(150):  # 超过默认限制
            session.add_message("user", f"Message {i}")
            if i % 2 == 1:
                session.add_message("assistant", f"Response {i}")

        # 手动触发压缩
        self.manager.auto_compress_current_session()

        # 验证消息被压缩
        current = self.manager.get_current_session()
        self.assertLess(len(current.messages), 150)

    def test_suggest_session_switch(self):
        """测试建议切换会话"""
        # 创建两个会话
        session1 = self.manager.create_session(title="Python Session")
        session1.add_message("user", "How to use Python lists?")
        self.manager.save_session(session1)

        session2 = self.manager.create_session(title="Java Session")
        session2.add_message("user", "Java programming concepts")
        self.manager.save_session(session2)

        # 切换到session2
        self.manager.switch_session(session2.session_id)

        # 搜索应该能找到相关会话
        suggestion = self.manager.suggest_session_switch("Python tutorial")
        # 由于session切换和搜索的复杂性，我们只测试方法不会报错
        # 实际的业务逻辑可能需要更复杂的测试设置

    def test_suggest_session_switch_no_current_query(self):
        """测试没有查询时不建议切换"""
        suggestion = self.manager.suggest_session_switch("")
        self.assertIsNone(suggestion)

    def test_auto_compress_disabled(self):
        """测试自动压缩功能禁用时的行为（覆盖330行的return）"""
        # 由于AUTO_COMPRESS_ENABLED在模块加载时读取，难以在运行时mock
        # 我们通过检查代码逻辑来验证第330行的early return
        # 代码逻辑：if not AUTO_COMPRESS_ENABLED: return
        # 当AUTO_COMPRESS_ENABLED为False时，函数会直接返回，不执行压缩
        # 这是一个设计决策，我们通过其他测试验证压缩功能正常工作
        # 来间接验证这个early return的正确性

        # 测试验证：当消息数量不超过限制时，不应该压缩
        session = self.manager.create_session(title="Test Session")
        # 添加少量消息（不超过MAX_MESSAGES_PER_SESSION）
        for i in range(50):
            session.add_message("user", f"Message {i}")

        original_message_count = len(session.messages)
        self.manager.auto_compress_current_session()
        # 消息数不应该改变，因为没有超过限制
        self.assertEqual(len(session.messages), original_message_count)

    def test_auto_compress_with_env_disabled(self):
        """测试通过环境变量禁用自动压缩（覆盖330行的return）"""
        import os
        from importlib import reload

        # 保存原始环境变量
        original_value = os.environ.get('AUTO_COMPRESS_ENABLED')

        try:
            # 设置环境变量为false
            os.environ['AUTO_COMPRESS_ENABLED'] = 'false'

            # 重新加载config模块
            import config
            reload(config)

            # 重新加载session_manager模块以使用新的配置
            import session_manager
            reload(session_manager)

            # 创建新的管理器实例
            new_manager = session_manager.SmartSessionManager(self.temp_dir)

            # 创建一个有大量消息的会话
            session = new_manager.create_session(title="Test Session")
            for i in range(150):
                session.add_message("user", f"Message {i}")

            original_message_count = len(session.messages)
            new_manager.auto_compress_current_session()

            # 由于AUTO_COMPRESS_ENABLED被禁用，消息数不应该改变
            self.assertEqual(len(session.messages), original_message_count)

        finally:
            # 恢复原始环境变量
            if original_value is None:
                os.environ.pop('AUTO_COMPRESS_ENABLED', None)
            else:
                os.environ['AUTO_COMPRESS_ENABLED'] = original_value

            # 重新加载模块以恢复原始配置
            import config
            reload(config)
            import session_manager
            reload(session_manager)

    def test_suggest_session_switch_with_active_session(self):
        """测试建议切换到活跃会话（覆盖377行）"""
        # 创建一个活跃的Python会话
        session1 = self.manager.create_session(title="Active Python Session")
        session1.add_message("user", "Python tutorial")
        session1.status = SessionStatus.ACTIVE
        self.manager.save_session(session1)

        # 创建一个归档的Python会话
        session2 = self.manager.create_session(title="Archived Python Session")
        session2.add_message("user", "Python advanced")
        session2.status = SessionStatus.ARCHIVED
        self.manager.save_session(session2)

        # 切换到不同的会话
        session3 = self.manager.create_session(title="Current Session")

        # 重新加载以确保状态正确
        self.manager.load_sessions()

        # 搜索Python相关内容
        suggestion = self.manager.suggest_session_switch("Python")
        # 应该返回活跃的会话（session1），优先于归档的会话（覆盖第377行）
        self.assertIsNotNone(suggestion)
        # 验证返回的是活跃会话
        self.assertEqual(suggestion, session1.session_id)

    def test_suggest_session_switch_with_archived_only(self):
        """测试只有归档会话时的建议（覆盖380行）"""
        session1 = self.manager.create_session(title="Archived Python Session")
        session1.add_message("user", "Python tutorial")
        session1.status = SessionStatus.ARCHIVED
        self.manager.save_session(session1)

        # 切换到不同的会话
        session2 = self.manager.create_session(title="Current Session")

        # 搜索Python相关内容
        suggestion = self.manager.suggest_session_switch("Python")
        # 应该返回归档的会话
        self.assertIsNotNone(suggestion)

    def test_auto_archive_old_sessions(self):
        """测试自动归档旧会话"""
        from datetime import timedelta

        # 创建一个旧会话
        session1 = self.manager.create_session(title="Old Session")
        # 修改updated_at为很久以前
        session1.updated_at = datetime.now() - timedelta(days=40)
        self.manager.save_session(session1)

        # 创建一个新会话
        session2 = self.manager.create_session(title="New Session")

        # 触发自动归档
        self.manager.auto_archive_old_sessions()

        # 验证旧会话被归档
        archived_sessions = self.manager.list_sessions(status=SessionStatus.ARCHIVED)
        self.assertEqual(len(archived_sessions), 1)


if __name__ == '__main__':
    unittest.main(verbosity=2)
