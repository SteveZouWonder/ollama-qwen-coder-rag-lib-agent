# F10: 工程加固与体验升级（安全 · 发布 · 流式 · 后端抽象 · 评测 · 规模化 · 拆分）

## 实施状态

**进行中**（P0-1 / P0-2 已完成 2026-09-09；其余六项待实现） · 立项 2026-09-08 · 分支 `docs/f10-hardening`
· 目标：针对项目评估发现的 7 类结构性问题，按"用户可感知价值 × 复杂度"分 P0–P3 八个独立任务逐项落地

| 编号 | 主题 | 价值 | 复杂度 | 依赖 | 状态 | 完成日期 | 提交 |
|---|---|---|---|---|---|---|---|
| P0-1 | 命令安全分级修正（token 级匹配）· 读路径边界 · `AUTO_CONFIRM` 不放行 high · 两端显示允许目录 | 高 | 低 | — | **已完成** | 2026-09-09 | 见下方实现记录 |
| P0-2 | 依赖钉版本 + `requirements-dev.txt` · CI PR 触发 + 三平台矩阵 · CHANGELOG 归档 v0.1.0 | 高 | 低 | — | **已完成** | 2026-09-09 | 见下方实现记录 |
| P1-1 | 真流式输出（Ollama NDJSON → Web token 事件 / CLI rich Live）· `LLM_STREAM` 开关 · 可中断 | 高 | 中 | — | 待实现 | | |
| P1-3 | RAG 评测集（≥30 例 + 小语料）· `src/rag_eval.py` 指标 · `scripts/eval_rag.py` 报表与 Δ | 中 | 中 | — | 待实现 | | |
| P1-2 | `src/llm_client.py` 后端抽象（Ollama / OpenAI 兼容）· 五处直连替换 · 模型列表 / 健康检查 | 中 | 中高 | P1-1 | 待实现 | | |
| P2-1 | BM25 持久化增量（`bm25_store`）· 混合检索关闭可见 · RLock 补齐 · Ollama 并发信号量 | 中 | 中高 | P1-2 / P1-3（可选） | 待实现 | | |
| P2-2 | 入口层拆分：`web/services/`、`web/handlers/` + `formatters.py`、`cli/handlers/` + `cli/parser.py`（纯重构） | 低（间接） | 高 | P1 全部合入 | 待实现 | | |
| P3-1 | Tesseract 跨平台探测与缺失提示 · README 瘦身到 ≤400 行 | 低 | 低 | — | 待实现 | | |

## 文档导读

| 文件 | 内容 | 适合 |
|---|---|---|
| [REQUIREMENTS.md](REQUIREMENTS.md) | 需求分项与验收标准；§0 为立项时核实的代码事实（带 `文件:行号`，按问题分 8 小节）；§5 两端规范；§6 实施顺序 | 了解"要做什么、为什么" |
| 本文件 | 实现记录（每项做了什么、落在哪个模块）、与需求的差异、验证结果、性能前后对比 | 了解"实际做成了什么" |
| [PROMPT.md](PROMPT.md) | 交给 Agent 的启动提示词，按八个任务分段、各自可独立粘贴 | 分批派发实现任务 |

用户可感知的变更同步记录在 [CHANGELOG.md](../../../CHANGELOG.md) `[Unreleased]` 与主 [README](../../../README.md) 对应段落。

## 立项背景

2026-09-08 对项目做整体评估（架构 / 代码规模 / 工程质量 / 依赖 / 安全 / 可扩展性），归纳出 7 类问题：

| # | 问题 | 用户可感知影响 | 对应任务 |
|---|---|---|---|
| 1 | 入口层 5 个文件 1400–2700 行，Web / CLI 双份呈现层 | 改一端漏一端；定位成本高 | P2-2 |
| 2 | 只支持 Ollama `/api/chat`；全部调用非流式，Web 为线程 + 心跳伪流式 | 长回答全程只见"思考中"；无法接入 vLLM / LM Studio / 内网网关 | P1-1、P1-2 |
| 3 | 命令安全靠子串黑名单（`"rm" in cmd`）；读操作无路径边界；`AUTO_CONFIRM` 可绕过 high | `pip show models` 被判高风险弹确认；可读工作区外任意文件 | P0-1 |
| 4 | BM25 每次全量拉取重建；`lock = None`；多 Agent 并行打爆单卡 Ollama | 大库入库卡顿、>2 万块静默降级、并行超时 | P2-1 |
| 5 | 依赖几乎未钉版本；104 条变更未发版；CI 单平台、仅 push master | 新用户安装失败；两个月成果无安装包 | P0-2 |
| 6 | 无 RAG 评测集；ReAct / rerank / 分解全靠 4B 模型结构化输出 | 改阈值后质量回归不可见 | P1-3 |
| 7 | Tesseract 路径 macOS 硬编码；README 1322 行 | Linux / Windows OCR 路径错误；新用户找不到入口 | P3-1 |

