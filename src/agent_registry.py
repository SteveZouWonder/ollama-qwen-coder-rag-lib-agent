"""
Agent注册中心 - 管理所有Agent实例的注册表
"""
from typing import Dict, List, Optional
import logging
from agents.base_agent import BaseAgent
from agents.agent_types import AgentType, AgentState


class AgentRegistry:
    """Agent注册中心，管理所有Agent实例"""
    
    def __init__(self):
        """初始化注册中心"""
        self.agents: Dict[str, BaseAgent] = {}
        self.capabilities_index: Dict[str, List[str]] = {}
        self.type_index: Dict[AgentType, List[str]] = {}
        self.lock = None  # 简化实现，实际可以使用threading.Lock
        self.logger = logging.getLogger("AgentRegistry")
    
    def register(self, agent: BaseAgent) -> bool:
        """
        注册Agent
        
        Args:
            agent: Agent实例
            
        Returns:
            bool: 注册是否成功
        """
        if agent.agent_id in self.agents:
            self.logger.warning(f"Agent {agent.agent_id} already registered")
            return False
        
        self.agents[agent.agent_id] = agent
        
        # 更新能力索引
        for capability in agent.capabilities:
            if capability not in self.capabilities_index:
                self.capabilities_index[capability] = []
            self.capabilities_index[capability].append(agent.agent_id)
        
        # 更新类型索引
        agent_type = agent.agent_type
        if agent_type not in self.type_index:
            self.type_index[agent_type] = []
        self.type_index[agent_type].append(agent.agent_id)
        
        self.logger.info(f"Agent {agent.agent_id} registered (type: {agent_type})")
        return True
    
    def unregister(self, agent_id: str) -> bool:
        """
        注销Agent
        
        Args:
            agent_id: Agent ID
            
        Returns:
            bool: 注销是否成功
        """
        if agent_id not in self.agents:
            self.logger.warning(f"Agent {agent_id} not found")
            return False
        
        agent = self.agents[agent_id]
        
        # 更新能力索引
        for capability in agent.capabilities:
            if capability in self.capabilities_index:
                if agent_id in self.capabilities_index[capability]:
                    self.capabilities_index[capability].remove(agent_id)
                if not self.capabilities_index[capability]:
                    del self.capabilities_index[capability]
        
        # 更新类型索引
        agent_type = agent.agent_type
        if agent_type in self.type_index:
            if agent_id in self.type_index[agent_type]:
                self.type_index[agent_type].remove(agent_id)
            if not self.type_index[agent_type]:
                del self.type_index[agent_type]
        
        del self.agents[agent_id]
        self.logger.info(f"Agent {agent_id} unregistered")
        return True
    
    def get_agent(self, agent_id: str) -> Optional[BaseAgent]:
        """
        获取Agent实例
        
        Args:
            agent_id: Agent ID
            
        Returns:
            Optional[BaseAgent]: Agent实例，如果不存在返回None
        """
        return self.agents.get(agent_id)
    
    def find_agents_by_capability(self, capability: str) -> List[BaseAgent]:
        """
        根据能力查找Agent
        
        Args:
            capability: 能力名称
            
        Returns:
            List[BaseAgent]: 匹配的Agent列表
        """
        agent_ids = self.capabilities_index.get(capability, [])
        return [self.agents[aid] for aid in agent_ids if aid in self.agents]
    
    def find_agents_by_type(self, agent_type: AgentType) -> List[BaseAgent]:
        """
        根据类型查找Agent
        
        Args:
            agent_type: Agent类型
            
        Returns:
            List[BaseAgent]: 匹配的Agent列表
        """
        agent_ids = self.type_index.get(agent_type, [])
        return [self.agents[aid] for aid in agent_ids if aid in self.agents]
    
    def find_agents_by_state(self, state: AgentState) -> List[BaseAgent]:
        """
        根据状态查找Agent
        
        Args:
            state: Agent状态
            
        Returns:
            List[BaseAgent]: 匹配的Agent列表
        """
        return [agent for agent in self.agents.values() if agent.get_state() == state]
    
    def find_available_agents(self, required_capabilities: List[str]) -> List[BaseAgent]:
        """
        查找可以处理特定能力的空闲Agent
        
        Args:
            required_capabilities: 所需能力列表
            
        Returns:
            List[BaseAgent]: 可用的Agent列表
        """
        available_agents = []
        
        for agent in self.agents.values():
            if agent.get_state() == AgentState.IDLE:
                agent_caps = set(agent.capabilities)
                required_caps = set(required_capabilities)
                if required_caps.issubset(agent_caps):
                    available_agents.append(agent)
        
        return available_agents
    
    def get_all_agents(self) -> List[BaseAgent]:
        """
        获取所有Agent
        
        Returns:
            List[BaseAgent]: 所有Agent列表
        """
        return list(self.agents.values())
    
    def get_agent_count(self) -> int:
        """
        获取Agent数量
        
        Returns:
            int: Agent数量
        """
        return len(self.agents)
    
    def get_all_capabilities(self) -> List[str]:
        """
        获取所有能力列表
        
        Returns:
            List[str]: 能力列表
        """
        return list(self.capabilities_index.keys())
    
    def get_statistics(self) -> Dict:
        """
        获取注册中心统计信息
        
        Returns:
            Dict: 统计信息字典
        """
        stats = {
            "total_agents": len(self.agents),
            "total_capabilities": len(self.capabilities_index),
            "agents_by_type": {},
            "agents_by_state": {},
            "capabilities_index": {}
        }
        
        # 按类型统计
        for agent_type, agent_ids in self.type_index.items():
            stats["agents_by_type"][agent_type.value] = len(agent_ids)
        
        # 按状态统计
        state_counts = {}
        for agent in self.agents.values():
            state = agent.get_state().value
            state_counts[state] = state_counts.get(state, 0) + 1
        stats["agents_by_state"] = state_counts
        
        # 能力索引
        for capability, agent_ids in self.capabilities_index.items():
            stats["capabilities_index"][capability] = len(agent_ids)
        
        return stats
    
    def shutdown_all(self):
        """关闭所有Agent"""
        for agent in self.agents.values():
            if hasattr(agent, 'shutdown'):
                try:
                    agent.shutdown()
                except Exception as e:
                    self.logger.error(f"Error shutting down agent {agent.agent_id}: {e}")
        
        self.logger.info("All agents shut down")
    
    def clear(self):
        """清空注册中心"""
        self.agents.clear()
        self.capabilities_index.clear()
        self.type_index.clear()
        self.logger.info("Registry cleared")
    
    def __contains__(self, agent_id: str) -> bool:
        """检查Agent是否已注册"""
        return agent_id in self.agents
    
    def __len__(self) -> int:
        """获取Agent数量"""
        return len(self.agents)
    
    def __iter__(self):
        """迭代所有Agent"""
        return iter(self.agents.values())
