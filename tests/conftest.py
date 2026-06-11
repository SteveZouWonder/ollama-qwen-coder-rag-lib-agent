"""
pytest配置文件 - 全局测试设置
防止测试中触发实际的弹窗和系统调用
"""
import subprocess
from unittest.mock import Mock, patch
import pytest


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
            mock_run.return_value = Mock(returncode=0)
            mock_popen.return_value = Mock()
            
            yield
            
            # 测试结束后自动清理（with语句自动处理）