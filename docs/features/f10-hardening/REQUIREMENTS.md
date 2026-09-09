# F10: 工程加固与体验升级需求（安全 · 发布 · 流式 · 后端抽象 · 评测 · 规模化 · 拆分）

> 功能编号 F10 · 状态 **待实现**（立项 2026-09-08；实现状态与差异见 README.md）· 分支 `docs/f10-hardening`（立项文档），实现分支按 P 级另建
> 目标：针对项目评估中发现的 7 类结构性问题，按"用户可感知价值 × 复杂度"排成 P0–P3 四级：
> P0 止血（安全误判 / 依赖与发布）→ P1 主升级（真流式 / 后端抽象 / RAG 评测）→ P2 规模化与可维护（BM25 持久化与并发 / 入口层拆分）→ P3 收尾（跨平台探测 / README 瘦身 / CLI 主文件二次拆分）。
> Web 与 CLI 同为一等入口，每项需求都注明两端落地方式。
>
> 本文件只记录**需求与已核实的代码事实**；实现记录、与需求的差异、验证结果见 [README.md](README.md)；
> 交给 Agent 的启动提示词见 [PROMPT.md](PROMPT.md)；功能索引见 [../README.md](../README.md)。
> §0 中的 `文件:行号` 为**立项时**（master `2d28905`）位置，实现后会变动，仅作定位参考。

## 目录

