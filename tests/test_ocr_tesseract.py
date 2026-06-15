"""
Tesseract OCR 引擎单元测试
"""
import pytest
from pathlib import Path
from PIL import Image, ImageDraw

# Skip tests if pytesseract is not installed
pytest.importorskip("pytesseract", reason="pytesseract not installed")

from ocr_processor import TesseractOCREngine


class TestTesseractOCREngine:
    """Tesseract OCR 引擎测试"""
    
    @pytest.fixture
    def ocr_config(self, tmp_path):
        """创建 OCR 配置"""
        return {
            'tesseract_path': None,  # Use system default
            'lang': 'eng',
            'config': '',
            'cache_dir': tmp_path / "cache",
            'parallel_workers': 1,
            'preprocess': False  # Disable preprocessing for faster testing
        }
    
    @pytest.fixture
    def ocr_engine(self, ocr_config):
        """创建 Tesseract OCR 引擎实例"""
        try:
            return TesseractOCREngine(ocr_config)
        except RuntimeError as e:
            pytest.skip(f"Tesseract not available: {e}")
    
    @pytest.fixture
    def sample_image(self, tmp_path):
        """创建测试图片"""
        img = Image.new('RGB', (400, 200), color='white')
        draw = ImageDraw.Draw(img)
        draw.text((20, 20), "Test Text", fill='black')
        
        image_path = tmp_path / "test.png"
        img.save(image_path)
        return image_path
    
    @pytest.fixture
    def sample_image_chinese(self, tmp_path):
        """创建中文测试图片"""
        img = Image.new('RGB', (400, 200), color='white')
        draw = ImageDraw.Draw(img)
        try:
            # Try to use a font that supports Chinese
            from PIL import ImageFont
            font = ImageFont.truetype("/System/Library/Fonts/PingFang.ttc", 20)
            draw.text((20, 20), "测试文本", fill='black', font=font)
        except:
            # Fallback to default font (may not render Chinese correctly)
            draw.text((20, 20), "Test Text", fill='black')
        
        image_path = tmp_path / "test_chinese.png"
        img.save(image_path)
        return image_path
    
    def test_engine_initialization(self, ocr_config):
        """测试引擎初始化"""
        try:
            engine = TesseractOCREngine(ocr_config)
            
            assert engine.lang == 'eng'
            assert engine.tesseract_config == ''
            assert engine._cache is not None
        except RuntimeError as e:
            pytest.skip(f"Tesseract not available: {e}")
    
    def test_engine_initialization_with_custom_path(self, ocr_config, tmp_path):
        """测试使用自定义路径初始化"""
        # Create a fake tesseract path
        fake_path = tmp_path / "fake_tesseract"
        
        ocr_config['tesseract_path'] = str(fake_path)
        
        try:
            engine = TesseractOCREngine(ocr_config)
            assert engine.tesseract_path == str(fake_path)
        except RuntimeError as e:
            # Expected if fake path doesn't work
            pytest.skip(f"Tesseract not available: {e}")
    
    def test_recognize_english_text(self, ocr_engine, sample_image):
        """测试英文文本识别"""
        results = ocr_engine.recognize_image(sample_image)
        
        assert len(results) > 0
        assert all(r.text for r in results)
        assert all(r.confidence >= 0 for r in results)
        assert all(r.confidence <= 1 for r in results)
    
    def test_recognize_empty_image(self, ocr_engine, tmp_path):
        """测试空白图片识别"""
        img = Image.new('RGB', (100, 100), color='white')
        image_path = tmp_path / "empty.png"
        img.save(image_path)
        
        results = ocr_engine.recognize_image(image_path)
        # 空图片可能返回空结果
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
            draw.text((10, 10), f"Text{i}", fill='black')
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
            draw.text((10, 10), f"Text{i}", fill='black')
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
        
        # Tesseract 使用配置的语言
        assert language == 'eng'
    
    def test_get_engine_info(self, ocr_engine):
        """测试获取引擎信息"""
        info = ocr_engine.get_engine_info()
        
        assert 'engine_name' in info
        assert 'config' in info
        assert 'tesseract_path' in info
        assert 'lang' in info
        assert 'version' in info
        assert info['engine_name'] == 'TesseractOCREngine'
    
    def test_chinese_language_config(self, tmp_path):
        """测试中文语言配置"""
        config = {
            'tesseract_path': None,
            'lang': 'chi_sim+eng',
            'cache_dir': tmp_path / "cache"
        }
        
        try:
            engine = TesseractOCREngine(config)
            assert engine.lang == 'chi_sim+eng'
        except RuntimeError as e:
            pytest.skip(f"Tesseract not available: {e}")
    
    def test_preprocessing_disabled(self, tmp_path):
        """测试禁用预处理"""
        config = {
            'tesseract_path': None,
            'lang': 'eng',
            'preprocess': False,
            'cache_dir': tmp_path / "cache"
        }
        
        try:
            engine = TesseractOCREngine(config)
            
            img = Image.new('RGB', (200, 100), color='white')
            draw = ImageDraw.Draw(img)
            draw.text((10, 10), "Test", fill='black')
            image_path = tmp_path / "test_no_preprocess.png"
            img.save(image_path)
            
            results = engine.recognize_image(image_path)
            assert isinstance(results, list)
        except RuntimeError as e:
            pytest.skip(f"Tesseract not available: {e}")
    
    def test_parallel_workers_config(self, tmp_path):
        """测试并行工作进程配置"""
        config = {
            'tesseract_path': None,
            'lang': 'eng',
            'parallel_workers': 4,
            'cache_dir': tmp_path / "cache"
        }
        
        try:
            engine = TesseractOCREngine(config)
            assert engine.config['parallel_workers'] == 4
        except RuntimeError as e:
            pytest.skip(f"Tesseract not available: {e}")
    
    def test_custom_tesseract_config(self, tmp_path):
        """测试自定义 Tesseract 配置"""
        config = {
            'tesseract_path': None,
            'lang': 'eng',
            'config': '--psm 6',
            'cache_dir': tmp_path / "cache"
        }
        
        try:
            engine = TesseractOCREngine(config)
            assert engine.tesseract_config == '--psm 6'
        except RuntimeError as e:
            pytest.skip(f"Tesseract not available: {e}")
    
    def test_result_bbox_format(self, ocr_engine, sample_image):
        """测试结果边界框格式"""
        results = ocr_engine.recognize_image(sample_image)
        
        for result in results:
            if result.bbox:
                assert len(result.bbox) == 4
                assert all(isinstance(v, int) for v in result.bbox)
                # bbox format: (left, top, right, bottom)
                left, top, right, bottom = result.bbox
                assert right >= left
                assert bottom >= top
    
    def test_result_metadata(self, ocr_engine, sample_image):
        """测试结果元数据"""
        results = ocr_engine.recognize_image(sample_image)
        
        for result in results:
            assert 'engine' in result.metadata
            assert result.metadata['engine'] == 'tesseract'
