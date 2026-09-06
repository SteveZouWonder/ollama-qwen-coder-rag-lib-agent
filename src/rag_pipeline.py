"""共享 RAG 编排层：CLI 与 Web UI 复用的知识库问答核心逻辑。

本模块从 ``query_interface.py`` 下沉而来，目的是让 CLI 与 Web UI 在
"基础问答表现"上完全一致。此前这些高级编排（LLM 驱动的网络搜索规划、
多查询合并去重、页面正文增强、知识库/网络双区综合、元查询直答、0 命中
网络回退）只写在 CLI 层且深度耦合 Rich 终端输出，导致 Web 的 ``/ask``
只能裸调 ``query_with_sources``，答案质量与 CLI 差异极大。

设计要点：

1. **无终端依赖**：本模块不 import rich、不直接 ``print``。所有面向用户的
   进度提示都通过可选的 ``progress`` 回调发出结构化事件，由调用方
   （CLI 用 Rich 渲染，Web 桥接为 StreamEvent）决定如何展示。
2. **引擎作为参数**：``rag_engine`` 由调用方传入，而非模块级全局，便于测试
   与多实例复用。
3. **纯数据返回**：核心函数返回结构化 dict（``answer`` / ``kb_sources`` /
   ``web_sources`` / ``meta``），不做任何渲染。

进度事件（``progress`` 回调收到的 dict）约定：

    {"stage": <str>, "message": <str>, ...额外字段}

``stage`` 取值：``meta_overview`` | ``web_plan`` | ``web_search_start`` |
``web_query`` | ``web_query_empty`` | ``web_search_done`` | ``web_search_empty`` |
``web_search_failed`` | ``enrich_start`` | ``enrich_page_failed`` |
``enrich_done`` | ``kb_decompose`` | ``kb_retrieving`` | ``kb_merged`` |
``kb_low_relevance`` | ``rerank`` | ``rerank_done`` | ``rerank_fallback`` |
``kb_irrelevant`` | ``kb_empty`` | ``kb_fallback_search`` | ``synthesizing`` |
``model_thinking`` | ``thinking``（/think on 时的思维链，截断 800 字）|
``fallback``（知识库与网络均无结果）| ``kb_uninitialized`` 等。

返回 ``kind``：``meta``（知识库概览直答）| ``answer`` | ``fallback``（无相关片段且
网络无结果，``answer`` 末尾附「建议：/agent <原问题>」）。来源项带引用编号
``ref``（知识库 ``"1"``..，网络 ``"W1"``..），与答案中的 ``[i]``/``[Wj]`` 对应。

取消：``answer_question`` 接受可选 ``should_stop`` 回调（返回 True 表示用户
已请求停止）。编排层在每个阶段边界检查它，命中则抛出 ``PipelineCancelled``；
正在进行中的单次 LLM/网络调用无法被打断，但不会再进入下一阶段。
"""
from __future__ import annotations

import contextvars
import json
import logging
import re
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# 可选进度回调类型：接收一个结构化事件 dict。
ProgressCallback = Optional[Callable[[Dict[str, Any]], None]]

# 可选取消探针：返回 True 表示应尽快停止。
StopCheck = Optional[Callable[[], bool]]


class PipelineCancelled(Exception):
    """用户请求停止，编排在阶段边界主动中止。"""


def _emit(cb: ProgressCallback, stage: str, message: str = "", **extra: Any) -> None:
    """安全地向进度回调发送一个事件；回调为空或抛错都不影响主流程。"""
    if cb is None:
        return
    try:
        event = {"stage": stage, "message": message}
        if extra:
            event.update(extra)
        cb(event)
    except Exception as e:  # noqa: BLE001 - 进度回调失败不应中断主流程
        logger.debug(f"progress callback error: {e}")


def _check_stop(should_stop: StopCheck) -> None:
    """若取消探针返回 True 则抛出 ``PipelineCancelled``；探针异常视为未取消。"""
    if should_stop is None:
        return
    try:
        cancelled = bool(should_stop())
    except Exception:  # noqa: BLE001
        cancelled = False
    if cancelled:
        raise PipelineCancelled("用户已停止")


# ==================== LLM 基础调用 ====================


def _get_synthesis_llm():
    """获取用于"综合回答/相关性判定"的 LLM。

    自 单模型架构 起，全程只使用用户所选的唯一模型（全局 Settings.llm）：综合/
    判定与 Agent/代码任务共用同一模型，避免多模型同时驻留显存导致卡顿。该模型的
    上下文窗口已在创建时按规格自动设为安全值（见 config.resolve_num_ctx）。

    返回 None 表示"用全局 Settings.llm"，保留此函数与 _complete 的既有契约。
    """
    return None


def reset_synthesis_llm() -> None:
    """兼容保留（单模型架构下无独立综合模型缓存，此处为空操作）。"""
    return None


# 思维链透出：generate_answer 在 /think on 时把 progress 回调放进该上下文变量，
# _complete 拿到响应后从中抽取 thinking 并以 ``stage="thinking"`` 事件推送。
_THINKING_SINK: contextvars.ContextVar = contextvars.ContextVar("rag_thinking_sink", default=None)
THINKING_MAX_CHARS = 800


def extract_thinking(response: Any) -> str:
    """从 ``Settings.llm.complete`` 的响应中尽力取出思维链文本；取不到返回空串。

    依次尝试：``raw["message"]["thinking"]``（Ollama 原始响应）→
    ``additional_kwargs["thinking"]`` → ``message.blocks`` 中的 ``ThinkingBlock``。
    """
    if response is None or isinstance(response, str):
        return ""
    try:
        raw = getattr(response, "raw", None)
        if isinstance(raw, dict):
            msg = raw.get("message")
            if isinstance(msg, dict) and msg.get("thinking"):
                return str(msg["thinking"])
        extra = getattr(response, "additional_kwargs", None)
        if isinstance(extra, dict) and extra.get("thinking"):
            return str(extra["thinking"])
        message = getattr(response, "message", None)
        blocks = getattr(message, "blocks", None) if message is not None else None
        if blocks:
            parts = []
            for block in blocks:
                if type(block).__name__ == "ThinkingBlock" or getattr(block, "block_type", "") == "thinking":
                    content = getattr(block, "content", "")
                    if content:
                        parts.append(str(content))
            if parts:
                return "\n".join(parts)
    except Exception as e:  # noqa: BLE001
        logger.debug(f"extract thinking failed: {e}")
    return ""


def _emit_thinking(response: Any) -> None:
    sink = _THINKING_SINK.get()
    if sink is None:
        return
    thinking = extract_thinking(response).strip()
    if not thinking:
        return
    shown = thinking[:THINKING_MAX_CHARS] + ("…" if len(thinking) > THINKING_MAX_CHARS else "")
    _emit(sink, "thinking", f"🧠 模型思考：{shown}", thinking=shown, truncated=len(thinking) > THINKING_MAX_CHARS)


def _complete(prompt: str) -> str:
    """用全局唯一模型执行一次补全（/think on 时顺带透出思维链）。"""
    llm = _get_synthesis_llm()
    if llm is None:
        from llama_index.core import Settings
        llm = Settings.llm
    response = llm.complete(prompt)
    _emit_thinking(response)
    return str(response)


