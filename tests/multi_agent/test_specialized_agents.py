"""
测试专业Agent（CodeAgent, RAGAgent, TestAgent, DocAgent, AuditAgent）

Code/Test/Doc/Audit 四个 Agent 现已委托受限工具集的 ReActEngine 真实执行，
测试通过 ``config["engine_factory"]`` 注入假引擎（见 conftest.FakeEngine）。
"""
import pytest

from agents.code_agent import CodeAgent
from agents.rag_agent import RAGAgent
from agents import TestAgent
from agents.doc_agent import DocAgent
from agents import AuditAgent
from agents.base_agent import ReActDelegateAgent, EphemeralContext
from agents.agent_types import AgentTask, AgentType, AgentState


def _task(task_type="code_generation", request="实现用户登录", caps=None, **extra):
    data = {"request": request}
    data.update(extra)
    return AgentTask(
        task_id="task_001",
        task_type=task_type,
        description=request,
        required_capabilities=caps or [task_type],
        input_data=data,
    )


# ==================== 通用：ReActDelegateAgent ====================

class TestReActDelegateAgent:
    """四个专业 Agent 共用的委托逻辑。"""

    def test_agents_are_delegates(self):
        for cls in (CodeAgent, TestAgent, DocAgent, AuditAgent):
            assert issubclass(cls, ReActDelegateAgent)
            assert cls.ALLOWED_TOOLS, cls
            assert cls.ROLE_PROMPT

    def test_role_prompt_is_short(self):
        from conversation_context import estimate_tokens
        for cls in (CodeAgent, TestAgent, DocAgent, AuditAgent):
            assert estimate_tokens(cls.ROLE_PROMPT) <= 200, cls

    def test_engine_receives_role_tools_and_config(self, fake_engine_factory):
        factory = fake_engine_factory("Final Answer: ok")
        agent = CodeAgent(config={
            "engine_factory": factory, "model": "m1", "max_iterations": 7, "host": "http://h",
        })
        result = agent.process_task(_task())
        eng = factory.cls.instances[-1]
        assert eng.kwargs["allowed_tools"] == CodeAgent.ALLOWED_TOOLS
        assert eng.kwargs["system_prompt_extra"] == CodeAgent.ROLE_PROMPT
        assert eng.kwargs["model"] == "m1"
        assert eng.kwargs["max_iterations"] == 7
        assert eng.kwargs["host"] == "http://h"
        assert isinstance(eng.kwargs["context"], EphemeralContext)
        assert eng.kwargs["prompt_mode"] == "builtin"
        assert eng.kwargs["on_confirm"] == agent._auto_confirm
        assert result.success is True
        assert result.output.endswith("Final Answer: ok")
        assert result.metadata["unverified"] is True  # 只 read_file 未 write_file
        assert result.metadata["handled_by"] == "CodeAgent"
        assert result.metadata["steps"] == 1
        assert result.metadata["tools"] == ["read_file"]
        assert result.metadata["step_log"]

    def test_auto_confirm_policy(self):
        agent = CodeAgent()
        # 白名单内的需确认工具（write_file）放行
        assert agent._auto_confirm({"tool": "write_file", "args": {"path": "a.py"}}) is True
        # 白名单外拒绝
        assert agent._auto_confirm({"tool": "web_cache_clear"}) is False
        # execute_command 按风险等级：low/medium 放行，high/critical 拒绝
        for level, ok in (("low", True), ("medium", True), ("high", False), ("critical", False), ("unknown", False)):
            evt = {"tool": "execute_command", "command": "x", "safety": {"risk_level": level}}
            assert agent._auto_confirm(evt) is ok, level
        assert agent._auto_confirm({"tool": "execute_command"}) is False
        # registry 的 [CONFIRM_REQUIRED] 路径不带 safety：按命令自行分析
        assert agent._auto_confirm({"tool": "execute_command", "args": {"command": "python test_x.py"}}) is True
        assert agent._auto_confirm({"tool": "execute_command", "args": {"command": "rm -rf build"}}) is False
        assert agent._auto_confirm({"tool": "execute_command", "command": "rm -rf /"}) is False
        assert agent._auto_confirm({"tool": "execute_command", "command": "cp a b"}) is True

    def test_prompt_mode_override(self, fake_engine_factory):
        factory = fake_engine_factory()
        agent = CodeAgent(config={"engine_factory": factory, "prompt_mode": "append"})
        agent.process_task(_task())
        assert factory.cls.instances[-1].kwargs["prompt_mode"] == "append"

    def test_tools_metadata_only_counts_confirmed(self, fake_engine_factory):
        log = [
            {"phase": "action", "tool": "read_system_prompt", "confirmed": False},
            {"phase": "action", "tool": "write_file", "confirmed": True},
            {"phase": "action", "tool": "write_file"},
            {"phase": "final"},
        ]
        agent = CodeAgent(config={"engine_factory": fake_engine_factory(step_log=log)})
        result = agent.process_task(_task())
        assert result.metadata["tools"] == ["write_file"]
        assert result.metadata["steps"] == 3

    def test_unverified_when_essential_tool_never_ran(self, fake_engine_factory):
        log = [{"phase": "action", "tool": "read_file", "confirmed": True}, {"phase": "final"}]
        agent = TestAgent(config={"engine_factory": fake_engine_factory("已写入 tests/test_x.py，3 passed", step_log=log)})
        result = agent.process_task(_task("testing", "写测试"))
        assert result.success is True
        assert result.metadata["unverified"] is True
        assert result.output.startswith("⚠️ 该 Agent 未实际调用 execute_command/write_file")
        assert "3 passed" in result.output

    def test_verified_when_essential_tool_ran(self, fake_engine_factory):
        log = [{"phase": "action", "tool": "execute_command", "confirmed": True}, {"phase": "final"}]
        agent = TestAgent(config={"engine_factory": fake_engine_factory("3 passed", step_log=log)})
        result = agent.process_task(_task("testing", "写测试"))
        assert result.metadata["unverified"] is False
        assert result.output == "3 passed"

    def test_unverified_not_applied_to_failures(self, fake_engine_factory):
        agent = CodeAgent(config={"engine_factory": fake_engine_factory("[错误] x", step_log=[])})
        result = agent.process_task(_task())
        assert result.metadata["unverified"] is False

    def test_essential_tools_declared(self):
        for cls in (CodeAgent, TestAgent, DocAgent, AuditAgent):
            assert cls.ESSENTIAL_TOOLS and cls.ESSENTIAL_TOOLS <= cls.ALLOWED_TOOLS, cls

    def test_allowed_tools_override_from_config(self, fake_engine_factory):
        factory = fake_engine_factory()
        agent = TestAgent(config={"engine_factory": factory, "allowed_tools": ["read_file"]})
        agent.process_task(_task("testing", "写测试"))
        assert factory.cls.instances[-1].kwargs["allowed_tools"] == {"read_file"}

    def test_prompt_contains_request_hint_original_and_upstream(self, fake_engine_factory):
        factory = fake_engine_factory()
        agent = TestAgent(config={"engine_factory": factory})
        task = _task("testing", "为 qs.py 写测试",
                     original_request="写快排并写测试",
                     upstream=[{"description": "写快排", "output": "已写入 qs.py"}])
        agent.process_task(task)
        prompt = factory.cls.instances[-1].prompts[0]
        assert "为 qs.py 写测试" in prompt
        assert TestAgent.TASK_TYPE_HINTS["testing"] in prompt
        assert "写快排并写测试" in prompt
        assert "已写入 qs.py" in prompt

    def test_prompt_without_request_uses_description(self, fake_engine_factory):
        factory = fake_engine_factory()
        agent = CodeAgent(config={"engine_factory": factory})
        task = AgentTask(task_id="t", task_type="x", description="", required_capabilities=[], input_data={})
        result = agent.process_task(task)
        assert "未提供描述" in factory.cls.instances[-1].prompts[0]
        assert result.success is True

    @pytest.mark.parametrize("answer", ["[错误] 无法连接到 Ollama", "", "[用户中断] 任务已停止。"])
    def test_error_answers_mark_failure(self, fake_engine_factory, answer):
        agent = CodeAgent(config={"engine_factory": fake_engine_factory(answer)})
        result = agent.process_task(_task())
        assert result.success is False
        assert result.error_message == answer

    def test_warning_answer_marks_incomplete(self, fake_engine_factory):
        agent = CodeAgent(config={"engine_factory": fake_engine_factory("[警告] 达到最大迭代次数")})
        result = agent.process_task(_task())
        assert result.success is True
        assert result.metadata["incomplete"] is True

    def test_engine_exception_returns_failure(self):
        def boom(**kw):
            raise RuntimeError("engine down")
        agent = DocAgent(config={"engine_factory": boom})
        result = agent.process_task(_task("documentation", "写文档"))
        assert result.success is False
        assert "engine down" in result.error_message
        assert agent._active_engine is None

    def test_progress_forwarded_and_filtered(self, fake_engine_factory):
        events = []
        agent = AuditAgent(config={"engine_factory": fake_engine_factory()})
        agent.on_progress = events.append
        agent.process_task(_task("audit", "审计"))
        stages = [e["stage"] for e in events]
        assert stages and set(stages) == {"agent_step"}
        thinking = [e for e in events if e["phase"] == "thinking"]
        observed = [e for e in events if e["phase"] == "observed"]
        assert thinking and thinking[0]["transient"] is True
        assert observed and "audit_agent_1" in observed[0]["message"]
        assert events[0]["agent_id"] == "audit_agent_1"

    def test_cancel_stops_active_engine(self, fake_engine_factory):
        factory = fake_engine_factory()
        agent = CodeAgent(config={"engine_factory": factory})
        eng = factory(model=None)
        agent._active_engine = eng
        agent.cancel()
        assert eng.stopped is True

    def test_output_truncated(self, fake_engine_factory):
        log = [{"phase": "action", "tool": "write_file", "confirmed": True}]
        agent = CodeAgent(config={"engine_factory": fake_engine_factory("x" * 10000, step_log=log)})
        result = agent.process_task(_task())
        assert len(result.output) == ReActDelegateAgent.OUTPUT_LIMIT

    def test_default_engine_is_real_react_engine(self):
        """未注入工厂时构造真实 ReActEngine（网络已被 conftest 拦截）。"""
        from react_engine import ReActEngine
        agent = CodeAgent()
        engine = agent._make_engine()
        assert isinstance(engine, ReActEngine)
        assert engine.allowed_tools == CodeAgent.ALLOWED_TOOLS
        assert "角色说明" in engine.system_prompt
        assert "项目附加规范" not in engine.system_prompt  # 子角色默认 builtin
        assert CodeAgent.ROLE_PROMPT[:20] in engine.system_prompt

    def test_real_engine_unreachable_gives_error_result(self):
        agent = CodeAgent(config={"max_iterations": 1})
        result = agent.process_task(_task())
        assert result.success is False
        assert "[错误]" in result.error_message


