# 测试指南

pytest，配置在 `pytest.ini`；覆盖率门禁 **80%**（`--cov-fail-under=80`，CI `ci.yml` 与 `pr-build-vulnerability-gate.yml` 同步）。`TESTING.md` 与 `docs/development/TEST_DESIGN.md` 描述整体测试设计，本文聚焦"怎么写不踩坑"。

## 1. 运行

```bash
source venv/bin/activate
python -m pytest tests -q --no-cov              # 快速回归（约 30s）
python -m pytest tests -q                       # 带覆盖率门禁
python -m pytest tests/test_xxx.py -q --no-cov  # 单文件
python -m pytest tests -q --no-cov -x -p no:cacheprovider   # 首个失败即停
python -m pytest tests --collect-only -q | tail -1          # 检查收集错误
```

- 收集错误（ImportError 等）会让整套测试"看起来通过但少跑一个文件"，改动导出名后务必看 `--collect-only`。
- markers：`slow / integration / unit / ocr`（`--strict-markers`，未注册的 marker 报错）。

## 2. 目录

```
tests/
├── conftest.py                  全局 autouse fixture（见 §3）
├── test_*.py                    按模块一文件（约 50 个）
├── multi_agent/                 多 Agent（自有 conftest：block_ollama、fake_engine_factory、scripted_complete）
└── test_command_recommender/    命令推荐系统
```

覆盖率 omit：`tests/`、`venv/`、`src/web/ui/*`（Gradio 装配只做手动 / 集成验证）。

## 3. 全局 autouse fixture（`tests/conftest.py`）

| fixture | 作用 | 为什么 |
|---|---|---|
| `prevent_popups` | patch `subprocess.run / Popen` | 防止测试真的执行命令 / 弹窗 |
| `setup_settings_mock` | patch `rag_engine.Settings` | 避免 LlamaIndex 全局 Settings 类型检查 |
| `block_rerank_llm` | `rag_rerank._llm_complete` 抛 ConnectionError | rerank 会直连 Ollama |
| `block_intent_llm` | `intent_router._llm_complete` 抛 ConnectionError | 路由模糊时会直连 Ollama |
| `isolate_file_metadata` | `file_metadata._global_metadata_manager` → tmp | 否则写真实 `.cerebro/file_metadata/metadata.json` |
| `isolate_knowledge_graph` | `set_default_persist_path(tmp)` + 重建 `_graph_builder` / `_graph_query` | 否则写真实 `.cerebro/knowledge/graph.json` |
| `reset_module_state` | 重置 `query_interface._progress_state / rag_engine`、`agent_tools._rag_engine` | 模块级全局跨测试泄漏 |

`tests/multi_agent/conftest.py` 的 `block_ollama` 拦截 `requests.post`（子 Agent 委托真实 ReActEngine）。

**新增会持久化或联网的模块时，同一 PR 内在 conftest 加隔离 fixture。**

## 4. 隔离原则

- 文件系统：只用 `tmp_path`；不读写 `index_storage/`、`.cerebro/`、`~/.code_agent_sessions/`、`data/`、`prompts/`（读 `prompts/` 可以，写用 `AGENT_PROMPTS_DIR` 指到 tmp）。
- 网络 / 模型：不调用真实 Ollama；用注入或 monkeypatch。
- 环境变量：`monkeypatch.setenv / delenv`；`config.py` 的常量在 import 时已固化，需要改配置时 monkeypatch 使用点（如 `qi.Config.AUTO_ROUTE`）而不是 env。
- 时间：`health()` 等依赖 `datetime.now()` 的逻辑，直接改 `session.updated_at`。
- 单例：见 `CODE_STANDARDS.md` §6 表格，用 monkeypatch 替换而不是 `del`。

## 5. 注入手段（优先于 mock）

| 目标 | 手段 |
|---|---|
| LLM 补全 | `ConversationContext(complete=lambda p: "...")`、`classify_intent(complete=...)`、`TaskDecomposer(complete=...)`；multi_agent `scripted_complete` fixture |
| ReActEngine | `agent.config["engine_factory"]`（multi_agent `fake_engine_factory`，记录 kwargs、脚本化 Final Answer）；直接构造 `ReActEngine` 后 monkeypatch `_call_model` |
| WebService | `WebService(rag_factory=, react_factory=, orchestrator_factory=, session_manager_factory=, model_switcher_factory=)`；`build_handlers(MagicMock())` 单测 handler |
| 会话 | `SessionManager(str(tmp_path / "sessions"))`；CLI 单例 `monkeypatch.setattr(cc, "_context_singleton", ctx)` + `monkeypatch.setattr(cc, "get_conversation_context", lambda: ctx)` |
| RAG 管道 | `monkeypatch.setattr(rag_pipeline, "llm_direct_answer", ...)`、`simple_web_search`、`judge_kb_relevance`、`answer_question`；`mock_rag_engine` fixture |
| 代码分块 | `monkeypatch.setattr(code_chunker, "_load_pack", ...)`（避免依赖 tree-sitter-language-pack） |
| prompts | `monkeypatch.setenv("AGENT_PROMPTS_DIR", str(tmp))` 并写入 `system/PROJECT_RULES.md` / `skills/x/SKILL.md`；`CODE_AGENT_SKILLS=off` 关闭 Skills 层 |
| 路径 | `monkeypatch.setattr("runtime_paths.user_data_dir", lambda: tmp_path)`（`app_state_dir` 迁移测试） |

## 6. 断言什么

- 行为而非实现：断言返回 dict 字段、前缀标记（`[错误]` / `[知识库无相关内容]` / `⚠️ 未完成`）、事件 phase 序列、写入文件内容；不断言日志文案。
- 结构化输出改动要同时断言三端消费者：CLI 打印（`patch("query_interface.console")` 后收集 `print.call_args_list`）、Web `format_*` 输出、Agent Observation。
- Bug 修复先写**会失败**的复现测试，再改代码（会话隔离、单例钉死这类回归尤其如此）。
- 边界：空输入、超长（截断标注）、可选依赖缺失、取消 / 超时、旧数据格式（`from_dict` 未知键）。
- 不写无断言测试凑覆盖率；`pragma: no cover` 只用于真正无法单测的 UI 装配 / `main()`。

## 7. 常见失败模式

| 现象 | 原因 | 处理 |
|---|---|---|
| 本地过、CI 挂 | 依赖真实 Ollama / 网络 / 家目录文件 | 补注入或 conftest 拦截 |
| 改了导出名后"全绿" | 某测试文件收集失败 | 看 `--collect-only` 的 error 数 |
| 测试后 `.cerebro/` 多了文件 | 新持久化点未隔离 | 加 autouse fixture |
| `estimate_tokens(prompt) <= 1500` 失败 | 改了 `SYSTEM_PROMPT_TEMPLATE` 或未关 Skills | 测试里 `CODE_AGENT_SKILLS=off`；模板精简 |
| `ROLE_PROMPT` 超 200 token | 角色提示膨胀 | 把通用规则移到 `prompts/skills` |
| `ALLOWED_TOOLS` 精确集合断言失败 | 改了子 Agent 白名单 | 同步 `agent_config.py`、测试、`prompts/system/PROJECT_RULES.md` |
| Gradio 事件输出数不匹配 | handler 返回元组长度与 `outputs` 列表不一致 | `ui/*` 无单测，手动启动 `python src/web/app.py` 验证 |
