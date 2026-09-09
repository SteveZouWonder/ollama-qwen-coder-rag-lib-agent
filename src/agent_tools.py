#!/usr/bin/env python3
"""
Agent 工具链实现 - 带安全确认 + RAG 知识库集成
"""
import os
import shlex
import subprocess
import json
import re
from typing import Any, Callable, Dict, List, Optional

# ========== RAG 引擎引用（由外部注入）==========
_rag_engine = None

def set_rag_engine(engine):
    """注入 RAG 引擎实例，供知识库工具使用"""
    global _rag_engine
    _rag_engine = engine

# ========== 工具注册中心 ==========

class ToolRegistry:
    """工具注册中心"""
    def __init__(self):
        self.tools: Dict[str, Dict] = {}

    def register(self, name: str, func: Callable, description: str, params: Dict[str, str], safe: bool = True):
        self.tools[name] = {
            "function": func,
            "description": description,
            "parameters": params,
            "safe": safe
        }

    def get_descriptions(self, names=None, compact: bool = False) -> str:
        """生成工具说明文本。

        Args:
            names: 只包含这些工具（None 表示全部）。用于按 Agent 角色限定工具集。
            compact: 紧凑格式——每个工具一行 ``name(参数, ...): 描述``，用于精简
                内置系统提示，token 约为完整格式的 1/2。
        """
        selected = [
            (n, info) for n, info in self.tools.items()
            if names is None or n in names
        ]
        if compact:
            lines = []
            for name, info in selected:
                params = []
                for k, v in info["parameters"].items():
                    params.append(k if "必填" in str(v) else f"{k}?")
                tag = "" if info["safe"] else " [需确认]"
                lines.append(f"- {name}({', '.join(params)}): {info['description']}{tag}")
            return "\n".join(lines)
        lines = ["=== 可用工具 ==="]
        for name, info in selected:
            safe_tag = "[安全]" if info["safe"] else "[需确认]"
            lines.append("")
            lines.append(safe_tag + " 工具名: " + name)
            lines.append("    描述: " + info['description'])
            param_lines = []
            for k, v in info["parameters"].items():
                param_lines.append("      - " + k + ": " + v)
            if param_lines:
                lines.append("    参数:")
                lines.extend(param_lines)
            else:
                lines.append("    参数: 无")
            if info['parameters']:
                first_key = list(info['parameters'].keys())[0]
                example = '    调用格式: Action: ' + name + '\n    Action Input: {"' + first_key + '": "值"}'
            else:
                example = '    调用格式: Action: ' + name + '\n    Action Input: {}'
            lines.append(example)
        return "\n".join(lines)

    def execute(self, name: str, args: Dict, auto_confirm: bool = False) -> str:
        if name not in self.tools:
            return "[错误] 未知工具: " + name
        tool = self.tools[name]
        try:
            if not tool["safe"] and not auto_confirm:
                return "[CONFIRM_REQUIRED] " + name + "|" + json.dumps(args, ensure_ascii=False)
            result = tool["function"](**args)
            return str(result)[:5000]
        except Exception as e:
            return "[错误] 工具执行失败: " + str(e)

    def list_tools(self) -> List[str]:
        return list(self.tools.keys())

# ========== 命令安全分析 ==========

