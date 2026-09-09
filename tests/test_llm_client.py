#!/usr/bin/env python3
"""
test_llm_client.py — F10 P1-2 LLM 后端抽象层（Ollama / OpenAI 兼容）

Mock ``requests.post`` / ``requests.get``，不触碰真实 Ollama 或任何网络服务。覆盖：
两种 client 的 普通 / 流式 / 超时 / 401 / 5xx / 非法 JSON；``OpenAICompatClient`` 的 options 映射；
工厂按 env 选择并缓存；``available_models`` 回退；五处调用点在 openai 模式下的请求形态；
``commit_generator`` 两种 provider 下的成功与回退；CLI / Web / 托盘 / bootstrap 的 provider 感知。
"""
import json
import logging
from unittest.mock import MagicMock, patch

import pytest
import requests

import llm_client
from llm_client import (
    LLMError,
    OllamaClient,
    OpenAICompatClient,
    available_models,
    client_for_host,
    connection_error_hint,
    consume_sse_stream,
    describe_backend,
    get_llm_client,
    reset_llm_client,
)


# ---------------------------------------------------------------------------
# 工具
# ---------------------------------------------------------------------------

def _resp(status=200, payload=None, text="", raw_json_error=False):
    r = MagicMock()
    r.status_code = status
    r.text = text
    if raw_json_error:
        r.json.side_effect = ValueError("bad json")
    else:
        r.json.return_value = payload if payload is not None else {}
    return r


def _ndjson(chunks, error=None, done=True):
    lines = [json.dumps({"message": {"content": c}, "done": False}).encode() for c in chunks]
    if error is not None:
        lines.append(json.dumps({"error": error}).encode())
    elif done:
        lines.append(b"")
        lines.append(json.dumps({"message": {"content": ""}, "done": True}).encode())
    r = MagicMock()
    r.status_code = 200
    r.iter_lines.return_value = iter(lines)
    return r


def _sse(chunks, error=None, done=True, extra_lines=()):
    lines = [b": keep-alive", b"event: message"]
    for c in chunks:
        lines.append(("data: " + json.dumps({"choices": [{"delta": {"content": c}}]})).encode())
    lines.extend(extra_lines)
    if error is not None:
        lines.append(("data: " + json.dumps({"error": {"message": error}})).encode())
    elif done:
        lines.append(b"")
        lines.append(b"data: [DONE]")
    r = MagicMock()
    r.status_code = 200
    r.iter_lines.return_value = iter(lines)
    return r


@pytest.fixture(autouse=True)
def _reset_client():
    reset_llm_client()
    yield
    reset_llm_client()


@pytest.fixture
def openai_env(monkeypatch):
    import config
    monkeypatch.setattr(config, "LLM_PROVIDER", "openai")
    monkeypatch.setattr(config, "LLM_BASE_URL", "http://lmstudio:1234")
    monkeypatch.setattr(config, "LLM_API_KEY", "sk-test")
    monkeypatch.setattr(config, "LLM_MODEL", "local-model")
    reset_llm_client()
    yield
    reset_llm_client()


@pytest.fixture
def ollama_env(monkeypatch):
    import config
    monkeypatch.setattr(config, "LLM_PROVIDER", "ollama")
    monkeypatch.setattr(config, "LLM_BASE_URL", "http://localhost:11434")
    monkeypatch.setattr(config, "LLM_API_KEY", "")
    monkeypatch.setattr(config, "OLLAMA_BASE_URL", "http://localhost:11434")
    reset_llm_client()
    yield
    reset_llm_client()


def set_stream(monkeypatch, value: bool) -> None:
    import config as cfg_mod
    monkeypatch.setattr(cfg_mod.Config, "LLM_STREAM", value)


# ===========================================================================
# OllamaClient
# ===========================================================================

