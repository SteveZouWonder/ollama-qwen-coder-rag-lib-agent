"""知识库命令：``/stats`` ``/sources`` ``/add``、``/generate-skills``、``/snapshot-*``、``/knowledge-summary``。"""
from __future__ import annotations

import logging
from pathlib import Path

from .base import _confirm

logger = logging.getLogger(__name__)


# ==================== 知识库基础命令 ====================

def handle_stats(ctx, parsed):
    ctx.print_knowledge_stats()
    ctx.record_command("stats")
    return True


def handle_sources(ctx, parsed):
    rag_sources = getattr(ctx, "last_rag_sources", None) or []
    web_sources = getattr(ctx, "last_web_sources", None) or []
    if not rag_sources and not web_sources:
        ctx.console.print("⚠️  没有来源信息", style="yellow")
        ctx.record_command("sources")
        return True
    if rag_sources:
        ctx.print_rag_sources(rag_sources)
    if web_sources:
        ctx.print_web_sources(web_sources)
    ctx.record_command("sources")
    return True


def _make_ingest_progress(console):
    """构造入库进度回调（rich Progress 两行：切分 / 嵌入）；rich 不可用时返回 (None, None)。

    返回 ``(progress, callback)``，``progress`` 需在 ``with`` 中使用。
    """
    try:
        from rich.console import Console
        from rich.progress import BarColumn, Progress, TextColumn, TimeElapsedColumn
    except ImportError:  # pragma: no cover - rich 为项目必装依赖
        return None, None
    if not isinstance(console, Console):
        # 非 rich Console（如测试桩）不渲染进度条
        return None, None
    progress = Progress(
        TextColumn("{task.description}"),
        BarColumn(bar_width=24),
        TextColumn("{task.completed}/{task.total}"),
        TimeElapsedColumn(),
        console=console,
        transient=True,
    )
    tasks: dict = {}

    def callback(event: dict) -> None:
        stage = event.get("stage") or event.get("phase")
        if stage not in ("chunk", "embed"):
            return
        total = int(event.get("total") or 0)
        current = int(event.get("current") or 0)
        label = "🧩 切分" if stage == "chunk" else "🧠 嵌入"
        if stage not in tasks:
            tasks[stage] = progress.add_task(label, total=max(total, 1))
        progress.update(tasks[stage], total=max(total, 1), completed=min(current, total) if total else current,
                        description=f"{label} {event.get('message', '')}"[:60])

    return progress, callback


