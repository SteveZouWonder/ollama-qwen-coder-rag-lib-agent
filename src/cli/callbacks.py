"""ReAct / RAG 进度与确认回调（F10 P3-2-b 由 ``query_interface`` 外迁）。

``on_step_callback`` 读写 ``state._progress_state``（``tests/conftest.py`` 每个用例后重置）。
"""
from cli import state

try:
    from rich.panel import Panel
    from rich import box
except ImportError:  # pragma: no cover - rich 缺失时由 state.HAS_RICH 走纯文本分支
    pass


# ReAct 步骤阶段 → CLI 标记 / 颜色（含 P1-8 鲁棒性事件：格式重试、重复、折叠、强制总结、错误）
STEP_PHASE_EMOJI = {
    "thinking": "[*]",
    "action": "[>]",
    "executing": "[!]",
    "observed": "[=]",
    "blocked": "[X]",
    "rejected": "[-]",
    "final": "[OK]",
    "format_retry": "[~]",
    "repeat": "[R]",
    "budget_fold": "[F]",
    "forced_summary": "[!!]",
    "error": "[E]",
}
STEP_PHASE_COLOR = {
    "thinking": "cyan",
    "executing": "yellow",
    "blocked": "red",
    "rejected": "red",
    "final": "green",
    "format_retry": "yellow",
    "repeat": "yellow",
    "budget_fold": "magenta",
    "forced_summary": "red",
    "error": "red",
}

def _live_streaming() -> bool:
    """当前是否有流式答案面板在刷新（见 ``cli.handlers.LiveAnswer``）。"""
    try:
        from cli.handlers import LiveAnswer
        return LiveAnswer.streaming()
    except Exception:  # noqa: BLE001
        return False


def on_step_callback(data: dict):
    from config import Config
    
    if not Config.SHOW_PROGRESS:
        return
    
    step = data.get("step", "?")
    total = data.get("total", "?")
    phase = data.get("phase", "?")
    msg = data.get("message", "")

    # F10 P1-1：Final Answer 正在逐 token 刷新实时面板时，推理心跳（\r 单行刷新）静默，
    # 否则会在面板上方反复刷出"模型推理中…"
    if data.get("transient") and _live_streaming():
        return

    phase_emoji = STEP_PHASE_EMOJI.get(phase, "[?]")

    if state.HAS_RICH and Config.PROGRESS_BAR_STYLE == "rich":
        from rich.console import Console as RichConsole
        
        color = STEP_PHASE_COLOR.get(phase, "white")
        
        # 计算进度百分比
        if step != "?" and total != "?":
            try:
                progress_percent = (int(step) / int(total)) * 100
                progress_bar = "█" * int(progress_percent / 5) + "░" * (20 - int(progress_percent / 5))
            except:
                progress_percent = 0
                progress_bar = "░" * 20
        else:
            progress_percent = 0
            progress_bar = "░" * 20
        
        # 根据阶段选择显示策略
        if phase == "thinking":
            # 推理期间：单行刷新，添加动态点
            state._progress_state["current_thinking_dots"] = (state._progress_state["current_thinking_dots"] + 1) % 4
            dots = "." * state._progress_state["current_thinking_dots"]
            content = f"[{color}]{phase_emoji} [{step}/{total}] 模型推理中{dots}[/{color}] [dim][{progress_bar}] {progress_percent:.0f}%[/dim]"
            state.console.print(content, end="\r")
            state._progress_state["last_line_length"] = len(content)
            
        elif phase in state._progress_state["important_phases"]:
            # 重要步骤：换行输出，保留历史记录
            # 先清理上一行的推理状态
            if state._progress_state["last_line_length"] > 0:
                state.console.print(" " * state._progress_state["last_line_length"], end="\r")
                state._progress_state["last_line_length"] = 0
            
            state.console.print(
                f"[{color}]{phase_emoji} [{step}/{total}] {msg}[/{color}] "
                f"[dim][{progress_bar}] {progress_percent:.0f}%[/dim]"
            )
            
        else:
            # 其他阶段：也换行输出
            if state._progress_state["last_line_length"] > 0:
                state.console.print(" " * state._progress_state["last_line_length"], end="\r")
                state._progress_state["last_line_length"] = 0
                
            state.console.print(
                f"[{color}]{phase_emoji} [{step}/{total}] {msg}[/{color}] "
                f"[dim][{progress_bar}] {progress_percent:.0f}%[/dim]"
            )
            
    else:
        # 非rich模式：保持原有行为
        print(f"[{step}/{total}] {phase_emoji} {msg}")

def on_confirm_callback(data: dict) -> bool:
    msg = data.get("message", "确认执行?")
    safety = data.get("safety", {})

    if state.HAS_RICH:
        risk = safety.get("risk_level", "unknown")
        color = {"low": "green", "medium": "yellow", "high": "red", "critical": "red"}.get(risk, "white")
        state.console.print(Panel(
            f"**{msg}**\n"
            f"风险等级: [{color}]{risk}[/{color}]",
            border_style="yellow",
            title="安全确认",
            box=box.ROUNDED
        ))
    else:
        print("\n安全确认")
        print(msg)
        if safety:
            print("风险等级: " + safety.get('risk_level', 'unknown'))

    try:
        answer = state.console.input("确认执行? (y/n): ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print("\n已取消")
        return False
    return answer in ("y", "yes", "是", "确认")

def ask_progress_callback(data: dict):
    """RAG 查询进度回调函数"""
    from config import Config
    
    if not Config.SHOW_PROGRESS:
        return
    
    phase = data.get("phase", "")
    msg = data.get("message", "")
    
    if state.HAS_RICH:
        phase_colors = {
            "embedding": "cyan",
            "retrieving": "blue",
            "scoring": "yellow",
            "generating": "magenta"
        }.get(phase, "white")
        
        if phase == "scoring":
            current = data.get("current", 0)
            total = data.get("total", 1)
            state.console.print(f"[dim]🔄 {msg} [progress]{current}/{total}[/progress][/dim]")
        else:
            state.console.print(f"[{phase_colors}]🔄 {msg}[/{phase_colors}]")
    else:
        print(f"🔄 {msg}")
