# OCR 功能测试策略

## 测试目标

确保 OCR 功能的：
- **功能性**：正确识别各种类型的图片和文档
- **准确性**：识别准确率满足要求
- **性能**：处理速度在可接受范围内
- **稳定性**：长时间运行不崩溃
- **兼容性**：与现有系统无冲突

## 测试分层

### 1. 单元测试 (Unit Tests)

#### 测试范围
- OCR 引擎基础功能
- 缓存机制
- 图片提取器
- 图像预处理

#### 测试文件结构
```
tests/
├── test_ocr_processor.py          # OCR 引擎单元测试
├── test_ocr_cache.py              # 缓存单元测试
├── test_image_extractor.py       # 图片提取器测试
└── test_image_preprocessor.py    # 图像预处理测试
```

#### 测试用例

##### test_ocr_processor.py

```python
import pytest
from pathlib import Path
from PIL import Image, ImageDraw
from ocr_processor.paddle_ocr import PaddleOCREngine
from ocr_processor import OCRResult


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

    @pytest.fixture
    def sample_image(self, tmp_path):
        """创建测试图片"""
        img = Image.new('RGB', (400, 200), color='white')
        draw = ImageDraw.Draw(img)
        draw.text((20, 20), "这是测试文本", fill='black')
        image_path = tmp_path / "test.png"
        img.save(image_path)
        return image_path

    def test_recognize_chinese_text(self, ocr_engine, sample_image):
        """测试中文文本识别"""
        results = ocr_engine.recognize_image(sample_image)

        assert len(results) > 0
        assert any("测试" in r.text for r in results)
        assert all(r.confidence > 0 for r in results)

    def test_recognize_empty_image(self, ocr_engine, tmp_path):
        """测试空白图片识别"""
        img = Image.new('RGB', (100, 100), color='white')
        image_path = tmp_path / "empty.png"
        img.save(image_path)

        results = ocr_engine.recognize_image(image_path)
        assert len(results) == 0

    def test_recognize_corrupted_image(self, ocr_engine, tmp_path):
        """测试损坏图片处理"""
        corrupted_path = tmp_path / "corrupted.png"
        corrupted_path.write_bytes(b"invalid image data")

        with pytest.raises(Exception):
            ocr_engine.recognize_image(corrupted_path)

    def test_batch_recognize(self, ocr_engine, tmp_path):
        """测试批量识别"""
        # 创建多个测试图片
        images = []
        for i in range(3):
            img = Image.new('RGB', (200, 100), color='white')
            draw = ImageDraw.Draw(img)
            draw.text((10, 10), f"文本{i}", fill='black')
            image_path = tmp_path / f"test{i}.png"
            img.save(image_path)
            images.append(image_path)

        results = ocr_engine.recognize_batch(images)
        assert len(results) == 3

    def test_cache_hit(self, ocr_engine, sample_image):
        """测试缓存命中"""
        # 第一次识别
        results1 = ocr_engine.recognize_image(sample_image)
        # 第二次识别（应该从缓存读取）
        results2 = ocr_engine.recognize_image(sample_image)

        assert len(results1) == len(results2)
        assert results1[0].text == results2[0].text
```

##### test_ocr_cache.py

