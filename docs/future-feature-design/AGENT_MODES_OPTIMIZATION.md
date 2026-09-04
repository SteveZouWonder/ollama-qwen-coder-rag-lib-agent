# F8: 三种对话模式优化需求（RAG 检索 / 单 Agent / 多 Agent）

> 功能编号：F8 · 状态：待实现 · 分支 `feat/agent-modes-optimization` · 目标：提升任务质量、回答准确度与智能程度
> 启动提示词见 [AGENT_MODES_OPTIMIZATION_PROMPT.md](AGENT_MODES_OPTIMIZATION_PROMPT.md)

## 0. 背景（已核实的代码事实，实施时勿重复调研）

| 模式 | 入口 | 现状 | 关键位置 |
|---|---|---|---|
| RAG 检索（默认） | CLI `/ask` 与无斜杠输入；Web「RAG 检索」 | 单趟管道：规则元查询 → 追问改写(LLM, `think=False`) → 搜索规划(LLM→JSON) → 1 次 dense 检索(top-10, cutoff 0.3, `compact`) → 阈值 0.45 + 一词相关性判定(LLM) → 0/1 次综合(LLM)。无 rerank/多跳/分解/自校验；`/think on` 的思维链被丢弃 | `src/rag_pipeline.py:919-1018`（`answer_question`）、`:703-752`（综合 prompt）、`:570-624`（相关性判定）、`src/rag_engine.py:430-440, 502-554` |
| 单 Agent（ReAct） | CLI `/agent`；Web「单 Agent」 | 真正的 Thought→Action→Observation 循环，29 个工具，危险命令拦截 + 确认 | `src/react_engine.py:322-477`（循环）、`:515-531`（`_call_model`）、`:178-187`（系统提示选择）、`src/agent_tools.py`（registry / `CommandSafetyChecker :74-135`） |
| 多 Agent | 仅 Web「多 Agent 协作」 | 骨架完整但 4/5 Agent 为硬编码桩返回伪造数据；分解为关键词匹配；PARALLEL 实际串行；COMPETITIVE 选最快 | `src/master_agent.py:114-259`、`src/collaboration/{task_decomposer,task_scheduler,result_integrator}.py`、`src/agents/*.py`、`src/agent_orchestrator.py`、`src/agent_config.py` |

### 0.1 单 Agent 已确认的缺陷
1. 实际生效的系统提示是 `.devin/SYSTEM_PROMPT.md`（390 行，≈6.2K token，占 16K ctx 40%），内容为本机开发规范：要求读 `~/.config/devin/*.md`、覆盖率 ≥95%、使用不存在的 `todo_write` 工具。内置 `SYSTEM_PROMPT_TEMPLATE`（`react_engine.py:109-175`）仅作回退。
2. 模型输出无 `Action`/`Final Answer`、或 `Action Input` 非合法 JSON、或 `_call_model` 返回 `[错误] ...` 时，整段文本被当作最终答案返回并 `_record_turn` 写入会话（`react_engine.py:462-473, 535-540`）。
3. `MAX_ITERATIONS=50` 耗尽只返回固定警告，丢弃全部中间结果（`:475-477`）。
4. 无相同 Action+Input 重复检测。
5. 历史部分有预算（`num_ctx×0.30`，`conversation_context.py:264-267, 420-425`），但本轮 ReAct 往返（≤50 步 × ≤5000 字符 Observation，`agent_tools.py:65`）无截断/折叠。
6. `query_knowledge_base` → `rag_engine.query_tool`（`:558-576`）：裸 LlamaIndex 检索（cutoff 0.3，无 0.45 阈值、无联网回退），只回"综合答案 + ≤3 文件名"，无原文片段；与 RAG 模式/RAGAgent 行为不一致（`agents/rag_agent.py:90-93` 注释已指出）。
7. `CommandSafetyChecker`：`python x.py`、`pip/npm install`、`git push/commit` 等落入默认 `low` 免确认（`agent_tools.py:131-133`）；`write_file` 无路径边界（`:158-170`）。

