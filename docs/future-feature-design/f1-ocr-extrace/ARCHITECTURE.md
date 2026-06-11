# OCR 功能架构设计

## 系统架构

### 整体架构图

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Application Layer                           │
│                   query_interface.py / CLI                         │
└─────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│                       Document Processing Layer                     │
│                      document_loader.py (扩展)                      │
└─────────────────────────────────────────────────────────────────────┘
                                  │
           ┌──────────────────────┼──────────────────────┐
           ▼                      ▼                      ▼
┌─────────────────────┐  ┌─────────────────────┐  ┌─────────────────────┐
│   Text Documents    │  │   PDF Documents     │  │   Image Files       │
│   (MD, TXT, Code)   │  │   (Scanned/Mixed)   │  │   (PNG, JPG, etc)   │
└─────────────────────┘  └─────────────────────┘  └─────────────────────┘
                                   │                      │
                                   ▼                      ▼
                           ┌──────────────────────────────────┐
                           │        OCR Processing Layer     │
                           │  ┌────────────────────────────┐ │
                           │  │   Image Extractor          │ │
                           │  │   (PDF → Images)           │ │
                           │  └────────────────────────────┘ │
                           │               │                  │
                           │               ▼                  │
                           │  ┌────────────────────────────┐ │
                           │  │   Image Preprocessor      │ │
                           │  │   (降噪/倾斜校正/增强)     │ │
                           │  └────────────────────────────┘ │
                           │               │                  │
                           │               ▼                  │
                           │  ┌────────────────────────────┐ │
                           │  │   OCR Engine (Paddle/Tess) │ │
                           │  └────────────────────────────┘ │
                           │               │                  │
                           │               ▼                  │
                           │  ┌────────────────────────────┐ │
                           │  │   Post Processor          │ │
                           │  │   (去噪/格式化/置信度)     │ │
                           │  └────────────────────────────┘ │
                           └──────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         Data Integration Layer                       │
│                    OCR Result + Original Text                       │
└─────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        Indexing Layer                               │
│                        rag_engine.py                                │
└─────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      Storage Layer                                  │
│              ChromaDB + OCR Cache + File System                     │
└─────────────────────────────────────────────────────────────────────┘
```

## 模块设计

### 1. OCR 核心模块

#### 1.1 基类设计 (ocr_processor/base.py)

```python
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from pathlib import Path

@dataclass
class OCRResult:
    """OCR 识别结果"""
    text: str                          # 识别的文本
    confidence: float                   # 置信度 (0-1)
    bbox: Optional[Tuple[int, int, int, int]]  # 边界框 (x1, y1, x2, y2)
    language: Optional[str] = None     # 检测到的语言
    page_num: Optional[int] = None     # 页码（PDF）
    image_hash: Optional[str] = None   # 图片哈希（用于缓存）

class BaseOCREngine(ABC):
    """OCR 引擎抽象基类"""

    def __init__(self, config: Dict):
        self.config = config
        self.cache = OCRCache(config.get('cache_dir'))

    @abstractmethod
    def recognize_image(
        self,
        image_path: Path,
        preprocess: bool = True
    ) -> List[OCRResult]:
        """识别单张图片"""
        pass

    @abstractmethod
    def recognize_batch(
        self,
        image_paths: List[Path],
        parallel: bool = True
    ) -> List[List[OCRResult]]:
        """批量识别图片"""
        pass

    @abstractmethod
    def detect_language(self, image_path: Path) -> str:
        """检测图片语言"""
        pass

    def get_cached_result(self, image_hash: str) -> Optional[OCRResult]:
        """获取缓存结果"""
        return self.cache.get(image_hash)

    def cache_result(self, image_hash: str, result: OCRResult):
        """缓存结果"""
        self.cache.set(image_hash, result)
```

#### 1.2 PaddleOCR 实现 (ocr_processor/paddle_ocr.py)

```python
from paddleocr import PaddleOCR
from .base import BaseOCREngine, OCRResult
import cv2
import numpy as np

