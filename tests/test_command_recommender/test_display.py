#!/usr/bin/env python3
"""
测试显示格式化器
"""
import unittest
from src.command_recommender.display import DisplayFormatter
from src.command_recommender.types import (
    Recommendation,
    RecommendationStrength,
    UserPreference
)


class TestDisplayFormatter(unittest.TestCase):
    """测试DisplayFormatter类"""
    
    def setUp(self):
        """设置测试环境"""
        self.preference = UserPreference()
        self.formatter = DisplayFormatter(self.preference)
    
    def test_initialization(self):
        """测试初始化"""
        self.assertIsNotNone(self.formatter.preference)
        self.assertIsInstance(self.formatter.preference, UserPreference)
    
    def test_format_recommendations_empty(self):
        """测试格式化空推荐列表"""
        result = self.formatter.format_recommendations([])
        
        self.assertEqual(result, "")
    
    def test_format_recommendations_plain(self):
        """测试纯文本格式化推荐"""
        recommendations = [
            Recommendation(
                command="/ask",
                description="查询知识库",
                strength=RecommendationStrength.STRONG,
                score=0.75
            )
        ]
        
        result = self.formatter.format_recommendations(recommendations, use_rich=False)
        
        self.assertIsInstance(result, str)
        self.assertIn("/ask", result)
        self.assertIn("查询知识库", result)
        self.assertIn("智能推荐", result)
    
    def test_format_recommendations_with_explanations(self):
        """测试带说明的推荐格式化"""
        from src.command_recommender.types import RecommendationReason, RecommendationSource
        
        recommendations = [
            Recommendation(
                command="/ask",
                description="查询知识库",
                strength=RecommendationStrength.STRONG,
                score=0.75
            )
        ]
        
        # 添加理由
        reason = RecommendationReason(
            source=RecommendationSource.WORKFLOW,
            explanation="基于工作流分析",
            confidence=0.8
        )
        recommendations[0].add_reason(reason)
        
        result = self.formatter.format_recommendations(recommendations, use_rich=False)
        
        self.assertIn("理由", result)
    
    def test_format_recommendations_with_paths(self):
        """测试带路径的推荐格式化"""
        recommendations = [
            Recommendation(
                command="/ask",
                description="查询知识库",
                strength=RecommendationStrength.STRONG,
                score=0.75,
                suggested_path=["/add", "/ask"]
            )
        ]
        
        result = self.formatter.format_recommendations(recommendations, use_rich=False)
        
        self.assertIn("路径", result)
        self.assertIn("/add", result)
        self.assertIn("/ask", result)
    
    def test_format_recommendations_hidden_filtered(self):
        """测试隐藏推荐过滤"""
        recommendations = [
            Recommendation(
                command="/ask",
                description="查询知识库",
                strength=RecommendationStrength.STRONG,
                score=0.75
            ),
            Recommendation(
                command="/help",
                description="显示帮助",
                strength=RecommendationStrength.WEAK,
                score=0.4
            )
        ]
        
        # 隐藏 /help
        self.formatter.preference.hide_recommendation("/help")
        
        result = self.formatter.format_recommendations(recommendations, use_rich=False)
        
        # 应该只包含 /ask
        self.assertIn("/ask", result)
        self.assertNotIn("/help", result)
    
    def test_format_recommendations_max_limit(self):
        """测试最大推荐数量限制"""
        recommendations = [
            Recommendation(
                command=f"/command_{i}",
                description=f"Command {i}",
                strength=RecommendationStrength.WEAK,
                score=0.3
            ) for i in range(10)
        ]
        
        result = self.formatter.format_recommendations(recommendations, use_rich=False)
        
        # 默认最多显示5个
        lines = result.split("\n")
        command_lines = [line for line in lines if "/command_" in line]
        self.assertLessEqual(len(command_lines), 5)
    
    def test_format_single_recommendation(self):
        """测试格式化单个推荐"""
        recommendation = Recommendation(
            command="/ask",
            description="查询知识库",
            strength=RecommendationStrength.STRONG
        )
        
        result = self.formatter.format_single_recommendation(recommendation, use_rich=False)
        
        self.assertIn("/ask", result)
        self.assertIn("查询知识库", result)
    
    def test_format_single_recommendation_rich(self):
        """测试Rich格式化单个推荐"""
        recommendation = Recommendation(
            command="/ask",
            description="查询知识库",
            strength=RecommendationStrength.STRONG
        )
        
        result = self.formatter.format_single_recommendation(recommendation, use_rich=True)
        
        self.assertIn("/ask", result)
        # Rich格式应该包含标记
        self.assertIn("[", result)
    
    def test_get_strength_emoji(self):
        """测试强度emoji"""
        emoji = self.formatter._get_strength_emoji(RecommendationStrength.VERY_STRONG)
        self.assertEqual(emoji, "🎯")
        
        emoji = self.formatter._get_strength_emoji(RecommendationStrength.STRONG)
        self.assertEqual(emoji, "🔧")
        
        emoji = self.formatter._get_strength_emoji(RecommendationStrength.MODERATE)
        self.assertEqual(emoji, "💭")
        
        emoji = self.formatter._get_strength_emoji(RecommendationStrength.WEAK)
        self.assertEqual(emoji, "💡")
    
    def test_get_strength_text(self):
        """测试强度文本"""
        text = self.formatter._get_strength_text(RecommendationStrength.VERY_STRONG)
        self.assertEqual(text, "强烈推荐")
        
        text = self.formatter._get_strength_text(RecommendationStrength.STRONG)
        self.assertEqual(text, "推荐")
        
        text = self.formatter._get_strength_text(RecommendationStrength.MODERATE)
        self.assertEqual(text, "建议")
        
        text = self.formatter._get_strength_text(RecommendationStrength.WEAK)
        self.assertEqual(text, "可能需要")
    
    def test_format_context_info(self):
        """测试格式化上下文信息"""
        context_info = {
            "session_duration": 120.5,
            "command_count": 5,
            "current_mode": "auto",
            "rag_available": True,
            "knowledge_empty": False
        }
        
        result = self.formatter.format_context_info(context_info, use_rich=False)
        
        self.assertIn("会话时长", result)
        self.assertIn("命令数量", result)
        self.assertIn("120", result)
        self.assertIn("5", result)
    
    def test_format_context_info_rich(self):
        """测试Rich格式化上下文信息"""
        context_info = {
            "session_duration": 120.5,
            "command_count": 5,
            "current_mode": "auto",
            "rag_available": True,
            "knowledge_empty": False
        }
        
        result = self.formatter.format_context_info(context_info, use_rich=True)
        
        self.assertIn("会话时长", result)
        # Rich格式应该包含标记
        self.assertIn("[", result)
    
    def test_format_learning_info(self):
        """测试格式化学习信息"""
        learning_info = {
            "weights": {
                "workflow": 0.5,
                "state": 0.3,
                "history": 0.2
            },
            "hidden_count": 2,
            "last_updated": "2026-06-17T10:00:00"
        }
        
        result = self.formatter.format_learning_info(learning_info, use_rich=False)
        
        self.assertIn("学习引擎状态", result)
        self.assertIn("工作流权重", result)
        self.assertIn("0.50", result)
    
    def test_format_learning_info_empty(self):
        """测试格式化空学习信息"""
        result = self.formatter.format_learning_info({}, use_rich=False)
        
        self.assertEqual(result, "")
    
    def test_set_preference(self):
        """测试设置偏好"""
        new_preference = UserPreference(max_recommendations=10)
        self.formatter.set_preference(new_preference)
        
        self.assertEqual(self.formatter.preference.max_recommendations, 10)
    
    def test_format_recommendations_show_strength(self):
        """测试显示强度"""
        self.preference.show_strength = True
        recommendations = [
            Recommendation(
                command="/ask",
                description="查询知识库",
                strength=RecommendationStrength.STRONG,
                score=0.75
            )
        ]
        
        result = self.formatter.format_recommendations(recommendations, use_rich=False)
        
        self.assertIn("建议强度", result)
        self.assertIn("75.0%", result)
    
    def test_format_recommendations_hide_strength(self):
        """测试隐藏强度"""
        self.preference.show_strength = False
        recommendations = [
            Recommendation(
                command="/ask",
                description="查询知识库",
                strength=RecommendationStrength.STRONG,
                score=0.75
            )
        ]
        
        result = self.formatter.format_recommendations(recommendations, use_rich=False)
        
        self.assertNotIn("建议强度", result)
    
    def test_format_recommendations_show_paths(self):
        """测试显示路径"""
        self.preference.show_paths = True
        recommendations = [
            Recommendation(
                command="/ask",
                description="查询知识库",
                strength=RecommendationStrength.STRONG,
                score=0.75,
                suggested_path=["/add", "/ask"]
            )
        ]
        
        result = self.formatter.format_recommendations(recommendations, use_rich=False)
        
        self.assertIn("路径", result)
        self.assertIn("/add", result)
        self.assertIn("/ask", result)
    
    def test_format_recommendations_hide_paths(self):
        """测试隐藏路径"""
        self.preference.show_paths = False
        recommendations = [
            Recommendation(
                command="/ask",
                description="查询知识库",
                strength=RecommendationStrength.STRONG,
                score=0.75,
                suggested_path=["/add", "/ask"]
            )
        ]
        
        result = self.formatter.format_recommendations(recommendations, use_rich=False)
        
        self.assertNotIn("路径", result)


if __name__ == '__main__':
    unittest.main()