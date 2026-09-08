# 模块指南

按目录分组说明每个模块的职责、关键函数与改动时的注意点。行号会漂移，以函数名为锚点。整体分层见 [ARCHITECTURE.md](ARCHITECTURE.md)。

## 基础层

### `config.py`
- 把 `.env` / 环境变量解析为模块级常量，并提供兼容的 `Config` dataclass（`Config.LLM_MODEL`、`Config.MAX_ITERATIONS`、`Config.AUTO_CONFIRM`、`Config.AUTO_ROUTE` …）。
- 运行时可变项有 setter：`set_llm_model()`、`set_llm_think()`（CLI `/model` `/think` 与 Web 模型页调用）。
- `resolve_num_ctx(model)`：按参数量推导安全上下文窗口（≤4B→16384，7–9B→8192，≥12B→4096），`LLM_NUM_CTX` 可覆盖。
- 两个阈值不要混：`SIMILARITY_CUTOFF`(0.3) 是底层召回保护，`KB_RELEVANCE_THRESHOLD`(0.45) 是编排层"命中"判定。
- `READONLY_COMMANDS` / `DANGEROUS_PATTERNS` **无人引用**；命令安全规则在 `agent_tools.CommandSafetyChecker`。

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
- `ReActEngine(model, host, on_step, on_confirm, context, allowed_tools, system_prompt_extra, max_iterations, prompt_mode, role)`；`chat(task)` 主循环与鲁棒性机制（格式重试 / 重复检测 / 安全拦截 / 确认协议 / Observation 截断 / 预算折叠 / 强制总结）见 ARCHITECTURE §2.3。
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
- `collaboration/llm_helper.py`：`complete_text` / `complete_json`（`/api/chat`, think=False, temperature 0.2）、`strip_think`、`truncate`。
- `collaboration/task_scheduler.py`：按 capability 分配（`schedule / schedule_parallel / schedule_sequential / schedule_competitive`）。`message_bus.py` 消息总线；`presenter.py` 多 Agent 结果 Markdown 渲染（CLI / Web 共用）。
- `agent_registry.py` 注册与查找 Agent；`agent_config.py` 默认配置（各角色 `specialized_tools` 即白名单）。

### `agents/`
- `agent_types.py`：`AgentType`（master/code/rag/test/doc/audit）、`AgentTask` / `AgentResult` / `CollaborationMode`。
- `base_agent.py`：`BaseAgent`、`execute_task_with_timeout`、`EphemeralContext`、`ReActDelegateAgent`（`ROLE_PROMPT` / `ALLOWED_TOOLS` / `ESSENTIAL_TOOLS` / `TASK_TYPE_HINTS`、`_auto_confirm`、`_make_engine`、`build_prompt`、`UNVERIFIED_NOTE`、`OUTPUT_LIMIT=6000`）。`config["engine_factory"]` 供测试注入。
- `code_agent.py` / `test_agent.py`(QAExpertAgent) / `doc_agent.py` / `audit_agent.py`：只声明白名单与角色提示；改白名单要同步 `agent_config.py` 与 `tests/multi_agent/test_specialized_agents.py` 的精确集合断言。
- `rag_agent.py`：不走 ReAct，直接 `rag_pipeline.answer_question(enable_web_search=True)`；依赖全局 `agent_tools._rag_engine` 已注入。

## 能力层

### `rag_engine.py`
- `RAGEngine`：LlamaIndex + Ollama + ChromaDB；`build_index` / `load_index` / `add_documents` / `remove_file` / `query`；hybrid（BM25 + RRF，`RAG_HYBRID`）；`progress_callback` 事件。三条入库路径共用 `node_parser`（`load_index()` 曾漏设切分器）。
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
- `git_analyzer.py`（`subprocess git`，非 gitpython）：历史 / 状态 / 作者统计，`get_overview(max_commits)` 供 Web 仪表盘与 CLI `/git-analyze` 表格共用；`get_commit_preview()`（暂存文件 / `diff --cached --stat` / 增删行数）与 `commit(message)`（仅提交暂存区，返回 `ok / hash7 / subject / error`）供 Web 一步提交（F9 P3）。`commit_generator.py`：AI 生成提交信息（`/api/generate`，`think=False` + `num_predict=256`，失败回退规则生成）。

