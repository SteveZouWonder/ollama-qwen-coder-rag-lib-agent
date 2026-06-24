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

try:
    import readline
    HAS_READLINE = True
except ImportError:
    HAS_READLINE = False

try:
    from rich.console import Console
    from rich.markdown import Markdown
    from rich.panel import Panel
    from rich.syntax import Syntax
    from rich import box
    from rich.table import Table
    from rich.prompt import Prompt
    HAS_RICH = True
except ImportError:
    HAS_RICH = False
    print("[提示] 安装 rich 可获得更好的输出体验: pip install rich")

try:
    from prompt_toolkit import prompt as pt_prompt
    from prompt_toolkit.history import FileHistory
    from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
    HAS_PROMPT_TOOLKIT = True
except ImportError:
    HAS_PROMPT_TOOLKIT = False

from config import Config, DATA_DIR, INDEX_DIR, LLM_MODEL, OLLAMA_BASE_URL
from rag_engine import RAGEngine, build_knowledge_base
from react_engine import ReActEngine
from agent_tools import registry, CommandSafetyChecker, set_rag_engine
from document_loader import load_documents

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

# ==================== 全局状态 ====================
rag_engine: RAGEngine = None
react_engine: ReActEngine = None
last_rag_sources = []
command_recommender: CommandRecommender = None


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

# ==================== 教程 ====================

TUTORIAL_TEXT = """
欢迎使用 Cerebro 🧠 — 你的第二大脑 + 代码助手！

本工具融合了两套核心能力：

1. 📚 RAG 知识库
   基于 LlamaIndex + ChromaDB 构建的个人文档检索系统。
   支持 PDF、Markdown、论文、代码文件等 14 种格式。
   上传文档后，可直接用自然语言查询内容。

2. 🤖 ReAct Agent
   基于 Ollama + ReAct 架构的代码助手。
   自动读写文件、执行命令、搜索代码、多步推理。
   带安全护栏：危险命令自动拦截，修改命令需确认。

快速上手示例：

  # 知识库查询
  >>> /ask 这篇论文的核心贡献是什么？
  >>> /ask 总结一下笔记中的关键概念

  # Agent 任务（自动调用工具）
  >>> /agent 写一个 Python 快速排序，保存到 sort.py，然后运行单元测试
  >>> /agent 检查 src/main.py 第 20-50 行是否有内存泄漏
  >>> /agent 搜索项目中所有硬编码的 API Key

  # 快捷命令
  >>> /file main.py          快速读取文件
  >>> /exec git status       执行命令
  >>> /add ./新论文.pdf       添加文档到知识库
  >>> /stats                 查看知识库统计

常用内置命令：
  /help      显示帮助
  /tutorial  重新显示本教程
  /ask       直接查询知识库
  /agent     进入 Agent 任务模式
  /tools     查看所有可用工具
  /add       添加文档到知识库
  /stats     知识库统计
  /sources   显示上次回答的来源
  /clear     清空屏幕
  /history   查看对话历史
  /summary   查看 Agent 执行摘要
  /file      快速读取文件
  /write     交互式写入文件
  /exec      执行命令（走安全确认）
  /pwd       显示当前目录
  /cd        切换目录
  /model     显示模型信息
  /reset     重置 Agent 对话上下文
  /quit      退出

文件管理命令：
  /file-list           列出知识库中的所有文件
  /file-info <path>    查看文件详细信息
  /file-cleanup        清理临时/重复文件
  /file-deduplicate    手动触发去重
  /file-stats          显示文件统计信息

会话管理命令：
  /session-new [title]        创建新会话
  /session-list               列出所有会话
  /session-switch <id>        切换到指定会话
  /session-archive <id>       归档会话
  /session-delete <id>       删除会话
  /session-info <id>          查看会话详情
  /session-search <query>     搜索会话
  /session-current            显示当前会话信息
  /session-compress           压缩当前会话历史

网络搜索命令：
  /web-search <query>         网络搜索（支持 DuckDuckGo）
  /web-cache status           查看搜索缓存状态
  /web-cache clear            清空搜索缓存
  /web-extract <url>          提取网页内容

代码分析命令：
  /code-ast <pattern>         AST 搜索（函数、类、变量）
  /code-quality <path>        代码质量检查

Git 命令：
  /git-analyze <type>         Git 分析（history/status/authors）
  /git-commit-gen             AI 生成提交信息

知识图谱命令：
  /graph-query <query>        图谱查询
  /graph-build                构建知识图谱
"""

def show_tutorial():
    if HAS_RICH:
        console.print(Panel(TUTORIAL_TEXT, border_style="cyan", title="使用指引", box=box.ROUNDED))
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
        console.print("\n提示：之后可随时输入 /tutorial 重新查看本教程\n")

# ==================== 回调函数 ====================

# 进度条状态管理
_progress_state = {
    "last_line_length": 0,
    "important_phases": {"executing", "observed", "blocked", "rejected", "final"},
    "current_thinking_dots": 0
}

def on_step_callback(data: dict):
    from config import Config
    
    if not Config.SHOW_PROGRESS:
        return
    
    step = data.get("step", "?")
    total = data.get("total", "?")
    phase = data.get("phase", "?")
    msg = data.get("message", "")

    phase_emoji = {
        "thinking": "[*]",
        "action": "[>]",
        "executing": "[!]",
        "observed": "[=]",
        "blocked": "[X]",
        "rejected": "[-]",
        "final": "[OK]"
    }.get(phase, "[?]")

    if HAS_RICH and Config.PROGRESS_BAR_STYLE == "rich":
        from rich.console import Console as RichConsole
        
        color = {
            "thinking": "cyan",
            "executing": "yellow",
            "blocked": "red",
            "rejected": "red",
            "final": "green"
        }.get(phase, "white")
        
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
            _progress_state["current_thinking_dots"] = (_progress_state["current_thinking_dots"] + 1) % 4
            dots = "." * _progress_state["current_thinking_dots"]
            content = f"[{color}]{phase_emoji} [{step}/{total}] 模型推理中{dots}[/{color}] [dim][{progress_bar}] {progress_percent:.0f}%[/dim]"
            console.print(content, end="\r")
            _progress_state["last_line_length"] = len(content)
            
        elif phase in _progress_state["important_phases"]:
            # 重要步骤：换行输出，保留历史记录
            # 先清理上一行的推理状态
            if _progress_state["last_line_length"] > 0:
                console.print(" " * _progress_state["last_line_length"], end="\r")
                _progress_state["last_line_length"] = 0
            
            console.print(
                f"[{color}]{phase_emoji} [{step}/{total}] {msg}[/{color}] "
                f"[dim][{progress_bar}] {progress_percent:.0f}%[/dim]"
            )
            
        else:
            # 其他阶段：也换行输出
            if _progress_state["last_line_length"] > 0:
                console.print(" " * _progress_state["last_line_length"], end="\r")
                _progress_state["last_line_length"] = 0
                
            console.print(
                f"[{color}]{phase_emoji} [{step}/{total}] {msg}[/{color}] "
                f"[dim][{progress_bar}] {progress_percent:.0f}%[/dim]"
            )
            
    else:
        # 非rich模式：保持原有行为
        print(f"[{step}/{total}] {phase_emoji} {msg}")

