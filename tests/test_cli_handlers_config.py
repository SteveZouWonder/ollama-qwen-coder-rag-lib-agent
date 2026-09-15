#!/usr/bin/env python3
"""test_cli_handlers_config.py — CLI ``/config``（F10 P0-1-d）。

显示运行配置，重点是「允许读目录 / 允许写目录」两行——读写越界报错时用户据此自查。
"""
import os
from unittest.mock import MagicMock

import pytest

import cli_handlers as h
from query_interface import ParsedCommand


@pytest.fixture
def scoped(tmp_path, monkeypatch):
    """cwd = tmp_path/proj；额外目录放在 proj 之外（cwd 的子目录会被 cwd 吸收，不单独列出）。"""
    proj = tmp_path / "proj"
    proj.mkdir()
    monkeypatch.chdir(proj)
    monkeypatch.delenv("WRITE_ALLOWED_DIRS", raising=False)
    monkeypatch.delenv("READ_ALLOWED_DIRS", raising=False)
    return tmp_path


def _ctx():
    return h.CLIContext(console=MagicMock(), has_rich=False, registry=MagicMock(),
                        record_command=MagicMock())


def _printed(ctx):
    return "\n".join(str(c.args[0]) for c in ctx.console.print.call_args_list if c.args)


class TestConfigRows:
    def test_includes_allowed_dirs(self, scoped, monkeypatch):
        extra = scoped / "ro"
        extra.mkdir()
        monkeypatch.setenv("READ_ALLOWED_DIRS", str(extra))
        rows = dict(h.config_rows())
        assert str((scoped / "proj").resolve()) in rows["允许写目录"]
        assert str(extra.resolve()) in rows["允许读目录"]

    def test_auto_confirm_scope_is_explicit(self, scoped, monkeypatch):
        from config import Config

        monkeypatch.setattr(Config, "AUTO_CONFIRM", True)
        assert "只放行 low / medium" in dict(h.config_rows())["自动确认"]
        monkeypatch.setattr(Config, "AUTO_CONFIRM", False)
        assert dict(h.config_rows())["自动确认"] == "关"

    def test_survives_missing_agent_tools(self, scoped, monkeypatch):
        import sys

        monkeypatch.setitem(sys.modules, "agent_tools", None)
        rows = dict(h.config_rows())
        assert "READ_ALLOWED_DIRS" in rows["允许读目录"]
        assert "WRITE_ALLOWED_DIRS" in rows["允许写目录"]

    def test_long_dir_list_is_folded(self, scoped, monkeypatch):
        """已入库文档目录累积后折叠显示，避免刷屏。"""
        dirs = []
        for i in range(9):
            d = scoped / f"d{i}"
            d.mkdir()
            dirs.append(str(d))
        monkeypatch.setenv("READ_ALLOWED_DIRS", os.pathsep.join(dirs))
        assert "…（共 10 个）" in dict(h.config_rows())["允许读目录"]


class TestHandleConfig:
    def test_prints_rows_and_hint(self, scoped):
        ctx = _ctx()
        assert h.handle_config(ctx, ParsedCommand("config", "/config")) is True
        out = _printed(ctx)
        assert "允许读目录:" in out and "允许写目录:" in out
        assert "路径超出允许范围" in out
        ctx.record_command.assert_called_once_with("config")

    def test_registered(self):
        assert h.COMMAND_HANDLERS["config"] is h.handle_config
