"""工具页：代码助手 / Git 仪表盘 / 数据库（自然语言 → SQL）/ 工作区（浏览 · 预览 · 编辑 · 命令）。

每个子页以自然语言为第一入口；AI 产出的 SQL / 命令只回填编辑框，执行前用户确认；
每个结果面板可「用 AI 解读」或「发送到对话」（F9 P1-6 / P2）。
P3：最近库 / 命令历史落盘回填、暂存预览 → 可编辑提交信息 → 确认提交、表格空态与长任务锁按钮。
"""  # pragma: no cover
from __future__ import annotations

from typing import Any, Callable, Dict, Optional, Sequence

import gradio as gr

from .common import Confirm, page_title, pick_cell, result_md, section, table

_SCHEMA_HINT = "_点击左侧表名查看列 / 类型 / 约束_"
_NO_FILE = "_在左侧选择文件以预览_"
_SQL_PLACEHOLDER = "-- 在此手写 SQL，或用上方自然语言生成"
_MEMORY_DB = ":memory:"


# ---------------- P3-4 小工具：空态 / 锁按钮 ----------------

def _empty_note(text: str, visible: bool = False) -> gr.HTML:  # pragma: no cover
    """表格下方的空态文案（``.cb-empty``），由对应 handler 控制可见性。"""
    return gr.HTML(f'<div class="cb-empty cb-empty-sm">{text}</div>', visible=visible)


def _vis_empty(rows) -> Dict[str, Any]:  # pragma: no cover
    """行为空时显示空态。"""
    return gr.update(visible=not rows)


def _lock(buttons: Sequence[gr.Button], *, gate: Optional[gr.Checkbox] = None):  # pragma: no cover
    """长任务运行期禁用触发按钮：返回 ``(on, off, off_inputs)``。

    ``gate`` 为总开关时，解锁值取开关当前状态（避免把被门控的按钮"解锁"成可用）。
    """
    n = len(buttons)

    def _updates(interactive: bool):
        # 单个输出组件时 Gradio 期望标量（列表会被当作 Button 的 value）
        ups = [gr.update(interactive=interactive) for _ in range(n)]
        return ups[0] if n == 1 else ups

    def on():
        return _updates(False)

    if gate is None:
        def off():
            return _updates(True)
        return on, off, None

    def off_gated(enabled):
        return _updates(bool(enabled))
    return on, off_gated, gate


def _locked(trigger, buttons: Sequence[gr.Button], fn, inputs, outputs, *, gate=None, event="click", **kw):  # pragma: no cover
    """``trigger.<event>``：锁按钮 → 执行 ``fn`` → 解锁。返回主事件依赖对象。"""
    on, off, off_in = _lock(buttons, gate=gate)
    ev = getattr(trigger, event)(on, None, list(buttons), show_progress="hidden")
    main = ev.then(fn, inputs, outputs, **kw)
    main.then(off, off_in, list(buttons), show_progress="hidden")
    return main


def _result_actions(  # pragma: no cover
    handlers: Dict[str, Callable],
    chat_refs: Optional[Dict[str, Any]],
    *,
    kind: str,
    tab: str,
    payload,
    explain_label: str = "用 AI 解读",
) -> gr.Markdown:
    """结果流转行（F9 P1-6）：``用 AI 解读`` / ``停止`` / ``发送到对话`` + 解读输出区。

    ``payload`` 为提供解读文本的组件（Markdown / State / Textbox）。
    「发送到对话」把模板填入对话页输入框、模式切「自动」、导航切到对话页，**不自动发送**。
    解读进行中禁用「用 AI 解读」按钮（P3-4）。
    """
    with gr.Row(elem_classes=["cb-inline-actions", "cb-result-actions"]):
        explain_btn = gr.Button(explain_label, size="sm", elem_classes=["cb-btn"], min_width=96)
        stop_btn = gr.Button("停止", size="sm", elem_classes=["cb-btn"], min_width=64)
        send_btn = gr.Button("发送到对话", size="sm", variant="primary", elem_classes=["cb-btn"], min_width=100)
        ai_hint = gr.Markdown("", elem_classes=["cb-muted"], scale=1)
    ai_md = result_md(classes=["cb-ai-explain"])

    def _explain(p):  # 必须是生成器函数，Gradio 才按流式处理
        yield from handlers["on_ai_explain"](kind, p or "", "")

    _locked(explain_btn, [explain_btn], _explain, payload, ai_md)
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


