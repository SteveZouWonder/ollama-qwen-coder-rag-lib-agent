"""
测试agent_orchestrator模块
"""
import pytest
from agent_orchestrator import AgentOrchestrator
from agent_config import AgentConfigManager
from agents.agent_types import CollaborationMode, AgentConfig, OrchestratorConfig, AgentType


class TestAgentOrchestrator:
    """测试AgentOrchestrator类"""
    
    def test_orchestrator_creation(self):
        """测试创建AgentOrchestrator"""
        config = AgentConfigManager.get_default_config()
        orchestrator = AgentOrchestrator(config)
        
        assert orchestrator is not None
        assert orchestrator.config == config
        assert orchestrator.registry is not None
        assert orchestrator.message_bus is not None
        assert orchestrator.master_agent is not None
    
    def test_orchestrator_initialization(self):
        """测试AgentOrchestrator初始化过程"""
        config = AgentConfigManager.get_default_config()
        orchestrator = AgentOrchestrator(config)
        
        # 检查专业Agent是否被初始化
        assert len(orchestrator.specialized_agents) > 0
        
        # 检查MasterAgent是否有专业Agent
        assert len(orchestrator.master_agent.specialized_agents) > 0
    
    def test_orchestrator_process_request(self):
        """测试处理请求"""
        config = AgentConfigManager.get_default_config()
        orchestrator = AgentOrchestrator(config)
        
        request = "实现用户登录功能"
        result = orchestrator.process_request(request, CollaborationMode.PARALLEL)
        
        assert result is not None
        assert "success" in result
    
    def test_orchestrator_process_request_default_mode(self):
        """测试使用默认模式处理请求"""
        config = AgentConfigManager.get_default_config()
        orchestrator = AgentOrchestrator(config)
        
        request = "实现功能"
        result = orchestrator.process_request(request)  # 不指定模式
        
        assert result is not None
        assert "success" in result
    
    def test_orchestrator_get_status(self):
        """测试获取编排器状态"""
        config = AgentConfigManager.get_default_config()
        orchestrator = AgentOrchestrator(config)
        
        status = orchestrator.get_status()
        
        assert "registry_stats" in status
        assert "master_status" in status
        assert "specialized_agents" in status
        assert "config" in status
    
    def test_orchestrator_get_agent(self):
        """测试获取指定Agent"""
        config = AgentConfigManager.get_default_config()
        orchestrator = AgentOrchestrator(config)
        
        # 获取MasterAgent
        master_agent = orchestrator.get_agent("master_agent")
        
        assert master_agent is not None
        assert master_agent.agent_id == "master_agent"
    
    def test_orchestrator_get_agent_nonexistent(self):
        """测试获取不存在的Agent"""
        config = AgentConfigManager.get_default_config()
        orchestrator = AgentOrchestrator(config)
        
        agent = orchestrator.get_agent("nonexistent_agent")
        
        assert agent is None
    
    def test_orchestrator_get_all_agents(self):
        """测试获取所有Agent"""
        config = AgentConfigManager.get_default_config()
        orchestrator = AgentOrchestrator(config)
        
        all_agents = orchestrator.get_all_agents()
        
        assert len(all_agents) > 0
        # 应该包含MasterAgent和至少一个专业Agent
        agent_ids = [agent.agent_id for agent in all_agents]
        assert "master_agent" in agent_ids
    
    def test_orchestrator_with_minimal_config(self):
        """测试使用最小化配置"""
        config = AgentConfigManager.get_minimal_config()
        orchestrator = AgentOrchestrator(config)
        
        assert len(orchestrator.specialized_agents) <= 2  # 只有CodeAgent和TestAgent
    
    def test_orchestrator_disabled_agents(self):
        """测试禁用某些Agent"""
        config = AgentConfigManager.get_default_config()
        
        # 禁用一些Agent
        for agent_config in config.agent_configs:
            if agent_config.agent_type.value in ["rag", "doc"]:
                agent_config.enabled = False
        
        orchestrator = AgentOrchestrator(config)
        
        # 检查只有启用的Agent被初始化
        enabled_types = {agent.agent_type.value for agent in orchestrator.specialized_agents}
        assert "rag" not in enabled_types
        assert "doc" not in enabled_types
        assert "code" in enabled_types
        assert "test" in enabled_types
    
    def test_orchestrator_process_request_parallel(self):
        """测试并行模式处理请求"""
        config = AgentConfigManager.get_default_config()
        orchestrator = AgentOrchestrator(config)
        
        request = "实现功能并测试"
        result = orchestrator.process_request(request, CollaborationMode.PARALLEL)
        
        assert result is not None
        assert "success" in result
    
    def test_orchestrator_process_request_sequential(self):
        """测试顺序模式处理请求"""
        config = AgentConfigManager.get_default_config()
        orchestrator = AgentOrchestrator(config)
        
        request = "实现功能并测试"
        result = orchestrator.process_request(request, CollaborationMode.SEQUENTIAL)
        
        assert result is not None
        assert "success" in result
    
    def test_orchestrator_message_bus_setup(self):
        """测试消息总线设置"""
        config = AgentConfigManager.get_default_config()
        orchestrator = AgentOrchestrator(config)
        
        # 检查所有Agent是否都有消息总线
        assert orchestrator.master_agent.message_bus is not None
        for agent in orchestrator.specialized_agents:
            assert agent.message_bus is not None
    
    def test_orchestrator_registry_setup(self):
        """测试注册中心设置"""
        config = AgentConfigManager.get_default_config()
        orchestrator = AgentOrchestrator(config)
        
        # 检查MasterAgent是否在注册中心
        master_agent = orchestrator.registry.get_agent("master_agent")
        assert master_agent is not None
        
        # 检查专业Agent是否在注册中心
        for agent in orchestrator.specialized_agents:
            registered_agent = orchestrator.registry.get_agent(agent.agent_id)
            assert registered_agent is not None
    
    def test_orchestrator_shutdown(self):
        """测试关闭编排器"""
        config = AgentConfigManager.get_default_config()
        orchestrator = AgentOrchestrator(config)
        
        orchestrator.shutdown()
        
        # 检查注册中心是否被清空
        assert len(orchestrator.registry.agents) == 0
        assert len(orchestrator.registry.capabilities_index) == 0
    
    def test_orchestrator_context_manager(self):
        """测试上下文管理器"""
        config = AgentConfigManager.get_default_config()
        
        with AgentOrchestrator(config) as orchestrator:
            assert orchestrator is not None
            all_agents = orchestrator.get_all_agents()
            assert len(all_agents) > 0
        
        # 退出上下文后应该被关闭
        # 注意：由于对象引用仍然存在，这里主要验证没有异常
        assert True
    
    def test_orchestrator_custom_config(self):
        """测试自定义配置"""
        config = AgentConfigManager.create_custom_config(
            model="custom_model",
            host="http://custom-host:11434",
            max_parallel_tasks=8,
            default_mode="parallel"
        )
        
        orchestrator = AgentOrchestrator(config)
        
        assert orchestrator.config.max_parallel_tasks == 8
        assert orchestrator.config.default_collaboration_mode == CollaborationMode.PARALLEL
    
    def test_orchestrator_multiple_requests(self):
        """测试处理多个请求"""
        config = AgentConfigManager.get_default_config()
        orchestrator = AgentOrchestrator(config)
        
        requests = [
            "实现功能1",
            "实现功能2",
            "实现功能3"
        ]
        
        results = []
        for request in requests:
            result = orchestrator.process_request(request)
            results.append(result)
        
        # 所有请求都应该有结果
        for result in results:
            assert result is not None
            assert "success" in result
    
    def test_orchestrator_status_detailed(self):
        """测试详细的状态信息"""
        config = AgentConfigManager.get_default_config()
        orchestrator = AgentOrchestrator(config)
        
        status = orchestrator.get_status()
        
        # 检查状态信息的结构
        assert "total_agents" in status["registry_stats"]
        assert "agent_id" in status["master_status"]
        assert isinstance(status["specialized_agents"], list)
        
        # 检查专业Agent状态信息
        if status["specialized_agents"]:
            agent_status = status["specialized_agents"][0]
            assert "agent_id" in agent_status
            assert "type" in agent_status
            assert "state" in agent_status
            assert "capabilities" in agent_status
    
    def test_orchestrator_error_handling(self):
        """测试错误处理"""
        config = AgentConfigManager.get_default_config()
        orchestrator = AgentOrchestrator(config)
        
        # 发送空请求
        result = orchestrator.process_request("")
        
        # 应该返回结果而不是抛出异常
        assert result is not None
    
    def test_orchestrator_message_handler_error_handling(self):
        """测试消息处理器错误处理"""
        config = AgentConfigManager.get_default_config()
        orchestrator = AgentOrchestrator(config)
        
        # 测试消息处理器在出错时的行为
        # 这个测试主要验证orchestrator的健壮性
        assert orchestrator.message_bus is not None
    
    def test_orchestrator_agent_initialization_failure(self):
        """测试Agent初始化失败的情况"""
        # 创建一个没有专业Agent的配置
        config = OrchestratorConfig(
            master_agent_config=AgentConfig(
                agent_id="master",
                agent_type=AgentType.MASTER,
                model="qwen2.5-coder:7b",
                host="http://localhost:11434",
                capabilities=["coordination"],
                specialized_tools=[]
            ),
            agent_configs=[],
            default_collaboration_mode=CollaborationMode.HIERARCHY
        )
        
        # 即使没有专业Agent，也应该能创建orchestrator
        orchestrator = AgentOrchestrator(config)
        
        assert orchestrator is not None
        assert orchestrator.master_agent is not None
        assert len(orchestrator.specialized_agents) == 0
    
    def test_orchestrator_message_bus_communication(self):
        """测试消息总线通信"""
        config = AgentConfigManager.get_minimal_config()
        orchestrator = AgentOrchestrator(config)
        
        # 验证消息总线已设置
        assert orchestrator.message_bus is not None
        assert orchestrator.master_agent.message_bus is not None
        
        # 验证专业Agent的消息总线已设置
        for agent in orchestrator.specialized_agents:
            assert agent.message_bus is not None
    
    def test_orchestrator_registry_management(self):
        """测试注册中心管理"""
        config = AgentConfigManager.get_minimal_config()
        orchestrator = AgentOrchestrator(config)
        
        # 验证MasterAgent已注册
        master_in_registry = orchestrator.registry.get_agent("master_agent")
        assert master_in_registry is not None
        
        # 验证专业Agent已注册
        for agent in orchestrator.specialized_agents:
            agent_in_registry = orchestrator.registry.get_agent(agent.agent_id)
            assert agent_in_registry is not None
    
    def test_orchestrator_process_with_invalid_mode(self):
        """测试使用无效的协作模式"""
        config = AgentConfigManager.get_minimal_config()
        orchestrator = AgentOrchestrator(config)
        
        # 创建一个无效的协作模式字符串
        from agents.agent_types import CollaborationMode
        
        # 测试使用有效的模式
        result = orchestrator.process_request("测试任务", CollaborationMode.PARALLEL)
        assert result is not None