| 章节 | 内容 |
|---|---|
| [§0 背景](#0-背景已核实的代码事实实施时勿重复调研) | 7 类问题对应的代码事实、工程约束 |
| [§1 P0](#1-p0--止血高) | P0-1 命令安全分级修正 + 读路径边界 · P0-2 依赖钉版本 + 归档发版 + CI 矩阵 |
| [§2 P1](#2-p1--主升级中高) | P1-1 真流式输出 · P1-2 LLM 后端抽象层 · P1-3 RAG 评测集与基准脚本 |
| [§3 P2](#3-p2--规模化与可维护中) | P2-1 BM25 持久化增量 + 锁补齐 + 并发限流 · P2-2 入口层拆分 |
| [§4 P3](#4-p3--收尾低) | P3-1 Tesseract 跨平台探测 + README 瘦身 · P3-2 `query_interface.py` 二次拆分（P2-2 遗留） |
| [§5 两端规范](#5-两端规范全-p-级共用) | Web / CLI 落地与文案约定 |
| [§6](#6-实施顺序与交付) | 实施顺序与交付 |

## 0. 背景（已核实的代码事实，实施时勿重复调研）

### 0.1 问题 → 任务映射

| # | 评估发现的问题 | 用户可感知影响 | 任务 | 复杂度 |
|---|---|---|---|---|
| 3 | 命令安全靠子串黑名单；读操作无边界；`AUTO_CONFIRM` 可绕过 critical | 误报确认弹窗打断 Agent 流程；可读工作区外任意文件 | P0-1 | 低 |
| 5 | 依赖未钉版本；104 条变更未发版；CI 单平台、仅 push master | 新用户安装失败；两个月成果无安装包 | P0-2 | 低 |
| 2 | 全部 LLM 调用非流式，Web 为线程 + 心跳伪流式 | 4B 模型长回答全程只见"思考中" | P1-1 | 中 |
| 2 | 只支持 Ollama `/api/chat`，无后端抽象 | 已有 vLLM / LM Studio / 内网网关的用户无法接入 | P1-2 | 中高 |
| 6 | 无 RAG 评测集，检索 / rerank 调参无基准 | 改阈值后质量回归不可见 | P1-3 | 中 |
| 4 | BM25 全量内存重建；`lock = None`；多 Agent 并行打爆单卡 Ollama | 大库入库卡顿、>2 万块静默降级、并行超时 | P2-1 | 中高 |
| 1 | 入口层 5 个文件 1400–2700 行，Web / CLI 双份呈现 | 改一端漏一端；AI 助手定位成本高 | P2-2 | 高 |
| 7 | Tesseract 路径 macOS 硬编码；README 1322 行 | Linux / Windows OCR 报路径错误；新用户找不到入口 | P3-1 | 低 |
| 1′ | P2-2 后 `query_interface.py` 仍 1799 行（≤800 未达）：渲染 / 回调 / 引擎耦合命令与模块级状态绑死，223 处测试打桩其命名空间 | 与 #1 同（改 CLI 命令仍需在 1800 行文件里定位） | P3-2 | 中 |

### 0.2 安全（P0-1）

| 项 | 位置 | 现状 |
|---|---|---|
| 风险分级 | `src/agent_tools.py:94-184 CommandSafetyChecker.analyze` | `DANGEROUS_PATTERNS :105` / `HIGH_PATTERNS :114` / `MEDIUM_PATTERNS :119` / `READONLY_PATTERNS :128` 为正则；**`:171` 与 `:177` 用 `kw in command.lower()` 子串匹配**（`rm/del/drop/truncate/format`、`write/insert/update/delete/chmod/chown/mv/cp`）。`pip show models`（含 `del`）、`ls performance/`（含 `rm`）、`git log --format=%H`（含 `format`）均被判 high/medium |
| 写边界 | `src/agent_tools.py:189-214` `write_allowed_dirs`（cwd + `WRITE_ALLOWED_DIRS`）/ `is_path_allowed` / `path_scope_error` | 仅 `write_file :237` 与入库路径调用 |
| 读操作 | `read_file :218`、`list_directory :278`、`search_files :398` | **未调用任何边界检查** |
| 命令执行 | `execute_command :255` | `shell=True`，`cwd=os.getcwd()`，timeout 30 |
| 自动确认 | `config.py:221 AUTO_CONFIRM`（`CODE_AGENT_AUTO_CONFIRM`）；`react_engine.py:588,616`、`query_interface.py:1456`、`cli_handlers.py:79` | 开启后 **high 亦免确认**（critical 在 registry 层拦截，不受影响，需保持） |
| 子 Agent 放行 | `src/agents/base_agent.py:298 AUTO_CONFIRM_RISK_LEVELS = ("low", "medium")`，`:323` | 合理，保持 |
| 两端展示 | CLI `/config`（`query_interface.py:1517` 打印自动确认状态）；Web「系统」页（`services.py:2086` 暴露 `auto_confirm_env`） | 均不显示允许目录 |

### 0.3 依赖 / 发布 / CI（P0-2）

| 项 | 位置 | 现状 |
|---|---|---|
| 依赖 | `requirements.txt`（86 行） | 仅 2 处 `==`；有下限约束的：`posthog>=3,<4 :18`、`pypdf>=6.15,<7 :34`、`ddgs>=5.3 :42`、`trafilatura>=2.0 :44`；其余裸包名。可选重依赖（sentence-transformers、tree-sitter-language-pack、OCR）以注释给安装命令 |
| 打包依赖 | `requirements-build.txt` | 精简版，内置 tree-sitter |
| 校验脚本 | `scripts/verify_deps.sh`、`scripts/install_deps.sh`、`scripts/check_prereqs.sh` | 需与 requirements 同步 |
| CHANGELOG | `CHANGELOG.md:8 [Unreleased]` 至 `:586`；`:587 [v0.0.13] 2026-07-20` | 约 104 条一级要点未归档；git tag 最新 `v0.0.9` |
| 版本号 | `packaging/cerebro.spec:33 APP_VERSION = env`（release.yml 由 tag 注入） | 仓库内无需手改版本文件 |
| CI | `.github/workflows/ci.yml:3-6` 仅 `push: master`；`:13-14` 矩阵仅 `python 3.13`（ubuntu）；flake8 / pylint `continue-on-error`；bandit 阻断；pip-audit 带 6 个 CVE ignore（`:133-147`，均附理由） | PR 由 `pr-build-vulnerability-gate.yml` 跑构建 + pip-audit，**不跑测试** |
| 发布 | `release.yml` 由 `v*` tag 触发三平台构建，调用 `scripts/bump_changelog.py` 归档 | 不改 |

### 0.4 LLM 调用（P1-1 / P1-2）

| 调用点 | 位置 | 说明 |
|---|---|---|
| ReAct | `src/react_engine.py:775 _call_model` → `:813 "stream": False`；`chat :508`；`_parse_response :653`；`_enforce_budget :401` | 每轮一次非流式 POST `/api/chat`，temperature 0.3，`think` 默认关 |
| 纯生成 | `src/collaboration/llm_helper.py:38 complete_text`（`complete_json :107` 可注入） | rerank / 路由 / 分解 / 整合 / NL→SQL 等 |
| 会话摘要 | `src/conversation_context.py:214` | 滚动摘要 |
| 提交信息 | `src/git_integration/commit_generator.py:163` | 直连 `/api/generate` |
| 托盘预热 | `src/desktop_app.py:189` | 预热请求 |
| RAG LLM | `src/rag_engine.py:139 _setup_llm` | `llama_index.llms.ollama.Ollama`；嵌入 `OllamaEmbedding`（`nomic-embed-text`，`config.py:59`） |
| 配置 | `config.py:46 OLLAMA_BASE_URL`、`:58 LLM_MODEL`、`:64 LLM_THINK`、`:67 resolve_num_ctx`、`:101 set_llm_model`（改模块变量） | 无 provider 概念 |
| Web 伪流式 | `src/web/services.py:355 _bridge`（线程 + 队列 + 心跳）、`StreamEvent` kinds `progress/answer/step/error/done/heartbeat/cancelled/confirm`；`is_running :287`、`stop_current :295`；`rag_query_stream :561`、`agent_chat_stream :672`、`multi_agent_stream :862` | Chatbot 收到整段 `answer`，无 token 级事件 |
| CLI 输出 | `src/query_interface.py`（rich `Console`；答案面板 / 来源表） | 一次性打印 |
| 模型列表 / 健康 | `src/model_switcher.py`、`src/bootstrap.py:54-60`（Ollama 路径探测）、`desktop_app.py` 状态轮询 | 直连 Ollama `/api/tags` |

### 0.5 RAG 检索（P1-3 / P2-1）

| 项 | 位置 | 说明 |
|---|---|---|
| 检索入口 | `src/rag_engine.py:854 query_with_sources(question, progress_callback, hybrid)` | dense `TOP_K=10`、`SIMILARITY_CUTOFF=0.3` |
| BM25 | `:672 _bm25_tokenize`（中文单字 + 二字组、驼峰 / 下划线拆词）、`:731 self._bm25 = None`（入库 / 删除后失效）、`:734 _ensure_bm25` → `:759 collection.get(include=["documents","metadatas"])` **全量拉取**建 `BM25Okapi`、`:800 rrf_fuse` | `config.py:168 RAG_HYBRID_MAX_CHUNKS=20000` 超限**静默**关闭 hybrid |
| rerank | `src/rag_rerank.py:200 rerank`；`:32 CONFIDENT_SCORE=0.6` 跳过 | `llm`（默认）/ `cross-encoder`（可选依赖） |
| 编排 | `src/rag_pipeline.py:276 plan_retrieval`（多跳 ≤3）、`:727 filter_relevant_sources`（0.45）、`:971 synthesize_prompt`、`:1591 answer_question`、`:666 simple_web_search`、`:837 is_meta_query` | F9-1 已加引用程序化校验与 notices |
| 现有评测先例 | `scripts/eval_overcompliance.py` + `tests/fixtures/overcompliance_cases.json` + `tests/test_eval_overcompliance_script.py` | **不经检索**，只评忠实性；无检索质量指标。P1-3 沿用"fixture + scripts + 纯函数单测"结构 |
| 测试隔离 | `tests/conftest.py` autouse 阻断 rerank / intent_router 真实 LLM，隔离 `index_storage/`、`.cerebro/` | 评测脚本需真 Ollama，不进 CI |

### 0.6 并发（P2-1）

| 项 | 位置 | 说明 |
|---|---|---|
| 未实现的锁 | `src/agent_registry.py:18`、`src/collaboration/task_scheduler.py:22` | `self.lock = None  # 简化实现` |
| 多 Agent 并行 | `src/master_agent.py:306 _execute_parallel`（`ThreadPoolExecutor`，按依赖分波）、`:351 _run_competitive` | 子 Agent 各自独立请求同一 Ollama；单 GPU 上排队导致超时计入任务耗时 |
| 全局状态 | `config.set_llm_model :101` 改模块变量；CLI `get_conversation_context()` 单例 | 单进程单用户假设，本期不改 |

### 0.7 入口层规模（P2-2）

| 文件 | 行数 | 关键符号 |
|---|---|---|
| `src/web/app.py` | 2705 | `format_*` 纯函数、`build_handlers`、`launch :2659` |
| `src/web/services.py` | 2604 | `WebService` 门面（唯一接引擎处）、`_default_react_factory :39`、`_bridge :355` |
| `src/query_interface.py` | 2189 | `TUTORIAL_TEXT :295`、`print_help :614`、`parse_command :879`、`classify_mode :1060`、主循环 |
| `src/cli_handlers.py` | 2000 | `handle_*`、`COMMAND_HANDLERS :1950` |
| `src/desktop_app.py` | 1458 | pystray 托盘；本期不拆 |
| 覆盖率排除 | `pytest.ini:33` `src/web/ui/*` | 拆分后 omit 路径需同步 |
| 测试导入 | `tests/test_web_services.py`、`tests/test_web_app.py`、`tests/test_query_interface*.py`、`tests/test_cli_handlers*.py` | 大量 `from web.app import X` / `from cli_handlers import Y`，拆分须保留兼容导出 |

### 0.8 其他（P3-1）

| 项 | 位置 | 说明 |
|---|---|---|
| Tesseract | `config.py:315 TESSERACT_PATH` 默认 `/opt/homebrew/bin/tesseract`；`document_loader.py:16,91` 使用；`scripts/check_prereqs.sh` | 无 `shutil.which` 回退；F5 残留小项"Tesseract 引导提示"与此合并 |
| README | `README.md` 1322 行 | `docs/tutorials/01-07` 已有教程体系可承接迁移 |

### 0.10 CLI 主文件剩余规模（P3-2；核实于 P2-2 合入后 `01f3a20`）

P2-2 把 `cli_handlers.py` 拆为 `cli/handlers/`、从 `query_interface.py` 抽出 `cli/parser.py`（`ParsedCommand / parse_command / classify_mode`）与 `cli/help_text.py`（`TUTORIAL_TEXT / print_help`）后，主文件 2274 → **1799 行**，未达 ≤800。剩余分段（`# ====` 注释为界）：

| 段 | 行号 | 行数 | 与模块级状态的耦合 |
|---|---|---|---|
| 解释器自保护 | `:26-136`（`MIN_PYTHON_VERSION`、`find_venv_python`、`ensure_compatible_interpreter`、`_enforce_compatible_interpreter`） | 110 | 无；`tests/test_query_interface_interpreter_guard.py` 直接 `from query_interface import` 三个名字 |
| 第三方导入 + 全局状态 | `:138-203`（`HAS_RICH` / `HAS_READLINE` / `HAS_PROMPT_TOOLKIT` 探测、`rag_engine = None` `:198`、`react_engine = None` `:199`、`last_rag_sources` / `last_web_sources` / `command_recommender`） | 65 | **是模块级状态本体** |
| 日志 / 控制台 | `:205-292`（`_NOISY_LOGGERS`、`setup_logging`、`get_console`、`console = get_console()` `:292`） | 88 | `console` 被 80 处测试 patch |
| 教程 / 帮助包装 | `:294-316`（`show_tutorial`、`check_first_run`；`print_help` 零参包装在 `:527`） | 23 | 读 `console` / `HAS_RICH` / `Config` |
| 回调 | `:318-487`（`_progress_state`、`STEP_PHASE_EMOJI` / `STEP_PHASE_COLOR`、`_live_streaming`、`on_step_callback`、`on_confirm_callback`、`ask_progress_callback`） | 170 | 读写 `_progress_state`（conftest `reset_module_state` 重置它）、`console`、`HAS_RICH`；`tests/test_query_interface_progress.py` 以 `from query_interface import ask_progress_callback as original_callback` 导入 |
| 界面渲染 | `:489-634`（`CEREBRO_ASCII`、`print_banner`、`backend_banner_text`、`print_tools`、`print_rag_sources`、`_source_code_location`、`count_code_sources`、`print_knowledge_stats`） | 146 | 读 `console` / `HAS_RICH` / `rag_engine`；`tests/test_query_interface_render.py` 74 处 `@patch("query_interface.console")` / `HAS_RICH` / `rag_engine` |
| readline / 输入 | `:636-665`（`setup_readline`、`get_input`） | 30 | 读 `HAS_READLINE` / `HAS_PROMPT_TOOLKIT` |
| 命令推荐辅助 | `:671-765`（`show_command_recommendations`、`record_command_execution`、`record_conversation`、`_conversation`、`_print_health_hint`、`_health_before`） | 95 | `record_command_execution` 被 40 处 patch；`_health_before` / `_print_health_hint` / `_conversation` 各 1–3 处 |
| 共享 RAG 编排适配 | `:768-915`（10 个 `rag_pipeline` 别名赋值 `:774-783`、`run_web_search`、`_cli_ask_progress`、`_render_meta_overview`、`print_web_sources`、`_synthesize_prompt`（**`:891` 重定义了 `:782` 的别名**，flake8 F811 既有）） | 148 | 读 `console` / `HAS_RICH`；`tests/test_query_interface_answer_strategy.py` 用 `qi._cli_ask_progress` / `qi._synthesize_prompt` / `qi._parse_web_sources` / `qi._format_kb_context` |
| 引擎耦合命令 | `:918-1526`（`_render_answer`、`_live_answer`、`_print_notices`、`_citation_summary`、`handle_clear / history / summary / reset / file / write / exec / pwd / cd / model / think / auto / ask`、`_run_ask`、`_ingest_inline_file`、`_augment_with_web_search`、`_answer_question`、`handle_agent`、`handle_natural`、`_route_natural_to_agent`、`handle_unknown_cmd`、`_ENGINE_HANDLERS :1509`） | **609** | 直接读写 `rag_engine` / `react_engine` / `last_rag_sources` / `last_web_sources` / `console` / `HAS_RICH` / `Config`；`tests/test_cli_handlers_context.py`（86 处）、`test_cli_handlers_model.py`（35）、`test_query_interface_exec_safety.py`（9）、`test_streaming_p1_1.py`（11）用 `patch.object(qi, "rag_engine", …)` / `qi.Config.AUTO_ROUTE` 等打桩 |
| 上下文装配 / 分发 / 主循环 | `:1529-1796`（`_build_cli_context`、`dispatch_command`、`main`） | 268 | `main` 227 行：argparse、引导、引擎创建、REPL 循环 |

测试对 `query_interface` 命名空间的打桩共 **223 处**（9 个文件）：`console` 80、`HAS_RICH` 66、`record_command_execution` 40、`rag_engine` 24、`Config.AUTO_ROUTE` 11、`react_engine` 9、`Config.AUTO_CONFIRM` 6、`_health_before` 3、`os.path.exists` 2、`registry` / `_print_health_hint` / `_conversation` / `Config.SHOW_PROGRESS` / `Config.LLM_MODEL` 各 1。这些打桩要求被测函数**在运行时从 `query_interface` 模块全局取名**——把函数搬到新模块后，它们从新模块的全局取名，旧打桩失效（P2-2 已在 13 处遇到并改为打桩实现模块）。

CLI 与 Web 已对齐的部分：Web 侧 `web/services/*` 用 `self._rag_engine` 实例属性 + 工厂注入，不存在模块级状态；CLI 侧 `cli/handlers/*` 经 `CLIContext`（`cli/handlers/base.py`，dataclass：`console / has_rich / rag_engine / react_engine / print_help / show_tutorial / print_tools / print_knowledge_stats / record_command / …`）注入——`query_interface._build_cli_context :1529` 每次分发时从模块全局装配一个新实例。`_ENGINE_HANDLERS` 段的函数签名为 `handle_xxx(arg)` 而非 `handle_xxx(ctx, parsed)`，是它们没能随 F7 进入 `cli_handlers` 的原因。

### 0.9 工程约束（沿用现有规范）

- 测试：`./venv/bin/python -m pytest -q -n 4`，全量覆盖 ≥80%；新逻辑必须有单测（Mock Ollama / requests，`tmp_path` 隔离，不读写 `index_storage/`、`.cerebro/`）。
- 分层：工具库 → `src/web/services.py`（唯一接引擎）→ `src/web/app.py`（可单测）→ `src/web/ui/*`（`# pragma: no cover`）；CLI：`query_interface.py::parse_command/print_help/TUTORIAL_TEXT` + `cli_handlers.py::COMMAND_HANDLERS`。**Web 与 CLI 共用逻辑放共享层，两端都要验证**。
- 工具注册名 / 参数名不得改动；改工具描述须同步 `prompts/system/PROJECT_RULES.md`、`docs/development/ai-assistant/TOOL_USAGE.md`、测试。
- 新依赖：兼容 Python 3.13、钉版本，同步 `requirements.txt` / `requirements-build.txt` / `scripts/*deps*.sh`；PyInstaller 需 `collect_all` 的库补入 `packaging/cerebro.spec`。
- 新环境变量：加入 `config.py` 常量与 `Config` dataclass，写入 `README.md` 环境变量表。
- 每个 P 级完成更新 `CHANGELOG.md [Unreleased]`、`README.md` 相关段落、本目录 `README.md`、`docs/features/README.md`、涉及的 `docs/development/ai-assistant/*`。
- Git：改动前询问是否新建分支及分支名；不得直接提交 master；完成后询问是否建 PR，不得自动建 PR。

---

## 1. P0 · 止血（高）

### 目标
两项改动都小、用户当天可感知：Agent 不再被误报确认打断、读操作不越界；安装可复现、两个月的成果可发版。

### P0-1 命令安全分级修正 + 读路径边界

**用户场景**：Agent 模式执行 `pip show models` / `ls performance/` / `git log --format=%H` 时弹出"高风险，是否继续"；同时 Agent 可 `read_file ~/.ssh/id_rsa`。

**需求**
- **P0-1-a token 级关键字匹配**：`CommandSafetyChecker.analyze` 的 `:171` 与 `:177` 改为：用 `shlex.split(command, posix=True)` 分词（失败回退 `re.split(r"\s+")`），把命令按 `|`、`&&`、`||`、`;` 切成子命令，仅当**子命令首 token**（去掉 `sudo` / `env VAR=` 前缀后）∈ 关键字集才计入：high 集 `{rm, rmdir, del, erase, rd, drop, truncate, format, mkfs, shred}`，medium 集 `{mv, cp, chmod, chown, tee, dd, sed -i（sed 且含 -i）}`；SQL 类关键字（`drop/truncate/insert/update/delete`）只在首 token 为 `sqlite3 / psql / mysql` 或命令含 `-c`/`-e` 且后续 token 命中时计入。保留现有全部正则模式不动。
- **P0-1-b 读边界**：`agent_tools` 新增 `read_allowed_dirs()` = 写允许目录 ∪ `READ_ALLOWED_DIRS`（冒号分隔）∪ 已入库文件所在目录（经 `file_metadata` 取 distinct 目录，不可用时忽略）；新增 `is_read_allowed(path)`；`read_file` / `list_directory` / `search_files` 越界时返回 `path_scope_error` 同款文案（"[错误] 路径超出允许范围: … （允许读取 …）"）。工具描述末尾加一句"仅限允许目录"，同步 `PROJECT_RULES.md` 与 `TOOL_USAGE.md`。
- **P0-1-c AUTO_CONFIRM 降权**：`react_engine.py:588,616`、`query_interface.py:1456`、`cli_handlers.py:79` 处的 `Config.AUTO_CONFIRM` 仅放行 `risk_level ∈ {low, medium}`；high 仍需确认（无交互场景下拒绝执行并返回 `[提示] 高风险命令需人工确认`）；critical 维持 registry 层拦截。抽成 `agent_tools.auto_confirm_allows(safety: dict) -> bool` 供三处复用。
- **P0-1-d 两端展示**：CLI `/config` 增加"允许读目录 / 允许写目录"两行；Web「系统」页运行环境区显示同样两项（service 暴露 `read_allowed_dirs` / `write_allowed_dirs`，`format_kv_table` 渲染）。

**验收**
- `tests/test_agent_tools*.py`：新增复现用例 `pip show models`、`ls performance/`、`git log --format=%H`、`echo delete`、`cat information.txt` → `low`；`rm -rf build` → `high`；`ls | xargs rm` → `high`；`sqlite3 a.db "DROP TABLE t"` → `high`；`mv a b` → `medium`；原有测试全部不改断言。
- `read_file("~/.ssh/id_rsa")`、`list_directory("/etc")`、`search_files("x", "/")` 在 cwd=tmp_path 下返回越界错误；`READ_ALLOWED_DIRS` 指向后放行。
- `AUTO_CONFIRM=true` 下 `risk_level=high` 命令不执行且返回提示（ReAct / CLI / cli_handlers 三处各一断言）。
- `grep -n 'in command.lower()' src/agent_tools.py` 无结果。
- CLI `/config` 与 Web 系统页显示允许目录（终端输出 + 截图）。

### P0-2 依赖钉版本 + 归档发版 + CI 矩阵

**用户场景**：新用户 `pip install -r requirements.txt` 拉到不兼容的 llama-index / gradio 新版启动失败；F8 / F9 的成果没有对应 Release。

**需求**
- **P0-2-a 钉版本**：在当前 venv 用 `pip freeze` 取实际版本，`requirements.txt` 中所有直接依赖改为 `==`（注释中的可选依赖同样写明版本）；`requirements-build.txt` 同步；新增 `requirements-dev.txt`（pytest 系、pytest-xdist、pytest-cov、flake8、pylint、bandit、pip-audit）并从 `requirements.txt` 移出，`-r requirements.txt` 引用；`scripts/install_deps.sh` / `verify_deps.sh` / `README` 安装章节 / `ci.yml` 安装步骤 / `Makefile` 同步。运行 `bash scripts/verify_deps.sh` 与 `pip-audit -r requirements.txt` 确认；新出现无修复版的 CVE 按 `ci.yml:133-147` 现有格式加 ignore 并注明理由。
- **P0-2-b CI**：`ci.yml` 增加 `pull_request` 触发（`branches: [master]`）；测试作业矩阵 `os: [ubuntu-latest, macos-latest, windows-latest]` × `python 3.13`，覆盖率与 Codecov 仅 ubuntu 上传；pip 缓存 key 含 `hashFiles('requirements*.txt')`；flake8 改为阻断但只查 `E9,F63,F7,F82`（语法 / 未定义名），其余保持 `continue-on-error`；Windows 作业中 `bash` 脚本步骤用 `shell: bash`。`pr-build-vulnerability-gate.yml` 不动。
- **P0-2-c 归档发版**：运行 `python scripts/bump_changelog.py`（参数见脚本 `--help`）将 `[Unreleased]` 归档为 `v0.1.0`（F8 / F9 属破坏性体验升级，minor 递增），日期取当日；`docs/features/ROADMAP.md` "当前版本"同步；**不打 tag、不推送 tag**，在交付输出中给出 `git tag -a v0.1.0 -m … && git push origin v0.1.0` 命令由用户执行。归档后新建空 `[Unreleased]` 并记入 P0-2 本身的"发布流程"条目。

**验收**
- `grep -cE '^[A-Za-z0-9_.-]+==' requirements.txt` ≥ 直接依赖数；`grep -E '^[A-Za-z0-9_.-]+\s*$' requirements.txt` 无裸包名。
- 新 venv `pip install -r requirements.txt -r requirements-dev.txt` 成功；`bash scripts/verify_deps.sh` 与 `pip-audit` 通过；全量测试通过。
- `ci.yml` 含 `pull_request` 与三 OS 矩阵；`act` 或语法校验（`python -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml'))"`）通过。
- `CHANGELOG.md` 出现 `## [v0.1.0] - 2026-09-XX` 且 `[Unreleased]` 仅含本次发布流程条目。

---

## 2. P1 · 主升级（中高）

### 目标
把"等一整段"变成"逐字出现"、把"必须装 Ollama"变成"可接任何 OpenAI 兼容后端"、把"改阈值靠几条问题"变成"一条命令出报表"。

### P1-1 真流式输出

**用户场景**：4B 模型输出 300 字需 15–30s，CLI 与 Web 全程只见转圈 / 心跳，用户无法判断是否卡死，也无法边看边决定是否中断。

**需求**
- **P1-1-a 引擎层**：`react_engine._call_model(messages, *, on_token=None)`：有回调时 `"stream": True`，用 `requests.post(..., stream=True)` 逐行解析 NDJSON（`message.content` 增量、`done` 结束），每个增量调 `on_token(text)`，累积后返回完整文本（下游 `_parse_response` 不变）。`ReActEngine.__init__` / `chat` 增加 `on_token` 参数并逐轮透传；工具步骤前后经现有 `on_step` 通知（不新增事件类型）。`rag_pipeline.answer_question` 最终合成调用、`llm_helper.complete_text` 增加可选 `on_token`；其余调用点保持非流式。
- **P1-1-b 配置**：`config.py` 新增 `LLM_STREAM`（默认 `true`）与 `Config.LLM_STREAM`；为 `false` 时所有 `on_token` 路径退化为一次性回调完整文本。
- **P1-1-c Web**：`StreamEvent` 增加 kind `token`；`_bridge` 中 `on_token` 把 `{"kind":"token","message":delta}` 入队；`rag_query_stream` / `agent_chat_stream` / `multi_agent_stream`（整合阶段）消费 `token` 事件逐步拼接到 Chatbot 最后一条消息；心跳仅在 ≥2s 无任何事件时发送；`answer` 事件仍在最后发出完整文本（现有测试兼容）。取消：`stop_current` 触发时关闭底层 `response`（`requests` 的 `Response.close()`），流式读取循环检查取消标志退出。
- **P1-1-d CLI**：`/ask`、`/agent`、`/auto` 的最终答案用 `rich.live.Live(Markdown(buffer), refresh_per_second=8)` 增量渲染；工具步骤保留现有面板输出（Live 上下文在工具调用期间暂停或分段）；`Ctrl+C` 中断时关闭连接并打印"已中断"。多 Agent 在 CLI 仅流式整合阶段。
- **P1-1-e 文档**：`README.md` 环境变量表加 `LLM_STREAM`；`ARCHITECTURE.md` 编排层说明加"流式回调路径"。

**验收**
- 单测：Mock `requests.post` 返回 `iter_lines()` 的 NDJSON 序列；断言 `on_token` 收到的增量拼接 == 返回文本；`LLM_STREAM=false` 时 `on_token` 只被调一次；取消标志置位后不再回调且 `response.close()` 被调用；无 `on_token` 时请求体 `stream=False` 与现在完全一致（现有测试不改断言）。
- `tests/test_web_services.py`：`agent_chat_stream` 产出 ≥2 个 `token` 事件后跟 `answer` + `done`；心跳在有 token 时不发。
- 浏览器验证：`cd src && ../venv/bin/python -c "import web.app as a; a.launch(server_port=7861)"`，三种模式各录 3 帧截图证明逐字出现；点击停止后 1s 内状态变为已取消。CLI 贴 `/ask` 终端录屏或分帧输出。
- 手测首字延迟（默认模型）前后对比写入 README.md（本目录）。

### P1-2 LLM 后端抽象层（Ollama / OpenAI 兼容）

**用户场景**：用户已有 vLLM / LM Studio / llama.cpp server / 公司内网 OpenAI 兼容网关，当前必须再装 Ollama 并拉模型。

**需求**
- **P1-2-a 抽象**：新建 `src/llm_client.py`：
  ```python
  class LLMClient(Protocol):
      def chat(self, messages, *, model=None, options=None, think=False, on_token=None) -> str
      def list_models(self) -> list[str]
      def health(self) -> bool
  ```
  `OllamaClient`（迁移 `react_engine._call_model` 的请求 / 流式 / 错误处理，含 P1-1 的 NDJSON 流）与 `OpenAICompatClient`（`POST {base}/v1/chat/completions`，SSE `data:` 行流式，`Authorization: Bearer`；`options` 映射 `temperature`、`num_predict→max_tokens`、`num_ctx` 忽略并 debug 日志一次；`think` 忽略）。工厂 `get_llm_client()` 读 `LLM_PROVIDER`（`ollama`|`openai`，默认 `ollama`）、`LLM_BASE_URL`（默认取 `OLLAMA_BASE_URL`）、`LLM_API_KEY`；进程内缓存单例，`set_llm_model` 不影响 client。
- **P1-2-b 替换调用点**：§0.4 五处直连（`react_engine`、`llm_helper`、`conversation_context`、`commit_generator`、`desktop_app` 预热）改为 `get_llm_client().chat(...)`；`commit_generator` 从 `/api/generate` 改为 chat 消息格式。`rag_engine._setup_llm` 在 `openai` 模式用 `llama_index.llms.openai_like.OpenAILike`（新依赖 `llama-index-llms-openai-like`，钉版本，写入 `requirements*.txt` 与 `cerebro.spec`）；嵌入保持 `OllamaEmbedding`。
- **P1-2-c 模型列表 / 健康**：CLI `/models`、`/status`、Web「系统」页、托盘状态轮询经 `LLMClient.list_models / health`；`openai` 模式 `list_models` 失败时回退 `[LLM_MODEL]` 并提示"后端未提供模型列表"。`bootstrap.py` 的 Ollama 安装 / 拉模型引导仅在 `LLM_PROVIDER=ollama` 时触发。
- **P1-2-d 文档**：`README.md` 新增"接入 OpenAI 兼容后端"章节（vLLM / LM Studio 示例、嵌入仍需 Ollama 的说明、`num_ctx` 由后端决定）与环境变量表三项；`ARCHITECTURE.md` 基础层加 `llm_client`；`MODULE_GUIDES.md` 加模块条目。

**验收**
- 单测：两种 client 各覆盖 普通 / 流式 / 超时 / 401 / 5xx / 非法 JSON；工厂按 env 选择并缓存；`OpenAICompatClient` 的 `options` 映射；`commit_generator` 在两种 provider 下生成成功与回退。
- 未设 `LLM_PROVIDER` 时：`grep -rn '"/api/chat"\|/api/generate' src/` 仅出现在 `llm_client.py`；现有测试全部不改断言。
- `bash scripts/verify_deps.sh` 与 `pip-audit` 通过；`packaging/cerebro.spec` 包含新依赖。
- 手测：用 `LLM_PROVIDER=openai LLM_BASE_URL=http://localhost:1234`（LM Studio 或任意兼容 mock）跑通 `/ask` 与 Web 对话，截图。

### P1-3 RAG 评测集与基准脚本

**用户场景**：开发者调 `SIMILARITY_CUTOFF` / rerank 策略 / hybrid 开关 / 分块参数，只能靠几条问题人眼看；F9-1 的 `eval_overcompliance.py` 只评忠实性不评检索。

**需求**
- **P1-3-a 语料与样本**：`tests/fixtures/rag_eval_corpus/`：≤20 个小型混合文档（md / py / txt / 一个含表格的 md；仓库自带、无隐私、总量 <200KB）；`tests/fixtures/rag_eval_cases.json`：≥30 条 `{id, question, type, expected_files, expected_keywords, notes}`，`type ∈ {single, multi_hop, code_symbol, meta, negative}`（negative 期望无来源 / 拒答）。
- **P1-3-b 打分纯函数**：新建 `src/rag_eval.py`：`recall_at_k(sources, expected_files, k)`、`mrr(sources, expected_files)`、`citation_hit_rate(answer, sources, expected_files)`（解析 `[n]` 编号映射到来源文件）、`keyword_hit(answer, expected_keywords)`、`negative_rejected(answer, sources)`（复用 F9-1 的 `HOLD_WORDS` 词表）、`aggregate(results) -> dict`（按 type 分组均值 + 总均值 + 平均延迟）、`render_markdown(agg, meta, previous=None)`（有上次报告时给 Δ 列）。
- **P1-3-c 脚本**：`scripts/eval_rag.py --hybrid on|off --rerank llm|cross-encoder|none --top-k N --tag NAME [--cases] [--limit] [--type]`：在 `tmp` 目录构建语料索引（`RAGEngine(persist_dir=tmp)`，不触碰 `index_storage/`、`.cerebro/`）；对每条用例调用 `query_with_sources` 与 `answer_question`，记录来源、答案、耗时；输出 `docs/development/rag-eval/reports/{tag}-{YYYYMMDD}.md` 与 `.json`；同 tag 存在上一份 `.json` 时在报告中给 Δ。`main` 标 `# pragma: no cover`。
- **P1-3-d 文档**：`docs/development/TEST_DESIGN.md` 新增"RAG 检索基准"章节（样本格式、如何加样本、指标含义、何时必须跑：改 `rag_engine` / `rag_rerank` / `rag_pipeline` / `code_chunker` / 检索阈值）；`docs/development/ai-assistant/TESTING_GUIDELINES.md` 加一行指引；`README.md` 开发者章节链接。

**验收**
- `tests/test_rag_eval.py` 覆盖每个指标的正常 / 边界（空来源、重复来源、多跳部分命中、编号越界、negative 有来源）与 `render_markdown` 的 Δ 列；`tests/test_eval_rag_script.py` 打桩引擎覆盖参数解析与 I/O。
- 本地实际跑 `--hybrid on` 与 `--hybrid off` 各一份报告并提交到 `docs/development/rag-eval/reports/`（作为基线）；核心指标写入本目录 README.md。
- 样本 type 分布：single ≥12、multi_hop ≥6、code_symbol ≥5、meta ≥3、negative ≥4。

---

## 3. P2 · 规模化与可维护（中）

### 目标
知识库过千文档后仍流畅、多 Agent 并行不互踩；入口层文件降到可维护规模且行为零变化。

### P2-1 BM25 持久化增量 + 锁补齐 + Ollama 并发限流

**用户场景**：千级文档库每次入库 / 删除后首次查询卡顿数秒（全量重建 BM25）；超 2 万块时混合检索静默关闭，用户不知检索质量下降；多 Agent 并行让单卡 Ollama 排队超时。

**需求**
- **P2-1-a BM25 持久化**：新建 `src/bm25_store.py`：`BM25Store(persist_dir)`：`load() / save()`（`index_storage/bm25/store.json.gz`：`{schema_version, tokenizer_version, docs: {doc_id: {tokens, metadata}}}`）、`upsert(doc_id, text, metadata)`、`remove(doc_id)` / `remove_where(pred)`、`dirty` 标志、`build() -> BM25Okapi`（惰性，首次查询或 dirty 时）。`rag_engine`：`add_documents` / 删除路径改为增量 `upsert / remove`（用 Chroma 的 id），不再置 `self._bm25 = None` 全量重建；`_ensure_bm25` 改为：store 存在且 `tokenizer_version` 匹配 → 直接 `build()`；否则全量构建一次并 `save()`（迁移旧库）；store 文件损坏 → warning + 全量重建。`_bm25_tokenize` 加 `TOKENIZER_VERSION` 常量，改分词逻辑必须递增。
- **P2-1-b 上限可观测**：超过 `RAG_HYBRID_MAX_CHUNKS` 时 `query_with_sources` 返回 `meta.hybrid_disabled_reason`；CLI `/status` 与 Web「知识库」页统计区显示"混合检索已关闭（N / 上限），可调 `RAG_HYBRID_MAX_CHUNKS`"；默认上限提升到 50000，README 环境变量表注明内存估算（约 每万块 30–50MB）。
- **P2-1-c 锁**：`agent_registry.py:18`、`task_scheduler.py:22` 改 `threading.RLock()`，读写字典 / 队列的方法加 `with self.lock`；补并发测试（16 线程同时注册 / 调度，结果计数完整、无异常）。
- **P2-1-d 并发限流**：`llm_client`（P1-2 已合入）或 `react_engine._call_model` 增加进程级 `threading.Semaphore(OLLAMA_MAX_CONCURRENCY)`（`config.py`，默认 2）；`master_agent` 子任务超时计时在**获得信号量后**开始（把等待时间从任务超时中剔除，进度事件显示"排队中"）；`README` 环境变量表加 `OLLAMA_MAX_CONCURRENCY`（`LLM_PROVIDER=openai` 时建议提高）。

**验收**
- 单测（`tmp_path` 假 collection）：增量 `upsert / remove` 后检索结果与全量重建一致；`save` → 新实例 `load` 后无需重建即可查询；`tokenizer_version` 变化触发重建；损坏文件回退；旧库（无 `bm25/`）首次查询后生成 store。
- `hybrid_disabled_reason` 在超限时非空；CLI `/status` 与 Web 知识库页显示提示（终端输出 + 截图）。
- 并发测试通过；信号量为 1 时 3 个并行子 Agent 串行完成且无超时（Mock 慢响应）。
- 手测：1000 块库 `add_documents` 后首次查询耗时前后对比写入 README.md（本目录）；若 P1-3 已合入，跑 `eval_rag.py --hybrid on` 确认指标无回归。

### P2-2 入口层拆分（纯重构，行为零变化）

**用户场景**：开发者 / AI 助手改一个 Web handler 需在 2700 行文件中定位；Web 与 CLI 逻辑漂移导致"CLI 修了 Web 没修"。

**需求**
- **P2-2-a services 拆包**：`src/web/services.py` → `src/web/services/`：`base.py`（`WebService` 骨架、状态、`_bridge`、`is_running / stop_current`、`react_factory`）、`chat.py`、`knowledge.py`、`tools.py`、`graph.py`、`system.py`（各为 mixin 类），`__init__.py` 组合 `class WebService(ChatMixin, KnowledgeMixin, ..., WebServiceBase)` 并重导出全部原公开名（`StreamEvent`、`_default_react_factory` 等）；`from web.services import WebService` 路径不变。
- **P2-2-b app 拆包**：`src/web/app.py` → `src/web/formatters.py`（全部 `format_*` 与 `_fmt_result` 等纯函数）+ `src/web/handlers/{chat,knowledge,tools,graph,system}.py`（`build_*_handlers(service)` 各返回 dict）+ `app.py`（仅 `build_handlers` 汇总、`create_app`、`launch`，≤300 行）；`app.py` 重导出旧公开名。
- **P2-2-c CLI 拆包**：`src/cli_handlers.py` → `src/cli/handlers/{knowledge,session,tools,git,db,agent,system}.py`，`src/cli/handlers/__init__.py` 汇总 `COMMAND_HANDLERS`；`src/query_interface.py` 抽出 `src/cli/parser.py`（`ParsedCommand`、`parse_command`、`classify_mode`）与 `src/cli/help_text.py`（`print_help`、`TUTORIAL_TEXT`），主文件保留主循环与渲染（≤800 行）；`src/cli_handlers.py` 与 `src/query_interface.py` 顶部保留兼容重导出。
- **P2-2-d 配套**：`pytest.ini` omit 改为 `src/web/ui/*`（路径不变）；`packaging/cerebro.spec` `hiddenimports` 补新包；`desktop_app.py` 本期不拆，仅将 Ollama 状态探测改用 `llm_client.health`（若 P1-2 已合入）。
- **P2-2-e 节奏**：每完成一个包（a / b / c）单独提交并全量测试；**禁止顺手改逻辑 / 文案 / 修 bug**，发现问题记入交付输出"待办"。

**验收**
- 现有测试**不改任何断言**（仅允许改导入路径或依赖兼容重导出）全部通过，覆盖 ≥80%。
- `wc -l`：`src/web/app.py` ≤300、`src/web/services/*.py` 与 `src/web/handlers/*.py` 单文件 ≤800、`src/query_interface.py` ≤800、`src/cli/handlers/*.py` ≤600。
- 浏览器冒烟：五页可打开、无 console error；CLI `/help` `/status` `/ask` 正常。
- `ARCHITECTURE.md` / `MODULE_GUIDES.md` / `CODE_STANDARDS.md` / `AGENTS.md` 目录职责表同步新结构。

---

## 4. P3 · 收尾（低）

### P3-1 Tesseract 跨平台探测 + README 瘦身

**需求**
- **P3-1-a Tesseract 探测**：`config.py` 新增 `resolve_tesseract_path()`：`TESSERACT_PATH` 已设且存在 → 用之；否则 `shutil.which("tesseract")`；否则按平台候选（macOS `/opt/homebrew/bin`、`/usr/local/bin`；Linux `/usr/bin`、`/usr/local/bin`；Windows `%ProgramFiles%\Tesseract-OCR\tesseract.exe`、`%LOCALAPPDATA%\Programs\Tesseract-OCR\…`）；均无 → `None`。`document_loader` / OCR 在 `None` 时返回明确提示"未检测到 Tesseract，安装方法见 docs/tutorials/02-installation.md#ocr"而非路径错误。CLI `/status` 与 Web「系统」页显示探测结果（路径或"未安装"）；`scripts/check_prereqs.sh` / `.ps1` 同步；`bootstrap.py` 启动时缺失仅提示一次（合并 F5 残留小项）。
- **P3-1-b README 瘦身**：`README.md` 压到 ≤400 行：定位与截图、快速开始（三入口各一段）、命令速查表、环境变量表、模型选择要点、文档索引；其余按主题迁入 `docs/tutorials/0X-*.md`（已有 01–07，缺的新建），**只移动不删除**，README 原位置留链接；`docs/tutorials/README.md`（无则新建）索引。

**验收**
- 单测 monkeypatch `shutil.which` / `os.path.exists` / `sys.platform` 覆盖三平台命中与未找到；OCR 缺失提示用例。
- `wc -l README.md` ≤400；脚本校验 README 与 `docs/tutorials/*.md` 内所有相对链接目标存在（在交付输出贴校验结果）；迁移前后文字总量差 <5%（仅去重与链接）。

### P3-2 `query_interface.py` 二次拆分（P2-2 遗留，纯重构 + 打桩迁移）

**用户场景**：与 P2-2 相同——改一条 CLI 命令（如 `/model`、`/exec`、`/ask` 的渲染）仍要在 1800 行文件里定位；`query_interface` 同时承担"入口脚本 / 全局状态 / 渲染 / 回调 / 命令实现 / 主循环"六种职责，AI 助手读它的成本最高。P2-2 未能做到 ≤800 的唯一障碍是 §0.10 所述 223 处对其命名空间的测试打桩：搬函数必须同步改打桩目标，超出 P2-2"只改导入路径"的许可，故单列。

**需求**（按 a → b → c 顺序，每步单独提交并全量测试；**业务逻辑 / 文案 / 输出格式零变化**）
- **P3-2-a 状态与控制台收口**：新建 `src/cli/state.py`：把 §0.10 "全局状态"段（`rag_engine` / `react_engine` / `last_rag_sources` / `last_web_sources` / `command_recommender`）、`HAS_RICH` / `HAS_READLINE` / `HAS_PROMPT_TOOLKIT` 探测、`_progress_state`、`get_console` / `console` 集中为**一个模块**（可用模块级变量保持现有 `patch("cli.state.console")` 形态，或 `class CLIState` 单例 + 同名模块级别名——二选一，选定后 CODE_STANDARDS §6 登记隔离方式）。`query_interface` 顶部 `from cli import state` 并保留 `rag_engine = state.rag_engine` 等**只读别名**供 `main` 使用；`conftest.reset_module_state` 改为重置 `cli.state`。**本步不搬任何函数**，只搬状态；随之把 223 处打桩里对 `console` / `HAS_RICH` / `rag_engine` / `react_engine` / `_progress_state` 的目标改为 `cli.state.*`（其余目标不动）。全量测试通过后提交。
- **P3-2-b 渲染 / 回调 / 编排适配外迁**：新建 `src/cli/render.py`（§0.10 "界面渲染"段 + `print_web_sources` / `_render_meta_overview` / `_render_answer` / `_live_answer` / `_print_notices` / `_citation_summary`、`show_tutorial` / `check_first_run`）、`src/cli/callbacks.py`（"回调"段：`STEP_PHASE_*`、`_live_streaming`、`on_step_callback`、`on_confirm_callback`、`ask_progress_callback`）、`src/cli/rag_adapter.py`（"共享 RAG 编排适配"段：10 个别名、`run_web_search`、`enrich_with_page_content`、`_cli_ask_progress`、`_synthesize_prompt`、`_answer_meta_query`、`_format_kb_context` 等；**顺手消除 `:891` 对 `:782` 别名的重定义（F811）**——保留函数定义、删别名行，属死代码清理不改行为）、`src/cli/recommend.py`（"命令推荐辅助"段）。函数体内对 `console` / `HAS_RICH` / `rag_engine` 的引用改为 `state.console` 等（或在模块顶部 `from .state import …` 并在函数内经 `state.` 取值——**必须运行时取值**，否则 patch 不生效）。`query_interface` 顶部重导出全部搬走的名字（`from cli.render import *` 形式 + 显式下划线名，沿用 P2-2 shim 写法）。测试：`tests/test_query_interface_render.py`、`test_query_interface_progress.py`、`test_query_interface_answer_strategy.py`、`test_cli_code_chunking.py` 的打桩目标改到对应新模块；`tests/test_query_interface_render.py` 建议整体改名为 `tests/test_cli_render.py`（`git mv`）。
- **P3-2-c 引擎耦合命令外迁**：新建 `src/cli/engine_commands.py`：§0.10 "引擎耦合命令"段全部 `handle_*` / `_run_ask` / `_ingest_inline_file` / `_answer_question` / `_route_natural_to_agent` 与 `_ENGINE_HANDLERS` 表；`_build_cli_context` 与 `dispatch_command` 一并搬入（`dispatch_command(user_input)` 保持签名）。函数签名 `handle_xxx(arg)` **不改**（改为 `(ctx, parsed)` 属行为面重构，不在本项范围；如需统一另立需求）。`query_interface` 保留：解释器自保护、日志、readline / 输入、`print_banner` / `backend_banner_text`（横幅依赖 argparse 结果，留在入口）、`main`，并重导出 `engine_commands` 全部名字。测试：`tests/test_cli_handlers_context.py`、`test_cli_handlers_model.py`、`test_query_interface_exec_safety.py`、`test_streaming_p1_1.py`、`test_llm_client.py`、`test_rag_engine_bm25_store.py` 的 `patch.object(qi, "rag_engine")` → `cli.state`、`qi.handle_*` → `cli.engine_commands.handle_*`（直接 `import query_interface as qi; qi.handle_model(...)` 的调用可保留，重导出仍指向同一函数对象）。
- **P3-2-d 配套**：`cli/__init__.py` 文档补新模块；`packaging/cerebro.spec` 无需改（子包递归收集）；`pytest.ini` 无需改；`docs/development/TEST_DESIGN.md:22` 的 `query_interface.py | 719` 行数与覆盖率目标行改为新结构；`ARCHITECTURE.md §1.1` 入口层表、`MODULE_GUIDES.md` 入口层节、`CODE_STANDARDS.md §6` 单例表（`react_engine / rag_engine` 模块全局 → `cli.state`）、`TESTING_GUIDELINES.md:43,77`（`reset_module_state` 与 `patch("query_interface.console")` 指引）同步。

**验收**
- 现有测试**不改任何断言**；允许且仅允许改：导入路径、`patch` / `monkeypatch.setattr` / `inspect.getsource` 的目标模块、测试文件重命名（`git mv`）。`./venv/bin/python -m pytest -q -n 4` 通过，覆盖 ≥80%，测试收集数与 P2-2 后相同（3528 passed / 36 skipped）。
- `wc -l src/query_interface.py` **≤800**；`src/cli/*.py` 单文件 ≤700（`engine_commands.py` 预计约 650）。
- `grep -rn 'patch("query_interface\.' tests/ | wc -l` 与 `patch.object(qi, "` 合计 ≤10（仅剩打 `main` / `print_banner` / `setup_logging` 等确实留在入口的名字）。
- `flake8 --select=E9,F63,F7,F82,F811 src/query_interface.py src/cli/` 无输出（`_synthesize_prompt` F811 消除；P2-2 记录的其余 8 条 F401 若属搬走的段随之自然消失，属入口的 `Syntax` / `Prompt` / `build_knowledge_base` 等可在本项一并删除——**仅删未使用的导入行**，不改逻辑）。
- CLI 冒烟：`/help` `/stats` `/config` `/model` `/ask` `/agent`（一条只读任务）终端输出与 P2-2 后逐行一致（用同一 `printf … | python query_interface.py --no-history` 脚本对照 P2-2 提交 `01f3a20` 的 worktree）；`python src/query_interface.py --query "…"` 与 `--agent "…"` 单次模式正常。
- `ARCHITECTURE.md` / `MODULE_GUIDES.md` / `CODE_STANDARDS.md` / `TESTING_GUIDELINES.md` / `AGENTS.md` 目录职责表同步。

**风险与说明**
- 打桩迁移是本项最大工作量（约 200 处、9 个文件），机械但必须逐处核对目标：搬到哪个模块就打那个模块。建议先做 a（只搬状态）把 `console / HAS_RICH / rag_engine / react_engine` 四类 180 处一次收口，b / c 只剩函数级目标。
- `state` 用模块级变量最省事，但 `from cli.state import console` 形式会在导入时固化对象、令 patch 失效——新模块内一律 `from cli import state` 后 `state.console`，或函数内取值。
- `main` 227 行含 argparse + 引导 + REPL，本项不拆（留在入口正当）；若 P3-2-c 后 `query_interface` 仍 >800，可再把 `main` 内的 REPL 循环抽成 `cli/repl.py::run_loop(args)`，但优先级低于上述三步。

---

## 5. 两端规范（全 P 级共用）

| 项 | 约定 |
|---|---|
| 共享层优先 | 安全判定、路径边界、LLM 客户端、BM25、评测打分均放共享层；Web / CLI 只做呈现 |
| CLI 呈现 | 状态类信息一行 `key: value`；错误 `style="red"`、提示 `style="yellow"`、空态 `style="dim"`；流式答案用 `rich.live.Live` + `Markdown`；改行为必须同步 `print_help` / `TUTORIAL_TEXT` |
| Web 呈现 | 状态类信息用 `format_kv_table`；长任务必经 `_bridge`；新增事件 kind 要在 `StreamEvent` 文档注释中列出；不出现工具注册名 |
| 环境变量 | 新增项：`config.py` 常量 + `Config` dataclass + README 环境变量表 + Web「系统」页只读展示（若与用户相关） |
| 提示文案 | 中文、先结论后说明、给出下一步（如"可设置 READ_ALLOWED_DIRS 放行"） |
| 失败可见 | 静默降级一律改为可见提示（hybrid 关闭、后端无模型列表、Tesseract 缺失） |

---

## 6. 实施顺序与交付

```
P0-1 安全分级 → P0-2 钉版本 + 发版 + CI
P1-1 真流式 → P1-3 RAG 评测（先建基线）→ P1-2 后端抽象（依赖 P1-1 的流式接口）
P2-1 BM25 + 锁 + 限流（用 P1-3 基线验证无回归）→ P2-2 入口层拆分（最后做，避免与前序改动冲突）
P3-1 Tesseract + README → P3-2 query_interface 二次拆分（依赖 P2-2 已合入；与 P3-1 无交集可并行）
```

每个编号项独立可提交、可发 PR；P1-2 依赖 P1-1，P2-2 建议在 P1 全部合入后进行，P3-2 依赖 P2-2。
交付物：改动文件清单、新增测试数、覆盖率、验收项逐条结果、涉及 Web 的截图、涉及 CLI 的终端输出、性能类改动的前后对比、未完成 / 风险。
