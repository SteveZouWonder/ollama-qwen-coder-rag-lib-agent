"""
OCR 基类单元测试
"""
import pytest
from pathlib import Path
from PIL import Image, ImageDraw
from abc import ABC

from ocr_processor.base import BaseOCREngine, OCRResult


class MockOCREngine(BaseOCREngine):
    """用于测试的 OCR 引擎模拟实现"""
    
    def recognize_image(self, image_path: Path, preprocess: bool = True):
        """模拟识别图片"""
        if not self.validate_image(image_path):
            raise ValueError("图片无效")
        
        # 返回模拟结果
        return [
            OCRResult(
                text="模拟识别结果",
                confidence=0.9,
                bbox=(0, 0, 100, 50),
                language="ch"
            )
        ]
    
    def recognize_batch(self, image_paths, parallel: bool = True):
        """模拟批量识别"""
        return [self.recognize_image(path) for path in image_paths]
    
    def detect_language(self, image_path: Path):
        """模拟语言检测"""
        return "ch"


class TestOCRResult:
    """OCRResult 数据类测试"""
    
    def test_ocr_result_creation(self):
        """测试 OCRResult 创建"""
        result = OCRResult(
            text="测试文本",
            confidence=0.95,
            bbox=(0, 0, 100, 50),
            language="ch",
            page_num=0
        )
        
        assert result.text == "测试文本"
        assert result.confidence == 0.95
        assert result.bbox == (0, 0, 100, 50)
        assert result.language == "ch"
        assert result.page_num == 0
    
    def test_ocr_result_with_metadata(self):
        """测试带元数据的 OCRResult"""
        result = OCRResult(
            text="测试",
            confidence=0.9,
            metadata={'key': 'value', 'number': 123}
        )
        
        assert result.metadata == {'key': 'value', 'number': 123}
    
    def test_ocr_result_invalid_confidence_high(self):
        """测试无效的高置信度"""
        with pytest.raises(ValueError, match="置信度必须在 0-1 之间"):
            OCRResult(text="测试", confidence=1.5)
    
    def test_ocr_result_invalid_confidence_low(self):
        """测试无效的低置信度"""
        with pytest.raises(ValueError, match="置信度必须在 0-1 之间"):
            OCRResult(text="测试", confidence=-0.5)
    
    def test_ocr_result_empty_text(self):
        """测试空文本"""
        with pytest.raises(ValueError, match="识别文本不能为空"):
            OCRResult(text="", confidence=0.9)
    
    def test_ocr_result_defaults(self):
        """测试默认值"""
        result = OCRResult(text="测试", confidence=0.9)
        
        assert result.bbox is None
        assert result.language is None
        assert result.page_num is None
        assert result.image_hash is None
        assert result.metadata == {}


