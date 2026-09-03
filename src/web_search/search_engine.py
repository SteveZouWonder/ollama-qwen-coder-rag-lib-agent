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


def _contains_cjk(text: str) -> bool:
    """判断文本是否包含中日韩（主要是中文）字符。"""
    if not text:
        return False
    for ch in text:
        if "\u4e00" <= ch <= "\u9fff":  # CJK 统一表意文字（中文常用区）
            return True
    return False


def _tokenize(text: str) -> list:
    """轻量分词：中文按单字，英文/数字按单词。用于中文友好的相关性打分。

    英文子串 ``.count()`` 对中文无效（中文不以空格分词）。这里对中文逐字、
    对拉丁串按 \\w+ 切词，得到可比较的 token 集合。
    """
    import re
    if not text:
        return []
    tokens = []
    # 先抽出连续的拉丁字母/数字作为词
    for m in re.finditer(r"[a-zA-Z0-9]+", text.lower()):
        tokens.append(m.group())
    # 再把中文逐字加入
    for ch in text:
        if "\u4e00" <= ch <= "\u9fff":
            tokens.append(ch)
    return tokens


def _get_search_config():
    """读取网络搜索配置，配置不可用时回退到安全默认值。"""
    try:
        from config import (
            WEB_SEARCH_REGION, WEB_SEARCH_BACKEND, WEB_SEARCH_SAFESEARCH,
            WEB_SEARCH_TIMELIMIT,
        )
        return {
            "region": WEB_SEARCH_REGION,
            "backend": WEB_SEARCH_BACKEND,
            "safesearch": WEB_SEARCH_SAFESEARCH,
            "timelimit": WEB_SEARCH_TIMELIMIT,
        }
    except Exception:  # noqa: BLE001
        return {
            "region": "auto",
            "backend": "brave, duckduckgo, google",
            "safesearch": "moderate",
            "timelimit": None,
        }


# 强烈指向"国内信息"的语境词：出现即用中国区搜索（能召回淘宝/京东/国行价格）。
_CN_CONTEXT_HINTS = (
    "国内", "中国", "国行", "大陆", "内地", "行货",
    "淘宝", "京东", "天猫", "拼多多", "苏宁", "抖音", "闲鱼",
    "售价", "价格", "多少钱", "报价", "优惠", "促销", "补贴", "包邮",
    "人民币", "元起", "元",
)
# 强烈指向"全球/海外"的语境词：出现即用全球区搜索。
_GLOBAL_CONTEXT_HINTS = (
    "global", "worldwide", "usa", "us price", "united states", "美国", "海外",
    "全球", "国际", "europe", "uk price",
)


