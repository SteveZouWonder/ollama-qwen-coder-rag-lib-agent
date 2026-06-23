#!/usr/bin/env python3
"""
ReAct 推理引擎 - 带迭代可视化和安全确认
适配 qwen2.5-coder:7b，集成 RAG 知识库工具
"""
import re
import ast
import json
import requests
import threading
import os
from typing import List, Dict, Callable, Optional, Tuple

from config import Config
from chat_history import ChatHistory
from agent_tools import registry, CommandSafetyChecker


def read_system_prompt_from_file():
    """
    从 .devin/SYSTEM_PROMPT.md 读取系统提示
    如果文件不存在，返回None，使用内置的默认提示
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

# 内置后备系统提示（fallback）。
# 仅当 .devin/SYSTEM_PROMPT.md 读取失败时使用，因此保持精简：
# 只保留驱动本地小模型（如 qwen2.5-coder:7b）做 ReAct 工具调用所必需的内容。
# 完整的开发规范/工作流/多 Agent 协作说明见 .devin/SYSTEM_PROMPT.md。
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


SYSTEM_PROMPT_TEMPLATE = """你是一个专业的代码助手 Agent，名为 CodeAgent，运行在 ReAct 工具调用框架中。

你的能力：代码生成与重构、代码审查与调试、测试生成与执行、文件操作与搜索、
个人知识库检索（RAG，数据持久化于 index_storage）、图片/扫描件 OCR 识别（默认 Tesseract）、
网络搜索（ddgs，Wikipedia 备用）、多 Agent 协作。这些功能均已启用——
若工具调用失败应分析原因（配置/依赖问题），不要声称功能不存在或"无法访问互联网"。

=== 可用工具（只能调用以下列出的工具）===
{tool_descriptions}

=== ReAct 输出格式（严格遵守）===
每一步输出一个 Thought，然后**要么**调用一个工具，**要么**给出最终答案：

调用工具时，严格输出（Action 与 Action Input 必须成对，且后面不要有多余文字）：
Thought: <你的推理>
Action: <工具名>
Action Input: <一行合法 JSON 对象>

任务完成时：
Thought: <你的推理>
Final Answer: <给用户的最终回答>

=== 格式硬性规则 ===
1. Action Input 必须是**合法 JSON**，键和字符串值都用双引号，且写在**一行内**。
   - 正确：Action Input: {"path": "test.py"}
   - 正确：Action Input: {}   （无参数时用空对象）
   - 错误：Action Input: {path: test.py}        （缺少引号）
   - 错误：Action Input: {'path': 'test.py'}     （用了单引号）
2. 每次**只能调用一个工具**；调用工具后**立即停止输出**，等待 Observation，不要自己编造 Observation。
3. 不要在同一次回复里既输出 Action 又输出 Final Answer。
4. 写多行代码到文件时，把代码作为 JSON 字符串值，用 \\n 表示换行、\\" 转义引号，整体仍是一行 JSON。
   若代码较长，优先拆成多次小步骤，避免单条 Action Input 过长。

=== 正确示例：读取并分析文件 ===
Thought: 需要先读取文件内容
Action: read_file
Action Input: {"path": "src/app.py"}
（停止，等待 Observation）

=== 正确示例：写代码并验证 ===
Thought: 先写入文件
Action: write_file
Action Input: {"path": "src/util.py", "content": "def add(a, b):\\n    return a + b\\n"}
（Observation 返回成功后，再用 execute_command 运行测试）

=== 常见错误示例（不要这样做）===
✗ 一次输出多个 Action
✗ Action Input 跨多行或用单引号 / 无引号
✗ Action 之后又写解释文字或 Final Answer
✗ 自己编写 Observation 内容

=== 工具选择速查 ===
- 写代码 → write_file，然后 execute_command 运行验证
- 看代码 → read_file
- 搜代码 → search_files；确认当前目录 → get_current_dir
- 列目录 → list_directory（分析项目结构时先列目录，不要把目录当文件读）
- 文档/论文/笔记内容 → query_knowledge_base；添加文档 → add_to_knowledge_base（支持 PDF/图片/文本）
- 用户给出图片/PDF 路径 → 先 add_to_knowledge_base，再 query_knowledge_base（查询时带上文件名提高精度）
- 知识库状态 → get_knowledge_stats / check_knowledge_status
- 最新信息/实时数据（版本、新闻、价格等）→ web_search；指定网址提取内容 → web_content_extract

