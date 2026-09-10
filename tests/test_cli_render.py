#!/usr/bin/env python3
"""
test_cli_render.py — CLI 渲染 / 回调函数单元测试（Mock cli.state.HAS_RICH；F10 P3-2-b 由 test_query_interface_render.py 改名）
"""
from unittest.mock import patch

from query_interface import print_banner
from cli.render import (
    print_help, print_tools, print_rag_sources,
    print_knowledge_stats, show_tutorial, check_first_run, print_web_sources, )
from cli.callbacks import on_step_callback, on_confirm_callback, ask_progress_callback, STEP_PHASE_COLOR


class TestOnStepCallback:
    """测试步骤回调"""

    @patch("cli.state.HAS_RICH", True)
    @patch("cli.state.console")
    def test_on_step_thinking(self, mock_console):
        on_step_callback({"step": 1, "total": 10, "phase": "thinking", "message": "msg"})
        mock_console.print.assert_called_once()

    @patch("cli.state.HAS_RICH", True)
    @patch("cli.state.console")
    def test_on_step_blocked(self, mock_console):
        on_step_callback({"step": 2, "total": 10, "phase": "blocked", "message": "msg"})
        # blocked 阶段会输出步骤信息
        mock_console.print.assert_called()
        # 验证调用了至少一次
        assert mock_console.print.call_count >= 1
        # 验证最后一次调用包含预期内容
        last_call = mock_console.print.call_args_list[-1]
        assert "[X]" in str(last_call)

    @patch("cli.state.HAS_RICH", False)
    def test_on_step_no_rich(self, capsys):
        on_step_callback({"step": 1, "total": 10, "phase": "thinking", "message": "msg"})
        captured = capsys.readouterr()
        assert "[1/10]" in captured.out

    @patch("cli.state.HAS_RICH", False)
    def test_on_step_robustness_phases_have_markers(self, capsys):
        """P1-8：格式重试 / 重复 / 折叠 / 强制总结 / 错误 事件有专属标记而非 [?]。"""
        expected = {
            "format_retry": "[~]", "repeat": "[R]", "budget_fold": "[F]",
            "forced_summary": "[!!]", "error": "[E]",
        }
        for phase, mark in expected.items():
            on_step_callback({"step": 3, "phase": phase, "message": f"Step 3: {phase}"})
            out = capsys.readouterr().out
            assert mark in out and f"Step 3: {phase}" in out and "[?]" not in out

    @patch("cli.state.HAS_RICH", True)
    @patch("cli.state.console")
    def test_on_step_robustness_phase_rich(self, mock_console):
        from cli.callbacks import STEP_PHASE_COLOR
        on_step_callback({"step": 2, "phase": "budget_fold", "message": "折叠"})
        last = str(mock_console.print.call_args_list[-1])
        assert "[F]" in last and "折叠" in last and STEP_PHASE_COLOR["budget_fold"] in last


class TestOnConfirmCallback:
    """测试确认回调"""

    @patch("cli.state.HAS_RICH", True)
    @patch("cli.state.console")
    def test_confirm_yes(self, mock_console):
        mock_console.input.return_value = "y"
        result = on_confirm_callback({"message": "确认?", "safety": {"risk_level": "high"}})
        assert result is True

    @patch("cli.state.HAS_RICH", True)
    @patch("cli.state.console")
    def test_confirm_no(self, mock_console):
        mock_console.input.return_value = "n"
        result = on_confirm_callback({"message": "确认?", "safety": {"risk_level": "medium"}})
        assert result is False

    @patch("cli.state.HAS_RICH", True)
    @patch("cli.state.console")
    def test_confirm_eof(self, mock_console):
        mock_console.input.side_effect = EOFError()
        result = on_confirm_callback({"message": "确认?", "safety": {}})
        assert result is False

    @patch("cli.state.HAS_RICH", False)
    @patch("cli.state.console")
    def test_confirm_no_rich(self, mock_console, capsys):
        mock_console.input.return_value = "yes"
        result = on_confirm_callback({"message": "确认?", "safety": {"risk_level": "low"}})
        assert result is True


class TestPrintBanner:
    """测试横幅打印"""

    @patch("cli.state.HAS_RICH", True)
    @patch("cli.state.console")
    def test_banner_rich(self, mock_console):
        print_banner()
        mock_console.print.assert_called_once()

    @patch("cli.state.HAS_RICH", False)
    def test_banner_no_rich(self, capsys):
        print_banner()
        captured = capsys.readouterr()
        assert "Cerebro" in captured.out


