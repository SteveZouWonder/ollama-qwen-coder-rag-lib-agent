# 更新日志

本项目所有重要变更都记录在本文件中。

格式遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [Unreleased]

> 下一版本的未发布变更请记录在此区段。发布时将其移动到对应的版本号下。

### 新增
- 网络搜索新增一批可配置项（环境变量）：`WEB_SEARCH_REGION`、`WEB_SEARCH_BACKEND`、
  `WEB_SEARCH_SAFESEARCH`、`WEB_SEARCH_TIMELIMIT`、`WEB_SEARCH_MAX_RESULTS`、
  `WEB_SEARCH_TIMEOUT`、`WEB_SEARCH_CACHE_TTL_HOURS`、`WEB_SEARCH_AGGREGATE`，
  可按部署网络环境（尤其国内）调整搜索区域、后端引擎、聚合策略与超时/缓存。
- Web 界面新增大量与 CLI 对齐的功能面板：文件管理（文件列表/统计）、网络搜索
  （搜索/网页正文提取/缓存状态与清空）、代码分析（AST 搜索/代码质量检查）、Git
  （历史/状态/作者分析、AI 生成提交信息）、数据库（连接/查询/执行/查看 Schema）、
  知识库管理（生成 Skills/知识库摘要/快照列表/创建/恢复脚本）以及知识图谱从文本
  构建，让 Web 覆盖面向 CLI 命令面看齐。
- Web 会话页新增"切换会话""搜索会话"，知识库页新增"从目录重建索引"，知识图谱页
  新增"图谱概览"，补齐了此前服务层已实现但界面未接线的能力。
- Web 对话页新增"联网搜索增强"（RAG 模式）与"自动确认危险命令"（单 Agent 模式，
  等价 CLI `--yes`）两个开关。
- 运行时模型热切换：CLI 新增 `/model <name>`（切换）与 `/model list`（列出本机已安装
  模型），`/model` 现会显示模型是否已加载、驻留大小、num_ctx 与思考模式；Web 对话页
  顶部新增模型下拉与状态行。切换会同步 RAG 引擎（重建 LLM 与查询引擎）、ReAct Agent
  与多 Agent 配置，并**立即释放旧模型**——Ollama 只在"放不下"时才驱逐旧模型，4B+9B
  会被判定为放得下而双驻留，与 IDE 并行时直接换页卡顿。无需重启即可在"协同档"
  `qwen3.5:4b` 与"性能档" `qwen3.5:9b` 之间切换。
- 新增 `LLM_THINK` 配置（默认 `false`）：关闭 qwen3.5 等模型的隐式思考模式。ReAct 的
  Thought/Action 协议本身就是显式推理，再叠加思维链只会拖慢每一步；本机实测同一问题
  qwen3.5:4b 从 31s（682 token，其中 1845 字思考）降到 2.8s（65 token）。需要深度推理
  时可设 `LLM_THINK=true`（仅支持思考模式的模型，否则 Ollama 会报错）。
- 文档新增「模型选择指南」（README 与 `docs/tutorials/07-best-practices.md`）：按机器
  内存与使用场景（与 IDE 并行 / 专注模式 / 低配 / 工作站 / 格式化输出）给出推荐模型、
  实测驻留内存与吞吐、三种切换方式，以及与 IDE 共存的内存实践；并说明
  `SparkLLM/Spark-X2.5-4B` 因官方 Ollama 尚不支持其架构暂列"关注中"。

### 改进
- 新增内置百度搜索引擎作为国内信息主力源（移植自 SearXNG 的 baidu 引擎逻辑）：
  调用百度网页搜索的 `tn=json` 结构化接口，纯 requests 实现、无浏览器/外部服务
  依赖、随 App 打包开箱即用。解决 DuckDuckGo/Brave 等海外引擎对中文与国内站点
  （京东/淘宝/知乎/中关村/学术站等）召回差、搜不到国内电商价格/论文/项目的问题。
  按查询语境自动选源：判定为国内查询（中文/含"国内/售价/价格"等语境）时以百度
  为主源、DuckDuckGo/Wikipedia 兜底；全球/英文查询以 DuckDuckGo 为主、百度作补充。
  含验证码（302 跳 wappass）与反爬（antiFlag）检测，触发时安全跳过。
