# 智能文档+代码助手 v3.0

基于 **Ollama qwen2.5-coder:7b** 的融合型 AI 助手，同时支持 **RAG 知识库检索** 和 **ReAct Agent 代码操作**。

---

## 融合架构

```
┌─────────────────────────────────────────────────────────────────────┐
│                        统一 CLI 交互层                               │
│         /ask (知识库)  /agent (Agent任务)  /file /exec ...          │
└─────────────────────────────────────────────────────────────────────┘
                              │
          ┌───────────────────┴───────────────────┐
          ▼                                       ▼
┌─────────────────────────────┐    ┌─────────────────────────────┐
│      📚 RAG 知识库引擎       │    │      🤖 ReAct Agent 引擎    │
│  LlamaIndex + ChromaDB      │    │  Thought → Action → Observe │
│  语义检索 + 来源追溯         │    │  自动工具调用 + 安全护栏      │
│  PDF/论文/笔记/代码          │    │  读写文件 / 执行命令 / 搜索  │
└─────────────────────────────┘    └─────────────────────────────┘
          │                                       │
          └───────────────────┬───────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     Ollama qwen2.5-coder:7b                         │
│              统一 LLM：文档理解 + 代码生成 + 推理                   │
│              Embedding: nomic-embed-text (语义编码)                 │
└─────────────────────────────────────────────────────────────────────┘
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

---

## 快速开始

### 前置条件检查（推荐）

在开始之前，建议运行前置条件检查脚本：

**Linux/macOS:**
```bash
./check_prereqs.sh
```

**Windows:**
```powershell
.\check_prereqs.ps1
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
./install_deps.sh      # Linux/macOS
.\install_deps.ps1     # Windows PowerShell
```

**标准方法：**
```bash
pip install -r requirements.txt
```

**如果遇到依赖冲突（如 "resolution-too-deep" 错误）：**
```bash
# 使用备用配置
pip install -r requirements_alternative.txt

# 或查看详细文档：[依赖冲突故障排除](TUTORIAL.md#依赖冲突问题-resolution-too-deep)
```

**如果遇到ChromaDB遥测错误：**
```bash
# 项目已自动禁用遥测，如仍遇到错误：
export ANONYMIZED_TELEMETRY=False

# 或查看详细文档：[ChromaDB遥测错误](TUTORIAL.md#问题5chromadb遥测错误)
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
├── config.py              # 统一配置（RAG + Agent）
├── document_loader.py     # 多格式文档加载器
├── rag_engine.py          # RAG 核心引擎（向量索引 + Agent 工具接口）
├── react_engine.py        # ReAct 推理引擎（qwen2.5-coder:7b）
├── agent_tools.py         # 工具链（文件/命令/搜索 + RAG 查询/添加）
├── chat_history.py        # 对话历史持久化
├── query_interface.py     # 统一 CLI 入口
├── knowledge_to_skills.py # 知识库到Skill智能转化引擎
├── knowledge_snapshot.py  # 知识库快照系统
├── content_security.py    # 内容安全扫描器（防止提示词攻击）
├── example.py             # 快速示例
├── requirements.txt       # 依赖
├── data/                  # 文档存放目录
├── index_storage/         # 索引持久化存储
│   ├── chroma_db/         # ChromaDB 向量数据库
│   └── llama_index/       # LlamaIndex 索引文件
├── docs/                  # 文档目录
│   ├── KNOWLEDGE_OPTIMIZATION_SUMMARY.md  # 知识库优化实现总结
│   ├── SECURITY_DOCUMENTATION.md           # 安全功能文档
│   └── ...                                # 其他文档
├── tests/                 # 单元测试
└── README.md
```

---

## 双模式使用指南

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

---

## 统一命令速查

| 命令 | 模式 | 说明 |
|------|------|------|
| `/ask <问题>` | RAG | 直接查询知识库 |
| `/agent <任务>` | Agent | 进入 ReAct 自动任务模式 |
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
| `/model` | - | 显示模型信息 |
| `/tutorial` | - | 使用教程 |
| `/help` | - | 帮助 |
| `/quit` | - | 退出 |

---

## 核心模块说明

### `rag_engine.py` — RAG 引擎

```python
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

```python
from document_loader import load_documents

# 加载整个目录
docs = load_documents("./data")

# 加载指定类型
docs = load_documents("./data", file_types=[".pdf", ".md"])

# 加载单个文件
docs = load_documents("./论文.pdf")
```

---

## 安全机制

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

详细安全说明请查看：[安全功能文档](docs/SECURITY_DOCUMENTATION.md)

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

详细实现说明请查看：[知识库优化实现总结](docs/KNOWLEDGE_OPTIMIZATION_SUMMARY.md)

---

## �📚 文档资源

- **[详细使用教程](TUTORIAL.md)** - 完整的前置条件配置、安装指南、功能说明、故障排除
- **[使用场景详细指南](docs/USE_CASES.md)** - 8大类别40+实战场景示例和最佳实践
- **[快速开始检查](docs/QUICK_START_CHECK.md)** - 一键验证环境配置
- **[警告问题修复说明](docs/WARNING_FIX.md)** - ChromaDB遥测错误和urllib3 OpenSSL警告的修复
- **[测试设计文档](docs/TEST_DESIGN.md)** - 单元测试设计和覆盖率说明（当前覆盖率87%）
- **[知识库优化实现总结](docs/KNOWLEDGE_OPTIMIZATION_SUMMARY.md)** - 知识库智能优化功能的完整实现说明
- **[安全功能文档](docs/SECURITY_DOCUMENTATION.md)** - 内容安全扫描器的详细使用指南

### 快速链接

- **使用场景** → [使用场景详细指南](docs/USE_CASES.md)
- **安装问题** → [前置条件检查与配置](TUTORIAL.md#前置条件检查与配置)
- **功能详解** → [详细功能说明](TUTORIAL.md#详细功能说明)
- **安全配置** → [安全机制](TUTORIAL.md#安全机制)
- **故障排除** → [故障排除](TUTORIAL.md#故障排除)
- **依赖冲突** → [依赖冲突问题](TUTORIAL.md#依赖冲突问题-resolution-too-deep)
- **警告问题** → [警告问题修复说明](docs/WARNING_FIX.md)
- **知识库优化** → [知识库优化实现总结](docs/KNOWLEDGE_OPTIMIZATION_SUMMARY.md)
- **安全防护** → [安全功能文档](docs/SECURITY_DOCUMENTATION.md)

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

*你的第二大脑 + 代码助手 🧠💻*
