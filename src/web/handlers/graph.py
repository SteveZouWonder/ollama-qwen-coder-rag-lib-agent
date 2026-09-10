"""知识图谱页处理器：实体查询 / 概览 / 构建 / 3D · 2D 可视化。"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..formatters import (
    _fmt_result,
    build_graph_figure,
    format_graph_result,
    format_graph_summary_cards,
    format_graph_view_stats,
)
from ..services import WebService


def build_graph_handlers(service: WebService) -> Dict[str, Any]:
    """知识图谱页处理器：实体查询 / 概览 / 构建 / 3D · 2D 可视化（由 ``app.build_handlers`` 汇总）。"""

    def on_query_graph(entity: str) -> str:
        return format_graph_result(service.query_graph_entity(entity))

    def on_graph_summary() -> str:
        """展示知识图谱概览（等价 service.graph_summary）。"""
        summary = service.graph_summary()
        if not summary.get("is_available", True) and summary.get("error"):
            return f"_知识图谱不可用：{summary.get('error')}_"
        lines = ["### 🕸️ 知识图谱概览", ""]
        for k, v in summary.items():
            lines.append(f"- {k}: **{v}**")
        return "\n".join(lines)

    def on_graph_build(text: str) -> str:
        return service.graph_build(text)

    # ---------- 知识图谱：带类型查询 / 文件构建 ----------

    def on_graph_query_typed(query_type: str, query: str) -> str:
        result = service.graph_query_typed(query, query_type or "entity")
        return _fmt_result(str(result.get("text", "")))

    def on_graph_build_any(source: str, text: str) -> str:
        """按来源构建：``文件路径`` 读取服务器文件，否则按文本。"""
        if (source or "").startswith("文件"):
            return _fmt_result(service.graph_build_file(text))
        return _fmt_result(service.graph_build(text))

    # ---------- 知识图谱：3D / 2D 可视化 ----------

    def on_graph_type_choices() -> List[str]:
        return service.graph_entity_types()

    def on_graph_summary_cards() -> str:
        return format_graph_summary_cards(service.graph_summary())

    def on_graph_view(
        dim_label: str = "3D", types: Optional[List[str]] = None, min_confidence: float = 0.6,
        max_nodes: float = 500, focus: str = "", hops: float = 1, edge_labels: bool = False,
    ):
        """渲染图谱视图：返回 (Plotly Figure 或 None, 视图统计 Markdown, 概览卡片 HTML)。"""
        dim = 3 if str(dim_label or "3D").upper().startswith("3") else 2
        view = service.graph_view_data(
            types=list(types or []) or None, min_confidence=float(min_confidence or 0),
            max_nodes=int(max_nodes or 500), focus=(focus or "").strip() or None,
            hops=int(hops or 1), dim=dim,
        )
        view["focus"] = (focus or "").strip()
        view["hops"] = int(hops or 1)
        stats_md = format_graph_view_stats(view)
        cards = on_graph_summary_cards()
        try:
            fig = build_graph_figure(
                view.get("nodes") or [], view.get("edges") or [], dim=dim,
                positions=view.get("positions") or None, edge_labels=bool(edge_labels) and dim == 2,
            )
        except ImportError:
            return None, "❌ 未安装 plotly：`pip install plotly` 后重启即可显示图谱视图", cards
        except Exception as exc:  # noqa: BLE001
            return None, f"❌ 渲染失败：{exc}", cards
        return fig, stats_md, cards

    return {
        "on_query_graph": on_query_graph,
        "on_graph_summary": on_graph_summary,
        "on_graph_build": on_graph_build,
        "on_graph_query_typed": on_graph_query_typed,
        "on_graph_build_any": on_graph_build_any,
        "on_graph_type_choices": on_graph_type_choices,
        "on_graph_summary_cards": on_graph_summary_cards,
        "on_graph_view": on_graph_view,
    }
