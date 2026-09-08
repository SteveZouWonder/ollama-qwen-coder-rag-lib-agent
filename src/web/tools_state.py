"""工具页轻量持久状态（F9 P3-1 / P3-2）：最近连接的数据库、命令历史。

落盘位置 ``<App 状态目录>/.cerebro/web_tools_state.json``（经 ``runtime_paths.app_state_dir`` 解析；
测试通过 ``runtime_paths.set_app_state_root`` 或直接传 ``path`` 隔离）。格式::

    {"recent_databases": ["/path/a.db", ...],   # ≤ RECENT_DB_MAX，最新在前
     "shell_history": ["ls -la", ...]}          # ≤ SHELL_HISTORY_MAX，最新在前、去重

读取容错：文件不存在 / JSON 损坏 / 结构不对 → 视为空状态，不抛异常；写失败只记日志。
"""
from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

STATE_FILENAME = "web_tools_state.json"
RECENT_DB_MAX = 8
SHELL_HISTORY_MAX = 50

_KEYS = ("recent_databases", "shell_history")


def default_state_path() -> Path:
    """默认状态文件路径（``.cerebro/web_tools_state.json``）。"""
    from runtime_paths import app_state_dir

    return app_state_dir(STATE_FILENAME)


def _empty() -> Dict[str, List[str]]:
    return {k: [] for k in _KEYS}


class ToolsState:
    """最近库 / 命令历史的读写器（每次操作读一次文件，避免多进程或手改文件后状态不一致）。"""

    def __init__(self, path: Optional[Any] = None, *,
                 recent_db_max: int = RECENT_DB_MAX, shell_history_max: int = SHELL_HISTORY_MAX):
        self._path = Path(path) if path else None
        self.recent_db_max = int(recent_db_max)
        self.shell_history_max = int(shell_history_max)
        self._lock = threading.RLock()

    @property
    def path(self) -> Path:
        if self._path is None:
            self._path = default_state_path()
        return self._path

    # ---------- 读写 ----------

    def load(self) -> Dict[str, List[str]]:
        """读取状态；任何异常都回退为空状态。"""
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return _empty()
        except Exception as exc:  # noqa: BLE001
            logger.warning("工具页状态文件损坏，按空状态处理: %s (%s)", self.path, exc)
            return _empty()
        if not isinstance(raw, dict):
            return _empty()
        state = _empty()
        for key in _KEYS:
            items = raw.get(key)
            if isinstance(items, list):
                state[key] = [str(x) for x in items if isinstance(x, (str, int, float)) and str(x).strip()]
        return state

    def save(self, state: Dict[str, Any]) -> bool:
        """写入状态（只保留已知键，按上限裁剪）。返回是否成功。"""
        data = {
            "recent_databases": list(state.get("recent_databases") or [])[: self.recent_db_max],
            "shell_history": list(state.get("shell_history") or [])[: self.shell_history_max],
        }
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            return True
        except Exception as exc:  # noqa: BLE001
            logger.warning("写入工具页状态失败 %s: %s", self.path, exc)
            return False

    @staticmethod
    def _push(items: List[str], value: str, limit: int) -> List[str]:
        """去重后插到最前，并裁剪到 ``limit``。"""
        value = (value or "").strip()
        if not value:
            return list(items)[:limit]
        rest = [x for x in items if x != value]
        return [value, *rest][:limit]

    # ---------- 最近数据库 ----------

    def recent_databases(self) -> List[str]:
        return self.load()["recent_databases"][: self.recent_db_max]

    def remember_database(self, database: str) -> List[str]:
        """记住一次成功连接（``:memory:`` 不记，它总在下拉里作为默认项）。"""
        database = (database or "").strip()
        if not database or database == ":memory:":
            return self.recent_databases()
        with self._lock:
            state = self.load()
            state["recent_databases"] = self._push(state["recent_databases"], database, self.recent_db_max)
            self.save(state)
            return list(state["recent_databases"])

    def forget_database(self, database: str) -> List[str]:
        with self._lock:
            state = self.load()
            state["recent_databases"] = [x for x in state["recent_databases"] if x != (database or "").strip()]
            self.save(state)
            return list(state["recent_databases"])

    # ---------- 命令历史 ----------

    def shell_history(self) -> List[str]:
        return self.load()["shell_history"][: self.shell_history_max]

    def remember_command(self, command: str) -> List[str]:
        """记住一条成功执行的命令（去重、最新在前）。"""
        command = (command or "").strip()
        if not command:
            return self.shell_history()
        with self._lock:
            state = self.load()
            state["shell_history"] = self._push(state["shell_history"], command, self.shell_history_max)
            self.save(state)
            return list(state["shell_history"])

    def clear_shell_history(self) -> None:
        with self._lock:
            state = self.load()
            state["shell_history"] = []
            self.save(state)
