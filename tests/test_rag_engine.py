#!/usr/bin/env python3
"""
test_rag_engine.py — RAG 引擎单元测试（Mock Ollama + ChromaDB + LlamaIndex）
"""
import sys
from unittest.mock import MagicMock, patch
import pytest
import importlib

# 在导入rag_engine之前，强制清理可能被污染的模块
if 'rag_engine' in sys.modules:
    del sys.modules['rag_engine']

from rag_engine import RAGEngine, build_knowledge_base

@pytest.fixture(autouse=True)
def ensure_rag_not_mocked(request):
    """
    在每个test_rag_engine.py测试前后确保rag_engine没有被mock
    """
    # 测试开始前检查RAGEngine是否被mock
    import rag_engine as rag_module
    # 如果RAGEngine类被mock了，重新加载模块
    if hasattr(rag_module.RAGEngine, '_mock_name'):
        importlib.reload(rag_module)
    
    yield
    
    # 测试结束后重新加载模块
    importlib.reload(rag_module)


class TestRAGEngineInit:
    """测试初始化"""

    @patch("rag_engine.Ollama")
    @patch("rag_engine.OllamaEmbedding")
    @patch("rag_engine.chromadb.PersistentClient")
    def test_init_sets_up_components(self, mock_chroma, mock_embed, mock_llm):
        # Mock chroma client's methods to avoid side effects
        mock_collection = MagicMock()
        mock_chroma.return_value.get_or_create_collection.return_value = mock_collection
        
        engine = RAGEngine()
        assert engine.index is None
        assert engine.retriever is None
        mock_llm.assert_called_once()
        mock_embed.assert_called_once()
        mock_chroma.assert_called_once()

    @patch("rag_engine.Ollama")
    @patch("rag_engine.OllamaEmbedding")
    @patch("rag_engine.chromadb.PersistentClient")
    def test_default_storage_follows_config(self, mock_chroma, mock_embed, mock_llm):
        """未传 persist_dir：Chroma 路径 / 索引目录与 config 一致（行为不变）。"""
        import rag_engine as rag_module
        engine = RAGEngine()
        assert engine.vector_db_path == rag_module.VECTOR_DB_PATH
        assert engine.index_dir == rag_module.INDEX_DIR
        assert mock_chroma.call_args.kwargs["path"] == rag_module.VECTOR_DB_PATH
        assert engine.get_stats()["vector_db_path"] == rag_module.VECTOR_DB_PATH

    @patch("rag_engine.Ollama")
    @patch("rag_engine.OllamaEmbedding")
    @patch("rag_engine.chromadb.PersistentClient")
    def test_persist_dir_redirects_storage(self, mock_chroma, mock_embed, mock_llm, tmp_path):
        """F10 P1-3：persist_dir 只改本实例的存储位置——Chroma、LlamaIndex 持久化、快照目录、统计。"""
        import rag_engine as rag_module
        mock_collection = MagicMock()
        mock_collection.count.return_value = 3
        mock_chroma.return_value.get_or_create_collection.return_value = mock_collection

        target = tmp_path / "eval-index"
        engine = RAGEngine(persist_dir=str(target), enable_auto_snapshot=True)
        assert engine.index_dir == target
        assert engine.vector_db_path == str(target / "chroma_db")
        assert mock_chroma.call_args.kwargs["path"] == str(target / "chroma_db")
        assert engine.get_stats()["vector_db_path"] == str(target / "chroma_db")
        if engine.snapshot_manager is not None:
            assert engine.snapshot_manager.index_dir == target

        # _persist_index 写到 persist_dir/llama_index（父目录不存在也会创建）
        engine.index = MagicMock()
        engine._persist_index()
        engine.index.storage_context.persist.assert_called_once_with(persist_dir=str(target / "llama_index"))
        assert (target / "llama_index").is_dir()

        # load_index 从同一目录读；目录不存在时返回 None
        other = RAGEngine(persist_dir=str(tmp_path / "empty"))
        assert other.load_index() is None
        # 真实 index_storage 路径未被本实例触碰
        assert str(rag_module.INDEX_DIR) not in engine.vector_db_path


