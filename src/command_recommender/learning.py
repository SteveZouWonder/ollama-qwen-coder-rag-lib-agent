#!/usr/bin/env python3
"""
学习引擎 - 记录用户行为和偏好学习
"""
import logging
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
from .types import UserPreference, CommandHistory, RecommendationSource
from .config import get_config

logger = logging.getLogger(__name__)


class LearningEngine:
    """学习引擎 - 学习用户偏好并调整推荐"""
    
    def __init__(self):
        self.preference: Optional[UserPreference] = None
        self.config = get_config()
        self._load_preference()
    
    def _load_preference(self):
        """加载用户偏好"""
        self.preference = self.config.load_preference()
        logger.info("用户偏好已加载")
    
    def _save_preference(self):
        """保存用户偏好"""
        if self.preference:
            success = self.config.save_preference(self.preference)
            if success:
                logger.info("用户偏好已保存")
    
    def record_command_execution(
        self,
        command: str,
        followed_recommendation: bool = False,
        recommendation_source: Optional[RecommendationSource] = None,
        satisfaction: Optional[float] = None
    ):
        """记录命令执行，用于学习用户偏好"""
        if not self.config.learning_enabled:
            return
        
        if followed_recommendation and recommendation_source:
            # 如果用户跟随了推荐，增加该来源的权重
            delta = 0.05  # 每次跟随推荐增加5%权重
            
            if recommendation_source == RecommendationSource.WORKFLOW:
                self.preference.update_weight("workflow", delta)
            elif recommendation_source == RecommendationSource.STATE:
                self.preference.update_weight("state", delta)
            elif recommendation_source == RecommendationSource.HISTORY:
                self.preference.update_weight("history", delta)
            
            self._save_preference()
            logger.debug(f"更新权重: {recommendation_source.value} +{delta}")
        
        # 记录满意度（如果提供）
        if satisfaction is not None:
            self._record_satisfaction(command, satisfaction)
    
    def _record_satisfaction(self, command: str, satisfaction: float):
        """记录用户对特定命令的满意度"""
        # 这里可以扩展为存储每个命令的满意度历史
        logger.debug(f"记录满意度 {command}: {satisfaction}")
    
    def hide_recommendation(self, command: str):
        """隐藏特定推荐"""
        if self.preference:
            self.preference.hide_recommendation(command)
            self._save_preference()
            logger.info(f"隐藏推荐: {command}")
    
    def is_hidden(self, command: str) -> bool:
        """检查推荐是否被隐藏"""
        if self.preference:
            return self.preference.is_hidden(command)
        return False
    
    def get_weights(self) -> Dict[str, float]:
        """获取当前推荐权重"""
        if self.preference:
            return {
                "workflow": self.preference.prefer_workflow,
                "state": self.preference.prefer_state,
                "history": self.preference.prefer_history
            }
        return {"workflow": 0.4, "state": 0.3, "history": 0.3}
    
    def get_display_preferences(self) -> Dict[str, Any]:
        """获取显示偏好"""
        if self.preference:
            return {
                "show_explanations": self.preference.show_explanations,
                "show_paths": self.preference.show_paths,
                "show_strength": self.preference.show_strength,
                "auto_hide_after": self.preference.auto_hide_after,
                "max_recommendations": self.preference.max_recommendations
            }
        return {
            "show_explanations": True,
            "show_paths": True,
            "show_strength": True,
            "auto_hide_after": 30,
            "max_recommendations": 5
        }
    
    def update_display_preferences(
        self,
        show_explanations: Optional[bool] = None,
        show_paths: Optional[bool] = None,
        show_strength: Optional[bool] = None,
        auto_hide_after: Optional[int] = None,
        max_recommendations: Optional[int] = None
    ):
        """更新显示偏好"""
        if not self.preference:
            return
        
        if show_explanations is not None:
            self.preference.show_explanations = show_explanations
        if show_paths is not None:
            self.preference.show_paths = show_paths
        if show_strength is not None:
            self.preference.show_strength = show_strength
        if auto_hide_after is not None:
            self.preference.auto_hide_after = auto_hide_after
        if max_recommendations is not None:
            self.preference.max_recommendations = max_recommendations
        
        self.preference.last_updated = datetime.now()
        self._save_preference()
        logger.info("显示偏好已更新")
    
    def reset_preferences(self):
        """重置用户偏好到默认值"""
        self.preference = UserPreference()
        self._save_preference()
        logger.info("用户偏好已重置")
    
    def get_preference_info(self) -> Dict[str, Any]:
        """获取偏好信息"""
        if self.preference:
            return {
                "weights": self.get_weights(),
                "display": self.get_display_preferences(),
                "hidden_count": len(self.preference.hidden_recommendations),
                "last_updated": self.preference.last_updated.isoformat()
            }
        return {}
    
    def analyze_user_patterns(self, command_history: list) -> Dict[str, Any]:
        """分析用户行为模式"""
        if not command_history:
            return {"pattern": "insufficient_data"}
        
        # 简单模式分析
        from collections import Counter
        command_counter = Counter(cmd.command for cmd in command_history)
        
        # 确定主要模式
        if command_counter:
            most_common = command_counter.most_common(1)[0]
            dominant_command = most_common[0]
            frequency = most_common[1] / len(command_history)
            
            if frequency > 0.5:
                pattern_type = "focused"
            elif frequency > 0.3:
                pattern_type = "semi_focused"
            else:
                pattern_type = "exploratory"
        else:
            pattern_type = "unknown"
        
        return {
            "pattern": pattern_type,
            "dominant_command": dominant_command if command_counter else None,
            "total_commands": len(command_history),
            "unique_commands": len(command_counter),
            "most_frequent": command_counter.most_common(3) if command_counter else []
        }