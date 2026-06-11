# 本地应用化设计方案

## 📋 概述

将 RAG + Agent 助手改造为本地桌面应用，支持系统自启动和 Ollama 模型预热，提供更好的用户体验。

---

## 🎯 设计目标

1. **桌面应用体验**: 提供图形界面或系统托盘图标
2. **开机自启动**: 系统启动时自动运行应用
3. **模型预热**: 启动时预热 Ollama 模型，减少首次查询延迟
4. **后台运行**: 最小化到系统托盘，不占用桌面空间
5. **状态监控**: 实时显示应用状态和模型加载情况
6. **跨平台支持**: 支持 macOS、Windows、Linux

---

## 🏗️ 系统架构

```
┌─────────────────────────────────────────────────────────────┐
│                    桌面应用层                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │ 系统托盘图标  │  │ 状态监控窗口  │  │ 配置管理界面  │     │
│  └──────────────┘  └──────────────┘  └──────────────┘     │
└─────────────────────────────────────────────────────────────┘
                            │
┌─────────────────────────────────────────────────────────────┐
│                    应用管理层                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │ 自启动管理器  │  │ 模型预热器    │  │ 健康检查器    │     │
│  └──────────────┘  └──────────────┘  └──────────────┘     │
└─────────────────────────────────────────────────────────────┘
                            │
┌─────────────────────────────────────────────────────────────┐
│                    核心服务层                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │ RAG 引擎     │  │ Agent 引擎   │  │ 查询接口     │     │
│  └──────────────┘  └──────────────┘  └──────────────┘     │
└─────────────────────────────────────────────────────────────┘
                            │
┌─────────────────────────────────────────────────────────────┐
│                    基础设施层                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │ Ollama 服务  │  │ 向量数据库   │  │ 文件系统     │     │
│  └──────────────┘  └──────────────┘  └──────────────┘     │
└─────────────────────────────────────────────────────────────┘
```

---

## 🔧 技术选型

### 方案A: 轻量级方案（推荐）

**优点**: 开发快速，资源占用少，易于维护
**缺点**: 功能相对基础

#### 技术栈
- **GUI框架**: `tkinter` (Python内置) 或 `PyQt5/PySide6`
- **系统托盘**: `pystray` (跨平台)
- **自启动**: 平台特定脚本
- **打包**: `PyInstaller` 或 `cx_Freeze`

#### 文件结构
```
ollama-qwen-coder-rag-lib/
├── desktop_app/              # 新增桌面应用目录
│   ├── __init__.py
│   ├── main.py              # 应用主入口
│   ├── tray_icon.py         # 系统托盘图标
│   ├── config_window.py     # 配置窗口
│   ├── status_window.py     # 状态监控窗口
│   ├── autostart_manager.py # 自启动管理器
│   └── model_warmer.py      # 模型预热器
├── installers/              # 新增安装脚本目录
│   ├── macos/
│   │   ├── install.sh      # macOS安装脚本
│   │   └── uninstall.sh    # macOS卸载脚本
│   ├── windows/
│   │   ├── install.ps1     # Windows安装脚本
│   │   └── uninstall.ps1   # Windows卸载脚本
│   └── linux/
│       ├── install.sh      # Linux安装脚本
│       └── uninstall.sh    # Linux卸载脚本
└── ... (现有文件)
```

### 方案B: Electron 方案

**优点**: 现代化UI，跨平台一致性好
**缺点**: 资源占用大，开发复杂度高

#### 技术栈
- **前端框架**: Electron + React/Vue
- **后端通信**: HTTP API 或 WebSocket
- **打包**: electron-builder

### 方案C: Web 界面 + 本地服务

**优点**: 界面现代，易于扩展
**缺点**: 需要浏览器，不够原生

#### 技术栈
- **Web框架**: Flask/FastAPI + Streamlit/Gradio
- **本地服务**: 系统服务
- **访问**: 浏览器或本地应用包装

---

## 📝 详细设计（方案A）

### 1. 系统托盘应用

**功能**:
- 显示应用图标（系统托盘）
- 右键菜单：打开配置、查看状态、重启、退出
- 左键单击：显示状态窗口
- 状态指示：正常/警告/错误

