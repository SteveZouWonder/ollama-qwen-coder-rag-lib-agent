"""
核心 RAG 引擎 - 基于 LlamaIndex + Ollama + ChromaDB
增加 Agent 工具接口，供 ReAct 引擎调用
"""
import os
import logging
import warnings

# 禁用ChromaDB遥测，避免capture()错误
os.environ['ANONYMIZED_TELEMETRY'] = 'False'
os.environ['CHROMA_TELEMETRY'] = 'False'
logging.getLogger("chromadb").setLevel(logging.ERROR)
logging.getLogger("chromadb.segment").setLevel(logging.ERROR)

# 禁用urllib3的OpenSSL警告（macOS LibreSSL版本问题）
warnings.filterwarnings("ignore", message="urllib3 v2 only supports OpenSSL 1.1.1+")

from pathlib import Path
from typing import List, Optional

from llama_index.core import (
    VectorStoreIndex,
    Settings,
    StorageContext,
    load_index_from_storage,
)
from llama_index.core.node_parser import SentenceSplitter
from llama_index.core.schema import Document
from llama_index.embeddings.ollama import OllamaEmbedding
from llama_index.llms.ollama import Ollama
from llama_index.vector_stores.chroma import ChromaVectorStore
import chromadb

from config import (
    OLLAMA_BASE_URL,
    LLM_MODEL,
    EMBED_MODEL,
    VECTOR_DB_PATH,
    INDEX_DIR,
    CHUNK_SIZE,
    CHUNK_OVERLAP,
    TOP_K,
    SIMILARITY_CUTOFF,
)
from document_loader import load_documents

# 导入快照管理
try:
    from knowledge_snapshot import KnowledgeSnapshotManager, AutoSnapshotTrigger
    SNAPSHOT_AVAILABLE = True
except ImportError:
    SNAPSHOT_AVAILABLE = False

# 导入内容安全扫描器
try:
    from content_security import ContentSecurityScanner, ThreatLevel
    SECURITY_AVAILABLE = True
except ImportError:
    SECURITY_AVAILABLE = False


