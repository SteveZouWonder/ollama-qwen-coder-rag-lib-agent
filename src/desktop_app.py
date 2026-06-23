#!/usr/bin/env python3
"""
RAG Assistant 桌面应用 - 简化版
功能：系统托盘 + 自启动 + 模型预热 + 状态监控
开发周期：1-2周
代码量：~500行
"""
import os
import sys
import json
import time
import atexit
import signal
import logging
import threading
import subprocess
import requests
from pathlib import Path
from typing import Optional
import argparse

# ==================== 依赖检查 ====================
try:
    import pystray
    from PIL import Image, ImageDraw
    DESKTOP_AVAILABLE = True
except ImportError:
    DESKTOP_AVAILABLE = False



# ==================== 配置 ====================
CONFIG_FILE = Path("../config/app_config.json")
LOG_FILE = Path("../logs/app.log")
STATUS_FILE = Path("logs/status.log")

DEFAULT_CONFIG = {
    "autostart": False,
    "warm_up_on_startup": True,
    "warm_up_models": [
        "qwen2.5-coder:7b",
        "nomic-embed-text:latest"
    ],
    "ollama_base_url": "http://localhost:11434",
    "check_interval": 300  # 5分钟
}

# ==================== 配置管理 ====================
class AppConfig:
    """配置管理类"""
    
    def __init__(self, config_file: Optional[Path] = None):
        self.config_file = config_file or CONFIG_FILE
        self.config = self.load_config()
        
    def load_config(self) -> dict:
        """加载配置文件"""
        if self.config_file.exists():
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                print(f"配置文件加载失败，使用默认配置: {e}")
        return DEFAULT_CONFIG.copy()
        
    def save_config(self) -> bool:
        """保存配置文件"""
        try:
            self.config_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"配置文件保存失败: {e}")
            return False
            
    def get(self, key, default=None):
        """获取配置项"""
        return self.config.get(key, default)
        
    def set(self, key, value):
        """设置配置项"""
        self.config[key] = value
        
    def reload(self):
        """重新加载配置"""
        self.config = self.load_config()

# ==================== 日志管理 ====================
class LogManager:
    """日志管理类"""
    
    def __init__(self, log_file: Optional[Path] = None):
        self.log_file = log_file or LOG_FILE
        self.logger = None
        
    def setup_logging(self, level=logging.INFO):
        """设置日志系统"""
        self.log_file.parent.mkdir(parents=True, exist_ok=True)
        
        logging.basicConfig(
            level=level,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(self.log_file, encoding='utf-8'),
                logging.StreamHandler()
            ]
        )
        
        self.logger = logging.getLogger(__name__)
        return self.logger
        
    def get_logger(self, name: str = None) -> logging.Logger:
        """获取日志记录器"""
        if name:
            return logging.getLogger(name)
        return self.logger or logging.getLogger(__name__)

# ==================== 模型预热器 ====================
class OllamaWarmer:
    """Ollama 模型预热器"""
    
    def __init__(self, base_url: str, logger: logging.Logger):
        self.base_url = base_url
        self.logger = logger
        
    def warm_up(self, models: list) -> dict:
        """预热指定的模型列表"""
        results = {}
        self.logger.info(f"开始预热 {len(models)} 个模型...")
        
        for model in models:
            try:
                self.logger.info(f"预热模型: {model}")
                start_time = time.time()
                
                # 根据模型类型选择预热方法
                if "embed" in model.lower():
                    # 嵌入模型使用 embed 端点
                    response = requests.post(
                        f"{self.base_url}/api/embed",
                        json={
                            "model": model,
                            "input": "test text for warmup"
                        },
                        timeout=60
                    )
                else:
                    # 文本生成模型使用 generate 端点
                    response = requests.post(
                        f"{self.base_url}/api/generate",
                        json={
                            "model": model,
                            "prompt": "hi",
                            "stream": False,
                            "options": {"num_predict": 1}
                        },
                        timeout=60
                    )
                
                load_time = time.time() - start_time
                
                if response.status_code == 200:
                    self.logger.info(f"✅ {model} 预热成功 ({load_time:.2f}s)")
                    results[model] = {"success": True, "time": load_time}
                else:
                    self.logger.warning(f"⚠️ {model} 预热失败 (HTTP {response.status_code})")
                    results[model] = {"success": False, "error": f"HTTP {response.status_code}"}
                    
            except requests.exceptions.Timeout:
                self.logger.error(f"❌ {model} 预热超时")
                results[model] = {"success": False, "error": "timeout"}
            except Exception as e:
                self.logger.error(f"❌ {model} 预热错误: {e}")
                results[model] = {"success": False, "error": str(e)}
                
        return results
        
    def check_service(self) -> bool:
        """检查 Ollama 服务是否可用"""
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=5)
            return response.status_code == 200
        except Exception:
            return False

