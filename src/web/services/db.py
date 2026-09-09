"""工具页 · 数据库：SQLite 连接 / 查询 / 写操作 / 自然语言 → SQL。"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class DatabaseMixin:
    """数据库工具（「当前连接」由共享层 ``database_tools.session`` 维护，Web / CLI / Agent 共用）。"""

    # -- 数据库（SQLite；「当前连接」由共享层 database_tools.session 维护，Web / CLI / Agent 共用）--

    DB_MAX_ROWS = 500
    """查询结果最多返回的行数（超出部分截断并在 ``truncated`` 标记）。"""

    @staticmethod
    def _db_session():
        from database_tools import session as db_session

        return db_session

    @staticmethod
    def _db_results():
        """共享层结构化取数模块（Web 与 CLI ``/db-query`` ``/db-schema`` 共用）。"""
        from database_tools import results as db_results

        return db_results

    def db_current(self) -> Dict[str, Any]:
        """当前连接：``{connected, db_type, database, label}``。"""
        try:
            sess = self._db_session()
            cur = sess.get_current()
        except BaseException as exc:  # noqa: BLE001
            return {"connected": False, "db_type": "", "database": "", "label": "", "error": str(exc)}
        if not cur:
            return {"connected": False, "db_type": "", "database": "", "label": ""}
        return {"connected": True, "db_type": cur.get("db_type", ""), "database": cur.get("database", ""),
                "label": sess.describe(cur)}

    def _db_executor(self):
        """当前连接的 ``QueryExecutor``；未连接返回 None。"""
        from database_tools import QueryExecutor

        connector = self._db_session().current_connector()
        return QueryExecutor(connector) if connector is not None else None

    def db_connect(self, database: str, db_type: str = "sqlite") -> str:
        """连接 SQLite 库并设为当前连接（等价 CLI ``/db-connect <database>``）。"""
        database = (database or "").strip()
        if not database:
            return "[提示] 请输入 SQLite 数据库文件路径"
        result = self.run_tool("database_connect", {"db_type": (db_type or "sqlite").strip() or "sqlite",
                                                    "database": database})
        if result.startswith("[成功]"):
            try:
                self.tools_state.remember_database(database)
            except BaseException as exc:  # noqa: BLE001
                logger.warning("记录最近数据库失败: %s", exc)
        return result

    def db_disconnect(self) -> str:
        """断开当前连接（关闭缓存的连接器）。"""
        try:
            self._db_session().clear_current()
            return "[成功] 已断开当前连接"
        except BaseException as exc:  # noqa: BLE001
            return f"[错误] 断开失败: {exc}"

    def db_tables(self) -> Dict[str, Any]:
        """当前库的表名列表：``{tables: [...], error?}``（共享层 ``results.tables_structured``）。"""
        try:
            return self._db_results().tables_structured(self._db_executor())
        except BaseException as exc:  # noqa: BLE001
            return {"tables": [], "error": str(exc)}

    def db_table_schema(self, table: str) -> Dict[str, Any]:
        """单表结构：``{table, columns: [{name, type, not_null, default_value, primary_key}], error?}``。"""
        table = (table or "").strip()
        try:
            return self._db_results().table_schema_structured(self._db_executor() if table else None, table)
        except BaseException as exc:  # noqa: BLE001
            return {"table": table, "columns": [], "error": str(exc)}

    def db_query(self, sql: str) -> Dict[str, Any]:
        """在当前连接上执行只读查询，返回结构化结果（共享层 ``results.query_structured``）。

        ``{sql, columns, rows(list of list), row_count, execution_time, truncated, error?}``；
        ``rows`` 最多 ``DB_MAX_ROWS`` 行。非 SELECT 类语句提示改用「执行」。
        """
        results = self._db_results()
        sql = (sql or "").strip()
        head = results.sql_head(sql)
        if not sql or not head or head not in results.READ_PREFIXES:
            return results.query_structured(None, sql, self.DB_MAX_ROWS)  # 参数校验分支，不需要连接
        try:
            return results.query_structured(self._db_executor(), sql, self.DB_MAX_ROWS)
        except BaseException as exc:  # noqa: BLE001
            return {"sql": sql, "columns": [], "rows": [], "row_count": 0, "execution_time": 0.0,
                    "truncated": False, "error": str(exc)}

    def db_execute(self, sql: str) -> Dict[str, Any]:
        """在当前连接上执行写语句：``{sql, affected_rows, execution_time, error?}``（调用方负责确认）。"""
        results = self._db_results()
        sql = (sql or "").strip()
        if not sql:
            return results.execute_structured(None, sql)
        try:
            return results.execute_structured(self._db_executor(), sql)
        except BaseException as exc:  # noqa: BLE001
            return {"sql": sql, "affected_rows": 0, "execution_time": 0.0, "error": str(exc)}

    def db_schema(self, table: str = "") -> str:
        """文本版表结构 / 表列表（沿用 registry 工具，供 Agent 与旧调用方）。"""
        return self.run_tool("database_get_schema", {"table": (table or "").strip()})

    # -- 自然语言 → SQL（F9 P2-2）--

    DB_NL2SQL_NUM_PREDICT = 256
    DB_NL2SQL_SCHEMA_MAX = 3000

    @classmethod
    def _sql_head(cls, sql: str) -> str:
        """去掉前导 ``--`` 行注释与左括号后的首个关键字（小写）；无内容返回空串（共享层实现）。"""
        return cls._db_results().sql_head(sql)

    @classmethod
    def sql_kind(cls, sql: str) -> str:
        """按首个关键字判定 ``select`` / ``write`` / ``invalid``（空串 / 仅注释亦为 invalid）。"""
        return cls._db_results().sql_kind(sql)

    def db_schema_text(self, max_chars: Optional[int] = None) -> str:
        """当前库全部表的 ``CREATE``-风格文本（供 NL→SQL 提示），截 ``max_chars``。"""
        max_chars = max_chars or self.DB_NL2SQL_SCHEMA_MAX
        tables = self.db_tables().get("tables") or []
        lines: List[str] = []
        for t in tables:
            schema = self.db_table_schema(t)
            cols = ", ".join(
                f"{c.get('name', '')} {c.get('type', '') or ''}".strip() + (" PRIMARY KEY" if c.get("primary_key") else "")
                for c in schema.get("columns") or []
            )
            lines.append(f"{t}({cols})")
        text = "\n".join(lines)
        return text[:max_chars]

    @staticmethod
    def _strip_fences(text: str) -> str:
        """去掉 ``` 围栏（含语言标记）并返回去首尾空白的正文。"""
        import re

        text = (text or "").strip()
        m = re.search(r"```[a-zA-Z0-9_-]*\s*(.*?)```", text, re.DOTALL)
        if m:
            text = m.group(1)
        return text.replace("```", "").strip()

    def db_nl2sql(self, question: str) -> Dict[str, Any]:
        """自然语言 → 一条 SQLite SQL：``{sql, kind, note}``（附录 A-2）。

        ``kind`` 按首个关键字判定 ``select`` / ``write`` / ``invalid``；模型失败或输出不可用时
        ``kind=invalid`` 并在 ``note`` 说明。含高危关键字（DROP / DELETE / ALTER …）时 ``note`` 提示需确认。
        """
        question = (question or "").strip()
        if not question:
            return {"sql": "", "kind": "invalid", "note": "请输入自然语言描述"}
        if not self.db_current().get("connected"):
            return {"sql": "", "kind": "invalid", "note": "尚未连接数据库，请先连接"}
        schema = self.db_schema_text() or "（当前库没有表）"
        prompt = f"你是 SQLite 专家。仅输出一条 SQL，不要解释、不要围栏。\n表结构：\n{schema}\n问题：{question}"
        try:
            raw = self._complete_text(prompt, num_predict=self.DB_NL2SQL_NUM_PREDICT, temperature=0)
        except BaseException as exc:  # noqa: BLE001
            return {"sql": "", "kind": "invalid", "note": f"生成失败: {exc}"}
        sql = self._strip_fences(str(raw or ""))
        # 只保留第一条语句（模型偶尔多输出一条）
        if ";" in sql:
            first = sql.split(";", 1)[0].strip()
            sql = first + ";" if first else sql
        kind = self.sql_kind(sql)
        if kind == "invalid":
            return {"sql": sql, "kind": "invalid", "note": "模型未生成可识别的 SQL，请换个说法或直接手写"}
        note = ""
        try:
            from database_tools.sql_generator import SQLGenerator

            if not SQLGenerator().validate_sql(sql):
                note = "含高危关键字（DROP / DELETE / ALTER …），执行前请仔细确认"
        except BaseException:  # noqa: BLE001
            pass
        if kind == "write" and not note:
            note = "这是写操作，运行前需确认"
        return {"sql": sql, "kind": kind, "note": note}