class PaddleOCREngine(BaseOCREngine):
    """PaddleOCR 引擎实现"""

    def __init__(self, config: Dict):
        super().__init__(config)
        self.use_gpu = config.get('use_gpu', False)
        self.lang = config.get('lang', 'ch')  # ch, en, jk

        # 初始化 PaddleOCR
        self.ocr = PaddleOCR(
            use_angle_cls=True,  # 启用方向分类
            lang=self.lang,
            use_gpu=self.use_gpu,
            show_log=False
        )

    def recognize_image(
        self,
        image_path: Path,
        preprocess: bool = True
    ) -> List[OCRResult]:
        """识别单张图片"""
        # 检查缓存
        image_hash = self._compute_hash(image_path)
        cached = self.get_cached_result(image_hash)
        if cached:
            return [cached]

        # 图像预处理
        if preprocess:
            image = self._preprocess_image(image_path)
        else:
            image = str(image_path)

        # OCR 识别
        result = self.ocr.ocr(image, cls=True)

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
                language=self.lang
            ))

        # 缓存结果
        if ocr_results:
            self.cache_result(image_hash, ocr_results[0])

        return ocr_results

    def _preprocess_image(self, image_path: Path) -> np.ndarray:
        """图像预处理"""
        img = cv2.imread(str(image_path))

        # 转换为灰度图
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        # 去噪
        denoised = cv2.fastNlMeansDenoising(gray)

        # 二值化
        _, binary = cv2.threshold(denoised, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

        return binary

    def _compute_hash(self, image_path: Path) -> str:
        """计算图片哈希用于缓存"""
        import hashlib
        with open(image_path, 'rb') as f:
            return hashlib.md5(f.read()).hexdigest()

    def _normalize_bbox(self, bbox: List) -> Tuple[int, int, int, int]:
        """标准化边界框坐标"""
        x_coords = [point[0] for point in bbox]
        y_coords = [point[1] for point in bbox]
        return (min(x_coords), min(y_coords), max(x_coords), max(y_coords))

    def recognize_batch(
        self,
        image_paths: List[Path],
        parallel: bool = True
    ) -> List[List[OCRResult]]:
        """批量识别"""
        if parallel:
            from concurrent.futures import ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=self.config.get('parallel_workers', 2)) as executor:
                return list(executor.map(self.recognize_image, image_paths))
        else:
            return [self.recognize_image(path) for path in image_paths]

    def detect_language(self, image_path: Path) -> str:
        """检测语言（简化版，直接返回配置的语言）"""
        return self.lang
```

#### 1.3 Tesseract 实现 (ocr_processor/tesseract_ocr.py)

```python
import pytesseract
from PIL import Image
from .base import BaseOCREngine, OCRResult

class TesseractOCREngine(BaseOCREngine):
    """Tesseract OCR 引擎实现"""

    def __init__(self, config: Dict):
        super().__init__(config)
        self.tesseract_path = config.get('tesseract_path', '/usr/local/bin/tesseract')
        self.lang = config.get('lang', 'chi_sim+eng')

        # 设置 Tesseract 路径
        pytesseract.pytesseract.tesseract_cmd = self.tesseract_path

    def recognize_image(
        self,
        image_path: Path,
        preprocess: bool = True
    ) -> List[OCRResult]:
        """识别单张图片"""
        # 检查缓存
        image_hash = self._compute_hash(image_path)
        cached = self.get_cached_result(image_hash)
        if cached:
            return [cached]

        # 打开图片
        image = Image.open(image_path)

        # OCR 识别
        text = pytesseract.image_to_string(
            image,
            lang=self.lang,
            config='--psm 6'  # 假设为统一文本块
        )

        # 获取详细信息（包括置信度）
        data = pytesseract.image_to_data(
            image,
            lang=self.lang,
            output_type=pytesseract.Output.DICT
        )

        # 计算平均置信度
        confidences = [int(conf) for conf in data['conf'] if conf != '-1']
        avg_confidence = sum(confidences) / len(confidences) if confidences else 0

        # 创建结果
        result = OCRResult(
            text=text.strip(),
            confidence=avg_confidence / 100.0,  # 转换为 0-1
            bbox=None,  # Tesseract bbox 较复杂，暂不实现
            language=self.lang,
            image_hash=image_hash
        )

        # 缓存结果
        self.cache_result(image_hash, result)

        return [result]

    def recognize_batch(
        self,
        image_paths: List[Path],
        parallel: bool = True
    ) -> List[List[OCRResult]]:
        """批量识别"""
        if parallel:
            from concurrent.futures import ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=self.config.get('parallel_workers', 2)) as executor:
                return list(executor.map(self.recognize_image, image_paths))
        else:
            return [self.recognize_image(path) for path in image_paths]

    def detect_language(self, image_path: Path) -> str:
        """检测语言"""
        return self.lang

    def _compute_hash(self, image_path: Path) -> str:
        """计算图片哈希"""
        import hashlib
        with open(image_path, 'rb') as f:
            return hashlib.md5(f.read()).hexdigest()
