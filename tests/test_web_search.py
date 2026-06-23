#!/usr/bin/env python3
"""
网络搜索模块单元测试
"""
import pytest
import asyncio
from pathlib import Path
from datetime import datetime, timedelta
import json

# 导入被测试的模块
from web_search.search_engine import SearchResult, DuckDuckGoSearchEngine, SearchEngineManager
from web_search.content_extractor import ContentExtractor
from web_search.search_cache import SearchCache, CacheEntry
from web_search.result_processor import ResultProcessor


class TestSearchResult:
    """测试 SearchResult 数据类"""
    
    def test_search_result_creation(self):
        """测试创建搜索结果"""
        result = SearchResult(
            title="测试标题",
            url="https://example.com",
            snippet="测试摘要",
            source="test",
            relevance_score=0.8
        )
        
        assert result.title == "测试标题"
        assert result.url == "https://example.com"
        assert result.snippet == "测试摘要"
        assert result.source == "test"
        assert result.relevance_score == 0.8
        assert isinstance(result.timestamp, str)
    
    def test_search_result_to_dict(self):
        """测试转换为字典"""
        result = SearchResult(
            title="测试标题",
            url="https://example.com",
            snippet="测试摘要",
            source="test",
            relevance_score=0.8
        )
        
        result_dict = result.to_dict()
        
        assert result_dict['title'] == "测试标题"
        assert result_dict['url'] == "https://example.com"
        assert result_dict['snippet'] == "测试摘要"
        assert result_dict['source'] == "test"
        assert result_dict['relevance_score'] == 0.8
        assert 'timestamp' in result_dict
        assert 'metadata' in result_dict


class TestDuckDuckGoSearchEngine:
    """测试 DuckDuckGo 搜索引擎"""
    
    def test_initialization(self):
        """测试初始化"""
        engine = DuckDuckGoSearchEngine()
        assert engine is not None
        assert engine.logger is not None
    
    def test_calculate_relevance(self):
        """测试相关性计算"""
        engine = DuckDuckGoSearchEngine()
        
        # 测试不同的结果
        result1 = {
            'title': 'Python编程教程',
            'body': '这是一个关于Python编程的详细教程'
        }
        result2 = {
            'title': '短标题',
            'body': '短内容'
        }
        
        score1 = engine._calculate_relevance(result1, "Python")
        score2 = engine._calculate_relevance(result2, "Python")
        
        # 包含关键词的结果应该有更高的相关性
        assert score1 > score2
    
    def test_calculate_relevance_with_error(self):
        """测试相关性计算错误处理"""
        engine = DuckDuckGoSearchEngine()
        
        # 测试空结果
        score = engine._calculate_relevance({}, "test")
        
        # 应该返回默认值
        assert score >= 0
    
    @pytest.mark.asyncio
    async def test_search_with_max_results(self):
        """测试指定最大结果数的搜索"""
        engine = DuckDuckGoSearchEngine()
        
        if not engine.is_available():
            pytest.skip("DuckDuckGo 搜索引擎不可用")
        
        results = await engine.search("test", max_results=5)
        
        assert len(results) <= 5
    
    def test_search_error_handling(self):
        """测试搜索错误处理"""
        engine = DuckDuckGoSearchEngine()
        
        # 测试无效的搜索参数
        import asyncio
        
        async def test_invalid_search():
            if not engine.is_available():
                results = await engine.search("", max_results=10)
                assert results == []  # 空查询应该返回空结果
        
        asyncio.run(test_invalid_search())
    
    def test_get_source_name(self):
        """测试获取源名称"""
        engine = DuckDuckGoSearchEngine()
        assert engine.get_source_name() == "DuckDuckGo"
    
    def test_is_available(self):
        """测试可用性检查"""
        engine = DuckDuckGoSearchEngine()
        # 如果库未安装，应该返回 False
        availability = engine.is_available()
        assert isinstance(availability, bool)
    
    @pytest.mark.asyncio
    async def test_search_with_unavailable_engine(self):
        """测试使用不可用的引擎搜索"""
        engine = DuckDuckGoSearchEngine()
        # 如果引擎不可用，应该返回空列表
        if not engine.is_available():
            results = await engine.search("test query")
            assert results == []
    
    def test_extract_domain(self):
        """测试域名提取"""
        engine = DuckDuckGoSearchEngine()
        
        domain1 = engine._extract_domain("https://www.example.com/path")
        assert domain1 == "www.example.com"
        
        domain2 = engine._extract_domain("http://test.org")
        assert domain2 == "test.org"
        
        # 测试无效 URL - 应该返回原字符串或空字符串
        domain3 = engine._extract_domain("invalid-url")
        assert domain3 in ["invalid-url", ""]


