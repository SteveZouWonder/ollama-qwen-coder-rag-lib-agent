# 项目陷阱清单

从 CHANGELOG 修复记录与代码注释中提炼的**本项目特有**陷阱。每条给出现象 → 根因 → 现行规则；改到相关区域前先读对应小节。通用 Python / pytest 常识不在此列。

## 1. 路径与运行时数据

| 陷阱 | 说明 |
|---|---|
| 相对 cwd 的数据路径 | 读端 `./index_storage/chroma_db` 按 cwd 解析、写端用绝对路径，用户 `/cd` 后读到空库。**规则**：所有程序生成的数据走 `runtime_paths.app_state_dir()` / `user_data_dir()`，不拼相对路径。 |
| 默认目录改名不迁移 | 把 `.devin/` 改为 `.cerebro/` 时若不搬迁，用户既有快照 / 图谱 / 元数据"消失"。**规则**：改默认路径必须带一次性迁移（参考 `_migrate_legacy_state`），不覆盖已有目标。 |
| 打包 datas 目标名 | PyInstaller `datas` 目标目录不能叫 `config`（与顶层模块 `config.py` 同名冲突），用 `default_config`；`prompts/` 无 .py 可同名。 |
| 打包不含资源 | 历史上 `.devin/SYSTEM_PROMPT.md` 从未进 `datas`，打包版项目规范静默失效。**规则**：任何运行时读取的仓库文件都要进 `datas` 并经 `resource_root()` 定位。 |
| 打包子进程继承 `_MEIPASS2` | 托盘启动 Web 子进程会把 PyInstaller 环境变量传下去导致导入错乱；需剔除 `_MEIPASS2` / `_PYI_*`。多进程需 `multiprocessing.freeze_support()`。 |
| `collect_all` 漏库 | trafilatura（`settings.cfg`）、justext（stoplists）、gradio / gradio_client（前端资源）、rank_bm25、tree_sitter*、plotly 等动态资源库不 `collect_all` 会在打包版运行时报错。 |

## 2. 会话与上下文

| 陷阱 | 说明 |
|---|---|
| 单例被钉死 | `ConversationContext.new_session()` 曾无条件设置 `self.session_id`，CLI 进程级单例从"跟随当前会话"变成钉死在某会话，之后 `/session-new` `/session-switch` 失效。**规则**：跟随模式（`session_id=None`）永不写 `session_id`。 |
| "携带摘要"泄漏原文 | 曾把未压缩的 live 消息启发式拼进新会话背景，新会话 UI 为空但模型"记得"旧对话。**规则**：只承接已折叠的滚动摘要；无摘要则新会话完全干净。 |
| Web 标签页未绑定会话 | `session_state` 为空时每次调用回落到全局"当前会话"指针，可被其他标签页改掉。**规则**：首轮 `ensure_session()` 钉死并在 `_end` 写回 `gr.State`。 |
| 复选框状态常驻 | Gradio 复选框（如「携带摘要」）勾选后对后续每次点击都生效。**规则**：一次性选项在事件输出中复位 `gr.update(value=False)`。 |
| metadata 字段兼容 | `session.metadata["context"]` 新增字段时旧会话文件没有；用 `_meta()` 的 `setdefault`，不要直接索引。`FileMetadata.from_dict` 同理忽略未知键。 |
| 系统提示落盘 | 早期把系统提示写进历史文件，与代码不同步。**规则**：系统提示运行时组装，会话只存 user / assistant 与摘要。 |

## 3. ReAct 引擎

