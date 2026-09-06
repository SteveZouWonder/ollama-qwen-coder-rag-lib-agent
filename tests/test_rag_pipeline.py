#!/usr/bin/env python3
"""test_rag_pipeline.py — 共享 RAG 编排层单元测试。

``rag_pipeline`` 是 CLI 与 Web 复用的知识库问答核心。本测试在不启动真实
Ollama/ChromaDB 的前提下，用桩引擎与打桩的 LLM/网络工具覆盖关键分支：
元查询直答、知识库命中、0 命中回退、进度事件透传。
"""
from unittest.mock import MagicMock

import pytest

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
        # P2-5：知识库无相关片段且网络无结果 → kind="fallback"，答案末尾附 /agent 建议
        assert result["kind"] == "fallback"
        assert "模型回答" in result["answer"]
        assert "/agent 冷门问题" in result["answer"]
        assert result["fallback_question"] == "冷门问题"
        assert result["kb_sources"] == []

    def test_kb_only_miss_skips_web_and_model_fallback(self, monkeypatch):
        """kb_only=True（Agent 工具）：未命中时不联网、不调模型兜底，直接返回空来源。"""
        rag = FakeRAG(result={"answer": "Empty Response", "sources": []})
        calls = []
        monkeypatch.setattr(rag_pipeline, "llm_direct_answer", lambda p: calls.append("llm") or "x")
        monkeypatch.setattr(rag_pipeline, "simple_web_search", lambda q: calls.append("web") or "y")
        events = []
        result = rag_pipeline.answer_question(
            rag, "冷门问题", enable_web_search=False, kb_only=True,
            progress=lambda e: events.append(e["stage"]),
        )
        assert result["answer"] == "" and result["kb_sources"] == []
        assert calls == []
        assert "kb_empty" in events

    def test_kb_only_uninitialized_returns_empty(self, monkeypatch):
        rag = FakeRAG(query_engine=None)
        monkeypatch.setattr(rag_pipeline, "llm_direct_answer", lambda p: pytest.fail("不应调用模型"))
        result = rag_pipeline.answer_question(rag, "问题", enable_web_search=False, kb_only=True)
        assert result["answer"] == "" and result["kb_sources"] == []

    def test_kb_only_hit_returns_sources(self):
        rag = FakeRAG(result={"answer": "命中答案", "sources": [{"content": "相关", "file": "d.md", "score": 0.8}]})
        result = rag_pipeline.answer_question(rag, "问题", enable_web_search=False, kb_only=True)
        assert result["answer"] == "命中答案" and len(result["kb_sources"]) == 1

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
    @pytest.fixture(autouse=True)
    def _force_default_llm(self, monkeypatch):
        # 单模型架构下综合/判定始终走全局 Settings.llm（测试里被打桩）。
        monkeypatch.setattr(rag_pipeline, "_get_synthesis_llm",
                            lambda: None, raising=False)

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


# ==================== 单模型架构：综合/判定复用全局模型 ====================

