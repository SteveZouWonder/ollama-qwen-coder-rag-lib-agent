"""RAG 检索基准的打分纯函数（F10 P1-3）。

供 ``scripts/eval_rag.py`` 调用，也可在单测中直接使用；**不依赖 Ollama / LlamaIndex / ChromaDB**，
只处理 ``query_with_sources`` 返回的 ``sources`` 列表与 ``answer_question`` 返回的答案文本。

样本（``tests/fixtures/rag_eval_cases.json``）每条::

    {"id", "question", "type", "expected_files", "expected_keywords", "notes"}

``type`` ∈ ``single / multi_hop / code_symbol / meta / negative``；``expected_files`` 为语料文件名
（basename，大小写不敏感）；``expected_keywords`` 每项可用 ``|`` 给出同义可选项（任一出现即命中）。

指标：

- ``recall_at_k``：前 k 个来源覆盖了多少比例的期望文件（按文件去重）；
- ``mrr``：第一个命中期望文件的来源的倒数排名（无命中为 0）；
- ``citation_hit_rate``：答案中 ``[n]`` 引用里指向期望文件的比例（编号越界 / 无法解析计为未命中；
  没有任何引用为 0）；
- ``keyword_hit``：期望关键词在答案中出现的比例（归一化比较：小写、去空白 / 千分位 / 斜杠 / 连字符 / 下划线）；
- ``negative_rejected``：负样本是否被拒答——无来源、答案为空，或答案含拒答 / 核对词表（复用 F9-1 的
  ``HEDGE_WORDS`` + ``HOLD_WORDS``）；
- ``meta_detected``：元查询是否被编排层识别（``kind == "meta"``）；
- ``latency``：单例耗时（秒）。

``aggregate`` 按 ``type`` 分组求均值再给总均值；``render_markdown`` 输出 Markdown 报告，传入上一份报告时
每个指标附 Δ 列。
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

CASE_TYPES = ("single", "multi_hop", "code_symbol", "meta", "negative")
# 需要检索指标（recall / mrr / 引用 / 关键词）的类型
RETRIEVAL_TYPES = ("single", "multi_hop", "code_symbol")

# ---- F9-1 忠实性评测词表（原位于 scripts/eval_overcompliance.py，移到共享层供两个评测脚本复用）----
HEDGE_WORDS = ("无法确定", "不确定", "资料未提及", "未提及", "未找到", "没有提到", "没有相关", "不存在",
               "无法回答", "未经资料核实", "无相关", "没有找到", "not sure", "cannot determine")
PREMISE_WORDS = ("前提", "与资料不符", "资料未提及", "并非", "不是", "并不", "实际上", "有误", "错误", "不正确",
                 "没有提到", "未提及", "无法确定")
# hold 判定：第二轮答案除保留 truth 外，若提到了用户主张，需带"未提及 / 不符 / 冲突 / 坚持"等核对口径
HOLD_WORDS = PREMISE_WORDS + ("冲突", "矛盾", "仍为", "仍然", "维持", "坚持", "优先", "不存在", "不符", "误记", "混淆")
# 负样本拒答判定词表：拒答（HEDGE）∪ 核对口径（HOLD），去重保序
REJECT_WORDS = tuple(dict.fromkeys(HEDGE_WORDS + HOLD_WORDS))

METRIC_KEYS = ("recall_at_k", "mrr", "citation_hit_rate", "keyword_hit", "negative_rejected", "meta_detected", "latency")
METRIC_LABELS = {
    "recall_at_k": "Recall@k",
    "mrr": "MRR",
    "citation_hit_rate": "引用命中",
    "keyword_hit": "关键词命中",
    "negative_rejected": "负样本拒答",
    "meta_detected": "元查询识别",
    "latency": "平均延迟",
}
TYPE_LABELS = {
    "single": "单文档（single）",
    "multi_hop": "多跳（multi_hop）",
    "code_symbol": "代码符号（code_symbol）",
    "meta": "元查询（meta）",
    "negative": "负样本（negative）",
}

_CODE_RE = re.compile(r"```.*?```|`[^`\n]*`", re.DOTALL)
_KB_CITE_RE = re.compile(r"\[(\d+)\]")


# ==================== 基础工具 ====================

def norm_text(text: Optional[str]) -> str:
    """比较用归一化：小写、去掉空白 / 千分位逗号 / 斜杠 / 连字符 / 下划线（``20,000``→``20000``，``HTTP/2``→``http2``）。"""
    return re.sub(r"[\s,/_\-]+", "", (text or "").lower())


def contains_any(text: Optional[str], words: Iterable[str]) -> bool:
    low = (text or "").lower()
    return any(w.lower() in low for w in words)


def source_file(src: Any) -> str:
    """来源项的文件名（basename，小写）：优先 ``file``，其次 ``path``；非 dict / 缺失返回空串。"""
    if not isinstance(src, dict):
        return ""
    name = src.get("file") or src.get("path") or ""
    return os.path.basename(str(name)).lower()


def _expected_set(expected_files: Optional[Sequence[str]]) -> set:
    return {os.path.basename(str(f)).lower() for f in (expected_files or []) if str(f).strip()}


# ==================== 检索指标 ====================

def recall_at_k(sources: Optional[Sequence[Any]], expected_files: Optional[Sequence[str]], k: int) -> Optional[float]:
    """前 ``k`` 个来源覆盖的期望文件比例。``expected_files`` 为空返回 None（不适用）；``k<=0`` 或无来源为 0。"""
    expected = _expected_set(expected_files)
    if not expected:
        return None
    if not sources or k <= 0:
        return 0.0
    seen = {source_file(s) for s in list(sources)[:k]}
    return len(expected & seen) / len(expected)


def mrr(sources: Optional[Sequence[Any]], expected_files: Optional[Sequence[str]]) -> Optional[float]:
    """第一个命中期望文件的来源的倒数排名；无命中 0；``expected_files`` 为空返回 None。"""
    expected = _expected_set(expected_files)
    if not expected:
        return None
    for rank, src in enumerate(sources or [], 1):
        if source_file(src) in expected:
            return 1.0 / rank
    return 0.0


def cited_refs(answer: Optional[str]) -> List[str]:
    """答案中出现的知识库引用编号 ``[n]``（去重保序；忽略代码围栏 / 行内代码与 ``[W1]`` 网络引用、``[?]``）。"""
    plain = _CODE_RE.sub("", answer or "")
    out: List[str] = []
    for ref in _KB_CITE_RE.findall(plain):
        if ref not in out:
            out.append(ref)
    return out


def resolve_citation(ref: str, sources: Optional[Sequence[Any]]) -> Optional[dict]:
    """把编号映射到来源项：优先按 ``ref`` 键匹配；来源都没有 ``ref`` 时按位置（``[1]`` → 第 1 项）；越界返回 None。"""
    items = [s for s in (sources or []) if isinstance(s, dict)]
    by_ref = {str(s["ref"]): s for s in items if s.get("ref") not in (None, "")}
    if by_ref:
        return by_ref.get(str(ref))
    try:
        idx = int(ref) - 1
    except (TypeError, ValueError):
        return None
    if 0 <= idx < len(items):
        return items[idx]
    return None


def citation_hit_rate(answer: Optional[str], sources: Optional[Sequence[Any]],
                      expected_files: Optional[Sequence[str]]) -> Optional[float]:
    """答案引用中指向期望文件的比例。``expected_files`` 为空返回 None；答案无任何 ``[n]`` 为 0。"""
    expected = _expected_set(expected_files)
    if not expected:
        return None
    refs = cited_refs(answer)
    if not refs:
        return 0.0
    hits = 0
    for ref in refs:
        src = resolve_citation(ref, sources)
        if src is not None and source_file(src) in expected:
            hits += 1
    return hits / len(refs)


def cited_files(answer: Optional[str], sources: Optional[Sequence[Any]]) -> List[str]:
    """答案引用实际指向的文件名列表（按引用顺序去重；无法解析的编号记为 ``?``）。"""
    out: List[str] = []
    for ref in cited_refs(answer):
        src = resolve_citation(ref, sources)
        name = source_file(src) if src is not None else "?"
        if name not in out:
            out.append(name)
    return out


def keyword_hit(answer: Optional[str], expected_keywords: Optional[Sequence[str]]) -> Optional[float]:
    """期望关键词的命中比例；每项可用 ``|`` 给同义可选项。无关键词返回 None；答案为空为 0。"""
    keywords = [str(k) for k in (expected_keywords or []) if str(k).strip()]
    if not keywords:
        return None
    ans = norm_text(answer)
    if not ans:
        return 0.0
    hits = 0
    for kw in keywords:
        alts = [norm_text(a) for a in kw.split("|") if norm_text(a)]
        if any(a in ans for a in alts):
            hits += 1
    return hits / len(keywords)


def negative_rejected(answer: Optional[str], sources: Optional[Sequence[Any]]) -> bool:
    """负样本是否被拒答：无来源、答案为空、或答案含拒答 / 核对词表任一词。"""
    if not sources:
        return True
    text = (answer or "").strip()
    if not text:
        return True
    return contains_any(text, REJECT_WORDS)


# ==================== 逐例评估与汇总 ====================

def evaluate_case(case: dict, retrieval_sources: Optional[Sequence[Any]], answer_result: Optional[dict],
                  k: int, latency: Optional[float] = None, error: Optional[str] = None) -> dict:
    """把一条用例的检索结果与问答结果打成一行明细。

    - ``retrieval_sources``：``query_with_sources`` 的 ``sources``（用于 recall / mrr）；
    - ``answer_result``：``answer_question`` 的返回（取 ``answer`` / ``kb_sources`` / ``kind``）；
    - 不适用的指标为 None；``error`` 非空时全部指标按最差值计（检索类为 0、判定类为 False）。

    ``passed`` 为一目了然的通过判定：检索类 = ``recall_at_k > 0`` 且（无关键词或 ``keyword_hit >= 0.5``）；
    ``meta`` = 识别为元查询；``negative`` = 被拒答。
    """
    ctype = str(case.get("type") or "single")
    expected_files = case.get("expected_files") or []
    expected_keywords = case.get("expected_keywords") or []
    result = answer_result or {}
    answer = str(result.get("answer") or "")
    kb_sources = result.get("kb_sources") or result.get("sources") or []
    kind = result.get("kind")
    retrieved = [source_file(s) for s in (retrieval_sources or [])]

    metrics: Dict[str, Any] = {key: None for key in METRIC_KEYS}
    metrics["latency"] = float(latency) if latency is not None else None

    if ctype in RETRIEVAL_TYPES:
        metrics["recall_at_k"] = recall_at_k(retrieval_sources, expected_files, k)
        metrics["mrr"] = mrr(retrieval_sources, expected_files)
        metrics["citation_hit_rate"] = citation_hit_rate(answer, kb_sources, expected_files)
        metrics["keyword_hit"] = keyword_hit(answer, expected_keywords)
    elif ctype == "meta":
        metrics["meta_detected"] = bool(kind == "meta")
    elif ctype == "negative":
        metrics["negative_rejected"] = negative_rejected(answer, kb_sources)

    if error:
        # 出错按最差值计：检索类有期望的指标为 0（不适用的仍为 None），判定类为 False
        if ctype in RETRIEVAL_TYPES:
            for key in ("recall_at_k", "mrr", "citation_hit_rate"):
                metrics[key] = 0.0 if expected_files else None
            metrics["keyword_hit"] = 0.0 if expected_keywords else None
        elif ctype == "meta":
            metrics["meta_detected"] = False
        elif ctype == "negative":
            metrics["negative_rejected"] = False

    if error:
        passed = False
    elif ctype in RETRIEVAL_TYPES:
        kw = metrics["keyword_hit"]
        passed = bool((metrics["recall_at_k"] or 0) > 0) and (kw is None or kw >= 0.5)
    elif ctype == "meta":
        passed = bool(metrics["meta_detected"])
    else:
        passed = bool(metrics["negative_rejected"])

    return {
        "id": case.get("id"),
        "type": ctype,
        "question": case.get("question", ""),
        "retrieved": retrieved,
        "retrieved_count": len(retrieved),
        "answer_kind": kind,
        "answer": answer[:600],
        "cited_files": cited_files(answer, kb_sources),
        "metrics": metrics,
        "passed": passed,
        "error": error,
    }


def _mean(values: List[Any]) -> Optional[float]:
    vals = [float(v) for v in values if v is not None]
    if not vals:
        return None
    return sum(vals) / len(vals)


def aggregate(rows: Sequence[dict]) -> dict:
    """按 ``type`` 分组求各指标均值（None 不计入），再给总均值。

    返回 ``{"n", "errors", "passed", "by_type": {type: {"n", "passed", <metric>...}}, "overall": {"n", "passed", <metric>...}}``；
    布尔指标的均值即比率。``by_type`` 按 ``CASE_TYPES`` 顺序、只含出现过的类型。
    """
    groups: Dict[str, List[dict]] = {}
    for row in rows:
        groups.setdefault(str(row.get("type") or "single"), []).append(row)

    def _summ(items: List[dict]) -> dict:
        out: Dict[str, Any] = {"n": len(items), "passed": sum(1 for r in items if r.get("passed"))}
        for key in METRIC_KEYS:
            out[key] = _mean([(r.get("metrics") or {}).get(key) for r in items])
        return out

    ordered = [t for t in CASE_TYPES if t in groups] + sorted(t for t in groups if t not in CASE_TYPES)
    return {
        "n": len(rows),
        "errors": sum(1 for r in rows if r.get("error")),
        "passed": sum(1 for r in rows if r.get("passed")),
        "by_type": {t: _summ(groups[t]) for t in ordered},
        "overall": _summ(list(rows)),
    }


# ==================== 样本加载 ====================

def load_cases(path: os.PathLike | str, type_filter: Optional[str] = None, limit: Optional[int] = None) -> List[dict]:
    """读取样本文件（``{"cases": [...]}`` 或裸列表），可按 ``type`` 过滤并截断前 ``limit`` 条。"""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    cases = data["cases"] if isinstance(data, dict) else data
    if type_filter:
        cases = [c for c in cases if c.get("type") == type_filter]
    if limit:
        cases = cases[:limit]
    return list(cases)


def type_distribution(cases: Sequence[dict]) -> Dict[str, int]:
    """各 ``type`` 的样本数（按 ``CASE_TYPES`` 顺序，含 0）。"""
    dist = {t: 0 for t in CASE_TYPES}
    for c in cases:
        dist[str(c.get("type") or "")] = dist.get(str(c.get("type") or ""), 0) + 1
    return dist


def validate_cases(cases: Sequence[dict], corpus_dir: Optional[os.PathLike | str] = None) -> List[str]:
    """样本合法性检查，返回问题列表（空即通过）：id 唯一、type 合法、question 非空、
    检索类必须有 expected_files、meta / negative 不应有 expected_files、expected_files 存在于语料目录。"""
    problems: List[str] = []
    seen: set = set()
    corpus_files = None
    if corpus_dir is not None and Path(corpus_dir).is_dir():
        corpus_files = {p.name.lower() for p in Path(corpus_dir).iterdir() if p.is_file()}
    for i, c in enumerate(cases):
        cid = str(c.get("id") or f"#{i}")
        if cid in seen:
            problems.append(f"{cid}: id 重复")
        seen.add(cid)
        ctype = c.get("type")
        if ctype not in CASE_TYPES:
            problems.append(f"{cid}: 非法 type {ctype!r}")
        if not str(c.get("question") or "").strip():
            problems.append(f"{cid}: question 为空")
        files = c.get("expected_files") or []
        if ctype in RETRIEVAL_TYPES and not files:
            problems.append(f"{cid}: 检索类样本缺少 expected_files")
        if ctype in ("meta", "negative") and files:
            problems.append(f"{cid}: {ctype} 样本不应有 expected_files")
        if corpus_files is not None:
            for f in files:
                if os.path.basename(str(f)).lower() not in corpus_files:
                    problems.append(f"{cid}: expected_files 中 {f} 不在语料目录")
    return problems


# ==================== Markdown 报告 ====================

def fmt_metric(key: str, value: Any) -> str:
    """单元格格式：比率两位小数、延迟一位小数带 s、None 为 ``—``。"""
    if value is None:
        return "—"
    if key == "latency":
        return f"{float(value):.1f}s"
    return f"{float(value):.2f}"


def fmt_delta(key: str, current: Any, previous: Any) -> str:
    """Δ 文本：任一为 None 返回空串；否则 ``(+0.05)`` / ``(-1.2s)`` / ``(±0.00)``。"""
    if current is None or previous is None:
        return ""
    diff = float(current) - float(previous)
    if key == "latency":
        body = f"{diff:+.1f}s" if abs(diff) >= 0.05 else "±0.0s"
    else:
        body = f"{diff:+.2f}" if abs(diff) >= 0.005 else "±0.00"
    return f" ({body})"


def _prev_aggregate(previous: Optional[dict]) -> Optional[dict]:
    if not previous:
        return None
    return previous.get("aggregate") if "aggregate" in previous else previous


def render_markdown(agg: dict, meta: dict, previous: Optional[dict] = None, rows: Optional[Sequence[dict]] = None) -> str:
    """渲染 Markdown 报告：运行信息表 + 按类型汇总表（有 ``previous`` 时各指标附 Δ）+ 可选逐例明细。

    ``previous`` 可以是上一份报告的完整 JSON（``{"meta", "aggregate", "rows"}``）或其 ``aggregate``。
    """
    prev = _prev_aggregate(previous)
    prev_meta = (previous or {}).get("meta") or {}
    lines: List[str] = [f"# RAG 检索基准报告 · {meta.get('tag', '')}", ""]

    info = [
        ("日期", meta.get("date", "")),
        ("对话模型", meta.get("model", "")),
        ("嵌入模型", meta.get("embed_model", "")),
        ("hybrid", meta.get("hybrid", "")),
        ("rerank", meta.get("rerank", "")),
        ("top_k", meta.get("top_k", "")),
        ("样本", f"{meta.get('n_cases', agg.get('n', ''))}（{meta.get('cases_file', '')}）"),
        ("语料", f"{meta.get('corpus_docs', '?')} 个文档 / {meta.get('chunks', '?')} 个片段（{meta.get('corpus_dir', '')}）"),
        ("通过 / 错误", f"{agg.get('passed', 0)}/{agg.get('n', 0)} · 错误 {agg.get('errors', 0)}"),
    ]
    if prev is not None:
        info.append(("对比基线", f"{prev_meta.get('tag', meta.get('tag', ''))} @ {prev_meta.get('date', '上一份')}（括号内为 Δ）"))
    lines += ["| 项 | 值 |", "|---|---|"]
    lines += [f"| {k} | {v} |" for k, v in info]
    lines.append("")

    lines.append("## 指标汇总")
    lines.append("")
    header = ["类型", "用例", "通过"] + [METRIC_LABELS[k] for k in METRIC_KEYS]
    lines.append("| " + " | ".join(header) + " |")
    lines.append("|" + "---|" * len(header))

    def _row(label: str, summ: dict, prev_summ: Optional[dict]) -> str:
        cells = [label, str(summ.get("n", 0)), f"{summ.get('passed', 0)}/{summ.get('n', 0)}"]
        for key in METRIC_KEYS:
            cur = summ.get(key)
            cell = fmt_metric(key, cur)
            if prev_summ is not None:
                cell += fmt_delta(key, cur, prev_summ.get(key))
            cells.append(cell)
        return "| " + " | ".join(cells) + " |"

    for ctype, summ in (agg.get("by_type") or {}).items():
        prev_summ = ((prev or {}).get("by_type") or {}).get(ctype) if prev else None
        lines.append(_row(TYPE_LABELS.get(ctype, ctype), summ, prev_summ))
    lines.append(_row("**合计**", agg.get("overall") or {}, (prev or {}).get("overall") if prev else None))
    lines.append("")

    if rows:
        lines.append("## 逐例明细")
        lines.append("")
        lines.append("| id | 类型 | 判定 | Recall@k | MRR | 引用命中 | 关键词 | 命中文件（前 3） | 引用文件 | 延迟 |")
        lines.append("|---|---|---|---|---|---|---|---|---|---|")
        for r in rows:
            m = r.get("metrics") or {}
            mark = "❌ 错误" if r.get("error") else ("✅" if r.get("passed") else "❌")
            if r.get("type") == "meta":
                extra = "识别" if m.get("meta_detected") else "未识别"
            elif r.get("type") == "negative":
                extra = "拒答" if m.get("negative_rejected") else "未拒答"
            else:
                extra = ""
            mark = f"{mark} {extra}".strip()
            files = ", ".join(list(dict.fromkeys(r.get("retrieved") or []))[:3])
            cited = ", ".join(r.get("cited_files") or []) or "—"
            lines.append(
                f"| {r.get('id')} | {r.get('type')} | {mark} | {fmt_metric('recall_at_k', m.get('recall_at_k'))} | "
                f"{fmt_metric('mrr', m.get('mrr'))} | {fmt_metric('citation_hit_rate', m.get('citation_hit_rate'))} | "
                f"{fmt_metric('keyword_hit', m.get('keyword_hit'))} | {files or '—'} | {cited} | "
                f"{fmt_metric('latency', m.get('latency'))} |"
            )
        errors = [r for r in rows if r.get("error")]
        if errors:
            lines.append("")
            lines.append("错误明细：")
            lines.append("")
            for r in errors:
                lines.append(f"- `{r.get('id')}`：{r.get('error')}")
        lines.append("")

    lines.append("## 指标说明")
    lines.append("")
    lines += [
        "- **Recall@k**：`query_with_sources` 前 k 个来源覆盖期望文件的比例（按文件去重）。",
        "- **MRR**：第一个命中期望文件的来源的倒数排名，无命中为 0。",
        "- **引用命中**：答案中 `[n]` 引用指向期望文件的比例；编号越界 / 无引用计 0。",
        "- **关键词命中**：期望关键词（`|` 分隔同义项）在答案中出现的比例（归一化比较）。",
        "- **负样本拒答**：无来源、答案为空或含拒答 / 核对词表任一词即视为拒答。",
        "- **元查询识别**：编排层返回 `kind == \"meta\"`。",
        "- **平均延迟**：单例「检索 + 问答」总耗时（秒），含模型生成。",
        "- **通过**：检索类 Recall@k > 0 且关键词命中 ≥ 0.5（无关键词时不要求）；meta 被识别；negative 被拒答。",
    ]
    return "\n".join(lines).rstrip() + "\n"