**实现要点**:
```python
# desktop_app/tray_icon.py
import pystray
from PIL import Image, ImageDraw
import threading

class TrayIcon:
    def __init__(self, app_controller):
        self.app = app_controller
        self.icon = None
        self.running = False
        
    def create_icon(self):
        # 创建托盘图标
        image = self._create_icon_image()
        menu = pystray.Menu(
            pystray.MenuItem("打开状态窗口", self.open_status_window),
            pystray.MenuItem("打开配置", self.open_config),
            pystray.MenuItem("重启服务", self.restart_services),
            pystray.MenuItem("退出", self.quit_app)
        )
        self.icon = pystray.Icon("RAG助手", image, menu=menu)
        
    def _create_icon_image(self):
        # 创建简单的图标
        image = Image.new('RGB', (64, 64), color=(0, 120, 215))
        d = ImageDraw.Draw(image)
        d.text((10, 10), "RAG", fill=(255, 255, 255))
        return image
        
    def run(self):
        self.running = True
        self.icon.run()
```

### 2. 自启动管理器

**macOS 实现**:
```python
# desktop_app/autostart_manager.py
import os
import plistlib

class MacAutostartManager:
    PLIST_PATH = os.path.expanduser(
        "~/Library/LaunchAgents/com.ragassistant.plist"
    )
    
    def enable_autostart(self, app_path):
        plist_content = {
            "Label": "com.ragassistant",
            "ProgramArguments": [app_path],
            "RunAtLoad": True,
            "KeepAlive": True
        }
        with open(self.PLIST_PATH, 'wb') as f:
            plistlib.dump(plist_content, f)
            
    def disable_autostart(self):
        if os.path.exists(self.PLIST_PATH):
            os.remove(self.PLIST_PATH)
```

**Windows 实现**:
```python
import winreg

class WindowsAutostartManager:
    REG_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
    
    def enable_autostart(self, app_path):
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, 
                            self.REG_PATH, 0, winreg.KEY_SET_VALUE)
        winreg.SetValueEx(key, "RAGAssistant", 0, 
                         winreg.REG_SZ, app_path)
        winreg.CloseKey(key)
        
    def disable_autostart(self):
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, 
                            self.REG_PATH, 0, winreg.KEY_SET_VALUE)
        try:
            winreg.DeleteValue(key, "RAGAssistant")
        except FileNotFoundError:
            pass
        winreg.CloseKey(key)
```

**Linux 实现**:
```python
class LinuxAutostartManager:
    DESKTOP_FILE = os.path.expanduser(
        "~/.config/autostart/ragassistant.desktop"
    )
    
    def enable_autostart(self, app_path):
        content = f"""[Desktop Entry]
Type=Application
Name=RAG Assistant
Exec={app_path}
Icon=ragassistant
Terminal=false
Categories=Utility;
"""
        os.makedirs(os.path.dirname(self.DESKTOP_FILE), exist_ok=True)
        with open(self.DESKTOP_FILE, 'w') as f:
            f.write(content)
```

### 3. 模型预热器

**策略**:
- 启动时发送预热请求到 Ollama
- 监控模型加载状态
- 显示预热进度
- 支持后台预热

**实现**:
```python
# desktop_app/model_warmer.py
import requests
import time
import logging
from typing import Optional

class ModelWarmer:
    def __init__(self, ollama_base_url="http://localhost:11434"):
        self.base_url = ollama_base_url
        self.logger = logging.getLogger(__name__)
        
    def warm_up_models(self, models: list, 
                      progress_callback=None) -> dict:
        """预热指定的模型列表"""
        results = {}
        total = len(models)
        
        for i, model in enumerate(models):
            if progress_callback:
                progress_callback(i, total, model)
                
            try:
                success = self._warm_up_single_model(model)
                results[model] = {
                    "success": success,
                    "message": "预热成功" if success else "预热失败"
                }
            except Exception as e:
                results[model] = {
                    "success": False,
                    "message": f"错误: {str(e)}"
                }
                
        return results
        
    def _warm_up_single_model(self, model: str) -> bool:
        """预热单个模型"""
        # 发送一个简单的生成请求来加载模型
        try:
            response = requests.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": model,
                    "prompt": "hi",
                    "stream": False
                },
                timeout=30
            )
            return response.status_code == 200
        except Exception as e:
            self.logger.error(f"预热模型 {model} 失败: {e}")
            return False
            
    def check_model_loaded(self, model: str) -> bool:
        """检查模型是否已加载"""
        try:
            response = requests.get(f"{self.base_url}/api/tags")
            if response.status_code == 200:
                data = response.json()
                models = data.get("models", [])
                return any(m["name"] == model for m in models)
        except Exception as e:
            self.logger.error(f"检查模型状态失败: {e}")
        return False
```

### 4. 状态监控窗口

**功能**:
- 显示应用运行状态
- 显示 Ollama 服务状态
- 显示模型加载状态
- 显示知识库统计信息
- 显示系统资源使用情况

