#!/usr/bin/env python3
"""
工作流分析器 - 基于常见使用场景预设工作流
"""
import logging
from typing import List, Dict, Optional, Set
from .types import (
    WorkflowDefinition,
    Recommendation,
    RecommendationReason,
    RecommendationSource,
    RecommendationStrength,
    CommandContext
)

logger = logging.getLogger(__name__)


class WorkflowAnalyzer:
    """工作流分析器 - 基于预设工作流推荐命令"""
    
    def __init__(self):
        self.workflows = self._initialize_workflows()
        self.workflow_map = self._build_workflow_map()
    
    def _initialize_workflows(self) -> List[WorkflowDefinition]:
        """初始化预设工作流"""
        return [
            WorkflowDefinition(
                name="new_user",
                description="新用户首次使用引导",
                steps=["/tutorial", "/add", "/ask"],
                entry_conditions=["first_session"],
                completion_commands=["/tutorial"]
            ),
            WorkflowDefinition(
                name="document_management",
                description="文档管理工作流",
                steps=["/file-list", "/add", "/file-info", "/snapshot-create"],
                entry_conditions=["/add", "/file-list"],
                completion_commands=["/snapshot-create"]
            ),
            WorkflowDefinition(
                name="knowledge_query",
                description="知识库查询工作流",
                steps=["/stats", "/ask", "/sources", "/history"],
                entry_conditions=["/stats", "/add"],
                completion_commands=["/history"]
            ),
            WorkflowDefinition(
                name="skill_development",
                description="技能开发工作流",
                steps=["/add", "/generate-skills", "/knowledge-summary"],
                entry_conditions=["/add", "/knowledge-summary"],
                completion_commands=["/generate-skills"]
            ),
            WorkflowDefinition(
                name="system_setup",
                description="系统设置工作流",
                steps=["check_prereqs.sh", "verify_deps.sh", "run_tests.sh"],
                entry_conditions=["first_session", "system_check"],
                completion_commands=["run_tests.sh"]
            ),
            WorkflowDefinition(
                name="backup_restore",
                description="备份恢复工作流",
                steps=["/snapshot-list", "/snapshot-create", "/snapshot-restore"],
                entry_conditions=["/snapshot-list"],
                completion_commands=["/snapshot-restore"]
            ),
            WorkflowDefinition(
                name="code_development",
                description="代码开发工作流",
                steps=["/agent-file", "/ask", "/agent-rag", "/agent-web"],
                entry_conditions=["/agent-file", "/ask"],
                completion_commands=["/agent-web"]
            ),
            WorkflowDefinition(
                name="data_analysis",
                description="数据分析工作流",
                steps=["/graph-build", "/graph-query", "/knowledge-summary"],
                entry_conditions=["/graph-build"],
                completion_commands=["/knowledge-summary"]
            ),
            WorkflowDefinition(
                name="session_start",
                description="会话开始工作流",
                steps=["/stats", "/file-list", "/history"],
                entry_conditions=["session_start"],
                completion_commands=["/history"]
            ),
            WorkflowDefinition(
                name="error_recovery",
                description="错误恢复工作流",
                steps=["/clear", "/stats", "/help"],
                entry_conditions=["error"],
                completion_commands=["/help"]
            )
        ]
    
    def _build_workflow_map(self) -> Dict[str, List[WorkflowDefinition]]:
        """构建命令到工作流的映射"""
        workflow_map = {}
        for workflow in self.workflows:
            for step in workflow.steps:
                if step not in workflow_map:
                    workflow_map[step] = []
                workflow_map[step].append(workflow)
            
            # 处理入口条件
            for condition in workflow.entry_conditions:
                if condition not in workflow_map:
                    workflow_map[condition] = []
                workflow_map[condition].append(workflow)
        
        return workflow_map
    
    def analyze(self, context: CommandContext) -> Dict[str, float]:
        """分析上下文，返回命令推荐得分"""
        scores = {}
        
        # 检查当前命令是否在工作流中
        if context.last_command:
            for workflow in self.workflow_map.get(context.last_command, []):
                next_step = workflow.get_next_step(context.last_command)
                if next_step:
                    # 工作流中的下一步得分较高
                    base_score = 0.7
                    if workflow.name == "error_recovery" and context.recent_errors:
                        base_score = 0.9
                    elif workflow.name == "new_user" and context.command_count < 5:
                        base_score = 0.85
                    scores[next_step] = max(scores.get(next_step, 0), base_score)
        
        # 检查特殊条件
        if context.command_count == 0:
            # 首次使用，引导用户
            scores["/tutorial"] = scores.get("/tutorial", 0) + 0.8
            scores["/help"] = scores.get("/help", 0) + 0.7
        
        if context.knowledge_base_empty and context.rag_engine_available:
            # 知识库为空，引导添加文档
            scores["/add"] = scores.get("/add", 0) + 0.75
            scores["/file-list"] = scores.get("/file-list", 0) + 0.6
        
        if context.recent_errors:
            # 有错误，建议清理和帮助
            scores["/clear"] = scores.get("/clear", 0) + 0.7
            scores["/help"] = scores.get("/help", 0) + 0.6
            scores["/stats"] = scores.get("/stats", 0) + 0.5
        
        if context.has_snapshots and not context.knowledge_base_empty:
            # 有快照，建议查看
            scores["/snapshot-list"] = scores.get("/snapshot-list", 0) + 0.6
        
        return scores
    
    def get_recommendations(self, context: CommandContext, min_score: float = 0.3) -> List[Recommendation]:
        """获取工作流推荐"""
        recommendations = []
        scores = self.analyze(context)
        
        command_descriptions = {
            "/tutorial": "显示使用教程，适合新用户",
            "/add": "添加文档到知识库",
            "/ask": "查询知识库内容",
            "/file-list": "列出知识库中的文件",
            "/stats": "查看知识库统计信息",
            "/sources": "查看查询结果的来源",
            "/history": "查看命令历史",
            "/clear": "清空会话历史",
            "/help": "显示帮助信息",
            "/snapshot-list": "查看快照列表",
            "/snapshot-create": "创建知识库快照",
            "/snapshot-restore": "恢复快照",
            "/generate-skills": "将知识库转换为Skills",
            "/knowledge-summary": "生成知识库摘要",
            "/agent-file": "使用Agent进行文件操作",
            "/agent-rag": "使用Agent进行RAG查询",
            "/agent-web": "使用Agent进行网络搜索",
            "/graph-build": "构建知识图谱",
            "/graph-query": "查询知识图谱",
            "check_prereqs.sh": "检查前置条件",
            "verify_deps.sh": "验证依赖",
            "run_tests.sh": "运行测试套件"
        }
        
        for command, score in scores.items():
            if score >= min_score:
                # 确定推荐强度
                if score >= 0.8:
                    strength = RecommendationStrength.VERY_STRONG
                elif score >= 0.6:
                    strength = RecommendationStrength.STRONG
                elif score >= 0.4:
                    strength = RecommendationStrength.MODERATE
                else:
                    strength = RecommendationStrength.WEAK
                
                # 获取描述
                description = command_descriptions.get(command, f"执行 {command} 命令")
                
                # 创建推荐
                recommendation = Recommendation(
                    command=command,
                    description=description,
                    strength=strength,
                    score=score
                )
                
                # 添加理由
                reason = RecommendationReason(
                    source=RecommendationSource.WORKFLOW,
                    explanation=f"基于工作流分析，这是推荐的下一步操作",
                    confidence=score
                )
                recommendation.add_reason(reason)
                
                # 添加建议路径
                if context.last_command:
                    recommendation.suggested_path = [context.last_command, command]
                
                recommendations.append(recommendation)
        
        return sorted(recommendations, key=lambda x: x.score, reverse=True)
    
    def get_workflow_info(self, command: str) -> Optional[WorkflowDefinition]:
        """获取命令所属的工作流信息"""
        for workflow in self.workflow_map.get(command, []):
            if command in workflow.steps:
                return workflow
        return None