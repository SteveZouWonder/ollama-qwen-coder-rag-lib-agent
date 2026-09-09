# 模块指南

按目录分组说明每个模块的职责、关键函数与改动时的注意点。行号会漂移，以函数名为锚点。整体分层见 [ARCHITECTURE.md](ARCHITECTURE.md)。

## 基础层

### `config.py`
- 把 `.env` / 环境变量解析为模块级常量，并提供兼容的 `Config` dataclass（`Config.LLM_MODEL`、`Config.MAX_ITERATIONS`、`Config.AUTO_CONFIRM`、`Config.AUTO_ROUTE` …）。
- 运行时可变项有 setter：`set_llm_model()`、`set_llm_think()`（CLI `/model` `/think` 与 Web 模型页调用）。
- `resolve_num_ctx(model)`：按参数量推导安全上下文窗口（≤4B→16384，7–9B→8192，≥12B→4096），`LLM_NUM_CTX` 可覆盖。
- 两个阈值不要混：`SIMILARITY_CUTOFF`(0.3) 是底层召回保护，`KB_RELEVANCE_THRESHOLD`(0.45) 是编排层"命中"判定。
- `READONLY_COMMANDS` / `DANGEROUS_PATTERNS` **无人引用**；命令安全规则在 `agent_tools.CommandSafetyChecker`。
- LLM 后端（F10 P1-2）：`LLM_PROVIDER`（`ollama` | `openai`，其他值回退 ollama 并 warning）、`LLM_BASE_URL`（默认取 `OLLAMA_BASE_URL`）、`LLM_API_KEY`、`LLM_REASONING_EFFORT`（默认 `none`）；均有 `Config.*` 映射。`OLLAMA_BASE_URL` 仍是嵌入模型与 Ollama 专有操作（卸载 / `/api/ps`）的地址。

### `llm_client.py`（F10 P1-2）
- **项目内唯一允许出现 `"/api/chat"` / `/api/generate` 字面量的文件**（`tests/test_llm_client.py::TestNoDirectEndpointsOutsideLLMClient` 守卫）。
- `LLMClient` Protocol：`chat(messages, *, model=None, options=None, think=False, on_token=None, should_stop=None, on_response=None, timeout=None) -> str`、`list_models() -> list[str]`、`health() -> bool`。`model=None` 时每次调用读 `config.LLM_MODEL`（所以 `set_llm_model` 不需要重建 client）。
- `OllamaClient(base_url)`：请求体 `{model, messages, stream, think, options}` 与 P1-2 之前的直连**逐字节一致**（`options` 原样透传；非流式 `requests.post(url, json=, timeout=)` 不带 `stream=` 关键字，现有测试对 `requests.post` 的打桩全部沿用）；流式 `consume_ndjson_stream`。另有 Ollama 专有 `unload(model)`（`/api/generate` + `keep_alive: 0`，`model_switcher.unload_model` 调用）。
- `OpenAICompatClient(base_url, api_key)`：`base_url` 带不带 `/v1` 均可；`Authorization: Bearer`；`map_options`：`temperature` 直传、`num_predict → max_tokens`、`num_ctx` 忽略（debug 日志一次）、其余忽略；`think=False` → `reasoning_effort=LLM_REASONING_EFFORT`（后端 400 时去掉重试一次，成功则记住不再发送；`think=True` 不发送）；流式 `consume_sse_stream`（`data:` 行、`[DONE]`、`choices[0].delta.content`，忽略 `reasoning` 增量）。
- 错误约定：`requests.exceptions.ConnectionError / Timeout` 原样抛出（调用方文案不变）；HTTP ≥400（含 401 提示检查 `LLM_API_KEY`）、流中 `error`、非法 JSON、缺 `choices` 抛 `LLMError(status_code=)`（`RuntimeError` 子类）。`_check_status` 只在 `status_code` 为整型时判断——`MagicMock()` 响应会被放过，测试替身无需设 `status_code`。
- 并发限流（F10 P2-1-d）：两种 client 的请求（含流式读取全程）都在 `with llm_slot():` 内，共享进程级 `FairSemaphore(OLLAMA_MAX_CONCURRENCY)`（FIFO，避免多轮 ReAct 的子 Agent 饿死同伴；`≤0` 不限制）。`max_concurrency()` / `set_max_concurrency(n|None)`（测试 / 运行时覆盖）、`slot_stats()`、线程局部 `set_queue_listener(QueueWaitTracker)`（`on_queue_start / on_queue_end / total()` 含进行中的等待）。`describe_backend()` 多返回 `max_concurrency`。注意：LlamaIndex 的 `Settings.llm`（RAG 综合 / 规划）与嵌入请求不经 llm_client，不受限流。
- 工厂 / 辅助：`get_llm_client()`（按 `(provider, base_url, api_key)` 缓存，配置变化自动重建；`reset_llm_client()` 测试用）、`client_for_host(host)`（`ReActEngine(host=…)` / 托盘配置的显式地址：ollama 模式且与全局不同 → 专用 `OllamaClient`，否则全局）、`ollama_client()`（始终指向 `OLLAMA_BASE_URL`，bootstrap 嵌入检查用）、`available_models() -> ModelList(names, fallback, notice)`（openai 失败回退 `[LLM_MODEL]` + 「后端未提供模型列表」）、`describe_backend(check_health)`、`connection_error_hint()`、`abort_response(resp)`（跨线程 socket shutdown + close；`collaboration.llm_helper` 保留同名重导出）。
- 调用方：`react_engine._call_model`（`on_response=_track_response` 记录 `_active_response` 供 `stop()`）、`llm_helper.complete_text`、`conversation_context._default_complete`、`commit_generator._generate_ai_commit_message`、`desktop_app.OllamaWarmer / StatusMonitor`、`bootstrap.ollama_running / list_installed_models`、`model_switcher`。RAG 综合不经此模块而经 LlamaIndex（`rag_engine._setup_llm`：openai 模式 `OpenAILike(api_base=…/v1, additional_kwargs={"reasoning_effort": …})`）。

