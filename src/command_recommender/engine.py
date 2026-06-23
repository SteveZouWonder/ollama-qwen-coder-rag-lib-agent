#!/usr/bin/env python3
"""
混合推荐器 - 综合多种推荐源生成最终推荐
"""
import logging
from typing import List, Dict, Optional, Set
from .types import (
    Recommendation,
    CommandContext,
    RecommendationSource,
    CommandHistory
)
from .workflow import WorkflowAnalyzer
from .state import StateAnalyzer
from .history import HistoryAnalyzer
from .context import ContextManager
from .learning import LearningEngine
from .display import DisplayFormatter
from .config import get_config

logger = logging.getLogger(__name__)


class CommandRecommender:
    """命令推荐引擎 - 混合推荐系统"""
    
    def __init__(self, config=None):
        self.config = config or get_config()
        
        # 初始化各个分析器
        self.workflow_analyzer = WorkflowAnalyzer()
        self.state_analyzer = StateAnalyzer()
        self.history_analyzer = HistoryAnalyzer(max_history=self.config.history_max_size)
        self.context_manager = ContextManager()
        self.learning_engine = LearningEngine()
        self.display_formatter = DisplayFormatter(self.learning_engine.preference)
        
        # 系统状态
        self.enabled = self.config.enabled
        self._initialization_complete = False
        
        logger.info("命令推荐引擎初始化完成")
    
    def initialize(self):
        """完成初始化"""
        if self._initialization_complete:
            return
        
        # 加载用户偏好
        if self.learning_engine.preference:
            self.display_formatter.set_preference(self.learning_engine.preference)
        
        self._initialization_complete = True
        logger.info("命令推荐引擎初始化完成")
    
    def record_command(
        self,
        command: str,
        args: str = "",
        result: str = "",
        followed_recommendation: bool = False,
        recommendation_source: Optional[RecommendationSource] = None,
        satisfaction: Optional[float] = None
    ):
        """记录命令执行"""
        # 更新上下文
        self.context_manager.record_command(command, args, result)
        
        # 添加到历史分析器
        history = CommandHistory(
            timestamp=self.context_manager.get_context().session_start_time,
            command=command,
            args=args,
            result=result,
            followed_recommendation=followed_recommendation,
            satisfaction=satisfaction,
            context_snapshot=self.context_manager.get_activity_summary()
        )
        self.history_analyzer.add_command(history)
        
        # 学习用户偏好
        self.learning_engine.record_command_execution(
            command,
            followed_recommendation,
            recommendation_source,
            satisfaction
        )
        
        logger.debug(f"记录命令: {command}")
    
    def record_error(self, error: str):
        """记录错误"""
        self.context_manager.record_error(error)
        logger.warning(f"记录错误: {error}")
    
    def clear_errors(self):
        """清空错误记录"""
        self.context_manager.clear_errors()
    
    def update_rag_status(self, available: bool, empty: bool = True):
        """更新RAG引擎状态"""
        self.context_manager.set_rag_engine_status(available, empty)
    
    def update_snapshot_status(self, has_snapshots: bool):
        """更新快照状态"""
        self.context_manager.set_snapshot_status(has_snapshots)
    
    def set_mode(self, mode: str):
        """设置当前模式"""
        self.context_manager.set_mode(mode)
    
    def get_recommendations(
        self,
        context: Optional[CommandContext] = None,
        min_score: Optional[float] = None
    ) -> List[Recommendation]:
        """获取推荐命令列表"""
        if not self.enabled:
            return []
        
        # 使用提供的上下文或当前上下文
        current_context = context or self.context_manager.get_context()
        
        # 使用配置的最小分数或默认值
        threshold = min_score if min_score is not None else self.config.min_strength_threshold
        
        try:
            # 获取各分析器的推荐
            workflow_recs = self.workflow_analyzer.get_recommendations(current_context, threshold)
            state_recs = self.state_analyzer.get_recommendations(current_context, threshold)
            history_recs = self.history_analyzer.get_recommendations(current_context, threshold)
            
            # 合并推荐
            merged_recs = self._merge_recommendations(
                workflow_recs,
                state_recs,
                history_recs
            )
            
            # 过滤和排序
            # 注意：merged_recs 的分数已乘以各分析器权重（≤0.4），
            # 不能再用原始打分阈值(threshold)过滤，否则几乎全部被滤掉。
            # 这里使用独立的、加权后的展示阈值 display_min_score。
            display_threshold = min_score if min_score is not None else self.config.display_min_score
            final_recs = self._filter_and_sort(merged_recs, display_threshold)
            
            logger.debug(f"生成 {len(final_recs)} 个推荐")
            return final_recs
            
        except Exception as e:
            logger.error(f"生成推荐时出错: {e}")
            return []
    
    def _merge_recommendations(
        self,
        workflow_recs: List[Recommendation],
        state_recs: List[Recommendation],
        history_recs: List[Recommendation]
    ) -> List[Recommendation]:
        """合并来自不同源的推荐"""
        merged: Dict[str, Recommendation] = {}
        
        # 获取用户权重
        weights = self.learning_engine.get_weights()
        workflow_weight = weights.get("workflow", 0.4)
        state_weight = weights.get("state", 0.3)
        history_weight = weights.get("history", 0.3)
        
        def _merge_source(recs, weight, source):
            for rec in recs:
                weighted = rec.score * weight
                if rec.command not in merged:
                    # 首次加入：直接使用该对象，其自带的 reasons 已存在，
                    # 不要再次迭代 rec.reasons 往自身追加（会造成无限循环）。
                    merged[rec.command] = rec
                    rec.score = weighted
                else:
                    target = merged[rec.command]
                    target.score = max(target.score, weighted)
                    # 合并到已有的不同对象上，仅补充该来源的理由
                    if target is not rec:
                        for reason in rec.reasons:
                            if reason.source == source:
                                target.add_reason(reason)

        # 合并工作流推荐
        _merge_source(workflow_recs, workflow_weight, RecommendationSource.WORKFLOW)
        # 合并状态推荐
        _merge_source(state_recs, state_weight, RecommendationSource.STATE)
        # 合并历史推荐
        _merge_source(history_recs, history_weight, RecommendationSource.HISTORY)
        
        return list(merged.values())
    
    def _filter_and_sort(
        self,
        recommendations: List[Recommendation],
        min_score: float
    ) -> List[Recommendation]:
        """过滤和排序推荐"""
        # 过滤隐藏的推荐
        filtered = [
            rec for rec in recommendations
            if rec.score >= min_score and not self.learning_engine.is_hidden(rec.command)
        ]
        
        # 按分数排序
        filtered.sort(key=lambda x: x.score, reverse=True)
        
        # 限制数量
        max_recs = self.learning_engine.get_display_preferences().get("max_recommendations", 5)
        return filtered[:max_recs]
    
    def format_recommendations(
        self,
        recommendations: List[Recommendation],
        use_rich: bool = True,
        compact: bool = False
    ) -> str:
        """格式化推荐供显示"""
        if not recommendations:
            return ""
        
        try:
            return self.display_formatter.format_recommendations(
                recommendations,
                use_rich=use_rich,
                compact=compact
            )
        except Exception as e:
            logger.error(f"格式化推荐时出错: {e}")
            return ""
    
    def execute_recommendation(self, index: int = 0) -> Optional[str]:
        """执行推荐命令（返回命令字符串供调用者执行）"""
        recommendations = self.get_recommendations()
        if index < len(recommendations):
            return recommendations[index].command
        return None
    
    def hide_recommendation(self, command: str):
        """隐藏特定推荐"""
        self.learning_engine.hide_recommendation(command)
    
    def update_display_preferences(
        self,
        show_explanations: Optional[bool] = None,
        show_paths: Optional[bool] = None,
        show_strength: Optional[bool] = None,
        auto_hide_after: Optional[int] = None,
        max_recommendations: Optional[int] = None
    ):
        """更新显示偏好"""
        self.learning_engine.update_display_preferences(
            show_explanations,
            show_paths,
            show_strength,
            auto_hide_after,
            max_recommendations
        )
        # 更新格式化器的偏好
        self.display_formatter.set_preference(self.learning_engine.preference)
    
    def reset_preferences(self):
        """重置所有偏好"""
        self.learning_engine.reset_preferences()
        self.display_formatter.set_preference(self.learning_engine.preference)
        self.history_analyzer.clear_history()
        logger.info("推荐系统偏好已重置")
    
    def get_statistics(self) -> Dict[str, any]:
        """获取推荐系统统计信息"""
        return {
            "enabled": self.enabled,
            "workflow_stats": {
                "total_workflows": len(self.workflow_analyzer.workflows),
                "active_workflows": len(self.workflow_analyzer.workflow_map)
            },
            "history_stats": self.history_analyzer.get_statistics(),
            "context_info": self.context_manager.get_activity_summary(),
            "preference_info": self.learning_engine.get_preference_info(),
            "learning_enabled": self.config.learning_enabled
        }
    
    def enable(self):
        """启用推荐系统"""
        self.enabled = True
        logger.info("推荐系统已启用")
    
    def disable(self):
        """禁用推荐系统"""
        self.enabled = False
        logger.info("推荐系统已禁用")
    
    def is_enabled(self) -> bool:
        """检查推荐系统是否启用"""
        return self.enabled