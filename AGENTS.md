# AGENTS.md

本文件为在此仓库工作的 AI Agent 提供项目级指令。第一部分是**强制的协作规则**，第二部分是**项目速览与开发要求**，深入的架构 / 模块 / 规范 / 陷阱知识见 `docs/development/ai-assistant/`。

> 本文件面向"开发本项目的 AI 编码助手"。产品内置 ReAct / 多 Agent 的运行时提示位于 `prompts/`（见 `prompts/README.md`），两者职责不同，不要混放。

## Git 工作流规则（强制）

1. **禁止直接在 `master` 分支提交代码。** 任何代码改动都不得直接 commit 到 `master`。

2. **处理任何改动前，必须先征求用户确认是否需要新建分支。** 在开始修改文件之前，先询问用户：本次改动是否需要新建分支、以及分支名称。未获确认前不得自行创建分支。

3. **禁止自动创建分支。** 不得在未经用户明确同意的情况下执行 `git checkout -b` / `git switch -c` 等创建分支的操作。

4. **改动完成后，提示用户是否需要创建 PR。** 完成修改并提交后，主动询问用户是否需要创建 Pull Request，由用户决定。

5. **禁止自动创建 PR。** 不得在未经用户明确同意的情况下执行 `gh pr create` 或通过其他方式创建 Pull Request。

### 简要流程

```
收到改动需求
  → 询问：是否需要新建分支？分支名？  （等待用户确认）
  → 用户确认后再创建分支并进行改动
  → 完成并提交
  → 询问：是否需要创建 PR？           （等待用户确认）
  → 用户确认后再创建 PR
```

## CHANGELOG 更新规则（强制）

1. **每次实现完需求后，必须更新 `CHANGELOG.md` 的 `[Unreleased]` 区段。** 只要产生了用户可见的变更（新功能、修复、改进、发布流程等），在提交前就要把对应条目补入 `[Unreleased]`。

2. **按类别归类。** 使用 `新增` / `修复` / `改进` / `发布流程` 等小节，遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/) 格式；每条为一句话，聚焦用户可感知的效果。

3. **不要写入已发布的版本区段。** 未发布变更一律记入 `[Unreleased]`，发布时再由发布流程归档到具体版本号下。

4. **纯内部改动可酌情省略。** 若改动对用户完全不可见（如仅调整注释、测试内部结构），可不记录，但拿不准时优先记录。

## 项目速览

**Cerebro** —— 本地优先的"知识库 + Agent"助手：RAG 检索（LlamaIndex + ChromaDB + Ollama）、单 Agent（ReAct 工具调用）、多 Agent 协作（Master + Code / Test / Doc / Audit / RAG），提供 CLI、Gradio Web 与桌面托盘三种入口。

| 项 | 内容 |
|---|---|
| 语言 / 运行时 | Python 3.13，`venv/`；默认模型 `qwen3.5:4b`（Ollama） |
| 核心库 | llama-index、chromadb、requests、gradio、ddgs、trafilatura、rank_bm25、tree_sitter |
| 测试 | pytest（`pytest.ini`），覆盖率门禁 **80%**（`--cov-fail-under=80`，CI 同步） |
| 打包 | PyInstaller（`packaging/cerebro.spec`），`datas` 包含 `assets/`、`config/`、`prompts/` |
| CI | `.github/workflows/ci.yml`（测试 + 覆盖率）、`pr-build-vulnerability-gate.yml`（pip-audit）、`release.yml` |

### 目录职责

```
src/                    代码（顶层模块名导入：from config import ...）
src/web/                Web 入口：services/（业务门面，唯一接引擎）· formatters.py（纯格式化）· handlers/（页面处理器）· app.py（汇总 + 装配）· ui/（Gradio 接线）
src/cli/                CLI 入口：parser.py（命令路由）· help_text.py（帮助 / 教程文案）· handlers/（命令处理器 + COMMAND_HANDLERS）；query_interface.py 保留主循环与引擎耦合命令
prompts/                产品 Agent 的模型输入资产（PROJECT_RULES / Skills），随 App 打包
config/                 用户运行时配置（app_config.json）
data/                   默认文档入库目录（用户资料，gitignored）
index_storage/          向量索引（gitignored）
.cerebro/               App 运行时状态：快照 / 知识图谱 / 文件元数据（gitignored）
docs/tutorials          用户教程        docs/features   功能设计与实现记录
docs/development        开发者文档      docs/history    一次性报告归档
docs/development/ai-assistant/   AI 编码助手的项目知识（架构、模块、规范、测试、陷阱、调试）
tests/                  pytest（conftest 自动隔离 file_metadata / knowledge_graph 等真实数据）
```

### 常用命令

