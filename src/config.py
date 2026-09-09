"""
融合配置 - RAG 知识库 + Code Agent
"""
import os
import re
import logging
import warnings

# 禁用ChromaDB遥测，避免capture()错误
os.environ['ANONYMIZED_TELEMETRY'] = 'False'
os.environ['DO_NOT_TRACK'] = '1'
os.environ['CHROMA_TELEMETRY'] = 'False'
# 禁用posthog日志
logging.getLogger("chromadb").setLevel(logging.ERROR)
logging.getLogger("chromadb.segment").setLevel(logging.ERROR)
logging.getLogger("posthog").setLevel(logging.ERROR)

from pathlib import Path
from dataclasses import dataclass, field

# ==================== 路径配置 ====================
# 打包运行（PyInstaller）时，源码位于只读目录，需要把数据/索引写到用户数据目录。
import sys as _sys

try:
    from runtime_paths import user_data_dir as _user_data_dir, home_file as _home_file
except ImportError:
    from src.runtime_paths import (  # type: ignore
        user_data_dir as _user_data_dir,
        home_file as _home_file,
    )

if getattr(_sys, "frozen", False) and hasattr(_sys, "_MEIPASS"):
    BASE_DIR = _user_data_dir()
else:
    BASE_DIR = Path(__file__).parent.parent.resolve()

DATA_DIR = BASE_DIR / "data"
INDEX_DIR = BASE_DIR / "index_storage"

# 确保目录存在
DATA_DIR.mkdir(parents=True, exist_ok=True)
INDEX_DIR.mkdir(parents=True, exist_ok=True)

# ==================== Ollama 模型配置 ====================
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

# 全局唯一 LLM：用户只需选这一个模型，它同时用于 ReAct Agent、代码任务、
# RAG 综合回答与相关性判定。全程只驻留单一模型，避免多模型同时占用显存导致
# 卡顿（尤其中端统一内存机器）。
#
# 默认 qwen3.5:4b（"协同档"）：16K 上下文下实测约 3.7GB 驻留，可与 IDE/浏览器
# 在 16GB 机器上共存；工具调用、中文归纳、长文本能力均可满足日常查询、报告分析、
# 文件整理、SQL 查询与简单重构。需要更强能力且内存宽裕时可切到 qwen3.5:9b
# （"性能档"，约 6GB 驻留）。可用 CLI `--model` / `/model <name>`、Web 界面下拉，
# 或 LLM_MODEL 环境变量覆盖。
DEFAULT_LLM_MODEL = "qwen3.5:4b"
LLM_MODEL = os.getenv("LLM_MODEL", DEFAULT_LLM_MODEL)
EMBED_MODEL = os.getenv("EMBED_MODEL", "nomic-embed-text:latest")

# 是否让支持"思考模式"的模型（qwen3.5 等）在回答前输出思维链。ReAct 工具调用与
# RAG 综合回答对隐式思考几乎无收益，却会让 4B 模型为三句话答案生成上千 token
# （本机实测约 40 秒）。默认关闭以换取响应速度；需要复杂推理时可设 LLM_THINK=true。
LLM_THINK = os.getenv("LLM_THINK", "false").strip().lower() in ("1", "true", "yes", "on")

# 是否以流式（Ollama NDJSON）接收模型输出，让 CLI / Web 逐字显示最终答案并可随时中断
# （F10 P1-1）。默认开启；设为 false 时所有 on_token 回调退化为"完整文本一次性回调"，
# 请求体与此前非流式行为完全一致。
LLM_STREAM = os.getenv("LLM_STREAM", "true").strip().lower() in ("1", "true", "yes", "on")

