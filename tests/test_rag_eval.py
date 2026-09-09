#!/usr/bin/env python3
"""src/rag_eval.py 纯函数单测（F10 P1-3）：每个指标的正常 / 边界、汇总、样本加载与 Markdown 报告的 Δ 列。

不依赖 Ollama / LlamaIndex / ChromaDB。
"""
import json
from pathlib import Path

import pytest

import rag_eval as re_

FIXTURES = Path(__file__).parent / "fixtures"
CASES_PATH = FIXTURES / "rag_eval_cases.json"
CORPUS_DIR = FIXTURES / "rag_eval_corpus"


def _src(file, ref=None, path=None, **extra):
    d = {"file": file, "content": "x", "score": 0.5}
    if ref is not None:
        d["ref"] = ref
    if path is not None:
        d["path"] = path
    d.update(extra)
    return d


# ==================== 基础工具 ====================

class TestBasics:
    def test_norm_text(self):
        assert re_.norm_text("20,000 HTTP/2 snake_case-x") == "20000http2snakecasex"
        assert re_.norm_text(None) == ""

    def test_source_file_prefers_file_then_path(self):
        assert re_.source_file({"file": "A.MD"}) == "a.md"
        assert re_.source_file({"path": "/tmp/dir/b.py"}) == "b.py"
        assert re_.source_file({"file": "", "path": "/x/c.txt"}) == "c.txt"
        assert re_.source_file("not a dict") == ""
        assert re_.source_file({}) == ""

    def test_word_lists_shared_with_overcompliance(self):
        # F9-1 词表迁入共享层：HOLD ⊇ PREMISE，REJECT = HEDGE ∪ HOLD 去重
        assert set(re_.PREMISE_WORDS) <= set(re_.HOLD_WORDS)
        assert set(re_.REJECT_WORDS) == set(re_.HEDGE_WORDS) | set(re_.HOLD_WORDS)
        assert len(re_.REJECT_WORDS) == len(set(re_.REJECT_WORDS))


# ==================== recall_at_k ====================

class TestRecallAtK:
    def test_full_and_partial(self):
        sources = [_src("a.md"), _src("b.md"), _src("c.md")]
        assert re_.recall_at_k(sources, ["a.md", "b.md"], 10) == 1.0
        assert re_.recall_at_k(sources, ["a.md", "zz.md"], 10) == 0.5
        assert re_.recall_at_k(sources, ["zz.md"], 10) == 0.0

    def test_k_cuts_off(self):
        sources = [_src("a.md"), _src("b.md"), _src("c.md")]
        assert re_.recall_at_k(sources, ["c.md"], 2) == 0.0
        assert re_.recall_at_k(sources, ["c.md"], 3) == 1.0
        assert re_.recall_at_k(sources, ["a.md"], 0) == 0.0

    def test_duplicates_and_case_and_paths(self):
        # 重复来源只算一次；文件名大小写 / 带目录的期望值按 basename 比较
        sources = [_src("A.md"), _src("a.md"), _src("a.md", path="/p/a.md")]
        assert re_.recall_at_k(sources, ["sub/a.md"], 10) == 1.0
        assert re_.recall_at_k(sources, ["a.md", "b.md"], 10) == 0.5

    def test_empty_inputs(self):
        assert re_.recall_at_k([], ["a.md"], 10) == 0.0
        assert re_.recall_at_k(None, ["a.md"], 10) == 0.0
        assert re_.recall_at_k([_src("a.md")], [], 10) is None
        assert re_.recall_at_k([_src("a.md")], None, 10) is None
        assert re_.recall_at_k([_src("a.md")], ["  "], 10) is None

    def test_non_dict_sources_ignored(self):
        assert re_.recall_at_k(["junk", None, _src("a.md")], ["a.md"], 10) == 1.0


# ==================== mrr ====================

