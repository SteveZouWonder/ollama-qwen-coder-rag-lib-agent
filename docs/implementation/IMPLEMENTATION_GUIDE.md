# 本地应用化实现指南

## 🛠️ 快速开始

### 1. 环境准备

```bash
# 安装桌面应用依赖
pip install pystray pillow
pip install PyQt5  # 可选，如果需要更现代的UI
pip install pyinstaller  # 用于打包
```

### 2. 项目结构初始化

```bash
# 创建桌面应用目录
mkdir -p desktop_app assets installers/{macos,windows,linux}
```

### 3. 最小化原型

首先实现一个可运行的最小化原型：

**desktop_app/minimal_app.py**:
```python
#!/usr/bin/env python3
"""
RAG Assistant 最小化桌面应用原型
"""
import sys
import time
import threading
import logging
from pathlib import Path

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class MinimalApp:
    def __init__(self):
        self.running = False
        logger.info("RAG Assistant 初始化...")
        
    def startup_check(self):
        """启动时检查"""
        logger.info("执行启动检查...")
        
        # 检查 Ollama 服务
        try:
            import requests
            response = requests.get("http://localhost:11434/api/tags", timeout=2)
            if response.status_code == 200:
                logger.info("✅ Ollama 服务正常")
            else:
                logger.warning("⚠️ Ollama 服务响应异常")
        except Exception as e:
            logger.error(f"❌ Ollama 服务不可用: {e}")
            
        # 检查知识库索引
        index_path = Path("./index_storage")
        if index_path.exists():
            logger.info("✅ 知识库索引存在")
        else:
            logger.warning("⚠️ 知识库索引不存在，请先构建索引")
            
    def warm_up_models(self):
        """模型预热"""
        logger.info("开始模型预热...")
        
        try:
            import requests
            models = ["qwen2.5-coder:7b", "nomic-embed-text:latest"]
            
            for model in models:
                logger.info(f"预热模型: {model}")
                try:
                    response = requests.post(
                        "http://localhost:11434/api/generate",
                        json={"model": model, "prompt": "hi", "stream": False},
                        timeout=30
                    )
                    if response.status_code == 200:
                        logger.info(f"✅ {model} 预热成功")
                    else:
                        logger.warning(f"⚠️ {model} 预热失败")
                except Exception as e:
                    logger.error(f"❌ {model} 预热错误: {e}")
                    
        except Exception as e:
            logger.error(f"模型预热过程错误: {e}")
            
    def run(self):
        """运行应用"""
        self.running = True
        
        # 启动检查
        self.startup_check()
        
        # 模型预热（后台线程）
        warm_thread = threading.Thread(target=self.warm_up_models)
        warm_thread.daemon = True
        warm_thread.start()
        
        logger.info("RAG Assistant 运行中...")
        logger.info("按 Ctrl+C 退出")
        
        try:
            while self.running:
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("收到退出信号")
            self.running = False
            
        logger.info("RAG Assistant 已停止")

def main():
    """主入口"""
    app = MinimalApp()
    app.run()

if __name__ == "__main__":
    main()
```

运行最小化原型：
```bash
python desktop_app/minimal_app.py
```

---

## 📱 系统托盘实现

### 基础系统托盘应用

