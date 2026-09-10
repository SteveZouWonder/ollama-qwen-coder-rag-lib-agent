#!/usr/bin/env python3
"""
融合 CLI 入口 - RAG 知识库 + Code Agent
统一交互界面，支持知识库查询和 ReAct Agent 任务
"""
import sys
import os
import argparse
import logging
import warnings
from pathlib import Path

logger = logging.getLogger(__name__)

# 在任何导入之前禁用各种警告
# 禁用ChromaDB遥测错误
os.environ['ANONYMIZED_TELEMETRY'] = 'False'
os.environ['CHROMA_TELEMETRY'] = 'False'
logging.getLogger("chromadb").setLevel(logging.ERROR)

# 禁用urllib3的OpenSSL警告（macOS LibreSSL版本问题）
warnings.filterwarnings("ignore", message="urllib3 v2 only supports OpenSSL 1.1.1+")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ==================== Python 解释器版本自保护 ====================
# 本项目要求 Python 3.13（最低 3.10，因依赖使用 ``X | Y`` 联合类型语法）。
# 若用户用不兼容的系统解释器（如 macOS 自带的 Python 3.9）启动本脚本，
# 直接导入 llama_index 等依赖会抛出晦涩的 ``TypeError: unsupported operand
# type(s) for |``。这里在加载任何第三方依赖之前进行版本检测，
# 若发现不兼容则自动使用项目虚拟环境的解释器重新执行本脚本。

# 兼容运行所需的最低 Python 版本 (major, minor)
MIN_PYTHON_VERSION = (3, 10)
# 防止重新执行陷入无限循环的环境变量哨兵
_REEXEC_GUARD_ENV = "QUERY_INTERFACE_REEXEC_GUARD"


def find_venv_python(start_path):
    """从脚本所在位置向上查找项目虚拟环境的 Python 解释器路径。

    Args:
        start_path: 起始路径（通常为本文件的绝对路径）。

    Returns:
        找到的可执行 Python 解释器路径字符串；未找到返回 None。
    """
    current = os.path.dirname(os.path.abspath(start_path))
    # 向上最多查找 5 层目录，寻找 venv / .venv
    for _ in range(5):
        for venv_dir in ("venv", ".venv"):
            candidate = os.path.join(current, venv_dir, "bin", "python")
            if os.path.exists(candidate) and os.access(candidate, os.X_OK):
                return candidate
        parent = os.path.dirname(current)
        if parent == current:
            break
        current = parent
    return None


def ensure_compatible_interpreter(
    version_info=None,
    env=None,
    script_path=None,
    min_version=MIN_PYTHON_VERSION,
):
    """检测当前解释器是否满足版本要求，必要时用 venv 解释器重新执行。

    该函数被设计为可测试：通过注入 ``version_info`` / ``env`` /
    ``script_path`` 即可在不真正重新执行进程的情况下验证决策逻辑。

    Args:
        version_info: 版本信息元组，默认取 ``sys.version_info``。
        env: 环境变量字典，默认取 ``os.environ``。
        script_path: 当前脚本路径，默认取本文件路径。
        min_version: 要求的最低版本 (major, minor)。

    Returns:
        - "ok": 当前解释器满足要求，可继续运行。
        - "reexec": 已（或将要）使用 venv 解释器重新执行。
        - "incompatible": 不兼容且未找到 venv，需要中止。

    Raises:
        SystemExit: 当不兼容且无法重新执行时（仅在直接运行场景下）。
    """
    version_info = version_info if version_info is not None else sys.version_info
    env = env if env is not None else os.environ
    script_path = script_path or os.path.abspath(__file__)

    # 当前解释器满足最低版本要求
    if tuple(version_info[:2]) >= tuple(min_version):
        return "ok"

    # 已经重新执行过一次，避免无限循环
    if env.get(_REEXEC_GUARD_ENV) == "1":
        return "incompatible"

    venv_python = find_venv_python(script_path)
    if not venv_python:
        return "incompatible"

    return "reexec"


def _enforce_compatible_interpreter():
    """在加载第三方依赖前执行版本自保护（实际副作用入口）。"""
    decision = ensure_compatible_interpreter()

    if decision == "ok":
        return

    current = "%d.%d.%d" % sys.version_info[:3]
    required = "%d.%d+" % MIN_PYTHON_VERSION

    if decision == "reexec":
        venv_python = find_venv_python(os.path.abspath(__file__))
        sys.stderr.write(
            "[提示] 当前 Python %s 不满足要求（需要 %s），"
            "正在使用项目虚拟环境重新启动...\n" % (current, required)
        )
        new_env = dict(os.environ)
        new_env[_REEXEC_GUARD_ENV] = "1"
        # 用 venv 解释器重新执行本脚本，保留原始命令行参数
        os.execve(venv_python, [venv_python, os.path.abspath(__file__)] + sys.argv[1:], new_env)

    # decision == "incompatible"
    sys.stderr.write(
        "\n错误: 当前 Python 版本为 %s，本项目要求 Python %s。\n"
        "未找到项目虚拟环境 (venv/.venv)，无法自动切换。\n\n"
        "请使用项目虚拟环境运行：\n"
        "  source venv/bin/activate && python src/query_interface.py\n"
        "或直接指定虚拟环境解释器：\n"
        "  venv/bin/python src/query_interface.py\n" % (current, required)
    )
    sys.exit(1)


# 仅在作为脚本直接运行时执行自保护（被 import 时不触发，便于测试）
if __name__ == "__main__":
    _enforce_compatible_interpreter()

# 终端能力探测（HAS_RICH / HAS_READLINE / HAS_PROMPT_TOOLKIT）、Rich 控制台与运行时状态
# 已收口到 cli.state（F10 P3-2-a）；本模块函数体内一律经 ``state.xxx`` 运行时取值。
from cli import state  # noqa: E402

if state.HAS_READLINE:
    import readline

if state.HAS_RICH:
    from rich.console import Console
    from rich.markdown import Markdown
    from rich.panel import Panel
    from rich.syntax import Syntax
    from rich import box
    from rich.table import Table
    from rich.prompt import Prompt
    from rich.markup import escape
else:
    def escape(text):  # type: ignore[misc]  # pragma: no cover - rich 缺失时的兜底
        return str(text)

if state.HAS_PROMPT_TOOLKIT:
    from prompt_toolkit import prompt as pt_prompt
    from prompt_toolkit.history import FileHistory
    from prompt_toolkit.auto_suggest import AutoSuggestFromHistory

from config import Config, DATA_DIR, INDEX_DIR, LLM_MODEL, OLLAMA_BASE_URL
from rag_engine import RAGEngine, build_knowledge_base
from react_engine import ReActEngine
from agent_tools import (registry, CommandSafetyChecker, set_rag_engine,
                         auto_confirm_allows, HIGH_RISK_CONFIRM_HINT)
from document_loader import load_documents
import rag_pipeline

# 导入知识库管理功能
try:
    from knowledge_to_skills import KnowledgeToSkillsEngine
    from knowledge_snapshot import KnowledgeSnapshotManager, RestoreHelper
    KNOWLEDGE_MANAGEMENT_AVAILABLE = True
except ImportError:
    KNOWLEDGE_MANAGEMENT_AVAILABLE = False

# 导入命令推荐系统
try:
    from command_recommender import CommandRecommender, RecommendationSource
    RECOMMENDER_AVAILABLE = True
except ImportError:
    RECOMMENDER_AVAILABLE = False

# ==================== 全局状态（只读别名） ====================
# 状态本体在 cli.state；这里的模块级名字仅为 ``from query_interface import HAS_RICH`` 等
# 旧导入路径保留的**导入时快照**，函数体内不要使用（要经 ``state.xxx`` 取当前值）。
HAS_RICH = state.HAS_RICH
HAS_READLINE = state.HAS_READLINE
HAS_PROMPT_TOOLKIT = state.HAS_PROMPT_TOOLKIT
rag_engine = state.rag_engine
react_engine = state.react_engine
last_rag_sources = state.last_rag_sources
last_web_sources = state.last_web_sources
command_recommender = state.command_recommender


# ==================== 日志配置 ====================

