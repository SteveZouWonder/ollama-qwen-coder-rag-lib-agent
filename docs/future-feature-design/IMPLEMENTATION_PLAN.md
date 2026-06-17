# 系统能力增强实现方案

> 基于 Qwen2.5-Coder:7B 模型特性的系统能力扩展详细实现方案

---

## 📋 文档信息

- **创建日期**: 2026-06-15
- **功能编号**: F5
- **状态**: 🚧 实现方案设计阶段
- **预计周期**: 8-12 周
- **优先级调整**: 网络搜索能力提升为核心功能

---

## 🎯 实施原则

基于项目特点和用户需求，确定以下实施原则：

1. **网络搜索优先**: 将网络搜索能力作为第一阶段核心功能
2. **架构一致性**: 与现有 RAG + ReAct Agent 架构完全集成
3. **渐进实施**: 每个阶段都有可交付的价值
4. **资源可控**: 适应 8-16GB 内存限制
5. **隐私保护**: 本地优先，网络功能可配置

---

## 🏗️ 代码架构设计

### 新增模块结构

```
src/
├── web_search/              # 网络搜索模块
│   ├── __init__.py
│   ├── search_engine.py    # 搜索引擎抽象接口
│   ├── duckduckgo_search.py # DuckDuckGo 搜索实现
│   ├── content_extractor.py # 网页内容提取
│   ├── result_processor.py # 搜索结果处理
│   └── search_cache.py    # 搜索缓存管理
├── code_analyzer/          # 代码分析模块
│   ├── __init__.py
│   ├── ast_analyzer.py     # AST 语法树分析
│   ├── semantic_search.py  # 代码语义搜索
│   ├── quality_checker.py  # 代码质量检查
│   └── code_indexer.py     # 代码索引管理
├── git_integration/         # Git 集成模块
│   ├── __init__.py
│   ├── git_analyzer.py     # Git 历史分析
│   ├── commit_generator.py # 提交信息生成
│   └── conflict_resolver.py # 冲突解决辅助
├── knowledge_graph/         # 知识图谱模块
│   ├── __init__.py
│   ├── graph_builder.py    # 知识图谱构建
│   ├── entity_extractor.py # 实体关系提取
│   ├── graph_query.py      # 图谱查询
│   └── visualizer.py       # 可视化
├── database_tools/          # 数据库工具模块
│   ├── __init__.py
│   ├── db_connector.py     # 数据库连接
│   ├── query_generator.py  # SQL 查询生成
│   └── data_analyzer.py    # 数据分析
└── time_series/            # 时间序列分析模块
    ├── __init__.py
    ├── analyzer.py         # 时间序列分析
    ├── predictor.py        # 预测模型
    └── anomaly_detector.py # 异常检测
```

### 集成点设计

#### 1. Agent 工具链集成
在 `agent_tools.py` 中新增工具：

```python
# 网络搜索工具
registry.register("web_search", web_search, 
                  "网络搜索（支持 DuckDuckGo、GitHub、arXiv）",
                  {"query": "搜索查询", "source": "搜索来源", "max_results": "最大结果数"}, 
                  safe=True)

registry.register("web_content_extract", web_content_extract,
                  "提取网页内容并清理格式",
                  {"url": "网页 URL"}, 
                  safe=True)

# 代码分析工具
registry.register("ast_search", ast_search,
                  "AST 语法树搜索（函数、类、变量）",
                  {"pattern": "搜索模式", "path": "搜索路径", "node_type": "节点类型"}, 
                  safe=True)

registry.register("code_quality_check", code_quality_check,
                  "代码质量分析（安全、性能、复杂度）",
                  {"path": "代码路径", "check_type": "检查类型"}, 
                  safe=True)

# Git 工具
registry.register("git_analyze", git_analyze,
                  "Git 历史分析和变更追踪",
                  {"repo_path": "仓库路径", "analysis_type": "分析类型"}, 
                  safe=True)

# 知识图谱工具
registry.register("knowledge_graph_query", knowledge_graph_query,
                  "知识图谱查询和推理",
                  {"query": "图谱查询", "depth": "搜索深度"}, 
                  safe=True)

# 数据库工具
registry.register("db_query", db_query,
                  "数据库查询和数据分析",
                  {"query": "查询语句", "db_type": "数据库类型"}, 
                  safe=False)  # 需要确认
```

#### 2. RAG 引擎集成
在 `rag_engine.py` 中扩展知识库：

```python
class EnhancedRAGEngine(RAGEngine):
    def __init__(self, enable_web_search=True, **kwargs):
        super().__init__(**kwargs)
        self.enable_web_search = enable_web_search
        if enable_web_search:
            from web_search.search_engine import SearchEngine
            self.search_engine = SearchEngine()
```

#### 3. CLI 命令集成
在 `query_interface.py` 中新增命令：

```python
# 网络搜索命令
/web-search <query>         # 网络搜索
/web-cache status           # 搜索缓存状态
/web-cache clear            # 清空搜索缓存

# 代码分析命令
/code-ast <pattern>         # AST 搜索
/code-quality <path>        # 代码质量检查
/code-semantic <query>      # 代码语义搜索

# Git 命令
/git-analyze <repo>         # Git 分析
/git-commit-gen             # 生成提交信息

# 知识图谱命令
/graph-build                # 构建知识图谱
/graph-query <query>        # 图谱查询
/graph-visualize            # 图谱可视化

# 数据库命令
/db-connect <config>        # 连接数据库
/db-query <sql>             # 执行查询
/db-analyze <table>         # 数据分析
```

