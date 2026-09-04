# 历史修复与实施报告

本目录存放一次性的修复报告与实施总结，记录"当时为什么这样改"。这些文档反映的是
**编写当日**的代码状态，其中的文件路径、行号、版本号（如 v4.x 为内部迭代代号，非发布
版本）可能已过时；当前行为以 [README.md](../../README.md)、[docs/tutorials/](../tutorials/)
与 [CHANGELOG.md](../../CHANGELOG.md) 为准。

功能级的设计与实现文档已按功能归档到 [docs/implemented-features/](../implemented-features/)，
不在此目录重复。

## 文档列表

| 文档 | 主题 | 日期 |
|---|---|---|
| [COMPREHENSIVE_FIX_REPORT.md](COMPREHENSIVE_FIX_REPORT.md) | 综合修复：Agent 对知识库持久化 / OCR 的认知修复（新增 `check_knowledge_status` 工具）、`/ask` 自动识别文件路径并入库、Python 3.13 与 OCR 引擎切换 | 2026-06 |
| [OCR_CONFIG_FIX_COMPLETE.md](OCR_CONFIG_FIX_COMPLETE.md) | OCR 配置六项修复：默认引擎改为 Tesseract、Homebrew 路径、`image_to_string`、缓存清理 | 2026-06 |
| [PROGRESS_DISPLAY_IMPLEMENTATION_REPORT.md](PROGRESS_DISPLAY_IMPLEMENTATION_REPORT.md) | RAG 查询四阶段进度回调（`progress_callback`）与 5 个显示配置项 | 2026-06 |
| [KNOWLEDGE_OPTIMIZATION_SUMMARY.md](KNOWLEDGE_OPTIMIZATION_SUMMARY.md) | 知识库 → Skills 转化、快照系统、内容安全扫描三项功能的首版实施总结（注：Skills 目标平台已由 Devin 改为 OpenCode + Claude；快照命令后续新增 `/snapshot-info|delete|prune` 与 `--apply`） | 2026-06 |
| [SYSTEM_PROMPT_OPTIMIZATION_REPORT.md](SYSTEM_PROMPT_OPTIMIZATION_REPORT.md) | 系统提示外置到 `.devin/SYSTEM_PROMPT.md`，新增 `read_system_prompt_from_file` 与 `read_system_prompt` 工具 | 2026-06-12 |
| [SYSTEM_PROMPT_V3_OPTIMIZATION_REPORT.md](SYSTEM_PROMPT_V3_OPTIMIZATION_REPORT.md) | 系统提示 V3：补多 Agent 说明、新工具描述、OCR 格式（F8 P1-1 将重做系统提示分层，此文为背景） | 2026-06-15 |

## 已清理

以下报告因内容已被合并、与 `implemented-features/` 重复、或仅为文档搬运记录而删除
（Git 历史可查）：`AGENT_FIX_SUMMARY`、`IMAGE_HANDLING_FIX`（并入 COMPREHENSIVE_FIX_REPORT）、
`COMMAND_RECOMMENDER_IMPLEMENTATION_SUMMARY`（见 `f4-command-recommender/IMPLEMENTATION_SUMMARY.md`）、
`WARNING_FIX`（内容见 `tutorials/06-troubleshooting.md`）、`DOCUMENTATION_REORG_SUMMARY`、
`DOCUMENTATION_UPDATE_REPORT`、`TUTORIAL_RESTRUCTURE_SUMMARY`。
