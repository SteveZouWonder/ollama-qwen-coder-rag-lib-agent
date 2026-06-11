# 简化版本地应用化设计方案

## 🎯 设计目标

基于现有CLI模式，添加最小化的桌面集成功能，开发周期控制在1-2周内完成。

---

## 💡 核心原则

1. **功能优先**: 专注于实用功能，不追求美观界面
2. **最小化改动**: 在现有代码基础上最小化修改
3. **CLI为主**: 保持CLI作为主要交互方式
4. **简单可靠**: 避免复杂依赖，降低维护成本

---

## 🔧 核心功能设计

### 1. 系统托盘应用（最小化版本）

**功能范围**:
- ✅ 托盘图标显示（状态颜色指示）
- ✅ 右键菜单（3-4个简单选项）
- ❌ 复杂的状态窗口
- ❌ 配置界面（使用配置文件）

**菜单选项**:
```
右键菜单:
├── 打开终端
├── 检查状态
├── 重启服务
└── 退出
```

**实现方式**:
- 使用 `pystray` (最简单的托盘库)
- 图标状态：绿色=正常，红色=错误
- 菜单项直接调用系统命令

### 2. 开机自启动（极简版本）

**功能范围**:
- ✅ 跨平台自启动支持
- ✅ 通过配置文件控制
- ❌ 图形界面配置

**实现方式**:
- 配置文件开关：`config/app_config.json` 中 `"autostart": true/false`
- 命令行控制：`python desktop_app.py --enable-autostart` / `--disable-autostart`
- 平台特定脚本：最小化的启动脚本

### 3. 模型预热（后台版本）

**功能范围**:
- ✅ 启动时自动预热
- ✅ 配置文件控制预热哪些模型
- ✅ 日志输出预热进度
- ❌ 图形化进度显示

**实现方式**:
- 在现有代码中添加预热逻辑
- 配置文件：`config/app_config.json` 中 `"warm_up_models": ["model1", "model2"]`
- 后台线程执行，日志输出到文件
- 支持命令行手动预热：`python desktop_app.py --warm-up`

### 4. 状态监控（日志版本）

**功能范围**:
- ✅ 定期健康检查
- ✅ 日志文件记录状态
- ✅ 命令行查看状态
- ❌ 图形化状态显示

**实现方式**:
- 定期检查服务状态（每5分钟）
- 状态日志：`logs/status.log`
- 命令行查看：`python desktop_app.py --status`
- 托盘菜单"检查状态"显示最近状态

---

## 📂 简化的项目结构

```
ollama-qwen-coder-rag-lib/
├── desktop_app.py          # 新增：桌面应用主文件（单文件）
├── config/
│   └── app_config.json      # 新增：应用配置文件
├── installers/              # 新增：简化安装脚本
│   ├── install_autostart.sh    # macOS/Linux 自启动安装
│   └── install_autostart.ps1   # Windows 自启动安装
├── assets/
│   └── icon.png            # 新增：简单的图标文件
└── ... (现有文件保持不变)
```

**设计特点**:
- 单文件桌面应用，避免复杂的项目结构
- 配置文件统一管理
- 最小化的安装脚本

---

## 🚀 实现方案（单文件架构）

### desktop_app.py 完整实现

