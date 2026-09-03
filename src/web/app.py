"""Gradio 界面组装（薄 UI 层）。

本模块只负责组件布局与事件绑定，全部业务逻辑委托给 ``services.WebService``。
纯格式化辅助函数（``format_*``）与 UI 处理器工厂（``build_handlers``）不依赖
gradio，可独立做单元测试；真正调用 gradio 的 ``build_app`` / ``launch`` 部分标注
``pragma: no cover``（UI 装配不做单元测试，通过手动/集成验证）。
"""
from __future__ import annotations

import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from .services import WebService, get_web_service

try:  # 上下文状态/提示的纯格式化函数（核心层提供，前端只接线）
    from conversation_context import format_context_status, format_suggest_hint, format_tokens
except ImportError:  # pragma: no cover - 以 src.* 方式导入时的兜底
    from src.conversation_context import (  # type: ignore
        format_context_status, format_suggest_hint, format_tokens,
    )


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

def format_sources(sources: List[Dict[str, Any]]) -> str:
    """把 sources 列表渲染为 Markdown 文本。"""
    if not sources:
        return "_无引用来源_"
    lines = ["### 引用来源", ""]
    for i, src in enumerate(sources, 1):
        score = src.get("score")
        score_str = f"（相似度 {score:.3f}）" if isinstance(score, (int, float)) else ""
        file_name = src.get("file", "未知")
        content = (src.get("content") or "").strip()
        lines.append(f"**{i}. {file_name}** {score_str}")
        if content:
            lines.append(f"> {content}")
        lines.append("")
    return "\n".join(lines).rstrip()


def format_web_sources(sources: List[Dict[str, Any]]) -> str:
    """把网络来源列表渲染为 Markdown 文本（与知识库来源明确区分）。"""
    if not sources:
        return ""
    lines = ["### 🌐 网络来源", ""]
    for i, src in enumerate(sources, 1):
        title = src.get("title", "") or src.get("url", "")
        url = src.get("url", "")
        if url:
            lines.append(f"{i}. [{title}]({url})")
        else:
            lines.append(f"{i}. {title}")
    return "\n".join(lines)


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
    """组合 RAG 回答的附加信息区：知识库来源 + 网络来源。"""
    parts = []
    kb = format_sources(result.get("sources", []))
    if kb and kb != "_无引用来源_":
        parts.append(kb)
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
        f"- 检索数量 TOP_K: {stats.get('top_k', '?')}"
    )


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
    """把多 Agent 协作结果渲染为 Markdown 文本。"""
    if not result.get("success"):
        err = result.get("error", "")
        summary = result.get("summary", "协作失败")
        return f"**❌ {summary}**\n\n{err}".strip()

    lines = [f"**✅ {result.get('summary', '协作完成')}**", ""]
    stats = (
        f"成功 {result.get('successful_results', 0)} / "
        f"共 {result.get('total_results', 0)}"
    )
    lines.append(stats)
    lines.append("")
    for r in result.get("results", []):
        status = "✅" if r.get("success") else "❌"
        agent_id = r.get("agent_id", "?")
        output = (r.get("output") or "").strip()
        lines.append(f"{status} **{agent_id}**")
        if output:
            lines.append(f"> {output}")
        lines.append("")
    return "\n".join(lines).rstrip()


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
        preview = summary if len(summary) <= 120 else summary[:120] + "…"
        line += f"\n\n> 📝 摘要：{preview}"
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
        elif phase == "final":
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
    ]
    tags = info.get("tags") or []
    if tags:
        rows.append(("标签", ", ".join(map(str, tags))))
    return format_kv_table(rows)


def format_env_info(info: Dict[str, Any]) -> str:
    """运行环境概览（对齐 CLI 横幅 + ``/model`` 附加字段）。"""
    if not info:
        return ""
    if info.get("error"):
        return f"_读取配置失败：{info['error']}_"
    rows = [
        ("Ollama 地址", f"`{info.get('ollama_url', '')}`"),
        ("LLM 模型", f"`{info.get('llm_model', '')}`"),
        ("Embedding 模型", f"`{info.get('embed_model', '')}`"),
        ("num_ctx", info.get("num_ctx", "")),
        ("思考模式", "开" if info.get("think") else "关"),
        ("自动确认（环境变量）", "开" if info.get("auto_confirm_env") else "关"),
        ("工作目录", f"`{info.get('cwd', '')}`"),
        ("数据目录", f"`{info.get('data_dir', '')}`"),
        ("索引目录", f"`{info.get('index_dir', '')}`"),
        ("向量库路径", f"`{info.get('vector_db_path', '')}`"),
        ("会话存储", f"`{info.get('session_storage', '')}`"),
        ("TOP_K", info.get("top_k", "")),
        ("分块大小 / 重叠", f"{info.get('chunk_size', '')} / {info.get('chunk_overlap', '')}"),
        ("相似度阈值", info.get("similarity_cutoff", "")),
        ("知识库相关性阈值", info.get("kb_relevance_threshold", "")),
        ("Agent 最大步数 / 超时", f"{info.get('max_iterations', '')} / {info.get('timeout', '')}s"),
        ("版本", info.get("app_version", "")),
    ]
    return format_kv_table(rows)


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
    cards.append(card("分块 / 重叠", f"{stats.get('chunk_size', '?')} / {stats.get('chunk_overlap', '?')}", small=True))
    cards.append(card("TOP_K", stats.get("top_k", "?")))
    return f'<div class="cb-cards">{"".join(cards)}</div>'


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