### 0.2 多 Agent 已确认的缺陷
1. `agents/code_agent.py:82-103,124-143`、`test_agent.py:86-90,134-137`、`doc_agent.py:86-113`、`audit_agent.py`：固定假文本且 `success=True`。
2. `collaboration/task_decomposer.py:60-134`：关键词表；每个子任务 `input_data={"request": 原请求}`；`master_agent.py:140` 进度文案却写"分解任务（模型推理）"。
3. `master_agent.py:219-250` 单一串行 for 循环服务所有模式；`result_integrator.py:145` `integrate_parallel = integrate`；`:199-203` COMPETITIVE 按最短耗时选优。
4. `agents/base_agent.py:128-161`：`execute_task_with_timeout` 不做超时；失败后 `ERROR` 状态无恢复。`agent_config.py` 的 model/timeout/max_iterations/specialized_tools 未传给实例（`agent_orchestrator.py:80-88`）。
5. 结果 `summary` 为统计句（`result_integrator.py:59-83`），会话只记该句（`web/services.py:723-727`）；来源以文本混在 RAGAgent `output`（`rag_agent.py:123-134`），无结构化字段；Web `format_multi_agent_result`（`web/app.py:252-274`）不处理 COMPETITIVE 的 `best_result` 结构。CLI 无多 Agent 入口。
6. `rag_agent.py:87-138` 调 `answer_question` 未传 `context`。

### 0.3 路由与模型
- `query_interface.py:975-1019` `classify_mode`：无斜杠输入 → 引擎可用即 `rag`，无意图判定；Web 默认 RAG（`web/ui/chat.py:47`）。
- 默认模型 `qwen3.5:4b`，`resolve_num_ctx`：≥12B→4096，≥7B→8192，其余→16384（`config.py:57-94`）；`LLM_THINK` 默认 false。
- 会话上下文层 `src/conversation_context.py`：`ConversationContext.rewrite_question/history_text/build_messages/record`；`_default_complete :175-203` 直连 `/api/chat`。

### 0.4 工程约束（沿用现有规范）
- 测试：`./venv/bin/python -m pytest -q -n 4`，全量覆盖 ≥80%；新逻辑必须有单测（Mock Ollama/Chroma，模式见 `tests/test_react_engine.py`、`tests/test_rag_pipeline.py`、`tests/multi_agent/`、`tests/test_web_services.py`）。
- Web 服务层 `src/web/services.py` 是唯一接引擎处；`src/web/app.py` 的 `format_*`/`build_handlers` 可单测；`src/web/ui/*` 标 `# pragma: no cover`。
- CLI：`query_interface.py::parse_command/classify_mode/print_help/TUTORIAL_TEXT` + `cli_handlers.py::COMMAND_HANDLERS`。
- 每阶段完成更新 `CHANGELOG.md [Unreleased]`、README 对应段落、`docs/future-feature-design/README.md` 状态。
- Git：不得直接提交 master；改动前确认分支；完成后询问是否建 PR，不得自动建 PR。

---

## 1. P0 · 多 Agent 重做为真实 Agent（方案 A）

### 目标
多 Agent 模式输出的每一条结果都来自真实的模型/工具执行；用户可见的每个阶段文案与实现一致。

### 需求
- **P0-1 专业 Agent 委托 ReActEngine**：Code/Test/Doc/Audit 四个 Agent 的 `process_task` 改为构造一个 `ReActEngine`（接受注入 `system_prompt_extra` 与 `allowed_tools` 参数，见 P1-1）执行子任务，返回真实答案；删除所有硬编码假数据。角色附加提示 ≤200 token，各自限定工具集：
  - Code：read_file/write_file/execute_command/list_directory/search_files/ast_search/analyze_project_structure/get_current_dir
  - Test：read_file/write_file/execute_command/search_files/code_quality_check
  - Doc：read_file/write_file/list_directory/search_files/query_knowledge_base/web_search
  - Audit：read_file/search_files/code_quality_check/ast_search/git_analyze/execute_command（只读）
  - RAG：保留 `answer_question` 路径，补传 `context`；`document_search/knowledge_extraction/literature_review` 三类桩改为 `answer_question` 的变体 prompt 或直接归并到 `knowledge_retrieval`。