# ==================== CodeAgent ====================

class TestCodeAgent:
    def test_code_agent_creation(self):
        agent = CodeAgent()
        assert agent.agent_id == "code_agent_1"
        assert agent.agent_type == AgentType.CODE
        for cap in ("code_generation", "code_refactoring", "bug_fixing", "code_review", "file_operations"):
            assert cap in agent.capabilities
        assert agent.get_state() == AgentState.IDLE

    def test_code_agent_custom_id(self):
        assert CodeAgent(agent_id="custom_code_agent").agent_id == "custom_code_agent"

    def test_code_agent_tools_whitelist(self):
        assert CodeAgent.ALLOWED_TOOLS == {
            "read_file", "write_file", "execute_command", "list_directory",
            "search_files", "ast_search", "analyze_project_structure", "get_current_dir",
        }

    @pytest.mark.parametrize("ttype", ["code_generation", "code_refactoring", "bug_fixing", "code_review", "other"])
    def test_code_agent_task_types(self, fake_engine_factory, ttype):
        agent = CodeAgent(config={"engine_factory": fake_engine_factory("Final Answer: done")})
        result = agent.process_task(_task(ttype, "任务"))
        assert result.success is True
        assert result.task_id == "task_001"
        assert result.agent_id == agent.agent_id
        assert result.metadata["task_type"] == ttype


