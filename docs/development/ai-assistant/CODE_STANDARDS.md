# 代码规范

约定以仓库现有代码为准（Python 3.13，`.flake8` / `.pylintrc` 在根目录）。本文只写本项目特有或容易踩坑的部分；通用 PEP 8 不再赘述。

## 1. 风格与组织

- PEP 8；行宽以 `.flake8` 为准；`from __future__ import annotations` 在新模块中优先使用。
- 命名：类 `PascalCase`，函数 / 变量 `snake_case`，模块级常量 `UPPER_CASE`，私有成员 `_prefix`。
- `src/` 内模块以**顶层名**互相导入（`from config import Config`，不是 `from src.config`）。需要兼容包内相对导入的地方用 `try: from runtime_paths import x / except ImportError: from src.runtime_paths import x`（现有模式）。
- 导入顺序：标准库 → 第三方 → 本地；重型依赖（llama_index、chromadb、gradio、trafilatura、tree_sitter…）放到**函数内惰性导入**，避免 CLI 启动变慢与测试收集时的可选依赖失败。
- 类型提示：公共函数写完整签名；返回 dict 的函数在 docstring 中列出字段。
- Docstring 用中文，首段一句话说职责；说明"为什么这样做"（历史 bug、约束）比复述代码更有价值。
- 每个模块顶部 docstring 说明职责与在分层中的位置（新模块必须有，`MODULE_GUIDES.md` 以它为准）。
- 入口层文件规模（F10 P2-2 起）：`web/app.py` ≤300 行；`web/services/*.py`、`web/handlers/*.py` 单文件 ≤800 行；`cli/handlers/*.py` ≤600 行。新增 Web 功能按页面落到对应 `services/<页>.py` mixin + `handlers/<页>.py` + `formatters.py`；新增 CLI 命令落到 `cli/handlers/<组>.py` 并登记 `COMMAND_HANDLERS`，不要再往 `query_interface.py` / 旧 `cli_handlers.py` shim 里加代码。拆包保留的兼容重导出（`web.app` → `formatters`、`cli_handlers` → `cli.handlers`）只为旧导入路径服务，新代码直接从实现模块导入；`monkeypatch` / `patch` 的目标必须是实现所在模块。

## 2. 配置与环境变量

- 所有可调参数经 `config.py` 从环境变量读取并给出默认值；模块内不要直接 `os.getenv` 业务参数（例外：`react_engine` / `prompt_assets` 的少量运行时旋钮，且都集中在模块顶部并有注释）。
- 新增环境变量：`config.py` 加常量 + 注释 → README「环境变量」表 → 如影响 Agent 行为则在 `prompts/README.md` 注明。
- 运行时可变项（模型、think）通过 `config.set_*()` 修改，不要各处赋值。

## 3. 路径

- 运行时状态一律 `runtime_paths.app_state_dir("...")`；资源 `resource_root()`；用户配置 `config_dir()`；家目录级文件 `home_file()`。禁止相对 cwd 拼路径（用户可 `/cd`）。
- 打包场景（`is_frozen()`）下不得写入 `resource_root()`。
- Agent 工具写文件必须过 `agent_tools.is_path_allowed()`。

## 4. 错误处理

- 能力层函数**返回带前缀的字符串或结构化 dict**，不向 ReAct / UI 抛裸异常：工具返回 `[错误] …`、`[提示] …`、`[成功] …`、`[知识库无相关内容]` 等前缀（完整清单见 `TOOL_USAGE.md`），上层按前缀分流。
- 捕获宽异常时写 `except Exception as exc:  # noqa: BLE001` 并记录日志或把原因带进返回值；不要静默 `pass`（现有少数 `pass` 都是"UI 已展示提示"的幂等路径）。
- 可选依赖缺失（OCR、cross-encoder、tree-sitter-language-pack、pylint…）：`ImportError` 处降级并说明，不让主流程崩。
- 取消 / 超时是正常路径：RAG 用 `PipelineCancelled`，Web 用 `threading.Event`，多 Agent 用 `execute_task_with_timeout`；新增长任务要接入 `should_stop` / 心跳。