---

## 🚀 阶段一：网络搜索核心功能（Week 1-3）

### 目标
实现完整的网络搜索能力，作为系统核心功能

### F5.7: 轻量级网络搜索（核心功能）

#### 实施步骤

##### Day 1-2: 基础搜索引擎

**文件**: `src/web_search/search_engine.py`

```python
from abc import ABC, abstractmethod
from typing import List, Dict, Optional
from dataclasses import dataclass
import asyncio

@dataclass
class SearchResult:
    """搜索结果数据类"""
    title: str
    url: str
    snippet: str
    source: str
    relevance_score: float
    metadata: Dict = None

class SearchEngine(ABC):
    """搜索引擎抽象接口"""
    
    @abstractmethod
    async def search(self, query: str, max_results: int = 10) -> List[SearchResult]:
        """执行搜索"""
        pass
    
    @abstractmethod
    def get_source_name(self) -> str:
        """获取搜索源名称"""
        pass

class DuckDuckGoSearchEngine(SearchEngine):
    """DuckDuckGo 搜索引擎实现"""
    
    def __init__(self):
        from duckduckgo_search import DDGS
        self.ddgs = DDGS()
    
    async def search(self, query: str, max_results: int = 10) -> List[SearchResult]:
        """执行 DuckDuckGo 搜索"""
        results = []
        try:
            # 使用异步方式
            loop = asyncio.get_event_loop()
            ddgs_results = await loop.run_in_executor(
                None, 
                lambda: list(self.ddgs.text(query, max_results=max_results))
            )
            
            for result in ddgs_results:
                results.append(SearchResult(
                    title=result.get('title', ''),
                    url=result.get('href', ''),
                    snippet=result.get('body', ''),
                    source='duckduckgo',
                    relevance_score=self._calculate_relevance(result),
                    metadata={'source_type': 'web'}
                ))
        except Exception as e:
            print(f"DuckDuckGo 搜索失败: {e}")
        
        return results
    
    def _calculate_relevance(self, result: Dict) -> float:
        """计算相关性得分"""
        # 简单的相关性计算
        title = result.get('title', '')
        body = result.get('body', '')
        return min(1.0, (len(title) + len(body)) / 500.0)
    
    def get_source_name(self) -> str:
        return "DuckDuckGo"

class GitHubSearchEngine(SearchEngine):
    """GitHub 搜索引擎"""
    
    def __init__(self, token: Optional[str] = None):
        self.token = token
        self.base_url = "https://api.github.com"
    
    async def search(self, query: str, max_results: int = 10) -> List[SearchResult]:
        """GitHub 代码搜索"""
        import aiohttp
        
        results = []
        headers = {}
        if self.token:
            headers['Authorization'] = f'token {self.token}'
        
        try:
            async with aiohttp.ClientSession() as session:
                params = {
                    'q': query,
                    'per_page': max_results,
                    'sort': 'stars'
                }
                async with session.get(
                    f"{self.base_url}/search/code",
                    headers=headers,
                    params=params
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        for item in data.get('items', []):
                            results.append(SearchResult(
                                title=item.get('name', ''),
                                url=item.get('html_url', ''),
                                snippet=item.get('text_matches', [{}])[0].get('fragment', '') if item.get('text_matches') else '',
                                source='github',
                                relevance_score=item.get('score', 0.0) / 100.0,
                                metadata={
                                    'repository': item.get('repository', {}).get('full_name', ''),
                                    'path': item.get('path', ''),
                                    'source_type': 'code'
                                }
                            ))
        except Exception as e:
            print(f"GitHub 搜索失败: {e}")
        
        return results
    
    def get_source_name(self) -> str:
        return "GitHub"

class ArXivSearchEngine(SearchEngine):
    """arXiv 学术论文搜索"""
    
    def __init__(self):
        self.base_url = "http://export.arxiv.org/api/query"
    
    async def search(self, query: str, max_results: int = 10) -> List[SearchResult]:
        """arXiv 论文搜索"""
        import aiohttp
        import feedparser
        
        results = []
        try:
            async with aiohttp.ClientSession() as session:
                params = {
                    'search_query': f'all:{query}',
                    'start': 0,
                    'max_results': max_results
                }
                async with session.get(self.base_url, params=params) as response:
                    if response.status == 200:
                        xml_content = await response.text()
                        feed = feedparser.parse(xml_content)
                        
                        for entry in feed.entries:
                            # 提取作者信息
                            authors = ', '.join([author.name for author in entry.authors])
                            
                            results.append(SearchResult(
                                title=entry.title,
                                url=entry.id,
                                snippet=entry.summary,
                                source='arxiv',
                                relevance_score=0.8,  # arXiv 结果通常相关性较高
                                metadata={
                                    'authors': authors,
                                    'published': entry.published,
                                    'arxiv_id': entry.id.split('/abs/')[-1],
                                    'source_type': 'academic'
                                }
                            ))
        except Exception as e:
            print(f"arXiv 搜索失败: {e}")
        
        return results
    
    def get_source_name(self) -> str:
        return "arXiv"

class CompositeSearchEngine:
    """组合搜索引擎"""
    
    def __init__(self):
        self.engines = [
            DuckDuckGoSearchEngine(),
            GitHubSearchEngine(),
            ArXivSearchEngine()
        ]
    
    async def search_all(self, query: str, max_results: int = 10) -> Dict[str, List[SearchResult]]:
        """在所有搜索引擎中搜索"""
        results = {}
        tasks = []
        
        for engine in self.engines:
            task = engine.search(query, max_results)
            tasks.append((engine.get_source_name(), task))
        
        # 并行执行所有搜索
        completed_tasks = await asyncio.gather(*[task for _, task in tasks], return_exceptions=True)
        
        for (source_name, _), result in zip(tasks, completed_tasks):
            if isinstance(result, Exception):
                print(f"{source_name} 搜索失败: {result}")
                results[source_name] = []
            else:
                results[source_name] = result
        
        return results
    
    async def search_unified(self, query: str, max_results: int = 10) -> List[SearchResult]:
        """统一搜索结果"""
        all_results = await self.search_all(query, max_results)
        
        # 合并和排序结果
        unified_results = []
        for source_results in all_results.values():
            unified_results.extend(source_results)
        
        # 按相关性排序
        unified_results.sort(key=lambda x: x.relevance_score, reverse=True)
        
        return unified_results[:max_results]
```

