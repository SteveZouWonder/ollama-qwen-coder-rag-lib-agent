# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置 —— Cerebro。

一个可执行体同时提供 GUI（系统托盘）与 CLI（--cli）两种入口，
入口为项目根目录的 ``launcher.py``。

构建命令（在项目根目录执行）：
    pyinstaller packaging/cerebro.spec --noconfirm

设计要点：
- 使用 collect_all / collect_submodules 处理 chromadb、llama_index 等
  存在大量动态导入的库，避免运行时 ImportError。
- 通过 datas 打包 assets/（图标）与 config/（默认配置）。
- 通过 excludes 排除测试与 OCR 等可选重依赖，控制体积。
"""
import sys
from pathlib import Path

from PyInstaller.utils.hooks import (
    collect_all,
    collect_submodules,
    collect_data_files,
)

# spec 文件被 PyInstaller 以 exec 方式加载，无 __file__；用 CWD 作为项目根。
PROJECT_ROOT = Path.cwd()

# 应用版本：从环境变量 APP_VERSION 读取（CI 中由 release.yml 注入，与 tag 同步），
# 本地构建未设置时回退为 0.0.0。
import os as _os

APP_VERSION = _os.environ.get("APP_VERSION", "0.0.0")

# 让 spec 内的 collect_submodules 能按顶层名找到 src 内的子包
sys.path.insert(0, str(PROJECT_ROOT / "src"))

block_cipher = None

# ---------------------------------------------------------------------------
# 数据文件：图标、默认配置
# ---------------------------------------------------------------------------
# 注意：数据目录目标名不能用 "config"，否则会与顶层模块 config.py 冲突
# （src 内模块以顶层名导入：from config import ...）。改用 default_config。
datas = [
    (str(PROJECT_ROOT / "assets"), "assets"),
    (str(PROJECT_ROOT / "config"), "default_config"),
]

# ---------------------------------------------------------------------------
# 隐藏导入与库自带数据
# ---------------------------------------------------------------------------
hiddenimports = []
binaries = []

# 这些库存在大量动态导入 / 数据文件，需要完整收集
for pkg in (
    "chromadb",
    "llama_index",
    "llama_index.core",
    "llama_index.embeddings.ollama",
    "llama_index.llms.ollama",
    "llama_index.readers.file",
    "llama_index.vector_stores.chroma",
):
    try:
        d, b, h = collect_all(pkg)
        datas += d
        binaries += b
        hiddenimports += h
    except Exception as exc:  # noqa: BLE001
        print(f"[spec] collect_all 跳过 {pkg}: {exc}")

# 仅收集子模块（避免体积过大或无数据文件）
for pkg in (
    "pymupdf",
    "fitz",
    "trafilatura",
    "bs4",
    "ddgs",
    "networkx",
    "posthog",
    "pystray",
    "PIL",
    "rich",
    "prompt_toolkit",
    "pypdf",
    "git",
):
    try:
        hiddenimports += collect_submodules(pkg)
    except Exception as exc:  # noqa: BLE001
        print(f"[spec] collect_submodules 跳过 {pkg}: {exc}")

# 项目自身：src 内模块以【顶层名】互相导入（from config import ...），
# 因此把 src 目录加入搜索路径，并以顶层模块名收集为 hiddenimports。
SRC_DIR = PROJECT_ROOT / "src"
for py in SRC_DIR.glob("*.py"):
    if py.stem == "__init__":
        continue
    hiddenimports.append(py.stem)
# src 下的子包（agents、code_analyzer 等）也以顶层名收集
# （SRC_DIR 已加入 sys.path，collect_submodules 可按顶层名解析）
for sub in SRC_DIR.iterdir():
    if sub.is_dir() and (sub / "__init__.py").exists():
        try:
            hiddenimports += collect_submodules(sub.name)
        except Exception as exc:  # noqa: BLE001
            print(f"[spec] collect_submodules 跳过 {sub.name}: {exc}")

# 部分 tokenizer / 配置数据
for pkg in ("tiktoken_ext", "tiktoken"):
    try:
        hiddenimports += collect_submodules(pkg)
        datas += collect_data_files(pkg)
    except Exception:  # noqa: BLE001
        pass

# ---------------------------------------------------------------------------
# 排除项：测试、OCR、构建工具等（控制体积）
# ---------------------------------------------------------------------------
excludes = [
    "pytest",
    "pytest_cov",
    "pytest_xdist",
    "_pytest",
    "pylint",
    "flake8",
    "bandit",
    "pip_audit",
    "pytesseract",
    "paddleocr",
    "paddlepaddle",
    "paddlex",
    "cv2",  # opencv，OCR 相关
    "tkinter",  # 未使用 GUI 工具包
    "matplotlib",
    "IPython",
    "jupyter",
]

# ---------------------------------------------------------------------------
# 图标
# ---------------------------------------------------------------------------
if sys.platform == "win32":
    app_icon = str(PROJECT_ROOT / "assets" / "icon.ico")
elif sys.platform == "darwin":
    app_icon = str(PROJECT_ROOT / "assets" / "icon.icns")
else:
    app_icon = str(PROJECT_ROOT / "assets" / "icon.png")

a = Analysis(
    [str(PROJECT_ROOT / "launcher.py")],
    pathex=[str(PROJECT_ROOT), str(PROJECT_ROOT / "src")],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)


# ---------------------------------------------------------------------------
# Windows: 为 exe 嵌入版本信息（文件属性 -> 详细信息 显示产品/文件版本）
# ---------------------------------------------------------------------------
def _build_win_version_info(version_str):
    from PyInstaller.utils.win32.versioninfo import (
        VSVersionInfo,
        FixedFileInfo,
        StringFileInfo,
        StringTable,
        StringStruct,
        VarFileInfo,
        VarStruct,
    )

    # 把 "1.0.1" 规整为 4 段整数元组 (1, 0, 1, 0)
    parts = []
    for token in version_str.split("."):
        digits = "".join(ch for ch in token if ch.isdigit())
        parts.append(int(digits) if digits else 0)
    while len(parts) < 4:
        parts.append(0)
    vtuple = tuple(parts[:4])

    return VSVersionInfo(
        ffi=FixedFileInfo(
            filevers=vtuple,
            prodvers=vtuple,
            mask=0x3F,
            flags=0x0,
            OS=0x40004,
            fileType=0x1,
            subtype=0x0,
            date=(0, 0),
        ),
        kids=[
            StringFileInfo([
                StringTable("040904B0", [
                    StringStruct("CompanyName", "Cerebro Open Source"),
                    StringStruct("FileDescription", "Cerebro - 本地 RAG + 代码助手"),
                    StringStruct("FileVersion", version_str),
                    StringStruct("ProductName", "Cerebro"),
                    StringStruct("ProductVersion", version_str),
                    StringStruct("OriginalFilename", "Cerebro.exe"),
                ]),
            ]),
            VarFileInfo([VarStruct("Translation", [0x0409, 0x04B0])]),
        ],
    )


exe_version = None
if sys.platform == "win32":
    try:
        exe_version = _build_win_version_info(APP_VERSION)
    except Exception as exc:  # noqa: BLE001
        print(f"[spec] 生成 Windows 版本信息失败，跳过: {exc}")

# 注：onedir 模式（非单文件），启动更快、对原生库兼容性更好。
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Cerebro",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,  # GUI 应用，不显示控制台窗口
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=app_icon,
    version=exe_version,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="Cerebro",
)

# ---------------------------------------------------------------------------
# macOS：额外生成 .app bundle
# ---------------------------------------------------------------------------
if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="Cerebro.app",
        icon=app_icon,
        bundle_identifier="com.cerebro.assistant",
        info_plist={
            "CFBundleName": "Cerebro",
            "CFBundleDisplayName": "Cerebro",
            "CFBundleShortVersionString": APP_VERSION,
            "CFBundleVersion": APP_VERSION,
            "NSHighResolutionCapable": True,
            # 托盘应用：作为后台代理运行，不在 Dock 显示主窗口
            "LSUIElement": True,
        },
    )
