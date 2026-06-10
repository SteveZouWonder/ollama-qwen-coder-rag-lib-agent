"""
文档加载器 - 支持 PDF、Markdown、TXT、代码文件等
"""
import os
from pathlib import Path
from typing import List, Optional

from llama_index.core.readers.base import BaseReader
from llama_index.core.schema import Document
from llama_index.readers.file import (
    PDFReader,
    MarkdownReader,
    FlatReader,
)

from config import DATA_DIR


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

    def __init__(self, data_dir: Path = DATA_DIR):
        self.data_dir = data_dir
        self.data_dir.mkdir(exist_ok=True)

    def load_file(self, file_path: Path) -> List[Document]:
        """加载单个文件"""
        file_path = Path(file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"文件不存在: {file_path}")

        suffix = file_path.suffix.lower()
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
