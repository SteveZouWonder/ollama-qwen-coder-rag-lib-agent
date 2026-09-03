"""Web 服务层：核心引擎的编排与流式桥接。

本模块是 Web 界面唯一与核心引擎（RAGEngine / ReActEngine / AgentOrchestrator /
SessionManager / GraphQuery）交互的地方。UI 层（``app.py``）只调用本模块暴露的
方法，不直接 import 引擎，从而：

1. 让业务编排逻辑可独立于 Gradio 做单元测试（本模块不 import gradio）。
2. 把引擎的"回调式"进度（``progress_callback`` / ``on_step``）桥接为 Gradio
   友好的"可迭代式"流式事件。

为便于测试，所有重量级引擎均通过可注入的工厂函数惰性创建（依赖注入）。
"""
from __future__ import annotations

import queue
import threading
from typing import Any, Callable, Dict, Iterator, List, Optional


# ==================== 引擎工厂（可在测试中替换/注入）====================

def _default_rag_factory():
    """创建并返回一个已加载索引的 RAGEngine。"""
    from rag_engine import RAGEngine

    engine = RAGEngine()
    try:
        engine.load_index()
    except Exception:
        # 尚无持久化索引时 load_index 可能失败，忽略，后续入库会自动构建。
        pass
    return engine


def _default_react_factory(on_step=None, on_confirm=None):
    """创建一个 ReActEngine（模型取自 config.LLM_MODEL，热切换后自动跟随）。"""
    from react_engine import ReActEngine

    return ReActEngine(on_step=on_step, on_confirm=on_confirm)


def _default_model_switcher():
    """返回 model_switcher 模块（便于测试注入替身）。"""
    import model_switcher

    return model_switcher


def _default_orchestrator_factory():
    """创建一个使用默认配置的 AgentOrchestrator。"""
    from agent_config import AgentConfigManager
    from agent_orchestrator import AgentOrchestrator

    return AgentOrchestrator(AgentConfigManager.get_default_config())


def _default_set_rag_engine(engine) -> None:
    """把 RAGEngine 注入 agent_tools 全局注册表。"""
    import agent_tools

    agent_tools.set_rag_engine(engine)


def _default_session_manager_factory():
    from session_manager import get_session_manager

    return get_session_manager()


def _default_graph_query_factory():
    from knowledge_graph.graph_query import get_graph_query

    return get_graph_query()


def _default_load_documents(path: str, file_types=None):
    from document_loader import load_documents

    return load_documents(path, file_types)


def _default_collaboration_mode(name: str):
    """把模式名字符串解析为 CollaborationMode 枚举，非法值返回 None。"""
    from agents.agent_types import CollaborationMode

    if not name:
        return None
    try:
        return CollaborationMode(name)
    except ValueError:
        return None


# ==================== 流式事件 ====================

_DONE = object()  # 内部结束哨兵


class StreamEvent:
    """服务层向 UI 层输出的统一流式事件。

    - ``kind``：``progress`` | ``answer`` | ``step`` | ``error`` | ``done``
    - ``message``：人类可读文本
    - ``data``：附加结构化数据（如 sources 列表、step_log 等）
    """

    __slots__ = ("kind", "message", "data")

    def __init__(self, kind: str, message: str = "", data: Any = None):
        self.kind = kind
        self.message = message
        self.data = data

    def __eq__(self, other):  # 便于测试断言
        return (
            isinstance(other, StreamEvent)
            and self.kind == other.kind
            and self.message == other.message
            and self.data == other.data
        )

    def __repr__(self):  # pragma: no cover - 仅调试用
        return f"StreamEvent(kind={self.kind!r}, message={self.message!r})"


# ==================== 服务层 ====================