# 第三方库默认会以 INFO 级别向终端刷屏（DuckDuckGo 搜索、httpx 的
# "HTTP Request POST ..." 以及 ollama 等），这里统一压制为 WARNING。
_NOISY_LOGGERS = (
    "httpx",
    "httpcore",
    "urllib3",
    "duckduckgo_search",
    "ollama",
    "chromadb",
    "web_search",
    "llama_index",
    "openai",
)


def setup_logging(verbose: bool = False):
    """统一配置 CLI 日志输出。

    策略：
      - 终端（控制台）默认只显示 WARNING 及以上，保持交互界面简洁；
        传入 ``--verbose`` 时拉回 INFO 以便排查问题。
      - INFO 级别完整日志写入 ``logs/cli.log`` 文件，便于事后回溯。
      - 显式压制第三方库的 INFO 噪音。

    Args:
        verbose: 是否在终端输出 INFO 级别日志。
    """
    from logging.handlers import RotatingFileHandler

    root = logging.getLogger()
    # 根 logger 放到 INFO，由各 handler 决定实际输出级别
    root.setLevel(logging.INFO)

    # 移除可能由第三方库提前安装的 handler，避免重复输出
    for handler in list(root.handlers):
        root.removeHandler(handler)

    fmt = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    # 控制台 handler：默认 WARNING，verbose 时 INFO
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(logging.INFO if verbose else logging.WARNING)
    console_handler.setFormatter(fmt)
    root.addHandler(console_handler)

    # 文件 handler：始终记录 INFO，带轮转
    try:
        log_dir = INDEX_DIR.parent / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            str(log_dir / "cli.log"),
            maxBytes=5 * 1024 * 1024,
            backupCount=3,
            encoding="utf-8",
        )
        file_handler.setLevel(logging.INFO)
        file_handler.setFormatter(fmt)
        root.addHandler(file_handler)
    except Exception as e:  # pragma: no cover - 文件系统异常降级处理
        logger.warning(f"无法创建日志文件，仅使用终端日志: {e}")

    # 压制第三方库的 INFO 噪音（仍写入文件 handler 的 WARNING+）
    for name in _NOISY_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)

# ==================== Rich 控制台（只读别名，实现见 cli.state） ====================

get_console = state.get_console
console = state.console

# ==================== 教程 ====================

from cli.help_text import TUTORIAL_TEXT  # noqa: E402,F401 - 教程文案已移至 cli.help_text
from cli.help_text import print_help as _print_help  # noqa: E402


def show_tutorial():
    if state.HAS_RICH:
        state.console.print(Panel(TUTORIAL_TEXT, border_style="cyan", title="使用指引", box=box.ROUNDED))
    else:
        print("=" * 60)
        print(TUTORIAL_TEXT)
        print("=" * 60)

def check_first_run():
    if not os.path.exists(Config.FIRST_RUN_MARKER):
        show_tutorial()
        try:
            with open(Config.FIRST_RUN_MARKER, "w") as f:
                f.write("done")
        except:
            pass
        state.console.print("\n提示：之后可随时输入 /tutorial 重新查看本教程\n")

# ==================== 回调函数 ====================

# 进度条状态管理：本体在 cli.state._progress_state（此处为只读别名）
_progress_state = state._progress_state

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

# ==================== 界面渲染 ====================

CEREBRO_ASCII = r"""   ____                _
  / ___|___ _ __ ___ | |__  _ __ ___
 | |   / _ \ '__/ _ \| '_ \| '__/ _ \
 | |__|  __/ | |  __/| |_) | | | (_) |
  \____\___|_|  \___||_.__/|_|  \___/"""


def print_banner():
    if state.HAS_RICH:
        state.console.print(Panel(
            f"[bold cyan]{CEREBRO_ASCII}[/bold cyan]\n"
            "[white]🧠 你的第二大脑 + 代码助手[/white]   [dim]v4.1[/dim]\n"
            "[dim]RAG 知识库 | ReAct Agent | 本地 Ollama | 安全护栏[/dim]\n"
            f"[green]模型: {LLM_MODEL}[/green] | [green]{backend_banner_text()}[/green]",
            border_style="cyan", box=box.ROUNDED
        ))
    else:
        print("=" * 60)
        print(CEREBRO_ASCII)
        print("    Cerebro 🧠 你的第二大脑 + 代码助手  v4.1")
        print("=" * 60)
        print(f"模型: {LLM_MODEL} | {backend_banner_text()}")
        print("=" * 60)


def backend_banner_text() -> str:
    """横幅中的后端一段：ollama 模式保持 ``Ollama: <url>``，openai 模式显示 ``后端: openai @ <url>``。"""
    try:
        from llm_client import describe_backend
        info = describe_backend()
    except Exception:  # noqa: BLE001
        return f"Ollama: {OLLAMA_BASE_URL}"
    if info.get("provider") == "openai":
        return f"后端: openai @ {info.get('base_url', '')}"
    return f"Ollama: {info.get('base_url') or OLLAMA_BASE_URL}"

def print_help():
    """打印 ``/help``（文案与渲染见 ``cli.help_text.print_help``）。"""
    _print_help(state.console, state.HAS_RICH)

def print_tools():
    if state.HAS_RICH:
        table = Table(title="可用工具", box=box.ROUNDED)
        table.add_column("工具名", style="cyan", no_wrap=True)
        table.add_column("安全等级", style="bold")
        table.add_column("描述", style="dim")

        for name, info in registry.tools.items():
            safe = info.get("safe", True)
            if safe:
                level = "[green]安全[/green]"
            else:
                level = "[yellow]需确认[/yellow]"
            table.add_row(name, level, info["description"])
        state.console.print(table)
        state.console.print("\n安全规则：")
        state.console.print("  [green]安全[/green]   = 只读操作，自动执行")
        state.console.print("  [yellow]需确认[/yellow] = 会修改系统，执行前询问")
        state.console.print("  [red]危险[/red]     = rm -rf / 等命令会被自动拦截")
    else:
        print("=== 可用工具 ===")
        for name, info in registry.tools.items():
            safe = "安全" if info.get("safe") else "需确认"
            print(f"  {name} [{safe}] - {info['description']}")

def print_rag_sources(sources: list):
    if not sources:
        state.console.print("⚠️  没有来源信息", style="yellow")
        return
    if state.HAS_RICH:
        table = Table(title="📚 参考来源（编号与回答中的 [n] 对应）", show_lines=True)
        table.add_column("#", style="bold", justify="right", no_wrap=True)
        table.add_column("文件", style="cyan", no_wrap=True)
        table.add_column("相似度", style="green", justify="right")
        table.add_column("引用", justify="right", no_wrap=True)
        table.add_column("内容片段", style="white")

        for i, src in enumerate(sources, 1):
            ref = f"[{src.get('ref') or i}]"
            score = f"{src['score']:.3f}" if src.get('score') else "N/A"
            if src.get("retriever") == "bm25":
                score += " (关键词)"
            content = src['content'][:100] + "..." if len(src['content']) > 100 else src['content']
            note = (src.get("rerank_note") or "").strip()
            if note:
                content += f"\n[dim]相关性：{note}[/dim]"
            # 代码块：文件名下一行显示 符号 · 行号（可直接定位）
            file_cell = escape(str(src.get('file', '未知')))
            loc = _source_code_location(src)
            if loc:
                file_cell += f"\n[dim]{escape(loc)}[/dim]"
            # P0-3：被引用次数（未引用显示 —）
            cited = src.get("cited")
            cited_cell = str(cited) if isinstance(cited, int) and cited > 0 else "[dim]—[/dim]"
            table.add_row(ref, file_cell, score, cited_cell, content)
        state.console.print(table)
    else:
        print("=== 参考来源 ===")
        for i, src in enumerate(sources, 1):
            ref = f"[{src.get('ref') or i}]"
            score = f"({src['score']:.3f})" if src.get('score') else ""
            loc = _source_code_location(src)
            head = f"{ref} {src['file']}" + (f" · {loc}" if loc else "")
            print(f"  {head} {score}".rstrip())
            print(f"    {src['content'][:100]}...")


