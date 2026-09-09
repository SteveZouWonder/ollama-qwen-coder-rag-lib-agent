# 详细功能说明

> 本文档详细介绍智能文档+代码助手的核心功能和使用方法。

---

## 1. RAG知识库功能

### 支持的文档格式

RAG引擎支持多种文档格式：

- **PDF文档**: .pdf
- **文本文档**: .txt, .md
- **代码文件**: .py, .js, .ts, .java, .c, .cpp, .go, .rs
- **网页文件**: .html, .xml
- **配置文件**: .json, .yaml, .yml
- **图片文件**: .png, .jpg, .jpeg, .gif, .bmp, .tiff (需要 OCR 功能)
- **其他**: 支持LlamaIndex的所有文档格式

### OCR 图像识别功能 (NEW)

系统集成了强大的 OCR 功能，可以处理扫描版 PDF 和图片文件：

#### 功能特性

- **扫描版 PDF**: 自动识别扫描版 PDF 中的文本内容
- **图片文件**: 直接识别 PNG、JPG、JPEG、GIF、BMP、TIFF 等格式
- **中英文混合**: 基于 PaddleOCR 实现高精度的中英文识别
- **PDF 图片提取**: 自动提取 PDF 中的嵌入图片并进行 OCR 识别
- **智能缓存**: 基于文件哈希的缓存机制，避免重复处理
- **并行处理**: 支持批量图片并行处理，提升处理效率

#### 安装 OCR 依赖

```bash
# 安装 OCR 核心依赖
pip install paddlepaddle==2.5.2
pip install paddleocr==2.7.0.3
pip install pytesseract==0.3.10
pip install pymupdf==1.23.8
pip install opencv-python==4.8.1.78
pip install pillow==10.1.0

# 安装 Tesseract（系统级）
# macOS
brew install tesseract tesseract-lang

# Linux (Ubuntu/Debian)
sudo apt-get install tesseract-ocr tesseract-ocr-chi-sim tesseract-ocr-chi-tra

# Windows
# 下载安装程序：https://github.com/UB-Mannheim/tesseract/wiki
```

#### 配置 OCR 功能

在 `config.py` 中配置：

```python
# OCR 开关
OCR_ENABLED = True  # 是否启用 OCR 功能
OCR_ENGINE = "paddle"  # OCR 引擎：paddle | tesseract | hybrid

# OCR 缓存配置
OCR_CACHE_DIR = INDEX_DIR / "ocr_cache"
OCR_PARALLEL_WORKERS = 2  # 并行处理任务数
OCR_CACHE_TTL_DAYS = 30  # 缓存过期时间（天）

# PaddleOCR 配置
PADDLE_USE_GPU = False  # 是否使用 GPU
PADDLE_LANG = "ch"  # 语言：ch(中文) | en(英文) | jk(日韩)

# Tesseract 配置
TESSERACT_PATH = "/usr/local/bin/tesseract"
TESSERACT_LANG = "chi_sim+eng"  # 语言包
```

#### 使用 OCR 功能

**在 RAG 知识库中使用**:
```bash
# 启用 OCR 加载文档
python query_interface.py --data ./data

# OCR 会自动处理：
# - 扫描版 PDF
# - 图片文件
# - PDF 中的嵌入图片
```

**编程方式使用**:
```python
from document_loader import DocumentLoader

# 创建启用 OCR 的加载器
loader = DocumentLoader(enable_ocr=True)

# 加载图片文件
documents = loader.load_file('scanned_page.png')

# 加载 PDF（自动提取图片并 OCR）
documents = loader.load_file('document_with_images.pdf')
```

**直接使用 OCR 引擎**:
```python
from ocr_processor import PaddleOCREngine

# 创建 OCR 引擎
config = {
    'use_gpu': False,
    'lang': 'ch',
    'cache_dir': './cache'
}
ocr = PaddleOCREngine(config)

# 识别图片
from pathlib import Path
results = ocr.recognize_image(Path('image.png'))

for result in results:
    print(f"文本: {result.text}")
    print(f"置信度: {result.confidence}")
    print(f"位置: {result.bbox}")
```

### 知识库构建

