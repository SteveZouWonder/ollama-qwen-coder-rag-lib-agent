# Web 界面（Gradio）设计方案

> 状态：✅ 已实现（v0.0.12 首版；后续重设计为「侧栏导航 + 主区 + 右侧面板」并支持多主题色，
> 实际结构见文末「实现记录」）
> 目标：为 Cerebro 增加一个基于 **Gradio** 的本地 Web 界面，作为可分发产品，
> 降低非技术用户的使用门槛，并可视化 Agent 执行过程。
> 关联需求：详见本文件"背景与动机"。

---

## 1. 背景与动机

### 1.1 现状

Cerebro 当前提供两种交互入口，且**均无 Web/HTTP 能力**：

| 入口 | 文件 | 特点 | 问题 |
|------|------|------|------|
| CLI 交互界面 | `src/query_interface.py` | 功能最全（几十个斜杠命令） | 学习门槛高，非技术用户难以使用 |
| 桌面托盘 GUI | `src/desktop_app.py` | pystray 系统托盘 | 本质只是启动 CLI 的壳，无真正图形交互 |

项目**没有任何 Web 框架、前端代码或 HTTP API**。但核心能力（`RAGEngine`、
`ReActEngine`、`AgentOrchestrator`）都是可独立调用的类，非常适合在其上叠加一层
Web UI。

### 1.2 为什么值得做

1. **降低使用门槛**：把几十个斜杠命令转化为可视化面板与表单，让非技术用户也能用。
2. **可视化 Agent 执行**：ReAct 的 Thought→Action→Observation 循环、多 Agent
   协作过程在终端里很难看清，Web 可视化收益最大。
3. **不违背隐私原则**：默认仅绑定 `127.0.0.1` 本地端口，数据不出本机，符合项目
   "100% 本地 / 隐私优先"的核心卖点。
4. **可分发**：Gradio 是纯 Python，可随现有 PyInstaller 打包流程一起分发，用户
   打开浏览器即用。

### 1.3 为什么选 Gradio

| 维度 | Gradio | Streamlit | FastAPI + 前端框架 |
|------|--------|-----------|--------------------|
| 语言 | 纯 Python | 纯 Python | Python + JS/TS |
| 上手速度 | 最快 | 快 | 慢 |
| 流式输出 | 原生支持（`yield`） | 较弱 | 需自行实现 SSE/WS |
| 聊天组件 | 内置 `gr.Chatbot` | 需拼装 | 需自行实现 |
| 文件上传 | 内置 | 内置 | 需自行实现 |
| 打包契合度 | 高（纯 Python） | 高 | 低（需构建前端） |

结论：**作为产品分发 + 纯 Python 团队**，Gradio 是投入产出比最高的选择。其原生的
`gr.Chatbot`、流式 `yield`、`gr.File` 上传能力与本项目需求高度契合。

---

## 2. 目标与非目标

### 2.1 目标（本方案范围）

- 提供一个可分发的本地 Web 界面，覆盖 P0/P1 核心功能。
- 复用现有核心类，**不重写业务逻辑**，Web 层只做编排与展示。
- 与现有 CLI / 桌面 GUI 并存，新增 `--web` 启动方式。

### 2.2 非目标（本方案不包含）

- 多用户认证 / 权限系统（默认单用户本地场景）。
- 云端部署 / 公网暴露（默认仅本地回环地址）。
- 替换或废弃现有 CLI（CLI 仍是功能最全的入口）。
- 重写核心引擎。

---

## 3. 总体架构