- 网络搜索支持按查询语境自动选择搜索区域：含"国内/中国/国行/淘宝/京东/售价/价格"
  等语境或中文的查询自动用中国区（`cn-zh`），能召回淘宝/京东/中关村/知乎等国内站点
  与国行价格；英文/全球性查询用全球区（`wt-wt`）。此前默认全球区导致"中国国内某产品
  售价"只搜到 Wikipedia/海外站、答不出国行价格。区域策略默认 `auto`，可用
  `WEB_SEARCH_REGION` 环境变量强制固定。
- 国内价格类查询不再自动补英文查询：`plan_web_search` 识别到国内语境时只用中文查询，
  避免英文结果把国内电商/国行价格挤出结果。
- 默认搜索后端调整为 `brave, duckduckgo, google`：部分 ddgs 版本的 bing 后端已被禁用
  （运行时告警并忽略），改用有效且对中文覆盖好的后端。
- 大幅提升中国国内信息的网络搜索准确率：此前搜索仅用 DuckDuckGo 单后端、且未设
  区域/语言（默认 us-en，偏英文/海外），中文与国行价格、国内新闻等召回很差。现在：
  搜索会传入 region、backend、safesearch、timelimit 等参数；多后端整体失败时逐个后端
  降级重试（DuckDuckGo/Google 常被连接重置时自动切到可用后端）；Wikipedia 备用改为按
  查询语言自动选择中/英文站点；网页正文提取修正中文编码（避免 GBK/GB2312 页面乱码）；
  相关性打分改为中文友好（中文逐字、英文按词的 token 覆盖率，降低长度权重）；并支持
  多引擎结果聚合去重而非"首个非空即返回"。
- Web 的 RAG 问答（`/ask` 等价能力）现与 CLI 表现一致：新增元/概览问题直答、
  LLM 驱动的网络搜索规划、多查询合并去重、页面正文增强、知识库/网络来源分区综合、
  0 命中时的网络/模型回退，回答中会明确区分知识库来源与网络来源。此前 Web 仅做
  裸检索，导致同一问题两端答案质量差异很大。
- Web 对话（RAG 与单 Agent）完成后会自动写入当前会话，与 CLI 的对话持久化行为
  对齐，可在会话历史中回看。
- 将 CLI 独有的高级 RAG 编排逻辑下沉到共享模块 `src/rag_pipeline.py`，供 CLI 与
  Web 复用，避免逻辑重复、保证两端行为一致（属内部重构，用户可感知效果见上）。
- 改为「单一模型」架构：用户只需选一个模型（`LLM_MODEL`，可用 CLI `--model`、
  `/model <name>`、Web 下拉或环境变量覆盖），它同时用于 ReAct Agent、代码任务、RAG
  综合回答与相关性判定；多 Agent 各角色、模型预热列表（桌面应用/首次引导）也统一跟随
  该模型。全程只驻留单一模型，避免此前「主模型 + 综合模型」在中端机（如统一内存）上
  同时占用显存导致卡顿/卸载到 CPU。移除了独立的 `SYNTHESIS_MODEL` 配置。
- 默认模型由 `qwen2.5-coder:7b` 改为 `qwen3.5:4b`（"协同档"）。选型依据：对比 Ollama
  库中 16GB 机器可运行的候选（qwen3.5 4b/9b、gemma4 e4b/12b、granite4.1 等）的公开
  基准与本机实测——4b 在 16K 上下文下约 3.7GB 驻留、~25 tok/s，可与 IDEA/PyCharm/
  浏览器并行；9b 约 6GB 驻留、工具调用与代码能力更强但与 IDE 并行会触发换页卡顿，故
  作为"性能档"供内存宽裕或专注模式时切换。README、教程、前置检查脚本、Release 文案、
  桌面应用配置同步更新。
- 上下文窗口（num_ctx）改为按所选模型自动推导（用户零配置）：qwen3.5 等模型默认上下文
  高达 256K，Ollama 会据此分配 KV cache 撑爆显存并卸载到 CPU，导致推理近乎卡死；现按
  参数量给出安全值（≤4B→16384，7~9B→8192，12B+→4096），Agent、RAG 全局模型均已应用。
  参数量解析改为正则提取，兼容 `qwen3.5:4b`、`qwen2.5-coder:7b`、`Vendor/Model-X2.5-4B`
  等命名。可用 `LLM_NUM_CTX` 环境变量强制覆盖。
