# 跨平台桌面应用发布流程设计

## 概述

本文档描述了将智能文档+代码助手打包成跨平台桌面应用的完整发布流程设计，支持 macOS、Windows 和 Linux 三大平台，并实现自启动功能。

## 设计目标

1. **跨平台支持**: macOS、Windows、Linux
2. **一键安装**: 提供安装包，用户只需双击安装
3. **自启动功能**: 支持系统启动时自动运行
4. **系统托盘**: 常驻系统托盘，提供快捷操作
5. **自动更新**: 支持应用自动更新机制
6. **依赖管理**: 处理 Python 依赖和外部依赖（Ollama、Tesseract）

## 技术选型

### 打包工具对比

| 工具 | 优点 | 缺点 | 推荐度 |
|------|------|------|--------|
| **PyInstaller** | 成熟稳定、跨平台、文档丰富 | 打包体积大、启动慢 | ⭐⭐⭐⭐⭐ |
| **Nuitka** | 编译成C、性能好、体积小 | 编译复杂、某些库不兼容 | ⭐⭐⭐ |
| **cx_Freeze** | 跨平台、轻量级 | 社区较小、某些功能缺失 | ⭐⭐⭐ |
| **Py2App** (macOS) | macOS原生、性能好 | 仅支持macOS | ⭐⭐⭐⭐ |

**选择**: **PyInstaller** 作为主要打包工具，原因：
- 跨平台支持最好
- 社区成熟，文档丰富
- 与现有项目兼容性好
- 支持系统托盘等GUI功能

### 平台特定工具

#### macOS
- **创建 .app bundle**: 使用 PyInstaller 的 `--windowed` 模式
- **安装包**: 使用 `packagesbuild` 或 `pkgbuild` 创建 .pkg 安装包
- **自启动**: 使用 `launchd` 服务
- **代码签名**: 使用 Apple 开发者证书签名

#### Windows
- **创建 .exe**: PyInstaller 的 `--onefile` 或 `--onedir` 模式
- **安装包**: 使用 **Inno Setup** 或 **NSIS** 创建安装程序
- **自启动**: 注册表 `Run` 键或启动文件夹
- **代码签名**: 使用 Code Signing 证书

#### Linux
- **创建可执行文件**: PyInstaller 的 `--onefile` 模式
- **打包**: 使用 **FPM** (Effing Package Management) 创建 .deb 和 .rpm 包
- **自启动**: systemd 服务
- **容器化**: 可选 Docker 支持

## 系统架构

### 应用结构

```
智能文档+代码助手 Desktop App
├── 核心功能
│   ├── CLI 交互界面 (query_interface.py)
│   ├── RAG 知识库引擎
│   ├── Agent 系统
│   └── 桌面应用管理 (desktop_app.py)
├── GUI 功能
│   ├── 系统托盘图标
│   ├── 右键菜单
│   ├── 状态指示器
│   └── 配置界面（可选）
└── 系统集成
    ├── 自启动服务
    ├── 文件关联
    └── 通知系统
```

### 运行模式

1. **CLI 模式**: 命令行交互（现有功能）
2. **托盘模式**: 系统托盘常驻，后台运行
3. **GUI 模式**: 可选的图形配置界面（未来扩展）

## 详细设计方案

### 1. 项目结构重组

```
ollama-qwen-coder-rag-lib-agent/
├── src/
│   ├── query_interface.py      # CLI 入口
│   ├── desktop_app.py          # 桌面应用
│   └── ... (现有模块)
├── packaging/                  # 新增：打包相关文件
│   ├── build/                  # 构建输出目录
│   ├── resources/              # 资源文件
│   │   ├── icons/              # 应用图标
│   │   │   ├── app_icon.icns   # macOS
│   │   │   ├── app_icon.ico    # Windows
│   │   │   └── app_icon.png    # Linux
│   │   └── scripts/            # 平台特定脚本
│   │       ├── macos/
│   │       │   ├── launchd.plist  # 自启动配置
│   │       │   └── postinstall.sh # 安装后脚本
│   │       ├── windows/
│   │       │   ├── autostart.reg  # 自启动注册表
│   │       │   └── installer.iss  # Inno Setup 脚本
│   │       └── linux/
│   │           ├── autostart.desktop # 自启动配置
│   │           └── service.service   # systemd 服务
│   ├── pyinstaller/
│   │   ├── main.spec         # 主程序 spec 文件
│   │   ├── desktop.spec      # 桌面应用 spec 文件
│   │   └── hooks/            # PyInstaller 钩子
│   ├── inno_setup/
│   │   └── installer.iss     # Windows 安装程序脚本
│   ├── fpm/
│   │   └── package.json      # Linux 打包配置
│   └── requirements.txt      # 打包依赖
├── scripts/
│   ├── build_all.sh          # 全平台构建脚本
│   ├── build_macos.sh        # macOS 构建脚本
│   ├── build_windows.bat     # Windows 构建脚本
│   ├── build_linux.sh        # Linux 构建脚本
│   └── test_package.sh       # 包测试脚本
└── docs/
    └── future-feature-design/
        └── CROSS_PLATFORM_DESKTOP_APP_DESIGN.md  # 本文档
```

