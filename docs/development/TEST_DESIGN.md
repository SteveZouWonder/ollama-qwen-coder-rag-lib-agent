# 单元测试设计方案（初版，2026-06）

> **现状说明**：本文是项目初期（7 个核心模块）的测试设计，其中的模块行数、"≥95%" 目标与
> 13 个测试文件清单均已过时。现行约束以代码为准：
> - 覆盖率门禁 **80%**（`pytest.ini` 的 `--cov-fail-under=80`），CI 上传 codecov
> - 运行方式 `./venv/bin/python -m pytest -q -n 4`
> - 测试清单见 `tests/`（50+ 文件，含 `tests/multi_agent/`、`tests/test_command_recommender/`）
>
> 保留本文是因为第 2、4 节的 **Mock 策略**（Ollama / ChromaDB / LlamaIndex / `requests.post` /
> `HAS_RICH`）与"抽离纯函数以提升可测性"的思路仍是新增测试时的参考。

## 1. 覆盖率目标（初版）

| 模块 | 行数 | 目标覆盖率 | 策略 |
|------|------|-----------|------|
| `config.py` | 55 | **100%** | 环境变量分支全覆盖 |
| `chat_history.py` | 50 | **100%** | 文件IO + 截断逻辑 |
| `agent_tools.py` | 297 | **≥ 95%** | 安全分析器 + 文件工具 + Registry + RAG工具 |
| `document_loader.py` | 145 | **≥ 90%** | Mock 读取器 + 文件发现 |
| `rag_engine.py` | 274 | **≥ 90%** | Mock 外部依赖 + Agent 接口 |
| `react_engine.py` | 296 | **≥ 90%** | Mock HTTP + 解析逻辑 + 安全拦截 |
| `query_interface.py` + `cli/*.py` | 563 + 1929（F10 P3-2 后：`state` 78 / `parser` 252 / `help_text` 251 / `render` 283 / `callbacks` 174 / `rag_adapter` 116 / `recommend` 108 / `engine_commands` 649） | **≥ 85%** | 纯函数 `cli.parser`；渲染 / 回调 / 引擎命令经 `patch("cli.state.console")` 等打桩实现模块 |
| **整体** | 1836 | **≥ 95%** | 不含 example.py |

---

## 2. 技术选型

```
pytest              # 测试框架
pytest-cov          # 覆盖率报告
unittest.mock       # Mock（标准库，不引入新依赖）
tempfile / pathlib  # 文件系统隔离
```

---

## 3. 目录结构

```
tests/
├── __init__.py
├── conftest.py                    # 共享 fixture
├── test_config.py                 # 配置读取（100%）
├── test_chat_history.py           # 对话历史（100%）
├── test_agent_tools_safety.py     # 安全分析器（参数化覆盖所有模式）
├── test_agent_tools_registry.py   # ToolRegistry
├── test_agent_tools_file.py       # 文件/目录/搜索工具（临时目录）
├── test_agent_tools_rag.py        # RAG 工具（注入 Mock 引擎）
├── test_document_loader.py        # 文档加载（Mock 读取器）
├── test_rag_engine.py             # RAG 引擎（Mock Ollama/ChromaDB/LlamaIndex）
├── test_react_engine.py           # ReAct 引擎（Mock requests.post）
├── test_query_interface_parse.py  # 命令解析（100% 覆盖所有分支）
└── test_cli_render.py             # 渲染 / 回调函数（Mock cli.state.HAS_RICH；原 test_query_interface_render.py）
```

---

## 4. 关键测试策略

### query_interface.py / cli/ — 抽离纯函数后可达 85%+

`cli/parser.py` 的 `ParsedCommand` 类、`parse_command()`、`classify_mode()` 三个纯函数：
- `parse_command`：覆盖所有 20+ 命令分支 + 空输入 + 未知命令 + 自然语言
- `classify_mode`：覆盖所有 cmd_type × rag_engine_available 组合
- 渲染函数（`cli/render.py`）：`print_banner`, `print_help`, `print_tools`, `print_rag_sources`, `print_knowledge_stats` — `patch("cli.state.HAS_RICH")` 为 True/False 分别测试，控制台用 `patch("cli.state.console")`
- 引擎耦合命令（`cli/engine_commands.py`）：`handle_*` 直接调用；引擎 / 来源打 `cli.state.rag_engine` 等，协作函数（`record_command_execution` / `_health_before` …）打 `cli.engine_commands.<name>`（**搬到哪个模块就打那个模块**，F10 P3-2）

### agent_tools.py — 安全分析器参数化

`CommandSafetyChecker.analyze()` 用 `@pytest.mark.parametrize` 覆盖：
- 全部 12 个 DANGEROUS_PATTERNS
- 全部 25 个 READONLY_PATTERNS
- high 风险关键词：`rm`, `del`, `drop`, `truncate`, `format`
- medium 风险关键词：`mv`, `cp`, `chmod`, `write`
- low 风险：其他命令
- 边界：`sudo rm file`（high 非 critical）、`rm -rf /tmp`（high 非 critical）

