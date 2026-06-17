#!/usr/bin/env python3
"""
搜索缓存管理 - 缓存搜索结果以提高性能和减少网络请求
"""
import json
import hashlib
import logging
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict

from .search_engine import SearchResult

logger = logging.getLogger(__name__)


@dataclass
class CacheEntry:
    """缓存条目"""
    query: str
    source: str
    results: List[Dict]
    timestamp: str
    ttl_hours: int = 24  # 缓存有效期（小时）
    
    def is_expired(self) -> bool:
        """检查缓存是否过期"""
        try:
            cache_time = datetime.fromisoformat(self.timestamp)
            expiry_time = cache_time + timedelta(hours=self.ttl_hours)
            return datetime.now() > expiry_time
        except Exception:
            return True  # 解析失败则认为过期
    
    def to_dict(self) -> Dict:
        """转换为字典"""
        return asdict(self)


class SearchCache:
    """搜索缓存管理器"""
    
    def __init__(self, cache_dir: Optional[Path] = None, max_cache_size: int = 1000):
        self.cache_dir = cache_dir or Path.home() / ".code_agent_search_cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.max_cache_size = max_cache_size
        self.logger = logger
        
        # 缓存索引
        self._index: Dict[str, CacheEntry] = {}
        self._load_index()
    
    def _get_cache_key(self, query: str, source: str) -> str:
        """生成缓存键"""
        key_string = f"{source}:{query}"
        return hashlib.md5(key_string.encode()).hexdigest()
    
    def _load_index(self):
        """加载缓存索引"""
        index_file = self.cache_dir / "index.json"
        try:
            if index_file.exists():
                with open(index_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for key, entry_data in data.items():
                        try:
                            entry = CacheEntry(**entry_data)
                            if not entry.is_expired():
                                self._index[key] = entry
                        except Exception as e:
                            self.logger.warning(f"加载缓存条目失败: {e}")
                
                self.logger.info(f"加载了 {len(self._index)} 个有效缓存条目")
        except Exception as e:
            self.logger.error(f"加载缓存索引失败: {e}")
    
    def _save_index(self):
        """保存缓存索引"""
        index_file = self.cache_dir / "index.json"
        try:
            data = {key: entry.to_dict() for key, entry in self._index.items()}
            with open(index_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            self.logger.error(f"保存缓存索引失败: {e}")
    
    def get(self, query: str, source: str = 'default') -> Optional[List[SearchResult]]:
        """获取缓存结果"""
        cache_key = self._get_cache_key(query, source)
        
        if cache_key in self._index:
            entry = self._index[cache_key]
            
            # 检查是否过期
            if entry.is_expired():
                self.logger.info(f"缓存已过期: {query}")
                self.delete(cache_key)
                return None
            
            # 转换回 SearchResult 对象
            try:
                results = [SearchResult(**result) for result in entry.results]
                self.logger.info(f"缓存命中: {query} ({len(results)} 条结果)")
                return results
            except Exception as e:
                self.logger.error(f"缓存数据解析失败: {e}")
                self.delete(cache_key)
                return None
        
        return None
    
    def set(self, query: str, source: str, results: List[SearchResult], ttl_hours: int = 24):
        """设置缓存"""
        cache_key = self._get_cache_key(query, source)
        
        # 转换为可序列化的格式
        results_data = [result.to_dict() for result in results]
        
        entry = CacheEntry(
            query=query,
            source=source,
            results=results_data,
            timestamp=datetime.now().isoformat(),
            ttl_hours=ttl_hours
        )
        
        self._index[cache_key] = entry
        
        # 检查缓存大小限制
        self._cleanup_old_entries()
        
        # 保存索引
        self._save_index()
        
        self.logger.info(f"缓存已保存: {query} ({len(results)} 条结果)")
    
    def delete(self, cache_key: str):
        """删除缓存条目"""
        if cache_key in self._index:
            del self._index[cache_key]
            self._save_index()
    
    def clear(self):
        """清空所有缓存"""
        self._index.clear()
        self._save_index()
        self.logger.info("缓存已清空")
    
    def _cleanup_old_entries(self):
        """清理旧缓存条目"""
        # 如果超过最大缓存大小，删除最旧的条目
        if len(self._index) > self.max_cache_size:
            # 按时间戳排序
            sorted_entries = sorted(
                self._index.items(),
                key=lambda x: x[1].timestamp
            )
            
            # 删除最旧的条目
            items_to_remove = len(self._index) - self.max_cache_size
            for cache_key, _ in sorted_entries[:items_to_remove]:
                del self._index[cache_key]
            
            self.logger.info(f"清理了 {items_to_remove} 个旧缓存条目")
    
    def cleanup_expired(self):
        """清理过期缓存"""
        expired_keys = [
            key for key, entry in self._index.items()
            if entry.is_expired()
        ]
        
        for key in expired_keys:
            del self._index[key]
        
        if expired_keys:
            self._save_index()
            self.logger.info(f"清理了 {len(expired_keys)} 个过期缓存条目")
    
    def get_stats(self) -> Dict:
        """获取缓存统计信息"""
        total_entries = len(self._index)
        expired_entries = sum(
            1 for entry in self._index.values()
            if entry.is_expired()
        )
        
        # 按来源统计
        source_stats: Dict[str, int] = {}
        for entry in self._index.values():
            source = entry.source
            source_stats[source] = source_stats.get(source, 0) + 1
        
        return {
            'total_entries': total_entries,
            'valid_entries': total_entries - expired_entries,
            'expired_entries': expired_entries,
            'max_cache_size': self.max_cache_size,
            'cache_dir': str(self.cache_dir),
            'source_distribution': source_stats
        }
    
    def get_size(self) -> int:
        """获取缓存大小（字节）"""
        try:
            total_size = 0
            for file_path in self.cache_dir.iterdir():
                if file_path.is_file():
                    total_size += file_path.stat().st_size
            return total_size
        except Exception as e:
            self.logger.error(f"计算缓存大小失败: {e}")
            return 0


# 全局搜索缓存实例
_search_cache = None

def get_search_cache(cache_dir: Optional[Path] = None) -> SearchCache:
    """获取全局搜索缓存实例"""
    global _search_cache
    if _search_cache is None:
        _search_cache = SearchCache(cache_dir)
    return _search_cache