##### Day 3-4: 内容提取和清理

**文件**: `src/web_search/content_extractor.py`

```python
import asyncio
import aiohttp
from typing import Optional, Dict
from bs4 import BeautifulSoup
import trafilatura
from readability import Document

class WebContentExtractor:
    """网页内容提取器"""
    
    def __init__(self):
        self.session = None
    
    async def _get_session(self):
        """获取 aiohttp 会话"""
        if self.session is None:
            self.session = aiohttp.ClientSession()
        return self.session
    
    async def extract_content(self, url: str) -> Dict:
        """提取网页内容"""
        session = await self._get_session()
        
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                if response.status != 200:
                    return {'error': f'HTTP {response.status}'}
                
                html = await response.text()
                
                # 尝试多种提取方法
                content = self._extract_with_trafilatura(html)
                if not content or len(content) < 100:
                    content = self._extract_with_readability(html)
                if not content or len(content) < 100:
                    content = self._extract_with_beautifulsoup(html)
                
                # 提取元数据
                metadata = self._extract_metadata(html, url)
                
                return {
                    'content': content,
                    'metadata': metadata,
                    'url': url,
                    'success': True
                }
                
        except Exception as e:
            return {
                'error': str(e),
                'url': url,
                'success': False
            }
    
    def _extract_with_trafilatura(self, html: str) -> str:
        """使用 trafilatura 提取内容"""
        try:
            content = trafilatura.extract(html, include_comments=False, include_formatting=False)
            return content or ""
        except Exception:
            return ""
    
    def _extract_with_readability(self, html: str) -> str:
        """使用 readability 提取内容"""
        try:
            doc = Document(html)
            content = doc.summary()
            soup = BeautifulSoup(content, 'html.parser')
            return soup.get_text(strip=True)
        except Exception:
            return ""
    
    def _extract_with_beautifulsoup(self, html: str) -> str:
        """使用 BeautifulSoup 提取内容"""
        try:
            soup = BeautifulSoup(html, 'html.parser')
            
            # 移除不需要的标签
            for script in soup(["script", "style", "nav", "footer", "header"]):
                script.decompose()
            
            # 提取主要内容
            text = soup.get_text(separator=' ', strip=True)
            return text
        except Exception:
            return ""
    
    def _extract_metadata(self, html: str, url: str) -> Dict:
        """提取网页元数据"""
        soup = BeautifulSoup(html, 'html.parser')
        
        metadata = {'url': url}
        
        # 提取标题
        title_tag = soup.find('title')
        if title_tag:
            metadata['title'] = title_tag.get_text(strip=True)
        
        # 提取描述
        description = soup.find('meta', attrs={'name': 'description'})
        if description:
            metadata['description'] = description.get('content', '')
        
        # 提取作者
        author = soup.find('meta', attrs={'name': 'author'})
        if author:
            metadata['author'] = author.get('content', '')
        
        return metadata
    
    async def close(self):
        """关闭会话"""
        if self.session:
            await self.session.close()
```

##### Day 5: 搜索缓存管理

**文件**: `src/web_search/search_cache.py`

