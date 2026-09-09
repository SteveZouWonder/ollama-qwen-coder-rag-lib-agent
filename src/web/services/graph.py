"""知识图谱页：实体查询 / 构建 / 可视化数据。"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class GraphMixin:
    """知识图谱查询、构建与可视化数据（对齐 CLI ``/graph-*``）。"""

    # ---------- 知识图谱 ----------

    def query_graph_entity(self, entity_text: str) -> Dict[str, Any]:
        """查询实体，返回结构化字典。"""
        entity_text = (entity_text or "").strip()
        if not entity_text:
            return {"entities": [], "relations": [], "explanation": "实体名不能为空"}
        try:
            result = self.graph_query.query_entity(entity_text)
            return result.to_dict()
        except BaseException as exc:  # noqa: BLE001
            return {"entities": [], "relations": [], "explanation": f"查询失败: {exc}"}

    def graph_summary(self) -> Dict[str, Any]:
        """返回知识图谱概览。"""
        try:
            return self.graph_query.get_graph_summary()
        except BaseException as exc:  # noqa: BLE001
            return {"is_available": False, "error": str(exc)}

    # -- 知识图谱构建 --
    def graph_build(self, text: str, doc_id: str = "manual", doc_type: str = "text") -> str:
        text = (text or "").strip()
        if not text:
            return "[提示] 请输入用于构建知识图谱的文本"
        return self.run_tool(
            "knowledge_graph_build",
            {"text": text, "doc_id": doc_id or "manual", "doc_type": doc_type or "text"},
        )

    # 与 CLI ``/graph-query`` 一致的前缀 → query_type 映射
    GRAPH_QUERY_TYPES: Dict[str, str] = {
        "entity": "entity", "type": "type", "neighbors": "neighbors",
        "neighbor": "neighbors", "path": "path", "similar": "similar",
    }
    _CODE_SUFFIXES = {".py", ".js", ".ts", ".java", ".go", ".rs", ".c", ".cpp", ".h",
                      ".hpp", ".rb", ".php", ".cs", ".kt", ".swift"}

    def graph_query_typed(self, query: str, query_type: str = "entity") -> Dict[str, Any]:
        """带类型的图谱查询（entity/type/neighbors/path/similar）。

        与 CLI 一致：``query`` 中若带 ``type:`` / ``neighbors:`` / ``path:`` /
        ``similar:`` / ``entity:`` 前缀，则前缀优先于 ``query_type`` 参数。
        """
        query = (query or "").strip()
        if not query:
            return {"text": "[提示] 查询内容不能为空", "query_type": query_type or "entity"}
        qtype = self.GRAPH_QUERY_TYPES.get((query_type or "entity").strip().lower(), "entity")
        if ":" in query:
            prefix, rest = query.split(":", 1)
            mapped = self.GRAPH_QUERY_TYPES.get(prefix.strip().lower())
            if mapped and rest.strip():
                qtype, query = mapped, rest.strip()
        result = self.run_tool("knowledge_graph_query", {"query": query, "query_type": qtype})
        return {"text": result, "query_type": qtype, "query": query}

    def graph_build_file(self, file_path: str) -> str:
        """读取服务器上的文件构建图谱（等价 CLI ``/graph-build @<文件>``）。

        常见代码后缀使用 ``code`` 抽取策略，其余按 ``text``。
        """
        from pathlib import Path

        file_path = (file_path or "").strip().lstrip("@").strip()
        if not file_path:
            return "[提示] 请输入文件路径"
        path = Path(file_path).expanduser()
        scope_err = self.path_read_error(str(path))
        if scope_err:
            return f"[错误] {scope_err}"
        if not path.exists() or not path.is_file():
            return f"[错误] 文件不存在: {file_path}"
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except BaseException as exc:  # noqa: BLE001
            return f"[错误] 读取文件失败: {exc}"
        if not text.strip():
            return f"[提示] 文件内容为空: {file_path}"
        doc_type = "code" if path.suffix.lower() in self._CODE_SUFFIXES else "text"
        return self.graph_build(text, doc_id=path.name, doc_type=doc_type)

    # ---------- 知识图谱可视化 ----------

    def _graph_builder(self):
        try:
            from knowledge_graph import get_graph_builder
        except ImportError:  # pragma: no cover
            from src.knowledge_graph import get_graph_builder  # type: ignore
        return get_graph_builder()

    def graph_view_data(
        self, types: Optional[List[str]] = None, min_confidence: float = 0.0,
        max_nodes: int = 500, focus: Optional[str] = None, hops: int = 1, dim: int = 3,
    ) -> Dict[str, Any]:
        """可视化子图：节点/边列表 + 每个节点的布局坐标（``positions``）。"""
        try:
            builder = self._graph_builder()
            view = builder.subgraph_for_view(
                types=types, min_confidence=min_confidence, max_nodes=max_nodes,
                focus=focus, hops=hops,
            )
            view["positions"] = builder.layout_positions([n["id"] for n in view["nodes"]], dim=dim)
            view["dim"] = 3 if int(dim or 3) >= 3 else 2
            return view
        except BaseException as exc:  # noqa: BLE001
            return {"nodes": [], "edges": [], "positions": {}, "dim": dim,
                    "total_nodes": 0, "total_edges": 0, "truncated": False, "error": str(exc)}

    def graph_entity_types(self) -> List[str]:
        """图谱中出现过的实体类型（按数量倒序），供筛选控件使用。"""
        try:
            stats = self._graph_builder().get_statistics()
            return [k for k, _ in sorted(stats.entity_types.items(), key=lambda kv: -kv[1])]
        except BaseException:  # noqa: BLE001
            return []
