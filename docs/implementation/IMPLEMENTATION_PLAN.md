# 桌面应用具体实现方案

## 📋 实施概览

本文档提供详细的实施步骤和代码，开发人员可以直接按照本文档进行开发。

**目标**: 1-2周内完成4个核心功能实现
**代码量**: 单文件 ~500行
**依赖**: pystray, pillow (可选)

---

## 📂 项目文件结构

### 新增文件
```
ollama-qwen-coder-rag-lib/
├── desktop_app.py              # 新增：桌面应用主文件
├── config/
│   └── app_config.json          # 新增：应用配置文件
├── assets/
│   └── icon.png                 # 新增：应用图标 (32x32)
├── logs/                       # 新增：日志目录（自动创建）
│   ├── app.log                 # 应用日志
│   └── status.log              # 状态日志
└── ... (现有文件保持不变)
```

### 文件说明
- `desktop_app.py`: 所有桌面功能的单文件实现
- `config/app_config.json`: 应用配置文件
- `assets/icon.png`: 32x32 PNG图标文件
- `logs/`: 自动创建的日志目录

---

## 🔧 开发环境准备

### 1. 安装依赖
```bash
# 桌面功能依赖（可选，不影响CLI功能）
pip install pystray pillow requests

# 验证安装
python -c "import pystray, PIL; print('桌面依赖安装成功')"
```

### 2. 创建目录结构
```bash
# 创建必要目录
mkdir -p config assets logs

# 验证目录结构
ls -la config/ assets/ logs/
```

### 3. 创建配置文件
```bash
# 创建默认配置文件
cat > config/app_config.json << 'EOF'
{
  "autostart": false,
  "warm_up_on_startup": true,
  "warm_up_models": [
    "qwen2.5-coder:7b",
    "nomic-embed-text:latest"
  ],
  "ollama_base_url": "http://localhost:11434",
  "check_interval": 300
}
EOF
```

---

## 💻 核心代码实现

### desktop_app.py 完整实现

将以下代码保存为 `desktop_app.py`:

