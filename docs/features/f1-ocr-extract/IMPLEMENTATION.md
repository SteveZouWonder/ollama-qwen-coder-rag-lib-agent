# OCR 功能实现指南

## 实施步骤

### Phase 1: 环境准备

#### 1.1 安装依赖

```bash
# 创建 OCR 虚拟环境（推荐）
python -m venv venv_ocr
source venv_ocr/bin/activate  # Linux/macOS
# venv_ocr\Scripts\activate  # Windows

# 安装核心依赖
pip install paddlepaddle==2.5.2  # CPU 版本
# pip install paddlepaddle-gpu==2.5.2  # GPU 版本（如需要）
pip install paddleocr==2.7.0.3
pip install pytesseract==0.3.10
pip install pymupdf==1.23.8
pip install pillow==10.1.0
pip install opencv-python==4.8.1.78

# 安装 Tesseract（系统级）
# macOS
brew install tesseract tesseract-lang

# Linux (Ubuntu/Debian)
sudo apt-get install tesseract-ocr tesseract-ocr-chi-sim tesseract-ocr-chi-tra

# Windows
# 下载安装程序：https://github.com/UB-Mannheim/tesseract/wiki
```

#### 1.2 验证安装

```python
# 验证 PaddleOCR
from paddleocr import PaddleOCR
ocr = PaddleOCR(use_angle_cls=True, lang="ch")
print("✅ PaddleOCR 安装成功")

# 验证 Tesseract
import pytesseract
print(pytesseract.get_tesseract_version())
print("✅ Tesseract 安装成功")

# 验证 PyMuPDF
import fitz
print(fitz.__version__)
print("✅ PyMuPDF 安装成功")
```

#### 1.3 创建 OCR 模块目录

```bash
mkdir -p ocr_processor
touch ocr_processor/__init__.py
```

### Phase 2: 实现 OCR 核心模块

#### 2.1 实现基类 (ocr_processor/base.py)

```python
"""
OCR 引擎抽象基类
"""
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from pathlib import Path

@dataclass
class OCRResult:
    """OCR 识别结果"""
    text: str
    confidence: float
    bbox: Optional[Tuple[int, int, int, int]] = None
    language: Optional[str] = None
    page_num: Optional[int] = None
    image_hash: Optional[str] = None

class BaseOCREngine(ABC):
    """OCR 引擎抽象基类"""

    def __init__(self, config: Dict):
        self.config = config
        from .cache import OCRCache
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

    def get_cached_result(self, image_hash: str) -> Optional[OCRResult]:
        """获取缓存结果"""
        return self.cache.get(image_hash)

    def cache_result(self, image_hash: str, result: OCRResult):
        """缓存结果"""
        self.cache.set(image_hash, result)
```

#### 2.2 实现 PaddleOCR (ocr_processor/paddle_ocr.py)

```python
"""
PaddleOCR 引擎实现
"""
from paddleocr import PaddleOCR
from .base import BaseOCREngine, OCRResult
import cv2
import numpy as np
from pathlib import Path
from typing import List, Dict
import hashlib

class PaddleOCREngine(BaseOCREngine):
    """PaddleOCR 引擎实现"""

    def __init__(self, config: Dict):
        super().__init__(config)
        self.use_gpu = config.get('use_gpu', False)
        self.lang = config.get('lang', 'ch')

        # 初始化 PaddleOCR
        self.ocr = PaddleOCR(
            use_angle_cls=True,
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
                image_hash=image_hash
            ))

        # 缓存第一个结果
        if ocr_results:
            self.cache_result(image_hash, ocr_results[0])

        return ocr_results

    def _preprocess_image(self, image_path: Path) -> np.ndarray:
        """图像预处理"""
        img = cv2.imread(str(image_path))

        if img is None:
            raise ValueError(f"无法读取图片: {image_path}")

        # 转换为灰度图
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        # 去噪
        denoised = cv2.fastNlMeansDenoising(gray, h=10)

        # 二值化
        _, binary = cv2.threshold(
            denoised, 0, 255,
            cv2.THRESH_BINARY + cv2.THRESH_OTSU
        )

        return binary

    def _compute_hash(self, image_path: Path) -> str:
        """计算图片哈希"""
        with open(image_path, 'rb') as f:
            return hashlib.md5(f.read()).hexdigest()

    def _normalize_bbox(self, bbox: List) -> Tuple[int, int, int, int]:
        """标准化边界框坐标"""
        x_coords = [point[0] for point in bbox]
        y_coords = [point[1] for point in bbox]
        return (
            int(min(x_coords)),
            int(min(y_coords)),
            int(max(x_coords)),
            int(max(y_coords))
        )

    def recognize_batch(
        self,
        image_paths: List[Path],
        parallel: bool = True
    ) -> List[List[OCRResult]]:
        """批量识别"""
        if parallel:
            from concurrent.futures import ThreadPoolExecutor
            max_workers = self.config.get('parallel_workers', 2)
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                return list(executor.map(self.recognize_image, image_paths))
        else:
            return [self.recognize_image(path) for path in image_paths]
```

