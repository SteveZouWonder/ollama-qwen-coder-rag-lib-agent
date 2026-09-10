"""Git 命令：``/git-analyze`` ``/git-commit-gen``。"""
from __future__ import annotations

import logging

from .base import _is_error

logger = logging.getLogger(__name__)


# ==================== Git 命令 ====================

# /git-analyze 支持的分析类型；含常见单复数别名以提升容错。
_GIT_ANALYSIS_TYPES = {
    "history": "history",
    "status": "status",
    "authors": "authors",
    "author": "authors",   # 容错别名
    "commit": "history",   # 容错别名
    "commits": "history",
}


GIT_ANALYZE_MAX_COMMITS = 10
"""``/git-analyze`` 概览表显示的最近提交条数。"""


def _rich_table(title: str, columns: list[tuple[str, dict]]):
    """构造 ``Table(box=box.ROUNDED)``（与 ``query_interface.print_tools`` 同风格）。"""
    from rich import box
    from rich.table import Table

    table = Table(title=title, box=box.ROUNDED)
    for name, kw in columns:
        table.add_column(name, **kw)
    return table


def _git_overview(repo_path: str = ".", max_commits: int = GIT_ANALYZE_MAX_COMMITS) -> dict:
    """共享层 ``GitAnalyzer.get_overview``（与 Web 仪表盘同一数据源）；异常抛给调用方。"""
    from git_integration.git_analyzer import GitAnalyzer

    return GitAnalyzer(repo_path).get_overview(max_commits=max_commits)


def _print_git_overview(console, ov: dict) -> None:
    """概览一行 + 最近提交表。"""
    n_changed = len(ov.get("changed") or [])
    console.print(
        f"分支: [bold]{ov.get('branch') or '(分离 HEAD)'}[/bold]  ·  变更文件: {n_changed}"
        f"  ·  最近提交: {(ov.get('last_commit_at') or '—')[:16]}"
    )
    commits = ov.get("commits") or []
    if not commits:
        console.print("还没有提交记录", style="dim")
        return
    table = _rich_table(f"最近 {len(commits)} 次提交", [
        ("提交", {"style": "cyan", "no_wrap": True}), ("作者", {"style": "bold"}),
        ("日期", {"no_wrap": True}), ("标题", {}),
    ])
    for c in commits:
        table.add_row(str(c.get("hash7", "")), str(c.get("author", "")), str(c.get("date", "")),
                      str(c.get("subject", "")))
    console.print(table)


def _print_git_status(console, ov: dict) -> None:
    changed = ov.get("changed") or []
    if not changed:
        console.print("工作区干净，没有未提交的变更", style="dim")
        return
    table = _rich_table(f"变更文件（{len(changed)}）", [("状态", {"style": "yellow", "no_wrap": True}),
                                                       ("路径", {"style": "cyan"})])
    for c in changed:
        table.add_row(str(c.get("label") or c.get("status", "")), str(c.get("path", "")))
    console.print(table)


def _print_git_authors(console, ov: dict) -> None:
    authors = ov.get("authors") or []
    if not authors:
        console.print("还没有提交者", style="dim")
        return
    table = _rich_table("提交者统计", [("作者", {"style": "cyan"}), ("提交数", {"justify": "right"})])
    for a in authors:
        table.add_row(str(a.get("name", "")), str(a.get("commits", 0)))
    console.print(table)


def _print_git_plain(console, ov: dict, analysis_type: str) -> None:
    """无 rich 时的纯文本回退。"""
    if analysis_type == "status":
        for c in ov.get("changed") or []:
            console.print(f"  {c.get('label') or c.get('status', '')} {c.get('path', '')}")
        if not ov.get("changed"):
            console.print("工作区干净，没有未提交的变更")
    elif analysis_type == "authors":
        for a in ov.get("authors") or []:
            console.print(f"  {a.get('name', '')}: {a.get('commits', 0)}")
        if not ov.get("authors"):
            console.print("还没有提交者")
    else:
        console.print(f"分支: {ov.get('branch') or '(分离 HEAD)'} · 变更文件: {len(ov.get('changed') or [])}"
                      f" · 最近提交: {(ov.get('last_commit_at') or '—')[:16]}")
        for c in ov.get("commits") or []:
            console.print(f"  {c.get('hash7', '')} {c.get('date', '')} {c.get('author', '')}: {c.get('subject', '')}")
        if not ov.get("commits"):
            console.print("还没有提交记录")


def handle_git_analyze(ctx, parsed):
    """Git 分析（rich 表格，F9 P3-5）：无参 / ``history`` → 概览 + 最近提交表；
    ``status`` → 变更文件表；``authors`` → 提交者表。数据来自共享层 ``GitAnalyzer.get_overview``。"""
    console = ctx.console
    arg = parsed.arg.strip().lower()
    analysis_type = "history" if not arg else _GIT_ANALYSIS_TYPES.get(arg)
    if analysis_type is None:
        console.print(
            f"❌ 未知的分析类型 '{parsed.arg.strip()}'，支持: history / status / authors",
            style="yellow",
        )
        return False
    try:
        ov = _git_overview(".")
        if not ov.get("is_repo"):
            console.print("当前目录不是 Git 仓库（可用 /cd 切换到仓库目录）", style="dim")
            ctx.record_command("git_analyze", analysis_type)
            return True
        if not ctx.has_rich:
            _print_git_plain(console, ov, analysis_type)
        elif analysis_type == "status":
            _print_git_status(console, ov)
        elif analysis_type == "authors":
            _print_git_authors(console, ov)
        else:
            _print_git_overview(console, ov)
        ctx.record_command("git_analyze", analysis_type)
    except Exception as e:  # noqa: BLE001
        console.print(f"❌ Git 分析失败: {e}", style="red")
        ctx.record_command("git_analyze", analysis_type, "failed", str(e))
    return True


def handle_git_commit_gen(ctx, parsed):
    """基于工作区变更生成（AI）提交信息建议。"""
    console = ctx.console
    try:
        console.print("🔍 正在生成提交信息...", style="cyan")
        result = ctx.registry.execute(
            "git_commit_gen", {"repo_path": ".", "use_ai": True}
        )
        if _is_error(result):
            console.print(result, style="red")
            return False
        console.print(result, style="green")
        ctx.record_command("git_commit_gen")
    except Exception as e:  # noqa: BLE001
        console.print(f"❌ 生成提交信息失败: {e}", style="red")
        ctx.record_command("git_commit_gen", "", "failed", str(e))
    return True