class TestOllamaClient:
    def test_plain_chat_payload_and_no_stream_kwarg(self):
        client = OllamaClient("http://h:1/")
        with patch("requests.post", return_value=_resp(200, {"message": {"content": "hi"}})) as post:
            out = client.chat([{"role": "user", "content": "q"}], model="m",
                              options={"temperature": 0.3, "num_ctx": 8, "num_predict": 9}, think=False, timeout=7)
        assert out == "hi"
        assert post.call_args[0][0] == "http://h:1/api/chat"
        kw = post.call_args.kwargs
        assert "stream" not in kw and kw["timeout"] == 7
        assert kw["json"] == {"model": "m", "messages": [{"role": "user", "content": "q"}], "stream": False,
                              "think": False, "options": {"temperature": 0.3, "num_ctx": 8, "num_predict": 9}}

    def test_default_model_from_config(self, monkeypatch):
        import config
        monkeypatch.setattr(config, "LLM_MODEL", "cfg-model")
        with patch("requests.post", return_value=_resp(200, {"message": {"content": "x"}})) as post:
            OllamaClient("http://h").chat([{"role": "user", "content": "q"}])
        assert post.call_args.kwargs["json"]["model"] == "cfg-model"

    def test_streaming_tokens_concat_and_on_response(self, monkeypatch):
        set_stream(monkeypatch, True)
        seen, hooked = [], []
        resp = _ndjson(["a", "b", "c"])
        with patch("requests.post", return_value=resp) as post:
            out = OllamaClient("http://h").chat([{"role": "user", "content": "q"}], model="m",
                                               on_token=seen.append, on_response=hooked.append)
        assert out == "abc" and seen == ["a", "b", "c"]
        assert hooked == [resp]
        assert post.call_args.kwargs["stream"] is True and post.call_args.kwargs["json"]["stream"] is True
        resp.close.assert_called()

    def test_stream_disabled_single_callback(self, monkeypatch):
        set_stream(monkeypatch, False)
        seen = []
        with patch("requests.post", return_value=_resp(200, {"message": {"content": "full"}})) as post:
            assert OllamaClient("http://h").chat([{"role": "user", "content": "q"}], on_token=seen.append) == "full"
        assert seen == ["full"] and "stream" not in post.call_args.kwargs

    def test_stream_should_stop(self, monkeypatch):
        set_stream(monkeypatch, True)
        seen, flag = [], {"stop": False}

        def on_token(d):
            seen.append(d)
            flag["stop"] = True

        with patch("requests.post", return_value=_ndjson(["a", "b"])):
            out = OllamaClient("http://h").chat([{"role": "user", "content": "q"}], on_token=on_token,
                                               should_stop=lambda: flag["stop"])
        assert out == "a" and seen == ["a"]

    def test_stream_error_line_raises_llmerror(self, monkeypatch):
        set_stream(monkeypatch, True)
        with patch("requests.post", return_value=_ndjson(["a"], error="model not found")):
            with pytest.raises(LLMError, match="model not found"):
                OllamaClient("http://h").chat([{"role": "user", "content": "q"}], on_token=lambda d: None)

    def test_timeout_propagates(self):
        with patch("requests.post", side_effect=requests.exceptions.Timeout()):
            with pytest.raises(requests.exceptions.Timeout):
                OllamaClient("http://h").chat([{"role": "user", "content": "q"}])

    def test_connection_error_propagates(self):
        with patch("requests.post", side_effect=requests.exceptions.ConnectionError()):
            with pytest.raises(requests.exceptions.ConnectionError):
                OllamaClient("http://h").chat([{"role": "user", "content": "q"}])

    def test_401(self):
        with patch("requests.post", return_value=_resp(401, {"error": "unauthorized"})):
            with pytest.raises(LLMError) as ei:
                OllamaClient("http://h").chat([{"role": "user", "content": "q"}])
        assert ei.value.status_code == 401 and "401" in str(ei.value) and "unauthorized" in str(ei.value)

    def test_5xx_with_text_body(self):
        with patch("requests.post", return_value=_resp(502, raw_json_error=True, text="bad gateway")):
            with pytest.raises(LLMError) as ei:
                OllamaClient("http://h").chat([{"role": "user", "content": "q"}])
        assert ei.value.status_code == 502 and "502" in str(ei.value) and "bad gateway" in str(ei.value)

    def test_5xx_streaming_raises_before_hook(self, monkeypatch):
        set_stream(monkeypatch, True)
        hooked = []
        with patch("requests.post", return_value=_resp(500, {"error": "boom"})):
            with pytest.raises(LLMError):
                OllamaClient("http://h").chat([{"role": "user", "content": "q"}], on_token=lambda d: None,
                                             on_response=hooked.append)
        assert hooked == []

    def test_invalid_json(self):
        with patch("requests.post", return_value=_resp(200, raw_json_error=True)):
            with pytest.raises(LLMError, match="JSON"):
                OllamaClient("http://h").chat([{"role": "user", "content": "q"}])

    def test_non_dict_json_returns_empty(self):
        r = _resp(200)
        r.json.return_value = ["not", "dict"]
        with patch("requests.post", return_value=r):
            assert OllamaClient("http://h").chat([{"role": "user", "content": "q"}]) == ""

    def test_list_models_and_health(self):
        with patch("requests.get", return_value=_resp(200, {"models": [{"name": "a:1"}, {"name": "b:2"}, "junk"]})) as get:
            client = OllamaClient("http://h")
            assert client.list_models() == ["a:1", "b:2"]
            assert client.health() is True
        assert get.call_args[0][0] == "http://h/api/tags"
        with patch("requests.get", side_effect=ConnectionError("down")):
            assert OllamaClient("http://h").health() is False
            with pytest.raises(ConnectionError):
                OllamaClient("http://h").list_models()
        with patch("requests.get", return_value=_resp(500, {"error": "x"})):
            with pytest.raises(LLMError):
                OllamaClient("http://h").list_models()

    def test_unload(self):
        with patch("requests.post", return_value=_resp(200)) as post:
            assert OllamaClient("http://h").unload("m:1") is True
        assert post.call_args[0][0] == "http://h/api/generate"
        assert post.call_args.kwargs["json"] == {"model": "m:1", "keep_alive": 0}
        assert OllamaClient("http://h").unload("") is False
        with patch("requests.post", side_effect=ConnectionError("down")):
            assert OllamaClient("http://h").unload("m") is False


# ===========================================================================
# OpenAICompatClient
# ===========================================================================