```python
import json
import hashlib
import time
from pathlib import Path
from typing import Optional, Dict, List
from datetime import datetime, timedelta

class SearchCache:
    """搜索缓存管理"""
    
    def __init__(self, cache_dir: Path, ttl_days: int = 7):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.ttl = timedelta(days=ttl_days)
    
    def _get_cache_key(self, query: str, source: str) -> str:
        """生成缓存键"""
        key_string = f"{source}:{query}"
        return hashlib.md5(key_string.encode()).hexdigest()
    
    def _get_cache_file(self, cache_key: str) -> Path:
        """获取缓存文件路径"""
        return self.cache_dir / f"{cache_key}.json"
    
    def get(self, query: str, source: str) -> Optional[Dict]:
        """获取缓存结果"""
        cache_key = self._get_cache_key(query, source)
        cache_file = self._get_cache_file(cache_key)
        
        if not cache_file.exists():
            return None
        
        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                cache_data = json.load(f)
            
            # 检查是否过期
            cache_time = datetime.fromisoformat(cache_data['timestamp'])
            if datetime.now() - cache_time > self.ttl:
                cache_file.unlink()  # 删除过期缓存
                return None
            
            return cache_data
            
        except Exception as e:
            print(f"缓存读取失败: {e}")
            return None
    
    def set(self, query: str, source: str, results: List[Dict]):
        """设置缓存结果"""
        cache_key = self._get_cache_key(query, source)
        cache_file = self._get_cache_file(cache_key)
        
        cache_data = {
            'query': query,
            'source': source,
            'timestamp': datetime.now().isoformat(),
            'results': results
        }
        
        try:
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"缓存写入失败: {e}")
    
    def clear(self):
        """清空所有缓存"""
        for cache_file in self.cache_dir.glob("*.json"):
            try:
                cache_file.unlink()
            except Exception as e:
                print(f"删除缓存文件失败: {e}")
    
    def clear_expired(self):
        """清空过期缓存"""
        now = datetime.now()
        for cache_file in self.cache_dir.glob("*.json"):
            try:
                with open(cache_file, 'r', encoding='utf-8') as f:
                    cache_data = json.load(f)
                
                cache_time = datetime.fromisoformat(cache_data['timestamp'])
                if now - cache_time > self.ttl:
                    cache_file.unlink()
            except Exception:
                continue
    
    def get_stats(self) -> Dict:
        """获取缓存统计信息"""
        cache_files = list(self.cache_dir.glob("*.json"))
        
        total_size = sum(f.stat().st_size for f in cache_files)
        expired_count = 0
        
        for cache_file in cache_files:
            try:
                with open(cache_file, 'r', encoding='utf-8') as f:
                    cache_data = json.load(f)
                cache_time = datetime.fromisoformat(cache_data['timestamp'])
                if datetime.now() - cache_time > self.ttl:
                    expired_count += 1
            except Exception:
                continue
        
        return {
            'total_files': len(cache_files),
            'total_size_bytes': total_size,
            'total_size_mb': total_size / (1024 * 1024),
            'expired_files': expired_count,
            'active_files': len(cache_files) - expired_count
        }
```

##### Day 6-7: 集成到 Agent 工具链

**文件**: `src/web_search/__init__.py`

```python
from .search_engine import (
    SearchEngine, 
    DuckDuckGoSearchEngine, 
    GitHubSearchEngine, 
    ArXivSearchEngine,
    CompositeSearchEngine,
    SearchResult
)
from .content_extractor import WebContentExtractor
from .search_cache import SearchCache

__all__ = [
    'SearchEngine',
    'DuckDuckGoSearchEngine', 
    'GitHubSearchEngine',
    'ArXivSearchEngine',
    'CompositeSearchEngine',
    'SearchResult',
    'WebContentExtractor',
    'SearchCache'
]
```

**更新**: `src/agent_tools.py`

```python
# 在文件开头添加导入
import asyncio
from web_search import CompositeSearchEngine, WebContentExtractor, SearchCache
from config import INDEX_DIR

# 初始化搜索组件
_search_engine = None
_content_extractor = None
_search_cache = None

def init_web_search():
    """初始化网络搜索组件"""
    global _search_engine, _content_extractor, _search_cache
    
    if _search_engine is None:
        _search_engine = CompositeSearchEngine()
        _content_extractor = WebContentExtractor()
        _search_cache = SearchCache(INDEX_DIR / "search_cache")
    
    return _search_engine, _content_extractor, _search_cache

async def web_search(query: str, source: str = "all", max_results: int = 5) -> str:
    """网络搜索工具"""
    try:
        engine, extractor, cache = init_web_search()
        
        # 检查缓存
        cached = cache.get(query, source)
        if cached:
            return f"[缓存结果] 找到 {len(cached['results'])} 条缓存结果"
        
        # 执行搜索
        if source == "all":
            results = await engine.search_unified(query, max_results)
        elif source == "duckduckgo":
            results = await engine.engines[0].search(query, max_results)
        elif source == "github":
            results = await engine.engines[1].search(query, max_results)
        elif source == "arxiv":
            results = await engine.engines[2].search(query, max_results)
        else:
            return f"[错误] 不支持的搜索源: {source}"
        
        # 缓存结果
        cache.set(query, source, [r.__dict__ for r in results])
        
        # 格式化结果
        output = f"搜索 '{query}' 找到 {len(results)} 条结果:\n\n"
        for i, result in enumerate(results, 1):
            output += f"{i}. {result.title}\n"
            output += f"   URL: {result.url}\n"
            output += f"   来源: {result.source}\n"
            output += f"   摘要: {result.snippet[:200]}...\n\n"
        
        return output
        
    except Exception as e:
        return f"[错误] 网络搜索失败: {str(e)}"

async def web_content_extract(url: str) -> str:
    """提取网页内容"""
    try:
        engine, extractor, cache = init_web_search()
        
        result = await extractor.extract_content(url)
        
        if result['success']:
            metadata = result['metadata']
            output = f"网页内容提取成功:\n"
            output += f"标题: {metadata.get('title', 'N/A')}\n"
            output += f"URL: {url}\n"
            output += f"作者: {metadata.get('author', 'N/A')}\n\n"
            output += f"内容:\n{result['content'][:2000]}..."
            
            return output
        else:
            return f"[错误] 内容提取失败: {result['error']}"
            
    except Exception as e:
        return f"[错误] 网页内容提取失败: {str(e)}"

def web_cache_status() -> str:
    """搜索缓存状态"""
    try:
        engine, extractor, cache = init_web_search()
        stats = cache.get_stats()
        
        output = "搜索缓存状态:\n"
        output += f"总文件数: {stats['total_files']}\n"
        output += f"总大小: {stats['total_size_mb']:.2f} MB\n"
        output += f"有效文件: {stats['active_files']}\n"
        output += f"过期文件: {stats['expired_files']}\n"
        
        return output
        
    except Exception as e:
        return f"[错误] 获取缓存状态失败: {str(e)}"

def web_cache_clear() -> str:
    """清空搜索缓存"""
    try:
        engine, extractor, cache = init_web_search()
        cache.clear()
        return "[成功] 搜索缓存已清空"
        
    except Exception as e:
        return f"[错误] 清空缓存失败: {str(e)}"

# 注册工具
registry.register("web_search", web_search, 
                  "网络搜索（支持 DuckDuckGo、GitHub、arXiv）",
                  {"query": "搜索查询(必填)", "source": "搜索源(all/duckduckgo/github/arxiv)", "max_results": "最大结果数"}, 
                  safe=True)

registry.register("web_content_extract", web_content_extract,
                  "提取网页内容并清理格式",
                  {"url": "网页 URL(必填)"}, 
                  safe=True)

registry.register("web_cache_status", web_cache_status,
                  "查看搜索缓存状态",
                  {}, 
                  safe=True)

registry.register("web_cache_clear", web_cache_clear,
                  "清空搜索缓存",
                  {}, 
                  safe=True)
```

