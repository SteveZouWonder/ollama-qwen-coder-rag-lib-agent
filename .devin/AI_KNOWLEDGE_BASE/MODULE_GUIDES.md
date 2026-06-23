# 模块详解

## 📚 核心模块详细说明

### RAG引擎模块 (`rag_engine.py`)

#### 职责
- 文档向量化存储
- 语义相似度搜索
- 智能结果排序
- 来源追溯

#### 关键类和方法
```python
class RAGEngine:
    def __init__(self, chunk_size=1024, chunk_overlap=200, top_k=5)
        """初始化RAG引擎"""
        
    def build_knowledge_base(self, documents: List[str], metadata: List[Dict])
        """构建知识库"""
        
    def query_with_sources(self, question: str, progress_callback=None) -> Dict
        """查询并返回来源信息"""
        
    def add_documents(self, documents: List[str], sources: List[str])
        """添加文档到知识库"""
        
    def query(self, question: str) -> str
        """简单查询，返回答案"""
```

#### 状态管理
- **存储**: ChromaDB持久化到 `index_storage/chroma_db`
- **状态**: `query_engine` 成员变量
- **重置**: 通过重新实例化或清空索引

#### 与其他模块交互
- **与Agent工具链**: 提供 `query_knowledge_base`, `add_to_knowledge_base` 工具
- **与知识快照**: 配合快照管理器保存和恢复状态
- **与OCR处理**: 接收OCR识别的文本内容

#### 常见问题
**问题**: 索引损坏
**解决**: 使用快照恢复或重新构建知识库

**问题**: 查询性能慢
**解决**: 调整 `top_k` 参数，使用缓存

**问题**: 内存占用高
**解决**: 调整 `chunk_size` 和 `chunk_overlap`

---

### Agent系统模块 (`agents/`, `agent_orchestrator.py`)

#### 职责
- 任务执行和智能推理
- 多Agent协作调度
- 工具调用和结果处理

#### 关键组件
```python
# Agent基类
class BaseAgent:
    def execute(self, task: str) -> AgentResult
        """执行任务"""
        
    def get_capabilities(self) -> List[str]
        """返回Agent能力"""

# 具体Agent
class CodeAgent(BaseAgent):
    """代码专家Agent"""
    
class RAGAgent(BaseAgent):
    """知识库专家Agent"""

# 协调器
class AgentOrchestrator:
    def process_request(self, request: str, mode="default") -> str
        """处理请求"""
```

#### 通信机制
- **MessageBus**: Agent间消息传递
- **AgentMessage**: 消息数据结构
- **支持**: 同步和异步通信

#### 协作模式
- **顺序协作**: CodeAgent → TestAgent → AuditAgent
- **并行协作**: CodeAgent 和 DocAgent 同时工作
- **审查协作**: CodeAgent 实现 → AuditAgent 审查
- **迭代协作**: CodeAgent → TestAgent → CodeAgent 修复

#### 常见问题
**问题**: Agent卡死
**解决**: 检查任务调度器，设置超时

**问题**: 结果丢失
**解决**: 检查结果整合器，确认回调机制

**问题**: 消息传递失败
**解决**: 检查MessageBus，确认消息格式

---

### 命令推荐系统模块 (`command_recommender/`)

#### 职责
- 智能命令建议
- 用户行为学习
- 上下文感知推荐

#### 关键组件
```python
class CommandRecommender:
    def get_recommendations(self) -> List[Recommendation]
        """获取推荐命令"""
        
    def record_command(self, command: str, args: str, result: str)
        """记录命令执行"""
        
    def record_error(self, error: str)
        """记录错误"""
        
    def update_rag_status(self, rag_available: bool, rag_empty: bool)
        """更新RAG状态"""
```

#### 策略类型
- **WorkflowAnalyzer**: 工作流分析
- **StateAnalyzer**: 状态感知
- **HistoryAnalyzer**: 历史分析
- **ContextManager**: 上下文管理

#### 存储和更新
- **存储**: `~/.code_agent_history.json` (历史)
- **存储**: `~/.code_agent_preferences.json` (偏好)
- **更新**: 每次命令执行后更新

#### 常见问题
**问题**: 推荐不准确
**解决**: 增加历史数据，调整权重参数

**问题**: 学习功能异常
**解决**: 检查偏好存储，验证JSON格式