### 2. PyInstaller 配置

#### 主程序 Spec 文件 (main.spec)
```python
# -*- mode: python ; coding: utf-8 -*-
"""
主程序打包配置 - CLI 模式
"""
block_cipher = None

a = Analysis(
    ['src/query_interface.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('config', 'config'),
        ('assets', 'assets'),
    ],
    hiddenimports=[
        'llama_index',
        'chromadb',
        'pystray',
        'PIL',
        'prompt_toolkit',
        'rich',
    ],
    hookspath=['packaging/pyinstaller/hooks/'],
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
    [],
    exclude_binaries=True,
    name='ollama-assistant',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,  # CLI 模式需要控制台
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='ollama-assistant-cli',
)
```

#### 桌面应用 Spec 文件 (desktop.spec)
```python
# -*- mode: python ; coding: utf-8 -*-
"""
桌面应用打包配置 - 托盘模式
"""
block_cipher = None

a = Analysis(
    ['src/desktop_app.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('config', 'config'),
        ('assets', 'assets'),
        ('packaging/resources/icons', 'icons'),
    ],
    hiddenimports=[
        'llama_index',
        'chromadb',
        'pystray',
        'PIL',
        'prompt_toolkit',
        'rich',
    ],
    hookspath=['packaging/pyinstaller/hooks/'],
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
    [],
    exclude_binaries=True,
    name='ollama-assistant-desktop',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # 桌面应用无控制台
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='packaging/resources/icons/app_icon.ico' if sys.platform == 'win32' else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='ollama-assistant-desktop',
)
```

### 3. 平台特定实现

#### macOS 实现方案

##### 3.1 .app Bundle 创建
```bash
# 使用 PyInstaller 创建 .app
pyinstaller --windowed --onefile \
  --icon=packaging/resources/icons/app_icon.icns \
  --name="Ollama Assistant" \
  --osx-bundle-id=com.yourcompany.ollama-assistant \
  packaging/pyinstaller/desktop.spec

# 创建 Info.plist
cat > Ollama\ Assistant.app/Contents/Info.plist << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleExecutable</key>
    <string>Ollama Assistant</string>
    <key>CFBundleIdentifier</key>
    <string>com.yourcompany.ollama-assistant</string>
    <key>CFBundleName</key>
    <string>Ollama Assistant</string>
    <key>CFBundleVersion</key>
    <string>1.0.0</string>
    <key>CFBundleShortVersionString</key>
    <string>1.0.0</string>
    <key>LSUIElement</key>
    <true/>  <!-- 后台运行，不显示 Dock 图标 -->
    <key>NSAppleEventsUsageDescription</key>
    <string>需要访问 Apple Events 用于系统集成</string>
</dict>
</plist>
EOF
```

##### 3.2 自启动实现 (launchd)
```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.yourcompany.ollama-assistant</string>
    
    <key>ProgramArguments</key>
    <array>
        <string>/Applications/Ollama Assistant.app/Contents/MacOS/Ollama Assistant</string>
        <string>--tray-mode</string>
    </array>
    
    <key>RunAtLoad</key>
    <true/>  <!-- 登录时启动 -->
    
    <key>KeepAlive</key>
    <true/>  <!-- 保持运行 -->
    
    <key>StandardOutPath</key>
    <string>/tmp/ollama-assistant.log</string>
    
    <key>StandardErrorPath</key>
    <string>/tmp/ollama-assistant-error.log</string>
    
    <key>WorkingDirectory</key>
    <string>/Users/$(whoami)/.ollama-assistant</string>
</dict>
</plist>
```

##### 3.3 安装包创建
```bash
# 使用 packagesbuild 创建 .pkg
packagesbuild \
  --identifier com.yourcompany.ollama-assistant \
  --version 1.0.0 \
  --install-location /Applications \
  packaging/resources/macos/Ollama-Assistant.pkgproj
```