def on_confirm_callback(data: dict) -> bool:
    msg = data.get("message", "确认执行?")
    safety = data.get("safety", {})

    if HAS_RICH:
        risk = safety.get("risk_level", "unknown")
        color = {"low": "green", "medium": "yellow", "high": "red", "critical": "red"}.get(risk, "white")
        console.print(Panel(
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
        answer = console.input("确认执行? (y/n): ").strip().lower()
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
    
    if HAS_RICH:
        phase_colors = {
            "embedding": "cyan",
            "retrieving": "blue",
            "scoring": "yellow",
            "generating": "magenta"
        }.get(phase, "white")
        
        if phase == "scoring":
            current = data.get("current", 0)
            total = data.get("total", 1)
            console.print(f"[dim]🔄 {msg} [progress]{current}/{total}[/progress][/dim]")
        else:
            console.print(f"[{phase_colors}]🔄 {msg}[/{phase_colors}]")
    else:
        print(f"🔄 {msg}")

# ==================== 界面渲染 ====================

def print_banner():
    if HAS_RICH:
        console.print(Panel(
            "[bold cyan]Cerebro[/bold cyan] [white]🧠 你的第二大脑 + 代码助手[/white]   [dim]v4.1[/dim]\n"
            "[dim]RAG 知识库 | ReAct Agent | 本地 Ollama | 安全护栏[/dim]\n"
            f"[green]模型: {LLM_MODEL}[/green] | [green]Ollama: {OLLAMA_BASE_URL}[/green]",
            border_style="cyan", box=box.ROUNDED
        ))
    else:
        print("=" * 60)
        print("    Cerebro 🧠 你的第二大脑 + 代码助手  v4.1")
        print("=" * 60)
        print(f"模型: {LLM_MODEL} | Ollama: {OLLAMA_BASE_URL}")
        print("=" * 60)

def print_help():
    help_text = """
内置命令：
  /help              显示本帮助
  /tutorial          显示使用指引教程
  /ask <question>    直接查询知识库（基于上传的文档）
  /agent <task>      进入 Agent 模式（自动调用工具完成复杂任务）
  /tools             查看所有可用工具及安全等级
  /add <path>        添加文档到知识库（PDF/MD/TXT/代码等）
  /stats             显示知识库统计
  /sources           显示上次知识库回答的来源
  /clear             清空屏幕
  /history           显示当前对话历史摘要
  /summary           显示本次 Agent 执行步骤摘要
  /file <path>       快速读取文件（不经过模型）
  /write <path>      交互式写入文件模式
  /exec <cmd>        快速执行命令（走安全确认流程）
  /pwd               显示当前工作目录
  /cd <path>         切换当前工作目录
  /model             显示当前模型信息
  /reset             重置 Agent 对话上下文
  /exit 或 /quit     退出程序

知识库管理命令（新功能）：
  /generate-skills   将知识库内容转化为Devin Skills
  /snapshot-list    查看所有知识库快照
  /snapshot-create  手动创建知识库快照
  /snapshot-restore <id>  恢复指定快照的知识库
  /knowledge-summary  查看知识库文档摘要

知识图谱管理命令（新功能）：
  /graph-query <query>      查询知识图谱
  /graph-build              构建知识图谱

数据库管理命令（新功能）：
  /db-connect <type> <database>  连接数据库
  /db-query <sql>               执行SQL查询
  /db-execute <sql>             执行SQL语句（INSERT/UPDATE/DELETE）
  /db-create-table <table>      创建数据库表
  /db-insert <table> <data>     插入数据
  /db-schema <table>            查看表结构

文件管理命令（新功能）：
  /file-list           列出知识库中的所有文件
  /file-info <path>    查看文件详细信息
  /file-cleanup        清理临时/重复文件
  /file-deduplicate    手动触发去重
  /file-stats          显示文件统计信息

会话管理命令（新功能）：
  /session-new [title]        创建新会话
  /session-list               列出所有会话
  /session-switch <id>        切换到指定会话
  /session-archive <id>       归档会话
  /session-delete <id>       删除会话
  /session-info <id>          查看会话详情
  /session-search <query>     搜索会话
  /session-current            显示当前会话信息
  /session-compress           压缩当前会话历史

网络搜索命令（新功能）：
  /web-search <query>         网络搜索（支持 DuckDuckGo）
  /web-cache status           查看搜索缓存状态
  /web-cache clear            清空搜索缓存
  /web-extract <url>          提取网页内容

代码分析命令（新功能）：
  /code-ast <pattern>         AST 搜索（函数、类、变量）
  /code-quality <path>        代码质量检查

Git 命令（新功能）：
  /git-analyze <type>         Git 分析（history/status/authors）
  /git-commit-gen             AI 生成提交信息

使用示例：
  >>> /ask 这篇论文的实验结果是什么？
  >>> /agent 把 utils.py 里的 print 改成 logging，并运行测试
  >>> /agent 搜索项目中所有使用硬编码密码的地方
  >>> /add ~/Downloads/论文.pdf
  >>> /file src/main.py
  >>> /generate-skills
  >>> /snapshot-list
  >>> /web-search 最新的 Python 稳定版本
  >>> /code-quality src/
  >>> /git-analyze history
"""
    if HAS_RICH:
        console.print(Panel(help_text, border_style="yellow", title="帮助", box=box.ROUNDED))
    else:
        print(help_text)

def print_tools():
    if HAS_RICH:
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
        console.print(table)
        console.print("\n安全规则：")
        console.print("  [green]安全[/green]   = 只读操作，自动执行")
        console.print("  [yellow]需确认[/yellow] = 会修改系统，执行前询问")
        console.print("  [red]危险[/red]     = rm -rf / 等命令会被自动拦截")
    else:
        print("=== 可用工具 ===")
        for name, info in registry.tools.items():
            safe = "安全" if info.get("safe") else "需确认"
            print(f"  {name} [{safe}] - {info['description']}")

def print_rag_sources(sources: list):
    if not sources:
        console.print("⚠️  没有来源信息", style="yellow")
        return
    if HAS_RICH:
        table = Table(title="📚 参考来源", show_lines=True)
        table.add_column("文件", style="cyan", no_wrap=True)
        table.add_column("相似度", style="green", justify="right")
        table.add_column("内容片段", style="white")

        for src in sources:
            score = f"{src['score']:.3f}" if src['score'] else "N/A"
            content = src['content'][:100] + "..." if len(src['content']) > 100 else src['content']
            table.add_row(src['file'], score, content)
        console.print(table)
    else:
        print("=== 参考来源 ===")
        for src in sources:
            score = f"({src['score']:.3f})" if src['score'] else ""
            print(f"  {src['file']} {score}")
            print(f"    {src['content'][:100]}...")

def print_knowledge_stats():
    global rag_engine
    if rag_engine is None:
        console.print("⚠️  知识库未初始化", style="yellow")
        return
    stats = rag_engine.get_stats()
    if HAS_RICH:
        table = Table(title="📊 知识库统计", box=box.ROUNDED)
        table.add_column("项目", style="cyan")
        table.add_column("值", style="white")
        for k, v in stats.items():
            table.add_row(k, str(v))
        console.print(table)
    else:
        print("=== 知识库统计 ===")
        for k, v in stats.items():
            print(f"  {k}: {v}")

# ==================== readline 历史 ====================

def setup_readline():
    if HAS_READLINE:
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
    if HAS_PROMPT_TOOLKIT:
        history = FileHistory(str(INDEX_DIR / ".chat_history"))
        return pt_prompt(prompt_text, history=history, auto_suggest=AutoSuggestFromHistory()).strip()
    else:
        return console.input(prompt_text).strip()

# ==================== 命令路由（纯函数，可单元测试）====================

class ParsedCommand:
    """解析后的命令对象"""
    def __init__(self, cmd_type: str, raw: str, arg: str = ""):
        self.cmd_type = cmd_type
        self.raw = raw
        self.arg = arg

    def __repr__(self):
        return f"ParsedCommand({self.cmd_type!r}, arg={self.arg!r})"

    def __eq__(self, other):
        if not isinstance(other, ParsedCommand):
            return False
        return self.cmd_type == other.cmd_type and self.arg == other.arg


def parse_command(user_input: str) -> ParsedCommand:
    """
    将用户输入解析为命令类型和参数。
    纯函数，无外部依赖，可完全单元测试。
    """
    user_input = user_input.strip()
    if not user_input:
        return ParsedCommand("empty", user_input)

    # 退出命令
    if user_input in ("/exit", "/quit", "exit", "quit"):
        return ParsedCommand("quit", user_input)

    # 无参数命令
    if user_input == "/help":
        return ParsedCommand("help", user_input)
    if user_input == "/tutorial":
        return ParsedCommand("tutorial", user_input)
    if user_input == "/tools":
        return ParsedCommand("tools", user_input)
    if user_input == "/stats":
        return ParsedCommand("stats", user_input)
    if user_input == "/sources":
        return ParsedCommand("sources", user_input)
    if user_input == "/clear":
        return ParsedCommand("clear", user_input)
    if user_input == "/history":
        return ParsedCommand("history", user_input)
    if user_input == "/summary":
        return ParsedCommand("summary", user_input)
    if user_input == "/reset":
        return ParsedCommand("reset", user_input)
    if user_input == "/pwd":
        return ParsedCommand("pwd", user_input)
    if user_input == "/model":
        return ParsedCommand("model", user_input)

    # 带参数命令（至少一个空格分隔）
    parts = user_input.split(None, 1)
    cmd = parts[0]
    arg = parts[1] if len(parts) > 1 else ""

    if cmd == "/ask":
        return ParsedCommand("ask", user_input, arg)
    if cmd == "/agent":
        return ParsedCommand("agent", user_input, arg)
    if cmd == "/add":
        return ParsedCommand("add", user_input, arg)
    if cmd == "/file":
        return ParsedCommand("file", user_input, arg)
    
    # 知识库管理命令
    if cmd == "/generate-skills":
        return ParsedCommand("generate_skills", user_input, arg)
    if cmd == "/snapshot-list":
        return ParsedCommand("snapshot_list", user_input, arg)
    if cmd == "/snapshot-create":
        return ParsedCommand("snapshot_create", user_input, arg)
    if cmd == "/snapshot-restore":
        return ParsedCommand("snapshot_restore", user_input, arg)
    if cmd == "/knowledge-summary":
        return ParsedCommand("knowledge_summary", user_input, arg)
    
    # 知识图谱管理命令
    if cmd == "/graph-query":
        return ParsedCommand("graph_query", user_input, arg)
    if cmd == "/graph-build":
        return ParsedCommand("graph_build", user_input, arg)
    
    # 数据库管理命令
    if cmd == "/db-connect":
        return ParsedCommand("db_connect", user_input, arg)
    if cmd == "/db-query":
        return ParsedCommand("db_query", user_input, arg)
    if cmd == "/db-execute":
        return ParsedCommand("db_execute", user_input, arg)
    if cmd == "/db-create-table":
        return ParsedCommand("db_create_table", user_input, arg)
    if cmd == "/db-insert":
        return ParsedCommand("db_insert", user_input, arg)
    if cmd == "/db-schema":
        return ParsedCommand("db_schema", user_input, arg)

    # 文件管理命令
    if cmd == "/file-list":
        return ParsedCommand("file_list", user_input, arg)
    if cmd == "/file-info":
        return ParsedCommand("file_info", user_input, arg)
    if cmd == "/file-cleanup":
        return ParsedCommand("file_cleanup", user_input, arg)
    if cmd == "/file-deduplicate":
        return ParsedCommand("file_deduplicate", user_input, arg)
    if cmd == "/file-stats":
        return ParsedCommand("file_stats", user_input, arg)

    # 会话管理命令
    if cmd == "/session-new":
        return ParsedCommand("session_new", user_input, arg)
    if cmd == "/session-list":
        return ParsedCommand("session_list", user_input, arg)
    if cmd == "/session-switch":
        return ParsedCommand("session_switch", user_input, arg)
    if cmd == "/session-archive":
        return ParsedCommand("session_archive", user_input, arg)
    if cmd == "/session-delete":
        return ParsedCommand("session_delete", user_input, arg)
    if cmd == "/session-info":
        return ParsedCommand("session_info", user_input, arg)
    if cmd == "/session-search":
        return ParsedCommand("session_search", user_input, arg)
    if cmd == "/session-current":
        return ParsedCommand("session_current", user_input, arg)
    if cmd == "/session-compress":
        return ParsedCommand("session_compress", user_input, arg)

    # 网络搜索命令
    if cmd == "/web-search":
        return ParsedCommand("web_search", user_input, arg)
    if cmd == "/web-cache":
        return ParsedCommand("web_cache", user_input, arg)
    if cmd == "/web-extract":
        return ParsedCommand("web_extract", user_input, arg)

    # 代码分析命令
    if cmd == "/code-ast":
        return ParsedCommand("code_ast", user_input, arg)
    if cmd == "/code-quality":
        return ParsedCommand("code_quality", user_input, arg)

    # Git 命令
    if cmd == "/git-analyze":
        return ParsedCommand("git_analyze", user_input, arg)
    if cmd == "/git-commit-gen":
        return ParsedCommand("git_commit_gen", user_input, arg)

    # 知识图谱命令
    if cmd == "/graph-query":
        return ParsedCommand("graph_query", user_input, arg)
    if cmd == "/graph-build":
        return ParsedCommand("graph_build", user_input, arg)
    
    # 数据库命令
    if cmd == "/db-connect":
        return ParsedCommand("db_connect", user_input, arg)
    if cmd == "/db-query":
        return ParsedCommand("db_query", user_input, arg)
    if cmd == "/db-execute":
        return ParsedCommand("db_execute", user_input, arg)
    if cmd == "/db-create-table":
        return ParsedCommand("db_create_table", user_input, arg)
    if cmd == "/db-insert":
        return ParsedCommand("db_insert", user_input, arg)
    if cmd == "/db-schema":
        return ParsedCommand("db_schema", user_input, arg)

    if cmd == "/write":
        return ParsedCommand("write", user_input, arg)
    if cmd == "/exec":
        return ParsedCommand("exec", user_input, arg)
    if cmd == "/cd":
        return ParsedCommand("cd", user_input, arg)

    # 默认：未识别的命令或自然语言输入
    if user_input.startswith("/"):
        return ParsedCommand("unknown_cmd", user_input, arg)
    return ParsedCommand("natural", user_input, user_input)


def classify_mode(rag_engine_available: bool, parsed: ParsedCommand) -> str:
    """
    根据知识库可用性和解析结果，决定处理模式。
    返回: "rag" | "agent" | "cmd" | "noop"
    """
    cmd_type = parsed.cmd_type

    # 纯命令，不走任何引擎
    if cmd_type in ("help", "tutorial", "tools", "stats", "sources",
                     "clear", "history", "summary", "reset",
                     "pwd", "cd", "model", "quit", "empty", "unknown_cmd",
                     "generate_skills", "snapshot_list", "snapshot_create",
                     "snapshot_restore", "knowledge_summary",
                     "graph_query", "graph_build",
                     "db_connect", "db_query", "db_execute",
                     "db_create_table", "db_insert", "db_schema",
                     "file_list", "file_info", "file_cleanup", "file_deduplicate", "file_stats",
                     "session_new", "session_list", "session_switch", "session_archive",
                     "session_delete", "session_info", "session_search", "session_current",
                     "session_compress", "web_search", "web_cache", "web_extract",
                     "code_ast", "code_quality", "git_analyze", "git_commit_gen",
                     "graph_query", "graph_build"):
        return "cmd"

    # 明确指定 RAG
    if cmd_type == "ask":
        return "rag"
    if cmd_type == "add":
        return "rag"

    # 明确指定 Agent
    if cmd_type == "agent":
        return "agent"
    if cmd_type in ("file", "write", "exec"):
        return "agent"

    # 自然语言输入：有知识库走 RAG，否则提示
    if cmd_type == "natural":
        if rag_engine_available:
            return "rag"
        return "agent"  # 无知识库时，让 Agent 尝试处理

    return "noop"


# ==================== 命令推荐系统辅助函数 ====================

def show_command_recommendations():
    """显示命令推荐"""
    logger.debug(f"show_command_recommendations 调用: command_recommender={command_recommender}")
    
    if not command_recommender:
        logger.debug("command_recommender 为 None")
        return
    
    if not command_recommender.is_enabled():
        logger.debug("command_recommender 已禁用")
        return
    
    try:
        recommendations = command_recommender.get_recommendations()
        logger.debug(f"获得 {len(recommendations) if recommendations else 0} 个推荐")
        
        if recommendations:
            # 默认使用紧凑单行模式，减少视觉噪音
            formatted = command_recommender.format_recommendations(
                recommendations, use_rich=HAS_RICH, compact=True
            )
            if formatted:
                console.print(formatted)
    except Exception as e:
        logger.error(f"推荐系统错误: {e}")
        console.print(f"[dim]⚠️  推荐系统错误: {e}[/dim]", style="dim")

def record_command_execution(cmd_type: str, args: str = "", result: str = "", error: str = ""):
    """记录命令执行到推荐系统"""
    logger.debug(f"record_command_execution: cmd_type={cmd_type}, args={args!r}")
    
    if not command_recommender:
        logger.debug(f"command_recommender 为 None，无法记录命令: {cmd_type}")
        return
    
    try:
        # 截断过长的参数，避免污染历史/上下文（如网络搜索结果正文）
        safe_args = args if len(args) <= 200 else args[:200] + "…"
        # 记录命令
        command_recommender.record_command(f"/{cmd_type}", safe_args, result)
        logger.debug(f"命令已记录: /{cmd_type}")
        
        # 记录错误（如果有）
        if error:
            command_recommender.record_error(error)
            logger.debug(f"错误已记录: {error}")
        
        # 更新RAG状态（可能变化）
        if rag_engine:
            rag_available = rag_engine.query_engine is not None
            rag_empty = rag_available and (rag_engine.get_stats().get("total_chunks", 0) == 0)
            command_recommender.update_rag_status(rag_available, rag_empty)
            logger.debug(f"RAG状态已更新: available={rag_available}, empty={rag_empty}")
        
    except Exception as e:
        logger.error(f"记录命令失败: {e}")


# ==================== 主程序 ====================

def main():
    global rag_engine, react_engine, last_rag_sources, command_recommender

    parser = argparse.ArgumentParser(
        description="Cerebro 🧠 你的第二大脑 + 代码助手 - RAG + Agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""
示例:
  # 启动并加载已有知识库
  python query_interface.py

  # 启动并构建新知识库
  python query_interface.py --data ./my_docs

  # 指定模型
  python query_interface.py --model qwen2.5-coder:7b

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
        rag_engine = RAGEngine()
        rag_engine.clear_index()
        return

    rag_engine = RAGEngine()
    if args.data:
        file_types = None
        if args.types:
            file_types = [t.strip() for t in args.types.split(",")]
        documents = load_documents(args.data, file_types)
        if documents:
            rag_engine.build_index(documents)
        else:
            console.print("⚠️  未找到任何文档", style="yellow")
    else:
        if not rag_engine.load_index():
            console.print(
                f"[dim]未找到已有索引。使用 --data 指定数据路径构建知识库。[/dim]\n"
                f"[dim]默认数据目录: {DATA_DIR}[/dim]"
            )
    
    # ==================== 初始化命令推荐系统 ====================
    logger.info(f"开始初始化推荐系统: RECOMMENDER_AVAILABLE={RECOMMENDER_AVAILABLE}")
    if RECOMMENDER_AVAILABLE:
        try:
            logger.info("创建 CommandRecommender 实例")
            command_recommender = CommandRecommender()
            logger.info("初始化 CommandRecommender")
            command_recommender.initialize()
            logger.info("CommandRecommender 初始化完成")
            
            # 更新RAG引擎状态到推荐系统
            rag_available = rag_engine.query_engine is not None
            rag_empty = rag_available and (rag_engine.get_stats().get("total_chunks", 0) == 0)
            command_recommender.update_rag_status(rag_available, rag_empty)
            
            console.print("[dim]💡 智能命令推荐系统已启用[/dim]", style="dim")
            logger.info(f"命令推荐系统初始化成功: enabled={command_recommender.is_enabled()}")
        except Exception as e:
            console.print(f"[dim]⚠️  命令推荐系统初始化失败: {e}[/dim]", style="dim")
            logger.error(f"命令推荐系统初始化失败: {e}", exc_info=True)
            command_recommender = None
    else:
        console.print("[dim]💡 命令推荐系统模块未安装[/dim]", style="dim")
        logger.warning("推荐系统模块未安装")
        command_recommender = None

    # 将 RAG 引擎注入 Agent 工具
    set_rag_engine(rag_engine)

    # ==================== 初始化 ReAct 引擎 ====================
    try:
        react_engine = ReActEngine(
            model=args.model,
            host=args.host,
            on_step=on_step_callback,
            on_confirm=on_confirm_callback
        )
    except Exception as e:
        console.print(f"[red]Agent 引擎初始化失败: {e}[/red]")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    if args.no_history:
        react_engine.clear_history()
        console.print("[yellow]已清空历史，以全新会话开始[/yellow]")

    # ==================== 单次模式 ====================
    if args.query:
        if rag_engine.query_engine is None:
            console.print("❌ 知识库未初始化，请使用 --data 指定数据", style="red")
            sys.exit(1)
        console.print(f"🔍 问题: {args.query}\n", style="bold")
        with console.status("[bold green]检索知识库..."):
            result = rag_engine.query_with_sources(args.query)
        console.print("🤖 回答:", style="bold blue")
        if HAS_RICH:
            console.print(Panel(Markdown(result["answer"]), border_style="green"))
        else:
            print(result["answer"])
        last_rag_sources = result["sources"]
        if last_rag_sources:
            print_rag_sources(last_rag_sources)
        return

    if args.agent:
        console.print(f"🤖 Agent 任务: {args.agent}\n", style="bold cyan")
        try:
            answer = react_engine.chat(args.agent)
        except KeyboardInterrupt:
            console.print("\n[yellow]用户中断[/yellow]")
            react_engine.stop()
            return
        if HAS_RICH:
            if "```" in answer or "**" in answer or "#" in answer:
                console.print(Markdown(answer))
            else:
                console.print(Panel(answer, border_style="green", title="Agent", box=box.ROUNDED))
        else:
            print("\n" + "=" * 50)
            print(answer)
            print("=" * 50 + "\n")
        return

    if args.build_only:
        if rag_engine.query_engine is not None:
            stats = rag_engine.get_stats()
            console.print(f"\n✅ 索引构建完成！", style="bold green")
            print_knowledge_stats()
        else:
            console.print("❌ 索引构建失败", style="red")
        return

    # ==================== 交互式模式 ====================
    print_help()

    while True:
        try:
            user_input = get_input("\n❯ ")
        except (EOFError, KeyboardInterrupt):
            console.print("\n\n👋 再见！", style="bold green")
            break

        if not user_input:
            continue

        parsed = parse_command(user_input)
        mode = classify_mode(rag_engine.query_engine is not None, parsed)
        
        # 标志变量：是否显示命令推荐（默认显示，错误情况设为 False）
        should_show_recommendations = True

        # ---- 退出 ----
        if parsed.cmd_type == "quit":
            console.print("👋 再见！", style="bold green")
            break

        # ---- 帮助与教程 ----
        elif parsed.cmd_type == "help":
            print_help()
            record_command_execution("help")
        elif parsed.cmd_type == "tutorial":
            show_tutorial()
            record_command_execution("tutorial")
        elif parsed.cmd_type == "tools":
            print_tools()
            record_command_execution("tools")

        # ---- 知识库命令 ----
        elif parsed.cmd_type == "stats":
            print_knowledge_stats()
            record_command_execution("stats")
        elif parsed.cmd_type == "sources":
            print_rag_sources(last_rag_sources)
            record_command_execution("sources")
        elif parsed.cmd_type == "add":
            path = parsed.arg
            try:
                docs = load_documents(path)
                if docs:
                    rag_engine.add_documents(docs, [path])
                    console.print("✅ 文档已添加到知识库", style="green")
                    console.print("💡 提示: 可以使用 /generate-skills 将知识库转化为Skills", style="dim")
                    record_command_execution("add", path, "success")
                else:
                    console.print("⚠️  未找到可加载的文档", style="yellow")
                    record_command_execution("add", path, "no documents")
            except Exception as e:
                console.print(f"❌ 添加失败: {e}", style="red")
                record_command_execution("add", path, "failed", str(e))
        
        # ---- 知识库管理命令 ----
        elif parsed.cmd_type == "generate_skills":
            if not KNOWLEDGE_MANAGEMENT_AVAILABLE:
                console.print("❌ 知识库管理模块未安装", style="red")
                should_show_recommendations = False
            elif not rag_engine:
                console.print("❌ 知识库未初始化", style="yellow")
                should_show_recommendations = False
            else:
                try:
                    console.print("🔄 开始生成Skills...", style="cyan")
                    engine = KnowledgeToSkillsEngine()
                    results = engine.convert()
                    console.print(f"✅ 成功生成 {len(results)} 个Skills:", style="green")
                    for key, path in results.items():
                        console.print(f"  • {key}: {path}", style="dim")
                    record_command_execution("generate_skills")
                except Exception as e:
                    console.print(f"❌ 生成Skills失败: {e}", style="red")
                    record_command_execution("generate_skills", "", "failed", str(e))
        
        elif parsed.cmd_type == "snapshot_list":
            if not KNOWLEDGE_MANAGEMENT_AVAILABLE:
                console.print("❌ 知识库管理模块未安装", style="red")
                should_show_recommendations = False
            else:
                try:
                    manager = KnowledgeSnapshotManager()
                    snapshots = manager.list_snapshots()
                    if not snapshots:
                        console.print("📭 没有找到快照", style="yellow")
                    else:
                        console.print(f"📋 共有 {len(snapshots)} 个快照:", style="cyan")
                        for snap in snapshots:
                            console.print(f"\n  🆔 {snap['snapshot_id']}", style="bold")
                            console.print(f"  📅 {snap['timestamp']}", style="dim")
                            console.print(f"  📄 文档数: {snap['document_count']}", style="dim")
                            console.print(f"  🧩 Chunk数: {snap['total_chunks']}", style="dim")
                            console.print(f"  ⚡ 触发方式: {snap['trigger']}", style="dim")
                    record_command_execution("snapshot_list")
                except Exception as e:
                    console.print(f"❌ 获取快照列表失败: {e}", style="red")
                    record_command_execution("snapshot_list", "", "failed", str(e))
        
        elif parsed.cmd_type == "snapshot_create":
            if not KNOWLEDGE_MANAGEMENT_AVAILABLE:
                console.print("❌ 知识库管理模块未安装", style="red")
                should_show_recommendations = False
            elif not rag_engine:
                console.print("❌ 知识库未初始化", style="yellow")
                should_show_recommendations = False
            else:
                try:
                    manager = KnowledgeSnapshotManager()
                    snapshot = manager.create_snapshot(trigger="manual")
                    console.print(f"✅ 快照创建完成: {snapshot.snapshot_id}", style="green")
                    console.print(f"📅 时间: {snapshot.timestamp}", style="dim")
                    console.print(f"📄 文档数: {len(snapshot.documents)}", style="dim")
                    record_command_execution("snapshot_create")
                except Exception as e:
                    console.print(f"❌ 创建快照失败: {e}", style="red")
                    record_command_execution("snapshot_create", "", "failed", str(e))
        
        elif parsed.cmd_type == "snapshot_restore":
            if not KNOWLEDGE_MANAGEMENT_AVAILABLE:
                console.print("❌ 知识库管理模块未安装", style="red")
                should_show_recommendations = False
            else:
                snapshot_id = parsed.arg
                if not snapshot_id:
                    console.print("❌ 请指定快照ID: /snapshot-restore <id>", style="yellow")
                    should_show_recommendations = False
                else:
                    try:
                        manager = KnowledgeSnapshotManager()
                        snapshot = manager.load_snapshot(snapshot_id)
                        if not snapshot:
                            console.print(f"❌ 快照不存在: {snapshot_id}", style="red")
                            should_show_recommendations = False
                        else:
                            console.print(f"🔄 恢复快照: {snapshot_id}", style="cyan")
                            console.print(f"📄 文档数: {len(snapshot.documents)}", style="dim")
                            
                            # 生成恢复脚本
                            helper = RestoreHelper(manager)
                            script_file = helper.generate_restore_script(snapshot_id)
                            console.print(f"✅ 恢复脚本已生成: {script_file}", style="green")
                            console.print("💡 请运行该脚本来恢复知识库", style="yellow")
                            record_command_execution("snapshot_restore", snapshot_id)
                    except Exception as e:
                        console.print(f"❌ 恢复快照失败: {e}", style="red")
                        record_command_execution("snapshot_restore", snapshot_id, "failed", str(e))
        
        elif parsed.cmd_type == "knowledge_summary":
            if not KNOWLEDGE_MANAGEMENT_AVAILABLE:
                console.print("❌ 知识库管理模块未安装", style="red")
                should_show_recommendations = False
            elif not rag_engine:
                console.print("❌ 知识库未初始化", style="yellow")
                should_show_recommendations = False
            else:
                try:
                    engine = KnowledgeToSkillsEngine()
                    summary = engine.get_document_summary()
                    console.print(f"📊 知识库文档摘要:", style="cyan")
                    for doc in summary:
                        type_indicator = "🌐 通用" if doc['is_generic'] else "🏢 项目"
                        console.print(f"\n  📄 {doc['file_name']}", style="bold")
                        console.print(f"  📍 {doc['file_path']}", style="dim")
                        console.print(f"  🏷️ 主题: {', '.join(doc['topics'])}", style="dim")
                        console.print(f"  {type_indicator} (置信度: {doc['confidence']:.2f})", style="dim")
                        console.print(f"  🧩 Chunks: {doc['chunk_count']}", style="dim")
                    record_command_execution("knowledge_summary")
                except Exception as e:
                    console.print(f"❌ 获取知识库摘要失败: {e}", style="red")
                    record_command_execution("knowledge_summary", "", "failed", str(e))

        # ---- 文件管理命令 ----
        elif parsed.cmd_type == "file_list":
            try:
                from file_metadata import get_global_metadata_manager
                manager = get_global_metadata_manager()
                files = manager.list_files()

                if not files:
                    console.print("📭 知识库中没有文件", style="yellow")
                else:
                    console.print(f"📁 共有 {len(files)} 个文件:", style="cyan")
                    for file_meta in files:
                        console.print(f"\n  📄 {file_meta.file_path}", style="bold")
                        console.print(f"  📊 大小: {manager._format_size(file_meta.file_size)}", style="dim")
                        console.print(f"  🏷️  类型: {file_meta.persistence_type}", style="dim")
                        console.print(f"  📅 上传: {file_meta.upload_time[:19]}", style="dim")
                        if file_meta.tags:
                            console.print(f"  🏷️  标签: {', '.join(file_meta.tags)}", style="dim")
                record_command_execution("file_list")
            except Exception as e:
                console.print(f"❌ 列出文件失败: {e}", style="red")
                record_command_execution("file_list", "", "failed", str(e))

        elif parsed.cmd_type == "file_info":
            file_path = parsed.arg
            if not file_path:
                console.print("❌ 请指定文件路径: /file-info <path>", style="yellow")
                should_show_recommendations = False
            else:
                try:
                    from file_metadata import get_global_metadata_manager
                    manager = get_global_metadata_manager()
                    file_meta = manager.get_file_metadata(file_path)

                    if not file_meta:
                        console.print(f"❌ 文件不在知识库中: {file_path}", style="yellow")
                        should_show_recommendations = False
                    else:
                        console.print(f"📄 文件信息: {file_path}", style="cyan")
                        console.print(f"📊 大小: {manager._format_size(file_meta.file_size)}", style="dim")
                        console.print(f"🏷️  类型: {file_meta.persistence_type}", style="dim")
                        console.print(f"📅 上传: {file_meta.upload_time}", style="dim")
                        console.print(f"🔢 访问次数: {file_meta.access_count}", style="dim")
                        console.print(f"📄 文档数: {file_meta.document_count}", style="dim")
                        console.print(f"🧩 Chunk数: {file_meta.chunk_count}", style="dim")
                        if file_meta.last_access:
                            console.print(f"🕐 最后访问: {file_meta.last_access[:19]}", style="dim")
                        if file_meta.tags:
                            console.print(f"🏷️  标签: {', '.join(file_meta.tags)}", style="dim")
                        record_command_execution("file_info", file_path)
                except Exception as e:
                    console.print(f"❌ 获取文件信息失败: {e}", style="red")
                    record_command_execution("file_info", file_path, "failed", str(e))

        elif parsed.cmd_type == "file_stats":
            try:
                from file_metadata import get_global_metadata_manager
                from file_validator import get_global_validator

                metadata_manager = get_global_metadata_manager()
                validator = get_global_validator()

                stats = metadata_manager.get_stats()
                validator_stats = validator.get_stats()

                console.print("📊 文件统计信息:", style="cyan")
                console.print(f"📁 总文件数: {stats['total_files']}", style="bold")
                console.print(f"💾 总大小: {stats['total_size_formatted']}", style="dim")
                console.print(f"📌 永久文件: {stats['permanent_count']}", style="dim")
                console.print(f"⏰ 临时文件: {stats['temporary_count']}", style="dim")
                console.print(f"🎯 会话文件: {stats['session_count']}", style="dim")
                console.print(f"🧹 待清理: {stats['cleanup_count']}", style="dim")
                console.print(f"🔗 已知文件: {validator_stats['known_file_count']}", style="dim")
                console.print(f"📈 利用率: {validator_stats['utilization_percent']:.1f}%", style="dim")
                record_command_execution("file_stats")
            except Exception as e:
                console.print(f"❌ 获取统计信息失败: {e}", style="red")
                record_command_execution("file_stats", "", "failed", str(e))

        elif parsed.cmd_type == "file_cleanup":
            try:
                from file_metadata import get_global_metadata_manager
                manager = get_global_metadata_manager()

                files_to_cleanup = manager.get_files_to_cleanup()
                if not files_to_cleanup:
                    console.print("✅ 没有需要清理的文件", style="green")
                else:
                    console.print(f"🧹 发现 {len(files_to_cleanup)} 个需要清理的文件", style="yellow")
                    for file_meta in files_to_cleanup:
                        console.print(f"  - {file_meta.file_path} ({file_meta.persistence_type})", style="dim")

                    # 执行清理
                    cleaned = manager.cleanup_files()
                    console.print(f"✅ 已清理 {len(cleaned)} 个文件", style="green")
                record_command_execution("file_cleanup")
            except Exception as e:
                console.print(f"❌ 清理文件失败: {e}", style="red")
                record_command_execution("file_cleanup", "", "failed", str(e))

        elif parsed.cmd_type == "file_deduplicate":
            try:
                from file_metadata import get_global_metadata_manager
                from file_validator import get_global_validator

                metadata_manager = get_global_metadata_manager()
                validator = get_global_validator()

                console.print("🔄 正在检查重复文件...", style="cyan")
                files = metadata_manager.list_files()

                duplicates = []
                seen_hashes = {}

                for file_meta in files:
                    if file_meta.file_hash:
                        if file_meta.file_hash in seen_hashes:
                            duplicates.append(file_meta)
                        else:
                            seen_hashes[file_meta.file_hash] = file_meta

                if not duplicates:
                    console.print("✅ 没有发现重复文件", style="green")
                    record_command_execution("file_deduplicate", "", "no_duplicates")
                else:
                    console.print(f"⚠️  发现 {len(duplicates)} 个重复文件:", style="yellow")
                    for file_meta in duplicates:
                        console.print(f"  - {file_meta.file_path}", style="dim")

                    # 询问是否删除重复文件
                    try:
                        answer = console.input("是否删除重复文件? (y/n): ").strip().lower()
                        if answer in ("y", "yes", "是", "确认"):
                            for file_meta in duplicates:
                                metadata_manager.remove_file(file_meta.file_path)
                                console.print(f"✅ 已删除: {file_meta.file_path}", style="green")
                            console.print(f"✅ 共删除 {len(duplicates)} 个重复文件", style="green")
                            record_command_execution("file_deduplicate", f"删除了{len(duplicates)}个重复文件", "success")
                        else:
                            console.print("❌ 取消删除", style="yellow")
                            record_command_execution("file_deduplicate", "", "cancelled")
                    except (EOFError, KeyboardInterrupt):
                        console.print("\n❌ 取消操作", style="yellow")
                        record_command_execution("file_deduplicate", "", "cancelled")

            except Exception as e:
                console.print(f"❌ 去重失败: {e}", style="red")
                record_command_execution("file_deduplicate", "", "failed", str(e))

        # ---- 会话管理命令 ----
        elif parsed.cmd_type == "session_new":
            try:
                from session_manager import SessionManager
                from config import SESSION_STORAGE_PATH

                manager = SessionManager(str(SESSION_STORAGE_PATH))
                title = parsed.arg if parsed.arg else None
                session = manager.create_session(title=title)

                console.print(f"✅ 新会话已创建: {session.session_id}", style="green")
                console.print(f"📋 标题: {session.title}", style="dim")
                console.print(f"📅 创建时间: {session.created_at.strftime('%Y-%m-%d %H:%M:%S')}", style="dim")
                record_command_execution("session_new", session.title if session.title else "")
            except Exception as e:
                console.print(f"❌ 创建会话失败: {e}", style="red")
                record_command_execution("session_new", "", "failed", str(e))

        elif parsed.cmd_type == "session_list":
            try:
                from session_manager import SessionManager
                from config import SESSION_STORAGE_PATH

                manager = SessionManager(str(SESSION_STORAGE_PATH))
                sessions = manager.list_sessions()

                if not sessions:
                    console.print("📭 没有会话", style="yellow")
                else:
                    console.print(f"💬 共有 {len(sessions)} 个会话:", style="cyan")
                    current_session = manager.get_current_session()

                    for session in sessions:
                        is_current = "🔸" if session.session_id == (current_session.session_id if current_session else None) else " "
                        status_emoji = "🟢" if session.status.value == "active" else "📦" if session.status.value == "archived" else "🗑️"
                        console.print(f"{is_current} {status_emoji} {session.session_id[:8]}... - {session.title}", style="bold" if session.session_id == (current_session.session_id if current_session else None) else "dim")
                        console.print(f"    📅 {session.updated_at.strftime('%Y-%m-%d %H:%M')}", style="dim")
                        console.print(f"    💬 {len(session.messages)} 条消息", style="dim")
                record_command_execution("session_list")
            except Exception as e:
                console.print(f"❌ 列出会话失败: {e}", style="red")
                record_command_execution("session_list", "", "failed", str(e))

        elif parsed.cmd_type == "session_switch":
            session_id = parsed.arg
            if not session_id:
                console.print("❌ 请指定会话ID: /session-switch <id>", style="yellow")
                should_show_recommendations = False
            else:
                try:
                    from session_manager import SessionManager
                    from config import SESSION_STORAGE_PATH

                    manager = SessionManager(str(SESSION_STORAGE_PATH))
                    success = manager.switch_session(session_id)

                    if success:
                        session = manager.get_current_session()
                        console.print(f"✅ 已切换到会话: {session.title}", style="green")
                        console.print(f"💬 该会话有 {len(session.messages)} 条消息", style="dim")
                        record_command_execution("session_switch", session_id)
                    else:
                        console.print(f"❌ 会话不存在或已删除: {session_id}", style="yellow")
                        should_show_recommendations = False
                except Exception as e:
                    console.print(f"❌ 切换会话失败: {e}", style="red")
                    record_command_execution("session_switch", session_id, "failed", str(e))

        elif parsed.cmd_type == "session_current":
            try:
                from session_manager import SessionManager
                from config import SESSION_STORAGE_PATH

                manager = SessionManager(str(SESSION_STORAGE_PATH))
                current = manager.get_current_session()

                if not current:
                    console.print("📭 没有当前会话，请使用 /session-new 创建新会话", style="yellow")
                    should_show_recommendations = False
                else:
                    console.print(f"💬 当前会话信息:", style="cyan")
                    console.print(f"🆔 ID: {current.session_id}", style="bold")
                    console.print(f"📋 标题: {current.title}", style="dim")
                    console.print(f"📊 状态: {current.status.value}", style="dim")
                    console.print(f"📅 创建: {current.created_at.strftime('%Y-%m-%d %H:%M:%S')}", style="dim")
                    console.print(f"🕐 更新: {current.updated_at.strftime('%Y-%m-%d %H:%M:%S')}", style="dim")
                    console.print(f"💬 消息数: {len(current.messages)}", style="dim")
                    if current.tags:
                        console.print(f"🏷️  标签: {', '.join(current.tags)}", style="dim")
                    record_command_execution("session_current")
            except Exception as e:
                console.print(f"❌ 获取当前会话失败: {e}", style="red")
                record_command_execution("session_current", "", "failed", str(e))

        elif parsed.cmd_type == "session_info":
            session_id = parsed.arg
            if not session_id:
                console.print("❌ 请指定会话ID: /session-info <id>", style="yellow")
                should_show_recommendations = False

            try:
                from session_manager import SessionManager
                from config import SESSION_STORAGE_PATH

                manager = SessionManager(str(SESSION_STORAGE_PATH))
                sessions = manager.list_sessions()

                # 查找匹配的会话
                matching_sessions = [s for s in sessions if session_id in s.session_id]

                if not matching_sessions:
                    console.print(f"❌ 未找到会话: {session_id}", style="yellow")
                    should_show_recommendations = False
                else:
                    session = matching_sessions[0]
                    console.print(f"💬 会话详细信息:", style="cyan")
                    console.print(f"🆔 ID: {session.session_id}", style="bold")
                    console.print(f"📋 标题: {session.title}", style="dim")
                    console.print(f"📊 状态: {session.status.value}", style="dim")
                    console.print(f"📅 创建: {session.created_at.strftime('%Y-%m-%d %H:%M:%S')}", style="dim")
                    console.print(f"🕐 更新: {session.updated_at.strftime('%Y-%m-%d %H:%M:%S')}", style="dim")
                    console.print(f"💬 消息数: {len(session.messages)}", style="dim")
                    if session.tags:
                        console.print(f"🏷️  标签: {', '.join(session.tags)}", style="dim")
                    if session.metadata:
                        console.print(f"📝 元数据: {session.metadata}", style="dim")
                    record_command_execution("session_info", session_id)
            except Exception as e:
                console.print(f"❌ 获取会话信息失败: {e}", style="red")
                record_command_execution("session_info", session_id, "failed", str(e))

        elif parsed.cmd_type == "session_search":
            query = parsed.arg
            if not query:
                console.print("❌ 请指定搜索查询: /session-search <query>", style="yellow")
                should_show_recommendations = False

            try:
                from session_manager import SessionManager
                from config import SESSION_STORAGE_PATH

                manager = SessionManager(str(SESSION_STORAGE_PATH))
                results = manager.search_sessions(query)

                if not results:
                    console.print(f"🔍 未找到包含 '{query}' 的会话", style="yellow")
                    should_show_recommendations = False
                else:
                    console.print(f"🔍 找到 {len(results)} 个包含 '{query}' 的会话:", style="cyan")
                    for session in results:
                        console.print(f"  • {session.title} ({session.session_id[:8]}...)", style="dim")
                        console.print(f"    💬 {len(session.messages)} 条消息", style="dim")
                    record_command_execution("session_search", query)
            except Exception as e:
                console.print(f"❌ 搜索会话失败: {e}", style="red")
                record_command_execution("session_search", query, "failed", str(e))

        elif parsed.cmd_type == "session_compress":
            try:
                from session_manager import SessionManager
                from config import SESSION_STORAGE_PATH
                from history_compressor import HistoryCompressor

                manager = SessionManager(str(SESSION_STORAGE_PATH))
                current = manager.get_current_session()

                if not current:
                    console.print("📭 没有当前会话", style="yellow")
                    should_show_recommendations = False
                else:
                    console.print(f"🔄 正在压缩会话历史...", style="cyan")
                    compressor = HistoryCompressor()
                    original_count = len(current.messages)
                    compressed_messages = compressor.compress_history(current.messages)

                    # 更新会话消息
                    current.messages = compressed_messages
                    manager.save_session(current)

                    console.print(f"✅ 压缩完成: {original_count} → {len(compressed_messages)} 条消息", style="green")
                    console.print(f"📊 压缩率: {(1 - len(compressed_messages)/original_count)*100:.1f}%", style="dim")
                    record_command_execution("session_compress", f"{original_count}→{len(compressed_messages)}")
            except Exception as e:
                console.print(f"❌ 压缩会话失败: {e}", style="red")
                record_command_execution("session_compress", "", "failed", str(e))

        elif parsed.cmd_type == "session_delete":
            session_id = parsed.arg
            if not session_id:
                console.print("❌ 请指定会话ID: /session-delete <id>", style="yellow")
                should_show_recommendations = False

            try:
                from session_manager import SessionManager
                from config import SESSION_STORAGE_PATH

                manager = SessionManager(str(SESSION_STORAGE_PATH))
                current = manager.get_current_session()

                # 防止删除当前会话
                if current and session_id in current.session_id:
                    console.print("⚠️  不能删除当前会话，请先切换到其他会话", style="yellow")
                    should_show_recommendations = False

                success = manager.delete_session(session_id)

                if success:
                    console.print(f"✅ 会话已删除: {session_id}", style="green")
                    record_command_execution("session_delete", session_id)
                else:
                    console.print(f"❌ 会话不存在: {session_id}", style="yellow")
                    should_show_recommendations = False
            except Exception as e:
                console.print(f"❌ 删除会话失败: {e}", style="red")
                record_command_execution("session_delete", session_id, "failed", str(e))

        elif parsed.cmd_type == "session_archive":
            session_id = parsed.arg
            if not session_id:
                console.print("❌ 请指定会话ID: /session-archive <id>", style="yellow")
                should_show_recommendations = False

            try:
                from session_manager import SessionManager
                from config import SESSION_STORAGE_PATH

                manager = SessionManager(str(SESSION_STORAGE_PATH))
                success = manager.archive_session(session_id)

                if success:
                    console.print(f"📦 会话已归档: {session_id}", style="green")
                    record_command_execution("session_archive", session_id)
                else:
                    console.print(f"❌ 会话不存在: {session_id}", style="yellow")
                    should_show_recommendations = False
            except Exception as e:
                console.print(f"❌ 归档会话失败: {e}", style="red")
                record_command_execution("session_archive", session_id, "failed", str(e))

        # ---- 网络搜索命令 ----
        elif parsed.cmd_type == "web_search":
            query = parsed.arg.strip()
            if not query:
                console.print("❌ 请提供搜索查询: /web-search <query>", style="yellow")
                should_show_recommendations = False

            try:
                console.print(f"🔍 正在搜索: {query}", style="cyan")
                result = registry.execute("web_search", {"query": query})
                
                if result.startswith("[错误]") or result.startswith("[提示]"):
                    console.print(result, style="yellow")
                    should_show_recommendations = False
                else:
                    console.print(result, style="green")
                    record_command_execution("web_search", query)
            except Exception as e:
                console.print(f"❌ 搜索失败: {e}", style="red")
                record_command_execution("web_search", query, "failed", str(e))

        elif parsed.cmd_type == "web_cache":
            arg = parsed.arg.strip()
            if not arg or arg == "status":
                # 显示缓存状态
                try:
                    result = registry.execute("web_cache_status", {})
                    console.print(result, style="cyan")
                    record_command_execution("web_cache", "status")
                except Exception as e:
                    console.print(f"❌ 获取缓存状态失败: {e}", style="red")
                    record_command_execution("web_cache", "status", "failed", str(e))
            elif arg == "clear":
                # 清空缓存
                try:
                    result = registry.execute("web_cache_clear", {})
                    console.print(result, style="green")
                    record_command_execution("web_cache", "clear")
                except Exception as e:
                    console.print(f"❌ 清空缓存失败: {e}", style="red")
                    record_command_execution("web_cache", "clear", "failed", str(e))
            else:
                console.print("❌ 未知命令，使用: /web-cache [status|clear]", style="yellow")
                should_show_recommendations = False

        elif parsed.cmd_type == "web_extract":
            url = parsed.arg.strip()
            if not url:
                console.print("❌ 请提供URL: /web-extract <url>", style="yellow")
                should_show_recommendations = False

            try:
                console.print(f"📄 正在提取内容: {url}", style="cyan")
                result = registry.execute("web_content_extract", {"url": url})
                
                if result.startswith("[错误]"):
                    console.print(result, style="red")
                    should_show_recommendations = False
                else:
                    console.print(result, style="green")
                    record_command_execution("web_extract", url)
            except Exception as e:
                console.print(f"❌ 内容提取失败: {e}", style="red")
                record_command_execution("web_extract", url, "failed", str(e))

        # ---- 代码分析命令 ----
        elif parsed.cmd_type == "code_ast":
            pattern = parsed.arg.strip()
            if not pattern:
                console.print("❌ 请提供搜索模式: /code-ast <pattern>", style="yellow")
                should_show_recommendations = False

            try:
                console.print(f"🔍 正在搜索 AST: {pattern}", style="cyan")
                result = registry.execute("ast_search", {"pattern": pattern, "path": "."})
                
                if result.startswith("[错误]"):
                    console.print(result, style="red")
                    should_show_recommendations = False
                else:
                    console.print(result, style="green")
                    record_command_execution("code_ast", pattern)
            except Exception as e:
                console.print(f"❌ AST 搜索失败: {e}", style="red")
                record_command_execution("code_ast", pattern, "failed", str(e))

        elif parsed.cmd_type == "code_quality":
            path = parsed.arg.strip() if parsed.arg.strip() else "."
            try:
                console.print(f"🔍 正在分析代码质量: {path}", style="cyan")
                result = registry.execute("code_quality_check", {"path": path})
                
                if result.startswith("[错误]"):
                    console.print(result, style="red")
                    should_show_recommendations = False
                else:
                    console.print(result, style="green")
                    record_command_execution("code_quality", path)
            except Exception as e:
                console.print(f"❌ 代码质量检查失败: {e}", style="red")
                record_command_execution("code_quality", path, "failed", str(e))

        # ---- 知识图谱命令 ----
        elif parsed.cmd_type == "graph_query":
            query = parsed.arg.strip()
            if not query:
                console.print("❌ 请提供查询内容: /graph-query <query>", style="yellow")
                should_show_recommendations = False

            try:
                console.print(f"🔍 正在查询知识图谱: {query}", style="cyan")
                result = registry.execute("knowledge_graph_query", {"query": query})
                
                if result.startswith("[错误]"):
                    console.print(result, style="red")
                    should_show_recommendations = False
                else:
                    console.print(result, style="green")
                    record_command_execution("graph_query", query)
            except Exception as e:
                console.print(f"❌ 知识图谱查询失败: {e}", style="red")
                record_command_execution("graph_query", query, "failed", str(e))

        elif parsed.cmd_type == "graph_build":
            # 图谱构建需要文本内容，这里简化处理
            console.print("📝 知识图谱构建需要文本内容", style="cyan")
            console.print("请使用 Agent 模式调用 knowledge_graph_build 工具", style="yellow")
            should_show_recommendations = False

        # 数据库管理命令
        elif parsed.cmd_type == "db_connect":
            args = parsed.arg.strip().split() if parsed.arg.strip() else []
            if len(args) < 2:
                console.print("❌ 请提供数据库类型和路径: /db-connect <type> <database>", style="yellow")
                should_show_recommendations = False
            
            db_type, database = args[0], args[1]
            try:
                console.print(f"🔗 正在连接数据库: {db_type} @ {database}", style="cyan")
                result = registry.execute("database_connect", {"db_type": db_type, "database": database})
                
                if result.startswith("[错误]"):
                    console.print(result, style="red")
                    should_show_recommendations = False
                else:
                    console.print(result, style="green")
                    record_command_execution("db_connect", f"{db_type} {database}")
            except Exception as e:
                console.print(f"❌ 数据库连接失败: {e}", style="red")
                record_command_execution("db_connect", f"{db_type} {database}", "failed", str(e))

        elif parsed.cmd_type == "db_query":
            sql = parsed.arg.strip()
            if not sql:
                console.print("❌ 请提供SQL查询语句: /db-query <sql>", style="yellow")
                should_show_recommendations = False

            try:
                console.print(f"🔍 正在执行SQL查询", style="cyan")
                result = registry.execute("database_query", {"sql": sql})
                
                if result.startswith("[错误]"):
                    console.print(result, style="red")
                    should_show_recommendations = False
                else:
                    console.print(result, style="green")
                    record_command_execution("db_query", sql[:50])
            except Exception as e:
                console.print(f"❌ SQL查询失败: {e}", style="red")
                record_command_execution("db_query", sql[:50], "failed", str(e))

        elif parsed.cmd_type == "db_execute":
            sql = parsed.arg.strip()
            if not sql:
                console.print("❌ 请提供SQL语句: /db-execute <sql>", style="yellow")
                should_show_recommendations = False

            try:
                console.print(f"⚡ 正在执行SQL语句", style="cyan")
                result = registry.execute("database_execute", {"sql": sql})
                
                if result.startswith("[错误]"):
                    console.print(result, style="red")
                    should_show_recommendations = False
                else:
                    console.print(result, style="green")
                    record_command_execution("db_execute", sql[:50])
            except Exception as e:
                console.print(f"❌ SQL执行失败: {e}", style="red")
                record_command_execution("db_execute", sql[:50], "failed", str(e))

        elif parsed.cmd_type == "db_create_table":
            args = parsed.arg.strip().split() if parsed.arg.strip() else []
            if len(args) < 1:
                console.print("❌ 请提供表名: /db-create-table <table> <columns_json>", style="yellow")
                should_show_recommendations = False
            
            table = args[0]
            columns_json = " ".join(args[1:]) if len(args) > 1 else "{}"
            
            try:
                import json
                columns = json.loads(columns_json)
            except json.JSONDecodeError:
                console.print("❌ 列定义必须是有效的JSON格式", style="yellow")
                should_show_recommendations = False

            try:
                console.print(f"🔨 正在创建表: {table}", style="cyan")
                result = registry.execute("database_create_table", {"table": table, "columns": columns})
                
                if result.startswith("[错误]"):
                    console.print(result, style="red")
                    should_show_recommendations = False
                else:
                    console.print(result, style="green")
                    record_command_execution("db_create_table", table)
            except Exception as e:
                console.print(f"❌ 创建表失败: {e}", style="red")
                record_command_execution("db_create_table", table, "failed", str(e))

        elif parsed.cmd_type == "db_insert":
            args = parsed.arg.strip().split() if parsed.arg.strip() else []
            if len(args) < 1:
                console.print("❌ 请提供表名和数据: /db-insert <table> <data_json>", style="yellow")
                should_show_recommendations = False
            
            table = args[0]
            data_json = " ".join(args[1:]) if len(args) > 1 else "{}"
            
            try:
                import json
                data = json.loads(data_json)
            except json.JSONDecodeError:
                console.print("❌ 数据必须是有效的JSON格式", style="yellow")
                should_show_recommendations = False

            try:
                console.print(f"➕ 正在插入数据到表: {table}", style="cyan")
                result = registry.execute("database_insert", {"table": table, "data": data})
                
                if result.startswith("[错误]"):
                    console.print(result, style="red")
                    should_show_recommendations = False
                else:
                    console.print(result, style="green")
                    record_command_execution("db_insert", table)
            except Exception as e:
                console.print(f"❌ 插入数据失败: {e}", style="red")
                record_command_execution("db_insert", table, "failed", str(e))

        elif parsed.cmd_type == "db_schema":
            table = parsed.arg.strip()
            if not table:
                console.print("❌ 请提供表名: /db-schema <table>", style="yellow")
                should_show_recommendations = False

            try:
                console.print(f"🔍 正在获取表结构: {table}", style="cyan")
                result = registry.execute("database_get_schema", {"table": table})
                
                if result.startswith("[错误]"):
                    console.print(result, style="red")
                    should_show_recommendations = False
                else:
                    console.print(result, style="green")
                    record_command_execution("db_schema", table)
            except Exception as e:
                console.print(f"❌ 获取表结构失败: {e}", style="red")
                record_command_execution("db_schema", table, "failed", str(e))

        # ---- Agent 历史与上下文 ----
        elif parsed.cmd_type == "clear":
            console.clear()
            print_banner()
            record_command_execution("clear")
            
        elif parsed.cmd_type == "history":
            msgs = react_engine.history.get_messages()
            if len(msgs) <= 1:
                console.print("[dim]暂无对话历史[/dim]")
                should_show_recommendations = False
            else:
                lines = []
                for i, m in enumerate(msgs):
                    role = m.get("role", "?")
                    content = m.get("content", "")[:80].replace("\n", " ")
                    lines.append(f"{i}. [{role}] {content}...")
                if HAS_RICH:
                    console.print(Panel("\n".join(lines), title="历史记录", border_style="dim"))
                else:
                    print("\n".join(lines))
                record_command_execution("history")
        elif parsed.cmd_type == "summary":
            summary = react_engine.get_step_summary()
            if HAS_RICH:
                console.print(Panel(summary, title="执行摘要", border_style="blue"))
            else:
                print(summary)
            record_command_execution("summary")
        elif parsed.cmd_type == "reset":
            react_engine.clear_history()
            console.print("🔄 Agent 对话上下文已重置", style="green")
            record_command_execution("reset")

        # ---- 文件操作 ----
        elif parsed.cmd_type == "file":
            path = parsed.arg
            result = registry.execute("read_file", {"path": path}, auto_confirm=True)
            if HAS_RICH:
                console.print(Panel(result, title=f"文件: {path}", border_style="blue"))
            else:
                print(result)
                record_command_execution("read", path)
        elif parsed.cmd_type == "write":
            path = parsed.arg
            console.print("[yellow]进入写入模式，输入内容（空行结束）:[/yellow]")
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
            console.print(result)
            record_command_execution("write", path)
        elif parsed.cmd_type == "exec":
            cmd = parsed.arg
            safety = CommandSafetyChecker.analyze(cmd)
            if HAS_RICH:
                color = {"low": "green", "medium": "yellow", "high": "red", "critical": "red"}.get(safety['risk_level'], "white")
                console.print(f"[dim]命令: {cmd}[/dim]")
                console.print(f"风险等级: [{color}]{safety['risk_level']}[/{color}]")
            else:
                print(f"命令: {cmd}")
                print(f"风险等级: {safety['risk_level']}")

            if safety["is_dangerous"]:
                console.print("[red]该命令被安全系统拦截，拒绝执行。[/red]")
                should_show_recommendations = False
            elif safety["needs_confirm"] and not Config.AUTO_CONFIRM:
                try:
                    ans = console.input("确认执行? (y/n): ").strip().lower()
                    if ans not in ("y", "yes", "是"):
                        console.print("[dim]已取消[/dim]")
                        should_show_recommendations = False
                    else:
                        result = registry.execute("execute_command", {"command": cmd}, auto_confirm=True)
                        if HAS_RICH:
                            console.print(Panel(result, title="命令输出", border_style="magenta"))
                        else:
                            print(result)
                        record_command_execution("exec", cmd)
                except (EOFError, KeyboardInterrupt):
                    print("已取消")
                    should_show_recommendations = False
            else:
                result = registry.execute("execute_command", {"command": cmd}, auto_confirm=True)
                if HAS_RICH:
                    console.print(Panel(result, title="命令输出", border_style="magenta"))
                else:
                    print(result)
                record_command_execution("exec", cmd)

        # ---- 目录操作 ----
        elif parsed.cmd_type == "pwd":
            print(os.getcwd())
            record_command_execution("pwd")
        elif parsed.cmd_type == "cd":
            path = parsed.arg
            try:
                os.chdir(path)
                new_dir = os.getcwd()
                console.print(f"[green]已切换到: {new_dir}[/green]")
                record_command_execution("cd", path)
            except FileNotFoundError:
                console.print(f"[red]目录不存在: {path}[/red]")
                should_show_recommendations = False
            except PermissionError:
                console.print(f"[red]权限不足: {path}[/red]")
                should_show_recommendations = False
            except Exception as e:
                console.print(f"[red]切换失败: {e}[/red]")
                should_show_recommendations = False
        elif parsed.cmd_type == "model":
            console.print(f"[green]模型: {react_engine.model}[/green]")
            console.print(f"[green]Ollama: {react_engine.host}[/green]")
            console.print(f"[green]自动确认: {Config.AUTO_CONFIRM}[/green]")
            record_command_execution("model")

        # ---- 模式分发 ----
        elif parsed.cmd_type == "ask":
            question = parsed.arg
            # 保存用户原始问题，用于命令记录（避免把网络搜索结果正文塞进历史）
            original_question = parsed.arg
            kb_initialized = rag_engine.query_engine is not None
            if not kb_initialized:
                console.print("⚠️  知识库未初始化，将根据网络搜索/模型直接回答", style="yellow")
            
            # 检测用户是否提供了文件路径（支持图片、PDF、MD、TXT等常见文档格式）
            import re
            file_pattern = r'/Users/[^\s\)]+\.(png|jpg|jpeg|PNG|JPG|JPEG|pdf|PDF|md|MD|txt|TXT)'
            file_path_match = re.search(file_pattern, question)
            
            if file_path_match:
                # 提取文件路径
                file_path = file_path_match.group()
                console.print(f"📄 检测到文件路径: {file_path}", style="yellow")
                console.print("🔄 正在添加到知识库...", style="yellow")
                
                try:
                    # 先添加文件到知识库
                    from document_loader import load_documents
                    documents = load_documents(file_path)
                    if documents:
                        rag_engine.add_documents(documents, [file_path])
                        if Config.SHOW_PROGRESS:
                            console.print(f"✅ 已加载 {len(documents)} 个文档", style="green")
                            total_chars = sum(len(doc.text) for doc in documents)
                            console.print(f"✅ 总字符数: {total_chars}", style="dim")
                        else:
                            console.print("✅ 文件已添加到知识库", style="green")
                        # 更新问题，移除文件路径部分，保持语义完整性
                        question = re.sub(re.escape(file_path), '', question)
                        # 清理多余空格和标点
                        question = re.sub(r'\s+', ' ', question).strip()
                        question = question.rstrip('，。,.')
                        # 如果问题太模糊，添加更具体的查询指导
                        if not question or question == "/ask" or question in ["请帮我检查", "请帮我分析", "分析", "检查", "看一下", "这张图片里面有什么"]:
                            question = f"刚刚添加的文件中包含什么内容？文件名是 {Path(file_path).name}"
                            print(f"💡 使用精确查询: {question}")
                        else:
                            # 添加文件名到查询中以提高检索精度
                            filename = Path(file_path).name
                            if filename not in question:
                                question = f"{filename} {question}"
                        console.print(f"❓ 查询: {question}", style="cyan")
                    else:
                        console.print("⚠️ 无法加载文件，直接查询现有知识库", style="yellow")
                except Exception as e:
                    console.print(f"⚠️ 添加文件失败，直接查询现有知识库: {e}", style="yellow")
            
            # 检测是否需要网络搜索（最新信息、实时数据等）
            web_search_keywords = ["最新", "当前", "版本", "今天", "现在", "实时", "发布", "发布时间", "latest", "current", "version", "release"]
            needs_web_search = any(keyword in question.lower() for keyword in web_search_keywords)
            
            web_search_result = ""
            if needs_web_search:
                try:
                    console.print("🌐 检测到需要最新信息，正在网络搜索...", style="cyan")
                    from agent_tools import web_search
                    
                    # 改进搜索查询：从用户问题中提取关键搜索词
                    search_query = question
                    
                    # 移除中文常见查询前缀
                    prefixes_to_remove = ["帮我", "请帮我", "能否帮我", "可以帮我", "帮我查询", "请帮我查询", 
                                         "从网络上查询", "从网络查询", "网上查", "网络查", "查询一下", "查一下",
                                         "告诉我", "请问", "我想知道", "什么是", "什么是"]
                    for prefix in prefixes_to_remove:
                        if search_query.startswith(prefix):
                            search_query = search_query[len(prefix):].strip()
                    
                    # 移除常见的查询后缀
                    suffixes_to_remove = ["是多少", "是什么", "吗", "呢", "？", "?", "。", ".", "！", "!"]
                    for suffix in suffixes_to_remove:
                        if search_query.endswith(suffix):
                            search_query = search_query[:-len(suffix)].strip()
                    
                    # 如果清理后的查询太短，使用原标题
                    if len(search_query) < 3:
                        search_query = question
                    
                    # 尝试中英文查询转换
                    search_queries = [search_query]
                    
                    # 如果查询主要是中文，尝试添加英文翻译
                    if any('\u4e00' <= char <= '\u9fff' for char in search_query):
                        # 更智能的关键词翻译和提取
                        translations = {
                            "最新": "latest",
                            "版本": "version",
                            "当前": "current",
                            "发布": "release",
                            "下载": "download",
                            "安装": "install"
                        }
                        
                        # 提取英文技术术语
                        tech_terms = []
                        for term in ["JDK", "Java", "Python", "React", "Node", "JavaScript", "TypeScript", "Vue", "Angular"]:
                            if term in search_query:
                                tech_terms.append(term)
                        
                        # 构建英文查询
                        if tech_terms:
                            # 对于版本查询，使用更精确的搜索词
                            if "版本" in search_query or "version" in search_query.lower():
                                if "JDK" in tech_terms or "Java" in tech_terms:
                                    search_queries.insert(0, "Java SE latest version")  # 更精确的查询
                                    search_queries.insert(1, "Java downloads Oracle")  # 备用查询
                                elif "Python" in tech_terms:
                                    search_queries.insert(0, "Python latest version download")
                                    search_queries.insert(1, "Python.org downloads")
                                else:
                                    # 其他技术术语
                                    english_query = " ".join(tech_terms)
                                    for chinese, english in translations.items():
                                        if chinese in search_query:
                                            english_query += f" {english}"
                                    search_queries.insert(0, english_query)
                            else:
                                # 非版本查询
                                english_query = " ".join(tech_terms)
                                for chinese, english in translations.items():
                                    if chinese in search_query:
                                        english_query += f" {english}"
                                search_queries.insert(0, english_query)
                        else:
                            # 没有技术术语，尝试简单翻译
                            english_query = search_query
                            for chinese, english in translations.items():
                                english_query = english_query.replace(chinese, english)
                            
                            if english_query != search_query and any('\u4e00' <= char <= '\u9fff' for char in english_query):
                                # 如果翻译后仍有中文，直接使用技术术语搜索
                                if any(term in search_query for term in ["JDK", "Java"]):
                                    search_queries.insert(0, "Java SE latest version")
                                elif any(term in search_query for term in ["Python"]):
                                    search_queries.insert(0, "Python latest version")
                                else:
                                    search_queries.insert(0, english_query)
                    
                    console.print(f"🔍 搜索查询: {search_queries[0]}", style="dim")
                    
                    # 尝试多个查询，直到有一个成功
                    successful_query = None
                    for query in search_queries:
                        web_search_result = web_search(query, max_results=5, use_cache=False)
                        if web_search_result and not web_search_result.startswith("[错误]") and not web_search_result.startswith("[提示]"):
                            console.print("✅ 网络搜索完成", style="green")
                            successful_query = query
                            break
                        else:
                            console.print(f"⚠️ 查询 '{query}' 未返回结果，尝试下一个...", style="dim")
                    
                    if web_search_result and not web_search_result.startswith("[错误]") and not web_search_result.startswith("[提示]"):
                        # 对于版本查询，尝试提取官方下载页面的具体版本信息
                        if "版本" in search_query or "version" in search_query.lower():
                            try:
                                from agent_tools import web_content_extract
                                # 尝试从搜索结果中提取官方下载页面的内容
                                import re
                                # 查找Oracle或Python.org的下载页面
                                official_urls = []
                                for line in web_search_result.split('\n'):
                                    if 'oracle.com/java/technologies/downloads' in line.lower() or \
                                       'python.org/downloads' in line.lower() or \
                                       'openjdk.org' in line.lower():
                                        url_match = re.search(r'https?://[^\s]+', line)
                                        if url_match:
                                            official_urls.append(url_match.group())
                                
                                if official_urls:
                                    console.print("📄 正在提取官方页面内容...", style="dim")
                                    page_content = web_content_extract(official_urls[0], timeout=10)
                                    if page_content and not page_content.startswith("[错误]"):
                                        console.print("✅ 官方页面内容提取成功", style="green")
                                        # 将官方页面内容添加到搜索结果中
                                        web_search_result += f"\n\n=== 官方页面详细信息 ===\n{page_content[:1000]}"
                            except Exception as e:
                                console.print(f"⚠️ 页面内容提取失败: {e}", style="dim")
                        
                        # 将网络搜索结果添加到问题中，让RAG引擎能够参考
                        question = f"{question}\n\n网络搜索参考信息：\n{web_search_result}"
                    else:
                        console.print("⚠️ 所有搜索查询均未返回有效结果，继续使用知识库", style="yellow")
                except Exception as e:
                    console.print(f"⚠️ 网络搜索失败，继续使用知识库: {e}", style="yellow")
            
            # 重新判断知识库状态（用户可能在上面通过文件路径添加了文档并初始化索引）
            kb_initialized = rag_engine.query_engine is not None

            if kb_initialized:
                if Config.SHOW_PROGRESS:
                    result = rag_engine.query_with_sources(question, progress_callback=ask_progress_callback)
                else:
                    with console.status("[bold green]检索知识库..."):
                        result = rag_engine.query_with_sources(question)
            else:
                # 知识库未初始化：直接用 LLM 回答（基于网络搜索结果或模型自身知识），
                # 避免查询空索引抛出 RuntimeError 导致程序崩溃。
                if web_search_result:
                    prompt = question  # 已拼接网络搜索参考信息
                else:
                    console.print("💡 知识库为空，直接使用模型回答（可能不含最新信息）", style="dim")
                    prompt = question
                try:
                    from llama_index.core import Settings
                    with console.status("[bold green]模型思考中..."):
                        llm_resp = Settings.llm.complete(prompt)
                    result = {"answer": str(llm_resp), "sources": []}
                except Exception as e:  # noqa: BLE001
                    result = {"answer": f"回答失败：{e}", "sources": []}

            console.print("\n🤖 回答:", style="bold blue")
            if HAS_RICH:
                console.print(Panel(Markdown(result["answer"]), border_style="green"))
            else:
                print(result["answer"])
            last_rag_sources = result["sources"]
            if last_rag_sources:
                console.print(f"\n📎 基于 {len(last_rag_sources)} 个相关片段生成", style="dim")
            # 只记录用户原始问题，不记录拼接的网络搜索结果正文
            record_command_execution("ask", original_question)

        elif parsed.cmd_type == "agent":
            task = parsed.arg
            try:
                answer = react_engine.chat(task)
            except KeyboardInterrupt:
                console.print("\n[yellow]用户中断，任务已停止。[/yellow]")
                react_engine.stop()
                should_show_recommendations = False
            except Exception as e:
                console.print(f"[red]错误: {e}[/red]")
                should_show_recommendations = False

            if HAS_RICH:
                if "```" in answer or "**" in answer or "#" in answer:
                    console.print(Markdown(answer))
                else:
                    console.print(Panel(answer, border_style="green", title="Agent", box=box.ROUNDED))
            else:
                print("\n" + "=" * 50)
                print(answer)
                print("=" * 50 + "\n")

            if len(react_engine.step_log) > 1:
                console.print(f"[dim]本次共执行 {len(react_engine.step_log)} 步，输入 /summary 查看详情[/dim]")
            record_command_execution("agent", task)

        # ---- 默认：智能路由 ----
        elif parsed.cmd_type == "natural":
            if rag_engine.query_engine is not None:
                with console.status("[bold green]检索知识库..."):
                    result = rag_engine.query_with_sources(parsed.arg)
                console.print("\n🤖 回答:", style="bold blue")
                if HAS_RICH:
                    console.print(Panel(Markdown(result["answer"]), border_style="green"))
                else:
                    print(result["answer"])
                last_rag_sources = result["sources"]
                if last_rag_sources:
                    console.print(f"\n📎 基于 {len(last_rag_sources)} 个相关片段生成", style="dim")
                    console.print("[dim]输入 /sources 查看详细来源 | /agent 切换 Agent 模式[/dim]")
                record_command_execution("natural", parsed.arg)
            else:
                console.print(
                    "[yellow]知识库未初始化。请选择:[/yellow]\n"
                    "  1. 输入 /agent <任务> 使用 Agent 模式（代码操作）\n"
                    "  2. 使用 --data <路径> 启动以构建知识库\n"
                    "  3. 输入 /add <文件> 添加文档到知识库"
                )
                should_show_recommendations = False

        # ---- 未知命令 ----
        elif parsed.cmd_type == "unknown_cmd":
            console.print(f"[yellow]未知命令: {parsed.raw}，输入 /help 查看帮助[/yellow]")
            should_show_recommendations = False
        
        # ---- 统一命令推荐显示 ----
        # 在所有命令处理完成后统一显示推荐，避免在每个命令分支中重复代码
        if should_show_recommendations:
            show_command_recommendations()

if __name__ == "__main__":
    main()
