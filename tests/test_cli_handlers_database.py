#!/usr/bin/env python3
"""test_cli_handlers_database.py — CLI ``/db-*`` 命令处理器测试（F9 P1-2 / P1-3）。

覆盖：``/db-connect <database>`` 单参数（默认 sqlite）与两参数兼容；
``/db-schema`` 无参数列出全部表；以及用真实 registry 的集成断言：
连接后 ``/db-query`` 只传 sql 也作用于已连接的库。
"""
from unittest.mock import MagicMock

import pytest

import cli_handlers as h
from query_interface import ParsedCommand


def _ctx(result="[成功] ok"):
    reg = MagicMock()
    reg.execute.return_value = result
    ctx = h.CLIContext(console=MagicMock(), has_rich=False, registry=reg, record_command=MagicMock())
    return ctx, reg


def _pc(kind, arg):
    return ParsedCommand(kind, f"/{kind.replace('_', '-')} {arg}".strip(), arg)


class TestDbConnect:
    def test_single_arg_defaults_to_sqlite(self):
        ctx, reg = _ctx()
        assert h.handle_db_connect(ctx, _pc("db_connect", "/tmp/x.db")) is True
        reg.execute.assert_called_once_with("database_connect", {"db_type": "sqlite", "database": "/tmp/x.db"})
        ctx.record_command.assert_called_once_with("db_connect", "sqlite /tmp/x.db")

    def test_two_args_still_supported(self):
        ctx, reg = _ctx()
        assert h.handle_db_connect(ctx, _pc("db_connect", "sqlite /tmp/y.db")) is True
        reg.execute.assert_called_once_with("database_connect", {"db_type": "sqlite", "database": "/tmp/y.db"})

    def test_no_arg_shows_usage(self):
        ctx, reg = _ctx()
        assert h.handle_db_connect(ctx, _pc("db_connect", "")) is False
        reg.execute.assert_not_called()
        assert "/db-connect <database>" in ctx.console.print.call_args.args[0]

    def test_only_type_name_is_usage_error(self):
        ctx, reg = _ctx()
        assert h.handle_db_connect(ctx, _pc("db_connect", "sqlite")) is False
        reg.execute.assert_not_called()

    def test_error_result(self):
        ctx, reg = _ctx("[错误] 连接失败")
        assert h.handle_db_connect(ctx, _pc("db_connect", "/tmp/x.db")) is False

    def test_exception_recorded(self):
        ctx, reg = _ctx()
        reg.execute.side_effect = RuntimeError("boom")
        assert h.handle_db_connect(ctx, _pc("db_connect", "/tmp/x.db")) is True
        assert ctx.record_command.call_args.args[2] == "failed"


class TestDbSchema:
    """``/db-schema`` 走共享层 ``database_tools.results``（不经 registry）；表格渲染断言见
    ``test_cli_handlers_rich_tables.py``，这里覆盖未连接 / 不存在的表 / 异常。"""

    @pytest.fixture(autouse=True)
    def _clean(self):
        from database_tools import session

        session.clear_current()
        yield
        session.clear_current()

    def _connect(self, tmp_path):
        from database_tools import session

        session.set_current("sqlite", str(tmp_path / "s.db"))

    def test_not_connected_hint(self):
        ctx, reg = _ctx()
        assert h.handle_db_schema(ctx, _pc("db_schema", "")) is False
        assert ctx.console.print.call_args.kwargs.get("style") == "dim"
        reg.execute.assert_not_called()

    def test_no_arg_lists_all_tables(self, tmp_path):
        self._connect(tmp_path)
        from database_tools import results
        results.execute_structured(results.current_executor(), "CREATE TABLE t(id INTEGER)")
        ctx, reg = _ctx()
        assert h.handle_db_schema(ctx, _pc("db_schema", "")) is True
        printed = "\n".join(str(c.args[0]) for c in ctx.console.print.call_args_list)
        assert "- t" in printed
        ctx.record_command.assert_called_once_with("db_schema", "(all)")
        reg.execute.assert_not_called()

    def test_empty_db_hint(self, tmp_path):
        self._connect(tmp_path)
        ctx, reg = _ctx()
        assert h.handle_db_schema(ctx, _pc("db_schema", "")) is True
        assert "没有表" in str(ctx.console.print.call_args.args[0])
        assert ctx.console.print.call_args.kwargs.get("style") == "dim"

    def test_with_table_plain(self, tmp_path):
        self._connect(tmp_path)
        from database_tools import results
        results.execute_structured(results.current_executor(), "CREATE TABLE t(id INTEGER PRIMARY KEY, n TEXT NOT NULL)")
        ctx, reg = _ctx()
        assert h.handle_db_schema(ctx, _pc("db_schema", "t")) is True
        printed = "\n".join(str(c.args[0]) for c in ctx.console.print.call_args_list)
        assert "id  INTEGER  PK" in printed and "NOT NULL" in printed
        ctx.record_command.assert_called_once_with("db_schema", "t")

    def test_unknown_table_error(self, tmp_path):
        self._connect(tmp_path)
        ctx, reg = _ctx()
        assert h.handle_db_schema(ctx, _pc("db_schema", "nope")) is False
        assert "不存在" in str(ctx.console.print.call_args.args[0])
        assert ctx.record_command.call_args.args[2] == "failed"

    def test_exception_recorded(self, monkeypatch):
        ctx, reg = _ctx()
        monkeypatch.setattr(h, "_db_results", lambda: (_ for _ in ()).throw(RuntimeError("boom")))
        assert h.handle_db_schema(ctx, _pc("db_schema", "")) is True
        assert ctx.record_command.call_args.args[2] == "failed"


