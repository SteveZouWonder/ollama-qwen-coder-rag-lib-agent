#!/usr/bin/env python3
"""test_query_interface_exec_safety.py — CLI ``/exec`` 的安全确认（F10 P0-1-c）。

``CODE_AGENT_AUTO_CONFIRM`` 只放行 low / medium；high 仍须人工确认，
无交互（EOF）时拒绝执行并给出 ``[提示] 高风险命令需人工确认``。
"""
from unittest.mock import MagicMock

import pytest

import query_interface as qi
from query_interface import ParsedCommand


@pytest.fixture
def env(monkeypatch):
    console = MagicMock()
    registry = MagicMock()
    registry.execute.return_value = "ok"
    monkeypatch.setattr("cli.state.console", console)
    monkeypatch.setattr(qi, "registry", registry)
    monkeypatch.setattr(qi, "record_command_execution", MagicMock())
    return console, registry


def _pc(cmd):
    return ParsedCommand("exec", f"/exec {cmd}", cmd)


def _printed(console):
    return "\n".join(str(c.args[0]) for c in console.print.call_args_list if c.args)


class TestExecAutoConfirm:
    def test_auto_confirm_runs_medium(self, env, monkeypatch):
        console, registry = env
        monkeypatch.setattr(qi.Config, "AUTO_CONFIRM", True)
        assert qi.handle_exec(None, _pc("pip install rich")) is True
        console.input.assert_not_called()
        registry.execute.assert_called_once()

    def test_auto_confirm_does_not_run_high(self, env, monkeypatch):
        """AUTO_CONFIRM=true 下 high 命令不执行，且返回提示。"""
        console, registry = env
        console.input.side_effect = EOFError
        monkeypatch.setattr(qi.Config, "AUTO_CONFIRM", True)
        assert qi.handle_exec(None, _pc("rm -rf build")) is False
        registry.execute.assert_not_called()
        assert "高风险命令需人工确认" in _printed(console)

    def test_auto_confirm_high_still_runs_when_user_agrees(self, env, monkeypatch):
        console, registry = env
        console.input.return_value = "y"
        monkeypatch.setattr(qi.Config, "AUTO_CONFIRM", True)
        assert qi.handle_exec(None, _pc("rm -rf build")) is True
        registry.execute.assert_called_once()

    def test_critical_still_blocked(self, env, monkeypatch):
        console, registry = env
        monkeypatch.setattr(qi.Config, "AUTO_CONFIRM", True)
        assert qi.handle_exec(None, _pc("rm -rf /")) is False
        registry.execute.assert_not_called()

    def test_low_needs_no_confirm(self, env, monkeypatch):
        console, registry = env
        monkeypatch.setattr(qi.Config, "AUTO_CONFIRM", False)
        assert qi.handle_exec(None, _pc("ls -la")) is True
        console.input.assert_not_called()
        registry.execute.assert_called_once()

    def test_medium_without_auto_confirm_asks(self, env, monkeypatch):
        console, registry = env
        console.input.return_value = "n"
        monkeypatch.setattr(qi.Config, "AUTO_CONFIRM", False)
        assert qi.handle_exec(None, _pc("mv a b")) is False
        console.input.assert_called_once()
        registry.execute.assert_not_called()
