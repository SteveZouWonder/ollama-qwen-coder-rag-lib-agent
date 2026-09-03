#!/usr/bin/env python3
"""test_model_switcher.py — 运行时模型热切换。"""
import importlib
from unittest.mock import MagicMock, patch

import pytest

import config
import model_switcher as ms


@pytest.fixture
def clean_config():
    """每个用例前后恢复干净的 config 模块与环境变量。

    注意不能用 monkeypatch.delenv 做清理：它会把清理时刻的（已污染）值记录为
    "原值"并在 fixture 结束后恢复回去，导致污染泄漏到其他测试文件。
    """
    import os

    def _reset():
        os.environ.pop("LLM_MODEL", None)
        os.environ.pop("LLM_THINK", None)
        importlib.reload(config)

    _reset()
    yield
    _reset()


# ==================== 名称解析 ====================

class TestResolveModelName:
    INSTALLED = ["qwen3.5:4b", "qwen3.5:9b", "nomic-embed-text:latest", "gemma4:latest"]

    def test_exact_match_case_insensitive(self):
        assert ms.resolve_model_name("QWEN3.5:4B", self.INSTALLED) == "qwen3.5:4b"

    def test_no_tag_prefers_latest(self):
        assert ms.resolve_model_name("gemma4", self.INSTALLED) == "gemma4:latest"

    def test_no_tag_unique_prefix(self):
        assert ms.resolve_model_name("nomic-embed-text", self.INSTALLED) == "nomic-embed-text:latest"

    def test_no_tag_ambiguous_returns_none(self):
        assert ms.resolve_model_name("qwen3.5", self.INSTALLED) is None

    def test_missing_returns_none(self):
        assert ms.resolve_model_name("llama9", self.INSTALLED) is None

    def test_empty_inputs(self):
        assert ms.resolve_model_name("", self.INSTALLED) is None
        assert ms.resolve_model_name("qwen3.5:4b", []) is None


class TestSuggestModels:
    def test_suggests_same_family(self):
        got = ms.suggest_models("qwen3.5:27b", ["qwen3.5:4b", "qwen3.5:9b", "gemma4:latest"])
        assert got == ["qwen3.5:4b", "qwen3.5:9b"]

    def test_falls_back_to_all(self):
        got = ms.suggest_models("zzz", ["a:1", "b:2"], limit=1)
        assert got == ["a:1"]

    def test_empty_request_lists_installed(self):
        assert ms.suggest_models("", ["a:1", "b:2"]) == ["a:1", "b:2"]


# ==================== Ollama 封装 ====================

class TestOllamaWrappers:
    @patch("bootstrap.list_installed_models", return_value=["x:1"])
    def test_list_installed_delegates_to_bootstrap(self, _m):
        assert ms.list_installed_models() == ["x:1"]

    def test_list_installed_swallow_errors(self):
        with patch("bootstrap.list_installed_models", side_effect=RuntimeError("boom")):
            assert ms.list_installed_models() == []

    @patch("requests.get")
    def test_list_loaded_models_parses_ps(self, mock_get):
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: {"models": [
                {"name": "qwen3.5:4b", "size": 3_900_000_000, "size_vram": 3_900_000_000,
                 "context_length": 16384},
            ]},
        )
        got = ms.list_loaded_models()
        assert got == [{"name": "qwen3.5:4b", "size": 3_900_000_000,
                        "size_vram": 3_900_000_000, "context": 16384}]
        assert mock_get.call_args[0][0].endswith("/api/ps")

    @patch("requests.get")
    def test_list_loaded_models_non_200(self, mock_get):
        mock_get.return_value = MagicMock(status_code=500)
        assert ms.list_loaded_models() == []

    @patch("requests.get", side_effect=ConnectionError("down"))
    def test_list_loaded_models_error(self, _m):
        assert ms.list_loaded_models() == []

    @patch("requests.post")
    def test_unload_model_sends_keep_alive_zero(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200)
        assert ms.unload_model("qwen3.5:4b") is True
        body = mock_post.call_args.kwargs["json"]
        assert body == {"model": "qwen3.5:4b", "keep_alive": 0}
        assert mock_post.call_args[0][0].endswith("/api/generate")

    @patch("requests.post", side_effect=ConnectionError("down"))
    def test_unload_model_error_false(self, _m):
        assert ms.unload_model("qwen3.5:4b") is False

    def test_unload_model_empty_false(self):
        assert ms.unload_model("") is False

    def test_format_size(self):
        assert ms.format_size(0) == "-"
        assert ms.format_size(3 * 1024 ** 3) == "3.0 GB"
        assert ms.format_size(300 * 1024 ** 2) == "300 MB"


# ==================== switch_model ====================

