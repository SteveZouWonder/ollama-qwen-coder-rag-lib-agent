#!/usr/bin/env python3
"""模型输入资产（``prompts/``）的定位与加载。

``prompts/`` 是所有"喂给模型的可维护文本"的唯一目录，与代码、用户运行时配置
（``config/``）和运行时数据（``.cerebro/``）严格分离::

    prompts/
    ├── system/PROJECT_RULES.md      # 项目附加规范（ReAct 系统提示的「项目附加规范」层）
    └── skills/<name>/SKILL.md       # 通用行为 Skill（ReAct 系统提示的「Skills」层）

三层解析（后者覆盖同名前者）：

1. 内置只读：``runtime_paths.resource_root()/prompts``（源码运行为仓库目录；
   PyInstaller 打包后随 App 分发，见 ``packaging/cerebro.spec``）；
2. 用户可写：``runtime_paths.user_data_dir()/prompts``（桌面版为
   ``<用户数据目录>/prompts``；源码运行时与 1 相同，自动去重）；
3. 环境变量 ``AGENT_PROMPTS_DIR``：``os.pathsep`` 分隔的额外目录，优先级最高。

Skill 文件为 Markdown，可选 YAML frontmatter（仅支持 ``key: value`` 与
``[a, b]`` / ``- item`` 列表这一子集，不引入 PyYAML 依赖）::

    ---
    name: core
    description: General behaviour for every agent role
    roles: [agent, code, test, doc, audit]   # 缺省 = 全部角色
    ---
    # Skill body ...

环境变量：

- ``CODE_AGENT_SKILLS``：``off`` / ``0`` / ``false`` / ``no`` 时不注入 Skills 层；
- ``SKILL_MAX_CHARS``：Skills 层总字符上限（默认 4000），超出截断并标注。
"""
from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

logger = logging.getLogger(__name__)

PROMPTS_DIRNAME = "prompts"
SYSTEM_SUBDIR = "system"
SKILLS_SUBDIR = "skills"
PROJECT_RULES_FILENAME = "PROJECT_RULES.md"
SKILL_FILENAME = "SKILL.md"

ENV_EXTRA_DIRS = "AGENT_PROMPTS_DIR"
ENV_SKILLS_ENABLED = "CODE_AGENT_SKILLS"
ENV_SKILL_MAX_CHARS = "SKILL_MAX_CHARS"
DEFAULT_SKILL_MAX_CHARS = 4000

# 角色名：单 Agent 为 "agent"，多 Agent 子角色与 ``agents.agent_types.AgentType`` 的值一致
ROLE_AGENT = "agent"
ALL_ROLES = (ROLE_AGENT, "code", "test", "doc", "audit")

_FALSY = {"0", "off", "false", "no"}


# ==================== 目录解析 ====================


def prompt_dirs() -> List[Path]:
    """按优先级**从低到高**返回存在的 ``prompts/`` 目录列表（已按真实路径去重）。"""
    from runtime_paths import resource_root, user_data_dir

    candidates: List[Path] = [
        resource_root() / PROMPTS_DIRNAME,
        user_data_dir() / PROMPTS_DIRNAME,
    ]
    extra = os.environ.get(ENV_EXTRA_DIRS, "").strip()
    if extra:
        for raw in extra.split(os.pathsep):
            raw = raw.strip()
            if raw:
                candidates.append(Path(raw).expanduser())

    seen = set()
    result: List[Path] = []
    for p in candidates:
        try:
            key = p.resolve()
        except OSError:
            key = p
        if key in seen:
            continue
        seen.add(key)
        if p.is_dir():
            result.append(p)
    return result


def _read_text(path: Path) -> Optional[str]:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        logger.warning("读取提示资产失败 %s: %s", path, exc)
        return None


# ==================== 项目附加规范 ====================


def project_rules_path() -> Optional[Path]:
    """优先级最高的 ``system/PROJECT_RULES.md`` 路径；不存在返回 None。"""
    for d in reversed(prompt_dirs()):
        p = d / SYSTEM_SUBDIR / PROJECT_RULES_FILENAME
        if p.is_file():
            return p
    return None


def load_project_rules() -> Optional[str]:
    """读取项目附加规范原文；不存在或读取失败返回 None。"""
    p = project_rules_path()
    if p is None:
        return None
    text = _read_text(p)
    return text if text and text.strip() else None


# ==================== Skills ====================


@dataclass
class Skill:
    name: str
    body: str
    path: Path
    description: str = ""
    roles: Optional[set] = None  # None = 全部角色
    meta: Dict[str, object] = field(default_factory=dict)

    def applies_to(self, role: Optional[str]) -> bool:
        if self.roles is None:
            return True
        return (role or ROLE_AGENT) in self.roles


