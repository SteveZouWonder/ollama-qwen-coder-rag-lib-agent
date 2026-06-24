#!/usr/bin/env python3
"""运行时路径解析工具。

集中处理"源码运行"与"PyInstaller 打包运行"两种场景下的路径差异：

- 源码运行时：以项目根目录为基准。
- PyInstaller 打包运行时：
    * 只读资源（assets/、打包进去的默认 config）位于 ``sys._MEIPASS``；
    * 用户可写数据（运行时生成的 config/app_config.json、logs/）位于用户数据目录，
      避免写入只读的应用安装目录。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def is_frozen() -> bool:
    """是否运行在 PyInstaller 打包环境中。"""
    return getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS")


def resource_root() -> Path:
    """只读资源根目录（assets、打包内置的默认配置）。"""
    if is_frozen():
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    # 源码运行：本文件位于 <root>/src/，根目录上一层
    return Path(__file__).resolve().parent.parent


def assets_dir() -> Path:
    """图标等资源目录。"""
    return resource_root() / "assets"


def user_data_dir() -> Path:
    """用户可写数据目录（配置、日志、索引等）。

    - 源码运行：直接使用项目根目录，保持原有行为不变。
    - 打包运行：使用各平台标准用户数据目录下的 Cerebro 子目录。
    """
    if not is_frozen():
        return resource_root()

    app_name = "Cerebro"
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        path = Path(base) / app_name
    elif sys.platform == "darwin":
        path = Path.home() / "Library" / "Application Support" / app_name
    else:  # linux 等
        base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
        path = Path(base) / app_name

    path.mkdir(parents=True, exist_ok=True)
    return path


def config_dir() -> Path:
    """配置目录（可写）。"""
    d = user_data_dir() / "config"
    d.mkdir(parents=True, exist_ok=True)
    return d


def home_file(name: str) -> Path:
    """家目录级配置/数据文件的路径。

    - 源码运行：保持原有行为，落在用户家目录 ``~/<name>``。
    - 打包运行：收纳到用户数据目录 ``<user_data>/<name>``，避免污染家目录根。

    参数 ``name`` 形如 ``.code_agent_history.json`` 或 ``.code_agent_sessions``。
    """
    if is_frozen():
        return user_data_dir() / name
    return Path.home() / name


def cwd_data_dir(relative: str) -> Path:
    """默认落在当前工作目录的产物路径（如 ``.devin/...``）。

    - 源码运行：保持原有行为，相对当前工作目录解析。
    - 打包运行：收纳到用户数据目录下，避免写入 Finder 启动时不可控/只读的 cwd。

    参数 ``relative`` 形如 ``.devin/knowledge/snapshots``。
    """
    if is_frozen():
        return user_data_dir() / relative
    return Path(relative)


def logs_dir() -> Path:
    """日志目录（可写）。"""
    d = user_data_dir() / "logs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def bundled_default_config() -> Path:
    """打包内置的默认配置文件路径（只读）。

    打包目标目录为 default_config（避免与顶层模块 config.py 冲突），
    源码运行时仍为项目内 config/。
    """
    if is_frozen():
        return resource_root() / "default_config" / "app_config.json"
    return resource_root() / "config" / "app_config.json"
