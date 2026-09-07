"""代码感知分块（F8 P4）。

代码文件入库时按语法结构（函数 / 类 / 方法）切分，而不是 ``SentenceSplitter`` 的
按 token 数硬切。核心是 :class:`LanguageAwareNodeParser`：按 ``Document.metadata["file_type"]``
把代码文件分派到 tree-sitter 路径，其余文件仍走通用 ``SentenceSplitter``。

代码路径的处理流程::

    源码 → tree-sitter 解析 → 原子（≤ max_chars 的语法节点，含其前置空白/注释）
        → 贪心打包（在函数/类定义前优先断开）→ 碎片合并（签名并入函数体）
        → 超长块按行二次切分 → 写入 symbol / start_line / end_line 元数据 + 注释头

依赖 ``tree-sitter-language-pack`` 为**可选**：未安装、解析异常或语法错误占比过高时
整文件回退 ``SentenceSplitter``，且只产生提示级文案，不抛错。

供 CLI / Web 共用的展示辅助：:func:`strategy_display`、:func:`availability_message`、
:func:`strip_header`、:func:`summarize_nodes`。
"""

from __future__ import annotations

import re
from collections import OrderedDict
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from llama_index.core.node_parser import SentenceSplitter
from llama_index.core.node_parser.interface import NodeParser
from llama_index.core.node_parser.node_utils import build_nodes_from_splits
from llama_index.core.schema import BaseNode, MetadataMode, TextNode
from pydantic import Field, PrivateAttr

from config import (
    CHUNK_OVERLAP,
    CHUNK_SIZE,
    CODE_AWARE_CHUNKING,
    CODE_CHUNK_MAX_CHARS,
    CODE_CHUNK_MIN_CHARS,
)

# ---------------------------------------------------------------------------
# 语言表：代码后缀的唯一来源（document_loader / config 白名单由此派生）
# ---------------------------------------------------------------------------

LANGUAGE_MAP: Dict[str, str] = OrderedDict(
    [
        (".py", "python"),
        (".js", "javascript"),
        (".ts", "typescript"),
        (".java", "java"),
        (".go", "go"),
        (".rs", "rust"),
        (".c", "c"),
        (".cpp", "cpp"),
    ]
)
CODE_EXTENSIONS: Tuple[str, ...] = tuple(LANGUAGE_MAP)

# 各语言"定义"节点类型：这些节点开头优先作为块边界，并用于推导 symbol。
_DEF_TYPES: Dict[str, frozenset] = {
    "python": frozenset({"function_definition", "class_definition", "decorated_definition"}),
    "javascript": frozenset(
        {
            "function_declaration",
            "generator_function_declaration",
            "class_declaration",
            "method_definition",
            "lexical_declaration",
            "variable_declaration",
            "export_statement",
        }
    ),
    "typescript": frozenset(
        {
            "function_declaration",
            "generator_function_declaration",
            "class_declaration",
            "abstract_class_declaration",
            "method_definition",
            "interface_declaration",
            "enum_declaration",
            "type_alias_declaration",
            "lexical_declaration",
            "variable_declaration",
            "export_statement",
        }
    ),
    "java": frozenset(
        {
            "class_declaration",
            "interface_declaration",
            "enum_declaration",
            "record_declaration",
            "method_declaration",
            "constructor_declaration",
        }
    ),
    "go": frozenset({"function_declaration", "method_declaration", "type_declaration"}),
    "rust": frozenset(
        {
            "function_item",
            "function_signature_item",
            "struct_item",
            "enum_item",
            "trait_item",
            "impl_item",
            "mod_item",
        }
    ),
    "c": frozenset({"function_definition", "struct_specifier", "enum_specifier", "union_specifier"}),
    "cpp": frozenset(
        {
            "function_definition",
            "struct_specifier",
            "class_specifier",
            "enum_specifier",
            "union_specifier",
            "namespace_definition",
        }
    ),
}

_COMMENT_PREFIX: Dict[str, str] = {"python": "#"}
_HEADER_RE = re.compile(r"^(#|//) .+? · L\d+-L\d+\n")
# 语法错误字节占比超过该值视为"不是该语言的代码"，整文件回退文本切分。
_ERROR_RATIO_LIMIT = 0.30
# 碎片合并后允许的块上限倍数（宁可略大也不把签名与函数体拆开）。
_MERGE_TOLERANCE = 1.5

# ---------------------------------------------------------------------------
# 依赖探测
# ---------------------------------------------------------------------------

