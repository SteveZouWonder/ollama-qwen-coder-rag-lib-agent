# F8: 三种对话模式优化（RAG 检索 / 单 Agent / 多 Agent）

## 实施状态

**✅ 全部完成** · 分支 `feat/agent-modes-optimization` · 目标：提升任务质量、回答准确度与智能程度

| 级别 | 主题 | 完成日期 | 提交 |
|---|---|---|---|
| P0 | 多 Agent 重做为真实 Agent | 2026-09-04 | `8a31b96` |
| P1 | 单 Agent 鲁棒性与上下文 | 2026-09-05 | `9075907` |
| P2 | RAG 推理与可核验性 | 2026-09-06 | `d6f69c2` |
| P3 | 入口智能路由 | 2026-09-06 | `3071dd2` |
| P4 | 代码感知分块 | 2026-09-07 | `f53480f` |

## 文档导读

| 文件 | 内容 | 适合 |
|---|---|---|
| [REQUIREMENTS.md](REQUIREMENTS.md) | 需求分项与验收标准；§0 为立项时核实的代码事实（带 `文件:行号`）；附录 A 为 LLM 提示词草案 | 了解"要做什么、为什么" |
| 本文件 | 实现记录（每项做了什么、落在哪个模块）、与需求的差异、验证结果 | 了解"实际做成了什么" |
| [PROMPT.md](PROMPT.md) | 交给 Agent 的启动提示词（省 token 版，可按 P 级拆多次任务） | 复用本流程做新任务 |

用户可感知的变更同步记录在 [CHANGELOG.md](../../../CHANGELOG.md) `[Unreleased]` 与主 [README](../../../README.md) 对应段落。

## 范围

| 级别 | 模式 | 内容 |
|---|---|---|
| P0 | 多 Agent | 4 个硬编码桩 Agent 改为委托 ReActEngine 真实执行；LLM 任务分解 / 结果整合 / 竞争评审；真并行与超时；结构化来源；CLI `/multi` |
| P1 | 单 Agent | 系统提示分层（内置 ≤1.5K token + 项目附加）；协议容错重试；步数耗尽强制总结；重复调用检测；本轮上下文预算折叠；知识库工具对齐 RAG 编排；安全分级与写路径边界 |
| P2 | RAG | 逐片段 rerank（LLM 默认 / cross-encoder 可选）；复合问题分解与多跳；带编号引用的综合与思维链透出；BM25 hybrid 召回；失败回退提示 |
| P3 | 路由 | 自然语言输入的意图判定（规则 + LLM 兜底），CLI `/auto`、Web「自动」模式 |
| P4 | RAG 入库 | 代码文件按函数/类切分（tree-sitter 可选依赖，缺失回退）；碎片合并与符号/行号元数据；来源可定位到 `文件 · 符号 · L起-止`；CLI/Web 入库文案、进度、文件表、详情、来源、系统页联动；顺带修复 `load_index` 分块参数、chunk_count 估算、扩展名白名单不一致 |

依赖顺序：P0 前置完成了 P1-1 的 `allowed_tools` / `system_prompt_extra` 参数；P4 复用 P2 的 sources / rerank / 进度事件结构。

## 实现记录

每项对应 REQUIREMENTS.md 的需求编号；「差异」指实现与需求文本不一致之处及原因。

### P0 · 多 Agent 重做为真实 Agent（2026-09-04，`8a31b96`）