# ==================== RAGAgent ====================

class TestRAGAgent:
    def test_rag_agent_creation(self):
        agent = RAGAgent()
        assert agent.agent_id == "rag_agent_1"
        assert agent.agent_type == AgentType.RAG
        for cap in ("knowledge_retrieval", "document_search", "knowledge_extraction",
                    "literature_review", "general"):
            assert cap in agent.capabilities

    def test_rag_agent_process_knowledge_retrieval(self):
        """复用 rag_pipeline，注入桩引擎；来源结构化到 sources。"""
        import agent_tools

        class _StubEngine:
            query_engine = object()

            def query_with_sources(self, question, progress_callback=None):
                return {
                    "answer": f"针对『{question}』的检索答案",
                    "sources": [{"content": "c", "file": "ml.md", "score": 0.72}],
                }

        agent_tools.set_rag_engine(_StubEngine())
        try:
            agent = RAGAgent()
            result = agent.process_task(_task("knowledge_retrieval", "查询机器学习算法"))
            assert result.success is True
            assert result.output.startswith("针对")  # 输出即答案，不带标题
            assert result.metadata["query"] == "查询机器学习算法"
            assert result.metadata["task_type"] == "knowledge_retrieval"
            assert result.sources and result.sources[0]["kind"] == "kb"
            assert result.sources[0]["file"] == "ml.md"
            assert result.sources[0]["score"] == 0.72
            assert result.metadata["kb_hits"] == 1
        finally:
            agent_tools.set_rag_engine(None)

    @pytest.mark.parametrize("ttype,marker", [
        ("document_search", "找出与下述主题相关的文档"),
        ("knowledge_extraction", "提取关于下述主题的关键知识点"),
        ("literature_review", "综述相关文档"),
        ("general", "某产品售价"),
    ])
    def test_rag_agent_variants_go_through_pipeline(self, monkeypatch, ttype, marker):
        """document_search / knowledge_extraction / literature_review 不再返回桩数据，
        而是以变体提问走 answer_question。"""
        import agent_tools
        import rag_pipeline

        seen = {}

        def fake_answer(engine, question, **kwargs):
            seen["question"] = question
            seen["context"] = kwargs.get("context")
            return {"answer": "真实答案", "kb_sources": [], "web_sources": [
                {"title": "站点", "url": "https://x"}]}

        monkeypatch.setattr(rag_pipeline, "answer_question", fake_answer)
        agent_tools.set_rag_engine(object())
        try:
            agent = RAGAgent()
            agent.conversation_context = "CTX"
            result = agent.process_task(_task(ttype, "某产品售价"))
            assert result.success is True
            assert marker in seen["question"]
            assert seen["context"] == "CTX"
            assert "真实答案" in result.output
            assert result.sources == [{"kind": "web", "title": "站点", "url": "https://x", }]
            assert result.metadata["web_hits"] == 1
            assert "找到 5 个相关文档片段" not in result.output
        finally:
            agent_tools.set_rag_engine(None)

    def test_rag_agent_general_task_uses_pipeline(self, monkeypatch):
        """低相关片段被过滤，不当作知识库来源展示。"""
        import agent_tools
        import rag_pipeline

        class _NoiseEngine:
            query_engine = object()

            def query_with_sources(self, question, progress_callback=None):
                return {
                    "answer": "无关内容",
                    "sources": [{"content": "http_status:404", "file": "cloudflare.md", "score": 0.398}],
                }

        monkeypatch.setattr(rag_pipeline, "simple_web_search", lambda q: "")
        monkeypatch.setattr(rag_pipeline, "augment_with_web_search", lambda q, progress=None: "")
        monkeypatch.setattr(rag_pipeline, "llm_direct_answer", lambda p: "基于模型的回答")

        agent_tools.set_rag_engine(_NoiseEngine())
        try:
            agent = RAGAgent()
            result = agent.process_task(_task("general", "某产品售价"))
            assert "cloudflare.md" not in result.output
            assert "0.398" not in result.output
            assert result.sources == []
        finally:
            agent_tools.set_rag_engine(None)

    def test_rag_agent_without_engine_falls_back_to_tool(self, monkeypatch):
        import agent_tools
        agent_tools.set_rag_engine(None)
        monkeypatch.setattr(agent_tools, "query_knowledge_base", lambda q: "[提示] 知识库未初始化")
        result = RAGAgent().process_task(_task("knowledge_retrieval", "q"))
        assert result.success is True
        assert "知识库未初始化" in result.output

    def test_rag_agent_empty_request(self):
        result = RAGAgent().process_task(_task("knowledge_retrieval", ""))
        assert "[提示] 空请求" in result.output

    def test_rag_agent_pipeline_error(self, monkeypatch):
        import agent_tools
        import rag_pipeline

        def boom(*a, **k):
            raise RuntimeError("db down")

        monkeypatch.setattr(rag_pipeline, "answer_question", boom)
        agent_tools.set_rag_engine(object())
        try:
            result = RAGAgent().process_task(_task("knowledge_retrieval", "q"))
            assert result.success is False
            assert "db down" in result.error_message
        finally:
            agent_tools.set_rag_engine(None)

    def test_rag_agent_process_task_exception(self, monkeypatch):
        agent = RAGAgent()
        monkeypatch.setattr(agent, "_handle_retrieval", lambda t: (_ for _ in ()).throw(ValueError("x")))
        result = agent.process_task(_task("knowledge_retrieval", "q"))
        assert result.success is False
        assert "x" in result.error_message


