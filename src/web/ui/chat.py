"""对话页：模式分段 + 聊天区 + 审批卡片 + 输入区 + 右侧面板（上下文 / 处理过程 / 来源）。"""  # pragma: no cover
from __future__ import annotations

from typing import Any, Callable, Dict

import gradio as gr

from .common import Confirm

MODE_RAG = "RAG 检索"
MODE_AGENT = "单 Agent"
MODE_MULTI = "多 Agent 协作"

EXAMPLES = [
    {"text": "知识库里有哪些文档？"},
    {"text": "总结一下知识库的核心内容"},
    {"text": "最新的 Python 稳定版本是什么？"},
]


def _placeholder(service) -> str:
    try:
        total = int((service.get_stats() or {}).get("total_documents", 0) or 0)
    except Exception:  # noqa: BLE001
        total = 0
    if total <= 0:
        return (
            "### 👋 欢迎使用 Cerebro\n\n"
            "知识库还是空的。你可以：\n\n"
            "1. 到左侧「📚 知识库」上传文档或追加目录；\n"
            "2. 直接提问——「RAG 检索」模式勾选联网后可搜索网络；\n"
            "3. 切到「单 Agent」让它读写文件、执行命令完成任务。"
        )
    return (
        f"### 开始对话\n\n知识库已有 **{total}** 个片段。输入问题即可检索，支持追问（如“它多少钱”）。\n\n"
        "切换上方模式可让 Agent 调用工具，或让多个 Agent 协作处理复杂任务。"
    )


