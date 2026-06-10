"""
融合配置 - RAG 知识库 + Code Agent
"""
import os
import logging
import warnings

# 禁用ChromaDB遥测，避免capture()错误
os.environ['ANONYMIZED_TELEMETRY'] = 'False'
os.environ['CHROMA_TELEMETRY'] = 'False'
logging.getLogger("chromadb").setLevel(logging.ERROR)
logging.getLogger("chromadb.segment").setLevel(logging.ERROR)

# 禁用urllib3的OpenSSL警告（macOS LibreSSL版本问题）
warnings.filterwarnings("ignore", message="urllib3 v2 only supports OpenSSL 1.1.1+")

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