#### Windows 实现方案

##### 4.1 自启动实现
```python
# 在 desktop_app.py 中添加 Windows 自启动功能
import winreg
import os

def setup_autostart_windows(enable: bool = True):
    """配置 Windows 自启动"""
    app_path = os.path.abspath(sys.executable)
    key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    app_name = "OllamaAssistant"
    
    try:
        if enable:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE) as key:
                winreg.SetValueEx(key, app_name, 0, winreg.REG_SZ, app_path)
        else:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE) as key:
                winreg.DeleteValue(key, app_name)
        return True
    except Exception as e:
        print(f"自启动配置失败: {e}")
        return False
```

##### 4.2 Inno Setup 安装程序脚本
```iss
[Setup]
AppName=Ollama Assistant
AppVersion=1.0.0
DefaultDirName={pf}\Ollama Assistant
DefaultGroupName=Ollama Assistant
OutputBaseFilename=ollama-assistant-setup
Compression=lzma
SolidCompression=yes
PrivilegesRequired=admin

[Files]
Source: "dist\ollama-assistant-desktop\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Ollama Assistant"; Filename: "{app}\ollama-assistant-desktop.exe"
Name: "{commondesktop}\Ollama Assistant"; Filename: "{app}\ollama-assistant-desktop.exe"
Name: "{userstartup}\Ollama Assistant"; Filename: "{app}\ollama-assistant-desktop.exe"

[Run]
Filename: "{app}\ollama-assistant-desktop.exe"; Description: "启动 Ollama Assistant"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{userappdata}\Ollama Assistant"
```

#### Linux 实现方案

##### 5.1 自启动实现
```ini
# ~/.config/autostart/ollama-assistant.desktop
[Desktop Entry]
Type=Application
Name=Ollama Assistant
Comment=智能文档+代码助手
Exec=/opt/ollama-assistant/ollama-assistant-desktop --tray-mode
Icon=/opt/ollama-assistant/icons/app_icon.png
Terminal=false
Categories=Utility;TextTools;
X-GNOME-Autostart-enabled=true
```

##### 5.2 Systemd 服务
```ini
# /etc/systemd/system/ollama-assistant.service
[Unit]
Description=Ollama Assistant Desktop Service
After=network.target

[Service]
Type=simple
User=your-user
WorkingDirectory=/home/your-user/.ollama-assistant
ExecStart=/opt/ollama-assistant/ollama-assistant-desktop --tray-mode
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

##### 5.3 DEB 包创建
```bash
# 使用 FPM 创建 DEB 包
fpm -s dir -t deb \
  -n ollama-assistant \
  -v 1.0.0 \
  --prefix /opt \
  --description "智能文档+代码助手" \
  --after-install packaging/resources/linux/postinstall.sh \
  --before-remove packaging/resources/linux/preremove.sh \
  dist/ollama-assistant-desktop/
```

### 4. 依赖管理策略

#### 4.1 Python 依赖
- 使用 PyInstaller 自动打包大多数 Python 依赖
- 对于特殊依赖（如某些机器学习库），可能需要额外的配置

#### 4.2 外部依赖处理
```
Ollama (必需)
├── 安装检查: 应用启动时检查 Ollama 是否安装
├── 自动安装: 提供一键安装 Ollama 功能
├── 版本要求: Ollama >= 0.1.0
└── 下载引导: 未安装时引导用户到官网下载

Tesseract OCR (可选)
├── 功能检查: 检测 OCR 功能是否可用
├── 优雅降级: 不可用时禁用 OCR 功能
├── 安装引导: 提供安装指导
└── 跳过安装: 可选择不安装 OCR 功能
```

#### 4.3 依赖检查脚本
```python
# dependency_checker.py
import subprocess
import sys
import requests

def check_ollama():
    """检查 Ollama 是否安装"""
    try:
        result = subprocess.run(['ollama', '--version'], 
                              capture_output=True, text=True)
        return result.returncode == 0
    except FileNotFoundError:
        return False

def check_ollama_service():
    """检查 Ollama 服务是否运行"""
    try:
        response = requests.get('http://localhost:11434/api/tags', timeout=2)
        return response.status_code == 200
    except:
        return False

def check_tesseract():
    """检查 Tesseract 是否安装"""
    try:
        result = subprocess.run(['tesseract', '--version'], 
                              capture_output=True, text=True)
        return result.returncode == 0
    except FileNotFoundError:
        return False