class TestRAGEngineBuildIndex:
    """测试构建索引"""

    @patch("rag_engine.Ollama")
    @patch("rag_engine.OllamaEmbedding")
    @patch("rag_engine.chromadb.PersistentClient")
    @patch("rag_engine.VectorStoreIndex")
    @patch("rag_engine.build_node_parser")
    @patch("rag_engine.Settings")
    def test_build_index(self, mock_settings, mock_build_parser, mock_index_cls, mock_chroma, mock_embed, mock_llm):
        """P4：统一切分器由 build_node_parser 提供并设到 Settings；切分结果直接建索引。"""
        from llama_index.core.schema import Document, TextNode

        mock_collection = MagicMock()
        mock_chroma.return_value.get_or_create_collection.return_value = mock_collection

        parser = MagicMock()
        parser.fallback_reasons = {}
        parser.get_nodes_from_documents.return_value = [TextNode(text="a"), TextNode(text="b")]
        mock_build_parser.return_value = parser
        mock_index = MagicMock()
        mock_index_cls.return_value = mock_index

        engine = RAGEngine()
        doc = Document(text="hello", metadata={"file_path": "/kb/a.md", "file_name": "a.md"})
        with patch.object(engine, "_register_file_metadata") as mock_register:
            result = engine.build_index([doc], persist=True)

        assert result == mock_index
        mock_build_parser.assert_called_once()
        assert mock_settings.node_parser is parser
        # 用切好的节点建索引（不再让 from_documents 内部重切一次）
        mock_index_cls.assert_called_once()
        assert mock_index_cls.call_args.kwargs["nodes"] == parser.get_nodes_from_documents.return_value
        mock_index_cls.from_documents.assert_not_called()
        # 登记元数据复用本次切分统计
        per_file = mock_register.call_args.kwargs["per_file"]
        assert per_file["/kb/a.md"]["chunk_count"] == 2
        assert engine.last_ingest_stats["/kb/a.md"]["chunk_count"] == 2

    @patch("rag_engine.Ollama")
    @patch("rag_engine.OllamaEmbedding")
    @patch("rag_engine.chromadb.PersistentClient")
    @patch("rag_engine.VectorStoreIndex")
    @patch("rag_engine.Settings")
    def test_build_index_falls_back_to_from_documents_when_split_fails(
        self, mock_settings, mock_index_cls, mock_chroma, mock_embed, mock_llm
    ):
        """切分异常时回退 LlamaIndex 内部路径（from_documents + transformations）。"""
        mock_chroma.return_value.get_or_create_collection.return_value = MagicMock()
        mock_index = MagicMock()
        mock_index_cls.from_documents.return_value = mock_index

        engine = RAGEngine()
        parser = MagicMock()
        parser.get_nodes_from_documents.side_effect = RuntimeError("boom")
        engine._node_parser = parser
        with patch.object(engine, "_register_file_metadata"):
            result = engine.build_index([MagicMock()], persist=False)
        assert result == mock_index
        assert mock_index_cls.from_documents.call_args.kwargs["transformations"] == [parser]

    @patch("rag_engine.Ollama")
    @patch("rag_engine.OllamaEmbedding")
    @patch("rag_engine.chromadb.PersistentClient")
    @patch("rag_engine.VectorStoreIndex")
    @patch("rag_engine.Settings")
    def test_build_index_no_persist(self, mock_settings, mock_index_cls, mock_chroma, mock_embed, mock_llm):
        
        # Mock chroma client's methods to avoid side effects
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
        
        # Mock chroma client's methods to avoid side effects
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
            # P4：加载路径也设置统一切分器（此前缺失 → 追加文档落到 llama-index 默认参数）
            assert mock_settings.node_parser is engine.node_parser
            assert mock_index._transformations == [engine.node_parser]

    @patch("rag_engine.Ollama")
    @patch("rag_engine.OllamaEmbedding")
    @patch("rag_engine.chromadb.PersistentClient")
    def test_load_index_not_exists(self, mock_chroma, mock_embed, mock_llm, temp_dir):
        
        # Mock chroma client's methods to avoid side effects
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
        
        # Mock chroma client's methods to avoid side effects
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
        
        # Mock chroma client's methods to avoid side effects
        mock_collection = MagicMock()
        mock_chroma.return_value.get_or_create_collection.return_value = mock_collection

        engine = RAGEngine()
        engine.index = MagicMock()
        engine.retriever = MagicMock()

        with patch.object(engine, "_persist_index") as mock_persist:
            mock_doc = MagicMock()
            # MagicMock 文档无法被统一切分器处理 → 回退 index.insert 路径
            engine.add_documents([mock_doc])
            engine.index.insert.assert_called_once_with(mock_doc)
            mock_persist.assert_called_once()

    @patch("rag_engine.Ollama")
    @patch("rag_engine.OllamaEmbedding")
    @patch("rag_engine.chromadb.PersistentClient")
    def test_add_documents_inserts_presplit_nodes_with_progress(self, mock_chroma, mock_embed, mock_llm):
        """P4：真实 Document 先统一切分，再分批 insert_nodes，并发 chunk/embed 进度事件。"""
        from llama_index.core.schema import Document

        mock_chroma.return_value.get_or_create_collection.return_value = MagicMock()
        engine = RAGEngine()
        engine.index = MagicMock()
        engine.retriever = MagicMock()
        events = []
        doc = Document(text="hello world. " * 400, metadata={"file_path": "/kb/x.txt", "file_name": "x.txt", "file_type": ".txt"})
        with patch.object(engine, "_persist_index"), patch.object(engine, "_register_file_metadata") as reg:
            engine.add_documents([doc], ["/kb/x.txt"], progress_callback=events.append)
        engine.index.insert.assert_not_called()
        assert engine.index.insert_nodes.call_count >= 1
        inserted = sum(len(c.args[0]) for c in engine.index.insert_nodes.call_args_list)
        assert inserted == reg.call_args.kwargs["per_file"]["/kb/x.txt"]["chunk_count"] >= 1
        stages = [e["stage"] for e in events]
        assert "chunk" in stages and "embed" in stages
        assert events[-1]["current"] == events[-1]["total"] == inserted


class TestRAGEngineQuery:
    """测试查询"""

    @patch("rag_engine.Ollama")
    @patch("rag_engine.OllamaEmbedding")
    @patch("rag_engine.chromadb.PersistentClient")
    def test_query(self, mock_chroma, mock_embed, mock_llm):
        
        # Mock chroma client's methods to avoid side effects
        mock_collection = MagicMock()
        mock_chroma.return_value.get_or_create_collection.return_value = mock_collection

        engine = RAGEngine()
        engine.retriever = MagicMock()
        # F9 P0-1：query() 委托共享编排层（kb_only），答案由忠实性 prompt 综合
        with patch("rag_pipeline.answer_question", return_value={"answer": "这是回答", "kb_sources": []}) as aq:
            result = engine.query("什么是RAG？")
        assert result == "这是回答"
        aq.assert_called_once()
        assert aq.call_args.kwargs["kb_only"] is True and aq.call_args.kwargs["enable_web_search"] is False

    @patch("rag_engine.Ollama")
    @patch("rag_engine.OllamaEmbedding")
    @patch("rag_engine.chromadb.PersistentClient")
    def test_query_without_engine_raises(self, mock_chroma, mock_embed, mock_llm):
        
        # Mock chroma client's methods to avoid side effects
        mock_collection = MagicMock()
        mock_chroma.return_value.get_or_create_collection.return_value = mock_collection

        engine = RAGEngine()
        with pytest.raises(RuntimeError):
            engine.query("test")


