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

``stage`` 取值：``meta_overview`` | ``web_search_start`` | ``web_query`` |
``web_query_empty`` | ``web_search_done`` | ``web_search_empty`` |
``web_search_failed`` | ``enrich_start`` | ``enrich_page_failed`` |
``enrich_done`` | ``kb_retrieving`` | ``kb_empty`` | ``kb_fallback_search`` |
``synthesizing`` | ``model_thinking`` | ``kb_uninitialized`` 等。
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

# 可选进度回调类型：接收一个结构化事件 dict。
ProgressCallback = Optional[Callable[[Dict[str, Any]], None]]


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


# ==================== LLM 基础调用 ====================

def llm_direct_answer(prompt: str) -> str:
    """用 LLM 直接回答（不经过知识库检索）。失败时返回错误说明。"""
    try:
        from llama_index.core import Settings
        resp = Settings.llm.complete(prompt)
        return str(resp)
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


def plan_web_search(question: str) -> dict:
    """用 LLM 判断问题是否需要联网搜索，并生成优化后的搜索查询。

    Returns:
        ``{"needs_search": bool, "queries": [str, ...]}``；queries 已去重。
        对非国内查询，会补一条英文查询提升召回；对国内查询（价格/售价/淘宝/京东
        等语境）则只保留中文查询，避免英文结果把国内电商/国行价格挤出结果。
        LLM 不可用时回退到轻量触发词。
    """
    domestic = _is_domestic_query(question)

    if domestic:
        query_rule = (
            "若需要搜索，请生成 1-2 条精简、高质量的**中文**搜索查询词（去掉'帮我'"
            "'请问'等口语化前后缀，只保留核心检索词）。这是面向中国国内的查询，"
            "请勿生成英文查询。\n"
        )
    else:
        query_rule = (
            "若需要搜索，请生成 1-3 条精简、高质量的搜索查询词（去掉'帮我''请问'"
            "等口语化前后缀，只保留核心检索词）；若原问题为中文，请额外补充一条"
            "等价的英文查询以提升召回。\n"
        )

    prompt = (
        "你是一个搜索规划助手。判断回答下面这个问题是否需要联网搜索"
        "最新/实时/外部信息（例如：版本号、新闻、价格、近期事件、特定事实）。"
        "如果问题可以仅凭通用知识回答，或属于代码/写作/推理类任务，则不需要搜索。\n"
        + query_rule +
        "严格只输出 JSON，格式：\n"
        '{"needs_search": true/false, "queries": ["查询1", "query2"]}\n\n'
        f"问题：{question}"
    )

    try:
        from llama_index.core import Settings
        raw = str(Settings.llm.complete(prompt)).strip()
        data = json.loads(_strip_json_fence(raw))
        needs = bool(data.get("needs_search", False))
        queries = [
            q.strip()
            for q in (data.get("queries") or [])
            if isinstance(q, str) and q.strip()
        ]
        # 国内查询：保险起见剔除 LLM 仍可能生成的英文查询（避免海外结果稀释）
        if domestic:
            filtered = [q for q in queries if not _is_mostly_ascii(q)]
            queries = filtered or queries  # 全被过滤则保底沿用
        seen = set()
        deduped = []
        for q in queries:
            if q.lower() not in seen:
                seen.add(q.lower())
                deduped.append(q)
        if needs and not deduped:
            deduped = [question]
        return {"needs_search": needs, "queries": deduped}
    except Exception as e:  # noqa: BLE001 - LLM/JSON 失败时回退到启发式
        logger.warning(f"LLM 搜索规划失败，回退到启发式判断: {e}")
        lowered = question.lower()
        needs = any(hint in lowered for hint in _WEB_SEARCH_FALLBACK_HINTS)
        return {"needs_search": needs, "queries": [question] if needs else []}


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


# 增强参数：提取前 N 个高排名结果页正文，每页保留的字符数。
_ENRICH_MAX_PAGES = 3
_ENRICH_PER_PAGE_CHARS = 2000


def enrich_with_page_content(search_result: str, progress: ProgressCallback = None) -> str:
    """对搜索结果做可选增强：提取前若干个高排名结果页正文并追加。"""
    urls = _extract_urls(search_result, _ENRICH_MAX_PAGES)
    if not urls:
        return search_result

    try:
        from agent_tools import web_content_extract
    except Exception as e:  # noqa: BLE001
        _emit(progress, "enrich_page_failed", f"⚠️ 无法导入内容提取工具: {e}")
        return search_result

    _emit(progress, "enrich_start", "📄 正在提取相关页面内容...")
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
        from llama_index.core import Settings
        raw = str(Settings.llm.complete(prompt)).strip().lower()
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