def check_dependencies():
    """检查所有依赖"""
    dependencies = {
        'Ollama CLI': check_ollama(),
        'Ollama Service': check_ollama_service(),
        'Tesseract OCR': check_tesseract(),
    }
    
    missing = [k for k, v in dependencies.items() if not v]
    
    if missing:
        print("⚠️  缺少以下依赖:")
        for dep in missing:
            print(f"   - {dep}")
        return False
    else:
        print("✅ 所有依赖检查通过")
        return True

if __name__ == '__main__':
    if not check_dependencies():
        sys.exit(1)
```

### 5. 发布流程设计

#### 5.1 CI/CD 流程
```yaml
# .github/workflows/release.yml
name: Release Pipeline

on:
  push:
    tags:
      - 'v*'
  workflow_dispatch:

jobs:
  build-macos:
    runs-on: macos-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.13'
      
      - name: Install dependencies
        run: |
          pip install pyinstaller
          pip install -r requirements.txt
      
      - name: Build macOS app
        run: ./scripts/build_macos.sh
      
      - name: Code sign
        env:
          APPLE_CERTIFICATE: ${{ secrets.APPLE_CERTIFICATE }}
          APPLE_CERTIFICATE_PASSWORD: ${{ secrets.APPLE_CERTIFICATE_PASSWORD }}
        run: ./scripts/sign_macos_app.sh
      
      - name: Create package
        run: ./scripts/package_macos.sh
      
      - name: Upload artifact
        uses: actions/upload-artifact@v4
        with:
          name: macos-package
          path: dist/*.dmg

  build-windows:
    runs-on: windows-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.13'
      
      - name: Install dependencies
        run: |
          pip install pyinstaller
          pip install -r requirements.txt
      
      - name: Build Windows exe
        run: .\scripts\build_windows.bat
      
      - name: Create installer
        run: iscc packaging\inno_setup\installer.iss
      
      - name: Upload artifact
        uses: actions/upload-artifact@v4
        with:
          name: windows-installer
          path: dist/*.exe

  build-linux:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.13'
      
      - name: Install dependencies
        run: |
          pip install pyinstaller
          pip install -r requirements.txt
          sudo apt-get install -y rpm  # for FPM
      
      - name: Build Linux binary
        run: ./scripts/build_linux.sh
      
      - name: Create packages
        run: |
          gem install fpm
          ./scripts/package_linux.sh
      
      - name: Upload artifact
        uses: actions/upload-artifact@v4
        with:
          name: linux-packages
          path: dist/*.deb

  create-release:
    needs: [build-macos, build-windows, build-linux]
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Download all artifacts
        uses: actions/download-artifact@v4
      
      - name: Create GitHub Release
        uses: softprops/action-gh-release@v1
        with:
          files: |
            macos-package/*.dmg
            windows-installer/*.exe
            linux-packages/*.deb
          draft: false
          prerelease: false
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

#### 5.2 版本管理
```
版本号格式: vMAJOR.MINOR.PATCH
- MAJOR: 重大架构变更
- MINOR: 新功能添加
- PATCH: Bug 修复

示例:
- v1.0.0: 首次发布
- v1.1.0: 添加新功能
- v1.1.1: Bug 修复
- v2.0.0: 重大更新
```

#### 5.3 自动更新机制
```python
# updater.py
import requests
import version_parser

def check_for_updates(current_version: str) -> dict:
    """检查是否有新版本"""
    try:
        response = requests.get(
            'https://api.github.com/repos/yourusername/ollama-qwen-coder-rag-lib-agent/releases/latest'
        )
        latest_release = response.json()
        latest_version = latest_release['tag_name']
        
        if version_parser.parse(latest_version) > version_parser.parse(current_version):
            return {
                'update_available': True,
                'latest_version': latest_version,
                'download_url': latest_release['html_url'],
                'release_notes': latest_release['body']
            }
        else:
            return {'update_available': False}
    except:
        return {'update_available': False}

def download_update(url: str, save_path: str):
    """下载更新"""
    response = requests.get(url, stream=True)
    with open(save_path, 'wb') as f:
        for chunk in response.iter_content(chunk_size=8192):
            f.write(chunk)
```

### 6. 构建脚本实现

#### 6.1 macOS 构建脚本 (build_macos.sh)
```bash
#!/bin/bash

set -e

VERSION=${VERSION:-"1.0.0"}
BUILD_DIR="dist"
APP_NAME="Ollama Assistant"

echo "🍎 Building macOS application..."

# 清理构建目录
rm -rf $BUILD_DIR
mkdir -p $BUILD_DIR

# 安装 PyInstaller
pip install pyinstaller

# 构建主程序
pyinstaller --clean \
  --windowed \
  --onefile \
  --icon=packaging/resources/icons/app_icon.icns \
  --name="$APP_NAME" \
  --osx-bundle-id=com.yourcompany.ollama-assistant \
  packaging/pyinstaller/desktop.spec

# 创建 .app 结构
APP_BUNDLE="$BUILD_DIR/$APP_NAME.app"
mkdir -p "$APP_BUNDLE/Contents/MacOS"
mkdir -p "$APP_BUNDLE/Contents/Resources"

# 复制可执行文件
cp "dist/$APP_NAME" "$APP_BUNDLE/Contents/MacOS/"

# 复制图标
cp packaging/resources/icons/app_icon.icns "$APP_BUNDLE/Contents/Resources/"

# 创建 Info.plist
cat > "$APP_BUNDLE/Contents/Info.plist" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleExecutable</key>
    <string>$APP_NAME</string>
    <key>CFBundleIdentifier</key>
    <string>com.yourcompany.ollama-assistant</string>
    <key>CFBundleName</key>
    <string>$APP_NAME</string>
    <key>CFBundleVersion</key>
    <string>$VERSION</string>
    <key>CFBundleShortVersionString</key>
    <string>$VERSION</string>
    <key>LSUIElement</key>
    <true/>
</dict>
</plist>
EOF

echo "✅ macOS app bundle created: $APP_BUNDLE"

# 创建 DMG
hdiutil create -volname "$APP_NAME" \
  -srcfolder "$APP_BUNDLE" \
  -ov -format UDZO \
  "$BUILD_DIR/$APP_NAME-$VERSION.dmg"

echo "🎉 macOS DMG created: $BUILD_DIR/$APP_NAME-$VERSION.dmg"
```

#### 6.2 Windows 构建脚本 (build_windows.bat)
```batch
@echo off
set VERSION=1.0.0
set BUILD_DIR=dist
set APP_NAME=Ollama Assistant

echo 🪟 Building Windows application...

REM 清理构建目录
if exist %BUILD_DIR% rmdir /s /q %BUILD_DIR%
mkdir %BUILD_DIR%

REM 安装 PyInstaller
pip install pyinstaller

REM 构建主程序
pyinstaller --clean ^
  --onefile ^
  --windowed ^
  --icon=packaging\resources\icons\app_icon.ico ^
  --name="%APP_NAME%" ^
  packaging\pyinstaller\desktop.spec

echo ✅ Windows executable created: %BUILD_DIR%\%APP_NAME%.exe

REM 使用 Inno Setup 创建安装程序
if exist "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" (
    "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" packaging\inno_setup\installer.iss
    echo 🎉 Windows installer created
) else (
    echo ⚠️  Inno Setup not found, skipping installer creation
)
```

#### 6.3 Linux 构建脚本 (build_linux.sh)
```bash
#!/bin/bash

set -e

VERSION=${VERSION:-"1.0.0"}
BUILD_DIR="dist"
APP_NAME="ollama-assistant"

echo "🐧 Building Linux application..."

# 清理构建目录
rm -rf $BUILD_DIR
mkdir -p $BUILD_DIR

# 安装 PyInstaller
pip install pyinstaller

# 构建主程序
pyinstaller --clean \
  --onefile \
  --icon=packaging/resources/icons/app_icon.png \
  --name="$APP_NAME" \
  packaging/pyinstaller/desktop.spec

echo "✅ Linux executable created: $BUILD_DIR/$APP_NAME"

# 创建 DEB 包
if command -v fpm &> /dev/null; then
  fpm -s dir -t deb \
    -n ollama-assistant \
    -v $VERSION \
    --prefix /opt \
    --description "智能文档+代码助手" \
    --after-install packaging/resources/linux/postinstall.sh \
    $BUILD_DIR/$APP_NAME
  
  echo "🎉 DEB package created"
else
  echo "⚠️  FPM not found, skipping DEB package creation"
fi

# 创建 RPM 包
if command -v fpm &> /dev/null; then
  fpm -s dir -t rpm \
    -n ollama-assistant \
    -v $VERSION \
    --prefix /opt \
    --description "智能文档+代码助手" \
    --after-install packaging/resources/linux/postinstall.sh \
    $BUILD_DIR/$APP_NAME
  
  echo "🎉 RPM package created"
else
  echo "⚠️  FPM not found, skipping RPM package creation"
fi
```

### 7. 质量保证

#### 7.1 测试策略
```bash
# 单元测试
pytest tests/ -v --cov=.

# 打包测试
./scripts/test_package.sh

# 跨平台测试
- 在真实 macOS 系统上测试 .app
- 在真实 Windows 系统上测试 .exe
- 在多个 Linux 发行版上测试 .deb/.rpm
```

#### 7.2 安装测试清单
```
□ macOS .app 双击启动
□ macOS 自启动功能
□ macOS 系统托盘功能
□ Windows 安装程序安装
□ Windows 自启动功能
□ Windows 系统托盘功能
□ Linux DEB 包安装
□ Linux 自启动功能
□ Linux 系统托盘功能
□ 所有平台 Ollama 依赖检查
□ 所有平台 OCR 功能检测
```

#### 7.3 性能指标
```
应用启动时间: < 5 秒
应用内存占用: < 500MB
应用安装包大小: < 200MB
磁盘占用: < 300MB
```

## 实施计划

### Phase 1: 准备阶段 (1-2 周)
- [ ] 创建打包目录结构
- [ ] 准备应用图标和资源文件
- [ ] 编写 PyInstaller 配置文件
- [ ] 实现依赖检查脚本

### Phase 2: 核心开发 (2-3 周)
- [ ] 实现 macOS .app bundle 创建
- [ ] 实现 Windows .exe 构建
- [ ] 实现 Linux 可执行文件构建
- [ ] 实现各平台自启动功能

### Phase 3: 安装程序 (1-2 周)
- [ ] 创建 macOS .pkg 安装包
- [ ] 创建 Windows Inno Setup 安装程序
- [ ] 创建 Linux .deb/.rpm 包
- [ ] 实现安装后脚本

### Phase 4: CI/CD 集成 (1 周)
- [ ] 配置 GitHub Actions 工作流
- [ ] 实现自动构建流程
- [ ] 配置代码签名
- [ ] 实现自动发布

### Phase 5: 测试与优化 (1-2 周)
- [ ] 跨平台功能测试
- [ ] 性能优化
- [ ] Bug 修复
- [ ] 文档完善

### Phase 6: 发布 (1 周)
- [ ] 创建 GitHub Release
- [ ] 发布到各平台应用商店（可选）
- [ ] 用户文档发布
- [ ] 社区推广

**总计**: 6-10 周

## 风险与挑战

### 技术风险
1. **PyInstaller 兼容性**: 某些 Python 库可能无法正确打包
   - 解决方案: 使用自定义 hooks 和隐藏imports

2. **跨平台差异**: 不同平台的行为差异可能导致问题
   - 解决方案: 充分的跨平台测试

3. **依赖管理**: Ollama 等外部依赖的安装和管理
   - 解决方案: 提供自动安装和友好的错误提示

### 用户体验风险
1. **安装包大小**: Python 应用通常体积较大
   - 解决方案: 使用 UPX 压缩，优化依赖

2. **启动速度**: 打包后的应用启动可能较慢
   - 解决方案: 优化导入，使用懒加载

3. **系统权限**: 某些功能可能需要特殊权限
   - 解决方案: 清晰的权限请求说明

## 成本估算

### 开发成本
- 人力成本: 1-2 名开发者，6-10 周
- 测试成本: 跨平台测试设备和软件
- 基础设施成本: CI/CD 服务器，代码签名证书

### 运营成本
- 应用商店费用（如 macOS App Store, Microsoft Store）
- 证书费用（代码签名证书年费）
- 分发成本（下载服务器，CDN）

## 后续优化方向

1. **自动更新**: 实现应用内自动更新功能
2. **应用商店发布**: 发布到各平台官方应用商店
3. **GUI 界面**: 添加图形配置界面
4. **插件系统**: 支持第三方插件
5. **云同步**: 实现配置和数据云同步
6. **多语言支持**: 国际化支持

## 总结

本设计方案提供了完整的跨平台桌面应用发布流程，从技术选型、系统架构到具体实施细节都有详细规划。按照此方案实施，可以将当前的 Python 项目打包成专业的跨平台桌面应用，提供一致的用户体验和可靠的安装方式。

---

**文档版本**: 1.0  
**创建日期**: 2026-06-12  
**预计实施周期**: 6-10 周  
**维护者**: AI Development Team