class TestSearchEngineManager:
    """测试搜索引擎管理器"""
    
    def test_initialization(self):
        """测试初始化"""
        manager = SearchEngineManager()
        assert manager is not None
        assert isinstance(manager.engines, dict)
    
    @pytest.mark.asyncio
    async def test_search_via_manager(self):
        """测试通过管理器搜索"""
        manager = SearchEngineManager()
        
        # 创建一个模拟搜索引擎
        class MockSearchEngine:
            def get_source_name(self):
                return "mock"
            def is_available(self):
                return True
            async def search(self, query, max_results=10):
                return [
                    SearchResult(
                        title="Mock Result",
                        url="https://mock.com",
                        snippet="Mock snippet",
                        source="mock",
                        relevance_score=0.9
                    )
                ]
        
        mock_engine = MockSearchEngine()
        manager.register_engine("mock", mock_engine, set_as_default=True)
        
        # 通过管理器搜索
        results = await manager.search("test query", source="mock", max_results=5)
        
        assert len(results) == 1
        assert results[0].title == "Mock Result"
    
    def test_get_nonexistent_engine(self):
        """测试获取不存在的搜索引擎"""
        manager = SearchEngineManager()
        
        engine = manager.get_engine("nonexistent")
        assert engine is None
    
    def test_register_engine(self):
        """测试注册搜索引擎"""
        manager = SearchEngineManager()
        
        # 创建一个模拟搜索引擎
        class MockSearchEngine:
            def get_source_name(self):
                return "mock"
            def is_available(self):
                return True
            async def search(self, query, max_results=10):
                return []
        
        mock_engine = MockSearchEngine()
        manager.register_engine("mock", mock_engine)
        
        assert "mock" in manager.engines
        assert manager.get_engine("mock") == mock_engine
    
    def test_list_engines(self):
        """测试列出所有引擎"""
        manager = SearchEngineManager()
        engines = manager.list_engines()
        assert isinstance(engines, list)
        # 如果 duckduckgo_search 未安装，可能没有默认引擎
        # 所以只验证类型，不验证数量