_PACK_CACHE: Dict[str, Any] = {}


def _load_pack() -> Optional[Any]:
    """导入 ``tree_sitter_language_pack``；失败返回 None（结果缓存）。"""
    if "module" in _PACK_CACHE:
        return _PACK_CACHE["module"]
    try:
        import tree_sitter_language_pack as pack  # type: ignore

        if not hasattr(pack, "get_parser"):
            raise ImportError("tree_sitter_language_pack 缺少 get_parser")
    except Exception:  # noqa: BLE001 - 任何导入问题都视为不可用
        pack = None
    _PACK_CACHE["module"] = pack
    return pack


def reset_availability_cache() -> None:
    """清空依赖探测缓存（测试用）。"""
    _PACK_CACHE.clear()


def is_available() -> bool:
    """tree-sitter 语言包是否可用。"""
    return _load_pack() is not None


def dependency_version() -> str:
    """返回 ``tree-sitter-language-pack`` 版本号；不可用时返回空串。"""
    if not is_available():
        return ""
    try:
        from importlib.metadata import version

        return version("tree-sitter-language-pack")
    except Exception:  # noqa: BLE001
        return "?"


def is_enabled() -> bool:
    """总开关：配置开启且依赖可用。"""
    return bool(CODE_AWARE_CHUNKING) and is_available()


def availability_message() -> str:
    """缺依赖 / 关闭时给用户的一句提示（CLI、Web 三处同源）；启用时返回空串。"""
    if not CODE_AWARE_CHUNKING:
        return "代码感知分块已关闭（CODE_AWARE_CHUNKING=false），代码文件按通用文本切分"
    if not is_available():
        return (
            "代码感知分块未启用（未安装 tree-sitter-language-pack），代码文件按通用文本切分："
            'pip install "tree-sitter-language-pack>=1.16,<2"'
        )
    return ""


def status_text() -> str:
    """供 ``get_stats()`` / 系统页显示的状态串。"""
    if not CODE_AWARE_CHUNKING:
        return "disabled: CODE_AWARE_CHUNKING=false"
    if not is_available():
        return "disabled: tree-sitter-language-pack not installed"
    return f"enabled (tree-sitter-language-pack {dependency_version()}) · max {CODE_CHUNK_MAX_CHARS} chars"


# ---------------------------------------------------------------------------
# 展示辅助
# ---------------------------------------------------------------------------


def strategy_display(strategy: Optional[str]) -> str:
    """把 ``chunk_strategy`` 转成中文标签：``code(python)`` → ``代码(python)``。"""
    s = (strategy or "").strip()
    if not s:
        return "文本"
    if s.startswith("code"):
        return "代码" + s[4:]
    if s.startswith("text(fallback"):
        return "文本（代码解析失败，已回退）"
    return "文本"


_HINT_SHOWN = {"shown": False}


def availability_hint_once() -> str:
    """进程内只返回一次的缺依赖/关闭提示（入库成功文案后追加），之后返回空串。"""
    msg = availability_message()
    if not msg or _HINT_SHOWN["shown"]:
        return ""
    _HINT_SHOWN["shown"] = True
    return msg


def reset_hint() -> None:
    """重置一次性提示（测试用）。"""
    _HINT_SHOWN["shown"] = False


def format_ingest_summary(per_file: Dict[str, Dict[str, Any]], file_count: Optional[int] = None) -> str:
    """入库结果一句话：``已入库 3 个文件 · 41 个片段（其中 2 个代码文件按函数/类切分，共 27 个符号）``。

    ``per_file`` 为 ``RAGEngine.last_ingest_stats``（path -> chunk_count/symbol_count/chunk_strategy）。
    """
    per_file = per_file or {}
    files = file_count if file_count is not None else len(per_file)
    chunks = sum(int(v.get("chunk_count", 0) or 0) for v in per_file.values())
    code_files = [v for v in per_file.values() if str(v.get("chunk_strategy", "")).startswith("code")]
    symbols = sum(int(v.get("symbol_count", 0) or 0) for v in code_files)
    text = f"已入库 {files} 个文件 · {chunks} 个片段"
    if code_files:
        text += f"（其中 {len(code_files)} 个代码文件按函数/类切分，共 {symbols} 个符号）"
    fallback = [v for v in per_file.values() if str(v.get("chunk_strategy", "")).startswith("text(fallback")]
    if fallback:
        text += f"；{len(fallback)} 个代码文件解析失败已按文本切分"
    return text


