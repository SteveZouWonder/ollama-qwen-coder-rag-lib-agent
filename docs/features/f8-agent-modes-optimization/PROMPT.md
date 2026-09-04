# F8 启动提示词：三种对话模式优化（P0-P3）

> 用法：新开任务时把「提示词正文」整段贴给 Agent。需求细节与代码事实都在
> `docs/features/f8-agent-modes-optimization/REQUIREMENTS.md`（下称 REQ），Agent 应先读它，**不要重复调研已核实事实**。
> 可按 P 级分多次任务：把「本次范围」一行改成对应 P 级即可。

---

## 提示词正文

```
# 任务：实现三种对话模式优化（RAG / 单 Agent / 多 Agent），按 P0→P1→P2→P3 顺序

先完整阅读 docs/features/f8-agent-modes-optimization/REQUIREMENTS.md（REQ）。其 §0 是已核实的代码事实与文件:行号，直接采信，勿重复调研；§1-§4 是需求与验收；附录 A 是 LLM 提示词草案。

## 本次范围
P0 → P1 → P2 → P3 全部（若上下文不足，至少完成一个完整 P 级并提交，再在总结中说明下一步）。

## 环境与规则
- 分支：feat/agent-modes-optimization（已存在，直接提交，不新建）。禁止提交 master。
- 测试：./venv/bin/python -m pytest -q -n 4，全量覆盖 ≥80%，新逻辑必须有单测（Mock Ollama/Chroma，参考 tests/test_react_engine.py、tests/test_rag_pipeline.py、tests/multi_agent/、tests/test_web_services.py）。src/web/ui/* 标 # pragma: no cover。
- 分层：引擎层（rag_pipeline/react_engine/master_agent…）→ src/web/services.py（唯一接引擎）→ src/web/app.py（format_*/build_handlers，可单测）→ src/web/ui/*；CLI 为 query_interface.py（parse_command/classify_mode/print_help/TUTORIAL_TEXT）+ cli_handlers.py（COMMAND_HANDLERS）。
- 新 LLM 提示词：短、只输出 JSON/一词、think=False、num_predict 限额；解析失败必须有回退。
- 每个 P 级完成：全量测试通过 → 更新 CHANGELOG.md [Unreleased]（新增/改进/修复）、README 对应段落、REQ 文件顶部状态 → 中文 commit（风格见 git log -5）→ 询问是否创建 PR（不得自动创建）。
- Web 项做浏览器验证：cd src && ../venv/bin/python -c "import web.app as a; a.launch(server_port=7861)"；/tmp/pw/bin/python + playwright chromium(channel="chrome", headless=True)；截图 + 无 console error。
- 不改动用户数据目录（.devin/knowledge、index_storage）；.devin/SYSTEM_PROMPT.md 按 REQ P1-1 清理时保留原文备份为 .devin/SYSTEM_PROMPT.md.bak。

## 交付顺序（每项对应 REQ 编号）
P0：P0-1 四个桩 Agent 委托 ReActEngine（需先做 P1-1 的 allowed_tools/system_prompt_extra 参数）→ P0-2 LLM 分解+回退 → P0-4 真并行与超时 → P0-3 LLM 整合 answer → P0-5 竞争评审 → P0-6 sources 与 Web 渲染 → P0-7 配置生效 → P0-8 文案 + CLI /multi。验收：src/ 中桩文本零命中。
P1：P1-1 提示分层 → P1-2 协议容错 → P1-3 步数耗尽总结 → P1-4 重复检测 → P1-5 本轮预算 → P1-6 知识库工具对齐 → P1-7 安全分级/路径边界 → P1-8 step_log 事件。验收：builtin 提示 ≤1.5K token（estimate_tokens）。
P2：P2-1 rerank（llm 默认，cross-encoder 可选回退）→ P2-2 检索规划+多跳（与搜索规划合并为一次 LLM）→ P2-3 编号引用 + think 透出 → P2-4 BM25 hybrid → P2-5 fallback 提示。验收：简单问题 LLM 调用次数不增加。
P3：P3-1 intent_router → P3-2 CLI /auto → P3-3 Web「自动」模式默认。

## 完成后输出
各 P 级：改动文件清单、新增测试数、覆盖率、验收项逐条结果、未完成/风险。
```

---

## 设计说明（为什么这样写）
- 事实全部放在 REQ §0 并给出行号，提示词只引用，避免 Agent 重新 grep 大文件消耗上下文。
- 顺序与依赖显式化（P0-1 依赖 P1-1 的两个参数），避免 Agent 先做 P1 再返工。
- 验收条件用可机器检查的表述（零命中、token 上限、调用次数不增加）。
- 规则只列与本仓库 AGENTS.md / 现有工程约束相关的最小集合。