### `ocr_processor/`
- `base.py` 抽象 → `tesseract_ocr.py`（默认）/ `paddle_ocr.py`；`preprocessor.py`（去噪 / 二值化 / 纠偏）、`image_extractor.py`（PDF 内嵌图）、`cache.py`（按内容 hash 缓存）。依赖不在 requirements 中，缺失时 `document_loader` 降级为跳过图片。

### `command_recommender/`（F4，仅 CLI）
- `engine.py` 混合推荐（规则 + 工作流 + 学习），`workflow.py` / `state.py` / `history.py` / `learning.py` / `context.py` / `display.py`；偏好存 `data/recommender_preferences.json`。桌面 / Web 不集成。

## 入口层

### `query_interface.py` / `cli_handlers.py`
- `parse_command()` → `ParsedCommand(cmd_type, raw, arg)`；分发：`_ENGINE_HANDLERS`（依赖引擎状态）+ `cli_handlers.COMMAND_HANDLERS`（表驱动）。
- `handle_natural` → 自动路由；`_run_ask`（RAG + 会话）；`handle_agent`；`cli_handlers.handle_multi`；会话命令 `handle_session_*`；模型 `/model` `/think`。
- 模块级全局 `react_engine` / `rag_engine` / `console`；测试用 `patch("query_interface.console")` 与 `conftest.reset_module_state`。

### `web/`
- `services.py` `WebService`：所有业务入口（对话流 / 模型 / 知识库 / 会话 / 图谱 / 工具），流式统一经 `_bridge`（后台线程 + 队列 → `StreamEvent(kind, message, data)`，kinds `progress | answer | step | error | done | heartbeat | cancelled`）。构造参数全部可注入工厂。单例 `get_web_service()` / `reset_web_service()`。
- `app.py`：`format_*` 纯函数（可单测）+ `build_handlers(service)`（返回 handler dict，可单测）+ `build_app / launch / main`（`pragma: no cover`）。`on_chat_stream` yield 七元组，`session_id` 为空时先 `ensure_session()` 钉死。
- `ui/layout.py` 骨架与侧栏（`session_state = gr.State("")` 每标签页一份）；`ui/chat.py` 对话页事件链（`_begin → _chat_stream_ui → _end`，`_end` 把实际会话 id 写回 `session_state`）；`ui/knowledge.py` / `graph.py` / `tools.py` / `system.py` 各页；`ui/common.py` 二步确认按钮等复用件；`theme.py` 主题。
- `tools_state.py` `ToolsState`：工具页轻量持久状态（最近数据库 ≤8 / 命令历史 ≤50，`.cerebro/web_tools_state.json` 经 `runtime_paths.app_state_dir`；损坏 JSON 回退空）。`WebService.tools_state` 惰性持有，测试直接赋值指向 `tmp_path` 的实例。
- `ui/tools.py` 工具页：`_result_actions`（结果流转行）、`_empty_note / _vis_empty`（表格空态）、`_lock / _locked`（长任务锁按钮；单输出组件须返回标量 `gr.update`）。Gradio 惰性渲染子页：对未渲染子页内 Markdown 的 `visible` 更新会丢失，需在 `tab.select` 时重同步。
- `ui/*` 不做单元测试（covered 排除），改动后需手动启动验证。

### `desktop_app.py`
- 托盘 + 自启动 + 模型预热 + 启动 Web 子进程（需剔除 `_MEIPASS2` / `_PYI_*` 环境变量）+ 状态监控。

## 改动前的最小检查

1. 该模块被谁调用？（`grep -rn "from <module> import"`，CLI / Web / Agent 三端往往都要同步）
2. 有没有全局单例或模块级状态？测试是否已有隔离 fixture？
3. 输出结构（dict 字段 / 事件 phase / 返回前缀标记）被哪些渲染层消费？
4. 路径是否走 `runtime_paths`？打包场景是否成立？
