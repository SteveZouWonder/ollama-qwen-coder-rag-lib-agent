#!/usr/bin/env python3
"""scripts/eval_rag.py 单测（F10 P1-3）：参数解析 / 环境变量映射 / 建库与逐例运行（打桩引擎）/ 报告 I/O 与 Δ。

**不调用真实 Ollama**：``RAGEngine`` / ``load_documents`` / ``answer_question`` 全部打桩；``main`` 标 no cover。
"""
import importlib.util
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

SCRIPT = Path(__file__).parent.parent / "scripts" / "eval_rag.py"


@pytest.fixture(scope="module")
def mod():
    spec = importlib.util.spec_from_file_location("eval_rag", SCRIPT)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class FakeEngine:
    """query_with_sources 按问题关键字返回预设来源；记录 hybrid 参数。"""

    def __init__(self, table=None, fail_on=None):
        self.table = table or {}
        self.fail_on = fail_on or set()
        self.calls = []
        self.hybrid_enabled = None
        self.retriever = object()
        self.chroma_collection = SimpleNamespace(count=lambda: 7)
        self.built = None

    def query_with_sources(self, question, progress_callback=None, hybrid=None):
        self.calls.append(("retrieve", question, hybrid))
        if question in self.fail_on:
            raise ConnectionError("no ollama")
        return {"answer": "", "sources": list(self.table.get(question, [])), "hybrid": bool(hybrid)}

    def build_index(self, documents, persist=True, file_paths=None, progress_callback=None):
        self.built = {"n": len(documents), "persist": persist, "file_paths": file_paths}


# ==================== 参数与环境 ====================

class TestArgs:
    def test_help(self, mod, capsys):
        with pytest.raises(SystemExit) as e:
            mod.build_parser().parse_args(["--help"])
        assert e.value.code == 0
        out = capsys.readouterr().out
        for flag in ("--hybrid", "--rerank", "--top-k", "--tag", "--cases", "--limit", "--type", "--corpus", "--out-dir"):
            assert flag in out

    def test_choices_enforced(self, mod):
        p = mod.build_parser()
        with pytest.raises(SystemExit):
            p.parse_args(["--hybrid", "maybe"])
        with pytest.raises(SystemExit):
            p.parse_args(["--rerank", "bm25"])
        with pytest.raises(SystemExit):
            p.parse_args(["--type", "weird"])
        args = p.parse_args(["--hybrid", "off", "--rerank", "none", "--top-k", "5", "--tag", "x", "--type", "negative",
                             "--limit", "2", "-v", "--debug"])
        assert (args.hybrid, args.rerank, args.top_k, args.tag, args.case_type, args.limit) == ("off", "none", 5, "x", "negative", 2)
        assert args.verbose and args.debug
        assert args.cases.endswith("rag_eval_cases.json") and args.corpus.endswith("rag_eval_corpus")
        assert args.out_dir.endswith(os.path.join("docs", "development", "rag-eval", "reports"))

    def test_apply_env_maps_flags(self, mod, monkeypatch):
        for k in ("LLM_MODEL", "TOP_K", "RAG_HYBRID", "RERANKER"):
            monkeypatch.delenv(k, raising=False)
        args = mod.build_parser().parse_args(["--hybrid", "off", "--rerank", "cross-encoder", "--top-k", "7", "--model", "m:1b"])
        mod.apply_env(args)
        assert os.environ["RAG_HYBRID"] == "false" and os.environ["RERANKER"] == "cross-encoder"
        assert os.environ["TOP_K"] == "7" and os.environ["LLM_MODEL"] == "m:1b"

    def test_apply_env_none_rerank_and_defaults_untouched(self, mod, monkeypatch):
        for k in ("LLM_MODEL", "TOP_K", "RAG_HYBRID", "RERANKER"):
            monkeypatch.delenv(k, raising=False)
        mod.apply_env(mod.build_parser().parse_args(["--rerank", "none", "--hybrid", "on"]))
        assert "RERANKER" not in os.environ  # none 不写环境变量，靠 disable_rerank 打桩
        assert os.environ["RAG_HYBRID"] == "true"
        assert "TOP_K" not in os.environ and "LLM_MODEL" not in os.environ

    def test_resolve_settings_defaults_from_config(self, mod, monkeypatch):
        import config
        monkeypatch.setattr(config, "RAG_HYBRID", False, raising=False)
        monkeypatch.setattr(config, "RERANKER", "llm", raising=False)
        monkeypatch.setattr(config, "TOP_K", 10, raising=False)
        monkeypatch.setattr(config, "LLM_MODEL", "qwen-test", raising=False)
        s = mod.resolve_settings(mod.build_parser().parse_args([]))
        assert s["hybrid"] == "off" and s["rerank"] == "llm" and s["top_k"] == 10
        assert s["tag"] == "hybrid-off" and s["model"] == "qwen-test"
        s2 = mod.resolve_settings(mod.build_parser().parse_args(["--hybrid", "on", "--rerank", "none", "--top-k", "3", "--tag", "T"]))
        assert (s2["hybrid"], s2["rerank"], s2["top_k"], s2["tag"]) == ("on", "none", 3, "T")


