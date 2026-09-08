#!/usr/bin/env python3
"""test_web_tools_state.py — 工具页持久状态（F9 P3-1 / P3-2）。

覆盖：默认路径经 ``runtime_paths.app_state_dir`` 解析（conftest 已隔离到临时目录）、
读写、上限裁剪、去重（最新在前）、损坏 JSON / 非 dict / 脏元素回退、写失败不抛。
"""
import json


from web.tools_state import RECENT_DB_MAX, SHELL_HISTORY_MAX, STATE_FILENAME, ToolsState, default_state_path


class TestPath:
    def test_default_path_under_app_state_dir(self, tmp_path):
        import runtime_paths as rp

        rp.set_app_state_root(tmp_path / "state")
        try:
            p = default_state_path()
            assert p == tmp_path / "state" / STATE_FILENAME
            assert ToolsState().path == p
        finally:
            rp.set_app_state_root(None)

    def test_explicit_path(self, tmp_path):
        st = ToolsState(tmp_path / "x.json")
        assert st.path == tmp_path / "x.json"


class TestLoadSave:
    def test_missing_file_is_empty(self, tmp_path):
        st = ToolsState(tmp_path / "s.json")
        assert st.load() == {"recent_databases": [], "shell_history": []}
        assert st.recent_databases() == [] and st.shell_history() == []

    def test_corrupt_json_falls_back_to_empty(self, tmp_path):
        p = tmp_path / "s.json"
        p.write_text("{not json", encoding="utf-8")
        st = ToolsState(p)
        assert st.load() == {"recent_databases": [], "shell_history": []}
        # 之后写入会覆盖损坏文件
        assert st.remember_database("/a.db") == ["/a.db"]
        assert json.loads(p.read_text(encoding="utf-8"))["recent_databases"] == ["/a.db"]

    def test_non_dict_and_dirty_items(self, tmp_path):
        p = tmp_path / "s.json"
        p.write_text("[1, 2]", encoding="utf-8")
        assert ToolsState(p).load()["recent_databases"] == []
        p.write_text(json.dumps({"recent_databases": ["/a.db", None, {"x": 1}, "  ", 3],
                                 "shell_history": "ls", "extra": 1}), encoding="utf-8")
        state = ToolsState(p).load()
        assert state == {"recent_databases": ["/a.db", "3"], "shell_history": []}

    def test_save_trims_and_keeps_only_known_keys(self, tmp_path):
        p = tmp_path / "s.json"
        st = ToolsState(p, recent_db_max=2, shell_history_max=3)
        assert st.save({"recent_databases": ["a", "b", "c"], "shell_history": list("abcd"), "junk": 1}) is True
        assert json.loads(p.read_text(encoding="utf-8")) == {"recent_databases": ["a", "b"], "shell_history": ["a", "b", "c"]}

    def test_save_failure_returns_false(self, tmp_path):
        # 父目录是文件 → mkdir 失败
        blocker = tmp_path / "blocker"
        blocker.write_text("x", encoding="utf-8")
        st = ToolsState(blocker / "s.json")
        assert st.save({"recent_databases": ["a"]}) is False
        assert st.remember_database("/a.db") == ["/a.db"]  # 内存结果仍返回，不抛


class TestRecentDatabases:
    def test_dedupe_newest_first_and_limit(self, tmp_path):
        st = ToolsState(tmp_path / "s.json", recent_db_max=3)
        st.remember_database("/a.db")
        st.remember_database("/b.db")
        assert st.remember_database("/a.db") == ["/a.db", "/b.db"]
        st.remember_database("/c.db")
        assert st.remember_database("/d.db") == ["/d.db", "/c.db", "/a.db"]
        assert st.recent_databases() == ["/d.db", "/c.db", "/a.db"]

    def test_memory_and_blank_not_recorded(self, tmp_path):
        st = ToolsState(tmp_path / "s.json")
        assert st.remember_database(":memory:") == []
        assert st.remember_database("   ") == []
        assert not (tmp_path / "s.json").exists()

    def test_forget(self, tmp_path):
        st = ToolsState(tmp_path / "s.json")
        st.remember_database("/a.db")
        st.remember_database("/b.db")
        assert st.forget_database("/a.db") == ["/b.db"]
        assert st.forget_database("/zzz") == ["/b.db"]

    def test_default_limits(self, tmp_path):
        st = ToolsState(tmp_path / "s.json")
        for i in range(RECENT_DB_MAX + 5):
            st.remember_database(f"/db{i}.db")
        assert len(st.recent_databases()) == RECENT_DB_MAX == 8
        assert st.recent_databases()[0] == f"/db{RECENT_DB_MAX + 4}.db"


class TestShellHistory:
    def test_dedupe_and_limit(self, tmp_path):
        st = ToolsState(tmp_path / "s.json", shell_history_max=2)
        st.remember_command("ls")
        st.remember_command("pwd")
        assert st.remember_command("ls") == ["ls", "pwd"]
        assert st.remember_command("date") == ["date", "ls"]
        assert st.shell_history() == ["date", "ls"]

    def test_blank_ignored_and_clear(self, tmp_path):
        st = ToolsState(tmp_path / "s.json")
        assert st.remember_command("  ") == []
        st.remember_command("ls -la")
        st.clear_shell_history()
        assert st.shell_history() == []
        assert SHELL_HISTORY_MAX == 50

    def test_independent_of_recent_databases(self, tmp_path):
        st = ToolsState(tmp_path / "s.json")
        st.remember_database("/a.db")
        st.remember_command("ls")
        assert st.load() == {"recent_databases": ["/a.db"], "shell_history": ["ls"]}
