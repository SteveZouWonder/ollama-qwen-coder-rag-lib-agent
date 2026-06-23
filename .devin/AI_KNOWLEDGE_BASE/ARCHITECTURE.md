# 系统架构设计

## 🏗️ 整体架构

本项目采用**分层融合架构**，将RAG知识库、ReAct Agent、多Agent协作、智能推荐等功能有机整合。

### 架构层次

```
┌─────────────────────────────────────────────────────────────┐
│                    用户交互层 (CLI/桌面)                     │
│              统一查询接口 + 智能命令推荐                     │
└─────────────────────────────────────────────────────────────┘
                              │
         ┌──────────────────┴──────────────────┐
         │                                      │
┌────────▼────────┐                   ┌───────▼────────┐
│   RAG知识库层    │                   │   Agent执行层   │
│  LlamaIndex+ChromaDB  │                   │  ReAct+Tools     │
└────────────────┘                   └────────────────┘
         │                                      │
         └──────────────────┬──────────────────┘
                            │
                ┌───────────▼────────────┐
                │     协调编排层           │
                │ Multi-Agent Orchestrator │
                └───────────┬────────────┘
                            │
                ┌───────────▼────────────┐
                │     AI模型层             │
                │  Ollama qwen2.5-coder:7b  │
                └──────────────────────────┘
```

## 🔄 核心设计模式

### 1. 工具链模式 (Tool Chain Pattern)

**设计目的**: 为AI提供可调用的工具集合

**实现**:
- `ToolRegistry`: 工具注册中心
- `CommandSafetyChecker`: 安全检查器
- 每个工具都是独立的函数，注册到注册表

**工具分类**:
- 文件操作: `read_file`, `write_file`, `list_directory`
- 命令执行: `execute_command`
- 知识检索: `query_knowledge_base`, `add_to_knowledge_base`
- 网络搜索: `web_search`, `web_content_extract`
- 代码分析: `ast_search`, `code_quality_check`
- Git操作: `git_analyze`, `git_commit_gen`

**调用流程**:
```
用户任务 → ReAct推理 → 工具选择 → 安全检查 → 工具执行 → 结果处理
```

### 2. 多Agent协作模式 (Multi-Agent Collaboration)

**设计目的**: 复杂任务分解和并行执行

**组件**:
- `AgentOrchestrator`: 协调器
- `AgentRegistry`: 注册中心
- `MessageBus`: 消息总线
- `TaskDecomposer`: 任务分解器
- `TaskScheduler`: 任务调度器
- `ResultIntegrator`: 结果整合器

**协作模式**:
- **顺序协作**: 按顺序执行不同Agent任务
- **并行协作**: 同时执行多个Agent任务
- **审查协作**: 一个Agent生成，另一个审查
- **迭代协作**: 多次循环改进结果

**通信机制**:
```
Agent消息 → MessageBus → 目标Agent → 处理 → 结果返回
```

### 3. 状态管理模式 (State Management)

**设计目的**: 确保状态一致性和测试隔离

**全局状态**:
- `_rag_engine`: RAG引擎实例
- `react_engine`: ReAct引擎实例  
- `command_recommender`: 命令推荐实例

**状态重置策略**:
- pytest fixture: `rag_engine_reset`, `react_engine_reset`
- Agent工具状态重置函数
- 缓存清理机制

**测试隔离**:
- 每个测试独立状态
- 使用mock避免真实操作
- fixture作用域控制

### 4. 异步处理模式 (Async Processing)

**设计目的**: 提高性能和响应性

**异步组件**:
- 网络搜索: `web_search` 使用asyncio
- 文档加载: 大文件异步处理
- Agent执行: 支持异步工具调用

**设计原则**:
- 异步函数明确标注
- 正确的事件循环管理
- 超时处理
- 资源及时释放

### 5. 缓存策略模式 (Caching Strategy)

**设计目的**: 优化性能，减少重复计算

**缓存类型**:
- 向量缓存: LlamaIndex embedding缓存
- 搜索缓存: 网络搜索结果缓存
- OCR缓存: 图片识别结果缓存

**缓存实现**:
- 文件系统缓存
- 内存缓存
- TTL过期机制
- 缓存失效策略

## 📦 模块依赖关系

### 依赖层次图

```
query_interface (入口层)
    ├─→ rag_engine (知识库层)
│       ├─→ llama_index
│       └─→ chromadb
├─→ react_engine (Agent层)
│       ├─→ agent_tools (工具链)
│       ├─→ agents (Agent实现)
│       └─→ agent_orchestrator (多Agent)
├─→ command_recommender (推荐系统)
├─→ web_search (网络搜索)
├─→ session_manager (会话管理)
└─→ knowledge_snapshot (快照管理)
```

### 关键依赖

**rag_engine依赖**:
- 必需: llama-index, chromadb
- 可选: 无

**react_engine依赖**:
- 必需: agent_tools, agents
- 可选: agent_orchestrator (多Agent)

**agent_tools依赖**:
- 必需: rag_engine (知识库工具)
- 可选: web_search (网络搜索)

## 🎨 接口设计原则

### 1. 统一入口接口
`query_interface.py` 提供统一的CLI入口，所有功能通过命令分发

### 2. 配置化接口
`config.py` 集中管理所有配置，支持环境变量覆盖

### 3. 工具注册接口
`agent_tools.py` 通过ToolRegistry注册工具，动态发现

### 4. 状态注入接口
通过set_rag_engine等函数注入全局状态，便于测试

### 5. 回调接口
进度回调机制，支持进度显示和用户交互

## 🔐 安全架构

### 命令安全
- `CommandSafetyChecker` 危险命令检测
- 用户确认机制
- 只读命令白名单

### 内容安全  
- `content_security.py` 内容过滤
- 敏感信息保护
- 文件路径验证

### 数据安全
- 用户文档隐私保护
- 会话数据加密
- 快照数据访问控制

## 🚀 性能架构

### 缓存策略
- 多层次缓存: 内存 → 文件 → 网络缓存
- 智能缓存失效
- 缓存预热

### 资源管理
- 及时清理临时文件
- 内存使用监控
- 连接池管理
- 异步资源释放

### 批处理优化
- 文档批量加载
- 向量批量生成
- 搜索结果批量处理

## 📊 数据流架构

### RAG查询流程
```
用户提问 → 
  query_with_sources() → 
    embed_query() → 
      chromadb_query() → 
        result_ranking() → 
          llm_generate() → 
            format_response()
```

### Agent执行流程
```
用户任务 →
  react_engine.chat() →
    thought → 
      action(tool) → 
        observation → 
          thought_loop → 
            final_answer
```

### 网络搜索流程
```
关键词检测 →
  web_search() →
    search_engine.search() →
      result_processing() →
        cache_update() →
          integrate_to_answer()
```

## 🎯 扩展点设计

### 新工具扩展
在`agent_tools.py`中注册新工具函数

### 新Agent扩展  
在`agents/`目录创建新Agent类，注册到AgentRegistry

### 新推荐器扩展
在`command_recommender/`中添加新的推荐策略

### 新数据源扩展
在`document_loader.py`中添加新的文档加载器

## 🔧 部署架构

### 本地部署
- Python虚拟环境
- Ollama本地服务
- ChromaDB本地持久化

### 配置管理
- 环境变量配置
- 配置文件覆盖
- 默认值降级

### 日志架构
- 分层日志记录
- 日志轮转
- 错误日志分离
- 调试日志控制

这个架构设计确保了项目的可维护性、可扩展性和稳定性。当修改代码时，请理解这些设计原则和模式。