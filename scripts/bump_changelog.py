#!/usr/bin/env python3
"""CHANGELOG 归档工具。

把 CHANGELOG.md 中的 `## [Unreleased]` 区段归档为具体版本号区段
`## [vX.Y.Z] - YYYY-MM-DD`，并在顶部补回一个空的 `## [Unreleased]`。
同时支持仅「提取」某个版本（或 Unreleased）的正文，用于注入 Release Notes。

设计目标：
  - 仅依赖 Python 标准库，可在任意 CI runner 直接运行；
  - 幂等：若目标版本已存在，bump 时报错退出，避免重复归档；
  - 不破坏文件其余内容（版本号规则、发布说明等保留原样）。

用法：
  # 将 Unreleased 归档为 v1.2.3（日期默认取今天，可用 --date 指定）
  python scripts/bump_changelog.py bump --version 1.2.3

  # 仅预览归档结果（不写回文件），打印到 stdout
  python scripts/bump_changelog.py bump --version 1.2.3 --dry-run

  # 提取某版本的正文（不含标题行）；version 可为 vX.Y.Z / X.Y.Z / unreleased
  python scripts/bump_changelog.py extract --version 1.2.3

版本号既可带 v 前缀也可不带，内部统一规范化为 `vX.Y.Z`。
"""

from __future__ import annotations

import argparse
import datetime
import re
import subprocess
import sys
from pathlib import Path

# CHANGELOG.md 默认位于仓库根目录（即本脚本的上一级目录）。
DEFAULT_CHANGELOG = Path(__file__).resolve().parent.parent / "CHANGELOG.md"

UNRELEASED_HEADING = "## [Unreleased]"
# 归档后顶部补回的空 Unreleased 区段（含使用提示）。
EMPTY_UNRELEASED_BLOCK = (
    "## [Unreleased]\n"
    "\n"
    "> 下一版本的未发布变更请记录在此区段。发布时将其移动到对应的版本号下。\n"
)

SEMVER_RE = re.compile(r"^v?\d+\.\d+\.\d+([-.][0-9A-Za-z.]+)?$")


def normalize_version(version: str) -> str:
    """把用户输入的版本号规范化为带 v 前缀的形式，并校验语义化格式。"""
    version = version.strip()
    if not SEMVER_RE.match(version):
        raise ValueError(
            f"版本号「{version}」不符合语义化版本规范（期望 X.Y.Z，例如 1.0.0）"
        )
    return version if version.startswith("v") else f"v{version}"


def find_section_bounds(lines: list[str], heading_text: str) -> tuple[int, int] | None:
    """定位某个二级标题区段在 lines 中的 [起始行, 结束行) 范围。

    起始行为标题行本身；结束行为下一个 `## ` 标题行（不含）或文件末尾。
    heading_text 形如 "## [Unreleased]" 或 "## [v1.2.3]"，按「行去空白后以其开头」匹配，
    以兼容版本标题后面跟着的 ` - 日期`。
    返回 None 表示未找到。
    """
    start = None
    for i, line in enumerate(lines):
        if line.strip().startswith(heading_text):
            start = i
            break
    if start is None:
        return None
    end = len(lines)
    for j in range(start + 1, len(lines)):
        if lines[j].startswith("## "):
            end = j
            break
    return start, end


def extract_body(lines: list[str], start: int, end: int) -> str:
    """提取区段正文（去掉标题行，并裁剪首尾空行）。"""
    body = lines[start + 1 : end]
    # 去掉开头/结尾的空行。
    while body and body[0].strip() == "":
        body.pop(0)
    while body and body[-1].strip() == "":
        body.pop()
    return "\n".join(body)


# Conventional Commits 类型 -> CHANGELOG 中文分组标题的映射。
# 顺序即为最终在版本区段中输出的分组顺序。
CC_TYPE_TO_GROUP: dict[str, str] = {
    "feat": "新增",
    "fix": "修复",
    "perf": "改进",
    "refactor": "改进",
    "docs": "文档",
    "build": "构建",
    "ci": "构建",
    "revert": "回滚",
}
# 最终分组的展示顺序（去重后的 CC_TYPE_TO_GROUP.values() 的稳定顺序 + 其他兜底）。
GROUP_ORDER: list[str] = ["新增", "修复", "改进", "文档", "构建", "回滚", "其他"]

# 解析 Conventional Commits 标题：type(scope)!: subject
CC_SUBJECT_RE = re.compile(
    r"^(?P<type>[a-zA-Z]+)(?:\((?P<scope>[^)]*)\))?(?P<bang>!)?:\s*(?P<subject>.+)$"
)