#### 2.3 实现缓存 (ocr_processor/cache.py)

```python
"""
OCR 结果缓存
"""
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
```

#### 2.4 实现图片提取器 (ocr_processor/image_extractor.py)

```python
"""
PDF 图片提取器
"""
import fitz
from typing import List, Tuple
from pathlib import Path
from dataclasses import dataclass

@dataclass
class ExtractedImage:
    """提取的图片"""
    image_bytes: bytes
    page_num: int
    bbox: Tuple[float, float, float, float]
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

### Phase 3: 扩展 DocumentLoader

#### 3.1 修改 document_loader.py

在现有 `DocumentLoader` 类中添加 OCR 支持：

```python
# 在文件开头添加导入
from typing import Dict, Optional
from .ocr_processor.paddle_ocr import PaddleOCREngine

class DocumentLoader:
    """统一文档加载器（扩展 OCR 支持）"""

    # 扩展支持的文件类型
    READERS = {
        # ... 现有格式 ...
        ".pdf": PDFReader,
        # ... 现有格式 ...

        # 新增图片格式
        ".png": "ocr",
        ".jpg": "ocr",
        ".jpeg": "ocr",
    }

    def __init__(self, data_dir: Path = DATA_DIR, ocr_config: Optional[Dict] = None):
        self.data_dir = data_dir
        self.data_dir.mkdir(exist_ok=True)

        # 初始化 OCR 引擎
        self.ocr_config = ocr_config or {}
        self.ocr_engine = None
        if self.ocr_config.get('enabled', False):
            try:
                self.ocr_engine = PaddleOCREngine(self.ocr_config)
                print("✅ OCR 引擎初始化成功")
            except Exception as e:
                print(f"⚠️  OCR 引擎初始化失败: {e}")

    def load_file(self, file_path: Path, enable_ocr: bool = True) -> List[Document]:
        """加载单个文件（扩展版）"""
        file_path = Path(file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"文件不存在: {file_path}")

        suffix = file_path.suffix.lower()

        # 图片格式：使用 OCR 处理
        if suffix in ['.png', '.jpg', '.jpeg']:
            if enable_ocr and self.ocr_engine:
                return self._load_image_with_ocr(file_path)

        # 其他格式：使用原有逻辑
        # ... 保持原有代码 ...

    def _load_image_with_ocr(self, image_path: Path) -> List[Document]:
        """使用 OCR 加载图片"""
        print(f"🔍 正在进行 OCR 识别: {image_path.name}")

        try:
            # OCR 识别
            ocr_results = self.ocr_engine.recognize_image(image_path)

            if not ocr_results:
                print(f"⚠️  OCR 未识别到文字: {image_path.name}")
                return []

            # 合并识别结果
            text = "\n".join([result.text for result in ocr_results])
            avg_confidence = sum([r.confidence for r in ocr_results]) / len(ocr_results)

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
                }
            )

            print(f"✅ OCR 完成: {image_path.name} (置信度: {avg_confidence:.2f})")
            return [document]

        except Exception as e:
            print(f"❌ OCR 失败: {image_path.name} - {e}")
            return []