```

#### 1.4 图片提取器 (ocr_processor/image_extractor.py)

```python
import fitz  # PyMuPDF
from typing import List, Tuple
from pathlib import Path
from dataclasses import dataclass

@dataclass
class ExtractedImage:
    """提取的图片"""
    image_bytes: bytes
    page_num: int
    bbox: Tuple[float, float, float, float]  # (x0, y0, x1, y1)
    image_index: int

class PDFImageExtractor:
    """从 PDF 提取图片"""

    def __init__(self, output_dir: Path):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def extract_images(self, pdf_path: Path) -> List[ExtractedImage]:
        """提取 PDF 中的所有图片"""
        doc = fitz.open(pdf_path)
        extracted_images = []

        for page_num in range(len(doc)):
            page = doc[page_num]
            image_list = page.get_images(full=True)

            for img_index, img in enumerate(image_list):
                xref = img[0]
                base_image = doc.extract_image(xref)
                image_bytes = base_image["image"]

                # 获取图片位置
                img_rects = page.get_image_rects(xref)
                bbox = img_rects[0] if img_rects else (0, 0, 0, 0)

                extracted_images.append(ExtractedImage(
                    image_bytes=image_bytes,
                    page_num=page_num,
                    bbox=bbox,
                    image_index=img_index
                ))

        doc.close()
        return extracted_images

    def save_images(
        self,
        extracted_images: List[ExtractedImage],
        prefix: str = "extracted"
    ) -> List[Path]:
        """保存提取的图片"""
        saved_paths = []

        for idx, img in enumerate(extracted_images):
            filename = f"{prefix}_page{img.page_num}_img{img.image_index}.png"
            output_path = self.output_dir / filename

            with open(output_path, 'wb') as f:
                f.write(img.image_bytes)

            saved_paths.append(output_path)

        return saved_paths
```

#### 1.5 OCR 缓存 (ocr_processor/cache.py)

```python
import pickle
import hashlib
from pathlib import Path
from typing import Optional
from .base import OCRResult

class OCRCache:
    """OCR 结果缓存"""

    def __init__(self, cache_dir: Path):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _get_cache_path(self, image_hash: str) -> Path:
        """获取缓存文件路径"""
        # 使用哈希的前两个字符作为子目录，避免单个目录文件过多
        subdir = self.cache_dir / image_hash[:2]
        subdir.mkdir(exist_ok=True)
        return subdir / f"{image_hash}.pkl"

    def get(self, image_hash: str) -> Optional[OCRResult]:
        """获取缓存结果"""
        cache_path = self._get_cache_path(image_hash)
        if cache_path.exists():
            try:
                with open(cache_path, 'rb') as f:
                    return pickle.load(f)
            except Exception as e:
                print(f"缓存读取失败: {e}")
                return None
        return None

    def set(self, image_hash: str, result: OCRResult):
        """缓存结果"""
        cache_path = self._get_cache_path(image_hash)
        try:
            with open(cache_path, 'wb') as f:
                pickle.dump(result, f)
        except Exception as e:
            print(f"缓存写入失败: {e}")

    def clear(self):
        """清空缓存"""
        import shutil
        if self.cache_dir.exists():
            shutil.rmtree(self.cache_dir)
            self.cache_dir.mkdir(parents=True, exist_ok=True)

    def get_cache_size(self) -> int:
        """获取缓存大小（字节）"""
        total_size = 0
        for path in self.cache_dir.rglob('*'):
            if path.is_file():
                total_size += path.stat().st_size
        return total_size
```

### 2. DocumentLoader 扩展

#### 扩展 document_loader.py

```python
from pathlib import Path
from typing import List, Optional
from llama_index.core.schema import Document