class TestMRR:
    def test_rank_positions(self):
        sources = [_src("x.md"), _src("a.md"), _src("b.md")]
        assert re_.mrr(sources, ["a.md"]) == 0.5
        assert re_.mrr(sources, ["b.md"]) == pytest.approx(1 / 3)
        assert re_.mrr(sources, ["a.md", "b.md"]) == 0.5  # 取第一个命中的任一期望文件
        assert re_.mrr(sources, ["x.md"]) == 1.0

    def test_no_hit_and_empty(self):
        assert re_.mrr([_src("x.md")], ["a.md"]) == 0.0
        assert re_.mrr([], ["a.md"]) == 0.0
        assert re_.mrr(None, ["a.md"]) == 0.0
        assert re_.mrr([_src("a.md")], []) is None

    def test_duplicates_do_not_change_first_hit(self):
        sources = [_src("x.md"), _src("x.md"), _src("a.md"), _src("a.md")]
        assert re_.mrr(sources, ["a.md"]) == pytest.approx(1 / 3)


# ==================== 引用解析与 citation_hit_rate ====================

class TestCitations:
    def test_cited_refs_dedup_and_ignore_code_and_web(self):
        ans = "甲[1]，乙[2]，再提甲[1]，网络[W1]，非法[?]，`code [9]` 与 ```\n[8]\n```"
        assert re_.cited_refs(ans) == ["1", "2"]
        assert re_.cited_refs("") == []
        assert re_.cited_refs(None) == []

    def test_resolve_by_ref_then_by_position(self):
        with_ref = [_src("a.md", ref="1"), _src("b.md", ref="2")]
        assert re_.resolve_citation("2", with_ref)["file"] == "b.md"
        assert re_.resolve_citation("3", with_ref) is None  # 越界
        no_ref = [_src("a.md"), _src("b.md")]
        assert re_.resolve_citation("1", no_ref)["file"] == "a.md"
        assert re_.resolve_citation("0", no_ref) is None
        assert re_.resolve_citation("5", no_ref) is None
        assert re_.resolve_citation("x", no_ref) is None
        assert re_.resolve_citation("1", []) is None

    def test_ref_keys_take_precedence_over_position(self):
        # ref 与位置不一致时以 ref 为准（rerank 后顺序可能已变）
        sources = [_src("b.md", ref="2"), _src("a.md", ref="1")]
        assert re_.resolve_citation("1", sources)["file"] == "a.md"

    def test_citation_hit_rate(self):
        sources = [_src("a.md", ref="1"), _src("b.md", ref="2"), _src("c.md", ref="3")]
        assert re_.citation_hit_rate("见[1]与[2]。", sources, ["a.md", "b.md"]) == 1.0
        assert re_.citation_hit_rate("见[1]与[3]。", sources, ["a.md"]) == 0.5
        assert re_.citation_hit_rate("见[1]与[7]。", sources, ["a.md"]) == 0.5  # 编号越界计未命中
        assert re_.citation_hit_rate("见[1][1][1]。", sources, ["a.md"]) == 1.0  # 重复引用去重
        assert re_.citation_hit_rate("没有引用。", sources, ["a.md"]) == 0.0
        assert re_.citation_hit_rate("", sources, ["a.md"]) == 0.0
        assert re_.citation_hit_rate("见[1]。", sources, []) is None
        assert re_.citation_hit_rate("见[1]。", [], ["a.md"]) == 0.0

    def test_cited_files(self):
        sources = [_src("a.md", ref="1"), _src("b.md", ref="2")]
        assert re_.cited_files("见[2]、[1]、[2]、[9]。", sources) == ["b.md", "a.md", "?"]
        assert re_.cited_files("无", sources) == []


# ==================== keyword_hit ====================

class TestKeywordHit:
    def test_ratio_and_normalization(self):
        assert re_.keyword_hit("默认 20,000 块，协议 HTTP/2", ["20000", "http2"]) == 1.0
        assert re_.keyword_hit("默认 3 次", ["3", "lumen:dead"]) == 0.5
        assert re_.keyword_hit("函数 _ensure_bm25", ["ensure_bm25"]) == 1.0

    def test_alternatives_with_pipe(self):
        assert re_.keyword_hit("超过 grace 会跳过", ["misfire_grace|60", "跳过"]) == 0.5
        assert re_.keyword_hit("60 秒内补投", ["misfire_grace|60"]) == 1.0
        assert re_.keyword_hit("x", ["|"]) == 0.0  # 全空可选项永不命中

    def test_empty_inputs(self):
        assert re_.keyword_hit("任意", []) is None
        assert re_.keyword_hit("任意", None) is None
        assert re_.keyword_hit("任意", ["  "]) is None
        assert re_.keyword_hit("", ["a"]) == 0.0
        assert re_.keyword_hit(None, ["a"]) == 0.0