### `runtime_paths.py`
- 源码 / 打包双场景路径解析：`resource_root` / `user_data_dir` / `config_dir` / `home_file` / `logs_dir` / `app_state_dir`。
- `app_state_dir(rel)` 返回 `.cerebro/<rel>`，并在目标不存在时从旧 `.devin/<rel>` 一次性搬迁。`cwd_data_dir` 为兼容别名（语义已不相对 cwd）。
- 新增任何"程序生成的持久化数据"都走 `app_state_dir`，不要自己拼相对路径。

### `prompt_assets.py`
- 定位 `prompts/`（三层：内置 → `user_data_dir()/prompts` → `AGENT_PROMPTS_DIR`），`load_project_rules()`、`load_skills()`、`render_skills(role)`、`describe()`。
- Skill frontmatter 只支持 `key: value`、`[a, b]`、`- item` 子集，不引入 PyYAML。
- `render_skills` 拼接后受 `SKILL_MAX_CHARS` 限制并标注截断。

### `content_security.py`
- `ContentSecurityScanner`：入库文本的提示词注入检测（模式匹配 + 风险分级）。`document_loader` 在入库前调用。

## 编排层

### `intent_router.py`（F8 P3）
- `classify_intent(text, kb_available, complete) -> RouteDecision(mode, reason)`；`agent_signals` / `rag_signals` 规则先行，模糊时 `llm_classify`（`num_predict=4`, `timeout=5`），失败回退 `rag`；知识库为空且模糊 → `agent`。
- 测试中 `conftest.block_intent_llm` 拦截 `_llm_complete`，规则路径必须可独立测。