```python
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
CONFIG_FILE = Path("config/app_config.json")
LOG_FILE = Path("logs/app.log")
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
    
    def __init__(self):
        self.config = self.load_config()
        
    def load_config(self) -> dict:
        """加载配置文件"""
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                print(f"配置文件加载失败，使用默认配置: {e}")
        return DEFAULT_CONFIG.copy()
        
    def save_config(self) -> bool:
        """保存配置文件"""
        try:
            CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
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
                
                # 发送预热请求
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
    
    def __init__(self, ollama_url: str, logger: logging.Logger):
        self.ollama_url = ollama_url
        self.logger = logger
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
        STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)
        
        # 追加状态记录
        with open(STATUS_FILE, 'a', encoding='utf-8') as f:
            f.write(json.dumps(status, ensure_ascii=False) + "\n")
            
        # 只保留最近100条记录
        try:
            with open(STATUS_FILE, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            if len(lines) > 100:
                with open(STATUS_FILE, 'w', encoding='utf-8') as f:
                    f.writelines(lines[-100:])
        except Exception:
            pass

# ==================== 系统托盘应用 ====================
class TrayApp:
    """系统托盘应用"""
    
    def __init__(self, config: AppConfig, logger: logging.Logger):
        self.config = config
        self.logger = logger
        self.icon = None
        self.running = False
        
    def create_icon(self, status: str = "normal"):
        """创建托盘图标"""
        if not DESKTOP_AVAILABLE:
            return None
            
        # 创建 32x32 的简单图标
        image = Image.new('RGB', (32, 32), color=(0, 120, 215))
        draw = ImageDraw.Draw(image)
        
        # 根据状态改变颜色
        if status == "normal":
            color = (0, 200, 83)  # 绿色
        elif status == "error":
            color = (244, 67, 54)  # 红色
        else:
            color = (0, 120, 215)  # 蓝色
            
        # 绘制圆形背景
        draw.ellipse([4, 4, 28, 28], fill=color)
        
        # 绘制文字 "R"
        try:
            from PIL import ImageFont
            font = ImageFont.load_default()
            draw.text((10, 10), "R", fill=(255, 255, 255), font=font)
        except:
            draw.text((10, 10), "R", fill=(255, 255, 255))
        
        return image
        
    def open_terminal(self):
        """打开系统终端"""
        self.logger.info("打开终端")
        import platform
        system = platform.system()
        
        try:
            if system == "Darwin":  # macOS
                subprocess.run(["open", "-a", "Terminal"])
            elif system == "Windows":
                subprocess.run(["cmd", "/c", "start"])
            else:  # Linux
                subprocess.run(["gnome-terminal"])
        except Exception as e:
            self.logger.error(f"打开终端失败: {e}")
            
    def show_status(self):
        """显示系统状态"""
        self.logger.info("显示状态")
        try:
            if not STATUS_FILE.exists():
                print("暂无状态记录")
                return
                
            with open(STATUS_FILE, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            if lines:
                last_status = json.loads(lines[-1])
                print(f"\n=== 系统状态 ({last_status['timestamp']}) ===")
                print(f"Ollama服务: {'✅ 正常' if last_status['ollama_service'] else '❌ 异常'}")
                print(f"已加载模型: {', '.join(last_status['models_loaded']) or '无'}")
            else:
                print("暂无状态记录")
                
        except Exception as e:
            print(f"读取状态失败: {e}")
            
    def restart_services(self):
        """重启服务（占位符）"""
        self.logger.info("重启服务")
        print("重启服务功能待实现")
        # TODO: 根据需要实现服务重启逻辑
        
    def quit_app(self):
        """退出应用"""
        self.logger.info("退出应用")
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
            pystray.MenuItem("打开终端", self.open_terminal),
            pystray.MenuItem("检查状态", self.show_status),
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
class DesktopApp:
    """桌面应用主控制器"""
    
    def __init__(self):
        self.setup_logging()
        self.config = AppConfig()
        self.logger = logging.getLogger(__name__)
        
    def setup_logging(self):
        """设置日志系统"""
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(LOG_FILE, encoding='utf-8'),
                logging.StreamHandler()
            ]
        )
        
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
        
        # 启动托盘应用
        tray = TrayApp(self.config, self.logger)
        
        try:
            tray.run()
        except KeyboardInterrupt:
            self.logger.info("应用退出")
            
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
        
    def enable_autostart(self):
        """启用开机自启动"""
        self.config.set("autostart", True)
        if self.config.save_config():
            self.install_autostart()
            print("✅ 自启动已启用")
        else:
            print("❌ 配置保存失败")
            
    def disable_autostart(self):
        """禁用开机自启动"""
        self.config.set("autostart", False)
        if self.config.save_config():
            self.uninstall_autostart()
            print("✅ 自启动已禁用")
        else:
            print("❌ 配置保存失败")
            
    def install_autostart(self):
        """安装自启动（跨平台）"""
        import platform
        system = platform.system()
        script_path = Path(__file__).absolute()
        
        if system == "Darwin":  # macOS
            self._install_macos_autostart(script_path)
        elif system == "Windows":
            self._install_windows_autostart(script_path)
        else:  # Linux
            self._install_linux_autostart(script_path)
            
    def _install_macos_autostart(self, script_path):
        """macOS 自启动安装"""
        try:
            import plistlib
            
            plist_path = Path.home() / "Library/LaunchAgents/com.ragassistant.plist"
            plist_content = {
                "Label": "com.ragassistant",
                "ProgramArguments": [str(script_path), "--tray"],
                "RunAtLoad": True,
                "KeepAlive": False
            }
            
            plist_path.parent.mkdir(parents=True, exist_ok=True)
            with open(plist_path, 'wb') as f:
                plistlib.dump(plist_content, f)
                
            subprocess.run(["launchctl", "load", str(plist_path)], check=True)
            self.logger.info(f"macOS自启动已安装: {plist_path}")
            
        except ImportError:
            self.logger.error("plistlib 未安装，无法安装 macOS 自启动")
        except Exception as e:
            self.logger.error(f"macOS自启动安装失败: {e}")
            
    def _install_windows_autostart(self, script_path):
        """Windows 自启动安装"""
        try:
            import winreg
            
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Run",
                0, winreg.KEY_SET_VALUE
            )
            winreg.SetValueEx(key, "RAGAssistant", 0, winreg.REG_SZ, str(script_path))
            winreg.CloseKey(key)
            
            self.logger.info("Windows自启动已安装")
            
        except ImportError:
            self.logger.error("winreg 模块不可用")
        except Exception as e:
            self.logger.error(f"Windows自启动安装失败: {e}")
            
    def _install_linux_autostart(self, script_path):
        """Linux 自启动安装"""
        try:
            desktop_file = Path.home() / ".config/autostart/ragassistant.desktop"
            desktop_file.parent.mkdir(parents=True, exist_ok=True)
            
            content = f"""[Desktop Entry]
Type=Application
Name=RAG Assistant
Exec={script_path} --tray
Terminal=false
Categories=Utility;
"""
            with open(desktop_file, 'w') as f:
                f.write(content)
                
            self.logger.info(f"Linux自启动已安装: {desktop_file}")
            
        except Exception as e:
            self.logger.error(f"Linux自启动安装失败: {e}")
            
    def uninstall_autostart(self):
        """卸载自启动（跨平台）"""
        import platform
        system = platform.system()
        
        if system == "Darwin":
            self._uninstall_macos_autostart()
        elif system == "Windows":
            self._uninstall_windows_autostart()
        else:
            self._uninstall_linux_autostart()
            
    def _uninstall_macos_autostart(self):
        """macOS 自启动卸载"""
        try:
            plist_path = Path.home() / "Library/LaunchAgents/com.ragassistant.plist"
            subprocess.run(["launchctl", "unload", str(plist_path)], check=False)
            
            if plist_path.exists():
                plist_path.unlink()
                
            self.logger.info("macOS自启动已卸载")
            
        except Exception as e:
            self.logger.error(f"macOS自启动卸载失败: {e}")
            
    def _uninstall_windows_autostart(self):
        """Windows 自启动卸载"""
        try:
            import winreg
            
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Run",
                0, winreg.KEY_SET_VALUE
            )
            try:
                winreg.DeleteValue(key, "RAGAssistant")
            except FileNotFoundError:
                pass
            winreg.CloseKey(key)
            
            self.logger.info("Windows自启动已卸载")
            
        except Exception as e:
            self.logger.error(f"Windows自启动卸载失败: {e}")
            
    def _uninstall_linux_autostart(self):
        """Linux 自启动卸载"""
        try:
            desktop_file = Path.home() / ".config/autostart/ragassistant.desktop"
            
            if desktop_file.exists():
                desktop_file.unlink()
                
            self.logger.info("Linux自启动已卸载")
            
        except Exception as e:
            self.logger.error(f"Linux自启动卸载失败: {e}")

# ==================== 命令行接口 ====================
def main():
    """命令行入口"""
    parser = argparse.ArgumentParser(
        description='RAG Assistant 桌面应用',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python desktop_app.py --tray           # 运行系统托盘应用
  python desktop_app.py --warm-up        # 手动预热模型
  python desktop_app.py --status         # 查看系统状态
  python desktop_app.py --enable-autostart   # 启用开机自启动
  python desktop_app.py --disable-autostart  # 禁用开机自启动
        """
    )
    
    parser.add_argument('--tray', action='store_true', help='运行系统托盘应用')
    parser.add_argument('--warm-up', action='store_true', help='手动预热模型')
    parser.add_argument('--status', action='store_true', help='查看系统状态')
    parser.add_argument('--enable-autostart', action='store_true', help='启用开机自启动')
    parser.add_argument('--disable-autostart', action='store_true', help='禁用开机自启动')
    
    args = parser.parse_args()
    
    app = DesktopApp()
    
    # 执行对应功能
    if args.tray:
        app.run_desktop()
    elif args.warm_up:
        app.warm_up_models()
    elif args.status:
        app.show_status()
    elif args.enable_autostart:
        app.enable_autostart()
    elif args.disable_autostart:
        app.disable_autostart()
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
```