- **P0-1 专业 Agent 委托 ReActEngine** — `agents/base_agent.py::ReActDelegateAgent` 统一委托逻辑；Code/Test/Doc/Audit 只声明 `ROLE_PROMPT` / `ALLOWED_TOOLS` / `ESSENTIAL_TOOLS`。新增：未调用关键工具即给结论 → 标记「未经验证」
- **P0-2 LLM 任务分解** — `TaskDecomposer(complete, use_llm)`，`last_method` 供进度文案；回退关键词表
- **P0-3 LLM 结果整合** — `ResultIntegrator.integrate*(…, request)` 产出 `answer` / `answer_method` / `sources` / `tasks`；单一成功子任务直接采用（不额外调用）
- **P0-4 真并行与超时** — 依赖分波 + `ThreadPoolExecutor`；`execute_task_with_timeout` 线程 + `cancel()`；失败/超时恢复 IDLE
- **P0-5 COMPETITIVE 选优** — LLM 评审 `{"best","reason"}`；回退最长成功输出；全部失败取错误信息最详细者
- **P0-6 结构化来源与展示** — `AgentResult.sources`；`collaboration/presenter.py` 为 CLI/Web 共用渲染器
- **P0-7 配置生效** — `agent_orchestrator._create_agent` 传 model/host/timeout/max_iterations/allowed_tools；`agent_config` 白名单为真实工具名
- **P0-8 文案与 CLI `/multi`** — 文案按 `last_method` 如实；CLI `/multi … [--mode m]`（`cli_handlers.handle_multi`）

### P1 · 单 Agent 鲁棒性与上下文（2026-09-05，`9075907`）

- **P1-1 系统提示分层** — `build_system_prompt(tools, extra, mode)`、`CODE_AGENT_PROMPT_MODE`、`SYSTEM_PROMPT_EXTRA_MAX_CHARS`；内置提示 ≈1.07K token（P0 前置）。`.devin/SYSTEM_PROMPT.md` v4.3.0 清理 `todo_write` / `~/.config/devin/*` / 「用 read_system_prompt 读本提示」/ `execute_command` 跑斜杠命令四类错误指引，原文备份 `.bak`（gitignore）
- **P1-2 协议容错** — `ReActEngine._parse_response` 三分类 action / final / format_error；`_handle_format_error` 连续重试 ≤`MAX_FORMAT_RETRIES`（env，默认 2），超过按现有文本收尾标注「（格式异常，可能不完整）」；`[错误]` 直接返回不 `_record_turn`
  - 差异：重试计数按**连续**格式错误（合法步骤后重置），"未知工具"也归为格式错误（不再执行 registry 得到 `[错误] 未知工具`）
- **P1-3 步数耗尽强制总结** — `_forced_summary(reason)`：追加 user 总结请求，`_call_model(num_predict=1024, think=False)`，前缀「⚠️ 未完成（已达最大步数 N）」；模型失败回退执行摘要
- **P1-4 重复检测** — `_check_repeat`：`(tool, json.dumps(sort_keys))` 计数，第 2 次回灌 `[重复调用]` 不执行，第 3 次 → `_forced_summary("repeat")` 前缀「⚠️ 未完成（检测到重复调用，已终止）」
  - 差异：全局计数而非仅"连续"相同
- **P1-5 本轮预算** — `_compute_turn_budget = num_ctx − system − history − 4096`（下限 1024）；`_truncate_observation`（`OBSERVATION_MAX_CHARS` env，默认 3000）；`_enforce_budget` 每步后检查，从最早步折叠为「（第 k 步 tool=x 结果已折叠，要点：前 200 字）」，保留最近 3 步；复用 `conversation_context.estimate_tokens / estimate_messages_tokens`
- **P1-6 知识库工具对齐** — `query_knowledge_base` → `answer_question(engine, q, enable_web_search=False, show_progress=False, kb_only=True)`；`format_kb_tool_result` 渲染「答案 + 相关性结论 + top-3 片段（≤300 字，含文件名）」/ `[知识库无相关内容]` / 元查询概览
  - 差异：新增 `kb_only` 参数——否则 `generate_answer` 在 0 命中时仍会 `simple_web_search` + LLM 兜底，结果被工具丢弃属纯浪费
- **P1-7 安全分级补洞** — `CommandSafetyChecker.MEDIUM_PATTERNS`（install / git 写操作 / `python x.py` / `node x.js` / make / docker run|exec）与 `HIGH_PATTERNS`（`curl|wget … | sh|bash|zsh`，含 `sudo`）；`is_path_allowed` + `WRITE_ALLOWED_DIRS`（env，冒号分隔，`Config.WRITE_ALLOWED_DIRS` 映射）保护 `write_file` / `add_to_knowledge_base`
  - 差异：`curl … | sh` 由 critical（直接拦截）改为 high（需确认），`| bash` 此前漏判为 low；多 Agent 子角色 `_auto_confirm` 只放行 low/medium，故 pip install / python x.py 在子 Agent 内仍自动放行、curl|sh 被拒——属预期