##### Day 8-10: CLI 集成和测试

**更新**: `src/query_interface.py`

```python
# 在命令解析部分添加
if cmd == "/web-search":
    return ParsedCommand("web_search", user_input, arg)
if cmd == "/web-cache":
    if arg == "status":
        return ParsedCommand("web_cache_status", user_input, "")
    elif arg == "clear":
        return ParsedCommand("web_cache_clear", user_input, "")
    else:
        return ParsedCommand("web_cache_status", user_input, arg)

# 在命令处理部分添加
elif parsed.cmd_type == "web_search":
    query = parsed.arg
    if not query:
        console.print("❌ 请指定搜索查询: /web-search <query>", style="yellow")
        continue
    
    try:
        import asyncio
        from agent_tools import web_search
        
        # 异步执行搜索
        result = asyncio.run(web_search(query, source="all", max_results=5))
        console.print(result)
        
    except Exception as e:
        console.print(f"❌ 网络搜索失败: {e}", style="red")

elif parsed.cmd_type == "web_cache_status":
    try:
        from agent_tools import web_cache_status
        result = web_cache_status()
        console.print(result)
    except Exception as e:
        console.print(f"❌ 获取缓存状态失败: {e}", style="red")

elif parsed.cmd_type == "web_cache_clear":
    try:
        from agent_tools import web_cache_clear
        result = web_cache_clear()
        console.print(result)
    except Exception as e:
        console.print(f"❌ 清空缓存失败: {e}", style="red")
```

##### Day 11-15: 测试和优化

**文件**: `tests/test_web_search.py`

```python
import pytest
import asyncio
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from web_search import CompositeSearchEngine, WebContentExtractor, SearchCache
from config import INDEX_DIR

class TestWebSearch:
    """网络搜索测试"""
    
    @pytest.fixture
    def search_engine(self):
        return CompositeSearchEngine()
    
    @pytest.fixture
    def content_extractor(self):
        return WebContentExtractor()
    
    @pytest.fixture
    def search_cache(self):
        cache_dir = INDEX_DIR / "test_search_cache"
        return SearchCache(cache_dir, ttl_days=0)  # 测试时立即过期
    
    @pytest.mark.asyncio
    async def test_duckduckgo_search(self, search_engine):
        """测试 DuckDuckGo 搜索"""
        results = await search_engine.engines[0].search("Python programming", max_results=3)
        
        assert len(results) > 0
        assert all(result.title for result in results)
        assert all(result.url for result in results)
        assert all(result.source == 'duckduckgo' for result in results)
    
    @pytest.mark.asyncio
    async def test_github_search(self, search_engine):
        """测试 GitHub 搜索"""
        results = await search_engine.engines[1].search("machine learning", max_results=3)
        
        # GitHub 搜索可能需要 API token，所以可能失败
        assert isinstance(results, list)
    
    @pytest.mark.asyncio
    async def test_arxiv_search(self, search_engine):
        """测试 arXiv 搜索"""
        results = await search_engine.engines[2].search("neural networks", max_results=3)
        
        assert len(results) > 0
        assert all(result.title for result in results)
        assert all(result.source == 'arxiv' for result in results)
        assert all('authors' in result.metadata for result in results)
    
    @pytest.mark.asyncio
    async def test_unified_search(self, search_engine):
        """测试统一搜索"""
        results = await search_engine.search_unified("artificial intelligence", max_results=5)
        
        assert len(results) > 0
        assert len(results) <= 5
        # 检查结果按相关性排序
        relevance_scores = [r.relevance_score for r in results]
        assert relevance_scores == sorted(relevance_scores, reverse=True)
    
    @pytest.mark.asyncio
    async def test_content_extraction(self, content_extractor):
        """测试内容提取"""
        # 使用一个简单的网页进行测试
        test_url = "https://example.com"
        result = await content_extractor.extract_content(test_url)
        
        assert result is not None
        assert 'url' in result
        assert result['url'] == test_url
    
    def test_cache_operations(self, search_cache):
        """测试缓存操作"""
        test_query = "test query"
        test_source = "test_source"
        test_results = [
            {"title": "Test Result", "url": "http://test.com", "snippet": "Test snippet"}
        ]
        
        # 测试设置缓存
        search_cache.set(test_query, test_source, test_results)
        
        # 测试获取缓存
        cached = search_cache.get(test_query, test_source)
        assert cached is not None
        assert cached['query'] == test_query
        assert len(cached['results']) == 1
        
        # 测试缓存统计
        stats = search_cache.get_stats()
        assert stats['total_files'] > 0
        
        # 测试清空缓存
        search_cache.clear()
        cached_after_clear = search_cache.get(test_query, test_source)
        assert cached_after_clear is None

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
```