**UI设计**:
```
┌─────────────────────────────────────────────┐
│ RAG助手状态监控              [_][□][×]       │
├─────────────────────────────────────────────┤
│ 应用状态: 🟢 运行中                          │
│ Ollama服务: 🟢 正常 (localhost:11434)       │
│                                             │
│ 模型状态:                                   │
│   qwen2.5-coder:7b      🟢 已加载           │
│   nomic-embed-text     🟢 已加载           │
│                                             │
│ 知识库统计:                                 │
│   文档数量: 1                               │
│   总片段数: 80                              │
│   索引大小: 2.3MB                           │
│                                             │
│ 系统资源:                                   │
│   CPU使用: 5%                               │
│   内存使用: 512MB                           │
│                                             │
│ 最近活动:                                   │
│   [11:45:23] 查询: "什么是Cloudflare Tunnel"│
│   [11:30:15] 技能生成: cloudflare          │
│                                             │
│            [刷新] [配置] [关闭]            │
└─────────────────────────────────────────────┘
```

### 5. 配置管理界面

**功能**:
- 自启动开关
- 模型预热设置
- Ollama 服务地址配置
- 知识库路径设置
- 日志级别设置
- 端口配置

**实现要点**:
```python
# desktop_app/config_window.py
import tkinter as tk
from tkinter import ttk

class ConfigWindow:
    def __init__(self, parent, config_manager):
        self.window = tk.Toplevel(parent)
        self.config = config_manager
        self.setup_ui()
        
    def setup_ui(self):
        # 自启动设置
        self.autostart_var = tk.BooleanVar()
        ttk.Checkbutton(
            self.window, 
            text="开机自启动",
            variable=self.autostart_var,
            command=self.toggle_autostart
        ).pack(pady=5)
        
        # 模型预热设置
        ttk.Label(self.window, text="预热模型:").pack(pady=5)
        self.model_listbox = tk.Listbox(self.window, height=3)
        self.model_listbox.insert(1, "qwen2.5-coder:7b")
        self.model_listbox.insert(2, "nomic-embed-text:latest")
        self.model_listbox.pack()
        
        # Ollama 配置
        ttk.Label(self.window, text="Ollama地址:").pack(pady=5)
        self.ollama_url = ttk.Entry(self.window)
        self.ollama_url.insert(0, "http://localhost:11434")
        self.ollama_url.pack()
        
        # 保存按钮
        ttk.Button(self.window, text="保存配置", 
                  command=self.save_config).pack(pady=10)
```

### 6. 应用主控制器

**功能**:
- 统一管理所有组件
- 协调各模块启动顺序
- 处理应用生命周期

**实现**:
```python
# desktop_app/main.py
import sys
import threading
import logging
from pathlib import Path

class AppController:
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.tray_icon = None
        self.model_warmer = None
        self.autostart_manager = None
        self.config = self.load_config()
        
    def initialize(self):
        """初始化所有组件"""
        # 1. 初始化日志
        self.setup_logging()
        
        # 2. 初始化模型预热器
        self.model_warmer = ModelWarmer(
            self.config.get("ollama_base_url", "http://localhost:11434")
        )
        
        # 3. 初始化自启动管理器
        self.autostart_manager = self.get_autostart_manager()
        
        # 4. 初始化系统托盘
        self.tray_icon = TrayIcon(self)
        self.tray_icon.create_icon()
        
        # 5. 预热模型
        self.warm_up_models()
        
    def start(self):
        """启动应用"""
        self.initialize()
        
        # 在单独线程中运行托盘图标
        tray_thread = threading.Thread(target=self.tray_icon.run)
        tray_thread.daemon = True
        tray_thread.start()
        
        self.logger.info("RAG助手已启动")
        
    def warm_up_models(self):
        """预热模型"""
        models = self.config.get("warm_up_models", [
            "qwen2.5-coder:7b",
            "nomic-embed-text:latest"
        ])
        
        def progress_callback(current, total, model):
            self.logger.info(f"预热进度: {current}/{total} - {model}")
            
        # 在后台线程中预热
        warm_thread = threading.Thread(
            target=self.model_warmer.warm_up_models,
            args=(models, progress_callback)
        )
        warm_thread.daemon = True
        warm_thread.start()
        
    def get_autostart_manager(self):
        """根据平台返回对应的管理器"""
        import platform
        system = platform.system()
        
        if system == "Darwin":  # macOS
            from autostart_manager import MacAutostartManager
            return MacAutostartManager()
        elif system == "Windows":
            from autostart_manager import WindowsAutostartManager
            return WindowsAutostartManager()
        else:  # Linux
            from autostart_manager import LinuxAutostartManager
            return LinuxAutostartManager()

def main():
    """应用主入口"""
    app = AppController()
    app.start()
    
    # 保持主线程运行
    try:
        while True:
            import time
            time.sleep(1)
    except KeyboardInterrupt:
        app.logger.info("应用退出")
        sys.exit(0)

if __name__ == "__main__":
    main()
```