def describe_file_chunking(file_path: Optional[str], chunk_strategy: Optional[str], symbol_count: int = 0) -> str:
    """文件级分块描述（/file-list、/file-info、Web 文件表与详情共用）。

    - 代码块：``代码(python) · 27 个符号``
    - 解析失败回退：``文本（代码解析失败，已回退）``
    - 代码后缀但按文本切分（旧库或未启用）：``文本（重新入库可启用代码分块）``
    - 其他：``文本``
    """
    label = strategy_display(chunk_strategy)
    if label.startswith("代码"):
        return f"{label} · {int(symbol_count or 0)} 个符号" if symbol_count else label
    if label.startswith("文本（"):
        return label
    if language_for(None, file_path or "") and is_enabled():
        return "文本（重新入库可启用代码分块）"
    return label


def strip_header(text: str) -> str:
    """去掉代码块首行的 ``# file · symbol · L1-L2`` 注释头（用于 prompt / 展示）。"""
    if not text:
        return text
    return _HEADER_RE.sub("", text, count=1)


def language_for(file_type: Optional[str], file_name: Optional[str] = None) -> Optional[str]:
    """由 ``file_type``（``.py``）或文件名后缀得到 tree-sitter 语言名。"""
    ext = (file_type or "").lower().strip()
    if not ext and file_name:
        idx = file_name.rfind(".")
        ext = file_name[idx:].lower() if idx >= 0 else ""
    if ext and not ext.startswith("."):
        ext = "." + ext
    return LANGUAGE_MAP.get(ext)


def summarize_nodes(nodes: Sequence[BaseNode]) -> Dict[str, Any]:
    """统计一批节点：``chunk_count`` / ``symbol_count`` / ``chunk_strategy``。"""
    strategies = [str(n.metadata.get("chunk_strategy") or "text") for n in nodes]
    symbols = {n.metadata.get("symbol") for n in nodes if n.metadata.get("symbol")}
    code = [s for s in strategies if s.startswith("code")]
    if code:
        strategy = code[0]
    elif any(s.startswith("text(fallback") for s in strategies):
        strategy = next(s for s in strategies if s.startswith("text(fallback"))
    else:
        strategy = "text"
    return {"chunk_count": len(nodes), "symbol_count": len(symbols), "chunk_strategy": strategy}


# ---------------------------------------------------------------------------
# tree-sitter 切分实现
# ---------------------------------------------------------------------------


class _Atom:
    """一个不可再分的语法片段：``[start, end)`` 字节区间 + 起始节点 + 是否为定义开头。"""

    __slots__ = ("start", "end", "node", "is_def", "breakable")

    def __init__(self, start: int, end: int, node: Any, is_def: bool):
        self.start = start
        self.end = end
        self.node = node
        self.is_def = is_def
        # 只有当原子位于行首（前置空白含换行）时才允许在其前面断块，避免块在行中间开始
        self.breakable = True


def _node_name(node: Any, language: str) -> str:
    """提取定义节点的名字；拿不到返回空串。"""
    t = node.type
    try:
        if language == "python" and t == "decorated_definition":
            inner = node.child_by_field_name("definition")
            return _node_name(inner, language) if inner is not None else ""
        if t == "export_statement":
            inner = node.child_by_field_name("declaration")
            return _node_name(inner, language) if inner is not None else ""
        if t in ("lexical_declaration", "variable_declaration"):
            for ch in node.children:
                if ch.type == "variable_declarator":
                    n = ch.child_by_field_name("name")
                    return n.text.decode("utf-8", "replace") if n is not None else ""
            return ""
        if language == "go" and t == "type_declaration":
            for ch in node.children:
                if ch.type == "type_spec":
                    n = ch.child_by_field_name("name")
                    return n.text.decode("utf-8", "replace") if n is not None else ""
            return ""
        if language == "rust" and t == "impl_item":
            n = node.child_by_field_name("type")
            return n.text.decode("utf-8", "replace") if n is not None else ""
        if language in ("c", "cpp") and t == "function_definition":
            decl = node.child_by_field_name("declarator")
            while decl is not None and decl.type not in (
                "identifier",
                "field_identifier",
                "qualified_identifier",
                "destructor_name",
                "operator_name",
            ):
                nxt = decl.child_by_field_name("declarator")
                if nxt is None:
                    # 例如 `int (*fp)(...)`：退到第一个 identifier 子节点
                    nxt = next((c for c in decl.children if c.type.endswith("identifier")), None)
                decl = nxt
            return decl.text.decode("utf-8", "replace") if decl is not None else ""
        n = node.child_by_field_name("name")
        return n.text.decode("utf-8", "replace") if n is not None else ""
    except Exception:  # noqa: BLE001
        return ""


