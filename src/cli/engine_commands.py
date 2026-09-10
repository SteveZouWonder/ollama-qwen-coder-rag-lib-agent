"""与引擎 / 主循环状态强耦合的 CLI 命令（F10 P3-2-c 由 ``query_interface`` 外迁）。

``handle_xxx(ctx, parsed)`` 直接读写 ``state.rag_engine`` / ``state.react_engine`` /
``state.last_*_sources``，与 ``cli.handlers.COMMAND_HANDLERS`` 互补；``_build_cli_context``
每次分发时从 ``cli.state`` 装配一个新的 ``CLIContext``，``dispatch_command`` 先查
``_ENGINE_HANDLERS`` 再查 ``COMMAND_HANDLERS``。函数签名保持 ``(ctx, parsed)`` 不变。

测试打桩约定：``record_command_execution`` / ``_health_before`` / ``_conversation`` /
``_print_health_hint`` / ``registry`` 等协作对象在**本模块**命名空间取名，patch 目标应为
``cli.engine_commands.<name>``；引擎与控制台走 ``cli.state.<name>``。
"""
import logging
import os
import re
from pathlib import Path

import rag_pipeline
from agent_tools import (registry, CommandSafetyChecker,
                         auto_confirm_allows, HIGH_RISK_CONFIRM_HINT)
from cli import state
from cli.callbacks import ask_progress_callback
from cli.parser import ParsedCommand
from cli.rag_adapter import _cli_ask_progress, _is_meta_query
from cli.recommend import (record_command_execution, record_conversation,
                           _conversation, _print_health_hint, _health_before)
from cli.render import (print_banner, print_help, print_tools, show_tutorial,
                        print_knowledge_stats, print_rag_sources, print_web_sources,
                        count_code_sources, _render_answer, _live_answer,
                        _print_notices, _citation_summary)
from config import Config
from document_loader import load_documents

logger = logging.getLogger(__name__)

try:
    from rich.markdown import Markdown
    from rich.panel import Panel
    from rich import box
except ImportError:  # pragma: no cover - rich 缺失时由 state.HAS_RICH 走纯文本分支
    pass

# 知识库管理功能（技能生成 / 快照）是否可用：只把"模块本身不存在"判为未安装，
# 模块内部导入出错会记 WARNING 而不是被吞成"未安装"（F10 P3-2 待办 #1）
from optional_deps import probe_modules

KNOWLEDGE_MANAGEMENT_AVAILABLE = probe_modules(
    "knowledge_to_skills", "knowledge_snapshot", feature="知识库管理（技能生成 / 快照）",
)


# ==================== 与引擎/主循环状态强耦合的命令处理 ====================
# 这些命令需要直接读写 rag_engine / react_engine / last_rag_sources 等运行时
# 状态，故保留在本模块（而非 cli.handlers），但同样抽成独立函数，使交互主循环
# 的分发逻辑保持精简。每个函数返回 should_show_recommendations。

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
    original_question = question  # 用于命令记录，避免把搜索结果正文塞进历史

    # 元/概览类问题会在 answer_question 内部识别并通过 meta_overview 事件渲染。
    # 检测用户是否在问题中提供了本地文件路径（图片/PDF/MD/TXT 等）——CLI 独有。
    if not _is_meta_query(original_question):
        inline_path = _detect_inline_file(question)
        if inline_path:
            question = _ingest_inline_file(inline_path, question)

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


# 可内联入库的文件类型（与历史行为一致：图片 / PDF / Markdown / 纯文本）
_INLINE_FILE_EXTS = ("png", "jpg", "jpeg", "pdf", "md", "txt")
# 绝对路径候选：POSIX ``/…`` 或 ``~/…``、Windows ``C:\…`` / ``C:/…``；到空白 / 括号 / 引号为止
_INLINE_FILE_RE = re.compile(
    r"(?:[A-Za-z]:[\\/]|~[\\/]|/)[^\s()\[\]<>\"'|]*?\.(?:%s)\b" % "|".join(_INLINE_FILE_EXTS),
    re.IGNORECASE,
)


def _detect_inline_file(question: str) -> str | None:
    """从问题文本中找出第一个**真实存在**的本地文件绝对路径；没有返回 None。

    F10 P3-2 待办 #6：此前正则写死 ``/Users/`` 前缀，Linux ``/home/…``、Windows 盘符路径
    都不会触发内联入库。现改为"形似绝对路径 + 扩展名白名单 + ``os.path.isfile``"三重判定，
    相对路径 / 不存在的路径不触发（避免把 URL 片段或误写路径当成文件去加载）。
    """
    for m in _INLINE_FILE_RE.finditer(question or ""):
        candidate = m.group(0)
        if os.path.isfile(os.path.expanduser(candidate)):
            return candidate
    return None


def _ingest_inline_file(file_path: str, question: str) -> str:
    """将问题中检测到的文件加入知识库，并清洗/补全查询文本后返回。"""
    state.console.print(f"📄 检测到文件路径: {file_path}", style="yellow")
    state.console.print("🔄 正在添加到知识库...", style="yellow")
    try:
        from document_loader import load_documents as _load
        documents = _load(os.path.expanduser(file_path))
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

    if engine is not None and getattr(engine, "retriever", None) is None:
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