class TestRAGEngineQueryWithSources:
    """测试带来源查询（F9 P0-1：检索-only，不生成答案）"""

    @staticmethod
    def _node(content="片段内容", fname="test.pdf", score=0.85):
        n = MagicMock()
        n.node.get_content.return_value = content
        n.node.metadata = {"file_name": fname, "file_path": f"/tmp/{fname}"}
        n.score = score
        return n

    @patch("rag_engine.Ollama")
    @patch("rag_engine.OllamaEmbedding")
    @patch("rag_engine.chromadb.PersistentClient")
    def test_query_with_sources(self, mock_chroma, mock_embed, mock_llm):
        mock_chroma.return_value.get_or_create_collection.return_value = MagicMock()
        engine = RAGEngine()
        engine.hybrid_enabled = False
        engine.retriever = MagicMock()
        engine.retriever.retrieve.return_value = [self._node()]

        result = engine.query_with_sources("test")
        # answer 键保留但恒为空：答案由 rag_pipeline 单次综合
        assert result["answer"] == ""
        assert len(result["sources"]) == 1
        assert result["sources"][0]["file"] == "test.pdf"
        assert result["sources"][0]["score"] == 0.85
        engine.retriever.retrieve.assert_called_once_with("test")

    @patch("rag_engine.Ollama")
    @patch("rag_engine.OllamaEmbedding")
    @patch("rag_engine.chromadb.PersistentClient")
    def test_query_with_sources_applies_similarity_postprocessor(self, mock_chroma, mock_embed, mock_llm):
        """检索器之后应用相似度阈值后处理（等价此前 as_query_engine 的 node_postprocessors）。"""
        mock_chroma.return_value.get_or_create_collection.return_value = MagicMock()
        engine = RAGEngine()
        engine.hybrid_enabled = False
        engine.retriever = MagicMock()
        engine.retriever.retrieve.return_value = [self._node(fname="hi.md", score=0.9), self._node(fname="lo.md", score=0.05)]
        pp = MagicMock()
        pp.postprocess_nodes.side_effect = lambda nodes, query_str=None: [n for n in nodes if n.score >= 0.3]
        engine.node_postprocessors = [pp]
        result = engine.query_with_sources("test")
        assert [s["file"] for s in result["sources"]] == ["hi.md"]
        pp.postprocess_nodes.assert_called_once()

    @patch("rag_engine.Ollama")
    @patch("rag_engine.OllamaEmbedding")
    @patch("rag_engine.chromadb.PersistentClient")
    def test_postprocessor_failure_keeps_raw_nodes(self, mock_chroma, mock_embed, mock_llm):
        mock_chroma.return_value.get_or_create_collection.return_value = MagicMock()
        engine = RAGEngine()
        engine.hybrid_enabled = False
        engine.retriever = MagicMock()
        engine.retriever.retrieve.return_value = [self._node()]
        pp = MagicMock()
        pp.postprocess_nodes.side_effect = RuntimeError("boom")
        engine.node_postprocessors = [pp]
        assert len(engine.query_with_sources("test")["sources"]) == 1

    @patch("rag_engine.Ollama")
    @patch("rag_engine.OllamaEmbedding")
    @patch("rag_engine.chromadb.PersistentClient")
    def test_query_with_sources_no_nodes(self, mock_chroma, mock_embed, mock_llm):
        mock_chroma.return_value.get_or_create_collection.return_value = MagicMock()
        engine = RAGEngine()
        engine.hybrid_enabled = False
        engine.retriever = MagicMock()
        engine.retriever.retrieve.return_value = []
        result = engine.query_with_sources("test")
        assert result["sources"] == [] and result["answer"] == ""

    @patch("rag_engine.Ollama")
    @patch("rag_engine.OllamaEmbedding")
    @patch("rag_engine.chromadb.PersistentClient")
    def test_query_with_sources_uninitialized_raises(self, mock_chroma, mock_embed, mock_llm):
        mock_chroma.return_value.get_or_create_collection.return_value = MagicMock()
        engine = RAGEngine()
        with pytest.raises(RuntimeError):
            engine.query_with_sources("test")

    @patch("rag_engine.Ollama")
    @patch("rag_engine.OllamaEmbedding")
    @patch("rag_engine.chromadb.PersistentClient")
    def test_query_with_sources_with_progress_callback(self, mock_chroma, mock_embed, mock_llm):
        """进度回调：embedding + retrieving + scoring（1 个节点）= 3 次，不再有 generating。"""
        mock_chroma.return_value.get_or_create_collection.return_value = MagicMock()
        engine = RAGEngine()
        engine.hybrid_enabled = False
        engine.retriever = MagicMock()
        engine.retriever.retrieve.return_value = [self._node()]
        progress_callback = MagicMock()

        result = engine.query_with_sources("test", progress_callback=progress_callback)
        assert result["answer"] == "" and len(result["sources"]) == 1
        assert progress_callback.call_count == 3
        phases = [c[0][0]["phase"] for c in progress_callback.call_args_list]
        assert phases == ["embedding", "retrieving", "scoring"]
        assert "generating" not in phases

    @patch("rag_engine.Ollama")
    @patch("rag_engine.OllamaEmbedding")
    @patch("rag_engine.chromadb.PersistentClient")
    def test_query_with_sources_progress_callback_scoring(self, mock_chroma, mock_embed, mock_llm):
        mock_chroma.return_value.get_or_create_collection.return_value = MagicMock()
        engine = RAGEngine()
        engine.hybrid_enabled = False
        engine.retriever = MagicMock()
        engine.retriever.retrieve.return_value = [self._node(f"片段{i}", f"test{i}.pdf", 0.8 + i * 0.05) for i in range(3)]
        progress_callback = MagicMock()

        result = engine.query_with_sources("test", progress_callback=progress_callback)
        assert len(result["sources"]) == 3
        # embedding + retrieving + 3 次 scoring = 5 次
        assert progress_callback.call_count == 5
        scoring_calls = [c for c in progress_callback.call_args_list if c[0][0].get("phase") == "scoring"]
        assert len(scoring_calls) == 3
        assert scoring_calls[0][0][0]["current"] == 1 and scoring_calls[0][0][0]["total"] == 3
        assert scoring_calls[2][0][0]["current"] == 3

    @patch("rag_engine.Ollama")
    @patch("rag_engine.OllamaEmbedding")
    @patch("rag_engine.chromadb.PersistentClient")
    def test_query_with_sources_score_none_tolerated(self, mock_chroma, mock_embed, mock_llm):
        mock_chroma.return_value.get_or_create_collection.return_value = MagicMock()
        engine = RAGEngine()
        engine.hybrid_enabled = False
        engine.retriever = MagicMock()
        engine.retriever.retrieve.return_value = [self._node(score=None)]
        assert engine.query_with_sources("test")["sources"][0]["score"] is None


class TestRAGEngineAgentTools:
    """测试 Agent 工具接口"""

    @patch("rag_engine.Ollama")
    @patch("rag_engine.OllamaEmbedding")
    @patch("rag_engine.chromadb.PersistentClient")
    def test_query_tool(self, mock_chroma, mock_embed, mock_llm):
        
        mock_collection = MagicMock()
        mock_chroma.return_value.get_or_create_collection.return_value = mock_collection

        engine = RAGEngine()
        engine.retriever = MagicMock()
        # F9 P0-1：query_tool 委托 answer_question(kb_only=True)
        with patch("rag_pipeline.answer_question", return_value={
            "answer": "工具回答", "kb_sources": [{"file": "a.md", "score": 0.9}],
        }) as aq:
            result = engine.query_tool("问题")
        assert "工具回答" in result and "[参考来源]" in result and "a.md" in result
        assert aq.call_args.kwargs["kb_only"] is True

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
        engine.retriever = MagicMock()
        with patch("rag_pipeline.answer_question", side_effect=Exception("query failed")):
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
        engine.retriever = MagicMock()

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
        engine.retriever = MagicMock()

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
        engine.retriever = MagicMock()

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
        assert "qwen3.5:4b" in result


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
        assert stats["llm_model"] == "qwen3.5:4b"
        assert stats["llm_num_ctx"] == 16384
        assert stats["chunk_size"] == 1024
        assert stats["self_check"] is False  # F9 P2-1：/stats 显示自校验开关（默认关）