def llm_direct_answer(prompt: str) -> str:
    """用 LLM 直接回答（不经过知识库检索）。失败时返回错误说明。"""
    try:
        return _complete(prompt)
    except Exception as e:  # noqa: BLE001
        return f"回答失败：{e}"


# ==================== 网络搜索：LLM 驱动的通用查询规划 ====================

# 仅作为 LLM 不可用时的轻量回退触发词（不再承担主要判定职责）。
_WEB_SEARCH_FALLBACK_HINTS = (
    "最新", "当前", "今天", "现在", "实时", "发布", "新闻", "价格", "版本",
    "latest", "current", "today", "now", "release", "news", "price", "version",
)


def _strip_json_fence(text: str) -> str:
    """去除 LLM 输出中可能包裹的 ```json ... ``` 代码块围栏。"""
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines:
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return text


# 指向"国内信息"的语境词：命中则视为国内查询，不补英文查询（避免海外结果稀释
# 国内召回，如价格/售价问题应聚焦淘宝/京东/国行）。
_CN_QUERY_HINTS = (
    "国内", "中国", "国行", "大陆", "内地", "行货",
    "淘宝", "京东", "天猫", "拼多多", "苏宁", "闲鱼",
    "售价", "价格", "多少钱", "报价", "优惠", "促销", "补贴", "包邮",
    "人民币", "元起",
)


def _is_domestic_query(question: str) -> bool:
    """判断是否为面向国内的查询（含国内语境词，且整体是中文问题）。"""
    if not question:
        return False
    has_hint = any(h in question for h in _CN_QUERY_HINTS)
    # 含中文
    has_cjk = any("\u4e00" <= ch <= "\u9fff" for ch in question)
    return has_hint and has_cjk


def _is_mostly_ascii(text: str) -> bool:
    """判断一条查询是否基本为英文/ASCII（用于识别 LLM 补充的英文查询）。"""
    if not text:
        return False
    cjk = sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")
    return cjk == 0


# 复合问题最多拆成的子问题数
MAX_SUBQUESTIONS = 3


def _dedupe_strings(items: list) -> list:
    seen = set()
    out = []
    for q in items:
        if not isinstance(q, str):
            continue
        q = q.strip()
        if q and q.lower() not in seen:
            seen.add(q.lower())
            out.append(q)
    return out


def build_retrieval_plan_prompt(question: str) -> str:
    """附录 A「检索规划」提示词（与搜索规划合并为一次调用）。"""
    domestic = _is_domestic_query(question)
    if domestic:
        query_rule = (
            "若需要搜索，queries 给 1-2 条精简的**中文**搜索词（去掉'帮我''请问'等口语化"
            "前后缀，只保留核心检索词）。这是面向中国国内的查询，请勿生成英文查询。"
        )
    else:
        query_rule = (
            "若需要搜索，queries 给 1-3 条精简搜索词（去掉'帮我''请问'等口语化前后缀，"
            "只保留核心检索词）；若原问题为中文，可额外补一条等价英文查询提升召回。"
        )
    return (
        "分析问题，只输出 JSON：\n"
        '{"complex":是否需要拆成多个子问题才能回答,'
        '"subquestions":[最多3个,简单问题留空],'
        '"needs_search":是否需要联网获取最新/外部信息,'
        '"queries":[最多3个搜索词]}\n'
        "说明：complex 仅在问题涉及多个对象/多个事实需分别查找再综合时为 true"
        "（如\"A 与 B 的价格差多少\"拆为 A 的价格、B 的价格）；"
        "needs_search 仅在需要版本号、新闻、价格、近期事件等最新/外部信息时为 true，"
        "可凭通用知识回答或属于代码/写作/推理类任务时为 false。"
        + query_rule + "\n"
        f"问题：{question}"
    )


def plan_retrieval(question: str, progress: ProgressCallback = None) -> dict:
    """一次 LLM 调用完成检索规划：复合问题分解 + 是否联网 + 搜索词。

    这是整条链路的第一次模型调用：若模型尚未驻留内存，还会叠加加载时间；
    开启思考模式时更慢。因此在调用前先发 ``web_plan`` 进度事件，避免用户
    在这一步只能看到静态的"正在处理"而误以为卡死。

    Returns:
        ``{"complex": bool, "subquestions": [str...](≤3), "needs_search": bool,
           "queries": [str...]}``。subquestions/queries 已去重；``complex`` 为 True
        但子问题不足 2 个时降级为简单问题。对国内查询剔除英文搜索词。
        LLM 不可用时回退到轻量触发词（不分解）。
    """
    domestic = _is_domestic_query(question)
    prompt = build_retrieval_plan_prompt(question)

    _emit(progress, "web_plan", "🧭 规划检索策略（是否拆分子问题、是否联网、生成查询词）...")
    try:
        raw = _complete(prompt).strip()
        data = json.loads(_strip_json_fence(raw))
        if not isinstance(data, dict):
            raise ValueError("规划输出不是 JSON 对象")

        needs = bool(data.get("needs_search", False))
        queries = _dedupe_strings(data.get("queries") or [])
        # 国内查询：保险起见剔除 LLM 仍可能生成的英文查询（避免海外结果稀释）
        if domestic:
            filtered = [q for q in queries if not _is_mostly_ascii(q)]
            queries = filtered or queries  # 全被过滤则保底沿用
        if needs and not queries:
            queries = [question]

        subquestions = _dedupe_strings(data.get("subquestions") or [])[:MAX_SUBQUESTIONS]
        complex_ = bool(data.get("complex", False)) and len(subquestions) >= 2
        if not complex_:
            subquestions = []
        plan = {
            "complex": complex_,
            "subquestions": subquestions,
            "needs_search": needs,
            "queries": queries,
        }
        if complex_:
            _emit(
                progress, "kb_decompose",
                "🧩 复合问题，拆为 " + "；".join(f"{i}. {sq}" for i, sq in enumerate(subquestions, 1)),
                subquestions=subquestions,
            )
        return plan
    except Exception as e:  # noqa: BLE001 - LLM/JSON 失败时回退到启发式
        logger.warning(f"LLM 检索规划失败，回退到启发式判断: {e}")
        lowered = question.lower()
        needs = any(hint in lowered for hint in _WEB_SEARCH_FALLBACK_HINTS)
        return {
            "complex": False,
            "subquestions": [],
            "needs_search": needs,
            "queries": [question] if needs else [],
        }


def plan_web_search(question: str, progress: ProgressCallback = None) -> dict:
    """向后兼容封装：只返回搜索相关字段 ``{"needs_search", "queries"}``。

    内部调用 :func:`plan_retrieval`（同一次 LLM 调用），不产生额外开销。
    """
    plan = plan_retrieval(question, progress=progress)
    return {"needs_search": plan["needs_search"], "queries": plan["queries"]}


def run_web_search(queries: list, progress: ProgressCallback = None) -> str:
    """执行所有给定查询并合并有效结果文本；都失败返回空串。

    合并所有查询结果、跨查询去重，最大化把有用摘要送进后续 prompt。
    """
    try:
        from agent_tools import web_search
    except Exception as e:  # noqa: BLE001
        logger.error(f"无法导入 web_search: {e}")
        return ""

    blocks = []
    for query in queries:
        _emit(progress, "web_query", f"🔍 搜索查询: {query}", query=query)
        result = web_search(query, max_results=5, use_cache=False)
        if result and not result.startswith("[错误]") and not result.startswith("[提示]"):
            blocks.append((query, result))
        else:
            _emit(progress, "web_query_empty", f"⚠️ 查询 '{query}' 未返回结果", query=query)

    if not blocks:
        return ""
    if len(blocks) == 1:
        return blocks[0][1]
    return _merge_search_results(blocks)