### `rag_pipeline.py`
- CLI / Web / RAGAgent 共用的问答编排：`answer_question(engine, question, *, enable_web_search, kb_only, context, progress, should_stop, …)` 返回 dict。
- 关键阶段函数：`is_meta_query` / `build_meta_overview`、`plan_retrieval`、`augment_with_web_search` / `run_web_search` / `enrich_with_page_content`、`generate_answer` / `_generate_answer_inner`、`_retrieve` / `_merge_multi_hop`、`filter_relevant_sources`、`assign_refs` / `format_kb_context` / `synthesize_prompt`、`simple_web_search`、`fallback_suggestion`、`record_conversation`。
- `answer_question` 不写会话，不做 UI；返回的 `kind` ∈ `meta | answer | fallback`。改返回结构要同步 CLI `_run_ask`、Web `format_*` 与 RAGAgent。
- 取消：`should_stop` 在阶段边界检查并抛 `PipelineCancelled`。

### `rag_rerank.py`（F8 P2）
- `rerank(question, sources, method)`：`llm`（逐片段 yes/no 判定）或 `cross-encoder`（sentence-transformers，可选依赖）；分数 ≥ `CONFIDENT_SCORE`(0.6) 的片段跳过。失败回退 `_fallback_judge` → `judge_kb_relevance`。
- 测试中 `conftest.block_rerank_llm` 拦截 `_llm_complete`。

### `react_engine.py`
- `build_system_prompt(tools, extra, mode, role)`：四层组装（内置 / Skills / 项目附加规范 / 角色说明），不落盘。`CODE_AGENT_PROMPT_MODE` 只剩 `builtin|append`。
- `ReActEngine(model, host, on_step, on_confirm, context, allowed_tools, system_prompt_extra, max_iterations, prompt_mode, role, on_token)`；`chat(task, on_token=None)` 主循环（`on_token` 只收到 `Final Answer:` 之后的增量，见 ARCHITECTURE §2.6；`stop()` 会 `abort_response` 关闭流式连接）；`_call_model` 经 `llm_client`（`self.llm_client` = `client_for_host(self.host)`，`host` 仅在 ollama 模式且与全局地址不同时生效）与鲁棒性机制（格式重试 / 重复检测 / 安全拦截 / 确认协议 / Observation 截断 / 预算折叠 / 强制总结）见 ARCHITECTURE §2.3。
- `on_step(evt)` 的 `phase` 取值：`thinking / action / blocked / rejected / executing / observed / final / format_retry / repeat / budget_fold / forced_summary / error / context`；`transient=True` 为心跳。CLI 与 Web 的进度渲染都消费它，新增 phase 要两端同步。
- `on_confirm(evt)` 收到 `{step, tool, command|args, safety?, message}`，返回 bool。无回调视为拒绝。
- `step_log` 供 CLI `/summary` 与 Web 执行摘要；`_record_turn` 只把"任务 + 最终答案 + 一句 trace"写回会话。

### `conversation_context.py`
- `ConversationContext(session_manager, session_id, *, num_ctx, ratio, recent_turns, complete)`；`session_id=None` = 跟随 manager 当前会话。
- 读：`build_messages(system_prompt)`、`history_text()`、`all_messages()`、`metrics()`、`health(question)`、`has_history()`、`carried_summary()`。
- 写：`record()`（含 `maybe_compress`）、`compact()`、`clear()`、`new_session(title, carry_summary)`、`mark_suggested()` / `continue_current()`。
- 改写：`rewrite_question()`（`is_followup` 命中才调 LLM，返回 `{question, original, changed}`）。
- 上下文状态存在 `session.metadata["context"]`（`summary / summary_covers / compressions / suggested / only_compressions / suggest_after_compressions`），改字段要考虑旧会话文件兼容。
- 单例 `get_conversation_context()` / `reset_conversation_context()` 仅 CLI 使用；测试用 `monkeypatch.setattr(cc, "_context_singleton", ctx)`。
- `migrate_legacy_history()`：旧 `~/.code_agent_history.json` 一次性迁入会话。

