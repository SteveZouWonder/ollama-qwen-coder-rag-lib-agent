# F9 启动提示词：Web「工具」页重构（按 P 级分发）

> 用法：按优先级依次把下方某个「提示词」代码块**整段**贴给 Agent，一次一个 P 级。
> 需求细节与代码事实都在 `docs/features/f9-web-tools-revamp/REQUIREMENTS.md`（下称 REQ），
> 提示词只引用章节号，Agent 应先读 REQ，**不要重复调研 §0 已核实的事实**。
> 实现记录与差异写入同目录 `README.md`（不写入 REQ）。
>
> 三段提示词各自独立、可单独使用；「公共规则」已内联在每段中，无需另贴。

---

## P1 · 止血与骨架（高优先级，建议先做）

```
# 任务：F9 P1 —— Web 工具页止血与骨架

先读 docs/features/f9-web-tools-revamp/REQUIREMENTS.md：§0 是已核实的代码事实（文件:行号），直接采信勿重新调研；§1 是本次需求与验收；§4 是 UI 规范；附录 A-5/A-6 是提示词模板。同目录 README.md 记录实现进度。

## 范围
§1 全部：P1-1 删网络搜索子页 → P1-2 DB 连接上下文透传（先写复现测试）→ P1-3 表列表与 Schema → P1-4 DB 结果表格化 → P1-5 Git 仪表盘 → P1-6 结果流转（用 AI 解读 / 发送到对话）。
「代码」「工作区」子页本次只挂结果流转行，不重构。

## 规则
- 分支 feat/web-tools-revamp（已存在，直接提交）；禁止提交 master；完成后询问是否建 PR，不得自动建。
- 分层：工具库 → src/web/services.py（唯一接引擎）→ src/web/app.py（format_*/build_handlers，可单测）→ src/web/ui/*（# pragma: no cover）。handler 返回值个数 = outputs 个数。
- 不新增/改名 registry 工具；database_get_schema 仅放宽 table="" 语义。
- LLM 长任务必须经 WebService._bridge；is_running() 时拒绝。新提示词短、think=False、num_predict 限额。
- 测试：./venv/bin/python -m pytest -q -n 4，覆盖 ≥80%；Mock Ollama；tmp_path 隔离；参考 tests/test_web_services.py、tests/test_web_app.py。
- 浏览器验证：cd src && ../venv/bin/python -c "import web.app as a; a.launch(server_port=7861)"，playwright chromium 截图四个子页，无 console error。

## 完成后
更新 CHANGELOG.md [Unreleased]（新增/修复/改进）、README.md 工具页段落、docs/features/f7-web-ui/README.md:31、docs/development/ai-assistant/TOOL_USAGE.md:70 连接描述、同目录 README.md（状态表 + 实现记录 + 差异 + 验证）、docs/features/README.md 状态。中文 commit（风格见 git log -5）。
输出：改动文件清单、新增测试数、覆盖率、§1 验收逐条结果、未完成/风险。
```

---

## P2 · AI 主入口（中优先级，P1 完成后）