def resolve_region(query: str, configured: str) -> str:
    """根据配置与查询语境解析最终搜索区域。

    - 若 configured 为具体 region（非 auto/空）→ 直接沿用（用户强制固定）。
    - 否则 auto：显式语境词优先（国内词 → cn-zh；全球词 → wt-wt）；
      再按语言（含中文 → cn-zh；纯英文 → wt-wt）。

    这样"中国国内 dji OSMO360 的最新售价"会用 cn-zh，从而召回京东/淘宝等国内
    电商与国行价格；而 "DJI Osmo 360 global price" 会用 wt-wt。
    """
    cfg = (configured or "").strip().lower()
    if cfg and cfg != "auto":
        return configured  # 用户显式固定区域

    q = (query or "")
    q_lower = q.lower()

    # 全球语境词优先级低于国内词（价格类问题多为国内诉求），但显式全球词仍生效
    has_cn = any(h in q for h in _CN_CONTEXT_HINTS)
    has_global = any(h in q_lower for h in _GLOBAL_CONTEXT_HINTS)

    if has_cn and not has_global:
        return "cn-zh"
    if has_global and not has_cn:
        return "wt-wt"
    # 二者都无/都有：按语言判断
    if _contains_cjk(q):
        return "cn-zh"
    return "wt-wt"


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
            # 优先使用新的 ddgs 包，如果不可用则回退到 duckduckgo_search
            try:
                from ddgs import DDGS
            except ImportError:
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
            cfg = _get_search_config()
            # 关键改进：按查询语境自动解析 region（国内查询→cn-zh，可召回淘宝/
            # 京东/国行价格；英文/全球→wt-wt），并传入 backend/safesearch/timelimit。
            region = resolve_region(query, cfg["region"])
            kwargs = {
                "max_results": max_results,
                "region": region,
                "safesearch": cfg["safesearch"],
                "backend": cfg["backend"],
            }
            if cfg.get("timelimit"):
                kwargs["timelimit"] = cfg["timelimit"]
            self.logger.info(
                f"开始 DuckDuckGo 搜索: query='{query}', max_results={max_results}, "
                f"region={region}, backend={cfg['backend']}"
            )

            def _do_search():
                try:
                    return list(self._ddgs.text(query, **kwargs))
                except TypeError:
                    # 兼容旧版 ddgs/duckduckgo_search（不支持 backend 等参数）：
                    # 逐步降级，尽量保留 region。
                    try:
                        return list(self._ddgs.text(
                            query, max_results=max_results,
                            region=region, safesearch=cfg["safesearch"],
                        ))
                    except TypeError:
                        return list(self._ddgs.text(query, max_results=max_results))
                except Exception:
                    # 多后端整体失败（如某后端 ConnectError 导致 ddgs 抛异常）时，
                    # 逐个后端降级重试：只要有一个后端可用就返回其结果。国内网络
                    # 下 duckduckgo/google 常被重置，而 bing/brave 往往可用。
                    backends = [b.strip() for b in str(cfg["backend"]).split(",") if b.strip()]
                    if len(backends) <= 1:
                        raise
                    for be in backends:
                        try:
                            single = dict(kwargs)
                            single["backend"] = be
                            r = list(self._ddgs.text(query, **single))
                            if r:
                                self.logger.info(f"后端 '{be}' 单独成功，结果数={len(r)}")
                                return r
                        except Exception as be_err:  # noqa: BLE001
                            self.logger.warning(f"后端 '{be}' 失败: {be_err}")
                            continue
                    raise

            ddgs_results = await loop.run_in_executor(None, _do_search)

            self.logger.info(f"DuckDuckGo 原始结果数: {len(ddgs_results)}")
            
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
            self.logger.error(f"DuckDuckGo 搜索失败: {e}", exc_info=True)
            return []
        
        return results
    
    def _calculate_relevance(self, result: Dict, query: str) -> float:
        """计算相关性得分（中文友好）。

        此前用英文子串 ``.count()`` + 文本长度权重，对中文几乎无效（中文不以
        空格分词、子串匹配也不合理），且长度占比过高会让"长而不相关"的结果
        排到前面。现改为基于查询 token（中文逐字、英文按词）与标题/正文的
        覆盖率打分，长度仅作很小的加成。
        """
        try:
            title = result.get('title', '')
            body = result.get('body', '')

            query_tokens = set(_tokenize(query))
            if not query_tokens:
                return 0.5

            title_tokens = set(_tokenize(title))
            body_tokens = set(_tokenize(body))

            # 覆盖率：查询 token 在标题/正文中被命中的比例
            title_cov = len(query_tokens & title_tokens) / len(query_tokens)
            body_cov = len(query_tokens & body_tokens) / len(query_tokens)

            # 长度只作微弱加成，避免主导排序
            length_bonus = min(1.0, (len(title) + len(body)) / 800.0) * 0.1

            # 标题命中权重高于正文
            total_score = title_cov * 0.55 + body_cov * 0.35 + length_bonus
            return max(0.0, min(1.0, total_score))
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


