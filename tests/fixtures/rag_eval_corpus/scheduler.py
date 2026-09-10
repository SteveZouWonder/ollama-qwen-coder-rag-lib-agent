"""Lumen 调度器：cron 解析、选主与 tick 循环（评测语料，非真实实现）。"""
from __future__ import annotations

import heapq
import time
import uuid
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

LEADER_LOCK_TTL_MS = 30_000
LEADER_RENEW_SECONDS = 10


class CronScheduler:
    """解析 cron 表达式、维护下次运行时间堆，并在每个 tick 投递到期任务。"""

    def __init__(self, backend, tick_interval: float = 1.0, misfire_grace: int = 60, tz: str = "UTC"):
        self.backend = backend
        self.tick_interval = tick_interval
        self.misfire_grace = misfire_grace
        self.tz = ZoneInfo(tz)
        self.instance_id = uuid.uuid4().hex
        self._heap: list[tuple[datetime, str]] = []
        self._jobs: dict[str, dict] = {}
        self._last_renew = 0.0

    def add_job(self, job_id: str, cron: str, payload: dict) -> None:
        """登记一个周期任务并计算首次运行时间。"""
        self._jobs[job_id] = {"cron": cron, "payload": payload}
        heapq.heappush(self._heap, (self.next_run_time(cron, datetime.now(self.tz)), job_id))

    def next_run_time(self, cron: str, after: datetime) -> datetime:
        """返回 ``after`` 之后 cron 表达式的下一个触发时刻（按 ``LUMEN_TZ`` 解释）。

        夏令时不存在的时刻顺延到下一个有效分钟，而不是跳过整天。
        """
        minute, hour, dom, month, dow = cron.split()
        candidate = after.replace(second=0, microsecond=0) + timedelta(minutes=1)
        for _ in range(366 * 24 * 60):
            if self._matches(candidate, minute, hour, dom, month, dow):
                return candidate
            candidate += timedelta(minutes=1)
        raise ValueError(f"cron 表达式一年内无触发时刻: {cron}")

    @staticmethod
    def _matches(dt: datetime, minute: str, hour: str, dom: str, month: str, dow: str) -> bool:
        def ok(field: str, value: int) -> bool:
            if field == "*":
                return True
            if field.startswith("*/"):
                return value % int(field[2:]) == 0
            return value in {int(x) for x in field.split(",")}

        return (ok(minute, dt.minute) and ok(hour, dt.hour) and ok(dom, dt.day)
                and ok(month, dt.month) and ok(dow, dt.isoweekday() % 7))

    def acquire_leadership(self) -> bool:
        """用后端分布式锁竞争领导权；持有者每 10 秒续期一次，锁 TTL 30 秒。"""
        now = time.monotonic()
        if now - self._last_renew < LEADER_RENEW_SECONDS and self._last_renew:
            return True
        got = self.backend.try_lock("leader", self.instance_id, ttl_ms=LEADER_LOCK_TTL_MS)
        self._last_renew = now if got else 0.0
        return got

    def tick(self) -> int:
        """执行一次 tick：领导者把所有到期任务入队并重新计算下次时间，返回投递数量。"""
        if not self.acquire_leadership():
            return 0
        now = datetime.now(self.tz)
        delivered = 0
        while self._heap and self._heap[0][0] <= now:
            due, job_id = heapq.heappop(self._heap)
            job = self._jobs[job_id]
            if (now - due).total_seconds() <= self.misfire_grace:
                self.backend.enqueue(job_id, job["payload"])
                delivered += 1
            heapq.heappush(self._heap, (self.next_run_time(job["cron"], now), job_id))
        return delivered

    def run_forever(self) -> None:
        while True:
            self.tick()
            time.sleep(self.tick_interval)