class TestSynthesisModel:
    """单模型架构下，综合/判定不再有独立模型，始终复用全局 Settings.llm。"""

    def test_get_synthesis_llm_always_none(self):
        """_get_synthesis_llm 恒返回 None（表示用全局 Settings.llm）。"""
        assert rag_pipeline._get_synthesis_llm() is None

    def test_reset_is_noop(self):
        """reset_synthesis_llm 为兼容保留的空操作，调用后仍返回 None。"""
        rag_pipeline.reset_synthesis_llm()
        assert rag_pipeline._get_synthesis_llm() is None

    def test_complete_uses_global_llm(self, monkeypatch):
        """_complete 应使用全局 Settings.llm 执行补全。"""
        import sys, types

        class _LLM:
            def complete(self, prompt):
                return "global-answer"
        monkeypatch.setitem(sys.modules, "llama_index.core",
                            types.SimpleNamespace(Settings=types.SimpleNamespace(llm=_LLM())))
        assert rag_pipeline._complete("hi") == "global-answer"


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

    def test_synthesize_prompt_has_accuracy_methodology(self):
        """综合 prompt 应包含通用准确回答方法论的关键指令。"""
        p = rag_pipeline.synthesize_prompt("现在dji osmo 360售价", "", "直降1177元")
        # 意图理解、忠实提取、数字带限定语、冲突处理
        assert "理解意图" in p or "真正问的是什么" in p
        assert "忠实提取" in p or "不要脑补" in p or "不要臆测" in p
        # 关键：区分优惠额与售价的通用指令
        assert "优惠额" in p or "降价额" in p or "到手价" in p
        assert "无法确定" in p  # 不确定时如实说明

    def test_synthesize_prompt_multi_value_enrichment(self):
        """多个取值时应要求丰富展开并解释差异原因。"""
        p = rag_pipeline.synthesize_prompt("售价", "", "多个价格")
        assert "解释" in p and "差异" in p  # 解释差异原因
        assert "分条" in p or "分点" in p  # 结构化组织
        assert "限定条件" in p  # 每条标注条件

    def test_compact_web_context_ranks_and_trims(self):
        """精简上下文应按匹配度排序、保留最相关条目。"""
        text = (
            "搜索结果 (3 条):\n"
            "1. 无关 Cloudflare 配置\n   URL: https://z.com\n   摘要: http_status 404 兜底\n"
            "2. dji osmo 360 售价2999\n   URL: https://a.com\n   摘要: 标准套装售价 2999 元起\n"
            "3. 其它\n   URL: https://c.com\n   摘要: 随便\n"
        )
        out = rag_pipeline.compact_web_context(text, "dji osmo 360 最新售价")
        # 相关条目应排在前面
        assert out.index("2999") < out.index("Cloudflare")
        assert "相关网页摘要" in out

    def test_compact_web_context_empty_question(self):
        # 无 question 时退化为截断原文
        out = rag_pipeline.compact_web_context("一些文本", "")
        assert out == "一些文本"

    def test_compact_web_context_empty(self):
        assert rag_pipeline.compact_web_context("", "q") == ""

    def test_parse_search_items(self):
        text = (
            "搜索结果 (2 条):\n"
            "1. 大疆 Osmo 360 售价2999元\n"
            "   URL: https://a.com\n"
            "   来源: baidu\n"
            "   摘要: 标准套装售价 2999 元\n"
            "2. 活动直降1177\n"
            "   URL: https://b.com\n"
            "   摘要: 至高直降 1177 元\n"
        )
        items = rag_pipeline._parse_search_items(text)
        assert len(items) == 2
        assert items[0]["url"] == "https://a.com"
        assert "2999" in items[0]["snippet"]
        assert items[1]["url"] == "https://b.com"

    def test_match_score(self):
        # 问题 token 命中越多分越高
        s_hi = rag_pipeline._match_score("dji osmo 360 售价", "dji osmo 360 标准套装售价 2999")
        s_lo = rag_pipeline._match_score("dji osmo 360 售价", "Cloudflare 内网穿透配置")
        assert s_hi > s_lo
        assert rag_pipeline._match_score("", "任意") == 0.0

    def test_enrich_picks_high_match_pages(self, monkeypatch):
        """enrich 应按匹配度选页：相关页(a.com)被抓、无关页(z.com)被跳过。"""
        text = (
            "1. dji osmo 360 售价\n   URL: https://a.com\n   摘要: dji osmo 360 售价 2999 元\n"
            "2. 无关内容\n   URL: https://z.com\n   摘要: Cloudflare 内网穿透 http_status 404\n"
        )
        fetched = []

        def fake_extract(url, timeout=10):
            fetched.append(url)
            return f"正文内容 {url}"

        import sys, types
        monkeypatch.setitem(sys.modules, "agent_tools",
                            types.SimpleNamespace(web_content_extract=fake_extract))
        out = rag_pipeline.enrich_with_page_content(text, question="dji osmo 360 最新售价")
        # 相关页被抓取，无关页（低于阈值）被跳过
        assert fetched == ["https://a.com"]
        assert "相关页面详细信息" in out

    def test_enrich_fallback_without_question(self, monkeypatch):
        """无 question 时退化为取前 N 个 URL（保持向后兼容）。"""
        text = "1. t\n   URL: https://a.com\n   摘要: x\n"
        fetched = []
        import sys, types
        monkeypatch.setitem(sys.modules, "agent_tools",
                            types.SimpleNamespace(
                                web_content_extract=lambda u, timeout=10: (fetched.append(u), "正文")[1]))
        rag_pipeline.enrich_with_page_content(text, question="")
        assert fetched == ["https://a.com"]

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


