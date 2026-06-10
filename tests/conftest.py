"""
共享 fixture 和测试工具
在导入被测模块前预注入 Mock，避免未安装依赖导致导入失败
"""
import sys
from unittest.mock import MagicMock

# ========== 预注入 Mock 模块（避免 llama_index/chromadb 未安装导致导入失败）==========

# Mock llama_index 整个包树
_llama_index = MagicMock()
sys.modules["llama_index"] = _llama_index
sys.modules["llama_index.core"] = _llama_index.core
sys.modules["llama_index.core.readers"] = _llama_index.core.readers
sys.modules["llama_index.core.readers.base"] = _llama_index.core.readers.base
sys.modules["llama_index.core.schema"] = _llama_index.core.schema
sys.modules["llama_index.core.node_parser"] = _llama_index.core.node_parser
sys.modules["llama_index.embeddings"] = _llama_index.embeddings
sys.modules["llama_index.embeddings.ollama"] = _llama_index.embeddings.ollama
sys.modules["llama_index.llms"] = _llama_index.llms
sys.modules["llama_index.llms.ollama"] = _llama_index.llms.ollama
sys.modules["llama_index.vector_stores"] = _llama_index.vector_stores
sys.modules["llama_index.vector_stores.chroma"] = _llama_index.vector_stores.chroma
sys.modules["llama_index.readers"] = _llama_index.readers
sys.modules["llama_index.readers.file"] = _llama_index.readers.file

# Mock chromadb
_chromadb = MagicMock()
sys.modules["chromadb"] = _chromadb

# Mock pypdf
sys.modules["pypdf"] = MagicMock()

# Mock rich（测试中会手动控制 HAS_RICH）
_rich = MagicMock()
sys.modules["rich"] = _rich
sys.modules["rich.console"] = _rich.console
sys.modules["rich.markdown"] = _rich.markdown
sys.modules["rich.panel"] = _rich.panel
sys.modules["rich.syntax"] = _rich.syntax
sys.modules["rich.box"] = _rich.box
sys.modules["rich.table"] = _rich.table
sys.modules["rich.prompt"] = _rich.prompt

# Mock prompt_toolkit
_ptk = MagicMock()
sys.modules["prompt_toolkit"] = _ptk
sys.modules["prompt_toolkit.history"] = _ptk.history
sys.modules["prompt_toolkit.auto_suggest"] = _ptk.auto_suggest

import pytest
import tempfile
import os
import json
from pathlib import Path


@pytest.fixture
def temp_dir():
    """提供临时目录，自动清理"""
    with tempfile.TemporaryDirectory() as td:
        yield Path(td)


@pytest.fixture
def mock_rag_engine():
    """Mock RAG 引擎，供 Agent 工具注入"""
    engine = MagicMock()
    engine.query_tool.return_value = "[Mock] 知识库查询结果"
    engine.add_document_tool.return_value = "[Mock] 文档已添加"
    engine.get_stats_tool.return_value = "[Mock] 统计信息"
    return engine


@pytest.fixture
def clean_env(monkeypatch):
    """清理环境变量，确保测试不受外部影响"""
    env_vars = [
        "LLM_MODEL", "EMBED_MODEL", "OLLAMA_BASE_URL",
        "CHUNK_SIZE", "CHUNK_OVERLAP", "TOP_K", "SIMILARITY_CUTOFF",
        "CODE_AGENT_AUTO_CONFIRM", "MAX_HISTORY", "MAX_ITERATIONS", "TIMEOUT",
    ]
    for var in env_vars:
        monkeypatch.delenv(var, raising=False)