class TestContentExtractor:
    """测试内容提取器"""
    
    def test_initialization(self):
        """测试初始化"""
        extractor = ContentExtractor()
        assert extractor is not None
        assert extractor.logger is not None
    
    @pytest.mark.asyncio
    async def test_extract_timeout(self):
        """测试提取超时"""
        extractor = ContentExtractor()
        
        # 使用一个可能超时的URL
        result = await extractor.extract("https://example.com", timeout=1)
        
        # 即使超时也应该返回结果
        assert result is not None
        assert isinstance(result, dict)
    
    @pytest.mark.asyncio
    async def test_extract_with_invalid_url(self):
        """测试使用无效 URL 提取"""
        extractor = ContentExtractor()
        
        result = await extractor.extract("invalid-url", timeout=10)
        
        assert result is not None
        assert 'error' in result or 'url' in result
    
    @pytest.mark.asyncio
    async def test_extract_methods_fallback(self):
        """测试提取方法回退"""
        extractor = ContentExtractor()
        
        # 即使所有方法都失败，也应该返回一个结果
        result = await extractor.extract("https://example.com", timeout=1)
        
        assert result is not None
        assert isinstance(result, dict)
    
    def test_check_trafilatura(self):
        """测试 trafilatura 可用性检查"""
        extractor = ContentExtractor()
        
        available = extractor._check_trafilatura()
        assert isinstance(available, bool)
    
    def test_check_beautifulsoup(self):
        """测试 beautifulsoup 可用性检查"""
        extractor = ContentExtractor()
        
        available = extractor._check_beautifulsoup()
        assert isinstance(available, bool)
    
    @pytest.mark.asyncio
    async def test_trafilatura_no_timeout_param(self):
        """测试 trafilatura 调用不传递 timeout 参数"""
        extractor = ContentExtractor()
        
        # 只有当 trafilatura 可用时才测试
        if not extractor._trafilatura_available:
            pytest.skip("trafilatura 不可用")
        
        # 模拟 trafilatura.fetch_url 不接受 timeout 参数
        import trafilatura
        original_fetch_url = trafilatura.fetch_url
        
        # 创建一个 mock 函数，只接受 url 参数
        def mock_fetch_url(url):
            return original_fetch_url(url)
        
        # 临时替换 fetch_url
        trafilatura.fetch_url = mock_fetch_url
        
        try:
            # 调用提取方法，应该不会因为 timeout 参数而失败
            result = await extractor._extract_with_trafilatura("https://example.com", timeout=10)
            
            # 结果可能为 None（因为 example.com 可能没有可提取的内容）
            # 但重要的是不应该抛出关于 timeout 参数的错误
            assert True  # 如果到这里说明没有参数错误
        finally:
            # 恢复原始函数
            trafilatura.fetch_url = original_fetch_url
    def test_is_valid_url(self):
        """测试 URL 验证"""
        extractor = ContentExtractor()
        
        # 有效的 URL
        assert extractor.is_valid_url("https://example.com") == True
        assert extractor.is_valid_url("http://test.org/path") == True
        
        # 无效的 URL
        assert extractor.is_valid_url("not-a-url") == False
        assert extractor.is_valid_url("") == False
    
    def test_extract_domain(self):
        """测试域名提取"""
        extractor = ContentExtractor()
        
        domain1 = extractor.extract_domain("https://www.example.com/path")
        assert domain1 == "www.example.com"
        
        domain2 = extractor.extract_domain("http://test.org")
        assert domain2 == "test.org"
    
    def test_clean_text(self):
        """测试文本清理"""
        extractor = ContentExtractor()
        
        # 测试多余空白
        text1 = "hello    world"
        cleaned1 = extractor.clean_text(text1)
        assert cleaned1 == "hello world"
        
        # 测试空字符串
        text2 = ""
        cleaned2 = extractor.clean_text(text2)
        assert cleaned2 == ""
        
        # 测试特殊字符
        text3 = "hello@#$world"
        cleaned3 = extractor.clean_text(text3)
        assert "@" not in cleaned3
        assert "#" not in cleaned3
        assert "$" not in cleaned3