# ==================== 进度可见性与取消 ====================

class TestProgressVisibilityAndCancel:
    """Web 端"只看到正在处理"的根因：链路首个模型调用（搜索规划）前没有任何
    进度事件。现在应在调用前发出 ``web_plan``；同时支持 ``should_stop`` 取消。"""

    @staticmethod
    def _patch_llm(monkeypatch, reply: str):
        import types

        class _FakeLLM:
            def complete(self, prompt):
                return reply

        monkeypatch.setitem(
            __import__("sys").modules, "llama_index.core",
            types.SimpleNamespace(Settings=types.SimpleNamespace(llm=_FakeLLM())),
        )

    def test_plan_web_search_emits_before_llm_call(self, monkeypatch):
        import json as _json

        events = []
        self._patch_llm(monkeypatch, _json.dumps({"needs_search": False, "queries": []}))
        rag_pipeline.plan_web_search("什么是递归", progress=lambda e: events.append(e))
        assert events and events[0]["stage"] == "web_plan"

    def test_augment_reports_skip_when_no_search_needed(self, monkeypatch):
        import json as _json

        events = []
        self._patch_llm(monkeypatch, _json.dumps({"needs_search": False, "queries": []}))
        out = rag_pipeline.augment_with_web_search("什么是递归", progress=lambda e: events.append(e))
        assert out == ""
        stages = [e["stage"] for e in events]
        assert stages == ["web_plan", "web_plan_skip"]

    def test_web_plan_is_first_event_in_full_pipeline(self, monkeypatch):
        import json as _json

        events = []
        self._patch_llm(monkeypatch, _json.dumps({"needs_search": False, "queries": []}))
        rag_pipeline.answer_question(
            FakeRAG(), "问题", enable_web_search=True,
            progress=lambda e: events.append(e),
        )
        assert events[0]["stage"] == "web_plan"

    def test_should_stop_before_start_raises(self):
        with pytest.raises(rag_pipeline.PipelineCancelled):
            rag_pipeline.answer_question(
                FakeRAG(), "问题", enable_web_search=False, should_stop=lambda: True,
            )

    def test_should_stop_after_retrieval_aborts_before_synthesis(self, monkeypatch):
        """检索完成后用户停止：不应再进入相关性判定/综合等模型调用。"""
        calls = {"llm": 0}

        def fake_direct(prompt):
            calls["llm"] += 1
            return "x"

        monkeypatch.setattr(rag_pipeline, "llm_direct_answer", fake_direct)
        monkeypatch.setattr(rag_pipeline, "judge_kb_relevance", lambda q, s: (_ for _ in ()).throw(AssertionError("不应调用")))

        state = {"retrieved": False}

        class RAG(FakeRAG):
            def query_with_sources(self, question, progress_callback=None):
                state["retrieved"] = True
                return {"answer": "a", "sources": [{"content": "c", "file": "f", "score": 0.9}]}

        with pytest.raises(rag_pipeline.PipelineCancelled):
            rag_pipeline.answer_question(
                RAG(), "问题", enable_web_search=False,
                should_stop=lambda: state["retrieved"],
            )
        assert calls["llm"] == 0

    def test_should_stop_probe_error_is_ignored(self):
        def bad_probe():
            raise RuntimeError("probe boom")

        result = rag_pipeline.answer_question(
            FakeRAG(), "问题", enable_web_search=False, should_stop=bad_probe,
        )
        assert result["kind"] == "answer"

    def test_cancel_during_web_search_propagates(self, monkeypatch):
        import json as _json

        self._patch_llm(monkeypatch, _json.dumps({"needs_search": True, "queries": ["q"]}))
        monkeypatch.setattr(rag_pipeline, "run_web_search", lambda queries, progress=None: "结果")
        state = {"planned": False}

        def probe():
            # 规划完成（第一次检查）后置位
            was = state["planned"]
            state["planned"] = True
            return was

        with pytest.raises(rag_pipeline.PipelineCancelled):
            rag_pipeline.augment_with_web_search("最新新闻", should_stop=probe)