class TestOpenAICompatClient:
    def test_base_url_normalization(self):
        assert OpenAICompatClient("http://h:1234/").base_url == "http://h:1234"
        assert OpenAICompatClient("http://h:1234/v1").base_url == "http://h:1234"
        assert OpenAICompatClient("http://h:1234/v1/").base_url == "http://h:1234"
        assert OpenAICompatClient("http://h:1234")._url("/models") == "http://h:1234/v1/models"

    def test_plain_chat_payload_headers_and_options_mapping(self):
        OpenAICompatClient._warned_num_ctx = False
        client = OpenAICompatClient("http://h:1234", api_key="sk-x")
        body = {"choices": [{"message": {"role": "assistant", "content": "hello"}}]}
        with patch("requests.post", return_value=_resp(200, body)) as post:
            out = client.chat([{"role": "user", "content": "q"}], model="m", think=True,
                              options={"temperature": 0.3, "num_ctx": 16384, "num_predict": 77, "mirostat": 1},
                              timeout=5)
        assert out == "hello"
        assert post.call_args[0][0] == "http://h:1234/v1/chat/completions"
        kw = post.call_args.kwargs
        assert kw["headers"]["Authorization"] == "Bearer sk-x"
        assert kw["timeout"] == 5 and "stream" not in kw
        # think=True 不发送任何字段；num_ctx 忽略、num_predict→max_tokens、未知键忽略
        assert kw["json"] == {"model": "m", "messages": [{"role": "user", "content": "q"}], "stream": False,
                              "temperature": 0.3, "max_tokens": 77}
        assert "think" not in kw["json"] and "num_ctx" not in kw["json"] and "options" not in kw["json"]
        assert "reasoning_effort" not in kw["json"]

    def test_think_false_maps_to_reasoning_effort_none(self):
        client = OpenAICompatClient("http://h")
        with patch("requests.post", return_value=_resp(200, {"choices": [{"message": {"content": "x"}}]})) as post:
            client.chat([{"role": "user", "content": "q"}], model="m", think=False)
        assert post.call_args.kwargs["json"]["reasoning_effort"] == "none"
        assert "think" not in post.call_args.kwargs["json"]

    def test_reasoning_effort_rejected_retries_once_and_remembers(self):
        client = OpenAICompatClient("http://h")
        ok = _resp(200, {"choices": [{"message": {"content": "x"}}]})
        bad = _resp(400, {"error": {"message": "Unrecognized request argument: reasoning_effort"}})
        with patch("requests.post", side_effect=[bad, ok]) as post:
            assert client.chat([{"role": "user", "content": "q"}], model="m") == "x"
        assert post.call_count == 2
        assert "reasoning_effort" in post.call_args_list[0].kwargs["json"]
        assert "reasoning_effort" not in post.call_args_list[1].kwargs["json"]
        assert client._reasoning_effort_unsupported is True
        # 之后不再发送、也不再重试
        with patch("requests.post", return_value=ok) as post2:
            client.chat([{"role": "user", "content": "q"}], model="m")
        assert post2.call_count == 1 and "reasoning_effort" not in post2.call_args.kwargs["json"]

    def test_400_for_other_reason_not_remembered(self):
        client = OpenAICompatClient("http://h")
        bad = _resp(400, {"error": {"message": "context length exceeded"}})
        with patch("requests.post", return_value=bad):
            with pytest.raises(LLMError, match="400"):
                client.chat([{"role": "user", "content": "q"}], model="m")
        # 重试去掉字段后仍 400 → 抛出真实错误，且不把后端标记为"不支持"
        assert client._reasoning_effort_unsupported is False

    def test_reasoning_effort_setting_configurable(self, monkeypatch):
        import config
        ok = _resp(200, {"choices": [{"message": {"content": "x"}}]})
        monkeypatch.setattr(config, "LLM_REASONING_EFFORT", "low")
        with patch("requests.post", return_value=ok) as post:
            OpenAICompatClient("http://h").chat([{"role": "user", "content": "q"}], model="m")
        assert post.call_args.kwargs["json"]["reasoning_effort"] == "low"
        monkeypatch.setattr(config, "LLM_REASONING_EFFORT", "")
        with patch("requests.post", return_value=ok) as post:
            OpenAICompatClient("http://h").chat([{"role": "user", "content": "q"}], model="m")
        assert "reasoning_effort" not in post.call_args.kwargs["json"]
        assert llm_client.reasoning_effort_setting() == ""

    def test_400_with_think_true_not_retried(self):
        client = OpenAICompatClient("http://h")
        bad = _resp(400, {"error": "x"})
        with patch("requests.post", return_value=bad) as post:
            with pytest.raises(LLMError):
                client.chat([{"role": "user", "content": "q"}], model="m", think=True)
        assert post.call_count == 1

    def test_no_api_key_no_auth_header(self):
        with patch("requests.post", return_value=_resp(200, {"choices": [{"message": {"content": "x"}}]})) as post:
            OpenAICompatClient("http://h").chat([{"role": "user", "content": "q"}], model="m")
        assert "Authorization" not in post.call_args.kwargs["headers"]

    def test_num_ctx_debug_logged_once(self, caplog):
        OpenAICompatClient._warned_num_ctx = False
        with caplog.at_level(logging.DEBUG, logger="llm_client"):
            OpenAICompatClient.map_options({"num_ctx": 1})
            OpenAICompatClient.map_options({"num_ctx": 2})
        msgs = [r.getMessage() for r in caplog.records if "num_ctx" in r.getMessage()]
        assert len(msgs) == 1 and OpenAICompatClient._warned_num_ctx is True
        assert OpenAICompatClient.map_options({"num_predict": "abc"}) == {}

    def test_streaming_sse(self, monkeypatch):
        set_stream(monkeypatch, True)
        seen, hooked = [], []
        resp = _sse(["he", "llo"], extra_lines=[b"data: not json", b"data: [1,2]",
                                                 ("data: " + json.dumps({"choices": []})).encode()])
        with patch("requests.post", return_value=resp) as post:
            out = OpenAICompatClient("http://h", api_key="k").chat(
                [{"role": "user", "content": "q"}], model="m", on_token=seen.append, on_response=hooked.append)
        assert out == "hello" and seen == ["he", "llo"] and hooked == [resp]
        assert post.call_args.kwargs["stream"] is True and post.call_args.kwargs["json"]["stream"] is True
        resp.close.assert_called()

    def test_streaming_error_chunk(self, monkeypatch):
        set_stream(monkeypatch, True)
        with patch("requests.post", return_value=_sse(["a"], error="context length exceeded")):
            with pytest.raises(LLMError, match="context length exceeded"):
                OpenAICompatClient("http://h").chat([{"role": "user", "content": "q"}], on_token=lambda d: None)

    def test_streaming_bare_json_error_line_and_string_error(self):
        r = MagicMock()
        r.iter_lines.return_value = iter([json.dumps({"error": "plain"}).encode()])
        with pytest.raises(LLMError, match="plain"):
            consume_sse_stream(r, lambda d: None)
        r.close.assert_called()

    def test_streaming_should_stop_swallows_read_error(self):
        r = MagicMock()
        flag = {"stop": False}

        def lines():
            yield ("data: " + json.dumps({"choices": [{"delta": {"content": "x"}}]})).encode()
            flag["stop"] = True
            raise ConnectionResetError("closed")

        r.iter_lines.return_value = lines()
        assert consume_sse_stream(r, lambda d: None, should_stop=lambda: flag["stop"]) == "x"
        r.close.assert_called()

    def test_streaming_read_error_without_stop_raises(self):
        r = MagicMock()

        def lines():
            yield b"data: {}"
            raise OSError("broken pipe")

        r.iter_lines.return_value = lines()
        with pytest.raises(OSError):
            consume_sse_stream(r, lambda d: None)
        r.close.assert_called()

    def test_stream_disabled_single_callback(self, monkeypatch):
        set_stream(monkeypatch, False)
        seen = []
        with patch("requests.post", return_value=_resp(200, {"choices": [{"message": {"content": "full"}}]})) as post:
            assert OpenAICompatClient("http://h").chat([{"role": "user", "content": "q"}], on_token=seen.append) == "full"
        assert seen == ["full"] and post.call_args.kwargs["json"]["stream"] is False

    def test_timeout_propagates(self):
        with patch("requests.post", side_effect=requests.exceptions.Timeout()):
            with pytest.raises(requests.exceptions.Timeout):
                OpenAICompatClient("http://h").chat([{"role": "user", "content": "q"}])

    def test_401_mentions_api_key(self):
        with patch("requests.post", return_value=_resp(401, {"error": {"message": "Invalid API key"}})):
            with pytest.raises(LLMError) as ei:
                OpenAICompatClient("http://h", api_key="bad").chat([{"role": "user", "content": "q"}])
        assert ei.value.status_code == 401 and "LLM_API_KEY" in str(ei.value) and "Invalid API key" in str(ei.value)

    def test_404_and_4xx(self):
        with patch("requests.post", return_value=_resp(404, {"error": {"message": "no model"}})):
            with pytest.raises(LLMError, match="404"):
                OpenAICompatClient("http://h").chat([{"role": "user", "content": "q"}])
        with patch("requests.post", return_value=_resp(429, {"error": "rate"})):
            with pytest.raises(LLMError, match="429"):
                OpenAICompatClient("http://h").chat([{"role": "user", "content": "q"}])

    def test_5xx(self):
        with patch("requests.post", return_value=_resp(503, {"error": {"message": "overloaded"}})):
            with pytest.raises(LLMError) as ei:
                OpenAICompatClient("http://h").chat([{"role": "user", "content": "q"}])
        assert ei.value.status_code == 503 and "overloaded" in str(ei.value)

    def test_invalid_json_and_missing_choices(self):
        with patch("requests.post", return_value=_resp(200, raw_json_error=True)):
            with pytest.raises(LLMError, match="JSON"):
                OpenAICompatClient("http://h").chat([{"role": "user", "content": "q"}])
        with patch("requests.post", return_value=_resp(200, {"id": "x"})):
            with pytest.raises(LLMError, match="choices"):
                OpenAICompatClient("http://h").chat([{"role": "user", "content": "q"}])

    def test_list_models_and_health(self):
        with patch("requests.get", return_value=_resp(200, {"data": [{"id": "m1"}, {"id": "m2"}, {"x": 1}]})) as get:
            client = OpenAICompatClient("http://h", api_key="k")
            assert client.list_models() == ["m1", "m2"]
            assert client.health() is True
        assert get.call_args[0][0] == "http://h/v1/models"
        assert get.call_args.kwargs["headers"]["Authorization"] == "Bearer k"
        with patch("requests.get", return_value=_resp(404, {})):
            with pytest.raises(LLMError):
                OpenAICompatClient("http://h").list_models()
            assert OpenAICompatClient("http://h").health() is False
        with patch("requests.get", side_effect=ConnectionError("down")):
            assert OpenAICompatClient("http://h").health() is False