# ==================== LLM 后端（F10 P1-2）====================
# LLM_PROVIDER：对话模型走哪种后端协议。
#   ollama（默认）：Ollama 原生 /api/chat（NDJSON 流、think / num_ctx 等 options 原样透传）；
#   openai：任意 OpenAI 兼容服务（vLLM / LM Studio / llama.cpp server / 内网网关，含 Ollama 自带的 /v1），
#           走 POST {LLM_BASE_URL}/v1/chat/completions，SSE 流式；options 映射 temperature、
#           num_predict→max_tokens，num_ctx 由后端决定（忽略），think 忽略。
# 未识别的取值回退 ollama 并打 warning。嵌入模型（EMBED_MODEL）始终走 Ollama（OLLAMA_BASE_URL）。
LLM_PROVIDERS = ("ollama", "openai")
LLM_PROVIDER = (os.getenv("LLM_PROVIDER", "ollama").strip().lower() or "ollama")
# LLM_BASE_URL：对话后端地址；未设置时取 OLLAMA_BASE_URL（openai 模式下即 Ollama 自带的兼容端点）。
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "").strip() or OLLAMA_BASE_URL
# LLM_API_KEY：openai 模式的 Bearer 令牌；本地服务通常不需要，留空即可。
LLM_API_KEY = os.getenv("LLM_API_KEY", "").strip()
# LLM_REASONING_EFFORT：openai 模式下、思考模式关闭（LLM_THINK=false）时随请求发送的标准字段
# reasoning_effort（OpenAI 协议没有 Ollama 的 think 字段；思考型模型在兼容端点上默认开启思考，
# 会把 max_tokens 预算全部花在 reasoning 上而 content 为空）。默认 none；Ollama /v1 与 OpenAI 均识别。
# 后端返回 400 不认识该字段时 llm_client 会自动去掉重试并记住。设为空串则不发送任何字段。
LLM_REASONING_EFFORT = os.getenv("LLM_REASONING_EFFORT", "none").strip().lower()
# OLLAMA_MAX_CONCURRENCY：进程内同时发往对话后端的 LLM 请求上限（F10 P2-1-d）。多 Agent 并行时
# 各子 Agent 独立请求同一 Ollama，单 GPU 上只会排队并让每个请求都变慢直至超时；用信号量把并发
# 压到 2，其余请求在本地排队（进度显示"排队中"，排队时间不计入子任务超时）。LLM_PROVIDER=openai
# 接 vLLM 等支持批处理的后端时建议调大；0 或负数表示不限制。
OLLAMA_MAX_CONCURRENCY = int(os.getenv("OLLAMA_MAX_CONCURRENCY", "2") or 0)


def resolve_num_ctx(model: str) -> int:
    """按模型规格自动推导安全且够用的上下文窗口（num_ctx），用户零配置。

    许多模型（如 qwen3.5 系列）默认上下文高达 256K，Ollama 会据此分配 KV cache
    撑爆显存并卸载到 CPU，导致推理近乎卡死。此处按参数量给出在中端机上仍能全 GPU
    驻留、且对 RAG/Agent 任务够用的上下文：参数量越大，权重占显存越多、留给 KV
    cache 的预算越小，num_ctx 越保守。可用 LLM_NUM_CTX 环境变量强制覆盖。
    """
    override = os.getenv("LLM_NUM_CTX")
    if override and override.strip():
        try:
            return int(override)
        except ValueError:
            pass
    # 从模型名中解析参数量（单位 B），兼容 "qwen3.5:4b"、"qwen2.5-coder:7b"、
    # "SparkLLM/Spark-X2.5-4B" 等命名（大小写不敏感，冒号/连字符分隔均可）。
    # 取最后一个匹配，避免把 "x2.5" 之类版本号误判为参数量。
    name = (model or "").lower()
    matches = re.findall(r"(?:^|[:\-_/])(\d+(?:\.\d+)?)b(?![a-z0-9])", name)
    params_b = float(matches[-1]) if matches else 0.0
    # 12B~14B：权重最重，上下文最保守
    if params_b >= 12:
        return 4096
    # 7B~9B：中等权重
    if params_b >= 7:
        return 8192
    # 4B 及以下（或无法识别）：显存宽裕，可给较大上下文
    return 16384


# 全局唯一 LLM 的上下文窗口，按所选模型自动推导（零配置），可用 LLM_NUM_CTX 覆盖。
LLM_NUM_CTX = resolve_num_ctx(LLM_MODEL)


