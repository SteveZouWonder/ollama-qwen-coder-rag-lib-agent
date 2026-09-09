"""CLI 帮助与教程文案（F10 P2-2 由 ``query_interface`` 抽出）。

``print_help(console, has_rich)`` 内联 ``/help`` 文案并渲染；``TUTORIAL_TEXT``（``/tutorial`` / 首次运行）为常量。改 CLI 行为时须同步这两段文案（AGENTS.md）。
"""
from __future__ import annotations

TUTORIAL_TEXT = """
欢迎使用 Cerebro 🧠 — 你的第二大脑 + 代码助手！

本工具融合了两套核心能力：

1. 📚 RAG 知识库
   基于 LlamaIndex + ChromaDB 构建的个人文档检索系统。
   支持 PDF、Markdown、论文、代码文件等 17 种格式。
   代码文件（.py/.js/.ts/.java/.go/.rs/.c/.cpp）按函数/类切分，引用可定位到行号。
   上传文档后，可直接用自然语言查询内容。

2. 🤖 ReAct Agent
   基于 Ollama + ReAct 架构的代码助手。
   自动读写文件、执行命令、搜索代码、多步推理。
   带安全护栏：危险命令自动拦截，修改命令需确认；读写文件限于允许目录
   （工作目录 + WRITE_ALLOWED_DIRS / READ_ALLOWED_DIRS + 已入库文档所在目录，/config 可查）。

快速上手示例：

  # 知识库查询
  >>> /ask 这篇论文的核心贡献是什么？
  >>> /ask 总结一下笔记中的关键概念

  # Agent 任务（自动调用工具）
  >>> /agent 写一个 Python 快速排序，保存到 sort.py，然后运行单元测试
  >>> /agent 检查 src/main.py 第 20-50 行是否有内存泄漏
  >>> /agent 搜索项目中所有硬编码的 API Key

  # 多 Agent 协作（代码/测试/文档/审计/知识库专家分工）
  >>> /multi 写一个快速排序保存到 sort.py 并为它写测试
  >>> /multi 审计 src/agent_tools.py 的安全问题 --mode competitive

  # 自动路由（默认开）：不加斜杠直接输入，自动判定走知识库还是 Agent
  >>> 什么是 RAG？                    → 知识库问答
  >>> 修改 main.py 加上日志           → Agent 处理（用 /ask 可强制知识库）

  # 流式输出（默认开）：/ask、/agent、/multi 的最终答案逐字出现，Ctrl+C 随时中断并关闭连接
  # （环境变量 LLM_STREAM=false 可回到整段一次性输出）

  # 快捷命令
  >>> /file main.py          快速读取文件
  >>> /exec git status       执行命令
  >>> /add ./新论文.pdf       添加文档到知识库
  >>> /stats                 查看知识库统计

常用内置命令：
  /help      显示帮助
  /tutorial  重新显示本教程
  /ask       直接查询知识库
  /agent     进入 Agent 任务模式
  /multi     多 Agent 协作模式
  /tools     查看所有可用工具
  /config    显示运行配置（含允许读 / 写目录）
  /add       添加文档到知识库
  /stats     知识库统计
  /sources   显示上次回答的来源
  /clear     清空屏幕
  /history   查看对话历史
  /summary   查看 Agent 执行摘要
  /file      快速读取文件
  /write     交互式写入文件
  /exec      执行命令（走安全确认）
  /pwd       显示当前目录
  /cd        切换目录
  /model     显示模型信息；/model <name> 热切换模型
  /think     显示/开关思考模式（/think on|off）
  /auto      显示/开关自动路由（/auto on|off；开时自然语言自动判定走知识库还是 Agent）
  /reset     重置 Agent 对话上下文
  /quit      退出

文件管理命令：
  /file-list           列出知识库中的所有文件
  /file-info <path>    查看文件详细信息
  /file-delete <path>  从知识库删除文件（不删磁盘文件，需确认）
  /file-cleanup        清理临时/重复文件
  /file-deduplicate    手动触发去重（只移除登记，不删向量）
  /file-stats          显示文件统计信息

知识库快照命令：
  /snapshot-list / /snapshot-create        列出 / 手动创建快照
  /snapshot-info <id>                      快照详情（文档清单与文件是否仍存在）
  /snapshot-restore <id> [--apply [--replace]]  生成恢复脚本 / 直接恢复（追加或替换）
  /snapshot-delete <id> | /snapshot-prune [N]   删除快照 / 清理自动快照仅保留最近 N 个

会话管理命令：
  /session-new [title]        创建新会话
  /session-list               列出所有会话
  /session-switch <id>        切换到指定会话
  /session-archive <id>       归档会话
  /session-delete <id>       删除会话
  /session-info <id>          查看会话详情
  /session-search <query>     搜索会话
  /session-current            显示当前会话信息
  /session-compress           压缩当前会话历史

网络搜索命令：
  /web-search <query>         网络搜索（支持 DuckDuckGo）
  /web-cache status           查看搜索缓存状态
  /web-cache clear            清空搜索缓存
  /web-extract <url>          提取网页内容

代码分析命令：
  /code-ast <pattern>         AST 搜索（函数、类、变量）
  /code-quality <path>        代码质量检查

Git 命令：
  /git-analyze [type]         Git 概览表（分支 / 变更数 / 最近 10 次提交）；status 变更文件表 / authors 提交者表
  /git-commit-gen             AI 生成提交信息

数据库命令（SQLite）：
  /db-connect <database>      连接并设为当前连接，之后 /db-query /db-execute /db-schema 作用于该库
  /db-query <sql>             执行查询，结果以表格显示（最多 50 行）
  /db-schema [table]          表结构表（列 / 类型 / 约束）；不带参数列出全部表

知识图谱命令：
  /graph-query <文本>         按实体名模糊查询（默认）
  /graph-query type:<类型>    列出某类型实体（如 type:tool）
  /graph-query neighbors:<实体>  查询邻居  | path:<A>-><B> 查路径 | similar:<实体> 查相似
  /graph-build <文本|@文件>   构建知识图谱
  /graph-summary              图谱概览（节点/边/类型分布）
  /graph-export [路径] [--3d|--2d] [--focus 实体]  导出交互式 HTML 图谱并在浏览器打开
"""




