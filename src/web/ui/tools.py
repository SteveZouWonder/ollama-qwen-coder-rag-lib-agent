"""工具页：代码 / Git 仪表盘 / 数据库 / 工作区；每个结果面板可「用 AI 解读」或「发送到对话」。"""  # pragma: no cover
from __future__ import annotations

from typing import Any, Callable, Dict, Optional

import gradio as gr

from .common import Confirm, page_title, pick_cell, result_md, section, table


def _result_actions(  # pragma: no cover
    handlers: Dict[str, Callable],
    chat_refs: Optional[Dict[str, Any]],
    *,
    kind: str,
    tab: str,
    payload,
) -> gr.Markdown:
    """结果流转行（F9 P1-6）：``用 AI 解读`` / ``停止`` / ``发送到对话`` + 解读输出区。

    ``payload`` 为提供解读文本的组件（Markdown / State / Textbox）。
    「发送到对话」把模板填入对话页输入框、模式切「自动」、导航切到对话页，**不自动发送**。
    """
    with gr.Row(elem_classes=["cb-inline-actions", "cb-result-actions"]):
        explain_btn = gr.Button("用 AI 解读", size="sm", elem_classes=["cb-btn"], min_width=96)
        stop_btn = gr.Button("停止", size="sm", elem_classes=["cb-btn"], min_width=64)
        send_btn = gr.Button("发送到对话", size="sm", variant="primary", elem_classes=["cb-btn"], min_width=100)
        ai_hint = gr.Markdown("", elem_classes=["cb-muted"], scale=1)
    ai_md = result_md(classes=["cb-ai-explain"])

    def _explain(p):  # 必须是生成器函数，Gradio 才按流式处理
        yield from handlers["on_ai_explain"](kind, p or "", "")

    explain_btn.click(_explain, payload, ai_md)
    stop_btn.click(handlers["on_stop"], None, ai_hint, show_progress="hidden")

    if chat_refs:
        mode_auto, nav_chat = chat_refs["mode_auto"], chat_refs["nav_chat"]

        def _send(p):
            text = handlers["on_send_to_chat"](tab, p or "")
            if not text:
                return gr.update(), gr.update(), gr.update(), "💡 没有可发送的结果，请先执行一次操作"
            return text, mode_auto, nav_chat, ""

        send_btn.click(
            _send, payload, [chat_refs["msg_box"], chat_refs["mode"], chat_refs["nav"], ai_hint],
            show_progress="hidden",
        )
    else:
        send_btn.click(lambda: "💡 对话页未就绪", None, ai_hint, show_progress="hidden")
    return ai_md


