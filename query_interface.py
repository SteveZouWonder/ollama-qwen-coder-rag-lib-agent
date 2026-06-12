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

# 在任何导入之前禁用各种警告
# 禁用ChromaDB遥测错误
os.environ['ANONYMIZED_TELEMETRY'] = 'False'
os.environ['CHROMA_TELEMETRY'] = 'False'
logging.getLogger("chromadb").setLevel(logging.ERROR)

# 禁用urllib3的OpenSSL警告（macOS LibreSSL版本问题）
warnings.filterwarnings("ignore", message="urllib3 v2 only supports OpenSSL 1.1.1+")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

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

# ==================== 全局状态 ====================
rag_engine: RAGEngine = None
react_engine: ReActEngine = None
last_rag_sources = []

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
欢迎使用 智能文档+代码助手！

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
        from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
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
        
        console.print(
            f"[{color}]{phase_emoji} [{step}/{total}] {msg}[/{color}] "
            f"[dim][{progress_bar}] {progress_percent:.0f}%[/dim]"
        )
    else:
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
            "[bold cyan]智能文档+代码助手[/bold cyan]   [dim]v3.0[/dim]\n"
            "[dim]RAG 知识库 | ReAct Agent | 本地 Ollama | 安全护栏[/dim]\n"
            f"[green]模型: {LLM_MODEL}[/green] | [green]Ollama: {OLLAMA_BASE_URL}[/green]",
            border_style="cyan", box=box.ROUNDED
        ))
    else:
        print("=" * 60)
        print("       智能文档+代码助手  v3.0")
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

使用示例：
  >>> /ask 这篇论文的实验结果是什么？
  >>> /agent 把 utils.py 里的 print 改成 logging，并运行测试
  >>> /agent 搜索项目中所有使用硬编码密码的地方
  >>> /add ~/Downloads/论文.pdf
  >>> /file src/main.py
  >>> /generate-skills
  >>> /snapshot-list
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
        histfile = os.path.expanduser("~/.code_agent_cli_history")
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
                     "snapshot_restore", "knowledge_summary"):
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


# ==================== 主程序 ====================