### `session_manager.py`
- `ChatSession` dataclass + `SessionManager(storage_path)`：`create_session`（自动设为当前）、`get_session`、`switch_session`、`save_session`、`archive_session`、`delete_session`、`list_sessions`、`search_sessions`；`current.txt` 持久化当前指针。`SmartSessionManager` 增加自动归档 / 压缩。
- 单例 `get_session_manager()`；测试用临时目录构造实例。

### `master_agent.py` / `agent_orchestrator.py` / `collaboration/`
- `AgentOrchestrator.process_request(request, mode)` → `MasterAgent.coordinate_task`：`decompose → schedule → execute → integrate`，进度 stage `decompose | decomposed | schedule | execute | agent_step | task_done | integrate`。
- 四种 `CollaborationMode` 的执行分支都在 `master_agent.py`（`_execute_sequential` / `_execute_parallel` / `_run_competitive`）；`_attach_upstream` 把上游输出（每条 ≤1500 字）放进下游 `input_data["upstream"]`。
- `collaboration/task_decomposer.py`：LLM 优先（`DECOMPOSE_PROMPT`, ≤512 token）→ 关键词表回退，`last_method` 记录用了哪种。`MAX_SUBTASKS=5`。
- `collaboration/result_integrator.py`：`INTEGRATE_PROMPT` 综合；`REVIEW_PROMPT` 供 COMPETITIVE 评审 `{"best","reason"}`，失败回退最长成功输出；`merge_sources` 合并引用。
- `collaboration/llm_helper.py`：`complete_text(prompt, num_predict, timeout, temperature, on_token=None, should_stop=None)` / `complete_json`（经 `llm_client.get_llm_client().chat`，think=False，temperature 0.2，返回值 strip）、`strip_think`、`truncate`；`consume_ndjson_stream` / `abort_response` 已迁入 `llm_client`，此处仅保留同名重导出。
- `collaboration/task_scheduler.py`：按 capability 分配（`schedule / schedule_parallel / schedule_sequential / schedule_competitive`）。`message_bus.py` 消息总线；`presenter.py` 多 Agent 结果 Markdown 渲染（CLI / Web 共用）。
- `agent_registry.py` 注册与查找 Agent；`agent_config.py` 默认配置（各角色 `specialized_tools` 即白名单）。F10 P2-1 起 `AgentRegistry.lock` / `TaskScheduler.lock` 为 `threading.RLock`（此前为 `None` 占位），读写索引表 / 任务表的方法都在 `with self.lock` 内，`__iter__` 返回快照。

### `agents/`
- `agent_types.py`：`AgentType`（master/code/rag/test/doc/audit）、`AgentTask` / `AgentResult` / `CollaborationMode`。
- `base_agent.py`：`BaseAgent`、`execute_task_with_timeout`（F10 P2-1：工作线程注册 `llm_client.QueueWaitTracker`，超时预算 = `timeout` + 在 LLM 信号量上排队的时间，`_join_excluding_queue` 每 0.25s 重算；首次排队追加 `phase="queued"` 进度行、之后 transient，结果 `metadata["queued_seconds"]`）、`EphemeralContext`、`ReActDelegateAgent`（`ROLE_PROMPT` / `ALLOWED_TOOLS` / `ESSENTIAL_TOOLS` / `TASK_TYPE_HINTS`、`_auto_confirm`、`_make_engine`、`build_prompt`、`UNVERIFIED_NOTE`、`OUTPUT_LIMIT=6000`）。`config["engine_factory"]` 供测试注入。
- `code_agent.py` / `test_agent.py`(QAExpertAgent) / `doc_agent.py` / `audit_agent.py`：只声明白名单与角色提示；改白名单要同步 `agent_config.py` 与 `tests/multi_agent/test_specialized_agents.py` 的精确集合断言。
- `rag_agent.py`：不走 ReAct，直接 `rag_pipeline.answer_question(enable_web_search=True)`；依赖全局 `agent_tools._rag_engine` 已注入。

## 能力层

