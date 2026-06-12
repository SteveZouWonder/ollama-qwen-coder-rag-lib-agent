"""
Tesseract OCR 引擎实现
"""
from typing import List, Dict
from pathlib import Path

from .base import BaseOCREngine, OCRResult


class TesseractOCREngine(BaseOCREngine):
    """Tesseract OCR 引擎实现"""
    
    def __init__(self, config: Dict):
        """
        初始化 Tesseract OCR 引擎
        
        Args:
            config: 配置字典
                - tesseract_path: Tesseract 可执行文件路径
                - lang: 语言代码 (如 'chi_sim+eng')
                - config: Tesseract 配置参数
        """
        super().__init__(config)
        
        self.tesseract_path = config.get('tesseract_path')
        self.lang = config.get('lang', 'chi_sim+eng')
        self.tesseract_config = config.get('config', '')
        
        # 设置 Tesseract 路径
        if self.tesseract_path:
            import pytesseract
            pytesseract.pytesseract.tesseract_cmd = self.tesseract_path
        
        # 验证 Tesseract 是否可用
        try:
            import pytesseract
            pytesseract.get_tesseract_version()
        except ImportError:
            raise ImportError(
                "pytesseract 未安装，请运行: pip install pytesseract"
            )
        except Exception as e:
            raise RuntimeError(
                f"Tesseract 不可用，请确保已安装 Tesseract: {e}"
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
        import pytesseract
        from PIL import Image
        
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
                processed_image = self._preprocessor.preprocess(image_path)
                # 将 numpy 数组转换回 PIL Image
                pil_image = Image.fromarray(processed_image)
            except Exception as e:
                # 预处理失败，使用原图
                print(f"预处理失败，使用原图: {e}")
                pil_image = Image.open(image_path)
        else:
            pil_image = Image.open(image_path)
        
        # OCR 识别
        try:
            # 使用 image_to_string 获得完整文本
            full_text = pytesseract.image_to_string(
                pil_image,
                lang=self.lang,
                config=self.tesseract_config
            )
            
            # 如果识别结果太短，尝试不同语言配置
            if len(full_text.strip()) < 10:
                # 尝试只用英文
                full_text = pytesseract.image_to_string(
                    pil_image,
                    lang='eng',
                    config=self.tesseract_config
                )
                
                # 如果还是很短，尝试不指定语言
                if len(full_text.strip()) < 10:
                    full_text = pytesseract.image_to_string(
                        pil_image,
                        config=self.tesseract_config
                    )
        except Exception as e:
            raise RuntimeError(f"OCR 识别失败: {e}")
        
        # 解析结果 - 使用完整的文本创建单个 OCRResult
        ocr_results = []
        
        # 将完整文本作为单个结果返回
        text = full_text.strip()
        if text:
            # 估算置信度（基于文本长度和清晰度）
            confidence = min(0.95, max(0.5, len(text) / 200.0))
            
            # 使用整个图片作为边界框
            width, height = pil_image.size
            bbox = (0, 0, width, height)
            
            ocr_results.append(OCRResult(
                text=text,
                confidence=confidence,
                bbox=bbox,
                language=self.lang,
                image_hash=image_hash,
                page_num=None,
                metadata={'engine': 'tesseract', 'method': 'image_to_string'}
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
        # Tesseract 不支持自动语言检测
        # 返回配置的语言
        return self.lang
    
    def get_engine_info(self) -> Dict:
        """
        获取引擎信息
        
        Returns:
            包含引擎信息的字典
        """
        import pytesseract
        
        info = super().get_engine_info()
        try:
            version = pytesseract.get_tesseract_version()
            info.update({
                'tesseract_path': self.tesseract_path,
                'lang': self.lang,
                'version': str(version),
            })
        except Exception:
            info.update({
                'tesseract_path': self.tesseract_path,
                'lang': self.lang,
                'version': 'unknown',
            })
        return info
