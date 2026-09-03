"""Gradio 界面组装（薄 UI 层）。

本模块只负责组件布局与事件绑定，全部业务逻辑委托给 ``services.WebService``。
纯格式化辅助函数（``format_*``）与 UI 处理器工厂（``build_handlers``）不依赖
gradio，可独立做单元测试；真正调用 gradio 的 ``build_app`` / ``launch`` 部分标注
``pragma: no cover``（UI 装配不做单元测试，通过手动/集成验证）。
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Tuple

from .services import WebService, get_web_service


# ==================== 纯格式化辅助（可测试）====================

def format_sources(sources: List[Dict[str, Any]]) -> str:
    """把 sources 列表渲染为 Markdown 文本。"""
    if not sources:
        return "_无引用来源_"
    lines = ["### 引用来源", ""]
    for i, src in enumerate(sources, 1):
        score = src.get("score")
        score_str = f"（相似度 {score:.3f}）" if isinstance(score, (int, float)) else ""
        file_name = src.get("file", "未知")
        content = (src.get("content") or "").strip()
        lines.append(f"**{i}. {file_name}** {score_str}")
        if content:
            lines.append(f"> {content}")
        lines.append("")
    return "\n".join(lines).rstrip()


def format_web_sources(sources: List[Dict[str, Any]]) -> str:
    """把网络来源列表渲染为 Markdown 文本（与知识库来源明确区分）。"""
    if not sources:
        return ""
    lines = ["### 🌐 网络来源", ""]
    for i, src in enumerate(sources, 1):
        title = src.get("title", "") or src.get("url", "")
        url = src.get("url", "")
        if url:
            lines.append(f"{i}. [{title}]({url})")
        else:
            lines.append(f"{i}. {title}")
    return "\n".join(lines)


def format_meta_overview(meta: Dict[str, Any]) -> str:
    """把知识库概览（元查询直答）渲染为 Markdown。"""
    files = (meta or {}).get("files") or []
    stats = (meta or {}).get("stats") or {}
    lines = ["### 📚 知识库概览", ""]
    if not files:
        lines.append("_知识库中暂无已登记的文件。_")
        if stats.get("total_documents"):
            lines.append(
                f"\n（向量库中存在 {stats['total_documents']} 个文档片段，"
                f"但未登记文件元数据）"
            )
    else:
        lines.append(f"共有 **{len(files)}** 个文件：")
        for fm in files:
            lines.append(f"- 📄 `{fm.get('path')}`（{fm.get('size', '?')}）")
    if stats:
        lines.append("")
        lines.append(
            f"文档片段总数: {stats.get('total_documents', '?')} | "
            f"Embedding: `{stats.get('embed_model', '?')}`"
        )
    return "\n".join(lines)


def format_rag_side(result: Dict[str, Any]) -> str:
    """组合 RAG 回答的附加信息区：知识库来源 + 网络来源。"""
    parts = []
    kb = format_sources(result.get("sources", []))
    if kb and kb != "_无引用来源_":
        parts.append(kb)
    web = format_web_sources(result.get("web_sources", []))
    if web:
        parts.append(web)
    if not parts:
        return "_无引用来源_"
    return "\n\n".join(parts)


def format_stats(stats: Dict[str, Any]) -> str:
    """把知识库统计渲染为 Markdown 文本。"""
    if "error" in stats:
        return f"[错误] 获取统计失败: {stats['error']}"
    return (
        f"- 文档片段总数: **{stats.get('total_documents', 0)}**\n"
        f"- LLM 模型: `{stats.get('llm_model', '?')}`"
        + (f"（num_ctx={stats['llm_num_ctx']}）" if stats.get("llm_num_ctx") else "")
        + "\n"
        f"- Embedding 模型: `{stats.get('embed_model', '?')}`\n"
        f"- 分块大小: {stats.get('chunk_size', '?')}\n"
        f"- 分块重叠: {stats.get('chunk_overlap', '?')}\n"
        f"- 检索数量 TOP_K: {stats.get('top_k', '?')}"
    )


def format_model_status(info: Dict[str, Any]) -> str:
    """把当前模型概况渲染为一行 Markdown 状态（对话页顶部显示）。"""
    if info.get("error"):
        return f"**模型**: `{info.get('model', '?')}`  ·  [错误] {info['error']}"
    if info.get("loaded"):
        size = info.get("size_bytes") or 0
        gb = size / (1024 ** 3)
        state = f"已加载，驻留 {gb:.1f} GB" if gb >= 0.1 else "已加载"
    else:
        state = "未加载（首次提问时按需加载）"
    think = "开" if info.get("think") else "关"
    line = (
        f"**模型**: `{info.get('model', '?')}`  ·  {state}  ·  "
        f"num_ctx={info.get('num_ctx', '?')}  ·  思考模式 {think}"
    )
    others = [m for m in info.get("loaded_models", []) if m != info.get("model")]
    if others:
        line += f"  ·  ⚠️ 内存中还驻留: {', '.join(f'`{m}`' for m in others)}"
    return line


def format_switch_result(result: Dict[str, Any]) -> str:
    """把模型切换结果渲染为 Markdown。"""
    prefix = "✅" if result.get("ok") else "❌"
    return f"{prefix} {result.get('message', '')}"


def format_multi_agent_result(result: Dict[str, Any]) -> str:
    """把多 Agent 协作结果渲染为 Markdown 文本。"""
    if not result.get("success"):
        err = result.get("error", "")
        summary = result.get("summary", "协作失败")
        return f"**❌ {summary}**\n\n{err}".strip()

    lines = [f"**✅ {result.get('summary', '协作完成')}**", ""]
    stats = (
        f"成功 {result.get('successful_results', 0)} / "
        f"共 {result.get('total_results', 0)}"
    )
    lines.append(stats)
    lines.append("")
    for r in result.get("results", []):
        status = "✅" if r.get("success") else "❌"
        agent_id = r.get("agent_id", "?")
        output = (r.get("output") or "").strip()
        lines.append(f"{status} **{agent_id}**")
        if output:
            lines.append(f"> {output}")
        lines.append("")
    return "\n".join(lines).rstrip()


def format_sessions(sessions: List[Dict[str, Any]]) -> str:
    """把会话列表渲染为 Markdown 文本。"""
    if not sessions:
        return "_暂无会话_"
    lines = ["### 会话列表", ""]
    for s in sessions:
        marker = "▶ " if s.get("is_current") else "  "
        lines.append(
            f"{marker}`{s.get('session_id', '')[:8]}` "
            f"{s.get('title', '未命名')} "
            f"（{s.get('messages', 0)} 条消息）"
        )
    return "\n".join(lines)


def format_graph_result(result: Dict[str, Any]) -> str:
    """把知识图谱查询结果渲染为 Markdown 文本。"""
    entities = result.get("entities", [])
    relations = result.get("relations", [])
    explanation = result.get("explanation", "")
    if not entities and not relations:
        return explanation or "_未找到相关实体_"
    lines = []
    if explanation:
        lines.append(explanation)
        lines.append("")
    if entities:
        lines.append("### 实体")
        for e in entities:
            lines.append(f"- **{e.get('text', '?')}** ({e.get('entity_type', '?')})")
        lines.append("")
    if relations:
        lines.append("### 关系")
        for r in relations:
            src = r.get("source", {}).get("text", "?")
            tgt = r.get("target", {}).get("text", "?")
            rel = r.get("relation_type", "?")
            lines.append(f"- {src} --[{rel}]--> {tgt}")
    return "\n".join(lines).rstrip()


# ==================== UI 处理器工厂（可测试）====================

def build_handlers(service: WebService) -> Dict[str, Callable]:
    """构造绑定到 service 的 UI 处理器集合。

    处理器返回值均为已格式化的字符串/数据，供 Gradio 组件直接展示。
    这些处理器不依赖 gradio，可独立单元测试。
    """

    def on_chat(
        message: str,
        mode: str,
        enable_web: bool = True,
        auto_confirm: bool = False,
    ) -> Tuple[str, str]:
        """统一对话入口，按模式分发。返回 (回答, 附加信息 Markdown)。

        Args:
            enable_web: RAG 模式下是否启用 LLM 驱动的网络搜索增强（与 CLI 对齐）。
            auto_confirm: 单 Agent 模式下是否自动确认危险命令（等价 CLI ``--yes``）。
        """
        message = (message or "").strip()
        if not message:
            return "", "_请输入内容_"

        if mode == "多 Agent 协作":
            result = service.multi_agent_run(message)
            return "", format_multi_agent_result(result)

        if mode == "单 Agent":
            answer = ""
            steps: List[str] = []
            # 危险命令确认：勾选"自动确认"时全部放行（等价 CLI --yes），
            # 否则默认拒绝以保证安全（用户可勾选后重试）。
            confirm_handler = (lambda evt: True) if auto_confirm else None
            for evt in service.agent_chat_stream(message, confirm_handler=confirm_handler):
                if evt.kind == "step":
                    steps.append(f"- {evt.message}")
                elif evt.kind == "answer":
                    answer = evt.message
                elif evt.kind == "error":
                    return "", f"[错误] {evt.message}"
            side = "### 执行过程\n" + "\n".join(steps) if steps else ""
            return answer, side

        # 默认 RAG 模式（与 CLI /ask 编排一致：可选网络搜索、双区综合、元查询直答）
        result = service.rag_query(message, enable_web_search=enable_web)
        # 元查询：直接展示知识库概览
        if result.get("kind") == "meta":
            return format_meta_overview(result.get("meta") or {}), ""
        return result["answer"], format_rag_side(result)

    def on_chat_stream(
        message: str,
        mode: str,
        enable_web: bool = True,
        auto_confirm: bool = False,
    ):
        """流式对话入口（供 Gradio 使用）：点击后立即反馈"处理中"，随后逐步更新。

        此前 ``on_chat`` 是同步阻塞函数：开启联网搜索的 RAG（或 Agent 任务）
        往往需数十秒，期间界面无任何反馈，用户误以为"点了没效果"。改为
        generator 后，Gradio 会先渲染占位提示与实时进度，最后替换为完整结果。

        yield ``(answer_markdown, side_markdown)`` 二元组，与 ``on_chat`` 输出
        契约一致。
        """
        message = (message or "").strip()
        if not message:
            yield "", "_请输入内容_"
            return

        # 立即反馈：点击后马上出现，消除"无响应"错觉
        yield "", "⏳ 正在处理，请稍候…"

        if mode == "多 Agent 协作":
            yield "", "⏳ 多 Agent 协作执行中…（分解 → 调度 → 执行 → 整合）"
            result = service.multi_agent_run(message)
            yield "", format_multi_agent_result(result)
            return

        if mode == "单 Agent":
            answer = ""
            steps: List[str] = []
            confirm_handler = (lambda evt: True) if auto_confirm else None
            for evt in service.agent_chat_stream(message, confirm_handler=confirm_handler):
                if evt.kind == "step":
                    steps.append(f"- {evt.message}")
                    yield "", "### 执行过程（进行中）\n" + "\n".join(steps)
                elif evt.kind == "answer":
                    answer = evt.message
                elif evt.kind == "error":
                    yield "", f"[错误] {evt.message}"
                    return
            side = "### 执行过程\n" + "\n".join(steps) if steps else ""
            yield answer, side
            return

        # 默认 RAG 模式：消费流式事件，实时展示进度（网络搜索/综合/思考等）
        progress_lines: List[str] = []
        final = None
        for evt in service.rag_query_stream(message, enable_web_search=enable_web):
            if evt.kind == "progress":
                msg = (evt.message or "").strip()
                if msg:
                    progress_lines.append(f"- {msg}")
                    yield "", "### 处理进度\n" + "\n".join(progress_lines[-12:])
            elif evt.kind == "answer":
                final = evt.data or {}
                final["answer"] = evt.message
            elif evt.kind == "error":
                yield "", f"[错误] {evt.message}"
                return

        if final is None:
            yield "", "_未获得回答_"
            return
        if final.get("kind") == "meta":
            yield format_meta_overview(final.get("meta") or {}), ""
            return
        yield final.get("answer", ""), format_rag_side(
            {
                "sources": final.get("sources", []),
                "web_sources": final.get("web_sources", []),
            }
        )

    def on_upload(file_paths: Optional[List[str]]) -> Tuple[str, str]:
        msg = service.add_documents(file_paths or [])
        return msg, format_stats(service.get_stats())

    def on_refresh_stats() -> str:
        return format_stats(service.get_stats())

    def on_clear_index() -> Tuple[str, str]:
        msg = service.clear_index()
        return msg, format_stats(service.get_stats())

    def on_list_sessions() -> str:
        return format_sessions(service.list_sessions())

    def on_create_session(title: str) -> Tuple[str, str]:
        sid = service.create_session(title)
        return f"已创建会话 {sid[:8]}", format_sessions(service.list_sessions())

    def on_switch_session(session_id: str) -> Tuple[str, str]:
        """切换到指定会话（等价 CLI /session-switch）。"""
        session_id = (session_id or "").strip()
        if not session_id:
            return "_请输入会话 ID_", format_sessions(service.list_sessions())
        ok = service.switch_session(session_id)
        msg = f"已切换到会话 {session_id[:8]}" if ok else f"切换失败：未找到会话 {session_id[:8]}"
        return msg, format_sessions(service.list_sessions())

    def on_search_sessions(query: str) -> str:
        """按关键词搜索会话（等价 CLI /session-search）。"""
        results = service.search_sessions(query)
        if not results:
            return "_未找到匹配的会话_"
        lines = ["### 搜索结果", ""]
        for s in results:
            lines.append(f"- `{s.get('session_id', '')[:8]}` {s.get('title', '未命名')}")
        return "\n".join(lines)

    def on_rebuild_index(data_path: str) -> Tuple[str, str]:
        """按路径重建知识库索引（等价 CLI --data 构建）。"""
        msg = service.rebuild_index((data_path or "").strip() or None)
        return msg, format_stats(service.get_stats())

    def on_query_graph(entity: str) -> str:
        return format_graph_result(service.query_graph_entity(entity))

    def on_graph_summary() -> str:
        """展示知识图谱概览（等价 service.graph_summary）。"""
        summary = service.graph_summary()
        if not summary.get("is_available", True) and summary.get("error"):
            return f"_知识图谱不可用：{summary.get('error')}_"
        lines = ["### 🕸️ 知识图谱概览", ""]
        for k, v in summary.items():
            lines.append(f"- {k}: **{v}**")
        return "\n".join(lines)

    def on_stop() -> str:
        return "已发送停止信号" if service.stop_agent() else "当前没有运行中的任务"

    # ---------- 模型管理（热切换）----------

    def on_model_status() -> str:
        return format_model_status(service.current_model())

    def on_model_choices() -> Tuple[List[str], str]:
        """返回 (可选模型列表, 当前模型)，供下拉框初始化/刷新。"""
        choices = service.list_models()
        current = service.current_model().get("model", "")
        if current and current not in choices:
            choices = [current] + choices
        return choices, current

    def on_switch_model(model: str) -> Tuple[str, str]:
        """切换模型；返回 (切换结果, 刷新后的状态行)。"""
        model = (model or "").strip()
        if not model:
            return "❌ 请选择模型", on_model_status()
        result = service.switch_model(model)
        return format_switch_result(result), on_model_status()

    def on_toggle_think(enabled: bool) -> Tuple[str, str, bool]:
        """开关思考模式；返回 (结果, 刷新后的状态行, 复选框应显示的实际值)。

        若当前模型不支持 thinking，服务层会拒绝开启，此时把复选框回弹为实际状态。
        """
        result = service.set_think(bool(enabled))
        return format_switch_result(result), on_model_status(), bool(result.get("enabled"))

    # ---------- 阶段三：工具命令面 ----------

    def on_web_search(query: str) -> str:
        return service.web_search(query)

    def on_web_extract(url: str) -> str:
        return service.web_extract(url)

    def on_web_cache_status() -> str:
        return service.web_cache_status()

    def on_web_cache_clear() -> str:
        return service.web_cache_clear()

    def on_code_ast(pattern: str, path: str) -> str:
        return service.code_ast(pattern, path or ".")

    def on_code_quality(path: str) -> str:
        return service.code_quality(path or ".")

    def on_git_analyze(analysis_type: str) -> str:
        return service.git_analyze(analysis_type or "history")

    def on_git_commit_gen() -> str:
        return service.git_commit_gen()

    def on_db_connect(db_type: str, database: str) -> str:
        return service.db_connect(db_type, database)

    def on_db_query(sql: str) -> str:
        return service.db_query(sql)

    def on_db_execute(sql: str) -> str:
        return service.db_execute(sql)

    def on_db_schema(table: str) -> str:
        return service.db_schema(table)

    def on_file_list() -> str:
        files = service.file_list()
        if not files:
            return "_知识库中暂无已登记的文件_"
        lines = ["### 📁 文件列表", ""]
        for fm in files:
            lines.append(f"- `{fm.get('path')}`（{fm.get('size', '?')}）")
        return "\n".join(lines)

    def on_file_stats() -> str:
        stats = service.file_stats()
        if "error" in stats:
            return f"[错误] {stats['error']}"
        return "\n".join(f"- {k}: **{v}**" for k, v in stats.items())

    def on_generate_skills() -> str:
        return service.generate_skills()

    def on_knowledge_summary() -> str:
        return service.knowledge_summary()

    def on_snapshot_list() -> str:
        return service.snapshot_list()

    def on_snapshot_create() -> str:
        return service.snapshot_create()

    def on_snapshot_restore(snapshot_id: str) -> str:
        return service.snapshot_restore(snapshot_id)

    def on_graph_build(text: str) -> str:
        return service.graph_build(text)

    return {
        "on_chat": on_chat,
        "on_chat_stream": on_chat_stream,
        "on_upload": on_upload,
        "on_refresh_stats": on_refresh_stats,
        "on_clear_index": on_clear_index,
        "on_rebuild_index": on_rebuild_index,
        "on_list_sessions": on_list_sessions,
        "on_create_session": on_create_session,
        "on_switch_session": on_switch_session,
        "on_search_sessions": on_search_sessions,
        "on_query_graph": on_query_graph,
        "on_graph_summary": on_graph_summary,
        "on_graph_build": on_graph_build,
        "on_stop": on_stop,
        "on_model_status": on_model_status,
        "on_model_choices": on_model_choices,
        "on_switch_model": on_switch_model,
        "on_toggle_think": on_toggle_think,
        "on_web_search": on_web_search,
        "on_web_extract": on_web_extract,
        "on_web_cache_status": on_web_cache_status,
        "on_web_cache_clear": on_web_cache_clear,
        "on_code_ast": on_code_ast,
        "on_code_quality": on_code_quality,
        "on_git_analyze": on_git_analyze,
        "on_git_commit_gen": on_git_commit_gen,
        "on_db_connect": on_db_connect,
        "on_db_query": on_db_query,
        "on_db_execute": on_db_execute,
        "on_db_schema": on_db_schema,
        "on_file_list": on_file_list,
        "on_file_stats": on_file_stats,
        "on_generate_skills": on_generate_skills,
        "on_knowledge_summary": on_knowledge_summary,
        "on_snapshot_list": on_snapshot_list,
        "on_snapshot_create": on_snapshot_create,
        "on_snapshot_restore": on_snapshot_restore,
    }


# ==================== Gradio 装配（不做单元测试）====================

def build_app(service: Optional[WebService] = None):  # pragma: no cover
    """组装 Gradio Blocks 应用。"""
    import gradio as gr

    service = service or get_web_service()
    handlers = build_handlers(service)

    with gr.Blocks(title="Cerebro 🧠") as app:
        gr.Markdown("# Cerebro 🧠\n本地优先的 RAG + Agent 助手")
        # 顶部状态行：当前模型 / 是否已加载 / num_ctx / 思考模式；切换后即时刷新
        model_status = gr.Markdown(handlers["on_model_status"]())

        with gr.Tab("对话"):
            # 模型热切换：下拉列出本机已安装模型，切换会同步 RAG/Agent 并释放旧模型
            _choices, _current = handlers["on_model_choices"]()
            with gr.Row():
                model_dd = gr.Dropdown(
                    choices=_choices,
                    value=_current or None,
                    label="模型（切换后立即生效，旧模型自动释放）",
                    scale=6,
                    allow_custom_value=True,
                )
                model_switch_btn = gr.Button("切换模型", scale=1)
                model_refresh_btn = gr.Button("刷新列表", scale=1)
                # 思考模式：默认关（响应快）；开启需模型支持，不支持时自动回弹
                think_cb = gr.Checkbox(
                    value=bool(service.current_model().get("think")),
                    label="思考模式（慢，适合复杂推理）",
                    scale=2,
                )
            model_switch_result = gr.Markdown()
            model_switch_btn.click(
                handlers["on_switch_model"], model_dd, [model_switch_result, model_status]
            )
            think_cb.input(
                handlers["on_toggle_think"], think_cb,
                [model_switch_result, model_status, think_cb],
            )

            def _refresh_model_dropdown():
                choices, current = handlers["on_model_choices"]()
                return gr.update(choices=choices, value=current or None)

            model_refresh_btn.click(_refresh_model_dropdown, None, model_dd)

            mode = gr.Radio(
                ["RAG 检索", "单 Agent", "多 Agent 协作"],
                value="RAG 检索",
                label="模式",
            )
            with gr.Row():
                enable_web = gr.Checkbox(
                    value=True,
                    label="联网搜索增强（RAG 模式，等价 CLI /ask 的网络增强）",
                )
                auto_confirm = gr.Checkbox(
                    value=False,
                    label="自动确认危险命令（单 Agent 模式，等价 CLI --yes）",
                )
            answer_box = gr.Markdown(label="回答")
            side_box = gr.Markdown(label="附加信息")
            with gr.Row():
                msg_box = gr.Textbox(placeholder="输入你的问题...", scale=8, label="输入")
                send_btn = gr.Button("发送", scale=1, variant="primary")
                stop_btn = gr.Button("停止", scale=1)
            _chat_inputs = [msg_box, mode, enable_web, auto_confirm]
            # 使用流式处理器：点击后立即反馈"处理中"并实时更新进度
            send_btn.click(
                handlers["on_chat_stream"], _chat_inputs, [answer_box, side_box]
            )
            msg_box.submit(
                handlers["on_chat_stream"], _chat_inputs, [answer_box, side_box]
            )
            stop_btn.click(handlers["on_stop"], None, side_box)

        with gr.Tab("知识库"):
            stats_box = gr.Markdown(format_stats(service.get_stats()))
            upload = gr.File(file_count="multiple", type="filepath", label="上传文档")
            upload_result = gr.Markdown()
            with gr.Row():
                refresh_btn = gr.Button("刷新统计")
                clear_btn = gr.Button("清空索引", variant="stop")
            upload.upload(handlers["on_upload"], upload, [upload_result, stats_box])
            refresh_btn.click(handlers["on_refresh_stats"], None, stats_box)
            clear_btn.click(handlers["on_clear_index"], None, [upload_result, stats_box])
            gr.Markdown("---\n**从目录重建索引**")
            with gr.Row():
                rebuild_path = gr.Textbox(
                    placeholder="数据目录/文件路径...", scale=8, label="重建路径"
                )
                rebuild_btn = gr.Button("重建索引", scale=1)
            rebuild_result = gr.Markdown()
            rebuild_btn.click(
                handlers["on_rebuild_index"], rebuild_path, [rebuild_result, stats_box]
            )

        with gr.Tab("会话"):
            sessions_box = gr.Markdown()
            with gr.Row():
                new_title = gr.Textbox(placeholder="会话标题（可选）", label="新建会话")
                new_btn = gr.Button("新建")
                list_btn = gr.Button("刷新列表")
            new_result = gr.Markdown()
            new_btn.click(
                handlers["on_create_session"], new_title, [new_result, sessions_box]
            )
            list_btn.click(handlers["on_list_sessions"], None, sessions_box)
            gr.Markdown("---")
            with gr.Row():
                switch_id = gr.Textbox(placeholder="会话 ID...", scale=6, label="切换会话")
                switch_btn = gr.Button("切换", scale=1)
            switch_result = gr.Markdown()
            switch_btn.click(
                handlers["on_switch_session"], switch_id, [switch_result, sessions_box]
            )
            with gr.Row():
                search_kw = gr.Textbox(placeholder="搜索关键词...", scale=6, label="搜索会话")
                search_btn = gr.Button("搜索", scale=1)
            search_result = gr.Markdown()
            search_btn.click(handlers["on_search_sessions"], search_kw, search_result)

        with gr.Tab("知识图谱"):
            entity_box = gr.Textbox(placeholder="输入实体名...", label="查询实体")
            with gr.Row():
                graph_btn = gr.Button("查询实体")
                summary_btn = gr.Button("图谱概览")
            graph_result = gr.Markdown()
            graph_btn.click(handlers["on_query_graph"], entity_box, graph_result)
            summary_btn.click(handlers["on_graph_summary"], None, graph_result)
            gr.Markdown("---\n**从文本构建图谱**")
            gb_text = gr.Textbox(lines=3, placeholder="输入用于构建知识图谱的文本...", label="构建文本")
            gb_btn = gr.Button("构建")
            gb_result = gr.Markdown()
            gb_btn.click(handlers["on_graph_build"], gb_text, gb_result)

        with gr.Tab("文件管理"):
            with gr.Row():
                fl_btn = gr.Button("文件列表")
                fs_btn = gr.Button("文件统计")
            file_result = gr.Markdown()
            fl_btn.click(handlers["on_file_list"], None, file_result)
            fs_btn.click(handlers["on_file_stats"], None, file_result)

        with gr.Tab("网络搜索"):
            with gr.Row():
                ws_query = gr.Textbox(placeholder="搜索关键词...", scale=8, label="网络搜索")
                ws_btn = gr.Button("搜索", scale=1, variant="primary")
            ws_result = gr.Markdown()
            ws_btn.click(handlers["on_web_search"], ws_query, ws_result)
            with gr.Row():
                we_url = gr.Textbox(placeholder="https://...", scale=8, label="提取网页正文")
                we_btn = gr.Button("提取", scale=1)
            we_result = gr.Markdown()
            we_btn.click(handlers["on_web_extract"], we_url, we_result)
            with gr.Row():
                wc_status_btn = gr.Button("缓存状态")
                wc_clear_btn = gr.Button("清空缓存", variant="stop")
            wc_result = gr.Markdown()
            wc_status_btn.click(handlers["on_web_cache_status"], None, wc_result)
            wc_clear_btn.click(handlers["on_web_cache_clear"], None, wc_result)

        with gr.Tab("代码分析"):
            with gr.Row():
                ca_pattern = gr.Textbox(placeholder="AST 搜索模式...", scale=6, label="AST 搜索")
                ca_path = gr.Textbox(value=".", scale=2, label="路径")
                ca_btn = gr.Button("搜索", scale=1)
            ca_result = gr.Markdown()
            ca_btn.click(handlers["on_code_ast"], [ca_pattern, ca_path], ca_result)
            with gr.Row():
                cq_path = gr.Textbox(value=".", scale=8, label="代码质量检查路径")
                cq_btn = gr.Button("检查", scale=1)
            cq_result = gr.Markdown()
            cq_btn.click(handlers["on_code_quality"], cq_path, cq_result)

        with gr.Tab("Git"):
            ga_type = gr.Radio(
                ["history", "status", "authors"], value="history", label="分析类型"
            )
            ga_btn = gr.Button("Git 分析")
            ga_result = gr.Markdown()
            ga_btn.click(handlers["on_git_analyze"], ga_type, ga_result)
            gr.Markdown("---")
            gcg_btn = gr.Button("生成提交信息（AI）")
            gcg_result = gr.Markdown()
            gcg_btn.click(handlers["on_git_commit_gen"], None, gcg_result)

        with gr.Tab("数据库"):
            with gr.Row():
                db_type = gr.Textbox(placeholder="sqlite / mysql ...", scale=3, label="类型")
                db_name = gr.Textbox(placeholder="数据库路径/名称", scale=5, label="数据库")
                db_conn_btn = gr.Button("连接", scale=1)
            db_conn_result = gr.Markdown()
            db_conn_btn.click(handlers["on_db_connect"], [db_type, db_name], db_conn_result)
            with gr.Row():
                dq_sql = gr.Textbox(placeholder="SELECT ...", scale=8, label="查询 SQL")
                dq_btn = gr.Button("查询", scale=1)
            dq_result = gr.Markdown()
            dq_btn.click(handlers["on_db_query"], dq_sql, dq_result)
            with gr.Row():
                de_sql = gr.Textbox(placeholder="INSERT/UPDATE/DDL ...", scale=8, label="执行 SQL")
                de_btn = gr.Button("执行", scale=1)
            de_result = gr.Markdown()
            de_btn.click(handlers["on_db_execute"], de_sql, de_result)
            with gr.Row():
                ds_table = gr.Textbox(placeholder="表名（留空列出所有表）", scale=8, label="查看 Schema")
                ds_btn = gr.Button("Schema", scale=1)
            ds_result = gr.Markdown()
            ds_btn.click(handlers["on_db_schema"], ds_table, ds_result)

        with gr.Tab("知识库管理"):
            with gr.Row():
                gs_btn = gr.Button("生成 Skills")
                ks_btn = gr.Button("知识库摘要")
            km_result = gr.Markdown()
            gs_btn.click(handlers["on_generate_skills"], None, km_result)
            ks_btn.click(handlers["on_knowledge_summary"], None, km_result)
            gr.Markdown("---\n**快照管理**")
            with gr.Row():
                sl_btn = gr.Button("快照列表")
                sc_btn = gr.Button("创建快照")
            snap_result = gr.Markdown()
            sl_btn.click(handlers["on_snapshot_list"], None, snap_result)
            sc_btn.click(handlers["on_snapshot_create"], None, snap_result)
            with gr.Row():
                sr_id = gr.Textbox(placeholder="快照 ID...", scale=8, label="恢复快照")
                sr_btn = gr.Button("生成恢复脚本", scale=1)
            sr_result = gr.Markdown()
            sr_btn.click(handlers["on_snapshot_restore"], sr_id, sr_result)

    return app


def serve_blocking(app, wait: Optional[Callable[[], None]] = None) -> None:
    """阻塞等待直到收到中断信号，并在退出时优雅关闭 app 以释放端口。

    该函数不直接调用 gradio，便于单元测试：
    - ``app.close()`` 用于关闭 Gradio 服务器、释放监听端口。
    - ``wait`` 为可注入的阻塞等待函数（默认无限等待事件），收到
      ``KeyboardInterrupt`` 时正常返回，进入 finally 关闭。

    这样无论前台运行还是从 launcher 启动，Ctrl+C / 进程退出都能确定地释放端口，
    Gradio 服务器随进程一并退出，不会残留孤儿进程占用端口。
    """
    if wait is None:  # pragma: no cover - 默认分支依赖真实阻塞，测试时注入 wait
        import threading

        def wait():
            threading.Event().wait()

    try:
        wait()
    except KeyboardInterrupt:
        pass
    finally:
        close = getattr(app, "close", None)
        if callable(close):
            try:
                close()
            except Exception:
                pass


def launch(
    server_name: str = "127.0.0.1",
    server_port: int = 7860,
    share: bool = False,
    **kwargs,
):  # pragma: no cover
    """启动 Web 界面。默认仅绑定本地回环地址，符合隐私优先原则。

    使用 ``prevent_thread_lock=True`` 让 ``launch()`` 立即返回，改由
    ``serve_blocking`` 统一负责阻塞与优雅关闭，从而保证 Ctrl+C 时能干净地
    释放端口、Gradio 服务器随进程一并退出。
    """
    import gradio as gr

    app = build_app()
    app.launch(
        server_name=server_name,
        server_port=server_port,
        share=share,
        theme=gr.themes.Soft(),
        prevent_thread_lock=True,
        **kwargs,
    )
    serve_blocking(app)


def main():  # pragma: no cover
    launch()


if __name__ == "__main__":  # pragma: no cover
    main()