- 桌面应用 `warm_up_on_startup` 默认改为 `false`：启动预热会让模型常驻内存，在 16GB
  机器上与 IDE/浏览器并行时加剧换页；Ollama 会在首次请求时按需加载、闲置后自动释放。
  内存宽裕的机器可在 `app_config.json` 改回 `true` 换取首问速度。
- 知识库统计（`/stats`、Web 知识库页）现显示当前模型的 num_ctx。

### 修复
- 进一步修复 RAG 会把"分数勉强过阈值但话题完全不相关"的知识库片段当作依据的
  问题：纯向量相似度无法区分话题相关性（例如问"某产品售价"却召回相似度 0.452、
  讲 Cloudflare 配置的中文文档片段，刚好越过 0.45 阈值）。现新增 LLM 相关性判定：
  对通过阈值的片段用 LLM 快速判断是否真能帮助回答问题，判为无关则视为知识库未
  命中、回退网络/模型且不展示噪音来源；最高分达到高可信线（0.6）时跳过判定省开销，
  判定器故障时保守保留命中（不误杀）。
- 修复"知识库里都有些什么资料""当前知识库包含哪些文档"等元/概览类问题变体未被
  识别、错误走向量检索命中无关噪音的问题：元查询识别改为固定短语 + 正则组合
  （知识库/库中 + 有哪些/包含/收录 + 信息/资料/内容/文档/文件/数据），覆盖更多表达。
- 修复多 Agent 协作模式下 RAGAgent 处理通用问题时答非所问的问题：此前 RAGAgent
  走底层裸检索，会把无关低分片段（相似度约 0.39）当作答案与来源展示，且不做网络
  回退。现改为复用共享编排层 `rag_pipeline.answer_question`，与 CLI/Web 的 RAG 模式
  表现一致（相关性过滤、网络搜索回退、知识库/网络双区综合）；``multi_agent_run``
  执行前会确保知识库引擎注入全局，使 RAGAgent 能真正检索。
- 修复 RAG 检索会把不相关的低分片段当作"知识库命中"展示的问题：底层检索阈值
  （SIMILARITY_CUTOFF=0.3）为保护"知识库里有什么"等元查询而故意调低，会带回语义
  几乎无关的片段（如问"某产品售价"却召回讲 Cloudflare 配置、相似度仅 0.398 的
  片段）。现在问答编排层新增独立的"知识库相关性阈值"（`KB_RELEVANCE_THRESHOLD`，
  默认 0.45），低于该分数的片段会被过滤：不计入引用来源、不进综合 prompt，从而
  正确回退到网络/模型回答，避免答非所问。该阈值不改变底层检索召回，元查询不受影响。
- 修复 Web 多 Agent 协作模式对"通用问题"（不含代码/测试/文档/检索/审计等关键词，
  如"某产品售价"）点击发送后无输出的问题：此类问题会被分解为通用任务，但此前无
  任何 Agent 声明可承接，调度阶段报"无可用 Agent"并返回空结果。现让 RAGAgent
  作为默认兜底承接通用任务，且其检索改为调用真实知识库引擎（此前返回硬编码占位
  文本），使多 Agent 模式能对通用问题给出真实答案。
- 修复 Web 对话点击"发送"后长时间无反馈、看似"没有效果"的问题：RAG 开启联网搜索
  或 Agent 任务往往耗时数十秒，此前界面在此期间无任何提示。现改为流式响应，点击
  后立即显示"处理中"占位，并实时展示网络搜索、综合、执行步骤等进度。
- 修复打包版从托盘"打开 Web UI"时浏览器打开但服务未启动的问题：直接以
  `subprocess.Popen` 复用打包可执行体启动 Web 子进程时，子进程会继承 PyInstaller
  注入的 `_MEIPASS2` / `_PYI_*` 等环境变量导致 bootloader 误判、无法启动。现在启动
  Web 子进程时会剔除这些变量，使其作为独立打包进程正常启动。
- 托盘"打开 Web UI"改为轮询等待服务端口就绪后再打开浏览器（此前固定等待 2 秒），
  避免在打包首启（需先做 Ollama 引导与索引加载）时打开空白/无法连接的页面。

## [v0.0.13] - 2026-07-20

### 新增
- 桌面托盘菜单新增"打开 Web UI"选项：以独立子进程启动 Web 界面并自动打开浏览器；
  已在运行时不重复启动、直接打开浏览器；退出托盘时会一并终止 Web 子进程，避免残留
  孤儿进程占用端口。

