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
# 切换到不同模型
export LLM_MODEL=llama3:8b
python query_interface.py --data ./data
```

---

## 7. 多Agent协作系统 ⭐ 新功能

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
    model="qwen2.5-coder:7b",
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

**上一篇**: [实战场景示例](03-scenarios.md) | **下一篇**: [桌面应用](05-desktop-app.md)