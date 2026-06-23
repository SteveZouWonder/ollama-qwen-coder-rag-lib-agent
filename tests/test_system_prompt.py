#!/usr/bin/env python3
"""
test_system_prompt.py — 系统提示文件功能单元测试
"""
import pytest
import os
import sys

# 添加src目录到Python路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from react_engine import read_system_prompt_from_file
from agent_tools import read_system_prompt


class TestReadSystemPromptFromFile:
    """测试从文件读取系统提示"""

    def test_read_existing_prompt_file(self):
        """测试读取存在的系统提示文件"""
        result = read_system_prompt_from_file()
        # 如果文件存在，应该返回内容
        if os.path.exists(os.path.join(os.path.dirname(__file__), '..', '.devin', 'SYSTEM_PROMPT.md')):
            assert result is not None
            assert isinstance(result, str)
            assert len(result) > 0
        else:
            assert result is None

    def test_read_system_prompt_tool(self):
        """测试read_system_prompt工具"""
        result = read_system_prompt()
        assert result is not None
        assert isinstance(result, str)
        assert len(result) > 0


class TestSystemPromptContent:
    """测试系统提示文件内容"""

    def test_system_prompt_file_exists(self):
        """测试系统提示文件是否存在"""
        prompt_file = os.path.join(os.path.dirname(__file__), '..', '.devin', 'SYSTEM_PROMPT.md')
        assert os.path.exists(prompt_file), "系统提示文件必须存在"

    def test_system_prompt_mandatory_sections(self):
        """测试系统提示包含必需的章节"""
        prompt_file = os.path.join(os.path.dirname(__file__), '..', '.devin', 'SYSTEM_PROMPT.md')
        with open(prompt_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 检查必需的关键词
        required_keywords = [
            "强制步骤",
            "MUST READ",
            "read_system_prompt",
            "工作流程",
            "质量标准",
            "禁止"
        ]
        
        for keyword in required_keywords:
            assert keyword in content, f"系统提示必须包含关键词: {keyword}"

    def test_system_prompt_priority(self):
        """测试系统提示强调优先级"""
        prompt_file = os.path.join(os.path.dirname(__file__), '..', '.devin', 'SYSTEM_PROMPT.md')
        with open(prompt_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 检查优先级相关的关键词
        priority_keywords = [
            "最高优先级",
            "强制",
            "必须",
            "首先"
        ]
        
        for keyword in priority_keywords:
            assert keyword in content, f"系统提示必须强调优先级: {keyword}"

    def test_system_prompt_workflow_steps(self):
        """测试系统提示包含工作流程步骤"""
        prompt_file = os.path.join(os.path.dirname(__file__), '..', '.devin', 'SYSTEM_PROMPT.md')
        with open(prompt_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 检查工作流程步骤
        workflow_keywords = [
            "读取配置文件",
            "任务追踪",
            "质量标准"
        ]
        
        for keyword in workflow_keywords:
            assert keyword in content, f"系统提示必须包含工作流程: {keyword}"

    def test_system_prompt_multi_agent_section(self):
        """测试系统提示包含多Agent协作系统说明"""
        prompt_file = os.path.join(os.path.dirname(__file__), '..', '.devin', 'SYSTEM_PROMPT.md')
        with open(prompt_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 检查多Agent相关内容
        multi_agent_keywords = [
            "多 Agent 协作",
            "MasterAgent",
            "CodeAgent",
            "RAGAgent",
            "TestAgent",
            "DocAgent",
            "AuditAgent",
            "协作模式"
        ]
        
        for keyword in multi_agent_keywords:
            assert keyword in content, f"系统提示必须包含多Agent协作内容: {keyword}"

    def test_system_prompt_new_tools_description(self):
        """测试系统提示包含新工具描述"""
        prompt_file = os.path.join(os.path.dirname(__file__), '..', '.devin', 'SYSTEM_PROMPT.md')
        with open(prompt_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 检查新工具描述
        new_tool_keywords = [
            "get_current_dir",
            "check_knowledge_status",
            "search_files"
        ]
        
        for keyword in new_tool_keywords:
            assert keyword in content, f"系统提示必须包含工具描述: {keyword}"

    def test_system_prompt_ocr_format_update(self):
        """测试OCR格式描述是否更新"""
        prompt_file = os.path.join(os.path.dirname(__file__), '..', '.devin', 'SYSTEM_PROMPT.md')
        with open(prompt_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 检查OCR格式支持
        ocr_format_keywords = [
            "GIF",
            "BMP",
            "TIFF",
            # 默认后端应为 Tesseract（兼容 Python 3.13）；PaddleOCR 为可选后端
            "Tesseract"
        ]
        
        for keyword in ocr_format_keywords:
            assert keyword in content, f"系统提示必须包含OCR格式: {keyword}"

    def test_system_prompt_tool_examples(self):
        """测试系统提示包含工具使用示例"""
        prompt_file = os.path.join(os.path.dirname(__file__), '..', '.devin', 'SYSTEM_PROMPT.md')
        with open(prompt_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 检查工具使用示例
        example_keywords = [
            "工具使用示例",
            "示例1",
            "示例2",
            "Thought",
            "Action",
            "Final Answer"
        ]
        
        for keyword in example_keywords:
            assert keyword in content, f"系统提示必须包含工具使用示例: {keyword}"

    def test_system_prompt_snapshot_session_management(self):
        """测试快照和会话管理说明"""
        prompt_file = os.path.join(os.path.dirname(__file__), '..', '.devin', 'SYSTEM_PROMPT.md')
        with open(prompt_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 检查快照和会话管理
        snapshot_keywords = [
            "快照",
            "会话管理",
            "版本管理",
            "会话恢复"
        ]
        
        for keyword in snapshot_keywords:
            assert keyword in content, f"系统提示必须包含快照和会话管理: {keyword}"

    def test_system_prompt_has_tool_descriptions_placeholder(self):
        """测试系统提示包含工具描述占位符（防止工具清单丢失回归）"""
        prompt_file = os.path.join(os.path.dirname(__file__), '..', '.devin', 'SYSTEM_PROMPT.md')
        with open(prompt_file, 'r', encoding='utf-8') as f:
            content = f.read()

        # react_engine 会用 registry 工具描述替换该占位符
        # 缺少占位符会导致工具清单无法注入系统提示
        assert "{tool_descriptions}" in content, \
            "系统提示必须包含 {tool_descriptions} 占位符以注入工具清单"

    def test_system_prompt_injects_tool_descriptions(self):
        """测试占位符在注入后被实际工具描述替换"""
        from agent_tools import registry
        content = read_system_prompt_from_file()
        assert content is not None
        injected = content.replace("{tool_descriptions}", registry.get_descriptions())
        # 替换后不应再残留占位符
        assert "{tool_descriptions}" not in injected
        # 注入后应包含核心工具名
        assert "read_system_prompt" in injected

    def test_system_prompt_version_update(self):
        """测试系统提示版本是否更新"""
        prompt_file = os.path.join(os.path.dirname(__file__), '..', '.devin', 'SYSTEM_PROMPT.md')
        with open(prompt_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 检查版本号（应与项目 CHANGELOG 当前版本保持同步）
        assert "4.2.1" in content, "系统提示版本应该更新为4.2.1"
        assert "2026-06-23" in content, "系统提示应该包含更新日期"


class TestSystemPromptIntegration:
    """测试系统提示集成"""

    def test_react_engine_uses_custom_prompt(self):
        """测试ReActEngine是否使用自定义提示"""
        # 检查自定义提示文件是否存在
        system_prompt_path = os.path.join(os.path.dirname(__file__), '..', '.devin', 'SYSTEM_PROMPT.md')
        
        if not os.path.exists(system_prompt_path):
            pytest.skip("自定义提示文件不存在，跳过此测试")
        
        # 读取自定义提示文件内容
        with open(system_prompt_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 验证自定义提示包含必要的关键词
        assert "MUST READ" in content or "强制步骤" in content, "自定义提示必须包含强制步骤说明"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
