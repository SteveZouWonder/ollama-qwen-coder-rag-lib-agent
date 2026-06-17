#!/usr/bin/env python3
"""
历史分析器 - 基于用户使用频率分析推荐
"""
import logging
from typing import List, Dict, Tuple, Optional
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from .types import (
    Recommendation,
    RecommendationReason,
    RecommendationSource,
    RecommendationStrength,
    CommandHistory,
    CommandContext
)

logger = logging.getLogger(__name__)


class HistoryAnalyzer:
    """历史分析器 - 基于命令历史推荐"""
    
    def __init__(self, max_history: int = 1000):
        self.max_history = max_history
        self.command_history: List[CommandHistory] = []
        self.temporal_patterns: Dict[str, List[datetime]] = defaultdict(list)
        self.sequence_patterns: Dict[Tuple[str, str], int] = defaultdict(int)
    
    def add_command(self, history: CommandHistory):
        """添加命令历史记录"""
        self.command_history.append(history)
        
        # 限制历史记录大小
        if len(self.command_history) > self.max_history:
            self.command_history = self.command_history[-self.max_history:]
        
        # 更新时间模式
        command_key = history.command
        self.temporal_patterns[command_key].append(history.timestamp)
        
        # 更新序列模式
        if len(self.command_history) >= 2:
            prev_cmd = self.command_history[-2].command
            curr_cmd = history.command
            self.sequence_patterns[(prev_cmd, curr_cmd)] += 1
        
        logger.debug(f"添加命令历史: {history.command}")
    
    def analyze_frequency(self) -> Dict[str, float]:
        """分析命令频率"""
        if not self.command_history:
            return {}
        
        counter = Counter(record.command for record in self.command_history)
        total = len(self.command_history)
        
        # 计算相对频率
        frequency_scores = {}
        for cmd, count in counter.items():
            frequency_scores[cmd] = count / total
        
        return frequency_scores
    
    def analyze_temporal_patterns(self) -> Dict[str, float]:
        """分析时间模式"""
        if not self.command_history:
            return {}
        
        now = datetime.now()
        temporal_scores = {}
        
        for cmd, timestamps in self.temporal_patterns.items():
            if not timestamps:
                continue
            
            # 计算最近使用情况（权重递减）
            recent_weight = 0
            for timestamp in timestamps:
                time_diff = (now - timestamp).total_seconds()
                # 越近的命令权重越高
                if time_diff < 3600:  # 1小时内
                    recent_weight += 1.0
                elif time_diff < 86400:  # 24小时内
                    recent_weight += 0.5
                elif time_diff < 604800:  # 7天内
                    recent_weight += 0.2
            
            temporal_scores[cmd] = recent_weight / len(timestamps)
        
        return temporal_scores
    
    def analyze_sequence_patterns(self, last_command: str) -> Dict[str, float]:
        """分析序列模式"""
        if not last_command:
            return {}
        
        sequence_scores = {}
        total_transitions = sum(count for (prev, _), count in self.sequence_patterns.items() if prev == last_command)
        
        if total_transitions == 0:
            return {}
        
        for (prev_cmd, next_cmd), count in self.sequence_patterns.items():
            if prev_cmd == last_command:
                # 计算转移概率
                probability = count / total_transitions
                sequence_scores[next_cmd] = probability
        
        return sequence_scores
    
    def analyze(self, context: CommandContext) -> Dict[str, float]:
        """综合分析历史记录"""
        frequency_scores = self.analyze_frequency()
        temporal_scores = self.analyze_temporal_patterns()
        sequence_scores = self.analyze_sequence_patterns(context.last_command)
        
        # 综合得分
        combined_scores = {}
        
        # 合并频率得分 (权重 0.4)
        for cmd, score in frequency_scores.items():
            combined_scores[cmd] = combined_scores.get(cmd, 0) + 0.4 * score
        
        # 合并时间得分 (权重 0.3)
        for cmd, score in temporal_scores.items():
            combined_scores[cmd] = combined_scores.get(cmd, 0) + 0.3 * score
        
        # 合并序列得分 (权重 0.3)
        for cmd, score in sequence_scores.items():
            combined_scores[cmd] = combined_scores.get(cmd, 0) + 0.3 * score
        
        return combined_scores
    
    def get_recommendations(self, context: CommandContext, min_score: float = 0.3) -> List[Recommendation]:
        """获取历史分析推荐"""
        recommendations = []
        scores = self.analyze(context)
        
        command_descriptions = {
            "/ask": "查询知识库内容",
            "/stats": "查看知识库统计信息",
            "/sources": "查看查询结果的来源",
            "/history": "查看命令历史",
            "/clear": "清空会话历史",
            "/add": "添加文档到知识库",
            "/tutorial": "显示使用教程",
            "/help": "显示帮助信息",
            "/tools": "查看可用工具",
            "/file-list": "列出知识库中的文件",
            "/agent-file": "使用Agent进行文件操作",
            "/agent-rag": "使用Agent进行RAG查询",
            "/agent-web": "使用Agent进行网络搜索"
        }
        
        for command, score in scores.items():
            if score >= min_score:
                # 确定推荐强度
                if score >= 0.7:
                    strength = RecommendationStrength.VERY_STRONG
                elif score >= 0.5:
                    strength = RecommendationStrength.STRONG
                elif score >= 0.3:
                    strength = RecommendationStrength.MODERATE
                else:
                    strength = RecommendationStrength.WEAK
                
                # 获取描述
                description = command_descriptions.get(command, f"执行 {command} 命令")
                
                # 创建推荐
                recommendation = Recommendation(
                    command=command,
                    description=description,
                    strength=strength,
                    score=score
                )
                
                # 添加理由
                reason = RecommendationReason(
                    source=RecommendationSource.HISTORY,
                    explanation=f"基于使用历史和模式分析推荐",
                    confidence=score
                )
                recommendation.add_reason(reason)
                
                recommendations.append(recommendation)
        
        return sorted(recommendations, key=lambda x: x.score, reverse=True)
    
    def get_statistics(self) -> Dict[str, any]:
        """获取历史统计信息"""
        if not self.command_history:
            return {
                "total_commands": 0,
                "unique_commands": 0,
                "most_frequent": None,
                "recent_activity": False
            }
        
        counter = Counter(record.command for record in self.command_history)
        most_frequent = counter.most_common(1)[0] if counter else None
        
        # 检查最近是否有活动
        recent_activity = False
        if self.command_history:
            last_activity = self.command_history[-1].timestamp
            recent_activity = (datetime.now() - last_activity).total_seconds() < 3600
        
        return {
            "total_commands": len(self.command_history),
            "unique_commands": len(counter),
            "most_frequent": most_frequent,
            "recent_activity": recent_activity
        }
    
    def clear_history(self):
        """清空历史记录"""
        self.command_history.clear()
        self.temporal_patterns.clear()
        self.sequence_patterns.clear()
        logger.info("命令历史已清空")