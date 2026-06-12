#!/usr/bin/env python3
"""
test_rag_engine.py — RAG 引擎单元测试（Mock Ollama + ChromaDB + LlamaIndex）
"""
import pytest
from unittest.mock import MagicMock, patch, PropertyMock
from pathlib import Path

from rag_engine import RAGEngine, build_knowledge_base


class TestRAGEngineInit:
    """测试初始化"""

    @patch("rag_engine.Ollama")
    @patch("rag_engine.OllamaEmbedding")
    @patch("rag_engine.chromadb.PersistentClient")
    def test_init_sets_up_components(self, mock_chroma, mock_embed, mock_llm):
        engine = RAGEngine()
        assert engine.index is None
        assert engine.query_engine is None
        mock_llm.assert_called_once()
        mock_embed.assert_called_once()
        mock_chroma.assert_called_once()


class TestRAGEngineBuildIndex:
    """测试构建索引"""

    @patch("rag_engine.Ollama")
    @patch("rag_engine.OllamaEmbedding")
    @patch("rag_engine.chromadb.PersistentClient")
    @patch("rag_engine.VectorStoreIndex")
    @patch("rag_engine.SentenceSplitter")
    @patch("rag_engine.Settings")
    def test_build_index(self, mock_settings, mock_splitter, mock_index_cls, mock_chroma, mock_embed, mock_llm):
        
        mock_collection = MagicMock()
        mock_chroma.return_value.get_or_create_collection.return_value = mock_collection

        mock_index = MagicMock()
        mock_index_cls.from_documents.return_value = mock_index

        engine = RAGEngine()
        mock_doc = MagicMock()
        result = engine.build_index([mock_doc], persist=True)

        assert result == mock_index
        mock_index_cls.from_documents.assert_called_once()
        mock_splitter.assert_called_once_with(chunk_size=1024, chunk_overlap=200)

    @patch("rag_engine.Ollama")
    @patch("rag_engine.OllamaEmbedding")
    @patch("rag_engine.chromadb.PersistentClient")
    @patch("rag_engine.VectorStoreIndex")
    @patch("rag_engine.Settings")
    def test_build_index_no_persist(self, mock_settings, mock_index_cls, mock_chroma, mock_embed, mock_llm):
        
        mock_collection = MagicMock()
        mock_chroma.return_value.get_or_create_collection.return_value = mock_collection
        mock_index = MagicMock()
        mock_index_cls.from_documents.return_value = mock_index

        engine = RAGEngine()
        mock_doc = MagicMock()
        result = engine.build_index([mock_doc], persist=False)
        assert result == mock_index


class TestRAGEngineLoadIndex:
    """测试加载索引"""

    @patch("rag_engine.Ollama")
    @patch("rag_engine.OllamaEmbedding")
    @patch("rag_engine.chromadb.PersistentClient")
    @patch("rag_engine.load_index_from_storage")
    @patch("rag_engine.StorageContext")
    @patch("rag_engine.Settings")
    def test_load_index_exists(self, mock_settings, mock_storage, mock_load, mock_chroma, mock_embed, mock_llm, temp_dir):
        
        mock_collection = MagicMock()
        mock_chroma.return_value.get_or_create_collection.return_value = mock_collection

        # 创建持久化目录
        persist_dir = temp_dir / "index_storage" / "llama_index"
        persist_dir.mkdir(parents=True)

        with patch("rag_engine.INDEX_DIR", temp_dir / "index_storage"):
            engine = RAGEngine()
            mock_index = MagicMock()
            mock_load.return_value = mock_index
            result = engine.load_index()
            assert result == mock_index

    @patch("rag_engine.Ollama")
    @patch("rag_engine.OllamaEmbedding")
    @patch("rag_engine.chromadb.PersistentClient")
    def test_load_index_not_exists(self, mock_chroma, mock_embed, mock_llm, temp_dir):
        
        mock_collection = MagicMock()
        mock_chroma.return_value.get_or_create_collection.return_value = mock_collection

        with patch("rag_engine.INDEX_DIR", temp_dir / "index_storage"):
            engine = RAGEngine()
            result = engine.load_index()
            assert result is None


