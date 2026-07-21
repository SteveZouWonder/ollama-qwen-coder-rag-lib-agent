#!/usr/bin/env python3
"""test_rag_pipeline.py — 共享 RAG 编排层单元测试。

``rag_pipeline`` 是 CLI 与 Web 复用的知识库问答核心。本测试在不启动真实
Ollama/ChromaDB 的前提下，用桩引擎与打桩的 LLM/网络工具覆盖关键分支：
元查询直答、知识库命中、0 命中回退、进度事件透传。
"""
from unittest.mock import MagicMock

import rag_pipeline


class FakeRAG:
    def __init__(self, query_engine=object(), result=None):
        self.query_engine = query_engine
        self._result = result or {
            "answer": "答案", "sources": [{"content": "c", "file": "f.md"}]
        }
        self.stats = {"total_documents": 5, "embed_model": "bge"}

    def query_with_sources(self, question, progress_callback=None):
        if progress_callback:
            progress_callback({"phase": "retrieving", "message": "检索"})
        return self._result

    def get_stats(self):
        return self.stats


# ==================== 元查询 ====================

class TestMetaQuery:
    def test_is_meta_query_true(self):
        assert rag_pipeline.is_meta_query("知识库里有什么")
        assert rag_pipeline.is_meta_query("list files")

    def test_is_meta_query_false(self):
        assert not rag_pipeline.is_meta_query("什么是向量检索")

    def test_is_meta_query_variants(self):
        # 正则组合应覆盖固定短语之外的变体
        assert rag_pipeline.is_meta_query("现在的知识库里面有哪些信息？")
        assert rag_pipeline.is_meta_query("知识库里面都有些什么资料")
        assert rag_pipeline.is_meta_query("当前知识库包含哪些文档")
        assert rag_pipeline.is_meta_query("知识库收录了哪些内容")
        assert rag_pipeline.is_meta_query("库中记录了哪些数据")

    def test_is_meta_query_not_task(self):
        # "用知识库里的资料写总结"是任务而非概览查询
        assert not rag_pipeline.is_meta_query("用知识库里的资料帮我写篇总结")
        # 具体主题问题不算元查询
        assert not rag_pipeline.is_meta_query("DJI OSMO360的最新售价")

    def test_answer_meta_returns_overview(self, monkeypatch):
        # 打桩 file_metadata，避免依赖真实元数据
        import sys
        fake_mod = MagicMock()
        mgr = MagicMock()
        mgr.list_files.return_value = []
        fake_mod.get_global_metadata_manager.return_value = mgr
        monkeypatch.setitem(sys.modules, "file_metadata", fake_mod)

        events = []
        result = rag_pipeline.answer_question(
            FakeRAG(), "知识库里有什么", enable_web_search=False,
            progress=lambda e: events.append(e),
        )
        assert result["kind"] == "meta"
        assert result["answer"] == "[知识库概览]"
        assert any(e["stage"] == "meta_overview" for e in events)


# ==================== 生成回答 ====================

