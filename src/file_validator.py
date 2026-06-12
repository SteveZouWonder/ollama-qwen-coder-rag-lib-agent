"""
文件上传验证器 - 提供文件大小、类型、去重等验证功能
"""
import hashlib
import logging
from pathlib import Path
from typing import Tuple, Set

from config import (
    MAX_FILE_SIZE,
    MAX_TOTAL_SIZE,
    ALLOWED_FILE_TYPES,
    BLOCKED_FILE_PATTERNS,
    ENABLE_FILE_DEDUPLICATION
)

logger = logging.getLogger(__name__)


class FileValidator:
    """文件上传验证器"""

    def __init__(
        self,
        max_file_size: int = None,
        max_total_size: int = None,
        allowed_types: list = None,
        blocked_patterns: list = None,
        enable_deduplication: bool = None
    ):
        self.max_file_size = max_file_size if max_file_size is not None else MAX_FILE_SIZE
        self.max_total_size = max_total_size if max_total_size is not None else MAX_TOTAL_SIZE
        self.allowed_types = allowed_types if allowed_types is not None else ALLOWED_FILE_TYPES
        self.blocked_patterns = blocked_patterns if blocked_patterns is not None else BLOCKED_FILE_PATTERNS
        self.enable_deduplication = enable_deduplication if enable_deduplication is not None else ENABLE_FILE_DEDUPLICATION

        # 已知的文件哈希集合，用于去重
        self.known_hashes: Set[str] = set()
        self.current_total_size = 0

    def validate_file(self, file_path: Path) -> Tuple[bool, str]:
        """
        验证单个文件

        Args:
            file_path: 文件路径

        Returns:
            (是否通过验证, 错误消息/通过消息)
        """
        try:
            # 检查文件是否存在
            if not file_path.exists():
                return False, "文件不存在"

            if not file_path.is_file():
                return False, "路径不是文件"

            # 检查文件大小
            file_size = file_path.stat().st_size
            if file_size > self.max_file_size:
                return False, f"文件过大 ({self._format_size(file_size)} > {self._format_size(self.max_file_size)})"

            if file_size == 0:
                return False, "文件为空"

            # 检查文件类型
            suffix = file_path.suffix.lower().lstrip('.')
            if suffix not in self.allowed_types:
                return False, f"不支持的文件类型: {suffix}"

            # 检查是否为阻塞模式
            for pattern in self.blocked_patterns:
                if file_path.match(pattern):
                    return False, f"文件匹配阻塞模式: {pattern}"

            # 检查文件是否可读
            try:
                with open(file_path, 'rb') as f:
                    f.read(1)  # 尝试读取一个字节
            except Exception as e:
                return False, f"文件不可读: {e}"

            return True, "验证通过"

        except Exception as e:
            logger.error(f"文件验证异常: {e}")
            return False, f"验证过程出错: {e}"

    def check_total_size(self, additional_size: int) -> Tuple[bool, str]:
        """
        检查总大小限制

        Args:
            additional_size: 新增的文件大小

        Returns:
            (是否通过验证, 错误消息/通过消息)
        """
        if self.current_total_size + additional_size > self.max_total_size:
            return False, f"总大小超限 ({self._format_size(self.current_total_size + additional_size)} > {self._format_size(self.max_total_size)})"
        return True, "验证通过"

    def calculate_file_hash(self, file_path: Path) -> str:
        """
        计算文件哈希用于去重

        Args:
            file_path: 文件路径

        Returns:
            文件的MD5哈希值
        """
        hash_md5 = hashlib.md5()
        try:
            with open(file_path, "rb") as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    hash_md5.update(chunk)
            return hash_md5.hexdigest()
        except Exception as e:
            logger.error(f"计算文件哈希失败: {e}")
            return ""

    def check_duplicate(self, file_path: Path) -> Tuple[bool, str]:
        """
        检查文件是否重复

        Args:
            file_path: 文件路径

        Returns:
            (是否重复, 消息)
        """
        if not self.enable_deduplication:
            return False, "去重功能未启用"

        file_hash = self.calculate_file_hash(file_path)
        if not file_hash:
            return False, "无法计算文件哈希"

        if file_hash in self.known_hashes:
            return True, f"文件重复 (哈希: {file_hash[:8]})"

        return False, "文件不重复"

    def register_file(self, file_path: Path, file_size: int = None):
        """
        注册文件到已知集合

        Args:
            file_path: 文件路径
            file_size: 文件大小（如果为None则自动计算）
        """
        if file_size is None:
            file_size = file_path.stat().st_size

        if self.enable_deduplication:
            file_hash = self.calculate_file_hash(file_path)
            if file_hash:
                self.known_hashes.add(file_hash)

        self.current_total_size += file_size
        logger.info(f"文件已注册: {file_path.name}, 大小: {self._format_size(file_size)}, 总大小: {self._format_size(self.current_total_size)}")

    def unregister_file(self, file_path: Path, file_size: int = None):
        """
        从已知集合中移除文件

        Args:
            file_path: 文件路径
            file_size: 文件大小（如果为None则自动计算）
        """
        if file_size is None:
            file_size = file_path.stat().st_size

        if self.enable_deduplication:
            file_hash = self.calculate_file_hash(file_path)
            if file_hash in self.known_hashes:
                self.known_hashes.remove(file_hash)

        self.current_total_size = max(0, self.current_total_size - file_size)
        logger.info(f"文件已移除: {file_path.name}, 大小: {self._format_size(file_size)}, 总大小: {self._format_size(self.current_total_size)}")

    def get_stats(self) -> dict:
        """
        获取验证器统计信息

        Returns:
            统计信息字典
        """
        return {
            "current_total_size": self.current_total_size,
            "current_total_size_formatted": self._format_size(self.current_total_size),
            "max_file_size": self.max_file_size,
            "max_file_size_formatted": self._format_size(self.max_file_size),
            "max_total_size": self.max_total_size,
            "max_total_size_formatted": self._format_size(self.max_total_size),
            "known_file_count": len(self.known_hashes),
            "utilization_percent": (self.current_total_size / self.max_total_size * 100) if self.max_total_size > 0 else 0
        }

    def reset(self):
        """重置验证器状态"""
        self.known_hashes.clear()
        self.current_total_size = 0
        logger.info("文件验证器已重置")

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


# 全局文件验证器实例（可选，用于跨模块共享）
_global_validator: FileValidator = None


def get_global_validator() -> FileValidator:
    """获取全局文件验证器实例"""
    global _global_validator
    if _global_validator is None:
        _global_validator = FileValidator()
    return _global_validator
