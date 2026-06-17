#!/usr/bin/env python3
"""
命令推荐系统 - 智能推荐下一步可能需要执行的命令
基于工作流分析、状态感知、历史分析和用户学习的混合推荐引擎
"""
from .config import RecommendationConfig, default_config
from .types import (
    CommandContext,
    Recommendation,
    RecommendationReason,
    UserPreference,
    CommandHistory
)
from .workflow import WorkflowAnalyzer
from .state import StateAnalyzer
from .history import HistoryAnalyzer
from .context import ContextManager
from .learning import LearningEngine
from .display import DisplayFormatter
from .engine import CommandRecommender

__all__ = [
    'RecommendationConfig',
    'default_config',
    'CommandContext',
    'Recommendation',
    'RecommendationReason',
    'UserPreference',
    'CommandHistory',
    'WorkflowAnalyzer',
    'StateAnalyzer',
    'HistoryAnalyzer',
    'ContextManager',
    'LearningEngine',
    'DisplayFormatter',
    'CommandRecommender'
]

__version__ = '1.0.0'