class TestRAGEngineAddDocuments:
    """测试添加文档"""

    @patch("rag_engine.Ollama")
    @patch("rag_engine.OllamaEmbedding")
    @patch("rag_engine.chromadb.PersistentClient")
    def test_add_documents_no_index(self, mock_chroma, mock_embed, mock_llm):
        
        mock_collection = MagicMock()
        mock_chroma.return_value.get_or_create_collection.return_value = mock_collection

        with patch.object(RAGEngine, "build_index") as mock_build:
            engine = RAGEngine()
            mock_doc = MagicMock()
            engine.add_documents([mock_doc])
            mock_build.assert_called_once()

    @patch("rag_engine.Ollama")
    @patch("rag_engine.OllamaEmbedding")
    @patch("rag_engine.chromadb.PersistentClient")
    def test_add_documents_with_index(self, mock_chroma, mock_embed, mock_llm):
        
        mock_collection = MagicMock()
        mock_chroma.return_value.get_or_create_collection.return_value = mock_collection

        engine = RAGEngine()
        engine.index = MagicMock()
        engine.query_engine = MagicMock()

        with patch.object(engine, "_persist_index") as mock_persist:
            mock_doc = MagicMock()
            engine.add_documents([mock_doc])
            engine.index.insert.assert_called_once_with(mock_doc)
            mock_persist.assert_called_once()


class TestRAGEngineQuery:
    """测试查询"""

    @patch("rag_engine.Ollama")
    @patch("rag_engine.OllamaEmbedding")
    @patch("rag_engine.chromadb.PersistentClient")
    def test_query(self, mock_chroma, mock_embed, mock_llm):
        
        mock_collection = MagicMock()
        mock_chroma.return_value.get_or_create_collection.return_value = mock_collection

        engine = RAGEngine()
        engine.query_engine = MagicMock()
        engine.query_engine.query.return_value = "这是回答"

        result = engine.query("什么是RAG？")
        assert result == "这是回答"
        engine.query_engine.query.assert_called_once()

    @patch("rag_engine.Ollama")
    @patch("rag_engine.OllamaEmbedding")
    @patch("rag_engine.chromadb.PersistentClient")
    def test_query_without_engine_raises(self, mock_chroma, mock_embed, mock_llm):
        
        mock_collection = MagicMock()
        mock_chroma.return_value.get_or_create_collection.return_value = mock_collection

        engine = RAGEngine()
        with pytest.raises(RuntimeError):
            engine.query("test")


class TestRAGEngineQueryWithSources:
    """测试带来源查询"""

    @patch("rag_engine.Ollama")
    @patch("rag_engine.OllamaEmbedding")
    @patch("rag_engine.chromadb.PersistentClient")
    def test_query_with_sources(self, mock_chroma, mock_embed, mock_llm):
        
        mock_collection = MagicMock()
        mock_chroma.return_value.get_or_create_collection.return_value = mock_collection

        engine = RAGEngine()
        mock_response = MagicMock()
        mock_node = MagicMock()
        mock_node.node.get_content.return_value = "片段内容"
        mock_node.node.metadata = {"file_name": "test.pdf", "file_path": "/tmp/test.pdf"}
        mock_node.score = 0.85
        mock_response.source_nodes = [mock_node]
        mock_response.__str__ = lambda self: "回答内容"

        engine.query_engine = MagicMock()
        engine.query_engine.query.return_value = mock_response

        result = engine.query_with_sources("test")
        assert result["answer"] == "回答内容"
        assert len(result["sources"]) == 1
        assert result["sources"][0]["file"] == "test.pdf"
        assert result["sources"][0]["score"] == 0.85

    @patch("rag_engine.Ollama")
    @patch("rag_engine.OllamaEmbedding")
    @patch("rag_engine.chromadb.PersistentClient")
    def test_query_with_sources_no_nodes(self, mock_chroma, mock_embed, mock_llm):
        
        mock_collection = MagicMock()
        mock_chroma.return_value.get_or_create_collection.return_value = mock_collection

        engine = RAGEngine()
        mock_response = MagicMock()
        mock_response.source_nodes = []
        mock_response.__str__ = lambda self: "无来源回答"

        engine.query_engine = MagicMock()
        engine.query_engine.query.return_value = mock_response

        result = engine.query_with_sources("test")
        assert result["sources"] == []


