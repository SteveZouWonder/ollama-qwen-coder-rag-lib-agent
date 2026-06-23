"""
文档加载器 - 支持 PDF、Markdown、TXT、代码文件等
"""
from pathlib import Path
from typing import List, Optional

from llama_index.core.schema import Document
from llama_index.readers.file import (
    PDFReader,
    MarkdownReader,
    FlatReader,
)

from config import DATA_DIR, OCR_ENABLED, OCR_ENGINE, OCR_CACHE_DIR, OCR_PARALLEL_WORKERS
from config import PADDLE_USE_GPU, PADDLE_LANG, PADDLE_USE_ANGLE_CLS
from config import TESSERACT_PATH, TESSERACT_LANG
from config import OCR_PREPROCESS, OCR_DENOISE, OCR_BINARIZE, OCR_DESKEW, OCR_ENHANCE_CONTRAST
from config import PDF_EXTRACT_IMAGES, PDF_MIN_IMAGE_SIZE
from config import OCR_CACHE_ENABLED, OCR_QUALITY_THRESHOLD, OCR_MAX_IMAGE_SIZE


class DocumentLoader:
    """统一文档加载器"""

    # 支持的文件类型映射
    READERS = {
        ".pdf": PDFReader,
        ".md": MarkdownReader,
        ".markdown": MarkdownReader,
        ".txt": FlatReader,
        ".py": FlatReader,
        ".js": FlatReader,
        ".ts": FlatReader,
        ".java": FlatReader,
        ".cpp": FlatReader,
        ".c": FlatReader,
        ".go": FlatReader,
        ".rs": FlatReader,
        ".html": FlatReader,
        ".json": FlatReader,
        ".yaml": FlatReader,
        ".yml": FlatReader,
        ".xml": FlatReader,
    }
    
    # 图片文件类型（需要 OCR）
    IMAGE_TYPES = {
        ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tiff", ".tif"
    }

    def __init__(self, data_dir: Path = DATA_DIR, enable_ocr: bool = None, enable_validation: bool = True):
        self.data_dir = data_dir
        self.data_dir.mkdir(exist_ok=True)

        # OCR 配置
        self.enable_ocr = enable_ocr if enable_ocr is not None else OCR_ENABLED
        self.enable_validation = enable_validation
        self.ocr_engine = None
        self.pdf_image_extractor = None

        # 文件验证器（延迟加载）
        self.file_validator = None

        if self.enable_ocr:
            self._init_ocr()

        if self.enable_validation:
            self._init_validator()
    
    def _init_ocr(self):
        """初始化 OCR 引擎"""
        try:
            from ocr_processor import (
                PaddleOCREngine, TesseractOCREngine, PDFImageExtractor
            )

            # 根据 OCR_ENGINE 选择引擎
            if OCR_ENGINE == "paddle":
                ocr_config = {
                    'use_gpu': PADDLE_USE_GPU,
                    'lang': PADDLE_LANG,
                    'use_angle_cls': PADDLE_USE_ANGLE_CLS,
                    'show_log': False,
                    'cache_dir': OCR_CACHE_DIR,
                    'parallel_workers': OCR_PARALLEL_WORKERS,
                    'preprocess': OCR_PREPROCESS,
                    'denoise': OCR_DENOISE,
                    'binarize': OCR_BINARIZE,
                    'deskew': OCR_DESKEW,
                    'enhance_contrast': OCR_ENHANCE_CONTRAST,
                }
                self.ocr_engine = PaddleOCREngine(ocr_config)
            elif OCR_ENGINE == "tesseract":
                ocr_config = {
                    'tesseract_path': TESSERACT_PATH,
                    'lang': TESSERACT_LANG,
                    'cache_dir': OCR_CACHE_DIR,
                    'parallel_workers': OCR_PARALLEL_WORKERS,
                    'preprocess': OCR_PREPROCESS,
                    'denoise': OCR_DENOISE,
                    'binarize': OCR_BINARIZE,
                    'deskew': OCR_DESKEW,
                    'enhance_contrast': OCR_ENHANCE_CONTRAST,
                }
                self.ocr_engine = TesseractOCREngine(ocr_config)

            # 初始化 PDF 图片提取器
            if PDF_EXTRACT_IMAGES:
                self.pdf_image_extractor = PDFImageExtractor(output_dir=OCR_CACHE_DIR / "pdf_images")

            print(f"✅ OCR 引擎初始化成功 ({OCR_ENGINE})")

        except ImportError as e:
            print(f"⚠️  OCR 依赖未安装，OCR 功能已禁用: {e}")
            self.enable_ocr = False
        except Exception as e:
            print(f"⚠️  OCR 初始化失败，OCR 功能已禁用: {e}")
            self.enable_ocr = False

    def _init_validator(self):
        """初始化文件验证器"""
        try:
            from file_validator import FileValidator
            self.file_validator = FileValidator()
            print("✅ 文件验证器初始化成功")
        except ImportError as e:
            print(f"⚠️  文件验证器导入失败: {e}")
            self.file_validator = None

    def load_file(self, file_path: Path, enable_ocr: bool = None) -> List[Document]:
        """加载单个文件"""
        file_path = Path(file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"文件不存在: {file_path}")

        # 文件验证
        if self.file_validator:
            is_valid, message = self.file_validator.validate_file(file_path)
            if not is_valid:
                print(f"❌ 文件验证失败: {message}")
                return []

            # 检查总大小限制
            file_size = file_path.stat().st_size
            is_valid, message = self.file_validator.check_total_size(file_size)
            if not is_valid:
                print(f"❌ 文件验证失败: {message}")
                return []

            # 检查文件去重
            is_duplicate, message = self.file_validator.check_duplicate(file_path)
            if is_duplicate:
                print(f"⚠️  {message}，跳过加载")
                return []

            # 注册文件
            self.file_validator.register_file(file_path, file_size)

        suffix = file_path.suffix.lower()

        # 处理图片文件（需要 OCR）
        if suffix in self.IMAGE_TYPES:
            return self._load_image_file(file_path, enable_ocr)

        # 处理普通文件
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

            # 如果是 PDF 且启用了 OCR，提取图片并进行 OCR
            if suffix == ".pdf" and self._should_enable_ocr(enable_ocr):
                ocr_documents = self._process_pdf_ocr(file_path)
                documents.extend(ocr_documents)

            print(f"✅ 已加载: {file_path.name} ({len(documents)} 个片段)")
            return documents

        except Exception as e:
            print(f"❌ 加载失败: {file_path.name} - {e}")
            # 如果加载失败，取消文件注册
            if self.file_validator:
                self.file_validator.unregister_file(file_path)
            return []
    
    def _should_enable_ocr(self, enable_ocr: bool) -> bool:
        """判断是否启用 OCR"""
        if enable_ocr is not None:
            return enable_ocr
        return self.enable_ocr
    
    def _load_image_file(self, image_path: Path, enable_ocr: bool = None) -> List[Document]:
        """
        加载图片文件并进行 OCR 识别

        Args:
            image_path: 图片文件路径
            enable_ocr: 是否启用 OCR

        Returns:
            文档列表
        """
        if not self._should_enable_ocr(enable_ocr):
            print(f"⚠️  OCR 未启用，跳过图片文件: {image_path.name}")
            return []

        if self.ocr_engine is None:
            print(f"⚠️  OCR 引擎未初始化，跳过图片文件: {image_path.name}")
            return []

        # 检查图片大小限制
        file_size = image_path.stat().st_size
        if file_size > OCR_MAX_IMAGE_SIZE:
            print(f"⚠️  图片过大，跳过OCR: {image_path.name} ({self._format_size(file_size)} > {self._format_size(OCR_MAX_IMAGE_SIZE)})")
            return []

        # 检查图片质量
        quality_score = self._assess_image_quality(image_path)
        if quality_score < OCR_QUALITY_THRESHOLD:
            print(f"⚠️  图片质量过低，跳过OCR: {image_path.name} (质量: {quality_score:.2f} < {OCR_QUALITY_THRESHOLD})")
            return []

        try:
            # 检查缓存
            if OCR_CACHE_ENABLED:
                cached_result = self._check_ocr_cache(image_path)
                if cached_result:
                    print(f"✅ 使用OCR缓存: {image_path.name}")
                    return cached_result

            # 进行 OCR 识别
            ocr_results = self.ocr_engine.recognize_image(image_path)

            if not ocr_results:
                print(f"⚠️  图片 OCR 识别无结果: {image_path.name}")
                return []

            # 合并所有识别结果
            combined_text = "\n".join([result.text for result in ocr_results])

            # 创建文档
            document = Document(
                text=combined_text,
                metadata={
                    "file_name": image_path.name,
                    "file_path": str(image_path),
                    "file_type": image_path.suffix.lower(),
                    "source": str(image_path),
                    "ocr_enabled": True,
                    "ocr_engine": OCR_ENGINE,
                    "ocr_confidence": sum(r.confidence for r in ocr_results) / len(ocr_results),
                    "image_quality": quality_score,
                }
            )

            # 缓存OCR结果
            if OCR_CACHE_ENABLED:
                self._save_ocr_cache(image_path, [document])

            print(f"✅ 已加载图片 (OCR): {image_path.name} ({len(combined_text)} 字符, 质量: {quality_score:.2f})")
            return [document]

        except Exception as e:
            print(f"❌ 图片 OCR 失败: {image_path.name} - {e}")
            return []

    def _assess_image_quality(self, image_path: Path) -> float:
        """评估图片质量"""
        try:
            from PIL import Image
            import numpy as np

            img = Image.open(image_path)
            width, height = img.size

            # 简单的质量评估
            # 1. 分辨率评分
            resolution_score = min(width, height) / 1000
            resolution_score = min(resolution_score, 1.0)

            # 2. 文件大小评分
            file_size = image_path.stat().st_size
            size_score = min(file_size / (1024 * 1024), 1.0)  # 归一化到MB

            # 综合评分
            quality_score = (resolution_score * 0.6 + size_score * 0.4)
            return quality_score

        except Exception as e:
            print(f"图片质量评估失败: {e}")
            return 0.5  # 无法评估时返回中等分数

    def _check_ocr_cache(self, image_path: Path) -> Optional[List[Document]]:
        """检查OCR缓存"""
        try:
            import hashlib
            import json

            # 计算图片哈希
            file_hash = hashlib.md5(image_path.read_bytes(), usedforsecurity=False).hexdigest()
            cache_file = OCR_CACHE_DIR / f"ocr_cache_{file_hash}.json"

            if cache_file.exists():
                with open(cache_file, 'r', encoding='utf-8') as f:
                    cache_data = json.load(f)

                # 检查缓存是否过期
                from datetime import datetime, timedelta
                cache_time = datetime.fromisoformat(cache_data['timestamp'])
                if datetime.now() - cache_time < timedelta(days=30):  # 30天缓存有效期
                    # 重建文档对象
                    document = Document(
                        text=cache_data['text'],
                        metadata=cache_data['metadata']
                    )
                    return [document]

        except Exception as e:
            print(f"OCR缓存检查失败: {e}")

        return None

    def _save_ocr_cache(self, image_path: Path, documents: List[Document]):
        """保存OCR缓存"""
        try:
            import hashlib
            import json
            from datetime import datetime

            # 计算图片哈希
            file_hash = hashlib.md5(image_path.read_bytes(), usedforsecurity=False).hexdigest()
            cache_file = OCR_CACHE_DIR / f"ocr_cache_{file_hash}.json"

            if len(documents) > 0:
                cache_data = {
                    'timestamp': datetime.now().isoformat(),
                    'text': documents[0].text,
                    'metadata': documents[0].metadata
                }

                with open(cache_file, 'w', encoding='utf-8') as f:
                    json.dump(cache_data, f, ensure_ascii=False, indent=2)

        except Exception as e:
            print(f"OCR缓存保存失败: {e}")

    @staticmethod
    def _format_size(size_bytes: int) -> str:
        """格式化文件大小"""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.2f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.2f} TB"
    
    def _process_pdf_ocr(self, pdf_path: Path) -> List[Document]:
        """
        处理 PDF 中的图片 OCR
        
        Args:
            pdf_path: PDF 文件路径
            
        Returns:
            OCR 识别的文档列表
        """
        if self.pdf_image_extractor is None or self.ocr_engine is None:
            return []
        
        documents = []
        
        try:
            # 提取 PDF 中的图片
            extracted_images = self.pdf_image_extractor.extract_images(
                pdf_path,
                min_size=PDF_MIN_IMAGE_SIZE
            )
            
            if not extracted_images:
                return documents
            
            print(f"📷 从 PDF 提取到 {len(extracted_images)} 张图片")
            
            # 对每张图片进行 OCR
            for i, extracted_image in enumerate(extracted_images):
                try:
                    # 保存临时图片文件
                    import tempfile
                    with tempfile.NamedTemporaryFile(
                        suffix=f".{extracted_image.format}",
                        delete=False
                    ) as tmp_file:
                        tmp_path = Path(tmp_file.name)
                        extracted_image.save(tmp_path)
                    
                    # 进行 OCR 识别
                    ocr_results = self.ocr_engine.recognize_image(tmp_path)
                    
                    # 删除临时文件
                    tmp_path.unlink()
                    
                    if not ocr_results:
                        continue
                    
                    # 合并识别结果
                    combined_text = "\n".join([result.text for result in ocr_results])
                    
                    # 创建文档
                    document = Document(
                        text=combined_text,
                        metadata={
                            "file_name": pdf_path.name,
                            "file_path": str(pdf_path),
                            "file_type": ".pdf",
                            "source": str(pdf_path),
                            "ocr_enabled": True,
                            "ocr_engine": OCR_ENGINE,
                            "page_num": extracted_image.page_num,
                            "image_index": extracted_image.image_index,
                            "image_bbox": extracted_image.bbox,
                            "ocr_confidence": sum(r.confidence for r in ocr_results) / len(ocr_results),
                        }
                    )
                    
                    documents.append(document)
                    
                except Exception as e:
                    print(f"⚠️  图片 {i+1} OCR 失败: {e}")
                    continue
            
            print(f"✅ PDF 图片 OCR 完成: {len(documents)} 个识别结果")
            
        except Exception as e:
            print(f"❌ PDF 图片提取失败: {e}")
        
        return documents

    def load_directory(
        self,
        directory: Optional[Path] = None,
        recursive: bool = True,
    ) -> List[Document]:
        """加载整个目录"""
        directory = directory or self.data_dir
        directory = Path(directory)

        if not directory.exists():
            raise FileNotFoundError(f"目录不存在: {directory}")

        all_documents = []
        pattern = "**/*" if recursive else "*"

        for file_path in directory.glob(pattern):
            if file_path.is_file() and file_path.suffix.lower() in self.READERS:
                docs = self.load_file(file_path)
                all_documents.extend(docs)

        print(f"\n📚 总计加载: {len(all_documents)} 个文档片段")
        return all_documents

    def load_specific_types(
        self,
        directory: Path,
        extensions: List[str],
        recursive: bool = True,
    ) -> List[Document]:
        """加载指定类型的文件"""
        all_documents = []
        pattern = "**/*" if recursive else "*"

        for ext in extensions:
            if not ext.startswith("."):
                ext = f".{ext}"
            for file_path in directory.glob(pattern):
                if file_path.is_file() and file_path.suffix.lower() == ext.lower():
                    docs = self.load_file(file_path)
                    all_documents.extend(docs)

        return all_documents


def load_documents(
    path: Optional[str] = None,
    file_types: Optional[List[str]] = None,
) -> List[Document]:
    """
    便捷函数：加载文档
    
    Args:
        path: 文件或目录路径，默认使用 DATA_DIR
        file_types: 指定文件类型，如 [".pdf", ".md"]
    """
    loader = DocumentLoader()
    target_path = Path(path) if path else DATA_DIR

    if target_path.is_file():
        return loader.load_file(target_path)
    elif target_path.is_dir():
        if file_types:
            return loader.load_specific_types(target_path, file_types)
        return loader.load_directory(target_path)
    else:
        raise ValueError(f"路径不存在: {target_path}")
