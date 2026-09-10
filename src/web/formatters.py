"""Web 呈现层的纯格式化函数（不依赖 gradio，可独立单元测试）。

由 ``web/app.py`` 拆出（F10 P2-2）：进度跟踪 ``ProgressTracker``、``format_*`` / ``*_rows`` /
表头常量 / 图谱 ``build_graph_figure`` 等全部纯函数。``web.app`` 重导出本模块全部公开名，
``from web.app import format_sources`` 等旧路径不变。
"""
from __future__ import annotations

import time
from typing import Any, Callable, Dict, List, Optional, Tuple


# 对话页模式分段的「自动」标签（与 ui/chat.py 的 MODE_AUTO 保持一致）：
# 服务层先判定意图再分发到 RAG / 单 Agent，UI 按 answer.data["routed_mode"] 渲染。
MODE_AUTO = "自动"

try:  # 上下文状态/提示的纯格式化函数（核心层提供，前端只接线）
    from conversation_context import (
        CARRY_PREFIX, format_context_status, format_suggest_hint, format_tokens,  # noqa: F401
    )
except ImportError:  # pragma: no cover - 以 src.* 方式导入时的兜底
    from src.conversation_context import (  # type: ignore # noqa: F401
        CARRY_PREFIX, format_context_status, format_suggest_hint, format_tokens,  # noqa: F401
    )

# "携带摘要"新建的会话在对话区顶部展示的可折叠说明标题
CARRIED_TITLE = "🧳 承接自上一会话的摘要（非本会话对话，仅作背景）"


# ==================== 进度跟踪（可测试）====================

def format_elapsed(seconds: float) -> str:
    """把秒数渲染为"12 秒" / "1 分 05 秒"。"""
    seconds = max(0, int(seconds))
    if seconds < 60:
        return f"{seconds} 秒"
    minutes, sec = divmod(seconds, 60)
    return f"{minutes} 分 {sec:02d} 秒"


class ProgressTracker:
    """聚合一次对话任务的进度事件，渲染为"状态行 + 处理过程列表"。

    解决的问题：此前 Web 端只把进度事件逐条追加进一个 Markdown，导致：
    - 单 Agent 每 0.5s 的"模型推理中..."心跳刷屏；
    - RAG 的"评分文档 1/5 … 5/5"占满列表；
    - 没有耗时，用户分不清"慢"还是"卡死"。

    规则：
    - ``transient`` 事件（如推理心跳）只更新"当前活动"文案，不进入步骤列表；
    - 带 ``current``/``total`` 计数且与上一条同 ``stage``/``phase`` 的事件
      原地替换上一行（进度条式刷新）；
    - 其余事件按顺序追加。
    """

    def __init__(self, clock: Callable[[], float] = time.monotonic, hint: str = ""):
        self._clock = clock
        self._start = clock()
        self.steps: List[str] = []
        self.current: str = ""
        self.hint = hint  # 附加提示（如"思考模式已开，响应较慢"）
        self._last_key: Optional[str] = None
        self._last_counter = False

    # ---- 事件接入 ----

    def add(self, message: str, data: Optional[Dict[str, Any]] = None) -> None:
        message = (message or "").strip()
        if not message:
            return
        data = data or {}
        if data.get("transient"):
            self.current = message
            return
        key = data.get("stage") or data.get("phase")
        counter = "current" in data and "total" in data
        if (
            counter
            and self._last_counter
            and key
            and key == self._last_key
            and self.steps
        ):
            self.steps[-1] = message
        else:
            self.steps.append(message)
        self._last_key = key
        self._last_counter = counter
        self.current = message

    def elapsed(self) -> float:
        return self._clock() - self._start

    # ---- 渲染 ----

    def render_status(self, state: str = "running", detail: str = "") -> str:
        """渲染一行状态：``running`` / ``done`` / ``error`` / ``cancelled``。"""
        took = format_elapsed(self.elapsed())
        if state == "done":
            return f"✅ 完成 · 用时 {took}"
        if state == "cancelled":
            return f"⏹️ 已停止 · 用时 {took}"
        if state == "error":
            return f"❌ 出错 · 用时 {took}" + (f" · {detail}" if detail else "")
        activity = self.current or "准备中..."
        line = f"⏳ {activity} · 已用时 {took}"
        if self.hint:
            line += f" · {self.hint}"
        return line

    def render_steps(self, title: str = "处理过程", done: bool = False) -> str:
        if not self.steps:
            return ""
        head = f"**{title}**" + ("（已完成）" if done else "")
        lines = [head, ""]
        lines.extend(f"{i}. {s}" for i, s in enumerate(self.steps, 1))
        return "\n".join(lines)


# ==================== 纯格式化辅助（可测试）====================

def _fmt_result(text: str) -> str:
    """把服务层 ``[成功]/[提示]/[错误]`` 前缀换成图标。"""
    for prefix, icon in (("[成功]", "✅"), ("[提示]", "💡"), ("[错误]", "❌")):
        if text.startswith(prefix):
            return icon + text[len(prefix):]
    return text


def component_update(**kwargs: Any) -> Dict[str, Any]:
    """等价 ``gr.update(**kwargs)`` 的纯字典（本模块不 import gradio，便于单元测试）。

    Gradio 以 ``{"__type__": "update", ...}`` 识别属性更新；无参数即"保持不变"。
    用于「📎 引用来源」Accordion 的 ``open`` 控制（F9 P0-3）。
    """
    out: Dict[str, Any] = dict(kwargs)
    out["__type__"] = "update"
    return out


def _noop() -> Dict[str, Any]:
    """八元组第 8 位的默认值：不改变 Accordion 当前折叠状态。"""
    return component_update()


def _starts_new_round(kind: str, data: Optional[Dict[str, Any]]) -> bool:
    """单 Agent 进入新一轮模型推理（非心跳的 ``thinking`` step 事件）——F10 P1-1。

    极少数情况下模型在一轮里先写 ``Final Answer:`` 又写 ``Action:``，协议解析按工具
    调用处理并进入下一轮；此时已流出的半截答案作废，UI 清空重来。
    """
    if kind != "step" or not isinstance(data, dict):
        return False
    return data.get("phase") == "thinking" and not data.get("transient")


def format_notices(notices: Optional[List[Dict[str, Any]]], position: str = "before") -> str:
    """把 ``answer_question`` 的结构化提示渲染为 blockquote（F9 P0-5）。

    warn → ``> ⚠️ text``，info → ``> 💡 text``（与 ``> 🔗 已理解为`` 同款，多条各一行）；
    ``code=="fallback"`` 不入气泡（沿用 retry 行）。返回空串表示该位置无提示；非空时
    ``before`` 组以空行结尾、``after`` 组以空行开头，便于直接与正文拼接。
    """
    lines = []
    for n in notices or []:
        if not isinstance(n, dict) or n.get("code") == "fallback":
            continue
        if (n.get("position") or "before") != position:
            continue
        text = str(n.get("text") or "").strip()
        if not text:
            continue
        icon = "⚠️" if n.get("level") == "warn" else "💡"
        lines.append(f"> {icon} {text}")
    if not lines:
        return ""
    block = "\n".join(lines)
    return block + "\n\n" if position == "before" else "\n\n" + block


def format_citation_status(check: Optional[Dict[str, Any]]) -> str:
    """状态行的引用校验片段（F9 P0-3）：全部有效 ``🔎 引用 N 处已核验``，否则 ``🔎 引用 v/t 有效``。"""
    if not isinstance(check, dict):
        return ""
    total = int(check.get("total_refs") or 0)
    if total <= 0:
        return ""
    valid = int(check.get("valid") or 0)
    if valid == total:
        return f"🔎 引用 {total} 处已核验"
    return f"🔎 引用 {valid}/{total} 有效"


