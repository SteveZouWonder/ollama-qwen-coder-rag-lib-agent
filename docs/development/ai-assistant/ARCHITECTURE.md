# 系统架构

Cerebro 是本地优先的"知识库 + Agent"助手。本文描述当前代码的分层、四种工作模式的数据流、系统提示层次与运行时路径。模块级细节见 [MODULE_GUIDES.md](MODULE_GUIDES.md)。

## 1. 分层与依赖方向

```
┌──────────────────────── 入口层 ────────────────────────┐
│  CLI                    Web (Gradio)         Desktop   │
│  query_interface.py     web/app.py           desktop_  │
│  cli_handlers.py        web/ui/*             app.py    │
│                         web/services.py      (托盘)    │
└──────────────┬──────────────────┬─────────────────────┘
               │                  │  WebService 是 Web 的唯一业务门面
┌──────────────▼──────────────────▼─────────────────────┐
│  编排层                                                │
│  intent_router.py     rag_pipeline.py    react_engine.py│
│  (自动模式路由)        (RAG 问答编排)     (ReAct 单 Agent)│
│  master_agent.py + collaboration/  (多 Agent 协作)      │
│  conversation_context.py  (会话为唯一真源的对话记忆)     │
└──────────────┬──────────────────────────────────────────┘
┌──────────────▼──────────────────────────────────────────┐
│  能力层                                                 │
│  rag_engine.py (LlamaIndex+ChromaDB+BM25)  rag_rerank.py│
│  agent_tools.py (28 个工具 + 安全分级)  agents/* (子角色) │
│  web_search/  knowledge_graph/  code_analyzer/          │
│  database_tools/  git_integration/  ocr_processor/      │
│  document_loader.py  code_chunker.py  file_metadata.py  │
│  knowledge_snapshot.py  session_manager.py              │
└──────────────┬──────────────────────────────────────────┘
┌──────────────▼──────────────────────────────────────────┐
│  基础层                                                 │
│  config.py (env → 常量)   runtime_paths.py (路径解析)    │
│  prompt_assets.py (prompts/ 加载)   content_security.py │
└─────────────────────────────────────────────────────────┘
```

依赖只能自上向下。能力层模块之间不互相 import 编排层；`web/` 只依赖 `WebService`，不直接触碰引擎（测试通过 `WebService(rag_factory=..., react_factory=..., orchestrator_factory=...)` 注入）。

`src/` 内模块以**顶层名**导入（`from config import ...`），`sys.path` 由入口脚本插入 `src/`；打包时 spec 同样 `sys.path.insert(0, "src")`。

## 2. 四种工作模式

用户在 CLI（自然语言 / `/ask` / `/agent` / `/multi`）或 Web 对话页（自动 / RAG 检索 / 单 Agent / 多 Agent 协作）选择模式。

### 2.1 自动（默认）— `intent_router.classify_intent`

```
文本 ─▶ agent_signals（路径 / 代码围栏 / 命令动词）
     ─▶ rag_signals（问号 / 疑问词 / 知识词 / 前缀）
     ├─ 仅 Agent 命中 → agent
     ├─ 仅 RAG 命中   → rag
     └─ 模糊 ──▶ kb_available=False → agent（不调 LLM）
                └─ 否则 llm_classify（num_predict=4, timeout=5）→ rag|agent，失败回退 rag
```

CLI：`query_interface.handle_natural` → `Config.AUTO_ROUTE and _route_natural_to_agent`。Web：`WebService.chat_auto_stream` 先 yield `progress(phase="route")`，`answer.data["routed_mode"]` 决定渲染路径。

### 2.2 RAG — `rag_pipeline.answer_question`

