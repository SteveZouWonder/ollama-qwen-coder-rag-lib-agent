"""整体骨架：顶栏 + 左侧栏（导航 / 会话）+ 主区五页 + 主题切换。"""  # pragma: no cover
from __future__ import annotations

from typing import Callable, Dict

import gradio as gr

from ..theme import DEFAULT_THEME, THEME_CHANGE_JS, THEME_LOAD_JS, normalize_theme, theme_choices
from .chat import build_chat_page
from .common import Confirm
from .graph import build_graph_page
from .knowledge import build_knowledge_page
from .system import build_system_page
from .tools import build_tools_page

NAV_CHAT = "💬  对话"
NAV_KB = "📚  知识库"
NAV_GRAPH = "🕸️  知识图谱"
NAV_TOOLS = "🧰  工具"
NAV_SYSTEM = "⚙️  系统"
NAV = [NAV_CHAT, NAV_KB, NAV_GRAPH, NAV_TOOLS, NAV_SYSTEM]


def build_layout(service, handlers: Dict[str, Callable]) -> gr.Blocks:  # pragma: no cover
    with gr.Blocks(title="Cerebro 🧠") as app:
        # ---------------- 顶栏 ----------------
        with gr.Row(elem_classes=["cb-header"]):
            gr.HTML(
                "<h1>Cerebro 🧠</h1><p>本地优先的 RAG + Agent 助手</p>",
                elem_classes=["cb-brand"], min_width=220, scale=3,
            )
            model_chip = gr.HTML(handlers["on_model_chip"](), scale=5, min_width=260)
            theme_dd = gr.Dropdown(
                choices=theme_choices(), value=DEFAULT_THEME, show_label=False, container=False,
                scale=0, min_width=128, elem_classes=["cb-theme-dd"], interactive=True,
            )

        # ---------------- 左侧栏：导航 + 会话 ----------------
        session_state = gr.State("")
        with gr.Sidebar(width=290, open=True):
            nav = gr.Radio(
                NAV, value=NAV_CHAT, show_label=False, container=False, elem_classes=["cb-nav"],
            )
            gr.HTML('<div class="cb-side-title"><h3>会话</h3></div>')
            session_search = gr.Textbox(
                placeholder="搜索会话标题 / 内容…", show_label=False, container=False, lines=1,
            )
            session_radio = gr.Radio(
                choices=[], value=None, show_label=False, container=False,
                elem_classes=["cb-session-list"],
            )
            with gr.Row(elem_classes=["cb-session-actions"]):
                new_session_btn = gr.Button("＋ 新建会话", size="sm", variant="primary")
                carry_cb = gr.Checkbox(value=False, label="携带摘要", container=False, scale=0, min_width=90)
            with gr.Row(elem_classes=["cb-session-actions"]):
                archive_btn = gr.Button("归档", size="sm")
                delete_confirm = Confirm("删除", "删除该会话？", size="sm", min_width=90)
            session_msg = gr.Markdown(elem_classes=["cb-status", "cb-muted"])

        sidebar = {
            "session_state": session_state, "session_radio": session_radio,
            "session_search": session_search, "new_session_btn": new_session_btn,
            "carry_cb": carry_cb, "archive_btn": archive_btn, "delete_confirm": delete_confirm,
            "session_msg": session_msg, "model_chip": model_chip,
        }

        # ---------------- 主区五页 ----------------
        with gr.Column(visible=True) as chat_col:
            chat = build_chat_page(service, handlers, sidebar)
        with gr.Column(visible=False) as kb_col:
            kb = build_knowledge_page(service, handlers)
        with gr.Column(visible=False) as graph_col:
            graph = build_graph_page(service, handlers)
        with gr.Column(visible=False) as tools_col:
            build_tools_page(service, handlers)
        with gr.Column(visible=False) as system_col:
            system = build_system_page(service, handlers, sidebar)

        cols = [chat_col, kb_col, graph_col, tools_col, system_col]

        def _switch(page: str):
            return [gr.update(visible=(page == n)) for n in NAV]

        nav.change(_switch, nav, cols, show_progress="hidden")
        # 进入知识库 / 系统页时刷新一次数据（避免陈旧）
        nav.change(
            lambda p: handlers["on_stats_cards"]() if p == NAV_KB else gr.update(),
            nav, kb["stats_cards"], show_progress="hidden",
        )
        nav.change(
            lambda p: kb["file_rows"]() if p == NAV_KB else (gr.update(), gr.update()),
            nav, [kb["file_table"], kb["file_paths"]], show_progress="hidden",
        )
        nav.change(
            lambda p: kb["snap_rows"]() if p == NAV_KB else gr.update(),
            nav, kb["snap_table"], show_progress="hidden",
        )
        # 进入知识图谱页时渲染一次图谱视图（惰性：不在启动时计算布局）
        nav.change(
            lambda p, *args: graph["render"](*args) if p == NAV_GRAPH else (gr.update(), gr.update(), gr.update()),
            [nav, *graph["inputs"]], graph["outputs"], show_progress="minimal",
        )
        nav.change(
            lambda p: handlers["on_env_info"]() if p == NAV_SYSTEM else gr.update(),
            nav, system["env_md"], show_progress="hidden",
        )

        # ---------------- 主题切换（应用 + 持久化）----------------
        theme_dd.change(None, theme_dd, None, js=THEME_CHANGE_JS, show_progress="hidden")
        app.load(normalize_theme, theme_dd, theme_dd, js=THEME_LOAD_JS, show_progress="hidden")

        # ---------------- 侧栏会话事件 ----------------
        def _sessions_refresh(sid):
            choices, sid = handlers["on_session_list_state"](sid)
            return gr.update(choices=choices, value=sid or None), sid

        session_search.change(
            lambda kw: gr.update(choices=handlers["on_session_filter"](kw)),
            session_search, session_radio, show_progress="hidden",
        )

        def _archive(sid):
            msg, choices, new_sid = handlers["on_sidebar_archive"](sid)
            return msg, gr.update(choices=choices, value=new_sid or None), new_sid

        archive_btn.click(_archive, session_state, [session_msg, session_radio, session_state])

        def _delete(sid):
            msg, choices, new_sid = handlers["on_sidebar_delete"](sid)
            return msg, gr.update(choices=choices, value=new_sid or None), new_sid

        delete_confirm.bind(_delete, session_state, [session_msg, session_radio, session_state]).then(
            chat["load_session"], session_state, chat["load_outputs"],
        )

        # 页面加载：初始化本标签页的会话绑定 + 聊天历史；文件表首次填充
        app.load(chat["init"], None, chat["init_outputs"])
        app.load(kb["file_rows"], None, [kb["file_table"], kb["file_paths"]], show_progress="hidden")

    return app
