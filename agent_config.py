"""
Agent配置管理 - 提供默认配置和配置加载功能
"""
import json
import os
from typing import Dict, Any, Optional
from pathlib import Path
from agents.agent_types import AgentConfig, OrchestratorConfig, AgentType, CollaborationMode


class AgentConfigManager:
    """Agent配置管理器"""
    
    DEFAULT_CONFIG_PATH = Path(__file__).parent / "config" / "agent_config.json"
    
    @staticmethod
    def get_default_config() -> OrchestratorConfig:
        """
        获取默认配置
        
        Returns:
            OrchestratorConfig: 默认编排器配置
        """
        # MasterAgent配置
        master_config = AgentConfig(
            agent_id="master_agent",
            agent_type=AgentType.MASTER,
            model="qwen2.5-coder:7b",
            host="http://localhost:11434",
            capabilities=["task_decomposition", "task_scheduling", "result_integration", "coordination"],
            specialized_tools=[],
            max_iterations=50,
            timeout=300,
            enabled=True,
            config_data={"max_parallel_tasks": 5}
        )
        
        # 专业Agent配置
        agent_configs = [
            AgentConfig(
                agent_id="code_agent_1",
                agent_type=AgentType.CODE,
                model="qwen2.5-coder:7b",
                host="http://localhost:11434",
                capabilities=["code_generation", "code_refactoring", "bug_fixing", "code_review", "file_operations"],
                specialized_tools=["code_analyzer", "refactoring_tool", "performance_profiler"],
                max_iterations=50,
                timeout=300,
                enabled=True,
                config_data={}
            ),
            AgentConfig(
                agent_id="rag_agent_1",
                agent_type=AgentType.RAG,
                model="qwen2.5-coder:7b",
                host="http://localhost:11434",
                capabilities=["knowledge_retrieval", "document_search", "knowledge_extraction", "literature_review"],
                specialized_tools=["advanced_search", "knowledge_graph", "document_comparison"],
                max_iterations=50,
                timeout=300,
                enabled=True,
                config_data={}
            ),
            AgentConfig(
                agent_id="test_agent_1",
                agent_type=AgentType.TEST,
                model="qwen2.5-coder:7b",
                host="http://localhost:11434",
                capabilities=["testing", "test_generation", "coverage_analysis", "quality_assessment"],
                specialized_tools=["test_generator", "coverage_analyzer", "mock_tool"],
                max_iterations=50,
                timeout=300,
                enabled=True,
                config_data={}
            ),
            AgentConfig(
                agent_id="doc_agent_1",
                agent_type=AgentType.DOC,
                model="qwen2.5-coder:7b",
                host="http://localhost:11434",
                capabilities=["documentation", "api_documentation", "technical_writing", "user_guide"],
                specialized_tools=["doc_generator", "format_converter", "doc_validator"],
                max_iterations=50,
                timeout=300,
                enabled=True,
                config_data={}
            ),
            AgentConfig(
                agent_id="audit_agent_1",
                agent_type=AgentType.AUDIT,
                model="qwen2.5-coder:7b",
                host="http://localhost:11434",
                capabilities=["audit", "security_check", "compliance_verification", "performance_audit"],
                specialized_tools=["security_scanner", "code_quality_tool", "dependency_checker"],
                max_iterations=50,
                timeout=300,
                enabled=True,
                config_data={}
            )
        ]
        
        # 编排器配置
        orchestrator_config = OrchestratorConfig(
            master_agent_config=master_config,
            agent_configs=agent_configs,
            default_collaboration_mode=CollaborationMode.HIERARCHY,
            max_parallel_tasks=5,
            task_timeout=600,
            enable_logging=True,
            log_level="INFO",
            log_file=None
        )
        
        return orchestrator_config
    
    @staticmethod
    def load_config_from_file(config_path: str) -> Optional[OrchestratorConfig]:
        """
        从文件加载配置
        
        Args:
            config_path: 配置文件路径
            
        Returns:
            Optional[OrchestratorConfig]: 加载的配置，如果失败返回None
        """
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config_data = json.load(f)
            
            return AgentConfigManager.parse_config(config_data)
        except Exception as e:
            print(f"Failed to load config from {config_path}: {e}")
            return None
    
    @staticmethod
    def parse_config(config_data: Dict[str, Any]) -> OrchestratorConfig:
        """
        解析配置数据
        
        Args:
            config_data: 配置数据字典
            
        Returns:
            OrchestratorConfig: 解析后的配置
        """
        # 解析MasterAgent配置
        master_config_data = config_data.get("master_agent_config", {})
        master_config = AgentConfig(
            agent_id=master_config_data.get("agent_id", "master_agent"),
            agent_type=AgentType(master_config_data.get("agent_type", "master")),
            model=master_config_data.get("model", "qwen2.5-coder:7b"),
            host=master_config_data.get("host", "http://localhost:11434"),
            capabilities=master_config_data.get("capabilities", []),
            specialized_tools=master_config_data.get("specialized_tools", []),
            max_iterations=master_config_data.get("max_iterations", 50),
            timeout=master_config_data.get("timeout", 300),
            enabled=master_config_data.get("enabled", True),
            config_data=master_config_data.get("config_data", {})
        )
        
        # 解析专业Agent配置
        agent_configs = []
        for agent_config_data in config_data.get("agent_configs", []):
            agent_config = AgentConfig(
                agent_id=agent_config_data.get("agent_id"),
                agent_type=AgentType(agent_config_data.get("agent_type")),
                model=agent_config_data.get("model", "qwen2.5-coder:7b"),
                host=agent_config_data.get("host", "http://localhost:11434"),
                capabilities=agent_config_data.get("capabilities", []),
                specialized_tools=agent_config_data.get("specialized_tools", []),
                max_iterations=agent_config_data.get("max_iterations", 50),
                timeout=agent_config_data.get("timeout", 300),
                enabled=agent_config_data.get("enabled", True),
                config_data=agent_config_data.get("config_data", {})
            )
            agent_configs.append(agent_config)
        
        # 解析编排器配置
        orchestrator_config = OrchestratorConfig(
            master_agent_config=master_config,
            agent_configs=agent_configs,
            default_collaboration_mode=CollaborationMode(
                config_data.get("default_collaboration_mode", "hierarchy")
            ),
            max_parallel_tasks=config_data.get("max_parallel_tasks", 5),
            task_timeout=config_data.get("task_timeout", 600),
            enable_logging=config_data.get("enable_logging", True),
            log_level=config_data.get("log_level", "INFO"),
            log_file=config_data.get("log_file")
        )
        
        return orchestrator_config
    
    @staticmethod
    def save_config_to_file(config: OrchestratorConfig, config_path: str):
        """
        保存配置到文件
        
        Args:
            config: 编排器配置
            config_path: 配置文件路径
        """
        try:
            config_data = config.to_dict()
            
            # 确保目录存在
            config_dir = os.path.dirname(config_path)
            if config_dir:
                os.makedirs(config_dir, exist_ok=True)
            
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(config_data, f, indent=2, ensure_ascii=False)
            
            print(f"Config saved to {config_path}")
        except Exception as e:
            print(f"Failed to save config to {config_path}: {e}")
    
    @staticmethod
    def create_custom_config(
        model: str = "qwen2.5-coder:7b",
        host: str = "http://localhost:11434",
        max_parallel_tasks: int = 5,
        default_mode: str = "hierarchy"
    ) -> OrchestratorConfig:
        """
        创建自定义配置
        
        Args:
            model: 模型名称
            host: 模型服务地址
            max_parallel_tasks: 最大并行任务数
            default_mode: 默认协作模式
            
        Returns:
            OrchestratorConfig: 自定义配置
        """
        config = AgentConfigManager.get_default_config()
        
        # 更新模型配置
        config.master_agent_config.model = model
        config.master_agent_config.host = host
        
        for agent_config in config.agent_configs:
            agent_config.model = model
            agent_config.host = host
        
        # 更新编排器配置
        config.max_parallel_tasks = max_parallel_tasks
        config.default_collaboration_mode = CollaborationMode(default_mode)
        
        return config
    
    @staticmethod
    def get_minimal_config() -> OrchestratorConfig:
        """
        获取最小化配置（仅包含必要的Agent）
        
        Returns:
            OrchestratorConfig: 最小化配置
        """
        config = AgentConfigManager.get_default_config()
        
        # 仅启用CodeAgent和TestAgent
        for agent_config in config.agent_configs:
            if agent_config.agent_type not in [AgentType.CODE, AgentType.TEST]:
                agent_config.enabled = False
        
        return config
