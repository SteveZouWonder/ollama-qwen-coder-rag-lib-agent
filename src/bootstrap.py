#!/usr/bin/env python3
"""Ollama 环境检测与引导安装。

应用首次/每次启动时调用 :func:`ensure_ollama_ready`：

1. 检测本机是否安装 Ollama（``ollama`` 命令是否存在）。
2. 检测 Ollama 服务是否在运行（HTTP 探测 ``/api/tags``）。
3. 检测所需模型是否已拉取，缺失则引导拉取。

所有"下载/安装第三方软件或模型"的动作都需要用户**明确确认**，
不会静默执行，避免安全与权限问题。

跨平台：
- macOS / Linux：使用官方一键脚本 ``curl -fsSL https://ollama.com/install.sh | sh``。
- Windows：下载并运行官方安装器 OllamaSetup.exe。

本模块尽量不引入额外依赖；HTTP 探测优先用 requests，回退到 urllib。
"""
from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
import time
from typing import List, Optional

OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_INSTALL_SH = "https://ollama.com/install.sh"
OLLAMA_DOWNLOAD_PAGE = "https://ollama.com/download"
OLLAMA_WINDOWS_INSTALLER = "https://ollama.com/download/OllamaSetup.exe"

# 默认需要的模型（与 config/app_config.json 保持一致）
DEFAULT_REQUIRED_MODELS = [
    "qwen2.5-coder:7b",
    "nomic-embed-text:latest",
]


# ---------------------------------------------------------------------------
# 基础检测
# ---------------------------------------------------------------------------
# 常见安装路径。Finder/`open` 启动的 GUI 应用 PATH 极简（通常只有
# /usr/bin:/bin:/usr/sbin:/sbin），shutil.which 找不到这些目录中的 ollama，
# 因此需要显式补充搜索。
_COMMON_OLLAMA_PATHS = [
    "/usr/local/bin/ollama",
    "/opt/homebrew/bin/ollama",
    "/usr/bin/ollama",
    "/Applications/Ollama.app/Contents/Resources/ollama",
    os.path.expanduser("~/.ollama/bin/ollama"),
    os.path.expanduser("~/AppData/Local/Programs/Ollama/ollama.exe"),
    "C:\\Program Files\\Ollama\\ollama.exe",
]


def find_ollama_executable() -> Optional[str]:
    """返回 ollama 可执行文件的完整路径，找不到返回 None。

    先查 PATH（shutil.which），再回退到常见安装路径，
    以兼容 GUI 启动时 PATH 不完整的情况。
    """
    found = shutil.which("ollama")
    if found:
        return found
    for p in _COMMON_OLLAMA_PATHS:
        if p and os.path.isfile(p) and os.access(p, os.X_OK):
            return p
    return None


def ollama_installed() -> bool:
    """``ollama`` 是否已安装（PATH 或常见安装路径）。"""
    return find_ollama_executable() is not None


def ollama_running(timeout: float = 2.0) -> bool:
    """Ollama 服务是否在运行。"""
    url = f"{OLLAMA_BASE_URL}/api/tags"
    try:
        import requests  # 项目已依赖

        resp = requests.get(url, timeout=timeout)
        return resp.status_code == 200
    except Exception:  # noqa: BLE001 回退到标准库
        try:
            import urllib.request

            with urllib.request.urlopen(url, timeout=timeout) as resp:  # nosec B310
                return resp.status == 200
        except Exception:  # noqa: BLE001
            return False


def list_installed_models(timeout: float = 3.0) -> List[str]:
    """返回已安装模型名列表（失败返回空列表）。"""
    url = f"{OLLAMA_BASE_URL}/api/tags"
    try:
        import requests

        resp = requests.get(url, timeout=timeout)
        if resp.status_code != 200:
            return []
        data = resp.json()
    except Exception:  # noqa: BLE001
        try:
            import json
            import urllib.request

            with urllib.request.urlopen(url, timeout=timeout) as resp:  # nosec B310
                data = json.loads(resp.read().decode("utf-8"))
        except Exception:  # noqa: BLE001
            return []
    return [m.get("name", "") for m in data.get("models", [])]