def _merge_search_results(blocks: list) -> str:
    """合并多条查询的搜索结果文本，跨查询按 URL 去重后重新编号。"""
    merged = []  # [{title, url, extra: [其余行]}]
    seen_urls = set()
    for _query, text in blocks:
        current = None
        for line in text.splitlines():
            m_title = re.match(r"^\s*\d+\.\s+(.*)$", line)
            if m_title:
                if current and current["url"] and current["url"] not in seen_urls:
                    seen_urls.add(current["url"])
                    merged.append(current)
                current = {"title": m_title.group(1).strip(), "url": "", "extra": []}
                continue
            if current is None:
                continue
            m_url = re.match(r"^\s*URL:\s*(\S+)", line)
            if m_url:
                current["url"] = m_url.group(1)
                current["extra"].append(line.rstrip())
                continue
            current["extra"].append(line.rstrip())
        if current and current["url"] and current["url"] not in seen_urls:
            seen_urls.add(current["url"])
            merged.append(current)

    if not merged:
        return "\n\n".join(text for _q, text in blocks)

    out = [f"搜索结果 (合并 {len(merged)} 条):", "=" * 60, ""]
    for i, item in enumerate(merged, 1):
        out.append(f"{i}. {item['title']}")
        out.extend(f"   {ln.strip()}" for ln in item["extra"] if ln.strip())
        out.append("")
    return "\n".join(out).rstrip() + "\n"


def _extract_urls(search_result: str, limit: int) -> list:
    """按出现顺序（即相关度排序）提取前 limit 个去重 URL。"""
    urls = []
    seen = set()
    for m in re.finditer(r"https?://[^\s)\]]+", search_result):
        u = m.group()
        if u not in seen:
            seen.add(u)
            urls.append(u)
        if len(urls) >= limit:
            break
    return urls


def _tokenize(text: str) -> list:
    """轻量分词：中文逐字、英文/数字按词。用于中文友好的匹配度计算。

    与 search_engine._tokenize 保持一致的思路（此处独立实现避免跨模块依赖）。
    """
    if not text:
        return []
    tokens = []
    for m in re.finditer(r"[a-zA-Z0-9]+", text.lower()):
        tokens.append(m.group())
    for ch in text:
        if "\u4e00" <= ch <= "\u9fff":
            tokens.append(ch)
    return tokens


def _match_score(question: str, text: str) -> float:
    """计算 text（标题+摘要）与 question 的匹配度：问题 token 的命中覆盖率。"""
    q = set(_tokenize(question))
    if not q:
        return 0.0
    hit = q & set(_tokenize(text))
    return len(hit) / len(q)


# 送入综合 prompt 的网络上下文精简参数
_CONTEXT_MAX_ITEMS = 5          # 最多保留的相关条目数
_CONTEXT_SNIPPET_CHARS = 300    # 每条摘要保留字符
_CONTEXT_PAGE_CHARS = 1500      # 每页正文保留字符
_CONTEXT_MAX_PAGES = 2          # 最多保留的正文页数


def _web_ref_map(web_sources: Optional[list]) -> Dict[str, str]:
    """URL → 引用编号（``W1``..）映射；``web_sources`` 上若无 ``ref`` 则按序补齐。"""
    refs: Dict[str, str] = {}
    for i, src in enumerate(web_sources or [], 1):
        if not isinstance(src, dict):
            continue
        ref = src.get("ref") or f"W{i}"
        src["ref"] = ref
        url = src.get("url")
        if url:
            refs[str(url)] = ref
    return refs


def compact_web_context(search_result: str, question: str, web_sources: Optional[list] = None) -> str:
    """把冗长的搜索结果按与问题的相关度精简，供综合 prompt 使用。

    背景：直接把"全部 10 条摘要 + 3 页全文"塞进 prompt 会引入大量噪音（选配件
    价格、英文营销文案、无关正文），淹没有效信息，导致本地 LLM 抓不住重点甚至
    误判"没有答案"。实测表明：同一 LLM 在**干净精简**的上下文下能准确作答。

    因此这里按匹配度排序，只保留最相关的前若干条摘要 + 少量高相关页正文，并对
    每部分截断，最大化信噪比。question 为空或解析失败时退化为原文截断。

    传入 ``web_sources``（``parse_web_sources`` 的结果）时，每条摘要/正文以其
    引用编号 ``[W1]``.. 标注，使综合答案中的 ``[Wj]`` 可对应到来源面板。
    """
    if not search_result:
        return ""
    if not question:
        return search_result[:4000]

    refs = _web_ref_map(web_sources)

    def label(url: str, fallback: str) -> str:
        return f"[{refs[url]}]" if url and url in refs else fallback

    # 分离"搜索结果"区与"相关页面详细信息"（正文）区
    marker = "=== 相关页面详细信息 ==="
    head, _, body = search_result.partition(marker)

    items = _parse_search_items(head)
    if not items:
        return search_result[:4000]

    scored = []
    for it in items:
        score = _match_score(question, f"{it.get('title','')} {it.get('snippet','')}")
        scored.append((score, it))
    scored.sort(key=lambda x: x[0], reverse=True)

    lines = ["【相关网页摘要】（按相关度排序，[W编号] 为引用编号）"]
    for i, (score, it) in enumerate(scored[:_CONTEXT_MAX_ITEMS], 1):
        title = (it.get("title") or "").strip()
        snippet = (it.get("snippet") or "").strip()[:_CONTEXT_SNIPPET_CHARS]
        url = it.get("url", "")
        lines.append(f"{label(url, f'{i}.')} {title}\n   摘要: {snippet}\n   来源: {url}")

    # 正文区：按页拆分，保留前 N 页（enrich 已按相关度选过页，这里再截断长度）
    if body.strip():
        pages = [p for p in re.split(r"--- 页面 \d+:", body) if p.strip()]
        if pages:
            lines.append("\n【高相关页面正文摘录】")
            for p in pages[:_CONTEXT_MAX_PAGES]:
                text = p.strip()
                m = re.match(r"^(\S+)\s*---", text)
                if m and m.group(1) in refs:
                    text = f"[{refs[m.group(1)]}] " + text
                lines.append(text[:_CONTEXT_PAGE_CHARS])

    return "\n".join(lines)


def _parse_search_items(search_result: str) -> list:
    """把 format_results 的文本解析为结构化条目 [{title, url, snippet}]。

    识别 ``N. 标题`` / ``URL: ...`` / ``摘要: ...`` 结构；摘要缺失时用其余行拼接。
    """
    items = []
    current = None
    for line in search_result.splitlines():
        m_title = re.match(r"^\s*\d+\.\s+(.*)$", line)
        if m_title:
            if current:
                items.append(current)
            current = {"title": m_title.group(1).strip(), "url": "", "snippet": ""}
            continue
        if current is None:
            continue
        m_url = re.match(r"^\s*URL:\s*(\S+)", line)
        if m_url:
            current["url"] = m_url.group(1)
            continue
        m_abs = re.match(r"^\s*摘要[:：]\s*(.*)$", line)
        if m_abs:
            current["snippet"] += " " + m_abs.group(1).strip()
            continue
        # 其余行（如 来源: ...）也纳入摘要，增加匹配信号
        stripped = line.strip()
        if stripped and not stripped.startswith("URL:") and not stripped.startswith("来源"):
            current["snippet"] += " " + stripped
    if current:
        items.append(current)
    return items


