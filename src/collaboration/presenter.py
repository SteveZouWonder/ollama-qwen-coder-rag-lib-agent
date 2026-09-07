"""
多 Agent 协作结果的 Markdown 渲染（CLI 与 Web 共用，保证两端输出一致）。
"""
from typing import Any, Dict, List


def _agent_line(r: Dict[str, Any], task_desc: str = "") -> List[str]:
    status = "✅" if r.get("success") else "❌"
    agent_id = r.get("agent_id", "?")
    meta = r.get("metadata") or {}
    bits = []
    if meta.get("steps"):
        bits.append(f"{meta['steps']} 步")
    if meta.get("tools"):
        bits.append("工具: " + "、".join(str(t) for t in meta["tools"][:6]))
    if meta.get("incomplete"):
        bits.append("未完成")
    if meta.get("unverified"):
        bits.append("⚠️ 未经验证")
    et = r.get("execution_time")
    if isinstance(et, (int, float)) and et > 0:
        bits.append(f"{et:.1f}s")
    head = f"{status} **{agent_id}**"
    if task_desc:
        head += f" · {task_desc}"
    if bits:
        head += f"（{'，'.join(bits)}）"
    lines = [head]
    if not r.get("success") and r.get("error_message"):
        lines.append(f"> 错误：{str(r['error_message'])[:300]}")
    return lines


def format_sources_md(sources: List[Dict[str, Any]]) -> str:
    """渲染结构化来源列表（kb / web）。"""
    if not sources:
        return ""
    lines = ["**📚 来源**"]
    for i, s in enumerate(sources, 1):
        if s.get("kind") == "web":
            title = s.get("title") or s.get("url") or "网页"
            url = s.get("url") or ""
            lines.append(f"{i}. 🌐 [{title}]({url})" if url else f"{i}. 🌐 {title}")
        else:
            score = s.get("score")
            score_str = f"（相似度 {score:.3f}）" if isinstance(score, (int, float)) else ""
            loc = ""
            if s.get("symbol"):
                loc += f" · `{s['symbol']}`"
            if s.get("start_line") is not None:
                loc += f" · L{s['start_line']}-{s.get('end_line') or s['start_line']}"
            lines.append(f"{i}. 📄 {s.get('file', '未知')}{loc}{score_str}")
    return "\n".join(lines)


def format_multi_agent_result(result: Dict[str, Any]) -> str:
    """把多 Agent 协作结果渲染为 Markdown：综合回答 + 各 Agent 摘要 + 来源。

    兼容 HIERARCHY/PARALLEL/SEQUENTIAL 的 ``results`` 结构与 COMPETITIVE 的
    ``best_result`` / ``all_results`` 结构。
    """
    if not isinstance(result, dict):
        return "**❌ 协作失败**"
    if not result.get("success"):
        err = result.get("error", "")
        summary = result.get("summary", "协作失败")
        answer = (result.get("answer") or "").strip()
        parts = [f"**❌ {summary}**"]
        if err:
            parts.append(str(err))
        if answer:
            parts.append(answer)
        # 部分失败时仍展示各 Agent 状态，便于定位
        results = result.get("results") or result.get("all_results") or []
        if results:
            parts.append("")
            for r in results:
                parts.extend(_agent_line(r))
        return "\n\n".join(p for p in parts if p is not None).strip()

    lines: List[str] = []
    answer = (result.get("answer") or "").strip()
    summary = result.get("summary", "协作完成")

    if answer:
        lines.append(answer)
        lines.append("")
        lines.append("---")
    lines.append(f"**✅ {summary}**")

    # 各 Agent 摘要
    task_desc = {t.get("task_id"): t.get("description", "") for t in (result.get("tasks") or [])}
    if "best_result" in result:
        best = result.get("best_result") or {}
        lines.append("")
        lines.append(f"🏆 选用：**{best.get('agent_id', '?')}** — {result.get('selection_criteria', '')}")
        others = [r for r in (result.get("all_results") or []) if r is not best]
        if others:
            lines.append("")
            lines.append("其他候选：")
            for r in others:
                lines.extend(_agent_line(r))
    else:
        results = result.get("results") or []
        if results:
            lines.append("")
            lines.append(
                f"成功 {result.get('successful_results', 0)} / 共 {result.get('total_results', len(results))}"
            )
            for r in results:
                lines.extend(_agent_line(r, task_desc.get(r.get("task_id"), "")))
        if not answer:
            # 无综合回答（旧结构/回退）：直接展示各 Agent 输出
            for r in results:
                output = (r.get("output") or "").strip()
                if output:
                    lines.append("")
                    lines.append(f"> {output}")

    src_md = format_sources_md(result.get("sources") or [])
    if src_md:
        lines.append("")
        lines.append(src_md)
    return "\n".join(lines).rstrip()