def _symbol_path(node: Any, language: str) -> str:
    """从节点向上收集定义名，形成 ``Class.method`` 形式的符号路径。"""
    defs = _DEF_TYPES.get(language, frozenset())
    names: List[str] = []
    cur = node
    while cur is not None:
        if cur.type in defs:
            name = _node_name(cur, language)
            if name and (not names or names[-1] != name):
                names.append(name)
        cur = cur.parent
    names.reverse()
    return ".".join(names)


def _error_ratio(root: Any) -> float:
    total = max(1, root.end_byte - root.start_byte)
    bad = 0
    stack = [root]
    while stack:
        n = stack.pop()
        if n.type == "ERROR" or n.is_missing:
            bad += max(1, n.end_byte - n.start_byte)
            continue
        if n.has_error:
            stack.extend(n.children)
    return bad / total


def _collect_atoms(node: Any, last_end: int, max_chars: int, defs: frozenset, out: List[_Atom], is_def_start: bool = False) -> int:
    """递归把 ``node`` 拆成原子（含其前置空白），返回新的 ``last_end``。"""
    size = node.end_byte - last_end
    is_def = node.type in defs or is_def_start
    if size <= max_chars or not node.children:
        out.append(_Atom(last_end, node.end_byte, node, is_def))
        return node.end_byte
    first = True
    for child in node.children:
        last_end = _collect_atoms(child, last_end, max_chars, defs, out, is_def_start=(is_def and first))
        first = False
    if node.end_byte > last_end:
        # 节点尾部残余（如闭合括号前的空白）并入最后一个原子
        if out:
            out[-1].end = node.end_byte
        last_end = node.end_byte
    return last_end


def _pack_atoms(atoms: List[_Atom], max_chars: int, min_chars: int) -> List[List[_Atom]]:
    """贪心打包：不超过 ``max_chars``；遇到定义开头且当前块已 ≥ ``min_chars`` 则断开。"""
    chunks: List[List[_Atom]] = []
    cur: List[_Atom] = []
    cur_len = 0
    for atom in atoms:
        alen = atom.end - atom.start
        if cur and atom.breakable and (cur_len + alen > max_chars or (atom.is_def and cur_len >= min_chars)):
            chunks.append(cur)
            cur, cur_len = [], 0
        cur.append(atom)
        cur_len += alen
    if cur:
        chunks.append(cur)
    return chunks


def _merge_fragments(spans: List[Tuple[int, int, List[_Atom]]], max_chars: int, min_chars: int) -> List[Tuple[int, int, List[_Atom]]]:
    """把过短的块并入**下一块**（签名跟函数体走）；末尾碎片并入上一块。"""
    limit = int(max_chars * _MERGE_TOLERANCE)
    merged: List[Tuple[int, int, List[_Atom]]] = []
    i = 0
    while i < len(spans):
        start, end, atoms = spans[i]
        while end - start < min_chars and i + 1 < len(spans):
            n_start, n_end, n_atoms = spans[i + 1]
            if n_end - start > limit:
                break
            end, atoms = n_end, atoms + n_atoms
            i += 1
        merged.append((start, end, atoms))
        i += 1
    if len(merged) >= 2:
        start, end, atoms = merged[-1]
        if end - start < min_chars:
            p_start, p_end, p_atoms = merged[-2]
            if end - p_start <= limit:
                merged[-2] = (p_start, end, p_atoms + atoms)
                merged.pop()
    return merged


def _split_oversized(text: str, max_chars: int) -> List[str]:
    """超长块按行贪心切分（不拆行）。"""
    if len(text) <= int(max_chars * _MERGE_TOLERANCE):
        return [text]
    parts: List[str] = []
    buf: List[str] = []
    size = 0
    for line in text.splitlines(keepends=True):
        if buf and size + len(line) > max_chars:
            parts.append("".join(buf))
            buf, size = [], 0
        buf.append(line)
        size += len(line)
    if buf:
        parts.append("".join(buf))
    return parts