def format_sources(sources: List[Dict[str, Any]], citation_check: Optional[Dict[str, Any]] = None) -> str:
    """把 sources 列表渲染为 Markdown 文本（按引用编号 ``[1]``.. 显示，与答案中的标注对应）。

    F9 P0-3：每条标题行末追加 ``（被引用 n 次）`` / ``（未被引用）``；``citation_check``
    有无效编号时面板首行列出 ``⚠️ 无效引用：[5] [W3]（回答中已标为 [?]）``。
    """
    if not sources:
        return "_无引用来源_"
    lines = ["### 引用来源", ""]
    invalid = (citation_check or {}).get("invalid") if isinstance(citation_check, dict) else None
    if invalid:
        refs = " ".join(f"[{r}]" for r in invalid)
        lines.append(f"⚠️ 无效引用：{refs}（回答中已标为 [?]）")
        lines.append("")
    for i, src in enumerate(sources, 1):
        score = src.get("score")
        score_str = f"（相似度 {score:.3f}）" if isinstance(score, (int, float)) else ""
        if src.get("retriever") == "bm25":
            score_str += "（关键词命中）"
        file_name = src.get("file", "未知")
        content = (src.get("content") or "").strip()
        ref = str(src.get("ref") or i)
        # 代码块：标题带 `符号` · L起-止，内容用对应语言的围栏渲染（可定位、可复制）
        loc = ""
        if src.get("symbol"):
            loc += f" · `{src['symbol']}`"
        if src.get("start_line") is not None:
            loc += f" · L{src['start_line']}-{src.get('end_line') or src['start_line']}"
        if src.get("part"):
            loc += f"（{src['part']}）"
        cited = src.get("cited")
        if isinstance(cited, int):
            cited_str = f"（被引用 {cited} 次）" if cited > 0 else " _（未被引用）_"
        else:
            cited_str = ""
        lines.append(f"**[{ref}] {file_name}**{loc} {score_str}{cited_str}".rstrip())
        note = (src.get("rerank_note") or "").strip()
        if note:
            lines.append(f"_相关性：{note}_")
        if content:
            if src.get("symbol") or str(src.get("chunk_strategy", "")).startswith("code"):
                lang = str(src.get("language") or "")
                lines.append(f"```{lang}")
                lines.append(content.replace("```", "ˋˋˋ"))
                lines.append("```")
            else:
                lines.append(f"> {content}")
        lines.append("")
    return "\n".join(lines).rstrip()


def format_web_sources(sources: List[Dict[str, Any]]) -> str:
    """把网络来源列表渲染为 Markdown 文本（按引用编号 ``[W1]``.. 显示，与知识库来源明确区分）。"""
    if not sources:
        return ""
    lines = ["### 🌐 网络来源", ""]
    for i, src in enumerate(sources, 1):
        title = src.get("title", "") or src.get("url", "")
        url = src.get("url", "")
        ref = str(src.get("ref") or f"W{i}")
        if url:
            lines.append(f"- **[{ref}]** [{title}]({url})")
        else:
            lines.append(f"- **[{ref}]** {title}")
    return "\n".join(lines)


def format_fallback_hint(question: str) -> str:
    """知识库与网络均无结果时的提示文案（旁边显示「用单 Agent 重试」按钮）。"""
    q = (question or "").strip()
    return f"📭 知识库与网络均未找到相关内容。可让单 Agent 用工具进一步查找：`/agent {q}`" if q else ""


def format_meta_overview(meta: Dict[str, Any]) -> str:
    """把知识库概览（元查询直答）渲染为 Markdown。"""
    files = (meta or {}).get("files") or []
    stats = (meta or {}).get("stats") or {}
    lines = ["### 📚 知识库概览", ""]
    if not files:
        lines.append("_知识库中暂无已登记的文件。_")
        if stats.get("total_documents"):
            lines.append(
                f"\n（向量库中存在 {stats['total_documents']} 个文档片段，"
                f"但未登记文件元数据）"
            )
    else:
        lines.append(f"共有 **{len(files)}** 个文件：")
        for fm in files:
            lines.append(f"- 📄 `{fm.get('path')}`（{fm.get('size', '?')}）")
    if stats:
        lines.append("")
        lines.append(
            f"文档片段总数: {stats.get('total_documents', '?')} | "
            f"Embedding: `{stats.get('embed_model', '?')}`"
        )
    return "\n".join(lines)


def format_rag_side(result: Dict[str, Any]) -> str:
    """组合 RAG 回答的附加信息区：知识库来源 + 网络来源（含引用校验明细，P0-3）。"""
    parts = []
    check = result.get("citation_check")
    kb = format_sources(result.get("sources", []), citation_check=check)
    if kb and kb != "_无引用来源_":
        parts.append(kb)
    elif isinstance(check, dict) and check.get("invalid"):
        # 只有网络来源时，无效编号提示同样放面板首行
        refs = " ".join(f"[{r}]" for r in check["invalid"])
        parts.append(f"⚠️ 无效引用：{refs}（回答中已标为 [?]）")
    web = format_web_sources(result.get("web_sources", []))
    if web:
        parts.append(web)
    if not parts:
        return "_无引用来源_"
    return "\n\n".join(parts)


def format_stats(stats: Dict[str, Any]) -> str:
    """把知识库统计渲染为 Markdown 文本。"""
    if "error" in stats:
        return f"[错误] 获取统计失败: {stats['error']}"
    return (
        f"- 文档片段总数: **{stats.get('total_documents', 0)}**\n"
        f"- LLM 模型: `{stats.get('llm_model', '?')}`"
        + (f"（num_ctx={stats['llm_num_ctx']}）" if stats.get("llm_num_ctx") else "")
        + "\n"
        f"- Embedding 模型: `{stats.get('embed_model', '?')}`\n"
        f"- 分块大小: {stats.get('chunk_size', '?')}\n"
        f"- 分块重叠: {stats.get('chunk_overlap', '?')}\n"
        f"- 代码分块: {stats.get('code_chunking', '?')}\n"
        f"- 检索数量 TOP_K: {stats.get('top_k', '?')}"
        + (f"\n- 混合检索: {stats['hybrid']}" if stats.get("hybrid") else "")
        + (f"\n\n> ⚠️ {_hybrid_disabled_text(stats)}" if stats.get("hybrid_disabled_reason") else "")
    )


def _hybrid_disabled_text(stats: Dict[str, Any]) -> str:
    """混合检索被关闭时的提示（F10 P2-1-b）：引擎给出原因与调法，这里只在原因未自述时补前缀。"""
    reason = str(stats.get("hybrid_disabled_reason") or "")
    if "混合检索已关闭" in reason:
        return reason
    return f"混合检索已关闭：{reason}（可设置 RAG_HYBRID=false 明确关闭，或安装 rank_bm25）"


def format_model_status(info: Dict[str, Any]) -> str:
    """把当前模型概况渲染为一行 Markdown 状态（对话页顶部显示）。"""
    if info.get("error"):
        return f"**模型**: `{info.get('model', '?')}`  ·  [错误] {info['error']}"
    if info.get("loaded"):
        size = info.get("size_bytes") or 0
        gb = size / (1024 ** 3)
        state = f"已加载，驻留 {gb:.1f} GB" if gb >= 0.1 else "已加载"
    else:
        state = "未加载（首次提问时按需加载）"
    think = "开" if info.get("think") else "关"
    provider = str(info.get("provider") or "ollama")
    if provider != "ollama":
        # OpenAI 兼容后端：驻留 / num_ctx / 思考模式均由后端决定
        line = (
            f"**模型**: `{info.get('model', '?')}`  ·  后端 `{provider}` @ `{info.get('base_url', '')}`"
            f"  ·  num_ctx / 思考模式由后端决定"
        )
        if info.get("models_notice"):
            line += f"  ·  ⚠️ {info['models_notice']}"
        return line
    line = (
        f"**模型**: `{info.get('model', '?')}`  ·  {state}  ·  "
        f"num_ctx={info.get('num_ctx', '?')}  ·  思考模式 {think}"
    )
    others = [m for m in info.get("loaded_models", []) if m != info.get("model")]
    if others:
        line += f"  ·  ⚠️ 内存中还驻留: {', '.join(f'`{m}`' for m in others)}"
    return line


def format_model_chip(info: Dict[str, Any]) -> str:
    """把当前模型概况渲染为顶栏状态胶囊（HTML）。"""
    model = info.get("model", "?")
    if info.get("error"):
        return (
            f'<span class="cb-status-chip"><span class="dot off"></span>'
            f'<code>{model}</code> · 连接失败</span>'
        )
    provider = str(info.get("provider") or "ollama")
    if provider != "ollama":
        # OpenAI 兼容后端：驻留 / ctx / 思考由后端决定，只显示 provider 与地址
        return (
            f'<span class="cb-status-chip"><span class="dot"></span>'
            f'<code>{model}</code> · {provider} · <code>{info.get("base_url", "")}</code></span>'
        )
    if info.get("loaded"):
        gb = (info.get("size_bytes") or 0) / (1024 ** 3)
        state = f"已加载 {gb:.1f} GB" if gb >= 0.1 else "已加载"
        dot = "dot"
    else:
        state = "未加载"
        dot = "dot off"
    think = "思考 开" if info.get("think") else "思考 关"
    parts = [f"<code>{model}</code>", state, f"ctx {info.get('num_ctx', '?')}", think]
    others = [m for m in info.get("loaded_models", []) if m != model]
    if others:
        parts.append(f"⚠️ 另驻留 {len(others)} 个模型")
    return f'<span class="cb-status-chip"><span class="{dot}"></span>{" · ".join(parts)}</span>'


def format_switch_result(result: Dict[str, Any]) -> str:
    """把模型切换结果渲染为 Markdown。"""
    prefix = "✅" if result.get("ok") else "❌"
    return f"{prefix} {result.get('message', '')}"


