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
        from config import LLM_MODEL, DEFAULT_LLM_MODEL
        assert DEFAULT_LLM_MODEL == "qwen3.5:4b"
        assert LLM_MODEL == DEFAULT_LLM_MODEL

    def test_llm_think_default_false(self, clean_env):
        from config import LLM_THINK
        assert LLM_THINK is False

    def test_llm_think_env_true(self, monkeypatch, clean_env):
        import importlib
        import config
        monkeypatch.setenv("LLM_THINK", "true")
        importlib.reload(config)
        try:
            assert config.LLM_THINK is True
        finally:
            monkeypatch.delenv("LLM_THINK", raising=False)
            importlib.reload(config)

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
        assert TOP_K == 10

    def test_similarity_cutoff_default(self, clean_env):
        from config import SIMILARITY_CUTOFF
        assert SIMILARITY_CUTOFF == 0.3

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


class TestProgressConfig:
    """测试进度显示配置"""

    def test_show_progress_default(self, clean_env):
        from config import SHOW_PROGRESS
        assert SHOW_PROGRESS is True

    def test_progress_bar_style_default(self, clean_env):
        from config import PROGRESS_BAR_STYLE
        assert PROGRESS_BAR_STYLE == "rich"

    def test_estimate_time_default(self, clean_env):
        from config import ESTIMATE_TIME
        assert ESTIMATE_TIME is True

    def test_show_stats_default(self, clean_env):
        from config import SHOW_STATS
        assert SHOW_STATS is False

    def test_verbose_mode_default(self, clean_env):
        from config import VERBOSE_MODE
        assert VERBOSE_MODE is False

    def test_show_progress_override_true(self, monkeypatch, clean_env):
        monkeypatch.setenv("SHOW_PROGRESS", "true")
        import importlib
        import config
        importlib.reload(config)
        assert config.SHOW_PROGRESS is True

    def test_show_progress_override_false(self, monkeypatch, clean_env):
        monkeypatch.setenv("SHOW_PROGRESS", "false")
        import importlib
        import config
        importlib.reload(config)
        assert config.SHOW_PROGRESS is False

    def test_progress_bar_style_override_rich(self, monkeypatch, clean_env):
        monkeypatch.setenv("PROGRESS_BAR_STYLE", "rich")
        import importlib
        import config
        importlib.reload(config)
        assert config.PROGRESS_BAR_STYLE == "rich"

    def test_progress_bar_style_override_simple(self, monkeypatch, clean_env):
        monkeypatch.setenv("PROGRESS_BAR_STYLE", "simple")
        import importlib
        import config
        importlib.reload(config)
        assert config.PROGRESS_BAR_STYLE == "simple"

    def test_estimate_time_override_true(self, monkeypatch, clean_env):
        monkeypatch.setenv("ESTIMATE_TIME", "true")
        import importlib
        import config
        importlib.reload(config)
        assert config.ESTIMATE_TIME is True

    def test_estimate_time_override_false(self, monkeypatch, clean_env):
        monkeypatch.setenv("ESTIMATE_TIME", "false")
        import importlib
        import config
        importlib.reload(config)
        assert config.ESTIMATE_TIME is False

    def test_show_stats_override_true(self, monkeypatch, clean_env):
        monkeypatch.setenv("SHOW_STATS", "true")
        import importlib
        import config
        importlib.reload(config)
        assert config.SHOW_STATS is True

    def test_verbose_mode_override_true(self, monkeypatch, clean_env):
        monkeypatch.setenv("VERBOSE_MODE", "true")
        import importlib
        import config
        importlib.reload(config)
        assert config.VERBOSE_MODE is True

    def test_config_dataclass_progress_config(self, clean_env):
        # 由于环境变量的缓存特性，需要重新导入 Config
        import importlib
        import config
        importlib.reload(config)
        
        # 确保 VERBOSE_MODE 被正确重置为默认值
        if "VERBOSE_MODE" in os.environ:
            del os.environ["VERBOSE_MODE"]
        
        importlib.reload(config)
        
        assert config.SHOW_PROGRESS is True
        assert config.PROGRESS_BAR_STYLE == "rich"
        assert config.ESTIMATE_TIME is True
        assert config.SHOW_STATS is False
        assert config.VERBOSE_MODE is False