**性能优化**:
- 实现搜索结果去重
- 添加搜索速率限制
- 优化内容提取速度
- 实现异步批量处理

---

## 🔧 阶段二：代码能力增强（Week 4-6）

### F5.1: AST 语法树搜索

#### 实施步骤

##### Day 16-18: AST 分析器实现

**文件**: `src/code_analyzer/ast_analyzer.py`

```python
import ast
import os
from typing import List, Dict, Optional, Set
from pathlib import Path
from dataclasses import dataclass
import hashlib

@dataclass
class ASTNodeInfo:
    """AST 节点信息"""
    node_type: str
    name: str
    file_path: str
    line_number: int
    end_line_number: int
    docstring: Optional[str]
    parent: Optional[str]
    children: List[str]
    metadata: Dict

class ASTAnalyzer:
    """AST 语法树分析器"""
    
    def __init__(self):
        self.cache = {}
    
    def analyze_file(self, file_path: str) -> List[ASTNodeInfo]:
        """分析单个 Python 文件"""
        if not os.path.exists(file_path):
            return []
        
        # 检查缓存
        file_hash = self._get_file_hash(file_path)
        if file_hash in self.cache:
            return self.cache[file_hash]
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                source = f.read()
            
            tree = ast.parse(source)
            nodes = []
            
            # 分析函数
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    nodes.append(self._extract_function_info(node, file_path))
                elif isinstance(node, ast.ClassDef):
                    nodes.append(self._extract_class_info(node, file_path))
            
            self.cache[file_hash] = nodes
            return nodes
            
        except SyntaxError:
            return []
        except Exception as e:
            print(f"AST 分析失败 {file_path}: {e}")
            return []
    
    def _extract_function_info(self, node: ast.FunctionDef, file_path: str) -> ASTNodeInfo:
        """提取函数信息"""
        return ASTNodeInfo(
            node_type='function',
            name=node.name,
            file_path=file_path,
            line_number=node.lineno,
            end_line_number=node.end_lineno if hasattr(node, 'end_lineno') else node.lineno,
            docstring=ast.get_docstring(node),
            parent=self._get_parent_name(node),
            children=self._get_child_names(node),
            metadata={
                'args': [arg.arg for arg in node.args.args],
                'returns': ast.unparse(node.returns) if node.returns else None,
                'decorators': [ast.unparse(dec) for dec in node.decorator_list],
                'is_async': isinstance(node, ast.AsyncFunctionDef)
            }
        )
    
    def _extract_class_info(self, node: ast.ClassDef, file_path: str) -> ASTNodeInfo:
        """提取类信息"""
        return ASTNodeInfo(
            node_type='class',
            name=node.name,
            file_path=file_path,
            line_number=node.lineno,
            end_line_number=node.end_lineno if hasattr(node, 'end_lineno') else node.lineno,
            docstring=ast.get_docstring(node),
            parent=self._get_parent_name(node),
            children=self._get_child_names(node),
            metadata={
                'bases': [ast.unparse(base) for base in node.bases],
                'decorators': [ast.unparse(dec) for dec in node.decorator_list],
                'methods': [n.name for n in node.body if isinstance(n, ast.FunctionDef)]
            }
        )
    
    def _get_parent_name(self, node) -> Optional[str]:
        """获取父节点名称"""
        # 简化实现，实际需要遍历父节点
        return None
    
    def _get_child_names(self, node) -> List[str]:
        """获取子节点名称"""
        names = []
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.ClassDef)):
                names.append(child.name)
        return names
    
    def _get_file_hash(self, file_path: str) -> str:
        """获取文件哈希"""
        with open(file_path, 'rb') as f:
            return hashlib.md5(f.read()).hexdigest()
    
    def search_by_pattern(self, root_dir: str, pattern: str, node_type: Optional[str] = None) -> List[ASTNodeInfo]:
        """按模式搜索 AST 节点"""
        results = []
        
        for file_path in self._get_python_files(root_dir):
            nodes = self.analyze_file(file_path)
            
            for node in nodes:
                # 检查节点类型
                if node_type and node.node_type != node_type:
                    continue
                
                # 检查名称模式
                if pattern.lower() in node.name.lower():
                    results.append(node)
                
                # 检查文档字符串
                if node.docstring and pattern.lower() in node.docstring.lower():
                    results.append(node)
        
        return results
    
    def _get_python_files(self, root_dir: str) -> List[str]:
        """获取目录下所有 Python 文件"""
        python_files = []
        
        for root, dirs, files in os.walk(root_dir):
            # 跳过常见目录
            dirs[:] = [d for d in dirs if d not in {'.git', '__pycache__', 'node_modules', 'venv'}]
            
            for file in files:
                if file.endswith('.py'):
                    python_files.append(os.path.join(root, file))
        
        return python_files
    
    def get_import_dependencies(self, file_path: str) -> Dict[str, List[str]]:
        """获取文件的导入依赖"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                source = f.read()
            
            tree = ast.parse(source)
            dependencies = {'local': [], 'external': []}
            
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        dependencies['external'].append(alias.name)
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        dependencies['external'].append(node.module)
                        for alias in node.names:
                            dependencies['external'].append(f"{node.module}.{alias.name}")
            
            return dependencies
            
        except Exception:
            return {'local': [], 'external': []}
```