def _pick_row(data, evt: gr.SelectData):  # pragma: no cover
    """``Dataframe.select`` → 选中行（list）；越界返回空列表。"""
    try:
        row = evt.index[0] if isinstance(evt.index, (list, tuple)) else int(evt.index)
        return list(data[row])
    except Exception:  # noqa: BLE001
        return []


def build_tools_page(  # pragma: no cover
    service, handlers: Dict[str, Callable], chat_refs: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    page_title("工具", "AI 驱动的代码 / Git / 数据库 / 工作区工具，结果可发送到对话继续追问。")
    headers = handlers["headers"]

    with gr.Tabs() as tabs:
        # ---------------- 代码助手（P2-1） ----------------
        with gr.Tab("代码", id="code"):
            cwd_md = gr.Markdown(handlers["on_cwd"](), elem_classes=["cb-muted"])
            with gr.Row(elem_classes=["cb-inline-actions"]):
                ca_path = gr.Textbox(value=".", placeholder="文件或目录，可从工作区选择", show_label=False,
                                     container=False, scale=2)
                ca_extra = gr.Textbox(placeholder="补充说明（可选），如：重点看异常处理", show_label=False,
                                      container=False, scale=3)
            with gr.Row(elem_classes=["cb-inline-actions", "cb-toolbar"]):
                ca_buttons = {
                    "explain": gr.Button("解释代码", variant="primary", elem_classes=["cb-btn"], min_width=88),
                    "review": gr.Button("审查问题", elem_classes=["cb-btn"], min_width=88),
                    "tests": gr.Button("生成测试", elem_classes=["cb-btn"], min_width=88),
                    "docs": gr.Button("生成文档", elem_classes=["cb-btn"], min_width=88),
                    "refactor": gr.Button("重构建议", elem_classes=["cb-btn"], min_width=88),
                }
                ca_stop = gr.Button("停止", elem_classes=["cb-btn"], min_width=64)
                ca_hint = gr.Markdown("", elem_classes=["cb-muted"], scale=1)
            with gr.Accordion("处理过程", open=False):
                ca_process = gr.Markdown("", elem_classes=["cb-muted"])
            ca_result = result_md()
            code_payload = gr.State("")

            def _assist(action):
                def _run(path, extra):
                    yield from handlers["on_code_assist"](action, path or ".", extra or "")
                return _run

            ca_all = list(ca_buttons.values())
            for action, btn in ca_buttons.items():
                _locked(btn, ca_all, _assist(action), [ca_path, ca_extra], [ca_process, ca_result])
            ca_stop.click(handlers["on_stop"], None, ca_hint, show_progress="hidden")
            ca_result.change(lambda r: r if r and not r.startswith("⏳") else gr.update(), ca_result, code_payload,
                             show_progress="hidden")
            _result_actions(handlers, chat_refs, kind="code", tab="代码", payload=code_payload)

            with gr.Accordion("高级：符号搜索 / 质量检查", open=False):
                section("符号搜索")
                with gr.Row(elem_classes=["cb-inline-actions"]):
                    sym_pattern = gr.Textbox(placeholder="函数 / 类 / 参数名…", show_label=False, container=False, scale=2)
                    sym_by = gr.Dropdown(
                        choices=[("按名称", "name"), ("按参数", "parameter"), ("按返回类型", "return"),
                                 ("按基类", "base"), ("按方法名", "method")],
                        value="name", show_label=False, container=False, scale=1, min_width=120,
                    )
                    sym_path = gr.Textbox(value=".", placeholder="路径", show_label=False, container=False, scale=1)
                    sym_btn = gr.Button("搜索", variant="primary", elem_classes=["cb-btn"], min_width=72)
                sym_status = gr.Markdown(elem_classes=["cb-status"])
                sym_table = table(headers["symbols"], max_height=300, search=False,
                                  column_widths=["22%", "10%", "44%", "10%", "14%"])
                sym_empty = _empty_note("未找到匹配的符号")

                def _symbols(pattern, path, by):
                    status, rows, payload = handlers["on_code_symbols"](pattern, path, by)
                    return status, rows, payload, _vis_empty(rows)

                sym_outputs = [sym_status, sym_table, code_payload, sym_empty]
                sym_btn.click(_symbols, [sym_pattern, sym_path, sym_by], sym_outputs)
                sym_pattern.submit(_symbols, [sym_pattern, sym_path, sym_by], sym_outputs)

                section("质量检查")
                with gr.Row(elem_classes=["cb-inline-actions"]):
                    cq_path = gr.Textbox(value=".", placeholder="文件或目录", show_label=False, container=False, scale=1)
                    cq_btn = gr.Button("检查", elem_classes=["cb-btn"], min_width=72)
                cq_cards = gr.HTML("")
                cq_table = table(headers["quality_issues"], max_height=300, search=False,
                                 column_widths=["12%", "28%", "60%"])
                cq_empty = _empty_note("没有发现问题")

                def _quality(path):
                    cards, rows, payload = handlers["on_code_quality_report"](path)
                    ok = bool(cards) and "cb-empty" not in cards  # 报错时卡片区已是空态，不再叠加"没有问题"
                    return cards, rows, payload, gr.update(visible=ok and not rows)

                cq_btn.click(_quality, cq_path, [cq_cards, cq_table, code_payload, cq_empty])

            # 代码助手路径变化时同步高级区路径（保持一处输入）
            ca_path.change(lambda p: (p, p), ca_path, [sym_path, cq_path], show_progress="hidden")

        # ---------------- Git 仪表盘（P1-5）+ 提交增强（P3-3） ----------------
        with gr.Tab("Git", id="git") as git_tab:
            with gr.Row(elem_classes=["cb-inline-actions"]):
                gr.Markdown("作用于「系统 → 运行环境」中的当前工作目录。", elem_classes=["cb-muted"], scale=1)
                git_refresh = gr.Button("刷新", elem_classes=["cb-btn"], min_width=72)
            git_cards = gr.HTML('<div class="cb-empty">进入本页时自动加载，或点「刷新」。</div>')
            with gr.Row():
                with gr.Column(scale=2, min_width=260):
                    section("变更文件")
                    git_changes = table(headers["git_changes"], max_height=320, search=False,
                                        column_widths=["22%", "78%"])
                    git_changes_empty = _empty_note("工作区干净，没有未提交的变更")
                with gr.Column(scale=3, min_width=320):
                    with gr.Tabs():
                        with gr.Tab("最近提交"):
                            git_commits = table(headers["git_commits"], max_height=320, search=False,
                                                column_widths=["14%", "18%", "18%", "50%"])
                            git_commits_empty = _empty_note("还没有提交记录")
                        with gr.Tab("提交者统计"):
                            git_authors = table(headers["git_authors"], max_height=320, search=False)
                            git_authors_empty = _empty_note("还没有提交者")
            git_payload = gr.State("")

            section("提交 · 暂存预览 → AI 生成提交信息 → 确认提交")
            with gr.Row(elem_classes=["cb-inline-actions"]):
                gcg_btn = gr.Button("AI 生成提交信息", variant="primary", elem_classes=["cb-btn"], min_width=140)
                gc_preview_btn = gr.Button("刷新暂存区", elem_classes=["cb-btn"], min_width=96)
                gc_hint = gr.Markdown("", elem_classes=["cb-status"], scale=1)
            gc_preview = gr.HTML("")
            gc_staged = table(headers["git_staged"], max_height=200, search=False, column_widths=["22%", "78%"])
            gc_msg = gr.Textbox(lines=4, max_lines=12, placeholder="提交信息（AI 生成后可编辑，也可直接手写）",
                                show_label=False, container=False)
            with gr.Row(elem_classes=["cb-inline-actions"]):
                gc_confirm = Confirm("提交", "将以上方文本作为提交信息执行 `git commit`（仅提交暂存区），确认？",
                                     variant="primary", min_width=88)
                gc_gate_hint = gr.Markdown("💡 提交需先在「工作区」启用文件编辑与 Shell 执行总开关",
                                           elem_classes=["cb-muted"], scale=1)
            gc_result = result_md()

            def _overview():
                cards, changes, commits, authors, payload = handlers["on_git_overview"]()
                return (cards, changes, commits, authors, payload,
                        _vis_empty(changes), _vis_empty(commits), _vis_empty(authors))

            git_outputs = [git_cards, git_changes, git_commits, git_authors, git_payload,
                           git_changes_empty, git_commits_empty, git_authors_empty]

            def _preview():
                html, rows, _has = handlers["on_git_commit_preview"]()
                return html, rows

            preview_outputs = [gc_preview, gc_staged]
            git_refresh.click(_overview, None, git_outputs).then(_preview, None, preview_outputs,
                                                                   show_progress="hidden")
            git_tab.select(_overview, None, git_outputs, show_progress="minimal").then(
                _preview, None, preview_outputs, show_progress="hidden")
            gc_preview_btn.click(_preview, None, preview_outputs)

            def _commit_gen():
                html, rows, message, hint = handlers["on_git_commit_gen"]()
                return html, rows, (message if message else gr.update()), hint

            _locked(gcg_btn, [gcg_btn], _commit_gen, None, [gc_preview, gc_staged, gc_msg, gc_hint])

            def _commit(message):
                result = handlers["on_git_commit"](message)
                cleared = "" if result.startswith("✅") else gr.update()
                return result, cleared

            gc_confirm.bind(_commit, gc_msg, [gc_result, gc_msg]).then(_overview, None, git_outputs).then(
                _preview, None, preview_outputs, show_progress="hidden")

            def _git_payload(overview_text, commit_msg):
                return (overview_text or "") + (f"\n\n提交信息草稿：\n{commit_msg}" if commit_msg else "")

            git_ai_payload = gr.State("")
            git_payload.change(_git_payload, [git_payload, gc_msg], git_ai_payload, show_progress="hidden")
            gc_msg.change(_git_payload, [git_payload, gc_msg], git_ai_payload, show_progress="hidden")
            _result_actions(handlers, chat_refs, kind="git", tab="Git", payload=git_ai_payload)

        # ---------------- 数据库（P1 连接 / 表 / Schema + P2-2 自然语言 → SQL + P3-1 最近库） ----------------
        with gr.Tab("数据库", id="db") as db_tab:
            with gr.Row(elem_classes=["cb-inline-actions"]):
                db_path = gr.Dropdown(
                    choices=handlers["on_recent_databases"](), value=_MEMORY_DB, allow_custom_value=True,
                    show_label=False, container=False, scale=1, filterable=True,
                )
                db_conn_btn = gr.Button("连接", variant="primary", elem_classes=["cb-btn"], min_width=80)
                db_disc_btn = gr.Button("断开", elem_classes=["cb-btn"], min_width=72)
            gr.Markdown("选择最近连接过的库，或直接输入 SQLite 文件路径（如 `./data/app.db`；`:memory:` 为临时内存库）。",
                        elem_classes=["cb-muted"])
            db_status = gr.HTML(handlers["on_db_status"]())
            db_conn_result = result_md()

            with gr.Row():
                with gr.Column(scale=2, min_width=220):
                    section("表")
                    init_tables = handlers["on_db_tables"]()
                    db_tables = table(headers["db_tables"], init_tables, max_height=300, search=False)
                    db_tables_empty = _empty_note("暂无表：连接后在下方用自然语言或 SQL 建表", visible=not init_tables)
                    db_tables_refresh = gr.Button("刷新表列表", size="sm", elem_classes=["cb-btn"], min_width=100)
                with gr.Column(scale=3, min_width=320):
                    section("表结构")
                    db_schema_title = gr.Markdown(_SCHEMA_HINT, elem_classes=["cb-muted"])
                    db_schema = table(headers["db_schema"], max_height=300, search=False,
                                      column_widths=["34%", "26%", "40%"])

            section("SQL · 用自然语言描述，或直接手写")
            connected = bool(handlers["on_db_connected"]())
            with gr.Row(elem_classes=["cb-inline-actions"]):
                nl_q = gr.Textbox(placeholder="如：每个表有多少行 / 最近 10 条订单 / 新建一张 users 表",
                                  show_label=False, container=False, scale=1, interactive=connected)
                nl_btn = gr.Button("AI 生成 SQL", variant="primary", elem_classes=["cb-btn"], min_width=110,
                                   interactive=connected)
            nl_note = gr.Markdown("" if connected else "💡 先连接数据库", elem_classes=["cb-status"])
            # 注：Gradio 6.20 的可编辑 gr.Code 若初始值为空则不渲染编辑器，且后续任何写值都会触发前端
            # Svelte 报错（props_invalid_value）并中断整次更新；给一个非空初始注释即可规避。
            # 同理不动态切换其 interactive，仅门控自然语言输入 / 生成按钮；未连接时运行会给出明确提示。
            dq_sql = gr.Code(value=_SQL_PLACEHOLDER, language="sql", lines=4, max_lines=12, show_label=False,
                             container=False, interactive=True, elem_classes=["cb-sql-editor"])
            with gr.Row(elem_classes=["cb-inline-actions"]):
                dq_run = gr.Button("运行", variant="primary", elem_classes=["cb-btn"], min_width=80, visible=False)
                de_confirm = Confirm("执行写操作", "该 SQL 会修改数据库，确认执行？", min_width=110)
                de_confirm.trigger.visible = False
                dq_hint = gr.Markdown("", elem_classes=["cb-muted"], scale=1)
            dq_status = gr.Markdown(elem_classes=["cb-status"])
            dq_table = table(["结果"], max_height=360)
            dq_empty = _empty_note("查询没有返回数据")
            db_payload = gr.State("")

            db_gated = [nl_q, nl_btn]

            def _db_gate():
                on = bool(handlers["on_db_connected"]())
                return [gr.update(interactive=on) for _ in db_gated] + ["" if on else "💡 先连接数据库"]

            def _recent(selected):
                return gr.update(choices=handlers["on_recent_databases"](), value=selected or _MEMORY_DB)

            def _connect(path):
                path = (path or "").strip() or _MEMORY_DB
                msg, status, rows = handlers["on_db_connect"](path)
                return (msg, status, rows, _vis_empty(rows), *_db_gate(), _recent(path))

            conn_outputs = [db_conn_result, db_status, db_tables, db_tables_empty, *db_gated, nl_note, db_path]
            db_conn_btn.click(_connect, db_path, conn_outputs)

            def _disconnect(path):
                msg, status, rows = handlers["on_db_disconnect"]()
                return (msg, status, rows, _vis_empty(rows), *_db_gate(), _recent(path), _SCHEMA_HINT, [])

            db_disc_btn.click(_disconnect, db_path, [*conn_outputs, db_schema_title, db_schema])

            def _tables():
                rows = handlers["on_db_tables"]()
                return rows, _vis_empty(rows)

            db_tables_refresh.click(_tables, None, [db_tables, db_tables_empty], show_progress="hidden")
            db_tab.select(
                lambda p: (handlers["on_db_status"](), *_tables(), *_db_gate(), _recent(p)), db_path,
                [db_status, db_tables, db_tables_empty, *db_gated, nl_note, db_path], show_progress="hidden",
            )
            db_selected = gr.State("")
            db_tables.select(pick_cell(0), db_tables, db_selected, show_progress="hidden").then(
                handlers["on_db_table_schema"], db_selected, [db_schema_title, db_schema],
            )

            def _nl2sql(question):
                sql, note, can_run, needs = handlers["on_db_nl2sql"](question)
                return sql, note, gr.update(visible=can_run), gr.update(visible=needs)

            nl_outputs = [dq_sql, nl_note, dq_run, de_confirm.trigger]
            _locked(nl_btn, [nl_btn], _nl2sql, nl_q, nl_outputs)
            _locked(nl_q, [nl_btn], _nl2sql, nl_q, nl_outputs, event="submit")

            def _sql_kind(sql):
                can_run, needs = handlers["on_sql_kind"](sql)
                has_code = any(ln.strip() and not ln.strip().startswith("--") for ln in (sql or "").splitlines())
                hint = "" if (can_run or needs or not has_code) else "💡 未识别的语句，请以 SELECT / INSERT / UPDATE… 开头"
                return gr.update(visible=can_run), gr.update(visible=needs), hint

            dq_sql.change(_sql_kind, dq_sql, [dq_run, de_confirm.trigger, dq_hint], show_progress="hidden")

            def _query(sql):
                status, cols, rows = handlers["on_db_query"](sql)
                payload = handlers["on_db_payload"](sql, cols, rows) if cols or rows else f"SQL: {sql}\n{status}"
                if cols:
                    return status, gr.Dataframe(headers=list(cols), value=rows), payload, _vis_empty(rows)
                return status, gr.Dataframe(headers=["结果"], value=[]), payload, gr.update(visible=False)

            dq_run.click(_query, dq_sql, [dq_status, dq_table, db_payload, dq_empty])

            def _execute(sql):
                status, tables = handlers["on_db_execute"](sql)
                return status, tables, _vis_empty(tables), f"SQL: {sql}\n{status}"

            de_confirm.bind(_execute, dq_sql, [dq_status, db_tables, db_tables_empty, db_payload])
            _result_actions(handlers, chat_refs, kind="db", tab="数据库", payload=db_payload)

        # ---------------- 工作区（P2-3 浏览 / 预览 / 编辑 + P2-4 命令 + P3-2 命令历史） ----------------
        with gr.Tab("工作区", id="workspace"):
            shell_enable = gr.Checkbox(
                value=False, label="启用文件编辑与 Shell 执行（默认关闭；同时门控 Git 提交；仅本机回环访问，仍请谨慎）",
                container=False,
            )
            start_dir = service.cwd() if hasattr(service, "cwd") else "."
            init_crumb, init_rows, init_path = handlers["on_list_dir"](start_dir, False)
            ws_cur = gr.State(init_path)
            ws_file = gr.State("")
            ws_page = gr.State(0)
            page_zero = gr.State(0)
            file_payload = gr.State("")

            with gr.Row():
                with gr.Column(scale=2, min_width=280):
                    ws_crumb = gr.Markdown(init_crumb, elem_classes=["cb-breadcrumb"])
                    with gr.Row(elem_classes=["cb-inline-actions"]):
                        ws_path = gr.Textbox(value=init_path, placeholder="目录路径，回车跳转", show_label=False,
                                             container=False, scale=1)
                        ws_up = gr.Button("上级", elem_classes=["cb-btn"], min_width=60)
                    ws_table = table(headers["dir"], init_rows, max_height=340, search=False,
                                     column_widths=["8%", "50%", "18%", "24%"])
                    ws_empty = _empty_note("空目录", visible=not init_rows)
                    with gr.Row(elem_classes=["cb-inline-actions"]):
                        ws_search = gr.Textbox(placeholder="搜索文件内容关键词…", show_label=False, container=False, scale=1)
                        ws_search_btn = gr.Button("搜索", elem_classes=["cb-btn"], min_width=64)
                        ws_hidden = gr.Checkbox(value=False, label="隐藏项", container=False, scale=0, min_width=84)
                    ws_search_status = gr.Markdown(elem_classes=["cb-status"])
                    ws_results = table(headers["search"], max_height=220, search=False,
                                       column_widths=["40%", "10%", "50%"])
                    ws_results_empty = _empty_note("没有匹配的内容")
                with gr.Column(scale=3, min_width=320):
                    ws_file_status = gr.Markdown(_NO_FILE, elem_classes=["cb-muted"])
                    ws_code = gr.Code(value="", language=None, lines=18, max_lines=28, interactive=False,
                                      show_label=False, container=False, elem_classes=["cb-file-preview"])
                    with gr.Row(elem_classes=["cb-inline-actions"]):
                        ws_prev = gr.Button("上一页", size="sm", elem_classes=["cb-btn"], min_width=64)
                        ws_next = gr.Button("下一页", size="sm", elem_classes=["cb-btn"], min_width=64)
                        ws_file_path = gr.Textbox(placeholder="文件路径（回车打开）", show_label=False, container=False,
                                                  scale=1)
                        ws_to_code = gr.Button("发到代码助手", size="sm", elem_classes=["cb-btn"], min_width=100)
                        ws_edit_btn = gr.Button("编辑", size="sm", elem_classes=["cb-btn"], min_width=56)
                    _result_actions(handlers, chat_refs, kind="file", tab="工作区 · 文件", payload=file_payload,
                                    explain_label="用 AI 总结")
                    with gr.Column(visible=False, elem_classes=["cb-edit-box"]) as ws_edit_box:
                        wf_hint = gr.Markdown("", elem_classes=["cb-muted"])
                        wf_content = gr.Textbox(lines=8, placeholder="文件内容…", show_label=False, container=False)
                        with gr.Row(elem_classes=["cb-inline-actions"]):
                            wf_append = gr.Checkbox(value=False, label="追加", container=False, scale=0, min_width=72)
                            wf_confirm = Confirm("保存", "保存到该文件？覆盖模式会替换原内容。", min_width=80)
                            wf_close = gr.Button("收起", size="sm", elem_classes=["cb-btn"], min_width=56)
                        wf_result = result_md()

            # -- 目录导航 --
            dir_outputs = [ws_crumb, ws_table, ws_cur, ws_path, ws_empty]

            def _go(path, hidden):
                crumb, rows, resolved = handlers["on_list_dir"](path, hidden)
                return crumb, rows, resolved, resolved, _vis_empty(rows)

            def _up(cur, hidden):
                crumb, rows, resolved = handlers["on_dir_parent"](cur, hidden)
                return crumb, rows, resolved, resolved, _vis_empty(rows)

            ws_path.submit(_go, [ws_path, ws_hidden], dir_outputs)
            ws_up.click(_up, [ws_cur, ws_hidden], dir_outputs)
            ws_hidden.change(_go, [ws_cur, ws_hidden], dir_outputs)

            # -- 文件预览 --
            file_outputs = [ws_file, ws_page, ws_code, ws_file_status, file_payload, ws_file_path]

            def _preview(path, page):
                content, lang, status, page, payload = handlers["on_file_preview"](path, page)
                return (path, page, gr.update(value=content, language=lang), status, payload,
                        handlers["abbreviate_home"](path))

            def _select(data, cur, hidden, evt: gr.SelectData):
                row = _pick_row(data, evt)
                full, is_dir = handlers["join_entry"](cur, row[0] if row else "", row[1] if len(row) > 1 else "")
                if not full:
                    return [gr.update()] * (len(dir_outputs) + len(file_outputs))
                if is_dir:
                    return [*_go(full, hidden), *([gr.update()] * len(file_outputs))]
                return [*([gr.update()] * len(dir_outputs)), *_preview(full, 0)]

            ws_table.select(_select, [ws_table, ws_cur, ws_hidden], [*dir_outputs, *file_outputs])
            ws_file_path.submit(_preview, [ws_file_path, page_zero], file_outputs)
            ws_prev.click(lambda f, p: _preview(f, max(0, int(p or 0) - 1)) if f else [gr.update()] * len(file_outputs),
                          [ws_file, ws_page], file_outputs)
            ws_next.click(lambda f, p: _preview(f, int(p or 0) + 1) if f else [gr.update()] * len(file_outputs),
                          [ws_file, ws_page], file_outputs)

            # -- 关键词搜索 → 点击结果跳到对应页 --
            def _search(query, cur):
                status, rows = handlers["on_dir_search"](query, cur)
                return status, rows, gr.update(visible=bool((query or "").strip()) and not rows)

            search_outputs = [ws_search_status, ws_results, ws_results_empty]
            ws_search_btn.click(_search, [ws_search, ws_cur], search_outputs)
            ws_search.submit(_search, [ws_search, ws_cur], search_outputs)

            def _open_result(data, cur, evt: gr.SelectData):
                row = _pick_row(data, evt)
                if not row:
                    return [gr.update()] * len(file_outputs)
                try:
                    line = int(row[1])
                except (TypeError, ValueError):
                    line = 1
                page_size = getattr(service, "FILE_PREVIEW_PAGE", 200) or 200
                full, _is_dir = handlers["join_entry"](cur, "📄", str(row[0]))  # 相对路径 → 完整路径
                return _preview(full, max(0, line - 1) // int(page_size))

            ws_results.select(_open_result, [ws_results, ws_cur], file_outputs)

            # -- 发到代码助手：填入路径并切到「代码」子页 --
            ws_to_code.click(lambda f: (f or ".", gr.Tabs(selected="code")), ws_file, [ca_path, tabs],
                             show_progress="hidden")

            # -- 编辑（受 shell_enable 门控）--
            def _edit_open(path):
                content, hint = handlers["on_file_edit_load"](path)
                return gr.update(visible=True), content, hint

            ws_edit_btn.click(_edit_open, ws_file_path, [ws_edit_box, wf_content, wf_hint])
            wf_close.click(lambda: gr.update(visible=False), None, ws_edit_box, show_progress="hidden")
            wf_confirm.bind(handlers["on_write_file"], [ws_file_path, wf_content, wf_append], wf_result).then(
                _preview, [ws_file_path, ws_page], file_outputs,
            ).then(_go, [ws_cur, ws_hidden], dir_outputs)

            # -- 命令（P2-4：自然语言 → 命令 → 分析 → 执行 / 确认执行；P3-2：历史命令回填）--
            section("命令 · 用自然语言描述，或直接输入命令")
            with gr.Row(elem_classes=["cb-inline-actions"]):
                ex_cmd = gr.Textbox(placeholder="如：列出当前目录最大的 5 个文件 / git status", show_label=False,
                                    container=False, scale=1)
                ex_gen = gr.Button("AI 生成命令", elem_classes=["cb-btn"], min_width=110)
                ex_analyze = gr.Button("分析", variant="primary", elem_classes=["cb-btn"], min_width=72)
                ex_run = gr.Button("执行", variant="primary", elem_classes=["cb-btn"], min_width=72, visible=False)
                ex_confirm = Confirm("确认后执行", "该命令会修改系统，确认执行？", min_width=120)
                ex_confirm.trigger.visible = False
            with gr.Row(elem_classes=["cb-inline-actions"]):
                ex_history = gr.Dropdown(
                    choices=handlers["on_shell_history"](), value=None, label="历史命令（选中即回填并分析）",
                    allow_custom_value=False, filterable=True, scale=1, elem_classes=["cb-history"],
                )
            ex_note = gr.Markdown(elem_classes=["cb-status"])
            ex_risk = gr.Markdown(elem_classes=["cb-status"])
            ex_result = result_md(classes=["cb-code"])

            def _analyze(cmd):
                md, can_run, needs = handlers["on_exec_analyze"](cmd)
                return md, gr.update(visible=can_run), gr.update(visible=needs)

            analyze_outputs = [ex_risk, ex_run, ex_confirm.trigger]
            ex_analyze.click(_analyze, ex_cmd, analyze_outputs)
            ex_cmd.submit(_analyze, ex_cmd, analyze_outputs)
            _locked(ex_gen, [ex_gen], handlers["on_shell_generate"], ex_cmd, [ex_cmd, ex_note],
                    gate=shell_enable).then(_analyze, ex_cmd, analyze_outputs)

            def _run_checked(cmd):
                """「执行」前复核：命令若在分析后被改成需确认的，拒绝直跑。"""
                _md, can_run, _needs = handlers["on_exec_analyze"](cmd)
                if not can_run:
                    return "💡 命令已变更，请重新点「分析」"
                return handlers["on_exec_run"](cmd)

            def _history_update():
                return gr.update(choices=handlers["on_shell_history"](), value=None)

            ex_run.click(_run_checked, ex_cmd, ex_result).then(_history_update, None, ex_history,
                                                               show_progress="hidden")
            ex_confirm.bind(handlers["on_exec_run"], ex_cmd, ex_result).then(_history_update, None, ex_history,
                                                                             show_progress="hidden")

            def _pick_history(cmd):
                if not cmd:
                    return gr.update(), gr.update(), gr.update(), gr.update()
                return (cmd, *_analyze(cmd))

            ex_history.input(_pick_history, ex_history, [ex_cmd, *analyze_outputs])

            shell_payload = gr.State("")
            ex_result.change(lambda c, r: f"$ {c}\n{r}" if r else "", [ex_cmd, ex_result], shell_payload,
                             show_progress="hidden")
            _result_actions(handlers, chat_refs, kind="shell", tab="工作区 · 命令", payload=shell_payload)

            gated = [ws_edit_btn, wf_content, wf_append, wf_confirm.trigger,
                     ex_cmd, ex_gen, ex_analyze, ex_run, ex_confirm.trigger, ex_history,
                     gc_confirm.trigger]

            def _gate(on):
                return [gr.update(interactive=bool(on)) for _ in gated] + [gr.update(visible=not on)]

            shell_enable.change(_gate, shell_enable, [*gated, gc_gate_hint], show_progress="hidden")
            # Gradio 惰性渲染子页：Git 子页未渲染时对其 Markdown 的 visible 更新会丢失（interactive 不会），
            # 故进入 Git 子页时按总开关状态重新同步提示的可见性。
            git_tab.select(lambda on: gr.update(visible=not on), shell_enable, gc_gate_hint, show_progress="hidden")
            for c in gated:
                c.interactive = False

    return {"cwd_md": cwd_md, "git_refresh": _overview, "git_outputs": git_outputs}