```python
import pytest
from pathlib import Path
import pickle
from ocr_processor import OCRCache
from ocr_processor import OCRResult


class TestOCRCache:
    """OCR 缓存测试"""

    @pytest.fixture
    def cache_dir(self, tmp_path):
        return tmp_path / "cache"

    @pytest.fixture
    def cache(self, cache_dir):
        return OCRCache(cache_dir)

    @pytest.fixture
    def sample_result(self):
        return OCRResult(
            text="测试文本",
            confidence=0.95,
            bbox=(0, 0, 100, 50)
        )

    def test_cache_set_and_get(self, cache, sample_result):
        """测试缓存写入和读取"""
        cache.set("test_hash", sample_result)
        retrieved = cache.get("test_hash")

        assert retrieved is not None
        assert retrieved.text == sample_result.text
        assert retrieved.confidence == sample_result.confidence

    def test_cache_miss(self, cache):
        """测试缓存未命中"""
        result = cache.get("nonexistent_hash")
        assert result is None

    def test_cache_clear(self, cache, sample_result):
        """测试缓存清理"""
        cache.set("test_hash", sample_result)
        assert cache.get("test_hash") is not None

        cache.clear()
        assert cache.get("test_hash") is None

    def test_cache_persistence(self, cache_dir, sample_result):
        """测试缓存持久化"""
        cache1 = OCRCache(cache_dir)
        cache1.set("test_hash", sample_result)

        # 重新创建缓存实例
        cache2 = OCRCache(cache_dir)
        retrieved = cache2.get("test_hash")

        assert retrieved is not None
        assert retrieved.text == sample_result.text

    def test_cache_subdir_structure(self, cache_dir, sample_result):
        """测试缓存子目录结构"""
        cache = OCRCache(cache_dir)

        # 写入多个不同哈希的缓存
        for i in range(10):
            hash_value = f"hash_{i:02d}_abcdef"
            cache.set(hash_value, sample_result)

        # 检查子目录是否正确创建
        subdirs = list(cache_dir.iterdir())
        assert len(subdirs) > 0
        assert all(d.is_dir() for d in subdirs)
```

##### test_image_extractor.py

```python
import pytest
from pathlib import Path
from ocr_processor.image_extractor import PDFImageExtractor, ExtractedImage


class TestPDFImageExtractor:
    """PDF 图片提取器测试"""

    @pytest.fixture
    def output_dir(self, tmp_path):
        return tmp_path / "extracted"

    @pytest.fixture
    def extractor(self, output_dir):
        return PDFImageExtractor(output_dir)

    @pytest.fixture
    def sample_pdf(self, tmp_path):
        """创建包含图片的测试 PDF"""
        import fitz

        doc = fitz.open()
        page = doc.new_page()

        # 创建测试图片
        from PIL import Image
        img = Image.new('RGB', (200, 100), color='red')
        img_bytes = io.BytesIO()
        img.save(img_bytes, format='PNG')
        img_bytes.seek(0)

        # 插入图片到 PDF
        page.insert_image(fitz.Rect(50, 50, 250, 150), stream=img_bytes.read())

        pdf_path = tmp_path / "test.pdf"
        doc.save(pdf_path)
        doc.close()

        return pdf_path

    def test_extract_images(self, extractor, sample_pdf):
        """测试图片提取"""
        images = extractor.extract_images(sample_pdf)

        assert len(images) > 0
        assert all(isinstance(img, ExtractedImage) for img in images)
        assert all(img.image_bytes for img in images)

    def test_save_images(self, extractor, tmp_path):
        """测试图片保存"""
        extracted_images = [
            ExtractedImage(
                image_bytes=b"fake image data",
                page_num=0,
                bbox=(0, 0, 100, 100),
                image_index=0
            )
        ]

        saved_paths = extractor.save_images(extracted_images, prefix="test")
        assert len(saved_paths) == 1
        assert all(p.exists() for p in saved_paths)

    def test_extract_empty_pdf(self, extractor, tmp_path):
        """测试空 PDF 提取"""
        import fitz
        doc = fitz.open()
        pdf_path = tmp_path / "empty.pdf"
        doc.save(pdf_path)
        doc.close()

        images = extractor.extract_images(pdf_path)
        assert len(images) == 0
```

### 2. 集成测试 (Integration Tests)

#### 测试范围
- OCR 与 DocumentLoader 集成
- OCR 与 RAG 引擎集成
- 端到端文档处理流程

#### 测试文件
```
tests/
├── test_ocr_integration.py         # OCR 集成测试
└── test_ocr_e2e.py                # 端到端测试
```

##### test_ocr_integration.py