## [v0.0.12] - 2026-07-20

### 新增
- 新增基于 Gradio 的 Web 界面设计方案文档
  （`docs/future-feature-design/WEB_UI_GRADIO_DESIGN.md`），规划对话问答、知识库
  管理、Agent 执行可视化、会话管理与知识图谱可视化等功能，并给出复用现有引擎的
  接口清单与分阶段实施计划。
- 新增基于 Gradio 的本地 Web 界面（`src/web/`），提供"对话 / 知识库 / 会话 /
  知识图谱"四个标签页：对话支持 RAG 检索、单 Agent、多 Agent 协作三种模式并展示
  引用来源与执行过程；知识库支持上传文档、查看统计与清空索引；会话支持新建与列表；
  知识图谱支持实体查询。默认仅绑定 `127.0.0.1:7860`，数据不出本机，符合隐私优先
  原则。
- 启动器新增 `--web` 参数（`Cerebro --web`）用于启动 Web 界面，启动前会自动完成
  Ollama 环境检测引导。

### 改进
- Web 界面退出更干净：`launch()` 改为非阻塞启动 + 统一的阻塞等待，收到 Ctrl+C
  或进程退出时会主动关闭 Gradio 服务器并释放端口，避免残留孤儿进程占用 7860 端口。

## [v0.0.11] - 2026-07-20

### 改进
- 知识图谱降级为文档入库的派生索引：`/add` 文档入库成功后会自动同步构建知识
  图谱，无需再手动执行 `/graph-build`。入库后提示相应改为"已同步更新知识图谱"，
  仅在自动构建失败时才提示可用 `/graph-build @<文件路径>` 手动补建。
- `/graph-build` 重新定位为手动/调试/补建入口，帮助文案同步说明常规入库已自动建图。
- 知识图谱构建器新增 `rebuild_from_documents()`，支持从文档集合全量重放重建图谱，
  消除增量累积导致的漂移。

### 修复
- 修复 `KnowledgeGraphBuilder.clear()` 默认会把空图写回磁盘、导致持久化图谱数据
  被永久抹除的缺陷：`clear()` 默认不再落盘，仅在显式 `clear(persist=True)` 时才
  同步清空磁盘文件。
- 清理 `/graph-*` 与 `/db-*` 命令在命令解析中的重复注册。

## [v0.0.10] - 2026-07-20

### 修复
- 修复 /ask 联网信息丢失与打包 justext 缺失，/generate-skills 改用 OpenCode+Claude

## [v0.0.9] - 2026-07-07

### 修复
- `/ask` 联网明明搜到答案却回答"无法确定"：`run_web_search` 此前只取首个有效
  查询的结果，会丢弃其余查询——而搜索规划常同时给出中文与英文查询，二者召回差异
  很大（如价格类问题中文页摘要已含"2998 元"，英文页却没有）。现改为合并所有查询
  结果并按 URL 去重，最大化把含答案的摘要送入回答
- `/ask` 网页正文增强只提取第 1 个结果页且截断到 1000 字，导致排名靠后的含答案
  页面（价格常出现在第 3/4 名的中文页）被漏掉。现改为提取前 3 个高排名页面、每页
  保留至 2000 字
- 打包后网页提取报 `No such file or directory: '.../justext/stoplists'`：
  PyInstaller spec 将 trafilatura 的传递依赖 `justext` 也纳入 `collect_all`，
  随包打入其语言停用词表数据文件（此前仅会静默回退到 BeautifulSoup 并污染日志）
- `/generate-skills` 报"没有找到可分析的文档"：读取端写死相对路径
  `./index_storage/chroma_db`（按 cwd 解析），与 `/add` 写入端的绝对路径
  （`config.VECTOR_DB_PATH`）错配，`/cd` 后或从非项目根运行会读到被静默新建的
  空库。改用统一的 App 数据目录基准，并在集合缺失/为空时给出明确提示

### 改进
- `/generate-skills` 改为面向更主流的 **OpenCode 与 Claude** 平台（原为较小众的
  Devin + OpenCode），且通用型与项目专用型文档**统一都生成全部平台**的 skill
  （此前项目专用型写死只出单平台）。输出目录：通用型写入
  `~/.config/opencode/skills` 与 `~/.claude/skills`；项目专用型写入 App 数据目录
  基准下的 `.opencode/skills` 与 `.claude/skills`。帮助文案由"转化为 Devin Skills"
  改为通用的"转化为 Skills"
