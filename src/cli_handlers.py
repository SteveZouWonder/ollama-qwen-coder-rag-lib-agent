#!/usr/bin/env python3
"""
CLI 命令处理器 —— 从 query_interface.main() 的巨型 if/elif 中抽出的命令实现。

设计要点：
  - 每个 handler 形如 ``handle_xxx(ctx, parsed) -> bool``，返回值表示
    “命令处理完成后是否显示命令推荐”（对应原先的 should_show_recommendations）。
  - 所有共享状态（console、rag_engine、react_engine、HAS_RICH、记录函数等）
    经由 ``CLIContext`` 注入，避免 handler 直接依赖 query_interface 的模块级
    全局变量，便于单元测试与复用。
  - 通过 ``COMMAND_HANDLERS`` 命令表（cmd_type -> handler）驱动调度，取代
    原先 1000+ 行的 if/elif 链。
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Callable

logger = logging.getLogger(__name__)


# ==================== 上下文 ====================

@dataclass
class CLIContext:
    """承载交互循环所需的全部共享状态与协作对象。

    handler 仅通过本上下文读写状态，从而与 query_interface 的模块级全局解耦。
    """

    console: Any
    has_rich: bool
    rag_engine: Any = None
    react_engine: Any = None
    last_rag_sources: list = field(default_factory=list)

    # 协作回调（由 query_interface 注入，保持单一实现来源）
    record_command: Callable[..., None] = lambda *a, **k: None
    record_conversation: Callable[[str, str], None] = lambda *a, **k: None
    ask_progress_callback: Callable[[dict], None] = lambda *a, **k: None

    # 渲染/工具函数（由 query_interface 注入）
    print_help: Callable[[], None] = lambda: None
    print_tools: Callable[[], None] = lambda: None
    show_tutorial: Callable[[], None] = lambda: None
    print_banner: Callable[[], None] = lambda: None
    print_knowledge_stats: Callable[[], None] = lambda: None
    print_rag_sources: Callable[[list], None] = lambda s: None
    load_documents: Callable[..., Any] = None
    registry: Any = None

    # 能力开关
    knowledge_management_available: bool = False


# ==================== 通用工具 ====================

def _is_error(result: str) -> bool:
    """工具返回文本是否表示错误/提示（约定以 [错误]/[提示] 前缀）。"""
    return result.startswith("[错误]") or result.startswith("[提示]")


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


# ==================== 知识库基础命令 ====================

def handle_stats(ctx, parsed):
    ctx.print_knowledge_stats()
    ctx.record_command("stats")
    return True


def handle_sources(ctx, parsed):
    ctx.print_rag_sources(ctx.last_rag_sources)
    ctx.record_command("sources")
    return True


def handle_add(ctx, parsed):
    console = ctx.console
    path = parsed.arg
    try:
        docs = ctx.load_documents(path)
        if docs:
            ctx.rag_engine.add_documents(docs, [path])
            console.print("✅ 文档已添加到知识库", style="green")
            console.print("💡 提示: 可以使用 /generate-skills 将知识库转化为Skills", style="dim")
            ctx.record_command("add", path, "success")
        else:
            console.print("⚠️  未找到可加载的文档", style="yellow")
            ctx.record_command("add", path, "no documents")
    except Exception as e:  # noqa: BLE001
        console.print(f"❌ 添加失败: {e}", style="red")
        ctx.record_command("add", path, "failed", str(e))
    return True


# ==================== 知识库管理命令 ====================

def _require_knowledge_management(ctx) -> bool:
    if not ctx.knowledge_management_available:
        ctx.console.print("❌ 知识库管理模块未安装", style="red")
        return False
    return True


def handle_generate_skills(ctx, parsed):
    console = ctx.console
    if not _require_knowledge_management(ctx):
        return False
    if not ctx.rag_engine:
        console.print("❌ 知识库未初始化", style="yellow")
        return False
    try:
        from knowledge_to_skills import KnowledgeToSkillsEngine
        console.print("🔄 开始生成Skills...", style="cyan")
        engine = KnowledgeToSkillsEngine()
        results = engine.convert()
        console.print(f"✅ 成功生成 {len(results)} 个Skills:", style="green")
        for key, path in results.items():
            console.print(f"  • {key}: {path}", style="dim")
        ctx.record_command("generate_skills")
    except Exception as e:  # noqa: BLE001
        console.print(f"❌ 生成Skills失败: {e}", style="red")
        ctx.record_command("generate_skills", "", "failed", str(e))
    return True


def handle_snapshot_list(ctx, parsed):
    console = ctx.console
    if not _require_knowledge_management(ctx):
        return False
    try:
        from knowledge_snapshot import KnowledgeSnapshotManager
        manager = KnowledgeSnapshotManager()
        snapshots = manager.list_snapshots()
        if not snapshots:
            console.print("📭 没有找到快照", style="yellow")
        else:
            console.print(f"📋 共有 {len(snapshots)} 个快照:", style="cyan")
            for snap in snapshots:
                console.print(f"\n  🆔 {snap['snapshot_id']}", style="bold")
                console.print(f"  📅 {snap['timestamp']}", style="dim")
                console.print(f"  📄 文档数: {snap['document_count']}", style="dim")
                console.print(f"  🧩 Chunk数: {snap['total_chunks']}", style="dim")
                console.print(f"  ⚡ 触发方式: {snap['trigger']}", style="dim")
        ctx.record_command("snapshot_list")
    except Exception as e:  # noqa: BLE001
        console.print(f"❌ 获取快照列表失败: {e}", style="red")
        ctx.record_command("snapshot_list", "", "failed", str(e))
    return True


def handle_snapshot_create(ctx, parsed):
    console = ctx.console
    if not _require_knowledge_management(ctx):
        return False
    if not ctx.rag_engine:
        console.print("❌ 知识库未初始化", style="yellow")
        return False
    try:
        from knowledge_snapshot import KnowledgeSnapshotManager
        manager = KnowledgeSnapshotManager()
        snapshot = manager.create_snapshot(trigger="manual")
        console.print(f"✅ 快照创建完成: {snapshot.snapshot_id}", style="green")
        console.print(f"📅 时间: {snapshot.timestamp}", style="dim")
        console.print(f"📄 文档数: {len(snapshot.documents)}", style="dim")
        ctx.record_command("snapshot_create")
    except Exception as e:  # noqa: BLE001
        console.print(f"❌ 创建快照失败: {e}", style="red")
        ctx.record_command("snapshot_create", "", "failed", str(e))
    return True


def handle_snapshot_restore(ctx, parsed):
    console = ctx.console
    if not _require_knowledge_management(ctx):
        return False
    snapshot_id = parsed.arg
    if not snapshot_id:
        console.print("❌ 请指定快照ID: /snapshot-restore <id>", style="yellow")
        return False
    try:
        from knowledge_snapshot import KnowledgeSnapshotManager, RestoreHelper
        manager = KnowledgeSnapshotManager()
        snapshot = manager.load_snapshot(snapshot_id)
        if not snapshot:
            console.print(f"❌ 快照不存在: {snapshot_id}", style="red")
            return False
        console.print(f"🔄 恢复快照: {snapshot_id}", style="cyan")
        console.print(f"📄 文档数: {len(snapshot.documents)}", style="dim")
        helper = RestoreHelper(manager)
        script_file = helper.generate_restore_script(snapshot_id)
        console.print(f"✅ 恢复脚本已生成: {script_file}", style="green")
        console.print("💡 请运行该脚本来恢复知识库", style="yellow")
        ctx.record_command("snapshot_restore", snapshot_id)
    except Exception as e:  # noqa: BLE001
        console.print(f"❌ 恢复快照失败: {e}", style="red")
        ctx.record_command("snapshot_restore", snapshot_id, "failed", str(e))
    return True


def handle_knowledge_summary(ctx, parsed):
    console = ctx.console
    if not _require_knowledge_management(ctx):
        return False
    if not ctx.rag_engine:
        console.print("❌ 知识库未初始化", style="yellow")
        return False
    try:
        from knowledge_to_skills import KnowledgeToSkillsEngine
        engine = KnowledgeToSkillsEngine()
        summary = engine.get_document_summary()
        console.print("📊 知识库文档摘要:", style="cyan")
        for doc in summary:
            type_indicator = "🌐 通用" if doc['is_generic'] else "🏢 项目"
            console.print(f"\n  📄 {doc['file_name']}", style="bold")
            console.print(f"  📍 {doc['file_path']}", style="dim")
            console.print(f"  🏷️ 主题: {', '.join(doc['topics'])}", style="dim")
            console.print(f"  {type_indicator} (置信度: {doc['confidence']:.2f})", style="dim")
            console.print(f"  🧩 Chunks: {doc['chunk_count']}", style="dim")
        ctx.record_command("knowledge_summary")
    except Exception as e:  # noqa: BLE001
        console.print(f"❌ 获取知识库摘要失败: {e}", style="red")
        ctx.record_command("knowledge_summary", "", "failed", str(e))
    return True


# ==================== 文件管理命令 ====================

def handle_file_list(ctx, parsed):
    console = ctx.console
    try:
        from file_metadata import get_global_metadata_manager
        manager = get_global_metadata_manager()
        files = manager.list_files()
        if not files:
            console.print("📭 知识库中没有文件", style="yellow")
        else:
            console.print(f"📁 共有 {len(files)} 个文件:", style="cyan")
            for file_meta in files:
                console.print(f"\n  📄 {file_meta.file_path}", style="bold")
                console.print(f"  📊 大小: {manager._format_size(file_meta.file_size)}", style="dim")
                console.print(f"  🏷️  类型: {file_meta.persistence_type}", style="dim")
                console.print(f"  📅 上传: {file_meta.upload_time[:19]}", style="dim")
                if file_meta.tags:
                    console.print(f"  🏷️  标签: {', '.join(file_meta.tags)}", style="dim")
        ctx.record_command("file_list")
    except Exception as e:  # noqa: BLE001
        console.print(f"❌ 列出文件失败: {e}", style="red")
        ctx.record_command("file_list", "", "failed", str(e))
    return True


def handle_file_info(ctx, parsed):
    console = ctx.console
    file_path = parsed.arg
    if not file_path:
        console.print("❌ 请指定文件路径: /file-info <path>", style="yellow")
        return False
    try:
        from file_metadata import get_global_metadata_manager
        manager = get_global_metadata_manager()
        file_meta = manager.get_file_metadata(file_path)
        if not file_meta:
            console.print(f"❌ 文件不在知识库中: {file_path}", style="yellow")
            return False
        console.print(f"📄 文件信息: {file_path}", style="cyan")
        console.print(f"📊 大小: {manager._format_size(file_meta.file_size)}", style="dim")
        console.print(f"🏷️  类型: {file_meta.persistence_type}", style="dim")
        console.print(f"📅 上传: {file_meta.upload_time}", style="dim")
        console.print(f"🔢 访问次数: {file_meta.access_count}", style="dim")
        console.print(f"📄 文档数: {file_meta.document_count}", style="dim")
        console.print(f"🧩 Chunk数: {file_meta.chunk_count}", style="dim")
        if file_meta.last_access:
            console.print(f"🕐 最后访问: {file_meta.last_access[:19]}", style="dim")
        if file_meta.tags:
            console.print(f"🏷️  标签: {', '.join(file_meta.tags)}", style="dim")
        ctx.record_command("file_info", file_path)
    except Exception as e:  # noqa: BLE001
        console.print(f"❌ 获取文件信息失败: {e}", style="red")
        ctx.record_command("file_info", file_path, "failed", str(e))
    return True


def handle_file_stats(ctx, parsed):
    console = ctx.console
    try:
        from file_metadata import get_global_metadata_manager
        from file_validator import get_global_validator
        metadata_manager = get_global_metadata_manager()
        validator = get_global_validator()
        stats = metadata_manager.get_stats()
        validator_stats = validator.get_stats()
        console.print("📊 文件统计信息:", style="cyan")
        console.print(f"📁 总文件数: {stats['total_files']}", style="bold")
        console.print(f"💾 总大小: {stats['total_size_formatted']}", style="dim")
        console.print(f"📌 永久文件: {stats['permanent_count']}", style="dim")
        console.print(f"⏰ 临时文件: {stats['temporary_count']}", style="dim")
        console.print(f"🎯 会话文件: {stats['session_count']}", style="dim")
        console.print(f"🧹 待清理: {stats['cleanup_count']}", style="dim")
        console.print(f"🔗 已知文件: {validator_stats['known_file_count']}", style="dim")
        console.print(f"📈 利用率: {validator_stats['utilization_percent']:.1f}%", style="dim")
        ctx.record_command("file_stats")
    except Exception as e:  # noqa: BLE001
        console.print(f"❌ 获取统计信息失败: {e}", style="red")
        ctx.record_command("file_stats", "", "failed", str(e))
    return True


def handle_file_cleanup(ctx, parsed):
    console = ctx.console
    try:
        from file_metadata import get_global_metadata_manager
        manager = get_global_metadata_manager()
        files_to_cleanup = manager.get_files_to_cleanup()
        if not files_to_cleanup:
            console.print("✅ 没有需要清理的文件", style="green")
        else:
            console.print(f"🧹 发现 {len(files_to_cleanup)} 个需要清理的文件", style="yellow")
            for file_meta in files_to_cleanup:
                console.print(f"  - {file_meta.file_path} ({file_meta.persistence_type})", style="dim")
            cleaned = manager.cleanup_files()
            console.print(f"✅ 已清理 {len(cleaned)} 个文件", style="green")
        ctx.record_command("file_cleanup")
    except Exception as e:  # noqa: BLE001
        console.print(f"❌ 清理文件失败: {e}", style="red")
        ctx.record_command("file_cleanup", "", "failed", str(e))
    return True


def handle_file_deduplicate(ctx, parsed):
    console = ctx.console
    try:
        from file_metadata import get_global_metadata_manager
        metadata_manager = get_global_metadata_manager()
        console.print("🔄 正在检查重复文件...", style="cyan")
        files = metadata_manager.list_files()

        duplicates = []
        seen_hashes = {}
        for file_meta in files:
            if file_meta.file_hash:
                if file_meta.file_hash in seen_hashes:
                    duplicates.append(file_meta)
                else:
                    seen_hashes[file_meta.file_hash] = file_meta

        if not duplicates:
            console.print("✅ 没有发现重复文件", style="green")
            ctx.record_command("file_deduplicate", "", "no_duplicates")
            return True

        console.print(f"⚠️  发现 {len(duplicates)} 个重复文件:", style="yellow")
        for file_meta in duplicates:
            console.print(f"  - {file_meta.file_path}", style="dim")
        try:
            answer = console.input("是否删除重复文件? (y/n): ").strip().lower()
            if answer in ("y", "yes", "是", "确认"):
                for file_meta in duplicates:
                    metadata_manager.remove_file(file_meta.file_path)
                    console.print(f"✅ 已删除: {file_meta.file_path}", style="green")
                console.print(f"✅ 共删除 {len(duplicates)} 个重复文件", style="green")
                ctx.record_command("file_deduplicate", f"删除了{len(duplicates)}个重复文件", "success")
            else:
                console.print("❌ 取消删除", style="yellow")
                ctx.record_command("file_deduplicate", "", "cancelled")
        except (EOFError, KeyboardInterrupt):
            console.print("\n❌ 取消操作", style="yellow")
            ctx.record_command("file_deduplicate", "", "cancelled")
    except Exception as e:  # noqa: BLE001
        console.print(f"❌ 去重失败: {e}", style="red")
        ctx.record_command("file_deduplicate", "", "failed", str(e))
    return True


# ==================== 会话管理命令 ====================

def _get_session_manager():
    from session_manager import get_session_manager
    from config import SESSION_STORAGE_PATH
    return get_session_manager(str(SESSION_STORAGE_PATH))


def handle_session_new(ctx, parsed):
    console = ctx.console
    try:
        manager = _get_session_manager()
        title = parsed.arg if parsed.arg else None
        session = manager.create_session(title=title)
        console.print(f"✅ 新会话已创建: {session.session_id}", style="green")
        console.print(f"📋 标题: {session.title}", style="dim")
        console.print(f"📅 创建时间: {session.created_at.strftime('%Y-%m-%d %H:%M:%S')}", style="dim")
        ctx.record_command("session_new", session.title if session.title else "")
    except Exception as e:  # noqa: BLE001
        console.print(f"❌ 创建会话失败: {e}", style="red")
        ctx.record_command("session_new", "", "failed", str(e))
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
    console = ctx.console
    try:
        from history_compressor import HistoryCompressor
        manager = _get_session_manager()
        current = manager.get_current_session()
        if not current:
            console.print("📭 没有当前会话", style="yellow")
            return False
        console.print("🔄 正在压缩会话历史...", style="cyan")
        compressor = HistoryCompressor()
        original_count = len(current.messages)
        compressed_messages = compressor.compress_history(current.messages)
        current.messages = compressed_messages
        manager.save_session(current)
        console.print(f"✅ 压缩完成: {original_count} → {len(compressed_messages)} 条消息", style="green")
        console.print(f"📊 压缩率: {(1 - len(compressed_messages)/original_count)*100:.1f}%", style="dim")
        ctx.record_command("session_compress", f"{original_count}→{len(compressed_messages)}")
    except Exception as e:  # noqa: BLE001
        console.print(f"❌ 压缩会话失败: {e}", style="red")
        ctx.record_command("session_compress", "", "failed", str(e))
    return True


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


# ==================== 网络搜索命令 ====================

def handle_web_search(ctx, parsed):
    console = ctx.console
    query = parsed.arg.strip()
    if not query:
        console.print("❌ 请提供搜索查询: /web-search <query>", style="yellow")
        return False
    try:
        console.print(f"🔍 正在搜索: {query}", style="cyan")
        result = ctx.registry.execute("web_search", {"query": query})
        if _is_error(result):
            console.print(result, style="yellow")
            return False
        console.print(result, style="green")
        ctx.record_command("web_search", query)
    except Exception as e:  # noqa: BLE001
        console.print(f"❌ 搜索失败: {e}", style="red")
        ctx.record_command("web_search", query, "failed", str(e))
    return True


def handle_web_cache(ctx, parsed):
    console = ctx.console
    arg = parsed.arg.strip()
    if not arg or arg == "status":
        try:
            result = ctx.registry.execute("web_cache_status", {})
            console.print(result, style="cyan")
            ctx.record_command("web_cache", "status")
        except Exception as e:  # noqa: BLE001
            console.print(f"❌ 获取缓存状态失败: {e}", style="red")
            ctx.record_command("web_cache", "status", "failed", str(e))
        return True
    if arg == "clear":
        try:
            result = ctx.registry.execute("web_cache_clear", {})
            console.print(result, style="green")
            ctx.record_command("web_cache", "clear")
        except Exception as e:  # noqa: BLE001
            console.print(f"❌ 清空缓存失败: {e}", style="red")
            ctx.record_command("web_cache", "clear", "failed", str(e))
        return True
    console.print("❌ 未知命令，使用: /web-cache [status|clear]", style="yellow")
    return False


def handle_web_extract(ctx, parsed):
    console = ctx.console
    url = parsed.arg.strip()
    if not url:
        console.print("❌ 请提供URL: /web-extract <url>", style="yellow")
        return False
    try:
        console.print(f"📄 正在提取内容: {url}", style="cyan")
        result = ctx.registry.execute("web_content_extract", {"url": url})
        if result.startswith("[错误]"):
            console.print(result, style="red")
            return False
        console.print(result, style="green")
        ctx.record_command("web_extract", url)
    except Exception as e:  # noqa: BLE001
        console.print(f"❌ 内容提取失败: {e}", style="red")
        ctx.record_command("web_extract", url, "failed", str(e))
    return True


# ==================== 代码分析命令 ====================

def handle_code_ast(ctx, parsed):
    console = ctx.console
    pattern = parsed.arg.strip()
    if not pattern:
        console.print("❌ 请提供搜索模式: /code-ast <pattern>", style="yellow")
        return False
    try:
        console.print(f"🔍 正在搜索 AST: {pattern}", style="cyan")
        result = ctx.registry.execute("ast_search", {"pattern": pattern, "path": "."})
        if result.startswith("[错误]"):
            console.print(result, style="red")
            return False
        console.print(result, style="green")
        ctx.record_command("code_ast", pattern)
    except Exception as e:  # noqa: BLE001
        console.print(f"❌ AST 搜索失败: {e}", style="red")
        ctx.record_command("code_ast", pattern, "failed", str(e))
    return True


def handle_code_quality(ctx, parsed):
    console = ctx.console
    path = parsed.arg.strip() if parsed.arg.strip() else "."
    try:
        console.print(f"🔍 正在分析代码质量: {path}", style="cyan")
        result = ctx.registry.execute("code_quality_check", {"path": path})
        if result.startswith("[错误]"):
            console.print(result, style="red")
            return False
        console.print(result, style="green")
        ctx.record_command("code_quality", path)
    except Exception as e:  # noqa: BLE001
        console.print(f"❌ 代码质量检查失败: {e}", style="red")
        ctx.record_command("code_quality", path, "failed", str(e))
    return True


# ==================== 知识图谱命令 ====================

def handle_graph_query(ctx, parsed):
    console = ctx.console
    query = parsed.arg.strip()
    if not query:
        console.print("❌ 请提供查询内容: /graph-query <query>", style="yellow")
        return False
    try:
        console.print(f"🔍 正在查询知识图谱: {query}", style="cyan")
        result = ctx.registry.execute("knowledge_graph_query", {"query": query})
        if result.startswith("[错误]"):
            console.print(result, style="red")
            return False
        console.print(result, style="green")
        ctx.record_command("graph_query", query)
    except Exception as e:  # noqa: BLE001
        console.print(f"❌ 知识图谱查询失败: {e}", style="red")
        ctx.record_command("graph_query", query, "failed", str(e))
    return True


def handle_graph_build(ctx, parsed):
    console = ctx.console
    console.print("📝 知识图谱构建需要文本内容", style="cyan")
    console.print("请使用 Agent 模式调用 knowledge_graph_build 工具", style="yellow")
    return False


# ==================== 数据库管理命令 ====================

def handle_db_connect(ctx, parsed):
    console = ctx.console
    args = parsed.arg.strip().split() if parsed.arg.strip() else []
    if len(args) < 2:
        console.print("❌ 请提供数据库类型和路径: /db-connect <type> <database>", style="yellow")
        return False
    db_type, database = args[0], args[1]
    try:
        console.print(f"🔗 正在连接数据库: {db_type} @ {database}", style="cyan")
        result = ctx.registry.execute("database_connect", {"db_type": db_type, "database": database})
        if result.startswith("[错误]"):
            console.print(result, style="red")
            return False
        console.print(result, style="green")
        ctx.record_command("db_connect", f"{db_type} {database}")
    except Exception as e:  # noqa: BLE001
        console.print(f"❌ 数据库连接失败: {e}", style="red")
        ctx.record_command("db_connect", f"{db_type} {database}", "failed", str(e))
    return True


def handle_db_query(ctx, parsed):
    console = ctx.console
    sql = parsed.arg.strip()
    if not sql:
        console.print("❌ 请提供SQL查询语句: /db-query <sql>", style="yellow")
        return False
    try:
        console.print("🔍 正在执行SQL查询", style="cyan")
        result = ctx.registry.execute("database_query", {"sql": sql})
        if result.startswith("[错误]"):
            console.print(result, style="red")
            return False
        console.print(result, style="green")
        ctx.record_command("db_query", sql[:50])
    except Exception as e:  # noqa: BLE001
        console.print(f"❌ SQL查询失败: {e}", style="red")
        ctx.record_command("db_query", sql[:50], "failed", str(e))
    return True


def handle_db_execute(ctx, parsed):
    console = ctx.console
    sql = parsed.arg.strip()
    if not sql:
        console.print("❌ 请提供SQL语句: /db-execute <sql>", style="yellow")
        return False
    try:
        console.print("⚡ 正在执行SQL语句", style="cyan")
        result = ctx.registry.execute("database_execute", {"sql": sql})
        if result.startswith("[错误]"):
            console.print(result, style="red")
            return False
        console.print(result, style="green")
        ctx.record_command("db_execute", sql[:50])
    except Exception as e:  # noqa: BLE001
        console.print(f"❌ SQL执行失败: {e}", style="red")
        ctx.record_command("db_execute", sql[:50], "failed", str(e))
    return True


def handle_db_create_table(ctx, parsed):
    console = ctx.console
    args = parsed.arg.strip().split() if parsed.arg.strip() else []
    if len(args) < 1:
        console.print("❌ 请提供表名: /db-create-table <table> <columns_json>", style="yellow")
        return False
    table = args[0]
    columns_json = " ".join(args[1:]) if len(args) > 1 else "{}"
    try:
        columns = json.loads(columns_json)
    except json.JSONDecodeError:
        console.print("❌ 列定义必须是有效的JSON格式", style="yellow")
        return False
    try:
        console.print(f"🔨 正在创建表: {table}", style="cyan")
        result = ctx.registry.execute("database_create_table", {"table": table, "columns": columns})
        if result.startswith("[错误]"):
            console.print(result, style="red")
            return False
        console.print(result, style="green")
        ctx.record_command("db_create_table", table)
    except Exception as e:  # noqa: BLE001
        console.print(f"❌ 创建表失败: {e}", style="red")
        ctx.record_command("db_create_table", table, "failed", str(e))
    return True


def handle_db_insert(ctx, parsed):
    console = ctx.console
    args = parsed.arg.strip().split() if parsed.arg.strip() else []
    if len(args) < 1:
        console.print("❌ 请提供表名和数据: /db-insert <table> <data_json>", style="yellow")
        return False
    table = args[0]
    data_json = " ".join(args[1:]) if len(args) > 1 else "{}"
    try:
        data = json.loads(data_json)
    except json.JSONDecodeError:
        console.print("❌ 数据必须是有效的JSON格式", style="yellow")
        return False
    try:
        console.print(f"➕ 正在插入数据到表: {table}", style="cyan")
        result = ctx.registry.execute("database_insert", {"table": table, "data": data})
        if result.startswith("[错误]"):
            console.print(result, style="red")
            return False
        console.print(result, style="green")
        ctx.record_command("db_insert", table)
    except Exception as e:  # noqa: BLE001
        console.print(f"❌ 插入数据失败: {e}", style="red")
        ctx.record_command("db_insert", table, "failed", str(e))
    return True


def handle_db_schema(ctx, parsed):
    console = ctx.console
    table = parsed.arg.strip()
    if not table:
        console.print("❌ 请提供表名: /db-schema <table>", style="yellow")
        return False
    try:
        console.print(f"🔍 正在获取表结构: {table}", style="cyan")
        result = ctx.registry.execute("database_get_schema", {"table": table})
        if result.startswith("[错误]"):
            console.print(result, style="red")
            return False
        console.print(result, style="green")
        ctx.record_command("db_schema", table)
    except Exception as e:  # noqa: BLE001
        console.print(f"❌ 获取表结构失败: {e}", style="red")
        ctx.record_command("db_schema", table, "failed", str(e))
    return True


# ==================== 命令表 ====================
# cmd_type -> handler。仅包含“自包含”命令；与引擎/主循环状态强耦合的命令
# （ask / agent / natural / clear / history / summary / reset / file / write /
# exec / pwd / cd / model / quit）仍由 query_interface.main() 直接处理。

COMMAND_HANDLERS: dict[str, Callable[[CLIContext, Any], bool]] = {
    "help": handle_help,
    "tutorial": handle_tutorial,
    "tools": handle_tools,
    "stats": handle_stats,
    "sources": handle_sources,
    "add": handle_add,
    "generate_skills": handle_generate_skills,
    "snapshot_list": handle_snapshot_list,
    "snapshot_create": handle_snapshot_create,
    "snapshot_restore": handle_snapshot_restore,
    "knowledge_summary": handle_knowledge_summary,
    "file_list": handle_file_list,
    "file_info": handle_file_info,
    "file_stats": handle_file_stats,
    "file_cleanup": handle_file_cleanup,
    "file_deduplicate": handle_file_deduplicate,
    "session_new": handle_session_new,
    "session_list": handle_session_list,
    "session_switch": handle_session_switch,
    "session_current": handle_session_current,
    "session_info": handle_session_info,
    "session_search": handle_session_search,
    "session_compress": handle_session_compress,
    "session_delete": handle_session_delete,
    "session_archive": handle_session_archive,
    "web_search": handle_web_search,
    "web_cache": handle_web_cache,
    "web_extract": handle_web_extract,
    "code_ast": handle_code_ast,
    "code_quality": handle_code_quality,
    "graph_query": handle_graph_query,
    "graph_build": handle_graph_build,
    "db_connect": handle_db_connect,
    "db_query": handle_db_query,
    "db_execute": handle_db_execute,
    "db_create_table": handle_db_create_table,
    "db_insert": handle_db_insert,
    "db_schema": handle_db_schema,
}
