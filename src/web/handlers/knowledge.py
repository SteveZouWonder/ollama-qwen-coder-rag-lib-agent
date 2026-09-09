"""知识库页处理器：入库（流式）/ 统计卡片 / 文件管理 / 快照 / 摘要与技能。"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from ..formatters import (
    ProgressTracker,
    _SNAPSHOT_TRIGGER_LABEL,
    _fmt_result,
    format_elapsed,
    format_file_action_bar,
    format_file_delete_prompt,
    format_file_info,
    format_kv_table,
    format_prune_preview,
    format_restore_result,
    format_snapshot_info,
    format_stats,
    format_stats_cards,
    snapshot_doc_rows,
)
from ..services import WebService


def build_knowledge_handlers(service: WebService) -> Dict[str, Any]:
    """知识库页处理器：入库（流式）/ 统计卡片 / 文件管理 / 快照 / 摘要与技能（由 ``app.build_handlers`` 汇总）。"""

    def on_upload(file_paths: Optional[List[str]]) -> Tuple[str, str]:
        msg = service.add_documents(file_paths or [])
        return msg, format_stats(service.get_stats())

    def _ingest_stream(**kwargs):
        """流式入库公共实现：yield (结果 Markdown, 统计卡片 HTML)。

        进行中：结果区显示「⏳ 切分 x/y · 嵌入 m/n · 已用时」+ 处理过程；完成后显示
        结果文案（含代码分块摘要与一次性缺依赖提示）并刷新统计卡片。
        """
        tracker = ProgressTracker()
        tracker.current = "准备入库…"
        cards = on_stats_cards()  # 进行中保持原卡片不变，完成后刷新
        yield tracker.render_status(), cards
        final = None
        for evt in service.ingest_stream(**kwargs):
            if evt.kind == "progress":
                tracker.add(evt.message, evt.data if isinstance(evt.data, dict) else None)
                yield tracker.render_status() + "\n\n" + tracker.render_steps("入库进度"), cards
            elif evt.kind == "heartbeat":
                yield tracker.render_status() + "\n\n" + tracker.render_steps("入库进度"), cards
            elif evt.kind == "answer":
                final = evt
            elif evt.kind == "cancelled":
                yield tracker.render_status("cancelled"), cards
                return
            elif evt.kind == "error":
                yield f"❌ {evt.message}", on_stats_cards()
                return
        if final is None:
            yield tracker.render_status("error", "未获得结果"), on_stats_cards()
            return
        msg = _fmt_result(str(final.message or ""))
        ok = msg.startswith("✅")
        took = f" · 用时 {format_elapsed(tracker.elapsed())}" if ok else ""
        yield msg + took, on_stats_cards()

    def on_upload_stream(file_paths: Optional[List[str]]):
        """上传入库（流式进度）。"""
        if not file_paths:
            yield "💡 未选择任何文件", on_stats_cards()
            return
        yield from _ingest_stream(file_paths=list(file_paths))

    def on_add_path_stream(path: str, file_types: str = ""):
        """从路径追加入库（流式进度，等价 CLI /add）。"""
        if not (path or "").strip():
            yield "💡 请输入文件或目录路径", on_stats_cards()
            return
        yield from _ingest_stream(path=path, file_types=file_types)

    def on_refresh_stats() -> str:
        return format_stats(service.get_stats())

    def on_clear_index() -> Tuple[str, str]:
        msg = service.clear_index()
        return msg, format_stats(service.get_stats())

    def on_rebuild_index(data_path: str) -> Tuple[str, str]:
        """按路径重建知识库索引（等价 CLI --data 构建）。"""
        msg = service.rebuild_index((data_path or "").strip() or None)
        return msg, format_stats(service.get_stats())

    def on_file_list() -> str:
        files = service.file_list()
        if not files:
            return "_知识库中暂无已登记的文件_"
        lines = ["### 📁 文件列表", ""]
        for fm in files:
            lines.append(f"- `{fm.get('path')}`（{fm.get('size', '?')}）")
        return "\n".join(lines)

    def on_file_stats() -> str:
        stats = service.file_stats()
        if "error" in stats:
            return f"[错误] {stats['error']}"
        return "\n".join(f"- {k}: **{v}**" for k, v in stats.items())

    def on_generate_skills() -> str:
        return service.generate_skills()

    def on_knowledge_summary() -> str:
        return service.knowledge_summary()

    def on_snapshot_list() -> str:
        return service.snapshot_list()

    def on_snapshot_create() -> str:
        return service.snapshot_create()

    def on_snapshot_restore(snapshot_id: str) -> str:
        return service.snapshot_restore(snapshot_id)

    # ---------- 知识库：追加入库 / 卡片统计 / 文件管理 / 快照 / 摘要 ----------

    def on_stats_cards() -> str:
        stats = service.get_stats()
        files = service.file_list()
        count = len([f for f in files if not str(f.get("path", "")).startswith("[错误]")])
        return format_stats_cards(stats, file_count=count)

    def on_add_path(path: str, file_types: str = "") -> Tuple[str, str]:
        """追加服务器上的文件/目录入库（等价 CLI /add）。返回 (结果, 统计卡片)。"""
        return _fmt_result(service.add_path(path, file_types)), on_stats_cards()

    _FILE_HEADERS = ["文件", "大小", "类型", "上传时间", "片段 · 分块", "访问", "路径"]

    def on_file_table() -> List[List[Any]]:
        """文件表：首列文件名便于浏览，末列完整路径供选中行取值。"""
        rows = []
        for f in service.file_list():
            path = str(f.get("path", ""))
            name = path.rsplit("/", 1)[-1] if "/" in path else path
            chunking = str(f.get("chunking_short") or "文本")
            rows.append([
                name, f.get("size", ""), f.get("type", ""),
                f.get("upload_time", ""), f"{f.get('chunk_count', 0)} · {chunking}", f.get("access_count", 0), path,
            ])
        return rows

    def on_file_info(path: str) -> str:
        return format_file_info(service.file_info(path))

    def on_file_stats_md() -> str:
        stats = service.file_stats()
        if "error" in stats:
            return f"❌ {stats['error']}"
        labels = {
            "total_files": "文件总数", "total_size_formatted": "总大小",
            "permanent_count": "永久", "temporary_count": "临时", "session_count": "会话级",
            "cleanup_count": "待清理",
        }
        rows = [(labels.get(k, k), v) for k, v in stats.items() if k != "total_size"]
        return format_kv_table(rows)

    def on_file_cleanup_preview() -> str:
        pending = service.file_cleanup_preview()
        if not pending:
            return "✅ 没有需要清理的文件"
        if str(pending[0].get("path", "")).startswith("[错误]"):
            return f"❌ {pending[0]['path']}"
        lines = [f"🧹 发现 {len(pending)} 个待清理文件（临时/过期，**将从磁盘删除**）：", ""]
        lines.extend(f"- `{p.get('path')}`（{p.get('type')}）" for p in pending[:20])
        if len(pending) > 20:
            lines.append(f"- … 共 {len(pending)} 个")
        return "\n".join(lines)

    def on_file_cleanup() -> Tuple[str, List[List[Any]]]:
        return _fmt_result(service.file_cleanup()), on_file_table()

    def on_file_dedupe_preview() -> str:
        dups = service.file_duplicates()
        if not dups:
            return "✅ 没有发现重复文件"
        if str(dups[0].get("path", "")).startswith("[错误]"):
            return f"❌ {dups[0]['path']}"
        lines = [f"⚠️ 发现 {len(dups)} 个重复登记（只移除登记，不删磁盘文件）：", ""]
        lines.extend(f"- `{d.get('path')}` ⟶ 与 `{d.get('duplicate_of')}` 重复" for d in dups[:20])
        return "\n".join(lines)

    def on_file_dedupe() -> Tuple[str, List[List[Any]]]:
        return _fmt_result(service.file_deduplicate()), on_file_table()

    # -- 文件「⋯」操作条：删除文件（向量 + 图谱 + 元数据，不删磁盘）--

    def on_file_action_bar(path: str) -> str:
        return format_file_action_bar(path)

    def on_file_delete_preview(path: str) -> str:
        return format_file_delete_prompt(service.file_delete_preview(path))

    def on_file_delete(path: str) -> Tuple[str, List[List[Any]], str]:
        """删除文件：返回 (结果, 刷新后的文件表, 刷新后的统计卡片)。"""
        msg = _fmt_result(service.remove_file(path))
        return msg, on_file_table(), on_stats_cards()

    _SNAPSHOT_HEADERS = ["快照 ID", "时间", "文档", "片段", "触发"]
    _SNAPSHOT_DOC_HEADERS = ["状态", "文件", "类型", "片段", "路径"]

    def on_snapshot_table() -> List[List[Any]]:
        return [
            [s.get("snapshot_id", ""), str(s.get("timestamp", ""))[:19].replace("T", " "),
             s.get("document_count", 0), s.get("total_chunks", 0),
             _SNAPSHOT_TRIGGER_LABEL.get(s.get("trigger", ""), s.get("trigger", ""))]
            for s in service.snapshot_list_data()
        ]

    def on_snapshot_create_table() -> Tuple[str, List[List[Any]]]:
        return _fmt_result(service.snapshot_create()), on_snapshot_table()

    # -- 快照「⋯」操作条：详情 / 恢复 / 删除 / 批量清理 --

    def on_snapshot_info(snapshot_id: str) -> Tuple[str, List[List[Any]]]:
        """快照详情：返回 (键值表 Markdown, 文档清单表格行)。"""
        info = service.snapshot_info(snapshot_id)
        return format_snapshot_info(info), snapshot_doc_rows(info)

    def on_snapshot_delete(snapshot_id: str) -> Tuple[str, List[List[Any]]]:
        return _fmt_result(service.snapshot_delete(snapshot_id)), on_snapshot_table()

    def on_snapshot_prune_preview(keep: float = 10) -> str:
        keep_n = int(keep or 0)
        return format_prune_preview(service.snapshot_prune_preview(keep_n), keep_n)

    def on_snapshot_prune(keep: float = 10) -> Tuple[str, List[List[Any]]]:
        return _fmt_result(service.snapshot_prune(int(keep or 0))), on_snapshot_table()

    def on_snapshot_restore_stream(snapshot_id: str, mode: str = "append"):
        """流式恢复快照：yield (状态行, 结果 Markdown)。"""
        snapshot_id = (snapshot_id or "").strip()
        if not snapshot_id:
            yield "_请先选中一个快照_", ""
            return
        tracker = ProgressTracker()
        tracker.current = "准备恢复…"
        yield tracker.render_status(), ""
        final = None
        for evt in service.snapshot_restore_stream(snapshot_id, mode=mode):
            if evt.kind == "progress":
                tracker.add(evt.message, evt.data if isinstance(evt.data, dict) else None)
                yield tracker.render_status(), tracker.render_steps("恢复进度")
            elif evt.kind == "heartbeat":
                yield tracker.render_status(), tracker.render_steps("恢复进度")
            elif evt.kind == "answer":
                final = evt
            elif evt.kind == "cancelled":
                yield tracker.render_status("cancelled"), tracker.render_steps("恢复进度", done=True)
                return
            elif evt.kind == "error":
                yield tracker.render_status("error"), f"❌ {evt.message}"
                return
        if final is None:
            yield tracker.render_status("error", "未获得结果"), ""
            return
        data = final.data if isinstance(final.data, dict) else {}
        yield tracker.render_status("done"), format_restore_result(data)

    _SUMMARY_HEADERS = ["文件", "类型", "置信度", "片段", "主题"]

    def on_knowledge_summary_table() -> List[List[Any]]:
        return [
            [d.get("file_name", ""), d.get("kind", ""),
             f"{d.get('confidence', 0):.2f}" if isinstance(d.get("confidence"), (int, float)) else "",
             d.get("chunk_count", 0), d.get("topics", "")]
            for d in service.knowledge_summary_data()
        ]

    return {
        "on_upload": on_upload,
        "on_upload_stream": on_upload_stream,
        "on_add_path_stream": on_add_path_stream,
        "on_refresh_stats": on_refresh_stats,
        "on_clear_index": on_clear_index,
        "on_rebuild_index": on_rebuild_index,
        "on_file_list": on_file_list,
        "on_file_stats": on_file_stats,
        "on_generate_skills": on_generate_skills,
        "on_knowledge_summary": on_knowledge_summary,
        "on_snapshot_list": on_snapshot_list,
        "on_snapshot_create": on_snapshot_create,
        "on_snapshot_restore": on_snapshot_restore,
        "on_stats_cards": on_stats_cards,
        "on_add_path": on_add_path,
        "on_file_table": on_file_table,
        "on_file_info": on_file_info,
        "on_file_stats_md": on_file_stats_md,
        "on_file_cleanup_preview": on_file_cleanup_preview,
        "on_file_cleanup": on_file_cleanup,
        "on_file_dedupe_preview": on_file_dedupe_preview,
        "on_file_dedupe": on_file_dedupe,
        "on_file_action_bar": on_file_action_bar,
        "on_file_delete_preview": on_file_delete_preview,
        "on_file_delete": on_file_delete,
        "on_snapshot_table": on_snapshot_table,
        "on_snapshot_create_table": on_snapshot_create_table,
        "on_snapshot_info": on_snapshot_info,
        "on_snapshot_delete": on_snapshot_delete,
        "on_snapshot_prune_preview": on_snapshot_prune_preview,
        "on_snapshot_prune": on_snapshot_prune,
        "on_snapshot_restore_stream": on_snapshot_restore_stream,
        "on_knowledge_summary_table": on_knowledge_summary_table,
        "headers": {
            "files": _FILE_HEADERS,
            "snapshots": _SNAPSHOT_HEADERS,
            "summary": _SUMMARY_HEADERS,
            "snapshot_docs": _SNAPSHOT_DOC_HEADERS,
        },
    }
