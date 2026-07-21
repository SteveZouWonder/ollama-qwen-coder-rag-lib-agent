"""
融合配置 - RAG 知识库 + Code Agent
"""
import os
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
# 统一使用 qwen2.5-coder:7b
LLM_MODEL = os.getenv("LLM_MODEL", "qwen2.5-coder:7b")
EMBED_MODEL = os.getenv("EMBED_MODEL", "nomic-embed-text:latest")

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
# 打包运行时收纳到用户数据目录，源码运行时仍为 ~/.code_agent_history.json
HISTORY_FILE = str(_home_file(".code_agent_history.json"))
MAX_HISTORY = int(os.getenv("MAX_HISTORY", "100"))
MAX_ITERATIONS = int(os.getenv("MAX_ITERATIONS", "50"))
TIMEOUT = int(os.getenv("TIMEOUT", "300"))

AUTO_CONFIRM = os.getenv("CODE_AGENT_AUTO_CONFIRM", "false").lower() == "true"

# ==================== 文件上传配置 ====================
# 文件大小限制（字节）
MAX_FILE_SIZE = int(os.getenv("MAX_FILE_SIZE", "10485760"))  # 10MB
MAX_TOTAL_SIZE = int(os.getenv("MAX_TOTAL_SIZE", "104857600"))  # 100MB

# 文件类型控制
ALLOWED_FILE_TYPES = os.getenv("ALLOWED_FILE_TYPES", "pdf,md,txt,py,js,ts,java,cpp,go,rs,html,json,yaml,xml").split(",")
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
    HISTORY_FILE: str = HISTORY_FILE
    MAX_HISTORY: int = MAX_HISTORY
    MAX_ITERATIONS: int = MAX_ITERATIONS
    TIMEOUT: int = TIMEOUT
    AUTO_CONFIRM: bool = AUTO_CONFIRM
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