### `rag_engine.py`
- `RAGEngine`：LlamaIndex + Ollama + ChromaDB（`_setup_llm` 在 `LLM_PROVIDER=openai` 时改用 `llama_index.llms.openai_like.OpenAILike`，嵌入始终 `OllamaEmbedding`）；`build_index` / `load_index` / `add_documents` / `remove_file` / `query`；hybrid（BM25 + RRF，`RAG_HYBRID`）；`progress_callback` 事件。三条入库路径共用 `node_parser`（`load_index()` 曾漏设切分器）。
- hybrid 的 BM25 侧（F10 P2-1）：`bm25_store` 属性惰性创建 `BM25Store(index_dir / "bm25")` 并 `load()`；`_bm25_after_ingest(nodes)`（入库后按节点 id 增量 `upsert` + 落盘；`nodes is None` 的回退路径 → `mark_stale`）、`_bm25_after_remove(path)`、`_bm25_after_clear()`；`_ensure_bm25()`：store 可用且片段数与 Chroma `count()` 一致 → 直接 `build()`，否则 `_bm25_full_rebuild`（唯一会 `collection.get(include=["documents","metadatas"])` 全量拉取的地方，用于旧库迁移 / 损坏 / 版本不匹配 / 条数不一致）。`self._bm25` 只是"已就位"缓存标记（`{"store": …}`），`invalidate_bm25()` 只清标记不触发全量。`hybrid_status()` / `hybrid_limit_reason()` 给 `get_stats()`（`hybrid` / `hybrid_max_chunks` / `hybrid_disabled_reason` 三键）与 `query_with_sources()["meta"]["hybrid_disabled_reason"]` 用；`_bm25_tokenize` 仅委托 `bm25_store.tokenize`。

### `bm25_store.py`（F10 P2-1）
- `BM25Store(persist_dir)`：BM25 语料的持久化增量存储，文件 `store.json.gz`（`{schema_version, tokenizer_version, docs: {chunk_id: {tf, len, metadata}}}`，gzip 级别 1）。内存只保留每片段的**词频字典**（token 经 `sys.intern` 跨片段共享）与词数，`_df` 随增删维护；`build()` 用这些字典直接装配 `BM25Okapi`（`doc_freqs` 共享同一批 dict，不复制；装配失败回退标准构造），分数与 `BM25Okapi(token_lists)` 逐位一致。
- API：`load()`（缺文件 / 版本不匹配 / 损坏都返回 False 并清空，损坏打 warning、`load_error` 记原因）、`save()`（临时文件 + `os.replace` 原子写）、`save_if_dirty()`、`upsert / upsert_many / remove / remove_many / remove_where(pred(doc_id, meta)) / replace_all / clear`、`mark_stale()`（调用方拿不到 chunk id 时标记，下次全量）、`is_usable()`、`search(query, top_k) -> [(doc_id, meta, score)]`、`describe()`。
- **改 `tokenize` 的任何逻辑必须递增 `TOKENIZER_VERSION`**（旧 store 的词频与新查询分词不一致；版本不匹配时引擎自动全量重建并重写）。`rag_engine.RAGEngine._bm25_tokenize` 与 `rag_pipeline` 的实体子词匹配都依赖同一分词。
- 测试：`tests/test_bm25_store.py`（单元）、`tests/test_rag_engine_bm25_store.py`（与 `RAGEngine` 集成，假 Chroma 集合 + `tmp_path` persist_dir）；`tests/conftest.py::isolate_bm25_store` 把 `rag_engine.INDEX_DIR` 重定向到临时目录，避免 Mock Chroma 的测试写真实 `index_storage/bm25/`。
- `document_loader.py`：多格式加载（PDF / MD / TXT / 代码 / 图片 OCR），入库前 `content_security` 扫描与 `file_validator` 校验；代码文件走 `code_chunker`（tree-sitter 按函数 / 类切分，F8 P4）。
- `file_metadata.py`：入库文件元数据（分类 / 大小 / hash / `chunk_strategy` / `symbol_count`），持久化到 `app_state_dir("file_metadata")`；`from_dict` 忽略未知键以兼容旧文件。全局单例 `_global_metadata_manager`（测试隔离）。
- `knowledge_snapshot.py`：快照创建 / 恢复 / 清理，目录 `app_state_dir("knowledge/snapshots")`。
- `knowledge_to_skills.py`：把知识库转为 opencode / Claude skills（输出到 `~/.config/opencode/skills` 等，与 `prompts/skills` 无关）。

