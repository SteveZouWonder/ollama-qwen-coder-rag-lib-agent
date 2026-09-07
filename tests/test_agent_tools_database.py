#!/usr/bin/env python3
"""test_agent_tools_database.py — 数据库工具「当前连接」回归测试（F9 P1-2 / P1-3）。

回归背景：``database_connect`` 之后 ``database_query`` 等工具只传 ``sql`` 时，
每次都在全新的 ``:memory:`` 库上执行，连接对后续操作无效（Web 与 CLI 共有）。
修复方案：``database_tools.session`` 提供进程级「当前连接」，工具在调用方未
显式传 ``database`` 时回退到它；同一 ``(db_type, database)`` 复用连接器。
"""
import pytest

import agent_tools
from database_tools import session


@pytest.fixture(autouse=True)
def _isolated_session():
    """每个用例前后清空当前连接，避免用例间串扰。"""
    session.clear_current()
    yield
    session.clear_current()


class TestSessionModule:
    def test_default_no_current(self):
        assert session.get_current() is None

    def test_set_get_clear(self, tmp_path):
        db = str(tmp_path / "a.db")
        info = session.set_current("sqlite", db)
        assert info == {"db_type": "sqlite", "database": db}
        assert session.get_current() == {"db_type": "sqlite", "database": db}
        # 返回的是副本，外部修改不影响内部状态
        info["database"] = "x"
        assert session.get_current()["database"] == db
        session.clear_current()
        assert session.get_current() is None

    def test_resolve_falls_back_only_when_default(self, tmp_path):
        db = str(tmp_path / "a.db")
        # 没有当前连接：原样返回
        assert session.resolve("sqlite", session.DEFAULT_DATABASE) == ("sqlite", session.DEFAULT_DATABASE, {})
        session.set_current("sqlite", db)
        # 默认值 → 回退到当前连接
        assert session.resolve("sqlite", session.DEFAULT_DATABASE) == ("sqlite", db, {})
        # 显式传参优先
        other = str(tmp_path / "b.db")
        assert session.resolve("sqlite", other) == ("sqlite", other, {})

    def test_connector_reused_for_same_key(self, tmp_path):
        db = str(tmp_path / "a.db")
        c1 = session.get_connector("sqlite", db)
        c2 = session.get_connector("sqlite", db)
        assert c1 is c2
        c3 = session.get_connector("sqlite", str(tmp_path / "b.db"))
        assert c3 is not c1

    def test_clear_closes_connectors(self, tmp_path):
        db = str(tmp_path / "a.db")
        c1 = session.get_connector("sqlite", db)
        assert c1.test_connection()
        session.set_current("sqlite", db)
        session.clear_current()
        assert c1.get_connection_info()["is_connected"] is False
        # 清空后再取会得到新的实例
        assert session.get_connector("sqlite", db) is not c1

    def test_current_connector_none_when_not_connected(self):
        assert session.current_connector() is None

    def test_memory_db_persists_via_cached_connector(self):
        """``:memory:`` 作为当前连接时也要复用同一连接，否则表会随连接消失。"""
        session.set_current("sqlite", session.DEFAULT_DATABASE)
        assert "成功" in agent_tools.database_execute("CREATE TABLE m(x INTEGER)")
        assert "成功" in agent_tools.database_execute("INSERT INTO m VALUES (1)")
        out = agent_tools.database_query("SELECT x FROM m")
        assert "返回 1 行" in out


