#!/usr/bin/env python3
"""
状态感知器 - 根据系统状态动态推荐命令
"""
import logging
from typing import Dict, List, Callable
from .types import (
    Recommendation,
    RecommendationReason,
    RecommendationSource,
    RecommendationStrength,
    CommandContext
)

logger = logging.getLogger(__name__)


class StateAnalyzer:
    """状态感知器 - 基于系统状态推荐命令"""
    
    def __init__(self):
        self.state_conditions = self._initialize_conditions()
    
    def _initialize_conditions(self) -> Dict[str, Dict]:
        """初始化状态条件"""
        return {
            "empty_knowledge_base": {
                "check": lambda ctx: ctx.knowledge_base_empty and ctx.rag_engine_available,
                "commands": ["/add", "/tutorial", "/help"],
                "weight": 0.8,
                "description": "知识库为空，建议添加文档"
            },
            "has_documents": {
                "check": lambda ctx: not ctx.knowledge_base_empty and ctx.rag_engine_available,
                "commands": ["/ask", "/stats", "/generate-skills"],
                "weight": 0.7,
                "description": "已有文档，可以开始查询"
            },
            "has_snapshots": {
                "check": lambda ctx: ctx.has_snapshots,
                "commands": ["/snapshot-restore", "/snapshot-list"],
                "weight": 0.6,
                "description": "有可用快照，可以恢复或查看"
            },
            "recent_search": {
                "check": lambda ctx: ctx.last_command in ["/ask", "/agent-rag", "/graph-query"],
                "commands": ["/sources", "/history", "/ask"],
                "weight": 0.65,
                "description": "最近进行了查询，可以查看来源或继续查询"
            },
            "recent_errors": {
                "check": lambda ctx: len(ctx.recent_errors) > 0,
                "commands": ["/clear", "/history", "/config"],
                "weight": 0.75,
                "description": "最近有错误，建议清理或检查配置"
            },
            "new_session": {
                "check": lambda ctx: ctx.command_count == 0,
                "commands": ["/tutorial", "/stats", "/file-list"],
                "weight": 0.7,
                "description": "新会话开始，建议查看系统状态"
            },
            "active_development": {
                "check": lambda ctx: ctx.last_command in ["/agent-file", "/agent-rag", "/agent-web"],
                "commands": ["/ask", "/history", "/agent-file"],
                "weight": 0.6,
                "description": "正在进行开发，可以查询知识库或继续文件操作"
            },
            "management_mode": {
                "check": lambda ctx: ctx.last_command in ["/file-list", "/file-info", "/snapshot-list"],
                "commands": ["/add", "/snapshot-create", "/file-delete"],
                "weight": 0.65,
                "description": "管理模式，可以进行文件和快照操作"
            },
            "learning_mode": {
                "check": lambda ctx: ctx.last_command in ["/tutorial", "/help", "/tools"],
                "commands": ["/ask", "/add", "/stats"],
                "weight": 0.6,
                "description": "学习模式，可以开始实际操作"
            },
            "idle_state": {
                "check": lambda ctx: ctx.command_count > 0 and ctx.last_command in ["/clear", "/exit"],
                "commands": ["/tutorial", "/stats", "/file-list"],
                "weight": 0.5,
                "description": "空闲状态，可以开始新的任务"
            }
        }
    
    def analyze(self, context: CommandContext) -> Dict[str, float]:
        """分析上下文状态，返回命令推荐得分"""
        scores = {}
        
        for condition_name, condition_info in self.state_conditions.items():
            try:
                check_func = condition_info["check"]
                if check_func(context):
                    weight = condition_info["weight"]
                    commands = condition_info["commands"]
                    
                    for cmd in commands:
                        scores[cmd] = max(scores.get(cmd, 0), weight)
                        
                    logger.debug(f"状态条件 '{condition_name}' 匹配，推荐: {commands}")
            except Exception as e:
                logger.warning(f"检查状态条件 '{condition_name}' 时出错: {e}")
        
        return scores
    
    def get_recommendations(self, context: CommandContext, min_score: float = 0.3) -> List[Recommendation]:
        """获取状态感知推荐"""
        recommendations = []
        scores = self.analyze(context)
        
        command_descriptions = {
            "/add": "添加文档到知识库",
            "/ask": "查询知识库内容",
            "/stats": "查看知识库统计信息",
            "/sources": "查看查询结果的来源",
            "/history": "查看命令历史",
            "/clear": "清空会话历史",
            "/config": "查看或修改配置",
            "/tutorial": "显示使用教程",
            "/help": "显示帮助信息",
            "/tools": "查看可用工具",
            "/snapshot-restore": "恢复知识库快照",
            "/snapshot-list": "查看快照列表",
            "/snapshot-create": "创建知识库快照",
            "/generate-skills": "将知识库转换为Skills",
            "/file-list": "列出知识库中的文件",
            "/file-info": "查看文件详细信息",
            "/file-delete": "删除文件",
            "/agent-file": "使用Agent进行文件操作",
            "/agent-rag": "使用Agent进行RAG查询",
            "/agent-web": "使用Agent进行网络搜索"
        }
        
        for command, score in scores.items():
            if score >= min_score:
                # 确定推荐强度
                if score >= 0.75:
                    strength = RecommendationStrength.VERY_STRONG
                elif score >= 0.6:
                    strength = RecommendationStrength.STRONG
                elif score >= 0.4:
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
                    source=RecommendationSource.STATE,
                    explanation=f"基于当前系统状态推荐",
                    confidence=score
                )
                recommendation.add_reason(reason)
                
                recommendations.append(recommendation)
        
        return sorted(recommendations, key=lambda x: x.score, reverse=True)
    
    def get_state_description(self, context: CommandContext) -> str:
        """获取当前状态的描述"""
        matched_conditions = []
        
        for condition_name, condition_info in self.state_conditions.items():
            try:
                if condition_info["check"](context):
                    matched_conditions.append(condition_info["description"])
            except Exception as e:
                logger.warning(f"检查状态条件时出错: {e}")
        
        if matched_conditions:
            return "; ".join(matched_conditions)
        return "正常运行状态"