def _source_code_location(src: dict) -> str:
    """代码来源的 ``symbol · L起-止`` 文案；文本来源返回空串。"""
    parts = []
    if src.get("symbol"):
        parts.append(str(src["symbol"]))
    if src.get("start_line") is not None:
        parts.append(f"L{src['start_line']}-{src.get('end_line') or src['start_line']}")
    if src.get("part"):
        parts.append(f"({src['part']})")
    return " · ".join(parts)


def count_code_sources(sources: list) -> int:
    """来源中代码块（带 symbol）的数量，用于 /ask 摘要行。"""
    return sum(1 for s in sources or [] if isinstance(s, dict) and s.get("symbol"))

def print_knowledge_stats():
    if state.rag_engine is None:
        state.console.print("⚠️  知识库未初始化", style="yellow")
        return
    stats = state.rag_engine.get_stats()
    # F10 P2-1-b：hybrid_disabled_reason 单独作为黄色提示行输出，表格里不重复；值为 None 的键不显示
    hybrid_reason = stats.get("hybrid_disabled_reason")
    rows = [(k, v) for k, v in stats.items() if v is not None and k != "hybrid_disabled_reason"]
    if state.HAS_RICH:
        table = Table(title="📊 知识库统计", box=box.ROUNDED)
        table.add_column("项目", style="cyan")
        table.add_column("值", style="white")
        for k, v in rows:
            table.add_row(k, str(v))
        state.console.print(table)
    else:
        print("=== 知识库统计 ===")
        for k, v in rows:
            print(f"  {k}: {v}")
    if hybrid_reason:
        state.console.print(f"⚠️ {hybrid_reason}", style="yellow")

# ==================== readline 历史 ====================

def setup_readline():
    if state.HAS_READLINE:
        try:
            from runtime_paths import home_file
        except ImportError:
            from src.runtime_paths import home_file  # type: ignore
        histfile = str(home_file(".code_agent_cli_history"))
        try:
            readline.read_history_file(histfile)
        except (FileNotFoundError, PermissionError, OSError):
            pass
        readline.set_history_length(1000)
        import atexit
        def save_history():
            try:
                readline.write_history_file(histfile)
            except (PermissionError, OSError):
                pass
        atexit.register(save_history)

# ==================== 输入获取 ====================

def get_input(prompt_text: str) -> str:
    if state.HAS_PROMPT_TOOLKIT:
        history = FileHistory(str(INDEX_DIR / ".chat_history"))
        return pt_prompt(prompt_text, history=history, auto_suggest=AutoSuggestFromHistory()).strip()
    else:
        return state.console.input(prompt_text).strip()

# 命令路由纯函数已移至 cli.parser（F10 P2-2），此处重导出以保持 ``from query_interface import parse_command`` 可用
from cli.parser import ParsedCommand, classify_mode, parse_command  # noqa: E402,F401


# ==================== 命令推荐系统辅助函数 ====================

def show_command_recommendations():
    """显示命令推荐"""
    logger.debug(f"show_command_recommendations 调用: command_recommender={state.command_recommender}")
    
    if not state.command_recommender:
        logger.debug("command_recommender 为 None")
        return
    
    if not state.command_recommender.is_enabled():
        logger.debug("command_recommender 已禁用")
        return
    
    try:
        recommendations = state.command_recommender.get_recommendations()
        logger.debug(f"获得 {len(recommendations) if recommendations else 0} 个推荐")
        
        if recommendations:
            # 默认使用紧凑单行模式，减少视觉噪音
            formatted = state.command_recommender.format_recommendations(
                recommendations, use_rich=state.HAS_RICH, compact=True
            )
            if formatted:
                state.console.print(formatted)
    except Exception as e:
        logger.error(f"推荐系统错误: {e}")
        state.console.print(f"[dim]⚠️  推荐系统错误: {e}[/dim]", style="dim")

def record_command_execution(cmd_type: str, args: str = "", result: str = "", error: str = ""):
    """记录命令执行到推荐系统"""
    logger.debug(f"record_command_execution: cmd_type={cmd_type}, args={args!r}")
    
    if not state.command_recommender:
        logger.debug(f"command_recommender 为 None，无法记录命令: {cmd_type}")
        return
    
    try:
        # 截断过长的参数，避免污染历史/上下文（如网络搜索结果正文）
        safe_args = args if len(args) <= 200 else args[:200] + "…"
        # 记录命令
        state.command_recommender.record_command(f"/{cmd_type}", safe_args, result)
        logger.debug(f"命令已记录: /{cmd_type}")
        
        # 记录错误（如果有）
        if error:
            state.command_recommender.record_error(error)
            logger.debug(f"错误已记录: {error}")
        
        # 更新RAG状态（可能变化）
        if state.rag_engine:
            rag_available = state.rag_engine.retriever is not None
            rag_empty = rag_available and (state.rag_engine.get_stats().get("total_chunks", 0) == 0)
            state.command_recommender.update_rag_status(rag_available, rag_empty)
            logger.debug(f"RAG状态已更新: available={rag_available}, empty={rag_empty}")
        
    except Exception as e:
        logger.error(f"记录命令失败: {e}")


def record_conversation(user_content: str, assistant_content: str, **kwargs):
    """将一轮对话写入"当前会话"，委托共享层 rag_pipeline.record_conversation。

    可选 ``rewritten`` / ``trace`` / ``progress`` 透传给会话上下文层（自动压缩时
    的进度事件经 ``progress`` 渲染到终端）。
    """
    rag_pipeline.record_conversation(user_content, assistant_content, **kwargs)


def _conversation():
    """进程内共享的会话上下文（跟随"当前会话"）。"""
    from conversation_context import get_conversation_context
    return get_conversation_context()


def _print_health_hint(pre: dict, question: str = ""):
    """回答后按上下文健康度打印一行 dim 提示（每会话只提示一次）。"""
    try:
        from conversation_context import merge_health, format_suggest_hint
        conv = _conversation()
        health = merge_health(pre or {}, conv.health())
        hint = format_suggest_hint(health)
        if hint:
            state.console.print(f"[dim]{hint}，输入 /session-new（可加 --carry 携带摘要）[/dim]")
            conv.mark_suggested()
    except Exception as e:  # noqa: BLE001 - 提示失败不影响主流程
        logger.debug(f"health hint failed: {e}")


def _health_before(question: str) -> dict:
    """提问前的健康度快照（用于判断空闲/话题漂移）。"""
    try:
        return _conversation().health(question)
    except Exception:  # noqa: BLE001
        return {}


# ==================== 共享 RAG 编排层的 CLI 适配 ====================
# 以下高级 RAG 逻辑（网络搜索规划、多查询合并、页面增强、元查询直答、
# 双区综合、0 命中回退）已下沉到 ``rag_pipeline``，供 CLI 与 Web 复用。
# 这里保留同名薄封装以维持向后兼容（测试/其它模块可能仍引用），实际逻辑
# 全部转调 rag_pipeline。CLI 独有的 Rich 终端渲染由 _cli_ask_progress 承接。

_simple_web_search = rag_pipeline.simple_web_search
_llm_direct_answer = rag_pipeline.llm_direct_answer
plan_web_search = rag_pipeline.plan_web_search
_merge_search_results = rag_pipeline._merge_search_results
_extract_urls = rag_pipeline._extract_urls
_is_empty_rag_result = rag_pipeline.is_empty_rag_result
_is_meta_query = rag_pipeline.is_meta_query
_parse_web_sources = rag_pipeline.parse_web_sources
_synthesize_prompt = rag_pipeline.synthesize_prompt
_format_kb_context = rag_pipeline.format_kb_context


def run_web_search(queries: list) -> str:
    """兼容封装：执行网络搜索，进度经 CLI 渲染。"""
    return rag_pipeline.run_web_search(queries, progress=_cli_ask_progress)


def enrich_with_page_content(search_result: str) -> str:
    """兼容封装：页面正文增强，进度经 CLI 渲染。"""
    return rag_pipeline.enrich_with_page_content(search_result, progress=_cli_ask_progress)


