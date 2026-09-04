# 文档中心

本目录包含项目的详细文档资源。

## 📚 文档分类

### 📖 教程文档 (tutorials/) — 面向用户
- [项目概述和系统要求](tutorials/01-overview.md)
- [安装和配置指南](tutorials/02-installation.md)
- [实战场景示例](tutorials/03-scenarios.md)
- [详细功能说明](tutorials/04-features.md)
- [桌面应用使用指南](tutorials/05-desktop-app.md)
- [故障排除指南](tutorials/06-troubleshooting.md)
- [最佳实践指南](tutorials/07-best-practices.md)

### 📋 一般文档 (general/)
- [前置条件检查快速指南](general/QUICK_START_CHECK.md) - 一键验证环境
- [内容安全扫描器文档](general/SECURITY_DOCUMENTATION.md) - `content_security.py` 的 API 与集成方式
- [项目路线图](general/PROJECT_ROADMAP.md) - 已完成 / 待实现 / 不做

### 🎯 功能实现文档 (implemented-features/) — 按功能归档的设计与实现记录
- [F1 OCR提取功能](implemented-features/f1-ocr-extrace/) ✅
- [F2 多Agent系统（骨架）](implemented-features/f2-multiple-agent/) ✅
- [F3 文件管理和会话管理](implemented-features/f3-file-session-management/) ✅
- [F4 智能命令推荐系统](implemented-features/f4-command-recommender/) ✅
- [F5 跨平台桌面应用打包与发布](implemented-features/f5-desktop-packaging/) ✅
- [F6 系统能力增强（Agent 工具集）](implemented-features/f6-capability-tools/) ✅
- [F7 Web 界面（Gradio）](implemented-features/f7-web-ui/) ✅

### 🚀 未来特性设计 (future-feature-design/)
- [待实现需求索引与残留小项](future-feature-design/README.md)
- [F8 三种对话模式优化（RAG / 单 Agent / 多 Agent）](future-feature-design/AGENT_MODES_OPTIMIZATION.md) 📋 待实现

### 🧪 测试文档 (testing/)
- [测试设计文档](testing/TEST_DESIGN.md)

### 📜 历史文档 (history/)
一次性修复报告与实施总结，见 [history/README.md](history/README.md)（内容反映编写当日状态，可能过时）。

### 🔧 工程文档
- [CI/CD 与发布流程](CI_CD.md)
- [文档组织工作流](DOCUMENTATION_ORGANIZATION_WORKFLOW.md)

## 相关链接

- **项目主文档**: [README.md](../README.md)
- **教程导航**: [TUTORIAL.md](../TUTORIAL.md)
- **变更日志**: [CHANGELOG.md](../CHANGELOG.md)

## 📖 文档导航

如果您是：
- **新用户** → 先阅读 [README.md](../README.md) 了解项目概览
- **想要快速开始** → [安装和配置指南](tutorials/02-installation.md) + [前置条件检查](general/QUICK_START_CHECK.md)
- **遇到问题** → [故障排除指南](tutorials/06-troubleshooting.md)
- **想了解新功能** → [CHANGELOG.md](../CHANGELOG.md) 与 [详细功能说明](tutorials/04-features.md)
- **关注安全问题** → [内容安全扫描器文档](general/SECURITY_DOCUMENTATION.md)、[详细功能说明 · 安全机制](tutorials/04-features.md#5-安全机制)
- **查看实际应用** → [实战场景示例](tutorials/03-scenarios.md)
- **参与开发** → [功能实现文档](implemented-features/)、[未来特性设计](future-feature-design/README.md)、[CI/CD](CI_CD.md)