```bash
# 构建知识库
python -c "
from rag_engine import build_knowledge_base

# 构建知识库
engine = build_knowledge_base('./data')

# 保存索引
engine.storage_context.persist()
"
```

**知识库特性**:
- 自动分块和向量化
- 智能语义索引
- 来源追溯
- 增量更新支持

### 查询方式

**交互式查询**:
```bash
python query_interface.py --data ./data
>>> /ask 你的问题
```

**编程接口**:
```python
from rag_engine import build_knowledge_base

# 构建知识库
engine = build_knowledge_base('./data')

# 查询
response = engine.query("你的问题")
print(response)
```

### CLI命令

```bash
# 查询知识库
python query_interface.py --data ./data --query "你的问题"

# 查看统计信息
>>> /stats

# 查看来源
>>> /sources

# 添加新文档
>>> /add ./新文档.pdf
```

### 引用校验行与可信度提示（F9）

每次 `/ask` 回答后，来源摘要行会附带**引用校验行**，Web 状态行同样显示：

```
📚 基于知识库 4 个片段 · 🔎 引用 5/6 有效        ← CLI（有无效引用时整行黄色）
✅ 完成 · 用时 12 秒 · 🔎 引用 6 处已核验          ← Web（全部有效）
```

- 答案中的 `[1]`、`[W2]` 会逐个与来源编号核对，**不存在的编号被改写为 `[?]`**，请以 `/sources`（Web「📎 引用来源」
  面板，出现无效引用时自动展开）为准；`/sources` 表新增「引用」列显示每条来源被引用次数，`—` 表示未被引用。
- 答案上方 / 下方的黄色 `⚠️ …`（Web 为 `> ⚠️ …`）表示**该回答的依据情况**，例如：
  `知识库无相关内容 · 回答基于网络搜索`、`无资料依据 · 模型自身知识 · 请自行核实`；dim 的 `💡 N 句含数字但未标来源`
  提示有数字句子没有来源编号，需要自行核对。
- 追问时若你在**反驳上一轮回答**（"不对 / 错了 / 应该是 / 确定吗"等），提示行会变为
  `🔁 用户质疑，重新核对：…`——系统会重新核对资料，资料支持原答案时会坚持并给出编号，而不是顺着你改口。
- 小模型（默认 `qwen3.5:4b`）更容易顺着问题的错误前提回答，上述提示与校验就是为此设计的；可用
  `scripts/eval_overcompliance.py --model <name>` 对比不同模型的表现。

---

## 2. ReAct Agent功能

### 工作原理

ReAct (Reasoning + Acting) Agent 通过以下循环执行任务：

1. **Thought**: 思考当前状态和下一步行动
2. **Action**: 选择并执行工具
3. **Observation**: 观察执行结果
4. **Repeat**: 重复直到达到目标

### 可用工具

**文件操作工具**:
- `read_file`: 读取文件内容
- `write_file`: 写入文件内容
- `search_file`: 搜索文件内容

**命令执行工具**:
- `execute_command`: 执行shell命令

**RAG查询工具**:
- `rag_query`: 查询知识库
- `rag_add`: 添加文档到知识库

**搜索工具**:
- `web_search`: 网络搜索（可选）

### CLI命令

```bash
# Agent任务
python query_interface.py --agent "你的任务描述"

# 交互式Agent
python query_interface.py
>>> /agent 你的任务描述
```

**Agent任务示例**:
```bash
>>> /agent 写一个Python快速排序，保存到sort.py，然后运行测试
>>> /agent 分析当前目录的代码结构，生成README
>>> /agent 检查所有.py文件的语法错误
```

---

## 3. 文件操作工具

### 读取文件

**Agent中使用**:
```bash
>>> /agent 读取config.yaml的内容
```

**编程接口**:
```python
from agent_tools import read_file_tool

content = read_file_tool('config.yaml')
print(content)
```

### 写入文件

**Agent中使用**:
```bash
>>> /agent 将这段代码写入utils.py
```

**编程接口**:
```python
from agent_tools import write_file_tool

code = """
def hello():
    print("Hello World")
"""
write_file_tool('utils.py', code)
```

