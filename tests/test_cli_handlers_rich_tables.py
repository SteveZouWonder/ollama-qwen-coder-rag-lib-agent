#!/usr/bin/env python3
"""test_cli_handlers_rich_tables.py — CLI rich 表格渲染（F9 P3-5）。

用 ``rich.console.Console(record=True)`` 捕获输出，断言表头 / 行数 / 空态提示：
``/git-analyze``（概览 + 最近提交表 / status 变更表 / authors 作者表）、``/db-query`` 结果表、
``/db-schema`` 列表与表名表。最后一组用同一临时 git 仓库 / 同一 SQLite 断言 Web 与 CLI 取到相同字段。
"""
import subprocess
from unittest.mock import MagicMock

_REAL_RUN = subprocess.run
_REAL_POPEN = subprocess.Popen

import pytest
from rich.console import Console

import cli_handlers as h
from database_tools import results as R
from database_tools import session
from query_interface import ParsedCommand


def _console():
    return Console(record=True, width=120, force_terminal=False, color_system=None)


def _ctx(console=None, has_rich=True):
    console = console or _console()
    ctx = h.CLIContext(console=console, has_rich=has_rich, registry=MagicMock(), record_command=MagicMock())
    return ctx, console


def _pc(kind, arg=""):
    return ParsedCommand(kind, f"/{kind.replace('_', '-')} {arg}".strip(), arg)


def _text(console) -> str:
    return console.export_text()


_OV = {
    "is_repo": True, "branch": "main", "last_commit_at": "2026-09-08 10:00:00 +0800",
    "changed": [{"status": "M", "label": "修改", "path": "a.py"}, {"status": "??", "label": "未跟踪", "path": "b.txt"}],
    "commits": [{"hash7": f"abc{i:04d}", "author": "Tester", "date": "2026-09-08", "subject": f"commit {i}"}
                for i in range(3)],
    "authors": [{"name": "Tester", "commits": 3}, {"name": "Other", "commits": 1}],
}
_EMPTY_REPO = {"is_repo": True, "branch": "main", "last_commit_at": "", "changed": [], "commits": [], "authors": []}


class TestGitAnalyzeTables:
    @pytest.fixture(autouse=True)
    def _patch(self, monkeypatch):
        self.calls = []

        def fake(repo_path=".", max_commits=10):
            self.calls.append(max_commits)
            return dict(getattr(self, "ov", _OV))

        monkeypatch.setattr(h, "_git_overview", fake)

    def test_overview_default(self):
        ctx, console = _ctx()
        assert h.handle_git_analyze(ctx, _pc("git_analyze")) is True
        out = _text(console)
        assert "分支: main" in out and "变更文件: 2" in out and "最近提交: 2026-09-08 10:00" in out
        assert "最近 3 次提交" in out
        for head in ("提交", "作者", "日期", "标题"):
            assert head in out
        assert out.count("Tester") == 3 and "commit 2" in out
        assert self.calls == [10]  # 最近 10 次

    def test_history_same_as_default(self):
        ctx, console = _ctx()
        h.handle_git_analyze(ctx, _pc("git_analyze", "history"))
        assert "最近 3 次提交" in _text(console)

    def test_status_table(self):
        ctx, console = _ctx()
        h.handle_git_analyze(ctx, _pc("git_analyze", "status"))
        out = _text(console)
        assert "变更文件（2）" in out and "状态" in out and "路径" in out
        assert "修改" in out and "a.py" in out and "未跟踪" in out and "b.txt" in out
        assert "最近 3 次提交" not in out

    def test_authors_table(self):
        ctx, console = _ctx()
        h.handle_git_analyze(ctx, _pc("git_analyze", "authors"))
        out = _text(console)
        assert "提交者统计" in out and "作者" in out and "提交数" in out
        assert "Tester" in out and "Other" in out and out.count("\n") >= 5

    def test_empty_states(self):
        self.ov = _EMPTY_REPO
        for arg, hint in (("", "还没有提交记录"), ("status", "工作区干净"), ("authors", "还没有提交者")):
            ctx, console = _ctx()
            assert h.handle_git_analyze(ctx, _pc("git_analyze", arg)) is True
            out = _text(console)
            assert hint in out and "╭" not in out.split(hint)[-1]  # 不打印空表

    def test_non_repo(self):
        self.ov = {**_EMPTY_REPO, "is_repo": False}
        ctx, console = _ctx()
        assert h.handle_git_analyze(ctx, _pc("git_analyze")) is True
        assert "不是 Git 仓库" in _text(console) and "╭" not in _text(console)

    def test_plain_fallback_without_rich(self):
        ctx, console = _ctx(has_rich=False)
        h.handle_git_analyze(ctx, _pc("git_analyze"))
        h.handle_git_analyze(ctx, _pc("git_analyze", "status"))
        h.handle_git_analyze(ctx, _pc("git_analyze", "authors"))
        out = _text(console)
        assert "╭" not in out and "abc0000" in out and "修改 a.py" in out and "Tester: 3" in out
        self.ov = _EMPTY_REPO
        ctx, console = _ctx(has_rich=False)
        for arg in ("", "status", "authors"):
            h.handle_git_analyze(ctx, _pc("git_analyze", arg))
        out = _text(console)
        assert "还没有提交记录" in out and "工作区干净" in out and "还没有提交者" in out


