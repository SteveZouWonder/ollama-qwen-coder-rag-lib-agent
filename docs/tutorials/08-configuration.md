# 配置参考：config.py、环境变量、LLM 后端与模型选择

> 本文汇集 README 中迁出的配置类章节（F10 P3-1，2026-09-09）。日常最常用的环境变量速查表仍在
> [README《环境变量表》](../../README.md#环境变量表)；这里是 `config.py` 常量的带注释版与背景说明。

---

## 配置说明（config.py）

编辑 `config.py` 或通过环境变量：

```python
# 模型配置
LLM_MODEL = "qwen3.5:4b"            # 全局唯一 LLM（Agent/RAG/多 Agent 共用），见下方「模型选择指南」
LLM_THINK = False                   # 思考模式，默认关闭（4B 模型响应 31s → 2.8s）
LLM_STREAM = True                   # 真流式输出：最终答案逐字出现、可随时中断（首字 6.6s → 0.2s）
LLM_NUM_CTX = 自动                  # 按模型参数量推导（4B→16K，7~9B→8K，12B+→4K），可用环境变量覆盖
LLM_PROVIDER = "ollama"             # 对话后端协议：ollama（默认）| openai（vLLM / LM Studio / 内网网关，见「接入 OpenAI 兼容后端」）
LLM_BASE_URL = OLLAMA_BASE_URL      # 对话后端地址（openai 模式下带不带 /v1 均可）
LLM_API_KEY = ""                    # openai 模式的 Bearer 令牌，本地服务留空
LLM_REASONING_EFFORT = "none"       # openai 模式 + 思考关闭时随请求发送的 reasoning_effort（空串则不发送）
OLLAMA_MAX_CONCURRENCY = 2          # 进程内同时在途的 LLM 请求上限（多 Agent 并行时其余排队；0 不限制）
EMBED_MODEL = "nomic-embed-text"     # 嵌入模型（始终由 Ollama 提供）

# RAG 配置
CHUNK_SIZE = 1024                   # 分块大小
CHUNK_OVERLAP = 200                 # 分块重叠
TOP_K = 10                          # 检索片段数

# Agent 配置
MAX_ITERATIONS = 50                 # 最大迭代步数
TIMEOUT = 300                       # 模型超时
AUTO_CONFIRM = False                # 自动确认

# 🆕 多Agent配置
DEFAULT_COLLABORATION_MODE = "hierarchy"  # 默认协作模式
MAX_PARALLEL_TASKS = 5               # 最大并行任务数
TASK_TIMEOUT = 600                   # 任务超时（秒）
AGENT_TIMEOUT = 300                  # Agent执行超时（秒）
ENABLE_LOGGING = True                # 启用日志
LOG_LEVEL = "INFO"                   # 日志级别
```

环境变量方式：每个常量都可用同名环境变量覆盖（`LLM_MODEL`、`LLM_STREAM`、`OLLAMA_MAX_CONCURRENCY`、`READ_ALLOWED_DIRS` …），
各变量的默认值与说明见 [README《环境变量表》](../../README.md#环境变量表)。示例：

```bash
export LLM_MODEL="qwen3.5:9b" LLM_THINK=false LLM_STREAM=true
export CODE_AGENT_AUTO_CONFIRM=true READ_ALLOWED_DIRS=~/Documents
python query_interface.py --data ./data
```

---

## 接入 OpenAI 兼容后端

默认对话模型由本机 Ollama 提供。如果你已经有 **vLLM / LM Studio / llama.cpp server / 公司内网的 OpenAI 兼容网关**，
可以不装对话模型、直接让 Cerebro 复用它（F10 P1-2）：

```bash
# LM Studio（默认端口 1234；「Local Server」页启动后即可）
export LLM_PROVIDER=openai
export LLM_BASE_URL=http://localhost:1234        # 带不带 /v1 都行
export LLM_MODEL=qwen2.5-7b-instruct             # 后端里的模型 id（/v1/models 可查）

# vLLM
python -m vllm.entrypoints.openai.api_server --model Qwen/Qwen2.5-7B-Instruct --port 8000
export LLM_PROVIDER=openai LLM_BASE_URL=http://localhost:8000 LLM_MODEL=Qwen/Qwen2.5-7B-Instruct

# 内网网关（需要令牌）
export LLM_PROVIDER=openai LLM_BASE_URL=https://llm.corp.example LLM_API_KEY=sk-xxx LLM_MODEL=gpt-4o-mini

# 验证：Ollama 自带 /v1 兼容端点，可先用它跑通 openai 模式再换真实后端
export LLM_PROVIDER=openai LLM_BASE_URL=http://localhost:11434
python src/query_interface.py --query "知识库里有什么"
```

生效范围：ReAct Agent、多 Agent 协作、RAG 综合回答（LlamaIndex `OpenAILike`）、会话摘要压缩、AI 提交信息、
托盘预热与状态轮询。CLI `/config` `/model`、Web「系统」页会显示 `LLM 后端 / 后端地址 / 后端状态`；
`/model list` 读取后端 `/v1/models`，后端不提供时回退为当前模型并提示「后端未提供模型列表」（此时 `/model <name>` 可切到任意名字，不做校验）。

注意事项：

| 项 | 说明 |
|---|---|
| **嵌入仍需 Ollama** | 知识库入库 / 检索用的 `EMBED_MODEL`（默认 `nomic-embed-text`）始终走 `OLLAMA_BASE_URL`。只用 Agent 对话可以不开 Ollama；要用知识库就需要 `ollama pull nomic-embed-text`。启动引导会提示但不会安装。 |
| **`num_ctx` 由后端决定** | OpenAI 协议没有 Ollama 的 `num_ctx`，上下文窗口以后端启动参数为准（vLLM `--max-model-len`、LM Studio 加载时的 Context Length）。Cerebro 仍按模型名推导 `LLM_NUM_CTX` 只用于历史 / 片段的 token 预算，可用 `LLM_NUM_CTX` 对齐后端实际值。 |
| **思考模式** | 没有 `think` 字段。思考关闭（默认）时随请求发送标准字段 `reasoning_effort=none`（Ollama `/v1`、OpenAI 均识别；否则 qwen3.5 这类模型会把输出预算全部花在 reasoning 上、回答为空）；后端返回 400 不认识该字段时自动去掉重试并记住。可用 `LLM_REASONING_EFFORT` 改为 `low/medium/high` 或设空不发送。 |
| **模型切换 / 卸载** | `/model <name>` 只改全局模型名；「释放旧模型」「已加载 / 驻留大小」是 Ollama 专有能力，openai 模式下不显示。 |
| **options 映射** | `temperature` 直传，`num_predict → max_tokens`，其余 Ollama `options` 忽略。 |

---

## 模型选择指南（补充）

按场景推荐表与三种切换方式见 [README《模型选择要点》](../../README.md#模型选择要点)。

**小模型更容易"过度顺从"**（H-Neurons 研究，arXiv 2512.01797：<10B 模型接受错误前提、被反驳就改口的倾向明显更强，
且换 instruct 版本不能解决）。本项目在模型外围加了忠实性条款、引用程序化校验与结构化警示（见「模式一」的 F9 段），
但对**重要事实请务必**用 `/sources` 与回答后的 `🔎 引用 v/t 有效` 校验行核对，不要仅凭答案文字。
切换模型前后可用评测脚本对比抗过度顺从表现（需本机 Ollama，规则词表判定，不用 LLM 当裁判）：

```bash
./venv/bin/python scripts/eval_overcompliance.py --model qwen3.5:4b            # 30 例：错误前提 / 误导片段 / 被质疑 / 虚构实体
./venv/bin/python scripts/eval_overcompliance.py --model qwen3.5:9b --out /tmp/eval-9b.json -v
```

Web 界面：「系统 → 模型」页有**模型下拉**（或点击模型表格行），选择后点「切换模型」即时生效；旁边的**「思考模式」复选框**可随时开关（模型不支持时会自动回弹并提示）。顶栏胶囊始终显示当前模型、驻留情况、num_ctx 与思考模式。

### 与 IDE 共存的内存实践

- **思考模式默认关闭**（`LLM_THINK=false`）：ReAct 的 Thought/Action 已是显式推理，再叠加隐式思维链只会拖慢。同一问题 qwen3.5:4b 从 31s 降到 2.8s。需要深度推理时可**运行中开启**：CLI `/think on`、Web 勾选「思考模式」，或启动前 `LLM_THINK=true`。仅 `ollama show <model>` 的 Capabilities 含 `thinking` 的模型（qwen3.5 系列等）支持，`/think on` 会自动校验。
- **桌面应用默认不预热**（`warm_up_on_startup: false`）：预热会让模型常驻；Ollama 会在首问时按需加载，闲置 5 分钟后释放。内存宽裕可改回 `true` 换首问速度，或设 `OLLAMA_KEEP_ALIVE=2m` 更快归还内存。
- **上下文自动推导**：4B→16K，7~9B→8K，12B+→4K；每 +16K 约多占 0.6GB（4B 实测）。长文档任务可临时 `LLM_NUM_CTX=32768`。
- **避免双驻留**：Ollama 只在"放不下"时才驱逐旧模型，4B+9B 会被同时保留。项目的 `/model` 切换会主动释放旧模型；若曾用 `ollama run` 手动加载过其他模型，`/model` 会给出提示，用 `ollama stop <name>` 释放。

### 关注中（暂不推荐）

`SparkLLM/Spark-X2.5-4B` 在同尺寸模型中 Agent / 代码基准领先（BFCL 65、SWE-Bench Pro 44），
但官方 Ollama 尚不支持其 `spark2_5` 架构（llama.cpp [PR #27868](https://github.com/ggml-org/llama.cpp/pull/27868) 进行中），
目前需自编译运行时且仅有 8.2GB 未量化版本。待上游合入并提供量化 tag 后再评估。

---

## OCR 配置

在 `config.py` 中配置 OCR 功能（以下为默认值）：

```python
# OCR 开关
OCR_ENABLED = True  # 是否启用 OCR 功能
OCR_ENGINE = "tesseract"  # OCR 引擎：tesseract（默认，兼容 Python 3.13）| paddle

# OCR 缓存配置
OCR_CACHE_DIR = INDEX_DIR / "ocr_cache"  # OCR 缓存目录
OCR_PARALLEL_WORKERS = 2  # 并行处理任务数
OCR_CACHE_TTL_DAYS = 30  # 缓存过期时间（天）

# PaddleOCR 配置
PADDLE_USE_GPU = False  # 是否使用 GPU
PADDLE_LANG = "ch"  # 语言：ch(中文) | en(英文) | jk(日韩)
PADDLE_USE_ANGLE_CLS = True  # 是否启用方向分类

# Tesseract 配置
TESSERACT_PATH = ""  # Tesseract 可执行文件路径；为空 = 自动探测（TESSERACT_PATH → PATH → 平台常见目录）
TESSERACT_LANG = "chi_sim+eng"  # 语言包

# 图像预处理配置
OCR_PREPROCESS = True  # 是否启用图像预处理
OCR_DENOISE = True  # 去噪
OCR_BINARIZE = True  # 二值化
OCR_DESKEW = True  # 倾斜校正
OCR_ENHANCE_CONTRAST = True  # 对比度增强

# PDF 图片提取配置
PDF_EXTRACT_IMAGES = True  # 是否提取 PDF 中的图片
PDF_MIN_IMAGE_SIZE = (50, 50)  # 最小图片尺寸
```

### 环境变量配置

也可以通过环境变量配置：

```bash
# OCR 功能
export OCR_ENABLED=true
export OCR_ENGINE=tesseract
export OCR_PARALLEL_WORKERS=2

# PaddleOCR
export PADDLE_USE_GPU=false
export PADDLE_LANG=ch

# Tesseract
export TESSERACT_PATH=/usr/local/bin/tesseract   # 仅在装在非常规位置时需要；默认自动探测
export TESSERACT_LANG=chi_sim+eng
```

> `TESSERACT_PATH` 现在默认为空 = 自动探测（`TESSERACT_PATH` → `PATH` → 平台常见目录），只在装在非常规位置时才需要设置；
> 探测顺序与安装方法见 [安装指南 §OCR](02-installation.md#ocr)。

---

## 智能命令推荐系统（CLI）

智能命令推荐系统会在您执行命令后自动显示推荐的操作建议：

```bash
# 环境变量配置（可选）
export RECOMMENDER_ENABLED=true          # 启用推荐系统
export RECOMMENDER_MAX=5                 # 最大推荐数量
export RECOMMENDER_MIN_STRENGTH=0.3      # 最小推荐强度
export RECOMMENDER_LEARNING=true         # 启用学习功能

# 推荐系统会在CLI中自动启用
# 注意：推荐系统仅在CLI中实现，不包含在桌面应用中
```

---

**上一篇**: [最佳实践](07-best-practices.md) | **下一篇**: [开发者指南](09-development.md) | **返回目录**: [README](README.md)