### react_engine.py — Mock HTTP + 迭代控制

- `_call_model()`：正常响应 / ConnectionError / Timeout / 异常
- `chat()`：
  - 无 Action → 直接 Final Answer
  - 有 Action → 解析 Thought/Action/Action Input
  - 危险命令 → 拦截（不执行）
  - 需确认 → 用户拒绝 / 用户确认
  - 达到 MAX_ITERATIONS → 返回警告
- `_init_system()`：首次运行注入 system prompt

### rag_engine.py — Mock 重型依赖

- `__init__`：Mock `Ollama`, `OllamaEmbedding`, `chromadb.PersistentClient`
- `build_index`：验证 `SentenceSplitter` 参数、调用 `persist`
- `load_index`：存在/不存在两种情况
- `query_tool` / `add_document_tool` / `get_stats_tool`：验证返回值格式
- `clear_index`：验证 collection 重建
- `RAGEngine(persist_dir=tmp)`（F10 P1-3）：Chroma / `llama_index` / 快照目录全部落在 `persist_dir`，不传时与 config 一致

---

## 5. 运行方式

```bash
# 全部测试 + 覆盖率
pytest tests/ -v --cov=. --cov-report=term-missing --cov-fail-under=95

# 只测纯逻辑（零外部依赖）
pytest tests/test_agent_tools_safety.py tests/test_chat_history.py tests/test_config.py tests/test_query_interface_parse.py -v

# 排除需要复杂 Mock 的测试
pytest tests/ -v -k "not integration"
```

---

## 6. 实施顺序

```
Phase 1（零依赖，立即可跑）
  ├── test_config.py
  ├── test_chat_history.py
  ├── test_agent_tools_safety.py
  ├── test_agent_tools_registry.py
  └── test_query_interface_parse.py

Phase 2（临时目录 / 简单 Mock）
  ├── test_agent_tools_file.py
  ├── test_agent_tools_rag.py
  └── test_document_loader.py

Phase 3（重型 Mock）
  ├── test_rag_engine.py
  ├── test_react_engine.py
  └── test_cli_render.py
```

---

## 7. RAG 检索基准（F10 P1-3，2026-09）

单测只能证明"管道没崩"，证明不了"改了阈值以后检索质量没退步"。`scripts/eval_rag.py` 用一份仓库自带的小语料
对真实 Ollama 跑一遍完整检索 + 问答，产出可对比的指标报告。**需要本机 Ollama，不进 CI**；纯函数部分
（`src/rag_eval.py`）与脚本的参数 / I/O 由 `tests/test_rag_eval.py`、`tests/test_eval_rag_script.py` 在 CI 中覆盖。

### 7.1 组成

| 文件 | 内容 |
|---|---|
| `tests/fixtures/rag_eval_corpus/` | 18 个小文档（13 个 md、含表格 / 2 个 txt / 5 个 py，共约 36 KB）：虚构的 **Lumen 任务调度库**的文档与代码，无隐私、无外部依赖 |
| `tests/fixtures/rag_eval_cases.json` | 38 条样本，`{"cases": [{id, question, type, expected_files, expected_keywords, notes}]}` |
| `src/rag_eval.py` | 打分纯函数：`recall_at_k / mrr / citation_hit_rate / keyword_hit / negative_rejected / evaluate_case / aggregate / render_markdown`；样本 `load_cases / validate_cases / type_distribution`；F9-1 的 `HEDGE_WORDS / PREMISE_WORDS / HOLD_WORDS` 词表也定义在这里（`scripts/eval_overcompliance.py` 从此导入） |
| `scripts/eval_rag.py` | 在临时目录 `RAGEngine(persist_dir=<tmp>)` 建索引 → 逐例 `query_with_sources` + `answer_question(kb_only=True)` → 写报告；`--rerank none` 时在本进程把 `rag_rerank.rerank` 打成恒等 |
| `docs/development/rag-eval/reports/{tag}-{YYYYMMDD}.md / .json` | 报告；同 tag 存在上一份 `.json` 时 Markdown 各指标附 Δ |

### 7.2 样本格式

```json
{
  "id": "m01-retry-then-dead",
  "question": "retry_limit 默认是多少次？超过后任务会进入哪个 Redis 键？",
  "type": "multi_hop",
  "expected_files": ["03-configuration.md", "05-retry-policy.md"],
  "expected_keywords": ["3", "lumen:dead"],
  "notes": "配置 + 重试策略"
}
```

- `type`：`single`（答案在一个文件）/ `multi_hop`（需两个以上文件）/ `code_symbol`（问函数 / 类 / 常量，期望命中 `.py`）/
  `meta`（"知识库里有哪些文档"，期望编排层识别为元查询、不检索）/ `negative`（语料没有答案，期望拒答）。
- `expected_files`：语料文件名（basename，大小写不敏感）。**列出所有直接包含答案的文件**——Recall 是标准定义
  （命中数 / 期望数），少列会虚高、多列会虚低。`meta` / `negative` 留空。
