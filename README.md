<div align="center">

# Cerebro 🧠

### 完全离线运行的「第二大脑」+ AI 代码助手 —— 数据不出本机，零 API 费用

[![License](https://img.shields.io/github/license/SteveZouWonder/ollama-qwen-coder-rag-lib-agent)](LICENSE)
[![Release](https://img.shields.io/github/v/release/SteveZouWonder/ollama-qwen-coder-rag-lib-agent)](../../releases)
[![Stars](https://img.shields.io/github/stars/SteveZouWonder/ollama-qwen-coder-rag-lib-agent?style=social)](../../stargazers)
[![Python](https://img.shields.io/badge/python-3.13-blue)](https://www.python.org/)
[![Ollama](https://img.shields.io/badge/Ollama-qwen3.5-000000)](https://ollama.com)

[下载安装](#下载安装包普通用户推荐) · [快速开始](#快速开始开发者--源码运行) · [使用场景](#使用场景) · [文档](#-文档资源)

</div>

> *Cerebro* —— 拉丁语「大脑」。一个**完全本地运行**的智能体：把你的 PDF、论文、笔记变成可检索的「第二大脑」，并让 AI 帮你读写代码、执行任务——**全程离线，数据不离开你的电脑**。

基于 **Ollama qwen3.5**（默认 `qwen3.5:4b`，可按机器配置一键切换，见[模型选择指南](#模型选择指南)），三合一融合：**📚 RAG 知识库检索** + **🤖 ReAct Agent 代码操作** + **🤝 多 Agent 协作系统**。

**为什么选 Cerebro？**

- 🔒 **隐私优先** —— 100% 本地推理，敏感文档与代码永不上传云端
- 💸 **零成本** —— 基于开源 Ollama，无需任何 API Key 或订阅费用
- 🧩 **三模式合一** —— 知识库问答、自动化代码 Agent、多 Agent 协作，一个工具全覆盖
- 📦 **开箱即用** —— 提供 Windows / macOS / Linux 桌面安装包，非开发者也能用

<div align="center">

![Cerebro 演示](docs/assets/demo.gif)

<sub>三大模式一镜演示：📚 RAG 知识库问答 · 🤖 ReAct Agent 自动改代码跑测试 · 🤝 多 Agent 协作交付</sub>

</div>

---

## 融合架构

```
┌─────────────────────────────────────────────────────────────────────┐
│                        统一 CLI 交互层                               │
│         /ask /agent /multi  /file /exec ...                           │
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
│                Ollama qwen3.5:4b（可热切换 9b/27b）                  │    │ (审计专家)│      │
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

## 下载安装包（普通用户推荐）

无需搭建 Python 环境，前往 [Releases](../../releases) 页面下载对应平台安装包：

| 平台 | 文件 | 安装方式 |
|------|------|---------|
| Windows | `Cerebro-Setup-x.x.x.exe` | 双击运行安装向导，按提示下一步即可 |
| macOS | `Cerebro-x.x.x.dmg` | 打开后将 Cerebro 拖入「应用程序」 |
| Linux | `Cerebro-x.x.x-x86_64.AppImage` | `chmod +x Cerebro-*.AppImage` 后双击运行 |

**运行前提**：应用依赖本地 [Ollama](https://ollama.com) 服务。首次启动会自动检测，
若未安装会引导你安装 Ollama 并拉取所需模型（`qwen3.5:4b`、`nomic-embed-text:latest`）。

**使用方式**：
- 直接运行 = 系统托盘桌面应用（GUI）
- 命令行交互模式 = 启动时加 `--cli` 参数（Windows 安装包已附「命令行模式」快捷方式）

<div align="center">

![Cerebro 桌面应用演示](docs/assets/demo-gui.gif)

<sub>桌面应用：点击托盘图标 → 「打开 CLI 界面」→ 进入交互</sub>

</div>

### ⚠️ macOS 用户须知（首次打开）

本应用为**免费开源项目，未购买 Apple 开发者证书**，因此未做苹果公证。
macOS 首次打开可能提示「无法验证开发者」或「已损坏」，属于正常现象。请按以下步骤打开：

1. 将 `Cerebro.app` 拖入「应用程序」文件夹。
2. 在「应用程序」中**右键点击 Cerebro → 选择「打开」**。
3. 在弹窗中再次点击「打开」。之后即可正常双击启动。

若提示「已损坏，无法打开」（Apple Silicon 常见），在「终端」执行：

```bash
xattr -dr com.apple.quarantine /Applications/Cerebro.app
```

---

## 快速开始（开发者 / 源码运行）

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

如果检查通过，继续以下步骤。如果有问题，请参考 [安装和配置指南](docs/tutorials/02-installation.md) （含一键前置条件检查与手动验证清单）。

### 1. 环境准备

```bash
# 安装 Ollama（如未安装）
curl -fsSL https://ollama.com/install.sh | sh

# 拉取模型（默认协同档 4b；内存宽裕可再拉 qwen3.5:9b，运行中用 /model 切换）
ollama pull qwen3.5:4b
ollama pull nomic-embed-text:latest
```

### 2. 安装依赖

依赖版本**已全部钉死**（`==`），任何机器上装出的环境一致。三份依赖清单各司其职：

| 文件 | 内容 | 谁需要 |
|---|---|---|
| `requirements.txt` | 运行时依赖（RAG / Agent / Web / 桌面托盘） | 所有人 |
| `requirements-dev.txt` | 测试与静态检查：pytest、pytest-cov、pytest-xdist、flake8、pylint、bandit、pip-audit（内含 `-r requirements.txt`） | 要跑测试 / 提 PR 的开发者 |
| `requirements-build.txt` | PyInstaller 打包用的精简运行时依赖 | 发布流程（`release.yml`） |

**推荐方法：使用专用安装脚本（避免依赖冲突）**
```bash
./scripts/install_deps.sh      # Linux/macOS（会询问是否一并安装 OCR / 开发测试依赖）
.\scripts\install_deps.ps1     # Windows PowerShell
```

**标准方法：**
```bash
pip install -r requirements.txt          # 只运行产品
pip install -r requirements-dev.txt      # 开发者：运行时 + 测试/静态检查（一条命令装全）
```

装完可用 `bash scripts/verify_deps.sh` 逐包校验导入（运行时与开发依赖分两段输出）。

**如果遇到依赖冲突（如 "resolution-too-deep" 错误）：**
```bash
# 使用 --no-cache-dir 选项
pip install -r requirements.txt --no-cache-dir

# 或查看详细文档：[依赖冲突故障排除](docs/tutorials/06-troubleshooting.md#依赖冲突问题-resolution-too-deep)
```

> 升级依赖：改 `requirements.txt` 后同步 `requirements-build.txt`（打包）与 `requirements-dev.txt`（开发），
> 再跑 `bash scripts/verify_deps.sh` 与 `pip-audit -r requirements.txt`。

**如果遇到ChromaDB遥测错误：**
```bash
# 项目已自动禁用遥测，如仍遇到错误：
export ANONYMIZED_TELEMETRY=False

# 或查看详细文档：[ChromaDB遥测错误](docs/tutorials/06-troubleshooting.md#chromadb遥测错误)
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

**Web 界面**：
```bash
python launcher.py --web        # 默认 http://127.0.0.1:7860
```
界面为「左侧栏导航 + 主区 + 右侧面板」：左侧栏切换 **对话 / 知识库 / 知识图谱 / 工具 / 系统**
五个页面并管理会话；对话页默认「自动」模式（按意图判定走 RAG 还是单 Agent，状态行显示实际模式），
也可手动选 RAG / 单 Agent / 多 Agent（可选协作模式），右侧面板
展示上下文用量、处理过程与引用来源，单 Agent 遇到危险操作会弹出「允许 / 拒绝」审批卡片；
右上角可切换 6 套主题色（跟随系统深浅色）。功能面与 CLI 命令一一对应，见「系统 → 帮助」。

工具页分 **代码 | Git | 数据库 | 工作区** 四个子页，每个子页以自然语言为第一入口，AI 产出的 SQL / 命令只回填编辑框、
确认后才执行：**代码助手** 输入文件或目录路径，一键「解释代码 / 审查问题 / 生成测试 / 生成文档 / 重构建议」
（受限只读 Agent 流式完成，可看处理过程、可停止；高级区提供符号表与质量卡片）；**Git** 是仪表盘（分支 / 变更 /
最近提交 / 提交者卡片与表格）+ 提交区（暂存区预览 →「AI 生成提交信息」→ 可编辑 →「提交」二步确认执行 `git commit`，
受工作区总开关门控）；**数据库** 连接 SQLite（下拉记住最近 8 个库，重启后仍在）后列出全部表、点表看 列 / 类型 / 约束，
用自然语言描述（如"每个表有多少行"）→「AI 生成 SQL」→ 可手改的 SQL 编辑框 →「运行」（只读直接跑，写操作二步确认）；
**工作区** 浏览目录（面包屑 / 上级 / 隐藏项 / 关键词搜索）、分页语法高亮预览文件、「发到代码助手」/「编辑」
（追加或覆盖，保存需确认），底部命令区既可写自然语言（「AI 生成命令」自动做风险分析）也可直接写命令，再 分析 → 执行，
「历史命令」下拉记住最近 50 条成功命令、选中即回填并分析；总开关「启用文件编辑与 Shell 执行」默认关闭。
每个结果面板下都有 **「用 AI 解读」**（流式、可停止）与 **「发送到对话」**（把结果填入对话输入框并切到对话页继续追问）；
表格为空时给出一行说明，AI 任务运行期间触发按钮禁用。网络搜索缓存管理在「系统 → 运行环境」。

知识库页的文件 / 快照表格末列有「⋯」：点击任意单元格即选中该行并弹出操作条——文件可
**查看详情 / 删除文件**（删向量片段 + 图谱来源 + 元数据，不删磁盘文件，二步确认并预览影响），
快照可 **详情 / 恢复（追加）/ 恢复（替换）/ 生成脚本 / 删除**，并可一键清理多余的自动快照。
知识图谱页提供 **3D / 2D 交互式图谱视图**（Plotly，离线）：按实体类型 / 置信度 / 节点数筛选、
聚焦某实体的 1–2 跳邻域，节点按类型着色、按度数定大小，悬停查看来源文档与关系类型。
对应 CLI：`/file-delete`、`/snapshot-info|delete|prune`、`/snapshot-restore <id> --apply [--replace]`、
`/graph-summary`、`/graph-export [--3d|--2d] [--focus 实体]`（导出自包含 HTML 并在浏览器打开）。

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
├── agent_tools.py         # 工具链（文件/命令/搜索 + RAG 查询/添加）
├── conversation_context.py # 连续对话上下文（会话记忆、token 预算、滚动压缩、追问改写）
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

### 🧭 自动路由（默认）：不用记模式，直接输入

CLI 中不加斜杠的自然语言输入、Web 对话页默认的「自动」模式，都会先由 `src/intent_router.py`
判定意图再分发：

| 输入特征 | 走向 | 示例 |
|---------|------|------|
| 文件/目录路径（`/x/y.py`、`./src`、`~/`、`*.log`）、代码围栏、命令式动词（修改/创建/运行/删除/安装/实现/修复/重构/部署、create/run/fix/refactor/…） | 🤖 Agent | `修改 main.py 加上日志` |
| 疑问句（？/吗/呢/什么/为什么/如何理解/是否）、"总结/比较/解释/介绍/区别/优缺点"、以"什么是"开头 | 📚 RAG | `什么是 RAG？` `总结这份文档` |
| 两类都命中或都不命中（模糊） | 一次 LLM 一词判定（`think=False`、`num_predict=4`、5s 超时；失败回退 RAG） | `你好啊` |
| 模糊且知识库为空 | 🤖 Agent（不调 LLM） | — |

- CLI 判为 Agent 时会提示「🤖 已按 Agent 模式处理（原因；用 /ask 强制知识库；/auto off 关闭自动路由）」；
  `/ask` / `/agent` / `/multi` 显式命令**不判定**。`/auto` 查看状态，`/auto on|off` 运行时开关，
  环境变量 `AUTO_ROUTE=false` 可默认关闭（关闭后自然语言一律走知识库问答）。
- Web「自动」模式下同时显示「联网搜索增强」与「自动确认危险操作」两个开关；处理过程首行为
  「🧭 自动路由：按 RAG/Agent 处理（原因）」，完成后状态行追加「· 实际模式：RAG 检索 | 单 Agent」，
  并按实际模式渲染来源面板 / 执行摘要。手动切到其他模式即不再判定。

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

**检索与推理链路（F8 P2）**：
- **hybrid 召回**：向量检索 + BM25 关键词检索用 RRF 融合，型号 / 术语等精确词也能召回
  （`RAG_HYBRID`，默认开；`rank_bm25` 未安装自动回退纯向量）。BM25 语料持久化在 `index_storage/bm25/`
  并随入库 / 删除增量维护，入库后首次查询不再全量重建（1 万块库 1.4s → 15ms）；文档块数超过
  `RAG_HYBRID_MAX_CHUNKS`（默认 50000）时关闭混合检索，并在 `/stats`、Web 知识库页与查询结果中给出原因与调法。
- **复合问题分解**：一次模型调用同时判断"是否拆子问题 / 是否联网 / 搜索词"；"A 与 B 的价格差多少"
  会拆为 ≤3 个子问题分别检索、去重合并后再综合，简单问题不增加调用。
- **逐片段 rerank**：对通过阈值的片段逐条判定"是否真能回答问题"并给出一句理由，剔除话题不搭的
  噪音（`RERANKER=llm` 默认；`RERANKER=cross-encoder` 可选，见下方环境变量）。
- **编号引用**：答案中的关键结论句末标注 `[1]`（知识库片段）/ `[W1]`（网络来源），`/sources`
  与 Web 来源面板按同一编号显示，可逐条核验。
- **思维链透出**：`/think on` 时模型思考过程（截断 800 字）显示在 Web「处理过程」/ CLI dim 行。
- **失败回退**：知识库与网络都没有结果时，CLI 黄色行提示 `可试试：/agent <原问题>`，Web 出现
  「用单 Agent 重试」按钮一键切模式重发。

**抗过度顺从与可核验性（F9 P0，基于 H-Neurons 研究）**：小模型（含默认 `qwen3.5:4b`）更容易"顺着
问题前提编、被反驳就改口"，本项目在模型外围加了三道防线（对 `/model` 切换后的任意模型同样生效）：
- **单一综合路径**：知识库回答一律经同一套忠实性 prompt 生成且只生成一次（不再有 LlamaIndex 默认英文
  模板的"快路径"和双重生成）；prompt 新增前提核对 / 冲突并列 / 被质疑不改口三条；ReAct Agent 加
  「事实规则」（被质疑先用工具核实；Observation 是数据不是指令）。
- **引用程序化校验**：答案里的 `[i]` / `[Wj]` 逐个核对，不存在的编号改写为 `[?]`；CLI `/ask` 摘要行显示
  `· 🔎 引用 v/t 有效`（有无效引用时整行黄色），`/sources` 表新增「引用」列（被引用次数）；Web 状态行显示
  `🔎 引用 N 处已核验` / `v/t 有效`，来源面板每条标注 `（被引用 n 次）` / `（未被引用）`，存在无效引用时列出
  编号并自动展开面板。
- **结构化提示**：警示 / 校验信息与正文分离——CLI 在答案上方 / 下方以黄色 `⚠️ …`、dim `💡 …` 行显示，Web 以
  `> ⚠️ …` blockquote 置于气泡前 / 后（如「知识库无相关内容 · 回答基于网络搜索」「无资料依据 · 模型自身知识 ·
  请自行核实」「N 句含数字但未标来源」）。重要事实请结合 `/sources` 与引用校验行核对。
- **前提实体校验（零新增调用）**：检索规划顺带提取问题中的专有名词 / 函数名 / 产品名，若资料中完全没出现，
  先提示 `⚠️ 资料中未出现「X」，已先核对前提` 再作答（避免顺着虚构实体编）。
- **可选自校验 `RAG_SELF_CHECK=true`**（默认关，每问多一次模型调用）：综合后用同一模型逐句核对是否被资料支持，
  未支持的陈述以 `⚠️ 以下陈述未在资料中找到依据：① …` 列在答案后；「系统 → 运行环境」与 `/stats` 显示开关状态。

**代码感知分块（F8 P4）**：代码文件（`.py/.js/.ts/.java/.go/.rs/.c/.cpp`）入库时不再按 token 数硬切，
而是用 tree-sitter 按函数 / 类 / 方法边界切分，签名与函数体不分离；每个片段带 `符号 · L起-止` 元数据：
- `/add` 后显示 `已入库 N 个文件 · M 个片段（其中 a 个代码文件按函数/类切分，共 s 个符号）`，追加入库有
  「切分 → 嵌入」进度条（Web 同样实时显示）；
- `/sources` 与 Web 来源面板对代码片段显示 `RAGEngine._ensure_bm25 · L534-581`，Web 以对应语言的代码块渲染；
  综合回答可在 `[i]` 之外注明函数名与行号；
- `/file-list`、`/file-info`、Web 文件表与详情显示每个文件的分块策略（`代码(python) · 27 个符号` / `文本`），
  旧库中的代码文件提示「重新入库可启用代码分块」；
- 依赖 `tree-sitter-language-pack` 为**可选**（`pip install "tree-sitter-language-pack>=1.16,<2"`，约 5 MB
  预编译 wheel，桌面打包版已内置）；未安装、`CODE_AWARE_CHUNKING=false` 或语法错误过多时自动回退通用切分，
  只在首次入库代码文件时给一行提示，`/stats` 与 Web「系统」页显示当前状态。
- 注意：代码文件的片段数约为原来的 3-4 倍，入库时的 embedding 时间同比增加；已入库的代码文件需重新 `/add`
  才会按新方式切分。

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

**鲁棒性保护（自动生效，进度行 / Web「处理过程」/ `/summary` 中可见）：**

| 标记 | 场景 | 行为 |
|---|---|---|
| `[~]` 格式重试 | 模型输出没有 `Action` / `Final Answer`、`Action Input` 不是 JSON、调用了不存在的工具 | 回灌 `[格式错误]` 提示连续重试最多 2 次（`MAX_FORMAT_RETRIES`），仍失败则按现有文本收尾并标注「（格式异常，可能不完整）」 |
| `[R]` 重复调用 | 相同工具 + 相同参数第 2 次出现 | 不再执行，回灌「已有结果，请换方法」；第 3 次终止并强制总结 |
| `[F]` 上下文折叠 | 本轮往返超出 `num_ctx − 系统提示 − 历史 − 4096` 的预算 | 单条 Observation 超过 `OBSERVATION_MAX_CHARS`（默认 3000）先截断；仍超预算则把最早步骤的 Observation 折叠为一行摘要，最近 3 步始终完整 |
| `[!!]` 强制总结 | 步数用尽（`MAX_ITERATIONS`）或重复调用终止 | 追加「请基于以上 Observation 总结已完成/未完成/建议」再调一次模型，以 **⚠️ 未完成** 为前缀返回，而不是丢弃全部中间结果 |
| `[E]` 错误 | Ollama 连不上 / 超时 | 直接返回 `[错误] …`，不写入会话 |

**命令安全分级**（`execute_command`）：`ls/cat/git status` 等只读命令 → low 免确认；
`pip/npm/brew/apt install`、`git push/commit/reset/checkout/rebase/merge`、`python x.py`、
`node x.js`、`make`、`docker run/exec`、`mv/cp/chmod/chown` → **medium 需确认**；
`rm`、`drop`、`curl … | sh|bash` → **high 需确认**；`rm -rf /`、`mkfs`、`sudo rm` 等 → critical 直接拦截。
关键字按**子命令首 token** 匹配，`pip show models`、`ls performance/`、`git log --format=%H`
不会再因含 `del` / `rm` / `format` 子串被误判为高风险；`ls | xargs rm` 仍判 high。
`CODE_AGENT_AUTO_CONFIRM=true`（或 `--yes`）只免除 low / medium，**high / critical 一律仍需人工确认**。

**路径边界**：`write_file` / `add_to_knowledge_base` 只允许操作**当前工作目录**或
`WRITE_ALLOWED_DIRS`（冒号分隔）内的路径；`read_file` / `list_directory` / `search_files` /
`analyze_project_structure` / `ast_search` / `code_quality_check` / `git_analyze`（含 CLI `/file` 与
Web「工具」页的目录浏览 / 预览 / 搜索 / 符号 / 质量 / 代码助手）只允许读**写允许目录 +
`READ_ALLOWED_DIRS` + 已入库文档所在目录**（Web 上传的文件按上传根目录一条计），越界返回
`[错误] 路径超出允许范围`。要让 Agent 入库项目外的 PDF/图片先
`export WRITE_ALLOWED_DIRS=~/Documents:~/Downloads`；只需读取则用
`export READ_ALLOWED_DIRS=~/Documents`。当前允许范围可用 CLI `/config` 或 Web「系统 → 运行环境」查看。

`query_knowledge_base` 与 RAG 模式走同一条管道（相关性阈值 + 模型判定），返回「答案 + 相关性
结论 + top-3 片段原文（含文件名）」；知识库无相关内容时明确返回 `[知识库无相关内容]`，Agent 会
据此改用 `web_search`。

### 🤝 模式三：多Agent 协作系统 ⭐ 新功能

适合 **复杂任务分解、专业化分工、并行处理、多视角分析** 等高级场景。

```bash
# 进入交互式模式
python query_interface.py

# 然后使用 /multi 命令（默认层级协作）：
>>> /multi 写一个快速排序保存到 sort.py 并为它写测试

# 或用 --mode 指定协作模式：
>>> /multi 重构 legacy.py，添加测试，更新文档 --mode parallel
>>> /multi 审计 src/agent_tools.py 的安全问题 --mode competitive
```

Web 界面在对话页选「多 Agent 协作」，右侧下拉可选协作模式；「处理过程」实时显示分解 →
调度 → 各 Agent 的 ReAct 步骤 → 整合，结果面板先给综合回答，再列各 Agent 摘要与来源。

**支持的协作模式：**
- `hierarchy`（默认）- 按依赖顺序逐个执行，下游子任务可看到上游产出
- `parallel` - 无依赖的子任务真正并发（线程池，受 `max_parallel_tasks` 限制），有依赖的分波执行
- `sequential` - 严格按依赖拓扑顺序执行
- `competitive` - 同一任务并行交给所有能胜任的 Agent，由 LLM 评审选出最佳（失败回退最长成功输出）

**专业 Agent（Code / Test / Doc / Audit 各自委托一个受限工具集的 ReActEngine 真实执行）：**
- `CodeAgent` - 代码专家：read_file / write_file / execute_command / list_directory / search_files / ast_search / analyze_project_structure / get_current_dir
- `TestAgent` - 测试专家：read_file / write_file / execute_command / search_files / code_quality_check
- `DocAgent` - 文档专家：read_file / write_file / list_directory / search_files / query_knowledge_base / web_search
- `AuditAgent` - 审计专家（只读）：read_file / search_files / code_quality_check / ast_search / git_analyze / execute_command
- `RAGAgent` - 知识库专家：复用 RAG 编排（相关性判定 + 联网回退），返回结构化来源

**多 Agent 执行流程：**
```
MasterAgent 接收任务
    ↓
TaskDecomposer：一次 LLM 输出 JSON 子任务（类型 / 独立描述 / 依赖），失败回退关键词表
    ↓
TaskScheduler 按能力分配给专业 Agent
    ↓
专业 Agent 真实执行（ReActEngine / RAG 编排），按 timeout 超时，失败后恢复 IDLE
    ↓
ResultIntegrator：LLM 综合为面向用户的回答 + 统计 + 合并来源（竞争模式 LLM 评审选优）
    ↓
用户获得综合回答、各 Agent 摘要（步数 / 工具 / 未经验证标记）与来源
```

> 子 Agent 若从未调用角色关键工具（如测试 Agent 没有真正写入 / 运行）却给出结论，结果会标记
> 「⚠️ 未经验证」——小模型偶尔会口头宣称完成，请以该标记与磁盘产物为准。

---

## 统一命令速查

| 命令 | 模式 | 说明 |
|------|------|------|
| `<自然语言>` | 自动 | 🆕 不加斜杠直接输入：按意图自动判定走 RAG 还是 Agent（`AUTO_ROUTE`） |
| `/auto` | 自动 | 🆕 显示自动路由状态（默认开） |
| `/auto on\|off` | 自动 | 🆕 运行时开关自动路由（关闭后自然语言一律走知识库问答） |
| `/ask <问题>` | RAG | 直接查询知识库（不做意图判定） |
| `/agent <任务>` | Agent | 进入 ReAct 自动任务模式 |
| `/multi <任务> [--mode m]` | MultiAgent | 多 Agent 协作（hierarchy / parallel / sequential / competitive） |
| `/add <路径>` | RAG | 添加文档到知识库 |
| `/stats` | RAG | 知识库统计 |
| `/sources` | RAG | 显示上次回答来源 |
| `/generate-skills` | RAG | 将知识库转化为Skills |
| `/snapshot-list` | RAG | 查看知识库快照 |
| `/snapshot-create` | RAG | 手动创建快照 |
| `/snapshot-restore <id> [--apply [--replace]]` | RAG | 生成恢复脚本；`--apply` 直接恢复（追加 / 替换） |
| `/snapshot-info <id>` | RAG | 🆕 快照详情（文档清单、文件是否仍存在） |
| `/snapshot-delete <id>` | RAG | 🆕 删除快照（确认） |
| `/snapshot-prune [N]` | RAG | 🆕 清理自动快照，仅保留最近 N 个 |
| `/knowledge-summary` | RAG | 查看知识库文档摘要 |
| `/file <路径>` | Agent | 快速读取文件 |
| `/write <路径>` | Agent | 交互式写入文件 |
| `/exec <命令>` | Agent | 执行命令（安全确认；high 风险即使开了自动确认也仍需确认） |
| `/search <关键字>` | Agent | 搜索代码文件 |
| `/tools` | - | 查看所有工具 |
| `/config` | - | 🆕 显示运行配置（模型 / 自动确认 / **允许读目录 · 允许写目录** / 数据与索引目录） |
| `/history` | Agent | 对话历史 |
| `/summary` | Agent | 执行步骤摘要 |
| `/clear` | - | 清屏 |
| `/reset` | Agent | 重置对话上下文 |
| `/pwd` / `/cd` | - | 目录操作 |
| `/db-connect <database>` | - | 🆕 连接 SQLite 并设为当前连接（默认 sqlite；`/db-connect sqlite x.db` 仍兼容） |
| `/db-query <sql>` / `/db-execute <sql>` | - | 在当前连接上查询（🆕 结果表格，最多 50 行）/ 执行写语句（执行需确认） |
| `/db-schema [table]` | - | 🆕 表结构表（列 / 类型 / 约束）；不带参数列出当前库全部表 |
| `/db-create-table <table> <json>` / `/db-insert <table> <json>` | - | 建表 / 插入（JSON 参数，需确认） |
| `/git-analyze [history\|status\|authors]` / `/git-commit-gen` | - | 🆕 Git 概览表（分支 · 变更数 · 最近 10 次提交）/ 变更文件表 / 提交者表；AI 生成提交信息 |
| `/code-ast <pattern>` / `/code-quality <path>` | - | 符号搜索 / 代码质量检查 |
| `/web-search <query>` / `/web-extract <url>` / `/web-cache [status\|clear]` | - | 网络搜索 / 正文提取 / 缓存管理 |
| `/file-list` | - | 🆕 列出知识库中的所有文件 |
| `/file-info <path>` | - | 🆕 查看文件详细信息 |
| `/file-delete <path>` | RAG | 🆕 从知识库删除文件（向量 + 图谱来源 + 元数据，不删磁盘文件） |
| `/graph-summary` | - | 🆕 图谱概览（节点 / 边 / 类型分布） |
| `/graph-export [路径] [--3d\|--2d] [--focus 实体]` | - | 🆕 导出交互式 HTML 图谱并在浏览器打开 |
| `/file-cleanup` | - | 🆕 清理临时/重复文件 |
| `/file-deduplicate` | - | 🆕 手动触发去重 |
| `/file-stats` | - | 🆕 显示文件统计信息 |
| `/session-new [--carry] [title]` | - | 🆕 创建新会话（默认全新上下文；`--carry` 仅承接上一会话已压缩的滚动摘要） |
| `/session-list` | - | 🆕 列出所有会话 |
| `/session-switch <id>` | - | 🆕 切换到指定会话 |
| `/session-archive <id>` | - | 🆕 归档会话 |
| `/session-delete <id>` | - | 🆕 删除会话 |
| `/session-info <id>` | - | 🆕 查看会话详情 |
| `/session-search <query>` | - | 🆕 搜索会话 |
| `/session-current` | - | 🆕 显示当前会话信息 |
| `/session-compress` | - | 🆕 压缩当前会话历史 |
| `/model` | - | 显示当前模型（是否已加载、驻留大小、num_ctx、思考模式） |
| `/model list` | - | 🆕 列出本机已安装模型 |
| `/model <name>` | - | 🆕 运行时热切换模型并释放旧模型（如 `/model qwen3.5:9b`） |
| `/think` | - | 🆕 显示思考模式状态（默认关） |
| `/think on\|off` | - | 🆕 运行时开关思考模式（需模型支持，如 qwen3.5） |
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
| **critical** | 自动拦截 | `rm -rf /`, `dd if=/dev/zero`, `sudo rm` |
| **high** | 询问确认 | `rm file`, `del file`, `curl … \| sh`, `wget … \| bash` |
| **medium** | 询问确认 | `mv`, `cp`, `chmod`, `chown`, `tee`, `dd`, `sed -i`, `pip/npm/brew/apt install`, `git push/commit/reset/checkout/rebase/merge`, `python x.py`, `node x.js`, `make`, `docker run/exec` |
| **low** | 自动执行 | `ls`, `cat`, `git status`, `pytest`, `python -m pytest`, `pip show`, `git log --format=%H` |

分级按**子命令首 token**（剥掉 `sudo` / `env VAR=` / `xargs` 等前缀）匹配，不做子串匹配，
所以 `pip show models`、`ls performance/`、`python rm_all.py` 不会被误判；`ls | xargs rm`、
`sqlite3 a.db "DROP TABLE t"` 仍判 high。

`--yes` / `CODE_AGENT_AUTO_CONFIRM=true` 只跳过 **low / medium** 的确认；high 仍需人工确认
（无交互场景返回 `[提示] 高风险命令需人工确认`），critical 始终拦截。

路径边界：`write_file` / `add_to_knowledge_base` 只能操作当前工作目录或 `WRITE_ALLOWED_DIRS`
内的文件；所有读文件 / 目录的工具（`read_file` / `list_directory` / `search_files` / 项目分析 / AST /
质量检查 / Git 分析）与 Web「工具」页的浏览、预览、搜索只能读「写允许目录 + `READ_ALLOWED_DIRS`
+ 已入库文档所在目录」。用 `/config`（CLI）或「系统 → 运行环境」（Web）查看当前允许范围。

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

详细安全说明请查看：[内容安全扫描器文档](docs/development/CONTENT_SECURITY.md)

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
样本格式、指标含义、何时必须跑见 [TEST_DESIGN.md §7](docs/development/TEST_DESIGN.md#7-rag-检索基准f10-p1-32026-09)。

---

## 配置说明

编辑 `config.py` 或通过环境变量：

```python
# 模型配置
LLM_MODEL = "qwen3.5:4b"            # 全局唯一 LLM（Agent/RAG/多 Agent 共用），见下方「模型选择指南」
LLM_THINK = False                   # 思考模式，默认关闭（4B 模型响应 31s → 2.8s）
LLM_STREAM = True                   # 真流式输出：最终答案逐字出现、可随时中断（首字 6.6s → 0.2s）
LLM_NUM_CTX = 自动                  # 按模型参数量推导（4B→16K，7~9B→8K，12B+→4K），可用环境变量覆盖
LLM_PROVIDER = "ollama"             # 对话后端协议：ollama（默认）| openai（vLLM / LM Studio / 内网网关，见「接入 OpenAI 兼容后端」）
LLM_BASE_URL = OLLAMA_BASE_URL      # 对话后端地址（openai 模式下带不带 /v1 均可）
LLM_API_KEY = ""                    # openai 模式的 Bearer 令牌，本地服务留空
LLM_REASONING_EFFORT = "none"       # openai 模式 + 思考关闭时随请求发送的 reasoning_effort（空串则不发送）
OLLAMA_MAX_CONCURRENCY = 2          # 进程内同时在途的 LLM 请求上限（多 Agent 并行时其余排队；0 不限制）
EMBED_MODEL = "nomic-embed-text"     # 嵌入模型（始终由 Ollama 提供）

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
export LLM_MODEL="qwen3.5:9b"
export LLM_THINK=false
# 真流式输出（默认 true）：/ask /agent /multi 与 Web 三种模式的最终答案逐字出现，Ctrl+C / 「停止」立即关闭连接；
# 设为 false 回到整段一次性输出（请求体与旧版完全一致，适合排查问题或不支持流式的代理）
export LLM_STREAM=true
export LLM_NUM_CTX=16384
# LLM 后端（F10 P1-2）：默认 ollama；接 vLLM / LM Studio / llama.cpp server / 内网 OpenAI 兼容网关时设 openai。
# LLM_BASE_URL 未设置时取 OLLAMA_BASE_URL（Ollama 自带 /v1 兼容端点，可直接用来验证）；嵌入模型仍走 Ollama。
export LLM_PROVIDER=openai
export LLM_BASE_URL=http://localhost:1234
export LLM_API_KEY=                          # 本地服务通常不需要
export LLM_REASONING_EFFORT=none             # 思考关闭时发送的 reasoning_effort；后端不认识会自动去掉重试；设空不发送
# LLM 请求并发上限（F10 P2-1）：多 Agent 并行时子 Agent 各自请求同一 Ollama，单 GPU 上只会互相拖慢直至超时；
# 默认 2，其余请求在本地排队（进度显示"排队中"，排队时间不计入子任务超时）。接 vLLM 等支持批处理的后端可调大；0 不限制
export OLLAMA_MAX_CONCURRENCY=2
export CHUNK_SIZE=512
export CODE_AGENT_AUTO_CONFIRM=true
# 入口智能路由：自然语言输入 / Web「自动」模式先判定走 RAG 还是 Agent（默认 true；CLI 可 /auto on|off）
export AUTO_ROUTE=true
# Agent 系统提示分层（详见 prompts/README.md）：内置模板 → Skills（prompts/skills/*/SKILL.md，所有 Agent 角色）
# → 项目附加规范（prompts/system/PROJECT_RULES.md，仅 append 模式，截断到 SYSTEM_PROMPT_EXTRA_MAX_CHARS）
export CODE_AGENT_PROMPT_MODE=append          # builtin | append（默认）
export SYSTEM_PROMPT_EXTRA_MAX_CHARS=4000
export CODE_AGENT_SKILLS=on                   # off 关闭 Skills 层
export SKILL_MAX_CHARS=4000                   # Skills 层总字符上限
export AGENT_PROMPTS_DIR=~/my-prompts         # 额外 prompts 目录（冒号分隔，同名 Skill / PROJECT_RULES 覆盖内置）
# 单 Agent 鲁棒性：连续格式错误重试次数 / 单条 Observation 最大字符数
export MAX_FORMAT_RETRIES=2
export OBSERVATION_MAX_CHARS=3000
# write_file / add_to_knowledge_base 允许操作的额外目录（冒号分隔；当前工作目录始终允许）
export WRITE_ALLOWED_DIRS=~/Documents:~/Downloads
# read_file / list_directory / search_files 允许读取的额外目录（冒号分隔）；
# 实际允许读取 = 上面的写允许目录 ∪ READ_ALLOWED_DIRS ∪ 已入库文件所在目录
export READ_ALLOWED_DIRS=~/Documents
# RAG 推理：逐片段 rerank 方式 llm（默认，一次模型调用）| cross-encoder（需 pip install sentence-transformers，
# 未安装自动回退 llm）；cross-encoder 模型名；hybrid（向量 + BM25）召回开关
export RERANKER=llm
export RERANKER_MODEL=BAAI/bge-reranker-v2-m3
export RAG_HYBRID=true
# 混合检索的块数上限（默认 50000）：超过即只用向量检索，/stats 与 Web 知识库页会显示原因。BM25 语料（词频 + 来源元数据 +
# 索引）常驻内存，实测每万块约 100–150MB（取决于词汇量）：默认上限约需 0.5–0.75GB，8GB 机器建议 20000；
# 持久化文件 index_storage/bm25/store.json.gz 每万块约 1–9MB，损坏或分词版本升级时自动全量重建
export RAG_HYBRID_MAX_CHUNKS=50000
# 抗过度顺从：知识库命中后用同一模型逐句自校验"是否被资料支持"（每问多一次调用，默认关；结果以 ⚠️ 警示列出，不改正文）
export RAG_SELF_CHECK=false
# 代码感知分块：开关（缺 tree-sitter-language-pack 时自动回退）/ 单片段字符上限 / 碎片合并阈值
export CODE_AWARE_CHUNKING=true
export CODE_CHUNK_MAX_CHARS=1500
export CODE_CHUNK_MIN_CHARS=120

python query_interface.py --data ./data
```

---

## 接入 OpenAI 兼容后端

默认对话模型由本机 Ollama 提供。如果你已经有 **vLLM / LM Studio / llama.cpp server / 公司内网的 OpenAI 兼容网关**，
可以不装对话模型、直接让 Cerebro 复用它（F10 P1-2）：

```bash
# LM Studio（默认端口 1234；「Local Server」页启动后即可）
export LLM_PROVIDER=openai
export LLM_BASE_URL=http://localhost:1234        # 带不带 /v1 都行
export LLM_MODEL=qwen2.5-7b-instruct             # 后端里的模型 id（/v1/models 可查）

# vLLM
python -m vllm.entrypoints.openai.api_server --model Qwen/Qwen2.5-7B-Instruct --port 8000
export LLM_PROVIDER=openai LLM_BASE_URL=http://localhost:8000 LLM_MODEL=Qwen/Qwen2.5-7B-Instruct

# 内网网关（需要令牌）
export LLM_PROVIDER=openai LLM_BASE_URL=https://llm.corp.example LLM_API_KEY=sk-xxx LLM_MODEL=gpt-4o-mini

# 验证：Ollama 自带 /v1 兼容端点，可先用它跑通 openai 模式再换真实后端
export LLM_PROVIDER=openai LLM_BASE_URL=http://localhost:11434
python src/query_interface.py --query "知识库里有什么"
```

生效范围：ReAct Agent、多 Agent 协作、RAG 综合回答（LlamaIndex `OpenAILike`）、会话摘要压缩、AI 提交信息、
托盘预热与状态轮询。CLI `/config` `/model`、Web「系统」页会显示 `LLM 后端 / 后端地址 / 后端状态`；
`/model list` 读取后端 `/v1/models`，后端不提供时回退为当前模型并提示「后端未提供模型列表」（此时 `/model <name>` 可切到任意名字，不做校验）。

注意事项：

| 项 | 说明 |
|---|---|
| **嵌入仍需 Ollama** | 知识库入库 / 检索用的 `EMBED_MODEL`（默认 `nomic-embed-text`）始终走 `OLLAMA_BASE_URL`。只用 Agent 对话可以不开 Ollama；要用知识库就需要 `ollama pull nomic-embed-text`。启动引导会提示但不会安装。 |
| **`num_ctx` 由后端决定** | OpenAI 协议没有 Ollama 的 `num_ctx`，上下文窗口以后端启动参数为准（vLLM `--max-model-len`、LM Studio 加载时的 Context Length）。Cerebro 仍按模型名推导 `LLM_NUM_CTX` 只用于历史 / 片段的 token 预算，可用 `LLM_NUM_CTX` 对齐后端实际值。 |
| **思考模式** | 没有 `think` 字段。思考关闭（默认）时随请求发送标准字段 `reasoning_effort=none`（Ollama `/v1`、OpenAI 均识别；否则 qwen3.5 这类模型会把输出预算全部花在 reasoning 上、回答为空）；后端返回 400 不认识该字段时自动去掉重试并记住。可用 `LLM_REASONING_EFFORT` 改为 `low/medium/high` 或设空不发送。 |
| **模型切换 / 卸载** | `/model <name>` 只改全局模型名；「释放旧模型」「已加载 / 驻留大小」是 Ollama 专有能力，openai 模式下不显示。 |
| **options 映射** | `temperature` 直传，`num_predict → max_tokens`，其余 Ollama `options` 忽略。 |

---

## 模型选择指南

Cerebro 采用「单一模型」架构：一个 LLM 同时驱动 RAG 综合、ReAct Agent 与多 Agent 协作，
全程只驻留一个模型。默认 **`qwen3.5:4b`（协同档）**：16K 上下文实测约 **3.7GB** 驻留，
可与 IDEA / PyCharm / 浏览器在 16GB 机器上并行运行；工具调用、中文归纳、长文本与代码
能力足以覆盖日常查询、报告分析、文件整理、SQL 查询与简单重构。

### 按场景推荐

| 场景 | 内存 | 推荐模型 | 说明 |
|---|---|---|---|
| **日常助手，与 IDE/浏览器并行（默认）** | 16GB | `qwen3.5:4b` | 约 3.7GB 驻留，M4 实测 ~25 tok/s |
| 专注模式 / 复杂重构 / 多步 Agent | 16GB（关闭 IDE）或 32GB | `qwen3.5:9b` | 约 6GB 驻留，~16 tok/s；工具调用（BFCL 66 vs 50）、SWE-Bench（53 vs 39）明显更强 |
| 低配 / 老机器 | 8GB | `qwen3.5:2b` | 约 1.9GB，适合问答与检索 |
| 工作站 | 32GB+ 或 24GB 显卡 | `qwen3.5:27b` / `gemma4:26b` | 17~19GB |
| 严格格式化输出 / 翻译为主，不依赖工具调用 | 16GB（关闭 IDE） | `gemma4:12b-it-qat` | 指令遵循最强（IFEval 94.8），但工具调用偏弱（BFCL 37） |
| Embedding（所有场景） | — | `nomic-embed-text:latest` | 固定 |

> 基准分数来自各模型官方页公开的模型卡数据；吞吐/驻留为 Apple M4 MacBook Air 16GB 实测。

**小模型更容易"过度顺从"**（H-Neurons 研究，arXiv 2512.01797：<10B 模型接受错误前提、被反驳就改口的倾向明显更强，
且换 instruct 版本不能解决）。本项目在模型外围加了忠实性条款、引用程序化校验与结构化警示（见「模式一」的 F9 段），
但对**重要事实请务必**用 `/sources` 与回答后的 `🔎 引用 v/t 有效` 校验行核对，不要仅凭答案文字。
切换模型前后可用评测脚本对比抗过度顺从表现（需本机 Ollama，规则词表判定，不用 LLM 当裁判）：

```bash
./venv/bin/python scripts/eval_overcompliance.py --model qwen3.5:4b            # 30 例：错误前提 / 误导片段 / 被质疑 / 虚构实体
./venv/bin/python scripts/eval_overcompliance.py --model qwen3.5:9b --out /tmp/eval-9b.json -v
```

### 三种切换方式

```bash
# 1) 启动时指定
python src/query_interface.py --model qwen3.5:9b

# 2) 环境变量
export LLM_MODEL=qwen3.5:9b

# 3) 运行中热切换（CLI）—— 同步 RAG/Agent/多 Agent，并立即释放旧模型
/model            # 查看当前模型、是否已加载、驻留大小
/model list       # 列出本机已安装模型
/model qwen3.5:9b # 切换
```

Web 界面：「系统 → 模型」页有**模型下拉**（或点击模型表格行），选择后点「切换模型」即时生效；旁边的**「思考模式」复选框**可随时开关（模型不支持时会自动回弹并提示）。顶栏胶囊始终显示当前模型、驻留情况、num_ctx 与思考模式。

### 与 IDE 共存的内存实践

- **思考模式默认关闭**（`LLM_THINK=false`）：ReAct 的 Thought/Action 已是显式推理，再叠加隐式思维链只会拖慢。同一问题 qwen3.5:4b 从 31s 降到 2.8s。需要深度推理时可**运行中开启**：CLI `/think on`、Web 勾选「思考模式」，或启动前 `LLM_THINK=true`。仅 `ollama show <model>` 的 Capabilities 含 `thinking` 的模型（qwen3.5 系列等）支持，`/think on` 会自动校验。
- **桌面应用默认不预热**（`warm_up_on_startup: false`）：预热会让模型常驻；Ollama 会在首问时按需加载，闲置 5 分钟后释放。内存宽裕可改回 `true` 换首问速度，或设 `OLLAMA_KEEP_ALIVE=2m` 更快归还内存。
- **上下文自动推导**：4B→16K，7~9B→8K，12B+→4K；每 +16K 约多占 0.6GB（4B 实测）。长文档任务可临时 `LLM_NUM_CTX=32768`。
- **避免双驻留**：Ollama 只在"放不下"时才驱逐旧模型，4B+9B 会被同时保留。项目的 `/model` 切换会主动释放旧模型；若曾用 `ollama run` 手动加载过其他模型，`/model` 会给出提示，用 `ollama stop <name>` 释放。

### 关注中（暂不推荐）

`SparkLLM/Spark-X2.5-4B` 在同尺寸模型中 Agent / 代码基准领先（BFCL 65、SWE-Bench Pro 44），
但官方 Ollama 尚不支持其 `spark2_5` 架构（llama.cpp [PR #27868](https://github.com/ggml-org/llama.cpp/pull/27868) 进行中），
目前需自编译运行时且仅有 8.2GB 未量化版本。待上游合入并提供量化 tag 后再评估。

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
3. **模型选择**：默认 `qwen3.5:4b` 兼顾速度与能力；内存宽裕时切 `qwen3.5:9b`，详见[模型选择指南](#模型选择指南)
4. **硬件要求**：4B 模型约 3.7GB 驻留（16K 上下文），9B 约 6GB；16GB 机器与 IDE 并行请用 4B
5. **思考模式**：默认关闭（`LLM_THINK=false`），同一问题 31s → 2.8s；仅复杂推理时开启

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
- [x] Web UI（Gradio，`python launcher.py --web`）
- [x] 图片/图表 OCR 提取
- [x] Git 集成（历史/状态/作者分析、AI 提交信息）
- [x] 代码质量自动检查（AST 搜索、质量检查）
- [x] 运行时模型热切换（CLI `/model` / Web 下拉）
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

# 查看快照详情（文档清单、文件是否仍在磁盘）
>>> /snapshot-info <snapshot_id>

# 生成恢复脚本 / 直接恢复（追加）/ 先清空再恢复
>>> /snapshot-restore <snapshot_id>
>>> /snapshot-restore <snapshot_id> --apply
>>> /snapshot-restore <snapshot_id> --apply --replace

# 删除快照 / 清理自动快照仅保留最近 5 个
>>> /snapshot-delete <snapshot_id>
>>> /snapshot-prune 5
```

#### 2. 知识库到Skill智能转化
- **智能分类**: 自动区分通用型vs项目型文档
- **主题合并**: 按主题合并多个文档生成统一skill
- **多平台支持**: 同时支持 OpenCode 和 Claude 平台
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

内容安全扫描器的详细说明请查看：[内容安全扫描器文档](docs/development/CONTENT_SECURITY.md)

---

## �📚 文档资源

- **[详细使用教程](TUTORIAL.md)** - 教程导航：安装配置、功能说明、实战场景、桌面应用、故障排除、最佳实践
- **[实战场景示例](docs/tutorials/03-scenarios.md)** - 14 个实战场景（学术、开发、OCR、多 Agent、文件与会话管理等）
- **[安装和配置指南](docs/tutorials/02-installation.md)** - 含一键前置条件检查（`scripts/check_prereqs.sh`）
- **[故障排除指南](docs/tutorials/06-troubleshooting.md)** - 依赖冲突、ChromaDB 遥测错误、urllib3 OpenSSL 警告等
- **[测试设计文档](docs/development/TEST_DESIGN.md)** - 测试 Mock 策略与可测性设计（覆盖率门禁 80%）；§7 RAG 检索基准（`scripts/eval_rag.py`，报告在 `docs/development/rag-eval/reports/`）
- **[文档中心](docs/README.md)** - 功能实现文档、未来特性设计、CI/CD 与历史报告索引
- **[内容安全扫描器文档](docs/development/CONTENT_SECURITY.md)** - `content_security.py` 的 API 与集成方式

### 快速链接

- **使用场景** → [实战场景示例](docs/tutorials/03-scenarios.md)
- **安装问题** → [安装和配置指南](docs/tutorials/02-installation.md)
- **功能详解** → [详细功能说明](docs/tutorials/04-features.md)
- **安全配置** → [安全机制](docs/tutorials/04-features.md#5-安全机制)
- **故障排除** → [故障排除指南](docs/tutorials/06-troubleshooting.md)
- **依赖冲突** → [依赖冲突问题](docs/tutorials/06-troubleshooting.md#依赖冲突问题-resolution-too-deep)
- **警告问题** → [ChromaDB / urllib3 警告](docs/tutorials/06-troubleshooting.md#chromadb相关问题)
- **桌面应用** → [桌面应用使用指南](docs/tutorials/05-desktop-app.md)
- **安全防护** → [内容安全扫描器文档](docs/development/CONTENT_SECURITY.md)

---

## 技术栈

| 组件 | 用途 |
|------|------|
| Ollama | 本地 LLM 推理 |
| qwen3.5:4b（默认，可热切换 9b/27b） | 通用理解 / 代码 / 工具调用 |
| nomic-embed-text | 文本语义嵌入 |
| LlamaIndex | RAG 框架 |
| ChromaDB | 向量数据库 |
| ReAct | 推理+行动循环 |
| Rich | 终端美化 |

---

*Cerebro — 你的第二大脑 + 代码助手 🧠💻*
