#!/usr/bin/env python3
"""
上下文管理器 - 维护会话和系统状态
"""
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime
from .types import CommandContext

logger = logging.getLogger(__name__)


class ContextManager:
    """上下文管理器 - 管理命令执行上下文"""
    
    def __init__(self):
        self.current_context = CommandContext()
        self.context_history: List[CommandContext] = []
        self.max_history = 100
    
    def update_context(self, **kwargs):
        """更新当前上下文"""
        for key, value in kwargs.items():
            if hasattr(self.current_context, key):
                setattr(self.current_context, key, value)
                logger.debug(f"更新上下文 {key} = {value}")
    
    def record_command(self, command: str, args: str = "", result: str = ""):
        """记录命令执行"""
        self.current_context.last_command = command
        self.current_context.last_command_args = args
        self.current_context.last_result = result
        self.current_context.command_count += 1
        
        # 保存上下文快照
        self._save_context_snapshot()
        
        logger.debug(f"记录命令: {command} (总命令数: {self.current_context.command_count})")
    
    def record_error(self, error: str):
        """记录错误"""
        self.current_context.recent_errors.append(error)
        # 只保留最近的5个错误
        if len(self.current_context.recent_errors) > 5:
            self.current_context.recent_errors = self.current_context.recent_errors[-5:]
        
        logger.warning(f"记录错误: {error}")
    
    def clear_errors(self):
        """清空错误记录"""
        self.current_context.recent_errors.clear()
        logger.debug("错误记录已清空")
    
    def set_rag_engine_status(self, available: bool, empty: bool = True):
        """设置RAG引擎状态"""
        self.current_context.rag_engine_available = available
        self.current_context.knowledge_base_empty = empty
        
        logger.debug(f"RAG引擎状态: available={available}, empty={empty}")
    
    def set_snapshot_status(self, has_snapshots: bool):
        """设置快照状态"""
        self.current_context.has_snapshots = has_snapshots
        
        logger.debug(f"快照状态: has_snapshots={has_snapshots}")
    
    def set_mode(self, mode: str):
        """设置当前模式"""
        self.current_context.current_mode = mode
        
        logger.debug(f"设置模式: {mode}")
    
    def add_metadata(self, key: str, value: Any):
        """添加元数据"""
        self.current_context.metadata[key] = value
        
        logger.debug(f"添加元数据: {key} = {value}")
    
    def get_context(self) -> CommandContext:
        """获取当前上下文"""
        return self.current_context
    
    def reset_session(self):
        """重置会话"""
        # 保存当前上下文到历史
        self._save_context_snapshot()
        
        # 重置关键状态
        self.current_context = CommandContext(
            session_start_time=datetime.now(),
            rag_engine_available=self.current_context.rag_engine_available,
            knowledge_base_empty=self.current_context.knowledge_base_empty,
            has_snapshots=self.current_context.has_snapshots
        )
        
        logger.info("会话已重置")
    
    def _save_context_snapshot(self):
        """保存上下文快照"""
        snapshot = CommandContext(
            last_command=self.current_context.last_command,
            last_command_args=self.current_context.last_command_args,
            last_result=self.current_context.last_result,
            rag_engine_available=self.current_context.rag_engine_available,
            knowledge_base_empty=self.current_context.knowledge_base_empty,
            has_snapshots=self.current_context.has_snapshots,
            recent_errors=self.current_context.recent_errors.copy(),
            session_start_time=self.current_context.session_start_time,
            command_count=self.current_context.command_count,
            current_mode=self.current_context.current_mode,
            metadata=self.current_context.metadata.copy()
        )
        
        self.context_history.append(snapshot)
        
        # 限制历史大小
        if len(self.context_history) > self.max_history:
            self.context_history = self.context_history[-self.max_history:]
    
    def get_session_duration(self) -> float:
        """获取会话持续时间（秒）"""
        return (datetime.now() - self.current_context.session_start_time).total_seconds()
    
    def get_activity_summary(self) -> Dict[str, Any]:
        """获取活动摘要"""
        return {
            "session_duration": self.get_session_duration(),
            "command_count": self.current_context.command_count,
            "current_mode": self.current_context.current_mode,
            "rag_available": self.current_context.rag_engine_available,
            "knowledge_empty": self.current_context.knowledge_base_empty,
            "has_snapshots": self.current_context.has_snapshots,
            "error_count": len(self.current_context.recent_errors),
            "last_command": self.current_context.last_command,
            "metadata": self.current_context.metadata
        }
    
    def restore_context(self, index: int = -1):
        """恢复历史上下文"""
        if not self.context_history:
            logger.warning("没有可恢复的上下文历史")
            return
        
        if index < 0:
            index = len(self.context_history) + index
        
        if 0 <= index < len(self.context_history):
            self.current_context = self.context_history[index]
            logger.info(f"恢复上下文快照 {index}")
        else:
            logger.warning(f"无效的上下文索引: {index}")