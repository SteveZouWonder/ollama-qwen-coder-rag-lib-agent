# F9: 抗过度顺从与回答可核验性（基于 H-Neurons 研究）

## 实施状态

**🚧 进行中（P0 已完成）** · 分支 `feat/anti-overcompliance`（自 master `d35ac38` 切出）· 目标：在不改模型内部的前提下降低小模型"过度顺从"型幻觉，引用可程序核验，措施随 `/model` 切换生效

| 级别 | 主题 | 完成日期 | 提交 |
|---|---|---|---|
| P0 | 单一综合路径 + 提示词条款 + 结构化提示 notices + 引用程序化校验 + ReAct 事实规则 | 2026-09-07 | （本次提交） |
| P1 | 无依据路径、追问改写、网页注入扫描、评测集与脚本、文档 | — | — |
| P2 | LLM 自校验开关（默认关）、前提实体校验（零新增调用） | — | — |

## 文档导读

| 文件 | 内容 | 适合 |
|---|---|---|
| [REQUIREMENTS.md](REQUIREMENTS.md) | 研究依据、已核实的代码事实（带 `文件:行号`）、需求分项与验收、附录 A 提示词草案 | 了解"要做什么、为什么" |
| 本文件 | 实现记录、与需求的差异、验证结果 | 了解"实际做成了什么" |
| [PROMPT.md](PROMPT.md) | 交给 Agent 的启动提示词（省 token 版，可按 P 级拆多次任务） | 复用本流程做新任务 |

## 范围

| 级别 | 模块 | 内容 |
|---|---|---|
| P0 | RAG / ReAct / CLI / Web | 检索-only 后单次综合（消除 LlamaIndex 默认模板快路径与双重生成）；`FAITHFULNESS_RULES` 常量 + 前提核对/冲突并列/被质疑不改口三条；`notices` 结构化提示（answer 只含正文，CLI 黄色行 / Web blockquote，修掉 fallback 三重冗余）；`verify_citations` 非法编号标 `[?]`、来源 `cited` 次数、状态行/摘要行计数、来源面板明细与自动展开；ReAct「事实规则」 |
| P1 | RAG / 会话 / 评测 | 双空路径先判断是否确知；追问改写不吸收用户断言并识别质疑句式；网页正文注入扫描；≥30 例过度顺从 fixture + Mock 测试 + 真实模型评测脚本；README 模型选择说明 |
| P2 | RAG | `RAG_SELF_CHECK` 逐句自校验（可选）；检索规划 JSON 增 `entities`，未命中时注入前提核对提示 |

研究依据：H-Neurons（arXiv 2512.01797）——幻觉与"过度顺从"因果关联，小模型更敏感，源于预训练；神经元级手段不可迁移，故全部措施在模型外围。

## 实现记录

### P0（2026-09-07）

| 编号 | 实现 | 位置 |
|---|---|---|
| P0-1 检索-only + 单次综合 | `RAGEngine._setup_query_engine` 只构造 `index.as_retriever(similarity_top_k=TOP_K)` 与 `node_postprocessors=[SimilarityPostprocessor(similarity_cutoff)]`（随 `set_model` / `set_think` 重建）；新增 `retrieve_nodes()`；`query_with_sources` 返回 `{"answer": "", "sources", "hybrid"}`，删去 `generating` 事件；`RAGEngine.retriever` 为"已初始化"哨兵，`query_engine` 保留为 property 别名；`rag_pipeline.kb_ready()` 统一判断；`is_empty_rag_result` 只看 `sources`；删除快路径，命中一律 `synthesize_prompt` + `llm_direct_answer`；`_merge_multi_hop` 不再拼接答案；`--query` 单次模式、`RAGEngine.query` / `query_tool` 统一委托 `answer_question(kb_only=True)` | `src/rag_engine.py`、`src/rag_pipeline.py`、`src/query_interface.py`、`src/web/services.py` |
| P0-2 条款收敛 | `rag_pipeline.FAITHFULNESS_RULES`（10 条：既有 7 条 + 前提核对 / 冲突处理 / 被质疑时），`synthesize_prompt` 直接拼接；既有断言子串（`忠实提取`/`不要脑补`/`无法确定`/编号格式）保留 | `src/rag_pipeline.py` |
| P0-5 结构化提示 | `make_notice / notice_lines / answer_with_notices / NOTICE_CODES`；`_finalize_answer` 统一剥离 `<think>`、引用校验、拼装 `notices`；`answer_question` 结果新增 `notices` / `citation_check` / `model`；三处 ⚠️ 前缀与 `fallback_suggestion` 拼接改为 `kb_uninitialized` / `web_only` / `no_evidence`（warn, before）与 `fallback`（info, after）notice。CLI `_print_notices`（warn→yellow `⚠️`、info→dim `💡`，`fallback` 不打印）分别在 Panel 前后调用；Web `format_notices(notices, position)` blockquote 拼入气泡；`presenter.format_notices_md` + `ResultIntegrator.merge_notices`（RAGAgent 经 `metadata["notices"]` 透传）；`agent_tools.format_kb_tool_result` 附 `[注意] …`；CLI / Web 会话记录写 `answer_with_notices()` | `src/rag_pipeline.py`、`src/query_interface.py`、`src/web/app.py`、`src/web/services.py`、`src/collaboration/presenter.py`、`src/collaboration/result_integrator.py`、`src/agents/rag_agent.py`、`src/agent_tools.py` |
| P0-3 引用校验 | `verify_citations(answer, kb_sources, web_sources)`：正则 `(```…```|`…`)|\[(W?\d+)\]` 一次扫描，代码原样保留、非法编号→`[?]`、回填 `cited`；`unsupported_numeric` 按 `。！？\n` 切句、去列表标记、去编号后含 `\d` 且无合法编号；返回 `{"answer","invalid","invalid_count","valid","unsupported_numeric","total_refs"}`；`citation_notices()` 生成 info 级 after 位提示。CLI 摘要行 `📚 基于知识库 N 个片段 · 🔎 引用 v/t 有效`（invalid>0 整行 yellow；仅网络来源时单独一行）、`/sources` 新增「引用」列；Web `format_citation_status`（全有效 `🔎 引用 N 处已核验`）追加到状态行，`format_sources(sources, citation_check)` 标题行末 `（被引用 n 次）` / `_（未被引用）_`、首行 `⚠️ 无效引用：…`；`on_chat_stream` 扩为八元组，第 8 位 `component_update(open=True)` / `component_update()`（等价 `gr.update`，app.py 不 import gradio）；`ui/chat.py` 把 `sources_acc` 加入 `_chat_outputs` | `src/rag_pipeline.py`、`src/query_interface.py`、`src/web/app.py`、`src/web/ui/chat.py`、`src/agent_tools.py` |
| P0-4 ReAct 事实规则 | `SYSTEM_PROMPT_TEMPLATE` 在「安全规则」前插入 `=== 事实规则 ===` 两条（附录 A 原文） | `src/react_engine.py` |