# ===========================================================================
# 工厂 / 配置
# ===========================================================================

class TestFactory:
    def test_default_is_ollama_with_ollama_url(self, ollama_env):
        client = get_llm_client()
        assert isinstance(client, OllamaClient) and client.base_url == "http://localhost:11434"
        assert get_llm_client() is client  # 缓存

    def test_openai_selected_and_cached(self, openai_env):
        client = get_llm_client()
        assert isinstance(client, OpenAICompatClient)
        assert client.base_url == "http://lmstudio:1234" and client.api_key == "sk-test"
        assert get_llm_client() is client

    def test_rebuild_when_config_changes(self, ollama_env, monkeypatch):
        import config
        first = get_llm_client()
        monkeypatch.setattr(config, "LLM_PROVIDER", "openai")
        second = get_llm_client()
        assert second is not first and isinstance(second, OpenAICompatClient)
        monkeypatch.setattr(config, "LLM_API_KEY", "changed")
        assert get_llm_client() is not second

    def test_base_url_defaults_to_ollama_url(self, monkeypatch):
        import config
        monkeypatch.setattr(config, "LLM_PROVIDER", "openai")
        monkeypatch.setattr(config, "LLM_BASE_URL", "")
        monkeypatch.setattr(config, "OLLAMA_BASE_URL", "http://ollama-host:11434")
        reset_llm_client()
        client = get_llm_client()
        assert client.base_url == "http://ollama-host:11434"

    def test_unknown_provider_falls_back_with_warning(self, monkeypatch, caplog):
        import config
        monkeypatch.setattr(config, "LLM_PROVIDER", "anthropic")
        monkeypatch.setattr(llm_client, "_warned_provider", None)
        reset_llm_client()
        with caplog.at_level(logging.WARNING, logger="llm_client"):
            client = get_llm_client()
            get_llm_client()
        assert isinstance(client, OllamaClient)
        assert sum("无法识别" in r.getMessage() for r in caplog.records) == 1
        assert llm_client.provider_name() == "ollama"

    def test_config_import_failure_defaults(self, monkeypatch):
        import builtins
        real_import = builtins.__import__

        def fake_import(name, *a, **k):
            if name == "config":
                raise ImportError("no config")
            return real_import(name, *a, **k)

        monkeypatch.setattr(builtins, "__import__", fake_import)
        assert llm_client._read_backend_config() == ("ollama", "http://localhost:11434", "")
        assert llm_client._current_model() == ""
        assert llm_client._default_timeout() == 300.0
        assert llm_client._stream_enabled() is True
        assert llm_client.ollama_client().base_url == "http://localhost:11434"
        assert describe_backend()["ollama_url"] == ""

    def test_client_for_host(self, ollama_env):
        g = get_llm_client()
        assert client_for_host(None) is g
        assert client_for_host("http://localhost:11434/") is g
        other = client_for_host("http://gpu-box:11434")
        assert isinstance(other, OllamaClient) and other.base_url == "http://gpu-box:11434"
        assert client_for_host("http://gpu-box:11434") is other  # 缓存

    def test_client_for_host_ignored_in_openai_mode(self, openai_env):
        g = get_llm_client()
        assert client_for_host("http://localhost:11434") is g

    def test_ollama_client_helper(self, openai_env, monkeypatch):
        import config
        monkeypatch.setattr(config, "OLLAMA_BASE_URL", "http://localhost:11434")
        oc = llm_client.ollama_client()
        assert isinstance(oc, OllamaClient) and oc.base_url == "http://localhost:11434"
        assert oc is not get_llm_client()
        monkeypatch.setattr(config, "LLM_PROVIDER", "ollama")
        monkeypatch.setattr(config, "LLM_BASE_URL", "http://localhost:11434")
        reset_llm_client()
        assert llm_client.ollama_client() is get_llm_client()

    def test_connection_error_hint(self, ollama_env, monkeypatch):
        assert "ollama serve" in connection_error_hint()
        import config
        monkeypatch.setattr(config, "LLM_PROVIDER", "openai")
        monkeypatch.setattr(config, "LLM_BASE_URL", "http://x:1")
        hint = connection_error_hint()
        assert "http://x:1" in hint and "LLM_PROVIDER=openai" in hint

    def test_describe_backend(self, openai_env):
        with patch("requests.get", return_value=_resp(200, {"data": []})):
            info = describe_backend(check_health=True)
        assert info["provider"] == "openai" and info["base_url"] == "http://lmstudio:1234"
        assert info["api_key_set"] is True and info["healthy"] is True and info["embed_via_ollama"] is True
        assert "healthy" not in describe_backend()
        with patch.object(OpenAICompatClient, "health", side_effect=RuntimeError("x")):
            assert describe_backend(check_health=True)["healthy"] is False

    def test_make_client(self):
        assert isinstance(llm_client.make_client("openai", "http://h", "k"), OpenAICompatClient)
        assert isinstance(llm_client.make_client("ollama", "http://h"), OllamaClient)


