# 文档中心

```
docs/
├── tutorials/     【用户】  安装、功能、场景、桌面应用、故障排除、最佳实践
├── features/      【功能】  每个功能一个目录：设计 + 实现记录 + 状态；索引与路线图
├── development/   【开发者】CI/CD、测试设计、内容安全扫描器、文档维护流程
├── history/       【归档】  一次性修复报告与实施总结（反映编写当日状态）
└── assets/                  README 演示 GIF 与生成脚本
```

## 📖 教程 (tutorials/)

| 篇 | 内容 |
|---|---|
| [01 项目概述和系统要求](tutorials/01-overview.md) | 定位、架构、硬件与软件要求 |
| [02 安装和配置指南](tutorials/02-installation.md) | Ollama 与模型、依赖安装、一键前置条件检查、环境变量 |
| [03 实战场景示例](tutorials/03-scenarios.md) | 14 个场景：学术、开发、OCR、多 Agent、文件与会话管理等 |
| [04 详细功能说明](tutorials/04-features.md) | RAG / Agent / 安全机制 / 文件与会话管理等 |
| [05 桌面应用使用指南](tutorials/05-desktop-app.md) | 托盘、模型预热、状态监控、打包版 |
| [06 故障排除指南](tutorials/06-troubleshooting.md) | 依赖冲突、ChromaDB、urllib3、OCR、性能 |
| [07 最佳实践指南](tutorials/07-best-practices.md) | 知识库组织、提问技巧、安全使用 |

导航页：[TUTORIAL.md](../TUTORIAL.md)

## 🎯 功能 (features/)

- [功能索引](features/README.md) - 待实现 / 已实现 / 残留小项 / 明确不做
- [路线图](features/ROADMAP.md) - 已完成领域、进行中、工程目标

| 编号 | 功能 | 状态 |
|---|---|---|
| [F1](features/f1-ocr-extract/) | OCR 图片/图表提取 | ✅ |
| [F2](features/f2-multiple-agent/) | 多 Agent 协作系统（骨架） | ✅ |
| [F3](features/f3-file-session-management/) | 文件管理与会话管理 | ✅ |
| [F4](features/f4-command-recommender/) | 智能命令推荐 | ✅ |
| [F5](features/f5-desktop-packaging/) | 跨平台桌面应用打包与发布 | ✅ |
| [F6](features/f6-capability-tools/) | 系统能力增强（Agent 工具集） | ✅ |
| [F7](features/f7-web-ui/) | Web 界面（Gradio） | ✅ |
| [F8](features/f8-agent-modes-optimization/) | 三种对话模式优化（RAG / 单 Agent / 多 Agent） | 📋 待实现 |

## 🔧 开发者 (development/)

- [CI_CD.md](development/CI_CD.md) - GitHub Actions：CI 检查、PR 门禁、打 tag 自动发布
- [TEST_DESIGN.md](development/TEST_DESIGN.md) - 测试 Mock 策略与可测性设计（初版，门禁现为 80%）
- [CONTENT_SECURITY.md](development/CONTENT_SECURITY.md) - 内容安全扫描器 `content_security.py` 的 API 与集成
- [DOCUMENTATION_WORKFLOW.md](development/DOCUMENTATION_WORKFLOW.md) - 代码变更后的文档更新与整理流程

## 📜 归档 (history/)

见 [history/README.md](history/README.md)。

## 快速导航

- **新用户** → [README.md](../README.md) → [02 安装](tutorials/02-installation.md)
- **遇到问题** → [06 故障排除](tutorials/06-troubleshooting.md)
- **想了解新功能** → [CHANGELOG.md](../CHANGELOG.md)、[04 功能说明](tutorials/04-features.md)
- **关注安全** → [04 · 安全机制](tutorials/04-features.md#5-安全机制)、[CONTENT_SECURITY.md](development/CONTENT_SECURITY.md)
- **参与开发** → [功能索引](features/README.md)、[CI/CD](development/CI_CD.md)、[文档流程](development/DOCUMENTATION_WORKFLOW.md)