- `expected_keywords`：答案里应出现的词；`"misfire_grace|60"` 表示任一出现即命中。比较前做归一化
  （小写、去空白 / 千分位逗号 / 斜杠 / 连字符 / 下划线），所以 `20,000` 与 `20000`、`_ensure_bm25` 与 `ensure bm25` 等价。
- 当前分布：single 15 / multi_hop 7 / code_symbol 7 / meta 4 / negative 5（验收下限 12 / 6 / 5 / 3 / 4）。

**加样本**：在 `cases` 末尾追加一条，`id` 用 `s / m / c / meta / n` 前缀 + 序号 + 简短英文；跑
`./venv/bin/python -m pytest tests/test_rag_eval.py -q --no-cov -k fixture` 会校验 id 唯一、type 合法、
`expected_files` 存在于语料目录、分布满足下限。**加语料**：放进 `rag_eval_corpus/`（保持 ≤20 个文件、总量 <200 KB），
再为它写至少一条 single 样本；改动语料后所有历史报告不再可比，请换新 tag。

### 7.3 指标含义

| 指标 | 定义 | 适用 type |
|---|---|---|
| Recall@k | `query_with_sources` 前 k 个来源（按文件去重）覆盖 `expected_files` 的比例 | 检索类三种 |
| MRR | 第一个命中期望文件的来源的倒数排名；无命中 0 | 检索类 |
| 引用命中 | 答案中 `[n]` 引用（去重，忽略代码块与 `[W1]`）指向期望文件的比例；编号越界 / 无引用计 0 | 检索类 |
| 关键词命中 | `expected_keywords` 在答案中出现的比例 | 检索类 |
| 负样本拒答 | 无来源、答案为空、或答案含 `REJECT_WORDS`（`HEDGE_WORDS ∪ HOLD_WORDS`）任一词 | negative |
| 元查询识别 | `answer_question` 返回 `kind == "meta"` | meta |
| 平均延迟 | 单例「检索 + 问答」总秒数（含规划 / rerank / 生成；JSON 明细另有 `retrieval_seconds` / `answer_seconds`） | 全部 |
| 通过 | 检索类：Recall@k > 0 且关键词命中 ≥ 0.5（无关键词时不要求）；meta：被识别；negative：被拒答 | 全部 |

不适用的指标为 `—`；`aggregate` 按 type 分组求均值（None 不计入）再给合计。

### 7.4 何时必须跑

改动以下任一处，提 PR 前用**同一模型**各跑一次 `--hybrid on` 与 `--hybrid off`，把报告提交到
`docs/development/rag-eval/reports/` 并在 PR 描述里贴合计行（含 Δ）：

- `src/rag_engine.py`（检索 / BM25 / RRF / 分块入库）、`src/rag_rerank.py`、`src/rag_pipeline.py`（规划 / 过滤 / 综合 prompt / 引用校验）、`src/code_chunker.py`；
- 检索阈值与参数：`TOP_K`、`SIMILARITY_CUTOFF`、`KB_RELEVANCE_THRESHOLD`、`CHUNK_SIZE / CHUNK_OVERLAP`、`RAG_HYBRID*`、`RERANKER`、`CONFIDENT_SCORE`；
- 换默认模型或嵌入模型。

```bash
./venv/bin/python scripts/eval_rag.py --hybrid on  --tag hybrid-on
./venv/bin/python scripts/eval_rag.py --hybrid off --tag hybrid-off
./venv/bin/python scripts/eval_rag.py --hybrid on --rerank none --top-k 5 --tag dense-k5   # 试验性配置用新 tag
./venv/bin/python scripts/eval_rag.py --type negative --limit 3 -v                          # 调试单类
```

默认模型下 38 例约 15 分钟一份。判读：Recall@k / MRR 反映**检索**（改 `rag_engine` / 分块 / hybrid 看这两列）；
引用命中 / 关键词命中反映**综合与引用**（改 prompt / rerank 看这两列）；负样本拒答下降说明 rerank 或 prompt 变"顺从"；
平均延迟看 rerank / 规划调用数的变化。同一模型的逐例 Δ 以 ±0.05 以内视为噪声（4B 模型在 temperature 0.1 下仍有波动）。

### 7.5 单测怎么写

- 指标函数：直接构造 `sources` 列表（`{"file", "ref"}`）与答案字符串，覆盖空来源 / 重复来源 / 多跳部分命中 / 编号越界 /
  negative 有来源等边界（见 `tests/test_rag_eval.py`）。
- 脚本：`importlib` 加载 `scripts/eval_rag.py`，monkeypatch `rag_engine.RAGEngine`、`document_loader.load_documents`、
  `rag_pipeline.answer_question` 为桩；`write_reports` 用 `tmp_path` 验证首份无 Δ、第二份有 Δ、同日重跑排除自身
  （见 `tests/test_eval_rag_script.py`）。`main()` 标 `# pragma: no cover`。