##### Day 19-20: 集成到工具链

**更新**: `src/agent_tools.py`

```python
from code_analyzer.ast_analyzer import ASTAnalyzer

_ast_analyzer = None

def init_ast_analyzer():
    """初始化 AST 分析器"""
    global _ast_analyzer
    if _ast_analyzer is None:
        _ast_analyzer = ASTAnalyzer()
    return _ast_analyzer

def ast_search(pattern: str, path: str = ".", node_type: str = None) -> str:
    """AST 语法树搜索"""
    try:
        analyzer = init_ast_analyzer()
        
        if node_type:
            node_type = node_type.lower()
        
        results = analyzer.search_by_pattern(path, pattern, node_type)
        
        if not results:
            return f"[结果] 未找到匹配 '{pattern}' 的 {node_type or '节点'}"
        
        output = f"找到 {len(results)} 个匹配结果:\n\n"
        for i, node in enumerate(results, 1):
            output += f"{i}. {node.node_type.upper()}: {node.name}\n"
            output += f"   文件: {node.file_path}\n"
            output += f"   位置: 第 {node.line_number}-{node.end_line_number} 行\n"
            if node.docstring:
                output += f"   文档: {node.docstring[:100]}...\n"
            if node.metadata:
                if node.metadata.get('args'):
                    output += f"   参数: {', '.join(node.metadata['args'])}\n"
                if node.metadata.get('bases'):
                    output += f"   基类: {', '.join(node.metadata['bases'])}\n"
            output += "\n"
        
        return output
        
    except Exception as e:
        return f"[错误] AST 搜索失败: {str(e)}"

registry.register("ast_search", ast_search,
                  "AST 语法树搜索（函数、类、变量）",
                  {"pattern": "搜索模式(必填)", "path": "搜索路径，默认当前目录", "node_type": "节点类型(function/class)"}, 
                  safe=True)
```

### F5.2: 代码语义搜索

#### 实施步骤

##### Day 21-23: 代码语义编码

**文件**: `src/code_analyzer/semantic_search.py`

```python
import os
import ast
import hashlib
from typing import List, Dict, Optional
from pathlib import Path
import numpy as np
from sentence_transformers import SentenceTransformer
import faiss
import pickle

class CodeSemanticSearch:
    """代码语义搜索"""
    
    def __init__(self, model_name: str = "microsoft/codebert-base"):
        self.model = SentenceTransformer(model_name)
        self.index = None
        self.code_blocks = []
        self.embeddings = None
    
    def index_codebase(self, root_dir: str) -> None:
        """为代码库建立索引"""
        self.code_blocks = []
        embeddings_list = []
        
        for file_path in self._get_code_files(root_dir):
            file_blocks = self._extract_code_blocks(file_path)
            self.code_blocks.extend(file_blocks)
            
            # 生成嵌入
            for block in file_blocks:
                # 组合代码和文档字符串
                text_to_encode = f"{block['name']}\n{block['docstring'] or ''}\n{block['code']}"
                embedding = self.model.encode([text_to_encode])[0]
                embeddings_list.append(embedding)
        
        # 构建 FAISS 索引
        if embeddings_list:
            self.embeddings = np.array(embeddings_list).astype('float32')
            self.index = faiss.IndexFlatIP(self.embeddings.shape[1])
            faiss.normalize_L2(self.embeddings)
            self.index.add(self.embeddings)
    
    def _extract_code_blocks(self, file_path: str) -> List[Dict]:
        """提取代码块"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                source = f.read()
            
            tree = ast.parse(source)
            blocks = []
            
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    blocks.append({
                        'type': 'function',
                        'name': node.name,
                        'file': file_path,
                        'line': node.lineno,
                        'docstring': ast.get_docstring(node),
                        'code': ast.unparse(node),
                        'metadata': {
                            'args': [arg.arg for arg in node.args.args],
                            'returns': ast.unparse(node.returns) if node.returns else None
                        }
                    })
                elif isinstance(node, ast.ClassDef):
                    blocks.append({
                        'type': 'class',
                        'name': node.name,
                        'file': file_path,
                        'line': node.lineno,
                        'docstring': ast.get_docstring(node),
                        'code': ast.unparse(node),
                        'metadata': {
                            'bases': [ast.unparse(base) for base in node.bases],
                            'methods': [n.name for n in node.body if isinstance(n, ast.FunctionDef)]
                        }
                    })
            
            return blocks
            
        except Exception:
            return []
    
    def _get_code_files(self, root_dir: str) -> List[str]:
        """获取代码文件"""
        code_files = []
        extensions = {'.py', '.js', '.ts', '.java', '.cpp', '.c'}
        
        for root, dirs, files in os.walk(root_dir):
            dirs[:] = [d for d in dirs if d not in {'.git', '__pycache__', 'node_modules'}]
            
            for file in files:
                if Path(file).suffix in extensions:
                    code_files.append(os.path.join(root, file))
        
        return code_files
    
    def search(self, query: str, top_k: int = 5) -> List[Dict]:
        """语义搜索"""
        if self.index is None:
            return []
        
        # 编码查询
        query_embedding = self.model.encode([query])[0].astype('float32')
        query_embedding = query_embedding.reshape(1, -1)
        faiss.normalize_L2(query_embedding)
        
        # 搜索
        scores, indices = self.index.search(query_embedding, top_k)
        
        results = []
        for score, idx in zip(scores[0], indices[0]):
            if idx < len(self.code_blocks):
                result = self.code_blocks[idx].copy()
                result['score'] = float(score)
                results.append(result)
        
        return results
    
    def save_index(self, save_path: str) -> None:
        """保存索引"""
        index_data = {
            'code_blocks': self.code_blocks,
            'embeddings': self.embeddings,
            'index': self.index
        }
        
        with open(save_path, 'wb') as f:
            pickle.dump(index_data, f)
    
    def load_index(self, load_path: str) -> None:
        """加载索引"""
        with open(load_path, 'rb') as f:
            index_data = pickle.load(f)
        
        self.code_blocks = index_data['code_blocks']
        self.embeddings = index_data['embeddings']
        self.index = index_data['index']
```