class TestResolveNumCtx:
    """按模型规格自动推导上下文窗口（num_ctx）。"""

    def test_small_model_large_ctx(self, clean_env):
        from config import resolve_num_ctx
        assert resolve_num_ctx("qwen3.5:4b") == 16384
        assert resolve_num_ctx("qwen3.5:1.5b") == 16384

    def test_default_model_ctx(self, clean_env):
        from config import resolve_num_ctx, DEFAULT_LLM_MODEL
        assert resolve_num_ctx(DEFAULT_LLM_MODEL) == 16384

    def test_unusual_model_naming(self, clean_env):
        """形如 SparkLLM/Spark-X2.5-4B 的命名：大写 B、以连字符分隔、带 x2.5 版本号，
        必须识别为 4B 而不是把 2.5 误当参数量。"""
        from config import resolve_num_ctx
        assert resolve_num_ctx("SparkLLM/Spark-X2.5-4B") == 16384
        assert resolve_num_ctx("SparkLLM/Spark-X2.5-7B") == 8192
        assert resolve_num_ctx("SparkLLM/Spark-X2.5-14B") == 4096

    def test_mid_model_ctx(self, clean_env):
        from config import resolve_num_ctx
        assert resolve_num_ctx("qwen2.5-coder:7b") == 8192
        assert resolve_num_ctx("qwen3.5:8b") == 8192
        assert resolve_num_ctx("qwen3.5:9b") == 8192

    def test_large_model_small_ctx(self, clean_env):
        from config import resolve_num_ctx
        assert resolve_num_ctx("qwen2.5:14b") == 4096
        assert resolve_num_ctx("some-13b-model") == 4096
        # 更大的模型同样保守
        assert resolve_num_ctx("qwen2.5:32b") == 4096

    def test_unknown_model_defaults_large(self, clean_env):
        from config import resolve_num_ctx
        assert resolve_num_ctx("mystery-model") == 16384
        assert resolve_num_ctx("") == 16384

    def test_env_override(self, monkeypatch, clean_env):
        monkeypatch.setenv("LLM_NUM_CTX", "2048")
        from config import resolve_num_ctx
        # 覆盖对任何模型都生效
        assert resolve_num_ctx("qwen3.5:9b") == 2048
        assert resolve_num_ctx("qwen3.5:4b") == 2048

    def test_env_override_invalid_ignored(self, monkeypatch, clean_env):
        monkeypatch.setenv("LLM_NUM_CTX", "not-a-number")
        from config import resolve_num_ctx
        # 非法值忽略，回退按模型推导
        assert resolve_num_ctx("qwen3.5:4b") == 16384

    def test_llm_num_ctx_module_value(self, monkeypatch, clean_env):
        import importlib
        import config
        monkeypatch.setenv("LLM_MODEL", "qwen3.5:9b")
        importlib.reload(config)
        try:
            assert config.LLM_NUM_CTX == 8192
        finally:
            # 恢复干净的模块级 config，避免污染后续依赖 config.LLM_MODEL 的测试
            monkeypatch.delenv("LLM_MODEL", raising=False)
            importlib.reload(config)


class TestSetLlmModel:
    """运行时热切换全局模型。"""

    def test_switch_updates_module_and_config_class(self, monkeypatch, clean_env):
        import importlib
        import config
        importlib.reload(config)
        try:
            ctx = config.set_llm_model("qwen3.5:9b")
            assert ctx == 8192
            assert config.LLM_MODEL == "qwen3.5:9b"
            assert config.LLM_NUM_CTX == 8192
            assert config.Config.LLM_MODEL == "qwen3.5:9b"
            assert config.Config.MODEL == "qwen3.5:9b"
            assert os.environ["LLM_MODEL"] == "qwen3.5:9b"
        finally:
            monkeypatch.delenv("LLM_MODEL", raising=False)
            importlib.reload(config)

    def test_switch_followed_by_lazy_readers(self, monkeypatch, clean_env):
        """agent_config 等在调用时才 import config 的模块应自动跟随新模型。"""
        import importlib
        import config
        importlib.reload(config)
        try:
            config.set_llm_model("qwen3.5:9b")
            from agent_config import _default_model
            assert _default_model() == "qwen3.5:9b"
        finally:
            monkeypatch.delenv("LLM_MODEL", raising=False)
            importlib.reload(config)

    def test_switch_rejects_empty(self, clean_env):
        import config
        with pytest.raises(ValueError):
            config.set_llm_model("   ")