---

## 📝 配置文件

### config/app_config.json
```json
{
  "autostart": false,
  "warm_up_on_startup": true,
  "warm_up_models": [
    "qwen2.5-coder:7b",
    "nomic-embed-text:latest"
  ],
  "ollama_base_url": "http://localhost:11434",
  "check_interval": 300
}
```

### 配置项说明
- `autostart`: 是否启用开机自启动
- `warm_up_on_startup`: 启动时是否预热模型
- `warm_up_models`: 需要预热的模型列表
- `ollama_base_url`: Ollama 服务地址
- `check_interval`: 状态检查间隔（秒）

---

## 🎨 图标文件

### 创建简单图标
```python
# 使用 Python 创建简单图标
from PIL import Image, ImageDraw

# 创建 32x32 图标
image = Image.new('RGB', (32, 32), color=(0, 120, 215))
draw = ImageDraw.Draw(image)
draw.ellipse([4, 4, 28, 28], fill=(0, 200, 83))
draw.text((10, 10), "R", fill=(255, 255, 255))

# 保存为 PNG
image.save("assets/icon.png")
```

或者使用任何图像编辑工具创建 32x32 的 PNG 图标。

---

## 🧪 测试步骤

### 1. 基础功能测试
```bash
# 测试配置加载
python desktop_app.py --status

# 测试状态检查
python desktop_app.py --status
```