def split_code(
    text: str,
    language: str,
    file_name: str = "",
    max_chars: int = CODE_CHUNK_MAX_CHARS,
    min_chars: int = CODE_CHUNK_MIN_CHARS,
    parser: Any = None,
) -> Optional[List[Dict[str, Any]]]:
    """把一段源码切成带元数据的片段列表。

    返回 ``[{"text", "symbol", "start_line", "end_line"}]``；tree-sitter 不可用、
    语言不支持或语法错误过多时返回 ``None`` 由调用方回退。
    """
    if parser is None:
        pack = _load_pack()
        if pack is None:
            return None
        try:
            parser = pack.get_parser(language)
        except Exception:  # noqa: BLE001
            return None
    data = text.encode("utf-8")
    if not data.strip():
        return []
    tree = parser.parse(data)
    root = tree.root_node
    if _error_ratio(root) > _ERROR_RATIO_LIMIT:
        return None

    defs = _DEF_TYPES.get(language, frozenset())
    atoms: List[_Atom] = []
    last = 0
    for child in root.children:
        last = _collect_atoms(child, last, max_chars, defs, atoms)
    if not atoms:
        atoms.append(_Atom(0, len(data), root, False))
    if last < len(data):
        atoms[-1].end = len(data)
    for atom in atoms:
        gap = data[atom.start : atom.node.start_byte]
        atom.breakable = atom.start == 0 or b"\n" in gap or data[atom.start - 1 : atom.start] == b"\n"

    packed = _pack_atoms(atoms, max_chars, min_chars)
    spans = [(grp[0].start, grp[-1].end, grp) for grp in packed]
    spans = _merge_fragments(spans, max_chars, min_chars)

    results: List[Dict[str, Any]] = []
    for start, end, grp in spans:
        raw = data[start:end].decode("utf-8", "replace")
        if not raw.strip():
            continue
        symbol = ""
        for atom in grp:
            symbol = _symbol_path(atom.node, language)
            if symbol:
                break
        # 行号：跳过块首的空白行，定位到首个非空字符
        lead = len(raw) - len(raw.lstrip())
        first_byte = start + len(raw[:lead].encode("utf-8"))
        start_line = data.count(b"\n", 0, first_byte) + 1
        body = raw.strip("\n")
        pieces = _split_oversized(body, max_chars)
        line_cursor = start_line
        for piece in pieces:
            n_lines = piece.count("\n") + (0 if piece.endswith("\n") else 1)
            results.append(
                {
                    "text": piece.rstrip("\n"),
                    "symbol": symbol,
                    "start_line": line_cursor,
                    "end_line": max(line_cursor, line_cursor + n_lines - 1),
                }
            )
            line_cursor += n_lines
    # 同一符号跨多块时标 part i/n
    counts: Dict[str, int] = {}
    for r in results:
        if r["symbol"]:
            counts[r["symbol"]] = counts.get(r["symbol"], 0) + 1
    seen: Dict[str, int] = {}
    for r in results:
        sym = r["symbol"]
        if sym and counts[sym] > 1:
            seen[sym] = seen.get(sym, 0) + 1
            r["part"] = f"{seen[sym]}/{counts[sym]}"
    # 注释头
    prefix = _COMMENT_PREFIX.get(language, "//")
    for r in results:
        label = r["symbol"] or "(module)"
        r["text"] = f"{prefix} {file_name or 'code'} · {label} · L{r['start_line']}-L{r['end_line']}\n{r['text']}"
    return results


# ---------------------------------------------------------------------------
# NodeParser
# ---------------------------------------------------------------------------

_EXCLUDED_META_KEYS = ("start_line", "end_line", "chunk_strategy", "language", "part")


