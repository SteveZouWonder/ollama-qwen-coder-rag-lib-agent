#!/usr/bin/env python3
"""
测试命令推荐系统的数据类型
"""
import unittest
from datetime import datetime
from src.command_recommender.types import (
    CommandContext,
    Recommendation,
    RecommendationReason,
    UserPreference,
    CommandHistory,
    RecommendationStrength,
    RecommendationSource,
    WorkflowDefinition,
    StateCondition
)


class TestCommandContext(unittest.TestCase):
    """测试CommandContext类"""
    
    def test_default_context(self):
        """测试默认上下文"""
        context = CommandContext()
        self.assertEqual(context.last_command, "")
        self.assertEqual(context.last_command_args, "")
        self.assertEqual(context.rag_engine_available, False)
        self.assertTrue(context.knowledge_base_empty)
        self.assertEqual(context.command_count, 0)
        self.assertEqual(len(context.recent_errors), 0)
    
    def test_context_with_values(self):
        """测试带值的上下文"""
        context = CommandContext(
            last_command="/ask",
            last_command_args="test query",
            rag_engine_available=True,
            knowledge_base_empty=False,
            command_count=5
        )
        self.assertEqual(context.last_command, "/ask")
        self.assertEqual(context.last_command_args, "test query")
        self.assertTrue(context.rag_engine_available)
        self.assertFalse(context.knowledge_base_empty)
        self.assertEqual(context.command_count, 5)
    
    def test_error_management(self):
        """测试错误管理"""
        context = CommandContext()
        context.recent_errors.append("Error 1")
        context.recent_errors.append("Error 2")
        self.assertEqual(len(context.recent_errors), 2)


class TestRecommendationReason(unittest.TestCase):
    """测试RecommendationReason类"""
    
    def test_reason_creation(self):
        """测试推荐理由创建"""
        reason = RecommendationReason(
            source=RecommendationSource.WORKFLOW,
            explanation="基于工作流分析",
            confidence=0.8
        )
        self.assertEqual(reason.source, RecommendationSource.WORKFLOW)
        self.assertEqual(reason.explanation, "基于工作流分析")
        self.assertAlmostEqual(reason.confidence, 0.8)
    
    def test_reason_to_string(self):
        """测试理由字符串表示"""
        reason = RecommendationReason(
            source=RecommendationSource.STATE,
            explanation="基于状态分析",
            confidence=0.7
        )
        reason_str = str(reason)
        self.assertIn("state", reason_str.lower())
        self.assertIn("0.70", reason_str)


class TestRecommendation(unittest.TestCase):
    """测试Recommendation类"""
    
    def test_recommendation_creation(self):
        """测试推荐创建"""
        rec = Recommendation(
            command="/ask",
            description="查询知识库",
            strength=RecommendationStrength.STRONG
        )
        self.assertEqual(rec.command, "/ask")
        self.assertEqual(rec.description, "查询知识库")
        self.assertEqual(rec.strength, RecommendationStrength.STRONG)
        self.assertEqual(len(rec.reasons), 0)
    
    def test_add_reason(self):
        """测试添加理由"""
        rec = Recommendation(
            command="/ask",
            description="查询知识库",
            strength=RecommendationStrength.STRONG
        )
        reason = RecommendationReason(
            source=RecommendationSource.WORKFLOW,
            explanation="基于工作流",
            confidence=0.8
        )
        rec.add_reason(reason)
        self.assertEqual(len(rec.reasons), 1)
        self.assertEqual(rec.reasons[0], reason)
    
    def test_to_dict(self):
        """测试转换为字典"""
        rec = Recommendation(
            command="/ask",
            description="查询知识库",
            strength=RecommendationStrength.STRONG,
            score=0.75
        )
        reason = RecommendationReason(
            source=RecommendationSource.WORKFLOW,
            explanation="基于工作流",
            confidence=0.8
        )
        rec.add_reason(reason)
        
        rec_dict = rec.to_dict()
        self.assertEqual(rec_dict["command"], "/ask")
        self.assertEqual(rec_dict["strength"], "STRONG")
        self.assertEqual(rec_dict["score"], 0.75)
        self.assertEqual(len(rec_dict["reasons"]), 1)


