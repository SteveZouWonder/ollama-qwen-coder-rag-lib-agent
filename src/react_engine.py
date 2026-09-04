#!/usr/bin/env python3
"""
ReAct 推理引擎 - 带迭代可视化和安全确认
适配本地小模型（默认 qwen3.5:4b），集成 RAG 知识库工具
"""
import re
import ast
import json
import requests
import threading
import os
from typing import List, Dict, Callable, Optional, Tuple

from config import Config
from agent_tools import registry, CommandSafetyChecker


def read_system_prompt_from_file():
    """
    从 .devin/SYSTEM_PROMPT.md 读取项目附加规范
    如果文件不存在，返回None
    """
    prompt_file = os.path.join(os.path.dirname(__file__), '..', '.devin', 'SYSTEM_PROMPT.md')
    if os.path.exists(prompt_file):
        try:
            with open(prompt_file, 'r', encoding='utf-8') as f:
                return f.read()
        except Exception:
            # 如果读取失败，返回None使用默认提示
            return None
    return None


# 项目附加规范的模式：builtin（只用内置模板）| append（内置 + 追加项目规范，默认）
# | replace（项目规范整体替换内置模板，旧行为）。
PROMPT_MODE_ENV = "CODE_AGENT_PROMPT_MODE"
# 追加模式下项目规范的最大字符数（超出截断），避免挤占本轮推理预算。
SYSTEM_PROMPT_EXTRA_MAX_CHARS = int(os.getenv("SYSTEM_PROMPT_EXTRA_MAX_CHARS", "4000"))


def _prompt_mode() -> str:
    mode = os.getenv(PROMPT_MODE_ENV, "append").strip().lower()
    return mode if mode in ("builtin", "append", "replace") else "append"


def _extract_json_object(text: str) -> Optional[str]:
    """
    从 `Action Input:` 之后的文本中提取第一个完整的 JSON 对象。

    使用花括号配对计数（同时跳过字符串字面量内的花括号），
    以正确处理嵌套对象和包含 `}` 的多行代码字符串，
    避免非贪婪正则在第一个 `}` 处过早截断。

    Args:
        text: `Action Input:` 标记之后的原始文本

    Returns:
        完整 JSON 对象的字符串（含首尾花括号），找不到时返回 None
    """
    start = text.find("{")
    if start == -1:
        return None

    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
    return None


def _parse_action_input(raw: str) -> dict:
    """
    安全地把 Action Input 原始字符串解析为 dict。

    解析顺序（均为安全解析，不使用 eval）：
    1. json.loads —— 标准合法 JSON
    2. ast.literal_eval —— 容错单引号 / Python 字面量（如 {'path': 'x'}）

    任何情况下都不会执行任意代码；解析失败返回空 dict。

    Args:
        raw: JSON 对象字符串

    Returns:
        解析后的 dict；非 dict 或解析失败时返回 {}
    """
    if not raw:
        return {}
    try:
        result = json.loads(raw)
        return result if isinstance(result, dict) else {}
    except (json.JSONDecodeError, ValueError):
        pass
    try:
        result = ast.literal_eval(raw)
        return result if isinstance(result, dict) else {}
    except (ValueError, SyntaxError):
        return {}