class TestRAGEngineSetModel:
    """运行时热切换 LLM + 思考模式"""

    @patch("rag_engine.Ollama")
    @patch("rag_engine.OllamaEmbedding")
    @patch("rag_engine.chromadb.PersistentClient")
    def test_init_passes_thinking_false(self, mock_chroma, mock_embed, mock_llm):
        mock_chroma.return_value.get_or_create_collection.return_value = MagicMock()
        RAGEngine()
        kwargs = mock_llm.call_args.kwargs
        assert kwargs["model"] == "qwen3.5:4b"
        assert kwargs["thinking"] is False
        assert kwargs["context_window"] == 16384
        assert kwargs["additional_kwargs"] == {"num_ctx": 16384}

    @patch("rag_engine.Ollama")
    @patch("rag_engine.OllamaEmbedding")
    @patch("rag_engine.chromadb.PersistentClient")
    def test_set_model_rebuilds_llm_and_retriever(self, mock_chroma, mock_embed, mock_llm):
        mock_collection = MagicMock()
        mock_collection.count.return_value = 1
        mock_chroma.return_value.get_or_create_collection.return_value = mock_collection

        engine = RAGEngine()
        # 模拟已加载索引：检索器应被重建（F9 P0-1：不再构造 as_query_engine）
        engine.index = MagicMock()
        engine.index.as_retriever.return_value = "new-retriever"

        ctx = engine.set_model("qwen3.5:9b")

        assert ctx == 8192
        assert engine.llm_model == "qwen3.5:9b"
        assert engine.llm_num_ctx == 8192
        kwargs = mock_llm.call_args.kwargs
        assert kwargs["model"] == "qwen3.5:9b"
        assert kwargs["context_window"] == 8192
        assert kwargs["additional_kwargs"] == {"num_ctx": 8192}
        assert engine.retriever == "new-retriever"
        assert engine.query_engine == "new-retriever"  # 兼容别名
        engine.index.as_query_engine.assert_not_called()
        assert len(engine.node_postprocessors) == 1
        assert engine.get_stats()["llm_model"] == "qwen3.5:9b"
        assert "qwen3.5:9b" in engine.get_stats_tool()

    @patch("rag_engine.Ollama")
    @patch("rag_engine.OllamaEmbedding")
    @patch("rag_engine.chromadb.PersistentClient")
    def test_set_model_without_index_is_safe(self, mock_chroma, mock_embed, mock_llm):
        mock_chroma.return_value.get_or_create_collection.return_value = MagicMock()
        engine = RAGEngine()
        assert engine.index is None
        engine.set_model("qwen3.5:9b")
        assert engine.retriever is None

    @patch("rag_engine.Ollama")
    @patch("rag_engine.OllamaEmbedding")
    @patch("rag_engine.chromadb.PersistentClient")
    def test_set_think_rebuilds_llm_and_keeps_model(self, mock_chroma, mock_embed, mock_llm):
        mock_collection = MagicMock()
        mock_collection.count.return_value = 1
        mock_chroma.return_value.get_or_create_collection.return_value = mock_collection
        engine = RAGEngine()
        engine.index = MagicMock()
        engine.index.as_retriever.return_value = "qe2"

        assert engine.set_think(True) is True
        kwargs = mock_llm.call_args.kwargs
        assert kwargs["thinking"] is True
        assert kwargs["model"] == "qwen3.5:4b"
        assert kwargs["context_window"] == 16384
        assert engine.retriever == "qe2"
        assert engine.get_stats()["llm_think"] is True

        # 切换模型时保留思考开关状态
        engine.set_model("qwen3.5:9b")
        assert mock_llm.call_args.kwargs["thinking"] is True
        assert engine.llm_think is True

        assert engine.set_think(False) is False
        assert mock_llm.call_args.kwargs["thinking"] is False

    @patch("rag_engine.Ollama")
    @patch("rag_engine.OllamaEmbedding")
    @patch("rag_engine.chromadb.PersistentClient")
    def test_set_model_rejects_empty(self, mock_chroma, mock_embed, mock_llm):
        mock_chroma.return_value.get_or_create_collection.return_value = MagicMock()
        engine = RAGEngine()
        with pytest.raises(ValueError):
            engine.set_model("")


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
        engine.retriever = MagicMock()

        engine.clear_index()
        assert engine.index is None
        assert engine.retriever is None


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