```
┌─────────────────────────────────────────────────────────┐
│                    浏览器 (localhost)                     │
└───────────────────────────┬─────────────────────────────┘
                            │ HTTP (127.0.0.1:7860)
┌───────────────────────────▼─────────────────────────────┐
│                   Gradio App (src/web/)                   │
│  ┌──────────┬──────────┬──────────┬──────────┬────────┐  │
│  │ 对话面板 │ 知识库   │ Agent    │ 图谱     │ 系统   │  │
│  │ (Chat)   │ 管理     │ 可视化   │ 视图     │ 状态   │  │
│  └────┬─────┴────┬─────┴────┬─────┴────┬─────┴───┬────┘  │
│       │          │          │          │         │       │
│  ┌────▼──────────▼──────────▼──────────▼─────────▼────┐  │
│  │            Web 服务层 / 适配器 (web/services.py)     │  │
│  │  - 单例管理引擎实例   - 回调 → Gradio 流式转换       │  │
│  │  - 会话状态隔离       - 错误处理与降级               │  │
│  └────┬──────────┬──────────┬──────────┬─────────┬────┘  │
└───────┼──────────┼──────────┼──────────┼─────────┼───────┘
        │          │          │          │         │
   ┌────▼───┐ ┌────▼────┐ ┌───▼────┐ ┌───▼────┐ ┌──▼─────┐
   │RAGEngine│ │ReActEng.│ │Orchestr│ │GraphQry│ │Session │
   │         │ │         │ │ ator   │ │        │ │Manager │
   └─────────┘ └─────────┘ └────────┘ └────────┘ └────────┘
                  (现有核心模块，直接复用)
```

**分层原则**：
- **UI 层**（`web/tabs/*.py`）：只负责 Gradio 组件布局与事件绑定。
- **服务层**（`web/services.py`）：持有引擎单例、把引擎回调转成 Gradio 可消费的
  流式输出、处理错误与降级。**这是唯一与核心引擎交互的层**，UI 层不直接 import
  引擎。
- **核心层**（现有 `src/`）：不改动业务逻辑。

---

## 4. 功能设计（按优先级）

### P0 — 核心必备

#### 4.1 对话式问答面板（Chat Tab）

统一入口，支持三种模式切换：**RAG 检索 / 单 Agent / 多 Agent 协作**。

- 组件：`gr.Chatbot` + `gr.Textbox` 输入框 + 模式 `gr.Radio` + "停止"按钮。
- **RAG 模式**：调用 `RAGEngine.query_with_sources(question, progress_callback)`。
  - 用 `progress_callback` 的 `phase`（embedding/retrieving/scoring/generating）驱动
    进度提示。
  - 返回结果的 `answer` 显示在对话中，`sources` 在下方"来源引用"区展开。
- **单 Agent 模式**：调用 `ReActEngine(on_step=..., on_confirm=...).chat(user_input)`。
  - `on_step` 回调实时把 Thought/Action/Observation 渲染到"执行过程"区（见 4.5）。
- **多 Agent 模式**：调用
  `AgentOrchestrator.process_request(request, mode)`，`mode` 由下拉选择
  （HIERARCHY / PARALLEL / SEQUENTIAL / COMPETITIVE）。

> 依赖顺序：初始化时必须先 `agent_tools.set_rag_engine(rag_engine)`，Agent 才能
> 使用知识库工具。

#### 4.2 来源引用展示（Sources）

- RAG 回答下方以 `gr.Accordion` / `gr.Dataframe` 展示 `sources` 列表。
- 每条显示：`file`（来源文件）、`score`（相似度）、`content`（片段，已截断 500 字）、
  `path`（可用于"打开原文"）。
- 数据直接来自 `query_with_sources()` 返回的 `sources[{content, score, file, path}]`。

#### 4.3 知识库管理面板（Knowledge Tab）

- **上传**：`gr.File`（多文件，`file_count="multiple"`），支持格式来自
  `DocumentLoader.READERS`（pdf/md/txt/py/js/ts/java/cpp/c/go/rs/html/json/yaml/yml/xml）
  与 `IMAGE_TYPES`（png/jpg/jpeg/gif/bmp/tiff/tif，OCR）。
  - 上传后调用 `load_documents(path, file_types)` → `RAGEngine.add_documents(docs, file_paths)`。
  - 入库成功后自动派生知识图谱（现有逻辑，无需额外操作）。
- **统计**：调用 `RAGEngine.get_stats()`，展示 `total_documents`、`llm_model`、
  `embed_model`、`chunk_size`、`chunk_overlap`、`top_k`。
  > 注意：使用键 `total_documents`（不是 `total_chunks`）。
- **重建索引**：调用 `build_knowledge_base(data_path, file_types)`。
- **清空**：调用 `RAGEngine.clear_index()`（需二次确认）。

#### 4.4 流式输出