class LanguageAwareNodeParser(NodeParser):
    """按文件类型分派：代码文件走 tree-sitter，其余走 ``SentenceSplitter``。"""

    text_splitter: SentenceSplitter = Field(description="非代码文件使用的通用切分器")
    code_enabled: bool = Field(default=True, description="是否启用代码感知分块")
    max_chars: int = Field(default=CODE_CHUNK_MAX_CHARS, gt=0)
    min_chars: int = Field(default=CODE_CHUNK_MIN_CHARS, gt=0)
    _parsers: Dict[str, Any] = PrivateAttr(default_factory=dict)
    _fallback_reasons: Dict[str, str] = PrivateAttr(default_factory=dict)

    @classmethod
    def class_name(cls) -> str:
        return "LanguageAwareNodeParser"

    # -- 依赖 -------------------------------------------------------------
    def _parser_for(self, language: str) -> Optional[Any]:
        if language in self._parsers:
            return self._parsers[language]
        pack = _load_pack()
        parser = None
        if pack is not None:
            try:
                parser = pack.get_parser(language)
            except Exception:  # noqa: BLE001
                parser = None
        self._parsers[language] = parser
        return parser

    @property
    def fallback_reasons(self) -> Dict[str, str]:
        """最近一次解析中回退到文本切分的文件 → 原因。"""
        return dict(self._fallback_reasons)

    # -- 主流程 -----------------------------------------------------------
    def _parse_nodes(self, nodes: Sequence[BaseNode], show_progress: bool = False, **kwargs: Any) -> List[BaseNode]:
        out: List[BaseNode] = []
        self._fallback_reasons = {}
        for node in nodes:
            language = language_for(node.metadata.get("file_type"), node.metadata.get("file_name"))
            if language and self.code_enabled:
                code_nodes = self._parse_code_node(node, language)
                if code_nodes is not None:
                    out.extend(code_nodes)
                    continue
            out.extend(self._parse_text_node(node, language))
        return out

    def _parse_text_node(self, node: BaseNode, language: Optional[str]) -> List[BaseNode]:
        parsed = self.text_splitter._parse_nodes([node])
        key = node.metadata.get("file_path") or node.metadata.get("file_name") or node.node_id
        strategy = "text"
        if language and self.code_enabled:
            reason = self._fallback_reasons.get(key, "")
            strategy = f"text(fallback:{reason})" if reason else "text"
        for n in parsed:
            n.metadata["chunk_strategy"] = strategy
            self._exclude_meta(n)
        return parsed

    def _parse_code_node(self, node: BaseNode, language: str) -> Optional[List[BaseNode]]:
        key = node.metadata.get("file_path") or node.metadata.get("file_name") or node.node_id
        parser = self._parser_for(language)
        if parser is None:
            self._fallback_reasons[key] = "no_parser"
            return None
        text = node.get_content(metadata_mode=MetadataMode.NONE)
        try:
            pieces = split_code(
                text,
                language,
                file_name=node.metadata.get("file_name", ""),
                max_chars=self.max_chars,
                min_chars=self.min_chars,
                parser=parser,
            )
        except Exception:  # noqa: BLE001
            pieces = None
        if pieces is None:
            self._fallback_reasons[key] = "parse_error"
            return None
        if not pieces:
            return []
        built = build_nodes_from_splits([p["text"] for p in pieces], node, id_func=self.id_func)
        for n, p in zip(built, pieces):
            n.metadata["symbol"] = p["symbol"]
            n.metadata["start_line"] = int(p["start_line"])
            n.metadata["end_line"] = int(p["end_line"])
            n.metadata["language"] = language
            n.metadata["chunk_strategy"] = f"code({language})"
            if p.get("part"):
                n.metadata["part"] = p["part"]
            self._exclude_meta(n)
        return built

    @staticmethod
    def _exclude_meta(n: BaseNode) -> None:
        if isinstance(n, TextNode):
            for k in _EXCLUDED_META_KEYS:
                if k not in n.excluded_embed_metadata_keys:
                    n.excluded_embed_metadata_keys.append(k)
                if k not in n.excluded_llm_metadata_keys:
                    n.excluded_llm_metadata_keys.append(k)


def build_node_parser(
    chunk_size: int = CHUNK_SIZE,
    chunk_overlap: int = CHUNK_OVERLAP,
    code_enabled: Optional[bool] = None,
) -> LanguageAwareNodeParser:
    """工厂：``rag_engine`` 的 build / load / add 三条路径统一由此获取切分器。"""
    enabled = bool(CODE_AWARE_CHUNKING) if code_enabled is None else bool(code_enabled)
    return LanguageAwareNodeParser(
        text_splitter=SentenceSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap),
        code_enabled=enabled and is_available(),
        max_chars=CODE_CHUNK_MAX_CHARS,
        min_chars=CODE_CHUNK_MIN_CHARS,
    )


__all__ = [
    "LANGUAGE_MAP",
    "CODE_EXTENSIONS",
    "LanguageAwareNodeParser",
    "availability_hint_once",
    "availability_message",
    "build_node_parser",
    "format_ingest_summary",
    "dependency_version",
    "describe_file_chunking",
    "is_available",
    "is_enabled",
    "language_for",
    "reset_availability_cache",
    "reset_hint",
    "split_code",
    "status_text",
    "strategy_display",
    "strip_header",
    "summarize_nodes",
]