class TestAvailableModels:
    def test_ollama_ok_and_fallback(self, ollama_env):
        with patch("requests.get", return_value=_resp(200, {"models": [{"name": "a"}, {"name": ""}]})):
            r = available_models()
        assert r.names == ["a"] and r.fallback is False and r.notice == ""
        with patch("requests.get", side_effect=ConnectionError("down")):
            r = available_models()
        assert r.names == [] and r.fallback is True and "ollama serve" in r.notice

    def test_openai_fallback_to_current_model(self, openai_env):
        with patch("requests.get", return_value=_resp(404, {})):
            r = available_models()
        assert r.names == ["local-model"] and r.fallback is True
        assert llm_client.MODELS_UNAVAILABLE_NOTICE in r.notice and "local-model" in r.notice

    def test_openai_fallback_without_model(self, openai_env, monkeypatch):
        import config
        monkeypatch.setattr(config, "LLM_MODEL", "")
        with patch("requests.get", side_effect=ConnectionError("down")):
            assert available_models().names == []


# ===========================================================================
# 五处调用点在 openai 模式下的请求形态
# ===========================================================================

class TestCallSitesOpenAI:
    def test_react_engine_call_model_openai(self, openai_env, monkeypatch):
        from react_engine import ReActEngine
        from tests.test_react_engine import FakeContext

        set_stream(monkeypatch, True)
        engine = ReActEngine(context=FakeContext(), model="local-model")
        seen = []
        resp = _sse(["Final ", "Answer: ok"])
        with patch("requests.post", return_value=resp) as post:
            out = engine._call_model([{"role": "user", "content": "q"}], on_token=seen.append)
        assert out == "Final Answer: ok" and "".join(seen) == out
        assert post.call_args[0][0] == "http://lmstudio:1234/v1/chat/completions"
        body = post.call_args.kwargs["json"]
        assert "num_ctx" not in body and "think" not in body and body["reasoning_effort"] == "none"
        assert body["temperature"] == 0.3
        assert engine._active_response is None

    def test_react_engine_connection_error_hint_openai(self, openai_env):
        from react_engine import ReActEngine
        from tests.test_react_engine import FakeContext

        engine = ReActEngine(context=FakeContext())
        with patch("requests.post", side_effect=requests.exceptions.ConnectionError()):
            out = engine._call_model([{"role": "user", "content": "q"}])
        assert out.startswith("[错误]") and "http://lmstudio:1234" in out

    def test_react_engine_host_uses_dedicated_ollama_client(self, ollama_env):
        from react_engine import ReActEngine
        from tests.test_react_engine import FakeContext

        engine = ReActEngine(context=FakeContext(), host="http://other:11434")
        assert engine.llm_client.base_url == "http://other:11434"
        with patch("requests.post", return_value=_resp(200, {"message": {"content": "x"}})) as post:
            assert engine._call_model([{"role": "user", "content": "q"}]) == "x"
        assert post.call_args[0][0] == "http://other:11434/api/chat"

    def test_react_engine_stop_closes_openai_stream(self, openai_env, monkeypatch):
        from react_engine import ReActEngine
        from tests.test_react_engine import FakeContext

        set_stream(monkeypatch, True)
        engine = ReActEngine(context=FakeContext())
        resp = MagicMock()
        resp.status_code = 200

        def lines():
            yield ("data: " + json.dumps({"choices": [{"delta": {"content": "x"}}]})).encode()
            engine.stop()
            assert resp.close.called
            raise ConnectionResetError("closed")

        resp.iter_lines.return_value = lines()
        with patch("requests.post", return_value=resp):
            assert engine._call_model([{"role": "user", "content": "q"}], on_token=lambda d: None) == "x"

    def test_complete_text_openai(self, openai_env):
        from collaboration.llm_helper import complete_text

        body = {"choices": [{"message": {"content": "  ok  "}}]}
        with patch("requests.post", return_value=_resp(200, body)) as post:
            assert complete_text("p", num_predict=33, temperature=0.5) == "ok"
        b = post.call_args.kwargs["json"]
        assert b["max_tokens"] == 33 and b["temperature"] == 0.5 and b["messages"] == [{"role": "user", "content": "p"}]

    def test_complete_text_stream_disabled_callback_stripped(self, ollama_env, monkeypatch):
        from collaboration.llm_helper import complete_text

        set_stream(monkeypatch, False)
        seen = []
        with patch("requests.post", return_value=_resp(200, {"message": {"content": " full "}})):
            assert complete_text("p", on_token=seen.append) == "full"
        assert seen == ["full"]

    def test_conversation_context_default_complete_openai(self, openai_env):
        import conversation_context as cc

        with patch("requests.post", return_value=_resp(200, {"choices": [{"message": {"content": " 摘要 "}}]})) as post:
            assert cc._default_complete("p") == "摘要"
        assert post.call_args[0][0].endswith("/v1/chat/completions")
        assert post.call_args.kwargs["json"]["max_tokens"] == 512

    def test_desktop_warm_up_openai_and_llmerror(self, openai_env):
        from desktop_app import OllamaWarmer

        warmer = OllamaWarmer("http://lmstudio:1234", MagicMock())
        with patch("requests.post", return_value=_resp(200, {"choices": [{"message": {"content": "hi"}}]})) as post:
            r = warmer.warm_up(["local-model"])
        assert r["local-model"]["success"] is True
        assert post.call_args[0][0] == "http://lmstudio:1234/v1/chat/completions"
        assert post.call_args.kwargs["json"]["max_tokens"] == 1
        with patch("requests.post", return_value=_resp(503, {"error": {"message": "x"}})):
            r = warmer.warm_up(["local-model"])
        assert r["local-model"] == {"success": False, "error": "HTTP 503"}
        with patch("requests.post", return_value=_resp(200, raw_json_error=True)):
            r = warmer.warm_up(["local-model"])
        assert r["local-model"]["success"] is False and "JSON" in r["local-model"]["error"]

    def test_desktop_check_service_and_status_openai(self, openai_env, tmp_path):
        from desktop_app import OllamaWarmer, StatusMonitor

        with patch("requests.get", return_value=_resp(200, {"data": [{"id": "m1"}]})):
            assert OllamaWarmer("http://lmstudio:1234", MagicMock()).check_service() is True
            status = StatusMonitor("http://lmstudio:1234", MagicMock(), tmp_path / "s.log").check_status()
        assert status["ollama_service"] is True and status["models_loaded"] == ["m1"] and status["provider"] == "openai"
        with patch("requests.get", side_effect=ConnectionError("down")):
            assert OllamaWarmer("http://lmstudio:1234", MagicMock()).check_service() is False
            status = StatusMonitor("http://lmstudio:1234", MagicMock(), tmp_path / "s.log").check_status()
        assert status["ollama_service"] is False and status["models_loaded"] == []


