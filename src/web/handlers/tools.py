"""工具页处理器：Git / 数据库 / AI 解读 / 代码助手 / 符号与质量 / NL→SQL / 工作区浏览 / 命令生成 / Shell 与文件。"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from ..formatters import (
    DB_SCHEMA_HEADERS,
    DB_TABLES_HEADERS,
    DIR_HEADERS,
    GIT_AUTHORS_HEADERS,
    GIT_CHANGES_HEADERS,
    GIT_COMMITS_HEADERS,
    GIT_STAGED_HEADERS,
    ProgressTracker,
    QUALITY_ISSUE_HEADERS,
    SEARCH_HEADERS,
    SYMBOL_HEADERS,
    _fmt_result,
    abbreviate_home,
    db_schema_rows,
    db_tables_rows,
    dir_rows,
    format_db_execute_status,
    format_db_payload,
    format_db_query_status,
    format_db_status,
    format_dir_breadcrumb,
    format_elapsed,
    format_exec_analysis,
    format_file_payload,
    format_file_preview_status,
    format_git_cards,
    format_git_commit_preview,
    format_git_payload,
    format_quality_cards,
    format_quality_payload,
    format_send_to_chat,
    format_symbols_payload,
    format_symbols_status,
    git_authors_rows,
    git_changes_rows,
    git_commits_rows,
    git_staged_rows,
    guess_code_language,
    join_entry,
    quality_issue_rows,
    search_rows,
    symbol_rows,
)
from ..services import WebService


def build_tools_handlers(service: WebService) -> Dict[str, Any]:
    """工具页处理器：Git / 数据库 / AI 解读 / 代码助手 / 符号与质量 / NL→SQL / 工作区浏览 / 命令生成 / Shell 与文件（由 ``app.build_handlers`` 汇总）。"""

    def on_git_commit_preview() -> Tuple[str, List[List[Any]], bool]:
        """暂存区预览：返回 (卡片 / 提示 HTML, 暂存文件行, 是否有暂存)。"""
        pv = service.git_commit_preview()
        return format_git_commit_preview(pv), git_staged_rows(pv), bool(pv.get("has_staged"))

    def on_git_commit_gen() -> Tuple[str, List[List[Any]], str, str]:
        """「AI 生成提交信息」：先取暂存预览，再生成；返回 (预览 HTML, 暂存行, 可编辑的提交信息, 提示行)。

        无暂存时不调用模型，提交信息留空并在提示行说明。
        """
        html, rows, has_staged = on_git_commit_preview()
        if not has_staged:
            return html, rows, "", "💡 暂存区为空，请先 `git add`"
        result = service.git_commit_message()
        if result.get("error"):
            return html, rows, "", f"❌ {result['error']}"
        return html, rows, str(result.get("message") or ""), "✅ 已生成，可编辑后点「提交」"

    def on_git_commit(message: str) -> str:
        """确认后提交（``git commit -m``）；UI 负责 ``shell_enable`` 门控与 ``Confirm``。"""
        return _fmt_result(service.git_commit(message))

    def on_git_overview() -> Tuple[str, List[List[Any]], List[List[Any]], List[List[Any]], str]:
        """Git 仪表盘：返回 (卡片 HTML, 变更文件行, 最近提交行, 提交者行, 解读用纯文本)。"""
        ov = service.git_overview()
        return (format_git_cards(ov), git_changes_rows(ov), git_commits_rows(ov), git_authors_rows(ov),
                format_git_payload(ov))

    def on_db_status() -> str:
        return format_db_status(service.db_current())

    def on_db_tables() -> List[List[Any]]:
        return db_tables_rows(service.db_tables())

    def on_db_connect(database: str) -> Tuple[str, str, List[List[Any]]]:
        """连接：返回 (结果文案, 状态芯片 HTML, 表列表行)。"""
        msg = _fmt_result(service.db_connect(database))
        return msg, on_db_status(), on_db_tables()

    def on_recent_databases() -> List[str]:
        """连接区下拉的候选：``:memory:`` 恒在首位 + 最近成功连接过的库（F9 P3-1）。"""
        recent = [d for d in service.recent_databases() if d and d != ":memory:"]
        return [":memory:", *recent]

    def on_shell_history() -> List[str]:
        """命令区「历史命令」下拉候选（最新在前，F9 P3-2）。"""
        return list(service.shell_history())

    def on_db_disconnect() -> Tuple[str, str, List[List[Any]]]:
        msg = _fmt_result(service.db_disconnect())
        return msg, on_db_status(), []

    def on_db_table_schema(table: str) -> Tuple[str, List[List[Any]]]:
        """点选表 → (标题文案, 列 / 类型 / 约束 行)。"""
        table = (table or "").strip()
        if not table:
            return "", []
        schema = service.db_table_schema(table)
        if schema.get("error"):
            return f"❌ {schema['error']}", []
        return f"**{table}** · {len(schema.get('columns') or [])} 列", db_schema_rows(schema)

    def on_db_query(sql: str) -> Tuple[str, List[str], List[List[Any]]]:
        """查询：返回 (状态行, 表头, 行)。"""
        result = service.db_query(sql)
        return format_db_query_status(result), list(result.get("columns") or []), list(result.get("rows") or [])

    def on_db_execute(sql: str) -> Tuple[str, List[List[Any]]]:
        """写操作（调用方已确认）：返回 (状态行, 刷新后的表列表行)。"""
        result = service.db_execute(sql)
        return format_db_execute_status(result), on_db_tables()

    def on_db_payload(sql: str, headers: List[str], rows: List[List[Any]]) -> str:
        """把当前查询与表格内容压成解读用文本（UI 在查询后调用）。"""
        return format_db_payload({"sql": sql, "columns": headers or [], "rows": rows or [],
                                  "row_count": len(rows or [])})

    def on_ai_explain(kind: str, payload: str, question: str = ""):
        """「用 AI 解读」：流式 yield Markdown（心跳期显示已用时；answer 直接展示）。"""
        tracker = ProgressTracker()
        yield "⏳ 思考中…"
        for evt in service.ai_explain_stream(kind, payload, question):
            if evt.kind in ("progress", "heartbeat"):
                yield f"⏳ 思考中… {format_elapsed(tracker.elapsed())}"
            elif evt.kind == "answer":
                yield evt.message
            elif evt.kind == "error":
                yield f"❌ {evt.message}"
                return
            elif evt.kind == "cancelled":
                yield "⏹️ 已停止"
                return

    def on_send_to_chat(tab: str, payload: str) -> str:
        """「发送到对话」：返回填入对话输入框的文本（空结果返回空串，UI 据此不跳转）。"""
        return format_send_to_chat(tab, payload)

    # ---------- 工具页 P2-1：代码助手 / 符号表 / 质量报告 ----------

    def on_code_assist(action: str, path: str, extra: str = ""):
        """代码助手（流式）：yield ``(处理过程 Markdown, 结果 Markdown)``。"""
        tracker = ProgressTracker()
        label = WebService.CODE_ASSIST_ACTIONS.get(action, action)
        yield tracker.render_status(), f"⏳ 正在{label}…"
        for evt in service.code_assist_stream(action, path, extra):
            if evt.kind == "step":
                tracker.add(evt.message, evt.data if isinstance(evt.data, dict) else None)
                yield _process_md(tracker), f"⏳ 正在{label}… {format_elapsed(tracker.elapsed())}"
            elif evt.kind in ("progress", "heartbeat"):
                yield _process_md(tracker), f"⏳ 正在{label}… {format_elapsed(tracker.elapsed())}"
            elif evt.kind == "answer":
                yield _process_md(tracker, done=True), evt.message
            elif evt.kind == "error":
                yield _process_md(tracker, state="error", detail=evt.message), f"❌ {evt.message}"
                return
            elif evt.kind == "cancelled":
                yield _process_md(tracker, state="cancelled"), "⏹️ 已停止"
                return

    def _process_md(tracker: ProgressTracker, done: bool = False, state: str = "", detail: str = "") -> str:
        status = tracker.render_status("done" if done else (state or "running"), detail)
        steps = tracker.render_steps(done=done)
        return f"{status}\n\n{steps}" if steps else status

    def on_code_symbols(pattern: str, path: str, search_by: str = "name") -> Tuple[str, List[List[Any]], str]:
        """符号搜索：返回 (状态行, 表格行, 解读用文本)。"""
        data = service.code_symbols(pattern, path or ".", search_by or "name")
        return format_symbols_status(data), symbol_rows(data), format_symbols_payload(pattern, data)

    def on_code_quality_report(path: str) -> Tuple[str, List[List[Any]], str]:
        """质量检查：返回 (卡片 HTML, 问题表行, 解读用文本)。"""
        report = service.code_quality_report(path or ".")
        return format_quality_cards(report), quality_issue_rows(report), format_quality_payload(report)

    # ---------- 工具页 P2-2：自然语言 → SQL ----------

    def on_db_connected() -> bool:
        return bool((service.db_current() or {}).get("connected"))

    def on_sql_kind(sql: str) -> Tuple[bool, bool]:
        """按 SQL 首关键字判定 (可直接运行, 需确认)；空 / 不可识别均为 (False, False)。"""
        kind = WebService.sql_kind(sql)
        return kind == "select", kind == "write"

    def on_db_nl2sql(question: str) -> Tuple[str, str, bool, bool]:
        """自然语言 → SQL：返回 (SQL 文本, 提示行, 可直接运行, 需确认)。"""
        result = service.db_nl2sql(question)
        sql = str(result.get("sql") or "")
        kind = result.get("kind") or "invalid"
        note = str(result.get("note") or "")
        if kind == "invalid":
            return sql, f"❌ {note or '未生成可用 SQL'}", False, False
        hint = f"💡 {note}" if note else ("✅ 已生成只读查询，可直接运行" if kind == "select" else "")
        return sql, hint, kind == "select", kind == "write"

    # ---------- 工具页 P2-3：工作区文件浏览 ----------

    def on_list_dir(path: str, show_hidden: bool = False) -> Tuple[str, List[List[Any]], str]:
        """列目录：返回 (面包屑, 表格行, 解析后的路径（主目录缩写为 ``~``）)。出错时路径保持原值。"""
        listing = service.list_dir(path or ".", bool(show_hidden))
        resolved = abbreviate_home(listing.get("path", path)) if not listing.get("error") else (path or ".")
        return format_dir_breadcrumb(listing), dir_rows(listing), resolved

    def on_dir_parent(path: str, show_hidden: bool = False) -> Tuple[str, List[List[Any]], str]:
        listing = service.list_dir(path or ".", bool(show_hidden))
        parent = listing.get("parent") or path or "."
        return on_list_dir(parent, show_hidden)

    def on_file_preview(path: str, page: float = 0) -> Tuple[str, Optional[str], str, int, str]:
        """文件预览：返回 (内容, 语言, 状态行, 页码, 解读用文本)。"""
        preview = service.file_preview(path, int(page or 0))
        content = preview.get("content", "") if not preview.get("error") else ""
        return (content, guess_code_language(path), format_file_preview_status(preview),
                int(preview.get("page", 0) or 0), format_file_payload(preview))

    FILE_EDIT_MAX_LINES = 2000

    def on_file_edit_load(path: str) -> Tuple[str, str]:
        """打开「编辑」：返回 (编辑框初始内容, 提示行)。

        新文件 / 不存在：内容空、提示"保存将创建新文件"；超过 ``FILE_EDIT_MAX_LINES`` 行不加载全文并提示用「追加」。
        """
        path = (path or "").strip()
        if not path:
            return "", "💡 先在左侧选择文件，或在上方输入新文件路径"
        preview = service.file_preview(path, 0, FILE_EDIT_MAX_LINES)
        if preview.get("error"):
            err = str(preview["error"])
            if "路径超出允许范围" in err:  # 写边界 ⊆ 读边界：保存同样会被拒，不要暗示"可新建"
                return "", f"❌ {err}"
            return "", f"💡 {err} · 保存将创建新文件"
        if int(preview.get("pages", 1) or 1) > 1:
            return "", (f"⚠️ 文件超过 {FILE_EDIT_MAX_LINES} 行，编辑框未加载全文；"
                        "覆盖保存会替换整个文件，建议勾选「追加」")
        return str(preview.get("content") or ""), ""

    def on_dir_search(query: str, path: str) -> Tuple[str, List[List[Any]]]:
        """关键词搜索：返回 (状态行, 表格行)。"""
        query = (query or "").strip()
        if not query:
            return "", []
        scope_err = service.path_read_error(path or ".")
        if scope_err:  # search_in_dir 没有 error 槽位：越界必须在这里可见，不能伪装成"未找到"
            return f"❌ {scope_err}", []
        results = service.search_in_dir(query, path or ".")
        if not results:
            return f"💡 未找到包含「{query}」的文件", []
        cap = WebService.SEARCH_MAX_RESULTS
        more = f"（仅显示前 {cap} 条）" if len(results) >= cap else ""
        return f"✅ 找到 {len(results)} 处匹配{more}", search_rows(results)

    # ---------- 工具页 P2-4：自然语言 → 命令 ----------

    def on_shell_generate(intent: str) -> Tuple[str, str]:
        """生成命令：返回 (命令文本, 提示行)。未生成时命令为空。"""
        result = service.shell_generate(intent)
        cmd = str(result.get("command") or "")
        note = str(result.get("note") or "")
        if not cmd:
            return "", f"❌ {note or '未生成'}"
        return cmd, "✅ 已生成命令，请检查后点「分析」→「执行」"

    # ---------- 工具：Shell / 文件读写 / 工作目录 ----------

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

    def on_write_file(path: str, content: str, append: bool = False) -> str:
        return _fmt_result(service.write_file(path, content, bool(append)))

    def on_cwd() -> str:
        return f"当前工作目录：`{service.cwd()}`"

    def on_chdir(path: str) -> Tuple[str, str]:
        """切换工作目录：返回 (结果, 当前目录文案)。"""
        return _fmt_result(service.chdir(path)), on_cwd()

    return {
        "on_git_commit_preview": on_git_commit_preview,
        "on_git_commit_gen": on_git_commit_gen,
        "on_git_commit": on_git_commit,
        "on_git_overview": on_git_overview,
        "on_db_status": on_db_status,
        "on_db_tables": on_db_tables,
        "on_db_connect": on_db_connect,
        "on_recent_databases": on_recent_databases,
        "on_shell_history": on_shell_history,
        "on_db_disconnect": on_db_disconnect,
        "on_db_table_schema": on_db_table_schema,
        "on_db_query": on_db_query,
        "on_db_execute": on_db_execute,
        "on_db_payload": on_db_payload,
        "on_ai_explain": on_ai_explain,
        "on_send_to_chat": on_send_to_chat,
        "on_code_assist": on_code_assist,
        "on_code_symbols": on_code_symbols,
        "on_code_quality_report": on_code_quality_report,
        "on_db_connected": on_db_connected,
        "on_sql_kind": on_sql_kind,
        "on_db_nl2sql": on_db_nl2sql,
        "on_list_dir": on_list_dir,
        "on_dir_parent": on_dir_parent,
        "on_file_preview": on_file_preview,
        "on_file_edit_load": on_file_edit_load,
        "on_dir_search": on_dir_search,
        "on_shell_generate": on_shell_generate,
        "on_exec_analyze": on_exec_analyze,
        "on_exec_run": on_exec_run,
        "on_write_file": on_write_file,
        "on_cwd": on_cwd,
        "on_chdir": on_chdir,
        "join_entry": join_entry,
        "abbreviate_home": abbreviate_home,
        "headers": {
            "git_changes": GIT_CHANGES_HEADERS,
            "git_commits": GIT_COMMITS_HEADERS,
            "git_authors": GIT_AUTHORS_HEADERS,
            "git_staged": GIT_STAGED_HEADERS,
            "db_tables": DB_TABLES_HEADERS,
            "db_schema": DB_SCHEMA_HEADERS,
            "symbols": SYMBOL_HEADERS,
            "quality_issues": QUALITY_ISSUE_HEADERS,
            "dir": DIR_HEADERS,
            "search": SEARCH_HEADERS,
        },
    }