def set_llm_model(model: str) -> int:
    """运行时切换全局唯一 LLM（供 CLI ``/model <name>`` 与 Web 模型下拉使用）。

    同步更新模块级 ``LLM_MODEL`` / ``LLM_NUM_CTX`` 以及兼容类 ``Config`` 的
    ``MODEL`` / ``LLM_MODEL``，使所有"调用时读取 config"的模块（多 Agent 配置、
    提交信息生成、知识快照等）自动跟随。已在 import 时绑定常量的引擎
    （RAGEngine / ReActEngine）需另行调用各自的 ``set_model``。

    返回新模型对应的 num_ctx。
    """
    global LLM_MODEL, LLM_NUM_CTX
    model = (model or "").strip()
    if not model:
        raise ValueError("模型名不能为空")
    LLM_MODEL = model
    LLM_NUM_CTX = resolve_num_ctx(model)
    os.environ["LLM_MODEL"] = model
    # Config 是 dataclass，字段默认值在类定义时冻结，这里直接改类属性。
    try:
        Config.MODEL = model
        Config.LLM_MODEL = model
    except NameError:  # Config 尚未定义（模块加载期不会走到这里）
        pass
    return LLM_NUM_CTX


def set_llm_think(enabled: bool) -> bool:
    """运行时开关思考模式（供 CLI ``/think on|off`` 与 Web 复选框使用）。

    仅更新模块级 ``LLM_THINK`` 与环境变量；已创建的引擎需另行调用各自的
    ``set_think``（见 model_switcher.switch_think）。返回新值。
    """
    global LLM_THINK
    LLM_THINK = bool(enabled)
    os.environ["LLM_THINK"] = "true" if LLM_THINK else "false"
    return LLM_THINK

# ==================== 向量数据库配置 ====================
VECTOR_DB_PATH = str(INDEX_DIR / "chroma_db")

# ==================== RAG 分块与检索配置 ====================
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "1024"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "200"))
TOP_K = int(os.getenv("TOP_K", "10"))
# nomic-embed-text 使用余弦相似度，相关结果分数通常在 0.3~0.75 之间。
# 对“知识库里有什么”这类元/概览查询，正文语义分数偏低（实测约 0.39），
# 0.4 阈值会把有效结果全部过滤，导致检索为 0；下调到 0.3 作为更合理的下限。
SIMILARITY_CUTOFF = float(os.getenv("SIMILARITY_CUTOFF", "0.3"))

# 知识库“命中相关性”阈值（区别于上面的检索召回阈值 SIMILARITY_CUTOFF）。
# 说明：SIMILARITY_CUTOFF 故意调低到 0.3 以保护元/概览类查询的召回，但这也会
# 让一些语义几乎无关的片段（实测约 0.39~0.42）被召回。若把它们当作“知识库命中”
# 塞进综合回答的上下文与引用来源，会产生答非所问的噪音（例如问“某产品售价”却
# 引用了讲 Cloudflare 配置的片段）。因此在问答编排层用一个更高的“相关性阈值”
# 判定知识库是否“真正命中”：低于该分数的片段视为噪音，不计入知识库来源、不进
# 综合 prompt，从而回退到网络/模型回答。仅影响问答判定，不改变底层检索召回。
KB_RELEVANCE_THRESHOLD = float(os.getenv("KB_RELEVANCE_THRESHOLD", "0.45"))

# ==================== RAG 推理与可核验性（F8 P2）====================
# RERANKER：逐片段相关性筛选方式。
#   llm（默认）：一次 LLM 调用（think=False）对 top-k 片段输出 keep/notes JSON；
#   cross-encoder：sentence-transformers CrossEncoder（可选依赖，未安装自动回退 llm）。
RERANKER = os.getenv("RERANKER", "llm").strip().lower() or "llm"
RERANKER_MODEL = os.getenv("RERANKER_MODEL", "BAAI/bge-reranker-v2-m3")
# RAG_HYBRID：dense（向量）+ BM25 关键词 hybrid 召回（RRF 融合），默认开启；
# rank_bm25 未安装时回退 dense。
# RAG_HYBRID_MAX_CHUNKS：文档块数超过该值时关闭 hybrid（仅向量检索），并在 /stats、Web 知识库页与
# query 结果 meta.hybrid_disabled_reason 中给出原因（F10 P2-1-b）。BM25 语料（词频 + 来源元数据 +
# 索引）常驻内存，实测每万块约 100–150MB（取决于词汇量），默认 50000（上限时约 0.5–0.75GB）；
# 8GB 机器建议 20000，内存宽裕可继续调大。
RAG_HYBRID = os.getenv("RAG_HYBRID", "true").strip().lower() in ("1", "true", "yes", "on")
RAG_HYBRID_MAX_CHUNKS = int(os.getenv("RAG_HYBRID_MAX_CHUNKS", "50000"))

