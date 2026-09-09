"""CLI 命令路由（纯函数，可单元测试；F10 P2-2 由 ``query_interface`` 抽出）。

``parse_command`` 把用户输入解析为 ``ParsedCommand``，``classify_mode`` 按知识库可用性
决定处理模式（``rag`` / ``agent`` / ``cmd`` / ``noop``）。``query_interface`` 重导出三者。
"""
from __future__ import annotations


class ParsedCommand:
    """解析后的命令对象"""
    def __init__(self, cmd_type: str, raw: str, arg: str = ""):
        self.cmd_type = cmd_type
        self.raw = raw
        self.arg = arg

    def __repr__(self):
        return f"ParsedCommand({self.cmd_type!r}, arg={self.arg!r})"

    def __eq__(self, other):
        if not isinstance(other, ParsedCommand):
            return False
        return self.cmd_type == other.cmd_type and self.arg == other.arg


def parse_command(user_input: str) -> ParsedCommand:
    """
    将用户输入解析为命令类型和参数。
    纯函数，无外部依赖，可完全单元测试。
    """
    user_input = user_input.strip()
    if not user_input:
        return ParsedCommand("empty", user_input)

    # 退出命令
    if user_input in ("/exit", "/quit", "exit", "quit"):
        return ParsedCommand("quit", user_input)

    # 无参数命令
    if user_input == "/help":
        return ParsedCommand("help", user_input)
    if user_input == "/tutorial":
        return ParsedCommand("tutorial", user_input)
    if user_input == "/tools":
        return ParsedCommand("tools", user_input)
    if user_input == "/config":
        return ParsedCommand("config", user_input)
    if user_input == "/stats":
        return ParsedCommand("stats", user_input)
    if user_input == "/sources":
        return ParsedCommand("sources", user_input)
    if user_input == "/clear":
        return ParsedCommand("clear", user_input)
    if user_input == "/history":
        return ParsedCommand("history", user_input)
    if user_input == "/summary":
        return ParsedCommand("summary", user_input)
    if user_input == "/reset":
        return ParsedCommand("reset", user_input)
    if user_input == "/context":
        return ParsedCommand("context", user_input)
    if user_input == "/compact":
        return ParsedCommand("compact", user_input)
    if user_input == "/pwd":
        return ParsedCommand("pwd", user_input)
    if user_input == "/model":
        return ParsedCommand("model", user_input)
    if user_input == "/think":
        return ParsedCommand("think", user_input)
    if user_input == "/auto":
        return ParsedCommand("auto", user_input)

    # 带参数命令（至少一个空格分隔）
    parts = user_input.split(None, 1)
    cmd = parts[0]
    arg = parts[1] if len(parts) > 1 else ""

    if cmd == "/ask":
        return ParsedCommand("ask", user_input, arg)
    if cmd == "/agent":
        return ParsedCommand("agent", user_input, arg)
    if cmd == "/multi":
        # /multi <任务> [--mode hierarchy|parallel|sequential|competitive]
        return ParsedCommand("multi", user_input, arg)
    if cmd == "/model":
        # /model <name> 运行时热切换；/model list 列出可选模型
        return ParsedCommand("model", user_input, arg)
    if cmd == "/think":
        # /think on|off 运行时开关思考模式
        return ParsedCommand("think", user_input, arg)
    if cmd == "/auto":
        # /auto on|off 运行时开关入口自动路由
        return ParsedCommand("auto", user_input, arg)
    if cmd == "/add":
        return ParsedCommand("add", user_input, arg)
    if cmd == "/file":
        return ParsedCommand("file", user_input, arg)
    
    # 知识库管理命令
    if cmd == "/generate-skills":
        return ParsedCommand("generate_skills", user_input, arg)
    if cmd == "/snapshot-list":
        return ParsedCommand("snapshot_list", user_input, arg)
    if cmd == "/snapshot-create":
        return ParsedCommand("snapshot_create", user_input, arg)
    if cmd == "/snapshot-restore":
        return ParsedCommand("snapshot_restore", user_input, arg)
    if cmd == "/snapshot-info":
        return ParsedCommand("snapshot_info", user_input, arg)
    if cmd == "/snapshot-delete":
        return ParsedCommand("snapshot_delete", user_input, arg)
    if cmd == "/snapshot-prune":
        return ParsedCommand("snapshot_prune", user_input, arg)
    if cmd == "/knowledge-summary":
        return ParsedCommand("knowledge_summary", user_input, arg)
    
    # 知识图谱管理命令
    if cmd == "/graph-query":
        return ParsedCommand("graph_query", user_input, arg)
    if cmd == "/graph-build":
        return ParsedCommand("graph_build", user_input, arg)
    if cmd == "/graph-summary":
        return ParsedCommand("graph_summary", user_input, arg)
    if cmd == "/graph-export":
        return ParsedCommand("graph_export", user_input, arg)
    
    # 数据库管理命令
    if cmd == "/db-connect":
        return ParsedCommand("db_connect", user_input, arg)
    if cmd == "/db-query":
        return ParsedCommand("db_query", user_input, arg)
    if cmd == "/db-execute":
        return ParsedCommand("db_execute", user_input, arg)
    if cmd == "/db-create-table":
        return ParsedCommand("db_create_table", user_input, arg)
    if cmd == "/db-insert":
        return ParsedCommand("db_insert", user_input, arg)
    if cmd == "/db-schema":
        return ParsedCommand("db_schema", user_input, arg)

    # 文件管理命令
    if cmd == "/file-list":
        return ParsedCommand("file_list", user_input, arg)
    if cmd == "/file-info":
        return ParsedCommand("file_info", user_input, arg)
    if cmd == "/file-cleanup":
        return ParsedCommand("file_cleanup", user_input, arg)
    if cmd == "/file-deduplicate":
        return ParsedCommand("file_deduplicate", user_input, arg)
    if cmd == "/file-stats":
        return ParsedCommand("file_stats", user_input, arg)
    if cmd == "/file-delete":
        return ParsedCommand("file_delete", user_input, arg)

    # 会话管理命令
    if cmd == "/session-new":
        return ParsedCommand("session_new", user_input, arg)
    if cmd == "/session-list":
        return ParsedCommand("session_list", user_input, arg)
    if cmd == "/session-switch":
        return ParsedCommand("session_switch", user_input, arg)
    if cmd == "/session-archive":
        return ParsedCommand("session_archive", user_input, arg)
    if cmd == "/session-delete":
        return ParsedCommand("session_delete", user_input, arg)
    if cmd == "/session-info":
        return ParsedCommand("session_info", user_input, arg)
    if cmd == "/session-search":
        return ParsedCommand("session_search", user_input, arg)
    if cmd == "/session-current":
        return ParsedCommand("session_current", user_input, arg)
    if cmd == "/session-compress":
        return ParsedCommand("session_compress", user_input, arg)

    # 网络搜索命令
    if cmd == "/web-search":
        return ParsedCommand("web_search", user_input, arg)
    if cmd == "/web-cache":
        return ParsedCommand("web_cache", user_input, arg)
    if cmd == "/web-extract":
        return ParsedCommand("web_extract", user_input, arg)

    # 代码分析命令
    if cmd == "/code-ast":
        return ParsedCommand("code_ast", user_input, arg)
    if cmd == "/code-quality":
        return ParsedCommand("code_quality", user_input, arg)

    # Git 命令
    if cmd == "/git-analyze":
        return ParsedCommand("git_analyze", user_input, arg)
    if cmd == "/git-commit-gen":
        return ParsedCommand("git_commit_gen", user_input, arg)


    if cmd == "/write":
        return ParsedCommand("write", user_input, arg)
    if cmd == "/exec":
        return ParsedCommand("exec", user_input, arg)
    if cmd == "/cd":
        return ParsedCommand("cd", user_input, arg)

    # 默认：未识别的命令或自然语言输入
    if user_input.startswith("/"):
        return ParsedCommand("unknown_cmd", user_input, arg)
    return ParsedCommand("natural", user_input, user_input)


