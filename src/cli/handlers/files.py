"""文件管理命令：``/file-list`` ``/file-info`` ``/file-delete`` ``/file-stats`` ``/file-cleanup`` ``/file-deduplicate``。"""
from __future__ import annotations

import logging

from .base import _confirm

logger = logging.getLogger(__name__)


# ==================== 文件管理命令 ====================

def handle_file_list(ctx, parsed):
    console = ctx.console
    try:
        from file_metadata import get_global_metadata_manager
        from code_chunker import describe_file_chunking
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
                console.print(
                    f"  🧩 片段: {file_meta.chunk_count} · 分块: "
                    f"{describe_file_chunking(file_meta.file_path, getattr(file_meta, 'chunk_strategy', None), getattr(file_meta, 'symbol_count', 0))}",
                    style="dim",
                )
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
        from code_chunker import describe_file_chunking
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
        console.print(
            f"🧬 分块策略: {describe_file_chunking(file_meta.file_path, getattr(file_meta, 'chunk_strategy', None), getattr(file_meta, 'symbol_count', 0))}",
            style="dim",
        )
        if file_meta.last_access:
            console.print(f"🕐 最后访问: {file_meta.last_access[:19]}", style="dim")
        if file_meta.tags:
            console.print(f"🏷️  标签: {', '.join(file_meta.tags)}", style="dim")
        ctx.record_command("file_info", file_path)
    except Exception as e:  # noqa: BLE001
        console.print(f"❌ 获取文件信息失败: {e}", style="red")
        ctx.record_command("file_info", file_path, "failed", str(e))
    return True


def handle_file_delete(ctx, parsed):
    """/file-delete <path>：从知识库删除文件（向量片段 + 图谱来源 + 元数据，不删磁盘文件）。"""
    console = ctx.console
    file_path = parsed.arg.strip()
    if not file_path:
        console.print("❌ 请指定文件路径: /file-delete <path>", style="yellow")
        return False
    if not ctx.rag_engine:
        console.print("❌ 知识库未初始化", style="yellow")
        return False
    try:
        preview = ctx.rag_engine.file_delete_preview(file_path)
        if not preview.get("exists"):
            console.print(f"❌ 文件不在知识库中: {file_path}", style="yellow")
            ctx.record_command("file_delete", file_path, "not_found")
            return False
        console.print(f"🗑️  将从知识库删除: {preview.get('file_name') or file_path}", style="yellow")
        console.print(f"  🧩 向量片段: {preview.get('chunk_count', 0)} 个", style="dim")
        if preview.get("graph_shared_basename"):
            console.print("  🕸️  图谱: 保留（另有同名文件）", style="dim")
        elif preview.get("graph_nodes") or preview.get("graph_edges"):
            console.print(
                f"  🕸️  图谱: 移除 {preview.get('graph_nodes', 0)} 个节点 / "
                f"{preview.get('graph_edges', 0)} 条边的来源（仅该文件贡献的会被删除）",
                style="dim",
            )
        else:
            console.print("  🕸️  图谱: 无变更", style="dim")
        console.print("  💾 磁盘上的原文件不会被删除", style="dim")
        if not _confirm(console, "确认删除? (y/n): "):
            console.print("❌ 已取消", style="yellow")
            ctx.record_command("file_delete", file_path, "cancelled")
            return True
        result = ctx.rag_engine.remove_file(file_path)
        graph = "图谱已更新" if result.get("graph_updated") else (result.get("note") or "图谱未变更")
        console.print(
            f"✅ 已删除 {result.get('file_name')}：{result.get('chunks_deleted', 0)} 个片段，{graph}",
            style="green",
        )
        console.print("💡 可用 /stats 查看当前知识库统计", style="dim")
        ctx.record_command("file_delete", file_path, "success")
    except FileNotFoundError as e:
        console.print(f"❌ {e}", style="yellow")
        ctx.record_command("file_delete", file_path, "not_found")
        return False
    except Exception as e:  # noqa: BLE001
        console.print(f"❌ 删除文件失败: {e}", style="red")
        ctx.record_command("file_delete", file_path, "failed", str(e))
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
