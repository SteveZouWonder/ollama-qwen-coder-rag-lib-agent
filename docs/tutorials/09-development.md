# 开发者指南：项目结构、核心模块 API 与测试

> 本文汇集 README 中迁出的开发者章节（F10 P3-1，2026-09-09）。AI 编码助手的项目知识见
> [docs/development/ai-assistant/](../development/ai-assistant/README.md)，协作规则见 [AGENTS.md](../../AGENTS.md)。

---

## 项目结构

```
ollama-qwen-coder-rag-lib/
├── config.py              # 统一配置（RAG + Agent + OCR）
├── document_loader.py     # 多格式文档加载器（支持 OCR）
├── ocr_processor/         # OCR 处理模块
│   ├── base.py            # OCR 抽象基类
│   ├── paddle_ocr.py      # PaddleOCR 引擎实现
│   ├── tesseract_ocr.py   # Tesseract OCR 引擎实现
│   ├── image_extractor.py # PDF 图片提取器
│   ├── preprocessor.py    # 图像预处理器
│   └── cache.py           # OCR 结果缓存
├── rag_engine.py          # RAG 核心引擎（向量索引 + Agent 工具接口）
├── react_engine.py        # ReAct 推理引擎（qwen3.5:4b，支持运行时热切换）
├── llm_client.py          # LLM 后端抽象：Ollama /api/chat 与 OpenAI 兼容 /v1/chat/completions（LLM_PROVIDER）
├── model_switcher.py      # 模型热切换（校验/同步引擎/释放旧模型，CLI 与 Web 共用）
├── optional_deps.py       # 可选模块探测（区分未安装 / 装了但导入出错）
├── agent_tools.py         # 工具链（文件/命令/搜索 + RAG 查询/添加）
├── conversation_context.py # 连续对话上下文（会话记忆、token 预算、滚动压缩、追问改写）
├── query_interface.py     # 统一 CLI 入口（解释器自保护 / 日志 / 输入 / main；重导出 cli.* 公开名）
├── cli/                   # CLI 入口层子包：state.py 共享状态 · parser.py 命令路由 · help_text.py 帮助与教程 · render.py 渲染 · callbacks.py 回调 · rag_adapter.py RAG 适配 · recommend.py 命令推荐 · engine_commands.py 引擎耦合命令与分发 · handlers/ 命令处理器（COMMAND_HANDLERS）
├── cli_handlers.py        # 兼容重导出（实现已迁至 cli/handlers/）
├── web/                   # Web 入口层：services/ 业务门面（唯一接引擎）· formatters.py 纯格式化 · handlers/ 页面处理器 · app.py 汇总与装配 · ui/ Gradio 接线
├── knowledge_to_skills.py # 知识库到Skill智能转化引擎
├── knowledge_snapshot.py  # 知识库快照系统
├── content_security.py    # 内容安全扫描器（防止提示词攻击）
├── file_validator.py      # 文件上传验证器（NEW）
├── file_metadata.py       # 文件元数据管理（NEW）
├── session_manager.py     # 会话管理器（NEW）
└── history_compressor.py  # 历史压缩器（NEW）
├── agents/               # Agent模块目录
│   ├── agent_types.py     # Agent基础数据类型
│   ├── base_agent.py     # Agent抽象基类
│   ├── code_agent.py     # 代码专家Agent
│   ├── rag_agent.py      # 知识库专家Agent
│   ├── test_agent.py     # 测试专家Agent
│   ├── doc_agent.py      # 文档专家Agent
│   └── audit_agent.py    # 审计专家Agent
├── collaboration/         # 协作机制目录
│   ├── task_decomposer.py    # 任务分解器
│   ├── task_scheduler.py     # 任务调度器
│   ├── result_integrator.py  # 结果整合器
│   └── message_bus.py        # 消息总线
├── agent_registry.py      # Agent注册中心
├── master_agent.py        # 主控Agent
├── agent_orchestrator.py  # Agent编排器
├── agent_config.py        # Agent配置管理
├── examples/               # 示例代码
│   └── example.py         # 快速示例
├── requirements.txt       # 运行时依赖（全部钉版本）
├── requirements-dev.txt   # 开发/测试依赖（pytest、flake8、bandit、pip-audit…）
├── requirements-build.txt # 打包依赖（PyInstaller 发布用）
├── data/                  # 文档存放目录
├── index_storage/         # 索引持久化存储
│   ├── chroma_db/         # ChromaDB 向量数据库
│   └── llama_index/       # LlamaIndex 索引文件
├── docs/                  # 文档目录（索引见 docs/README.md）
│   ├── tutorials/        # 用户教程
│   ├── features/         # 功能设计与实现记录（f1–f8）、路线图
│   ├── development/      # CI/CD、测试设计、内容安全、文档流程
│   │   └── rag-eval/reports/  # RAG 检索基准报告（scripts/eval_rag.py 输出）
│   ├── history/          # 历史修复报告
│   └── assets/           # 演示 GIF
├── scripts/               # 脚本文件
│   ├── check_prereqs.sh   # 前置条件检查脚本
│   ├── install_deps.sh    # 依赖安装脚本
│   ├── verify_deps.sh     # 依赖验证脚本
│   ├── eval_overcompliance.py  # 忠实性（抗过度顺从）评测，需本机 Ollama
│   └── eval_rag.py        # RAG 检索基准（Recall@k / MRR / 引用 / 拒答 / 延迟），需本机 Ollama
├── tests/                 # 单元测试
│   ├── fixtures/         # 评测样本与小语料（rag_eval_cases.json、rag_eval_corpus/、overcompliance_cases.json）
│   └── multi_agent/      # 多Agent系统测试
└── README.md
```