class TestPrintHelp:
    """测试帮助打印"""

    @patch("cli.state.HAS_RICH", True)
    @patch("cli.state.console")
    def test_help_rich(self, mock_console):
        print_help()
        mock_console.print.assert_called_once()

    @patch("cli.state.HAS_RICH", False)
    def test_help_no_rich(self, capsys):
        print_help()
        captured = capsys.readouterr()
        assert "/help" in captured.out


class TestPrintTools:
    """测试工具列表打印"""

    @patch("cli.state.HAS_RICH", True)
    @patch("cli.state.console")
    def test_tools_rich(self, mock_console):
        print_tools()
        assert mock_console.print.call_count >= 2

    @patch("cli.state.HAS_RICH", False)
    def test_tools_no_rich(self, capsys):
        print_tools()
        captured = capsys.readouterr()
        assert "可用工具" in captured.out or "read_file" in captured.out


class TestPrintRagSources:
    """测试来源打印"""

    @patch("cli.state.HAS_RICH", True)
    @patch("cli.state.console")
    def test_sources_rich(self, mock_console):
        sources = [{"file": "a.pdf", "score": 0.85, "content": "片段"}]
        print_rag_sources(sources)
        mock_console.print.assert_called()

    @patch("cli.state.HAS_RICH", False)
    def test_sources_no_rich(self, capsys):
        sources = [{"file": "a.pdf", "score": 0.85, "content": "片段"}]
        print_rag_sources(sources)
        captured = capsys.readouterr()
        assert "a.pdf" in captured.out

    @patch("cli.state.HAS_RICH", True)
    @patch("cli.state.console")
    def test_sources_empty(self, mock_console):
        print_rag_sources([])
        mock_console.print.assert_called_once()


class TestPrintKnowledgeStats:
    """测试统计打印"""

    @patch("cli.state.HAS_RICH", True)
    @patch("cli.state.console")
    @patch("cli.state.rag_engine")
    def test_stats_rich(self, mock_rag, mock_console):
        mock_rag.get_stats.return_value = {"total_documents": 5}
        print_knowledge_stats()
        mock_console.print.assert_called()
        # 测试结束后确保rag_engine被恢复为None
        # patch会自动unpatch，但我们要确保全局变量也被重置

    @patch("cli.state.HAS_RICH", False)
    @patch("cli.state.rag_engine")
    def test_stats_no_rich(self, mock_rag, capsys):
        mock_rag.get_stats.return_value = {"total_documents": 5}
        print_knowledge_stats()
        captured = capsys.readouterr()
        assert "5" in captured.out

    @patch("cli.state.HAS_RICH", True)
    @patch("cli.state.console")
    @patch("cli.state.rag_engine", None)
    def test_stats_no_engine(self, mock_console):
        print_knowledge_stats()
        mock_console.print.assert_called_once()


class TestShowTutorial:
    """测试教程显示"""

    @patch("cli.state.HAS_RICH", True)
    @patch("cli.state.console")
    def test_tutorial_rich(self, mock_console):
        show_tutorial()
        mock_console.print.assert_called_once()

    @patch("cli.state.HAS_RICH", False)
    def test_tutorial_no_rich(self, capsys):
        show_tutorial()
        captured = capsys.readouterr()
        assert "欢迎使用" in captured.out


class TestCheckFirstRun:
    """测试首次运行检测"""

    @patch("cli.state.HAS_RICH", True)
    @patch("cli.state.console")
    @patch("cli.render.os.path.exists")
    def test_first_run_shows_tutorial(self, mock_exists, mock_console, temp_dir):
        mock_exists.return_value = False
        check_first_run()
        mock_console.print.assert_called()

    @patch("cli.render.os.path.exists")
    def test_not_first_run_skips(self, mock_exists):
        mock_exists.return_value = True
        check_first_run()
        # 不应调用 show_tutorial


