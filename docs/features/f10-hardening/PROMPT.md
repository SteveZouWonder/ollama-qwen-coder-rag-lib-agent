# F10 启动提示词：工程加固与体验升级（按任务分发）

> 用法：按 [REQUIREMENTS.md §6](REQUIREMENTS.md#6-实施顺序与交付) 的顺序，把下方某个「提示词」代码块**整段**贴给 Agent，一次一个任务。
> 需求细节与代码事实都在 `docs/features/f10-hardening/REQUIREMENTS.md`（下称 REQ），
> 提示词只引用章节号，Agent 应先读 REQ 对应章节，**不要重复调研 §0 已核实的事实**。
> 实现记录与差异写入同目录 `README.md`（不写入 REQ）。
>
> 八段提示词各自独立、可单独使用；「规则」已内联在每段中，无需另贴。
> 分支：每个任务开始时 Agent 会询问分支名，建议 `feat/f10-p0-1-safety` 这类 `feat/f10-{编号}-{主题}` 命名。

---

## P0-1 · 命令安全分级修正 + 读路径边界（高，建议最先做）

```
# 任务：F10 P0-1 —— 命令安全分级修正 + 读路径边界

先读 docs/features/f10-hardening/REQUIREMENTS.md：§0.2 是已核实的代码事实（文件:行号），直接采信勿重新调研；§1 P0-1 是本次需求与验收；§5 两端规范。同目录 README.md 记录实现进度。

## 范围
P0-1-a token 级关键字匹配（shlex 分词 + 子命令首 token，保留全部正则）→ P0-1-b 读边界（read_allowed_dirs / is_read_allowed，read_file / list_directory / search_files 越界返错）→ P0-1-c AUTO_CONFIRM 仅放行 low/medium（抽 auto_confirm_allows 供三处复用）→ P0-1-d CLI /config 与 Web 系统页显示允许读 / 写目录。

## 规则
- 先询问是否新建分支及分支名，确认后再改；禁止提交 master；完成后询问是否建 PR，不得自动建。
- 先写 §1 验收列出的复现测试（误报 → low、真危险 → high、读越界、AUTO_CONFIRM 不放行 high）再改代码；原有测试不改断言。
- 不改 registry 工具名 / 参数名；工具描述改动同步 prompts/system/PROJECT_RULES.md 与 docs/development/ai-assistant/TOOL_USAGE.md。
- 新环境变量 READ_ALLOWED_DIRS：config.py 常量 + Config dataclass + README 环境变量表。
- 测试：./venv/bin/python -m pytest -q -n 4，覆盖 ≥80%；tmp_path 隔离；不调真实 Ollama。
- 验证：grep -n 'in command.lower()' src/agent_tools.py 无结果；CLI /config 贴终端输出；Web 系统页截图。

## 完成后
更新 CHANGELOG.md [Unreleased]（修复：误报 / 读边界 / AUTO_CONFIRM；改进：允许目录可见）、README.md 安全说明段与环境变量表、同目录 README.md（状态表 + 实现记录 + 差异 + 验证）。中文 commit（风格见 git log -5）。
输出：改动文件清单、新增测试数、覆盖率、§1 P0-1 验收逐条结果、未完成 / 风险。
```

---

## P0-2 · 依赖钉版本 + 归档发版 + CI 矩阵（高）

```
# 任务：F10 P0-2 —— 依赖钉版本 + 归档发版 + CI 矩阵

先读 docs/features/f10-hardening/REQUIREMENTS.md：§0.3 代码事实直接采信；§1 P0-2 是本次需求与验收。同目录 README.md 记录实现进度。

## 范围
P0-2-a 钉版本（pip freeze 取实际版本 → requirements.txt 全 ==、requirements-build.txt 同步、新增 requirements-dev.txt 并从主文件移出测试 / lint 依赖、install_deps.sh / verify_deps.sh / Makefile / README 安装章节 / ci.yml 安装步骤同步）→ P0-2-b CI（ci.yml 加 pull_request 触发、三 OS 矩阵、覆盖率仅 ubuntu 上传、flake8 仅 E9,F63,F7,F82 阻断、Windows 步骤 shell: bash）→ P0-2-c 归档（scripts/bump_changelog.py 归档为 v0.1.0，ROADMAP 当前版本同步，不打 tag，输出打 tag 命令）。

## 规则
- 先询问是否新建分支及分支名；禁止提交 master；完成后询问是否建 PR，不得自动建。
- 不改 release.yml 与 pr-build-vulnerability-gate.yml 的逻辑；只改 ci.yml 触发 / 矩阵 / 安装步骤。
- 新增 CVE ignore 必须按 ci.yml 现有格式附理由；无理由不得 ignore。
- 验证：bash scripts/verify_deps.sh；pip-audit -r requirements.txt；python -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml'))"；全量 ./venv/bin/python -m pytest -q -n 4。
- 归档后 [Unreleased] 只保留本任务的「发布流程」条目。

## 完成后
CHANGELOG 由归档脚本处理，另在新 [Unreleased] 记「发布流程：依赖钉版本、requirements-dev.txt、CI 三平台矩阵与 PR 触发」；README 安装章节说明 dev 依赖；同目录 README.md（状态 + 实现记录 + 验证）。中文 commit。
输出：版本差异表（包名 / 旧约束 / 新版本）、CI 改动摘要、归档条目数、`git tag` 与 `git push` 命令、未完成 / 风险。
```

---

## P1-1 · 真流式输出（中高，P0 之后）

```
# 任务：F10 P1-1 —— 真流式输出

先读 docs/features/f10-hardening/REQUIREMENTS.md：§0.4 代码事实直接采信（五处非流式调用点、_bridge / StreamEvent、CLI 输出位置）；§2 P1-1 是本次需求与验收；§5 两端规范。同目录 README.md 记录实现进度。

## 范围
P1-1-a 引擎层（_call_model on_token + NDJSON 流；ReActEngine.chat 透传；rag_pipeline 最终合成与 llm_helper.complete_text 可选 on_token）→ P1-1-b LLM_STREAM 配置（默认 true）→ P1-1-c Web（StreamEvent kind token、_bridge 入队、三种模式 Chatbot 增量拼接、心跳仅无事件时、stop_current 关闭 response）→ P1-1-d CLI（/ask /agent /auto 用 rich Live 增量渲染，Ctrl+C 关闭连接）→ P1-1-e 文档。

## 规则
- 先询问是否新建分支及分支名；禁止提交 master；完成后询问是否建 PR，不得自动建。
- 无 on_token 时请求体与行为必须与现在字节级一致；现有测试不改断言。answer 事件仍在最后发完整文本。
- 不改 ReAct 工具协议与 _parse_response。
- 测试：Mock requests.post 的 iter_lines 返回 NDJSON；断言增量拼接 == 返回值、LLM_STREAM=false 单次回调、取消后不再回调且 response.close() 被调；Web 断言 ≥2 个 token 事件后跟 answer + done。./venv/bin/python -m pytest -q -n 4，覆盖 ≥80%。
- 浏览器验证：cd src && ../venv/bin/python -c "import web.app as a; a.launch(server_port=7861)"，三种模式各 3 帧截图 + 停止按钮生效；CLI 贴 /ask 分帧输出；手测首字延迟前后对比。

## 完成后
CHANGELOG.md [Unreleased]（新增：真流式；改进：可中断）、README.md 环境变量表 LLM_STREAM、docs/development/ai-assistant/ARCHITECTURE.md 流式回调路径、同目录 README.md（状态 + 实现记录 + 差异 + 验证 + 首字延迟对比）。中文 commit。
输出：改动文件清单、新增测试数、覆盖率、§2 P1-1 验收逐条结果、未完成 / 风险。
```

---

## P1-3 · RAG 评测集与基准脚本（中，建议在 P1-2 之前建立基线）

```
# 任务：F10 P1-3 —— RAG 评测集与基准脚本

先读 docs/features/f10-hardening/REQUIREMENTS.md：§0.5 代码事实直接采信（检索入口、rerank、编排、F9-1 评测先例的文件结构）；§2 P1-3 是本次需求与验收。同目录 README.md 记录实现进度。参考 scripts/eval_overcompliance.py 与 tests/test_eval_overcompliance_script.py 的结构（fixture + 脚本 + 纯函数单测）。

## 范围
P1-3-a 语料 tests/fixtures/rag_eval_corpus/（≤20 文档，<200KB，无隐私）+ tests/fixtures/rag_eval_cases.json（≥30 条，type 分布见验收）→ P1-3-b src/rag_eval.py 纯函数（recall_at_k / mrr / citation_hit_rate / keyword_hit / negative_rejected / aggregate / render_markdown 含 Δ）→ P1-3-c scripts/eval_rag.py（--hybrid --rerank --top-k --tag --cases --limit --type；tmp 目录建索引；输出 docs/development/rag-eval/reports/{tag}-{date}.md/.json）→ P1-3-d 文档（TEST_DESIGN.md 新章节、TESTING_GUIDELINES.md 指引、README 开发者章节链接）。

## 规则
- 先询问是否新建分支及分支名；禁止提交 master；完成后询问是否建 PR，不得自动建。
- 不改检索 / rerank / 编排逻辑；脚本默认模型读 config；绝不触碰 index_storage/ 与 .cerebro/。
- 单测：tests/test_rag_eval.py 覆盖每个指标正常 / 边界；tests/test_eval_rag_script.py 打桩引擎覆盖参数与 I/O；脚本 main 标 # pragma: no cover。./venv/bin/python -m pytest -q -n 4，覆盖 ≥80%。
- 本地实际用默认模型跑 --hybrid on 与 --hybrid off 各一份报告，提交为基线。

## 完成后
CHANGELOG.md [Unreleased]（新增：RAG 检索基准脚本）、README.md 开发者章节、TEST_DESIGN.md、TESTING_GUIDELINES.md、同目录 README.md（状态 + 实现记录 + 两份基线核心指标）。中文 commit。
输出：样本 type 分布表、两份报告核心指标（Recall@10 / MRR / 引用命中 / 负样本拒答 / 平均延迟）、新增测试数、覆盖率、未完成 / 风险。
```

---

## P1-2 · LLM 后端抽象层（中高，P1-1 完成后）

```
# 任务：F10 P1-2 —— LLM 后端抽象层（Ollama / OpenAI 兼容）

先读 docs/features/f10-hardening/REQUIREMENTS.md：§0.4 代码事实直接采信（五处直连调用点、rag_engine._setup_llm、模型列表 / 健康检查位置、config 常量）；§2 P1-2 是本次需求与验收（含 LLMClient Protocol 签名）。同目录 README.md 中 P1-1 已完成项以它为准（_call_model 的 on_token / NDJSON 流已存在，迁入 OllamaClient 时直接复用）。

## 范围
P1-2-a src/llm_client.py（LLMClient Protocol、OllamaClient、OpenAICompatClient SSE 流 + options 映射、get_llm_client 工厂读 LLM_PROVIDER / LLM_BASE_URL / LLM_API_KEY 并缓存）→ P1-2-b 替换五处直连 + commit_generator 改 chat 格式 + rag_engine openai 模式用 OpenAILike（新依赖 llama-index-llms-openai-like 钉版本，写 requirements*.txt 与 cerebro.spec；嵌入保持 Ollama）→ P1-2-c CLI /models /status、Web 系统页、托盘经 list_models / health，openai 模式列表失败回退 [LLM_MODEL]；bootstrap 引导仅 provider=ollama → P1-2-d 文档。

## 规则
- 先询问是否新建分支及分支名；禁止提交 master；完成后询问是否建 PR，不得自动建。
- 未设 LLM_PROVIDER 时行为与现在字节级一致；现有测试不改断言。完成后 grep -rn '"/api/chat"\|/api/generate' src/ 只出现在 llm_client.py。
- 新环境变量三项：config.py 常量 + Config dataclass + README 环境变量表 + Web 系统页只读展示。
- 测试：两种 client 各覆盖 普通 / 流式 / 超时 / 401 / 5xx / 非法 JSON（Mock requests）；工厂按 env 选择并缓存；commit_generator 两 provider 成功与回退。./venv/bin/python -m pytest -q -n 4，覆盖 ≥80%。
- bash scripts/verify_deps.sh 与 pip-audit 通过。
- 手测：LLM_PROVIDER=openai 指向本地任一兼容服务（LM Studio / vLLM / 简单 mock）跑通 /ask 与 Web 对话并截图。

## 完成后
CHANGELOG.md [Unreleased]（新增：OpenAI 兼容后端）、README.md「接入 OpenAI 兼容后端」章节 + 环境变量表、ARCHITECTURE.md 基础层、MODULE_GUIDES.md、同目录 README.md（状态 + 实现记录 + 差异 + 验证 + 已知限制：嵌入仍需 Ollama、num_ctx 由后端决定）。中文 commit。
输出：改动文件清单、新增测试数、覆盖率、§2 P1-2 验收逐条结果、未完成 / 风险。
```

---

## P2-1 · BM25 持久化增量 + 锁补齐 + 并发限流（中，P1 合入后）

```
# 任务：F10 P2-1 —— BM25 持久化增量 + 锁补齐 + Ollama 并发限流

先读 docs/features/f10-hardening/REQUIREMENTS.md：§0.5 与 §0.6 代码事实直接采信（_ensure_bm25 全量拉取、失效位置、tokenize、RAG_HYBRID_MAX_CHUNKS、两处 lock=None、_execute_parallel）；§3 P2-1 是本次需求与验收。同目录 README.md 中 P1-2 / P1-3 已完成项以它为准（限流放 llm_client；基线报告用于回归对比）。

## 范围
P2-1-a src/bm25_store.py（json.gz 持久化到 index_storage/bm25/、upsert / remove / dirty / 惰性 build、schema_version + TOKENIZER_VERSION、损坏回退、旧库迁移）并接入 rag_engine 增量路径 → P2-1-b 超限可观测（meta.hybrid_disabled_reason；CLI /status 与 Web 知识库页提示；默认上限 50000 + README 内存估算）→ P2-1-c 两处 RLock + 并发测试 → P2-1-d Semaphore(OLLAMA_MAX_CONCURRENCY=2)，master_agent 超时从获得信号量后计时并显示"排队中"。

## 规则
- 先询问是否新建分支及分支名；禁止提交 master；完成后询问是否建 PR，不得自动建。
- 不改 ChromaDB 存储格式与既有 index_storage/ 文件；bm25/ 为新增目录，损坏时 warning + 全量重建。
- 改 _bm25_tokenize 逻辑必须递增 TOKENIZER_VERSION。
- 新环境变量 OLLAMA_MAX_CONCURRENCY：config.py + Config + README 环境变量表。
- 测试（tmp_path 假 collection）：增量结果 == 全量重建；save → load 无需重建；版本变化触发重建；损坏回退；旧库首查后生成 store；16 线程注册 / 调度完整；信号量 1 时 3 个并行子 Agent 串行完成无超时（Mock 慢响应）。./venv/bin/python -m pytest -q -n 4，覆盖 ≥80%。
- 手测：1000 块库入库后首次查询耗时前后对比；若 scripts/eval_rag.py 存在，跑 --hybrid on 与基线对比无回归。

## 完成后
CHANGELOG.md [Unreleased]（改进：BM25 增量持久化、混合检索关闭可见、多 Agent 排队；修复：并发锁）、README.md 环境变量表（OLLAMA_MAX_CONCURRENCY、RAG_HYBRID_MAX_CHUNKS 说明）、MODULE_GUIDES.md 加 bm25_store、同目录 README.md（状态 + 实现记录 + 差异 + 耗时对比 + 评测对比）。中文 commit。
输出：改动文件清单、新增测试数、覆盖率、§3 P2-1 验收逐条结果、未完成 / 风险。
```

---

## P2-2 · 入口层拆分（高复杂度，最后做）

```
# 任务：F10 P2-2 —— 入口层拆分（纯重构，行为零变化）

先读 docs/features/f10-hardening/REQUIREMENTS.md：§0.7 代码事实直接采信（五个大文件的关键符号与行号、pytest.ini omit、测试导入路径）；§3 P2-2 是本次需求与验收（目标目录结构与行数上限）。同目录 README.md 记录已合入的前序任务，以它为准。

## 范围
按 a → b → c 顺序，每个包单独提交并全量测试：
P2-2-a src/web/services.py → src/web/services/{base,chat,knowledge,tools,graph,system}.py mixin 组合，__init__ 重导出全部原公开名
→ P2-2-b src/web/app.py → src/web/formatters.py + src/web/handlers/{chat,knowledge,tools,graph,system}.py + app.py（≤300 行）重导出旧名
→ P2-2-c src/cli_handlers.py → src/cli/handlers/*.py 汇总 COMMAND_HANDLERS；query_interface.py 抽 src/cli/parser.py 与 src/cli/help_text.py，主文件 ≤800 行；两个旧文件保留兼容重导出
→ P2-2-d pytest.ini omit、cerebro.spec hiddenimports、desktop_app 状态探测改用 llm_client.health（若已存在）。

## 规则
- 先询问是否新建分支及分支名；禁止提交 master；完成后询问是否建 PR，不得自动建。
- 纯移动 + 重导出：禁止顺手改逻辑 / 文案 / 修 bug；发现问题写入输出的「待办」。
- 现有测试不改任何断言（只允许改导入路径或依赖兼容重导出）；每次提交后 ./venv/bin/python -m pytest -q -n 4 通过、覆盖 ≥80%。
- 完成后 wc -l 校验 §3 P2-2 行数上限；浏览器冒烟五页无 console error；CLI /help /status /ask 正常。

## 完成后
CHANGELOG.md [Unreleased] 改进一条（内部结构）；ARCHITECTURE.md / MODULE_GUIDES.md / CODE_STANDARDS.md / AGENTS.md 目录职责表同步；同目录 README.md（状态 + 拆分前后行数表 + 提交列表 + 待办）。中文 commit。
输出：拆分前后文件行数表、提交列表、覆盖率、发现的待办问题。
```

---

## P3-1 · Tesseract 跨平台探测 + README 瘦身（低）

```
# 任务：F10 P3-1 —— Tesseract 跨平台探测 + README 瘦身

先读 docs/features/f10-hardening/REQUIREMENTS.md：§0.8 代码事实直接采信；§4 P3-1 是本次需求与验收。同目录 README.md 记录实现进度。

## 范围
P3-1-a config.resolve_tesseract_path（env → shutil.which → 三平台候选 → None）；document_loader / OCR 缺失时明确提示并给安装文档链接；CLI /status 与 Web 系统页显示探测结果；check_prereqs.sh / .ps1 与 bootstrap 一次性提示同步（合并 F5 残留小项"Tesseract 引导提示"）→ P3-1-b README.md ≤400 行，其余按主题迁入 docs/tutorials/0X-*.md（只移动不删除，原位留链接），docs/tutorials/README.md 索引。

## 规则
- 先询问是否新建分支及分支名；禁止提交 master；完成后询问是否建 PR，不得自动建。
- 测试 monkeypatch shutil.which / os.path.exists / sys.platform 覆盖三平台与未找到，OCR 缺失提示用例。./venv/bin/python -m pytest -q -n 4，覆盖 ≥80%。
- 迁移后用脚本校验 README 与 docs/tutorials/*.md 全部相对链接目标存在，结果贴入输出；迁移前后文字总量差 <5%。

## 完成后
CHANGELOG.md [Unreleased]（改进：Tesseract 自动探测与缺失提示；文档：README 精简）、docs/features/README.md 残留小项移除"Tesseract 引导提示"、同目录 README.md（状态改 ✅ + 实现记录 + 验证）、docs/features/README.md（F10 移入已实现）、ROADMAP.md。中文 commit。
输出：探测逻辑测试数、README 前后行数、迁移文件清单、链接校验结果、未完成 / 风险。
```

---

## 设计说明（为什么这样写）
- 需求（REQ）与实现记录（README）分文件：REQ 只增不改；实现差异集中在 README。
- 代码事实全部在 REQ §0 并带行号，提示词只引用章节，避免 Agent 在 2000+ 行文件中重新 grep——这是最主要的 token 节省点。
- 八段按任务而非按 P 级分发：P0-1 / P0-2、P1-1 / P1-2 / P1-3 之间改动面互不重叠，可由不同会话并行推进；P1-2 显式声明依赖 P1-1 产物，P2-1 声明复用 P1-2 / P1-3 产物，P2-2 放最后避免与前序冲突。
- 每段的「范围」用箭头写实施顺序，「规则」只列与 AGENTS.md / 现有工程约束相关的最小集合，「完成后」列全需同步的文档，避免漏更。
- Web 与 CLI 同为一等入口：每个任务的两端落地写在 REQ 需求正文，验证项要求同时贴终端输出与截图。
- 行为零变化类任务（P2-2）与行为变更类任务分开写规则："不改断言"与"先写复现测试"不混用。