class CommandSafetyChecker:
    """命令安全分析器。

    风险分级（由高到低）：
    - ``critical``：匹配 ``DANGEROUS_PATTERNS``，直接拦截不执行；
    - ``high``：匹配 ``HIGH_PATTERNS``（如 ``curl … | sh`` 远程脚本直执行）或**子命令首 token**
      属于破坏性命令（``HIGH_COMMANDS``），需确认；
    - ``medium``：匹配 ``MEDIUM_PATTERNS``（安装依赖、git 写操作、运行脚本、make、docker run/exec）
      或**子命令首 token**属于修改类命令（``MEDIUM_COMMANDS``），需确认；
    - ``low``：只读命令（全部子命令都只读）或其余命令，免确认。

    关键字匹配为 **token 级**（F10 P0-1-a）：命令先按 ``|`` / ``&&`` / ``||`` / ``;``
    切成子命令，各取首 token（剥掉 ``sudo`` / ``env VAR=`` / ``xargs`` 等透明前缀、
    取 basename）后再比对关键字集合。因此 ``pip show models``、``ls performance/``、
    ``git log --format=%H`` 不会再因含 ``del`` / ``rm`` / ``format`` 子串被误判。
    """

    DANGEROUS_PATTERNS = [
        r"rm\s+-rf\s+/", r"rm\s+-rf\s+/\*", r"dd\s+if=/dev/zero",
        r"mkfs\.", r">\s*/dev/sda", r"chmod\s+777\s+/",
        r"sudo\s+rm",
        r"del\s+/f\s+/s\s+/q", r"format\s+", r":\(\)\{\s*:\|:&\s*\};:",
        r"mv\s+/\s+", r"cp\s+/\s+", r"ln\s+-sf\s+/",
    ]

    # 高风险（需确认，但不直接拦截）：下载远程脚本直接交给 shell 执行
    HIGH_PATTERNS = [
        r"\b(curl|wget)\b.*\|\s*(sudo\s+)?(sh|bash|zsh)\b",
    ]

    # 中风险（需确认）：会改变环境/仓库/运行任意代码，但不具破坏性
    MEDIUM_PATTERNS = [
        r"\b(pip3?|npm|yarn|pnpm|brew|apt(-get)?)\s+install\b",
        r"\bgit\s+(push|commit|reset|checkout|rebase|merge)\b",
        r"\bpython3?\s+(\S+/)?\S+\.py\b",
        r"\bnode\s+(\S+/)?\S+\.js\b",
        r"(^|[;&|]\s*)make\b",
        r"\bdocker\s+(run|exec)\b",
    ]

    READONLY_PATTERNS = [
        r"^ls\b", r"^pwd\b", r"^echo\b", r"^cat\b", r"^head\b",
        r"^tail\b", r"^find\b", r"^grep\b", r"^wc\b", r"^ps\b",
        r"^which\b", r"^whereis\b", r"^uname\b", r"^whoami\b",
        r"^date\b", r"^df\b", r"^du\b", r"^top\b", r"^htop\b",
        r"^git\s+status\b", r"^git\s+log\b", r"^git\s+diff\b",
        r"^git\s+branch\b", r"^git\s+remote\b", r"^git\s+show\b",
        r"^python\s+-m\s+pytest\s+--collect-only\b",
        r"^pip\s+list\b", r"^pip\s+freeze\b",
        r"^ollama\s+list\b", r"^ollama\s+ps\b",
        r"^tree\b", r"^file\b", r"^stat\b",
    ]

    # ---------- token 级关键字集合（F10 P0-1-a）----------

    # 子命令分隔符：其后的 token 视为新子命令的首 token
    SUBCOMMAND_SEPARATORS = frozenset({"|", "||", "&&", ";", "&", "|&"})

    # 透明前缀：本身不是"要执行的命令"，剥掉后继续看下一个 token
    TRANSPARENT_PREFIXES = frozenset({
        "sudo", "doas", "env", "xargs", "nohup", "time", "command", "builtin", "exec", "nice", "ionice",
    })

    # 透明前缀的带值选项：其后一个 token 是选项值而非命令名（如 ``sudo -u root rm x``）
    PREFIX_FLAGS_WITH_VALUE = frozenset({
        "-u", "-g", "-p", "-n", "-P", "-I", "-i", "-d", "-a", "-r", "-s", "-C", "-L", "-D",
        "--user", "--group", "--prompt", "--max-procs", "--max-args", "--replace", "--delimiter",
    })

    # 首 token 命中即 high：破坏性删除 / 格式化
    HIGH_COMMANDS = frozenset({
        "rm", "rmdir", "del", "erase", "rd", "drop", "truncate", "format", "mkfs", "shred",
    })

    # 首 token 命中即 medium：会修改文件 / 权限但不具破坏性
    MEDIUM_COMMANDS = frozenset({"mv", "cp", "chmod", "chown", "tee", "dd"})

    # 需要特定参数才算 medium 的命令：命令名 → 必须出现的参数
    MEDIUM_COMMANDS_WITH_FLAG = {"sed": "-i"}

    # SQL 客户端：其后的 token 里出现 SQL 写关键字才计入（避免把 "insert" 当命令名）
    SQL_CLIENTS = frozenset({"sqlite3", "sqlite", "psql", "mysql", "mariadb", "mongosh", "duckdb"})
    SQL_HIGH_KEYWORDS = frozenset({"drop", "truncate"})
    SQL_MEDIUM_KEYWORDS = frozenset({"insert", "update", "delete", "alter", "replace"})

    # 把下一个 token 当作嵌套命令 / SQL 载荷的参数
    INLINE_SCRIPT_FLAGS = frozenset({"-c", "-e", "--command", "--execute"})

    _RISK_ORDER = {"low": 0, "medium": 1, "high": 2}

    @classmethod
    def _tokenize(cls, command: str) -> List[str]:
        """分词。``shlex``（保留引号语义、把 ``|`` / ``&&`` 切成独立 token）失败时回退空白切分。"""
        try:
            lexer = shlex.shlex(command, posix=True, punctuation_chars=True)
            lexer.whitespace_split = True
            return list(lexer)
        except ValueError:
            return [t for t in re.split(r"\s+", command.strip()) if t]

    @classmethod
    def _split_subcommands(cls, tokens: List[str]) -> List[List[str]]:
        """按管道 / 逻辑连接符把 token 列表切成子命令。"""
        groups: List[List[str]] = [[]]
        for tok in tokens:
            if tok in cls.SUBCOMMAND_SEPARATORS:
                groups.append([])
            else:
                groups[-1].append(tok)
        return [g for g in groups if g]

    @classmethod
    def _head(cls, tokens: List[str]) -> str:
        """取子命令真正的命令名：剥掉透明前缀与 ``VAR=value`` 赋值，再取 basename、转小写。"""
        skip_next = False
        for tok in tokens:
            if skip_next:  # 上一个是带值选项，本 token 是它的值
                skip_next = False
                continue
            base = os.path.basename(tok).lower()
            if base in cls.TRANSPARENT_PREFIXES:
                continue
            if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", tok):
                continue
            if tok.startswith("-"):  # 透明前缀自己的选项（如 sudo -u root）
                skip_next = tok.lower() in cls.PREFIX_FLAGS_WITH_VALUE
                continue
            return base
        return ""

    @classmethod
    def _sql_risk(cls, head: str, rest: List[str]) -> Optional[str]:
        """SQL 写操作风险：仅在 SQL 客户端或带 ``-c`` / ``-e`` 载荷的命令中判定。"""
        has_inline = any(t.lower() in cls.INLINE_SCRIPT_FLAGS for t in rest)
        if head not in cls.SQL_CLIENTS and not has_inline:
            return None
        words = {w.lower() for tok in rest for w in re.findall(r"[A-Za-z_]+", tok)}
        if words & cls.SQL_HIGH_KEYWORDS:
            return "high"
        if words & cls.SQL_MEDIUM_KEYWORDS:
            return "medium"
        return None

    @classmethod
    def _subcommand_risk(cls, tokens: List[str], depth: int = 0) -> Optional[str]:
        """单个子命令的关键字风险（``None`` 表示关键字集合未命中）。"""
        head = cls._head(tokens)
        if not head:
            return None
        rest = [t for t in tokens if os.path.basename(t).lower() != head]
        risks: List[str] = []

        if head in cls.HIGH_COMMANDS:
            risks.append("high")
        if head in cls.MEDIUM_COMMANDS:
            risks.append("medium")
        flag = cls.MEDIUM_COMMANDS_WITH_FLAG.get(head)
        if flag and flag in rest:
            risks.append("medium")

        sql = cls._sql_risk(head, rest)
        if sql:
            risks.append(sql)

        # ``bash -c '<cmd>'`` / ``sh -c`` 等：载荷本身也按首 token 判级（限一层，防递归爆炸）
        if depth < 2:
            for idx, tok in enumerate(rest):
                if tok.lower() in cls.INLINE_SCRIPT_FLAGS and idx + 1 < len(rest):
                    for sub in cls._split_subcommands(cls._tokenize(rest[idx + 1])):
                        nested = cls._subcommand_risk(sub, depth + 1)
                        if nested:
                            risks.append(nested)
        if not risks:
            return None
        return max(risks, key=lambda r: cls._RISK_ORDER[r])

    @classmethod
    def keyword_risk(cls, command: str) -> Optional[str]:
        """整条命令的 token 级关键字风险：取各子命令的最高风险，未命中返回 ``None``。"""
        risks = [
            r for sub in cls._split_subcommands(cls._tokenize(command or ""))
            if (r := cls._subcommand_risk(sub)) is not None
        ]
        if not risks:
            return None
        return max(risks, key=lambda r: cls._RISK_ORDER[r])

    @classmethod
    def is_readonly_command(cls, command: str) -> bool:
        """是否只读：**全部**子命令都匹配 ``READONLY_PATTERNS``。

        整条匹配（旧行为）会让 ``ls | xargs rm`` 因 ``^ls`` 被放行，故改为逐子命令判定。
        """
        subs = cls._split_subcommands(cls._tokenize(command or ""))
        if not subs:
            return False
        for sub in subs:
            text = " ".join(sub)
            if not any(re.search(p, text, re.IGNORECASE) for p in cls.READONLY_PATTERNS):
                return False
        return True

    @classmethod
    def analyze(cls, command: str) -> Dict[str, Any]:
        result = {
            "command": command,
            "is_dangerous": False,
            "danger_reasons": [],
            "is_readonly": False,
            "needs_confirm": True,
            "risk_level": "unknown",
        }

        for pattern in cls.DANGEROUS_PATTERNS:
            if re.search(pattern, command, re.IGNORECASE):
                result["is_dangerous"] = True
                result["danger_reasons"].append("匹配危险模式: " + pattern)

        result["is_readonly"] = cls.is_readonly_command(command)
        keyword = cls.keyword_risk(command)

        if result["is_dangerous"]:
            result["risk_level"] = "critical"
            result["needs_confirm"] = True
        elif result["is_readonly"]:
            result["risk_level"] = "low"
            result["needs_confirm"] = False
        elif any(re.search(p, command, re.IGNORECASE) for p in cls.HIGH_PATTERNS):
            result["risk_level"] = "high"
            result["needs_confirm"] = True
        elif keyword == "high":
            result["risk_level"] = "high"
            result["needs_confirm"] = True
        elif any(re.search(p, command, re.IGNORECASE) for p in cls.MEDIUM_PATTERNS):
            result["risk_level"] = "medium"
            result["needs_confirm"] = True
        elif keyword == "medium":
            result["risk_level"] = "medium"
            result["needs_confirm"] = True
        else:
            result["risk_level"] = "low"
            result["needs_confirm"] = False

        return result


# ========== 自动确认闸门（AUTO_CONFIRM 只放行 low / medium）==========

# ``CODE_AGENT_AUTO_CONFIRM`` 能免除人工确认的风险等级；high / critical 一律需人工确认。
# 与 ``agents.base_agent.ReActDelegateAgent.AUTO_CONFIRM_RISK_LEVELS`` 保持同一口径。
AUTO_CONFIRM_RISK_LEVELS = ("low", "medium")
HIGH_RISK_CONFIRM_HINT = "[提示] 高风险命令需人工确认"


def auto_confirm_allows(safety: Optional[Dict[str, Any]] = None) -> bool:
    """``AUTO_CONFIRM`` 开启时，该命令是否可以免人工确认。

    Args:
        safety: ``CommandSafetyChecker.analyze`` 的结果。为 ``None`` / 空字典时表示
            调用方没有命令风险信息（如 ``write_file`` 等非命令类工具），沿用
            registry 的 ``safe`` 标记，返回 ``True``。

    Returns:
        ``risk_level`` 属于 :data:`AUTO_CONFIRM_RISK_LEVELS` 且未被判定为危险时为 ``True``。
    """
    if not safety:
        return True
    if safety.get("is_dangerous"):
        return False
    return safety.get("risk_level", "unknown") in AUTO_CONFIRM_RISK_LEVELS