---

## 📦 打包和部署

### 1. 打包配置

**PyInstaller 配置** (`rag_assistant.spec`):
```python
# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['desktop_app/main.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('data', 'data'),
        ('index_storage', 'index_storage'),
        ('docs', 'docs'),
    ],
    hiddenimports=[
        'llama_index',
        'chromadb',
        'prompt_toolkit',
        'rich',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
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
    icon='assets/icon.icns' if sys.platform == 'darwin' else 'assets/icon.ico'
)
```

### 2. 安装脚本

**macOS 安装脚本** (`installers/macos/install.sh`):
```bash
#!/bin/bash

# RAG Assistant macOS 安装脚本

APP_NAME="RAG Assistant"
APP_DIR="/Applications/RAG Assistant.app"
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

echo "正在安装 $APP_NAME..."

# 创建应用目录结构
sudo mkdir -p "$APP_DIR/Contents/MacOS"
sudo mkdir -p "$APP_DIR/Contents/Resources"

# 复制应用文件
sudo cp "$SCRIPT_DIR/../../dist/RAG Assistant" "$APP_DIR/Contents/MacOS/"
sudo cp "$SCRIPT_DIR/../../assets/icon.icns" "$APP_DIR/Contents/Resources/"

# 创建 Info.plist
cat > "$APP_DIR/Contents/Info.plist" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleExecutable</key>
    <string>RAG Assistant</string>
    <key>CFBundleIconFile</key>
    <string>icon</string>
    <key>CFBundleIdentifier</key>
    <string>com.ragassistant.app</string>
    <key>CFBundleName</key>
    <string>RAG Assistant</string>
    <key>CFBundleVersion</key>
    <string>1.0.0</string>
    <key>LSUIElement</key>
    <false/>
</dict>
</plist>
EOF

# 设置权限
sudo chmod +x "$APP_DIR/Contents/MacOS/RAG Assistant"

echo "安装完成！应用已安装到 $APP_DIR"
echo "你可以从应用程序文件夹启动 RAG Assistant"
```

**Windows 安装脚本** (`installers/windows/install.ps1`):
```powershell
# RAG Assistant Windows 安装脚本

$ErrorActionPreference = "Stop"

$AppName = "RAG Assistant"
$InstallDir = "$env:LOCALAPPDATA\RAG Assistant"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

Write-Host "正在安装 $AppName..."

# 创建安装目录
New-Item -ItemType Directory -Force -Path $InstallDir

# 复制应用文件
Copy-Item -Path "$ScriptDir\..\..\dist\RAG Assistant.exe" -Destination $InstallDir -Force
Copy-Item -Path "$ScriptDir\..\..\assets\icon.ico" -Destination $InstallDir -Force

# 创建桌面快捷方式
$WshShell = New-Object -comObject WScript.Shell
$Shortcut = $WshShell.CreateShortcut("$env:USERPROFILE\Desktop\RAG Assistant.lnk")
$Shortcut.TargetPath = "$InstallDir\RAG Assistant.exe"
$Shortcut.IconLocation = "$InstallDir\icon.ico"
$Shortcut.Save()

# 创建开始菜单快捷方式
$StartMenuDir = "$env:APPDATA\Microsoft\Windows\Start Menu\Programs"
$Shortcut = $WshShell.CreateShortcut("$StartMenuDir\RAG Assistant.lnk")
$Shortcut.TargetPath = "$InstallDir\RAG Assistant.exe"
$Shortcut.IconLocation = "$InstallDir\icon.ico"
$Shortcut.Save()

Write-Host "安装完成！"
Write-Host "应用已安装到: $InstallDir"
Write-Host "桌面快捷方式已创建"
```

---

## 🚀 使用流程

### 1. 开发者流程

```bash
# 1. 开发桌面应用
cd desktop_app
python main.py  # 测试运行

# 2. 打包应用
cd ..
pyinstaller rag_assistant.spec

# 3. 测试打包后的应用
./dist/RAG\ Assistant  # macOS
dist/RAG\ Assistant.exe  # Windows

# 4. 创建安装包
# macOS: 创建 .dmg 文件
# Windows: 使用 NSIS 或 Inno Setup 创建 .exe 安装程序
```

