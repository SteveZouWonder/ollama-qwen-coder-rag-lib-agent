"""工具页：registry 工具命令、代码助手 / 符号 / 质量、Git、AI 解读、Shell / 文件读写、工作区浏览、命令生成。"""
from __future__ import annotations

import logging
import queue
import threading
from typing import Any, Dict, Iterator, List, Optional

from .base import ScratchContext, StreamEvent

logger = logging.getLogger(__name__)


class ToolsMixin:
    """工具页服务（对齐 CLI ``/tools`` ``/exec`` ``/file`` ``/write`` ``/pwd`` ``/cd`` ``/git-*`` ``/code-*``）。"""

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

    @staticmethod
    def path_read_error(path: str) -> Optional[str]:
        """路径不在允许读取范围时返回错误文案（不带 ``[错误]`` 前缀），否则 ``None``。

        Web「工具」页直接读文件 / 目录的入口（预览、目录、搜索、符号、质量、图谱 @文件、代码助手）
        与 Agent 的 ``read_file`` 等工具共用 ``agent_tools`` 的读边界（F10 P0-1），两端一致、无绕过口。
        """
        try:
            from agent_tools import is_read_allowed, read_scope_error
        except ImportError:  # pragma: no cover - 裁剪部署缺少 agent_tools 时不设边界
            return None
        if is_read_allowed(path):
            return None
        msg = read_scope_error(path)
        return msg[len("[错误] "):] if msg.startswith("[错误] ") else msg

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
        scope_err = self.path_read_error(path)
        if scope_err:
            yield StreamEvent("error", scope_err)
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
        scope_err = self.path_read_error(real)
        if scope_err:
            return {"symbols": [], "error": scope_err}
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
        scope_err = self.path_read_error(real)
        if scope_err:
            return {**base, "error": scope_err}
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
        scope_err = self.path_read_error(real)
        if scope_err:
            return {**base, "error": scope_err}
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
        scope_err = self.path_read_error(real)
        if scope_err:
            return {**base, "error": scope_err}
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
        if not os.path.isdir(real) or self.path_read_error(real):
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