```python
import pytest
from pathlib import Path
from document_loader import DocumentLoader
from PIL import Image, ImageDraw

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

    def test_load_image_file(self, loader, tmp_path):
        """测试加载图片文件"""
        img = Image.new('RGB', (400, 200), color='white')
        draw = ImageDraw.Draw(img)
        draw.text((20, 20), "集成测试文本", fill='black')

        image_path = tmp_path / "test.png"
        img.save(image_path)

        documents = loader.load_file(image_path, enable_ocr=True)

        assert len(documents) == 1
        assert documents[0].metadata['ocr_processed'] == True
        assert "集成测试" in documents[0].text

    def test_load_image_without_ocr(self, loader, tmp_path):
        """测试禁用 OCR 时加载图片"""
        img = Image.new('RGB', (100, 100), color='white')
        image_path = tmp_path / "test.png"
        img.save(image_path)

        documents = loader.load_file(image_path, enable_ocr=False)

        assert len(documents) == 1
        assert documents[0].metadata.get('ocr_processed') != True

    def test_load_mixed_directory(self, loader, tmp_path):
        """测试加载混合类型目录"""
        # 创建图片文件
        img = Image.new('RGB', (100, 100), color='white')
        image_path = tmp_path / "test.png"
        img.save(image_path)

        # 创建文本文件
        text_path = tmp_path / "test.txt"
        text_path.write_text("纯文本文件")

        documents = loader.load_directory(tmp_path)

        assert len(documents) == 2
        ocr_docs = [d for d in documents if d.metadata.get('ocr_processed')]
        assert len(ocr_docs) == 1
```

##### test_ocr_e2e.py

```python
import pytest
from pathlib import Path
from rag_engine import RAGEngine
from document_loader import DocumentLoader

class TestOCRE2E:
    """OCR 端到端测试"""

    @pytest.fixture
    def ocr_config(self):
        return {
            'enabled': True,
            'use_gpu': False,
            'lang': 'ch',
            'cache_dir': '/tmp/test_ocr_cache',
        }

    @pytest.fixture
    def sample_image_doc(self, tmp_path):
        """创建包含图片的测试文档"""
        from PIL import Image, ImageDraw

        img = Image.new('RGB', (400, 200), color='white')
        draw = ImageDraw.Draw(img)
        draw.text((20, 20), "端到端测试：人工智能是计算机科学的一个分支", fill='black')

        image_path = tmp_path / "ai_doc.png"
        img.save(image_path)
        return image_path

    def test_image_to_rag_query(self, sample_image_doc, ocr_config):
        """测试图片 → RAG 索引 → 查询完整流程"""
        # 1. 加载文档
        loader = DocumentLoader(ocr_config=ocr_config)
        documents = loader.load_file(sample_image_doc, enable_ocr=True)

        # 2. 创建索引
        from config import INDEX_DIR
        rag_engine = RAGEngine(documents, index_dir=INDEX_DIR)

        # 3. 查询
        query = "人工智能是什么？"
        results = rag_engine.query(query)

        assert len(results) > 0
        assert "计算机科学" in results[0].text
```

### 3. 性能测试 (Performance Tests)

#### 测试指标
- 单张图片处理时间
- 批量处理吞吐量
- 内存使用情况
- 缓存命中率

#### 测试文件
```
tests/
└── test_ocr_performance.py
```

##### test_ocr_performance.py

