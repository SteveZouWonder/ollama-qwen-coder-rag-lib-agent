"""
测试专业Agent（CodeAgent, RAGAgent, TestAgent, DocAgent, AuditAgent）
"""
import pytest
from agents.code_agent import CodeAgent
from agents.rag_agent import RAGAgent
from agents.test_agent import TestAgent
from agents.doc_agent import DocAgent
from agents.audit_agent import AuditAgent
from agents.agent_types import AgentTask, AgentType, AgentState


class TestCodeAgent:
    """测试CodeAgent"""
    
    def test_code_agent_creation(self):
        """测试创建CodeAgent"""
        agent = CodeAgent()
        
        assert agent.agent_id == "code_agent_1"
        assert agent.agent_type == AgentType.CODE
        assert "code_generation" in agent.capabilities
        assert "code_refactoring" in agent.capabilities
        assert "bug_fixing" in agent.capabilities
        assert "code_review" in agent.capabilities
        assert "file_operations" in agent.capabilities
        assert agent.get_state() == AgentState.IDLE
    
    def test_code_agent_custom_id(self):
        """测试自定义ID的CodeAgent"""
        agent = CodeAgent(agent_id="custom_code_agent")
        
        assert agent.agent_id == "custom_code_agent"
    
    def test_code_agent_process_code_generation(self):
        """测试CodeAgent处理代码生成任务"""
        agent = CodeAgent()
        
        task = AgentTask(
            task_id="task_001",
            task_type="code_generation",
            description="实现登录功能",
            required_capabilities=["code_generation"],
            input_data={"request": "实现用户登录"}
        )
        
        result = agent.process_task(task)
        
        assert result.success is True
        assert result.agent_id == agent.agent_id
        assert result.task_id == "task_001"
        assert "代码生成结果" in result.output
        assert result.metadata["task_type"] == "code_generation"
    
    def test_code_agent_process_code_refactoring(self):
        """测试CodeAgent处理代码重构任务"""
        agent = CodeAgent()
        
        task = AgentTask(
            task_id="task_002",
            task_type="code_refactoring",
            description="重构代码",
            required_capabilities=["code_refactoring"],
            input_data={"request": "重构旧代码"}
        )
        
        result = agent.process_task(task)
        
        assert result.success is True
        assert result.metadata["task_type"] == "code_refactoring"
    
    def test_code_agent_process_bug_fixing(self):
        """测试CodeAgent处理Bug修复任务"""
        agent = CodeAgent()
        
        task = AgentTask(
            task_id="task_003",
            task_type="bug_fixing",
            description="修复Bug",
            required_capabilities=["bug_fixing"],
            input_data={"request": "修复内存泄漏"}
        )
        
        result = agent.process_task(task)
        
        assert result.success is True
        assert result.metadata["task_type"] == "bug_fixing"
        assert result.metadata["bugs_fixed"] == 2
    
    def test_code_agent_process_code_review(self):
        """测试CodeAgent处理代码审查任务"""
        agent = CodeAgent()
        
        task = AgentTask(
            task_id="task_004",
            task_type="code_review",
            description="代码审查",
            required_capabilities=["code_review"],
            input_data={"request": "审查代码质量"}
        )
        
        result = agent.process_task(task)
        
        assert result.success is True
        assert result.metadata["task_type"] == "code_review"
        assert result.metadata["issues_found"] == 3
    
    def test_code_agent_process_general_task(self):
        """测试CodeAgent处理通用任务"""
        agent = CodeAgent()
        
        task = AgentTask(
            task_id="task_005",
            task_type="general",
            description="通用任务",
            required_capabilities=["code_generation"],
            input_data={"request": "通用请求"}
        )
        
        result = agent.process_task(task)
        
        assert result.success is True
        assert result.metadata["handled_by"] == "CodeAgent"


