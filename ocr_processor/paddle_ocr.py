"""
PaddleOCR 引擎实现
"""
from typing import List, Dict
from pathlib import Path
import numpy as np

from .base import BaseOCREngine, OCRResult


class PaddleOCREngine(BaseOCREngine):
    """PaddleOCR 引擎实现"""
    
    def __init__(self, config: Dict):
        """
        初始化 PaddleOCR 引擎
        
        Args:
            config: 配置字典
                - use_gpu: 是否使用 GPU
                - lang: 语言 ('ch', 'en', 'jk')
                - use_angle_cls: 是否使用方向分类
                - show_log: 是否显示日志
        """
        super().__init__(config)
        
        self.use_gpu = config.get('use_gpu', False)
        self.lang = config.get('lang', 'ch')
        self.use_angle_cls = config.get('use_angle_cls', True)
        self.show_log = config.get('show_log', False)
        
        # 初始化 PaddleOCR
        try:
            from paddleocr import PaddleOCR
            self.ocr = PaddleOCR(
                use_angle_cls=self.use_angle_cls,
                lang=self.lang,
                use_gpu=self.use_gpu,
                show_log=self.show_log
            )
        except ImportError:
            raise ImportError(
                "PaddleOCR 未安装，请运行: pip install paddleocr paddlepaddle"
            )
        
        # 初始化预处理器
        self._preprocessor = None
        if config.get('preprocess', True):
            from .preprocessor import ImagePreprocessor, PreprocessConfig
            preprocess_config = PreprocessConfig(
                denoise=config.get('denoise', True),
                binarize=config.get('binarize', True),
                deskew=config.get('deskew', True),
                enhance_contrast=config.get('enhance_contrast', True),
                resize=config.get('resize')
            )
            self._preprocessor = ImagePreprocessor(preprocess_config)
    
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
        # 验证图片
        if not self.validate_image(image_path):
            raise ValueError(f"图片无效或不存在: {image_path}")
        
        # 检查缓存
        image_hash = self.compute_image_hash(image_path)
        cached = self.get_cached_result(image_hash)
        if cached:
            return [cached]
        
        # 图像预处理
        if preprocess and self._preprocessor:
            try:
                image = self._preprocessor.preprocess(image_path)
            except Exception as e:
                # 预处理失败，使用原图
                print(f"预处理失败，使用原图: {e}")
                image = str(image_path)
        else:
            image = str(image_path)
        
        # OCR 识别
        try:
            result = self.ocr.ocr(image, cls=True)
        except Exception as e:
            raise RuntimeError(f"OCR 识别失败: {e}")
        
        if not result or not result[0]:
            return []
        
        # 转换为标准格式
        ocr_results = []
        for line in result[0]:
            text = line[1][0]
            confidence = line[1][1]
            bbox = line[0]
            
            ocr_results.append(OCRResult(
                text=text,
                confidence=confidence,
                bbox=self._normalize_bbox(bbox),
                language=self.lang,
                image_hash=image_hash,
                page_num=None,
                metadata={'engine': 'paddle'}
            ))
        
        # 缓存第一个结果
        if ocr_results:
            self.cache_result(image_hash, ocr_results[0])
        
        return ocr_results
    
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
        if parallel:
            from concurrent.futures import ThreadPoolExecutor, as_completed
            max_workers = self.config.get('parallel_workers', 2)
            
            results = [None] * len(image_paths)
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_to_index = {
                    executor.submit(self.recognize_image, path): i
                    for i, path in enumerate(image_paths)
                }
                
                for future in as_completed(future_to_index):
                    index = future_to_index[future]
                    try:
                        results[index] = future.result()
                    except Exception as e:
                        print(f"图片 {image_paths[index]} 识别失败: {e}")
                        results[index] = []
            
            return results
        else:
            return [self.recognize_image(path) for path in image_paths]
    
    def detect_language(self, image_path: Path) -> str:
        """
        检测图片语言
        
        Args:
            image_path: 图片文件路径
            
        Returns:
            检测到的语言代码
        """
        # PaddleOCR 目前不支持自动语言检测
        # 返回配置的语言
        return self.lang
    
    def _normalize_bbox(self, bbox: List) -> tuple:
        """
        标准化边界框坐标
        
        Args:
            bbox: PaddleOCR 返回的边界框 [[x1, y1], [x2, y2], [x3, y3], [x4, y4]]
            
        Returns:
            标准化的边界框 (x1, y1, x2, y2)
        """
        x_coords = [point[0] for point in bbox]
        y_coords = [point[1] for point in bbox]
        return (
            int(min(x_coords)),
            int(min(y_coords)),
            int(max(x_coords)),
            int(max(y_coords))
        )
    
    def get_engine_info(self) -> Dict:
        """
        获取引擎信息
        
        Returns:
            包含引擎信息的字典
        """
        info = super().get_engine_info()
        info.update({
            'use_gpu': self.use_gpu,
            'lang': self.lang,
            'use_angle_cls': self.use_angle_cls,
        })
        return info
