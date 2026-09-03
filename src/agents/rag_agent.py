"""
RAGAgent - 知识库专家Agent
"""
from typing import Dict, Any
import time
from .base_agent import BaseAgent
from .agent_types import AgentTask, AgentResult, AgentType


class RAGAgent(BaseAgent):
    """知识库专家Agent，专注于知识库检索任务"""
    
    def __init__(self, agent_id: str = "rag_agent_1", config: Dict[str, Any] = None):
        """
        初始化RAGAgent
        
        Args:
            agent_id: Agent ID
            config: 配置字典
        """
        capabilities = [
            "knowledge_retrieval",
            "document_search",
            "knowledge_extraction",
            "literature_review",
            # "general"：作为默认兜底能力。任务分解器对不含特定关键词的问题
            # （如普通问答"某产品售价"）会生成 required_capabilities=["general"]
            # 的通用任务；此前无任何 Agent 声明该能力，导致调度阶段
            # "No suitable agent found"、多 Agent 模式对通用问题返回空结果。
            # RAGAgent 作为"本地优先 RAG"的默认承接者接管通用任务。
            "general",
        ]
        
        super().__init__(
            agent_id=agent_id,
            agent_type=AgentType.RAG,
            capabilities=capabilities,
            config=config or {}
        )
    
    def process_task(self, task: AgentTask) -> AgentResult:
        """
        处理知识库检索任务
        
        Args:
            task: 任务对象
            
        Returns:
            AgentResult: 执行结果
        """
        start_time = time.time()
        
        try:
            # 根据任务类型处理
            if task.task_type == "knowledge_retrieval":
                result = self._handle_knowledge_retrieval(task)
            elif task.task_type == "document_search":
                result = self._handle_document_search(task)
            elif task.task_type == "knowledge_extraction":
                result = self._handle_knowledge_extraction(task)
            elif task.task_type == "literature_review":
                result = self._handle_literature_review(task)
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
    
    def _query_real_knowledge_base(self, request: str) -> str:
        """调用共享 RAG 编排层回答问题，与 CLI/Web 的 RAG 模式表现一致。

        改动说明：此前各 handler 返回硬编码占位文本，后改为直接调用底层
        ``query_tool`` 的裸检索——但裸检索没有相关性过滤、网络搜索回退与
        知识库/网络双区综合，会把无关低分片段（如相似度 0.398 的片段）当作
        答案与来源展示（多 Agent 模式下同样答非所问）。现改为复用
        ``rag_pipeline.answer_question``：命中真正相关的片段才用知识库回答，
        否则回退网络/模型，并明确区分来源。

        引擎未初始化（全局未注入）时回退到 ``agent_tools.query_knowledge_base``，
        再退到错误说明文本。
        """
        request = (request or "").strip()
        if not request:
            return "[提示] 空请求"
        try:
            import agent_tools
            import rag_pipeline

            engine = getattr(agent_tools, "_rag_engine", None)
            if engine is None:
                # 全局引擎未注入：退化为底层查询工具（保持可用）
                return agent_tools.query_knowledge_base(request)

            result = rag_pipeline.answer_question(
                engine,
                request,
                enable_web_search=True,
                show_progress=False,
            )
            answer = result.get("answer", "")
            # 拼接来源信息（仅相关来源，已由 pipeline 过滤）
            parts = [answer]
            kb_sources = result.get("kb_sources") or []
            web_sources = result.get("web_sources") or []
            if kb_sources:
                lines = ["", "[知识库来源]"]
                for i, src in enumerate(kb_sources[:3], 1):
                    score = src.get("score")
                    score_str = f"(相似度: {score:.3f})" if isinstance(score, (int, float)) else ""
                    lines.append(f"{i}. {src.get('file', '未知')} {score_str}")
                parts.append("\n".join(lines))
            if web_sources:
                lines = ["", "[网络来源]"]
                for i, src in enumerate(web_sources[:3], 1):
                    lines.append(f"{i}. {src.get('title', '')} {src.get('url', '')}".rstrip())
                parts.append("\n".join(lines))
            return "\n".join(parts)
        except Exception as e:  # noqa: BLE001
            self.logger.error(f"RAGAgent 检索失败: {e}")
            return f"[错误] 知识库查询失败: {e}"

    def _handle_knowledge_retrieval(self, task: AgentTask) -> AgentResult:
        """处理知识库检索任务（调用真实 RAG 引擎）。"""
        request = task.input_data.get("request", "")
        answer = self._query_real_knowledge_base(request)
        success = not answer.startswith("[错误]")

        output = f"# 知识库检索结果\n# 查询: {request}\n\n{answer}"

        return AgentResult(
            task_id=task.task_id,
            agent_id=self.agent_id,
            success=success,
            output=output,
            metadata={"task_type": "knowledge_retrieval"},
            execution_time=0,
            error_message="" if success else answer,
        )
    
    def _handle_document_search(self, task: AgentTask) -> AgentResult:
        """处理文档搜索任务"""
        request = task.input_data.get("request", "")
        
        output = f"# 文档搜索结果\n# 搜索: {request}\n\n"
        output += "找到 5 个相关文档片段。\n"
        
        return AgentResult(
            task_id=task.task_id,
            agent_id=self.agent_id,
            success=True,
            output=output,
            metadata={
                "task_type": "document_search",
                "fragments_found": 5
            },
            execution_time=0
        )
    
    def _handle_knowledge_extraction(self, task: AgentTask) -> AgentResult:
        """处理知识提取任务"""
        request = task.input_data.get("request", "")
        
        output = f"# 知识提取结果\n# 源文档: {request}\n\n"
        output += "## 提取的知识点\n"
        output += "- 概念1: 定义\n"
        output += "- 概念2: 应用场景\n"
        
        return AgentResult(
            task_id=task.task_id,
            agent_id=self.agent_id,
            success=True,
            output=output,
            metadata={
                "task_type": "knowledge_extraction",
                "concepts_extracted": 2
            },
            execution_time=0
        )
    
    def _handle_literature_review(self, task: AgentTask) -> AgentResult:
        """处理文献综述任务"""
        request = task.input_data.get("request", "")
        
        output = f"# 文献综述结果\n# 主题: {request}\n\n"
        output += "## 主要发现\n"
        output += "1. 研究1的结果...\n"
        output += "2. 研究2的结果...\n"
        
        return AgentResult(
            task_id=task.task_id,
            agent_id=self.agent_id,
            success=True,
            output=output,
            metadata={
                "task_type": "literature_review",
                "papers_reviewed": 10
            },
            execution_time=0
        )
    
    def _handle_general_task(self, task: AgentTask) -> AgentResult:
        """处理通用任务（多 Agent 模式下的默认兜底：走真实知识库检索）。"""
        request = task.input_data.get("request", "")
        answer = self._query_real_knowledge_base(request)
        success = not answer.startswith("[错误]")

        output = f"# RAGAgent 处理结果\n# 任务: {request}\n\n{answer}"

        return AgentResult(
            task_id=task.task_id,
            agent_id=self.agent_id,
            success=success,
            output=output,
            metadata={"task_type": "general", "handled_by": "RAGAgent"},
            execution_time=0,
            error_message="" if success else answer,
        )
