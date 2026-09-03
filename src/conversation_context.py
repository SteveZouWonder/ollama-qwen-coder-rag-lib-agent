"""连续对话上下文：会话为唯一真源的记忆读写、token 预算裁剪与滚动压缩。

背景：此前 ReAct 用全局单文件 ChatHistory（按条数截断、系统提示落盘、
CLI/所有 Web 标签页共用），RAG / 多 Agent 则完全无状态，追问"它多少钱"
无法解析。本模块把三种模式的对话记忆统一到 ``SessionManager`` 的会话上：

- **ContextBuilder**：输入会话 + token 预算，输出
  ``[系统提示] + [滚动摘要] + [最近 K 轮原文]``。token 用字符启发式估算
  （中文≈1 token/1.5 字，英文≈4 字符/token，偏保守），不依赖 tokenizer。
- **自动压缩**：历史估算超预算 70% 时，用同一模型（强制 think=False）把最旧
  轮次合并进滚动摘要，仅保留最近 K 轮原文；LLM 不可用时退化为启发式摘要。
- **问题改写**：会话有历史且问题疑似追问（指代词/承接词或很短）时，把问题
  改写为独立问题供检索/联网/相关性判定/综合使用；首轮/独立问题零开销。
- **health()**：纯函数返回上下文指标与 ``suggest_new_session``，供前端提示
  "对话过长，建议新会话"。
- **携带摘要**：新建会话时可把当前滚动摘要作为新会话的首条背景。
- **一次性迁移**：把旧的 ``~/.code_agent_history.json`` 迁入默认会话后归档。

本模块不 import rich / gradio，不直接 print；进度通过可选回调发出结构化事件
``{"stage": ..., "message": ...}``，与 ``rag_pipeline`` 的事件约定一致。
"""
from __future__ import annotations

import json
import logging
import math
import os
import re
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

ProgressCallback = Optional[Callable[[Dict[str, Any]], None]]
CompleteFn = Callable[[str], str]

# 会话 metadata 中存放上下文状态的键
META_KEY = "context"

# 滚动摘要的目标长度（字），以及硬截断上限
SUMMARY_TARGET_CHARS = 300
SUMMARY_MAX_CHARS = 600

# 单条历史消息放进上下文前的截断长度（字符），避免一条超长回答吃掉全部预算
MESSAGE_MAX_CHARS = 1500

# 疑似"追问"的线索词：指代/承接/省略主语等
_FOLLOWUP_CUES_CJK = (
    "它", "这", "那", "刚才", "刚刚", "继续", "还有", "呢", "为什么", "上面", "前面",
    "之前", "其中", "他们", "另外", "那么", "展开说", "再说",
)
_FOLLOWUP_CUES_EN = (
    "it", "its", "this", "that", "these", "those", "they", "them", "why", "then",
    "also", "more", "again", "above", "previous", "elaborate", "how about", "what about",
)
_FOLLOWUP_SHORT_LEN = 12

_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
_WORD_RE = re.compile(r"[a-zA-Z0-9_]{2,}")


# ==================== 进度事件 ====================


def _emit(cb: ProgressCallback, stage: str, message: str = "", **extra: Any) -> None:
    if cb is None:
        return
    try:
        event: Dict[str, Any] = {"stage": stage, "message": message}
        event.update(extra)
        cb(event)
    except Exception as e:  # noqa: BLE001
        logger.debug(f"progress callback error: {e}")


# ==================== token 估算 ====================


def estimate_tokens(text: Any) -> int:
    """字符启发式估算 token 数（偏保守，宁多算不少算）。

    中文等 CJK 字符约 1.5 字/token，其余字符约 4 字符/token；两部分分别向上
    取整。空文本返回 0。
    """
    if not text:
        return 0
    text = str(text)
    cjk = len(_CJK_RE.findall(text))
    other = len(text) - cjk
    return int(math.ceil(cjk / 1.5)) + int(math.ceil(other / 4))


def estimate_messages_tokens(messages: List[Dict[str, Any]]) -> int:
    """估算一组消息的 token 数（每条附加 4 token 的角色/分隔开销）。"""
    total = 0
    for m in messages or []:
        if not isinstance(m, dict):
            continue
        total += estimate_tokens(m.get("content", "")) + 4
    return total