class TestRAGEngineFileMetadataRegistration:
    """测试文档入库时登记文件元数据（修复 /file-list 永远为空的问题）"""

    def _make_engine(self, mock_chroma, tmp_storage):
        from file_metadata import FileMetadataManager
        mock_collection = MagicMock()
        mock_chroma.return_value.get_or_create_collection.return_value = mock_collection
        engine = RAGEngine()
        # 注入独立的元数据管理器，避免污染全局/真实数据
        engine.metadata_manager = FileMetadataManager(storage_path=str(tmp_storage))
        return engine, mock_collection

    @patch("rag_engine.Ollama")
    @patch("rag_engine.OllamaEmbedding")
    @patch("rag_engine.chromadb.PersistentClient")
    def test_add_documents_registers_file_metadata(
        self, mock_chroma, mock_embed, mock_llm, tmp_path
    ):
        from llama_index.core.schema import Document

        engine, _ = self._make_engine(mock_chroma, tmp_path / "meta")
        # 真实存在的源文件，便于计算哈希/大小
        src = tmp_path / "doc.md"
        src.write_text("hello world\n" * 50, encoding="utf-8")

        engine.index = MagicMock()  # 已有索引，走 add_documents 分支
        doc = Document(text="hello world\n" * 50,
                       metadata={"file_path": str(src), "file_name": "doc.md"})

        engine.add_documents([doc], [str(src)])

        meta = engine.metadata_manager.get_file_metadata(str(src))
        assert meta is not None
        assert meta.document_count == 1
        assert meta.chunk_count >= 1
        assert meta.file_hash  # 已计算哈希
        # /file-list 现在能看到该文件
        assert len(engine.metadata_manager.list_files()) == 1

    @patch("rag_engine.Ollama")
    @patch("rag_engine.OllamaEmbedding")
    @patch("rag_engine.chromadb.PersistentClient")
    def test_register_falls_back_to_file_paths_without_doc_metadata(
        self, mock_chroma, mock_embed, mock_llm, tmp_path
    ):
        from llama_index.core.schema import Document

        engine, _ = self._make_engine(mock_chroma, tmp_path / "meta")
        engine.index = MagicMock()
        # 文档不带 file_path 元数据，应回退到传入的 file_paths
        doc = Document(text="content")
        engine.add_documents([doc], ["/tmp/some_file.txt"])

        meta = engine.metadata_manager.get_file_metadata("/tmp/some_file.txt")
        assert meta is not None

    @patch("rag_engine.Ollama")
    @patch("rag_engine.OllamaEmbedding")
    @patch("rag_engine.chromadb.PersistentClient")
    def test_backfill_from_vector_store_registers_existing_files(
        self, mock_chroma, mock_embed, mock_llm, tmp_path
    ):
        engine, mock_collection = self._make_engine(mock_chroma, tmp_path / "meta")
        # 模拟向量库中已有两个文件、共 3 个 chunk
        mock_collection.get.return_value = {
            "metadatas": [
                {"file_path": "/kb/a.md"},
                {"file_path": "/kb/a.md"},
                {"file_path": "/kb/b.md"},
            ]
        }

        engine._backfill_file_metadata_from_vector_store()

        a = engine.metadata_manager.get_file_metadata("/kb/a.md")
        b = engine.metadata_manager.get_file_metadata("/kb/b.md")
        assert a is not None and a.chunk_count == 2
        assert b is not None and b.chunk_count == 1
        assert a.chunk_strategy == "text" and a.symbol_count == 0

    @patch("rag_engine.Ollama")
    @patch("rag_engine.OllamaEmbedding")
    @patch("rag_engine.chromadb.PersistentClient")
    def test_backfill_reads_code_chunk_strategy_and_symbols(
        self, mock_chroma, mock_embed, mock_llm, tmp_path
    ):
        """P4：存量补登记从 node metadata 反推分块策略与符号数。"""
        engine, mock_collection = self._make_engine(mock_chroma, tmp_path / "meta")
        mock_collection.get.return_value = {
            "metadatas": [
                {"file_path": "/kb/x.py", "chunk_strategy": "code(python)", "symbol": "A"},
                {"file_path": "/kb/x.py", "chunk_strategy": "code(python)", "symbol": "A.run"},
                {"file_path": "/kb/x.py", "chunk_strategy": "code(python)", "symbol": "A"},
            ]
        }
        engine._backfill_file_metadata_from_vector_store()
        x = engine.metadata_manager.get_file_metadata("/kb/x.py")
        assert x.chunk_count == 3 and x.symbol_count == 2 and x.chunk_strategy == "code(python)"

    @patch("rag_engine.Ollama")
    @patch("rag_engine.OllamaEmbedding")
    @patch("rag_engine.chromadb.PersistentClient")
    def test_register_uses_per_file_stats(self, mock_chroma, mock_embed, mock_llm, tmp_path):
        """P4：登记优先使用本次实际切分统计（chunk_count / symbol_count / chunk_strategy）。"""
        from llama_index.core.schema import Document

        engine, _ = self._make_engine(mock_chroma, tmp_path / "meta")
        src = tmp_path / "m.py"
        src.write_text("def f():\n    return 1\n", encoding="utf-8")
        doc = Document(text=src.read_text(), metadata={"file_path": str(src), "file_name": "m.py", "file_type": ".py"})
        engine._register_file_metadata(
            [doc], [str(src)],
            per_file={str(src): {"chunk_count": 7, "symbol_count": 5, "chunk_strategy": "code(python)"}},
        )
        meta = engine.metadata_manager.get_file_metadata(str(src))
        assert meta.chunk_count == 7 and meta.symbol_count == 5 and meta.chunk_strategy == "code(python)"

    @patch("rag_engine.Ollama")
    @patch("rag_engine.OllamaEmbedding")
    @patch("rag_engine.chromadb.PersistentClient")
    def test_get_stats_includes_code_chunking(self, mock_chroma, mock_embed, mock_llm):
        mock_collection = MagicMock()
        mock_collection.count.return_value = 3
        mock_chroma.return_value.get_or_create_collection.return_value = mock_collection
        engine = RAGEngine()
        stats = engine.get_stats()
        assert "code_chunking" in stats and "code_chunk_max_chars" in stats
        assert "代码分块" in engine.get_stats_tool()

    @patch("rag_engine.Ollama")
    @patch("rag_engine.OllamaEmbedding")
    @patch("rag_engine.chromadb.PersistentClient")
    def test_backfill_does_not_overwrite_existing_metadata(
        self, mock_chroma, mock_embed, mock_llm, tmp_path
    ):
        from file_metadata import FilePersistenceType

        engine, mock_collection = self._make_engine(mock_chroma, tmp_path / "meta")
        # 预先登记一个文件并设定 chunk_count=99
        engine.metadata_manager.add_file("/kb/a.md", FilePersistenceType.PERMANENT)
        engine.metadata_manager.update_file_metadata("/kb/a.md", chunk_count=99)

        mock_collection.get.return_value = {
            "metadatas": [{"file_path": "/kb/a.md"}, {"file_path": "/kb/a.md"}]
        }
        engine._backfill_file_metadata_from_vector_store()

        # 不应覆盖既有计数
        a = engine.metadata_manager.get_file_metadata("/kb/a.md")
        assert a.chunk_count == 99


