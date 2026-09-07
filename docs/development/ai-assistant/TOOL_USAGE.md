# Agent 工具参考

`src/agent_tools.py` 的 `registry.register(...)` 是工具名 / 参数 / 描述 / 安全标记的**唯一事实源**；本文按其摘录。改工具后同步：`prompts/system/PROJECT_RULES.md`「Parameter names」段、子 Agent 白名单（`agents/*_agent.py` + `agent_config.py`）、`tests/test_agent_tools*.py`、`tests/multi_agent/test_specialized_agents.py`、`tests/test_project_rules.py`，以及本文。

## 1. 注册表机制

- `ToolRegistry.register(name, func, description, params: dict[str, str], safe=True)`；参数是否必填由描述文本含 `(必填)` 判定。
- `get_descriptions(names=None, compact=False)`：系统提示用 `compact=True`，输出 `- name(必填, 可选?): 描述 [需确认]`，`names` 过滤即子 Agent 白名单。
- `execute(name, args, auto_confirm=False)` 返回字符串（截 5000 字）：
  - 未知工具 → `[错误] 未知工具: X`
  - `safe=False` 且未 `auto_confirm` → `[CONFIRM_REQUIRED] name|{json args}`（不执行，交 ReAct 层走 `on_confirm`）
  - 异常 → `[错误] 工具执行失败: …`
- ReAct 层（`react_engine.py`）在此之上再生成：`[安全拦截]`（critical 命令）、`[用户拒绝]`、`[格式错误]`、`[重复调用]`、`[错误] 工具 X 不在当前允许的工具集内`；单条 Observation 再截到 `OBSERVATION_MAX_CHARS`(3000)。

## 2. 工具表（28 个）

`*` = 必填；「确认」= `safe=False`，单 Agent 需用户确认（CLI y/n、Web 审批卡片、`--yes` / `CODE_AGENT_AUTO_CONFIRM=true` 放行），子 Agent 白名单内自动放行。

### 文件与命令

| 工具 | 参数 | 确认 | 说明 / 返回约定 |
|---|---|---|---|
| `read_file` | `path*`, `offset`(0), `limit`(100) | | 按行范围读；目录路径会报错，先 `list_directory` |
| `write_file` | `path*`, `content*`, `append`(false) | ✔ | 路径须在 cwd 或 `WRITE_ALLOWED_DIRS` 内，否则 `[错误] 路径超出允许范围`；成功 `[成功] 写入/追加 <abs> 共 N 字符`；自动建父目录 |
| `execute_command` | `command*`, `timeout`(30) | ✔ | `shell=True`，cwd 为当前目录；输出 stdout + `[stderr]` + `[退出码]`，截 4000 字；超时 `[错误] 命令超时`。安全分级见 §3 |
| `list_directory` | `path`(.) | | |
| `analyze_project_structure` | `project_path`(.) | | 技术栈 / 关键文件识别 |
| `search_files` | `query*`, `path`(.), `max_results`(10) | | 关键字搜索代码文件（参数名是 `query`，不是 `keyword`） |
| `get_current_dir` | — | | |

### 知识库

| 工具 | 参数 | 确认 | 说明 / 返回约定 |
|---|---|---|---|
| `query_knowledge_base` | `question*` | | 走 `rag_pipeline.answer_question(kb_only=True, enable_web_search=False)`，**不联网**。返回：`[知识库概览]…`（元查询）/ `[知识库命中] …答案… 相关片段(top-3)`/ `[知识库无相关内容] …请改用 web_search…` / `[错误] 知识库引擎未初始化` |
| `add_to_knowledge_base` | `file_path*` | ✔ | PDF / 图片（OCR）/ MD / TXT / 代码；路径同 `write_file` 边界 |
| `get_knowledge_stats` | — | | 文档块数、文件数、模型 num_ctx |
| `check_knowledge_status` | — | | 持久化 / 数据量 / OCR 可用性 |

### 网络

| 工具 | 参数 | 确认 | 说明 / 返回约定 |
|---|---|---|---|
| `web_search` | `query*`, `source`(default), `max_results`(10), `use_cache`(true), `enable_fallback`(true) | | 聚合 DuckDuckGo / Baidu / Wikipedia（`WEB_SEARCH_*` 配置）；返回 `搜索结果 (N 条): 1. 标题 / URL / 来源 / 摘要…`；无结果 `[提示] 搜索未返回结果…`；模块缺失 `[错误] 网络搜索模块未安装` |
| `web_content_extract` | `url*`, `timeout`(30) | | trafilatura → requests+bs4 回退；`=== 网页内容提取 === … === 正文内容 ===`，正文截 5000 字；无效 URL `[错误] 无效的 URL 格式` |
| `clear_web_search_cache` | — | | |
| `web_cache_status` | — | | |
| `web_cache_clear` | — | ✔ | |

### 代码 / Git

| 工具 | 参数 | 确认 | 说明 |
|---|---|---|---|
| `ast_search` | `pattern*`, `path`(.), `search_by`(name \| parameter \| return \| base \| method) | | stdlib ast |
| `code_quality_check` | `path`(.), `check_type`(basic \| security \| complexity \| pylint) | | 依赖 pylint / bandit / radon 子进程，缺失时降级说明 |
| `git_analyze` | `repo_path`(.), `analysis_type`(history \| status \| authors) | | gitpython |
| `git_commit_gen` | `repo_path`(.), `use_ai`(true) | | |

