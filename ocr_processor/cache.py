"""
OCR 结果缓存系统
"""
import pickle
import hashlib
import shutil
from pathlib import Path
from typing import Optional, List
from datetime import datetime, timedelta


class OCRCache:
    """OCR 结果缓存"""
    
    def __init__(self, cache_dir: Path, ttl_days: int = 30):
        """
        初始化缓存系统
        
        Args:
            cache_dir: 缓存目录路径
            ttl_days: 缓存过期时间（天）
        """
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.ttl_days = ttl_days
    
    def _get_cache_path(self, image_hash: str) -> Path:
        """
        获取缓存文件路径
        
        Args:
            image_hash: 图片哈希值
            
        Returns:
            缓存文件路径
        """
        # 使用哈希值的前两位作为子目录，避免单个目录文件过多
        subdir = self.cache_dir / image_hash[:2]
        subdir.mkdir(exist_ok=True)
        return subdir / f"{image_hash}.pkl"
    
    def get(self, image_hash: str) -> Optional:
        """
        获取缓存结果
        
        Args:
            image_hash: 图片哈希值
            
        Returns:
            缓存的 OCR 结果，如果不存在或已过期则返回 None
        """
        cache_path = self._get_cache_path(image_hash)
        if cache_path.exists():
            try:
                with open(cache_path, 'rb') as f:
                    data = pickle.load(f)
                
                # 检查是否过期
                cache_time = data.get('timestamp')
                if cache_time:
                    cache_datetime = datetime.fromisoformat(cache_time)
                    if datetime.now() - cache_datetime > timedelta(days=self.ttl_days):
                        # 缓存已过期，删除并返回 None
                        cache_path.unlink()
                        return None
                
                return data.get('result')
            except (pickle.PickleError, EOFError, KeyError) as e:
                # 缓存文件损坏，删除并返回 None
                if cache_path.exists():
                    cache_path.unlink()
                return None
            except Exception as e:
                # 其他错误，返回 None
                return None
        return None
    
    def set(self, image_hash: str, result):
        """
        缓存结果
        
        Args:
            image_hash: 图片哈希值
            result: OCR 识别结果
        """
        cache_path = self._get_cache_path(image_hash)
        try:
            data = {
                'result': result,
                'timestamp': datetime.now().isoformat(),
                'hash': image_hash
            }
            with open(cache_path, 'wb') as f:
                pickle.dump(data, f)
        except Exception as e:
            # 缓存写入失败，打印警告但不影响主流程
            print(f"缓存写入失败: {e}")
    
    def exists(self, image_hash: str) -> bool:
        """
        检查缓存是否存在
        
        Args:
            image_hash: 图片哈希值
            
        Returns:
            如果缓存存在且未过期则返回 True
        """
        cache_path = self._get_cache_path(image_hash)
        if cache_path.exists():
            # 检查是否过期
            try:
                with open(cache_path, 'rb') as f:
                    data = pickle.load(f)
                cache_time = data.get('timestamp')
                if cache_time:
                    cache_datetime = datetime.fromisoformat(cache_time)
                    if datetime.now() - cache_datetime > timedelta(days=self.ttl_days):
                        return False
                return True
            except Exception:
                return False
        return False
    
    def clear(self):
        """清空所有缓存"""
        if self.cache_dir.exists():
            shutil.rmtree(self.cache_dir)
            self.cache_dir.mkdir(parents=True, exist_ok=True)
    
    def clear_expired(self):
        """清理过期的缓存"""
        now = datetime.now()
        expired_count = 0
        
        for subdir in self.cache_dir.iterdir():
            if subdir.is_dir():
                for cache_file in subdir.iterdir():
                    if cache_file.is_file() and cache_file.suffix == '.pkl':
                        try:
                            with open(cache_file, 'rb') as f:
                                data = pickle.load(f)
                            cache_time = data.get('timestamp')
                            if cache_time:
                                cache_datetime = datetime.fromisoformat(cache_time)
                                if now - cache_datetime > timedelta(days=self.ttl_days):
                                    cache_file.unlink()
                                    expired_count += 1
                        except Exception:
                            # 损坏的缓存文件，删除
                            cache_file.unlink()
                            expired_count += 1
        
        return expired_count
    
    def get_cache_size(self) -> int:
        """
        获取缓存大小（字节）
        
        Returns:
            缓存总大小
        """
        total_size = 0
        if self.cache_dir.exists():
            for file_path in self.cache_dir.rglob('*.pkl'):
                total_size += file_path.stat().st_size
        return total_size
    
    def get_cache_count(self) -> int:
        """
        获取缓存文件数量
        
        Returns:
            缓存文件总数
        """
        count = 0
        if self.cache_dir.exists():
            for file_path in self.cache_dir.rglob('*.pkl'):
                count += 1
        return count
    
    def get_stats(self) -> dict:
        """
        获取缓存统计信息
        
        Returns:
            包含缓存统计信息的字典
        """
        return {
            'cache_dir': str(self.cache_dir),
            'cache_count': self.get_cache_count(),
            'cache_size_bytes': self.get_cache_size(),
            'cache_size_mb': self.get_cache_size() / (1024 * 1024),
            'ttl_days': self.ttl_days,
        }
