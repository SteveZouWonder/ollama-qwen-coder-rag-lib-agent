#!/usr/bin/env python3
"""test_cli_handlers_model.py — CLI ``/model`` 命令（显示 / list / 热切换）。"""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import query_interface as qi
from query_interface import ParsedCommand


def _parsed(arg=""):
    raw = f"/model {arg}".strip()
    return ParsedCommand("model", raw, arg)


def _ctx():
    return SimpleNamespace(rag_engine=MagicMock(), react_engine=MagicMock(host="http://h:1"))


def _printed(mock_console):
    return "\n".join(str(c.args[0]) for c in mock_console.print.call_args_list if c.args)


class TestHandleModelShow:
    @patch("query_interface.record_command_execution")
    @patch("query_interface.console")
    @patch("model_switcher.current_model_info")
    def test_show_loaded_with_other_resident(self, mock_info, mock_console, _rec):
        mock_info.return_value = {
            "model": "qwen3.5:4b", "num_ctx": 16384, "think": False, "loaded": True,
            "size_bytes": 4 * 1024 ** 3, "loaded_models": ["qwen3.5:4b", "qwen3.5:9b"],
        }
        assert qi.handle_model(_ctx(), _parsed("")) is True
        out = _printed(mock_console)
        assert "qwen3.5:4b" in out
        assert "4.0 GB" in out
        assert "num_ctx=16384" in out
        assert "qwen3.5:9b" in out  # 提示其他驻留模型
        assert "/model <name>" in out

    @patch("query_interface.record_command_execution")
    @patch("query_interface.console")
    @patch("model_switcher.current_model_info")
    def test_show_not_loaded(self, mock_info, mock_console, _rec):
        mock_info.return_value = {
            "model": "qwen3.5:4b", "num_ctx": 16384, "think": True, "loaded": False,
            "size_bytes": 0, "loaded_models": [],
        }
        qi.handle_model(_ctx(), _parsed(""))
        out = _printed(mock_console)
        assert "未加载" in out
        assert "思考模式: 开" in out


class TestHandleModelList:
    @patch("query_interface.record_command_execution")
    @patch("query_interface.console")
    @patch("model_switcher.list_loaded_models", return_value=[{"name": "qwen3.5:4b"}])
    @patch("model_switcher.list_installed_models", return_value=["qwen3.5:4b", "qwen3.5:9b"])
    def test_list_marks_current_and_loaded(self, _inst, _loaded, mock_console, _rec):
        with patch.object(qi.Config, "LLM_MODEL", "qwen3.5:4b"):
            qi.handle_model(_ctx(), _parsed("list"))
        out = _printed(mock_console)
        assert "qwen3.5:4b  [当前/已加载]" in out
        assert "- qwen3.5:9b" in out

    @patch("query_interface.record_command_execution")
    @patch("query_interface.console")
    @patch("model_switcher.list_installed_models", return_value=[])
    def test_list_when_ollama_down(self, _inst, mock_console, _rec):
        qi.handle_model(_ctx(), _parsed("ls"))
        assert "无法获取模型列表" in _printed(mock_console)


class TestHandleModelSwitch:
    @patch("query_interface.record_command_execution")
    @patch("query_interface.console")
    @patch("model_switcher.switch_model")
    def test_switch_passes_ctx_engines(self, mock_switch, mock_console, _rec):
        mock_switch.return_value = SimpleNamespace(ok=True, message="已切换到 qwen3.5:9b")
        ctx = _ctx()
        assert qi.handle_model(ctx, _parsed("qwen3.5:9b")) is True
        mock_switch.assert_called_once_with(
            "qwen3.5:9b", rag_engine=ctx.rag_engine, react_engine=ctx.react_engine
        )
        assert "已切换到 qwen3.5:9b" in _printed(mock_console)

    @patch("query_interface.record_command_execution")
    @patch("query_interface.console")
    @patch("model_switcher.switch_model")
    def test_switch_failure_printed_red(self, mock_switch, mock_console, _rec):
        mock_switch.return_value = SimpleNamespace(ok=False, message="模型 'x' 未安装")
        qi.handle_model(_ctx(), _parsed("x"))
        out = _printed(mock_console)
        assert "[red]" in out
        assert "未安装" in out
