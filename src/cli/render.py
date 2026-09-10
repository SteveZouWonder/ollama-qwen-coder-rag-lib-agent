"""CLI 界面渲染（F10 P3-2-b 由 ``query_interface`` 外迁）。

教程 / 帮助包装、工具表、知识库来源表、网络来源表、知识库统计、知识库概览、
回答 Panel、流式答案面板、结构化提示与引用计数文案。全部经 ``state.console`` /
``state.HAS_RICH`` / ``state.rag_engine`` 运行时取值；横幅 ``print_banner`` 依赖入口
横幅 ``print_banner`` / ``backend_banner_text`` 也在此（``handle_clear`` 需要，且避免与入口模块循环导入）。
"""
import os

from agent_tools import registry
from cli import state
from cli.help_text import TUTORIAL_TEXT
from cli.help_text import print_help as _print_help
from config import Config, LLM_MODEL, OLLAMA_BASE_URL

try:
    from rich.markdown import Markdown
    from rich.panel import Panel
    from rich import box
    from rich.table import Table
    from rich.markup import escape
except ImportError:  # pragma: no cover - rich 缺失时由 state.HAS_RICH 走纯文本分支
    def escape(text):  # type: ignore[misc]
        return str(text)


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
