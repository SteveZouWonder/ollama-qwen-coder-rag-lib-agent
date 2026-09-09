# F10: 工程加固与体验升级（安全 · 发布 · 流式 · 后端抽象 · 评测 · 规模化 · 拆分）

## 实施状态

**进行中**（P0-1 / P0-2 / P1-1 已完成 2026-09-09；其余五项待实现） · 立项 2026-09-08 · 分支 `docs/f10-hardening`
· 目标：针对项目评估发现的 7 类结构性问题，按"用户可感知价值 × 复杂度"分 P0–P3 八个独立任务逐项落地

| 编号 | 主题 | 价值 | 复杂度 | 依赖 | 状态 | 完成日期 | 提交 |
|---|---|---|---|---|---|---|---|
| P0-1 | 命令安全分级修正（token 级匹配）· 读路径边界 · `AUTO_CONFIRM` 不放行 high · 两端显示允许目录 | 高 | 低 | — | **已完成** | 2026-09-09 | 见下方实现记录 |
| P0-2 | 依赖钉版本 + `requirements-dev.txt` · CI PR 触发 + 三平台矩阵 · CHANGELOG 归档 v0.1.0 | 高 | 低 | — | **已完成** | 2026-09-09 | 见下方实现记录 |
| P1-1 | 真流式输出（Ollama NDJSON → Web token 事件 / CLI rich Live）· `LLM_STREAM` 开关 · 可中断 | 高 | 中 | — | **已完成** | 2026-09-09 | 见下方实现记录 |
| P1-3 | RAG 评测集（≥30 例 + 小语料）· `src/rag_eval.py` 指标 · `scripts/eval_rag.py` 报表与 Δ | 中 | 中 | — | 待实现 | | |
| P1-2 | `src/llm_client.py` 后端抽象（Ollama / OpenAI 兼容）· 五处直连替换 · 模型列表 / 健康检查 | 中 | 中高 | P1-1 | 待实现 | | |
| P2-1 | BM25 持久化增量（`bm25_store`）· 混合检索关闭可见 · RLock 补齐 · Ollama 并发信号量 | 中 | 中高 | P1-2 / P1-3（可选） | 待实现 | | |
| P2-2 | 入口层拆分：`web/services/`、`web/handlers/` + `formatters.py`、`cli/handlers/` + `cli/parser.py`（纯重构） | 低（间接） | 高 | P1 全部合入 | 待实现 | | |
| P3-1 | Tesseract 跨平台探测与缺失提示 · README 瘦身到 ≤400 行 | 低 | 低 | — | 待实现 | | |

## 文档导读

| 文件 | 内容 | 适合 |
|---|---|---|
| [REQUIREMENTS.md](REQUIREMENTS.md) | 需求分项与验收标准；§0 为立项时核实的代码事实（带 `文件:行号`，按问题分 8 小节）；§5 两端规范；§6 实施顺序 | 了解"要做什么、为什么" |
| 本文件 | 实现记录（每项做了什么、落在哪个模块）、与需求的差异、验证结果、性能前后对比 | 了解"实际做成了什么" |
| [PROMPT.md](PROMPT.md) | 交给 Agent 的启动提示词，按八个任务分段、各自可独立粘贴 | 分批派发实现任务 |

用户可感知的变更同步记录在 [CHANGELOG.md](../../../CHANGELOG.md) `[Unreleased]` 与主 [README](../../../README.md) 对应段落。

## 立项背景

2026-09-08 对项目做整体评估（架构 / 代码规模 / 工程质量 / 依赖 / 安全 / 可扩展性），归纳出 7 类问题：

| # | 问题 | 用户可感知影响 | 对应任务 |
|---|---|---|---|
| 1 | 入口层 5 个文件 1400–2700 行，Web / CLI 双份呈现层 | 改一端漏一端；定位成本高 | P2-2 |
| 2 | 只支持 Ollama `/api/chat`；全部调用非流式，Web 为线程 + 心跳伪流式 | 长回答全程只见"思考中"；无法接入 vLLM / LM Studio / 内网网关 | P1-1、P1-2 |
| 3 | 命令安全靠子串黑名单（`"rm" in cmd`）；读操作无路径边界；`AUTO_CONFIRM` 可绕过 high | `pip show models` 被判高风险弹确认；可读工作区外任意文件 | P0-1 |
| 4 | BM25 每次全量拉取重建；`lock = None`；多 Agent 并行打爆单卡 Ollama | 大库入库卡顿、>2 万块静默降级、并行超时 | P2-1 |
| 5 | 依赖几乎未钉版本；104 条变更未发版；CI 单平台、仅 push master | 新用户安装失败；两个月成果无安装包 | P0-2 |
| 6 | 无 RAG 评测集；ReAct / rerank / 分解全靠 4B 模型结构化输出 | 改阈值后质量回归不可见 | P1-3 |
| 7 | Tesseract 路径 macOS 硬编码；README 1322 行 | Linux / Windows OCR 路径错误；新用户找不到入口 | P3-1 |

