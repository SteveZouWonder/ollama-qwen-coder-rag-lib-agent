"""
文件元数据管理 - 提供文件分类、持久化类型管理、清理等功能
"""
import json
import logging
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict

from config import TEMPORARY_FILE_TTL_HOURS

logger = logging.getLogger(__name__)


class FilePersistenceType(Enum):
    """文件持久化类型"""
    PERMANENT = "permanent"  # 永久保存
    TEMPORARY = "temporary"  # 临时保存（24小时后自动清理）
    SESSION = "session"     # 会话级别（当前会话结束清理）


@dataclass
class FileMetadata:
    """文件元数据"""
    file_path: str
    persistence_type: str
    upload_time: str
    file_hash: Optional[str] = None
    access_count: int = 0
    last_access: Optional[str] = None
    file_size: int = 0
    document_count: int = 0  # 知识库中的文档数量
    chunk_count: int = 0     # 知识库中的chunk数量
    tags: List[str] = None  # 文件标签

    def __post_init__(self):
        if self.tags is None:
            self.tags = []

    def mark_access(self):
        """标记文件访问"""
        self.access_count += 1
        self.last_access = datetime.now().isoformat()

    def should_cleanup(self) -> bool:
        """
        检查文件是否应该清理

        Returns:
            是否应该清理
        """
        try:
            persistence_type = FilePersistenceType(self.persistence_type)
            upload_time = datetime.fromisoformat(self.upload_time)

            if persistence_type == FilePersistenceType.PERMANENT:
                return False

            if persistence_type == FilePersistenceType.TEMPORARY:
                # 24小时后清理
                return datetime.now() - upload_time > timedelta(hours=TEMPORARY_FILE_TTL_HOURS)

            if persistence_type == FilePersistenceType.SESSION:
                # 会话结束清理（外部控制）
                return True

            return False

        except Exception as e:
            logger.error(f"检查清理条件失败: {e}")
            return False

    def to_dict(self) -> Dict:
        """转换为字典"""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict) -> 'FileMetadata':
        """从字典创建实例"""
        return cls(**data)


