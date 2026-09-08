# 项目路线图

> 本文件原为「本地应用化」的逐周开发计划（2026-06）。该计划已完成并归档为
> [F5 跨平台桌面应用打包与发布](f5-desktop-packaging/)，
> 这里改为按当前状态维护的精简路线图。原逐周任务清单见 Git 历史。

**当前版本**: v0.0.13（2026-07-20 发布；`[Unreleased]` 见 [CHANGELOG.md](../../CHANGELOG.md)）
**默认模型**: `qwen3.5:4b` + `nomic-embed-text`（单一模型架构，按模型规模自动推导 `num_ctx`）

---

## 已完成

| 领域 | 内容 | 文档 |
|---|---|---|
| 知识库 | 14+ 格式入库、OCR（PaddleOCR / Tesseract）、快照管理、文件删除、Skills 生成 | [F1](f1-ocr-extract/)、[F3](f3-file-session-management/) |
| 对话 | RAG 检索（hybrid 召回、逐片段 rerank、复合问题多跳、编号引用、联网回退）、单 Agent（ReAct，29 工具，危险命令拦截、协议容错、上下文预算）、多 Agent（真实 Agent 委托、LLM 分解/整合/评审、真并行）、入口自动路由、连续对话上下文记忆与滚动压缩、思考模式开关、模型热切换 | [F2](f2-multiple-agent/)、[F8](f8-agent-modes-optimization/)、CHANGELOG |
| 知识库（代码） | 代码文件按函数/类切分（tree-sitter 可选依赖），来源定位到 `文件 · 符号 · 行号`，入库进度与分块策略可见 | [F8 P4](f8-agent-modes-optimization/) |
| 回答可信度 | 抗过度顺从：检索-only 单次综合 + 前提核对 / 冲突并列 / 被质疑不改口条款、引用程序化校验（`[?]` 标记、被引用次数、状态行计数）、结构化警示 notices（CLI / Web / Agent 四端）、无依据路径先判断是否确知、质疑追问不吸收用户断言、网页正文注入扫描、30 例评测集与真实模型评测脚本、可选 `RAG_SELF_CHECK` 自校验与前提实体校验 | [F9](f9-anti-overcompliance/) |
| Agent 工具 | 网络搜索、AST 分析、代码质量、Git 分析/提交信息、知识图谱（Plotly 3D/2D）、SQLite 数据库 | [F6](f6-capability-tools/) |
| 入口 | CLI（几十个斜杠命令 + 智能命令推荐）、桌面托盘（状态监控 / 模型预热 / Ollama 引导）、Gradio Web UI（5 页、多主题、审批卡片） | [F4](f4-command-recommender/)、[F5](f5-desktop-packaging/)、[F7](f7-web-ui/) |
| 工具工作台 | Web「工具」页 AI 化（代码助手 / Git 仪表盘 + 一步提交 / NL→SQL / 工作区浏览与 NL→命令、结果流转、连接记忆与命令历史）、DB 当前连接下沉共享层（Web + CLI + Agent 同修）、CLI `/git-analyze` `/db-query` `/db-schema` rich 表格 | [F9](f9-web-tools-revamp/) |
| 发布 | GitHub Actions 打 tag 自动构建 dmg / Inno Setup exe / AppImage，自动 Release Notes 与 CHANGELOG 归档；CI 含 flake8 / pylint / bandit / pip-audit / pytest / codecov、PR 漏洞门禁 | [CI_CD.md](../development/CI_CD.md) |

---

## 进行中 / 待实现

| 优先级 | 内容 | 文档 |
|---|---|---|
| 高 | F10 P0：命令安全分级修正（token 级匹配、读路径边界、`AUTO_CONFIRM` 不放行 high）；依赖钉版本 + `requirements-dev.txt`、CI PR 触发与三平台矩阵、CHANGELOG 归档发版 v0.1.0 | [F10](f10-hardening/) |
| 中高 | F10 P1：真流式输出（Web token 事件 / CLI rich Live、可中断）；LLM 后端抽象层（Ollama / OpenAI 兼容，接入 vLLM / LM Studio）；RAG 评测集与基准脚本 | [F10](f10-hardening/) |
| 中 | F10 P2：BM25 持久化增量 + 混合检索关闭可见 + 并发锁与 Ollama 限流；入口层拆分（`web/services/`、`web/handlers/`、`cli/`，纯重构） | [F10](f10-hardening/) |
| 低 | F10 P3：Tesseract 跨平台探测与缺失提示（合并原残留小项）、README 瘦身 | [F10](f10-hardening/) |
| 低 | 残留小项：启动时新版本检查提示、macOS / Linux 自启动、Web 配置可编辑 | [features/README.md](README.md)「残留小项」 |

## 已明确不做

时间序列分析、学习路径推荐、独立代码语义索引、MySQL / PostgreSQL、应用内自动更新、
`.pkg` / deb / rpm / Docker、应用商店、插件系统、云同步、移动端。原因见
[features/README.md](README.md)「已明确不做」。

---

## 持续性工程目标

- 单元测试覆盖率 ≥ 80%（`./venv/bin/python -m pytest -q -n 4`），新逻辑必须有单测
- 每次用户可见变更更新 `CHANGELOG.md [Unreleased]`
- 隐私优先：核心功能 100% 本地，网络功能默认可关、仅绑定 `127.0.0.1`
- 资源可控：面向 8–16GB 内存桌面环境，避免引入重依赖

---

**最后更新**: 2026-09-08（F10 立项）