class TestSwitchModel:
    def test_empty_request(self, clean_config):
        r = ms.switch_model("")
        assert r.ok is False
        assert "请指定模型名" in r.message

    @patch("model_switcher.list_installed_models", return_value=[])
    def test_ollama_unreachable(self, _m, clean_config):
        r = ms.switch_model("qwen3.5:9b")
        assert r.ok is False
        assert "ollama serve" in r.message

    @patch("model_switcher.list_installed_models", return_value=["qwen3.5:4b"])
    def test_not_installed_with_suggestions(self, _m, clean_config):
        r = ms.switch_model("qwen3.5:9b")
        assert r.ok is False
        assert "未安装" in r.message
        assert "ollama pull qwen3.5:9b" in r.message
        assert r.candidates == ["qwen3.5:4b"]
        # 不应改动全局配置
        assert config.LLM_MODEL == "qwen3.5:4b"

    @patch("model_switcher.list_installed_models", return_value=["qwen3.5:4b", "qwen3.5:9b"])
    def test_ambiguous_family_asks_for_tag(self, _m, clean_config):
        r = ms.switch_model("qwen3.5")
        assert r.ok is False
        assert "多个已安装规格" in r.message
        assert r.candidates == ["qwen3.5:4b", "qwen3.5:9b"]
        assert config.LLM_MODEL == "qwen3.5:4b"

    @patch("model_switcher.unload_model")
    @patch("model_switcher.list_installed_models", return_value=["qwen3.5:4b", "qwen3.5:9b"])
    def test_same_model_noop(self, _m, mock_unload, clean_config):
        r = ms.switch_model("qwen3.5:4b")
        assert r.ok is True
        assert "无需切换" in r.message
        mock_unload.assert_not_called()

    @patch("model_switcher.unload_model", return_value=True)
    @patch("model_switcher.list_installed_models", return_value=["qwen3.5:4b", "qwen3.5:9b"])
    def test_switch_syncs_engines_and_unloads_previous(self, _m, mock_unload, clean_config):
        rag = MagicMock()
        react = MagicMock()
        r = ms.switch_model("qwen3.5:9b", rag_engine=rag, react_engine=react)

        assert r.ok is True
        assert r.model == "qwen3.5:9b"
        assert r.previous == "qwen3.5:4b"
        assert r.num_ctx == 8192
        assert r.unloaded_previous is True
        assert "已释放 qwen3.5:4b" in r.message
        rag.set_model.assert_called_once_with("qwen3.5:9b")
        react.set_model.assert_called_once_with("qwen3.5:9b")
        mock_unload.assert_called_once_with("qwen3.5:4b")
        # 全局 config 同步
        assert config.LLM_MODEL == "qwen3.5:9b"
        assert config.LLM_NUM_CTX == 8192
        assert config.Config.LLM_MODEL == "qwen3.5:9b"

    @patch("model_switcher.unload_model", return_value=True)
    @patch("model_switcher.list_installed_models", return_value=["qwen3.5:4b", "qwen3.5:9b"])
    def test_switch_without_unload(self, _m, mock_unload, clean_config):
        r = ms.switch_model("qwen3.5:9b", unload_previous=False)
        assert r.ok is True
        assert r.unloaded_previous is False
        mock_unload.assert_not_called()

    @patch("model_switcher.unload_model", return_value=False)
    @patch("model_switcher.list_installed_models", return_value=["qwen3.5:4b", "qwen3.5:9b"])
    def test_engine_failure_reported(self, _m, _u, clean_config):
        rag = MagicMock()
        rag.set_model.side_effect = RuntimeError("no ollama")
        r = ms.switch_model("qwen3.5:9b", rag_engine=rag)
        assert r.ok is False
        assert "RAG 引擎切换失败" in r.message
        # config 仍已切换（引擎失败不回滚，保持与 CLI --model 行为一致）
        assert config.LLM_MODEL == "qwen3.5:9b"

    @patch("model_switcher.unload_model", return_value=False)
    def test_skip_install_check(self, _u, clean_config):
        r = ms.switch_model("whatever:latest", require_installed=False)
        assert r.ok is True
        assert config.LLM_MODEL == "whatever:latest"

    @patch("model_switcher.unload_model", return_value=True)
    @patch("model_switcher.list_installed_models", return_value=["qwen3.5:4b", "qwen3.5:9b"])
    def test_engines_without_set_model_are_ignored(self, _m, _u, clean_config):
        r = ms.switch_model("qwen3.5:9b", rag_engine=object(), react_engine=object())
        assert r.ok is True


# ==================== current_model_info ====================

class TestCurrentModelInfo:
    @patch("model_switcher.list_loaded_models")
    def test_loaded(self, mock_ps, clean_config):
        mock_ps.return_value = [
            {"name": "qwen3.5:4b", "size": 4_000_000_000, "size_vram": 0, "context": 16384},
            {"name": "qwen2.5-coder:7b", "size": 5_000_000_000, "size_vram": 0, "context": 8192},
        ]
        info = ms.current_model_info()
        assert info["model"] == "qwen3.5:4b"
        assert info["num_ctx"] == 16384
        assert info["think"] is False
        assert info["loaded"] is True
        assert info["size_bytes"] == 4_000_000_000
        assert info["loaded_models"] == ["qwen3.5:4b", "qwen2.5-coder:7b"]

    @patch("model_switcher.list_loaded_models", return_value=[])
    def test_not_loaded(self, _m, clean_config):
        info = ms.current_model_info()
        assert info["loaded"] is False
        assert info["size_bytes"] == 0