def missing_models(required: Optional[List[str]] = None) -> List[str]:
    """返回缺失的所需模型列表。"""
    required = required or DEFAULT_REQUIRED_MODELS
    installed = list_installed_models()
    if not installed:
        return list(required)
    missing = []
    for need in required:
        # 允许 tag 宽松匹配：need 不含冒号时匹配前缀
        if any(name == need or name.startswith(need.split(":")[0] + ":") for name in installed):
            continue
        missing.append(need)
    return missing


# ---------------------------------------------------------------------------
# 交互辅助
# ---------------------------------------------------------------------------
def _confirm(prompt: str, default: bool = True) -> bool:
    """命令行 yes/no 确认。非交互式环境返回 default。"""
    if not sys.stdin or not sys.stdin.isatty():
        return default
    suffix = " [Y/n] " if default else " [y/N] "
    try:
        ans = input(prompt + suffix).strip().lower()
    except (EOFError, KeyboardInterrupt):
        return False
    if not ans:
        return default
    return ans in ("y", "yes")


def _open_url(url: str) -> None:
    """用系统默认浏览器打开 URL。"""
    try:
        import webbrowser

        webbrowser.open(url)
    except Exception:  # noqa: BLE001
        print(f"请手动访问：{url}")


# ---------------------------------------------------------------------------
# 安装 Ollama
# ---------------------------------------------------------------------------
def install_ollama(interactive: bool = True) -> bool:
    """引导安装 Ollama。返回是否已安装成功。"""
    system = platform.system()

    print("=" * 56)
    print("  未检测到 Ollama —— Cerebro 需要它来运行本地大模型")
    print("=" * 56)

    if system in ("Darwin", "Linux"):
        if interactive and not _confirm(
            "是否使用官方脚本自动安装 Ollama？(需要网络，可能请求管理员权限)"
        ):
            print(f"已取消自动安装。请手动安装：{OLLAMA_DOWNLOAD_PAGE}")
            _open_url(OLLAMA_DOWNLOAD_PAGE)
            return False
        try:
            print("正在下载并运行官方安装脚本……")
            # curl -fsSL https://ollama.com/install.sh | sh
            curl = subprocess.Popen(
                ["curl", "-fsSL", OLLAMA_INSTALL_SH],
                stdout=subprocess.PIPE,
            )
            sh = subprocess.Popen(["sh"], stdin=curl.stdout)
            if curl.stdout:
                curl.stdout.close()
            sh.communicate()
            ok = sh.returncode == 0 and ollama_installed()
            if ok:
                print("Ollama 安装完成。")
            else:
                print("自动安装未成功，请手动安装：" + OLLAMA_DOWNLOAD_PAGE)
                _open_url(OLLAMA_DOWNLOAD_PAGE)
            return ok
        except FileNotFoundError:
            print("未找到 curl，请手动安装 Ollama：" + OLLAMA_DOWNLOAD_PAGE)
            _open_url(OLLAMA_DOWNLOAD_PAGE)
            return False

    if system == "Windows":
        if interactive and not _confirm(
            "是否下载并运行 Ollama 官方安装器？"
        ):
            print(f"已取消。请手动安装：{OLLAMA_DOWNLOAD_PAGE}")
            _open_url(OLLAMA_DOWNLOAD_PAGE)
            return False
        try:
            import tempfile
            import urllib.request

            tmp = os.path.join(tempfile.gettempdir(), "OllamaSetup.exe")
            print("正在下载安装器……")
            urllib.request.urlretrieve(OLLAMA_WINDOWS_INSTALLER, tmp)  # nosec B310
            print("启动安装器，请按提示完成安装……")
            # 运行官方安装器（交互式）
            subprocess.run([tmp], check=False)
            ok = ollama_installed()
            if not ok:
                print("安装器已退出，但仍未检测到 Ollama，请确认安装是否完成。")
            return ok
        except Exception as exc:  # noqa: BLE001
            print(f"下载/安装失败：{exc}")
            print("请手动安装：" + OLLAMA_DOWNLOAD_PAGE)
            _open_url(OLLAMA_DOWNLOAD_PAGE)
            return False

    print(f"未识别的系统 {system}，请手动安装：{OLLAMA_DOWNLOAD_PAGE}")
    _open_url(OLLAMA_DOWNLOAD_PAGE)
    return False