- 统一项目数据目录基准：所有 App 自身数据（向量库、快照、知识图谱、文件元数据、
  生成的 skills 等）一律以"已安装 App 数据目录"为默认基准的**绝对路径**写入，
  与运行时工作目录（cwd）彻底解耦——`/cd` 或从非项目根启动不再导致数据漂移
  - `runtime_paths.cwd_data_dir` 源码运行时也基于 `user_data_dir()`（项目根），
    不再返回相对 cwd 的路径
  - `knowledge_snapshot` 向量库路径改用 `config.INDEX_DIR`，与写入端同一来源
  - `knowledge_to_skills` 项目专用型 skill 不再写到 `Path.cwd()`，统一落到
    App 数据目录基准（通用型仍写入各工具全局约定位置，如
    `~/.config/opencode/skills`、`~/.claude/skills`）
  - `desktop_app` 去掉源码分支的写死相对 `..` 路径，统一用 `config_dir()/logs_dir()`
  - 相关 CLI 默认参数（`--index-dir`/`--output-dir`/`--snapshot-dir`）改为走内部
    统一基准

## [v0.0.8] - 2026-07-06

### 修复
- `/ask` 检索为 0 且答非所问：
  - 相似度阈值 `SIMILARITY_CUTOFF` 由 `0.4` 下调至 `0.3`，避免元/概览类查询
    因语义分数偏低（实测约 0.39）被全部过滤
  - "知识库里有什么/列出文件"等元问题直接返回知识库概览（文件列表 + 统计），
    不再走向量检索、不再联网，从根源杜绝答非所问
- `launcher.py` 补 `multiprocessing.freeze_support()`：修复打包环境下多进程子进程
  重执行入口导致的 `unrecognized arguments ... resource_tracker` 报错
- 打包后网页提取报 `No option 'download_timeout' in section: 'DEFAULT'`：
  - PyInstaller spec 将 `trafilatura` 改用 `collect_all` 完整收集，随包打入其
    `settings.cfg` 数据文件
  - `ContentExtractor` 为 `trafilatura.fetch_url` 显式传入健壮配置并补齐关键
    默认项，即使 `settings.cfg` 缺失或用户配置损坏也不再崩溃（旧版本无 `config`
    参数时自动回退）
  - `requirements*.txt` 将 `trafilatura` 下限提升至 `>=2.0.0`（`<2.0` 存在
    配置缺项问题）

### 改进
- `/ask` 回答策略：知识库检索内容与网络搜索结果**分区标注、综合总结**，明确区分
  来源；知识库 0 命中时不再把网络结果冒充成知识库回答，并显式声明来源
- 新增网络来源结构化展示（标题 + 链接），`/sources` 同时列出知识库来源与网络来源

## [v0.0.7] - 2026-07-06

### 发布流程
- `bump_changelog.py`：`[Unreleased]` 为空时按 Conventional Commits 从上一个版本 tag 到本次 tag 的提交自动生成变更内容，发布不再因空区段中断；新增 `--since/--until/--no-git-fallback` 参数，存在人工记录时仍优先采用
- 为 changelog job 添加 `pull-requests` 写权限，修复归档 PR 创建失败
- pip-audit 安全门禁忽略不适用于本项目的 `CVE-2026-12243`（nltk 路径穿越，仅为 llama-index 传递依赖且从不以用户可控输入调用其资源加载 API，上游暂无修复版本），修复 CI/PR 门禁误报失败

## [v0.0.6] - 2026-06-25

### 新增
- 知识图谱自动持久化，修复跨会话查询丢失
- `/graph-query` 支持按类型/邻居/路径查询并优化用法说明

### 修复
- `/web-cache clear` 走交互确认，不再泄露 `[CONFIRM_REQUIRED]` 协议串
- 补上 `/git-analyze` 与 `/git-commit-gen` 处理器，修复静默无输出
- `/graph-query` 关系类型转回枚举，修复 `'str' has no attribute 'value'`
- `/graph-build` 直接可用，不再甩锅给 Agent
- 文档入库时登记文件元数据，修复 `/file-list` 永远为空
- 原子化写入快照并自动清理损坏文件

### 改进
- `query_interface` 命令表驱动调度并拆分模块
- web search 改为 LLM 驱动的通用查询规划

