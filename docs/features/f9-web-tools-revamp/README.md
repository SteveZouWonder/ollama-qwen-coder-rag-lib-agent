# F9: Web「工具」页重构（AI 优先 · 结构化展示 · 跨页联动）

## 实施状态

**🚧 P1 已完成，P2 / P3 待实现** · 分支 `feat/web-tools-revamp` · 立项 2026-09-07
· 目标：工具页从 registry 直通命令面板升级为 AI 驱动的工作台

| 级别 | 主题 | 状态 | 完成日期 | 提交 |
|---|---|---|---|---|
| P1 | 止血与骨架：删网络搜索（Web）· DB 当前连接下沉共享层（Web + CLI 同时修复）· Git 仪表盘 · 结果流转（AI 解读 / 发送到对话） | ✅ | 2026-09-07 | 见分支 `feat/web-tools-revamp` |
| P2 | AI 主入口：代码助手 · DB 自然语言转 SQL · 工作区文件浏览 · Shell 自然语言生成命令 | ⏳ | — | — |
| P3 | 体验打磨：连接记忆 · 命令历史 · 提交信息 diff 预览与一步提交 · 空态/加载态 · CLI `/git-analyze` `/db-query` `/db-schema` rich 表格 | ⏳ | — | — |

## 文档导读

| 文件 | 内容 | 适合 |
|---|---|---|
| [REQUIREMENTS.md](REQUIREMENTS.md) | 需求分项与验收标准；§0 为立项时核实的代码事实（带 `文件:行号`）；§4 UI 规范；附录 A 为 LLM 提示词草案 | 了解"要做什么、为什么" |
| 本文件 | 实现记录（每项做了什么、落在哪个模块）、与需求的差异、验证结果 | 了解"实际做成了什么" |
| [PROMPT.md](PROMPT.md) | 交给 Agent 的启动提示词，按 P1 / P2 / P3 分三段、各自可独立粘贴 | 分批派发实现任务 |

用户可感知的变更同步记录在 [CHANGELOG.md](../../../CHANGELOG.md) `[Unreleased]` 与主 [README](../../../README.md) 对应段落。

## 立项背景

Web「工具」页（F7 交付）五个子页的问题：

| 子页 | 问题 |
|---|---|
| 网络搜索 | 对话页已内置联网开关，独立子页无增量价值，浏览器直接搜更直观 |
| 代码分析 | 仅标准库 `ast` 文本输出，零 LLM 参与 |
| Git | 原始 `git log` 文本，排版差；AI 生成提交信息看不到 diff、不能一步提交 |
| 数据库 | **功能性 Bug（Web 与 CLI 共有）**：连接参数不透传，所有查询落在临时 `:memory:` 库；无表列表、无 NL→SQL；UI 提供后端未实现的 MySQL/PostgreSQL |
| Shell 与文件 | 手填路径 / 行号；AI 只做风险分级，命令需用户手写；`list_directory` / `search_files` 未暴露 |
| 全局 | 无跨页联动（不能发送到对话 / 让 AI 解读）；全部同步阻塞不可取消 |
| CLI | `/db-*` 同一 Bug；`/git-analyze` `/db-query` 纯文本输出。`/web-* /code-* /file /exec` 保留（终端无浏览器替代，AI 入口由 `/agent` 覆盖） |