# 新增 OCR 处理器导入
from ocr_processor.paddle_ocr import PaddleOCREngine
from ocr_processor.tesseract_ocr import TesseractOCREngine
from ocr_processor.image_extractor import PDFImageExtractor

class DocumentLoader:
    """统一文档加载器（扩展版）"""

    # 扩展支持的文件类型
    READERS = {
        # ... 现有格式 ...
        ".pdf": PDFReader,
        # ... 现有格式 ...

        # 新增图片格式
        ".png": "ocr",
        ".jpg": "ocr",
        ".jpeg": "ocr",
        ".gif": "ocr",
        ".bmp": "ocr",
        ".tiff": "ocr",
    }

    def __init__(self, data_dir: Path = DATA_DIR, ocr_config: Optional[Dict] = None):
        self.data_dir = data_dir
        self.data_dir.mkdir(exist_ok=True)

        # 初始化 OCR 引擎
        self.ocr_config = ocr_config or {}
        self.ocr_engine = self._init_ocr_engine()
        self.pdf_image_extractor = PDFImageExtractor(INDEX_DIR / "extracted_images")

    def _init_ocr_engine(self):
        """初始化 OCR 引擎"""
        engine_type = self.ocr_config.get('engine', 'paddle')

        if engine_type == 'paddle':
            return PaddleOCREngine(self.ocr_config)
        elif engine_type == 'tesseract':
            return TesseractOCREngine(self.ocr_config)
        else:
            raise ValueError(f"不支持的 OCR 引擎: {engine_type}")

    def load_file(self, file_path: Path, enable_ocr: bool = True) -> List[Document]:
        """加载单个文件（扩展版）"""
        file_path = Path(file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"文件不存在: {file_path}")

        suffix = file_path.suffix.lower()

        # 图片格式：使用 OCR 处理
        if suffix in ['.png', '.jpg', '.jpeg', '.gif', '.bmp', '.tiff']:
            if enable_ocr and self.ocr_engine:
                return self._load_image_with_ocr(file_path)
            else:
                # 如果未启用 OCR，作为二进制文件处理
                return self._load_image_as_binary(file_path)

        # PDF 格式：提取文本 + 图片 OCR
        if suffix == '.pdf':
            return self._load_pdf_with_ocr(file_path, enable_ocr)

        # 其他格式：使用原有逻辑
        reader_class = self.READERS.get(suffix)
        if reader_class is None:
            print(f"⚠️  不支持的文件类型: {suffix}，尝试用文本方式读取")
            reader_class = FlatReader

        try:
            reader = reader_class()
            documents = reader.load_data(file_path)

            # 添加元数据
            for doc in documents:
                doc.metadata.update({
                    "file_name": file_path.name,
                    "file_path": str(file_path),
                    "file_type": suffix,
                    "source": str(file_path),
                })

            print(f"✅ 已加载: {file_path.name} ({len(documents)} 个片段)")
            return documents

        except Exception as e:
            print(f"❌ 加载失败: {file_path.name} - {e}")
            return []

    def _load_image_with_ocr(self, image_path: Path) -> List[Document]:
        """使用 OCR 加载图片"""
        print(f"🔍 正在进行 OCR 识别: {image_path.name}")

        try:
            # OCR 识别
            ocr_results = self.ocr_engine.recognize_image(image_path)

            # 合并识别结果
            text = "\n".join([result.text for result in ocr_results])
            avg_confidence = sum([r.confidence for r in ocr_results]) / len(ocr_results) if ocr_results else 0

            # 创建文档
            document = Document(
                text=text,
                metadata={
                    "file_name": image_path.name,
                    "file_path": str(image_path),
                    "file_type": image_path.suffix.lower(),
                    "source": str(image_path),
                    "ocr_processed": True,
                    "ocr_confidence": avg_confidence,
                    "ocr_engine": self.ocr_config.get('engine', 'unknown'),
                }
            )

            print(f"✅ OCR 完成: {image_path.name} (置信度: {avg_confidence:.2f})")
            return [document]

        except Exception as e:
            print(f"❌ OCR 失败: {image_path.name} - {e}")
            return []

    def _load_pdf_with_ocr(self, pdf_path: Path, enable_ocr: bool) -> List[Document]:
        """加载 PDF 并进行图片 OCR"""
        print(f"📄 正在加载 PDF: {pdf_path.name}")

        all_documents = []

        # 1. 使用原有方式提取文本
        try:
            reader = PDFReader()
            text_documents = reader.load_data(pdf_path)

            for doc in text_documents:
                doc.metadata.update({
                    "file_name": pdf_path.name,
                    "file_path": str(pdf_path),
                    "file_type": ".pdf",
                    "source": str(pdf_path),
                })

            all_documents.extend(text_documents)
            print(f"✅ PDF 文本提取完成: {len(text_documents)} 个片段")

        except Exception as e:
            print(f"⚠️  PDF 文本提取失败: {e}")

        # 2. 提取并 OCR 图片
        if enable_ocr and self.ocr_engine:
            try:
                extracted_images = self.pdf_image_extractor.extract_images(pdf_path)

                if extracted_images:
                    print(f"🖼️  发现 {len(extracted_images)} 张图片，正在进行 OCR...")

                    # 保存图片
                    image_paths = self.pdf_image_extractor.save_images(
                        extracted_images,
                        prefix=pdf_path.stem
                    )

                    # 批量 OCR
                    ocr_results_batch = self.ocr_engine.recognize_batch(image_paths)

                    # 为每张图片创建文档
                    for img_path, ocr_results in zip(image_paths, ocr_results_batch):
                        if ocr_results:
                            text = "\n".join([r.text for r in ocr_results])
                            avg_confidence = sum([r.confidence for r in ocr_results]) / len(ocr_results)

                            document = Document(
                                text=text,
                                metadata={
                                    "file_name": pdf_path.name,
                                    "file_path": str(pdf_path),
                                    "file_type": ".pdf",
                                    "source": str(pdf_path),
                                    "ocr_processed": True,
                                    "ocr_confidence": avg_confidence,
                                    "ocr_from_image": True,
                                    "image_path": str(img_path),
                                }
                            )
                            all_documents.append(document)

                    print(f"✅ PDF 图片 OCR 完成: {len(image_paths)} 张图片")

            except Exception as e:
                print(f"⚠️  PDF 图片 OCR 失败: {e}")

        return all_documents

    def _load_image_as_binary(self, image_path: Path) -> List[Document]:
        """将图片作为二进制文件加载（未启用 OCR 时）"""
        with open(image_path, 'rb') as f:
            binary_data = f.read()

        document = Document(
            text=f"[二进制图片文件: {image_path.name}, 大小: {len(binary_data)} 字节]",
            metadata={
                "file_name": image_path.name,
                "file_path": str(image_path),
                "file_type": image_path.suffix.lower(),
                "source": str(image_path),
                "binary": True,
            }
        )

        return [document]