排序原则：两端共有的功能性缺陷（3、5）> 影响主路径的体验（2、6）> 规模化与可维护（4、1）> 收尾（7）。详细事实与行号见 [REQUIREMENTS.md §0](REQUIREMENTS.md#0-背景已核实的代码事实实施时勿重复调研)。

## 实施顺序

```
P0-1 安全分级 → P0-2 钉版本 + 发版 + CI
P1-1 真流式 → P1-3 RAG 评测（先建基线）→ P1-2 后端抽象
P2-1 BM25 + 锁 + 限流 → P2-2 入口层拆分
P3-1 Tesseract + README
```

## 实现记录

### P0-1 命令安全分级修正 + 读路径边界（2026-09-09）

| 子项 | 实现位置 | 做了什么 |
|---|---|---|
| P0-1-a token 级匹配 | `src/agent_tools.py` `CommandSafetyChecker` | 新增分词与判定纯函数：`_tokenize`（`shlex.shlex(posix=True, punctuation_chars=True)`，`ValueError` 回退 `re.split(r"\s+")`）、`_split_subcommands`（按 `|` `||` `&&` `;` `&` 切分）、`_head`（剥 `TRANSPARENT_PREFIXES` = sudo/doas/env/xargs/nohup/time/command/builtin/exec/nice/ionice 及其带值选项 `PREFIX_FLAGS_WITH_VALUE`、跳过 `VAR=value`、取 basename 转小写）、`_sql_risk`、`_subcommand_risk`（含 `-c`/`-e` 载荷递归，深度 ≤2）、`keyword_risk`、`is_readonly_command`。关键字集合：`HIGH_COMMANDS`（rm rmdir del erase rd drop truncate format mkfs shred）、`MEDIUM_COMMANDS`（mv cp chmod chown tee dd）、`MEDIUM_COMMANDS_WITH_FLAG`（`sed` + `-i`）、`SQL_CLIENTS` / `SQL_HIGH_KEYWORDS` / `SQL_MEDIUM_KEYWORDS`。`analyze` 中两处 `kw in command.lower()` 替换为 `keyword_risk()`；只读判定改为「全部子命令都命中 `READONLY_PATTERNS`」。`DANGEROUS_PATTERNS` / `HIGH_PATTERNS` / `MEDIUM_PATTERNS` / `READONLY_PATTERNS` 一字未改。 |
| P0-1-b 读边界 | `src/agent_tools.py`、`src/config.py` | 新增 `READ_ALLOWED_DIRS_ENV`、`read_allowed_dirs()`（写允许目录 ∪ `READ_ALLOWED_DIRS` ∪ `_indexed_document_dirs()`）、`is_read_allowed()`、`read_scope_error()`；抽出 `_normalize_dirs()` / `_within()` 供读写共用（`is_path_allowed` 改为复用）。`read_file` / `list_directory` / `search_files` 在 `expanduser` 后立刻校验。`config.py` 新增 `READ_ALLOWED_DIRS` 常量与 `Config.READ_ALLOWED_DIRS`。三个工具描述末尾加「（仅限允许目录）」。 |
| P0-1-c AUTO_CONFIRM 降权 | `src/agent_tools.py`、`src/react_engine.py`、`src/query_interface.py`、`src/cli_handlers.py`、`src/agents/base_agent.py` | 共享层新增 `AUTO_CONFIRM_RISK_LEVELS = ("low","medium")`、`HIGH_RISK_CONFIRM_HINT`、`auto_confirm_allows(safety)`（`safety` 为空 → True，`is_dangerous` → False）。`react_engine` 确认分支与 `registry.execute` 的 `auto_confirm` 均经该闸门；`query_interface.handle_exec` 同理并在 AUTO_CONFIRM 下打印提示；`cli_handlers._confirm` 增加 `safety=` 形参（默认 None，行为不变），`handle_db_execute` 经新增的 `_sql_safety(sql)` 传入；`base_agent.AUTO_CONFIRM_RISK_LEVELS` 改为引用共享常量，消除两处漂移。 |
| P0-1-d 两端展示 | `src/cli_handlers.py`、`src/query_interface.py`、`src/web/services.py`、`src/web/app.py` | 新增 CLI `/config`：`config_rows()`（纯函数，返回 `(标签, 值)` 列表）+ `handle_config`，注册进 `COMMAND_HANDLERS["config"]`、`parse_command` 与 `classify_mode`；同步 `print_help` 与 `TUTORIAL_TEXT`。Web：`WebService.env_info()` 增加 `read_allowed_dirs` / `write_allowed_dirs`，`format_env_info` 增加「允许读目录 / 允许写目录」两行（新增 `_fmt_dir_list`，超 6 个折叠），自动确认一行改为「开（只放行 low / medium）」。 |
| P0-1 后续（同日第二次提交）| `src/agent_tools.py`、`src/web/services.py`、`src/web/app.py`、`.flake8` | **读边界补全两端**：`analyze_project_structure` / `ast_search` / `code_quality_check` / `git_analyze` / `git_commit_gen` 接 `is_read_allowed`；Web 新增 `WebService.path_read_error(path)` 复用同一判定，约束 `list_dir` / `file_preview` / `search_in_dir` / `code_symbols` / `code_quality_report` / `graph_build_file` / `code_assist_stream`；`app.on_dir_search` 越界先报错（`search_in_dir` 无 error 槽位，否则会伪装成"未找到"），`on_file_edit_load` 越界不再提示"保存将创建新文件"。**允许目录收敛**：`_normalize_dirs` 丢弃被包含的子目录；`_indexed_document_dirs` 把 Gradio 上传根（`$GRADIO_TEMP_DIR` / `<tmp>/gradio`）下的哈希目录折叠为根一条。**守卫测试**：真实 registry 下 high 命令确认一次即执行一次（不再二次 `[CONFIRM_REQUIRED]`）。**flake8**：`.flake8` 的 `ignore` 行内注释导致 flake8 根本跑不起来（`ValueError`），移到独立行；顺手删掉 5 处只读的死 `global` 声明（F824），为 P0-2-b 的阻断门禁留出干净基线。 |

### P0-2 依赖钉版本 + 归档发版 + CI 矩阵（2026-09-09）

| 子项 | 实现位置 | 做了什么 |
|---|---|---|
| P0-2-a 钉版本 | `requirements.txt`、`requirements-build.txt`、**新增** `requirements-dev.txt` | 以当前 venv 的 `pip freeze` 为准，把 `requirements.txt` 的 28 个直接依赖全部改为 `==`（原先仅 2 处 `==`、4 处下限约束、其余裸包名）；可选依赖（sentence-transformers / tree-sitter-language-pack / OCR）在注释的安装命令里同样写明版本。`requirements-build.txt` 逐项对齐同一批版本（另含 `tree-sitter-language-pack==1.16.2`、`pyinstaller==6.21.0`、`pefile==2024.8.26; sys_platform == "win32"`）。测试 / lint 依赖移入 `requirements-dev.txt`（`-r requirements.txt` + pytest 9.0.3 / pytest-cov 7.1.0 / pytest-xdist 3.8.0 / flake8 7.3.0 / pylint 4.0.5 / bandit 1.9.4 / pip-audit 2.10.1）。 |
| P0-2-a 安全兜底 | 同上 | 直接冻结本地版本会把 51 条**已有修复版**的漏洞钉进仓库（此前依赖不钉版本，CI 每次装最新反而没有）。因此先把 `setuptools 82.0.1 → 84.0.0`、`gitpython 3.1.50 → 3.1.62`、`pillow 12.2.0 → 12.3.0` 升级后再冻结；`pypdf` 本地为 6.13.3、低于原约束 `>=6.15`（Dependabot 升过但本地没装），一并升到 6.18.0 再钉。 |
| P0-2-a 脚本同步 | `scripts/verify_deps.sh`、`scripts/install_deps.sh`、`scripts/install_deps.ps1`、`Makefile`、`README.md` | `verify_deps.sh`：抽出 `verify_requirements_file()`，跳过 `-r` 引用行，分「运行时」「开发/测试」两段校验（原来测试工具是硬编码三行）。`install_deps.sh` / `.ps1`：numpy/pandas 预装改为从 `requirements.txt` 读钉版本（原来裸装再被覆盖）；OCR 依赖改用 `pytesseract==0.3.13 opencv-python==4.13.0.92`（顺带修掉 `.ps1` 里 `pymupdf>=1.25.0` 中 `>` 被 PowerShell 当重定向符的 bug）；新增「是否安装开发/测试依赖」一步。`Makefile` 拆出 `install` / `install-dev` / `test`，`build` 依赖 `install`（`pr-build-vulnerability-gate.yml` 的 `make build` 行为不变）。README「2. 安装依赖」加三份依赖清单的分工表与升级流程说明，项目结构树补两个新文件。 |
| P0-2-b CI | `.github/workflows/ci.yml` | 加 `pull_request: branches: [master]` 触发；`build-and-test` 改 `runs-on: ${{ matrix.os }}`，矩阵 `os: [ubuntu-latest, macos-latest, windows-latest] × python 3.13`，`fail-fast: false`；安装步骤改为一条 `pip install -r requirements-dev.txt`（原来手写 `pip install flake8 pylint bandit pip-audit pytest pytest-cov`，版本随缘）；pip 缓存先用 `python -m pip cache dir` 解析平台缓存目录再 `actions/cache`，key 改 `hashFiles('requirements*.txt')`；flake8 拆成两步——`E9,F63,F7,F82` **阻断**、风格检查 `continue-on-error`；测试拆成 ubuntu（带覆盖率 + `coverage report --fail-under=80` + Codecov + artifact）与非 ubuntu（`-q --no-cov`）两步；pip-audit / 覆盖率 / artifact 上传均加 `matrix.os == 'ubuntu-latest'` 条件（避免 artifact 重名冲突）；所有 shell 步骤加 `shell: bash`。`security-scan` 作业与 CVE ignore 列表**一字未改**；`release.yml`、`pr-build-vulnerability-gate.yml` 未动。 |
| P0-2-c 归档 | `CHANGELOG.md`、`docs/features/ROADMAP.md` | `python scripts/bump_changelog.py bump --version 0.1.0 --date 2026-09-09` 把 `[Unreleased]` 的 **112 条**一级要点归档为 `## [v0.1.0] - 2026-09-09`（F8 / F9 为破坏性体验升级，按 minor 递增）；新 `[Unreleased]` 只写 P0-2 自身的「发布流程」4 条。ROADMAP「当前版本」由 v0.0.13 改为 v0.1.0。**未打 tag、未推送**，命令交由用户执行。 |

## 验证结果

### P0-2（2026-09-09）

| 项 | 结果 |
|---|---|
| 钉版本完整性 | `grep -cE '^[A-Za-z0-9_.-]+==' requirements.txt` → **28**；`grep -E '^[A-Za-z0-9_.-]+\s*$'` 无裸包名；非注释行全部含 `==` |
| `bash scripts/verify_deps.sh` | 运行时 23 项全 ✓（llama-index 插件包 / gitpython / opencv 按规则跳过），开发/测试 7 项全 ✓ |
| `pip-audit -r requirements.txt` | 升级三个包前 **51 条 / 5 包**；升级后 **5 条 / 2 包**（chromadb 4 条 + nltk 1 条），全部无修复版且已在 `ci.yml` ignore 列表中附理由。按 CI 原样带 ignore 参数运行 → `No known vulnerabilities found, 5 ignored`。**未新增任何 ignore** |
| `ci.yml` 语法 | `python -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml'))"` 通过；解析出 `on = {push: master, pull_request: master}`、`matrix.os = [ubuntu, macos, windows]` |
| 全量测试 | `./venv/bin/python -m pytest -q -n 4` → **3224 passed, 36 skipped**，覆盖率 **91.26%**（门禁 80%） |
| 归档 | `CHANGELOG.md` 出现 `## [v0.1.0] - 2026-09-09`，含 112 条一级要点；新 `[Unreleased]` 仅「发布流程」4 条 |

依赖版本差异（旧约束 → 新钉版本，仅列有变化的直接依赖）：

| 包 | 旧约束 | 新版本 | 备注 |
|---|---|---|---|
| setuptools | `>=60.0.0` | `==84.0.0` | 从 82.0.1 升级，修 PYSEC-2026-3447 |
| gitpython | `>=3.1.0` | `==3.1.62` | 从 3.1.50 升级，修 26 条 CVE/GHSA |
| pillow | 裸包名 | `==12.3.0` | 从 12.2.0 升级，修 19 条 PYSEC |
| pypdf | `>=6.15.0,<7` | `==6.18.0` | 本地实为 6.13.3（低于原约束），升级后钉版 |
| 其余 24 个直接依赖 | 裸包名 / 下限约束 | 冻结当前实测版本 | 见 `requirements.txt` |

> 未在干净 venv 里跑 `pip install -r requirements.txt -r requirements-dev.txt` 复装验证（约 2 GB 下载）；
> 已通过 `pip-audit -r requirements.txt` 的依赖解析间接确认全部钉版本可解，且 CI 三平台会在 PR 上做真实复装。

`git tag` 与推送命令（**待用户执行**）：

```bash
git tag -a v0.1.0 -m "v0.1.0: F8 Agent 模式优化 + F9 Web 工具页改版 + F10 P0 安全与依赖加固"
git push origin v0.1.0
```

### P0-1（2026-09-09）

| 项 | 结果 |
|---|---|
| 全量测试 | `./venv/bin/python -m pytest tests -q -n 4` → **3224 passed, 36 skipped**（第二次提交后） |
| 覆盖率 | **91.26%**（门禁 80%） |
| 新增测试 | **+100 个**（3159 → 3259 收集数；第二次提交 +20：`TestP01ReadBoundaryMoreTools`、`TestWorkspaceReadBoundary`、允许目录收敛 4 例、`test_high_risk_confirmed_once_executes_once`、Web handler 越界可见 2 例）。首次提交：`test_agent_tools_safety.py` +55（`TestP01TokenLevelGrading` / `TestP01AutoConfirmAllows` / `TestP01ReadBoundary` 三个新类）、`test_cli_handlers_database.py` +7（`TestP01AutoConfirmRiskGate`）、`test_cli_handlers_config.py` +6（新文件）、`test_query_interface_exec_safety.py` +6（新文件）、`test_react_engine.py` +2、`test_web_app.py` +2、`test_web_services.py` +1、`test_query_interface_parse.py` +1 |
| 无子串匹配 | `grep -n 'in command.lower()' src/agent_tools.py` → 无输出（并有 `test_no_substring_matching_left` 守卫） |
| CLI `/config` | 终端输出见下（第二次提交后允许读目录由 4 条收敛为 3 条：两个 gradio 哈希目录折叠为 `…/T/gradio`） |
| flake8 语法门禁 | `flake8 --select=E9,F63,F7,F82 src tests` → rc=0（此前配置错误无法运行） |
| Web 系统页 | 「运行环境」渲染见下 |

CLI（`READ_ALLOWED_DIRS=~/Documents`）：

```
模型: qwen3.5:4b
Ollama 地址: http://localhost:11434
自动确认: 关
自动路由: 开
工作目录: /Users/steve/PycharmProjects/ollama-qwen-coder-rag-lib-agent
允许读目录: /Users/steve/PycharmProjects/ollama-qwen-coder-rag-lib-agent : /Users/steve/Documents : /private/var/folders/.../T/gradio
允许写目录: /Users/steve/PycharmProjects/ollama-qwen-coder-rag-lib-agent
数据目录: /Users/steve/PycharmProjects/ollama-qwen-coder-rag-lib-agent/data
索引目录: /Users/steve/PycharmProjects/ollama-qwen-coder-rag-lib-agent/index_storage
Agent 最大步数 / 超时: 50 / 300s
提示: 路径边界越界时工具返回 [错误] 路径超出允许范围，可用 READ_ALLOWED_DIRS / WRITE_ALLOWED_DIRS 放行
```

Web「系统 → 运行环境」（`format_env_info(WebService().env_info())` 实际输出，`CODE_AGENT_AUTO_CONFIRM=true READ_ALLOWED_DIRS=~/Documents`）：

```
| 自动确认（环境变量） | 开（只放行 low / medium） |
| 工作目录 | `…/ollama-qwen-coder-rag-lib-agent/src` |
| 允许读目录 | `…/src` · `/Users/steve/Documents` · `/private/var/folders/…/gradio/bce86ed6…` · `/private/var/folders/…/gradio/bf6e094d…` |
| 允许写目录 | `…/ollama-qwen-coder-rag-lib-agent/src` |
```

> 浏览器截图未提交：本次在无头环境实现，用 service → formatter 的真实渲染输出替代（系统页即 `gr.Markdown(format_env_info(...))`，无额外交互逻辑）。

## 与需求的差异

### P0-1

| # | 需求 | 实际 | 原因 |
|---|---|---|---|
| 1 | 「原有测试全部不改断言」 | 改了 4 条 | 这 4 条恰好编码了被移除的子串行为，与 P0-1-a 互斥：`write_file test.py content` / `insert into table` / `update table set` 由 medium 改为 **low**（首 token 不是修改类命令，也无 SQL 客户端上下文），`python rm_all.py` 由 high 改为 **medium**（正是 §1 点名的误报）。改动处均写明原因，其余断言一字未动；另给 `TestReadFile` / `TestListDirectory` / `TestSearchFiles`、`TestAnalyzeProjectStructure`、Web 的 `TestCodeAssist` / `TestCodeSymbolsAndQuality` / `TestWorkspaceBrowse` 加了设置 `READ_ALLOWED_DIRS` 的 autouse fixture（**只加 fixture，不改断言**，沿用 P1-7 给 `TestWriteFile` 加 `WRITE_ALLOWED_DIRS` 的先例）；第二次提交把 3 处用绝对越界路径测"不存在"的**参数**改到允许目录内（`/nonexistent/path` → `temp_dir/nonexistent`、`/nope/x.txt` → `tmp_path/nope.txt`），断言文本不变，并给 `list_dir("/")` 用例追加了一条越界 error 断言。 |
| 2 | medium 集含 `tee`、`dd`、`sed -i` | 同需求；SQL medium 集扩到 `alter` / `replace` | 与 `insert/update/delete` 同类的写操作，漏掉会留缺口。 |
| 3 | 透明前缀「`sudo` / `env VAR=`」 | 扩到 `doas xargs nohup time command builtin exec nice ionice` 及其带值选项 | §1 验收要求 `ls | xargs rm` → high，仅剥 sudo/env 做不到；带值选项（`sudo -u root rm x`）不剥会把选项值当命令名。 |
| 4 | SQL 关键字「首 token 为客户端或命令含 `-c`/`-e`」 | 另对 `-c`/`-e` 的载荷递归做首 token 判定（深度 ≤2） | 否则 `bash -c 'rm -rf build'` 判 low。 |
| 5 | 只读判定 | 由「任一 `READONLY_PATTERNS` 命中」改为「全部子命令命中」 | `ls | xargs rm` 会被 `^ls` 提前判 low，无法满足验收要求的 high。需求未提及此处，但不改无法达成验收。 |
| 6 | 「CLI `/config` 增加两行」 | **新建** `/config` 命令 | 该命令原本不存在（§0.2 的 `query_interface.py:1517` 实际指向 `/model` 无参输出的「自动确认」行）。经确认新建 `/config`，一并显示模型 / 自动确认 / 数据与索引目录等运行配置，与 Web「运行环境」对齐；`print_help`、`TUTORIAL_TEXT`、README 命令表同步。 |
| 7 | 未提及 | `react_engine` 的 `registry.execute` 增加 `or step_record["confirmed"] is True` | 闸门收紧后，high 命令经用户确认仍会被 registry 二次索要确认（`[CONFIRM_REQUIRED]`）。加此条保持「确认一次即执行」，不引入新的免确认路径。 |
| 8 | 未提及 | CLI `/file <path>` 一并受读边界约束 | 经确认：用户显式命令与 Agent 同一边界，无绕过口；README 与 `print_help` 说明可用 `READ_ALLOWED_DIRS` 放行。 |
| 9 | §1 只点名 `read_file` / `list_directory` / `search_files` | **扩到** `analyze_project_structure` / `ast_search` / `code_quality_check` / `git_analyze` / `git_commit_gen` 与 Web「工具」页 7 个直接读盘入口（第二次提交） | 首次提交后核实：Web 端 `services.py` 有 5 处直接 `open()` / `os.walk()` 完全绕过边界——Agent 读 `~/.ssh` 被拦，Web 工作区输入同一路径却能预览，违反 AGENTS.md "禁止只修一端"。`database_connect` 的 SQLite 路径仍未接边界（数据库工具另有 `safe` 标记），记为待办。 |
| 10 | 需求"已入库文件所在目录" | 落在 Gradio 上传根下的目录折叠为根一条；被包含的子目录不列 | 每个 Web 上传文件都在独立哈希目录，逐条列出会让 `/config` / 系统页随入库数增长；上传根下都是用户自己上传的内容，放行整个根不扩大风险面。 |
| 11 | 本次未要求 | 修 `.flake8` 配置 + 删 5 处死 `global` | flake8 因 `ignore` 行内注释根本跑不起来；P0-2-b 要把它改为阻断门禁，先给出干净基线。属 P0-2 范围，提前做掉。 |

### P0-2

| # | 需求 | 实际 | 原因 |
|---|---|---|---|
| 1 | 「在当前 venv 用 `pip freeze` 取实际版本」 | setuptools / gitpython / pillow / pypdf 先升级再冻结 | 直接冻结本地版本会把 **51 条已有修复版**的漏洞钉死在仓库里，反而比原先「不钉版本、CI 每次装最新」更差；`pypdf` 本地 6.13.3 还低于原约束 `>=6.15`（Dependabot 升过约束但本地没装）。四个包升到有修复的版本后再 `pip freeze`，`pip-audit` 从 51 条降到 5 条（全部无修复版）。 |
| 2 | 「pip 缓存 key 含 `hashFiles('requirements*.txt')`」 | 另加一步 `python -m pip cache dir` 解析缓存路径 | 原写死的 `~/.cache/pip` 只在 Linux 成立，macOS 是 `~/Library/Caches/pip`、Windows 是 `%LOCALAPPDATA%\pip\Cache`；上矩阵后不改会让另两个平台缓存永远 miss。 |
| 3 | 「覆盖率与 Codecov 仅 ubuntu 上传」 | 连同 pip-audit 步骤、`security-reports` / `coverage-reports` 两个 artifact 上传也限定 ubuntu | `actions/upload-artifact@v4` 同名 artifact 在三个平台并发上传会直接失败；pip-audit 是纯依赖扫描，跨平台重复跑无收益。 |
| 4 | 「flake8 改为阻断但只查 `E9,F63,F7,F82`，其余保持 `continue-on-error`」 | 拆成两个独立 step | 原来两条 flake8 命令在同一个 step 里、整个 step `continue-on-error: true`，「只让语法错误阻断」在单 step 内无法表达。 |
| 5 | 未提及 | `install_deps.ps1` 的 OCR 安装行由 `pymupdf>=1.25.0 opencv-python>=4.13.0` 改为 `==` 钉版本 | PowerShell 把 `>` 解析成输出重定向，原命令实际是写文件而不是装包（既有 bug）。钉版本顺带修掉。 |
| 6 | 「`Makefile` 同步」 | 拆出 `install` / `install-dev` / `test` 三个目标，`build` 依赖 `install` | `pr-build-vulnerability-gate.yml` 依赖 `make build`（本次不改该 workflow），必须保持其行为不变；新增目标只是补充入口。 |
| 7 | §0.3 称「PR 由 `pr-build-vulnerability-gate.yml` 跑构建 + pip-audit，**不跑测试**」 | 该 workflow 实际有 `test` job（跑 pytest + `coverage report --fail-under=80`） | 立项时的事实记录有误。因本次不改该文件，仅记录：合并后 PR 上会同时有 `ci.yml` 三平台测试与该 workflow 的 ubuntu 测试，存在重复执行，可在后续任务中合并。 |
| 8 | 未提及 | 三平台测试均为**阻断**（未加 `continue-on-error`） | 按需求原文实现。风险：测试套件此前从未在 macOS / Windows 跑过，首次 PR 可能因路径分隔符 / 编码 / 文件锁等平台差异变红。若要先观察一轮，可给非 ubuntu 的测试步骤临时加 `continue-on-error: true`。 |
