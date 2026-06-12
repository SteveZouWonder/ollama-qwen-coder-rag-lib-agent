"""
会话管理器 - 提供多会话管理、历史压缩、会话搜索等功能
"""
import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import List, Dict, Optional

from config import (
    MAX_SESSIONS,
    MAX_MESSAGES_PER_SESSION,
    AUTO_ARCHIVE_DAYS,
    HISTORY_COMPRESSION_RATIO,
    AUTO_COMPRESS_ENABLED
)

logger = logging.getLogger(__name__)


class SessionStatus(Enum):
    """会话状态"""
    ACTIVE = "active"
    ARCHIVED = "archived"
    DELETED = "deleted"


@dataclass
class ChatSession:
    """聊天会话"""
    session_id: str
    title: str
    created_at: datetime
    updated_at: datetime
    status: SessionStatus
    messages: List[Dict] = field(default_factory=list)
    metadata: Dict = field(default_factory=dict)
    tags: List[str] = field(default_factory=list)

    def add_message(self, role: str, content: str):
        """添加消息"""
        self.messages.append({
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat()
        })
        self.updated_at = datetime.now()

    def get_summary(self) -> str:
        """获取会话摘要"""
        if len(self.messages) < 2:
            return self.title

        # 提取前几条用户消息作为摘要
        user_messages = [m for m in self.messages if m["role"] == "user"]
        if user_messages:
            first_msg = user_messages[0]["content"]
            return first_msg[:50] + "..." if len(first_msg) > 50 else first_msg

        return self.title

    def to_dict(self) -> Dict:
        """转换为字典"""
        return {
            "session_id": self.session_id,
            "title": self.title,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "status": self.status.value,
            "messages": self.messages,
            "metadata": self.metadata,
            "tags": self.tags
        }

    @classmethod
    def from_dict(cls, data: Dict) -> 'ChatSession':
        """从字典创建实例"""
        return cls(
            session_id=data["session_id"],
            title=data["title"],
            created_at=datetime.fromisoformat(data["created_at"]),
            updated_at=datetime.fromisoformat(data["updated_at"]),
            status=SessionStatus(data["status"]),
            messages=data["messages"],
            metadata=data.get("metadata", {}),
            tags=data.get("tags", [])
        )