### 与需求的差异

| 项 | 需求文本 | 实际 | 原因 |
|---|---|---|---|
| 哨兵 | "改为检索器或统一 `self.index is not None`" | `retriever is not None`，并保留 `query_engine` property 别名 | 20+ 处调用方与测试桩以 `MagicMock(query_engine=…)` 形式依赖该属性名；别名保证外部代码零改动，源码内全部改用 `retriever` / `kb_ready()` |
| `kb_uninitialized` 无网络子路径 | 仅列出"知识库为空，模型直答" | 同样产生 `kb_uninitialized` warn notice（文案"回答基于模型自身知识，未经资料核实"） | 该路径此前无任何声明；P1-1 会将两条双空路径统一改为 `no_evidence` |
| fallback 路径 | P0 仅列 `fallback` notice | 额外产生 `no_evidence` warn notice（before） | 否则 P0 阶段用户会失去"以下为模型自身知识回答"的可见警示（`fallback` 本身不入 CLI/Web 正文）；亦满足 P0 验收"会话记录含 `[no_evidence]` 行" |
| `verify_citations` 返回 | `{"answer","invalid","unsupported_numeric","total_refs"}` | 额外 `invalid_count`（非法引用出现次数）与 `valid`（合法出现次数） | `invalid` 为去重编号列表，计数行 `v/t` 需要按出现次数统计 |
| Web「未被引用」样式 | dim | Markdown 斜体 `_（未被引用）_` | Gradio Markdown 无 dim 语义，避免内联 HTML 被清洗 |
| 会话记录 | "正文 + 每条 warn 级 notice 一行" | 同 | info 级（引用校验计数、fallback 建议）不写入，避免污染后续轮次的历史上下文 |
| `model` 字段 | `config.LLM_MODEL` | 优先 `rag_engine.llm_model`，回退 `config.LLM_MODEL` | 引擎实例才是热切换后的真值；两者由 `model_switcher` 保持同步 |

## 验证记录

### P0

- 全量测试：`./venv/bin/python -m pytest -q -n 4` → **2750 passed, 36 skipped**，总覆盖率 **89%**（≥80%）。
- 新增 / 改写测试 54 个：`tests/test_rag_pipeline.py`（单次 `llm.complete`、无快路径、`is_empty_rag_result` / `kb_ready` 新语义、`FAITHFULNESS_RULES`、三条路径 notices、`verify_citations` 8 例、`citation_check` / `model`）、`tests/test_rag_engine.py`（检索器构造与 `set_model` 重建、后处理器应用 / 失败保留、进度事件无 `generating`、`query` / `query_tool` 委托）、`tests/test_web_app.py`（`format_notices` / `format_citation_status` / `format_sources` 明细、八元组与 `open=True` 分支、blockquote 顺序、多 Agent notices）、`tests/test_web_services.py`（会话记录含 `[no_evidence]` 行、answer 事件新字段）、`tests/test_cli_handlers_context.py`（warn 行 yellow 且在 Panel 前、after 行在 Panel 后、fallback 不重复、摘要行计数与样式）、`tests/test_query_interface_render.py`（`/sources`「引用」列）、`tests/test_agent_tools_rag.py`（`[注意]` 行 / 无效引用行）、`tests/test_react_engine_prompt_layers.py`（事实规则位置 + ≤1500 token）。
- 验收 grep：`src/` 中 `as_query_engine(` 与 `⚠️ 知识库中无相关内容` 字面量均为 0 命中。
- 浏览器验证（Gradio 7861 + Playwright Chrome headless，真实 Ollama `qwen3.5:4b`）：
  - 问「Cloudflare Tunnel 如何配置 ingress 规则？」（联网关）：状态行 `✅ 完成 · 用时 31 秒 · 上下文 1.1K / 4.9K · 🔎 引用 13 处已核验`；气泡末尾 blockquote `💡 3 句含数字但未标来源`；来源面板每条 `（被引用 3 次）` / `（未被引用）`；console error 0。截图 `/tmp/f9shots/03_kbhit.png`。
  - 问「莎士比亚的《哈姆雷特》第一幕讲了什么？」：模型按第 8 条回答「资料未提及…」（前提核对条款生效），`🔎 引用 2 处已核验`，console error 0。

（P1 / P2 完成后在此追加：`scripts/eval_overcompliance.py` 对比表、开关截图。）
