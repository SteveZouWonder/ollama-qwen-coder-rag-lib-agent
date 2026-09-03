"""工具页：网络搜索 / 代码分析 / Git / 数据库 / Shell 与文件。"""  # pragma: no cover
from __future__ import annotations

from typing import Any, Callable, Dict

import gradio as gr

from .common import Confirm, page_title, result_md, section


def build_tools_page(service, handlers: Dict[str, Callable]) -> Dict[str, Any]:  # pragma: no cover
    page_title("工具", "直接调用 Agent 工具，与 CLI 的 /web-* /code-* /git-* /db-* /exec /file 命令面一致。")

    with gr.Tabs():
        # ---------------- 网络搜索 ----------------
        with gr.Tab("网络搜索"):
            with gr.Row(elem_classes=["cb-inline-actions"]):
                ws_query = gr.Textbox(placeholder="搜索关键词…", show_label=False, container=False, scale=1)
                ws_btn = gr.Button("搜索", variant="primary", elem_classes=["cb-btn"], min_width=80)
            ws_result = result_md()
            ws_btn.click(handlers["on_web_search"], ws_query, ws_result)
            ws_query.submit(handlers["on_web_search"], ws_query, ws_result)

            section("提取网页正文")
            with gr.Row(elem_classes=["cb-inline-actions"]):
                we_url = gr.Textbox(placeholder="https://…", show_label=False, container=False, scale=1)
                we_btn = gr.Button("提取", elem_classes=["cb-btn"], min_width=80)
            we_result = result_md()
            we_btn.click(handlers["on_web_extract"], we_url, we_result)
            we_url.submit(handlers["on_web_extract"], we_url, we_result)

            section("搜索缓存")
            with gr.Row(elem_classes=["cb-inline-actions"]):
                wc_status_btn = gr.Button("缓存状态", elem_classes=["cb-btn"], min_width=96)
                wc_clear = Confirm("清空缓存", "清空全部搜索缓存？", min_width=100)
            wc_result = result_md()
            wc_status_btn.click(handlers["on_web_cache_status"], None, wc_result)
            wc_clear.bind(handlers["on_web_cache_clear"], None, wc_result)

        # ---------------- 代码分析 ----------------
        with gr.Tab("代码分析"):
            cwd_md = gr.Markdown(handlers["on_cwd"](), elem_classes=["cb-muted"])
            section("AST 搜索")
            with gr.Row(elem_classes=["cb-inline-actions"]):
                ca_pattern = gr.Textbox(placeholder="函数 / 类 / 变量名…", show_label=False, container=False, scale=2)
                ca_path = gr.Textbox(value=".", placeholder="路径", show_label=False, container=False, scale=1)
                ca_btn = gr.Button("搜索", variant="primary", elem_classes=["cb-btn"], min_width=80)
            ca_result = result_md()
            ca_btn.click(handlers["on_code_ast"], [ca_pattern, ca_path], ca_result)
            ca_pattern.submit(handlers["on_code_ast"], [ca_pattern, ca_path], ca_result)

            section("代码质量检查")
            with gr.Row(elem_classes=["cb-inline-actions"]):
                cq_path = gr.Textbox(value=".", placeholder="路径", show_label=False, container=False, scale=1)
                cq_btn = gr.Button("检查", elem_classes=["cb-btn"], min_width=80)
            cq_result = result_md()
            cq_btn.click(handlers["on_code_quality"], cq_path, cq_result)

        # ---------------- Git ----------------
        with gr.Tab("Git"):
            gr.Markdown("作用于「系统 → 运行环境」中的当前工作目录。", elem_classes=["cb-muted"])
            with gr.Row(elem_classes=["cb-inline-actions"]):
                ga_type = gr.Radio(
                    [("提交历史", "history"), ("工作区状态", "status"), ("作者统计", "authors")],
                    value="history", show_label=False, container=False, elem_classes=["cb-segment"],
                    scale=0, min_width=320,
                )
                ga_btn = gr.Button("分析", variant="primary", elem_classes=["cb-btn"], min_width=80)
                gcg_btn = gr.Button("AI 生成提交信息", elem_classes=["cb-btn"], min_width=140)
            ga_result = result_md()
            ga_btn.click(handlers["on_git_analyze"], ga_type, ga_result)
            gcg_btn.click(handlers["on_git_commit_gen"], None, ga_result)

        # ---------------- 数据库 ----------------
        with gr.Tab("数据库"):
            section("连接")
            with gr.Row(elem_classes=["cb-inline-actions"]):
                db_type = gr.Dropdown(
                    choices=["sqlite", "mysql", "postgresql"], value="sqlite", allow_custom_value=True,
                    show_label=False, container=False, scale=0, min_width=140,
                )
                db_name = gr.Textbox(placeholder="数据库路径 / 名称", show_label=False, container=False, scale=1)
                db_conn_btn = gr.Button("连接", variant="primary", elem_classes=["cb-btn"], min_width=80)
            db_conn_result = result_md()
            db_conn_btn.click(handlers["on_db_connect"], [db_type, db_name], db_conn_result)

            section("查询 / Schema")
            with gr.Row(elem_classes=["cb-inline-actions"]):
                dq_sql = gr.Textbox(placeholder="SELECT …", show_label=False, container=False, scale=1)
                dq_btn = gr.Button("查询", elem_classes=["cb-btn"], min_width=80)
            with gr.Row(elem_classes=["cb-inline-actions"]):
                ds_table = gr.Textbox(placeholder="表名（留空列出所有表）", show_label=False, container=False, scale=1)
                ds_btn = gr.Button("查看 Schema", elem_classes=["cb-btn"], min_width=110)
            dq_result = result_md()
            dq_btn.click(handlers["on_db_query"], dq_sql, dq_result)
            dq_sql.submit(handlers["on_db_query"], dq_sql, dq_result)
            ds_btn.click(handlers["on_db_schema"], ds_table, dq_result)

            section("写操作（需确认）")
            with gr.Row(elem_classes=["cb-inline-actions"]):
                de_sql = gr.Textbox(placeholder="INSERT / UPDATE / DELETE / DDL …", show_label=False, container=False, scale=1)
                de_confirm = Confirm("执行 SQL", "执行该写操作 SQL？", min_width=100)
            with gr.Row(elem_classes=["cb-inline-actions"]):
                ct_table = gr.Textbox(placeholder="表名", show_label=False, container=False, scale=0, min_width=160)
                ct_cols = gr.Textbox(
                    placeholder='列定义 JSON，如 {"id": "INTEGER PRIMARY KEY", "name": "TEXT"}',
                    show_label=False, container=False, scale=1,
                )
                ct_confirm = Confirm("创建表", "创建该表？", min_width=90)
            with gr.Row(elem_classes=["cb-inline-actions"]):
                ins_table = gr.Textbox(placeholder="表名", show_label=False, container=False, scale=0, min_width=160)
                ins_data = gr.Textbox(
                    placeholder='数据 JSON，如 {"name": "Alice", "age": 30}', show_label=False, container=False, scale=1,
                )
                ins_confirm = Confirm("插入数据", "插入该行数据？", min_width=100)
            dw_result = result_md()
            de_confirm.bind(handlers["on_db_execute"], de_sql, dw_result)
            ct_confirm.bind(handlers["on_db_create_table"], [ct_table, ct_cols], dw_result)
            ins_confirm.bind(handlers["on_db_insert"], [ins_table, ins_data], dw_result)

        # ---------------- Shell 与文件 ----------------
        with gr.Tab("Shell 与文件"):
            shell_enable = gr.Checkbox(
                value=False, label="启用 Shell 执行与文件写入（默认关闭；仅本机回环访问，仍请谨慎）",
                container=False,
            )

            section("执行命令（等价 CLI /exec，先分析再执行）")
            with gr.Row(elem_classes=["cb-inline-actions"]):
                ex_cmd = gr.Textbox(placeholder="如 git status / ls -la", show_label=False, container=False, scale=1)
                ex_analyze = gr.Button("分析", elem_classes=["cb-btn"], min_width=80)
                ex_run = gr.Button("执行", variant="primary", elem_classes=["cb-btn"], min_width=80, visible=False)
                ex_confirm = Confirm("确认后执行", "该命令会修改系统，确认执行？", min_width=120)
            ex_risk = gr.Markdown(elem_classes=["cb-status"])
            ex_result = result_md(classes=["cb-code"])

            def _analyze(cmd):
                md, can_run, needs = handlers["on_exec_analyze"](cmd)
                return md, gr.update(visible=can_run), gr.update(visible=needs)

            ex_analyze.click(_analyze, ex_cmd, [ex_risk, ex_run, ex_confirm.trigger])
            ex_cmd.submit(_analyze, ex_cmd, [ex_risk, ex_run, ex_confirm.trigger])
            ex_cmd.change(
                lambda: (gr.update(visible=False), gr.update(visible=False)), None,
                [ex_run, ex_confirm.trigger], show_progress="hidden",
            )
            ex_run.click(handlers["on_exec_run"], ex_cmd, ex_result)
            ex_confirm.bind(handlers["on_exec_run"], ex_cmd, ex_result)
            # 初始隐藏确认按钮（分析出"需确认"时才显示）
            ex_confirm.trigger.visible = False

            section("读取文件（等价 CLI /file，不经过模型）")
            with gr.Row(elem_classes=["cb-inline-actions"]):
                rf_path = gr.Textbox(placeholder="文件路径", show_label=False, container=False, scale=1)
                rf_offset = gr.Number(value=0, label="起始行", minimum=0, precision=0, scale=0, min_width=110)
                rf_limit = gr.Number(value=200, label="行数", minimum=1, precision=0, scale=0, min_width=110)
                rf_btn = gr.Button("读取", elem_classes=["cb-btn"], min_width=80)
            rf_result = result_md(classes=["cb-code"])
            rf_btn.click(handlers["on_read_file"], [rf_path, rf_offset, rf_limit], rf_result)
            rf_path.submit(handlers["on_read_file"], [rf_path, rf_offset, rf_limit], rf_result)

            section("写入文件（等价 CLI /write）")
            with gr.Row(elem_classes=["cb-inline-actions"]):
                wf_path = gr.Textbox(placeholder="目标文件路径", show_label=False, container=False, scale=1)
                wf_append = gr.Checkbox(value=False, label="追加模式", container=False, scale=0, min_width=100)
                wf_confirm = Confirm("写入", "写入该文件？覆盖模式会替换原内容。", min_width=80)
            wf_content = gr.Textbox(lines=6, placeholder="文件内容…", show_label=False, container=False)
            wf_result = result_md()
            wf_confirm.bind(handlers["on_write_file"], [wf_path, wf_content, wf_append], wf_result)

            # 总开关：关闭时禁用执行/写入相关控件
            gated = [ex_cmd, ex_analyze, ex_run, ex_confirm.trigger, wf_path, wf_content, wf_append, wf_confirm.trigger]

            def _gate(on):
                return [gr.update(interactive=bool(on)) for _ in gated]

            shell_enable.change(_gate, shell_enable, gated, show_progress="hidden")
            for c in gated:
                c.interactive = False

    return {"cwd_md": cwd_md}