# ==================== 抗过度顺从（F9 P2）====================
# RAG_SELF_CHECK：知识库命中并综合完成后，再用同一模型逐句核对"回答中的事实句是否被资料支持"
#   （一次额外 LLM 调用，think=False，num_predict≤400）；有未支持的陈述时以 self_check 警示列出，
#   不改答案正文。默认关闭（每问多一次调用）；解析失败 / 超时静默跳过。
RAG_SELF_CHECK = os.getenv("RAG_SELF_CHECK", "false").strip().lower() in ("1", "true", "yes", "on")

# ==================== 代码感知分块（F8 P4）====================
# CODE_AWARE_CHUNKING：代码文件（.py/.js/.ts/.java/.go/.rs/.c/.cpp）入库时按函数/类边界
#   切分（tree-sitter），片段带 symbol / 行号元数据，引用可定位到 `文件 · 符号 · L起-止`。
#   可选依赖 tree-sitter-language-pack 未安装或解析失败时自动回退通用 SentenceSplitter。
CODE_AWARE_CHUNKING = os.getenv("CODE_AWARE_CHUNKING", "true").strip().lower() in ("1", "true", "yes", "on")
# 单个代码片段的字符上限（≈400 token，与 rerank 的 400 字截断对齐）；超长函数体再二次切分。
CODE_CHUNK_MAX_CHARS = int(os.getenv("CODE_CHUNK_MAX_CHARS", "1500"))
# 小于该字符数的碎片（如单独的签名/装饰器/`class X:` 行）并入相邻片段。
CODE_CHUNK_MIN_CHARS = int(os.getenv("CODE_CHUNK_MIN_CHARS", "120"))

# ==================== 网络搜索配置 ====================
# 此前网络搜索完全未设 region/backend，DuckDuckGo 默认 us-en，天然偏英文/海外
# 结果，导致中国国内信息（中文网页、国行价格、国内新闻等）召回与准确率很差。
# 这里把关键参数外置为可配置项，并给出对中英文都友好的默认值。
#
# WEB_SEARCH_REGION：搜索区域。取值 auto（按查询语境自动判断）或 ddgs 的具体
#   region（如 wt-wt 全球 / cn-zh 中国区中文 / us-en 美国英文）。默认 auto：
#   含中文或"国内/售价/淘宝/京东"等语境的查询用 cn-zh（能召回淘宝/京东等国内
#   电商与价格），英文/全球性查询用 wt-wt。显式设为具体 region 则强制固定。
WEB_SEARCH_REGION = os.getenv("WEB_SEARCH_REGION", "auto")
# WEB_SEARCH_BACKEND：ddgs 后端引擎，逗号分隔可聚合/降级多引擎。
#   注意：部分 ddgs 版本的 bing 后端已被禁用（运行时会告警并忽略），故默认改用
#   brave/duckduckgo/google（对中文与国内信息覆盖好）。整体失败会逐个后端降级重试。
WEB_SEARCH_BACKEND = os.getenv("WEB_SEARCH_BACKEND", "brave, duckduckgo, google")
# WEB_SEARCH_SAFESEARCH：安全搜索级别（on / moderate / off）。
WEB_SEARCH_SAFESEARCH = os.getenv("WEB_SEARCH_SAFESEARCH", "moderate")
# WEB_SEARCH_TIMELIMIT：时间范围（d/w/m/y 或空表示不限）。默认不限。
WEB_SEARCH_TIMELIMIT = os.getenv("WEB_SEARCH_TIMELIMIT", "") or None
# WEB_SEARCH_MAX_RESULTS：单次搜索返回结果数上限。
WEB_SEARCH_MAX_RESULTS = int(os.getenv("WEB_SEARCH_MAX_RESULTS", "10"))
# WEB_SEARCH_TIMEOUT：网页正文提取超时（秒）。
WEB_SEARCH_TIMEOUT = int(os.getenv("WEB_SEARCH_TIMEOUT", "30"))
# WEB_SEARCH_CACHE_TTL_HOURS：搜索结果缓存有效期（小时）。
WEB_SEARCH_CACHE_TTL_HOURS = int(os.getenv("WEB_SEARCH_CACHE_TTL_HOURS", "24"))
# WEB_SEARCH_AGGREGATE：是否聚合多个引擎的结果（合并去重）而非"首个非空即返回"。
WEB_SEARCH_AGGREGATE = os.getenv("WEB_SEARCH_AGGREGATE", "true").lower() == "true"