**desktop_app/tray_app.py**:
```python
#!/usr/bin/env python3
"""
RAG Assistant 系统托盘应用
"""
import sys
import time
import threading
import logging
import pystray
from PIL import Image, ImageDraw, ImageFont
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TrayApp:
    def __init__(self):
        self.icon = None
        self.running = False
        self.status = "初始化中"
        
    def create_icon_image(self, status="normal"):
        """创建托盘图标"""
        # 创建64x64的图像
        image = Image.new('RGB', (64, 64), color=(0, 120, 215))
        draw = ImageDraw.Draw(image)
        
        # 根据状态改变颜色
        if status == "normal":
            color = (0, 200, 83)  # 绿色
        elif status == "warning":
            color = (255, 193, 7)  # 黄色
        elif status == "error":
            color = (244, 67, 54)  # 红色
        else:
            color = (0, 120, 215)  # 蓝色
            
        # 绘制背景圆
        draw.ellipse([8, 8, 56, 56], fill=color)
        
        # 绘制文字
        try:
            font = ImageFont.truetype("/System/Library/Fonts/Arial.ttf", 24)
        except:
            font = ImageFont.load_default()
            
        draw.text((16, 20), "R", fill=(255, 255, 255), font=font)
        
        return image
        
    def on_clicked(self, icon, item):
        """菜单项点击事件"""
        if item == "打开状态":
            self.show_status()
        elif item == "打开配置":
            self.show_config()
        elif item == "重启服务":
            self.restart_services()
        elif item == "退出":
            self.quit_app()
            
    def show_status(self):
        """显示状态窗口"""
        logger.info("打开状态窗口")
        # TODO: 实现状态窗口
        
    def show_config(self):
        """显示配置窗口"""
        logger.info("打开配置窗口")
        # TODO: 实现配置窗口
        
    def restart_services(self):
        """重启服务"""
        logger.info("重启服务")
        self.status = "重启中"
        self.icon.icon = self.create_icon_image("warning")
        # TODO: 实现服务重启逻辑
        time.sleep(2)
        self.status = "正常"
        self.icon.icon = self.create_icon_image("normal")
        
    def quit_app(self):
        """退出应用"""
        logger.info("退出应用")
        self.running = False
        self.icon.stop()
        
    def run(self):
        """运行托盘应用"""
        # 创建菜单
        menu = pystray.Menu(
            pystray.MenuItem("打开状态", lambda: self.on_clicked(None, "打开状态")),
            pystray.MenuItem("打开配置", lambda: self.on_clicked(None, "打开配置")),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("重启服务", lambda: self.on_clicked(None, "重启服务")),
            pystray.MenuItem("退出", lambda: self.on_clicked(None, "退出"))
        )
        
        # 创建图标
        image = self.create_icon_image("normal")
        self.icon = pystray.Icon("RAG Assistant", image, menu=menu)
        
        # 设置状态
        self.status = "正常"
        self.running = True
        
        logger.info("系统托盘应用启动")
        self.icon.run()

def main():
    """主入口"""
    app = TrayApp()
    app.run()

if __name__ == "__main__":
    main()
```

运行系统托盘应用：
```bash
python desktop_app/tray_app.py
```

---

## 🚀 模型预热实现

### 完整的模型预热器