# 不应进入 CHANGELOG 的提交（噪音）：CHANGELOG 归档提交、版本号 bump 等。
SKIP_SUBJECT_RE = re.compile(
    r"(archive CHANGELOG|bump version|归档 CHANGELOG|Merge (branch|pull request))",
    re.IGNORECASE,
)


def _run_git(args: list[str]) -> str | None:
    """运行 git 命令并返回 stdout；失败（非 0 退出或 git 不可用）返回 None。"""
    try:
        result = subprocess.run(
            ["git", *args],
            check=True,
            capture_output=True,
            text=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None
    return result.stdout


def collect_commit_subjects(since_ref: str | None, until_ref: str | None) -> list[str]:
    """收集 (since_ref, until_ref] 范围内的非合并提交标题。

    - since_ref 为 None 时，回退取 until_ref（或 HEAD）的全部历史；
    - until_ref 为 None 时默认 HEAD；
    - 自动过滤合并提交与归档噪音提交。
    返回保持 git log 默认的「从新到旧」顺序的标题列表。
    """
    until = until_ref or "HEAD"
    rev_range = f"{since_ref}..{until}" if since_ref else until
    out = _run_git(["log", "--no-merges", "--pretty=format:%s", rev_range])
    if out is None:
        return []
    subjects: list[str] = []
    for line in out.splitlines():
        subject = line.strip()
        if not subject or SKIP_SUBJECT_RE.search(subject):
            continue
        subjects.append(subject)
    return subjects


def previous_version_ref(version: str) -> str | None:
    """返回排在 `version`（带 v 前缀）之前的最近一个语义化版本 tag。

    若不存在前序 tag，返回 None（调用方将回退取全部历史）。
    """
    out = _run_git(["tag", "--sort=-v:refname"])
    if out is None:
        return None
    tags = [
        t.strip()
        for t in out.splitlines()
        if re.match(r"^v\d+\.\d+\.\d+$", t.strip())
    ]
    if version in tags:
        idx = tags.index(version)
        # tags 按版本从新到旧排序，version 之后的元素即更早的版本。
        if idx + 1 < len(tags):
            return tags[idx + 1]
        return None
    # version 自身尚未打 tag：tags 已是从新到旧，第一个即上一个版本。
    return tags[0] if tags else None


def generate_body_from_git(
    version: str, since_ref: str | None, until_ref: str | None
) -> str:
    """根据 git 提交记录按 Conventional Commits 分类，生成 CHANGELOG 正文。

    version 为带 v 前缀的目标版本，用于在缺省 since_ref 时自动推断前序 tag。
    返回组装好的 Markdown 正文（含 ### 分组小标题与列表项）；无可用提交时返回空串。
    """
    if since_ref is None:
        since_ref = previous_version_ref(version)
    subjects = collect_commit_subjects(since_ref, until_ref)
    if not subjects:
        return ""

    # 按分组聚合，保留各分组内「从新到旧」的提交顺序。
    grouped: dict[str, list[str]] = {}
    for subject in subjects:
        match = CC_SUBJECT_RE.match(subject)
        if match:
            cc_type = match.group("type").lower()
            group = CC_TYPE_TO_GROUP.get(cc_type, "其他")
            text = match.group("subject").strip()
        else:
            group = "其他"
            text = subject
        grouped.setdefault(group, []).append(text)

    lines: list[str] = []
    for group in GROUP_ORDER:
        items = grouped.get(group)
        if not items:
            continue
        if lines:
            lines.append("")
        lines.append(f"### {group}")
        for item in items:
            lines.append(f"- {item}")
    return "\n".join(lines)


def cmd_extract(args: argparse.Namespace) -> int:
    path = Path(args.file)
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()

    target = args.version.strip()
    if target.lower() == "unreleased":
        heading = UNRELEASED_HEADING
    else:
        heading = f"## [{normalize_version(target)}]"

    bounds = find_section_bounds(lines, heading)
    if bounds is None:
        print(f"::error::未找到区段 {heading}", file=sys.stderr)
        return 1
    start, end = bounds
    body = extract_body(lines, start, end)
    # 去除「使用提示」引用块（以 > 开头的行），避免污染 Release Notes。
    body_lines = [ln for ln in body.splitlines() if not ln.lstrip().startswith(">")]
    body = "\n".join(body_lines).strip()
    sys.stdout.write(body + ("\n" if body else ""))
    return 0


def cmd_bump(args: argparse.Namespace) -> int:
    path = Path(args.file)
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()

    version = normalize_version(args.version)
    date = args.date or datetime.date.today().isoformat()
    new_heading = f"## [{version}] - {date}"

    # 目标版本已存在则拒绝重复归档（幂等保护）。
    if find_section_bounds(lines, f"## [{version}]") is not None:
        print(f"::error::版本 {version} 已存在于 CHANGELOG，拒绝重复归档", file=sys.stderr)
        return 1

    bounds = find_section_bounds(lines, UNRELEASED_HEADING)
    if bounds is None:
        print("::error::CHANGELOG 中未找到 [Unreleased] 区段", file=sys.stderr)
        return 1
    start, end = bounds

    body = extract_body(lines, start, end)
    # 去掉「使用提示」引用块行，判断 [Unreleased] 是否真有可发布内容。
    content_lines = [
        ln for ln in body.splitlines() if ln.strip() and not ln.lstrip().startswith(">")
    ]

    if content_lines:
        # 优先使用人工在 [Unreleased] 中记录的内容（保留原 body，去掉提示引用块）。
        archived_body_lines = [
            ln for ln in body.splitlines() if not ln.lstrip().startswith(">")
        ]
        source = "[Unreleased] 人工记录"
    elif args.no_git_fallback:
        # 显式禁用 git 兜底时，维持原有的「必须人工补充」行为。
        print(
            "::error::[Unreleased] 区段没有任何可归档的变更内容，请先补充后再发布",
            file=sys.stderr,
        )
        return 1
    else:
        # [Unreleased] 为空：从 git 提交记录按 Conventional Commits 自动生成变更内容。
        generated = generate_body_from_git(version, args.since, args.until)
        if not generated.strip():
            print(
                "::error::[Unreleased] 为空，且无法从 git 提交记录自动生成变更内容"
                "（无前序提交或 git 不可用）。请手动补充 [Unreleased] 后再发布。",
                file=sys.stderr,
            )
            return 1
        archived_body_lines = generated.splitlines()
        source = "git 提交记录自动生成"
        print(f"::notice::[Unreleased] 为空，已从 {source} 填充 {version} 变更内容")

    # 裁剪首尾空行。
    while archived_body_lines and archived_body_lines[0].strip() == "":
        archived_body_lines.pop(0)
    while archived_body_lines and archived_body_lines[-1].strip() == "":
        archived_body_lines.pop()

    # 组装新的文件内容：
    #   [0, start)            = Unreleased 之前的内容（标题、说明等）
    #   空 Unreleased 区块
    #   归档后的版本区段
    #   [end, ...)            = 原 Unreleased 之后的所有内容（历史版本等）
    before = lines[:start]
    after = lines[end:]

    new_block: list[str] = []
    new_block.extend(EMPTY_UNRELEASED_BLOCK.rstrip("\n").splitlines())
    new_block.append("")
    new_block.append(new_heading)
    new_block.append("")
    new_block.extend(archived_body_lines)
    new_block.append("")

    new_lines = before + new_block + after
    new_text = "\n".join(new_lines).rstrip("\n") + "\n"

    if args.dry_run:
        sys.stdout.write(new_text)
        return 0

    path.write_text(new_text, encoding="utf-8")
    print(f"✅ 已将 [Unreleased] 归档为 {new_heading}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="CHANGELOG 归档工具")
    parser.add_argument(
        "--file",
        default=str(DEFAULT_CHANGELOG),
        help="CHANGELOG 路径（默认仓库根目录的 CHANGELOG.md）",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_bump = sub.add_parser("bump", help="将 [Unreleased] 归档为具体版本号")
    p_bump.add_argument("--version", required=True, help="版本号（可含或不含 v 前缀）")
    p_bump.add_argument("--date", help="发布日期 YYYY-MM-DD（默认今天）")
    p_bump.add_argument(
        "--dry-run", action="store_true", help="仅打印归档后的内容，不写回文件"
    )
    p_bump.add_argument(
        "--since",
        help="git 自动填充的起始 ref（不含）。缺省时自动取上一个版本 tag",
    )
    p_bump.add_argument(
        "--until",
        help="git 自动填充的结束 ref（含）。缺省为 HEAD",
    )
    p_bump.add_argument(
        "--no-git-fallback",
        action="store_true",
        help="禁用「[Unreleased] 为空时从 git 自动填充」，恢复为必须人工补充",
    )
    p_bump.set_defaults(func=cmd_bump)

    p_extract = sub.add_parser("extract", help="提取某版本/Unreleased 的正文")
    p_extract.add_argument(
        "--version", required=True, help="版本号或 unreleased"
    )
    p_extract.set_defaults(func=cmd_extract)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except ValueError as exc:
        print(f"::error::{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
