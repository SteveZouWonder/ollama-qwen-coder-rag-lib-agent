#!/usr/bin/env python3
"""
CLI 命令处理器 —— 兼容重导出（F10 P2-2 起实现位于 ``cli.handlers`` 包）。

``from cli_handlers import COMMAND_HANDLERS, CLIContext, handle_multi, ...`` 等旧路径保持可用；
新代码请直接 ``from cli.handlers import ...``。若需打桩模块级依赖（如 ``_git_overview``、
``_db_results``、``_get_session_manager``），请以实际所在子模块为目标
（``cli.handlers.git`` / ``cli.handlers.db`` / ``cli.handlers.session``）。
"""
from __future__ import annotations

from cli.handlers import *  # noqa: F401,F403
from cli.handlers import (  # noqa: F401 - 下划线名不会被 * 导出，显式列出
    _is_error,
    _confirm,
    _sql_safety,
    _MULTI_MODES,
    _default_orchestrator,
    _make_ingest_progress,
    _require_knowledge_management,
    _get_session_manager,
    _get_conversation_context,
    _parse_session_new_args,
    _GRAPH_QUERY_PREFIXES,
    _print_graph_query_usage,
    _get_graph_builder,
    _GIT_ANALYSIS_TYPES,
    _rich_table,
    _git_overview,
    _print_git_overview,
    _print_git_status,
    _print_git_authors,
    _print_git_plain,
    _DB_TYPES,
    _DB_NOT_CONNECTED_HINT,
    _db_results,
    _cell,
)
