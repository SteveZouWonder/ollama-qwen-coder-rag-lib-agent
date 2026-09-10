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
``web_search_failed`` | ``enrich_start`` | ``enrich_page_failed`` | ``enrich_page_blocked`` |
``enrich_done`` | ``kb_decompose`` | ``kb_retrieving`` | ``kb_merged`` |
``kb_low_relevance`` | ``rerank`` | ``rerank_done`` | ``rerank_fallback`` |
``kb_irrelevant`` | ``kb_empty`` | ``kb_fallback_search`` | ``synthesizing`` |
``model_thinking`` | ``thinking``（/think on 时的思维链，截断 800 字）|
``fallback``（知识库与网络均无结果）| ``kb_uninitialized`` | ``self_check``（RAG_SELF_CHECK 开启时）|
``premise_unverified``（前提实体未在资料中出现）等。

返回 ``kind``：``meta``（知识库概览直答）| ``answer`` | ``fallback``（无相关片段且
网络无结果）。``answer`` 只含正文；警示 / 建议 / 引用校验等"关于可信度的信息"以
结构化 ``notices``（``{"level","code","text","position"}``）返回，由各端加样式渲染
（F9 P0-5）。来源项带引用编号 ``ref``（知识库 ``"1"``..，网络 ``"W1"``..）与被引用
次数 ``cited``，与答案中的 ``[i]``/``[Wj]`` 对应；非法编号被改写为 ``[?]``（P0-3）。

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

# 可选最终答案增量回调（F10 P1-1）：综合回答阶段每收到一段模型输出即回调一次。
TokenCallback = Optional[Callable[[str], None]]


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


def _stream_enabled() -> bool:
    try:
        from config import Config
        return bool(getattr(Config, "LLM_STREAM", True))
    except Exception:  # noqa: BLE001
        return True


def _stream_complete(llm, prompt: str, on_token: TokenCallback, should_stop: StopCheck = None) -> str:
    """经 LlamaIndex ``stream_chat`` 流式补全，逐增量回调 ``on_token``，返回累积文本（F10 P1-1）。

    沿用 ``Settings.llm`` 的模型 / num_ctx / think 配置。``should_stop()`` 为真时停止读取
    并关闭生成器（连接随之关闭）。LLM 不支持 ``stream_chat`` 时回退一次性补全 + 单次回调。
    """
    stream_chat = getattr(llm, "stream_chat", None)
    if not callable(stream_chat):
        response = llm.complete(prompt)
        _emit_thinking(response)
        text = str(response)
        on_token(text)
        return text

    from llama_index.core.llms import ChatMessage, MessageRole

    gen = stream_chat([ChatMessage(role=MessageRole.USER, content=prompt)])
    parts: List[str] = []
    last = None
    try:
        for chunk in gen:
            if should_stop is not None and should_stop():
                break
            last = chunk
            delta = getattr(chunk, "delta", None) or ""
            if delta:
                parts.append(delta)
                on_token(delta)
    finally:
        close = getattr(gen, "close", None)
        if callable(close):
            try:
                close()
            except Exception as e:  # noqa: BLE001
                logger.debug(f"close stream failed: {e}")
    if last is not None:
        _emit_thinking(last)
    return "".join(parts)


def _complete(prompt: str, on_token: TokenCallback = None, should_stop: StopCheck = None) -> str:
    """用全局唯一模型执行一次补全（/think on 时顺带透出思维链）。

    ``on_token`` 非空且 ``LLM_STREAM`` 开启时流式（F10 P1-1）；``LLM_STREAM=false`` 时
    非流式并把完整文本一次性回调；无 ``on_token`` 时与此前完全一致。
    """
    llm = _get_synthesis_llm()
    if llm is None:
        from llama_index.core import Settings
        llm = Settings.llm
    if on_token is not None and _stream_enabled():
        return _stream_complete(llm, prompt, on_token, should_stop)
    response = llm.complete(prompt)
    _emit_thinking(response)
    text = str(response)
    if on_token is not None:
        on_token(text)
    return text