```
问题
 ├─ is_meta_query → build_meta_overview（"知识库里有什么"直答，kind="meta"）
 ├─ context.rewrite_question（追问改写，仅 is_followup 命中时调 LLM）
 ├─ plan_retrieval（一次 LLM：complex / subquestions≤3 / needs_search / queries）
 ├─ augment_with_web_search（可选：run_web_search → enrich_with_page_content）
 └─ generate_answer
     ├─ _retrieve（hybrid: 向量 + BM25 RRF）/ _merge_multi_hop
     ├─ filter_relevant_sources（KB_RELEVANCE_THRESHOLD=0.45）
     ├─ rag_rerank.rerank（llm / cross-encoder；CONFIDENT_SCORE=0.6 跳过）
     ├─ assign_refs（kb [1..k] / web [W1..]）→ synthesize_prompt → LLM
     └─ 0 命中：kb_only→空；否则 simple_web_search；再无→模型自答 + fallback_suggestion（kind="fallback"）
返回 dict（answer / sources / web_sources / kind / rewritten / thinking …）
```

`answer_question` **不写会话**；调用方（CLI `_run_ask`、Web `_finish_turn`、RAGAgent）负责 `record_conversation`。阶段边界检查 `should_stop` 抛 `PipelineCancelled`。

### 2.3 单 Agent — `react_engine.ReActEngine.chat`

```
chat(task)
 ├─ _load_context：context.build_messages(system_prompt) + 本轮问题
 │   turn_budget = num_ctx − 系统提示 − 历史 − NUM_PREDICT(4096)，下限 1024
 └─ for step in 1..max_iterations:
     ├─ _call_model（/api/chat，temperature 0.3，think 默认关）
     ├─ _parse_response → action | final | format_error
     │   format_error：≤ MAX_FORMAT_RETRIES(2) 回灌 [格式错误]；超出以现文本收尾并标注
     ├─ allowed_tools 越界 → [错误] 工具 X 不在当前允许的工具集内
     ├─ _check_repeat：同 (tool, args) 第 2 次 [重复调用]，第 3 次强制总结
     ├─ execute_command：CommandSafetyChecker → [安全拦截] / on_confirm → [用户拒绝]
     ├─ registry.execute → [CONFIRM_REQUIRED] → on_confirm → 确认后 auto_confirm=True 重执行
     ├─ _truncate_observation（OBSERVATION_MAX_CHARS=3000）→ _push_observation
     └─ _enforce_budget：超预算从最早步折叠为一行要点，保留最近 KEEP_RECENT_STEPS=3
 步数耗尽 / 重复终止 → _forced_summary（"⚠️ 未完成…" 前缀）
 _finish → context.record(task, answer, trace=一句执行摘要)
```

系统提示每次构造时组装、不落盘（见 §3）。

### 2.4 多 Agent — `master_agent.coordinate_task`

```
request ─▶ TaskDecomposer.decompose（LLM ≤512 token → 关键词规则回退；MAX_SUBTASKS=5）
        ─▶ TaskScheduler.schedule*（按 capability 分配到 Code/Test/Doc/Audit/RAG）
        ─▶ 执行（模式决定）
            HIERARCHY（默认）/ SEQUENTIAL：_execute_sequential，上游输出经 _attach_upstream 传下游
            PARALLEL：_execute_parallel，按依赖分波，ThreadPoolExecutor
            COMPETITIVE：_run_competitive，同一子任务多 Agent 并行，LLM 评审选优
        ─▶ ResultIntegrator.integrate*（LLM 综合 answer，合并 sources）
```

子角色（`agents/code_agent.py` 等）继承 `ReActDelegateAgent`：构造受限 `ReActEngine(allowed_tools=白名单, system_prompt_extra=ROLE_PROMPT, prompt_mode="builtin", role=agent_type, context=EphemeralContext())`。子 Agent 无交互界面，`_auto_confirm` 对白名单工具放行、`execute_command` 仅 low/medium。未调用 `ESSENTIAL_TOOLS` 的结果标 `unverified` 并加"⚠️ 未经验证"前缀。RAGAgent 不走 ReAct，直接调 `answer_question`。

### 2.5 会话与上下文（三种模式共用）

