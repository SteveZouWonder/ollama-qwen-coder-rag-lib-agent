#!/usr/bin/env python3
"""
test_query_interface_interpreter_guard.py

测试 query_interface 的 Python 解释器版本自保护逻辑。

回归背景：当用户用不兼容的系统解释器（如 macOS 自带 Python 3.9）
直接运行 ``python src/query_interface.py`` 时，导入 llama_index 会抛出
``TypeError: unsupported operand type(s) for |``。新增的版本自保护会在加载
第三方依赖前检测版本，必要时自动用项目虚拟环境解释器重新执行。
"""
import os

from query_interface import (
    ensure_compatible_interpreter,
    find_venv_python,
    MIN_PYTHON_VERSION,
)


class TestEnsureCompatibleInterpreter:
    """ensure_compatible_interpreter 决策逻辑测试。"""

    def test_current_version_meets_requirement_returns_ok(self):
        """版本满足要求时返回 ok。"""
        result = ensure_compatible_interpreter(
            version_info=(3, 13, 0),
            env={},
            script_path=__file__,
        )
        assert result == "ok"

    def test_exact_min_version_returns_ok(self):
        """恰好等于最低版本时返回 ok（边界条件）。"""
        result = ensure_compatible_interpreter(
            version_info=(MIN_PYTHON_VERSION[0], MIN_PYTHON_VERSION[1], 0),
            env={},
            script_path=__file__,
        )
        assert result == "ok"

    def test_old_version_with_venv_returns_reexec(self, tmp_path):
        """版本过低且存在 venv 时返回 reexec。"""
        # 构造一个带 venv/bin/python 的临时项目结构
        venv_bin = tmp_path / "venv" / "bin"
        venv_bin.mkdir(parents=True)
        py = venv_bin / "python"
        py.write_text("#!/bin/sh\n")
        os.chmod(py, 0o755)
        fake_script = tmp_path / "src" / "query_interface.py"
        fake_script.parent.mkdir(parents=True)
        fake_script.write_text("# placeholder\n")

        result = ensure_compatible_interpreter(
            version_info=(3, 9, 6),
            env={},
            script_path=str(fake_script),
        )
        assert result == "reexec"

    def test_old_version_without_venv_returns_incompatible(self, tmp_path):
        """版本过低且找不到 venv 时返回 incompatible。"""
        fake_script = tmp_path / "src" / "query_interface.py"
        fake_script.parent.mkdir(parents=True)
        fake_script.write_text("# placeholder\n")

        result = ensure_compatible_interpreter(
            version_info=(3, 9, 6),
            env={},
            script_path=str(fake_script),
        )
        assert result == "incompatible"

    def test_old_version_with_guard_set_returns_incompatible(self, tmp_path):
        """已设置重执行哨兵时返回 incompatible，避免无限循环。"""
        venv_bin = tmp_path / "venv" / "bin"
        venv_bin.mkdir(parents=True)
        py = venv_bin / "python"
        py.write_text("#!/bin/sh\n")
        os.chmod(py, 0o755)
        fake_script = tmp_path / "src" / "query_interface.py"
        fake_script.parent.mkdir(parents=True)
        fake_script.write_text("# placeholder\n")

        result = ensure_compatible_interpreter(
            version_info=(3, 9, 6),
            env={"QUERY_INTERFACE_REEXEC_GUARD": "1"},
            script_path=str(fake_script),
        )
        assert result == "incompatible"


class TestFindVenvPython:
    """find_venv_python 路径查找测试。"""

    def test_finds_venv_in_parent_directory(self, tmp_path):
        """能在脚本上层目录找到 venv/bin/python。"""
        venv_bin = tmp_path / "venv" / "bin"
        venv_bin.mkdir(parents=True)
        py = venv_bin / "python"
        py.write_text("#!/bin/sh\n")
        os.chmod(py, 0o755)
        script = tmp_path / "src" / "query_interface.py"
        script.parent.mkdir(parents=True)
        script.write_text("# placeholder\n")

        found = find_venv_python(str(script))
        assert found == str(py)

    def test_finds_dot_venv(self, tmp_path):
        """支持 .venv 目录。"""
        venv_bin = tmp_path / ".venv" / "bin"
        venv_bin.mkdir(parents=True)
        py = venv_bin / "python"
        py.write_text("#!/bin/sh\n")
        os.chmod(py, 0o755)
        script = tmp_path / "src" / "query_interface.py"
        script.parent.mkdir(parents=True)
        script.write_text("# placeholder\n")

        found = find_venv_python(str(script))
        assert found == str(py)

    def test_returns_none_when_no_venv(self, tmp_path):
        """找不到 venv 时返回 None。"""
        script = tmp_path / "src" / "query_interface.py"
        script.parent.mkdir(parents=True)
        script.write_text("# placeholder\n")

        assert find_venv_python(str(script)) is None

    def test_ignores_non_executable_python(self, tmp_path):
        """非可执行的 python 文件不应被当作有效解释器。"""
        venv_bin = tmp_path / "venv" / "bin"
        venv_bin.mkdir(parents=True)
        py = venv_bin / "python"
        py.write_text("not executable\n")
        os.chmod(py, 0o644)
        script = tmp_path / "src" / "query_interface.py"
        script.parent.mkdir(parents=True)
        script.write_text("# placeholder\n")

        assert find_venv_python(str(script)) is None


class TestRealProjectVenv:
    """针对真实项目结构的集成校验。"""

    def test_real_project_venv_discoverable(self):
        """真实仓库中应能从 query_interface.py 找到 venv 解释器。"""
        import query_interface

        real_script = os.path.abspath(query_interface.__file__)
        found = find_venv_python(real_script)
        # 仓库中存在 venv，应能找到；若 CI 环境无 venv 则跳过断言
        if found is not None:
            assert os.path.basename(found) == "python"
            assert os.access(found, os.X_OK)
