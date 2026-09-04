"""
DocAgent - 文档专家Agent（委托受限工具集的 ReActEngine 真实执行）
"""
from typing import Dict, Any
from .base_agent import ReActDelegateAgent
from .agent_types import AgentType


class DocAgent(ReActDelegateAgent):
    """文档专家Agent：撰写 API 文档、技术说明与使用指南。"""

    ROLE_PROMPT = (
        "你是多 Agent 团队中的文档专家。只负责当前子任务的文档工作：先 read_file /"
        "search_files 了解代码或用 query_knowledge_base 查资料，再把 Markdown 文档"
        "写入文件。不要修改代码。Final Answer 必须给出文档路径与内容提要。"
    )
    ALLOWED_TOOLS = {
        "read_file", "write_file", "list_directory", "search_files",
        "query_knowledge_base", "web_search",
    }
    ESSENTIAL_TOOLS = {"write_file"}
    TASK_TYPE_HINTS = {
        "documentation": "撰写准确、结构清晰的 Markdown 文档",
        "api_documentation": "逐个接口说明参数、返回值与示例，以代码为准",
        "technical_writing": "面向开发者的技术说明，避免空泛描述",
        "user_guide": "面向使用者的分步指南",
    }

    def __init__(self, agent_id: str = "doc_agent_1", config: Dict[str, Any] = None):
        capabilities = [
            "documentation",
            "api_documentation",
            "technical_writing",
            "user_guide",
        ]
        super().__init__(
            agent_id=agent_id,
            agent_type=AgentType.DOC,
            capabilities=capabilities,
            config=config or {},
        )