```bash
source venv/bin/activate
python -m pytest tests -q --no-cov              # 快速回归
python -m pytest tests -q                       # 带覆盖率（门禁 80%）
python -m pytest tests/test_xxx.py -q --no-cov  # 单文件
python src/query_interface.py                   # CLI
python src/web/app.py                           # Web UI
bash scripts/verify_deps.sh                     # 依赖校验
```

## 开发要求

### 开始任务前

- 代码改动前先读 `docs/development/ai-assistant/README.md`，按任务类型选读 ARCHITECTURE / MODULE_GUIDES / CODE_STANDARDS / TESTING_GUIDELINES / TRAP_AVOIDANCE。
- 定位实现以 `src/` 为准，文档可能滞后；发现文档与代码不一致时**以代码为准并顺手修正文档**。
- 多步任务先列计划并逐项跟踪。

### 需求分析（强制）

- **从用户体验与 UI 设计角度分析问题。** 收到需求或缺陷时，先回答：用户在什么场景、想达成什么、当前路径卡在哪；再给方案。方案要说明入口是否直观、步骤是否最少、结果是否结构化可读、危险操作是否有确认、失败是否有明确提示，而不是只描述"调用哪个函数"。
- **同时考虑 Web UI 与 CLI 两个入口。** 本项目的功能面在 `src/web/`（Gradio：`services/` 业务 → `handlers/` + `formatters.py` 呈现 → `ui/` 接线）与 `src/cli/`（`handlers/` 命令处理器 + `parser.py`）+ `src/query_interface.py`（主循环与引擎耦合命令）各有一份呈现层。任何需求分析必须逐一说明：该问题在两端是否都存在、方案在两端各如何落地（或明确说明某端不做及原因）。共用逻辑放共享层（`agent_tools` / `database_tools` / `git_integration` 等），禁止只修一端；改 CLI 行为须同步 `cli/help_text.py` 的 `print_help` / `TUTORIAL_TEXT`，改 Web 须同步页面文案。
- **优先修复共有缺陷，再做单端增强。** 排优先级时，两端共有的功能性 Bug > 影响主路径的体验问题 > 单端的锦上添花；需求文档按此分 P 级并给出可检查的验收。
- 需求文档模板见 `docs/features/f8-agent-modes-optimization/` 与 `docs/features/f9-web-tools-revamp/`（REQUIREMENTS §0 代码事实 + 分 P 级需求 + UI 规范 + 按 P 级分发的 PROMPT）。

### 依赖

- 新依赖须兼容 Python 3.13，使用最新稳定版；同步更新 `requirements.txt`、`requirements-build.txt`（打包用）与 `scripts/install_deps.sh` / `verify_deps.sh` / `check_prereqs.sh`（如涉及系统级前置）；PyInstaller 需要 `collect_all` 的库要在 `packaging/cerebro.spec` 中补充。
- 运行 `bash scripts/verify_deps.sh` 与 pip-audit 门禁（CI）确认。

### 测试

- 修改代码必须补充 / 更新测试；Bug 修复先写复现测试；新功能覆盖正常路径与边界。
- 全量 `python -m pytest tests -q` 通过且覆盖率不低于 80% 门禁；不得为凑覆盖率写无断言测试。
- 测试必须隔离真实数据：使用 `tmp_path`，不读写 `index_storage/`、`.cerebro/`、`~/.code_agent_sessions/`（见 `tests/conftest.py` 的 autouse fixture）。
- 不调用真实 Ollama / 网络：注入 `complete=` / `engine_factory=` / monkeypatch。

### 文档

- 用户可见变更：更新 `README.md` 相关章节（命令表、环境变量、功能说明）与 `CHANGELOG.md` `[Unreleased]`。
- 功能级需求：在 `docs/features/f{N}-{主题}/` 记录 REQUIREMENTS / 实现记录，并更新 `docs/features/README.md` 索引。
- 涉及提示文本：改 `prompts/`，并保持 `prompts/README.md` 中的层次说明准确。

### 禁止

- 直接修改 `index_storage/`、`.cerebro/` 内的数据文件；破坏快照 / 元数据 / 图谱的持久化格式而不提供迁移。
- 改变 `agent_tools.registry` 工具的注册名或参数名而不同步 `prompts/system/PROJECT_RULES.md`、`docs/development/ai-assistant/TOOL_USAGE.md` 与测试。
- 在系统提示 / Skill 中写入开发者规范（会挤占模型上下文并诱导 Agent 读项目文件）。
- 在回答或日志中泄露用户文档内容、命令历史、会话记录等隐私数据。

## 参考

- `docs/development/ai-assistant/README.md` —— 开发知识索引与选读指南
- `docs/development/ai-assistant/DEBUGGING_WORKFLOW.md` —— 调试流程
- `docs/features/README.md` —— 功能索引与状态；`docs/features/ROADMAP.md`
- `TESTING.md`、`docs/development/TEST_DESIGN.md`、`docs/development/CI_CD.md`
- `prompts/README.md` —— 产品 Agent 提示层次与自定义方式
