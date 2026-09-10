"""网络搜索 / 代码分析 / 知识图谱命令：``/web-*`` ``/code-*`` ``/graph-*``。"""
from __future__ import annotations

import logging
from pathlib import Path

from .base import _confirm, _is_error

logger = logging.getLogger(__name__)


# ==================== 网络搜索命令 ====================

def handle_web_search(ctx, parsed):
    console = ctx.console
    query = parsed.arg.strip()
    if not query:
        console.print("❌ 请提供搜索查询: /web-search <query>", style="yellow")
        return False
    try:
        console.print(f"🔍 正在搜索: {query}", style="cyan")
        result = ctx.registry.execute("web_search", {"query": query})
        if _is_error(result):
            console.print(result, style="yellow")
            return False
        console.print(result, style="green")
        ctx.record_command("web_search", query)
    except Exception as e:  # noqa: BLE001
        console.print(f"❌ 搜索失败: {e}", style="red")
        ctx.record_command("web_search", query, "failed", str(e))
    return True


def handle_web_cache(ctx, parsed):
    console = ctx.console
    arg = parsed.arg.strip()
    if not arg or arg == "status":
        try:
            result = ctx.registry.execute("web_cache_status", {})
            console.print(result, style="cyan")
            ctx.record_command("web_cache", "status")
        except Exception as e:  # noqa: BLE001
            console.print(f"❌ 获取缓存状态失败: {e}", style="red")
            ctx.record_command("web_cache", "status", "failed", str(e))
        return True
    if arg == "clear":
        # web_cache_clear 工具标记为 safe=False（需确认）。这是用户显式发起的
        # 命令，需走交互确认后再以 auto_confirm=True 执行，避免把内部协议串
        # [CONFIRM_REQUIRED] ... 直接打印给用户。
        if not _confirm(console, "确认清空搜索缓存? (y/n): "):
            console.print("[dim]已取消[/dim]")
            return False
        try:
            result = ctx.registry.execute("web_cache_clear", {}, auto_confirm=True)
            if _is_error(result):
                console.print(result, style="red")
                return False
            console.print(result, style="green")
            ctx.record_command("web_cache", "clear")
        except Exception as e:  # noqa: BLE001
            console.print(f"❌ 清空缓存失败: {e}", style="red")
            ctx.record_command("web_cache", "clear", "failed", str(e))
        return True
    console.print("❌ 未知命令，使用: /web-cache [status|clear]", style="yellow")
    return False


def handle_web_extract(ctx, parsed):
    console = ctx.console
    url = parsed.arg.strip()
    if not url:
        console.print("❌ 请提供URL: /web-extract <url>", style="yellow")
        return False
    try:
        console.print(f"📄 正在提取内容: {url}", style="cyan")
        result = ctx.registry.execute("web_content_extract", {"url": url})
        if result.startswith("[错误]"):
            console.print(result, style="red")
            return False
        console.print(result, style="green")
        ctx.record_command("web_extract", url)
    except Exception as e:  # noqa: BLE001
        console.print(f"❌ 内容提取失败: {e}", style="red")
        ctx.record_command("web_extract", url, "failed", str(e))
    return True


# ==================== 代码分析命令 ====================

def handle_code_ast(ctx, parsed):
    console = ctx.console
    pattern = parsed.arg.strip()
    if not pattern:
        console.print("❌ 请提供搜索模式: /code-ast <pattern>", style="yellow")
        return False
    try:
        console.print(f"🔍 正在搜索 AST: {pattern}", style="cyan")
        result = ctx.registry.execute("ast_search", {"pattern": pattern, "path": "."})
        if result.startswith("[错误]"):
            console.print(result, style="red")
            return False
        console.print(result, style="green")
        ctx.record_command("code_ast", pattern)
    except Exception as e:  # noqa: BLE001
        console.print(f"❌ AST 搜索失败: {e}", style="red")
        ctx.record_command("code_ast", pattern, "failed", str(e))
    return True


