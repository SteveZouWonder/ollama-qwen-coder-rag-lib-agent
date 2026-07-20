# 更新日志

本项目所有重要变更都记录在本文件中。

格式遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [Unreleased]

> 下一版本的未发布变更请记录在此区段。发布时将其移动到对应的版本号下。

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
