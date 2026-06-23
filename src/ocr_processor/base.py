"""
OCR 引擎抽象基类
"""
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class OCRResult:
    """OCR 识别结果"""
    text: str                          # 识别的文本
    confidence: float                   # 置信度 (0-1)
    bbox: Optional[Tuple[int, int, int, int]] = None  # 边界框 (x1, y1, x2, y2)
    language: Optional[str] = None     # 检测到的语言
    page_num: Optional[int] = None     # 页码（PDF）
    image_hash: Optional[str] = None   # 图片哈希（用于缓存）
    metadata: Dict = field(default_factory=dict)  # 额外元数据
    
    def __post_init__(self):
        """验证数据"""
        if not 0 <= self.confidence <= 1:
            raise ValueError(f"置信度必须在 0-1 之间: {self.confidence}")
        if not self.text:
            raise ValueError("识别文本不能为空")


class BaseOCREngine(ABC):
    """OCR 引擎抽象基类"""
    
    def __init__(self, config: Dict):
        """
        初始化 OCR 引擎
        
        Args:
            config: 配置字典，包含引擎特定的参数
        """
        self.config = config
        self._cache = None
        cache_dir = config.get('cache_dir')
        if cache_dir:
            from .cache import OCRCache
            self._cache = OCRCache(cache_dir)
    
    @abstractmethod
    def recognize_image(
        self,
        image_path: Path,
        preprocess: bool = True
    ) -> List[OCRResult]:
        """
        识别单张图片
        
        Args:
            image_path: 图片文件路径
            preprocess: 是否进行图像预处理
            
        Returns:
            OCR 识别结果列表
        """
        pass
    
    @abstractmethod
    def recognize_batch(
        self,
        image_paths: List[Path],
        parallel: bool = True
    ) -> List[List[OCRResult]]:
        """
        批量识别图片
        
        Args:
            image_paths: 图片文件路径列表
            parallel: 是否并行处理
            
        Returns:
            每张图片的 OCR 识别结果列表
        """
        pass
    
    @abstractmethod
    def detect_language(self, image_path: Path) -> str:
        """
        检测图片语言
        
        Args:
            image_path: 图片文件路径
            
        Returns:
            检测到的语言代码
        """
        pass
    
    def get_cached_result(self, image_hash: str) -> Optional[OCRResult]:
        """
        获取缓存结果
        
        Args:
            image_hash: 图片哈希值
            
        Returns:
            缓存的 OCR 结果，如果不存在则返回 None
        """
        if self._cache:
            return self._cache.get(image_hash)
        return None
    
    def cache_result(self, image_hash: str, result: OCRResult):
        """
        缓存结果
        
        Args:
            image_hash: 图片哈希值
            result: OCR 识别结果
        """
        if self._cache:
            self._cache.set(image_hash, result)
    
    def clear_cache(self):
        """清空缓存"""
        if self._cache:
            self._cache.clear()
    
    def compute_image_hash(self, image_path: Path) -> str:
        """
        计算图片哈希值（用于缓存）
        
        Args:
            image_path: 图片文件路径
            
        Returns:
            图片的 MD5 哈希值
        """
        import hashlib
        with open(image_path, 'rb') as f:
            return hashlib.md5(f.read(), usedforsecurity=False).hexdigest()
    
    def validate_image(self, image_path: Path) -> bool:
        """
        验证图片文件是否有效
        
        Args:
            image_path: 图片文件路径
            
        Returns:
            如果图片有效则返回 True，否则返回 False
        """
        if not image_path.exists():
            return False
        
        try:
            from PIL import Image
            with Image.open(image_path) as img:
                img.verify()
            return True
        except Exception:
            return False
    
    def get_engine_info(self) -> Dict:
        """
        获取引擎信息
        
        Returns:
            包含引擎名称、版本等信息的字典
        """
        return {
            'engine_name': self.__class__.__name__,
            'config': self.config,
        }