def llm_direct_answer(prompt: str, on_token: TokenCallback = None, should_stop: StopCheck = None) -> str:
    """用 LLM 直接回答（不经过知识库检索）。失败时返回错误说明。

    ``on_token`` / ``should_stop`` 透传给 ``_complete``（无回调时调用形态与此前一致）。
    """
    try:
        if on_token is None:
            return _complete(prompt)
        return _complete(prompt, on_token=on_token, should_stop=should_stop)
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
# F9 P2-2：检索规划中提取的实体上限
MAX_ENTITIES = 4


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
        '"queries":[最多3个搜索词],'
        '"entities":[问题中的专有名词/函数名/产品名，最多4个，没有则空]}\n'
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
           "queries": [str...], "entities": [str...](≤4)}``。subquestions/queries 已去重；``complex`` 为 True
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
        # F9 P2-2：问题中的实体（≤4），供"前提实体校验"使用；缺失 / 非列表兼容为空
        raw_entities = data.get("entities")
        entities = _dedupe_strings(raw_entities)[:MAX_ENTITIES] if isinstance(raw_entities, list) else []
        plan = {
            "complex": complex_,
            "subquestions": subquestions,
            "needs_search": needs,
            "queries": queries,
            "entities": entities,
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
            "entities": [],  # 回退（无 LLM）时跳过前提实体校验
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


# 网页正文注入扫描（F9 P1-3）：模块级惰性单例，只用扫描器的提示词注入检测
_PAGE_SCANNER = None


def _page_scanner():
    global _PAGE_SCANNER
    if _PAGE_SCANNER is None:
        try:
            from content_security import ContentSecurityScanner
            _PAGE_SCANNER = ContentSecurityScanner()
        except Exception as e:  # noqa: BLE001 - 扫描器不可用时不阻断联网增强
            logger.debug(f"内容安全扫描器不可用，跳过网页注入扫描: {e}")
            _PAGE_SCANNER = False
    return _PAGE_SCANNER or None


def page_has_prompt_injection(page_content: str) -> bool:
    """网页正文是否疑似含提示词注入（``ContentSecurityScanner._detect_prompt_injection``，不用密钥等规则）。"""
    scanner = _page_scanner()
    if scanner is None or not page_content:
        return False
    try:
        return bool(scanner._detect_prompt_injection(page_content))
    except Exception as e:  # noqa: BLE001
        logger.debug(f"网页注入扫描失败，视为安全: {e}")
        return False


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
                # F9 P1-3：抓取的网页正文直接进 prompt，先做提示词注入扫描，命中整页丢弃并留痕
                if page_has_prompt_injection(page_content):
                    _emit(progress, "enrich_page_blocked", f"🛡️ 已丢弃疑似提示词注入的页面: {url}", url=url)
                    continue
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

def kb_ready(rag_engine) -> bool:
    """知识库是否已初始化：以引擎的 ``retriever`` 是否存在为唯一哨兵（F9 P0-1）。"""
    return rag_engine is not None and getattr(rag_engine, "retriever", None) is not None


def is_empty_rag_result(result: dict) -> bool:
    """判断 RAG 检索结果是否为"空命中"：只看 ``sources`` 是否为空。

    F9 P0-1 起 ``query_with_sources`` 只检索不生成（``answer`` 恒为空串），因此不再
    以答案文本（此前的 ``"Empty Response"`` 占位）作为判据。
    """
    if not result:
        return True
    sources = result.get("sources") or []
    return len(sources) == 0


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

# 综合 prompt 的忠实性规则（F9 P0-2 提取为常量，供自校验 / 评测复用）。
# 第 1-7 条为既有规则；第 8-10 条针对 H-Neurons 研究揭示的"过度顺从"三个维度：
# 接受错误前提 / 顺从误导性上下文 / 被质疑就改口。
FAITHFULNESS_RULES: List[str] = [
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
    "7. 引用代码片段时，在 [i] 之外可注明函数/类名与行号（如「`_ensure_bm25`（L534-581）[2]」），"
    "便于用户定位；行号只能取自资料标注（来自 … · L起-止），不要编造。",
    "8. 前提核对：问题若预设了资料未证实的事实（某功能存在、某数值、某因果），先指出"
    "「资料未提及/与资料不符」，再按资料回答，不要顺着前提编。",
    "9. 冲突处理：多条资料矛盾时并列列出各说法及编号，不要擅自取一或折中。",
    "10. 被质疑时：用户反驳只是重新核对的信号；资料支持原答案则坚持并给编号，资料支持"
    "用户才修正，不要仅因被反驳而改口。",
]


# ==================== 前提实体校验（F9 P2-2，零新增调用）====================

_ENTITY_SPLIT_RE = re.compile(r"[^0-9A-Za-z\u4e00-\u9fff]+")
_CAMEL_RE = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")


def _entity_tokens(entity: str) -> List[str]:
    """实体的子词（小写）：按非字母数字拆分，再拆 snake / camel（兼容 ``_bm25_tokenize`` 的拆词）。"""
    out: List[str] = []
    for part in _ENTITY_SPLIT_RE.split(entity or ""):
        if not part:
            continue
        for sub in _CAMEL_RE.split(part):
            sub = sub.lower()
            if len(sub) >= 2 and sub not in out:
                out.append(sub)
    return out


def entity_in_text(entity: str, text: str) -> bool:
    """大小写不敏感子串命中；否则要求实体的全部子词都出现在文本中（如 ``_ensure_bm25`` → ensure + bm25）。"""
    e = (entity or "").strip().lower()
    t = (text or "").lower()
    if not e or not t:
        return False
    if e in t:
        return True
    tokens = _entity_tokens(entity)
    return bool(tokens) and all(tok in t for tok in tokens)


def unverified_entities(entities: Optional[list], sources: Optional[list]) -> List[str]:
    """返回在**所有**保留片段（内容 + 文件名 + 符号名）中都没出现的实体；实体为空返回 []。"""
    ents = [str(e).strip() for e in (entities or []) if str(e or "").strip()]
    if not ents or not sources:
        return []
    texts = []
    for src in sources:
        if not isinstance(src, dict):
            continue
        texts.append(" ".join(str(src.get(k) or "") for k in ("content", "file", "symbol")))
    blob = "\n".join(texts)
    return [e for e in ents if not entity_in_text(e, blob)]


def premise_note(missing: List[str]) -> str:
    """注入综合 prompt 问题段前的一行提示（无缺失实体返回空串）。"""
    if not missing:
        return ""
    names = "」「".join(missing)
    return f"注意：资料中未出现「{names}」，先核对该前提是否成立。"


# 无依据作答（F9 P1-1）：知识库与网络双空时替换 prompt 末尾的作答指令——先判断是否确知
NO_EVIDENCE_INSTRUCTION = (
    "当前没有任何资料。先判断你是否确知答案：确知则简要回答并注明「依据模型自身知识，未经资料核实」；"
    "不确知则只说「我不确定」并说明缺少什么信息，不要猜测或编造。"
)


def synthesize_prompt(
    question: str, kb_context: str, web_context: str, history: str = "",
    no_evidence: bool = False, premise: str = "",
) -> str:
    """组装带"准确回答方法论"的结构化 prompt。

    ``no_evidence=True``（知识库与网络均无资料，F9 P1-1）时末尾的作答指令替换为
    ``NO_EVIDENCE_INSTRUCTION``：先判断是否确知，确知则答并注明依据模型知识，不确知只说不确定。
    ``premise``（F9 P2-2）非空时在「## 问题」段前注入该行（``premise_note`` 生成的
    「注意：资料中未出现「X」，先核对该前提是否成立。」）。

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
    parts = ["你是严谨、忠实于来源的中文问答助手。基于下面资料回答问题，遵守："]
    parts.extend(FAITHFULNESS_RULES)
    parts.append("")
    if history:
        parts.append(
            "## 对话上下文（最近几轮，仅用于理解指代与延续话题；事实请以下方资料为准）\n"
            f"{history}"
        )
        parts.append("")
    if premise:
        parts.append(premise)
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
    if no_evidence:
        parts.append(NO_EVIDENCE_INSTRUCTION)
    else:
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
        src["ref"] = str(i)
        blocks.append(f"[{i}]（来自 {source_location(src)}）\n{content}")
    return "\n\n".join(blocks)


def source_location(src: dict) -> str:
    """来源定位文案：文本块为文件名；代码块为 ``file · symbol · L起-止``（CLI / Web / prompt 共用）。"""
    fname = src.get("file") or "未知文件"
    parts = [str(fname)]
    if src.get("symbol"):
        parts.append(str(src["symbol"]))
    if src.get("start_line") is not None:
        end = src.get("end_line") or src.get("start_line")
        parts.append(f"L{src['start_line']}-{end}")
    return " · ".join(parts)


def source_symbols(sources: list, limit: int = 3) -> str:
    """取前 ``limit`` 个代码来源的符号名拼成短文案（进度事件用），无代码块返回空串。"""
    names = []
    for src in sources or []:
        sym = src.get("symbol") if isinstance(src, dict) else None
        if sym and sym not in names:
            names.append(str(sym))
        if len(names) >= limit:
            break
    if not names:
        return ""
    more = sum(1 for s in sources if isinstance(s, dict) and s.get("symbol")) - len(names)
    text = ", ".join(f"`{n}`" for n in names)
    return text + (f" 等 {more + len(names)} 个符号" if more > 0 else "")


# ==================== 结构化提示 notices 与引用校验（F9 P0-5 / P0-3）====================

# notice 的 ``code`` 枚举（各端据此决定是否单独渲染，如 ``fallback`` 沿用既有 retry 行）
NOTICE_CODES = (
    "kb_uninitialized",  # 知识库为空，模型直答 / 依据网络
    "web_only",          # 知识库无相关内容，依据网络
    "no_evidence",       # 无任何资料，模型自身知识
    "fallback",          # 建议 /agent（text 含原问题）
    "citation",          # 引用校验结果
    "self_check",        # LLM 自校验（P2-1）
    "premise",           # 前提实体未命中（P2-2）
)


NO_EVIDENCE_NOTICE_TEXT = "无资料依据 · 模型自身知识 · 请自行核实"


def make_notice(code: str, text: str, *, level: str = "warn", position: str = "before") -> dict:
    """构造一条结构化提示：``text`` 为纯文本（无 emoji / markup，由各端加样式）。"""
    return {"level": level, "code": code, "text": text, "position": position}


def notice_lines(notices: Optional[list], level: str = "warn") -> List[str]:
    """会话记录 / Agent 工具回灌用：每条指定级别的 notice 渲染为 ``[code] text`` 一行。"""
    out = []
    for n in notices or []:
        if isinstance(n, dict) and n.get("level") == level and n.get("text"):
            out.append(f"[{n.get('code', '')}] {n['text']}")
    return out


def answer_with_notices(answer: str, notices: Optional[list]) -> str:
    """答案正文 + warn 级 notice 各一行（供会话记录，使后续轮次知道上一答的可信度）。"""
    lines = notice_lines(notices, "warn")
    body = (answer or "").rstrip()
    if not lines:
        return body
    return (body + "\n\n" + "\n".join(lines)).strip()


# 引用编号 ``[1]`` / ``[W2]``；代码围栏与行内反引号内的文本不参与校验
_CITE_RE = re.compile(r"\[(W?\d+)\]")
_CODE_OR_CITE_RE = re.compile(r"(```.*?```|`[^`\n]*`)|\[(W?\d+)\]", re.DOTALL)
_CODE_RE = re.compile(r"```.*?```|`[^`\n]*`", re.DOTALL)
_SENTENCE_SPLIT_RE = re.compile(r"[。！？\n]")
_LIST_MARKER_RE = re.compile(r"^\s*(?:\d+[.、)]|[-*+]|#+)\s*")


def verify_citations(answer: str, kb_sources: Optional[list], web_sources: Optional[list]) -> dict:
    """程序化核验答案中的引用编号（F9 P0-3）。

    - 合法编号集 = 各来源的 ``ref``；扫描 ``[i]`` / ``[Wj]``（忽略代码围栏与行内反引号），
      非法编号原地改写为 ``[?]``；
    - 每条来源回填 ``cited``（被引用次数）；
    - ``unsupported_numeric``：含数字（阿拉伯数字 / 版本号形态）却没有任一合法编号的句子数
      （按 ``。！？\\n`` 切句；仅在有来源时统计，无来源不统计）。

    返回 ``{"answer", "invalid", "invalid_count", "valid", "unsupported_numeric", "total_refs"}``。
    """
    kb = [s for s in (kb_sources or []) if isinstance(s, dict)]
    web = [s for s in (web_sources or []) if isinstance(s, dict)]
    valid_refs = {str(s["ref"]) for s in kb + web if s.get("ref")}
    text = answer or ""

    counts: Dict[str, int] = {}
    invalid: List[str] = []
    invalid_count = 0
    total = 0

    def _sub(m: "re.Match") -> str:
        nonlocal invalid_count, total
        if m.group(1) is not None:
            return m.group(1)  # 代码：原样保留
        ref = m.group(2)
        total += 1
        if ref in valid_refs:
            counts[ref] = counts.get(ref, 0) + 1
            return m.group(0)
        invalid_count += 1
        if ref not in invalid:
            invalid.append(ref)
        return "[?]"

    rewritten = _CODE_OR_CITE_RE.sub(_sub, text)

    for s in kb + web:
        s["cited"] = counts.get(str(s.get("ref") or ""), 0)

    unsupported = 0
    if valid_refs:
        plain = _CODE_RE.sub("", text)
        for sent in _SENTENCE_SPLIT_RE.split(plain):
            sent = _LIST_MARKER_RE.sub("", sent.strip())
            if not sent:
                continue
            cites = _CITE_RE.findall(sent)
            body = _CITE_RE.sub("", sent)
            if re.search(r"\d", body) and not any(c in valid_refs for c in cites):
                unsupported += 1

    return {
        "answer": rewritten,
        "invalid": invalid,
        "invalid_count": invalid_count,
        "valid": total - invalid_count,
        "unsupported_numeric": unsupported,
        "total_refs": total,
    }


# ==================== LLM 自校验（F9 P2-1，可选开关 RAG_SELF_CHECK）====================

SELF_CHECK_NUM_PREDICT = 400
SELF_CHECK_TIMEOUT = 60
SELF_CHECK_MAX_ITEMS = 5


def self_check_enabled() -> bool:
    """读取 ``RAG_SELF_CHECK`` 开关（默认关闭）。"""
    try:
        import config as _cfg
        return bool(getattr(_cfg, "RAG_SELF_CHECK", False))
    except Exception:  # noqa: BLE001
        return False


def build_self_check_prompt(kb_context: str, answer: str) -> str:
    """附录 A「LLM 自校验」提示词：逐条核对回答中的事实句是否被资料支持，只输出 JSON。"""
    return (
        "逐条核对「回答」中的事实句是否被「资料」支持。只输出 JSON："
        '{"unsupported":["原句…"]}；全部支持输出 {"unsupported":[]}\n'
        f"资料：\n{kb_context}\n回答：\n{answer}"
    )


def _self_check_complete(prompt: str) -> str:
    """默认 LLM 调用：全局唯一模型、``think=False``、限制输出长度与超时。失败抛异常。"""
    from collaboration.llm_helper import complete_text
    return complete_text(prompt, num_predict=SELF_CHECK_NUM_PREDICT, timeout=SELF_CHECK_TIMEOUT)


def parse_self_check(raw: str) -> Optional[List[str]]:
    """解析自校验输出为未支持句列表；无法解析返回 None（调用方静默跳过）。"""
    text = _strip_json_fence(str(raw or ""))
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return None
    try:
        data = json.loads(m.group(0))
    except Exception:  # noqa: BLE001
        return None
    items = data.get("unsupported") if isinstance(data, dict) else None
    if not isinstance(items, list):
        return None
    out: List[str] = []
    for it in items:
        t = str(it or "").strip()
        if t and t not in out:
            out.append(t)
    return out


def run_self_check(answer: str, kb_context: str, progress: ProgressCallback = None,
                   complete: Optional[Callable[[str], str]] = None) -> Optional[dict]:
    """知识库命中后的可选自校验：返回 ``{"unsupported": [...], "checked": True}``；失败 / 解析不了返回 None。"""
    if not (answer or "").strip() or not (kb_context or "").strip():
        return None
    _emit(progress, "self_check", "🔍 自校验：逐句核对回答是否被资料支持...")
    fn = complete or _self_check_complete
    try:
        raw = fn(build_self_check_prompt(kb_context, answer))
    except Exception as e:  # noqa: BLE001 - 超时 / 连接失败静默跳过
        logger.debug(f"self_check 调用失败，跳过: {e}")
        _emit(progress, "self_check", "🔍 自校验未完成（调用失败，已跳过）")
        return None
    items = parse_self_check(raw)
    if items is None:
        logger.debug("self_check 输出无法解析，跳过")
        _emit(progress, "self_check", "🔍 自校验未完成（输出无法解析，已跳过）")
        return None
    if items:
        _emit(progress, "self_check", f"🔍 自校验：{len(items)} 句未在资料中找到依据", count=len(items))
    else:
        _emit(progress, "self_check", "🔍 自校验：全部陈述有资料支持", count=0)
    return {"unsupported": items, "checked": True}


_CIRCLED = "①②③④⑤⑥⑦⑧⑨⑩"


def self_check_notice(result: Optional[dict]) -> Optional[dict]:
    """把自校验结果转成 after 位 warn notice；无未支持句返回 None。"""
    items = (result or {}).get("unsupported") or []
    if not items:
        return None
    shown = items[:SELF_CHECK_MAX_ITEMS]
    parts = [f"{_CIRCLED[i] if i < len(_CIRCLED) else str(i + 1) + '.'} {t[:80]}" for i, t in enumerate(shown)]
    more = f" …另 {len(items) - len(shown)} 句" if len(items) > len(shown) else ""
    return make_notice("self_check", "以下陈述未在资料中找到依据：" + " ".join(parts) + more, position="after")


def citation_notices(check: Optional[dict]) -> List[dict]:
    """由 ``verify_citations`` 结果生成 info 级 notices（无问题返回空列表）。"""
    out: List[dict] = []
    if not check:
        return out
    if check.get("invalid"):
        out.append(make_notice("citation", "回答中 [?] 为无效引用，请以来源面板为准", level="info", position="after"))
    n = int(check.get("unsupported_numeric") or 0)
    if n > 0:
        out.append(make_notice("citation", f"{n} 句含数字但未标来源", level="info", position="after"))
    return out


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
    entities: Optional[list] = None,
    on_token: TokenCallback = None,
) -> dict:
    """根据知识库状态生成回答（知识库/网络分区标注、编号引用、综合总结）。

    Args:
        rag_engine: 已初始化的 RAGEngine（其 ``retriever`` 可能为 None）。
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
        entities: 检索规划提取的问题实体（F9 P2-2）；知识库命中后若所有保留片段都不含任一
            实体，发 ``premise_unverified`` 事件 + ``premise`` notice，并在综合 prompt 注入前提核对行。
        on_token: 最终综合回答的增量回调（F10 P1-1）：只有生成正文的那次 LLM 调用流式回调，
            规划 / rerank / 自校验等工具性调用不回调。回调收到的是模型原始输出（未做
            ``<think>`` 剥离与引用校验），最终 ``answer`` 以返回值为准。

    Returns:
        ``{"answer": str, "sources": [...], "web_sources": [...], "kind": "answer"|"fallback"}``。
        sources 仅含知识库来源（带 ``ref``）；``kind="fallback"`` 表示知识库无相关
        片段且网络也无结果（附 ``fallback_question``）。
    """
    kb_initialized = kb_ready(rag_engine)
    _check_stop(should_stop)

    if kb_only and not kb_initialized:
        _emit(progress, "kb_uninitialized", "⚠️ 知识库未初始化")
        return {"answer": "", "sources": [], "web_sources": [], "kind": "answer", "notices": []}

    # /think on：把 progress 交给 _complete，使综合/规划调用的思维链能推送给 UI
    think_on = bool(getattr(rag_engine, "llm_think", False))
    sink_token = _THINKING_SINK.set(progress if think_on else None)
    try:
        return _generate_answer_inner(
            rag_engine, question, original_question, web_search_result,
            show_progress=show_progress, progress=progress,
            rag_progress_callback=rag_progress_callback, should_stop=should_stop,
            history_text=history_text, kb_only=kb_only, subquestions=subquestions,
            web_sources=web_sources, kb_initialized=kb_initialized, entities=entities,
            on_token=on_token,
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
    for res in results:
        if not isinstance(res, dict):
            continue
        for src in res.get("sources") or []:
            if not isinstance(src, dict):
                continue
            where = src.get("file") or src.get("path") or ""
            # 代码块用起始行去重（多个相似函数头的正文前缀可能相同）
            key = (where, f"L{src['start_line']}") if src.get("start_line") is not None else (where, (src.get("content") or "").strip())
            if key in seen:
                continue
            seen.add(key)
            merged.append(src)
    # 分数高的在前，便于后续编号与截断
    merged.sort(key=lambda s: float(s.get("score") or 0), reverse=True)
    return {"answer": "", "sources": merged}


def _generate_answer_inner(
    rag_engine, question, original_question, web_search_result, *,
    show_progress, progress, rag_progress_callback, should_stop, history_text,
    kb_only, subquestions, web_sources, kb_initialized, entities=None, on_token=None,
) -> dict:
    def synthesize(prompt: str) -> str:
        """最终综合调用：有 on_token 时流式，否则与此前完全相同的单参调用（便于测试打桩）。"""
        if on_token is None:
            return llm_direct_answer(prompt)
        return llm_direct_answer(prompt, on_token=on_token, should_stop=should_stop)

    web_sources = [s for s in (web_sources if web_sources is not None else parse_web_sources(web_search_result)) if isinstance(s, dict)]
    assign_refs([], web_sources)

    # 按相关度精简网络上下文：只保留与问题最相关的摘要 + 精选正文，最大化信噪比，
    # 避免全部结果+全文的噪音淹没有效信息、导致 LLM 抓不住重点或误判无答案。
    web_context = compact_web_context(web_search_result, original_question, web_sources) if web_search_result else ""

    # 知识库未初始化：只能用网络/模型自身知识，明确声明来源（F9 P0-5：声明走 notices，
    # answer 只含正文）
    if not kb_initialized:
        if not web_search_result:
            _emit(progress, "kb_uninitialized", "💡 知识库为空，直接使用模型回答（可能不含最新信息）")
        # F9 P1-1：双空（知识库为空且无网络）→ 无依据作答指令 + no_evidence notice
        no_evidence = not web_search_result
        prompt = synthesize_prompt(original_question, kb_context="", web_context=web_context,
                                   history=history_text, no_evidence=no_evidence)
        _emit(progress, "model_thinking", "✍️ 模型生成回答中...")
        answer = synthesize(prompt)
        if web_search_result:
            notices = [make_notice("kb_uninitialized", "知识库为空 · 回答基于网络搜索与模型知识，非你的知识库内容")]
        else:
            notices = [make_notice("no_evidence", NO_EVIDENCE_NOTICE_TEXT)]
        return _finalize_answer(answer, [], web_sources, "answer", notices)

    # 检索知识库（F9 P0-1：只做向量/BM25 检索，不生成初步回答）
    multi_hop = bool(subquestions) and len(subquestions) >= 2
    if multi_hop:
        results = []
        for i, sq in enumerate(subquestions, 1):
            _emit(progress, "kb_retrieving", f"📖 子问题 {i}/{len(subquestions)}：{sq}",
                  current=i, total=len(subquestions), subquestion=sq)
            results.append(_retrieve(rag_engine, sq, show_progress, rag_progress_callback))
            _check_stop(should_stop)
        result = _merge_multi_hop(results)
        syms = source_symbols(result["sources"])
        _emit(progress, "kb_merged",
              f"🔗 合并 {len(subquestions)} 个子问题的检索结果，去重后 {len(result['sources'])} 个片段" + (f"（含代码 {syms}）" if syms else ""),
              count=len(result["sources"]), symbols=[s.get("symbol") for s in result["sources"] if s.get("symbol")])
    else:
        _emit(progress, "kb_retrieving", "📖 检索知识库...")
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
    kb_hit = not is_empty_rag_result({"sources": relevant_sources})

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

    # 知识库命中：以（筛选后的）知识库为主，一律经同一套忠实性 prompt 单次综合
    # （F9 P0-1：删除了"沿用 LlamaIndex 原始回答"的快路径——那份回答由默认英文模板
    # 生成，不含任何忠实性条款与编号引用）。
    if kb_hit:
        assign_refs(relevant_sources, web_sources)
        kb_context = format_kb_context(relevant_sources)
        # F9 P2-2：前提实体校验（零新增调用）——规划提取的实体在所有保留片段中都未出现时，
        # 进度事件 + before 位 warn notice + prompt 注入前提核对行三轨并行
        notices: List[dict] = []
        missing = unverified_entities(entities, relevant_sources)
        if missing:
            names = "」「".join(missing)
            _emit(progress, "premise_unverified", f"⚠️ 问题中的「{names}」未在资料中出现，将先核对前提",
                  entities=missing)
            notices.append(make_notice("premise", f"资料中未出现「{names}」，已先核对前提"))
        prompt = synthesize_prompt(original_question, kb_context, web_context, history=history_text,
                                   premise=premise_note(missing))
        if web_search_result:
            _emit(progress, "synthesizing", "✍️ 综合知识库与网络信息生成回答（带编号引用）...")
        else:
            _emit(progress, "synthesizing", "✍️ 基于知识库综合回答（带编号引用）...")
        answer = synthesize(prompt)
        out = _finalize_answer(answer, relevant_sources, web_sources, "answer", notices)
        # F9 P2-1：可选 LLM 自校验（默认关；一次额外调用；不改正文）
        if self_check_enabled():
            _check_stop(should_stop)
            sc = run_self_check(out["answer"], kb_context, progress=progress)
            out["self_check"] = sc
            n = self_check_notice(sc)
            if n:
                out["notices"].append(n)
        return out

    # 知识库 0 命中（或全部为低相关噪音）：明确告知，再用网络/模型回答。
    _emit(progress, "kb_empty", "📭 知识库中未检索到相关内容。")
    if kb_only:
        return {"answer": "", "sources": [], "web_sources": web_sources, "kind": "answer", "notices": []}
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

    if web_search_result:
        prompt = synthesize_prompt(original_question, kb_context="", web_context=web_context, history=history_text)
        _emit(progress, "model_thinking", "✍️ 模型生成回答中...")
        answer = synthesize(prompt)
        notices = [make_notice("web_only", "知识库无相关内容 · 回答基于网络搜索，非你的知识库内容")]
        return _finalize_answer(answer, [], web_sources, "answer", notices)

    # 失败回退：知识库无相关片段且网络也无结果 → 模型自身知识作答，并建议改用单 Agent
    # 工具进一步查找（建议文案走 ``fallback`` notice，由各端的 retry 行渲染，不再拼进 answer）
    _emit(progress, "model_thinking", "💡 未获取到网络信息，直接使用模型自身知识回答")
    prompt = synthesize_prompt(original_question, kb_context="", web_context="", history=history_text, no_evidence=True)
    answer = synthesize(prompt)
    _emit(progress, "fallback", "🧭 知识库与网络均未找到相关内容，可用单 Agent 进一步查找",
          question=original_question)
    notices = [
        make_notice("no_evidence", NO_EVIDENCE_NOTICE_TEXT),
        make_notice("fallback", fallback_suggestion(original_question), level="info", position="after"),
    ]
    out = _finalize_answer(answer, [], [], "fallback", notices)
    out["fallback_question"] = original_question
    return out


def fallback_suggestion(question: str) -> str:
    """知识库与网络均无结果时的建议文案（F9 P0-5 起作为 ``fallback`` notice 的 text）。"""
    return f"建议：/agent {question} 让 Agent 用工具进一步查找"


def _finalize_answer(answer: str, kb_sources: list, web_sources: list, kind: str, notices: list) -> dict:
    """统一收尾：剥离内联 <think>、有来源时做引用校验并回填 ``cited``、拼装 notices。"""
    from conversation_context import _strip_think
    body = _strip_think(answer or "")
    out = {"answer": body, "sources": kb_sources, "web_sources": web_sources, "kind": kind,
           "notices": list(notices or []), "citation_check": None}
    if kb_sources or web_sources:
        check = verify_citations(body, kb_sources, web_sources)
        out["answer"] = check["answer"]
        out["citation_check"] = check
        out["notices"].extend(citation_notices(check))
    return out


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
    on_token: TokenCallback = None,
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
        on_token: 最终综合回答的增量回调（F10 P1-1），透传给 ``generate_answer``；元查询
            不产生回调。

    Returns:
        统一结构：
        ``{"kind": "meta"|"answer"|"fallback", "answer": str, "kb_sources": [...],
           "web_sources": [...], "meta": {...}|None, "rewritten": str|None,
           "notices": [{"level","code","text","position"}...], "citation_check": {...}|None,
           "model": str}``
        ``rewritten`` 为被改写后的独立问题（未改写时为 None）；``challenge`` 为是否命中质疑句式
        （F9 P1-2，各端据此把「🔗 已理解为」改为「🔁 用户质疑，重新核对」）；``answer`` 只含正文，
        警示 / 引用校验等"关于可信度的信息"在 ``notices``（F9 P0-5）；``citation_check``
        为 ``verify_citations`` 结果（无来源时 None）；``model`` 为本次作答的 LLM 名。
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
            "notices": [],
            "citation_check": None,
            "model": _current_model_name(rag_engine),
            "challenge": False,
        }

    # 连续对话：疑似追问时改写为独立问题；并取最近几轮紧凑文本供综合 prompt
    effective = question
    rewritten = None
    challenge = False
    history_text = ""
    if context is not None:
        try:
            rw = context.rewrite_question(question, progress=progress)
            challenge = bool(rw.get("challenge"))
            if rw.get("changed"):
                effective = rw["question"]
                rewritten = effective
            history_text = context.history_text(turns=3)
        except Exception as e:  # noqa: BLE001 - 上下文层故障不影响作答
            logger.warning(f"读取会话上下文失败，按无历史处理: {e}")
        _check_stop(should_stop)

    kb_initialized = kb_ready(rag_engine)
    if not kb_initialized:
        _emit(progress, "kb_uninitialized", "⚠️ 知识库未初始化，将根据网络搜索/模型直接回答")

    # /think on：整条链路（规划/综合）的思维链都透出到 progress
    think_on = bool(getattr(rag_engine, "llm_think", False))
    sink_token = _THINKING_SINK.set(progress if think_on else None)
    try:
        out = _answer_question_planned(
            rag_engine, question, effective, rewritten, history_text, kb_initialized,
            enable_web_search=enable_web_search, show_progress=show_progress, progress=progress,
            rag_progress_callback=rag_progress_callback, should_stop=should_stop, kb_only=kb_only,
            on_token=on_token,
        )
        out["challenge"] = challenge
        return out
    finally:
        _THINKING_SINK.reset(sink_token)


def _answer_question_planned(
    rag_engine, question, effective, rewritten, history_text, kb_initialized, *,
    enable_web_search, show_progress, progress, rag_progress_callback, should_stop, kb_only,
    on_token=None,
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
        entities=(plan or {}).get("entities") or [],
        on_token=on_token,
    )

    kb_sources, web_sources = assign_refs(result.get("sources", []), result.get("web_sources", web_sources))
    out = {
        "kind": result.get("kind") or "answer",
        "answer": result.get("answer", ""),
        "kb_sources": kb_sources,
        "web_sources": web_sources,
        "meta": None,
        "rewritten": rewritten,
        "notices": list(result.get("notices") or []),
        "citation_check": result.get("citation_check"),
        "self_check": result.get("self_check"),
        "model": _current_model_name(rag_engine),
    }
    if out["kind"] == "fallback":
        out["fallback_question"] = result.get("fallback_question") or question
    return out


def _current_model_name(rag_engine) -> str:
    """本次作答使用的 LLM 名：优先引擎当前模型（随 /model 热切换），否则 config.LLM_MODEL。"""
    name = getattr(rag_engine, "llm_model", None)
    if isinstance(name, str) and name:
        return name
    try:
        from config import LLM_MODEL
        return str(LLM_MODEL)
    except Exception:  # noqa: BLE001
        return ""


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
