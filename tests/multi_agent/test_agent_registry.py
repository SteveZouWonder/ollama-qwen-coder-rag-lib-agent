"""
测试agent_registry模块
"""
import pytest
from agent_registry import AgentRegistry
from agents.base_agent import BaseAgent
from agents.agent_types import AgentTask, AgentResult, AgentType, AgentState, TaskStatus


class MockAgentForRegistry(BaseAgent):
    """用于注册中心测试的Mock Agent"""
    
    def process_task(self, task: AgentTask) -> AgentResult:
        return AgentResult(
            task_id=task.task_id,
            agent_id=self.agent_id,
            success=True,
            output="Processed",
            metadata={},
            execution_time=0.1
        )


class TestAgentRegistry:
    """测试AgentRegistry类"""
    
    def test_registry_creation(self):
        """测试创建注册中心"""
        registry = AgentRegistry()
        
        assert len(registry.agents) == 0
        assert len(registry.capabilities_index) == 0
        assert len(registry.type_index) == 0
    
    def test_register_agent(self):
        """测试注册Agent"""
        registry = AgentRegistry()
        
        agent = MockAgentForRegistry(
            agent_id="agent_001",
            agent_type=AgentType.CODE,
            capabilities=["code_generation", "file_operations"]
        )
        
        result = registry.register(agent)
        
        assert result is True
        assert "agent_001" in registry.agents
        assert "code_generation" in registry.capabilities_index
        assert "file_operations" in registry.capabilities_index
        assert AgentType.CODE in registry.type_index
    
    def test_register_duplicate_agent(self):
        """测试注册重复Agent"""
        registry = AgentRegistry()
        
        agent1 = MockAgentForRegistry(
            agent_id="agent_001",
            agent_type=AgentType.CODE,
            capabilities=["code_generation"]
        )
        
        agent2 = MockAgentForRegistry(
            agent_id="agent_001",  # 相同ID
            agent_type=AgentType.CODE,
            capabilities=["code_generation"]
        )
        
        registry.register(agent1)
        result = registry.register(agent2)
        
        assert result is False
        assert len(registry.agents) == 1
    
    def test_unregister_agent(self):
        """测试注销Agent"""
        registry = AgentRegistry()
        
        agent = MockAgentForRegistry(
            agent_id="agent_001",
            agent_type=AgentType.CODE,
            capabilities=["code_generation", "file_operations"]
        )
        
        registry.register(agent)
        result = registry.unregister("agent_001")
        
        assert result is True
        assert "agent_001" not in registry.agents
        assert "code_generation" not in registry.capabilities_index
        assert AgentType.CODE not in registry.type_index
    
    def test_unregister_nonexistent_agent(self):
        """测试注销不存在的Agent"""
        registry = AgentRegistry()
        
        result = registry.unregister("nonexistent")
        
        assert result is False
    
    def test_get_agent(self):
        """测试获取Agent"""
        registry = AgentRegistry()
        
        agent = MockAgentForRegistry(
            agent_id="agent_001",
            agent_type=AgentType.CODE,
            capabilities=["code_generation"]
        )
        
        registry.register(agent)
        
        retrieved_agent = registry.get_agent("agent_001")
        
        assert retrieved_agent is not None
        assert retrieved_agent.agent_id == "agent_001"
    
    def test_get_agent_nonexistent(self):
        """测试获取不存在的Agent"""
        registry = AgentRegistry()
        
        retrieved_agent = registry.get_agent("nonexistent")
        
        assert retrieved_agent is None
    
    def test_find_agents_by_capability(self):
        """测试根据能力查找Agent"""
        registry = AgentRegistry()
        
        agent1 = MockAgentForRegistry(
            agent_id="agent_001",
            agent_type=AgentType.CODE,
            capabilities=["code_generation", "file_operations"]
        )
        
        agent2 = MockAgentForRegistry(
            agent_id="agent_002",
            agent_type=AgentType.RAG,
            capabilities=["knowledge_retrieval", "file_operations"]
        )
        
        agent3 = MockAgentForRegistry(
            agent_id="agent_003",
            agent_type=AgentType.CODE,
            capabilities=["code_generation"]
        )
        
        registry.register(agent1)
        registry.register(agent2)
        registry.register(agent3)
        
        # 查找具有code_generation能力的Agent
        agents = registry.find_agents_by_capability("code_generation")
        
        assert len(agents) == 2
        agent_ids = [a.agent_id for a in agents]
        assert "agent_001" in agent_ids
        assert "agent_003" in agent_ids
        
        # 查找具有file_operations能力的Agent
        agents = registry.find_agents_by_capability("file_operations")
        
        assert len(agents) == 2
        agent_ids = [a.agent_id for a in agents]
        assert "agent_001" in agent_ids
        assert "agent_002" in agent_ids
    
    def test_find_agents_by_capability_nonexistent(self):
        """测试查找不存在的能力"""
        registry = AgentRegistry()
        
        agent = MockAgentForRegistry(
            agent_id="agent_001",
            agent_type=AgentType.CODE,
            capabilities=["code_generation"]
        )
        
        registry.register(agent)
        
        agents = registry.find_agents_by_capability("nonexistent_capability")
        
        assert len(agents) == 0
    
    def test_find_agents_by_type(self):
        """测试根据类型查找Agent"""
        registry = AgentRegistry()
        
        agent1 = MockAgentForRegistry(
            agent_id="agent_001",
            agent_type=AgentType.CODE,
            capabilities=["code_generation"]
        )
        
        agent2 = MockAgentForRegistry(
            agent_id="agent_002",
            agent_type=AgentType.RAG,
            capabilities=["knowledge_retrieval"]
        )
        
        agent3 = MockAgentForRegistry(
            agent_id="agent_003",
            agent_type=AgentType.CODE,
            capabilities=["code_generation"]
        )
        
        registry.register(agent1)
        registry.register(agent2)
        registry.register(agent3)
        
        # 查找CODE类型的Agent
        agents = registry.find_agents_by_type(AgentType.CODE)
        
        assert len(agents) == 2
        agent_ids = [a.agent_id for a in agents]
        assert "agent_001" in agent_ids
        assert "agent_003" in agent_ids
        
        # 查找RAG类型的Agent
        agents = registry.find_agents_by_type(AgentType.RAG)
        
        assert len(agents) == 1
        assert agents[0].agent_id == "agent_002"
    
    def test_find_agents_by_state(self):
        """测试根据状态查找Agent"""
        registry = AgentRegistry()
        
        agent1 = MockAgentForRegistry(
            agent_id="agent_001",
            agent_type=AgentType.CODE,
            capabilities=["code_generation"]
        )
        
        agent2 = MockAgentForRegistry(
            agent_id="agent_002",
            agent_type=AgentType.RAG,
            capabilities=["knowledge_retrieval"]
        )
        
        registry.register(agent1)
        registry.register(agent2)
        
        agent1.set_state(AgentState.BUSY)
        agent2.set_state(AgentState.IDLE)
        
        # 查找IDLE状态的Agent
        agents = registry.find_agents_by_state(AgentState.IDLE)
        
        assert len(agents) == 1
        assert agents[0].agent_id == "agent_002"
        
        # 查找BUSY状态的Agent
        agents = registry.find_agents_by_state(AgentState.BUSY)
        
        assert len(agents) == 1
        assert agents[0].agent_id == "agent_001"
    
    def test_find_available_agents(self):
        """测试查找可用的Agent"""
        registry = AgentRegistry()
        
        agent1 = MockAgentForRegistry(
            agent_id="agent_001",
            agent_type=AgentType.CODE,
            capabilities=["code_generation", "file_operations"]
        )
        
        agent2 = MockAgentForRegistry(
            agent_id="agent_002",
            agent_type=AgentType.CODE,
            capabilities=["code_generation"]
        )
        
        agent3 = MockAgentForRegistry(
            agent_id="agent_003",
            agent_type=AgentType.RAG,
            capabilities=["knowledge_retrieval"]
        )
        
        registry.register(agent1)
        registry.register(agent2)
        registry.register(agent3)
        
        agent1.set_state(AgentState.BUSY)
        agent2.set_state(AgentState.IDLE)
        agent3.set_state(AgentState.IDLE)
        
        # 查找可以处理code_generation任务的空闲Agent
        agents = registry.find_available_agents(["code_generation"])
        
        assert len(agents) == 1
        assert agents[0].agent_id == "agent_002"
    
    def test_find_available_agents_multiple_capabilities(self):
        """测试查找需要多个能力的可用Agent"""
        registry = AgentRegistry()
        
        agent1 = MockAgentForRegistry(
            agent_id="agent_001",
            agent_type=AgentType.CODE,
            capabilities=["code_generation", "file_operations", "testing"]
        )
        
        agent2 = MockAgentForRegistry(
            agent_id="agent_002",
            agent_type=AgentType.CODE,
            capabilities=["code_generation"]
        )
        
        registry.register(agent1)
        registry.register(agent2)
        
        # 查找需要多个能力的Agent
        agents = registry.find_available_agents(["code_generation", "file_operations"])
        
        assert len(agents) == 1
        assert agents[0].agent_id == "agent_001"
    
    def test_get_all_agents(self):
        """测试获取所有Agent"""
        registry = AgentRegistry()
        
        agent1 = MockAgentForRegistry(
            agent_id="agent_001",
            agent_type=AgentType.CODE,
            capabilities=["code_generation"]
        )
        
        agent2 = MockAgentForRegistry(
            agent_id="agent_002",
            agent_type=AgentType.RAG,
            capabilities=["knowledge_retrieval"]
        )
        
        registry.register(agent1)
        registry.register(agent2)
        
        agents = registry.get_all_agents()
        
        assert len(agents) == 2
        agent_ids = [a.agent_id for a in agents]
        assert "agent_001" in agent_ids
        assert "agent_002" in agent_ids
    
    def test_get_agent_count(self):
        """测试获取Agent数量"""
        registry = AgentRegistry()
        
        assert registry.get_agent_count() == 0
        
        agent = MockAgentForRegistry(
            agent_id="agent_001",
            agent_type=AgentType.CODE,
            capabilities=["code_generation"]
        )
        
        registry.register(agent)
        
        assert registry.get_agent_count() == 1
    
    def test_get_all_capabilities(self):
        """测试获取所有能力"""
        registry = AgentRegistry()
        
        agent1 = MockAgentForRegistry(
            agent_id="agent_001",
            agent_type=AgentType.CODE,
            capabilities=["code_generation", "file_operations"]
        )
        
        agent2 = MockAgentForRegistry(
            agent_id="agent_002",
            agent_type=AgentType.RAG,
            capabilities=["knowledge_retrieval", "file_operations"]
        )
        
        registry.register(agent1)
        registry.register(agent2)
        
        capabilities = registry.get_all_capabilities()
        
        assert len(capabilities) == 3  # code_generation, file_operations, knowledge_retrieval
        assert "code_generation" in capabilities
        assert "file_operations" in capabilities
        assert "knowledge_retrieval" in capabilities
    
    def test_get_statistics(self):
        """测试获取统计信息"""
        registry = AgentRegistry()
        
        agent1 = MockAgentForRegistry(
            agent_id="agent_001",
            agent_type=AgentType.CODE,
            capabilities=["code_generation"]
        )
        
        agent2 = MockAgentForRegistry(
            agent_id="agent_002",
            agent_type=AgentType.RAG,
            capabilities=["knowledge_retrieval"]
        )
        
        agent3 = MockAgentForRegistry(
            agent_id="agent_003",
            agent_type=AgentType.CODE,
            capabilities=["code_generation"]
        )
        
        registry.register(agent1)
        registry.register(agent2)
        registry.register(agent3)
        
        agent1.set_state(AgentState.IDLE)
        agent2.set_state(AgentState.BUSY)
        agent3.set_state(AgentState.IDLE)
        
        stats = registry.get_statistics()
        
        assert stats["total_agents"] == 3
        assert stats["total_capabilities"] == 2
        assert stats["agents_by_type"]["code"] == 2
        assert stats["agents_by_type"]["rag"] == 1
        assert stats["agents_by_state"]["idle"] == 2
        assert stats["agents_by_state"]["busy"] == 1
    
    def test_clear(self):
        """测试清空注册中心"""
        registry = AgentRegistry()
        
        agent = MockAgentForRegistry(
            agent_id="agent_001",
            agent_type=AgentType.CODE,
            capabilities=["code_generation"]
        )
        
        registry.register(agent)
        
        registry.clear()
        
        assert len(registry.agents) == 0
        assert len(registry.capabilities_index) == 0
        assert len(registry.type_index) == 0
    
    def test_contains(self):
        """测试__contains__方法"""
        registry = AgentRegistry()
        
        agent = MockAgentForRegistry(
            agent_id="agent_001",
            agent_type=AgentType.CODE,
            capabilities=["code_generation"]
        )
        
        assert "agent_001" not in registry
        
        registry.register(agent)
        
        assert "agent_001" in registry
        assert "agent_002" not in registry
    
    def test_len(self):
        """测试__len__方法"""
        registry = AgentRegistry()
        
        assert len(registry) == 0
        
        agent = MockAgentForRegistry(
            agent_id="agent_001",
            agent_type=AgentType.CODE,
            capabilities=["code_generation"]
        )
        
        registry.register(agent)
        
        assert len(registry) == 1
    
    def test_iter(self):
        """测试__iter__方法"""
        registry = AgentRegistry()
        
        agent1 = MockAgentForRegistry(
            agent_id="agent_001",
            agent_type=AgentType.CODE,
            capabilities=["code_generation"]
        )
        
        agent2 = MockAgentForRegistry(
            agent_id="agent_002",
            agent_type=AgentType.RAG,
            capabilities=["knowledge_retrieval"]
        )
        
        registry.register(agent1)
        registry.register(agent2)
        
        agent_ids = [agent.agent_id for agent in registry]
        
        assert len(agent_ids) == 2
        assert "agent_001" in agent_ids
        assert "agent_002" in agent_ids
    
    def test_find_agents_by_capability_empty_index(self):
        """测试查找能力时能力索引为空"""
        registry = AgentRegistry()
        
        agents = registry.find_agents_by_capability("nonexistent")
        
        assert len(agents) == 0
    
    def test_unregister_agent_cleanup_index(self):
        """测试注销Agent时清理索引"""
        registry = AgentRegistry()
        
        agent = MockAgentForRegistry(
            agent_id="agent_001",
            agent_type=AgentType.CODE,
            capabilities=["code_generation", "file_operations"]
        )
        
        registry.register(agent)
        assert "code_generation" in registry.capabilities_index
        
        registry.unregister("agent_001")
        assert "code_generation" not in registry.capabilities_index
