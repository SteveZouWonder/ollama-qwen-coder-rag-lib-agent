"""
历史压缩器 - 提供聊天历史压缩、去重、摘要等功能
"""
import hashlib
import logging
from typing import List, Dict

from config import HISTORY_COMPRESSION_RATIO

logger = logging.getLogger(__name__)


class HistoryCompressor:
    """历史记录压缩器"""

    def __init__(self, compression_ratio: float = None):
        """
        初始化压缩器

        Args:
            compression_ratio: 压缩比例 (0-1)，默认使用配置值
        """
        self.compression_ratio = compression_ratio if compression_ratio is not None else HISTORY_COMPRESSION_RATIO
        self.summarization_enabled = True

    def compress_history(self, messages: List[Dict]) -> List[Dict]:
        """
        压缩历史记录

        Args:
            messages: 消息列表

        Returns:
            压缩后的消息列表
        """
        if len(messages) <= 10:  # 消息太少，不压缩
            return messages

        # 保留最近的消息
        recent_count = max(5, int(len(messages) * (1 - self.compression_ratio)))
        recent_messages = messages[-recent_count:]

        # 压缩旧消息
        old_messages = messages[:-recent_count]

        if self.summarization_enabled and len(old_messages) > 0:
            compressed_summary = self._generate_summary(old_messages)
            compressed_messages = [{"role": "system", "content": f"历史对话摘要: {compressed_summary}"}]
        else:
            # 简单去重压缩
            compressed_messages = self._deduplicate_messages(old_messages)

        return compressed_messages + recent_messages

    def _generate_summary(self, messages: List[Dict]) -> str:
        """
        生成历史摘要

        Args:
            messages: 消息列表

        Returns:
            摘要文本
        """
        # 这里应该调用LLM来生成摘要
        # 简化实现：提取关键信息
        user_messages = [m["content"] for m in messages if m["role"] == "user"]
        assistant_messages = [m["content"] for m in messages if m["role"] == "assistant"]

        summary = f"用户问了{len(user_messages)}个问题，助手进行了{len(assistant_messages)}次回答。"

        if user_messages:
            # 提取主要话题（取第一条用户消息的前50个字符）
            first_topic = user_messages[0][:50]
            summary += f" 主要讨论话题: {first_topic}..."

        return summary

    def _deduplicate_messages(self, messages: List[Dict]) -> List[Dict]:
        """
        去重消息

        Args:
            messages: 消息列表

        Returns:
            去重后的消息列表
        """
        seen_hashes = set()
        deduplicated = []

        for message in messages:
            content_hash = hashlib.md5(message["content"].encode(), usedforsecurity=False).hexdigest()
            if content_hash not in seen_hashes:
                seen_hashes.add(content_hash)
                deduplicated.append(message)

        return deduplicated

    def compress_by_topics(self, messages: List[Dict]) -> List[Dict]:
        """
        按话题压缩

        Args:
            messages: 消息列表

        Returns:
            按话题压缩后的消息列表
        """
        # 简化实现：按时间分块
        chunk_size = 10
        compressed = []

        for i in range(0, len(messages), chunk_size):
            chunk = messages[i:i+chunk_size]
            if len(chunk) > 0:
                summary = self._generate_summary(chunk)
                compressed.append({"role": "system", "content": f"对话片段{i//chunk_size+1}摘要: {summary}"})

        return compressed

    def compress_smart(self, messages: List[Dict], context_window: int = 4096) -> List[Dict]:
        """
        智能压缩（考虑上下文窗口）

        Args:
            messages: 消息列表
            context_window: 上下文窗口大小（字符数）

        Returns:
            智能压缩后的消息列表
        """
        # 计算当前总字符数
        total_chars = sum(len(m["content"]) for m in messages)

        if total_chars <= context_window:
            return messages  # 不需要压缩

        # 计算需要保留的比例
        keep_ratio = context_window / total_chars

        # 保留最近的对话
        recent_count = max(3, int(len(messages) * keep_ratio))
        recent_messages = messages[-recent_count:]

        # 压缩旧对话
        old_messages = messages[:-recent_count]
        if old_messages:
            compressed_summary = self._generate_summary(old_messages)
            old_compressed = [{"role": "system", "content": f"历史对话摘要: {compressed_summary}"}]
        else:
            old_compressed = []

        return old_compressed + recent_messages

    def get_compression_stats(self, original: List[Dict], compressed: List[Dict]) -> Dict:
        """
        获取压缩统计信息

        Args:
            original: 原始消息列表
            compressed: 压缩后的消息列表

        Returns:
            统计信息字典
        """
        original_count = len(original)
        compressed_count = len(compressed)
        original_chars = sum(len(m["content"]) for m in original)
        compressed_chars = sum(len(m["content"]) for m in compressed)

        return {
            "original_count": original_count,
            "compressed_count": compressed_count,
            "count_reduction": original_count - compressed_count,
            "count_reduction_percent": (1 - compressed_count / original_count) * 100 if original_count > 0 else 0,
            "original_chars": original_chars,
            "compressed_chars": compressed_chars,
            "chars_reduction": original_chars - compressed_chars,
            "chars_reduction_percent": (1 - compressed_chars / original_chars) * 100 if original_chars > 0 else 0,
        }
