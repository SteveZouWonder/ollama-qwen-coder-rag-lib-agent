# prompts/ — 模型输入资产

本目录集中存放**所有喂给产品内置 Agent 的可维护文本**，与代码（`src/`）、用户运行时配置（`config/`）、运行时数据（`.cerebro/`）严格分离。随桌面应用打包分发（`packaging/cerebro.spec`），用户可在数据目录中覆盖或扩展。

```
prompts/
├── system/PROJECT_RULES.md      # 项目附加规范：产品事实、知识库工具语义、参数名、多 Agent 语境
└── skills/<name>/SKILL.md       # 通用行为 Skill：任务分流、证据规则、效率、安全、回答形态、角色纪律
```

## 系统提示的层次

`src/react_engine.py: build_system_prompt()` 运行时组装，**不落盘**：

| 层 | 来源 | 谁能看到 |
|---|---|---|
| 1. 内置模板 | `SYSTEM_PROMPT_TEMPLATE`（协议 / 格式 / 工具速查 / 安全规则） | 全部 |
| 2. `=== Skills ===` | `prompts/skills/*/SKILL.md`，按 `roles` 过滤 | 单 Agent + 所有多 Agent 子角色 |
| 3. `=== 项目附加规范 ===` | `prompts/system/PROJECT_RULES.md`（截断到 `SYSTEM_PROMPT_EXTRA_MAX_CHARS`，默认 4000） | 单 Agent（`CODE_AGENT_PROMPT_MODE=append`，默认）；子角色默认 `builtin` 不含 |
| 4. `=== 角色说明 ===` | 各子 Agent 的 `ROLE_PROMPT`（≤200 token，代码内） | 对应子角色 |

RAG 模式的综合 prompt、多 Agent 的分解 / 整合 prompt 独立于本目录（见 `src/rag_pipeline.py`、`src/collaboration/`）。

## 三层解析（`src/prompt_assets.py`）

按优先级从低到高，同名后者覆盖前者：

1. **内置只读**：`runtime_paths.resource_root()/prompts`（源码运行 = 仓库目录；打包后随 App 分发）
2. **用户可写**：`runtime_paths.user_data_dir()/prompts`（macOS 桌面版 `~/Library/Application Support/Cerebro/prompts/`；源码运行时与 1 相同）
3. **环境变量** `AGENT_PROMPTS_DIR`：`os.pathsep` 分隔的额外目录

## 编写 Skill

```markdown
---
name: my-skill                 # 缺省 = 目录名；同名覆盖低优先级层的同名 Skill
description: 一句话说明
roles: [code, test]            # 缺省 / all = 全部角色；可选值 agent, code, test, doc, audit
---
# 正文（Markdown，直接注入系统提示）
```

- 语言：与模型交互的文本统一**英文**（内置模板为中文，Qwen 系列混合无碍；回答语言跟随用户）。
- 长度：所有适用 Skill 拼接后受 `SKILL_MAX_CHARS`（默认 4000 字符）限制，超出截断并标注 `…(skills truncated)`；单个 Skill 建议 ≤ 3500 字符。
- 内容：写"如何做"，不写"是什么"；不要重复内置模板已有的协议 / 格式规则；工具名与参数名以 `src/agent_tools.py` 的注册名为准。
- 关闭：`CODE_AGENT_SKILLS=off`。

## 编写 PROJECT_RULES

- 只写**产品特有**、且用户任务中真正会用到的事实与约定；开发者规范请写到 `docs/development/ai-assistant/`，不要放进这里（会挤占模型上下文并诱导 Agent 去读项目文件）。
- 控制在 4000 字符内，超出部分不会被模型看到。

## 验证

```bash
python -c "import sys; sys.path.insert(0,'src'); import prompt_assets, json; print(json.dumps(prompt_assets.describe(), ensure_ascii=False, indent=2))"
python -m pytest tests/test_prompt_assets.py tests/test_project_rules.py tests/test_react_engine_prompt_layers.py -q
```
