"""Lumen 重试策略：指数退避与死信队列（评测语料，非真实实现）。"""
from __future__ import annotations

import json
import random
import time

DEAD_LETTER_KEY = "dead"


class NonRetryable(Exception):
    """任务声明"此错误不应重试"，Worker 直接送入死信队列。"""


def compute_backoff(attempt: int, base: float = 2.0, cap: float = 300.0, jitter: bool = True) -> float:
    """第 ``attempt`` 次重试前的等待秒数：``min(base * 2**(attempt-1), cap)``，可选 50%–100% 抖动。"""
    if attempt < 1:
        raise ValueError("attempt 从 1 开始计数")
    delay = min(base * (2 ** (attempt - 1)), cap)
    if jitter:
        delay *= random.uniform(0.5, 1.0)
    return delay


class DeadLetterQueue:
    """死信队列：保存耗尽重试次数或抛出 ``NonRetryable`` 的任务。"""

    def __init__(self, backend, queue_prefix: str = "lumen:"):
        self.backend = backend
        self.key = f"{queue_prefix}{DEAD_LETTER_KEY}"

    def push(self, job_id: str, payload: dict, error: str, attempts: int) -> None:
        """把任务连同最后一次异常与重试次数写入死信队列。"""
        record = {"job_id": job_id, "payload": payload, "error": error,
                  "attempts": attempts, "dead_at": time.time()}
        self.backend.list_push(self.key, json.dumps(record, ensure_ascii=False))

    def list(self, limit: int = 100) -> list[dict]:
        """列出最近 ``limit`` 条死信任务。"""
        return [json.loads(raw) for raw in self.backend.list_range(self.key, 0, limit - 1)]

    def replay(self, job_id: str) -> bool:
        """把一条死信任务重新入队（重试计数归零），返回是否找到。"""
        for raw in self.backend.list_range(self.key, 0, -1):
            record = json.loads(raw)
            if record["job_id"] == job_id:
                self.backend.list_remove(self.key, raw)
                self.backend.enqueue(job_id, record["payload"])
                return True
        return False

    def purge(self) -> int:
        """清空死信队列，返回删除条数。"""
        return self.backend.list_clear(self.key)


def should_retry(exc: BaseException, attempts: int, retry_limit: int = 3) -> bool:
    """是否继续重试：``NonRetryable`` 或已达 ``retry_limit`` 时返回 False。"""
    if isinstance(exc, NonRetryable):
        return False
    return attempts < retry_limit