class TestRAGEngineDeriveKnowledgeGraph:
    """测试文档入库时派生构建知识图谱（图谱作为派生索引）。"""

    @patch("rag_engine.Ollama")
    @patch("rag_engine.OllamaEmbedding")
    @patch("rag_engine.chromadb.PersistentClient")
    def test_derive_empty_documents_returns_false(
        self, mock_chroma, mock_embed, mock_llm
    ):
        mock_chroma.return_value.get_or_create_collection.return_value = MagicMock()
        engine = RAGEngine()
        assert engine._derive_knowledge_graph([]) is False

    @patch("rag_engine.Ollama")
    @patch("rag_engine.OllamaEmbedding")
    @patch("rag_engine.chromadb.PersistentClient")
    def test_derive_builds_graph_from_documents(
        self, mock_chroma, mock_embed, mock_llm
    ):
        mock_chroma.return_value.get_or_create_collection.return_value = MagicMock()
        engine = RAGEngine()

        fake_builder = MagicMock()
        fake_builder.graph = object()  # networkx 可用
        fake_builder.add_document.return_value = True

        with patch("knowledge_graph.get_graph_builder", return_value=fake_builder):
            doc = MagicMock()
            doc.text = "Python is a language."
            doc.metadata = {"file_name": "a.txt", "doc_type": "text"}
            assert engine._derive_knowledge_graph([doc]) is True
            fake_builder.add_document.assert_called_once_with(
                "Python is a language.", "a.txt", "text"
            )

    @patch("rag_engine.Ollama")
    @patch("rag_engine.OllamaEmbedding")
    @patch("rag_engine.chromadb.PersistentClient")
    def test_derive_skips_empty_text(self, mock_chroma, mock_embed, mock_llm):
        mock_chroma.return_value.get_or_create_collection.return_value = MagicMock()
        engine = RAGEngine()

        fake_builder = MagicMock()
        fake_builder.graph = object()

        with patch("knowledge_graph.get_graph_builder", return_value=fake_builder):
            doc = MagicMock()
            doc.text = "   "
            doc.metadata = {}
            assert engine._derive_knowledge_graph([doc]) is False
            fake_builder.add_document.assert_not_called()

    @patch("rag_engine.Ollama")
    @patch("rag_engine.OllamaEmbedding")
    @patch("rag_engine.chromadb.PersistentClient")
    def test_derive_uses_get_content_when_no_text_attr(
        self, mock_chroma, mock_embed, mock_llm
    ):
        mock_chroma.return_value.get_or_create_collection.return_value = MagicMock()
        engine = RAGEngine()

        fake_builder = MagicMock()
        fake_builder.graph = object()
        fake_builder.add_document.return_value = True

        class Doc:
            metadata = {"source": "s.md"}

            def get_content(self):
                return "content via get_content"

        with patch("knowledge_graph.get_graph_builder", return_value=fake_builder):
            assert engine._derive_knowledge_graph([Doc()]) is True
            fake_builder.add_document.assert_called_once_with(
                "content via get_content", "s.md", "text"
            )

    @patch("rag_engine.Ollama")
    @patch("rag_engine.OllamaEmbedding")
    @patch("rag_engine.chromadb.PersistentClient")
    def test_derive_returns_false_when_networkx_unavailable(
        self, mock_chroma, mock_embed, mock_llm
    ):
        mock_chroma.return_value.get_or_create_collection.return_value = MagicMock()
        engine = RAGEngine()

        fake_builder = MagicMock()
        fake_builder.graph = None  # networkx 不可用

        with patch("knowledge_graph.get_graph_builder", return_value=fake_builder):
            doc = MagicMock()
            doc.text = "Python"
            doc.metadata = {}
            assert engine._derive_knowledge_graph([doc]) is False

    @patch("rag_engine.Ollama")
    @patch("rag_engine.OllamaEmbedding")
    @patch("rag_engine.chromadb.PersistentClient")
    def test_derive_exception_is_non_fatal(self, mock_chroma, mock_embed, mock_llm):
        mock_chroma.return_value.get_or_create_collection.return_value = MagicMock()
        engine = RAGEngine()

        with patch(
            "knowledge_graph.get_graph_builder", side_effect=RuntimeError("boom")
        ):
            doc = MagicMock()
            doc.text = "Python"
            doc.metadata = {}
            assert engine._derive_knowledge_graph([doc]) is False

    @patch("rag_engine.Ollama")
    @patch("rag_engine.OllamaEmbedding")
    @patch("rag_engine.chromadb.PersistentClient")
    def test_add_documents_sets_last_graph_derived(
        self, mock_chroma, mock_embed, mock_llm
    ):
        mock_chroma.return_value.get_or_create_collection.return_value = MagicMock()
        engine = RAGEngine()
        engine.index = MagicMock()
        engine.retriever = MagicMock()

        with patch.object(engine, "_persist_index"), patch.object(
            engine, "_register_file_metadata"
        ), patch.object(
            engine, "_derive_knowledge_graph", return_value=True
        ) as mock_derive:
            doc = MagicMock()
            engine.add_documents([doc])
            mock_derive.assert_called_once()
            assert engine.last_graph_derived is True

    @patch("rag_engine.Ollama")
    @patch("rag_engine.OllamaEmbedding")
    @patch("rag_engine.chromadb.PersistentClient")
    @patch("rag_engine.VectorStoreIndex")
    @patch("rag_engine.Settings")
    def test_build_index_sets_last_graph_derived(
        self, mock_settings, mock_index_cls, mock_chroma,
        mock_embed, mock_llm,
    ):
        mock_chroma.return_value.get_or_create_collection.return_value = MagicMock()
        mock_index_cls.from_documents.return_value = MagicMock()
        mock_index_cls.return_value = MagicMock()

        engine = RAGEngine()
        with patch.object(engine, "_register_file_metadata"), patch.object(
            engine, "_derive_knowledge_graph", return_value=True
        ) as mock_derive:
            engine.build_index([MagicMock()], persist=False)
            mock_derive.assert_called_once()
            assert engine.last_graph_derived is True


# ==================== F8 P2-4：hybrid 召回（BM25 + RRF）====================

def _mk_engine(mock_chroma, count=3, docs=None, metas=None):
    """构造带可控 chroma_collection 的引擎。"""
    mock_collection = MagicMock()
    mock_collection.count.return_value = count
    docs = docs if docs is not None else ["Cloudflare Tunnel 配置指南", "DJI Osmo 360 售价 2999 元", "Python 递归示例"]
    metas = metas if metas is not None else [
        {"file_name": "cf.md", "file_path": "/d/cf.md"},
        {"file_name": "dji.md", "file_path": "/d/dji.md"},
        {"file_name": "py.md", "file_path": "/d/py.md"},
    ]
    mock_collection.get.return_value = {"documents": docs, "metadatas": metas}
    mock_chroma.return_value.get_or_create_collection.return_value = mock_collection
    engine = RAGEngine()
    return engine, mock_collection


def _dense_response(items):
    """items: [(content, score, file_name, file_path)] → 检索器 ``retrieve`` 返回的 NodeWithScore 列表
    （F9 P0-1：引擎只检索不生成，故不再有 ``source_nodes``/``__str__`` 的 Response 对象）。"""
    nodes = []
    for content, score, fname, fpath in items:
        n = MagicMock()
        n.node.get_content.return_value = content
        n.node.metadata = {"file_name": fname, "file_path": fpath}
        n.score = score
        nodes.append(n)
    return nodes


