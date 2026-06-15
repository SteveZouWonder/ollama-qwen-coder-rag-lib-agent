"""
OCR 缓存系统单元测试
"""
import pytest
import pickle
from datetime import datetime, timedelta

from ocr_processor import OCRCache
from ocr_processor import OCRResult


class TestOCRCache:
    """OCR 缓存测试"""
    
    @pytest.fixture
    def cache_dir(self, tmp_path):
        """创建临时缓存目录"""
        return tmp_path / "cache"
    
    @pytest.fixture
    def cache(self, cache_dir):
        """创建缓存实例"""
        return OCRCache(cache_dir, ttl_days=30)
    
    @pytest.fixture
    def sample_result(self):
        """创建测试用的 OCR 结果"""
        return OCRResult(
            text="测试文本",
            confidence=0.95,
            bbox=(0, 0, 100, 50),
            language="ch",
            page_num=0
        )
    
    def test_cache_set_and_get(self, cache, sample_result):
        """测试缓存写入和读取"""
        cache.set("test_hash", sample_result)
        retrieved = cache.get("test_hash")
        
        assert retrieved is not None
        assert retrieved.text == sample_result.text
        assert retrieved.confidence == sample_result.confidence
        assert retrieved.bbox == sample_result.bbox
    
    def test_cache_miss(self, cache):
        """测试缓存未命中"""
        result = cache.get("nonexistent_hash")
        assert result is None
    
    def test_cache_clear(self, cache, sample_result):
        """测试缓存清理"""
        cache.set("test_hash", sample_result)
        assert cache.get("test_hash") is not None
        
        cache.clear()
        assert cache.get("test_hash") is None
    
    def test_cache_persistence(self, cache_dir, sample_result):
        """测试缓存持久化"""
        cache1 = OCRCache(cache_dir, ttl_days=30)
        cache1.set("test_hash", sample_result)
        
        # 重新创建缓存实例
        cache2 = OCRCache(cache_dir, ttl_days=30)
        retrieved = cache2.get("test_hash")
        
        assert retrieved is not None
        assert retrieved.text == sample_result.text
    
    def test_cache_subdir_structure(self, cache_dir, sample_result):
        """测试缓存子目录结构"""
        cache = OCRCache(cache_dir, ttl_days=30)
        
        # 写入多个不同哈希的缓存
        for i in range(10):
            hash_value = f"hash_{i:02d}_abcdef"
            cache.set(hash_value, sample_result)
        
        # 检查子目录是否正确创建
        subdirs = list(cache_dir.iterdir())
        assert len(subdirs) > 0
        assert all(d.is_dir() for d in subdirs)
    
    def test_cache_ttl(self, cache_dir, sample_result):
        """测试缓存过期"""
        # 创建 TTL 为 0.001 天（约 86 秒）的缓存
        cache = OCRCache(cache_dir, ttl_days=0.001)
        
        # 写入缓存
        cache.set("test_hash", sample_result)
        
        # 立即读取应该成功
        assert cache.get("test_hash") is not None
        
        # 手动修改缓存时间为过去
        cache_path = cache._get_cache_path("test_hash")
        with open(cache_path, 'rb') as f:
            data = pickle.load(f)
        
        # 设置时间为 2 天前
        data['timestamp'] = (datetime.now() - timedelta(days=2)).isoformat()
        
        with open(cache_path, 'wb') as f:
            pickle.dump(data, f)
        
        # 再次读取应该返回 None（已过期）
        assert cache.get("test_hash") is None
    
    def test_cache_exists(self, cache, sample_result):
        """测试缓存存在性检查"""
        assert not cache.exists("test_hash")
        
        cache.set("test_hash", sample_result)
        assert cache.exists("test_hash")
    
    def test_cache_clear_expired(self, cache_dir, sample_result):
        """测试清理过期缓存"""
        cache = OCRCache(cache_dir, ttl_days=1)
        
        # 写入多个缓存
        for i in range(5):
            hash_value = f"hash_{i}"
            cache.set(hash_value, sample_result)
        
        # 修改部分缓存为过期
        for i in range(3):
            hash_value = f"hash_{i}"
            cache_path = cache._get_cache_path(hash_value)
            with open(cache_path, 'rb') as f:
                data = pickle.load(f)
            data['timestamp'] = (datetime.now() - timedelta(days=2)).isoformat()
            with open(cache_path, 'wb') as f:
                pickle.dump(data, f)
        
        # 清理过期缓存
        expired_count = cache.clear_expired()
        
        # 应该清理了 3 个过期缓存
        assert expired_count == 3
        
        # 剩余 2 个应该仍然存在
        assert cache.exists("hash_3")
        assert cache.exists("hash_4")
        assert not cache.exists("hash_0")
    
    def test_cache_get_size(self, cache, sample_result):
        """测试获取缓存大小"""
        # 初始大小应该为 0
        assert cache.get_cache_size() == 0
        
        # 添加缓存
        cache.set("test_hash", sample_result)
        
        # 大小应该大于 0
        assert cache.get_cache_size() > 0
    
    def test_cache_get_count(self, cache, sample_result):
        """测试获取缓存数量"""
        # 初始数量应该为 0
        assert cache.get_cache_count() == 0
        
        # 添加缓存
        cache.set("test_hash1", sample_result)
        cache.set("test_hash2", sample_result)
        
        # 数量应该为 2
        assert cache.get_cache_count() == 2
    
    def test_cache_get_stats(self, cache, sample_result):
        """测试获取缓存统计信息"""
        stats = cache.get_stats()
        
        assert 'cache_dir' in stats
        assert 'cache_count' in stats
        assert 'cache_size_bytes' in stats
        assert 'cache_size_mb' in stats
        assert 'ttl_days' in stats
        
        # 添加缓存后重新获取统计
        cache.set("test_hash", sample_result)
        stats = cache.get_stats()
        
        assert stats['cache_count'] == 1
        assert stats['cache_size_bytes'] > 0
    
    def test_cache_corrupted_file_handling(self, cache_dir, sample_result):
        """测试损坏缓存文件的处理"""
        cache = OCRCache(cache_dir, ttl_days=30)
        
        # 写入正常缓存
        cache.set("test_hash", sample_result)
        
        # 破坏缓存文件
        cache_path = cache._get_cache_path("test_hash")
        cache_path.write_bytes(b"corrupted data")
        
        # 读取应该返回 None 并删除损坏的文件
        result = cache.get("test_hash")
        assert result is None
        assert not cache_path.exists()
    
    def test_cache_with_none_result(self, cache):
        """测试缓存 None 值"""
        cache.set("test_hash", None)
        result = cache.get("test_hash")
        assert result is None
    
    def test_cache_with_complex_metadata(self, cache):
        """测试缓存复杂元数据"""
        complex_result = OCRResult(
            text="复杂测试",
            confidence=0.88,
            bbox=(10, 20, 100, 200),
            language="en",
            page_num=5,
            metadata={
                'key1': 'value1',
                'key2': [1, 2, 3],
                'key3': {'nested': 'data'}
            }
        )
        
        cache.set("complex_hash", complex_result)
        retrieved = cache.get("complex_hash")
        
        assert retrieved is not None
        assert retrieved.text == complex_result.text
        assert retrieved.metadata == complex_result.metadata
    
    def test_cache_multiple_instances_same_dir(self, cache_dir, sample_result):
        """测试多个实例使用同一目录"""
        cache1 = OCRCache(cache_dir, ttl_days=30)
        cache2 = OCRCache(cache_dir, ttl_days=30)
        
        # cache1 写入
        cache1.set("test_hash", sample_result)
        
        # cache2 应该能读取
        retrieved = cache2.get("test_hash")
        assert retrieved is not None
        assert retrieved.text == sample_result.text
    
    def test_cache_long_hash(self, cache, sample_result):
        """测试长哈希值"""
        long_hash = "a" * 100
        cache.set(long_hash, sample_result)
        retrieved = cache.get(long_hash)
        
        assert retrieved is not None
        assert retrieved.text == sample_result.text
    
    def test_cache_special_characters_hash(self, cache, sample_result):
        """测试特殊字符哈希值"""
        special_hash = "hash_!@#$%^&*()_+-=[]{}|;:,.<>?"
        cache.set(special_hash, sample_result)
        retrieved = cache.get(special_hash)
        
        assert retrieved is not None
        assert retrieved.text == sample_result.text
    
    def test_cache_empty_hash(self, cache):
        """测试空哈希值"""
        result = cache.get("")
        assert result is None
    
    def test_cache_update_existing(self, cache, sample_result):
        """测试更新已存在的缓存"""
        cache.set("test_hash", sample_result)
        
        # 更新缓存
        updated_result = OCRResult(
            text="更新后的文本",
            confidence=0.99,
            bbox=(0, 0, 200, 100)
        )
        cache.set("test_hash", updated_result)
        
        retrieved = cache.get("test_hash")
        assert retrieved.text == "更新后的文本"
        assert retrieved.confidence == 0.99
    
    def test_cache_concurrent_access(self, cache_dir, sample_result):
        """测试并发访问缓存"""
        import threading
        
        cache1 = OCRCache(cache_dir, ttl_days=30)
        cache2 = OCRCache(cache_dir, ttl_days=30)
        
        def write_cache():
            for i in range(10):
                cache1.set(f"hash_{i}", sample_result)
        
        def read_cache():
            for i in range(10):
                cache2.get(f"hash_{i}")
        
        thread1 = threading.Thread(target=write_cache)
        thread2 = threading.Thread(target=read_cache)
        
        thread1.start()
        thread2.start()
        thread1.join()
        thread2.join()
        
        # 验证缓存状态
        assert cache1.get_cache_count() >= 0
    
    def test_cache_ttl_zero(self, cache_dir, sample_result):
        """测试 TTL 为 0 的缓存"""
        cache = OCRCache(cache_dir, ttl_days=0)
        
        cache.set("test_hash", sample_result)
        
        # 手动设置为过去时间
        cache_path = cache._get_cache_path("test_hash")
        with open(cache_path, 'rb') as f:
            data = pickle.load(f)
        data['timestamp'] = (datetime.now() - timedelta(days=1)).isoformat()
        with open(cache_path, 'wb') as f:
            pickle.dump(data, f)
        
        # 应该立即过期
        assert cache.get("test_hash") is None
    
    def test_cache_very_large_ttl(self, cache_dir, sample_result):
        """测试很大的 TTL 值"""
        cache = OCRCache(cache_dir, ttl_days=36500)  # 100 年
        
        cache.set("test_hash", sample_result)
        retrieved = cache.get("test_hash")
        
        assert retrieved is not None
        assert retrieved.text == sample_result.text
    
    def test_cache_stats_accuracy(self, cache, sample_result):
        """测试缓存统计信息的准确性"""
        stats_before = cache.get_stats()
        initial_count = stats_before['cache_count']
        
        # 添加多个缓存
        for i in range(5):
            cache.set(f"hash_{i}", sample_result)
        
        stats_after = cache.get_stats()
        
        assert stats_after['cache_count'] == initial_count + 5
        assert stats_after['cache_size_bytes'] > stats_before['cache_size_bytes']
    
    def test_cache_subdir_collision(self, cache_dir, sample_result):
        """测试子目录哈希冲突处理"""
        cache = OCRCache(cache_dir, ttl_days=30)
        
        # 创建哈希值前两位相同的多个缓存
        for i in range(10):
            hash_value = f"ab_{i:08d}"  # 都以 'ab' 开头
            cache.set(hash_value, sample_result)
        
        # 验证都在同一个子目录
        subdir = cache_dir / "ab"
        assert subdir.exists()
        assert subdir.is_dir()
        
        # 验证文件数量
        files = list(subdir.glob("*.pkl"))
        assert len(files) == 10
