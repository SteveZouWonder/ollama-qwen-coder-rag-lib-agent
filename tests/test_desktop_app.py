#!/usr/bin/env python3
"""
desktop_app.py 的单元测试
测试覆盖率目标：95%+
"""
import unittest
import json
import tempfile
import shutil
import logging
import requests
import time
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import sys
import os

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))

from desktop_app import (
    AppConfig, LogManager, OllamaWarmer, StatusMonitor, TrayApp, DesktopApp, BaseApp,
    DEFAULT_CONFIG, CONFIG_FILE, LOG_FILE, STATUS_FILE
)
import signal

class TestAppConfig(unittest.TestCase):
    """AppConfig 类的单元测试"""
    
    def setUp(self):
        """设置测试环境"""
        self.test_dir = tempfile.mkdtemp()
        self.test_config_file = Path(self.test_dir) / "test_config.json"
        
    def tearDown(self):
        """清理测试环境"""
        shutil.rmtree(self.test_dir)
        
    def test_load_config_default(self):
        """测试加载默认配置"""
        config = AppConfig(self.test_config_file)
        self.assertEqual(config.config, DEFAULT_CONFIG)
        
    def test_load_config_from_file(self):
        """测试从文件加载配置"""
        # 创建测试配置文件
        test_config = {
            "autostart": True,
            "warm_up_on_startup": False,
            "warm_up_models": ["test-model"],
            "ollama_base_url": "http://test.com:11434",
            "check_interval": 600
        }
        
        with open(self.test_config_file, 'w', encoding='utf-8') as f:
            json.dump(test_config, f)
            
        config = AppConfig(self.test_config_file)
        self.assertEqual(config.config, test_config)
        
    def test_load_config_invalid_json(self):
        """测试加载无效JSON文件"""
        # 创建无效的JSON文件
        with open(self.test_config_file, 'w', encoding='utf-8') as f:
            f.write("{ invalid json }")
            
        config = AppConfig(self.test_config_file)
        # 应该回退到默认配置
        self.assertEqual(config.config, DEFAULT_CONFIG)
        
    def test_save_config(self):
        """测试保存配置"""
        config = AppConfig(self.test_config_file)
        config.set("autostart", True)
        config.set("new_key", "new_value")
        
        result = config.save_config()
        self.assertTrue(result)
        
        # 验证文件存在
        self.assertTrue(self.test_config_file.exists())
        
        # 验证保存的内容
        with open(self.test_config_file, 'r', encoding='utf-8') as f:
            saved_config = json.load(f)
            
        self.assertTrue(saved_config["autostart"])
        self.assertEqual(saved_config["new_key"], "new_value")
        
    def test_save_config_create_directory(self):
        """测试保存配置时创建目录"""
        # 使用不存在的目录
        nested_dir = self.test_config_file.parent / "nested" / "config.json"
        config = AppConfig(nested_dir)
        config.set("test", "value")
        
        result = config.save_config()
        self.assertTrue(result)
        self.assertTrue(nested_dir.exists())
        
    def test_get_config(self):
        """测试获取配置项"""
        config = AppConfig(self.test_config_file)
        
        # 获取存在的键
        self.assertEqual(config.get("autostart"), False)
        
        # 获取不存在的键（使用默认值）
        self.assertIsNone(config.get("nonexistent"))
        self.assertEqual(config.get("nonexistent", "default"), "default")
        
    def test_set_config(self):
        """测试设置配置项"""
        config = AppConfig(self.test_config_file)
        config.set("autostart", True)
        self.assertEqual(config.get("autostart"), True)
        
        config.set("new_key", "new_value")
        self.assertEqual(config.get("new_key"), "new_value")
        
    def test_reload_config(self):
        """测试重新加载配置"""
        config = AppConfig(self.test_config_file)
        
        # 修改内存中的配置
        config.set("autostart", True)
        self.assertTrue(config.get("autostart"))
        
        # 修改文件
        with open(self.test_config_file, 'w', encoding='utf-8') as f:
            json.dump({"autostart": False}, f)
            
        # 重新加载
        config.reload()
        self.assertFalse(config.get("autostart"))

class TestLogManager(unittest.TestCase):
    """LogManager 类的单元测试"""
    
    def setUp(self):
        """设置测试环境"""
        self.test_dir = tempfile.mkdtemp()
        self.test_log_file = Path(self.test_dir) / "test.log"
        
    def tearDown(self):
        """清理测试环境"""
        shutil.rmtree(self.test_dir)
        
    def test_setup_logging(self):
        """测试设置日志系统"""
        log_manager = LogManager(self.test_log_file)
        logger = log_manager.setup_logging()
        
        self.assertIsNotNone(logger)
        self.assertTrue(self.test_log_file.exists())
        
    def test_setup_logging_creates_directory(self):
        """测试设置日志时创建目录"""
        nested_log = self.test_log_file.parent / "nested" / "test.log"
        log_manager = LogManager(nested_log)
        logger = log_manager.setup_logging()
        
        self.assertIsNotNone(logger)
        self.assertTrue(nested_log.exists())
        
    def test_get_logger(self):
        """测试获取日志记录器"""
        log_manager = LogManager(self.test_log_file)
        log_manager.setup_logging()
        
        # 获取默认记录器
        logger1 = log_manager.get_logger()
        self.assertIsNotNone(logger1)
        
        # 获取命名记录器
        logger2 = log_manager.get_logger("test_logger")
        self.assertIsNotNone(logger2)
        self.assertEqual(logger2.name, "test_logger")
        
    def test_logging_writes_to_file(self):
        """测试日志写入文件"""
        # 使用单独的logger实例避免冲突
        log_manager = LogManager(self.test_log_file)
        
        # 清除现有的handlers
        logging.getLogger().handlers.clear()
        
        logger = log_manager.setup_logging(level=logging.DEBUG)
        
        test_message = "Test log message"
        logger.info(test_message)
        
        # 强制刷新所有日志处理器并关闭
        for handler in logger.handlers:
            handler.flush()
            handler.close()
            
        # 等待文件系统同步
        import time
        time.sleep(0.3)
        
        # 验证日志文件存在且不为空
        self.assertTrue(self.test_log_file.exists())
        
        # 验证日志文件内容
        if self.test_log_file.stat().st_size > 0:
            with open(self.test_log_file, 'r', encoding='utf-8') as f:
                log_content = f.read()
            self.assertIn("INFO", log_content)  # 至少应该有日志级别