# 增强参数：抓取正文的最大页数、每页保留字符数、以及"值得抓取"的匹配度阈值。
_ENRICH_MAX_PAGES = 3
_ENRICH_PER_PAGE_CHARS = 3000
# 匹配度低于此阈值的结果不抓正文（避免对弱相关页面浪费请求/引入噪音）。
_ENRICH_MATCH_THRESHOLD = 0.34


def enrich_with_page_content(
    search_result: str, question: str = "", progress: ProgressCallback = None
) -> str:
    """按"摘要与问题的匹配度"选页抓取正文并追加，提升回答准确性。

    改进说明：此前无脑抓取搜索结果里排名最前的 3 个 URL 正文，不管它们是否
    真的与问题相关，既可能抓到弱相关页（引入噪音），又浪费请求。现改为：
    1. 把搜索结果解析成 (标题, URL, 摘要) 结构；
    2. 用问题 token 与"标题+摘要"计算匹配度（中文友好）；
    3. 按匹配度降序，只对匹配度 >= 阈值的前 N 页抓正文（供 LLM 拿到完整上下文，
       而非仅靠零散摘要——摘要里常混有原价/优惠额/到手价等多个数字，易致误读）。

    当 ``question`` 为空（无法计算匹配度）时，退化为原先的"取前 N 个 URL"策略。
    """
    items = _parse_search_items(search_result)

    # 计算每个条目的匹配度并排序（有 question 时）
    if question and items:
        scored = []
        for it in items:
            if not it.get("url"):
                continue
            score = _match_score(question, f"{it.get('title','')} {it.get('snippet','')}")
            scored.append((score, it))
        scored.sort(key=lambda x: x[0], reverse=True)
        # 阈值过滤；若全部低于阈值，则保底取匹配度最高的 1 个（仍比纯排名靠谱）
        picked = [it for s, it in scored if s >= _ENRICH_MATCH_THRESHOLD][:_ENRICH_MAX_PAGES]
        if not picked and scored:
            picked = [scored[0][1]]
        urls = [it["url"] for it in picked]
    else:
        urls = _extract_urls(search_result, _ENRICH_MAX_PAGES)

    if not urls:
        return search_result

    try:
        from agent_tools import web_content_extract
    except Exception as e:  # noqa: BLE001
        _emit(progress, "enrich_page_failed", f"⚠️ 无法导入内容提取工具: {e}")
        return search_result

    _emit(progress, "enrich_start", f"📄 正在提取 {len(urls)} 个高相关页面正文...")
    blocks = []
    for idx, url in enumerate(urls, 1):
        try:
            page_content = web_content_extract(url, timeout=10)
            if page_content and not page_content.startswith("[错误]"):
                blocks.append(
                    f"--- 页面 {idx}: {url} ---\n{page_content[:_ENRICH_PER_PAGE_CHARS]}"
                )
        except Exception as e:  # noqa: BLE001
            _emit(progress, "enrich_page_failed", f"⚠️ 页面 {idx} 内容提取失败: {e}", url=url)

    if blocks:
        _emit(progress, "enrich_done", f"✅ 页面内容提取成功（{len(blocks)} 个页面）", count=len(blocks))
        return search_result + "\n\n=== 相关页面详细信息 ===\n" + "\n\n".join(blocks)
    return search_result


def simple_web_search(query: str) -> str:
    """对给定查询执行一次网络搜索，返回有效结果文本；失败或无结果返回空串。"""
    try:
        from agent_tools import web_search
        result = web_search(query, max_results=5, use_cache=False)
        if result and not result.startswith("[错误]") and not result.startswith("[提示]"):
            return result
    except Exception as e:  # noqa: BLE001
        logger.error(f"回退网络搜索失败: {e}")
    return ""


# ==================== 网络来源解析 ====================

def parse_web_sources(search_result: str) -> list:
    """从网络搜索结果文本中解析出结构化来源 [{title, url}]。"""
    sources = []
    if not search_result:
        return sources
    lines = search_result.splitlines()
    pending_title = ""
    for line in lines:
        m_title = re.match(r"^\s*\d+\.\s+(.*)$", line)
        if m_title:
            pending_title = m_title.group(1).strip()
            continue
        m_url = re.match(r"^\s*URL:\s*(\S+)", line)
        if m_url:
            sources.append({"title": pending_title or m_url.group(1), "url": m_url.group(1)})
            pending_title = ""
    return sources


# ==================== 结果判定 ====================

def is_empty_rag_result(result: dict) -> bool:
    """判断 RAG 查询结果是否为"空命中"（无来源或返回 LlamaIndex 占位文本）。"""
    if not result:
        return True
    sources = result.get("sources") or []
    answer = (result.get("answer") or "").strip()
    return len(sources) == 0 or answer == "" or answer == "Empty Response"


def _kb_relevance_threshold() -> float:
    """读取知识库"命中相关性"阈值（可被环境变量/配置覆盖）。"""
    try:
        from config import KB_RELEVANCE_THRESHOLD
        return float(KB_RELEVANCE_THRESHOLD)
    except Exception:  # noqa: BLE001 - 配置不可用时用安全默认值
        return 0.45


def filter_relevant_sources(sources: list, threshold: float = None) -> list:
    """按相关性阈值过滤知识库来源，剔除低分噪音片段。

    检索召回阈值（SIMILARITY_CUTOFF）为保护元查询而调得较低（0.3），会带回
    一些语义几乎无关的片段（实测约 0.39）。本函数用更高的"命中相关性"阈值
    过滤这些噪音：分数缺失（None）的片段保守保留（避免误伤无分数的场景，如
    元查询概览），有分数但低于阈值的片段剔除。
    """
    if not sources:
        return []
    if threshold is None:
        threshold = _kb_relevance_threshold()
    kept = []
    for src in sources:
        score = src.get("score")
        if score is None:
            kept.append(src)  # 无分数：保守保留
        elif float(score) >= threshold:
            kept.append(src)
    return kept


# 分数"高可信线"：命中片段最高分达到此值即认为明显相关，跳过 LLM 判定省一次调用。
_KB_CONFIDENT_SCORE = 0.6