# ==================== UI 处理器工厂（可测试）====================

def build_handlers(service: WebService) -> Dict[str, Callable]:
    """构造绑定到 service 的 UI 处理器集合。

    处理器返回值均为已格式化的字符串/数据，供 Gradio 组件直接展示。
    这些处理器不依赖 gradio，可独立单元测试。
    """

    def on_chat(
        message: str,
        mode: str,
        enable_web: bool = True,
        auto_confirm: bool = False,
    ) -> Tuple[str, str]:
        """统一对话入口，按模式分发。返回 (回答, 附加信息 Markdown)。

        Args:
            enable_web: RAG 模式下是否启用 LLM 驱动的网络搜索增强（与 CLI 对齐）。
            auto_confirm: 单 Agent 模式下是否自动确认危险命令（等价 CLI ``--yes``）。
        """
        message = (message or "").strip()
        if not message:
            return "", "_请输入内容_"

        if mode == "多 Agent 协作":
            result = service.multi_agent_run(message)
            return "", format_multi_agent_result(result)

        if mode == "单 Agent":
            answer = ""
            steps: List[str] = []
            # 危险命令确认：勾选"自动确认"时全部放行（等价 CLI --yes），
            # 否则默认拒绝以保证安全（用户可勾选后重试）。
            confirm_handler = (lambda evt: True) if auto_confirm else None
            for evt in service.agent_chat_stream(message, confirm_handler=confirm_handler):
                if evt.kind == "step":
                    steps.append(f"- {evt.message}")
                elif evt.kind == "answer":
                    answer = evt.message
                elif evt.kind == "error":
                    return "", f"[错误] {evt.message}"
            side = "### 执行过程\n" + "\n".join(steps) if steps else ""
            return answer, side

        # 默认 RAG 模式（与 CLI /ask 编排一致：可选网络搜索、双区综合、元查询直答）
        result = service.rag_query(message, enable_web_search=enable_web)
        # 元查询：直接展示知识库概览
        if result.get("kind") == "meta":
            return format_meta_overview(result.get("meta") or {}), ""
        return result["answer"], format_rag_side(result)

    def _startup_hint() -> Tuple[str, str]:
        """根据当前模型状态生成 (首条活动文案, 常驻提示)。

        首次提问时模型尚未驻留内存，Ollama 需要先加载（4B 量化模型通常 10-30 秒）；
        思考模式开启时每次推理明显更慢。把这两点显式告诉用户，避免误判卡死。
        """
        try:
            info = service.current_model()
        except Exception:  # noqa: BLE001
            info = None
        if not isinstance(info, dict):
            return "准备中...", ""
        activity = "准备中..."
        if not info.get("loaded") and not info.get("error"):
            activity = f"📥 首次加载模型 `{info.get('model', '?')}`（通常需 10-30 秒）..."
        hint = "🧠 思考模式已开（响应较慢）" if info.get("think") else ""
        return activity, hint

    def _load_history(session_id: str) -> List[Dict[str, str]]:
        try:
            history = service.chat_history(session_id or None)
        except Exception:  # noqa: BLE001
            history = []
        return list(history) if isinstance(history, list) else []

    def _context_status(session_id: str) -> str:
        try:
            return format_context_metrics(service.context_metrics(session_id or None))
        except Exception:  # noqa: BLE001
            return ""

    def on_chat_stream(
        message: str,
        mode: str,
        enable_web: bool = True,
        auto_confirm: bool = False,
        session_id: str = "",
        collab_mode: str = "",
    ):
        """流式对话入口（供 Gradio 使用）。

        yield 六元组 ``(history, status_md, process_md, sources_md, hint_md, confirm_md)``：

        - ``history``：Chatbot（messages 格式）的完整多轮消息列表——会话内既有
          历史 + 本轮用户消息，完成后追加助手回答；
        - ``status_md``：一行状态，始终显示"当前在做什么 + 已用时"，完成/出错/
          停止时换成对应结论，完成后追加 ``上下文 3.2K / 4.8K · 已压缩 N 次``；
        - ``process_md``：按阶段累积的处理过程列表（心跳与计数类事件原地刷新，
          不刷屏；含"结合上下文理解问题""压缩历史上下文"等上下文事件）；单
          Agent 完成后追加执行摘要（对齐 CLI ``/summary``）；
        - ``sources_md``：完成后的引用来源 / 多 Agent 结果明细；
        - ``hint_md``：健康度建议（如"对话较长，建议新建会话"），空串表示无提示；
        - ``confirm_md``：单 Agent 遇到危险操作时的审批卡片文案（非空时 UI 显示
          「允许 / 拒绝」按钮），用户决定后或任务继续推进时回到空串。

        三种模式（RAG / 单 Agent / 多 Agent）统一走服务层带心跳与取消的事件流，
        并绑定到 ``session_id``（每个浏览器标签页自己的会话）。多 Agent 可指定
        ``collab_mode``（hierarchy/parallel/sequential/competitive，空为自动）。
        """
        message = (message or "").strip()
        session_id = (session_id or "").strip()
        history = _load_history(session_id)
        if not message:
            yield history, "_请输入内容_", "", "", "", ""
            return

        if service.is_running() is True:
            yield history, "⚠️ 已有任务在运行，请先等待完成或点击「停止」", "", "", "", ""
            return

        activity, hint = _startup_hint()
        tracker = ProgressTracker(hint=hint)
        tracker.current = activity

        history = history + [{"role": "user", "content": message}]

        # 立即反馈：点击后马上出现，消除"无响应"错觉
        yield history, tracker.render_status(), "", "", "", ""

        if mode == "多 Agent 协作":
            stream = service.multi_agent_stream(
                message, mode=(collab_mode or "").strip() or None, session_id=session_id or None,
            )
            title = "协作过程"
        elif mode == "单 Agent":
            # 勾选"自动确认"时全部放行（等价 CLI --yes）；否则挂起等待页面审批
            confirm_handler = (lambda evt: True) if auto_confirm else None
            stream = service.agent_chat_stream(
                message, confirm_handler=confirm_handler, session_id=session_id or None,
                interactive_confirm=not auto_confirm,
            )
            title = "执行过程"
        else:
            stream = service.rag_query_stream(
                message, enable_web_search=enable_web, session_id=session_id or None
            )
            title = "处理过程"

        final = None
        confirm_md = ""
        for evt in stream:
            if evt.kind == "confirm":
                confirm_md = format_confirm_request(evt.data if isinstance(evt.data, dict) else {})
                tracker.current = "⏸️ 等待你确认危险操作…"
                yield history, tracker.render_status(), tracker.render_steps(title), "", "", confirm_md
            elif evt.kind in ("progress", "step"):
                confirm_md = ""
                tracker.add(evt.message, evt.data if isinstance(evt.data, dict) else None)
                yield history, tracker.render_status(), tracker.render_steps(title), "", "", ""
            elif evt.kind == "heartbeat":
                yield history, tracker.render_status(), tracker.render_steps(title), "", "", confirm_md
            elif evt.kind == "answer":
                final = evt
            elif evt.kind == "cancelled":
                yield (
                    history, tracker.render_status("cancelled"),
                    tracker.render_steps(title, done=True), "", "", "",
                )
                return
            elif evt.kind == "error":
                yield (
                    history + [{"role": "assistant", "content": f"[错误] {evt.message}"}],
                    tracker.render_status("error"),
                    tracker.render_steps(title, done=True),
                    "",
                    "",
                    "",
                )
                return

        steps_md = tracker.render_steps(title, done=True)
        if final is None:
            yield history, tracker.render_status("error", "未获得回答"), steps_md, "", "", ""
            return

        data = final.data if isinstance(final.data, dict) else {}
        ctx = data.get("context") if isinstance(data.get("context"), dict) else {}
        status = with_context_status(tracker.render_status("done"), ctx)

        # 健康度提示：每会话只提示一次（展示后即标记）
        hint_md = format_suggest_hint(ctx)
        if hint_md:
            service.mark_suggested(session_id or None)

        # 追问被改写为独立问题时，在回答前注明"已理解为"
        prefix = ""
        rewritten = data.get("rewritten")
        if rewritten:
            prefix = f"> 🔗 已理解为：{rewritten}\n\n"

        if mode == "多 Agent 协作":
            content = prefix + format_multi_agent_result(data)
            yield history + [{"role": "assistant", "content": content}], status, steps_md, "", hint_md, ""
            return

        if mode == "单 Agent":
            content = prefix + (final.message or "")
            summary = format_step_log(data.get("step_log") or [])
            if summary:
                steps_md = f"{steps_md}\n\n{summary}" if steps_md else summary
            yield history + [{"role": "assistant", "content": content}], status, steps_md, "", hint_md, ""
            return

        if data.get("kind") == "meta":
            content = format_meta_overview(data.get("meta") or {})
            yield history + [{"role": "assistant", "content": content}], status, steps_md, "", hint_md, ""
            return
        yield (
            history + [{"role": "assistant", "content": prefix + (final.message or "")}],
            status,
            steps_md,
            format_rag_side(
                {
                    "sources": data.get("sources", []),
                    "web_sources": data.get("web_sources", []),
                }
            ),
            hint_md,
            "",
        )

    def on_resolve_confirm(approved: bool) -> str:
        """用户在审批卡片上点「允许 / 拒绝」。返回写入状态行的文案。"""
        if not service.resolve_confirm(bool(approved)):
            return "当前没有等待确认的操作"
        return "✅ 已允许，Agent 继续执行…" if approved else "⛔ 已拒绝，Agent 将改用其他方式或说明风险…"

    # ---------- 对话页会话控件（每个标签页绑定自己的会话）----------

    def on_session_init() -> Tuple[List[Tuple[str, str]], str, List[Dict[str, str]], str]:
        """页面加载：返回 (会话下拉选项, 本标签页会话 id, 该会话历史, 上下文状态)。"""
        sid = service.ensure_session()
        return service.session_choices(), sid, _load_history(sid), _context_status(sid)

    def on_session_select(session_id: str) -> Tuple[str, List[Dict[str, str]], str, str]:
        """下拉切换会话：返回 (会话 id, 历史, 上下文状态, 清空的提示)。"""
        sid = (session_id or "").strip()
        if not sid:
            return "", [], "", ""
        return sid, _load_history(sid), _context_status(sid), ""

    def on_new_session(
        carry_summary: bool, from_session_id: str
    ) -> Tuple[List[Tuple[str, str]], str, List[Dict[str, str]], str, str]:
        """新建会话（可选携带摘要）：返回 (下拉选项, 新会话 id, 历史, 上下文状态, 清空的提示)。"""
        sid = service.create_session(
            None, carry_summary=bool(carry_summary),
            from_session_id=(from_session_id or "").strip() or None,
        )
        return service.session_choices(), sid, _load_history(sid), _context_status(sid), ""

    def on_clear_context(session_id: str) -> Tuple[List[Dict[str, str]], str, str, str]:
        """清空当前会话上下文：返回 (历史, 状态行文案, 上下文状态, 清空的提示)。"""
        sid = (session_id or "").strip() or None
        ok = service.clear_context(sid)
        msg = "🧹 已清空当前会话上下文" if ok else "当前没有可清空的会话"
        return _load_history(sid or ""), msg, _context_status(sid or ""), ""

    def on_compact_context(session_id: str) -> Tuple[str, str]:
        """手动压缩：返回 (状态行文案, 上下文状态)。"""
        sid = (session_id or "").strip() or None
        result = service.compact_context(sid)
        if result.get("error"):
            msg = f"❌ 压缩失败：{result['error']}"
        elif not result.get("folded_messages"):
            msg = "当前历史较短，无需压缩"
        else:
            msg = f"🗜️ 已压缩：折叠 {result['folded_messages']} 条消息（第 {result.get('compressions', '?')} 次）"
        return msg, _context_status(sid or "")

    def on_continue_session(session_id: str) -> str:
        """用户选择继续当前会话：关闭提示，压缩次数再 +2 才再提示。"""
        service.continue_session((session_id or "").strip() or None)
        return ""

    def on_upload(file_paths: Optional[List[str]]) -> Tuple[str, str]:
        msg = service.add_documents(file_paths or [])
        return msg, format_stats(service.get_stats())

    def on_refresh_stats() -> str:
        return format_stats(service.get_stats())

    def on_clear_index() -> Tuple[str, str]:
        msg = service.clear_index()
        return msg, format_stats(service.get_stats())

    def on_list_sessions() -> str:
        return format_sessions(service.list_sessions())

    def _session_page_state(msg: str) -> Tuple[str, str, List[Tuple[str, str]], Optional[str]]:
        """会话页统一返回：(结果文案, 会话列表 Markdown, 下拉选项, 下拉当前值)。"""
        sessions = service.list_sessions()
        current = next((s["session_id"] for s in sessions if s.get("is_current")), None)
        return msg, format_sessions(sessions), service.session_choices(), current

    def on_sessions_refresh() -> Tuple[str, str, List[Tuple[str, str]], Optional[str]]:
        """刷新会话页（列表 + 下拉）。"""
        return _session_page_state("")

    def on_create_session(title: str, carry_summary: bool = False):
        """新建会话（可携带当前会话摘要）并切换过去。"""
        sid = service.create_session((title or "").strip() or None, carry_summary=bool(carry_summary))
        note = "（已携带上一会话摘要）" if carry_summary else ""
        return _session_page_state(f"✅ 已创建并切换到会话 `{sid[:8]}`{note}")

    def on_switch_session(session_id: str):
        """切换到指定会话（等价 CLI /session-switch）。"""
        session_id = (session_id or "").strip()
        if not session_id:
            return _session_page_state("_请先在下拉框选择会话_")
        ok = service.switch_session(session_id)
        msg = f"✅ 已切换到会话 `{session_id[:8]}`" if ok else f"❌ 切换失败：未找到会话 `{session_id[:8]}`"
        return _session_page_state(msg)

    def _fmt_result(text: str) -> str:
        """把服务层 ``[成功]/[提示]/[错误]`` 前缀换成图标。"""
        for prefix, icon in (("[成功]", "✅"), ("[提示]", "💡"), ("[错误]", "❌")):
            if text.startswith(prefix):
                return icon + text[len(prefix):]
        return text

    def on_delete_session(session_id: str):
        """删除指定会话（等价 CLI /session-delete；不允许删除当前会话）。"""
        return _session_page_state(_fmt_result(service.delete_session(session_id)))

    def on_archive_session(session_id: str):
        """归档指定会话（等价 CLI /session-archive）。"""
        return _session_page_state(_fmt_result(service.archive_session(session_id)))

    def on_search_sessions(query: str) -> str:
        """按关键词搜索会话（等价 CLI /session-search）。"""
        query = (query or "").strip()
        if not query:
            return ""
        results = service.search_sessions(query)
        if not results:
            return f"### 🔍 搜索结果\n\n_未找到包含「{query}」的会话_"
        lines = [f"### 🔍 搜索结果（{len(results)} 个包含「{query}」）", ""]
        for s in results:
            lines.append(f"- **{s.get('title', '未命名')}** `{s.get('session_id', '')[:8]}`")
        return "\n".join(lines)

    def on_rebuild_index(data_path: str) -> Tuple[str, str]:
        """按路径重建知识库索引（等价 CLI --data 构建）。"""
        msg = service.rebuild_index((data_path or "").strip() or None)
        return msg, format_stats(service.get_stats())

    def on_query_graph(entity: str) -> str:
        return format_graph_result(service.query_graph_entity(entity))

    def on_graph_summary() -> str:
        """展示知识图谱概览（等价 service.graph_summary）。"""
        summary = service.graph_summary()
        if not summary.get("is_available", True) and summary.get("error"):
            return f"_知识图谱不可用：{summary.get('error')}_"
        lines = ["### 🕸️ 知识图谱概览", ""]
        for k, v in summary.items():
            lines.append(f"- {k}: **{v}**")
        return "\n".join(lines)

    def on_stop() -> str:
        """停止当前任务（任一模式）。返回写入状态行的文案。"""
        return "⏹️ 已发送停止信号，正在中止…" if service.stop_agent() else "当前没有运行中的任务"

    # ---------- 模型管理（热切换）----------

    def on_model_status() -> str:
        return format_model_status(service.current_model())

    def on_model_chip() -> str:
        return format_model_chip(service.current_model())

    def on_model_choices() -> Tuple[List[str], str]:
        """返回 (可选模型列表, 当前模型)，供下拉框初始化/刷新。"""
        choices = service.list_models()
        current = service.current_model().get("model", "")
        if current and current not in choices:
            choices = [current] + choices
        return choices, current

    def on_switch_model(model: str) -> Tuple[str, str]:
        """切换模型；返回 (切换结果, 刷新后的状态行)。"""
        model = (model or "").strip()
        if not model:
            return "❌ 请选择模型", on_model_status()
        result = service.switch_model(model)
        return format_switch_result(result), on_model_status()

    def on_toggle_think(enabled: bool) -> Tuple[str, str, bool]:
        """开关思考模式；返回 (结果, 刷新后的状态行, 复选框应显示的实际值)。

        若当前模型不支持 thinking，服务层会拒绝开启，此时把复选框回弹为实际状态。
        """
        result = service.set_think(bool(enabled))
        return format_switch_result(result), on_model_status(), bool(result.get("enabled"))

    # ---------- 阶段三：工具命令面 ----------

    def on_web_search(query: str) -> str:
        return service.web_search(query)

    def on_web_extract(url: str) -> str:
        return service.web_extract(url)

    def on_web_cache_status() -> str:
        return service.web_cache_status()

    def on_web_cache_clear() -> str:
        return service.web_cache_clear()

    def on_code_ast(pattern: str, path: str) -> str:
        return service.code_ast(pattern, path or ".")

    def on_code_quality(path: str) -> str:
        return service.code_quality(path or ".")

    def on_git_analyze(analysis_type: str) -> str:
        return service.git_analyze(analysis_type or "history")

    def on_git_commit_gen() -> str:
        return service.git_commit_gen()

    def on_db_connect(db_type: str, database: str) -> str:
        return service.db_connect(db_type, database)

    def on_db_query(sql: str) -> str:
        return service.db_query(sql)

    def on_db_execute(sql: str) -> str:
        return service.db_execute(sql)

    def on_db_schema(table: str) -> str:
        return service.db_schema(table)

    def on_file_list() -> str:
        files = service.file_list()
        if not files:
            return "_知识库中暂无已登记的文件_"
        lines = ["### 📁 文件列表", ""]
        for fm in files:
            lines.append(f"- `{fm.get('path')}`（{fm.get('size', '?')}）")
        return "\n".join(lines)

    def on_file_stats() -> str:
        stats = service.file_stats()
        if "error" in stats:
            return f"[错误] {stats['error']}"
        return "\n".join(f"- {k}: **{v}**" for k, v in stats.items())

    def on_generate_skills() -> str:
        return service.generate_skills()

    def on_knowledge_summary() -> str:
        return service.knowledge_summary()

    def on_snapshot_list() -> str:
        return service.snapshot_list()

    def on_snapshot_create() -> str:
        return service.snapshot_create()

    def on_snapshot_restore(snapshot_id: str) -> str:
        return service.snapshot_restore(snapshot_id)

    def on_graph_build(text: str) -> str:
        return service.graph_build(text)

    # ---------- 侧栏会话列表 / 会话详情 ----------

    def on_session_list_state(session_id: str = "") -> Tuple[List[Tuple[str, str]], str]:
        """侧栏会话列表：返回 (选项, 应选中的会话 id)。

        若传入的 id 已不存在（被删除），回落到服务层当前会话。
        """
        choices = service.session_choices()
        ids = {sid for _, sid in choices}
        sid = (session_id or "").strip()
        if sid not in ids:
            try:
                sid = service.ensure_session()
            except Exception:  # noqa: BLE001
                sid = ""
            if sid not in ids:
                choices = service.session_choices()
        return choices, sid

    def on_session_filter(keyword: str) -> List[Tuple[str, str]]:
        """按关键词过滤侧栏会话列表（标题或消息内容）。"""
        keyword = (keyword or "").strip()
        choices = service.session_choices()
        if not keyword:
            return choices
        hit = {s.get("session_id") for s in service.search_sessions(keyword)}
        return [(label, sid) for label, sid in choices if sid in hit or keyword.lower() in label.lower()]

    def on_session_info(session_id: str) -> str:
        return format_session_info(service.session_info(session_id or ""))

    def on_sidebar_archive(session_id: str) -> Tuple[str, List[Tuple[str, str]], str]:
        """侧栏归档当前选中会话：返回 (结果文案, 列表选项, 选中 id)。"""
        msg = _fmt_result(service.archive_session(session_id))
        choices, sid = on_session_list_state(session_id)
        return msg, choices, sid

    def on_sidebar_delete(session_id: str) -> Tuple[str, List[Tuple[str, str]], str]:
        """侧栏删除当前选中会话（不允许删除当前会话）：返回 (结果, 选项, 选中 id)。"""
        msg = _fmt_result(service.delete_session(session_id))
        choices, sid = on_session_list_state("" if msg.startswith("✅") else session_id)
        return msg, choices, sid

    # ---------- 知识库：追加入库 / 卡片统计 / 文件管理 / 快照 / 摘要 ----------

    def on_stats_cards() -> str:
        stats = service.get_stats()
        files = service.file_list()
        count = len([f for f in files if not str(f.get("path", "")).startswith("[错误]")])
        return format_stats_cards(stats, file_count=count)

    def on_add_path(path: str, file_types: str = "") -> Tuple[str, str]:
        """追加服务器上的文件/目录入库（等价 CLI /add）。返回 (结果, 统计卡片)。"""
        return _fmt_result(service.add_path(path, file_types)), on_stats_cards()

    _FILE_HEADERS = ["文件", "大小", "类型", "上传时间", "片段", "访问", "路径"]

    def on_file_table() -> List[List[Any]]:
        """文件表：首列文件名便于浏览，末列完整路径供选中行取值。"""
        rows = []
        for f in service.file_list():
            path = str(f.get("path", ""))
            name = path.rsplit("/", 1)[-1] if "/" in path else path
            rows.append([
                name, f.get("size", ""), f.get("type", ""),
                f.get("upload_time", ""), f.get("chunk_count", 0), f.get("access_count", 0), path,
            ])
        return rows

    def on_file_info(path: str) -> str:
        return format_file_info(service.file_info(path))

    def on_file_stats_md() -> str:
        stats = service.file_stats()
        if "error" in stats:
            return f"❌ {stats['error']}"
        labels = {
            "total_files": "文件总数", "total_size_formatted": "总大小",
            "permanent_count": "永久", "temporary_count": "临时", "session_count": "会话级",
            "cleanup_count": "待清理",
        }
        rows = [(labels.get(k, k), v) for k, v in stats.items() if k != "total_size"]
        return format_kv_table(rows)

    def on_file_cleanup_preview() -> str:
        pending = service.file_cleanup_preview()
        if not pending:
            return "✅ 没有需要清理的文件"
        if str(pending[0].get("path", "")).startswith("[错误]"):
            return f"❌ {pending[0]['path']}"
        lines = [f"🧹 发现 {len(pending)} 个待清理文件（临时/过期，**将从磁盘删除**）：", ""]
        lines.extend(f"- `{p.get('path')}`（{p.get('type')}）" for p in pending[:20])
        if len(pending) > 20:
            lines.append(f"- … 共 {len(pending)} 个")
        return "\n".join(lines)

    def on_file_cleanup() -> Tuple[str, List[List[Any]]]:
        return _fmt_result(service.file_cleanup()), on_file_table()

    def on_file_dedupe_preview() -> str:
        dups = service.file_duplicates()
        if not dups:
            return "✅ 没有发现重复文件"
        if str(dups[0].get("path", "")).startswith("[错误]"):
            return f"❌ {dups[0]['path']}"
        lines = [f"⚠️ 发现 {len(dups)} 个重复登记（只移除登记，不删磁盘文件）：", ""]
        lines.extend(f"- `{d.get('path')}` ⟶ 与 `{d.get('duplicate_of')}` 重复" for d in dups[:20])
        return "\n".join(lines)

    def on_file_dedupe() -> Tuple[str, List[List[Any]]]:
        return _fmt_result(service.file_deduplicate()), on_file_table()

    _SNAPSHOT_HEADERS = ["快照 ID", "时间", "文档", "片段", "触发"]

    def on_snapshot_table() -> List[List[Any]]:
        return [
            [s.get("snapshot_id", ""), s.get("timestamp", ""), s.get("document_count", 0),
             s.get("total_chunks", 0), s.get("trigger", "")]
            for s in service.snapshot_list_data()
        ]

    def on_snapshot_create_table() -> Tuple[str, List[List[Any]]]:
        return _fmt_result(service.snapshot_create()), on_snapshot_table()

    _SUMMARY_HEADERS = ["文件", "类型", "置信度", "片段", "主题"]

    def on_knowledge_summary_table() -> List[List[Any]]:
        return [
            [d.get("file_name", ""), d.get("kind", ""),
             f"{d.get('confidence', 0):.2f}" if isinstance(d.get("confidence"), (int, float)) else "",
             d.get("chunk_count", 0), d.get("topics", "")]
            for d in service.knowledge_summary_data()
        ]

    # ---------- 知识图谱：带类型查询 / 文件构建 ----------

    def on_graph_query_typed(query_type: str, query: str) -> str:
        result = service.graph_query_typed(query, query_type or "entity")
        return _fmt_result(str(result.get("text", "")))

    def on_graph_build_any(source: str, text: str) -> str:
        """按来源构建：``文件路径`` 读取服务器文件，否则按文本。"""
        if (source or "").startswith("文件"):
            return _fmt_result(service.graph_build_file(text))
        return _fmt_result(service.graph_build(text))

    # ---------- 工具：数据库写操作 / Shell / 文件读写 / 工作目录 ----------

    def on_db_create_table(table: str, columns_json: str) -> str:
        return _fmt_result(service.db_create_table(table, columns_json))

    def on_db_insert(table: str, data_json: str) -> str:
        return _fmt_result(service.db_insert(table, data_json))

    def on_exec_analyze(command: str) -> Tuple[str, bool, bool]:
        """分析命令：返回 (分析文案, 可直接执行, 需二次确认)。"""
        safety = service.exec_analyze(command)
        if not command or not command.strip():
            return "", False, False
        if safety.get("error") or safety.get("is_dangerous"):
            return format_exec_analysis(safety), False, False
        needs = bool(safety.get("needs_confirm"))
        return format_exec_analysis(safety), not needs, needs

    def on_exec_run(command: str) -> str:
        result = service.exec_run(command)
        if result.startswith("[错误]") or result.startswith("[提示]"):
            return _fmt_result(result)
        return f"```\n{result}\n```"

    def on_read_file(path: str, offset: float = 0, limit: float = 200) -> str:
        result = service.read_file(path, int(offset or 0), int(limit or 200))
        if result.startswith("[错误]") or result.startswith("[提示]"):
            return _fmt_result(result)
        return f"```\n{result}\n```"

    def on_write_file(path: str, content: str, append: bool = False) -> str:
        return _fmt_result(service.write_file(path, content, bool(append)))

    def on_cwd() -> str:
        return f"当前工作目录：`{service.cwd()}`"

    def on_chdir(path: str) -> Tuple[str, str]:
        """切换工作目录：返回 (结果, 当前目录文案)。"""
        return _fmt_result(service.chdir(path)), on_cwd()

    # ---------- 系统：环境 / 工具清单 / 模型表 ----------

    def on_env_info() -> str:
        return format_env_info(service.env_info())

    _TOOL_HEADERS = ["工具", "安全等级", "描述", "参数"]

    def on_tools_table() -> List[List[Any]]:
        return [
            [t.get("name", ""), "安全（只读）" if t.get("safe", True) else "需确认（会修改系统）",
             t.get("description", ""), ", ".join((t.get("parameters") or {}).keys())]
            for t in service.list_tools()
        ]

    _MODEL_HEADERS = ["模型", "当前", "已加载"]

    def on_model_table() -> List[List[Any]]:
        return [
            [m.get("name", ""), "✔" if m.get("current") else "", "✔" if m.get("loaded") else ""]
            for m in service.model_table()
        ]

    def on_collab_choices() -> List[Tuple[str, str]]:
        return service.collaboration_modes()

    return {
        "on_resolve_confirm": on_resolve_confirm,
        "on_session_list_state": on_session_list_state,
        "on_session_filter": on_session_filter,
        "on_session_info": on_session_info,
        "on_sidebar_archive": on_sidebar_archive,
        "on_sidebar_delete": on_sidebar_delete,
        "on_stats_cards": on_stats_cards,
        "on_add_path": on_add_path,
        "on_file_table": on_file_table,
        "on_file_info": on_file_info,
        "on_file_stats_md": on_file_stats_md,
        "on_file_cleanup_preview": on_file_cleanup_preview,
        "on_file_cleanup": on_file_cleanup,
        "on_file_dedupe_preview": on_file_dedupe_preview,
        "on_file_dedupe": on_file_dedupe,
        "on_snapshot_table": on_snapshot_table,
        "on_snapshot_create_table": on_snapshot_create_table,
        "on_knowledge_summary_table": on_knowledge_summary_table,
        "on_graph_query_typed": on_graph_query_typed,
        "on_graph_build_any": on_graph_build_any,
        "on_db_create_table": on_db_create_table,
        "on_db_insert": on_db_insert,
        "on_exec_analyze": on_exec_analyze,
        "on_exec_run": on_exec_run,
        "on_read_file": on_read_file,
        "on_write_file": on_write_file,
        "on_cwd": on_cwd,
        "on_chdir": on_chdir,
        "on_env_info": on_env_info,
        "on_tools_table": on_tools_table,
        "on_model_table": on_model_table,
        "on_collab_choices": on_collab_choices,
        "headers": {
            "files": _FILE_HEADERS, "snapshots": _SNAPSHOT_HEADERS, "summary": _SUMMARY_HEADERS,
            "tools": _TOOL_HEADERS, "models": _MODEL_HEADERS,
        },
        "on_chat": on_chat,
        "on_chat_stream": on_chat_stream,
        "on_session_init": on_session_init,
        "on_session_select": on_session_select,
        "on_new_session": on_new_session,
        "on_clear_context": on_clear_context,
        "on_compact_context": on_compact_context,
        "on_continue_session": on_continue_session,
        "on_upload": on_upload,
        "on_refresh_stats": on_refresh_stats,
        "on_clear_index": on_clear_index,
        "on_rebuild_index": on_rebuild_index,
        "on_list_sessions": on_list_sessions,
        "on_sessions_refresh": on_sessions_refresh,
        "on_create_session": on_create_session,
        "on_switch_session": on_switch_session,
        "on_delete_session": on_delete_session,
        "on_archive_session": on_archive_session,
        "on_search_sessions": on_search_sessions,
        "on_query_graph": on_query_graph,
        "on_graph_summary": on_graph_summary,
        "on_graph_build": on_graph_build,
        "on_stop": on_stop,
        "on_model_status": on_model_status,
        "on_model_chip": on_model_chip,
        "on_model_choices": on_model_choices,
        "on_switch_model": on_switch_model,
        "on_toggle_think": on_toggle_think,
        "on_web_search": on_web_search,
        "on_web_extract": on_web_extract,
        "on_web_cache_status": on_web_cache_status,
        "on_web_cache_clear": on_web_cache_clear,
        "on_code_ast": on_code_ast,
        "on_code_quality": on_code_quality,
        "on_git_analyze": on_git_analyze,
        "on_git_commit_gen": on_git_commit_gen,
        "on_db_connect": on_db_connect,
        "on_db_query": on_db_query,
        "on_db_execute": on_db_execute,
        "on_db_schema": on_db_schema,
        "on_file_list": on_file_list,
        "on_file_stats": on_file_stats,
        "on_generate_skills": on_generate_skills,
        "on_knowledge_summary": on_knowledge_summary,
        "on_snapshot_list": on_snapshot_list,
        "on_snapshot_create": on_snapshot_create,
        "on_snapshot_restore": on_snapshot_restore,
    }


