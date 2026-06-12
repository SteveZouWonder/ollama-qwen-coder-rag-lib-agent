"""
PDF 图片提取器
"""
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional
import io


@dataclass
class ExtractedImage:
    """提取的图片信息"""
    image_bytes: bytes              # 图片字节数据
    page_num: int                   # 页码（从 0 开始）
    bbox: tuple                    # 边界框 (x0, y0, x1, y1)
    image_index: int               # 图片索引（在该页中的位置）
    width: int = 0                 # 图片宽度
    height: int = 0                # 图片高度
    format: str = 'png'            # 图片格式
    
    def save(self, output_path: Path):
        """
        保存图片到文件
        
        Args:
            output_path: 输出文件路径
        """
        from PIL import Image
        
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 从字节数据创建图片
        image = Image.open(io.BytesIO(self.image_bytes))
        
        # 根据扩展名确定格式
        if output_path.suffix:
            format = output_path.suffix[1:].upper()
        else:
            format = self.format
        
        image.save(output_path, format=format)
    
    def to_pil_image(self):
        """
        转换为 PIL Image
        
        Returns:
            PIL Image 对象
        """
        from PIL import Image
        return Image.open(io.BytesIO(self.image_bytes))


class PDFImageExtractor:
    """PDF 图片提取器"""
    
    def __init__(self, output_dir: Optional[Path] = None):
        """
        初始化图片提取器
        
        Args:
            output_dir: 默认输出目录
        """
        self.output_dir = Path(output_dir) if output_dir else None
        
        try:
            import pymupdf as fitz
            self.fitz = fitz
        except ImportError:
            raise ImportError(
                "PyMuPDF 未安装，请运行: pip install pymupdf"
            )
    
    def extract_images(
        self,
        pdf_path: Path,
        min_size: tuple = (50, 50)
    ) -> List[ExtractedImage]:
        """
        从 PDF 提取图片
        
        Args:
            pdf_path: PDF 文件路径
            min_size: 最小图片尺寸 (width, height)，小于此尺寸的图片将被过滤
            
        Returns:
            提取的图片列表
        """
        pdf_path = Path(pdf_path)
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF 文件不存在: {pdf_path}")
        
        extracted_images = []
        
        # 打开 PDF
        doc = self.fitz.open(str(pdf_path))
        
        try:
            # 遍历每一页
            for page_num in range(len(doc)):
                page = doc[page_num]
                
                # 获取页面上的图片
                image_list = page.get_images(full=True)
                
                for image_index, img_info in enumerate(image_list):
                    try:
                        # 提取图片
                        xref = img_info[0]
                        base_image = doc.extract_image(xref)
                        image_bytes = base_image["image"]
                        
                        # 获取图片尺寸
                        width = base_image.get("width", 0)
                        height = base_image.get("height", 0)
                        
                        # 过滤小图片
                        if width < min_size[0] or height < min_size[1]:
                            continue
                        
                        # 获取图片边界框
                        bbox = self._get_image_bbox(page, xref)
                        
                        # 创建 ExtractedImage 对象
                        extracted_image = ExtractedImage(
                            image_bytes=image_bytes,
                            page_num=page_num,
                            bbox=bbox,
                            image_index=image_index,
                            width=width,
                            height=height,
                            format=base_image.get("ext", "png")
                        )
                        
                        extracted_images.append(extracted_image)
                        
                    except Exception as e:
                        print(f"提取图片失败 (页 {page_num}, 图 {image_index}): {e}")
                        continue
        
        finally:
            doc.close()
        
        return extracted_images
    
    def _get_image_bbox(self, page, xref: int) -> tuple:
        """
        获取图片在页面中的边界框
        
        Args:
            page: PyMuPDF 页面对象
            xref: 图片引用
            
        Returns:
            边界框 (x0, y0, x1, y1)
        """
        # 查找图片在页面中的位置
        for item in page.get_images():
            if item[0] == xref:
                # item 格式: (xref, smask, width, height, bpc, colorspace, alt_colorspace, name, filter, bbox)
                # bbox 在最后
                if len(item) > 9:
                    return item[9]
        
        # 如果找不到边界框，返回页面尺寸
        return (0, 0, page.rect.width, page.rect.height)
    
    def save_images(
        self,
        images: List[ExtractedImage],
        output_dir: Optional[Path] = None,
        prefix: str = "image"
    ) -> List[Path]:
        """
        保存提取的图片
        
        Args:
            images: 提取的图片列表
            output_dir: 输出目录，如果为 None 则使用初始化时设置的目录
            prefix: 文件名前缀
            
        Returns:
            保存的图片路径列表
        """
        if output_dir is None:
            if self.output_dir is None:
                raise ValueError("未指定输出目录")
            output_dir = self.output_dir
        
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        saved_paths = []
        
        for i, image in enumerate(images):
            # 生成文件名
            filename = f"{prefix}_page{image.page_num}_img{image.image_index}.{image.format}"
            output_path = output_dir / filename
            
            # 保存图片
            image.save(output_path)
            saved_paths.append(output_path)
        
        return saved_paths
    
    def extract_and_save(
        self,
        pdf_path: Path,
        output_dir: Optional[Path] = None,
        prefix: str = "image",
        min_size: tuple = (50, 50)
    ) -> List[Path]:
        """
        提取并保存图片（便捷方法）
        
        Args:
            pdf_path: PDF 文件路径
            output_dir: 输出目录
            prefix: 文件名前缀
            min_size: 最小图片尺寸
            
        Returns:
            保存的图片路径列表
        """
        # 提取图片
        images = self.extract_images(pdf_path, min_size=min_size)
        
        # 保存图片
        return self.save_images(images, output_dir, prefix)
    
    def get_pdf_image_count(self, pdf_path: Path) -> int:
        """
        获取 PDF 中的图片数量
        
        Args:
            pdf_path: PDF 文件路径
            
        Returns:
            图片数量
        """
        try:
            images = self.extract_images(pdf_path)
            return len(images)
        except Exception:
            return 0
    
    def get_page_image_info(
        self,
        pdf_path: Path,
        page_num: int
    ) -> List[dict]:
        """
        获取指定页的图片信息
        
        Args:
            pdf_path: PDF 文件路径
            page_num: 页码（从 0 开始）
            
        Returns:
            图片信息列表
        """
        images = self.extract_images(pdf_path)
        
        page_images = [
            {
                'page_num': img.page_num,
                'image_index': img.image_index,
                'bbox': img.bbox,
                'width': img.width,
                'height': img.height,
                'format': img.format,
                'size_bytes': len(img.image_bytes),
            }
            for img in images
            if img.page_num == page_num
        ]
        
        return page_images
