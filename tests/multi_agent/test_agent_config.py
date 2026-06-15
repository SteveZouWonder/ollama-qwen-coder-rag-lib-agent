"""
测试agent_config模块
"""
import tempfile
import os
from agent_config import AgentConfigManager
from agents.agent_types import AgentConfig, OrchestratorConfig, AgentType, CollaborationMode


class TestAgentConfigManager:
    """测试AgentConfigManager类"""
    
    def test_get_default_config(self):
        """测试获取默认配置"""
        config = AgentConfigManager.get_default_config()
        
        assert config is not None
        assert isinstance(config, OrchestratorConfig)
        assert config.master_agent_config is not None
        assert len(config.agent_configs) > 0
    
    def test_default_config_master_agent(self):
        """测试默认配置中的MasterAgent配置"""
        config = AgentConfigManager.get_default_config()
        
        master_config = config.master_agent_config
        assert master_config.agent_type == AgentType.MASTER
        assert master_config.agent_id == "master_agent"
        assert master_config.model == "qwen2.5-coder:7b"
        assert "task_decomposition" in master_config.capabilities
    
    def test_default_config_specialized_agents(self):
        """测试默认配置中的专业Agent配置"""
        config = AgentConfigManager.get_default_config()
        
        # 应该有5个专业Agent
        assert len(config.agent_configs) == 5
        
        # 检查各个Agent类型
        agent_types = {cfg.agent_type for cfg in config.agent_configs}
        assert AgentType.CODE in agent_types
        assert AgentType.RAG in agent_types
        assert AgentType.TEST in agent_types
        assert AgentType.DOC in agent_types
        assert AgentType.AUDIT in agent_types
    
    def test_default_config_orchestrator_settings(self):
        """测试默认配置的编排器设置"""
        config = AgentConfigManager.get_default_config()
        
        assert config.default_collaboration_mode == CollaborationMode.HIERARCHY
        assert config.max_parallel_tasks == 5
        assert config.task_timeout == 600
        assert config.enable_logging is True
        assert config.log_level == "INFO"
    
    def test_config_to_dict(self):
        """测试配置转换为字典"""
        config = AgentConfigManager.get_default_config()
        
        config_dict = config.to_dict()
        
        assert "master_agent_config" in config_dict
        assert "agent_configs" in config_dict
        assert "default_collaboration_mode" in config_dict
        assert isinstance(config_dict["agent_configs"], list)
    
    def test_agent_config_to_dict(self):
        """测试AgentConfig转换为字典"""
        agent_config = AgentConfig(
            agent_id="test_agent",
            agent_type=AgentType.CODE,
            model="qwen2.5-coder:7b",
            host="http://localhost:11434",
            capabilities=["code_generation"],
            specialized_tools=[]
        )
        
        config_dict = agent_config.to_dict()
        
        assert config_dict["agent_id"] == "test_agent"
        assert config_dict["agent_type"] == "code"
        assert config_dict["model"] == "qwen2.5-coder:7b"
        assert config_dict["capabilities"] == ["code_generation"]
    
    def test_load_config_from_file(self):
        """测试从文件加载配置"""
        # 创建临时配置文件
        config = AgentConfigManager.get_default_config()
        config_dict = config.to_dict()
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            import json
            json.dump(config_dict, f)
            temp_file = f.name
        
        try:
            loaded_config = AgentConfigManager.load_config_from_file(temp_file)
            
            assert loaded_config is not None
            assert loaded_config.master_agent_config.agent_id == config.master_agent_config.agent_id
            assert len(loaded_config.agent_configs) == len(config.agent_configs)
        finally:
            os.unlink(temp_file)
    
    def test_load_config_from_nonexistent_file(self):
        """测试从不存在的文件加载配置"""
        loaded_config = AgentConfigManager.load_config_from_file("/nonexistent/file.json")
        
        assert loaded_config is None
    
    def test_parse_config(self):
        """测试解析配置数据"""
        config_data = {
            "master_agent_config": {
                "agent_id": "master",
                "agent_type": "master",
                "model": "qwen2.5-coder:7b",
                "host": "http://localhost:11434",
                "capabilities": ["coordination"],
                "specialized_tools": [],
                "max_iterations": 50,
                "timeout": 300,
                "enabled": True,
                "config_data": {}
            },
            "agent_configs": [
                {
                    "agent_id": "code_agent",
                    "agent_type": "code",
                    "model": "qwen2.5-coder:7b",
                    "host": "http://localhost:11434",
                    "capabilities": ["code_generation"],
                    "specialized_tools": [],
                    "max_iterations": 50,
                    "timeout": 300,
                    "enabled": True,
                    "config_data": {}
                }
            ],
            "default_collaboration_mode": "parallel",
            "max_parallel_tasks": 10,
            "task_timeout": 900,
            "enable_logging": False,
            "log_level": "DEBUG",
            "log_file": "/tmp/test.log"
        }
        
        config = AgentConfigManager.parse_config(config_data)
        
        assert config is not None
        assert config.master_agent_config.agent_id == "master"
        assert len(config.agent_configs) == 1
        assert config.default_collaboration_mode == CollaborationMode.PARALLEL
        assert config.max_parallel_tasks == 10
        assert config.enable_logging is False
    
    def test_save_config_to_file(self):
        """测试保存配置到文件"""
        config = AgentConfigManager.get_default_config()
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            temp_file = f.name
        
        try:
            AgentConfigManager.save_config_to_file(config, temp_file)
            
            # 验证文件存在
            assert os.path.exists(temp_file)
            
            # 验证可以重新加载
            loaded_config = AgentConfigManager.load_config_from_file(temp_file)
            assert loaded_config is not None
        finally:
            if os.path.exists(temp_file):
                os.unlink(temp_file)
    
    def test_save_config_to_file_with_directory(self):
        """测试保存配置到需要创建目录的路径"""
        config = AgentConfigManager.get_default_config()
        
        with tempfile.TemporaryDirectory() as temp_dir:
            config_file = os.path.join(temp_dir, "subdir", "config.json")
            
            AgentConfigManager.save_config_to_file(config, config_file)
            
            assert os.path.exists(config_file)
    
    def test_create_custom_config(self):
        """测试创建自定义配置"""
        config = AgentConfigManager.create_custom_config(
            model="custom_model",
            host="http://custom-host:11434",
            max_parallel_tasks=8,
            default_mode="parallel"
        )
        
        assert config.master_agent_config.model == "custom_model"
        assert config.master_agent_config.host == "http://custom-host:11434"
        assert config.max_parallel_tasks == 8
        assert config.default_collaboration_mode == CollaborationMode.PARALLEL
        
        # 检查所有Agent的模型是否都被更新
        for agent_config in config.agent_configs:
            assert agent_config.model == "custom_model"
            assert agent_config.host == "http://custom-host:11434"
    
    def test_create_custom_config_default_params(self):
        """测试创建自定义配置使用默认参数"""
        config = AgentConfigManager.create_custom_config()
        
        assert config.master_agent_config.model == "qwen2.5-coder:7b"
        assert config.max_parallel_tasks == 5
        assert config.default_collaboration_mode == CollaborationMode.HIERARCHY
    
    def test_get_minimal_config(self):
        """测试获取最小化配置"""
        config = AgentConfigManager.get_minimal_config()
        
        # 检查只有CodeAgent和TestAgent被启用
        enabled_agents = [cfg for cfg in config.agent_configs if cfg.enabled]
        assert len(enabled_agents) == 2
        
        enabled_types = {cfg.agent_type for cfg in enabled_agents}
        assert AgentType.CODE in enabled_types
        assert AgentType.TEST in enabled_types
    
    def test_get_minimal_config_structure(self):
        """测试最小化配置的结构"""
        config = AgentConfigManager.get_minimal_config()
        
        assert config.master_agent_config is not None
        assert len(config.agent_configs) == 5  # 总共5个配置，但只有2个启用
        assert isinstance(config, OrchestratorConfig)
    
    def test_agent_config_disabled(self):
        """测试禁用的Agent配置"""
        config = AgentConfig(
            agent_id="disabled_agent",
            agent_type=AgentType.CODE,
            model="qwen2.5-coder:7b",
            host="http://localhost:11434",
            capabilities=["code_generation"],
            specialized_tools=[],
            enabled=False
        )
        
        assert config.enabled is False
    
    def test_agent_config_custom_settings(self):
        """测试自定义Agent配置设置"""
        config = AgentConfig(
            agent_id="custom_agent",
            agent_type=AgentType.CODE,
            model="custom_model",
            host="http://custom-host:11434",
            capabilities=["code_generation", "testing"],
            specialized_tools=["analyzer", "profiler"],
            max_iterations=100,
            timeout=600,
            enabled=True,
            config_data={"custom_key": "custom_value"}
        )
        
        assert config.max_iterations == 100
        assert config.timeout == 600
        assert len(config.specialized_tools) == 2
        assert config.config_data["custom_key"] == "custom_value"
    
    def test_orchestrator_config_custom_log_settings(self):
        """测试自定义日志设置"""
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
            default_collaboration_mode=CollaborationMode.PARALLEL,
            enable_logging=True,
            log_level="DEBUG",
            log_file="/tmp/debug.log"
        )
        
        assert config.enable_logging is True
        assert config.log_level == "DEBUG"
        assert config.log_file == "/tmp/debug.log"
    
    def test_orchestrator_config_no_logging(self):
        """测试禁用日志"""
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
            default_collaboration_mode=CollaborationMode.HIERARCHY,
            enable_logging=False
        )
        
        assert config.enable_logging is False
        assert config.log_file is None
    
    def test_load_config_invalid_json(self):
        """测试加载无效的JSON配置"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write("invalid json content")
            temp_file = f.name
        
        try:
            loaded_config = AgentConfigManager.load_config_from_file(temp_file)
            assert loaded_config is None
        finally:
            os.unlink(temp_file)
    
    def test_parse_config_missing_fields(self):
        """测试解析缺少字段的配置"""
        config_data = {
            "master_agent_config": {
                "agent_id": "master",
                "agent_type": "master"
            },
            "agent_configs": [],
            "default_collaboration_mode": "hierarchy"
        }
        
        # 应该能解析并使用默认值
        config = AgentConfigManager.parse_config(config_data)
        assert config is not None
        assert config.master_agent_config.agent_id == "master"
    
    def test_parse_config_empty_agent_type(self):
        """测试解析空的Agent类型"""
        config_data = {
            "master_agent_config": {
                "agent_id": "master",
                "agent_type": ""
            },
            "agent_configs": [],
            "default_collaboration_mode": "hierarchy"
        }
        
        # 应该能处理空的agent_type
        try:
            config = AgentConfigManager.parse_config(config_data)
            # 如果解析失败，这是可以接受的
        except (ValueError, KeyError):
            pass  # 预期的错误
    
    def test_get_default_config_completeness(self):
        """测试默认配置的完整性"""
        config = AgentConfigManager.get_default_config()
        
        # 验证所有必需字段都存在
        assert config.master_agent_config.agent_id is not None
        assert config.master_agent_config.model is not None
        assert config.master_agent_config.host is not None
        assert len(config.agent_configs) == 5
        
        # 验证每个专业Agent配置
        for agent_config in config.agent_configs:
            assert agent_config.agent_id is not None
            assert agent_config.agent_type is not None
            assert agent_config.capabilities is not None
