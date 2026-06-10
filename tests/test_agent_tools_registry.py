#!/usr/bin/env python3
"""
test_agent_tools_registry.py — ToolRegistry 单元测试
"""
import pytest
from agent_tools import ToolRegistry


def dummy_func(x: str) -> str:
    return f"result: {x}"


def unsafe_func(x: str) -> str:
    return f"modified: {x}"


class TestToolRegistryRegister:
    """测试工具注册"""

    def test_register_tool(self):
        reg = ToolRegistry()
        reg.register("test_tool", dummy_func, "测试工具", {"x": "参数"}, safe=True)
        assert "test_tool" in reg.tools
        assert reg.tools["test_tool"]["description"] == "测试工具"
        assert reg.tools["test_tool"]["safe"] is True

    def test_register_unsafe_tool(self):
        reg = ToolRegistry()
        reg.register("write", unsafe_func, "写入工具", {"x": "参数"}, safe=False)
        assert reg.tools["write"]["safe"] is False

    def test_get_descriptions_contains_tool_name(self):
        reg = ToolRegistry()
        reg.register("read", dummy_func, "读取文件", {"path": "路径"}, safe=True)
        desc = reg.get_descriptions()
        assert "read" in desc
        assert "读取文件" in desc
        assert "[安全]" in desc

    def test_get_descriptions_contains_unsafe_tag(self):
        reg = ToolRegistry()
        reg.register("delete", unsafe_func, "删除文件", {"path": "路径"}, safe=False)
        desc = reg.get_descriptions()
        assert "[需确认]" in desc

    def test_get_descriptions_contains_params(self):
        reg = ToolRegistry()
        reg.register("read", dummy_func, "读取", {"path": "路径", "offset": "偏移"}, safe=True)
        desc = reg.get_descriptions()
        assert "path" in desc
        assert "offset" in desc

    def test_get_descriptions_no_params(self):
        reg = ToolRegistry()
        reg.register("noop", lambda: "ok", "无参", {}, safe=True)
        desc = reg.get_descriptions()
        assert "参数: 无" in desc


class TestToolRegistryExecute:
    """测试工具执行"""

    def test_execute_safe_tool(self):
        reg = ToolRegistry()
        reg.register("echo", dummy_func, "回声", {"x": "输入"}, safe=True)
        result = reg.execute("echo", {"x": "hello"}, auto_confirm=False)
        assert result == "result: hello"

    def test_execute_unknown_tool(self):
        reg = ToolRegistry()
        result = reg.execute("unknown", {}, auto_confirm=False)
        assert "[错误] 未知工具" in result

    def test_execute_unsafe_without_confirm(self):
        reg = ToolRegistry()
        reg.register("write", unsafe_func, "写入", {"x": "输入"}, safe=False)
        result = reg.execute("write", {"x": "data"}, auto_confirm=False)
        assert "[CONFIRM_REQUIRED]" in result

    def test_execute_unsafe_with_confirm(self):
        reg = ToolRegistry()
        reg.register("write", unsafe_func, "写入", {"x": "输入"}, safe=False)
        result = reg.execute("write", {"x": "data"}, auto_confirm=True)
        assert result == "modified: data"

    def test_execute_exception_handling(self):
        def bad_func():
            raise ValueError("boom")
        reg = ToolRegistry()
        reg.register("bad", bad_func, "坏的", {}, safe=True)
        result = reg.execute("bad", {}, auto_confirm=False)
        assert "[错误] 工具执行失败" in result
        assert "boom" in result

    def test_execute_result_truncated(self):
        def long_func():
            return "x" * 6000
        reg = ToolRegistry()
        reg.register("long", long_func, "长结果", {}, safe=True)
        result = reg.execute("long", {}, auto_confirm=False)
        assert len(result) == 5000

    def test_list_tools(self):
        reg = ToolRegistry()
        reg.register("a", dummy_func, "A", {}, safe=True)
        reg.register("b", dummy_func, "B", {}, safe=True)
        assert reg.list_tools() == ["a", "b"]
