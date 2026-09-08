# F9 启动提示词：抗过度顺从与回答可核验性（P0-P2）

> 用法：新开任务时把「提示词正文」整段贴给 Agent。需求细节与代码事实都在
> `docs/features/f9-anti-overcompliance/REQUIREMENTS.md`（下称 REQ），Agent 应先读它，**不要重复调研已核实事实**。
> 可按 P 级分多次任务：把「本次范围」一行改成对应 P 级即可。实现记录与差异写入同目录 `README.md`（不写入 REQ）。

---

## 提示词正文

```
# 任务：实现 F9 抗过度顺从与回答可核验性，按 P0→P1→P2 顺序

先完整阅读 docs/features/f9-anti-overcompliance/REQUIREMENTS.md（REQ）。§0 是立项时核实的研究依据与代码事实（文件:行号，基于 master d35ac38），直接采信，勿重复调研；§1-§3 是 P0-P2 需求与验收；§4 明确不做；§5 顺序；附录 A 是提示词草案。同目录 README.md 是实现记录，已完成的 P 级以它为准。

## 本次范围
P0 → P1 → P2 全部（上下文不足时至少完成一个完整 P 级并提交，再在总结中说明下一步）。

## 环境与规则
- 分支：feat/anti-overcompliance（已存在，直接提交，不新建）。禁止提交 master。
- 测试：./venv/bin/python -m pytest -q -n 4，覆盖 ≥80%，新逻辑必须有单测（Mock Ollama/Chroma，参考 tests/test_rag_pipeline.py、tests/test_rag_engine.py、tests/test_react_engine_prompt_layers.py、tests/test_web_app.py）。REQ §0.2 列出的既有断言子串与 ≤1500 token 限制不得破坏。
- 分层：引擎层（rag_engine/rag_pipeline/react_engine/conversation_context）→ src/web/services.py（唯一接引擎）→ src/web/app.py（format_*，可单测）→ src/web/ui/*（# pragma: no cover）；CLI 为 query_interface.py + cli_handlers.py。
- 提示词：只按附录 A 增删，短、中文；新 LLM 调用 think=False、num_predict 限额、解析失败必须回退；P2 两项默认关/零新增调用。
- 展示：所有面向用户的警示/校验信息走 REQ P0-5 的 notices，answer 只含正文；各端样式与位置按 REQ §1 P0-3/P0-5 与 §0.4 事实，不自行发明新组件；新增进度 stage 在 CLI style_map 登记。
- 模型无关：所有改动不得依赖特定模型名；检索器/模板在 rag_engine._setup_query_engine 内构造以随 set_model 重建。
- 每个 P 级完成：全量测试通过 → 更新 CHANGELOG.md [Unreleased]（新增/改进/修复）、主 README 对应段落、同目录 README.md（状态表 + 实现记录 + 差异 + 验证记录）、REQ 顶部状态行、docs/features/README.md → 中文 commit（风格见 git log -5）→ 询问是否创建 PR（不得自动创建）。
- Web 项做浏览器验证：cd src && ../venv/bin/python -c "import web.app as a; a.launch(server_port=7861)"；/tmp/pw/bin/python + playwright chromium(channel="chrome", headless=True)；截图 + 无 console error。
- 不改动用户数据目录（.devin/knowledge、index_storage）。scripts/eval_overcompliance.py 需要真实 Ollama，只手动运行，不进测试集。

## 交付顺序（每项对应 REQ 编号）
P0：P0-1 检索-only + 删快路径 + 单次综合（改 query_with_sources / is_empty_rag_result / --query 路径 / query_tool）→ P0-2 FAITHFULNESS_RULES 常量 + 3 条新条款 → P0-5 notices 结构（answer 只含正文；CLI yellow 行 / Web blockquote / presenter / 会话记录 / Agent 工具四端渲染；删 ⚠️ 前缀与 fallback 重复文案）→ P0-3 verify_citations + cited 回填 + citation_check/model 字段 + 状态行计数 + 来源面板明细 + invalid>0 自动展开（八元组）→ P0-4 ReAct 事实规则。验收：简单问题恰好 1 次 llm.complete；src/ 中 as_query_engine( 与 `⚠️ 知识库中无相关内容` 字面量零命中。
P1：P1-1 no_evidence 路径（notice，不改 answer）→ P1-2 质疑句式与改写规则 + challenge 字段（复用 🔗 已理解为 通道改文案）→ P1-3 网页正文注入扫描（仅进度事件）→ P1-4 fixture ≥30 例 + test_overcompliance_prompts.py + scripts/eval_overcompliance.py → P1-5 README/教程说明。验收：fixture 四类齐全；eval 脚本对 qwen3.5:4b 跑一次并把结果表写入 README.md。
P2：P2-1 RAG_SELF_CHECK 开关（默认关；结果为 after 位 notice；系统页/`/stats` 显示开关）→ P2-2 entities 字段 + 前提未命中双轨（进度事件 + before 位 notice + prompt 注入行）。验收：开关关时 complete 次数不变。

## 完成后输出
各 P 级：改动文件清单、新增测试数、覆盖率、验收项逐条结果、未完成/风险。
```

---

## 设计说明
- 事实与研究依据全部放在 REQ §0 并给出行号，提示词只引用，避免 Agent 重新 grep 或重新查论文。
- P0-1 是本轮最大改动（改生成路径），显式放首位并列出受影响的调用方，避免 Agent 只改模板而遗留双重生成。
- P0-5 放在 P0-3 之前：先有 notices 结构与渲染落点，引用校验的展示才不会各端各写一套。
- "模型无关"作为独立规则写出，防止实现时写入 `qwen` 等模型名判断。
- 验收用可机器检查的表述：调用次数、零命中、token 上限、fixture 数量。
