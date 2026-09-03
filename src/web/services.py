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
import time
from typing import Any, Callable, Dict, Iterator, List, Optional, Tuple


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


def _default_react_factory(on_step=None, on_confirm=None, context=None):
    """创建一个 ReActEngine（模型取自 config.LLM_MODEL，热切换后自动跟随）。

    ``context`` 为本次对话绑定的会话上下文（每个浏览器标签页有自己的会话）。
    """
    from react_engine import ReActEngine

    return ReActEngine(on_step=on_step, on_confirm=on_confirm, context=context)


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

    # ---------- 多 Agent 协作 ----------

    def _run_orchestrator(self, request: str, mode: Optional[str], progress=None) -> Dict[str, Any]:
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
            if progress is not None:
                return orchestrator.process_request(request, resolved, progress=progress)
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
            result = self._run_orchestrator(effective, mode, progress=progress_cb)
            if not isinstance(result, dict):
                result = {"success": False, "summary": str(result)}
            summary = str(result.get("summary", ""))
            recorded = summary if result.get("success") else f"[协作失败] {summary}"
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
            yield StreamEvent("answer", str(result.get("summary", "")), result)

        yield from self._bridge(run, on_finish)

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

    def add_path(self, path: str, file_types: Optional[str] = None) -> str:
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
            self.rag_engine.add_documents(docs, [path])
        except BaseException as exc:  # noqa: BLE001
            return f"[错误] 入库失败: {exc}"
        graph_note = (
            "，已同步更新知识图谱"
            if getattr(self.rag_engine, "last_graph_derived", False)
            else "，知识图谱未自动更新（可在「知识图谱」页手动构建）"
        )
        return f"[成功] 已追加入库 {len(docs)} 个片段{graph_note}"

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

    # -- 数据库（写操作）--
    @staticmethod
    def _parse_json_object(raw: str, what: str) -> Tuple[Optional[Dict[str, Any]], str]:
        import json

        raw = (raw or "").strip() or "{}"
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            return None, f"[错误] {what}必须是有效的 JSON 对象: {exc}"
        if not isinstance(data, dict):
            return None, f"[错误] {what}必须是 JSON 对象（{{...}}）"
        return data, ""

    def db_create_table(self, table: str, columns_json: str) -> str:
        """创建表（等价 CLI ``/db-create-table``；列定义为 JSON 对象）。"""
        table = (table or "").strip()
        if not table:
            return "[提示] 请输入表名"
        columns, err = self._parse_json_object(columns_json, "列定义")
        if err:
            return err
        return self.run_tool(
            "database_create_table", {"table": table, "columns": columns}, auto_confirm=True,
        )

    def db_insert(self, table: str, data_json: str) -> str:
        """插入一行数据（等价 CLI ``/db-insert``；数据为 JSON 对象）。"""
        table = (table or "").strip()
        if not table:
            return "[提示] 请输入表名"
        data, err = self._parse_json_object(data_json, "数据")
        if err:
            return err
        return self.run_tool("database_insert", {"table": table, "data": data}, auto_confirm=True)

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
        return self.run_tool("execute_command", {"command": command}, auto_confirm=True)

    def read_file(self, path: str, offset: int = 0, limit: int = 200) -> str:
        """直接读取文件内容（不经过模型，等价 CLI ``/file``）。"""
        path = (path or "").strip()
        if not path:
            return "[提示] 请输入文件路径"
        args: Dict[str, Any] = {"path": path}
        try:
            if int(offset or 0) > 0:
                args["offset"] = int(offset)
            if limit:
                args["limit"] = int(limit)
        except (TypeError, ValueError):
            pass
        return self.run_tool("read_file", args, auto_confirm=True)

    def write_file(self, path: str, content: str, append: bool = False) -> str:
        """写入文件（等价 CLI ``/write``；调用方负责二次确认）。"""
        path = (path or "").strip()
        if not path:
            return "[提示] 请输入文件路径"
        args: Dict[str, Any] = {"path": path, "content": content or ""}
        if append:
            args["append"] = True
        return self.run_tool("write_file", args, auto_confirm=True)

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
