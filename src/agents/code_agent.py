"""
CodeAgent - 代码专家Agent（委托受限工具集的 ReActEngine 真实执行）
"""
from typing import Dict, Any
from .base_agent import ReActDelegateAgent
from .agent_types import AgentType


class CodeAgent(ReActDelegateAgent):
    """代码专家Agent，专注于代码生成、重构、修复与审查。"""

    ROLE_PROMPT = (
        "你是多 Agent 团队中的代码专家。只负责当前子任务的代码工作：先看相关文件，"
        "再用 write_file 落盘，最后用 execute_command 运行验证。不要写测试文件或文档"
        "（由其他 Agent 负责）。没有 write_file 就不能说已写入。Final Answer 列出改动的"
        "文件路径与真实验证结果。"
    )
    ALLOWED_TOOLS = {
        "read_file", "write_file", "execute_command", "list_directory",
        "search_files", "ast_search", "analyze_project_structure", "get_current_dir",
    }
    ESSENTIAL_TOOLS = {"write_file", "execute_command"}
    TASK_TYPE_HINTS = {
        "code_generation": "实现代码并保证可运行，代码写入文件而不是只贴在回答里",
        "code_refactoring": "重构时保持行为不变，说明改动点",
        "bug_fixing": "先复现/定位问题再修复，说明根因",
        "code_review": "只读审查：指出问题与改进建议，不修改文件",
    }

    def __init__(self, agent_id: str = "code_agent_1", config: Dict[str, Any] = None):
        capabilities = [
            "code_generation",
            "code_refactoring",
            "bug_fixing",
            "code_review",
            "file_operations",
        ]
        super().__init__(
            agent_id=agent_id,
            agent_type=AgentType.CODE,
            capabilities=capabilities,
            config=config or {},
        )
