# F9: Web「工具」页重构需求（AI 优先 · 结构化展示 · 跨页联动）

> 功能编号 F9 · 状态 **⏳ 待实现**（立项 2026-09-07）· 分支 `feat/web-tools-revamp`
> 目标：Web「工具」页从"registry 直通命令面板"升级为"AI 驱动的工作台"——删除无增量价值的网络搜索子页，
> 修复数据库连接失效缺陷，各子页以自然语言为主入口、结构化展示结果、结果可流转到对话。
>
> 本文件只记录**需求与已核实的代码事实**；实现记录、与需求的差异、验证结果见 [README.md](README.md)；
> 交给 Agent 的启动提示词见 [PROMPT.md](PROMPT.md)；功能索引见 [../README.md](../README.md)。
> §0 中的 `文件:行号` 为**立项时**位置，实现后会变动，仅作定位参考。

## 目录

| 章节 | 内容 |
|---|---|
| [§0 背景](#0-背景已核实的代码事实实施时勿重复调研) | 工具页现状、五个子页缺陷、可复用的 AI 与 UI 资产、工程约束 |
| [§1 P1](#1-p1--止血与骨架高) | 删网络搜索 · DB 透传修复 · Git 仪表盘 · 结果流转（AI 解读 / 发送到对话） |
| [§2 P2](#2-p2--ai-主入口中) | 代码助手 · DB 自然语言转 SQL · 工作区文件浏览 · Shell 自然语言生成命令 |
| [§3 P3](#3-p3--体验打磨低) | 连接记忆 · 命令历史 · 提交信息 diff 预览与一步提交 |
| [§4 UI 规范](#4-ui-规范全-p-级共用) | 布局、组件、样式、交互约定 |
| [§5](#5-实施顺序与交付) | 实施顺序与交付 |
| [附录 A](#附录-a--llm-提示词草案实施时可微调保持简短) | LLM 提示词草案 |

## 0. 背景（已核实的代码事实，实施时勿重复调研）

### 0.1 工具页结构

| 层 | 位置 | 说明 |
|---|---|---|
| UI | `src/web/ui/tools.py:11` `build_tools_page(service, handlers)` | 5 个 `gr.Tab`：网络搜索 `:16` / 代码分析 `:41` / Git `:60` / 数据库 `:75` / Shell 与文件 `:122`；返回 `{"cwd_md"}` 但 `layout.py:77` 未接收 |
| 挂载 | `src/web/ui/layout.py:77` | 只传 `service, handlers`，**未传** `session_state`（`:39`）/ `nav`（`:41`）/ 对话页组件 |
| handlers | `src/web/app.py:1486-1522, 1800-1838` | `on_web_*` / `on_code_ast :1500` / `on_code_quality` / `on_git_analyze :1506` / `on_git_commit_gen :1509` / `on_db_* :1512-1521` / `on_exec_analyze :1808` / `on_exec_run :1818` / `on_read_file :1824` / `on_write_file :1830` / `on_cwd :1833`；全部返回 Markdown 字符串，`_fmt_result :1404` 把 `[错误]/[提示]/[成功]` 转图标 |
| service | `src/web/services.py:1148-1401` | `run_tool :1148` → `agent_tools.registry.execute(name, args, auto_confirm)`；`web_* :1167-1182`、`code_ast :1186`、`code_quality :1192`、`git_analyze :1196`、`git_commit_gen :1205`、`db_connect :1209`、`db_query :1216`、`db_execute :1222`、`db_schema :1228`、`db_create_table :1303`、`db_insert :1315`、`exec_analyze :1343`、`exec_run :1358`、`read_file :1371`、`write_file :1386`、`cwd :1396`、`chdir :1401` |
| 工具实现 | `src/agent_tools.py`（单文件，`ToolRegistry :21`，`registry :759`） | 所有工具返回 **纯文本 str**，前缀 `[成功]/[错误]/[提示]`；`registry.execute` 截 5000 字 |

工具页全部为**同步、非流式、不可取消**调用；除 Git「AI 生成提交信息」外**没有任何 LLM 参与**；没有"发送到对话 / 用 AI 解读"的跨页联动。

### 0.2 各子页已确认的缺陷

**网络搜索**：`web_search :589` / `web_content_extract :658` 输出纯文本；对话页 RAG / 自动模式已有"联网搜索"开关（`rag_query_stream :493`），Agent 亦可自行调用 `web_search`。独立子页无增量价值。缓存操作 `web_cache_status :715` / `web_cache_clear :745`（非 safe，`auto_confirm=True`）。

**代码分析**：`ast_search :805` 基于标准库 `ast`（`src/code_analyzer/ast_analyzer.py:56`，**非 tree_sitter**，仅 Python），目录模式用 `pattern in name` 子串匹配且忽略 `search_by`，最多 20 条纯文本；`code_quality_check :846` 文件模式返回 summary + 前 10 条 issue，目录模式只返回汇总。`QualityChecker`（`quality_checker.py:129`）可选调 pylint / bandit / radon。**零 LLM 路径**。

**Git**：`git_analyze :890` 返回 `history / status / authors` 三种纯文本；UI 是 Radio + 一个按钮。`GitAnalyzer`（`src/git_integration/git_analyzer.py:62`）已有 `get_current_branch :100`、`get_commit_history(max_count) :105`、`get_status :217`、`get_author_stats :259`、`get_branches :212`，可直接产出结构化数据。`git_commit_gen :945` → `CommitMessageGenerator`（`commit_generator.py:29`）：`get_staged_changes :46` 取 diff，`_generate_ai_commit_message :130` 直连 `/api/generate`，失败回退规则；UI 看不到 diff 就生成，也不能一步提交。

**数据库**（含功能性 Bug）：
1. `services.db_query / db_execute / db_schema / db_create_table / db_insert`（`:1216-1323`）**只传 `sql` / `table`，不传 `db_type` / `database`**；而 `database_query :1094` 等每次 `DatabaseConnector(db_type, database=database)` 新建连接、默认 `sqlite` + `:memory:`。结果：「连接」子页选的库对后续操作**无效**，每次查询都在全新内存库上执行。`TOOL_USAGE.md:70` 写的"按 (db_type, database) 缓存"与代码不符。
2. `DatabaseType` 枚举 4 种，`_create_connection`（`db_connector.py:60-77`）只实现 sqlite，其余 `NotImplementedError`；`docs/features/README.md:44` 已把 MySQL / PostgreSQL 列为"不做"。UI 下拉仍提供三种。
3. 无表列表：UI 提示"留空列出所有表"，但 `database_get_schema :1235` / `QueryExecutor.get_table_schema :218` 只查单表。
4. 无 NL→SQL；`SQLGenerator`（`sql_generator.py:25`）仅模板拼接 + `validate_sql :201`。
5. `QueryResult`（`query_executor.py:17`）已有 `rows / columns / row_count / execution_time / success / error_message / affected_rows`，但 registry 路径把它拍平成文本。
6. 连接参数无任何持久化（无 config / 环境变量）。

**Shell 与文件**：
- `execute_command :253` `shell=True`，`cwd=os.getcwd()`；`CommandSafetyChecker.analyze :94-184` 四级（critical 拦截 / high / medium 需确认 / low）；Web 有总开关 `shell_enable`（`tools.py:123`，默认关）+ 分析→执行两步 + `Confirm`。AI 仅做风险分级，命令由用户手写。
- `read_file :218`（按行范围）/ `write_file :237`（`is_path_allowed :201`：cwd 或 `WRITE_ALLOWED_DIRS`）已暴露；`list_directory :276`、`search_files :388`（子串）**未暴露**。读文件要手填路径 + 起始行 + 行数，无浏览、无预览、无语法高亮。

### 0.3 可复用的 AI 与 UI 资产

| 资产 | 位置 | 用途 |
|---|---|---|
| 流式桥 | `WebService._bridge(run, on_finish) :287`；`StreamEvent(kind, message, data) :108`，kinds `progress/answer/step/error/done/heartbeat/cancelled/confirm`；`is_running :219`、`stop_current :227` | 所有 LLM 长任务必须经此，UI 才可显示进度与取消 |
| 单 Agent | `agent_chat_stream :595` → `self._react_factory(on_step, on_confirm, context)`（默认 `_default_react_factory :36`）；`ReActEngine.__init__ :271` 已支持 `allowed_tools`、`system_prompt_extra`、`max_iterations`，但工厂**未透传**这两个参数 | 带工具的 AI 动作（代码助手） |
| 纯 LLM | `collaboration/llm_helper.complete_text(prompt, num_predict, timeout, temperature) :20`（`think=False`）、`complete_json(prompt, complete=None) :107`（可注入）；`rag_pipeline.llm_direct_answer(prompt) :167` | NL→SQL、生成命令、AI 解读 |
| 对话页联动 | `chat.py:71 msg_box`、`:135 pending_msg = gr.State("")`（"用单 Agent 重试"回填模板 `:190-200`）、`:274` 返回 dict 只暴露 `chatbot/status_box`；`layout.py:83 _switch(page)` 按 `nav` 切换 5 个 Column | "发送到对话"需暴露 `msg_box`/`mode` 并对 `nav` 输出 `gr.update(value=...)` |
| UI 组件 | `ui/common.py`：`page_title :9`、`section :15`、`result_md :20`、`table :24`（只读 `gr.Dataframe(type="array")`）、`pick_cell :53`（配 `.select`，用法见 `knowledge.py:136,234`）、`Confirm :66`（`.bind/.on_open/.trigger`）、`toggle_visible :130` | 表格、二步确认 |
| 样式 | `src/web/theme.py BASE_CSS :138-307`：`.cb-cards/.cb-card .k/.v :241`、`.cb-result :253`、`.cb-code pre :254`、`.cb-risk-low/medium/high/critical :255`、`.cb-kv :260`、`.cb-inline-actions :248`、`.cb-confirm :250`、`.cb-hint :232`、`.cb-action-bar :270`、`.cb-segment :203`、`.cb-empty :258` | 卡片 / 结果面板 / 风险色 |
| 格式化纯函数 | `app.py`：`format_stats_cards :548`（卡片 HTML 范例）、`format_kv_table :461`、`format_exec_analysis :444`、`format_sources :124` | 新增 `format_*` 照此写法，可单测 |
| 运行时状态目录 | `.cerebro/`（gitignored；`runtime_paths.py`） | P3 连接记忆 / 命令历史落盘 |

### 0.4 工程约束（沿用现有规范）
- 测试：`./venv/bin/python -m pytest -q -n 4`，全量覆盖 ≥80%；新逻辑必须有单测（Mock Ollama，模式见 `tests/test_web_services.py`、`tests/test_web_app.py`）；`src/web/ui/*` 标 `# pragma: no cover`，改动后需浏览器手动验证。
- 分层：引擎 / 工具库 → `src/web/services.py`（唯一接引擎处）→ `src/web/app.py`（`format_*` / `build_handlers`，可单测）→ `src/web/ui/*`。handler 返回值个数必须与 outputs 一致。
- 工具注册名 / 参数名不得改动（改则同步 `prompts/system/PROJECT_RULES.md`、`docs/development/ai-assistant/TOOL_USAGE.md`、测试）；本需求**不新增 registry 工具**，结构化数据在 service 层直接调用 `git_integration` / `database_tools` / `os` 获得。
- 新 LLM 提示词：短、只输出目标格式、`think=False`、`num_predict` 限额；解析失败必须有回退。
- 每个 P 级完成更新 `CHANGELOG.md [Unreleased]`、`README.md` 相关段落、本目录 `README.md`、`docs/features/README.md`、`docs/features/f7-web-ui/README.md:31` 工具页描述、`TOOL_USAGE.md:70` 连接缓存描述。
- Git：不得直接提交 master；完成后询问是否建 PR，不得自动建 PR。

---

## 1. P1 · 止血与骨架（高）

### 目标
去掉无价值子页、修复 DB 功能性缺陷、Git 改为可读的仪表盘、建立"结果流转"通用机制，为 P2 的 AI 主入口铺好骨架。

### 需求
- **P1-1 删除「网络搜索」子页**：移除 `tools.py` 网络搜索 Tab 及 `on_web_search / on_web_extract / on_web_cache_status / on_web_cache_clear` handler 与对应 service 方法（`services.py:1167-1182`）及其测试；**registry 工具与 CLI `/web-*` 保持不变**。缓存状态 / 清空（含 `Confirm`）迁到「系统」页运行环境区，一行 `.cb-inline-actions`。页面副标题改为"AI 驱动的代码 / Git / 数据库 / 工作区工具，结果可发送到对话继续追问。"；子页顺序 `代码 | Git | 数据库 | 工作区`。
- **P1-2 DB 连接上下文透传**：`WebService` 新增 `_db_ctx: Dict = {"db_type": "sqlite", "database": ":memory:"}`；`db_connect` 成功后写入；所有 `db_*` 方法透传 `db_type` / `database`。UI 连接区改为：SQLite 文件路径输入（默认 `:memory:`，`placeholder` 示例 `./data/app.db`）+ `连接` 按钮 + 当前连接状态芯片（`.cb-status-chip`）；**移除** `db_type` 下拉（后端仅 sqlite）。先写复现测试：连接 A 库建表后 `db_query` 能查到该表。
- **P1-3 表列表与 Schema 面板**：`QueryExecutor` 新增 `list_tables() -> List[str]`（`sqlite_master`）；`database_get_schema(table="")` 返回全部表名列表（保持工具名 / 参数名不变，仅放宽空值语义）。UI 左栏 `table(["表名"])`，连接成功后自动刷新；点击行 → 右栏显示该表 schema 表格（列 / 类型 / 约束）。
- **P1-4 DB 结果表格化**：`WebService.db_query` 改为 service 层直接用 `QueryExecutor.execute_query` 拿 `QueryResult`，返回 `Dict`（`columns/rows/row_count/execution_time/error`）；handler `on_db_query -> (status_md, headers, rows)`，UI 用 `gr.Dataframe` 显示（最多 500 行，超出提示）。`db_execute` 同样返回 `affected_rows`。删除「创建表」「插入数据」两个 JSON 表单（由 P2-2 NL→SQL 覆盖）；`db_create_table / db_insert` service 方法与 handler 一并删除。
- **P1-5 Git 仪表盘**：`WebService.git_overview(repo_path=".") -> Dict`：`branch`、`changed: List[{status, path}]`、`commits: List[{hash7, author, date, subject}]`（最近 20）、`authors: List[{name, commits}]`、`last_commit_at`、`is_repo`。`app.py` 新增 `format_git_cards(overview)`（4 张卡：当前分支 / 变更文件 / 最近提交时间 / 提交者数）与 `git_changes_rows / git_commits_rows / git_authors_rows`。UI 布局：顶部卡片行 → 下方两栏（左：变更文件表；右：`gr.Tabs` 最近提交 / 提交者统计）→ 底部 AI 动作行（保留「AI 生成提交信息」，P3-3 增强）。进入 Git 子页或点击 `刷新` 时加载；非 git 目录显示 `.cb-empty` 提示。移除 Radio。
- **P1-6 结果流转（通用机制）**：
  - `WebService.ai_explain_stream(kind: str, payload: str, question: str = "") -> Iterator[StreamEvent]`：按 `kind`（`code|git|db|shell|file`）选附录 A-5 模板，`payload` 截 6000 字，经 `_bridge` 调 `llm_helper.complete_text(num_predict=768)`，`answer` 事件返回；`is_running()` 时返回 `error` 事件"有任务进行中"。
  - 每个子页的主结果面板下方统一一行 `.cb-inline-actions`：`用 AI 解读`（本页流式输出到 `ai_md`，旁边 `停止` 按钮 → `stop_current`）与 `发送到对话`。
  - `发送到对话`：`layout.py` 把对话页 `msg_box`、`mode` 与 `nav` 传给 `build_tools_page(service, handlers, chat_refs)`；点击后 `msg_box` 填入模板（附录 A-6，结果截 4000 字）、`mode` 切到「自动」、`nav` 切到对话页；**不自动发送**（用户可编辑后再发，避免与进行中的任务冲突）。`chat.py:274` 返回 dict 增加 `msg_box`、`mode`。
  - 「代码」「工作区」子页在 P1 先保留现有控件不动，只挂上这行动作（P2 再重构）。

### 验收
- `tests/test_web_services.py`：DB 透传复现测试通过；`list_tables`；`db_query` 返回结构化 dict；`git_overview` 用临时 git 仓库（`tmp_path` + `subprocess git init`）断言字段；`ai_explain_stream` Mock `complete_text` 产出 `answer` + `done`，并发时 `error`。
- `tests/test_web_app.py`：`format_git_cards`、各 `*_rows`、`on_db_query` 三元组、`_fmt_result` 对新前缀。
- `src/web/` 中 `web_search|web_extract|web_cache` 仅剩系统页两个缓存 handler；`grep -n "db_type" src/web/ui/tools.py` 无下拉。
- 浏览器验证：连接 `tmp.db` → 表列表出现 → 点表看 schema → 查询出表格 → `用 AI 解读` 有流式输出且可停止 → `发送到对话` 跳到对话页且输入框已填充。

---

## 2. P2 · AI 主入口（中）

### 目标
每个子页的第一入口是自然语言；AI 产出的动作（SQL / 命令）先预览、用户确认后执行；结果结构化。

### 需求
- **P2-1 代码助手**：
  - `_default_react_factory` 与 `WebService.__init__` 的 `react_factory` 签名增加 `allowed_tools=None, system_prompt_extra="", max_iterations=None` 透传。
  - `WebService.code_assist_stream(action: str, path: str, extra: str = "") -> Iterator[StreamEvent]`：`action ∈ {explain, review, tests, docs, refactor}`（附录 A-1）；校验 `path` 存在；经 `_bridge` 运行 `ReActEngine(allowed_tools={read_file, list_directory, search_files, ast_search, code_quality_check, get_current_dir}, max_iterations=12)`；`on_step` → `step` 事件，最终答案 → `answer`。若 `path` 是单文件且 ≤ 6000 字，直接把内容放进 prompt（省一次 `read_file` 往返）。
  - UI：顶部 路径输入（默认 `.`，`placeholder` "文件或目录，可从工作区选择") + 可选补充说明（单行）；一行 5 个动作按钮 `解释代码 / 审查问题 / 生成测试 / 生成文档 / 重构建议` + `停止`；下方 `处理过程`（可折叠 `gr.Accordion`，显示 step 事件）与 结果 `result_md`；再下方是 P1-6 动作行。折叠区「高级：符号搜索 / 质量检查」：符号搜索结果改为表格（名称 / 类型 / 文件 / 行号 / 复杂度，由 `ASTAnalyzer.search_functions/search_classes` 直接产出而非解析文本，且尊重 `search_by`）；质量检查改为 卡片（评分 / 问题数 / 严重度分布）+ 问题表格（严重度 / 行 / 描述）。新增 `WebService.code_symbols(pattern, path, search_by) -> List[Dict]`、`code_quality_report(path) -> Dict`。
  - 工作区（P2-3）选中文件时联动填入路径。
- **P2-2 DB 自然语言转 SQL**：
  - `WebService.db_nl2sql(question: str) -> Dict{sql, kind, note}`：拼接当前库全部表 schema（截 3000 字）+ 问题 → `complete_text(num_predict=256, temperature=0)`（附录 A-2）；去掉 ``` 围栏；`SQLGenerator.validate_sql` 校验；`kind = select|write|invalid`（按首个关键字）。失败返回 `kind=invalid` + `note`。
  - UI 主区：自然语言输入 → `AI 生成 SQL` → SQL 编辑框（`gr.Code(language="sql")`，可手改，也可直接手写）→ `运行`：`kind=select` 直接执行 `db_query`；否则按钮变为 `Confirm("执行写操作")` 走 `db_execute`。结果表格复用 P1-4；下方 P1-6 动作行（`用 AI 解读` 的 payload = SQL + 前 50 行）。
  - 未连接时主区置灰并提示"先连接数据库"。
- **P2-3 工作区文件浏览**：
  - `WebService.list_dir(path=".") -> Dict{path, parent, entries: List[{kind, name, size, mtime}]}`（`os.scandir`，目录在前、按名排序、跳过隐藏项可选 Checkbox；路径不存在 / 非目录返回 `error`）；`WebService.search_in_dir(query, path) -> List[Dict{file, line, text}]`（复用 `agent_tools.search_files` 逻辑但返回结构化，最多 50 条）。
  - UI 左栏（scale 2）：面包屑（当前路径 Markdown + `上级` 按钮 + 路径输入回车跳转）、关键词搜索框、`table(["", "名称", "大小", "修改时间"])`（`kind` 列用 `📁/📄`）；`.select` → 目录进入 / 文件预览。右栏（scale 3）：文件预览 `gr.Code`（自动按后缀选 language，`read_file(offset, limit=200)` + `上一页 / 下一页`）、文件路径行、动作行 `用 AI 总结`（P1-6，kind=file）/ `发送到对话` / `发到代码助手`（填入 P2-1 路径并切 Tab）/ `编辑`（展开写入框 + `追加` Checkbox + `Confirm("保存")`，受 `shell_enable` 门控）。
  - 移除原「读取文件」手填行号表单；`write_file` 表单并入「编辑」。
- **P2-4 Shell 自然语言生成命令**：
  - `WebService.shell_generate(intent: str) -> Dict{command, note}`：`complete_text(num_predict=128, temperature=0)`（附录 A-3，附 `os.name` / cwd）；只取第一行、去围栏；空则 `note="未生成"`。
  - UI 工作区底部「命令」区：一行输入框既可写自然语言也可写命令，右侧两个按钮 `AI 生成命令`（结果回填输入框并自动触发风险分析）与 `分析`；后续沿用现有 分析 → 执行 / 确认执行 流程与 `.cb-risk-*` 展示；输出 `result_md(classes=["cb-code"])` + P1-6 动作行（kind=shell，payload = 命令 + 输出）。总开关 `shell_enable` 保留并同时门控「编辑」与「命令」。

### 验收
- `tests/test_web_services.py`：`code_assist_stream`（注入 `react_factory` 断言 `allowed_tools` / `max_iterations` 透传与 step/answer 事件、路径不存在报错）；`db_nl2sql`（Mock `complete_text` 返回围栏 SQL / 非法文本 → `kind`）；`list_dir`（`tmp_path` 目录树、隐藏项开关、错误路径）；`search_in_dir`；`shell_generate`（多行输出只取首行、空输出）；`code_symbols` 尊重 `search_by`。
- `tests/test_web_app.py`：`format_quality_cards`、`symbol_rows`、`dir_rows`、`format_dir_breadcrumb`、`on_db_nl2sql` 返回 SQL 与按钮可见性更新元组、语言映射 `guess_code_language(".py") == "python"`。
- 浏览器验证：代码助手「解释代码」对 `src/web/ui/common.py` 有 step 与最终答案且可停止；DB 自然语言"每个表有多少行"生成 SQL 并运行；工作区浏览 → 预览 → 发到代码助手；命令区"列出当前目录最大的 5 个文件"→ 生成命令 → 分析 → 执行。

---

## 3. P3 · 体验打磨（低）

### 需求
- **P3-1 连接记忆**：`.cerebro/web_tools_state.json`（`runtime_paths` 解析；`{"recent_databases": [...≤8], "shell_history": [...≤50]}`）；`WebService` 惰性读写，测试用 `tmp_path` monkeypatch 路径。UI 连接区路径输入改为 `gr.Dropdown(allow_custom_value=True)` 列出最近库；启动时不自动连接。
- **P3-2 命令历史**：`exec_run` 成功后写入 `shell_history`（去重、最新在前）；UI 命令区下方 `gr.Dropdown` "历史命令"，选中回填输入框并触发分析。
- **P3-3 提交信息增强**：`WebService.git_commit_preview() -> Dict{staged_files, diff_stat, has_staged}`（`git diff --cached --stat`）；UI 点「AI 生成提交信息」先显示暂存文件 + stat 卡片，若无暂存给出 `.cb-hint`"请先 `git add`"；生成结果放入可编辑 `gr.Textbox(lines=4)`；新增 `Confirm("提交")` → `WebService.git_commit(message) -> str`（`git commit -m`，受 `shell_enable` 门控，走 `CommandSafetyChecker` 记录 medium）；成功后刷新仪表盘。
- **P3-4 空态与加载态**：所有表格空数据显示 `.cb-empty` 文案；长任务按钮在运行期 `interactive=False`；`ai_md` 显示 heartbeat 期间的"思考中…"。

### 验收
- 状态文件读写、上限裁剪、损坏 JSON 回退空；`git_commit_preview` / `git_commit` 用临时仓库；历史去重。
- 浏览器验证：重启 Web 后最近库仍在下拉；提交流程端到端。

---

## 4. UI 规范（全 P 级共用）

| 项 | 约定 |
|---|---|
| 页面结构 | `page_title` → `gr.Tabs`（代码 / Git / 数据库 / 工作区）；每个子页：**输入区（自然语言优先）→ 动作行 → 结构化结果 → 结果流转行 → 折叠"高级"** |
| 输入 | 单行 `gr.Textbox(show_label=False, container=False)` 置于 `.cb-inline-actions` Row，主按钮 `variant="primary"`；`submit` 与主按钮同 handler |
| 结构化结果 | 列表用 `common.table`（只读 Dataframe）；指标用 `.cb-cards` 卡片 HTML（`gr.HTML`）；代码 / 输出用 `gr.Code` 或 `result_md(classes=["cb-code"])`；键值用 `format_kv_table` |
| AI 输出 | `result_md` + 旁置 `停止` 按钮；进行中禁用触发按钮；step 事件放 `gr.Accordion("处理过程", open=False)` |
| 危险操作 | 一律 `Confirm`（写 SQL / 写文件 / 执行 medium+ 命令 / git commit）；`shell_enable` 总开关默认关，门控 编辑 / 命令 / 提交 |
| 空态 / 错误 | `.cb-empty`；错误经 `_fmt_result` 统一图标；不抛裸异常到 UI |
| 两栏布局 | `gr.Row` 内 `gr.Column(scale=2)` + `gr.Column(scale=3)`；≤ 900px 由 Gradio 自动堆叠，不写额外媒体查询 |
| 新样式 | 仅在 `theme.py BASE_CSS` 追加（如 `.cb-breadcrumb`、`.cb-toolbar`），复用现有变量，深浅主题都要看 |
| 文案 | 中文、动词开头、≤ 8 字按钮；不出现工具注册名（如 `database_query`） |

---

## 5. 实施顺序与交付

```
P1-1 删网络搜索 → P1-2 DB 透传（先复现测试）→ P1-3 表列表 → P1-4 结果表格 → P1-5 Git 仪表盘 → P1-6 结果流转
P2-1 代码助手（先做 react_factory 透传）→ P2-3 工作区（P2-1 依赖其选路径联动，可并行）→ P2-2 NL→SQL → P2-4 Shell 生成
P3-1 连接记忆 → P3-2 命令历史 → P3-3 提交增强 → P3-4 空态/加载态
```

每个 P 级独立可提交、可发 PR。交付物：改动文件清单、新增测试数、覆盖率、验收项逐条结果、浏览器截图（工具页四个子页）、未完成 / 风险。

---

## 附录 A · LLM 提示词草案（实施时可微调，保持简短）

统一要求：`think=False`；不含寒暄；输出只含目标内容。`{...}` 为运行时填充。

### A-1 代码助手动作（`system_prompt_extra`，配合 ReAct 协议）
```
角色：代码助手。目标路径：{path}。用户补充：{extra}
动作 = {action}：
- explain：先说明用途与入口，再按调用顺序讲关键函数/类，最后列出依赖与注意点。
- review：按 严重度(高/中/低) 列问题，每条给 位置(文件:行)、原因、修复建议；无问题要明说。
- tests：给出 pytest 测试代码（可直接落盘的完整文件），覆盖正常路径与边界，Mock 外部 I/O。
- docs：生成模块级 docstring 与 README 片段（用途、用法示例、参数说明）。
- refactor：列 3-5 条可落地的重构建议，每条给 动机、改法、风险。
规则：只读，不得写文件或执行命令；引用代码时标 文件:行；结论用中文。
```
（`path` 为单文件且 ≤6000 字时，追加 `文件内容：\n{content}`，并在规则中加"内容已给出，勿再 read_file"。）

### A-2 NL→SQL（`complete_text`，`num_predict=256`，`temperature=0`）
```
你是 SQLite 专家。仅输出一条 SQL，不要解释、不要围栏。
表结构：
{schema}
问题：{question}
```

### A-3 自然语言 → Shell 命令（`num_predict=128`，`temperature=0`）
```
把需求转成一条 {os_name} shell 命令。当前目录：{cwd}。只输出命令本身，一行，不要解释。
禁止破坏性操作（rm -rf、格式化、管道到 sh）。
需求：{intent}
```

### A-4 AI 生成提交信息（沿用 `commit_generator.py:130` 现有提示，不改）

### A-5 用 AI 解读（`num_predict=768`）
按 `kind` 选首句，其余相同：
```
{lead}
内容：
{payload}
{question_or_empty}
要求：中文，≤300 字，先结论后依据；有风险或异常先说。
```
| kind | lead |
|---|---|
| code | 解读下面的代码分析结果，指出最值得关注的问题与下一步。 |
| git | 解读下面的 Git 信息，总结近期改动主题、活跃度与潜在风险。 |
| db | 解读下面的 SQL 与查询结果，说明数据含义与异常值。 |
| shell | 解读下面的命令与输出，说明结果含义与可能的问题。 |
| file | 总结下面文件的用途、结构与关键点。 |

### A-6 发送到对话（填入 `msg_box` 的模板，非 LLM 提示）
```
以下是工具页「{tab}」的结果，请基于它继续分析：
```
{payload}
```
我的问题：
```