# ==================== 隔离 / 建库 / rerank 打桩 ====================

class TestIsolationAndBuild:
    def test_isolate_runtime_state_redirects_everything(self, mod, tmp_path):
        import runtime_paths as rp
        import file_metadata as fm
        import knowledge_graph.graph_builder as gb

        mod.isolate_runtime_state(tmp_path)
        assert str(rp.app_state_dir("knowledge")).startswith(str(tmp_path / "app_state"))
        assert str(fm._global_metadata_manager.storage_path).startswith(str(tmp_path / "file_metadata"))
        assert str(gb._graph_builder.persist_path) == str(tmp_path / "graph.json")

    def test_isolate_tolerates_broken_submodules(self, mod, tmp_path, monkeypatch, capsys):
        import file_metadata as fm
        import knowledge_graph.graph_builder as gb

        def boom(*a, **k):
            raise RuntimeError("nope")

        monkeypatch.setattr(fm, "FileMetadataManager", boom)
        monkeypatch.setattr(gb, "KnowledgeGraphBuilder", boom)
        mod.isolate_runtime_state(tmp_path)  # 不抛
        out = capsys.readouterr().out
        assert "文件元数据隔离失败" in out and "知识图谱隔离失败" in out

    def test_disable_rerank_identity(self, mod, monkeypatch):
        import rag_rerank
        saved = rag_rerank.rerank
        try:
            mod.disable_rerank()
            srcs = [{"file": "a"}, {"file": "b"}]
            out = rag_rerank.rerank("q", srcs, progress=lambda *a, **k: None)
            assert out == srcs and out is not srcs
            assert rag_rerank.rerank("q", None) == []
        finally:
            rag_rerank.rerank = saved

    def test_build_engine_uses_tmp_persist_dir(self, mod, tmp_path, monkeypatch):
        import rag_engine as re_mod
        import document_loader as dl

        created = {}

        class StubEngine(FakeEngine):
            def __init__(self, persist_dir=None, enable_auto_snapshot=True, enable_security=True):
                super().__init__()
                created.update(persist_dir=persist_dir, snapshot=enable_auto_snapshot, security=enable_security)

        docs = [SimpleNamespace(metadata={"file_path": "/c/b.md"}), SimpleNamespace(metadata={"file_path": "/c/a.md"}),
                SimpleNamespace(metadata={"file_path": "/c/a.md"}), SimpleNamespace(metadata={})]
        monkeypatch.setattr(re_mod, "RAGEngine", StubEngine)
        monkeypatch.setattr(dl, "load_documents", lambda path: docs)
        logs = []
        engine, n_docs, n_chunks = mod.build_engine(tmp_path / "corpus", tmp_path, hybrid=False, log=logs.append)
        assert created == {"persist_dir": str(tmp_path / "index"), "snapshot": False, "security": False}
        assert engine.hybrid_enabled is False
        assert engine.built == {"n": 4, "persist": False, "file_paths": ["/c/a.md", "/c/b.md"]}
        assert (n_docs, n_chunks) == (2, 7)
        assert any("建索引中" in s for s in logs) and any("7 个片段" in s for s in logs)

    def test_build_engine_empty_corpus_raises(self, mod, tmp_path, monkeypatch):
        import rag_engine as re_mod
        import document_loader as dl
        monkeypatch.setattr(re_mod, "RAGEngine", lambda **k: FakeEngine())
        monkeypatch.setattr(dl, "load_documents", lambda path: [])
        with pytest.raises(RuntimeError, match="没有可加载的文档"):
            mod.build_engine(tmp_path, tmp_path, hybrid=True, log=lambda s: None)

    def test_build_engine_count_failure_gives_minus_one(self, mod, tmp_path, monkeypatch):
        import rag_engine as re_mod
        import document_loader as dl

        class E(FakeEngine):
            def __init__(self, **k):
                super().__init__()
                self.chroma_collection = SimpleNamespace(count=lambda: (_ for _ in ()).throw(RuntimeError("x")))

        monkeypatch.setattr(re_mod, "RAGEngine", lambda **k: E())
        monkeypatch.setattr(dl, "load_documents", lambda path: [SimpleNamespace(metadata={})])
        _, n_docs, n_chunks = mod.build_engine(tmp_path, tmp_path, hybrid=True, log=lambda s: None)
        assert (n_docs, n_chunks) == (1, -1)

    def test_quiet_logging(self, mod):
        import logging
        root = logging.getLogger()
        saved = root.level
        try:
            root.setLevel(logging.INFO)
            mod.quiet_logging(debug=True)
            assert root.level == logging.INFO
            mod.quiet_logging()
            assert root.level == logging.WARNING and logging.getLogger("httpx").level == logging.WARNING
        finally:
            root.setLevel(saved)