### 搜索功能

**Agent中使用**:
```bash
>>> /agent 在项目中搜索所有包含"API Key"的文件
```

**编程接口**:
```python
from agent_tools import search_file_tool

results = search_file_tool('API Key', './src')
print(results)
```

---

## 4. 对话历史

### 历史管理

系统自动维护对话历史，支持：

- 多轮对话上下文
- 历史持久化
- 历史查询和清理

### 历史命令

```bash
# 查看历史
>>> /history

# 清除历史
>>> /clear

# 导出历史
>>> /export history.json
```

---

## 5. 安全机制

### 命令安全检查

所有执行命令都会经过安全检查：

- 危险命令检测（rm, format等）
- 用户确认机制
- 操作范围限制

### 用户确认机制

```bash
# 需要确认的操作
>>> /agent 删除所有临时文件

# 系统会提示
⚠️ 警告：此操作将删除文件
确认执行？(y/n): _
```

### 内容安全防护

自动检测和防护提示词攻击：

- 注入攻击检测
- 越权操作防护
- 数据泄露防护

---

## 6. 高级功能

### 自定义模型配置

```python
# 在代码中配置
from config import Config

config = Config()
config.llm_model = "custom-model"
config.embed_model = "custom-embed"
```

### 批量文档处理

```bash
# 批量添加文档
for file in data/*.pdf; do
    python query_interface.py --data ./data --add "$file"
done
```

### 多模型切换

```bash
# 启动前切换到不同模型
export LLM_MODEL=qwen3.5:9b
python query_interface.py --data ./data
```

**运行中热切换（CLI 命令）**:

```bash
/model             显示当前模型（是否已加载、驻留大小、num_ctx、思考模式）
/model list        列出本机已安装模型
/model <name>      运行时热切换模型，旧模型立即释放（如 /model qwen3.5:9b）
/think             显示思考模式状态（默认关，响应快）
/think on|off      运行时开关思考模式（需模型支持，如 qwen3.5；不支持时会提示）
```

---

## 7. 文件管理优化 ⭐ v4.1.0新功能

### 概述

v4.1.0版本引入了智能文件管理系统，提供文件验证、元数据管理、智能OCR优化等功能，显著提升文件处理效率和存储利用率。

### 文件验证功能

**功能特性**:
- 文件大小限制（默认10MB单文件，100MB总大小）
- 文件类型白名单控制
- 阻塞模式过滤（*.tmp, *.cache, *.log等）
- 文件哈希去重
- 总大小限制检查

**配置参数**:
```python
# config.py
MAX_FILE_SIZE = 10485760  # 10MB
MAX_TOTAL_SIZE = 104857600  # 100MB
ALLOWED_FILE_TYPES = ["pdf", "md", "txt", "py", "js", "ts", "java", "cpp", "go", "rs", "html", "json", "yaml", "xml"]
BLOCKED_FILE_PATTERNS = ["*.tmp", "*.cache", "*.log", "node_modules", "__pycache__"]
ENABLE_FILE_DEDUPLICATION = True
```

**环境变量配置**:
```bash
export MAX_FILE_SIZE=10485760        # 10MB
export MAX_TOTAL_SIZE=104857600      # 100MB
export ALLOWED_FILE_TYPES=pdf,md,txt,py,js,ts
export BLOCKED_FILE_PATTERNS=*.tmp,*.cache
export ENABLE_FILE_DEDUPLICATION=true
```

### 文件管理CLI命令

| 命令 | 说明 | 示例 |
|------|------|------|
| `/file-list` | 列出知识库中的所有文件 | `/file-list` |
| `/file-info <path>` | 查看文件详细信息 | `/file-info document.pdf` |
| `/file-cleanup` | 清理临时/重复文件 | `/file-cleanup` |
| `/file-deduplicate` | 手动触发去重 | `/file-deduplicate` |
| `/file-stats` | 显示文件统计信息 | `/file-stats` |