class TestRRFFuse:
    def test_fuse_orders_and_labels(self):
        dense = [
            {"content": "A", "file": "a", "path": "/a", "score": 0.8},
            {"content": "B", "file": "b", "path": "/b", "score": 0.7},
        ]
        sparse = [
            {"content": "B", "file": "b", "path": "/b", "bm25_score": 5.0},
            {"content": "C", "file": "c", "path": "/c", "bm25_score": 3.0},
        ]
        fused = RAGEngine.rrf_fuse(dense, sparse, top_k=10)
        # B 两路都命中 → 最高；A（dense 第 1）与 C（bm25 第 2）分别为 1/61、1/62
        assert [s["content"] for s in fused] == ["B", "A", "C"]
        by = {s["content"]: s for s in fused}
        assert by["B"]["retriever"] == "hybrid" and by["B"]["score"] == 0.7 and by["B"]["bm25_score"] == 5.0
        assert by["A"]["retriever"] == "dense" and by["A"]["score"] == 0.8
        assert by["C"]["retriever"] == "bm25"
        # bm25-only 的 score = rrf / (2/(k+1))，上限 0.5：能过 0.45 粗筛但不触发 0.6 跳过线
        assert 0.45 < by["C"]["score"] < 0.5
        assert by["B"]["rrf"] == round(1 / 62 + 1 / 61, 6)  # dense 第 2 + bm25 第 1

    def test_fuse_respects_top_k(self):
        dense = [{"content": f"d{i}", "file": "f", "path": "/f", "score": 0.9 - i * 0.01} for i in range(5)]
        sparse = [{"content": f"s{i}", "file": "f", "path": "/f"} for i in range(5)]
        fused = RAGEngine.rrf_fuse(dense, sparse, top_k=4)
        assert len(fused) == 4

    def test_bm25_only_rank1_score_is_half(self):
        fused = RAGEngine.rrf_fuse([], [{"content": "x", "file": "f", "path": "/f"}], top_k=5)
        assert fused[0]["score"] == 0.5 and fused[0]["retriever"] == "bm25"

    def test_tokenize_mixed(self):
        toks = RAGEngine._bm25_tokenize("DJI Osmo 售价")
        assert "dji" in toks and "osmo" in toks and "售" in toks and "售价" in toks
        assert RAGEngine._bm25_tokenize("") == []

    def test_tokenize_splits_identifiers(self):
        """P4：snake_case / camelCase 保留原词并追加子词。"""
        toks = RAGEngine._bm25_tokenize("def _ensure_bm25(self): getUserName HTTPServer")
        assert "_ensure_bm25" in toks and "ensure" in toks and "bm25" in toks
        assert "getusername" in toks and "get" in toks and "user" in toks and "name" in toks
        assert "httpserver" in toks and "http" in toks and "server" in toks
        # 普通单词不重复
        assert RAGEngine._bm25_tokenize("hello").count("hello") == 1

    def test_rrf_key_uses_start_line_for_code_chunks(self):
        """P4：代码块以 (path, L起始行) 去重，相似函数头前 500 字相同也不会误合并。"""
        same_head = "def handler(self, request):\n    # 相同开头\n" + "x" * 600
        dense = [
            {"content": same_head, "file": "a.py", "path": "/a.py", "score": 0.7, "start_line": 10, "end_line": 30},
            {"content": same_head, "file": "a.py", "path": "/a.py", "score": 0.6, "start_line": 50, "end_line": 70},
        ]
        sparse = [{"content": same_head, "file": "a.py", "path": "/a.py", "start_line": 50, "bm25_score": 3.0}]
        fused = RAGEngine.rrf_fuse(dense, sparse, top_k=5)
        assert len(fused) == 2
        by_line = {f["start_line"]: f for f in fused}
        assert by_line[50]["retriever"] == "hybrid" and by_line[10]["retriever"] == "dense"

    def test_make_source_strips_header_and_exposes_code_fields(self):
        meta = {"file_name": "a.py", "file_path": "/a.py", "symbol": "Engine.run", "start_line": 12,
                "end_line": 20, "language": "python", "chunk_strategy": "code(python)", "part": "1/2"}
        src = RAGEngine._make_source("# a.py · Engine.run · L12-L20\n    def run(self):\n        pass", meta, score=0.8)
        assert src["content"].startswith("    def run(self):")
        assert src["symbol"] == "Engine.run" and src["start_line"] == 12 and src["end_line"] == 20
        assert src["language"] == "python" and src["chunk_strategy"] == "code(python)" and src["part"] == "1/2"
        assert src["score"] == 0.8 and src["file"] == "a.py"
        plain = RAGEngine._make_source("普通文本", {"file_name": "a.md"})
        assert plain == {"content": "普通文本", "score": None, "file": "a.md", "path": ""}
        bad = RAGEngine._make_source("x", {"file_name": "a.py", "start_line": "abc"})
        assert "start_line" not in bad