def _cli_ask_progress(event: dict):
    """把 rag_pipeline 的结构化进度事件渲染到 Rich 终端（CLI 专属）。"""
    stage = event.get("stage", "")
    msg = event.get("message", "")

    if stage == "meta_overview":
        _render_meta_overview(event)
        return

    style_map = {
        "web_search_start": "cyan",
        "web_query": "dim",
        "web_query_empty": "dim",
        "web_search_done": "green",
        "web_search_empty": "yellow",
        "web_search_failed": "yellow",
        "enrich_start": "dim",
        "enrich_page_failed": "dim",
        "enrich_page_blocked": "cyan",   # F9 P1-3：丢弃疑似注入页面
        "premise_unverified": "yellow",  # F9 P2-2：前提实体未在资料中出现
        "self_check": "dim",             # F9 P2-1：LLM 自校验
        "enrich_done": "green",
        "kb_empty": "yellow",
        "kb_fallback_search": "cyan",
        "kb_uninitialized": "yellow",
        "context_rewrite": "cyan",
        "context_rewritten": "cyan",
    }
    style = style_map.get(stage, "dim")
    if stage == "thinking":
        # /think on：模型思维链（已截断 800 字），dim 样式、转义避免被当作 Rich 标记
        from rich.markup import escape as _escape
        state.console.print(f"[dim]{_escape(msg)}[/dim]")
    elif stage == "fallback":
        state.console.print(msg, style="yellow")  # 具体 /agent 提示在回答渲染后由 _run_ask 打印
    elif stage in ("kb_retrieving", "synthesizing", "model_thinking", "rerank",
                   "context_compress", "context_compressed"):
        # 这些"进行中"提示走安静的 dim 行，避免打断 status
        state.console.print(f"[dim]{msg}[/dim]")
    elif msg:
        state.console.print(msg, style=style)


def _render_meta_overview(event: dict):
    """CLI 渲染知识库概览（文件列表 + 统计）。"""
    files = event.get("files") or []
    stats = event.get("stats") or {}
    state.console.print("\n📚 知识库概览:", style="bold blue")
    if not files:
        state.console.print("📭 知识库中暂无已登记的文件。", style="yellow")
        if stats.get("total_documents"):
            state.console.print(
                f"[dim]（向量库中存在 {stats['total_documents']} 个文档片段，"
                f"但未登记文件元数据）[/dim]"
            )
    else:
        state.console.print(f"📁 共有 {len(files)} 个文件:", style="cyan")
        for fm in files:
            state.console.print(f"  📄 {fm.get('path')}  [dim]({fm.get('size', '?')})[/dim]")

    if stats:
        state.console.print(
            f"\n[dim]文档片段总数: {stats.get('total_documents', '?')} | "
            f"Embedding: {stats.get('embed_model', '?')}[/dim]"
        )


def _answer_meta_query() -> bool:
    """兼容封装：直接渲染知识库概览。"""
    overview = rag_pipeline.build_meta_overview(state.rag_engine)
    _render_meta_overview({"files": overview["files"], "stats": overview["stats"]})
    return True


def print_web_sources(sources: list):
    """渲染网络来源区块（与知识库来源明确区分）。"""
    if not sources:
        return
    if state.HAS_RICH:
        table = Table(title="🌐 网络来源（编号与回答中的 [Wn] 对应）", show_lines=False)
        table.add_column("#", style="dim", justify="right", no_wrap=True)
        table.add_column("标题", style="cyan")
        table.add_column("链接", style="blue")
        for i, src in enumerate(sources, 1):
            ref = f"[{src.get('ref') or f'W{i}'}]"
            table.add_row(ref, src.get("title", ""), src.get("url", ""))
        state.console.print(table)
    else:
        print("=== 🌐 网络来源 ===")
        for i, src in enumerate(sources, 1):
            ref = f"[{src.get('ref') or f'W{i}'}]"
            print(f"  {ref} {src.get('title', '')}")
            print(f"     {src.get('url', '')}")


def _synthesize_prompt(question: str, kb_context: str, web_context: str) -> str:
    """组装“知识库/网络分区标注”的结构化 prompt，要求 LLM 区分来源并综合总结。"""
    parts = [
        "你是一个严谨的问答助手。请根据下面两类来源回答问题，并遵守规则：",
        "1. 【知识库检索内容】来自用户的本地知识库，是权威且优先的依据；",
        "2. 【网络搜索补充】来自互联网，仅作补充参考，可能不准确；",
        "3. 回答中必须明确区分：哪些结论来自知识库、哪些来自网络；",
        "4. 若两类来源冲突，以知识库为准并指出差异；",
        "5. 若知识库内容不足以回答，明确说明，再用网络信息补充。",
        "",
        f"【问题】\n{question}",
        "",
    ]
    if kb_context:
        parts.append(f"【知识库检索内容】（本地文档，优先依据）\n{kb_context}")
    else:
        parts.append("【知识库检索内容】\n（无相关内容）")
    parts.append("")
    if web_context:
        parts.append(f"【网络搜索补充】（互联网，仅供参考）\n{web_context}")
    else:
        parts.append("【网络搜索补充】\n（无）")
    parts.append("")
    parts.append("请给出综合回答，并在末尾用一句话说明主要依据来自知识库还是网络。")
    return "\n".join(parts)


# ==================== 与引擎/主循环状态强耦合的命令处理 ====================
# 这些命令需要直接读写 rag_engine / react_engine / last_rag_sources 等运行时
# 状态，故保留在本模块（而非 cli.handlers），但同样抽成独立函数，使交互主循环
# 的分发逻辑保持精简。每个函数返回 should_show_recommendations。

def _render_answer(answer: str):
    """统一渲染回答文本（Markdown / 纯文本）。"""
    if state.HAS_RICH:
        state.console.print(Panel(Markdown(answer), border_style="green"))
    else:
        print(answer)


def _live_answer(title: str = None):
    """构造终端流式答案渲染器（F10 P1-1；非 Rich 终端为空操作）。"""
    from cli.handlers import LiveAnswer

    return LiveAnswer(state.console, state.HAS_RICH, title=title)


def _print_notices(notices, position: str = "before") -> None:
    """渲染 ``answer_question`` 的结构化提示（F9 P0-5）。

    warn → 黄色 ``⚠️ text``，info → dim ``💡 text``；``fallback`` 不在此打印（沿用
    ``_run_ask`` 末尾的黄色 ``/agent`` 提示行）。``position`` 选择答案 Panel 之前/之后的那组。
    """
    from rich.markup import escape as _escape
    for n in notices or []:
        if not isinstance(n, dict) or n.get("code") == "fallback":
            continue
        if (n.get("position") or "before") != position:
            continue
        text = _escape(str(n.get("text") or ""))
        if not text:
            continue
        if n.get("level") == "warn":
            state.console.print(f"⚠️ {text}", style="yellow")
        else:
            state.console.print(f"💡 {text}", style="dim")


def _citation_summary(citation_check) -> str:
    """来源摘要行的引用计数文案 ``🔎 引用 {valid}/{total} 有效``；无引用返回空串。"""
    if not isinstance(citation_check, dict):
        return ""
    total = int(citation_check.get("total_refs") or 0)
    if total <= 0:
        return ""
    valid = int(citation_check.get("valid") or 0)
    return f"🔎 引用 {valid}/{total} 有效"


def handle_clear(ctx, parsed):
    state.console.clear()
    print_banner()
    record_command_execution("clear")
    return True


def handle_history(ctx, parsed):
    from session_manager import get_session_manager
    manager = get_session_manager()
    current = manager.get_current_session()
    msgs = current.messages if current else []
    dialog_msgs = [m for m in msgs if m.get("role") in ("user", "assistant")]
    if not dialog_msgs:
        state.console.print("[dim]暂无对话历史[/dim]")
        return False
    lines = []
    for i, m in enumerate(dialog_msgs):
        role = m.get("role", "?")
        content = m.get("content", "")[:80].replace("\n", " ")
        lines.append(f"{i}. [{role}] {content}...")
    title = f"历史记录 - {current.title}" if current else "历史记录"
    if state.HAS_RICH:
        state.console.print(Panel("\n".join(lines), title=title, border_style="dim"))
    else:
        print("\n".join(lines))
    record_command_execution("history")
    return True


def handle_summary(ctx, parsed):
    summary = state.react_engine.get_step_summary()
    if state.HAS_RICH:
        state.console.print(Panel(summary, title="执行摘要", border_style="blue"))
    else:
        print(summary)
    record_command_execution("summary")
    return True


