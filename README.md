# Cerebro 🧠 — 你的第二大脑 + 代码助手 v4.1

> *Cerebro* —— 拉丁语「大脑」。一个完全本地运行的智能体，把你的知识库变成可检索的「第二大脑」，并让 AI 帮你读写代码、执行任务。

基于 **Ollama qwen2.5-coder:7b** 的融合型 AI 助手，同时支持 **RAG 知识库检索**、**ReAct Agent 代码操作** 和 **多Agent 协作系统**。

---

## 融合架构

```
┌─────────────────────────────────────────────────────────────────────┐
│                        统一 CLI 交互层                               │
│         /ask /agent /multi-agent  /file /exec ...                     │
│         智能命令推荐系统 (工作流+状态+历史混合推荐)                  │
└─────────────────────────────────────────────────────────────────────┘
                              │
          ┌───────────────────┴───────────────────┐
          ▼                                       ▼
┌─────────────────────────────┐    ┌─────────────────────────────┐
│      📚 RAG 知识库引擎       │    │      🤖 Agent 系统          │
│  LlamaIndex + ChromaDB      │    │  ┌─────────────────────────┐  │
│  语义检索 + 来源追溯         │    │  │  Multi-Agent Orchestrator│ │
│  PDF/论文/笔记/代码          │    │  └─────────┬───────────────┘  │
└─────────────────────────────┘    │            │              │
          │                           │    ┌───────┴──────┐         │
          └───────────────────┬───────────┘    │  MasterAgent  │         │
                              ▼              │  (主控Agent)  │         │
┌─────────────────────────────────────────────────────────────┐    │  └───────┬──────┘         │
│      🤖 ReAct Agent 引擎    │    │          │              │
│  Thought → Action → Observe │    │    ┌─────┴────┬─────┐      │
│  自动工具调用 + 安全护栏      │    │    │ CodeAgent│RAGAgent│      │
│  读写文件 / 执行命令 / 搜索  │    │    │ (代码专家)│(知识库)│      │
└─────────────────────────────┘    │    ├─────────┼───────┤      │
          │                           │    │ TestAgent│DocAgent│      │
          └───────────────────┬───────────┘    │ (测试专家)│(文档)│      │
                              ▼              ├─────────┼───────┤      │
┌─────────────────────────────────────────────────────────────┐    │AuditAgent│      │
│                     Ollama qwen2.5-coder:7b                         │    │ (审计专家)│      │
│              统一 LLM：文档理解 + 代码生成 + 推理 + 协作               │    └─────────┴───────┘      │
│              Embedding: nomic-embed-text (语义编码)                 │                             │
└─────────────────────────────────────────────────────────────┘                             │
          ┌──────────────────────────────┴─────────────────────────┐
          │                    协作机制                                 │
          │  MessageBus (消息总线) + AgentRegistry (注册中心)       │
          │  TaskDecomposer (任务分解) + TaskScheduler (调度)       │
          │  ResultIntegrator (结果整合) + 4种协作模式              │
          └─────────────────────────────────────────────────────────┘
```

---

## 使用场景

### 🎓 学术研究
- **论文分析**: 查询论文核心贡献、方法论、实验结果
- **笔记整理**: 跨文档查询知识点，生成复习提纲
- **文献综述**: 对比多篇论文观点，识别研究趋势

### 💻 代码开发
- **自动生成**: 根据需求生成功能代码和测试用例
- **代码重构**: 优化代码结构，提高可读性和性能
- **调试修复**: 定位bug，生成测试，验证修复

### 📚 文档分析
- **技术理解**: 快速理解复杂技术文档和API说明
- **知识提取**: 从文档中提取配置参数和操作步骤
- **文档生成**: 基于代码生成API文档和使用指南

### 🛠️ 项目维护
- **代码搜索**: 搜索特定功能实现和调用关系
- **配置管理**: 统一配置格式，验证配置正确性
- **代码审查**: 检查代码质量，提供改进建议

### 🎯 数据处理
- **日志分析**: 分析服务器日志，识别问题和趋势
- **数据分析**: 分析数据集特征，生成探索报告
- **数据迁移**: 转换数据格式，处理数据清洗

