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
            "PaddleOCR"
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

    def test_system_prompt_version_update(self):
        """测试系统提示版本是否更新"""
        prompt_file = os.path.join(os.path.dirname(__file__), '..', '.devin', 'SYSTEM_PROMPT.md')
        with open(prompt_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 检查版本号
        assert "3.0" in content, "系统提示版本应该更新为3.0"
        assert "2026-06-15" in content, "系统提示应该包含更新日期"


class TestSystemPromptIntegration:
    """测试系统提示集成"""

    def test_react_engine_uses_custom_prompt(self):
        """测试ReActEngine是否使用自定义提示"""
        from react_engine import ReActEngine
        import tempfile
        import shutil
        
        # 创建临时历史文件
        with tempfile.TemporaryDirectory() as temp_dir:
            history_file = os.path.join(temp_dir, 'history.json')
            
            # 修改配置使用临时文件
            import config
            original_history = config.Config.HISTORY_FILE
            config.Config.HISTORY_FILE = history_file
            
            try:
                engine = ReActEngine()
                # 检查系统提示是否包含自定义内容
                messages = engine.history.get_messages()
                system_msg = [m for m in messages if m.get("role") == "system"]
                assert len(system_msg) > 0, "必须有系统消息"
                
                # 如果自定义提示文件存在，检查内容
                if os.path.exists(os.path.join(os.path.dirname(__file__), '..', '.devin', 'SYSTEM_PROMPT.md')):
                    assert "强制步骤" in system_msg[0]['content'] or "MUST READ" in system_msg[0]['content']
            finally:
                config.Config.HISTORY_FILE = original_history


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