```

### Phase 4: 扩展配置

#### 4.1 修改 config.py

```python
# ==================== OCR 配置 ====================
OCR_ENABLED = os.getenv("OCR_ENABLED", "true").lower() == "true"
OCR_ENGINE = os.getenv("OCR_ENGINE", "paddle")
OCR_CACHE_DIR = INDEX_DIR / "ocr_cache"
OCR_PARALLEL_WORKERS = int(os.getenv("OCR_PARALLEL_WORKERS", "2"))

# PaddleOCR 配置
PADDLE_USE_GPU = os.getenv("PADDLE_USE_GPU", "false").lower() == "true"
PADDLE_LANG = os.getenv("PADDLE_LANG", "ch")
```

### Phase 5: 添加单元测试

#### 5.1 创建测试文件 (tests/test_ocr_processor.py)

```python
"""
OCR 处理器单元测试
"""
import pytest
from pathlib import Path
from ocr_processor.paddle_ocr import PaddleOCREngine
from ocr_processor import OCRCache


class TestPaddleOCREngine:
    """PaddleOCR 引擎测试"""

    @pytest.fixture
    def ocr_config(self):
        return {
            'use_gpu': False,
            'lang': 'ch',
            'cache_dir': '/tmp/test_ocr_cache',
            'parallel_workers': 1
        }

    @pytest.fixture
    def ocr_engine(self, ocr_config):
        return PaddleOCREngine(ocr_config)

    def test_recognize_image(self, ocr_engine, tmp_path):
        """测试图片识别"""
        # 创建测试图片
        from PIL import Image, ImageDraw, ImageFont
        img = Image.new('RGB', (200, 100), color='white')
        draw = ImageDraw.Draw(img)
        draw.text((10, 10), "测试文本", fill='black')

        test_image = tmp_path / "test.png"
        img.save(test_image)

        # OCR 识别
        results = ocr_engine.recognize_image(test_image)

        assert len(results) > 0
        assert results[0].text
        assert results[0].confidence > 0

    def test_cache(self, ocr_config):
        """测试缓存功能"""
        cache = OCRCache(Path(ocr_config['cache_dir']))

        # 测试缓存写入
        from ocr_processor import OCRResult
        result = OCRResult(text="test", confidence=0.9)
        cache.set("test_hash", result)

        # 测试缓存读取
        cached = cache.get("test_hash")
        assert cached is not None
        assert cached.text == "test"

        # 清理
        cache.clear()
```

### Phase 6: 集成测试

#### 6.1 创建集成测试 (tests/test_ocr_integration.py)

```python
"""
OCR 集成测试
"""
import pytest
from pathlib import Path
from document_loader import DocumentLoader

class TestOCRIntegration:
    """OCR 集成测试"""

    @pytest.fixture
    def ocr_config(self):
        return {
            'enabled': True,
            'use_gpu': False,
            'lang': 'ch',
            'cache_dir': '/tmp/test_ocr_cache',
            'parallel_workers': 1
        }

    @pytest.fixture
    def loader(self, ocr_config):
        return DocumentLoader(ocr_config=ocr_config)

    def test_load_image_with_ocr(self, loader, tmp_path):
        """测试加载图片并进行 OCR"""
        # 创建测试图片
        from PIL import Image, ImageDraw
        img = Image.new('RGB', (200, 100), color='white')
        draw = ImageDraw.Draw(img)
        draw.text((10, 10), "这是一段测试文本", fill='black')

        test_image = tmp_path / "test.png"
        img.save(test_image)

        # 加载图片
        documents = loader.load_file(test_image, enable_ocr=True)

        assert len(documents) == 1
        assert documents[0].metadata['ocr_processed'] == True
        assert "测试文本" in documents[0].text

    def test_load_pdf_with_ocr(self, loader, tmp_path):
        """测试加载 PDF 并进行图片 OCR"""
        # 创建包含图片的测试 PDF
        # （此处需要实际 PDF 文件或使用 PyMuPDF 创建）
        pass