def format_multi_agent_result(result: Dict[str, Any]) -> str:
    """把多 Agent 协作结果渲染为 Markdown 文本（与 CLI ``/multi`` 共用渲染器）。

    展示综合回答 ``answer`` + 各 Agent 摘要（步数/工具/耗时）+ 结构化来源，
    兼容 COMPETITIVE 模式的 ``best_result`` / ``all_results`` 结构。
    """
    from collaboration.presenter import format_multi_agent_result as _render

    return _render(result if isinstance(result, dict) else {})


_SESSION_STATUS_ICON = {"active": "🟢 活跃", "archived": "📦 已归档", "deleted": "🗑️ 已删除"}


def _md_cell(text: Any) -> str:
    """表格单元格转义：去掉换行与竖线，避免破坏 Markdown 表格。"""
    return str("" if text is None else text).replace("\n", " ").replace("|", "／").strip()


def format_sessions(sessions: List[Dict[str, Any]]) -> str:
    """把会话列表渲染为 Markdown 表格（当前会话以 ▶ 与加粗标出）。"""
    if not sessions:
        return "### 💬 会话列表\n\n_暂无会话。在「对话」页提问会自动创建，或在下方新建。_"
    current = sum(1 for s in sessions if s.get("is_current"))
    lines = [
        f"### 💬 会话列表（共 {len(sessions)} 个）",
        "",
        "| | 标题 | 状态 | 消息 | 最近更新 | 首条提问 | ID |",
        "|:-:|---|---|--:|---|---|---|",
    ]
    for s in sessions:
        is_cur = bool(s.get("is_current"))
        title = _md_cell(s.get("title") or "未命名")
        if is_cur:
            title = f"**{title}**"
        status = _SESSION_STATUS_ICON.get(s.get("status") or "", s.get("status") or "—")
        preview = _md_cell(s.get("preview") or "")
        preview = f"_{preview}_" if preview else "—"
        lines.append(
            f"| {'▶' if is_cur else ''} | {title} | {status} | {s.get('messages', 0)} | "
            f"{_md_cell(s.get('updated_at')) or '—'} | {preview} | `{(s.get('session_id') or '')[:8]}` |"
        )
    if current:
        lines += ["", "_▶ 为当前会话（CLI 与新开的对话页默认使用）。_"]
    return "\n".join(lines)


def format_context_metrics(m: Dict[str, Any]) -> str:
    """把上下文指标渲染为一小段 Markdown（对话页会话控件下方显示）。"""
    if not m:
        return ""
    if m.get("error"):
        return f"_上下文信息不可用：{m['error']}_"
    line = (
        f"🧠 上下文：{m.get('turns', 0)} 轮 · "
        f"{format_tokens(m.get('history_tokens', 0))} / {format_tokens(m.get('budget', 0))} tokens"
    )
    comp = int(m.get("compressions", 0) or 0)
    if comp:
        line += f" · 已压缩 {comp} 次"
    summary = (m.get("summary") or "").strip()
    if summary:
        label = "📝 摘要"
        if summary.startswith(CARRY_PREFIX):
            label = "🧳 承接自上一会话"
            summary = summary[len(CARRY_PREFIX):].strip()
        preview = summary if len(summary) <= 120 else summary[:120] + "…"
        line += f"\n\n> {label}：{preview}"
    return line


def with_context_status(status: str, ctx: Optional[Dict[str, Any]]) -> str:
    """在状态行末尾追加 ``上下文 3.2K / 4.8K · 已压缩 1 次``。"""
    extra = format_context_status(ctx) if isinstance(ctx, dict) and not ctx.get("error") else ""
    return f"{status} · {extra}" if extra else status


def format_step_log(step_log: List[Dict[str, Any]]) -> str:
    """把单 Agent 的 ``step_log`` 渲染为执行摘要（对齐 CLI ``/summary``）。"""
    if not step_log:
        return ""
    lines = ["**执行摘要**", ""]
    for log in step_log:
        if not isinstance(log, dict):
            continue
        step = log.get("step", "?")
        phase = log.get("phase", "")
        if phase == "action":
            mark = "✅" if log.get("confirmed", True) else "⛔"
            tool = log.get("tool", "?")
            line = f"- Step {step} {mark} 调用 `{tool}`"
            safety = log.get("safety") or {}
            if isinstance(safety, dict) and safety.get("risk_level"):
                line += f"（风险 {safety['risk_level']}）"
            thought = (log.get("thought") or "").strip().replace("\n", " ")
            if thought:
                line += f" — {thought[:80]}{'…' if len(thought) > 80 else ''}"
            lines.append(line)
        elif phase == "blocked":
            lines.append(f"- Step {step} 🛡️ 危险命令被拦截")
        elif phase == "rejected":
            lines.append(f"- Step {step} ⛔ 用户拒绝执行")
        elif phase == "format_retry":
            reason = (log.get("reason") or "").strip()
            lines.append(f"- Step {step} 🔁 输出格式错误，回灌重试（第 {log.get('retry', '?')} 次）"
                         + (f"：{reason[:80]}" if reason else ""))
        elif phase == "repeat":
            lines.append(f"- Step {step} ♻️ 重复调用 `{log.get('tool', '?')}`（第 {log.get('count', '?')} 次相同参数）")
        elif phase == "budget_fold":
            folded = "、".join(str(s) for s in log.get("folded_steps", []))
            lines.append(f"- Step {step} 🗜️ 上下文超预算，已折叠第 {folded} 步的 Observation")
        elif phase == "forced_summary":
            why = "步数已用尽" if log.get("reason") == "max_iterations" else "重复调用终止"
            lines.append(f"- Step {step} ⚠️ {why}，请模型总结已完成/未完成/建议")
        elif phase == "error":
            lines.append(f"- Step {step} ❌ {log.get('message', '模型调用失败')}")
        elif phase == "final":
            if log.get("forced"):
                lines.append(f"- Step {step} ⚠️ 未完成，强制总结收尾")
            elif log.get("format_abnormal"):
                lines.append(f"- Step {step} 🏁 格式异常，按现有文本收尾（可能不完整）")
            else:
                lines.append(f"- Step {step} 🏁 给出最终答案")
    return "\n".join(lines) if len(lines) > 2 else ""


_RISK_LABEL = {"low": "低", "medium": "中", "high": "高", "critical": "危险"}


def format_confirm_request(evt: Dict[str, Any]) -> str:
    """把 Agent 的确认请求渲染为审批卡片文案。"""
    if not evt:
        return ""
    tool = evt.get("tool") or "操作"
    lines = [f"**⚠️ Agent 请求执行需确认的操作：`{tool}`**"]
    cmd = evt.get("command")
    if cmd:
        lines.append(f"```\n{cmd}\n```")
    args = evt.get("args")
    if args and not cmd:
        try:
            import json
            lines.append(f"```json\n{json.dumps(args, ensure_ascii=False, indent=2)[:600]}\n```")
        except Exception:  # noqa: BLE001
            lines.append(f"`{args}`")
    safety = evt.get("safety") or {}
    if isinstance(safety, dict) and safety.get("risk_level"):
        risk = safety["risk_level"]
        lines.append(
            f"风险等级：<span class=\"cb-risk-{risk}\">{_RISK_LABEL.get(risk, risk)}</span>"
        )
    lines.append("_点击「允许」继续执行，「拒绝」则 Agent 会改用其他方式或说明风险。_")
    return "\n\n".join(lines)


def format_exec_analysis(safety: Dict[str, Any]) -> str:
    """把 Shell 命令安全分析渲染为 Markdown。"""
    if not safety:
        return ""
    if safety.get("error"):
        return f"❌ {safety['error']}"
    risk = safety.get("risk_level", "unknown")
    label = _RISK_LABEL.get(risk, risk)
    line = f"风险等级：<span class=\"cb-risk-{risk}\">{label}</span>"
    if safety.get("is_dangerous"):
        reasons = "；".join(safety.get("danger_reasons") or [])
        return f"🛡️ **该命令被安全系统拦截，拒绝执行。** {reasons}\n\n{line}"
    if safety.get("needs_confirm"):
        return f"{line} · 该命令会修改系统，执行前需确认。"
    return f"{line} · 只读命令，可直接执行。"


def format_kv_table(rows: List[Tuple[str, Any]]) -> str:
    """把键值对渲染为两列 Markdown 表格。"""
    if not rows:
        return ""
    lines = ["| 项 | 值 |", "|---|---|"]
    for k, v in rows:
        lines.append(f"| {_md_cell(k)} | {_md_cell(v) or '—'} |")
    return "\n".join(lines)