```python
import pytest
import time
import psutil
from pathlib import Path
from PIL import Image, ImageDraw
from ocr_processor.paddle_ocr import PaddleOCREngine


class TestOCRPerformance:
    """OCR 性能测试"""

    @pytest.fixture
    def ocr_config(self):
        return {
            'use_gpu': False,
            'lang': 'ch',
            'cache_dir': '/tmp/test_ocr_cache',
        }

    @pytest.fixture
    def ocr_engine(self, ocr_config):
        return PaddleOCREngine(ocr_config)

    @pytest.fixture
    def test_images(self, tmp_path):
        """创建测试图片集"""
        images = []
        for i in range(10):
            img = Image.new('RGB', (800, 600), color='white')
            draw = ImageDraw.Draw(img)
            draw.text((50, 50), f"性能测试文本 {i}", fill='black')
            image_path = tmp_path / f"perf_test_{i}.png"
            img.save(image_path)
            images.append(image_path)
        return images

    def test_single_image_performance(self, ocr_engine, tmp_path):
        """测试单张图片处理性能"""
        img = Image.new('RGB', (800, 600), color='white')
        draw = ImageDraw.Draw(img)
        draw.text((50, 50), "性能测试", fill='black')
        image_path = tmp_path / "perf_test.png"
        img.save(image_path)

        start_time = time.time()
        results = ocr_engine.recognize_image(image_path)
        elapsed = time.time() - start_time

        assert len(results) > 0
        assert elapsed < 5.0, f"单张图片处理时间过长: {elapsed:.2f}s"

    def test_batch_performance(self, ocr_engine, test_images):
        """测试批量处理性能"""
        start_time = time.time()
        results = ocr_engine.recognize_batch(test_images)
        elapsed = time.time() - start_time

        assert len(results) == len(test_images)
        assert elapsed < 30.0, f"批量处理时间过长: {elapsed:.2f}s"

    def test_cache_performance(self, ocr_engine, test_images):
        """测试缓存性能"""
        # 第一次处理（无缓存）
        start_time = time.time()
        ocr_engine.recognize_batch(test_images)
        first_run = time.time() - start_time

        # 第二次处理（有缓存）
        start_time = time.time()
        ocr_engine.recognize_batch(test_images)
        second_run = time.time() - start_time

        # 缓存后应该快很多
        assert second_run < first_run * 0.1, "缓存未生效"

    def test_memory_usage(self, ocr_engine, test_images):
        """测试内存使用"""
        process = psutil.Process()
        initial_mem = process.memory_info().rss

        ocr_engine.recognize_batch(test_images)

        final_mem = process.memory_info().rss
        mem_increase = (final_mem - initial_mem) / 1024 / 1024  # MB

        # 内存增长不应超过 500MB
        assert mem_increase < 500, f"内存增长过大: {mem_increase:.2f}MB"
```

### 4. 准确性测试 (Accuracy Tests)

#### 测试方法
- 使用标准测试集
- 计算字符准确率 (CAR)
- 计算词准确率 (WAR)
- 计算编辑距离

#### 测试文件
```
tests/
└── test_ocr_accuracy.py
```

##### test_ocr_accuracy.py

```python
import pytest
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from ocr_processor.paddle_ocr import PaddleOCREngine


class TestOCRAccuracy:
    """OCR 准确性测试"""

    @pytest.fixture
    def ocr_engine(self):
        config = {
            'use_gpu': False,
            'lang': 'ch',
            'cache_dir': '/tmp/test_ocr_cache',
        }
        return PaddleOCREngine(config)

    def create_test_image(self, text, font_size=20):
        """创建包含指定文本的测试图片"""
        img = Image.new('RGB', (400, 100), color='white')
        draw = ImageDraw.Draw(img)

        try:
            font = ImageFont.truetype("/System/Library/Fonts/PingFang.ttc", font_size)
        except:
            font = ImageFont.load_default()

        draw.text((10, 30), text, fill='black', font=font)
        return img

    def calculate_accuracy(self, expected, actual):
        """计算准确率"""
        import difflib

        matcher = difflib.SequenceMatcher(None, expected, actual)
        return matcher.ratio()

    def test_chinese_accuracy(self, ocr_engine, tmp_path):
        """测试中文识别准确率"""
        test_texts = [
            "人工智能",
            "机器学习",
            "深度学习",
            "神经网络",
            "自然语言处理",
        ]

        total_accuracy = 0
        for text in test_texts:
            img = self.create_test_image(text)
            image_path = tmp_path / f"{text}.png"
            img.save(image_path)

            results = ocr_engine.recognize_image(image_path)
            if results:
                recognized = results[0].text
                accuracy = self.calculate_accuracy(text, recognized)
                total_accuracy += accuracy
                print(f"文本: {text}, 识别: {recognized}, 准确率: {accuracy:.2f}")

        avg_accuracy = total_accuracy / len(test_texts)
        assert avg_accuracy > 0.8, f"中文识别准确率过低: {avg_accuracy:.2f}"

    def test_english_accuracy(self, ocr_engine, tmp_path):
        """测试英文识别准确率"""
        test_texts = [
            "Artificial Intelligence",
            "Machine Learning",
            "Deep Learning",
            "Neural Network",
        ]

        total_accuracy = 0
        for text in test_texts:
            img = self.create_test_image(text)
            image_path = tmp_path / f"{text}.png"
            img.save(image_path)

            results = ocr_engine.recognize_image(image_path)
            if results:
                recognized = results[0].text
                accuracy = self.calculate_accuracy(text, recognized)
                total_accuracy += accuracy

        avg_accuracy = total_accuracy / len(test_texts)
        assert avg_accuracy > 0.9, f"英文识别准确率过低: {avg_accuracy:.2f}"
```

