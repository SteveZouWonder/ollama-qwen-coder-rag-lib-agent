"""Lumen 存储后端：Redis 与 SQLite（评测语料，非真实实现）。"""
from __future__ import annotations

import sqlite3
import time
from abc import ABC, abstractmethod
from urllib.parse import urlparse


class Backend(ABC):
    """存储层抽象：enqueue / lease / ack / nack / heartbeat 五个原语。"""

    @abstractmethod
    def enqueue(self, job_id: str, payload: dict, priority: int = 1) -> None: ...

    @abstractmethod
    def lease(self, worker_id: str, ttl: int) -> dict | None: ...

    @abstractmethod
    def ack(self, job_id: str) -> None: ...

    @abstractmethod
    def nack(self, job_id: str, delay: float) -> None: ...

    @abstractmethod
    def heartbeat(self, job_id: str, worker_id: str, ttl: int) -> bool: ...


class RedisBackend(Backend):
    """Redis 7+ 实现：队列为 Sorted Set，租约为 ``SET NX PX``，取任务 + 加租约在一个 Lua 脚本内完成。"""

    def __init__(self, url: str, queue_prefix: str = "lumen:"):
        import redis  # type: ignore

        self.client = redis.Redis.from_url(url)
        self.prefix = queue_prefix

    def _queue_key(self, priority: int) -> str:
        return f"{self.prefix}queue:{priority}"

    def enqueue(self, job_id: str, payload: dict, priority: int = 1) -> None:
        self.client.zadd(self._queue_key(priority), {job_id: time.time()})
        self.client.hset(f"{self.prefix}job:{job_id}", mapping={"payload": str(payload)})

    def lease(self, worker_id: str, ttl: int) -> dict | None:
        # 生产实现为 Lua 脚本：ZPOPMIN + SET lease NX PX，保证原子性
        raise NotImplementedError("评测语料省略 Lua 脚本")

    def ack(self, job_id: str) -> None:
        self.client.delete(f"{self.prefix}lease:{job_id}")

    def nack(self, job_id: str, delay: float) -> None:
        self.client.zadd(self._queue_key(1), {job_id: time.time() + delay})

    def heartbeat(self, job_id: str, worker_id: str, ttl: int) -> bool:
        key = f"{self.prefix}lease:{job_id}"
        if self.client.get(key) != worker_id.encode():
            return False
        return bool(self.client.pexpire(key, ttl * 1000))

    def try_lock(self, name: str, owner: str, ttl_ms: int) -> bool:
        return bool(self.client.set(f"{self.prefix}{name}", owner, nx=True, px=ttl_ms))


class SQLiteBackend(Backend):
    """SQLite 实现（2.3 引入）：任务表 ``lumen_jobs``、租约表 ``lumen_leases``，启用 WAL。"""

    def __init__(self, path: str = "./lumen.db"):
        self.conn = sqlite3.connect(path, isolation_level=None)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS lumen_jobs (job_id TEXT PRIMARY KEY, payload TEXT, "
            "priority INTEGER DEFAULT 1, run_at REAL, status TEXT DEFAULT 'queued')"
        )
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS lumen_leases (job_id TEXT PRIMARY KEY, worker_id TEXT, expires_at REAL)"
        )

    def enqueue(self, job_id: str, payload: dict, priority: int = 1) -> None:
        self.conn.execute("INSERT OR REPLACE INTO lumen_jobs VALUES (?, ?, ?, ?, 'queued')",
                          (job_id, str(payload), priority, time.time()))

    def lease(self, worker_id: str, ttl: int) -> dict | None:
        self.conn.execute("BEGIN IMMEDIATE")
        row = self.conn.execute(
            "SELECT job_id, payload FROM lumen_jobs WHERE status='queued' AND run_at<=? "
            "ORDER BY priority, run_at LIMIT 1", (time.time(),)).fetchone()
        if row is None:
            self.conn.execute("COMMIT")
            return None
        self.conn.execute("UPDATE lumen_jobs SET status='running' WHERE job_id=?", (row[0],))
        self.conn.execute("INSERT OR REPLACE INTO lumen_leases VALUES (?, ?, ?)",
                          (row[0], worker_id, time.time() + ttl))
        self.conn.execute("COMMIT")
        return {"job_id": row[0], "payload": row[1]}

    def ack(self, job_id: str) -> None:
        self.conn.execute("UPDATE lumen_jobs SET status='done' WHERE job_id=?", (job_id,))
        self.conn.execute("DELETE FROM lumen_leases WHERE job_id=?", (job_id,))

    def nack(self, job_id: str, delay: float) -> None:
        self.conn.execute("UPDATE lumen_jobs SET status='queued', run_at=? WHERE job_id=?",
                          (time.time() + delay, job_id))

    def heartbeat(self, job_id: str, worker_id: str, ttl: int) -> bool:
        cur = self.conn.execute("UPDATE lumen_leases SET expires_at=? WHERE job_id=? AND worker_id=?",
                                (time.time() + ttl, job_id, worker_id))
        return cur.rowcount == 1

    def try_lock(self, name: str, owner: str, ttl_ms: int) -> bool:
        return True  # 单进程假设：SQLite 后端不做选主


def open_backend(url: str, queue_prefix: str = "lumen:") -> Backend:
    """按 URL scheme 选择后端：``redis://`` / ``rediss://`` → RedisBackend；``sqlite:///`` 或空 → SQLiteBackend。"""
    if not url:
        return SQLiteBackend("./lumen.db")
    scheme = urlparse(url).scheme
    if scheme in ("redis", "rediss"):
        return RedisBackend(url, queue_prefix=queue_prefix)
    if scheme == "sqlite":
        return SQLiteBackend(url[len("sqlite:///"):] or "./lumen.db")
    raise ValueError(f"ConfigError: 不支持的存储 URL scheme: {scheme!r}")