class TestUserPreference(unittest.TestCase):
    """测试UserPreference类"""
    
    def test_default_preference(self):
        """测试默认偏好"""
        pref = UserPreference()
        self.assertAlmostEqual(pref.prefer_workflow, 0.4)
        self.assertAlmostEqual(pref.prefer_state, 0.3)
        self.assertAlmostEqual(pref.prefer_history, 0.3)
        self.assertTrue(pref.show_explanations)
        self.assertTrue(pref.show_paths)
        self.assertTrue(pref.show_strength)
        self.assertEqual(pref.max_recommendations, 5)
    
    def test_update_weight(self):
        """测试权重更新"""
        pref = UserPreference()
        initial_workflow = pref.prefer_workflow
        
        pref.update_weight("workflow", 0.1)
        
        # 工作流权重应该增加
        self.assertGreater(pref.prefer_workflow, initial_workflow)
        
        # 权重应该归一化
        total = pref.prefer_workflow + pref.prefer_state + pref.prefer_history
        self.assertAlmostEqual(total, 1.0)
    
    def test_hide_recommendation(self):
        """测试隐藏推荐"""
        pref = UserPreference()
        pref.hide_recommendation("/ask")
        
        self.assertTrue(pref.is_hidden("/ask"))
        self.assertFalse(pref.is_hidden("/help"))
    
    def test_hide_recommendation_expiry(self):
        """测试隐藏推荐过期"""
        from datetime import timedelta
        
        pref = UserPreference()
        pref.hide_recommendation("/ask")
        
        # 修改隐藏时间为2小时前
        hide_time = datetime.now() - timedelta(hours=2)
        pref.hidden_recommendations["/ask"] = hide_time
        
        # 应该不再隐藏
        self.assertFalse(pref.is_hidden("/ask"))


class TestCommandHistory(unittest.TestCase):
    """测试CommandHistory类"""
    
    def test_history_creation(self):
        """测试历史记录创建"""
        history = CommandHistory(
            timestamp=datetime.now(),
            command="/ask",
            args="test query",
            result="success"
        )
        self.assertEqual(history.command, "/ask")
        self.assertEqual(history.args, "test query")
        self.assertEqual(history.result, "success")
        self.assertFalse(history.followed_recommendation)
    
    def test_to_dict(self):
        """测试转换为字典"""
        history = CommandHistory(
            timestamp=datetime.now(),
            command="/ask",
            args="test query",
            result="success",
            followed_recommendation=True,
            satisfaction=0.8
        )
        
        history_dict = history.to_dict()
        self.assertEqual(history_dict["command"], "/ask")
        self.assertTrue(history_dict["followed_recommendation"])
        self.assertEqual(history_dict["satisfaction"], 0.8)


class TestWorkflowDefinition(unittest.TestCase):
    """测试WorkflowDefinition类"""
    
    def test_workflow_creation(self):
        """测试工作流定义创建"""
        workflow = WorkflowDefinition(
            name="test_workflow",
            description="测试工作流",
            steps=["/add", "/ask"]
        )
        self.assertEqual(workflow.name, "test_workflow")
        self.assertEqual(workflow.description, "测试工作流")
        self.assertEqual(workflow.steps, ["/add", "/ask"])
    
    def test_is_entry_point(self):
        """测试入口点检查"""
        workflow = WorkflowDefinition(
            name="test_workflow",
            description="测试工作流",
            steps=["/add", "/ask"],
            entry_conditions=["/add"]
        )
        self.assertTrue(workflow.is_entry_point("/add"))
        self.assertFalse(workflow.is_entry_point("/ask"))
    
    def test_get_next_step(self):
        """测试获取下一步"""
        workflow = WorkflowDefinition(
            name="test_workflow",
            description="测试工作流",
            steps=["/add", "/ask", "/history"]
        )
        
        next_step = workflow.get_next_step("/add")
        self.assertEqual(next_step, "/ask")
        
        next_step = workflow.get_next_step("/ask")
        self.assertEqual(next_step, "/history")
        
        next_step = workflow.get_next_step("/history")
        self.assertIsNone(next_step)


class TestStateCondition(unittest.TestCase):
    """测试StateCondition类"""
    
    def test_condition_creation(self):
        """测试状态条件创建"""
        condition = StateCondition(
            name="test_condition",
            description="测试条件",
            check_function="lambda ctx: True",
            recommended_commands=["/ask"],
            weight=0.8
        )
        self.assertEqual(condition.name, "test_condition")
        self.assertEqual(condition.description, "测试条件")
        self.assertEqual(condition.recommended_commands, ["/ask"])
        self.assertAlmostEqual(condition.weight, 0.8)


if __name__ == '__main__':
    unittest.main()