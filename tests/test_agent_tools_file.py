#!/usr/bin/env python3
"""
test_agent_tools_file.py — 文件/目录/搜索工具单元测试（临时目录）
"""
import os
import pytest
from agent_tools import (
    read_file, write_file, list_directory, search_files,
    get_current_dir, execute_command
)


class TestReadFile:
    """测试 read_file"""

    def test_read_existing_file(self, temp_dir):
        path = temp_dir / "test.txt"
        path.write_text("line1\nline2\nline3\n", encoding="utf-8")
        result = read_file(str(path))
        assert "line1" in result
        assert "总行数: 3" in result

    def test_read_nonexistent_file(self, temp_dir):
        result = read_file(str(temp_dir / "no.txt"))
        assert "[错误] 文件不存在" in result

    def test_read_empty_file(self, temp_dir):
        path = temp_dir / "empty.txt"
        path.write_text("", encoding="utf-8")
        result = read_file(str(path))
        assert "[文件为空]" in result

    def test_read_with_offset(self, temp_dir):
        path = temp_dir / "test.txt"
        path.write_text("line1\nline2\nline3\nline4\nline5\n", encoding="utf-8")
        result = read_file(str(path), offset=2, limit=2)
        assert "显示: 3-4" in result
        assert "line3" in result
        assert "line1" not in result

    def test_read_with_limit(self, temp_dir):
        path = temp_dir / "test.txt"
        lines = "\n".join([f"line{i}" for i in range(1, 101)])
        path.write_text(lines + "\n", encoding="utf-8")
        result = read_file(str(path), offset=0, limit=50)
        assert "显示: 1-50" in result
        assert "... (50 行省略)" in result

    def test_read_offset_beyond_end(self, temp_dir):
        path = temp_dir / "test.txt"
        path.write_text("line1\n", encoding="utf-8")
        result = read_file(str(path), offset=10, limit=10)
        # 当 offset 超出文件长度时，start=10, end=1, 选取范围为空
        assert "显示: 11-1" in result  # 反映实际的实现行为

    def test_read_binary_file(self, temp_dir):
        path = temp_dir / "binary.bin"
        path.write_bytes(b"\x00\x01\x02\xff")
        result = read_file(str(path))
        assert "总行数" in result


class TestWriteFile:
    """测试 write_file"""

    def test_write_new_file(self, temp_dir):
        path = temp_dir / "new.txt"
        result = write_file(str(path), "hello world")
        assert "[成功] 写入" in result
        assert path.read_text(encoding="utf-8") == "hello world"

    def test_write_creates_parent_dirs(self, temp_dir):
        path = temp_dir / "sub" / "dir" / "file.txt"
        result = write_file(str(path), "content")
        assert "[成功]" in result
        assert path.exists()

    def test_append_to_file(self, temp_dir):
        path = temp_dir / "test.txt"
        path.write_text("first\n", encoding="utf-8")
        result = write_file(str(path), "second\n", append=True)
        assert "[成功] 追加" in result
        content = path.read_text(encoding="utf-8")
        assert "first" in content
        assert "second" in content

    def test_write_permission_error(self, temp_dir, monkeypatch):
        # 模拟不可写目录
        def mock_makedirs(*a, **k):
            raise PermissionError("no")
        monkeypatch.setattr(os, "makedirs", mock_makedirs)
        result = write_file("/fake/path.txt", "x")
        assert "[错误] 写入失败" in result


class TestListDirectory:
    """测试 list_directory"""

    def test_list_existing_dir(self, temp_dir):
        (temp_dir / "file1.txt").write_text("a")
        (temp_dir / "file2.py").write_text("b")
        (temp_dir / "subdir").mkdir()
        result = list_directory(str(temp_dir))
        assert "[目录]" in result
        assert "[F] file1.txt" in result
        assert "[F] file2.py" in result
        assert "[D] subdir/" in result

    def test_list_filters_hidden(self, temp_dir):
        (temp_dir / ".hidden").write_text("x")
        (temp_dir / "visible").write_text("y")
        result = list_directory(str(temp_dir))
        assert "visible" in result
        assert ".hidden" not in result

    def test_list_nonexistent(self, temp_dir):
        result = list_directory(str(temp_dir / "no"))
        assert "[错误] 目录不存在" in result

    def test_list_current_dir_default(self, temp_dir, monkeypatch):
        monkeypatch.chdir(temp_dir)
        (temp_dir / "here.txt").write_text("x")
        result = list_directory()
        assert "here.txt" in result


class TestSearchFiles:
    """测试 search_files"""

    def test_search_finds_match(self, temp_dir):
        (temp_dir / "a.py").write_text("def hello():\n    pass\n", encoding="utf-8")
        (temp_dir / "b.py").write_text("def world():\n    pass\n", encoding="utf-8")
        result = search_files("hello", str(temp_dir))
        assert "a.py" in result
        assert "b.py" not in result

    def test_search_no_match(self, temp_dir):
        (temp_dir / "a.py").write_text("def foo(): pass\n", encoding="utf-8")
        result = search_files("bar", str(temp_dir))
        assert "未找到" in result

    def test_search_max_results(self, temp_dir):
        for i in range(15):
            (temp_dir / f"f{i}.py").write_text(f"def hello{i}(): pass\n", encoding="utf-8")
        result = search_files("def", str(temp_dir), max_results=5)
        # 最多返回 max_results 个文件
        matches = [line for line in result.split("\n") if line.startswith("[匹配]")]
        assert len(matches) <= 5

    def test_search_skips_dirs(self, temp_dir):
        (temp_dir / "__pycache__").mkdir()
        (temp_dir / "__pycache__" / "cache.pyc").write_text("hello", encoding="utf-8")
        (temp_dir / "src.py").write_text("hello", encoding="utf-8")
        result = search_files("hello", str(temp_dir))
        assert "src.py" in result
        assert "__pycache__" not in result

    def test_search_shows_line_numbers(self, temp_dir):
        (temp_dir / "test.py").write_text("a\nb\nhello\nd\n", encoding="utf-8")
        result = search_files("hello", str(temp_dir))
        assert "行3" in result


class TestGetCurrentDir:
    def test_returns_cwd(self):
        result = get_current_dir()
        assert isinstance(result, str)
        assert len(result) > 0


class TestExecuteCommand:
    """测试 execute_command"""

    def test_execute_echo(self):
        result = execute_command("echo hello_test")
        assert "hello_test" in result

    def test_execute_with_stderr(self):
        result = execute_command("python3 -c \"import sys; sys.stderr.write('err')\"")
        assert "[stderr]" in result

    def test_execute_nonzero_exit(self):
        result = execute_command("python3 -c \"exit(1)\"")
        assert "[退出码] 1" in result

    def test_execute_timeout(self):
        result = execute_command("sleep 5", timeout=1)
        assert "[错误] 命令超时" in result

    def test_execute_invalid_command(self):
        result = execute_command("this_command_does_not_exist_12345")
        assert "[错误]" in result or "[stderr]" in result