class TestRAGEngineAgentTools:
    """测试 Agent 工具接口"""

    @patch("rag_engine.Ollama")
    @patch("rag_engine.OllamaEmbedding")
    @patch("rag_engine.chromadb.PersistentClient")
    def test_query_tool(self, mock_chroma, mock_embed, mock_llm):
        
        mock_collection = MagicMock()
        mock_chroma.return_value.get_or_create_collection.return_value = mock_collection

        engine = RAGEngine()
        engine.query_engine = MagicMock()
        mock_response = MagicMock()
        mock_response.source_nodes = []
        mock_response.__str__ = lambda self: "工具回答"
        engine.query_engine.query.return_value = mock_response

        result = engine.query_tool("问题")
        assert "工具回答" in result

    @patch("rag_engine.Ollama")
    @patch("rag_engine.OllamaEmbedding")
    @patch("rag_engine.chromadb.PersistentClient")
    def test_query_tool_no_engine(self, mock_chroma, mock_embed, mock_llm):
        
        mock_collection = MagicMock()
        mock_chroma.return_value.get_or_create_collection.return_value = mock_collection

        engine = RAGEngine()
        result = engine.query_tool("问题")
        assert "[错误] 知识库索引未初始化" in result

    @patch("rag_engine.Ollama")
    @patch("rag_engine.OllamaEmbedding")
    @patch("rag_engine.chromadb.PersistentClient")
    def test_query_tool_exception_handling(self, mock_chroma, mock_embed, mock_llm):
        """测试query_tool的异常处理"""
        
        mock_collection = MagicMock()
        mock_chroma.return_value.get_or_create_collection.return_value = mock_collection

        engine = RAGEngine()
        engine.query_engine = MagicMock()
        engine.query_engine.query.side_effect = Exception("query failed")

        result = engine.query_tool("问题")
        assert "[错误] 知识库查询失败" in result

    @patch("rag_engine.Ollama")
    @patch("rag_engine.OllamaEmbedding")
    @patch("rag_engine.chromadb.PersistentClient")
    def test_add_document_tool(self, mock_chroma, mock_embed, mock_llm, temp_dir):
        mock_collection = MagicMock()
        mock_chroma.return_value.get_or_create_collection.return_value = mock_collection

        engine = RAGEngine()
        engine.index = MagicMock()
        engine.query_engine = MagicMock()

        path = temp_dir / "test.txt"
        path.write_text("hello")

        with patch("rag_engine.load_documents") as mock_load:
            mock_doc = MagicMock()
            mock_load.return_value = [mock_doc]
            result = engine.add_document_tool(str(path))
            assert "[成功]" in result

    @patch("rag_engine.Ollama")
    @patch("rag_engine.OllamaEmbedding")
    @patch("rag_engine.chromadb.PersistentClient")
    def test_add_document_tool_not_found(self, mock_chroma, mock_embed, mock_llm):
        mock_collection = MagicMock()
        mock_chroma.return_value.get_or_create_collection.return_value = mock_collection

        engine = RAGEngine()
        result = engine.add_document_tool("/nonexistent/file.pdf")
        assert "[错误] 文件不存在" in result

    @patch("rag_engine.Ollama")
    @patch("rag_engine.OllamaEmbedding")
    @patch("rag_engine.chromadb.PersistentClient")
    def test_add_document_tool_no_docs(self, mock_chroma, mock_embed, mock_llm, temp_dir):
        """测试添加文件但无法加载文档"""
        mock_collection = MagicMock()
        mock_chroma.return_value.get_or_create_collection.return_value = mock_collection

        engine = RAGEngine()
        engine.index = MagicMock()
        engine.query_engine = MagicMock()

        path = temp_dir / "test.txt"
        path.write_text("hello")

        with patch("rag_engine.load_documents") as mock_load:
            mock_load.return_value = []  # 返回空文档列表
            result = engine.add_document_tool(str(path))
            assert "[错误] 无法加载文档" in result

    @patch("rag_engine.Ollama")
    @patch("rag_engine.OllamaEmbedding")
    @patch("rag_engine.chromadb.PersistentClient")
    def test_add_document_tool_exception_handling(self, mock_chroma, mock_embed, mock_llm, temp_dir):
        """测试add_document_tool的异常处理"""
        mock_collection = MagicMock()
        mock_chroma.return_value.get_or_create_collection.return_value = mock_collection

        engine = RAGEngine()
        engine.index = MagicMock()
        engine.query_engine = MagicMock()

        path = temp_dir / "test.txt"
        path.write_text("hello")

        with patch("rag_engine.load_documents") as mock_load:
            mock_load.side_effect = Exception("load failed")
            result = engine.add_document_tool(str(path))
            assert "[错误] 添加文档失败" in result

    @patch("rag_engine.Ollama")
    @patch("rag_engine.OllamaEmbedding")
    @patch("rag_engine.chromadb.PersistentClient")
    def test_get_stats_tool(self, mock_chroma, mock_embed, mock_llm):
        mock_collection = MagicMock()
        mock_collection.count.return_value = 42
        mock_chroma.return_value.get_or_create_collection.return_value = mock_collection

        engine = RAGEngine()
        result = engine.get_stats_tool()
        assert "42" in result
        assert "qwen2.5-coder:7b" in result


