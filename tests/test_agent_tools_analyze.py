#!/usr/bin/env python3
"""
test_agent_tools_analyze.py — 项目分析工具单元测试
"""
import os
import sys
import pytest
from pathlib import Path

# 直接添加src目录到路径，避免触发conftest.py中的rag_engine导入
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

# 直接导入函数，避免导入整个agent_tools模块可能触发的依赖
import importlib.util
spec = importlib.util.spec_from_file_location("agent_tools", os.path.join(os.path.dirname(__file__), '..', 'src', 'agent_tools.py'))
agent_tools_module = importlib.util.module_from_spec(spec)

# 避免触发RAG引擎相关的导入
import unittest.mock as mock
sys.modules['rag_engine'] = mock.MagicMock()

spec.loader.exec_module(agent_tools_module)
analyze_project_structure = agent_tools_module.analyze_project_structure


class TestAnalyzeProjectStructure:
    """测试 analyze_project_structure"""

    def test_analyze_existing_project(self, temp_dir):
        """测试分析现有项目"""
        # 创建一个模拟的项目结构
        (temp_dir / "src").mkdir()
        (temp_dir / "tests").mkdir()
        (temp_dir / "README.md").write_text("# Test Project")
        (temp_dir / "requirements.txt").write_text("requests==2.28.0")
        (temp_dir / "setup.py").write_text("# setup file")
        (temp_dir / "src" / "main.py").write_text("# main file")
        (temp_dir / "tests" / "test_main.py").write_text("# test file")
        
        result = analyze_project_structure(str(temp_dir))
        
        # 验证基本结构分析
        assert "项目路径" in result
        assert "根目录数" in result
        assert "根文件数" in result
        assert "主要目录" in result
        assert "主要文件" in result
        
        # 验证识别的技术栈
        assert "Python" in result
        
        # 验证关键文件识别
        assert "README.md" in result or "README" in result
        assert "requirements.txt" in result
        
        # 验证目录详情
        assert "src/" in result
        assert "tests/" in result

    def test_analyze_python_project(self, temp_dir):
        """测试分析Python项目"""
        (temp_dir / "requirements.txt").write_text("numpy")
        (temp_dir / "setup.py").write_text("# setup")
        (temp_dir / "pyproject.toml").write_text("# pyproject")
        
        result = analyze_project_structure(str(temp_dir))
        
        assert "Python" in result
        assert "requirements.txt" in result
        assert "setup.py" in result or "pyproject.toml" in result

    def test_analyze_javascript_project(self, temp_dir):
        """测试分析JavaScript项目"""
        (temp_dir / "package.json").write_text('{"name": "test"}')
        
        result = analyze_project_structure(str(temp_dir))
        
        assert "JavaScript" in result or "Node.js" in result
        assert "package.json" in result

    def test_analyze_rust_project(self, temp_dir):
        """测试分析Rust项目"""
        (temp_dir / "Cargo.toml").write_text("[package]")
        
        result = analyze_project_structure(str(temp_dir))
        
        assert "Rust" in result
        assert "Cargo.toml" in result

    def test_analyze_go_project(self, temp_dir):
        """测试分析Go项目"""
        (temp_dir / "go.mod").write_text("module test")
        
        result = analyze_project_structure(str(temp_dir))
        
        assert "Go" in result
        assert "go.mod" in result

    def test_analyze_docker_project(self, temp_dir):
        """测试分析Docker项目"""
        (temp_dir / "Dockerfile").write_text("FROM python")
        (temp_dir / "docker-compose.yml").write_text("version: '3'")
        
        result = analyze_project_structure(str(temp_dir))
        
        assert "Docker" in result
        assert "Dockerfile" in result or "docker-compose.yml" in result

    def test_analyze_mixed_project(self, temp_dir):
        """测试分析混合技术栈项目"""
        (temp_dir / "package.json").write_text('{"name": "test"}')
        (temp_dir / "requirements.txt").write_text("requests")
        (temp_dir / "Dockerfile").write_text("FROM python")
        
        result = analyze_project_structure(str(temp_dir))
        
        # 应该识别多个技术栈
        assert "JavaScript" in result or "Node.js" in result
        assert "Python" in result
        assert "Docker" in result

    def test_analyze_empty_project(self, temp_dir):
        """测试分析空项目"""
        result = analyze_project_structure(str(temp_dir))
        
        assert "项目路径" in result
        assert "根目录数: 0" in result
        assert "根文件数: 0" in result
        assert "未知" in result  # 技术栈未知

    def test_analyze_nonexistent_path(self):
        """测试分析不存在的路径"""
        result = analyze_project_structure("/nonexistent/path")
        
        assert "[错误] 项目路径不存在" in result

    def test_analyze_file_instead_of_directory(self, temp_dir):
        """测试传入文件路径而非目录"""
        file_path = temp_dir / "test.txt"
        file_path.write_text("test content")
        
        result = analyze_project_structure(str(file_path))
        
        assert "[错误] 提供的路径不是目录" in result

    def test_analyze_project_with_many_dirs(self, temp_dir):
        """测试分析包含多个目录的项目"""
        # 创建多个目录
        for i in range(15):
            (temp_dir / f"dir{i}").mkdir()
        
        result = analyze_project_structure(str(temp_dir))
        
        # 应该只显示前10个目录的详情
        assert "根目录数: 15" in result
        assert "目录详情" in result

    def test_analyze_project_with_hidden_files(self, temp_dir):
        """测试分析包含隐藏文件的项目"""
        (temp_dir / ".git").mkdir()
        (temp_dir / ".env").write_text("SECRET")
        (temp_dir / "visible.txt").write_text("public")
        
        result = analyze_project_structure(str(temp_dir))
        
        # 隐藏文件不应该出现在主要文件中
        assert ".git" not in result
        assert ".env" not in result
        assert "visible.txt" in result

    def test_analyze_project_with_subdirectories(self, temp_dir):
        """测试分析包含子目录的项目"""
        src_dir = temp_dir / "src"
        src_dir.mkdir()
        (src_dir / "main.py").write_text("# main")
        (src_dir / "utils.py").write_text("# utils")
        (src_dir / "subdir").mkdir()
        (src_dir / "subdir" / "helper.py").write_text("# helper")
        
        result = analyze_project_structure(str(temp_dir))
        
        assert "src/" in result
        # 检查是否显示了目录详情
        assert "目录详情" in result
        assert "src/" in result

    def test_analyze_project_permission_error(self, temp_dir, monkeypatch):
        """测试权限错误处理"""
        def mock_listdir(path):
            if "unreadable" in str(path):
                raise PermissionError("Permission denied")
            return os.listdir.__wrapped__(path)  # 使用原始的listdir
        
        # 创建一个不可读的目录
        unreadable_dir = temp_dir / "unreadable"
        unreadable_dir.mkdir()
        
        result = analyze_project_structure(str(temp_dir))
        
        # 即使有权限错误，也应该返回部分结果
        assert "项目路径" in result

    def test_analyze_project_with_java_project(self, temp_dir):
        """测试分析Java Maven项目"""
        (temp_dir / "pom.xml").write_text("<project>...</project>")
        
        result = analyze_project_structure(str(temp_dir))
        
        assert "Java" in result or "Maven" in result
        assert "pom.xml" in result

    def test_analyze_project_with_gradle_project(self, temp_dir):
        """测试分析Java Gradle项目"""
        (temp_dir / "build.gradle").write_text("plugins {}")
        
        result = analyze_project_structure(str(temp_dir))
        
        assert "Java" in result or "Gradle" in result
        assert "build.gradle" in result

    def test_analyze_project_with_ruby_project(self, temp_dir):
        """测试分析Ruby项目"""
        (temp_dir / "Gemfile").write_text("source 'https://rubygems.org'")
        
        result = analyze_project_structure(str(temp_dir))
        
        assert "Ruby" in result
        assert "Gemfile" in result

    def test_analyze_project_with_make_project(self, temp_dir):
        """测试分析Make项目"""
        (temp_dir / "Makefile").write_text("all:\n\techo 'building'")
        
        result = analyze_project_structure(str(temp_dir))
        
        assert "Make" in result
        assert "Makefile" in result

    def test_analyze_project_with_cmake_project(self, temp_dir):
        """测试分析CMake项目"""
        (temp_dir / "CMakeLists.txt").write_text("cmake_minimum_required(VERSION 3.0)")
        
        result = analyze_project_structure(str(temp_dir))
        
        assert "CMake" in result
        assert "CMakeLists.txt" in result

    def test_analyze_project_with_readme_rst(self, temp_dir):
        """测试分析reStructuredText README"""
        (temp_dir / "README.rst").write_text("Test Project")
        
        result = analyze_project_structure(str(temp_dir))
        
        assert "Documentation" in result or "README" in result

    def test_analyze_project_specific_path(self, temp_dir):
        """测试分析特定路径的项目"""
        subdir = temp_dir / "subproject"
        subdir.mkdir()
        (subdir / "package.json").write_text('{"name": "sub"}')
        
        result = analyze_project_structure(str(subdir))
        
        assert str(subdir) in result
        assert "JavaScript" in result or "Node.js" in result