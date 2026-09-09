# 开发流程

仓库级强制规则（禁止直接提交 master、创建分支 / PR 前须用户确认、CHANGELOG 必写）见根 `AGENTS.md`，此处不重复。本文给出各类任务的标准步骤与检查清单。

## 0. 通用步骤

```
1. 明确需求 → 若为功能级，先在 docs/features/f{N}-{主题}/REQUIREMENTS.md 写需求
2. 读 ai-assistant/README.md 按任务类型选读文档；以 src/ 代码为准
3. 列计划（多步任务逐项跟踪）
4. 询问用户：是否新建分支 / 分支名 → 确认后创建
5. 实现（小步提交；每步可运行）
6. 测试：复现 / 新增 / 更新；全量 pytest 通过，覆盖率 ≥ 80%
7. 文档：README（命令表 / 环境变量 / 功能）、CHANGELOG [Unreleased]、docs/features 记录、ai-assistant 事实更新
8. 提交 → 询问用户是否创建 PR
```

## 1. 新功能

1. `docs/features/README.md` 分配编号，新建 `f{N}-{主题}/`：`REQUIREMENTS.md`（背景 / 目标 / 非目标 / 验收）；实现后补 `README.md`（状态 + 实现记录）。
2. 确定落点（参考 ARCHITECTURE §6 扩展点）。跨三端（CLI / Web / Agent）的能力先在编排层或能力层实现一份，再分别接线。
3. 配置项进 `config.py` + README 表；路径走 `runtime_paths`；提示文本进 `prompts/`。
4. 每个新持久化 / 联网点同步 conftest 隔离。
5. 测试覆盖正常路径 + 边界 + 三端消费者。
6. 更新 `MODULE_GUIDES.md`（新模块 / 新函数）、`ARCHITECTURE.md`（若改数据流）、`TOOL_USAGE.md`（若加工具）。

## 2. Bug 修复

1. 复现：写会失败的测试（见 `DEBUGGING_WORKFLOW.md`）。
2. 定位根因（不是症状）：单例 / 路径 / 截断 / 状态残留 / 事件字段是高频根因，先查 `TRAP_AVOIDANCE.md`。
3. 最小修复 + 相邻同类隐患顺手修（同一 PR 内说明）。
4. 若修复改变了持久化格式或默认路径，提供一次性迁移（参考 `runtime_paths._migrate_legacy_state`、`conversation_context.migrate_legacy_history`）。
5. CHANGELOG `修复` 小节：写现象 + 根因 + 现在的行为。
6. 若根因是一类模式，补一条到 `TRAP_AVOIDANCE.md`。

## 3. 重构

- 先有测试再动手；保持公共签名或提供兼容别名（如 `read_system_prompt_from_file = read_project_rules`、`cwd_data_dir`）。
- 移除公共名前 `grep -rn` 全仓库（含 tests、docs、prompts），一次改全。
- 大重组（目录迁移）用 `git mv` 保留历史；同步 `.gitignore`、打包 `datas`、文档路径引用、CHANGELOG `改进`。

## 4. 改 Agent 工具 / 提示 / 白名单

1. 工具：`agent_tools.py` `registry.register` 是唯一事实源。改名 / 改参数后同步：`prompts/system/PROJECT_RULES.md` 参数名段 → `TOOL_USAGE.md` → 子 Agent `ALLOWED_TOOLS` / `agent_config.py` → 测试（`test_agent_tools*.py`、`multi_agent/test_specialized_agents.py` 精确集合、`test_project_rules.py`）。
2. Skill：改 `prompts/skills/<name>/SKILL.md`；保持英文；总长 ≤ 4000 字符；跑 `tests/test_prompt_assets.py`、`tests/test_react_engine_prompt_layers.py`。
3. 项目规范：改 `prompts/system/PROJECT_RULES.md`（≤ 4000 字符，只写产品事实）；跑 `tests/test_project_rules.py`。
4. 内置模板 `SYSTEM_PROMPT_TEMPLATE` / `ROLE_PROMPT`：受 token 上限测试约束（builtin ≤1500、ROLE ≤200），能移到 Skills 的就移。
5. 手动冒烟：`python src/query_interface.py` 跑一条 `/agent` 与一条 `/multi`，看系统提示是否按预期分层（`prompt_assets.describe()` 可打印诊断）。

## 5. 改会话 / 上下文

- 三个消费者：CLI 单例（跟随当前会话）、Web 每请求绑定实例（`gr.State` session_id）、多 Agent `EphemeralContext`。改 `ConversationContext` 后三处都要验证。
- `session.metadata["context"]` 字段变更要兼容旧会话文件（`_meta()` 用 `setdefault`）。
- 新会话必须干净：只有已折叠摘要可被"携带"；跟随模式不钉死 `session_id`。
- 测试：`tests/test_conversation_context.py`、`tests/test_cli_handlers_context.py`、`tests/test_web_services.py`（会话段）、`tests/test_web_app.py`（`TestSessionHandlers`）。

## 6. 改 Web UI

- 业务进 `web/services/<页>.py` 对应 mixin，渲染进 `web/formatters.py` 的 `format_*`，处理器进 `web/handlers/<页>.py` 的 `build_<页>_handlers`（`app.build_handlers` 自动汇总），接线进 `ui/*.py`。handlers 与 `format_*` 有单测；`ui/*` 没有，改完必须 `python src/web/app.py` 手动验证事件链（尤其 outputs 元组长度）。
- 每标签页状态用 `gr.State`；不要用模块级变量存"当前会话"。
- 长任务走 `_bridge` 流式 + 取消；进度事件 phase 与 CLI 对齐。

## 7. 打包 / 发布

- 新资源目录 → `packaging/cerebro.spec` `datas`；动态导入库 → `collect_all`；打包依赖 → `requirements-build.txt`。
- 本地验证：`pyinstaller packaging/cerebro.spec --noconfirm` 后启动 `dist/` 产物，确认 `prompts/` 与 `default_config/` 被读到（`prompt_assets.describe()`）。
- 发布由 `release.yml` 按 tag 触发；CHANGELOG 归档用 `scripts/bump_changelog.py`（见 `docs/development/CI_CD.md`）。

## 8. 交付前检查清单

- [ ] 全量 `python -m pytest tests -q` 通过，覆盖率 ≥ 80%，`--collect-only` 无 error
- [ ] 无真实数据被写入（`git status` 不出现 `.cerebro/` / `index_storage/` 变化；conftest 隔离到位）
- [ ] 新增 / 修改的环境变量、命令、路径已进 README
- [ ] CHANGELOG `[Unreleased]` 已记录（新增 / 修复 / 改进）
- [ ] `docs/features` 记录（功能级）；`ai-assistant/*` 事实同步（模块 / 工具 / 陷阱）
- [ ] 提示文本改动跑过 prompt 相关测试并手动冒烟
- [ ] 依赖改动跑过 `bash scripts/verify_deps.sh`
- [ ] 已询问用户是否创建 PR
