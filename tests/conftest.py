"""
pytest配置文件 - 全局测试设置
防止测试中触发实际的弹窗和系统调用
"""
import subprocess
import os
import tempfile
import shutil
import sys
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import pytest
import warnings

# 忽略 pymupdf 的 Swig 类型警告（库的问题）
warnings.filterwarnings("ignore", category=DeprecationWarning, message="builtin type.*Swig.*")

# 添加src目录到Python路径，支持模块导入
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))


@pytest.fixture(autouse=True)
def prevent_popups():
    """
    全局fixture：防止所有测试中触发实际弹窗
    
    这个fixture会自动应用到所有测试，mock掉subprocess.run和subprocess.Popen调用，
    防止在测试过程中触发实际的系统弹窗、通知或其他GUI操作。
    
    这样可以确保：
    1. 测试运行时不会弹出实际的对话框或通知
    2. 测试环境保持干净，不干扰用户
    3. 测试速度更快，不需要等待系统响应
    4. 测试更加稳定和可重复
    """
    with patch('subprocess.run') as mock_run:
        with patch('subprocess.Popen') as mock_popen:
            # 设置默认返回值，模拟成功的系统调用
            mock_result = Mock()
            mock_result.returncode = 0
            mock_result.stdout = ""
            mock_result.stderr = ""
            mock_run.return_value = mock_result
            mock_popen.return_value = Mock()
            
            yield
            
            # 测试结束后自动清理（with语句自动处理）


@pytest.fixture(autouse=True)
def setup_settings_mock():
    """
    全局fixture：自动 mock Settings 以避免 LlamaIndex 类型检查问题
    """
    with patch('rag_engine.Settings') as mock_settings_class:
        mock_settings = MagicMock()
        mock_settings.llm = MagicMock()
        mock_settings.embed_model = MagicMock()
        mock_settings_class.return_value = mock_settings
        
        yield


@pytest.fixture
def clean_env():
    """
    清理测试环境的fixture
    
    为每个测试提供一个干净的环境：
    1. 临时环境变量清理
    2. 临时目录创建和清理
    3. 确保测试之间不相互影响
    """
    # 保存当前环境变量
    original_env = os.environ.copy()
    
    # 创建临时目录
    temp_dir = tempfile.mkdtemp()
    
    yield {
        'temp_dir': temp_dir,
        'original_env': original_env
    }
    
    # 清理：恢复环境变量
    os.environ.clear()
    os.environ.update(original_env)
    
    # 清理临时目录
    if os.path.exists(temp_dir):
        shutil.rmtree(temp_dir)


@pytest.fixture
def temp_dir():
    """
    创建临时目录的fixture（返回 Path 对象）
    """
    temp_dir = Path(tempfile.mkdtemp())
    yield temp_dir
    # 清理临时目录
    if temp_dir.exists():
        shutil.rmtree(temp_dir)


@pytest.fixture
def mock_rag_engine():
    """
    Mock RAG engine fixture for agent tools tests
    """
    engine = MagicMock()
    engine.query_tool.return_value = "[Mock] 知识库查询结果"
    engine.add_document_tool.return_value = "[Mock] 文档已添加"
    engine.get_stats_tool.return_value = "[Mock] 统计信息"
    return engine