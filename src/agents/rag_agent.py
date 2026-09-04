"""
RAGAgent - 知识库专家Agent
"""
from typing import Dict, Any, List, Tuple
import time
from .base_agent import BaseAgent
from .agent_types import AgentTask, AgentResult, AgentType


class RAGAgent(BaseAgent):
    """知识库专家Agent，专注于知识库检索任务"""

    # 各任务类型对应的检索提问变体：同一 answer_question 路径，仅改写提问侧重点。
    # 此前 document_search / knowledge_extraction / literature_review 返回伪造桩数据。
    TASK_PROMPTS = {
        "knowledge_retrieval": "{request}",
        "general": "{request}",
        "document_search": "找出与下述主题相关的文档内容并列出出处：{request}",
        "knowledge_extraction": "从相关文档中提取关于下述主题的关键知识点（概念、定义、要点），逐条列出：{request}",
        "literature_review": "综述相关文档中关于下述主题的主要观点、方法与结论，并注明各来源：{request}",
    }
    
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
            result = self._handle_retrieval(task)
            
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
    
    def _query_real_knowledge_base(self, request: str, context=None) -> Tuple[str, List[Dict[str, Any]]]:
        """调用共享 RAG 编排层回答问题，与 CLI/Web 的 RAG 模式表现一致。

        改动说明：此前各 handler 返回硬编码占位文本，后改为直接调用底层
        ``query_tool`` 的裸检索——但裸检索没有相关性过滤、网络搜索回退与
        知识库/网络双区综合，会把无关低分片段（如相似度 0.398 的片段）当作
        答案与来源展示（多 Agent 模式下同样答非所问）。现改为复用
        ``rag_pipeline.answer_question``：命中真正相关的片段才用知识库回答，
        否则回退网络/模型，并明确区分来源。

        引擎未初始化（全局未注入）时回退到 ``agent_tools.query_knowledge_base``，
        再退到错误说明文本。

        Returns:
            ``(答案文本, 结构化来源列表)``
        """
        request = (request or "").strip()
        if not request:
            return "[提示] 空请求", []
        try:
            import agent_tools
            import rag_pipeline

            engine = getattr(agent_tools, "_rag_engine", None)
            if engine is None:
                # 全局引擎未注入：退化为底层查询工具（保持可用）
                return agent_tools.query_knowledge_base(request), []

            result = rag_pipeline.answer_question(
                engine,
                request,
                enable_web_search=True,
                show_progress=False,
                context=context,
            )
            answer = result.get("answer", "")
            sources: List[Dict[str, Any]] = []
            for src in (result.get("kb_sources") or [])[:5]:
                item = {"kind": "kb", "file": src.get("file", "未知")}
                if isinstance(src.get("score"), (int, float)):
                    item["score"] = round(float(src["score"]), 3)
                if src.get("text"):
                    item["text"] = str(src["text"])[:300]
                sources.append(item)
            for src in (result.get("web_sources") or [])[:5]:
                sources.append({
                    "kind": "web",
                    "title": src.get("title", ""),
                    "url": src.get("url", ""),
                })
            return answer, sources
        except Exception as e:  # noqa: BLE001
            self.logger.error(f"RAGAgent 检索失败: {e}")
            return f"[错误] 知识库查询失败: {e}", []

    def _handle_retrieval(self, task: AgentTask) -> AgentResult:
        """所有任务类型都走真实 RAG 编排，仅按类型改写提问侧重点。"""
        request = task.input_data.get("request", "")
        template = self.TASK_PROMPTS.get(task.task_type, "{request}")
        question = template.format(request=request) if request else request
        # 会话上下文由协调者注入到 Agent 属性（不放进 input_data，保持任务可序列化）
        context = getattr(self, "conversation_context", None)
        answer, sources = self._query_real_knowledge_base(question, context=context)
        success = not answer.startswith("[错误]")

        # 输出即答案本身（单子任务时会被直接作为综合回答展示，不再带 Markdown 标题）
        return AgentResult(
            task_id=task.task_id,
            agent_id=self.agent_id,
            success=success,
            output=answer,
            metadata={
                "task_type": task.task_type,
                "handled_by": "RAGAgent",
                "query": question,
                "kb_hits": sum(1 for s in sources if s.get("kind") == "kb"),
                "web_hits": sum(1 for s in sources if s.get("kind") == "web"),
            },
            execution_time=0,
            error_message="" if success else answer,
            sources=sources,
        )
