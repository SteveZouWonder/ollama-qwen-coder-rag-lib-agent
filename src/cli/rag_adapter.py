"""共享 RAG 编排层（``rag_pipeline``）的 CLI 适配（F10 P3-2-b 由 ``query_interface`` 外迁）。

高级 RAG 逻辑（网络搜索规划、多查询合并、页面增强、元查询直答、双区综合、
0 命中回退）在 ``rag_pipeline`` 供 CLI 与 Web 复用；这里保留同名薄封装以维持
向后兼容，实际逻辑全部转调 rag_pipeline。CLI 独有的 Rich 终端渲染由
``_cli_ask_progress`` 承接。
"""
import rag_pipeline
from cli import state
from cli.render import _render_meta_overview


# ==================== 共享 RAG 编排层的 CLI 适配 ====================
# 以下高级 RAG 逻辑（网络搜索规划、多查询合并、页面增强、元查询直答、
# 双区综合、0 命中回退）已下沉到 ``rag_pipeline``，供 CLI 与 Web 复用。
# 这里保留同名薄封装以维持向后兼容（测试/其它模块可能仍引用），实际逻辑
# 全部转调 rag_pipeline。CLI 独有的 Rich 终端渲染由 _cli_ask_progress 承接。

_simple_web_search = rag_pipeline.simple_web_search
_llm_direct_answer = rag_pipeline.llm_direct_answer
plan_web_search = rag_pipeline.plan_web_search
_merge_search_results = rag_pipeline._merge_search_results
_extract_urls = rag_pipeline._extract_urls
_is_empty_rag_result = rag_pipeline.is_empty_rag_result
_is_meta_query = rag_pipeline.is_meta_query
_parse_web_sources = rag_pipeline.parse_web_sources


_format_kb_context = rag_pipeline.format_kb_context


def run_web_search(queries: list) -> str:
    """兼容封装：执行网络搜索，进度经 CLI 渲染。"""
    return rag_pipeline.run_web_search(queries, progress=_cli_ask_progress)


def enrich_with_page_content(search_result: str) -> str:
    """兼容封装：页面正文增强，进度经 CLI 渲染。"""
    return rag_pipeline.enrich_with_page_content(search_result, progress=_cli_ask_progress)


def _cli_ask_progress(event: dict):
    """把 rag_pipeline 的结构化进度事件渲染到 Rich 终端（CLI 专属）。"""
    stage = event.get("stage", "")
    msg = event.get("message", "")

    if stage == "meta_overview":
        _render_meta_overview(event)
        return

    style_map = {
        "web_search_start": "cyan",
        "web_query": "dim",
        "web_query_empty": "dim",
        "web_search_done": "green",
        "web_search_empty": "yellow",
        "web_search_failed": "yellow",
        "enrich_start": "dim",
        "enrich_page_failed": "dim",
        "enrich_page_blocked": "cyan",   # F9 P1-3：丢弃疑似注入页面
        "premise_unverified": "yellow",  # F9 P2-2：前提实体未在资料中出现
        "self_check": "dim",             # F9 P2-1：LLM 自校验
        "enrich_done": "green",
        "kb_empty": "yellow",
        "kb_fallback_search": "cyan",
        "kb_uninitialized": "yellow",
        "context_rewrite": "cyan",
        "context_rewritten": "cyan",
    }
    style = style_map.get(stage, "dim")
    if stage == "thinking":
        # /think on：模型思维链（已截断 800 字），dim 样式、转义避免被当作 Rich 标记
        from rich.markup import escape as _escape
        state.console.print(f"[dim]{_escape(msg)}[/dim]")
    elif stage == "fallback":
        state.console.print(msg, style="yellow")  # 具体 /agent 提示在回答渲染后由 _run_ask 打印
    elif stage in ("kb_retrieving", "synthesizing", "model_thinking", "rerank",
                   "context_compress", "context_compressed"):
        # 这些"进行中"提示走安静的 dim 行，避免打断 status
        state.console.print(f"[dim]{msg}[/dim]")
    elif msg:
        state.console.print(msg, style=style)


def _answer_meta_query() -> bool:
    """兼容封装：直接渲染知识库概览。"""
    overview = rag_pipeline.build_meta_overview(state.rag_engine)
    _render_meta_overview({"files": overview["files"], "stats": overview["stats"]})
    return True


def _synthesize_prompt(question: str, kb_context: str, web_context: str) -> str:
    """组装“知识库/网络分区标注”的结构化 prompt，要求 LLM 区分来源并综合总结。"""
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