```python
#!/usr/bin/env python3
"""
RAG Assistant 桌面应用 - 简化版
功能：系统托盘 + 自启动 + 模型预热 + 状态监控
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

# 条件导入桌面应用依赖
try:
    import pystray
    from PIL import Image, ImageDraw
    DESKTOP_AVAILABLE = True
except ImportError:
    DESKTOP_AVAILABLE = False
    print("警告: pystray 或 PIL 未安装，桌面功能将不可用")
    print("安装命令: pip install pystray pillow")

# 配置
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

class AppConfig:
    """配置管理"""
    
    def __init__(self):
        self.config = self.load_config()
        
    def load_config(self) -> dict:
        """加载配置"""
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                print(f"配置文件加载失败，使用默认配置: {e}")
        return DEFAULT_CONFIG.copy()
        
    def save_config(self) -> bool:
        """保存配置"""
        try:
            CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"配置文件保存失败: {e}")
            return False
            
    def get(self, key, default=None):
        return self.config.get(key, default)
        
    def set(self, key, value):
        self.config[key] = value

class OllamaWarmer:
    """Ollama 模型预热器"""
    
    def __init__(self, base_url: str, logger: logging.Logger):
        self.base_url = base_url
        self.logger = logger
        
    def warm_up(self, models: list) -> dict:
        """预热模型"""
        results = {}
        self.logger.info(f"开始预热 {len(models)} 个模型...")
        
        for model in models:
            try:
                self.logger.info(f"预热模型: {model}")
                start_time = time.time()
                
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
        """检查Ollama服务"""
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=5)
            return response.status_code == 200
        except:
            return False

class StatusMonitor:
    """状态监控"""
    
    def __init__(self, ollama_url: str, logger: logging.Logger):
        self.ollama_url = ollama_url
        self.logger = logger
        self.running = False
        
    def check_status(self) -> dict:
        """检查所有状态"""
        status = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "ollama_service": False,
            "models_loaded": []
        }
        
        # 检查Ollama服务
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
        """开始监控"""
        self.running = True
        
        while self.running:
            status = self.check_status()
            self.log_status(status)
            time.sleep(interval)
            
    def stop_monitoring(self):
        """停止监控"""
        self.running = False
        
    def log_status(self, status: dict):
        """记录状态"""
        STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)
        
        with open(STATUS_FILE, 'a', encoding='utf-8') as f:
            f.write(json.dumps(status, ensure_ascii=False) + "\n")
            
        # 只保留最近100条记录
        try:
            with open(STATUS_FILE, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            if len(lines) > 100:
                with open(STATUS_FILE, 'w', encoding='utf-8') as f:
                    f.writelines(lines[-100:])
        except:
            pass

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
            
        # 创建简单的图标
        image = Image.new('RGB', (32, 32), color=(0, 120, 215))
        draw = ImageDraw.Draw(image)
        
        # 根据状态改变颜色
        if status == "normal":
            color = (0, 200, 83)  # 绿色
        elif status == "error":
            color = (244, 67, 54)  # 红色
        else:
            color = (0, 120, 215)  # 蓝色
            
        draw.ellipse([4, 4, 28, 28], fill=color)
        draw.text((10, 10), "R", fill=(255, 255, 255))
        
        return image
        
    def open_terminal(self):
        """打开终端"""
        self.logger.info("打开终端")
        import platform
        system = platform.system()
        
        if system == "Darwin":  # macOS
            subprocess.run(["open", "-a", "Terminal"])
        elif system == "Windows":
            subprocess.run(["cmd", "/c", "start"])
        else:  # Linux
            subprocess.run(["gnome-terminal"])
            
    def show_status(self):
        """显示状态"""
        self.logger.info("显示状态")
        try:
            with open(STATUS_FILE, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            if lines:
                last_status = json.loads(lines[-1])
                print(f"\n=== 系统状态 ({last_status['timestamp']}) ===")
                print(f"Ollama服务: {'✅ 正常' if last_status['ollama_service'] else '❌ 异常'}")
                print(f"已加载模型: {', '.join(last_status['models_loaded'])}")
            else:
                print("暂无状态记录")
        except Exception as e:
            print(f"读取状态失败: {e}")
            
    def restart_services(self):
        """重启服务"""
        self.logger.info("重启服务")
        print("重启服务...")
        # TODO: 实现服务重启逻辑
        print("服务重启完成")
        
    def run(self):
        """运行托盘应用"""
        if not DESKTOP_AVAILABLE:
            self.logger.error("桌面功能不可用，请安装 pystray 和 pillow")
            return
            
        menu = pystray.Menu(
            pystray.MenuItem("打开终端", self.open_terminal),
            pystray.MenuItem("检查状态", self.show_status),
            pystray.MenuItem("重启服务", self.restart_services),
            pystray.MenuItem("退出", self.quit_app)
        )
        
        image = self.create_icon("normal")
        self.icon = pystray.Icon("RAG Assistant", image, menu=menu)
        self.running = True
        
        self.logger.info("系统托盘启动")
        self.icon.run()
        
    def quit_app(self):
        """退出应用"""
        self.logger.info("退出应用")
        self.running = False
        if self.icon:
            self.icon.stop()

class DesktopApp:
    """桌面应用主控制器"""
    
    def __init__(self):
        self.setup_logging()
        self.config = AppConfig()
        self.logger = logging.getLogger(__name__)
        
    def setup_logging(self):
        """设置日志"""
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
        """预热模型"""
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
        """开始状态监控"""
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
        
        # 模型预热
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
        """显示状态"""
        monitor = StatusMonitor(
            self.config.get("ollama_base_url", "http://localhost:11434"),
            self.logger
        )
        status = monitor.check_status()
        
        print(f"\n=== 系统状态 ({status['timestamp']}) ===")
        print(f"Ollama服务: {'✅ 正常' if status['ollama_service'] else '❌ 异常'}")
        print(f"已加载模型: {', '.join(status['models_loaded'])}")
        
    def enable_autostart(self):
        """启用自启动"""
        self.config.set("autostart", True)
        if self.config.save_config():
            self.install_autostart()
            print("自启动已启用")
        else:
            print("配置保存失败")
            
    def disable_autostart(self):
        """禁用自启动"""
        self.config.set("autostart", False)
        if self.config.save_config():
            self.uninstall_autostart()
            print("自启动已禁用")
        else:
            print("配置保存失败")
            
    def install_autostart(self):
        """安装自启动"""
        import platform
        system = platform.system()
        
        script_path = Path(__file__).absolute()
        
        if system == "Darwin":  # macOS
            plist_path = Path.home() / "Library/LaunchAgents/com.ragassistant.plist"
            plist_content = {
                "Label": "com.ragassistant",
                "ProgramArguments": [str(script_path), "--tray"],
                "RunAtLoad": True
            }
            
            try:
                import plistlib
                plist_path.parent.mkdir(parents=True, exist_ok=True)
                with open(plist_path, 'wb') as f:
                    plistlib.dump(plist_content, f)
                subprocess.run(["launchctl", "load", str(plist_path)], check=True)
                self.logger.info(f"自启动已安装: {plist_path}")
            except Exception as e:
                self.logger.error(f"自启动安装失败: {e}")
                
        elif system == "Windows":
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
            except Exception as e:
                self.logger.error(f"Windows自启动安装失败: {e}")
                
        else:  # Linux
            desktop_file = Path.home() / ".config/autostart/ragassistant.desktop"
            desktop_file.parent.mkdir(parents=True, exist_ok=True)
            
            content = f"""[Desktop Entry]
Type=Application
Name=RAG Assistant
Exec={script_path} --tray
Terminal=false
"""
            try:
                with open(desktop_file, 'w') as f:
                    f.write(content)
                self.logger.info(f"Linux自启动已安装: {desktop_file}")
            except Exception as e:
                self.logger.error(f"Linux自启动安装失败: {e}")
                
    def uninstall_autostart(self):
        """卸载自启动"""
        import platform
        system = platform.system()
        
        if system == "Darwin":  # macOS
            plist_path = Path.home() / "Library/LaunchAgents/com.ragassistant.plist"
            try:
                subprocess.run(["launchctl", "unload", str(plist_path)], check=False)
                if plist_path.exists():
                    plist_path.unlink()
                self.logger.info("macOS自启动已卸载")
            except Exception as e:
                self.logger.error(f"macOS自启动卸载失败: {e}")
                
        elif system == "Windows":
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
                
        else:  # Linux
            desktop_file = Path.home() / ".config/autostart/ragassistant.desktop"
            try:
                if desktop_file.exists():
                    desktop_file.unlink()
                self.logger.info("Linux自启动已卸载")
            except Exception as e:
                self.logger.error(f"Linux自启动卸载失败: {e}")

def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='RAG Assistant 桌面应用')
    parser.add_argument('--tray', action='store_true', help='运行系统托盘应用')
    parser.add_argument('--warm-up', action='store_true', help='手动预热模型')
    parser.add_argument('--status', action='store_true', help='查看状态')
    parser.add_argument('--enable-autostart', action='store_true', help='启用自启动')
    parser.add_argument('--disable-autostart', action='store_true', help='禁用自启动')
    
    args = parser.parse_args()
    
    app = DesktopApp()
    
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

## 📋 开发任务清单（简化版）

### Week 1: 核心功能实现

#### Day 1-2: 基础框架
- [ ] 创建 `desktop_app.py` 单文件
- [ ] 实现配置管理类
- [ ] 实现日志系统
- [ ] 基础测试

#### Day 3-4: 模型预热
- [ ] 实现 OllamaWarmer 类
- [ ] 集成到启动流程
- [ ] 测试预热功能

#### Day 5: 状态监控
- [ ] 实现 StatusMonitor 类
- [ ] 实现状态日志
- [ ] 测试监控功能

#### Day 6-7: 系统托盘
- [ ] 实现托盘应用
- [ ] 实现右键菜单
- [ ] 跨平台测试

### Week 2: 自启动和优化

#### Day 8-9: 自启动功能
- [ ] 实现自启动安装/卸载
- [ ] 跨平台测试
- [ ] 文档完善

#### Day 10: 集成测试
- [ ] 功能集成测试
- [ ] 跨平台兼容性测试
- [ ] 性能测试

#### Day 11-12: 文档和发布
- [ ] 编写使用文档
- [ ] 创建安装脚本
- [ ] 准备发布

#### Day 13-14: 缓冲和优化
- [ ] 修复发现的问题
- [ ] 性能优化
- [ ] 最终测试

---

## 🚀 使用示例

### 安装依赖
```bash
pip install pystray pillow requests
```

### 运行托盘应用
```bash
python desktop_app.py --tray
```

### 手动预热模型
```bash
python desktop_app.py --warm-up
```

### 查看状态
```bash
python desktop_app.py --status
```

### 启用自启动
```bash
python desktop_app.py --enable-autostart
```

### 禁用自启动
```bash
python desktop_app.py --disable-autostart
```

### 配置文件 (config/app_config.json)
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

---

## 📊 预期效果

### 功能完整性
- ✅ 系统托盘应用（最小化）
- ✅ 开机自启动（跨平台）
- ✅ 模型预热（后台）
- ✅ 状态监控（日志）

### 开发复杂度
- 代码量: 单文件 ~500行
- 依赖: pystray + pillow (可选)
- 开发周期: 1-2周
- 维护成本: 低

### 用户体验
- 保持CLI简洁性
- 托盘图标提供便捷访问
- 后台自动预热提升体验
- 日志文件提供状态查看

---

## ⚠️ 注意事项

1. **可选依赖**: pystray/pillow 是可选的，不安装也能使用其他功能
2. **配置优先**: 所有功能通过配置文件控制，无需GUI
3. **向后兼容**: 不影响现有CLI功能
4. **简单可靠**: 避免复杂逻辑，优先保证稳定性

---

这个简化方案去掉了所有复杂的GUI，聚焦于核心功能的实现，开发周期短，维护成本低，完全符合你的需求。