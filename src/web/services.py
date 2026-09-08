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

import logging
import queue
import threading
import time
from typing import Any, Callable, Dict, Iterator, List, Optional, Tuple

logger = logging.getLogger(__name__)


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


def _default_react_factory(on_step=None, on_confirm=None, context=None,
                           allowed_tools=None, system_prompt_extra: str = "",
                           max_iterations=None):
    """创建一个 ReActEngine（模型取自 config.LLM_MODEL，热切换后自动跟随）。

    ``context`` 为本次对话绑定的会话上下文（每个浏览器标签页有自己的会话）。
    ``allowed_tools`` / ``system_prompt_extra`` / ``max_iterations`` 透传给引擎，
    供工具页「代码助手」等受限场景收窄工具集、附加角色提示、限制步数（F9 P2-1）。
    """
    from react_engine import ReActEngine

    kwargs: Dict[str, Any] = {}
    if allowed_tools is not None:
        kwargs["allowed_tools"] = set(allowed_tools)
    if system_prompt_extra:
        kwargs["system_prompt_extra"] = system_prompt_extra
    if max_iterations:
        kwargs["max_iterations"] = int(max_iterations)
    return ReActEngine(on_step=on_step, on_confirm=on_confirm, context=context, **kwargs)


class ScratchContext:
    """一次性会话上下文：不读历史、不写回会话（工具页「代码助手」用）。

    只实现 ``ReActEngine`` 依赖的三个方法，避免把工具性调用混入用户的对话会话。
    """

    def build_messages(self, system_prompt: Optional[str] = None) -> List[Dict[str, str]]:
        return [{"role": "system", "content": system_prompt}] if system_prompt else []

    def record(self, *args, **kwargs) -> None:  # noqa: D401 - 有意为空
        return None

    def clear(self) -> bool:
        return True


def _default_complete_text(prompt: str, **kwargs) -> str:
    """一次性短补全（``think=False``），用于「用 AI 解读」等工具性调用。"""
    from collaboration.llm_helper import complete_text

    return complete_text(prompt, **kwargs)


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
    """返回进程内共享的 SessionManager。

    经由会话上下文单例获取：首次创建时会把旧的 ``~/.code_agent_history.json``
    一次性迁入默认会话（与 CLI 启动行为一致）。
    """
    from conversation_context import get_conversation_context

    return get_conversation_context().manager


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

    - ``kind``：``progress`` | ``answer`` | ``step`` | ``error`` | ``done`` |
      ``heartbeat`` | ``cancelled``
    - ``message``：人类可读文本
    - ``data``：附加结构化数据（如 sources 列表、step_log 等）

    ``heartbeat`` 在后台任务长时间无新事件时按固定间隔发出（``data`` 含
    ``elapsed`` 秒数），让 UI 能刷新"已用时"，消除"卡死"错觉。
    ``cancelled`` 表示用户主动停止，任务未产出最终结果。
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


def _describe_chunking(fm, short: bool = False) -> str:
    """文件分块描述（与 CLI ``/file-list`` 同源）；``short`` 用于表格单列：``代码`` / ``文本``。"""
    try:
        from code_chunker import describe_file_chunking, strategy_display
    except ImportError:  # pragma: no cover
        from src.code_chunker import describe_file_chunking, strategy_display  # type: ignore
    strategy = str(getattr(fm, "chunk_strategy", "") or "text")
    if short:
        label = strategy_display(strategy)
        return "代码" if label.startswith("代码") else "文本"
    return describe_file_chunking(
        getattr(fm, "file_path", ""), strategy, int(getattr(fm, "symbol_count", 0) or 0)
    )