## 5. 日志与输出

- 模块级 `logger = logging.getLogger(__name__)`；`info` 记录状态变化（迁移、加载索引、切模型），`warning` 记录降级，`error` 记录失败原因。
- 不在日志 / 回答中输出用户文档内容、命令历史、会话正文、绝对家目录路径以外的敏感信息。
- 面向用户的文案：CLI 用 `rich` console（emoji 前缀已成惯例），Web 返回 Markdown 字符串由 `format_*` 纯函数生成；业务层不要拼 UI 文案。

## 6. 状态与单例

现有进程级单例及其重置 / 隔离方式（测试必须用）：

| 单例 | 位置 | 隔离 |
|---|---|---|
| `_context_singleton` | `conversation_context` | `reset_conversation_context()` / monkeypatch |
| `_session_manager_singleton` | `session_manager` | 构造 `SessionManager(tmp)` 注入 |
| `_web_service_singleton` | `web/services/__init__` | `reset_web_service()` / 直接 `WebService(...factory)` |
| `_rag_engine` | `agent_tools` | `set_rag_engine(None)`（conftest `reset_module_state`） |
| `_global_metadata_manager` | `file_metadata` | conftest `isolate_file_metadata` |
| `_graph_builder` / `_DEFAULT_PERSIST_PATH_OVERRIDE` | `knowledge_graph.graph_builder` | conftest `isolate_knowledge_graph` |
| `react_engine` / `rag_engine` 模块全局 | `query_interface` | conftest `reset_module_state` |

- 新增单例要同时提供 `reset_*()` 与 conftest 隔离；能用依赖注入（工厂参数）就不要单例。
- "跟随当前会话"的 `ConversationContext`（`session_id=None`）不得把 `session_id` 写死（历史 bug）。

## 7. 提示文本（prompt）

- 产品 Agent 的可维护提示放 `prompts/`（英文）；`SYSTEM_PROMPT_TEMPLATE` 与 `ROLE_PROMPT` 留在代码里是因为与协议 / token 预算测试强耦合，改动需跑 `tests/test_react_engine_prompt_layers.py` 与 `tests/multi_agent/test_specialized_agents.py`（builtin ≤1500 token，ROLE_PROMPT ≤200 token）。
- 工具名 / 参数名以 `registry.register` 为唯一来源；`PROJECT_RULES.md` 的参数名段有测试校验。
- 不要在系统提示里写开发者流程（读文档、跑测试、覆盖率），会挤占上下文并诱导 Agent 读项目文件。

## 8. 并发

- Web 流式：业务在后台线程跑，经 `queue.Queue` 推 `StreamEvent`，主线程 yield；取消用 `threading.Event`。不要在 handler 里直接跑长任务。
- 多 Agent PARALLEL / COMPETITIVE 用 `ThreadPoolExecutor`；共享的 `agent_tools._rag_engine` 只读。
- Ollama 单实例串行，`WebService.is_running()` 拒绝并发任务。

## 9. 依赖管理

- 新依赖：兼容 Python 3.13、最新稳定版、写版本约束；同步 `requirements.txt`（开发 / 运行）与 `requirements-build.txt`（打包，不含 pytest）；系统级前置（Tesseract 等）同步 `scripts/check_prereqs.sh` / `install_deps.sh` / `verify_deps.sh`。
- PyInstaller 动态导入多的库要在 `packaging/cerebro.spec` `collect_all` 列表加入（现有：chromadb、llama_index*、trafilatura、justext、gradio*、rank_bm25、tree_sitter*、plotly 等）。
- 合并前跑 `bash scripts/verify_deps.sh`；CI 的 pip-audit 门禁（`pr-build-vulnerability-gate.yml`）对 High/Critical 失败，不适用的 CVE 需在 workflow 中显式 ignore 并注明理由。

## 10. 提交与变更记录

- 提交信息：`type(scope): 摘要`（feat / fix / docs / refactor / test / chore），中文摘要可，正文列要点。
- 用户可见改动必须写 `CHANGELOG.md` `[Unreleased]`；分支 / PR 规则见根 `AGENTS.md`。