def format_tokens(n: int) -> str:
    """把 token 数渲染为 ``950`` / ``3.2K`` 形式。"""
    n = max(0, int(n or 0))
    if n < 1000:
        return str(n)
    return f"{n / 1000:.1f}K"


# ==================== 追问 / 话题漂移启发式 ====================


def is_followup(question: str) -> bool:
    """问题是否疑似"追问"（依赖上文才能理解）。

    命中任一条件即视为追问：含指代/承接线索词；或去掉标点后长度 < 12 字。
    仅在会话已有历史时才有意义，由调用方保证。
    """
    q = (question or "").strip()
    if not q:
        return False
    stripped = re.sub(r"[\s\W_]+", "", q)
    if len(stripped) < _FOLLOWUP_SHORT_LEN:
        return True
    if any(cue in q for cue in _FOLLOWUP_CUES_CJK):
        return True
    lowered = q.lower()
    words = set(re.findall(r"[a-z']+", lowered))
    for cue in _FOLLOWUP_CUES_EN:
        if " " in cue:
            if cue in lowered:
                return True
        elif cue in words:
            return True
    return False


def _keywords(text: str) -> set:
    """轻量关键词集合：英文/数字词（≥2 字符）+ 中文双字组合。"""
    if not text:
        return set()
    keys = set(w.lower() for w in _WORD_RE.findall(text))
    cjk_chars = _CJK_RE.findall(text)
    for i in range(len(cjk_chars) - 1):
        keys.add(cjk_chars[i] + cjk_chars[i + 1])
    return keys


def topic_drift(question: str, recent_messages: List[Dict[str, Any]]) -> bool:
    """当前问题与最近几轮是否毫无实体/关键词重叠且不是追问句式。

    不调用 LLM。历史为空、问题为空或问题本身像追问时一律返回 False。
    """
    q = (question or "").strip()
    if not q or not recent_messages:
        return False
    if is_followup(q):
        return False
    q_keys = _keywords(q)
    if not q_keys:
        return False
    hist_keys: set = set()
    for m in recent_messages:
        if isinstance(m, dict):
            hist_keys |= _keywords(str(m.get("content", "")))
    if not hist_keys:
        return False
    return not (q_keys & hist_keys)


# ==================== LLM 调用（强制 think=False）====================


def _default_complete(prompt: str) -> str:
    """用全局唯一模型做一次补全：直连 Ollama /api/chat 并强制 ``think=False``。

    压缩/改写是纯工具性调用，不需要思维链；显式关闭思考模式避免 4B 模型为
    一句摘要生成上千 token。失败抛出异常，由调用方决定回退。
    """
    import requests
    from config import Config

    try:
        import config as _cfg
        model = getattr(_cfg, "LLM_MODEL", Config.LLM_MODEL)
        num_ctx = int(getattr(_cfg, "LLM_NUM_CTX", 8192))
    except Exception:  # noqa: BLE001
        model, num_ctx = Config.LLM_MODEL, 8192

    resp = requests.post(
        Config.OLLAMA_HOST + "/api/chat",
        json={
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "think": False,
            "options": {"temperature": 0.2, "num_ctx": num_ctx, "num_predict": 512},
        },
        timeout=Config.TIMEOUT,
    )
    resp.raise_for_status()
    return str(resp.json().get("message", {}).get("content", "")).strip()


def resolve_num_ctx() -> int:
    """读取当前全局模型的上下文窗口（模型热切换后自动跟随）。"""
    try:
        import config as _cfg
        return int(getattr(_cfg, "LLM_NUM_CTX", 8192))
    except Exception:  # noqa: BLE001
        return 8192


def _cfg(name: str, default: Any) -> Any:
    try:
        import config as _c
        return getattr(_c, name, default)
    except Exception:  # noqa: BLE001
        return default


# ==================== 核心：会话上下文 ====================