=== 安全规则 ===
- 不执行危险命令（如 rm -rf /）；可能修改系统的命令先说明意图等待确认
- 写文件前确认路径正确

回答保持简洁专业，代码块用 markdown。不需要工具时直接给出 Final Answer。
"""

class ReActEngine:
    def __init__(self, model: str = None, host: str = None,
                 on_step: Callable = None, on_confirm: Callable = None):
        self.model = model or Config.LLM_MODEL
        self.host = host or Config.OLLAMA_HOST
        self.history = ChatHistory(Config.HISTORY_FILE, Config.MAX_HISTORY)
        self._init_system()
        self._stop_event = threading.Event()
        self.on_step = on_step
        self.on_confirm = on_confirm
        self.step_log: List[Dict] = []

    def _init_system(self):
        msgs = self.history.get_messages()
        has_system = any(m.get("role") == "system" for m in msgs)
        if not has_system:
            # 优先从文件读取系统提示
            custom_prompt = read_system_prompt_from_file()
            if custom_prompt:
                # 使用自定义提示，替换工具描述占位符
                tool_desc = registry.get_descriptions()
                system_msg = custom_prompt.replace("{tool_descriptions}", tool_desc)
            else:
                # 使用内置默认提示
                tool_desc = registry.get_descriptions()
                system_msg = SYSTEM_PROMPT_TEMPLATE.replace("{tool_descriptions}", tool_desc)
            
            self.history.messages.insert(0, {"role": "system", "content": system_msg})
            self.history.save()

    def stop(self):
        self._stop_event.set()

    def reset_stop(self):
        self._stop_event.clear()

    def chat(self, user_input: str) -> str:
        self.reset_stop()
        self.step_log = []
        self.history.add("user", user_input)

        for step in range(1, Config.MAX_ITERATIONS + 1):
            if self._stop_event.is_set():
                return "[用户中断] 任务已停止。"

            if self.on_step:
                self.on_step({
                    "step": step,
                    "total": Config.MAX_ITERATIONS,
                    "phase": "thinking",
                    "message": f"Step {step}/{Config.MAX_ITERATIONS}: 模型推理中..."
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

                if tool_name == "execute_command":
                    cmd = tool_input.get("command", "")
                    safety = CommandSafetyChecker.analyze(cmd)
                    step_record["safety"] = safety

                    if safety["is_dangerous"]:
                        step_record["observation"] = f"[安全拦截] 检测到危险命令: {cmd}\n原因: {', '.join(safety['danger_reasons'])}\n该命令被拒绝执行。"
                        step_record["confirmed"] = False
                        self.step_log.append(step_record)
                        self.history.add("assistant", response)
                        self.history.add("user", "Observation: " + step_record['observation'] + "\n请使用安全的方式完成任务，或向用户解释风险。")
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
                            self.history.add("assistant", response)
                            self.history.add("user", "Observation: " + obs + "\n请尝试其他方法，或向用户解释为什么需要这个命令。")
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
                        self.history.add("assistant", response)
                        self.history.add("user", "Observation: " + obs + "\n请尝试其他方法。")
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

                self.history.add("assistant", response)
                self.history.add("user", "Observation: " + observation + "\n请继续下一步，或直接给出最终答案。")
            else:
                final_match = re.search(r'Final Answer:\s*(.*)', response, re.DOTALL)
                if final_match:
                    answer = final_match.group(1).strip()
                else:
                    answer = response.strip()

                self.step_log.append({"step": step, "phase": "final", "answer": answer})
                self.history.add("assistant", answer)
                return answer

        return "[警告] 达到最大迭代次数，任务可能未完成。请简化需求重试。"

    def _call_model(self) -> str:
        messages = self.history.get_messages()
        clean_messages = []
        for m in messages:
            if isinstance(m, dict) and "role" in m and "content" in m:
                clean_messages.append({"role": m["role"], "content": m["content"]})

        if not clean_messages:
            return "[错误] 消息列表为空"

        # 启动进度更新线程
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
                    "options": {
                        "temperature": 0.3,
                        "num_ctx": 8192,
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

    def clear_history(self):
        self.history.clear()
        self._init_system()

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
