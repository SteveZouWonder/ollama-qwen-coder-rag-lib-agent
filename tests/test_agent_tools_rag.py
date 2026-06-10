#!/usr/bin/env python3
"""
test_agent_tools_rag.py — RAG 工具单元测试（注入 Mock 引擎）
"""
import pytest
from agent_tools import query_knowledge_base, add_to_knowledge_base, get_knowledge_stats, set_rag_engine


class TestRAGToolsWithoutEngine:
    """测试未注入引擎时的错误处理"""

    def test_query_without_engine(self):
        set_rag_engine(None)
        result = query_knowledge_base("什么是RAG？")
        assert "[错误] 知识库引擎未初始化" in result

    def test_add_without_engine(self):
        set_rag_engine(None)
        result = add_to_knowledge_base("./file.pdf")
        assert "[错误] 知识库引擎未初始化" in result

    def test_stats_without_engine(self):
        set_rag_engine(None)
        result = get_knowledge_stats()
        assert "[错误] 知识库引擎未初始化" in result


class TestRAGToolsWithEngine:
    """测试注入 Mock 引擎后的行为"""

    def test_query_with_engine(self, mock_rag_engine):
        set_rag_engine(mock_rag_engine)
        result = query_knowledge_base("什么是RAG？")
        assert result == "[Mock] 知识库查询结果"
        mock_rag_engine.query_tool.assert_called_once_with("什么是RAG？")

    def test_add_with_engine(self, mock_rag_engine):
        set_rag_engine(mock_rag_engine)
        result = add_to_knowledge_base("./论文.pdf")
        assert result == "[Mock] 文档已添加"
        mock_rag_engine.add_document_tool.assert_called_once_with("./论文.pdf")

    def test_stats_with_engine(self, mock_rag_engine):
        set_rag_engine(mock_rag_engine)
        result = get_knowledge_stats()
        assert result == "[Mock] 统计信息"
        mock_rag_engine.get_stats_tool.assert_called_once()

    def test_query_with_exception(self, mock_rag_engine):
        mock_rag_engine.query_tool.side_effect = RuntimeError("boom")
        set_rag_engine(mock_rag_engine)
        result = query_knowledge_base("test")
        assert "[错误] 知识库查询失败" in result
        assert "boom" in result

    def test_add_with_exception(self, mock_rag_engine):
        mock_rag_engine.add_document_tool.side_effect = ValueError("bad path")
        set_rag_engine(mock_rag_engine)
        result = add_to_knowledge_base("bad")
        assert "[错误] 添加文档失败" in result
