#!/usr/bin/env python3
"""
测试命令推荐系统的配置管理
"""
import unittest
import tempfile
import os
from pathlib import Path
from src.command_recommender.config import (
    RecommendationConfig,
    default_config,
    get_config,
    reset_config
)
from src.command_recommender.types import UserPreference


class TestRecommendationConfig(unittest.TestCase):
    """测试RecommendationConfig类"""
    
    def test_default_config(self):
        """测试默认配置"""
        config = RecommendationConfig()
        self.assertTrue(config.enabled)
        self.assertEqual(config.max_recommendations, 5)
        self.assertAlmostEqual(config.min_strength_threshold, 0.3)
        self.assertTrue(config.learning_enabled)
        self.assertTrue(config.show_explanations)
        self.assertTrue(config.show_paths)
        self.assertTrue(config.show_strength)
        self.assertEqual(config.auto_hide_after, 30)
    
    def test_config_weights(self):
        """测试配置权重"""
        config = RecommendationConfig()
        self.assertAlmostEqual(config.weights["workflow"], 0.4)
        self.assertAlmostEqual(config.weights["state"], 0.3)
        self.assertAlmostEqual(config.weights["history"], 0.3)
    
    def test_preference_save_load(self):
        """测试偏好保存和加载"""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = RecommendationConfig(preference_file=os.path.join(tmpdir, "test_pref.json"))
            
            # 创建测试偏好
            preference = UserPreference(
                prefer_workflow=0.5,
                prefer_state=0.3,
                prefer_history=0.2,
                show_explanations=False
            )
            
            # 保存偏好
            self.assertTrue(config.save_preference(preference))
            
            # 加载偏好
            loaded_preference = config.load_preference()
            self.assertAlmostEqual(loaded_preference.prefer_workflow, 0.5)
            self.assertAlmostEqual(loaded_preference.prefer_state, 0.3)
            self.assertAlmostEqual(loaded_preference.prefer_history, 0.2)
            self.assertFalse(loaded_preference.show_explanations)
    
    def test_preference_save_load_with_file_not_exist(self):
        """测试文件不存在时的偏好加载"""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = RecommendationConfig(preference_file=os.path.join(tmpdir, "nonexistent.json"))
            
            # 文件不存在时应返回默认偏好
            preference = config.load_preference()
            self.assertIsInstance(preference, UserPreference)
            self.assertAlmostEqual(preference.prefer_workflow, 0.4)
    
    def test_update_from_environment(self):
        """测试从环境变量更新配置"""
        # 设置环境变量
        os.environ["RECOMMENDER_ENABLED"] = "false"
        os.environ["RECOMMENDER_MAX"] = "10"
        os.environ["RECOMMENDER_MIN_STRENGTH"] = "0.5"
        os.environ["RECOMMENDER_LEARNING"] = "false"
        os.environ["RECOMMENDER_AUTO_HIDE"] = "60"
        
        try:
            config = RecommendationConfig()
            config.update_from_environment()
            
            self.assertFalse(config.enabled)
            self.assertEqual(config.max_recommendations, 10)
            self.assertAlmostEqual(config.min_strength_threshold, 0.5)
            self.assertFalse(config.learning_enabled)
            self.assertEqual(config.auto_hide_after, 60)
        finally:
            # 清理环境变量
            del os.environ["RECOMMENDER_ENABLED"]
            del os.environ["RECOMMENDER_MAX"]
            del os.environ["RECOMMENDER_MIN_STRENGTH"]
            del os.environ["RECOMMENDER_LEARNING"]
            del os.environ["RECOMMENDER_AUTO_HIDE"]


class TestConfigFunctions(unittest.TestCase):
    """测试配置函数"""
    
    def test_default_config_function(self):
        """测试默认配置函数"""
        config = default_config()
        self.assertIsInstance(config, RecommendationConfig)
        self.assertTrue(config.enabled)
    
    def test_get_config_singleton(self):
        """测试配置单例"""
        reset_config()
        
        config1 = get_config()
        config2 = get_config()
        
        # 应该是同一个实例
        self.assertIs(config1, config2)
    
    def test_reset_config(self):
        """测试重置配置"""
        config1 = get_config()
        reset_config()
        
        config2 = get_config()
        
        # 重置后应该是新实例
        self.assertIsNot(config1, config2)
    
    def test_environment_override_default_config(self):
        """测试环境变量覆盖默认配置"""
        os.environ["RECOMMENDER_ENABLED"] = "false"
        
        try:
            reset_config()
            config = get_config()
            
            self.assertFalse(config.enabled)
        finally:
            if "RECOMMENDER_ENABLED" in os.environ:
                del os.environ["RECOMMENDER_ENABLED"]
            reset_config()


if __name__ == '__main__':
    unittest.main()