### 2. 模型预热测试
```bash
# 确保 Ollama 服务运行
ollama list

# 手动预热模型
python desktop_app.py --warm-up

# 检查日志
cat logs/app.log
```

### 3. 自启动测试
```bash
# 启用自启动
python desktop_app.py --enable-autostart

# 验证配置
cat config/app_config.json

# 禁用自启动
python desktop_app.py --disable-autostart
```

### 4. 系统托盘测试
```bash
# 运行托盘应用
python desktop_app.py --tray
```

**测试要点**:
- 托盘图标是否显示
- 右键菜单是否正常
- 各菜单项是否工作
- 状态指示颜色是否正确

---

## 📊 开发检查清单

### Phase 1: 基础框架 (Day 1-2)
- [ ] 创建 desktop_app.py 文件
- [ ] 实现 AppConfig 类
- [ ] 实现日志系统
- [ ] 创建配置文件
- [ ] 基础功能测试

### Phase 2: 模型预热 (Day 3-4)
- [ ] 实现 OllamaWarmer 类
- [ ] 实现单模型预热
- [ ] 实现批量预热
- [ ] 集成到启动流程
- [ ] 预热功能测试

### Phase 3: 状态监控 (Day 5)
- [ ] 实现 StatusMonitor 类
- [ ] 实现状态检查
- [ ] 实现日志记录
- [ ] 实现后台监控
- [ ] 监控功能测试

### Phase 4: 系统托盘 (Day 6-7)
- [ ] 实现 TrayApp 类
- [ ] 实现图标创建
- [ ] 实现菜单功能
- [ ] 跨平台兼容性测试
- [ ] 托盘功能测试

### Phase 5: 自启动 (Day 8-9)
- [ ] 实现 macOS 自启动
- [ ] 实现 Windows 自启动
- [ ] 实现 Linux 自启动
- [ ] 跨平台测试
- [ ] 自启动功能测试

### Phase 6: 集成和优化 (Day 10-14)
- [ ] 功能集成测试
- [ ] 错误处理完善
- [ ] 性能优化
- [ ] 文档完善
- [ ] 最终测试