class TestDbTables:
    @pytest.fixture(autouse=True)
    def _clean(self):
        session.clear_current()
        yield
        session.clear_current()

    def _connected(self, tmp_path):
        session.set_current("sqlite", str(tmp_path / "cli.db"))
        ex = R.current_executor()
        R.execute_structured(ex, "CREATE TABLE users(id INTEGER PRIMARY KEY, name TEXT NOT NULL, age INTEGER DEFAULT 18)")
        R.execute_structured(ex, "INSERT INTO users(name, age) VALUES ('Alice', 30), ('Bob', NULL)")
        R.execute_structured(ex, "CREATE TABLE orders(id INTEGER)")
        return ex

    def test_query_table(self, tmp_path):
        self._connected(tmp_path)
        ctx, console = _ctx()
        assert h.handle_db_query(ctx, _pc("db_query", "SELECT id, name, age FROM users ORDER BY id")) is True
        out = _text(console)
        assert "查询结果" in out
        for head in ("id", "name", "age"):
            assert head in out
        assert "Alice" in out and "Bob" in out and "NULL" in out
        assert "共 2 行" in out and "s" in out
        ctx.record_command.assert_called_once()

    def test_query_truncated_hint(self, tmp_path, monkeypatch):
        self._connected(tmp_path)
        monkeypatch.setattr(h, "DB_QUERY_MAX_ROWS", 1)
        ctx, console = _ctx()
        h.handle_db_query(ctx, _pc("db_query", "SELECT name FROM users"))
        out = _text(console)
        assert "仅显示前 1 行" in out and "…共 2 行" in out and out.count("Alice") + out.count("Bob") == 1

    def test_query_empty_result(self, tmp_path):
        self._connected(tmp_path)
        ctx, console = _ctx()
        assert h.handle_db_query(ctx, _pc("db_query", "SELECT * FROM orders")) is True
        out = _text(console)
        assert "查询没有返回数据" in out and "╭" not in out

    def test_query_plain_fallback(self, tmp_path):
        self._connected(tmp_path)
        ctx, console = _ctx(has_rich=False)
        h.handle_db_query(ctx, _pc("db_query", "SELECT name FROM users ORDER BY id"))
        out = _text(console)
        assert "name" in out and "Alice" in out and "╭" not in out

    def test_schema_table(self, tmp_path):
        self._connected(tmp_path)
        ctx, console = _ctx()
        assert h.handle_db_schema(ctx, _pc("db_schema", "users")) is True
        out = _text(console)
        assert "表 users · 3 列" in out
        for head in ("列", "类型", "约束"):
            assert head in out
        assert "PK" in out and "NOT NULL" in out and "DEFAULT 18" in out

    def test_schema_list_tables(self, tmp_path):
        self._connected(tmp_path)
        ctx, console = _ctx()
        assert h.handle_db_schema(ctx, _pc("db_schema")) is True
        out = _text(console)
        assert "共 2 张表" in out and "表名" in out and "orders" in out and "users" in out
        assert "/db-schema <table>" in out

    def test_not_connected_dim_hint(self):
        ctx, console = _ctx()
        assert h.handle_db_query(ctx, _pc("db_query", "select 1")) is False
        assert h.handle_db_schema(ctx, _pc("db_schema")) is False
        out = _text(console)
        assert out.count("尚未连接数据库") == 2 and "/db-connect" in out and "╭" not in out