class TestDbQuery:
    @pytest.fixture(autouse=True)
    def _clean(self):
        from database_tools import session

        session.clear_current()
        yield
        session.clear_current()

    def test_empty_sql_usage(self):
        ctx, reg = _ctx()
        assert h.handle_db_query(ctx, _pc("db_query", "")) is False

    def test_not_connected_hint(self):
        ctx, reg = _ctx()
        assert h.handle_db_query(ctx, _pc("db_query", "select 1")) is False
        assert ctx.console.print.call_args.kwargs.get("style") == "dim"
        reg.execute.assert_not_called()

    def test_error_recorded(self, tmp_path):
        from database_tools import session

        session.set_current("sqlite", str(tmp_path / "q.db"))
        ctx, reg = _ctx()
        assert h.handle_db_query(ctx, _pc("db_query", "SELECT * FROM nope")) is False
        assert "no such table" in str(ctx.console.print.call_args.args[0])
        assert ctx.record_command.call_args.args[2] == "failed"
        assert h.handle_db_query(ctx, _pc("db_query", "DELETE FROM x")) is False  # 写语句拒绝

    def test_exception_recorded(self, monkeypatch):
        ctx, reg = _ctx()
        monkeypatch.setattr(h, "_db_results", lambda: (_ for _ in ()).throw(RuntimeError("boom")))
        assert h.handle_db_query(ctx, _pc("db_query", "select 1")) is True
        assert ctx.record_command.call_args.args[2] == "failed"


class TestDbWriteConfirm:
    """写操作工具 safe=False：需交互确认后 auto_confirm=True 执行，不得打印协议串。"""

    def _ctx(self, input_value="y", result="[成功] ok"):
        ctx, reg = _ctx(result)
        ctx.console.input.return_value = input_value
        return ctx, reg

    def test_execute_confirm_yes(self):
        ctx, reg = self._ctx("y")
        assert h.handle_db_execute(ctx, _pc("db_execute", "DELETE FROM t")) is True
        assert reg.execute.call_args.kwargs.get("auto_confirm") is True
        outs = [c.args[0] for c in ctx.console.print.call_args_list if c.args]
        assert all("CONFIRM_REQUIRED" not in str(o) for o in outs)

    def test_execute_confirm_no(self):
        ctx, reg = self._ctx("n")
        assert h.handle_db_execute(ctx, _pc("db_execute", "DELETE FROM t")) is False
        reg.execute.assert_not_called()

    def test_execute_empty(self):
        ctx, reg = self._ctx()
        assert h.handle_db_execute(ctx, _pc("db_execute", "")) is False

    def test_create_table_and_insert_confirm(self):
        ctx, reg = self._ctx("y")
        assert h.handle_db_create_table(ctx, _pc("db_create_table", 't {"id": "INTEGER"}')) is True
        assert reg.execute.call_args.kwargs.get("auto_confirm") is True
        assert h.handle_db_insert(ctx, _pc("db_insert", 't {"id": 1}')) is True
        assert reg.execute.call_args.kwargs.get("auto_confirm") is True

    def test_create_table_cancel(self):
        ctx, reg = self._ctx("n")
        assert h.handle_db_create_table(ctx, _pc("db_create_table", 't {"id": "INTEGER"}')) is False
        assert h.handle_db_insert(ctx, _pc("db_insert", 't {"id": 1}')) is False
        reg.execute.assert_not_called()