- **P0-2 LLM 任务分解**：`TaskDecomposer.decompose` 先调用一次 LLM（`think=False`，`num_predict≤512`），输出 JSON：`{"subtasks":[{"type":"code_generation|testing|documentation|knowledge_retrieval|audit|general","description":"...","depends_on":[idx...]}]}`；每个子任务 `input_data.request` 为**该子任务的独立描述**，另带 `original_request`。解析失败/超时回退现有关键词表。单一意图请求（如纯问答）必须只产生 1 个子任务，避免"检查一下这个 PDF 的价格"触发 audit。
- **P0-3 LLM 结果整合**：`ResultIntegrator.integrate*` 在统计之上增加一次 LLM 综合（输入各子任务描述 + 输出，截断到预算），产出面向用户的 `answer` 字段；`summary` 保留统计句。会话记录 `answer` 而非 `summary`（`web/services.py` 多 Agent 路径）。
- **P0-4 真并行**：PARALLEL 用 `ThreadPoolExecutor(max_workers=orchestrator.max_parallel_tasks)` 执行无依赖子任务；`execute_task_with_timeout` 真正按 `task.timeout` 超时（线程 + 取消信号，超时返回 `success=False, error="timeout"`）；Agent 失败后状态恢复为 IDLE。
- **P0-5 COMPETITIVE 选优**：由 LLM 评审各候选（评分 JSON `{"best": idx, "reason": "..."}`），失败回退"最长成功输出"而非最短耗时；`selection_criteria` 字段如实描述。
- **P0-6 结构化来源与展示**：`AgentResult` 增加 `sources: List[dict]`（RAGAgent 填 kb/web 来源）；整合结果暴露 `sources` 合并列表；`web/app.py::format_multi_agent_result` 渲染 `answer` + 各 Agent 摘要 + 来源，并兼容 COMPETITIVE 的 `best_result/all_results`。
- **P0-7 配置生效**：`agent_orchestrator` 把 `AgentConfig.model/timeout/max_iterations` 传入实例；`specialized_tools` 改为上面的真实工具名白名单。
- **P0-8 文案与 CLI**：进度文案如实（"分解任务（模型推理）"仅在真的调 LLM 时显示，回退时显示"分解任务（规则回退）"）；新增 CLI `/multi <任务> [--mode hierarchy|parallel|sequential|competitive]`，输出与 Web 一致，并接入 `classify_mode`/help/tutorial。

### 验收
- `tests/multi_agent/` 用 Mock LLM 覆盖：分解 JSON 解析与回退、并行执行与超时、竞争评审与回退、整合 answer/sources、ERROR 恢复；桩文本（`generated_function`、"覆盖率: 85%"）在 `src/` 中零命中。
- Web 多 Agent 一次"写一个快速排序并写测试"任务：Code 与 Test Agent 各自有真实 ReAct 步骤日志，结果面板显示综合回答与来源。

---

## 2. P1 · 单 Agent 鲁棒性与上下文

- **P1-1 系统提示分层**：`build_system_prompt(tools, extra=None)` = 精简内置模板（目标 ≤1.5K token，保留输出协议、格式规则、工具速查、安全规则）+ 可选项目附加规范。`.devin/SYSTEM_PROMPT.md` 改为**追加**（且截断到 `SYSTEM_PROMPT_EXTRA_MAX_CHARS`，默认 4000）而非替换；提供 `CODE_AGENT_PROMPT_MODE=builtin|append|replace` 环境变量（默认 `append`）。清理 `.devin/SYSTEM_PROMPT.md` 中对 `todo_write`、`~/.config/devin/*`、`execute_command` 跑斜杠命令的错误指引。`ReActEngine.__init__` 新增 `allowed_tools: Optional[set]`（工具描述与可执行集合同时过滤）与 `system_prompt_extra: str`。
- **P1-2 协议容错**：解析失败（无 Action 且无 Final Answer / Action Input 非 JSON 对象 / 未知工具）→ 回灌 `Observation: [格式错误] ...请严格按协议重新输出` 最多 `MAX_FORMAT_RETRIES=2` 次，之后把最后一段文本作为答案但标注"（格式异常，可能不完整）"；`_call_model` 返回 `[错误]` 时抛出/直接返回错误，不 `_record_turn`。
- **P1-3 步数耗尽强制总结**：达到 `MAX_ITERATIONS` 时追加一条 user 消息"步数已用尽，请基于以上 Observation 总结：已完成/未完成/建议"，再调一次模型作为最终答案（前缀"⚠️ 未完成"）。
- **P1-4 重复检测**：维护 `(tool, canonical_json(args))` 计数；连续第 2 次相同 → 回灌"该调用与上一步完全相同且已有结果，请换方法或给出答案"；第 3 次 → 触发 P1-3 总结并结束。
- **P1-5 本轮预算**：`ReActEngine` 计算 `turn_budget = num_ctx - system_tokens - history_tokens - reserve(num_predict)`；Observation 超过 `OBSERVATION_MAX_CHARS`（默认 3000）截断并注明；当本轮消息估算 token 超 `turn_budget` 时，把最早的 N 步 Observation 折叠为一行摘要"（第 k 步 tool=x 结果已折叠，要点：前 200 字）"，始终保留系统提示与最近 3 步完整。复用 `conversation_context.estimate_tokens`。
- **P1-6 知识库工具对齐**：`query_knowledge_base` 改走 `rag_pipeline.answer_question(engine, q, enable_web_search=False, show_progress=False)`（沿用 0.45 阈值与相关性判定），返回给模型："答案 + 相关性结论 + top-3 片段原文（每条 ≤300 字，含文件名）"；不相关时明确返回"[知识库无相关内容]"，以便模型转 web_search。
- **P1-7 安全分级补洞**：`CommandSafetyChecker` 新增 medium 规则：`pip|pip3|npm|yarn|pnpm|brew|apt(-get)? install`、`git (push|commit|reset|checkout|rebase|merge)`、`python[3]? \S+\.py`、`node \S+\.js`、`make`、`docker run|exec`、`curl|wget .* \| *(sh|bash)`→high；`write_file`/`add_to_knowledge_base` 路径必须解析后位于 `os.getcwd()` 或 `Config.WRITE_ALLOWED_DIRS`（env，冒号分隔）内，否则返回 `[错误] 路径超出允许范围`。
- **P1-8 观测**：`step_log` 记录 `format_retry/repeat/budget_fold/forced_summary` 事件；Web「处理过程」与 CLI 进度显示这些事件；CLI `/summary` 同步。

