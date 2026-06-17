#!/usr/bin/env python3
"""
测试历史分析器
"""
import unittest
from datetime import datetime, timedelta
from src.command_recommender.history import HistoryAnalyzer
from src.command_recommender.types import (
    CommandContext,
    CommandHistory,
    RecommendationStrength,
    RecommendationSource
)


class TestHistoryAnalyzer(unittest.TestCase):
    """测试HistoryAnalyzer类"""
    
    def setUp(self):
        """设置测试环境"""
        self.analyzer = HistoryAnalyzer(max_history=100)
    
    def test_initialization(self):
        """测试初始化"""
        self.assertEqual(self.analyzer.max_history, 100)
        self.assertEqual(len(self.analyzer.command_history), 0)
        self.assertEqual(len(self.analyzer.temporal_patterns), 0)
        self.assertEqual(len(self.analyzer.sequence_patterns), 0)
    
    def test_add_command(self):
        """测试添加命令"""
        history = CommandHistory(
            timestamp=datetime.now(),
            command="/ask",
            args="test",
            result="success"
        )
        
        self.analyzer.add_command(history)
        
        self.assertEqual(len(self.analyzer.command_history), 1)
        self.assertEqual(self.analyzer.command_history[0], history)
    
    def test_add_command_updates_patterns(self):
        """测试添加命令更新模式"""
        history = CommandHistory(
            timestamp=datetime.now(),
            command="/ask",
            args="test",
            result="success"
        )
        
        self.analyzer.add_command(history)
        
        # 时间模式应该更新
        self.assertIn("/ask", self.analyzer.temporal_patterns)
        self.assertEqual(len(self.analyzer.temporal_patterns["/ask"]), 1)
    
    def test_add_command_sequence_patterns(self):
        """测试序列模式更新"""
        history1 = CommandHistory(
            timestamp=datetime.now() - timedelta(seconds=10),
            command="/add",
            args="file.txt",
            result="success"
        )
        
        history2 = CommandHistory(
            timestamp=datetime.now(),
            command="/ask",
            args="query",
            result="success"
        )
        
        self.analyzer.add_command(history1)
        self.analyzer.add_command(history2)
        
        # 序列模式应该更新
        self.assertIn(("/add", "/ask"), self.analyzer.sequence_patterns)
        self.assertEqual(self.analyzer.sequence_patterns[("/add", "/ask")], 1)
    
    def test_history_limit(self):
        """测试历史记录限制"""
        # 添加超过限制的记录
        for i in range(150):
            history = CommandHistory(
                timestamp=datetime.now(),
                command=f"/command_{i % 10}",
                args="test",
                result="success"
            )
            self.analyzer.add_command(history)
        
        # 应该只保留最后100条
        self.assertEqual(len(self.analyzer.command_history), 100)
    
    def test_analyze_frequency(self):
        """测试频率分析"""
        # 添加重复命令
        for _ in range(5):
            history = CommandHistory(
                timestamp=datetime.now(),
                command="/ask",
                args="test",
                result="success"
            )
            self.analyzer.add_command(history)
        
        # 添加其他命令
        for _ in range(2):
            history = CommandHistory(
                timestamp=datetime.now(),
                command="/stats",
                args="",
                result="success"
            )
            self.analyzer.add_command(history)
        
        frequency_scores = self.analyzer.analyze_frequency()
        
        # /ask 应该有更高的频率分数
        self.assertIn("/ask", frequency_scores)
        self.assertIn("/stats", frequency_scores)
        self.assertGreater(frequency_scores["/ask"], frequency_scores["/stats"])
    
    def test_analyze_temporal_patterns(self):
        """测试时间模式分析"""
        # 添加最近命令
        now = datetime.now()
        history = CommandHistory(
            timestamp=now,
            command="/ask",
            args="test",
            result="success"
        )
        self.analyzer.add_command(history)
        
        temporal_scores = self.analyzer.analyze_temporal_patterns()
        
        self.assertIn("/ask", temporal_scores)
        self.assertGreater(temporal_scores["/ask"], 0)
    
    def test_analyze_sequence_patterns(self):
        """测试序列模式分析"""
        # 添加序列：/add -> /ask -> /ask
        history1 = CommandHistory(
            timestamp=datetime.now() - timedelta(seconds=20),
            command="/add",
            args="file.txt",
            result="success"
        )
        
        history2 = CommandHistory(
            timestamp=datetime.now() - timedelta(seconds=10),
            command="/ask",
            args="query",
            result="success"
        )
        
        history3 = CommandHistory(
            timestamp=datetime.now(),
            command="/ask",
            args="query2",
            result="success"
        )
        
        self.analyzer.add_command(history1)
        self.analyzer.add_command(history2)
        self.analyzer.add_command(history3)
        
        # 分析从 /ask 的转移
        sequence_scores = self.analyzer.analyze_sequence_patterns("/ask")
        
        # /ask -> /ask 应该有较高的转移概率
        self.assertIn("/ask", sequence_scores)
    
    def test_analyze_empty_history(self):
        """测试分析空历史"""
        context = CommandContext()
        scores = self.analyzer.analyze(context)
        
        # 空历史应该返回空字典
        self.assertEqual(scores, {})
    
    def test_analyze_combined(self):
        """测试综合分析"""
        # 添加历史数据
        for i in range(10):
            history = CommandHistory(
                timestamp=datetime.now() - timedelta(minutes=i),
                command="/ask" if i % 2 == 0 else "/stats",
                args="test",
                result="success"
            )
            self.analyzer.add_command(history)
        
        context = CommandContext(last_command="/add")
        scores = self.analyzer.analyze(context)
        
        # 应该有推荐分数
        self.assertIsInstance(scores, dict)
        self.assertGreater(len(scores), 0)
    
    def test_get_recommendations(self):
        """测试获取推荐"""
        # 添加历史数据
        for i in range(10):
            history = CommandHistory(
                timestamp=datetime.now() - timedelta(minutes=i),
                command="/ask",
                args="test",
                result="success"
            )
            self.analyzer.add_command(history)
        
        context = CommandContext()
        recommendations = self.analyzer.get_recommendations(context, min_score=0.1)
        
        self.assertIsInstance(recommendations, list)
        self.assertGreater(len(recommendations), 0)
    
    def test_recommendation_strength_levels(self):
        """测试推荐强度级别"""
        # 添加足够多的历史数据
        for i in range(20):
            history = CommandHistory(
                timestamp=datetime.now() - timedelta(minutes=i),
                command="/ask",
                args="test",
                result="success"
            )
            self.analyzer.add_command(history)
        
        context = CommandContext()
        recommendations = self.analyzer.get_recommendations(context, min_score=0.0)
        
        # 检查不同强度级别
        has_very_strong = any(r.strength == RecommendationStrength.VERY_STRONG for r in recommendations)
        has_strong = any(r.strength == RecommendationStrength.STRONG for r in recommendations)
        
        # 至少应该有一个推荐
        self.assertTrue(has_very_strong or has_strong or len(recommendations) > 0)
    
    def test_recommendation_reasons(self):
        """测试推荐理由"""
        # 添加历史数据
        for i in range(5):
            history = CommandHistory(
                timestamp=datetime.now() - timedelta(minutes=i),
                command="/ask",
                args="test",
                result="success"
            )
            self.analyzer.add_command(history)
        
        context = CommandContext()
        recommendations = self.analyzer.get_recommendations(context, min_score=0.1)
        
        if recommendations:
            # 推荐应该有理由
            first_rec = recommendations[0]
            self.assertGreater(len(first_rec.reasons), 0)
            
            # 理由应该来自历史源
            history_reasons = [r for r in first_rec.reasons if r.source == RecommendationSource.HISTORY]
            self.assertGreater(len(history_reasons), 0)
    
    def test_get_statistics(self):
        """测试获取统计信息"""
        # 添加一些历史
        for i in range(5):
            history = CommandHistory(
                timestamp=datetime.now() - timedelta(minutes=i),
                command="/ask",
                args="test",
                result="success"
            )
            self.analyzer.add_command(history)
        
        stats = self.analyzer.get_statistics()
        
        self.assertIn("total_commands", stats)
        self.assertIn("unique_commands", stats)
        self.assertIn("most_frequent", stats)
        self.assertEqual(stats["total_commands"], 5)
    
    def test_get_statistics_empty(self):
        """测试获取空统计信息"""
        stats = self.analyzer.get_statistics()
        
        self.assertEqual(stats["total_commands"], 0)
        self.assertEqual(stats["unique_commands"], 0)
        self.assertIsNone(stats["most_frequent"])
    
    def test_clear_history(self):
        """测试清空历史"""
        # 添加一些数据
        for i in range(5):
            history = CommandHistory(
                timestamp=datetime.now(),
                command="/ask",
                args="test",
                result="success"
            )
            self.analyzer.add_command(history)
        
        self.assertEqual(len(self.analyzer.command_history), 5)
        
        # 清空历史
        self.analyzer.clear_history()
        
        self.assertEqual(len(self.analyzer.command_history), 0)
        self.assertEqual(len(self.analyzer.temporal_patterns), 0)
        self.assertEqual(len(self.analyzer.sequence_patterns), 0)
    
    def test_recent_activity_detection(self):
        """测试最近活动检测"""
        # 添加最近的命令
        history = CommandHistory(
            timestamp=datetime.now(),
            command="/ask",
            args="test",
            result="success"
        )
        self.analyzer.add_command(history)
        
        stats = self.analyzer.get_statistics()
        self.assertTrue(stats["recent_activity"])
    
    def test_old_activity_detection(self):
        """测试旧活动检测"""
        # 添加很久以前的命令
        history = CommandHistory(
            timestamp=datetime.now() - timedelta(hours=2),
            command="/ask",
            args="test",
            result="success"
        )
        self.analyzer.add_command(history)
        
        stats = self.analyzer.get_statistics()
        self.assertFalse(stats["recent_activity"])


if __name__ == '__main__':
    unittest.main()