SYSTEM_PROMPT_TEMPLATE = """你是代码助手 CodeAgent，运行在 ReAct 工具调用框架中。能力：代码生成/重构/审查/调试、测试、文件操作与搜索、个人知识库检索（RAG）、图片/PDF OCR、网络搜索。这些功能均已启用；工具失败时分析原因，不要声称功能不存在或"无法访问互联网"。

=== 可用工具（只能调用以下工具；参数名后带 ? 表示可选）===
{tool_descriptions}

=== 输出协议（严格遵守）===
每步先写 Thought，然后要么调用一个工具，要么给出最终答案：
Thought: <推理>
Action: <工具名>
Action Input: <一行合法 JSON 对象>
（停止输出，等待 Observation）

任务完成时：
Thought: <推理>
Final Answer: <给用户的最终回答>

=== 格式规则 ===
1. Action Input 必须是一行合法 JSON：键和字符串值用双引号；无参数写 {}。
   错误示例：{path: test.py}、{'path': 'test.py'}、跨多行。
2. 每次只调用一个工具，Action 之后不要再写解释或 Final Answer，也不要自己编造 Observation。
3. 多行代码作为 JSON 字符串值，用 \\n 表示换行、\\" 转义引号；代码较长时拆成多次小步骤。
4. 工具返回 [格式错误]/[用户拒绝]/[错误] 时，修正后重试一次；连续两次失败换方法或说明原因。
5. 相同工具与参数不要重复调用；已有结果直接使用。

=== 示例 ===
Thought: 先写入文件再运行验证
Action: write_file
Action Input: {"path": "src/util.py", "content": "def add(a, b):\\n    return a + b\\n"}

=== 工具速查 ===
- 写代码 → write_file，再 execute_command 运行验证；看代码 → read_file；搜代码 → search_files
- 列目录 → list_directory（不要把目录当文件读）；当前目录 → get_current_dir
- 文档/论文/笔记内容 → query_knowledge_base；添加文档 → add_to_knowledge_base（PDF/图片/文本）
- 用户给出图片/PDF 路径 → 先 add_to_knowledge_base 再 query_knowledge_base（带文件名）
- 最新/实时信息（版本、新闻、价格）→ web_search；指定网址 → web_content_extract
- 知识库无相关内容（返回 [知识库无相关内容]）→ 转 web_search

=== 安全规则 ===
- 不执行危险命令（如 rm -rf /）；可能修改系统的命令先说明意图等待确认
- 写文件前确认路径正确，只在项目目录内写文件

回答简洁专业，代码块用 markdown。不需要工具时直接给出 Final Answer。
"""


def build_system_prompt(tools: Optional[set] = None, extra: Optional[str] = None,
                        mode: Optional[str] = None) -> str:
    """运行时组装分层系统提示：精简内置模板 + 可选项目附加规范。

    Args:
        tools: 允许的工具名集合（None 表示全部），工具速查只列出这些工具。
        extra: 角色附加提示（多 Agent 子角色注入），追加在最后。
        mode: ``builtin`` 只用内置模板；``append``（默认）内置模板后追加
            ``.devin/SYSTEM_PROMPT.md``（截断到 ``SYSTEM_PROMPT_EXTRA_MAX_CHARS``）；
            ``replace`` 用该文件整体替换内置模板（旧行为）。

    系统提示不落盘：每次启动按当前工具表重新生成，避免与代码不同步。
    """
    mode = mode or _prompt_mode()
    tool_desc = registry.get_descriptions(names=tools, compact=True)
    custom_prompt = read_system_prompt_from_file() if mode != "builtin" else None

    if mode == "replace" and custom_prompt:
        prompt = custom_prompt.replace(
            "{tool_descriptions}", registry.get_descriptions(names=tools))
    else:
        prompt = SYSTEM_PROMPT_TEMPLATE.replace("{tool_descriptions}", tool_desc)
        if mode == "append" and custom_prompt:
            project = custom_prompt.replace("{tool_descriptions}", "（见上方工具列表）").strip()
            if len(project) > SYSTEM_PROMPT_EXTRA_MAX_CHARS:
                project = project[:SYSTEM_PROMPT_EXTRA_MAX_CHARS] + "\n…（项目规范已截断）"
            prompt = prompt.rstrip() + "\n\n=== 项目附加规范 ===\n" + project + "\n"

    if extra and extra.strip():
        prompt = prompt.rstrip() + "\n\n=== 角色说明 ===\n" + extra.strip() + "\n"
    return prompt


