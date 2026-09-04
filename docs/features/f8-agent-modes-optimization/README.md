# F8: 三种对话模式优化（RAG 检索 / 单 Agent / 多 Agent）

## 实施状态

**状态**: 🚧 P0（多 Agent 真实化）已完成（2026-09-04），P1 / P2 / P3 进行中 · 分支 `feat/agent-modes-optimization`
**目标**: 提升任务质量、回答准确度与智能程度

## 文档

- [REQUIREMENTS.md](REQUIREMENTS.md) - 需求、已核实的代码事实（带 `文件:行号`）、验收标准、LLM 提示词草案
- [PROMPT.md](PROMPT.md) - 交给 Agent 的启动提示词（省 token 版，可按 P 级拆多次任务）

## 范围（按 P0 → P3 顺序实施）

| 级别 | 模式 | 内容 |
|---|---|---|
| P0 ✅ | 多 Agent | 4 个硬编码桩 Agent 改为委托 ReActEngine 真实执行；LLM 任务分解 / 结果整合 / 竞争评审；真并行与超时；结构化来源；CLI `/multi` |
| P1 | 单 Agent | 系统提示分层（内置 ≤1.5K token + 项目附加）；协议容错重试；步数耗尽强制总结；重复调用检测；本轮上下文预算折叠；知识库工具对齐 RAG 编排；安全分级与写路径边界 |
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
| P1-1（前置部分） | ✅ | `build_system_prompt(tools, extra, mode)`、`CODE_AGENT_PROMPT_MODE`、`SYSTEM_PROMPT_EXTRA_MAX_CHARS`；内置提示 ≈1.07K token。`.devin/SYSTEM_PROMPT.md` 内容清理留在 P1 |