def format_session_info(info: Dict[str, Any]) -> str:
    """会话详情（对齐 CLI ``/session-info``）。"""
    if not info:
        return ""
    if info.get("error"):
        return f"_{info['error']}_"
    rows = [
        ("ID", f"`{info.get('session_id', '')}`"),
        ("标题", info.get("title", "")),
        ("状态", _SESSION_STATUS_ICON.get(info.get("status") or "", info.get("status") or "—")),
        ("创建时间", info.get("created_at", "")),
        ("最近更新", info.get("updated_at", "")),
        ("消息数", info.get("messages", 0)),
    ]
    tags = info.get("tags") or []
    if tags:
        rows.append(("标签", ", ".join(map(str, tags))))
    meta = info.get("metadata") or {}
    if meta:
        rows.append(("元数据", str(meta)[:200]))
    return format_kv_table(rows)


def format_file_info(info: Dict[str, Any]) -> str:
    """单文件元数据详情（对齐 CLI ``/file-info``）。"""
    if not info:
        return ""
    if info.get("error"):
        return f"_{info['error']}_"
    rows = [
        ("路径", f"`{info.get('path', '')}`"),
        ("大小", info.get("size", "")),
        ("持久化类型", info.get("type", "")),
        ("上传时间", info.get("upload_time", "")),
        ("最后访问", info.get("last_access", "") or "—"),
        ("访问次数", info.get("access_count", 0)),
        ("文档数", info.get("document_count", 0)),
        ("片段数", info.get("chunk_count", 0)),
        ("分块策略", info.get("chunking", "") or "文本"),
    ]
    if info.get("symbol_count"):
        rows.append(("符号数", info.get("symbol_count", 0)))
    tags = info.get("tags") or []
    if tags:
        rows.append(("标签", ", ".join(map(str, tags))))
    return format_kv_table(rows)


_DIR_LIST_MAX_SHOWN = 6


def _fmt_dir_list(dirs: Optional[List[str]], env_name: str) -> str:
    """把允许目录列表渲染成一格：``` `d1` · `d2` ``` ；为空时提示可用的环境变量。

    已入库文档目录会随知识库增长，超过 ``_DIR_LIST_MAX_SHOWN`` 个时折叠为"共 N 个"。
    """
    items = [str(d) for d in (dirs or []) if str(d).strip()]
    if not items:
        return f"—（可设置 `{env_name}` 放行）"
    text = " · ".join(f"`{d}`" for d in items[:_DIR_LIST_MAX_SHOWN])
    if len(items) > _DIR_LIST_MAX_SHOWN:
        text += f" …（共 {len(items)} 个）"
    return text


def format_env_info(info: Dict[str, Any]) -> str:
    """运行环境概览（对齐 CLI 横幅 + ``/model`` 附加字段）。"""
    if not info:
        return ""
    if info.get("error"):
        return f"_读取配置失败：{info['error']}_"
    provider = str(info.get("llm_provider") or "ollama")
    healthy = info.get("backend_healthy")
    health_text = "—" if healthy is None else ("✅ 可达" if healthy else "❌ 不可达（请确认服务已启动、地址正确）")
    rows = [
        ("LLM 后端", f"`{provider}`" + ("" if provider == "ollama" else "（OpenAI 兼容；`num_ctx` / 思考模式由后端决定）")),
        ("后端地址", f"`{info.get('llm_base_url') or info.get('ollama_url', '')}`"),
        ("后端状态", health_text),
    ]
    if provider != "ollama":
        rows.append(("API Key（LLM_API_KEY）", "已设置" if info.get("llm_api_key_set") else "未设置（本地服务通常无需）"))
    rows += [
        ("Ollama 地址" + ("（嵌入模型）" if provider != "ollama" else ""), f"`{info.get('ollama_url', '')}`"),
        ("LLM 模型", f"`{info.get('llm_model', '')}`"),
        ("LLM 并发上限（OLLAMA_MAX_CONCURRENCY）", _fmt_concurrency(info.get("max_concurrency"))),
        ("Embedding 模型", f"`{info.get('embed_model', '')}`"),
        ("num_ctx", info.get("num_ctx", "")),
        ("思考模式", "开" if info.get("think") else "关"),
        ("自动确认（环境变量）",
         "开（只放行 low / medium）" if info.get("auto_confirm_env") else "关"),
        ("工作目录", f"`{info.get('cwd', '')}`"),
        ("允许读目录", _fmt_dir_list(info.get("read_allowed_dirs"), "READ_ALLOWED_DIRS")),
        ("允许写目录", _fmt_dir_list(info.get("write_allowed_dirs"), "WRITE_ALLOWED_DIRS")),
        ("数据目录", f"`{info.get('data_dir', '')}`"),
        ("索引目录", f"`{info.get('index_dir', '')}`"),
        ("向量库路径", f"`{info.get('vector_db_path', '')}`"),
        ("会话存储", f"`{info.get('session_storage', '')}`"),
        ("TOP_K", info.get("top_k", "")),
        ("文本分块 / 重叠", f"{info.get('chunk_size', '')} / {info.get('chunk_overlap', '')}"),
        ("代码分块", info.get("code_chunking", "") or "—"),
        ("相似度阈值", info.get("similarity_cutoff", "")),
        ("知识库相关性阈值", info.get("kb_relevance_threshold", "")),
        ("自校验（RAG_SELF_CHECK）", "开启" if info.get("self_check") else "关闭"),
        ("Agent 最大步数 / 超时", f"{info.get('max_iterations', '')} / {info.get('timeout', '')}s"),
    ]
    if "tesseract_path" in info or "tesseract_hint" in info:
        rows.append(("Tesseract（OCR）", _fmt_tesseract(info)))
    rows.append(("版本", info.get("app_version", "")))
    return format_kv_table(rows)


_TESSERACT_SOURCE_TEXT = {
    "env": "TESSERACT_PATH 指定",
    "path": "PATH 中找到",
    "candidate": "常见安装目录探测到",
}


def _fmt_tesseract(info: Dict[str, Any]) -> str:
    """Tesseract 探测结果（F10 P3-1）：``✅ `路径`（来源）`` / ``❌ 未安装 —— 安装方法见 …``。

    与 CLI ``/config`` 的 ``tesseract_row_text`` 同一语义；OCR 关闭或引擎非 tesseract 时附注当前设置。
    """
    path = info.get("tesseract_path")
    hint = info.get("tesseract_hint")
    engine = info.get("ocr_engine", "tesseract")
    enabled = info.get("ocr_enabled", True)
    suffix = ""
    if not (enabled and engine == "tesseract"):
        suffix = f"；当前 `OCR_ENGINE={engine}`" + ("" if enabled else "、`OCR_ENABLED=false`")
    if not path:
        return f"❌ 未安装 —— {hint or '安装方法见 docs/tutorials/02-installation.md#ocr'}{suffix}"
    source = _TESSERACT_SOURCE_TEXT.get(info.get("tesseract_source"), "已找到")
    text = f"✅ `{path}`（{source}）"
    if hint:
        text += f"；{hint}"
    return text + suffix


def _fmt_concurrency(value: Any) -> str:
    """并发上限展示（F10 P2-1-d）：None → 未知；0 → 不限制；其余 → ``N（多 Agent 并行时其余请求排队）``。"""
    if value is None or value == "":
        return "—"
    try:
        n = int(value)
    except (TypeError, ValueError):
        return str(value)
    if n <= 0:
        return "不限制"
    return f"{n}（多 Agent 并行时其余请求本地排队，排队时间不计入子任务超时）"


def format_stats_cards(stats: Dict[str, Any], file_count: Optional[int] = None) -> str:
    """把知识库统计渲染为指标卡片（HTML，供 ``gr.HTML`` 展示）。"""
    if "error" in stats:
        return f'<div class="cb-empty">❌ 获取统计失败：{stats["error"]}</div>'

    def card(k: str, v: Any, small: bool = False) -> str:
        cls = "v small" if small else "v"
        return f'<div class="cb-card"><div class="k">{k}</div><div class="{cls}" title="{v}">{v}</div></div>'

    cards = [card("文档片段", stats.get("total_documents", 0))]
    if file_count is not None:
        cards.append(card("已登记文件", file_count))
    cards.append(card("Embedding", stats.get("embed_model", "?"), small=True))
    code = str(stats.get("code_chunking", "") or "")
    code_label = f" / 代码 {stats.get('code_chunk_max_chars', '')}".rstrip() if code.startswith("enabled") else ""
    cards.append(card("分块 / 重叠", f"{stats.get('chunk_size', '?')} / {stats.get('chunk_overlap', '?')}{code_label}", small=True))
    cards.append(card("TOP_K", stats.get("top_k", "?")))
    html = f'<div class="cb-cards">{"".join(cards)}</div>'
    # F10 P2-1-b：块数超限等原因导致混合检索关闭时，卡片下方给出可见提示（此前静默降级）
    if stats.get("hybrid_disabled_reason"):
        html += f'<div class="cb-empty cb-empty-sm">⚠️ {_hybrid_disabled_text(stats)}</div>'
    return html