_FRONTMATTER_RE = re.compile(r"\A---[ \t]*\r?\n(.*?)\r?\n---[ \t]*\r?\n?", re.DOTALL)


def _parse_scalar(raw: str):
    raw = raw.strip()
    if not raw:
        return ""
    if raw.startswith("[") and raw.endswith("]"):
        inner = raw[1:-1].strip()
        return [x.strip().strip("'\"") for x in inner.split(",") if x.strip()] if inner else []
    return raw.strip("'\"")


def parse_frontmatter(text: str) -> Tuple[Dict[str, object], str]:
    """解析 YAML frontmatter 子集，返回 ``(meta, body)``；无 frontmatter 时 meta 为空。"""
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return {}, text
    meta: Dict[str, object] = {}
    current_list_key: Optional[str] = None
    for line in m.group(1).splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        stripped = line.strip()
        if stripped.startswith("- ") and current_list_key:
            meta.setdefault(current_list_key, [])
            lst = meta[current_list_key]
            if isinstance(lst, list):
                lst.append(stripped[2:].strip().strip("'\""))
            continue
        if ":" not in stripped:
            continue
        key, _, value = stripped.partition(":")
        key = key.strip()
        value = value.strip()
        if not value:
            # 块列表开头：下面的 "- item" 行归属该键
            meta[key] = []
            current_list_key = key
            continue
        current_list_key = None
        meta[key] = _parse_scalar(value)
    return meta, text[m.end():]


def _normalize_roles(value) -> Optional[set]:
    if value is None:
        return None
    if isinstance(value, str):
        if value.strip().lower() in ("", "all", "*"):
            return None
        value = [value]
    roles = {str(v).strip().lower() for v in value if str(v).strip()}
    if not roles or "all" in roles or "*" in roles:
        return None
    return roles


def _load_skill_file(path: Path, default_name: str) -> Optional[Skill]:
    text = _read_text(path)
    if text is None:
        return None
    meta, body = parse_frontmatter(text)
    body = body.strip()
    if not body:
        return None
    name = str(meta.get("name") or default_name).strip() or default_name
    return Skill(
        name=name,
        body=body,
        path=path,
        description=str(meta.get("description") or "").strip(),
        roles=_normalize_roles(meta.get("roles")),
        meta=meta,
    )


def load_skills() -> List[Skill]:
    """加载全部 Skill：目录内按子目录名排序；跨层同名后者覆盖前者。"""
    by_name: Dict[str, Skill] = {}
    order: List[str] = []
    for d in prompt_dirs():
        skills_dir = d / SKILLS_SUBDIR
        if not skills_dir.is_dir():
            continue
        for sub in sorted(p for p in skills_dir.iterdir() if p.is_dir()):
            f = sub / SKILL_FILENAME
            if not f.is_file():
                continue
            skill = _load_skill_file(f, sub.name)
            if skill is None:
                continue
            if skill.name not in by_name:
                order.append(skill.name)
            by_name[skill.name] = skill
    return [by_name[n] for n in order]


def skills_enabled() -> bool:
    return os.environ.get(ENV_SKILLS_ENABLED, "on").strip().lower() not in _FALSY


def skill_max_chars() -> int:
    try:
        return max(200, int(os.environ.get(ENV_SKILL_MAX_CHARS, DEFAULT_SKILL_MAX_CHARS)))
    except ValueError:
        return DEFAULT_SKILL_MAX_CHARS


def render_skills(role: Optional[str] = None, max_chars: Optional[int] = None,
                  skills: Optional[Iterable[Skill]] = None) -> str:
    """把适用于 ``role`` 的 Skill 正文拼成一段文本（超出上限截断并标注）；无适用项返回空串。"""
    if skills is None:
        if not skills_enabled():
            return ""
        skills = load_skills()
    role = (role or ROLE_AGENT).strip().lower()
    parts = [s.body.strip() for s in skills if s.applies_to(role) and s.body.strip()]
    if not parts:
        return ""
    text = "\n\n".join(parts)
    limit = skill_max_chars() if max_chars is None else int(max_chars)
    if len(text) > limit:
        text = text[:limit] + "\n…(skills truncated)"
    return text


def describe() -> Dict[str, object]:
    """诊断信息（供 CLI/Web 展示）：目录、项目规范路径、已加载 Skill 列表。"""
    rules = project_rules_path()
    return {
        "dirs": [str(d) for d in prompt_dirs()],
        "project_rules": str(rules) if rules else None,
        "skills_enabled": skills_enabled(),
        "skill_max_chars": skill_max_chars(),
        "skills": [
            {
                "name": s.name,
                "description": s.description,
                "roles": sorted(s.roles) if s.roles else "all",
                "path": str(s.path),
                "chars": len(s.body),
            }
            for s in load_skills()
        ],
    }