def start_ollama_service() -> bool:
    """尝试在后台启动 Ollama 服务，并等待其就绪。"""
    exe = find_ollama_executable()
    if not exe:
        return False
    try:
        creationflags = 0
        if platform.system() == "Windows":
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        subprocess.Popen(
            [exe, "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            creationflags=creationflags,
        )
    except Exception:  # noqa: BLE001
        return False
    # 等待最多 ~10s
    for _ in range(20):
        if ollama_running():
            return True
        time.sleep(0.5)
    return ollama_running()


# ---------------------------------------------------------------------------
# 拉取模型
# ---------------------------------------------------------------------------
def pull_models(models: List[str], interactive: bool = True) -> bool:
    """引导拉取缺失模型。返回是否全部就绪。"""
    if not models:
        return True
    print("=" * 56)
    print("  以下所需模型尚未拉取：")
    for m in models:
        print(f"    - {m}")
    print("=" * 56)
    if interactive and not _confirm("是否现在拉取这些模型？(可能较大，需要时间)"):
        print("已跳过。可稍后手动执行：")
        for m in models:
            print(f"    ollama pull {m}")
        return False

    exe = find_ollama_executable() or "ollama"
    all_ok = True
    for m in models:
        print(f"正在拉取 {m} ……")
        try:
            ret = subprocess.run([exe, "pull", m], check=False)
            if ret.returncode != 0:
                all_ok = False
                print(f"拉取 {m} 失败，可稍后手动执行：ollama pull {m}")
        except FileNotFoundError:
            print("未找到 ollama 命令。")
            return False
    return all_ok


# ---------------------------------------------------------------------------
# 总入口
# ---------------------------------------------------------------------------
def ensure_ollama_ready(
    interactive: bool = True,
    required_models: Optional[List[str]] = None,
    auto_pull_models: bool = True,
    notify=None,
) -> bool:
    """确保 Ollama 已安装、服务在运行、所需模型已就绪。

    参数:
        interactive: 是否交互式（可调用 input、可自动安装第三方软件）。
            GUI/无终端场景应传 False —— 此时**不会**静默安装第三方软件或
            拉取大模型，只做检测并通过 ``notify`` 提示用户。
        notify: 可选回调 ``notify(title, message)``，用于在 GUI 下弹通知。

    返回 True 表示环境就绪；False 表示仍有缺失（不会抛异常阻断启动）。
    """
    required_models = required_models or DEFAULT_REQUIRED_MODELS

    def _notify(title: str, message: str) -> None:
        if callable(notify):
            try:
                notify(title, message)
            except Exception:  # noqa: BLE001
                pass
        print(f"[Cerebro] {title}: {message}")

    # 0) 服务已在运行 —— 最强信号：Ollama 必然已安装且就绪，直接进入模型检查。
    #    （优先于"命令是否存在"的判断，避免 GUI 下 PATH 不全导致误判未安装）
    if ollama_running():
        pass
    else:
        # 1) 安装检测（PATH + 常见安装路径）
        if not ollama_installed():
            if not interactive:
                # 非交互（GUI）：不静默安装第三方软件，仅提示用户手动安装。
                _notify(
                    "需要安装 Ollama",
                    "未检测到 Ollama。请访问 https://ollama.com/download 安装后重启 Cerebro。",
                )
                return False
            installed = install_ollama(interactive=interactive)
            if not installed:
                print("[Cerebro] Ollama 尚未就绪，部分功能将不可用。")
                return False

        # 2) 服务（已安装但未运行）：尝试启动，风险低，交互与否都可执行
        print("[Cerebro] Ollama 服务未运行，尝试启动……")
        if not start_ollama_service():
            _notify(
                "Ollama 服务未运行",
                "无法自动启动 Ollama 服务，请手动运行：ollama serve",
            )
            return False

    # 3) 模型
    if auto_pull_models:
        missing = missing_models(required_models)
        if missing:
            if not interactive:
                # 非交互：不自动拉取（可能很大），仅提示。
                _notify(
                    "缺少所需模型",
                    "请执行：" + "；".join(f"ollama pull {m}" for m in missing),
                )
            else:
                pull_models(missing, interactive=interactive)

    return True


if __name__ == "__main__":
    ok = ensure_ollama_ready(interactive=True)
    print("环境就绪" if ok else "环境未完全就绪")
    sys.exit(0 if ok else 1)