**使用示例**:
```bash
# 查看所有文件
>>> /file-list
📁 共有 5 个文件:
  📄 document.pdf
  📊 大小: 2.50 MB
  🏷️ 类型: permanent
  📅 上传: 2026-06-12 10:30:00

# 查看文件详情
>>> /file-info document.pdf
📄 文件信息: document.pdf
📊 大小: 2.50 MB
🏷️ 类型: permanent
📅 上传: 2026-06-12 10:30:00
🔢 访问次数: 5
📄 文档数: 10
🧩 Chunk数: 150

# 清理临时文件
>>> /file-cleanup
🧹 发现 2 个需要清理的文件
✅ 已清理 2 个文件

# 显示统计
>>> /file-stats
📊 文件统计信息:
📁 总文件数: 5
💾 总大小: 10.50 MB
📌 永久文件: 3
⏰ 临时文件: 2
🎯 会话文件: 0
🧹 待清理: 2
📈 利用率: 10.5%
```

### 智能OCR优化

**功能特性**:
- 图片质量评估（分辨率、模糊度）
- OCR结果缓存（基于文件哈希）
- 图片大小限制（5MB）
- 优先处理小文件
- 批量处理优化

**配置参数**:
```python
# config.py
OCR_CACHE_ENABLED = True
OCR_QUALITY_THRESHOLD = 0.3
OCR_MAX_IMAGE_SIZE = 5242880  # 5MB
```

**性能提升**:
- OCR处理效率提升30-50%
- 存储空间优化40-60%（去重和缓存）
- 用户体验显著改善

### 最佳实践

1. **合理设置大小限制**: 根据存储资源调整文件大小限制
2. **定期清理**: 使用 `/file-cleanup` 定期清理临时文件
3. **使用标签**: 为重要文件添加标签，便于管理
4. **监控存储**: 使用 `/file-stats` 监控存储使用情况

详细文档请参考: [文件管理和会话管理功能文档](../features/f3-file-session-management/FEATURES_FILE_AND_SESSION_MANAGEMENT.md)

---

## 8. 会话管理优化 ⭐ v4.1.0新功能

### 概述

v4.1.0版本引入了强大的会话管理系统，支持多会话、历史压缩、会话搜索等功能，让对话管理更加灵活高效。

### 多会话管理

**功能特性**:
- 多会话创建/切换/删除/归档
- 会话标签和元数据
- 会话搜索功能
- 会话持久化存储
- 自动归档旧会话（30天）

**会话状态**:
- `ACTIVE` - 活跃会话
- `ARCHIVED` - 归档会话
- `DELETED` - 已删除会话

**配置参数**:
```python
# config.py
SESSION_STORAGE_PATH = "~/.code_agent_sessions"
MAX_SESSIONS = 50
MAX_MESSAGES_PER_SESSION = 100
AUTO_ARCHIVE_DAYS = 30
HISTORY_COMPRESSION_RATIO = 0.5
AUTO_COMPRESS_ENABLED = True
```

**环境变量配置**:
```bash
export MAX_SESSIONS=50
export MAX_MESSAGES_PER_SESSION=100
export AUTO_ARCHIVE_DAYS=30
export HISTORY_COMPRESSION_RATIO=0.5
export AUTO_COMPRESS_ENABLED=true
export SESSION_STORAGE_PATH=~/.code_agent_sessions
```

### 会话管理CLI命令

| 命令 | 说明 | 示例 |
|------|------|------|
| `/session-new [title]` | 创建新会话 | `/session-new 工作项目` |
| `/session-list` | 列出所有会话 | `/session-list` |
| `/session-switch <id>` | 切换到指定会话 | `/session-switch abc123` |
| `/session-archive <id>` | 归档会话 | `/session-archive abc123` |
| `/session-delete <id>` | 删除会话 | `/session-delete abc123` |
| `/session-info <id>` | 查看会话详情 | `/session-info abc123` |
| `/session-search <query>` | 搜索会话 | `/session-search Python` |
| `/session-current` | 显示当前会话信息 | `/session-current` |
| `/session-compress` | 压缩当前会话历史 | `/session-compress` |