def print_help(console=None, has_rich: bool = False) -> None:
    """打印 ``/help``：有 rich 时用 Panel，否则纯文本（文案内联，便于 ``inspect.getsource`` 校验）。"""
    help_text = """
内置命令：
  /help              显示本帮助
  /tutorial          显示使用指引教程
  /ask <question>    直接查询知识库（基于上传的文档；答案逐字流式输出，Ctrl+C 中断）
  /agent <task>      进入 Agent 模式（自动调用工具完成复杂任务；最终答案流式输出，Ctrl+C 中断）
  /multi <task>      多 Agent 协作（分解→并行执行→综合）；可加 --mode parallel|sequential|competitive
  /tools             查看所有可用工具及安全等级
  /config            显示运行配置（模型 / 自动确认 / 允许读写目录 / 数据与索引目录）
  /add <path>        添加文档到知识库（PDF/MD/TXT/代码等；代码按函数/类切分，来源带 符号·行号）
  /stats             显示知识库统计
  /sources           显示上次知识库回答的来源
  /clear             清空屏幕
  /history           显示当前对话历史摘要
  /summary           显示本次 Agent 执行步骤摘要
  /file <path>       快速读取文件（不经过模型）
  /write <path>      交互式写入文件模式
  /exec <cmd>        快速执行命令（走安全确认流程；high 风险即使开了自动确认也仍需确认）
  /pwd               显示当前工作目录
  /cd <path>         切换当前工作目录
  /model             显示当前模型信息（含是否已加载、驻留大小）
  /model list        列出本机已安装的模型
  /model <name>      运行时热切换模型并释放旧模型（如 /model qwen3.5:9b）
  /think             显示思考模式状态（默认关，响应快）
  /think on|off      运行时开关思考模式（开启需模型支持，如 qwen3.5）
  /auto              显示自动路由状态（默认开：自然语言先判定走知识库还是 Agent）
  /auto on|off       运行时开关自动路由（关闭后自然语言一律走知识库问答）
  /context           查看当前会话上下文（轮数/估算 token/预算/压缩次数/摘要）
  /compact           手动压缩当前会话历史（最旧轮次折叠进滚动摘要）
  /reset             清空当前会话上下文（消息与滚动摘要，三种模式共用）
  /exit 或 /quit     退出程序

连续对话：/ask、自然语言输入与 /agent 都会记住当前会话的上下文，可直接追问
（如"它多少钱"）；历史超出预算时自动压缩，对话过长会提示新建会话。
自动路由：不加斜杠的自然语言输入会先判定意图——含路径/代码/命令式动词走 Agent，
疑问/总结类走知识库；/ask、/agent 显式命令不判定。可用 /auto off 关闭（或环境变量 AUTO_ROUTE=false）。

知识库管理命令（新功能）：
  /generate-skills   将知识库内容转化为Skills
  /snapshot-list    查看所有知识库快照
  /snapshot-create  手动创建知识库快照
  /snapshot-info <id>     查看快照详情（文档清单、文件是否仍存在、模型配置）
  /snapshot-restore <id>  生成恢复脚本；加 --apply 直接恢复（追加），--apply --replace 先清空再恢复
  /snapshot-delete <id>   删除指定快照（需确认）
  /snapshot-prune [N]     清理自动快照，仅保留最近 N 个（默认 10，手动快照不受影响）
  /knowledge-summary  查看知识库文档摘要

知识图谱管理命令（新功能）：
  /graph-query <文本>       按实体名模糊查询（默认）
  /graph-query type:<类型>  列出某类型实体；另支持 neighbors:/path:/similar: 前缀
  /graph-build <文本>       从文本构建知识图谱（或 /graph-build @<文件路径>）
  /graph-summary            图谱概览（节点/边/类型分布）
  /graph-export [路径] [--3d|--2d] [--types a,b] [--max N] [--focus 实体] [--hops 1|2]
                            导出自包含的交互式 HTML 图谱并在浏览器打开

数据库管理命令（SQLite）：
  /db-connect <database>        连接数据库并设为当前连接（默认 sqlite；也可 /db-connect sqlite <database>）
  /db-query <sql>               在当前连接上执行SQL查询（表格显示，最多 50 行）
  /db-execute <sql>             在当前连接上执行SQL语句（INSERT/UPDATE/DELETE/DDL）
  /db-create-table <table> <columns_json>  创建数据库表
  /db-insert <table> <data_json>           插入数据
  /db-schema [table]            表结构表（列 / 类型 / 约束）；不带参数列出全部表

文件管理命令（新功能）：
  /file-list           列出知识库中的所有文件
  /file-info <path>    查看文件详细信息
  /file-delete <path>  从知识库删除文件（向量片段 + 图谱来源 + 元数据，不删磁盘文件，需确认）
  /file-cleanup        清理临时/重复文件
  /file-deduplicate    手动触发去重（只移除重复登记，不删向量；彻底删除请用 /file-delete）
  /file-stats          显示文件统计信息

会话管理命令（新功能）：
  /session-new [title]        创建新会话（加 --carry 可把当前会话摘要带入新会话）
  /session-list               列出所有会话
  /session-switch <id>        切换到指定会话
  /session-archive <id>       归档会话
  /session-delete <id>       删除会话
  /session-info <id>          查看会话详情
  /session-search <query>     搜索会话
  /session-current            显示当前会话信息
  /session-compress           压缩当前会话历史（等同 /compact）

网络搜索命令（新功能）：
  /web-search <query>         网络搜索（支持 DuckDuckGo）
  /web-cache status           查看搜索缓存状态
  /web-cache clear            清空搜索缓存
  /web-extract <url>          提取网页内容

代码分析命令（新功能）：
  /code-ast <pattern>         AST 搜索（函数、类、变量）
  /code-quality <path>        代码质量检查

Git 命令（新功能）：
  /git-analyze [type]         Git 概览表（分支 / 变更 / 最近提交）；status 变更文件表 / authors 提交者表
  /git-commit-gen             AI 生成提交信息

使用示例：
  >>> /ask 这篇论文的实验结果是什么？
  >>> /agent 把 utils.py 里的 print 改成 logging，并运行测试
  >>> /agent 搜索项目中所有使用硬编码密码的地方
  >>> /add ~/Downloads/论文.pdf
  >>> /file src/main.py
  >>> /generate-skills
  >>> /snapshot-list
  >>> /web-search 最新的 Python 稳定版本
  >>> /code-quality src/
  >>> /git-analyze
  >>> /db-connect ./data/app.db
  >>> /db-query SELECT * FROM users LIMIT 5
"""
    if has_rich and console is not None:
        from rich import box
        from rich.panel import Panel

        console.print(Panel(help_text, border_style="yellow", title="帮助", box=box.ROUNDED))
    else:
        print(help_text)
