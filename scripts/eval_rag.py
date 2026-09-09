#!/usr/bin/env python3
"""RAG 检索基准（F10 P1-3）：在临时目录用 ``tests/fixtures/rag_eval_corpus/`` 建索引，跑
``tests/fixtures/rag_eval_cases.json`` 并输出 Markdown / JSON 报告。

**需要本机 Ollama（对话模型 + 嵌入模型），不进 CI / 测试集。** 用途：调 ``SIMILARITY_CUTOFF`` /
rerank 策略 / hybrid 开关 / 分块参数前后各跑一次，比较 Recall@k、MRR、引用命中、关键词命中、
负样本拒答、元查询识别与平均延迟；同 tag 有上一份报告时自动给出 Δ。

用法::

  ./venv/bin/python scripts/eval_rag.py --hybrid on --tag hybrid-on
  ./venv/bin/python scripts/eval_rag.py --hybrid off --rerank none --top-k 5 --tag dense-only
  ./venv/bin/python scripts/eval_rag.py --type negative --limit 3 -v      # 调试单类

参数：``--hybrid on|off``（默认取 config ``RAG_HYBRID``）、``--rerank llm|cross-encoder|none``（默认 config
``RERANKER``；``none`` 为跳过 rerank）、``--top-k N``（默认 config ``TOP_K``）、``--tag NAME``（默认
``hybrid-<on|off>``）、``--cases`` / ``--corpus`` / ``--out-dir`` / ``--limit`` / ``--type`` / ``--model`` / ``-v``。

隔离：``RAGEngine(persist_dir=<tmp>)`` 建库，``runtime_paths`` / 文件元数据 / 知识图谱全部重定向到同一临时目录，
**绝不触碰 ``index_storage/`` 与 ``.cerebro/``**；结束后删除临时目录。

输出：``docs/development/rag-eval/reports/{tag}-{YYYYMMDD}.md`` 与 ``.json``（后者含逐例明细，供下次 Δ 对比）。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time
from datetime import date
from pathlib import Path
from typing import Callable, Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

DEFAULT_CASES = ROOT / "tests" / "fixtures" / "rag_eval_cases.json"
DEFAULT_CORPUS = ROOT / "tests" / "fixtures" / "rag_eval_corpus"
DEFAULT_OUT_DIR = ROOT / "docs" / "development" / "rag-eval" / "reports"

HYBRID_CHOICES = ("on", "off")
RERANK_CHOICES = ("llm", "cross-encoder", "none")


# ==================== 参数 ====================

def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="F10 RAG 检索基准（需本机 Ollama）")
    ap.add_argument("--hybrid", choices=HYBRID_CHOICES, help="dense + BM25 混合检索开关（默认取 config RAG_HYBRID）")
    ap.add_argument("--rerank", choices=RERANK_CHOICES, help="rerank 策略（默认取 config RERANKER；none 为跳过）")
    ap.add_argument("--top-k", type=int, dest="top_k", help="检索条数（默认取 config TOP_K）")
    ap.add_argument("--tag", help="报告标签，默认 hybrid-<on|off>；同 tag 的上一份报告用于 Δ 对比")
    ap.add_argument("--cases", default=str(DEFAULT_CASES), help="样本文件")
    ap.add_argument("--corpus", default=str(DEFAULT_CORPUS), help="语料目录")
    ap.add_argument("--out-dir", dest="out_dir", default=str(DEFAULT_OUT_DIR), help="报告输出目录")
    ap.add_argument("--limit", type=int, help="只跑前 N 例（调试用）")
    ap.add_argument("--type", dest="case_type", choices=("single", "multi_hop", "code_symbol", "meta", "negative"),
                    help="只跑某一类样本")
    ap.add_argument("--model", help="对话模型名（默认取 config LLM_MODEL）")
    ap.add_argument("-v", "--verbose", action="store_true", help="打印每例问答")
    ap.add_argument("--debug", action="store_true", help="保留各模块的 INFO 日志（默认只显示 WARNING 以上）")
    return ap


def quiet_logging(debug: bool = False) -> None:
    """建库 / 问答期间知识图谱与 httpx 的 INFO 日志会刷屏，默认压到 WARNING。"""
    import logging

    if debug:
        return
    # 先触发相关模块导入（部分模块在导入时 basicConfig(level=INFO)），再统一压级别
    for mod in ("rag_engine", "rag_pipeline", "knowledge_graph"):
        try:
            __import__(mod)
        except Exception:  # noqa: BLE001 - 仅为触发日志配置，导入失败交给后续真正使用处报错
            pass
    logging.getLogger().setLevel(logging.WARNING)
    for name in ("httpx", "httpcore", "knowledge_graph", "rag_pipeline", "rag_engine"):
        logging.getLogger(name).setLevel(logging.WARNING)


def apply_env(args: argparse.Namespace) -> None:
    """把命令行参数写入环境变量——必须在 ``import config`` 之前调用（config 在导入时读取）。"""
    if args.model:
        os.environ["LLM_MODEL"] = args.model
    if args.top_k is not None:
        os.environ["TOP_K"] = str(args.top_k)
    if args.hybrid:
        os.environ["RAG_HYBRID"] = "true" if args.hybrid == "on" else "false"
    if args.rerank and args.rerank != "none":
        os.environ["RERANKER"] = args.rerank


def resolve_settings(args: argparse.Namespace) -> dict:
    """在 ``apply_env`` 之后读取最终生效的设置（``import config`` 放在这里，避免模块导入即读环境）。"""
    import config

    hybrid = args.hybrid or ("on" if getattr(config, "RAG_HYBRID", True) else "off")
    rerank = args.rerank or str(getattr(config, "RERANKER", "llm"))
    top_k = int(args.top_k if args.top_k is not None else getattr(config, "TOP_K", 10))
    return {
        "hybrid": hybrid,
        "rerank": rerank,
        "top_k": top_k,
        "tag": args.tag or f"hybrid-{hybrid}",
        "model": str(getattr(config, "LLM_MODEL", "")),
        "embed_model": str(getattr(config, "EMBED_MODEL", "")),
        "provider": str(getattr(config, "LLM_PROVIDER", "ollama")),
        "similarity_cutoff": getattr(config, "SIMILARITY_CUTOFF", None),
        "kb_relevance_threshold": getattr(config, "KB_RELEVANCE_THRESHOLD", None),
    }


# ==================== 隔离与建库 ====================

def isolate_runtime_state(tmp: Path) -> None:
    """把 App 运行时状态（``.cerebro/``：文件元数据 / 知识图谱 / 快照）重定向到临时目录。"""
    import runtime_paths as rp

    rp.set_app_state_root(tmp / "app_state")
    try:
        import file_metadata as fm

        fm._global_metadata_manager = fm.FileMetadataManager(storage_path=str(tmp / "file_metadata"))
    except Exception as e:  # noqa: BLE001 - 元数据模块不可用时忽略
        print(f"⚠️ 文件元数据隔离失败（忽略）: {e}")
    try:
        import knowledge_graph.graph_builder as gb
        import knowledge_graph.graph_query as gq

        gb.set_default_persist_path(str(tmp / "graph.json"))
        gb._graph_builder = gb.KnowledgeGraphBuilder(persist_path=str(tmp / "graph.json"))
        gq._graph_query = None
    except Exception as e:  # noqa: BLE001
        print(f"⚠️ 知识图谱隔离失败（忽略）: {e}")


def disable_rerank() -> None:
    """``--rerank none``：让编排层的 rerank 原样返回全部片段（不改 rag_rerank 源码，仅本进程打桩）。"""
    import rag_rerank

    def _identity(question, sources, progress=None, complete=None, kind=None):  # noqa: ARG001
        return list(sources or [])

    rag_rerank.rerank = _identity


def build_engine(corpus_dir: Path, tmp: Path, hybrid: bool, log: Callable[[str], None] = print):
    """在 ``tmp/index`` 建语料索引，返回 ``(engine, n_docs, n_chunks)``。"""
    from document_loader import load_documents
    from rag_engine import RAGEngine

    engine = RAGEngine(persist_dir=str(tmp / "index"), enable_auto_snapshot=False, enable_security=False)
    engine.hybrid_enabled = hybrid
    docs = load_documents(str(corpus_dir))
    if not docs:
        raise RuntimeError(f"语料目录没有可加载的文档: {corpus_dir}")
    files = sorted({str((getattr(d, "metadata", None) or {}).get("file_path") or "") for d in docs} - {""})
    log(f"📚 语料：{len(files)} 个文件 / {len(docs)} 个文档对象，建索引中…")
    t0 = time.perf_counter()
    engine.build_index(docs, persist=False, file_paths=files or None)
    try:
        n_chunks = int(engine.chroma_collection.count())
    except Exception:  # noqa: BLE001
        n_chunks = -1
    log(f"✅ 索引就绪：{n_chunks} 个片段，用时 {time.perf_counter() - t0:.1f}s")
    return engine, len(files) or len(docs), n_chunks


# ==================== 逐例运行 ====================

def run_case(engine, case: dict, k: int, hybrid: bool) -> dict:
    """对一条用例先 ``query_with_sources`` 再 ``answer_question(kb_only)``，返回打分明细行。"""
    from rag_eval import evaluate_case
    from rag_pipeline import answer_question

    question = str(case.get("question") or "")
    t0 = time.perf_counter()
    error: Optional[str] = None
    retrieval_sources: list = []
    result: Optional[dict] = None
    hybrid_applied = False
    t_retrieval = t_answer = 0.0
    try:
        retrieval = engine.query_with_sources(question, hybrid=hybrid)
        retrieval_sources = list(retrieval.get("sources") or [])
        hybrid_applied = bool(retrieval.get("hybrid"))
        t_retrieval = time.perf_counter() - t0
        t1 = time.perf_counter()
        result = answer_question(engine, question, enable_web_search=False, show_progress=False, kb_only=True)
        t_answer = time.perf_counter() - t1
    except Exception as e:  # noqa: BLE001 - 单例失败不影响整体
        error = f"{type(e).__name__}: {e}"
    latency = time.perf_counter() - t0
    row = evaluate_case(case, retrieval_sources, result, k, latency=latency, error=error)
    row["retrieval_seconds"] = round(t_retrieval, 3)
    row["answer_seconds"] = round(t_answer, 3)
    row["hybrid_applied"] = hybrid_applied
    return row


def run(engine, cases: list, k: int, hybrid: bool, verbose: bool = False, log: Callable[[str], None] = print) -> list:
    rows = []
    for i, case in enumerate(cases, 1):
        row = run_case(engine, case, k, hybrid)
        rows.append(row)
        mark = "✅" if row["passed"] else "❌"
        lat = row["metrics"].get("latency") or 0.0
        log(f"[{i}/{len(cases)}] {mark} {row['id']} ({row['type']}, {lat:.1f}s)")
        if verbose:
            log(f"   Q: {row['question']}")
            log(f"   命中: {', '.join(dict.fromkeys(row['retrieved'])) or '—'}")
            log(f"   A: {(row.get('answer') or row.get('error') or '')[:300]}".replace("\n", " "))
    return rows


# ==================== 报告 I/O ====================

def report_paths(out_dir: Path, tag: str, day: str) -> tuple[Path, Path]:
    base = out_dir / f"{tag}-{day}"
    return base.with_suffix(".md"), base.with_suffix(".json")


def find_previous_report(out_dir: Path, tag: str, exclude: Optional[Path] = None) -> Optional[Path]:
    """同 tag 最近一份 ``.json`` 报告（按文件名日期排序；排除本次输出路径）。"""
    if not out_dir.is_dir():
        return None
    candidates = sorted(p for p in out_dir.glob(f"{tag}-*.json") if exclude is None or p.resolve() != exclude.resolve())
    return candidates[-1] if candidates else None


def load_previous(path: Optional[Path]) -> Optional[dict]:
    if path is None:
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001 - 损坏的旧报告不阻断本次
        print(f"⚠️ 上一份报告无法读取，跳过 Δ 对比: {path.name}（{e}）")
        return None


def write_reports(out_dir: Path, tag: str, day: str, meta: dict, agg: dict, rows: list) -> tuple[Path, Path]:
    """写 ``.md`` 与 ``.json``；同 tag 存在上一份 ``.json`` 时报告带 Δ。返回两个路径。"""
    from rag_eval import render_markdown

    out_dir.mkdir(parents=True, exist_ok=True)
    md_path, json_path = report_paths(out_dir, tag, day)
    previous = load_previous(find_previous_report(out_dir, tag, exclude=json_path))
    md = render_markdown(agg, meta, previous=previous, rows=rows)
    md_path.write_text(md, encoding="utf-8")
    json_path.write_text(json.dumps({"meta": meta, "aggregate": agg, "rows": rows}, ensure_ascii=False, indent=2),
                         encoding="utf-8")
    return md_path, json_path


def summary_lines(agg: dict) -> list:
    """终端摘要：合计行的核心指标。"""
    from rag_eval import METRIC_KEYS, METRIC_LABELS, fmt_metric

    overall = agg.get("overall") or {}
    parts = [f"{METRIC_LABELS[k]} {fmt_metric(k, overall.get(k))}" for k in METRIC_KEYS if overall.get(k) is not None]
    return [f"通过 {agg.get('passed', 0)}/{agg.get('n', 0)} · 错误 {agg.get('errors', 0)}", " · ".join(parts)]


# ==================== 入口 ====================

def main(argv: Optional[list] = None) -> int:  # pragma: no cover - 需真实 Ollama，由单测覆盖各纯函数
    args = build_parser().parse_args(argv)
    apply_env(args)
    settings = resolve_settings(args)

    from rag_eval import aggregate, load_cases, type_distribution, validate_cases

    quiet_logging(args.debug)

    cases_path = Path(args.cases)
    corpus_dir = Path(args.corpus)
    cases = load_cases(cases_path, args.case_type, args.limit)
    if not cases:
        print("没有可运行的用例", file=sys.stderr)
        return 2
    problems = validate_cases(cases, corpus_dir)
    if problems:
        print("样本文件有问题：", file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        return 2

    hybrid_on = settings["hybrid"] == "on"
    if settings["rerank"] == "none":
        disable_rerank()

    dist = type_distribution(cases)
    print(f"模型：{settings['model']}（{settings['provider']}）· 嵌入：{settings['embed_model']} · "
          f"hybrid={settings['hybrid']} · rerank={settings['rerank']} · top_k={settings['top_k']} · tag={settings['tag']}")
    print("样本：" + " / ".join(f"{t} {n}" for t, n in dist.items() if n) + f"（共 {len(cases)}）\n", flush=True)

    with tempfile.TemporaryDirectory(prefix="cerebro-rag-eval-") as tmp_str:
        tmp = Path(tmp_str)
        isolate_runtime_state(tmp)
        t_start = time.perf_counter()
        engine, n_docs, n_chunks = build_engine(corpus_dir, tmp, hybrid_on)
        rows = run(engine, cases, settings["top_k"], hybrid_on, verbose=args.verbose)
        total = time.perf_counter() - t_start

    agg = aggregate(rows)
    day = date.today().strftime("%Y%m%d")
    meta = {
        **settings,
        "date": date.today().isoformat(),
        "cases_file": str(cases_path.relative_to(ROOT)) if cases_path.is_relative_to(ROOT) else str(cases_path),
        "corpus_dir": str(corpus_dir.relative_to(ROOT)) if corpus_dir.is_relative_to(ROOT) else str(corpus_dir),
        "n_cases": len(cases),
        "type_distribution": dist,
        "corpus_docs": n_docs,
        "chunks": n_chunks,
        "total_seconds": round(total, 1),
        "filters": {"type": args.case_type, "limit": args.limit},
    }
    md_path, json_path = write_reports(Path(args.out_dir), settings["tag"], day, meta, agg, rows)
    print()
    for line in summary_lines(agg):
        print(line)
    print(f"\n报告：{md_path}\n明细：{json_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
