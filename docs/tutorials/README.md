# 教程索引

> 主 [README](../../README.md) 只保留定位、快速开始、命令速查、环境变量表、模型选择要点与文档索引；
> 其余内容按主题分在下面九篇教程里（F10 P3-1 迁移，2026-09-09）。根目录 [TUTORIAL.md](../../TUTORIAL.md) 是同一索引的旧入口。

| # | 文档 | 内容（★ = 2026-09-09 自 README 迁入的章节） |
|---|---|---|
| 01 | [项目概述和系统要求](01-overview.md) | 核心功能、技术架构、适用场景、硬件 / 软件要求；★ 融合架构、使用场景、扩展方向、技术栈 |
| 02 | [安装和配置指南](02-installation.md) | Ollama / Python / 依赖 / OCR 安装、一键前置条件检查、`.env` 与桌面配置；★ 依赖清单分工与升级流程，[§OCR](02-installation.md#ocr) 含 Tesseract 三平台自动探测 |
| 03 | [实战场景示例](03-scenarios.md) | 14 个完整实战场景（学术、开发、OCR、多 Agent、文件与会话管理） |
| 04 | [详细功能说明](04-features.md) | RAG / Agent / 工具 / 会话 / 安全 / 文件与会话管理 / 多 Agent；★ [Web 界面](04-features.md#10-web-界面)、[三模式使用指南](04-features.md#11-三模式使用指南自动路由--rag--agent--多-agent)、[高级用法](04-features.md#12-高级用法)、[知识库智能优化](04-features.md#13-知识库智能优化快照--skills--内容安全) |
| 05 | [桌面应用使用指南](05-desktop-app.md) | 托盘应用安装、配置、命令行功能、日志、故障排除；★ [macOS 用户须知](05-desktop-app.md#macos-用户须知首次打开) |
| 06 | [故障排除指南](06-troubleshooting.md) | 依赖冲突、ChromaDB 遥测、urllib3 警告、调试技巧；★ [常见问题速查](06-troubleshooting.md#常见问题速查) |
| 07 | [最佳实践指南](07-best-practices.md) | 知识库管理、Agent 任务设计、安全、性能、工作流集成；★ [性能优化建议](07-best-practices.md#11-性能优化建议速查) |
| 08 | [配置参考](08-configuration.md) | ★ 全文：`config.py` 常量注释、接入 OpenAI 兼容后端、模型选择补充、OCR 配置、智能命令推荐 |
| 09 | [开发者指南](09-development.md) | ★ 全文：项目结构、Python 路径、核心模块 API 示例、测试与 RAG 检索基准 |

## 推荐阅读路径

- **初次使用**：01 → 02 → 03 → 04
- **开发者**：02 → 09 → 08 → [docs/development/ai-assistant/](../development/ai-assistant/README.md)、[AGENTS.md](../../AGENTS.md)
- **运维 / 桌面用户**：02 → 05 → 06

## 相关文档

- [文档中心](../README.md)：功能实现记录（`docs/features/`）、路线图、CI/CD、历史报告
- [TEST_DESIGN.md](../development/TEST_DESIGN.md)、[TESTING.md](../../TESTING.md)：测试设计与运行
- [CONTENT_SECURITY.md](../development/CONTENT_SECURITY.md)：内容安全扫描器
