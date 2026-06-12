"""
OCR 处理模块 - 支持图片和 PDF 的光学字符识别
"""
from .base import BaseOCREngine, OCRResult
from .paddle_ocr import PaddleOCREngine
from .tesseract_ocr import TesseractOCREngine
from .image_extractor import PDFImageExtractor, ExtractedImage
from .preprocessor import ImagePreprocessor
from .cache import OCRCache

__all__ = [
    'BaseOCREngine',
    'OCRResult',
    'PaddleOCREngine',
    'TesseractOCREngine',
    'PDFImageExtractor',
    'ExtractedImage',
    'ImagePreprocessor',
    'OCRCache',
]
