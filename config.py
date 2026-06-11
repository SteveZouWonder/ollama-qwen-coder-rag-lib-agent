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
from dataclasses import dataclass

# ==================== 路径配置 ====================
BASE_DIR = Path(__file__).parent.resolve()
DATA_DIR = BASE_DIR / "data"
INDEX_DIR = BASE_DIR / "index_storage"

# 确保目录存在
DATA_DIR.mkdir(exist_ok=True)
INDEX_DIR.mkdir(exist_ok=True)

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
TOP_K = int(os.getenv("TOP_K", "5"))
SIMILARITY_CUTOFF = float(os.getenv("SIMILARITY_CUTOFF", "0.7"))

# ==================== Agent 配置 ====================
HISTORY_FILE = os.path.expanduser("~/.code_agent_history.json")
MAX_HISTORY = int(os.getenv("MAX_HISTORY", "100"))
MAX_ITERATIONS = int(os.getenv("MAX_ITERATIONS", "50"))
TIMEOUT = int(os.getenv("TIMEOUT", "300"))

AUTO_CONFIRM = os.getenv("CODE_AGENT_AUTO_CONFIRM", "false").lower() == "true"

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

FIRST_RUN_MARKER = os.path.expanduser("~/.code_agent_first_run")


# ==================== OCR 配置 ====================
OCR_ENABLED = os.getenv("OCR_ENABLED", "true").lower() == "true"
OCR_ENGINE = os.getenv("OCR_ENGINE", "paddle")  # paddle | tesseract | hybrid
OCR_CACHE_DIR = INDEX_DIR / "ocr_cache"
OCR_PARALLEL_WORKERS = int(os.getenv("OCR_PARALLEL_WORKERS", "2"))
OCR_TIMEOUT = int(os.getenv("OCR_TIMEOUT", "60"))
OCR_CACHE_TTL_DAYS = int(os.getenv("OCR_CACHE_TTL_DAYS", "30"))

# PaddleOCR 特定配置
PADDLE_USE_GPU = os.getenv("PADDLE_USE_GPU", "false").lower() == "true"
PADDLE_LANG = os.getenv("PADDLE_LANG", "ch")  # ch | en | jk
PADDLE_USE_ANGLE_CLS = os.getenv("PADDLE_USE_ANGLE_CLS", "true").lower() == "true"

# Tesseract 特定配置
TESSERACT_PATH = os.getenv("TESSERACT_PATH", "/usr/local/bin/tesseract")
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
