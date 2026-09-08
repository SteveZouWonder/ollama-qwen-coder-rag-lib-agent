"""数据库「当前连接」（进程级，Web / CLI / Agent 三端共用）。

背景：``agent_tools.database_*`` 工具的 ``database`` 参数默认为 ``":memory:"``，
调用方（Web 工具页、CLI ``/db-*``、Agent）通常只传 ``sql``，导致每次都在全新的
内存库上执行，``database_connect`` 形同无效。本模块提供：

- ``set_current / get_current / clear_current``：记录用户最近一次成功连接的库；
- ``resolve``：调用方未显式传 ``database``（仍为默认值）且存在当前连接时，回退到它；
  显式传参始终优先；
- ``get_connector``：同一 ``(db_type, database)`` 复用同一个 ``DatabaseConnector``
  （``:memory:`` 尤其依赖此复用，否则表会随连接消失）；``clear_current`` 时全部关闭。

不做任何持久化（P3 连接记忆另行处理）。
"""
from __future__ import annotations

import threading
from typing import Any, Dict, Optional, Tuple

from .db_connector import DatabaseConnector, DatabaseType

DEFAULT_DB_TYPE = "sqlite"
DEFAULT_DATABASE = ":memory:"

_lock = threading.RLock()
_current: Optional[Dict[str, Any]] = None
_connectors: Dict[Tuple[str, str], DatabaseConnector] = {}


def _key(db_type: str, database: str) -> Tuple[str, str]:
    return ((db_type or DEFAULT_DB_TYPE).lower(), database or DEFAULT_DATABASE)


def set_current(db_type: str, database: str, **kwargs: Any) -> Dict[str, Any]:
    """记录当前连接；返回其副本（``db_type`` / ``database`` / 其余连接参数）。"""
    global _current
    info: Dict[str, Any] = {"db_type": (db_type or DEFAULT_DB_TYPE).lower(), "database": database or DEFAULT_DATABASE}
    info.update(kwargs)
    with _lock:
        _current = dict(info)
    return {k: v for k, v in info.items() if k != "password"}


def get_current() -> Optional[Dict[str, Any]]:
    """当前连接（副本，不含密码）；未连接返回 None。"""
    with _lock:
        if _current is None:
            return None
        return {k: v for k, v in _current.items() if k != "password"}


def clear_current() -> None:
    """清除当前连接并关闭所有缓存的连接器。"""
    global _current
    with _lock:
        _current = None
        connectors = list(_connectors.values())
        _connectors.clear()
    for c in connectors:
        try:
            c.close()
        except Exception:  # noqa: BLE001
            pass


def resolve(db_type: str, database: str, **kwargs: Any) -> Tuple[str, str, Dict[str, Any]]:
    """决定本次操作实际作用的库。

    调用方未显式传 ``database``（仍为默认 ``":memory:"``）且存在当前连接 → 使用当前连接；
    否则按传入参数（显式优先）。返回 ``(db_type, database, extra_kwargs)``。
    """
    db_type = (db_type or DEFAULT_DB_TYPE).lower()
    database = database or DEFAULT_DATABASE
    with _lock:
        cur = dict(_current) if _current else None
    if database == DEFAULT_DATABASE and cur:
        extra = {k: v for k, v in cur.items() if k not in ("db_type", "database")}
        return cur["db_type"], cur["database"], extra
    return db_type, database, dict(kwargs)


def get_connector(db_type: str, database: str, **kwargs: Any) -> DatabaseConnector:
    """按 ``(db_type, database)`` 复用连接器；首次访问时创建。"""
    key = _key(db_type, database)
    with _lock:
        connector = _connectors.get(key)
        if connector is None:
            connector = DatabaseConnector(DatabaseType(key[0]), database=key[1], **kwargs)
            _connectors[key] = connector
        return connector


def current_connector() -> Optional[DatabaseConnector]:
    """当前连接对应的连接器；未连接返回 None。"""
    with _lock:
        cur = dict(_current) if _current else None
    if not cur:
        return None
    extra = {k: v for k, v in cur.items() if k not in ("db_type", "database")}
    return get_connector(cur["db_type"], cur["database"], **extra)


def describe(info: Optional[Dict[str, Any]] = None) -> str:
    """一行可读描述，如 ``sqlite · /path/app.db``；未连接返回空串。"""
    info = info if info is not None else get_current()
    if not info:
        return ""
    return f"{info.get('db_type', DEFAULT_DB_TYPE)} · {info.get('database', DEFAULT_DATABASE)}"