def handle_add(ctx, parsed):
    console = ctx.console
    path = parsed.arg
    try:
        docs = ctx.load_documents(path)
        if docs:
            progress, callback = _make_ingest_progress(console)
            if progress is not None:
                with progress:
                    ctx.rag_engine.add_documents(docs, [path], progress_callback=callback)
            else:
                ctx.rag_engine.add_documents(docs, [path])
            # 结果摘要：文件数 · 片段数（· 代码文件按函数/类切分，符号数）
            try:
                from code_chunker import availability_hint_once, format_ingest_summary, language_for
                stats = getattr(ctx.rag_engine, "last_ingest_stats", None) or {}
                summary = format_ingest_summary(stats) if stats else "文档已添加到知识库"
                # 本次含代码文件但代码分块未启用 → 追加一次性提示
                has_code = any(language_for(None, str(p)) for p in stats)
                hint = availability_hint_once() if has_code else ""
            except Exception:  # noqa: BLE001 - 摘要失败不影响入库结果
                summary, hint = "文档已添加到知识库", ""
            console.print(f"✅ {summary}", style="green")
            if hint:
                console.print(f"💡 {hint}", style="dim")
            # 知识图谱作为文档入库的派生索引，已在 add_documents 中同步构建。
            if getattr(ctx.rag_engine, "last_graph_derived", False):
                console.print("🕸️  已同步更新知识图谱", style="dim")
            else:
                console.print(
                    "⚠️  知识图谱未自动更新，可用 /graph-build @<文件路径> 手动补建",
                    style="dim",
                )
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
    """/snapshot-restore <id> [--apply [--replace]]

    - 默认：生成恢复脚本（保持旧行为）；
    - ``--apply``：直接按快照文档清单重新入库（追加到现有索引）；
    - ``--apply --replace``：先清空索引再入库（需确认）。缺失文件跳过并列出。
    """
    console = ctx.console
    if not _require_knowledge_management(ctx):
        return False
    tokens = parsed.arg.split()
    flags = {t.lower() for t in tokens if t.startswith("--")}
    positional = [t for t in tokens if not t.startswith("--")]
    snapshot_id = positional[0] if positional else ""
    if not snapshot_id:
        console.print("❌ 请指定快照ID: /snapshot-restore <id> [--apply [--replace]]", style="yellow")
        return False
    apply = "--apply" in flags
    replace = "--replace" in flags
    try:
        from knowledge_snapshot import KnowledgeSnapshotManager, RestoreHelper
        manager = KnowledgeSnapshotManager()
        snapshot = manager.load_snapshot(snapshot_id)
        if not snapshot:
            console.print(f"❌ 快照不存在: {snapshot_id}", style="red")
            return False
        console.print(f"🔄 恢复快照: {snapshot_id}", style="cyan")
        console.print(f"📄 文档数: {len(snapshot.documents)}", style="dim")

        if not apply:
            helper = RestoreHelper(manager)
            script_file = helper.generate_restore_script(snapshot_id)
            console.print(f"✅ 恢复脚本已生成: {script_file}", style="green")
            console.print("💡 请运行该脚本来恢复知识库；或使用 /snapshot-restore <id> --apply 直接恢复", style="yellow")
            ctx.record_command("snapshot_restore", snapshot_id)
            return True

        if not ctx.rag_engine:
            console.print("❌ 知识库未初始化，无法直接恢复", style="yellow")
            return False
        missing = [d.file_path for d in snapshot.documents if not Path(d.file_path).exists()]
        if missing:
            console.print(f"⚠️  {len(missing)} 个文件已不存在，将跳过:", style="yellow")
            for m in missing:
                console.print(f"  - {m}", style="dim")
        mode = "replace" if replace else "append"
        if replace:
            console.print("⚠️  替换模式将先清空现有索引与图谱，再按快照重新入库", style="yellow")
            if not _confirm(console, "确认替换恢复? (y/n): "):
                console.print("❌ 已取消", style="yellow")
                ctx.record_command("snapshot_restore", snapshot_id, "cancelled")
                return True

        def progress(evt):
            msg = evt.get("message", "")
            if evt.get("stage") == "load":
                console.print(f"  [{evt.get('current')}/{evt.get('total')}] {msg}", style="dim")
            elif msg:
                console.print(f"  {msg}", style="dim")

        result = manager.restore_apply(
            snapshot_id, ctx.rag_engine, mode=mode,
            load_documents=ctx.load_documents, progress=progress,
        )
        if not result.get("ok"):
            console.print(f"❌ {result.get('error', '恢复失败')}", style="red")
            ctx.record_command("snapshot_restore", snapshot_id, "failed", str(result.get("error")))
            return True
        console.print(
            f"✅ 恢复完成（{mode}）：成功 {result['restored']}，跳过 {result['skipped']}，"
            f"失败 {result['failed']}，共 {result['chunks']} 个片段",
            style="green",
        )
        for err in result.get("errors", []):
            console.print(f"  ✗ {err}", style="red")
        console.print("💡 可用 /stats 查看当前知识库统计", style="dim")
        ctx.record_command("snapshot_restore", f"{snapshot_id} --apply{' --replace' if replace else ''}", "success")
    except Exception as e:  # noqa: BLE001
        console.print(f"❌ 恢复快照失败: {e}", style="red")
        ctx.record_command("snapshot_restore", snapshot_id, "failed", str(e))
    return True


def handle_snapshot_info(ctx, parsed):
    """/snapshot-info <id>：快照详情（文档清单 + 文件是否仍存在 + 模型配置）。"""
    console = ctx.console
    if not _require_knowledge_management(ctx):
        return False
    snapshot_id = parsed.arg.strip()
    if not snapshot_id:
        console.print("❌ 请指定快照ID: /snapshot-info <id>", style="yellow")
        return False
    try:
        from knowledge_snapshot import KnowledgeSnapshotManager
        info = KnowledgeSnapshotManager().snapshot_info(snapshot_id)
        if not info:
            console.print(f"❌ 快照不存在: {snapshot_id}", style="red")
            return False
        model = info.get("model_config") or {}
        console.print(f"📸 快照 {info['snapshot_id']}", style="bold cyan")
        console.print(f"  📅 时间: {info.get('timestamp', '')}", style="dim")
        console.print(f"  ⚡ 触发: {info.get('trigger', '')}", style="dim")
        console.print(
            f"  📄 文档 {info.get('document_count', 0)} 个 / 片段 {info.get('total_chunks', 0)}"
            f"（缺失 {info.get('missing_count', 0)} 个文件）",
            style="dim",
        )
        console.print(
            f"  🤖 模型: LLM {model.get('llm_model', '?')} / Embedding {model.get('embed_model', '?')}",
            style="dim",
        )
        console.print("  文档清单:", style="cyan")
        for doc in info.get("documents", []):
            mark = "✓" if doc.get("exists") else "✗"
            style = "green" if doc.get("exists") else "red"
            console.print(
                f"    {mark} {doc.get('file_name')}  ({doc.get('chunk_count', 0)} chunks)  {doc.get('file_path')}",
                style=style,
            )
        if info.get("missing_count"):
            console.print("  ⚠️  缺失的文件恢复时将被跳过", style="yellow")
        ctx.record_command("snapshot_info", snapshot_id)
    except Exception as e:  # noqa: BLE001
        console.print(f"❌ 获取快照详情失败: {e}", style="red")
        ctx.record_command("snapshot_info", snapshot_id, "failed", str(e))
    return True


