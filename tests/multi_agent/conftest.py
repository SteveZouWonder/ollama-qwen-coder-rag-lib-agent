"""多 Agent 测试公共夹具。

- ``block_ollama``（autouse）：拦截所有 ``requests.post``，避免测试真正调用本机
  Ollama（专业 Agent 现在委托真实 ReActEngine，未 Mock 时会发起模型请求）。
  被拦截时抛 ConnectionError → 分解/整合回退规则路径，Agent 返回 ``[错误]``。
- ``fake_engine_factory``：返回可注入 ``config["engine_factory"]`` 的假引擎工厂，
  记录构造参数并按脚本返回 Final Answer。
"""
from __future__ import annotations

from typing import Any, Dict, List

import pytest
import requests


class _Blocked(requests.exceptions.ConnectionError):
    pass


def _blocked_post(*args, **kwargs):  # noqa: D401
    raise _Blocked("network disabled in tests")


@pytest.fixture(autouse=True)
def block_ollama(monkeypatch):
    monkeypatch.setattr(requests, "post", _blocked_post)
    monkeypatch.setattr("react_engine.requests.post", _blocked_post, raising=False)
    yield


class FakeEngine:
    """替代 ReActEngine 的假引擎：记录 kwargs，chat 返回脚本化答案。"""

    instances: List["FakeEngine"] = []

    def __init__(self, answer: str = "Final Answer: 完成", step_log=None, **kwargs):
        self.kwargs = kwargs
        self.answer = answer
        self.step_log = step_log if step_log is not None else [
            {"step": 1, "phase": "action", "tool": "read_file", "input": {"path": "a.py"},
             "observation": "x", "confirmed": True},
            {"step": 2, "phase": "final", "answer": "完成"},
        ]
        self.stopped = False
        self.prompts: List[str] = []
        FakeEngine.instances.append(self)

    def chat(self, prompt: str) -> str:
        self.prompts.append(prompt)
        if self.kwargs.get("on_step"):
            self.kwargs["on_step"]({"step": 1, "phase": "thinking", "message": "Step 1"})
            self.kwargs["on_step"]({"step": 1, "phase": "observed", "message": "Step 1: read_file 执行完成"})
        return self.answer

    def stop(self):
        self.stopped = True


@pytest.fixture
def fake_engine_factory():
    """返回 ``make(answer=..., step_log=...) -> factory``；factory 可放入 config。"""
    FakeEngine.instances.clear()

    def make(answer: str = "Final Answer: 完成", step_log=None):
        def factory(**kwargs):
            return FakeEngine(answer=answer, step_log=step_log, **kwargs)
        factory.cls = FakeEngine
        return factory

    yield make
    FakeEngine.instances.clear()


@pytest.fixture
def scripted_complete():
    """按 prompt 关键词返回脚本化 LLM 输出的 complete 函数，记录调用。"""
    calls: List[str] = []

    def make(decompose: Any = None, integrate: Any = "综合回答", review: Any = None):
        def complete(prompt: str) -> str:
            calls.append(prompt)
            if "拆成可独立执行的子任务" in prompt:
                if isinstance(decompose, Exception):
                    raise decompose
                return decompose if decompose is not None else '{"subtasks":[]}'
            if "多个候选答案" in prompt:
                if isinstance(review, Exception):
                    raise review
                return review if review is not None else "{}"
            if isinstance(integrate, Exception):
                raise integrate
            return integrate
        complete.calls = calls
        return complete

    return make
