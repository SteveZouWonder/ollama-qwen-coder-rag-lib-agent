"""会话管理命令：``/session-*`` ``/context`` ``/compact``。"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


# ==================== 会话管理命令 ====================

def _get_session_manager():
    from session_manager import get_session_manager
    from config import SESSION_STORAGE_PATH
    return get_session_manager(str(SESSION_STORAGE_PATH))


def _get_conversation_context():
    from conversation_context import get_conversation_context
    return get_conversation_context()


def _parse_session_new_args(arg: str):
    """解析 ``/session-new [--carry] [title]``，返回 ``(title|None, carry)``。"""
    tokens = (arg or "").split()
    carry = False
    rest = []
    for tok in tokens:
        if tok in ("--carry", "-c"):
            carry = True
        else:
            rest.append(tok)
    title = " ".join(rest).strip() or None
    return title, carry


def handle_session_new(ctx, parsed):
    console = ctx.console
    title, carry = _parse_session_new_args(parsed.arg)
    try:
        carried = ""
        if carry:
            # 携带摘要：只把当前会话「已折叠的滚动摘要」作为新会话的首条背景
            conv = _get_conversation_context()
            session = conv.new_session(title=title, carry_summary=True)
            carried = conv.carried_summary()
        else:
            manager = _get_session_manager()
            session = manager.create_session(title=title)
        console.print(f"✅ 新会话已创建: {session.session_id}", style="green")
        console.print(f"📋 标题: {session.title}", style="dim")
        console.print(f"📅 创建时间: {session.created_at.strftime('%Y-%m-%d %H:%M:%S')}", style="dim")
        if carry and carried:
            preview = carried if len(carried) <= 120 else carried[:120] + "…"
            console.print(f"🧳 已承接上一会话的滚动摘要: {preview}", style="dim")
        elif carry:
            console.print("🧳 上一会话尚无滚动摘要，未承接任何内容（新会话为空）", style="dim")
        ctx.record_command("session_new", session.title if session.title else "")
    except Exception as e:  # noqa: BLE001
        console.print(f"❌ 创建会话失败: {e}", style="red")
        ctx.record_command("session_new", "", "failed", str(e))
    return True


def handle_context(ctx, parsed):
    """``/context``：显示当前会话上下文的轮数/估算 token/预算/压缩次数/摘要预览。"""
    console = ctx.console
    try:
        from conversation_context import format_tokens
        m = _get_conversation_context().metrics()
        if not m.get("session_id"):
            console.print("📭 当前没有会话，提问后会自动创建", style="yellow")
            return True
        console.print("🧠 当前会话上下文:", style="cyan")
        console.print(f"🆔 会话: {m['session_id'][:8]}... {m.get('title', '')}", style="dim")
        console.print(f"💬 轮数: {m['turns']}（未折叠）/ 共 {m['messages']} 条消息", style="dim")
        console.print(
            f"📏 估算 token: {format_tokens(m['history_tokens'])} / 预算 {format_tokens(m['budget'])}"
            f"（{m['usage_ratio'] * 100:.0f}%，num_ctx={m['num_ctx']}）",
            style="dim",
        )
        console.print(f"🗜️ 压缩次数: {m['compressions']}", style="dim")
        summary = (m.get("summary") or "").strip()
        if summary:
            preview = summary if len(summary) <= 200 else summary[:200] + "…"
            console.print(f"📝 滚动摘要（{format_tokens(m['summary_tokens'])} tokens）: {preview}", style="dim")
        else:
            console.print("📝 滚动摘要: （无）", style="dim")
        ctx.record_command("context")
    except Exception as e:  # noqa: BLE001
        console.print(f"❌ 获取上下文信息失败: {e}", style="red")
        ctx.record_command("context", "", "failed", str(e))
    return True


def handle_compact(ctx, parsed):
    """``/compact``：手动把最近 K 轮之前的历史折叠进滚动摘要。"""
    console = ctx.console
    try:
        conv = _get_conversation_context()
        if not conv.has_history():
            console.print("📭 当前会话没有可压缩的历史", style="yellow")
            return True
        console.print("🗜️ 正在压缩会话历史...", style="cyan")
        result = conv.compact()
        if not result:
            console.print("✅ 当前历史较短，无需压缩", style="green")
        else:
            console.print(
                f"✅ 压缩完成: 折叠 {result['folded_messages']} 条消息（第 {result['compressions']} 次）",
                style="green",
            )
            summary = result.get("summary") or ""
            preview = summary if len(summary) <= 200 else summary[:200] + "…"
            console.print(f"📝 摘要: {preview}", style="dim")
        ctx.record_command("compact")
    except Exception as e:  # noqa: BLE001
        console.print(f"❌ 压缩失败: {e}", style="red")
        ctx.record_command("compact", "", "failed", str(e))
    return True


def handle_session_list(ctx, parsed):
    console = ctx.console
    try:
        manager = _get_session_manager()
        sessions = manager.list_sessions()
        if not sessions:
            console.print("📭 没有会话", style="yellow")
        else:
            console.print(f"💬 共有 {len(sessions)} 个会话:", style="cyan")
            current_session = manager.get_current_session()
            current_id = current_session.session_id if current_session else None
            for session in sessions:
                is_current = "🔸" if session.session_id == current_id else " "
                status_emoji = ("🟢" if session.status.value == "active"
                                else "📦" if session.status.value == "archived" else "🗑️")
                console.print(
                    f"{is_current} {status_emoji} {session.session_id[:8]}... - {session.title}",
                    style="bold" if session.session_id == current_id else "dim",
                )
                console.print(f"    📅 {session.updated_at.strftime('%Y-%m-%d %H:%M')}", style="dim")
                console.print(f"    💬 {len(session.messages)} 条消息", style="dim")
        ctx.record_command("session_list")
    except Exception as e:  # noqa: BLE001
        console.print(f"❌ 列出会话失败: {e}", style="red")
        ctx.record_command("session_list", "", "failed", str(e))
    return True


def handle_session_switch(ctx, parsed):
    console = ctx.console
    session_id = parsed.arg
    if not session_id:
        console.print("❌ 请指定会话ID: /session-switch <id>", style="yellow")
        return False
    try:
        manager = _get_session_manager()
        success = manager.switch_session(session_id)
        if success:
            session = manager.get_current_session()
            console.print(f"✅ 已切换到会话: {session.title}", style="green")
            console.print(f"💬 该会话有 {len(session.messages)} 条消息", style="dim")
            ctx.record_command("session_switch", session_id)
        else:
            console.print(f"❌ 会话不存在或已删除: {session_id}", style="yellow")
            return False
    except Exception as e:  # noqa: BLE001
        console.print(f"❌ 切换会话失败: {e}", style="red")
        ctx.record_command("session_switch", session_id, "failed", str(e))
    return True


def handle_session_current(ctx, parsed):
    console = ctx.console
    try:
        manager = _get_session_manager()
        current = manager.get_current_session()
        if not current:
            console.print("📭 没有当前会话，请使用 /session-new 创建新会话", style="yellow")
            return False
        console.print("💬 当前会话信息:", style="cyan")
        console.print(f"🆔 ID: {current.session_id}", style="bold")
        console.print(f"📋 标题: {current.title}", style="dim")
        console.print(f"📊 状态: {current.status.value}", style="dim")
        console.print(f"📅 创建: {current.created_at.strftime('%Y-%m-%d %H:%M:%S')}", style="dim")
        console.print(f"🕐 更新: {current.updated_at.strftime('%Y-%m-%d %H:%M:%S')}", style="dim")
        console.print(f"💬 消息数: {len(current.messages)}", style="dim")
        if current.tags:
            console.print(f"🏷️  标签: {', '.join(current.tags)}", style="dim")
        ctx.record_command("session_current")
    except Exception as e:  # noqa: BLE001
        console.print(f"❌ 获取当前会话失败: {e}", style="red")
        ctx.record_command("session_current", "", "failed", str(e))
    return True


def handle_session_info(ctx, parsed):
    console = ctx.console
    session_id = parsed.arg
    if not session_id:
        console.print("❌ 请指定会话ID: /session-info <id>", style="yellow")
        return False
    try:
        manager = _get_session_manager()
        sessions = manager.list_sessions()
        matching_sessions = [s for s in sessions if session_id in s.session_id]
        if not matching_sessions:
            console.print(f"❌ 未找到会话: {session_id}", style="yellow")
            return False
        session = matching_sessions[0]
        console.print("💬 会话详细信息:", style="cyan")
        console.print(f"🆔 ID: {session.session_id}", style="bold")
        console.print(f"📋 标题: {session.title}", style="dim")
        console.print(f"📊 状态: {session.status.value}", style="dim")
        console.print(f"📅 创建: {session.created_at.strftime('%Y-%m-%d %H:%M:%S')}", style="dim")
        console.print(f"🕐 更新: {session.updated_at.strftime('%Y-%m-%d %H:%M:%S')}", style="dim")
        console.print(f"💬 消息数: {len(session.messages)}", style="dim")
        if session.tags:
            console.print(f"🏷️  标签: {', '.join(session.tags)}", style="dim")
        if session.metadata:
            console.print(f"📝 元数据: {session.metadata}", style="dim")
        ctx.record_command("session_info", session_id)
    except Exception as e:  # noqa: BLE001
        console.print(f"❌ 获取会话信息失败: {e}", style="red")
        ctx.record_command("session_info", session_id, "failed", str(e))
    return True


def handle_session_search(ctx, parsed):
    console = ctx.console
    query = parsed.arg
    if not query:
        console.print("❌ 请指定搜索查询: /session-search <query>", style="yellow")
        return False
    try:
        manager = _get_session_manager()
        results = manager.search_sessions(query)
        if not results:
            console.print(f"🔍 未找到包含 '{query}' 的会话", style="yellow")
            return False
        console.print(f"🔍 找到 {len(results)} 个包含 '{query}' 的会话:", style="cyan")
        for session in results:
            console.print(f"  • {session.title} ({session.session_id[:8]}...)", style="dim")
            console.print(f"    💬 {len(session.messages)} 条消息", style="dim")
        ctx.record_command("session_search", query)
    except Exception as e:  # noqa: BLE001
        console.print(f"❌ 搜索会话失败: {e}", style="red")
        ctx.record_command("session_search", query, "failed", str(e))
    return True


def handle_session_compress(ctx, parsed):
    """``/session-compress``：等同 ``/compact``（滚动摘要压缩，替代旧的按条数截断）。"""
    return handle_compact(ctx, parsed)


def handle_session_delete(ctx, parsed):
    console = ctx.console
    session_id = parsed.arg
    if not session_id:
        console.print("❌ 请指定会话ID: /session-delete <id>", style="yellow")
        return False
    try:
        manager = _get_session_manager()
        current = manager.get_current_session()
        if current and session_id in current.session_id:
            console.print("⚠️  不能删除当前会话，请先切换到其他会话", style="yellow")
            return False
        success = manager.delete_session(session_id)
        if success:
            console.print(f"✅ 会话已删除: {session_id}", style="green")
            ctx.record_command("session_delete", session_id)
        else:
            console.print(f"❌ 会话不存在: {session_id}", style="yellow")
            return False
    except Exception as e:  # noqa: BLE001
        console.print(f"❌ 删除会话失败: {e}", style="red")
        ctx.record_command("session_delete", session_id, "failed", str(e))
    return True


def handle_session_archive(ctx, parsed):
    console = ctx.console
    session_id = parsed.arg
    if not session_id:
        console.print("❌ 请指定会话ID: /session-archive <id>", style="yellow")
        return False
    try:
        manager = _get_session_manager()
        success = manager.archive_session(session_id)
        if success:
            console.print(f"📦 会话已归档: {session_id}", style="green")
            ctx.record_command("session_archive", session_id)
        else:
            console.print(f"❌ 会话不存在: {session_id}", style="yellow")
            return False
    except Exception as e:  # noqa: BLE001
        console.print(f"❌ 归档会话失败: {e}", style="red")
        ctx.record_command("session_archive", session_id, "failed", str(e))
    return True