# ==================== 逐例运行 ====================

class TestRun:
    @pytest.fixture
    def stub_answer(self, monkeypatch):
        import rag_pipeline
        calls = []

        def fake(engine, question, **kw):
            calls.append((question, kw))
            if question == "meta?":
                return {"kind": "meta", "answer": "[知识库概览]", "kb_sources": []}
            if question == "neg?":
                return {"kind": "answer", "answer": "", "kb_sources": []}
            return {"kind": "answer", "answer": "默认 3 次[1]。", "kb_sources": [{"file": "a.md", "ref": "1"}]}

        monkeypatch.setattr(rag_pipeline, "answer_question", fake)
        return calls

    def test_run_case_success_and_kwargs(self, mod, stub_answer):
        engine = FakeEngine({"q1": [{"file": "x.md"}, {"file": "a.md"}]})
        case = {"id": "s", "type": "single", "question": "q1", "expected_files": ["a.md"], "expected_keywords": ["3"]}
        row = mod.run_case(engine, case, k=10, hybrid=True)
        assert row["passed"] is True and row["metrics"]["recall_at_k"] == 1.0 and row["metrics"]["mrr"] == 0.5
        assert row["hybrid_applied"] is True and row["error"] is None
        assert row["retrieval_seconds"] >= 0 and row["answer_seconds"] >= 0 and row["metrics"]["latency"] >= 0
        assert engine.calls == [("retrieve", "q1", True)]
        q, kw = stub_answer[0]
        assert q == "q1" and kw == {"enable_web_search": False, "show_progress": False, "kb_only": True}

    def test_run_case_meta_and_negative(self, mod, stub_answer):
        engine = FakeEngine({"neg?": [{"file": "a.md"}]})
        meta = mod.run_case(engine, {"id": "m", "type": "meta", "question": "meta?"}, k=10, hybrid=False)
        assert meta["passed"] is True and meta["metrics"]["meta_detected"] is True and meta["hybrid_applied"] is False
        neg = mod.run_case(engine, {"id": "n", "type": "negative", "question": "neg?"}, k=10, hybrid=False)
        assert neg["passed"] is True and neg["metrics"]["negative_rejected"] is True
        assert neg["retrieved"] == ["a.md"]  # 检索到但编排层拒答

    def test_run_case_error_recorded(self, mod, stub_answer):
        engine = FakeEngine(fail_on={"bad"})
        row = mod.run_case(engine, {"id": "e", "type": "single", "question": "bad", "expected_files": ["a.md"]}, k=10, hybrid=True)
        assert row["passed"] is False and row["error"] == "ConnectionError: no ollama"
        assert row["metrics"]["recall_at_k"] == 0.0 and row["answer_seconds"] == 0.0
        assert stub_answer == []  # 检索失败不再问答

    def test_run_prints_progress_and_verbose(self, mod, stub_answer):
        engine = FakeEngine({"q1": [{"file": "a.md"}, {"file": "a.md"}]}, fail_on={"bad"})
        cases = [
            {"id": "s", "type": "single", "question": "q1", "expected_files": ["a.md"], "expected_keywords": ["3"]},
            {"id": "e", "type": "single", "question": "bad", "expected_files": ["a.md"]},
        ]
        logs = []
        rows = mod.run(engine, cases, k=10, hybrid=True, verbose=True, log=logs.append)
        assert [r["passed"] for r in rows] == [True, False]
        assert logs[0].startswith("[1/2] ✅ s (single, ") and logs[4].startswith("[2/2] ❌ e (single, ")
        assert "   命中: a.md" in logs and any(l.startswith("   A: 默认 3 次[1]") for l in logs)
        assert any(l.startswith("   A: ConnectionError") for l in logs)
        assert any(l == "   命中: —" for l in logs)


