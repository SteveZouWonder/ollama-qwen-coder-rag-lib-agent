#!/usr/bin/env python3
"""
命令推荐系统 - 配置管理
"""
import os
import json
import logging
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Dict, Any, Optional
from .types import UserPreference

logger = logging.getLogger(__name__)


@dataclass
class RecommendationConfig:
    """推荐系统配置"""
    enabled: bool = True
    max_recommendations: int = 5
    min_strength_threshold: float = 0.3
    learning_enabled: bool = True
    show_explanations: bool = True
    show_paths: bool = True
    show_strength: bool = True
    auto_hide_after: Optional[int] = 30
    weights: Dict[str, float] = field(default_factory=lambda: {
        "workflow": 0.4,
        "state": 0.3,
        "history": 0.3
    })
    history_max_size: int = 1000
    preference_file: str = "data/recommender_preferences.json"
    
    def __post_init__(self):
        """初始化后处理，确保路径为绝对路径"""
        if not Path(self.preference_file).is_absolute():
            # 如果是相对路径，转换为相对于项目根目录的绝对路径
            base_dir = Path(__file__).parent.parent.parent
            self.preference_file = str(base_dir / self.preference_file)
    
    def save_preference(self, preference: UserPreference) -> bool:
        """保存用户偏好"""
        try:
            pref_file = Path(self.preference_file)
            pref_file.parent.mkdir(parents=True, exist_ok=True)
            
            with open(pref_file, 'w', encoding='utf-8') as f:
                json.dump(asdict(preference), f, indent=2, default=str)
            
            logger.info(f"用户偏好已保存到 {pref_file}")
            return True
        except Exception as e:
            logger.error(f"保存用户偏好失败: {e}")
            return False
    
    def load_preference(self) -> UserPreference:
        """加载用户偏好"""
        try:
            pref_file = Path(self.preference_file)
            if pref_file.exists():
                with open(pref_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                # 转换 datetime 字符串回 datetime 对象
                if 'last_updated' in data and isinstance(data['last_updated'], str):
                    from datetime import datetime
                    data['last_updated'] = datetime.fromisoformat(data['last_updated'])
                
                if 'hidden_recommendations' in data:
                    from datetime import datetime
                    hidden = {}
                    for cmd, time_str in data['hidden_recommendations'].items():
                        if isinstance(time_str, str):
                            hidden[cmd] = datetime.fromisoformat(time_str)
                    data['hidden_recommendations'] = hidden
                
                preference = UserPreference(**data)
                logger.info(f"用户偏好已加载从 {pref_file}")
                return preference
        except Exception as e:
            logger.warning(f"加载用户偏好失败，使用默认配置: {e}")
        
        return UserPreference()
    
    def update_from_environment(self):
        """从环境变量更新配置"""
        self.enabled = os.getenv("RECOMMENDER_ENABLED", "true").lower() == "true"
        self.max_recommendations = int(os.getenv("RECOMMENDER_MAX", "5"))
        self.min_strength_threshold = float(os.getenv("RECOMMENDER_MIN_STRENGTH", "0.3"))
        self.learning_enabled = os.getenv("RECOMMENDER_LEARNING", "true").lower() == "true"
        self.auto_hide_after = int(os.getenv("RECOMMENDER_AUTO_HIDE", "30")) if os.getenv("RECOMMENDER_AUTO_HIDE") else None


def default_config() -> RecommendationConfig:
    """创建默认配置"""
    config = RecommendationConfig()
    config.update_from_environment()
    return config


# 全局配置实例
_global_config: Optional[RecommendationConfig] = None


def get_config() -> RecommendationConfig:
    """获取全局配置实例"""
    global _global_config
    if _global_config is None:
        _global_config = default_config()
    return _global_config


def reset_config():
    """重置全局配置"""
    global _global_config
    _global_config = None