# ==================== Agent 配置 ====================
# 【已弃用】旧版 ReAct 专用的全局历史文件。对话历史现已统一存放在会话
# （SESSION_STORAGE_PATH）中；该路径仅用于启动时把旧文件一次性迁移到默认会话。
HISTORY_FILE = str(_home_file(".code_agent_history.json"))
MAX_HISTORY = int(os.getenv("MAX_HISTORY", "100"))  # 已弃用：历史按 token 预算滚动压缩，不再按条数截断
MAX_ITERATIONS = int(os.getenv("MAX_ITERATIONS", "50"))
TIMEOUT = int(os.getenv("TIMEOUT", "300"))

# AUTO_CONFIRM：开启后 low / medium 风险的命令与工具免人工确认；
# high / critical 仍需确认（agent_tools.auto_confirm_allows 统一判定）。
AUTO_CONFIRM = os.getenv("CODE_AGENT_AUTO_CONFIRM", "false").lower() == "true"

# 入口智能路由（F8 P3）：自然语言输入先由 intent_router 判定走 RAG 还是 Agent；
# 关闭后自然语言一律走知识库问答（与 /ask 相同）。CLI 可用 /auto on|off 运行时切换。
AUTO_ROUTE = os.getenv("AUTO_ROUTE", "true").lower() == "true"

# Agent 的 write_file / add_to_knowledge_base 允许操作的目录（冒号分隔），
# 始终隐含当前工作目录；解析后不在这些目录内的路径返回 "[错误] 路径超出允许范围"。
# agent_tools 在调用时实时读取该环境变量，这里仅作为配置项文档与 Config 映射。
WRITE_ALLOWED_DIRS = os.getenv("WRITE_ALLOWED_DIRS", "")

# Agent 的 read_file / list_directory / search_files 允许读取的额外目录（冒号分隔）。
# 允许读取范围 = 允许写入目录 ∪ READ_ALLOWED_DIRS ∪ 已入库文件所在目录；越界返回
# "[错误] 路径超出允许范围: …（允许读取 …）"。同样由 agent_tools 实时读取。
READ_ALLOWED_DIRS = os.getenv("READ_ALLOWED_DIRS", "")

# ==================== 文件上传配置 ====================
# 文件大小限制（字节）
MAX_FILE_SIZE = int(os.getenv("MAX_FILE_SIZE", "10485760"))  # 10MB
MAX_TOTAL_SIZE = int(os.getenv("MAX_TOTAL_SIZE", "104857600"))  # 100MB

# 文件类型控制
# 代码文件后缀（不带点）：与 code_chunker.LANGUAGE_MAP 一一对应，document_loader.READERS 与
# ALLOWED_FILE_TYPES 默认值均由此派生，避免三处白名单不一致。
CODE_FILE_EXTENSIONS = ("py", "js", "ts", "java", "go", "rs", "c", "cpp")
DOC_FILE_EXTENSIONS = ("pdf", "md", "markdown", "txt", "html", "json", "yaml", "yml", "xml")
_DEFAULT_ALLOWED_FILE_TYPES = ",".join(DOC_FILE_EXTENSIONS + CODE_FILE_EXTENSIONS)
ALLOWED_FILE_TYPES = os.getenv("ALLOWED_FILE_TYPES", _DEFAULT_ALLOWED_FILE_TYPES).split(",")
BLOCKED_FILE_PATTERNS = os.getenv("BLOCKED_FILE_PATTERNS", "*.tmp,*.cache,*.log,node_modules,__pycache__").split(",")

