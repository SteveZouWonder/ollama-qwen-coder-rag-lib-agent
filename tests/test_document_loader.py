#!/usr/bin/env python3
"""
test_document_loader.py — 文档加载器单元测试（Mock 外部读取器）
"""
import pytest
from unittest.mock import MagicMock
from pathlib import Path

from document_loader import DocumentLoader, load_documents


class TestDocumentLoaderInit:
    def test_init_creates_data_dir(self, temp_dir):
        dl = DocumentLoader(temp_dir)
        assert dl.data_dir == temp_dir


class TestDocumentLoaderLoadFile:
    """测试 load_file"""

    def test_load_pdf(self, temp_dir, monkeypatch):
        path = temp_dir / "test.pdf"
        path.write_text("fake pdf content")

        mock_doc = MagicMock()
        mock_doc.metadata = {}
        mock_reader = MagicMock()
        mock_reader.load_data.return_value = [mock_doc]

        # 直接修改 READERS 字典来注入 Mock
        import document_loader
        monkeypatch.setattr(document_loader.DocumentLoader, "READERS", {".pdf": lambda: mock_reader})
        dl = DocumentLoader(temp_dir)
        docs = dl.load_file(path)

        assert len(docs) == 1
        assert docs[0].metadata["file_name"] == "test.pdf"
        assert docs[0].metadata["file_type"] == ".pdf"

    def test_load_markdown(self, temp_dir, monkeypatch):
        path = temp_dir / "note.md"
        path.write_text("# Title")

        mock_doc = MagicMock()
        mock_doc.metadata = {}
        mock_reader = MagicMock()
        mock_reader.load_data.return_value = [mock_doc]

        import document_loader
        monkeypatch.setattr(document_loader.DocumentLoader, "READERS", {".md": lambda: mock_reader})
        dl = DocumentLoader(temp_dir)
        docs = dl.load_file(path)

        assert len(docs) == 1
        assert docs[0].metadata["file_type"] == ".md"

    def test_load_unsupported_uses_flat_reader(self, temp_dir, monkeypatch):
        path = temp_dir / "data.xyz"
        path.write_text("content")

        mock_doc = MagicMock()
        mock_doc.metadata = {}
        mock_reader = MagicMock()
        mock_reader.load_data.return_value = [mock_doc]

        import document_loader
        monkeypatch.setattr(document_loader.DocumentLoader, "READERS", {".xyz": lambda: mock_reader})
        dl = DocumentLoader(temp_dir)
        docs = dl.load_file(path)

        assert len(docs) == 1

    def test_load_nonexistent_raises(self, temp_dir):
        dl = DocumentLoader(temp_dir)
        with pytest.raises(FileNotFoundError):
            dl.load_file(temp_dir / "no.pdf")

    def test_load_file_failure_returns_empty(self, temp_dir, monkeypatch):
        path = temp_dir / "bad.pdf"
        path.write_text("x")

        mock_reader = MagicMock()
        mock_reader.load_data.side_effect = Exception("read error")

        import document_loader
        monkeypatch.setattr(document_loader.DocumentLoader, "READERS", {".pdf": lambda: mock_reader})
        dl = DocumentLoader(temp_dir)
        docs = dl.load_file(path)

        assert docs == []