def handle_code_quality(ctx, parsed):
    console = ctx.console
    path = parsed.arg.strip() if parsed.arg.strip() else "."
    try:
        console.print(f"🔍 正在分析代码质量: {path}", style="cyan")
        result = ctx.registry.execute("code_quality_check", {"path": path})
        if result.startswith("[错误]"):
            console.print(result, style="red")
            return False
        console.print(result, style="green")
        ctx.record_command("code_quality", path)
    except Exception as e:  # noqa: BLE001
        console.print(f"❌ 代码质量检查失败: {e}", style="red")
        ctx.record_command("code_quality", path, "failed", str(e))
    return True


# ==================== 知识图谱命令 ====================

# /graph-query 支持的前缀 → 底层 query_type
_GRAPH_QUERY_PREFIXES = {
    "type": "type",            # type:tool      列出某类型的所有实体
    "neighbors": "neighbors",  # neighbors:DNS  查询邻居
    "neighbor": "neighbors",   # 容错别名
    "path": "path",            # path:A->B      查询两实体间路径
    "similar": "similar",      # similar:DNS    查询相似实体
    "entity": "entity",        # entity:DNS     显式按实体文本匹配
}


def _print_graph_query_usage(console):
    """打印 /graph-query 用法与可用类型，帮助用户选择正确查询方式。"""
    console.print("📖 /graph-query 用法：", style="cyan")
    console.print("  /graph-query <文本>            按实体名称模糊匹配（默认）", style="dim")
    console.print("  /graph-query type:<类型>       列出某类型的所有实体", style="dim")
    console.print("  /graph-query neighbors:<实体>  查询某实体的邻居", style="dim")
    console.print("  /graph-query path:<A>-><B>     查询两实体间的路径", style="dim")
    console.print("  /graph-query similar:<实体>    查询相似实体", style="dim")
    console.print(
        "  可用实体类型: person, organization, location, concept, "
        "technology, tool, language, framework, other",
        style="dim",
    )
    console.print("  示例: /graph-query type:tool   /graph-query neighbors:DNS", style="dim")


def handle_graph_query(ctx, parsed):
    console = ctx.console
    raw = parsed.arg.strip()
    if not raw:
        console.print("❌ 请提供查询内容。", style="yellow")
        _print_graph_query_usage(console)
        return False

    # 解析可选前缀（type:/neighbors:/path:/similar:/entity:）
    query_type = "entity"
    query = raw
    if ":" in raw:
        prefix, rest = raw.split(":", 1)
        mapped = _GRAPH_QUERY_PREFIXES.get(prefix.strip().lower())
        if mapped:
            query_type = mapped
            query = rest.strip()
        # 非已知前缀（如 URL、普通含冒号文本）则整体作为实体文本查询

    if not query:
        console.print("❌ 查询内容为空。", style="yellow")
        _print_graph_query_usage(console)
        return False

    try:
        desc = "" if query_type == "entity" else f"（{query_type}）"
        console.print(f"🔍 正在查询知识图谱{desc}: {query}", style="cyan")
        result = ctx.registry.execute(
            "knowledge_graph_query", {"query": query, "query_type": query_type}
        )
        if result.startswith("[错误]"):
            console.print(result, style="red")
            return False
        console.print(result, style="green")
        # 命中为空时给出引导（区分“图谱为空”与“查询方式不对”）
        if "找到 0 个实体" in result:
            console.print(
                "💡 未命中。若想按类型列出实体，请用 /graph-query type:<类型>；"
                "图谱为空则先 /graph-build 构建。",
                style="yellow",
            )
            _print_graph_query_usage(console)
        ctx.record_command("graph_query", raw)
    except Exception as e:  # noqa: BLE001
        console.print(f"❌ 知识图谱查询失败: {e}", style="red")
        ctx.record_command("graph_query", raw, "failed", str(e))
    return True