class ConversationContext:
    """绑定到某个会话（或"当前会话"）的对话记忆读写器。

    Args:
        session_manager: SessionManager 实例；为空时使用进程内单例。
        session_id: 目标会话 ID；为空表示跟随管理器的"当前会话"。
        num_ctx: 模型上下文窗口；为空时按全局模型自动读取。
        ratio: 历史预算占 num_ctx 的比例；为空时读配置 CONTEXT_HISTORY_RATIO。
        recent_turns: 以原文保留的最近轮数 K。
        complete: LLM 补全函数（prompt -> text），便于测试注入；默认直连 Ollama。
    """

    def __init__(
        self,
        session_manager=None,
        session_id: Optional[str] = None,
        *,
        num_ctx: Optional[int] = None,
        ratio: Optional[float] = None,
        recent_turns: Optional[int] = None,
        complete: Optional[CompleteFn] = None,
    ):
        if session_manager is None:
            from session_manager import get_session_manager
            session_manager = get_session_manager()
        self.manager = session_manager
        self.session_id = session_id
        self._num_ctx = num_ctx
        self._ratio = ratio
        self.recent_turns = int(recent_turns or _cfg("CONTEXT_RECENT_TURNS", 3))
        self._complete: CompleteFn = complete or _default_complete

    # ---------- 预算 ----------

    @property
    def num_ctx(self) -> int:
        return int(self._num_ctx or resolve_num_ctx())

    @property
    def budget(self) -> int:
        ratio = self._ratio if self._ratio is not None else float(_cfg("CONTEXT_HISTORY_RATIO", 0.30))
        return max(256, int(self.num_ctx * ratio))

    # ---------- 会话访问 ----------

    def session(self, create: bool = True):
        """返回绑定的会话；``session_id`` 为空时取当前会话，必要时自动创建。"""
        if self.session_id:
            s = self.manager.get_session(self.session_id) if hasattr(self.manager, "get_session") \
                else getattr(self.manager, "sessions", {}).get(self.session_id)
            if s is not None:
                return s
        s = self.manager.get_current_session()
        if s is None and create:
            s = self.manager.create_session()
            logger.info(f"自动创建会话用于记录对话: {s.session_id}")
        if s is not None and self.session_id and s.session_id != self.session_id:
            # 绑定的会话已不存在：回落到当前会话并同步指针
            self.session_id = s.session_id
        return s

    def _meta(self, session) -> Dict[str, Any]:
        if not isinstance(session.metadata, dict):
            session.metadata = {}
        meta = session.metadata.get(META_KEY)
        if not isinstance(meta, dict):
            meta = {}
            session.metadata[META_KEY] = meta
        meta.setdefault("summary", "")
        meta.setdefault("summary_covers", 0)
        meta.setdefault("compressions", 0)
        meta.setdefault("suggested", False)
        meta.setdefault("only_compressions", False)
        meta.setdefault(
            "suggest_after_compressions",
            int(_cfg("CONTEXT_SUGGEST_NEW_AFTER_COMPRESSIONS", 2)),
        )
        return meta

    def _save(self, session) -> None:
        try:
            self.manager.save_session(session)
        except Exception as e:  # noqa: BLE001
            logger.error(f"保存会话失败: {e}")

    @staticmethod
    def _dialog(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return [
            m for m in (messages or [])
            if isinstance(m, dict) and m.get("role") in ("user", "assistant")
        ]

    def live_messages(self, session=None) -> List[Dict[str, Any]]:
        """尚未折叠进摘要的对话消息（user/assistant）。"""
        session = session or self.session(create=False)
        if session is None:
            return []
        meta = self._meta(session)
        covers = int(meta.get("summary_covers", 0) or 0)
        return self._dialog(session.messages[covers:])

    def all_messages(self) -> List[Dict[str, Any]]:
        """会话内全部对话消息（供前端多轮展示）。"""
        session = self.session(create=False)
        if session is None:
            return []
        return self._dialog(session.messages)

    def has_history(self) -> bool:
        session = self.session(create=False)
        if session is None:
            return False
        if self._meta(session).get("summary"):
            return True
        return bool(self.live_messages(session))

    @staticmethod
    def _turns(messages: List[Dict[str, Any]]) -> List[List[Dict[str, Any]]]:
        """把消息按"用户提问开始的一轮"分组。"""
        turns: List[List[Dict[str, Any]]] = []
        for m in messages:
            if m.get("role") == "user" or not turns:
                turns.append([m])
            else:
                turns[-1].append(m)
        return turns

    # ---------- 记录 ----------

    def record(
        self,
        user_content: str,
        assistant_content: str,
        *,
        trace: Optional[str] = None,
        rewritten: Optional[str] = None,
        progress: ProgressCallback = None,
    ) -> None:
        """写入一轮对话并按需自动压缩。

        Args:
            trace: ReAct 等模式的一句执行摘要（如"调用 read_file、execute_command 共 3 步"）。
            rewritten: RAG 改写后的独立问题（仅记录，便于回看）。
        """
        session = self.session(create=True)
        now = datetime.now().isoformat()
        if user_content:
            msg: Dict[str, Any] = {"role": "user", "content": str(user_content), "timestamp": now}
            if rewritten and rewritten != user_content:
                msg["rewritten"] = rewritten
            session.messages.append(msg)
        if assistant_content:
            msg = {"role": "assistant", "content": str(assistant_content), "timestamp": now}
            if trace:
                msg["trace"] = str(trace)
            session.messages.append(msg)
        session.updated_at = datetime.now()
        self._save(session)
        self.maybe_compress(progress=progress)

    # ---------- 构建上下文 ----------

    @staticmethod
    def _compact_content(m: Dict[str, Any]) -> str:
        content = str(m.get("content", "")).strip()
        if len(content) > MESSAGE_MAX_CHARS:
            content = content[:MESSAGE_MAX_CHARS] + "…（已截断）"
        trace = m.get("trace")
        if trace and m.get("role") == "assistant":
            content += f"\n[执行摘要: {trace}]"
        return content

    def build_messages(self, system_prompt: Optional[str] = None) -> List[Dict[str, str]]:
        """输出 ``[系统提示] + [滚动摘要] + [最近 K 轮原文]``（不含本轮新问题）。"""
        out: List[Dict[str, str]] = []
        if system_prompt:
            out.append({"role": "system", "content": system_prompt})
        session = self.session(create=False)
        if session is None:
            return out
        meta = self._meta(session)
        summary = (meta.get("summary") or "").strip()
        if summary:
            out.append({
                "role": "system",
                "content": f"以下是此前对话的滚动摘要（供理解指代与延续上下文）：\n{summary}",
            })
        live = self.live_messages(session)
        turns = self._turns(live)
        recent = turns[-self.recent_turns:] if self.recent_turns > 0 else []
        recent_msgs = [
            {"role": m["role"], "content": self._compact_content(m)}
            for turn in recent for m in turn
        ]
        # 预算硬上限：即使最近 K 轮本身就超预算，也从最旧一轮起裁掉（至少保留 1 轮）
        base_tokens = estimate_messages_tokens(out)
        while len(recent) > 1 and base_tokens + estimate_messages_tokens(recent_msgs) > self.budget:
            dropped = len(recent[0])
            recent = recent[1:]
            recent_msgs = recent_msgs[dropped:]
        out.extend(recent_msgs)
        return out

    def history_text(self, turns: int = 3, max_chars: int = 400) -> str:
        """最近若干轮的紧凑文本（供 RAG 综合 prompt / 改写 prompt 使用）。"""
        session = self.session(create=False)
        if session is None:
            return ""
        parts: List[str] = []
        summary = (self._meta(session).get("summary") or "").strip()
        if summary:
            parts.append(f"[更早对话摘要] {summary}")
        live_turns = self._turns(self.live_messages(session))
        for turn in live_turns[-turns:]:
            for m in turn:
                role = "用户" if m.get("role") == "user" else "助手"
                content = str(m.get("content", "")).replace("\n", " ").strip()
                if len(content) > max_chars:
                    content = content[:max_chars] + "…"
                parts.append(f"{role}: {content}")
        return "\n".join(parts)

    # ---------- 指标 ----------

    def metrics(self) -> Dict[str, Any]:
        """当前上下文指标：轮数 / 估算 token / 预算 / 压缩次数 / 摘要预览。"""
        session = self.session(create=False)
        budget = self.budget
        if session is None:
            return {
                "session_id": None, "turns": 0, "messages": 0, "history_tokens": 0,
                "budget": budget, "usage_ratio": 0.0, "compressions": 0,
                "summary": "", "summary_tokens": 0, "num_ctx": self.num_ctx,
            }
        meta = self._meta(session)
        built = self.build_messages()
        tokens = estimate_messages_tokens(built)
        live = self.live_messages(session)
        return {
            "session_id": session.session_id,
            "title": session.title,
            "turns": len(self._turns(live)),
            "messages": len(self._dialog(session.messages)),
            "history_tokens": tokens,
            "budget": budget,
            "usage_ratio": (tokens / budget) if budget else 0.0,
            "compressions": int(meta.get("compressions", 0) or 0),
            "summary": meta.get("summary") or "",
            "summary_tokens": estimate_tokens(meta.get("summary") or ""),
            "num_ctx": self.num_ctx,
        }

    # ---------- 压缩 ----------

    def _live_tokens(self, session) -> int:
        return estimate_messages_tokens(self.build_messages()) if session else 0

    def maybe_compress(self, progress: ProgressCallback = None) -> bool:
        """历史估算超过预算阈值（默认 70%）时自动压缩；返回是否压缩了。"""
        session = self.session(create=False)
        if session is None:
            return False
        threshold = float(_cfg("CONTEXT_COMPRESS_THRESHOLD", 0.70))
        # 用"全部 live 消息"而非"最近 K 轮"衡量，避免超预算但永不触发
        live = self.live_messages(session)
        summary_tokens = estimate_tokens(self._meta(session).get("summary") or "")
        if estimate_messages_tokens(live) + summary_tokens <= self.budget * threshold:
            return False
        return self.compact(progress=progress) is not None

    def compact(self, progress: ProgressCallback = None) -> Optional[Dict[str, Any]]:
        """手动压缩：把最近 K 轮之前的全部原文折叠进滚动摘要。

        Returns:
            ``{"folded_messages": n, "summary": str, "compressions": n}``；
            没有可折叠的内容时返回 None。
        """
        session = self.session(create=False)
        if session is None:
            return None
        meta = self._meta(session)
        covers = int(meta.get("summary_covers", 0) or 0)
        live = self.live_messages(session)
        turns = self._turns(live)
        if len(turns) <= self.recent_turns:
            return None
        to_fold_turns = turns[:-self.recent_turns] if self.recent_turns > 0 else turns
        to_fold = [m for t in to_fold_turns for m in t]
        if not to_fold:
            return None

        _emit(progress, "context_compress", "🗜️ 压缩历史上下文…")
        new_summary = self._summarize(meta.get("summary") or "", to_fold)

        # 推进 summary_covers：找到最后一条被折叠消息在 session.messages 中的位置
        target = to_fold[-1]
        new_covers = covers
        for idx in range(covers, len(session.messages)):
            if session.messages[idx] is target:
                new_covers = idx + 1
                break
        else:
            new_covers = covers + len(to_fold)

        meta["summary"] = new_summary
        meta["summary_covers"] = new_covers
        meta["compressions"] = int(meta.get("compressions", 0) or 0) + 1
        self._save(session)
        _emit(
            progress, "context_compressed",
            f"🗜️ 已压缩历史上下文（第 {meta['compressions']} 次，折叠 {len(to_fold)} 条消息）",
            compressions=meta["compressions"], folded=len(to_fold),
        )
        return {
            "folded_messages": len(to_fold),
            "summary": new_summary,
            "compressions": meta["compressions"],
        }

    def _summarize(self, previous: str, messages: List[Dict[str, Any]]) -> str:
        """用 LLM 把旧摘要 + 待折叠消息合并为新的滚动摘要；失败退化为启发式。"""
        lines = []
        for m in messages:
            role = "用户" if m.get("role") == "user" else "助手"
            content = str(m.get("content", "")).replace("\n", " ").strip()
            if len(content) > 800:
                content = content[:800] + "…"
            lines.append(f"{role}: {content}")
        transcript = "\n".join(lines)
        prompt = (
            "你是对话记忆压缩器。请把「已有摘要」与「新增对话」合并成一段连贯的中文滚动摘要，"
            f"不超过 {SUMMARY_TARGET_CHARS} 字。必须保留：用户的目标与偏好、关键实体/数字/"
            "文件名/产品名、已得出的结论、尚未解决的问题。不要添加评论，不要使用列表符号，"
            "只输出摘要正文。\n\n"
            f"【已有摘要】\n{previous or '（无）'}\n\n"
            f"【新增对话】\n{transcript}"
        )
        try:
            result = (self._complete(prompt) or "").strip()
            result = _strip_think(result)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"LLM 压缩历史失败，退化为启发式摘要: {e}")
            result = ""
        if not result:
            result = _heuristic_summary(previous, messages)
        if len(result) > SUMMARY_MAX_CHARS:
            result = result[:SUMMARY_MAX_CHARS] + "…"
        return result

    # ---------- 问题改写 ----------

    def rewrite_question(self, question: str, progress: ProgressCallback = None) -> Dict[str, Any]:
        """若疑似追问，则结合最近对话把问题改写为独立问题。

        Returns:
            ``{"question": 用于检索的问题, "original": 原问题, "changed": bool}``
        """
        question = (question or "").strip()
        result = {"question": question, "original": question, "changed": False}
        if not question or not self.has_history() or not is_followup(question):
            return result
        history = self.history_text(turns=3, max_chars=300)
        if not history:
            return result
        _emit(progress, "context_rewrite", "🔗 结合上下文理解问题…")
        prompt = (
            "下面是一段对话的最近内容，以及用户的最新问题。最新问题可能省略了主语或使用了"
            "指代（如“它”“这个”“刚才那个”）。请把最新问题改写成一个不依赖上文、可独立理解"
            "的完整问题：补全被指代的对象名称与必要限定条件，保持原意与语言，不要回答问题，"
            "不要添加解释。若问题本身已经独立完整，原样输出。只输出改写后的问题一行。\n\n"
            f"【最近对话】\n{history}\n\n"
            f"【最新问题】\n{question}"
        )
        try:
            raw = (self._complete(prompt) or "").strip()
            raw = _strip_think(raw)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"LLM 问题改写失败，沿用原问题: {e}")
            return result
        rewritten = _clean_single_line(raw)
        if not rewritten or rewritten == question or len(rewritten) > 300:
            return result
        result.update({"question": rewritten, "changed": True})
        _emit(progress, "context_rewritten", f"🔗 已理解为：{rewritten}", rewritten=rewritten)
        return result

    # ---------- 健康度 / 新会话建议 ----------

    def health(self, question: Optional[str] = None) -> Dict[str, Any]:
        """纯函数：返回上下文指标与是否建议新建会话（不修改任何状态）。

        触发条件任一满足即建议（每会话只提示一次；用户选择继续后仅当压缩次数
        再增加 2 才再次提示）：
        - 压缩次数 ≥ 阈值（默认 2）；
        - 历史占预算 ≥ 90% 且已压缩过；
        - 话题漂移：当前问题与最近 3 轮无关键词重叠且非追问句式；
        - 距上一条消息超过 CONTEXT_SUGGEST_IDLE_HOURS（默认 6）小时。
        """
        m = self.metrics()
        session = self.session(create=False)
        reasons: List[str] = []
        idle_hours = 0.0
        if session is not None:
            meta = self._meta(session)
            compressions = m["compressions"]
            after = int(meta.get("suggest_after_compressions", 2) or 2)
            if compressions >= after:
                reasons.append("compressions")
            only_comp = bool(meta.get("only_compressions"))
            if not only_comp:
                if m["usage_ratio"] >= 0.9 and compressions >= 1:
                    reasons.append("usage")
                live = self.live_messages(session)
                turns = self._turns(live)
                # 若问题已被记录为最后一轮，则与其之前的轮次比较
                if question and turns and turns[-1] and turns[-1][0].get("content") == question:
                    turns = turns[:-1]
                recent = [mm for t in turns[-3:] for mm in t]
                if question and topic_drift(question, recent):
                    reasons.append("topic_drift")
                last = self._last_timestamp(session, exclude_content=question)
                if last is not None:
                    idle_hours = max(0.0, (datetime.now() - last).total_seconds() / 3600)
                    if idle_hours > float(_cfg("CONTEXT_SUGGEST_IDLE_HOURS", 6)):
                        reasons.append("idle")
            suggested_before = bool(meta.get("suggested"))
        else:
            suggested_before = False
        m.update({
            "reasons": reasons,
            "idle_hours": round(idle_hours, 2),
            "suggest_new_session": bool(reasons) and not suggested_before,
        })
        return m

    def _last_timestamp(self, session, exclude_content: Optional[str] = None) -> Optional[datetime]:
        msgs = self._dialog(session.messages)
        # 若最后一轮就是当前问题（已记录），跳过它以衡量"上一条消息"的空闲时长
        if exclude_content and msgs:
            idx = len(msgs) - 1
            while idx >= 0 and msgs[idx].get("role") == "assistant":
                idx -= 1
            if idx >= 0 and msgs[idx].get("content") == exclude_content:
                msgs = msgs[:idx]
        for mm in reversed(msgs):
            ts = mm.get("timestamp")
            if ts:
                try:
                    return datetime.fromisoformat(ts)
                except ValueError:
                    continue
        return None

    def mark_suggested(self) -> None:
        """前端已展示"建议新会话"提示：本会话不再重复提示。"""
        session = self.session(create=False)
        if session is None:
            return
        meta = self._meta(session)
        meta["suggested"] = True
        self._save(session)

    def continue_current(self) -> None:
        """用户选择"继续当前会话"：仅当压缩次数再 +2 时才再次提示。"""
        session = self.session(create=False)
        if session is None:
            return
        meta = self._meta(session)
        meta["suggested"] = False
        meta["only_compressions"] = True
        meta["suggest_after_compressions"] = int(meta.get("compressions", 0) or 0) + 2
        self._save(session)

    # ---------- 清空 / 新建 ----------

    def clear(self) -> bool:
        """清空当前会话的对话消息与上下文状态（会话本身保留）。"""
        session = self.session(create=False)
        if session is None:
            return False
        session.messages = []
        session.metadata[META_KEY] = {}
        self._meta(session)
        session.updated_at = datetime.now()
        self._save(session)
        return True

    def carry_summary_text(self) -> str:
        """当前会话可携带到新会话的背景摘要（约 200-300 token）。"""
        session = self.session(create=False)
        if session is None:
            return ""
        meta = self._meta(session)
        summary = (meta.get("summary") or "").strip()
        live = self.live_messages(session)
        if live:
            # 把仍以原文保留的最近几轮也并入携带摘要（启发式，不调 LLM）
            tail = _heuristic_summary("", live)
            summary = (summary + " " + tail).strip() if summary else tail
        if len(summary) > 450:
            summary = summary[:450] + "…"
        return summary

    def new_session(self, title: Optional[str] = None, carry_summary: bool = False):
        """新建会话并切换；``carry_summary`` 为真时把当前滚动摘要作为新会话背景。"""
        carried = self.carry_summary_text() if carry_summary else ""
        session = self.manager.create_session(title=title or None)
        self.session_id = session.session_id
        if carried:
            meta = self._meta(session)
            meta["summary"] = f"（承接自上一会话）{carried}"
            meta["summary_covers"] = 0
            self._save(session)
        return session