- 所有 LLM 回答用 Gradio 的生成器 `yield` 逐段返回，提升响应感知。
- RAG 检索阶段用 `progress_callback` 更新进度文本；生成阶段流式追加答案。
- ReAct 的 `on_step` 回调（含每 0.5s 的 thinking 动画）转成 `yield` 更新"执行过程"区。

### P1 — 高价值

#### 4.5 Agent 执行过程可视化

- 单 Agent：用 `ReActEngine(on_step=cb)` 的回调，把 `step_log` 中的
  `{thought, tool, input, observation}` 逐步渲染为时间线 / 折叠卡片。
- 危险命令确认：`on_confirm(dict) -> bool` 回调映射到 Gradio 的确认交互
  （`gr.Button` 二次确认或 `gr.Modal`）。
- "停止"按钮调用 `ReActEngine.stop()`。
- 多 Agent：`process_request` 无逐步回调，用 `AgentOrchestrator.get_status()`
  轮询展示各 Agent 状态；结束后展示整合结果（`success/results/summary`）。

#### 4.6 会话管理面板（Sessions Tab）

- 统一通过单例 `get_session_manager()` 获取管理器。
- 功能映射：
  - 新建 → `create_session(title, tags)`
  - 列表 → `list_sessions(status, tags)`
  - 切换 → `switch_session(session_id)`
  - 当前 → `get_current_session()`
  - 搜索 → `search_sessions(query)`
  - 归档/删除 → `archive_session` / `delete_session`
  - 统计 → `get_stats()`
- **多用户/多标签页隔离**：见"5. 关键技术难点"。

#### 4.7 知识图谱可视化（Graph Tab）

- 结构化查询：`get_graph_query()` 的 `query_entity / query_by_type /
  query_relations / query_neighbors / query_path / query_similar`，返回
  `QueryResult.to_dict()`（`entities/relations/confidence/explanation`），用
  `gr.Dataframe` 展示。
- 图形可视化：直接取底层 `get_graph_builder().graph`（`networkx.DiGraph`），用
  **pyvis** 生成交互式 HTML，嵌入 `gr.HTML`。
- 概览：`get_graph_summary()`（节点/边数、实体类型、关系类型分布）。

### P2 — 增值（后续迭代）

- **工具/命令面板**：Web 搜索、代码 AST 分析、代码质量检查、Git 分析、数据库查询等
  以表单化入口呈现（对应现有 `agent_tools` 注册的工具）。
- **系统状态面板**：Ollama 模型状态、索引统计、OCR 缓存（复用 `desktop_app.py` 的
  `StatusMonitor` / `OllamaWarmer` 思路）。
- **配置管理**：可视化调整 `LLM_MODEL`、`TOP_K`、`SIMILARITY_CUTOFF`、`CHUNK_SIZE`
  等（写回 Config / 环境变量）。

---

## 5. 关键技术难点与对策

### 5.1 引擎回调 → Gradio 流式输出

核心引擎用**回调**（`progress_callback` / `on_step` / `on_confirm`）暴露进度，
Gradio 用**生成器 `yield`** 驱动流式 UI。二者需桥接。

**对策**：在服务层用线程 + 队列（`queue.Queue`）把回调事件转成可迭代流：
- 引擎在工作线程运行，回调把事件 `put` 进队列。
- Gradio 事件函数是一个生成器，`get` 队列事件并 `yield` 给 UI，直到收到结束标记。

```python
# web/services.py 伪代码
def rag_query_stream(question):
    q = queue.Queue()
    def cb(evt): q.put(("progress", evt))
    def work():
        result = rag_engine.query_with_sources(question, progress_callback=cb)
        q.put(("done", result))
    threading.Thread(target=work, daemon=True).start()
    while True:
        kind, payload = q.get()
        if kind == "done":
            yield render_answer(payload); return
        yield render_progress(payload)
```

### 5.2 会话/状态隔离

Gradio 默认单进程多会话共享全局变量。`SessionManager` 的 "current session" 指针
是进程级单例，多标签页会互相干扰。

**对策**：
- 默认定位为**单用户本地场景**，接受进程级单例。
- 如需团队内网共享（多用户），用 Gradio 的 `gr.State` 为每个浏览器会话保存
  `session_id`，服务层按 `session_id` 显式操作，不依赖全局 current 指针。

