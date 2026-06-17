#!/usr/bin/env python3
"""
测试工作流分析器
"""
import unittest
from src.command_recommender.workflow import WorkflowAnalyzer
from src.command_recommender.types import (
    CommandContext,
    RecommendationStrength,
    RecommendationSource
)


class TestWorkflowAnalyzer(unittest.TestCase):
    """测试WorkflowAnalyzer类"""
    
    def setUp(self):
        """设置测试环境"""
        self.analyzer = WorkflowAnalyzer()
    
    def test_initialization(self):
        """测试初始化"""
        self.assertIsNotNone(self.analyzer.workflows)
        self.assertGreater(len(self.analyzer.workflows), 0)
        self.assertIsNotNone(self.analyzer.workflow_map)
    
    def test_workflows_count(self):
        """测试工作流数量"""
        # 应该有预设的工作流
        self.assertGreater(len(self.analyzer.workflows), 5)
    
    def test_workflow_map_building(self):
        """测试工作流映射构建"""
        # 检查常见命令是否在映射中
        self.assertIn("/tutorial", self.analyzer.workflow_map)
        self.assertIn("/add", self.analyzer.workflow_map)
        self.assertIn("/ask", self.analyzer.workflow_map)
    
    def test_analyze_empty_context(self):
        """测试分析空上下文"""
        context = CommandContext()
        scores = self.analyzer.analyze(context)
        
        # 新用户应该得到教程推荐
        self.assertIn("/tutorial", scores)
        self.assertGreater(scores["/tutorial"], 0.5)
    
    def test_analyze_with_command(self):
        """测试分析带命令的上下文"""
        context = CommandContext(
            last_command="/add",
            command_count=1
        )
        scores = self.analyzer.analyze(context)
        
        # 在添加文档后应该推荐查询
        self.assertIn("/ask", scores)
    
    def test_analyze_with_errors(self):
        """测试分析带错误的上下文"""
        context = CommandContext(
            last_command="/ask",
            recent_errors=["Error occurred"],
            command_count=5
        )
        scores = self.analyzer.analyze(context)
        
        # 有错误时应该推荐清理和帮助
        self.assertIn("/clear", scores)
        self.assertIn("/help", scores)
    
    def test_analyze_empty_knowledge_base(self):
        """测试分析空知识库"""
        context = CommandContext(
            rag_engine_available=True,
            knowledge_base_empty=True,
            command_count=0
        )
        scores = self.analyzer.analyze(context)
        
        # 空知识库应该推荐添加文档
        self.assertIn("/add", scores)
        self.assertGreater(scores["/add"], 0.5)
    
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
        context = CommandContext(command_count=0)
        recommendations = self.analyzer.get_recommendations(context, min_score=0.0)
        
        # 检查不同强度级别
        has_very_strong = any(r.strength == RecommendationStrength.VERY_STRONG for r in recommendations)
        has_strong = any(r.strength == RecommendationStrength.STRONG for r in recommendations)
        
        # 至少应该有一个强推荐
        self.assertTrue(has_very_strong or has_strong)
    
    def test_recommendation_reasons(self):
        """测试推荐理由"""
        context = CommandContext(command_count=0)
        recommendations = self.analyzer.get_recommendations(context, min_score=0.3)
        
        # 推荐应该有理由
        first_rec = recommendations[0]
        self.assertGreater(len(first_rec.reasons), 0)
        
        # 理由应该来自工作流源
        workflow_reasons = [r for r in first_rec.reasons if r.source == RecommendationSource.WORKFLOW]
        self.assertGreater(len(workflow_reasons), 0)
    
    def test_suggested_path(self):
        """测试建议路径"""
        context = CommandContext(
            last_command="/add",
            command_count=1
        )
        recommendations = self.analyzer.get_recommendations(context, min_score=0.3)
        
        # 推荐应该有建议路径
        for rec in recommendations:
            if rec.suggested_path:
                # 路径应该包含上一个命令
                self.assertIn(context.last_command, rec.suggested_path)
                break
    
    def test_get_workflow_info(self):
        """测试获取工作流信息"""
        workflow_info = self.analyzer.get_workflow_info("/add")
        
        # /add 应该在某个工作流中
        self.assertIsNotNone(workflow_info)
        
        # 应该有有效的属性
        self.assertIsNotNone(workflow_info.name)
        self.assertIsNotNone(workflow_info.description)
        self.assertIsNotNone(workflow_info.steps)
    
    def test_get_workflow_info_nonexistent(self):
        """测试获取不存在命令的工作流信息"""
        workflow_info = self.analyzer.get_workflow_info("/nonexistent")
        
        # 不存在的命令应该返回None
        self.assertIsNone(workflow_info)
    
    def test_min_score_filtering(self):
        """测试最小分数过滤"""
        context = CommandContext(command_count=0)
        
        # 高阈值应该返回更少的推荐
        high_threshold_recs = self.analyzer.get_recommendations(context, min_score=0.8)
        low_threshold_recs = self.analyzer.get_recommendations(context, min_score=0.1)
        
        self.assertLessEqual(len(high_threshold_recs), len(low_threshold_recs))
    
    def test_new_user_workflow(self):
        """测试新用户工作流"""
        context = CommandContext(command_count=0)
        recommendations = self.analyzer.get_recommendations(context, min_score=0.3)
        
        # 新用户应该看到教程推荐
        tutorial_recs = [r for r in recommendations if r.command == "/tutorial"]
        self.assertGreater(len(tutorial_recs), 0)
    
    def test_document_management_workflow(self):
        """测试文档管理工作流"""
        context = CommandContext(
            last_command="/file-list",
            rag_engine_available=True,
            command_count=3
        )
        recommendations = self.analyzer.get_recommendations(context, min_score=0.3)
        
        # 在文件管理中应该推荐相关操作
        management_recs = [r for r in recommendations if r.command in ["/add", "/file-info", "/snapshot-create"]]
        self.assertGreater(len(management_recs), 0)


if __name__ == '__main__':
    unittest.main()