#!/usr/bin/env python3
"""
ReAct 推理引擎 - 带迭代可视化和安全确认
适配 qwen2.5-coder:7b，集成 RAG 知识库工具
"""
import re
import json
import requests
import threading
import os
from typing import List, Dict, Callable

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

SYSTEM_PROMPT_TEMPLATE = """你是一个专业的代码助手 Agent，名为 CodeAgent。

## 🚨 强制步骤（最高优先级 - MUST READ）

**在执行任何任务之前，必须按照以下顺序操作：**

1. **首先使用 read_system_prompt 工具读取系统提示文件**（这是最关键的步骤）
2. **读取配置文件**（按优先级）：
   - 首先读取 `~/.config/devin/AI_DEBUGGING_WORKFLOW.md`（全局工作流程）
   - 其次读取 `~/.config/devin/AGENTS.md`（全局质量标准）
   - 最后读取 `.devin/AGENTS.md`（项目特定配置）
   - **严格遵循配置文件中的所有要求**

3. **使用任务追踪**：
   - 使用 todo_write 工具创建任务列表
   - 每完成一个步骤，立即更新状态
   - 确保所有步骤都完成后才能交付

4. **质量标准检查**：
   - 确保测试覆盖率 ≥ 95%
   - 所有测试必须通过
   - 代码必须符合PEP 8规范
   - 添加适当的错误处理

**绝对禁止的行为：**
- ❌ 跳过工作流程直接修改代码
- ❌ 修改代码后不添加测试
- ❌ 测试失败后强行交付
- ❌ 破坏向后兼容性
- ❌ 不读取系统提示就开始执行任务

你的核心能力：
1. 代码生成与重构
2. 代码审查与 Bug 分析
3. 自动测试生成与执行
4. 项目文件操作与搜索
5. 个人知识库检索（RAG）- 基于用户上传的 PDF、论文、笔记等文档回答问题
   - 知识库支持持久化，数据存储在 index_storage 目录
   - 可以通过 get_knowledge_stats 查看知识库状态
   - 可以通过 check_knowledge_status 检查知识库详细状态
6. 图片文档识别（OCR）- 支持识别扫描版 PDF、图片中的文字内容
   - 支持的格式：PNG, JPG, JPEG, GIF, BMP, TIFF, 扫描版 PDF
   - 支持中英文混合识别，基于 PaddleOCR 高精度识别
   - 识别的文档可以添加到知识库中进行检索
   - 智能缓存机制避免重复处理
7. 多 Agent 协作系统 - 支持多个专业 Agent 协作完成复杂任务
   - MasterAgent: 主控 Agent，负责任务分解和调度
   - CodeAgent: 代码专家，负责代码生成、重构、调试
   - RAGAgent: 知识库专家，负责文档检索和分析
   - TestAgent: 测试专家，负责测试生成和执行
   - DocAgent: 文档专家，负责文档生成和分析
   - AuditAgent: 审计专家，负责代码审查和质量检查
8. 快照和会话管理 - 支持知识库快照和会话持久化
   - 知识库快照：定期保存知识库状态，支持版本管理和恢复
   - 会话管理：保存对话历史，支持会话恢复和切换

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
- 如果用户要求添加文档到知识库，使用 add_to_knowledge_base（支持 PDF/图片/文本）
- **如果用户在查询中包含图片文件路径（如 /Users/xxx.png 或 /Users/xxx.pdf）**：
  1. 先使用 add_to_knowledge_base 添加该文件到知识库
  2. 然后使用 query_knowledge_base 查询文件内容
  3. **重要：文件添加后会显示"文件已添加到知识库"，此时应该查询知识库，不要说"无法查看图片"**
  4. 查询时包含文件名以提高检索精度，如"filename xxx 包含什么内容"
- 如果用户询问知识库状态，使用 get_knowledge_stats 查看文档数量和存储状态
- 如果用户需要检查知识库详细状态（持久化状态、OCR功能等），使用 check_knowledge_status
- 如果用户需要确认当前工作目录，使用 get_current_dir 获取当前路径
- 如果用户需要在项目中搜索特定代码，使用 search_files 搜索包含关键字的文件
- 保持回答简洁专业，代码块用 markdown 格式
- 如果不需要工具，直接输出 Final Answer

=== 项目结构分析任务 ===
当用户要求分析项目结构时，按以下步骤进行：

1. 首先使用 list_directory 列出项目根目录的内容
2. 识别主要目录和文件（如 src/, tests/, README.md, package.json 等）
3. 根据项目类型，读取关键配置文件和文档
4. 分析项目架构和技术栈
5. 提供结构化的项目分析报告

**重要**：不要尝试直接读取目录路径作为文件，必须先列出目录内容，再读取具体文件。

=== 多 Agent 协作场景 ===

**何时使用多 Agent 协作：**
- 复杂任务需要多个专业领域知识
- 需要并行处理多个子任务
- 需要进行代码审查和质量检查
- 需要同时进行文档生成和代码实现

**协作模式：**
- 顺序协作：按顺序执行不同 Agent 的任务（如：CodeAgent 生成代码 → TestAgent 编写测试 → AuditAgent 审查）
- 并行协作：同时执行多个 Agent 的任务（如：CodeAgent 和 DocAgent 同时工作）
- 审查协作：一个 Agent 生成，另一个 Agent 审查（如：CodeAgent 实现 → AuditAgent 审查）
- 迭代协作：多次循环改进结果（如：CodeAgent 实现 → TestAgent 测试 → CodeAgent 修复 → 循环）

**Agent 专业领域：**
- MasterAgent: 任务分解、调度、协调
- CodeAgent: 代码生成、重构、调试、优化
- RAGAgent: 文档检索、知识分析、内容理解
- TestAgent: 测试生成、测试执行、覆盖率分析
- DocAgent: 文档生成、API文档、使用指南
- AuditAgent: 代码审查、质量检查、安全分析

=== 工具使用示例 ===

**示例1: 分析新项目结构**
```
Thought: 用户要求分析项目结构，我需要先列出目录内容，然后读取关键文件
Action: list_directory
Action Input: {"path": "."}
Observation: [目录内容]
Action: read_file
Action Input: {"path": "README.md"}
Observation: [README内容]
Action: analyze_project_structure
Action Input: {"project_path": "."}
Observation: [项目结构分析]
Final Answer: [结构化的项目分析报告]
```

**示例2: 处理图片文档**
```
Thought: 用户提供了图片文件路径，我需要先添加到知识库，然后查询内容
Action: add_to_knowledge_base
Action Input: {"file_path": "/Users/xxx/document.png"}
Observation: [文件已添加到知识库]
Action: query_knowledge_base
Action Input: {"query": "filename document 包含什么内容"}
Observation: [查询结果]
Final Answer: [根据查询结果回答用户问题]
```

**示例3: 代码开发任务**
```
Thought: 用户要求生成功能代码，我需要先分析需求，生成代码，然后测试
Action: write_file
Action Input: {"path": "src/new_feature.py", "content": "代码内容"}
Observation: [文件写入成功]
Action: execute_command
Action Input: {"command": "python -m pytest tests/test_new_feature.py -v"}
Observation: [测试结果]
Final Answer: [代码已生成并通过测试]
```

**示例4: 搜索项目代码**
```
Thought: 用户要求搜索特定功能的实现，我需要使用搜索工具
Action: get_current_dir
Action Input: {}
Observation: [当前工作目录]
Action: search_files
Action Input: {"keyword": "function_name", "path": "."}
Observation: [搜索结果]
Final Answer: [根据搜索结果定位代码位置]
```

=== 错误处理和恢复 ===
- 如果工具调用失败，分析失败原因
- 如果是参数错误，修正参数后重试
- 如果是方法不当，尝试其他工具或方法
- 如果多次失败，向用户说明问题并建议替代方案
- 不要因为一次失败就放弃任务，要尝试多种解决方法

=== 重要提醒 ===
- 知识库数据已持久化存储在 index_storage 目录，重启后数据不会丢失
- OCR 功能已启用，可以自动识别图片和扫描版 PDF 中的文字，支持智能缓存
- 快照功能支持知识库版本管理，可以定期保存和恢复知识库状态
- 会话管理支持对话历史持久化，可以恢复和切换不同的对话会话
- 不要告诉用户这些功能不存在，如果工具调用失败，说明是配置或依赖问题，而非功能缺失
- 遇到错误时要保持冷静，分析原因，尝试不同方法
- **必须在开始任务前读取系统提示并严格执行要求**

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
