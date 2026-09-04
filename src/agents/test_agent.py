"""
QAExpertAgent - 质量保证专家Agent（委托受限工具集的 ReActEngine 真实执行）
"""
from typing import Dict, Any
from .base_agent import ReActDelegateAgent
from .agent_types import AgentType


class QAExpertAgent(ReActDelegateAgent):
    """质量保证专家Agent：编写并运行测试、分析覆盖率与质量。"""

    ROLE_PROMPT = (
        "你是多 Agent 团队中的测试专家。只负责当前子任务的测试工作：先 read_file 了解"
        "被测代码，再用 write_file 把测试真正写入文件，最后用 execute_command 运行（如 "
        "python3 -m pytest -q 文件）。不要修改被测的业务代码。没有 write_file 就不能说"
        "已写入，没有运行就不能报告通过/失败数。Final Answer 给出测试文件路径与真实运行结果。"
    )
    ALLOWED_TOOLS = {
        "read_file", "write_file", "execute_command", "search_files", "code_quality_check",
    }
    ESSENTIAL_TOOLS = {"write_file", "execute_command"}
    TASK_TYPE_HINTS = {
        "testing": "编写并运行测试，报告真实的通过/失败情况",
        "test_generation": "为目标代码生成单元测试并运行一次确认可执行",
        "coverage_analysis": "用 pytest --cov 或等价方式测量覆盖率，报告真实数字",
        "quality_assessment": "用 code_quality_check 评估并给出具体问题清单",
    }

    def __init__(self, agent_id: str = "test_agent_1", config: Dict[str, Any] = None):
        capabilities = [
            "testing",
            "test_generation",
            "coverage_analysis",
            "quality_assessment",
        ]
        super().__init__(
            agent_id=agent_id,
            agent_type=AgentType.TEST,
            capabilities=capabilities,
            config=config or {},
        )