`conversation_context.ConversationContext` 以 `session_manager` 的会话为唯一真源：

- `build_messages(system_prompt)` → `[系统提示] + [滚动摘要 system] + [最近 K 轮原文]`，按 `CONTEXT_HISTORY_RATIO`（0.30 × num_ctx）裁剪。
- `record()` 写一轮并 `maybe_compress`（占用 > 70% 时 LLM 折叠旧轮为摘要，失败退化启发式）。
- `health()` 给出"建议新建会话"信号（压缩 ≥2 / 占用 ≥90% / 话题漂移 / 空闲 >6h）。
- `new_session(carry_summary)` 只承接**已折叠的滚动摘要**；跟随模式（`session_id=None`）不钉死到新会话。
- CLI 使用进程级单例 `get_conversation_context()`（跟随当前会话）；Web 每次请求按 `gr.State` 里的 `session_id` 新建绑定实例；多 Agent 子角色用 `EphemeralContext`（不读写会话）。

### 2.6 流式回调路径（F10 P1-1，三种模式共用）

所有 LLM 调用都接受可选 `on_token(delta: str)`；**不传时请求保持 `stream: False`，行为与旧版字节级一致**。传入且 `Config.LLM_STREAM`（默认 `true`）开启时改为 `stream: True` 逐行读 NDJSON、每个增量回调一次；`LLM_STREAM=false` 时仍非流式但把完整文本一次性回调，因此消费方无需区分。

```
                      ┌ CLI：cli_handlers.LiveAnswer.on_token（rich Live(Markdown) 面板，transient；finish() 后按原格式打印全文）
  on_token ◀──────────┤
                      └ Web：WebService._token_sink(q, cancel) → StreamEvent("token", delta) → app.on_chat_stream 逐段拼到最后一条气泡
                                                                                              （answer 到达后以完整文本替换）
  RAG    answer_question(on_token) → generate_answer → 只有最终综合那次 llm_direct_answer(prompt, on_token, should_stop)
         → _complete → _stream_complete：Settings.llm.stream_chat(...)，should_stop 为真即 break + gen.close()
  单 Agent ReActEngine(on_token) / chat(task, on_token) → 每轮 _call_model(on_token=FinalAnswerStream(cb))
         FinalAnswerStream：缓冲到看见 "Final Answer:" 才转发其后的增量；缓冲区出现 "Action:" 则丢弃本轮
         _call_model → requests.post(stream=True) → llm_helper.consume_ndjson_stream(resp, cb, should_stop=_stop_event.is_set)
         stop()：置位 + llm_helper.abort_response(_active_response)（socket.shutdown + close → 读线程立刻退出、模型停止生成）
  多 Agent orchestrator.process_request(on_token) → coordinate_task(on_token) → ResultIntegrator.on_token（仅整合阶段）
         → complete_text(prompt, on_token=…)（子任务执行不流式）
```

约定：`answer` / 最终返回值仍是**完整文本**（经 `<think>` 剥离、引用校验等后处理），流出的 token 只是原始增量，UI 以最终文本为准；`_bridge` 的心跳只在心跳间隔内没有任何事件（含 token）时发出；单 Agent 在 `_call_model` 返回后再查一次 `_stop_event`，被中断的半截文本不进协议解析。

## 3. 系统提示层次（`react_engine.build_system_prompt`）

| 层 | 来源 | 作用范围 |
|---|---|---|
| 1 内置模板 | `SYSTEM_PROMPT_TEMPLATE`：身份 / 输出协议 / 格式规则 / 工具速查（按 `tools` 过滤）/ 安全规则 | 全部 |
| 2 `=== Skills ===` | `prompts/skills/*/SKILL.md`，`prompt_assets.render_skills(role)` 按 frontmatter `roles` 过滤，总长 ≤ `SKILL_MAX_CHARS`(4000) | 单 Agent + 所有子角色；`CODE_AGENT_SKILLS=off` 关闭 |
| 3 `=== 项目附加规范 ===` | `prompts/system/PROJECT_RULES.md`，截断到 `SYSTEM_PROMPT_EXTRA_MAX_CHARS`(4000) | 仅 `CODE_AGENT_PROMPT_MODE=append`（默认）；子角色默认 `builtin` 不含 |
| 4 `=== 角色说明 ===` | 子 Agent 类的 `ROLE_PROMPT`（≤200 token，测试硬限） | 对应子角色 |

