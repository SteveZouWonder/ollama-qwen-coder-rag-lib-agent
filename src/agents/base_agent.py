"""
Agent基类 - 多Agent系统的核心抽象
"""
from abc import ABC, abstractmethod
from datetime import datetime
from typing import List, Dict, Any, Optional, Callable, Set
import threading
import time
import logging
from .agent_types import AgentTask, AgentResult, AgentMessage, AgentType, AgentState

try:  # 共享层的自动确认闸门（agent_tools 不可用时退化为本地默认值）
    from agent_tools import AUTO_CONFIRM_RISK_LEVELS as _SHARED_AUTO_CONFIRM_RISK_LEVELS
except ImportError:  # pragma: no cover - 仅在裁剪部署缺少 agent_tools 时触发
    _SHARED_AUTO_CONFIRM_RISK_LEVELS = ("low", "medium")


class BaseAgent(ABC):
    """Agent基类，定义所有Agent的通用接口和行为"""
    
    def __init__(self, agent_id: str, agent_type: AgentType, 
                 capabilities: List[str], config: Dict[str, Any] = None):
        """
        初始化Agent
        
        Args:
            agent_id: Agent唯一标识符
            agent_type: Agent类型
            capabilities: Agent能力列表
            config: 额外配置
        """
        self.agent_id = agent_id
        self.agent_type = agent_type
        self.capabilities = capabilities
        self.config = config or {}
        self.state = AgentState.IDLE
        self.message_handlers: Dict[str, Callable] = {}
        self.message_bus = None
        self.logger = logging.getLogger(f"Agent.{agent_id}")
        # 协调者注入的进度回调（子任务内部步骤上报）；None 表示不上报
        self.on_progress: Optional[Callable[[Dict[str, Any]], None]] = None
        
    def set_message_bus(self, message_bus):
        """设置消息总线"""
        self.message_bus = message_bus
        
    @abstractmethod
    def process_task(self, task: AgentTask) -> AgentResult:
        """
        处理任务（子类必须实现）
        
        Args:
            task: 要处理的任务
            
        Returns:
            AgentResult: 执行结果
        """
        pass
    
    def can_handle(self, task: AgentTask) -> bool:
        """
        判断是否能处理该任务
        
        Args:
            task: 任务对象
            
        Returns:
            bool: 是否能处理
        """
        if self.state != AgentState.IDLE:
            return False
            
        required = set(task.required_capabilities)
        available = set(self.capabilities)
        return required.issubset(available)
    
    def get_capabilities(self) -> List[str]:
        """获取能力列表"""
        return self.capabilities.copy()
    
    def get_state(self) -> AgentState:
        """获取Agent状态"""
        return self.state
    
    def set_state(self, state: AgentState):
        """设置Agent状态"""
        self.state = state
        self.logger.debug(f"Agent {self.agent_id} state changed to {state}")
    
    def register_message_handler(self, message_type: str, handler: Callable[[AgentMessage], None]):
        """
        注册消息处理器
        
        Args:
            message_type: 消息类型
            handler: 处理函数
        """
        self.message_handlers[message_type] = handler
        self.logger.debug(f"Registered handler for message type: {message_type}")
    
    def handle_message(self, message: AgentMessage):
        """
        处理接收到的消息
        
        Args:
            message: 消息对象
        """
        handler = self.message_handlers.get(message.message_type)
        if handler:
            try:
                handler(message)
            except Exception as e:
                self.logger.error(f"Error handling message {message.message_type}: {e}")
        else:
            self.logger.warning(f"No handler registered for message type: {message.message_type}")
    
    def send_message(self, to_agent: str, message_type: str, content: Dict[str, Any]):
        """
        发送消息给其他Agent
        
        Args:
            to_agent: 目标Agent ID
            message_type: 消息类型
            content: 消息内容
        """
        if self.message_bus:
            message = AgentMessage(
                from_agent=self.agent_id,
                to_agent=to_agent,
                message_type=message_type,
                content=content
            )
            self.message_bus.publish(message)
        else:
            self.logger.warning("Message bus not set, cannot send message")
    
    # ---------- 进度 / 取消 钩子 ----------

    def emit_progress(self, event: Dict[str, Any]) -> None:
        """把子 Agent 内部进度（如 ReAct 步骤）上报给协调者；回调缺失或抛错都忽略。"""
        cb = getattr(self, "on_progress", None)
        if cb is None:
            return
        try:
            event = dict(event)
            event.setdefault("agent_id", self.agent_id)
            cb(event)
        except Exception:  # noqa: BLE001 - 进度回调失败不影响任务
            pass

    def cancel(self) -> None:
        """请求中止当前任务（超时时由 ``execute_task_with_timeout`` 调用）。子类可覆盖。"""
        engine = getattr(self, "_active_engine", None)
        stop = getattr(engine, "stop", None)
        if callable(stop):
            try:
                stop()
            except Exception:  # noqa: BLE001
                pass

    def execute_task_with_timeout(self, task: AgentTask, timeout: Optional[float] = None) -> AgentResult:
        """
        在工作线程中执行任务并真正按超时时间返回。

        超时后调用 ``cancel()`` 通知任务中止，返回 ``success=False,
        error_message="timeout"``。无论成功、失败还是超时，Agent 状态都恢复为
        IDLE，避免一次失败后该 Agent 永久不可调度。
        
        Args:
            task: 任务对象
            timeout: 超时时间（秒），如果为None则使用任务的timeout
            
        Returns:
            AgentResult: 执行结果
        """
        # 优先级：显式参数 > Agent 配置（AgentConfig.timeout）> 任务默认值
        timeout = timeout or self.config.get("timeout") or task.timeout
        start_time = time.time()
        
        self.set_state(AgentState.BUSY)
        task.status = task.status.__class__.RUNNING
        task.started_at = datetime.now()

        holder: Dict[str, Any] = {}
        # F10 P2-1-d：观测工作线程在 LLM 并发信号量上的排队时间——排队不计入超时，
        # 并向协调者上报"排队中"（首次排队追加一行，之后只刷新当前状态）
        tracker = self._make_queue_tracker()

        def _worker():
            self._install_queue_listener(tracker)
            try:
                holder["result"] = self.process_task(task)
            except Exception as e:  # noqa: BLE001
                holder["error"] = e
            finally:
                self._install_queue_listener(None)

        worker = threading.Thread(
            target=_worker, name=f"{self.agent_id}-task", daemon=True)
        worker.start()
        self._join_excluding_queue(worker, timeout, start_time, tracker)

        execution_time = time.time() - start_time
        queued = round(tracker.total(), 2) if tracker is not None else 0.0
        try:
            if worker.is_alive():
                self.logger.warning(
                    f"Task {task.task_id} timed out after {timeout}s"
                    + (f" (excluding {queued}s queued for LLM)" if queued else ""))
                self.cancel()
                task.status = task.status.__class__.FAILED
                meta: Dict[str, Any] = {"timeout": timeout}
                if queued:
                    meta["queued_seconds"] = queued
                return AgentResult(
                    task_id=task.task_id,
                    agent_id=self.agent_id,
                    success=False,
                    output="",
                    metadata=meta,
                    execution_time=execution_time,
                    error_message="timeout",
                )

            if "error" in holder:
                e = holder["error"]
                self.logger.error(f"Task execution failed: {e}")
                task.status = task.status.__class__.FAILED
                return AgentResult(
                    task_id=task.task_id,
                    agent_id=self.agent_id,
                    success=False,
                    output="",
                    metadata={},
                    execution_time=execution_time,
                    error_message=str(e),
                )

            result = holder.get("result")
            if result is None:
                task.status = task.status.__class__.FAILED
                return AgentResult(
                    task_id=task.task_id, agent_id=self.agent_id, success=False,
                    output="", metadata={}, execution_time=execution_time,
                    error_message="process_task 未返回结果",
                )
            result.execution_time = execution_time
            if queued:
                try:
                    result.metadata["queued_seconds"] = queued
                except Exception:  # noqa: BLE001 - metadata 非 dict 时忽略
                    pass
            if result.success:
                task.status = task.status.__class__.COMPLETED
                task.completed_at = datetime.now()
            else:
                task.status = task.status.__class__.FAILED
            return result
        finally:
            # 失败/超时后恢复 IDLE：状态只表示"当前是否在忙"，不记录历史错误
            self.set_state(AgentState.IDLE)

    # ---------- LLM 排队观测（F10 P2-1-d）----------

    # 超时轮询步长：等待期间每隔这么久重新计算剩余预算（排队时间实时剔除）
    _JOIN_POLL_SECONDS = 0.25

    def _make_queue_tracker(self):
        """构造排队观测器；``llm_client`` 不可用时返回 None（行为退化为原来的单次 join）。"""
        try:
            from llm_client import QueueWaitTracker
        except Exception:  # noqa: BLE001
            return None
        state = {"announced": False}

        def on_change(waiting: bool, waited_total: float) -> None:
            if waiting:
                first = not state["announced"]
                state["announced"] = True
                try:
                    from llm_client import max_concurrency
                    limit = max_concurrency()
                except Exception:  # noqa: BLE001
                    limit = 0
                hint = f"（并发上限 {limit}）" if limit > 0 else ""
                event = {
                    "stage": "agent_step",
                    "message": f"[{self.agent_id}] ⏳ 排队等待模型空闲{hint}…",
                    "phase": "queued",
                }
                if not first:
                    event["transient"] = True
                self.emit_progress(event)
            else:
                self.emit_progress({
                    "stage": "agent_step",
                    "message": f"[{self.agent_id}] 模型已就位，继续执行（已排队 {waited_total:.1f}s）",
                    "phase": "queued_done",
                    "transient": True,
                })

        return QueueWaitTracker(on_change=on_change)

    @staticmethod
    def _install_queue_listener(tracker) -> None:
        try:
            from llm_client import set_queue_listener
            set_queue_listener(tracker)
        except Exception:  # noqa: BLE001
            pass

    def _join_excluding_queue(self, worker: threading.Thread, timeout, start_time: float, tracker) -> None:
        """等待工作线程；超时预算 = ``timeout`` + 已在 LLM 信号量上排队的时间（排队不计入超时）。"""
        if not timeout or timeout <= 0:
            worker.join()
            return
        if tracker is None:
            worker.join(timeout)
            return
        while worker.is_alive():
            remaining = float(timeout) + tracker.total() - (time.time() - start_time)
            if remaining <= 0:
                return
            worker.join(min(remaining, self._JOIN_POLL_SECONDS))
    
    def __repr__(self):
        return f"BaseAgent(id={self.agent_id}, type={self.agent_type}, state={self.state})"


