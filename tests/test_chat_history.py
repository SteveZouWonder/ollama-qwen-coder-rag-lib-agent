#!/usr/bin/env python3
"""
test_chat_history.py — 对话历史持久化单元测试（目标 100% 覆盖）
"""
import os
import json
import pytest
from chat_history import ChatHistory


class TestChatHistoryInit:
    """测试初始化"""

    def test_init_creates_empty(self, temp_dir):
        path = temp_dir / "history.json"
        ch = ChatHistory(str(path), max_messages=10)
        assert ch.messages == []
        assert ch.filepath == str(path)
        assert ch.max_messages == 10

    def test_init_loads_existing(self, temp_dir):
        path = temp_dir / "history.json"
        data = [{"role": "user", "content": "hello"}]
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f)
        ch = ChatHistory(str(path), max_messages=10)
        assert len(ch.messages) == 1
        assert ch.messages[0]["role"] == "user"

    def test_init_handles_corrupted_json(self, temp_dir):
        path = temp_dir / "history.json"
        with open(path, "w", encoding="utf-8") as f:
            f.write("not json")
        ch = ChatHistory(str(path), max_messages=10)
        assert ch.messages == []

    def test_init_handles_missing_file(self, temp_dir):
        path = temp_dir / "nonexistent.json"
        ch = ChatHistory(str(path), max_messages=10)
        assert ch.messages == []


class TestChatHistoryAdd:
    """测试添加消息"""

    def test_add_user_message(self, temp_dir):
        path = temp_dir / "history.json"
        ch = ChatHistory(str(path), max_messages=10)
        ch.add("user", "hello")
        assert len(ch.messages) == 1
        assert ch.messages[0]["role"] == "user"
        assert ch.messages[0]["content"] == "hello"

    def test_add_assistant_message(self, temp_dir):
        path = temp_dir / "history.json"
        ch = ChatHistory(str(path), max_messages=10)
        ch.add("assistant", "hi")
        assert len(ch.messages) == 1
        assert ch.messages[0]["role"] == "assistant"

    def test_add_system_message(self, temp_dir):
        path = temp_dir / "history.json"
        ch = ChatHistory(str(path), max_messages=10)
        ch.add("system", "prompt")
        assert len(ch.messages) == 1
        assert ch.messages[0]["role"] == "system"

    def test_add_truncates_non_system(self, temp_dir):
        path = temp_dir / "history.json"
        ch = ChatHistory(str(path), max_messages=3)
        ch.add("system", "sys")
        ch.add("user", "a")
        ch.add("user", "b")
        ch.add("user", "c")
        ch.add("user", "d")
        # system 保留，非 system 只保留最近 2 条
        assert len(ch.messages) == 3
        assert ch.messages[0]["role"] == "system"
        assert ch.messages[1]["content"] == "c"
        assert ch.messages[2]["content"] == "d"

    def test_add_truncates_when_no_system(self, temp_dir):
        path = temp_dir / "history.json"
        ch = ChatHistory(str(path), max_messages=2)
        ch.add("user", "a")
        ch.add("user", "b")
        ch.add("user", "c")
        assert len(ch.messages) == 2
        assert ch.messages[0]["content"] == "b"
        assert ch.messages[1]["content"] == "c"

    def test_add_persists_to_file(self, temp_dir):
        path = temp_dir / "history.json"
        ch = ChatHistory(str(path), max_messages=10)
        ch.add("user", "hello")
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert len(data) == 1
        assert data[0]["content"] == "hello"

    def test_add_handles_permission_error(self, temp_dir, monkeypatch):
        path = temp_dir / "readonly_dir" / "history.json"
        os.makedirs(path.parent, exist_ok=True)
        # 让目录不可写
        os.chmod(str(path.parent), 0o555)
        try:
            ch = ChatHistory(str(path), max_messages=10)
            ch.add("user", "hello")
            # 不应抛出异常，只在内存保存
            assert len(ch.messages) == 1
        finally:
            os.chmod(str(path.parent), 0o755)


class TestChatHistoryGetMessages:
    """测试获取消息"""

    def test_get_messages_filters_invalid(self, temp_dir):
        path = temp_dir / "history.json"
        ch = ChatHistory(str(path), max_messages=10)
        ch.messages = [
            {"role": "user", "content": "ok"},
            {"not_role": "x"},  # 无效
            "not_dict",  # 无效
            {"role": "assistant", "content": "ok2"},
        ]
        msgs = ch.get_messages()
        assert len(msgs) == 2
        assert msgs[0]["role"] == "user"
        assert msgs[1]["role"] == "assistant"

    def test_get_messages_empty(self, temp_dir):
        path = temp_dir / "history.json"
        ch = ChatHistory(str(path), max_messages=10)
        assert ch.get_messages() == []


class TestChatHistoryClear:
    """测试清空"""

    def test_clear_keeps_system(self, temp_dir):
        path = temp_dir / "history.json"
        ch = ChatHistory(str(path), max_messages=10)
        ch.add("system", "sys")
        ch.add("user", "hello")
        ch.add("assistant", "hi")
        ch.clear()
        assert len(ch.messages) == 1
        assert ch.messages[0]["role"] == "system"

    def test_clear_all_when_no_system(self, temp_dir):
        path = temp_dir / "history.json"
        ch = ChatHistory(str(path), max_messages=10)
        ch.add("user", "hello")
        ch.clear()
        assert ch.messages == []

    def test_clear_persists(self, temp_dir):
        path = temp_dir / "history.json"
        ch = ChatHistory(str(path), max_messages=10)
        ch.add("system", "sys")
        ch.add("user", "hello")
        ch.clear()
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert len(data) == 1
        assert data[0]["role"] == "system"
