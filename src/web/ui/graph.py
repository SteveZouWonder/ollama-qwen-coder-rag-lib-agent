"""知识图谱页：3D / 2D 图谱视图 + 概览卡片 / 带类型查询 / 从文本或文件构建。"""  # pragma: no cover
from __future__ import annotations

from typing import Any, Callable, Dict

import gradio as gr

from .common import page_title, result_md, section

QUERY_TYPES = [
    ("实体（模糊匹配）", "entity"),
    ("按类型列出实体", "type"),
    ("邻居", "neighbors"),
    ("两实体间路径（A->B）", "path"),
    ("相似实体", "similar"),
]

_PLACEHOLDER = {
    "entity": "实体名，如 DNS",
    "type": "实体类型：person / organization / location / concept / technology / tool / language / framework / other",
    "neighbors": "实体名，列出与之相连的实体",
    "path": "两个实体，用 -> 连接，如 DNS->HTTP",
    "similar": "实体名，查找相似实体",
}


def build_graph_page(service, handlers: Dict[str, Callable]) -> Dict[str, Any]:  # pragma: no cover
    page_title("知识图谱", "文档入库时自动派生图谱；可在此浏览 3D / 2D 视图、按类型查询或手动构建。")

    # ---------------- 图谱视图 ----------------
    section("图谱视图")
    summary_cards = gr.HTML(handlers["on_graph_summary_cards"]())
    with gr.Row(elem_classes=["cb-graph-controls"]):
        dim = gr.Radio(
            ["3D", "2D"], value="3D", show_label=False, container=False,
            elem_classes=["cb-segment"], scale=0, min_width=120,
        )
        types = gr.Dropdown(
            choices=handlers["on_graph_type_choices"](), value=[], multiselect=True,
            label="实体类型（空=全部）", scale=2, min_width=220, interactive=True,
        )
        min_conf = gr.Slider(0.0, 1.0, value=0.6, step=0.05, label="最小置信度", scale=1, min_width=160)
        max_nodes = gr.Number(value=500, minimum=10, maximum=5000, precision=0, label="最多节点数", scale=0, min_width=110)
    with gr.Row(elem_classes=["cb-graph-controls"]):
        focus = gr.Textbox(placeholder="聚焦实体（可选，如 Python）", show_label=False, container=False, scale=2)
        hops = gr.Radio([1, 2], value=1, label="跳数", show_label=True, container=True, scale=0, min_width=120,
                        elem_classes=["cb-hops"])
        edge_labels = gr.Checkbox(value=False, label="边标签（2D）", container=False, scale=0, min_width=120)
        render_btn = gr.Button("渲染", variant="primary", elem_classes=["cb-btn"], min_width=80)
        refresh_types_btn = gr.Button("刷新类型", elem_classes=["cb-btn"], min_width=90)
    graph_plot = gr.Plot(show_label=False, elem_classes=["cb-graph-plot"])
    view_stats = gr.Markdown("_点击「渲染」或切换任一控件生成图谱视图_", elem_classes=["cb-muted"])

    view_inputs = [dim, types, min_conf, max_nodes, focus, hops, edge_labels]
    view_outputs = [graph_plot, view_stats, summary_cards]
    render_btn.click(handlers["on_graph_view"], view_inputs, view_outputs, show_progress="minimal")
    focus.submit(handlers["on_graph_view"], view_inputs, view_outputs, show_progress="minimal")
    for ctrl in (dim, types, min_conf, max_nodes, hops, edge_labels):
        ctrl.change(handlers["on_graph_view"], view_inputs, view_outputs, show_progress="minimal")
    refresh_types_btn.click(
        lambda: gr.update(choices=handlers["on_graph_type_choices"]()), None, types, show_progress="hidden",
    )

    # ---------------- 查询 ----------------
    section("查询")
    with gr.Row(elem_classes=["cb-inline-actions"]):
        qtype = gr.Dropdown(
            choices=QUERY_TYPES, value="entity", show_label=False, container=False,
            scale=0, min_width=200, interactive=True,
        )
        query = gr.Textbox(placeholder=_PLACEHOLDER["entity"], show_label=False, container=False, scale=1)
        query_btn = gr.Button("查询", variant="primary", elem_classes=["cb-btn"], min_width=80)
    graph_result = result_md()

    qtype.change(lambda t: gr.update(placeholder=_PLACEHOLDER.get(t, "")), qtype, query, show_progress="hidden")
    query_btn.click(handlers["on_graph_query_typed"], [qtype, query], graph_result)
    query.submit(handlers["on_graph_query_typed"], [qtype, query], graph_result)

    # ---------------- 构建 ----------------
    section("构建")
    with gr.Row(elem_classes=["cb-inline-actions"]):
        source = gr.Radio(
            ["文本", "文件路径"], value="文本", show_label=False, container=False,
            elem_classes=["cb-segment"], scale=0, min_width=200,
        )
        build_btn = gr.Button("构建图谱", variant="primary", elem_classes=["cb-btn"], min_width=100)
    gb_text = gr.Textbox(
        lines=4, placeholder="输入用于抽取实体与关系的文本…", show_label=False, container=False,
    )
    gb_result = result_md()

    source.change(
        lambda s: gr.update(
            lines=1 if s.startswith("文件") else 4,
            placeholder="服务器上的文件路径，如 ~/notes/dns.md（代码文件自动按 code 抽取）"
            if s.startswith("文件") else "输入用于抽取实体与关系的文本…",
        ),
        source, gb_text, show_progress="hidden",
    )
    # 构建完成后刷新视图与类型选项
    build_btn.click(handlers["on_graph_build_any"], [source, gb_text], gb_result).then(
        handlers["on_graph_view"], view_inputs, view_outputs, show_progress="minimal",
    ).then(lambda: gr.update(choices=handlers["on_graph_type_choices"]()), None, types, show_progress="hidden")

    return {"render": handlers["on_graph_view"], "inputs": view_inputs, "outputs": view_outputs}
