"""对话页：会话上下文、RAG / 单 Agent / 自动路由 / 多 Agent 流式对话、会话管理。"""
from __future__ import annotations

import logging
import queue
import threading
from typing import Any, Callable, Dict, Iterator, List, Optional, Tuple

from .base import StreamEvent

logger = logging.getLogger(__name__)


class ChatMixin:
    """三种对话模式的流式编排与会话管理（对齐 CLI ``/ask`` ``/agent`` ``/multi`` ``/session-*``）。"""

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
                on_token=self._token_sink(q, cancel),
            )
            # 对话落库（与 CLI 一致）：即使是元查询也记录，便于历史回看。
            # 在后台线程内完成，压缩期间心跳仍可刷新 UI。
            # F9 P0-5：记录正文 + warn 级 notice 各一行（后续轮次据此知道上一答是否有依据）
            if result.get("kind") == "meta":
                recorded = "[知识库概览]"
            else:
                recorded = rag_pipeline.answer_with_notices(result.get("answer", ""), result.get("notices"))
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
                    "challenge": bool(result.get("challenge")),
                    "context": result.get("context") or {},
                    # kind="fallback" 时附原问题，供 UI「用单 Agent 重试」
                    "fallback_question": result.get("fallback_question"),
                    # F9：结构化提示 / 引用校验 / 本次作答模型
                    "notices": result.get("notices") or [],
                    "citation_check": result.get("citation_check"),
                    "model": result.get("model"),
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
            # F10 P1-1：Final Answer 增量以 token 事件推给 UI（工具调用轮不产生 token）
            answer = engine.chat(user_input, on_token=self._token_sink(q, cancel))
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
            return getattr(self.rag_engine, "retriever", None) is not None
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
                          context=None, on_token=None) -> Dict[str, Any]:
        """创建编排器执行一次协作请求，结束后释放；异常转为失败 dict。

        ``on_token``（F10 P1-1）透传给编排器：仅整合阶段的模型综合流式回调。
        """
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
            if on_token is not None:
                kwargs["on_token"] = on_token
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
            effective, rewritten, challenge = request, None, False
            try:
                rw = ctx.rewrite_question(request, progress=progress_cb)
                challenge = bool(rw.get("challenge"))
                if rw.get("changed"):
                    effective = rw["question"]
                    rewritten = effective
            except Exception:  # noqa: BLE001 - 改写失败沿用原请求
                pass
            result = self._run_orchestrator(effective, mode, progress=progress_cb, context=ctx,
                                            on_token=self._token_sink(q, cancel))
            if not isinstance(result, dict):
                result = {"success": False, "summary": str(result)}
            summary = str(result.get("summary", ""))
            # 会话记录面向用户的综合回答（answer），而不是统计句
            answer = str(result.get("answer") or "").strip() or summary
            recorded = answer if result.get("success") else f"[协作失败] {answer}"
            result["rewritten"] = rewritten
            result["challenge"] = challenge
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
