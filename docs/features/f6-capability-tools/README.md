# F6: 系统能力增强（Agent 工具集扩展）

## 功能概述

在 RAG + ReAct Agent 架构之上扩展一组本地优先的能力工具：网络搜索、AST 代码分析、
代码质量检查、Git 分析与提交信息生成、知识图谱、SQLite 数据库工具。全部以
`agent_tools.py` 工具 + CLI 斜杠命令 + Web「工具」页三种形式暴露。

## 实施状态

**状态**: ✅ 已完成（v0.0.x 系列陆续交付）
**原设计**: [DESIGN.md](DESIGN.md)（需求，2026-06-15）、[IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md)（代码级方案）
**原编号**: F5（归档时重编号为 F6，避免与 `f5-desktop-packaging` 冲突）

> 原设计以 `Qwen2.5-Coder:7B` 为前提；当前默认模型已改为 `qwen3.5:4b`
> （`src/config.py`，按模型规模自动推导 `num_ctx`）。设计中的模型分析章节仅作历史参考。

## 逐项实现记录

| 子项 | 原设计 | 结论 | 实际实现 |
|---|---|---|---|
| F5.1 AST 语法树搜索 | `code_analyzer.py` + jedi | ✅ 已实现 | `src/code_analyzer/ast_analyzer.py::ASTAnalyzer`（纯 stdlib `ast`，仅 Python）；工具 `ast_search`；CLI `/code-ast`；Web 工具页 |
| F5.2 代码语义搜索 | sentence-transformers + faiss 独立索引 | ❌ 取消 | 与现有 RAG 向量库重叠（代码文件已可入库检索）。若需改进，作为"代码感知分块"挂到 F8 P2 可选项 |
| F5.3 代码质量分析 | pylint / bandit / radon / vulture | ✅ 已实现 | `src/code_analyzer/quality_checker.py::QualityChecker`（子进程调用 pylint/bandit/radon，运行时探测）；工具 `code_quality_check`；CLI `/code-quality`。打包版依赖用户本机安装这些工具 |
| F5.4 Git 深度集成 | gitpython + PyGithub | ✅ 已实现 | `src/git_integration/{git_analyzer,commit_generator}.py`（`subprocess git`，未用 gitpython）；工具 `git_analyze` / `git_commit_gen`；CLI `/git-analyze` / `/git-commit-gen`。未做冲突解决辅助、PyGithub |
| F5.5 本地知识图谱 | networkx + pyvis + rdflib | ✅ 已实现 | `src/knowledge_graph/{entity_extractor,graph_builder,graph_query}.py`（规则抽取 + networkx）；可视化改用 **Plotly 3D/2D**（Web 图谱页、CLI `/graph-export`）；工具 `knowledge_graph_query` / `knowledge_graph_build`；CLI `/graph-*`。未用 rdflib |
| F5.6 知识点关联网络 / 学习路径 / 复习计划 | scikit-learn + community | ❌ 取消 | 偏学习型产品需求；图谱的邻居/路径查询已覆盖用户实际需要 |
| F5.7 轻量级网络搜索 | duckduckgo-search + trafilatura | ✅ 已实现 | `src/web_search/`：DuckDuckGo / Baidu / Wikipedia 降级链、`SearchCache`、`ResultProcessor`、`ContentExtractor`（trafilatura → bs4 回退）；工具 `web_search` / `web_content_extract` / `web_cache_*`；CLI `/web-search` / `/web-extract` / `/web-cache`；RAG 管道联网回退 `rag_pipeline.plan_web_search / augment_with_web_search` |
| F5.8 技术文档智能查询 | readability + markdownify，版本对比、变更追踪 | ⚠️ 部分 / 其余取消 | 网页正文提取已由 `web_content_extract` 覆盖；"API 文档结构化 / 版本差异对比 / 变更追踪"取消（不实际） |
| F5.9 本地数据库工具 | sqlalchemy，SQLite/MySQL/PostgreSQL | ⚠️ SQLite 已实现 / 其余取消 | `src/database_tools/{db_connector,query_executor,sql_generator}.py`（原生 `sqlite3`）；工具 `database_*` 6 个；CLI `/db-*`。MySQL/PostgreSQL 分支 `NotImplementedError`，本地隐私助手定位下不再扩展 |
| F5.10 时间序列分析 | statsmodels + prophet | ❌ 取消 | 与"文档 + 代码助手"定位无关，依赖极重 |

## 当前注册的 Agent 工具（29 个）

- 文件/系统：`read_file` `write_file` `execute_command` `list_directory` `analyze_project_structure` `search_files` `get_current_dir` `read_system_prompt`
- 知识库：`query_knowledge_base` `add_to_knowledge_base` `get_knowledge_stats` `check_knowledge_status`
- 网络：`web_search` `web_content_extract` `web_cache_status` `web_cache_clear` `clear_web_search_cache`
- 代码分析：`ast_search` `code_quality_check`
- Git：`git_analyze` `git_commit_gen`
- 知识图谱：`knowledge_graph_query` `knowledge_graph_build`
- 数据库：`database_connect` `database_query` `database_execute` `database_create_table` `database_insert` `database_get_schema`

## 相关文档

- [DESIGN.md](DESIGN.md) - 原需求设计
- [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) - 原代码级实现方案（模块名与库选型与实际有出入，以本文件为准）
- [F8 三种对话模式优化](../f8-agent-modes-optimization/REQUIREMENTS.md) - 后续：让 Agent 更好地使用这些工具（F8）
