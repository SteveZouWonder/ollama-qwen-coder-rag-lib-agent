# F7: Web 界面（Gradio）

## 功能概述

基于 Gradio 的本地 Web 界面（`python launcher.py --web`，默认 `127.0.0.1:7860`），
作为 CLI 与桌面托盘之外的第三种入口：左侧栏导航 5 个页面（对话 / 知识库 / 知识图谱 /
工具 / 系统），三种对话模式（RAG 检索 / 单 Agent / 多 Agent 协作），处理过程全程可见，
Agent 危险命令审批卡片，多主题色。

## 实施状态

**状态**: ✅ 已完成（v0.0.12 首版；后续重设计为侧栏布局并持续迭代）
**设计文档**: [DESIGN.md](DESIGN.md)（文末「实现记录」表列出了与设计的全部差异）

## 代码位置

```
src/web/
├── app.py          # format_* 纯函数、build_handlers、build_app / launch / main、build_graph_figure
├── services.py     # WebService：唯一接引擎处（RAG / ReAct / Orchestrator / 会话 / 知识库）
├── theme.py        # 6 套主题色
└── ui/             # layout / chat / knowledge / graph / tools / system / common（# pragma: no cover）
```

测试：`tests/test_web_app.py`、`test_web_services.py`、`test_web_kb_management.py`、`test_web_theme.py`。

## 原设计 P2 项的处置

| 项 | 结论 |
|---|---|
| 工具/命令面板 | ✅ 已实现（「工具」页：网络搜索 / 代码分析 / Git / 数据库 / Shell 与文件） |
| 系统状态面板 | ✅ 已实现（「系统」页：模型热切换与思考模式 / 运行环境 / 工具清单 / 帮助） |
| 配置管理（可视化修改 `TOP_K`、`SIMILARITY_CUTOFF`、`CHUNK_SIZE` 等并写回） | ⏳ 未实现，「系统」页目前为只读概览。已收入 [features/README.md](../README.md)「残留小项」 |

## 相关文档

- [DESIGN.md](DESIGN.md) - 设计方案与实现记录
- [F8 三种对话模式优化](../f8-agent-modes-optimization/REQUIREMENTS.md) - F8 对 Web 对话页的后续改动（自动模式、来源编号、fallback 按钮）
