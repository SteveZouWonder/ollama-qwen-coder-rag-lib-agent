# 未来功能设计

本目录只保留**尚未实现**的需求。功能完成后，设计文档迁移到
[`../implemented-features/`](../implemented-features/) 并补「实现记录」，本文件同步删减。

## 待实现

### F8: 三种对话模式优化（RAG / 单 Agent / 多 Agent）

**状态**: 📋 需求已定稿，待实现（2026-09-03） · 分支 `feat/agent-modes-optimization`

**文档**:
- [AGENT_MODES_OPTIMIZATION.md](AGENT_MODES_OPTIMIZATION.md) - 需求、已核实代码事实、验收标准、LLM 提示词草案
- [AGENT_MODES_OPTIMIZATION_PROMPT.md](AGENT_MODES_OPTIMIZATION_PROMPT.md) - 交给 Agent 的启动提示词

**范围**（按 P0 → P3 顺序）:
- **P0 多 Agent**：4 个硬编码桩 Agent 改为委托 ReActEngine 真实执行；LLM 任务分解 / 结果整合 / 竞争评审；真并行与超时；结构化来源；CLI `/multi`
- **P1 单 Agent**：系统提示分层（内置 ≤1.5K token + 项目附加）；协议容错重试；步数耗尽强制总结；重复调用检测；本轮上下文预算折叠；知识库工具对齐 RAG 编排；安全分级与写路径边界
- **P2 RAG**：逐片段 rerank（LLM 默认 / cross-encoder 可选）；复合问题分解与多跳；带编号引用的综合与思维链透出；BM25 hybrid 召回；失败回退提示
- **P3 路由**：自然语言输入的意图判定（规则 + LLM 兜底），CLI `/auto`、Web「自动」模式

---

## 残留小项（无独立设计文档，按需排期）

以下为已归档功能遗留的少量待办，每项工作量小，可单独立 issue 或在相关改动中顺带完成。

| 项 | 来源 | 说明 |
|---|---|---|
| 启动时检查新版本并提示 | F5 桌面打包 | 调 GitHub Releases API 比对当前 `APP_VERSION`，托盘 / Web「系统」页提示下载链接。**不做**应用内自更新（需正式签名与公证，成本不匹配） |
| macOS / Linux 开机自启 | F5 桌面打包 | `AppConfig.autostart` 配置项已存在但未生效；补 launchd plist / XDG `autostart/*.desktop`。Windows 已由 Inno Setup 可选任务覆盖 |
| `bootstrap.py` 补 Tesseract 检测提示 | F5 桌面打包 | 当前仅引导 Ollama；OCR 依赖缺失时给出安装提示（不自动安装） |
| Web「系统」页配置可编辑 | F7 Web UI | `TOP_K` / `SIMILARITY_CUTOFF` / `CHUNK_SIZE` 等写回 `.env`，重启生效；当前为只读概览 |
| 代码感知分块（可选） | F6 能力增强 F5.2 | 代码文件入库时按函数 / 类边界切分，替代通用 `SentenceSplitter`。作为 F8 P2 的可选子项评估，不单独立项 |

---

## 已归档（已实现）

| 编号 | 功能 | 目录 |
|---|---|---|
| F1 | OCR 图片/图表提取 | [f1-ocr-extrace/](../implemented-features/f1-ocr-extrace/) |
| F2 | 多 Agent 协作系统（骨架） | [f2-multiple-agent/](../implemented-features/f2-multiple-agent/) — 真实化改造见 F8 P0 |
| F3 | 文件管理与会话管理 | [f3-file-session-management/](../implemented-features/f3-file-session-management/) |
| F4 | 智能命令推荐 | [f4-command-recommender/](../implemented-features/f4-command-recommender/) |
| F5 | 跨平台桌面应用打包与发布 | [f5-desktop-packaging/](../implemented-features/f5-desktop-packaging/) |
| F6 | 系统能力增强（Agent 工具集） | [f6-capability-tools/](../implemented-features/f6-capability-tools/) |
| F7 | Web 界面（Gradio） | [f7-web-ui/](../implemented-features/f7-web-ui/) |

## 已明确不做

| 项 | 原因 |
|---|---|
| 时间序列分析、学习路径推荐 / 复习计划 | 与"文档 + 代码助手"定位无关 |
| 独立代码语义搜索索引（faiss）、MySQL / PostgreSQL 支持、技术文档版本对比 | 与现有能力重叠或场景不足 |
| 应用内自动更新、macOS `.pkg`、deb / rpm、Docker 镜像、应用商店发布 | 现有 dmg / Inno / AppImage + GitHub Release 已满足分发；其余成本不匹配 |
| 插件系统、云同步 | 云同步违背本地优先；插件系统暂无需求 |

---

## 贡献指南

新增需求时：

1. 在本目录新建 `F{编号}_{主题}.md`（或按 F8 的做法拆成"需求 + 启动提示词"两份），编号顺延。
2. 文档至少包含：背景与已核实的代码事实（带 `文件:行号`）、需求分项、验收标准。
3. 在本文件「待实现」区加一条目；完成后迁移到 `implemented-features/f{编号}-{主题}/`，补 README 与实现记录，并从「待实现」删除。

---

**最后更新**: 2026-09-04（归档 F5/F6/F7，收拢残留小项，明确不做项）
