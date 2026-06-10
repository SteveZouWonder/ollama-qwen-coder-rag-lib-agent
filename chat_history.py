#!/usr/bin/env python3
"""对话历史持久化"""
import json
import os
from typing import List, Dict

class ChatHistory:
    def __init__(self, filepath: str, max_messages: int = 50):
        self.filepath = filepath
        self.max_messages = max_messages
        self.messages: List[Dict] = []
        self.load()

    def load(self):
        if os.path.exists(self.filepath):
            try:
                with open(self.filepath, "r", encoding="utf-8") as f:
                    self.messages = json.load(f)
            except (json.JSONDecodeError, IOError):
                self.messages = []

    def save(self):
        try:
            os.makedirs(os.path.dirname(self.filepath), exist_ok=True)
            with open(self.filepath, "w", encoding="utf-8") as f:
                json.dump(self.messages, f, ensure_ascii=False, indent=2)
        except (PermissionError, OSError) as e:
            # 如果无法写入文件，只在内存中保存（不报错）
            pass

    def add(self, role: str, content: str):
        self.messages.append({"role": role, "content": content})
        # 保留 system + 最近 N 条
        system_msgs = [m for m in self.messages if m.get("role") == "system"]
        other_msgs = [m for m in self.messages if m.get("role") != "system"]
        keep_count = self.max_messages - len(system_msgs)
        if keep_count > 0:
            other_msgs = other_msgs[-keep_count:]
        else:
            other_msgs = other_msgs[-self.max_messages:]
        self.messages = system_msgs + other_msgs
        self.save()

    def get_messages(self) -> List[Dict]:
        return [m for m in self.messages if isinstance(m, dict) and "role" in m and "content" in m]

    def clear(self):
        system_msgs = [m for m in self.messages if m.get("role") == "system"]
        self.messages = system_msgs
        self.save()
