"""知识图谱页：带类型查询 / 概览 / 从文本或文件构建。"""  # pragma: no cover
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
    page_title("知识图谱", "文档入库时自动派生图谱；也可在此按类型查询或手动构建。")

    section("查询")
    with gr.Row(elem_classes=["cb-inline-actions"]):
        qtype = gr.Dropdown(
            choices=QUERY_TYPES, value="entity", show_label=False, container=False,
            scale=0, min_width=200, interactive=True,
        )
        query = gr.Textbox(placeholder=_PLACEHOLDER["entity"], show_label=False, container=False, scale=1)
        query_btn = gr.Button("查询", variant="primary", elem_classes=["cb-btn"], min_width=80)
        summary_btn = gr.Button("图谱概览", elem_classes=["cb-btn"], min_width=96)
    graph_result = result_md()

    qtype.change(lambda t: gr.update(placeholder=_PLACEHOLDER.get(t, "")), qtype, query, show_progress="hidden")
    query_btn.click(handlers["on_graph_query_typed"], [qtype, query], graph_result)
    query.submit(handlers["on_graph_query_typed"], [qtype, query], graph_result)
    summary_btn.click(handlers["on_graph_summary"], None, graph_result)

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
    build_btn.click(handlers["on_graph_build_any"], [source, gb_text], gb_result)
    return {}
