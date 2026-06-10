#!/usr/bin/env python3
"""
test_query_interface_render.py — 渲染函数单元测试（Mock HAS_RICH）
"""
import pytest
from unittest.mock import MagicMock, patch

from query_interface import (
    print_banner, print_help, print_tools, print_rag_sources,
    print_knowledge_stats, show_tutorial, check_first_run,
    on_step_callback, on_confirm_callback,
)


class TestOnStepCallback:
    """测试步骤回调"""

    @patch("query_interface.HAS_RICH", True)
    @patch("query_interface.console")
    def test_on_step_thinking(self, mock_console):
        on_step_callback({"step": 1, "total": 10, "phase": "thinking", "message": "msg"})
        mock_console.print.assert_called_once()

    @patch("query_interface.HAS_RICH", True)
    @patch("query_interface.console")
    def test_on_step_blocked(self, mock_console):
        on_step_callback({"step": 2, "total": 10, "phase": "blocked", "message": "msg"})
        mock_console.print.assert_called_once()

    @patch("query_interface.HAS_RICH", False)
    def test_on_step_no_rich(self, capsys):
        on_step_callback({"step": 1, "total": 10, "phase": "thinking", "message": "msg"})
        captured = capsys.readouterr()
        assert "[1/10]" in captured.out


class TestOnConfirmCallback:
    """测试确认回调"""

    @patch("query_interface.HAS_RICH", True)
    @patch("query_interface.console")
    def test_confirm_yes(self, mock_console):
        mock_console.input.return_value = "y"
        result = on_confirm_callback({"message": "确认?", "safety": {"risk_level": "high"}})
        assert result is True

    @patch("query_interface.HAS_RICH", True)
    @patch("query_interface.console")
    def test_confirm_no(self, mock_console):
        mock_console.input.return_value = "n"
        result = on_confirm_callback({"message": "确认?", "safety": {"risk_level": "medium"}})
        assert result is False

    @patch("query_interface.HAS_RICH", True)
    @patch("query_interface.console")
    def test_confirm_eof(self, mock_console):
        mock_console.input.side_effect = EOFError()
        result = on_confirm_callback({"message": "确认?", "safety": {}})
        assert result is False

    @patch("query_interface.HAS_RICH", False)
    @patch("query_interface.console")
    def test_confirm_no_rich(self, mock_console, capsys):
        mock_console.input.return_value = "yes"
        result = on_confirm_callback({"message": "确认?", "safety": {"risk_level": "low"}})
        assert result is True


class TestPrintBanner:
    """测试横幅打印"""

    @patch("query_interface.HAS_RICH", True)
    @patch("query_interface.console")
    def test_banner_rich(self, mock_console):
        print_banner()
        mock_console.print.assert_called_once()

    @patch("query_interface.HAS_RICH", False)
    def test_banner_no_rich(self, capsys):
        print_banner()
        captured = capsys.readouterr()
        assert "智能文档+代码助手" in captured.out


class TestPrintHelp:
    """测试帮助打印"""

    @patch("query_interface.HAS_RICH", True)
    @patch("query_interface.console")
    def test_help_rich(self, mock_console):
        print_help()
        mock_console.print.assert_called_once()

    @patch("query_interface.HAS_RICH", False)
    def test_help_no_rich(self, capsys):
        print_help()
        captured = capsys.readouterr()
        assert "/help" in captured.out


class TestPrintTools:
    """测试工具列表打印"""

    @patch("query_interface.HAS_RICH", True)
    @patch("query_interface.console")
    def test_tools_rich(self, mock_console):
        print_tools()
        assert mock_console.print.call_count >= 2

    @patch("query_interface.HAS_RICH", False)
    def test_tools_no_rich(self, capsys):
        print_tools()
        captured = capsys.readouterr()
        assert "可用工具" in captured.out or "read_file" in captured.out


class TestPrintRagSources:
    """测试来源打印"""

    @patch("query_interface.HAS_RICH", True)
    @patch("query_interface.console")
    def test_sources_rich(self, mock_console):
        sources = [{"file": "a.pdf", "score": 0.85, "content": "片段"}]
        print_rag_sources(sources)
        mock_console.print.assert_called()

    @patch("query_interface.HAS_RICH", False)
    def test_sources_no_rich(self, capsys):
        sources = [{"file": "a.pdf", "score": 0.85, "content": "片段"}]
        print_rag_sources(sources)
        captured = capsys.readouterr()
        assert "a.pdf" in captured.out

    @patch("query_interface.HAS_RICH", True)
    @patch("query_interface.console")
    def test_sources_empty(self, mock_console):
        print_rag_sources([])
        mock_console.print.assert_called_once()


class TestPrintKnowledgeStats:
    """测试统计打印"""

    @patch("query_interface.HAS_RICH", True)
    @patch("query_interface.console")
    @patch("query_interface.rag_engine")
    def test_stats_rich(self, mock_rag, mock_console):
        mock_rag.get_stats.return_value = {"total_documents": 5}
        print_knowledge_stats()
        mock_console.print.assert_called()

    @patch("query_interface.HAS_RICH", False)
    @patch("query_interface.rag_engine")
    def test_stats_no_rich(self, mock_rag, capsys):
        mock_rag.get_stats.return_value = {"total_documents": 5}
        print_knowledge_stats()
        captured = capsys.readouterr()
        assert "5" in captured.out

    @patch("query_interface.HAS_RICH", True)
    @patch("query_interface.console")
    @patch("query_interface.rag_engine", None)
    def test_stats_no_engine(self, mock_console):
        print_knowledge_stats()
        mock_console.print.assert_called_once()


class TestShowTutorial:
    """测试教程显示"""

    @patch("query_interface.HAS_RICH", True)
    @patch("query_interface.console")
    def test_tutorial_rich(self, mock_console):
        show_tutorial()
        mock_console.print.assert_called_once()

    @patch("query_interface.HAS_RICH", False)
    def test_tutorial_no_rich(self, capsys):
        show_tutorial()
        captured = capsys.readouterr()
        assert "欢迎使用" in captured.out


class TestCheckFirstRun:
    """测试首次运行检测"""

    @patch("query_interface.HAS_RICH", True)
    @patch("query_interface.console")
    @patch("query_interface.os.path.exists")
    def test_first_run_shows_tutorial(self, mock_exists, mock_console, temp_dir):
        mock_exists.return_value = False
        check_first_run()
        mock_console.print.assert_called()

    @patch("query_interface.os.path.exists")
    def test_not_first_run_skips(self, mock_exists):
        mock_exists.return_value = True
        check_first_run()
        # 不应调用 show_tutorial