`prompts/` 的三层解析（内置 → 用户数据目录 → `AGENT_PROMPTS_DIR`）见 `prompt_assets.py` 与 `prompts/README.md`。RAG 综合 prompt、分解 / 整合 prompt 独立于此（分别在 `rag_pipeline.py`、`collaboration/`）。

## 4. 运行时路径（`runtime_paths.py`）

| 函数 | 源码运行 | PyInstaller 打包 |
|---|---|---|
| `resource_root()` | 仓库根 | `sys._MEIPASS` |
| `user_data_dir()` | 仓库根 | `~/Library/Application Support/Cerebro`（macOS）/ `%APPDATA%/Cerebro` / `$XDG_DATA_HOME/Cerebro` |
| `config_dir()` | `config/` | `<user_data>/config/` |
| `app_state_dir(rel)` | `.cerebro/<rel>` | `<user_data>/.cerebro/<rel>`；目标不存在而 `.devin/<rel>` 存在时**一次性搬迁** |
| `home_file(name)` | `~/<name>` | `<user_data>/<name>` |
| `logs_dir()` | `logs/` | `<user_data>/logs/` |

只读资产打包到 `datas`：`assets/`、`config/`→`default_config/`（目标名不能叫 `config`，会与 `config.py` 冲突）、`prompts/`。运行时状态（快照 / 图谱 / 文件元数据）统一走 `app_state_dir`，与 cwd 解耦（历史 bug：读端相对 cwd、写端绝对路径导致 `/cd` 后读到空库）。

## 5. 数据目录一览

```
data/                     用户文档默认入库目录（gitignored）
index_storage/            ChromaDB 向量库 + LlamaIndex 索引（gitignored）
.cerebro/
  knowledge/snapshots/    知识库快照
  knowledge/graph.json    知识图谱
  file_metadata/          入库文件元数据
~/.code_agent_sessions/   会话 JSON + current.txt（SESSION_STORAGE_PATH 可覆盖；打包版在用户数据目录）
config/app_config.json    用户运行时配置（Ollama 地址等，UI 可写）
prompts/                  模型输入资产（只读，版本化）
```

## 6. 关键扩展点

| 想做什么 | 改哪里 |
|---|---|
| 新增 Agent 工具 | `agent_tools.py` `registry.register(...)`；同步 `prompts/system/PROJECT_RULES.md` 参数名段、`TOOL_USAGE.md`、子角色白名单（如需）与测试 |
| 新增子 Agent 角色 | `agents/agent_types.py` 加枚举；新建 `agents/xxx_agent.py` 继承 `ReActDelegateAgent`；`agent_config.py` 默认配置；`agent_registry` 注册；`prompts/skills` 的 `roles` 可选值随之扩展 |
| 新增 / 调整 Agent 行为规范 | `prompts/skills/<name>/SKILL.md`（全局）或 `PROJECT_RULES.md`（产品事实） |
| 新增 Web 页面 | `web/ui/<page>.py` 构建组件 + `web/app.py build_handlers` 加 handler + `WebService` 加业务方法 |
| 新增 CLI 命令 | `query_interface.parse_command` 加分支 + `cli_handlers` 处理函数 + `COMMAND_HANDLERS` 表 + README 命令表 |
| 新增搜索源 | `web_search/search_engine.py` 实现 `SearchEngine` 子类并加入聚合器 |
| 新增 OCR 引擎 | `ocr_processor/base.py` 抽象类实现 + `config.OCR_ENGINE` 选项 |