class TestHybridQuery:
    @patch("rag_engine.Ollama")
    @patch("rag_engine.OllamaEmbedding")
    @patch("rag_engine.chromadb.PersistentClient")
    def test_hybrid_merges_bm25_hit_missing_from_dense(self, mock_chroma, mock_embed, mock_llm):
        pytest.importorskip("rank_bm25")
        engine, coll = _mk_engine(mock_chroma)
        engine.hybrid_enabled = True
        engine.retriever = MagicMock()
        engine.retriever.retrieve.return_value = _dense_response([
            ("Cloudflare Tunnel 配置指南", 0.5, "cf.md", "/d/cf.md"),
        ])
        events = []
        result = engine.query_with_sources("DJI Osmo 售价", progress_callback=lambda e: events.append(e))
        assert result["hybrid"] is True
        files = [s["file"] for s in result["sources"]]
        assert "dji.md" in files  # BM25 关键词命中补进来
        dji = next(s for s in result["sources"] if s["file"] == "dji.md")
        assert dji["retriever"] == "bm25" and 0 < dji["score"] <= 0.5
        cf = next(s for s in result["sources"] if s["file"] == "cf.md")
        assert cf["retriever"] == "dense" and cf["score"] == 0.5
        assert any(e["phase"] == "hybrid" for e in events)
        coll.get.assert_called_once_with(include=["documents", "metadatas"])

    @patch("rag_engine.Ollama")
    @patch("rag_engine.OllamaEmbedding")
    @patch("rag_engine.chromadb.PersistentClient")
    def test_bm25_index_lazy_and_invalidated(self, mock_chroma, mock_embed, mock_llm):
        pytest.importorskip("rank_bm25")
        engine, coll = _mk_engine(mock_chroma)
        engine.hybrid_enabled = True
        engine.retriever = MagicMock()
        engine.retriever.retrieve.return_value = _dense_response([])
        engine.query_with_sources("售价")
        engine.query_with_sources("售价")
        assert coll.get.call_count == 1  # 第二次复用缓存
        # 入库后"已就位"缓存失效；MagicMock 文档切分失败 → 回退路径拿不到 chunk id → store 标记 stale
        # → 下次查询全量重建一次（F10 P2-1：能拿到节点的正常路径为增量 upsert，见 test_bm25_store_integration）
        engine.index = MagicMock()
        engine.security_scanner = None
        engine.metadata_manager = None
        engine.auto_snapshot_trigger = None
        engine._derive_knowledge_graph = lambda docs: False
        engine._persist_index = lambda: None
        engine.add_documents([MagicMock()])
        assert engine._bm25 is None
        engine.query_with_sources("售价")
        assert coll.get.call_count == 2
        # 清空后失效
        engine.chroma_client = MagicMock()
        engine.clear_index()
        assert engine._bm25 is None

    @patch("rag_engine.Ollama")
    @patch("rag_engine.OllamaEmbedding")
    @patch("rag_engine.chromadb.PersistentClient")
    def test_remove_file_invalidates_bm25(self, mock_chroma, mock_embed, mock_llm):
        engine, coll = _mk_engine(mock_chroma)
        engine._bm25 = {"index": object(), "entries": []}
        engine.metadata_manager = None
        engine.index = None
        coll.get.return_value = {"metadatas": [{"file_path": "/d/cf.md", "file_name": "cf.md"}]}
        engine.remove_file("/d/cf.md")
        assert engine._bm25 is None

    @patch("rag_engine.Ollama")
    @patch("rag_engine.OllamaEmbedding")
    @patch("rag_engine.chromadb.PersistentClient")
    def test_too_many_chunks_disables_hybrid_with_hint(self, mock_chroma, mock_embed, mock_llm):
        pytest.importorskip("rank_bm25")
        import rag_engine as rag_module
        limit = rag_module.RAG_HYBRID_MAX_CHUNKS  # F10 P2-1-b：默认上限由 20000 提到 50000，这里跟随常量
        engine, coll = _mk_engine(mock_chroma, count=limit + 1)
        engine.hybrid_enabled = True
        engine.retriever = MagicMock()
        engine.retriever.retrieve.return_value = _dense_response([("x", 0.5, "a", "/a")])
        events = []
        result = engine.query_with_sources("q", progress_callback=lambda e: events.append(e))
        assert result["hybrid"] is False
        assert any(e["phase"] == "hybrid_off" and str(limit) in e["message"] for e in events)
        coll.get.assert_not_called()
        assert str(limit + 1) in (engine._bm25_disabled_reason or "")
        # F10 P2-1-b：关闭原因随结果 meta 返回，并给出可调的环境变量
        assert result["meta"]["hybrid_requested"] is True
        assert "RAG_HYBRID_MAX_CHUNKS" in result["meta"]["hybrid_disabled_reason"]
        # 已记录关闭原因 → 后续不再重复检查（bm25_store 惰性属性在超限前不会被创建，count 只查一次）
        engine.query_with_sources("q")
        assert coll.count.call_count == 1

    @patch("rag_engine.Ollama")
    @patch("rag_engine.OllamaEmbedding")
    @patch("rag_engine.chromadb.PersistentClient")
    def test_missing_rank_bm25_falls_back_dense_silently(self, mock_chroma, mock_embed, mock_llm, monkeypatch):
        monkeypatch.setitem(sys.modules, "rank_bm25", None)
        engine, coll = _mk_engine(mock_chroma)
        engine.hybrid_enabled = True
        engine.retriever = MagicMock()
        engine.retriever.retrieve.return_value = _dense_response([("x", 0.5, "a", "/a")])
        events = []
        result = engine.query_with_sources("q", progress_callback=lambda e: events.append(e))
        assert result["hybrid"] is False
        assert [s["file"] for s in result["sources"]] == ["a"]
        assert "retriever" not in result["sources"][0]
        assert not any(e["phase"] in ("hybrid", "hybrid_off") for e in events)
        coll.get.assert_not_called()

    @patch("rag_engine.Ollama")
    @patch("rag_engine.OllamaEmbedding")
    @patch("rag_engine.chromadb.PersistentClient")
    def test_hybrid_explicit_false_and_env_default(self, mock_chroma, mock_embed, mock_llm):
        engine, coll = _mk_engine(mock_chroma)
        engine.retriever = MagicMock()
        engine.retriever.retrieve.return_value = _dense_response([("x", 0.5, "a", "/a")])
        result = engine.query_with_sources("q", hybrid=False)
        assert result["hybrid"] is False
        coll.get.assert_not_called()
        import config
        assert engine.hybrid_enabled == bool(config.RAG_HYBRID)

    @patch("rag_engine.Ollama")
    @patch("rag_engine.OllamaEmbedding")
    @patch("rag_engine.chromadb.PersistentClient")
    def test_empty_collection_or_bad_data_falls_back(self, mock_chroma, mock_embed, mock_llm):
        pytest.importorskip("rank_bm25")
        engine, coll = _mk_engine(mock_chroma, docs=[], metas=[])
        engine.hybrid_enabled = True
        engine.retriever = MagicMock()
        engine.retriever.retrieve.return_value = _dense_response([("x", 0.5, "a", "/a")])
        assert engine.query_with_sources("q")["hybrid"] is False
        # get() 抛错 → 记录原因、回退 dense
        engine.invalidate_bm25()
        coll.get.side_effect = RuntimeError("boom")
        assert engine.query_with_sources("q")["hybrid"] is False
        assert "BM25 构建失败" in engine._bm25_disabled_reason

    @patch("rag_engine.Ollama")
    @patch("rag_engine.OllamaEmbedding")
    @patch("rag_engine.chromadb.PersistentClient")
    def test_bm25_search_no_tokens_or_zero_scores(self, mock_chroma, mock_embed, mock_llm):
        pytest.importorskip("rank_bm25")
        engine, coll = _mk_engine(mock_chroma)
        assert engine._bm25_search("q", 5) == []  # 未构建
        assert engine._ensure_bm25() is True
        assert engine._bm25_search("", 5) == []
        assert engine._bm25_search("完全不相关的词汇组合", 5) == [] or all(
            s["bm25_score"] > 0 for s in engine._bm25_search("完全不相关的词汇组合", 5)
        )
