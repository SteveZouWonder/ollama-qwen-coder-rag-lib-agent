"""知识库页：文档入库 / 文件管理 / 快照 / Skills 与摘要。"""  # pragma: no cover
from __future__ import annotations

from typing import Any, Callable, Dict

import gradio as gr

from .common import Confirm, page_title, pick_cell, result_md, section, table


def build_knowledge_page(service, handlers: Dict[str, Callable]) -> Dict[str, Any]:  # pragma: no cover
    page_title("知识库", "上传或追加文档进入向量库；管理已登记文件、快照与 Skills。")
    stats_cards = gr.HTML(handlers["on_stats_cards"]())
    headers = handlers["headers"]

    with gr.Tabs():
        # ---------------- 文档 ----------------
        with gr.Tab("文档入库"):
            with gr.Row(equal_height=False):
                with gr.Column(scale=1, min_width=320):
                    section("上传文件（追加）")
                    upload = gr.File(
                        file_count="multiple", type="filepath", show_label=False,
                        file_types=None, height=140,
                    )
                    upload_result = result_md()
                with gr.Column(scale=1, min_width=320):
                    section("从本机路径追加（等价 CLI /add）")
                    add_path = gr.Textbox(
                        placeholder="文件或目录路径，如 ~/Documents/notes", show_label=False, container=False,
                    )
                    with gr.Row(elem_classes=["cb-inline-actions"]):
                        add_types = gr.Textbox(
                            placeholder="类型过滤（可选）：.pdf,.md", show_label=False, container=False, scale=1,
                        )
                        add_btn = gr.Button("追加入库", variant="primary", elem_classes=["cb-btn"], min_width=110)
                    add_result = result_md()

            section("危险操作")
            with gr.Row(elem_classes=["cb-inline-actions"]):
                rebuild_path = gr.Textbox(
                    placeholder="重建索引的数据目录/文件路径（将替换现有索引）", show_label=False,
                    container=False, scale=1,
                )
                rebuild_confirm = Confirm("重建索引（替换）", "重建会**清空并替换**现有索引，继续？", min_width=150)
                clear_confirm = Confirm("清空索引", "清空全部向量索引？此操作不可撤销。", min_width=110)
            danger_result = result_md()

            def _upload(paths):
                msg, _ = handlers["on_upload"](paths)
                return msg, handlers["on_stats_cards"]()

            upload.upload(_upload, upload, [upload_result, stats_cards])
            add_btn.click(handlers["on_add_path"], [add_path, add_types], [add_result, stats_cards])
            add_path.submit(handlers["on_add_path"], [add_path, add_types], [add_result, stats_cards])

            def _rebuild(path):
                msg, _ = handlers["on_rebuild_index"](path)
                return msg, handlers["on_stats_cards"]()

            rebuild_confirm.bind(_rebuild, rebuild_path, [danger_result, stats_cards])

            def _clear():
                msg, _ = handlers["on_clear_index"]()
                return msg, handlers["on_stats_cards"]()

            clear_confirm.bind(_clear, None, [danger_result, stats_cards])

        # ---------------- 文件管理 ----------------
        with gr.Tab("文件管理"):
            with gr.Row(elem_classes=["cb-inline-actions"]):
                fl_refresh = gr.Button("刷新列表", elem_classes=["cb-btn"], min_width=96)
                fl_stats_btn = gr.Button("文件统计", elem_classes=["cb-btn"], min_width=96)
                cleanup_confirm = Confirm(
                    "清理临时文件", "将删除下方列出的临时/过期文件（含磁盘文件），继续？", min_width=130,
                )
                dedupe_confirm = Confirm("去重", "移除重复登记（不删磁盘文件），继续？", min_width=90)
            file_result = result_md()
            file_paths = gr.State([])
            with gr.Row(equal_height=False):
                with gr.Column(scale=7, min_width=520):
                    file_table = table(
                        headers["files"][:-1], [], max_height=380,
                        column_widths=["34%", "12%", "14%", "22%", "9%", "9%"],
                    )
                with gr.Column(scale=3, min_width=260):
                    section("文件详情（点击表格行）")
                    file_info_md = gr.Markdown("_点击左侧表格中的文件查看详情_", elem_classes=["cb-kv"])

            def _split(rows):
                """末列完整路径不展示，存入 State 供选中行取值。"""
                return [r[:-1] for r in rows], [r[-1] for r in rows]

            def _file_rows():
                return _split(handlers["on_file_table"]())

            fl_refresh.click(_file_rows, None, [file_table, file_paths])
            fl_stats_btn.click(handlers["on_file_stats_md"], None, file_result)

            def _file_pick(paths, evt: gr.SelectData):
                try:
                    path = paths[evt.index[0]]
                except Exception:  # noqa: BLE001
                    return ""
                return handlers["on_file_info"](path) if path else ""

            file_table.select(_file_pick, file_paths, file_info_md)

            def _cleanup():
                msg, rows = handlers["on_file_cleanup"]()
                return (msg, *_split(rows))

            def _dedupe():
                msg, rows = handlers["on_file_dedupe"]()
                return (msg, *_split(rows))

            cleanup_confirm.on_open(handlers["on_file_cleanup_preview"], None, file_result).bind(
                _cleanup, None, [file_result, file_table, file_paths],
            )
            dedupe_confirm.on_open(handlers["on_file_dedupe_preview"], None, file_result).bind(
                _dedupe, None, [file_result, file_table, file_paths],
            )

        # ---------------- 快照 ----------------
        with gr.Tab("快照"):
            with gr.Row(elem_classes=["cb-inline-actions"]):
                snap_refresh = gr.Button("刷新列表", elem_classes=["cb-btn"], min_width=96)
                snap_create = gr.Button("创建快照", variant="primary", elem_classes=["cb-btn"], min_width=96)
                snap_id = gr.Textbox(placeholder="选中一行或粘贴快照 ID", show_label=False, container=False, scale=1)
                snap_restore = gr.Button("生成恢复脚本", elem_classes=["cb-btn"], min_width=120)
            snap_result = result_md()
            snap_table = table(headers["snapshots"], [], max_height=320, search=False)

            snap_refresh.click(handlers["on_snapshot_table"], None, snap_table)
            snap_create.click(handlers["on_snapshot_create_table"], None, [snap_result, snap_table])
            snap_table.select(pick_cell(0), snap_table, snap_id)
            snap_restore.click(handlers["on_snapshot_restore"], snap_id, snap_result)

        # ---------------- Skills 与摘要 ----------------
        with gr.Tab("Skills 与摘要"):
            with gr.Row(elem_classes=["cb-inline-actions"]):
                gs_btn = gr.Button("生成 Skills", variant="primary", elem_classes=["cb-btn"], min_width=110)
                ks_btn = gr.Button("刷新文档摘要", elem_classes=["cb-btn"], min_width=110)
            km_result = result_md()
            summary_table = table(headers["summary"], [], max_height=360)
            gs_btn.click(handlers["on_generate_skills"], None, km_result)
            ks_btn.click(handlers["on_knowledge_summary_table"], None, summary_table)

    return {"stats_cards": stats_cards, "file_table": file_table, "file_paths": file_paths,
            "file_rows": _file_rows}