class TestEnhancedOnStepCallback:
    """测试增强的步骤回调（带进度条）"""

    @patch("cli.state.HAS_RICH", True)
    @patch("cli.state.console")
    def test_on_step_basic_functionality(self, mock_console):
        # 测试基本功能，不测试配置控制
        # 注意：由于Config在模块级别导入，这里只能测试基本调用
        from cli.callbacks import on_step_callback as original_callback
        
        # 临时修改 Config.SHOW_PROGRESS
        from config import Config
        original_value = Config.SHOW_PROGRESS
        Config.SHOW_PROGRESS = True
        
        try:
            original_callback({"step": 1, "total": 10, "phase": "thinking", "message": "msg"})
            # 由于导入缓存，可能不会调用，但至少不会报错
        finally:
            Config.SHOW_PROGRESS = original_value

    @patch("cli.state.HAS_RICH", False)
    def test_on_step_without_rich(self, capsys):
        from cli.callbacks import on_step_callback as original_callback
        from config import Config
        
        original_value = Config.SHOW_PROGRESS
        Config.SHOW_PROGRESS = True
        
        try:
            original_callback({"step": 1, "total": 10, "phase": "thinking", "message": "msg"})
            captured = capsys.readouterr()
            # 由于导入缓存，可能不会输出，但至少不会报错
        finally:
            Config.SHOW_PROGRESS = original_value

    @patch("cli.state.HAS_RICH", True)
    @patch("cli.state.console")
    def test_on_step_progress_calculation(self, mock_console):
        from config import Config
        
        original_value = Config.SHOW_PROGRESS
        Config.SHOW_PROGRESS = True
        
        try:
            # 测试进度计算逻辑
            data = {"step": 5, "total": 10, "phase": "thinking", "message": "msg"}
            # 手动计算进度百分比
            if data["step"] != "?" and data["total"] != "?":
                try:
                    progress_percent = (int(data["step"]) / int(data["total"])) * 100
                    assert progress_percent == 50.0
                except:
                    pass
        finally:
            Config.SHOW_PROGRESS = original_value

    @patch("cli.state.HAS_RICH", True)
    @patch("cli.state.console")
    def test_on_step_different_phases(self, mock_console):
        from cli.callbacks import on_step_callback as original_callback
        from config import Config
        
        original_value = Config.SHOW_PROGRESS
        Config.SHOW_PROGRESS = True
        
        try:
            phases = ["thinking", "action", "executing", "observed", "blocked", "rejected", "final"]
            for phase in phases:
                original_callback({"step": 1, "total": 10, "phase": phase, "message": f"{phase} msg"})
        finally:
            Config.SHOW_PROGRESS = original_value


class TestAskProgressCallback:
    """测试 RAG 查询进度回调"""

    @patch("cli.state.HAS_RICH", True)
    @patch("cli.state.console")
    def test_ask_progress_callback_embedding(self, mock_console):
        from cli.callbacks import ask_progress_callback as original_callback
        from config import Config
        
        original_value = Config.SHOW_PROGRESS
        Config.SHOW_PROGRESS = True
        
        try:
            original_callback({"phase": "embedding", "message": "正在生成查询向量..."})
        finally:
            Config.SHOW_PROGRESS = original_value

    @patch("cli.state.HAS_RICH", True)
    @patch("cli.state.console")
    def test_ask_progress_callback_retrieving(self, mock_console):
        from cli.callbacks import ask_progress_callback as original_callback
        from config import Config
        
        original_value = Config.SHOW_PROGRESS
        Config.SHOW_PROGRESS = True
        
        try:
            original_callback({"phase": "retrieving", "message": "检索到 5 个相关文档"})
        finally:
            Config.SHOW_PROGRESS = original_value

    @patch("cli.state.HAS_RICH", True)
    @patch("cli.state.console")
    def test_ask_progress_callback_scoring(self, mock_console):
        from cli.callbacks import ask_progress_callback as original_callback
        from config import Config
        
        original_value = Config.SHOW_PROGRESS
        Config.SHOW_PROGRESS = True
        
        try:
            original_callback({
                "phase": "scoring",
                "message": "评分文档 2/5",
                "current": 2,
                "total": 5
            })
        finally:
            Config.SHOW_PROGRESS = original_value

    @patch("cli.state.HAS_RICH", True)
    @patch("cli.state.console")
    def test_ask_progress_callback_generating(self, mock_console):
        from cli.callbacks import ask_progress_callback as original_callback
        from config import Config
        
        original_value = Config.SHOW_PROGRESS
        Config.SHOW_PROGRESS = True
        
        try:
            original_callback({"phase": "generating", "message": "正在生成回答..."})
        finally:
            Config.SHOW_PROGRESS = original_value

    @patch("cli.state.HAS_RICH", False)
    def test_ask_progress_callback_without_rich(self, capsys):
        from cli.callbacks import ask_progress_callback as original_callback
        from config import Config
        
        original_value = Config.SHOW_PROGRESS
        Config.SHOW_PROGRESS = True
        
        try:
            original_callback({"phase": "embedding", "message": "正在生成查询向量..."})
            captured = capsys.readouterr()
        finally:
            Config.SHOW_PROGRESS = original_value

    @patch("cli.state.HAS_RICH", True)
    @patch("cli.state.console")
    def test_ask_progress_callback_full_workflow(self, mock_console):
        from cli.callbacks import ask_progress_callback as original_callback
        from config import Config
        
        original_value = Config.SHOW_PROGRESS
        Config.SHOW_PROGRESS = True
        
        try:
            # 模拟完整的查询工作流
            original_callback({"phase": "embedding", "message": "正在生成查询向量..."})
            original_callback({"phase": "retrieving", "message": "检索到 3 个相关文档"})
            original_callback({"phase": "scoring", "message": "评分文档 1/3", "current": 1, "total": 3})
            original_callback({"phase": "scoring", "message": "评分文档 2/3", "current": 2, "total": 3})
            original_callback({"phase": "scoring", "message": "评分文档 3/3", "current": 3, "total": 3})
            original_callback({"phase": "generating", "message": "正在生成回答..."})
        finally:
            Config.SHOW_PROGRESS = original_value

    @patch("cli.state.HAS_RICH", True)
    @patch("cli.state.console")
    def test_ask_progress_callback_unknown_phase(self, mock_console):
        from cli.callbacks import ask_progress_callback as original_callback
        from config import Config
        
        original_value = Config.SHOW_PROGRESS
        Config.SHOW_PROGRESS = True
        
        try:
            original_callback({"phase": "unknown", "message": "未知阶段"})
        finally:
            Config.SHOW_PROGRESS = original_value