##### Day 24-25: 集成和测试

**更新**: `src/agent_tools.py`

```python
from code_analyzer.semantic_search import CodeSemanticSearch

_semantic_search = None

def init_semantic_search():
    """初始化语义搜索"""
    global _semantic_search
    if _semantic_search is None:
        _semantic_search = CodeSemanticSearch()
    return _semantic_search

def code_semantic_search(query: str, path: str = ".", top_k: int = 5) -> str:
    """代码语义搜索"""
    try:
        searcher = init_semantic_search()
        
        # 检查是否已有索引
        if searcher.index is None:
            return "[信息] 正在建立代码索引，请稍候..."
        
        results = searcher.search(query, top_k)
        
        if not results:
            return f"[结果] 未找到与 '{query}' 相似的代码"
        
        output = f"找到 {len(results)} 个相似代码块:\n\n"
        for i, result in enumerate(results, 1):
            output += f"{i}. {result['type'].upper()}: {result['name']} (相似度: {result['score']:.3f})\n"
            output += f"   文件: {result['file']}\n"
            output += f"   位置: 第 {result['line']} 行\n"
            if result['docstring']:
                output += f"   文档: {result['docstring'][:100]}...\n"
            output += f"   代码: {result['code'][:150]}...\n\n"
        
        return output
        
    except Exception as e:
        return f"[错误] 语义搜索失败: {str(e)}"

registry.register("code_semantic_search", code_semantic_search,
                  "代码语义搜索（基于功能描述）",
                  {"query": "搜索查询(必填)", "path": "搜索路径，默认当前目录", "top_k": "返回结果数"}, 
                  safe=True)
```

---

## 🗄️ 阶段三：数据库和存储设计

### 存储架构

#### 1. 搜索缓存存储
```python
# 使用 JSON 文件存储，按哈希组织
index_storage/
├── search_cache/
│   ├── {md5_hash}.json
│   └── cache_stats.json
```

#### 2. 代码索引存储
```python
# 使用 FAISS 向量索引 + 元数据
index_storage/
├── code_index/
│   ├── faiss_index.bin
│   ├── metadata.json
│   └── code_blocks.pkl
```

#### 3. 知识图谱存储
```python
# 使用 NetworkX + 序列化
index_storage/
├── knowledge_graph/
│   ├── graph.pkl
│   ├── entities.json
│   └── relations.json
```

#### 4. Git 分析缓存
```python
index_storage/
├── git_cache/
│   ├── {repo_hash}/
│   │   ├── commits.json
│   │   ├── branches.json
│   │   └── analysis.json
```

---

## 🧪 测试策略

### 单元测试
- 每个模块独立测试
- 覆盖率目标 >80%
- 使用 pytest 框架

### 集成测试
- 测试模块间集成
- 测试与现有系统集成
- 测试端到端流程

### 性能测试
- 搜索响应时间 <2 秒
- 索引建立时间可接受
- 内存占用监控

### 安全测试
- 网络请求安全检查
- 输入验证和清理
- 缓存投毒防护

---

## 📅 详细时间表

### Week 1-3: 网络搜索核心功能
- Day 1-2: 基础搜索引擎
- Day 3-4: 内容提取和清理
- Day 5: 搜索缓存管理
- Day 6-7: Agent 工具链集成
- Day 8-10: CLI 集成
- Day 11-15: 测试和优化

### Week 4-6: 代码能力增强
- Day 16-18: AST 分析器
- Day 19-20: AST 工具集成
- Day 21-23: 代码语义搜索
- Day 24-25: 语义搜索集成
- Day 26-27: 代码质量检查
- Day 28-30: Git 集成

### Week 7-9: 知识能力增强
- Day 31-35: 知识图谱构建
- Day 36-38: 知识点关联网络
- Day 39-40: 可视化功能

### Week 10-12: 数据处理和优化
- Day 41-43: 数据库工具
- Day 44-46: 时间序列分析
- Day 47-48: 性能优化
- Day 49-50: 文档和部署

---

## 🎯 成功指标

### 功能指标
- 网络搜索成功率 >95%
- 代码搜索准确率 >90%
- 索引覆盖率 >80%
- 集成测试通过率 100%

### 性能指标
- 搜索响应时间 <2 秒
- 索引建立时间 <5 分钟（中等项目）
- 内存占用增加 <200MB
- 启动时间影响 <3 秒

### 用户体验指标
- 功能使用率 >60%
- 用户满意度 >4.0/5.0
- 任务完成效率提升 >30%

---

**文档版本**: 1.0
**最后更新**: 2026-06-15
**维护者**: AI Development Team
**状态**: 待审核和确认