class TestRAGEngineStats:
    """测试统计信息"""

    @patch("rag_engine.Ollama")
    @patch("rag_engine.OllamaEmbedding")
    @patch("rag_engine.chromadb.PersistentClient")
    def test_get_stats(self, mock_chroma, mock_embed, mock_llm):
        mock_collection = MagicMock()
        mock_collection.count.return_value = 10
        mock_chroma.return_value.get_or_create_collection.return_value = mock_collection

        engine = RAGEngine()
        stats = engine.get_stats()
        assert stats["total_documents"] == 10
        assert stats["llm_model"] == "qwen2.5-coder:7b"
        assert stats["chunk_size"] == 1024


class TestRAGEngineClear:
    """测试清空索引"""

    @patch("rag_engine.Ollama")
    @patch("rag_engine.OllamaEmbedding")
    @patch("rag_engine.chromadb.PersistentClient")
    def test_clear_index(self, mock_chroma, mock_embed, mock_llm):
        mock_collection = MagicMock()
        mock_chroma.return_value.get_or_create_collection.return_value = mock_collection

        engine = RAGEngine()
        engine.index = MagicMock()
        engine.query_engine = MagicMock()

        engine.clear_index()
        assert engine.index is None
        assert engine.query_engine is None


class TestBuildKnowledgeBase:
    """测试便捷函数"""

    @patch("rag_engine.Ollama")
    @patch("rag_engine.OllamaEmbedding")
    @patch("rag_engine.chromadb.PersistentClient")
    @patch("rag_engine.VectorStoreIndex")
    def test_build_with_documents(self, mock_index_cls, mock_chroma, mock_embed, mock_llm, temp_dir):
        mock_collection = MagicMock()
        mock_chroma.return_value.get_or_create_collection.return_value = mock_collection
        mock_index = MagicMock()
        mock_index_cls.from_documents.return_value = mock_index

        path = temp_dir / "test.txt"
        path.write_text("hello")

        with patch("rag_engine.load_documents") as mock_load:
            mock_doc = MagicMock()
            mock_load.return_value = [mock_doc]
            engine = build_knowledge_base(str(temp_dir))
            assert engine is not None

    @patch("rag_engine.Ollama")
    @patch("rag_engine.OllamaEmbedding")
    @patch("rag_engine.chromadb.PersistentClient")
    def test_build_no_documents(self, mock_chroma, mock_embed, mock_llm, temp_dir):
        mock_collection = MagicMock()
        mock_chroma.return_value.get_or_create_collection.return_value = mock_collection

        with patch("rag_engine.load_documents") as mock_load:
            mock_load.return_value = []
            engine = build_knowledge_base(str(temp_dir))
            assert engine is not None