```

## 数据流设计

### OCR 处理流程

```
用户请求加载文档
        │
        ▼
DocumentLoader.load_file()
        │
        ▼
┌───────────────────┐
│ 文件类型检测      │
└───────────────────┘
        │
   ┌────┴────┬─────────┬─────────┐
   │         │         │         │
   ▼         ▼         ▼         ▼
PDF      图片      Markdown   其他
   │         │         │         │
   │         ▼         │         ▼
   │    OCR识别      │    原有逻辑
   │         │         │
   ▼         │         │
提取文本     │         │
   │         │         │
   ▼         │         │
提取图片     │         │
   │         │         │
   └────┬────┘         │
        │              │
        ▼              │
   保存临时图片       │
        │              │
        ▼              │
   批量OCR识别        │
        │              │
        ▼              │
   合并结果           │
        │              │
        └──────┬───────┘
               │
               ▼
        返回 Document 列表
               │
               ▼
        添加到知识库
```

### 缓存策略

```
图片文件
    │
    ▼
计算 MD5 哈希
    │
    ▼
┌───────────────┐
│ 检查缓存      │
└───────────────┘
    │
    ├─ 命中 ──→ 返回缓存结果
    │
    └─ 未命中 ──→ 执行 OCR
                      │
                      ▼
                 保存到缓存
                      │
                      ▼
                 返回结果