### 5. 稳定性测试 (Stability Tests)

#### 测试内容
- 长时间运行测试
- 大批量文件处理
- 内存泄漏检测
- 错误恢复能力

#### 测试文件
```
tests/
└── test_ocr_stability.py
```

##### test_ocr_stability.py

```python
import pytest
import time
from pathlib import Path
from PIL import Image, ImageDraw
from ocr_processor.paddle_ocr import PaddleOCREngine


class TestOCRStability:
    """OCR 稳定性测试"""

    @pytest.fixture
    def ocr_engine(self):
        config = {
            'use_gpu': False,
            'lang': 'ch',
            'cache_dir': '/tmp/test_ocr_cache',
        }
        return PaddleOCREngine(config)

    def test_long_running_stability(self, ocr_engine, tmp_path):
        """测试长时间运行稳定性"""
        # 创建测试图片
        img = Image.new('RGB', (400, 200), color='white')
        draw = ImageDraw.Draw(img)
        draw.text((20, 20), "稳定性测试", fill='black')
        image_path = tmp_path / "stable_test.png"
        img.save(image_path)

        # 连续处理 100 次
        for i in range(100):
            try:
                results = ocr_engine.recognize_image(image_path)
                assert len(results) > 0
            except Exception as e:
                pytest.fail(f"第 {i} 次处理失败: {e}")

    def test_large_batch_stability(self, ocr_engine, tmp_path):
        """测试大批量处理稳定性"""
        # 创建 50 张测试图片
        images = []
        for i in range(50):
            img = Image.new('RGB', (400, 200), color='white')
            draw = ImageDraw.Draw(img)
            draw.text((20, 20), f"批量测试 {i}", fill='black')
            image_path = tmp_path / f"batch_{i}.png"
            img.save(image_path)
            images.append(image_path)

        # 批量处理
        try:
            results = ocr_engine.recognize_batch(images)
            assert len(results) == 50
        except Exception as e:
            pytest.fail(f"批量处理失败: {e}")
```

## 测试数据准备

### 测试图片集

创建 `tests/fixtures/images/` 目录：

```
tests/fixtures/images/
├── simple_chinese.png       # 简单中文文本
├── simple_english.png       # 简单英文文本
├── mixed_lang.png           # 中英文混合
├── multi_line.png           # 多行文本
├── low_contrast.png         # 低对比度
├── noisy.png               # 噪声图片
├── scanned_paper.png        # 扫描文档
└── sample.pdf              # 包含图片的 PDF
```

### 测试数据生成脚本

创建 `tests/fixtures/generate_test_images.py`:

```python
"""
生成测试图片
"""
from PIL import Image, ImageDraw, ImageFont
from pathlib import Path

def generate_test_images():
    output_dir = Path(__file__).parent / "images"
    output_dir.mkdir(exist_ok=True)

    # 简单中文
    img = Image.new('RGB', (400, 100), color='white')
    draw = ImageDraw.Draw(img)
    draw.text((50, 30), "这是中文测试", fill='black')
    img.save(output_dir / "simple_chinese.png")

    # 简单英文
    img = Image.new('RGB', (400, 100), color='white')
    draw = ImageDraw.Draw(img)
    draw.text((50, 30), "This is English test", fill='black')
    img.save(output_dir / "simple_english.png")

    # 中英文混合
    img = Image.new('RGB', (400, 100), color='white')
    draw = ImageDraw.Draw(img)
    draw.text((50, 30), "这是中English混合测试", fill='black')
    img.save(output_dir / "mixed_lang.png")

    print(f"测试图片已生成到 {output_dir}")

if __name__ == "__main__":
    generate_test_images()
```

## 测试执行

### 运行所有测试

```bash
# 运行所有 OCR 测试
pytest tests/test_ocr*.py -v

# 运行特定类型测试
pytest tests/test_ocr_processor.py -v  # 单元测试
pytest tests/test_ocr_integration.py -v  # 集成测试
pytest tests/test_ocr_performance.py -v  # 性能测试
```

### 运行覆盖率测试

```bash
# 生成覆盖率报告
pytest tests/test_ocr*.py --cov=ocr_processor --cov-report=html
```

### 性能基准测试

```bash
# 运行性能测试并生成报告
pytest tests/test_ocr_performance.py --benchmark-only
```

## 测试报告

### 自动化报告

使用 pytest-html 生成 HTML 报告：

```bash
pytest tests/test_ocr*.py --html=reports/ocr_test_report.html
```

### 持续集成

在 CI/CD 流水线中集成测试：

```yaml
# .github/workflows/ocr_tests.yml
name: OCR Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Set up Python
        uses: actions/setup-python@v2
        with:
          python-version: '3.9'
      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install pytest pytest-cov pytest-html
      - name: Run OCR tests
        run: |
          pytest tests/test_ocr*.py -v --cov=ocr_processor --html=reports/ocr_test_report.html
      - name: Upload test results
        uses: actions/upload-artifact@v2
        with:
          name: test-report
          path: reports/ocr_test_report.html
```

## 测试通过标准

### 功能测试
- [ ] 所有单元测试通过率 100%
- [ ] 所有集成测试通过率 100%
- [ ] 无 P0、P1 级别 bug

### 性能测试
- [ ] 单张图片处理时间 <3 秒
- [ ] 批量处理吞吐量 >10 图片/分钟
- [ ] 内存使用 <500MB

### 准确性测试
- [ ] 中文识别准确率 >90%
- [ ] 英文识别准确率 >95%
- [ ] 中英文混合准确率 >85%

### 稳定性测试
- [ ] 连续处理 1000 张图片无崩溃
- [ ] 长时间运行（1小时）无内存泄漏
- [ ] 错误恢复成功率 >95%

## 问题跟踪

### 测试失败处理

1. **单元测试失败**
   - 检查代码逻辑
   - 验证测试用例正确性
   - 修复后重新测试

2. **性能测试失败**
   - 分析性能瓶颈
   - 优化算法或增加并行度
   - 调整性能目标

3. **准确性测试失败**
   - 检查 OCR 引擎配置
   - 调整预处理参数
   - 考虑切换 OCR 引擎

### 回归测试

每次修改后运行完整测试套件：

```bash
# 快速回归测试（核心功能）
pytest tests/test_ocr_processor.py tests/test_ocr_integration.py -v

# 完整回归测试
pytest tests/test_ocr*.py -v
```

## 测试维护

### 定期更新
- 每月更新测试数据集
- 根据实际使用场景调整测试用例
- 更新性能基准

### 测试优化
- 移除过时的测试用例
- 合并重复的测试
- 提高测试执行效率