---

## 🚀 部署步骤

### 开发环境
```bash
# 1. 安装依赖
pip install pystray pillow requests

# 2. 创建目录结构
mkdir -p config assets logs

# 3. 创建配置文件
cat > config/app_config.json << 'EOF'
{
  "autostart": false,
  "warm_up_on_startup": true,
  "warm_up_models": ["qwen2.5-coder:7b", "nomic-embed-text:latest"],
  "ollama_base_url": "http://localhost:11434",
  "check_interval": 300
}
EOF

# 4. 创建图标
# (使用上面的 Python 脚本或图像编辑工具)

# 5. 测试功能
python desktop_app.py --status
python desktop_app.py --warm-up
```

### 生产环境
```bash
# 1. 复制文件到目标位置
cp desktop_app.py /path/to/target/
cp -r config /path/to/target/
cp -r assets /path/to/target/

# 2. 设置可执行权限
chmod +x /path/to/target/desktop_app.py

# 3. 配置自启动（可选）
/path/to/target/desktop_app.py --enable-autostart

# 4. 启动应用
/path/to/target/desktop_app.py --tray
```

---

## 🔍 故障排除

### 常见问题

**1. ImportError: No module named 'pystray'**
```bash
# 解决方案
pip install pystray pillow
```

**2. Ollama 服务不可用**
```bash
# 检查 Ollama 是否运行
ollama list

# 启动 Ollama
ollama serve
```

**3. 配置文件加载失败**
```bash
# 检查配置文件路径
ls -la config/app_config.json

# 重新创建配置文件
cat > config/app_config.json << 'EOF'
{
  "autostart": false,
  "warm_up_on_startup": true,
  "warm_up_models": ["qwen2.5-coder:7b", "nomic-embed-text:latest"],
  "ollama_base_url": "http://localhost:11434",
  "check_interval": 300
}
EOF
```

**4. 自启动安装失败**
```bash
# macOS: 检查权限
ls -la ~/Library/LaunchAgents/

# Windows: 检查注册表
reg query "HKCU\Software\Microsoft\Windows\CurrentVersion\Run"

# Linux: 检查桌面文件
ls -la ~/.config/autostart/
```

**5. 托盘图标不显示**
```bash
# 检查依赖
python -c "import pystray, PIL; print('OK')"

# 检查图标文件
ls -la assets/icon.png
```

---

## 📚 使用文档

### 命令行选项
```bash
# 查看帮助
python desktop_app.py --help

# 运行系统托盘
python desktop_app.py --tray

# 手动预热模型
python desktop_app.py --warm-up

# 查看状态
python desktop_app.py --status

# 启用自启动
python desktop_app.py --enable-autostart

# 禁用自启动
python desktop_app.py --disable-autostart
```

### 配置管理
```bash
# 编辑配置文件
vim config/app_config.json

# 或使用 JSON 编辑器
code config/app_config.json
```

### 日志查看
```bash
# 应用日志
tail -f logs/app.log

# 状态日志
tail -f logs/status.log

# 最近状态
python desktop_app.py --status
```

---

## ✅ 验收标准

### 功能完整性
- [ ] 系统托盘应用正常显示
- [ ] 托盘菜单功能正常
- [ ] 模型预热功能正常
- [ ] 状态监控功能正常
- [ ] 自启动功能正常

### 跨平台兼容性
- [ ] macOS 测试通过
- [ ] Windows 测试通过
- [ ] Linux 测试通过

### 稳定性
- [ ] 长时间运行稳定
- [ ] 错误处理完善
- [ ] 日志记录完整

### 用户体验
- [ ] 启动速度合理 (<10秒)
- [ ] 资源占用合理 (<100MB)
- [ ] 操作简单直观

---

这个实施计划提供了完整的代码实现和详细的开发步骤，开发人员可以直接按照文档进行开发，预计1-2周内完成所有功能。