# F9: Web「工具」页重构（AI 优先 · 结构化展示 · 跨页联动）

## 实施状态

**🚧 P1 / P2 已完成，P3 待实现** · 分支 `feat/web-tools-revamp` · 立项 2026-09-07
· 目标：工具页从 registry 直通命令面板升级为 AI 驱动的工作台

| 级别 | 主题 | 状态 | 完成日期 | 提交 |
|---|---|---|---|---|
| P1 | 止血与骨架：删网络搜索（Web）· DB 当前连接下沉共享层（Web + CLI 同时修复）· Git 仪表盘 · 结果流转（AI 解读 / 发送到对话） | ✅ | 2026-09-07 | `40b035a` |
| P2 | AI 主入口：代码助手 · DB 自然语言转 SQL · 工作区文件浏览 · Shell 自然语言生成命令 | ✅ | 2026-09-08 | 见分支 `feat/web-tools-revamp` |
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

### P2（2026-09-08）

| 编号 | 实现位置 | 差异 |
|---|---|---|
| P2-1 代码助手 | `services._default_react_factory` 增加 `allowed_tools / system_prompt_extra / max_iterations` 透传（仅非空时传给 `ReActEngine`，旧调用不受影响）；新增 `services.ScratchContext`（只实现 `build_messages / record / clear`，让代码助手不读不写用户对话会话）；`WebService.build_code_assist_prompt`（附录 A-1）/ `code_assist_stream`（校验动作与路径 → `is_running` 互斥 → 单文件 ≤6000 字内联 → `_bridge` 内 `react_factory(allowed_tools=CODE_ASSIST_TOOLS, max_iterations=12, on_confirm=拒绝)` → `step` / `answer(step_log)` / `done`）；`code_symbols`（`ASTAnalyzer.search_functions / search_classes` 逐文件，目录模式亦尊重 `search_by`，类复杂度 = 方法复杂度之和，上限 200）；`code_quality_report`（`check_file` / `check_project` + `get_project_summary`，问题按严重度排序，上限 200）。`app.py`：`on_code_assist`（yield `(处理过程, 结果)`，复用 `ProgressTracker`）、`SYMBOL_HEADERS / symbol_rows / format_symbols_status / format_symbols_payload`、`QUALITY_ISSUE_HEADERS / format_quality_cards / quality_issue_rows / format_quality_payload`、`on_code_symbols / on_code_quality_report`。UI：路径 + 补充说明 → 5 动作按钮 + 停止 → `Accordion("处理过程")` → 结果 → 结果流转行 → `Accordion("高级")`（符号表 / 质量卡片 + 问题表）；路径输入变化时同步高级区路径 | ① 删除了被替代的 `services.code_ast / code_quality` 与 `app.on_code_ast / on_code_quality`（文本版）。② 质量卡片多一张「文件数」；问题表「行」列在目录模式为 `文件:行`（需求只写 3 列，未增列）。③ 代码助手不透传 `on_confirm` 交互确认——工具集只读，危险操作一律拒绝 |
| P2-2 NL→SQL | `WebService.sql_kind`（按首关键字 `select / write / invalid`，忽略前导 `--` 注释）、`db_schema_text`（`表(列 类型 [PRIMARY KEY])` 每表一行，截 3000）、`_strip_fences`、`db_nl2sql`（附录 A-2，`complete_text(num_predict=256, temperature=0)`，只保留第一条语句；模型异常 / 空 / 不可识别 → `kind=invalid` + `note`；`SQLGenerator.validate_sql` 为假时 `note` 提示高危；写操作 `note` 提示需确认）；`db_query` 同样忽略前导注释。`app.py`：`on_db_nl2sql -> (sql, 提示, 可运行, 需确认)`、`on_sql_kind`、`on_db_connected`。UI：自然语言输入 + 「AI 生成 SQL」→ `gr.Code(language="sql")` 编辑框（`.change` 实时切换「运行」/「执行写操作」Confirm 可见性）→ 结果表格；未连接时自然语言输入 / 按钮置灰并提示"先连接数据库"，连接 / 断开 / 进入子页时刷新门控 | ① `validate_sql` 为假不判 `invalid`（它把 DELETE 也算危险，属合法写操作），改为保留 `kind=write` 并在 `note` 提示；`invalid` 只用于模型失败 / 不可识别。② **Gradio 6.20 缺陷规避**：可编辑 `gr.Code` 若初始值为空则不渲染编辑器，且后续任何写值都触发前端 `props_invalid_value` 并中断整次更新；动态切换其 `interactive` 亦如此。故编辑框给非空初始注释 `-- 在此手写 SQL，或用上方自然语言生成`、始终可编辑，仅门控自然语言区（未连接时运行会得到明确的"尚未连接"错误） |
| P2-3 工作区 | `WebService.list_dir`（`os.scandir`，目录在前按名排序，`show_hidden`，返回 `path / parent / entries[{kind,name,size,mtime}] / truncated`，错误路径 / 非目录 → `error`）、`file_preview(path, page, page_size=200)`（分页读取，越界收敛）、`search_in_dir`（复用 `agent_tools.SEARCH_FILE_EXTS / SEARCH_SKIP_DIRS`——从 `search_files` 内联集合提为模块常量——返回 `file / rel / line / text`，最多 50 条，行截 200 字）。`app.py`：`DIR_HEADERS / dir_rows / format_dir_breadcrumb / abbreviate_home / join_entry / format_size / guess_code_language / SEARCH_HEADERS / search_rows / format_file_preview_status / format_file_payload`，handlers `on_list_dir / on_dir_parent / on_file_preview / on_file_edit_load / on_dir_search`。UI 左栏（scale 2）：面包屑 + 路径输入（回车跳转）+ 上级 + 目录表（`.select` 目录进入 / 文件预览）+ 搜索框 + 隐藏项 + 结果表（`.select` 跳到命中行所在页）；右栏（scale 3）：状态行 + `gr.Code` 预览（按后缀选 `language`）+ 上一页 / 下一页 + 文件路径（回车打开）+「发到代码助手」（填路径并 `gr.Tabs(selected="code")`）+「编辑」（展开编辑框：≤2000 行加载全文，否则提示用追加；`Confirm("保存")` → `write_file` → 刷新预览与目录）+ 结果流转行（「用 AI 总结」）。移除「读取文件」表单，「写入文件」并入编辑 | ① 预览用服务层 `file_preview` 直接读文件返回结构化 dict，而非解析 `read_file` 工具文本（需求写 `read_file(offset, limit=200)`）；`services.read_file` 与 `app.on_read_file` 随之删除。② 路径显示把主目录缩写为 `~`（面包屑 / 路径框 / 文件路径框），状态里也存 `~` 路径，因此共享层 `agent_tools.read_file / write_file / list_directory / search_files / ast_search / code_quality_check` 增加 `os.path.expanduser`（Agent 与 CLI 同样受益）。③ 隐藏项开关放在搜索行而非路径行（路径太长时挤压输入框） |
| P2-4 NL→命令 | `WebService.shell_generate`（附录 A-3，附 `platform.system()` 与 cwd，`complete_text(num_predict=128, temperature=0)`，去围栏、取首个非空行、去 `$` 提示符；空 → `note="未生成"`）。`app.on_shell_generate -> (命令, 提示)`。UI：命令输入框 + 「AI 生成命令」（`.then` 自动触发分析）+ 「分析」+ 「执行」/「确认后执行」；`_run_checked` 在「执行」前复核命令仍为可直跑（防止分析后改成 medium+ 命令直跑）；`shell_enable` 同时门控 编辑按钮 / 编辑框 / 保存 与 命令输入 / 生成 / 分析 / 执行 | 去掉了 P1 里"命令文本变化即隐藏执行按钮"的 `.change` 钩子（与「生成 → 自动分析」链式更新竞态），改为「执行」前服务端复核 |

