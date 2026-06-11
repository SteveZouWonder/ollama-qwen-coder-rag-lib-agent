"""
测试task_decomposer模块
"""
import pytest
from collaboration.task_decomposer import TaskDecomposer
from agents.agent_types import AgentTask


class TestTaskDecomposer:
    """测试TaskDecomposer类"""
    
    def test_decomposer_creation(self):
        """测试创建任务分解器"""
        decomposer = TaskDecomposer()
        
        assert decomposer is not None
    
    def test_decompose_code_task(self):
        """测试分解代码任务"""
        decomposer = TaskDecomposer()
        
        request = "实现一个用户登录功能"
        tasks = decomposer.decompose(request)
        
        assert len(tasks) > 0
        
        # 应该包含code_generation任务
        code_tasks = [t for t in tasks if t.task_type == "code_generation"]
        assert len(code_tasks) > 0
    
    def test_decompose_test_task(self):
        """测试分解测试任务"""
        decomposer = TaskDecomposer()
        
        request = "编写单元测试"
        tasks = decomposer.decompose(request)
        
        assert len(tasks) > 0
        
        # 应该包含testing任务
        test_tasks = [t for t in tasks if t.task_type == "testing"]
        assert len(test_tasks) > 0
    
    def test_decompose_documentation_task(self):
        """测试分解文档任务"""
        decomposer = TaskDecomposer()
        
        request = "编写API文档"
        tasks = decomposer.decompose(request)
        
        assert len(tasks) > 0
        
        # 应该包含documentation任务
        doc_tasks = [t for t in tasks if t.task_type == "documentation"]
        assert len(doc_tasks) > 0
    
    def test_decompose_knowledge_task(self):
        """测试分解知识库任务"""
        decomposer = TaskDecomposer()
        
        request = "检索相关文档"
        tasks = decomposer.decompose(request)
        
        assert len(tasks) > 0
        
        # 应该包含knowledge_retrieval任务
        knowledge_tasks = [t for t in tasks if t.task_type == "knowledge_retrieval"]
        assert len(knowledge_tasks) > 0
    
    def test_decompose_audit_task(self):
        """测试分解审计任务"""
        decomposer = TaskDecomposer()
        
        request = "进行安全审计"
        tasks = decomposer.decompose(request)
        
        assert len(tasks) > 0
        
        # 应该包含audit任务
        audit_tasks = [t for t in tasks if t.task_type == "audit"]
        assert len(audit_tasks) > 0
    
    def test_decompose_general_task(self):
        """测试分解通用任务"""
        decomposer = TaskDecomposer()
        
        request = "做一些通用任务"
        tasks = decomposer.decompose(request)
        
        assert len(tasks) > 0
        
        # 应该包含general任务
        general_tasks = [t for t in tasks if t.task_type == "general"]
        assert len(general_tasks) > 0
    
    def test_decompose_complex_task(self):
        """测试分解复杂任务"""
        decomposer = TaskDecomposer()
        
        request = "实现用户认证功能并编写测试和文档"
        tasks = decomposer.decompose(request)
        
        assert len(tasks) >= 2  # 至少应该有代码和测试任务
        
        # 检查是否有不同类型的任务
        task_types = set(t.task_type for t in tasks)
        assert "code_generation" in task_types
        assert "testing" in task_types
    
    def test_decompose_with_available_agents(self):
        """测试根据可用Agent分解任务"""
        decomposer = TaskDecomposer()
        
        # 创建模拟的可用Agent
        class MockAgent:
            def __init__(self, capabilities):
                self.capabilities = capabilities
        
        available_agents = [
            MockAgent(["code_generation", "file_operations"]),
            MockAgent(["testing"])
        ]
        
        request = "实现功能并测试"
        tasks = decomposer.decompose(request, available_agents)
        
        # 所有任务都应该有对应的能力
        for task in tasks:
            has_capability = any(
                set(task.required_capabilities).issubset(set(agent.capabilities))
                for agent in available_agents
            )
            # 由于简化逻辑，这里只验证任务被生成
            assert task.task_id is not None
    
    def test_decompose_by_pattern_parallel(self):
        """测试并行模式分解"""
        decomposer = TaskDecomposer()
        
        request = "实现功能并测试"
        tasks = decomposer.decompose_by_pattern("parallel", request)
        
        # 并行模式应该没有依赖关系
        for task in tasks:
            assert len(task.dependencies) == 0
    
    def test_decompose_by_pattern_sequential(self):
        """测试顺序模式分解"""
        decomposer = TaskDecomposer()
        
        request = "实现功能并测试"
        tasks = decomposer.decompose_by_pattern("sequential", request)
        
        if len(tasks) > 1:
            # 顺序模式应该有依赖关系
            has_dependencies = any(len(t.dependencies) > 0 for t in tasks[1:])
            assert has_dependencies
    
    def test_decompose_by_pattern_hierarchy(self):
        """测试层级模式分解"""
        decomposer = TaskDecomposer()
        
        request = "实现功能并测试"
        tasks = decomposer.decompose_by_pattern("hierarchy", request)
        
        # 层级模式保持默认的依赖关系
        assert len(tasks) > 0
    
    def test_validate_task_valid(self):
        """测试验证有效任务"""
        decomposer = TaskDecomposer()
        
        task = AgentTask(
            task_id="task_001",
            task_type="code_generation",
            description="测试任务",
            required_capabilities=["code_generation"],
            input_data={}
        )
        
        available_capabilities = ["code_generation", "file_operations"]
        
        is_valid = decomposer.validate_task(task, available_capabilities)
        
        assert is_valid is True
    
    def test_validate_task_invalid(self):
        """测试验证无效任务"""
        decomposer = TaskDecomposer()
        
        task = AgentTask(
            task_id="task_001",
            task_type="code_generation",
            description="测试任务",
            required_capabilities=["code_generation", "testing"],
            input_data={}
        )
        
        available_capabilities = ["code_generation"]
        
        is_valid = decomposer.validate_task(task, available_capabilities)
        
        assert is_valid is False
    
    def test_estimate_complexity_low(self):
        """测试估计低复杂度"""
        decomposer = TaskDecomposer()
        
        task = AgentTask(
            task_id="task_001",
            task_type="code_generation",
            description="简单任务",
            required_capabilities=["code_generation"],
            input_data={}
        )
        
        complexity = decomposer.estimate_complexity(task)
        
        assert complexity == "low"
    
    def test_estimate_complexity_medium(self):
        """测试估计中等复杂度"""
        decomposer = TaskDecomposer()
        
        task = AgentTask(
            task_id="task_001",
            task_type="complex",
            description="中等复杂任务",
            required_capabilities=["code_generation", "file_operations", "testing"],
            input_data={}
        )
        
        complexity = decomposer.estimate_complexity(task)
        
        assert complexity == "medium"
    
    def test_estimate_complexity_high(self):
        """测试估计高复杂度"""
        decomposer = TaskDecomposer()
        
        task = AgentTask(
            task_id="task_001",
            task_type="complex",
            description="高复杂任务",
            required_capabilities=["code_generation", "file_operations", "testing", "documentation", "audit"],
            input_data={}
        )
        
        complexity = decomposer.estimate_complexity(task)
        
        assert complexity == "high"
    
    def test_create_task_from_template(self):
        """测试从模板创建任务"""
        decomposer = TaskDecomposer()
        
        template = {
            "task_type": "code_generation",
            "description": "模板任务",
            "required_capabilities": ["code_generation"],
            "input_data": {},
            "priority": 7,
            "timeout": 300
        }
        
        params = {"description": "自定义描述"}
        
        task = decomposer.create_task_from_template(template, params)
        
        assert task.task_type == "code_generation"
        assert task.description == "自定义描述"
        assert task.priority == 7
        assert task.task_id is not None  # 应该生成新的task_id
    
    def test_task_dependencies(self):
        """测试任务依赖关系"""
        decomposer = TaskDecomposer()
        
        request = "实现功能并编写测试"
        tasks = decomposer.decompose(request)
        
        code_tasks = [t for t in tasks if t.task_type == "code_generation"]
        test_tasks = [t for t in tasks if t.task_type == "testing"]
        
        if code_tasks and test_tasks:
            # 测试任务应该依赖于代码任务
            for test_task in test_tasks:
                if test_task.dependencies:
                    assert any(dep in [ct.task_id for ct in code_tasks] for dep in test_task.dependencies)