# ==================== negative_rejected ====================

class TestNegativeRejected:
    def test_no_sources_or_empty_answer(self):
        assert re_.negative_rejected("任何内容", []) is True
        assert re_.negative_rejected("任何内容", None) is True
        assert re_.negative_rejected("", [_src("a.md")]) is True
        assert re_.negative_rejected("   ", [_src("a.md")]) is True

    def test_with_sources_needs_hedge(self):
        srcs = [_src("a.md")]
        assert re_.negative_rejected("资料未提及 Kafka 后端。", srcs) is True
        assert re_.negative_rejected("Kafka 后端不存在于文档中。", srcs) is True
        assert re_.negative_rejected("Kafka 后端 partition 数默认 12。", srcs) is False  # 有来源且编造

    def test_english_hedges(self):
        assert re_.negative_rejected("I am not sure about this.", [_src("a.md")]) is True


# ==================== evaluate_case ====================

class TestEvaluateCase:
    def _case(self, ctype="single", files=("a.md",), keywords=("3",)):
        return {"id": "c", "type": ctype, "question": "q", "expected_files": list(files), "expected_keywords": list(keywords)}

    def test_retrieval_type_metrics(self):
        retrieved = [_src("x.md"), _src("a.md")]
        result = {"answer": "默认 3 次[1]。", "kb_sources": [_src("a.md", ref="1")], "kind": "answer"}
        row = re_.evaluate_case(self._case(), retrieved, result, k=10, latency=1.25)
        m = row["metrics"]
        assert m["recall_at_k"] == 1.0 and m["mrr"] == 0.5 and m["citation_hit_rate"] == 1.0 and m["keyword_hit"] == 1.0
        assert m["negative_rejected"] is None and m["meta_detected"] is None and m["latency"] == 1.25
        assert row["passed"] is True and row["retrieved"] == ["x.md", "a.md"] and row["cited_files"] == ["a.md"]
        assert row["answer_kind"] == "answer" and row["error"] is None

    def test_retrieval_type_fail_when_keyword_missing(self):
        row = re_.evaluate_case(self._case(keywords=("3", "lumen:dead", "x")), [_src("a.md")],
                                {"answer": "默认 3 次。", "kb_sources": [_src("a.md", ref="1")]}, k=10)
        assert row["metrics"]["keyword_hit"] == pytest.approx(1 / 3)
        assert row["passed"] is False

    def test_retrieval_type_no_keywords_passes_on_recall(self):
        row = re_.evaluate_case(self._case(keywords=()), [_src("a.md")], {"answer": "…"}, k=10)
        assert row["metrics"]["keyword_hit"] is None and row["passed"] is True
        row = re_.evaluate_case(self._case(keywords=()), [_src("zz.md")], {"answer": "…"}, k=10)
        assert row["passed"] is False

    def test_multi_hop_partial_hit(self):
        case = self._case("multi_hop", files=("a.md", "b.md"), keywords=("3", "dead"))
        row = re_.evaluate_case(case, [_src("a.md")], {"answer": "3 次[1]", "kb_sources": [_src("a.md", ref="1")]}, k=10)
        assert row["metrics"]["recall_at_k"] == 0.5 and row["metrics"]["keyword_hit"] == 0.5
        assert row["passed"] is True  # 部分命中：recall>0 且关键词 ≥0.5

    def test_sources_fallback_key(self):
        # answer_question 内层返回用 sources 键，顶层用 kb_sources；两者都接受
        row = re_.evaluate_case(self._case(), [_src("a.md")], {"answer": "[1] 3", "sources": [_src("a.md", ref="1")]}, k=10)
        assert row["metrics"]["citation_hit_rate"] == 1.0

    def test_meta_case(self):
        case = self._case("meta", files=(), keywords=())
        ok = re_.evaluate_case(case, [], {"answer": "[知识库概览]", "kind": "meta"}, k=10)
        assert ok["metrics"]["meta_detected"] is True and ok["passed"] is True
        assert ok["metrics"]["recall_at_k"] is None
        bad = re_.evaluate_case(case, [_src("a.md")], {"answer": "…", "kind": "answer"}, k=10)
        assert bad["metrics"]["meta_detected"] is False and bad["passed"] is False

    def test_negative_case(self):
        case = self._case("negative", files=(), keywords=())
        rej = re_.evaluate_case(case, [_src("a.md")], {"answer": "", "kb_sources": []}, k=10)
        assert rej["metrics"]["negative_rejected"] is True and rej["passed"] is True
        # negative 有来源且答案编造 → 未拒答
        bad = re_.evaluate_case(case, [_src("a.md")], {"answer": "Kafka 分区 12 个[1]", "kb_sources": [_src("a.md", ref="1")]}, k=10)
        assert bad["metrics"]["negative_rejected"] is False and bad["passed"] is False

    def test_error_marks_worst_values(self):
        row = re_.evaluate_case(self._case(), [], None, k=10, error="ConnectionError: x")
        m = row["metrics"]
        assert (m["recall_at_k"], m["mrr"], m["citation_hit_rate"], m["keyword_hit"]) == (0.0, 0.0, 0.0, 0.0)
        assert row["passed"] is False and row["error"] == "ConnectionError: x"
        row = re_.evaluate_case(self._case(keywords=()), [], None, k=10, error="e")
        assert row["metrics"]["keyword_hit"] is None
        meta = re_.evaluate_case(self._case("meta", files=(), keywords=()), [], None, k=10, error="e")
        assert meta["metrics"]["meta_detected"] is False
        neg = re_.evaluate_case(self._case("negative", files=(), keywords=()), [], None, k=10, error="e")
        assert neg["metrics"]["negative_rejected"] is False

    def test_answer_truncated_and_none_result(self):
        row = re_.evaluate_case(self._case(), None, None, k=10)
        assert row["answer"] == "" and row["retrieved"] == [] and row["metrics"]["latency"] is None
        long_ans = "字" * 1000
        row = re_.evaluate_case(self._case(), [], {"answer": long_ans}, k=10)
        assert len(row["answer"]) == 600

    def test_unknown_type_treated_as_retrieval(self):
        row = re_.evaluate_case({"id": "u", "question": "q", "expected_files": ["a.md"]}, [_src("a.md")], {"answer": ""}, k=5)
        assert row["type"] == "single" and row["metrics"]["recall_at_k"] == 1.0