# ==================== F8 P2：检索规划 / 多跳 / 编号引用 / thinking / fallback ====================

def _patch_settings_llm(monkeypatch, fn):
    """把 ``llama_index.core.Settings.llm.complete`` 打桩为 ``fn(prompt) -> str|obj``。"""
    import types

    class _FakeLLM:
        def complete(self, prompt):
            return fn(prompt)

    monkeypatch.setitem(
        __import__("sys").modules, "llama_index.core",
        types.SimpleNamespace(Settings=types.SimpleNamespace(llm=_FakeLLM())),
    )


class TestPlanRetrieval:
    def test_parses_complex_plan(self, monkeypatch):
        import json as _json
        _patch_settings_llm(monkeypatch, lambda p: _json.dumps({
            "complex": True,
            "subquestions": ["A 的价格", "B 的价格", " A 的价格 ", "C", "D"],
            "needs_search": True,
            "queries": ["A 价格", "B 价格"],
        }))
        events = []
        plan = rag_pipeline.plan_retrieval("A 与 B 的价格差多少", progress=lambda e: events.append(e))
        assert plan["complex"] is True
        assert plan["subquestions"] == ["A 的价格", "B 的价格", "C"]  # 去重 + ≤3
        assert plan["needs_search"] is True and plan["queries"] == ["A 价格", "B 价格"]
        assert events[0]["stage"] == "web_plan"
        assert any(e["stage"] == "kb_decompose" and e["subquestions"] == plan["subquestions"] for e in events)

    def test_complex_with_single_subquestion_downgrades(self, monkeypatch):
        import json as _json
        _patch_settings_llm(monkeypatch, lambda p: _json.dumps({
            "complex": True, "subquestions": ["只有一个"], "needs_search": False, "queries": [],
        }))
        plan = rag_pipeline.plan_retrieval("q")
        assert plan["complex"] is False and plan["subquestions"] == []

    def test_simple_plan(self, monkeypatch):
        import json as _json
        _patch_settings_llm(monkeypatch, lambda p: "```json\n" + _json.dumps({
            "complex": False, "subquestions": [], "needs_search": False, "queries": [],
        }) + "\n```")
        plan = rag_pipeline.plan_retrieval("什么是递归")
        assert plan == {"complex": False, "subquestions": [], "needs_search": False, "queries": []}

    def test_needs_search_without_queries_uses_question(self, monkeypatch):
        _patch_settings_llm(monkeypatch, lambda p: '{"needs_search": true}')
        plan = rag_pipeline.plan_retrieval("最新版本")
        assert plan["queries"] == ["最新版本"] and plan["complex"] is False

    def test_llm_failure_falls_back_to_heuristics(self, monkeypatch):
        def boom(p):
            raise RuntimeError("down")
        _patch_settings_llm(monkeypatch, boom)
        plan = rag_pipeline.plan_retrieval("最新版本是什么")
        assert plan == {"complex": False, "subquestions": [], "needs_search": True, "queries": ["最新版本是什么"]}
        assert rag_pipeline.plan_retrieval("写一首诗")["needs_search"] is False

    def test_plan_web_search_wrapper_is_single_call(self, monkeypatch):
        calls = []

        def fake(p):
            calls.append(p)
            return '{"complex": false, "subquestions": [], "needs_search": true, "queries": ["x"]}'
        _patch_settings_llm(monkeypatch, fake)
        plan = rag_pipeline.plan_web_search("q")
        assert plan == {"needs_search": True, "queries": ["x"]}
        assert len(calls) == 1

    def test_prompt_contains_schema_and_domestic_rule(self):
        p = rag_pipeline.build_retrieval_plan_prompt("国内 dji 售价")
        assert '"complex"' in p and '"subquestions"' in p and '"needs_search"' in p and '"queries"' in p
        assert "请勿生成英文查询" in p
        assert "请勿生成英文查询" not in rag_pipeline.build_retrieval_plan_prompt("what is rag")