### 验收
- `tests/test_react_engine.py` 新增：分层提示（builtin/append/replace + 截断）、`allowed_tools` 过滤、格式重试 2 次后收尾、`[错误]` 不入会话、步数耗尽总结、重复检测、预算折叠（用小 num_ctx 触发）、知识库工具对齐（Mock `answer_question`）；`tests/test_agent_tools_safety.py` 覆盖新分级与路径边界。
- 系统提示 token 估算（`estimate_tokens`）在 builtin 模式 ≤1.5K。

---

## 3. P2 · RAG 推理与可核验性

- **P2-1 逐片段相关性筛选（rerank）**：新增 `src/rag_rerank.py`：
  - 默认 `Reranker="llm"`：一次 LLM 调用对 top-k 片段输出 JSON `{"keep":[idx...],"notes":{"idx":"一句理由"}}`（`think=False`，片段各截 400 字）；
  - 可选 `Reranker="cross-encoder"`：`sentence-transformers` + `BAAI/bge-reranker-v2-m3`（可选依赖，`requirements.txt` 注释块 + `RERANKER=cross-encoder`、`RERANKER_MODEL` 环境变量；未安装自动回退 llm）；
  - 替换 `judge_kb_relevance` 一词判定；进度事件 `rerank`；保留 `KB_RELEVANCE_THRESHOLD` 作为前置粗筛。
- **P2-2 复合问题分解 + 多跳**：`plan_web_search` 之前新增 `plan_retrieval`（一次 LLM，JSON `{"complex": bool, "subquestions": [...]}`，≤3 个）；`complex=true` 时对每个子问题分别 `query_with_sources`（可复用同一 embedding 批），合并去重后进入 rerank 与综合；简单问题走现有路径，不增加调用。可与搜索规划合并为一次调用（同一 JSON 含 `needs_search/queries`）以省 token。
- **P2-3 带编号引用的综合**：`format_kb_context` 输出 `[1]..[k]`；综合 prompt 要求关键句末标注 `[i]`，网络来源用 `[W1]..`；返回 `sources[i].ref="1"`；Web 来源面板按编号显示且答案中的 `[i]` 可对应；CLI `/sources` 显示编号。`/think on` 时通过 `Settings.llm.complete` 的 `additional_kwargs`/response `ThinkingBlock` 取出思维链，作为 `progress` 事件 `stage="thinking"` 推送到「处理过程」（截断 800 字），CLI 以 dim 样式打印。
- **P2-4 hybrid 召回**：`rank_bm25`（轻依赖，加入 requirements）在 `RAGEngine` 侧维护按 `chroma_collection.get(include=["documents","metadatas"])` 构建的 BM25 索引（惰性构建、入库/删除后失效）；`query_with_sources` 支持 `hybrid=True`：dense top-k 与 BM25 top-k 用 RRF 融合后取 top-k；`RAG_HYBRID` 环境变量默认开启，文档数 >20000 时自动关闭并提示。
- **P2-5 失败回退提示**：rerank 后无相关片段且联网无结果 → `answer` 末尾追加建议，`kind="fallback"`；Web 状态行出现「用单 Agent 重试」按钮（同一问题切模式重发）；CLI 提示 `/agent <原问题>`。