class TestDocumentLoaderLoadDirectory:
    """测试 load_directory"""

    def test_load_directory_recursive(self, temp_dir, monkeypatch):
        (temp_dir / "a.py").write_text("print(1)")
        (temp_dir / "sub").mkdir()
        (temp_dir / "sub" / "b.py").write_text("print(2)")
        (temp_dir / "readme.md").write_text("# doc")

        mock_doc = MagicMock()
        mock_doc.metadata = {}
        mock_reader = MagicMock()
        mock_reader.load_data.return_value = [mock_doc]

        import document_loader
        mock_readers = {".py": lambda: mock_reader, ".md": lambda: mock_reader}
        monkeypatch.setattr(document_loader.DocumentLoader, "READERS", mock_readers)
        dl = DocumentLoader(temp_dir)
        docs = dl.load_directory(temp_dir, recursive=True)

        assert len(docs) == 3  # a.py, b.py, readme.md

    def test_load_directory_non_recursive(self, temp_dir, monkeypatch):
        (temp_dir / "a.py").write_text("x")
        (temp_dir / "sub").mkdir()
        (temp_dir / "sub" / "b.py").write_text("y")

        mock_doc = MagicMock()
        mock_doc.metadata = {}
        mock_reader = MagicMock()
        mock_reader.load_data.return_value = [mock_doc]

        import document_loader
        monkeypatch.setattr(document_loader.DocumentLoader, "READERS", {".py": lambda: mock_reader})
        dl = DocumentLoader(temp_dir)
        docs = dl.load_directory(temp_dir, recursive=False)

        assert len(docs) == 1  # 只有 a.py

    def test_load_directory_nonexistent_raises(self, temp_dir):
        dl = DocumentLoader(temp_dir)
        with pytest.raises(FileNotFoundError):
            dl.load_directory(temp_dir / "no")


class TestDocumentLoaderLoadSpecificTypes:
    def test_load_specific_extensions(self, temp_dir, monkeypatch):
        (temp_dir / "a.py").write_text("x")
        (temp_dir / "b.js").write_text("y")
        (temp_dir / "c.txt").write_text("z")

        mock_doc = MagicMock()
        mock_doc.metadata = {}
        mock_reader = MagicMock()
        mock_reader.load_data.return_value = [mock_doc]

        import document_loader
        monkeypatch.setattr(document_loader.DocumentLoader, "READERS", {".py": lambda: mock_reader, ".js": lambda: mock_reader, ".txt": lambda: mock_reader})
        dl = DocumentLoader(temp_dir)
        docs = dl.load_specific_types(temp_dir, [".py", ".js"])

        assert len(docs) == 2


class TestLoadDocumentsConvenience:
    """测试便捷函数 load_documents"""

    def test_load_file(self, temp_dir, monkeypatch):
        path = temp_dir / "test.txt"
        path.write_text("hello")

        mock_doc = MagicMock()
        mock_doc.metadata = {}
        mock_reader = MagicMock()
        mock_reader.load_data.return_value = [mock_doc]

        import document_loader
        monkeypatch.setattr(document_loader.DocumentLoader, "READERS", {".txt": lambda: mock_reader})
        docs = load_documents(str(path))

        assert len(docs) == 1

    def test_load_directory(self, temp_dir, monkeypatch):
        (temp_dir / "a.py").write_text("x")
        (temp_dir / "b.md").write_text("y")

        mock_doc = MagicMock()
        mock_doc.metadata = {}
        mock_reader = MagicMock()
        mock_reader.load_data.return_value = [mock_doc]

        import document_loader
        monkeypatch.setattr(document_loader.DocumentLoader, "READERS", {".py": lambda: mock_reader, ".md": lambda: mock_reader})
        docs = load_documents(str(temp_dir))

        assert len(docs) == 2

    def test_load_directory_with_types(self, temp_dir, monkeypatch):
        (temp_dir / "a.py").write_text("x")
        (temp_dir / "b.md").write_text("y")

        mock_doc = MagicMock()
        mock_doc.metadata = {}
        mock_reader = MagicMock()
        mock_reader.load_data.return_value = [mock_doc]

        import document_loader
        monkeypatch.setattr(document_loader.DocumentLoader, "READERS", {".py": lambda: mock_reader, ".md": lambda: mock_reader})
        docs = load_documents(str(temp_dir), file_types=[".py"])

        assert len(docs) == 1

    def test_load_nonexistent_raises(self, temp_dir):
        with pytest.raises(ValueError):
            load_documents(str(temp_dir / "no"))