## [v0.0.5] - 2026-06-25

### 新增
- README 顶部新增 CLI 三模式演示 GIF 与桌面应用演示 GIF
- 新增演示 GIF 生成脚本 `docs/assets/demo_script.sh`

### 改进
- 优化 README 首屏：居中布局、项目定位副标题、徽章、四大卖点与快捷导航
- CLI 启动 banner 改用 Cerebro ASCII 艺术字，与 README/演示 GIF 视觉统一
- 纯文本（无 Rich）环境的 banner 保留 `Cerebro` 产品名，提升可读性

### 发布流程
- Release Notes 改为从 CHANGELOG 提取当前版本正文（关闭 GitHub 自动 PR 汇总），使发布说明与 CHANGELOG 内容一致；未归档时回退提取 `[Unreleased]`
- Release 正文末尾保留「完整对比」链接（自动计算上一个版本 tag）

## [v0.0.4] - 2026-06-24

### 发布流程
- 重写 CHANGELOG 对齐真实发布标签（v0.0.1 ~ v0.0.3）
- Release Notes 改为由 GitHub 自动汇总 commit/PR，并附固定安装说明
- Release 流程新增版本号一致性校验（tag 与手动输入对齐）
- 新增 `scripts/bump_changelog.py`，支持归档 `[Unreleased]` 与提取版本正文
- 发布时（推送 `v*` tag）自动归档 CHANGELOG 并创建 PR，由人工审核合并到 `master`

## [v0.0.3] - 2026-06-24

### 新增
- 新增 `AGENTS.md`，定义强制性的 Git 工作流规则（禁止直接提交 master、改动前确认分支、完成后确认 PR）

### 修复
- 修复打包后应用在知识库未初始化时执行 `/ask` 导致崩溃的问题
- 打包模式下将运行时数据路径统一收敛到用户数据目录，避免写入只读的应用目录

## [v0.0.2] - 2026-06-24

### 修复
- 修复打包后应用的 GUI 启动卡死与 Ollama 检测失败问题
- 修复 macOS 应用包版本号未与 `APP_VERSION`（发布 tag）同步的问题

### 改进
- 将版本号嵌入 Windows exe 与 Linux AppImage 的元数据中

## [v0.0.1] - 2026-06-23

### 新增
- 首个公开发布版本：本地 RAG + 代码助手（基于 Ollama `qwen2.5-coder`）
- 三平台桌面安装包：Windows 安装器、macOS DMG、Linux AppImage
- 完整的发布流程（GitHub Actions：推送 `v*` tag 自动构建并发布到 Release）

### 修复
- 修复 CI/CD 流水线中的构建与测试任务失败问题
- 移除 `desktop_app.py` 中 `subprocess.Popen` 的 `shell=True`，消除 bandit HIGH (B602) 告警

### 安全
- 在依赖审计中忽略 chromadb 的 CVE-2026-45829（项目未启用 `trust_remote_code`，且暂无修复版本）

---

## 版本号规则

- **主版本号（MAJOR）**：包含不兼容的重大架构变更
- **次版本号（MINOR）**：向后兼容的新功能
- **修订号（PATCH）**：向后兼容的缺陷修复

## 发布说明

每次发布由推送 `v<MAJOR>.<MINOR>.<PATCH>` 标签触发，GitHub Actions 会自动：

1. 解析标签得到版本号（并校验语义化版本格式）
2. 并行构建 Windows / macOS / Linux 三平台安装包
3. 汇总产物并创建 GitHub Release（从 CHANGELOG 提取本版本正文作为 Release Notes + 安装说明 + SHA256 校验和 + 完整对比链接）
4. 自动归档 CHANGELOG：把 `[Unreleased]` 归档为该版本号，提交到新分支并创建 PR

> Release Notes 的「本次变更」来自 CHANGELOG 当前版本区段（若发布时尚未归档则取 `[Unreleased]`），
> 因此请在发布前把变更写清楚，确保 Release 页面展示与 CHANGELOG 一致。

平时把变更写入 `[Unreleased]` 区段即可；发布时归档由 CI 自动完成，
生成的 PR 需人工审核后合并到 `master`。也可在本地手动归档预览：

```bash
# 预览归档结果（不写文件）
python scripts/bump_changelog.py bump --version 1.0.0 --dry-run
# 实际归档
python scripts/bump_changelog.py bump --version 1.0.0
```