def synthesize_prompt(question: str, kb_context: str, web_context: str) -> str:
    """组装"知识库/网络分区标注"的结构化 prompt，要求 LLM 区分来源并综合总结。"""
    parts = [
        "你是一个严谨的问答助手。请根据下面两类来源回答问题，并遵守规则：",
        "1. 【知识库检索内容】来自用户的本地知识库，是权威且优先的依据；",
        "2. 【网络搜索补充】来自互联网，仅作补充参考，可能不准确；",
        "3. 回答中必须明确区分：哪些结论来自知识库、哪些来自网络；",
        "4. 若两类来源冲突，以知识库为准并指出差异；",
        "5. 若知识库内容不足以回答，明确说明，再用网络信息补充。",
        "",
        f"【问题】\n{question}",
        "",
    ]
    if kb_context:
        parts.append(f"【知识库检索内容】（本地文档，优先依据）\n{kb_context}")
    else:
        parts.append("【知识库检索内容】\n（无相关内容）")
    parts.append("")
    if web_context:
        parts.append(f"【网络搜索补充】（互联网，仅供参考）\n{web_context}")
    else:
        parts.append("【网络搜索补充】\n（无）")
    parts.append("")
    parts.append("请给出综合回答，并在末尾用一句话说明主要依据来自知识库还是网络。")
    return "\n".join(parts)


def format_kb_context(sources: list) -> str:
    """把知识库来源拼成带文件标注的上下文文本，供综合 prompt 使用。"""
    blocks = []
    for i, src in enumerate(sources, 1):
        content = (src.get("content") or "").strip()
        if not content:
            continue
        fname = src.get("file", "未知文件")
        blocks.append(f"[片段{i}｜来自 {fname}]\n{content}")
    return "\n\n".join(blocks)


# ==================== 网络搜索增强编排 ====================

def augment_with_web_search(question: str, progress: ProgressCallback = None) -> str:
    """按需执行 LLM 规划的网络搜索，返回搜索结果文本（无则空串）。"""
    try:
        plan = plan_web_search(question)
        if plan.get("needs_search") and plan.get("queries"):
            _emit(progress, "web_search_start", "🌐 检测到需要最新信息，正在网络搜索...")
            result = run_web_search(plan["queries"], progress=progress)
            if result:
                _emit(progress, "web_search_done", "✅ 网络搜索完成")
                return enrich_with_page_content(result, progress=progress)
            _emit(progress, "web_search_empty", "⚠️ 所有搜索查询均未返回有效结果，继续使用知识库")
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
) -> dict:
    """根据知识库状态生成回答（知识库/网络分区标注、综合总结）。

    Args:
        rag_engine: 已初始化的 RAGEngine（其 ``query_engine`` 可能为 None）。
        question: 用于检索的问题（可能已被内联文件入库逻辑改写）。
        original_question: 用户原始问题，用于综合 prompt 与声明来源。
        web_search_result: 预先执行的网络搜索结果文本（可为空）。
        show_progress: 是否把 RAG 检索进度透传给 ``rag_progress_callback``。
        progress: 编排级进度回调（网络回退、综合、思考等阶段）。
        rag_progress_callback: 直接透传给 ``query_with_sources`` 的进度回调。

    Returns:
        ``{"answer": str, "sources": [...]}``。sources 仅含知识库来源。
    """
    kb_initialized = rag_engine.query_engine is not None

    # 知识库未初始化：只能用网络/模型自身知识，明确声明来源
    if not kb_initialized:
        if not web_search_result:
            _emit(progress, "kb_uninitialized", "💡 知识库为空，直接使用模型回答（可能不含最新信息）")
        prompt = synthesize_prompt(original_question, kb_context="", web_context=web_search_result)
        _emit(progress, "model_thinking", "模型思考中...")
        answer = llm_direct_answer(prompt)
        if web_search_result:
            answer = "⚠️ 以下回答基于网络搜索与模型知识，非你的知识库内容：\n\n" + answer
        return {"answer": answer, "sources": []}

    # 检索知识库
    _emit(progress, "kb_retrieving", "检索知识库...")
    if show_progress and rag_progress_callback is not None:
        result = rag_engine.query_with_sources(question, progress_callback=rag_progress_callback)
    else:
        result = rag_engine.query_with_sources(question)

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

    # LLM 相关性判定（治本）：纯 embedding 分数无法区分"话题相关"，用 LLM 判断
    # 这些片段是否真能帮助回答问题；判为无关则视为未命中，避免把 0.45 这类勉强
    # 过阈值但话题不搭的噪音（如问"售价"却召回 Cloudflare 配置）当作依据展示。
    if kb_hit:
        _emit(progress, "kb_relevance_check", "校验知识库片段相关性...")
        if not judge_kb_relevance(original_question, relevant_sources):
            _emit(progress, "kb_irrelevant", "🧹 知识库片段与问题无关，已忽略")
            kb_hit = False

    # 知识库命中：以（过滤后的）知识库为主。
    if kb_hit:
        # 快路径：没有过滤掉任何片段、也没有网络补充时，直接沿用 LlamaIndex 的
        # 原始回答（它正是基于这些相关片段生成的），避免多余的 LLM 调用。
        if dropped == 0 and not web_search_result:
            return {"answer": result.get("answer", ""), "sources": relevant_sources}

        # 否则（过滤掉了噪音，或需要综合网络补充）基于"仅相关片段"重新综合，
        # 避免 LlamaIndex 原始回答里混入被过滤掉的噪音内容。
        kb_context = format_kb_context(relevant_sources)
        prompt = synthesize_prompt(original_question, kb_context, web_search_result)
        if web_search_result:
            _emit(progress, "synthesizing", "综合知识库与网络信息...")
        else:
            _emit(progress, "synthesizing", "基于知识库综合回答...")
        answer = llm_direct_answer(prompt)
        return {"answer": answer, "sources": relevant_sources}

    # 知识库 0 命中（或全部为低相关噪音）：明确告知，再用网络/模型回答。
    _emit(progress, "kb_empty", "📭 知识库中未检索到相关内容。")
    if not web_search_result:
        _emit(progress, "kb_fallback_search", "🌐 正在网络搜索补充信息...")
        web_search_result = simple_web_search(original_question)
        if web_search_result:
            _emit(progress, "web_search_done", "✅ 网络搜索完成")

    prompt = synthesize_prompt(original_question, kb_context="", web_context=web_search_result)
    _emit(progress, "model_thinking", "模型思考中...")
    answer = llm_direct_answer(prompt)
    if web_search_result:
        answer = "⚠️ 知识库中无相关内容，以下回答基于网络搜索，非你的知识库内容：\n\n" + answer
    else:
        _emit(progress, "model_thinking", "💡 未获取到网络信息，直接使用模型自身知识回答")
        answer = "⚠️ 知识库中无相关内容，以下为模型自身知识回答：\n\n" + answer
    return {"answer": answer, "sources": []}