class FileMetadataManager:
    """文件元数据管理器"""

    def __init__(self, storage_path: str = "./.devin/file_metadata"):
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self.metadata_file = self.storage_path / "metadata.json"
        self.metadata: Dict[str, FileMetadata] = {}
        self.load_metadata()

    def add_file(
        self,
        file_path: str,
        persistence_type: FilePersistenceType = FilePersistenceType.PERMANENT,
        file_hash: str = None,
        tags: List[str] = None
    ) -> FileMetadata:
        """
        添加文件元数据

        Args:
            file_path: 文件路径
            persistence_type: 持久化类型
            file_hash: 文件哈希
            tags: 文件标签

        Returns:
            创建的文件元数据
        """
        file_path_obj = Path(file_path)
        file_size = file_path_obj.stat().st_size if file_path_obj.exists() else 0

        metadata = FileMetadata(
            file_path=str(file_path),
            persistence_type=persistence_type.value,
            upload_time=datetime.now().isoformat(),
            file_hash=file_hash,
            file_size=file_size,
            tags=tags or []
        )

        # 使用文件路径作为键
        key = str(file_path)
        self.metadata[key] = metadata
        self.save_metadata()

        logger.info(f"文件元数据已添加: {file_path}, 类型: {persistence_type.value}")
        return metadata

    def get_file_metadata(self, file_path: str) -> Optional[FileMetadata]:
        """
        获取文件元数据

        Args:
            file_path: 文件路径

        Returns:
            文件元数据，如果不存在则返回None
        """
        key = str(file_path)
        return self.metadata.get(key)

    def update_file_metadata(self, file_path: str, **kwargs):
        """
        更新文件元数据

        Args:
            file_path: 文件路径
            **kwargs: 要更新的字段
        """
        key = str(file_path)
        if key in self.metadata:
            metadata = self.metadata[key]
            for field, value in kwargs.items():
                if hasattr(metadata, field):
                    setattr(metadata, field, value)
            self.save_metadata()
            logger.info(f"文件元数据已更新: {file_path}")

    def mark_file_access(self, file_path: str):
        """
        标记文件访问

        Args:
            file_path: 文件路径
        """
        metadata = self.get_file_metadata(file_path)
        if metadata:
            metadata.mark_access()
            self.save_metadata()

    def remove_file(self, file_path: str):
        """
        移除文件元数据

        Args:
            file_path: 文件路径
        """
        key = str(file_path)
        if key in self.metadata:
            del self.metadata[key]
            self.save_metadata()
            logger.info(f"文件元数据已移除: {file_path}")

    def list_files(
        self,
        persistence_type: FilePersistenceType = None,
        tags: List[str] = None
    ) -> List[FileMetadata]:
        """
        列出文件

        Args:
            persistence_type: 持久化类型过滤
            tags: 标签过滤

        Returns:
            文件元数据列表
        """
        files = list(self.metadata.values())

        if persistence_type:
            files = [f for f in files if f.persistence_type == persistence_type.value]

        if tags:
            files = [f for f in files if any(tag in f.tags for tag in tags)]

        # 按上传时间排序
        files.sort(key=lambda x: x.upload_time, reverse=True)

        return files

    def get_files_to_cleanup(self) -> List[FileMetadata]:
        """
        获取需要清理的文件

        Returns:
            需要清理的文件元数据列表
        """
        return [f for f in self.metadata.values() if f.should_cleanup()]

    def cleanup_files(self) -> List[str]:
        """
        清理过期文件

        Returns:
            被清理的文件路径列表
        """
        files_to_cleanup = self.get_files_to_cleanup()
        cleaned_files = []

        for metadata in files_to_cleanup:
            try:
                file_path = Path(metadata.file_path)
                if file_path.exists():
                    file_path.unlink()
                    logger.info(f"文件已清理: {metadata.file_path}")

                self.remove_file(metadata.file_path)
                cleaned_files.append(metadata.file_path)

            except Exception as e:
                logger.error(f"清理文件失败 {metadata.file_path}: {e}")

        return cleaned_files

    def get_stats(self) -> Dict:
        """
        获取统计信息

        Returns:
            统计信息字典
        """
        total_files = len(self.metadata)
        total_size = sum(m.file_size for m in self.metadata.values())

        permanent_count = sum(1 for m in self.metadata.values() if m.persistence_type == FilePersistenceType.PERMANENT.value)
        temporary_count = sum(1 for m in self.metadata.values() if m.persistence_type == FilePersistenceType.TEMPORARY.value)
        session_count = sum(1 for m in self.metadata.values() if m.persistence_type == FilePersistenceType.SESSION.value)

        cleanup_count = len(self.get_files_to_cleanup())

        return {
            "total_files": total_files,
            "total_size": total_size,
            "total_size_formatted": self._format_size(total_size),
            "permanent_count": permanent_count,
            "temporary_count": temporary_count,
            "session_count": session_count,
            "cleanup_count": cleanup_count
        }

    def save_metadata(self):
        """保存元数据到文件"""
        try:
            metadata_data = {key: value.to_dict() for key, value in self.metadata.items()}
            with open(self.metadata_file, 'w', encoding='utf-8') as f:
                json.dump(metadata_data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存元数据失败: {e}")

    def load_metadata(self):
        """从文件加载元数据"""
        try:
            if self.metadata_file.exists():
                with open(self.metadata_file, 'r', encoding='utf-8') as f:
                    metadata_data = json.load(f)
                self.metadata = {key: FileMetadata.from_dict(value) for key, value in metadata_data.items()}
                logger.info(f"加载了 {len(self.metadata)} 条文件元数据")
        except Exception as e:
            logger.error(f"加载元数据失败: {e}")
            self.metadata = {}

    @staticmethod
    def _format_size(size_bytes: int) -> str:
        """
        格式化文件大小显示

        Args:
            size_bytes: 字节数

        Returns:
            格式化的大小字符串
        """
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.2f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.2f} TB"


# 全局文件元数据管理器实例（可选，用于跨模块共享）
_global_metadata_manager: FileMetadataManager = None


def get_global_metadata_manager() -> FileMetadataManager:
    """获取全局文件元数据管理器实例"""
    global _global_metadata_manager
    if _global_metadata_manager is None:
        _global_metadata_manager = FileMetadataManager()
    return _global_metadata_manager