class ReActEngine:
    """ReAct 推理引擎。

    对话记忆以"当前会话"（``conversation_context.ConversationContext``）为唯一
    真源：每轮开始时从会话取 ``[系统提示] + [滚动摘要] + [最近 K 轮原文]``，本轮
    的 Thought/Action/Observation 只存在于内存工作列表，结束后折叠为
    "任务 + 最终答案 + 一句执行摘要" 写回会话。
    """

    def __init__(self, model: str = None, host: str = None,
                 on_step: Callable = None, on_confirm: Callable = None,
                 context=None, allowed_tools: Optional[set] = None,
                 system_prompt_extra: str = "", max_iterations: Optional[int] = None,
                 prompt_mode: Optional[str] = None):
        """
        Args:
            allowed_tools: 限定可用工具集（工具描述与可执行集合同时过滤）；
                None 表示全部工具。多 Agent 子角色据此收窄能力。
            system_prompt_extra: 角色附加提示，追加到系统提示末尾（≤200 token 为宜）。
            max_iterations: 本实例的最大步数，默认 ``Config.MAX_ITERATIONS``。
            prompt_mode: 覆盖 ``CODE_AGENT_PROMPT_MODE``（builtin|append|replace）。
        """
        self.model = model or Config.LLM_MODEL
        self.host = host or Config.OLLAMA_HOST
        self.allowed_tools: Optional[set] = set(allowed_tools) if allowed_tools is not None else None
        self.system_prompt_extra = system_prompt_extra or ""
        self.max_iterations = int(max_iterations) if max_iterations else int(Config.MAX_ITERATIONS)
        # 按所选模型自动推导安全的上下文窗口，避免大默认上下文撑爆显存导致卡顿。
        self.num_ctx = self._resolve_num_ctx(self.model)
        # 是否启用模型"思考模式"：ReAct 的 Thought/Action 协议本身就是显式推理，
        # 再叠加隐式思维链只会拖慢每一步（4B 模型可多出上千 token）。默认关闭。
        try:
            from config import LLM_THINK
            self.think = bool(LLM_THINK)
        except Exception:  # noqa: BLE001
            self.think = False
        # 会话上下文（可注入；为空时惰性取进程内单例，跟随"当前会话"）
        self._context = context
        self.system_prompt = build_system_prompt(
            tools=self.allowed_tools, extra=self.system_prompt_extra, mode=prompt_mode)
        # 本轮的内存工作消息列表（系统提示 + 历史上下文 + 本轮 ReAct 往返）
        self.messages: List[Dict] = []
        self._stop_event = threading.Event()
        self.on_step = on_step
        self.on_confirm = on_confirm
        self.step_log: List[Dict] = []

    @property
    def context(self):
        if self._context is None:
            from conversation_context import get_conversation_context
            self._context = get_conversation_context()
        return self._context

    @context.setter
    def context(self, value):
        self._context = value

    @staticmethod
    def _resolve_num_ctx(model: str) -> int:
        try:
            from config import resolve_num_ctx
            return resolve_num_ctx(model)
        except Exception:  # noqa: BLE001
            return 8192

    def set_model(self, model: str) -> int:
        """运行时切换模型（供 CLI ``/model <name>`` 使用），同步重算 num_ctx。

        对话历史与系统提示保持不变，无需重建实例。返回新 num_ctx。
        """
        model = (model or "").strip()
        if not model:
            raise ValueError("模型名不能为空")
        self.model = model
        self.num_ctx = self._resolve_num_ctx(model)
        return self.num_ctx

    def set_think(self, enabled: bool) -> bool:
        """运行时开关思考模式（供 CLI ``/think on|off`` 使用），下一次请求即生效。"""
        self.think = bool(enabled)
        return self.think

    def stop(self):
        self._stop_event.set()

    def reset_stop(self):
        self._stop_event.clear()

    # ---------- 会话上下文桥接 ----------

    def _context_progress(self, evt: Dict) -> None:
        """把上下文层的进度事件（压缩等）转发为 on_step 事件。"""
        if self.on_step:
            self.on_step({
                "step": "?",
                "phase": evt.get("stage", "context"),
                "message": evt.get("message", ""),
            })

    def _load_context(self, user_input: str) -> None:
        """从会话构建本轮起始消息：系统提示 + 滚动摘要 + 最近 K 轮 + 本轮问题。"""
        try:
            base = self.context.build_messages(system_prompt=self.system_prompt)
        except Exception as e:  # noqa: BLE001 - 会话不可用时仍可无记忆运行
            base = [{"role": "system", "content": self.system_prompt}]
            if self.on_step:
                self.on_step({"step": "?", "phase": "context", "message": f"⚠️ 读取会话上下文失败: {e}"})
        self.messages = list(base) + [{"role": "user", "content": user_input}]

    def _trace_summary(self) -> str:
        """把本轮中间步骤折叠为一句执行摘要（不含 Observation 正文）。"""
        tools: List[str] = []
        blocked = rejected = 0
        for log in self.step_log:
            phase = log.get("phase")
            if phase == "action":
                tool = log.get("tool")
                if tool and tool not in tools:
                    tools.append(tool)
                if not log.get("confirmed", True):
                    rejected += 1
            elif phase == "blocked":
                blocked += 1
            elif phase == "rejected":
                rejected += 1
        steps = len([l for l in self.step_log if l.get("phase") == "action"])
        if not steps:
            return ""
        parts = [f"共 {steps} 步", "调用 " + "、".join(tools) if tools else ""]
        if blocked:
            parts.append(f"拦截危险命令 {blocked} 次")
        if rejected:
            parts.append(f"用户拒绝 {rejected} 次")
        return "，".join(p for p in parts if p)

    def _record_turn(self, user_input: str, answer: str) -> None:
        try:
            self.context.record(
                user_input, answer, trace=self._trace_summary(),
                progress=self._context_progress,
            )
        except Exception as e:  # noqa: BLE001 - 落库失败不影响返回结果
            if self.on_step:
                self.on_step({"step": "?", "phase": "context", "message": f"⚠️ 记录会话失败: {e}"})

    def chat(self, user_input: str) -> str:
        self.reset_stop()
        self.step_log = []
        self._load_context(user_input)

        max_iter = self.max_iterations
        for step in range(1, max_iter + 1):
            if self._stop_event.is_set():
                return "[用户中断] 任务已停止。"

            if self.on_step:
                self.on_step({
                    "step": step,
                    "total": max_iter,
                    "phase": "thinking",
                    "message": f"Step {step}/{max_iter}: 模型推理中..."
                })

            response = self._call_model()

            action_match = re.search(r'Action:\s*(\w+)', response)
            # 定位 "Action Input:" 后的文本，再用括号配对提取完整 JSON 对象，
            # 以正确处理嵌套对象与含 "}" 的多行代码（非贪婪正则会过早截断）。
            input_label = re.search(r'Action Input:\s*', response)
            json_str = None
            if input_label:
                json_str = _extract_json_object(response[input_label.end():])

            if action_match and json_str:
                tool_name = action_match.group(1).strip()
                tool_input = _parse_action_input(json_str)

                thought_match = re.search(r'Thought:\s*(.*?)(?=Action:|$)', response, re.DOTALL)
                thought = thought_match.group(1).strip() if thought_match else ""

                step_record = {
                    "step": step,
                    "phase": "action",
                    "thought": thought,
                    "tool": tool_name,
                    "input": tool_input,
                    "observation": "",
                    "confirmed": True
                }

                if self.allowed_tools is not None and tool_name not in self.allowed_tools:
                    obs = (f"[错误] 工具 {tool_name} 不在当前允许的工具集内，"
                           f"可用: {', '.join(sorted(self.allowed_tools))}")
                    step_record["observation"] = obs
                    step_record["confirmed"] = False
                    self.step_log.append(step_record)
                    self._push("assistant", response)
                    self._push("user", "Observation: " + obs + "\n请改用允许的工具，或直接给出最终答案。")
                    continue

                if tool_name == "execute_command":
                    cmd = tool_input.get("command", "")
                    safety = CommandSafetyChecker.analyze(cmd)
                    step_record["safety"] = safety

                    if safety["is_dangerous"]:
                        step_record["observation"] = f"[安全拦截] 检测到危险命令: {cmd}\n原因: {', '.join(safety['danger_reasons'])}\n该命令被拒绝执行。"
                        step_record["confirmed"] = False
                        self.step_log.append(step_record)
                        self._push("assistant", response)
                        self._push("user", "Observation: " + step_record['observation'] + "\n请使用安全的方式完成任务，或向用户解释风险。")
                        if self.on_step:
                            self.on_step({
                                "step": step,
                                "phase": "blocked",
                                "message": f"Step {step}: 危险命令已拦截 [{cmd}]"
                            })
                        continue

                    elif safety["needs_confirm"] and not Config.AUTO_CONFIRM:
                        step_record["confirmed"] = False
                        self.step_log.append(step_record)

                        if self.on_confirm:
                            confirmed = self.on_confirm({
                                "step": step,
                                "tool": tool_name,
                                "command": cmd,
                                "safety": safety,
                                "message": f"即将执行命令: {cmd}\n风险等级: {safety['risk_level']}\n是否确认执行? (y/n)"
                            })
                        else:
                            confirmed = False

                        if not confirmed:
                            obs = f"[用户拒绝] 命令未执行: {cmd}"
                            step_record["observation"] = obs
                            step_record["confirmed"] = False
                            self._push("assistant", response)
                            self._push("user", "Observation: " + obs + "\n请尝试其他方法，或向用户解释为什么需要这个命令。")
                            if self.on_step:
                                self.on_step({
                                    "step": step,
                                    "phase": "rejected",
                                    "message": f"Step {step}: 用户拒绝执行 [{cmd}]"
                                })
                            continue
                        else:
                            step_record["confirmed"] = True

                if self.on_step:
                    self.on_step({
                        "step": step,
                        "phase": "executing",
                        "message": f"Step {step}: 执行 {tool_name}..."
                    })

                observation = registry.execute(tool_name, tool_input, auto_confirm=Config.AUTO_CONFIRM)

                if observation.startswith("[CONFIRM_REQUIRED]"):
                    step_record["confirmed"] = False
                    self.step_log.append(step_record)
                    if self.on_confirm:
                        parts = observation.split("|", 1)
                        args = json.loads(parts[1]) if len(parts) > 1 else {}
                        confirmed = self.on_confirm({
                            "step": step,
                            "tool": tool_name,
                            "args": args,
                            "message": f"即将执行 {tool_name}: {json.dumps(args, ensure_ascii=False)}\n是否确认? (y/n)"
                        })
                    else:
                        confirmed = False

                    if not confirmed:
                        obs = f"[用户拒绝] {tool_name} 未执行"
                        step_record["observation"] = obs
                        self._push("assistant", response)
                        self._push("user", "Observation: " + obs + "\n请尝试其他方法。")
                        continue
                    else:
                        observation = registry.execute(tool_name, tool_input, auto_confirm=True)
                        step_record["confirmed"] = True

                step_record["observation"] = observation
                self.step_log.append(step_record)

                if self.on_step:
                    self.on_step({
                        "step": step,
                        "phase": "observed",
                        "message": f"Step {step}: {tool_name} 执行完成"
                    })

                self._push("assistant", response)
                self._push("user", "Observation: " + observation + "\n请继续下一步，或直接给出最终答案。")
            else:
                final_match = re.search(r'Final Answer:\s*(.*)', response, re.DOTALL)
                if final_match:
                    answer = final_match.group(1).strip()
                else:
                    answer = response.strip()

                self.step_log.append({"step": step, "phase": "final", "answer": answer})
                self._push("assistant", answer)
                # 折叠本轮：只把"任务 + 最终答案 + 一句执行摘要"写回会话
                self._record_turn(user_input, answer)
                return answer

        warning = "[警告] 达到最大迭代次数，任务可能未完成。请简化需求重试。"
        self._record_turn(user_input, warning)
        return warning

    def _push(self, role: str, content: str) -> None:
        """追加到本轮内存工作列表（不落盘；中间往返在轮末被折叠）。"""
        self.messages.append({"role": role, "content": content})

    def _call_model(self, messages: Optional[List[Dict]] = None) -> str:
        messages = self.messages if messages is None else messages
        clean_messages = []
        for m in messages:
            if isinstance(m, dict) and "role" in m and "content" in m:
                clean_messages.append({"role": m["role"], "content": m["content"]})

        if not clean_messages:
            return "[错误] 消息列表为空"

        # 启动进度更新线程。心跳事件标记 transient=True：它们只表示"仍在推理"，
        # 消费方（如 Web UI）应原地刷新当前状态而不是逐条追加，避免刷屏。
        stop_progress = threading.Event()
        def update_progress():
            dots = 0
            while not stop_progress.is_set():
                if self.on_step and not stop_progress.is_set():
                    dot_str = "." * (dots % 4)
                    self.on_step({
                        "step": "?",
                        "total": "?",
                        "phase": "thinking",
                        "transient": True,
                        "message": f"模型推理中{dot_str}"
                    })
                dots += 1
                stop_progress.wait(0.5)  # 每0.5秒更新一次
        
        progress_thread = threading.Thread(target=update_progress, daemon=True)
        progress_thread.start()

        try:
            resp = requests.post(
                self.host + "/api/chat",
                json={
                    "model": self.model,
                    "messages": clean_messages,
                    "stream": False,
                    # 显式传 think：对支持思考模式的模型（qwen3.5 等）默认关闭，
                    # 不支持的模型 Ollama 会忽略该字段。
                    "think": self.think,
                    "options": {
                        "temperature": 0.3,
                        "num_ctx": self.num_ctx,
                        "num_predict": 4096
                    }
                },
                timeout=Config.TIMEOUT
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("message", {}).get("content", "")
        except requests.exceptions.ConnectionError:
            return "[错误] 无法连接到 Ollama，请确认服务已启动: ollama serve"
        except requests.exceptions.Timeout:
            return "[错误] 模型响应超时，请检查模型是否已加载到内存"
        except Exception as e:
            return "[错误] 模型调用失败: " + str(e)
        finally:
            stop_progress.set()
            progress_thread.join(timeout=1.0)

    def clear_history(self) -> bool:
        """清空当前会话的对话上下文（消息与滚动摘要），系统提示由运行时注入不受影响。"""
        self.messages = []
        try:
            return bool(self.context.clear())
        except Exception as e:  # noqa: BLE001
            if self.on_step:
                self.on_step({"step": "?", "phase": "context", "message": f"⚠️ 清空会话失败: {e}"})
            return False

    def get_step_summary(self) -> str:
        lines = ["=== Agent 执行摘要 ==="]
        for log in self.step_log:
            step = log.get("step", "?")
            phase = log.get("phase", "?")
            if phase == "action":
                tool = log.get("tool", "?")
                confirmed = "OK" if log.get("confirmed") else "X"
                lines.append(f"Step {step}: [{confirmed}] 调用 {tool}")
                if log.get("thought"):
                    lines.append(f"  思考: {log['thought'][:100]}...")
                if log.get("safety"):
                    lines.append(f"  安全: {log['safety']['risk_level']}")
            elif phase == "blocked":
                lines.append(f"Step {step}: [拦截] 危险命令被拒绝")
            elif phase == "rejected":
                lines.append(f"Step {step}: [拒绝] 用户取消执行")
            elif phase == "final":
                lines.append(f"Step {step}: [完成] 给出最终答案")
        return "\n".join(lines)