def _init_repo(path):
    def git(*args):
        subprocess.run(["git", *args], cwd=path, check=True, capture_output=True, text=True)

    git("init", "-q", "-b", "main")
    git("config", "user.email", "t@example.com")
    git("config", "user.name", "Tester")
    for i in range(2):
        (path / f"f{i}.txt").write_text(f"v{i}\n", encoding="utf-8")
        git("add", ".")
        git("commit", "-q", "-m", f"commit {i}")
    (path / "f0.txt").write_text("changed\n", encoding="utf-8")
    return git


class TestWebCliParity:
    """同一临时仓库 / 同一 SQLite：Web service 与 CLI handler 取到相同字段。"""

    @pytest.fixture(autouse=True)
    def _real_git(self, monkeypatch):
        monkeypatch.setattr(subprocess, "run", _REAL_RUN)
        monkeypatch.setattr(subprocess, "Popen", _REAL_POPEN)
        session.clear_current()
        yield
        session.clear_current()

    def test_git_overview_same_source(self, tmp_path, monkeypatch):
        from web.services import WebService

        _init_repo(tmp_path)
        web_ov = WebService().git_overview(str(tmp_path), max_commits=10)
        cli_ov = h._git_overview(str(tmp_path))
        assert web_ov == cli_ov
        assert cli_ov["branch"] == "main" and len(cli_ov["commits"]) == 2
        assert [c["path"] for c in cli_ov["changed"]] == ["f0.txt"]
        # CLI 渲染读取的就是这份数据
        monkeypatch.setattr(h, "_git_overview", lambda repo_path=".", max_commits=10: cli_ov)
        ctx, console = _ctx()
        h.handle_git_analyze(ctx, _pc("git_analyze"))
        out = _text(console)
        assert "分支: main" in out and "commit 1" in out and "commit 0" in out

    def test_db_query_same_source(self, tmp_path):
        from web.services import WebService

        svc = WebService()
        assert svc.db_connect(str(tmp_path / "same.db")).startswith("[成功]")
        svc.db_execute("CREATE TABLE t(id INTEGER PRIMARY KEY, n TEXT)")
        svc.db_execute("INSERT INTO t(n) VALUES ('x'), ('y')")
        web_q = svc.db_query("SELECT id, n FROM t ORDER BY id")
        cli_q = R.query_structured(R.current_executor(), "SELECT id, n FROM t ORDER BY id", max_rows=h.DB_QUERY_MAX_ROWS)
        for key in ("sql", "columns", "rows", "row_count", "truncated"):
            assert web_q[key] == cli_q[key]
        assert svc.db_table_schema("t") == R.table_schema_structured(R.current_executor(), "t")
        assert svc.db_tables() == R.tables_structured(R.current_executor())
        ctx, console = _ctx()
        h.handle_db_query(ctx, _pc("db_query", "SELECT id, n FROM t ORDER BY id"))
        out = _text(console)
        assert "x" in out and "y" in out and "共 2 行" in out
