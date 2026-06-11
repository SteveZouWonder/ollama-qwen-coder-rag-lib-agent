"""
DocumentLoader OCR 集成测试
"""
import pytest
import io
from pathlib import Path
from PIL import Image, ImageDraw
from unittest.mock import Mock, patch

from document_loader import DocumentLoader
from ocr_processor.base import OCRResult


class TestDocumentLoaderOCR:
    """DocumentLoader OCR 集成测试"""
    
    @pytest.fixture
    def data_dir(self, tmp_path):
        """创建临时数据目录"""
        return tmp_path / "data"
    
    @pytest.fixture
    def sample_image(self, tmp_path):
        """创建测试图片文件"""
        img = Image.new('RGB', (400, 200), color='white')
        draw = ImageDraw.Draw(img)
        draw.text((20, 20), "Test Text", fill='black')
        
        image_path = tmp_path / "test_image.png"
        img.save(image_path)
        return image_path
    
    @pytest.fixture
    def sample_pdf(self, tmp_path):
        """创建测试 PDF 文件"""
        try:
            import fitz
        except ImportError:
            pytest.skip("PyMuPDF not installed")
        
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((50, 50), "Test PDF content", fontsize=12)
        
        pdf_path = tmp_path / "test.pdf"
        doc.save(pdf_path)
        doc.close()
        
        return pdf_path
    
    def test_loader_initialization_without_ocr(self, data_dir):
        """测试不启用 OCR 的加载器初始化"""
        loader = DocumentLoader(data_dir, enable_ocr=False)
        
        assert loader.enable_ocr == False
        assert loader.ocr_engine is None
    
    def test_loader_initialization_with_ocr_disabled(self, data_dir):
        """测试 OCR 功能禁用时的初始化"""
        with patch('document_loader.OCR_ENABLED', False):
            loader = DocumentLoader(data_dir)
            
            assert loader.enable_ocr == False
    
    def test_loader_load_image_without_ocr(self, data_dir, sample_image):
        """测试不启用 OCR 时加载图片"""
        loader = DocumentLoader(data_dir, enable_ocr=False)
        
        documents = loader.load_file(sample_image, enable_ocr=False)
        
        # 应该返回空列表（图片文件需要 OCR）
        assert len(documents) == 0
    
    def test_loader_load_image_with_mock_ocr(self, data_dir, sample_image):
        """测试使用模拟 OCR 加载图片"""
        loader = DocumentLoader(data_dir, enable_ocr=True)
        
        # 模拟 OCR 引擎
        mock_ocr = Mock()
        mock_ocr.recognize_image.return_value = [
            OCRResult(
                text="模拟识别的文本",
                confidence=0.95,
                bbox=(0, 0, 100, 50),
                language="ch"
            )
        ]
        loader.ocr_engine = mock_ocr
        
        documents = loader.load_file(sample_image, enable_ocr=True)
        
        assert len(documents) == 1
        assert "模拟识别的文本" in documents[0].text
        assert documents[0].metadata['ocr_enabled'] == True
        assert documents[0].metadata['file_type'] == '.png'
    
    def test_loader_load_pdf_without_ocr(self, data_dir, sample_pdf):
        """测试不启用 OCR 时加载 PDF"""
        loader = DocumentLoader(data_dir, enable_ocr=False)
        
        documents = loader.load_file(sample_pdf, enable_ocr=False)
        
        assert len(documents) > 0
        # 应该只包含文本内容
        assert all('ocr_enabled' not in doc.metadata or not doc.metadata.get('ocr_enabled') for doc in documents)
    
    def test_loader_load_pdf_with_mock_ocr(self, data_dir, sample_pdf):
        """测试使用模拟 OCR 加载 PDF"""
        loader = DocumentLoader(data_dir, enable_ocr=True)
        
        # 模拟 OCR 引擎和图片提取器
        mock_ocr = Mock()
        mock_ocr.recognize_image.return_value = [
            OCRResult(
                text="PDF 图片识别结果",
                confidence=0.9,
                bbox=(0, 0, 100, 50),
                language="ch"
            )
        ]
        loader.ocr_engine = mock_ocr
        
        mock_extractor = Mock()
        mock_extractor.extract_images.return_value = []
        loader.pdf_image_extractor = mock_extractor
        
        documents = loader.load_file(sample_pdf, enable_ocr=True)
        
        # 应该包含普通文档内容
        assert len(documents) > 0
    
    def test_loader_should_enable_ocr(self, data_dir):
        """测试 OCR 启用判断逻辑"""
        # 测试禁用 OCR 的加载器
        loader = DocumentLoader(data_dir, enable_ocr=False)
        assert loader.enable_ocr == False
        assert loader._should_enable_ocr(None) == False
        assert loader._should_enable_ocr(True) == True  # 显式启用
        assert loader._should_enable_ocr(False) == False
        
        # 测试启用 OCR 的加载器（如果依赖可用）
        loader2 = DocumentLoader(data_dir, enable_ocr=True)
        # 如果 OCR 依赖未安装，enable_ocr 会被自动设为 False
        if loader2.ocr_engine is not None:
            assert loader2.enable_ocr == True
            assert loader2._should_enable_ocr(None) == True
        else:
            assert loader2.enable_ocr == False  # 依赖不可用，自动禁用
            assert loader2._should_enable_ocr(None) == False
    
    def test_loader_image_types(self):
        """测试图片文件类型判断"""
        from document_loader import DocumentLoader
        
        assert ".png" in DocumentLoader.IMAGE_TYPES
        assert ".jpg" in DocumentLoader.IMAGE_TYPES
        assert ".jpeg" in DocumentLoader.IMAGE_TYPES
        assert ".gif" in DocumentLoader.IMAGE_TYPES
        assert ".bmp" in DocumentLoader.IMAGE_TYPES
    
    def test_loader_load_text_file_unchanged(self, data_dir, tmp_path):
        """测试加载文本文件（不应受 OCR 影响）"""
        # 创建文本文件
        text_file = tmp_path / "test.txt"
        text_file.write_text("This is a test text file")
        
        loader = DocumentLoader(data_dir, enable_ocr=True)
        documents = loader.load_file(text_file)
        
        assert len(documents) > 0
        assert "test text file" in documents[0].text.lower()
    
    def test_loader_load_markdown_file_unchanged(self, data_dir, tmp_path):
        """测试加载 Markdown 文件（不应受 OCR 影响）"""
        # 创建 Markdown 文件
        md_file = tmp_path / "test.md"
        md_file.write_text("# Test Header\n\nThis is test content")
        
        loader = DocumentLoader(data_dir, enable_ocr=True)
        documents = loader.load_file(md_file)
        
        assert len(documents) > 0
        assert "Test Header" in documents[0].text
    
    def test_loader_image_file_with_ocr_disabled(self, data_dir, sample_image):
        """测试禁用 OCR 时加载图片文件"""
        loader = DocumentLoader(data_dir, enable_ocr=False)
        documents = loader.load_file(sample_image)
        
        # 应该返回空列表（图片需要 OCR 才能处理）
        assert len(documents) == 0
    
    def test_loader_with_nonexistent_file(self, data_dir):
        """测试加载不存在的文件"""
        loader = DocumentLoader(data_dir, enable_ocr=True)
        
        with pytest.raises(FileNotFoundError):
            loader.load_file(data_dir / "nonexistent.png")
    
    def test_loader_image_formats_supported(self, data_dir):
        """测试支持的图片格式"""
        from document_loader import DocumentLoader
        
        supported_formats = DocumentLoader.IMAGE_TYPES
        
        # 验证常见格式
        assert ".png" in supported_formats
        assert ".jpg" in supported_formats
        assert ".jpeg" in supported_formats
        assert ".gif" in supported_formats
        assert ".bmp" in supported_formats
        assert ".tiff" in supported_formats
        assert ".tif" in supported_formats
    
    def test_loader_image_file_with_ocr_error(self, data_dir, sample_image):
        """测试 OCR 出错时的处理"""
        loader = DocumentLoader(data_dir, enable_ocr=True)
        
        # 模拟 OCR 引擎抛出异常
        mock_ocr = Mock()
        mock_ocr.recognize_image.side_effect = Exception("OCR failed")
        loader.ocr_engine = mock_ocr
        
        documents = loader.load_file(sample_image, enable_ocr=True)
        
        # 应该返回空列表（OCR 失败）
        assert len(documents) == 0
    
    def test_loader_image_file_without_ocr_engine(self, data_dir, sample_image):
        """测试没有 OCR 引擎时加载图片"""
        loader = DocumentLoader(data_dir, enable_ocr=True)
        loader.ocr_engine = None
        
        documents = loader.load_file(sample_image, enable_ocr=True)
        
        # 应该返回空列表（没有 OCR 引擎）
        assert len(documents) == 0
    
    def test_loader_pdf_image_ocr_with_mock_extractor(self, data_dir, sample_pdf):
        """测试 PDF 图片 OCR 模拟"""
        loader = DocumentLoader(data_dir, enable_ocr=True)
        
        # 模拟 OCR 引擎
        mock_ocr = Mock()
        mock_ocr.recognize_image.return_value = [
            OCRResult(
                text="图片文本",
                confidence=0.9,
                bbox=(0, 0, 100, 50),
                language="ch"
            )
        ]
        loader.ocr_engine = mock_ocr
        
        # 模拟图片提取器
        from ocr_processor.image_extractor import ExtractedImage
        import io
        
        img = Image.new('RGB', (100, 50), color='red')
        img_bytes = io.BytesIO()
        img.save(img_bytes, format='PNG')
        
        mock_extracted = ExtractedImage(
            image_bytes=img_bytes.getvalue(),
            page_num=0,
            bbox=(0, 0, 100, 50),
            image_index=0,
            width=100,
            height=50,
            format='png'
        )
        
        mock_extractor = Mock()
        mock_extractor.extract_images.return_value = [mock_extracted]
        loader.pdf_image_extractor = mock_extractor
        
        documents = loader.load_file(sample_pdf, enable_ocr=True)
        
        # 应该包含 OCR 结果
        ocr_docs = [doc for doc in documents if doc.metadata.get('ocr_enabled')]
        assert len(ocr_docs) > 0
    
    def test_loader_pdf_image_ocr_error_handling(self, data_dir, sample_pdf):
        """测试 PDF 图片 OCR 错误处理"""
        loader = DocumentLoader(data_dir, enable_ocr=True)
        
        # 模拟 OCR 引擎
        mock_ocr = Mock()
        mock_ocr.recognize_image.return_value = [
            OCRResult(
                text="图片文本",
                confidence=0.9,
                bbox=(0, 0, 100, 50),
                language="ch"
            )
        ]
        loader.ocr_engine = mock_ocr
        
        # 模拟图片提取器抛出异常
        mock_extractor = Mock()
        mock_extractor.extract_images.side_effect = Exception("Extraction failed")
        loader.pdf_image_extractor = mock_extractor
        
        # 不应该抛出异常，应该继续处理
        documents = loader.load_file(sample_pdf, enable_ocr=True)
        
        # 至少应该有普通文本内容
        assert len(documents) > 0
    
    def test_loader_directory_load_ignores_images_without_ocr(self, data_dir, tmp_path):
        """测试目录加载时忽略图片（未启用 OCR）"""
        # 创建图片文件
        img = Image.new('RGB', (100, 50), color='white')
        image_path = tmp_path / "image.png"
        img.save(image_path)
        
        # 创建文本文件
        text_path = tmp_path / "text.txt"
        text_path.write_text("Test content")
        
        loader = DocumentLoader(tmp_path, enable_ocr=False)
        documents = loader.load_directory()
        
        # 应该只加载文本文件
        assert len(documents) > 0
        # 图片应该被忽略
        assert all('.png' not in doc.metadata.get('file_type', '') for doc in documents)
    
    def test_loader_load_specific_types_ignores_images(self, data_dir, tmp_path):
        """测试加载指定类型时忽略图片"""
        # 创建图片文件
        img = Image.new('RGB', (100, 50), color='white')
        image_path = tmp_path / "image.png"
        img.save(image_path)
        
        # 创建文本文件
        text_path = tmp_path / "text.txt"
        text_path.write_text("Test content")
        
        loader = DocumentLoader(tmp_path, enable_ocr=False)
        documents = loader.load_specific_types(tmp_path, [".txt"])
        
        # 应该只加载文本文件
        assert len(documents) > 0
        assert all('.txt' in doc.metadata.get('file_type', '') for doc in documents)
    
    def test_loader_with_mixed_files(self, data_dir, tmp_path):
        """测试加载混合文件类型"""
        # 创建各种文件类型
        img = Image.new('RGB', (100, 50), color='white')
        (tmp_path / "image.png").write_bytes(b"fake")
        (tmp_path / "doc.txt").write_text("Text content")
        (tmp_path / "doc.md").write_text("# Markdown")
        
        loader = DocumentLoader(tmp_path, enable_ocr=False)
        documents = loader.load_directory()
        
        # 应该加载非图片文件
        text_docs = [doc for doc in documents if doc.metadata.get('file_type') in ['.txt', '.md']]
        assert len(text_docs) > 0
    
    def test_loader_pdf_with_mixed_content(self, data_dir, tmp_path):
        """测试包含混合内容的 PDF"""
        try:
            import fitz
        except ImportError:
            pytest.skip("PyMuPDF not installed")
        
        # 创建包含文本和图片的 PDF
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((50, 50), "Text content", fontsize=12)
        
        img = Image.new('RGB', (100, 50), color='red')
        img_bytes = io.BytesIO()
        img.save(img_bytes, format='PNG')
        img_bytes.seek(0)
        page.insert_image(fitz.Rect(50, 100, 150, 150), stream=img_bytes.read())
        
        pdf_path = tmp_path / "mixed.pdf"
        doc.save(pdf_path)
        doc.close()
        
        loader = DocumentLoader(tmp_path, enable_ocr=False)
        documents = loader.load_file(pdf_path)
        
        # 应该至少有文本内容
        assert len(documents) > 0
    
    def test_loader_ocr_initialization_failure_handling(self, data_dir):
        """测试 OCR 初始化失败的处理"""
        # 模拟 OCR 初始化失败
        loader = DocumentLoader(data_dir, enable_ocr=True)
        
        # 如果依赖不可用，应该自动禁用 OCR
        if loader.ocr_engine is None:
            assert loader.enable_ocr == False
        else:
            assert loader.enable_ocr == True
    
    def test_load_file_with_enable_ocr_override(self, data_dir, tmp_path):
        """测试使用 enable_ocr 参数覆盖"""
        img = Image.new('RGB', (100, 50), color='white')
        image_path = tmp_path / "image.png"
        img.save(image_path)
        
        # 创建禁用 OCR 的加载器
        loader = DocumentLoader(data_dir, enable_ocr=False)
        
        # 使用参数覆盖启用 OCR（如果可用）
        if loader.ocr_engine is not None:
            documents = loader.load_file(image_path, enable_ocr=True)
            # 应该尝试 OCR
        else:
            documents = loader.load_file(image_path, enable_ocr=True)
            # OCR 不可用，应该返回空
            assert len(documents) == 0
    
    def test_load_file_ocr_metadata(self, data_dir, tmp_path):
        """测试 OCR 文档的元数据"""
        loader = DocumentLoader(data_dir, enable_ocr=True)
        
        # 模拟 OCR 引擎
        mock_ocr = Mock()
        mock_ocr.recognize_image.return_value = [
            OCRResult(
                text="Test",
                confidence=0.95,
                bbox=(0, 0, 100, 50),
                language="en"
            )
        ]
        loader.ocr_engine = mock_ocr
        
        img = Image.new('RGB', (100, 50), color='white')
        image_path = tmp_path / "image.png"
        img.save(image_path)
        
        documents = loader.load_file(image_path, enable_ocr=True)
        
        if documents:
            doc = documents[0]
            assert 'ocr_enabled' in doc.metadata
            assert 'ocr_engine' in doc.metadata
            assert 'ocr_confidence' in doc.metadata
            assert 'file_type' in doc.metadata
