"""命令推荐系统与会话上下文辅助（F10 P3-2-b 由 ``query_interface`` 外迁）。

``record_command_execution`` 被引擎耦合命令大量调用；测试打桩目标应是**调用方模块**
（如 ``cli.engine_commands.record_command_execution``），而非本模块。
"""
import logging

import rag_pipeline
from cli import state

logger = logging.getLogger(__name__)


# ==================== 命令推荐系统辅助函数 ====================

def show_command_recommendations():
    """显示命令推荐"""
    logger.debug(f"show_command_recommendations 调用: command_recommender={state.command_recommender}")
    
    if not state.command_recommender:
        logger.debug("command_recommender 为 None")
        return
    
    if not state.command_recommender.is_enabled():
        logger.debug("command_recommender 已禁用")
        return
    
    try:
        recommendations = state.command_recommender.get_recommendations()
        logger.debug(f"获得 {len(recommendations) if recommendations else 0} 个推荐")
        
        if recommendations:
            # 默认使用紧凑单行模式，减少视觉噪音
            formatted = state.command_recommender.format_recommendations(
                recommendations, use_rich=state.HAS_RICH, compact=True
            )
            if formatted:
                state.console.print(formatted)
    except Exception as e:
        logger.error(f"推荐系统错误: {e}")
        state.console.print(f"[dim]⚠️  推荐系统错误: {e}[/dim]", style="dim")

def record_command_execution(cmd_type: str, args: str = "", result: str = "", error: str = ""):
    """记录命令执行到推荐系统"""
    logger.debug(f"record_command_execution: cmd_type={cmd_type}, args={args!r}")
    
    if not state.command_recommender:
        logger.debug(f"command_recommender 为 None，无法记录命令: {cmd_type}")
        return
    
    try:
        # 截断过长的参数，避免污染历史/上下文（如网络搜索结果正文）
        safe_args = args if len(args) <= 200 else args[:200] + "…"
        # 记录命令
        state.command_recommender.record_command(f"/{cmd_type}", safe_args, result)
        logger.debug(f"命令已记录: /{cmd_type}")
        
        # 记录错误（如果有）
        if error:
            state.command_recommender.record_error(error)
            logger.debug(f"错误已记录: {error}")
        
        # 更新RAG状态（可能变化）
        if state.rag_engine:
            rag_available = state.rag_engine.retriever is not None
            rag_empty = rag_available and (state.rag_engine.get_stats().get("total_chunks", 0) == 0)
            state.command_recommender.update_rag_status(rag_available, rag_empty)
            logger.debug(f"RAG状态已更新: available={rag_available}, empty={rag_empty}")
        
    except Exception as e:
        logger.error(f"记录命令失败: {e}")


def record_conversation(user_content: str, assistant_content: str, **kwargs):
    """将一轮对话写入"当前会话"，委托共享层 rag_pipeline.record_conversation。

    可选 ``rewritten`` / ``trace`` / ``progress`` 透传给会话上下文层（自动压缩时
    的进度事件经 ``progress`` 渲染到终端）。
    """
    rag_pipeline.record_conversation(user_content, assistant_content, **kwargs)


def _conversation():
    """进程内共享的会话上下文（跟随"当前会话"）。"""
    from conversation_context import get_conversation_context
    return get_conversation_context()


def _print_health_hint(pre: dict, question: str = ""):
    """回答后按上下文健康度打印一行 dim 提示（每会话只提示一次）。"""
    try:
        from conversation_context import merge_health, format_suggest_hint
        conv = _conversation()
        health = merge_health(pre or {}, conv.health())
        hint = format_suggest_hint(health)
        if hint:
            state.console.print(f"[dim]{hint}，输入 /session-new（可加 --carry 携带摘要）[/dim]")
            conv.mark_suggested()
    except Exception as e:  # noqa: BLE001 - 提示失败不影响主流程
        logger.debug(f"health hint failed: {e}")


def _health_before(question: str) -> dict:
    """提问前的健康度快照（用于判断空闲/话题漂移）。"""
    try:
        return _conversation().health(question)
    except Exception:  # noqa: BLE001
        return {}
