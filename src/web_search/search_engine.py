#!/usr/bin/env python3
"""
搜索引擎抽象接口和实现
"""
from abc import ABC, abstractmethod
from typing import List, Dict, Optional
from dataclasses import dataclass, field
import asyncio
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    """搜索结果数据类"""
    title: str
    url: str
    snippet: str
    source: str
    relevance_score: float
    metadata: Dict = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def to_dict(self) -> Dict:
        """转换为字典"""
        return {
            'title': self.title,
            'url': self.url,
            'snippet': self.snippet,
            'source': self.source,
            'relevance_score': self.relevance_score,
            'metadata': self.metadata,
            'timestamp': self.timestamp
        }


class SearchEngine(ABC):
    """搜索引擎抽象接口"""
    
    def __init__(self):
        self.logger = logger
        
    @abstractmethod
    async def search(self, query: str, max_results: int = 10) -> List[SearchResult]:
        """执行搜索"""
        pass
    
    @abstractmethod
    def get_source_name(self) -> str:
        """获取搜索源名称"""
        pass
    
    @abstractmethod
    def is_available(self) -> bool:
        """检查搜索引擎是否可用"""
        pass


class DuckDuckGoSearchEngine(SearchEngine):
    """DuckDuckGo 搜索引擎实现"""
    
    def __init__(self):
        super().__init__()
        self._ddgs = None
        self._initialize()
    
    def _initialize(self):
        """初始化 DuckDuckGo 搜索客户端"""
        try:
            from duckduckgo_search import DDGS
            self._ddgs = DDGS()
            self.logger.info("DuckDuckGo 搜索引擎初始化成功")
        except ImportError as e:
            self.logger.error(f"DuckDuckGo 搜索库未安装: {e}")
            self._ddgs = None
        except Exception as e:
            self.logger.error(f"DuckDuckGo 搜索引擎初始化失败: {e}")
            self._ddgs = None
    
    async def search(self, query: str, max_results: int = 10) -> List[SearchResult]:
        """执行 DuckDuckGo 搜索"""
        if not self.is_available():
            self.logger.warning("DuckDuckGo 搜索引擎不可用")
            return []
        
        results = []
        try:
            # 使用异步方式执行同步搜索
            loop = asyncio.get_event_loop()
            ddgs_results = await loop.run_in_executor(
                None, 
                lambda: list(self._ddgs.text(query, max_results=max_results))
            )
            
            for result in ddgs_results:
                results.append(SearchResult(
                    title=result.get('title', ''),
                    url=result.get('href', ''),
                    snippet=result.get('body', ''),
                    source='duckduckgo',
                    relevance_score=self._calculate_relevance(result, query),
                    metadata={
                        'source_type': 'web',
                        'domain': self._extract_domain(result.get('href', ''))
                    }
                ))
            
            self.logger.info(f"DuckDuckGo 搜索完成: 查询='{query}', 结果数={len(results)}")
            
        except Exception as e:
            self.logger.error(f"DuckDuckGo 搜索失败: {e}")
            return []
        
        return results
    
    def _calculate_relevance(self, result: Dict, query: str) -> float:
        """计算相关性得分"""
        try:
            title = result.get('title', '')
            body = result.get('body', '')
            
            # 基于文本长度的简单相关性计算
            title_score = min(1.0, len(title) / 100.0)
            body_score = min(1.0, len(body) / 500.0)
            
            # 检查查询词在标题和正文中出现的次数
            query_lower = query.lower()
            title_lower = title.lower()
            body_lower = body.lower()
            
            title_match_score = title_lower.count(query_lower) * 0.1
            body_match_score = body_lower.count(query_lower) * 0.05
            
            # 综合得分
            total_score = (title_score * 0.4 + body_score * 0.4 + 
                          title_match_score * 0.15 + body_match_score * 0.05)
            
            return min(1.0, total_score)
        except Exception as e:
            self.logger.warning(f"相关性计算失败: {e}")
            return 0.5  # 默认中等相关性
    
    def _extract_domain(self, url: str) -> str:
        """提取域名"""
        try:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            return parsed.netloc
        except Exception:
            return url
    
    def get_source_name(self) -> str:
        return "DuckDuckGo"
    
    def is_available(self) -> bool:
        """检查搜索引擎是否可用"""
        return self._ddgs is not None


class SearchEngineManager:
    """搜索引擎管理器 - 支持多搜索引擎"""
    
    def __init__(self):
        self.engines: Dict[str, SearchEngine] = {}
        self._register_default_engines()
    
    def _register_default_engines(self):
        """注册默认搜索引擎"""
        # 注册 DuckDuckGo
        ddg_engine = DuckDuckGoSearchEngine()
        if ddg_engine.is_available():
            self.engines['duckduckgo'] = ddg_engine
            self.engines['default'] = ddg_engine  # 设置为默认
    
    def register_engine(self, name: str, engine: SearchEngine, set_as_default: bool = False):
        """注册搜索引擎"""
        self.engines[name] = engine
        if set_as_default:
            self.engines['default'] = engine
    
    def get_engine(self, name: str = 'default') -> Optional[SearchEngine]:
        """获取搜索引擎"""
        return self.engines.get(name)
    
    def list_engines(self) -> List[str]:
        """列出所有可用搜索引擎"""
        return list(self.engines.keys())
    
    async def search(self, query: str, source: str = 'default', 
                    max_results: int = 10) -> List[SearchResult]:
        """执行搜索"""
        engine = self.get_engine(source)
        if engine is None:
            logger.error(f"搜索引擎 '{source}' 不可用")
            return []
        
        return await engine.search(query, max_results)


# 全局搜索引擎管理器实例
_search_engine_manager = None

def get_search_engine_manager() -> SearchEngineManager:
    """获取全局搜索引擎管理器实例"""
    global _search_engine_manager
    if _search_engine_manager is None:
        _search_engine_manager = SearchEngineManager()
    return _search_engine_manager
