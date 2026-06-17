#!/usr/bin/env python3
"""
测试学习引擎
"""
import unittest
import tempfile
import os
from datetime import datetime
from src.command_recommender.learning import LearningEngine
from src.command_recommender.types import RecommendationSource, UserPreference
from src.command_recommender.config import RecommendationConfig


class TestLearningEngine(unittest.TestCase):
    """测试LearningEngine类"""
    
    def setUp(self):
        """设置测试环境"""
        # 使用临时目录进行测试
        self.temp_dir = tempfile.mkdtemp()
        self.config = RecommendationConfig(preference_file=os.path.join(self.temp_dir, "test_pref.json"))
        self.learning_engine = LearningEngine.__new__(LearningEngine)
        self.learning_engine.config = self.config
        self.learning_engine.preference = UserPreference()
        self.learning_engine._load_preference = lambda: UserPreference()  # Mock加载
        self.learning_engine._save_preference = lambda: True  # Mock保存
    
    def tearDown(self):
        """清理测试环境"""
        import shutil
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
    
    def test_initialization(self):
        """测试初始化"""
        self.assertIsNotNone(self.learning_engine.preference)
        self.assertIsNotNone(self.learning_engine.config)
    
    def test_get_weights(self):
        """测试获取权重"""
        weights = self.learning_engine.get_weights()
        
        self.assertIn("workflow", weights)
        self.assertIn("state", weights)
        self.assertIn("history", weights)
        self.assertAlmostEqual(weights["workflow"], 0.4)
        self.assertAlmostEqual(weights["state"], 0.3)
        self.assertAlmostEqual(weights["history"], 0.3)
    
    def test_get_display_preferences(self):
        """测试获取显示偏好"""
        display_prefs = self.learning_engine.get_display_preferences()
        
        self.assertIn("show_explanations", display_prefs)
        self.assertIn("show_paths", display_prefs)
        self.assertIn("show_strength", display_prefs)
        self.assertIn("auto_hide_after", display_prefs)
        self.assertIn("max_recommendations", display_prefs)
    
    def test_record_command_execution_with_recommendation(self):
        """测试记录命令执行（跟随推荐）"""
        initial_workflow_weight = self.learning_engine.preference.prefer_workflow
        
        self.learning_engine.record_command_execution(
            command="/ask",
            followed_recommendation=True,
            recommendation_source=RecommendationSource.WORKFLOW
        )
        
        # 工作流权重应该增加
        self.assertGreater(
            self.learning_engine.preference.prefer_workflow,
            initial_workflow_weight
        )
    
    def test_record_command_execution_without_recommendation(self):
        """测试记录命令执行（不跟随推荐）"""
        # 设置学习禁用
        self.learning_engine.config.learning_enabled = False
        
        initial_weights = self.learning_engine.get_weights()
        
        self.learning_engine.record_command_execution(
            command="/ask",
            followed_recommendation=False
        )
        
        # 权重不应该改变
        self.assertEqual(self.learning_engine.get_weights(), initial_weights)
    
    def test_update_weight_normalization(self):
        """测试权重归一化"""
        self.learning_engine.preference.update_weight("workflow", 0.5)
        
        # 权重应该归一化
        total = (self.learning_engine.preference.prefer_workflow + 
                self.learning_engine.preference.prefer_state + 
                self.learning_engine.preference.prefer_history)
        self.assertAlmostEqual(total, 1.0)
    
    def test_update_weight_limits(self):
        """测试权重限制"""
        # 权重应该在合理范围内
        self.learning_engine.preference.update_weight("workflow", 1.0)
        self.assertLessEqual(self.learning_engine.preference.prefer_workflow, 0.8)
        self.assertGreaterEqual(self.learning_engine.preference.prefer_workflow, 0.1)
    
    def test_hide_recommendation(self):
        """测试隐藏推荐"""
        self.learning_engine.hide_recommendation("/ask")
        
        self.assertTrue(self.learning_engine.is_hidden("/ask"))
        self.assertFalse(self.learning_engine.is_hidden("/stats"))
    
    def test_hide_recommendation_expiry(self):
        """测试隐藏推荐过期"""
        from datetime import timedelta
        
        self.learning_engine.hide_recommendation("/ask")
        
        # 修改隐藏时间为2小时前
        hide_time = self.learning_engine.preference.hidden_recommendations["/ask"]
        self.learning_engine.preference.hidden_recommendations["/ask"] = hide_time - timedelta(hours=2)
        
        # 应该不再隐藏
        self.assertFalse(self.learning_engine.is_hidden("/ask"))
    
    def test_update_display_preferences(self):
        """测试更新显示偏好"""
        self.learning_engine.update_display_preferences(
            show_explanations=False,
            max_recommendations=10
        )
        
        self.assertFalse(self.learning_engine.preference.show_explanations)
        self.assertEqual(self.learning_engine.preference.max_recommendations, 10)
    
    def test_update_display_preferences_partial(self):
        """测试部分更新显示偏好"""
        initial_show_paths = self.learning_engine.preference.show_paths
        initial_max_recommendations = self.learning_engine.preference.max_recommendations
        
        self.learning_engine.update_display_preferences(show_explanations=False)
        
        # 只更新的字段应该改变
        self.assertFalse(self.learning_engine.preference.show_explanations)
        # 未更新的字段应该保持不变
        self.assertEqual(self.learning_engine.preference.show_paths, initial_show_paths)
        self.assertEqual(self.learning_engine.preference.max_recommendations, initial_max_recommendations)
    
    def test_reset_preferences(self):
        """测试重置偏好"""
        # 修改偏好
        self.learning_engine.preference.prefer_workflow = 0.8
        self.learning_engine.preference.show_explanations = False
        
        # 重置偏好
        self.learning_engine.reset_preferences()
        
        # 应该恢复默认值
        self.assertAlmostEqual(self.learning_engine.preference.prefer_workflow, 0.4)
        self.assertTrue(self.learning_engine.preference.show_explanations)
    
    def test_get_preference_info(self):
        """测试获取偏好信息"""
        info = self.learning_engine.get_preference_info()
        
        self.assertIn("weights", info)
        self.assertIn("display", info)
        self.assertIn("hidden_count", info)
        self.assertIn("last_updated", info)
    
    def test_analyze_user_patterns_insufficient_data(self):
        """测试分析用户模式（数据不足）"""
        patterns = self.learning_engine.analyze_user_patterns([])
        
        self.assertEqual(patterns["pattern"], "insufficient_data")
    
    def test_analyze_user_patterns(self):
        """测试分析用户模式"""
        from src.command_recommender.types import CommandHistory
        
        histories = [
            CommandHistory(
                timestamp=datetime.now(),
                command="/ask",
                args="test",
                result="success"
            ) for _ in range(10)
        ]
        
        patterns = self.learning_engine.analyze_user_patterns(histories)
        
        self.assertIn("pattern", patterns)
        self.assertIn("total_commands", patterns)
        self.assertIn("unique_commands", patterns)
        self.assertEqual(patterns["total_commands"], 10)
    
    def test_analyze_user_patterns_focused(self):
        """测试分析专注型用户模式"""
        from src.command_recommender.types import CommandHistory
        
        # 创建专注型模式（主要使用一个命令）
        histories = [
            CommandHistory(
                timestamp=datetime.now(),
                command="/ask",
                args="test",
                result="success"
            ) for _ in range(8)
        ]
        
        # 添加少量其他命令
        histories.extend([
            CommandHistory(
                timestamp=datetime.now(),
                command="/stats",
                args="",
                result="success"
            ) for _ in range(2)
        ])
        
        patterns = self.learning_engine.analyze_user_patterns(histories)
        
        self.assertEqual(patterns["pattern"], "focused")
        self.assertEqual(patterns["dominant_command"], "/ask")
    
    def test_analyze_user_patterns_exploratory(self):
        """测试分析探索型用户模式"""
        from src.command_recommender.types import CommandHistory
        
        # 创建探索型模式（使用多种命令）
        commands = ["/ask", "/stats", "/add", "/history", "/clear"]
        histories = [
            CommandHistory(
                timestamp=datetime.now(),
                command=cmd,
                args="test",
                result="success"
            ) for cmd in commands for _ in range(2)
        ]
        
        patterns = self.learning_engine.analyze_user_patterns(histories)
        
        self.assertEqual(patterns["pattern"], "exploratory")
        self.assertEqual(patterns["unique_commands"], 5)
    
    def test_record_satisfaction(self):
        """测试记录满意度"""
        # 不应该抛出异常
        self.learning_engine.record_command_execution(
            command="/ask",
            satisfaction=0.8
        )
    
    def test_multiple_weight_updates(self):
        """测试多次权重更新"""
        initial_workflow = self.learning_engine.preference.prefer_workflow
        initial_state = self.learning_engine.preference.prefer_state
        initial_history = self.learning_engine.preference.prefer_history
        
        # 多次更新工作流权重
        for _ in range(3):
            self.learning_engine.record_command_execution(
                command="/ask",
                followed_recommendation=True,
                recommendation_source=RecommendationSource.WORKFLOW
            )
        
        # 工作流权重应该显著增加
        self.assertGreater(
            self.learning_engine.preference.prefer_workflow,
            initial_workflow
        )
        
        # 权重应该仍然归一化
        total = (self.learning_engine.preference.prefer_workflow + 
                self.learning_engine.preference.prefer_state + 
                self.learning_engine.preference.prefer_history)
        self.assertAlmostEqual(total, 1.0)


if __name__ == '__main__':
    unittest.main()