### 5.3 引擎实例化成本与预热

`RAGEngine` 构造即连接 Ollama / ChromaDB；`AgentOrchestrator` 会创建 5 个 Agent，
较重。

**对策**：
- 服务层持有**单例**，应用启动时初始化一次并 `load_index()`。
- 复用现有 `OllamaWarmer` 思路，启动时预热模型。
- Ollama 未就绪时，复用 `bootstrap.ensure_ollama_ready` 做引导，UI 给出友好提示。

### 5.4 并发与线程安全

多 Agent 协作与 ReAct 使用后台线程，`ReActEngine.stop()` 基于 `threading.Event`。

**对策**：
- 每个请求使用独立的引擎调用上下文；`AgentOrchestrator` 用完 `shutdown()` 或
  `with` 管理。
- 长任务提供"停止"按钮，映射到 `stop()`。

### 5.5 危险命令确认

ReAct 的 `on_confirm` 是同步阻塞回调（返回 `bool`），但 Web 交互是异步的。

**对策**：用 `threading.Event` + 共享状态，`on_confirm` 阻塞等待用户在 UI 点击
确认/拒绝后再返回；同时给出超时默认拒绝，避免线程悬挂。

---

## 6. 目录结构与入口

新增代码集中在 `src/web/`，不侵入现有模块：

```
src/web/
├── __init__.py
├── app.py            # build_app() -> gr.Blocks，组装所有 Tab
├── services.py       # 服务层：引擎单例、回调→流式桥接、错误处理
├── state.py          # gr.State 会话隔离辅助
└── tabs/
    ├── chat.py       # P0 对话面板（三模式）
    ├── knowledge.py  # P0 知识库管理
    ├── sessions.py   # P1 会话管理
    ├── graph.py      # P1 知识图谱可视化
    └── system.py     # P2 系统状态 / 配置
```

**启动入口**（复用现有分流机制）：
- 在 `launcher.py` 增加 `--web` 参数：`python launcher.py --web` → 启动 Gradio。
- 或在 `src/` 下新增 `web_interface.py` 提供 `main()`，`launcher.py` 转调。
- 桌面托盘 `desktop_app.py` 可增加"打开 Web 界面"菜单项，`webbrowser.open` 到
  `http://127.0.0.1:7860`。

**默认配置**：`server_name="127.0.0.1"`、`server_port=7860`、`share=False`
（不生成公网链接，符合隐私原则）。

---

## 7. 依赖与打包

- 新增依赖：`gradio`（P0/P1），`pyvis`（P1 图谱可视化，可选）。
- 依赖文件：
  - `requirements.txt`（开发）新增 `gradio`、`pyvis`。
  - `requirements-build.txt`（打包运行时）按需新增（注意 Gradio 体积较大，评估打包
    产物大小）。
- PyInstaller：Gradio 有静态资源（前端），打包需在 `packaging/cerebro.spec` 中
  正确收集 `gradio` 的 `datas`（可用 `collect_data_files('gradio')`），需单独验证。
- Python 3.13 兼容性：选用支持 3.13 的 Gradio 版本，需实测。

> ⚠️ 打包体积与 3.13 兼容是主要风险点，建议在实现前先做一个"最小 Gradio 打包"
> 验证。

---

## 8. 分阶段实施计划

| 阶段 | 内容 | 交付物 |
|------|------|--------|
| M0 | 技术验证：Gradio 最小 app + PyInstaller 打包 + 3.13 兼容验证 | 可运行的空壳 + 打包报告 |
| M1（P0） | 服务层 + 对话面板（三模式）+ 来源展示 + 知识库上传/统计 + 流式 | 可用 MVP |
| M2（P1） | Agent 执行可视化 + 会话管理 + 图谱可视化 | 功能完整版 |
| M3（P2） | 工具面板 + 系统状态 + 配置管理 | 增强版 |
| M4 | 与 `launcher.py` / 托盘集成 + 文档 + 测试 | 可分发版本 |

---

## 9. 复用接口速查表