- **P1-8 观测事件** — `step_log` 事件 `format_retry / repeat / budget_fold / forced_summary / error`；`ReActEngine.get_step_summary` / `_trace_summary`、`web/app.py::format_step_log`、`query_interface.on_step_callback`（`STEP_PHASE_EMOJI/COLOR`：`[~] [R] [F] [!!] [E]`）与 `/summary` 同步

### P2 · RAG 推理与可核验性（2026-09-06，`d6f69c2`）

- **P2-1 逐片段 rerank** — `src/rag_rerank.py::rerank(question, sources, progress, complete=None, kind=None)`：`RERANKER=llm` 默认（`build_rerank_prompt` 附录 A 草案、片段截 400 字、`parse_rerank_output` 校验越界/重复、保留项带 `rerank_note`），`RERANKER=cross-encoder` 走 `sentence_transformers.CrossEncoder(RERANKER_MODEL)`（sigmoid ≥0.3 保留，模块级缓存），ImportError → `rerank_fallback` 事件 + 回退 llm。`generate_answer` 用其替换 `judge_kb_relevance`（后者保留作解析失败回退，保守保留）；top≥0.6 跳过；keep 为空 → 未命中。进度 `rerank / rerank_done / rerank_fallback`
  - 差异：LLM 调用走 `llm_helper.complete_text`（`/api/chat` 直连才能 `think=False`+`num_predict`），`tests/conftest.py` 全局拦截默认调用避免测试打真 Ollama
- **P2-2 复合问题分解 + 多跳** — `plan_retrieval(question, progress)` 一次 LLM 输出 `{"complex","subquestions"(≤3, 去重, <2 个降级),"needs_search","queries"}`（国内查询剔英文词逻辑保留），`plan_web_search` 为兼容封装；`augment_with_web_search(..., plan=)` 复用规划。`answer_question` 在联网或知识库已初始化时规划一次，`complex` 时 `generate_answer(subquestions=)` 逐子问题 `query_with_sources`、`_merge_multi_hop` 按 `(file, content)` 去重、按分排序，事件 `kb_decompose / kb_merged`
  - 差异：关闭联网 / `kb_only` 仍规划（比改动前多 1 次调用，联网路径不变）；多跳强制综合不走快路径
- **P2-3 带编号引用的综合 + 思维链透出** — `format_kb_context` → `[i]（来自 f）`；`compact_web_context(..., web_sources)` 以 `[Wj]` 标注摘要与正文页；`synthesize_prompt` 第 6 条要求句末标注 `[i]`/`[Wj]`；`assign_refs` 写入 `kb_sources[i].ref` / `web_sources[j].ref`（回退搜索得到的网络来源也编号并返回）。Web `format_sources` / `format_web_sources` 显示 `[ref]`、相关性理由、「关键词命中」；CLI `print_rag_sources` / `print_web_sources` 加 `#` 列。thinking：`_complete` 经 `extract_thinking`（`raw.message.thinking` → `additional_kwargs` → `ThinkingBlock`）在 `_THINKING_SINK`（ContextVar，`answer_question`/`generate_answer` 在 `rag_engine.llm_think` 为真时设置）非空时 `_emit("thinking", 截 800 字)`；CLI dim + `rich.markup.escape`
- **P2-4 hybrid 召回** — `RAGEngine._ensure_bm25`（`chroma_collection.get(include=["documents","metadatas"])`，中文单字+二字组、英文小写词分词）、`invalidate_bm25`（`build_index / add_documents / remove_file / clear_index`）、`rrf_fuse(dense, sparse, top_k, k=60)`（`retriever` = dense/bm25/hybrid，`rrf` 原始分）、`query_with_sources(question, progress_callback=None, hybrid=None)` 返回附 `"hybrid": bool`；`RAG_HYBRID`（默认 true）/ `RAG_HYBRID_MAX_CHUNKS`（默认 20000，超限 `phase="hybrid_off"` 提示 + print）；`rank_bm25` 未安装静默回退。`requirements.txt` 加 `rank_bm25>=0.2.2` 与 sentence-transformers 可选依赖注释块
  - 差异：BM25-only 项 `score = rrf / (2/(k+1))`（上限 0.5）而非按当批最大值归一，避免纯关键词命中拿 1.0 跳过 rerank；含 bm25 片段时强制综合
