"""
AuditAgent - 审计专家Agent（委托受限工具集的 ReActEngine 真实执行，只读）
"""
from typing import Dict, Any
from .base_agent import ReActDelegateAgent
from .agent_types import AgentType


class AuditAgent(ReActDelegateAgent):
    """审计专家Agent：安全、合规与性能审计（只读，不修改任何文件）。"""

    ROLE_PROMPT = (
        "你是多 Agent 团队中的审计专家，只读审查、绝不修改文件。用 read_file / "
        "search_files / ast_search / code_quality_check / git_analyze 收集证据；"
        "execute_command 只允许只读命令（ls、grep、pytest --collect-only 等）。"
        "Final Answer 按 [高]/[中]/[低] 列出发现，每条注明文件位置与依据；没有证据的"
        "问题不要凭空编造。"
    )
    ALLOWED_TOOLS = {
        "read_file", "search_files", "code_quality_check", "ast_search",
        "git_analyze", "execute_command",
    }
    ESSENTIAL_TOOLS = {"read_file", "search_files", "code_quality_check", "ast_search", "git_analyze", "execute_command"}
    TASK_TYPE_HINTS = {
        "audit": "对目标代码做整体审计，给出分级发现",
        "security_check": "重点检查注入、敏感信息、危险调用等安全问题",
        "compliance_verification": "对照给定规范逐条核对并说明依据",
        "performance_audit": "定位明显的性能热点与低效模式",
    }

    def __init__(self, agent_id: str = "audit_agent_1", config: Dict[str, Any] = None):
        capabilities = [
            "audit",
            "security_check",
            "compliance_verification",
            "performance_audit",
        ]
        super().__init__(
            agent_id=agent_id,
            agent_type=AgentType.AUDIT,
            capabilities=capabilities,
            config=config or {},
        )