def judge_kb_relevance(question: str, sources: list) -> bool:
    """用 LLM 判断检索到的知识库片段是否真能帮助回答问题。

    背景：纯 embedding 相似度无法区分"话题相关"——例如问"DJI 售价"却把整篇
    讲 Cloudflare 配置的中文文档片段以 0.45 的分数召回（因同为中文技术文档，
    向量天然接近），仅靠阈值挡不住这类"分数勉强过线但话题完全不搭"的噪音。

    本函数对通过阈值的片段做一次轻量 LLM 判定：只要 LLM 认为其中有内容与问题
    相关就返回 True；判为无关则返回 False（调用方据此视为知识库未命中，回退
    网络/模型回答，且不把噪音片段当作来源展示）。

    优化：
    - 最高分 >= 高可信线（0.6）时直接判定相关，省去 LLM 调用；
    - LLM 不可用/解析失败时**保守返回 True**（不因判定器故障而误杀真实命中）。
    """
    if not sources:
        return False

    # 明显高分：跳过 LLM
    try:
        top = max((float(s.get("score") or 0) for s in sources), default=0)
    except Exception:  # noqa: BLE001
        top = 0
    if top >= _KB_CONFIDENT_SCORE:
        return True

    # 取前若干片段拼摘要（截断，避免 prompt 过长）
    snippets = []
    for i, s in enumerate(sources[:4], 1):
        content = (s.get("content") or "").strip().replace("\n", " ")
        if content:
            snippets.append(f"[{i}] {content[:200]}")
    if not snippets:
        return False

    prompt = (
        "你是一个严格的相关性判定器。判断下面这些「知识库片段」是否包含"
        "能够直接帮助回答「问题」的信息。\n"
        "只要有任一片段与问题主题相关、可作为回答依据，就回答 relevant；\n"
        "若所有片段都与问题主题无关（例如问的是产品价格，片段却在讲网络配置），"
        "回答 irrelevant。\n"
        "严格只输出一个词：relevant 或 irrelevant。\n\n"
        f"【问题】\n{question}\n\n"
        "【知识库片段】\n" + "\n".join(snippets)
    )

    try:
        raw = _complete(prompt).strip().lower()
        # 解析：包含 irrelevant 判为不相关；否则默认相关（保守）
        if "irrelevant" in raw or "不相关" in raw or "无关" in raw:
            return False
        return True
    except Exception as e:  # noqa: BLE001 - 判定器故障时保守保留命中
        logger.warning(f"LLM 相关性判定失败，保守视为相关: {e}")
        return True


# ==================== 元/概览类问题 ====================

_META_QUERY_PATTERNS = (
    "知识库里有什么", "知识库有什么", "知识库里面有什么", "知识库中有什么",
    "知识库里有哪些", "知识库有哪些", "知识库里面有哪些", "知识库中有哪些",
    "有哪些文件", "有哪些文档", "有什么文件", "有什么文档",
    "列出文件", "列出文档", "列举文件", "列举文档", "文件列表", "文档列表",
    "知识库内容", "知识库里面有内容", "知识库有多少",
    "what is in the knowledge base", "what's in the knowledge base",
    "list files", "list documents", "what files", "what documents",
)


# 正则组合识别元/概览类问题，覆盖固定短语列表之外的表达变体（如"资料/包含/
# 收录/记录"），避免"当前知识库包含哪些文档""都有些什么资料"这类问题漏网后
# 走向量检索、命中无关噪音。
# 结构：提到"知识库/知识库里/库中" + 询问动词(有/包含/收录/存/记录…) +
#      内容名词(信息/资料/内容/文档/文件/数据/东西)
_META_SUBJECT = r"(知识库|资料库|文档库|库里|库中)"
_META_ASK = r"(有哪些|有什么|有多少|包含|收录|存了|存有|记录了|都有|里面有|中有)"
_META_OBJECT = r"(信息|资料|内容|文档|文件|数据|东西|资源|条目)"
_META_REGEX = re.compile(
    rf"{_META_SUBJECT}.*{_META_ASK}.*{_META_OBJECT}"
    rf"|{_META_SUBJECT}.*{_META_OBJECT}.*{_META_ASK}"
)


def is_meta_query(question: str) -> bool:
    """判断是否为"关于知识库本身"的元/概览类问题。

    先用固定短语列表快速命中，再用正则组合覆盖表达变体（资料/包含/收录等），
    使"当前知识库包含哪些文档""知识库里都有些什么资料"等也能被正确识别为
    元查询，直接返回文件概览而非走向量检索。
    """
    if not question:
        return False
    q = question.strip().lower()
    if any(pat in q for pat in _META_QUERY_PATTERNS):
        return True
    # 正则用原文（中文），不用小写化后的 q
    return bool(_META_REGEX.search(question.strip()))


def build_meta_overview(rag_engine) -> dict:
    """构建知识库概览数据（文件列表 + 统计），不做向量检索、不联网。

    Returns:
        ``{"files": [{"path", "size"}], "stats": {...}}`` 的结构化数据，
        由调用方决定如何渲染。
    """
    files_data: List[Dict[str, Any]] = []
    try:
        from file_metadata import get_global_metadata_manager
        manager = get_global_metadata_manager()
        files = manager.list_files()
        for fm in files:
            try:
                size = manager._format_size(fm.file_size)
            except Exception:  # noqa: BLE001
                size = "?"
            files_data.append({"path": fm.file_path, "size": size})
    except Exception as e:  # noqa: BLE001
        logger.debug(f"读取文件元数据失败: {e}")

    stats: Dict[str, Any] = {}
    try:
        if rag_engine is not None:
            stats = rag_engine.get_stats()
    except Exception as e:  # noqa: BLE001
        logger.debug(f"读取知识库统计失败: {e}")

    return {"files": files_data, "stats": stats}


# ==================== 知识库/网络分区综合 ====================

def synthesize_prompt(
    question: str, kb_context: str, web_context: str, history: str = ""
) -> str:
    """组装带"准确回答方法论"的结构化 prompt。

    ``history`` 为最近 2-3 轮对话的紧凑摘要（可为空）：连续对话中用于理解指代
    与延续上下文，但明确要求"事实只以资料为准"，避免把历史回答当作依据。

    此前 prompt 只要求"区分来源、综合总结"，缺乏对**语义准确性**的引导，导致
    LLM 从含多个数字/限定语的上下文里挑错信息（例如把"直降 1177 元"当成售价，
    而实际售价是 2999 元起）。这类错误对所有"带限定语的事实"（价格、版本号、
    时间、规格、人物职务等）都普遍存在。

    因此在 prompt 中注入通用的"准确回答方法论"：先理解问题真正问的是什么、
    只用能直接支撑答案的信息、忠实引用不脑补、对数字/指标标注其限定条件、
    来源冲突或不明确时如实说明。这是**语义理解层面**的改进，而非针对某一类
    问题的补丁。
    """
    parts = [
        "你是严谨、忠实于来源的中文问答助手。基于下面资料回答问题，遵守：",
        "1. 先弄清问题真正问的是什么（哪个对象的哪个属性），只答这一点，不要答非所问。",
        "2. 忠实提取：只用资料里的信息，找到就答、不要脑补；来源没有才说「无法确定」，"
        "绝不编造数值。",
        "3. 注意区分易混概念，尤其数字：售价 vs 优惠额/降价额（如「直降1177」是优惠"
        "而非售价）、原价 vs 到手价、标准版 vs 套装版、不同地区/时间；给数字要带限定条件。",
        "4. 若有多个取值，先给最能代表问题的主答案（如问售价优先给官方起售价），再分条"
        "列出其他版本/渠道的取值并解释差异原因，让回答丰富清楚，不要一句话带过。",
        "5. 【知识库检索内容】优先于【网络搜索补充】；两者冲突以知识库为准并指出差异。",
        "6. 引用标注：资料已按 [1]、[2]…（知识库片段）与 [W1]、[W2]…（网络来源）编号，"
        "每个关键结论/数字所在句子的末尾必须标注其依据编号（如「售价 2999 元起[1]」、"
        "「最新版本为 3.2[W1]」）；一句话依据多条时并列标注（[1][W2]）。不要标注不存在的编号。",
        "",
    ]
    if history:
        parts.append(
            "## 对话上下文（最近几轮，仅用于理解指代与延续话题；事实请以下方资料为准）\n"
            f"{history}"
        )
        parts.append("")
    parts.append(f"## 问题\n{question}")
    parts.append("")
    if kb_context:
        parts.append(f"## 知识库检索内容（本地文档，优先）\n{kb_context}")
    else:
        parts.append("## 知识库检索内容\n（无相关内容）")
    parts.append("")
    if web_context:
        parts.append(f"## 网络搜索补充（互联网，仅供参考）\n{web_context}")
    else:
        parts.append("## 网络搜索补充\n（无）")
    parts.append("")
    parts.append("请给出准确、必要处展开的回答，并在末尾用一句话说明主要依据来自知识库还是网络。")
    return "\n".join(parts)