def main():
    global rag_engine, react_engine, last_rag_sources

    parser = argparse.ArgumentParser(
        description="智能文档+代码助手 - RAG + Agent",
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
    args = parser.parse_args()

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

        # ---- 退出 ----
        if parsed.cmd_type == "quit":
            console.print("👋 再见！", style="bold green")
            break

        # ---- 帮助与教程 ----
        elif parsed.cmd_type == "help":
            print_help()
            continue
        elif parsed.cmd_type == "tutorial":
            show_tutorial()
            continue
        elif parsed.cmd_type == "tools":
            print_tools()
            continue

        # ---- 知识库命令 ----
        elif parsed.cmd_type == "stats":
            print_knowledge_stats()
            continue
        elif parsed.cmd_type == "sources":
            print_rag_sources(last_rag_sources)
            continue
        elif parsed.cmd_type == "add":
            path = parsed.arg
            try:
                docs = load_documents(path)
                if docs:
                    rag_engine.add_documents(docs, [path])
                    console.print("✅ 文档已添加到知识库", style="green")
                    console.print("💡 提示: 可以使用 /generate-skills 将知识库转化为Skills", style="dim")
                else:
                    console.print("⚠️  未找到可加载的文档", style="yellow")
            except Exception as e:
                console.print(f"❌ 添加失败: {e}", style="red")
            continue
        
        # ---- 知识库管理命令 ----
        elif parsed.cmd_type == "generate_skills":
            if not KNOWLEDGE_MANAGEMENT_AVAILABLE:
                console.print("❌ 知识库管理模块未安装", style="red")
                continue
            if not rag_engine:
                console.print("❌ 知识库未初始化", style="yellow")
                continue
            try:
                console.print("🔄 开始生成Skills...", style="cyan")
                engine = KnowledgeToSkillsEngine()
                results = engine.convert()
                console.print(f"✅ 成功生成 {len(results)} 个Skills:", style="green")
                for key, path in results.items():
                    console.print(f"  • {key}: {path}", style="dim")
            except Exception as e:
                console.print(f"❌ 生成Skills失败: {e}", style="red")
            continue
        
        elif parsed.cmd_type == "snapshot_list":
            if not KNOWLEDGE_MANAGEMENT_AVAILABLE:
                console.print("❌ 知识库管理模块未安装", style="red")
                continue
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
            except Exception as e:
                console.print(f"❌ 获取快照列表失败: {e}", style="red")
            continue
        
        elif parsed.cmd_type == "snapshot_create":
            if not KNOWLEDGE_MANAGEMENT_AVAILABLE:
                console.print("❌ 知识库管理模块未安装", style="red")
                continue
            if not rag_engine:
                console.print("❌ 知识库未初始化", style="yellow")
                continue
            try:
                manager = KnowledgeSnapshotManager()
                snapshot = manager.create_snapshot(trigger="manual")
                console.print(f"✅ 快照创建完成: {snapshot.snapshot_id}", style="green")
                console.print(f"📅 时间: {snapshot.timestamp}", style="dim")
                console.print(f"📄 文档数: {len(snapshot.documents)}", style="dim")
            except Exception as e:
                console.print(f"❌ 创建快照失败: {e}", style="red")
            continue
        
        elif parsed.cmd_type == "snapshot_restore":
            if not KNOWLEDGE_MANAGEMENT_AVAILABLE:
                console.print("❌ 知识库管理模块未安装", style="red")
                continue
            snapshot_id = parsed.arg
            if not snapshot_id:
                console.print("❌ 请指定快照ID: /snapshot-restore <id>", style="yellow")
                continue
            try:
                manager = KnowledgeSnapshotManager()
                snapshot = manager.load_snapshot(snapshot_id)
                if not snapshot:
                    console.print(f"❌ 快照不存在: {snapshot_id}", style="red")
                    continue
                
                console.print(f"🔄 恢复快照: {snapshot_id}", style="cyan")
                console.print(f"📄 文档数: {len(snapshot.documents)}", style="dim")
                
                # 生成恢复脚本
                helper = RestoreHelper(manager)
                script_file = helper.generate_restore_script(snapshot_id)
                console.print(f"✅ 恢复脚本已生成: {script_file}", style="green")
                console.print("💡 请运行该脚本来恢复知识库", style="yellow")
            except Exception as e:
                console.print(f"❌ 恢复快照失败: {e}", style="red")
            continue
        
        elif parsed.cmd_type == "knowledge_summary":
            if not KNOWLEDGE_MANAGEMENT_AVAILABLE:
                console.print("❌ 知识库管理模块未安装", style="red")
                continue
            if not rag_engine:
                console.print("❌ 知识库未初始化", style="yellow")
                continue
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
            except Exception as e:
                console.print(f"❌ 获取摘要失败: {e}", style="red")
            continue

        # ---- Agent 历史与上下文 ----
        elif parsed.cmd_type == "clear":
            console.clear()
            print_banner()
            continue
        elif parsed.cmd_type == "history":
            msgs = react_engine.history.get_messages()
            if len(msgs) <= 1:
                console.print("[dim]暂无对话历史[/dim]")
                continue
            lines = []
            for i, m in enumerate(msgs):
                role = m.get("role", "?")
                content = m.get("content", "")[:80].replace("\n", " ")
                lines.append(f"{i}. [{role}] {content}...")
            if HAS_RICH:
                console.print(Panel("\n".join(lines), title="历史记录", border_style="dim"))
            else:
                print("\n".join(lines))
            continue
        elif parsed.cmd_type == "summary":
            summary = react_engine.get_step_summary()
            if HAS_RICH:
                console.print(Panel(summary, title="执行摘要", border_style="blue"))
            else:
                print(summary)
            continue
        elif parsed.cmd_type == "reset":
            react_engine.clear_history()
            console.print("🔄 Agent 对话上下文已重置", style="green")
            continue

        # ---- 文件操作 ----
        elif parsed.cmd_type == "file":
            path = parsed.arg
            result = registry.execute("read_file", {"path": path}, auto_confirm=True)
            if HAS_RICH:
                console.print(Panel(result, title=f"文件: {path}", border_style="blue"))
            else:
                print(result)
            continue
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
            continue
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
                continue
            if safety["needs_confirm"] and not Config.AUTO_CONFIRM:
                try:
                    ans = console.input("确认执行? (y/n): ").strip().lower()
                except (EOFError, KeyboardInterrupt):
                    print("已取消")
                    continue
                if ans not in ("y", "yes", "是"):
                    console.print("[dim]已取消[/dim]")
                    continue
            result = registry.execute("execute_command", {"command": cmd}, auto_confirm=True)
            if HAS_RICH:
                console.print(Panel(result, title="命令输出", border_style="magenta"))
            else:
                print(result)
            continue

        # ---- 目录操作 ----
        elif parsed.cmd_type == "pwd":
            print(os.getcwd())
            continue
        elif parsed.cmd_type == "cd":
            path = parsed.arg
            try:
                os.chdir(path)
                new_dir = os.getcwd()
                console.print(f"[green]已切换到: {new_dir}[/green]")
            except FileNotFoundError:
                console.print(f"[red]目录不存在: {path}[/red]")
            except PermissionError:
                console.print(f"[red]权限不足: {path}[/red]")
            except Exception as e:
                console.print(f"[red]切换失败: {e}[/red]")
            continue
        elif parsed.cmd_type == "model":
            console.print(f"[green]模型: {react_engine.model}[/green]")
            console.print(f"[green]Ollama: {react_engine.host}[/green]")
            console.print(f"[green]自动确认: {Config.AUTO_CONFIRM}[/green]")
            continue

        # ---- 模式分发 ----
        elif parsed.cmd_type == "ask":
            question = parsed.arg
            if rag_engine.query_engine is None:
                console.print("⚠️  知识库未初始化，请先添加文档", style="yellow")
                continue
            
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
            
            if Config.SHOW_PROGRESS:
                result = rag_engine.query_with_sources(question, progress_callback=ask_progress_callback)
            else:
                with console.status("[bold green]检索知识库..."):
                    result = rag_engine.query_with_sources(question)
            console.print("\n🤖 回答:", style="bold blue")
            if HAS_RICH:
                console.print(Panel(Markdown(result["answer"]), border_style="green"))
            else:
                print(result["answer"])
            last_rag_sources = result["sources"]
            if last_rag_sources:
                console.print(f"\n📎 基于 {len(last_rag_sources)} 个相关片段生成", style="dim")
            continue

        elif parsed.cmd_type == "agent":
            task = parsed.arg
            try:
                answer = react_engine.chat(task)
            except KeyboardInterrupt:
                console.print("\n[yellow]用户中断，任务已停止。[/yellow]")
                react_engine.stop()
                continue
            except Exception as e:
                console.print(f"[red]错误: {e}[/red]")
                continue

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
            continue

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
            else:
                console.print(
                    "[yellow]知识库未初始化。请选择:[/yellow]\n"
                    "  1. 输入 /agent <任务> 使用 Agent 模式（代码操作）\n"
                    "  2. 使用 --data <路径> 启动以构建知识库\n"
                    "  3. 输入 /add <文件> 添加文档到知识库"
                )
            continue

        # ---- 未知命令 ----
        elif parsed.cmd_type == "unknown_cmd":
            console.print(f"[yellow]未知命令: {parsed.raw}，输入 /help 查看帮助[/yellow]")
            continue

if __name__ == "__main__":
    main()