# ========== 读 / 写路径边界 ==========

WRITE_ALLOWED_DIRS_ENV = "WRITE_ALLOWED_DIRS"
READ_ALLOWED_DIRS_ENV = "READ_ALLOWED_DIRS"
PATH_OUT_OF_SCOPE_ERROR = "[错误] 路径超出允许范围"
# 错误提示里最多列出几个允许目录（更多的折叠为"等 N 个"，避免刷屏）
_SCOPE_HINT_MAX_DIRS = 5


def _is_subpath(child: str, parent: str) -> bool:
    return child == parent or child.startswith(parent.rstrip(os.sep) + os.sep)


def _normalize_dirs(dirs) -> List[str]:
    """展开 ``~``、解析符号链接与 ``..``，按原顺序去重，并丢弃被其他目录包含的子目录。

    ``cwd`` 已覆盖 ``cwd/sub``，再单独列出只会让 ``/config`` / 系统页的目录列表越来越长。
    """
    seen: List[str] = []
    for d in dirs:
        if not d or not str(d).strip():
            continue
        real = os.path.realpath(os.path.expanduser(str(d).strip()))
        if any(_is_subpath(real, kept) for kept in seen):
            continue
        seen = [kept for kept in seen if not _is_subpath(kept, real)]
        seen.append(real)
    return seen


def _upload_root() -> str:
    """Web 上传文件的临时根目录（Gradio：``$GRADIO_TEMP_DIR`` 或 ``<tmp>/gradio``）。"""
    import tempfile

    return os.path.realpath(os.getenv("GRADIO_TEMP_DIR") or os.path.join(tempfile.gettempdir(), "gradio"))


def write_allowed_dirs() -> List[str]:
    """允许写入/入库的目录：当前工作目录 + ``WRITE_ALLOWED_DIRS``（冒号分隔）。"""
    dirs = [os.getcwd()]
    dirs.extend(os.getenv(WRITE_ALLOWED_DIRS_ENV, "").split(":"))
    return _normalize_dirs(dirs)


def _indexed_document_dirs() -> List[str]:
    """已入库文件所在的目录（去重）。

    知识库文档常在工作区之外（``~/Documents/论文.pdf``），既然用户已显式入库，
    Agent 就应能读回原文；元数据不可用时忽略该来源。

    Web 上传的文件落在 Gradio 临时根下的随机哈希目录（每个文件一个），逐个列出会让允许目录
    越积越多；这些都是用户自己上传的内容，统一折叠为上传根目录一条。
    """
    try:
        from file_metadata import get_global_metadata_manager

        manager = get_global_metadata_manager()
        upload_root = _upload_root()
        dirs: List[str] = []
        for fm in manager.list_files():
            path = getattr(fm, "file_path", "")
            if not path:
                continue
            d = os.path.realpath(os.path.dirname(os.path.abspath(path)))
            dirs.append(upload_root if _is_subpath(d, upload_root) else d)
        return dirs
    except Exception:  # noqa: BLE001 - 元数据缺失/损坏不应影响读操作可用性
        return []


def read_allowed_dirs() -> List[str]:
    """允许读取的目录：写允许目录 ∪ ``READ_ALLOWED_DIRS`` ∪ 已入库文件所在目录。"""
    dirs = list(write_allowed_dirs())
    dirs.extend(os.getenv(READ_ALLOWED_DIRS_ENV, "").split(":"))
    dirs.extend(_indexed_document_dirs())
    return _normalize_dirs(dirs)


def _within(path: str, bases: List[str]) -> bool:
    if not path or not str(path).strip():
        return False
    real = os.path.realpath(os.path.abspath(os.path.expanduser(str(path))))
    for base in bases:
        if real == base or real.startswith(base.rstrip(os.sep) + os.sep):
            return True
    return False


def is_path_allowed(path: str) -> bool:
    """路径（解析符号链接与 ``..`` 后）是否位于允许**写入**的目录内。"""
    return _within(path, write_allowed_dirs())


def is_read_allowed(path: str) -> bool:
    """路径（解析符号链接与 ``..`` 后）是否位于允许**读取**的目录内。"""
    return _within(path, read_allowed_dirs())


def _format_dirs(dirs: List[str]) -> str:
    shown = dirs[:_SCOPE_HINT_MAX_DIRS]
    text = "、".join(shown)
    if len(dirs) > len(shown):
        text += f" 等 {len(dirs)} 个目录"
    return text


def path_scope_error(path: str) -> str:
    return (f"{PATH_OUT_OF_SCOPE_ERROR}: {path}（仅允许 {os.getcwd()} "
            f"或环境变量 {WRITE_ALLOWED_DIRS_ENV} 指定的目录）")


def read_scope_error(path: str) -> str:
    return (f"{PATH_OUT_OF_SCOPE_ERROR}: {path}（允许读取 {_format_dirs(read_allowed_dirs())}；"
            f"可设置环境变量 {READ_ALLOWED_DIRS_ENV} 放行）")

# ========== 具体工具实现 ==========

def read_file(path: str, offset: int = 0, limit: int = 100) -> str:
    path = os.path.expanduser(str(path or ""))
    if not is_read_allowed(path):
        return read_scope_error(path)
    if not os.path.exists(path):
        return "[错误] 文件不存在: " + path
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
            if not lines:
                return "[文件为空]"
            start = max(0, offset)
            end = min(start + limit, len(lines))
            selected = lines[start:end]
            result = "".join(selected)
            info = "[文件: " + path + " | 总行数: " + str(len(lines)) + " | 显示: " + str(start+1) + "-" + str(end) + "]\n"
            if end < len(lines):
                result = result + "\n... (" + str(len(lines) - end) + " 行省略) ..."
            return info + result
    except Exception as e:
        return "[错误] 读取失败: " + str(e)