class _CountingRAG(FakeRAG):
    """记录 query_with_sources 被调用的问题列表。"""

    def __init__(self, results=None, default=None):
        super().__init__(result=default)
        self.results = results or {}
        self.queries = []

    def query_with_sources(self, question, progress_callback=None):
        self.queries.append(question)
        return self.results.get(question, self._result)


class TestLLMCallBudgetAndMultiHop:
    def test_simple_question_call_count_unchanged(self, monkeypatch):
        """简单问题（联网开、无需搜索）：规划 1 + rerank ≤1 + 综合 ≤1，且无多余调用。"""
        import rag_rerank
        settings_calls = []

        def settings_llm(p):
            settings_calls.append(p)
            return '{"complex": false, "subquestions": [], "needs_search": false, "queries": []}'
        _patch_settings_llm(monkeypatch, settings_llm)

        rerank_calls = []

        def rerank_llm(p):
            rerank_calls.append(p)
            return '{"keep":[1],"notes":{"1":"相关"}}'
        monkeypatch.setattr(rag_rerank, "_llm_complete", rerank_llm)

        direct = []
        monkeypatch.setattr(rag_pipeline, "llm_direct_answer", lambda p: direct.append(p) or "综合")

        rag = _CountingRAG(default={"answer": "原答案", "sources": [{"content": "c", "file": "f.md", "score": 0.5}]})
        result = rag_pipeline.answer_question(rag, "简单问题", enable_web_search=True)
        assert rag.queries == ["简单问题"]  # 单跳：只检索一次
        assert len(settings_calls) == 1     # 规划 1 次（分解 + 搜索规划合并）
        assert len(rerank_calls) == 1       # rerank 1 次
        assert direct == []                 # 快路径：无过滤/无网络 → 不再综合
        assert result["answer"] == "原答案"
        assert result["kb_sources"][0]["ref"] == "1" and result["kb_sources"][0]["rerank_note"] == "相关"

    def test_complex_question_multi_hop_dedup(self, monkeypatch):
        import rag_rerank
        _patch_settings_llm(monkeypatch, lambda p: (
            '{"complex": true, "subquestions": ["A 的价格", "B 的价格"], "needs_search": false, "queries": []}'
        ))
        monkeypatch.setattr(rag_rerank, "_llm_complete", lambda p: '{"keep":[1,2,3]}')
        prompts = []
        monkeypatch.setattr(rag_pipeline, "llm_direct_answer", lambda p: prompts.append(p) or "A 比 B 贵 1000 元[1][2]")

        shared = {"content": "共同片段", "file": "common.md", "score": 0.7}
        rag = _CountingRAG(results={
            "A 的价格": {"answer": "A 2999", "sources": [
                {"content": "A 售价 2999", "file": "a.md", "score": 0.8}, dict(shared),
            ]},
            "B 的价格": {"answer": "B 1999", "sources": [
                {"content": "B 售价 1999", "file": "b.md", "score": 0.75}, dict(shared),
            ]},
        })
        events = []
        result = rag_pipeline.answer_question(
            rag, "A 与 B 的价格差多少", enable_web_search=False, progress=lambda e: events.append(e),
        )
        assert rag.queries == ["A 的价格", "B 的价格"]
        files = [s["file"] for s in result["kb_sources"]]
        assert sorted(files) == ["a.md", "b.md", "common.md"]  # 按 (file, content) 去重
        assert [s["ref"] for s in result["kb_sources"]] == ["1", "2", "3"]
        # 多跳必须综合（不能沿用某个子问题的原始答案）
        assert len(prompts) == 1 and "[1]" in prompts[0] and "[2]" in prompts[0] and "[3]" in prompts[0]
        assert result["answer"].endswith("[1][2]")
        stages = [e["stage"] for e in events]
        assert "kb_decompose" in stages and "kb_merged" in stages
        assert sum(1 for s in stages if s == "kb_retrieving") == 2

    def test_web_off_still_decomposes_but_no_search(self, monkeypatch):
        import rag_rerank
        _patch_settings_llm(monkeypatch, lambda p: (
            '{"complex": true, "subquestions": ["s1", "s2"], "needs_search": true, "queries": ["q"]}'
        ))
        monkeypatch.setattr(rag_rerank, "_llm_complete", lambda p: '{"keep":[1]}')
        monkeypatch.setattr(rag_pipeline, "llm_direct_answer", lambda p: "ok")
        monkeypatch.setattr(rag_pipeline, "run_web_search", lambda *a, **k: pytest.fail("不应联网"))
        rag = _CountingRAG(default={"answer": "a", "sources": [{"content": "c", "file": "f", "score": 0.5}]})
        result = rag_pipeline.answer_question(rag, "复合", enable_web_search=False)
        assert rag.queries == ["s1", "s2"]
        assert result["web_sources"] == []

    def test_kb_uninitialized_web_off_skips_planning(self, monkeypatch):
        _patch_settings_llm(monkeypatch, lambda p: pytest.fail("不应规划"))
        monkeypatch.setattr(rag_pipeline, "llm_direct_answer", lambda p: "模型回答")
        result = rag_pipeline.answer_question(FakeRAG(query_engine=None), "q", enable_web_search=False)
        assert result["kind"] == "answer" and "模型回答" in result["answer"]

    def test_rerank_drops_some_then_synthesizes(self, monkeypatch):
        import rag_rerank
        monkeypatch.setattr(rag_rerank, "_llm_complete", lambda p: '{"keep":[2],"notes":{"2":"含答案"}}')
        prompts = []
        monkeypatch.setattr(rag_pipeline, "llm_direct_answer", lambda p: prompts.append(p) or "答[1]")
        rag = FakeRAG(result={"answer": "原答案", "sources": [
            {"content": "噪音", "file": "n.md", "score": 0.5},
            {"content": "有用", "file": "u.md", "score": 0.5},
        ]})
        events = []
        result = rag_pipeline.answer_question(rag, "q", enable_web_search=False, progress=lambda e: events.append(e))
        assert [s["file"] for s in result["kb_sources"]] == ["u.md"]
        assert result["kb_sources"][0]["ref"] == "1"
        assert len(prompts) == 1 and "[1]（来自 u.md）" in prompts[0] and "n.md" not in prompts[0]
        assert any(e["stage"] == "rerank_done" and e["kept"] == 1 for e in events)

    def test_rerank_all_dropped_is_miss(self, monkeypatch):
        import rag_rerank
        monkeypatch.setattr(rag_rerank, "_llm_complete", lambda p: '{"keep":[]}')
        monkeypatch.setattr(rag_pipeline, "llm_direct_answer", lambda p: "网络答")
        monkeypatch.setattr(rag_pipeline, "simple_web_search", lambda q: "1. 标题\n   URL: http://x\n   摘要: y")
        rag = FakeRAG(result={"answer": "原答案", "sources": [{"content": "噪音", "file": "n.md", "score": 0.5}]})
        events = []
        result = rag_pipeline.answer_question(rag, "q", enable_web_search=False, progress=lambda e: events.append(e))
        assert result["kb_sources"] == [] and result["kind"] == "answer"
        assert "kb_irrelevant" in [e["stage"] for e in events]
        # 回退搜索得到的网络来源也被编号并返回
        assert result["web_sources"] and result["web_sources"][0]["ref"] == "W1"

    def test_hybrid_bm25_source_forces_synthesis(self, monkeypatch):
        prompts = []
        monkeypatch.setattr(rag_pipeline, "llm_direct_answer", lambda p: prompts.append(p) or "综合")
        rag = FakeRAG(result={"answer": "原答案", "sources": [
            {"content": "向量命中", "file": "d.md", "score": 0.8, "retriever": "dense"},
            {"content": "关键词命中", "file": "k.md", "score": 0.5, "retriever": "bm25"},
        ]})
        result = rag_pipeline.answer_question(rag, "q", enable_web_search=False)
        assert result["answer"] == "综合" and len(prompts) == 1


