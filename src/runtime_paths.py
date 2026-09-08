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
    """App 可写数据/产物的绝对路径（如 ``index_storage``）。

    统一以“App 数据目录”为基准，与运行时当前工作目录（cwd）彻底解耦：

    - 源码运行：基准为项目根（``user_data_dir()`` 在源码下即项目根，绝对路径）。
    - 打包运行：基准为用户数据目录（``<App 数据>/``）。

    这保证了 App 自身数据（向量库、快照、图谱、文件元数据、生成的 skills 等）
    写入位置始终稳定；即使用户通过 ``/cd`` 切换了工作目录，或从非项目根启动，
    数据也不会漂移到别处（历史 bug：读取端相对 cwd、写入端绝对路径导致读到空库）。

    注意：函数名保留 ``cwd_data_dir`` 仅为兼容既有调用点，其语义已不再相对 cwd。
    App 自身的运行时状态（快照 / 图谱 / 文件元数据）请用 :func:`app_state_dir`。
    """
    return user_data_dir() / relative


# App 运行时状态目录名（快照、知识图谱、文件元数据等由程序生成的数据）。
# 历史上位于 ``.devin/``（Devin 时代的遗留命名），现统一为产品名的隐藏目录。
APP_STATE_DIRNAME = ".cerebro"
LEGACY_STATE_DIRNAME = ".devin"

# 测试隔离用：非空时 app_state_dir 以此为根（跳过迁移），避免测试写入真实 .cerebro/。
_APP_STATE_ROOT_OVERRIDE: Path | None = None


def set_app_state_root(path) -> None:
    """覆盖 App 运行时状态根目录（``None`` 恢复默认）。仅供测试 / 诊断使用。"""
    global _APP_STATE_ROOT_OVERRIDE
    _APP_STATE_ROOT_OVERRIDE = Path(path) if path else None


def app_state_dir(relative: str = "") -> Path:
    """App 运行时状态的绝对路径：``<App 数据目录>/.cerebro/<relative>``。

    - ``relative`` 形如 ``knowledge/snapshots``、``file_metadata``；为空返回目录根。
    - **一次性迁移**：若目标不存在而旧位置 ``<App 数据目录>/.devin/<relative>`` 存在，
      则把旧目录/文件整体移动到新位置（不覆盖已有数据），保证升级后既有的快照、
      图谱、元数据不会"消失"。迁移失败只记录日志，不影响启动。
    """
    if _APP_STATE_ROOT_OVERRIDE is not None:
        return _APP_STATE_ROOT_OVERRIDE / relative if relative else _APP_STATE_ROOT_OVERRIDE
    base = user_data_dir()
    target = base / APP_STATE_DIRNAME / relative if relative else base / APP_STATE_DIRNAME
    if relative:
        _migrate_legacy_state(base / LEGACY_STATE_DIRNAME / relative, target)
    return target


def _migrate_legacy_state(old: Path, new: Path) -> bool:
    """把 ``old`` 移到 ``new``（仅当 new 不存在且 old 存在）。返回是否发生了迁移。"""
    try:
        if new.exists() or not old.exists():
            return False
        new.parent.mkdir(parents=True, exist_ok=True)
        import shutil
        shutil.move(str(old), str(new))
        import logging
        logging.getLogger(__name__).info("已迁移运行时数据: %s -> %s", old, new)
        return True
    except Exception as exc:  # noqa: BLE001
        import logging
        logging.getLogger(__name__).warning("迁移运行时数据失败 %s -> %s: %s", old, new, exc)
        return False


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
