# AI 编码助手项目知识（开发者向）

本目录面向**在此仓库写代码的 AI 编码助手与人类开发者**：架构、模块、规范、测试、陷阱、调试流程。它不会被注入到产品内置 Agent 的系统提示中——产品 Agent 的运行时提示位于 `prompts/`（见 `prompts/README.md`）。仓库级强制协作规则（Git / CHANGELOG）见根目录 `AGENTS.md`。

> 所有文档以 `src/` 代码为准；发现不一致时以代码为准并顺手修正文档。

## 文件一览

| 文件 | 回答什么问题 | 何时读 |
|---|---|---|
| [ARCHITECTURE.md](ARCHITECTURE.md) | 三种入口、四种模式如何组合；数据流；分层与依赖方向；运行时路径 | 任何跨模块改动前 |
| [MODULE_GUIDES.md](MODULE_GUIDES.md) | 每个模块 / 子包的职责、关键函数、扩展点 | 定位实现、改某个模块前 |
| [CODE_STANDARDS.md](CODE_STANDARDS.md) | 代码风格、错误处理、日志、路径、配置、依赖管理 | 写代码前 |
| [TESTING_GUIDELINES.md](TESTING_GUIDELINES.md) | 测试隔离、注入手段、conftest fixture、覆盖率门禁 80% | 写 / 改测试前 |
| [WORKFLOWS.md](WORKFLOWS.md) | 新功能 / Bug 修复 / 重构 / 提示文本改动的标准流程与检查清单 | 开始任务时 |
| [TOOL_USAGE.md](TOOL_USAGE.md) | `agent_tools.registry` 28 个工具的真实签名、返回协议、安全分级 | 改工具 / 提示 / 多 Agent 白名单时 |
| [TRAP_AVOIDANCE.md](TRAP_AVOIDANCE.md) | 从 CHANGELOG 修复记录提炼的项目特有陷阱 | 改路径 / 会话 / 提示 / 打包 / 测试时 |
| [DEBUGGING_WORKFLOW.md](DEBUGGING_WORKFLOW.md) | 从错误现象到修复 + 复现测试的调试流程 | 排查 Bug 时 |

## 按任务类型选读

| 任务 | 必读 | 选读 |
|---|---|---|
| 新功能 | ARCHITECTURE、WORKFLOWS、CODE_STANDARDS | 涉及模块的 MODULE_GUIDES 段落、TRAP_AVOIDANCE |
| Bug 修复 | DEBUGGING_WORKFLOW、TESTING_GUIDELINES | TRAP_AVOIDANCE 对应条目 |
| 改 Agent 工具 / 提示 | TOOL_USAGE、`prompts/README.md` | ARCHITECTURE「系统提示层次」 |
| 改会话 / 上下文 | MODULE_GUIDES「conversation_context」、TRAP_AVOIDANCE「会话」 | |
| 改 Web UI | MODULE_GUIDES「web/」、TRAP_AVOIDANCE「Gradio」 | |
| 打包 / 发布 | ARCHITECTURE「运行时路径」、TRAP_AVOIDANCE「PyInstaller」、`docs/development/CI_CD.md` | |
| 只改测试 | TESTING_GUIDELINES | |

## 相关文档

- 用户视角：`README.md`、`docs/tutorials/`
- 功能设计与实现记录：`docs/features/README.md`（F1–F8）、`docs/features/ROADMAP.md`
- 测试设计与 CI：`TESTING.md`、`docs/development/TEST_DESIGN.md`、`docs/development/CI_CD.md`
- 一次性报告归档：`docs/history/`

## 维护

- 代码改动影响本目录描述的事实（模块新增 / 移除、工具签名、环境变量、路径、门禁）时，同一 PR 内更新对应文档。
- 不在此写"强制阅读清单"或"违规后果"之类的口号；写事实、写为什么、写怎么做。