class TestRAGAgent:
    """测试RAGAgent"""
    
    def test_rag_agent_creation(self):
        """测试创建RAGAgent"""
        agent = RAGAgent()
        
        assert agent.agent_id == "rag_agent_1"
        assert agent.agent_type == AgentType.RAG
        assert "knowledge_retrieval" in agent.capabilities
        assert "document_search" in agent.capabilities
        assert "knowledge_extraction" in agent.capabilities
        assert "literature_review" in agent.capabilities
    
    def test_rag_agent_process_knowledge_retrieval(self):
        """测试RAGAgent处理知识检索任务"""
        agent = RAGAgent()
        
        task = AgentTask(
            task_id="task_001",
            task_type="knowledge_retrieval",
            description="检索知识",
            required_capabilities=["knowledge_retrieval"],
            input_data={"request": "查询机器学习算法"}
        )
        
        result = agent.process_task(task)
        
        assert result.success is True
        assert "知识库检索结果" in result.output
        assert result.metadata["task_type"] == "knowledge_retrieval"
    
    def test_rag_agent_process_document_search(self):
        """测试RAGAgent处理文档搜索任务"""
        agent = RAGAgent()
        
        task = AgentTask(
            task_id="task_002",
            task_type="document_search",
            description="搜索文档",
            required_capabilities=["document_search"],
            input_data={"request": "搜索相关文档"}
        )
        
        result = agent.process_task(task)
        
        assert result.success is True
        assert result.metadata["task_type"] == "document_search"
    
    def test_rag_agent_process_knowledge_extraction(self):
        """测试RAGAgent处理知识提取任务"""
        agent = RAGAgent()
        
        task = AgentTask(
            task_id="task_003",
            task_type="knowledge_extraction",
            description="提取知识",
            required_capabilities=["knowledge_extraction"],
            input_data={"request": "提取关键概念"}
        )
        
        result = agent.process_task(task)
        
        assert result.success is True
        assert result.metadata["task_type"] == "knowledge_extraction"
        assert result.metadata["concepts_extracted"] == 2
    
    def test_rag_agent_process_literature_review(self):
        """测试RAGAgent处理文献综述任务"""
        agent = RAGAgent()
        
        task = AgentTask(
            task_id="task_004",
            task_type="literature_review",
            description="文献综述",
            required_capabilities=["literature_review"],
            input_data={"request": "综述深度学习"}
        )
        
        result = agent.process_task(task)
        
        assert result.success is True
        assert result.metadata["task_type"] == "literature_review"
        assert result.metadata["papers_reviewed"] == 10


class TestTestAgent:
    """测试TestAgent"""
    
    def test_test_agent_creation(self):
        """测试创建TestAgent"""
        agent = TestAgent()
        
        assert agent.agent_id == "test_agent_1"
        assert agent.agent_type == AgentType.TEST
        assert "testing" in agent.capabilities
        assert "test_generation" in agent.capabilities
        assert "coverage_analysis" in agent.capabilities
        assert "quality_assessment" in agent.capabilities
    
    def test_test_agent_process_testing(self):
        """测试TestAgent处理测试任务"""
        agent = TestAgent()
        
        task = AgentTask(
            task_id="task_001",
            task_type="testing",
            description="执行测试",
            required_capabilities=["testing"],
            input_data={"request": "运行单元测试"}
        )
        
        result = agent.process_task(task)
        
        assert result.success is True
        assert "测试执行结果" in result.output
        assert result.metadata["task_type"] == "testing"
        assert result.metadata["total_tests"] == 25
    
    def test_test_agent_process_test_generation(self):
        """测试TestAgent处理测试生成任务"""
        agent = TestAgent()
        
        task = AgentTask(
            task_id="task_002",
            task_type="test_generation",
            description="生成测试",
            required_capabilities=["test_generation"],
            input_data={"request": "为函数生成测试"}
        )
        
        result = agent.process_task(task)
        
        assert result.success is True
        assert result.metadata["task_type"] == "test_generation"
        assert result.metadata["tests_generated"] == 5
        assert "unittest" in result.output
    
    def test_test_agent_process_coverage_analysis(self):
        """测试TestAgent处理覆盖率分析任务"""
        agent = TestAgent()
        
        task = AgentTask(
            task_id="task_003",
            task_type="coverage_analysis",
            description="覆盖率分析",
            required_capabilities=["coverage_analysis"],
            input_data={"request": "分析测试覆盖率"}
        )
        
        result = agent.process_task(task)
        
        assert result.success is True
        assert result.metadata["task_type"] == "coverage_analysis"
        assert result.metadata["line_coverage"] == 0.85
    
    def test_test_agent_process_quality_assessment(self):
        """测试TestAgent处理质量评估任务"""
        agent = TestAgent()
        
        task = AgentTask(
            task_id="task_004",
            task_type="quality_assessment",
            description="质量评估",
            required_capabilities=["quality_assessment"],
            input_data={"request": "评估代码质量"}
        )
        
        result = agent.process_task(task)
        
        assert result.success is True
        assert result.metadata["task_type"] == "quality_assessment"
        assert result.metadata["quality_score"] == 8.2


