"""知识库页：入库 / 统计 / 文件管理 / 摘要与技能 / 快照。"""
from __future__ import annotations

import logging
import queue
import threading
from typing import Any, Dict, Iterator, List, Optional

from .base import StreamEvent

logger = logging.getLogger(__name__)


def _describe_chunking(fm, short: bool = False) -> str:
    """文件分块描述（与 CLI ``/file-list`` 同源）；``short`` 用于表格单列：``代码`` / ``文本``。"""
    try:
        from code_chunker import describe_file_chunking, strategy_display
    except ImportError:  # pragma: no cover
        from src.code_chunker import describe_file_chunking, strategy_display  # type: ignore
    strategy = str(getattr(fm, "chunk_strategy", "") or "text")
    if short:
        label = strategy_display(strategy)
        return "代码" if label.startswith("代码") else "文本"
    return describe_file_chunking(
        getattr(fm, "file_path", ""), strategy, int(getattr(fm, "symbol_count", 0) or 0)
    )


class KnowledgeMixin:
    """知识库管理（对齐 CLI ``/add`` ``/stats`` ``/file-*`` ``/snapshot-*`` ``/summary``）。"""

    # ---------- 知识库管理 ----------

    def _ingest_summary(self, file_count: int, doc_count: int, paths: Optional[List[str]] = None) -> str:
        """入库成功文案（与 CLI ``/add`` 同源）：文件数 · 片段数（· 代码文件按函数/类切分，符号数）。

        代码分块未启用且本次含代码文件时，追加一行一次性提示（进程内仅一次）。
        """
        try:
            from code_chunker import availability_hint_once, format_ingest_summary, language_for
        except ImportError:  # pragma: no cover
            from src.code_chunker import availability_hint_once, format_ingest_summary, language_for  # type: ignore
        stats = getattr(self.rag_engine, "last_ingest_stats", None) or {}
        if stats:
            text = format_ingest_summary(stats, file_count=file_count)
        else:
            text = f"已入库 {file_count} 个文件，共 {doc_count} 个片段"
        candidates = list(stats.keys()) or list(paths or [])
        if any(language_for(None, str(p)) for p in candidates):
            hint = availability_hint_once()
            if hint:
                text += f"\n💡 {hint}（详见「系统」页）"
        return text

    def _graph_note(self) -> str:
        return (
            "，已同步更新知识图谱"
            if getattr(self.rag_engine, "last_graph_derived", False)
            else "，知识图谱未自动更新（可在「知识图谱」页手动构建）"
        )

    def add_documents(self, file_paths: List[str], progress_callback=None) -> str:
        """把上传的文件加入知识库，返回人类可读的结果摘要。

        ``progress_callback`` 透传给 ``RAGEngine.add_documents``（``stage=chunk|embed`` 事件）。
        """
        if not file_paths:
            return "[提示] 未选择任何文件"

        loaded = 0
        added_files: List[str] = []
        errors: List[str] = []
        all_docs: List[Any] = []
        valid_paths: List[str] = []
        for path in file_paths:
            try:
                docs = self._load_documents(path)
                if not docs:
                    errors.append(f"无法加载: {path}")
                    continue
                all_docs.extend(docs)
                valid_paths.append(path)
                loaded += len(docs)
                added_files.append(path)
            except BaseException as exc:  # noqa: BLE001
                errors.append(f"{path}: {exc}")

        if all_docs:
            try:
                if progress_callback is not None:
                    self.rag_engine.add_documents(all_docs, valid_paths, progress_callback=progress_callback)
                else:
                    self.rag_engine.add_documents(all_docs, valid_paths)
            except BaseException as exc:  # noqa: BLE001
                return f"[错误] 入库失败: {exc}"

        if all_docs:
            lines = [f"[成功] {self._ingest_summary(len(added_files), loaded, valid_paths)}"]
        else:
            lines = [f"[成功] 已入库 {len(added_files)} 个文件，共 {loaded} 个片段"]
        if errors:
            lines.append("[部分失败]")
            lines.extend(f"  - {e}" for e in errors)
        return "\n".join(lines)

    def add_path(self, path: str, file_types: Optional[str] = None, progress_callback=None) -> str:
        """把服务器上的文件/目录**追加**入库（等价 CLI ``/add <path>``，可选类型过滤）。

        与 ``rebuild_index``（替换整个索引）不同，本方法只追加。``file_types`` 为
        逗号分隔的后缀（如 ``.pdf,.md``），等价 CLI ``--types``。
        """
        path = (path or "").strip()
        if not path:
            return "[提示] 请输入文件或目录路径"
        types = [t.strip() for t in (file_types or "").split(",") if t.strip()] or None
        try:
            docs = self._load_documents(path, types) if types else self._load_documents(path)
        except BaseException as exc:  # noqa: BLE001
            return f"[错误] 加载失败: {exc}"
        if not docs:
            return f"[提示] 未找到可加载的文档: {path}"
        try:
            if progress_callback is not None:
                self.rag_engine.add_documents(docs, [path], progress_callback=progress_callback)
            else:
                self.rag_engine.add_documents(docs, [path])
        except BaseException as exc:  # noqa: BLE001
            return f"[错误] 入库失败: {exc}"
        stats = getattr(self.rag_engine, "last_ingest_stats", None) or {}
        file_count = len(stats) if stats else 1
        return f"[成功] {self._ingest_summary(file_count, len(docs), [path])}{self._graph_note()}"

    def ingest_stream(self, file_paths: Optional[List[str]] = None, path: Optional[str] = None,
                      file_types: Optional[str] = None) -> Iterator[StreamEvent]:
        """流式入库：``progress`` 事件（``stage=chunk|embed``，带 current/total）+ 最终 ``answer``。

        ``file_paths`` 非空走上传路径（``add_documents``），否则走 ``add_path``。结果文案在
        ``answer.message``（含 ``[成功]/[提示]/[错误]`` 前缀，由 ``app._fmt_result`` 换图标）。
        """
        def run(q: "queue.Queue", cancel: threading.Event):
            def progress_cb(evt: Dict[str, Any]):
                q.put(StreamEvent("progress", evt.get("message", ""), evt))

            if file_paths:
                return self.add_documents(list(file_paths), progress_callback=progress_cb)
            return self.add_path(path or "", file_types, progress_callback=progress_cb)

        def on_finish(result_holder, error_holder):
            if "error" in error_holder:
                yield StreamEvent("error", f"入库失败: {error_holder['error']}")
                return
            yield StreamEvent("answer", str(result_holder.get("result") or ""), {})

        yield from self._bridge(run, on_finish)

    def get_stats(self) -> Dict[str, Any]:
        """返回知识库统计信息（含 ``total_documents`` 键）。"""
        try:
            return self.rag_engine.get_stats()
        except BaseException as exc:  # noqa: BLE001
            return {"error": str(exc)}

    def rebuild_index(self, data_path: Optional[str] = None) -> str:
        """重建知识库索引。"""
        try:
            docs = self._load_documents(data_path) if data_path else None
            if data_path:
                if not docs:
                    return f"[错误] 目录中无可加载文档: {data_path}"
                self.rag_engine.build_index(docs, file_paths=[data_path])
                return f"[成功] 已重建索引，共 {len(docs)} 个片段"
            return "[提示] 未指定数据路径"
        except BaseException as exc:  # noqa: BLE001
            return f"[错误] 重建失败: {exc}"

    def clear_index(self) -> str:
        """清空知识库索引。"""
        try:
            self.rag_engine.clear_index()
            return "[成功] 索引已清空"
        except BaseException as exc:  # noqa: BLE001
            return f"[错误] 清空失败: {exc}"

    # ---------- 文件管理 ----------

    @staticmethod
    def _file_meta_dict(manager, fm) -> Dict[str, Any]:
        try:
            size = manager._format_size(fm.file_size)
        except Exception:  # noqa: BLE001
            size = "?"
        upload = str(getattr(fm, "upload_time", "") or "")
        last = str(getattr(fm, "last_access", "") or "")
        return {
            "path": fm.file_path,
            "size": size,
            "size_bytes": int(getattr(fm, "file_size", 0) or 0),
            "type": str(getattr(fm, "persistence_type", "") or ""),
            "upload_time": upload[:19].replace("T", " "),
            "last_access": last[:19].replace("T", " "),
            "access_count": int(getattr(fm, "access_count", 0) or 0),
            "document_count": int(getattr(fm, "document_count", 0) or 0),
            "chunk_count": int(getattr(fm, "chunk_count", 0) or 0),
            "tags": list(getattr(fm, "tags", None) or []),
            "file_hash": getattr(fm, "file_hash", None),
            "chunk_strategy": str(getattr(fm, "chunk_strategy", "") or "text"),
            "symbol_count": int(getattr(fm, "symbol_count", 0) or 0),
            "chunking": _describe_chunking(fm),
            "chunking_short": _describe_chunking(fm, short=True),
        }

    def file_list(self) -> List[Dict[str, Any]]:
        """列出知识库已登记的文件（等价 /file-list），含类型/时间/片段数等明细。"""
        try:
            from file_metadata import get_global_metadata_manager
            manager = get_global_metadata_manager()
            return [self._file_meta_dict(manager, fm) for fm in manager.list_files()]
        except BaseException as exc:  # noqa: BLE001
            return [{"path": f"[错误] {exc}", "size": ""}]

    def file_info(self, path: str) -> Dict[str, Any]:
        """单个文件的元数据详情（等价 /file-info）。"""
        path = (path or "").strip()
        if not path:
            return {"error": "请输入文件路径"}
        try:
            from file_metadata import get_global_metadata_manager
            manager = get_global_metadata_manager()
            fm = manager.get_file_metadata(path)
            if fm is None:
                return {"error": f"文件不在知识库中: {path}"}
            return self._file_meta_dict(manager, fm)
        except BaseException as exc:  # noqa: BLE001
            return {"error": str(exc)}

    def file_cleanup_preview(self) -> List[Dict[str, Any]]:
        """待清理（临时/过期）文件列表，供二次确认前预览。"""
        try:
            from file_metadata import get_global_metadata_manager
            manager = get_global_metadata_manager()
            return [self._file_meta_dict(manager, fm) for fm in manager.get_files_to_cleanup()]
        except BaseException as exc:  # noqa: BLE001
            return [{"path": f"[错误] {exc}", "size": ""}]

    def file_cleanup(self) -> str:
        """清理临时/过期文件（等价 /file-cleanup）。"""
        try:
            from file_metadata import get_global_metadata_manager
            manager = get_global_metadata_manager()
            pending = manager.get_files_to_cleanup()
            if not pending:
                return "[提示] 没有需要清理的文件"
            cleaned = manager.cleanup_files()
            return f"[成功] 已清理 {len(cleaned)} 个文件"
        except BaseException as exc:  # noqa: BLE001
            return f"[错误] 清理失败: {exc}"

    def file_duplicates(self) -> List[Dict[str, Any]]:
        """按内容哈希找出重复登记的文件（等价 /file-deduplicate 的扫描阶段）。"""
        try:
            from file_metadata import get_global_metadata_manager
            manager = get_global_metadata_manager()
            seen: Dict[str, Any] = {}
            dups = []
            for fm in manager.list_files():
                h = getattr(fm, "file_hash", None)
                if not h:
                    continue
                if h in seen:
                    d = self._file_meta_dict(manager, fm)
                    d["duplicate_of"] = seen[h].file_path
                    dups.append(d)
                else:
                    seen[h] = fm
            return dups
        except BaseException as exc:  # noqa: BLE001
            return [{"path": f"[错误] {exc}", "size": ""}]

    def file_deduplicate(self) -> str:
        """移除重复登记（只删元数据，不删磁盘文件；等价 /file-deduplicate 确认后）。"""
        try:
            from file_metadata import get_global_metadata_manager
            manager = get_global_metadata_manager()
            dups = self.file_duplicates()
            if dups and dups[0].get("path", "").startswith("[错误]"):
                return dups[0]["path"]
            if not dups:
                return "[提示] 没有发现重复文件"
            for d in dups:
                manager.remove_file(d["path"])
            return f"[成功] 已移除 {len(dups)} 个重复登记"
        except BaseException as exc:  # noqa: BLE001
            return f"[错误] 去重失败: {exc}"

    def file_delete_preview(self, path: str) -> Dict[str, Any]:
        """删除文件前的影响预览（片段数 / 图谱节点边数 / 是否同名保留）。"""
        path = (path or "").strip()
        if not path:
            return {"error": "请先选择文件"}
        try:
            return dict(self.rag_engine.file_delete_preview(path))
        except BaseException as exc:  # noqa: BLE001
            return {"error": str(exc)}

    def remove_file(self, path: str) -> str:
        """从知识库删除文件：向量 chunk + 图谱贡献 + 元数据，不删磁盘文件（等价 /file-delete）。"""
        path = (path or "").strip()
        if not path:
            return "[提示] 请先选择要删除的文件"
        try:
            result = self.rag_engine.remove_file(path)
        except FileNotFoundError as exc:
            return f"[错误] {exc}"
        except BaseException as exc:  # noqa: BLE001
            return f"[错误] 删除失败: {exc}"
        name = result.get("file_name") or path.rsplit("/", 1)[-1]
        graph = "图谱已更新" if result.get("graph_updated") else (result.get("note") or "图谱未变更")
        return f"[成功] 已删除 {name}：{result.get('chunks_deleted', 0)} 个片段，{graph}"

    def file_stats(self) -> Dict[str, Any]:
        """文件统计概览（等价 /file-stats）。"""
        try:
            from file_metadata import get_global_metadata_manager
            manager = get_global_metadata_manager()
            get_stats = getattr(manager, "get_statistics", None) or getattr(manager, "get_stats", None)
            if callable(get_stats):
                return get_stats()
            files = manager.list_files()
            return {"total_files": len(files)}
        except BaseException as exc:  # noqa: BLE001
            return {"error": str(exc)}

    # ---------- 知识库管理 ----------

    def generate_skills(self) -> str:
        """从知识库生成 Skills（等价 /generate-skills）。"""
        try:
            from knowledge_to_skills import KnowledgeToSkillsEngine
            engine = KnowledgeToSkillsEngine()
            results = engine.convert()
            lines = [f"[成功] 生成 {len(results)} 个 Skills:"]
            for key, path in results.items():
                lines.append(f"  • {key}: {path}")
            return "\n".join(lines)
        except BaseException as exc:  # noqa: BLE001
            return f"[错误] 生成 Skills 失败: {exc}"

    def knowledge_summary_data(self) -> List[Dict[str, Any]]:
        """知识库文档摘要的结构化版本（供表格展示）。"""
        try:
            from knowledge_to_skills import KnowledgeToSkillsEngine
            summary = KnowledgeToSkillsEngine().get_document_summary()
            return [
                {
                    "file_name": d.get("file_name", ""),
                    "file_path": d.get("file_path", ""),
                    "kind": "通用" if d.get("is_generic") else "项目",
                    "confidence": float(d.get("confidence", 0) or 0),
                    "chunk_count": int(d.get("chunk_count", 0) or 0),
                    "topics": ", ".join(str(t) for t in (d.get("topics") or [])),
                }
                for d in summary
            ]
        except BaseException as exc:  # noqa: BLE001
            return [{"file_name": f"[错误] {exc}"}]

    def snapshot_list_data(self) -> List[Dict[str, Any]]:
        """快照列表的结构化版本（供表格展示）。"""
        try:
            from knowledge_snapshot import KnowledgeSnapshotManager
            return [
                {
                    "snapshot_id": s.get("snapshot_id", ""),
                    "timestamp": str(s.get("timestamp", "")),
                    "document_count": s.get("document_count", 0),
                    "total_chunks": s.get("total_chunks", 0),
                    "trigger": s.get("trigger", ""),
                }
                for s in KnowledgeSnapshotManager().list_snapshots()
            ]
        except BaseException as exc:  # noqa: BLE001
            return [{"snapshot_id": f"[错误] {exc}"}]

    def knowledge_summary(self) -> str:
        """知识库文档摘要（等价 /knowledge-summary）。"""
        try:
            from knowledge_to_skills import KnowledgeToSkillsEngine
            engine = KnowledgeToSkillsEngine()
            summary = engine.get_document_summary()
            lines = ["知识库文档摘要:"]
            for doc in summary:
                kind = "通用" if doc.get("is_generic") else "项目"
                lines.append(
                    f"- {doc.get('file_name')}（{kind}, "
                    f"置信度 {doc.get('confidence', 0):.2f}, "
                    f"chunks {doc.get('chunk_count', 0)}）"
                )
            return "\n".join(lines) if summary else "知识库暂无文档"
        except BaseException as exc:  # noqa: BLE001
            return f"[错误] 获取知识库摘要失败: {exc}"

    def snapshot_list(self) -> str:
        """列出知识库快照（等价 /snapshot-list）。"""
        try:
            from knowledge_snapshot import KnowledgeSnapshotManager
            manager = KnowledgeSnapshotManager()
            snapshots = manager.list_snapshots()
            if not snapshots:
                return "暂无快照"
            lines = [f"共 {len(snapshots)} 个快照:"]
            for snap in snapshots:
                lines.append(
                    f"- `{snap['snapshot_id']}` {snap['timestamp']} "
                    f"（文档 {snap['document_count']}, chunks {snap['total_chunks']}, "
                    f"触发 {snap['trigger']}）"
                )
            return "\n".join(lines)
        except BaseException as exc:  # noqa: BLE001
            return f"[错误] 获取快照列表失败: {exc}"

    def snapshot_create(self) -> str:
        """创建知识库快照（等价 /snapshot-create）。"""
        try:
            from knowledge_snapshot import KnowledgeSnapshotManager
            manager = KnowledgeSnapshotManager()
            snapshot = manager.create_snapshot(trigger="manual")
            return (
                f"[成功] 快照已创建: {snapshot.snapshot_id}\n"
                f"时间: {snapshot.timestamp}，文档数: {len(snapshot.documents)}"
            )
        except BaseException as exc:  # noqa: BLE001
            return f"[错误] 创建快照失败: {exc}"

    def snapshot_restore(self, snapshot_id: str) -> str:
        """为指定快照生成恢复脚本（等价 /snapshot-restore）。"""
        snapshot_id = (snapshot_id or "").strip()
        if not snapshot_id:
            return "[提示] 请指定快照 ID"
        try:
            from knowledge_snapshot import KnowledgeSnapshotManager, RestoreHelper
            manager = KnowledgeSnapshotManager()
            snapshot = manager.load_snapshot(snapshot_id)
            if not snapshot:
                return f"[错误] 快照不存在: {snapshot_id}"
            helper = RestoreHelper(manager)
            script_file = helper.generate_restore_script(snapshot_id)
            return (
                f"[成功] 恢复脚本已生成: {script_file}\n"
                f"（文档数 {len(snapshot.documents)}）请运行该脚本恢复知识库。"
            )
        except BaseException as exc:  # noqa: BLE001
            return f"[错误] 恢复快照失败: {exc}"

    # ---------- 快照：详情 / 恢复 / 删除 / 批量清理 ----------

    @staticmethod
    def _snapshot_manager():
        from knowledge_snapshot import KnowledgeSnapshotManager

        return KnowledgeSnapshotManager()

    def snapshot_info(self, snapshot_id: str) -> Dict[str, Any]:
        """快照详情（文档清单 + 每个文件是否仍在磁盘 + 模型配置 + 触发方式）。"""
        snapshot_id = (snapshot_id or "").strip()
        if not snapshot_id:
            return {"error": "请指定快照 ID"}
        try:
            info = self._snapshot_manager().snapshot_info(snapshot_id)
            return info or {"error": f"快照不存在: {snapshot_id}"}
        except BaseException as exc:  # noqa: BLE001
            return {"error": str(exc)}

    def snapshot_delete(self, snapshot_id: str) -> str:
        """删除单个快照（等价 /snapshot-delete）。"""
        snapshot_id = (snapshot_id or "").strip()
        if not snapshot_id:
            return "[提示] 请指定快照 ID"
        try:
            ok = self._snapshot_manager().delete_snapshot(snapshot_id)
            return f"[成功] 已删除快照 {snapshot_id}" if ok else f"[错误] 快照不存在: {snapshot_id}"
        except BaseException as exc:  # noqa: BLE001
            return f"[错误] 删除快照失败: {exc}"

    def snapshot_prune_preview(self, keep: int = 10) -> List[Dict[str, Any]]:
        """批量清理预览：将被删除的自动快照列表。"""
        try:
            return list(self._snapshot_manager().prune_preview(keep=int(keep or 0), auto_only=True))
        except BaseException as exc:  # noqa: BLE001
            return [{"snapshot_id": f"[错误] {exc}"}]

    def snapshot_prune(self, keep: int = 10) -> str:
        """批量清理自动快照，保留最近 ``keep`` 个（等价 /snapshot-prune）。"""
        try:
            deleted = self._snapshot_manager().prune(keep=int(keep or 0), auto_only=True)
        except BaseException as exc:  # noqa: BLE001
            return f"[错误] 清理失败: {exc}"
        if not deleted:
            return "[提示] 没有需要清理的自动快照"
        return f"[成功] 已清理 {len(deleted)} 个自动快照，保留最近 {int(keep or 0)} 个"

    def snapshot_restore_apply(self, snapshot_id: str, mode: str = "append", progress=None) -> Dict[str, Any]:
        """阻塞式真正恢复快照（``append`` 追加 / ``replace`` 替换）。"""
        snapshot_id = (snapshot_id or "").strip()
        if not snapshot_id:
            return {"ok": False, "error": "请指定快照 ID"}
        try:
            return self._snapshot_manager().restore_apply(
                snapshot_id, self.rag_engine, mode=mode,
                load_documents=self._load_documents, progress=progress,
            )
        except BaseException as exc:  # noqa: BLE001
            return {"ok": False, "error": str(exc)}

    def snapshot_restore_stream(self, snapshot_id: str, mode: str = "append") -> Iterator[StreamEvent]:
        """流式恢复快照：逐文件 ``progress`` 事件 + 最终 ``answer``（data 为结果 dict）。"""
        snapshot_id = (snapshot_id or "").strip()
        if not snapshot_id:
            yield StreamEvent("error", "请指定快照 ID")
            return

        def run(q: "queue.Queue", cancel: threading.Event):
            def progress_cb(evt: Dict[str, Any]):
                q.put(StreamEvent("progress", evt.get("message", ""), evt))

            return self.snapshot_restore_apply(snapshot_id, mode=mode, progress=progress_cb)

        def on_finish(result_holder, error_holder):
            if "error" in error_holder:
                yield StreamEvent("error", f"恢复失败: {error_holder['error']}")
                return
            result = result_holder.get("result") or {}
            if not result.get("ok"):
                yield StreamEvent("error", str(result.get("error") or "恢复失败"))
                return
            yield StreamEvent(
                "answer",
                f"恢复完成：成功 {result.get('restored', 0)}，跳过 {result.get('skipped', 0)}，"
                f"失败 {result.get('failed', 0)}",
                result,
            )

        yield from self._bridge(run, on_finish)
