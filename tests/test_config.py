#!/usr/bin/env python3
"""
test_config.py — 配置模块单元测试（目标 100% 覆盖）
"""
import os
import pytest
from pathlib import Path


class TestConfigDefaults:
    """测试默认值（无环境变量时）"""

    def test_base_dir_exists(self, clean_env):
        from config import BASE_DIR
        assert BASE_DIR.exists()
        assert BASE_DIR.is_dir()

    def test_data_dir_created(self, clean_env):
        from config import DATA_DIR
        assert DATA_DIR.exists()
        assert DATA_DIR.is_dir()

    def test_index_dir_created(self, clean_env):
        from config import INDEX_DIR
        assert INDEX_DIR.exists()
        assert INDEX_DIR.is_dir()

    def test_ollama_base_url_default(self, clean_env):
        from config import OLLAMA_BASE_URL
        assert OLLAMA_BASE_URL == "http://localhost:11434"

    def test_llm_model_default(self, clean_env):
        from config import LLM_MODEL
        assert LLM_MODEL == "qwen2.5-coder:7b"

    def test_embed_model_default(self, clean_env):
        from config import EMBED_MODEL
        assert EMBED_MODEL == "nomic-embed-text:latest"

    def test_vector_db_path(self, clean_env):
        from config import VECTOR_DB_PATH, INDEX_DIR
        assert VECTOR_DB_PATH == str(INDEX_DIR / "chroma_db")

    def test_chunk_size_default(self, clean_env):
        from config import CHUNK_SIZE
        assert CHUNK_SIZE == 1024

    def test_chunk_overlap_default(self, clean_env):
        from config import CHUNK_OVERLAP
        assert CHUNK_OVERLAP == 200

    def test_top_k_default(self, clean_env):
        from config import TOP_K
        assert TOP_K == 5

    def test_similarity_cutoff_default(self, clean_env):
        from config import SIMILARITY_CUTOFF
        assert SIMILARITY_CUTOFF == 0.7

    def test_history_file_default(self, clean_env):
        from config import HISTORY_FILE
        assert HISTORY_FILE == os.path.expanduser("~/.code_agent_history.json")

    def test_max_history_default(self, clean_env):
        from config import MAX_HISTORY
        assert MAX_HISTORY == 100

    def test_max_iterations_default(self, clean_env):
        from config import MAX_ITERATIONS
        assert MAX_ITERATIONS == 50

    def test_timeout_default(self, clean_env):
        from config import TIMEOUT
        assert TIMEOUT == 300

    def test_auto_confirm_default(self, clean_env):
        from config import AUTO_CONFIRM
        assert AUTO_CONFIRM is False

    def test_readonly_commands_tuple(self, clean_env):
        from config import READONLY_COMMANDS
        assert isinstance(READONLY_COMMANDS, tuple)
        assert "ls" in READONLY_COMMANDS
        assert "git status" in READONLY_COMMANDS
        assert "pwd" in READONLY_COMMANDS

    def test_dangerous_patterns_tuple(self, clean_env):
        from config import DANGEROUS_PATTERNS
        assert isinstance(DANGEROUS_PATTERNS, tuple)
        assert len(DANGEROUS_PATTERNS) > 0

    def test_first_run_marker(self, clean_env):
        from config import FIRST_RUN_MARKER
        assert FIRST_RUN_MARKER == os.path.expanduser("~/.code_agent_first_run")


class TestConfigEnvOverride:
    """测试环境变量覆盖"""

    def test_llm_model_override(self, monkeypatch, clean_env):
        monkeypatch.setenv("LLM_MODEL", "custom-model:13b")
        # 必须重新导入才能读取新环境变量
        import importlib
        import config
        importlib.reload(config)
        assert config.LLM_MODEL == "custom-model:13b"

    def test_embed_model_override(self, monkeypatch, clean_env):
        monkeypatch.setenv("EMBED_MODEL", "custom-embed")
        import importlib
        import config
        importlib.reload(config)
        assert config.EMBED_MODEL == "custom-embed"

    def test_ollama_base_url_override(self, monkeypatch, clean_env):
        monkeypatch.setenv("OLLAMA_BASE_URL", "http://192.168.1.100:11434")
        import importlib
        import config
        importlib.reload(config)
        assert config.OLLAMA_BASE_URL == "http://192.168.1.100:11434"

    def test_chunk_size_override(self, monkeypatch, clean_env):
        monkeypatch.setenv("CHUNK_SIZE", "512")
        import importlib
        import config
        importlib.reload(config)
        assert config.CHUNK_SIZE == 512

    def test_chunk_overlap_override(self, monkeypatch, clean_env):
        monkeypatch.setenv("CHUNK_OVERLAP", "100")
        import importlib
        import config
        importlib.reload(config)
        assert config.CHUNK_OVERLAP == 100

    def test_top_k_override(self, monkeypatch, clean_env):
        monkeypatch.setenv("TOP_K", "10")
        import importlib
        import config
        importlib.reload(config)
        assert config.TOP_K == 10

    def test_similarity_cutoff_override(self, monkeypatch, clean_env):
        monkeypatch.setenv("SIMILARITY_CUTOFF", "0.85")
        import importlib
        import config
        importlib.reload(config)
        assert config.SIMILARITY_CUTOFF == 0.85

    def test_max_history_override(self, monkeypatch, clean_env):
        monkeypatch.setenv("MAX_HISTORY", "200")
        import importlib
        import config
        importlib.reload(config)
        assert config.MAX_HISTORY == 200

    def test_max_iterations_override(self, monkeypatch, clean_env):
        monkeypatch.setenv("MAX_ITERATIONS", "100")
        import importlib
        import config
        importlib.reload(config)
        assert config.MAX_ITERATIONS == 100

    def test_timeout_override(self, monkeypatch, clean_env):
        monkeypatch.setenv("TIMEOUT", "600")
        import importlib
        import config
        importlib.reload(config)
        assert config.TIMEOUT == 600

    def test_auto_confirm_true(self, monkeypatch, clean_env):
        monkeypatch.setenv("CODE_AGENT_AUTO_CONFIRM", "true")
        import importlib
        import config
        importlib.reload(config)
        assert config.AUTO_CONFIRM is True

    def test_auto_confirm_yes(self, monkeypatch, clean_env):
        monkeypatch.setenv("CODE_AGENT_AUTO_CONFIRM", "yes")
        import importlib
        import config
        importlib.reload(config)
        assert config.AUTO_CONFIRM is False  # 只有 "true" 才为真

    def test_auto_confirm_1(self, monkeypatch, clean_env):
        monkeypatch.setenv("CODE_AGENT_AUTO_CONFIRM", "1")
        import importlib
        import config
        importlib.reload(config)
        assert config.AUTO_CONFIRM is False  # 只有 "true" 才为真

    def test_auto_confirm_false(self, monkeypatch, clean_env):
        monkeypatch.setenv("CODE_AGENT_AUTO_CONFIRM", "false")
        import importlib
        import config
        importlib.reload(config)
        assert config.AUTO_CONFIRM is False

    def test_auto_confirm_empty(self, monkeypatch, clean_env):
        monkeypatch.setenv("CODE_AGENT_AUTO_CONFIRM", "")
        import importlib
        import config
        importlib.reload(config)
        assert config.AUTO_CONFIRM is False