def assign_refs(kb_sources: Optional[list], web_sources: Optional[list]) -> Tuple[list, list]:
    """为知识库/网络来源就地写入引用编号：``kb_sources[i]["ref"]="1"``、``web_sources[j]["ref"]="W1"``。"""
    kb = [s for s in (kb_sources or []) if isinstance(s, dict)]
    web = [s for s in (web_sources or []) if isinstance(s, dict)]
    for i, src in enumerate(kb, 1):
        src["ref"] = str(i)
    for j, src in enumerate(web, 1):
        src["ref"] = f"W{j}"
    return kb, web


def format_kb_context(sources: list) -> str:
    """把知识库来源拼成带编号与文件标注的上下文文本 ``[1]..[k]``，供综合 prompt 使用。

    编号与 ``assign_refs`` 写入的 ``ref`` 一致（按列表顺序 1..k），综合答案中的
    ``[i]`` 即对应第 i 条来源。空内容的片段仍占用编号，避免编号错位。
    """
    blocks = []
    for i, src in enumerate(sources, 1):
        content = (src.get("content") or "").strip()
        if not content:
            continue
        fname = src.get("file", "未知文件")
        src["ref"] = str(i)
        blocks.append(f"[{i}]（来自 {fname}）\n{content}")
    return "\n\n".join(blocks)


# ==================== 网络搜索增强编排 ====================

def augment_with_web_search(
    question: str,
    progress: ProgressCallback = None,
    should_stop: StopCheck = None,
    plan: Optional[dict] = None,
) -> str:
    """按需执行 LLM 规划的网络搜索，返回搜索结果文本（无则空串）。

    ``plan`` 可传入 :func:`plan_retrieval` 已得到的规划（避免重复调用 LLM）；
    为空时内部调用一次 ``plan_web_search``。
    """
    try:
        if plan is None:
            plan = plan_web_search(question, progress=progress)
        _check_stop(should_stop)
        if plan.get("needs_search") and plan.get("queries"):
            _emit(progress, "web_search_start", "🌐 检测到需要最新信息，正在网络搜索...")
            result = run_web_search(plan["queries"], progress=progress)
            _check_stop(should_stop)
            if result:
                _emit(progress, "web_search_done", "✅ 网络搜索完成")
                # 传入原始问题，使 enrich 按"摘要与问题的匹配度"选页抓正文
                return enrich_with_page_content(result, question=question, progress=progress)
            _emit(progress, "web_search_empty", "⚠️ 所有搜索查询均未返回有效结果，继续使用知识库")
        else:
            _emit(progress, "web_plan_skip", "💡 判断无需联网，直接使用知识库/模型回答")
    except PipelineCancelled:
        raise
    except Exception as e:  # noqa: BLE001
        _emit(progress, "web_search_failed", f"⚠️ 网络搜索失败，继续使用知识库: {e}")
    return ""


# ==================== 核心：生成回答 ====================

def generate_answer(
    rag_engine,
    question: str,
    original_question: str,
    web_search_result: str,
    show_progress: bool = True,
    progress: ProgressCallback = None,
    rag_progress_callback: ProgressCallback = None,
    should_stop: StopCheck = None,
    history_text: str = "",
    kb_only: bool = False,
    subquestions: Optional[list] = None,
    web_sources: Optional[list] = None,
) -> dict:
    """根据知识库状态生成回答（知识库/网络分区标注、编号引用、综合总结）。

    Args:
        rag_engine: 已初始化的 RAGEngine（其 ``query_engine`` 可能为 None）。
        question: 用于检索的问题（可能已被内联文件入库逻辑改写）。
        original_question: 用户原始问题，用于综合 prompt 与声明来源。
        web_search_result: 预先执行的网络搜索结果文本（可为空）。
        show_progress: 是否把 RAG 检索进度透传给 ``rag_progress_callback``。
        progress: 编排级进度回调（网络回退、综合、思考等阶段）。
        rag_progress_callback: 直接透传给 ``query_with_sources`` 的进度回调。
        should_stop: 取消探针，阶段边界命中即抛 ``PipelineCancelled``。
        history_text: 最近几轮对话的紧凑文本（连续对话时注入综合 prompt）。
        kb_only: 只要知识库结论：未初始化或未命中时不做网络回退、不调模型
            兜底，直接返回 ``{"answer": "", "sources": []}``（供 Agent 工具
            ``query_knowledge_base`` 使用，由模型自行决定是否转 web_search）。
        subquestions: 复合问题的子问题列表（≥2 时多跳：逐个检索、去重合并后
            再筛选/综合）；为空走单次检索路径。
        web_sources: 已解析的网络来源（``parse_web_sources``），用于 ``[Wj]``
            编号；为空时按 ``web_search_result`` 解析。

    Returns:
        ``{"answer": str, "sources": [...], "web_sources": [...], "kind": "answer"|"fallback"}``。
        sources 仅含知识库来源（带 ``ref``）；``kind="fallback"`` 表示知识库无相关
        片段且网络也无结果（附 ``fallback_question``）。
    """
    kb_initialized = rag_engine.query_engine is not None
    _check_stop(should_stop)

    if kb_only and not kb_initialized:
        _emit(progress, "kb_uninitialized", "⚠️ 知识库未初始化")
        return {"answer": "", "sources": [], "web_sources": [], "kind": "answer"}

    # /think on：把 progress 交给 _complete，使综合/规划调用的思维链能推送给 UI
    think_on = bool(getattr(rag_engine, "llm_think", False))
    sink_token = _THINKING_SINK.set(progress if think_on else None)
    try:
        return _generate_answer_inner(
            rag_engine, question, original_question, web_search_result,
            show_progress=show_progress, progress=progress,
            rag_progress_callback=rag_progress_callback, should_stop=should_stop,
            history_text=history_text, kb_only=kb_only, subquestions=subquestions,
            web_sources=web_sources, kb_initialized=kb_initialized,
        )
    finally:
        _THINKING_SINK.reset(sink_token)


def _retrieve(rag_engine, question: str, show_progress: bool, rag_progress_callback: ProgressCallback) -> dict:
    if show_progress and rag_progress_callback is not None:
        return rag_engine.query_with_sources(question, progress_callback=rag_progress_callback)
    return rag_engine.query_with_sources(question)