class SessionManager:
    """会话管理器"""

    def __init__(self, storage_path: str):
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self.current_session_id: Optional[str] = None
        self.sessions: Dict[str, ChatSession] = {}
        self.load_sessions()

    def create_session(self, title: str = None, tags: List[str] = None) -> ChatSession:
        """
        创建新会话

        Args:
            title: 会话标题
            tags: 会话标签

        Returns:
            创建的会话对象
        """
        session_id = str(uuid.uuid4())
        if title is None:
            title = f"会话 {datetime.now().strftime('%Y-%m-%d %H:%M')}"

        session = ChatSession(
            session_id=session_id,
            title=title,
            created_at=datetime.now(),
            updated_at=datetime.now(),
            status=SessionStatus.ACTIVE,
            tags=tags or []
        )

        self.sessions[session_id] = session
        self.current_session_id = session_id
        self.save_session(session)

        logger.info(f"新会话已创建: {session_id} - {title}")
        return session

    def switch_session(self, session_id: str) -> bool:
        """
        切换会话

        Args:
            session_id: 会话ID

        Returns:
            是否切换成功
        """
        if session_id not in self.sessions:
            return False

        if self.sessions[session_id].status == SessionStatus.DELETED:
            return False

        self.current_session_id = session_id
        self.sessions[session_id].status = SessionStatus.ACTIVE
        self.sessions[session_id].updated_at = datetime.now()
        self.save_session(self.sessions[session_id])

        logger.info(f"会话已切换: {session_id}")
        return True

    def archive_session(self, session_id: str) -> bool:
        """
        归档会话

        Args:
            session_id: 会话ID

        Returns:
            是否归档成功
        """
        if session_id not in self.sessions:
            return False

        self.sessions[session_id].status = SessionStatus.ARCHIVED
        self.sessions[session_id].updated_at = datetime.now()
        self.save_session(self.sessions[session_id])

        logger.info(f"会话已归档: {session_id}")
        return True

    def delete_session(self, session_id: str) -> bool:
        """
        删除会话

        Args:
            session_id: 会话ID

        Returns:
            是否删除成功
        """
        if session_id not in self.sessions:
            return False

        self.sessions[session_id].status = SessionStatus.DELETED
        session_file = self.storage_path / f"{session_id}.json"

        if session_file.exists():
            session_file.unlink()

        del self.sessions[session_id]

        if self.current_session_id == session_id:
            self.current_session_id = None

        logger.info(f"会话已删除: {session_id}")
        return True

    def get_current_session(self) -> Optional[ChatSession]:
        """
        获取当前会话

        Returns:
            当前会话对象，如果不存在则返回None
        """
        if self.current_session_id is None:
            return None
        return self.sessions.get(self.current_session_id)

    def list_sessions(self, status: SessionStatus = None, tags: List[str] = None) -> List[ChatSession]:
        """
        列出会话

        Args:
            status: 会话状态过滤
            tags: 标签过滤

        Returns:
            会话列表
        """
        sessions = list(self.sessions.values())

        if status:
            sessions = [s for s in sessions if s.status == status]

        if tags:
            sessions = [s for s in sessions if any(tag in s.tags for tag in tags)]

        # 按更新时间排序
        sessions.sort(key=lambda x: x.updated_at, reverse=True)

        return sessions

    def search_sessions(self, query: str) -> List[ChatSession]:
        """
        搜索会话

        Args:
            query: 搜索查询

        Returns:
            匹配的会话列表
        """
        query_lower = query.lower()
        results = []

        for session in self.sessions.values():
            # 搜索标题
            if query_lower in session.title.lower():
                results.append(session)
                continue

            # 搜索消息内容
            for message in session.messages:
                if query_lower in message["content"].lower():
                    results.append(session)
                    break

        return results

    def save_session(self, session: ChatSession):
        """
        保存会话

        Args:
            session: 会话对象
        """
        session_file = self.storage_path / f"{session.session_id}.json"

        session_data = session.to_dict()

        with open(session_file, 'w', encoding='utf-8') as f:
            json.dump(session_data, f, ensure_ascii=False, indent=2)

    def load_sessions(self):
        """加载所有会话"""
        for session_file in self.storage_path.glob("*.json"):
            try:
                with open(session_file, 'r', encoding='utf-8') as f:
                    session_data = json.load(f)

                if session_data["status"] == SessionStatus.DELETED.value:
                    continue

                session = ChatSession.from_dict(session_data)
                self.sessions[session.session_id] = session

            except Exception as e:
                logger.error(f"加载会话失败 {session_file}: {e}")

        logger.info(f"加载了 {len(self.sessions)} 个会话")

    def get_stats(self) -> Dict:
        """
        获取统计信息

        Returns:
            统计信息字典
        """
        total_sessions = len(self.sessions)
        active_sessions = sum(1 for s in self.sessions.values() if s.status == SessionStatus.ACTIVE)
        archived_sessions = sum(1 for s in self.sessions.values() if s.status == SessionStatus.ARCHIVED)
        total_messages = sum(len(s.messages) for s in self.sessions.values())

        return {
            "total_sessions": total_sessions,
            "active_sessions": active_sessions,
            "archived_sessions": archived_sessions,
            "total_messages": total_messages,
            "current_session": self.current_session_id
        }


class SmartSessionManager(SessionManager):
    """智能会话管理器（扩展功能）"""

    def __init__(self, storage_path: str):
        super().__init__(storage_path)
        self.compressor = None  # 延迟加载

    def auto_compress_current_session(self):
        """自动压缩当前会话"""
        if not AUTO_COMPRESS_ENABLED:
            return

        current = self.get_current_session()
        if current and len(current.messages) > MAX_MESSAGES_PER_SESSION:
            if self.compressor is None:
                from history_compressor import HistoryCompressor
                self.compressor = HistoryCompressor(HISTORY_COMPRESSION_RATIO)

            compressed_messages = self.compressor.compress_history(current.messages)
            current.messages = compressed_messages
            self.save_session(current)

            logger.info(f"当前会话已自动压缩: {len(compressed_messages)} 条消息")

    def auto_archive_old_sessions(self):
        """自动归档旧会话"""
        cutoff_date = datetime.now() - timedelta(days=AUTO_ARCHIVE_DAYS)

        for session in self.sessions.values():
            if (session.status == SessionStatus.ACTIVE and
                session.updated_at < cutoff_date and
                session.session_id != self.current_session_id):
                self.archive_session(session.session_id)

    def suggest_session_switch(self, current_query: str) -> Optional[str]:
        """
        建议切换会话

        Args:
            current_query: 当前查询内容

        Returns:
            建议切换的会话ID，如果没有建议则返回None
        """
        if not current_query:
            return None

        # 搜索相关会话
        related_sessions = self.search_sessions(current_query)

        # 排除当前会话
        related_sessions = [s for s in related_sessions
                          if s.session_id != self.current_session_id]

        # 优先返回活跃会话
        active_sessions = [s for s in related_sessions if s.status == SessionStatus.ACTIVE]
        if active_sessions:
            return active_sessions[0].session_id

        if related_sessions:
            return related_sessions[0].session_id

        return None