**desktop_app/model_warmer.py**:
```python
#!/usr/bin/env python3
"""
Ollama 模型预热器
"""
import requests
import time
import logging
import threading
from typing import List, Dict, Callable, Optional
from dataclasses import dataclass
from enum import Enum

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class WarmupStatus(Enum):
    """预热状态"""
    PENDING = "pending"
    WARMING = "warming"
    SUCCESS = "success"
    FAILED = "failed"

@dataclass
class WarmupResult:
    """预热结果"""
    model: str
    status: WarmupStatus
    message: str
    load_time: float = 0.0

class ModelWarmer:
    """模型预热器"""
    
    def __init__(self, ollama_base_url: str = "http://localhost:11434"):
        self.base_url = ollama_base_url
        self.logger = logging.getLogger(__name__)
        self.results: Dict[str, WarmupResult] = {}
        
    def check_ollama_service(self) -> bool:
        """检查 Ollama 服务是否可用"""
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=5)
            return response.status_code == 200
        except Exception as e:
            self.logger.error(f"Ollama 服务检查失败: {e}")
            return False
            
    def get_available_models(self) -> List[str]:
        """获取可用模型列表"""
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=5)
            if response.status_code == 200:
                data = response.json()
                models = [m["name"] for m in data.get("models", [])]
                return models
        except Exception as e:
            self.logger.error(f"获取模型列表失败: {e}")
        return []
        
    def warm_up_single_model(self, model: str, timeout: int = 60) -> WarmupResult:
        """预热单个模型"""
        self.logger.info(f"开始预热模型: {model}")
        start_time = time.time()
        
        try:
            # 发送预热请求
            response = requests.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": model,
                    "prompt": "hello",
                    "stream": False,
                    "options": {
                        "num_predict": 1  # 最小生成，仅用于加载模型
                    }
                },
                timeout=timeout
            )
            
            load_time = time.time() - start_time
            
            if response.status_code == 200:
                self.logger.info(f"✅ {model} 预热成功 (耗时: {load_time:.2f}s)")
                return WarmupResult(
                    model=model,
                    status=WarmupStatus.SUCCESS,
                    message="预热成功",
                    load_time=load_time
                )
            else:
                self.logger.warning(f"⚠️ {model} 预热失败 (状态码: {response.status_code})")
                return WarmupResult(
                    model=model,
                    status=WarmupStatus.FAILED,
                    message=f"HTTP {response.status_code}",
                    load_time=load_time
                )
                
        except requests.exceptions.Timeout:
            load_time = time.time() - start_time
            self.logger.error(f"❌ {model} 预热超时")
            return WarmupResult(
                model=model,
                status=WarmupStatus.FAILED,
                message="请求超时",
                load_time=load_time
            )
        except Exception as e:
            load_time = time.time() - start_time
            self.logger.error(f"❌ {model} 预热错误: {e}")
            return WarmupResult(
                model=model,
                status=WarmupStatus.FAILED,
                message=str(e),
                load_time=load_time
            )
            
    def warm_up_models(
        self, 
        models: List[str],
        progress_callback: Optional[Callable] = None,
        timeout: int = 60
    ) -> Dict[str, WarmupResult]:
        """预热多个模型"""
        self.logger.info(f"开始预热 {len(models)} 个模型...")
        
        results = {}
        total = len(models)
        
        # 检查 Ollama 服务
        if not self.check_ollama_service():
            self.logger.error("Ollama 服务不可用，无法预热模型")
            for model in models:
                results[model] = WarmupResult(
                    model=model,
                    status=WarmupStatus.FAILED,
                    message="Ollama 服务不可用"
                )
            return results
            
        # 逐个预热模型
        for i, model in enumerate(models):
            if progress_callback:
                progress_callback(i, total, model, WarmupStatus.WARMING)
                
            result = self.warm_up_single_model(model, timeout)
            results[model] = result
            self.results[model] = result
            
            if progress_callback:
                progress_callback(i + 1, total, model, result.status)
                
        # 统计结果
        success_count = sum(1 for r in results.values() if r.status == WarmupStatus.SUCCESS)
        self.logger.info(f"预热完成: {success_count}/{total} 成功")
        
        return results
        
    def warm_up_parallel(
        self,
        models: List[str],
        max_workers: int = 2,
        progress_callback: Optional[Callable] = None
    ) -> Dict[str, WarmupResult]:
        """并行预热模型"""
        import concurrent.futures
        
        self.logger.info(f"开始并行预热 {len(models)} 个模型 (最大并发: {max_workers})...")
        
        results = {}
        
        # 检查 Ollama 服务
        if not self.check_ollama_service():
            self.logger.error("Ollama 服务不可用，无法预热模型")
            for model in models:
                results[model] = WarmupResult(
                    model=model,
                    status=WarmupStatus.FAILED,
                    message="Ollama 服务不可用"
                )
            return results
            
        # 并行预热
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_model = {
                executor.submit(self.warm_up_single_model, model): model 
                for model in models
            }
            
            for i, future in enumerate(concurrent.futures.as_completed(future_to_model)):
                model = future_to_model[future]
                try:
                    result = future.result()
                    results[model] = result
                    
                    if progress_callback:
                        progress_callback(i + 1, len(models), model, result.status)
                        
                except Exception as e:
                    results[model] = WarmupResult(
                        model=model,
                        status=WarmupStatus.FAILED,
                        message=str(e)
                    )
                    
        return results
        
    def get_model_info(self, model: str) -> Optional[Dict]:
        """获取模型详细信息"""
        try:
            response = requests.post(
                f"{self.base_url}/api/show",
                json={"name": model},
                timeout=10
            )
            if response.status_code == 200:
                return response.json()
        except Exception as e:
            self.logger.error(f"获取模型信息失败: {e}")
        return None

def main():
    """测试主函数"""
    warmer = ModelWarmer()
    
    # 检查服务
    if not warmer.check_ollama_service():
        print("Ollama 服务不可用，请先启动 Ollama")
        return
        
    # 获取可用模型
    available_models = warmer.get_available_models()
    print(f"可用模型: {available_models}")
    
    # 指定要预热的模型
    models_to_warm = ["qwen2.5-coder:7b", "nomic-embed-text:latest"]
    
    # 过滤掉不可用的模型
    models_to_warm = [m for m in models_to_warm if m in available_models]
    
    if not models_to_warm:
        print("没有找到要预热的模型")
        return
        
    # 进度回调
    def progress_callback(current, total, model, status):
        status_str = status.value if isinstance(status, WarmupStatus) else status
        print(f"[{current}/{total}] {model}: {status_str}")
        
    # 预热模型
    results = warmer.warm_up_models(models_to_warm, progress_callback)
    
    # 打印结果
    print("\n预热结果:")
    for model, result in results.items():
        print(f"{model}: {result.status.value} - {result.message} ({result.load_time:.2f}s)")

if __name__ == "__main__":
    main()
```

测试模型预热器：
```bash
python desktop_app/model_warmer.py
```

---

## ⚙️ 自启动实现

### macOS 自启动