class TestCurrentConnectionFallback:
    """复现：连接 → 建表 → 只传 sql 查询，必须查到数据。"""

    def test_connect_execute_query_roundtrip(self, tmp_path):
        db = str(tmp_path / "t.db")
        out = agent_tools.database_connect(database=db)
        assert out.startswith("[成功]")
        assert session.get_current() == {"db_type": "sqlite", "database": db}

        out = agent_tools.database_execute("CREATE TABLE users(id INTEGER PRIMARY KEY, name TEXT NOT NULL)")
        assert out.startswith("[成功]") and "影响 0 行" in out  # DDL 的 rowcount=-1 归一为 0
        assert "影响 1 行" in agent_tools.database_execute("INSERT INTO users(name) VALUES ('Alice')")

        out = agent_tools.database_query("SELECT id, name FROM users")
        assert "返回 1 行" in out and "Alice" in out

    def test_explicit_database_overrides_current(self, tmp_path):
        cur = str(tmp_path / "cur.db")
        other = str(tmp_path / "other.db")
        agent_tools.database_connect(database=cur)
        agent_tools.database_execute("CREATE TABLE a(x INTEGER)")
        # 显式指定另一库：不受当前连接影响（该库没有表 a）
        out = agent_tools.database_query("SELECT * FROM a", database=other)
        assert out.startswith("[错误]") and "no such table" in out
        # 当前连接仍然是 cur
        assert session.get_current()["database"] == cur
        assert "返回 0 行" in agent_tools.database_query("SELECT * FROM a")

    def test_create_table_and_insert_use_current(self, tmp_path):
        agent_tools.database_connect(database=str(tmp_path / "c.db"))
        assert agent_tools.database_create_table("p", {"id": "INTEGER PRIMARY KEY", "v": "TEXT"}).startswith("[成功]")
        assert agent_tools.database_insert("p", {"v": "hi"}).startswith("[成功]")
        assert "hi" in agent_tools.database_query("SELECT v FROM p")

    def test_connect_failure_keeps_previous_current(self, tmp_path):
        cur = str(tmp_path / "cur.db")
        agent_tools.database_connect(database=cur)
        out = agent_tools.database_connect(db_type="mysql", database="whatever")
        assert out.startswith("[错误]")
        assert session.get_current()["database"] == cur

    def test_connect_message_mentions_followup(self, tmp_path):
        out = agent_tools.database_connect(database=str(tmp_path / "m.db"))
        assert "当前连接" in out


class TestGetSchema:
    def test_schema_single_table(self, tmp_path):
        agent_tools.database_connect(database=str(tmp_path / "s.db"))
        agent_tools.database_execute("CREATE TABLE t(id INTEGER PRIMARY KEY, n TEXT NOT NULL)")
        out = agent_tools.database_get_schema("t")
        assert "[表] t" in out and "id: INTEGER" in out and "PK: True" in out

    def test_schema_empty_table_lists_all(self, tmp_path):
        agent_tools.database_connect(database=str(tmp_path / "s.db"))
        agent_tools.database_execute("CREATE TABLE b(x INTEGER)")
        agent_tools.database_execute("CREATE TABLE a(x INTEGER)")
        out = agent_tools.database_get_schema("")
        assert out.startswith("[成功]") and "2 张表" in out
        # 按名排序
        assert out.index("- a") < out.index("- b")

    def test_schema_list_empty_db(self, tmp_path):
        agent_tools.database_connect(database=str(tmp_path / "e.db"))
        out = agent_tools.database_get_schema("")
        assert out.startswith("[提示]") and "没有表" in out

    def test_schema_unknown_table(self, tmp_path):
        agent_tools.database_connect(database=str(tmp_path / "s.db"))
        assert agent_tools.database_get_schema("nope").startswith("[错误]")

    def test_registry_schema_param_optional(self, tmp_path):
        """通过 registry 调用、不传 table，也应列出全部表（工具名 / 参数名不变）。"""
        agent_tools.database_connect(database=str(tmp_path / "r.db"))
        agent_tools.database_execute("CREATE TABLE z(x INTEGER)")
        out = agent_tools.registry.execute("database_get_schema", {})
        assert "- z" in out


class TestQueryExecutorListTables:
    def test_list_tables_sorted_excludes_internal(self, tmp_path):
        from database_tools import DatabaseConnector, DatabaseType, QueryExecutor

        ex = QueryExecutor(DatabaseConnector(DatabaseType.SQLITE, database=str(tmp_path / "l.db")))
        assert ex.list_tables() == []
        ex.execute_update("CREATE TABLE zeta(id INTEGER PRIMARY KEY AUTOINCREMENT)")  # 产生 sqlite_sequence
        ex.execute_update("CREATE TABLE alpha(x INTEGER)")
        assert ex.list_tables() == ["alpha", "zeta"]

    def test_list_tables_error_returns_empty(self):
        from database_tools import DatabaseConnector, DatabaseType, QueryExecutor

        ex = QueryExecutor(DatabaseConnector(DatabaseType.MYSQL, database="x"))
        assert ex.list_tables() == []