```

### Phase 7: 性能优化

#### 7.1 添加进度条

```python
from tqdm import tqdm

def recognize_batch_with_progress(self, image_paths: List[Path]) -> List[List[OCRResult]]:
    """带进度条的批量识别"""
    results = []
    for img in tqdm(image_paths, desc="OCR 处理"):
        result = self.recognize_image(img)
        results.append(result)
    return results
```

#### 7.2 添加内存监控

```python
import psutil

def check_memory_usage():
    """检查内存使用情况"""
    process = psutil.Process()
    mem_info = process.memory_info()
    print(f"内存使用: {mem_info.rss / 1024 / 1024:.2f} MB")

    if mem_info.rss > 2 * 1024 * 1024 * 1024:  # 2GB
        print("⚠️  内存使用超过 2GB，建议分批处理")
```

### Phase 8: 文档和部署

#### 8.1 更新 README.md

在 README.md 中添加 OCR 功能说明：

```markdown
## OCR 图片识别功能

### 功能特性
- 支持扫描版 PDF OCR
- 支持图片文件（PNG、JPG）识别
- 智能缓存避免重复处理
- 中英文混合识别

### 使用方法

```bash
# 启用 OCR 功能
export OCR_ENABLED=true
export OCR_ENGINE=paddle

# 加载包含图片的文档
python query_interface.py --data ./data --enable-ocr
```

### 安装 OCR 依赖

```bash
# 安装 Python 依赖
pip install paddlepaddle paddleocr pymupdf

# 安装 Tesseract（系统级）
brew install tesseract  # macOS
sudo apt-get install tesseract-ocr  # Linux
```
```

#### 8.2 创建安装脚本

创建 `install_ocr_deps.sh`:

```bash
#!/bin/bash
set -e

echo "安装 OCR 依赖..."

# 检测操作系统
if [[ "$OSTYPE" == "darwin"* ]]; then
    # macOS
    if ! command -v brew &> /dev/null; then
        echo "请先安装 Homebrew"
        exit 1
    fi
    brew install tesseract
elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
    # Linux
    sudo apt-get update
    sudo apt-get install -y tesseract-ocr tesseract-ocr-chi-sim
else
    echo "不支持的操作系统"
    exit 1
fi

# 安装 Python 依赖
pip install paddlepaddle==2.5.2
pip install paddleocr==2.7.0.3
pip install pymupdf==1.23.8
pip install opencv-python==4.8.1.78

echo "✅ OCR 依赖安装完成"
```

## 验收标准

### 功能验收
- [ ] 能够识别 PNG/JPG 图片中的中文文本
- [ ] 能够从 PDF 中提取图片并进行 OCR
- [ ] OCR 结果能够正确缓存
- [ ] 置信度低于阈值时给出警告

### 性能验收
- [ ] 单张图片 OCR 处理时间 <3 秒
- [ ] 10 页 PDF 图片 OCR 处理时间 <30 秒
- [ ] 缓存命中时处理时间 <0.1 秒

### 兼容性验收
- [ ] 与现有 DocumentLoader 100% 兼容
- [ ] 不影响非 OCR 文档的处理
- [ ] OCR 功能可独立开关

## 常见问题

### Q1: PaddleOCR 模型下载失败
**A**: 手动下载模型并放置到 `~/.paddleocr/` 目录，或设置代理。

### Q2: Tesseract 未找到
**A**: 确保 Tesseract 已安装并添加到 PATH，或通过 `TESSERACT_PATH` 指定路径。

### Q3: GPU 不可用
**A**: 确保 CUDA 驱动已安装，或使用 CPU 版本（默认）。

### Q4: 内存不足
**A**: 减少并行工作线程数，或分批处理大文件。

## 下一步

- [ ] 添加表格识别支持
- [ ] 实现手写文字识别
- [ ] 集成多模态模型（Qwen2-VL）
- [ ] 添加 OCR 结果人工校正界面