def build_tools_page(  # pragma: no cover
    service, handlers: Dict[str, Callable], chat_refs: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    page_title("工具", "AI 驱动的代码 / Git / 数据库 / 工作区工具，结果可发送到对话继续追问。")
    headers = handlers["headers"]

    with gr.Tabs():
        # ---------------- 代码 ----------------
        with gr.Tab("代码"):
            cwd_md = gr.Markdown(handlers["on_cwd"](), elem_classes=["cb-muted"])
            section("符号搜索")
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

            # 两个结果合并为解读 payload（取最近一次非空）
            code_payload = gr.State("")
            ca_result.change(lambda a, b: (a or "") + ("\n\n" + b if b else ""), [ca_result, cq_result], code_payload, show_progress="hidden")
            cq_result.change(lambda a, b: (a or "") + ("\n\n" + b if b else ""), [ca_result, cq_result], code_payload, show_progress="hidden")
            _result_actions(handlers, chat_refs, kind="code", tab="代码", payload=code_payload)

        # ---------------- Git 仪表盘 ----------------
        with gr.Tab("Git") as git_tab:
            with gr.Row(elem_classes=["cb-inline-actions"]):
                gr.Markdown("作用于「系统 → 运行环境」中的当前工作目录。", elem_classes=["cb-muted"], scale=1)
                git_refresh = gr.Button("刷新", elem_classes=["cb-btn"], min_width=72)
                gcg_btn = gr.Button("AI 生成提交信息", elem_classes=["cb-btn"], min_width=140)
            git_cards = gr.HTML('<div class="cb-empty">进入本页时自动加载，或点「刷新」。</div>')
            with gr.Row():
                with gr.Column(scale=2, min_width=260):
                    section("变更文件")
                    git_changes = table(headers["git_changes"], max_height=320, search=False,
                                        column_widths=["22%", "78%"])
                with gr.Column(scale=3, min_width=320):
                    with gr.Tabs():
                        with gr.Tab("最近提交"):
                            git_commits = table(headers["git_commits"], max_height=320, search=False,
                                                column_widths=["14%", "18%", "18%", "50%"])
                        with gr.Tab("提交者统计"):
                            git_authors = table(headers["git_authors"], max_height=320, search=False)
            git_payload = gr.State("")
            gcg_result = result_md()
            git_outputs = [git_cards, git_changes, git_commits, git_authors, git_payload]
            git_refresh.click(handlers["on_git_overview"], None, git_outputs)
            git_tab.select(handlers["on_git_overview"], None, git_outputs, show_progress="minimal")
            gcg_btn.click(handlers["on_git_commit_gen"], None, gcg_result)

            def _git_payload(overview_text, commit_msg):
                return (overview_text or "") + (f"\n\nAI 提交信息建议：\n{commit_msg}" if commit_msg else "")

            git_ai_payload = gr.State("")
            git_payload.change(_git_payload, [git_payload, gcg_result], git_ai_payload, show_progress="hidden")
            gcg_result.change(_git_payload, [git_payload, gcg_result], git_ai_payload, show_progress="hidden")
            _result_actions(handlers, chat_refs, kind="git", tab="Git", payload=git_ai_payload)

        # ---------------- 数据库 ----------------
        with gr.Tab("数据库") as db_tab:
            with gr.Row(elem_classes=["cb-inline-actions"]):
                db_path = gr.Textbox(
                    value=":memory:", placeholder="SQLite 文件路径，如 ./data/app.db（:memory: 为临时内存库）",
                    show_label=False, container=False, scale=1,
                )
                db_conn_btn = gr.Button("连接", variant="primary", elem_classes=["cb-btn"], min_width=80)
                db_disc_btn = gr.Button("断开", elem_classes=["cb-btn"], min_width=72)
            db_status = gr.HTML(handlers["on_db_status"]())
            db_conn_result = result_md()

            with gr.Row():
                with gr.Column(scale=2, min_width=220):
                    section("表")
                    db_tables = table(headers["db_tables"], handlers["on_db_tables"](), max_height=300, search=False)
                    db_tables_refresh = gr.Button("刷新表列表", size="sm", elem_classes=["cb-btn"], min_width=100)
                with gr.Column(scale=3, min_width=320):
                    section("表结构")
                    db_schema_title = gr.Markdown("_点击左侧表名查看列 / 类型 / 约束_", elem_classes=["cb-muted"])
                    db_schema = table(headers["db_schema"], max_height=300, search=False,
                                      column_widths=["34%", "26%", "40%"])

            db_conn_btn.click(handlers["on_db_connect"], db_path, [db_conn_result, db_status, db_tables])
            db_path.submit(handlers["on_db_connect"], db_path, [db_conn_result, db_status, db_tables])
            db_disc_btn.click(handlers["on_db_disconnect"], None, [db_conn_result, db_status, db_tables]).then(
                lambda: ("_点击左侧表名查看列 / 类型 / 约束_", []), None, [db_schema_title, db_schema], show_progress="hidden",
            )
            db_tables_refresh.click(handlers["on_db_tables"], None, db_tables, show_progress="hidden")
            db_tab.select(
                lambda: (handlers["on_db_status"](), handlers["on_db_tables"]()), None, [db_status, db_tables],
                show_progress="hidden",
            )
            db_selected = gr.State("")
            db_tables.select(pick_cell(0), db_tables, db_selected, show_progress="hidden").then(
                handlers["on_db_table_schema"], db_selected, [db_schema_title, db_schema],
            )

            section("SQL")
            with gr.Row(elem_classes=["cb-inline-actions"]):
                dq_sql = gr.Textbox(placeholder="SELECT …（查询）或 INSERT / UPDATE / DELETE / DDL（执行，需确认）",
                                    show_label=False, container=False, scale=1, lines=2)
                dq_btn = gr.Button("查询", variant="primary", elem_classes=["cb-btn"], min_width=80)
                de_confirm = Confirm("执行", "执行该写操作 SQL？", min_width=80)
            dq_status = gr.Markdown(elem_classes=["cb-status"])
            dq_table = table(["结果"], max_height=360)
            db_payload = gr.State("")

            def _query(sql):
                status, cols, rows = handlers["on_db_query"](sql)
                payload = handlers["on_db_payload"](sql, cols, rows) if cols or rows else f"SQL: {sql}\n{status}"
                if cols:
                    return status, gr.Dataframe(headers=list(cols), value=rows), payload
                return status, gr.Dataframe(headers=["结果"], value=[]), payload

            dq_btn.click(_query, dq_sql, [dq_status, dq_table, db_payload])
            dq_sql.submit(_query, dq_sql, [dq_status, dq_table, db_payload])

            def _execute(sql):
                status, tables = handlers["on_db_execute"](sql)
                return status, tables, f"SQL: {sql}\n{status}"

            de_confirm.bind(_execute, dq_sql, [dq_status, db_tables, db_payload])
            _result_actions(handlers, chat_refs, kind="db", tab="数据库", payload=db_payload)

        # ---------------- 工作区（Shell 与文件）----------------
        with gr.Tab("工作区"):
            shell_enable = gr.Checkbox(
                value=False, label="启用 Shell 执行与文件写入（默认关闭；仅本机回环访问，仍请谨慎）",
                container=False,
            )

            section("执行命令（先分析再执行）")
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
            ex_confirm.trigger.visible = False

            shell_payload = gr.State("")
            ex_result.change(lambda c, r: f"$ {c}\n{r}" if r else "", [ex_cmd, ex_result], shell_payload, show_progress="hidden")
            _result_actions(handlers, chat_refs, kind="shell", tab="工作区 · 命令", payload=shell_payload)

            section("读取文件（不经过模型）")
            with gr.Row(elem_classes=["cb-inline-actions"]):
                rf_path = gr.Textbox(placeholder="文件路径", show_label=False, container=False, scale=1)
                rf_offset = gr.Number(value=0, label="起始行", minimum=0, precision=0, scale=0, min_width=110)
                rf_limit = gr.Number(value=200, label="行数", minimum=1, precision=0, scale=0, min_width=110)
                rf_btn = gr.Button("读取", elem_classes=["cb-btn"], min_width=80)
            rf_result = result_md(classes=["cb-code"])
            rf_btn.click(handlers["on_read_file"], [rf_path, rf_offset, rf_limit], rf_result)
            rf_path.submit(handlers["on_read_file"], [rf_path, rf_offset, rf_limit], rf_result)

            file_payload = gr.State("")
            rf_result.change(lambda p, r: f"文件: {p}\n{r}" if r else "", [rf_path, rf_result], file_payload, show_progress="hidden")
            _result_actions(handlers, chat_refs, kind="file", tab="工作区 · 文件", payload=file_payload)

            section("写入文件")
            with gr.Row(elem_classes=["cb-inline-actions"]):
                wf_path = gr.Textbox(placeholder="目标文件路径", show_label=False, container=False, scale=1)
                wf_append = gr.Checkbox(value=False, label="追加模式", container=False, scale=0, min_width=100)
                wf_confirm = Confirm("写入", "写入该文件？覆盖模式会替换原内容。", min_width=80)
            wf_content = gr.Textbox(lines=6, placeholder="文件内容…", show_label=False, container=False)
            wf_result = result_md()
            wf_confirm.bind(handlers["on_write_file"], [wf_path, wf_content, wf_append], wf_result)

            gated = [ex_cmd, ex_analyze, ex_run, ex_confirm.trigger, wf_path, wf_content, wf_append, wf_confirm.trigger]

            def _gate(on):
                return [gr.update(interactive=bool(on)) for _ in gated]

            shell_enable.change(_gate, shell_enable, gated, show_progress="hidden")
            for c in gated:
                c.interactive = False

    return {"cwd_md": cwd_md, "git_refresh": handlers["on_git_overview"], "git_outputs": git_outputs}