# ==================== Gradio 装配（不做单元测试）====================

# 完整样式（布局 + 多主题色变量）由 theme 模块生成；Gradio 6 起 css 需在 launch() 传入。
from .theme import build_css as _build_css  # noqa: E402

APP_CSS = _build_css()


def build_app(service: Optional[WebService] = None):  # pragma: no cover
    """组装 Gradio Blocks 应用（布局细节见 ``web.ui`` 包）。"""
    from .ui.layout import build_layout

    service = service or get_web_service()
    handlers = build_handlers(service)
    return build_layout(service, handlers)


def serve_blocking(app, wait: Optional[Callable[[], None]] = None) -> None:
    """阻塞等待直到收到中断信号，并在退出时优雅关闭 app 以释放端口。

    该函数不直接调用 gradio，便于单元测试：
    - ``app.close()`` 用于关闭 Gradio 服务器、释放监听端口。
    - ``wait`` 为可注入的阻塞等待函数（默认无限等待事件），收到
      ``KeyboardInterrupt`` 时正常返回，进入 finally 关闭。

    这样无论前台运行还是从 launcher 启动，Ctrl+C / 进程退出都能确定地释放端口，
    Gradio 服务器随进程一并退出，不会残留孤儿进程占用端口。
    """
    if wait is None:  # pragma: no cover - 默认分支依赖真实阻塞，测试时注入 wait
        import threading

        def wait():
            threading.Event().wait()

    try:
        wait()
    except KeyboardInterrupt:
        pass
    finally:
        close = getattr(app, "close", None)
        if callable(close):
            try:
                close()
            except Exception:
                pass


