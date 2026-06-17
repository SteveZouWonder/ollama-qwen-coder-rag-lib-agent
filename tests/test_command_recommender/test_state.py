#!/usr/bin/env python3
"""
测试状态分析器
"""
import unittest
from src.command_recommender.state import StateAnalyzer
from src.command_recommender.types import (
    CommandContext,
    RecommendationStrength,
    RecommendationSource
)


class TestStateAnalyzer(unittest.TestCase):
    """测试StateAnalyzer类"""
    
    def setUp(self):
        """设置测试环境"""
        self.analyzer = StateAnalyzer()
    
    def test_initialization(self):
        """测试初始化"""
        self.assertIsNotNone(self.analyzer.state_conditions)
        self.assertGreater(len(self.analyzer.state_conditions), 0)
    
    def test_state_conditions_count(self):
        """测试状态条件数量"""
        # 应该有预设的状态条件
        self.assertGreater(len(self.analyzer.state_conditions), 5)
    
    def test_analyze_empty_context(self):
        """测试分析空上下文"""
        context = CommandContext()
        scores = self.analyzer.analyze(context)
        
        # 新会话应该推荐教程和状态查看
        self.assertIn("/tutorial", scores)
        self.assertIn("/stats", scores)
    
    def test_analyze_empty_knowledge_base(self):
        """测试分析空知识库"""
        context = CommandContext(
            rag_engine_available=True,
            knowledge_base_empty=True
        )
        scores = self.analyzer.analyze(context)
        
        # 空知识库应该推荐添加文档
        self.assertIn("/add", scores)
        self.assertGreater(scores["/add"], 0.5)
    
    def test_analyze_has_documents(self):
        """测试分析有文档的情况"""
        context = CommandContext(
            rag_engine_available=True,
            knowledge_base_empty=False
        )
        scores = self.analyzer.analyze(context)
        
        # 有文档应该推荐查询
        self.assertIn("/ask", scores)
        self.assertIn("/stats", scores)
    
    def test_analyze_with_snapshots(self):
        """测试分析有快照的情况"""
        context = CommandContext(has_snapshots=True)
        scores = self.analyzer.analyze(context)
        
        # 有快照应该推荐恢复和查看
        self.assertIn("/snapshot-restore", scores)
        self.assertIn("/snapshot-list", scores)
    
    def test_analyze_recent_search(self):
        """测试分析最近搜索"""
        context = CommandContext(last_command="/ask")
        scores = self.analyzer.analyze(context)
        
        # 最近搜索应该推荐查看来源和历史
        self.assertIn("/sources", scores)
        self.assertIn("/history", scores)
    
    def test_analyze_recent_errors(self):
        """测试分析最近错误"""
        context = CommandContext(
            recent_errors=["Error occurred"]
        )
        scores = self.analyzer.analyze(context)
        
        # 有错误应该推荐清理和配置检查
        self.assertIn("/clear", scores)
        self.assertIn("/config", scores)
    
    def test_analyze_new_session(self):
        """测试分析新会话"""
        context = CommandContext(command_count=0)
        scores = self.analyzer.analyze(context)
        
        # 新会话应该推荐教程和状态查看
        self.assertIn("/tutorial", scores)
        self.assertIn("/stats", scores)
    
    def test_analyze_active_development(self):
        """测试分析活跃开发状态"""
        context = CommandContext(last_command="/agent-file")
        scores = self.analyzer.analyze(context)
        
        # 活跃开发应该推荐相关操作
        self.assertIn("/ask", scores)
        self.assertIn("/history", scores)
    
    def test_analyze_management_mode(self):
        """测试分析管理模式"""
        context = CommandContext(last_command="/file-list")
        scores = self.analyzer.analyze(context)
        
        # 管理模式应该推荐文件操作
        self.assertIn("/add", scores)
        self.assertIn("/snapshot-create", scores)
    
    def test_analyze_learning_mode(self):
        """测试分析学习模式"""
        context = CommandContext(last_command="/tutorial")
        scores = self.analyzer.analyze(context)
        
        # 学习模式应该推荐实际操作
        self.assertIn("/ask", scores)
        self.assertIn("/stats", scores)
    
    def test_get_recommendations(self):
        """测试获取推荐"""
        context = CommandContext(command_count=0)
        recommendations = self.analyzer.get_recommendations(context, min_score=0.3)
        
        self.assertIsInstance(recommendations, list)
        self.assertGreater(len(recommendations), 0)
        
        # 检查推荐属性
        first_rec = recommendations[0]
        self.assertIsNotNone(first_rec.command)
        self.assertIsNotNone(first_rec.description)
        self.assertIsNotNone(first_rec.strength)
        self.assertGreaterEqual(first_rec.score, 0.3)
    
    def test_recommendation_strength_levels(self):
        """测试推荐强度级别"""
        context = CommandContext(
            rag_engine_available=True,
            knowledge_base_empty=True
        )
        recommendations = self.analyzer.get_recommendations(context, min_score=0.0)
        
        # 检查不同强度级别
        has_very_strong = any(r.strength == RecommendationStrength.VERY_STRONG for r in recommendations)
        has_strong = any(r.strength == RecommendationStrength.STRONG for r in recommendations)
        
        # 空知识库应该有强推荐
        self.assertTrue(has_very_strong or has_strong)
    
    def test_recommendation_reasons(self):
        """测试推荐理由"""
        context = CommandContext(command_count=0)
        recommendations = self.analyzer.get_recommendations(context, min_score=0.3)
        
        # 推荐应该有理由
        first_rec = recommendations[0]
        self.assertGreater(len(first_rec.reasons), 0)
        
        # 理由应该来自状态源
        state_reasons = [r for r in first_rec.reasons if r.source == RecommendationSource.STATE]
        self.assertGreater(len(state_reasons), 0)
    
    def test_get_state_description(self):
        """测试获取状态描述"""
        context = CommandContext(command_count=0)
        description = self.analyzer.get_state_description(context)
        
        self.assertIsNotNone(description)
        self.assertIsInstance(description, str)
        self.assertGreater(len(description), 0)
    
    def test_multiple_conditions_overlap(self):
        """测试多个条件重叠"""
        context = CommandContext(
            rag_engine_available=True,
            knowledge_base_empty=False,
            last_command="/ask",
            command_count=0
        )
        scores = self.analyzer.analyze(context)
        
        # 多个条件可能重叠，应该累积分数
        self.assertGreater(len(scores), 0)
    
    def test_min_score_filtering(self):
        """测试最小分数过滤"""
        context = CommandContext(command_count=0)
        
        # 高阈值应该返回更少的推荐
        high_threshold_recs = self.analyzer.get_recommendations(context, min_score=0.8)
        low_threshold_recs = self.analyzer.get_recommendations(context, min_score=0.1)
        
        self.assertLessEqual(len(high_threshold_recs), len(low_threshold_recs))
    
    def test_error_condition_priority(self):
        """测试错误条件的优先级"""
        context = CommandContext(
            recent_errors=["Error 1", "Error 2"],
            command_count=5
        )
        scores = self.analyzer.analyze(context)
        
        # 错误条件应该有较高权重
        if "/clear" in scores:
            self.assertGreater(scores["/clear"], 0.6)
    
    def test_state_condition_handling_errors(self):
        """测试状态条件错误处理"""
        # 创建一个可能导致错误的上下文
        context = CommandContext()
        
        # 这应该不会抛出异常
        try:
            scores = self.analyzer.analyze(context)
            self.assertIsInstance(scores, dict)
        except Exception as e:
            self.fail(f"analyze() 不应该抛出异常: {e}")


if __name__ == '__main__':
    unittest.main()