- **P2-5 失败回退提示** — `generate_answer` 末路径：知识库已初始化且无相关片段、`simple_web_search` 也为空 → `kind="fallback"`、`fallback_question`、答案末尾 `fallback_suggestion()`（「建议：/agent <原问题> 让 Agent 用工具进一步查找」）、事件 `fallback`。`web/services.rag_query_stream` 透传 `kind` / `fallback_question`；`web/app.on_chat_stream` 改为**七元组**（第 7 项 `retry_md`），`web/ui/chat.py` 新增 `retry_row`（`#retry-agent-btn`「用单 Agent 重试」：切 `mode`=单 Agent → 用 `pending_msg` 重发 → `_end`），`stop` 可取消该链；CLI `_run_ask` 在回答后打印「可试试：/agent <原问题>」

### P3 · 入口智能路由（2026-09-06，`3071dd2`）

- **P3-1 意图判定** — `src/intent_router.py::classify_intent(text, kb_available=True, complete=None) -> RouteDecision(mode, reason)`（可解包为 `(mode, reason)`）。规则表为模块常量：`PATH_PATTERNS`（绝对/相对/家目录路径、`*.ext`、常见源码/配置扩展名，先剔除 URL 避免 `https://…/a.py` 误判）、`AGENT_VERBS_ZH/EN`（英文按词边界）、`RAG_QUESTION_MARKS/WORDS_ZH`、`RAG_TOPIC_WORDS_ZH`、`RAG_PREFIXES_ZH`、`RAG_WORDS_EN`；`agent_signals` / `rag_signals` 返回命中描述用于原因文案。单边命中直接判定；冲突或无信号 → `kb_available=False` 直接 agent（0 次 LLM），否则 `llm_classify`（`INTENT_PROMPT` 附录 A 草案，`complete_text(num_predict=4, timeout=5)`，`parse_intent_word` 剥 `<think>` 后取词），异常/超时/乱输出回退 rag。`tests/conftest.py` 新增 `block_intent_llm` 全局拦截默认调用
  - 差异：需求只列了动词与疑问词，实现额外补了"帮我写/编写/调试/移动/复制"与"哪些/多少/原理/含义/讲讲"等常用词以及英文同义集合，并把 `build` 从动词表剔除（"build fail" 类疑问句误判）
- **P3-2 CLI 自动路由 / `/auto`** — `config.AUTO_ROUTE`（env `AUTO_ROUTE`，默认 true，`Config.AUTO_ROUTE` 映射，运行时开关直接改类属性）；`parse_command` 识别 `/auto` / `/auto on|off`（`classify_mode` 归为 `cmd`）；`handle_auto` 复用 `model_switcher.parse_think_flag`（无参显示状态与用法）。`handle_natural` 在 `Config.AUTO_ROUTE` 为真时调用 `_route_natural_to_agent`：`kb_available = rag_engine.query_engine is not None`，判为 agent 打印「🤖 已按 Agent 模式处理（原因；用 /ask 强制知识库；/auto off 关闭自动路由）」并交给 `handle_agent(ParsedCommand("agent", raw, text))`（会话由 ReAct 引擎落库，不重复记录；命令记录为 `agent`），否则原 `_run_ask`。`/ask` `/agent` 不判定；`classify_mode` 语义不变。`/help` `TUTORIAL_TEXT` 同步
  - 差异：Agent 引擎不可用（`ctx.react_engine` 与模块级均为 None）或判定抛异常时静默回退知识库问答；`handle_agent` 改为优先用 `ctx.react_engine`