class WebService:
    """Web 界面服务层。

    通过依赖注入接收各引擎的工厂函数，便于在不启动真实 Ollama/ChromaDB 的情况下
    进行单元测试。
    """

    def __init__(
        self,
        rag_factory: Callable = _default_rag_factory,
        react_factory: Callable = _default_react_factory,
        orchestrator_factory: Callable = _default_orchestrator_factory,
        session_manager_factory: Callable = _default_session_manager_factory,
        graph_query_factory: Callable = _default_graph_query_factory,
        set_rag_engine: Callable = _default_set_rag_engine,
        load_documents: Callable = _default_load_documents,
        resolve_mode: Callable = _default_collaboration_mode,
        model_switcher_factory: Callable = _default_model_switcher,
    ):
        self._rag_factory = rag_factory
        self._react_factory = react_factory
        self._orchestrator_factory = orchestrator_factory
        self._session_manager_factory = session_manager_factory
        self._graph_query_factory = graph_query_factory
        self._set_rag_engine = set_rag_engine
        self._load_documents = load_documents
        self._resolve_mode = resolve_mode
        self._model_switcher_factory = model_switcher_factory

        self._rag_engine = None
        self._session_manager = None
        self._graph_query = None
        self._active_react: Optional[Any] = None

    # ---------- 惰性单例 ----------

    @property
    def rag_engine(self):
        """惰性创建 RAGEngine，并注入 agent_tools 供 Agent 使用知识库。"""
        if self._rag_engine is None:
            self._rag_engine = self._rag_factory()
            self._set_rag_engine(self._rag_engine)
        return self._rag_engine

    @property
    def session_manager(self):
        if self._session_manager is None:
            self._session_manager = self._session_manager_factory()
        return self._session_manager

    @property
    def graph_query(self):
        if self._graph_query is None:
            self._graph_query = self._graph_query_factory()
        return self._graph_query

    # ---------- 模型管理（热切换）----------

    def list_models(self) -> List[str]:
        """本机 Ollama 已安装模型名列表（失败返回空列表）。"""
        try:
            return list(self._model_switcher_factory().list_installed_models())
        except BaseException:  # noqa: BLE001
            return []

    def current_model(self) -> Dict[str, Any]:
        """当前模型概况：``model`` / ``num_ctx`` / ``think`` / ``loaded`` / ``size_bytes``。"""
        try:
            return dict(self._model_switcher_factory().current_model_info())
        except BaseException as exc:  # noqa: BLE001
            return {"model": "?", "num_ctx": 0, "think": False, "loaded": False,
                    "size_bytes": 0, "loaded_models": [], "error": str(exc)}

    def switch_model(self, model: str) -> Dict[str, Any]:
        """热切换全局 LLM。

        同步 RAG 引擎（若已创建；未创建则下次惰性创建时自然读取新 config），
        更新全局 config（Web 端 ReActEngine / 多 Agent 每次对话新建，会自动跟随），
        并立即释放旧模型避免双驻留。返回 ``{ok, model, previous, num_ctx, message}``。
        """
        try:
            switcher = self._model_switcher_factory()
            result = switcher.switch_model(
                model,
                rag_engine=self._rag_engine,  # 仅同步已创建的实例，不触发惰性加载
                react_engine=None,
            )
            return {
                "ok": result.ok,
                "model": result.model,
                "previous": result.previous,
                "num_ctx": result.num_ctx,
                "unloaded_previous": result.unloaded_previous,
                "message": result.message,
            }
        except BaseException as exc:  # noqa: BLE001
            return {"ok": False, "model": "", "previous": "", "num_ctx": 0,
                    "unloaded_previous": False, "message": f"切换失败: {exc}"}

    def set_think(self, enabled: bool) -> Dict[str, Any]:
        """运行时开关思考模式。

        同步已创建的 RAG 引擎（重建 LLM）并更新全局 config（Web 端 ReActEngine
        每次对话新建，会自动跟随）。开启前校验当前模型是否支持 thinking。
        返回 ``{ok, enabled, changed, message}``。
        """
        try:
            result = self._model_switcher_factory().switch_think(
                bool(enabled), rag_engine=self._rag_engine, react_engine=None,
            )
            return {
                "ok": result.ok,
                "enabled": result.enabled,
                "changed": result.changed,
                "message": result.message,
            }
        except BaseException as exc:  # noqa: BLE001
            return {"ok": False, "enabled": False, "changed": False,
                    "message": f"设置失败: {exc}"}

    # ---------- RAG 检索 ----------

    def rag_query_stream(
        self, question: str, enable_web_search: bool = True
    ) -> Iterator[StreamEvent]:
        """流式 RAG 检索，与 CLI 的 ``/ask`` 行为一致。

        改动说明：此前仅裸调 ``query_with_sources``，缺少 CLI 独有的高级编排，
        导致同一问题两端答案质量差异极大。现改为调用共享层
        ``rag_pipeline.answer_question``，从而获得：元/概览问题直答、LLM 驱动
        的网络搜索规划、多查询合并、页面正文增强、知识库/网络双区综合、0 命中
        网络回退。编排级进度与 RAG 检索进度统一桥接为 ``StreamEvent``；对话完成
        后自动写入当前会话（record_conversation），与 CLI 持久化行为对齐。
        """
        question = (question or "").strip()
        if not question:
            yield StreamEvent("error", "问题不能为空")
            return

        import rag_pipeline

        q: "queue.Queue" = queue.Queue()
        result_holder: Dict[str, Any] = {}
        error_holder: Dict[str, BaseException] = {}

        def progress_cb(evt: Dict[str, Any]):
            # 元/概览事件带结构化数据（files/stats），透传给 UI 展示。
            q.put(StreamEvent("progress", evt.get("message", ""), evt))

        def worker():
            try:
                result_holder["result"] = rag_pipeline.answer_question(
                    self.rag_engine,
                    question,
                    enable_web_search=enable_web_search,
                    show_progress=True,
                    progress=progress_cb,
                    rag_progress_callback=progress_cb,
                )
            except BaseException as exc:  # noqa: BLE001
                error_holder["error"] = exc
            finally:
                q.put(_DONE)

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()

        while True:
            item = q.get()
            if item is _DONE:
                break
            yield item

        if "error" in error_holder:
            yield StreamEvent("error", f"检索失败: {error_holder['error']}")
            return

        result = result_holder.get("result", {}) or {}
        answer = result.get("answer", "")

        # 对话落库（与 CLI 一致）：即使是元查询也记录，便于历史回看。
        try:
            recorded = "[知识库概览]" if result.get("kind") == "meta" else answer
            rag_pipeline.record_conversation(question, recorded)
        except Exception:  # noqa: BLE001 - 落库失败不影响返回
            pass

        yield StreamEvent(
            "answer",
            answer,
            {
                "kind": result.get("kind", "answer"),
                "sources": result.get("kb_sources", []),
                "web_sources": result.get("web_sources", []),
                "meta": result.get("meta"),
            },
        )

    def rag_query(self, question: str, enable_web_search: bool = True) -> Dict[str, Any]:
        """非流式 RAG 检索，返回 ``{answer, sources, web_sources, kind, meta}``。"""
        events = list(self.rag_query_stream(question, enable_web_search=enable_web_search))
        for evt in events:
            if evt.kind == "error":
                return {
                    "answer": f"[错误] {evt.message}",
                    "sources": [], "web_sources": [], "kind": "error", "meta": None,
                }
        for evt in reversed(events):
            if evt.kind == "answer":
                data = evt.data or {}
                return {
                    "answer": evt.message,
                    "sources": data.get("sources", []),
                    "web_sources": data.get("web_sources", []),
                    "kind": data.get("kind", "answer"),
                    "meta": data.get("meta"),
                }
        return {"answer": "", "sources": [], "web_sources": [], "kind": "answer", "meta": None}

    # ---------- 单 Agent（ReAct）----------

    def agent_chat_stream(
        self, user_input: str, confirm_handler: Optional[Callable] = None
    ) -> Iterator[StreamEvent]:
        """流式单 Agent 对话，把 ``on_step`` 桥接为 ``step`` 事件流。"""
        user_input = (user_input or "").strip()
        if not user_input:
            yield StreamEvent("error", "输入不能为空")
            return

        # 确保知识库工具就绪
        _ = self.rag_engine

        q: "queue.Queue" = queue.Queue()
        result_holder: Dict[str, Any] = {}
        error_holder: Dict[str, BaseException] = {}

        def on_step(evt: Dict[str, Any]):
            q.put(StreamEvent("step", evt.get("message", ""), evt))

        def on_confirm(evt: Dict[str, Any]) -> bool:
            if confirm_handler is None:
                # 无确认处理器时，默认拒绝危险操作，保证安全。
                return False
            return bool(confirm_handler(evt))

        engine = self._react_factory(on_step=on_step, on_confirm=on_confirm)
        self._active_react = engine

        def worker():
            try:
                result_holder["answer"] = engine.chat(user_input)
            except BaseException as exc:  # noqa: BLE001
                error_holder["error"] = exc
            finally:
                q.put(_DONE)

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()

        while True:
            item = q.get()
            if item is _DONE:
                break
            yield item

        if "error" in error_holder:
            yield StreamEvent("error", f"Agent 执行失败: {error_holder['error']}")
        else:
            answer = result_holder.get("answer", "")
            # 对话落库（与 CLI handle_agent 一致）
            try:
                import rag_pipeline
                rag_pipeline.record_conversation(user_input, answer)
            except Exception:  # noqa: BLE001
                pass
            yield StreamEvent(
                "answer",
                answer,
                {"step_log": getattr(engine, "step_log", [])},
            )
        self._active_react = None

    def stop_agent(self) -> bool:
        """中断当前正在运行的 Agent，返回是否成功发出中断信号。"""
        if self._active_react is not None:
            self._active_react.stop()
            return True
        return False

    # ---------- 多 Agent 协作 ----------

    def multi_agent_run(self, request: str, mode: Optional[str] = None) -> Dict[str, Any]:
        """执行多 Agent 协作，返回整合结果 dict。"""
        request = (request or "").strip()
        if not request:
            return {"success": False, "error": "请求不能为空", "summary": "请求为空"}

        # 确保知识库引擎已注入全局注册表：RAGAgent 承接通用任务时会复用
        # rag_pipeline.answer_question，需要全局 rag_engine 才能真正检索。
        try:
            _ = self.rag_engine
        except Exception:  # noqa: BLE001 - 引擎不可用时仍允许多 Agent 尝试运行
            pass

        resolved = self._resolve_mode(mode)
        orchestrator = self._orchestrator_factory()
        try:
            return orchestrator.process_request(request, resolved)
        except BaseException as exc:  # noqa: BLE001
            return {"success": False, "error": str(exc), "summary": "协作执行失败"}
        finally:
            shutdown = getattr(orchestrator, "shutdown", None)
            if callable(shutdown):
                try:
                    shutdown()
                except Exception:
                    pass

    # ---------- 知识库管理 ----------

    def add_documents(self, file_paths: List[str]) -> str:
        """把上传的文件加入知识库，返回人类可读的结果摘要。"""
        if not file_paths:
            return "[提示] 未选择任何文件"

        loaded = 0
        added_files: List[str] = []
        errors: List[str] = []
        all_docs: List[Any] = []
        valid_paths: List[str] = []
        for path in file_paths:
            try:
                docs = self._load_documents(path)
                if not docs:
                    errors.append(f"无法加载: {path}")
                    continue
                all_docs.extend(docs)
                valid_paths.append(path)
                loaded += len(docs)
                added_files.append(path)
            except BaseException as exc:  # noqa: BLE001
                errors.append(f"{path}: {exc}")

        if all_docs:
            try:
                self.rag_engine.add_documents(all_docs, valid_paths)
            except BaseException as exc:  # noqa: BLE001
                return f"[错误] 入库失败: {exc}"

        lines = [f"[成功] 已入库 {len(added_files)} 个文件，共 {loaded} 个片段"]
        if errors:
            lines.append("[部分失败]")
            lines.extend(f"  - {e}" for e in errors)
        return "\n".join(lines)

    def get_stats(self) -> Dict[str, Any]:
        """返回知识库统计信息（含 ``total_documents`` 键）。"""
        try:
            return self.rag_engine.get_stats()
        except BaseException as exc:  # noqa: BLE001
            return {"error": str(exc)}

    def rebuild_index(self, data_path: Optional[str] = None) -> str:
        """重建知识库索引。"""
        try:
            docs = self._load_documents(data_path) if data_path else None
            if data_path:
                if not docs:
                    return f"[错误] 目录中无可加载文档: {data_path}"
                self.rag_engine.build_index(docs, file_paths=[data_path])
                return f"[成功] 已重建索引，共 {len(docs)} 个片段"
            return "[提示] 未指定数据路径"
        except BaseException as exc:  # noqa: BLE001
            return f"[错误] 重建失败: {exc}"

    def clear_index(self) -> str:
        """清空知识库索引。"""
        try:
            self.rag_engine.clear_index()
            return "[成功] 索引已清空"
        except BaseException as exc:  # noqa: BLE001
            return f"[错误] 清空失败: {exc}"

    # ---------- 会话管理 ----------

    def list_sessions(self) -> List[Dict[str, Any]]:
        """返回会话摘要列表。"""
        sessions = self.session_manager.list_sessions()
        current = self.session_manager.get_current_session()
        current_id = current.session_id if current else None
        result = []
        for s in sessions:
            result.append(
                {
                    "session_id": s.session_id,
                    "title": s.title,
                    "messages": len(getattr(s, "messages", [])),
                    "is_current": s.session_id == current_id,
                }
            )
        return result

    def create_session(self, title: Optional[str] = None) -> str:
        """新建会话并切换过去，返回其 id。"""
        session = self.session_manager.create_session(title=title or None)
        return session.session_id

    def switch_session(self, session_id: str) -> bool:
        if not session_id:
            return False
        return bool(self.session_manager.switch_session(session_id))

    def search_sessions(self, query: str) -> List[Dict[str, Any]]:
        query = (query or "").strip()
        if not query:
            return []
        sessions = self.session_manager.search_sessions(query)
        return [{"session_id": s.session_id, "title": s.title} for s in sessions]

    # ---------- 知识图谱 ----------

    def query_graph_entity(self, entity_text: str) -> Dict[str, Any]:
        """查询实体，返回结构化字典。"""
        entity_text = (entity_text or "").strip()
        if not entity_text:
            return {"entities": [], "relations": [], "explanation": "实体名不能为空"}
        try:
            result = self.graph_query.query_entity(entity_text)
            return result.to_dict()
        except BaseException as exc:  # noqa: BLE001
            return {"entities": [], "relations": [], "explanation": f"查询失败: {exc}"}

    def graph_summary(self) -> Dict[str, Any]:
        """返回知识图谱概览。"""
        try:
            return self.graph_query.get_graph_summary()
        except BaseException as exc:  # noqa: BLE001
            return {"is_available": False, "error": str(exc)}

    # ---------- 工具命令（对齐 CLI 的 registry 工具命令面）----------

    def run_tool(self, tool_name: str, args: Optional[Dict[str, Any]] = None,
                 auto_confirm: bool = False) -> str:
        """通用工具执行入口，桥接 agent_tools 全局注册表。

        CLI 的 /web-search、/code-*、/git-*、/db-* 等命令底层都调用
        ``registry.execute(tool, args)``；Web 侧此前无直接入口，只能靠 Agent
        间接触发。此方法把这些工具直接暴露给 Web，与 CLI 命令面对齐。
        """
        try:
            import agent_tools
            # 确保知识库工具就绪（部分工具依赖 rag_engine）
            _ = self.rag_engine
            return agent_tools.registry.execute(
                tool_name, args or {}, auto_confirm=auto_confirm
            )
        except BaseException as exc:  # noqa: BLE001
            return f"[错误] 工具 {tool_name} 执行失败: {exc}"

    # -- 网络搜索 --
    def web_search(self, query: str) -> str:
        query = (query or "").strip()
        if not query:
            return "[提示] 请输入搜索查询"
        return self.run_tool("web_search", {"query": query})

    def web_extract(self, url: str) -> str:
        url = (url or "").strip()
        if not url:
            return "[提示] 请输入 URL"
        return self.run_tool("web_content_extract", {"url": url})

    def web_cache_status(self) -> str:
        return self.run_tool("web_cache_status", {})

    def web_cache_clear(self) -> str:
        return self.run_tool("web_cache_clear", {}, auto_confirm=True)

    # -- 代码分析 --
    def code_ast(self, pattern: str, path: str = ".") -> str:
        pattern = (pattern or "").strip()
        if not pattern:
            return "[提示] 请输入搜索模式"
        return self.run_tool("ast_search", {"pattern": pattern, "path": path or "."})

    def code_quality(self, path: str = ".") -> str:
        return self.run_tool("code_quality_check", {"path": (path or ".").strip() or "."})

    # -- Git --
    def git_analyze(self, analysis_type: str = "history", repo_path: str = ".") -> str:
        allowed = {"history", "status", "authors"}
        analysis_type = (analysis_type or "history").strip().lower()
        if analysis_type not in allowed:
            return f"[错误] 未知分析类型 '{analysis_type}'，支持: history / status / authors"
        return self.run_tool(
            "git_analyze", {"repo_path": repo_path or ".", "analysis_type": analysis_type}
        )

    def git_commit_gen(self, repo_path: str = ".") -> str:
        return self.run_tool("git_commit_gen", {"repo_path": repo_path or ".", "use_ai": True})

    # -- 数据库 --
    def db_connect(self, db_type: str, database: str) -> str:
        db_type = (db_type or "").strip()
        database = (database or "").strip()
        if not db_type or not database:
            return "[提示] 请提供数据库类型和路径"
        return self.run_tool("database_connect", {"db_type": db_type, "database": database})

    def db_query(self, sql: str) -> str:
        sql = (sql or "").strip()
        if not sql:
            return "[提示] 请输入 SQL 查询语句"
        return self.run_tool("database_query", {"sql": sql})

    def db_execute(self, sql: str) -> str:
        sql = (sql or "").strip()
        if not sql:
            return "[提示] 请输入 SQL 语句"
        return self.run_tool("database_execute", {"sql": sql})

    def db_schema(self, table: str = "") -> str:
        return self.run_tool("database_get_schema", {"table": (table or "").strip()})

    # -- 知识图谱构建 --
    def graph_build(self, text: str, doc_id: str = "manual", doc_type: str = "text") -> str:
        text = (text or "").strip()
        if not text:
            return "[提示] 请输入用于构建知识图谱的文本"
        return self.run_tool(
            "knowledge_graph_build",
            {"text": text, "doc_id": doc_id or "manual", "doc_type": doc_type or "text"},
        )

    def graph_query_typed(self, query: str, query_type: str = "entity") -> Dict[str, Any]:
        """带类型的图谱查询（entity/type/neighbors/path/similar）。"""
        query = (query or "").strip()
        if not query:
            return {"entities": [], "relations": [], "explanation": "查询内容不能为空"}
        result = self.run_tool(
            "knowledge_graph_query", {"query": query, "query_type": query_type or "entity"}
        )
        return {"text": result}

    # ---------- 文件管理 ----------

    def file_list(self) -> List[Dict[str, Any]]:
        """列出知识库已登记的文件（等价 /file-list）。"""
        try:
            from file_metadata import get_global_metadata_manager
            manager = get_global_metadata_manager()
            files = manager.list_files()
            out = []
            for fm in files:
                try:
                    size = manager._format_size(fm.file_size)
                except Exception:  # noqa: BLE001
                    size = "?"
                out.append({"path": fm.file_path, "size": size})
            return out
        except BaseException as exc:  # noqa: BLE001
            return [{"path": f"[错误] {exc}", "size": ""}]

    def file_stats(self) -> Dict[str, Any]:
        """文件统计概览（等价 /file-stats）。"""
        try:
            from file_metadata import get_global_metadata_manager
            manager = get_global_metadata_manager()
            get_stats = getattr(manager, "get_statistics", None) or getattr(manager, "get_stats", None)
            if callable(get_stats):
                return get_stats()
            files = manager.list_files()
            return {"total_files": len(files)}
        except BaseException as exc:  # noqa: BLE001
            return {"error": str(exc)}

    # ---------- 知识库管理 ----------

    def generate_skills(self) -> str:
        """从知识库生成 Skills（等价 /generate-skills）。"""
        try:
            from knowledge_to_skills import KnowledgeToSkillsEngine
            engine = KnowledgeToSkillsEngine()
            results = engine.convert()
            lines = [f"[成功] 生成 {len(results)} 个 Skills:"]
            for key, path in results.items():
                lines.append(f"  • {key}: {path}")
            return "\n".join(lines)
        except BaseException as exc:  # noqa: BLE001
            return f"[错误] 生成 Skills 失败: {exc}"

    def knowledge_summary(self) -> str:
        """知识库文档摘要（等价 /knowledge-summary）。"""
        try:
            from knowledge_to_skills import KnowledgeToSkillsEngine
            engine = KnowledgeToSkillsEngine()
            summary = engine.get_document_summary()
            lines = ["知识库文档摘要:"]
            for doc in summary:
                kind = "通用" if doc.get("is_generic") else "项目"
                lines.append(
                    f"- {doc.get('file_name')}（{kind}, "
                    f"置信度 {doc.get('confidence', 0):.2f}, "
                    f"chunks {doc.get('chunk_count', 0)}）"
                )
            return "\n".join(lines) if summary else "知识库暂无文档"
        except BaseException as exc:  # noqa: BLE001
            return f"[错误] 获取知识库摘要失败: {exc}"

    def snapshot_list(self) -> str:
        """列出知识库快照（等价 /snapshot-list）。"""
        try:
            from knowledge_snapshot import KnowledgeSnapshotManager
            manager = KnowledgeSnapshotManager()
            snapshots = manager.list_snapshots()
            if not snapshots:
                return "暂无快照"
            lines = [f"共 {len(snapshots)} 个快照:"]
            for snap in snapshots:
                lines.append(
                    f"- `{snap['snapshot_id']}` {snap['timestamp']} "
                    f"（文档 {snap['document_count']}, chunks {snap['total_chunks']}, "
                    f"触发 {snap['trigger']}）"
                )
            return "\n".join(lines)
        except BaseException as exc:  # noqa: BLE001
            return f"[错误] 获取快照列表失败: {exc}"

    def snapshot_create(self) -> str:
        """创建知识库快照（等价 /snapshot-create）。"""
        try:
            from knowledge_snapshot import KnowledgeSnapshotManager
            manager = KnowledgeSnapshotManager()
            snapshot = manager.create_snapshot(trigger="manual")
            return (
                f"[成功] 快照已创建: {snapshot.snapshot_id}\n"
                f"时间: {snapshot.timestamp}，文档数: {len(snapshot.documents)}"
            )
        except BaseException as exc:  # noqa: BLE001
            return f"[错误] 创建快照失败: {exc}"

    def snapshot_restore(self, snapshot_id: str) -> str:
        """为指定快照生成恢复脚本（等价 /snapshot-restore）。"""
        snapshot_id = (snapshot_id or "").strip()
        if not snapshot_id:
            return "[提示] 请指定快照 ID"
        try:
            from knowledge_snapshot import KnowledgeSnapshotManager, RestoreHelper
            manager = KnowledgeSnapshotManager()
            snapshot = manager.load_snapshot(snapshot_id)
            if not snapshot:
                return f"[错误] 快照不存在: {snapshot_id}"
            helper = RestoreHelper(manager)
            script_file = helper.generate_restore_script(snapshot_id)
            return (
                f"[成功] 恢复脚本已生成: {script_file}\n"
                f"（文档数 {len(snapshot.documents)}）请运行该脚本恢复知识库。"
            )
        except BaseException as exc:  # noqa: BLE001
            return f"[错误] 恢复快照失败: {exc}"

    # ---------- 会话高级 ----------

    def session_info(self, session_id: str = "") -> Dict[str, Any]:
        """获取会话详情（等价 /session-info）。空 ID 表示当前会话。"""
        try:
            session_id = (session_id or "").strip()
            if session_id:
                session = self.session_manager.get_session(session_id) \
                    if hasattr(self.session_manager, "get_session") else None
                if session is None and hasattr(self.session_manager, "load_session"):
                    session = self.session_manager.load_session(session_id)
            else:
                session = self.session_manager.get_current_session()
            if session is None:
                return {"error": "未找到会话"}
            return {
                "session_id": session.session_id,
                "title": session.title,
                "messages": len(getattr(session, "messages", [])),
            }
        except BaseException as exc:  # noqa: BLE001
            return {"error": str(exc)}

    def delete_session(self, session_id: str) -> str:
        """删除指定会话（等价 /session-delete）。"""
        session_id = (session_id or "").strip()
        if not session_id:
            return "[提示] 请指定会话 ID"
        try:
            deleter = getattr(self.session_manager, "delete_session", None)
            if not callable(deleter):
                return "[错误] 当前会话管理器不支持删除"
            ok = deleter(session_id)
            return f"[成功] 已删除会话 {session_id[:8]}" if ok else f"[错误] 删除失败: {session_id[:8]}"
        except BaseException as exc:  # noqa: BLE001
            return f"[错误] 删除会话失败: {exc}"


# ==================== 模块级单例 ====================

_web_service_singleton: Optional[WebService] = None


def get_web_service(**kwargs) -> WebService:
    """获取进程内共享的 WebService 单例。

    仅在首次创建时使用传入的工厂参数；后续调用忽略参数返回既有实例。
    """
    global _web_service_singleton
    if _web_service_singleton is None:
        _web_service_singleton = WebService(**kwargs)
    return _web_service_singleton


def reset_web_service() -> None:
    """重置单例（主要供测试使用）。"""
    global _web_service_singleton
    _web_service_singleton = None