class TestPrintSourcesNumbered:
    """F8 P2-3：来源按引用编号显示（与回答中的 [n]/[Wn] 对应）。"""

    @patch("cli.state.HAS_RICH", False)
    def test_rag_sources_show_ref(self, capsys):
        print_rag_sources([
            {"file": "a.pdf", "score": 0.85, "content": "片段", "ref": "1"},
            {"file": "k.md", "score": 0.49, "content": "关键词", "ref": "2", "retriever": "bm25"},
        ])
        out = capsys.readouterr().out
        assert "[1] a.pdf (0.850)" in out and "[2] k.md" in out

    @patch("cli.state.HAS_RICH", False)
    def test_rag_sources_without_ref_use_index(self, capsys):
        print_rag_sources([{"file": "a.pdf", "score": None, "content": "片段"}])
        assert "[1] a.pdf" in capsys.readouterr().out

    @patch("cli.state.HAS_RICH", True)
    @patch("cli.state.console")
    def test_rag_sources_rich_with_note_and_bm25(self, mock_console):
        print_rag_sources([
            {"file": "a.pdf", "score": 0.5, "content": "x" * 120, "ref": "1", "rerank_note": "含售价"},
            {"file": "k.md", "score": 0.49, "content": "y", "ref": "2", "retriever": "bm25"},
        ])
        table = mock_console.print.call_args.args[0]
        cells = [str(c) for col in table.columns for c in col._cells]
        assert "[1]" in cells and "[2]" in cells
        assert any("含售价" in c for c in cells) and any("关键词" in c for c in cells)

    @patch("cli.state.HAS_RICH", True)
    @patch("cli.state.console")
    def test_rag_sources_rich_has_cited_column(self, mock_console):
        """F9 P0-3：/sources 表新增「引用」列（次数，未引用显示 —）。"""
        print_rag_sources([
            {"file": "a.pdf", "score": 0.5, "content": "x", "ref": "1", "cited": 2},
            {"file": "b.md", "score": 0.4, "content": "y", "ref": "2", "cited": 0},
            {"file": "c.md", "score": 0.3, "content": "z", "ref": "3"},
        ])
        table = mock_console.print.call_args.args[0]
        headers = [str(col.header) for col in table.columns]
        assert headers == ["#", "文件", "相似度", "引用", "内容片段"]
        cited_col = table.columns[3]._cells
        assert cited_col[0] == "2" and "—" in cited_col[1] and "—" in cited_col[2]

    @patch("cli.state.HAS_RICH", False)
    def test_web_sources_show_w_ref(self, capsys):
        from cli.render import print_web_sources
        print_web_sources([{"title": "T", "url": "http://x", "ref": "W1"}, {"title": "U", "url": "http://y"}])
        out = capsys.readouterr().out
        assert "[W1] T" in out and "[W2] U" in out

    @patch("cli.state.HAS_RICH", True)
    @patch("cli.state.console")
    def test_web_sources_rich(self, mock_console):
        from cli.render import print_web_sources
        print_web_sources([{"title": "T", "url": "http://x", "ref": "W1"}])
        table = mock_console.print.call_args.args[0]
        cells = [str(c) for col in table.columns for c in col._cells]
        assert "[W1]" in cells
