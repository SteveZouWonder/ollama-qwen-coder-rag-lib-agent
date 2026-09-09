"""Web 服务层骨架：引擎工厂、流式事件、任务生命周期与 ``_bridge``。

``web.services`` 包是 Web 界面唯一与核心引擎（RAGEngine / ReActEngine / AgentOrchestrator /
SessionManager / GraphQuery）交互的地方。UI 层（``app.py`` / ``handlers``）只调用本包暴露的
方法，不直接 import 引擎，从而：

1. 让业务编排逻辑可独立于 Gradio 做单元测试（本包不 import gradio）。
2. 把引擎的"回调式"进度（``progress_callback`` / ``on_step``）桥接为 Gradio
   友好的"可迭代式"流式事件。

为便于测试，所有重量级引擎均通过可注入的工厂函数惰性创建（依赖注入）。

本模块只含 ``WebServiceBase``（状态、取消、确认、``_bridge``、惰性单例）；各功能面
以 mixin 形式放在同包的 ``chat`` / ``knowledge`` / ``tools`` / ``db`` / ``graph`` / ``system``
模块，由 ``__init__`` 组合成 ``WebService``（F10 P2-2）。
"""
from __future__ import annotations

import logging
import queue
import threading
import time
from typing import Any, Callable, Dict, Iterator, List, Optional

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

    - ``kind``：``progress`` | ``answer`` | ``step`` | ``token`` | ``error`` | ``done`` |
      ``heartbeat`` | ``cancelled`` | ``confirm``
    - ``message``：人类可读文本
    - ``data``：附加结构化数据（如 sources 列表、step_log 等）

    ``token``（F10 P1-1）：最终答案的一段增量文本（``message`` 为 delta），UI 逐段拼接到
    Chatbot 最后一条消息；随后仍会收到携带完整文本的 ``answer``，以 ``answer`` 为准。
    ``heartbeat`` 在后台任务长时间无新事件（含 token）时按固定间隔发出（``data`` 含
    ``elapsed`` 秒数），让 UI 能刷新"已用时"，消除"卡死"错觉。
    ``cancelled`` 表示用户主动停止，任务未产出最终结果。
    ``confirm`` 为单 Agent 危险操作的审批请求（``data`` 含命令与风险等级）。
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

class WebServiceBase:
    """Web 界面服务层骨架（状态 / 取消 / 确认 / 流式桥接 / 惰性单例）。

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
            from ..tools_state import ToolsState

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

        - 置位当前运行的取消信号：RAG 编排在阶段边界（及流式综合的每个 token 之间）
          看到后中止，桥接生成器立刻停止转发并产出 ``cancelled`` 事件。
        - 若单 Agent 引擎在跑，同时调用其 ``stop()``（会关闭正在流式读取的 HTTP
          响应，模型端随之停止生成；F10 P1-1）。

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

    @staticmethod
    def _token_sink(q: "queue.Queue", cancel: threading.Event) -> Callable[[str], None]:
        """构造 ``on_token`` 回调：把每段增量作为 ``token`` 事件入队；取消后丢弃（F10 P1-1）。"""
        def on_token(delta: str) -> None:
            if delta and not cancel.is_set():
                q.put(StreamEvent("token", delta))
        return on_token

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
        - 队列 ``get`` 带超时，仅在 ``heartbeat_interval`` 内**没有任何事件**（含
          ``token``）时产出 ``heartbeat``（含 ``elapsed``）；流式输出期间不发心跳。
        - 每次循环检查取消信号；命中则产出 ``cancelled`` 并停止转发（后台
          线程为 daemon，继续跑完当前阻塞调用后自行退出，其结果被丢弃；单 Agent
          的流式读取会被 ``stop()`` 立刻关闭连接）。
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
