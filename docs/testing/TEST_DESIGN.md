# 单元测试设计方案（目标覆盖率 ≥ 95%）

## 1. 覆盖率目标

| 模块 | 行数 | 目标覆盖率 | 策略 |
|------|------|-----------|------|
| `config.py` | 55 | **100%** | 环境变量分支全覆盖 |
| `chat_history.py` | 50 | **100%** | 文件IO + 截断逻辑 |
| `agent_tools.py` | 297 | **≥ 95%** | 安全分析器 + 文件工具 + Registry + RAG工具 |
| `document_loader.py` | 145 | **≥ 90%** | Mock 读取器 + 文件发现 |
| `rag_engine.py` | 274 | **≥ 90%** | Mock 外部依赖 + Agent 接口 |
| `react_engine.py` | 296 | **≥ 90%** | Mock HTTP + 解析逻辑 + 安全拦截 |
| `query_interface.py` | 719 | **≥ 85%** | 纯函数 `parse_command`/`classify_mode` + 渲染函数 |
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
└── test_query_interface_render.py # 渲染函数（Mock HAS_RICH）
```

---

## 4. 关键测试策略

### query_interface.py — 抽离纯函数后可达 85%+

重构后新增 `ParsedCommand` 类、`parse_command()`、`classify_mode()` 三个纯函数：
- `parse_command`：覆盖所有 20+ 命令分支 + 空输入 + 未知命令 + 自然语言
- `classify_mode`：覆盖所有 cmd_type × rag_engine_available 组合
- 渲染函数：`print_banner`, `print_help`, `print_tools`, `print_rag_sources`, `print_knowledge_stats` — Mock `HAS_RICH` 为 True/False 分别测试

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
  └── test_query_interface_render.py
```