**问题**: 性能问题
**解决**: 调整推荐算法复杂度

---

### 网络搜索模块 (`web_search/`)

#### 职责
- 实时网络信息获取
- 网页内容提取
- 搜索结果缓存

#### 关键组件
```python
class SearchEngine(ABC):
    async def search(self, query: str, max_results: int = 10) -> List[SearchResult]
        """执行搜索"""
        
    def get_source_name(self) -> str
        """获取搜索源名称"""
        
    def is_available(self) -> bool
        """检查是否可用"""

class DuckDuckGoSearchEngine(SearchEngine):
    """DuckDuckGo搜索引擎实现"""

class SearchEngineManager:
    """搜索引擎管理器"""
```

#### 缓存机制
- **位置**: `index_storage/search_cache/`
- **格式**: JSON文件
- **TTL**: 默认24小时
- **失效**: 手动清除或过期

#### 使用方式
```python
from web_search import get_search_engine_manager

manager = get_search_engine_manager()
results = manager.search("Python latest version", max_results=5)
```

#### 常见问题
**问题**: 搜索失败
**解决**: 检查网络连接，验证duckduckgo-search安装

**问题**: 结果相关性低
**解决**: 调整查询词，增加max_results

**问题**: 缓存过时
**解决**: 手动清除缓存或更新查询词

---

### 会话管理模块 (`session_manager.py`)

#### 职责
- 对话状态持久化
- 会话切换和恢复
- 历史压缩

#### 关键类
```python
class SessionManager:
    def create_session(self, title: str) -> str
        """创建新会话"""
        
    def list_sessions(self) -> List[Dict]
        """列出所有会话"""
        
    def switch_session(self, session_id: str)
        """切换到指定会话"""
        
    def compress_session(self, session_id: str)
        """压缩会话历史"""
```

#### 存储机制
- **位置**: `~/.code_agent_sessions/`
- **格式**: JSON文件
- **结构**: 每个会话一个文件

#### 使用方式
```python
from session_manager import SessionManager

manager = SessionManager()
session_id = manager.create_session("工作项目")
manager.switch_session(session_id)
```

#### 常见问题
**问题**: 会话文件损坏
**解决**: 备份机制，JSON格式验证

**问题**: 历史压缩失败
**解决**: 检查历史长度，调整压缩策略

---

### OCR处理模块 (`ocr_processor/`)

#### 职责
- 图片文字识别
- 扫描版PDF处理
- 智能缓存

#### 关键组件
```python
class BaseOCREngine:
    """OCR引擎基类"""
    
    def extract_text(self, image_path: str) -> str
        """提取文字"""
        
    def is_available(self) -> bool
        """检查是否可用"""

class PaddleOCREngine(BaseOCREngine):
    """PaddleOCR引擎（Python 3.13有兼容性问题）"""

class TesseractOCREngine(BaseOCREngine):
    """Tesseract OCR引擎（Python 3.13推荐）"""
```

#### 支持格式
- 图片: PNG, JPG, JPEG, GIF, BMP, TIFF
- 文档: 扫描版 PDF
- OCR引擎: PaddleOCR, Tesseract

#### 缓存机制
- **位置**: `index_storage/ocr_cache/`
- **键**: 文件路径的hash
- **格式**: 图片hash → 识别结果

#### 使用方式
```python
from ocr_processor import get_ocr_engine

engine = get_ocr_engine()
text = engine.extract_text("/path/to/image.png")
```

#### 常见问题
**问题**: PaddleOCR在Python 3.13上不工作
**解决**: 使用Tesseract OCR

**问题**: 识别率低
**解决**: 检查图片质量，预处理图片

**问题**: 内存占用高
**解决**: 启用缓存，及时清理临时文件

---

### Git集成模块 (`git_integration/`)

#### 职责
- Git历史分析
- 提交信息生成
- 变更追踪

#### 关键类
```python
class GitAnalyzer:
    def get_commit_history(self, max_count: int = 10) -> List[CommitInfo]
        """获取提交历史"""
        
    def get_status(self) -> Dict
        """获取当前状态"""
        
    def analyze_changes(self, commit_hash: str) -> List[ChangeInfo]
        """分析变更"""

class CommitMessageGenerator:
    def generate(self, changes: List[ChangeInfo]) -> str
        """生成提交信息"""
```