class TestSearchCache:
    """测试搜索缓存"""
    
    @pytest.fixture
    def temp_cache_dir(self, tmp_path):
        """创建临时缓存目录"""
        cache_dir = tmp_path / "test_cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        return cache_dir
    
    def test_cache_save_and_load_index(self, temp_cache_dir):
        """测试保存和加载索引"""
        cache = SearchCache(cache_dir=temp_cache_dir)
        
        results = [
            SearchResult(
                title="测试",
                url="https://example.com",
                snippet="测试摘要",
                source="test",
                relevance_score=0.8
            )
        ]
        cache.set("test query", "default", results)
        
        # 创建新的缓存实例，应该能加载之前的数据
        cache2 = SearchCache(cache_dir=temp_cache_dir)
        
        cached_results = cache2.get("test query", "default")
        assert cached_results is not None
        assert len(cached_results) == 1
    
    def test_cache_with_expired_entry_on_load(self, temp_cache_dir):
        """测试加载时处理过期条目"""
        cache = SearchCache(cache_dir=temp_cache_dir)
        
        # 手动添加一个过期的条目到索引文件
        past_time = datetime.now() - timedelta(hours=25)
        entry = CacheEntry(
            query="old query",
            source="default",
            results=[],
            timestamp=past_time.isoformat(),
            ttl_hours=24
        )
        
        # 直接修改索引文件
        import json
        index_file = temp_cache_dir / "index.json"
        index_data = {
            "old_key": entry.to_dict()
        }
        with open(index_file, 'w') as f:
            json.dump(index_data, f)
        
        # 创建新的缓存实例，应该自动忽略过期条目
        cache2 = SearchCache(cache_dir=temp_cache_dir)
        
        # 过期条目不应该被加载
        assert len(cache2._index) == 0
    
    def test_cache_max_size_cleanup(self, temp_cache_dir):
        """测试缓存大小限制清理"""
        # 设置较小的缓存大小
        cache = SearchCache(cache_dir=temp_cache_dir, max_cache_size=3)
        
        # 添加超过限制的缓存
        for i in range(5):
            results = [
                SearchResult(
                    title=f"测试{i}",
                    url=f"https://example{i}.com",
                    snippet=f"摘要{i}",
                    source="test",
                    relevance_score=0.8
                )
            ]
            cache.set(f"query{i}", "default", results)
        
        # 验证缓存大小被限制
        assert len(cache._index) <= 3
    
    def test_cache_delete(self, temp_cache_dir):
        """测试删除特定缓存"""
        cache = SearchCache(cache_dir=temp_cache_dir)
        
        results = [
            SearchResult(
                title="测试",
                url="https://example.com",
                snippet="测试摘要",
                source="test",
                relevance_score=0.8
            )
        ]
        cache.set("test query", "default", results)
        
        # 删除缓存
        cache_key = cache._get_cache_key("test query", "default")
        cache.delete(cache_key)
        
        # 验证已删除
        assert cache.get("test query", "default") is None
    
    def test_cleanup_expired(self, temp_cache_dir):
        """测试清理过期缓存"""
        cache = SearchCache(cache_dir=temp_cache_dir)
        
        # 添加一个过期的缓存条目
        past_time = datetime.now() - timedelta(hours=25)
        entry = CacheEntry(
            query="old query",
            source="default",
            results=[],
            timestamp=past_time.isoformat(),
            ttl_hours=24
        )
        cache._index["old_key"] = entry
        
        # 添加一个有效的缓存条目
        results = [
            SearchResult(
                title="测试",
                url="https://example.com",
                snippet="测试摘要",
                source="test",
                relevance_score=0.8
            )
        ]
        cache.set("new query", "default", results)
        
        # 清理过期缓存
        cache.cleanup_expired()
        
        # 验证过期缓存被删除
        assert "old_key" not in cache._index
        assert len(cache._index) == 1
    
    def test_cache_size_calculation(self, temp_cache_dir):
        """测试缓存大小计算"""
        cache = SearchCache(cache_dir=temp_cache_dir)
        
        size = cache.get_size()
        assert isinstance(size, int)
        assert size >= 0
    
    def test_cache_with_different_sources(self, temp_cache_dir):
        """测试不同来源的缓存"""
        cache = SearchCache(cache_dir=temp_cache_dir)
        
        results = [
            SearchResult(
                title="测试",
                url="https://example.com",
                snippet="测试摘要",
                source="test",
                relevance_score=0.8
            )
        ]
        
        # 缓存不同来源的结果
        cache.set("query1", "source1", results)
        cache.set("query2", "source2", results)
        
        stats = cache.get_stats()
        assert 'source_distribution' in stats
        assert 'source1' in stats['source_distribution']
        assert 'source2' in stats['source_distribution']
    
    def test_initialization(self, temp_cache_dir):
        """测试初始化"""
        cache = SearchCache(cache_dir=temp_cache_dir, max_cache_size=100)
        assert cache is not None
        assert cache.cache_dir == temp_cache_dir
        assert cache.max_cache_size == 100
    
    def test_cache_key_generation(self, temp_cache_dir):
        """测试缓存键生成"""
        cache = SearchCache(cache_dir=temp_cache_dir)
        
        key1 = cache._get_cache_key("test query", "default")
        key2 = cache._get_cache_key("test query", "default")
        key3 = cache._get_cache_key("different query", "default")
        
        # 相同的查询应该生成相同的键
        assert key1 == key2
        
        # 不同的查询应该生成不同的键
        assert key1 != key3
    
    def test_cache_set_and_get(self, temp_cache_dir):
        """测试缓存设置和获取"""
        cache = SearchCache(cache_dir=temp_cache_dir)
        
        # 创建测试结果
        results = [
            SearchResult(
                title="测试",
                url="https://example.com",
                snippet="测试摘要",
                source="test",
                relevance_score=0.8
            )
        ]
        
        # 设置缓存
        cache.set("test query", "default", results, ttl_hours=1)
        
        # 获取缓存
        cached_results = cache.get("test query", "default")
        
        assert cached_results is not None
        assert len(cached_results) == 1
        assert cached_results[0].title == "测试"
    
    def test_cache_expiry(self, temp_cache_dir):
        """测试缓存过期"""
        cache = SearchCache(cache_dir=temp_cache_dir)
        
        # 创建一个已过期的缓存条目
        past_time = datetime.now() - timedelta(hours=2)
        entry = CacheEntry(
            query="old query",
            source="default",
            results=[],
            timestamp=past_time.isoformat(),
            ttl_hours=1
        )
        
        cache._index["test_key"] = entry
        
        # 检查是否过期
        assert entry.is_expired() == True
    
    def test_cache_clear(self, temp_cache_dir):
        """测试清空缓存"""
        cache = SearchCache(cache_dir=temp_cache_dir)
        
        # 添加一些缓存
        results = [
            SearchResult(
                title="测试",
                url="https://example.com",
                snippet="测试摘要",
                source="test",
                relevance_score=0.8
            )
        ]
        cache.set("test query", "default", results)
        
        # 清空缓存
        cache.clear()
        
        # 验证缓存已清空
        assert len(cache._index) == 0
    
    def test_cache_stats(self, temp_cache_dir):
        """测试缓存统计"""
        cache = SearchCache(cache_dir=temp_cache_dir)
        
        # 添加一些缓存
        results = [
            SearchResult(
                title="测试",
                url="https://example.com",
                snippet="测试摘要",
                source="test",
                relevance_score=0.8
            )
        ]
        cache.set("test query", "default", results)
        
        # 获取统计信息
        stats = cache.get_stats()
        
        assert stats['total_entries'] >= 1
        assert 'max_cache_size' in stats
        assert 'cache_dir' in stats
        assert 'source_distribution' in stats


