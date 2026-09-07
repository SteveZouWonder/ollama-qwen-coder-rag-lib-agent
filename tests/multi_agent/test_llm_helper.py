"""collaboration.llm_helper 单测。"""
from unittest.mock import MagicMock, patch

import pytest

from collaboration import llm_helper as h


class TestParseJson:
    def test_plain(self):
        assert h.parse_json_object('{"a": 1}') == {"a": 1}

    def test_with_think_and_fence(self):
        text = '<think>嗯</think>\n```json\n{"subtasks": [{"type": "x"}]}\n```'
        assert h.parse_json_object(text) == {"subtasks": [{"type": "x"}]}

    def test_prefix_text_and_nested(self):
        text = '好的，结果：{"a": {"b": "}"}, "c": [1,2]} 完'
        assert h.parse_json_object(text) == {"a": {"b": "}"}, "c": [1, 2]}

    @pytest.mark.parametrize("text", ["", "没有 json", "{broken", "[1,2]", '"str"'])
    def test_invalid(self, text):
        assert h.parse_json_object(text) is None

    def test_extract_json_object_none(self):
        assert h.extract_json_object("") is None
        assert h.extract_json_object("{never closed") is None


class TestCompleteJson:
    def test_uses_injected_complete(self):
        assert h.complete_json("p", complete=lambda p: '{"ok": true}') == {"ok": True}

    def test_exception_returns_none(self):
        def boom(p):
            raise RuntimeError("x")
        assert h.complete_json("p", complete=boom) is None

    def test_default_complete_text(self):
        resp = MagicMock()
        resp.json.return_value = {"message": {"content": ' {"k": 1} '}}
        with patch("requests.post", return_value=resp) as post:
            assert h.complete_text("hi", num_predict=64, timeout=7) == '{"k": 1}'
            payload = post.call_args.kwargs["json"]
            assert payload["think"] is False
            assert payload["options"]["num_predict"] == 64
            assert post.call_args.kwargs["timeout"] == 7
        with patch("requests.post", return_value=resp):
            assert h.complete_json("hi") == {"k": 1}

    def test_default_complete_text_config_fallback(self, monkeypatch):
        import config as cfg
        monkeypatch.delattr(cfg, "LLM_NUM_CTX", raising=False)
        resp = MagicMock()
        resp.json.return_value = {"message": {"content": "x"}}
        with patch("requests.post", return_value=resp) as post:
            assert h.complete_text("hi") == "x"
            assert post.call_args.kwargs["json"]["options"]["num_ctx"] == 8192


class TestMisc:
    def test_strip_think(self):
        assert h.strip_think("<think>a</think> b") == "b"
        assert h.strip_think(None) == ""

    def test_truncate(self):
        assert h.truncate("abc", 5) == "abc"
        out = h.truncate("abcdefgh", 3)
        assert out.startswith("abc") and "已截断 5 字" in out
        assert h.truncate(None, 3) == ""