# ==================== 辅助 ====================


def _strip_think(text: str) -> str:
    """去掉模型可能输出的 <think>…</think> 段。"""
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()


def _clean_single_line(text: str) -> str:
    """取 LLM 输出的首个非空行，去掉引号/前缀标签。"""
    quotes = '"“”\'「」'
    for line in (text or "").splitlines():
        line = line.strip().strip(quotes)
        line = re.sub(r"^(改写后的问题|改写|问题|Question)\s*[:：]\s*", "", line).strip().strip(quotes)
        if line:
            return line
    return ""


def _heuristic_summary(previous: str, messages: List[Dict[str, Any]]) -> str:
    """LLM 不可用时的退化摘要：拼接每条消息的开头。"""
    parts: List[str] = []
    if previous:
        parts.append(previous.strip())
    for m in messages:
        content = str(m.get("content", "")).replace("\n", " ").strip()
        if not content:
            continue
        if m.get("role") == "user":
            parts.append("用户问：" + content[:60])
        else:
            parts.append("助手答：" + content[:90])
    text = "；".join(parts)
    if len(text) > SUMMARY_MAX_CHARS:
        text = text[:SUMMARY_MAX_CHARS] + "…"
    return text


def merge_health(pre: Dict[str, Any], post: Dict[str, Any]) -> Dict[str, Any]:
    """合并"提问前"（可判空闲/漂移）与"记录后"（压缩计数已更新）的两次 health。"""
    merged = dict(post or {})
    reasons = list(dict.fromkeys(list((pre or {}).get("reasons", [])) + list((post or {}).get("reasons", []))))
    merged["reasons"] = reasons
    merged["suggest_new_session"] = bool(
        (pre or {}).get("suggest_new_session") or (post or {}).get("suggest_new_session")
    )
    if pre and pre.get("idle_hours"):
        merged["idle_hours"] = pre["idle_hours"]
    return merged