**使用示例**:
```bash
# 创建新会话
>>> /session-new 工作项目
✅ 新会话已创建: abc123...
📋 标题: 工作项目
📅 创建时间: 2026-06-12 10:30:00

# 列出所有会话
>>> /session-list
💬 共有 3 个会话:
🔸 🟢 工作项目 (abc123...)
    📅 2026-06-12 10:30
    💬 15 条消息
  🟢 学习笔记 (def456...)
    📅 2026-06-11 15:20
    💬 8 条消息
  📦 归档项目 (ghi789...)
    📅 2026-06-10 09:00
    💬 25 条消息

# 切换会话
>>> /session-switch def456
✅ 已切换到会话: 学习笔记
💬 该会话有 8 条消息

# 搜索会话
>>> /session-search Python
🔍 找到 2 个包含 'Python' 的会话:
  • 工作项目 (abc123...)
    💬 15 条消息
  • 学习笔记 (def456...)
    💬 8 条消息

# 压缩历史
>>> /session-compress
🔄 正在压缩会话历史...
✅ 压缩完成: 15 → 8 条消息
📊 压缩率: 46.7%
```

### 历史压缩功能

**功能特性**:
- 智能历史摘要压缩
- 消息去重压缩
- 按话题分块压缩
- 上下文窗口优化
- 压缩统计信息

**压缩策略**:
- 默认保留最近50%的消息
- 旧消息压缩为摘要
- 支持按话题分块
- 可配置压缩比例

**性能提升**:
- 历史存储优化70-90%（压缩功能）
- 多会话支持管理多个对话主题
- 搜索能力快速找到历史对话
- 智能建议基于上下文建议相关会话

### 最佳实践

1. **按项目分类**: 为不同项目创建独立会话
2. **定期归档**: 归档不再需要的旧会话
3. **压缩历史**: 定期压缩长会话的历史记录
4. **使用搜索**: 利用搜索功能快速找到相关对话

详细文档请参考: [文件管理和会话管理功能文档](../features/f3-file-session-management/FEATURES_FILE_AND_SESSION_MANAGEMENT.md)

---

## 9. 多Agent协作系统 ⭐ v4.0.0新功能

### 概述

多Agent协作系统通过多个专业Agent协同工作，实现复杂任务的智能分解和并行处理。系统包含：

- **5个专业Agent**: CodeAgent、RAGAgent、TestAgent、DocAgent、AuditAgent
- **4种协作模式**: Parallel（并行）、Sequential（顺序）、Hierarchy（层级）、Competitive（竞争）
- **智能任务分解**: 自动将复杂任务拆分为子任务
- **灵活调度**: 根据Agent能力和状态智能分配任务
- **结果整合**: 自动整合多个Agent的结果

### 专业Agent类型

#### CodeAgent - 代码专家
- **代码生成**: 根据需求生成功能代码
- **代码重构**: 优化代码结构和质量
- **代码审查**: 检查代码质量和安全
- **调试修复**: 定位和修复bug

#### RAGAgent - 知识库专家
- **知识检索**: 查询知识库获取信息
- **文档分析**: 分析文档内容和结构
- **文献综述**: 生成文献综述报告
- **知识提取**: 从文档中提取关键信息

#### TestAgent - 测试专家
- **测试生成**: 自动生成单元测试
- **覆盖率分析**: 分析测试覆盖率
- **质量评估**: 评估代码质量
- **测试执行**: 执行测试并报告结果

#### DocAgent - 文档专家
- **API文档**: 生成API接口文档
- **技术文档**: 编写技术架构文档
- **用户指南**: 创建用户使用指南
- **文档更新**: 更新和维护现有文档

#### AuditAgent - 审计专家
- **安全检查**: 检查代码安全漏洞
- **合规验证**: 验证合规性要求
- **性能审计**: 评估系统性能
- **代码审计**: 代码质量审计

### 协作模式

#### Parallel（并行）模式
多个Agent同时执行独立任务，适合互不依赖的任务场景。

```bash
# 并行模式示例
>>> /multi 实现用户认证功能并生成测试 PARALLEL
```

**使用场景**:
- 同时生成代码和文档
- 并行执行多个独立功能
- 多角度分析同一问题

#### Sequential（顺序）模式
按照任务依赖顺序依次执行，适合有依赖关系的任务链。