def _html_escape(text: Any) -> str:
    """HTML 属性 / 文本转义（卡片 title 等）。"""
    return (str("" if text is None else text)
            .replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;"))


def format_git_cards(overview: Dict[str, Any]) -> str:
    """Git 仪表盘顶部 4 张卡：当前分支 / 变更文件 / 最近提交时间 / 提交者数（HTML）。"""
    if not overview or not overview.get("is_repo"):
        err = overview.get("error") if overview else ""
        detail = f"<p>{_html_escape(err)}</p>" if err else "<p>在「系统 → 运行环境」切换到 Git 仓库目录后刷新。</p>"
        return f'<div class="cb-empty"><h3>当前目录不是 Git 仓库</h3>{detail}</div>'

    def card(k: str, v: Any, small: bool = False) -> str:
        cls = "v small" if small else "v"
        v = _html_escape(v)
        return f'<div class="cb-card"><div class="k">{k}</div><div class="{cls}" title="{v}">{v}</div></div>'

    last = str(overview.get("last_commit_at") or "")
    last_short = last[:16] if last else "—"
    cards = [
        card("当前分支", overview.get("branch") or "（分离 HEAD）", small=True),
        card("变更文件", len(overview.get("changed") or [])),
        card("最近提交", last_short, small=True),
        card("提交者", len(overview.get("authors") or [])),
    ]
    return f'<div class="cb-cards">{"".join(cards)}</div>'


GIT_CHANGES_HEADERS = ["状态", "路径"]
GIT_COMMITS_HEADERS = ["提交", "作者", "日期", "标题"]
GIT_AUTHORS_HEADERS = ["作者", "提交数"]


def git_changes_rows(overview: Dict[str, Any]) -> List[List[Any]]:
    return [[c.get("label") or c.get("status", ""), c.get("path", "")] for c in (overview or {}).get("changed") or []]


def git_commits_rows(overview: Dict[str, Any]) -> List[List[Any]]:
    return [[c.get("hash7", ""), c.get("author", ""), c.get("date", ""), c.get("subject", "")]
            for c in (overview or {}).get("commits") or []]


def git_authors_rows(overview: Dict[str, Any]) -> List[List[Any]]:
    return [[a.get("name", ""), a.get("commits", 0)] for a in (overview or {}).get("authors") or []]


def format_git_payload(overview: Dict[str, Any]) -> str:
    """把 Git 概览压成纯文本，供「用 AI 解读 / 发送到对话」。"""
    if not overview or not overview.get("is_repo"):
        return ""
    lines = [f"分支: {overview.get('branch') or '(detached)'}", f"最近提交: {overview.get('last_commit_at') or '—'}"]
    changed = overview.get("changed") or []
    lines.append(f"变更文件 ({len(changed)}):")
    lines += [f"  {c.get('label') or c.get('status', '')} {c.get('path', '')}" for c in changed[:50]]
    lines.append("最近提交:")
    lines += [f"  {c.get('hash7', '')} {c.get('date', '')} {c.get('author', '')}: {c.get('subject', '')}"
              for c in overview.get("commits") or []]
    lines.append("提交者: " + ", ".join(f"{a.get('name', '')}({a.get('commits', 0)})" for a in overview.get("authors") or []))
    return "\n".join(lines)


GIT_STAGED_HEADERS = ["状态", "路径"]


def git_staged_rows(preview: Dict[str, Any]) -> List[List[Any]]:
    return [[f.get("label") or f.get("status", ""), f.get("path", "")]
            for f in (preview or {}).get("staged_files") or []]


def format_git_commit_preview(preview: Dict[str, Any]) -> str:
    """暂存区预览卡片（HTML）：暂存文件数 / 新增行 / 删除行；无暂存时给 ``.cb-hint`` 提示。"""
    if not preview or not preview.get("is_repo"):
        err = (preview or {}).get("error")
        detail = f"<p>{_html_escape(err)}</p>" if err else ""
        return f'<div class="cb-empty"><h3>当前目录不是 Git 仓库</h3>{detail}</div>'
    if not preview.get("has_staged"):
        return ('<div class="cb-hint cb-hint-block">💡 暂存区为空：请先在终端 <code>git add</code> 要提交的文件，'
                '再点「AI 生成提交信息」。</div>')

    def card(k: str, v: Any) -> str:
        return f'<div class="cb-card"><div class="k">{k}</div><div class="v">{_html_escape(v)}</div></div>'

    cards = [
        card("暂存文件", preview.get("files_changed") or len(preview.get("staged_files") or [])),
        card("新增行", f"+{int(preview.get('insertions') or 0)}"),
        card("删除行", f"-{int(preview.get('deletions') or 0)}"),
    ]
    stat = _html_escape(preview.get("diff_stat") or "")
    stat_html = f'<pre class="cb-diff-stat">{stat}</pre>' if stat else ""
    return f'<div class="cb-cards">{"".join(cards)}</div>{stat_html}'


def format_db_status(current: Dict[str, Any]) -> str:
    """数据库当前连接状态芯片（HTML）。"""
    if not current or not current.get("connected"):
        return '<span class="cb-status-chip"><span class="dot off"></span>未连接 · 输入 SQLite 文件路径后点「连接」</span>'
    return (f'<span class="cb-status-chip"><span class="dot"></span>已连接 · '
            f'<code>{_html_escape(current.get("database", ""))}</code></span>')


DB_TABLES_HEADERS = ["表名"]
DB_SCHEMA_HEADERS = ["列", "类型", "约束"]


def db_tables_rows(data: Dict[str, Any]) -> List[List[Any]]:
    return [[t] for t in (data or {}).get("tables") or []]


def db_schema_rows(schema: Dict[str, Any]) -> List[List[Any]]:
    """列 / 类型 / 约束（PK · NOT NULL · DEFAULT x）；与 CLI ``/db-schema`` 共用共享层实现。"""
    from database_tools.results import schema_rows

    return schema_rows(schema)


def format_db_query_status(result: Dict[str, Any]) -> str:
    """查询结果状态行：行数 / 耗时 / 截断提示，或错误。"""
    if not result:
        return ""
    if result.get("error"):
        return f"❌ {result['error']}"
    n = int(result.get("row_count", 0) or 0)
    shown = len(result.get("rows") or [])
    took = f"{float(result.get('execution_time', 0) or 0):.3f}s"
    if result.get("truncated"):
        return f"✅ 共 {n} 行，仅显示前 {shown} 行 · {took}"
    return f"✅ 返回 {n} 行 · {took}"


def format_db_execute_status(result: Dict[str, Any]) -> str:
    if not result:
        return ""
    if result.get("error"):
        return f"❌ {result['error']}"
    return f"✅ 执行成功，影响 {int(result.get('affected_rows', 0) or 0)} 行 · {float(result.get('execution_time', 0) or 0):.3f}s"


def format_db_payload(result: Dict[str, Any], max_rows: int = 50) -> str:
    """SQL + 前 ``max_rows`` 行结果的纯文本，供「用 AI 解读 / 发送到对话」。"""
    if not result:
        return ""
    lines = [f"SQL: {result.get('sql', '')}"]
    if result.get("error"):
        lines.append(f"错误: {result['error']}")
        return "\n".join(lines)
    if "affected_rows" in result and "columns" not in result:
        lines.append(f"影响行数: {result.get('affected_rows', 0)}")
        return "\n".join(lines)
    cols = result.get("columns") or []
    rows = (result.get("rows") or [])[:max_rows]
    lines.append(f"共 {result.get('row_count', 0)} 行" + (f"（下面为前 {len(rows)} 行）" if result.get("row_count", 0) > len(rows) else ""))
    if cols:
        lines.append(" | ".join(map(str, cols)))
        lines += [" | ".join("" if v is None else str(v) for v in r) for r in rows]
    return "\n".join(lines)


SEND_TO_CHAT_MAX = 4000


def format_send_to_chat(tab: str, payload: str) -> str:
    """「发送到对话」填入输入框的模板（附录 A-6）；结果截 ``SEND_TO_CHAT_MAX`` 字。"""
    payload = (payload or "").strip()
    if not payload:
        return ""
    if len(payload) > SEND_TO_CHAT_MAX:
        payload = payload[:SEND_TO_CHAT_MAX] + "\n…（已截断）"
    return f"以下是工具页「{tab}」的结果，请基于它继续分析：\n```\n{payload}\n```\n我的问题："


# ---------- 工具页 P2：代码助手 / 符号表 / 质量卡片 ----------

SYMBOL_HEADERS = ["名称", "类型", "文件", "行号", "复杂度"]
QUALITY_ISSUE_HEADERS = ["严重度", "行", "描述"]
_SEVERITY_LABEL = {"critical": "危险", "error": "错误", "warning": "警告", "info": "提示"}


def symbol_rows(data: Dict[str, Any]) -> List[List[Any]]:
    """符号搜索结果 → 表格行（名称 / 类型 / 文件 / 行号 / 复杂度）。"""
    return [[s.get("name", ""), s.get("kind", ""), s.get("file", ""), s.get("line", 0), s.get("complexity", "")]
            for s in (data or {}).get("symbols") or []]


def format_symbols_status(data: Dict[str, Any]) -> str:
    if not data:
        return ""
    if data.get("error"):
        return f"❌ {data['error']}"
    n = len(data.get("symbols") or [])
    if n == 0:
        return "💡 未找到匹配的函数 / 类"
    return f"✅ 找到 {n} 个符号" + ("（已截断）" if data.get("truncated") else "")


def format_symbols_payload(pattern: str, data: Dict[str, Any]) -> str:
    """符号表的纯文本（供「用 AI 解读 / 发送到对话」）。"""
    rows = symbol_rows(data)
    if not rows:
        return ""
    lines = [f"符号搜索「{pattern}」共 {len(rows)} 条："]
    lines += [f"  {r[1]} {r[0]}  {r[2]}:{r[3]}  复杂度 {r[4]}" for r in rows[:100]]
    return "\n".join(lines)


def format_quality_cards(report: Dict[str, Any]) -> str:
    """质量检查卡片：评分 / 问题数 / 文件数 / 严重度分布（HTML）。"""
    if not report:
        return ""
    if report.get("error"):
        return f'<div class="cb-empty">❌ {_html_escape(report["error"])}</div>'

    def card(k: str, v: Any, small: bool = False) -> str:
        cls = "v small" if small else "v"
        v = _html_escape(v)
        return f'<div class="cb-card"><div class="k">{k}</div><div class="{cls}" title="{v}">{v}</div></div>'

    sev = report.get("severity") or {}
    dist = " · ".join(f"{_SEVERITY_LABEL.get(k, k)} {int(sev.get(k, 0) or 0)}"
                      for k in ("critical", "error", "warning", "info"))
    cards = [
        card("评分", f"{float(report.get('score', 0) or 0):.1f} / 100"),
        card("问题数", int(report.get("total_issues", 0) or 0)),
        card("文件数", int(report.get("files", 0) or 0)),
        card("严重度分布", dist, small=True),
    ]
    return f'<div class="cb-cards">{"".join(cards)}</div>'


def quality_issue_rows(report: Dict[str, Any]) -> List[List[Any]]:
    """问题表：严重度 / 行（多文件时为 ``文件:行``）/ 描述。"""
    issues = (report or {}).get("issues") or []
    multi = int((report or {}).get("files", 0) or 0) > 1
    rows = []
    for i in issues:
        loc = f"{i.get('file', '')}:{i.get('line', 0)}" if multi else str(i.get("line", 0))
        rows.append([_SEVERITY_LABEL.get(i.get("severity", ""), i.get("severity", "")), loc, i.get("message", "")])
    return rows


def format_quality_payload(report: Dict[str, Any]) -> str:
    if not report or report.get("error"):
        return f"质量检查失败: {report.get('error')}" if report and report.get("error") else ""
    sev = report.get("severity") or {}
    lines = [f"质量检查 {report.get('path', '')}：评分 {float(report.get('score', 0) or 0):.1f}/100，"
             f"{report.get('files', 0)} 个文件，{report.get('total_issues', 0)} 个问题"
             f"（危险 {sev.get('critical', 0)} / 错误 {sev.get('error', 0)} / 警告 {sev.get('warning', 0)} / 提示 {sev.get('info', 0)}）"]
    lines += [f"  [{r[0]}] {r[1]}: {r[2]}" for r in quality_issue_rows(report)[:100]]
    return "\n".join(lines)


# ---------- 工具页 P2：工作区文件浏览 ----------

DIR_HEADERS = ["", "名称", "大小", "修改时间"]
SEARCH_HEADERS = ["文件", "行", "内容"]
_LANGUAGE_BY_SUFFIX = {
    ".py": "python", ".js": "javascript", ".mjs": "javascript", ".ts": "typescript", ".tsx": "typescript",
    ".jsx": "javascript", ".json": "json", ".md": "markdown", ".html": "html", ".htm": "html", ".css": "css",
    ".sh": "shell", ".bash": "shell", ".zsh": "shell", ".yaml": "yaml", ".yml": "yaml", ".sql": "sql",
    ".c": "c", ".h": "c", ".cpp": "cpp", ".hpp": "cpp", ".cc": "cpp", ".r": "r", ".jinja": "jinja2",
}
_LANGUAGE_BY_NAME = {"dockerfile": "dockerfile", "makefile": "shell"}


def guess_code_language(name: str) -> Optional[str]:
    """按文件名后缀推断 ``gr.Code`` 的 ``language``（未知返回 None，即纯文本）。"""
    import os

    base = os.path.basename((name or "").strip())
    if not base:
        return None
    if base.lower() in _LANGUAGE_BY_NAME:
        return _LANGUAGE_BY_NAME[base.lower()]
    suffix = os.path.splitext(base)[1] or (base if base.startswith(".") else "")  # 允许直接传 ".py"
    return _LANGUAGE_BY_SUFFIX.get(suffix.lower())


def format_size(size: Any) -> str:
    """字节数 → ``1.2 KB`` 样式（目录 / 0 显示 ``—``）。"""
    try:
        n = float(size or 0)
    except (TypeError, ValueError):
        return "—"
    if n <= 0:
        return "—"
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{int(n)} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return "—"  # pragma: no cover - 循环内必返回


def dir_rows(listing: Dict[str, Any]) -> List[List[Any]]:
    """目录列表 → 表格行：``📁/📄`` / 名称 / 大小 / 修改时间。"""
    rows = []
    for e in (listing or {}).get("entries") or []:
        is_dir = e.get("kind") == "dir"
        rows.append(["📁" if is_dir else "📄", e.get("name", ""), "—" if is_dir else format_size(e.get("size")),
                     e.get("mtime", "")])
    return rows


def abbreviate_home(path: str) -> str:
    """把用户主目录前缀缩写为 ``~``（仅用于显示；服务层照常接受 ``~`` 路径）。"""
    import os

    path = str(path or "")
    home = os.path.expanduser("~").rstrip(os.sep)
    if home and (path == home or path.startswith(home + os.sep)):
        return "~" + path[len(home):]
    return path


def format_dir_breadcrumb(listing: Dict[str, Any]) -> str:
    """面包屑：``📂 `~/path` · N 项``；出错时 ❌。"""
    if not listing:
        return ""
    if listing.get("error"):
        return f"❌ {listing['error']}"
    n = len(listing.get("entries") or [])
    extra = "（已截断）" if listing.get("truncated") else ""
    return f"📂 `{abbreviate_home(listing.get('path', ''))}` · {n} 项{extra}"


def join_entry(cur_path: str, kind_cell: str, name: str) -> Tuple[str, bool]:
    """把表格选中行还原为 ``(完整路径, 是否目录)``；名称为空返回 ``("", False)``。"""
    import os

    name = (name or "").strip()
    if not name:
        return "", False
    return os.path.join((cur_path or ".").strip() or ".", name), (kind_cell or "").strip() == "📁"


def search_rows(results: List[Dict[str, Any]]) -> List[List[Any]]:
    """搜索结果行：相对路径（无则绝对路径）/ 行 / 内容。"""
    return [[r.get("rel") or r.get("file", ""), r.get("line", 0), r.get("text", "")] for r in results or []]


def format_file_preview_status(preview: Dict[str, Any]) -> str:
    """预览状态行：``📄 `path` · 第 1/3 页 · 行 1-200 / 512``。"""
    if not preview:
        return ""
    if preview.get("error"):
        return f"❌ {preview['error']}"
    total = int(preview.get("total_lines", 0) or 0)
    if total == 0:
        return f"📄 `{preview.get('path', '')}` · 空文件"
    return (f"📄 `{preview.get('path', '')}` · 第 {int(preview.get('page', 0)) + 1}/{preview.get('pages', 1)} 页 · "
            f"行 {int(preview.get('start', 0)) + 1}-{preview.get('end', 0)} / {total}")


def format_file_payload(preview: Dict[str, Any]) -> str:
    if not preview or preview.get("error") or not preview.get("content"):
        return ""
    return f"文件: {preview.get('path', '')}（行 {int(preview.get('start', 0)) + 1}-{preview.get('end', 0)}）\n{preview.get('content', '')}"


def format_graph_result(result: Dict[str, Any]) -> str:
    """把知识图谱查询结果渲染为 Markdown 文本。"""
    entities = result.get("entities", [])
    relations = result.get("relations", [])
    explanation = result.get("explanation", "")
    if not entities and not relations:
        return explanation or "_未找到相关实体_"
    lines = []
    if explanation:
        lines.append(explanation)
        lines.append("")
    if entities:
        lines.append("### 实体")
        for e in entities:
            lines.append(f"- **{e.get('text', '?')}** ({e.get('entity_type', '?')})")
        lines.append("")
    if relations:
        lines.append("### 关系")
        for r in relations:
            src = r.get("source", {}).get("text", "?")
            tgt = r.get("target", {}).get("text", "?")
            rel = r.get("relation_type", "?")
            lines.append(f"- {src} --[{rel}]--> {tgt}")
    return "\n".join(lines).rstrip()


def format_file_delete_prompt(preview: Dict[str, Any]) -> str:
    """删除文件二步确认的提示文案（片段数 / 元数据 / 图谱影响，强调不删磁盘文件）。"""
    if not preview:
        return ""
    if preview.get("error"):
        return f"❌ {preview['error']}"
    name = preview.get("file_name") or preview.get("file_path") or "?"
    if not preview.get("exists", True):
        return f"❌ 文件不在知识库中：`{name}`"
    if preview.get("graph_shared_basename"):
        graph = "图谱保留（另有同名文件）"
    elif preview.get("graph_nodes") or preview.get("graph_edges"):
        graph = f"移除 {preview.get('graph_nodes', 0)} 个节点 / {preview.get('graph_edges', 0)} 条边的来源"
    else:
        graph = "无变更"
    return (
        f"将删除 `{name}` 的 **{preview.get('chunk_count', 0)} 个片段**与元数据，"
        f"不删除磁盘文件；图谱：{graph}。继续？"
    )


def format_file_action_bar(path: str) -> str:
    """文件操作条标题：``📄 文件名``（附完整路径 tooltip）。"""
    path = (path or "").strip()
    if not path:
        return ""
    name = path.rsplit("/", 1)[-1] if "/" in path else path
    return f'<div class="cb-action-title" title="{path}">📄 <b>{name}</b></div>'


_SNAPSHOT_TRIGGER_LABEL = {
    "manual": "手动", "document_added": "自动（入库）", "batch_added": "自动（批量入库）",
}


def format_snapshot_info(info: Dict[str, Any]) -> str:
    """快照详情（键值表 + 缺失文件提示）；文档清单另以表格展示。"""
    if not info:
        return ""
    if info.get("error"):
        return f"_{info['error']}_"
    model = info.get("model_config") or {}
    rows = [
        ("快照 ID", f"`{info.get('snapshot_id', '')}`"),
        ("时间", str(info.get("timestamp", ""))[:19].replace("T", " ")),
        ("触发", _SNAPSHOT_TRIGGER_LABEL.get(info.get("trigger", ""), info.get("trigger", "") or "—")),
        ("文档数 / 片段数", f"{info.get('document_count', 0)} / {info.get('total_chunks', 0)}"),
        ("LLM / Embedding", f"`{model.get('llm_model', '?')}` / `{model.get('embed_model', '?')}`"),
    ]
    out = format_kv_table(rows)
    missing = int(info.get("missing_count", 0) or 0)
    if missing:
        out += f"\n\n⚠️ **{missing} 个文件已不在磁盘上**，恢复时将跳过（下表红色标出）。"
    return out


def snapshot_doc_rows(info: Dict[str, Any]) -> List[List[Any]]:
    """快照文档清单表格行：``[状态, 文件, 类型, 片段, 路径]``（不存在的文件标红）。"""
    rows = []
    for d in (info or {}).get("documents") or []:
        exists = bool(d.get("exists", True))
        status = "✅ 存在" if exists else '<span style="color:#dc2626;font-weight:700">❌ 缺失</span>'
        name = d.get("file_name") or ""
        if not exists:
            name = f'<span style="color:#dc2626">{name}</span>'
        rows.append([status, name, d.get("file_type", "") or "—", d.get("chunk_count", 0), d.get("file_path", "")])
    return rows


def format_restore_result(result: Dict[str, Any]) -> str:
    """把 ``restore_apply`` 的结果渲染为 Markdown。"""
    if not result:
        return ""
    if not result.get("ok"):
        return f"❌ {result.get('error', '恢复失败')}"
    mode = "替换" if result.get("mode") == "replace" else "追加"
    lines = [
        f"✅ 快照 `{result.get('snapshot_id', '')}` 已恢复（{mode}）：成功 **{result.get('restored', 0)}**，"
        f"跳过 {result.get('skipped', 0)}，失败 {result.get('failed', 0)}，共 {result.get('chunks', 0)} 个片段"
    ]
    missing = result.get("missing") or []
    if missing:
        lines.append("")
        lines.append(f"⚠️ 以下 {len(missing)} 个文件已不存在，已跳过：")
        lines.extend(f"- `{m}`" for m in missing[:20])
        if len(missing) > 20:
            lines.append(f"- … 共 {len(missing)} 个")
    errors = result.get("errors") or []
    if errors:
        lines.append("")
        lines.append("❌ 失败明细：")
        lines.extend(f"- {e}" for e in errors[:20])
    return "\n".join(lines)


def format_prune_preview(pending: List[Dict[str, Any]], keep: int) -> str:
    """批量清理自动快照的确认预览。"""
    if pending and str(pending[0].get("snapshot_id", "")).startswith("[错误]"):
        return f"❌ {pending[0]['snapshot_id']}"
    if not pending:
        return f"✅ 自动快照不超过 {keep} 个，无需清理"
    lines = [f"🧹 将删除 **{len(pending)}** 个自动快照（保留最近 {keep} 个，手动快照不受影响）：", ""]
    lines.extend(
        f"- `{p.get('snapshot_id')}` {str(p.get('timestamp', ''))[:19].replace('T', ' ')}"
        for p in pending[:15]
    )
    if len(pending) > 15:
        lines.append(f"- … 共 {len(pending)} 个")
    return "\n".join(lines)


# ==================== 知识图谱可视化（Plotly，可测试）====================

# 实体类型 → 颜色（与 EntityType 对齐；未知类型回落到 other）
GRAPH_TYPE_COLORS: Dict[str, str] = {
    "person": "#f97316", "organization": "#8b5cf6", "location": "#10b981",
    "concept": "#3b82f6", "technology": "#06b6d4", "tool": "#eab308",
    "language": "#ec4899", "framework": "#14b8a6", "other": "#9ca3af",
}
# 边 / 边标签颜色：slate-500/600，浅色与深色背景均可辨（此前的浅灰半透明在浅色下近似白色）
GRAPH_EDGE_COLOR = "rgba(100,116,139,0.78)"
GRAPH_EDGE_LABEL_COLOR = "#64748b"


def _node_size(degree: int, dim: int) -> float:
    """按度数定节点大小（平方根缩放，避免高频节点过大）。"""
    base = 6.0 if dim == 3 else 9.0
    return base + min(float(degree or 0), 60.0) ** 0.5 * (2.2 if dim == 3 else 3.0)


def _hover_docs(docs: List[str], limit: int = 5) -> str:
    docs = [str(d) for d in (docs or []) if d]
    if not docs:
        return "—"
    shown = ", ".join(docs[:limit])
    return shown + (f" 等 {len(docs)} 个" if len(docs) > limit else "")


def build_graph_figure(
    nodes: List[Dict[str, Any]],
    edges: List[Dict[str, Any]],
    dim: int = 3,
    positions: Optional[Dict[str, Tuple[float, ...]]] = None,
    edge_labels: bool = False,
    title: str = "",
):
    """把子图（节点/边列表）渲染为 Plotly Figure（2D 或 3D）。

    - 节点按 ``entity_type`` 着色、按 ``degree`` 定大小，悬停显示名称 / 类型 / 来源文档；
    - 边悬停显示 ``relation_type``（在边中点放透明标记承载 hover）；2D 可选显示边标签；
    - ``positions`` 缺失时用 networkx spring 布局现场计算；
    - 无节点时返回带"暂无数据"提示的空图。

    依赖 plotly（惰性导入，未安装时抛 ImportError 由调用方提示）。
    """
    import plotly.graph_objects as go

    dim = 3 if int(dim or 3) >= 3 else 2
    fig = go.Figure()
    layout_common = dict(
        title=dict(text=title, x=0.01, font=dict(size=14)) if title else None,
        margin=dict(l=0, r=0, t=30 if title else 8, b=0),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#6b7280"),
        legend=dict(orientation="h", yanchor="bottom", y=1.0, xanchor="right", x=1.0,
                    bgcolor="rgba(0,0,0,0)", itemsizing="constant"),
        hoverlabel=dict(font_size=12),
        height=560,
    )

    if not nodes:
        fig.update_layout(
            **layout_common,
            annotations=[dict(
                text="暂无图谱数据：请先入库文档或在下方「构建」中手动构建，或放宽筛选条件",
                showarrow=False, xref="paper", yref="paper", x=0.5, y=0.5, font=dict(size=14),
            )],
            xaxis=dict(visible=False), yaxis=dict(visible=False),
        )
        return fig

    ids = [str(n["id"]) for n in nodes]
    if not positions or any(i not in positions for i in ids):
        import networkx as nx

        g = nx.Graph()
        g.add_nodes_from(ids)
        g.add_edges_from((str(e["source"]), str(e["target"])) for e in edges
                         if str(e.get("source")) in g and str(e.get("target")) in g)
        positions = {str(k): tuple(float(x) for x in v) for k, v in nx.spring_layout(g, dim=dim, seed=42).items()}

    def coord(node_id: str, axis: int) -> float:
        pos = positions.get(node_id) or (0.0, 0.0, 0.0)
        return float(pos[axis]) if axis < len(pos) else 0.0

    # ---- 边：一条 trace 画全部线段（用 None 断开）+ 中点透明标记承载 hover ----
    ex: List[Optional[float]] = []
    ey: List[Optional[float]] = []
    ez: List[Optional[float]] = []
    mx: List[float] = []
    my: List[float] = []
    mz: List[float] = []
    mtext: List[str] = []
    mlabel: List[str] = []
    id_set = set(ids)
    for e in edges:
        s, t = str(e.get("source")), str(e.get("target"))
        if s not in id_set or t not in id_set:
            continue
        xs, ys = coord(s, 0), coord(s, 1)
        xt, yt = coord(t, 0), coord(t, 1)
        ex += [xs, xt, None]
        ey += [ys, yt, None]
        mx.append((xs + xt) / 2)
        my.append((ys + yt) / 2)
        if dim == 3:
            zs, zt = coord(s, 2), coord(t, 2)
            ez += [zs, zt, None]
            mz.append((zs + zt) / 2)
        rel = str(e.get("relation_type", "related"))
        s_text = next((n.get("text", s) for n in nodes if str(n["id"]) == s), s)
        t_text = next((n.get("text", t) for n in nodes if str(n["id"]) == t), t)
        mtext.append(f"<b>{s_text}</b> —[{rel}]→ <b>{t_text}</b><br>置信度 {float(e.get('confidence', 0) or 0):.2f}"
                     f"<br>来源: {_hover_docs(e.get('documents') or [])}")
        mlabel.append(rel)

    # 边色取 slate-500 中灰：浅色背景上足够深、深色背景上足够亮，两种模式都可辨；
    # 3D 场景里 WebGL 线条视觉上更细，线宽给得更大一些。
    edge_line = dict(color=GRAPH_EDGE_COLOR, width=2.4 if dim == 3 else 1.6)
    if ex:
        if dim == 3:
            fig.add_trace(go.Scatter3d(x=ex, y=ey, z=ez, mode="lines", line=edge_line,
                                       hoverinfo="none", showlegend=False, name="边"))
            fig.add_trace(go.Scatter3d(
                x=mx, y=my, z=mz, mode="markers", marker=dict(size=2, color="rgba(148,163,184,0.01)"),
                hovertext=mtext, hoverinfo="text", showlegend=False, name="关系",
            ))
        else:
            fig.add_trace(go.Scatter(x=ex, y=ey, mode="lines", line=edge_line,
                                     hoverinfo="none", showlegend=False, name="边"))
            fig.add_trace(go.Scatter(
                x=mx, y=my, mode="markers+text" if edge_labels else "markers",
                marker=dict(size=4, color="rgba(148,163,184,0.01)"),
                text=mlabel if edge_labels else None, textposition="top center",
                textfont=dict(size=9, color=GRAPH_EDGE_LABEL_COLOR),
                hovertext=mtext, hoverinfo="text", showlegend=False, name="关系",
            ))

    # ---- 节点：按类型分 trace（便于图例显隐）----
    by_type: Dict[str, List[Dict[str, Any]]] = {}
    for n in nodes:
        by_type.setdefault(str(n.get("entity_type", "other")).lower(), []).append(n)
    for etype in sorted(by_type, key=lambda t: -len(by_type[t])):
        group = by_type[etype]
        color = GRAPH_TYPE_COLORS.get(etype, GRAPH_TYPE_COLORS["other"])
        xs = [coord(str(n["id"]), 0) for n in group]
        ys = [coord(str(n["id"]), 1) for n in group]
        sizes = [_node_size(int(n.get("degree", 0) or 0), dim) for n in group]
        hover = [
            f"<b>{n.get('text', n['id'])}</b><br>类型: {etype}<br>度数: {int(n.get('degree', 0) or 0)}"
            f"<br>置信度: {float(n.get('confidence', 0) or 0):.2f}<br>来源: {_hover_docs(n.get('documents') or [])}"
            for n in group
        ]
        labels = [str(n.get("text", n["id"])) for n in group]
        marker = dict(size=sizes, color=color, opacity=0.92,
                      line=dict(width=0.6, color="rgba(255,255,255,0.7)"))
        name = f"{etype}（{len(group)}）"
        if dim == 3:
            zs = [coord(str(n["id"]), 2) for n in group]
            fig.add_trace(go.Scatter3d(
                x=xs, y=ys, z=zs, mode="markers+text", marker=marker, text=labels,
                textposition="top center", textfont=dict(size=9),
                hovertext=hover, hoverinfo="text", name=name,
            ))
        else:
            fig.add_trace(go.Scatter(
                x=xs, y=ys, mode="markers+text", marker=marker, text=labels,
                textposition="top center", textfont=dict(size=10),
                hovertext=hover, hoverinfo="text", name=name,
            ))

    axis_off = dict(showgrid=False, zeroline=False, showticklabels=False, visible=False)
    if dim == 3:
        fig.update_layout(
            **layout_common,
            scene=dict(xaxis=dict(**axis_off, title=""), yaxis=dict(**axis_off, title=""),
                       zaxis=dict(**axis_off, title=""), bgcolor="rgba(0,0,0,0)",
                       camera=dict(eye=dict(x=1.4, y=1.4, z=1.0))),
        )
    else:
        fig.update_layout(**layout_common, xaxis=axis_off, yaxis=axis_off)
    return fig


def format_graph_view_stats(view: Dict[str, Any]) -> str:
    """当前视图统计：显示节点/边数（相对总量）、类型分布、截断提示。"""
    if not view:
        return ""
    if view.get("error"):
        return f"❌ 图谱不可用：{view['error']}"
    nodes = view.get("nodes") or []
    edges = view.get("edges") or []
    total_n = int(view.get("total_nodes", 0) or 0)
    total_e = int(view.get("total_edges", 0) or 0)
    if not total_n:
        return "_图谱为空：入库文档后会自动派生，也可在下方「构建」手动喂入文本。_"
    types: Dict[str, int] = {}
    for n in nodes:
        t = str(n.get("entity_type", "other"))
        types[t] = types.get(t, 0) + 1
    dist = " · ".join(f"{t} {c}" for t, c in sorted(types.items(), key=lambda kv: -kv[1]))
    line = (
        f"当前视图：**{len(nodes)}** / {total_n} 节点 · **{len(edges)}** / {total_e} 边"
        + (f" · {'3D' if int(view.get('dim', 3) or 3) >= 3 else '2D'}")
    )
    if dist:
        line += f"\n\n类型分布：{dist}"
    if view.get("truncated"):
        line += "\n\n_已按度数截取前 N 个节点，可调大「最多节点数」或用聚焦实体缩小范围。_"
    if view.get("focus"):
        line += f"\n\n聚焦：`{view['focus']}`（{view.get('hops', 1)} 跳）"
    return line


def format_graph_summary_cards(summary: Dict[str, Any]) -> str:
    """图谱概览指标卡片（HTML）：节点 / 边 / 连通分量 / 平均度 / 类型数。"""
    if not summary.get("is_available", True) and summary.get("error"):
        return f'<div class="cb-empty">❌ 知识图谱不可用：{summary["error"]}</div>'
    stats = summary.get("statistics") or {}

    def card(k: str, v: Any, small: bool = False) -> str:
        cls = "v small" if small else "v"
        return f'<div class="cb-card"><div class="k">{k}</div><div class="{cls}" title="{v}">{v}</div></div>'

    avg = stats.get("average_degree", 0) or 0
    density = stats.get("density", 0) or 0
    cards = [
        card("节点", stats.get("total_nodes", 0)),
        card("边", stats.get("total_edges", 0)),
        card("实体类型", len(stats.get("entity_types") or {})),
        card("关系类型", len(stats.get("relation_types") or {})),
        card("连通分量", stats.get("connected_components", 0)),
        card("平均度 / 密度", f"{float(avg):.2f} / {float(density):.4f}", small=True),
    ]
    return f'<div class="cb-cards">{"".join(cards)}</div>'
