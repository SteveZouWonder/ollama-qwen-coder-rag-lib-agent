#!/usr/bin/env python3
"""
test_query_interface_parse.py — 命令解析纯函数单元测试（目标 100% 分支覆盖）
"""
import pytest
from query_interface import parse_command, classify_mode, ParsedCommand


class TestParseCommandEmpty:
    def test_empty_string(self):
        result = parse_command("")
        assert result.cmd_type == "empty"
        assert result.raw == ""

    def test_whitespace_only(self):
        result = parse_command("   \t\n  ")
        assert result.cmd_type == "empty"


class TestParseCommandQuit:
    @pytest.mark.parametrize("inp", ["/exit", "/quit", "exit", "quit"])
    def test_quit_variants(self, inp):
        result = parse_command(inp)
        assert result.cmd_type == "quit"


class TestParseCommandNoArg:
    """测试无参数命令"""

    def test_help(self):
        assert parse_command("/help").cmd_type == "help"

    def test_tutorial(self):
        assert parse_command("/tutorial").cmd_type == "tutorial"

    def test_tools(self):
        assert parse_command("/tools").cmd_type == "tools"

    def test_stats(self):
        assert parse_command("/stats").cmd_type == "stats"

    def test_sources(self):
        assert parse_command("/sources").cmd_type == "sources"

    def test_clear(self):
        assert parse_command("/clear").cmd_type == "clear"

    def test_history(self):
        assert parse_command("/history").cmd_type == "history"

    def test_summary(self):
        assert parse_command("/summary").cmd_type == "summary"

    def test_reset(self):
        assert parse_command("/reset").cmd_type == "reset"

    def test_pwd(self):
        assert parse_command("/pwd").cmd_type == "pwd"

    def test_model(self):
        assert parse_command("/model").cmd_type == "model"


class TestParseCommandWithArg:
    """测试带参数命令"""

    def test_ask(self):
        r = parse_command("/ask 什么是RAG？")
        assert r.cmd_type == "ask"
        assert r.arg == "什么是RAG？"

    def test_ask_no_arg(self):
        r = parse_command("/ask")
        assert r.cmd_type == "ask"
        assert r.arg == ""

    def test_agent(self):
        r = parse_command("/agent 检查代码")
        assert r.cmd_type == "agent"
        assert r.arg == "检查代码"

    def test_add(self):
        r = parse_command("/add ./论文.pdf")
        assert r.cmd_type == "add"
        assert r.arg == "./论文.pdf"

    def test_file(self):
        r = parse_command("/file main.py")
        assert r.cmd_type == "file"
        assert r.arg == "main.py"

    def test_write(self):
        r = parse_command("/write output.txt")
        assert r.cmd_type == "write"
        assert r.arg == "output.txt"

    def test_exec(self):
        r = parse_command("/exec ls -la")
        assert r.cmd_type == "exec"
        assert r.arg == "ls -la"

    def test_cd(self):
        r = parse_command("/cd /tmp")
        assert r.cmd_type == "cd"
        assert r.arg == "/tmp"

    def test_arg_with_multiple_spaces(self):
        r = parse_command("/ask   什么是   RAG？  ")
        assert r.cmd_type == "ask"
        assert r.arg == "什么是   RAG？"


class TestParseCommandUnknown:
    """测试未知命令"""

    def test_unknown_slash_command(self):
        r = parse_command("/unknown something")
        assert r.cmd_type == "unknown_cmd"
        assert r.raw == "/unknown something"
        assert r.arg == "something"

    def test_unknown_slash_no_arg(self):
        r = parse_command("/foobar")
        assert r.cmd_type == "unknown_cmd"
        assert r.arg == ""


class TestParseCommandNatural:
    """测试自然语言输入"""

    def test_plain_text(self):
        r = parse_command("你好，请帮我写代码")
        assert r.cmd_type == "natural"
        assert r.arg == "你好，请帮我写代码"

    def test_text_with_numbers(self):
        r = parse_command("12345")
        assert r.cmd_type == "natural"

    def test_text_with_special_chars(self):
        r = parse_command("hello! @#$% world")
        assert r.cmd_type == "natural"


class TestParsedCommandEquality:
    def test_equal(self):
        assert ParsedCommand("ask", "/ask x", "x") == ParsedCommand("ask", "/ask y", "x")

    def test_not_equal_type(self):
        assert ParsedCommand("ask", "", "") != ParsedCommand("agent", "", "")

    def test_not_equal_arg(self):
        assert ParsedCommand("ask", "", "a") != ParsedCommand("ask", "", "b")

    def test_not_equal_other_type(self):
        assert ParsedCommand("ask", "", "") != "ask"

    def test_repr(self):
        r = ParsedCommand("ask", "/ask x", "x")
        assert "ask" in repr(r)
        assert "x" in repr(r)


class TestClassifyMode:
    """测试模式分类"""

    def test_cmd_types(self):
        for cmd_type in ["help", "tutorial", "tools", "stats", "sources",
                         "clear", "history", "summary", "reset",
                         "pwd", "cd", "model", "quit", "empty", "unknown_cmd"]:
            assert classify_mode(True, ParsedCommand(cmd_type, "")) == "cmd"
            assert classify_mode(False, ParsedCommand(cmd_type, "")) == "cmd"

    def test_ask_always_rag(self):
        assert classify_mode(True, ParsedCommand("ask", "", "q")) == "rag"
        assert classify_mode(False, ParsedCommand("ask", "", "q")) == "rag"

    def test_add_always_rag(self):
        assert classify_mode(True, ParsedCommand("add", "", "f")) == "rag"
        assert classify_mode(False, ParsedCommand("add", "", "f")) == "rag"

    def test_agent_always_agent(self):
        assert classify_mode(True, ParsedCommand("agent", "", "t")) == "agent"
        assert classify_mode(False, ParsedCommand("agent", "", "t")) == "agent"

    def test_file_write_exec_always_agent(self):
        for ct in ["file", "write", "exec"]:
            assert classify_mode(True, ParsedCommand(ct, "", "a")) == "agent"
            assert classify_mode(False, ParsedCommand(ct, "", "a")) == "agent"

    def test_natural_with_rag(self):
        assert classify_mode(True, ParsedCommand("natural", "", "hello")) == "rag"

    def test_natural_without_rag(self):
        assert classify_mode(False, ParsedCommand("natural", "", "hello")) == "agent"

    def test_unexpected_type(self):
        assert classify_mode(True, ParsedCommand("weird", "", "")) == "noop"