# ==================== 状态监控器 ====================
class StatusMonitor:
    """状态监控器"""
    
    def __init__(self, ollama_url: str, logger: logging.Logger, status_file: Optional[Path] = None):
        self.ollama_url = ollama_url
        self.logger = logger
        self.status_file = status_file or STATUS_FILE
        self.running = False
        
    def check_status(self) -> dict:
        """检查系统状态"""
        status = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "ollama_service": False,
            "models_loaded": []
        }
        
        # 检查 Ollama 服务
        try:
            response = requests.get(f"{self.ollama_url}/api/tags", timeout=5)
            status["ollama_service"] = response.status_code == 200
            
            if status["ollama_service"]:
                data = response.json()
                status["models_loaded"] = [m["name"] for m in data.get("models", [])]
                
        except Exception as e:
            self.logger.error(f"状态检查失败: {e}")
            
        return status
        
    def start_monitoring(self, interval: int = 300):
        """开始状态监控（后台线程）"""
        self.running = True
        
        while self.running:
            status = self.check_status()
            self.log_status(status)
            time.sleep(interval)
            
    def stop_monitoring(self):
        """停止状态监控"""
        self.running = False
        
    def log_status(self, status: dict):
        """记录状态到日志文件"""
        self.status_file.parent.mkdir(parents=True, exist_ok=True)
        
        # 追加状态记录
        with open(self.status_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps(status, ensure_ascii=False) + "\n")
            
        # 只保留最近100条记录
        try:
            with open(self.status_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            if len(lines) > 100:
                with open(self.status_file, 'w', encoding='utf-8') as f:
                    f.writelines(lines[-100:])
        except Exception:
            pass

# ==================== 应用基类 ====================
class BaseApp:
    """应用基类，提供公共功能"""
    
    # 用于精确标识本程序启动的 CLI 进程/窗口的标记前缀
    CLI_SESSION_TAG_PREFIX = "RAG_CLI_SESSION"

    def __init__(self, config: AppConfig, logger: logging.Logger):
        self.config = config
        self.logger = logger
        self.status_file = STATUS_FILE
        # 跟踪打开的CLI会话（存储会话标记/标题，用于精确关闭）
        self.cli_sessions = []  # 每项: {"id", "start_time", "script", "tag", "title"}
    
    def show_notification(self, title: str, message: str):
        """显示系统通知"""
        import platform
        system = platform.system()
        
        try:
            if system == "Darwin":  # macOS
                subprocess.run([
                    "osascript", "-e",
                    f'display notification "{title}" with message "{message}"'
                ], stderr=subprocess.DEVNULL)
            elif system == "Windows":
                try:
                    from win10toast import ToastNotifier
                    toaster = ToastNotifier()
                    toaster.show_notification(title, message)
                except ImportError:
                    # Windows通知库未安装，跳过
                    pass
            # Linux的通知需要额外的依赖，暂时跳过
        except Exception as e:
            self.logger.warning(f"显示通知失败: {e}")
    
    def show_popup(self, title: str, message: str, duration: int = 2000):
        """显示弹窗提示"""
        import platform
        system = platform.system()
        
        try:
            if system == "Darwin":  # macOS
                applescript = f'''
                tell application "System Events"
                    display dialog "{message}" buttons {{"OK"}} default button "OK" with title "{title}" with icon note
                end tell
                '''
                subprocess.run(["osascript", "-e", applescript], 
                             stderr=subprocess.DEVNULL, timeout=duration//1000 + 2)
                
            elif system == "Windows":
                import ctypes
                MessageBox = ctypes.windll.user32.MessageBoxW
                MessageBox(None, message, title, 0)
                
            elif system == "Linux":
                # 尝试使用zenity（如果可用）
                try:
                    subprocess.run([
                        "zenity", "--info",
                        f"--text={message}",
                        f"--title={title}",
                        f"--timeout={duration//1000}"
                    ], stderr=subprocess.DEVNULL, timeout=duration//1000 + 2)
                except FileNotFoundError:
                    # zenity不可用，使用tkinter作为后备
                    try:
                        import tkinter as tk
                        from tkinter import messagebox
                        root = tk.Tk()
                        root.withdraw()
                        root.after(duration, root.destroy)
                        messagebox.showinfo(title, message)
                    except ImportError:
                        # tkinter也不可用，跳过
                        pass
        except Exception as e:
            self.logger.warning(f"显示弹窗失败: {e}")
    
    def open_cli_interface(self):
        """打开CLI交互界面（后台进程）"""
        self.logger.info("启动CLI界面")
        
        # TrayApp 版本才有的功能
        if hasattr(self, 'set_progress_state'):
            self.set_progress_state()
        self.show_notification("CLI界面", "正在启动交互界面...")
        
        import platform
        import sys
        import time
        
        try:
            script_path = sys.executable
            query_script = Path(__file__).parent / "query_interface.py"
            
            # 生成本次会话的唯一标记：用于在退出时精确定位并关闭对应的进程/窗口，
            # 同时避免误杀用户手动启动的同名 CLI。
            session_id = int(time.time() * 1000)
            session_tag = f"{self.CLI_SESSION_TAG_PREFIX}={session_id}"
            window_title = f"RAG CLI [{session_id}]"
            self.cli_sessions.append({
                "id": session_id,
                "start_time": time.time(),
                "script": str(query_script),
                "tag": session_tag,
                "title": window_title,
            })
            self.logger.info(f"CLI会话已记录，ID: {session_id}, 当前会话数: {len(self.cli_sessions)}")
            
            if platform.system() == "Darwin":  # macOS
                # 通过环境变量注入唯一标记（pgrep 无法匹配 env，但 ps -E 可以；
                # 这里主要靠窗口自定义标题来精确定位并关闭整个 Terminal 窗口）。
                # do script 内：导出标记 -> 设置窗口标题 -> 运行 CLI -> 结束后自动关闭窗口
                inner_cmd = (
                    f"export {session_tag}; "
                    f"cd '{Path.cwd()}' && "
                    f"'{script_path}' '{query_script}'; "
                    f"exit"
                )
                # 转义双引号，供 AppleScript 字符串使用
                inner_cmd_escaped = inner_cmd.replace('\\', '\\\\').replace('"', '\\"')
                applescript = f'''
                tell application "Terminal"
                    set newTab to do script "{inner_cmd_escaped}"
                    set custom title of newTab to "{window_title}"
                    activate
                end tell
                '''
                subprocess.Popen([
                    "osascript", "-e", applescript
                ], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                
            elif platform.system() == "Windows":
                # 在 Windows 上启动 cmd，用 start 的第一个参数设置窗口标题（唯一标记），
                # 退出时按窗口标题精确 taskkill 整个 cmd 窗口。
                subprocess.Popen([
                    "cmd", "/c",
                    f'start "{window_title}" /max cmd /k '
                    f'"set {session_tag}&& cd /d {Path.cwd()} && {script_path} {query_script}"'
                ], shell=True)
                
            else:  # Linux
                # 通过环境变量注入唯一标记，退出时用 pkill -f 按标记精确匹配，
                # 关闭整个 bash（连带 gnome-terminal 子窗口随之关闭）。
                bash_cmd = (
                    f"export {session_tag}; "
                    f"cd {Path.cwd()} && {script_path} {query_script}; exec bash"
                )
                try:
                    subprocess.Popen([
                        "gnome-terminal", "--",
                        "bash", "-c", bash_cmd
                    ], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    
                    # 尝试置顶（需要 wmctrl）
                    subprocess.run([
                        "wmctrl", "-a", "Terminal"
                    ], stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
                except FileNotFoundError:
                    # wmctrl 不可用，正常启动
                    subprocess.Popen([
                        "gnome-terminal", "--",
                        "bash", "-c", bash_cmd
                    ], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                
            self.logger.info("CLI界面已启动")
            
            if hasattr(self, 'set_success_state'):
                self.set_success_state()
            self.show_notification("CLI界面", "✅ 交互界面已在新终端中打开")
            self.show_popup("CLI界面", "✅ 交互界面已在新终端中打开", duration=1500)
            return True
        except Exception as e:
            self.logger.error(f"启动CLI界面失败: {e}")
            
            # 如果启动失败，移除会话记录
            if self.cli_sessions:
                self.cli_sessions.pop()
            
            if hasattr(self, 'set_error_state'):
                self.set_error_state()
            self.show_notification("启动失败", f"❌ CLI界面启动失败: {e}")
            self.show_popup("启动失败", f"❌ CLI界面启动失败: {e}", duration=2000)
            return False

# ==================== 系统托盘应用 ====================
class TrayApp(BaseApp):
    """系统托盘应用"""
    
    def __init__(self, config: AppConfig, logger: logging.Logger):
        super().__init__(config, logger)
        self.icon = None
        self.running = False
        
        # 图标状态颜色定义
        self.COLOR_NORMAL = (0, 120, 215)    # 蓝色
        self.COLOR_PROGRESS = (255, 152, 0)  # 橙色
        self.COLOR_SUCCESS = (76, 175, 80)   # 绿色
        self.COLOR_ERROR = (244, 67, 54)    # 红色
        
        # 图标恢复定时器
        self.icon_restore_timer = None
        
    def update_icon(self, status: str = "normal"):
        """更新托盘图标"""
        if not self.icon:
            return
            
        new_image = self.create_icon(status)
        self.icon.icon = new_image
        self.logger.info(f"图标状态更新为: {status}")
        
        # 如果不是正常状态，设置定时器恢复
        if status != "normal" and self.icon_restore_timer is None:
            self.icon_restore_timer = threading.Timer(3.0, self.restore_normal_icon)
            self.icon_restore_timer.daemon = True
            self.icon_restore_timer.start()
    
    def restore_normal_icon(self):
        """恢复到正常图标状态"""
        self.icon_restore_timer = None
        self.update_icon("normal")
    
    def set_progress_state(self):
        """设置为进行中状态"""
        self.update_icon("progress")
        
    def set_success_state(self):
        """设置为成功状态"""
        self.update_icon("success")
        
    def set_error_state(self):
        """设置为错误状态"""
        self.update_icon("error")
        
    def create_icon(self, status: str = "normal"):
        """创建托盘图标"""
        if not DESKTOP_AVAILABLE:
            return None
            
        # 创建 48x48 的图标（更高分辨率）
        image = Image.new('RGBA', (48, 48), (0, 0, 0, 0))  # 透明背景
        draw = ImageDraw.Draw(image)
        
        # 根据状态改变颜色
        if status == "normal":
            primary_color = self.COLOR_NORMAL
            secondary_color = (0, 80, 180)
        elif status == "progress":
            primary_color = self.COLOR_PROGRESS
            secondary_color = (230, 120, 0)
        elif status == "success":
            primary_color = self.COLOR_SUCCESS
            secondary_color = (50, 140, 60)
        elif status == "error":
            primary_color = self.COLOR_ERROR
            secondary_color = (200, 40, 30)
        else:
            primary_color = self.COLOR_NORMAL
            secondary_color = (0, 80, 180)
        
        # 绘制圆角矩形背景
        corner_radius = 8
        draw.rounded_rectangle(
            [2, 2, 46, 46],
            radius=corner_radius,
            fill=primary_color + (255,),  # 添加透明度
            outline=secondary_color + (255,),
            width=2
        )
        
        # 绘制文档图标（代表检索）
        doc_x, doc_y = 8, 8
        doc_w, doc_h = 14, 18
        draw.rectangle([doc_x, doc_y, doc_x + doc_w, doc_y + doc_h],
                      fill=(255, 255, 255, 200), outline=secondary_color + (255,))
        # 文档折角
        draw.polygon([
            (doc_x + doc_w - 4, doc_y),
            (doc_x + doc_w, doc_y + 4),
            (doc_x + doc_w, doc_y)
        ], fill=secondary_color + (255,))
        # 文档线条
        draw.line([doc_x + 3, doc_y + 5, doc_x + doc_w - 3, doc_y + 5],
                 fill=secondary_color + (200,), width=1)
        draw.line([doc_x + 3, doc_y + 9, doc_x + doc_w - 3, doc_y + 9],
                 fill=secondary_color + (200,), width=1)
        draw.line([doc_x + 3, doc_y + 13, doc_x + doc_w - 5, doc_y + 13],
                 fill=secondary_color + (200,), width=1)
        
        # 绘制AI芯片图标（代表生成）
        chip_x, chip_y = 26, 12
        chip_w, chip_h = 14, 14
        # 芯片主体
        draw.rounded_rectangle(
            [chip_x, chip_y, chip_x + chip_w, chip_y + chip_h],
            radius=2,
            fill=(255, 255, 255, 200),
            outline=secondary_color + (255,),
            width=1
        )
        # 芯片引脚
        pin_length = 3
        # 左侧引脚
        for i in range(3):
            py = chip_y + 3 + i * 4
            draw.line([chip_x - pin_length, py, chip_x, py],
                     fill=secondary_color + (255,), width=1)
        # 右侧引脚
        for i in range(3):
            py = chip_y + 3 + i * 4
            draw.line([chip_x + chip_w, py, chip_x + chip_w + pin_length, py],
                     fill=secondary_color + (255,), width=1)
        # 顶部引脚
        for i in range(3):
            px = chip_x + 3 + i * 4
            draw.line([px, chip_y - pin_length, px, chip_y],
                     fill=secondary_color + (255,), width=1)
        # 底部引脚
        for i in range(3):
            px = chip_x + 3 + i * 4
            draw.line([px, chip_y + chip_h, px, chip_y + chip_h + pin_length],
                     fill=secondary_color + (255,), width=1)
        # 芯片中心
        center_x, center_y = chip_x + chip_w // 2, chip_y + chip_h // 2
        draw.ellipse([center_x - 3, center_y - 3, center_x + 3, center_y + 3],
                     fill=secondary_color + (255,))
        
        # 绘制连接线（代表RAG的连接）
        draw.line([doc_x + doc_w, doc_y + doc_h // 2,
                 chip_x, chip_y + chip_h // 2],
                 fill=(255, 255, 255, 150), width=2)
        # 连接点
        draw.ellipse([doc_x + doc_w - 2, doc_y + doc_h // 2 - 2,
                     doc_x + doc_w + 2, doc_y + doc_h // 2 + 2],
                     fill=(255, 255, 255, 255))
        draw.ellipse([chip_x - 2, chip_y + chip_h // 2 - 2,
                     chip_x + 2, chip_y + chip_h // 2 + 2],
                     fill=(255, 255, 255, 255))
        
        # 缩放到32x32用于系统托盘
        image = image.resize((32, 32), Image.LANCZOS)
        
        return image
        
    def show_notification(self, title: str, message: str):
        """显示系统通知"""
        import platform
        system = platform.system()
        
        try:
            if system == "Darwin":  # macOS
                subprocess.run([
                    "osascript", "-e",
                    f'display notification "{title}" with message "{message}"'
                ], stderr=subprocess.DEVNULL)
            elif system == "Windows":
                try:
                    from win10toast import ToastNotifier
                    toaster = ToastNotifier()
                    toaster.show_notification(title, message)
                except ImportError:
                    # Windows通知库未安装，跳过
                    pass
            # Linux的通知需要额外的依赖，暂时跳过
        except Exception as e:
            self.logger.warning(f"显示通知失败: {e}")
    
    def show_popup(self, title: str, message: str, duration: int = 2000):
        """显示弹窗提示"""
        import platform
        system = platform.system()
        
        try:
            if system == "Darwin":  # macOS
                applescript = f'''
                tell application "System Events"
                    display dialog "{message}" buttons {{"OK"}} default button "OK" with title "{title}" with icon note
                end tell
                '''
                subprocess.run(["osascript", "-e", applescript], 
                             stderr=subprocess.DEVNULL, timeout=duration//1000 + 2)
                
            elif system == "Windows":
                import ctypes
                MessageBox = ctypes.windll.user32.MessageBoxW
                MessageBox(None, message, title, 0)
                
            elif system == "Linux":
                # 尝试使用zenity（如果可用）
                try:
                    subprocess.run([
                        "zenity", "--info",
                        f"--text={message}",
                        f"--title={title}",
                        f"--timeout={duration//1000}"
                    ], stderr=subprocess.DEVNULL, timeout=duration//1000 + 2)
                except FileNotFoundError:
                    # zenity不可用，使用tkinter作为后备
                    try:
                        import tkinter as tk
                        from tkinter import messagebox
                        root = tk.Tk()
                        root.withdraw()
                        root.after(duration, root.destroy)
                        messagebox.showinfo(title, message)
                    except ImportError:
                        # tkinter也不可用，跳过
                        pass
        except Exception as e:
            self.logger.warning(f"显示弹窗失败: {e}")
    
    def show_status(self):
        """显示系统状态"""
        self.logger.info("显示状态")
        self.set_progress_state()
        self.show_notification("状态检查", "正在检查系统状态...")
        
        try:
            if not self.status_file.exists():
                print("暂无状态记录")
                self.set_error_state()
                self.show_notification("状态检查", "⚠️ 暂无状态记录")
                return
                
            with open(self.status_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            if lines:
                last_status = json.loads(lines[-1])
                status_text = f"Ollama服务: {'✅ 正常' if last_status['ollama_service'] else '❌ 异常'}"
                models_text = f"已加载模型: {', '.join(last_status['models_loaded']) or '无'}"
                
                print(f"\n=== 系统状态 ({last_status['timestamp']}) ===")
                print(status_text)
                print(models_text)
                
                if last_status['ollama_service']:
                    self.set_success_state()
                else:
                    self.set_error_state()
                self.show_notification("系统状态", status_text)
                self.show_popup("系统状态", status_text, duration=1500)
            else:
                print("暂无状态记录")
                self.set_error_state()
                self.show_notification("状态检查", "⚠️ 暂无状态记录")
                self.show_popup("状态检查", "⚠️ 暂无状态记录", duration=1500)
                
        except Exception as e:
            print(f"读取状态失败: {e}")
            self.set_error_state()
            self.show_notification("状态检查失败", f"❌ 读取状态失败: {e}")
            self.show_popup("状态检查失败", f"❌ 读取状态失败: {e}", duration=2000)
            
    def status_file_exists(self) -> bool:
        """检查状态文件是否存在"""
        return self.config.status_file.exists() if hasattr(self.config, 'status_file') else STATUS_FILE.exists()
        
    def restart_services(self):
        """重启服务"""
        self.logger.info("重启服务")
        self.set_progress_state()
        self.show_notification("重启服务", "正在重启服务...")
        self.show_popup("重启服务", "正在重启服务...", duration=1500)
        
        print("重启服务功能待实现")
        self.set_error_state()
        self.show_notification("重启服务", "⚠️ 功能待实现")
        self.show_popup("重启服务", "⚠️ 功能待实现", duration=1500)
        # TODO: 根据需要实现服务重启逻辑
        
    def warm_up_models_from_menu(self):
        """从托盘菜单手动触发模型预热"""
        self.logger.info("从菜单触发模型预热")
        self.set_progress_state()
        self.show_notification("模型预热", "正在预热模型...")
        
        models = self.config.get("warm_up_models", [])
        if not models:
            print("配置中没有需要预热的模型")
            self.set_error_state()
            self.show_notification("模型预热", "⚠️ 配置中没有需要预热的模型")
            return
        
        warmer = OllamaWarmer(
            self.config.get("ollama_base_url", "http://localhost:11434"),
            self.logger
        )
        
        if not warmer.check_service():
            print("Ollama服务不可用，无法预热模型")
            self.set_error_state()
            self.show_notification("预热失败", "❌ Ollama服务不可用")
            return
        
        results = warmer.warm_up(models)
        
        # 统计结果
        success_count = sum(1 for r in results.values() if r.get("success"))
        if success_count == len(models):
            self.set_success_state()
            self.show_notification("预热完成", f"✅ 成功预热 {success_count} 个模型")
            self.show_popup("预热完成", f"✅ 成功预热 {success_count} 个模型", duration=2000)
        else:
            self.set_error_state()
            self.show_notification("预热部分完成", f"⚠️ 成功预热 {success_count}/{len(models)} 个模型")
            self.show_popup("预热部分完成", f"⚠️ 成功预热 {success_count}/{len(models)} 个模型", duration=2000)
    
    def close_all_cli_processes(self):
        """关闭所有打开的CLI进程"""
        if not self.cli_sessions:
            self.logger.info("没有需要关闭的CLI会话")
            return
        
        import platform
        system = platform.system()
        closed_count = 0
        failed_count = 0
        
        self.logger.info(f"开始关闭 {len(self.cli_sessions)} 个CLI会话")
        
        try:
            if system == "Darwin":  # macOS
                closed_count = self._close_cli_macos()
            elif system == "Windows":
                closed_count = self._close_cli_windows()
            elif system == "Linux":
                closed_count = self._close_cli_linux()
            else:
                self.logger.warning(f"不支持的操作系统: {system}")
                
        except Exception as e:
            self.logger.error(f"关闭CLI进程时发生异常: {e}")
        
        # 清空会话记录
        self.cli_sessions.clear()
        self.logger.info(f"关闭完成: 成功 {closed_count}, 失败 {failed_count}")
        
        return closed_count
    
    def _close_cli_macos(self):
        """关闭macOS上的CLI进程及其Terminal窗口

        关键修复：仅杀死 query_interface.py 的 Python 进程并不会关闭 Terminal 窗口，
        因为窗口属于 Terminal.app 而非本程序的子进程。这里改为：
        1) 通过窗口自定义标题精确关闭对应的整个 Terminal 窗口；
        2) 再杀死残留的 Python 进程作为兜底。
        """
        import signal
        import os
        closed_count = 0

        # 1) 按窗口标题关闭整个 Terminal 窗口
        for session in self.cli_sessions:
            title = session.get("title")
            if not title:
                continue
            try:
                applescript = f'''
                tell application "Terminal"
                    repeat with w in windows
                        try
                            if custom title of w is "{title}" then
                                close w saving no
                            end if
                        end try
                    end repeat
                end tell
                '''
                subprocess.run(
                    ["osascript", "-e", applescript],
                    stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL
                )
                self.logger.info(f"macOS: 已请求关闭Terminal窗口 '{title}'")
                closed_count += 1
            except FileNotFoundError:
                self.logger.warning("macOS: osascript命令不可用")
                break
            except Exception as e:
                self.logger.warning(f"macOS: 关闭窗口 '{title}' 失败: {e}")

        # 2) 兜底：杀死仍在运行的 query_interface.py 进程
        try:
            result = subprocess.run(
                ["pgrep", "-f", "query_interface.py"],
                capture_output=True,
                text=True
            )
            if result.returncode == 0 and result.stdout:
                pids = result.stdout.strip().split('\n')
                for pid_str in pids:
                    try:
                        pid = int(pid_str)
                        os.kill(pid, signal.SIGTERM)
                        time.sleep(0.3)
                        try:
                            os.kill(pid, 0)
                            os.kill(pid, signal.SIGKILL)
                            self.logger.info(f"macOS: 进程 {pid} 强制终止")
                        except ProcessLookupError:
                            self.logger.info(f"macOS: 进程 {pid} 已终止")
                    except (ValueError, ProcessLookupError) as e:
                        self.logger.warning(f"macOS: 处理进程失败: {e}")
        except FileNotFoundError:
            self.logger.warning("macOS: pgrep命令不可用")

        return closed_count
    
    def _close_cli_windows(self):
        """关闭Windows上的CLI窗口（整个cmd窗口）

        关键修复：按启动时设置的唯一窗口标题精确关闭整个 cmd 窗口（连带其中的
        python 子进程），而非仅杀 python.exe 进程，避免留下空的 cmd 窗口，也
        避免误杀用户手动启动的同名 CLI。
        """
        closed_count = 0

        for session in self.cli_sessions:
            title = session.get("title")
            if not title:
                continue
            try:
                # 按窗口标题强制关闭整个进程树
                result = subprocess.run(
                    ["taskkill", "/F", "/T", "/FI", f"WINDOWTITLE eq {title}"],
                    capture_output=True,
                    text=True
                )
                if result.returncode == 0:
                    self.logger.info(f"Windows: 已关闭窗口 '{title}'")
                    closed_count += 1
                else:
                    self.logger.info(f"Windows: 未找到窗口 '{title}'")
            except FileNotFoundError:
                self.logger.warning("Windows: taskkill命令不可用")
                break
            except Exception as e:
                self.logger.warning(f"Windows: 关闭窗口 '{title}' 失败: {e}")

        return closed_count
    
    def _close_cli_linux(self):
        """关闭Linux上的CLI进程及其终端窗口

        关键修复：按启动时注入的唯一会话标记（环境变量名出现在进程环境中，
        pkill -f 会匹配命令行；这里在 bash 命令里 export 了标记，bash 的命令行
        含该标记）精确终止对应的整个 bash 进程，gnome-terminal 子窗口随之关闭，
        避免误杀其它同名 CLI。若无记录的会话，则回退到按脚本名匹配。
        """
        closed_count = 0

        targets = [s.get("tag") for s in self.cli_sessions if s.get("tag")]
        if not targets:
            targets = ["query_interface.py"]

        for pattern in targets:
            try:
                result = subprocess.run(
                    ["pkill", "-f", pattern],
                    stderr=subprocess.DEVNULL,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL
                )
                if result.returncode == 0:
                    self.logger.info(f"Linux: 已终止匹配 '{pattern}' 的进程")
                    closed_count += 1
                else:
                    self.logger.info(f"Linux: 没有找到匹配 '{pattern}' 的进程")
            except FileNotFoundError:
                self.logger.warning("Linux: pkill命令不可用")
                break

        return closed_count

    def quit_app(self):
        """退出应用"""
        self.logger.info("退出应用")
        self.set_progress_state()
        self.show_notification("退出应用", "正在退出 RAG Assistant...")
        self.show_popup("退出应用", "正在退出 RAG Assistant...", duration=1500)
        
        # 关闭所有CLI进程
        self.close_all_cli_processes()
        
        self.running = False
        if self.icon:
            self.icon.stop()
            
    def run(self):
        """运行托盘应用"""
        if not DESKTOP_AVAILABLE:
            self.logger.error("桌面功能不可用，请安装 pystray 和 pillow")
            print("错误: pystray 或 PIL 未安装")
            print("安装命令: pip install pystray pillow")
            return
            
        # 创建菜单
        menu = pystray.Menu(
            pystray.MenuItem("打开CLI界面", self.open_cli_interface),
            pystray.MenuItem("检查状态", self.show_status),
            pystray.MenuItem("模型预热", self.warm_up_models_from_menu),
            pystray.MenuItem("重启服务", self.restart_services),
            pystray.MenuItem("退出", self.quit_app)
        )
        
        # 创建图标
        image = self.create_icon("normal")
        self.icon = pystray.Icon("RAG Assistant", image, menu=menu)
        self.running = True
        
        self.logger.info("系统托盘启动")
        self.icon.run()

# ==================== 主应用控制器 ====================
class DesktopApp(BaseApp):
    """桌面应用主控制器"""
    
    def __init__(self, config_file: Optional[Path] = None):
        self.log_manager = LogManager()
        self.logger = self.log_manager.setup_logging()
        self.config = AppConfig(config_file)
        # 调用父类初始化
        super().__init__(self.config, self.logger)
    
    def show_notification(self, title: str, message: str):
        """显示系统通知"""
        import platform
        system = platform.system()
        
        try:
            if system == "Darwin":  # macOS
                subprocess.run([
                    "osascript", "-e",
                    f'display notification "{title}" with message "{message}"'
                ], stderr=subprocess.DEVNULL)
            elif system == "Windows":
                try:
                    from win10toast import ToastNotifier
                    toaster = ToastNotifier()
                    toaster.show_notification(title, message)
                except ImportError:
                    # Windows通知库未安装，跳过
                    pass
            # Linux的通知需要额外的依赖，暂时跳过
        except Exception as e:
            self.logger.warning(f"显示通知失败: {e}")
    
    def show_popup(self, title: str, message: str, duration: int = 2000):
        """显示弹窗提示"""
        import platform
        system = platform.system()
        
        try:
            if system == "Darwin":  # macOS
                applescript = f'''
                tell application "System Events"
                    display dialog "{message}" buttons {{"OK"}} default button "OK" with title "{title}" with icon note
                end tell
                '''
                subprocess.run(["osascript", "-e", applescript], 
                             stderr=subprocess.DEVNULL, timeout=duration//1000 + 2)
                
            elif system == "Windows":
                import ctypes
                MessageBox = ctypes.windll.user32.MessageBoxW
                MessageBox(None, message, title, 0)
                
            elif system == "Linux":
                # 尝试使用zenity（如果可用）
                try:
                    subprocess.run([
                        "zenity", "--info",
                        f"--text={message}",
                        f"--title={title}",
                        f"--timeout={duration//1000}"
                    ], stderr=subprocess.DEVNULL, timeout=duration//1000 + 2)
                except FileNotFoundError:
                    # zenity不可用，使用tkinter作为后备
                    try:
                        import tkinter as tk
                        from tkinter import messagebox
                        root = tk.Tk()
                        root.withdraw()
                        root.after(duration, root.destroy)
                        messagebox.showinfo(title, message)
                    except ImportError:
                        # tkinter也不可用，跳过
                        pass
        except Exception as e:
            self.logger.warning(f"显示弹窗失败: {e}")
    
        
    def warm_up_models(self):
        """模型预热"""
        if not self.config.get("warm_up_on_startup"):
            self.logger.info("模型预热已禁用")
            return
            
        warmer = OllamaWarmer(
            self.config.get("ollama_base_url", "http://localhost:11434"),
            self.logger
        )
        
        if not warmer.check_service():
            self.logger.error("Ollama服务不可用，跳过模型预热")
            return
            
        models = self.config.get("warm_up_models", [])
        warmer.warm_up(models)
        
    def start_monitoring(self):
        """启动状态监控"""
        interval = self.config.get("check_interval", 300)
        monitor = StatusMonitor(
            self.config.get("ollama_base_url", "http://localhost:11434"),
            self.logger
        )
        
        monitor_thread = threading.Thread(target=monitor.start_monitoring, args=(interval,))
        monitor_thread.daemon = True
        monitor_thread.start()
        
        self.logger.info(f"状态监控已启动 (间隔: {interval}秒)")
        
    def run_desktop(self):
        """运行桌面应用（托盘模式）"""
        self.logger.info("启动桌面应用...")
        
        # 模型预热（后台线程）
        warm_thread = threading.Thread(target=self.warm_up_models)
        warm_thread.daemon = True
        warm_thread.start()
        
        # 启动状态监控
        self.start_monitoring()
        
        # 自动打开CLI界面（后台进程）
        self.open_cli_interface()
        
        # 启动托盘应用
        tray = TrayApp(self.config, self.logger)
        # 共享 CLI 会话记录：CLI 由 DesktopApp 启动并记录在 self.cli_sessions，
        # 而退出清理在 TrayApp.quit_app 中执行，必须让两者引用同一份记录，
        # 否则退出时遍历到空列表导致 macOS/Windows 无法定位并关闭窗口。
        tray.cli_sessions = self.cli_sessions

        # 退出兜底：即使没有走托盘“退出”菜单（如进程被 SIGTERM/SIGINT、
        # 或异常退出），也尽量关闭已打开的 CLI 进程/窗口。
        self._register_exit_handlers(tray)

        try:
            tray.run()
        except KeyboardInterrupt:
            self.logger.info("应用退出")
        finally:
            # 正常退出路径的兜底清理（重复调用是安全的：sessions 已清空则直接返回）
            try:
                tray.close_all_cli_processes()
            except Exception as e:
                self.logger.warning(f"退出清理CLI进程时出错: {e}")

    def _register_exit_handlers(self, tray: "TrayApp"):
        """注册 atexit 与信号处理器，确保各种退出路径都能清理CLI进程。"""
        def _cleanup(*_args):
            try:
                tray.close_all_cli_processes()
            except Exception as e:
                self.logger.warning(f"兜底清理CLI进程失败: {e}")

        atexit.register(_cleanup)

        def _signal_handler(signum, frame):
            self.logger.info(f"收到信号 {signum}，开始清理并退出")
            _cleanup()
            try:
                tray.running = False
                if tray.icon:
                    tray.icon.stop()
            except Exception:
                pass

        for _sig in (signal.SIGTERM, signal.SIGINT):
            try:
                signal.signal(_sig, _signal_handler)
            except (ValueError, OSError):
                # 非主线程或平台不支持时忽略
                pass
            
    def show_status(self):
        """显示当前状态"""
        monitor = StatusMonitor(
            self.config.get("ollama_base_url", "http://localhost:11434"),
            self.logger
        )
        status = monitor.check_status()
        
        print(f"\n=== 系统状态 ({status['timestamp']}) ===")
        print(f"Ollama服务: {'✅ 正常' if status['ollama_service'] else '❌ 异常'}")
        print(f"已加载模型: {', '.join(status['models_loaded']) or '无'}")

# ==================== 命令行接口 ====================
def main():
    """命令行入口"""
    parser = argparse.ArgumentParser(
        description='RAG Assistant 桌面应用 - 主要启动入口',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python desktop_app.py                # 启动桌面应用（默认托盘模式）
  python desktop_app.py --tray          # 运行系统托盘应用
  python desktop_app.py --warm-up       # 手动预热模型
  python desktop_app.py --status        # 查看系统状态
        """
    )
    
    parser.add_argument('--tray', action='store_true', help='运行系统托盘应用')
    parser.add_argument('--warm-up', action='store_true', help='手动预热模型')
    parser.add_argument('--status', action='store_true', help='查看系统状态')
    
    args = parser.parse_args()
    
    app = DesktopApp()
    
    # 执行对应功能
    if args.tray or not any([args.warm_up, args.status]):
        # 默认行为：启动托盘应用
        app.run_desktop()
    elif args.warm_up:
        app.warm_up_models()
    elif args.status:
        app.show_status()

if __name__ == "__main__":
    main()