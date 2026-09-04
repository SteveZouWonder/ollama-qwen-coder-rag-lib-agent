# 项目路线图

> 本文件原为「本地应用化」的逐周开发计划（2026-06）。该计划已完成并归档为
> [F5 跨平台桌面应用打包与发布](../implemented-features/f5-desktop-packaging/)，
> 这里改为按当前状态维护的精简路线图。原逐周任务清单见 Git 历史。

**当前版本**: v0.0.13（2026-07-20 发布；`[Unreleased]` 见 [CHANGELOG.md](../../CHANGELOG.md)）
**默认模型**: `qwen3.5:4b` + `nomic-embed-text`（单一模型架构，按模型规模自动推导 `num_ctx`）

---

## 已完成

| 领域 | 内容 | 文档 |
|---|---|---|
| 知识库 | 14+ 格式入库、OCR（PaddleOCR / Tesseract）、快照管理、文件删除、Skills 生成 | [F1](../implemented-features/f1-ocr-extrace/)、[F3](../implemented-features/f3-file-session-management/) |
| 对话 | RAG 检索（联网回退）、单 Agent（ReAct，29 工具，危险命令拦截）、多 Agent（骨架）、连续对话上下文记忆与滚动压缩、思考模式开关、模型热切换 | [F2](../implemented-features/f2-multiple-agent/)、CHANGELOG |
| Agent 工具 | 网络搜索、AST 分析、代码质量、Git 分析/提交信息、知识图谱（Plotly 3D/2D）、SQLite 数据库 | [F6](../implemented-features/f6-capability-tools/) |
| 入口 | CLI（几十个斜杠命令 + 智能命令推荐）、桌面托盘（状态监控 / 模型预热 / Ollama 引导）、Gradio Web UI（5 页、多主题、审批卡片） | [F4](../implemented-features/f4-command-recommender/)、[F5](../implemented-features/f5-desktop-packaging/)、[F7](../implemented-features/f7-web-ui/) |
| 发布 | GitHub Actions 打 tag 自动构建 dmg / Inno Setup exe / AppImage，自动 Release Notes 与 CHANGELOG 归档；CI 含 flake8 / pylint / bandit / pip-audit / pytest / codecov、PR 漏洞门禁 | [CI_CD.md](../CI_CD.md) |

---

## 进行中 / 待实现

| 优先级 | 内容 | 文档 |
|---|---|---|
| 高 | **F8 三种对话模式优化**：多 Agent 真实化（P0）→ 单 Agent 鲁棒性与上下文预算（P1）→ RAG rerank / 多跳 / 编号引用 / hybrid 召回（P2）→ 入口自动路由（P3） | [AGENT_MODES_OPTIMIZATION.md](../future-feature-design/AGENT_MODES_OPTIMIZATION.md) |
| 低 | 残留小项：启动时新版本检查提示、macOS / Linux 自启动、Tesseract 引导提示、Web 配置可编辑、代码感知分块 | [future-feature-design/README.md](../future-feature-design/README.md) |

## 已明确不做

时间序列分析、学习路径推荐、独立代码语义索引、MySQL / PostgreSQL、应用内自动更新、
`.pkg` / deb / rpm / Docker、应用商店、插件系统、云同步、移动端。原因见
[future-feature-design/README.md](../future-feature-design/README.md)「已明确不做」。

---

## 持续性工程目标

- 单元测试覆盖率 ≥ 80%（`./venv/bin/python -m pytest -q -n 4`），新逻辑必须有单测
- 每次用户可见变更更新 `CHANGELOG.md [Unreleased]`
- 隐私优先：核心功能 100% 本地，网络功能默认可关、仅绑定 `127.0.0.1`
- 资源可控：面向 8–16GB 内存桌面环境，避免引入重依赖

---

**最后更新**: 2026-09-04