def classify_mode(rag_engine_available: bool, parsed: ParsedCommand) -> str:
    """
    根据知识库可用性和解析结果，决定处理模式。
    返回: "rag" | "agent" | "cmd" | "noop"
    """
    cmd_type = parsed.cmd_type

    # 纯命令，不走任何引擎
    if cmd_type in ("help", "tutorial", "tools", "config", "stats", "sources",
                     "clear", "history", "summary", "reset", "context", "compact",
                     "pwd", "cd", "model", "think", "auto", "quit", "empty", "unknown_cmd",
                     "generate_skills", "snapshot_list", "snapshot_create",
                     "snapshot_restore", "snapshot_info", "snapshot_delete", "snapshot_prune",
                     "knowledge_summary",
                     "graph_query", "graph_build", "graph_summary", "graph_export",
                     "db_connect", "db_query", "db_execute",
                     "db_create_table", "db_insert", "db_schema",
                     "file_list", "file_info", "file_cleanup", "file_deduplicate", "file_stats",
                     "file_delete",
                     "session_new", "session_list", "session_switch", "session_archive",
                     "session_delete", "session_info", "session_search", "session_current",
                     "session_compress", "web_search", "web_cache", "web_extract",
                     "code_ast", "code_quality", "git_analyze", "git_commit_gen",
                     "graph_query", "graph_build", "multi"):
        return "cmd"

    # 明确指定 RAG
    if cmd_type == "ask":
        return "rag"
    if cmd_type == "add":
        return "rag"

    # 明确指定 Agent
    if cmd_type == "agent":
        return "agent"
    if cmd_type in ("file", "write", "exec"):
        return "agent"

    # 自然语言输入：有知识库走 RAG，否则提示
    if cmd_type == "natural":
        if rag_engine_available:
            return "rag"
        return "agent"  # 无知识库时，让 Agent 尝试处理

    return "noop"