def handle_reset(ctx, parsed):
    """清空当前会话的对话上下文（消息 + 滚动摘要），三种模式共用。"""
    engine = ctx.react_engine if ctx and ctx.react_engine is not None else state.react_engine
    ok = engine.clear_history() if engine is not None else _conversation().clear()
    if ok:
        state.console.print("🔄 当前会话上下文已清空（消息与滚动摘要）", style="green")
    else:
        state.console.print("[dim]当前没有可清空的会话上下文[/dim]")
    record_command_execution("reset")
    return True


def handle_file(ctx, parsed):
    path = parsed.arg
    result = registry.execute("read_file", {"path": path}, auto_confirm=True)
    if state.HAS_RICH:
        state.console.print(Panel(result, title=f"文件: {path}", border_style="blue"))
    else:
        print(result)
        record_command_execution("read", path)
    return True


def handle_write(ctx, parsed):
    path = parsed.arg
    state.console.print("[yellow]进入写入模式，输入内容（空行结束）:[/yellow]")
    lines = []
    while True:
        try:
            line = input()
        except (EOFError, KeyboardInterrupt):
            break
        if line == "":
            break
        lines.append(line)
    content = "\n".join(lines)
    result = registry.execute("write_file", {"path": path, "content": content}, auto_confirm=False)
    state.console.print(result)
    record_command_execution("write", path)
    return True