排序原则：两端共有的功能性缺陷（3、5）> 影响主路径的体验（2、6）> 规模化与可维护（4、1）> 收尾（7）。详细事实与行号见 [REQUIREMENTS.md §0](REQUIREMENTS.md#0-背景已核实的代码事实实施时勿重复调研)。

## 实施顺序

```
P0-1 安全分级 → P0-2 钉版本 + 发版 + CI
P1-1 真流式 → P1-3 RAG 评测（先建基线）→ P1-2 后端抽象
P2-1 BM25 + 锁 + 限流 → P2-2 入口层拆分
P3-1 Tesseract + README
```

## 实现记录

### P0-1 命令安全分级修正 + 读路径边界（2026-09-09）

| 子项 | 实现位置 | 做了什么 |
|---|---|---|
| P0-1-a token 级匹配 | `src/agent_tools.py` `CommandSafetyChecker` | 新增分词与判定纯函数：`_tokenize`（`shlex.shlex(posix=True, punctuation_chars=True)`，`ValueError` 回退 `re.split(r"\s+")`）、`_split_subcommands`（按 `|` `||` `&&` `;` `&` 切分）、`_head`（剥 `TRANSPARENT_PREFIXES` = sudo/doas/env/xargs/nohup/time/command/builtin/exec/nice/ionice 及其带值选项 `PREFIX_FLAGS_WITH_VALUE`、跳过 `VAR=value`、取 basename 转小写）、`_sql_risk`、`_subcommand_risk`（含 `-c`/`-e` 载荷递归，深度 ≤2）、`keyword_risk`、`is_readonly_command`。关键字集合：`HIGH_COMMANDS`（rm rmdir del erase rd drop truncate format mkfs shred）、`MEDIUM_COMMANDS`（mv cp chmod chown tee dd）、`MEDIUM_COMMANDS_WITH_FLAG`（`sed` + `-i`）、`SQL_CLIENTS` / `SQL_HIGH_KEYWORDS` / `SQL_MEDIUM_KEYWORDS`。`analyze` 中两处 `kw in command.lower()` 替换为 `keyword_risk()`；只读判定改为「全部子命令都命中 `READONLY_PATTERNS`」。`DANGEROUS_PATTERNS` / `HIGH_PATTERNS` / `MEDIUM_PATTERNS` / `READONLY_PATTERNS` 一字未改。 |
| P0-1-b 读边界 | `src/agent_tools.py`、`src/config.py` | 新增 `READ_ALLOWED_DIRS_ENV`、`read_allowed_dirs()`（写允许目录 ∪ `READ_ALLOWED_DIRS` ∪ `_indexed_document_dirs()`）、`is_read_allowed()`、`read_scope_error()`；抽出 `_normalize_dirs()` / `_within()` 供读写共用（`is_path_allowed` 改为复用）。`read_file` / `list_directory` / `search_files` 在 `expanduser` 后立刻校验。`config.py` 新增 `READ_ALLOWED_DIRS` 常量与 `Config.READ_ALLOWED_DIRS`。三个工具描述末尾加「（仅限允许目录）」。 |
| P0-1-c AUTO_CONFIRM 降权 | `src/agent_tools.py`、`src/react_engine.py`、`src/query_interface.py`、`src/cli_handlers.py`、`src/agents/base_agent.py` | 共享层新增 `AUTO_CONFIRM_RISK_LEVELS = ("low","medium")`、`HIGH_RISK_CONFIRM_HINT`、`auto_confirm_allows(safety)`（`safety` 为空 → True，`is_dangerous` → False）。`react_engine` 确认分支与 `registry.execute` 的 `auto_confirm` 均经该闸门；`query_interface.handle_exec` 同理并在 AUTO_CONFIRM 下打印提示；`cli_handlers._confirm` 增加 `safety=` 形参（默认 None，行为不变），`handle_db_execute` 经新增的 `_sql_safety(sql)` 传入；`base_agent.AUTO_CONFIRM_RISK_LEVELS` 改为引用共享常量，消除两处漂移。 |
| P0-1-d 两端展示 | `src/cli_handlers.py`、`src/query_interface.py`、`src/web/services.py`、`src/web/app.py` | 新增 CLI `/config`：`config_rows()`（纯函数，返回 `(标签, 值)` 列表）+ `handle_config`，注册进 `COMMAND_HANDLERS["config"]`、`parse_command` 与 `classify_mode`；同步 `print_help` 与 `TUTORIAL_TEXT`。Web：`WebService.env_info()` 增加 `read_allowed_dirs` / `write_allowed_dirs`，`format_env_info` 增加「允许读目录 / 允许写目录」两行（新增 `_fmt_dir_list`，超 6 个折叠），自动确认一行改为「开（只放行 low / medium）」。 |
| P0-1 后续（同日第二次提交）| `src/agent_tools.py`、`src/web/services.py`、`src/web/app.py`、`.flake8` | **读边界补全两端**：`analyze_project_structure` / `ast_search` / `code_quality_check` / `git_analyze` / `git_commit_gen` 接 `is_read_allowed`；Web 新增 `WebService.path_read_error(path)` 复用同一判定，约束 `list_dir` / `file_preview` / `search_in_dir` / `code_symbols` / `code_quality_report` / `graph_build_file` / `code_assist_stream`；`app.on_dir_search` 越界先报错（`search_in_dir` 无 error 槽位，否则会伪装成"未找到"），`on_file_edit_load` 越界不再提示"保存将创建新文件"。**允许目录收敛**：`_normalize_dirs` 丢弃被包含的子目录；`_indexed_document_dirs` 把 Gradio 上传根（`$GRADIO_TEMP_DIR` / `<tmp>/gradio`）下的哈希目录折叠为根一条。**守卫测试**：真实 registry 下 high 命令确认一次即执行一次（不再二次 `[CONFIRM_REQUIRED]`）。**flake8**：`.flake8` 的 `ignore` 行内注释导致 flake8 根本跑不起来（`ValueError`），移到独立行；顺手删掉 5 处只读的死 `global` 声明（F824），为 P0-2-b 的阻断门禁留出干净基线。 |

### P1-1 真流式输出（2026-09-09）

| 子项 | 实现位置 | 做了什么 |
|---|---|---|
| P1-1-a 引擎层 | `src/react_engine.py` | `_call_model(messages, num_predict, think, on_token=None)`：`on_token` 为空时请求体 `stream: False`、调用形态与旧版完全一致；非空且 `Config.LLM_STREAM` 时 `requests.post(..., stream=True)` → `_consume_stream`（委托共享层 `consume_ndjson_stream`，`should_stop=_stop_event.is_set`），读取期间把响应挂在 `_active_response`；`LLM_STREAM=false` 时非流式并把完整文本一次性回调。`ReActEngine.__init__(on_token=)` / `chat(task, on_token=None)`（`chat` 参数优先）；每轮经 `_call_model_streaming()` 包一层新增的 **`FinalAnswerStream`**：缓冲到看见 `Final Answer:` 才转发其后增量（首段 `lstrip`），缓冲区出现 `Action:` 则丢弃本轮——用户不会看到 `Thought / Action` 协议文本闪现。`_forced_summary` 同样经该包装。`stop()` 置位后调用 `llm_helper.abort_response(_active_response)`。`chat` 在 `_call_model` 返回后再查一次 `_stop_event`，被中断的半截文本不进 `_parse_response`。协议与 `_parse_response` 一字未改。 |
| P1-1-a 共享层 | `src/collaboration/llm_helper.py` | `complete_text(..., on_token=None, should_stop=None)` 同一套开关语义；新增 `consume_ndjson_stream(resp, on_token, should_stop)`（空行 / 非 JSON 行忽略，`{"error"}` 抛 `RuntimeError`，`done` 结束，`should_stop` 为真即停止回调并关闭响应，响应总会被关闭）与 `abort_response(resp)`（先 `resp.raw._fp.fp.raw._sock.shutdown(SHUT_RDWR)` 再 `close()`；只 `close()` 在 macOS 上不会唤醒阻塞在 `recv` 的读线程）。 |
| P1-1-a RAG 综合 | `src/rag_pipeline.py` | 新类型 `TokenCallback`；`answer_question(..., on_token=None)` → `_answer_question_planned` → `generate_answer(..., on_token=None)` → `_generate_answer_inner` 内四处最终综合调用统一走局部 `synthesize(prompt)`：无 `on_token` 时仍是 `llm_direct_answer(prompt)` 单参调用（现有 `lambda p:` 桩全部兼容），有则 `llm_direct_answer(prompt, on_token, should_stop)` → `_complete(prompt, on_token, should_stop)` → 新增 `_stream_complete`：`Settings.llm.stream_chat([ChatMessage(user)])` 逐 `delta` 回调，`should_stop` 为真 `break` 并 `gen.close()`，末块经现有 `_emit_thinking` 透出思维链；LLM 无 `stream_chat` 时回退一次性补全 + 单次回调。规划 / rerank / 自校验等工具性调用不流式。 |
| P1-1-a 多 Agent 整合 | `src/collaboration/result_integrator.py`、`src/master_agent.py`、`src/agent_orchestrator.py` | `ResultIntegrator.on_token` 属性（未注入 `complete` 时 `_synthesize_answer` 用 `complete_text(prompt, on_token=...)`）；`MasterAgent.coordinate_task(..., on_token=None)` 进入时注入、`finally` 复位；`AgentOrchestrator.process_request(..., on_token=None)` 仅在非空时透传（`kwargs` 形态与 `progress` / `context` 一致）。子任务执行不流式。 |
| P1-1-b 配置 | `src/config.py` | `LLM_STREAM = env LLM_STREAM（默认 true，1/true/yes/on）` 与 `Config.LLM_STREAM`。 |
| P1-1-c Web 服务层 | `src/web/services.py` | `StreamEvent` 文档注释补 `token` / `confirm`；新增 `WebService._token_sink(q, cancel)`（取消后丢弃增量）；`rag_query_stream` 把它传给 `answer_question(on_token=)`，`agent_chat_stream` 传给 `engine.chat(user_input, on_token=)`，`multi_agent_stream` 经 `_run_orchestrator(..., on_token=)` 透传；`chat_auto_stream` 原样转发子流的 `token`。`_bridge` 逻辑不变（`queue.get(timeout=heartbeat_interval)` 天然做到"只在无任何事件时发心跳"），文档注释明确。`stop_current` → `engine.stop()` 现在会关闭流式连接。 |
| P1-1-c Web 呈现层 | `src/web/app.py` | `on_chat_stream` 新增 `partial` 缓冲：`token` 事件逐段拼接为"正在生成"的助手气泡并把状态行设为「✍️ 生成回答中…」；`answer` 到达后以完整文本（含 notices / 引用校验后处理）替换；新增 `_starts_new_round(kind, data)`——非心跳的 `thinking` step 到来时清空 `partial`（极少数"先写 Final Answer 又写 Action"的轮次）；生成期间 transient 心跳不再覆盖状态文案；`cancelled` 时保留已流出的部分回答并追加「> ⏹️ 已停止，以上为中断前的部分回答」。 |
| P1-1-d CLI | `src/cli_handlers.py`、`src/query_interface.py` | 新增 **`LiveAnswer`**（`rich.live.Live(Panel(Markdown(buffer)), refresh_per_second=8, transient=True)`，首个 token 才启动，`finish()` 停止并清除实时区域；类级 `LiveAnswer.streaming()` 标志；非 Rich 终端为空操作）。`_run_ask`（`/ask` 与自然语言）传 `on_token=live.on_token`，`KeyboardInterrupt` → `live.finish()` + 打印「已中断，已关闭与模型的连接。」；`handle_agent` 以 `engine.on_token = live.on_token` 方式注入（结束后恢复，`engine.chat(task)` 调用形态不变），`Ctrl+C` → `engine.stop()`（关闭连接）+「已中断：…」；单次 `--agent` 同理；`handle_multi` 传 `on_token`（仅整合阶段有 token）。`on_step_callback` 在 `LiveAnswer.streaming()` 时静默 transient 推理心跳（否则 `\r` 单行刷新会在面板上方反复刷出）。Live 面板为 transient：完成后仍按既有格式打印完整答案 + 来源 + notices，最终输出与非流式完全一致。`print_help`（`/ask` `/agent` 行）与 `TUTORIAL_TEXT`（新增"流式输出"示例段）同步。 |
| P1-1-e 文档 | `README.md`、`CHANGELOG.md`、`docs/development/ai-assistant/ARCHITECTURE.md` §2.6、`MODULE_GUIDES.md` | 环境变量表加 `LLM_STREAM`（配置块 + export 示例）；CHANGELOG `[Unreleased]` 新增「真流式输出」、改进「回答可中断」；ARCHITECTURE 新增 §2.6「流式回调路径」；MODULE_GUIDES 更新 `ReActEngine` 签名、`llm_helper` 新函数、`StreamEvent` kinds。 |

### P0-2 依赖钉版本 + 归档发版 + CI 矩阵（2026-09-09）

| 子项 | 实现位置 | 做了什么 |
|---|---|---|
| P0-2-a 钉版本 | `requirements.txt`、`requirements-build.txt`、**新增** `requirements-dev.txt` | 以当前 venv 的 `pip freeze` 为准，把 `requirements.txt` 的 28 个直接依赖全部改为 `==`（原先仅 2 处 `==`、4 处下限约束、其余裸包名）；可选依赖（sentence-transformers / tree-sitter-language-pack / OCR）在注释的安装命令里同样写明版本。`requirements-build.txt` 逐项对齐同一批版本（另含 `tree-sitter-language-pack==1.16.2`、`pyinstaller==6.21.0`、`pefile==2024.8.26; sys_platform == "win32"`）。测试 / lint 依赖移入 `requirements-dev.txt`（`-r requirements.txt` + pytest 9.0.3 / pytest-cov 7.1.0 / pytest-xdist 3.8.0 / flake8 7.3.0 / pylint 4.0.5 / bandit 1.9.4 / pip-audit 2.10.1）。 |
| P0-2-a 安全兜底 | 同上 | 直接冻结本地版本会把 51 条**已有修复版**的漏洞钉进仓库（此前依赖不钉版本，CI 每次装最新反而没有）。因此先把 `setuptools 82.0.1 → 84.0.0`、`gitpython 3.1.50 → 3.1.62`、`pillow 12.2.0 → 12.3.0` 升级后再冻结；`pypdf` 本地为 6.13.3、低于原约束 `>=6.15`（Dependabot 升过但本地没装），一并升到 6.18.0 再钉。 |
| P0-2-a 脚本同步 | `scripts/verify_deps.sh`、`scripts/install_deps.sh`、`scripts/install_deps.ps1`、`Makefile`、`README.md` | `verify_deps.sh`：抽出 `verify_requirements_file()`，跳过 `-r` 引用行，分「运行时」「开发/测试」两段校验（原来测试工具是硬编码三行）。`install_deps.sh` / `.ps1`：numpy/pandas 预装改为从 `requirements.txt` 读钉版本（原来裸装再被覆盖）；OCR 依赖改用 `pytesseract==0.3.13 opencv-python==4.13.0.92`（顺带修掉 `.ps1` 里 `pymupdf>=1.25.0` 中 `>` 被 PowerShell 当重定向符的 bug）；新增「是否安装开发/测试依赖」一步。`Makefile` 拆出 `install` / `install-dev` / `test`，`build` 依赖 `install`（`pr-build-vulnerability-gate.yml` 的 `make build` 行为不变）。README「2. 安装依赖」加三份依赖清单的分工表与升级流程说明，项目结构树补两个新文件。 |
| P0-2-b CI | `.github/workflows/ci.yml` | 加 `pull_request: branches: [master]` 触发；`build-and-test` 改 `runs-on: ${{ matrix.os }}`，矩阵 `os: [ubuntu-latest, macos-latest, windows-latest] × python 3.13`，`fail-fast: false`；安装步骤改为一条 `pip install -r requirements-dev.txt`（原来手写 `pip install flake8 pylint bandit pip-audit pytest pytest-cov`，版本随缘）；pip 缓存先用 `python -m pip cache dir` 解析平台缓存目录再 `actions/cache`，key 改 `hashFiles('requirements*.txt')`；flake8 拆成两步——`E9,F63,F7,F82` **阻断**、风格检查 `continue-on-error`；测试拆成 ubuntu（带覆盖率 + `coverage report --fail-under=80` + Codecov + artifact）与非 ubuntu（`-q --no-cov`）两步；pip-audit / 覆盖率 / artifact 上传均加 `matrix.os == 'ubuntu-latest'` 条件（避免 artifact 重名冲突）；所有 shell 步骤加 `shell: bash`。`security-scan` 作业与 CVE ignore 列表**一字未改**；`release.yml`、`pr-build-vulnerability-gate.yml` 未动。 |
| P0-2-c 归档 | `CHANGELOG.md`、`docs/features/ROADMAP.md` | `python scripts/bump_changelog.py bump --version 0.1.0 --date 2026-09-09` 把 `[Unreleased]` 的 **112 条**一级要点归档为 `## [v0.1.0] - 2026-09-09`（F8 / F9 为破坏性体验升级，按 minor 递增）；新 `[Unreleased]` 只写 P0-2 自身的「发布流程」4 条。ROADMAP「当前版本」由 v0.0.13 改为 v0.1.0。**未打 tag、未推送**，命令交由用户执行。 |

## 验证结果

### P1-1（2026-09-09）

| 项 | 结果 |
|---|---|
| 全量测试 | `./venv/bin/python -m pytest -q -n 4` → **3287 passed, 36 skipped**，覆盖率 **91.42%**（门禁 80%） |
| 新增测试 | **+63 个**（新文件 `tests/test_streaming_p1_1.py`）：`_call_model` 流式 / 非流式请求体一致 / `LLM_STREAM=false` 单次回调 / 取消后不再回调且 `close()` 被调 / 跨线程 `stop()` 关闭响应 / 流中 error / 读错误 / 垃圾行；`FinalAnswerStream` 四例；`chat` 透传（仅 Final Answer、工具轮不产生 token、构造参数回退、无回调时 `_call_model` 无 kwargs、中断返回、强制总结）；`complete_text` / `consume_ndjson_stream` / `abort_response`；`rag_pipeline._complete` 经 `stream_chat` / 停止 / 思维链 / 无 `stream_chat` 回退 / `answer_question` 透传与单参兼容；`ResultIntegrator` / `MasterAgent` 注入复位 / `AgentOrchestrator` 透传；Web 服务层五种流的 `token` 事件（≥2 token → answer，取消后丢弃，无心跳）；Web 呈现层增量拼接 / 新轮清空 / 心跳不覆盖 / 取消保留部分回答；CLI `LiveAnswer` 四例 + `_run_ask` / `handle_agent` / `on_step_callback` / `handle_multi` 接线 + 帮助文案 |
| 现有测试断言 | **一条未改**。改动的只有测试替身的签名：`tests/conftest.py` 的综合桩 `_fake(prompt, on_token=None, should_stop=None)`（有回调时按 `LLM_STREAM=false` 语义一次性回调）、`tests/test_web_services.py` 的 `FakeReact.chat(user_input, on_token=None)`（2 处）与 3 个假编排器 `process_request(..., on_token=None)`、`tests/test_cli_handlers_multi.py` 的 `_Orch.process_request(..., on_token=None)` |
| flake8 语法门禁 | `flake8 --select=E9,F63,F7,F82 src tests` → rc=0 |
| 无 `on_token` 时请求体 | `test_no_on_token_request_unchanged`：`json["stream"] is False` 且 `requests.post` 不带 `stream=` 关键字；`test_no_on_token_calls_call_model_without_kwargs`：`chat()` 无回调时 `_call_model()` 零 kwargs |
| 首字延迟（`qwen3.5:4b`，同一 200 字提示，预热后） | **非流式：首字可见 6.57s（= 全文到达）** → **流式：首字 0.17s，全文 6.87s**（146 个增量）。命令：`complete_text(prompt)` vs `complete_text(prompt, on_token=…)` 计时 |
| 停止的实际效果（真实 Ollama） | 流式开始 6s 后 `engine.stop()`：`_call_model` **0.000s** 内返回（已收 148 个增量），紧接着的短请求 0.25s 返回（模型已停止生成，未排队）。流式尚未开始（仍在 `requests.post` 等响应头，即模型在处理 prompt）时 `stop()`：需等响应头到达（本机约 3.4s）才退出——此阶段没有可关闭的 response |
| 浏览器（`a.launch(server_port=7861)` + Playwright 无头 Chromium） | 三种模式各 3 帧 + 停止 2 帧见下 |
| CLI | `/ask` 与 `/agent` 在伪终端中的分帧输出见下 |

浏览器三种模式逐字出现（同一提问的连续 3 帧，气泡字数递增；截图裁到对话列）：

| 模式 | 帧 1 | 帧 2 | 帧 3 |
|---|---|---|---|
| RAG 检索（首 token 距发送 49.2s：前面是改写 / 规划 / 联网 / 检索 / rerank）| ![](assets/rag-frame1.png) 7 字 | ![](assets/rag-frame2.png) 28 字 | ![](assets/rag-frame3.png) 41 字 |
| 单 Agent（首 token 63.8s：4B 模型先写 Thought，再流出 Final Answer）| ![](assets/agent-frame1.png) 5 字 | ![](assets/agent-frame2.png) 18 字 | ![](assets/agent-frame3.png) 45 字 |
| 多 Agent 协作（整合阶段，两个子任务执行完 ~3.5 分钟后开始流出）| ![](assets/multi-frame1.png) | ![](assets/multi-frame2.png) 196 字 | ![](assets/multi-frame3.png) 212 字 |

> 多 Agent 帧 1 抓到的是上一条历史消息（脚本按气泡计数切帧的误差），帧 2 / 3 为整合阶段真实增长。

停止：单 Agent 流出 33 字时点「停止」，**0.23s** 后状态行变为「⏹️ 已发送停止信号，正在中止…」、「发送」按钮恢复可用；气泡保留中断前文本。

| 停止前（流式中） | 停止后 |
|---|---|
| ![](assets/stop-frame3.png) | ![](assets/stop-cancelled.png) |

CLI `/ask`（伪终端 100×40，`script` 录制后按 rich Live 的光标上移序列切帧；共 46 次实时刷新，首帧距发命令 25.6s）：

```
--- 流式帧 1 @ 距发命令 25.60s ---
╭──────────────────────────────────────────────────────────────────────────────────────────────────╮
│ 知识库中未明确定义"主要                                                                          │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
--- 流式帧 2 @ 28.57s ---
╭──────────────────────────────────────────────────────────────────────────────────────────────────╮
│ 知识库中未明确定义"主要主题"这一概念，仅提供了具体文档主题（如 HTTP/3 影响、Cloudflare           │
│ 内网穿透）及外部知识分类原则。根据资料                                                           │
│ [15][W5]，企业知识库通常按人力资源、市场营销、技术研发等大领域划分；而本地文档 [1][2][4]         │
│ 实际涉及的技术主题包括**HTTP/3 与                                                                │
--- 流式帧 3 @ 31.20s ---
│ 内网穿透（需迁移 DNS 记录并创建隧道）以及知识图谱的构建与应用（基于实体 -                        │
│ 关系三元组结构）。这些内容共同构成了当前资料库的核心技术主题。                                   │
│                                                                                                  │
│ 主要依据来自知识库                                                                               │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
（随后照常打印 🤖 回答 面板、📚 基于知识库 N 个片段、🌐 网络来源表、/sources 提示）
```

CLI `/agent` + `Ctrl+C`（Live 面板刷新 1.5s 后发送 `\x03`）：

```
Ctrl+C 发送于 37.66s（首个流式刷新 36.12s）
已中断：用户中断，任务已停止，已关闭与模型的连接。        ← 与 Ctrl+C 同一采样帧内出现（<0.15s）
❯                                                          ← 回到提示符
```

### P0-2（2026-09-09）

| 项 | 结果 |
|---|---|
| 钉版本完整性 | `grep -cE '^[A-Za-z0-9_.-]+==' requirements.txt` → **28**；`grep -E '^[A-Za-z0-9_.-]+\s*$'` 无裸包名；非注释行全部含 `==` |
| `bash scripts/verify_deps.sh` | 运行时 23 项全 ✓（llama-index 插件包 / gitpython / opencv 按规则跳过），开发/测试 7 项全 ✓ |
| `pip-audit -r requirements.txt` | 升级三个包前 **51 条 / 5 包**；升级后 **5 条 / 2 包**（chromadb 4 条 + nltk 1 条），全部无修复版且已在 `ci.yml` ignore 列表中附理由。按 CI 原样带 ignore 参数运行 → `No known vulnerabilities found, 5 ignored`。**未新增任何 ignore** |
| `ci.yml` 语法 | `python -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml'))"` 通过；解析出 `on = {push: master, pull_request: master}`、`matrix.os = [ubuntu, macos, windows]` |
| 全量测试 | `./venv/bin/python -m pytest -q -n 4` → **3224 passed, 36 skipped**，覆盖率 **91.26%**（门禁 80%） |
| 归档 | `CHANGELOG.md` 出现 `## [v0.1.0] - 2026-09-09`，含 112 条一级要点；新 `[Unreleased]` 仅「发布流程」4 条 |

依赖版本差异（旧约束 → 新钉版本，仅列有变化的直接依赖）：

| 包 | 旧约束 | 新版本 | 备注 |
|---|---|---|---|
| setuptools | `>=60.0.0` | `==84.0.0` | 从 82.0.1 升级，修 PYSEC-2026-3447 |
| gitpython | `>=3.1.0` | `==3.1.62` | 从 3.1.50 升级，修 26 条 CVE/GHSA |
| pillow | 裸包名 | `==12.3.0` | 从 12.2.0 升级，修 19 条 PYSEC |
| pypdf | `>=6.15.0,<7` | `==6.18.0` | 本地实为 6.13.3（低于原约束），升级后钉版 |
| 其余 24 个直接依赖 | 裸包名 / 下限约束 | 冻结当前实测版本 | 见 `requirements.txt` |

> 未在干净 venv 里跑 `pip install -r requirements.txt -r requirements-dev.txt` 复装验证（约 2 GB 下载）；
> 已通过 `pip-audit -r requirements.txt` 的依赖解析间接确认全部钉版本可解，且 CI 三平台会在 PR 上做真实复装。

`git tag` 与推送命令（**待用户执行**）：

```bash
git tag -a v0.1.0 -m "v0.1.0: F8 Agent 模式优化 + F9 Web 工具页改版 + F10 P0 安全与依赖加固"
git push origin v0.1.0
```

### P0-1（2026-09-09）

| 项 | 结果 |
|---|---|
| 全量测试 | `./venv/bin/python -m pytest tests -q -n 4` → **3224 passed, 36 skipped**（第二次提交后） |
| 覆盖率 | **91.26%**（门禁 80%） |
| 新增测试 | **+100 个**（3159 → 3259 收集数；第二次提交 +20：`TestP01ReadBoundaryMoreTools`、`TestWorkspaceReadBoundary`、允许目录收敛 4 例、`test_high_risk_confirmed_once_executes_once`、Web handler 越界可见 2 例）。首次提交：`test_agent_tools_safety.py` +55（`TestP01TokenLevelGrading` / `TestP01AutoConfirmAllows` / `TestP01ReadBoundary` 三个新类）、`test_cli_handlers_database.py` +7（`TestP01AutoConfirmRiskGate`）、`test_cli_handlers_config.py` +6（新文件）、`test_query_interface_exec_safety.py` +6（新文件）、`test_react_engine.py` +2、`test_web_app.py` +2、`test_web_services.py` +1、`test_query_interface_parse.py` +1 |
| 无子串匹配 | `grep -n 'in command.lower()' src/agent_tools.py` → 无输出（并有 `test_no_substring_matching_left` 守卫） |
| CLI `/config` | 终端输出见下（第二次提交后允许读目录由 4 条收敛为 3 条：两个 gradio 哈希目录折叠为 `…/T/gradio`） |
| flake8 语法门禁 | `flake8 --select=E9,F63,F7,F82 src tests` → rc=0（此前配置错误无法运行） |
| Web 系统页 | 「运行环境」渲染见下 |

CLI（`READ_ALLOWED_DIRS=~/Documents`）：

```
模型: qwen3.5:4b
Ollama 地址: http://localhost:11434
自动确认: 关
自动路由: 开
工作目录: /Users/steve/PycharmProjects/ollama-qwen-coder-rag-lib-agent
允许读目录: /Users/steve/PycharmProjects/ollama-qwen-coder-rag-lib-agent : /Users/steve/Documents : /private/var/folders/.../T/gradio
允许写目录: /Users/steve/PycharmProjects/ollama-qwen-coder-rag-lib-agent
数据目录: /Users/steve/PycharmProjects/ollama-qwen-coder-rag-lib-agent/data
索引目录: /Users/steve/PycharmProjects/ollama-qwen-coder-rag-lib-agent/index_storage
Agent 最大步数 / 超时: 50 / 300s
提示: 路径边界越界时工具返回 [错误] 路径超出允许范围，可用 READ_ALLOWED_DIRS / WRITE_ALLOWED_DIRS 放行
```

Web「系统 → 运行环境」（`format_env_info(WebService().env_info())` 实际输出，`CODE_AGENT_AUTO_CONFIRM=true READ_ALLOWED_DIRS=~/Documents`）：

```
| 自动确认（环境变量） | 开（只放行 low / medium） |
| 工作目录 | `…/ollama-qwen-coder-rag-lib-agent/src` |
| 允许读目录 | `…/src` · `/Users/steve/Documents` · `/private/var/folders/…/gradio/bce86ed6…` · `/private/var/folders/…/gradio/bf6e094d…` |
| 允许写目录 | `…/ollama-qwen-coder-rag-lib-agent/src` |
```

> 浏览器截图未提交：本次在无头环境实现，用 service → formatter 的真实渲染输出替代（系统页即 `gr.Markdown(format_env_info(...))`，无额外交互逻辑）。

## 与需求的差异

### P1-1

| # | 需求 | 实际 | 原因 |
|---|---|---|---|
| 1 | 「`ReActEngine.chat` 增加 `on_token` 参数并逐轮透传」 | 逐轮透传，但经 `FinalAnswerStream` 过滤，**只转发 `Final Answer:` 之后的文本**；工具调用轮不产生 token | 原始增量是 `Thought: … Action: read_file … Action Input: {...}`，直接推给 UI 会让用户先看到一段协议文本再被整段替换。过滤后 `_parse_response` 仍拿到完整累积文本，协议不受影响。代价：`Final Answer:` 出现前（模型写 Thought 期间）没有 token，单 Agent 首字比 RAG 综合晚。 |
| 2 | 「心跳仅在 ≥2s 无任何事件时发送」 | 保持 `heartbeat_interval = 1.0s`，语义为「≥1s 无任何事件（含 token）」 | `_bridge` 的 `queue.get(timeout=heartbeat_interval)` 本来就只在队列空闲时发心跳，流式期间自然静默；状态行「已用时」刷新依赖 1s 心跳，改成 2s 会让计时明显跳格。若仍要 2s 可改一处常量。 |
| 3 | 「取消：`stop_current` 触发时关闭底层 `response`」 | 单 Agent：`engine.stop()` → `abort_response`（**socket shutdown + close**）；RAG 综合与多 Agent 整合：靠 `should_stop` / 取消标志在**每个 token 之间**退出并 `gen.close()` / `resp.close()` | RAG 走 LlamaIndex `stream_chat`（ollama python client → httpx），没有可跨线程关闭的 `requests.Response`；生成期间 token 间隔约 50ms，实测停止延迟与关闭连接无差别。只 `close()` 不够：macOS 上另一线程 `close()` 不会唤醒阻塞的 `recv`，故加 `shutdown`。 |
| 4 | 「CLI … `rich.live.Live(Markdown(buffer))` 增量渲染」 | `Live(Panel(Markdown(buffer)), transient=True)`，完成后**清除实时区域再按原格式打印全文** | 答案面板前后还有「🤖 回答」头、`🔗 已理解为`、notices（before / after）、来源表、引用校验计数；若让 Live 面板直接作为最终输出，这些只能排在面板之后，破坏既有版式与所有现有 CLI 输出断言。transient 方案最终输出与非流式**逐字一致**，只多一次极短的面板替换。 |
| 5 | 「`Ctrl+C` 中断时关闭连接并打印"已中断"」 | 文案为「已中断：用户中断，任务已停止，已关闭与模型的连接。」（`/agent`）与「已中断，已关闭与模型的连接。」（`/ask`）；`/multi` 为「已中断：用户中断，协作已停止。」 | 保留原有「用户中断」字样（`test_cli_handlers_multi` 断言 `"用户中断" in ...`），并加"已中断"前缀满足验收。此前 `/ask` 期间 `Ctrl+C` 会直接抛出到主循环退出程序，现在回到提示符。 |
| 6 | 「`llm_helper.complete_text` 增加可选 `on_token`」 | 另加 `should_stop`，并抽出 `consume_ndjson_stream` / `abort_response` 供 `react_engine` 复用 | 避免 NDJSON 解析在两处各写一份；`abort_response` 需要被 `ReActEngine.stop()` 调用。 |
| 7 | 「现有测试不改断言」 | 断言未改；改了 6 处**测试替身签名**（见验证表） | 服务层 / CLI 现在总是传 `on_token`，固定签名的假引擎 / 假编排器 / 综合桩会 `TypeError`。加 `on_token=None` 形参不影响任何断言。 |
| 8 | 未提及 | `handle_agent` 用 `engine.on_token = live.on_token` 注入而非 `engine.chat(task, on_token=)` | 现有 3 条断言 `engine.chat.assert_called_once_with(text)`；引擎级回调本就是 `__init__(on_token=)` 支持的路径，`chat` 结束后恢复原值。 |
| 9 | 未提及 | Web 生成期间 transient 推理心跳不再覆盖「✍️ 生成回答中…」；`cancelled` 时保留部分回答并注明 | 首轮浏览器验证发现状态行在流式期间被「模型推理中.」反复覆盖；停止后气泡清空会让用户丢失已看到的内容。 |
| 10 | 需求「浏览器验证 … 点击停止后 1s 内状态变为已取消」 | 0.23s 内状态行变为「⏹️ 已发送停止信号，正在中止…」并解锁「发送」；最终「⏹️ 已停止 · 用时」帧未稳定出现 | Gradio 的 `cancels=` 会在停止时直接终止流式事件（`GeneratorExit`），`cancelled` 帧是否来得及渲染取决于时序，属既有行为（F7 起如此），本次未改。 |

### P0-1

| # | 需求 | 实际 | 原因 |
|---|---|---|---|
| 1 | 「原有测试全部不改断言」 | 改了 4 条 | 这 4 条恰好编码了被移除的子串行为，与 P0-1-a 互斥：`write_file test.py content` / `insert into table` / `update table set` 由 medium 改为 **low**（首 token 不是修改类命令，也无 SQL 客户端上下文），`python rm_all.py` 由 high 改为 **medium**（正是 §1 点名的误报）。改动处均写明原因，其余断言一字未动；另给 `TestReadFile` / `TestListDirectory` / `TestSearchFiles`、`TestAnalyzeProjectStructure`、Web 的 `TestCodeAssist` / `TestCodeSymbolsAndQuality` / `TestWorkspaceBrowse` 加了设置 `READ_ALLOWED_DIRS` 的 autouse fixture（**只加 fixture，不改断言**，沿用 P1-7 给 `TestWriteFile` 加 `WRITE_ALLOWED_DIRS` 的先例）；第二次提交把 3 处用绝对越界路径测"不存在"的**参数**改到允许目录内（`/nonexistent/path` → `temp_dir/nonexistent`、`/nope/x.txt` → `tmp_path/nope.txt`），断言文本不变，并给 `list_dir("/")` 用例追加了一条越界 error 断言。 |
| 2 | medium 集含 `tee`、`dd`、`sed -i` | 同需求；SQL medium 集扩到 `alter` / `replace` | 与 `insert/update/delete` 同类的写操作，漏掉会留缺口。 |
| 3 | 透明前缀「`sudo` / `env VAR=`」 | 扩到 `doas xargs nohup time command builtin exec nice ionice` 及其带值选项 | §1 验收要求 `ls | xargs rm` → high，仅剥 sudo/env 做不到；带值选项（`sudo -u root rm x`）不剥会把选项值当命令名。 |
| 4 | SQL 关键字「首 token 为客户端或命令含 `-c`/`-e`」 | 另对 `-c`/`-e` 的载荷递归做首 token 判定（深度 ≤2） | 否则 `bash -c 'rm -rf build'` 判 low。 |
| 5 | 只读判定 | 由「任一 `READONLY_PATTERNS` 命中」改为「全部子命令命中」 | `ls | xargs rm` 会被 `^ls` 提前判 low，无法满足验收要求的 high。需求未提及此处，但不改无法达成验收。 |
| 6 | 「CLI `/config` 增加两行」 | **新建** `/config` 命令 | 该命令原本不存在（§0.2 的 `query_interface.py:1517` 实际指向 `/model` 无参输出的「自动确认」行）。经确认新建 `/config`，一并显示模型 / 自动确认 / 数据与索引目录等运行配置，与 Web「运行环境」对齐；`print_help`、`TUTORIAL_TEXT`、README 命令表同步。 |
| 7 | 未提及 | `react_engine` 的 `registry.execute` 增加 `or step_record["confirmed"] is True` | 闸门收紧后，high 命令经用户确认仍会被 registry 二次索要确认（`[CONFIRM_REQUIRED]`）。加此条保持「确认一次即执行」，不引入新的免确认路径。 |
| 8 | 未提及 | CLI `/file <path>` 一并受读边界约束 | 经确认：用户显式命令与 Agent 同一边界，无绕过口；README 与 `print_help` 说明可用 `READ_ALLOWED_DIRS` 放行。 |
| 9 | §1 只点名 `read_file` / `list_directory` / `search_files` | **扩到** `analyze_project_structure` / `ast_search` / `code_quality_check` / `git_analyze` / `git_commit_gen` 与 Web「工具」页 7 个直接读盘入口（第二次提交） | 首次提交后核实：Web 端 `services.py` 有 5 处直接 `open()` / `os.walk()` 完全绕过边界——Agent 读 `~/.ssh` 被拦，Web 工作区输入同一路径却能预览，违反 AGENTS.md "禁止只修一端"。`database_connect` 的 SQLite 路径仍未接边界（数据库工具另有 `safe` 标记），记为待办。 |
| 10 | 需求"已入库文件所在目录" | 落在 Gradio 上传根下的目录折叠为根一条；被包含的子目录不列 | 每个 Web 上传文件都在独立哈希目录，逐条列出会让 `/config` / 系统页随入库数增长；上传根下都是用户自己上传的内容，放行整个根不扩大风险面。 |
| 11 | 本次未要求 | 修 `.flake8` 配置 + 删 5 处死 `global` | flake8 因 `ignore` 行内注释根本跑不起来；P0-2-b 要把它改为阻断门禁，先给出干净基线。属 P0-2 范围，提前做掉。 |

### P0-2

| # | 需求 | 实际 | 原因 |
|---|---|---|---|
| 1 | 「在当前 venv 用 `pip freeze` 取实际版本」 | setuptools / gitpython / pillow / pypdf 先升级再冻结 | 直接冻结本地版本会把 **51 条已有修复版**的漏洞钉死在仓库里，反而比原先「不钉版本、CI 每次装最新」更差；`pypdf` 本地 6.13.3 还低于原约束 `>=6.15`（Dependabot 升过约束但本地没装）。四个包升到有修复的版本后再 `pip freeze`，`pip-audit` 从 51 条降到 5 条（全部无修复版）。 |
| 2 | 「pip 缓存 key 含 `hashFiles('requirements*.txt')`」 | 另加一步 `python -m pip cache dir` 解析缓存路径 | 原写死的 `~/.cache/pip` 只在 Linux 成立，macOS 是 `~/Library/Caches/pip`、Windows 是 `%LOCALAPPDATA%\pip\Cache`；上矩阵后不改会让另两个平台缓存永远 miss。 |
| 3 | 「覆盖率与 Codecov 仅 ubuntu 上传」 | 连同 pip-audit 步骤、`security-reports` / `coverage-reports` 两个 artifact 上传也限定 ubuntu | `actions/upload-artifact@v4` 同名 artifact 在三个平台并发上传会直接失败；pip-audit 是纯依赖扫描，跨平台重复跑无收益。 |
| 4 | 「flake8 改为阻断但只查 `E9,F63,F7,F82`，其余保持 `continue-on-error`」 | 拆成两个独立 step | 原来两条 flake8 命令在同一个 step 里、整个 step `continue-on-error: true`，「只让语法错误阻断」在单 step 内无法表达。 |
| 5 | 未提及 | `install_deps.ps1` 的 OCR 安装行由 `pymupdf>=1.25.0 opencv-python>=4.13.0` 改为 `==` 钉版本 | PowerShell 把 `>` 解析成输出重定向，原命令实际是写文件而不是装包（既有 bug）。钉版本顺带修掉。 |
| 6 | 「`Makefile` 同步」 | 拆出 `install` / `install-dev` / `test` 三个目标，`build` 依赖 `install` | `pr-build-vulnerability-gate.yml` 依赖 `make build`（本次不改该 workflow），必须保持其行为不变；新增目标只是补充入口。 |
| 7 | §0.3 称「PR 由 `pr-build-vulnerability-gate.yml` 跑构建 + pip-audit，**不跑测试**」 | 该 workflow 实际有 `test` job（跑 pytest + `coverage report --fail-under=80`） | 立项时的事实记录有误。因本次不改该文件，仅记录：合并后 PR 上会同时有 `ci.yml` 三平台测试与该 workflow 的 ubuntu 测试，存在重复执行，可在后续任务中合并。 |
| 8 | 未提及 | 三平台测试均为**阻断**（未加 `continue-on-error`） | 按需求原文实现。风险：测试套件此前从未在 macOS / Windows 跑过，首次 PR 可能因路径分隔符 / 编码 / 文件锁等平台差异变红。若要先观察一轮，可给非 ubuntu 的测试步骤临时加 `continue-on-error: true`。 |