# ==================== aggregate ====================

class TestAggregate:
    def _row(self, ctype, passed=True, error=None, **metrics):
        m = {k: None for k in re_.METRIC_KEYS}
        m.update(metrics)
        return {"id": f"{ctype}-{len(metrics)}", "type": ctype, "metrics": m, "passed": passed, "error": error}

    def test_group_means_ignore_none(self):
        rows = [
            self._row("single", recall_at_k=1.0, mrr=1.0, latency=2.0),
            self._row("single", passed=False, recall_at_k=0.0, mrr=None, latency=4.0),
            self._row("negative", negative_rejected=True, latency=1.0),
            self._row("negative", passed=False, negative_rejected=False, latency=3.0),
            self._row("meta", meta_detected=True, latency=0.5),
        ]
        agg = re_.aggregate(rows)
        assert agg["n"] == 5 and agg["passed"] == 3 and agg["errors"] == 0
        assert list(agg["by_type"]) == ["single", "meta", "negative"]  # 按 CASE_TYPES 顺序
        s = agg["by_type"]["single"]
        assert s["n"] == 2 and s["passed"] == 1 and s["recall_at_k"] == 0.5 and s["mrr"] == 1.0 and s["latency"] == 3.0
        assert s["negative_rejected"] is None
        assert agg["by_type"]["negative"]["negative_rejected"] == 0.5
        assert agg["by_type"]["meta"]["meta_detected"] == 1.0
        o = agg["overall"]
        assert o["n"] == 5 and o["recall_at_k"] == 0.5 and o["latency"] == pytest.approx(2.1)

    def test_empty_and_errors(self):
        agg = re_.aggregate([])
        assert agg["n"] == 0 and agg["by_type"] == {} and agg["overall"]["recall_at_k"] is None
        agg = re_.aggregate([self._row("single", passed=False, error="boom", recall_at_k=0.0)])
        assert agg["errors"] == 1 and agg["passed"] == 0

    def test_unknown_type_sorted_after_known(self):
        agg = re_.aggregate([self._row("zzz"), self._row("single")])
        assert list(agg["by_type"]) == ["single", "zzz"]


