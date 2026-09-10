"""Gradio 界面组装（薄 UI 层）。

本模块只负责：把各页面的处理器组合成一个 dict（``build_handlers``）、组装 Gradio Blocks
（``build_app``）与启动 / 优雅关闭（``launch`` / ``serve_blocking``）。业务逻辑全部在
``web.services``，纯格式化函数在 ``web.formatters``，各页面处理器在 ``web.handlers``
（F10 P2-2 拆包）。本模块重导出 ``formatters`` 的全部名字，``from web.app import format_*``
等旧路径保持可用。真正调用 gradio 的 ``build_app`` / ``launch`` 标注 ``pragma: no cover``。
"""
from __future__ import annotations

from typing import Callable, Dict, Optional

from .formatters import (  # noqa: F401 - 重导出：保持拆包前 ``web.app`` 的公开名
    MODE_AUTO,
    CARRY_PREFIX,
    format_context_status,
    format_suggest_hint,
    format_tokens,
    CARRIED_TITLE,
    format_elapsed,
    ProgressTracker,
    _fmt_result,
    component_update,
    _noop,
    _starts_new_round,
    format_notices,
    format_citation_status,
    format_sources,
    format_web_sources,
    format_fallback_hint,
    format_meta_overview,
    format_rag_side,
    format_stats,
    _hybrid_disabled_text,
    format_model_status,
    format_model_chip,
    format_switch_result,
    format_multi_agent_result,
    _SESSION_STATUS_ICON,
    _md_cell,
    format_sessions,
    format_context_metrics,
    with_context_status,
    format_step_log,
    _RISK_LABEL,
    format_confirm_request,
    format_exec_analysis,
    format_kv_table,
    format_session_info,
    format_file_info,
    _DIR_LIST_MAX_SHOWN,
    _fmt_dir_list,
    format_env_info,
    _fmt_concurrency,
    format_stats_cards,
    _html_escape,
    format_git_cards,
    GIT_CHANGES_HEADERS,
    GIT_COMMITS_HEADERS,
    GIT_AUTHORS_HEADERS,
    git_changes_rows,
    git_commits_rows,
    git_authors_rows,
    format_git_payload,
    GIT_STAGED_HEADERS,
    git_staged_rows,
    format_git_commit_preview,
    format_db_status,
    DB_TABLES_HEADERS,
    DB_SCHEMA_HEADERS,
    db_tables_rows,
    db_schema_rows,
    format_db_query_status,
    format_db_execute_status,
    format_db_payload,
    SEND_TO_CHAT_MAX,
    format_send_to_chat,
    SYMBOL_HEADERS,
    QUALITY_ISSUE_HEADERS,
    _SEVERITY_LABEL,
    symbol_rows,
    format_symbols_status,
    format_symbols_payload,
    format_quality_cards,
    quality_issue_rows,
    format_quality_payload,
    DIR_HEADERS,
    SEARCH_HEADERS,
    _LANGUAGE_BY_SUFFIX,
    _LANGUAGE_BY_NAME,
    guess_code_language,
    format_size,
    dir_rows,
    abbreviate_home,
    format_dir_breadcrumb,
    join_entry,
    search_rows,
    format_file_preview_status,
    format_file_payload,
    format_graph_result,
    format_file_delete_prompt,
    format_file_action_bar,
    _SNAPSHOT_TRIGGER_LABEL,
    format_snapshot_info,
    snapshot_doc_rows,
    format_restore_result,
    format_prune_preview,
    GRAPH_TYPE_COLORS,
    GRAPH_EDGE_COLOR,
    GRAPH_EDGE_LABEL_COLOR,
    _node_size,
    _hover_docs,
    build_graph_figure,
    format_graph_view_stats,
    format_graph_summary_cards,
)
from .handlers import (
    build_chat_handlers,
    build_graph_handlers,
    build_knowledge_handlers,
    build_system_handlers,
    build_tools_handlers,
)
from .services import WebService, get_web_service


# ==================== UI 处理器工厂（可测试）====================

def build_handlers(service: WebService) -> Dict[str, Callable]:
    """构造绑定到 service 的 UI 处理器集合（五个页面的处理器合并为一个 dict）。

    处理器返回值均为已格式化的字符串/数据，供 Gradio 组件直接展示。
    这些处理器不依赖 gradio，可独立单元测试。``headers`` 键为各表格的表头表。
    """
    handlers: Dict[str, Callable] = {}
    headers: Dict[str, list] = {}
    for build in (
        build_chat_handlers,
        build_knowledge_handlers,
        build_tools_handlers,
        build_graph_handlers,
        build_system_handlers,
    ):
        part = build(service)
        headers.update(part.pop("headers", {}) or {})
        handlers.update(part)
    handlers["headers"] = headers
    return handlers


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