class TestNumberedCitations:
    def test_format_kb_context_numbering(self):
        srcs = [{"content": "甲", "file": "a.md"}, {"content": "", "file": "skip.md"}, {"content": "丙", "file": "c.md"}]
        ctx = rag_pipeline.format_kb_context(srcs)
        assert ctx.startswith("[1]（来自 a.md）\n甲")
        assert "[3]（来自 c.md）\n丙" in ctx and "[2]" not in ctx  # 空内容占号不输出
        assert srcs[0]["ref"] == "1" and srcs[2]["ref"] == "3"

    def test_assign_refs(self):
        kb, web = rag_pipeline.assign_refs([{"a": 1}, {"b": 2}], [{"url": "u"}])
        assert [s["ref"] for s in kb] == ["1", "2"] and web[0]["ref"] == "W1"

    def test_synthesize_prompt_requires_citations(self):
        p = rag_pipeline.synthesize_prompt("q", "[1]（来自 a.md）\n甲", "[W1] 网页")
        assert "[W1]" in p and "末尾必须标注" in p and "不要标注不存在的编号" in p

    def test_compact_web_context_labels_w_refs(self):
        text = (
            "搜索结果:\n1. 标题一\n   URL: http://a\n   摘要: 售价 2999\n"
            "2. 标题二\n   URL: http://b\n   摘要: 其他\n"
            "=== 相关页面详细信息 ===\n--- 页面 1: http://b ---\n正文 B\n"
        )
        web_sources = rag_pipeline.parse_web_sources(text)
        ctx = rag_pipeline.compact_web_context(text, "售价", web_sources)
        assert "[W1] 标题一" in ctx and "[W2] 标题二" in ctx
        assert "[W2] http://b ---" in ctx
        assert web_sources[0]["ref"] == "W1" and web_sources[1]["ref"] == "W2"

    def test_compact_web_context_without_sources_keeps_numbers(self):
        text = "1. 标题一\n   URL: http://a\n   摘要: 售价 2999\n"
        ctx = rag_pipeline.compact_web_context(text, "售价")
        assert "1. 标题一" in ctx

    def test_answer_question_refs_kb_and_web(self, monkeypatch):
        import rag_rerank
        _patch_settings_llm(monkeypatch, lambda p: '{"complex": false, "needs_search": true, "queries": ["q"]}')
        monkeypatch.setattr(rag_rerank, "_llm_complete", lambda p: '{"keep":[1]}')
        monkeypatch.setattr(rag_pipeline, "run_web_search", lambda queries, progress=None: "1. 网页\n   URL: http://w\n   摘要: 最新 3.2")
        monkeypatch.setattr(rag_pipeline, "enrich_with_page_content", lambda r, question="", progress=None: r)
        prompts = []
        monkeypatch.setattr(rag_pipeline, "llm_direct_answer", lambda p: prompts.append(p) or "售价 2999[1]，最新 3.2[W1]")
        rag = FakeRAG(result={"answer": "原答案", "sources": [{"content": "售价 2999", "file": "a.md", "score": 0.5}]})
        result = rag_pipeline.answer_question(rag, "q", enable_web_search=True)
        assert result["kb_sources"][0]["ref"] == "1"
        assert result["web_sources"][0]["ref"] == "W1" and result["web_sources"][0]["url"] == "http://w"
        assert "[1]" in result["answer"] and "[W1]" in result["answer"]
        assert "[1]（来自 a.md）" in prompts[0] and "[W1] 网页" in prompts[0]