class TestDocAgent:
    """测试DocAgent"""
    
    def test_doc_agent_creation(self):
        """测试创建DocAgent"""
        agent = DocAgent()
        
        assert agent.agent_id == "doc_agent_1"
        assert agent.agent_type == AgentType.DOC
        assert "documentation" in agent.capabilities
        assert "api_documentation" in agent.capabilities
        assert "technical_writing" in agent.capabilities
        assert "user_guide" in agent.capabilities
    
    def test_doc_agent_process_documentation(self):
        """测试DocAgent处理文档生成任务"""
        agent = DocAgent()
        
        task = AgentTask(
            task_id="task_001",
            task_type="documentation",
            description="生成文档",
            required_capabilities=["documentation"],
            input_data={"request": "编写项目文档"}
        )
        
        result = agent.process_task(task)
        
        assert result.success is True
        assert "文档生成结果" in result.output
        assert result.metadata["task_type"] == "documentation"
    
    def test_doc_agent_process_api_documentation(self):
        """测试DocAgent处理API文档任务"""
        agent = DocAgent()
        
        task = AgentTask(
            task_id="task_002",
            task_type="api_documentation",
            description="API文档",
            required_capabilities=["api_documentation"],
            input_data={"request": "编写API文档"}
        )
        
        result = agent.process_task(task)
        
        assert result.success is True
        assert result.metadata["task_type"] == "api_documentation"
        assert result.metadata["endpoints_documented"] == 5
    
    def test_doc_agent_process_technical_writing(self):
        """测试DocAgent处理技术写作任务"""
        agent = DocAgent()
        
        task = AgentTask(
            task_id="task_003",
            task_type="technical_writing",
            description="技术文档",
            required_capabilities=["technical_writing"],
            input_data={"request": "编写技术架构文档"}
        )
        
        result = agent.process_task(task)
        
        assert result.success is True
        assert result.metadata["task_type"] == "technical_writing"
    
    def test_doc_agent_process_user_guide(self):
        """测试DocAgent处理用户指南任务"""
        agent = DocAgent()
        
        task = AgentTask(
            task_id="task_004",
            task_type="user_guide",
            description="用户指南",
            required_capabilities=["user_guide"],
            input_data={"request": "编写用户使用指南"}
        )
        
        result = agent.process_task(task)
        
        assert result.success is True
        assert result.metadata["task_type"] == "user_guide"
        assert result.metadata["steps"] == 10