def handle_graph_build(ctx, parsed):
    """手动/补建方式从文本或文件构建知识图谱。

    说明：常规文档入库（/add）已自动派生构建知识图谱，无需手动执行本命令。
    本命令用于手动喂入任意文本、调试，或在自动派生失败时补建。

    用法：
      /graph-build <文本>        直接用这段文本构建
      /graph-build @<文件路径>   读取文件内容后构建
    """
    console = ctx.console
    arg = parsed.arg.strip()
    if not arg:
        console.print("📝 知识图谱构建需要文本内容。用法：", style="cyan")
        console.print("  /graph-build <文本>        直接用这段文本构建", style="dim")
        console.print("  /graph-build @<文件路径>   读取文件内容后构建", style="dim")
        return False

    # 解析输入：@路径 → 读文件；否则视为内联文本
    doc_id = "manual"
    doc_type = "text"
    if arg.startswith("@"):
        file_path = arg[1:].strip()
        path = Path(file_path)
        if not path.exists() or not path.is_file():
            console.print(f"❌ 文件不存在: {file_path}", style="yellow")
            return False
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except Exception as e:  # noqa: BLE001
            console.print(f"❌ 读取文件失败: {e}", style="red")
            ctx.record_command("graph_build", file_path, "failed", str(e))
            return False
        if not text.strip():
            console.print(f"⚠️ 文件内容为空: {file_path}", style="yellow")
            return False
        doc_id = path.name
        # 常见代码后缀使用 code 抽取策略，其余按文本
        code_suffixes = {".py", ".js", ".ts", ".java", ".go", ".rs", ".c",
                         ".cpp", ".h", ".hpp", ".rb", ".php", ".cs", ".kt", ".swift"}
        doc_type = "code" if path.suffix.lower() in code_suffixes else "text"
        record_arg = f"@{file_path}"
    else:
        text = arg
        record_arg = arg[:50]

    try:
        console.print("🔨 正在构建知识图谱...", style="cyan")
        result = ctx.registry.execute(
            "knowledge_graph_build",
            {"text": text, "doc_id": doc_id, "doc_type": doc_type},
        )
        if _is_error(result):
            console.print(result, style="red")
            return False
        console.print(result, style="green")
        ctx.record_command("graph_build", record_arg)
    except Exception as e:  # noqa: BLE001
        console.print(f"❌ 知识图谱构建失败: {e}", style="red")
        ctx.record_command("graph_build", record_arg, "failed", str(e))
    return True


def _get_graph_builder():
    try:
        from knowledge_graph import get_graph_builder
    except ImportError:  # pragma: no cover
        from src.knowledge_graph import get_graph_builder  # type: ignore
    return get_graph_builder()


def handle_graph_summary(ctx, parsed):
    """/graph-summary：图谱概览（节点/边/连通分量/类型分布）。"""
    console = ctx.console
    try:
        builder = _get_graph_builder()
        if getattr(builder, "graph", None) is None:
            console.print("❌ 知识图谱不可用（networkx 未安装）", style="red")
            return False
        stats = builder.get_statistics()
        console.print("🕸️  知识图谱概览", style="bold cyan")
        console.print(f"  节点: {stats.total_nodes}   边: {stats.total_edges}", style="bold")
        console.print(
            f"  连通分量: {stats.connected_components}   平均度: {stats.average_degree:.2f}   "
            f"密度: {stats.density:.4f}",
            style="dim",
        )
        if stats.total_nodes == 0:
            console.print("  图谱为空：/add 入库文档会自动派生，或 /graph-build 手动构建", style="yellow")
        if stats.entity_types:
            console.print("  实体类型分布:", style="cyan")
            for t, c in sorted(stats.entity_types.items(), key=lambda kv: -kv[1]):
                console.print(f"    {t:<14} {c}", style="dim")
        if stats.relation_types:
            console.print("  关系类型分布:", style="cyan")
            for t, c in sorted(stats.relation_types.items(), key=lambda kv: -kv[1]):
                console.print(f"    {t:<14} {c}", style="dim")
        console.print("💡 /graph-export 可导出交互式 3D 图谱 HTML 并在浏览器打开", style="dim")
        ctx.record_command("graph_summary")
    except Exception as e:  # noqa: BLE001
        console.print(f"❌ 获取图谱概览失败: {e}", style="red")
        ctx.record_command("graph_summary", "", "failed", str(e))
    return True