# ==================== TestAgent / DocAgent / AuditAgent ====================

class TestTestAgent:
    def test_test_agent_creation(self):
        agent = TestAgent()
        assert agent.agent_id == "test_agent_1"
        assert agent.agent_type == AgentType.TEST
        for cap in ("testing", "test_generation", "coverage_analysis", "quality_assessment"):
            assert cap in agent.capabilities

    def test_test_agent_tools_whitelist(self):
        assert TestAgent.ALLOWED_TOOLS == {
            "read_file", "write_file", "execute_command", "search_files", "code_quality_check"}

    @pytest.mark.parametrize("ttype", ["testing", "test_generation", "coverage_analysis", "quality_assessment"])
    def test_test_agent_task_types(self, fake_engine_factory, ttype):
        agent = TestAgent(config={"engine_factory": fake_engine_factory("Final Answer: 3 passed")})
        result = agent.process_task(_task(ttype, "测试"))
        assert result.success is True
        assert "3 passed" in result.output
        assert result.metadata["task_type"] == ttype


class TestDocAgent:
    def test_doc_agent_creation(self):
        agent = DocAgent()
        assert agent.agent_id == "doc_agent_1"
        assert agent.agent_type == AgentType.DOC
        for cap in ("documentation", "api_documentation", "technical_writing", "user_guide"):
            assert cap in agent.capabilities

    def test_doc_agent_tools_whitelist(self):
        assert DocAgent.ALLOWED_TOOLS == {
            "read_file", "write_file", "list_directory", "search_files",
            "query_knowledge_base", "web_search"}

    @pytest.mark.parametrize("ttype", ["documentation", "api_documentation", "technical_writing", "user_guide"])
    def test_doc_agent_task_types(self, fake_engine_factory, ttype):
        agent = DocAgent(config={"engine_factory": fake_engine_factory("Final Answer: README.md 已写")})
        result = agent.process_task(_task(ttype, "文档"))
        assert result.success is True
        assert result.metadata["task_type"] == ttype