- **P3-3 Web「自动」模式** — `web/ui/chat.py::MODE_AUTO="自动"`（`web/app.py` 同名常量）加入模式分段首位并设为默认，`_mode_changed` 在自动下同时显示 `enable_web` 与 `auto_confirm`（初始 `visible=True`）；空态文案改为介绍自动模式。`WebService.kb_available()` / `classify_intent()`（异常回退 rag）/ `chat_auto_stream(message, enable_web_search, auto_confirm, session_id, interactive_confirm=True)`：先 yield `progress`「🧭 自动路由：按 RAG/Agent 处理（原因）」（`data.phase="route"`），再分发到 `rag_query_stream` / `agent_chat_stream`（`confirm_handler=lambda: True` 当 auto_confirm，否则 `interactive_confirm`），`answer.data` 追加 `routed_mode` / `route_reason`，其余事件（confirm/heartbeat/step/cancelled/error）原样透传。`on_chat_stream` 的自动分支据 `routed_mode` 选择渲染路径（缺省 rag），状态行「✅ 完成 · 用时 … · 实际模式：RAG 检索|单 Agent · 上下文 …」；七元组不变，P2 `kind/fallback_question`（重试按钮）与 `step_log` 渲染不变。非流式 `on_chat` 同样支持（`interactive_confirm=False`，侧栏首行为路由原因）
  - 差异：意图判定在 `_bridge` 之外同步执行（最长 5s，无心跳），因规则命中时为零开销、LLM 兜底有硬超时而接受

### P4 · 代码感知分块（2026-09-07，`f53480f`）

- **P4-1 切分器 `code_chunker.py`** — `src/code_chunker.py`：`LANGUAGE_MAP`（8 种语言，`config.CODE_FILE_EXTENSIONS` 同源）、`LanguageAwareNodeParser(NodeParser)` 按 `file_type` 分派；代码路径**自研** tree-sitter 切分（原子收集 → 贪心打包（定义前优先断块、只在行首断）→ 碎片并入下一块 / 尾碎片并入上一块 → 超长块按行二次切分），metadata `symbol / start_line / end_line / language / chunk_strategy / part`，首行注释头 `# file · symbol · L起-止`；`ERROR` 字节占比 >30% 回退
  - 差异：未复用 llama-index `CodeSplitter`（实测碎片多、无位置信息），改为直接基于 tree-sitter 节点树实现；超长块用**按行贪心**而非 `SentenceSplitter` 二次切（不拆行、无 tokenizer 开销）；`part i/n` 对任何跨块符号标注而不只限超长函数。实测 `rag_engine.py` 48 块 / 0 碎片 / 行号全部核对一致
- **P4-2 引擎接入** — `RAGEngine.node_parser`（惰性 `build_node_parser()`）在 `build_index / load_index / add_documents` 三处统一；`_split_documents` 先切分再 `VectorStoreIndex(nodes=…)` / 分批 `insert_nodes`（`_INSERT_BATCH=16`），`progress_callback` 发 `stage=chunk|embed`；`per_file` 统计直接写 `FileMetadata.chunk_count / symbol_count / chunk_strategy`（新增字段，`from_dict` 忽略未知键）；`_backfill_file_metadata_from_vector_store` 从 node metadata 反推；`_make_source` 为 dense / BM25 两路共用（剥注释头、透出符号字段）；`_bm25_tokenize` 拆 `snake_case/camelCase`；`rrf_fuse` 键 `(path, L起始行)`；`get_stats().code_chunking / code_chunk_max_chars`
  - 差异：切分异常时回退 `from_documents(transformations=[parser])` / `index.insert(doc)` 内部路径，保证 Mock 文档与异常输入不阻断入库
