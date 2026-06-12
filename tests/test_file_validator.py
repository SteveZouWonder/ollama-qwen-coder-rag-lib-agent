#!/usr/bin/env python3
"""
file_validator.py 的单元测试
测试覆盖率目标: 95%以上
"""
import os
import sys
import tempfile
import shutil
import unittest
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))

from file_validator import FileValidator


class TestFileValidator(unittest.TestCase):
    """测试FileValidator"""

    def setUp(self):
        """设置测试环境"""
        self.temp_dir = tempfile.mkdtemp()
        self.validator = FileValidator(
            max_file_size=1024,  # 1KB
            max_total_size=5120,  # 5KB
            allowed_types=["txt", "md", "pdf"],
            blocked_patterns=["*.tmp"],
            enable_deduplication=True
        )

    def tearDown(self):
        """清理测试环境"""
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def test_validate_file_success(self):
        """测试文件验证成功"""
        test_file = os.path.join(self.temp_dir, "test.txt")
        with open(test_file, 'w') as f:
            f.write("test content")

        is_valid, message = self.validator.validate_file(Path(test_file))

        self.assertTrue(is_valid)
        self.assertIn("验证通过", message)

    def test_validate_file_too_large(self):
        """测试文件过大验证"""
        test_file = os.path.join(self.temp_dir, "large.txt")
        with open(test_file, 'w') as f:
            f.write("x" * 2048)  # 2KB > 1KB限制

        is_valid, message = self.validator.validate_file(Path(test_file))

        self.assertFalse(is_valid)
        self.assertIn("文件过大", message)

    def test_validate_file_empty(self):
        """测试空文件验证"""
        test_file = os.path.join(self.temp_dir, "empty.txt")
        with open(test_file, 'w') as f:
            f.write("")

        is_valid, message = self.validator.validate_file(Path(test_file))

        self.assertFalse(is_valid)
        self.assertIn("文件为空", message)

    def test_validate_file_not_exists(self):
        """测试文件不存在验证"""
        test_file = os.path.join(self.temp_dir, "nonexistent.txt")

        is_valid, message = self.validator.validate_file(Path(test_file))

        self.assertFalse(is_valid)
        self.assertIn("文件不存在", message)

    def test_validate_file_unsupported_type(self):
        """测试不支持的文件类型"""
        test_file = os.path.join(self.temp_dir, "test.exe")
        with open(test_file, 'w') as f:
            f.write("test content")

        is_valid, message = self.validator.validate_file(Path(test_file))

        self.assertFalse(is_valid)
        self.assertIn("不支持的文件类型", message)

    def test_validate_file_blocked_pattern(self):
        """测试阻塞模式验证"""
        # 创建一个.txt文件但匹配阻塞模式
        test_file = os.path.join(self.temp_dir, "test.txt")
        with open(test_file, 'w') as f:
            f.write("test content")

        # 添加一个匹配的阻塞模式
        self.validator.blocked_patterns = ["*.txt"]

        is_valid, message = self.validator.validate_file(Path(test_file))

        self.assertFalse(is_valid)
        self.assertIn("阻塞模式", message)

    def test_check_total_size_success(self):
        """测试总大小检查成功"""
        is_valid, message = self.validator.check_total_size(100)

        self.assertTrue(is_valid)
        self.assertIn("验证通过", message)

    def test_check_total_size_exceed(self):
        """测试总大小超限"""
        # 先注册一个文件，使当前总大小接近限制
        test_file = os.path.join(self.temp_dir, "test.txt")
        with open(test_file, 'w') as f:
            f.write("x" * 4000)  # 4KB

        self.validator.register_file(Path(test_file), 4000)

        is_valid, message = self.validator.check_total_size(2000)  # 再添加2KB会超过5KB限制

        self.assertFalse(is_valid)
        self.assertIn("总大小超限", message)

    def test_calculate_file_hash(self):
        """测试文件哈希计算"""
        test_file = os.path.join(self.temp_dir, "test.txt")
        with open(test_file, 'w') as f:
            f.write("test content")

        file_hash = self.validator.calculate_file_hash(Path(test_file))

        self.assertIsInstance(file_hash, str)
        self.assertEqual(len(file_hash), 32)  # MD5哈希长度

    def test_check_duplicate_not_duplicate(self):
        """测试文件不重复"""
        test_file = os.path.join(self.temp_dir, "test.txt")
        with open(test_file, 'w') as f:
            f.write("test content")

        is_duplicate, message = self.validator.check_duplicate(Path(test_file))

        self.assertFalse(is_duplicate)
        self.assertIn("文件不重复", message)

    def test_check_duplicate_duplicate(self):
        """测试文件重复"""
        test_file = os.path.join(self.temp_dir, "test.txt")
        with open(test_file, 'w') as f:
            f.write("test content")

        # 注册文件到已知集合
        self.validator.register_file(Path(test_file))

        is_duplicate, message = self.validator.check_duplicate(Path(test_file))

        self.assertTrue(is_duplicate)
        self.assertIn("文件重复", message)

    def test_register_file(self):
        """测试文件注册"""
        test_file = os.path.join(self.temp_dir, "test.txt")
        with open(test_file, 'w') as f:
            f.write("x" * 100)

        self.validator.register_file(Path(test_file), 100)

        stats = self.validator.get_stats()
        self.assertEqual(stats["current_total_size"], 100)

    def test_unregister_file(self):
        """测试文件取消注册"""
        test_file = os.path.join(self.temp_dir, "test.txt")
        with open(test_file, 'w') as f:
            f.write("x" * 100)

        self.validator.register_file(Path(test_file), 100)
        self.validator.unregister_file(Path(test_file), 100)

        stats = self.validator.get_stats()
        self.assertEqual(stats["current_total_size"], 0)

    def test_get_stats(self):
        """测试获取统计信息"""
        stats = self.validator.get_stats()

        self.assertIn("current_total_size", stats)
        self.assertIn("max_file_size", stats)
        self.assertIn("max_total_size", stats)
        self.assertIn("known_file_count", stats)
        self.assertIn("utilization_percent", stats)

    def test_reset(self):
        """测试重置验证器"""
        test_file = os.path.join(self.temp_dir, "test.txt")
        with open(test_file, 'w') as f:
            f.write("x" * 100)

        self.validator.register_file(Path(test_file), 100)
        self.validator.reset()

        stats = self.validator.get_stats()
        self.assertEqual(stats["current_total_size"], 0)
        self.assertEqual(stats["known_file_count"], 0)

    def test_format_size(self):
        """测试大小格式化"""
        self.assertEqual(FileValidator._format_size(500), "500.00 B")
        self.assertEqual(FileValidator._format_size(2048), "2.00 KB")
        self.assertEqual(FileValidator._format_size(1048576), "1.00 MB")

    def test_check_duplicate_disabled(self):
        """测试去重功能禁用时的行为"""
        validator = FileValidator(enable_deduplication=False)
        test_file = os.path.join(self.temp_dir, "test.txt")
        with open(test_file, 'w') as f:
            f.write("test content")

        is_duplicate, message = validator.check_duplicate(Path(test_file))

        self.assertFalse(is_duplicate)
        self.assertIn("去重功能未启用", message)

    def test_calculate_file_hash_error(self):
        """测试文件读取错误时的哈希计算"""
        # 创建一个不可读的文件
        test_file = os.path.join(self.temp_dir, "test.txt")
        with open(test_file, 'w') as f:
            f.write("test content")

        # 删除文件
        os.remove(test_file)

        file_hash = self.validator.calculate_file_hash(Path(test_file))

        self.assertEqual(file_hash, "")  # 读取失败时返回空字符串

    def test_register_file_with_auto_size(self):
        """测试自动计算文件大小的注册"""
        test_file = os.path.join(self.temp_dir, "test.txt")
        with open(test_file, 'w') as f:
            f.write("x" * 100)

        # 不传文件大小，自动计算
        self.validator.register_file(Path(test_file))

        stats = self.validator.get_stats()
        self.assertEqual(stats["current_total_size"], 100)

    def test_unregister_file_with_auto_size(self):
        """测试自动计算文件大小的取消注册"""
        test_file = os.path.join(self.temp_dir, "test.txt")
        with open(test_file, 'w') as f:
            f.write("x" * 100)

        self.validator.register_file(Path(test_file))
        # 不传文件大小，自动计算
        self.validator.unregister_file(Path(test_file))

        stats = self.validator.get_stats()
        self.assertEqual(stats["current_total_size"], 0)

    def test_validate_file_is_directory(self):
        """测试目录路径验证"""
        dir_path = os.path.join(self.temp_dir, "test_dir")
        os.makedirs(dir_path)

        is_valid, message = self.validator.validate_file(Path(dir_path))

        self.assertFalse(is_valid)
        self.assertIn("不是文件", message)

    def test_validator_with_custom_params(self):
        """测试自定义参数的验证器"""
        custom_validator = FileValidator(
            max_file_size=2048,
            max_total_size=10240,
            allowed_types=["txt"],
            blocked_patterns=[],
            enable_deduplication=False
        )

        self.assertEqual(custom_validator.max_file_size, 2048)
        self.assertEqual(custom_validator.max_total_size, 10240)
        self.assertEqual(custom_validator.allowed_types, ["txt"])
        self.assertEqual(custom_validator.enable_deduplication, False)

    def test_validate_file_unreadable(self):
        """测试文件不可读验证"""
        # 创建一个没有读取权限的文件
        test_file = os.path.join(self.temp_dir, "test.txt")
        with open(test_file, 'w') as f:
            f.write("test content")

        # 在Unix系统上移除读权限
        try:
            os.chmod(test_file, 0o000)
        except:
            # 如果无法修改权限，跳过这个测试
            self.skipTest("无法修改文件权限")

        is_valid, message = self.validator.validate_file(Path(test_file))

        self.assertFalse(is_valid)
        self.assertIn("文件不可读", message)

        # 恢复权限以便清理
        try:
            os.chmod(test_file, 0o644)
        except:
            pass

    def test_validate_file_with_mock_exception(self):
        """测试文件验证过程中的异常"""
        # 创建一个特殊的文件对象来模拟异常
        from unittest.mock import patch, MagicMock

        test_file = os.path.join(self.temp_dir, "test.txt")
        with open(test_file, 'w') as f:
            f.write("test content")

        # 模拟Path.stat()抛出异常
        with patch.object(Path, 'stat', side_effect=PermissionError("Mock error")):
            is_valid, message = self.validator.validate_file(Path(test_file))
            self.assertFalse(is_valid)
            self.assertIn("验证过程出错", message)

    def test_check_duplicate_with_hash_calculation_error(self):
        """测试哈希计算失败时的去重检查"""
        test_file = os.path.join(self.temp_dir, "test.txt")
        with open(test_file, 'w') as f:
            f.write("test content")

        # 删除文件以使哈希计算失败
        os.remove(test_file)

        is_duplicate, message = self.validator.check_duplicate(Path(test_file))

        self.assertFalse(is_duplicate)
        self.assertIn("无法计算文件哈希", message)

    def test_format_size_terabytes(self):
        """测试TB大小的格式化"""
        result = FileValidator._format_size(1024 * 1024 * 1024 * 1024)  # 1TB
        self.assertIn("TB", result)

    def test_get_global_validator(self):
        """测试获取全局验证器"""
        from file_validator import get_global_validator

        # 第一次调用应该创建新实例
        validator1 = get_global_validator()
        self.assertIsNotNone(validator1)

        # 第二次调用应该返回同一个实例
        validator2 = get_global_validator()
        self.assertIs(validator1, validator2)


if __name__ == '__main__':
    unittest.main(verbosity=2)
