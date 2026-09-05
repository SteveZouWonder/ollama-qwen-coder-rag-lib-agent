# F8: 三种对话模式优化（RAG 检索 / 单 Agent / 多 Agent）

## 实施状态

**状态**: 🚧 P0（多 Agent 真实化，2026-09-04）、P1（单 Agent 鲁棒性与上下文，2026-09-05）已完成，P2 / P3 待实现 · 分支 `feat/agent-modes-optimization`
**目标**: 提升任务质量、回答准确度与智能程度

## 文档

- [REQUIREMENTS.md](REQUIREMENTS.md) - 需求、已核实的代码事实（带 `文件:行号`）、验收标准、LLM 提示词草案
- [PROMPT.md](PROMPT.md) - 交给 Agent 的启动提示词（省 token 版，可按 P 级拆多次任务）

## 范围（按 P0 → P3 顺序实施）

| 级别 | 模式 | 内容 |
|---|---|---|
| P0 ✅ | 多 Agent | 4 个硬编码桩 Agent 改为委托 ReActEngine 真实执行；LLM 任务分解 / 结果整合 / 竞争评审；真并行与超时；结构化来源；CLI `/multi` |
| P1 ✅ | 单 Agent | 系统提示分层（内置 ≤1.5K token + 项目附加）；协议容错重试；步数耗尽强制总结；重复调用检测；本轮上下文预算折叠；知识库工具对齐 RAG 编排；安全分级与写路径边界 |
| P2 | RAG | 逐片段 rerank（LLM 默认 / cross-encoder 可选）；复合问题分解与多跳；带编号引用的综合与思维链透出；BM25 hybrid 召回；失败回退提示 |
| P3 | 路由 | 自然语言输入的意图判定（规则 + LLM 兜底），CLI `/auto`、Web「自动」模式 |

## 关联

- 前置基础：[F2 多 Agent 协作系统（骨架）](../f2-multiple-agent/)、[F6 Agent 工具集](../f6-capability-tools/)、[F7 Web 界面](../f7-web-ui/)
- 完成后：本 README 状态改为 ✅，补「实现记录（与需求的差异）」表，并更新 [../README.md](../README.md) 索引

## 实现记录

| 项 | 状态 | 说明 / 与需求的差异 |
|---|---|---|
| P0-1 | ✅ | `agents/base_agent.py::ReActDelegateAgent` 统一委托逻辑；Code/Test/Doc/Audit 只声明 `ROLE_PROMPT` / `ALLOWED_TOOLS` / `ESSENTIAL_TOOLS`。新增：未调用关键工具即给结论 → 标记「未经验证」 |
| P0-2 | ✅ | `TaskDecomposer(complete, use_llm)`，`last_method` 供进度文案；回退关键词表 |
| P0-3 | ✅ | `ResultIntegrator.integrate*(…, request)` 产出 `answer` / `answer_method` / `sources` / `tasks`；单一成功子任务直接采用（不额外调用） |
| P0-4 | ✅ | 依赖分波 + `ThreadPoolExecutor`；`execute_task_with_timeout` 线程 + `cancel()`；失败/超时恢复 IDLE |
| P0-5 | ✅ | LLM 评审 `{"best","reason"}`；回退最长成功输出；全部失败取错误信息最详细者 |
| P0-6 | ✅ | `AgentResult.sources`；`collaboration/presenter.py` 为 CLI/Web 共用渲染器 |
| P0-7 | ✅ | `agent_orchestrator._create_agent` 传 model/host/timeout/max_iterations/allowed_tools；`agent_config` 白名单为真实工具名 |
| P0-8 | ✅ | 文案按 `last_method` 如实；CLI `/multi … [--mode m]`（`cli_handlers.handle_multi`）|
| P1-1 | ✅ | `build_system_prompt(tools, extra, mode)`、`CODE_AGENT_PROMPT_MODE`、`SYSTEM_PROMPT_EXTRA_MAX_CHARS`；内置提示 ≈1.07K token（P0 前置）。`.devin/SYSTEM_PROMPT.md` v4.3.0 清理 `todo_write` / `~/.config/devin/*` / 「用 read_system_prompt 读本提示」/ `execute_command` 跑斜杠命令四类错误指引，原文备份 `.bak`（gitignore） |
| P1-2 | ✅ | `ReActEngine._parse_response` 三分类 action / final / format_error；`_handle_format_error` 连续重试 ≤`MAX_FORMAT_RETRIES`（env，默认 2），超过按现有文本收尾标注「（格式异常，可能不完整）」；`[错误]` 直接返回不 `_record_turn`。差异：重试计数按**连续**格式错误（合法步骤后重置），"未知工具"也归为格式错误（不再执行 registry 得到 `[错误] 未知工具`） |
| P1-3 | ✅ | `_forced_summary(reason)`：追加 user 总结请求，`_call_model(num_predict=1024, think=False)`，前缀「⚠️ 未完成（已达最大步数 N）」；模型失败回退执行摘要 |
| P1-4 | ✅ | `_check_repeat`：`(tool, json.dumps(sort_keys))` 计数，第 2 次回灌 `[重复调用]` 不执行，第 3 次 → `_forced_summary("repeat")` 前缀「⚠️ 未完成（检测到重复调用，已终止）」。差异：全局计数而非仅"连续"相同 |
| P1-5 | ✅ | `_compute_turn_budget = num_ctx − system − history − 4096`（下限 1024）；`_truncate_observation`（`OBSERVATION_MAX_CHARS` env，默认 3000）；`_enforce_budget` 每步后检查，从最早步折叠为「（第 k 步 tool=x 结果已折叠，要点：前 200 字）」，保留最近 3 步；复用 `conversation_context.estimate_tokens / estimate_messages_tokens` |
| P1-6 | ✅ | `query_knowledge_base` → `answer_question(engine, q, enable_web_search=False, show_progress=False, kb_only=True)`；`format_kb_tool_result` 渲染「答案 + 相关性结论 + top-3 片段（≤300 字，含文件名）」/ `[知识库无相关内容]` / 元查询概览。差异：新增 `kb_only` 参数——否则 `generate_answer` 在 0 命中时仍会 `simple_web_search` + LLM 兜底，结果被工具丢弃属纯浪费 |
| P1-7 | ✅ | `CommandSafetyChecker.MEDIUM_PATTERNS`（install / git 写操作 / `python x.py` / `node x.js` / make / docker run|exec）与 `HIGH_PATTERNS`（`curl|wget … \| sh|bash|zsh`，含 `sudo`）；`is_path_allowed` + `WRITE_ALLOWED_DIRS`（env，冒号分隔，`Config.WRITE_ALLOWED_DIRS` 映射）保护 `write_file` / `add_to_knowledge_base`。差异：`curl … \| sh` 由 critical（直接拦截）改为 high（需确认），`\| bash` 此前漏判为 low；多 Agent 子角色 `_auto_confirm` 只放行 low/medium，故 pip install / python x.py 在子 Agent 内仍自动放行、curl\|sh 被拒——属预期 |
| P1-8 | ✅ | `step_log` 事件 `format_retry / repeat / budget_fold / forced_summary / error`；`ReActEngine.get_step_summary` / `_trace_summary`、`web/app.py::format_step_log`、`query_interface.on_step_callback`（`STEP_PHASE_EMOJI/COLOR`：`[~] [R] [F] [!!] [E]`）与 `/summary` 同步。浏览器验证：Web「处理过程」实时显示格式重试 / 重复调用事件，无 console error |