# ==================== 报告 I/O ====================

class TestReports:
    def _agg(self, recall):
        summ = {"n": 1, "passed": 1, "recall_at_k": recall, "mrr": None, "citation_hit_rate": None, "keyword_hit": None,
                "negative_rejected": None, "meta_detected": None, "latency": 1.0}
        return {"n": 1, "errors": 0, "passed": 1, "by_type": {"single": summ}, "overall": dict(summ)}

    def test_report_paths(self, mod, tmp_path):
        md, js = mod.report_paths(tmp_path, "hybrid-on", "20260909")
        assert md == tmp_path / "hybrid-on-20260909.md" and js == tmp_path / "hybrid-on-20260909.json"

    def test_find_previous_report(self, mod, tmp_path):
        assert mod.find_previous_report(tmp_path / "missing", "t") is None
        assert mod.find_previous_report(tmp_path, "t") is None
        (tmp_path / "t-20260901.json").write_text("{}")
        (tmp_path / "t-20260905.json").write_text("{}")
        (tmp_path / "t-20260905.md").write_text("")
        (tmp_path / "other-20260908.json").write_text("{}")
        assert mod.find_previous_report(tmp_path, "t").name == "t-20260905.json"
        # 排除本次输出（同日重跑时对比更早一份）
        assert mod.find_previous_report(tmp_path, "t", exclude=tmp_path / "t-20260905.json").name == "t-20260901.json"

    def test_load_previous_handles_bad_json(self, mod, tmp_path, capsys):
        assert mod.load_previous(None) is None
        bad = tmp_path / "t-1.json"
        bad.write_text("{not json", encoding="utf-8")
        assert mod.load_previous(bad) is None
        assert "上一份报告无法读取" in capsys.readouterr().out
        good = tmp_path / "t-2.json"
        good.write_text(json.dumps({"aggregate": {"n": 1}}), encoding="utf-8")
        assert mod.load_previous(good) == {"aggregate": {"n": 1}}

    def test_write_reports_first_then_with_delta(self, mod, tmp_path):
        out = tmp_path / "reports"
        meta = {"tag": "t", "date": "2026-09-01", "model": "m", "embed_model": "e", "hybrid": "on", "rerank": "llm",
                "top_k": 10, "cases_file": "c", "corpus_docs": 1, "chunks": 2, "corpus_dir": "d", "n_cases": 1}
        rows = [{"id": "s", "type": "single", "passed": True, "retrieved": ["a.md"], "cited_files": [],
                 "metrics": {"recall_at_k": 0.7, "latency": 1.0}, "error": None}]
        md1, js1 = mod.write_reports(out, "t", "20260901", meta, self._agg(0.7), rows)
        assert md1.exists() and js1.exists() and out.is_dir()
        text1 = md1.read_text(encoding="utf-8")
        assert "(+" not in text1 and "| s | single | ✅ |" in text1
        data = json.loads(js1.read_text(encoding="utf-8"))
        assert data["meta"]["tag"] == "t" and data["aggregate"]["n"] == 1 and data["rows"][0]["id"] == "s"

        meta2 = dict(meta, date="2026-09-09")
        md2, js2 = mod.write_reports(out, "t", "20260909", meta2, self._agg(0.9), rows)
        text2 = md2.read_text(encoding="utf-8")
        assert "| 对比基线 | t @ 2026-09-01（括号内为 Δ） |" in text2
        assert "0.90 (+0.20)" in text2
        # 同日重跑：排除自身，仍与 0901 对比
        md3, _ = mod.write_reports(out, "t", "20260909", meta2, self._agg(0.8), rows)
        assert "0.80 (+0.10)" in md3.read_text(encoding="utf-8")
        # 不同 tag 互不对比
        md4, _ = mod.write_reports(out, "u", "20260909", dict(meta, tag="u"), self._agg(0.5), rows)
        assert "对比基线" not in md4.read_text(encoding="utf-8")

    def test_summary_lines(self, mod):
        agg = self._agg(0.75)
        agg["overall"]["mrr"] = 0.5
        lines = mod.summary_lines(agg)
        assert lines[0] == "通过 1/1 · 错误 0"
        assert lines[1] == "Recall@k 0.75 · MRR 0.50 · 平均延迟 1.0s"
