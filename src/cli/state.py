"""CLI 进程内共享状态（F10 P3-2-a 由 ``query_interface`` 收口）。

集中放置原本散落在 ``query_interface`` 模块顶层的可变全局：

- 终端能力探测：``HAS_RICH`` / ``HAS_READLINE`` / ``HAS_PROMPT_TOOLKIT``
- Rich 控制台：``get_console()`` / ``console``
- 运行时引擎与来源：``rag_engine`` / ``react_engine`` / ``last_rag_sources`` /
  ``last_web_sources`` / ``command_recommender``（由 ``query_interface.main`` 装配）
- ReAct 进度条状态：``_progress_state``

约定（见 CODE_STANDARDS §6）：其他模块一律 ``from cli import state`` 后在**函数体内**
以 ``state.console`` / ``state.rag_engine`` 形式运行时取值，不要 ``from cli.state import console``
——后者会在导入时固化对象，令测试的 ``patch("cli.state.console")`` 失效。
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - 仅供类型标注，避免在导入期拉起重依赖
    from rag_engine import RAGEngine
    from react_engine import ReActEngine
    from command_recommender import CommandRecommender

# ==================== 终端能力探测 ====================

try:
    import readline  # noqa: F401 - 仅探测可用性，实际使用在 query_interface.setup_readline
    HAS_READLINE = True
except ImportError:
    HAS_READLINE = False

try:
    from rich.console import Console
    HAS_RICH = True
except ImportError:
    HAS_RICH = False
    print("[提示] 安装 rich 可获得更好的输出体验: pip install rich")

try:
    import prompt_toolkit  # noqa: F401 - 仅探测可用性，实际使用在 query_interface.get_input
    HAS_PROMPT_TOOLKIT = True
except ImportError:
    HAS_PROMPT_TOOLKIT = False

# ==================== 运行时状态 ====================

rag_engine: "RAGEngine | None" = None
react_engine: "ReActEngine | None" = None
last_rag_sources: list = []
last_web_sources: list = []  # 上次回答引用的网络来源（[{title, url}]），供 /sources 展示
command_recommender: "CommandRecommender | None" = None

# 进度条状态管理（``callbacks.on_step_callback`` 读写；``tests/conftest.py`` 每个用例后重置）
_progress_state = {
    "last_line_length": 0,
    "important_phases": {"executing", "observed", "blocked", "rejected", "final"},
    "current_thinking_dots": 0
}

# ==================== Rich 控制台 ====================

def get_console():
    if HAS_RICH:
        return Console()
    else:
        class FakeConsole:
            def print(self, *args, **kwargs):
                print(*args)
            def input(self, prompt_text):
                return input(prompt_text)
            def status(self, msg):
                class Dummy:
                    def __enter__(self): return self
                    def __exit__(self, *a): pass
                return Dummy()
        return FakeConsole()

console = get_console()