#### 实现方式
- **不使用gitpython**: 使用subprocess调用系统git命令
- **依赖**: 系统git命令
- **状态**: 无状态，每次调用独立执行

#### 使用方式
```python
from git_integration import get_git_analyzer

analyzer = get_git_analyzer(".")
commits = analyzer.get_commit_history(max_count=5)
```

#### 常见问题
**问题**: Git命令不可用
**解决**: 确保系统安装了git

**问题**: 分析缓慢
**解决**: 限制max_count，使用缓存

---

### 工具链模块 (`agent_tools.py`)

#### 职责
- 统一工具注册
- 工具调用
- 安全检查

#### 关键类
```python
class ToolRegistry:
    def register(self, name: str, func: Callable, description: str, params: Dict)
        """注册工具"""
        
    def execute(self, name: str, args: Dict, auto_confirm: bool = False) -> str
        """执行工具"""
        
    def get_descriptions(self) -> str
        """获取工具描述"""

class CommandSafetyChecker:
    def analyze(cls, command: str) -> Dict
        """分析命令安全性"""
```

#### 工具分类
- **文件操作**: `read_file`, `write_file`, `list_directory`
- **命令执行**: `execute_command`
- **知识检索**: `query_knowledge_base`, `add_to_knowledge_base`
- **网络搜索**: `web_search`, `web_content_extract`
- **代码分析**: `ast_search`, `code_quality_check`
- **Git操作**: `git_analyze`, `git_commit_gen`

#### 安全机制
- **危险命令检测**: 正则表达式匹配危险模式
- **用户确认**: 非安全命令需要用户确认
- **只读白名单**: 已知的只读命令

#### 使用方式
```python
from agent_tools import registry

# 注册工具
registry.register("my_tool", my_function, "描述", {"param": "参数说明"})

# 执行工具
result = registry.execute("my_tool", {"param": "value"})
```

#### 常见问题
**问题**: 工具注册失败
**解决**: 检查函数签名，验证参数类型

**问题**: 安全检查误报
**解决**: 调整危险模式，添加例外

---

### 查询接口模块 (`query_interface.py`)

#### 职责
- 统一CLI交互入口
- 命令解析和分发
- 进度显示
- 用户交互

#### 命令类型
- `/ask`: 知识库查询
- `/agent`: Agent任务
- `/multi-agent`: 多Agent协作
- `/file`: 文件操作
- `/exec`: 命令执行
- `/web-search`: 网络搜索
- `/snapshot-*`: 快照管理
- `/session-*`: 会话管理

#### 进度显示
- **Rich进度条**: 可视化进度
- **简单文本**: 终端兼容
- **可配置**: 通过Config.SHOW_PROGRESS控制

#### 使用方式
```python
from query_interface import main

# 启动CLI
main()
```

#### 常见问题
**问题**: 命令解析失败
**解决**: 检查命令格式，验证参数

**问题**: 进度显示异常
**解决**: 确认Rich库安装，检查进度配置

---

## 🔄 模块间交互

### 典型交互流程

#### 1. 知识库查询流程
```
用户 → query_interface → rag_engine → llama_index → chromadb → 返回结果
```

#### 2. Agent任务执行流程
```
用户 → query_interface → react_engine → agent_tools → 具体工具 → 返回结果
```

#### 3. 网络搜索集成
```
用户 → query_interface → agent_tools.web_search → web_search模块 → DuckDuckGo → 返回结果
```

#### 4. 多Agent协作
```
用户 → query_interface → agent_orchestrator → 分发到多个Agent → 结果整合 → 返回结果
```

## ⚠️ 模块使用注意事项

### RAG引擎
- 需要先初始化索引
- 大量文档分批添加
- 定期创建快照备份

### Agent系统
- 每次任务独立执行
- 避免Agent间的状态依赖
- 设置合理的超时

### 命令推荐
- 需要一定的历史积累
- 可以手动清除历史
- 权重参数可以调整

### 网络搜索
- 需要网络连接
- 结果有缓存
- 可以手动清除缓存

### 会话管理
- 会话数据可能很大
- 定期压缩历史
- 可以归档旧会话

### OCR处理
- 图片质量影响识别率
- 缓存可以加快速度
- Python 3.13推荐Tesseract

修改模块时，请先仔细阅读相关文档，理解模块的设计和交互方式。