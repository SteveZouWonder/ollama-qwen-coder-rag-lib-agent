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
    return str(text or "").replace("\n", " ").replace("|", "／").strip()


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
    ):
        """流式对话入口（供 Gradio 使用）。

        yield 五元组 ``(history, status_md, process_md, sources_md, hint_md)``：

        - ``history``：Chatbot（messages 格式）的完整多轮消息列表——会话内既有
          历史 + 本轮用户消息，完成后追加助手回答；
        - ``status_md``：一行状态，始终显示"当前在做什么 + 已用时"，完成/出错/
          停止时换成对应结论，完成后追加 ``上下文 3.2K / 4.8K · 已压缩 N 次``；
        - ``process_md``：按阶段累积的处理过程列表（心跳与计数类事件原地刷新，
          不刷屏；含"结合上下文理解问题""压缩历史上下文"等上下文事件）；
        - ``sources_md``：完成后的引用来源 / 多 Agent 结果明细；
        - ``hint_md``：健康度建议（如"对话较长，建议新建会话"），空串表示无提示。

        三种模式（RAG / 单 Agent / 多 Agent）统一走服务层带心跳与取消的事件流，
        并绑定到 ``session_id``（每个浏览器标签页自己的会话）。
        """
        message = (message or "").strip()
        session_id = (session_id or "").strip()
        history = _load_history(session_id)
        if not message:
            yield history, "_请输入内容_", "", "", ""
            return

        if service.is_running() is True:
            yield history, "⚠️ 已有任务在运行，请先等待完成或点击「停止」", "", "", ""
            return

        activity, hint = _startup_hint()
        tracker = ProgressTracker(hint=hint)
        tracker.current = activity

        history = history + [{"role": "user", "content": message}]

        # 立即反馈：点击后马上出现，消除"无响应"错觉
        yield history, tracker.render_status(), "", "", ""

        if mode == "多 Agent 协作":
            stream = service.multi_agent_stream(message, session_id=session_id or None)
            title = "协作过程"
        elif mode == "单 Agent":
            confirm_handler = (lambda evt: True) if auto_confirm else None
            stream = service.agent_chat_stream(
                message, confirm_handler=confirm_handler, session_id=session_id or None
            )
            title = "执行过程"
        else:
            stream = service.rag_query_stream(
                message, enable_web_search=enable_web, session_id=session_id or None
            )
            title = "处理过程"

        final = None
        for evt in stream:
            if evt.kind in ("progress", "step"):
                tracker.add(evt.message, evt.data if isinstance(evt.data, dict) else None)
                yield history, tracker.render_status(), tracker.render_steps(title), "", ""
            elif evt.kind == "heartbeat":
                yield history, tracker.render_status(), tracker.render_steps(title), "", ""
            elif evt.kind == "answer":
                final = evt
            elif evt.kind == "cancelled":
                yield (
                    history, tracker.render_status("cancelled"),
                    tracker.render_steps(title, done=True), "", "",
                )
                return
            elif evt.kind == "error":
                yield (
                    history + [{"role": "assistant", "content": f"[错误] {evt.message}"}],
                    tracker.render_status("error"),
                    tracker.render_steps(title, done=True),
                    "",
                    "",
                )
                return

        steps_md = tracker.render_steps(title, done=True)
        if final is None:
            yield history, tracker.render_status("error", "未获得回答"), steps_md, "", ""
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
            yield history + [{"role": "assistant", "content": content}], status, steps_md, "", hint_md
            return

        if mode == "单 Agent":
            content = prefix + (final.message or "")
            yield history + [{"role": "assistant", "content": content}], status, steps_md, "", hint_md
            return

        if data.get("kind") == "meta":
            content = format_meta_overview(data.get("meta") or {})
            yield history + [{"role": "assistant", "content": content}], status, steps_md, "", hint_md
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
        )

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

    return {
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

# 对话页样式：操作按钮靠右排列、状态行固定高度避免抖动。
# Gradio 6 起 css 需在 launch() 传入，而非 Blocks()。
APP_CSS = """
.chat-actions { justify-content: flex-end !important; gap: 8px; }
.chat-actions > * { flex-grow: 0 !important; }
.chat-status { min-height: 1.8em; opacity: 0.9; }
.chat-hint { align-items: center; padding: 6px 10px; border-radius: 8px;
             background: var(--color-accent-soft, rgba(255, 196, 0, 0.12)); }
/* 对话区：标题「对话」与右上角按钮固定不随滚轮滚动。
   Gradio 未设固定 height 时会让整个 .block 以 overflow:auto 滚动，而标签/按钮是相对
   .block 绝对定位的，于是一起滚走。这里让 .block 不滚、只让内部消息区滚动。 */
#chatbot { overflow: hidden !important; display: flex !important; flex-direction: column; }
#chatbot > .wrapper { flex: 1 1 auto; min-height: 0; }
#chatbot .bubble-wrap, #chatbot .panel-wrap { overflow-y: auto; min-height: 0; }
/* 会话页：表格撑满宽度，标题列可换行、其余列不换行 */
.session-list table { width: 100%; table-layout: auto; }
.session-list th, .session-list td { white-space: nowrap; }
.session-list td:nth-child(2), .session-list td:nth-child(6) { white-space: normal; }
"""


def build_app(service: Optional[WebService] = None):  # pragma: no cover
    """组装 Gradio Blocks 应用。"""
    import gradio as gr

    service = service or get_web_service()
    handlers = build_handlers(service)

    with gr.Blocks(title="Cerebro 🧠") as app:
        gr.Markdown("# Cerebro 🧠\n本地优先的 RAG + Agent 助手")
        # 顶部状态行：当前模型 / 是否已加载 / num_ctx / 思考模式；切换后即时刷新
        model_status = gr.Markdown(handlers["on_model_status"]())

        with gr.Tab("对话"):
            # 模型热切换：下拉列出本机已安装模型，切换会同步 RAG/Agent 并释放旧模型
            _choices, _current = handlers["on_model_choices"]()
            with gr.Row():
                model_dd = gr.Dropdown(
                    choices=_choices,
                    value=_current or None,
                    label="模型（切换后立即生效，旧模型自动释放）",
                    scale=6,
                    allow_custom_value=True,
                )
                model_switch_btn = gr.Button("切换模型", scale=1)
                model_refresh_btn = gr.Button("刷新列表", scale=1)
                # 思考模式：默认关（响应快）；开启需模型支持，不支持时自动回弹
                think_cb = gr.Checkbox(
                    value=bool(service.current_model().get("think")),
                    label="思考模式（慢，适合复杂推理）",
                    scale=2,
                )
            model_switch_result = gr.Markdown()
            model_switch_btn.click(
                handlers["on_switch_model"], model_dd, [model_switch_result, model_status]
            )
            think_cb.input(
                handlers["on_toggle_think"], think_cb,
                [model_switch_result, model_status, think_cb],
            )

            def _refresh_model_dropdown():
                choices, current = handlers["on_model_choices"]()
                return gr.update(choices=choices, value=current or None)

            model_refresh_btn.click(_refresh_model_dropdown, None, model_dd)

            # ---- 会话控件：每个浏览器标签页用 gr.State 绑定自己的会话 ----
            session_state = gr.State("")
            with gr.Row():
                session_dd = gr.Dropdown(
                    choices=[], value=None, label="会话（切换后加载该会话的多轮历史）",
                    scale=6, allow_custom_value=True,
                )
                carry_cb = gr.Checkbox(value=False, label="携带摘要", scale=1)
                new_session_btn = gr.Button("新建会话", scale=1)
                clear_ctx_btn = gr.Button("清空上下文", scale=1)
                compact_btn = gr.Button("压缩历史", scale=1)
            context_box = gr.Markdown(elem_classes=["chat-status"])

            mode = gr.Radio(
                ["RAG 检索", "单 Agent", "多 Agent 协作"],
                value="RAG 检索",
                label="模式",
            )
            with gr.Row():
                enable_web = gr.Checkbox(
                    value=True,
                    label="联网搜索增强（RAG 模式，等价 CLI /ask 的网络增强）",
                )
                auto_confirm = gr.Checkbox(
                    value=False,
                    label="自动确认危险命令（单 Agent 模式，等价 CLI --yes）",
                )

            # ---- 多轮对话展示（Gradio 6 的 Chatbot 即 messages 格式）----
            # 不设固定 height（默认 400px 会让空会话留一大片空白）：随消息自动扩展，
            # 超过 max_height 后在内部滚动；空态用 placeholder 提示，可拖拽右下角调高。
            chatbot = gr.Chatbot(
                label="对话",
                elem_id="chatbot",
                height=None,
                min_height=96,
                max_height=560,
                resizable=True,
                placeholder="_还没有消息。输入问题开始对话，支持追问（如“它多少钱”）。_",
            )

            # ---- 输入区：输入框在上，操作按钮在其下方右对齐 ----
            # 此前输入框与两个按钮同排，按钮顶部对齐到输入框的 label 行，视觉错位。
            with gr.Group():
                msg_box = gr.Textbox(
                    placeholder="输入你的问题…（Enter 发送，Shift+Enter 换行；支持追问，如“它多少钱”）",
                    show_label=False,
                    lines=1,
                    max_lines=6,
                    autofocus=True,
                )
                with gr.Row(elem_classes=["chat-actions"]):
                    stop_btn = gr.Button("停止", scale=0, min_width=96, interactive=False)
                    send_btn = gr.Button("发送", scale=0, min_width=120, variant="primary")

            # ---- 输出区：状态行 → 健康度提示 → 处理过程 → 引用来源 ----
            status_box = gr.Markdown(elem_classes=["chat-status"])
            with gr.Row(visible=False, elem_classes=["chat-hint"]) as hint_row:
                hint_box = gr.Markdown(scale=6)
                hint_new_btn = gr.Button("新建会话", scale=1, size="sm")
                hint_continue_btn = gr.Button("继续当前会话", scale=1, size="sm")
            with gr.Accordion("处理过程", open=True):
                process_box = gr.Markdown()
            with gr.Accordion("引用来源 / 结果明细", open=False):
                sources_box = gr.Markdown()

            # 待发送消息暂存：先把输入框清空并锁定按钮，再用暂存值发起对话
            pending_msg = gr.State("")
            _chat_outputs = [chatbot, status_box, process_box, sources_box, hint_box, hint_row]

            def _chat_stream_ui(message, mode_v, web_v, confirm_v, sid):
                """把处理器的五元组映射为组件更新（提示非空时显示提示行）。"""
                for history, status, process, sources, hint in handlers["on_chat_stream"](
                    message, mode_v, web_v, confirm_v, sid
                ):
                    yield history, status, process, sources, hint, gr.update(visible=bool(hint))

            def _begin(message: str):
                """点击发送：暂存消息、清空输入框、禁用发送、启用停止。"""
                return (
                    message,
                    "",
                    gr.update(interactive=False),
                    gr.update(interactive=True),
                )

            def _end(sid):
                """任务结束/停止后：恢复发送、禁用停止、刷新上下文状态与会话列表。"""
                return (
                    gr.update(interactive=True),
                    gr.update(interactive=False),
                    handlers["on_session_select"](sid)[2],
                    gr.update(choices=service.session_choices(), value=sid or None),
                )

            _begin_outputs = [pending_msg, msg_box, send_btn, stop_btn]
            _chat_inputs = [pending_msg, mode, enable_web, auto_confirm, session_state]
            _end_outputs = [send_btn, stop_btn, context_box, session_dd]

            send_chain = send_btn.click(_begin, msg_box, _begin_outputs).then(
                _chat_stream_ui, _chat_inputs, _chat_outputs
            )
            send_chain.then(_end, session_state, _end_outputs)
            submit_chain = msg_box.submit(_begin, msg_box, _begin_outputs).then(
                _chat_stream_ui, _chat_inputs, _chat_outputs
            )
            submit_chain.then(_end, session_state, _end_outputs)

            # 停止：通知服务层取消（三种模式通用），同时让 Gradio 中断正在推送的流
            stop_btn.click(
                handlers["on_stop"], None, status_box,
                cancels=[send_chain, submit_chain],
            ).then(_end, session_state, _end_outputs)

            # ---- 会话控件事件 ----
            def _session_init():
                choices, sid, history, ctx_md = handlers["on_session_init"]()
                return gr.update(choices=choices, value=sid), sid, history, ctx_md

            app.load(_session_init, None, [session_dd, session_state, chatbot, context_box])

            def _session_select(sid):
                new_sid, history, ctx_md, hint = handlers["on_session_select"](sid)
                return new_sid, history, ctx_md, hint, gr.update(visible=False)

            session_dd.input(
                _session_select, session_dd,
                [session_state, chatbot, context_box, hint_box, hint_row],
            )

            def _new_session(carry, sid):
                choices, new_sid, history, ctx_md, hint = handlers["on_new_session"](carry, sid)
                return (
                    gr.update(choices=choices, value=new_sid), new_sid, history, ctx_md,
                    hint, gr.update(visible=False), "✨ 已新建会话" + ("（已携带摘要）" if carry else ""),
                )

            _new_outputs = [session_dd, session_state, chatbot, context_box, hint_box, hint_row, status_box]
            new_session_btn.click(_new_session, [carry_cb, session_state], _new_outputs)
            hint_new_btn.click(_new_session, [carry_cb, session_state], _new_outputs)

            def _clear_ctx(sid):
                history, msg, ctx_md, hint = handlers["on_clear_context"](sid)
                return history, msg, ctx_md, hint, gr.update(visible=False)

            clear_ctx_btn.click(
                _clear_ctx, session_state,
                [chatbot, status_box, context_box, hint_box, hint_row],
            )
            compact_btn.click(
                handlers["on_compact_context"], session_state, [status_box, context_box]
            )

            def _continue(sid):
                handlers["on_continue_session"](sid)
                return "", gr.update(visible=False)

            hint_continue_btn.click(_continue, session_state, [hint_box, hint_row])

        with gr.Tab("知识库"):
            stats_box = gr.Markdown(format_stats(service.get_stats()))
            upload = gr.File(file_count="multiple", type="filepath", label="上传文档")
            upload_result = gr.Markdown()
            with gr.Row():
                refresh_btn = gr.Button("刷新统计")
                clear_btn = gr.Button("清空索引", variant="stop")
            upload.upload(handlers["on_upload"], upload, [upload_result, stats_box])
            refresh_btn.click(handlers["on_refresh_stats"], None, stats_box)
            clear_btn.click(handlers["on_clear_index"], None, [upload_result, stats_box])
            gr.Markdown("---\n**从目录重建索引**")
            with gr.Row():
                rebuild_path = gr.Textbox(
                    placeholder="数据目录/文件路径...", scale=8, label="重建路径"
                )
                rebuild_btn = gr.Button("重建索引", scale=1)
            rebuild_result = gr.Markdown()
            rebuild_btn.click(
                handlers["on_rebuild_index"], rebuild_path, [rebuild_result, stats_box]
            )

        with gr.Tab("会话"):
            # 会话管理：表格列表 + 下拉选中后 切换 / 归档 / 删除 + 新建（可携带摘要）+ 搜索。
            # 与 CLI 的 /session-* 命令面对齐；删除同样禁止删当前会话。
            _s_msg, _s_list, _s_choices, _s_current = handlers["on_sessions_refresh"]()
            sessions_box = gr.Markdown(_s_list, elem_classes=["session-list"])
            session_result = gr.Markdown(elem_classes=["chat-status"])
            with gr.Row():
                manage_dd = gr.Dropdown(
                    choices=_s_choices, value=_s_current, label="选择会话",
                    scale=6, allow_custom_value=True,
                )
                switch_btn = gr.Button("切换", scale=1, variant="primary")
                archive_btn = gr.Button("归档", scale=1)
                delete_btn = gr.Button("删除", scale=1, variant="stop")
                list_btn = gr.Button("刷新", scale=1)
            with gr.Row():
                new_title = gr.Textbox(placeholder="会话标题（可选，留空按时间命名）", label="新建会话", scale=5)
                new_carry_cb = gr.Checkbox(value=False, label="携带当前会话摘要", scale=2)
                new_btn = gr.Button("新建并切换", scale=1)
            with gr.Row():
                search_kw = gr.Textbox(placeholder="按标题或消息内容搜索…", scale=6, label="搜索会话")
                search_btn = gr.Button("搜索", scale=1)
            search_result = gr.Markdown()

            _session_outputs = [session_result, sessions_box, manage_dd]

            def _wrap_session(fn):
                """把 (文案, 列表, 选项, 当前值) 映射为组件更新（下拉需 gr.update）。"""
                def inner(*args):
                    msg, table, choices, current = fn(*args)
                    return msg, table, gr.update(choices=choices, value=current)
                inner.__name__ = fn.__name__  # 保持 API 端点名可读（/on_switch_session 等）
                return inner

            switch_btn.click(_wrap_session(handlers["on_switch_session"]), manage_dd, _session_outputs)
            archive_btn.click(_wrap_session(handlers["on_archive_session"]), manage_dd, _session_outputs)
            delete_btn.click(_wrap_session(handlers["on_delete_session"]), manage_dd, _session_outputs)
            list_btn.click(_wrap_session(handlers["on_sessions_refresh"]), None, _session_outputs)
            new_btn.click(
                _wrap_session(handlers["on_create_session"]), [new_title, new_carry_cb], _session_outputs
            )
            search_btn.click(handlers["on_search_sessions"], search_kw, search_result)
            search_kw.submit(handlers["on_search_sessions"], search_kw, search_result)

        with gr.Tab("知识图谱"):
            entity_box = gr.Textbox(placeholder="输入实体名...", label="查询实体")
            with gr.Row():
                graph_btn = gr.Button("查询实体")
                summary_btn = gr.Button("图谱概览")
            graph_result = gr.Markdown()
            graph_btn.click(handlers["on_query_graph"], entity_box, graph_result)
            summary_btn.click(handlers["on_graph_summary"], None, graph_result)
            gr.Markdown("---\n**从文本构建图谱**")
            gb_text = gr.Textbox(lines=3, placeholder="输入用于构建知识图谱的文本...", label="构建文本")
            gb_btn = gr.Button("构建")
            gb_result = gr.Markdown()
            gb_btn.click(handlers["on_graph_build"], gb_text, gb_result)

        with gr.Tab("文件管理"):
            with gr.Row():
                fl_btn = gr.Button("文件列表")
                fs_btn = gr.Button("文件统计")
            file_result = gr.Markdown()
            fl_btn.click(handlers["on_file_list"], None, file_result)
            fs_btn.click(handlers["on_file_stats"], None, file_result)

        with gr.Tab("网络搜索"):
            with gr.Row():
                ws_query = gr.Textbox(placeholder="搜索关键词...", scale=8, label="网络搜索")
                ws_btn = gr.Button("搜索", scale=1, variant="primary")
            ws_result = gr.Markdown()
            ws_btn.click(handlers["on_web_search"], ws_query, ws_result)
            with gr.Row():
                we_url = gr.Textbox(placeholder="https://...", scale=8, label="提取网页正文")
                we_btn = gr.Button("提取", scale=1)
            we_result = gr.Markdown()
            we_btn.click(handlers["on_web_extract"], we_url, we_result)
            with gr.Row():
                wc_status_btn = gr.Button("缓存状态")
                wc_clear_btn = gr.Button("清空缓存", variant="stop")
            wc_result = gr.Markdown()
            wc_status_btn.click(handlers["on_web_cache_status"], None, wc_result)
            wc_clear_btn.click(handlers["on_web_cache_clear"], None, wc_result)

        with gr.Tab("代码分析"):
            with gr.Row():
                ca_pattern = gr.Textbox(placeholder="AST 搜索模式...", scale=6, label="AST 搜索")
                ca_path = gr.Textbox(value=".", scale=2, label="路径")
                ca_btn = gr.Button("搜索", scale=1)
            ca_result = gr.Markdown()
            ca_btn.click(handlers["on_code_ast"], [ca_pattern, ca_path], ca_result)
            with gr.Row():
                cq_path = gr.Textbox(value=".", scale=8, label="代码质量检查路径")
                cq_btn = gr.Button("检查", scale=1)
            cq_result = gr.Markdown()
            cq_btn.click(handlers["on_code_quality"], cq_path, cq_result)

        with gr.Tab("Git"):
            ga_type = gr.Radio(
                ["history", "status", "authors"], value="history", label="分析类型"
            )
            ga_btn = gr.Button("Git 分析")
            ga_result = gr.Markdown()
            ga_btn.click(handlers["on_git_analyze"], ga_type, ga_result)
            gr.Markdown("---")
            gcg_btn = gr.Button("生成提交信息（AI）")
            gcg_result = gr.Markdown()
            gcg_btn.click(handlers["on_git_commit_gen"], None, gcg_result)

        with gr.Tab("数据库"):
            with gr.Row():
                db_type = gr.Textbox(placeholder="sqlite / mysql ...", scale=3, label="类型")
                db_name = gr.Textbox(placeholder="数据库路径/名称", scale=5, label="数据库")
                db_conn_btn = gr.Button("连接", scale=1)
            db_conn_result = gr.Markdown()
            db_conn_btn.click(handlers["on_db_connect"], [db_type, db_name], db_conn_result)
            with gr.Row():
                dq_sql = gr.Textbox(placeholder="SELECT ...", scale=8, label="查询 SQL")
                dq_btn = gr.Button("查询", scale=1)
            dq_result = gr.Markdown()
            dq_btn.click(handlers["on_db_query"], dq_sql, dq_result)
            with gr.Row():
                de_sql = gr.Textbox(placeholder="INSERT/UPDATE/DDL ...", scale=8, label="执行 SQL")
                de_btn = gr.Button("执行", scale=1)
            de_result = gr.Markdown()
            de_btn.click(handlers["on_db_execute"], de_sql, de_result)
            with gr.Row():
                ds_table = gr.Textbox(placeholder="表名（留空列出所有表）", scale=8, label="查看 Schema")
                ds_btn = gr.Button("Schema", scale=1)
            ds_result = gr.Markdown()
            ds_btn.click(handlers["on_db_schema"], ds_table, ds_result)

        with gr.Tab("知识库管理"):
            with gr.Row():
                gs_btn = gr.Button("生成 Skills")
                ks_btn = gr.Button("知识库摘要")
            km_result = gr.Markdown()
            gs_btn.click(handlers["on_generate_skills"], None, km_result)
            ks_btn.click(handlers["on_knowledge_summary"], None, km_result)
            gr.Markdown("---\n**快照管理**")
            with gr.Row():
                sl_btn = gr.Button("快照列表")
                sc_btn = gr.Button("创建快照")
            snap_result = gr.Markdown()
            sl_btn.click(handlers["on_snapshot_list"], None, snap_result)
            sc_btn.click(handlers["on_snapshot_create"], None, snap_result)
            with gr.Row():
                sr_id = gr.Textbox(placeholder="快照 ID...", scale=8, label="恢复快照")
                sr_btn = gr.Button("生成恢复脚本", scale=1)
            sr_result = gr.Markdown()
            sr_btn.click(handlers["on_snapshot_restore"], sr_id, sr_result)

    return app


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
    import gradio as gr

    app = build_app()
    app.launch(
        server_name=server_name,
        server_port=server_port,
        share=share,
        theme=gr.themes.Soft(),
        css=APP_CSS,
        prevent_thread_lock=True,
        **kwargs,
    )
    serve_blocking(app)


def main():  # pragma: no cover
    launch()


if __name__ == "__main__":  # pragma: no cover
    main()
