"""结构化取数（Web 工具页与 CLI ``/db-*`` 共用，F9 P1-4 / P3-5）。

所有函数都以 ``QueryExecutor``（或 ``None`` 表示未连接）为输入、返回可直接渲染的 ``dict``，
不做任何展示层假设：Web 用它填 ``gr.Dataframe``，CLI 用它画 rich ``Table``。
列表内容为 ``list``（非 ``QueryResult`` 的 ``dict`` 行），便于表格化。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

NOT_CONNECTED = "尚未连接数据库，请先连接"

READ_PREFIXES = ("select", "with", "pragma", "explain", "values")
WRITE_PREFIXES = ("insert", "update", "delete", "create", "drop", "alter", "replace", "truncate")

DEFAULT_MAX_ROWS = 500


def sql_head(sql: str) -> str:
    """去掉前导 ``--`` 行注释与左括号后的首个关键字（小写）；无内容返回空串。"""
    lines = [ln for ln in (sql or "").splitlines() if ln.strip() and not ln.strip().startswith("--")]
    body = "\n".join(lines).strip().lstrip("(")
    return body.split(None, 1)[0].lower() if body.split() else ""


def sql_kind(sql: str) -> str:
    """按首个关键字判定 ``select`` / ``write`` / ``invalid``（空串 / 仅注释亦为 invalid）。"""
    head = sql_head(sql)
    if head in READ_PREFIXES:
        return "select"
    if head in WRITE_PREFIXES:
        return "write"
    return "invalid"


def query_structured(executor, sql: str, max_rows: int = DEFAULT_MAX_ROWS) -> Dict[str, Any]:
    """只读查询 → ``{sql, columns, rows(list of list), row_count, execution_time, truncated, error?}``。

    ``rows`` 最多 ``max_rows`` 行（``truncated`` 标记是否截断）；非 SELECT 类语句拒绝并提示改用「执行」。
    """
    sql = (sql or "").strip()
    base: Dict[str, Any] = {"sql": sql, "columns": [], "rows": [], "row_count": 0,
                            "execution_time": 0.0, "truncated": False}
    head = sql_head(sql)
    if not sql or not head:
        return {**base, "error": "请输入 SQL 查询语句"}
    if head not in READ_PREFIXES:
        return {**base, "error": "「查询」只接受 SELECT 等只读语句；写操作请使用「执行」"}
    if executor is None:
        return {**base, "error": NOT_CONNECTED}
    try:
        result = executor.execute_query(sql)
    except BaseException as exc:  # noqa: BLE001
        return {**base, "error": str(exc)}
    if not result.success:
        return {**base, "execution_time": result.execution_time, "error": result.error_message or "查询失败"}
    columns = list(result.columns)
    max_rows = max(int(max_rows or 0), 0) or DEFAULT_MAX_ROWS
    rows = [[r.get(c) for c in columns] for r in result.rows[:max_rows]]
    return {
        **base, "columns": columns, "rows": rows, "row_count": result.row_count,
        "execution_time": result.execution_time, "truncated": result.row_count > len(rows),
    }


def execute_structured(executor, sql: str) -> Dict[str, Any]:
    """写语句 → ``{sql, affected_rows, execution_time, error?}``（调用方负责确认）。"""
    sql = (sql or "").strip()
    base: Dict[str, Any] = {"sql": sql, "affected_rows": 0, "execution_time": 0.0}
    if not sql:
        return {**base, "error": "请输入 SQL 语句"}
    if executor is None:
        return {**base, "error": NOT_CONNECTED}
    try:
        result = executor.execute_update(sql)
    except BaseException as exc:  # noqa: BLE001
        return {**base, "error": str(exc)}
    if not result.success:
        return {**base, "execution_time": result.execution_time, "error": result.error_message or "执行失败"}
    return {**base, "affected_rows": int(result.affected_rows), "execution_time": result.execution_time}


def tables_structured(executor) -> Dict[str, Any]:
    """表名列表 → ``{tables: [...], error?}``。"""
    if executor is None:
        return {"tables": [], "error": NOT_CONNECTED}
    try:
        return {"tables": list(executor.list_tables())}
    except BaseException as exc:  # noqa: BLE001
        return {"tables": [], "error": str(exc)}


def table_schema_structured(executor, table: str) -> Dict[str, Any]:
    """单表结构 → ``{table, columns: [{name, type, not_null, default_value, primary_key}], error?}``。"""
    table = (table or "").strip()
    if not table:
        return {"table": "", "columns": [], "error": "请选择表"}
    if executor is None:
        return {"table": table, "columns": [], "error": NOT_CONNECTED}
    try:
        schema = executor.get_table_schema(table) or {}
    except BaseException as exc:  # noqa: BLE001
        return {"table": table, "columns": [], "error": str(exc)}
    columns = list(schema.get("columns") or [])
    if not columns:
        return {"table": table, "columns": [], "error": f"表 {table} 不存在或没有列"}
    return {"table": table, "columns": columns}


def constraint_label(column: Dict[str, Any]) -> str:
    """列约束的一行标签：``PK · NOT NULL · DEFAULT x``（Web 表格与 CLI 表格共用）。"""
    cons: List[str] = []
    if column.get("primary_key"):
        cons.append("PK")
    if column.get("not_null"):
        cons.append("NOT NULL")
    if column.get("default_value") not in (None, ""):
        cons.append(f"DEFAULT {column.get('default_value')}")
    return " · ".join(cons)


def schema_rows(schema: Dict[str, Any]) -> List[List[Any]]:
    """``table_schema_structured`` 结果 → ``[[列, 类型, 约束], ...]``。"""
    return [[c.get("name", ""), c.get("type", "") or "—", constraint_label(c)]
            for c in (schema or {}).get("columns") or []]


def current_executor() -> Optional[Any]:
    """当前连接的 ``QueryExecutor``；未连接返回 ``None``。"""
    from . import session
    from .query_executor import QueryExecutor

    connector = session.current_connector()
    return QueryExecutor(connector) if connector is not None else None