def build_chat_page(service, handlers: Dict[str, Callable], sb: Dict[str, Any]) -> Dict[str, Any]:  # pragma: no cover
    session_state = sb["session_state"]
    session_radio = sb["session_radio"]

    # ---- 顶部：模式分段 + 协作模式 + 上下文胶囊 ----
    with gr.Row(elem_classes=["cb-toolbar"]):
        mode = gr.Radio(
            [MODE_RAG, MODE_AGENT, MODE_MULTI], value=MODE_RAG, show_label=False,
            container=False, elem_classes=["cb-segment"], scale=0, min_width=360,
        )
        collab_dd = gr.Dropdown(
            choices=handlers["on_collab_choices"](), value="", show_label=False, container=False,
            visible=False, scale=0, min_width=200, interactive=True,
        )
        context_chip = gr.Markdown(elem_classes=["cb-status", "cb-muted"], scale=1)

    with gr.Row(equal_height=False):
        # ---- 左：聊天区 ----
        with gr.Column(scale=7, min_width=420):
            chatbot = gr.Chatbot(
                elem_id="chatbot", show_label=False, height="calc(100vh - 400px)",
                min_height=320, resizable=True, placeholder=_placeholder(service),
                examples=EXAMPLES, buttons=["copy"],
            )
            with gr.Row(visible=False, elem_classes=["cb-approval"]) as approval_row:
                approval_md = gr.Markdown(scale=1)
                allow_btn = gr.Button("允许", variant="primary", size="sm", elem_classes=["cb-btn"], min_width=80)
                deny_btn = gr.Button("拒绝", variant="stop", size="sm", elem_classes=["cb-btn"], min_width=80)

            with gr.Group(elem_classes=["cb-composer"]):
                msg_box = gr.Textbox(
                    placeholder="输入你的问题…（Enter 发送，Shift+Enter 换行）",
                    show_label=False, lines=1, max_lines=6, autofocus=True, container=False,
                )
                with gr.Row(elem_classes=["cb-composer-bar"]):
                    with gr.Row(scale=1, elem_classes=["cb-composer-toggles"]):
                        enable_web = gr.Checkbox(
                            value=True, label="联网搜索增强", container=False, scale=0, min_width=0,
                        )
                        auto_confirm = gr.Checkbox(
                            value=False, label="自动确认危险操作（等价 --yes）", container=False, scale=0,
                            min_width=0, visible=False,
                        )
                    with gr.Row(scale=0, elem_classes=["cb-composer-actions"]):
                        stop_btn = gr.Button("停止", scale=0, min_width=88, interactive=False, elem_classes=["cb-btn"])
                        send_btn = gr.Button("发送", scale=0, min_width=110, variant="primary", elem_classes=["cb-btn"])

            status_box = gr.Markdown(elem_classes=["cb-status"])
            with gr.Row(visible=False, elem_classes=["cb-hint"]) as hint_row:
                hint_box = gr.Markdown(scale=1)
                hint_new_btn = gr.Button("新建会话", size="sm", elem_classes=["cb-btn"], min_width=90)
                hint_continue_btn = gr.Button("继续当前会话", size="sm", elem_classes=["cb-btn"], min_width=110)

        # ---- 右：侧面板 ----
        with gr.Column(scale=3, min_width=280, elem_classes=["cb-side-panel"]):
            with gr.Accordion("🧠 上下文", open=True):
                context_box = gr.Markdown(elem_classes=["cb-status"])
                with gr.Row(elem_classes=["cb-inline-actions"]):
                    compact_btn = gr.Button("压缩历史", size="sm", elem_classes=["cb-btn"], min_width=90)
                    clear_confirm = Confirm(
                        "清空上下文", "清空该会话的全部消息与摘要？", size="sm", min_width=110,
                    )
            with gr.Accordion("⚙️ 处理过程", open=True):
                process_box = gr.Markdown(elem_classes=["cb-result"])
            with gr.Accordion("📎 引用来源 / 结果明细", open=False):
                sources_box = gr.Markdown(elem_classes=["cb-result"])
            with gr.Accordion("ℹ️ 会话详情", open=False):
                session_info_md = gr.Markdown(elem_classes=["cb-kv"])
                info_refresh_btn = gr.Button("刷新", size="sm", elem_classes=["cb-btn"], min_width=70)

    # ================== 事件 ==================

    # 模式切换：只显示与当前模式相关的开关
    def _mode_changed(m):
        return (
            gr.update(visible=(m == MODE_RAG)),
            gr.update(visible=(m == MODE_AGENT)),
            gr.update(visible=(m == MODE_MULTI)),
        )

    mode.change(_mode_changed, mode, [enable_web, auto_confirm, collab_dd], show_progress="hidden")

    def _ctx_chip(ctx_md: str) -> str:
        first = (ctx_md or "").split("\n", 1)[0]
        return first

    # ---- 发送链：暂存 → 流式 → 收尾 ----
    pending_msg = gr.State("")
    _chat_outputs = [
        chatbot, status_box, process_box, sources_box, hint_box, hint_row, approval_md, approval_row,
    ]

    def _chat_stream_ui(message, mode_v, web_v, confirm_v, sid, collab_v):
        for history, status, process, sources, hint, confirm in handlers["on_chat_stream"](
            message, mode_v, web_v, confirm_v, sid, collab_v
        ):
            yield (
                history, status, process, sources, hint, gr.update(visible=bool(hint)),
                confirm, gr.update(visible=bool(confirm)),
            )

    def _begin(message: str):
        return message, "", gr.update(interactive=False), gr.update(interactive=True)

    def _end(sid):
        ctx_md = handlers["on_session_select"](sid)[2]
        choices, sid2 = handlers["on_session_list_state"](sid)
        return (
            gr.update(interactive=True), gr.update(interactive=False), ctx_md, _ctx_chip(ctx_md),
            gr.update(choices=choices, value=sid2 or None), gr.update(visible=False),
        )

    _begin_outputs = [pending_msg, msg_box, send_btn, stop_btn]
    _chat_inputs = [pending_msg, mode, enable_web, auto_confirm, session_state, collab_dd]
    _end_outputs = [send_btn, stop_btn, context_box, context_chip, session_radio, approval_row]

    send_chain = send_btn.click(_begin, msg_box, _begin_outputs).then(
        _chat_stream_ui, _chat_inputs, _chat_outputs
    )
    send_chain.then(_end, session_state, _end_outputs)
    submit_chain = msg_box.submit(_begin, msg_box, _begin_outputs).then(
        _chat_stream_ui, _chat_inputs, _chat_outputs
    )
    submit_chain.then(_end, session_state, _end_outputs)

    # 空态示例：点击即发送
    def _example_text(evt: gr.SelectData):
        value = evt.value
        return value.get("text", "") if isinstance(value, dict) else str(value or "")

    example_chain = (
        chatbot.example_select(_example_text, None, msg_box)
        .then(_begin, msg_box, _begin_outputs)
        .then(_chat_stream_ui, _chat_inputs, _chat_outputs)
    )
    example_chain.then(_end, session_state, _end_outputs)

    stop_btn.click(
        handlers["on_stop"], None, status_box,
        cancels=[send_chain, submit_chain, example_chain],
    ).then(_end, session_state, _end_outputs)

    # 审批卡片
    allow_btn.click(lambda: handlers["on_resolve_confirm"](True), None, status_box).then(
        lambda: gr.update(visible=False), None, approval_row, show_progress="hidden",
    )
    deny_btn.click(lambda: handlers["on_resolve_confirm"](False), None, status_box).then(
        lambda: gr.update(visible=False), None, approval_row, show_progress="hidden",
    )

    # ---- 会话：初始化 / 切换 / 新建 / 清空 / 压缩 ----
    def _init():
        choices, sid, history, ctx_md = handlers["on_session_init"]()
        return (
            gr.update(choices=choices, value=sid), sid, history, ctx_md, _ctx_chip(ctx_md),
            handlers["on_session_info"](sid),
        )

    init_outputs = [session_radio, session_state, chatbot, context_box, context_chip, session_info_md]

    def _load_session(sid):
        new_sid, history, ctx_md, hint = handlers["on_session_select"](sid)
        return (
            new_sid, history, ctx_md, _ctx_chip(ctx_md), hint, gr.update(visible=False),
            handlers["on_session_info"](new_sid), "",
        )

    load_outputs = [session_state, chatbot, context_box, context_chip, hint_box, hint_row, session_info_md, status_box]
    session_radio.input(_load_session, session_radio, load_outputs)

    def _new_session(carry, sid):
        choices, new_sid, history, ctx_md, hint = handlers["on_new_session"](carry, sid)
        return (
            gr.update(choices=choices, value=new_sid), new_sid, history, ctx_md, _ctx_chip(ctx_md),
            hint, gr.update(visible=False),
            "✨ 已新建会话" + ("（已携带摘要）" if carry else ""),
            handlers["on_session_info"](new_sid),
        )

    _new_outputs = [
        session_radio, session_state, chatbot, context_box, context_chip, hint_box, hint_row,
        status_box, session_info_md,
    ]
    sb["new_session_btn"].click(_new_session, [sb["carry_cb"], session_state], _new_outputs)
    hint_new_btn.click(_new_session, [sb["carry_cb"], session_state], _new_outputs)

    def _clear_ctx(sid):
        history, msg, ctx_md, hint = handlers["on_clear_context"](sid)
        return history, msg, ctx_md, _ctx_chip(ctx_md), hint, gr.update(visible=False)

    clear_confirm.bind(
        _clear_ctx, session_state, [chatbot, status_box, context_box, context_chip, hint_box, hint_row],
    )

    def _compact(sid):
        msg, ctx_md = handlers["on_compact_context"](sid)
        return msg, ctx_md, _ctx_chip(ctx_md)

    compact_btn.click(_compact, session_state, [status_box, context_box, context_chip])

    def _continue(sid):
        handlers["on_continue_session"](sid)
        return "", gr.update(visible=False)

    hint_continue_btn.click(_continue, session_state, [hint_box, hint_row])
    info_refresh_btn.click(handlers["on_session_info"], session_state, session_info_md)

    return {
        "init": _init, "init_outputs": init_outputs,
        "load_session": _load_session, "load_outputs": load_outputs,
        "chatbot": chatbot, "status_box": status_box,
    }