def _merge_multi_hop(results: list) -> dict:
    """合并多个子问题的检索结果：按 ``(file, content)`` 去重，保留首次出现的分数/顺序。"""
    merged: List[dict] = []
    seen = set()
    answers = []
    for res in results:
        if not isinstance(res, dict):
            continue
        ans = (res.get("answer") or "").strip()
        if ans and ans != "Empty Response":
            answers.append(ans)
        for src in res.get("sources") or []:
            if not isinstance(src, dict):
                continue
            key = (src.get("file") or src.get("path") or "", (src.get("content") or "").strip())
            if key in seen:
                continue
            seen.add(key)
            merged.append(src)
    # 分数高的在前，便于后续编号与截断
    merged.sort(key=lambda s: float(s.get("score") or 0), reverse=True)
    return {"answer": "\n\n".join(answers), "sources": merged}


def _generate_answer_inner(
    rag_engine, question, original_question, web_search_result, *,
    show_progress, progress, rag_progress_callback, should_stop, history_text,
    kb_only, subquestions, web_sources, kb_initialized,
) -> dict:
    web_sources = [s for s in (web_sources if web_sources is not None else parse_web_sources(web_search_result)) if isinstance(s, dict)]
    assign_refs([], web_sources)

    # 按相关度精简网络上下文：只保留与问题最相关的摘要 + 精选正文，最大化信噪比，
    # 避免全部结果+全文的噪音淹没有效信息、导致 LLM 抓不住重点或误判无答案。
    web_context = compact_web_context(web_search_result, original_question, web_sources) if web_search_result else ""

    # 知识库未初始化：只能用网络/模型自身知识，明确声明来源
    if not kb_initialized:
        if not web_search_result:
            _emit(progress, "kb_uninitialized", "💡 知识库为空，直接使用模型回答（可能不含最新信息）")
        prompt = synthesize_prompt(original_question, kb_context="", web_context=web_context, history=history_text)
        _emit(progress, "model_thinking", "✍️ 模型生成回答中...")
        answer = llm_direct_answer(prompt)
        if web_search_result:
            answer = "⚠️ 以下回答基于网络搜索与模型知识，非你的知识库内容：\n\n" + answer
        return {"answer": answer, "sources": [], "web_sources": web_sources, "kind": "answer"}

    # 检索知识库（LlamaIndex 的 query 会一次完成"向量检索 + 初步生成"，含模型推理）
    multi_hop = bool(subquestions) and len(subquestions) >= 2
    if multi_hop:
        results = []
        for i, sq in enumerate(subquestions, 1):
            _emit(progress, "kb_retrieving", f"📖 子问题 {i}/{len(subquestions)}：{sq}",
                  current=i, total=len(subquestions), subquestion=sq)
            results.append(_retrieve(rag_engine, sq, show_progress, rag_progress_callback))
            _check_stop(should_stop)
        result = _merge_multi_hop(results)
        _emit(progress, "kb_merged", f"🔗 合并 {len(subquestions)} 个子问题的检索结果，去重后 {len(result['sources'])} 个片段",
              count=len(result["sources"]))
    else:
        _emit(progress, "kb_retrieving", "📖 检索知识库并生成初步回答（含模型推理）...")
        result = _retrieve(rag_engine, question, show_progress, rag_progress_callback)
        _check_stop(should_stop)

    # 相关性过滤：剔除低分噪音片段（检索阈值 0.3 会带回语义几乎无关的片段）。
    raw_sources = result.get("sources") or []
    relevant_sources = filter_relevant_sources(raw_sources)
    dropped = len(raw_sources) - len(relevant_sources)
    if dropped > 0:
        _emit(
            progress, "kb_low_relevance",
            f"🧹 已过滤 {dropped} 个低相关片段（低于相关性阈值）",
            dropped=dropped,
        )

    # 初步命中判定：过滤后仍有相关来源才算命中。
    kb_hit = len(relevant_sources) > 0 and not is_empty_rag_result(
        {"answer": result.get("answer"), "sources": relevant_sources}
    )

    # 逐片段相关性筛选（rerank）：纯 embedding 分数无法区分"话题相关"，用 LLM /
    # cross-encoder 逐片段判断是否真能帮助回答问题；全部无关则视为未命中，避免把
    # 0.45 这类勉强过阈值但话题不搭的噪音（如问"售价"却召回 Cloudflare 配置）当作依据。
    if kb_hit:
        from rag_rerank import rerank
        kept = rerank(original_question, relevant_sources, progress=progress)
        _check_stop(should_stop)
        if not kept:
            _emit(progress, "kb_irrelevant", "🧹 知识库片段与问题无关，已忽略")
            kb_hit = False
        else:
            dropped += len(relevant_sources) - len(kept)
            relevant_sources = kept

    # 知识库命中：以（筛选后的）知识库为主。
    if kb_hit:
        assign_refs(relevant_sources, web_sources)
        hybrid_added = any(s.get("retriever") == "bm25" for s in relevant_sources)
        # 快路径：没有过滤掉任何片段、没有网络补充、非多跳、且无 BM25 补充的片段时，
        # 直接沿用 LlamaIndex 的原始回答（它正是基于这些片段生成的），省一次 LLM 调用。
        if dropped == 0 and not web_search_result and not multi_hop and not hybrid_added:
            return {"answer": result.get("answer", ""), "sources": relevant_sources,
                    "web_sources": web_sources, "kind": "answer"}

        # 否则（过滤掉了噪音、多跳合并、或需要综合网络补充）基于"仅相关片段"重新综合，
        # 避免 LlamaIndex 原始回答里混入被过滤掉的噪音内容。
        kb_context = format_kb_context(relevant_sources)
        prompt = synthesize_prompt(original_question, kb_context, web_context, history=history_text)
        if web_search_result:
            _emit(progress, "synthesizing", "✍️ 综合知识库与网络信息生成回答（带编号引用）...")
        else:
            _emit(progress, "synthesizing", "✍️ 基于知识库综合回答（带编号引用）...")
        answer = llm_direct_answer(prompt)
        return {"answer": answer, "sources": relevant_sources, "web_sources": web_sources, "kind": "answer"}

    # 知识库 0 命中（或全部为低相关噪音）：明确告知，再用网络/模型回答。
    _emit(progress, "kb_empty", "📭 知识库中未检索到相关内容。")
    if kb_only:
        return {"answer": "", "sources": [], "web_sources": web_sources, "kind": "answer"}
    if not web_search_result:
        _emit(progress, "kb_fallback_search", "🌐 正在网络搜索补充信息...")
        web_search_result = simple_web_search(original_question)
        _check_stop(should_stop)
        if web_search_result:
            _emit(progress, "web_search_done", "✅ 网络搜索完成")
            # 回退搜索的结果同样解析来源、编号并精简后再入 prompt
            web_sources = parse_web_sources(web_search_result)
            assign_refs([], web_sources)
            web_context = compact_web_context(web_search_result, original_question, web_sources)

    prompt = synthesize_prompt(original_question, kb_context="", web_context=web_context, history=history_text)
    _emit(progress, "model_thinking", "✍️ 模型生成回答中...")
    answer = llm_direct_answer(prompt)
    if web_search_result:
        answer = "⚠️ 知识库中无相关内容，以下回答基于网络搜索，非你的知识库内容：\n\n" + answer
        return {"answer": answer, "sources": [], "web_sources": web_sources, "kind": "answer"}

    # 失败回退：知识库无相关片段且网络也无结果 → 提示改用单 Agent 工具进一步查找
    _emit(progress, "model_thinking", "💡 未获取到网络信息，直接使用模型自身知识回答")
    answer = "⚠️ 知识库中无相关内容，以下为模型自身知识回答：\n\n" + answer
    answer += "\n\n" + fallback_suggestion(original_question)
    _emit(progress, "fallback", "🧭 知识库与网络均未找到相关内容，可用单 Agent 进一步查找",
          question=original_question)
    return {"answer": answer, "sources": [], "web_sources": [], "kind": "fallback",
            "fallback_question": original_question}


