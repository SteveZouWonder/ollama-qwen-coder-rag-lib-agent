"""Lumen Worker：取任务、心跳续租、失败重试（评测语料，非真实实现）。"""
from __future__ import annotations

import importlib
import threading
import time
import uuid

from retry import DeadLetterQueue, NonRetryable, compute_backoff, should_retry


class Worker:
    """从存储后端租约取任务并执行；后台线程按 ``heartbeat_interval`` 续租。"""

    def __init__(self, backend, *, heartbeat_interval: int = 15, lease_ttl: int = 45,
                 retry_limit: int = 3, queue_prefix: str = "lumen:"):
        if lease_ttl <= heartbeat_interval:
            raise ValueError("lease_ttl 必须大于 heartbeat_interval，否则会触发 E204")
        self.backend = backend
        self.heartbeat_interval = heartbeat_interval
        self.lease_ttl = lease_ttl
        self.retry_limit = retry_limit
        self.worker_id = uuid.uuid4().hex
        self.dead_letters = DeadLetterQueue(backend, queue_prefix)
        self._attempts: dict[str, int] = {}
        self._stop = threading.Event()

    def run_forever(self, idle_sleep: float = 0.5) -> None:
        """主循环：租约取任务 → 执行 → ack / nack；无任务时休眠 ``idle_sleep`` 秒。"""
        while not self._stop.is_set():
            job = self.backend.lease(self.worker_id, self.lease_ttl)
            if job is None:
                time.sleep(idle_sleep)
                continue
            self._execute_job(job)

    def stop(self) -> None:
        self._stop.set()

    def heartbeat(self, job_id: str, stop: threading.Event) -> None:
        """后台续租线程：每 ``heartbeat_interval`` 秒刷新一次租约，失败即记录 E204 并退出。"""
        while not stop.wait(self.heartbeat_interval):
            if not self.backend.heartbeat(job_id, self.worker_id, self.lease_ttl):
                print(f"E204 lease expired before ack: {job_id}")
                return

    def _execute_job(self, job: dict) -> None:
        job_id = job["job_id"]
        stop = threading.Event()
        hb = threading.Thread(target=self.heartbeat, args=(job_id, stop), daemon=True)
        hb.start()
        try:
            self._call(job["payload"])
            self.backend.ack(job_id)
            self._attempts.pop(job_id, None)
        except Exception as exc:  # noqa: BLE001
            attempts = self._attempts.get(job_id, 0) + 1
            self._attempts[job_id] = attempts
            if should_retry(exc, attempts, self.retry_limit):
                self.backend.nack(job_id, compute_backoff(attempts))
            else:
                self.dead_letters.push(job_id, job["payload"], repr(exc), attempts)
                self.backend.ack(job_id)
        finally:
            stop.set()

    @staticmethod
    def _call(payload: dict) -> None:
        """按可导入路径加载任务函数并调用；``NonRetryable`` 原样抛出。"""
        module_name, _, func_name = payload["task"].rpartition(".")
        func = getattr(importlib.import_module(module_name), func_name)
        try:
            func(**payload.get("kwargs", {}))
        except NonRetryable:
            raise