def format_context_status(m: Dict[str, Any]) -> str:
    """一行状态：``上下文 3.2K / 4.8K · 已压缩 1 次``。"""
    if not m:
        return ""
    line = f"上下文 {format_tokens(m.get('history_tokens', 0))} / {format_tokens(m.get('budget', 0))}"
    comp = int(m.get("compressions", 0) or 0)
    if comp:
        line += f" · 已压缩 {comp} 次"
    return line


def format_suggest_hint(h: Dict[str, Any]) -> str:
    """把 health 结果渲染成一句提示；未建议时返回空串。"""
    if not h or not h.get("suggest_new_session"):
        return ""
    reasons = h.get("reasons", [])
    comp = int(h.get("compressions", 0) or 0)
    if "idle" in reasons:
        why = f"距上次对话已超过 {int(h.get('idle_hours', 0))} 小时"
    elif "topic_drift" in reasons:
        why = "话题似乎已切换"
    elif comp:
        why = f"对话较长（已压缩 {comp} 次）"
    else:
        why = "对话较长"
    return f"💡 {why}，建议新建会话以获得更好的回答质量"


# ==================== 旧历史文件迁移 ====================


def migrate_legacy_history(history_file: Optional[str] = None, manager=None) -> int:
    """把旧版 ``~/.code_agent_history.json`` 一次性迁入默认会话并归档原文件。

    仅保留真实的用户提问与最终回答：跳过 system 消息、``Observation:`` 开头的
    工具反馈、含 ``Action:`` 的中间推理；``Final Answer:`` 前缀被去掉。
    返回迁移的消息条数（文件不存在/无有效内容返回 0）。
    """
    try:
        if history_file is None:
            from config import Config
            history_file = Config.HISTORY_FILE
        if not history_file or not os.path.exists(history_file):
            return 0
        with open(history_file, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"读取旧历史文件失败，跳过迁移: {e}")
        return 0

    messages: List[Dict[str, str]] = []
    for m in raw if isinstance(raw, list) else []:
        if not isinstance(m, dict):
            continue
        role, content = m.get("role"), str(m.get("content", "")).strip()
        if role == "user" and content and not content.startswith("Observation:"):
            messages.append({"role": "user", "content": content})
        elif role == "assistant" and content and "Action:" not in content:
            fm = re.search(r"Final Answer:\s*(.*)", content, re.DOTALL)
            messages.append({"role": "assistant", "content": (fm.group(1).strip() if fm else content)})

    try:
        if manager is None:
            from session_manager import get_session_manager
            manager = get_session_manager()
        if messages:
            prev_id = getattr(manager, "current_session_id", None)
            session = manager.create_session(title="默认会话（迁移自历史文件）")
            now = datetime.now().isoformat()
            for m in messages:
                session.messages.append({**m, "timestamp": now})
            manager.save_session(session)
            if prev_id:
                # 不抢占用户正在使用的会话：迁移会话仅作为历史保留
                manager.switch_session(prev_id)
        os.replace(history_file, history_file + ".migrated")
        logger.info(f"旧历史文件已迁移 {len(messages)} 条消息并归档: {history_file}.migrated")
    except Exception as e:  # noqa: BLE001
        logger.warning(f"迁移旧历史文件失败: {e}")
        return 0
    return len(messages)


# ==================== 模块级单例（CLI 与 rag_pipeline.record_conversation 使用）====================

_context_singleton: Optional[ConversationContext] = None


def get_conversation_context() -> ConversationContext:
    """进程内共享的、跟随"当前会话"的 ConversationContext；首次创建时迁移旧历史。"""
    global _context_singleton
    if _context_singleton is None:
        _context_singleton = ConversationContext()
        try:
            migrate_legacy_history(manager=_context_singleton.manager)
        except Exception:  # noqa: BLE001
            pass
    return _context_singleton


def reset_conversation_context() -> None:
    """重置单例（主要供测试使用）。"""
    global _context_singleton
    _context_singleton = None