### 2. 用户流程

**Windows**:
1. 下载 `RAG-Assistant-Setup.exe`
2. 双击运行安装程序
3. 选择安装路径
4. 完成安装，桌面出现快捷方式
5. 首次启动时配置 Ollama 地址
6. 选择是否开机自启动
7. 应用自动预热模型
8. 最小化到系统托盘

**macOS**:
1. 下载 `RAG-Assistant.dmg`
2. 打开 DMG 文件
3. 拖拽应用到 Applications 文件夹
4. 从启动台打开应用
5. 配置应用设置
6. 应用自动预热模型
7. 最小化到菜单栏

---

## 🔍 配置选项

### 应用配置 (`config/app_config.json`)
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
    "warm_up_on_startup": true
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
  },
  "server": {
    "host": "localhost",
    "port": 8080,
    "enable_api": false
  }
}
```

---

## 📊 监控和日志

### 日志系统
- 应用日志: `logs/app.log`
- 错误日志: `logs/error.log`
- 性能日志: `logs/performance.log`

### 健康检查
- Ollama 服务可用性检查
- 模型加载状态检查
- 知识库索引完整性检查
- 磁盘空间检查

---

## 🎨 UI/UX 设计要点

### 系统托盘图标状态
- 🟢 绿色: 应用正常运行，所有服务正常
- 🟡 黄色: 部分服务异常（如模型未加载）
- 🔴 红色: 应用错误或服务不可用

### 通知机制
- 应用启动通知
- 模型预热完成通知
- 错误警告通知
- 更新提醒通知

---

## 🔒 安全考虑

1. **本地服务**: 所有服务监听 localhost，不暴露到外网
2. **配置保护**: 敏感配置加密存储
3. **权限管理**: 最小权限原则
4. **代码签名**: 应用程序代码签名（macOS/Windows）
5. **安全更新**: 自动更新机制

---

## 📈 性能优化

1. **模型预热**: 启动时预热，减少首次查询延迟
2. **懒加载**: 按需加载知识库索引
3. **缓存机制**: 查询结果缓存
4. **资源限制**: 限制内存和CPU使用
5. **后台优化**: 繁重操作后台执行

---

## 🐛 故障排除

### 常见问题

1. **Ollama 服务未启动**
   - 自动检测并提示用户启动
   - 提供启动 Ollama 的快捷方式

2. **模型加载失败**
   - 显示详细错误信息
   - 提供重试机制
   - 提供模型下载链接

3. **知识库索引损坏**
   - 自动重建索引
   - 备份恢复机制

4. **端口冲突**
   - 自动检测可用端口
   - 动态端口分配

---

## 📅 开发计划

### Phase 1: 基础功能 (1-2周)
- [ ] 系统托盘应用框架
- [ ] 基础状态监控
- [ ] 简单配置界面
- [ ] macOS 自启动支持

### Phase 2: 核心功能 (2-3周)
- [ ] 模型预热功能
- [ ] Windows/Linux 自启动支持
- [ ] 完整配置管理
- [ ] 健康检查系统

### Phase 3: 打包部署 (1周)
- [ ] PyInstaller 打包配置
- [ ] 跨平台安装脚本
- [ ] 应用图标设计
- [ ] 用户文档

### Phase 4: 优化增强 (1-2周)
- [ ] 性能优化
- [ ] UI/UX 改进
- [ ] 错误处理完善
- [ ] 自动更新机制

---

## 💡 未来扩展

1. **Web 界面**: 添加 Web UI 访问方式
2. **移动端**: 开发移动端应用
3. **插件系统**: 支持第三方插件
4. **云同步**: 知识库云同步功能
5. **多语言**: 国际化支持
6. **AI 功能增强**: 更多 AI 功能集成

---

## 📝 总结

本设计方案提供了一个完整的本地应用化解决方案，重点包括：

1. **轻量级实现**: 使用 Python 原生 GUI，资源占用小
2. **跨平台支持**: macOS、Windows、Linux 统一体验
3. **自启动机制**: 系统启动时自动运行
4. **模型预热**: 减少首次查询延迟，提升用户体验
5. **状态监控**: 实时显示应用和服务状态
6. **易于部署**: 提供完整的打包和安装方案

推荐采用 **方案A（轻量级方案）** 作为初始实现，后续根据需求可以逐步扩展到更复杂的方案。