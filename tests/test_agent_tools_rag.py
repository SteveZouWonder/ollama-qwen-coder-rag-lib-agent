#!/usr/bin/env python3
"""
test_agent_tools_rag.py — RAG 工具单元测试（注入 Mock 引擎）
"""
from unittest.mock import patch

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


def _hit_result(n=3, answer="RAG 是检索增强生成"):
    return {
        "kind": "answer",
        "answer": answer,
        "kb_sources": [
            {"content": f"片段{i}正文 " * 60, "score": 0.9 - i * 0.1, "file": f"doc{i}.pdf", "path": f"/kb/doc{i}.pdf"}
            for i in range(1, n + 1)
        ],
        "web_sources": [], "meta": None, "rewritten": None,
    }


class TestRAGToolsWithEngine:
    """测试注入 Mock 引擎后的行为（P1-6：query_knowledge_base 改走 answer_question）"""

    def test_query_routes_through_answer_question(self, mock_rag_engine):
        set_rag_engine(mock_rag_engine)
        with patch("rag_pipeline.answer_question", return_value=_hit_result()) as aq:
            result = query_knowledge_base("什么是RAG？")
        aq.assert_called_once()
        args, kwargs = aq.call_args
        assert args == (mock_rag_engine, "什么是RAG？")
        assert kwargs["enable_web_search"] is False
        assert kwargs["show_progress"] is False
        assert kwargs["kb_only"] is True
        mock_rag_engine.query_tool.assert_not_called()
        # 答案 + 相关性结论 + top-3 片段（含文件名，每条 ≤300 字）
        assert "[知识库命中] 相关性判定：通过（3 个相关片段，最高相关度 0.80）" in result
        assert "答案：\nRAG 是检索增强生成" in result
        assert "[doc1.pdf]" in result and "[doc2.pdf]" in result and "[doc3.pdf]" in result
        assert "相关度 0.80" in result
        for line in result.splitlines():
            if line.startswith("1. ["):
                body = line.split("） ", 1)[1]
                assert len(body) <= 301  # 300 字 + 省略号

    def test_query_limits_to_top3_snippets(self, mock_rag_engine):
        set_rag_engine(mock_rag_engine)
        with patch("rag_pipeline.answer_question", return_value=_hit_result(n=5)):
            result = query_knowledge_base("q")
        assert "5 个相关片段" in result
        assert "[doc3.pdf]" in result and "[doc4.pdf]" not in result
        assert "top-3" in result

    def test_query_no_relevant_content(self, mock_rag_engine):
        set_rag_engine(mock_rag_engine)
        miss = {"kind": "answer", "answer": "⚠️ 知识库中无相关内容…", "kb_sources": [],
                "web_sources": [], "meta": None, "rewritten": None}
        with patch("rag_pipeline.answer_question", return_value=miss):
            result = query_knowledge_base("今天股价")
        assert result.startswith("[知识库无相关内容]")
        assert "web_search" in result
        assert "⚠️" not in result  # 不把兜底答案回灌模型

    def test_query_meta_overview(self, mock_rag_engine):
        set_rag_engine(mock_rag_engine)
        meta = {"kind": "meta", "answer": "[知识库概览]", "kb_sources": [], "web_sources": [],
                "meta": {"files": [{"path": "/kb/a.pdf", "size": "1.2 MB"}], "stats": {"total_documents": 42}},
                "rewritten": None}
        with patch("rag_pipeline.answer_question", return_value=meta):
            result = query_knowledge_base("知识库里有什么")
        assert result.startswith("[知识库概览]")
        assert "文档块数: 42" in result and "a.pdf (1.2 MB)" in result

    def test_format_kb_tool_result_edge_cases(self):
        from agent_tools import format_kb_tool_result
        assert format_kb_tool_result(None) == "[知识库无相关内容]"
        assert "暂无文件" in format_kb_tool_result({"kind": "meta", "meta": {}})
        # 缺 score / 缺 content 的来源也能渲染
        out = format_kb_tool_result({"kind": "answer", "answer": "", "kb_sources": [{"file_name": "x.md"}]})
        assert "[x.md]" in out and "（无正文）" in out and "（无综合答案）" in out
        assert "最高相关度" not in out
        # 超过 20 个文件折叠
        many = {"kind": "meta", "meta": {"files": [{"path": f"/f{i}.md", "size": "1K"} for i in range(25)]}}
        assert "另有 5 个文件" in format_kb_tool_result(many)

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
        set_rag_engine(mock_rag_engine)
        with patch("rag_pipeline.answer_question", side_effect=RuntimeError("boom")):
            result = query_knowledge_base("test")
        assert "[错误] 知识库查询失败" in result
        assert "boom" in result

    def test_add_with_exception(self, mock_rag_engine):
        mock_rag_engine.add_document_tool.side_effect = ValueError("bad path")
        set_rag_engine(mock_rag_engine)
        result = add_to_knowledge_base("bad")
        assert "[错误] 添加文档失败" in result


class TestKbToolResultP2Compat:
    """F8 P2：kb_sources 新增 ref/rerank_note/retriever 字段与 kind=fallback 不影响工具回灌文本。"""

    def test_ref_fields_tolerated(self):
        from agent_tools import format_kb_tool_result
        result = _hit_result(n=2)
        for i, s in enumerate(result["kb_sources"], 1):
            s["ref"] = str(i)
            s["rerank_note"] = "相关"
            s["retriever"] = "bm25"
        out = format_kb_tool_result(result)
        assert "[知识库命中]" in out and "1. [doc1.pdf]" in out and "2. [doc2.pdf]" in out

    def test_fallback_kind_without_sources_is_miss(self):
        from agent_tools import format_kb_tool_result, KB_NO_RELEVANT_MARK
        out = format_kb_tool_result({"kind": "fallback", "answer": "x 建议：/agent q", "kb_sources": []})
        assert out.startswith(KB_NO_RELEVANT_MARK)
