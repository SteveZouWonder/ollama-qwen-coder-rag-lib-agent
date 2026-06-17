#!/usr/bin/env python3
"""
命令推荐系统 - 数据类型定义
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime
from enum import Enum


class RecommendationStrength(Enum):
    """推荐强度级别"""
    VERY_STRONG = 4
    STRONG = 3
    MODERATE = 2
    WEAK = 1


class RecommendationSource(Enum):
    """推荐来源"""
    WORKFLOW = "workflow"
    STATE = "state"
    HISTORY = "history"
    LEARNING = "learning"


@dataclass
class CommandContext:
    """命令上下文信息"""
    last_command: str = ""
    last_command_args: str = ""
    last_result: str = ""
    rag_engine_available: bool = False
    knowledge_base_empty: bool = True
    has_snapshots: bool = False
    recent_errors: List[str] = field(default_factory=list)
    session_start_time: datetime = field(default_factory=datetime.now)
    command_count: int = 0
    current_mode: str = "auto"
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RecommendationReason:
    """推荐理由"""
    source: RecommendationSource
    explanation: str
    confidence: float
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __str__(self) -> str:
        return f"[{self.source.value}] {self.explanation} (置信度: {self.confidence:.2f})"


@dataclass
class Recommendation:
    """单个推荐命令"""
    command: str
    description: str
    strength: RecommendationStrength
    reasons: List[RecommendationReason] = field(default_factory=list)
    suggested_path: List[str] = field(default_factory=list)
    examples: List[str] = field(default_factory=list)
    score: float = 0.0
    
    def add_reason(self, reason: RecommendationReason):
        """添加推荐理由"""
        self.reasons.append(reason)
        
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "command": self.command,
            "description": self.description,
            "strength": self.strength.name,
            "reasons": [str(r) for r in self.reasons],
            "suggested_path": self.suggested_path,
            "examples": self.examples,
            "score": self.score
        }


@dataclass
class UserPreference:
    """用户偏好设置"""
    prefer_workflow: float = 0.4
    prefer_state: float = 0.3
    prefer_history: float = 0.3
    show_explanations: bool = True
    show_paths: bool = True
    show_strength: bool = True
    auto_hide_after: Optional[int] = 30  # 秒
    max_recommendations: int = 5
    min_strength_threshold: float = 0.3
    hidden_recommendations: Dict[str, datetime] = field(default_factory=dict)
    last_updated: datetime = field(default_factory=datetime.now)
    
    def update_weight(self, source: str, delta: float):
        """更新权重"""
        if source == "workflow":
            self.prefer_workflow = max(0.1, min(0.8, self.prefer_workflow + delta))
        elif source == "state":
            self.prefer_state = max(0.1, min(0.8, self.prefer_state + delta))
        elif source == "history":
            self.prefer_history = max(0.1, min(0.8, self.prefer_history + delta))
        
        # 归一化权重
        total = self.prefer_workflow + self.prefer_state + self.prefer_history
        self.prefer_workflow /= total
        self.prefer_state /= total
        self.prefer_history /= total
        self.last_updated = datetime.now()
    
    def hide_recommendation(self, command: str):
        """隐藏特定推荐"""
        self.hidden_recommendations[command] = datetime.now()
        self.last_updated = datetime.now()
    
    def is_hidden(self, command: str) -> bool:
        """检查推荐是否被隐藏"""
        if command not in self.hidden_recommendations:
            return False
        
        # 1小时后自动取消隐藏
        hide_time = self.hidden_recommendations[command]
        return (datetime.now() - hide_time).seconds < 3600


@dataclass
class CommandHistory:
    """命令历史记录"""
    timestamp: datetime
    command: str
    args: str
    result: str
    followed_recommendation: bool = False
    satisfaction: Optional[float] = None  # 0.0-1.0
    context_snapshot: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "timestamp": self.timestamp.isoformat(),
            "command": self.command,
            "args": self.args,
            "result": self.result,
            "followed_recommendation": self.followed_recommendation,
            "satisfaction": self.satisfaction,
            "context_snapshot": self.context_snapshot
        }


@dataclass
class WorkflowDefinition:
    """工作流定义"""
    name: str
    description: str
    steps: List[str]
    entry_conditions: List[str] = field(default_factory=list)
    completion_commands: List[str] = field(default_factory=list)
    
    def is_entry_point(self, command: str) -> bool:
        """检查是否为工作流入口点"""
        return command in self.entry_conditions
    
    def get_next_step(self, current_step: str) -> Optional[str]:
        """获取下一步"""
        try:
            index = self.steps.index(current_step)
            if index + 1 < len(self.steps):
                return self.steps[index + 1]
        except ValueError:
            pass
        return None


@dataclass
class StateCondition:
    """状态条件"""
    name: str
    description: str
    check_function: str  # 函数名
    recommended_commands: List[str]
    weight: float = 1.0
