#!/usr/bin/env python3
"""
网页内容提取器 - 提取网页正文内容并清理格式
"""
import logging
from typing import Optional, Dict
from urllib.parse import urlparse
import re

logger = logging.getLogger(__name__)


class ContentExtractor:
    """网页内容提取器"""
    
    def __init__(self):
        self.logger = logger
        self._trafilatura_available = self._check_trafilatura()
        self._beautifulsoup_available = self._check_beautifulsoup()
    
    def _check_trafilatura(self) -> bool:
        """检查 trafilatura 是否可用"""
        try:
            import trafilatura
            return True
        except ImportError:
            self.logger.warning("trafilatura 未安装，将使用备用提取方法")
            return False
    
    def _check_beautifulsoup(self) -> bool:
        """检查 beautifulsoup4 是否可用"""
        try:
            from bs4 import BeautifulSoup
            return True
        except ImportError:
            self.logger.warning("beautifulsoup4 未安装")
            return False
    
    async def extract(self, url: str, timeout: int = 30) -> Dict:
        """提取网页内容"""
        result = {
            'url': url,
            'title': '',
            'content': '',
            'error': None,
            'method_used': ''
        }
        
        try:
            # 优先使用 trafilatura
            if self._trafilatura_available:
                content = await self._extract_with_trafilatura(url, timeout)
                if content:
                    result.update(content)
                    result['method_used'] = 'trafilatura'
                    return result
            
            # 备用方案：使用 beautifulsoup
            if self._beautifulsoup_available:
                content = await self._extract_with_beautifulsoup(url, timeout)
                if content:
                    result.update(content)
                    result['method_used'] = 'beautifulsoup'
                    return result
            
            # 最后备用：使用 requests 直接获取
            content = await self._extract_with_requests(url, timeout)
            if content:
                result.update(content)
                result['method_used'] = 'requests'
                return result
            
            result['error'] = "所有提取方法都失败了"
            
        except Exception as e:
            result['error'] = str(e)
            self.logger.error(f"内容提取失败: {e}")
        
        return result
    
    async def _extract_with_trafilatura(self, url: str, timeout: int) -> Optional[Dict]:
        """使用 trafilatura 提取内容"""
        try:
            import trafilatura
            # 使用异步方式执行同步操作
            import asyncio
            loop = asyncio.get_event_loop()
            
            downloaded = await loop.run_in_executor(
                None,
                lambda: trafilatura.fetch_url(url, timeout=timeout)
            )
            
            if downloaded:
                content = trafilatura.extract(
                    downloaded,
                    output_format='json',
                    include_comments=False,
                    include_tables=True
                )
                
                if content:
                    import json
                    data = json.loads(content)
                    return {
                        'title': data.get('title', ''),
                        'content': data.get('text', ''),
                        'author': data.get('author', ''),
                        'date': data.get('date', ''),
                        'metadata': {
                            'language': data.get('language', ''),
                            'categories': data.get('categories', [])
                        }
                    }
        except Exception as e:
            self.logger.warning(f"trafilatura 提取失败: {e}")
        
        return None
    
    async def _extract_with_beautifulsoup(self, url: str, timeout: int) -> Optional[Dict]:
        """使用 beautifulsoup 提取内容"""
        try:
            import asyncio
            import requests
            from bs4 import BeautifulSoup
            
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: requests.get(url, timeout=timeout, headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                })
            )
            
            if response.status_code == 200:
                soup = BeautifulSoup(response.content, 'html.parser')
                
                # 提取标题
                title = ''
                if soup.title:
                    title = soup.title.get_text().strip()
                
                # 移除脚本和样式
                for script in soup(["script", "style", "nav", "footer", "header"]):
                    script.decompose()
                
                # 提取正文
                text = soup.get_text()
                
                # 清理文本
                lines = (line.strip() for line in text.splitlines())
                chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
                text = '\n'.join(chunk for chunk in chunks if chunk)
                
                return {
                    'title': title,
                    'content': text,
                    'metadata': {
                        'content_length': len(text),
                        'status_code': response.status_code
                    }
                }
        except Exception as e:
            self.logger.warning(f"beautifulsoup 提取失败: {e}")
        
        return None
    
    async def _extract_with_requests(self, url: str, timeout: int) -> Optional[Dict]:
        """使用 requests 直接获取内容"""
        try:
            import asyncio
            import requests
            
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: requests.get(url, timeout=timeout, headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                })
            )
            
            if response.status_code == 200:
                return {
                    'title': '',
                    'content': response.text[:10000],  # 限制长度
                    'metadata': {
                        'content_length': len(response.text),
                        'status_code': response.status_code
                    }
                }
        except Exception as e:
            self.logger.warning(f"requests 提取失败: {e}")
        
        return None
    
    def clean_text(self, text: str) -> str:
        """清理文本格式"""
        if not text:
            return ""
        
        # 移除多余空白
        text = re.sub(r'\s+', ' ', text)
        
        # 移除特殊字符（保留常用标点）
        text = re.sub(r'[^\w\s\.\,\!\?\-\(\)\[\]\{\}\:\;\"\']', '', text)
        
        # 移除连续的标点
        text = re.sub(r'[\.\!\?]{2,}', '.', text)
        
        return text.strip()
    
    def is_valid_url(self, url: str) -> bool:
        """验证 URL 是否有效"""
        try:
            result = urlparse(url)
            return all([result.scheme, result.netloc])
        except Exception:
            return False
    
    def extract_domain(self, url: str) -> str:
        """提取域名"""
        try:
            result = urlparse(url)
            return result.netloc
        except Exception:
            return url


# 全局内容提取器实例
_content_extractor = None

def get_content_extractor() -> ContentExtractor:
    """获取全局内容提取器实例"""
    global _content_extractor
    if _content_extractor is None:
        _content_extractor = ContentExtractor()
    return _content_extractor