# ===========================================================================
# commit_generator：两种 provider 的成功与回退
# ===========================================================================

class TestCommitGeneratorProviders:
    @pytest.mark.parametrize("provider", ["ollama", "openai"])
    def test_success(self, provider, ollama_env, monkeypatch):
        import config
        from git_integration import commit_generator as cg

        monkeypatch.setattr(config, "LLM_PROVIDER", provider)
        monkeypatch.setattr(config, "LLM_BASE_URL", "http://backend:1")
        reset_llm_client()
        payload = ({"message": {"content": "fix: bug\n\nbody"}} if provider == "ollama"
                   else {"choices": [{"message": {"content": "fix: bug\n\nbody"}}]})
        with patch("requests.post", return_value=_resp(200, payload)) as post:
            s = cg.CommitMessageGenerator(".", model="m")._generate_ai_commit_message("diff --git a b")
        assert s.title == "fix: bug" and s.body == "body" and s.conventional_type == "fix"
        url = post.call_args[0][0]
        assert url.endswith("/api/chat" if provider == "ollama" else "/v1/chat/completions")
        assert post.call_args.kwargs["timeout"] == 60
        body = post.call_args.kwargs["json"]
        if provider == "ollama":
            assert body["options"] == {"num_predict": 256} and body["think"] is False
        else:
            assert body["max_tokens"] == 256 and "think" not in body

    @pytest.mark.parametrize("provider", ["ollama", "openai"])
    @pytest.mark.parametrize("failure", ["http500", "timeout", "connection", "badjson", "empty"])
    def test_fallback(self, provider, failure, ollama_env, monkeypatch):
        import config
        from git_integration import commit_generator as cg

        monkeypatch.setattr(config, "LLM_PROVIDER", provider)
        reset_llm_client()
        if failure == "http500":
            side = dict(return_value=_resp(500, {"error": "x"}))
        elif failure == "timeout":
            side = dict(side_effect=requests.exceptions.Timeout())
        elif failure == "connection":
            side = dict(side_effect=requests.exceptions.ConnectionError())
        elif failure == "badjson":
            side = dict(return_value=_resp(200, raw_json_error=True))
        else:
            empty = {"message": {"content": "  "}} if provider == "ollama" else {"choices": [{"message": {"content": ""}}]}
            side = dict(return_value=_resp(200, empty))
        with patch("requests.post", **side):
            s = cg.CommitMessageGenerator(".", model="m")._generate_ai_commit_message("new file mode x.py")
        assert s.title.startswith(("Add", "Update"))


# ===========================================================================
# 模型列表 / 健康：model_switcher / bootstrap / CLI / Web
# ===========================================================================

class TestModelSwitcherProviderAware:
    def test_list_installed_models_openai_uses_available_models(self, openai_env):
        import model_switcher as ms

        with patch("requests.get", return_value=_resp(200, {"data": [{"id": "m1"}]})):
            assert ms.list_installed_models() == ["m1"]
            assert ms.models_notice() == ""
        with patch("requests.get", return_value=_resp(404, {})):
            assert ms.list_installed_models() == ["local-model"]
            assert llm_client.MODELS_UNAVAILABLE_NOTICE in ms.models_notice()

    def test_models_notice_ollama_and_errors(self, ollama_env):
        import model_switcher as ms

        with patch("requests.get", return_value=_resp(200, {"models": [{"name": "a"}]})):
            assert ms.models_notice() == ""
        with patch("llm_client.available_models", side_effect=RuntimeError("x")):
            assert ms.models_notice() == ""

    def test_unload_model_noop_in_openai(self, openai_env):
        import model_switcher as ms

        with patch("requests.post") as post:
            assert ms.unload_model("m") is False
        post.assert_not_called()

    def test_switch_model_openai_without_list_allows_any_name(self, openai_env, monkeypatch):
        import config
        import model_switcher as ms

        monkeypatch.setattr(config, "set_llm_model", lambda m: 4096)
        with patch("requests.get", return_value=_resp(404, {})), patch("requests.post") as post:
            r = ms.switch_model("any-model")
        assert r.ok and r.model == "any-model" and "未校验" in r.message
        post.assert_not_called()  # openai 模式不卸载旧模型

    def test_switch_model_openai_with_list_validates(self, openai_env, monkeypatch):
        import config
        import model_switcher as ms

        monkeypatch.setattr(config, "set_llm_model", lambda m: 4096)
        with patch("requests.get", return_value=_resp(200, {"data": [{"id": "m1"}]})):
            r = ms.switch_model("nope")
        assert not r.ok and "未安装" in r.message

    def test_current_model_info_openai(self, openai_env):
        import model_switcher as ms

        with patch("requests.get") as get:
            info = ms.current_model_info()
        get.assert_not_called()  # /api/ps 是 Ollama 专有
        assert info["provider"] == "openai" and info["base_url"] == "http://lmstudio:1234"
        assert info["loaded"] is False and info["loaded_models"] == []

    def test_current_model_info_ollama_has_provider(self, ollama_env):
        import model_switcher as ms

        with patch("requests.get", return_value=_resp(200, {"models": []})):
            info = ms.current_model_info()
        assert info["provider"] == "ollama"