class TestAuditAgent:
    """测试AuditAgent"""
    
    def test_audit_agent_creation(self):
        """测试创建AuditAgent"""
        agent = AuditAgent()
        
        assert agent.agent_id == "audit_agent_1"
        assert agent.agent_type == AgentType.AUDIT
        assert "audit" in agent.capabilities
        assert "security_check" in agent.capabilities
        assert "compliance_verification" in agent.capabilities
        assert "performance_audit" in agent.capabilities
    
    def test_audit_agent_process_audit(self):
        """测试AuditAgent处理审计任务"""
        agent = AuditAgent()
        
        task = AgentTask(
            task_id="task_001",
            task_type="audit",
            description="审计",
            required_capabilities=["audit"],
            input_data={"request": "进行代码审计"}
        )
        
        result = agent.process_task(task)
        
        assert result.success is True
        assert "审计结果" in result.output
        assert result.metadata["task_type"] == "audit"
    
    def test_audit_agent_process_security_check(self):
        """测试AuditAgent处理安全检查任务"""
        agent = AuditAgent()
        
        task = AgentTask(
            task_id="task_002",
            task_type="security_check",
            description="安全检查",
            required_capabilities=["security_check"],
            input_data={"request": "进行安全扫描"}
        )
        
        result = agent.process_task(task)
        
        assert result.success is True
        assert result.metadata["task_type"] == "security_check"
        assert result.metadata["vulnerabilities_found"] == 3
        assert result.metadata["critical_count"] == 1
    
    def test_audit_agent_process_compliance_verification(self):
        """测试AuditAgent处理合规性验证任务"""
        agent = AuditAgent()
        
        task = AgentTask(
            task_id="task_003",
            task_type="compliance_verification",
            description="合规性验证",
            required_capabilities=["compliance_verification"],
            input_data={"request": "验证GDPR合规性"}
        )
        
        result = agent.process_task(task)
        
        assert result.success is True
        assert result.metadata["task_type"] == "compliance_verification"
        assert "GDPR" in result.metadata["standards_checked"]
    
    def test_audit_agent_process_performance_audit(self):
        """测试AuditAgent处理性能审计任务"""
        agent = AuditAgent()
        
        task = AgentTask(
            task_id="task_004",
            task_type="performance_audit",
            description="性能审计",
            required_capabilities=["performance_audit"],
            input_data={"request": "审计系统性能"}
        )
        
        result = agent.process_task(task)
        
        assert result.success is True
        assert result.metadata["task_type"] == "performance_audit"
        assert result.metadata["response_time"] == 120
        assert result.metadata["throughput"] == 1000
    
    def test_code_agent_custom_config(self):
        """测试CodeAgent使用自定义配置"""
        config = {"custom_key": "custom_value"}
        agent = CodeAgent(config=config)
        
        assert agent.config == config
    
    def test_rag_agent_custom_config(self):
        """测试RAGAgent使用自定义配置"""
        config = {"custom_key": "custom_value"}
        agent = RAGAgent(config=config)
        
        assert agent.config == config
    
    def test_test_agent_custom_config(self):
        """测试TestAgent使用自定义配置"""
        config = {"custom_key": "custom_value"}
        agent = TestAgent(config=config)
        
        assert agent.config == config
    
    def test_doc_agent_custom_config(self):
        """测试DocAgent使用自定义配置"""
        config = {"custom_key": "custom_value"}
        agent = DocAgent(config=config)
        
        assert agent.config == config
    
    def test_audit_agent_custom_config(self):
        """测试AuditAgent使用自定义配置"""
        config = {"custom_key": "custom_value"}
        agent = AuditAgent(config=config)
        
        assert agent.config == config
    
    def test_code_agent_process_error_handling(self):
        """测试CodeAgent错误处理"""
        agent = CodeAgent()
        
        # 创建一个可能触发错误处理的情况
        task = AgentTask(
            task_id="task_001",
            task_type="unknown_type",
            description="未知任务类型",
            required_capabilities=["code_generation"],
            input_data={"request": "测试"}
        )
        
        result = agent.process_task(task)
        
        # 即使是未知类型，也应该返回结果而不是抛出异常
        assert result is not None
        assert result.task_id == "task_001"
    
    def test_rag_agent_exception_handling(self):
        """测试RAGAgent异常处理"""
        agent = RAGAgent()
        
        # 创建一个可能触发异常的情况
        task = AgentTask(
            task_id="task_001",
            task_type="error_case",
            description="错误情况",
            required_capabilities=["knowledge_retrieval"],
            input_data={"request": "测试"}
        )
        
        result = agent.process_task(task)
        
        # 应该返回结果而不是抛出异常
        assert result is not None
        assert result.task_id == "task_001"
    
    def test_test_agent_exception_handling(self):
        """测试TestAgent异常处理"""
        agent = TestAgent()
        
        task = AgentTask(
            task_id="task_001",
            task_type="error_case",
            description="错误情况",
            required_capabilities=["testing"],
            input_data={"request": "测试"}
        )
        
        result = agent.process_task(task)
        
        # 应该返回结果而不是抛出异常
        assert result is not None
        assert result.task_id == "task_001"
    
    def test_doc_agent_exception_handling(self):
        """测试DocAgent异常处理"""
        agent = DocAgent()
        
        task = AgentTask(
            task_id="task_001",
            task_type="error_case",
            description="错误情况",
            required_capabilities=["documentation"],
            input_data={"request": "测试"}
        )
        
        result = agent.process_task(task)
        
        # 应该返回结果而不是抛出异常
        assert result is not None
        assert result.task_id == "task_001"
    
    def test_audit_agent_exception_handling(self):
        """测试AuditAgent异常处理"""
        agent = AuditAgent()
        
        task = AgentTask(
            task_id="task_001",
            task_type="error_case",
            description="错误情况",
            required_capabilities=["audit"],
            input_data={"request": "测试"}
        )
        
        result = agent.process_task(task)
        
        # 应该返回结果而不是抛出异常
        assert result is not None
        assert result.task_id == "task_001"
    
    def test_code_agent_empty_request(self):
        """测试CodeAgent处理空请求"""
        agent = CodeAgent()
        
        task = AgentTask(
            task_id="task_001",
            task_type="code_generation",
            description="空请求",
            required_capabilities=["code_generation"],
            input_data={}
        )
        
        result = agent.process_task(task)
        
        assert result is not None
        assert result.success is True