class TestResultProcessor:
    """测试结果处理器"""
    
    def test_initialization(self):
        """测试初始化"""
        processor = ResultProcessor()
        assert processor is not None
        assert processor.logger is not None
    
    def test_filter_by_domain(self):
        """测试按域名过滤"""
        processor = ResultProcessor()
        
        results = [
            SearchResult(
                title="测试1",
                url="https://example1.com/path",
                snippet="摘要1",
                source="test",
                relevance_score=0.8
            ),
            SearchResult(
                title="测试2",
                url="https://example2.com/path",
                snippet="摘要2",
                source="test",
                relevance_score=0.7
            ),
            SearchResult(
                title="测试3",
                url="https://different.com/path",
                snippet="摘要3",
                source="test",
                relevance_score=0.9
            )
        ]
        
        filtered = processor.filter_by_domain(results, "example1")
        
        assert len(filtered) == 1
        assert filtered[0].url == "https://example1.com/path"
    
    def test_filter_by_keywords(self):
        """测试按关键词过滤"""
        processor = ResultProcessor()
        
        results = [
            SearchResult(
                title="Python编程教程",
                url="https://example1.com",
                snippet="学习Python编程",
                source="test",
                relevance_score=0.8
            ),
            SearchResult(
                title="Java开发指南",
                url="https://example2.com",
                snippet="Java编程入门",
                source="test",
                relevance_score=0.7
            ),
            SearchResult(
                title="JavaScript框架",
                url="https://example3.com",
                snippet="前端开发",
                source="test",
                relevance_score=0.9
            )
        ]
        
        filtered = processor.filter_by_keywords(results, ["Python", "编程"])
        
        # 应该包含 "Python编程教程"（标题匹配）
        assert len(filtered) >= 1
        assert any("Python" in r.title or "编程" in r.snippet for r in filtered)
    
    def test_enrich_results(self):
        """测试丰富结果"""
        processor = ResultProcessor()
        
        results = [
            SearchResult(
                title="测试",
                url="https://github.com/test/repo",
                snippet="测试摘要",
                source="test",
                relevance_score=0.8
            )
        ]
        
        enriched = processor.enrich_results(results)
        
        assert len(enriched) == 1
        assert 'domain' in enriched[0].metadata
        assert 'site_type' in enriched[0].metadata
        assert enriched[0].metadata['site_type'] == 'code_repository'
    
    def test_merge_results(self):
        """测试合并结果"""
        processor = ResultProcessor()
        
        results_set1 = [
            SearchResult(
                title="测试1",
                url="https://example1.com",
                snippet="摘要1",
                source="source1",
                relevance_score=0.8
            )
        ]
        
        results_set2 = [
            SearchResult(
                title="测试2",
                url="https://example2.com",
                snippet="摘要2",
                source="source2",
                relevance_score=0.9
            )
        ]
        
        merged = processor.merge_results([results_set1, results_set2], max_results=10)
        
        assert len(merged) == 2
    
    def test_format_results_markdown(self):
        """测试格式化为 Markdown"""
        processor = ResultProcessor()
        
        results = [
            SearchResult(
                title="测试标题",
                url="https://example.com",
                snippet="测试摘要",
                source="test",
                relevance_score=0.8
            )
        ]
        
        formatted = processor.format_results(results, format='markdown')
        
        assert "测试标题" in formatted
        assert "https://example.com" in formatted
        assert "#" in formatted  # Markdown 标题
    
    def test_classify_site_type(self):
        """测试网站类型分类"""
        processor = ResultProcessor()
        
        # 测试不同类型的网站
        assert processor._classify_site_type("github.com") == 'code_repository'
        assert processor._classify_site_type("stackoverflow.com") == 'qa_forum'
        assert processor._classify_site_type("wikipedia.org") == 'wiki'
        assert processor._classify_site_type("arxiv.org") == 'academic'
        assert processor._classify_site_type("docs.python.org") == 'documentation'
        assert processor._classify_site_type("blog.example.com") == 'blog'
        assert processor._classify_site_type("example.com") == 'general'
    
    def test_deduplicate(self):
        """测试去重"""
        processor = ResultProcessor()
        
        # 创建重复的结果
        results = [
            SearchResult(
                title="测试1",
                url="https://example.com",
                snippet="摘要1",
                source="test",
                relevance_score=0.8
            ),
            SearchResult(
                title="测试2",
                url="https://example.com",  # 相同的 URL
                snippet="摘要2",
                source="test",
                relevance_score=0.7
            ),
            SearchResult(
                title="测试3",
                url="https://different.com",
                snippet="摘要3",
                source="test",
                relevance_score=0.9
            )
        ]
        
        unique_results = processor.deduplicate(results)
        
        # 应该去重，只剩下 2 个结果
        assert len(unique_results) == 2
    
    def test_sort_by_relevance(self):
        """测试按相关性排序"""
        processor = ResultProcessor()
        
        results = [
            SearchResult(
                title="低相关性",
                url="https://example1.com",
                snippet="摘要1",
                source="test",
                relevance_score=0.5
            ),
            SearchResult(
                title="高相关性",
                url="https://example2.com",
                snippet="摘要2",
                source="test",
                relevance_score=0.9
            ),
            SearchResult(
                title="中相关性",
                url="https://example3.com",
                snippet="摘要3",
                source="test",
                relevance_score=0.7
            )
        ]
        
        sorted_results = processor.sort_by_relevance(results, descending=True)
        
        # 第一个应该是相关性最高的
        assert sorted_results[0].relevance_score == 0.9
        assert sorted_results[-1].relevance_score == 0.5
    
    def test_filter_by_source(self):
        """测试按来源过滤"""
        processor = ResultProcessor()
        
        results = [
            SearchResult(
                title="测试1",
                url="https://example1.com",
                snippet="摘要1",
                source="source1",
                relevance_score=0.8
            ),
            SearchResult(
                title="测试2",
                url="https://example2.com",
                snippet="摘要2",
                source="source2",
                relevance_score=0.7
            ),
            SearchResult(
                title="测试3",
                url="https://example3.com",
                snippet="摘要3",
                source="source1",
                relevance_score=0.9
            )
        ]
        
        filtered = processor.filter_by_source(results, "source1")
        
        assert len(filtered) == 2
        assert all(r.source == "source1" for r in filtered)
    
    def test_limit_results(self):
        """测试限制结果数量"""
        processor = ResultProcessor()
        
        results = [
            SearchResult(
                title=f"测试{i}",
                url=f"https://example{i}.com",
                snippet=f"摘要{i}",
                source="test",
                relevance_score=0.8
            )
            for i in range(10)
        ]
        
        limited = processor.limit_results(results, 5)
        
        assert len(limited) == 5
    
    def test_format_results_text(self):
        """测试格式化为文本"""
        processor = ResultProcessor()
        
        results = [
            SearchResult(
                title="测试标题",
                url="https://example.com",
                snippet="测试摘要",
                source="test",
                relevance_score=0.8
            )
        ]
        
        formatted = processor.format_results(results, format='text')
        
        assert "测试标题" in formatted
        assert "https://example.com" in formatted
        assert "test" in formatted
    
    def test_format_results_json(self):
        """测试格式化为 JSON"""
        processor = ResultProcessor()
        
        results = [
            SearchResult(
                title="测试标题",
                url="https://example.com",
                snippet="测试摘要",
                source="test",
                relevance_score=0.8
            )
        ]
        
        formatted = processor.format_results(results, format='json')
        
        # 验证可以解析为 JSON
        data = json.loads(formatted)
        assert len(data) == 1
        assert data[0]['title'] == "测试标题"
    
    def test_get_summary(self):
        """测试获取结果摘要"""
        processor = ResultProcessor()
        
        results = [
            SearchResult(
                title="测试1",
                url="https://example1.com",
                snippet="摘要1",
                source="source1",
                relevance_score=0.8
            ),
            SearchResult(
                title="测试2",
                url="https://example2.com",
                snippet="摘要2",
                source="source2",
                relevance_score=0.9
            )
        ]
        
        summary = processor.get_summary(results)
        
        assert summary['total'] == 2
        assert 'avg_relevance' in summary
        assert 'sources' in summary
        assert 'timestamp' in summary


