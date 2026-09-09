"""对话页处理器：对话 / 流式对话 / 审批 / 会话控件 / 会话页 / 侧栏会话列表。"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from ..formatters import (
    CARRIED_TITLE,
    MODE_AUTO,
    ProgressTracker,
    _fmt_result,
    _noop,
    _starts_new_round,
    component_update,
    format_citation_status,
    format_confirm_request,
    format_context_metrics,
    format_fallback_hint,
    format_meta_overview,
    format_multi_agent_result,
    format_notices,
    format_rag_side,
    format_session_info,
    format_sessions,
    format_step_log,
    format_suggest_hint,
    with_context_status,
)
from ..services import WebService


def build_chat_handlers(service: WebService) -> Dict[str, Any]:
    """对话页处理器：对话 / 流式对话 / 审批 / 会话控件 / 会话页 / 侧栏会话列表（由 ``app.build_handlers`` 汇总）。"""

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

        if mode == MODE_AUTO:
            # 自动路由（F8 P3-3）：服务层判定后分发；按 routed_mode 选择渲染路径
            answer = ""
            steps: List[str] = []
            route_line = ""
            final = None
            for evt in service.chat_auto_stream(
                message, enable_web_search=enable_web, auto_confirm=auto_confirm,
                interactive_confirm=False,
            ):
                if evt.kind == "progress" and isinstance(evt.data, dict) and evt.data.get("phase") == "route":
                    route_line = evt.message
                elif evt.kind == "step":
                    steps.append(f"- {evt.message}")
                elif evt.kind == "answer":
                    final = evt
                elif evt.kind == "error":
                    return "", f"[错误] {evt.message}"
            if final is None:
                return "", "[错误] 未获得回答"
            data = final.data if isinstance(final.data, dict) else {}
            if data.get("routed_mode") == "agent":
                side = "### 执行过程\n" + "\n".join(steps) if steps else ""
                return final.message or "", (route_line + "\n\n" + side).strip()
            if data.get("kind") == "meta":
                return format_meta_overview(data.get("meta") or {}), route_line
            side = format_rag_side({"sources": data.get("sources", []), "web_sources": data.get("web_sources", [])})
            return final.message or "", (route_line + "\n\n" + side).strip()

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

    def _load_history(session_id: str) -> List[Dict[str, Any]]:
        try:
            history = service.chat_history(session_id or None)
        except Exception:  # noqa: BLE001
            history = []
        history = list(history) if isinstance(history, list) else []
        # "携带摘要"新建的会话：把承接的背景作为一条可折叠的说明放在最前面，
        # 让用户看得见模型"记得"什么（它不是本会话的真实对话）。
        carried = _carried_summary(session_id)
        if carried:
            history.insert(0, {
                "role": "assistant",
                "content": carried,
                "metadata": {"title": CARRIED_TITLE},
            })
        return history

    def _carried_summary(session_id: str) -> str:
        try:
            return str(service.carried_summary(session_id or None) or "").strip()
        except Exception:  # noqa: BLE001
            return ""

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

        yield 八元组 ``(history, status_md, process_md, sources_md, hint_md, confirm_md, retry_md, sources_open)``：

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
          「允许 / 拒绝」按钮），用户决定后或任务继续推进时回到空串；
        - ``retry_md``：RAG 回答 ``kind="fallback"``（知识库无相关片段且网络无结果）
          时的提示文案，非空时 UI 显示「用单 Agent 重试」按钮（切模式并用同一问题重发）；
        - ``sources_open``：「📎 引用来源」Accordion 的 ``gr.update``——仅最终帧且引用校验
          发现无效编号时为 ``gr.update(open=True)``，其余一律 ``gr.update()``（不改变用户
          当前折叠状态）（F9 P0-3）。

        RAG 回答的警示 / 引用校验等结构化 ``notices``（F9 P0-5）以 blockquote 渲染：
        ``before`` 组置于气泡正文前（与 ``> 🔗 已理解为`` 同款），``after`` 组置于正文后；
        ``code=="fallback"`` 不入气泡（沿用 retry 行）。

        三种模式（RAG / 单 Agent / 多 Agent）统一走服务层带心跳与取消的事件流，
        并绑定到 ``session_id``（每个浏览器标签页自己的会话）。多 Agent 可指定
        ``collab_mode``（hierarchy/parallel/sequential/competitive，空为自动）。

        「自动」模式（默认）：服务层 ``chat_auto_stream`` 先判定意图再分发到 RAG /
        单 Agent，``answer.data["routed_mode"]`` 决定渲染路径（RAG 来源面板 / Agent
        执行摘要），状态行追加「· 实际模式：RAG 检索|单 Agent」；用户手动选其他模式
        时不判定。
        """
        message = (message or "").strip()
        session_id = (session_id or "").strip()
        if not session_id:
            # 标签页尚未完成会话绑定（如 app.load 未返回就发送）：先钉死到一个具体
            # 会话，整轮对话都用它，避免中途"当前会话"指针被其他标签页改掉。
            try:
                session_id = service.ensure_session()
            except Exception:  # noqa: BLE001
                session_id = ""
        history = _load_history(session_id)
        if not message:
            yield history, "_请输入内容_", "", "", "", "", "", _noop()
            return

        if service.is_running() is True:
            yield history, "⚠️ 已有任务在运行，请先等待完成或点击「停止」", "", "", "", "", "", _noop()
            return

        activity, hint = _startup_hint()
        tracker = ProgressTracker(hint=hint)
        tracker.current = activity

        history = history + [{"role": "user", "content": message}]

        # 立即反馈：点击后马上出现，消除"无响应"错觉
        yield history, tracker.render_status(), "", "", "", "", "", _noop()

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
        elif mode == MODE_AUTO:
            # 自动路由（F8 P3-3）：服务层先判定意图再分发；answer.data["routed_mode"] 决定渲染路径
            stream = service.chat_auto_stream(
                message, enable_web_search=enable_web, auto_confirm=auto_confirm,
                session_id=session_id or None, interactive_confirm=True,
            )
            title = "处理过程"
        else:
            stream = service.rag_query_stream(
                message, enable_web_search=enable_web, session_id=session_id or None
            )
            title = "处理过程"

        final = None
        confirm_md = ""
        # F10 P1-1：token 事件逐段拼接为"正在生成"的助手气泡；answer 到达后以完整文本替换
        partial = ""

        def live_history() -> List[Dict[str, Any]]:
            return history + [{"role": "assistant", "content": partial}] if partial else history

        for evt in stream:
            if evt.kind == "token":
                tracker.current = "✍️ 生成回答中…"
                partial += evt.message or ""
                yield live_history(), tracker.render_status(), tracker.render_steps(title), "", "", "", "", _noop()
            elif evt.kind == "confirm":
                confirm_md = format_confirm_request(evt.data if isinstance(evt.data, dict) else {})
                tracker.current = "⏸️ 等待你确认危险操作…"
                yield live_history(), tracker.render_status(), tracker.render_steps(title), "", "", confirm_md, "", _noop()
            elif evt.kind in ("progress", "step"):
                confirm_md = ""
                data = evt.data if isinstance(evt.data, dict) else None
                if partial and _starts_new_round(evt.kind, data):
                    partial = ""  # 上一轮的半截 Final Answer 被工具调用推翻，清掉重来
                if partial and data and data.get("transient"):
                    # 正在逐字输出时，推理心跳不再覆盖「✍️ 生成回答中…」状态
                    yield live_history(), tracker.render_status(), tracker.render_steps(title), "", "", "", "", _noop()
                    continue
                tracker.add(evt.message, data)
                yield live_history(), tracker.render_status(), tracker.render_steps(title), "", "", "", "", _noop()
            elif evt.kind == "heartbeat":
                yield live_history(), tracker.render_status(), tracker.render_steps(title), "", "", confirm_md, "", _noop()
            elif evt.kind == "answer":
                final = evt
            elif evt.kind == "cancelled":
                # 已流出的部分答案保留在气泡里并注明已停止，用户能看到中断前的内容
                if partial:
                    partial = partial.rstrip() + "\n\n> ⏹️ 已停止，以上为中断前的部分回答"
                yield (
                    live_history(), tracker.render_status("cancelled"),
                    tracker.render_steps(title, done=True), "", "", "", "",
                    _noop(),
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
                    "",
                    _noop(),
                )
                return

        steps_md = tracker.render_steps(title, done=True)
        if final is None:
            yield history, tracker.render_status("error", "未获得回答"), steps_md, "", "", "", "", _noop()
            return

        data = final.data if isinstance(final.data, dict) else {}
        ctx = data.get("context") if isinstance(data.get("context"), dict) else {}
        status = tracker.render_status("done")
        # 自动模式：状态行追加实际模式，并按 routed_mode 切换到对应渲染路径
        render_mode = mode
        if mode == MODE_AUTO:
            routed = data.get("routed_mode") or "rag"
            render_mode = "单 Agent" if routed == "agent" else "RAG 检索"
            status = f"{status} · 实际模式：{render_mode}"
        status = with_context_status(status, ctx)

        # 健康度提示：每会话只提示一次（展示后即标记）
        hint_md = format_suggest_hint(ctx)
        if hint_md:
            service.mark_suggested(session_id or None)

        # 追问被改写为独立问题时，在回答前注明"已理解为"
        prefix = ""
        rewritten = data.get("rewritten")
        if rewritten:
            # F9 P1-2：质疑类追问复用同一 blockquote，文案改为「重新核对」
            label = "🔁 用户质疑，重新核对" if data.get("challenge") else "🔗 已理解为"
            prefix = f"> {label}：{rewritten}\n\n"

        if mode == "多 Agent 协作":
            content = prefix + format_multi_agent_result(data)
            yield history + [{"role": "assistant", "content": content}], status, steps_md, "", hint_md, "", "", _noop()
            return

        if render_mode == "单 Agent":
            content = prefix + (final.message or "")
            summary = format_step_log(data.get("step_log") or [])
            if summary:
                steps_md = f"{steps_md}\n\n{summary}" if steps_md else summary
            yield history + [{"role": "assistant", "content": content}], status, steps_md, "", hint_md, "", "", _noop()
            return

        if data.get("kind") == "meta":
            content = format_meta_overview(data.get("meta") or {})
            yield history + [{"role": "assistant", "content": content}], status, steps_md, "", hint_md, "", "", _noop()
            return
        # 失败回退：知识库与网络均无结果 → 状态行下方出现「用单 Agent 重试」按钮
        retry_q = ""
        if data.get("kind") == "fallback":
            retry_q = format_fallback_hint(data.get("fallback_question") or message)
        # F9 P0-5 / P0-3：结构化提示以 blockquote 包裹正文；状态行追加引用校验计数；
        # 有无效引用时自动展开「📎 引用来源」
        notices = data.get("notices") or []
        check = data.get("citation_check")
        cite = format_citation_status(check)
        if cite:
            status = f"{status} · {cite}"
        content = prefix + format_notices(notices, "before") + (final.message or "") + format_notices(notices, "after")
        sources_open = component_update(open=True) if (isinstance(check, dict) and check.get("invalid")) else _noop()
        yield (
            history + [{"role": "assistant", "content": content}],
            status,
            steps_md,
            format_rag_side(
                {
                    "sources": data.get("sources", []),
                    "web_sources": data.get("web_sources", []),
                    "citation_check": check,
                }
            ),
            hint_md,
            "",
            retry_q,
            sources_open,
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
    ) -> Tuple[List[Tuple[str, str]], str, List[Dict[str, Any]], str, str, str]:
        """新建会话（可选携带摘要）：返回 (下拉选项, 新会话 id, 历史, 上下文状态, 清空的提示, 状态行文案)。

        「携带摘要」只承接上一会话**已折叠的滚动摘要**；上一会话没有摘要时新会话
        完全干净，状态行会明确说明，避免用户误以为带了上下文。
        """
        sid = service.create_session(
            None, carry_summary=bool(carry_summary),
            from_session_id=(from_session_id or "").strip() or None,
        )
        if not carry_summary:
            status = "✨ 已新建会话"
        elif _carried_summary(sid):
            status = "✨ 已新建会话（已承接上一会话的滚动摘要，见对话区顶部说明）"
        else:
            status = "✨ 已新建会话（上一会话尚无滚动摘要，未承接任何内容）"
        return service.session_choices(), sid, _load_history(sid), _context_status(sid), "", status

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

    def on_stop() -> str:
        """停止当前任务（任一模式）。返回写入状态行的文案。"""
        return "⏹️ 已发送停止信号，正在中止…" if service.stop_agent() else "当前没有运行中的任务"

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

    def on_collab_choices() -> List[Tuple[str, str]]:
        return service.collaboration_modes()

    return {
        "on_chat": on_chat,
        "on_chat_stream": on_chat_stream,
        "on_resolve_confirm": on_resolve_confirm,
        "on_session_init": on_session_init,
        "on_session_select": on_session_select,
        "on_new_session": on_new_session,
        "on_clear_context": on_clear_context,
        "on_compact_context": on_compact_context,
        "on_continue_session": on_continue_session,
        "on_list_sessions": on_list_sessions,
        "on_sessions_refresh": on_sessions_refresh,
        "on_create_session": on_create_session,
        "on_switch_session": on_switch_session,
        "on_delete_session": on_delete_session,
        "on_archive_session": on_archive_session,
        "on_search_sessions": on_search_sessions,
        "on_stop": on_stop,
        "on_session_list_state": on_session_list_state,
        "on_session_filter": on_session_filter,
        "on_session_info": on_session_info,
        "on_sidebar_archive": on_sidebar_archive,
        "on_sidebar_delete": on_sidebar_delete,
        "on_collab_choices": on_collab_choices,
    }