# ==================== 样本加载 / 校验 ====================

class TestCases:
    def test_fixture_distribution_meets_acceptance(self):
        cases = re_.load_cases(CASES_PATH)
        assert len(cases) >= 30
        dist = re_.type_distribution(cases)
        assert dist["single"] >= 12 and dist["multi_hop"] >= 6 and dist["code_symbol"] >= 5
        assert dist["meta"] >= 3 and dist["negative"] >= 4
        assert re_.validate_cases(cases, CORPUS_DIR) == []

    def test_fixture_corpus_constraints(self):
        files = [p for p in CORPUS_DIR.iterdir() if p.is_file()]
        assert 1 <= len(files) <= 20
        assert sum(p.stat().st_size for p in files) < 200 * 1024
        suffixes = {p.suffix for p in files}
        assert {".md", ".py", ".txt"} <= suffixes
        # 至少一个含表格的 md
        assert any(p.suffix == ".md" and "|---|" in p.read_text(encoding="utf-8") for p in files)

    def test_load_cases_filters_and_bare_list(self, tmp_path):
        assert all(c["type"] == "negative" for c in re_.load_cases(CASES_PATH, "negative"))
        assert len(re_.load_cases(CASES_PATH, None, 3)) == 3
        bare = tmp_path / "bare.json"
        bare.write_text(json.dumps([{"id": "a", "type": "single"}]), encoding="utf-8")
        assert re_.load_cases(bare) == [{"id": "a", "type": "single"}]

    def test_type_distribution_counts_unknown(self):
        dist = re_.type_distribution([{"type": "single"}, {"type": "odd"}, {}])
        assert dist["single"] == 1 and dist["odd"] == 1 and dist[""] == 1 and dist["meta"] == 0

    def test_validate_cases_reports_problems(self, tmp_path):
        (tmp_path / "a.md").write_text("x", encoding="utf-8")
        cases = [
            {"id": "dup", "type": "single", "question": "q", "expected_files": ["a.md"]},
            {"id": "dup", "type": "bogus", "question": "", "expected_files": []},
            {"id": "m", "type": "meta", "question": "q", "expected_files": ["a.md"]},
            {"id": "n", "type": "negative", "question": "q"},
            {"id": "miss", "type": "code_symbol", "question": "q", "expected_files": ["nope.py"]},
            {"id": "nofiles", "type": "multi_hop", "question": "q", "expected_files": []},
        ]
        problems = re_.validate_cases(cases, tmp_path)
        joined = "\n".join(problems)
        assert "dup: id 重复" in joined and "非法 type 'bogus'" in joined and "question 为空" in joined
        assert "nofiles: 检索类样本缺少 expected_files" in joined
        assert "m: meta 样本不应有 expected_files" in joined
        assert "miss: expected_files 中 nope.py 不在语料目录" in joined
        assert not any(p.startswith("n:") for p in problems)
        # 不给语料目录 / 目录不存在时不校验文件存在性
        assert not any("不在语料目录" in p for p in re_.validate_cases(cases))
        assert not any("不在语料目录" in p for p in re_.validate_cases(cases, tmp_path / "nope"))


# ==================== Markdown 报告 ====================