def write_file(path: str, content: str, append: bool = False) -> str:
    path = os.path.expanduser(str(path or ""))
    if not is_path_allowed(path):
        return path_scope_error(path)
    try:
        abs_path = os.path.abspath(path)
        parent = os.path.dirname(abs_path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        mode = "a" if append else "w"
        with open(abs_path, mode, encoding="utf-8") as f:
            f.write(content)
        action = "追加" if append else "写入"
        return "[成功] " + action + " " + abs_path + "，共 " + str(len(content)) + " 字符"
    except Exception as e:
        return "[错误] 写入失败: " + str(e)

def execute_command(command: str, timeout: int = 30) -> str:
    try:
        result = subprocess.run(
            command,
            shell=True,  # nosec B602
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=os.getcwd()
        )
        output = []
        if result.stdout:
            output.append(result.stdout)
        if result.stderr:
            output.append("[stderr] " + result.stderr)
        if result.returncode != 0:
            output.append("[退出码] " + str(result.returncode))
        return "\n".join(output)[:4000]
    except subprocess.TimeoutExpired:
        return "[错误] 命令超时 (> " + str(timeout) + "s): " + command
    except Exception as e:
        return "[错误] 执行失败: " + str(e)

def list_directory(path: str = ".") -> str:
    path = os.path.expanduser(str(path or "."))
    if not is_read_allowed(path):
        return read_scope_error(path)
    if not os.path.exists(path):
        return "[错误] 目录不存在: " + path
    try:
        items = os.listdir(path)
        lines = ["[目录] " + os.path.abspath(path)]
        dirs = []
        files = []
        for item in sorted(items):
            if item.startswith("."):
                continue
            full = os.path.join(path, item)
            if os.path.isdir(full):
                dirs.append("  [D] " + item + "/")
            else:
                files.append("  [F] " + item)
        lines.extend(dirs)
        lines.extend(files)
        return "\n".join(lines)
    except Exception as e:
        return "[错误] " + str(e)

def analyze_project_structure(project_path: str = ".") -> str:
    """分析项目结构，提供项目概览"""
    project_path = os.path.expanduser(str(project_path or "."))
    if not is_read_allowed(project_path):
        return read_scope_error(project_path)
    if not os.path.exists(project_path):
        return "[错误] 项目路径不存在: " + project_path
    if not os.path.isdir(project_path):
        return "[错误] 提供的路径不是目录: " + project_path
    
    try:
        analysis = {
            "project_path": os.path.abspath(project_path),
            "structure": {},
            "key_files": [],
            "tech_stack": []
        }
        
        # 列出根目录内容
        items = os.listdir(project_path)
        dirs = [item for item in items if os.path.isdir(os.path.join(project_path, item)) and not item.startswith(".")]
        files = [item for item in items if os.path.isfile(os.path.join(project_path, item)) and not item.startswith(".")]
        
        analysis["structure"]["root_directories"] = dirs
        analysis["structure"]["root_files"] = files
        
        # 识别关键文件
        key_files = []
        tech_indicators = {
            "package.json": "JavaScript/Node.js",
            "requirements.txt": "Python",
            "setup.py": "Python",
            "pyproject.toml": "Python",
            "Cargo.toml": "Rust",
            "go.mod": "Go",
            "pom.xml": "Java/Maven",
            "build.gradle": "Java/Gradle",
            "Gemfile": "Ruby",
            "composer.json": "PHP",
            "README.md": "Documentation",
            "README.rst": "Documentation",
            "Dockerfile": "Docker",
            "docker-compose.yml": "Docker",
            "Makefile": "Make",
            "CMakeLists.txt": "CMake",
        }
        
        for file in files:
            if file in tech_indicators:
                key_files.append(file)
                if tech_indicators[file] not in analysis["tech_stack"]:
                    analysis["tech_stack"].append(tech_indicators[file])
        
        analysis["key_files"] = key_files
        
        # 分析主要目录
        dir_analysis = {}
        for dir_name in dirs[:10]:  # 限制分析前10个目录
            dir_path = os.path.join(project_path, dir_name)
            try:
                sub_items = os.listdir(dir_path)
                sub_files = [item for item in sub_items if os.path.isfile(os.path.join(dir_path, item))]
                sub_dirs = [item for item in sub_items if os.path.isdir(os.path.join(dir_path, item))]
                dir_analysis[dir_name] = {
                    "files_count": len(sub_files),
                    "dirs_count": len(sub_dirs),
                    "sample_files": sub_files[:5]
                }
            except PermissionError:
                dir_analysis[dir_name] = {"error": "权限不足"}
        
        analysis["structure"]["directory_details"] = dir_analysis
        
        # 格式化输出
        lines = ["=== 项目结构分析 ==="]
        lines.append(f"项目路径: {analysis['project_path']}")
        lines.append(f"根目录数: {len(dirs)}")
        lines.append(f"根文件数: {len(files)}")
        lines.append(f"\n主要目录: {', '.join(dirs)}")
        lines.append(f"主要文件: {', '.join(files)}")
        lines.append(f"\n识别的技术栈: {', '.join(analysis['tech_stack']) if analysis['tech_stack'] else '未知'}")
        lines.append(f"\n关键文件: {', '.join(key_files) if key_files else '无'}")
        lines.append(f"\n目录详情:")
        for dir_name, details in dir_analysis.items():
            if "error" not in details:
                lines.append(f"  {dir_name}/: {details['files_count']} 文件, {details['dirs_count']} 子目录")
            else:
                lines.append(f"  {dir_name}/: {details['error']}")
        
        return "\n".join(lines)
    except Exception as e:
        return "[错误] 分析项目结构失败: " + str(e)

# 文本搜索的文件后缀 / 跳过目录（``search_files`` 与 Web 工作区搜索共用）
SEARCH_FILE_EXTS = frozenset({".py", ".js", ".java", ".ts", ".go", ".rs", ".c", ".cpp", ".h", ".md", ".txt",
                              ".json", ".yaml", ".yml", ".sql", ".sh"})
SEARCH_SKIP_DIRS = frozenset({".git", "node_modules", "__pycache__", "venv", ".venv", "dist", "build", ".idea",
                              ".vscode"})


def search_files(query: str, path: str = ".", max_results: int = 10) -> str:
    path = os.path.expanduser(str(path or "."))
    if not is_read_allowed(path):
        return read_scope_error(path)
    results = []
    exts = SEARCH_FILE_EXTS
    skip_dirs = SEARCH_SKIP_DIRS

    try:
        for root, dirs, files in os.walk(path):
            dirs[:] = [d for d in dirs if d not in skip_dirs and not d.startswith(".")]
            for file in files:
                if any(file.endswith(ext) for ext in exts):
                    filepath = os.path.join(root, file)
                    try:
                        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                            content = f.read()
                            if query in content:
                                lines = content.split("\n")
                                matches = []
                                for i, line in enumerate(lines):
                                    if query in line:
                                        matches.append("    行" + str(i+1) + ": " + line.strip())
                                    if len(matches) >= 3:
                                        break
                                results.append("[匹配] " + filepath + "\n" + "\n".join(matches))
                                if len(results) >= max_results:
                                    break
                    except:
                        continue
                if len(results) >= max_results:
                    break
        if not results:
            return "[结果] 未找到包含 '" + query + "' 的文件"
        return "\n\n".join(results)
    except Exception as e:
        return "[错误] " + str(e)

def get_current_dir() -> str:
    return os.getcwd()

# ========== RAG 知识库工具 ==========

# query_knowledge_base 返回给模型的片段数与每条片段最大字符数
KB_TOOL_TOP_K = 3
KB_TOOL_SNIPPET_CHARS = 300
KB_NO_RELEVANT_MARK = "[知识库无相关内容]"


def format_kb_tool_result(result: Dict[str, Any]) -> str:
    """把 ``rag_pipeline.answer_question`` 的结果渲染为回灌模型的文本。

    命中：``答案 + 相关性结论 + top-3 片段原文（每条 ≤300 字，含文件名）``；
    未命中：``[知识库无相关内容]``（内置提示据此引导模型转 web_search）；
    元查询（"知识库里有什么"）：文件清单概览。
    """
    if not isinstance(result, dict):
        return KB_NO_RELEVANT_MARK
    if result.get("kind") == "meta":
        meta = result.get("meta") or {}
        files = meta.get("files") or []
        stats = meta.get("stats") or {}
        lines = ["[知识库概览]"]
        if stats:
            doc_count = stats.get("total_documents", stats.get("document_count"))
            if doc_count is not None:
                lines.append(f"文档块数: {doc_count}")
        if files:
            lines.append(f"文件 {len(files)} 个：")
            for f in files[:20]:
                lines.append(f"- {os.path.basename(str(f.get('path', '')))} ({f.get('size', '?')})")
            if len(files) > 20:
                lines.append(f"…另有 {len(files) - 20} 个文件")
        else:
            lines.append("知识库中暂无文件")
        return "\n".join(lines)

    sources = [s for s in (result.get("kb_sources") or []) if isinstance(s, dict)]
    if not sources:
        return (f"{KB_NO_RELEVANT_MARK} 知识库中没有与该问题相关的文档"
                "（已按相关性阈值与模型判定过滤）。请改用 web_search，或基于自身知识回答并说明来源。")

    scores = [float(s["score"]) for s in sources if isinstance(s.get("score"), (int, float))]
    top = f"，最高相关度 {max(scores):.2f}" if scores else ""
    lines = [
        f"[知识库命中] 相关性判定：通过（{len(sources)} 个相关片段{top}）",
        "",
    ]
    # F9 P0-5：warn 级 notice 以 [注意] 行附在答案前（模型可见）
    for n in result.get("notices") or []:
        if isinstance(n, dict) and n.get("level") == "warn" and n.get("text"):
            lines.append(f"[注意] {n['text']}")
    # F9 P0-3：引用校验发现无效编号时提醒模型
    check = result.get("citation_check")
    if isinstance(check, dict) and check.get("invalid"):
        lines.append("（注意：回答中 [?] 为无效引用）")
    lines.extend([
        "答案：",
        (result.get("answer") or "").strip() or "（无综合答案）",
        "",
        f"相关片段（top-{min(KB_TOOL_TOP_K, len(sources))}，原文）：",
    ])
    for i, src in enumerate(sources[:KB_TOOL_TOP_K], 1):
        name = src.get("file") or src.get("file_name") or os.path.basename(str(src.get("path") or "")) or "未知"
        text = str(src.get("content") or src.get("text") or "").strip()
        text = re.sub(r"\s+", " ", text)
        if len(text) > KB_TOOL_SNIPPET_CHARS:
            text = text[:KB_TOOL_SNIPPET_CHARS] + "…"
        score = src.get("score")
        score_s = f"（相关度 {float(score):.2f}）" if isinstance(score, (int, float)) else ""
        # 代码块附 符号 · 行号：模型可据此 read_file 精确读取该行段
        loc = ""
        if src.get("symbol"):
            loc += f" {src['symbol']}"
        if src.get("start_line") is not None:
            loc += f" L{src['start_line']}-{src.get('end_line') or src['start_line']}"
        label = f"[{name}{' ·' + loc if loc else ''}]"
        lines.append(f"{i}. {label}{score_s} {text or '（无正文）'}")
    return "\n".join(lines)


def query_knowledge_base(question: str) -> str:
    """查询个人知识库（PDF、论文、笔记等）。

    与 RAG 模式走同一条管道（``rag_pipeline.answer_question``：0.45 相关性阈值 +
    模型相关性判定），只取知识库结论、不联网、不兜底；返回"答案 + 相关性结论 +
    top-3 片段原文"，不相关时返回 ``[知识库无相关内容]``。
    """
    if _rag_engine is None:
        return "[错误] 知识库引擎未初始化"
    try:
        from rag_pipeline import answer_question
        result = answer_question(
            _rag_engine, question,
            enable_web_search=False, show_progress=False, kb_only=True,
        )
        return format_kb_tool_result(result)
    except Exception as e:
        return "[错误] 知识库查询失败: " + str(e)

def add_to_knowledge_base(file_path: str) -> str:
    """将文档添加到知识库"""
    if _rag_engine is None:
        return "[错误] 知识库引擎未初始化"
    if not is_path_allowed(file_path):
        return path_scope_error(file_path)
    try:
        return _rag_engine.add_document_tool(file_path)
    except Exception as e:
        return "[错误] 添加文档失败: " + str(e)

def get_knowledge_stats() -> str:
    """获取知识库统计信息"""
    if _rag_engine is None:
        return "[错误] 知识库引擎未初始化"
    try:
        return _rag_engine.get_stats_tool()
    except Exception as e:
        return "[错误] 获取统计信息失败: " + str(e)

def check_knowledge_status() -> str:
    """检查知识库状态，包括持久化和数据情况"""
    if _rag_engine is None:
        return "[错误] 知识库引擎未初始化"
    try:
        from pathlib import Path
        from config import INDEX_DIR
        
        status_info = []
        status_info.append("=== 知识库状态检查 ===")
        
        # 检查持久化目录
        index_dir = Path(INDEX_DIR)
        if index_dir.exists():
            status_info.append(f"✅ 持久化目录存在: {index_dir}")
            status_info.append(f"   - ChromaDB: {index_dir / 'chroma_db'}")
            status_info.append(f"   - LlamaIndex: {index_dir / 'llama_index'}")
        else:
            status_info.append(f"❌ 持久化目录不存在: {index_dir}")
        
        # 检查数据量
        try:
            doc_count = _rag_engine.chroma_collection.count()
            status_info.append(f"✅ 向量数据库中包含 {doc_count} 个文档块")
        except Exception as e:
            status_info.append(f"⚠️ 无法获取文档数量: {e}")
        
        # 检查索引状态
        if _rag_engine.index is not None:
            status_info.append("✅ 索引已加载到内存")
        else:
            status_info.append("⚠️ 索引未加载到内存（但持久化数据可能存在）")
        
        # 检查 OCR 功能
        try:
            from config import OCR_ENABLED, OCR_ENGINE
            status_info.append(f"✅ OCR 功能: {'启用' if OCR_ENABLED else '禁用'}")
            if OCR_ENABLED:
                status_info.append(f"   - OCR 引擎: {OCR_ENGINE}")
                status_info.append("   - 支持格式: PNG, JPG, JPEG, 扫描版 PDF")
        except ImportError:
            status_info.append("⚠️ OCR 配置不可用")
        
        return "\n".join(status_info)
    except Exception as e:
        return "[错误] 状态检查失败: " + str(e)


# ========== 网络搜索工具 ==========

def web_search(query: str, source: str = 'default', max_results: int = 10, use_cache: bool = True, enable_fallback: bool = True) -> str:
    """网络搜索工具 - 支持 DuckDuckGo 搜索，自动降级到Wikipedia"""
    try:
        import asyncio
        from web_search import get_search_engine_manager, get_search_cache, get_result_processor
        
        # 检查缓存
        cache_key = f"{query}_{source}"
        if use_cache:
            cache = get_search_cache()
            cached_results = cache.get(cache_key, source)
            if cached_results:
                processor = get_result_processor()
                return processor.format_results(cached_results, format='text')
        
        # 执行搜索
        manager = get_search_engine_manager()
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        # 是否聚合多引擎结果（合并去重）而非"首个非空即返回"
        try:
            from config import WEB_SEARCH_AGGREGATE
            aggregate = WEB_SEARCH_AGGREGATE
        except Exception:  # noqa: BLE001
            aggregate = True

        try:
            if enable_fallback and source == 'default':
                if aggregate:
                    # 聚合模式：按查询语境自动选源（国内→百度优先）并合并去重
                    results = loop.run_until_complete(
                        manager.search_aggregated(query, sources=None, max_results=max_results)
                    )
                else:
                    # 降级模式：按查询语境自动选主源，失败才用备用
                    results = loop.run_until_complete(
                        manager.search_with_fallback(query, primary_source='default',
                                                    fallback_sources=None,
                                                    max_results=max_results)
                    )
            else:
                # 使用指定搜索引擎
                results = loop.run_until_complete(
                    manager.search(query, source=source, max_results=max_results)
                )
        finally:
            loop.close()
        
        if not results:
            return "[提示] 搜索未返回结果，可能网络不可用或查询无匹配"
        
        # 处理结果
        processor = get_result_processor()
        processed_results = processor.deduplicate(results)
        processed_results = processor.sort_by_relevance(processed_results)
        
        # 缓存结果
        if use_cache:
            cache.set(cache_key, source, processed_results)
        
        return processor.format_results(processed_results, format='text')
        
    except ImportError as e:
        return f"[错误] 网络搜索模块未安装: {e}"
    except Exception as e:
        return f"[错误] 网络搜索失败: {str(e)}"


def web_content_extract(url: str, timeout: int = None) -> str:
    """提取网页内容并清理格式。timeout 为 None 时读取配置 WEB_SEARCH_TIMEOUT。"""
    try:
        import asyncio
        from web_search import get_content_extractor

        if timeout is None:
            try:
                from config import WEB_SEARCH_TIMEOUT
                timeout = WEB_SEARCH_TIMEOUT
            except Exception:  # noqa: BLE001
                timeout = 30

        extractor = get_content_extractor()
        
        # 验证 URL
        if not extractor.is_valid_url(url):
            return "[错误] 无效的 URL 格式"
        
        # 提取内容
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            result = loop.run_until_complete(
                extractor.extract(url, timeout=timeout)
            )
        finally:
            loop.close()
        
        if result.get('error'):
            return f"[错误] 内容提取失败: {result['error']}"
        
        # 格式化输出
        output = []
        output.append(f"=== 网页内容提取 ===")
        output.append(f"URL: {result['url']}")
        output.append(f"标题: {result['title']}")
        output.append(f"提取方法: {result['method_used']}")
        
        if result.get('metadata'):
            output.append(f"元数据: {result['metadata']}")
        
        output.append(f"\n=== 正文内容 ===")
        output.append(result['content'][:5000])  # 限制长度
        
        if len(result['content']) > 5000:
            output.append(f"\n... (内容已截断，完整长度: {len(result['content'])} 字符)")
        
        return "\n".join(output)
        
    except ImportError as e:
        return f"[错误] 内容提取模块未安装: {e}"
    except Exception as e:
        return f"[错误] 内容提取失败: {str(e)}"


def web_cache_status() -> str:
    """查看搜索缓存状态"""
    try:
        from web_search import get_search_cache
        
        cache = get_search_cache()
        stats = cache.get_stats()
        size_bytes = cache.get_size()
        size_mb = size_bytes / (1024 * 1024)
        
        output = []
        output.append("=== 搜索缓存状态 ===")
        output.append(f"缓存目录: {stats['cache_dir']}")
        output.append(f"总条目数: {stats['total_entries']}")
        output.append(f"有效条目: {stats['valid_entries']}")
        output.append(f"过期条目: {stats['expired_entries']}")
        output.append(f"最大容量: {stats['max_cache_size']}")
        output.append(f"占用空间: {size_mb:.2f} MB")
        
        if stats['source_distribution']:
            output.append("\n来源分布:")
            for source, count in stats['source_distribution'].items():
                output.append(f"  - {source}: {count} 条")
        
        return "\n".join(output)
        
    except Exception as e:
        return f"[错误] 获取缓存状态失败: {str(e)}"


def web_cache_clear() -> str:
    """清空搜索缓存"""
    try:
        from web_search import get_search_cache
        
        cache = get_search_cache()
        cache.clear()
        
        return "[成功] 搜索缓存已清空"
        
    except Exception as e:
        return f"[错误] 清空缓存失败: {str(e)}"

# ========== 初始化注册表 ==========
registry = ToolRegistry()
registry.register("read_file", read_file, "读取文件内容，支持指定行范围（仅限允许目录）",
                  {"path": "文件路径(必填)", "offset": "起始行号，默认0", "limit": "最大行数，默认100"}, safe=True)
registry.register("write_file", write_file, "写入或追加内容到文件",
                  {"path": "文件路径(必填)", "content": "文件内容(必填)", "append": "是否追加，默认false"}, safe=False)
registry.register("execute_command", execute_command, "执行shell命令（如python test.py, ls, git status等）",
                  {"command": "命令字符串(必填)", "timeout": "超时秒数，默认30"}, safe=False)
registry.register("list_directory", list_directory, "列出目录内容（仅限允许目录）",
                  {"path": "目录路径，默认当前目录"}, safe=True)
registry.register("analyze_project_structure", analyze_project_structure, "分析项目结构，识别技术栈和关键文件（仅限允许目录）",
                  {"project_path": "项目路径，默认当前目录"}, safe=True)
registry.register("search_files", search_files, "在项目中搜索包含关键字的代码文件（仅限允许目录）",
                  {"query": "搜索关键字(必填)", "path": "搜索目录，默认当前目录", "max_results": "最大结果数，默认10"}, safe=True)
registry.register("get_current_dir", get_current_dir, "获取当前工作目录路径", {}, safe=True)

# RAG 工具
registry.register("query_knowledge_base", query_knowledge_base, "查询个人知识库（PDF、论文、笔记、OCR识别的图片等文档）",
                  {"question": "查询问题(必填)"}, safe=True)
registry.register("add_to_knowledge_base", add_to_knowledge_base, "将文档添加到知识库（支持PDF/图片/MD/TXT等，自动进行OCR识别）",
                  {"file_path": "文件路径(必填)"}, safe=False)
registry.register("get_knowledge_stats", get_knowledge_stats, "获取知识库统计信息", {}, safe=True)
registry.register("check_knowledge_status", check_knowledge_status, "检查知识库状态（持久化、数据量、OCR功能）", {}, safe=True)

# 网络搜索工具
registry.register("web_search", web_search, "网络搜索（支持 DuckDuckGo + Wikipedia 自动降级）",
                  {"query": "搜索查询(必填)", "source": "搜索来源，默认default", "max_results": "最大结果数，默认10", "use_cache": "是否使用缓存，默认true", "enable_fallback": "是否启用自动降级到Wikipedia，默认true"}, safe=True)

def clear_web_search_cache() -> str:
    """清除网络搜索缓存"""
    try:
        from web_search import get_search_cache
        cache = get_search_cache()
        stats_before = cache.get_stats()
        cache.clear()
        stats_after = cache.get_stats()
        return f"[成功] 已清除搜索缓存。清除前: {stats_before['valid_entries']} 条，清除后: {stats_after['valid_entries']} 条"
    except Exception as e:
        return f"[错误] 清除缓存失败: {str(e)}"

registry.register("clear_web_search_cache", clear_web_search_cache, "清除网络搜索缓存", {}, safe=True)
registry.register("web_content_extract", web_content_extract, "提取网页内容并清理格式",
                  {"url": "网页URL(必填)", "timeout": "超时秒数，默认30"}, safe=True)
registry.register("web_cache_status", web_cache_status, "查看搜索缓存状态", {}, safe=True)
registry.register("web_cache_clear", web_cache_clear, "清空搜索缓存", {}, safe=False)

# 代码分析工具
def ast_search(pattern: str, path: str = ".", search_by: str = "name") -> str:
    """AST 语法树搜索（函数、类、变量）"""
    path = os.path.expanduser(str(path or "."))
    if not is_read_allowed(path):
        return read_scope_error(path)
    try:
        from code_analyzer import get_ast_analyzer
        
        analyzer = get_ast_analyzer()
        
        results = []
        # 如果是文件，搜索单个文件
        if os.path.isfile(path):
            # 搜索函数
            functions = analyzer.search_functions(path, pattern, search_by)
            results.extend([f"函数: {f.name} (行 {f.line_no}) - {f.parameters}" for f in functions])
            
            # 搜索类
            classes = analyzer.search_classes(path, pattern, search_by)
            results.extend([f"类: {c.name} (行 {c.line_no}) - 基类: {c.bases}" for c in classes])
        
        # 如果是目录，搜索整个项目
        elif os.path.isdir(path):
            project_analysis = analyzer.analyze_project(path, "*.py")
            for file_analysis in project_analysis.get('files', []):
                file_path = file_analysis['file_path']
                for func in file_analysis.get('functions', []):
                    if pattern in func['name']:
                        results.append(f"{file_path}: 函数 {func['name']} (行 {func['line_no']})")
                for cls in file_analysis.get('classes', []):
                    if pattern in cls['name']:
                        results.append(f"{file_path}: 类 {cls['name']} (行 {cls['line_no']})")
        
        if results:
            return f"找到 {len(results)} 个结果:\n" + "\n".join(results[:20])
        else:
            return f"未找到匹配 '{pattern}' 的代码"
        
    except ImportError as e:
        return f"[错误] 代码分析模块未安装: {e}"
    except Exception as e:
        return f"[错误] AST 搜索失败: {str(e)}"


def code_quality_check(path: str = ".", check_type: str = "basic") -> str:
    """代码质量分析（安全、性能、复杂度）"""
    path = os.path.expanduser(str(path or "."))
    if not is_read_allowed(path):
        return read_scope_error(path)
    try:
        from code_analyzer import get_quality_checker
        
        checker = get_quality_checker()
        
        if os.path.isfile(path):
            # 检查单个文件
            report = checker.check_file(path, check_types=['basic', check_type])
            return report.summary + "\n\n" + "\n".join([f"{i.line_no}: [{i.severity.value}] {i.message}" for i in report.issues[:10]])
        
        elif os.path.isdir(path):
            # 检查整个项目
            reports = checker.check_project(path)
            summary = checker.get_project_summary(reports)
            
            output = []
            output.append(f"项目质量检查摘要:")
            output.append(f"总文件数: {summary.get('total_files', 0)}")
            output.append(f"总问题数: {summary.get('total_issues', 0)}")
            output.append(f"平均分数: {summary.get('average_score', 0):.1f}/100")
            output.append(f"有问题的文件: {summary.get('files_with_issues', 0)}")
            output.append(f"\n严重程度分布:")
            for severity, count in summary.get('severity_breakdown', {}).items():
                output.append(f"  - {severity}: {count}")
            
            return "\n".join(output)
        
        else:
            return "[错误] 路径不存在"
        
    except ImportError as e:
        return f"[错误] 代码分析模块未安装: {e}"
    except Exception as e:
        return f"[错误] 代码质量检查失败: {str(e)}"


registry.register("ast_search", ast_search, "AST 语法树搜索（函数、类、变量；仅限允许目录）",
                  {"pattern": "搜索模式(必填)", "path": "搜索路径，默认当前目录", "search_by": "搜索类型（name/parameter/return/base/method），默认name"}, safe=True)
registry.register("code_quality_check", code_quality_check, "代码质量分析（安全、性能、复杂度；仅限允许目录）",
                  {"path": "代码路径，默认当前目录", "check_type": "检查类型（basic/security/complexity/pylint），默认basic"}, safe=True)

# Git 工具
def git_analyze(repo_path: str = ".", analysis_type: str = "history") -> str:
    """Git 历史分析和变更追踪"""
    repo_path = os.path.expanduser(str(repo_path or "."))
    if not is_read_allowed(repo_path):
        return read_scope_error(repo_path)
    try:
        from git_integration import get_git_analyzer
        
        analyzer = get_git_analyzer(repo_path)
        
        if analysis_type == "history":
            commits = analyzer.get_commit_history(max_count=10)
            if not commits:
                return "没有提交历史"
            
            output = []
            output.append(f"最近 {len(commits)} 次提交:")
            for commit in commits:
                output.append(f"\n{commit.commit_hash[:8]} - {commit.author}")
                output.append(f"  {commit.message}")
                output.append(f"  变更文件: {len(commit.changes)}")
                output.append(f"  时间: {commit.date[:19]}")
            
            return "\n".join(output)
        
        elif analysis_type == "status":
            status = analyzer.get_status()
            
            output = []
            output.append(f"当前分支: {status['branch']}")
            output.append(f"暂存文件: {len(status['staged'])}")
            output.append(f"未暂存文件: {len(status['unstaged'])}")
            output.append(f"未跟踪文件: {len(status['untracked'])}")
            
            if status['diverged']:
                output.append(f"分支状态: 领先 {status['ahead']} | 落后 {status['behind']}")
            
            return "\n".join(output)
        
        elif analysis_type == "authors":
            stats = analyzer.get_author_stats()
            
            output = []
            output.append("作者统计:")
            for author, data in list(stats.items())[:10]:
                output.append(f"  {author}: {data['commits']} 次提交")
            
            return "\n".join(output)
        
        else:
            return "[错误] 未知的分析类型，支持: history, status, authors"
        
    except ImportError as e:
        return f"[错误] Git 集成模块未安装: {e}"
    except Exception as e:
        return f"[错误] Git 分析失败: {str(e)}"


def git_commit_gen(repo_path: str = ".", use_ai: bool = True) -> str:
    """生成提交信息"""
    repo_path = os.path.expanduser(str(repo_path or "."))
    if not is_read_allowed(repo_path):
        return read_scope_error(repo_path)
    try:
        from git_integration import get_commit_generator
        
        generator = get_commit_generator(repo_path)
        suggestion = generator.generate_commit_message(use_ai=use_ai)
        
        output = []
        output.append("建议的提交信息:")
        output.append(f"标题: {suggestion.title}")
        if suggestion.body:
            output.append(f"\n正文:\n{suggestion.body}")
        if suggestion.conventional_type:
            output.append(f"\n类型: {suggestion.conventional_type}")
        
        return "\n".join(output)
        
    except ImportError as e:
        return f"[错误] Git 集成模块未安装: {e}"
    except Exception as e:
        return f"[错误] 生成提交信息失败: {str(e)}"


registry.register("git_analyze", git_analyze, "Git 历史分析和变更追踪（仅限允许目录）",
                  {"repo_path": "仓库路径，默认当前目录", "analysis_type": "分析类型（history/status/authors），默认history"}, safe=True)
registry.register("git_commit_gen", git_commit_gen, "生成提交信息（仅限允许目录）",
                  {"repo_path": "仓库路径，默认当前目录", "use_ai": "是否使用AI生成，默认true"}, safe=True)

# 知识图谱工具
def knowledge_graph_query(query: str, query_type: str = "entity") -> str:
    """知识图谱查询和推理"""
    try:
        from knowledge_graph import get_graph_query
        
        query_engine = get_graph_query()
        
        if query_type == "entity":
            result = query_engine.query_entity(query)
        elif query_type == "neighbors":
            result = query_engine.query_neighbors(query)
        elif query_type == "path":
            # 路径查询需要两个实体，这里简化处理
            parts = query.split('->')
            if len(parts) == 2:
                result = query_engine.query_path(parts[0].strip(), parts[1].strip())
            else:
                result = query_engine.query_path(query, query)  # 尝试作为单一查询
        elif query_type == "similar":
            result = query_engine.query_similar(query)
        elif query_type == "type":
            # 按实体类型列出实体（如 tool/concept/technology...）
            from knowledge_graph import EntityType
            try:
                entity_type = EntityType(query.strip().lower())
            except (ValueError, TypeError):
                valid = ", ".join(t.value for t in EntityType)
                return f"[错误] 无效的实体类型 '{query}'。可用类型: {valid}"
            result = query_engine.query_by_type(entity_type)
        else:
            result = query_engine.query_entity(query)
        
        # 格式化结果
        output = []
        output.append(result.explanation)
        
        if result.entities:
            output.append(f"\n实体 ({len(result.entities)}):")
            for entity in result.entities[:10]:
                output.append(f"  - {entity.text} ({entity.entity_type.value})")
        
        if result.relations:
            output.append(f"\n关系 ({len(result.relations)}):")
            for relation in result.relations[:10]:
                output.append(f"  - {relation.source.text} -> {relation.target.text} ({relation.relation_type.value})")
        
        output.append(f"\n置信度: {result.confidence:.2f}")
        
        return "\n".join(output)
        
    except ImportError as e:
        return f"[错误] 知识图谱模块未安装: {e}"
    except Exception as e:
        return f"[错误] 知识图谱查询失败: {str(e)}"


def knowledge_graph_build(text: str, doc_id: str = "manual", doc_type: str = "text") -> str:
    """构建知识图谱"""
    try:
        from knowledge_graph import get_graph_builder
        
        builder = get_graph_builder()
        
        success = builder.add_document(text, doc_id, doc_type)
        
        if success:
            stats = builder.get_statistics()
            output = []
            output.append("知识图谱构建成功")
            output.append(f"节点数: {stats.total_nodes}")
            output.append(f"边数: {stats.total_edges}")
            output.append(f"实体类型: {list(stats.entity_types.keys())}")
            output.append(f"关系类型: {list(stats.relation_types.keys())}")
            return "\n".join(output)
        else:
            return "[错误] 知识图谱构建失败"
        
    except ImportError as e:
        return f"[错误] 知识图谱模块未安装: {e}"
    except Exception as e:
        return f"[错误] 知识图谱构建失败: {str(e)}"


registry.register("knowledge_graph_query", knowledge_graph_query, "知识图谱查询和推理",
                  {"query": "图谱查询", "query_type": "查询类型（entity/type/neighbors/path/similar），默认entity"}, safe=True)
registry.register("knowledge_graph_build", knowledge_graph_build, "构建知识图谱",
                  {"text": "文本内容(必填)", "doc_id": "文档ID，默认manual", "doc_type": "文档类型（text/code），默认text"}, safe=True)

# ========== 数据库工具 ==========
#
# 「当前连接」语义（database_tools.session）：``database_connect`` 成功后记录当前库；
# 其余工具在调用方未显式传 ``database``（仍为默认 ``:memory:``）时回退到当前连接，
# 显式传参优先；同一 (db_type, database) 复用同一连接器。Web / CLI / Agent 三端共用。

def _db_executor(db_type: str, database: str, **kwargs):
    """解析当前连接并返回复用的 ``QueryExecutor``。"""
    from database_tools import QueryExecutor
    from database_tools import session as db_session

    db_type, database, extra = db_session.resolve(db_type, database, **kwargs)
    connector = db_session.get_connector(db_type, database, **extra)
    return QueryExecutor(connector)


def database_connect(db_type: str = "sqlite", database: str = ":memory:", **kwargs) -> str:
    """
    连接数据库并设为当前连接（后续 database_query / execute / get_schema 未指定 database 时作用于它）
    
    Args:
        db_type: 数据库类型（当前仅实现 sqlite）
        database: 数据库路径或名称
        **kwargs: 其他连接参数
        
    Returns:
        连接结果信息
    """
    try:
        from database_tools import DatabaseType
        from database_tools import session as db_session
        
        db_type = (db_type or "sqlite").lower()
        database = database or ":memory:"
        DatabaseType(db_type)  # 校验类型合法
        connector = db_session.get_connector(db_type, database, **kwargs)
        
        if connector.test_connection():
            db_session.set_current(db_type, database, **kwargs)
            conn_info = connector.get_connection_info()
            return (
                f"[成功] 数据库连接成功\n类型: {conn_info['db_type']}\n"
                f"参数: {json.dumps(conn_info['connection_params'], ensure_ascii=False)}\n"
                f"已设为当前连接：后续查询 / 执行 / 表结构未指定 database 时作用于此库"
            )
        else:
            return "[错误] 数据库连接测试失败"
    
    except ImportError as e:
        return f"[错误] 数据库工具模块未安装: {e}"
    except Exception as e:
        return f"[错误] 数据库连接失败: {str(e)}"

def database_query(sql: str, db_type: str = "sqlite", database: str = ":memory:", **kwargs) -> str:
    """
    执行SQL查询（SELECT）
    
    Args:
        sql: SQL查询语句
        db_type: 数据库类型
        database: 数据库路径或名称（省略时使用当前连接）
        **kwargs: 其他连接参数
        
    Returns:
        查询结果
    """
    try:
        executor = _db_executor(db_type, database, **kwargs)
        result = executor.execute_query(sql)
        
        if result.success:
            output = [f"[成功] 查询执行成功，返回 {result.row_count} 行"]
            output.append(f"执行时间: {result.execution_time:.3f}s")
            output.append("列: " + ", ".join(result.columns))
            
            for row in result.rows:
                output.append(str(row))
            
            return "\n".join(output)
        else:
            return f"[错误] 查询失败: {result.error_message}"
    
    except ImportError as e:
        return f"[错误] 数据库工具模块未安装: {e}"
    except Exception as e:
        return f"[错误] 查询执行失败: {str(e)}"

def database_execute(sql: str, db_type: str = "sqlite", database: str = ":memory:", **kwargs) -> str:
    """
    执行SQL语句（INSERT/UPDATE/DELETE/DDL）
    
    Args:
        sql: SQL语句
        db_type: 数据库类型
        database: 数据库路径或名称（省略时使用当前连接）
        **kwargs: 其他连接参数
        
    Returns:
        执行结果
    """
    try:
        executor = _db_executor(db_type, database, **kwargs)
        result = executor.execute_update(sql)
        
        if result.success:
            return f"[成功] 语句执行成功，影响 {result.affected_rows} 行\n执行时间: {result.execution_time:.3f}s"
        else:
            return f"[错误] 执行失败: {result.error_message}"
    
    except ImportError as e:
        return f"[错误] 数据库工具模块未安装: {e}"
    except Exception as e:
        return f"[错误] 执行失败: {str(e)}"

def database_create_table(table: str, columns: dict, db_type: str = "sqlite", database: str = ":memory:", **kwargs) -> str:
    """
    创建数据库表
    
    Args:
        table: 表名
        columns: 列定义字典，如 {"id": "INTEGER PRIMARY KEY", "name": "TEXT"}
        db_type: 数据库类型
        database: 数据库路径或名称（省略时使用当前连接）
        **kwargs: 其他连接参数
        
    Returns:
        执行结果
    """
    try:
        from database_tools import SQLGenerator
        
        executor = _db_executor(db_type, database, **kwargs)
        generator = SQLGenerator()
        
        sql = generator.generate_create_table(table, columns)
        result = executor.execute_update(sql)
        
        if result.success:
            return f"[成功] 表 {table} 创建成功"
        else:
            return f"[错误] 创建表失败: {result.error_message}"
    
    except ImportError as e:
        return f"[错误] 数据库工具模块未安装: {e}"
    except Exception as e:
        return f"[错误] 创建表失败: {str(e)}"

def database_insert(table: str, data: dict, db_type: str = "sqlite", database: str = ":memory:", **kwargs) -> str:
    """
    插入数据到表
    
    Args:
        table: 表名
        data: 数据字典，如 {"name": "John", "age": 30}
        db_type: 数据库类型
        database: 数据库路径或名称（省略时使用当前连接）
        **kwargs: 其他连接参数
        
    Returns:
        执行结果
    """
    try:
        from database_tools import SQLGenerator
        
        executor = _db_executor(db_type, database, **kwargs)
        generator = SQLGenerator()
        
        sql, params = generator.generate_insert(table, data)
        result = executor.execute_update(sql, params)
        
        if result.success:
            return f"[成功] 数据插入成功，影响 {result.affected_rows} 行"
        else:
            return f"[错误] 插入数据失败: {result.error_message}"
    
    except ImportError as e:
        return f"[错误] 数据库工具模块未安装: {e}"
    except Exception as e:
        return f"[错误] 插入数据失败: {str(e)}"

def database_get_schema(table: str = "", db_type: str = "sqlite", database: str = ":memory:", **kwargs) -> str:
    """
    获取表结构；``table`` 为空时列出库中全部表名
    
    Args:
        table: 表名（空 → 列出所有表）
        db_type: 数据库类型
        database: 数据库路径或名称（省略时使用当前连接）
        **kwargs: 其他连接参数
        
    Returns:
        表结构信息 / 表名列表
    """
    try:
        executor = _db_executor(db_type, database, **kwargs)
        table = (table or "").strip()
        
        if not table:
            tables = executor.list_tables()
            if not tables:
                return "[提示] 数据库中没有表"
            return f"[成功] 共 {len(tables)} 张表\n" + "\n".join(f"- {t}" for t in tables)
        
        schema = executor.get_table_schema(table)
        
        if schema and schema.get('columns'):
            output = [f"[表] {schema['table_name']}"]
            output.append("[列信息]")
            for col in schema['columns']:
                output.append(f"  {col['name']}: {col['type']} (NOT NULL: {col['not_null']}, PK: {col['primary_key']})")
            return "\n".join(output)
        else:
            return f"[错误] 获取表结构失败: 表 {table} 不存在或没有列"
    
    except ImportError as e:
        return f"[错误] 数据库工具模块未安装: {e}"
    except Exception as e:
        return f"[错误] 获取表结构失败: {str(e)}"

# 注册数据库工具
registry.register("database_connect", database_connect, "连接数据库并设为当前连接（后续 database_* 未指定 database 时作用于它）",
                  {"db_type": "数据库类型（当前仅实现 sqlite），默认sqlite", "database": "数据库路径或名称，省略时使用当前连接"}, safe=True)
registry.register("database_query", database_query, "执行SQL查询（SELECT）",
                  {"sql": "SQL查询语句(必填)", "db_type": "数据库类型，默认sqlite", "database": "数据库路径或名称，省略时使用当前连接"}, safe=True)
registry.register("database_execute", database_execute, "执行SQL语句（INSERT/UPDATE/DELETE）",
                  {"sql": "SQL语句(必填)", "db_type": "数据库类型，默认sqlite", "database": "数据库路径或名称，省略时使用当前连接"}, safe=False)
registry.register("database_create_table", database_create_table, "创建数据库表",
                  {"table": "表名(必填)", "columns": "列定义字典(必填)，如 {\"id\": \"INTEGER PRIMARY KEY\", \"name\": \"TEXT\"}", "db_type": "数据库类型，默认sqlite", "database": "数据库路径或名称，省略时使用当前连接"}, safe=False)
registry.register("database_insert", database_insert, "插入数据到表",
                  {"table": "表名(必填)", "data": "数据字典(必填)，如 {\"name\": \"John\", \"age\": 30}", "db_type": "数据库类型，默认sqlite", "database": "数据库路径或名称，省略时使用当前连接"}, safe=False)
registry.register("database_get_schema", database_get_schema, "获取表结构（table 为空时列出全部表名）",
                  {"table": "表名，留空列出全部表", "db_type": "数据库类型，默认sqlite", "database": "数据库路径或名称，省略时使用当前连接"}, safe=True)
