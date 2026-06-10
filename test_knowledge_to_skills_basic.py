#!/usr/bin/env python3
"""
test_knowledge_to_skills.py 的简化版本
只测试基本功能，避免安全扫描器的依赖
"""
import os
import sys
import tempfile
import shutil
import unittest
from pathlib import Path
import warnings

# 禁用警告
warnings.filterwarnings("ignore")
os.environ['ANONYMIZED_TELEMETRY'] = 'False'
os.environ['CHROMA_TELEMETRY'] = 'False'

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))

from knowledge_to_skills import (
    DocumentInfo,
    TopicGroup,
    SkillConfig,
)


class TestDocumentInfo(unittest.TestCase):
    """测试DocumentInfo数据类"""
    
    def test_document_info_creation(self):
        """测试DocumentInfo创建"""
        doc_info = DocumentInfo(
            file_path="/test/path.md",
            file_name="test.md",
            file_type=".md",
            chunk_count=10,
            content_preview="Test content",
            topics=["cloudflare", "networking"],
            is_generic=True,
            confidence=0.85
        )
        
        self.assertEqual(doc_info.file_path, "/test/path.md")
        self.assertEqual(doc_info.file_name, "test.md")
        self.assertEqual(doc_info.topics, ["cloudflare", "networking"])
        self.assertTrue(doc_info.is_generic)
        self.assertEqual(doc_info.confidence, 0.85)


class TestSkillConfig(unittest.TestCase):
    """测试SkillConfig数据类"""
    
    def test_skill_config_defaults(self):
        """测试SkillConfig默认值"""
        config = SkillConfig(
            name="test-skill",
            description="Test skill description"
        )
        
        self.assertEqual(config.name, "test-skill")
        self.assertEqual(config.description, "Test skill description")
        self.assertEqual(config.argument_hint, "")
        self.assertEqual(config.allowed_tools, ["read", "grep", "glob", "exec"])
        self.assertEqual(config.triggers, ["user", "model"])
    
    def test_skill_config_custom(self):
        """测试SkillConfig自定义值"""
        config = SkillConfig(
            name="custom-skill",
            description="Custom description",
            argument_hint="[file]",
            allowed_tools=["read"],
            triggers=["user"],
            subagent=True,
            model="sonnet"
        )
        
        self.assertEqual(config.argument_hint, "[file]")
        self.assertEqual(config.allowed_tools, ["read"])
        self.assertEqual(config.triggers, ["user"])
        self.assertTrue(config.subagent)
        self.assertEqual(config.model, "sonnet")


class TestTopicGroup(unittest.TestCase):
    """测试TopicGroup数据类"""
    
    def test_topic_group_creation(self):
        """测试TopicGroup创建"""
        doc_info = DocumentInfo(
            file_path="/test/path.md",
            file_name="test.md",
            file_type=".md",
            chunk_count=10,
            content_preview="Test content",
            topics=["cloudflare"],
            is_generic=True,
            confidence=0.8
        )
        
        group = TopicGroup(
            topic_name="test",
            documents=[doc_info],
            skill_name="test-skill",
            description="Test description",
            platforms=["devin"]
        )
        
        self.assertEqual(group.topic_name, "test")
        self.assertEqual(len(group.documents), 1)
        self.assertEqual(group.skill_name, "test-skill")


if __name__ == '__main__':
    # 运行测试
    unittest.main(verbosity=2)