**desktop_app/autostart_macos.py**:
```python
#!/usr/bin/env python3
"""
macOS 自启动管理器
"""
import os
import subprocess
import plistlib
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

class MacAutostartManager:
    """macOS 自启动管理器"""
    
    def __init__(self, app_name="RAG Assistant"):
        self.app_name = app_name
        self.bundle_id = f"com.ragassistant.app"
        self.plist_path = Path.home() / "Library" / "LaunchAgents" / f"{self.bundle_id}.plist"
        
    def enable_autostart(self, app_path: str) -> bool:
        """启用自启动"""
        try:
            # 确保 LaunchAgents 目录存在
            self.plist_path.parent.mkdir(parents=True, exist_ok=True)
            
            # 创建 plist 文件
            plist_content = {
                "Label": self.bundle_id,
                "ProgramArguments": [app_path],
                "RunAtLoad": True,
                "KeepAlive": {
                    "SuccessfulExit": False,
                    "NetworkState": True
                },
                "StandardOutPath": str(Path.home() / "Library" / "Logs" / f"{self.app_name}.log"),
                "StandardErrorPath": str(Path.home() / "Library" / "Logs" / f"{self.app_name}-error.log"),
                "WorkingDirectory": str(Path(app_path).parent)
            }
            
            with open(self.plist_path, 'wb') as f:
                plistlib.dump(plist_content, f)
                
            # 加载到 launchd
            subprocess.run(["launchctl", "load", str(self.plist_path)], check=True)
            
            logger.info(f"自启动已启用: {self.plist_path}")
            return True
            
        except Exception as e:
            logger.error(f"启用自启动失败: {e}")
            return False
            
    def disable_autostart(self) -> bool:
        """禁用自启动"""
        try:
            # 卸载从 launchd
            if self.plist_path.exists():
                subprocess.run(["launchctl", "unload", str(self.plist_path)], check=False)
                self.plist_path.unlink()
                logger.info(f"自启动已禁用: {self.plist_path}")
            return True
            
        except Exception as e:
            logger.error(f"禁用自启动失败: {e}")
            return False
            
    def is_autostart_enabled(self) -> bool:
        """检查自启动是否启用"""
        return self.plist_path.exists()
        
    def get_autostart_status(self) -> dict:
        """获取自启动状态"""
        return {
            "enabled": self.is_autostart_enabled(),
            "plist_path": str(self.plist_path),
            "exists": self.plist_path.exists()
        }

def main():
    """测试主函数"""
    manager = MacAutostartManager()
    
    # 检查当前状态
    status = manager.get_autostart_status()
    print(f"自启动状态: {status}")
    
    # 测试启用自启动
    if not status["enabled"]:
        app_path = "/Applications/RAG Assistant.app/Contents/MacOS/RAG Assistant"
        if manager.enable_autostart(app_path):
            print("自启动已启用")
        else:
            print("启用自启动失败")
```

### Windows 自启动

**desktop_app/autostart_windows.py**:
```python
#!/usr/bin/env python3
"""
Windows 自启动管理器
"""
import winreg
import os
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

class WindowsAutostartManager:
    """Windows 自启动管理器"""
    
    def __init__(self, app_name="RAG Assistant"):
        self.app_name = app_name
        self.reg_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
        
    def enable_autostart(self, app_path: str) -> bool:
        """启用自启动"""
        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                self.reg_path,
                0,
                winreg.KEY_SET_VALUE
            )
            
            winreg.SetValueEx(
                key,
                self.app_name,
                0,
                winreg.REG_SZ,
                app_path
            )
            
            winreg.CloseKey(key)
            logger.info(f"自启动已启用: {app_path}")
            return True
            
        except Exception as e:
            logger.error(f"启用自启动失败: {e}")
            return False
            
    def disable_autostart(self) -> bool:
        """禁用自启动"""
        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                self.reg_path,
                0,
                winreg.KEY_SET_VALUE
            )
            
            try:
                winreg.DeleteValue(key, self.app_name)
                logger.info("自启动已禁用")
            except FileNotFoundError:
                logger.warning("自启动项不存在")
                
            winreg.CloseKey(key)
            return True
            
        except Exception as e:
            logger.error(f"禁用自启动失败: {e}")
            return False
            
    def is_autostart_enabled(self) -> bool:
        """检查自启动是否启用"""
        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                self.reg_path,
                0,
                winreg.KEY_READ
            )
            
            try:
                winreg.QueryValueEx(key, self.app_name)
                return True
            except FileNotFoundError:
                return False
            finally:
                winreg.CloseKey(key)
                
        except Exception as e:
            logger.error(f"检查自启动状态失败: {e}")
            return False
            
    def get_autostart_path(self) -> str:
        """获取自启动路径"""
        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                self.reg_path,
                0,
                winreg.KEY_READ
            )
            
            try:
                path, _ = winreg.QueryValueEx(key, self.app_name)
                return path
            except FileNotFoundError:
                return ""
            finally:
                winreg.CloseKey(key)
                
        except Exception as e:
            logger.error(f"获取自启动路径失败: {e}")
            return ""
```

