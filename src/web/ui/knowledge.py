"""知识库页：文档入库 / 文件管理 / 快照 / Skills 与摘要。"""  # pragma: no cover
from __future__ import annotations

from typing import Any, Callable, Dict

import gradio as gr

from .common import Confirm, page_title, pick_cell, result_md, section, table, with_more_column


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
                dedupe_confirm = Confirm(
                    "去重", "只移除重复登记，不删向量、不删磁盘文件；如需彻底删除请用「删除文件」。继续？",
                    min_width=90,
                )
            file_result = result_md()
            file_paths = gr.State([])
            selected_path = gr.State("")
            with gr.Row(equal_height=False):
                with gr.Column(scale=7, min_width=520):
                    file_table = table(
                        [*headers["files"][:-1], "⋯"], [], max_height=380,
                        column_widths=["32%", "11%", "13%", "20%", "8%", "8%", "8%"],
                        datatype=[*(["str"] * (len(headers["files"]) - 1)), "html"],
                    )
                with gr.Column(scale=3, min_width=260):
                    # 操作条：选中行后出现（📄 文件名 [查看详情] [删除文件]）
                    with gr.Column(visible=False, elem_classes=["cb-action-bar"]) as file_actions:
                        file_action_title = gr.HTML("")
                        with gr.Row(elem_classes=["cb-inline-actions"]):
                            file_detail_btn = gr.Button("查看详情", size="sm", elem_classes=["cb-btn"], min_width=90)
                            file_delete_confirm = Confirm(
                                "删除文件", "将删除该文件的片段与元数据，不删除磁盘文件。继续？",
                                size="sm", min_width=100,
                            )
                    section("文件详情（点击表格行）")
                    file_info_md = gr.Markdown("_点击左侧表格中的文件查看详情_", elem_classes=["cb-kv"])

            def _split(rows):
                """末列完整路径不展示（存入 State 供选中行取值），并追加「⋯」操作列。"""
                return with_more_column([r[:-1] for r in rows]), [r[-1] for r in rows]

            def _file_rows():
                return _split(handlers["on_file_table"]())

            fl_refresh.click(_file_rows, None, [file_table, file_paths])
            fl_stats_btn.click(handlers["on_file_stats_md"], None, file_result)

            def _file_pick(paths, evt: gr.SelectData):
                """点击任意单元格 = 选中该行：展开操作条并显示详情。"""
                try:
                    path = paths[evt.index[0]]
                except Exception:  # noqa: BLE001
                    path = ""
                if not path:
                    return "", gr.update(visible=False), "", ""
                return (
                    path, gr.update(visible=True), handlers["on_file_action_bar"](path),
                    handlers["on_file_info"](path),
                )

            file_table.select(
                _file_pick, file_paths, [selected_path, file_actions, file_action_title, file_info_md],
            )
            file_detail_btn.click(handlers["on_file_info"], selected_path, file_info_md)

            def _file_delete(path):
                msg, rows, cards = handlers["on_file_delete"](path)
                table_rows, paths = _split(rows)
                ok = msg.startswith("✅")
                return (
                    msg, table_rows, paths, cards,
                    gr.update(visible=not ok), "" if ok else path,
                    "_文件已删除_" if ok else gr.update(),
                )

            file_delete_confirm.on_open(
                handlers["on_file_delete_preview"], selected_path, file_delete_confirm.prompt,
            ).bind(
                _file_delete, selected_path,
                [file_result, file_table, file_paths, stats_cards, file_actions, selected_path, file_info_md],
            )

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
                prune_keep = gr.Number(
                    value=10, minimum=0, precision=0, label="保留最近", scale=0, min_width=110,
                )
                prune_confirm = Confirm("清理自动快照…", "将删除多余的自动快照，继续？", min_width=130)
            snap_result = result_md()
            snap_id = gr.State("")
            with gr.Row(equal_height=False):
                with gr.Column(scale=7, min_width=520):
                    snap_table = table(
                        [*headers["snapshots"], "⋯"], [], max_height=320, search=False,
                        column_widths=["30%", "26%", "10%", "10%", "16%", "8%"],
                        datatype=[*(["str"] * len(headers["snapshots"])), "html"],
                    )
                with gr.Column(scale=3, min_width=280):
                    with gr.Column(visible=False, elem_classes=["cb-action-bar"]) as snap_actions:
                        snap_action_title = gr.HTML("")
                        with gr.Row(elem_classes=["cb-inline-actions"]):
                            snap_info_btn = gr.Button("详情", size="sm", elem_classes=["cb-btn"], min_width=64)
                            snap_restore_append = gr.Button(
                                "恢复（追加）", size="sm", variant="primary", elem_classes=["cb-btn"], min_width=104,
                            )
                            snap_restore_replace = Confirm(
                                "恢复（替换）", "将**清空现有索引**后按快照重新入库，继续？",
                                size="sm", min_width=104,
                            )
                        with gr.Row(elem_classes=["cb-inline-actions"]):
                            snap_script_btn = gr.Button("生成脚本", size="sm", elem_classes=["cb-btn"], min_width=90)
                            snap_delete_confirm = Confirm("删除", "删除该快照？", size="sm", min_width=72)
                    snap_status = gr.Markdown("", elem_classes=["cb-status"])
                    section("快照详情")
                    snap_info_md = gr.Markdown("_点击左侧表格中的快照查看详情_", elem_classes=["cb-kv"])
            snap_docs = table(
                headers["snapshot_docs"], [], max_height=260, search=False,
                column_widths=["10%", "26%", "8%", "8%", "48%"],
                datatype=["html", "html", "str", "str", "str"],
            )

            def _snap_rows():
                return with_more_column(handlers["on_snapshot_table"]())

            snap_refresh.click(_snap_rows, None, snap_table)

            def _snap_create():
                msg, rows = handlers["on_snapshot_create_table"]()
                return msg, with_more_column(rows)

            snap_create.click(_snap_create, None, [snap_result, snap_table])

            def _snap_pick(data, evt: gr.SelectData):
                sid = pick_cell(0)(data, evt)
                if not sid or sid.startswith("[错误]"):
                    return "", gr.update(visible=False), "", gr.update(), []
                info_md, doc_rows = handlers["on_snapshot_info"](sid)
                title = f'<div class="cb-action-title" title="{sid}">📸 <code>{sid}</code></div>'
                return sid, gr.update(visible=True), title, info_md, doc_rows

            snap_table.select(
                _snap_pick, snap_table, [snap_id, snap_actions, snap_action_title, snap_info_md, snap_docs],
            )
            snap_info_btn.click(handlers["on_snapshot_info"], snap_id, [snap_info_md, snap_docs])
            snap_script_btn.click(handlers["on_snapshot_restore"], snap_id, snap_result)

            def _restore_append(sid):
                yield from handlers["on_snapshot_restore_stream"](sid, "append")

            def _restore_replace(sid):
                yield from handlers["on_snapshot_restore_stream"](sid, "replace")

            snap_restore_append.click(_restore_append, snap_id, [snap_status, snap_result]).then(
                _snap_rows, None, snap_table,
            ).then(handlers["on_stats_cards"], None, stats_cards)
            snap_restore_replace.bind(_restore_replace, snap_id, [snap_status, snap_result]).then(
                _snap_rows, None, snap_table,
            ).then(handlers["on_stats_cards"], None, stats_cards)

            def _snap_delete(sid):
                msg, rows = handlers["on_snapshot_delete"](sid)
                ok = msg.startswith("✅")
                return msg, with_more_column(rows), gr.update(visible=not ok), "" if ok else sid

            snap_delete_confirm.bind(
                _snap_delete, snap_id, [snap_result, snap_table, snap_actions, snap_id],
            )

            def _prune(keep):
                msg, rows = handlers["on_snapshot_prune"](keep)
                return msg, with_more_column(rows)

            prune_confirm.on_open(handlers["on_snapshot_prune_preview"], prune_keep, prune_confirm.prompt).bind(
                _prune, prune_keep, [snap_result, snap_table],
            )

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
            "file_rows": _file_rows, "snap_table": snap_table, "snap_rows": _snap_rows}
