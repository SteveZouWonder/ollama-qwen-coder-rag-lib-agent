"""CLI 命令处理器公共底座：``CLIContext``、确认 / 错误判定 / SQL 安全评估、流式答案面板 ``LiveAnswer``。"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable

logger = logging.getLogger(__name__)


# ==================== 上下文 ====================

@dataclass
class CLIContext:
    """承载交互循环所需的全部共享状态与协作对象。

    handler 仅通过本上下文读写状态，从而与 query_interface 的模块级全局解耦。
    """

    console: Any
    has_rich: bool
    rag_engine: Any = None
    react_engine: Any = None
    last_rag_sources: list = field(default_factory=list)
    last_web_sources: list = field(default_factory=list)

    # 协作回调（由 query_interface 注入，保持单一实现来源）
    record_command: Callable[..., None] = lambda *a, **k: None
    record_conversation: Callable[[str, str], None] = lambda *a, **k: None
    ask_progress_callback: Callable[[dict], None] = lambda *a, **k: None

    # 渲染/工具函数（由 query_interface 注入）
    print_help: Callable[[], None] = lambda: None
    print_tools: Callable[[], None] = lambda: None
    show_tutorial: Callable[[], None] = lambda: None
    print_banner: Callable[[], None] = lambda: None
    print_knowledge_stats: Callable[[], None] = lambda: None
    print_rag_sources: Callable[[list], None] = lambda s: None
    print_web_sources: Callable[[list], None] = lambda s: None
    load_documents: Callable[..., Any] = None
    registry: Any = None

    # 能力开关
    knowledge_management_available: bool = False

    # 多 Agent 编排器工厂（None 时用默认配置创建；测试可注入替身）
    orchestrator_factory: Callable[[], Any] = None


# ==================== 通用工具 ====================

def _is_error(result: str) -> bool:
    """工具返回文本是否表示错误/提示（约定以 [错误]/[提示] 前缀）。"""
    return result.startswith("[错误]") or result.startswith("[提示]")


def _confirm(console, prompt: str = "确认执行? (y/n): ", safety: dict | None = None) -> bool:
    """交互式 y/n 确认。

    - 若 Config.AUTO_CONFIRM 开启（自动化场景）**且风险等级为 low / medium**，直接返回 True；
      ``safety`` 为 None 表示调用方没有风险信息（沿用工具自身的 safe 标记），按放行处理；
    - high / critical 即使开启 AUTO_CONFIRM 也仍需人工确认（F10 P0-1-c），并提示原因；
    - 读取输入失败（EOF/Ctrl-C）按取消处理，返回 False。
    """
    auto_confirm = False
    try:
        from config import Config
        from agent_tools import auto_confirm_allows

        auto_confirm = bool(getattr(Config, "AUTO_CONFIRM", False))
        if auto_confirm and auto_confirm_allows(safety):
            return True
    except Exception:  # noqa: BLE001 - 配置不可用时退化为交互确认
        pass
    if auto_confirm:
        console.print("[提示] 高风险命令需人工确认（自动确认只放行 low / medium）", style="yellow")
    try:
        answer = console.input(prompt).strip().lower()
    except (EOFError, KeyboardInterrupt):
        return False
    return answer in ("y", "yes", "是", "确认")


def _sql_safety(sql: str) -> dict | None:
    """把一条 SQL 交给共享层的命令安全分级（当作 ``sqlite3 -c '<sql>'`` 判定）。

    用于 ``/db-execute``：``DROP`` / ``TRUNCATE`` → high（AUTO_CONFIRM 不放行），
    ``INSERT`` / ``UPDATE`` / ``DELETE`` → medium。共享层不可用时返回 None（退化为交互确认）。
    """
    try:
        from agent_tools import CommandSafetyChecker

        return CommandSafetyChecker.analyze(f"sqlite3 -c {sql!r}")
    except Exception:  # noqa: BLE001
        return None


# ==================== 流式答案渲染（F10 P1-1） ====================

class LiveAnswer:
    """终端流式答案渲染：``rich.live.Live(Markdown(buffer))`` 随 token 增量刷新。

    供 ``/ask`` / ``/agent`` / 自然语言输入 / ``/multi`` 整合阶段共用。作为 ``on_token``
    回调传给编排层；首个 token 到达时才启动 Live（工具步骤期间不会出现空面板），
    ``finish()`` 停止并**清除**实时区域（``transient=True``），随后由调用方按既有格式
    打印完整答案（含来源 / 提示 / 引用校验），保证最终输出与非流式时完全一致。

    非 Rich 终端或 ``console`` 不可用时全部为空操作。

    ``LiveAnswer.streaming()`` 为进程内"是否有实时面板在刷新"的标志：ReAct 的推理心跳
    （``\\r`` 单行刷新）在面板刷新期间应静默，否则会在面板上方反复刷出"模型推理中…"。
    """

    _current: "LiveAnswer | None" = None

    @classmethod
    def streaming(cls) -> bool:
        return cls._current is not None and cls._current._live is not None

    def __init__(self, console, has_rich: bool = True, title: str | None = None,
                 border_style: str = "green", refresh_per_second: int = 8):
        self.console = console
        self.has_rich = bool(has_rich)
        self.title = title
        self.border_style = border_style
        self.refresh_per_second = refresh_per_second
        self.buffer = ""
        self.tokens = 0
        self._live = None

    def _renderable(self):
        from rich.markdown import Markdown
        from rich.panel import Panel

        return Panel(Markdown(self.buffer), border_style=self.border_style, title=self.title)

    def on_token(self, delta: str) -> None:
        """追加一段增量并刷新实时面板（首个 token 时启动 Live）。"""
        if not delta or not self.has_rich:
            return
        self.buffer += delta
        self.tokens += 1
        try:
            if self._live is None:
                from rich.live import Live

                self._live = Live(
                    self._renderable(), console=self.console,
                    refresh_per_second=self.refresh_per_second, transient=True,
                )
                self._live.start()
                LiveAnswer._current = self
            else:
                self._live.update(self._renderable())
        except Exception as exc:  # noqa: BLE001 - 渲染问题不影响问答
            logger.debug("LiveAnswer render failed: %s", exc)
            self._stop()

    def _stop(self) -> None:
        live, self._live = self._live, None
        if LiveAnswer._current is self:
            LiveAnswer._current = None
        if live is not None:
            try:
                live.stop()
            except Exception:  # noqa: BLE001
                pass

    def finish(self) -> bool:
        """停止并清除实时区域；返回是否曾输出过 token。"""
        self._stop()
        return self.tokens > 0

    @property
    def active(self) -> bool:
        return self._live is not None
