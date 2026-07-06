#!/usr/bin/env python3
"""
test_query_interface_answer_strategy.py

覆盖方案 B 回答策略相关纯函数：
- 元/概览类问题识别（_is_meta_query）
- 网络来源结构化解析（_parse_web_sources）
- 知识库/网络分区综合 prompt 组装（_synthesize_prompt）
- 知识库上下文格式化（_format_kb_context）
"""
import pytest
import query_interface as qi


class TestIsMetaQuery:
    @pytest.mark.parametrize("q", [
        "现在的知识库里面有哪些东西？",
        "知识库里有什么",
        "知识库中有哪些文档",
        "列出文件",
        "文件列表",
        "有哪些文档",
        "what is in the knowledge base",
        "list files",
    ])
    def test_meta_queries_detected(self, q):
        assert qi._is_meta_query(q) is True

    @pytest.mark.parametrize("q", [
        "Cloudflare Tunnel 怎么配置",
        "解释一下这段代码",
        "帮我总结这份报告的结论",
        "",
    ])
    def test_non_meta_queries(self, q):
        assert qi._is_meta_query(q) is False


class TestParseWebSources:
    def test_parse_standard_text_format(self):
        text = (
            "搜索结果 (2 条):\n"
            "============================================================\n"
            "\n1. 标题A\n"
            "   URL: https://example.com/a\n"
            "   来源: web | 相关性: 0.90\n"
            "   摘要: ...\n"
            "\n2. 标题B\n"
            "   URL: https://example.com/b\n"
            "   来源: web | 相关性: 0.80\n"
            "   摘要: ...\n"
        )
        srcs = qi._parse_web_sources(text)
        assert srcs == [
            {"title": "标题A", "url": "https://example.com/a"},
            {"title": "标题B", "url": "https://example.com/b"},
        ]

    def test_empty_input(self):
        assert qi._parse_web_sources("") == []
        assert qi._parse_web_sources(None) == []

    def test_url_without_title_falls_back_to_url(self):
        text = "   URL: https://only-url.example\n"
        srcs = qi._parse_web_sources(text)
        assert srcs == [{"title": "https://only-url.example", "url": "https://only-url.example"}]


class TestSynthesizePrompt:
    def test_both_contexts_present(self):
        p = qi._synthesize_prompt("问题X", kb_context="KB内容", web_context="WEB内容")
        assert "【知识库检索内容】" in p
        assert "KB内容" in p
        assert "【网络搜索补充】" in p
        assert "WEB内容" in p
        assert "问题X" in p

    def test_empty_kb_context(self):
        p = qi._synthesize_prompt("问题Y", kb_context="", web_context="W")
        assert "【知识库检索内容】\n（无相关内容）" in p

    def test_empty_web_context(self):
        p = qi._synthesize_prompt("问题Z", kb_context="K", web_context="")
        assert "【网络搜索补充】\n（无）" in p


class TestFormatKbContext:
    def test_format_with_files(self):
        ctx = qi._format_kb_context([
            {"file": "a.md", "content": "内容1"},
            {"file": "b.md", "content": "内容2"},
        ])
        assert "来自 a.md" in ctx
        assert "内容1" in ctx
        assert "来自 b.md" in ctx
        assert "内容2" in ctx

    def test_skip_empty_content(self):
        ctx = qi._format_kb_context([
            {"file": "a.md", "content": ""},
            {"file": "b.md", "content": "有内容"},
        ])
        assert "a.md" not in ctx
        assert "有内容" in ctx

    def test_missing_file_key(self):
        ctx = qi._format_kb_context([{"content": "x"}])
        assert "未知文件" in ctx