class BaiduSearchEngine(SearchEngine):
    """百度网页搜索引擎实现 —— 面向中国国内信息的主力源。

    移植自 SearXNG 的 baidu 引擎逻辑：调用百度网页搜索的 ``tn=json`` 结构化
    接口（``https://www.baidu.com/s?wd=...&tn=json``），解析返回 JSON 中的
    ``feed.entry`` 列表。相比 DuckDuckGo/Brave 等海外引擎，百度对中文与国内
    站点（京东/淘宝/知乎/中关村/学术等）召回显著更好；相比解析 HTML 的爬虫，
    JSON 接口更稳定、返回的是真实 URL（非百度跳转链）。

    纯 requests 实现，无浏览器/Chromium 依赖，可随 App 打包、开箱即用。
    """

    _ENDPOINT = "https://www.baidu.com/s"
    _UA = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
    # 时间范围（秒），对应 ddgs/searxng 的 day/week/month/year
    _TIME_RANGE = {"d": 86400, "w": 604800, "m": 2592000, "y": 31536000}

    def __init__(self):
        super().__init__()

    async def search(self, query: str, max_results: int = 10) -> List[SearchResult]:
        if not query or not query.strip():
            return []

        import asyncio
        from urllib.parse import urlencode

        loop = asyncio.get_event_loop()
        cfg = _get_search_config()
        params = {
            "wd": query,
            "rn": max_results,
            "pn": 0,
            "tn": "json",
        }
        # 时间范围（若配置）
        tl = cfg.get("timelimit")
        if tl in self._TIME_RANGE:
            import time as _t
            now = int(_t.time())
            past = now - self._TIME_RANGE[tl]
            params["gpc"] = f"stf={past},{now}|stftype=1"

        url = f"{self._ENDPOINT}?{urlencode(params)}"

        def _do():
            import requests
            return requests.get(
                url, headers={"User-Agent": self._UA}, timeout=12, allow_redirects=False
            )

        try:
            self.logger.info(f"开始百度搜索: query='{query}', max_results={max_results}")
            resp = await loop.run_in_executor(None, _do)
        except Exception as e:  # noqa: BLE001
            self.logger.error(f"百度搜索请求失败: {e}")
            return []

        # 验证码/反爬检测：百度会 302 跳到 wappass.baidu.com/static/captcha
        location = resp.headers.get("Location", "") if hasattr(resp, "headers") else ""
        if self._is_captcha_redirect(location):
            self.logger.warning("百度触发验证码，跳过本次结果")
            return []

        results = self._parse(resp, query)
        self.logger.info(f"百度搜索完成: 查询='{query}', 结果数={len(results)}")
        return results

    @staticmethod
    def _is_captcha_redirect(location: str) -> bool:
        """判断 302 Location 是否指向百度验证码页。

        按解析后的主机名与路径判断，而非对整段 URL 做子串匹配，避免把
        ``https://evil.example/?x=wappass.baidu.com`` 之类误判，也让判断语义清晰。
        """
        if not location:
            return False
        from urllib.parse import urlparse

        try:
            parsed = urlparse(location)
        except ValueError:
            return False
        host = (parsed.hostname or "").lower()
        path = (parsed.path or "").lower()
        if host == "wappass.baidu.com":
            return True
        # 同域下的验证码页（如 /static/captcha/...）
        return (host == "baidu.com" or host.endswith(".baidu.com")) and "captcha" in path

    def _parse(self, resp, query: str) -> List[SearchResult]:
        """解析百度 JSON 响应为 SearchResult 列表。"""
        import json
        from html import unescape

        try:
            data = json.loads(resp.text, strict=False)
        except Exception as e:  # noqa: BLE001
            self.logger.error(f"百度响应 JSON 解析失败: {e}")
            return []

        # 反爬标志
        if data.get("antiFlag") == 1:
            self.logger.warning("百度返回 antiFlag=1（拒绝抓取）")
            return []

        entries = (data.get("feed") or {}).get("entry") or []
        results = []
        for entry in entries:
            title = entry.get("title")
            url = entry.get("url")
            if not title or not url:
                continue
            title = unescape(title)
            content = unescape(entry.get("abs", "") or "")
            results.append(SearchResult(
                title=title,
                url=url,
                snippet=content,
                source="baidu",
                relevance_score=self._calc_relevance(title, content, query),
                metadata={
                    "source_type": "web",
                    "domain": self._extract_domain(url),
                },
            ))
        return results

    def _calc_relevance(self, title: str, body: str, query: str) -> float:
        """中文友好的相关性打分（复用 token 覆盖率逻辑）。"""
        try:
            qt = set(_tokenize(query))
            if not qt:
                return 0.6
            title_cov = len(qt & set(_tokenize(title))) / len(qt)
            body_cov = len(qt & set(_tokenize(body))) / len(qt)
            length_bonus = min(1.0, (len(title) + len(body)) / 800.0) * 0.1
            # 百度作为国内主力源，基础分略高
            return max(0.0, min(1.0, 0.15 + title_cov * 0.5 + body_cov * 0.3 + length_bonus))
        except Exception:  # noqa: BLE001
            return 0.6

    def _extract_domain(self, url: str) -> str:
        try:
            from urllib.parse import urlparse
            return urlparse(url).netloc
        except Exception:  # noqa: BLE001
            return url

    def get_source_name(self) -> str:
        return "Baidu"

    def is_available(self) -> bool:
        return True


