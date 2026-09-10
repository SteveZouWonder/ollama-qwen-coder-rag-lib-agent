"""CLI 命令处理器包（F10 P2-2 由 ``src/cli_handlers.py`` 拆分）。

设计要点（沿用 F7）：
  - 每个 handler 形如 ``handle_xxx(ctx, parsed) -> bool``，返回值表示
    "命令处理完成后是否显示命令推荐"。
  - 共享状态（console、rag_engine、react_engine、HAS_RICH、记录函数等）经由
    ``CLIContext`` 注入，handler 不依赖 query_interface 的模块级全局变量。
  - ``COMMAND_HANDLERS``（cmd_type -> handler）驱动调度，由本模块汇总各子模块。

子模块：``base``（CLIContext / 确认 / LiveAnswer）、``agent``（/multi）、``system``
（/help /tutorial /tools /config）、``knowledge``（/stats /add /snapshot-* …）、``files``
（/file-*）、``session``（/session-* /context /compact）、``tools``（/web-* /code-* /graph-*）、
``git``（/git-*）、``db``（/db-*）。顶层 ``cli_handlers`` 模块保留为兼容重导出。
"""
from __future__ import annotations

from typing import Any, Callable

from .base import (  # noqa: F401
    CLIContext,
    _is_error,
    _confirm,
    _sql_safety,
    LiveAnswer,
)
from .agent import (  # noqa: F401
    _MULTI_MODES,
    parse_multi_args,
    _default_orchestrator,
    handle_multi,
)
from .system import (  # noqa: F401
    handle_help,
    handle_tutorial,
    handle_tools,
    config_rows,
    handle_config,
)
from .knowledge import (  # noqa: F401
    handle_stats,
    handle_sources,
    _make_ingest_progress,
    handle_add,
    _require_knowledge_management,
    handle_generate_skills,
    handle_snapshot_list,
    handle_snapshot_create,
    handle_snapshot_restore,
    handle_snapshot_info,
    handle_snapshot_delete,
    handle_snapshot_prune,
    handle_knowledge_summary,
)
from .files import (  # noqa: F401
    handle_file_list,
    handle_file_info,
    handle_file_delete,
    handle_file_stats,
    handle_file_cleanup,
    handle_file_deduplicate,
)
from .session import (  # noqa: F401
    _get_session_manager,
    _get_conversation_context,
    _parse_session_new_args,
    handle_session_new,
    handle_context,
    handle_compact,
    handle_session_list,
    handle_session_switch,
    handle_session_current,
    handle_session_info,
    handle_session_search,
    handle_session_compress,
    handle_session_delete,
    handle_session_archive,
)
from .tools import (  # noqa: F401
    handle_web_search,
    handle_web_cache,
    handle_web_extract,
    handle_code_ast,
    handle_code_quality,
    _GRAPH_QUERY_PREFIXES,
    _print_graph_query_usage,
    handle_graph_query,
    handle_graph_build,
    _get_graph_builder,
    handle_graph_summary,
    parse_graph_export_args,
    handle_graph_export,
)
from .git import (  # noqa: F401
    _GIT_ANALYSIS_TYPES,
    GIT_ANALYZE_MAX_COMMITS,
    _rich_table,
    _git_overview,
    _print_git_overview,
    _print_git_status,
    _print_git_authors,
    _print_git_plain,
    handle_git_analyze,
    handle_git_commit_gen,
)
from .db import (  # noqa: F401
    _DB_TYPES,
    handle_db_connect,
    DB_QUERY_MAX_ROWS,
    _DB_NOT_CONNECTED_HINT,
    _db_results,
    _cell,
    handle_db_query,
    handle_db_execute,
    handle_db_create_table,
    handle_db_insert,
    handle_db_schema,
)


# ==================== 命令表 ====================
# cmd_type -> handler。仅包含“自包含”命令；与引擎/主循环状态强耦合的命令
# （ask / agent / natural / clear / history / summary / reset / file / write /
# exec / pwd / cd / model / quit）仍由 query_interface.main() 直接处理。

COMMAND_HANDLERS: dict[str, Callable[[CLIContext, Any], bool]] = {
    "help": handle_help,
    "tutorial": handle_tutorial,
    "multi": handle_multi,
    "tools": handle_tools,
    "config": handle_config,
    "stats": handle_stats,
    "sources": handle_sources,
    "add": handle_add,
    "generate_skills": handle_generate_skills,
    "snapshot_list": handle_snapshot_list,
    "snapshot_create": handle_snapshot_create,
    "snapshot_restore": handle_snapshot_restore,
    "snapshot_info": handle_snapshot_info,
    "snapshot_delete": handle_snapshot_delete,
    "snapshot_prune": handle_snapshot_prune,
    "knowledge_summary": handle_knowledge_summary,
    "file_list": handle_file_list,
    "file_info": handle_file_info,
    "file_delete": handle_file_delete,
    "file_stats": handle_file_stats,
    "file_cleanup": handle_file_cleanup,
    "file_deduplicate": handle_file_deduplicate,
    "session_new": handle_session_new,
    "context": handle_context,
    "compact": handle_compact,
    "session_list": handle_session_list,
    "session_switch": handle_session_switch,
    "session_current": handle_session_current,
    "session_info": handle_session_info,
    "session_search": handle_session_search,
    "session_compress": handle_session_compress,
    "session_delete": handle_session_delete,
    "session_archive": handle_session_archive,
    "web_search": handle_web_search,
    "web_cache": handle_web_cache,
    "web_extract": handle_web_extract,
    "code_ast": handle_code_ast,
    "code_quality": handle_code_quality,
    "graph_query": handle_graph_query,
    "graph_build": handle_graph_build,
    "graph_summary": handle_graph_summary,
    "graph_export": handle_graph_export,
    "git_analyze": handle_git_analyze,
    "git_commit_gen": handle_git_commit_gen,
    "db_connect": handle_db_connect,
    "db_query": handle_db_query,
    "db_execute": handle_db_execute,
    "db_create_table": handle_db_create_table,
    "db_insert": handle_db_insert,
    "db_schema": handle_db_schema,
}