class TestAnswerQuestion:
    def test_kb_hit_no_web(self):
        result = rag_pipeline.answer_question(
            FakeRAG(), "问题", enable_web_search=False,
        )
        assert result["kind"] == "answer"
        assert result["answer"] == "答案"
        assert result["kb_sources"][0]["file"] == "f.md"
        assert result["web_sources"] == []

    def test_kb_empty_fallback_to_model(self, monkeypatch):
        # 空命中：sources 为空
        rag = FakeRAG(result={"answer": "Empty Response", "sources": []})
        # 打桩 LLM 直答
        monkeypatch.setattr(rag_pipeline, "llm_direct_answer", lambda p: "模型回答")
        # 打桩回退网络搜索为空
        monkeypatch.setattr(rag_pipeline, "simple_web_search", lambda q: "")
        result = rag_pipeline.answer_question(
            rag, "冷门问题", enable_web_search=False,
        )
        assert result["kind"] == "answer"
        assert "模型回答" in result["answer"]
        assert result["kb_sources"] == []

    def test_low_relevance_source_treated_as_miss(self, monkeypatch):
        """低相关片段（低于阈值）应被过滤，视为 0 命中并回退网络/模型。

        复现截图问题：问"某产品售价"却命中 0.398 分的无关片段。过滤后应不把
        该片段计入知识库来源，改走网络/模型回答。
        """
        rag = FakeRAG(result={
            "answer": "这段无关内容",
            "sources": [{"content": "http_status:404", "file": "cloudflare.md", "score": 0.398}],
        })
        monkeypatch.setattr(rag_pipeline, "llm_direct_answer", lambda p: "基于网络的回答")
        monkeypatch.setattr(rag_pipeline, "simple_web_search", lambda q: "网络结果")
        result = rag_pipeline.answer_question(
            rag, "某产品售价", enable_web_search=False,
        )
        # 低分片段被过滤 → 知识库来源为空 → 走网络回退
        assert result["kb_sources"] == []
        assert "网络" in result["answer"] or "基于网络的回答" in result["answer"]

    def test_relevant_source_kept(self, monkeypatch):
        """高相关片段（>= 阈值）应保留并命中知识库。"""
        rag = FakeRAG(result={
            "answer": "知识库原始答案",
            "sources": [{"content": "相关内容", "file": "doc.md", "score": 0.72}],
        })
        result = rag_pipeline.answer_question(
            rag, "相关问题", enable_web_search=False,
        )
        assert len(result["kb_sources"]) == 1
        assert result["kb_sources"][0]["score"] == 0.72
        # 无过滤、无网络 → 快路径沿用原始答案
        assert result["answer"] == "知识库原始答案"

    def test_progress_events_emitted(self, monkeypatch):
        rag = FakeRAG()
        events = []
        rag_pipeline.answer_question(
            rag, "问题", enable_web_search=False,
            progress=lambda e: events.append(e),
            rag_progress_callback=lambda e: events.append(e),
        )
        stages = {e.get("stage") or e.get("phase") for e in events}
        assert "kb_retrieving" in stages

    def test_edge_score_noise_judged_irrelevant(self, monkeypatch):
        """复现本轮问题：0.452 分的 Cloudflare 片段勉强过阈值，但 LLM 判为无关
        → 视为未命中，不把噪音当依据，改走网络/模型回答。"""
        rag = FakeRAG(result={
            "answer": "http_status:404 是兜底规则",
            "sources": [{
                "content": "Cloudflare Tunnel 内网穿透配置 http_status:404 兜底规则",
                "file": "cloudflare-tunnel-guide_v2.md", "score": 0.452,
            }],
        })
        # LLM 相关性判定：判为不相关
        monkeypatch.setattr(rag_pipeline, "judge_kb_relevance", lambda q, s: False)
        monkeypatch.setattr(rag_pipeline, "llm_direct_answer", lambda p: "2999元（来自网络）")
        monkeypatch.setattr(rag_pipeline, "simple_web_search", lambda q: "京东 2999元")
        result = rag_pipeline.answer_question(
            rag, "中国国内dji OSMO360的最新售价", enable_web_search=False,
        )
        # 噪音片段不应作为知识库来源
        assert result["kb_sources"] == []
        assert "cloudflare" not in str(result["kb_sources"]).lower()

    def test_edge_score_relevant_kept(self, monkeypatch):
        """同为边缘分数（0.452），但 LLM 判为相关时应保留并用知识库回答。"""
        rag = FakeRAG(result={
            "answer": "知识库答案",
            "sources": [{"content": "相关内容", "file": "doc.md", "score": 0.452}],
        })
        monkeypatch.setattr(rag_pipeline, "judge_kb_relevance", lambda q, s: True)
        result = rag_pipeline.answer_question(
            rag, "相关问题", enable_web_search=False,
        )
        assert len(result["kb_sources"]) == 1
        assert result["answer"] == "知识库答案"


# ==================== LLM 相关性判定 ====================