| 陷阱 | 说明 |
|---|---|
| 裸文本当答案 | 无 `Final Answer` 的文本、非 JSON 的 `Action Input`、`[错误] 模型调用失败` 曾整段当最终答案写入会话。**规则**：格式错误回灌 `[格式错误]` 重试 ≤ `MAX_FORMAT_RETRIES`；模型调用失败直接返回不落库。 |
| 步数耗尽丢结果 | 曾只返回固定警告丢弃全部中间结果。**规则**：`_forced_summary` 让模型基于 Observation 总结，前缀 `⚠️ 未完成`。 |
| 无限重复调用 | 相同 `(tool, args)` 无限循环。**规则**：第 2 次 `[重复调用]`，第 3 次强制总结。 |
| Observation 撑爆上下文 | 单步 5000 字 × 50 步无折叠。**规则**：单条截 `OBSERVATION_MAX_CHARS`(3000)，本轮超预算从最早步折叠，保留最近 3 步。 |
| 系统提示占满 ctx | 6.2K token 的规范整体替换内置模板占 40% 上下文。**规则**：内置模板 ≤1500 token（测试硬限）；项目规范 append 且截 4000 字；Skills 截 4000 字；子角色 `builtin`。 |
| `replace` 模式 | 已移除（PROJECT_RULES 是补充不是完整提示）；传入按 `append` 处理并 warning。 |
| 命令分级盲区 | `python x.py` / `pip install` / `git push` 曾为 low 免确认；`curl … | bash` 曾漏判。**规则**：改 `CommandSafetyChecker` 模式表时补对应测试；`config.READONLY_COMMANDS` 无人引用。 |
| 写文件越界 | Agent 可写任意路径。**规则**：`write_file` / `add_to_knowledge_base` 过 `is_path_allowed()`。 |
| `[CONFIRM_REQUIRED]` 泄露到用户 | CLI 曾直接打印协议串。**规则**：协议串只在 ReAct 层解析并走 `on_confirm`。 |
| `LLM_THINK` 开着跑 ReAct | 4B 模型每步从 2.8s 变 31s。默认关；ReAct 协议本身已是显式推理。 |

## 4. 多 Agent

| 陷阱 | 说明 |
|---|---|
| 假成功 | 早期 4/5 个 Agent 返回硬编码文本 `success=True`；PARALLEL 实为串行；COMPETITIVE 按最快选优；超时不生效。现全部委托真实 ReActEngine，`ThreadPoolExecutor` 并行，LLM 评审选优，`execute_task_with_timeout`。 |
| 子 Agent 一律拒绝确认 | 导致 Code / Test Agent 永远写不了文件，模型进而编造"已完成"。**规则**：白名单工具放行，`execute_command` 仅 low / medium。 |
| 口头完成 | 子 Agent 未调 `ESSENTIAL_TOOLS` 却报告完成。**规则**：标 `unverified` + 前缀提示。 |
| RAGAgent 无引擎 | 多 Agent 前必须 `agent_tools.set_rag_engine()` 注入全局（Web `_run_orchestrator` 已处理）。 |
| 白名单与配置双份 | `agents/*_agent.py` 的 `ALLOWED_TOOLS` 与 `agent_config.py` 的 `specialized_tools` 必须一致，测试有精确集合断言。 |

## 5. RAG 与检索

| 陷阱 | 说明 |
|---|---|
| 两个阈值混用 | `SIMILARITY_CUTOFF`(0.3) 是底层召回保护（保住元查询）；`KB_RELEVANCE_THRESHOLD`(0.45) 是命中判定。纯向量分数分不开话题，命中判定要过 rerank。 |
| 元查询走向量 | "知识库里有什么"若走检索会命中噪音。**规则**：`is_meta_query` 固定短语 + 正则先拦。 |
| `load_index()` 未设切分器 | 启动加载已有索引后追加文档落到 LlamaIndex 默认 `SentenceSplitter(1024/200)`。**规则**：三条入库路径共用 `node_parser`。 |
| `run_web_search` 丢查询 | 曾只取第一个有效查询。**规则**：合并所有查询按 URL 去重，正文提取前 3 页。 |
| 图谱 `clear()` 落盘 | 默认把空图写回磁盘抹掉数据。**规则**：`clear(persist=False)` 默认不落盘。 |
| num_ctx 不限 | qwen3.5 默认 256K 撑爆显存。**规则**：`resolve_num_ctx` 按参数量推导。 |
| 双模型驻留 | 切模型后旧模型不释放（Ollama 不主动驱逐）。**规则**：`model_switcher` 切换时立即 unload 旧模型。 |