## 验证记录

### P2

- 测试：全量 `./venv/bin/python -m pytest tests -q -n 4` → **2901 passed, 36 skipped**，覆盖率 **90.41%**（门禁 80%；`src/web/app.py` 97%、`src/web/services.py` 91%）。
  新增 58 个用例：`tests/test_web_services.py` +35 —— `TestReactFactoryPassthrough / TestCodeAssist / TestCodeSymbolsAndQuality / TestDbNl2Sql / TestWorkspaceBrowse / TestShellGenerate`；
  `tests/test_web_app.py` +20 —— `TestCodeAssistFormatters / TestNl2SqlHandlers / TestWorkspaceFormatters / TestWorkspaceHandlers`；`tests/test_agent_tools_file.py` +3 —— `TestTildePaths`。
  删除 1 个被替代功能的旧用例（`test_code_ast_args`），改写 2 个（`read_file` 相关断言改为断言旧 handler 已移除）；全量计数 2845 → 2901。
- 浏览器（Playwright chromium + 真实 Ollama `qwen3.5:4b`，`launch(server_port=7861)`）：四个子页截图正常，**0 console error / 0 pageerror / 0 服务端 Traceback**，20 项自动检查全部通过：
  - 代码助手：工作区选中 `src/web/ui/common.py` →「发到代码助手」路径已填、Tab 切到「代码」→「解释代码」处理过程出现 step、最终答案为结构化解读（用途 / 关键函数表 / 依赖）→ 再发起「审查问题」点「停止」显示已停止；高级区符号搜索 `pick` 命中 `pick_cell`，质量检查出评分 / 严重度分布卡片与问题表。
  - 数据库：未连接时提示"先连接数据库"→ 连接 `/tmp/f9_p2.db` → 表列表 `orders / users` → 自然语言"users 表有多少行"生成 `SELECT COUNT(*) FROM users;`、显示「运行」→ 运行返回 1 行（3）。
  - 工作区：面包屑 `📂 ~/…/src/web/ui · 9 项` → 预览 `common.py` 第 1/1 页带 Python 高亮 → 搜索 `def pick_cell` 找到 1 处（相对路径 `common.py:53`）→ 启用总开关前「编辑」不可用；启用后打开 `tmp_f9_edit.txt` → 编辑框载入原文 → 勾「追加」→ 保存 → 确定 → 文件追加成功且预览刷新。
  - 命令：输入"列出当前目录最大的 5 个文件"→「AI 生成命令」得 `ls -S | head -n 5` → 自动分析「风险等级：低 · 只读命令」→「执行」输出文件列表。
- Gradio 6.20 已知问题（见 P2-2 差异 ②）：可编辑 `gr.Code` 需非空初始值且不可动态切换 `interactive`，否则前端报 `props_invalid_value` 并丢弃整次更新，页面无任何提示。已用最小复现定位并在 `tools.py` 注释说明。

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