```bash
# 顺序模式示例
>>> /multi 重构代码，添加测试，更新文档 SEQUENTIAL
```

**使用场景**:
- 代码 → 测试 → 文档
- 分析 → 设计 → 实现
- 构建 → 测试 → 部署

#### Hierarchy（层级）模式
MasterAgent分解任务并协调专业Agent执行，适合复杂任务。

```bash
# 层级模式示例
>>> /multi 开发完整的用户认证系统 HIERARCHY
```

**使用场景**:
- 大型项目开发
- 复杂功能实现
- 多阶段任务处理

#### Competitive（竞争）模式
多个Agent竞争完成任务，系统自动选择最佳方案。

```bash
# 竞争模式示例
>>> /multi 设计一个高效的算法 COMPETITIVE
```

**使用场景**:
- 多方案对比
- 算法优化
- 架构设计选择

### 使用示例

#### 编程接口

```python
from agent_orchestrator import AgentOrchestrator
from agent_config import AgentConfigManager
from agents.agent_types import CollaborationMode

# 获取默认配置
config = AgentConfigManager.get_default_config()
orchestrator = AgentOrchestrator(config)

# 并行协作
result = orchestrator.process_request(
    "实现用户注册功能并生成测试",
    CollaborationMode.PARALLEL
)

# 查看结果
print(result["summary"])
print(result["detailed_report"])
```

#### CLI命令

```bash
# 启动多Agent任务
python query_interface.py
>>> /multi 实现用户认证系统，包括注册、登录、密码重置，生成测试和文档 PARALLEL

# 指定协作模式
>>> /multi 分析项目代码质量，生成审计报告 HIERARCHY

# 竞争模式获取最佳方案
>>> /multi 设计一个RESTful API架构 COMPETITIVE
```

### 自定义配置

```python
from agent_config import AgentConfigManager

# 自定义配置
config = AgentConfigManager.create_custom_config(
    model="qwen3.5:4b",
    max_parallel_tasks=8,
    default_mode="parallel"
)

# 最小化配置（只启用CodeAgent和TestAgent）
config = AgentConfigManager.get_minimal_config()
```

### 监控和状态查询

```python
# 获取编排器状态
status = orchestrator.get_status()
print(f"总Agent数: {status['total_agents']}")
print(f"MasterAgent状态: {status['master_status']}")

# 获取所有Agent信息
all_agents = orchestrator.get_all_agents()
for agent in all_agents:
    print(f"{agent.agent_id}: {agent.agent_type} - {agent.get_state()}")
```

### 测试覆盖率

多Agent系统包含完整的单元测试，总覆盖率达到95%：

```bash
# 运行多Agent系统测试
python -m pytest tests/multi_agent/ --cov=agents --cov=collaboration
```

---

## 8. 性能优化

### 索引优化

- 使用增量更新而非全量重建
- 调整分块大小和重叠
- 使用缓存加速重复查询

### 查询优化

- 使用TOP_K控制返回数量
- 设置相似度阈值过滤低质量结果
- 使用嵌入缓存减少重复计算

### 资源管理

- 合理设置MAX_ITERATIONS避免无限循环
- 使用虚拟环境隔离依赖
- 定期清理日志和临时文件

---

## 10. Web 界面

> 本节自 README 迁入（F10 P3-1）。

界面为「左侧栏导航 + 主区 + 右侧面板」，启动命令 `python launcher.py --web`（默认 http://127.0.0.1:7860）。

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

## 11. 三模式使用指南（自动路由 / RAG / Agent / 多 Agent）

> 本节自 README 迁入（F10 P3-1）。

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

## 12. 高级用法

> 本节自 README 迁入（F10 P3-1）。

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

详细安全说明请查看：[内容安全扫描器文档](../development/CONTENT_SECURITY.md)

---

## 13. 知识库智能优化（快照 / Skills / 内容安全）

> 本节自 README 迁入（F10 P3-1）。

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

内容安全扫描器的详细说明请查看：[内容安全扫描器文档](../development/CONTENT_SECURITY.md)

---

**上一篇**: [实战场景示例](03-scenarios.md) | **下一篇**: [桌面应用](05-desktop-app.md)