class TestBootstrapProviderAware:
    def test_ollama_helpers_via_client(self, ollama_env):
        import bootstrap

        with patch("requests.get", return_value=_resp(200, {"models": [{"name": "a"}]})):
            assert bootstrap.ollama_running() is True
            assert bootstrap.list_installed_models() == ["a"]
        with patch("requests.get", side_effect=ConnectionError("down")):
            assert bootstrap.ollama_running() is False
            assert bootstrap.list_installed_models() == []
        assert bootstrap.llm_provider() == "ollama"

    def test_openai_backend_unhealthy(self, openai_env):
        import bootstrap

        notes = []
        with patch("requests.get", side_effect=ConnectionError("down")):
            ok = bootstrap.ensure_ollama_ready(interactive=False, notify=lambda t, m: notes.append((t, m)))
        assert ok is False and notes and "不可达" in notes[0][0] and "http://lmstudio:1234" in notes[0][1]

    def test_openai_backend_healthy_ollama_missing_only_hint(self, openai_env, monkeypatch):
        import bootstrap

        notes = []

        def fake_get(url, **kw):
            if "/v1/models" in url:
                return _resp(200, {"data": []})
            raise ConnectionError("no ollama")

        with patch("requests.get", side_effect=fake_get), patch("bootstrap.install_ollama") as inst, \
                patch("bootstrap.pull_models") as pull:
            ok = bootstrap.ensure_ollama_ready(interactive=True, notify=lambda t, m: notes.append((t, m)))
        assert ok is True
        inst.assert_not_called()
        pull.assert_not_called()
        assert any("嵌入" in t for t, _ in notes)

    def test_openai_backend_healthy_embed_missing(self, openai_env, monkeypatch):
        import bootstrap

        notes = []

        def fake_get(url, **kw):
            if "/v1/models" in url:
                return _resp(200, {"data": []})
            return _resp(200, {"models": [{"name": "qwen3.5:4b"}]})

        with patch("requests.get", side_effect=fake_get):
            ok = bootstrap.ensure_ollama_ready(interactive=False, notify=lambda t, m: notes.append((t, m)))
        assert ok is True and any("ollama pull" in m for _, m in notes)

    def test_openai_backend_probe_exception(self, openai_env):
        import bootstrap

        with patch("llm_client.get_llm_client", side_effect=RuntimeError("boom")):
            assert bootstrap.ensure_ollama_ready(interactive=False) is False


class TestCLIProviderAware:
    def test_config_rows_openai(self, openai_env):
        import cli_handlers as h

        rows = dict(h.config_rows())
        assert rows["LLM 后端"].startswith("openai") and rows["后端地址"] == "http://lmstudio:1234"
        assert rows["API Key"] == "已设置" and "Ollama 地址（嵌入模型）" in rows

    def test_config_rows_ollama(self, ollama_env):
        import cli_handlers as h

        rows = dict(h.config_rows())
        assert rows["LLM 后端"] == "ollama" and "API Key" not in rows

    def test_banner_text(self, openai_env, monkeypatch):
        import query_interface as qi

        assert qi.backend_banner_text() == "后端: openai @ http://lmstudio:1234"
        import config
        monkeypatch.setattr(config, "LLM_PROVIDER", "ollama")
        assert qi.backend_banner_text().startswith("Ollama: ")
        with patch("llm_client.describe_backend", side_effect=RuntimeError("x")):
            assert qi.backend_banner_text().startswith("Ollama: ")

    def test_handle_model_no_arg_openai(self, openai_env, monkeypatch):
        import query_interface as qi
        from query_interface import ParsedCommand

        out = []
        monkeypatch.setattr(qi, "console", MagicMock(print=lambda *a, **k: out.append(str(a[0]) if a else "")))
        with patch("requests.get", return_value=_resp(404, {})):
            assert qi.handle_model(None, ParsedCommand("model", "/model", "")) is True
        text = "\n".join(out)
        assert "后端: openai @ http://lmstudio:1234" in text and "由后端决定" in text

    def test_handle_model_list_openai_fallback_notice(self, openai_env, monkeypatch):
        import query_interface as qi
        from query_interface import ParsedCommand

        out = []
        monkeypatch.setattr(qi, "console", MagicMock(print=lambda *a, **k: out.append(str(a[0]) if a else "")))
        with patch("requests.get", return_value=_resp(404, {})):
            assert qi.handle_model(None, ParsedCommand("model", "/model list", "list")) is True
        text = "\n".join(out)
        assert llm_client.MODELS_UNAVAILABLE_NOTICE in text and "local-model" in text and "可用模型" in text

    def test_handle_model_list_ollama_down(self, ollama_env, monkeypatch):
        import query_interface as qi
        from query_interface import ParsedCommand

        out = []
        monkeypatch.setattr(qi, "console", MagicMock(print=lambda *a, **k: out.append(str(a[0]) if a else "")))
        with patch("requests.get", side_effect=ConnectionError("down")):
            assert qi.handle_model(None, ParsedCommand("model", "/model list", "list")) is True
        assert any("ollama serve" in line for line in out)