class WikipediaSearchEngine(SearchEngine):
    """Wikipedia 搜索引擎实现 - 作为备用搜索引擎"""
    
    def __init__(self):
        super().__init__()
        # 语言站点按查询语言动态选择（见 _api_base_for_query）
        self._en_api = "https://en.wikipedia.org/w/api.php"
        self._zh_api = "https://zh.wikipedia.org/w/api.php"

    def _api_base_for_query(self, query: str) -> tuple:
        """按查询语言选择 Wikipedia 站点。

        此前写死英文站，中文查询召回极差。含中文的查询改用中文维基百科。
        返回 (api_url, lang) 其中 lang 用于构建结果 URL。
        """
        if _contains_cjk(query):
            return self._zh_api, "zh"
        return self._en_api, "en"

    async def search(self, query: str, max_results: int = 10) -> List[SearchResult]:
        """执行 Wikipedia 搜索"""
        if not self.is_available():
            self.logger.warning("Wikipedia 搜索引擎不可用")
            return []
        
        results = []
        try:
            import asyncio
            import requests

            loop = asyncio.get_event_loop()
            api_url, lang = self._api_base_for_query(query)

            # 使用Wikipedia API搜索
            params = {
                'action': 'query',
                'list': 'search',
                'srsearch': query,
                'format': 'json',
                'srlimit': max_results,
                'utf8': ''
            }
            
            response = await loop.run_in_executor(
                None,
                lambda: requests.get(api_url, params=params, timeout=10, headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                })
            )
            
            if response.status_code == 200:
                data = response.json()
                search_results = data.get('query', {}).get('search', [])
                
                for item in search_results:
                    title = item.get('title', '')
                    snippet = item.get('snippet', '').replace('<span class="searchmatch">', '').replace('</span>', '')
                    
                    if title:
                        # 构建Wikipedia URL（对应语言站点）
                        page_id = item.get('pageid', '')
                        wiki_url = f"https://{lang}.wikipedia.org/wiki?curid={page_id}"
                        
                        results.append(SearchResult(
                            title=title,
                            url=wiki_url,
                            snippet=snippet,
                            source='wikipedia',
                            relevance_score=0.8,  # Wikipedia通常质量较高
                            metadata={
                                'source_type': 'encyclopedia',
                                'domain': f'{lang}.wikipedia.org',
                                'pageid': page_id
                            }
                        ))
                
                self.logger.info(f"Wikipedia 搜索完成: 查询='{query}', 结果数={len(results)}")
            else:
                self.logger.warning(f"Wikipedia API 返回状态码: {response.status_code}")
                
        except Exception as e:
            self.logger.error(f"Wikipedia 搜索失败: {e}")
            return []
        
        return results
    
    def get_source_name(self) -> str:
        return "Wikipedia"
    
    def is_available(self) -> bool:
        """Wikipedia API通常是公开可用的"""
        return True