class TestCacheEntry:
    """测试缓存条目"""
    
    def test_cache_entry_creation(self):
        """测试创建缓存条目"""
        entry = CacheEntry(
            query="test query",
            source="default",
            results=[],
            timestamp=datetime.now().isoformat(),
            ttl_hours=24
        )
        
        assert entry.query == "test query"
        assert entry.source == "default"
        assert entry.ttl_hours == 24
    
    def test_is_expired(self):
        """测试过期检查"""
        # 未过期的条目
        future_time = datetime.now() + timedelta(hours=1)
        entry1 = CacheEntry(
            query="test query",
            source="default",
            results=[],
            timestamp=future_time.isoformat(),
            ttl_hours=24
        )
        assert entry1.is_expired() == False
        
        # 已过期的条目
        past_time = datetime.now() - timedelta(hours=25)
        entry2 = CacheEntry(
            query="test query",
            source="default",
            results=[],
            timestamp=past_time.isoformat(),
            ttl_hours=24
        )
        assert entry2.is_expired() == True
    
    def test_to_dict(self):
        """测试转换为字典"""
        entry = CacheEntry(
            query="test query",
            source="default",
            results=[],
            timestamp=datetime.now().isoformat(),
            ttl_hours=24
        )
        
        entry_dict = entry.to_dict()
        
        assert entry_dict['query'] == "test query"
        assert entry_dict['source'] == "default"
        assert entry_dict['ttl_hours'] == 24