```

## 配置管理

### config.py 扩展

```python
# ==================== OCR 配置 ====================
OCR_ENABLED = os.getenv("OCR_ENABLED", "true").lower() == "true"
OCR_ENGINE = os.getenv("OCR_ENGINE", "paddle")  # paddle | tesseract | hybrid
OCR_CACHE_DIR = INDEX_DIR / "ocr_cache"
OCR_PARALLEL_WORKERS = int(os.getenv("OCR_PARALLEL_WORKERS", "2"))
OCR_TIMEOUT = int(os.getenv("OCR_TIMEOUT", "60"))
OCR_MIN_CONFIDENCE = float(os.getenv("OCR_MIN_CONFIDENCE", "0.6"))

# PaddleOCR 配置
PADDLE_USE_GPU = os.getenv("PADDLE_USE_GPU", "false").lower() == "true"
PADDLE_LANG = os.getenv("PADDLE_LANG", "ch")  # ch | en | jk
PADDLE_USE_ANGLE_CLS = os.getenv("PADDLE_USE_ANGLE_CLS", "true").lower() == "true"

# Tesseract 配置
TESSERACT_PATH = os.getenv("TESSERACT_PATH", "/usr/local/bin/tesseract")
TESSERACT_LANG = os.getenv("TESSERACT_LANG", "chi_sim+eng")
TESSERACT_CONFIG = os.getenv("TESSERACT_CONFIG", "--psm 6")

# PDF 图片提取配置
PDF_EXTRACT_IMAGES = os.getenv("PDF_EXTRACT_IMAGES", "true").lower() == "true"
PDF_IMAGE_MIN_SIZE = int(os.getenv("PDF_IMAGE_MIN_SIZE", "100"))  # 最小图片尺寸（像素）
```

## 错误处理

### 错误分类

1. **OCR 引擎错误**
   - 引擎未安装
   - 模型下载失败
   - GPU 不可用

2. **图像处理错误**
   - 图片格式不支持
   - 图片损坏
   - 内存不足

3. **PDF 提取错误**
   - PDF 加密
   - PDF 损坏
   - 图片提取失败

### 错误处理策略

```python
class OCRError(Exception):
    """OCR 错误基类"""
    pass

class OCREngineNotAvailableError(OCRError):
    """OCR 引擎不可用"""
    pass

class ImageProcessingError(OCRError):
    """图像处理错误"""
    pass

class PDFExtractionError(OCRError):
    """PDF 提取错误"""
    pass

def safe_ocr_recognize(ocr_engine, image_path, fallback_engine=None):
    """安全的 OCR 识别，带降级策略"""
    try:
        return ocr_engine.recognize_image(image_path)
    except Exception as e:
        print(f"主 OCR 引擎失败: {e}")

        # 尝试备用引擎
        if fallback_engine:
            try:
                print("尝试备用 OCR 引擎...")
                return fallback_engine.recognize_image(image_path)
            except Exception as e2:
                print(f"备用 OCR 引擎也失败: {e2}")

        # 返回空结果
        return []
```

## 性能优化

### 1. 并行处理

```python
from concurrent.futures import ThreadPoolExecutor, as_completed

def parallel_ocr(images: List[Path], max_workers: int = 2):
    """并行 OCR 处理"""
    results = {}
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_img = {
            executor.submit(ocr_engine.recognize_image, img): img
            for img in images
        }

        for future in as_completed(future_to_img):
            img = future_to_img[future]
            try:
                results[img] = future.result()
            except Exception as e:
                print(f"处理失败 {img}: {e}")
                results[img] = None

    return results
```

### 2. 内存管理

```python
def process_large_pdf(pdf_path: Path, batch_size: int = 10):
    """分批处理大 PDF"""
    doc = fitz.open(pdf_path)
    total_pages = len(doc)

    for start in range(0, total_pages, batch_size):
        end = min(start + batch_size, total_pages)
        print(f"处理页码 {start+1}-{end}")

        # 处理当前批次
        for page_num in range(start, end):
            # 处理单页
            pass

        # 手动触发垃圾回收
        import gc
        gc.collect()

    doc.close()
```

### 3. 进度监控

```python
from tqdm import tqdm

def ocr_with_progress(images: List[Path]):
    """带进度条的 OCR 处理"""
    results = []
    for img in tqdm(images, desc="OCR 处理"):
        result = ocr_engine.recognize_image(img)
        results.append(result)
    return results
```

## 测试策略

参见 TESTING.md