## 6. Web / Gradio

| 陷阱 | 说明 |
|---|---|
| outputs 元组长度 | handler 返回值个数必须与 `outputs` 列表一致，否则运行时才报错且 `ui/*` 无单测。改事件后手动启动验证。 |
| `launch()` 阻塞 | 需非阻塞启动 + 统一等待；Ctrl+C 主动 `close()` 释放 7860。 |
| 长任务在 handler 内直跑 | 界面卡死无法取消。**规则**：走 `WebService._bridge` 后台线程 + 队列 + 心跳。 |
| 模块级"当前会话" | 多标签页共享。**规则**：每标签页 `gr.State`。 |
| `is_running()` 并发 | Ollama 单实例，第二个任务应被拒绝而不是排队。 |
| 单输出组件返回列表 | `outputs=[btn]` 时返回 `[gr.update(...)]` 会被当作 Button 的 value 渲染成 `[{'interactive': False…}]`。**规则**：单输出返回标量（`tools.py::_lock` 已处理）。 |
| 可编辑 `gr.Code` 空初值 | Gradio 6.20：初值为空则不渲染编辑器，之后任何写值触发前端 `props_invalid_value` 并中断整次更新；动态切 `interactive` 亦如此。**规则**：给非空初始注释、不切 `interactive`。 |
| 惰性渲染子页的 `visible` 更新 | 未访问过的 `gr.Tab` 内 Markdown 的 `gr.update(visible=…)` 会丢失（`interactive` 不会）。**规则**：在 `tab.select` 时按状态重同步（Git 子页门控提示）。 |

## 7. 测试

| 陷阱 | 说明 |
|---|---|
| 真连 Ollama | `rag_rerank._llm_complete`、`intent_router._llm_complete`、子 Agent 的 `requests.post` 会直连本机；conftest 已拦截，新增直连点要补。 |
| 污染真实数据 | `file_metadata` / `knowledge_graph` 单例默认写 `.cerebro/`，`command_recommender.config.get_config()` 默认写 `data/recommender_preferences.json`；conftest 已隔离（`isolate_*` fixture），新增持久化点要补。 |
| 模块内 `get_config()` 单例绕过依赖注入 | 构造函数接受 `config` 却在内部子对象里再调 `get_config()`（`LearningEngine` 曾如此），注入的临时路径形同虚设：测试写用户真实文件，且经共享文件跨 worker 耦合——`test_format_recommendations` 在 xdist 下随机失败就是这样来的。子对象要显式接收父对象的 `config`；`learning_enabled=False` 之类的"只读"开关要真正拦住落盘。 |
| xdist 顺序依赖 | 顺序单跑通过、`-n 4` 偶发失败 ⇒ 先找跨测试共享的**文件 / 环境变量 / 模块级单例**，再看 `reset_*()` + `os.environ[...] =` 这类改全局状态的测试（用 `monkeypatch` / `patch.dict` 限定作用域）。 |
| 收集错误被忽略 | 改导出名后某测试文件 ImportError，全套仍"通过"。看 `--collect-only` 的 error 计数。 |
| token 上限测试 | 改 `SYSTEM_PROMPT_TEMPLATE` 后 builtin ≤1500 token 失败；测试里需 `CODE_AGENT_SKILLS=off` 隔离 Skills 层。 |

## 8. 提示与文档

| 陷阱 | 说明 |
|---|---|
| 提示里写开发者流程 | "先读 AGENTS.md / 加载知识库文档 / 覆盖率 95%" 之类内容会诱导产品 Agent 在用户任务前浪费步数读项目文件。**规则**：开发者规范在 `docs/development/ai-assistant/`，产品提示在 `prompts/`。 |
| 提示里的参数名漂移 | 曾写 `"query"`（实为 `question`）、`"keyword"`（实为 `query`）。**规则**：`PROJECT_RULES.md` 参数名段有测试对照 `registry`。 |
| 文档写死行号 / 数字 | 工具数、行号、版本号很快过时。以函数名为锚，数字写在一处（本目录）并在改动时更新。 |
