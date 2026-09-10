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
    from rich.markdown import Markdown
    from rich.panel import Panel
    from rich import box

if state.HAS_PROMPT_TOOLKIT:
    from prompt_toolkit import prompt as pt_prompt
    from prompt_toolkit.history import FileHistory
    from prompt_toolkit.auto_suggest import AutoSuggestFromHistory

from config import Config, DATA_DIR, INDEX_DIR, LLM_MODEL, OLLAMA_BASE_URL  # noqa: F401 - Config 供 ``qi.Config`` 兼容引用
from rag_engine import RAGEngine
from react_engine import ReActEngine
from agent_tools import set_rag_engine
from document_loader import load_documents
import rag_pipeline

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

# ==================== 教程 / 回调 / 渲染 / 推荐 / RAG 适配（F10 P3-2-b 已外迁，此处重导出） ====================

from cli.help_text import TUTORIAL_TEXT  # noqa: E402,F401 - 教程文案已移至 cli.help_text
from cli.render import (  # noqa: E402,F401
    CEREBRO_ASCII, print_banner, backend_banner_text,
    show_tutorial, check_first_run, print_help, print_tools, print_rag_sources,
    _source_code_location, count_code_sources, print_knowledge_stats,
    _render_meta_overview, print_web_sources,
    _render_answer, _live_answer, _print_notices, _citation_summary,
)
from cli.callbacks import (  # noqa: E402,F401
    STEP_PHASE_EMOJI, STEP_PHASE_COLOR, _live_streaming,
    on_step_callback, on_confirm_callback, ask_progress_callback,
)
from cli.rag_adapter import (  # noqa: E402,F401
    _simple_web_search, _llm_direct_answer, plan_web_search, _merge_search_results,
    _extract_urls, _is_empty_rag_result, _is_meta_query, _parse_web_sources,
    _format_kb_context, run_web_search, enrich_with_page_content, _cli_ask_progress,
    _answer_meta_query, _synthesize_prompt,
)
from cli.recommend import (  # noqa: E402,F401
    show_command_recommendations, record_command_execution, record_conversation,
    _conversation, _print_health_hint, _health_before,
)

# 进度条状态管理：本体在 cli.state._progress_state（此处为只读别名）
_progress_state = state._progress_state

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


# ==================== 引擎耦合命令 / 上下文装配 / 分发（F10 P3-2-c 已外迁至 cli.engine_commands，此处重导出） ====================

from cli.engine_commands import (  # noqa: E402,F401
    KNOWLEDGE_MANAGEMENT_AVAILABLE,
    handle_clear, handle_history, handle_summary, handle_reset, handle_file, handle_write,
    handle_exec, handle_pwd, handle_cd, handle_model, handle_think, handle_auto, handle_ask,
    _run_ask, _ingest_inline_file, _augment_with_web_search, _answer_question,
    handle_agent, handle_natural, _route_natural_to_agent, handle_unknown_cmd,
    _ENGINE_HANDLERS, _build_cli_context, dispatch_command,
)

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