### 🚀 运维自动化
- **部署脚本**: 生成自动化部署和监控脚本
- **故障排查**: 分析错误日志，提供解决方案
- **配置迁移**: 系统升级时的配置转换和验证

### 🖼️ OCR 图像识别 (NEW)
- **扫描版 PDF**: 自动识别扫描版 PDF 中的文本内容
- **图片文件**: 支持 PNG、JPG、JPEG、GIF、BMP、TIFF 等格式
- **中英文混合**: 基于 PaddleOCR 实现高精度的中英文识别
- **PDF 图片提取**: 自动提取 PDF 中的嵌入图片并进行 OCR 识别
- **智能缓存**: 基于文件哈希的缓存机制，避免重复处理
- **并行处理**: 支持批量图片并行处理，提升处理效率

### 🧠 智能命令推荐系统 (NEW)
- **混合推荐**: 基于工作流分析、状态感知、历史分析的智能推荐
- **上下文感知**: 根据当前系统状态和使用历史推荐最相关的命令
- **个性化学习**: 学习用户偏好，随时间优化推荐策略
- **CLI集成**: 在命令行界面显示智能建议功能
- **可配置性**: 支持自定义推荐权重、显示选项和过滤规则

---

## 快速开始

### 前置条件检查（推荐）

在开始之前，建议运行前置条件检查脚本：

**Linux/macOS:**
```bash
./scripts/check_prereqs.sh
```

**Windows:**
```powershell
.\scripts\check_prereqs.ps1
```