class TestP01AutoConfirmRiskGate:
    """F10 P0-1-c：``_confirm`` 的 AUTO_CONFIRM 只放行 low / medium。"""

    @pytest.fixture
    def auto_confirm_on(self, monkeypatch):
        from config import Config

        monkeypatch.setattr(Config, "AUTO_CONFIRM", True)

    def test_confirm_without_safety_still_auto_allowed(self, auto_confirm_on):
        console = MagicMock()
        assert h._confirm(console) is True
        console.input.assert_not_called()

    @pytest.mark.parametrize("level", ["low", "medium"])
    def test_confirm_allows_low_medium(self, auto_confirm_on, level):
        console = MagicMock()
        assert h._confirm(console, safety={"risk_level": level}) is True
        console.input.assert_not_called()

    @pytest.mark.parametrize("level", ["high", "critical"])
    def test_confirm_rejects_high_without_interaction(self, auto_confirm_on, level):
        console = MagicMock()
        console.input.side_effect = EOFError
        assert h._confirm(console, safety={"risk_level": level}) is False
        printed = "\n".join(str(c.args[0]) for c in console.print.call_args_list if c.args)
        assert "高风险命令需人工确认" in printed

    def test_db_execute_auto_confirms_insert(self, auto_confirm_on):
        ctx, reg = _ctx()
        assert h.handle_db_execute(ctx, _pc("db_execute", "INSERT INTO t VALUES (1)")) is True
        ctx.console.input.assert_not_called()
        assert reg.execute.call_args.kwargs.get("auto_confirm") is True

    def test_db_execute_does_not_auto_confirm_drop(self, auto_confirm_on):
        """``DROP TABLE`` 经 SQL 客户端上下文判为 high，AUTO_CONFIRM 不放行。"""
        ctx, reg = _ctx()
        ctx.console.input.side_effect = EOFError
        assert h.handle_db_execute(ctx, _pc("db_execute", "DROP TABLE t")) is False
        reg.execute.assert_not_called()
        printed = "\n".join(str(c.args[0]) for c in ctx.console.print.call_args_list if c.args)
        assert "高风险命令需人工确认" in printed


class TestRealRegistryIntegration:
    """用真实 registry：连接 → 建表 → 只传 sql 查询 → 列表。"""

    @pytest.fixture(autouse=True)
    def _clean(self):
        from database_tools import session

        session.clear_current()
        yield
        session.clear_current()

    def test_connect_then_query_uses_connected_db(self, tmp_path):
        import agent_tools

        ctx = h.CLIContext(console=MagicMock(), has_rich=False, registry=agent_tools.registry, record_command=MagicMock())
        ctx.console.input.return_value = "y"
        db = str(tmp_path / "cli.db")
        assert h.handle_db_connect(ctx, _pc("db_connect", db)) is True
        assert h.handle_db_execute(ctx, _pc("db_execute", "CREATE TABLE t(id INTEGER, name TEXT)")) is True
        assert h.handle_db_execute(ctx, _pc("db_execute", "INSERT INTO t VALUES (1, 'Bob')")) is True
        assert h.handle_db_query(ctx, _pc("db_query", "SELECT name FROM t")) is True
        printed = "\n".join(str(c.args[0]) for c in ctx.console.print.call_args_list)
        assert "Bob" in printed and "共 1 行" in printed
        assert h.handle_db_schema(ctx, _pc("db_schema", "")) is True
        printed = "\n".join(str(c.args[0]) for c in ctx.console.print.call_args_list)
        assert "- t" in printed


def test_handlers_registered():
    from cli_handlers import COMMAND_HANDLERS

    for name in ("db_connect", "db_query", "db_execute", "db_schema"):
        assert name in COMMAND_HANDLERS