# 文件去重和清理
ENABLE_FILE_DEDUPLICATION = os.getenv("ENABLE_FILE_DEDUPLICATION", "true").lower() == "true"
TEMPORARY_FILE_TTL_HOURS = int(os.getenv("TEMPORARY_FILE_TTL_HOURS", "24"))

# OCR优化配置
OCR_CACHE_ENABLED = os.getenv("OCR_CACHE_ENABLED", "true").lower() == "true"
OCR_QUALITY_THRESHOLD = float(os.getenv("OCR_QUALITY_THRESHOLD", "0.3"))
OCR_MAX_IMAGE_SIZE = int(os.getenv("OCR_MAX_IMAGE_SIZE", "5242880"))  # 5MB

# ==================== 会话管理配置 ====================
# 环境变量优先；未设置时，打包运行收纳到用户数据目录，源码运行用 ~/.code_agent_sessions
_session_env = os.getenv("SESSION_STORAGE_PATH")
if _session_env:
    SESSION_STORAGE_PATH = Path(_session_env).expanduser()
else:
    SESSION_STORAGE_PATH = _home_file(".code_agent_sessions")
MAX_SESSIONS = int(os.getenv("MAX_SESSIONS", "50"))
MAX_MESSAGES_PER_SESSION = int(os.getenv("MAX_MESSAGES_PER_SESSION", "100"))
AUTO_ARCHIVE_DAYS = int(os.getenv("AUTO_ARCHIVE_DAYS", "30"))

# 历史压缩配置
HISTORY_COMPRESSION_RATIO = float(os.getenv("HISTORY_COMPRESSION_RATIO", "0.5"))
AUTO_COMPRESS_ENABLED = os.getenv("AUTO_COMPRESS_ENABLED", "true").lower() == "true"

# ==================== 连续对话上下文配置 ====================
# 对话历史（滚动摘要 + 最近几轮原文）允许占用的上下文窗口比例。默认 30%：
# 其余留给系统提示、知识库片段/网络摘要与模型输出。可用环境变量覆盖。
CONTEXT_HISTORY_RATIO = float(os.getenv("CONTEXT_HISTORY_RATIO", "0.30"))
# 始终以原文保留的最近轮数（1 轮 = 一问一答），更早的轮次被折叠进滚动摘要。
CONTEXT_RECENT_TURNS = int(os.getenv("CONTEXT_RECENT_TURNS", "3"))
# 历史估算 token 超过预算的该比例即触发自动压缩。
CONTEXT_COMPRESS_THRESHOLD = float(os.getenv("CONTEXT_COMPRESS_THRESHOLD", "0.70"))
# "对话过长建议新会话"：累计压缩次数达到该值即建议；用户选择继续后再 +2 才再次提示。
CONTEXT_SUGGEST_NEW_AFTER_COMPRESSIONS = int(os.getenv("CONTEXT_SUGGEST_NEW_AFTER_COMPRESSIONS", "2"))
# 距上一条消息超过该小时数再提问，视为新话题建议新会话。
CONTEXT_SUGGEST_IDLE_HOURS = float(os.getenv("CONTEXT_SUGGEST_IDLE_HOURS", "6"))

# ==================== 安全策略 ====================
READONLY_COMMANDS = (
    "ls", "pwd", "echo", "cat", "head", "tail", "find", "grep", "wc", "ps",
    "which", "whereis", "uname", "whoami", "date", "df", "du", "top", "htop",
    "git status", "git log", "git diff", "git branch", "git remote", "git show",
    "python -m pytest --collect-only", "python -m pytest -q", "pip list", "pip freeze",
    "ollama list", "ollama ps", "tree", "file", "stat", "lsblk", "lscpu", "free",
)

DANGEROUS_PATTERNS = (
    r"rm -rf /", r"rm -rf /\*", r"dd if=/dev/zero", r"mkfs", r"> /dev/sda",
    r"chmod 777 /", r"curl .*\|.*sh", r"wget .*\|.*sh", r"sudo rm",
    r"del /f /s /q", r"format ", r":\(\)\{ :\|:& };:",
)

FIRST_RUN_MARKER = str(_home_file(".code_agent_first_run"))