```
# 任务：F9 P2 —— Web 工具页 AI 主入口

先读 docs/features/f9-web-tools-revamp/REQUIREMENTS.md：§0 代码事实直接采信；§2 是本次需求与验收；§4 UI 规范；附录 A-1~A-3 是提示词草案。同目录 README.md 中 P1 已完成项以它为准（P1-6 的 ai_explain_stream / 结果流转行、react_factory 与 chat_refs 传参已存在，直接复用）。

## 范围
§2 全部，顺序：P2-1 代码助手（先给 _default_react_factory / WebService.react_factory 加 allowed_tools / system_prompt_extra / max_iterations 透传）→ P2-3 工作区文件浏览 → P2-2 DB 自然语言转 SQL → P2-4 Shell 自然语言生成命令。
若上下文不足，至少完成一个完整编号项并提交，总结中说明下一步。

## 规则
- 分支 feat/web-tools-revamp；禁止提交 master；完成后询问是否建 PR，不得自动建。
- 分层：工具库 → services.py（唯一接引擎）→ app.py（format_*/handlers，可单测）→ ui/*（no cover）。handler 返回值个数 = outputs 个数。
- 不新增/改名 registry 工具；结构化数据在 service 层直接调 code_analyzer / database_tools / os。
- 带工具的 AI 动作走 ReActEngine(allowed_tools=只读集, max_iterations=12) 经 _bridge；纯生成走 collaboration.llm_helper.complete_text，think=False，num_predict 按 REQ 限额，解析失败必须有回退。
- AI 生成的 SQL / 命令只回填编辑框，执行前用户确认：SELECT 直接跑，写操作与 medium+ 命令走 Confirm；shell_enable 总开关门控 编辑 / 命令。
- 测试：./venv/bin/python -m pytest -q -n 4，覆盖 ≥80%；注入 react_factory / Mock complete_text；tmp_path。
- 浏览器验证同 P1（四个子页截图 + §2 验收场景）。

## 完成后
更新 CHANGELOG.md [Unreleased]、README.md 工具页段落、docs/features/f7-web-ui/README.md、同目录 README.md（状态 + 实现记录 + 差异 + 验证）、docs/features/README.md。中文 commit。
输出：改动文件清单、新增测试数、覆盖率、§2 验收逐条结果、未完成/风险。
```

---

## P3 · 体验打磨（低优先级，P2 完成后）

```
# 任务：F9 P3 —— Web 工具页体验打磨

先读 docs/features/f9-web-tools-revamp/REQUIREMENTS.md：§0 代码事实直接采信；§3 是本次需求与验收；§4 UI 规范。同目录 README.md 记录 P1/P2 已完成实现，以它为准。

## 范围
§3 全部：P3-1 连接记忆（.cerebro/web_tools_state.json）→ P3-2 命令历史 → P3-3 提交信息增强（暂存预览 + 可编辑 + Confirm 提交）→ P3-4 空态与加载态。

## 规则
- 分支 feat/web-tools-revamp；禁止提交 master；完成后询问是否建 PR，不得自动建。
- 状态文件经 runtime_paths 解析，测试用 tmp_path monkeypatch；损坏 JSON 回退空；不改动 index_storage/ 与 .cerebro/ 内既有文件格式。
- git commit 受 shell_enable 门控 + Confirm；service 层执行，不经 registry。
- 分层与测试要求同 P1/P2：services.py → app.py → ui/*；./venv/bin/python -m pytest -q -n 4，覆盖 ≥80%。
- 浏览器验证：重启后最近库仍在下拉；历史命令回填；提交流程端到端截图。

## 完成后
更新 CHANGELOG.md [Unreleased]、README.md、docs/features/f7-web-ui/README.md、同目录 README.md（状态改 ✅ + 实现记录 + 差异 + 验证）、docs/features/README.md（F9 移入已实现）、ROADMAP.md。中文 commit。
输出：改动文件清单、新增测试数、覆盖率、§3 验收逐条结果、未完成/风险。
```

---

## 设计说明（为什么这样写）
- 需求（REQ）与实现记录（README）分文件：REQ 只增不改；实现差异集中在 README。
- 代码事实全部在 REQ §0 并带行号，提示词只引用章节，避免 Agent 重新 grep 大文件。
- 三个 P 级各自独立成段、规则内联，可单独粘贴；P2/P3 显式声明依赖前序产物（`ai_explain_stream`、`react_factory` 透传），避免返工。
- 顺序中的前置项写明（P1-2 先写复现测试、P2-1 先做工厂透传），验收用可检查的表述（grep 结果、返回元组、截图）。
- 规则只列与 AGENTS.md / 现有工程约束相关的最小集合，不复制 REQ 正文。