class TestThinkingEvents:
    def test_extract_thinking_from_raw(self):
        class R:
            raw = {"message": {"thinking": "先想想", "content": "答"}}

            def __str__(self):
                return "答"
        assert rag_pipeline.extract_thinking(R()) == "先想想"

    def test_extract_thinking_from_additional_kwargs_and_blocks(self):
        class R1:
            raw = None
            additional_kwargs = {"thinking": "kw"}
        assert rag_pipeline.extract_thinking(R1()) == "kw"

        class ThinkingBlock:
            content = "blk"

        class Msg:
            blocks = [ThinkingBlock()]

        class R2:
            raw = {}
            additional_kwargs = {}
            message = Msg()
        assert rag_pipeline.extract_thinking(R2()) == "blk"
        assert rag_pipeline.extract_thinking("plain") == ""
        assert rag_pipeline.extract_thinking(None) == ""

    def test_thinking_emitted_when_think_on_and_truncated(self, monkeypatch):
        class R:
            raw = {"message": {"thinking": "思" * 1000, "content": "综合答案"}}

            def __str__(self):
                return "综合答案"
        _patch_settings_llm(monkeypatch, lambda p: R())

        rag = FakeRAG(result={"answer": "原答案", "sources": [
            {"content": "噪音", "file": "n.md", "score": 0.5}, {"content": "有用", "file": "u.md", "score": 0.5},
        ]})
        rag.llm_think = True
        import rag_rerank
        monkeypatch.setattr(rag_rerank, "_llm_complete", lambda p: '{"keep":[2]}')
        events = []
        result = rag_pipeline.answer_question(
            rag, "q", enable_web_search=False, progress=lambda e: events.append(e),
        )
        thinking = [e for e in events if e["stage"] == "thinking"]
        # 规划 + 综合各一次 → 两次 thinking；每条截断 800 字（+ 省略号）
        assert len(thinking) == 2
        assert all(len(e["thinking"]) == 801 and e["truncated"] for e in thinking)
        assert all(e["message"].startswith("🧠 模型思考：") for e in thinking)
        assert result["answer"] == "综合答案"

    def test_thinking_not_emitted_when_think_off(self, monkeypatch):
        class R:
            raw = {"message": {"thinking": "秘密", "content": "答"}}

            def __str__(self):
                return "答"
        _patch_settings_llm(monkeypatch, lambda p: R())
        rag = FakeRAG(result={"answer": "原答案", "sources": [{"content": "c", "file": "f", "score": 0.9}]})
        rag.llm_think = False
        events = []
        rag_pipeline.answer_question(rag, "q", enable_web_search=False, progress=lambda e: events.append(e))
        assert not any(e["stage"] == "thinking" for e in events)