def _code_chunking_env_text() -> str:
    """系统页「代码分块」一行：``启用 · max 1500 字 · tree-sitter-language-pack 1.16.2`` 或未启用原因。"""
    try:
        from code_chunker import availability_message, dependency_version, is_enabled
        import config as _cfg
    except ImportError:  # pragma: no cover
        return ""
    if is_enabled():
        return (
            f"启用 · max {getattr(_cfg, 'CODE_CHUNK_MAX_CHARS', '')} 字 · "
            f"tree-sitter-language-pack {dependency_version()}"
        )
    return f"未启用：{availability_message()}"

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
        complete_text: Callable = _default_complete_text,
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
        self._complete_text = complete_text

        self._rag_engine = None
        self._session_manager = None
        self._graph_query = None
        self._active_react: Optional[Any] = None
        # 跨模式取消：RAG / 单 Agent / 多 Agent 三种模式共用同一套取消机制
        # （``_cancel_event`` 指向当前运行的取消信号，每次运行独立创建）。
        # ``_running`` 标记当前是否有对话任务在跑（UI 据此决定是否接受新请求）。
        self._cancel_event = threading.Event()
        self._running = False
        # 心跳间隔（秒）：后台任务超过该时长无新事件时，向 UI 发一次 heartbeat。
        self.heartbeat_interval: float = 1.0
        # 交互式确认：单 Agent 遇到危险操作时挂起等待用户在页面上「允许/拒绝」。
        # ``_pending_confirm`` 为 ``{"event": Event, "approved": bool, "data": dict}``。
        self._pending_confirm: Optional[Dict[str, Any]] = None
        self.confirm_timeout: float = 300.0
        # 工具页轻量持久状态（最近库 / 命令历史，F9 P3-1/2）：惰性创建，路径经 runtime_paths 解析
        self._tools_state: Optional[Any] = None

    # ---------- 工具页持久状态（最近数据库 / 命令历史） ----------

    @property
    def tools_state(self):
        """``ToolsState``（惰性）；测试可直接赋值为指向 ``tmp_path`` 的实例。"""
        if self._tools_state is None:
            from .tools_state import ToolsState

            self._tools_state = ToolsState()
        return self._tools_state

    def recent_databases(self) -> List[str]:
        """最近成功连接过的 SQLite 路径（最新在前，≤8）。读失败回退空列表。"""
        try:
            return list(self.tools_state.recent_databases())
        except BaseException as exc:  # noqa: BLE001
            logger.warning("读取最近数据库失败: %s", exc)
            return []

    def shell_history(self) -> List[str]:
        """成功执行过的命令（最新在前、去重，≤50）。读失败回退空列表。"""
        try:
            return list(self.tools_state.shell_history())
        except BaseException as exc:  # noqa: BLE001
            logger.warning("读取命令历史失败: %s", exc)
            return []

    # ---------- 任务生命周期 / 取消 ----------

    def is_running(self) -> bool:
        """当前是否有对话任务（任一模式）正在执行。"""
        return bool(self._running)

    def is_cancelled(self) -> bool:
        """当前任务是否已收到停止信号。"""
        return self._cancel_event.is_set()

    def stop_current(self) -> bool:
        """停止当前正在运行的对话任务（任一模式）。

        - 置位当前运行的取消信号：RAG 编排在阶段边界看到后中止，桥接生成器
          立刻停止转发并产出 ``cancelled`` 事件。
        - 若单 Agent 引擎在跑，同时调用其 ``stop()``。

        返回是否有任务被通知停止。
        """
        notified = False
        if self._active_react is not None:
            try:
                self._active_react.stop()
            except Exception:  # noqa: BLE001
                pass
            notified = True
        if self._running:
            notified = True
        if notified:
            self._cancel_event.set()
        # 停止时同时释放挂起的确认（按"拒绝"处理），避免后台线程一直等待
        self.resolve_confirm(False)
        return notified

    # ---------- 交互式确认（单 Agent 危险操作审批）----------

    def pending_confirm(self) -> Optional[Dict[str, Any]]:
        """当前挂起等待用户审批的确认请求（无则 None）。"""
        pending = self._pending_confirm
        return dict(pending["data"]) if pending else None

    def resolve_confirm(self, approved: bool) -> bool:
        """用户在页面上做出「允许/拒绝」决定；返回是否确有挂起的确认。"""
        pending = self._pending_confirm
        if not pending:
            return False
        pending["approved"] = bool(approved)
        pending["event"].set()
        return True

    def _ask_confirm(self, q: "queue.Queue", evt: Dict[str, Any], cancel: threading.Event) -> bool:
        """在后台线程中挂起：向 UI 推送 ``confirm`` 事件，等待 ``resolve_confirm``。

        取消信号置位或超时（``confirm_timeout``）视为拒绝。
        """
        pending = {"event": threading.Event(), "approved": False, "data": dict(evt)}
        self._pending_confirm = pending
        q.put(StreamEvent("confirm", evt.get("message", "是否确认执行？"), dict(evt)))
        started = time.monotonic()
        try:
            while not pending["event"].wait(0.2):
                if cancel.is_set():
                    return False
                if time.monotonic() - started > self.confirm_timeout:
                    return False
            return bool(pending["approved"])
        finally:
            if self._pending_confirm is pending:
                self._pending_confirm = None

    def _bridge(
        self,
        run: Callable[["queue.Queue", threading.Event], Any],
        on_finish: Callable[[Dict[str, Any], Dict[str, BaseException]], Iterator[StreamEvent]],
    ) -> Iterator[StreamEvent]:
        """把"后台线程 + 回调"桥接为带心跳与取消的事件流（三种模式共用）。

        Args:
            run: 在后台线程中执行的函数，接收 ``(q, cancel)``：事件队列 ``q``
                用于回调投递 ``StreamEvent``，``cancel`` 为本次运行的取消信号
                （``threading.Event``）；返回值存入 ``result_holder["result"]``。
            on_finish: 后台正常结束（未取消）后调用，参数为
                ``(result_holder, error_holder)``，产出收尾事件（answer/error）。

        行为：
        - 队列 ``get`` 带超时，超时即产出 ``heartbeat``（含 ``elapsed``）。
        - 每次循环检查取消信号；命中则产出 ``cancelled`` 并停止转发（后台
          线程为 daemon，继续跑完当前阻塞调用后自行退出，其结果被丢弃）。
        - 生成器被消费方关闭（Gradio ``cancels`` 触发 GeneratorExit）时同样
          置位取消信号，让编排层尽快停止。
        """
        q: "queue.Queue" = queue.Queue()
        result_holder: Dict[str, Any] = {}
        error_holder: Dict[str, BaseException] = {}

        # 每次运行使用独立的取消信号：被取消但仍在后台收尾的旧任务不会因为
        # 新任务开始（重置信号）而"复活"继续跑完后续阶段。
        cancel = threading.Event()
        self._cancel_event = cancel

        def worker():
            try:
                result_holder["result"] = run(q, cancel)
            except BaseException as exc:  # noqa: BLE001
                error_holder["error"] = exc
            finally:
                q.put(_DONE)

        self._running = True
        started = time.monotonic()
        thread = threading.Thread(target=worker, daemon=True)
        thread.start()

        cancelled = False
        try:
            while True:
                if cancel.is_set():
                    cancelled = True
                    yield StreamEvent("cancelled", "已停止", {"elapsed": time.monotonic() - started})
                    break
                try:
                    item = q.get(timeout=self.heartbeat_interval)
                except queue.Empty:
                    yield StreamEvent("heartbeat", "", {"elapsed": time.monotonic() - started})
                    continue
                if item is _DONE:
                    break
                yield item
            if not cancelled:
                yield from on_finish(result_holder, error_holder)
        except GeneratorExit:
            # 消费方主动关闭（如 Gradio cancels）：通知后台尽快停止
            cancel.set()
            if self._active_react is not None:
                try:
                    self._active_react.stop()
                except Exception:  # noqa: BLE001
                    pass
            raise
        finally:
            self._running = False

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

    def model_table(self) -> List[Dict[str, Any]]:
        """已安装模型清单（含"当前 / 已加载"标记），对齐 CLI ``/model list``。"""
        info = self.current_model()
        loaded = set(info.get("loaded_models") or [])
        current = info.get("model", "")
        names = self.list_models()
        if current and current not in names:
            names = [current] + names
        return [
            {"name": n, "current": n == current, "loaded": n in loaded}
            for n in names
        ]

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

    # ---------- 会话上下文（三种模式共用）----------

    def _context(self, session_id: Optional[str] = None):
        """构造绑定到指定会话（为空则当前会话）的 ConversationContext。"""
        from conversation_context import ConversationContext

        return ConversationContext(self.session_manager, session_id=session_id or None)

    @staticmethod
    def _health_before(ctx, question: str) -> Dict[str, Any]:
        """提问前的健康度快照（用于判断空闲/话题漂移）；失败返回空 dict。"""
        try:
            return ctx.health(question)
        except Exception:  # noqa: BLE001
            return {}

    @staticmethod
    def _finish_turn(
        ctx, question: str, answer: str, pre: Dict[str, Any], *,
        trace: Optional[str] = None, rewritten: Optional[str] = None,
        progress=None, record: bool = True,
    ) -> Dict[str, Any]:
        """记录本轮（可选）并返回合并后的上下文健康度/指标，供 UI 状态行与提示。"""
        from conversation_context import merge_health

        try:
            if record:
                ctx.record(question, answer, trace=trace, rewritten=rewritten, progress=progress)
            post = ctx.health()
            return merge_health(pre, post)
        except Exception as exc:  # noqa: BLE001 - 落库/统计失败不影响返回
            return {"error": str(exc)}

    # ---------- RAG 检索 ----------

    def rag_query_stream(
        self, question: str, enable_web_search: bool = True,
        session_id: Optional[str] = None,
    ) -> Iterator[StreamEvent]:
        """流式 RAG 检索，与 CLI 的 ``/ask`` 行为一致。

        改动说明：此前仅裸调 ``query_with_sources``，缺少 CLI 独有的高级编排，
        导致同一问题两端答案质量差异极大。现改为调用共享层
        ``rag_pipeline.answer_question``，从而获得：元/概览问题直答、LLM 驱动
        的网络搜索规划、多查询合并、页面正文增强、知识库/网络双区综合、0 命中
        网络回退。编排级进度与 RAG 检索进度统一桥接为 ``StreamEvent``。

        连续对话：传入 ``session_id``（每个浏览器标签页自己的会话）后，追问会
        结合会话历史改写为独立问题（``answer`` 事件 ``data["rewritten"]``），
        综合回答带最近几轮上下文；对话完成后写入该会话并按需自动压缩，
        ``data["context"]`` 携带上下文指标与"建议新会话"判定。
        """
        question = (question or "").strip()
        if not question:
            yield StreamEvent("error", "问题不能为空")
            return

        import rag_pipeline

        def run(q: "queue.Queue", cancel: threading.Event):
            def progress_cb(evt: Dict[str, Any]):
                # 元/概览事件带结构化数据（files/stats），透传给 UI 展示。
                q.put(StreamEvent("progress", evt.get("message", ""), evt))

            ctx = self._context(session_id)
            pre = self._health_before(ctx, question)
            result = rag_pipeline.answer_question(
                self.rag_engine,
                question,
                enable_web_search=enable_web_search,
                show_progress=True,
                progress=progress_cb,
                rag_progress_callback=progress_cb,
                should_stop=cancel.is_set,
                context=ctx,
            )
            # 对话落库（与 CLI 一致）：即使是元查询也记录，便于历史回看。
            # 在后台线程内完成，压缩期间心跳仍可刷新 UI。
            recorded = "[知识库概览]" if result.get("kind") == "meta" else result.get("answer", "")
            result["context"] = self._finish_turn(
                ctx, question, recorded, pre,
                rewritten=result.get("rewritten"), progress=progress_cb,
            )
            return result

        def on_finish(result_holder, error_holder):
            if "error" in error_holder:
                exc = error_holder["error"]
                cancelled_cls = getattr(rag_pipeline, "PipelineCancelled", ())
                if cancelled_cls and isinstance(exc, cancelled_cls):
                    yield StreamEvent("cancelled", "已停止")
                    return
                yield StreamEvent("error", f"检索失败: {exc}")
                return

            result = result_holder.get("result", {}) or {}
            answer = result.get("answer", "")
            yield StreamEvent(
                "answer",
                answer,
                {
                    "kind": result.get("kind", "answer"),
                    "sources": result.get("kb_sources", []),
                    "web_sources": result.get("web_sources", []),
                    "meta": result.get("meta"),
                    "rewritten": result.get("rewritten"),
                    "context": result.get("context") or {},
                    # kind="fallback" 时附原问题，供 UI「用单 Agent 重试」
                    "fallback_question": result.get("fallback_question"),
                },
            )

        yield from self._bridge(run, on_finish)

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
        self, user_input: str, confirm_handler: Optional[Callable] = None,
        session_id: Optional[str] = None, interactive_confirm: bool = False,
    ) -> Iterator[StreamEvent]:
        """流式单 Agent 对话，把 ``on_step`` 桥接为 ``step`` 事件流。

        引擎绑定到 ``session_id`` 对应的会话上下文：开局读取滚动摘要 + 最近几轮，
        结束后由引擎自行把本轮折叠写回会话（任务 + 最终答案 + 一句执行摘要）。

        危险操作确认的三种策略：
        - ``confirm_handler`` 非空：直接调用（如"自动确认"时的 ``lambda: True``）；
        - ``interactive_confirm=True``：推送 ``confirm`` 事件并挂起，等待用户在
          页面上点「允许/拒绝」（``resolve_confirm``）；
        - 否则默认拒绝，保证安全。
        """
        user_input = (user_input or "").strip()
        if not user_input:
            yield StreamEvent("error", "输入不能为空")
            return

        # 确保知识库工具就绪
        _ = self.rag_engine

        engine_holder: Dict[str, Any] = {}

        def run(q: "queue.Queue", cancel: threading.Event):
            def on_step(evt: Dict[str, Any]):
                q.put(StreamEvent("step", evt.get("message", ""), evt))

            def on_confirm(evt: Dict[str, Any]) -> bool:
                if confirm_handler is not None:
                    return bool(confirm_handler(evt))
                if interactive_confirm:
                    return self._ask_confirm(q, evt, cancel)
                # 无确认处理器时，默认拒绝危险操作，保证安全。
                return False

            ctx = self._context(session_id)
            pre = self._health_before(ctx, user_input)
            engine = self._react_factory(on_step=on_step, on_confirm=on_confirm, context=ctx)
            engine_holder["engine"] = engine
            self._active_react = engine
            answer = engine.chat(user_input)
            # 引擎已在 chat() 结束时把本轮折叠写回会话，这里只汇总健康度
            return {
                "answer": answer,
                "context": self._finish_turn(ctx, user_input, answer, pre, record=False),
            }

        def on_finish(result_holder, error_holder):
            engine = engine_holder.get("engine")
            if "error" in error_holder:
                yield StreamEvent("error", f"Agent 执行失败: {error_holder['error']}")
                return
            result = result_holder.get("result") or {}
            if not isinstance(result, dict):
                result = {"answer": str(result), "context": {}}
            yield StreamEvent(
                "answer",
                result.get("answer", ""),
                {
                    "step_log": getattr(engine, "step_log", []),
                    "context": result.get("context") or {},
                },
            )

        try:
            yield from self._bridge(run, on_finish)
        finally:
            self._active_react = None

    def stop_agent(self) -> bool:
        """中断当前正在运行的对话任务（任一模式）。兼容旧名，等价 ``stop_current``。"""
        return self.stop_current()

    # ---------- 自动路由（F8 P3-3）----------

    def kb_available(self) -> bool:
        """知识库是否可用（RAG 引擎已建索引）；引擎创建失败视为不可用。"""
        try:
            return getattr(self.rag_engine, "query_engine", None) is not None
        except BaseException:  # noqa: BLE001
            return False

    def classify_intent(self, message: str) -> Tuple[str, str]:
        """调用 ``intent_router.classify_intent`` 判定 ``(mode, reason)``；异常回退 rag。"""
        try:
            from intent_router import classify_intent
            decision = classify_intent(message, kb_available=self.kb_available())
            return decision.mode, decision.reason
        except BaseException as exc:  # noqa: BLE001
            return "rag", f"判定失败，默认 RAG（{exc}）"

    def chat_auto_stream(
        self, message: str, enable_web_search: bool = True, auto_confirm: bool = False,
        session_id: Optional[str] = None, interactive_confirm: bool = True,
    ) -> Iterator[StreamEvent]:
        """「自动」模式：先判定意图，再分发到 ``rag_query_stream`` / ``agent_chat_stream``。

        - 判定后先 yield 一条 ``progress``「🧭 自动路由：按 RAG/Agent 处理（原因）」；
        - 子流事件原样透传，``answer`` 事件的 ``data`` 追加 ``routed_mode``
          （``"rag"``/``"agent"``）与 ``route_reason``，供 UI 选择渲染路径；
        - Agent 路径的确认策略与「单 Agent」模式一致：``auto_confirm`` 全部放行，
          否则按 ``interactive_confirm`` 决定挂起等待页面审批还是默认拒绝。
        """
        message = (message or "").strip()
        if not message:
            yield StreamEvent("error", "输入不能为空")
            return

        routed, reason = self.classify_intent(message)
        label = "Agent" if routed == "agent" else "RAG"
        yield StreamEvent(
            "progress", f"🧭 自动路由：按 {label} 处理（{reason}）",
            {"phase": "route", "routed_mode": routed, "route_reason": reason},
        )

        if routed == "agent":
            confirm_handler = (lambda evt: True) if auto_confirm else None
            stream = self.agent_chat_stream(
                message, confirm_handler=confirm_handler, session_id=session_id,
                interactive_confirm=(not auto_confirm) and bool(interactive_confirm),
            )
        else:
            stream = self.rag_query_stream(
                message, enable_web_search=enable_web_search, session_id=session_id,
            )

        for evt in stream:
            if evt.kind == "answer":
                data = dict(evt.data) if isinstance(evt.data, dict) else {}
                data["routed_mode"] = routed
                data["route_reason"] = reason
                yield StreamEvent("answer", evt.message, data)
            else:
                yield evt

    # ---------- 多 Agent 协作 ----------

    def _run_orchestrator(self, request: str, mode: Optional[str], progress=None,
                          context=None) -> Dict[str, Any]:
        """创建编排器执行一次协作请求，结束后释放；异常转为失败 dict。"""
        # 确保知识库引擎已注入全局注册表：RAGAgent 承接通用任务时会复用
        # rag_pipeline.answer_question，需要全局 rag_engine 才能真正检索。
        try:
            _ = self.rag_engine
        except Exception:  # noqa: BLE001 - 引擎不可用时仍允许多 Agent 尝试运行
            pass

        resolved = self._resolve_mode(mode)
        orchestrator = self._orchestrator_factory()
        try:
            kwargs: Dict[str, Any] = {}
            if progress is not None:
                kwargs["progress"] = progress
            if context is not None:
                kwargs["context"] = context
            return orchestrator.process_request(request, resolved, **kwargs)
        except BaseException as exc:  # noqa: BLE001
            return {"success": False, "error": str(exc), "summary": "协作执行失败"}
        finally:
            shutdown = getattr(orchestrator, "shutdown", None)
            if callable(shutdown):
                try:
                    shutdown()
                except Exception:
                    pass

    def collaboration_modes(self) -> List[Tuple[str, str]]:
        """多 Agent 可选协作模式 ``[(中文标签, 模式值), ...]``；首项为"自动"。"""
        labels = {
            "hierarchy": "层级协作", "parallel": "并行协作",
            "sequential": "顺序协作", "competitive": "竞争协作",
        }
        out: List[Tuple[str, str]] = [("自动（由编排器决定）", "")]
        try:
            from agents.agent_types import CollaborationMode
            for m in CollaborationMode:
                out.append((labels.get(m.value, m.value), m.value))
        except BaseException:  # noqa: BLE001
            out.extend((v, k) for k, v in labels.items())
        return out

    def multi_agent_run(self, request: str, mode: Optional[str] = None) -> Dict[str, Any]:
        """执行多 Agent 协作（阻塞），返回整合结果 dict。"""
        request = (request or "").strip()
        if not request:
            return {"success": False, "error": "请求不能为空", "summary": "请求为空"}
        return self._run_orchestrator(request, mode)

    def multi_agent_stream(
        self, request: str, mode: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> Iterator[StreamEvent]:
        """流式多 Agent 协作：把"分解 → 调度 → 执行 → 整合"各阶段桥接为
        ``progress`` 事件，最后产出 ``answer``（``data`` 为整合结果 dict）。

        此前 Web 端只能显示一条静态"执行中"，多 Agent 往往要跑数分钟，用户
        完全不知道进行到哪一步。

        连续对话：疑似追问的请求先结合会话历史改写为独立请求（不做工具记忆），
        协作结束后把"请求 + 整合摘要"记入会话；``data["rewritten"]`` /
        ``data["context"]`` 与 RAG 模式一致。
        """
        request = (request or "").strip()
        if not request:
            yield StreamEvent("error", "请求不能为空")
            return

        def run(q: "queue.Queue", cancel: threading.Event):
            def progress_cb(evt: Dict[str, Any]):
                q.put(StreamEvent("progress", evt.get("message", ""), evt))

            ctx = self._context(session_id)
            pre = self._health_before(ctx, request)
            effective, rewritten = request, None
            try:
                rw = ctx.rewrite_question(request, progress=progress_cb)
                if rw.get("changed"):
                    effective = rw["question"]
                    rewritten = effective
            except Exception:  # noqa: BLE001 - 改写失败沿用原请求
                pass
            result = self._run_orchestrator(effective, mode, progress=progress_cb, context=ctx)
            if not isinstance(result, dict):
                result = {"success": False, "summary": str(result)}
            summary = str(result.get("summary", ""))
            # 会话记录面向用户的综合回答（answer），而不是统计句
            answer = str(result.get("answer") or "").strip() or summary
            recorded = answer if result.get("success") else f"[协作失败] {answer}"
            result["rewritten"] = rewritten
            result["context"] = self._finish_turn(
                ctx, request, recorded, pre, rewritten=rewritten, progress=progress_cb,
            )
            return result

        def on_finish(result_holder, error_holder):
            if "error" in error_holder:
                yield StreamEvent("error", f"协作执行失败: {error_holder['error']}")
                return
            result = result_holder.get("result") or {}
            message = str(result.get("answer") or "").strip() or str(result.get("summary", ""))
            yield StreamEvent("answer", message, result)

        yield from self._bridge(run, on_finish)

    # ---------- 知识库管理 ----------

    def _ingest_summary(self, file_count: int, doc_count: int, paths: Optional[List[str]] = None) -> str:
        """入库成功文案（与 CLI ``/add`` 同源）：文件数 · 片段数（· 代码文件按函数/类切分，符号数）。

        代码分块未启用且本次含代码文件时，追加一行一次性提示（进程内仅一次）。
        """
        try:
            from code_chunker import availability_hint_once, format_ingest_summary, language_for
        except ImportError:  # pragma: no cover
            from src.code_chunker import availability_hint_once, format_ingest_summary, language_for  # type: ignore
        stats = getattr(self.rag_engine, "last_ingest_stats", None) or {}
        if stats:
            text = format_ingest_summary(stats, file_count=file_count)
        else:
            text = f"已入库 {file_count} 个文件，共 {doc_count} 个片段"
        candidates = list(stats.keys()) or list(paths or [])
        if any(language_for(None, str(p)) for p in candidates):
            hint = availability_hint_once()
            if hint:
                text += f"\n💡 {hint}（详见「系统」页）"
        return text

    def _graph_note(self) -> str:
        return (
            "，已同步更新知识图谱"
            if getattr(self.rag_engine, "last_graph_derived", False)
            else "，知识图谱未自动更新（可在「知识图谱」页手动构建）"
        )

    def add_documents(self, file_paths: List[str], progress_callback=None) -> str:
        """把上传的文件加入知识库，返回人类可读的结果摘要。

        ``progress_callback`` 透传给 ``RAGEngine.add_documents``（``stage=chunk|embed`` 事件）。
        """
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
                if progress_callback is not None:
                    self.rag_engine.add_documents(all_docs, valid_paths, progress_callback=progress_callback)
                else:
                    self.rag_engine.add_documents(all_docs, valid_paths)
            except BaseException as exc:  # noqa: BLE001
                return f"[错误] 入库失败: {exc}"

        if all_docs:
            lines = [f"[成功] {self._ingest_summary(len(added_files), loaded, valid_paths)}"]
        else:
            lines = [f"[成功] 已入库 {len(added_files)} 个文件，共 {loaded} 个片段"]
        if errors:
            lines.append("[部分失败]")
            lines.extend(f"  - {e}" for e in errors)
        return "\n".join(lines)

    def add_path(self, path: str, file_types: Optional[str] = None, progress_callback=None) -> str:
        """把服务器上的文件/目录**追加**入库（等价 CLI ``/add <path>``，可选类型过滤）。

        与 ``rebuild_index``（替换整个索引）不同，本方法只追加。``file_types`` 为
        逗号分隔的后缀（如 ``.pdf,.md``），等价 CLI ``--types``。
        """
        path = (path or "").strip()
        if not path:
            return "[提示] 请输入文件或目录路径"
        types = [t.strip() for t in (file_types or "").split(",") if t.strip()] or None
        try:
            docs = self._load_documents(path, types) if types else self._load_documents(path)
        except BaseException as exc:  # noqa: BLE001
            return f"[错误] 加载失败: {exc}"
        if not docs:
            return f"[提示] 未找到可加载的文档: {path}"
        try:
            if progress_callback is not None:
                self.rag_engine.add_documents(docs, [path], progress_callback=progress_callback)
            else:
                self.rag_engine.add_documents(docs, [path])
        except BaseException as exc:  # noqa: BLE001
            return f"[错误] 入库失败: {exc}"
        stats = getattr(self.rag_engine, "last_ingest_stats", None) or {}
        file_count = len(stats) if stats else 1
        return f"[成功] {self._ingest_summary(file_count, len(docs), [path])}{self._graph_note()}"

    def ingest_stream(self, file_paths: Optional[List[str]] = None, path: Optional[str] = None,
                      file_types: Optional[str] = None) -> Iterator[StreamEvent]:
        """流式入库：``progress`` 事件（``stage=chunk|embed``，带 current/total）+ 最终 ``answer``。

        ``file_paths`` 非空走上传路径（``add_documents``），否则走 ``add_path``。结果文案在
        ``answer.message``（含 ``[成功]/[提示]/[错误]`` 前缀，由 ``app._fmt_result`` 换图标）。
        """
        def run(q: "queue.Queue", cancel: threading.Event):
            def progress_cb(evt: Dict[str, Any]):
                q.put(StreamEvent("progress", evt.get("message", ""), evt))

            if file_paths:
                return self.add_documents(list(file_paths), progress_callback=progress_cb)
            return self.add_path(path or "", file_types, progress_callback=progress_cb)

        def on_finish(result_holder, error_holder):
            if "error" in error_holder:
                yield StreamEvent("error", f"入库失败: {error_holder['error']}")
                return
            yield StreamEvent("answer", str(result_holder.get("result") or ""), {})

        yield from self._bridge(run, on_finish)

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

    @staticmethod
    def _fmt_time(value: Any) -> str:
        """把 datetime 渲染为 ``2026-09-03 15:12``；非 datetime 返回空串。"""
        strftime = getattr(value, "strftime", None)
        if not callable(strftime):
            return ""
        try:
            return strftime("%Y-%m-%d %H:%M")
        except Exception:  # noqa: BLE001
            return ""

    def list_sessions(self) -> List[Dict[str, Any]]:
        """返回会话摘要列表（含状态、更新时间、首条提问预览，按更新时间倒序）。"""
        sessions = self.session_manager.list_sessions()
        current = self.session_manager.get_current_session()
        current_id = current.session_id if current else None
        result = []
        for s in sessions:
            msgs = [m for m in getattr(s, "messages", []) if isinstance(m, dict)]
            first_user = next((m.get("content", "") for m in msgs if m.get("role") == "user"), "")
            status = getattr(getattr(s, "status", None), "value", "") or ""
            result.append(
                {
                    "session_id": s.session_id,
                    "title": s.title,
                    "messages": len(getattr(s, "messages", [])),
                    "is_current": s.session_id == current_id,
                    "status": status if isinstance(status, str) else "",
                    "updated_at": self._fmt_time(getattr(s, "updated_at", None)),
                    "created_at": self._fmt_time(getattr(s, "created_at", None)),
                    "preview": str(first_user)[:40],
                }
            )
        return result

    def create_session(
        self, title: Optional[str] = None, carry_summary: bool = False,
        from_session_id: Optional[str] = None,
    ) -> str:
        """新建会话并切换过去，返回其 id。

        ``carry_summary`` 为真时，把 ``from_session_id``（为空则当前会话）的
        滚动摘要作为新会话的首条背景，使新会话仍"记得"上一会话的要点。
        """
        if carry_summary:
            ctx = self._context(from_session_id)
            session = ctx.new_session(title=title or None, carry_summary=True)
            return session.session_id
        session = self.session_manager.create_session(title=title or None)
        return session.session_id

    def switch_session(self, session_id: str) -> bool:
        if not session_id:
            return False
        return bool(self.session_manager.switch_session(session_id))

    # ---------- 连续对话上下文（供对话页会话控件使用）----------

    def ensure_session(self) -> str:
        """返回当前会话 id；没有则新建。用于浏览器标签页初始化自己的会话绑定。"""
        current = self.session_manager.get_current_session()
        if current is None:
            current = self.session_manager.create_session()
        return current.session_id

    def session_choices(self) -> List[Tuple[str, str]]:
        """会话下拉选项 ``[(label, session_id), ...]``，按更新时间倒序。"""
        out: List[Tuple[str, str]] = []
        for s in self.session_manager.list_sessions():
            n = len([m for m in getattr(s, "messages", []) if isinstance(m, dict)])
            out.append((f"{s.title}（{n} 条）· {s.session_id[:8]}", s.session_id))
        return out

    def chat_history(self, session_id: Optional[str] = None) -> List[Dict[str, str]]:
        """会话内的对话消息（``[{role, content}, ...]``），供 Chatbot 多轮展示。"""
        try:
            msgs = self._context(session_id).all_messages()
        except Exception:  # noqa: BLE001
            return []
        return [{"role": m.get("role", "user"), "content": str(m.get("content", ""))} for m in msgs]

    def context_metrics(self, session_id: Optional[str] = None) -> Dict[str, Any]:
        """上下文指标：轮数 / 估算 token / 预算 / 压缩次数 / 摘要预览。"""
        try:
            return self._context(session_id).metrics()
        except Exception as exc:  # noqa: BLE001
            return {"error": str(exc)}

    def carried_summary(self, session_id: Optional[str] = None) -> str:
        """若该会话是"携带摘要"新建的，返回承接自上一会话的背景文本；否则空串。"""
        try:
            return self._context(session_id).carried_summary()
        except Exception:  # noqa: BLE001
            return ""

    def clear_context(self, session_id: Optional[str] = None) -> bool:
        """清空指定会话的对话上下文（消息 + 滚动摘要），会话本身保留。"""
        try:
            return bool(self._context(session_id).clear())
        except Exception:  # noqa: BLE001
            return False

    def compact_context(self, session_id: Optional[str] = None) -> Dict[str, Any]:
        """手动压缩指定会话的历史上下文。"""
        try:
            result = self._context(session_id).compact()
            return result or {"folded_messages": 0}
        except Exception as exc:  # noqa: BLE001
            return {"error": str(exc)}

    def mark_suggested(self, session_id: Optional[str] = None) -> None:
        """UI 已展示"建议新会话"提示。"""
        try:
            self._context(session_id).mark_suggested()
        except Exception:  # noqa: BLE001
            pass

    def continue_session(self, session_id: Optional[str] = None) -> None:
        """用户选择继续当前会话：压缩次数再 +2 才再次提示。"""
        try:
            self._context(session_id).continue_current()
        except Exception:  # noqa: BLE001
            pass

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

        CLI 的 /code-*、/git-*、/db-*、/exec、/file 等命令底层都调用
        ``registry.execute(tool, args)``；此方法把这些工具直接暴露给 Web，
        与 CLI 命令面对齐。
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

    # -- 网络搜索缓存（系统页 · 运行环境；搜索本身由对话页「联网搜索」与 Agent 覆盖）--
    def web_cache_status(self) -> str:
        return self.run_tool("web_cache_status", {})

    def web_cache_clear(self) -> str:
        return self.run_tool("web_cache_clear", {}, auto_confirm=True)

    # -- 代码助手（F9 P2-1）：受限 ReAct（只读工具集、≤12 步、一次性上下文）--

    CODE_ASSIST_ACTIONS: Dict[str, str] = {
        "explain": "解释代码", "review": "审查问题", "tests": "生成测试",
        "docs": "生成文档", "refactor": "重构建议",
    }
    CODE_ASSIST_TOOLS = frozenset({
        "read_file", "list_directory", "search_files", "ast_search", "code_quality_check", "get_current_dir",
    })
    CODE_ASSIST_MAX_ITERATIONS = 12
    CODE_ASSIST_INLINE_MAX = 6000
    """单文件内容不超过该字数时直接放进提示，省一次 ``read_file`` 往返。"""

    _CODE_ASSIST_GUIDE: Dict[str, str] = {
        "explain": "先说明用途与入口，再按调用顺序讲关键函数/类，最后列出依赖与注意点。",
        "review": "按 严重度(高/中/低) 列问题，每条给 位置(文件:行)、原因、修复建议；无问题要明说。",
        "tests": "给出 pytest 测试代码（可直接落盘的完整文件），覆盖正常路径与边界，Mock 外部 I/O。",
        "docs": "生成模块级 docstring 与 README 片段（用途、用法示例、参数说明）。",
        "refactor": "列 3-5 条可落地的重构建议，每条给 动机、改法、风险。",
    }

    def build_code_assist_prompt(self, action: str, path: str, extra: str = "",
                                 content: Optional[str] = None) -> str:
        """组装代码助手的 ``system_prompt_extra``（附录 A-1）。``content`` 非空时内联文件内容。"""
        action = (action or "").strip().lower()
        guide = self._CODE_ASSIST_GUIDE.get(action, self._CODE_ASSIST_GUIDE["explain"])
        lines = [
            f"角色：代码助手。目标路径：{path}。用户补充：{(extra or '').strip() or '无'}",
            f"动作 = {action}：{guide}",
            "规则：只读，不得写文件或执行命令；引用代码时标 文件:行；结论用中文。",
        ]
        if content is not None:
            lines[-1] += "内容已给出，勿再 read_file。"
            lines.append(f"文件内容：\n{content}")
        return "\n".join(lines)

    def code_assist_stream(self, action: str, path: str, extra: str = "") -> Iterator[StreamEvent]:
        """代码助手：对 ``path`` 执行 ``action``（explain/review/tests/docs/refactor），流式返回。

        经 ``_bridge`` 运行受限 ``ReActEngine``（只读工具集、``max_iterations=12``、
        一次性上下文不写回会话）；``on_step`` → ``step`` 事件，最终答案 → ``answer``。
        """
        import os

        action = (action or "").strip().lower()
        path = (path or "").strip() or "."
        if action not in self.CODE_ASSIST_ACTIONS:
            yield StreamEvent("error", f"未知动作 '{action}'，支持: {' / '.join(self.CODE_ASSIST_ACTIONS)}")
            return
        if not os.path.exists(os.path.expanduser(path)):
            yield StreamEvent("error", f"路径不存在: {path}")
            return
        if self.is_running():
            yield StreamEvent("error", "有任务进行中，请先停止或等待完成")
            return

        content: Optional[str] = None
        real = os.path.expanduser(path)
        if os.path.isfile(real):
            try:
                if os.path.getsize(real) <= self.CODE_ASSIST_INLINE_MAX * 4:
                    with open(real, "r", encoding="utf-8", errors="ignore") as f:
                        text = f.read()
                    if len(text) <= self.CODE_ASSIST_INLINE_MAX:
                        content = text
            except OSError:
                content = None
        label = self.CODE_ASSIST_ACTIONS[action]
        prompt_extra = self.build_code_assist_prompt(action, path, extra, content)
        task = f"请对 {path} 执行「{label}」" + (f"。补充：{extra.strip()}" if (extra or "").strip() else "")

        engine_holder: Dict[str, Any] = {}

        def run(q: "queue.Queue", cancel: threading.Event):
            def on_step(evt: Dict[str, Any]):
                q.put(StreamEvent("step", evt.get("message", ""), evt))

            engine = self._react_factory(
                on_step=on_step, on_confirm=lambda evt: False, context=ScratchContext(),
                allowed_tools=set(self.CODE_ASSIST_TOOLS), system_prompt_extra=prompt_extra,
                max_iterations=self.CODE_ASSIST_MAX_ITERATIONS,
            )
            engine_holder["engine"] = engine
            self._active_react = engine
            return engine.chat(task)

        def on_finish(result_holder, error_holder):
            engine = engine_holder.get("engine")
            if "error" in error_holder:
                yield StreamEvent("error", f"代码助手执行失败: {error_holder['error']}")
                return
            answer = str(result_holder.get("result") or "").strip()
            if not answer:
                yield StreamEvent("error", "模型没有返回内容")
                return
            yield StreamEvent("answer", answer, {"action": action, "path": path,
                                                 "step_log": list(getattr(engine, "step_log", []) or [])})
            yield StreamEvent("done", "")

        try:
            yield from self._bridge(run, on_finish)
        finally:
            self._active_react = None

    CODE_SYMBOLS_MAX = 200

    def code_symbols(self, pattern: str, path: str = ".", search_by: str = "name") -> Dict[str, Any]:
        """符号搜索（结构化）：``{symbols: [{name, kind, file, line, complexity}], error?}``。

        直接调用 ``ASTAnalyzer.search_functions / search_classes``，目录模式逐文件搜索并
        同样尊重 ``search_by``（name / parameter / return / base / method）。
        """
        import os

        pattern = (pattern or "").strip()
        path = (path or ".").strip() or "."
        search_by = (search_by or "name").strip().lower() or "name"
        if not pattern:
            return {"symbols": [], "error": "请输入搜索模式"}
        real = os.path.expanduser(path)
        if not os.path.exists(real):
            return {"symbols": [], "error": f"路径不存在: {path}"}
        try:
            from code_analyzer import get_ast_analyzer

            analyzer = get_ast_analyzer()
            if os.path.isfile(real):
                files = [real]
            else:
                files = [str(p) for p in sorted(__import__("pathlib").Path(real).rglob("*.py"))
                         if "venv" not in str(p) and "__pycache__" not in str(p)]
            out: List[Dict[str, Any]] = []
            for fp in files:
                for fn in analyzer.search_functions(fp, pattern, search_by):
                    out.append({"name": fn.name, "kind": "函数", "file": fp, "line": fn.line_no,
                                "complexity": int(getattr(fn, "complexity", 1) or 1)})
                for cls in analyzer.search_classes(fp, pattern, search_by):
                    cx = sum(int(getattr(m, "complexity", 1) or 1) for m in getattr(cls, "methods", []) or [])
                    out.append({"name": cls.name, "kind": "类", "file": fp, "line": cls.line_no, "complexity": cx})
                if len(out) >= self.CODE_SYMBOLS_MAX:
                    break
            return {"symbols": out[: self.CODE_SYMBOLS_MAX], "truncated": len(out) > self.CODE_SYMBOLS_MAX}
        except BaseException as exc:  # noqa: BLE001
            return {"symbols": [], "error": str(exc)}

    CODE_QUALITY_MAX_ISSUES = 200
    _SEVERITY_ORDER = {"critical": 0, "error": 1, "warning": 2, "info": 3}

    def code_quality_report(self, path: str = ".") -> Dict[str, Any]:
        """质量检查（结构化）：``{path, files, score, total_issues, severity: {...}, issues: [...], error?}``。

        文件模式直接用 ``QualityChecker.check_file``；目录模式 ``check_project`` + ``get_project_summary``，
        问题按严重度排序汇总（最多 ``CODE_QUALITY_MAX_ISSUES`` 条）。
        """
        import os

        path = (path or ".").strip() or "."
        real = os.path.expanduser(path)
        base = {"path": path, "files": 0, "score": 0.0, "total_issues": 0,
                "severity": {"critical": 0, "error": 0, "warning": 0, "info": 0}, "issues": []}
        if not os.path.exists(real):
            return {**base, "error": f"路径不存在: {path}"}
        try:
            from code_analyzer import get_quality_checker

            checker = get_quality_checker()
            if os.path.isfile(real):
                reports = {real: checker.check_file(real)}
            else:
                reports = checker.check_project(real)
            if not reports:
                return {**base, "error": "没有可检查的 Python 文件"}
            summary = checker.get_project_summary(reports) or {}
            issues: List[Dict[str, Any]] = []
            for fp, rep in reports.items():
                for iss in getattr(rep, "issues", []) or []:
                    sev = getattr(getattr(iss, "severity", None), "value", str(getattr(iss, "severity", "")))
                    issues.append({"severity": sev, "file": fp, "line": int(getattr(iss, "line_no", 0) or 0),
                                   "message": str(getattr(iss, "message", ""))})
            issues.sort(key=lambda i: (self._SEVERITY_ORDER.get(i["severity"], 9), i["file"], i["line"]))
            sev = summary.get("severity_breakdown") or base["severity"]
            return {
                **base, "files": int(summary.get("total_files", len(reports)) or 0),
                "score": float(summary.get("average_score", 0.0) or 0.0),
                "total_issues": int(summary.get("total_issues", len(issues)) or 0),
                "severity": {k: int(sev.get(k, 0) or 0) for k in ("critical", "error", "warning", "info")},
                "issues": issues[: self.CODE_QUALITY_MAX_ISSUES],
                "truncated": len(issues) > self.CODE_QUALITY_MAX_ISSUES,
            }
        except BaseException as exc:  # noqa: BLE001
            return {**base, "error": str(exc)}

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

    # -- 提交信息增强（F9 P3-3）：暂存预览 → AI 生成（可编辑）→ 确认提交 --

    _GIT_EMPTY_PREVIEW: Dict[str, Any] = {
        "is_repo": False, "has_staged": False, "staged_files": [], "diff_stat": "",
        "files_changed": 0, "insertions": 0, "deletions": 0,
    }

    def git_commit_preview(self, repo_path: str = ".") -> Dict[str, Any]:
        """暂存区预览（共享层 ``GitAnalyzer.get_commit_preview``）：
        ``{is_repo, has_staged, staged_files[{status,label,path}], diff_stat, files_changed, insertions, deletions}``；
        异常时附 ``error``。"""
        try:
            from git_integration.git_analyzer import GitAnalyzer

            return GitAnalyzer(repo_path or ".").get_commit_preview()
        except BaseException as exc:  # noqa: BLE001
            return {**self._GIT_EMPTY_PREVIEW, "error": str(exc)}

    def git_commit_message(self, repo_path: str = ".") -> Dict[str, Any]:
        """AI 生成提交信息（沿用 ``CommitMessageGenerator`` 现有提示，附录 A-4）。

        返回 ``{title, body, message, error?}``；``message`` 为可直接填入编辑框的完整文本
        （标题 + 空行 + 正文）。无暂存 / 非仓库时返回 ``error``，不调用模型。
        """
        preview = self.git_commit_preview(repo_path)
        if preview.get("error"):
            return {"title": "", "body": "", "message": "", "error": preview["error"]}
        if not preview.get("is_repo"):
            return {"title": "", "body": "", "message": "", "error": "当前目录不是 Git 仓库"}
        if not preview.get("has_staged"):
            return {"title": "", "body": "", "message": "", "error": "暂存区为空，请先 git add 要提交的文件"}
        try:
            from git_integration.commit_generator import CommitMessageGenerator

            suggestion = CommitMessageGenerator(repo_path or ".").generate_commit_message(use_ai=True)
        except BaseException as exc:  # noqa: BLE001
            return {"title": "", "body": "", "message": "", "error": f"生成提交信息失败: {exc}"}
        title = (getattr(suggestion, "title", "") or "").strip()
        body = (getattr(suggestion, "body", "") or "").strip()
        if not title or title.lower().startswith("no changes staged"):
            return {"title": "", "body": "", "message": "", "error": "暂存区为空，请先 git add 要提交的文件"}
        message = f"{title}\n\n{body}" if body else title
        return {"title": title, "body": body, "message": message}

    def git_commit(self, message: str, repo_path: str = ".") -> str:
        """执行 ``git commit -m``（仅提交暂存区；调用方负责 ``shell_enable`` 门控与二次确认）。

        不经 registry：在 service 层直接调用共享层 ``GitAnalyzer.commit``；
        执行前用 ``CommandSafetyChecker`` 记录风险等级（git commit 为 medium）。
        """
        message = (message or "").strip()
        if not message:
            return "[提示] 请填写提交信息"
        try:
            from agent_tools import CommandSafetyChecker

            safety = CommandSafetyChecker.analyze(f"git commit -m {message.splitlines()[0]!r}")
            if safety.get("is_dangerous"):
                return "[错误] 提交信息包含危险内容，已拒绝"
            logger.info("git commit 风险等级 %s（用户已确认）", safety.get("risk_level"))
        except BaseException as exc:  # noqa: BLE001
            logger.warning("提交前安全分析失败，按 medium 继续: %s", exc)
        try:
            from git_integration.git_analyzer import GitAnalyzer

            result = GitAnalyzer(repo_path or ".").commit(message)
        except BaseException as exc:  # noqa: BLE001
            return f"[错误] 提交失败: {exc}"
        if not result.get("ok"):
            return f"[错误] 提交失败: {result.get('error') or '未知错误'}"
        return f"[成功] 已提交 {result.get('hash7', '')} · {result.get('subject', '')}".rstrip(" ·")

    def git_overview(self, repo_path: str = ".", max_commits: int = 20) -> Dict[str, Any]:
        """Git 仪表盘数据（结构化，来自共享层 ``GitAnalyzer.get_overview``）。

        返回 ``is_repo / branch / changed / commits / authors / last_commit_at``；
        异常时 ``is_repo=False`` 并附 ``error``。
        """
        try:
            from git_integration.git_analyzer import GitAnalyzer

            return GitAnalyzer(repo_path or ".").get_overview(max_commits=max_commits)
        except BaseException as exc:  # noqa: BLE001
            return {"is_repo": False, "branch": "", "changed": [], "commits": [], "authors": [],
                    "last_commit_at": "", "error": str(exc)}

    # -- 结果流转：用 AI 解读（工具页各子页共用）--

    AI_EXPLAIN_LEADS: Dict[str, str] = {
        "code": "解读下面的代码分析结果，指出最值得关注的问题与下一步。",
        "git": "解读下面的 Git 信息，总结近期改动主题、活跃度与潜在风险。",
        "db": "解读下面的 SQL 与查询结果，说明数据含义与异常值。",
        "shell": "解读下面的命令与输出，说明结果含义与可能的问题。",
        "file": "总结下面文件的用途、结构与关键点。",
    }
    AI_EXPLAIN_MAX_PAYLOAD = 6000
    AI_EXPLAIN_NUM_PREDICT = 768

    def build_explain_prompt(self, kind: str, payload: str, question: str = "") -> str:
        """按 ``kind`` 组装「用 AI 解读」提示词（附录 A-5）；未知 kind 回退 ``code``。"""
        lead = self.AI_EXPLAIN_LEADS.get((kind or "").strip().lower(), self.AI_EXPLAIN_LEADS["code"])
        payload = (payload or "").strip()[: self.AI_EXPLAIN_MAX_PAYLOAD]
        question = (question or "").strip()
        parts = [lead, "内容：", payload]
        if question:
            parts.append(f"问题：{question}")
        parts.append("要求：中文，≤300 字，先结论后依据；有风险或异常先说。")
        return "\n".join(parts)

    def ai_explain_stream(self, kind: str, payload: str, question: str = "") -> Iterator[StreamEvent]:
        """用当前模型解读工具页结果（流式：heartbeat → answer / error / cancelled）。

        经 ``_bridge`` 运行，可被 ``stop_current`` 取消；已有任务在跑时直接产出 ``error``。
        """
        if self.is_running():
            yield StreamEvent("error", "有任务进行中，请先停止或等待完成")
            return
        if not (payload or "").strip():
            yield StreamEvent("error", "没有可解读的内容，请先执行一次操作")
            return
        prompt = self.build_explain_prompt(kind, payload, question)

        def run(q: "queue.Queue", cancel: threading.Event):
            q.put(StreamEvent("progress", "正在解读…"))
            return self._complete_text(prompt, num_predict=self.AI_EXPLAIN_NUM_PREDICT)

        def on_finish(result_holder, error_holder):
            if "error" in error_holder:
                yield StreamEvent("error", f"解读失败: {error_holder['error']}")
                return
            text = str(result_holder.get("result") or "").strip()
            if not text:
                yield StreamEvent("error", "模型没有返回内容")
                return
            yield StreamEvent("answer", text, {"kind": kind})
            yield StreamEvent("done", "")

        yield from self._bridge(run, on_finish)

    # -- 数据库（SQLite；「当前连接」由共享层 database_tools.session 维护，Web / CLI / Agent 共用）--

    DB_MAX_ROWS = 500
    """查询结果最多返回的行数（超出部分截断并在 ``truncated`` 标记）。"""

    @staticmethod
    def _db_session():
        from database_tools import session as db_session

        return db_session

    @staticmethod
    def _db_results():
        """共享层结构化取数模块（Web 与 CLI ``/db-query`` ``/db-schema`` 共用）。"""
        from database_tools import results as db_results

        return db_results

    def db_current(self) -> Dict[str, Any]:
        """当前连接：``{connected, db_type, database, label}``。"""
        try:
            sess = self._db_session()
            cur = sess.get_current()
        except BaseException as exc:  # noqa: BLE001
            return {"connected": False, "db_type": "", "database": "", "label": "", "error": str(exc)}
        if not cur:
            return {"connected": False, "db_type": "", "database": "", "label": ""}
        return {"connected": True, "db_type": cur.get("db_type", ""), "database": cur.get("database", ""),
                "label": sess.describe(cur)}

    def _db_executor(self):
        """当前连接的 ``QueryExecutor``；未连接返回 None。"""
        from database_tools import QueryExecutor

        connector = self._db_session().current_connector()
        return QueryExecutor(connector) if connector is not None else None

    def db_connect(self, database: str, db_type: str = "sqlite") -> str:
        """连接 SQLite 库并设为当前连接（等价 CLI ``/db-connect <database>``）。"""
        database = (database or "").strip()
        if not database:
            return "[提示] 请输入 SQLite 数据库文件路径"
        result = self.run_tool("database_connect", {"db_type": (db_type or "sqlite").strip() or "sqlite",
                                                    "database": database})
        if result.startswith("[成功]"):
            try:
                self.tools_state.remember_database(database)
            except BaseException as exc:  # noqa: BLE001
                logger.warning("记录最近数据库失败: %s", exc)
        return result

    def db_disconnect(self) -> str:
        """断开当前连接（关闭缓存的连接器）。"""
        try:
            self._db_session().clear_current()
            return "[成功] 已断开当前连接"
        except BaseException as exc:  # noqa: BLE001
            return f"[错误] 断开失败: {exc}"

    def db_tables(self) -> Dict[str, Any]:
        """当前库的表名列表：``{tables: [...], error?}``（共享层 ``results.tables_structured``）。"""
        try:
            return self._db_results().tables_structured(self._db_executor())
        except BaseException as exc:  # noqa: BLE001
            return {"tables": [], "error": str(exc)}

    def db_table_schema(self, table: str) -> Dict[str, Any]:
        """单表结构：``{table, columns: [{name, type, not_null, default_value, primary_key}], error?}``。"""
        table = (table or "").strip()
        try:
            return self._db_results().table_schema_structured(self._db_executor() if table else None, table)
        except BaseException as exc:  # noqa: BLE001
            return {"table": table, "columns": [], "error": str(exc)}

    def db_query(self, sql: str) -> Dict[str, Any]:
        """在当前连接上执行只读查询，返回结构化结果（共享层 ``results.query_structured``）。

        ``{sql, columns, rows(list of list), row_count, execution_time, truncated, error?}``；
        ``rows`` 最多 ``DB_MAX_ROWS`` 行。非 SELECT 类语句提示改用「执行」。
        """
        results = self._db_results()
        sql = (sql or "").strip()
        head = results.sql_head(sql)
        if not sql or not head or head not in results.READ_PREFIXES:
            return results.query_structured(None, sql, self.DB_MAX_ROWS)  # 参数校验分支，不需要连接
        try:
            return results.query_structured(self._db_executor(), sql, self.DB_MAX_ROWS)
        except BaseException as exc:  # noqa: BLE001
            return {"sql": sql, "columns": [], "rows": [], "row_count": 0, "execution_time": 0.0,
                    "truncated": False, "error": str(exc)}

    def db_execute(self, sql: str) -> Dict[str, Any]:
        """在当前连接上执行写语句：``{sql, affected_rows, execution_time, error?}``（调用方负责确认）。"""
        results = self._db_results()
        sql = (sql or "").strip()
        if not sql:
            return results.execute_structured(None, sql)
        try:
            return results.execute_structured(self._db_executor(), sql)
        except BaseException as exc:  # noqa: BLE001
            return {"sql": sql, "affected_rows": 0, "execution_time": 0.0, "error": str(exc)}

    def db_schema(self, table: str = "") -> str:
        """文本版表结构 / 表列表（沿用 registry 工具，供 Agent 与旧调用方）。"""
        return self.run_tool("database_get_schema", {"table": (table or "").strip()})

    # -- 自然语言 → SQL（F9 P2-2）--

    DB_NL2SQL_NUM_PREDICT = 256
    DB_NL2SQL_SCHEMA_MAX = 3000

    @classmethod
    def _sql_head(cls, sql: str) -> str:
        """去掉前导 ``--`` 行注释与左括号后的首个关键字（小写）；无内容返回空串（共享层实现）。"""
        return cls._db_results().sql_head(sql)

    @classmethod
    def sql_kind(cls, sql: str) -> str:
        """按首个关键字判定 ``select`` / ``write`` / ``invalid``（空串 / 仅注释亦为 invalid）。"""
        return cls._db_results().sql_kind(sql)

    def db_schema_text(self, max_chars: Optional[int] = None) -> str:
        """当前库全部表的 ``CREATE``-风格文本（供 NL→SQL 提示），截 ``max_chars``。"""
        max_chars = max_chars or self.DB_NL2SQL_SCHEMA_MAX
        tables = self.db_tables().get("tables") or []
        lines: List[str] = []
        for t in tables:
            schema = self.db_table_schema(t)
            cols = ", ".join(
                f"{c.get('name', '')} {c.get('type', '') or ''}".strip() + (" PRIMARY KEY" if c.get("primary_key") else "")
                for c in schema.get("columns") or []
            )
            lines.append(f"{t}({cols})")
        text = "\n".join(lines)
        return text[:max_chars]

    @staticmethod
    def _strip_fences(text: str) -> str:
        """去掉 ``` 围栏（含语言标记）并返回去首尾空白的正文。"""
        import re

        text = (text or "").strip()
        m = re.search(r"```[a-zA-Z0-9_-]*\s*(.*?)```", text, re.DOTALL)
        if m:
            text = m.group(1)
        return text.replace("```", "").strip()

    def db_nl2sql(self, question: str) -> Dict[str, Any]:
        """自然语言 → 一条 SQLite SQL：``{sql, kind, note}``（附录 A-2）。

        ``kind`` 按首个关键字判定 ``select`` / ``write`` / ``invalid``；模型失败或输出不可用时
        ``kind=invalid`` 并在 ``note`` 说明。含高危关键字（DROP / DELETE / ALTER …）时 ``note`` 提示需确认。
        """
        question = (question or "").strip()
        if not question:
            return {"sql": "", "kind": "invalid", "note": "请输入自然语言描述"}
        if not self.db_current().get("connected"):
            return {"sql": "", "kind": "invalid", "note": "尚未连接数据库，请先连接"}
        schema = self.db_schema_text() or "（当前库没有表）"
        prompt = f"你是 SQLite 专家。仅输出一条 SQL，不要解释、不要围栏。\n表结构：\n{schema}\n问题：{question}"
        try:
            raw = self._complete_text(prompt, num_predict=self.DB_NL2SQL_NUM_PREDICT, temperature=0)
        except BaseException as exc:  # noqa: BLE001
            return {"sql": "", "kind": "invalid", "note": f"生成失败: {exc}"}
        sql = self._strip_fences(str(raw or ""))
        # 只保留第一条语句（模型偶尔多输出一条）
        if ";" in sql:
            first = sql.split(";", 1)[0].strip()
            sql = first + ";" if first else sql
        kind = self.sql_kind(sql)
        if kind == "invalid":
            return {"sql": sql, "kind": "invalid", "note": "模型未生成可识别的 SQL，请换个说法或直接手写"}
        note = ""
        try:
            from database_tools.sql_generator import SQLGenerator

            if not SQLGenerator().validate_sql(sql):
                note = "含高危关键字（DROP / DELETE / ALTER …），执行前请仔细确认"
        except BaseException:  # noqa: BLE001
            pass
        if kind == "write" and not note:
            note = "这是写操作，运行前需确认"
        return {"sql": sql, "kind": kind, "note": note}

    # -- 知识图谱构建 --
    def graph_build(self, text: str, doc_id: str = "manual", doc_type: str = "text") -> str:
        text = (text or "").strip()
        if not text:
            return "[提示] 请输入用于构建知识图谱的文本"
        return self.run_tool(
            "knowledge_graph_build",
            {"text": text, "doc_id": doc_id or "manual", "doc_type": doc_type or "text"},
        )

    # 与 CLI ``/graph-query`` 一致的前缀 → query_type 映射
    GRAPH_QUERY_TYPES: Dict[str, str] = {
        "entity": "entity", "type": "type", "neighbors": "neighbors",
        "neighbor": "neighbors", "path": "path", "similar": "similar",
    }
    _CODE_SUFFIXES = {".py", ".js", ".ts", ".java", ".go", ".rs", ".c", ".cpp", ".h",
                      ".hpp", ".rb", ".php", ".cs", ".kt", ".swift"}

    def graph_query_typed(self, query: str, query_type: str = "entity") -> Dict[str, Any]:
        """带类型的图谱查询（entity/type/neighbors/path/similar）。

        与 CLI 一致：``query`` 中若带 ``type:`` / ``neighbors:`` / ``path:`` /
        ``similar:`` / ``entity:`` 前缀，则前缀优先于 ``query_type`` 参数。
        """
        query = (query or "").strip()
        if not query:
            return {"text": "[提示] 查询内容不能为空", "query_type": query_type or "entity"}
        qtype = self.GRAPH_QUERY_TYPES.get((query_type or "entity").strip().lower(), "entity")
        if ":" in query:
            prefix, rest = query.split(":", 1)
            mapped = self.GRAPH_QUERY_TYPES.get(prefix.strip().lower())
            if mapped and rest.strip():
                qtype, query = mapped, rest.strip()
        result = self.run_tool("knowledge_graph_query", {"query": query, "query_type": qtype})
        return {"text": result, "query_type": qtype, "query": query}

    def graph_build_file(self, file_path: str) -> str:
        """读取服务器上的文件构建图谱（等价 CLI ``/graph-build @<文件>``）。

        常见代码后缀使用 ``code`` 抽取策略，其余按 ``text``。
        """
        from pathlib import Path

        file_path = (file_path or "").strip().lstrip("@").strip()
        if not file_path:
            return "[提示] 请输入文件路径"
        path = Path(file_path).expanduser()
        if not path.exists() or not path.is_file():
            return f"[错误] 文件不存在: {file_path}"
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except BaseException as exc:  # noqa: BLE001
            return f"[错误] 读取文件失败: {exc}"
        if not text.strip():
            return f"[提示] 文件内容为空: {file_path}"
        doc_type = "code" if path.suffix.lower() in self._CODE_SUFFIXES else "text"
        return self.graph_build(text, doc_id=path.name, doc_type=doc_type)

    # -- 工具清单 / Shell / 文件读写 / 工作目录（对齐 CLI /tools /exec /file /write /pwd /cd）--

    def list_tools(self) -> List[Dict[str, Any]]:
        """注册表中的全部 Agent 工具：``name / safe / description / parameters``。"""
        try:
            import agent_tools
            out = []
            for name, info in agent_tools.registry.tools.items():
                out.append({
                    "name": name,
                    "safe": bool(info.get("safe", True)),
                    "description": str(info.get("description", "")),
                    "parameters": dict(info.get("parameters", {}) or {}),
                })
            return out
        except BaseException as exc:  # noqa: BLE001
            return [{"name": "[错误]", "safe": True, "description": str(exc), "parameters": {}}]

    def exec_analyze(self, command: str) -> Dict[str, Any]:
        """分析 Shell 命令安全性（等价 CLI ``/exec`` 的前置分析）。

        返回 ``CommandSafetyChecker.analyze`` 的结果：``risk_level / is_dangerous /
        needs_confirm / is_readonly / danger_reasons``。
        """
        command = (command or "").strip()
        if not command:
            return {"error": "命令不能为空"}
        try:
            from agent_tools import CommandSafetyChecker
            return dict(CommandSafetyChecker.analyze(command))
        except BaseException as exc:  # noqa: BLE001
            return {"error": str(exc)}

    @staticmethod
    def exec_succeeded(result: str) -> bool:
        """``exec_run`` 的文本结果是否表示成功（无错误 / 提示前缀且退出码为 0）。"""
        text = result or ""
        if text.startswith("[错误]") or text.startswith("[提示]"):
            return False
        return "\n[退出码] " not in f"\n{text}"

    def exec_run(self, command: str) -> str:
        """执行 Shell 命令；危险命令一律拦截（调用方负责"需确认"的二次确认）。"""
        command = (command or "").strip()
        if not command:
            return "[提示] 命令不能为空"
        safety = self.exec_analyze(command)
        if safety.get("error"):
            return f"[错误] 安全分析失败: {safety['error']}"
        if safety.get("is_dangerous"):
            reasons = "；".join(safety.get("danger_reasons") or [])
            return f"[错误] 该命令被安全系统拦截，拒绝执行。{reasons}".rstrip()
        result = self.run_tool("execute_command", {"command": command}, auto_confirm=True)
        # 命令历史（F9 P3-2）：只记成功执行过的命令（工具层错误 / 提示 / 非零退出码不记）
        if self.exec_succeeded(result):
            try:
                self.tools_state.remember_command(command)
            except BaseException as exc:  # noqa: BLE001
                logger.warning("记录命令历史失败: %s", exc)
        return result

    def write_file(self, path: str, content: str, append: bool = False) -> str:
        """写入文件（等价 CLI ``/write``；调用方负责二次确认）。"""
        path = (path or "").strip()
        if not path:
            return "[提示] 请输入文件路径"
        args: Dict[str, Any] = {"path": path, "content": content or ""}
        if append:
            args["append"] = True
        return self.run_tool("write_file", args, auto_confirm=True)

    # -- 工作区文件浏览（F9 P2-3）：结构化目录 / 预览 / 搜索 --

    DIR_MAX_ENTRIES = 2000
    FILE_PREVIEW_PAGE = 200
    SEARCH_MAX_RESULTS = 50
    SEARCH_MAX_LINE = 200

    def list_dir(self, path: str = ".", show_hidden: bool = False) -> Dict[str, Any]:
        """列出目录：``{path, parent, entries: [{kind, name, size, mtime}], error?}``。

        目录在前、按名排序；``show_hidden=False`` 时跳过以 ``.`` 开头的项；
        路径不存在 / 非目录返回 ``error``（``entries`` 为空）。
        """
        import os
        from datetime import datetime

        raw = (path or ".").strip() or "."
        real = os.path.abspath(os.path.expanduser(raw))
        parent = os.path.dirname(real) if os.path.dirname(real) != real else real
        base = {"path": real, "parent": parent, "entries": []}
        if not os.path.exists(real):
            return {**base, "error": f"路径不存在: {raw}"}
        if not os.path.isdir(real):
            return {**base, "error": f"不是目录: {raw}"}
        dirs: List[Dict[str, Any]] = []
        files: List[Dict[str, Any]] = []
        try:
            with os.scandir(real) as it:
                for entry in it:
                    if not show_hidden and entry.name.startswith("."):
                        continue
                    try:
                        st = entry.stat(follow_symlinks=False)
                        mtime = datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M")
                        size = int(st.st_size)
                    except OSError:
                        mtime, size = "", 0
                    is_dir = entry.is_dir(follow_symlinks=True)
                    item = {"kind": "dir" if is_dir else "file", "name": entry.name,
                            "size": 0 if is_dir else size, "mtime": mtime}
                    (dirs if is_dir else files).append(item)
        except PermissionError:
            return {**base, "error": f"权限不足: {raw}"}
        except OSError as exc:
            return {**base, "error": str(exc)}
        dirs.sort(key=lambda e: e["name"].lower())
        files.sort(key=lambda e: e["name"].lower())
        entries = (dirs + files)[: self.DIR_MAX_ENTRIES]
        return {**base, "entries": entries, "truncated": len(dirs) + len(files) > len(entries)}

    def file_preview(self, path: str, page: int = 0, page_size: Optional[int] = None) -> Dict[str, Any]:
        """分页读取文件：``{path, page, pages, total_lines, start, end, content, error?}``（``page`` 从 0 起）。"""
        import os

        page_size = int(page_size or self.FILE_PREVIEW_PAGE)
        raw = (path or "").strip()
        base = {"path": raw, "page": 0, "pages": 0, "total_lines": 0, "start": 0, "end": 0, "content": ""}
        if not raw:
            return {**base, "error": "请选择文件"}
        real = os.path.expanduser(raw)
        if not os.path.exists(real):
            return {**base, "error": f"文件不存在: {raw}"}
        if os.path.isdir(real):
            return {**base, "error": f"是目录而非文件: {raw}"}
        try:
            with open(real, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()
        except OSError as exc:
            return {**base, "error": f"读取失败: {exc}"}
        total = len(lines)
        pages = max(1, (total + page_size - 1) // page_size)
        page = min(max(int(page or 0), 0), pages - 1)
        start = page * page_size
        end = min(start + page_size, total)
        return {**base, "page": page, "pages": pages, "total_lines": total, "start": start, "end": end,
                "content": "".join(lines[start:end])}

    def search_in_dir(self, query: str, path: str = ".", max_results: Optional[int] = None) -> List[Dict[str, Any]]:
        """在目录下按子串搜索文本文件：``[{file, rel, line, text}]``（最多 ``max_results`` 条）。

        ``file`` 为绝对路径，``rel`` 为相对搜索目录的路径（供表格显示）；
        与 ``agent_tools.search_files`` 同一套后缀 / 跳过目录规则，但返回结构化行。
        """
        import os

        query = (query or "").strip()
        max_results = int(max_results or self.SEARCH_MAX_RESULTS)
        if not query:
            return []
        real = os.path.abspath(os.path.expanduser((path or ".").strip() or "."))
        if not os.path.isdir(real):
            return []
        try:
            from agent_tools import SEARCH_FILE_EXTS as exts, SEARCH_SKIP_DIRS as skip_dirs
        except (ImportError, AttributeError):  # pragma: no cover - 兜底
            exts = {".py", ".js", ".java", ".ts", ".go", ".rs", ".c", ".cpp", ".h", ".md", ".txt", ".json",
                    ".yaml", ".yml", ".sql", ".sh"}
            skip_dirs = {".git", "node_modules", "__pycache__", "venv", ".venv", "dist", "build", ".idea", ".vscode"}
        out: List[Dict[str, Any]] = []
        for root, dirs, files in os.walk(real):
            dirs[:] = sorted(d for d in dirs if d not in skip_dirs and not d.startswith("."))
            for name in sorted(files):
                if not any(name.endswith(ext) for ext in exts):
                    continue
                fp = os.path.join(root, name)
                try:
                    with open(fp, "r", encoding="utf-8", errors="ignore") as f:
                        for no, line in enumerate(f, 1):
                            if query in line:
                                out.append({"file": fp, "rel": os.path.relpath(fp, real), "line": no,
                                            "text": line.strip()[: self.SEARCH_MAX_LINE]})
                                if len(out) >= max_results:
                                    return out
                except OSError:
                    continue
        return out

    # -- 自然语言 → Shell 命令（F9 P2-4）--

    SHELL_GEN_NUM_PREDICT = 128

    def shell_generate(self, intent: str) -> Dict[str, Any]:
        """把自然语言需求转成一条 shell 命令：``{command, note}``（附录 A-3）。

        只取模型输出的第一行、去围栏与 ``$`` 提示符；空输出 ``note="未生成"``。
        生成结果仅回填编辑框，执行仍走 分析 → 确认 流程。
        """
        import os
        import platform

        intent = (intent or "").strip()
        if not intent:
            return {"command": "", "note": "请输入需求描述"}
        os_name = platform.system() or os.name
        prompt = (
            f"把需求转成一条 {os_name} shell 命令。当前目录：{os.getcwd()}。只输出命令本身，一行，不要解释。\n"
            "禁止破坏性操作（rm -rf、格式化、管道到 sh）。\n"
            f"需求：{intent}"
        )
        try:
            raw = self._complete_text(prompt, num_predict=self.SHELL_GEN_NUM_PREDICT, temperature=0)
        except BaseException as exc:  # noqa: BLE001
            return {"command": "", "note": f"生成失败: {exc}"}
        text = self._strip_fences(str(raw or ""))
        first = next((ln.strip() for ln in text.splitlines() if ln.strip()), "")
        if first.startswith("$ "):
            first = first[2:].strip()
        elif first.startswith("$"):
            first = first[1:].strip()
        if not first:
            return {"command": "", "note": "未生成"}
        return {"command": first, "note": ""}

    def cwd(self) -> str:
        """当前工作目录（等价 CLI ``/pwd``；Git / 代码工具默认作用于此）。"""
        import os
        return os.getcwd()

    def chdir(self, path: str) -> str:
        """切换进程工作目录（等价 CLI ``/cd``）。"""
        import os

        path = (path or "").strip()
        if not path:
            return "[提示] 请输入目录路径"
        try:
            os.chdir(os.path.expanduser(path))
            return f"[成功] 已切换到: {os.getcwd()}"
        except FileNotFoundError:
            return f"[错误] 目录不存在: {path}"
        except NotADirectoryError:
            return f"[错误] 不是目录: {path}"
        except PermissionError:
            return f"[错误] 权限不足: {path}"
        except BaseException as exc:  # noqa: BLE001
            return f"[错误] 切换失败: {exc}"

    def env_info(self) -> Dict[str, Any]:
        """运行环境概览（对齐 CLI 启动横幅与 ``/model`` 的附加字段）。"""
        info: Dict[str, Any] = {}
        try:
            import config
            info.update({
                "ollama_url": getattr(config, "OLLAMA_BASE_URL", ""),
                "llm_model": getattr(config, "LLM_MODEL", ""),
                "embed_model": getattr(config, "EMBED_MODEL", ""),
                "num_ctx": getattr(config, "LLM_NUM_CTX", ""),
                "think": bool(getattr(config, "LLM_THINK", False)),
                "auto_confirm_env": bool(getattr(getattr(config, "Config", None), "AUTO_CONFIRM", False)),
                "top_k": getattr(config, "TOP_K", ""),
                "chunk_size": getattr(config, "CHUNK_SIZE", ""),
                "chunk_overlap": getattr(config, "CHUNK_OVERLAP", ""),
                "code_chunking": _code_chunking_env_text(),
                "similarity_cutoff": getattr(config, "SIMILARITY_CUTOFF", ""),
                "kb_relevance_threshold": getattr(config, "KB_RELEVANCE_THRESHOLD", ""),
                "data_dir": str(getattr(config, "DATA_DIR", "")),
                "index_dir": str(getattr(config, "INDEX_DIR", "")),
                "vector_db_path": str(getattr(config, "VECTOR_DB_PATH", "")),
                "session_storage": str(getattr(config, "SESSION_STORAGE_PATH", "")),
                "max_iterations": getattr(config, "MAX_ITERATIONS", ""),
                "timeout": getattr(config, "TIMEOUT", ""),
            })
        except BaseException as exc:  # noqa: BLE001
            info["error"] = str(exc)
        try:
            import os
            info["cwd"] = os.getcwd()
            info["app_version"] = os.environ.get("APP_VERSION", "") or "dev"
        except BaseException:  # noqa: BLE001
            pass
        return info

    # ---------- 文件管理 ----------

    @staticmethod
    def _file_meta_dict(manager, fm) -> Dict[str, Any]:
        try:
            size = manager._format_size(fm.file_size)
        except Exception:  # noqa: BLE001
            size = "?"
        upload = str(getattr(fm, "upload_time", "") or "")
        last = str(getattr(fm, "last_access", "") or "")
        return {
            "path": fm.file_path,
            "size": size,
            "size_bytes": int(getattr(fm, "file_size", 0) or 0),
            "type": str(getattr(fm, "persistence_type", "") or ""),
            "upload_time": upload[:19].replace("T", " "),
            "last_access": last[:19].replace("T", " "),
            "access_count": int(getattr(fm, "access_count", 0) or 0),
            "document_count": int(getattr(fm, "document_count", 0) or 0),
            "chunk_count": int(getattr(fm, "chunk_count", 0) or 0),
            "tags": list(getattr(fm, "tags", None) or []),
            "file_hash": getattr(fm, "file_hash", None),
            "chunk_strategy": str(getattr(fm, "chunk_strategy", "") or "text"),
            "symbol_count": int(getattr(fm, "symbol_count", 0) or 0),
            "chunking": _describe_chunking(fm),
            "chunking_short": _describe_chunking(fm, short=True),
        }

    def file_list(self) -> List[Dict[str, Any]]:
        """列出知识库已登记的文件（等价 /file-list），含类型/时间/片段数等明细。"""
        try:
            from file_metadata import get_global_metadata_manager
            manager = get_global_metadata_manager()
            return [self._file_meta_dict(manager, fm) for fm in manager.list_files()]
        except BaseException as exc:  # noqa: BLE001
            return [{"path": f"[错误] {exc}", "size": ""}]

    def file_info(self, path: str) -> Dict[str, Any]:
        """单个文件的元数据详情（等价 /file-info）。"""
        path = (path or "").strip()
        if not path:
            return {"error": "请输入文件路径"}
        try:
            from file_metadata import get_global_metadata_manager
            manager = get_global_metadata_manager()
            fm = manager.get_file_metadata(path)
            if fm is None:
                return {"error": f"文件不在知识库中: {path}"}
            return self._file_meta_dict(manager, fm)
        except BaseException as exc:  # noqa: BLE001
            return {"error": str(exc)}

    def file_cleanup_preview(self) -> List[Dict[str, Any]]:
        """待清理（临时/过期）文件列表，供二次确认前预览。"""
        try:
            from file_metadata import get_global_metadata_manager
            manager = get_global_metadata_manager()
            return [self._file_meta_dict(manager, fm) for fm in manager.get_files_to_cleanup()]
        except BaseException as exc:  # noqa: BLE001
            return [{"path": f"[错误] {exc}", "size": ""}]

    def file_cleanup(self) -> str:
        """清理临时/过期文件（等价 /file-cleanup）。"""
        try:
            from file_metadata import get_global_metadata_manager
            manager = get_global_metadata_manager()
            pending = manager.get_files_to_cleanup()
            if not pending:
                return "[提示] 没有需要清理的文件"
            cleaned = manager.cleanup_files()
            return f"[成功] 已清理 {len(cleaned)} 个文件"
        except BaseException as exc:  # noqa: BLE001
            return f"[错误] 清理失败: {exc}"

    def file_duplicates(self) -> List[Dict[str, Any]]:
        """按内容哈希找出重复登记的文件（等价 /file-deduplicate 的扫描阶段）。"""
        try:
            from file_metadata import get_global_metadata_manager
            manager = get_global_metadata_manager()
            seen: Dict[str, Any] = {}
            dups = []
            for fm in manager.list_files():
                h = getattr(fm, "file_hash", None)
                if not h:
                    continue
                if h in seen:
                    d = self._file_meta_dict(manager, fm)
                    d["duplicate_of"] = seen[h].file_path
                    dups.append(d)
                else:
                    seen[h] = fm
            return dups
        except BaseException as exc:  # noqa: BLE001
            return [{"path": f"[错误] {exc}", "size": ""}]

    def file_deduplicate(self) -> str:
        """移除重复登记（只删元数据，不删磁盘文件；等价 /file-deduplicate 确认后）。"""
        try:
            from file_metadata import get_global_metadata_manager
            manager = get_global_metadata_manager()
            dups = self.file_duplicates()
            if dups and dups[0].get("path", "").startswith("[错误]"):
                return dups[0]["path"]
            if not dups:
                return "[提示] 没有发现重复文件"
            for d in dups:
                manager.remove_file(d["path"])
            return f"[成功] 已移除 {len(dups)} 个重复登记"
        except BaseException as exc:  # noqa: BLE001
            return f"[错误] 去重失败: {exc}"

    def file_delete_preview(self, path: str) -> Dict[str, Any]:
        """删除文件前的影响预览（片段数 / 图谱节点边数 / 是否同名保留）。"""
        path = (path or "").strip()
        if not path:
            return {"error": "请先选择文件"}
        try:
            return dict(self.rag_engine.file_delete_preview(path))
        except BaseException as exc:  # noqa: BLE001
            return {"error": str(exc)}

    def remove_file(self, path: str) -> str:
        """从知识库删除文件：向量 chunk + 图谱贡献 + 元数据，不删磁盘文件（等价 /file-delete）。"""
        path = (path or "").strip()
        if not path:
            return "[提示] 请先选择要删除的文件"
        try:
            result = self.rag_engine.remove_file(path)
        except FileNotFoundError as exc:
            return f"[错误] {exc}"
        except BaseException as exc:  # noqa: BLE001
            return f"[错误] 删除失败: {exc}"
        name = result.get("file_name") or path.rsplit("/", 1)[-1]
        graph = "图谱已更新" if result.get("graph_updated") else (result.get("note") or "图谱未变更")
        return f"[成功] 已删除 {name}：{result.get('chunks_deleted', 0)} 个片段，{graph}"

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

    def knowledge_summary_data(self) -> List[Dict[str, Any]]:
        """知识库文档摘要的结构化版本（供表格展示）。"""
        try:
            from knowledge_to_skills import KnowledgeToSkillsEngine
            summary = KnowledgeToSkillsEngine().get_document_summary()
            return [
                {
                    "file_name": d.get("file_name", ""),
                    "file_path": d.get("file_path", ""),
                    "kind": "通用" if d.get("is_generic") else "项目",
                    "confidence": float(d.get("confidence", 0) or 0),
                    "chunk_count": int(d.get("chunk_count", 0) or 0),
                    "topics": ", ".join(str(t) for t in (d.get("topics") or [])),
                }
                for d in summary
            ]
        except BaseException as exc:  # noqa: BLE001
            return [{"file_name": f"[错误] {exc}"}]

    def snapshot_list_data(self) -> List[Dict[str, Any]]:
        """快照列表的结构化版本（供表格展示）。"""
        try:
            from knowledge_snapshot import KnowledgeSnapshotManager
            return [
                {
                    "snapshot_id": s.get("snapshot_id", ""),
                    "timestamp": str(s.get("timestamp", "")),
                    "document_count": s.get("document_count", 0),
                    "total_chunks": s.get("total_chunks", 0),
                    "trigger": s.get("trigger", ""),
                }
                for s in KnowledgeSnapshotManager().list_snapshots()
            ]
        except BaseException as exc:  # noqa: BLE001
            return [{"snapshot_id": f"[错误] {exc}"}]

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

    # ---------- 快照：详情 / 恢复 / 删除 / 批量清理 ----------

    @staticmethod
    def _snapshot_manager():
        from knowledge_snapshot import KnowledgeSnapshotManager

        return KnowledgeSnapshotManager()

    def snapshot_info(self, snapshot_id: str) -> Dict[str, Any]:
        """快照详情（文档清单 + 每个文件是否仍在磁盘 + 模型配置 + 触发方式）。"""
        snapshot_id = (snapshot_id or "").strip()
        if not snapshot_id:
            return {"error": "请指定快照 ID"}
        try:
            info = self._snapshot_manager().snapshot_info(snapshot_id)
            return info or {"error": f"快照不存在: {snapshot_id}"}
        except BaseException as exc:  # noqa: BLE001
            return {"error": str(exc)}

    def snapshot_delete(self, snapshot_id: str) -> str:
        """删除单个快照（等价 /snapshot-delete）。"""
        snapshot_id = (snapshot_id or "").strip()
        if not snapshot_id:
            return "[提示] 请指定快照 ID"
        try:
            ok = self._snapshot_manager().delete_snapshot(snapshot_id)
            return f"[成功] 已删除快照 {snapshot_id}" if ok else f"[错误] 快照不存在: {snapshot_id}"
        except BaseException as exc:  # noqa: BLE001
            return f"[错误] 删除快照失败: {exc}"

    def snapshot_prune_preview(self, keep: int = 10) -> List[Dict[str, Any]]:
        """批量清理预览：将被删除的自动快照列表。"""
        try:
            return list(self._snapshot_manager().prune_preview(keep=int(keep or 0), auto_only=True))
        except BaseException as exc:  # noqa: BLE001
            return [{"snapshot_id": f"[错误] {exc}"}]

    def snapshot_prune(self, keep: int = 10) -> str:
        """批量清理自动快照，保留最近 ``keep`` 个（等价 /snapshot-prune）。"""
        try:
            deleted = self._snapshot_manager().prune(keep=int(keep or 0), auto_only=True)
        except BaseException as exc:  # noqa: BLE001
            return f"[错误] 清理失败: {exc}"
        if not deleted:
            return "[提示] 没有需要清理的自动快照"
        return f"[成功] 已清理 {len(deleted)} 个自动快照，保留最近 {int(keep or 0)} 个"

    def snapshot_restore_apply(self, snapshot_id: str, mode: str = "append", progress=None) -> Dict[str, Any]:
        """阻塞式真正恢复快照（``append`` 追加 / ``replace`` 替换）。"""
        snapshot_id = (snapshot_id or "").strip()
        if not snapshot_id:
            return {"ok": False, "error": "请指定快照 ID"}
        try:
            return self._snapshot_manager().restore_apply(
                snapshot_id, self.rag_engine, mode=mode,
                load_documents=self._load_documents, progress=progress,
            )
        except BaseException as exc:  # noqa: BLE001
            return {"ok": False, "error": str(exc)}

    def snapshot_restore_stream(self, snapshot_id: str, mode: str = "append") -> Iterator[StreamEvent]:
        """流式恢复快照：逐文件 ``progress`` 事件 + 最终 ``answer``（data 为结果 dict）。"""
        snapshot_id = (snapshot_id or "").strip()
        if not snapshot_id:
            yield StreamEvent("error", "请指定快照 ID")
            return

        def run(q: "queue.Queue", cancel: threading.Event):
            def progress_cb(evt: Dict[str, Any]):
                q.put(StreamEvent("progress", evt.get("message", ""), evt))

            return self.snapshot_restore_apply(snapshot_id, mode=mode, progress=progress_cb)

        def on_finish(result_holder, error_holder):
            if "error" in error_holder:
                yield StreamEvent("error", f"恢复失败: {error_holder['error']}")
                return
            result = result_holder.get("result") or {}
            if not result.get("ok"):
                yield StreamEvent("error", str(result.get("error") or "恢复失败"))
                return
            yield StreamEvent(
                "answer",
                f"恢复完成：成功 {result.get('restored', 0)}，跳过 {result.get('skipped', 0)}，"
                f"失败 {result.get('failed', 0)}",
                result,
            )

        yield from self._bridge(run, on_finish)

    # ---------- 知识图谱可视化 ----------

    def _graph_builder(self):
        try:
            from knowledge_graph import get_graph_builder
        except ImportError:  # pragma: no cover
            from src.knowledge_graph import get_graph_builder  # type: ignore
        return get_graph_builder()

    def graph_view_data(
        self, types: Optional[List[str]] = None, min_confidence: float = 0.0,
        max_nodes: int = 500, focus: Optional[str] = None, hops: int = 1, dim: int = 3,
    ) -> Dict[str, Any]:
        """可视化子图：节点/边列表 + 每个节点的布局坐标（``positions``）。"""
        try:
            builder = self._graph_builder()
            view = builder.subgraph_for_view(
                types=types, min_confidence=min_confidence, max_nodes=max_nodes,
                focus=focus, hops=hops,
            )
            view["positions"] = builder.layout_positions([n["id"] for n in view["nodes"]], dim=dim)
            view["dim"] = 3 if int(dim or 3) >= 3 else 2
            return view
        except BaseException as exc:  # noqa: BLE001
            return {"nodes": [], "edges": [], "positions": {}, "dim": dim,
                    "total_nodes": 0, "total_edges": 0, "truncated": False, "error": str(exc)}

    def graph_entity_types(self) -> List[str]:
        """图谱中出现过的实体类型（按数量倒序），供筛选控件使用。"""
        try:
            stats = self._graph_builder().get_statistics()
            return [k for k, _ in sorted(stats.entity_types.items(), key=lambda kv: -kv[1])]
        except BaseException:  # noqa: BLE001
            return []

    # ---------- 会话高级 ----------

    def session_info(self, session_id: str = "") -> Dict[str, Any]:
        """获取会话详情（等价 /session-info、/session-current）。

        空 ID 表示当前会话；非空时先精确匹配，再按 CLI 的子串匹配兜底。
        返回 ``session_id/title/status/created_at/updated_at/messages/tags/metadata``。
        """
        try:
            session_id = (session_id or "").strip()
            session = None
            if session_id:
                getter = getattr(self.session_manager, "get_session", None)
                if callable(getter):
                    session = getter(session_id)
                if session is None:
                    session = next(
                        (s for s in self.session_manager.list_sessions()
                         if session_id in getattr(s, "session_id", "")),
                        None,
                    )
            else:
                session = self.session_manager.get_current_session()
            if session is None:
                return {"error": "未找到会话"}
            status = getattr(getattr(session, "status", None), "value", "") or ""
            return {
                "session_id": session.session_id,
                "title": session.title,
                "status": status if isinstance(status, str) else "",
                "created_at": self._fmt_time(getattr(session, "created_at", None)),
                "updated_at": self._fmt_time(getattr(session, "updated_at", None)),
                "messages": len(getattr(session, "messages", [])),
                "tags": list(getattr(session, "tags", None) or []),
                "metadata": dict(getattr(session, "metadata", None) or {}),
            }
        except BaseException as exc:  # noqa: BLE001
            return {"error": str(exc)}

    def delete_session(self, session_id: str) -> str:
        """删除指定会话（等价 /session-delete）。与 CLI 一致：不允许删除当前会话。"""
        session_id = (session_id or "").strip()
        if not session_id:
            return "[提示] 请先选择要删除的会话"
        try:
            current = self.session_manager.get_current_session()
            if current is not None and getattr(current, "session_id", None) == session_id:
                return "[提示] 不能删除当前会话，请先切换到其他会话"
            deleter = getattr(self.session_manager, "delete_session", None)
            if not callable(deleter):
                return "[错误] 当前会话管理器不支持删除"
            ok = deleter(session_id)
            return f"[成功] 已删除会话 {session_id[:8]}" if ok else f"[错误] 会话不存在: {session_id[:8]}"
        except BaseException as exc:  # noqa: BLE001
            return f"[错误] 删除会话失败: {exc}"

    def archive_session(self, session_id: str) -> str:
        """归档指定会话（等价 /session-archive）。"""
        session_id = (session_id or "").strip()
        if not session_id:
            return "[提示] 请先选择要归档的会话"
        try:
            ok = bool(self.session_manager.archive_session(session_id))
            return f"[成功] 已归档会话 {session_id[:8]}" if ok else f"[错误] 会话不存在: {session_id[:8]}"
        except BaseException as exc:  # noqa: BLE001
            return f"[错误] 归档会话失败: {exc}"


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