- **P4-3 RAG 管道** — `format_kb_context` → `[i]（来自 file · symbol · L起-止）`（`source_location` 共用）；`synthesize_prompt` 第 7 条行号引用规则；`_merge_multi_hop` 代码块按起始行去重；`kb_merged` / `rerank_done` 事件带 `symbols` 与符号名文案；`build_rerank_prompt` 片段标签附符号
- **P4-4 CLI** — `handle_add` rich `Progress`（切分 / 嵌入两行，非 rich Console 不渲染）+ `format_ingest_summary` 文案 + `availability_hint_once`（进程内一次，仅含代码文件时）；`/file-list` 加「🧩 片段 · 分块」行、`/file-info` 加「🧬 分块策略」（`describe_file_chunking` 共用，旧库代码文件提示重新入库）；`/sources` 文件列下加 dim `symbol · L起-止 · (part)`；`/ask` 摘要「（N 个代码符号）」；`--build-only` 补 `file_paths` 并打印摘要；`/help` `TUTORIAL_TEXT` 更新
- **P4-5 Web** — `services.ingest_stream`（`_bridge` 桥接 `add_documents / add_path` 的 `progress_callback`）+ `app._ingest_stream / on_upload_stream / on_add_path_stream`（`ProgressTracker` 渲染「⏳ … 入库进度」，完成后刷新统计卡片）；`ui/knowledge.py` 上传与追加改流式并在进行中禁用按钮；`_file_meta_dict` 新增 `chunk_strategy / symbol_count / chunking / chunking_short`，文件表「片段 · 分块」列 `27 · 代码`，`format_file_info` 加「分块策略 / 符号数」；`format_sources` 标题 `` `symbol` · L起-止（part）``、代码内容按 `language` 围栏（内部 ``` 转义）；系统页「文本分块 / 重叠」+「代码分块」两行（`_code_chunking_env_text`），统计卡「分块 / 重叠」附「/ 代码 1500」；`presenter.format_sources_md`、`rag_agent` sources、`agent_tools.format_kb_tool_result` 带符号与行号
- **P4-6 依赖、打包与测试** — `requirements.txt` 可选依赖注释块；`requirements-build.txt` 加 `tree-sitter-language-pack>=1.16,<2` 与此前漏掉的 `rank_bm25`；`packaging/cerebro.spec` `collect_all` 三个包（缺失时跳过）。测试：`tests/test_code_chunker.py`（29，真实解析用例 `skipif` 缺依赖）、`tests/test_cli_code_chunking.py`（12）及 rag_engine / pipeline / rerank / web / presenter / agent_tools 增补；屏蔽 tree-sitter 导入后相关套件仍全部通过；全量 2704+ 通过、覆盖率 89%

## 与需求的差异汇总

各 P 级完成时记录的总体差异（细项差异见上文各条目）：

- **P0**：前置完成 P1-1 的 `build_system_prompt(tools, extra, mode)` 分层、`allowed_tools` / `system_prompt_extra` / `max_iterations` 参数与 `CODE_AGENT_PROMPT_MODE`（`.devin/SYSTEM_PROMPT.md` 错误指引清理留在 P1）；新增「未经验证」标记（子 Agent 未调用角色关键工具却给出结论时）；子 Agent 对白名单内需确认工具自动放行、`execute_command` 只放行 low/medium 风险（需求未规定确认策略）。
- **P1**：格式重试按**连续**次数计（合法步骤后重置）；重复检测为全局计数；`answer_question` 新增 `kb_only` 参数避免 0 命中时的无用网络回退；`curl … | sh` 由 critical 降为 high（需确认而非直接拦截，`| bash|zsh` 同级）；`write_file` / `add_to_knowledge_base` 越界拒绝对 Web「工具」页同样生效。
- **P2**：rerank 的 LLM 调用走 `collaboration.llm_helper.complete_text`（`/api/chat` 直连，才能真正 `think=False` + `num_predict`；`Settings.llm.complete` 的 `think` kwarg 会被 `or self.thinking` 吞掉），解析失败回退 `judge_kb_relevance`；`plan_retrieval` 在关闭联网时**仍会调用一次**（为了分解），故 `enable_web_search=False` / `kb_only` 路径比改动前多 1 次规划调用（联网路径次数不变）；BM25-only 片段的 `score` 用 RRF 相对"两路均第 1"的归一值（上限 0.5：能过 0.45 粗筛、不会触发 0.6 跳过 rerank）；hybrid 补入 BM25 片段或多跳时不再走"沿用 LlamaIndex 原答案"的快路径而强制综合；`kind="fallback"` 只在知识库已初始化且无命中、网络也无结果时触发（知识库未初始化不算）。
- **P3**：规则表在需求列举之外补充了常用中英文动词/疑问词并剔除易误判的 `build`；路径匹配先剔除 URL；`classify_intent` 返回 `RouteDecision(mode, reason)`（可解包）而非裸字符串，原因文案用于 CLI 提示与 Web 处理过程；CLI 在 Agent 引擎不可用或判定异常时静默回退知识库问答；Web 意图判定在心跳桥接之外同步执行（LLM 兜底硬超时 5s）。
- **P4**：未复用 llama-index `CodeSplitter` 而直接基于 tree-sitter 节点树自研切分（原子→打包→合并，只在行首断块）；超长块按行贪心二次切分而非 `SentenceSplitter`；`part i/n` 对任何跨块符号标注；切分异常回退 LlamaIndex 内部路径；Web 入库进度以结果区 Markdown（`ProgressTracker`）呈现而非独立进度条组件。

## 验证记录

| 级别 | 自动化 | 浏览器验证（playwright + 打桩引擎/LLM） |
|---|---|---|
| P0 | `tests/multi_agent/`：分解 JSON 与回退、并行与超时、竞争评审与回退、整合 answer/sources、ERROR 恢复；`src/` 桩文本零命中 | Web 多 Agent「写一个快速排序并写测试」：Code / Test Agent 各有真实 ReAct 步骤，结果面板显示综合回答与来源 |
| P1 | `tests/test_react_engine.py`：分层提示、`allowed_tools`、格式重试、`[错误]` 不入会话、步数耗尽总结、重复检测、预算折叠、知识库工具对齐；`tests/test_agent_tools_safety.py`；内置提示 ≈1.07K token | Web「处理过程」实时显示格式重试 / 重复调用事件，无 console error |
| P2 | `tests/test_rag_rerank.py`、`tests/test_rag_pipeline.py`：rerank 解析与回退、cross-encoder 缺依赖回退、分解与单跳快路径调用次数、编号引用、hybrid RRF 与失效、fallback kind | 编号来源与理由、thinking 步骤、fallback 按钮切模式重发，无 console error |
| P3 | `tests/test_intent_router.py` 规则用例 ≥20、LLM 回退与超时；Web/CLI 处理器测试 | 默认选中「自动」；问句按 RAG 渲染并显示「实际模式：RAG 检索」；"修改 main.py …" 按 Agent 渲染，无 console error |
| P4 | `tests/test_code_chunker.py`（29，真实解析用例缺依赖时 `skipif`）、`tests/test_cli_code_chunking.py`（12）及 rag_engine / pipeline / rerank / web / presenter / agent_tools 增补；屏蔽 tree-sitter 导入后相关套件仍全部通过；实测 `rag_engine.py` 48 块 / 0 碎片 / 行号全部核对一致 | 路径追加显示流式进度与「✅ 已入库 1 个文件 · 38 个片段（其中 1 个代码文件按函数/类切分，共 31 个符号）· 用时」；文件表 `38 · 代码`；详情含分块策略与符号数；来源面板 `RAGEngine._ensure_bm25 · L620-640` + 代码围栏；处理过程显示符号名；系统页「代码分块 启用 · max 1500 字 · tree-sitter-language-pack 1.16.2」；无 console error |

全量：`./venv/bin/python -m pytest -q -n 4` 2704 通过 / 36 跳过，覆盖率 89%（P4 完成时）。

## 关联

- 前置基础：[F2 多 Agent 协作系统（骨架）](../f2-multiple-agent/)、[F6 Agent 工具集](../f6-capability-tools/)、[F7 Web 界面](../f7-web-ui/)
- P4 来源：原 `docs/features/README.md`「残留小项 · 代码感知分块」（F6 / F5.2 遗留），2026-09-07 评估后并入 F8
- 功能索引：[../README.md](../README.md) · 路线图：[../ROADMAP.md](../ROADMAP.md)