class TestWebProviderAware:
    def test_env_info_and_format_openai(self, openai_env):
        from web.app import format_env_info
        from web.services import WebService

        svc = WebService()
        with patch("requests.get", return_value=_resp(200, {"data": []})):
            info = svc.env_info()
        assert info["llm_provider"] == "openai" and info["llm_base_url"] == "http://lmstudio:1234"
        assert info["llm_api_key_set"] is True and info["backend_healthy"] is True
        md = format_env_info(info)
        assert "`openai`" in md and "✅ 可达" in md and "已设置" in md and "Ollama 地址（嵌入模型）" in md

    def test_env_info_and_format_ollama_unhealthy(self, ollama_env):
        from web.app import format_env_info
        from web.services import WebService

        with patch("requests.get", side_effect=ConnectionError("down")):
            info = WebService().env_info()
        assert info["backend_healthy"] is False
        md = format_env_info(info)
        assert "`ollama`" in md and "❌ 不可达" in md and "API Key" not in md

    def test_format_env_info_unknown_health(self):
        from web.app import format_env_info

        md = format_env_info({"llm_provider": "ollama", "backend_healthy": None, "ollama_url": "http://o"})
        assert "| 后端状态 | — |" in md

    def test_env_info_backend_exception(self, ollama_env):
        from web.services import WebService

        with patch("llm_client.describe_backend", side_effect=RuntimeError("x")):
            info = WebService().env_info()
        assert info["backend_healthy"] is None

    def test_format_model_status_openai(self):
        from web.app import format_model_status

        md = format_model_status({"model": "m", "provider": "openai", "base_url": "http://b", "num_ctx": 1,
                                  "models_notice": "后端未提供模型列表"})
        assert "`openai`" in md and "http://b" in md and "由后端决定" in md and "⚠️ 后端未提供模型列表" in md
        md2 = format_model_status({"model": "m", "provider": "openai", "base_url": "http://b"})
        assert "⚠️" not in md2

    def test_format_model_chip_openai(self):
        from web.app import format_model_chip

        html = format_model_chip({"model": "m", "provider": "openai", "base_url": "http://b", "loaded": False})
        assert "openai" in html and "http://b" in html and "未加载" not in html and "ctx" not in html
        assert "未加载" in format_model_chip({"model": "m", "provider": "ollama", "loaded": False})

    def test_service_models_notice_and_on_model_status(self, openai_env):
        from web.app import build_handlers
        from web.services import WebService

        svc = WebService()
        with patch("requests.get", return_value=_resp(404, {})):
            assert llm_client.MODELS_UNAVAILABLE_NOTICE in svc.models_notice()
            status = build_handlers(svc)["on_model_status"]()
        assert "⚠️" in status and "local-model" in status

    def test_service_models_notice_swallows(self):
        from web.services import WebService

        svc = WebService(model_switcher_factory=lambda: MagicMock(models_notice=MagicMock(side_effect=RuntimeError("x"))))
        assert svc.models_notice() == ""
        svc2 = WebService(model_switcher_factory=lambda: object())
        assert svc2.models_notice() == ""


class TestRAGEngineOpenAILike:
    def test_setup_llm_uses_openai_like(self, openai_env, monkeypatch):
        import sys
        import types

        import rag_engine as re_mod

        fake_mod = types.ModuleType("llama_index.llms.openai_like")
        captured = {}

        class FakeOpenAILike:
            def __init__(self, **kw):
                captured.update(kw)

        fake_mod.OpenAILike = FakeOpenAILike
        monkeypatch.setitem(sys.modules, "llama_index.llms.openai_like", fake_mod)
        with patch("rag_engine.Ollama") as ollama_cls, patch("rag_engine.OllamaEmbedding"), \
                patch("rag_engine.chromadb.PersistentClient") as chroma, patch("rag_engine.Settings") as settings:
            chroma.return_value.get_or_create_collection.return_value = MagicMock()
            eng = re_mod.RAGEngine(enable_auto_snapshot=False, enable_security=False)
            ollama_cls.assert_not_called()
            assert isinstance(settings.llm, FakeOpenAILike)
        assert captured["api_base"] == "http://lmstudio:1234/v1" and captured["api_key"] == "sk-test"
        assert captured["model"] == re_mod.LLM_MODEL and captured["is_chat_model"] is True
        assert captured["context_window"] == eng.llm_num_ctx
        # 思考关闭 → 随请求发送 reasoning_effort（与 OpenAICompatClient 同一开关）
        assert captured["additional_kwargs"] == {"reasoning_effort": "none"}
        with patch("rag_engine.OllamaEmbedding"), patch("rag_engine.chromadb.PersistentClient") as chroma, \
                patch("rag_engine.Settings"):
            chroma.return_value.get_or_create_collection.return_value = MagicMock()
            eng.set_think(True)
        assert captured["additional_kwargs"] == {}

    def test_setup_llm_openai_like_no_key_and_v1_suffix(self, openai_env, monkeypatch):
        import sys
        import types

        import config
        import rag_engine as re_mod

        monkeypatch.setattr(config, "LLM_API_KEY", "")
        monkeypatch.setattr(config, "LLM_BASE_URL", "http://lmstudio:1234/v1")
        reset_llm_client()
        fake_mod = types.ModuleType("llama_index.llms.openai_like")
        captured = {}
        fake_mod.OpenAILike = lambda **kw: captured.update(kw) or MagicMock()
        monkeypatch.setitem(sys.modules, "llama_index.llms.openai_like", fake_mod)
        with patch("rag_engine.OllamaEmbedding"), patch("rag_engine.chromadb.PersistentClient") as chroma, \
                patch("rag_engine.Settings"):
            chroma.return_value.get_or_create_collection.return_value = MagicMock()
            re_mod.RAGEngine(enable_auto_snapshot=False, enable_security=False)
        assert captured["api_base"] == "http://lmstudio:1234/v1" and captured["api_key"] == "not-needed"

    def test_setup_llm_ollama_default(self, ollama_env):
        import rag_engine as re_mod

        with patch("rag_engine.Ollama") as ollama_cls, patch("rag_engine.OllamaEmbedding"), \
                patch("rag_engine.chromadb.PersistentClient") as chroma, patch("rag_engine.Settings"):
            chroma.return_value.get_or_create_collection.return_value = MagicMock()
            re_mod.RAGEngine(enable_auto_snapshot=False, enable_security=False)
        ollama_cls.assert_called_once()

    def test_provider_helpers_swallow(self):
        import rag_engine as re_mod

        with patch("llm_client.provider_name", side_effect=RuntimeError("x")):
            assert re_mod.RAGEngine._llm_provider() == "ollama"
        with patch("llm_client.reasoning_effort_setting", side_effect=RuntimeError("x")):
            assert re_mod.RAGEngine._reasoning_effort() == "none"


class TestNoDirectEndpointsOutsideLLMClient:
    def test_grep_guard(self):
        """§2 P1-2 验收：``/api/chat`` 与 ``/api/generate`` 只出现在 llm_client.py。"""
        import os
        import re

        src = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
        pattern = re.compile(r'"/api/chat"|/api/generate')
        offenders = []
        for root, _dirs, files in os.walk(src):
            for f in files:
                if not f.endswith(".py"):
                    continue
                path = os.path.join(root, f)
                with open(path, encoding="utf-8") as fh:
                    for i, line in enumerate(fh, 1):
                        if pattern.search(line) and not path.endswith("llm_client.py"):
                            offenders.append(f"{path}:{i}: {line.strip()}")
        assert offenders == []
