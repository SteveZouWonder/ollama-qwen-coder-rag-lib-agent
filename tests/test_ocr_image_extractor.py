"""
PDF 图片提取器单元测试
"""
import pytest
from pathlib import Path
from PIL import Image
import io

from ocr_processor.image_extractor import PDFImageExtractor, ExtractedImage


class TestPDFImageExtractor:
    """PDF 图片提取器测试"""
    
    @pytest.fixture
    def output_dir(self, tmp_path):
        """创建临时输出目录"""
        return tmp_path / "extracted"
    
    @pytest.fixture
    def extractor(self, output_dir):
        """创建图片提取器实例"""
        return PDFImageExtractor(output_dir)
    
    @pytest.fixture
    def sample_pdf_with_images(self, tmp_path):
        """创建包含图片的测试 PDF"""
        try:
            import pymupdf as fitz
        except ImportError:
            pytest.skip("PyMuPDF not installed")
        
        doc = fitz.open()
        page = doc.new_page()
        
        # 创建测试图片
        img = Image.new('RGB', (200, 100), color='red')
        img_bytes = io.BytesIO()
        img.save(img_bytes, format='PNG')
        img_bytes.seek(0)
        
        # 插入图片到 PDF
        page.insert_image(fitz.Rect(50, 50, 250, 150), stream=img_bytes.read())
        
        # 添加第二页
        page2 = doc.new_page()
        img2 = Image.new('RGB', (150, 80), color='blue')
        img_bytes2 = io.BytesIO()
        img2.save(img_bytes2, format='PNG')
        img_bytes2.seek(0)
        page2.insert_image(fitz.Rect(30, 30, 180, 110), stream=img_bytes2.read())
        
        pdf_path = tmp_path / "test_with_images.pdf"
        doc.save(pdf_path)
        doc.close()
        
        return pdf_path
    
    @pytest.fixture
    def sample_pdf_without_images(self, tmp_path):
        """创建不包含图片的测试 PDF"""
        try:
            import pymupdf as fitz
        except ImportError:
            pytest.skip("PyMuPDF not installed")
        
        doc = fitz.open()
        page = doc.new_page()
        
        # 添加文本
        page.insert_text((50, 50), "This is a test PDF without images", fontsize=12)
        
        pdf_path = tmp_path / "test_without_images.pdf"
        doc.save(pdf_path)
        doc.close()
        
        return pdf_path
    
    @pytest.fixture
    def extracted_image(self):
        """创建测试用的 ExtractedImage 对象"""
        img = Image.new('RGB', (100, 50), color='green')
        img_bytes = io.BytesIO()
        img.save(img_bytes, format='PNG')
        
        return ExtractedImage(
            image_bytes=img_bytes.getvalue(),
            page_num=0,
            bbox=(0, 0, 100, 50),
            image_index=0,
            width=100,
            height=50,
            format='png'
        )
    
    def test_extract_images(self, extractor, sample_pdf_with_images):
        """测试图片提取"""
        images = extractor.extract_images(sample_pdf_with_images)
        
        assert len(images) > 0
        assert all(isinstance(img, ExtractedImage) for img in images)
        assert all(img.image_bytes for img in images)
    
    def test_extract_images_from_pdf_without_images(self, extractor, sample_pdf_without_images):
        """测试从无图片的 PDF 提取图片"""
        images = extractor.extract_images(sample_pdf_without_images)
        
        assert len(images) == 0
    
    def test_extract_images_with_min_size(self, extractor, sample_pdf_with_images):
        """测试使用最小尺寸过滤图片"""
        # 设置较大的最小尺寸，应该过滤掉所有图片
        images = extractor.extract_images(sample_pdf_with_images, min_size=(1000, 1000))
        
        assert len(images) == 0
    
    def test_extract_images_nonexistent_pdf(self, extractor):
        """测试提取不存在的 PDF"""
        nonexistent_path = Path("/nonexistent/path.pdf")
        
        with pytest.raises(FileNotFoundError):
            extractor.extract_images(nonexistent_path)
    
    def test_save_images(self, extractor, tmp_path):
        """测试保存图片"""
        # 创建真实的图片数据
        img = Image.new('RGB', (100, 100), color='red')
        img_bytes = io.BytesIO()
        img.save(img_bytes, format='PNG')
        
        extracted_images = [
            ExtractedImage(
                image_bytes=img_bytes.getvalue(),
                page_num=0,
                bbox=(0, 0, 100, 100),
                image_index=0,
                width=100,
                height=100,
                format='png'
            )
        ]
        
        output_dir = tmp_path / "saved"
        saved_paths = extractor.save_images(extracted_images, output_dir=output_dir, prefix="test")
        
        assert len(saved_paths) == 1
        assert all(p.exists() for p in saved_paths)
    
    def test_save_images_default_output_dir(self, extractor, extracted_image):
        """测试使用默认输出目录保存图片"""
        saved_paths = extractor.save_images([extracted_image], prefix="test")
        
        assert len(saved_paths) == 1
        assert all(p.exists() for p in saved_paths)
        assert extractor.output_dir in saved_paths[0].parents
    
    def test_save_images_with_subdirs(self, extractor, tmp_path, extracted_image):
        """测试保存图片到子目录"""
        output_dir = tmp_path / "subdir1" / "subdir2"
        saved_paths = extractor.save_images([extracted_image], output_dir=output_dir, prefix="test")
        
        assert len(saved_paths) == 1
        assert all(p.exists() for p in saved_paths)
        assert output_dir in saved_paths[0].parents
    
    def test_extract_and_save(self, extractor, sample_pdf_with_images, tmp_path):
        """测试提取并保存图片（便捷方法）"""
        output_dir = tmp_path / "extracted_and_saved"
        saved_paths = extractor.extract_and_save(sample_pdf_with_images, output_dir=output_dir)
        
        assert len(saved_paths) > 0
        assert all(p.exists() for p in saved_paths)
    
    def test_extract_and_save_without_output_dir(self, extractor, sample_pdf_with_images):
        """测试提取并保存图片（使用默认输出目录）"""
        saved_paths = extractor.extract_and_save(sample_pdf_with_images)
        
        assert len(saved_paths) > 0
        assert all(p.exists() for p in saved_paths)
    
    def test_get_pdf_image_count(self, extractor, sample_pdf_with_images, sample_pdf_without_images):
        """测试获取 PDF 图片数量"""
        count_with_images = extractor.get_pdf_image_count(sample_pdf_with_images)
        count_without_images = extractor.get_pdf_image_count(sample_pdf_without_images)
        
        assert count_with_images > 0
        assert count_without_images == 0
    
    def test_get_page_image_info(self, extractor, sample_pdf_with_images):
        """测试获取指定页的图片信息"""
        page_0_info = extractor.get_page_image_info(sample_pdf_with_images, 0)
        page_1_info = extractor.get_page_image_info(sample_pdf_with_images, 1)
        
        assert isinstance(page_0_info, list)
        assert isinstance(page_1_info, list)
        
        # 第一页应该有图片
        assert len(page_0_info) > 0
        
        # 第二页应该有图片
        assert len(page_1_info) > 0
    
    def test_get_page_image_info_nonexistent_page(self, extractor, sample_pdf_with_images):
        """测试获取不存在的页的图片信息"""
        page_info = extractor.get_page_image_info(sample_pdf_with_images, 999)
        
        assert isinstance(page_info, list)
        assert len(page_info) == 0
    
    def test_extracted_image_save(self, extracted_image, tmp_path):
        """测试 ExtractedImage.save 方法"""
        output_path = tmp_path / "saved_image.png"
        
        extracted_image.save(output_path)
        
        assert output_path.exists()
        # 验证保存的图像可以读取
        loaded = Image.open(output_path)
        assert loaded.size == (100, 50)
    
    def test_extracted_image_save_with_subdirs(self, extracted_image, tmp_path):
        """测试 ExtractedImage.save 到子目录"""
        output_path = tmp_path / "subdir" / "saved_image.png"
        
        extracted_image.save(output_path)
        
        assert output_path.exists()
    
    def test_extracted_image_to_pil_image(self, extracted_image):
        """测试 ExtractedImage.to_pil_image 方法"""
        pil_image = extracted_image.to_pil_image()
        
        assert isinstance(pil_image, Image.Image)
        assert pil_image.size == (100, 50)
    
    def test_extracted_image_properties(self, extracted_image):
        """测试 ExtractedImage 属性"""
        assert extracted_image.page_num == 0
        assert extracted_image.image_index == 0
        assert extracted_image.width == 100
        assert extracted_image.height == 50
        assert extracted_image.format == 'png'
        assert extracted_image.bbox == (0, 0, 100, 50)
        assert len(extracted_image.image_bytes) > 0
    
    def test_extractor_initialization_with_none_output_dir(self):
        """测试使用 None 输出目录初始化提取器"""
        extractor = PDFImageExtractor(output_dir=None)
        
        assert extractor.output_dir is None
    
    def test_save_images_without_output_dir_raises_error(self, tmp_path):
        """测试在没有输出目录时保存图片引发错误"""
        extractor = PDFImageExtractor(output_dir=None)
        extracted_image = ExtractedImage(
            image_bytes=b"fake image data",
            page_num=0,
            bbox=(0, 0, 100, 100),
            image_index=0
        )
        
        with pytest.raises(ValueError, match="未指定输出目录"):
            extractor.save_images([extracted_image])
    
    def test_extract_multiple_images_from_pdf(self, sample_pdf_with_images):
        """测试从 PDF 提取多张图片"""
        extractor = PDFImageExtractor()
        images = extractor.extract_images(sample_pdf_with_images)
        
        # 检查是否提取了多张图片
        assert len(images) >= 2
        
        # 检查图片是否来自不同的页
        page_nums = [img.page_num for img in images]
        assert len(set(page_nums)) > 1  # 应该有来自不同页的图片
    
    def test_image_info_structure(self, extractor, sample_pdf_with_images):
        """测试图片信息结构"""
        page_info = extractor.get_page_image_info(sample_pdf_with_images, 0)
        
        for info in page_info:
            assert 'page_num' in info
            assert 'image_index' in info
            assert 'bbox' in info
            assert 'width' in info
            assert 'height' in info
            assert 'format' in info
            assert 'size_bytes' in info
    
    def test_extracted_image_with_different_formats(self, tmp_path):
        """测试不同格式的 ExtractedImage"""
        formats = ['png', 'jpeg', 'bmp']
        
        for fmt in formats:
            img = Image.new('RGB', (50, 50), color='blue')
            img_bytes = io.BytesIO()
            img.save(img_bytes, format=fmt.upper())
            
            extracted_image = ExtractedImage(
                image_bytes=img_bytes.getvalue(),
                page_num=0,
                bbox=(0, 0, 50, 50),
                image_index=0,
                width=50,
                height=50,
                format=fmt
            )
            
            # 测试保存
            output_path = tmp_path / f"test.{fmt}"
            extracted_image.save(output_path)
            assert output_path.exists()
    
    def test_extracted_image_without_width_height(self, tmp_path):
        """测试没有宽高的 ExtractedImage"""
        img = Image.new('RGB', (50, 50), color='green')
        img_bytes = io.BytesIO()
        img.save(img_bytes, format='PNG')
        
        extracted_image = ExtractedImage(
            image_bytes=img_bytes.getvalue(),
            page_num=0,
            bbox=(0, 0, 50, 50),
            image_index=0
        )
        
        # 默认宽高应该为 0
        assert extracted_image.width == 0
        assert extracted_image.height == 0
    
    def test_extracted_image_different_page_numbers(self):
        """测试不同页码的 ExtractedImage"""
        img = Image.new('RGB', (50, 50), color='yellow')
        img_bytes = io.BytesIO()
        img.save(img_bytes, format='PNG')
        
        for page_num in [0, 1, 5, 10, 100]:
            extracted_image = ExtractedImage(
                image_bytes=img_bytes.getvalue(),
                page_num=page_num,
                bbox=(0, 0, 50, 50),
                image_index=0
            )
            assert extracted_image.page_num == page_num
    
    def test_extracted_image_different_bboxes(self):
        """测试不同边界框的 ExtractedImage"""
        img = Image.new('RGB', (100, 100), color='purple')
        img_bytes = io.BytesIO()
        img.save(img_bytes, format='PNG')
        
        bboxes = [
            (0, 0, 100, 100),
            (10, 20, 110, 120),
            (50, 50, 150, 150),
            (0, 0, 50, 50)
        ]
        
        for bbox in bboxes:
            extracted_image = ExtractedImage(
                image_bytes=img_bytes.getvalue(),
                page_num=0,
                bbox=bbox,
                image_index=0
            )
            assert extracted_image.bbox == bbox
    
    def test_extract_images_with_various_sizes(self, tmp_path):
        """测试提取不同大小的图片"""
        try:
            import pymupdf as fitz
        except ImportError:
            pytest.skip("PyMuPDF not installed")
        
        sizes = [(50, 50), (100, 100), (200, 150), (300, 300)]
        
        for size in sizes:
            doc = fitz.open()
            page = doc.new_page()
            
            img = Image.new('RGB', size, color='red')
            img_bytes = io.BytesIO()
            img.save(img_bytes, format='PNG')
            img_bytes.seek(0)
            
            page.insert_image(fitz.Rect(0, 0, size[0], size[1]), stream=img_bytes.read())
            
            pdf_path = tmp_path / f"test_{size[0]}x{size[1]}.pdf"
            doc.save(pdf_path)
            doc.close()
            
            extractor = PDFImageExtractor()
            images = extractor.extract_images(pdf_path, min_size=(10, 10))
            
            assert len(images) > 0
    
    def test_get_image_bbox_edge_cases(self, extractor):
        """测试获取图片边界框的边界情况"""
        # 测试 None 值处理
        try:
            import pymupdf as fitz
            page = extractor.fitz.open().new_page()
            
            # 测试在没有图片的页面上获取边界框
            bbox = extractor._get_image_bbox(page, 999)  # 不存在的 xref
            
            # 应该返回页面边界
            assert bbox is not None
            assert len(bbox) == 4
            
            extractor.fitz.open().close()
        except ImportError:
            pytest.skip("PyMuPDF not installed")
    
    def test_extract_and_save_with_custom_prefix(self, extractor, sample_pdf_with_images, tmp_path):
        """测试使用自定义前缀提取并保存"""
        output_dir = tmp_path / "custom_prefix"
        saved_paths = extractor.extract_and_save(sample_pdf_with_images, output_dir=output_dir, prefix="custom")
        
        assert len(saved_paths) > 0
        assert all("custom" in str(p) for p in saved_paths)
    
    def test_extract_and_save_with_empty_prefix(self, extractor, sample_pdf_with_images, tmp_path):
        """测试使用空前缀提取并保存"""
        output_dir = tmp_path / "empty_prefix"
        saved_paths = extractor.extract_and_save(sample_pdf_with_images, output_dir=output_dir, prefix="")
        
        assert len(saved_paths) > 0