### `agent_tools.py`
- `ToolRegistry`（`register / get_descriptions(names, compact) / execute(name, args, auto_confirm)`）与 28 个工具；`CommandSafetyChecker` 四级分级；写路径边界 `write_allowed_dirs()` / `is_path_allowed()`。详见 [TOOL_USAGE.md](TOOL_USAGE.md)。
- 全局 `_rag_engine` 由入口注入（`set_rag_engine`）；多 Agent 运行前必须已注入。

### `web_search/`
- `search_engine.py`：`DuckDuckGoSearchEngine`（ddgs，多后端）/ `BaiduSearchEngine` / `WikipediaSearchEngine` + 聚合与降级（`WEB_SEARCH_*` 配置）；`result_processor.py` 去重 / 排序 / 格式化；`content_extractor.py` trafilatura → requests+bs4 回退；`search_cache.py` TTL 缓存。

### `knowledge_graph/`
- `entity_extractor.py`（规则 + LLM）、`graph_builder.py`（networkx；`add_document` / `remove_document` / `query` / `subgraph_for_view` / `layout_positions`；持久化 `app_state_dir("knowledge/graph.json")`，`clear(persist=False)` 默认不落盘；`set_default_persist_path` 供测试）、`graph_query.py`（实体 / 邻居 / 路径查询）。

### `code_analyzer/` · `database_tools/` · `git_integration/`
- `ast_analyzer.py`（stdlib ast 搜索函数 / 类 / 变量）、`quality_checker.py`（pylint / bandit / radon 子进程，缺工具时降级）。
- `db_connector.py` / `query_executor.py`（含 `list_tables`）/ `sql_generator.py`：SQLite 为主。`session.py` 进程级「当前连接」（`set_current / get_current / clear_current / resolve / current_connector`，按 `(db_type, database)` 复用连接器；Web / CLI / Agent 三端共用）。`results.py` 结构化取数（`query_structured / execute_structured / tables_structured / table_schema_structured / schema_rows / sql_kind`，以 `QueryExecutor | None` 为输入），Web `WebService.db_*` 与 CLI `/db-query` `/db-schema` 都调它（F9）。
- `git_analyzer.py`（`subprocess git`，非 gitpython）：历史 / 状态 / 作者统计，`get_overview(max_commits)` 供 Web 仪表盘与 CLI `/git-analyze` 表格共用；`get_commit_preview()`（暂存文件 / `diff --cached --stat` / 增删行数）与 `commit(message)`（仅提交暂存区，返回 `ok / hash7 / subject / error`）供 Web 一步提交（F9 P3）。`commit_generator.py`：AI 生成提交信息（经 `llm_client` chat 消息格式，`think=False` + `num_predict=256` + 60s 超时，HTTP 非 200 / 超时 / 空响应回退规则生成；`ollama_base_url` 参数仅为兼容保留）。

### `ocr_processor/`
- `base.py` 抽象 → `tesseract_ocr.py`（默认）/ `paddle_ocr.py`；`preprocessor.py`（去噪 / 二值化 / 纠偏）、`image_extractor.py`（PDF 内嵌图）、`cache.py`（按内容 hash 缓存）。依赖不在 requirements 中，缺失时 `document_loader` 降级为跳过图片。

### `command_recommender/`（F4，仅 CLI）
- `engine.py` 混合推荐（规则 + 工作流 + 学习），`workflow.py` / `state.py` / `history.py` / `learning.py` / `context.py` / `display.py`；偏好存 `data/recommender_preferences.json`。桌面 / Web 不集成。

