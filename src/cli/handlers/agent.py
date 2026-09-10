"""多 Agent 协作命令：``/multi``。"""
from __future__ import annotations

import logging

from .base import LiveAnswer

logger = logging.getLogger(__name__)


# ==================== 多 Agent 协作 ====================

_MULTI_MODES = ("hierarchy", "parallel", "sequential", "competitive")


def parse_multi_args(arg: str) -> tuple[str, str | None]:
    """解析 ``/multi <任务> [--mode xxx]``，返回 ``(任务文本, 模式或 None)``。

    ``--mode`` 可出现在任意位置；非法模式按 None（编排器默认）处理并由调用方提示。
    """
    import re

    text = arg or ""
    mode = None
    m = re.search(r"(?:^|\s)--mode(?:=|\s+)(\S+)", text)
    if m:
        mode = m.group(1).strip().lower()
        text = (text[: m.start()] + " " + text[m.end():]).strip()
    return re.sub(r"\s{2,}", " ", text).strip(), mode


def _default_orchestrator():
    from agent_config import AgentConfigManager
    from agent_orchestrator import AgentOrchestrator

    return AgentOrchestrator(AgentConfigManager.get_default_config())


def handle_multi(ctx, parsed):
    """``/multi <任务> [--mode hierarchy|parallel|sequential|competitive]``：
    多 Agent 协作，实时打印"分解 → 调度 → 执行 → 整合"进度，输出与 Web 一致。"""
    console = ctx.console
    task, mode = parse_multi_args(getattr(parsed, "arg", ""))
    if not task:
        console.print("用法: /multi <任务> [--mode hierarchy|parallel|sequential|competitive]", style="yellow")
        return False
    if mode is not None and mode not in _MULTI_MODES:
        console.print(f"⚠️ 未知模式 {mode}，可选: {', '.join(_MULTI_MODES)}；改用编排器默认模式", style="yellow")
        mode = None

    # 保证知识库引擎已注入全局工具表，RAGAgent 才能真正检索
    if ctx.rag_engine is not None:
        try:
            import agent_tools
            agent_tools.set_rag_engine(ctx.rag_engine)
        except Exception:  # noqa: BLE001
            pass

    try:
        from agents.agent_types import CollaborationMode
        resolved = CollaborationMode(mode) if mode else None
    except Exception:  # noqa: BLE001
        resolved = None

    context = None
    try:
        from conversation_context import get_conversation_context
        context = get_conversation_context()
    except Exception:  # noqa: BLE001
        context = None

    def progress(evt):
        msg = evt.get("message", "")
        if not msg or evt.get("transient"):
            return
        stage = evt.get("stage", "")
        style = "dim" if stage in ("agent_step", "schedule") else "cyan"
        console.print(f"  {msg}", style=style)

    factory = ctx.orchestrator_factory or _default_orchestrator
    orchestrator = factory()
    # F10 P1-1：仅整合阶段（模型综合最终回答）逐 token 刷新实时面板
    live = LiveAnswer(console, ctx.has_rich, title="综合回答")
    try:
        console.print(f"🤝 多 Agent 协作（模式: {mode or '默认'}）…", style="bold cyan")
        kwargs = {"progress": progress, "on_token": live.on_token}
        if context is not None:
            kwargs["context"] = context
        result = orchestrator.process_request(task, resolved, **kwargs)
    except KeyboardInterrupt:
        live.finish()
        console.print("\n已中断：用户中断，协作已停止。", style="yellow")
        return False
    except Exception as e:  # noqa: BLE001
        live.finish()
        console.print(f"❌ 协作执行失败: {e}", style="red")
        return False
    finally:
        live.finish()
        shutdown = getattr(orchestrator, "shutdown", None)
        if callable(shutdown):
            try:
                shutdown()
            except Exception:  # noqa: BLE001
                pass

    if not isinstance(result, dict):
        result = {"success": False, "summary": str(result)}

    from collaboration.presenter import format_multi_agent_result

    rendered = format_multi_agent_result(result)
    if ctx.has_rich:
        try:
            from rich.markdown import Markdown
            console.print(Markdown(rendered))
        except Exception:  # noqa: BLE001
            console.print(rendered)
    else:
        console.print(rendered)

    answer = str(result.get("answer") or "").strip() or str(result.get("summary", ""))
    recorded = answer if result.get("success") else f"[协作失败] {answer}"
    try:
        ctx.record_conversation(task, recorded)
    except Exception:  # noqa: BLE001
        pass
    ctx.record_command("multi", task, "success" if result.get("success") else "failed")
    return True