class TestBaseOCREngine:
    """OCR 基类测试"""
    
    @pytest.fixture
    def engine_config(self, tmp_path):
        """创建引擎配置"""
        return {
            'cache_dir': tmp_path / "cache",
            'parallel_workers': 2
        }
    
    @pytest.fixture
    def mock_engine(self, engine_config):
        """创建模拟 OCR 引擎"""
        return MockOCREngine(engine_config)
    
    @pytest.fixture
    def sample_image(self, tmp_path):
        """创建测试图片"""
        img = Image.new('RGB', (400, 200), color='white')
        draw = ImageDraw.Draw(img)
        draw.text((20, 20), "Test Text", fill='black')
        
        image_path = tmp_path / "test.png"
        img.save(image_path)
        return image_path
    
    def test_engine_initialization(self, engine_config):
        """测试引擎初始化"""
        engine = MockOCREngine(engine_config)
        
        assert engine.config == engine_config
        assert engine._cache is not None
    
    def test_engine_initialization_without_cache(self):
        """测试不使用缓存初始化引擎"""
        engine = MockOCREngine({})
        
        assert engine._cache is None
    
    def test_validate_image_valid(self, mock_engine, sample_image):
        """测试验证有效图片"""
        assert mock_engine.validate_image(sample_image) == True
    
    def test_validate_image_nonexistent(self, mock_engine):
        """测试验证不存在的图片"""
        nonexistent_path = Path("/nonexistent/path.png")
        assert mock_engine.validate_image(nonexistent_path) == False
    
    def test_validate_image_corrupted(self, mock_engine, tmp_path):
        """测试验证损坏的图片"""
        corrupted_path = tmp_path / "corrupted.png"
        corrupted_path.write_bytes(b"invalid image data")
        
        assert mock_engine.validate_image(corrupted_path) == False
    
    def test_compute_image_hash(self, mock_engine, sample_image):
        """测试计算图片哈希"""
        hash1 = mock_engine.compute_image_hash(sample_image)
        hash2 = mock_engine.compute_image_hash(sample_image)
        
        assert hash1 == hash2
        assert len(hash1) == 32  # MD5 哈希长度
        assert isinstance(hash1, str)
    
    def test_compute_image_hash_different_images(self, mock_engine, tmp_path):
        """测试不同图片的哈希值不同"""
        img1 = Image.new('RGB', (100, 100), color='red')
        path1 = tmp_path / "img1.png"
        img1.save(path1)
        
        img2 = Image.new('RGB', (100, 100), color='blue')
        path2 = tmp_path / "img2.png"
        img2.save(path2)
        
        hash1 = mock_engine.compute_image_hash(path1)
        hash2 = mock_engine.compute_image_hash(path2)
        
        assert hash1 != hash2
    
    def test_cache_operations(self, mock_engine, sample_image):
        """测试缓存操作"""
        # 创建测试结果
        result = OCRResult(
            text="测试",
            confidence=0.95,
            bbox=(0, 0, 100, 50)
        )
        
        # 计算哈希
        image_hash = mock_engine.compute_image_hash(sample_image)
        
        # 缓存结果
        mock_engine.cache_result(image_hash, result)
        
        # 获取缓存结果
        cached = mock_engine.get_cached_result(image_hash)
        
        assert cached is not None
        assert cached.text == result.text
        assert cached.confidence == result.confidence
    
    def test_cache_miss(self, mock_engine):
        """测试缓存未命中"""
        result = mock_engine.get_cached_result("nonexistent_hash")
        assert result is None
    
    def test_cache_without_cache_dir(self):
        """测试不使用缓存的情况"""
        engine = MockOCREngine({})
        result = OCRResult(text="测试", confidence=0.9)
        
        # 不应该抛出错误
        engine.cache_result("hash", result)
        cached = engine.get_cached_result("hash")
        
        assert cached is None  # 没有缓存目录，无法缓存
    
    def test_clear_cache(self, mock_engine, sample_image):
        """测试清空缓存"""
        result = OCRResult(text="测试", confidence=0.9)
        image_hash = mock_engine.compute_image_hash(sample_image)
        
        mock_engine.cache_result(image_hash, result)
        assert mock_engine.get_cached_result(image_hash) is not None
        
        mock_engine.clear_cache()
        assert mock_engine.get_cached_result(image_hash) is None
    
    def test_clear_cache_without_cache_dir(self):
        """测试不使用缓存时清空缓存"""
        engine = MockOCREngine({})
        # 不应该抛出错误
        engine.clear_cache()
    
    def test_get_engine_info(self, mock_engine):
        """测试获取引擎信息"""
        info = mock_engine.get_engine_info()
        
        assert 'engine_name' in info
        assert 'config' in info
        assert info['engine_name'] == 'MockOCREngine'
    
    def test_recognize_image(self, mock_engine, sample_image):
        """测试识别图片"""
        results = mock_engine.recognize_image(sample_image)
        
        assert len(results) > 0
        assert all(isinstance(r, OCRResult) for r in results)
    
    def test_recognize_image_invalid(self, mock_engine, tmp_path):
        """测试识别无效图片"""
        invalid_path = tmp_path / "invalid.png"
        invalid_path.write_bytes(b"invalid data")
        
        with pytest.raises(ValueError, match="图片无效"):
            mock_engine.recognize_image(invalid_path)
    
    def test_recognize_batch(self, mock_engine, tmp_path):
        """测试批量识别"""
        # 创建多个测试图片
        images = []
        for i in range(3):
            img = Image.new('RGB', (100, 50), color='white')
            path = tmp_path / f"test{i}.png"
            img.save(path)
            images.append(path)
        
        results = mock_engine.recognize_batch(images)
        
        assert len(results) == 3
        assert all(len(r) > 0 for r in results)
    
    def test_detect_language(self, mock_engine, sample_image):
        """测试语言检测"""
        language = mock_engine.detect_language(sample_image)
        
        assert language == "ch"
    
    def test_abstract_methods(self):
        """测试抽象方法"""
        # 确认 BaseOCREngine 是抽象类
        assert issubclass(BaseOCREngine, ABC)
        
        # 确认无法直接实例化
        with pytest.raises(TypeError):
            BaseOCREngine({})
    
    def test_engine_config_passthrough(self, engine_config):
        """测试配置传递"""
        engine = MockOCREngine(engine_config)
        
        assert engine.config == engine_config
        assert engine.config['parallel_workers'] == 2
    
    def test_cache_directory_creation(self, engine_config):
        """测试缓存目录创建"""
        # 确保缓存目录不存在
        cache_dir = engine_config['cache_dir']
        if cache_dir.exists():
            import shutil
            shutil.rmtree(cache_dir)
        
        engine = MockOCREngine(engine_config)
        
        assert cache_dir.exists()
        assert cache_dir.is_dir()
    
    def test_detect_language_not_implemented(self, engine_config):
        """测试语言检测方法签名"""
        # MockOCREngine 实现了 detect_language，但基类要求它是抽象的
        # 测试实现的签名正确
        engine = MockOCREngine(engine_config)
        assert hasattr(engine, 'detect_language')
        assert callable(engine.detect_language)
    
    def test_recognize_image_preprocess_flag(self, engine_config, sample_image):
        """测试预处理标志"""
        engine = MockOCREngine(engine_config)
        
        # 测试 preprocess=True
        results1 = engine.recognize_image(sample_image, preprocess=True)
        assert isinstance(results1, list)
        
        # 测试 preprocess=False
        results2 = engine.recognize_image(sample_image, preprocess=False)
        assert isinstance(results2, list)
    
    def test_ocr_result_with_all_fields(self):
        """测试包含所有字段的 OCRResult"""
        result = OCRResult(
            text="完整测试",
            confidence=0.88,
            bbox=(10, 20, 110, 120),
            language="en",
            page_num=5,
            image_hash="abc123",
            metadata={'field1': 'value1', 'field2': 123}
        )
        
        assert result.text == "完整测试"
        assert result.confidence == 0.88
        assert result.bbox == (10, 20, 110, 120)
        assert result.language == "en"
        assert result.page_num == 5
        assert result.image_hash == "abc123"
        assert result.metadata == {'field1': 'value1', 'field2': 123}
    
    def test_ocr_result_edge_case_confidence(self):
        """测试边界置信度值"""
        result1 = OCRResult(text="测试", confidence=0.0)
        assert result1.confidence == 0.0
        
        result2 = OCRResult(text="测试", confidence=1.0)
        assert result2.confidence == 1.0