---

## Python 路径设置

项目代码已重构到 `src/` 目录。在使用示例代码时，需要确保 Python 能找到模块：

**方法1：设置 PYTHONPATH（推荐）**
```bash
export PYTHONPATH="${PYTHONPATH}:$(pwd)/src"
```

**方法2：在代码中添加路径**
```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
```

**方法3：使用项目提供的脚本**
```bash
python src/query_interface.py  # 直接运行 src 目录下的脚本
```

---

## 核心模块说明

### `rag_engine.py` — RAG 引擎

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from rag_engine import build_knowledge_base

# 一键构建知识库
engine = build_knowledge_base("./data")

# 查询（走共享编排层的忠实性 prompt，只用知识库）
answer = engine.query("什么是注意力机制？")

# 检索-only：只返回来源（F9 起 answer 恒为空串，答案由 rag_pipeline 单次综合）
result = engine.query_with_sources("RAG 的优势是什么？")
for src in result["sources"]:
    print(f"来源: {src['file']} (相似度: {src['score']:.3f})")

# 完整问答（答案 + 编号来源 + 引用校验 + 结构化提示）
from rag_pipeline import answer_question
out = answer_question(engine, "RAG 的优势是什么？", enable_web_search=False)
print(out["answer"], out["citation_check"], out["notices"])

# Agent 工具接口
print(engine.query_tool("论文结论是什么？"))
print(engine.add_document_tool("./新论文.pdf"))
```

### `react_engine.py` — ReAct 推理引擎

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from react_engine import ReActEngine

engine = ReActEngine()
answer = engine.chat("写一个快速排序并测试")
print(answer)

# 查看执行步骤
print(engine.get_step_summary())
```

### `agent_tools.py` — 工具链

| 工具 | 安全等级 | 说明 |
|------|----------|------|
| `read_file` | 安全 | 读取文件内容 |
| `write_file` | 需确认 | 写入/追加文件 |
| `execute_command` | 需确认 | 执行 shell 命令 |
| `list_directory` | 安全 | 列出目录 |
| `search_files` | 安全 | 代码搜索 |
| `query_knowledge_base` | 安全 | 查询知识库 |
| `add_to_knowledge_base` | 需确认 | 添加文档 |
| `get_knowledge_stats` | 安全 | 知识库统计 |

### `document_loader.py` — 文档加载

> **注意**：以下所有示例代码都需要先设置 Python 路径：
> ```python
> import sys
> from pathlib import Path
> sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
> ```

```python
from document_loader import load_documents

# 加载整个目录
docs = load_documents("./data")

# 加载指定类型
docs = load_documents("./data", file_types=[".pdf", ".md"])

# 加载单个文件
docs = load_documents("./论文.pdf")
```

### 🆕 `agents/` — 专业Agent模块

```python
from agent_orchestrator import AgentOrchestrator
from agent_config import AgentConfigManager

# 使用多Agent系统
config = AgentConfigManager.get_default_config()
orchestrator = AgentOrchestrator(config)

# 并行协作模式
result = orchestrator.process_request(
    "实现用户认证功能并测试",
    CollaborationMode.PARALLEL
)
```

