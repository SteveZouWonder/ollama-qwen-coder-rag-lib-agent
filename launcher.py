#!/usr/bin/env python3
"""Cerebro 统一启动入口（用于 PyInstaller 打包）。

一个可执行体内同时提供两种使用方式：

    Cerebro                 # 默认：启动桌面托盘应用（GUI）
    Cerebro --gui           # 同上，显式启动托盘
    Cerebro --cli           # 启动命令行交互界面（RAG / ReAct Agent）
    Cerebro chat            # --cli 的别名
    Cerebro --skip-bootstrap  # 跳过 Ollama 检测引导（调试用）

启动时会先运行 Ollama 环境检测与引导（src/bootstrap.py），
未安装时会提示用户安装，未拉取模型时会引导拉取。
"""
from __future__ import annotations

import os
import sys


def _ensure_src_on_path() -> None:
    """确保 src 包可被导入（源码运行与打包运行均适用）。"""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        base = sys._MEIPASS  # type: ignore[attr-defined]
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    if base not in sys.path:
        sys.path.insert(0, base)
    src_dir = os.path.join(base, "src")
    if os.path.isdir(src_dir) and src_dir not in sys.path:
        sys.path.insert(0, src_dir)


def main() -> int:
    _ensure_src_on_path()

    argv = sys.argv[1:]

    # 解析启动器自身的标志，其余参数透传给目标入口
    skip_bootstrap = "--skip-bootstrap" in argv
    argv = [a for a in argv if a != "--skip-bootstrap"]

    want_cli = "--cli" in argv or "chat" in argv
    argv = [a for a in argv if a not in ("--cli", "--gui", "chat")]

    # Ollama 环境检测与引导
    if not skip_bootstrap:
        try:
            from bootstrap import ensure_ollama_ready  # 顶层名（打包/源码 src 在 path）
        except ImportError:
            from src.bootstrap import ensure_ollama_ready
        try:
            ensure_ollama_ready(interactive=True)
        except Exception as exc:  # noqa: BLE001
            # 引导失败不应阻断启动，仅提示
            print(f"[Cerebro] Ollama 环境检测出现问题：{exc}", file=sys.stderr)

    # 透传剩余参数给目标入口
    sys.argv = [sys.argv[0]] + argv

    if want_cli:
        try:
            from query_interface import main as cli_main
        except ImportError:
            from src.query_interface import main as cli_main
        cli_main()
    else:
        try:
            from desktop_app import main as gui_main
        except ImportError:
            from src.desktop_app import main as gui_main
        gui_main()

    return 0


if __name__ == "__main__":
    sys.exit(main())