class TestWebSearchCacheBehavior:
    """测试 web_search 函数的缓存行为"""
    
    @pytest.fixture
    def temp_cache_dir(self, tmp_path):
        """创建临时缓存目录"""
        cache_dir = tmp_path / "test_cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        return cache_dir
    
    def test_web_search_cache_bypass(self, temp_cache_dir):
        """测试缓存可以被新数据覆盖，模拟 use_cache=False 的行为"""
        # 创建一个模拟缓存，预先填充旧数据
        cache = SearchCache(cache_dir=temp_cache_dir)
        old_results = [
            SearchResult(
                title="Old JDK Version",
                url="https://example.com/old",
                snippet="Java SE 17.0.19",
                source="test",
                relevance_score=0.8,
                timestamp=(datetime.now() - timedelta(hours=2)).isoformat()
            )
        ]
        cache.set("Java SE latest version", "default", old_results, ttl_hours=24)
        
        # 验证缓存中有旧数据
        cached_data = cache.get("Java SE latest version", "default")
        assert cached_data is not None
        assert len(cached_data) == 1
        assert cached_data[0].snippet == "Java SE 17.0.19"
        
        # 模拟网络搜索返回新数据（覆盖缓存）
        fresh_results = [
            SearchResult(
                title="New JDK Version",
                url="https://example.com/new",
                snippet="Java SE 21.0.1",
                source="test",
                relevance_score=0.9,
                timestamp=datetime.now().isoformat()
            )
        ]
        cache.set("Java SE latest version", "default", fresh_results, ttl_hours=24)
        
        # 验证新数据覆盖了旧数据
        updated_data = cache.get("Java SE latest version", "default")
        assert updated_data is not None
        assert updated_data[0].snippet == "Java SE 21.0.1"
    
    def test_cache_key_consistency(self, temp_cache_dir):
        """测试缓存键的一致性"""
        cache = SearchCache(cache_dir=temp_cache_dir)
        
        # 测试相同的查询和源生成相同的键
        key1 = cache._get_cache_key("test query", "default")
        key2 = cache._get_cache_key("test query", "default")
        assert key1 == key2
        
        # 测试不同的查询生成不同的键
        key3 = cache._get_cache_key("different query", "default")
        assert key1 != key3
        
        # 测试不同的源生成不同的键
        key4 = cache._get_cache_key("test query", "wikipedia")
        assert key1 != key4