## 入口层

### `query_interface.py` / `cli/`（F10 P2-2 拆包）
- `cli/parser.py`：`parse_command()` → `ParsedCommand(cmd_type, raw, arg)`、`classify_mode()`（纯函数）；`query_interface` 重导出三者。
- `cli/help_text.py`：`TUTORIAL_TEXT`、`print_help(console, has_rich)`（`/help` 文案内联在函数体内，`inspect.getsource` 可校验）；`query_interface.print_help()` 为零参包装（读模块级 `console` / `HAS_RICH`）。
- `cli/handlers/`：`base.py`（`CLIContext` dataclass、`_is_error` / `_confirm(…, safety=)` / `_sql_safety`、`LiveAnswer`）、`agent.py`（`/multi`）、`system.py`（`/help /tutorial /tools /config`，`config_rows`）、`knowledge.py`（`/stats /sources /add /generate-skills /snapshot-* /knowledge-summary`）、`files.py`（`/file-*`）、`session.py`（`/session-* /context /compact`）、`tools.py`（`/web-* /code-* /graph-*`）、`git.py`（`/git-*`，`_rich_table`）、`db.py`（`/db-*`）；`__init__.py` 汇总 `COMMAND_HANDLERS` 并重导出全部名字。顶层 `cli_handlers.py` 只剩兼容重导出。
- `query_interface.py` 保留：解释器自保护、日志 / 控制台、回调、渲染（`print_rag_sources` 等）、共享 RAG 编排适配、引擎耦合命令（`_ENGINE_HANDLERS`：ask / agent / natural / model / think / exec …）、`dispatch_command`、`main`。分发：`_ENGINE_HANDLERS` → `cli.handlers.COMMAND_HANDLERS`。
- 模块级全局 `react_engine` / `rag_engine` / `console`；测试用 `patch("query_interface.console")` 与 `conftest.reset_module_state`。**打桩 handler 内部依赖须以实际子模块为目标**（如 `cli.handlers.git._git_overview`、`cli.handlers.db._db_results`、`cli.handlers.session._get_session_manager`），patch `cli_handlers.X` 不再生效。