def fallback_suggestion(question: str) -> str:
    """知识库与网络均无结果时追加到答案末尾的建议文案。"""
    return f"建议：/agent {question} 让 Agent 用工具进一步查找"


# ==================== 顶层入口：完整问答编排 ====================

def answer_question(
    rag_engine,
    question: str,
    *,
    enable_web_search: bool = True,
    show_progress: bool = True,
    progress: ProgressCallback = None,
    rag_progress_callback: ProgressCallback = None,
    should_stop: StopCheck = None,
    context=None,
    kb_only: bool = False,
) -> dict:
    """完整的知识库问答编排入口，CLI 与 Web 共享。

    覆盖：元/概览问题直答、LLM 驱动网络搜索增强、知识库/网络双区综合、
    0 命中网络回退。**不包含**内联文件入库（该逻辑与交互强相关，保留在
    CLI 层，调用本函数前自行处理并传入改写后的 question）。

    连续对话：传入 ``context``（``conversation_context.ConversationContext``）
    后，若会话已有历史且问题疑似追问，会先用 LLM 把问题改写为独立问题，并以
    改写后的问题做检索/联网/相关性判定/综合；综合 prompt 追加最近几轮摘要。
    首轮或独立问题不产生任何额外开销。**本函数不写入会话**，由调用方记录。

    Args:
        rag_engine: 已初始化的 RAGEngine。
        question: 用户问题（若外部已做内联文件入库改写，请传改写后的文本）。
        enable_web_search: 是否启用 LLM 规划的网络搜索增强。
        show_progress: 是否透传 RAG 检索进度。
        progress: 编排级进度回调。
        rag_progress_callback: 透传给 query_with_sources 的进度回调。
        should_stop: 取消探针；用户请求停止时在阶段边界抛 ``PipelineCancelled``。
        context: 可选会话上下文，用于问题改写与历史注入。
        kb_only: 只取知识库结论，未命中时不做网络回退/模型兜底（见 ``generate_answer``）。

    Returns:
        统一结构：
        ``{"kind": "meta"|"answer", "answer": str, "kb_sources": [...],
           "web_sources": [...], "meta": {...}|None, "rewritten": str|None}``
        ``rewritten`` 为被改写后的独立问题（未改写时为 None）。
    """
    question = (question or "").strip()
    _check_stop(should_stop)

    # 元/概览类问题：直接返回知识库概览，不检索不联网
    if is_meta_query(question):
        overview = build_meta_overview(rag_engine)
        _emit(progress, "meta_overview", "📚 知识库概览", **overview)
        return {
            "kind": "meta",
            "answer": "[知识库概览]",
            "kb_sources": [],
            "web_sources": [],
            "meta": overview,
            "rewritten": None,
        }

    # 连续对话：疑似追问时改写为独立问题；并取最近几轮紧凑文本供综合 prompt
    effective = question
    rewritten = None
    history_text = ""
    if context is not None:
        try:
            rw = context.rewrite_question(question, progress=progress)
            if rw.get("changed"):
                effective = rw["question"]
                rewritten = effective
            history_text = context.history_text(turns=3)
        except Exception as e:  # noqa: BLE001 - 上下文层故障不影响作答
            logger.warning(f"读取会话上下文失败，按无历史处理: {e}")
        _check_stop(should_stop)

    kb_initialized = rag_engine.query_engine is not None
    if not kb_initialized:
        _emit(progress, "kb_uninitialized", "⚠️ 知识库未初始化，将根据网络搜索/模型直接回答")

    # /think on：整条链路（规划/综合）的思维链都透出到 progress
    think_on = bool(getattr(rag_engine, "llm_think", False))
    sink_token = _THINKING_SINK.set(progress if think_on else None)
    try:
        return _answer_question_planned(
            rag_engine, question, effective, rewritten, history_text, kb_initialized,
            enable_web_search=enable_web_search, show_progress=show_progress, progress=progress,
            rag_progress_callback=rag_progress_callback, should_stop=should_stop, kb_only=kb_only,
        )
    finally:
        _THINKING_SINK.reset(sink_token)


def _answer_question_planned(
    rag_engine, question, effective, rewritten, history_text, kb_initialized, *,
    enable_web_search, show_progress, progress, rag_progress_callback, should_stop, kb_only,
) -> dict:
    # 检索规划（一次 LLM）：复合问题分解 + 是否联网 + 搜索词。关闭联网/kb_only 时
    # 仍做分解（多跳检索）但不搜索；知识库未初始化时无需分解，仅在联网时规划。
    plan: Optional[dict] = None
    if enable_web_search or kb_initialized:
        plan = plan_retrieval(effective, progress=progress)
        _check_stop(should_stop)

    # 网络搜索增强（复用上面的规划结果，不再额外调用 LLM）
    web_search_result = ""
    if enable_web_search:
        web_search_result = augment_with_web_search(
            effective, progress=progress, should_stop=should_stop, plan=plan
        )
    web_sources = parse_web_sources(web_search_result) if web_search_result else []

    subquestions = (plan or {}).get("subquestions") if (plan or {}).get("complex") else None

    result = generate_answer(
        rag_engine,
        effective,
        effective,
        web_search_result,
        show_progress=show_progress,
        progress=progress,
        rag_progress_callback=rag_progress_callback,
        should_stop=should_stop,
        history_text=history_text,
        kb_only=kb_only,
        subquestions=subquestions,
        web_sources=web_sources,
    )

    kb_sources, web_sources = assign_refs(result.get("sources", []), result.get("web_sources", web_sources))
    out = {
        "kind": result.get("kind") or "answer",
        "answer": result.get("answer", ""),
        "kb_sources": kb_sources,
        "web_sources": web_sources,
        "meta": None,
        "rewritten": rewritten,
    }
    if out["kind"] == "fallback":
        out["fallback_question"] = result.get("fallback_question") or question
    return out


# ==================== 对话落库（会话持久化）====================

def record_conversation(
    user_content: str,
    assistant_content: str,
    *,
    context=None,
    trace: Optional[str] = None,
    rewritten: Optional[str] = None,
    progress: ProgressCallback = None,
) -> None:
    """将一轮对话写入会话（对话历史的单一来源），并按需触发自动压缩。

    ``context`` 为空时使用进程内单例（跟随"当前会话"，无会话则自动创建），
    使 CLI/Web 的 /ask、/agent、自然语言输入与多 Agent 对话始终被持久化。
    """
    try:
        if context is None:
            from conversation_context import get_conversation_context
            context = get_conversation_context()
        context.record(
            user_content, assistant_content,
            trace=trace, rewritten=rewritten, progress=progress,
        )
    except Exception as e:  # noqa: BLE001
        logger.error(f"记录对话到会话失败: {e}")