class TestAuditAgent:
    def test_audit_agent_creation(self):
        agent = AuditAgent()
        assert agent.agent_id == "audit_agent_1"
        assert agent.agent_type == AgentType.AUDIT
        for cap in ("audit", "security_check", "compliance_verification", "performance_audit"):
            assert cap in agent.capabilities

    def test_audit_agent_tools_whitelist_is_readonly(self):
        assert "write_file" not in AuditAgent.ALLOWED_TOOLS
        assert AuditAgent.ALLOWED_TOOLS == {
            "read_file", "search_files", "code_quality_check", "ast_search",
            "git_analyze", "execute_command"}

    @pytest.mark.parametrize("ttype", ["audit", "security_check", "compliance_verification", "performance_audit"])
    def test_audit_agent_task_types(self, fake_engine_factory, ttype):
        agent = AuditAgent(config={"engine_factory": fake_engine_factory("Final Answer: [高] 无")})
        result = agent.process_task(_task(ttype, "审计"))
        assert result.success is True
        assert result.metadata["task_type"] == ttype


class TestEphemeralContext:
    def test_ephemeral_context(self):
        ctx = EphemeralContext()
        assert ctx.build_messages("SYS") == [{"role": "system", "content": "SYS"}]
        assert ctx.build_messages() == [{"role": "system", "content": ""}]
        assert ctx.record("a", "b") is None
        assert ctx.clear() is True