| 功能 | 复用接口 | 位置 |
|------|----------|------|
| RAG 检索 | `RAGEngine.query_with_sources(q, progress_callback)` | `src/rag_engine.py:457` |
| RAG 统计 | `RAGEngine.get_stats()`（键 `total_documents`） | `src/rag_engine.py:564` |
| 构建/重建索引 | `build_knowledge_base(data_path, file_types)` | `src/rag_engine.py:593` |
| 清空索引 | `RAGEngine.clear_index()` | `src/rag_engine.py:577` |
| 单 Agent 对话 | `ReActEngine(on_step, on_confirm).chat(input)` | `src/react_engine.py:214` |
| Agent 停止 | `ReActEngine.stop()` | `src/react_engine.py:208` |
| Agent 工具注入 | `agent_tools.set_rag_engine(engine)` | `src/agent_tools.py:14` |
| 多 Agent 协作 | `AgentOrchestrator(cfg).process_request(req, mode)` | `src/agent_orchestrator.py:126` |
| 协作配置 | `AgentConfigManager.get_default_config()` | `src/agent_config.py:17` |
| 会话管理 | `get_session_manager()` | `src/session_manager.py:420` |
| 文档加载 | `load_documents(path, file_types)` | `src/document_loader.py:495` |
| 图谱查询 | `get_graph_query().query_*()` → `QueryResult` | `src/knowledge_graph/graph_query.py:336` |
| 图谱原始图 | `get_graph_builder().graph`（networkx.DiGraph） | `src/knowledge_graph/graph_builder.py:508` |
| 配置常量 | `from config import TOP_K, LLM_MODEL, ...` | `src/config.py` |

---

## 10. 风险与开放问题

1. **打包体积**：Gradio 依赖较多，可能显著增大 PyInstaller 产物，需 M0 验证。
2. **Python 3.13 兼容**：需锁定兼容的 Gradio 版本。
3. **多用户隔离**：若未来要做内网共享，会话隔离需按 `gr.State` 重构（本方案已给出
   对策，但默认按单用户实现）。
4. **回调→流式桥接的健壮性**：线程 + 队列方案需覆盖异常、超时、中断路径。
5. **危险命令确认的异步化**：需仔细处理阻塞回调与 Web 异步之间的同步。

---

## 附：与现有交互方式的关系

Web 界面是**新增的第三种入口**，与 CLI、桌面托盘并存：
- CLI（`query_interface.py`）仍是功能最全、面向高级用户的入口。
- 桌面托盘（`desktop_app.py`）增加"打开 Web 界面"入口。
- Web（本方案）面向非技术用户与需要可视化的场景。


---

## 实现记录（与本设计的差异）

| 设计 | 实现 |
|---|---|
| 顶层 4 个 Tab | 左侧栏 5 个一级页面（对话 / 知识库 / 知识图谱 / 工具 / 系统），页内二级用 `gr.Tabs`；会话列表只在左侧栏一处 |
| `web/tabs/*.py` + `state.py` | `web/ui/{layout,chat,knowledge,graph,tools,system,common}.py`；每标签页会话绑定用 `gr.State`；主题在 `web/theme.py` |
| `gr.Dataframe` 展示来源 | 来源仍用 Markdown（便于引用片段）；文件 / 快照 / 摘要 / 模型 / 工具清单用 `gr.Dataframe` |
| 阻塞式 `on_confirm` 弹窗 | 服务层 `_ask_confirm` 推送 `confirm` 事件并挂起，对话页显示「允许 / 拒绝」审批卡片，`resolve_confirm` 唤醒；勾选"自动确认"等价 `--yes` |
| 多 Agent 模式选择 | 对话页多 Agent 模式下显示协作模式下拉（自动 / 层级 / 并行 / 顺序 / 竞争） |
| pyvis 图谱可视化 | 未实现；提供实体 / 类型 / 邻居 / 路径 / 相似五种查询与概览 |
| 系统状态面板 | 「系统」页：模型热切换与思考模式、运行环境配置概览、工作目录、工具清单、帮助 |
| 主题 | 6 套主题色运行时切换：为每套主题覆写 Gradio 全部依赖主色的语义变量（挂在 `body[data-cb-theme]`），localStorage 持久化，`<head>` 脚本提前应用避免闪烁 |
| 打包 | `packaging/cerebro.spec` 对 gradio / gradio_client `collect_all`，`requirements-build.txt` 加入 gradio |