def launch(
    server_name: str = "127.0.0.1",
    server_port: int = 7860,
    share: bool = False,
    **kwargs,
):  # pragma: no cover
    """启动 Web 界面。默认仅绑定本地回环地址，符合隐私优先原则。

    使用 ``prevent_thread_lock=True`` 让 ``launch()`` 立即返回，改由
    ``serve_blocking`` 统一负责阻塞与优雅关闭，从而保证 Ctrl+C 时能干净地
    释放端口、Gradio 服务器随进程一并退出。
    """
    from pathlib import Path

    from .theme import HEAD_HTML, make_gradio_theme

    # favicon 复用桌面端图标（打包后 assets 目录随包分发）
    favicon = None
    for candidate in (
        Path(__file__).resolve().parents[2] / "assets" / "icon.png",
        Path(__file__).resolve().parents[1] / "assets" / "icon.png",
    ):
        if candidate.exists():
            favicon = str(candidate)
            break

    app = build_app()
    app.launch(
        server_name=server_name,
        server_port=server_port,
        share=share,
        theme=make_gradio_theme(),
        css=APP_CSS,
        head=HEAD_HTML,
        favicon_path=favicon,
        prevent_thread_lock=True,
        **kwargs,
    )
    serve_blocking(app)


def main():  # pragma: no cover
    launch()


if __name__ == "__main__":  # pragma: no cover
    main()
