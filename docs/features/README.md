# 功能设计与实现记录

每个功能一个目录 `f{编号}-{主题}/`，目录内 `README.md` 记录**当前状态**（待实现 / 已实现）与
实现记录（与原设计的差异）。设计文档随功能同目录存放，实现前后不搬家。
整体进度见 [ROADMAP.md](ROADMAP.md)。

## 待实现

| 编号 | 功能 | 状态 | 目录 |
|---|---|---|---|
| F8 | 三种对话模式优化（RAG / 单 Agent / 多 Agent） | 📋 需求已定稿，分支 `feat/agent-modes-optimization` | [f8-agent-modes-optimization/](f8-agent-modes-optimization/) |

## 已实现

| 编号 | 功能 | 目录 |
|---|---|---|
| F1 | OCR 图片/图表提取 | [f1-ocr-extract/](f1-ocr-extract/) |
| F2 | 多 Agent 协作系统（骨架） | [f2-multiple-agent/](f2-multiple-agent/) — 真实化改造见 F8 P0 |
| F3 | 文件管理与会话管理 | [f3-file-session-management/](f3-file-session-management/) |
| F4 | 智能命令推荐 | [f4-command-recommender/](f4-command-recommender/) |
| F5 | 跨平台桌面应用打包与发布 | [f5-desktop-packaging/](f5-desktop-packaging/) |
| F6 | 系统能力增强（Agent 工具集） | [f6-capability-tools/](f6-capability-tools/) |
| F7 | Web 界面（Gradio） | [f7-web-ui/](f7-web-ui/) |

---

## 残留小项（无独立目录，按需排期）

已实现功能遗留的少量待办，每项工作量小，可单独立 issue 或在相关改动中顺带完成。

| 项 | 来源 | 说明 |
|---|---|---|
| 启动时检查新版本并提示 | F5 | 调 GitHub Releases API 比对当前 `APP_VERSION`，托盘 / Web「系统」页提示下载链接。**不做**应用内自更新（需正式签名与公证，成本不匹配） |
| macOS / Linux 开机自启 | F5 | `AppConfig.autostart` 配置项已存在但未生效；补 launchd plist / XDG `autostart/*.desktop`。Windows 已由 Inno Setup 可选任务覆盖 |
| `bootstrap.py` 补 Tesseract 检测提示 | F5 | 当前仅引导 Ollama；OCR 依赖缺失时给出安装提示（不自动安装） |
| Web「系统」页配置可编辑 | F7 | `TOP_K` / `SIMILARITY_CUTOFF` / `CHUNK_SIZE` 等写回 `.env`，重启生效；当前为只读概览 |
| 代码感知分块（可选） | F6（原 F5.2） | 代码文件入库时按函数 / 类边界切分，替代通用 `SentenceSplitter`。作为 F8 P2 的可选子项评估，不单独立项 |

## 已明确不做

| 项 | 原因 |
|---|---|
| 时间序列分析、学习路径推荐 / 复习计划 | 与"文档 + 代码助手"定位无关 |
| 独立代码语义搜索索引（faiss）、MySQL / PostgreSQL 支持、技术文档版本对比 | 与现有能力重叠或场景不足 |
| 应用内自动更新、macOS `.pkg`、deb / rpm、Docker 镜像、应用商店发布 | 现有 dmg / Inno / AppImage + GitHub Release 已满足分发；其余成本不匹配 |
| 插件系统、云同步、移动端 | 云同步违背本地优先；其余暂无需求 |

---

## 新增功能的流程

1. 新建 `f{编号}-{主题}/`（编号顺延），至少包含 `README.md`（状态 + 范围）与需求/设计文档；
   需求文档应含已核实的代码事实（带 `文件:行号`）、需求分项、验收标准。
2. 在本文件「待实现」表加一行。
3. 实现完成后：目录 `README.md` 状态改为 ✅ 并补「实现记录（与原设计差异）」表，本文件该行移到「已实现」，
   更新 `ROADMAP.md`、`CHANGELOG.md [Unreleased]`。
4. 决定不做的项写入「已明确不做」并注明原因，避免重复提出。

**最后更新**: 2026-09-04