---

## 📦 打包配置

### PyInstaller 基础配置

**rag_assistant.spec**:
```python
# -*- mode: python ; coding: utf-8 -*-
import sys
import os

block_cipher = None

# 获取项目根目录
project_root = os.path.dirname(os.path.abspath(SPEC))

a = Analysis(
    ['desktop_app/main.py'],
    pathex=[project_root],
    binaries=[],
    datas=[
        (os.path.join(project_root, 'data'), 'data'),
        (os.path.join(project_root, 'index_storage'), 'index_storage'),
        (os.path.join(project_root, 'docs'), 'docs'),
    ],
    hiddenimports=[
        'llama_index.core',
        'llama_index.readers.file',
        'chromadb',
        'prompt_toolkit',
        'rich',
        'pystray',
        'PIL',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'matplotlib',
        'numpy',
        'pandas',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='RAGAssistant',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # 不显示控制台窗口
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join(project_root, 'assets/icon.icns') if sys.platform == 'darwin' else os.path.join(project_root, 'assets/icon.ico')
)
```

### 打包命令

```bash
# 开发模式打包 (快速测试)
pyinstaller rag_assistant.spec --onefile --noconsole

# 生产模式打包
pyinstaller rag_assistant.spec --onefile --noconsole --clean

# 查看打包内容
pyinstaller rag_assistant.spec --onefile --noconsole --log-level DEBUG
```

---

## 🧪 测试指南

### 1. 单元测试

**tests/test_desktop_app.py**:
```python
import unittest
import tempfile
import os
from pathlib import Path

class TestModelWarmer(unittest.TestCase):
    def test_ollama_service_check(self):
        from desktop_app.model_warmer import ModelWarmer
        warmer = ModelWarmer()
        result = warmer.check_ollama_service()
        self.assertIsInstance(result, bool)
        
    def test_get_available_models(self):
        from desktop_app.model_warmer import ModelWarmer
        warmer = ModelWarmer()
        models = warmer.get_available_models()
        self.assertIsInstance(models, list)

class TestAutostartManager(unittest.TestCase):
    def test_macos_autostart(self):
        # 只在 macOS 上测试
        import platform
        if platform.system() != 'Darwin':
            self.skipTest("macOS only test")
            
        from desktop_app.autostart_macos import MacAutostartManager
        manager = MacAutostartManager()
        
        # 测试状态检查
        status = manager.get_autostart_status()
        self.assertIn('enabled', status)
```

### 2. 集成测试

```bash
# 测试最小化原型
python desktop_app/minimal_app.py

# 测试系统托盘
python desktop_app/tray_app.py

# 测试模型预热
python desktop_app/model_warmer.py
```

---

## 📚 配置文件示例

### 应用配置

**config/app_config.json**:
```json
{
  "app": {
    "name": "RAG Assistant",
    "version": "1.0.0",
    "autostart": true,
    "minimize_to_tray": true,
    "show_notifications": true
  },
  "ollama": {
    "base_url": "http://localhost:11434",
    "timeout": 30,
    "warm_up_models": [
      "qwen2.5-coder:7b",
      "nomic-embed-text:latest"
    ],
    "warm_up_on_startup": true,
    "parallel_warmup": true,
    "max_warmup_workers": 2
  },
  "knowledge_base": {
    "data_dir": "./data",
    "index_dir": "./index_storage",
    "auto_index": true
  },
  "logging": {
    "level": "INFO",
    "file": "logs/app.log",
    "max_size": "10MB",
    "backup_count": 5
  }
}
```

---

## 🚨 故障排除

### 常见问题及解决方案

1. **pystray 图标不显示**
   - 确保安装了 `pillow`: `pip install pillow`
   - 检查图标路径是否正确
   - 尝试使用更简单的图标

2. **macOS 权限问题**
   - 确保应用有辅助功能权限
   - 检查 plist 文件权限: `chmod 644 ~/Library/LaunchAgents/com.ragassistant.app.plist`

3. **Windows 打包后无法运行**
   - 检查是否安装了 Visual C++ Redistributable
   - 尝试使用 `--debug` 模式打包查看详细错误

4. **模型预热超时**
   - 增加 `timeout` 参数
   - 检查 Ollama 服务是否正常
   - 减少并行预热的模型数量

---

这个实现指南提供了具体的代码示例和实现细节，可以作为开发桌面应用的技术参考。建议按照最小化原型 → 系统托盘 → 完整功能的顺序逐步实现。