def handle_snapshot_delete(ctx, parsed):
    """/snapshot-delete <id>：删除快照（需确认）。"""
    console = ctx.console
    if not _require_knowledge_management(ctx):
        return False
    snapshot_id = parsed.arg.strip()
    if not snapshot_id:
        console.print("❌ 请指定快照ID: /snapshot-delete <id>", style="yellow")
        return False
    try:
        from knowledge_snapshot import KnowledgeSnapshotManager
        manager = KnowledgeSnapshotManager()
        snapshot = manager.load_snapshot(snapshot_id)
        if not snapshot:
            console.print(f"❌ 快照不存在: {snapshot_id}", style="red")
            return False
        console.print(
            f"⚠️  将删除快照 {snapshot_id}（{snapshot.timestamp}，文档 {len(snapshot.documents)} 个）",
            style="yellow",
        )
        if not _confirm(console, "确认删除? (y/n): "):
            console.print("❌ 已取消", style="yellow")
            ctx.record_command("snapshot_delete", snapshot_id, "cancelled")
            return True
        if manager.delete_snapshot(snapshot_id):
            console.print(f"✅ 快照已删除: {snapshot_id}", style="green")
            ctx.record_command("snapshot_delete", snapshot_id, "success")
        else:
            console.print(f"❌ 删除失败: {snapshot_id}", style="red")
            ctx.record_command("snapshot_delete", snapshot_id, "failed")
    except Exception as e:  # noqa: BLE001
        console.print(f"❌ 删除快照失败: {e}", style="red")
        ctx.record_command("snapshot_delete", snapshot_id, "failed", str(e))
    return True


def handle_snapshot_prune(ctx, parsed):
    """/snapshot-prune [N]：清理自动触发的快照，仅保留最近 N 个（默认 10）。"""
    console = ctx.console
    if not _require_knowledge_management(ctx):
        return False
    arg = parsed.arg.strip()
    keep = 10
    if arg:
        try:
            keep = max(0, int(arg))
        except ValueError:
            console.print("❌ 保留数量必须是整数: /snapshot-prune [N]", style="yellow")
            return False
    try:
        from knowledge_snapshot import KnowledgeSnapshotManager
        manager = KnowledgeSnapshotManager()
        pending = manager.prune_preview(keep=keep, auto_only=True)
        if not pending:
            console.print(f"✅ 自动快照不超过 {keep} 个，无需清理", style="green")
            ctx.record_command("snapshot_prune", str(keep), "nothing")
            return True
        console.print(
            f"🧹 将删除 {len(pending)} 个自动快照（保留最近 {keep} 个，手动快照不受影响）:",
            style="yellow",
        )
        for snap in pending:
            console.print(f"  - {snap['snapshot_id']}  {snap['timestamp']}  ({snap['trigger']})", style="dim")
        if not _confirm(console, "确认清理? (y/n): "):
            console.print("❌ 已取消", style="yellow")
            ctx.record_command("snapshot_prune", str(keep), "cancelled")
            return True
        deleted = manager.prune(keep=keep, auto_only=True)
        console.print(f"✅ 已清理 {len(deleted)} 个自动快照", style="green")
        ctx.record_command("snapshot_prune", str(keep), "success")
    except Exception as e:  # noqa: BLE001
        console.print(f"❌ 清理快照失败: {e}", style="red")
        ctx.record_command("snapshot_prune", str(keep), "failed", str(e))
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