class TestRenderMarkdown:
    def _agg(self, recall, latency, passed=1):
        summ = {"n": 1, "passed": passed, "recall_at_k": recall, "mrr": None, "citation_hit_rate": None,
                "keyword_hit": None, "negative_rejected": None, "meta_detected": None, "latency": latency}
        return {"n": 1, "errors": 0, "passed": passed, "by_type": {"single": dict(summ)}, "overall": dict(summ)}

    def test_fmt_helpers(self):
        assert re_.fmt_metric("recall_at_k", None) == "—"
        assert re_.fmt_metric("recall_at_k", 0.5) == "0.50"
        assert re_.fmt_metric("latency", 3.14) == "3.1s"
        assert re_.fmt_delta("recall_at_k", 0.8, 0.75) == " (+0.05)"
        assert re_.fmt_delta("recall_at_k", 0.8, 0.801) == " (±0.00)"
        assert re_.fmt_delta("latency", 2.0, 3.5) == " (-1.5s)"
        assert re_.fmt_delta("latency", 2.0, 2.01) == " (±0.0s)"
        assert re_.fmt_delta("mrr", None, 0.5) == "" and re_.fmt_delta("mrr", 0.5, None) == ""

    def test_without_previous_has_no_delta(self):
        md = re_.render_markdown(self._agg(0.8, 2.0), {"tag": "t", "date": "2026-09-09", "model": "m",
                                                       "embed_model": "e", "hybrid": "on", "rerank": "llm", "top_k": 10,
                                                       "cases_file": "c.json", "corpus_docs": 18, "chunks": 91,
                                                       "corpus_dir": "d", "n_cases": 1})
        assert md.startswith("# RAG 检索基准报告 · t\n")
        assert "| 对话模型 | m |" in md and "| 语料 | 18 个文档 / 91 个片段（d） |" in md
        assert "| 单文档（single） | 1 | 1/1 | 0.80 | — | — | — | — | — | 2.0s |" in md
        assert "| **合计** | 1 | 1/1 | 0.80 |" in md
        assert "(+" not in md and "(-" not in md and "对比基线" not in md
        assert "## 逐例明细" not in md and "## 指标说明" in md

    def test_with_previous_adds_delta_column(self):
        cur = self._agg(0.8, 2.0)
        prev = {"meta": {"tag": "t", "date": "2026-09-01"}, "aggregate": self._agg(0.75, 3.5)}
        md = re_.render_markdown(cur, {"tag": "t"}, previous=prev)
        assert "| 对比基线 | t @ 2026-09-01（括号内为 Δ） |" in md
        assert "| 单文档（single） | 1 | 1/1 | 0.80 (+0.05) | — | — | — | — | — | 2.0s (-1.5s) |" in md
        assert "| **合计** | 1 | 1/1 | 0.80 (+0.05) |" in md
        # previous 也可以直接传 aggregate
        md2 = re_.render_markdown(cur, {"tag": "t"}, previous=self._agg(0.75, 3.5))
        assert "0.80 (+0.05)" in md2 and "上一份" in md2

    def test_previous_missing_type_has_no_delta_for_it(self):
        cur = self._agg(0.8, 2.0)
        cur["by_type"]["negative"] = {"n": 1, "passed": 1, "recall_at_k": None, "mrr": None, "citation_hit_rate": None,
                                      "keyword_hit": None, "negative_rejected": 1.0, "meta_detected": None, "latency": 1.0}
        md = re_.render_markdown(cur, {"tag": "t"}, previous={"aggregate": self._agg(0.7, 2.0)})
        assert "| 负样本（negative） | 1 | 1/1 | — | — | — | — | 1.00 | — | 1.0s |" in md

    def test_rows_section_marks_and_errors(self):
        rows = [
            {"id": "s1", "type": "single", "passed": True, "retrieved": ["a.md", "a.md", "b.md", "c.md", "d.md"],
             "cited_files": ["a.md"], "metrics": {"recall_at_k": 1.0, "mrr": 1.0, "citation_hit_rate": 1.0,
                                                  "keyword_hit": 1.0, "latency": 2.0}, "error": None},
            {"id": "m1", "type": "meta", "passed": False, "retrieved": [], "cited_files": [],
             "metrics": {"meta_detected": False, "latency": 0.5}, "error": None},
            {"id": "n1", "type": "negative", "passed": True, "retrieved": [], "cited_files": [],
             "metrics": {"negative_rejected": True, "latency": 0.5}, "error": None},
            {"id": "e1", "type": "single", "passed": False, "retrieved": [], "cited_files": [],
             "metrics": {"recall_at_k": 0.0, "latency": None}, "error": "ConnectionError: no ollama"},
        ]
        md = re_.render_markdown(self._agg(0.5, 1.0), {"tag": "t"}, rows=rows)
        assert "## 逐例明细" in md
        assert "| s1 | single | ✅ | 1.00 | 1.00 | 1.00 | 1.00 | a.md, b.md, c.md | a.md | 2.0s |" in md  # 去重取前 3
        assert "| m1 | meta | ❌ 未识别 |" in md
        assert "| n1 | negative | ✅ 拒答 |" in md
        assert "| e1 | single | ❌ 错误 | 0.00 | — | — | — | — | — | — |" in md
        assert "- `e1`：ConnectionError: no ollama" in md