# ==================== OCR 配置 ====================
OCR_ENABLED = os.getenv("OCR_ENABLED", "true").lower() == "true"
OCR_ENGINE = os.getenv("OCR_ENGINE", "tesseract")  # paddle | tesseract | hybrid (默认 tesseract 以兼容 Python 3.13)
OCR_CACHE_DIR = INDEX_DIR / "ocr_cache"
OCR_PARALLEL_WORKERS = int(os.getenv("OCR_PARALLEL_WORKERS", "2"))
OCR_TIMEOUT = int(os.getenv("OCR_TIMEOUT", "60"))
OCR_CACHE_TTL_DAYS = int(os.getenv("OCR_CACHE_TTL_DAYS", "30"))

# PaddleOCR 特定配置
PADDLE_USE_GPU = os.getenv("PADDLE_USE_GPU", "false").lower() == "true"
PADDLE_LANG = os.getenv("PADDLE_LANG", "ch")  # ch | en | jk
PADDLE_USE_ANGLE_CLS = os.getenv("PADDLE_USE_ANGLE_CLS", "true").lower() == "true"

# Tesseract 特定配置
TESSERACT_PATH = os.getenv("TESSERACT_PATH", "/opt/homebrew/bin/tesseract")  # macOS Homebrew 路径
TESSERACT_LANG = os.getenv("TESSERACT_LANG", "chi_sim+eng")

# 图像预处理配置
OCR_PREPROCESS = os.getenv("OCR_PREPROCESS", "true").lower() == "true"
OCR_DENOISE = os.getenv("OCR_DENOISE", "true").lower() == "true"
OCR_BINARIZE = os.getenv("OCR_BINARIZE", "true").lower() == "true"
OCR_DESKEW = os.getenv("OCR_DESKEW", "true").lower() == "true"
OCR_ENHANCE_CONTRAST = os.getenv("OCR_ENHANCE_CONTRAST", "true").lower() == "true"

# PDF 图片提取配置
PDF_EXTRACT_IMAGES = os.getenv("PDF_EXTRACT_IMAGES", "true").lower() == "true"
PDF_MIN_IMAGE_SIZE = tuple(map(int, os.getenv("PDF_MIN_IMAGE_SIZE", "50,50").split(",")))


# ==================== 进度显示配置 ====================
# 是否显示进度信息
SHOW_PROGRESS = os.getenv("SHOW_PROGRESS", "true").lower() == "true"
# 进度条样式 (rich | simple)
PROGRESS_BAR_STYLE = os.getenv("PROGRESS_BAR_STYLE", "rich").lower()
# 是否显示时间估算
ESTIMATE_TIME = os.getenv("ESTIMATE_TIME", "true").lower() == "true"
# 是否显示详细统计信息
SHOW_STATS = os.getenv("SHOW_STATS", "false").lower() == "true"
# 详细模式（显示技术参数）
VERBOSE_MODE = os.getenv("VERBOSE_MODE", "false").lower() == "true"