class EphemeralContext:
    """子 Agent 专用的一次性会话上下文：只提供系统提示，不读写用户会话。

    多 Agent 子任务的中间往返不应污染用户的"当前会话"（那由协调层统一记录
    一条"请求 + 综合回答"）。
    """

    def build_messages(self, system_prompt: Optional[str] = None) -> List[Dict[str, str]]:
        return [{"role": "system", "content": system_prompt or ""}]

    def record(self, *args, **kwargs) -> None:  # noqa: D401 - 空实现
        return None

    def clear(self) -> bool:
        return True


class ReActDelegateAgent(BaseAgent):
    """把子任务委托给一个受限工具集的 ``ReActEngine`` 执行的专业 Agent 基类。

    子类只需声明：
    - ``ROLE_PROMPT``：角色附加提示（≤200 token）
    - ``ALLOWED_TOOLS``：该角色可用的工具名白名单
    - ``TASK_TYPE_HINTS``：``task_type -> 一句任务要求``（可选）

    ``config`` 支持 ``model`` / ``max_iterations`` / ``allowed_tools`` /
    ``engine_factory``（测试注入）。
    """

    ROLE_PROMPT: str = ""
    ALLOWED_TOOLS: Set[str] = set()
    TASK_TYPE_HINTS: Dict[str, str] = {}
    # 角色"必须至少用过其一"的关键工具：一次都没执行，说明模型只是在口头描述
    # （如声称已写测试文件却从未 write_file）。此时结果标记 unverified 并在输出
    # 前加注，避免协调层/用户把未验证的自述当成事实。空集表示不检查。
    ESSENTIAL_TOOLS: Set[str] = set()
    UNVERIFIED_NOTE = "⚠️ 该 Agent 未实际调用 {tools} 等工具，以下内容为模型自述、未经验证：\n\n"
    # 每步 Observation 最多带回协调层的字符数（避免整合 prompt 爆掉）
    OUTPUT_LIMIT = 6000

    def __init__(self, agent_id: str, agent_type: AgentType,
                 capabilities: List[str], config: Dict[str, Any] = None):
        super().__init__(agent_id=agent_id, agent_type=agent_type,
                         capabilities=capabilities, config=config or {})
        self._active_engine = None

    # ---------- 引擎 ----------

    def allowed_tools(self) -> Set[str]:
        tools = self.config.get("allowed_tools")
        return set(tools) if tools else set(self.ALLOWED_TOOLS)

    # execute_command 允许自动放行的风险等级（更高等级一律拒绝）。
    # 与共享层 agent_tools.AUTO_CONFIRM_RISK_LEVELS 同一口径，避免两处漂移。
    AUTO_CONFIRM_RISK_LEVELS = _SHARED_AUTO_CONFIRM_RISK_LEVELS

    def _auto_confirm(self, evt: Dict[str, Any]) -> bool:
        """子 Agent 无交互界面，确认策略必须是确定性的：

        - 工具在角色白名单内（如 write_file）→ 放行：白名单本身就是授权；
        - ``execute_command`` 只放行 low/medium 风险（危险命令在此之前已被拦截，
          high/critical 一律拒绝，由模型改用安全方式或说明原因）。
        此前一律拒绝会导致 Code/Test Agent 永远写不了文件，模型进而编造"已完成"。
        """
        tool = evt.get("tool")
        if tool == "execute_command":
            safety = evt.get("safety")
            if not safety:
                # registry 的 [CONFIRM_REQUIRED] 路径不带 safety，这里自行分析命令
                cmd = evt.get("command") or (evt.get("args") or {}).get("command", "")
                if not str(cmd or "").strip():
                    return False
                try:
                    from agent_tools import CommandSafetyChecker
                    safety = CommandSafetyChecker.analyze(str(cmd or ""))
                except Exception:  # noqa: BLE001
                    safety = {}
            if safety.get("is_dangerous"):
                return False
            return safety.get("risk_level", "unknown") in self.AUTO_CONFIRM_RISK_LEVELS
        return tool in self.allowed_tools()

    def _make_engine(self):
        """构造受限 ReActEngine；``config["engine_factory"]`` 可替换（测试用）。"""
        factory = self.config.get("engine_factory")
        kwargs = dict(
            model=self.config.get("model"),
            host=self.config.get("host"),
            allowed_tools=self.allowed_tools(),
            system_prompt_extra=self.ROLE_PROMPT,
            max_iterations=self.config.get("max_iterations"),
            context=EphemeralContext(),
            on_step=self._on_engine_step,
            on_confirm=self._auto_confirm,
            # 子角色默认只用精简内置提示 + Skills 层（项目附加规范面向单 Agent 的完整任务，
            # 子任务不需要）；Skills 按角色名过滤（prompts/skills/*/SKILL.md 的 roles）。
            prompt_mode=self.config.get("prompt_mode", "builtin"),
            role=str(self.agent_type),
        )
        if factory is not None:
            return factory(**kwargs)
        from react_engine import ReActEngine
        return ReActEngine(**kwargs)

    def _on_engine_step(self, evt: Dict[str, Any]) -> None:
        """把 ReAct 步骤转发为协作进度：推理心跳只刷新当前状态（transient），
        每步完成/拦截/拒绝各追加一行，避免刷屏。"""
        phase = evt.get("phase")
        if evt.get("transient") or phase in ("executing", "context"):
            return
        event = {
            "stage": "agent_step",
            "message": f"[{self.agent_id}] {evt.get('message', '')}",
            "step": evt.get("step"),
            "phase": phase,
        }
        if phase == "thinking":
            event["transient"] = True
        self.emit_progress(event)

    # ---------- 任务 ----------

    def build_prompt(self, task: AgentTask) -> str:
        """把子任务组装成给 ReAct 引擎的用户输入。"""
        data = task.input_data or {}
        request = (data.get("request") or task.description or "").strip()
        parts = [f"子任务：{request}" if request else "子任务：（未提供描述）"]
        hint = self.TASK_TYPE_HINTS.get(task.task_type)
        if hint:
            parts.append(f"要求：{hint}")
        original = (data.get("original_request") or "").strip()
        if original and original != request:
            parts.append(f"用户原始请求（仅供理解背景，只需完成上面的子任务）：{original}")
        upstream = data.get("upstream") or []
        if upstream:
            lines = ["前置子任务的结果（可直接使用）："]
            for item in upstream[:3]:
                desc = str(item.get("description", ""))[:120]
                out = str(item.get("output", ""))[:800]
                lines.append(f"- {desc}\n  结果：{out}")
            parts.append("\n".join(lines))
        parts.append("完成后用 Final Answer 给出结果：做了什么、产出文件/结论、未完成项。")
        return "\n\n".join(parts)

    def process_task(self, task: AgentTask) -> AgentResult:
        start_time = time.time()
        engine = None
        try:
            engine = self._make_engine()
            self._active_engine = engine
            answer = str(engine.chat(self.build_prompt(task)) or "").strip()
            step_log = list(getattr(engine, "step_log", []) or [])
            tools = []
            for log in step_log:
                # 只统计真正执行了的工具（被白名单/安全拦截/拒绝的不算）
                if (log.get("phase") == "action" and log.get("tool")
                        and log.get("confirmed", True) and log["tool"] not in tools):
                    tools.append(log["tool"])
            failed = (
                not answer
                or answer.startswith("[错误]")
                or answer.startswith("[用户中断]")
            )
            incomplete = answer.startswith("[警告]") or answer.startswith("⚠️")
            unverified = bool(
                not failed and self.ESSENTIAL_TOOLS
                and not (set(tools) & set(self.ESSENTIAL_TOOLS))
            )
            output = answer
            if unverified:
                output = self.UNVERIFIED_NOTE.format(
                    tools="/".join(sorted(self.ESSENTIAL_TOOLS))) + answer
            return AgentResult(
                task_id=task.task_id,
                agent_id=self.agent_id,
                success=not failed,
                output=output[: self.OUTPUT_LIMIT],
                metadata={
                    "task_type": task.task_type,
                    "handled_by": type(self).__name__,
                    "steps": len([l for l in step_log if l.get("phase") == "action"]),
                    "tools": tools,
                    "incomplete": incomplete,
                    "unverified": unverified,
                    "step_log": step_log,
                },
                execution_time=time.time() - start_time,
                error_message=answer if failed else "",
            )
        except Exception as e:  # noqa: BLE001
            self.logger.error(f"Error processing task: {e}")
            return AgentResult(
                task_id=task.task_id,
                agent_id=self.agent_id,
                success=False,
                output="",
                metadata={"task_type": task.task_type},
                execution_time=time.time() - start_time,
                error_message=str(e),
            )
        finally:
            self._active_engine = None