class SearchEngineManager:
    """搜索引擎管理器 - 支持多搜索引擎"""
    
    def __init__(self):
        self.engines: Dict[str, SearchEngine] = {}
        self.logger = logger
        self._register_default_engines()
    
    def _register_default_engines(self):
        """注册默认搜索引擎"""
        # 注册 DuckDuckGo
        ddg_engine = DuckDuckGoSearchEngine()
        if ddg_engine.is_available():
            self.engines['duckduckgo'] = ddg_engine
            self.engines['default'] = ddg_engine  # 设置为默认

        # 注册百度（国内信息主力源）
        try:
            self.engines['baidu'] = BaiduSearchEngine()
        except Exception as e:  # noqa: BLE001
            self.logger.warning(f"百度搜索引擎注册失败: {e}")

        # 注册 Wikipedia 作为备用
        wiki_engine = WikipediaSearchEngine()
        self.engines['wikipedia'] = wiki_engine

    def _sources_for_query(self, query: str) -> tuple:
        """按查询语境决定引擎优先级：国内查询以百度为主源。

        返回 (primary, fallbacks)。国内查询（region 解析为 cn-zh）→ 百度优先、
        DuckDuckGo/Wikipedia 兜底；否则 DuckDuckGo 优先、百度/Wikipedia 兜底。
        """
        cfg = _get_search_config()
        region = resolve_region(query, cfg["region"])
        has_baidu = 'baidu' in self.engines
        if region == "cn-zh" and has_baidu:
            return 'baidu', ['default', 'wikipedia']
        # 全球查询：DDG 主，百度也作为补充源之一
        fallbacks = (['baidu'] if has_baidu else []) + ['wikipedia']
        return 'default', fallbacks
    
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
    
    async def search_with_fallback(self, query: str, primary_source: str = 'default', 
                                  fallback_sources: List[str] = None, 
                                  max_results: int = 10) -> List[SearchResult]:
        """执行搜索，支持自动降级到备用搜索引擎。

        当调用方使用默认主源（'default'）且未显式指定备用时，按查询语境自动
        选择主源与备用：国内查询以百度为主源、DDG/Wikipedia 兜底。
        """
        if primary_source == 'default' and fallback_sources is None:
            primary_source, fallback_sources = self._sources_for_query(query)
        if fallback_sources is None:
            fallback_sources = ['wikipedia']  # 默认使用Wikipedia作为备用
        
        # 尝试主要搜索引擎
        engine = self.get_engine(primary_source)
        if engine:
            try:
                results = await engine.search(query, max_results)
                if results:
                    self.logger.info(f"使用主要搜索引擎 '{primary_source}' 成功获得 {len(results)} 个结果")
                    return results
            except Exception as e:
                self.logger.warning(f"主要搜索引擎 '{primary_source}' 失败: {e}")
        
        # 尝试备用搜索引擎
        for fallback_source in fallback_sources:
            fallback_engine = self.get_engine(fallback_source)
            if fallback_engine:
                try:
                    results = await fallback_engine.search(query, max_results)
                    if results:
                        self.logger.info(f"使用备用搜索引擎 '{fallback_source}' 成功获得 {len(results)} 个结果")
                        return results
                except Exception as e:
                    self.logger.warning(f"备用搜索引擎 '{fallback_source}' 失败: {e}")
        
        self.logger.error("所有搜索引擎均失败")
        return []
    
    async def search(self, query: str, source: str = 'default', 
                    max_results: int = 10) -> List[SearchResult]:
        """执行搜索"""
        engine = self.get_engine(source)
        if engine is None:
            logger.error(f"搜索引擎 '{source}' 不可用")
            return []
        
        return await engine.search(query, max_results)

    async def search_aggregated(self, query: str, sources: List[str] = None,
                                max_results: int = 10) -> List[SearchResult]:
        """聚合多个引擎的结果（合并去重）而非"首个非空即返回"。

        此前 search_with_fallback 只在主引擎失败时才用备用，且一旦有结果就
        立即返回，丢弃其它来源。聚合模式下同时查询多个引擎并合并结果，跨来源
        按 URL 去重，提升覆盖率（尤其中英文混合、国内信息场景）。

        注意：主引擎 DuckDuckGo 已通过 ddgs 的 backend 在内部聚合
        bing/google 等，本方法进一步把 Wikipedia 等异构来源也纳入。
        """
        if sources is None:
            # 按查询语境排序引擎：国内查询把百度放首位
            primary, fallbacks = self._sources_for_query(query)
            sources = [primary] + [s for s in fallbacks if s != primary]

        seen_engines = set()
        merged: List[SearchResult] = []
        seen_urls = set()

        for source in sources:
            engine = self.get_engine(source)
            if engine is None or id(engine) in seen_engines:
                continue
            seen_engines.add(id(engine))
            try:
                results = await engine.search(query, max_results)
            except Exception as e:  # noqa: BLE001
                self.logger.warning(f"聚合搜索：引擎 '{source}' 失败: {e}")
                continue
            for r in results:
                key = (r.url or "").split("#")[0].rstrip("/")
                if key and key in seen_urls:
                    continue
                if key:
                    seen_urls.add(key)
                merged.append(r)

        if not merged:
            self.logger.error("聚合搜索：所有引擎均无结果")
        return merged


# 全局搜索引擎管理器实例
_search_engine_manager = None

def get_search_engine_manager() -> SearchEngineManager:
    """获取全局搜索引擎管理器实例"""
    global _search_engine_manager
    if _search_engine_manager is None:
        _search_engine_manager = SearchEngineManager()
    return _search_engine_manager
