"""
Agent编排器 - 协调多个Agent的交互和执行
"""
from typing import List, Dict, Any, Optional
import logging
from agents.base_agent import BaseAgent
from agents.agent_types import CollaborationMode, OrchestratorConfig, AgentConfig
from master_agent import MasterAgent
from agent_registry import AgentRegistry
from collaboration.message_bus import MessageBus
from agents.code_agent import CodeAgent
from agents.rag_agent import RAGAgent
from agents import TestAgent
from agents.doc_agent import DocAgent
from agents.audit_agent import AuditAgent


class AgentOrchestrator:
    """Agent编排器，负责协调Agent交互和任务执行"""
    
    def __init__(self, config: OrchestratorConfig):
        """
        初始化Agent编排器
        
        Args:
            config: 编排器配置
        """
        self.config = config
        self.logger = logging.getLogger("AgentOrchestrator")
        
        # 初始化组件
        self.registry = AgentRegistry()
        self.message_bus = MessageBus(
            enable_persistence=config.enable_logging,
            persistence_file=config.log_file
        )
        
        # 创建MasterAgent
        self.master_agent = MasterAgent(
            agent_id=config.master_agent_config.agent_id,
            config=config.master_agent_config.config_data
        )
        
        # 创建专业Agent
        self.specialized_agents: List[BaseAgent] = []
        self._initialize_agents()
        
        # 设置Agent间的关系
        self._setup_agent_relationships()
        
        self.logger.info("AgentOrchestrator initialized")
    
    def _initialize_agents(self):
        """初始化所有专业Agent"""
        for agent_config in self.config.agent_configs:
            if not agent_config.enabled:
                continue
            
            agent = self._create_agent(agent_config)
            if agent:
                self.specialized_agents.append(agent)
                self.registry.register(agent)
                self.logger.info(f"Initialized agent: {agent.agent_id}")
        
        # 将专业Agent设置给MasterAgent
        self.master_agent.set_specialized_agents(self.specialized_agents)
    
    def _create_agent(self, config: AgentConfig) -> Optional[BaseAgent]:
        """
        根据配置创建Agent
        
        Args:
            config: Agent配置
            
        Returns:
            Optional[BaseAgent]: 创建的Agent实例
        """
        try:
            if config.agent_type.value == "code":
                return CodeAgent(agent_id=config.agent_id, config=config.config_data)
            elif config.agent_type.value == "rag":
                return RAGAgent(agent_id=config.agent_id, config=config.config_data)
            elif config.agent_type.value == "test":
                return TestAgent(agent_id=config.agent_id, config=config.config_data)
            elif config.agent_type.value == "doc":
                return DocAgent(agent_id=config.agent_id, config=config.config_data)
            elif config.agent_type.value == "audit":
                return AuditAgent(agent_id=config.agent_id, config=config.config_data)
            else:
                self.logger.warning(f"Unknown agent type: {config.agent_type}")
                return None
        except Exception as e:
            self.logger.error(f"Failed to create agent {config.agent_id}: {e}")
            return None
    
    def _setup_agent_relationships(self):
        """设置Agent间的关系和通信"""
        # 为所有Agent设置消息总线
        self.master_agent.set_message_bus(self.message_bus)
        for agent in self.specialized_agents:
            agent.set_message_bus(self.message_bus)
        
        # 注册MasterAgent
        self.registry.register(self.master_agent)
        
        # 设置消息处理器
        self._setup_message_handlers()
    
    def _setup_message_handlers(self):
        """设置消息处理器"""
        # MasterAgent的消息处理器
        def master_message_handler(message):
            self.logger.debug(f"MasterAgent received message: {message.message_type}")
        
        self.master_agent.register_message_handler("task_update", master_message_handler)
        self.message_bus.subscribe(self.master_agent.agent_id, master_message_handler)
        
        # 专业Agent的消息处理器
        for agent in self.specialized_agents:
            def agent_message_handler(message, agent=agent):
                self.logger.debug(f"Agent {agent.agent_id} received message: {message.message_type}")
            
            agent.register_message_handler("coordination", agent_message_handler)
            self.message_bus.subscribe(agent.agent_id, agent_message_handler)
    
    def process_request(self, request: str, mode: CollaborationMode = None) -> Dict[str, Any]:
        """
        处理用户请求
        
        Args:
            request: 用户请求
            mode: 协作模式，如果为None则使用默认模式
            
        Returns:
            Dict[str, Any]: 处理结果
        """
        if mode is None:
            mode = self.config.default_collaboration_mode
        
        self.logger.info(f"Processing request with mode: {mode}")
        
        try:
            result = self.master_agent.coordinate_task(request, mode)
            return result
        except Exception as e:
            self.logger.error(f"Request processing failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "summary": "Request processing failed"
            }
    
    def get_status(self) -> Dict[str, Any]:
        """获取系统状态"""
        registry_stats = self.registry.get_statistics()
        master_status = self.master_agent.get_status()
        
        agent_states = []
        for agent in self.specialized_agents:
            agent_states.append({
                "agent_id": agent.agent_id,
                "type": agent.agent_type.value,
                "state": agent.get_state().value,
                "capabilities": agent.get_capabilities()
            })
        
        return {
            "registry_stats": registry_stats,
            "master_status": master_status,
            "specialized_agents": agent_states,
            "config": self.config.to_dict()
        }
    
    def get_agent(self, agent_id: str) -> Optional[BaseAgent]:
        """获取指定的Agent"""
        return self.registry.get_agent(agent_id)
    
    def get_all_agents(self) -> List[BaseAgent]:
        """获取所有Agent"""
        return self.registry.get_all_agents()
    
    def shutdown(self):
        """关闭编排器"""
        self.logger.info("Shutting down AgentOrchestrator")
        
        # 关闭所有Agent
        self.registry.shutdown_all()
        
        # 关闭消息总线
        self.message_bus.shutdown()
        
        # 清空注册表
        self.registry.clear()
        
        self.logger.info("AgentOrchestrator shutdown complete")
    
    def __enter__(self):
        """上下文管理器入口"""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器出口"""
        self.shutdown()
