#!/usr/bin/env python3
"""
ReAct 推理引擎 - 带迭代可视化和安全确认
适配 qwen2.5-coder:7b，集成 RAG 知识库工具
"""
import re
import json
import requests
import threading
from typing import List, Dict, Optional, Callable

from config import Config
from chat_history import ChatHistory
from agent_tools import registry, CommandSafetyChecker

SYSTEM_PROMPT_TEMPLATE = """你是一个专业的代码助手 Agent，名为 CodeAgent。

你的核心能力：
1. 代码生成与重构
2. 代码审查与 Bug 分析
3. 自动测试生成与执行
4. 项目文件操作与搜索
5. 个人知识库检索（RAG）- 基于用户上传的 PDF、论文、笔记等文档回答问题

{tool_descriptions}

=== ReAct 工作流 ===
当用户提出请求时，按以下步骤思考：

1. Thought: 分析用户需求，判断是否需要工具。如果需要，规划步骤。
2. Action: 如果需要工具，严格按以下格式输出（不要有多余文字）：
   Action: 工具名
   Action Input: {key: value}  （key 和 value 用实际参数名和值替换）
3. Observation: 工具执行结果会自动提供给你。
4. 根据 Observation，决定下一步行动或给出最终答案。
5. Final Answer: 当任务完成时，输出最终回答。

=== 输出规则 ===
- 每次只调用一个工具
- Action 和 Action Input 必须严格配对出现
- 如果用户要求写代码，先 write_file 写入，再 execute_command 运行验证
- 如果用户要求检查代码，先 read_file 读取，再分析
- 如果用户询问文档/论文/笔记中的内容，使用 query_knowledge_base 查询知识库
- 如果用户要求添加文档到知识库，使用 add_to_knowledge_base
- 保持回答简洁专业，代码块用 markdown 格式
- 如果不需要工具，直接输出 Final Answer

=== 安全规则 ===
- 执行命令前确认安全性，避免 rm -rf / 等危险命令
- 写入文件前确认路径正确
- 如果命令可能修改系统，先说明要执行什么，等待确认
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
            action_input_match = re.search(r'Action Input:\s*(\{.*?\})', response, re.DOTALL)

            if action_match and action_input_match:
                tool_name = action_match.group(1).strip()
                try:
                    tool_input = json.loads(action_input_match.group(1))
                except json.JSONDecodeError:
                    raw = action_input_match.group(1)
                    try:
                        tool_input = eval(raw)
                        if not isinstance(tool_input, dict):
                            tool_input = {}
                    except:
                        tool_input = {}

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