如果检查通过，继续以下步骤。如果有问题，请参考 [详细使用教程](TUTORIAL.md#前置条件检查与配置)。

### 1. 环境准备

```bash
# 安装 Ollama（如未安装）
curl -fsSL https://ollama.com/install.sh | sh

# 拉取模型
ollama pull qwen2.5-coder:7b
ollama pull nomic-embed-text:latest
```

### 2. 安装依赖

**推荐方法：使用专用安装脚本（避免依赖冲突）**
```bash
./scripts/install_deps.sh      # Linux/macOS
.\scripts\install_deps.ps1     # Windows PowerShell
```

**标准方法：**
```bash
pip install -r requirements.txt
```

**如果遇到依赖冲突（如 "resolution-too-deep" 错误）：**
```bash
# 使用 --no-cache-dir 选项
pip install -r requirements.txt --no-cache-dir

# 或查看详细文档：[依赖冲突故障排除](TUTORIAL.md#依赖冲突问题-resolution-too-deep)
```

**如果遇到ChromaDB遥测错误：**
```bash
# 项目已自动禁用遥测，如仍遇到错误：
export ANONYMIZED_TELEMETRY=False

# 或查看详细文档：[ChromaDB遥测错误](TUTORIAL.md#问题5chromadb遥测错误)
```

### 3.1 启用智能命令推荐系统

智能命令推荐系统会在您执行命令后自动显示推荐的操作建议：

```bash
# 环境变量配置（可选）
export RECOMMENDER_ENABLED=true          # 启用推荐系统
export RECOMMENDER_MAX=5                 # 最大推荐数量
export RECOMMENDER_MIN_STRENGTH=0.3      # 最小推荐强度
export RECOMMENDER_LEARNING=true         # 启用学习功能

# 推荐系统会在CLI中自动启用
# 注意：推荐系统仅在CLI中实现，不包含在桌面应用中
```

### 3. Python 路径设置

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

**OCR 功能依赖（可选）：**
```bash
# 运行安装脚本时会提示是否安装 OCR 依赖
./scripts/install_deps.sh      # Linux/macOS
.\scripts\install_deps.ps1     # Windows PowerShell

# 或手动安装 OCR 核心依赖（使用兼容版本）
pip install paddlepaddle==3.0.0 paddleocr==3.0.0 pytesseract==0.3.13 opencv-python==4.9.0.80

# 安装 Tesseract（系统级）
# macOS
brew install tesseract tesseract-lang

# Linux (Ubuntu/Debian)
sudo apt-get install tesseract-ocr tesseract-ocr-chi-sim tesseract-ocr-chi-tra

# Windows
# 下载安装程序：https://github.com/UB-Mannheim/tesseract/wiki
```

### 3. 启动

**交互式模式**（推荐）：
```bash
# 带知识库启动
python query_interface.py --data ./data

# 纯 Agent 模式启动
python query_interface.py
```

**单次查询**：
```bash
# 知识库查询
python query_interface.py --data ./papers --query "实验结果是什么？"

# Agent 任务
python query_interface.py --agent "检查 main.py 的语法错误"
```

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
├── react_engine.py        # ReAct 推理引擎（qwen2.5-coder:7b）
├── agent_tools.py         # 工具链（文件/命令/搜索 + RAG 查询/添加）
├── chat_history.py        # 对话历史持久化
├── query_interface.py     # 统一 CLI 入口
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
├── requirements.txt       # 依赖
├── data/                  # 文档存放目录
├── index_storage/         # 索引持久化存储
│   ├── chroma_db/         # ChromaDB 向量数据库
│   └── llama_index/       # LlamaIndex 索引文件
├── docs/                  # 文档目录
│   ├── design/           # 设计文档
│   ├── implementation/    # 实现文档
│   ├── testing/          # 测试文档
│   ├── general/          # 一般文档
│   ├── future-feature-design/  # 未来特性设计
│   └── tutorials/        # 教程文档
├── scripts/               # 脚本文件
│   ├── check_prereqs.sh   # 前置条件检查脚本
│   ├── install_deps.sh    # 依赖安装脚本
│   └── verify_deps.sh     # 依赖验证脚本
├── tests/                 # 单元测试
│   └── multi_agent/      # 多Agent系统测试
└── README.md
```

---

## 配置说明

### OCR 配置

在 `config.py` 中配置 OCR 功能：

```python
# OCR 开关
OCR_ENABLED = True  # 是否启用 OCR 功能
OCR_ENGINE = "paddle"  # OCR 引擎：paddle | tesseract | hybrid

# OCR 缓存配置
OCR_CACHE_DIR = INDEX_DIR / "ocr_cache"  # OCR 缓存目录
OCR_PARALLEL_WORKERS = 2  # 并行处理任务数
OCR_CACHE_TTL_DAYS = 30  # 缓存过期时间（天）

# PaddleOCR 配置
PADDLE_USE_GPU = False  # 是否使用 GPU
PADDLE_LANG = "ch"  # 语言：ch(中文) | en(英文) | jk(日韩)
PADDLE_USE_ANGLE_CLS = True  # 是否启用方向分类

# Tesseract 配置
TESSERACT_PATH = "/usr/local/bin/tesseract"  # Tesseract 可执行文件路径
TESSERACT_LANG = "chi_sim+eng"  # 语言包

# 图像预处理配置
OCR_PREPROCESS = True  # 是否启用图像预处理
OCR_DENOISE = True  # 去噪
OCR_BINARIZE = True  # 二值化
OCR_DESKEW = True  # 倾斜校正
OCR_ENHANCE_CONTRAST = True  # 对比度增强

# PDF 图片提取配置
PDF_EXTRACT_IMAGES = True  # 是否提取 PDF 中的图片
PDF_MIN_IMAGE_SIZE = (50, 50)  # 最小图片尺寸
```

### 环境变量配置

也可以通过环境变量配置：

```bash
# OCR 功能
export OCR_ENABLED=true
export OCR_ENGINE=paddle
export OCR_PARALLEL_WORKERS=2

# PaddleOCR
export PADDLE_USE_GPU=false
export PADDLE_LANG=ch

# Tesseract
export TESSERACT_PATH=/usr/local/bin/tesseract
export TESSERACT_LANG=chi_sim+eng
```

---

## 三模式使用指南

### 📚 模式一：RAG 知识库查询

适合基于上传的 **PDF、论文、笔记、文档** 回答问题。

```bash
# 进入交互式模式
python query_interface.py --data ./data

# 然后输入：
>>> /ask 这篇论文的核心贡献是什么？
>>> /ask 总结一下所有笔记中的关键概念
>>> /ask 这个算法的时间复杂度是多少？

# 快捷命令
>>> /stats              查看知识库统计
>>> /sources            显示上次回答的参考来源
>>> /add ./新论文.pdf    动态添加新文档
```

**支持的格式**：PDF、Markdown、TXT、Python、JS/TS、Java、C/C++、Go、Rust、HTML、JSON、YAML、XML

**OCR 增强功能**（需要安装 OCR 依赖）：
- 扫描版 PDF 自动识别
- 图片文件直接识别：PNG、JPG、JPEG、GIF、BMP、TIFF
- PDF 嵌入图片自动提取并识别
- 中英文混合识别支持

### 🤖 模式二：ReAct Agent 任务

适合 **代码生成、文件操作、命令执行、项目分析** 等复杂任务。

```bash
# 进入交互式模式
python query_interface.py

# 然后输入：
>>> /agent 写一个 Python 快速排序，保存到 sort.py，然后运行单元测试
>>> /agent 检查 src/main.py 第 20-50 行是否有内存泄漏
>>> /agent 搜索项目中所有硬编码的 API Key
>>> /agent 把 utils.py 里的 print 改成 logging，并运行测试确认
```

Agent 会自动：
1. `read_file` 读取代码
2. `write_file` 写入修改
3. `execute_command` 运行测试
4. 根据结果给出最终回答

**执行时你会看到：**
```
[*] [1/50] Step 1/50: 模型推理中...
[>] [2/50] Step 2/50: 执行 write_file...
[=] [3/50] Step 3/50: write_file 执行完成
[*] [4/50] Step 4/50: 模型推理中...
[!] [5/50] Step 5/50: 执行 execute_command...
[=] [6/50] Step 6/50: execute_command 执行完成
[OK] [7/50] Step 7/50: 给出最终答案
```

### 🤝 模式三：多Agent 协作系统 ⭐ 新功能

适合 **复杂任务分解、专业化分工、并行处理、多视角分析** 等高级场景。

```bash
# 进入交互式模式
python query_interface.py

# 然后使用 /multi 命令：
>>> /multi 实现用户认证系统，包括注册、登录、密码重置功能，并生成完整文档和测试 PARALLEL

# 或指定协作模式：
>>> /multi 重构 legacy.py，提高代码质量，添加测试，更新文档 SEQUENTIAL

>>> /multi 分析项目架构，CodeAgent分析代码，AuditAgent检查安全，DocAgent生成文档 HIERARCHY
```

**支持的协作模式：**
- `PARALLEL` - 并行执行多个独立任务
- `SEQUENTIAL` - 按依赖顺序执行任务
- `HIERARCHY` - 层级协作，任务分解和协调
- `COMPETITIVE` - 多Agent竞争，选择最佳方案

**专业Agent：**
- `CodeAgent` - 代码专家（生成、重构、审查、调试）
- `RAGAgent` - 知识库专家（检索、提取、综述）
- `TestAgent` - 测试专家（生成、覆盖率分析、质量评估）
- `DocAgent` - 文档专家（API文档、技术文档、用户指南）
- `AuditAgent` - 审计专家（安全检查、合规验证、性能审计）

**多Agent执行流程：**
```
MasterAgent 接收任务
    ↓
TaskDecomposer 分解为子任务
    ↓
TaskScheduler 分配给专业Agent
    ↓
专业Agent 并行/顺序执行
    ↓
ResultIntegrator 整合结果
    ↓
用户获得完整解决方案
```

---

## 统一命令速查

| 命令 | 模式 | 说明 |
|------|------|------|
| `/ask <问题>` | RAG | 直接查询知识库 |
| `/agent <任务>` | Agent | 进入 ReAct 自动任务模式 |
| `/multi <任务> <模式>` | MultiAgent | 多Agent协作系统 (PARALLEL/SEQUENTIAL/HIERARCHY/COMPETITIVE) |
| `/add <路径>` | RAG | 添加文档到知识库 |
| `/stats` | RAG | 知识库统计 |
| `/sources` | RAG | 显示上次回答来源 |
| `/generate-skills` | RAG | 将知识库转化为Skills |
| `/snapshot-list` | RAG | 查看知识库快照 |
| `/snapshot-create` | RAG | 手动创建快照 |
| `/snapshot-restore <id>` | RAG | 恢复指定快照 |
| `/knowledge-summary` | RAG | 查看知识库文档摘要 |
| `/file <路径>` | Agent | 快速读取文件 |
| `/write <路径>` | Agent | 交互式写入文件 |
| `/exec <命令>` | Agent | 执行命令（安全确认） |
| `/search <关键字>` | Agent | 搜索代码文件 |
| `/tools` | - | 查看所有工具 |
| `/history` | Agent | 对话历史 |
| `/summary` | Agent | 执行步骤摘要 |
| `/clear` | - | 清屏 |
| `/reset` | Agent | 重置对话上下文 |
| `/pwd` / `/cd` | - | 目录操作 |
| `/file-list` | - | 🆕 列出知识库中的所有文件 |
| `/file-info <path>` | - | 🆕 查看文件详细信息 |
| `/file-cleanup` | - | 🆕 清理临时/重复文件 |
| `/file-deduplicate` | - | 🆕 手动触发去重 |
| `/file-stats` | - | 🆕 显示文件统计信息 |
| `/session-new [title]` | - | 🆕 创建新会话 |
| `/session-list` | - | 🆕 列出所有会话 |
| `/session-switch <id>` | - | 🆕 切换到指定会话 |
| `/session-archive <id>` | - | 🆕 归档会话 |
| `/session-delete <id>` | - | 🆕 删除会话 |
| `/session-info <id>` | - | 🆕 查看会话详情 |
| `/session-search <query>` | - | 🆕 搜索会话 |
| `/session-current` | - | 🆕 显示当前会话信息 |
| `/session-compress` | - | 🆕 压缩当前会话历史 |
| `/model` | - | 显示模型信息 |
| `/tutorial` | - | 使用教程 |
| `/help` | - | 帮助 |
| `/quit` | - | 退出 |

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

# 查询
answer = engine.query("什么是注意力机制？")

# 带来源的查询
result = engine.query_with_sources("RAG 的优势是什么？")
print(result["answer"])
for src in result["sources"]:
    print(f"来源: {src['file']} (相似度: {src['score']:.3f})")

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
    model="qwen2.5-coder:7b",
    max_parallel_tasks=8,
    default_mode="parallel"
)

orchestrator = AgentOrchestrator(config)
status = orchestrator.get_status()
```

---

## 高级用法

### 🆕 多Agent协作

#### 复杂项目开发
```python
from agent_orchestrator import AgentOrchestrator
from agent_config import AgentConfigManager

config = AgentConfigManager.get_default_config()
orchestrator = AgentOrchestrator(config)

# 并行开发：代码 + 测试 + 文档
result = orchestrator.process_request(
    "实现用户注册登录功能，并生成测试和文档",
    CollaborationMode.PARALLEL
)

# 查看执行结果
print(result["summary"])
print(result["detailed_report"])
```

#### 竞争协作：多方案对比
```python
# 竞争模式：多个Agent提供不同方案
result = orchestrator.process_request(
    "设计一个高效的数据结构",
    CollaborationMode.COMPETITIVE
)

# 系统会自动选择最佳方案
best_solution = result["best_result"]
```

#### 顺序协作：依赖任务链
```python
# 顺序模式：代码 → 测试 → 文档
result = orchestrator.process_request(
    "重构代码，添加测试，更新文档",
    CollaborationMode.SEQUENTIAL
)

# 任务会按依赖顺序执行
```

#### 自定义Agent配置
```python
# 创建最小化配置（只启用需要的Agent）
config = AgentConfigManager.get_minimal_config()
orchestrator = AgentOrchestrator(config)
```

### 混合使用：Agent + 知识库

### 命令执行安全

| 风险等级 | 行为 | 示例 |
|----------|------|------|
| **critical** | 自动拦截 | `rm -rf /`, `dd if=/dev/zero` |
| **high** | 询问确认 | `rm file`, `del file` |
| **medium** | 询问确认 | `mv`, `cp`, `chmod`, `write_file` |
| **low** | 自动执行 | `ls`, `cat`, `git status`, `pytest` |

使用 `--yes` 参数可跳过所有确认（仅自动化脚本使用）。

### 内容安全防护 ⚡

系统内置了**内容安全扫描器**，防止基于文档的提示词攻击：

- **提示词注入检测**: 自动检测 "ignore instructions"、"bypass security" 等攻击模式
- **角色劫持防护**: 防止恶意文档改变AI角色和行为
- **高风险关键词识别**: 识别危险操作词汇（delete, destroy, exploit等）
- **可疑模式检测**: 检测字符重复、Base64编码等混淆攻击
- **威胁等级评估**: 5级威胁分类（SAFE/LOW/MEDIUM/HIGH/CRITICAL）

```python
# 启用安全扫描（默认启用）
engine = RAGEngine(enable_security=True)

# 禁用安全扫描（不推荐）
engine = RAGEngine(enable_security=False)
```

详细安全说明请查看：[安全功能文档](docs/general/SECURITY_DOCUMENTATION.md)

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

项目要求测试覆盖率 ≥ 95%。

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
- **tests/test_query_interface_*.py** - 查询接口测试
- **tests/multi_agent/** - 多Agent系统测试
- **tests/test_web_search.py** - 网络搜索功能测试
- **tests/test_ocr_*.py** - OCR功能测试

详细测试文档请查看：[TESTING.md](TESTING.md)

---

## 配置说明

编辑 `config.py` 或通过环境变量：

```python
# 模型配置
LLM_MODEL = "qwen2.5-coder:7b"      # 主模型（统一）
EMBED_MODEL = "nomic-embed-text"     # 嵌入模型

# RAG 配置
CHUNK_SIZE = 1024                   # 分块大小
CHUNK_OVERLAP = 200                 # 分块重叠
TOP_K = 5                           # 检索片段数

# Agent 配置
MAX_ITERATIONS = 50                 # 最大迭代步数
TIMEOUT = 300                       # 模型超时
AUTO_CONFIRM = False                # 自动确认

# 🆕 多Agent配置
DEFAULT_COLLABORATION_MODE = "hierarchy"  # 默认协作模式
MAX_PARALLEL_TASKS = 5               # 最大并行任务数
TASK_TIMEOUT = 600                   # 任务超时（秒）
AGENT_TIMEOUT = 300                  # Agent执行超时（秒）
ENABLE_LOGGING = True                # 启用日志
LOG_LEVEL = "INFO"                   # 日志级别
```

**环境变量方式**：
```bash
export LLM_MODEL="qwen2.5-coder:7b"
export CHUNK_SIZE=512
export CODE_AGENT_AUTO_CONFIRM=true

python query_interface.py --data ./data
```

---

## 高级用法

### 混合使用：Agent + 知识库

Agent 在完成任务时，会自动调用 `query_knowledge_base` 查询知识库：

```
>>> /agent 根据知识库中的论文，写一个实现该算法的 Python 代码
```

Agent 执行流程：
1. `query_knowledge_base` — 查询论文内容
2. `write_file` — 根据论文写代码
3. `execute_command` — 运行测试验证

### 增量更新知识库

```python
from rag_engine import RAGEngine
from document_loader import load_documents

engine = RAGEngine()
engine.load_index()

# 添加新论文
new_docs = load_documents("./新论文.pdf")
engine.add_documents(new_docs)
```

### 多格式混合索引

```python
all_docs = []
all_docs.extend(load_documents("./papers", [".pdf"]))
all_docs.extend(load_documents("./notes", [".md"]))
all_docs.extend(load_documents("./src", [".py", ".js"]))

engine.build_index(all_docs)
```

---

## 性能优化建议

1. **Embedding 模型**：`nomic-embed-text` 速度快、效果好
2. **分块大小**：论文 1024，代码 512，笔记 768
3. **模型选择**：`qwen2.5-coder:7b` 兼顾代码和文档理解
4. **硬件要求**：7B 模型约需 8GB 显存/内存

---

## 常见问题

**Q: Ollama 连接失败？**
```bash
ollama serve
export OLLAMA_BASE_URL="http://localhost:11434"
```

**Q: 中文 PDF 乱码？**
确保 PDF 是文本型而非扫描型。扫描版需先 OCR。

**Q: Agent 不调用工具？**
- 确认模型已正确加载
- 尝试更明确的指令，如 "请使用 read_file 读取..."
- 检查系统提示词中是否包含工具描述

**Q: 知识库回答质量不佳？**
- 检查文档是否成功加载
- 调整 `CHUNK_OVERLAP` 增加上下文连贯性
- 使用更具体的提问方式

---

## 扩展方向

- [x] 知识库自动快照系统
- [x] 知识库到Skill智能转化
- [x] 内容安全扫描器（防止提示词攻击）
- [ ] Web UI（Gradio / Streamlit）
- [ ] 图片/图表 OCR 提取
- [ ] Git 集成（diff、commit、blame）
- [ ] 代码质量自动检查（pylint、flake8）
- [ ] 多用户集合隔离

---

## 新增功能特性

### � 知识库智能优化

#### 1. 自动快照系统
- **自动创建**: 每次添加文档时自动创建知识库快照
- **版本管理**: 保留最近10个快照，自动清理旧版本
- **快照恢复**: 支持一键恢复到任意历史快照
- **迁移支持**: 自动生成恢复脚本，便于知识库迁移

```bash
# 查看所有快照
>>> /snapshot-list

# 手动创建快照
>>> /snapshot-create

# 恢复指定快照
>>> /snapshot-restore <snapshot_id>
```

#### 2. 知识库到Skill智能转化
- **智能分类**: 自动区分通用型vs项目型文档
- **主题合并**: 按主题合并多个文档生成统一skill
- **多平台支持**: 同时支持Devin和OpenCode平台
- **自动路径管理**: 通用型skill放入全局目录，项目专用型放入项目目录

```bash
# 将知识库转化为Skills
>>> /generate-skills

# 查看知识库文档摘要
>>> /knowledge-summary
```

#### 3. 内容安全防护
- **提示词注入检测**: 防止恶意文档改变AI行为
- **角色劫持防护**: 检测并阻止角色定义攻击
- **内容净化**: 自动移除或标记危险内容
- **威胁分级**: 5级威胁分类，灵活应对不同风险

详细实现说明请查看：[知识库优化实现总结](docs/general/KNOWLEDGE_OPTIMIZATION_SUMMARY.md)

---

## �📚 文档资源

- **[详细使用教程](TUTORIAL.md)** - 完整的前置条件配置、安装指南、功能说明、故障排除
- **[使用场景详细指南](docs/general/USE_CASES.md)** - 8大类别40+实战场景示例和最佳实践
- **[快速开始检查](docs/general/QUICK_START_CHECK.md)** - 一键验证环境配置
- **[警告问题修复说明](docs/general/WARNING_FIX.md)** - ChromaDB遥测错误和urllib3 OpenSSL警告的修复
- **[测试设计文档](docs/testing/TEST_DESIGN.md)** - 单元测试设计和覆盖率说明（当前覆盖率87%）
- **[知识库优化实现总结](docs/general/KNOWLEDGE_OPTIMIZATION_SUMMARY.md)** - 知识库智能优化功能的完整实现说明
- **[安全功能文档](docs/general/SECURITY_DOCUMENTATION.md)** - 内容安全扫描器的详细使用指南

### 快速链接

- **使用场景** → [使用场景详细指南](docs/general/USE_CASES.md)
- **安装问题** → [前置条件检查与配置](TUTORIAL.md#前置条件检查与配置)
- **功能详解** → [详细功能说明](TUTORIAL.md#详细功能说明)
- **安全配置** → [安全机制](TUTORIAL.md#安全机制)
- **故障排除** → [故障排除](TUTORIAL.md#故障排除)
- **依赖冲突** → [依赖冲突问题](TUTORIAL.md#依赖冲突问题-resolution-too-deep)
- **警告问题** → [警告问题修复说明](docs/general/WARNING_FIX.md)
- **知识库优化** → [知识库优化实现总结](docs/general/KNOWLEDGE_OPTIMIZATION_SUMMARY.md)
- **安全防护** → [安全功能文档](docs/general/SECURITY_DOCUMENTATION.md)

---

## 技术栈

| 组件 | 用途 |
|------|------|
| Ollama | 本地 LLM 推理 |
| qwen2.5-coder:7b | 代码/文档理解与生成 |
| nomic-embed-text | 文本语义嵌入 |
| LlamaIndex | RAG 框架 |
| ChromaDB | 向量数据库 |
| ReAct | 推理+行动循环 |
| Rich | 终端美化 |

---

*Cerebro — 你的第二大脑 + 代码助手 🧠💻*
