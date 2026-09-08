#!/usr/bin/env python3
"""test_database_results.py — 共享层结构化取数 ``database_tools.results``（F9 P1-4 / P3-5）。

Web ``WebService.db_*`` 与 CLI ``/db-query`` ``/db-schema`` 都调用这里；用真实 SQLite（tmp_path）验证。
"""
from unittest.mock import MagicMock

import pytest

from database_tools import results as R
from database_tools import session


@pytest.fixture(autouse=True)
def _clean():
    session.clear_current()
    yield
    session.clear_current()


def _executor(tmp_path, name="r.db"):
    session.set_current("sqlite", str(tmp_path / name))
    return R.current_executor()


class TestSqlKind:
    def test_head_and_kind(self):
        assert R.sql_head("  SELECT 1") == "select"
        assert R.sql_head("-- c\n\n(select 1)") == "select"
        assert R.sql_head("-- only comment") == "" and R.sql_head("") == ""
        assert R.sql_kind("WITH x AS (SELECT 1) SELECT * FROM x") == "select"
        assert R.sql_kind("pragma table_info(t)") == "select"
        assert R.sql_kind("InSeRt into t values (1)") == "write"
        assert R.sql_kind("drop table t") == "write"
        assert R.sql_kind("bogus") == "invalid" and R.sql_kind("") == "invalid"


class TestQuery:
    def test_validation_without_executor(self):
        assert R.query_structured(None, "")["error"] == "请输入 SQL 查询语句"
        assert R.query_structured(None, "-- x")["error"] == "请输入 SQL 查询语句"
        assert "只接受 SELECT" in R.query_structured(None, "DELETE FROM t")["error"]
        assert R.query_structured(None, "select 1")["error"] == R.NOT_CONNECTED

    def test_query_rows_and_truncate(self, tmp_path):
        ex = _executor(tmp_path)
        assert "error" not in R.execute_structured(ex, "CREATE TABLE n(x INTEGER, s TEXT)")
        assert R.execute_structured(ex, "INSERT INTO n VALUES (1,'a'),(2,NULL),(3,'c')")["affected_rows"] == 3
        q = R.query_structured(ex, "SELECT x, s FROM n ORDER BY x")
        assert q["columns"] == ["x", "s"] and q["rows"] == [[1, "a"], [2, None], [3, "c"]]
        assert q["row_count"] == 3 and q["truncated"] is False and q["execution_time"] >= 0
        t = R.query_structured(ex, "SELECT x FROM n ORDER BY x", max_rows=2)
        assert t["rows"] == [[1], [2]] and t["row_count"] == 3 and t["truncated"] is True
        # max_rows 非法回退默认
        assert R.query_structured(ex, "SELECT x FROM n", max_rows=0)["row_count"] == 3

    def test_query_error_and_exception(self, tmp_path):
        ex = _executor(tmp_path)
        r = R.query_structured(ex, "SELECT * FROM nope")
        assert "no such table" in r["error"] and r["rows"] == []
        broken = MagicMock()
        broken.execute_query.side_effect = RuntimeError("boom")
        assert R.query_structured(broken, "select 1")["error"] == "boom"
        failed = MagicMock()
        failed.execute_query.return_value = MagicMock(success=False, error_message="", execution_time=0.1)
        assert R.query_structured(failed, "select 1")["error"] == "查询失败"


class TestExecute:
    def test_execute_paths(self, tmp_path):
        assert R.execute_structured(None, "")["error"] == "请输入 SQL 语句"
        assert R.execute_structured(None, "create table t(x)")["error"] == R.NOT_CONNECTED
        ex = _executor(tmp_path)
        assert R.execute_structured(ex, "CREATE TABLE t(x)")["affected_rows"] == 0  # DDL 归一为 0
        assert "no such table" in R.execute_structured(ex, "INSERT INTO nope VALUES (1)")["error"]
        broken = MagicMock()
        broken.execute_update.side_effect = RuntimeError("boom")
        assert R.execute_structured(broken, "delete from t")["error"] == "boom"
        failed = MagicMock()
        failed.execute_update.return_value = MagicMock(success=False, error_message=None, execution_time=0.1)
        assert R.execute_structured(failed, "delete from t")["error"] == "执行失败"


class TestTablesAndSchema:
    def test_tables(self, tmp_path):
        assert R.tables_structured(None) == {"tables": [], "error": R.NOT_CONNECTED}
        ex = _executor(tmp_path)
        assert R.tables_structured(ex) == {"tables": []}
        R.execute_structured(ex, "CREATE TABLE b(x)")
        R.execute_structured(ex, "CREATE TABLE a(x)")
        assert R.tables_structured(ex) == {"tables": ["a", "b"]}
        broken = MagicMock()
        broken.list_tables.side_effect = RuntimeError("boom")
        assert R.tables_structured(broken)["error"] == "boom"

    def test_table_schema(self, tmp_path):
        assert R.table_schema_structured(None, "")["error"] == "请选择表"
        assert R.table_schema_structured(None, "t")["error"] == R.NOT_CONNECTED
        ex = _executor(tmp_path)
        R.execute_structured(ex, "CREATE TABLE a(id INTEGER PRIMARY KEY, n TEXT NOT NULL, d REAL DEFAULT 1.5)")
        sc = R.table_schema_structured(ex, " a ")
        assert sc["table"] == "a" and [c["name"] for c in sc["columns"]] == ["id", "n", "d"]
        assert "不存在" in R.table_schema_structured(ex, "zzz")["error"]
        broken = MagicMock()
        broken.get_table_schema.side_effect = RuntimeError("boom")
        assert R.table_schema_structured(broken, "a")["error"] == "boom"
        assert R.schema_rows(sc) == [["id", "INTEGER", "PK"], ["n", "TEXT", "NOT NULL"], ["d", "REAL", "DEFAULT 1.5"]]

    def test_constraint_label_and_rows(self):
        assert R.constraint_label({"primary_key": True, "not_null": True, "default_value": "'x'"}) == "PK · NOT NULL · DEFAULT 'x'"
        assert R.constraint_label({"default_value": ""}) == "" and R.constraint_label({}) == ""
        assert R.schema_rows({"columns": [{"name": "n", "type": ""}]}) == [["n", "—", ""]]
        assert R.schema_rows({}) == [] and R.schema_rows(None) == []

    def test_current_executor(self, tmp_path):
        assert R.current_executor() is None
        ex = _executor(tmp_path)
        assert ex is not None and ex.connector is session.current_connector()
