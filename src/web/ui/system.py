"""系统页：模型管理 / 运行环境与工作目录 / 工具清单 / 帮助。"""  # pragma: no cover
from __future__ import annotations

from typing import Any, Callable, Dict

import gradio as gr

from .common import page_title, result_md, section, table

HELP_MD = """
### 页面导航

| 页面 | 用途 | 对应 CLI 命令 |
|---|---|---|
| 💬 对话 | RAG 检索 / 单 Agent / 多 Agent 协作，多轮追问，右侧查看处理过程与来源 | `/ask` `/agent` `/sources` `/summary` `/history` `/context` `/compact` `/reset` |
| 侧栏 · 会话 | 新建（可携带摘要）/ 切换 / 搜索 / 归档 / 删除，详情见对话页右侧 | `/session-*` |
| 📚 知识库 | 上传或按路径追加入库、重建 / 清空索引、文件管理（表格行「⋯」：详情 / 删除文件，清理 / 去重）、快照（「⋯」：详情 / 恢复追加或替换 / 生成脚本 / 删除，批量清理自动快照）、Skills 与摘要 | `/add` `/stats` `/file-*` `/file-delete` `/snapshot-*` `/generate-skills` `/knowledge-summary` |
| 🕸️ 知识图谱 | 3D / 2D 交互式图谱视图（类型 / 置信度 / 节点数 / 聚焦实体筛选）、概览卡片，实体 / 类型 / 邻居 / 路径 / 相似查询，从文本或文件构建 | `/graph-query` `/graph-build` `/graph-summary` `/graph-export` |
| 🧰 工具 | 网络搜索与正文提取、AST 搜索与质量检查、Git 分析与提交信息、数据库读写、Shell 与文件读写 | `/web-*` `/code-*` `/git-*` `/db-*` `/exec` `/file` `/write` |
| ⚙️ 系统 | 模型热切换与思考模式、运行环境、工作目录、工具清单 | `/model` `/think` `/pwd` `/cd` `/tools` |

### 对话小贴士

- **模式**：RAG 检索适合基于知识库/网络的问答；单 Agent 会调用工具读写文件、执行命令；多 Agent 把复杂任务拆给多个角色协作。
- **危险操作审批**：单 Agent 执行会修改系统的命令时，对话区上方会弹出审批卡片，点「允许 / 拒绝」；勾选「自动确认」等价 CLI `--yes`。
- **追问**：直接输入"它多少钱"这类省略式问题，系统会结合上下文改写后检索。
- **上下文过长**：状态行提示后可「压缩历史」或「新建会话（携带摘要）」。
- **停止**：任一模式运行中都可点「停止」。

### 主题色

右上角下拉可切换主题色，选择会保存在浏览器中；跟随系统深浅色模式（或在地址后加 `?__theme=dark`）。
"""


def build_system_page(service, handlers: Dict[str, Callable], sb: Dict[str, Any]) -> Dict[str, Any]:  # pragma: no cover
    page_title("系统", "模型热切换、思考模式、运行环境与工作目录、工具清单。")
    headers = handlers["headers"]
    model_chip = sb["model_chip"]

    with gr.Tabs():
        # ---------------- 模型 ----------------
        with gr.Tab("模型"):
            model_status = gr.Markdown(handlers["on_model_status"]())
            _choices, _current = handlers["on_model_choices"]()
            with gr.Row(elem_classes=["cb-inline-actions"]):
                model_dd = gr.Dropdown(
                    choices=_choices, value=_current or None, show_label=False, container=False,
                    allow_custom_value=True, scale=1, min_width=240,
                )
                switch_btn = gr.Button("切换模型", variant="primary", elem_classes=["cb-btn"], min_width=100)
                refresh_btn = gr.Button("刷新列表", elem_classes=["cb-btn"], min_width=96)
                think_cb = gr.Checkbox(
                    value=bool(service.current_model().get("think")), label="思考模式（慢，适合复杂推理）",
                    container=False, scale=0, min_width=220,
                )
            switch_result = result_md()
            gr.Markdown("切换后立即生效并释放旧模型；思考模式开启需模型支持，不支持时自动回弹。", elem_classes=["cb-muted"])
            model_table = table(headers["models"], handlers["on_model_table"](), max_height=260, search=False)

            def _switch(model):
                msg, status = handlers["on_switch_model"](model)
                return msg, status, handlers["on_model_chip"](), handlers["on_model_table"]()

            switch_btn.click(_switch, model_dd, [switch_result, model_status, model_chip, model_table])

            def _refresh():
                choices, current = handlers["on_model_choices"]()
                return gr.update(choices=choices, value=current or None), handlers["on_model_table"]()

            refresh_btn.click(_refresh, None, [model_dd, model_table])

            def _think(enabled):
                msg, status, actual = handlers["on_toggle_think"](enabled)
                return msg, status, actual, handlers["on_model_chip"]()

            think_cb.input(_think, think_cb, [switch_result, model_status, think_cb, model_chip])
            def _pick_model(data, evt: gr.SelectData):
                try:
                    return str(data[evt.index[0]][0])
                except Exception:  # noqa: BLE001
                    return gr.update()

            model_table.select(_pick_model, model_table, model_dd)

        # ---------------- 运行环境 ----------------
        with gr.Tab("运行环境"):
            section("工作目录（Git / 代码 / Shell 工具默认作用于此）")
            with gr.Row(elem_classes=["cb-inline-actions"]):
                cwd_input = gr.Textbox(placeholder="目录路径，如 ~/Projects/demo", show_label=False, container=False, scale=1)
                cd_btn = gr.Button("切换目录", variant="primary", elem_classes=["cb-btn"], min_width=96)
            cwd_md = gr.Markdown(handlers["on_cwd"](), elem_classes=["cb-status"])
            cd_result = result_md()

            def _cd(path):
                msg, cwd = handlers["on_chdir"](path)
                return msg, cwd, handlers["on_env_info"]()

            section("配置概览（来自环境变量 / .env，只读）")
            env_md = gr.Markdown(handlers["on_env_info"](), elem_classes=["cb-kv"])
            cd_btn.click(_cd, cwd_input, [cd_result, cwd_md, env_md])
            cwd_input.submit(_cd, cwd_input, [cd_result, cwd_md, env_md])

        # ---------------- 工具清单 ----------------
        with gr.Tab("工具清单"):
            gr.Markdown(
                "Agent 可调用的全部工具。**安全** = 只读、自动执行；**需确认** = 会修改系统，"
                "单 Agent 模式下弹出审批卡片；`rm -rf /` 等危险命令一律拦截。",
                elem_classes=["cb-muted"],
            )
            tools_table = table(headers["tools"], handlers["on_tools_table"](), max_height=480)

        # ---------------- 帮助 ----------------
        with gr.Tab("帮助"):
            gr.Markdown(HELP_MD)

    return {"env_md": env_md, "cwd_md": cwd_md, "tools_table": tools_table}
