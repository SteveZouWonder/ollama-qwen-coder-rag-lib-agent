"""数据库管理命令：``/db-connect`` ``/db-query`` ``/db-execute`` ``/db-create-table`` ``/db-insert`` ``/db-schema``。"""
from __future__ import annotations

import json
import logging

from .base import _confirm, _sql_safety
from .git import _rich_table

logger = logging.getLogger(__name__)


# ==================== 数据库管理命令 ====================

# database_connect 支持的类型名（用于区分 ``/db-connect sqlite`` 与 ``/db-connect <path>``）
_DB_TYPES = {"sqlite", "mysql", "postgresql", "mssql"}


def handle_db_connect(ctx, parsed):
    """连接数据库并设为当前连接：``/db-connect <database>``（默认 sqlite）或 ``/db-connect <type> <database>``。"""
    console = ctx.console
    args = parsed.arg.strip().split() if parsed.arg.strip() else []
    if not args or (len(args) == 1 and args[0].lower() in _DB_TYPES):
        console.print(
            "❌ 请提供数据库路径: /db-connect <database>（默认 sqlite；也可 /db-connect sqlite <database>）",
            style="yellow",
        )
        return False
    if len(args) == 1:
        db_type, database = "sqlite", args[0]
    else:
        db_type, database = args[0], args[1]
    try:
        console.print(f"🔗 正在连接数据库: {db_type} @ {database}", style="cyan")
        result = ctx.registry.execute("database_connect", {"db_type": db_type, "database": database})
        if result.startswith("[错误]"):
            console.print(result, style="red")
            return False
        console.print(result, style="green")
        console.print("💡 之后的 /db-query /db-execute /db-schema 将自动作用于该库", style="dim")
        ctx.record_command("db_connect", f"{db_type} {database}")
    except Exception as e:  # noqa: BLE001
        console.print(f"❌ 数据库连接失败: {e}", style="red")
        ctx.record_command("db_connect", f"{db_type} {database}", "failed", str(e))
    return True


DB_QUERY_MAX_ROWS = 50
"""``/db-query`` 表格最多显示的行数（超出提示 ``…共 N 行``）。"""

_DB_NOT_CONNECTED_HINT = "尚未连接数据库：先 /db-connect <path>（如 /db-connect ./data/app.db）"


def _db_results():
    """共享层结构化取数模块（与 Web 工具页同一实现）。"""
    from database_tools import results

    return results


def _cell(value) -> str:
    return "NULL" if value is None else str(value)


def handle_db_query(ctx, parsed):
    """``/db-query <sql>``：在当前连接上执行只读查询，rich 表格显示（F9 P3-5）。"""
    console = ctx.console
    sql = parsed.arg.strip()
    if not sql:
        console.print("❌ 请提供SQL查询语句: /db-query <sql>", style="yellow")
        return False
    try:
        results = _db_results()
        executor = results.current_executor()
        if executor is None:
            console.print(_DB_NOT_CONNECTED_HINT, style="dim")
            return False
        data = results.query_structured(executor, sql, max_rows=DB_QUERY_MAX_ROWS)
        if data.get("error"):
            console.print(f"❌ {data['error']}", style="red")
            ctx.record_command("db_query", sql[:50], "failed", data["error"])
            return False
        columns, rows = data.get("columns") or [], data.get("rows") or []
        total, took = int(data.get("row_count", 0) or 0), float(data.get("execution_time", 0) or 0)
        if not rows:
            console.print(f"查询没有返回数据 · {took:.3f}s", style="dim")
        elif ctx.has_rich:
            table = _rich_table("查询结果", [(str(c), {"overflow": "fold"}) for c in columns])
            for r in rows:
                table.add_row(*[_cell(v) for v in r])
            console.print(table)
        else:
            console.print(" | ".join(map(str, columns)))
            for r in rows:
                console.print(" | ".join(_cell(v) for v in r))
        if rows:
            more = f"（仅显示前 {len(rows)} 行）…共 {total} 行" if data.get("truncated") else f"共 {total} 行"
            console.print(f"{more} · {took:.3f}s", style="dim")
        ctx.record_command("db_query", sql[:50])
    except Exception as e:  # noqa: BLE001
        console.print(f"❌ SQL查询失败: {e}", style="red")
        ctx.record_command("db_query", sql[:50], "failed", str(e))
    return True


def handle_db_execute(ctx, parsed):
    console = ctx.console
    sql = parsed.arg.strip()
    if not sql:
        console.print("❌ 请提供SQL语句: /db-execute <sql>", style="yellow")
        return False
    # database_execute 标记为 safe=False：用户显式发起的命令需先交互确认，
    # 再以 auto_confirm=True 执行，避免把内部协议串 [CONFIRM_REQUIRED] 打印给用户。
    # 风险分级复用共享层：DROP / TRUNCATE 判 high，AUTO_CONFIRM 下也仍需人工确认。
    if not _confirm(console, f"确认执行写操作? {sql[:80]} (y/n): ", safety=_sql_safety(sql)):
        console.print("[dim]已取消[/dim]")
        return False
    try:
        console.print("⚡ 正在执行SQL语句", style="cyan")
        result = ctx.registry.execute("database_execute", {"sql": sql}, auto_confirm=True)
        if result.startswith("[错误]"):
            console.print(result, style="red")
            return False
        console.print(result, style="green")
        ctx.record_command("db_execute", sql[:50])
    except Exception as e:  # noqa: BLE001
        console.print(f"❌ SQL执行失败: {e}", style="red")
        ctx.record_command("db_execute", sql[:50], "failed", str(e))
    return True