class TestJudgeKbRelevance:
    def test_empty_sources(self):
        assert rag_pipeline.judge_kb_relevance("q", []) is False

    def test_high_score_skips_llm(self, monkeypatch):
        # 最高分 >= 0.6 直接判相关，不调用 LLM
        called = {"n": 0}

        def _boom(*a, **k):
            called["n"] += 1
            raise AssertionError("不应调用 LLM")
        import sys, types
        monkeypatch.setitem(sys.modules, "llama_index.core",
                            types.SimpleNamespace(Settings=types.SimpleNamespace(llm=_boom)))
        assert rag_pipeline.judge_kb_relevance("q", [{"content": "x", "score": 0.72}]) is True
        assert called["n"] == 0

    def _patch_llm(self, monkeypatch, reply):
        import sys, types

        class _LLM:
            def complete(self, prompt):
                return reply
        monkeypatch.setitem(sys.modules, "llama_index.core",
                            types.SimpleNamespace(Settings=types.SimpleNamespace(llm=_LLM())))

    def test_llm_irrelevant(self, monkeypatch):
        self._patch_llm(monkeypatch, "irrelevant")
        assert rag_pipeline.judge_kb_relevance(
            "DJI售价", [{"content": "Cloudflare 配置", "score": 0.45}]
        ) is False

    def test_llm_relevant(self, monkeypatch):
        self._patch_llm(monkeypatch, "relevant")
        assert rag_pipeline.judge_kb_relevance(
            "深度学习", [{"content": "深度学习综述", "score": 0.45}]
        ) is True

    def test_llm_failure_conservative_true(self, monkeypatch):
        # LLM 抛错时保守视为相关（不误杀真实命中）
        import sys, types

        class _LLM:
            def complete(self, prompt):
                raise RuntimeError("llm down")
        monkeypatch.setitem(sys.modules, "llama_index.core",
                            types.SimpleNamespace(Settings=types.SimpleNamespace(llm=_LLM())))
        assert rag_pipeline.judge_kb_relevance(
            "q", [{"content": "x", "score": 0.45}]
        ) is True


# ==================== 纯函数 ====================

class TestHelpers:
    def test_parse_web_sources(self):
        text = "1. 标题A\n   URL: https://a.com\n2. 标题B\n   URL: https://b.com"
        srcs = rag_pipeline.parse_web_sources(text)
        assert len(srcs) == 2
        assert srcs[0] == {"title": "标题A", "url": "https://a.com"}

    def test_is_empty_rag_result(self):
        assert rag_pipeline.is_empty_rag_result({"answer": "Empty Response", "sources": []})
        assert not rag_pipeline.is_empty_rag_result(
            {"answer": "x", "sources": [{"file": "f"}]}
        )

    def test_synthesize_prompt_contains_sections(self):
        p = rag_pipeline.synthesize_prompt("问题", "KB内容", "网络内容")
        assert "知识库检索内容" in p and "网络搜索补充" in p and "问题" in p

    def test_strip_json_fence(self):
        assert rag_pipeline._strip_json_fence('```json\n{"a":1}\n```') == '{"a":1}'

    def test_filter_relevant_sources(self):
        sources = [
            {"file": "a", "score": 0.72},   # 保留
            {"file": "b", "score": 0.398},  # 过滤（低于 0.45）
            {"file": "c", "score": None},   # 无分数：保守保留
        ]
        kept = rag_pipeline.filter_relevant_sources(sources, threshold=0.45)
        files = [s["file"] for s in kept]
        assert "a" in files and "c" in files
        assert "b" not in files

    def test_filter_relevant_sources_empty(self):
        assert rag_pipeline.filter_relevant_sources([]) == []

    def test_is_domestic_query(self):
        assert rag_pipeline._is_domestic_query("中国国内dji OSMO360的最新售价")
        assert rag_pipeline._is_domestic_query("京东上的价格是多少")
        # 纯英文不算国内查询
        assert not rag_pipeline._is_domestic_query("dji osmo360 price")
        # 中文但无国内语境词
        assert not rag_pipeline._is_domestic_query("什么是向量检索")

    def test_is_mostly_ascii(self):
        assert rag_pipeline._is_mostly_ascii("dji osmo 360 price")
        assert not rag_pipeline._is_mostly_ascii("大疆售价")

    def test_plan_web_search_domestic_drops_english(self, monkeypatch):
        """国内查询应剔除 LLM 仍可能给出的英文查询。"""
        import json as _json

        class _FakeLLM:
            def complete(self, prompt):
                # 模拟 LLM 同时返回中文与英文查询
                return _json.dumps({
                    "needs_search": True,
                    "queries": ["DJI OSMO360 售价", "DJI Osmo 360 price"],
                })

        import types
        fake_settings = types.SimpleNamespace(llm=_FakeLLM())
        monkeypatch.setitem(
            __import__("sys").modules, "llama_index.core",
            types.SimpleNamespace(Settings=fake_settings),
        )
        plan = rag_pipeline.plan_web_search("中国国内dji OSMO360的最新售价")
        assert plan["needs_search"] is True
        # 只保留中文查询
        assert all(not rag_pipeline._is_mostly_ascii(q) for q in plan["queries"])
        assert any("售价" in q for q in plan["queries"])