详细事实与行号见 [REQUIREMENTS.md §0](REQUIREMENTS.md#0-背景已核实的代码事实实施时勿重复调研)。

## 页面重组

```
工具
├── 代码      自然语言动作（解释 / 审查 / 测试 / 文档 / 重构）→ ReAct 流式；高级：符号表 / 质量卡片
├── Git       卡片 + 变更文件表 + 提交表；AI 提交信息（diff 预览 → 可编辑 → 确认提交）
├── 数据库    SQLite 连接 → 表列表 / Schema；自然语言 → SQL 预览 → 运行；结果表格
└── 工作区    文件浏览 / 预览 / 编辑；自然语言 → 命令 → 风险分析 → 执行；命令历史
每个结果面板：[用 AI 解读] [发送到对话]

CLI：/db-connect <path>（单参数）· /db-schema（无参列表）· /git-analyze /db-query /db-schema rich 表格；其余命令不变
```

## 实现记录

### P1（2026-09-07）

| 编号 | 实现位置 | 差异 |
|---|---|---|
| P1-1 删网络搜索子页 | `src/web/ui/tools.py` 重写（四子页 代码 \| Git \| 数据库 \| 工作区，副标题更新）；`services.web_search / web_extract` 与 `app.on_web_search / on_web_extract` 删除；缓存状态 / 清空（`Confirm`）迁到 `src/web/ui/system.py` 运行环境区；`HELP_MD` 工具页描述同步；CLI `/web-*` 与 registry 工具不变 | 无 |
| P1-2 DB 当前连接 | 新增 `src/database_tools/session.py`（`set_current / get_current / clear_current / resolve / get_connector / current_connector / describe`）；`agent_tools.database_*` 经 `_db_executor()` 解析回退并复用连接器，`database_connect` 成功后 `set_current`；`db_connector.py` sqlite `check_same_thread=False` + `RLock`（Web 请求线程池跨线程复用）；Web `db_connect(database)` 单参数 + 状态芯片 `format_db_status` + 「断开」；CLI `handle_db_connect` 单参数（`/db-connect sqlite` 视为用法错误）、`/help` 与 `TUTORIAL_TEXT` 新增数据库段 | ① **额外修复**：CLI `/db-execute /db-create-table /db-insert` 原本把 `[CONFIRM_REQUIRED]` 协议串打印给用户（工具 `safe=False` 且未 `auto_confirm`），现改为 `_confirm` 后 `auto_confirm=True`，否则验收流程 `/db-execute` 走不通。② DDL `rowcount=-1` 归一为 0。③ 新增「断开」按钮（需求未列，便于切库） |
| P1-3 表列表与 Schema | `QueryExecutor.list_tables()`；`database_get_schema(table="")` 列出全部表（`table` 改为可选，工具名 / 参数名不变）；Web `WebService.db_tables / db_table_schema`，UI 左栏表格 `.select` → 右栏 列 / 类型 / 约束；CLI `/db-schema` 无参列表 | 未知表名此前返回空 schema 仍打「[表]」，现返回 `[错误] 表 x 不存在或没有列` |
| P1-4 结果表格化 | `WebService.db_query -> Dict{sql, columns, rows, row_count, execution_time, truncated, error?}`（`DB_MAX_ROWS=500`；非只读语句拒绝并提示用「执行」）、`db_execute -> Dict{affected_rows, execution_time, error?}`；`app.on_db_query -> (status_md, headers, rows)`、`on_db_execute -> (status_md, tables_rows)`；UI 用 `gr.Dataframe(headers=…, value=…)` 更新表头；`db_create_table / db_insert` service + handler + 测试删除 | 为让「用 AI 解读」拿到 SQL + 前 50 行，新增 `format_db_payload` 与 `on_db_payload`（需求未列） |
| P1-5 Git 仪表盘 | **共享层** `GitAnalyzer.is_repo() / get_overview(max_commits)`（`git_integration/git_analyzer.py`，P3-5 CLI 直接复用；作者统计用 `git log %an` 计数而非 `shortlog`，并给 `_run_git_command` 加 `stdin=DEVNULL` 防阻塞）；`WebService.git_overview`；`app.format_git_cards / git_changes_rows / git_commits_rows / git_authors_rows / format_git_payload`；UI 卡片行 → 两栏（变更文件表 / 最近提交 · 提交者统计 Tabs）→ 动作行；`git_tab.select` 与「刷新」触发；Radio 移除 | `changed` 项除 `status / path` 外多带 `label`（中文标签），供 Web 与 CLI 共用 |
| P1-6 结果流转 | `WebService.build_explain_prompt / ai_explain_stream`（附录 A-5，`payload` 截 6000，`complete_text(num_predict=768)` 可注入，经 `_bridge`，`is_running()` 时 `error`）；`app.on_ai_explain`（流式 yield）、`format_send_to_chat`（附录 A-6，截 4000）与 `on_send_to_chat`；`tools.py::_result_actions` 统一动作行（用 AI 解读 / 停止 / 发送到对话 + `ai_md`）；`chat.py` 返回 dict 增加 `msg_box / mode / mode_auto`；`layout.py` 传 `chat_refs`（含 `nav / nav_chat`）；`theme.py` 新增 `.cb-result-actions / .cb-ai-explain` | 「代码」「工作区」子页控件未重构，只挂动作行（按需求）。解读 payload 通过 `gr.State` 由结果组件 `.change` 聚合 |

## 验证记录

### P1

- 测试：全量 `./venv/bin/python -m pytest tests -q -n 4` → **2845 passed, 36 skipped**，覆盖率 **90.10%**（门禁 80%）。
  测试数 2807 → 2880（净增 73；含删除 5 个旧用例）：新增`tests/test_agent_tools_database.py`（19，新文件：session 模块 / 回退复现 / 显式优先 / 连接复用 / `:memory:` 持久 / schema 列表）、
  `tests/test_cli_handlers_database.py`（18，新文件：`/db-connect` 单参数与兼容 / `/db-schema` 无参 / 写操作确认 / 真实 registry 集成）、
  `tests/test_web_services.py`（+19 净增：`TestDbStructured` / `TestGitOverview`（临时 git 仓库）/ `TestAiExplain`）、
  `tests/test_web_app.py`（+17 净增：`TestGitFormatters` / `TestDbFormatters` / `TestResultFlow`）。
- 验收 grep：`grep -rnE "\b(web_search|web_extract|web_cache\w*)\b" src/web/` 仅剩 `web_cache_status / web_cache_clear`
  两组 service + handler；`grep -n db_type src/web/ui/tools.py` 无结果；`grep -n ":memory:" src/web/services.py src/cli_handlers.py` 无结果。
- 浏览器（Playwright chromium，`launch(server_port=7861)`）：四个子页截图正常，**0 console error / 0 服务端 Traceback**；
  连接 `/tmp/f9_browser.db` → 表列表 `orders / users` → 点 `users` 显示 `PK / NOT NULL / DEFAULT 18` → 查询出 2 行表格 →
  「用 AI 解读」进入「正在解读…」并可「停止」（服务层实测 Ollama 返回解读文本）→ 「发送到对话」跳到对话页、模式「自动」、输入框已填模板。
- CLI（`CODE_AGENT_AUTO_CONFIRM=true`，stdin 管道）：`/db-connect /tmp/t.db` → `/db-execute CREATE TABLE…`（影响 0 行）→
  `/db-execute INSERT…`（影响 2 行）→ `/db-query SELECT…`（返回 2 行 Alice / Bob）→ `/db-schema`（共 1 张表 - users）→ `/db-schema users`（列信息）。
- 已知：`tests/conftest.py` 全局 Mock 了 `subprocess.run/Popen`，Git 概览测试在类级 fixture 内还原真实实现。

## 相关文档

- [F7 Web 界面](../f7-web-ui/README.md) — 工具页原始交付
- [F6 系统能力增强](../f6-capability-tools/) — 工具页调用的 registry 工具来源
- [MODULE_GUIDES.md web/](../../development/ai-assistant/MODULE_GUIDES.md) · [TRAP_AVOIDANCE.md Gradio](../../development/ai-assistant/TRAP_AVOIDANCE.md)