class TestGlobalSingletons:
    """测试全局单例函数"""
    
    def test_get_search_engine_manager(self):
        """测试获取搜索引擎管理器单例"""
        from web_search.search_engine import get_search_engine_manager
        
        manager1 = get_search_engine_manager()
        manager2 = get_search_engine_manager()
        
        # 应该返回同一个实例
        assert manager1 is manager2
    
    def test_get_content_extractor(self):
        """测试获取内容提取器单例"""
        from web_search.content_extractor import get_content_extractor
        
        extractor1 = get_content_extractor()
        extractor2 = get_content_extractor()
        
        # 应该返回同一个实例
        assert extractor1 is extractor2
    
    def test_get_search_cache(self, tmp_path):
        """测试获取搜索缓存单例"""
        from web_search.search_cache import get_search_cache
        
        cache1 = get_search_cache(cache_dir=tmp_path)
        cache2 = get_search_cache(cache_dir=tmp_path)
        
        # 应该返回同一个实例
        assert cache1 is cache2
    
    def test_get_result_processor(self):
        """测试获取结果处理器单例"""
        from web_search.result_processor import get_result_processor
        
        processor1 = get_result_processor()
        processor2 = get_result_processor()
        
        # 应该返回同一个实例
        assert processor1 is processor2
    
    def test_search_engine_manager_set_as_default(self):
        """测试设置默认搜索引擎"""
        from web_search.search_engine import get_search_engine_manager
        
        manager = get_search_engine_manager()
        
        # 创建模拟引擎
        class MockEngine:
            def get_source_name(self):
                return "mock"
            def is_available(self):
                return True
            async def search(self, query, max_results=10):
                return []
        
        mock_engine = MockEngine()
        manager.register_engine("mock", mock_engine, set_as_default=True)
        
        # 验证设置为默认
        default_engine = manager.get_engine('default')
        assert default_engine is mock_engine
    
    def test_is_expired(self):
        """测试过期检查"""
        # 未过期的条目
        future_time = datetime.now() + timedelta(hours=1)
        entry1 = CacheEntry(
            query="test query",
            source="default",
            results=[],
            timestamp=future_time.isoformat(),
            ttl_hours=24
        )
        assert entry1.is_expired() == False
        
        # 已过期的条目
        past_time = datetime.now() - timedelta(hours=25)
        entry2 = CacheEntry(
            query="test query",
            source="default",
            results=[],
            timestamp=past_time.isoformat(),
            ttl_hours=24
        )
        assert entry2.is_expired() == True
    
    def test_to_dict(self):
        """测试转换为字典"""
        entry = CacheEntry(
            query="test query",
            source="default",
            results=[],
            timestamp=datetime.now().isoformat(),
            ttl_hours=24
        )
        
        entry_dict = entry.to_dict()
        
        assert entry_dict['query'] == "test query"
        assert entry_dict['source'] == "default"
        assert entry_dict['ttl_hours'] == 24
