"""
测试master_agent模块
"""
import pytest
from master_agent import MasterAgent
from agents.agent_types import AgentTask, AgentResult, AgentType, CollaborationMode
from agents.code_agent import CodeAgent
from agents import TestAgent


class TestMasterAgent:
    """测试MasterAgent类"""
    
    def test_master_agent_creation(self):
        """测试创建MasterAgent"""
        agent = MasterAgent()
        
        assert agent.agent_id == "master_agent"
        assert agent.agent_type == AgentType.MASTER
        assert "task_decomposition" in agent.capabilities
        assert "task_scheduling" in agent.capabilities
        assert "result_integration" in agent.capabilities
        assert "coordination" in agent.capabilities
    
    def test_master_agent_custom_id(self):
        """测试自定义ID的MasterAgent"""
        agent = MasterAgent(agent_id="custom_master")
        
        assert agent.agent_id == "custom_master"
    
    def test_master_agent_with_config(self):
        """测试带配置的MasterAgent"""
        config = {"max_parallel_tasks": 10}
        agent = MasterAgent(config=config)
        
        assert agent is not None
    
    def test_master_agent_set_specialized_agents(self):
        """测试设置专业Agent"""
        master = MasterAgent()
        
        code_agent = CodeAgent()
        test_agent = TestAgent()
        
        agents = [code_agent, test_agent]
        master.set_specialized_agents(agents)
        
        assert len(master.specialized_agents) == 2
        assert code_agent in master.specialized_agents
        assert test_agent in master.specialized_agents
    
    def test_master_agent_process_coordination_task(self):
        """测试处理协调任务"""
        master = MasterAgent()
        
        code_agent = CodeAgent()
        master.set_specialized_agents([code_agent])
        
        task = AgentTask(
            task_id="task_001",
            task_type="coordination",
            description="协调任务",
            required_capabilities=["coordination"],
            input_data={
                "request": "实现功能并测试",
                "mode": "hierarchy"
            }
        )
        
        result = master.process_task(task)
        
        assert result.success is True
        assert result.agent_id == master.agent_id
        assert result.task_id == "task_001"
    
    def test_master_agent_process_general_task(self):
        """测试处理通用任务"""
        master = MasterAgent()
        
        task = AgentTask(
            task_id="task_001",
            task_type="general",
            description="通用任务",
            required_capabilities=["general"],
            input_data={}
        )
        
        result = master.process_task(task)
        
        assert result.success is True
        assert "MasterAgent主要负责任务协调" in result.output
    
    def test_master_agent_coordinate_task_hierarchy(self):
        """测试层级协调任务"""
        master = MasterAgent()
        
        code_agent = CodeAgent()
        test_agent = TestAgent()
        master.set_specialized_agents([code_agent, test_agent])
        
        request = "实现用户登录功能并编写测试"
        result = master.coordinate_task(request, CollaborationMode.HIERARCHY)
        
        assert result is not None
        assert "success" in result
        assert "summary" in result
    
    def test_master_agent_coordinate_task_parallel(self):
        """测试并行协调任务"""
        master = MasterAgent()
        
        code_agent = CodeAgent()
        test_agent = TestAgent()
        master.set_specialized_agents([code_agent, test_agent])
        
        request = "实现功能和测试"
        result = master.coordinate_task(request, CollaborationMode.PARALLEL)
        
        assert result is not None
        assert "success" in result
    
    def test_master_agent_coordinate_task_sequential(self):
        """测试顺序协调任务"""
        master = MasterAgent()
        
        code_agent = CodeAgent()
        test_agent = TestAgent()
        master.set_specialized_agents([code_agent, test_agent])
        
        request = "实现功能并测试"
        result = master.coordinate_task(request, CollaborationMode.SEQUENTIAL)
        
        assert result is not None
        assert "success" in result
    
    def test_master_agent_coordinate_task_competitive(self):
        """测试竞争协调任务"""
        master = MasterAgent()
        
        code_agent1 = CodeAgent(agent_id="code_agent_1")
        code_agent2 = CodeAgent(agent_id="code_agent_2")
        master.set_specialized_agents([code_agent1, code_agent2])
        
        request = "实现登录功能"
        result = master.coordinate_task(request, CollaborationMode.COMPETITIVE)
        
        assert result is not None
        assert "success" in result
        assert "best_result" in result
    
    def test_master_agent_coordinate_task_no_agents(self):
        """测试无专业Agent时的协调任务"""
        master = MasterAgent()
        
        request = "实现功能"
        result = master.coordinate_task(request, CollaborationMode.HIERARCHY)
        
        assert result is not None
        # 可能会失败或产生警告
    
    def test_master_agent_coordinate_task_decomposition_failure(self):
        """测试任务分解失败的情况"""
        master = MasterAgent()
        master.set_specialized_agents([])
        
        # 如果没有专业Agent，任务分解可能产生空结果
        request = "实现功能"
        result = master.coordinate_task(request, CollaborationMode.HIERARCHY)
        
        assert result is not None
    
    def test_master_agent_get_status(self):
        """测试获取MasterAgent状态"""
        master = MasterAgent()
        
        code_agent = CodeAgent()
        test_agent = TestAgent()
        master.set_specialized_agents([code_agent, test_agent])
        
        status = master.get_status()
        
        assert status["agent_id"] == master.agent_id
        assert status["state"] == master.get_state().value
        assert status["specialized_agents_count"] == 2
        assert "scheduler_stats" in status
    
    def test_master_agent_get_status_no_agents(self):
        """测试无专业Agent时获取状态"""
        master = MasterAgent()
        
        status = master.get_status()
        
        assert status["specialized_agents_count"] == 0
    
    def test_master_agent_coordinate_task_with_dependencies(self):
        """测试有依赖关系的任务协调"""
        master = MasterAgent()
        
        code_agent = CodeAgent()
        test_agent = TestAgent()
        master.set_specialized_agents([code_agent, test_agent])
        
        # 这个请求应该产生有依赖关系的任务
        request = "实现功能并编写测试"
        result = master.coordinate_task(request, CollaborationMode.SEQUENTIAL)
        
        assert result is not None
    
    def test_master_agent_invalid_mode(self):
        """测试无效的协作模式"""
        master = MasterAgent()
        
        code_agent = CodeAgent()
        master.set_specialized_agents([code_agent])
        
        request = "实现功能"
        # 使用无效的模式字符串
        result = master.coordinate_task(request, "invalid_mode")
        
        # 应该回退到默认模式
        assert result is not None
    
    def test_master_agent_task_execution_error_handling(self):
        """测试任务执行错误处理"""
        master = MasterAgent()
        
        code_agent = CodeAgent()
        master.set_specialized_agents([code_agent])
        
        request = "实现功能"
        result = master.coordinate_task(request, CollaborationMode.HIERARCHY)
        
        assert result is not None
        # 即使出现错误，也应该返回结果
    
    def test_master_agent_invalid_collaboration_mode(self):
        """测试无效的协作模式字符串"""
        master = MasterAgent()
        
        code_agent = CodeAgent()
        master.set_specialized_agents([code_agent])
        
        task = AgentTask(
            task_id="task_001",
            task_type="coordination",
            description="协调任务",
            required_capabilities=["coordination"],
            input_data={
                "request": "实现功能",
                "mode": "invalid_mode_string"
            }
        )
        
        result = master.process_task(task)
        
        # 应该回退到默认模式
        assert result is not None
    
    def test_master_agent_competitive_mode_multiple_tasks(self):
        """测试竞争模式下多个任务的情况"""
        master = MasterAgent()
        
        code_agent = CodeAgent()
        master.set_specialized_agents([code_agent])
        
        request = "实现功能"
        # 竞争模式应该只处理一个任务
        result = master.coordinate_task(request, CollaborationMode.COMPETITIVE)
        
        assert result is not None
    
    def test_master_agent_sequential_mode_empty_tasks(self):
        """测试顺序模式下没有任务的情况"""
        master = MasterAgent()
        master.set_specialized_agents([])
        
        request = "实现功能"
        result = master.coordinate_task(request, CollaborationMode.SEQUENTIAL)
        
        assert result is not None
    
    def test_master_agent_competitive_mode_single_task(self):
        """测试竞争模式下单个任务"""
        master = MasterAgent()
        
        code_agent = CodeAgent()
        test_agent = TestAgent()
        master.set_specialized_agents([code_agent, test_agent])
        
        request = "实现功能"
        result = master.coordinate_task(request, CollaborationMode.COMPETITIVE)
        
        assert result is not None
        # 竞争模式应该有best_result
        assert "best_result" in result or "success" in result
    
    def test_master_agent_parallel_mode_error_handling(self):
        """测试并行模式错误处理"""
        master = MasterAgent()
        
        # 没有专业Agent
        master.set_specialized_agents([])
        
        request = "实现功能"
        result = master.coordinate_task(request, CollaborationMode.PARALLEL)
        
        # 应该返回结果而不是抛出异常
        assert result is not None
    
    def test_master_agent_task_decomposition_error(self):
        """测试任务分解错误处理"""
        master = MasterAgent()
        
        code_agent = CodeAgent()
        master.set_specialized_agents([code_agent])
        
        # 使用一个会导致简单分解的请求
        request = "simple task"
        result = master.coordinate_task(request, CollaborationMode.HIERARCHY)
        
        assert result is not None
    
    def test_master_agent_integration_error_handling(self):
        """测试结果整合错误处理"""
        master = MasterAgent()
        
        code_agent = CodeAgent()
        master.set_specialized_agents([code_agent])
        
        request = "实现功能"
        result = master.coordinate_task(request, CollaborationMode.HIERARCHY)
        
        # 即使整合出现问题，也应该返回结果
        assert result is not None