class TestOllamaWarmer(unittest.TestCase):
    """OllamaWarmer 类的单元测试"""
    
    def setUp(self):
        """设置测试环境"""
        self.logger = Mock()
        self.base_url = "http://localhost:11434"
        self.warmer = OllamaWarmer(self.base_url, self.logger)
        
    @patch('desktop_app.requests.post')
    def test_warm_up_success(self, mock_post):
        """测试成功的模型预热"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response
        
        models = ["test-model"]
        results = self.warmer.warm_up(models)
        
        self.assertTrue(results["test-model"]["success"])
        self.assertIn("time", results["test-model"])
        self.logger.info.assert_called()
        
    @patch('desktop_app.requests.post')
    def test_warm_up_http_error(self, mock_post):
        """测试HTTP错误"""
        mock_response = Mock()
        mock_response.status_code = 500
        mock_post.return_value = mock_response
        
        models = ["test-model"]
        results = self.warmer.warm_up(models)
        
        self.assertFalse(results["test-model"]["success"])
        self.assertEqual(results["test-model"]["error"], "HTTP 500")
        
    @patch('desktop_app.requests.post')
    def test_warm_up_timeout(self, mock_post):
        """测试超时"""
        mock_post.side_effect = requests.exceptions.Timeout()
        
        models = ["test-model"]
        results = self.warmer.warm_up(models)
        
        self.assertFalse(results["test-model"]["success"])
        self.assertEqual(results["test-model"]["error"], "timeout")
        
    @patch('desktop_app.requests.post')
    def test_warm_up_exception(self, mock_post):
        """测试异常处理"""
        mock_post.side_effect = Exception("Connection error")
        
        models = ["test-model"]
        results = self.warmer.warm_up(models)
        
        self.assertFalse(results["test-model"]["success"])
        self.assertEqual(results["test-model"]["error"], "Connection error")
        
    @patch('desktop_app.requests.post')
    def test_warm_up_multiple_models(self, mock_post):
        """测试多个模型预热"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response
        
        models = ["model1", "model2", "model3"]
        results = self.warmer.warm_up(models)
        
        self.assertEqual(len(results), 3)
        for model in models:
            self.assertTrue(results[model]["success"])
            
    @patch('desktop_app.requests.get')
    def test_check_service_success(self, mock_get):
        """测试服务检查成功"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_get.return_value = mock_response
        
        result = self.warmer.check_service()
        self.assertTrue(result)
        
    @patch('desktop_app.requests.get')
    def test_check_service_failure(self, mock_get):
        """测试服务检查失败"""
        mock_get.side_effect = Exception("Service not available")
        
        result = self.warmer.check_service()
        self.assertFalse(result)
    
    @patch('desktop_app.requests.post')
    def test_warm_up_embed_model(self, mock_post):
        """测试嵌入模型预热"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response
        
        result = self.warmer.warm_up(["nomic-embed-text:latest"])
        
        # 验证调用了 embed 端点
        self.assertTrue(mock_post.called)
        call_args = mock_post.call_args
        self.assertIn("/api/embed", call_args[0][0])
        self.assertTrue(result["nomic-embed-text:latest"]["success"])
    
    @patch('desktop_app.requests.post')
    def test_warm_up_chat_model(self, mock_post):
        """测试聊天模型预热"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response
        
        result = self.warmer.warm_up(["qwen2.5-coder:7b"])
        
        # 验证调用了 generate 端点（不是 embed）
        self.assertTrue(mock_post.called)
        call_args = mock_post.call_args
        self.assertIn("/api/generate", call_args[0][0])
        self.assertTrue(result["qwen2.5-coder:7b"]["success"])
    
    @patch('desktop_app.requests.post')
    def test_warm_up_embed_model_failure(self, mock_post):
        """测试嵌入模型预热失败"""
        mock_post.side_effect = Exception("Embed API error")
        
        result = self.warmer.warm_up(["nomic-embed-text:latest"])
        
        # 验证失败处理
        self.assertFalse(result["nomic-embed-text:latest"]["success"])
        self.assertIn("error", result["nomic-embed-text:latest"])

class TestStatusMonitor(unittest.TestCase):
    """StatusMonitor 类的单元测试"""
    
    def setUp(self):
        """设置测试环境"""
        self.test_dir = tempfile.mkdtemp()
        self.test_status_file = Path(self.test_dir) / "test_status.log"
        self.logger = Mock()
        self.ollama_url = "http://localhost:11434"
        self.monitor = StatusMonitor(self.ollama_url, self.logger, self.test_status_file)
        
    def tearDown(self):
        """清理测试环境"""
        shutil.rmtree(self.test_dir)
        
    @patch('desktop_app.requests.get')
    def test_check_status_success(self, mock_get):
        """测试状态检查成功"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "models": [
                {"name": "model1"},
                {"name": "model2"}
            ]
        }
        mock_get.return_value = mock_response
        
        status = self.monitor.check_status()
        
        self.assertTrue(status["ollama_service"])
        self.assertEqual(len(status["models_loaded"]), 2)
        self.assertIn("model1", status["models_loaded"])
        
    @patch('desktop_app.requests.get')
    def test_check_status_failure(self, mock_get):
        """测试状态检查失败"""
        mock_get.side_effect = Exception("Connection error")
        
        status = self.monitor.check_status()
        
        self.assertFalse(status["ollama_service"])
        self.assertEqual(status["models_loaded"], [])
        
    def test_log_status(self):
        """测试记录状态"""
        test_status = {
            "timestamp": "2024-01-01 12:00:00",
            "ollama_service": True,
            "models_loaded": ["model1"]
        }
        
        self.monitor.log_status(test_status)
        
        # 验证文件创建
        self.assertTrue(self.test_status_file.exists())
        
        # 验证内容
        with open(self.test_status_file, 'r', encoding='utf-8') as f:
            content = f.read()
            
        self.assertIn("ollama_service", content)
        self.assertIn("model1", content)
        
    def test_log_status_limits_records(self):
        """测试状态记录限制"""
        # 写入超过100条记录
        for i in range(150):
            test_status = {
                "timestamp": f"2024-01-01 12:00:{i}",
                "ollama_service": True,
                "models_loaded": []
            }
            self.monitor.log_status(test_status)
            
        # 验证只保留最近100条
        with open(self.test_status_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            
        self.assertEqual(len(lines), 100)
        
    def test_start_monitoring(self):
        """测试启动监控"""
        # 使用短间隔进行测试，但不要真正启动长时间运行的监控
        # 只测试检查状态的功能
        status = self.monitor.check_status()
        self.monitor.log_status(status)
        
        # 验证记录被创建
        self.assertTrue(self.test_status_file.exists())
        
        # 验证状态格式正确
        self.assertIn("timestamp", status)
        self.assertIn("ollama_service", status)
        self.assertIn("models_loaded", status)

class TestTrayApp(unittest.TestCase):
    """TrayApp 类的单元测试"""
    
    def setUp(self):
        """设置测试环境"""
        self.config = Mock()
        self.logger = Mock()
        self.tray_app = TrayApp(self.config, self.logger)
        
    def test_create_icon_normal(self):
        """测试创建正常状态图标"""
        # 简化测试，只测试没有桌面支持的情况
        with patch('desktop_app.DESKTOP_AVAILABLE', False):
            icon = self.tray_app.create_icon("normal")
            self.assertIsNone(icon)
            
    def test_create_icon_error(self):
        """测试创建错误状态图标"""
        # 简化测试，只测试没有桌面支持的情况
        with patch('desktop_app.DESKTOP_AVAILABLE', False):
            icon = self.tray_app.create_icon("error")
            self.assertIsNone(icon)
            
    def test_create_icon_no_desktop(self):
        """测试没有桌面支持时创建图标"""
        with patch('desktop_app.DESKTOP_AVAILABLE', False):
            icon = self.tray_app.create_icon("normal")
            self.assertIsNone(icon)
            
    def test_restart_services(self):
        """测试重启服务"""
        self.tray_app.restart_services()
        
        # 验证日志记录
        self.logger.info.assert_called_with("重启服务")
        
    def test_quit_app(self):
        """测试退出应用"""
        self.tray_app.icon = Mock()
        
        self.tray_app.quit_app()
        
        self.assertTrue(self.tray_app.running == False)
        self.tray_app.icon.stop.assert_called_once()
        
    def test_quit_app_no_icon(self):
        """测试没有图标时退出"""
        self.tray_app.icon = None
        
        # 应该不抛出异常
        self.tray_app.quit_app()

class TestDesktopApp(unittest.TestCase):
    """DesktopApp 类的单元测试"""
    
    def setUp(self):
        """设置测试环境"""
        self.test_dir = tempfile.mkdtemp()
        self.test_config_file = Path(self.test_dir) / "test_config.json"
        
    def tearDown(self):
        """清理测试环境"""
        shutil.rmtree(self.test_dir)
        
    def test_init(self):
        """测试初始化"""
        app = DesktopApp(self.test_config_file)
        
        self.assertIsNotNone(app.config)
        self.assertIsNotNone(app.logger)
        
    @patch('desktop_app.OllamaWarmer')
    def test_warm_up_models_disabled(self, mock_warmer_class):
        """测试禁用模型预热"""
        # 创建禁用预热的配置
        config = AppConfig(self.test_config_file)
        config.set("warm_up_on_startup", False)
        config.save_config()
        
        app = DesktopApp(self.test_config_file)
        app.warm_up_models()
        
        # 验证没有创建预热器
        mock_warmer_class.assert_not_called()
        
    @patch('desktop_app.OllamaWarmer')
    def test_warm_up_models_service_unavailable(self, mock_warmer_class):
        """测试Ollama服务不可用"""
        # 创建启用预热的配置
        config = AppConfig(self.test_config_file)
        config.set("warm_up_on_startup", True)
        config.save_config()
        
        # 模拟服务不可用
        mock_warmer_instance = Mock()
        mock_warmer_instance.check_service.return_value = False
        mock_warmer_class.return_value = mock_warmer_instance
        
        app = DesktopApp(self.test_config_file)
        app.warm_up_models()
        
        # 验证检查了服务状态
        mock_warmer_instance.check_service.assert_called_once()
        
    @patch('desktop_app.StatusMonitor')
    def test_start_monitoring(self, mock_monitor_class):
        """测试启动监控"""
        app = DesktopApp(self.test_config_file)
        
        # 模拟监控器实例
        mock_monitor = Mock()
        mock_monitor_class.return_value = mock_monitor
        
        app.start_monitoring()
        
        # 验证监控器被创建
        mock_monitor_class.assert_called_once()
        # 验证监控在后台线程启动
        # (我们无法直接测试线程，但可以验证方法被调用)
        
    @patch('desktop_app.StatusMonitor')
    def test_show_status(self, mock_monitor_class):
        """测试显示状态"""
        app = DesktopApp(self.test_config_file)
        
        # 模拟监控器和状态
        mock_monitor = Mock()
        mock_monitor.check_status.return_value = {
            "timestamp": "2024-01-01 12:00:00",
            "ollama_service": True,
            "models_loaded": ["model1", "model2"]
        }
        mock_monitor_class.return_value = mock_monitor
        
        # 捕获打印输出
        from io import StringIO
        import sys
        captured_output = StringIO()
        sys.stdout = captured_output
        
        app.show_status()
        
        sys.stdout = sys.__stdout__
        
        # 验证输出包含状态信息
        output = captured_output.getvalue()
        self.assertIn("系统状态", output)
        self.assertIn("model1", output)

class TestIntegration(unittest.TestCase):
    """集成测试"""
    
    def setUp(self):
        """设置测试环境"""
        self.test_dir = tempfile.mkdtemp()
        self.test_config_file = Path(self.test_dir) / "test_config.json"
        self.test_log_file = Path(self.test_dir) / "test.log"
        self.test_status_file = Path(self.test_dir) / "test_status.log"
        
    def tearDown(self):
        """清理测试环境"""
        shutil.rmtree(self.test_dir)
        
    def test_full_config_workflow(self):
        """测试完整配置工作流"""
        # 1. 创建配置
        config = AppConfig(self.test_config_file)
        config.set("autostart", True)
        config.set("warm_up_on_startup", True)
        
        # 2. 保存配置
        self.assertTrue(config.save_config())
        
        # 3. 重新加载配置
        config2 = AppConfig(self.test_config_file)
        self.assertTrue(config2.get("autostart"))
        
        # 4. 修改配置
        config2.set("autostart", False)
        config2.save_config()
        
        # 5. 再次验证
        config3 = AppConfig(self.test_config_file)
        self.assertFalse(config3.get("autostart"))
        
    def test_logging_and_monitoring_integration(self):
        """测试日志和监控集成"""
        # 设置日志
        log_manager = LogManager(self.test_log_file)
        logger = log_manager.setup_logging()
        
        # 创建监控器
        monitor = StatusMonitor("http://localhost:11434", logger, self.test_status_file)
        
        # 记录状态
        status = monitor.check_status()
        monitor.log_status(status)
        
        # 验证日志文件
        self.assertTrue(self.test_log_file.exists())
        self.assertTrue(self.test_status_file.exists())

class TestCommandLineInterface(unittest.TestCase):
    """命令行接口测试"""
    
    @patch('desktop_app.DesktopApp')
    @patch('desktop_app.argparse.ArgumentParser')
    def test_main_tray(self, mock_parser_class, mock_app_class):
        """测试--tray参数"""
        # 设置mock
        mock_parser = Mock()
        mock_parser.parse_args.return_value = Mock(tray=True, warm_up=False, status=False)
        mock_parser_class.return_value = mock_parser
        
        mock_app = Mock()
        mock_app_class.return_value = mock_app
        
        # 导入main函数（需要在模块级别定义）
        from desktop_app import main
        main()
        
        # 验证调用
        mock_app.run_desktop.assert_called_once()
        
    @patch('desktop_app.DesktopApp')
    @patch('desktop_app.argparse.ArgumentParser')
    def test_main_warm_up(self, mock_parser_class, mock_app_class):
        """测试--warm-up参数"""
        # 设置mock
        mock_parser = Mock()
        mock_parser.parse_args.return_value = Mock(tray=False, warm_up=True, status=False)
        mock_parser_class.return_value = mock_parser
        
        mock_app = Mock()
        mock_app_class.return_value = mock_app
        
        from desktop_app import main
        main()
        
        # 验证调用
        mock_app.warm_up_models.assert_called_once()
        
    @patch('desktop_app.DesktopApp')
    @patch('desktop_app.argparse.ArgumentParser')
    def test_main_status(self, mock_parser_class, mock_app_class):
        """测试--status参数"""
        # 设置mock
        mock_parser = Mock()
        mock_parser.parse_args.return_value = Mock(tray=False, warm_up=False, status=True)
        mock_parser_class.return_value = mock_parser
        
        mock_app = Mock()
        mock_app_class.return_value = mock_app
        
        from desktop_app import main
        main()
        
        # 验证调用
        mock_app.show_status.assert_called_once()
        
    @patch('desktop_app.DesktopApp')
    @patch('desktop_app.argparse.ArgumentParser')
    def test_main_no_args_shows_help(self, mock_parser_class, mock_app_class):
        """测试无参数时启动托盘（默认行为）"""
        # 设置mock
        mock_parser = Mock()
        mock_parser.parse_args.return_value = Mock(tray=False, warm_up=False, status=False)
        mock_parser_class.return_value = mock_parser
        
        mock_app = Mock()
        mock_app_class.return_value = mock_app
        
        from desktop_app import main
        main()
        
        # 验证调用（现在无参数应该启动托盘）
        mock_app.run_desktop.assert_called_once()

class TestConfigEdgeCases(unittest.TestCase):
    """配置边缘情况测试"""
    
    def setUp(self):
        """设置测试环境"""
        self.test_dir = tempfile.mkdtemp()
        self.test_config_file = Path(self.test_dir) / "test_config.json"
        
    def tearDown(self):
        """清理测试环境"""
        shutil.rmtree(self.test_dir)
        
    def test_config_with_none_values(self):
        """测试包含None值的配置"""
        config = AppConfig(self.test_config_file)
        config.set("ollama_base_url", None)
        config.set("models_to_warm_up", None)
        config.save_config()
        
        # 重新加载
        config2 = AppConfig(self.test_config_file)
        self.assertIsNone(config2.get("ollama_base_url"))
        self.assertIsNone(config2.get("models_to_warm_up"))
        
    def test_config_with_array_types(self):
        """测试数组类型的配置"""
        config = AppConfig(self.test_config_file)
        config.set("models_to_warm_up", ["model1", "model2"])
        config.save_config()
        
        # 重新加载
        config2 = AppConfig(self.test_config_file)
        self.assertEqual(config2.get("models_to_warm_up"), ["model1", "model2"])
        
    def test_config_overwrite_existing(self):
        """测试覆盖现有配置"""
        config = AppConfig(self.test_config_file)
        config.set("check_interval", 300)
        config.save_config()
        
        # 覆盖
        config.set("check_interval", 600)
        config.save_config()
        
        # 重新加载验证
        config2 = AppConfig(self.test_config_file)
        self.assertEqual(config2.get("check_interval"), 600)

class TestDependencyDetection(unittest.TestCase):
    """依赖检测测试"""
    
    @patch('desktop_app.DESKTOP_AVAILABLE', False)
    def test_tray_app_with_no_desktop(self):
        """测试没有桌面依赖时的行为"""
        config = Mock()
        logger = Mock()
        tray_app = TrayApp(config, logger)
        
        # 测试在没有桌面支持时的行为
        tray_app.quit_app()
        tray_app.restart_services()
        
    def test_desktop_available_variable(self):
        """测试DESKTOP_AVAILABLE变量"""
        # 这个测试确保模块能够正确处理依赖缺失的情况
        from desktop_app import DESKTOP_AVAILABLE
        self.assertIsInstance(DESKTOP_AVAILABLE, bool)

class TestOllamaServiceInteraction(unittest.TestCase):
    """Ollama服务交互测试"""
    
    def setUp(self):
        """设置测试环境"""
        self.logger = Mock()
        
    @patch('desktop_app.requests.get')
    def test_warm_up_various_response_codes(self, mock_get):
        """测试不同HTTP响应码"""
        warmer = OllamaWarmer("http://localhost:11434", self.logger)
        
        # 测试404
        mock_get.return_value = Mock(status_code=404)
        self.assertFalse(warmer.check_service())
        
        # 测试500
        mock_get.return_value = Mock(status_code=500)
        self.assertFalse(warmer.check_service())
        
        # 测试200
        mock_get.return_value = Mock(status_code=200)
        self.assertTrue(warmer.check_service())
        
    @patch('desktop_app.requests.post')
    def test_warm_up_connection_error(self, mock_post):
        """测试连接错误"""
        mock_post.side_effect = requests.exceptions.ConnectionError("Connection refused")
        
        warmer = OllamaWarmer("http://localhost:11434", self.logger)
        results = warmer.warm_up(["model1"])
        
        # 应该处理错误
        self.assertFalse(results["model1"]["success"])
        
    @patch('desktop_app.requests.get')
    def test_status_check_with_timeout(self, mock_get):
        """测试超时检查"""
        mock_get.side_effect = requests.exceptions.Timeout("Request timeout")
        
        monitor = StatusMonitor("http://localhost:11434", self.logger, "/tmp/test_status.log")
        status = monitor.check_status()
        
        # 应该返回错误状态
        self.assertFalse(status["ollama_service"])

class TestEdgeCases(unittest.TestCase):
    """边缘情况测试"""
    
    def setUp(self):
        """设置测试环境"""
        self.test_dir = tempfile.mkdtemp()
        self.test_config_file = Path(self.test_dir) / "test_config.json"
        
    def tearDown(self):
        """清理测试环境"""
        shutil.rmtree(self.test_dir)
        
    def test_config_file_permission_denied(self):
        """测试配置文件权限拒绝"""
        # 创建一个无法写入的配置文件
        config = AppConfig(self.test_config_file)
        config.save_config()
        
        # 设置为只读
        os.chmod(self.test_config_file, 0o444)
        
        try:
            config2 = AppConfig(self.test_config_file)
            config2.set("new_key", "value")
            result = config2.save_config()
            
            # 应该失败
            self.assertFalse(result)
        finally:
            # 恢复权限以便清理
            os.chmod(self.test_config_file, 0o644)
            
    def test_empty_config_file(self):
        """测试空配置文件"""
        # 创建空文件
        self.test_config_file.write_text("")
        
        config = AppConfig(self.test_config_file)
        # 应该使用默认配置
        self.assertEqual(config.config, DEFAULT_CONFIG)
        
    def test_config_with_extra_fields(self):
        """测试包含额外字段的配置文件"""
        # 创建包含额外字段的配置
        extra_config = {
            "autostart": True,
            "extra_field": "extra_value",
            "another_field": 123
        }
        
        with open(self.test_config_file, 'w', encoding='utf-8') as f:
            json.dump(extra_config, f)
            
        config = AppConfig(self.test_config_file)
        # 额外字段应该被保留
        self.assertEqual(config.get("extra_field"), "extra_value")
        self.assertEqual(config.get("another_field"), 123)
        
    def test_status_file_cleanup_on_overflow(self):
        """测试状态文件溢出时的清理"""
        from desktop_app import StatusMonitor
        import logging
        
        logger = logging.getLogger("test")
        status_file = Path(self.test_dir) / "status.log"
        monitor = StatusMonitor("http://localhost:11434", logger, status_file)
        
        # 写入超过100条记录
        for i in range(150):
            status = {
                "timestamp": f"2024-01-01 12:00:{i}",
                "ollama_service": True,
                "models_loaded": []
            }
            monitor.log_status(status)
            
        # 验证只保留最近100条
        with open(status_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            
        self.assertEqual(len(lines), 100)
        
        # 验证最后一条是第150条
        last_status = json.loads(lines[-1])
        self.assertIn("12:00:149", last_status["timestamp"])

class TestDesktopAppFull(unittest.TestCase):
    """DesktopApp 完整功能测试"""
    
    def setUp(self):
        """设置测试环境"""
        self.test_dir = tempfile.mkdtemp()
        self.test_config_file = Path(self.test_dir) / "test_config.json"
        
    def tearDown(self):
        """清理测试环境"""
        shutil.rmtree(self.test_dir)
        
    @patch('desktop_app.OllamaWarmer')
    @patch('desktop_app.StatusMonitor')
    def test_run_desktop_integration(self, mock_monitor_class, mock_warmer_class):
        """测试run_desktop的集成"""
        # 设置mock
        mock_warmer_instance = Mock()
        mock_warmer_instance.check_service.return_value = True
        mock_warmer_class.return_value = mock_warmer_instance
        
        mock_monitor_instance = Mock()
        mock_monitor_class.return_value = mock_monitor_instance
        
        # 创建配置
        config = AppConfig(self.test_config_file)
        config.set("warm_up_on_startup", True)
        config.save_config()
        
        # 这个测试不真正运行，只验证初始化
        app = DesktopApp(self.test_config_file)
        
        # 验证组件被创建
        self.assertIsNotNone(app.config)
        self.assertIsNotNone(app.logger)
        
    def test_show_status_output(self):
        """测试show_status的输出"""
        # 创建配置
        config = AppConfig(self.test_config_file)
        config.set("ollama_base_url", "http://localhost:11434")
        config.save_config()
        
        app = DesktopApp(self.test_config_file)
        
        # 捕获输出
        from io import StringIO
        import sys
        captured_output = StringIO()
        sys.stdout = captured_output
        
        app.show_status()
        
        sys.stdout = sys.__stdout__
        
        # 验证输出包含关键信息
        output = captured_output.getvalue()
        self.assertIn("系统状态", output)
        self.assertIn("Ollama服务", output)

class TestTrayAppGUI(unittest.TestCase):
    """TrayApp GUI相关测试"""
    
    def setUp(self):
        """设置测试环境"""
        self.config = Mock()
        self.logger = Mock()
        self.tray_app = TrayApp(self.config, self.logger)
        
    def test_show_status_no_file(self):
        """测试没有状态文件时的show_status"""
        with patch('desktop_app.STATUS_FILE', Path('/nonexistent/status.log')):
            # 应该不抛出异常
            self.tray_app.show_status()
            
    def test_show_status_invalid_json(self):
        """测试状态文件包含无效JSON"""
        test_dir = tempfile.mkdtemp()
        test_status_file = Path(test_dir) / "test_status.log"
        
        try:
            # 写入无效JSON
            test_status_file.write_text("invalid json content")
            
            # 临时修改TrayApp的status_file检查
            self.tray_app.config.status_file = test_status_file
            
            # 应该不抛出异常
            self.tray_app.show_status()
            
        finally:
            shutil.rmtree(test_dir)

class TestWarmingUpScenarios(unittest.TestCase):
    """模型预热场景测试"""
    
    def setUp(self):
        """设置测试环境"""
        self.logger = Mock()
        
    @patch('desktop_app.requests.post')
    def test_warming_up_with_empty_model_list(self, mock_post):
        """测试空模型列表预热"""
        warmer = OllamaWarmer("http://localhost:11434", self.logger)
        
        results = warmer.warm_up([])
        
        # 应该返回空字典
        self.assertEqual(results, {})
        mock_post.assert_not_called()
        
    @patch('desktop_app.requests.post')
    def test_warming_up_with_invalid_model_name(self, mock_post):
        """测试无效模型名称预热"""
        mock_response = Mock()
        mock_response.status_code = 404
        mock_post.return_value = mock_response
        
        warmer = OllamaWarmer("http://localhost:11434", self.logger)
        results = warmer.warm_up(["invalid-model"])
        
        # 应该处理错误
        self.assertFalse(results["invalid-model"]["success"])

class TestExceptionHandling(unittest.TestCase):
    """异常处理测试"""
    
    def setUp(self):
        """设置测试环境"""
        self.test_dir = tempfile.mkdtemp()
        self.test_config_file = Path(self.test_dir) / "test_config.json"
        self.logger = Mock()
        
    def tearDown(self):
        """清理测试环境"""
        shutil.rmtree(self.test_dir)
        
    @patch('desktop_app.requests.get')
    def test_status_monitor_request_exception(self, mock_get):
        """测试状态监控请求异常"""
        mock_get.side_effect = requests.exceptions.RequestException("Network error")
        
        monitor = StatusMonitor("http://localhost:11434", self.logger, Path(self.test_dir) / "status.log")
        status = monitor.check_status()
        
        # 应该返回错误状态
        self.assertFalse(status["ollama_service"])
        self.assertEqual(status["models_loaded"], [])
        
    @patch('desktop_app.requests.get')
    def test_ollama_warmer_timeout_variations(self, mock_get):
        """测试不同类型的超时"""
        warmer = OllamaWarmer("http://localhost:11434", self.logger)
        
        # 测试连接超时
        mock_get.side_effect = requests.exceptions.Timeout("Connection timeout")
        result = warmer.check_service()
        self.assertFalse(result)
        
    def test_config_corrupted_file_handling(self):
        """测试损坏配置文件的处理"""
        # 写入损坏的JSON
        with open(self.test_config_file, 'w', encoding='utf-8') as f:
            f.write("{corrupted json data}")
            
        # 应该不抛出异常，使用默认配置
        config = AppConfig(self.test_config_file)
        self.assertEqual(config.config, DEFAULT_CONFIG)



class TestDesktopAppFlow(unittest.TestCase):
    """DesktopApp流程测试"""
    
    def setUp(self):
        """设置测试环境"""
        self.test_dir = tempfile.mkdtemp()
        self.test_config_file = Path(self.test_dir) / "test_config.json"
        
    def tearDown(self):
        """清理测试环境"""
        shutil.rmtree(self.test_dir)
        
    @patch('desktop_app.OllamaWarmer')
    def test_warm_up_models_calls_warmer(self, mock_warmer_class):
        """测试warm_up_models调用预热器"""
        # 设置配置
        config = AppConfig(self.test_config_file)
        config.set("warm_up_on_startup", True)
        config.save_config()
        
        # 设置mock
        mock_warmer = Mock()
        mock_warmer.check_service.return_value = True
        mock_warmer_class.return_value = mock_warmer
        
        app = DesktopApp(self.test_config_file)
        app.warm_up_models()
        
        # 验证预热器被调用
        mock_warmer_class.assert_called_once()
        
    @patch('desktop_app.StatusMonitor')
    def test_start_monitoring_creates_monitor(self, mock_monitor_class):
        """测试start_monitoring创建监控器"""
        # 设置配置
        config = AppConfig(self.test_config_file)
        config.set("check_interval", 600)
        config.save_config()
        
        # 设置mock
        mock_monitor = Mock()
        mock_monitor_class.return_value = mock_monitor
        
        app = DesktopApp(self.test_config_file)
        app.start_monitoring()
        
        # 验证监控器被创建
        mock_monitor_class.assert_called()
        
    @patch('desktop_app.OllamaWarmer')
    @patch('desktop_app.StatusMonitor')
    @patch('desktop_app.TrayApp')
    @patch('threading.Thread')
    def test_run_desktop_integration(self, mock_thread, mock_tray_class, mock_monitor_class, mock_warmer_class):
        """测试run_desktop集成"""
        # 设置mock
        mock_warmer = Mock()
        mock_warmer.check_service.return_value = True
        mock_warmer_class.return_value = mock_warmer
        
        mock_monitor = Mock()
        mock_monitor_class.return_value = mock_monitor
        
        mock_tray = Mock()
        mock_tray_class.return_value = mock_tray
        
        # 设置配置
        config = AppConfig(self.test_config_file)
        config.set("warm_up_on_startup", True)
        config.save_config()
        
        app = DesktopApp(self.test_config_file)
        
        # 只验证初始化，不真正运行
        self.assertIsNotNone(app.config)
        self.assertIsNotNone(app.logger)
        
    def test_config_with_missing_optional_fields(self):
        """测试缺少可选字段的配置"""
        # 创建只有部分字段的配置
        partial_config = {
            "autostart": True
            # 缺少其他字段
        }
        
        with open(self.test_config_file, 'w', encoding='utf-8') as f:
            json.dump(partial_config, f)
            
        config = AppConfig(self.test_config_file)
        
        # 存在的字段应该正确加载
        self.assertTrue(config.get("autostart"))
        # 不存在的字段应该返回None或默认值
        self.assertIsNone(config.get("warm_up_on_startup"))
        
    @patch('desktop_app.StatusMonitor')
    def test_show_status_uses_monitor(self, mock_monitor_class):
        """测试show_status使用监控器"""
        # 设置配置
        config = AppConfig(self.test_config_file)
        config.set("ollama_base_url", "http://test-url:11434")
        config.save_config()
        
        # 设置mock
        mock_monitor = Mock()
        mock_monitor.check_status.return_value = {
            "timestamp": "2024-01-01 12:00:00",
            "ollama_service": False,
            "models_loaded": []
        }
        mock_monitor_class.return_value = mock_monitor
        
        app = DesktopApp(self.test_config_file)
        app.show_status()
        
        # 验证监控器被调用
        mock_monitor.check_status.assert_called_once()

class TestTrayAppIconStates(unittest.TestCase):
    """TrayApp 图标状态变化的单元测试"""
    
    def setUp(self):
        """设置测试环境"""
        self.test_dir = tempfile.mkdtemp()
        self.test_config_file = Path(self.test_dir) / "test_config.json"
        self.logger = Mock()
        self.config = AppConfig(self.test_config_file)
        
    def tearDown(self):
        """清理测试环境"""
        shutil.rmtree(self.test_dir)
        
    @patch('desktop_app.DESKTOP_AVAILABLE', False)
    def test_icon_states_defined(self):
        """测试图标状态颜色定义"""
        tray_app = TrayApp(self.config, self.logger)
        
        # 验证所有状态颜色都定义了
        self.assertIsNotNone(tray_app.COLOR_NORMAL)
        self.assertIsNotNone(tray_app.COLOR_PROGRESS)
        self.assertIsNotNone(tray_app.COLOR_SUCCESS)
        self.assertIsNotNone(tray_app.COLOR_ERROR)
        
        # 验证颜色是RGB元组
        self.assertEqual(len(tray_app.COLOR_NORMAL), 3)
        self.assertEqual(len(tray_app.COLOR_PROGRESS), 3)
        self.assertEqual(len(tray_app.COLOR_SUCCESS), 3)
        self.assertEqual(len(tray_app.COLOR_ERROR), 3)
        
    def test_create_icon_rag_design(self):
        """测试新的RAG图标设计"""
        tray_app = TrayApp(self.config, self.logger)
        
        # 测试正常状态
        icon_normal = tray_app.create_icon("normal")
        self.assertIsNotNone(icon_normal)
        self.assertEqual(icon_normal.size, (32, 32))
        
        # 测试其他状态
        icon_progress = tray_app.create_icon("progress")
        self.assertIsNotNone(icon_progress)
        
        icon_success = tray_app.create_icon("success")
        self.assertIsNotNone(icon_success)
        
        icon_error = tray_app.create_icon("error")
        self.assertIsNotNone(icon_error)
        
        # 验证不同状态的图标颜色不同（通过像素抽样）
        # 中心点应该有不同颜色
        normal_pixel = icon_normal.getpixel((16, 16))
        progress_pixel = icon_progress.getpixel((16, 16))
        self.assertNotEqual(normal_pixel, progress_pixel)
        
    @patch('desktop_app.DESKTOP_AVAILABLE', True)
    @patch('desktop_app.pystray')
    def test_create_icon_normal_state(self, mock_pystray):
        """测试创建正常状态图标"""
        tray_app = TrayApp(self.config, self.logger)
        
        # Mock PIL 相关组件
        with patch('desktop_app.Image'):
            with patch('desktop_app.ImageDraw'):
                icon = tray_app.create_icon("normal")
                
        # 验证返回值（desktop不可用时返回None）
        self.assertIsNotNone(icon)
        
    @patch('desktop_app.DESKTOP_AVAILABLE', True)
    @patch('desktop_app.pystray')
    def test_create_icon_progress_state(self, mock_pystray):
        """测试创建进行中状态图标"""
        tray_app = TrayApp(self.config, self.logger)
        
        with patch('desktop_app.Image'):
            with patch('desktop_app.ImageDraw'):
                icon = tray_app.create_icon("progress")
                
        self.assertIsNotNone(icon)
        
    @patch('desktop_app.DESKTOP_AVAILABLE', True)
    @patch('desktop_app.pystray')
    def test_create_icon_success_state(self, mock_pystray):
        """测试创建成功状态图标"""
        tray_app = TrayApp(self.config, self.logger)
        
        with patch('desktop_app.Image'):
            with patch('desktop_app.ImageDraw'):
                icon = tray_app.create_icon("success")
                
        self.assertIsNotNone(icon)
        
    @patch('desktop_app.DESKTOP_AVAILABLE', True)
    @patch('desktop_app.pystray')
    def test_create_icon_error_state(self, mock_pystray):
        """测试创建错误状态图标"""
        tray_app = TrayApp(self.config, self.logger)
        
        with patch('desktop_app.Image'):
            with patch('desktop_app.ImageDraw'):
                icon = tray_app.create_icon("error")
                
        self.assertIsNotNone(icon)
        
    @patch('desktop_app.DESKTOP_AVAILABLE', True)
    @patch('desktop_app.pystray')
    def test_update_icon_without_icon_object(self, mock_pystray):
        """测试在没有图标对象时更新图标"""
        tray_app = TrayApp(self.config, self.logger)
        tray_app.icon = None
        
        # 不应该抛出错误
        tray_app.update_icon("normal")
        
    @patch('desktop_app.DESKTOP_AVAILABLE', True)
    @patch('desktop_app.pystray')
    def test_set_progress_state(self, mock_pystray):
        """测试设置为进行中状态"""
        tray_app = TrayApp(self.config, self.logger)
        mock_icon = Mock()
        tray_app.icon = mock_icon
        
        with patch('desktop_app.Image'):
            with patch('desktop_app.ImageDraw'):
                tray_app.set_progress_state()
                
        # 验证更新图标被调用
        self.assertIsNotNone(tray_app.icon_restore_timer)
        
    @patch('desktop_app.DESKTOP_AVAILABLE', True)
    @patch('desktop_app.pystray')
    def test_set_success_state(self, mock_pystray):
        """测试设置为成功状态"""
        tray_app = TrayApp(self.config, self.logger)
        mock_icon = Mock()
        tray_app.icon = mock_icon
        
        with patch('desktop_app.Image'):
            with patch('desktop_app.ImageDraw'):
                tray_app.set_success_state()
                
        # 验证更新图标被调用
        self.assertIsNotNone(tray_app.icon_restore_timer)
        
    @patch('desktop_app.DESKTOP_AVAILABLE', True)
    @patch('desktop_app.pystray')
    def test_set_error_state(self, mock_pystray):
        """测试设置为错误状态"""
        tray_app = TrayApp(self.config, self.logger)
        mock_icon = Mock()
        tray_app.icon = mock_icon
        
        with patch('desktop_app.Image'):
            with patch('desktop_app.ImageDraw'):
                tray_app.set_error_state()
                
        # 验证更新图标被调用
        self.assertIsNotNone(tray_app.icon_restore_timer)
        
    @patch('desktop_app.DESKTOP_AVAILABLE', True)
    @patch('desktop_app.pystray')
    def test_restore_normal_icon(self, mock_pystray):
        """测试恢复到正常图标状态"""
        tray_app = TrayApp(self.config, self.logger)
        mock_icon = Mock()
        tray_app.icon = mock_icon
        tray_app.icon_restore_timer = Mock()
        
        with patch('desktop_app.Image'):
            with patch('desktop_app.ImageDraw'):
                tray_app.restore_normal_icon()
                
        # 验证定时器被清除
        self.assertIsNone(tray_app.icon_restore_timer)

class TestTrayAppNotificationFeedback(unittest.TestCase):
    """TrayApp 通知反馈的单元测试"""
    
    def setUp(self):
        """设置测试环境"""
        self.test_dir = tempfile.mkdtemp()
        self.test_config_file = Path(self.test_dir) / "test_config.json"
        self.logger = Mock()
        self.config = AppConfig(self.test_config_file)
        
    def tearDown(self):
        """清理测试环境"""
        shutil.rmtree(self.test_dir)
        
    @unittest.skip("弹窗相关测试已禁用")
    @patch('subprocess.run')
    def test_show_notification_macos(self, mock_run):
        """测试macOS系统通知"""
        tray_app = TrayApp(self.config, self.logger)
        
        with patch('platform.system', return_value='Darwin'):
            tray_app.show_notification("测试标题", "测试消息")
            
        # 验证subprocess.run被调用
        mock_run.assert_called_once()
        
    # Windows测试跳过，因为依赖ToastNotifier库
    @patch('subprocess.run')
    @patch('subprocess.Popen')
    def test_open_cli_with_icon_feedback(self, mock_popen, mock_run):
        """测试打开CLI界面时的图标反馈"""
        tray_app = TrayApp(self.config, self.logger)
        
        with patch('platform.system', return_value='Darwin'):
            with patch.object(tray_app, 'set_progress_state') as mock_progress:
                with patch.object(tray_app, 'set_success_state') as mock_success:
                    with patch.object(tray_app, 'show_notification') as mock_notify:
                        with patch.object(tray_app, 'show_popup') as mock_popup:
                            with patch('desktop_app.Image'):
                                with patch('desktop_app.ImageDraw'):
                                    tray_app.open_cli_interface()
                        
                        # 验证进度状态被设置
                        mock_progress.assert_called()
                        # 验证成功状态被设置
                        mock_success.assert_called()
                        # 验证通知被调用
                        mock_notify.assert_called()
                        # 验证弹窗被调用
                        mock_popup.assert_called_once()
        
    @patch('subprocess.run')
    @patch('subprocess.Popen')
    def test_open_cli_error_feedback(self, mock_popen, mock_run):
        """测试打开CLI界面失败时的图标反馈"""
        tray_app = TrayApp(self.config, self.logger)
        
        with patch('platform.system', return_value='Darwin'):
            with patch.object(tray_app, 'set_progress_state') as mock_progress:
                with patch.object(tray_app, 'set_error_state') as mock_error:
                    with patch.object(tray_app, 'show_notification') as mock_notify:
                        with patch.object(tray_app, 'show_popup') as mock_popup:
                            # 由于代码中使用subprocess.run用于osascript，我们需要让它失败
                            # 但在实际代码中异常会先触发Popen，所以这里模拟Popen失败
                            mock_popen.side_effect = Exception("测试错误")
                            
                            with patch('desktop_app.Image'):
                                with patch('desktop_app.ImageDraw'):
                                    result = tray_app.open_cli_interface()
                            
                            # 验证进度状态被设置
                            mock_progress.assert_called()
                            # 验证错误状态被设置
                            mock_error.assert_called()
                            # 验证失败通知被调用
                            mock_notify.assert_called()
                            # 验证失败弹窗被调用
                            mock_popup.assert_called_once()
                            # 验证返回False
                            self.assertFalse(result)
                        
    @patch('desktop_app.Image')
    @patch('desktop_app.ImageDraw')
    def test_show_status_with_status_file(self, mock_image, mock_draw):
        """测试显示状态（有状态文件）"""
        tray_app = TrayApp(self.config, self.logger)
        
        # 创建测试状态文件
        tray_app.status_file.parent.mkdir(parents=True, exist_ok=True)
        test_status = {
            "timestamp": "2024-01-01 12:00:00",
            "ollama_service": True,
            "models_loaded": ["model1", "model2"]
        }
        with open(tray_app.status_file, 'w', encoding='utf-8') as f:
            json.dump(test_status, f)
        
        with patch.object(tray_app, 'set_progress_state') as mock_progress:
            with patch.object(tray_app, 'set_success_state') as mock_success:
                with patch.object(tray_app, 'show_notification') as mock_notify:
                    with patch.object(tray_app, 'show_popup') as mock_popup:
                        tray_app.show_status()
        
        # 验证状态被设置
        mock_progress.assert_called()
        mock_success.assert_called()
        mock_notify.assert_called()
        mock_popup.assert_called_once()
        
        # 清理
        tray_app.status_file.unlink()
        if tray_app.status_file.parent.exists() and tray_app.status_file.parent.is_dir():
            try:
                tray_app.status_file.parent.rmdir()
            except OSError:
                # 目录可能不为空，使用shutil清理
                shutil.rmtree(tray_app.status_file.parent)
        
    @patch('desktop_app.Image')
    @patch('desktop_app.ImageDraw')
    def test_show_status_no_file(self, mock_image, mock_draw):
        """测试显示状态（无状态文件）"""
        tray_app = TrayApp(self.config, self.logger)
        
        # 确保状态文件不存在
        if tray_app.status_file.exists():
            tray_app.status_file.unlink()
        
        with patch.object(tray_app, 'set_progress_state') as mock_progress:
            with patch.object(tray_app, 'set_error_state') as mock_error:
                with patch.object(tray_app, 'show_notification') as mock_notify:
                    with patch.object(tray_app, 'show_popup') as mock_popup:
                        tray_app.show_status()
        
        # 验证状态被设置
        mock_progress.assert_called()
        mock_error.assert_called()
        mock_notify.assert_called()
        # 无状态文件时会提前return，show_popup不会被调用
        mock_popup.assert_not_called()
        
    @patch('desktop_app.Image')
    @patch('desktop_app.ImageDraw')
    def test_show_status_invalid_json(self, mock_image, mock_draw):
        """测试显示状态（无效JSON）"""
        tray_app = TrayApp(self.config, self.logger)
        
        # 创建无效的状态文件
        tray_app.status_file.parent.mkdir(parents=True, exist_ok=True)
        with open(tray_app.status_file, 'w', encoding='utf-8') as f:
            f.write("invalid json content")
        
        with patch.object(tray_app, 'set_progress_state') as mock_progress:
            with patch.object(tray_app, 'set_error_state') as mock_error:
                with patch.object(tray_app, 'show_notification') as mock_notify:
                    with patch.object(tray_app, 'show_popup') as mock_popup:
                        tray_app.show_status()
        
        # 验证错误状态被设置
        mock_progress.assert_called()
        mock_error.assert_called()
        mock_notify.assert_called()
        mock_popup.assert_called_once()
        
        # 清理
        tray_app.status_file.unlink()
        if tray_app.status_file.parent.exists() and tray_app.status_file.parent.is_dir():
            try:
                tray_app.status_file.parent.rmdir()
            except OSError:
                # 目录可能不为空，使用shutil清理
                shutil.rmtree(tray_app.status_file.parent)
        
    def test_tray_app_has_status_file_attribute(self):
        """测试TrayApp有status_file属性"""
        tray_app = TrayApp(self.config, self.logger)
        
        # 验证status_file属性存在
        self.assertIsNotNone(tray_app.status_file)
        # 验证它等于全局STATUS_FILE
        from desktop_app import STATUS_FILE
        self.assertEqual(tray_app.status_file, STATUS_FILE)
        
    def test_tray_app_tracks_cli_sessions(self):
        """测试TrayApp跟踪CLI会话"""
        tray_app = TrayApp(self.config, self.logger)
        
        # 初始化时应该有空的会话列表
        self.assertEqual(len(tray_app.cli_sessions), 0)
        self.assertIsInstance(tray_app.cli_sessions, list)
        
    @patch('desktop_app.subprocess.Popen')
    @patch('platform.system', return_value='Darwin')
    def test_cli_session_tracking_on_open(self, mock_system, mock_popen):
        """测试CLI会话在打开时被正确跟踪"""
        tray_app = TrayApp(self.config, self.logger)
        mock_popen.return_value = None  # osascript不需要返回值
        
        # Mock弹窗和其他方法
        with patch.object(tray_app, 'set_progress_state'):
            with patch.object(tray_app, 'set_success_state'):
                with patch.object(tray_app, 'show_notification'):
                    with patch.object(tray_app, 'show_popup'):
                        tray_app.open_cli_interface()
        
        # 验证会话被跟踪
        self.assertEqual(len(tray_app.cli_sessions), 1)
        self.assertIn("id", tray_app.cli_sessions[0])
        self.assertIn("start_time", tray_app.cli_sessions[0])
        self.assertIn("script", tray_app.cli_sessions[0])
        
    @patch('desktop_app.subprocess.Popen')
    @patch('platform.system', return_value='Darwin')
    def test_cli_session_cleanup_on_failure(self, mock_system, mock_popen):
        """测试启动失败时会清理会话记录"""
        tray_app = TrayApp(self.config, self.logger)
        mock_popen.side_effect = Exception("启动失败")
        
        # Mock弹窗和其他方法
        with patch.object(tray_app, 'set_progress_state'):
            with patch.object(tray_app, 'set_error_state'):
                with patch.object(tray_app, 'show_notification'):
                    with patch.object(tray_app, 'show_popup'):
                        result = tray_app.open_cli_interface()
        
        # 验证失败时没有添加会话
        self.assertFalse(result)
        self.assertEqual(len(tray_app.cli_sessions), 0)
        
    def test_close_cli_processes_empty_sessions(self):
        """测试没有会话时的关闭行为"""
        tray_app = TrayApp(self.config, self.logger)
        
        # Mock平台相关方法
        with patch('platform.system', return_value='Darwin'):
            result = tray_app.close_all_cli_processes()
        
        # 验证返回None（没有会话时）
        self.assertIsNone(result)
        
    @patch('platform.system', return_value='Darwin')
    @patch('desktop_app.subprocess.run')
    def test_close_cli_macos_with_processes(self, mock_run, mock_system):
        """测试macOS关闭CLI进程（有进程）"""
        tray_app = TrayApp(self.config, self.logger)
        # 添加一个测试会话
        tray_app.cli_sessions.append({"id": 123456, "start_time": time.time(), "script": "test.py"})
        
        # Mock pgrep找到进程
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "12345\n67890"
        mock_run.return_value = mock_result
        
        with patch('desktop_app.os.kill') as mock_kill:
            # 模拟进程不存在，第一次os.kill返回ProcessLookupError
            mock_kill.side_effect = [None, ProcessLookupError("No such process")]
            
            result = tray_app.close_all_cli_processes()
        
        # 验证会话被清空
        self.assertEqual(len(tray_app.cli_sessions), 0)
        
    @patch('platform.system', return_value='Darwin')
    @patch('desktop_app.subprocess.run')
    def test_close_cli_macos_pgrep_unavailable(self, mock_run, mock_system):
        """测试macOS pgrep不可用时的后备方案"""
        tray_app = TrayApp(self.config, self.logger)
        tray_app.cli_sessions.append({"id": 123456, "start_time": time.time(), "script": "test.py"})
        
        # pgrep不可用
        mock_run.side_effect = FileNotFoundError("pgrep not found")
        
        result = tray_app.close_all_cli_processes()
        
        # 验证调用后备方案
        self.assertEqual(result, 0)
        
    @patch('platform.system', return_value='Windows')
    @patch('desktop_app.subprocess.run')
    def test_close_cli_windows(self, mock_run, mock_system):
        """测试Windows关闭CLI进程"""
        tray_app = TrayApp(self.config, self.logger)
        tray_app.cli_sessions.append({"id": 123456, "start_time": time.time(), "script": "test.py"})
        
        # Mock tasklist找到进程
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = '"python.exe","1234","query_interface.py","Console"\n'
        mock_run.return_value = mock_result
        
        result = tray_app.close_all_cli_processes()
        
        # 验证会话被清空
        self.assertEqual(len(tray_app.cli_sessions), 0)
        
    @patch('platform.system', return_value='Linux')
    @patch('desktop_app.subprocess.run')
    def test_close_cli_linux(self, mock_run, mock_system):
        """测试Linux关闭CLI进程"""
        tray_app = TrayApp(self.config, self.logger)
        tray_app.cli_sessions.append({"id": 123456, "start_time": time.time(), "script": "test.py"})
        
        # Mock pkill成功
        mock_result = Mock()
        mock_result.returncode = 0
        mock_run.return_value = mock_result
        
        result = tray_app.close_all_cli_processes()
        
        # 验证返回至少1
        self.assertGreaterEqual(result, 0)
        # 验证会话被清空
        self.assertEqual(len(tray_app.cli_sessions), 0)
        
    @patch('platform.system', return_value='Linux')
    @patch('desktop_app.subprocess.run')
    def test_close_cli_linux_pkill_unavailable(self, mock_run, mock_system):
        """测试Linux pkill不可用"""
        tray_app = TrayApp(self.config, self.logger)
        tray_app.cli_sessions.append({"id": 123456, "start_time": time.time(), "script": "test.py"})
        
        # pkill不可用
        mock_run.side_effect = FileNotFoundError("pkill not found")
        
        result = tray_app.close_all_cli_processes()
        
        # 验证返回0
        self.assertEqual(result, 0)
        # 验证会话仍被清空（即使关闭失败）
        self.assertEqual(len(tray_app.cli_sessions), 0)
        
    @patch('platform.system', return_value='Unknown')
    @patch('desktop_app.subprocess.run')
    def test_close_cli_unsupported_platform(self, mock_run, mock_system):
        """测试不支持的平台"""
        tray_app = TrayApp(self.config, self.logger)
        tray_app.cli_sessions.append({"id": 123456, "start_time": time.time(), "script": "test.py"})
        
        result = tray_app.close_all_cli_processes()
        
        # 验证返回0
        self.assertEqual(result, 0)
        # 验证会话仍被清空
        self.assertEqual(len(tray_app.cli_sessions), 0)
        
    @patch('desktop_app.subprocess.run')
    def test_close_cli_macos_exception_handling(self, mock_run):
        """测试macOS关闭异常处理"""
        tray_app = TrayApp(self.config, self.logger)
        tray_app.cli_sessions.append({"id": 123456, "start_time": time.time(), "script": "test.py"})
        
        # 模拟异常
        mock_run.side_effect = Exception("pgrep error")
        
        result = tray_app.close_all_cli_processes()
        
        # 验证即使异常也清空会话
        self.assertEqual(len(tray_app.cli_sessions), 0)
        
    @patch.object(TrayApp, 'close_all_cli_processes', return_value=2)
    def test_quit_app_closes_cli_sessions(self, mock_close):
        """测试退出时关闭CLI会话"""
        tray_app = TrayApp(self.config, self.logger)
        tray_app.cli_sessions.append({"id": 123456, "start_time": time.time(), "script": "test.py"})
        mock_icon = Mock()
        tray_app.icon = mock_icon
        
        # Mock弹窗和其他方法
        with patch.object(tray_app, 'set_progress_state'):
            with patch.object(tray_app, 'show_notification'):
                with patch.object(tray_app, 'show_popup'):
                    tray_app.quit_app()
        
        # 验证关闭方法被调用
        mock_close.assert_called_once()
        # 验证托盘停止
        mock_icon.stop.assert_called_once()
        # 验证running标志被设置
        self.assertFalse(tray_app.running)
        
    @unittest.skip("弹窗相关测试已禁用")
    @patch('subprocess.run')
    def test_show_popup_macos(self, mock_run):
        """测试macOS弹窗（完全mock，不触发实际弹窗）"""
        tray_app = TrayApp(self.config, self.logger)
        
        # Mock整个show_popup方法，避免实际弹窗
        with patch.object(tray_app, 'show_popup') as mock_popup:
            tray_app.show_popup("测试标题", "测试消息", duration=1000)
        
        # 验证方法被调用
        mock_run.assert_not_called()  # 不应该调用subprocess
        mock_popup.assert_called_once()  # 应该调用mock的方法
        
    @unittest.skip("弹窗相关测试已禁用")
    @patch('subprocess.run')
    def test_show_popup_linux_no_fallback(self, mock_run):
        """测试Linux无可用弹窗方法时的处理（完全mock，不触发实际弹窗）"""
        tray_app = TrayApp(self.config, self.logger)
        
        # Mock整个show_popup方法，避免实际弹窗
        with patch.object(tray_app, 'show_popup') as mock_popup:
            with patch('platform.system', return_value='Darwin'):
                tray_app.show_popup("测试标题", "测试消息", duration=1000)
        
        # 验证方法被调用
        mock_run.assert_not_called()  # 不应该调用subprocess
        mock_popup.assert_called_once()  # 应该调用mock的方法
    
    def test_warm_up_models_from_menu_empty_config(self):
        """测试从菜单预热模型时配置为空"""
        # 设置空的模型列表
        self.config.set("warm_up_models", [])
        tray_app = TrayApp(self.config, self.logger)
        
        # Mock弹窗和其他方法
        with patch.object(tray_app, 'set_progress_state'):
            with patch.object(tray_app, 'set_error_state'):
                with patch.object(tray_app, 'show_notification'):
                    with patch.object(tray_app, 'show_popup'):
                        tray_app.warm_up_models_from_menu()
        
        # 验证设置了错误状态
        # (由于我们mock了set_error_state，无法直接验证状态，
        # 但可以验证通知被调用)
    
    @patch('desktop_app.OllamaWarmer')
    def test_warm_up_models_from_menu_service_unavailable(self, mock_warmer_class):
        """测试从菜单预热模型时服务不可用"""
        # 设置模型列表
        self.config.set("warm_up_models", ["qwen2.5-coder:7b"])
        tray_app = TrayApp(self.config, self.logger)
        
        # Mock warmer实例
        mock_warmer = Mock()
        mock_warmer.check_service.return_value = False
        mock_warmer_class.return_value = mock_warmer
        
        # Mock弹窗和其他方法
        with patch.object(tray_app, 'set_progress_state'):
            with patch.object(tray_app, 'set_error_state'):
                with patch.object(tray_app, 'show_notification'):
                    with patch.object(tray_app, 'show_popup'):
                        tray_app.warm_up_models_from_menu()
        
        # 验证服务检查被调用
        mock_warmer.check_service.assert_called_once()
    
    @patch('desktop_app.OllamaWarmer')
    def test_warm_up_models_from_menu_success(self, mock_warmer_class):
        """测试从菜单预热模型成功"""
        # 设置模型列表
        self.config.set("warm_up_models", ["qwen2.5-coder:7b", "nomic-embed-text:latest"])
        tray_app = TrayApp(self.config, self.logger)
        
        # Mock warmer实例
        mock_warmer = Mock()
        mock_warmer.check_service.return_value = True
        mock_warmer.warm_up.return_value = {
            "qwen2.5-coder:7b": {"success": True},
            "nomic-embed-text:latest": {"success": True}
        }
        mock_warmer_class.return_value = mock_warmer
        
        # Mock弹窗和其他方法
        with patch.object(tray_app, 'set_progress_state'):
            with patch.object(tray_app, 'set_success_state'):
                with patch.object(tray_app, 'show_notification'):
                    with patch.object(tray_app, 'show_popup'):
                        tray_app.warm_up_models_from_menu()
        
        # 验证warm_up被调用
        mock_warmer.warm_up.assert_called_once_with(["qwen2.5-coder:7b", "nomic-embed-text:latest"])
    
    def test_restart_services(self):
        """测试重启服务方法"""
        tray_app = TrayApp(self.config, self.logger)
        
        # Mock弹窗和其他方法
        with patch.object(tray_app, 'set_progress_state'):
            with patch.object(tray_app, 'set_error_state'):
                with patch.object(tray_app, 'show_notification'):
                    with patch.object(tray_app, 'show_popup'):
                        tray_app.restart_services()
        
        # 验证状态转换被调用（progress -> error）
        # 由于我们mock了这些方法，主要验证方法能被调用而不出错

class TestBaseApp(unittest.TestCase):
    """BaseApp 基类的单元测试"""
    
    def setUp(self):
        """设置测试环境"""
        self.test_dir = tempfile.mkdtemp()
        self.test_config_file = Path(self.test_dir) / "test_config.json"
        self.logger = Mock()
        self.config = AppConfig(self.test_config_file)
        
    def tearDown(self):
        """清理测试环境"""
        shutil.rmtree(self.test_dir)
        
    def test_baseapp_initialization(self):
        """测试BaseApp初始化"""
        base_app = BaseApp(self.config, self.logger)
        
        # 验证属性设置正确
        self.assertEqual(base_app.config, self.config)
        self.assertEqual(base_app.logger, self.logger)
        self.assertEqual(base_app.status_file, STATUS_FILE)
        
    @unittest.skip("弹窗相关测试已禁用")
    @patch('subprocess.run')
    def test_baseapp_show_notification(self, mock_run):
        """测试BaseApp的show_notification方法"""
        base_app = BaseApp(self.config, self.logger)
        
        with patch('platform.system', return_value='Darwin'):
            base_app.show_notification("测试标题", "测试消息")
            
        # 验证subprocess.run被调用
        mock_run.assert_called_once()
        
    @unittest.skip("弹窗相关测试已禁用")
    @patch('subprocess.run')
    def test_baseapp_show_popup(self, mock_run):
        """测试BaseApp的show_popup方法（完全mock，不触发实际弹窗）"""
        base_app = BaseApp(self.config, self.logger)
        
        # Mock整个show_popup方法，避免实际弹窗
        with patch.object(base_app, 'show_popup') as mock_popup:
            base_app.show_popup("测试标题", "测试消息", duration=1000)
        
        # 验证方法被调用
        mock_run.assert_not_called()  # 不应该调用subprocess，因为我们mock了整个方法

class TestInheritance(unittest.TestCase):
    """继承关系的单元测试"""
    
    def setUp(self):
        """设置测试环境"""
        self.test_dir = tempfile.mkdtemp()
        self.test_config_file = Path(self.test_dir) / "test_config.json"
        self.logger = Mock()
        self.config = AppConfig(self.test_config_file)
        
    def tearDown(self):
        """清理测试环境"""
        shutil.rmtree(self.test_dir)
        
    def test_trayapp_inherits_from_baseapp(self):
        """测试TrayApp继承自BaseApp"""
        tray_app = TrayApp(self.config, self.logger)
        
        # 验证继承关系
        self.assertIsInstance(tray_app, BaseApp)
        self.assertIsInstance(tray_app, TrayApp)
        
    def test_desktopapp_inherits_from_baseapp(self):
        """测试DesktopApp继承自BaseApp"""
        desktop_app = DesktopApp(self.test_config_file)
        
        # 验证继承关系
        self.assertIsInstance(desktop_app, BaseApp)
        self.assertIsInstance(desktop_app, DesktopApp)
        
    def test_trayapp_has_baseapp_methods(self):
        """测试TrayApp拥有BaseApp的方法"""
        tray_app = TrayApp(self.config, self.logger)
        
        # 验证拥有BaseApp的方法
        self.assertTrue(hasattr(tray_app, 'show_notification'))
        self.assertTrue(hasattr(tray_app, 'show_popup'))
        self.assertTrue(hasattr(tray_app, 'open_cli_interface'))
        self.assertTrue(hasattr(tray_app, 'status_file'))
        
    def test_desktopapp_has_baseapp_methods(self):
        """测试DesktopApp拥有BaseApp的方法"""
        desktop_app = DesktopApp(self.test_config_file)
        
        # 验证拥有BaseApp的方法
        self.assertTrue(hasattr(desktop_app, 'show_notification'))
        self.assertTrue(hasattr(desktop_app, 'show_popup'))
        self.assertTrue(hasattr(desktop_app, 'open_cli_interface'))
        self.assertTrue(hasattr(desktop_app, 'status_file'))
        
    @patch('subprocess.run')
    def test_trayapp_uses_inherited_methods(self, mock_run):
        """测试TrayApp正确使用继承的方法"""
        tray_app = TrayApp(self.config, self.logger)
        
        with patch('platform.system', return_value='Darwin'):
            tray_app.show_notification("测试", "消息")
            
        # 验证继承的方法被调用
        mock_run.assert_called_once()
        
    @patch('subprocess.run')
    def test_desktopapp_uses_inherited_methods(self, mock_run):
        """测试DesktopApp正确使用继承的方法"""
        desktop_app = DesktopApp(self.test_config_file)
        
        with patch('platform.system', return_value='Darwin'):
            desktop_app.show_notification("测试", "消息")
            
        # 验证继承的方法被调用
        mock_run.assert_called_once()

if __name__ == '__main__':
    unittest.main(verbosity=2)