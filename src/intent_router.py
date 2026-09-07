#!/usr/bin/env python3
"""intent_router.py — 入口智能路由（F8 P3-1）：判定自然语言输入应走 RAG 还是 Agent。

规则优先、LLM 兜底：

1. **Agent 信号**：文件/目录路径（``/x/y.py``、``./``、``~/``、``*.ext``）、代码围栏
   ```` ``` ````、命令式动词（修改/创建/运行/…、create/run/fix/…）。
2. **RAG 信号**：疑问句（？/吗/呢/什么/为什么/如何理解/是否）、"总结/比较/解释/介绍/
   区别/优缺点"、以"什么是"开头。
3. 两类都命中或都不命中 → **模糊**：知识库不可用时直接 agent（不调 LLM）；否则一次
   LLM 一词判定（``think=False``、``num_predict=4``、``timeout=5``），异常/超时/输出
   不是 ``rag``/``agent`` 一律回退 ``rag``。

规则表为模块常量，便于扩展；``classify_intent`` 返回 ``RouteDecision``（``mode`` +
``reason``），``mode`` 只会是 ``"rag"`` 或 ``"agent"``。
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Callable, Optional

logger = logging.getLogger(__name__)

# ==================== 规则表（可扩展） ====================

# 文件/目录路径：绝对/相对/家目录路径、带扩展名的文件、通配符文件
PATH_PATTERNS = (
    r"(?<![\w:])/[\w.\-]+(?:/[\w.\-]+)*\.\w{1,6}\b",   # /x/y.py（排除 URL 的 ://）
    r"(?<![\w:])/[\w.\-]+/[\w.\-]*",                      # /usr/local 这类目录路径
    r"(?:^|\s)\.{1,2}/[\w.\-/]*",                        # ./src  ../x
    r"(?:^|\s)~/[\w.\-/]*",                              # ~/proj
    r"\*\.\w{1,6}\b",                                    # *.py
    r"\b[\w\-]+\.(?:py|js|ts|tsx|jsx|java|go|rs|c|cpp|h|hpp|cs|rb|php|sh|bash|zsh|"
    r"yaml|yml|toml|ini|cfg|json|xml|html|css|scss|sql|md|txt|csv|log|env|lock|"
    r"dockerfile|makefile|gradle|swift|kt|m|mm|vue|svelte)\b",  # main.py / app.ts
)

CODE_FENCE = "```"

# 命令式动词（中文按子串匹配；英文按词边界匹配）
AGENT_VERBS_ZH = (
    "修改", "创建", "新建", "运行", "执行", "重命名", "删除", "安装", "写一个", "写个",
    "实现", "修复", "重构", "生成文件", "提交", "部署", "帮我改", "帮我写", "加一个",
    "添加一个", "编写", "调试", "跑一下", "跑一遍", "移动", "复制", "卸载", "初始化",
)
AGENT_VERBS_EN = (
    "create", "run", "fix", "refactor", "implement", "install", "delete", "rename",
    "write a", "write an", "execute", "deploy", "commit", "remove", "generate a file",
    "modify", "edit", "add a", "compile", "debug",
)

# 疑问/知识查询信号（中文子串）
RAG_QUESTION_MARKS = ("?", "？")
RAG_QUESTION_WORDS_ZH = ("吗", "呢", "什么", "为什么", "如何理解", "是否", "怎么理解",
                         "哪些", "多少", "哪个", "何时", "是不是", "有没有")
RAG_TOPIC_WORDS_ZH = ("总结", "比较", "解释", "介绍", "区别", "优缺点", "概括", "概述",
                      "对比", "含义", "定义", "原理", "说明一下", "讲讲", "讲一下", "谈谈")
RAG_PREFIXES_ZH = ("什么是", "何谓", "请问", "介绍一下", "解释一下")
RAG_WORDS_EN = (
    "what is", "what are", "what's", "why", "how does", "how do", "how to understand",
    "explain", "summarize", "summary", "compare", "comparison", "difference", "differences",
    "pros and cons", "introduce", "overview", "describe", "tell me about", "who is",
    "when did", "where is", "which",
)

# LLM 一词判定提示词（REQUIREMENTS 附录 A）
INTENT_PROMPT = (
    "用户输入是「查询/理解知识」还是「让助手执行操作（改文件/跑命令/写代码）」？"
    "只输出一个词：rag 或 agent\n输入：{text}"
)
LLM_NUM_PREDICT = 4
LLM_TIMEOUT = 5

_URL_RE = re.compile(r"[a-z][a-z0-9+.\-]*://\S+", re.IGNORECASE)
_PATH_RES = tuple(re.compile(p, re.IGNORECASE) for p in PATH_PATTERNS)
_EN_VERB_RES = tuple(re.compile(r"(?<![\w-])" + re.escape(v) + r"(?![\w-])", re.IGNORECASE)
                     for v in AGENT_VERBS_EN)
_EN_RAG_RES = tuple(re.compile(r"(?<![\w-])" + re.escape(w) + r"(?![\w-])", re.IGNORECASE)
                    for w in RAG_WORDS_EN)


@dataclass(frozen=True)
class RouteDecision:
    """路由判定结果：``mode`` ∈ {"rag", "agent"}，``reason`` 为可展示的简短原因。"""
    mode: str
    reason: str

    def __iter__(self):  # 允许 ``mode, reason = classify_intent(...)``
        yield self.mode
        yield self.reason


# ==================== 规则匹配 ====================

def agent_signals(text: str) -> list:
    """返回命中的 Agent 信号描述列表（空列表表示未命中）。"""
    hits = []
    if not text:
        return hits
    if CODE_FENCE in text:
        hits.append("代码围栏")
    no_url = _URL_RE.sub(" ", text)  # URL 中的 /a/b.py 不算本地路径
    for rx in _PATH_RES:
        m = rx.search(no_url)
        if m:
            hits.append(f"路径 {m.group().strip()}")
            break
    for v in AGENT_VERBS_ZH:
        if v in text:
            hits.append(f"动词「{v}」")
            break
    else:
        for rx in _EN_VERB_RES:
            m = rx.search(text)
            if m:
                hits.append(f"动词「{m.group()}」")
                break
    return hits


def rag_signals(text: str) -> list:
    """返回命中的 RAG 信号描述列表（空列表表示未命中）。"""
    hits = []
    if not text:
        return hits
    stripped = text.strip()
    for p in RAG_PREFIXES_ZH:
        if stripped.startswith(p):
            hits.append(f"以「{p}」开头")
            break
    if any(stripped.endswith(m) or m in stripped for m in RAG_QUESTION_MARKS):
        hits.append("疑问句")
    else:
        for w in RAG_QUESTION_WORDS_ZH:
            if w in stripped:
                hits.append(f"疑问词「{w}」")
                break
    for w in RAG_TOPIC_WORDS_ZH:
        if w in stripped:
            hits.append(f"知识词「{w}」")
            break
    else:
        for rx in _EN_RAG_RES:
            m = rx.search(stripped)
            if m:
                hits.append(f"知识词「{m.group()}」")
                break
    return hits


# ==================== LLM 兜底 ====================

def _llm_complete(prompt: str, num_predict: int = LLM_NUM_PREDICT,
                  timeout: int = LLM_TIMEOUT) -> str:
    """默认 LLM 调用：``/api/chat`` 直连、``think=False``、限额输出；失败抛异常。"""
    from collaboration.llm_helper import complete_text
    return complete_text(prompt, num_predict=num_predict, timeout=timeout)


default_llm_complete = _llm_complete  # 稳定别名：测试打桩 ``_llm_complete`` 后仍可取到原实现


def parse_intent_word(raw: str) -> Optional[str]:
    """把 LLM 输出解析为 ``"rag"``/``"agent"``；无法识别返回 None。"""
    if not raw:
        return None
    text = raw.strip().lower()
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()
    m = re.search(r"\b(rag|agent)\b", text)
    return m.group(1) if m else None


def llm_classify(text: str, complete: Optional[Callable[..., str]] = None) -> Optional[str]:
    """一次 LLM 一词判定；异常/超时/乱输出返回 None（由调用方回退）。"""
    fn = complete or _llm_complete
    prompt = INTENT_PROMPT.format(text=(text or "").strip()[:500])
    try:
        raw = fn(prompt, num_predict=LLM_NUM_PREDICT, timeout=LLM_TIMEOUT)
    except Exception as e:  # noqa: BLE001
        logger.debug("intent LLM 判定失败: %s", e)
        return None
    return parse_intent_word(raw)


# ==================== 入口 ====================

def classify_intent(text: str, kb_available: bool = True,
                    complete: Optional[Callable[..., str]] = None) -> RouteDecision:
    """判定自然语言输入应走 ``rag`` 还是 ``agent``。

    :param text: 用户输入
    :param kb_available: 知识库是否可用（False 且模糊 → agent，不调 LLM）
    :param complete: 可注入的 LLM 调用 ``fn(prompt, num_predict=, timeout=) -> str``
    """
    a_hits = agent_signals(text)
    r_hits = rag_signals(text)

    if a_hits and not r_hits:
        return RouteDecision("agent", "规则：" + "、".join(a_hits))
    if r_hits and not a_hits:
        return RouteDecision("rag", "规则：" + "、".join(r_hits))

    ambiguity = "规则冲突" if (a_hits and r_hits) else "无明确信号"
    if not kb_available:
        return RouteDecision("agent", f"{ambiguity}，知识库不可用")

    word = llm_classify(text, complete=complete)
    if word in ("rag", "agent"):
        return RouteDecision(word, f"{ambiguity}，LLM 判定")
    return RouteDecision("rag", f"{ambiguity}，LLM 不可用，默认 RAG")


__all__ = [
    "RouteDecision", "classify_intent", "agent_signals", "rag_signals",
    "llm_classify", "parse_intent_word", "INTENT_PROMPT", "LLM_NUM_PREDICT", "LLM_TIMEOUT",
]