### `web/`
- `services/`（F10 P2-2 拆包）`WebService = ChatMixin + KnowledgeMixin + ToolsMixin + DatabaseMixin + GraphMixin + SystemMixin + WebServiceBase`：`base.py` 含引擎工厂 `_default_*`、`ScratchContext`、`StreamEvent`、`WebServiceBase`（工厂注入、`is_running / stop_current`、交互式确认 `pending_confirm / resolve_confirm / _ask_confirm`、`_token_sink`、`_bridge`、`rag_engine / session_manager / graph_query` 惰性单例）；`chat.py`（会话上下文、`rag_query_stream / agent_chat_stream / chat_auto_stream / multi_agent_stream`、会话管理与会话高级）；`knowledge.py`（入库 / 统计 / 文件管理 / 摘要与技能 / 快照，含 `_describe_chunking`）；`tools.py`（`run_tool`、代码助手 / 符号 / 质量、Git、AI 解读、Shell / 文件读写、工作区浏览、命令生成、`cwd / chdir`）；`db.py`（SQLite 连接 / 查询 / 写 / NL→SQL）；`graph.py`（图谱查询 / 构建 / 可视化数据）；`system.py`（模型热切换 / 思考模式 / `env_info`，含 `_code_chunking_env_text`）。流式统一经 `_bridge`（后台线程 + 队列 → `StreamEvent(kind, message, data)`，kinds `progress | answer | step | token | error | done | heartbeat | cancelled | confirm`）。`__init__.py` 重导出全部旧公开名与单例 `get_web_service()` / `reset_web_service()`；`from web.services import WebService` 路径不变。
- `formatters.py`：全部 `format_*` / `*_rows` / 表头常量 / `ProgressTracker` / `component_update` / `_fmt_result` / `build_graph_figure` 等纯函数（可单测）。
- `handlers/`：`build_chat_handlers`（对话 / 流式 / 审批 / 会话控件 / 会话页 / 侧栏）、`build_knowledge_handlers`（入库流 / 卡片 / 文件 / 快照 / 摘要）、`build_tools_handlers`（Git / DB / AI 解读 / 代码 / NL→SQL / 工作区 / 命令生成 / Shell）、`build_graph_handlers`、`build_system_handlers`（模型 / 网络缓存 / 环境 / 工具表 / 模型表）；各返回 dict，带表头的组附 `"headers"` 子字典。
- `app.py`：`build_handlers(service)` 汇总五组并合并 `headers`（返回结构与拆包前完全一致）+ `build_app / serve_blocking / launch / main`；重导出 `formatters` 全部名字。`on_chat_stream` yield 八元组，`session_id` 为空时先 `ensure_session()` 钉死。
- `ui/layout.py` 骨架与侧栏（`session_state = gr.State("")` 每标签页一份）；`ui/chat.py` 对话页事件链（`_begin → _chat_stream_ui → _end`，`_end` 把实际会话 id 写回 `session_state`）；`ui/knowledge.py` / `graph.py` / `tools.py` / `system.py` 各页；`ui/common.py` 二步确认按钮等复用件；`theme.py` 主题。
- `tools_state.py` `ToolsState`：工具页轻量持久状态（最近数据库 ≤8 / 命令历史 ≤50，`.cerebro/web_tools_state.json` 经 `runtime_paths.app_state_dir`；损坏 JSON 回退空）。`WebService.tools_state` 惰性持有，测试直接赋值指向 `tmp_path` 的实例。
- `ui/tools.py` 工具页：`_result_actions`（结果流转行）、`_empty_note / _vis_empty`（表格空态）、`_lock / _locked`（长任务锁按钮；单输出组件须返回标量 `gr.update`）。Gradio 惰性渲染子页：对未渲染子页内 Markdown 的 `visible` 更新会丢失，需在 `tab.select` 时重同步。
- `ui/*` 不做单元测试（covered 排除），改动后需手动启动验证。

### `desktop_app.py`
- 托盘 + 自启动 + 模型预热 + 启动 Web 子进程（需剔除 `_MEIPASS2` / `_PYI_*` 环境变量）+ 状态监控。
- `OllamaWarmer.warm_up`：对话模型经 `llm_client.chat`（`num_predict=1`），嵌入模型仍直连 Ollama `/api/embed`；`check_service` → `LLMClient.health`。`StatusMonitor.check_status` → `LLMClient.list_models`（状态键 `ollama_service` 保持不变，另加 `provider`）。

### `bootstrap.py` / `model_switcher.py`
- `bootstrap`：`ollama_running` / `list_installed_models` 经 `llm_client.OllamaClient(OLLAMA_BASE_URL)`；`ensure_ollama_ready` 在 `LLM_PROVIDER=openai` 时走 `_ensure_openai_backend_ready`（只探测后端 health、提示嵌入模型是否就绪，不安装、不拉取）。
- `model_switcher`：`list_installed_models` 按 provider 分流（ollama → bootstrap；openai → `available_models`），`models_notice()` 给两端展示回退提示；`switch_model` 在 openai 且后端无列表时放行任意名字并在消息里注明「未校验」；`unload_model` / `list_loaded_models`（`/api/ps`）为 Ollama 专有，openai 模式不调用；`current_model_info` 多返回 `provider` / `base_url`。

## 改动前的最小检查

1. 该模块被谁调用？（`grep -rn "from <module> import"`，CLI / Web / Agent 三端往往都要同步）
2. 有没有全局单例或模块级状态？测试是否已有隔离 fixture？
3. 输出结构（dict 字段 / 事件 phase / 返回前缀标记）被哪些渲染层消费？
4. 路径是否走 `runtime_paths`？打包场景是否成立？