# ==================== 兼容 Config dataclass（供 query_interface / react_engine 引用）====================
@dataclass
class Config:
    """向后兼容的 Config 类，属性映射到模块级变量"""
    OLLAMA_BASE_URL: str = OLLAMA_BASE_URL  # 保持向后兼容
    OLLAMA_HOST: str = OLLAMA_BASE_URL
    MODEL: str = LLM_MODEL
    LLM_MODEL: str = LLM_MODEL
    LLM_STREAM: bool = LLM_STREAM
    LLM_PROVIDER: str = LLM_PROVIDER
    LLM_BASE_URL: str = LLM_BASE_URL
    LLM_API_KEY: str = LLM_API_KEY
    LLM_REASONING_EFFORT: str = LLM_REASONING_EFFORT
    OLLAMA_MAX_CONCURRENCY: int = OLLAMA_MAX_CONCURRENCY
    RAG_HYBRID: bool = RAG_HYBRID
    RAG_HYBRID_MAX_CHUNKS: int = RAG_HYBRID_MAX_CHUNKS
    HISTORY_FILE: str = HISTORY_FILE
    MAX_HISTORY: int = MAX_HISTORY
    MAX_ITERATIONS: int = MAX_ITERATIONS
    TIMEOUT: int = TIMEOUT
    AUTO_CONFIRM: bool = AUTO_CONFIRM
    AUTO_ROUTE: bool = AUTO_ROUTE
    WRITE_ALLOWED_DIRS: str = WRITE_ALLOWED_DIRS
    READ_ALLOWED_DIRS: str = READ_ALLOWED_DIRS
    CODE_AWARE_CHUNKING: bool = CODE_AWARE_CHUNKING
    CODE_CHUNK_MAX_CHARS: int = CODE_CHUNK_MAX_CHARS
    CODE_CHUNK_MIN_CHARS: int = CODE_CHUNK_MIN_CHARS
    READONLY_COMMANDS: tuple = READONLY_COMMANDS
    DANGEROUS_PATTERNS: tuple = DANGEROUS_PATTERNS
    FIRST_RUN_MARKER: str = FIRST_RUN_MARKER
    
    # OCR 配置
    OCR_ENABLED: bool = OCR_ENABLED
    OCR_ENGINE: str = OCR_ENGINE
    OCR_CACHE_DIR: Path = OCR_CACHE_DIR
    OCR_PARALLEL_WORKERS: int = OCR_PARALLEL_WORKERS
    OCR_TIMEOUT: int = OCR_TIMEOUT
    OCR_CACHE_TTL_DAYS: int = OCR_CACHE_TTL_DAYS
    PADDLE_USE_GPU: bool = PADDLE_USE_GPU
    PADDLE_LANG: str = PADDLE_LANG
    PADDLE_USE_ANGLE_CLS: bool = PADDLE_USE_ANGLE_CLS
    TESSERACT_PATH: str = TESSERACT_PATH
    TESSERACT_LANG: str = TESSERACT_LANG
    OCR_PREPROCESS: bool = OCR_PREPROCESS
    OCR_DENOISE: bool = OCR_DENOISE
    OCR_BINARIZE: bool = OCR_BINARIZE
    OCR_DESKEW: bool = OCR_DESKEW
    OCR_ENHANCE_CONTRAST: bool = OCR_ENHANCE_CONTRAST
    PDF_EXTRACT_IMAGES: bool = PDF_EXTRACT_IMAGES
    PDF_MIN_IMAGE_SIZE: tuple = PDF_MIN_IMAGE_SIZE
    
    # 进度显示配置
    SHOW_PROGRESS: bool = SHOW_PROGRESS
    PROGRESS_BAR_STYLE: str = PROGRESS_BAR_STYLE
    ESTIMATE_TIME: bool = ESTIMATE_TIME
    SHOW_STATS: bool = SHOW_STATS
    VERBOSE_MODE: bool = VERBOSE_MODE
    
    # 文件上传配置
    MAX_FILE_SIZE: int = MAX_FILE_SIZE
    MAX_TOTAL_SIZE: int = MAX_TOTAL_SIZE
    ALLOWED_FILE_TYPES: list = field(default_factory=lambda: ALLOWED_FILE_TYPES)
    BLOCKED_FILE_PATTERNS: list = field(default_factory=lambda: BLOCKED_FILE_PATTERNS)
    ENABLE_FILE_DEDUPLICATION: bool = ENABLE_FILE_DEDUPLICATION
    TEMPORARY_FILE_TTL_HOURS: int = TEMPORARY_FILE_TTL_HOURS
    OCR_CACHE_ENABLED: bool = OCR_CACHE_ENABLED
    OCR_QUALITY_THRESHOLD: float = OCR_QUALITY_THRESHOLD
    OCR_MAX_IMAGE_SIZE: int = OCR_MAX_IMAGE_SIZE
    
    # 会话管理配置
    SESSION_STORAGE_PATH: Path = SESSION_STORAGE_PATH
    MAX_SESSIONS: int = MAX_SESSIONS
    MAX_MESSAGES_PER_SESSION: int = MAX_MESSAGES_PER_SESSION
    AUTO_ARCHIVE_DAYS: int = AUTO_ARCHIVE_DAYS
    HISTORY_COMPRESSION_RATIO: float = HISTORY_COMPRESSION_RATIO
    AUTO_COMPRESS_ENABLED: bool = AUTO_COMPRESS_ENABLED