**专业Agent类型：**
- `CodeAgent` - 代码生成、重构、审查、调试
- `RAGAgent` - 知识库检索、文档分析、文献综述
- `TestAgent` - 测试生成、覆盖率分析、质量评估
- `DocAgent` - 文档编写、API文档、用户指南
- `AuditAgent` - 安全检查、合规验证、性能审计

### 🆕 `collaboration/` — 协作机制模块

- `TaskDecomposer` - 智能任务分解
- `TaskScheduler` - 灵活任务调度
- `ResultIntegrator` - 结果整合和报告
- `MessageBus` - Agent间消息通信

### 🆕 `agent_orchestrator.py` — Agent编排器

```python
from agent_orchestrator import AgentOrchestrator
from agent_config import AgentConfigManager

# 自定义配置
config = AgentConfigManager.create_custom_config(
    model="qwen3.5:9b",  # 不传则跟随全局 LLM_MODEL
    max_parallel_tasks=8,
    default_mode="parallel"
)

orchestrator = AgentOrchestrator(config)
status = orchestrator.get_status()
```

---

## 测试

项目使用 pytest 进行单元测试，测试覆盖了所有核心功能。

### 测试策略

**完整测试套件**：项目支持完整的测试套件运行，所有测试都能通过。

```bash
# 完整测试套件（排除集成测试和Tesseract相关测试）
pytest tests/ -k "not integration and not tesseract" -v
```

### 测试脚本

项目提供了多种测试运行脚本：

```bash
# 使用测试脚本
./run_tests.sh

# 分批模式
./run_tests.sh batch

# 并行模式
./run_tests_parallel.sh

# 覆盖率模式
./run_tests.sh coverage
```

### 测试覆盖率

项目要求测试覆盖率 ≥ 80%（`pytest.ini` 的 `--cov-fail-under=80`，CI 同步）。

```bash
# 检查覆盖率
pytest tests/ --cov=src --cov-report=term-missing

# 生成HTML覆盖率报告
pytest tests/ --cov=src --cov-report=html
# 打开 htmlcov/index.html 查看详细报告
```

### 测试架构

- **tests/test_rag_engine.py** - RAG引擎测试
- **tests/test_react_engine.py** - ReAct推理引擎测试
- **tests/test_agent_tools_*.py** - 工具链测试
- **tests/test_knowledge_*.py** - 知识管理测试
- **tests/test_query_interface_*.py / test_cli_*.py** - CLI 入口与命令处理器测试
- **tests/multi_agent/** - 多Agent系统测试
- **tests/test_web_search.py** - 网络搜索功能测试
- **tests/test_ocr_*.py** - OCR功能测试

详细测试文档请查看：[TESTING.md](../../TESTING.md)

### RAG 检索基准（改检索 / rerank / 分块参数前后必跑）

单测证明不了"改了阈值以后检索质量没退步"。`scripts/eval_rag.py` 用仓库自带的小语料
（`tests/fixtures/rag_eval_corpus/`，18 个虚构项目文档 + 代码）与 38 条样本
（`tests/fixtures/rag_eval_cases.json`：单文档 / 多跳 / 代码符号 / 元查询 / 负样本），对真实 Ollama 跑一遍
完整检索 + 问答，输出 Recall@k、MRR、引用命中、关键词命中、负样本拒答、元查询识别与平均延迟：

```bash
./venv/bin/python scripts/eval_rag.py --hybrid on  --tag hybrid-on      # 约 15 分钟（qwen3.5:4b）
./venv/bin/python scripts/eval_rag.py --hybrid off --tag hybrid-off
./venv/bin/python scripts/eval_rag.py --hybrid on --rerank none --top-k 5 --tag dense-k5   # 试验配置用新 tag
./venv/bin/python scripts/eval_rag.py --type negative --limit 3 -v                          # 调试单类
```

索引建在临时目录（`RAGEngine(persist_dir=<tmp>)`），**不触碰 `index_storage/` 与 `.cerebro/`**；报告写到
`docs/development/rag-eval/reports/{tag}-{日期}.md / .json`，同 tag 有上一份时每个指标附 Δ。基线报告已随仓库提交。
样本格式、指标含义、何时必须跑见 [TEST_DESIGN.md §7](../development/TEST_DESIGN.md#7-rag-检索基准f10-p1-32026-09)。

---

**上一篇**: [配置参考](08-configuration.md) | **返回目录**: [README](README.md)