class RAGEngine:
    """RAG 知识库引擎 - 支持独立查询和 Agent 工具调用"""

    def __init__(self, enable_auto_snapshot: bool = True, enable_security: bool = True):
        self.index: Optional[VectorStoreIndex] = None
        self.query_engine = None
        self.enable_auto_snapshot = enable_auto_snapshot
        self.enable_security = enable_security
        self._setup_llm()
        self._setup_embedding()
        self._setup_chroma()
        
        # 初始化快照管理器
        self.snapshot_manager = None
        self.auto_snapshot_trigger = None
        if SNAPSHOT_AVAILABLE and enable_auto_snapshot:
            try:
                self.snapshot_manager = KnowledgeSnapshotManager(index_dir=str(INDEX_DIR))
                self.auto_snapshot_trigger = AutoSnapshotTrigger(self.snapshot_manager)
                print("✅ 自动快照已启用")
            except Exception as e:
                print(f"⚠️ 自动快照初始化失败: {e}")
        
        # 初始化安全扫描器
        self.security_scanner = None
        if SECURITY_AVAILABLE and enable_security:
            try:
                self.security_scanner = ContentSecurityScanner()
                print("🔒 内容安全扫描器已启用")
            except Exception as e:
                print(f"⚠️ 安全扫描器初始化失败: {e}")

    def _setup_llm(self):
        """配置 Ollama LLM"""
        print(f"🤖 加载 LLM 模型: {LLM_MODEL}")
        Settings.llm = Ollama(
            model=LLM_MODEL,
            base_url=OLLAMA_BASE_URL,
            request_timeout=120.0,
            temperature=0.1,
        )

    def _setup_embedding(self):
        """配置 Ollama Embedding"""
        print(f"🔢 加载 Embedding 模型: {EMBED_MODEL}")
        Settings.embed_model = OllamaEmbedding(
            model_name=EMBED_MODEL,
            base_url=OLLAMA_BASE_URL,
            ollama_additional_kwargs={"mirostat": 0},
        )

    def _setup_chroma(self):
        """配置 ChromaDB 向量存储"""
        print(f"💾 向量数据库: {VECTOR_DB_PATH}")
        self.chroma_client = chromadb.PersistentClient(path=VECTOR_DB_PATH)
        self.chroma_collection = self.chroma_client.get_or_create_collection(
            name="rag_knowledge_base"
        )
        self.vector_store = ChromaVectorStore(chroma_collection=self.chroma_collection)

    def build_index(
        self,
        documents: List[Document],
        persist: bool = True,
        file_paths: List[str] = None,
    ) -> VectorStoreIndex:
        """构建向量索引"""
        print(f"\n🏗️  构建索引中... (文档数: {len(documents)})")

        node_parser = SentenceSplitter(
            chunk_size=CHUNK_SIZE,
            chunk_overlap=CHUNK_OVERLAP,
        )
        Settings.node_parser = node_parser

        storage_context = StorageContext.from_defaults(
            vector_store=self.vector_store
        )

        self.index = VectorStoreIndex.from_documents(
            documents,
            storage_context=storage_context,
            show_progress=True,
        )

        if persist:
            self._persist_index()

        self._setup_query_engine()
        print("✅ 索引构建完成！")
        return self.index

    def _persist_index(self):
        """持久化索引到磁盘"""
        persist_dir = INDEX_DIR / "llama_index"
        persist_dir.mkdir(exist_ok=True)
        self.index.storage_context.persist(persist_dir=str(persist_dir))
        print(f"💾 索引已保存到: {persist_dir}")

    def load_index(self) -> Optional[VectorStoreIndex]:
        """从磁盘加载索引"""
        persist_dir = INDEX_DIR / "llama_index"
        if not persist_dir.exists():
            print("⚠️  未找到持久化索引，请先构建索引")
            return None

        print(f"📂 加载索引: {persist_dir}")
        storage_context = StorageContext.from_defaults(
            vector_store=self.vector_store,
            persist_dir=str(persist_dir),
        )
        self.index = load_index_from_storage(storage_context)
        self._setup_query_engine()
        print("✅ 索引加载完成！")
        return self.index

    def _setup_query_engine(self):
        """配置查询引擎"""
        if self.index is None:
            return
        self.query_engine = self.index.as_query_engine(
            similarity_top_k=TOP_K,
            response_mode="compact",
            node_postprocessors=[],
        )

    def add_documents(self, documents: List[Document], file_paths: List[str] = None):
        """向现有索引添加新文档"""
        if self.index is None:
            print("⚠️  索引不存在，将创建新索引")
            return self.build_index(documents, file_paths=file_paths)

        print(f"\n➕ 添加 {len(documents)} 个新文档到索引...")
        
        # 安全检查
        if self.security_scanner and file_paths:
            for file_path in file_paths:
                try:
                    # 读取文件内容进行安全检查
                    path = Path(file_path)
                    if path.exists():
                        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                            content = f.read()
                        
                        is_safe, issues = self.security_scanner.scan_content(content, path.name)
                        if not is_safe:
                            threat_level = self.security_scanner.assess_overall_threat(issues)
                            if threat_level == ThreatLevel.HIGH:
                                print(f"❌ 拒绝添加文件 {path.name} - 检测到严重安全问题")
                                print(f"   检测到 {len(issues)} 个安全问题")
                                continue
                            else:
                                print(f"⚠️  文件 {path.name} 包含潜在安全问题，但仍会添加")
                except Exception as e:
                    print(f"⚠️  无法检查文件 {file_path} 的安全性: {e}")
        
        for doc in documents:
            self.index.insert(doc)

        self._persist_index()
        print("✅ 文档添加完成！")
        
        # 触发自动快照
        if self.auto_snapshot_trigger and file_paths:
            try:
                if len(file_paths) == 1:
                    self.auto_snapshot_trigger.on_document_added(file_paths[0], len(documents))
                else:
                    self.auto_snapshot_trigger.on_documents_batch_added(file_paths)
            except Exception as e:
                print(f"⚠️ 自动快照失败: {e}")

    def query(self, question: str) -> str:
        """查询知识库"""
        if self.query_engine is None:
            raise RuntimeError("索引未初始化，请先构建或加载索引")
        print(f"\n🔍 查询: {question}")
        response = self.query_engine.query(question)
        return str(response)

    def query_with_sources(self, question: str, progress_callback=None) -> dict:
        """
        查询并返回来源信息
        
        Args:
            question: 查询问题
            progress_callback: 进度回调函数，接收字典参数：
                - phase: 当前阶段 (embedding|retrieving|scoring|generating)
                - message: 进度消息
                - current: 当前步骤（可选）
                - total: 总步骤（可选）
        """
        if self.query_engine is None:
            raise RuntimeError("索引未初始化")
        
        # 调用进度回调：开始生成查询向量
        if progress_callback:
            progress_callback({"phase": "embedding", "message": "正在生成查询向量..."})
        
        response = self.query_engine.query(question)
        
        # 调用进度回调：检索完成
        source_count = len(response.source_nodes) if hasattr(response, "source_nodes") else 0
        if progress_callback:
            progress_callback({"phase": "retrieving", "message": f"检索到 {source_count} 个相关文档"})

        sources = []
        if hasattr(response, "source_nodes"):
            for i, node in enumerate(response.source_nodes):
                # 调用进度回调：评分文档
                if progress_callback:
                    progress_callback({
                        "phase": "scoring",
                        "message": f"评分文档 {i+1}/{source_count}",
                        "current": i+1,
                        "total": source_count
                    })
                
                sources.append({
                    "content": node.node.get_content()[:300],
                    "score": float(node.score) if hasattr(node, "score") else None,
                    "file": node.node.metadata.get("file_name", "未知"),
                    "path": node.node.metadata.get("file_path", ""),
                })
        
        # 调用进度回调：生成回答
        if progress_callback:
            progress_callback({"phase": "generating", "message": "正在生成回答..."})

        return {
            "answer": str(response),
            "sources": sources,
        }

    # ==================== Agent 工具接口 ====================

    def query_tool(self, question: str) -> str:
        """
        供 Agent 调用的知识库查询工具
        返回简洁的字符串，包含回答和来源
        """
        if self.query_engine is None:
            return "[错误] 知识库索引未初始化，请先添加文档构建索引。"
        try:
            result = self.query_with_sources(question)
            answer = result["answer"]
            sources_info = ""
            if result["sources"]:
                sources_info = "\n\n[参考来源]\n"
                for i, src in enumerate(result["sources"][:3], 1):
                    score = f"(相似度: {src['score']:.3f})" if src['score'] else ""
                    sources_info += f"{i}. {src['file']} {score}\n"
            return answer + sources_info
        except Exception as e:
            return f"[错误] 知识库查询失败: {str(e)}"

    def add_document_tool(self, file_path: str) -> str:
        """
        供 Agent 调用的添加文档工具
        """
        try:
            path = Path(file_path)
            if not path.exists():
                return f"[错误] 文件不存在: {file_path}"
            docs = load_documents(str(path))
            if not docs:
                return f"[错误] 无法加载文档: {file_path}"
            self.add_documents(docs)
            return f"[成功] 已将 {path.name} ({len(docs)} 个片段) 添加到知识库"
        except Exception as e:
            return f"[错误] 添加文档失败: {str(e)}"

    def get_stats_tool(self) -> str:
        """供 Agent 调用的统计信息工具"""
        try:
            count = self.chroma_collection.count()
            return (
                f"知识库统计:\n"
                f"- 文档片段总数: {count}\n"
                f"- LLM 模型: {LLM_MODEL}\n"
                f"- Embedding 模型: {EMBED_MODEL}\n"
                f"- 分块大小: {CHUNK_SIZE}\n"
                f"- 检索数量: {TOP_K}"
            )
        except Exception as e:
            return f"[错误] 获取统计失败: {str(e)}"

    def get_stats(self) -> dict:
        """获取知识库统计信息"""
        count = self.chroma_collection.count()
        return {
            "total_documents": count,
            "vector_db_path": VECTOR_DB_PATH,
            "llm_model": LLM_MODEL,
            "embed_model": EMBED_MODEL,
            "chunk_size": CHUNK_SIZE,
            "chunk_overlap": CHUNK_OVERLAP,
            "top_k": TOP_K,
        }

    def clear_index(self):
        """清空索引"""
        print("🗑️  清空索引...")
        try:
            self.chroma_client.delete_collection("rag_knowledge_base")
        except Exception:
            pass
        self.chroma_collection = self.chroma_client.create_collection(
            name="rag_knowledge_base"
        )
        self.vector_store = ChromaVectorStore(chroma_collection=self.chroma_collection)
        self.index = None
        self.query_engine = None
        print("✅ 索引已清空")


def build_knowledge_base(
    data_path: Optional[str] = None,
    file_types: Optional[List[str]] = None,
) -> RAGEngine:
    """便捷函数：一键构建知识库"""
    engine = RAGEngine()
    documents = load_documents(data_path, file_types)
    if not documents:
        print("⚠️  未找到任何文档")
        return engine
    
    # 收集文件路径
    file_paths = set()
    if data_path:
        path = Path(data_path)
        if path.is_file():
            file_paths.add(str(path))
        elif path.is_dir():
            pattern = "**/*"
            for file_path in path.glob(pattern):
                if file_path.is_file():
                    file_paths.add(str(file_path))
    
    engine.build_index(documents, file_paths=list(file_paths))
    
    # 创建初始快照
    if engine.auto_snapshot_trigger and file_paths:
        try:
            engine.auto_snapshot_trigger.on_documents_batch_added(list(file_paths))
        except Exception as e:
            print(f"⚠️ 初始快照失败: {e}")
    
    return engine