# ==================== 顶层入口：完整问答编排 ====================

def answer_question(
    rag_engine,
    question: str,
    *,
    enable_web_search: bool = True,
    show_progress: bool = True,
    progress: ProgressCallback = None,
    rag_progress_callback: ProgressCallback = None,
) -> dict:
    """完整的知识库问答编排入口，CLI 与 Web 共享。

    覆盖：元/概览问题直答、LLM 驱动网络搜索增强、知识库/网络双区综合、
    0 命中网络回退。**不包含**内联文件入库（该逻辑与交互强相关，保留在
    CLI 层，调用本函数前自行处理并传入改写后的 question）。

    Args:
        rag_engine: 已初始化的 RAGEngine。
        question: 用户问题（若外部已做内联文件入库改写，请传改写后的文本）。
        enable_web_search: 是否启用 LLM 规划的网络搜索增强。
        show_progress: 是否透传 RAG 检索进度。
        progress: 编排级进度回调。
        rag_progress_callback: 透传给 query_with_sources 的进度回调。

    Returns:
        统一结构：
        ``{"kind": "meta"|"answer", "answer": str, "kb_sources": [...],
           "web_sources": [...], "meta": {...}|None}``
    """
    question = (question or "").strip()

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
        }

    if rag_engine.query_engine is None:
        _emit(progress, "kb_uninitialized", "⚠️ 知识库未初始化，将根据网络搜索/模型直接回答")

    # 网络搜索增强（LLM 驱动的通用查询规划）
    web_search_result = ""
    if enable_web_search:
        web_search_result = augment_with_web_search(question, progress=progress)
    web_sources = parse_web_sources(web_search_result) if web_search_result else []

    result = generate_answer(
        rag_engine,
        question,
        question,
        web_search_result,
        show_progress=show_progress,
        progress=progress,
        rag_progress_callback=rag_progress_callback,
    )

    return {
        "kind": "answer",
        "answer": result.get("answer", ""),
        "kb_sources": result.get("sources", []),
        "web_sources": web_sources,
        "meta": None,
    }


# ==================== 对话落库（会话持久化）====================

def record_conversation(user_content: str, assistant_content: str) -> None:
    """将一轮对话写入"当前会话"，作为对话历史的单一来源。

    若当前没有会话则自动创建，使 CLI/Web 的 /ask、/agent 对话始终被持久化。
    """
    try:
        from session_manager import get_session_manager
        manager = get_session_manager()
        session = manager.get_current_session()
        if session is None:
            session = manager.create_session()
            logger.info(f"自动创建会话用于记录对话: {session.session_id}")
        if user_content:
            session.add_message("user", user_content)
        if assistant_content:
            session.add_message("assistant", assistant_content)
        manager.save_session(session)
    except Exception as e:  # noqa: BLE001
        logger.error(f"记录对话到会话失败: {e}")