# ==================== 思考模式开关 ====================

class TestParseThinkFlag:
    @pytest.mark.parametrize("word", ["on", "ON", "true", "1", "yes", "开", "开启"])
    def test_true_words(self, word):
        assert ms.parse_think_flag(word) is True

    @pytest.mark.parametrize("word", ["off", "false", "0", "no", "关", "关闭"])
    def test_false_words(self, word):
        assert ms.parse_think_flag(word) is False

    @pytest.mark.parametrize("word", ["", "maybe", "开关"])
    def test_unknown(self, word):
        assert ms.parse_think_flag(word) is None


class TestModelSupportsThinking:
    @patch("requests.post")
    def test_supported(self, mock_post):
        mock_post.return_value = MagicMock(
            status_code=200, json=lambda: {"capabilities": ["completion", "tools", "thinking"]}
        )
        assert ms.model_supports_thinking("qwen3.5:4b") is True
        assert mock_post.call_args.kwargs["json"] == {"model": "qwen3.5:4b"}
        assert mock_post.call_args[0][0].endswith("/api/show")

    @patch("requests.post")
    def test_not_supported(self, mock_post):
        mock_post.return_value = MagicMock(
            status_code=200, json=lambda: {"capabilities": ["completion", "tools"]}
        )
        assert ms.model_supports_thinking("qwen2.5-coder:7b") is False

    @patch("requests.post")
    def test_unknown_on_error(self, mock_post):
        mock_post.return_value = MagicMock(status_code=404)
        assert ms.model_supports_thinking("x") is None
        mock_post.side_effect = ConnectionError("down")
        assert ms.model_supports_thinking("x") is None

    def test_uses_config_model_when_omitted(self, clean_config):
        with patch("requests.post") as mock_post:
            mock_post.return_value = MagicMock(status_code=200, json=lambda: {"capabilities": []})
            ms.model_supports_thinking()
            assert mock_post.call_args.kwargs["json"] == {"model": "qwen3.5:4b"}

    def test_empty_model(self, clean_config):
        with patch.object(config, "LLM_MODEL", ""):
            assert ms.model_supports_thinking("") is None


class TestSwitchThink:
    @patch("model_switcher.model_supports_thinking", return_value=True)
    def test_enable_syncs_engines(self, _cap, clean_config):
        rag, react = MagicMock(), MagicMock()
        r = ms.switch_think(True, rag_engine=rag, react_engine=react)
        assert r.ok is True and r.enabled is True and r.changed is True
        assert "已开启" in r.message
        rag.set_think.assert_called_once_with(True)
        react.set_think.assert_called_once_with(True)
        assert config.LLM_THINK is True
        import os
        assert os.environ.get("LLM_THINK") == "true"

    @patch("model_switcher.model_supports_thinking", return_value=False)
    def test_enable_rejected_when_unsupported(self, _cap, clean_config):
        rag = MagicMock()
        r = ms.switch_think(True, rag_engine=rag)
        assert r.ok is False and r.enabled is False and r.changed is False
        assert "不支持思考模式" in r.message
        rag.set_think.assert_not_called()
        assert config.LLM_THINK is False

    @patch("model_switcher.model_supports_thinking", return_value=None)
    def test_enable_with_unknown_capability_warns(self, _cap, clean_config):
        r = ms.switch_think(True)
        assert r.ok is True and r.enabled is True
        assert "无法确认" in r.message

    @patch("model_switcher.model_supports_thinking")
    def test_disable_skips_capability_check(self, mock_cap, clean_config):
        config.set_llm_think(True)
        r = ms.switch_think(False)
        assert r.ok is True and r.enabled is False and r.changed is True
        assert "已关闭" in r.message
        mock_cap.assert_not_called()
        assert config.LLM_THINK is False

    def test_noop_when_same(self, clean_config):
        r = ms.switch_think(False)
        assert r.ok is True and r.changed is False
        assert "已是关" in r.message

    @patch("model_switcher.model_supports_thinking", return_value=True)
    def test_engine_error_reported(self, _cap, clean_config):
        rag = MagicMock()
        rag.set_think.side_effect = RuntimeError("boom")
        r = ms.switch_think(True, rag_engine=rag)
        assert r.ok is False
        assert "RAG 引擎设置失败" in r.message

    @patch("model_switcher.model_supports_thinking", return_value=True)
    def test_engines_without_set_think_ignored(self, _cap, clean_config):
        r = ms.switch_think(True, rag_engine=object(), react_engine=object())
        assert r.ok is True

    def test_skip_capability_check_flag(self, clean_config):
        with patch("model_switcher.model_supports_thinking") as mock_cap:
            r = ms.switch_think(True, check_capability=False)
            assert r.ok is True
            mock_cap.assert_not_called()