def handle_db_create_table(ctx, parsed):
    console = ctx.console
    args = parsed.arg.strip().split() if parsed.arg.strip() else []
    if len(args) < 1:
        console.print("❌ 请提供表名: /db-create-table <table> <columns_json>", style="yellow")
        return False
    table = args[0]
    columns_json = " ".join(args[1:]) if len(args) > 1 else "{}"
    try:
        columns = json.loads(columns_json)
    except json.JSONDecodeError:
        console.print("❌ 列定义必须是有效的JSON格式", style="yellow")
        return False
    if not _confirm(console, f"确认创建表 {table}? (y/n): "):
        console.print("[dim]已取消[/dim]")
        return False
    try:
        console.print(f"🔨 正在创建表: {table}", style="cyan")
        result = ctx.registry.execute(
            "database_create_table", {"table": table, "columns": columns}, auto_confirm=True
        )
        if result.startswith("[错误]"):
            console.print(result, style="red")
            return False
        console.print(result, style="green")
        ctx.record_command("db_create_table", table)
    except Exception as e:  # noqa: BLE001
        console.print(f"❌ 创建表失败: {e}", style="red")
        ctx.record_command("db_create_table", table, "failed", str(e))
    return True


def handle_db_insert(ctx, parsed):
    console = ctx.console
    args = parsed.arg.strip().split() if parsed.arg.strip() else []
    if len(args) < 1:
        console.print("❌ 请提供表名和数据: /db-insert <table> <data_json>", style="yellow")
        return False
    table = args[0]
    data_json = " ".join(args[1:]) if len(args) > 1 else "{}"
    try:
        data = json.loads(data_json)
    except json.JSONDecodeError:
        console.print("❌ 数据必须是有效的JSON格式", style="yellow")
        return False
    if not _confirm(console, f"确认向表 {table} 插入数据? (y/n): "):
        console.print("[dim]已取消[/dim]")
        return False
    try:
        console.print(f"➕ 正在插入数据到表: {table}", style="cyan")
        result = ctx.registry.execute("database_insert", {"table": table, "data": data}, auto_confirm=True)
        if result.startswith("[错误]"):
            console.print(result, style="red")
            return False
        console.print(result, style="green")
        ctx.record_command("db_insert", table)
    except Exception as e:  # noqa: BLE001
        console.print(f"❌ 插入数据失败: {e}", style="red")
        ctx.record_command("db_insert", table, "failed", str(e))
    return True


def handle_db_schema(ctx, parsed):
    """``/db-schema [table]``：有参 → 列 / 类型 / 约束 表；无参 → 当前库表名表（F9 P3-5）。"""
    console = ctx.console
    table = parsed.arg.strip()
    try:
        results = _db_results()
        executor = results.current_executor()
        if executor is None:
            console.print(_DB_NOT_CONNECTED_HINT, style="dim")
            return False
        if table:
            schema = results.table_schema_structured(executor, table)
            if schema.get("error"):
                console.print(f"❌ {schema['error']}", style="red")
                ctx.record_command("db_schema", table, "failed", schema["error"])
                return False
            rows = results.schema_rows(schema)
            if ctx.has_rich:
                t = _rich_table(f"表 {table} · {len(rows)} 列", [
                    ("列", {"style": "cyan", "no_wrap": True}), ("类型", {"style": "bold"}), ("约束", {"style": "dim"}),
                ])
                for r in rows:
                    t.add_row(*[str(v) for v in r])
                console.print(t)
            else:
                for r in rows:
                    console.print(f"  {r[0]}  {r[1]}  {r[2]}".rstrip())
        else:
            data = results.tables_structured(executor)
            if data.get("error"):
                console.print(f"❌ {data['error']}", style="red")
                ctx.record_command("db_schema", "(all)", "failed", data["error"])
                return False
            names = data.get("tables") or []
            if not names:
                console.print("数据库中没有表（可用 /db-execute CREATE TABLE … 建表）", style="dim")
            elif ctx.has_rich:
                t = _rich_table(f"共 {len(names)} 张表", [("表名", {"style": "cyan"})])
                for n in names:
                    t.add_row(str(n))
                console.print(t)
                console.print("💡 /db-schema <table> 查看列 / 类型 / 约束", style="dim")
            else:
                for n in names:
                    console.print(f"  - {n}")
        ctx.record_command("db_schema", table or "(all)")
    except Exception as e:  # noqa: BLE001
        console.print(f"❌ 获取表结构失败: {e}", style="red")
        ctx.record_command("db_schema", table or "(all)", "failed", str(e))
    return True
