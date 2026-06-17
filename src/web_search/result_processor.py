#!/usr/bin/env python3
"""
搜索结果处理器 - 处理、排序、去重搜索结果
"""
import logging
from typing import List, Dict, Optional
from urllib.parse import urlparse
from datetime import datetime

from .search_engine import SearchResult

logger = logging.getLogger(__name__)


class ResultProcessor:
    """搜索结果处理器"""
    
    def __init__(self):
        self.logger = logger
    
    def deduplicate(self, results: List[SearchResult]) -> List[SearchResult]:
        """去重搜索结果"""
        seen_urls = set()
        unique_results = []
        
        for result in results:
            # 标准化 URL 进行比较
            url = self._normalize_url(result.url)
            if url not in seen_urls:
                seen_urls.add(url)
                unique_results.append(result)
        
        self.logger.info(f"去重: {len(results)} -> {len(unique_results)}")
        return unique_results
    
    def _normalize_url(self, url: str) -> str:
        """标准化 URL"""
        try:
            parsed = urlparse(url)
            # 移除常见的跟踪参数
            return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
        except Exception:
            return url
    
    def sort_by_relevance(self, results: List[SearchResult], 
                         descending: bool = True) -> List[SearchResult]:
        """按相关性排序"""
        sorted_results = sorted(
            results,
            key=lambda x: x.relevance_score,
            reverse=descending
        )
        return sorted_results
    
    def filter_by_source(self, results: List[SearchResult], 
                       source: str) -> List[SearchResult]:
        """按来源过滤"""
        filtered = [r for r in results if r.source == source]
        self.logger.info(f"按来源 '{source}' 过滤: {len(filtered)} 条结果")
        return filtered
    
    def filter_by_domain(self, results: List[SearchResult], 
                        domain: str) -> List[SearchResult]:
        """按域名过滤"""
        filtered = []
        for result in results:
            try:
                url_domain = urlparse(result.url).netloc
                if domain in url_domain:
                    filtered.append(result)
            except Exception:
                continue
        
        self.logger.info(f"按域名 '{domain}' 过滤: {len(filtered)} 条结果")
        return filtered
    
    def filter_by_keywords(self, results: List[SearchResult], 
                          keywords: List[str]) -> List[SearchResult]:
        """按关键词过滤"""
        keywords_lower = [k.lower() for k in keywords]
        filtered = []
        
        for result in results:
            title_lower = result.title.lower()
            snippet_lower = result.snippet.lower()
            
            # 检查是否包含任一关键词
            if any(
                keyword in title_lower or keyword in snippet_lower
                for keyword in keywords_lower
            ):
                filtered.append(result)
        
        self.logger.info(f"按关键词 {keywords} 过滤: {len(filtered)} 条结果")
        return filtered
    
    def limit_results(self, results: List[SearchResult], 
                     limit: int) -> List[SearchResult]:
        """限制结果数量"""
        limited = results[:limit]
        self.logger.info(f"限制结果数量: {len(results)} -> {len(limited)}")
        return limited
    
    def enrich_results(self, results: List[SearchResult]) -> List[SearchResult]:
        """丰富结果信息"""
        enriched = []
        
        for result in results:
            # 添加额外的元数据
            metadata = result.metadata.copy()
            
            # 提取域名
            try:
                domain = urlparse(result.url).netloc
                metadata['domain'] = domain
                
                # 尝试判断网站类型
                metadata['site_type'] = self._classify_site_type(domain)
            except Exception as e:
                self.logger.warning(f"丰富结果失败: {e}")
            
            # 创建新的 SearchResult 对象
            enriched_result = SearchResult(
                title=result.title,
                url=result.url,
                snippet=result.snippet,
                source=result.source,
                relevance_score=result.relevance_score,
                metadata=metadata,
                timestamp=result.timestamp
            )
            enriched.append(enriched_result)
        
        return enriched
    
    def _classify_site_type(self, domain: str) -> str:
        """分类网站类型"""
        domain_lower = domain.lower()
        
        if any(x in domain_lower for x in ['github', 'gitlab', 'bitbucket']):
            return 'code_repository'
        elif any(x in domain_lower for x in ['stackoverflow', 'stackexchange']):
            return 'qa_forum'
        elif any(x in domain_lower for x in ['wikipedia', 'wiki']):
            return 'wiki'
        elif any(x in domain_lower for x in ['arxiv', 'researchgate', 'scholar']):
            return 'academic'
        elif any(x in domain_lower for x in ['docs', 'documentation']):
            return 'documentation'
        elif any(x in domain_lower for x in ['blog', 'medium', 'dev.to']):
            return 'blog'
        else:
            return 'general'
    
    def merge_results(self, result_sets: List[List[SearchResult]], 
                     max_results: int = 20) -> List[SearchResult]:
        """合并多个搜索结果集"""
        # 合并所有结果
        all_results = []
        for results in result_sets:
            all_results.extend(results)
        
        # 去重
        unique_results = self.deduplicate(all_results)
        
        # 排序
        sorted_results = self.sort_by_relevance(unique_results)
        
        # 限制数量
        final_results = self.limit_results(sorted_results, max_results)
        
        self.logger.info(f"合并 {len(result_sets)} 个结果集: 最终 {len(final_results)} 条结果")
        return final_results
    
    def format_results(self, results: List[SearchResult], 
                      format: str = 'text') -> str:
        """格式化搜索结果"""
        if format == 'text':
            return self._format_text(results)
        elif format == 'json':
            return self._format_json(results)
        elif format == 'markdown':
            return self._format_markdown(results)
        else:
            return self._format_text(results)
    
    def _format_text(self, results: List[SearchResult]) -> str:
        """格式化为文本"""
        lines = []
        lines.append(f"搜索结果 ({len(results)} 条):")
        lines.append("=" * 60)
        
        for i, result in enumerate(results, 1):
            lines.append(f"\n{i}. {result.title}")
            lines.append(f"   URL: {result.url}")
            lines.append(f"   来源: {result.source} | 相关性: {result.relevance_score:.2f}")
            lines.append(f"   摘要: {result.snippet[:200]}...")
        
        return "\n".join(lines)
    
    def _format_json(self, results: List[SearchResult]) -> str:
        """格式化为 JSON"""
        import json
        data = [result.to_dict() for result in results]
        return json.dumps(data, ensure_ascii=False, indent=2)
    
    def _format_markdown(self, results: List[SearchResult]) -> str:
        """格式化为 Markdown"""
        lines = []
        lines.append(f"# 搜索结果 ({len(results)} 条)")
        lines.append("")
        
        for i, result in enumerate(results, 1):
            lines.append(f"## {i}. {result.title}")
            lines.append(f"**URL**: {result.url}")
            lines.append(f"**来源**: {result.source} | **相关性**: {result.relevance_score:.2f}")
            lines.append(f"**摘要**: {result.snippet}")
            lines.append("")
        
        return "\n".join(lines)
    
    def get_summary(self, results: List[SearchResult]) -> Dict:
        """获取搜索结果摘要"""
        if not results:
            return {
                'total': 0,
                'sources': {},
                'avg_relevance': 0.0,
                'domains': {}
            }
        
        # 按来源统计
        source_stats: Dict[str, int] = {}
        for result in results:
            source = result.source
            source_stats[source] = source_stats.get(source, 0) + 1
        
        # 按域名统计
        domain_stats: Dict[str, int] = {}
        for result in results:
            try:
                domain = urlparse(result.url).netloc
                domain_stats[domain] = domain_stats.get(domain, 0) + 1
            except Exception:
                continue
        
        # 平均相关性
        avg_relevance = sum(r.relevance_score for r in results) / len(results)
        
        return {
            'total': len(results),
            'sources': source_stats,
            'avg_relevance': avg_relevance,
            'domains': domain_stats,
            'timestamp': datetime.now().isoformat()
        }


# 全局结果处理器实例
_result_processor = None

def get_result_processor() -> ResultProcessor:
    """获取全局结果处理器实例"""
    global _result_processor
    if _result_processor is None:
        _result_processor = ResultProcessor()
    return _result_processor