class TestFallbackKind:
    def test_fallback_when_kb_miss_and_no_web(self, monkeypatch):
        monkeypatch.setattr(rag_pipeline, "llm_direct_answer", lambda p: "模型自答")
        monkeypatch.setattr(rag_pipeline, "simple_web_search", lambda q: "")
        rag = FakeRAG(result={"answer": "Empty Response", "sources": []})
        events = []
        result = rag_pipeline.answer_question(rag, "冷门", enable_web_search=False, progress=lambda e: events.append(e))
        assert result["kind"] == "fallback"
        assert result["answer"].rstrip().endswith(rag_pipeline.fallback_suggestion("冷门"))
        assert result["fallback_question"] == "冷门"
        assert any(e["stage"] == "fallback" and e["question"] == "冷门" for e in events)

    def test_no_fallback_when_web_has_results(self, monkeypatch):
        monkeypatch.setattr(rag_pipeline, "llm_direct_answer", lambda p: "网络答")
        monkeypatch.setattr(rag_pipeline, "simple_web_search", lambda q: "1. t\n   URL: http://x\n   摘要: y")
        rag = FakeRAG(result={"answer": "Empty Response", "sources": []})
        result = rag_pipeline.answer_question(rag, "q", enable_web_search=False)
        assert result["kind"] == "answer" and "fallback_question" not in result
        assert "/agent" not in result["answer"]

    def test_kb_only_miss_is_not_fallback(self, monkeypatch):
        rag = FakeRAG(result={"answer": "Empty Response", "sources": []})
        result = rag_pipeline.answer_question(rag, "q", enable_web_search=False, kb_only=True)
        assert result["kind"] == "answer" and result["answer"] == ""

    def test_uninitialized_kb_no_web_is_plain_answer(self, monkeypatch):
        monkeypatch.setattr(rag_pipeline, "llm_direct_answer", lambda p: "模型答")
        result = rag_pipeline.answer_question(FakeRAG(query_engine=None), "q", enable_web_search=False)
        assert result["kind"] == "answer"
