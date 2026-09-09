"""帮助 / 教程 / 工具清单 / 运行配置命令：``/help`` ``/tutorial`` ``/tools`` ``/config``。"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


# ==================== 帮助 / 教程 / 工具 ====================

def handle_help(ctx, parsed):
    ctx.print_help()
    ctx.record_command("help")
    return True


def handle_tutorial(ctx, parsed):
    ctx.show_tutorial()
    ctx.record_command("tutorial")
    return True


def handle_tools(ctx, parsed):
    ctx.print_tools()
    ctx.record_command("tools")
    return True


def config_rows() -> list[tuple[str, str]]:
    """``/config`` 展示的运行配置行（``(标签, 值)``），与 Web「系统 → 运行环境」同源。

    纯函数，便于单测；路径边界两项是 F10 P0-1-d 的核心：越界报错时用户能自查允许范围。
    """
    import os

    import config as cfg
    from config import Config

    # 目录多时（已入库文档目录会累积）只列前几个，避免刷屏
    max_shown = 6

    def _dirs(dirs, env_name: str) -> str:
        items = [str(d) for d in (dirs or []) if str(d).strip()]
        if not items:
            return f"—（可设置 {env_name} 放行）"
        text = " : ".join(items[:max_shown])
        if len(items) > max_shown:
            text += f" …（共 {len(items)} 个）"
        return text

    try:
        from agent_tools import read_allowed_dirs, write_allowed_dirs
        read_dirs, write_dirs = read_allowed_dirs(), write_allowed_dirs()
    except Exception:  # noqa: BLE001
        read_dirs, write_dirs = [], []

    auto = "开（只放行 low / medium，high 仍需确认）" if Config.AUTO_CONFIRM else "关"
    try:
        from llm_client import describe_backend
        backend = describe_backend()
    except Exception:  # noqa: BLE001
        backend = {"provider": "ollama", "base_url": str(Config.OLLAMA_HOST), "api_key_set": False}
    provider = backend.get("provider", "ollama")
    rows = [
        ("模型", str(Config.LLM_MODEL)),
        ("LLM 后端", provider + ("" if provider == "ollama" else "（OpenAI 兼容；num_ctx 由后端决定）")),
        ("后端地址", str(backend.get("base_url") or Config.OLLAMA_HOST)),
    ]
    if provider != "ollama":
        rows.append(("API Key", "已设置" if backend.get("api_key_set") else "未设置（本地服务通常无需）"))
        rows.append(("Ollama 地址（嵌入模型）", str(Config.OLLAMA_HOST)))
    # F10 P2-1-d：进程内 LLM 请求并发上限
    limit = backend.get("max_concurrency", getattr(Config, "OLLAMA_MAX_CONCURRENCY", 2))
    try:
        limit = int(limit)
    except (TypeError, ValueError):
        limit = 0
    rows.append(("LLM 并发上限", "不限制" if limit <= 0 else f"{limit}（多 Agent 并行时其余请求排队，可调 OLLAMA_MAX_CONCURRENCY）"))
    return rows + [
        ("自动确认", auto),
        ("自动路由", "开" if getattr(Config, "AUTO_ROUTE", False) else "关"),
        ("工作目录", os.getcwd()),
        ("允许读目录", _dirs(read_dirs, "READ_ALLOWED_DIRS")),
        ("允许写目录", _dirs(write_dirs, "WRITE_ALLOWED_DIRS")),
        ("数据目录", str(getattr(cfg, "DATA_DIR", "") or "")),
        ("索引目录", str(getattr(cfg, "INDEX_DIR", "") or "")),
        ("Agent 最大步数 / 超时", f"{Config.MAX_ITERATIONS} / {Config.TIMEOUT}s"),
    ]


def handle_config(ctx, parsed):
    """``/config`` 显示当前运行配置（含读 / 写路径边界）。"""
    console = ctx.console
    for label, value in config_rows():
        console.print(f"{label}: {value}")
    console.print("提示: 路径边界越界时工具返回 [错误] 路径超出允许范围，"
                  "可用 READ_ALLOWED_DIRS / WRITE_ALLOWED_DIRS 放行", style="dim")
    ctx.record_command("config")
    return True
