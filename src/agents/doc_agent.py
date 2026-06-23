"""
DocAgent - 文档专家Agent
"""
from typing import Dict, Any
import time
from .base_agent import BaseAgent
from .agent_types import AgentTask, AgentResult, AgentType


class DocAgent(BaseAgent):
    """文档专家Agent，专注于文档相关任务"""
    
    def __init__(self, agent_id: str = "doc_agent_1", config: Dict[str, Any] = None):
        """
        初始化DocAgent
        
        Args:
            agent_id: Agent ID
            config: 配置字典
        """
        capabilities = [
            "documentation",
            "api_documentation",
            "technical_writing",
            "user_guide"
        ]
        
        super().__init__(
            agent_id=agent_id,
            agent_type=AgentType.DOC,
            capabilities=capabilities,
            config=config or {}
        )
    
    def process_task(self, task: AgentTask) -> AgentResult:
        """
        处理文档任务
        
        Args:
            task: 任务对象
            
        Returns:
            AgentResult: 执行结果
        """
        start_time = time.time()
        
        try:
            # 根据任务类型处理
            if task.task_type == "documentation":
                result = self._handle_documentation(task)
            elif task.task_type == "api_documentation":
                result = self._handle_api_documentation(task)
            elif task.task_type == "technical_writing":
                result = self._handle_technical_writing(task)
            elif task.task_type == "user_guide":
                result = self._handle_user_guide(task)
            else:
                result = self._handle_general_task(task)
            
            execution_time = time.time() - start_time
            result.execution_time = execution_time
            result.task_id = task.task_id
            result.agent_id = self.agent_id
            
            return result
            
        except Exception as e:
            execution_time = time.time() - start_time
            self.logger.error(f"Error processing task: {e}")
            
            return AgentResult(
                task_id=task.task_id,
                agent_id=self.agent_id,
                success=False,
                output="",
                metadata={},
                execution_time=execution_time,
                error_message=str(e)
            )
    
    def _handle_documentation(self, task: AgentTask) -> AgentResult:
        """处理文档生成任务"""
        request = task.input_data.get("request", "")
        
        output = f"# 文档生成结果\n# 任务: {request}\n\n"
        output += "## 项目概述\n"
        output += "本文档描述了项目的功能和使用方法。\n\n"
        output += "## 安装\n"
        output += "```bash\npip install package-name\n```\n"
        
        return AgentResult(
            task_id=task.task_id,
            agent_id=self.agent_id,
            success=True,
            output=output,
            metadata={
                "task_type": "documentation",
                "sections": 3,
                "word_count": 150
            },
            execution_time=0
        )
    
    def _handle_api_documentation(self, task: AgentTask) -> AgentResult:
        """处理API文档任务"""
        request = task.input_data.get("request", "")
        
        output = f"# API文档\n# 任务: {request}\n\n"
        output += "## API端点\n\n"
        output += "### GET /api/resource\n"
        output += "获取资源列表\n\n"
        output += "### POST /api/resource\n"
        output += "创建新资源\n"
        
        return AgentResult(
            task_id=task.task_id,
            agent_id=self.agent_id,
            success=True,
            output=output,
            metadata={
                "task_type": "api_documentation",
                "endpoints_documented": 5
            },
            execution_time=0
        )
    
    def _handle_technical_writing(self, task: AgentTask) -> AgentResult:
        """处理技术写作任务"""
        request = task.input_data.get("request", "")
        
        output = f"# 技术文档\n# 任务: {request}\n\n"
        output += "## 技术架构\n"
        output += "系统采用模块化设计...\n"
        
        return AgentResult(
            task_id=task.task_id,
            agent_id=self.agent_id,
            success=True,
            output=output,
            metadata={
                "task_type": "technical_writing",
                "complexity": "medium"
            },
            execution_time=0
        )
    
    def _handle_user_guide(self, task: AgentTask) -> AgentResult:
        """处理用户指南任务"""
        request = task.input_data.get("request", "")
        
        output = f"# 用户指南\n# 任务: {request}\n\n"
        output += "## 快速开始\n"
        output += "1. 安装软件\n"
        output += "2. 配置设置\n"
        output += "3. 开始使用\n"
        
        return AgentResult(
            task_id=task.task_id,
            agent_id=self.agent_id,
            success=True,
            output=output,
            metadata={
                "task_type": "user_guide",
                "steps": 10
            },
            execution_time=0
        )
    
    def _handle_general_task(self, task: AgentTask) -> AgentResult:
        """处理通用任务"""
        request = task.input_data.get("request", "")
        
        output = f"# DocAgent处理结果\n# 任务: {request}\n\n"
        output += "任务已由DocAgent处理。\n"
        
        return AgentResult(
            task_id=task.task_id,
            agent_id=self.agent_id,
            success=True,
            output=output,
            metadata={
                "task_type": "general",
                "handled_by": "DocAgent"
            },
            execution_time=0
        )