def handle_exec(ctx, parsed):
    cmd = parsed.arg
    safety = CommandSafetyChecker.analyze(cmd)
    if state.HAS_RICH:
        color = {"low": "green", "medium": "yellow", "high": "red", "critical": "red"}.get(safety['risk_level'], "white")
        state.console.print(f"[dim]命令: {cmd}[/dim]")
        state.console.print(f"风险等级: [{color}]{safety['risk_level']}[/{color}]")
    else:
        print(f"命令: {cmd}")
        print(f"风险等级: {safety['risk_level']}")

    if safety["is_dangerous"]:
        state.console.print("[red]该命令被安全系统拦截，拒绝执行。[/red]")
        return False
    # AUTO_CONFIRM 只放行 low / medium；high 仍需人工确认（F10 P0-1-c）
    if safety["needs_confirm"] and not (Config.AUTO_CONFIRM and auto_confirm_allows(safety)):
        if Config.AUTO_CONFIRM:
            state.console.print(f"[yellow]{HIGH_RISK_CONFIRM_HINT}"
                          f"（自动确认只放行 low / medium）[/yellow]")
        try:
            ans = state.console.input("确认执行? (y/n): ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("已取消")
            return False
        if ans not in ("y", "yes", "是"):
            state.console.print("[dim]已取消[/dim]")
            return False

    result = registry.execute("execute_command", {"command": cmd}, auto_confirm=True)
    if state.HAS_RICH:
        state.console.print(Panel(result, title="命令输出", border_style="magenta"))
    else:
        print(result)
    record_command_execution("exec", cmd)
    return True


def handle_pwd(ctx, parsed):
    print(os.getcwd())
    record_command_execution("pwd")
    return True


def handle_cd(ctx, parsed):
    path = parsed.arg
    try:
        os.chdir(path)
        state.console.print(f"[green]已切换到: {os.getcwd()}[/green]")
        record_command_execution("cd", path)
        return True
    except FileNotFoundError:
        state.console.print(f"[red]目录不存在: {path}[/red]")
    except PermissionError:
        state.console.print(f"[red]权限不足: {path}[/red]")
    except Exception as e:  # noqa: BLE001
        state.console.print(f"[red]切换失败: {e}[/red]")
    return False


def handle_model(ctx, parsed):
    """``/model`` 显示当前模型；``/model list`` 列出可选；``/model <name>`` 热切换。

    切换会同步 RAG 引擎（重建 LLM 与检索器）、ReAct 引擎（模型名 +
    num_ctx）与全局 config（多 Agent 等跟随），并立即释放旧模型避免双驻留。
    """
    import model_switcher

    arg = (parsed.arg or "").strip()
    record_command_execution("model")

    if not arg:
        info = model_switcher.current_model_info()
        provider = info.get("provider") or "ollama"
        if provider == "ollama":
            state_text = (
                f"已加载，驻留 {model_switcher.format_size(info['size_bytes'])}"
                if info["loaded"] else "未加载（首次请求时按需加载）"
            )
            state.console.print(f"[green]模型: {info['model']}[/green]  ({state_text})")
            state.console.print(f"[green]上下文: num_ctx={info['num_ctx']}  思考模式: {'开' if info['think'] else '关'}[/green]")
            state.console.print(f"[green]Ollama: {state.react_engine.host if state.react_engine else Config.OLLAMA_HOST}[/green]")
        else:
            # OpenAI 兼容后端：驻留 / num_ctx / 思考模式由后端管理，不显示 Ollama 专有状态
            state.console.print(f"[green]模型: {info['model']}[/green]")
            state.console.print(f"[green]后端: {provider} @ {info.get('base_url') or Config.LLM_BASE_URL}[/green]")
            state.console.print("[dim]num_ctx / 思考模式由后端决定；嵌入模型仍走 Ollama[/dim]")
        state.console.print(f"[green]自动确认: {Config.AUTO_CONFIRM}[/green]")
        others = [m for m in info["loaded_models"] if m != info["model"]]
        if others:
            state.console.print(f"[yellow]提示: 内存中还驻留着其他模型: {', '.join(others)}（可用 ollama stop 释放）[/yellow]")
        state.console.print("[dim]用法: /model list 查看可选模型；/model <name> 切换（如 /model qwen3.5:9b）[/dim]")
        return True

    if arg.lower() in ("list", "ls"):
        installed = model_switcher.list_installed_models()
        notice = model_switcher.models_notice()
        if not installed:
            state.console.print(f"[red]{notice or '无法获取模型列表，请确认 Ollama 已启动'}[/red]")
            return True
        if notice:
            # openai 模式后端未提供 /v1/models：列表只有当前模型，/model <name> 可切到任意名字
            state.console.print(f"[yellow]{notice}[/yellow]")
        loaded = {m["name"] for m in model_switcher.list_loaded_models()}
        current = Config.LLM_MODEL
        state.console.print("[bold]本机已安装模型:[/bold]" if not notice else "[bold]可用模型:[/bold]")
        for name in installed:
            marks = []
            if name == current:
                marks.append("当前")
            if name in loaded:
                marks.append("已加载")
            suffix = f"  [{'/'.join(marks)}]" if marks else ""
            state.console.print(f"  - {name}{suffix}")
        state.console.print("[dim]切换: /model <name>[/dim]")
        return True

    result = model_switcher.switch_model(
        arg, rag_engine=ctx.rag_engine if ctx else state.rag_engine,
        react_engine=ctx.react_engine if ctx else state.react_engine,
    )
    color = "green" if result.ok else "red"
    state.console.print(f"[{color}]{result.message}[/{color}]")
    return True


def handle_think(ctx, parsed):
    """``/think`` 显示思考模式状态；``/think on|off`` 运行时开关。

    同步 RAG 引擎（重建 LLM）与 ReAct 引擎；开启前会校验当前模型是否支持 thinking。
    """
    import model_switcher

    arg = (parsed.arg or "").strip()
    record_command_execution("think")

    if not arg:
        info = model_switcher.current_model_info()
        state_text = "开" if info["think"] else "关"
        state.console.print(f"[green]思考模式: {state_text}  （模型: {info['model']}）[/green]")
        state.console.print(
            "[dim]关闭时响应更快（4B 模型同一问题约 31s → 3s），适合日常查询与工具调用；"
            "开启时模型先输出思维链再作答，适合复杂推理。用法: /think on | /think off[/dim]"
        )
        return True

    flag = model_switcher.parse_think_flag(arg)
    if flag is None:
        state.console.print(f"[red]无法识别参数 '{arg}'，请使用 /think on 或 /think off[/red]")
        return True

    result = model_switcher.switch_think(
        flag, rag_engine=ctx.rag_engine if ctx else state.rag_engine,
        react_engine=ctx.react_engine if ctx else state.react_engine,
    )
    color = "green" if result.ok else "red"
    state.console.print(f"[{color}]{result.message}[/{color}]")
    return True


def handle_auto(ctx, parsed):
    """``/auto`` 显示自动路由状态；``/auto on|off`` 运行时开关（F8 P3-2）。

    开启时自然语言输入先由 ``intent_router.classify_intent`` 判定走知识库还是
    Agent；关闭后一律走知识库问答（等价 ``/ask``）。显式命令不受影响。
    """
    import model_switcher

    arg = (parsed.arg or "").strip()
    record_command_execution("auto")

    if not arg:
        state_text = "开" if Config.AUTO_ROUTE else "关"
        state.console.print(f"[green]自动路由: {state_text}[/green]")
        state.console.print(
            "[dim]开启时自然语言输入先判定意图：含路径/代码/命令式动词走 Agent，疑问/总结类走知识库，"
            "模糊时由模型一词判定；关闭后一律走知识库问答。/ask、/agent 显式命令不判定。"
            "用法: /auto on | /auto off[/dim]"
        )
        return True

    flag = model_switcher.parse_think_flag(arg)
    if flag is None:
        state.console.print(f"[red]无法识别参数 '{arg}'，请使用 /auto on 或 /auto off[/red]")
        return True

    Config.AUTO_ROUTE = flag
    if flag:
        state.console.print("[green]自动路由已开启：自然语言输入将自动判定走知识库还是 Agent[/green]")
    else:
        state.console.print("[green]自动路由已关闭：自然语言输入一律走知识库问答（/agent 可显式使用 Agent）[/green]")
    return True


def handle_ask(ctx, parsed):
    """知识库查询：可选文件入库 + 网络搜索增强 + RAG/LLM 回答与回退。

    核心编排逻辑已下沉到共享层 ``rag_pipeline.answer_question``（CLI 与 Web
    共用）；本函数只负责 CLI 特有的内联文件入库、Rich 进度/来源渲染。
    """
    return _run_ask(ctx, parsed.arg, cmd_name="ask")


def _run_ask(ctx, question: str, cmd_name: str = "ask") -> bool:
    """``/ask`` 与自然语言输入共用的知识库问答实现（带会话上下文）。"""
    import re

    original_question = question  # 用于命令记录，避免把搜索结果正文塞进历史

    # 元/概览类问题会在 answer_question 内部识别并通过 meta_overview 事件渲染。
    # 检测用户是否在问题中提供了本地文件路径（图片/PDF/MD/TXT 等）——CLI 独有。
    if not _is_meta_query(original_question):
        file_pattern = r'/Users/[^\s\)]+\.(png|jpg|jpeg|PNG|JPG|JPEG|pdf|PDF|md|MD|txt|TXT)'
        file_path_match = re.search(file_pattern, question)
        if file_path_match:
            question = _ingest_inline_file(file_path_match.group(), question)

    # 连续对话：提问前先做健康度快照（空闲/话题漂移），并把会话上下文交给编排层
    # 用于追问改写与综合 prompt 注入。
    pre_health = _health_before(original_question)
    try:
        conv = _conversation()
    except Exception as e:  # noqa: BLE001 - 会话不可用时退化为无记忆问答
        logger.warning(f"会话上下文不可用: {e}")
        conv = None

    # 调用共享编排层：网络搜索规划、双区综合、0 命中回退、元查询直答一体化。
    # F10 P1-1：综合回答阶段逐 token 刷新实时面板；Ctrl+C 关闭连接并提示已中断。
    rag_progress = ask_progress_callback if Config.SHOW_PROGRESS else None
    live = _live_answer()
    try:
        result = rag_pipeline.answer_question(
            state.rag_engine,
            question,
            enable_web_search=True,
            show_progress=Config.SHOW_PROGRESS,
            progress=_cli_ask_progress,
            rag_progress_callback=rag_progress,
            context=conv,
            on_token=live.on_token,
        )
    except KeyboardInterrupt:
        live.finish()
        state.console.print("\n[yellow]已中断，已关闭与模型的连接。[/yellow]")
        return False
    finally:
        live.finish()

    # 元查询：概览已在 _cli_ask_progress 中渲染，这里只记录并返回。
    if result.get("kind") == "meta":
        state.last_rag_sources = []
        state.last_web_sources = []
        ctx.last_rag_sources = state.last_rag_sources
        ctx.last_web_sources = state.last_web_sources
        record_command_execution(cmd_name, original_question)
        record_conversation(original_question, "[知识库概览]", progress=_cli_ask_progress)
        return True

    state.console.print("\n🤖 回答:", style="bold blue")
    if result.get("rewritten"):
        # F9 P1-2：质疑类追问复用同一通道，文案改为「重新核对」
        label = "🔁 用户质疑，重新核对" if result.get("challenge") else "🔗 已理解为"
        state.console.print(f"[cyan]{label}：{result['rewritten']}[/cyan]")
    # F9 P0-5：警示 / 校验等结构化提示与正文分离——before 组在 Panel 上方，after 组在下方
    notices = result.get("notices") or []
    _print_notices(notices, position="before")
    _render_answer(result["answer"])
    _print_notices(notices, position="after")

    state.last_rag_sources = result.get("kb_sources", [])
    state.last_web_sources = result.get("web_sources", [])
    ctx.last_rag_sources = state.last_rag_sources
    ctx.last_web_sources = state.last_web_sources

    # 确定性双区块来源展示：明确区分知识库来源与网络来源
    check = result.get("citation_check")
    cite = _citation_summary(check)
    cite_style = "yellow" if (isinstance(check, dict) and check.get("invalid")) else "dim"
    if state.last_rag_sources:
        n_code = count_code_sources(state.last_rag_sources)
        suffix = f"（{n_code} 个代码符号）" if n_code else ""
        # P0-3：同一行追加引用计数；有无效引用时整行黄色
        state.console.print(
            f"\n📚 基于知识库 {len(state.last_rag_sources)} 个片段{suffix}" + (f" · {cite}" if cite else ""),
            style=cite_style,
        )
    elif cite:
        state.console.print(f"\n{cite}", style=cite_style)
    if state.last_web_sources:
        state.console.print()
        print_web_sources(state.last_web_sources)
    if state.last_rag_sources or state.last_web_sources:
        state.console.print("[dim]输入 /sources 查看完整来源明细（编号与回答中的 [n]/[Wn] 对应）[/dim]")

    # 失败回退：知识库与网络均无结果 → 提示改用单 Agent 工具进一步查找
    if result.get("kind") == "fallback":
        fq = result.get("fallback_question") or original_question
        state.console.print(f"\n💡 知识库与网络均未找到相关内容，可试试：[bold]/agent {fq}[/bold]", style="yellow")

    record_command_execution(cmd_name, original_question)
    # 会话记录：正文 + warn 级 notice 各一行（后续轮次据此知道上一答是否有依据）
    record_conversation(
        original_question, rag_pipeline.answer_with_notices(result.get("answer", ""), notices),
        rewritten=result.get("rewritten"), progress=_cli_ask_progress,
    )
    _print_health_hint(pre_health, original_question)
    return True


def _ingest_inline_file(file_path: str, question: str) -> str:
    """将问题中检测到的文件加入知识库，并清洗/补全查询文本后返回。"""
    import re
    state.console.print(f"📄 检测到文件路径: {file_path}", style="yellow")
    state.console.print("🔄 正在添加到知识库...", style="yellow")
    try:
        from document_loader import load_documents as _load
        documents = _load(file_path)
        if not documents:
            state.console.print("⚠️ 无法加载文件，直接查询现有知识库", style="yellow")
            return question
        state.rag_engine.add_documents(documents, [file_path])
        if Config.SHOW_PROGRESS:
            state.console.print(f"✅ 已加载 {len(documents)} 个文档", style="green")
            total_chars = sum(len(doc.text) for doc in documents)
            state.console.print(f"✅ 总字符数: {total_chars}", style="dim")
        else:
            state.console.print("✅ 文件已添加到知识库", style="green")
        # 移除路径文本、清理空白与标点
        question = re.sub(re.escape(file_path), '', question)
        question = re.sub(r'\s+', ' ', question).strip().rstrip('，。,.')
        vague = ["请帮我检查", "请帮我分析", "分析", "检查", "看一下", "这张图片里面有什么"]
        if not question or question == "/ask" or question in vague:
            question = f"刚刚添加的文件中包含什么内容？文件名是 {Path(file_path).name}"
            print(f"💡 使用精确查询: {question}")
        else:
            filename = Path(file_path).name
            if filename not in question:
                question = f"{filename} {question}"
        state.console.print(f"❓ 查询: {question}", style="cyan")
    except Exception as e:  # noqa: BLE001
        state.console.print(f"⚠️ 添加文件失败，直接查询现有知识库: {e}", style="yellow")
    return question


def _augment_with_web_search(question: str) -> str:
    """兼容封装：按需执行 LLM 规划的网络搜索（逻辑见 rag_pipeline）。"""
    return rag_pipeline.augment_with_web_search(question, progress=_cli_ask_progress)


def _answer_question(question: str, original_question: str, web_search_result: str) -> dict:
    """兼容封装：根据知识库状态生成回答（逻辑见 rag_pipeline.generate_answer）。"""
    rag_progress = ask_progress_callback if Config.SHOW_PROGRESS else None
    return rag_pipeline.generate_answer(
        state.rag_engine,
        question,
        original_question,
        web_search_result,
        show_progress=Config.SHOW_PROGRESS,
        progress=_cli_ask_progress,
        rag_progress_callback=rag_progress,
    )


def handle_agent(ctx, parsed):
    task = parsed.arg
    answer = ""
    engine = ctx.react_engine if (ctx is not None and getattr(ctx, "react_engine", None) is not None) else state.react_engine
    pre_health = _health_before(task)
    # F10 P1-1：Final Answer 逐 token 刷新实时面板（工具步骤仍走 on_step 面板输出）；
    # Ctrl+C 时 engine.stop() 关闭流式连接。
    live = _live_answer(title="Agent")
    prev_sink = getattr(engine, "on_token", None)
    engine.on_token = live.on_token  # 引擎级回调：本次 chat() 生效，结束后恢复
    try:
        answer = engine.chat(task)
    except KeyboardInterrupt:
        live.finish()
        engine.stop()
        state.console.print("\n[yellow]已中断：用户中断，任务已停止，已关闭与模型的连接。[/yellow]")
        return False
    except Exception as e:  # noqa: BLE001
        live.finish()
        state.console.print(f"[red]错误: {e}[/red]")
        return False
    finally:
        engine.on_token = prev_sink
        live.finish()

    if state.HAS_RICH:
        if "```" in answer or "**" in answer or "#" in answer:
            state.console.print(Markdown(answer))
        else:
            state.console.print(Panel(answer, border_style="green", title="Agent", box=box.ROUNDED))
    else:
        print("\n" + "=" * 50)
        print(answer)
        print("=" * 50 + "\n")

    if len(engine.step_log) > 1:
        state.console.print(f"[dim]本次共执行 {len(engine.step_log)} 步，输入 /summary 查看详情[/dim]")
    # ReAct 引擎已在 chat() 结束时把本轮（任务 + 最终答案 + 执行摘要）写回会话
    record_command_execution("agent", task)
    _print_health_hint(pre_health, task)
    return True


def handle_natural(ctx, parsed):
    """自然语言输入：与 ``/ask`` 走同一条带会话上下文的问答链路。

    此前直接裸调 ``query_with_sources``、不记录会话、无联网增强，且知识库
    未初始化时只能提示；现统一到 ``_run_ask``（知识库为空时由编排层自动
    回退到网络/模型回答），追问同样能结合上下文理解。
    """
    text = parsed.arg
    engine = ctx.rag_engine if (ctx is not None and getattr(ctx, "rag_engine", None) is not None) else state.rag_engine
    kb_available = bool(engine is not None and getattr(engine, "retriever", None) is not None)

    # F8 P3-2：自动路由——先判定意图，再决定走知识库问答还是 Agent
    if Config.AUTO_ROUTE and _route_natural_to_agent(ctx, text, kb_available):
        return handle_agent(ctx, ParsedCommand("agent", parsed.raw, text))

    if state.rag_engine is not None and state.rag_engine.retriever is None:
        state.console.print(
            "[dim]知识库未初始化，将根据网络搜索/模型直接回答；"
            "可用 /add <文件> 添加文档，或 /agent <任务> 使用 Agent 模式[/dim]"
        )
    return _run_ask(ctx, text, cmd_name="natural")


def _route_natural_to_agent(ctx, text: str, kb_available: bool) -> bool:
    """自动路由判定：返回 True 表示应按 Agent 处理（并已打印状态行）。

    判定失败或 Agent 引擎不可用时返回 False（走知识库问答），不影响主流程。
    """
    engine = ctx.react_engine if (ctx is not None and getattr(ctx, "react_engine", None) is not None) else state.react_engine
    if engine is None:
        return False
    try:
        from intent_router import classify_intent
        decision = classify_intent(text, kb_available=kb_available)
    except Exception as e:  # noqa: BLE001
        logger.debug("自动路由判定失败，回退知识库问答: %s", e)
        return False
    if decision.mode != "agent":
        return False
    state.console.print(
        f"[cyan]🤖 已按 Agent 模式处理（{decision.reason}；用 /ask 强制知识库；/auto off 关闭自动路由）[/cyan]"
    )
    return True


def handle_unknown_cmd(ctx, parsed):
    state.console.print(f"[yellow]未知命令: {parsed.raw}，输入 /help 查看帮助[/yellow]")
    return False


# 引擎/状态耦合命令的分发表（与 cli.handlers.COMMAND_HANDLERS 互补）
_ENGINE_HANDLERS = {
    "clear": handle_clear,
    "history": handle_history,
    "summary": handle_summary,
    "reset": handle_reset,
    "file": handle_file,
    "write": handle_write,
    "exec": handle_exec,
    "pwd": handle_pwd,
    "cd": handle_cd,
    "model": handle_model,
    "think": handle_think,
    "auto": handle_auto,
    "ask": handle_ask,
    "agent": handle_agent,
    "natural": handle_natural,
    "unknown_cmd": handle_unknown_cmd,
}


def _build_cli_context():
    """构造注入了当前运行时状态/协作函数的 CLIContext。"""
    from cli.handlers import CLIContext
    return CLIContext(
        console=state.console,
        has_rich=state.HAS_RICH,
        rag_engine=state.rag_engine,
        react_engine=state.react_engine,
        last_rag_sources=state.last_rag_sources,
        last_web_sources=state.last_web_sources,
        record_command=record_command_execution,
        record_conversation=record_conversation,
        ask_progress_callback=ask_progress_callback,
        print_help=print_help,
        print_tools=print_tools,
        show_tutorial=show_tutorial,
        print_banner=print_banner,
        print_knowledge_stats=print_knowledge_stats,
        print_rag_sources=print_rag_sources,
        print_web_sources=print_web_sources,
        load_documents=load_documents,
        registry=registry,
        knowledge_management_available=KNOWLEDGE_MANAGEMENT_AVAILABLE,
    )


def dispatch_command(ctx, parsed) -> bool:
    """根据 parsed.cmd_type 分发到对应 handler，返回是否显示命令推荐。

    优先使用引擎耦合分发表，其次使用 cli.handlers 的自包含命令表。
    未匹配的类型（如 empty）默认不显示推荐。
    """
    from cli.handlers import COMMAND_HANDLERS
    handler = _ENGINE_HANDLERS.get(parsed.cmd_type) or COMMAND_HANDLERS.get(parsed.cmd_type)
    if handler is None:
        return False
    return handler(ctx, parsed)


# ==================== 主程序 ====================

def main():
    parser = argparse.ArgumentParser(
        description="Cerebro 🧠 你的第二大脑 + 代码助手 - RAG + Agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""
示例:
  # 启动并加载已有知识库
  python query_interface.py

  # 启动并构建新知识库
  python query_interface.py --data ./my_docs

  # 指定模型（默认 qwen3.5:4b；内存宽裕时可用 qwen3.5:9b，运行中可用 /model 切换）
  python query_interface.py --model qwen3.5:9b

  # 单次知识库查询
  python query_interface.py --data ./papers --query "实验结果是什么？"

  # 只构建索引
  python query_interface.py --data ./papers --build-only

  # Agent 模式执行单次任务
  python query_interface.py --agent "检查 main.py 的语法错误"
        """
    )
    parser.add_argument("--data", "-d", help="数据目录或文件路径，用于构建知识库")
    parser.add_argument("--query", "-q", help="单次知识库查询")
    parser.add_argument("--agent", "-a", help="单次 Agent 任务")
    parser.add_argument("--types", "-t", help="文件类型过滤，如: .pdf,.md,.txt")
    parser.add_argument("--build-only", "-b", action="store_true", help="只构建索引")
    parser.add_argument("--clear", action="store_true", help="清空现有索引")
    parser.add_argument("--model", default=LLM_MODEL, help="Ollama 模型名")
    parser.add_argument("--host", default=OLLAMA_BASE_URL, help="Ollama 服务地址")
    parser.add_argument("--no-history", action="store_true", help="不使用历史记录")
    parser.add_argument("--yes", action="store_true", help="自动确认所有命令（危险！仅自动化脚本使用）")
    parser.add_argument("--tutorial", action="store_true", help="启动时显示教程")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="在终端输出 INFO 级别日志（默认仅 WARNING+，完整日志写入 logs/cli.log）")
    args = parser.parse_args()

    # 统一配置日志：终端默认 WARNING，--verbose 拉回 INFO；INFO 完整写入文件
    setup_logging(verbose=getattr(args, "verbose", False))

    # 环境变量覆盖
    os.environ["LLM_MODEL"] = args.model
    os.environ["OLLAMA_BASE_URL"] = args.host
    if args.yes:
        os.environ["CODE_AGENT_AUTO_CONFIRM"] = "true"
        print("[警告] 已启用自动确认模式，所有命令将直接执行！")

    setup_readline()
    print_banner()

    if args.tutorial:
        show_tutorial()
    else:
        check_first_run()

    # ==================== 初始化 RAG 引擎 ====================
    if args.clear:
        state.rag_engine = RAGEngine()
        state.rag_engine.clear_index()
        return

    state.rag_engine = RAGEngine()
    if args.data:
        file_types = None
        if args.types:
            file_types = [t.strip() for t in args.types.split(",")]
        documents = load_documents(args.data, file_types)
        if documents:
            # 传入 file_paths：文档缺 file_path 元数据时仍能登记文件元数据
            state.rag_engine.build_index(documents, file_paths=[args.data])
            try:
                from code_chunker import format_ingest_summary
                stats = getattr(state.rag_engine, "last_ingest_stats", None) or {}
                if stats:
                    state.console.print(f"📦 {format_ingest_summary(stats)}", style="dim")
            except Exception:  # noqa: BLE001
                pass
        else:
            state.console.print("⚠️  未找到任何文档", style="yellow")
    else:
        if not state.rag_engine.load_index():
            state.console.print(
                f"[dim]未找到已有索引。使用 --data 指定数据路径构建知识库。[/dim]\n"
                f"[dim]默认数据目录: {DATA_DIR}[/dim]"
            )
    
    # ==================== 初始化命令推荐系统 ====================
    logger.info(f"开始初始化推荐系统: RECOMMENDER_AVAILABLE={RECOMMENDER_AVAILABLE}")
    if RECOMMENDER_AVAILABLE:
        try:
            logger.info("创建 CommandRecommender 实例")
            state.command_recommender = CommandRecommender()
            logger.info("初始化 CommandRecommender")
            state.command_recommender.initialize()
            logger.info("CommandRecommender 初始化完成")
            
            # 更新RAG引擎状态到推荐系统
            rag_available = state.rag_engine.retriever is not None
            rag_empty = rag_available and (state.rag_engine.get_stats().get("total_chunks", 0) == 0)
            state.command_recommender.update_rag_status(rag_available, rag_empty)
            
            state.console.print("[dim]💡 智能命令推荐系统已启用[/dim]", style="dim")
            logger.info(f"命令推荐系统初始化成功: enabled={state.command_recommender.is_enabled()}")
        except Exception as e:
            state.console.print(f"[dim]⚠️  命令推荐系统初始化失败: {e}[/dim]", style="dim")
            logger.error(f"命令推荐系统初始化失败: {e}", exc_info=True)
            state.command_recommender = None
    else:
        state.console.print("[dim]💡 命令推荐系统模块未安装[/dim]", style="dim")
        logger.warning("推荐系统模块未安装")
        state.command_recommender = None

    # 将 RAG 引擎注入 Agent 工具
    set_rag_engine(state.rag_engine)

    # ==================== 初始化 ReAct 引擎 ====================
    try:
        state.react_engine = ReActEngine(
            model=args.model,
            host=args.host,
            on_step=on_step_callback,
            on_confirm=on_confirm_callback
        )
    except Exception as e:
        state.console.print(f"[red]Agent 引擎初始化失败: {e}[/red]")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    # 会话上下文：首次获取时会把旧的 ~/.code_agent_history.json 一次性迁入默认会话
    try:
        conv = _conversation()
        if args.no_history:
            conv.new_session()
            state.console.print("[yellow]已新建空会话，以全新上下文开始[/yellow]")
    except Exception as e:  # noqa: BLE001
        state.console.print(f"[dim]⚠️ 会话上下文初始化失败（将无记忆运行）: {e}[/dim]")

    # ==================== 单次模式 ====================
    if args.query:
        if state.rag_engine.retriever is None:
            state.console.print("❌ 知识库未初始化，请使用 --data 指定数据", style="red")
            sys.exit(1)
        state.console.print(f"🔍 问题: {args.query}\n", style="bold")
        # F9 P0-1：与 /ask 同一条忠实性管道（只用知识库、不联网、不记录会话）
        with state.console.status("[bold green]检索知识库..."):
            result = rag_pipeline.answer_question(
                state.rag_engine, args.query, enable_web_search=False, show_progress=False, kb_only=True,
            )
        state.console.print("🤖 回答:", style="bold blue")
        _print_notices(result.get("notices"), position="before")
        _render_answer(result.get("answer", ""))
        _print_notices(result.get("notices"), position="after")
        state.last_rag_sources = result.get("kb_sources", [])
        if state.last_rag_sources:
            print_rag_sources(state.last_rag_sources)
        return

    if args.agent:
        state.console.print(f"🤖 Agent 任务: {args.agent}\n", style="bold cyan")
        live = _live_answer(title="Agent")
        try:
            answer = state.react_engine.chat(args.agent, on_token=live.on_token)
        except KeyboardInterrupt:
            live.finish()
            state.react_engine.stop()
            state.console.print("\n[yellow]已中断：用户中断，已关闭与模型的连接。[/yellow]")
            return
        finally:
            live.finish()
        if state.HAS_RICH:
            if "```" in answer or "**" in answer or "#" in answer:
                state.console.print(Markdown(answer))
            else:
                state.console.print(Panel(answer, border_style="green", title="Agent", box=box.ROUNDED))
        else:
            print("\n" + "=" * 50)
            print(answer)
            print("=" * 50 + "\n")
        return

    if args.build_only:
        if state.rag_engine.retriever is not None:
            stats = state.rag_engine.get_stats()
            state.console.print(f"\n✅ 索引构建完成！", style="bold green")
            print_knowledge_stats()
        else:
            state.console.print("❌ 索引构建失败", style="red")
        return

    # ==================== 交互式模式 ====================
    print_help()

    while True:
        try:
            user_input = get_input("\n❯ ")
        except (EOFError, KeyboardInterrupt):
            state.console.print("\n\n👋 再见！", style="bold green")
            break

        if not user_input:
            continue

        parsed = parse_command(user_input)

        # 退出单独处理（需要 break 主循环）
        if parsed.cmd_type == "quit":
            state.console.print("👋 再见！", style="bold green")
            break

        # 构造上下文并通过命令表分发。dispatch_command 返回
        # should_show_recommendations（未匹配的类型如 empty 返回 False）。
        ctx = _build_cli_context()
        should_show_recommendations = dispatch_command(ctx, parsed)

        # 处理期间可能更新了运行时状态，同步回模块全局
        state.last_rag_sources = ctx.last_rag_sources
        state.last_web_sources = ctx.last_web_sources

        # 统一在命令处理完成后显示推荐
        if should_show_recommendations:
            show_command_recommendations()

if __name__ == "__main__":
    main()