def parse_graph_export_args(arg: str) -> dict:
    """解析 ``/graph-export [路径] [--3d|--2d] [--types a,b] [--max N] [--focus 实体] [--hops N]``。

    ``--focus`` 的值可含空格（取到下一个 ``--`` 开头的 token 为止）。返回
    ``{"path", "dim", "types", "max_nodes", "focus", "hops", "error"}``。
    """
    out = {"path": "", "dim": 3, "types": None, "max_nodes": 500, "focus": None, "hops": 1, "error": ""}
    tokens = (arg or "").split()
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        low = tok.lower()
        if low == "--3d":
            out["dim"] = 3
        elif low == "--2d":
            out["dim"] = 2
        elif low in ("--types", "--type"):
            i += 1
            if i >= len(tokens):
                out["error"] = "--types 需要参数，如 --types tool,concept"
                break
            out["types"] = [t.strip() for t in tokens[i].split(",") if t.strip()] or None
        elif low == "--max":
            i += 1
            try:
                out["max_nodes"] = max(1, int(tokens[i]))
            except (IndexError, ValueError):
                out["error"] = "--max 需要正整数参数"
                break
        elif low == "--hops":
            i += 1
            try:
                out["hops"] = max(1, min(3, int(tokens[i])))
            except (IndexError, ValueError):
                out["error"] = "--hops 需要整数参数（1-3）"
                break
        elif low == "--focus":
            words = []
            i += 1
            while i < len(tokens) and not tokens[i].startswith("--"):
                words.append(tokens[i])
                i += 1
            if not words:
                out["error"] = "--focus 需要实体名参数"
                break
            out["focus"] = " ".join(words)
            continue
        elif tok.startswith("--"):
            out["error"] = f"未知选项: {tok}"
            break
        else:
            out["path"] = tok
        i += 1
    return out


def handle_graph_export(ctx, parsed, open_browser=None):
    """/graph-export：导出自包含的交互式 HTML 图谱（Plotly，离线）并在浏览器打开。"""
    console = ctx.console
    opts = parse_graph_export_args(parsed.arg)
    if opts["error"]:
        console.print(f"❌ {opts['error']}", style="yellow")
        console.print(
            "用法: /graph-export [路径] [--3d|--2d] [--types a,b] [--max N] [--focus 实体] [--hops 1|2]",
            style="dim",
        )
        return False
    try:
        try:
            from web.app import build_graph_figure
        except ImportError:  # pragma: no cover
            from src.web.app import build_graph_figure  # type: ignore
        builder = _get_graph_builder()
        if getattr(builder, "graph", None) is None:
            console.print("❌ 知识图谱不可用（networkx 未安装）", style="red")
            return False
        view = builder.subgraph_for_view(
            types=opts["types"], max_nodes=opts["max_nodes"], focus=opts["focus"], hops=opts["hops"],
        )
        if not view["nodes"]:
            console.print("📭 没有可导出的节点（图谱为空或筛选条件过严）", style="yellow")
            ctx.record_command("graph_export", parsed.arg, "empty")
            return True
        positions = builder.layout_positions([n["id"] for n in view["nodes"]], dim=opts["dim"])
        title = f"Cerebro 知识图谱（{len(view['nodes'])} 节点 / {len(view['edges'])} 边）"
        try:
            fig = build_graph_figure(
                view["nodes"], view["edges"], dim=opts["dim"], positions=positions,
                edge_labels=(opts["dim"] == 2), title=title,
            )
        except ImportError:
            console.print("❌ 未安装 plotly：pip install plotly 后重试", style="red")
            return False
        from datetime import datetime
        path = opts["path"] or f"knowledge_graph_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
        out_path = Path(path).expanduser()
        if out_path.suffix.lower() != ".html":
            out_path = out_path.with_suffix(".html")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        fig.write_html(str(out_path), include_plotlyjs=True, full_html=True)
        console.print(
            f"✅ 已导出 {opts['dim']}D 图谱: {out_path}（{len(view['nodes'])} 节点 / {len(view['edges'])} 边"
            + ("，已按度数截断" if view.get("truncated") else "") + "）",
            style="green",
        )
        opener = open_browser
        if opener is None:
            import webbrowser
            opener = webbrowser.open
        try:
            opener(out_path.resolve().as_uri())
            console.print("🌐 已在浏览器中打开", style="dim")
        except Exception as e:  # noqa: BLE001
            console.print(f"⚠️  无法自动打开浏览器: {e}", style="yellow")
        ctx.record_command("graph_export", str(out_path), "success")
    except Exception as e:  # noqa: BLE001
        console.print(f"❌ 导出图谱失败: {e}", style="red")
        ctx.record_command("graph_export", parsed.arg, "failed", str(e))
    return True
