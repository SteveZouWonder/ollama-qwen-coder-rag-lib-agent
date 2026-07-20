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


def format_stats(stats: Dict[str, Any]) -> str:
    """把知识库统计渲染为 Markdown 文本。"""
    if "error" in stats:
        return f"[错误] 获取统计失败: {stats['error']}"
    return (
        f"- 文档片段总数: **{stats.get('total_documents', 0)}**\n"
        f"- LLM 模型: `{stats.get('llm_model', '?')}`\n"
        f"- Embedding 模型: `{stats.get('embed_model', '?')}`\n"
        f"- 分块大小: {stats.get('chunk_size', '?')}\n"
        f"- 分块重叠: {stats.get('chunk_overlap', '?')}\n"
        f"- 检索数量 TOP_K: {stats.get('top_k', '?')}"
    )


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

    def on_chat(message: str, mode: str) -> Tuple[str, str]:
        """统一对话入口，按模式分发。返回 (回答, 附加信息 Markdown)。"""
        message = (message or "").strip()
        if not message:
            return "", "_请输入内容_"

        if mode == "多 Agent 协作":
            result = service.multi_agent_run(message)
            return "", format_multi_agent_result(result)

        if mode == "单 Agent":
            answer = ""
            steps: List[str] = []
            for evt in service.agent_chat_stream(message):
                if evt.kind == "step":
                    steps.append(f"- {evt.message}")
                elif evt.kind == "answer":
                    answer = evt.message
                elif evt.kind == "error":
                    return "", f"[错误] {evt.message}"
            side = "### 执行过程\n" + "\n".join(steps) if steps else ""
            return answer, side

        # 默认 RAG 模式
        result = service.rag_query(message)
        return result["answer"], format_sources(result["sources"])

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

    def on_query_graph(entity: str) -> str:
        return format_graph_result(service.query_graph_entity(entity))

    def on_stop() -> str:
        return "已发送停止信号" if service.stop_agent() else "当前没有运行中的任务"

    return {
        "on_chat": on_chat,
        "on_upload": on_upload,
        "on_refresh_stats": on_refresh_stats,
        "on_clear_index": on_clear_index,
        "on_list_sessions": on_list_sessions,
        "on_create_session": on_create_session,
        "on_query_graph": on_query_graph,
        "on_stop": on_stop,
    }


# ==================== Gradio 装配（不做单元测试）====================

def build_app(service: Optional[WebService] = None):  # pragma: no cover
    """组装 Gradio Blocks 应用。"""
    import gradio as gr

    service = service or get_web_service()
    handlers = build_handlers(service)

    with gr.Blocks(title="Cerebro 🧠") as app:
        gr.Markdown("# Cerebro 🧠\n本地优先的 RAG + Agent 助手")

        with gr.Tab("对话"):
            mode = gr.Radio(
                ["RAG 检索", "单 Agent", "多 Agent 协作"],
                value="RAG 检索",
                label="模式",
            )
            answer_box = gr.Markdown(label="回答")
            side_box = gr.Markdown(label="附加信息")
            with gr.Row():
                msg_box = gr.Textbox(placeholder="输入你的问题...", scale=8, label="输入")
                send_btn = gr.Button("发送", scale=1, variant="primary")
                stop_btn = gr.Button("停止", scale=1)
            send_btn.click(
                handlers["on_chat"], [msg_box, mode], [answer_box, side_box]
            )
            msg_box.submit(
                handlers["on_chat"], [msg_box, mode], [answer_box, side_box]
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

        with gr.Tab("知识图谱"):
            entity_box = gr.Textbox(placeholder="输入实体名...", label="查询实体")
            graph_btn = gr.Button("查询")
            graph_result = gr.Markdown()
            graph_btn.click(handlers["on_query_graph"], entity_box, graph_result)

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
