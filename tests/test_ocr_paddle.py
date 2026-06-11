"""
PaddleOCR 引擎单元测试
"""
import pytest
from pathlib import Path
from PIL import Image, ImageDraw

# Skip tests if PaddleOCR is not installed
pytest.importorskip("paddleocr", reason="PaddleOCR not installed")

from ocr_processor.paddle_ocr import PaddleOCREngine


class TestPaddleOCREngine:
    """PaddleOCR 引擎测试"""
    
    @pytest.fixture
    def ocr_config(self, tmp_path):
        """创建 OCR 配置"""
        return {
            'use_gpu': False,
            'lang': 'ch',
            'use_angle_cls': True,
            'show_log': False,
            'cache_dir': tmp_path / "cache",
            'parallel_workers': 1,
            'preprocess': False  # Disable preprocessing for faster testing
        }
    
    @pytest.fixture
    def ocr_engine(self, ocr_config):
        """创建 PaddleOCR 引擎实例"""
        return PaddleOCREngine(ocr_config)
    
    @pytest.fixture
    def sample_image(self, tmp_path):
        """创建测试图片"""
        img = Image.new('RGB', (400, 200), color='white')
        draw = ImageDraw.Draw(img)
        draw.text((20, 20), "测试文本", fill='black')
        
        image_path = tmp_path / "test.png"
        img.save(image_path)
        return image_path
    
    @pytest.fixture
    def sample_image_english(self, tmp_path):
        """创建英文测试图片"""
        img = Image.new('RGB', (400, 200), color='white')
        draw = ImageDraw.Draw(img)
        draw.text((20, 20), "Test Text", fill='black')
        
        image_path = tmp_path / "test_english.png"
        img.save(image_path)
        return image_path
    
    def test_engine_initialization(self, ocr_config):
        """测试引擎初始化"""
        engine = PaddleOCREngine(ocr_config)
        
        assert engine.use_gpu == False
        assert engine.lang == 'ch'
        assert engine.use_angle_cls == True
        assert engine.ocr is not None
    
    def test_engine_initialization_with_gpu(self, ocr_config):
        """测试 GPU 模式初始化"""
        ocr_config['use_gpu'] = True
        # Note: This may fail if GPU is not available, but we're just testing configuration
        try:
            engine = PaddleOCREngine(ocr_config)
            assert engine.use_gpu == True
        except Exception:
            # GPU initialization may fail, which is expected without GPU
            pytest.skip("GPU not available")
    
    def test_recognize_chinese_text(self, ocr_engine, sample_image):
        """测试中文文本识别"""
        results = ocr_engine.recognize_image(sample_image)
        
        assert len(results) > 0
        assert all(r.text for r in results)
        assert all(r.confidence > 0 for r in results)
        assert all(r.language == 'ch' for r in results)
    
    def test_recognize_empty_image(self, ocr_engine, tmp_path):
        """测试空白图片识别"""
        img = Image.new('RGB', (100, 100), color='white')
        image_path = tmp_path / "empty.png"
        img.save(image_path)
        
        results = ocr_engine.recognize_image(image_path)
        # 空图片可能返回空结果或非常少的结果
        assert isinstance(results, list)
    
    def test_recognize_corrupted_image(self, ocr_engine, tmp_path):
        """测试损坏图片处理"""
        corrupted_path = tmp_path / "corrupted.png"
        corrupted_path.write_bytes(b"invalid image data")
        
        with pytest.raises(ValueError, match="图片无效"):
            ocr_engine.recognize_image(corrupted_path)
    
    def test_recognize_nonexistent_image(self, ocr_engine):
        """测试不存在的图片"""
        nonexistent_path = Path("/nonexistent/path.png")
        
        with pytest.raises(ValueError, match="图片无效"):
            ocr_engine.recognize_image(nonexistent_path)
    
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
        assert all(isinstance(r, list) for r in results)
    
    def test_batch_recognize_sequential(self, ocr_engine, tmp_path):
        """测试顺序批量识别"""
        images = []
        for i in range(2):
            img = Image.new('RGB', (200, 100), color='white')
            draw = ImageDraw.Draw(img)
            draw.text((10, 10), f"文本{i}", fill='black')
            image_path = tmp_path / f"test_seq{i}.png"
            img.save(image_path)
            images.append(image_path)
        
        results = ocr_engine.recognize_batch(images, parallel=False)
        
        assert len(results) == 2
        assert all(isinstance(r, list) for r in results)
    
    def test_cache_hit(self, ocr_engine, sample_image):
        """测试缓存命中"""
        # 第一次识别
        results1 = ocr_engine.recognize_image(sample_image)
        
        # 第二次识别（应该从缓存读取）
        results2 = ocr_engine.recognize_image(sample_image)
        
        assert len(results1) == len(results2)
        if results1 and results2:
            assert results1[0].text == results2[0].text
    
    def test_detect_language(self, ocr_engine, sample_image):
        """测试语言检测"""
        language = ocr_engine.detect_language(sample_image)
        
        # PaddleOCR 使用配置的语言
        assert language == 'ch'
    
    def test_get_engine_info(self, ocr_engine):
        """测试获取引擎信息"""
        info = ocr_engine.get_engine_info()
        
        assert 'engine_name' in info
        assert 'config' in info
        assert 'use_gpu' in info
        assert 'lang' in info
        assert 'use_angle_cls' in info
        assert info['engine_name'] == 'PaddleOCREngine'
    
    def test_normalize_bbox(self, ocr_engine):
        """测试边界框标准化"""
        bbox = [[10, 20], [110, 20], [110, 70], [10, 70]]
        normalized = ocr_engine._normalize_bbox(bbox)
        
        assert normalized == (10, 20, 110, 70)
        assert all(isinstance(v, int) for v in normalized)
    
    def test_preprocessing_disabled(self, tmp_path):
        """测试禁用预处理"""
        config = {
            'use_gpu': False,
            'lang': 'ch',
            'preprocess': False,
            'cache_dir': tmp_path / "cache"
        }
        engine = PaddleOCREngine(config)
        
        img = Image.new('RGB', (200, 100), color='white')
        draw = ImageDraw.Draw(img)
        draw.text((10, 10), "Test", fill='black')
        image_path = tmp_path / "test_no_preprocess.png"
        img.save(image_path)
        
        results = engine.recognize_image(image_path)
        assert isinstance(results, list)
    
    def test_different_languages(self, tmp_path):
        """测试不同语言配置"""
        # 测试英文
        config_en = {
            'use_gpu': False,
            'lang': 'en',
            'cache_dir': tmp_path / "cache_en"
        }
        engine_en = PaddleOCREngine(config_en)
        assert engine_en.lang == 'en'
    
    def test_parallel_workers_config(self, tmp_path):
        """测试并行工作进程配置"""
        config = {
            'use_gpu': False,
            'lang': 'ch',
            'parallel_workers': 4,
            'cache_dir': tmp_path / "cache"
        }
        engine = PaddleOCREngine(config)
        
        assert engine.config['parallel_workers'] == 4
    
    def test_english_language_recognition(self, tmp_path):
        """测试英文识别"""
        config = {
            'use_gpu': False,
            'lang': 'en',
            'preprocess': False,
            'cache_dir': tmp_path / "cache_en"
        }
        engine = PaddleOCREngine(config)
        
        img = Image.new('RGB', (400, 200), color='white')
        draw = ImageDraw.Draw(img)
        draw.text((20, 20), "Hello World", fill='black')
        image_path = tmp_path / "test_english.png"
        img.save(image_path)
        
        results = engine.recognize_image(image_path)
        assert len(results) > 0