### 知识图谱

| 工具 | 参数 | 确认 | 说明 |
|---|---|---|---|
| `knowledge_graph_query` | `query`, `query_type`(entity \| type \| neighbors \| path \| similar) | | `query` 未标必填（type 查询可为空） |
| `knowledge_graph_build` | `text*`, `doc_id`(manual), `doc_type`(text \| code) | | 持久化到 `.cerebro/knowledge/graph.json` |

### 数据库

| 工具 | 参数 | 确认 | 说明 |
|---|---|---|---|
| `database_connect` | `db_type`(sqlite), `database`(:memory:) | | 成功后 `database_tools.session.set_current`：设为进程级**当前连接**；只实现 sqlite（mysql / postgresql / mssql 抛 NotImplementedError） |
| `database_query` | `sql*`, `db_type`, `database` | | SELECT。未显式传 `database`（仍为默认 `:memory:`）时回退到当前连接，显式传参优先 |
| `database_execute` | `sql*`, `db_type`, `database` | ✔ | INSERT / UPDATE / DELETE / DDL（DDL 的 affected_rows 归一为 0）；同上回退 |
| `database_create_table` | `table*`, `columns*`(dict), `db_type`, `database` | ✔ | 同上回退 |
| `database_insert` | `table*`, `data*`(dict), `db_type`, `database` | ✔ | 同上回退 |
| `database_get_schema` | `table`, `db_type`, `database` | | `table` 留空 → 列出全部表名（`QueryExecutor.list_tables`）；同上回退 |

连接复用：`database_tools/session.py` 按 `(db_type, database)` 缓存 `DatabaseConnector`（sqlite `check_same_thread=False` + 连接器内 RLock，可跨 Web 请求线程），`clear_current()` 关闭全部。Web `WebService.db_*`、CLI `/db-*`、Agent 三端共用同一当前连接；测试用 `session.clear_current()` 隔离（`tests/conftest.py` autouse 已处理）。

## 3. `CommandSafetyChecker.analyze(command)` 四级判定

按顺序匹配，返回 `{risk_level, is_dangerous, needs_confirm, reason}`：

| 等级 | 规则（`agent_tools.py` 模式表） | ReAct 处理 |
|---|---|---|
| `critical` | `DANGEROUS_PATTERNS`：`rm -rf /`、`dd if=/dev/zero`、`mkfs.`、`> /dev/sda`、`chmod 777 /`、`sudo rm`、`del /f /s /q`、`format `、fork bomb、`mv / `、`cp / `、`ln -sf /` | 直接拦截，回灌 `[安全拦截] …该命令被拒绝执行` |
| `low` | `READONLY_PATTERNS` 开头：`ls pwd echo cat head tail find grep wc ps which uname whoami date df du top tree file stat`、`git status/log/diff/branch/remote/show`、`python -m pytest --collect-only`、`pip list/freeze`、`ollama list/ps` | 免确认 |
| `high` | `HIGH_PATTERNS`：`curl|wget … | sh|bash|zsh`；或含 `rm del drop truncate format` | 需确认；子 Agent 一律拒绝 |
| `medium` | `MEDIUM_PATTERNS`：`pip/npm/yarn/pnpm/brew/apt install`、`git push/commit/reset/checkout/rebase/merge`、`python x.py`、`node x.js`、`make`、`docker run/exec`；或含 `write insert update delete chmod chown mv cp` | 需确认；子 Agent 自动放行 |
| `low`（其余） | 兜底 | 免确认 |

`config.READONLY_COMMANDS` / `config.DANGEROUS_PATTERNS` 无人引用，改它们不生效。

## 4. 子 Agent 白名单（`agents/*_agent.py`，与 `agent_config.py` 一致）

| Agent | `ALLOWED_TOOLS` | `ESSENTIAL_TOOLS` |
|---|---|---|
| Code | read_file, write_file, execute_command, list_directory, search_files, ast_search, analyze_project_structure, get_current_dir | write_file, execute_command |
| Test (QAExpertAgent) | read_file, write_file, execute_command, search_files, code_quality_check | write_file, execute_command |
| Audit | read_file, search_files, code_quality_check, ast_search, git_analyze, execute_command | 任一 |
| Doc | read_file, write_file, list_directory, search_files, query_knowledge_base, web_search | write_file |
| RAG | （不走 ReAct）`query_knowledge_base` + 联网回退，经 `rag_pipeline.answer_question` | — |

未调用任何 `ESSENTIAL_TOOLS` 的结果标 `unverified` 并加 `⚠️ 该 Agent 未实际调用 … 以下内容为模型自述、未经验证：` 前缀。

## 5. 写路径边界

`write_allowed_dirs()` = `os.getcwd()` + 环境变量 `WRITE_ALLOWED_DIRS`（`os.pathsep` 分隔）；`is_path_allowed()` 用 `realpath` 解析符号链接与 `..`。适用于 `write_file` 与 `add_to_knowledge_base`；`read_file` / `list_directory` / `execute_command` 不受限（命令由安全分级约束）。

## 6. 给模型看的版本

以上事实中模型需要知道的部分（参数名、返回前缀、斜杠命令不能经 shell 执行、KB 无命中转 web_search）已写入 `prompts/system/PROJECT_RULES.md` 与 `prompts/skills/core/SKILL.md`；工具描述本身由 `get_descriptions(compact=True)` 运行时注入。不要在提示中再复制本表。