### 验收
- `tests/test_rag_pipeline.py`/新增 `tests/test_rag_rerank.py`：llm rerank 解析与回退、cross-encoder 缺依赖回退、分解 JSON 与单跳快路径不增加 LLM 调用次数、编号引用格式、hybrid RRF 融合与失效、fallback kind。
- 手动：复合问题"A 与 B 的价格差多少"在知识库有两份文档时能给出带 `[1][2]` 引用的答案。

---

## 4. P3 · 入口智能路由

- **P3-1 意图判定** `src/intent_router.py::classify_intent(text, kb_available) -> "rag"|"agent"`：规则优先（含文件/目录路径、代码围栏、动词"修改/创建/运行/执行/重命名/删除/安装/写一个/实现/修复/重构"→ agent；疑问句/"是什么/为什么/如何理解/总结/比较"→ rag）；模糊时一次 LLM 一词判定（`think=False`，`num_predict=4`，超时 5s 回退 rag）。
- **P3-2 CLI**：`handle_natural` 调用判定；走 agent 时状态行提示"已按 Agent 模式处理（用 /ask 强制知识库）"；新增 `/auto on|off`（默认 on，配置 `AUTO_ROUTE`）。
- **P3-3 Web**：模式分段新增「自动」并设为默认；服务层 `chat_auto_stream` 判定后分发，`answer` 事件 `data["routed_mode"]`，状态行显示实际模式；用户手动选其他模式时不判定。
- 验收：`tests/test_intent_router.py` 规则用例 ≥20、LLM 回退与超时；Web/CLI 处理器测试。

---

## 5. 实施顺序与交付
1. P0（含 P1-1 的 `allowed_tools/system_prompt_extra` 前置能力）→ 2. P1 → 3. P2 → 4. P3。
2. 每个 P 级完成后：全量测试通过、更新 CHANGELOG/README/本文件状态、提交（中文 commit，风格见 `git log -5`）、询问是否创建 PR（建议每个 P 级一个 PR，基于 `feat/agent-modes-optimization`）。
3. 浏览器验证（Web 相关项）：`/tmp/pw/bin/python` + `p.chromium.launch(channel="chrome", headless=True)`；启动 `cd src && ../venv/bin/python -c "import web.app as a; a.launch(server_port=7861)"`。

## 附录 A · 新增/修改的 LLM 提示词草案（实施时可微调，保持简短）

**任务分解（P0-2）**
```
把用户请求拆成可独立执行的子任务，只输出 JSON，不要解释。
type 只能取: code_generation|testing|documentation|knowledge_retrieval|audit|general
纯问答/查资料 → 只给 1 个 knowledge_retrieval；单一意图不要拆。
{"subtasks":[{"type":"...","description":"独立可执行的描述","depends_on":[]}]}
用户请求：{request}
```
**结果整合（P0-3）**
```
以下是多个 Agent 对同一请求的分工结果。写一段面向用户的最终回答：先给结论，再按子任务列要点；失败项如实说明。不要复述统计。
请求：{request}
{subtask_outputs}
```
**竞争评审（P0-5）**
```
同一任务有多个候选答案，选出最正确、完整、可执行的一个。只输出 JSON：{"best": 序号, "reason": "一句话"}
任务：{request}
{candidates}
```
**逐片段相关性（P2-1）**
```
判断每个片段是否包含回答问题所需的信息。只输出 JSON：{"keep":[序号...],"notes":{"序号":"一句理由"}}
问题：{question}
{chunks}
```
**检索规划（P2-2，可与搜索规划合并）**
```
分析问题，只输出 JSON：
{"complex":是否需要拆成多个子问题才能回答,"subquestions":[最多3个,简单问题留空],"needs_search":是否需要联网获取最新/外部信息,"queries":[最多3个搜索词]}
问题：{question}
```
**意图判定（P3-1）**
```
用户输入是「查询/理解知识」还是「让助手执行操作（改文件/跑命令/写代码）」？只输出一个词：rag 或 agent
输入：{text}
```
**ReAct 内置系统提示（P1-1）**：在现有 `SYSTEM_PROMPT_TEMPLATE` 基础上删减示例至各 1 个、合并"常见错误"到格式规则、保留工具速查与安全规则，并追加两条：
```
- 工具返回 [格式错误]/[用户拒绝]/[错误] 时，修正后重试一次；连续两次失败换方法或说明原因。
- 相同工具与参数不要重复调用；已有结果直接使用。
```
