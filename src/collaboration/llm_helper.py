"""
多 Agent 协作层的轻量 LLM 调用工具。

分解 / 整合 / 评审都是"一次性、短输出"的工具性调用：强制 ``think=False``、
限制 ``num_predict``、失败抛异常交由调用方回退（关键词表 / 拼接 / 最长输出）。
所有函数都可通过注入 ``complete`` 回调替换，便于单测 Mock。
"""
from __future__ import annotations

import json
import re
from typing import Any, Callable, Dict, Optional

CompleteFn = Callable[[str], str]

_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)
_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


def complete_text(prompt: str, num_predict: int = 512, timeout: Optional[int] = None,
                  temperature: float = 0.2) -> str:
    """用全局唯一模型做一次补全（``/api/chat``，``think=False``）。失败抛异常。"""
    import requests
    from config import Config

    try:
        import config as _cfg
        model = getattr(_cfg, "LLM_MODEL", Config.LLM_MODEL)
        num_ctx = int(getattr(_cfg, "LLM_NUM_CTX", 8192))
    except Exception:  # noqa: BLE001
        model, num_ctx = Config.LLM_MODEL, 8192

    resp = requests.post(
        Config.OLLAMA_HOST + "/api/chat",
        json={
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "think": False,
            "options": {
                "temperature": temperature,
                "num_ctx": num_ctx,
                "num_predict": int(num_predict),
            },
        },
        timeout=timeout or Config.TIMEOUT,
    )
    resp.raise_for_status()
    return str(resp.json().get("message", {}).get("content", "")).strip()


def strip_think(text: str) -> str:
    """去掉模型可能输出的 ``<think>…</think>`` 段。"""
    return _THINK_RE.sub("", text or "").strip()


def extract_json_object(text: str) -> Optional[str]:
    """从任意文本中提取第一个完整的 JSON 对象字符串（花括号配对，跳过字符串内花括号）。"""
    if not text:
        return None
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
    return None


def parse_json_object(text: str) -> Optional[Dict[str, Any]]:
    """把 LLM 输出解析为 dict：去思维链 → 去代码围栏 → 花括号配对提取 → json.loads。

    解析失败或结果不是对象时返回 None（调用方据此回退）。
    """
    cleaned = strip_think(text)
    fence = _FENCE_RE.search(cleaned)
    if fence:
        cleaned = fence.group(1)
    raw = extract_json_object(cleaned)
    if not raw:
        return None
    try:
        obj = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return None
    return obj if isinstance(obj, dict) else None


def complete_json(prompt: str, complete: Optional[CompleteFn] = None,
                  num_predict: int = 512, timeout: Optional[int] = None) -> Optional[Dict[str, Any]]:
    """一次 LLM 调用并解析为 JSON 对象；任何失败（网络/解析）都返回 None。"""
    fn = complete or (lambda p: complete_text(p, num_predict=num_predict, timeout=timeout))
    try:
        text = fn(prompt)
    except Exception:  # noqa: BLE001 - 调用失败由调用方回退
        return None
    return parse_json_object(text)


def truncate(text: Any, limit: int) -> str:
    """截断到 ``limit`` 字符并注明省略长度。"""
    text = "" if text is None else str(text)
    if len(text) <= limit:
        return text
    return text[:limit] + f"…（已截断 {len(text) - limit} 字）"
