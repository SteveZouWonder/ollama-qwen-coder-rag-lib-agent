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
from llama_index.core.postprocessor import SimilarityPostprocessor
from llama_index.core.schema import Document
from llama_index.embeddings.ollama import OllamaEmbedding
from llama_index.llms.ollama import Ollama
from llama_index.vector_stores.chroma import ChromaVectorStore
import chromadb

from config import (
    OLLAMA_BASE_URL,
    LLM_MODEL,
    LLM_NUM_CTX,
    LLM_THINK,
    EMBED_MODEL,
    VECTOR_DB_PATH,
    INDEX_DIR,
    CHUNK_SIZE,
    CHUNK_OVERLAP,
    TOP_K,
    SIMILARITY_CUTOFF,
)
from config import resolve_num_ctx as _resolve_num_ctx
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

# 导入文件元数据管理（用于登记“知识库中有哪些文件”，供 /file-list 等命令读取）
try:
    from file_metadata import (
        get_global_metadata_manager,
        FilePersistenceType,
    )
    FILE_METADATA_AVAILABLE = True
except ImportError:
    FILE_METADATA_AVAILABLE = False


class RAGEngine:
    """RAG 知识库引擎 - 支持独立查询和 Agent 工具调用"""

    def __init__(self, enable_auto_snapshot: bool = True, enable_security: bool = True):
        self.index: Optional[VectorStoreIndex] = None
        self.query_engine = None
        # 最近一次入库时知识图谱是否成功派生构建（供 CLI 调整提示文案）
        self.last_graph_derived: bool = False
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

        # 初始化文件元数据管理器（与 /file-list 等命令共享同一全局实例，
        # 确保文档入库时登记的元数据可被文件管理命令读取）。
        self.metadata_manager = None
        if FILE_METADATA_AVAILABLE:
            try:
                self.metadata_manager = get_global_metadata_manager()
            except Exception as e:
                print(f"⚠️ 文件元数据管理器初始化失败: {e}")

    def _setup_llm(
        self,
        model: Optional[str] = None,
        num_ctx: Optional[int] = None,
        think: Optional[bool] = None,
    ):
        """配置 Ollama LLM（初始化与运行时热切换/思考开关共用）。"""
        self.llm_model = model or LLM_MODEL
        self.llm_num_ctx = num_ctx or (
            LLM_NUM_CTX if model is None else _resolve_num_ctx(self.llm_model)
        )
        if think is None:
            # 首次初始化读 config；后续切换模型时保留当前开关状态
            think = getattr(self, "llm_think", LLM_THINK)
        self.llm_think = bool(think)
        print(f"🤖 加载 LLM 模型: {self.llm_model} (num_ctx={self.llm_num_ctx}, think={self.llm_think})")
        Settings.llm = Ollama(
            model=self.llm_model,
            base_url=OLLAMA_BASE_URL,
            request_timeout=120.0,
            temperature=0.1,
            # 显式限制上下文窗口，避免 Ollama 按模型默认的超大上下文（如 256K）
            # 分配 KV cache 撑爆显存、卸载到 CPU 导致卡顿。值按模型自动推导。
            context_window=self.llm_num_ctx,
            additional_kwargs={"num_ctx": self.llm_num_ctx},
            # 默认关闭思考模式：RAG 综合/相关性判定无需长思维链，显著缩短响应。
            thinking=self.llm_think,
        )

    def set_think(self, enabled: bool) -> bool:
        """运行时开关思考模式（供 CLI ``/think`` 与 Web 复选框使用）。

        重建 ``Settings.llm`` 与缓存的 query_engine（原因同 ``set_model``）。
        """
        self._setup_llm(model=self.llm_model, num_ctx=self.llm_num_ctx, think=bool(enabled))
        self._setup_query_engine()
        return self.llm_think

    def set_model(self, model: str) -> int:
        """运行时切换 LLM（供 CLI ``/model <name>`` 与 Web 下拉使用）。

        重建 ``Settings.llm`` 并重建已缓存的 query_engine（llama_index 在
        ``as_query_engine`` 时把 LLM 捕获进 response synthesizer，仅替换
        ``Settings.llm`` 不会生效）。Embedding 与向量库不受影响。返回新 num_ctx。
        """
        model = (model or "").strip()
        if not model:
            raise ValueError("模型名不能为空")
        self._setup_llm(model=model)
        self._setup_query_engine()
        return self.llm_num_ctx

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

        # 登记文件元数据（供 /file-list 等命令读取）。复用上面创建的 node_parser，
        # 避免重复构造 SentenceSplitter。
        self._register_file_metadata(documents, file_paths, splitter=node_parser)

        # 派生构建知识图谱（图谱是文档入库的派生索引）
        self.last_graph_derived = self._derive_knowledge_graph(documents)

        print("✅ 索引构建完成！")
        return self.index

    def _persist_index(self):
        """持久化索引到磁盘"""
        persist_dir = INDEX_DIR / "llama_index"
        persist_dir.mkdir(exist_ok=True)
        self.index.storage_context.persist(persist_dir=str(persist_dir))
        print(f"💾 索引已保存到: {persist_dir}")

    def _register_file_metadata(
        self,
        documents: List[Document],
        file_paths: Optional[List[str]] = None,
        splitter: Optional["SentenceSplitter"] = None,
    ):
        """将本次入库的文件登记到文件元数据管理器。

        修复历史问题：文档仅写入向量库而从未登记元数据，导致 /file-list、
        /file-info、/file-stats 等命令永远显示“没有文件”。

        登记策略：
          - 优先按文档自带的 ``metadata['file_path']`` 分组统计 document_count；
          - 缺失时回退到传入的 ``file_paths``；
          - chunk_count 用与索引一致的 SentenceSplitter 切分估算；
          - file_hash 基于文件内容计算，便于去重命令识别重复。
        """
        if not self.metadata_manager:
            return

        try:
            # 1) 按来源文件分组：path -> 该文件的 Document 列表
            grouped: dict[str, List[Document]] = {}
            for doc in documents:
                meta = getattr(doc, "metadata", None) or {}
                fp = meta.get("file_path") or meta.get("source")
                if fp:
                    grouped.setdefault(str(fp), []).append(doc)

            # 2) 文档未携带 file_path 时，回退到调用方提供的 file_paths
            if not grouped and file_paths:
                for fp in file_paths:
                    grouped.setdefault(str(fp), [])

            if not grouped:
                return

            # 复用调用方传入的切分器（如 build_index 已创建的），否则按需新建，
            # 避免重复构造 SentenceSplitter。
            if splitter is None:
                splitter = SentenceSplitter(
                    chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP
                )

            for fp, docs in grouped.items():
                document_count = len(docs)
                # 估算 chunk 数：对该文件的所有文档做与索引一致的切分
                try:
                    chunk_count = len(splitter.get_nodes_from_documents(docs)) if docs else 0
                except Exception:
                    chunk_count = document_count

                file_hash = self._compute_file_hash(fp)

                # 已登记则更新计数，否则新增
                existing = self.metadata_manager.get_file_metadata(fp)
                if existing is None:
                    self.metadata_manager.add_file(
                        file_path=fp,
                        persistence_type=FilePersistenceType.PERMANENT,
                        file_hash=file_hash,
                    )
                self.metadata_manager.update_file_metadata(
                    fp,
                    document_count=document_count,
                    chunk_count=chunk_count,
                    file_hash=file_hash,
                )
        except Exception as e:  # noqa: BLE001 - 登记失败不应影响入库主流程
            print(f"⚠️ 文件元数据登记失败: {e}")

    def _derive_knowledge_graph(self, documents: List[Document]) -> bool:
        """入库成功后，将文档派生构建到知识图谱。

        知识图谱是文档入库的派生索引：文档一旦进入向量库，就同步喂给图谱
        构建器，使二者保持一致，用户无需再手动执行 /graph-build。

        失败不影响入库主流程（向量库已成功持久化），仅返回 False 供调用方
        决定是否提示用户手动补建（/graph-build）。
        """
        if not documents:
            return False
        try:
            try:
                from knowledge_graph import get_graph_builder
            except ImportError:  # pragma: no cover - 包内相对导入回退
                from src.knowledge_graph import get_graph_builder  # type: ignore

            builder = get_graph_builder()
            if getattr(builder, "graph", None) is None:
                return False  # networkx 不可用

            ok = False
            for doc in documents:
                meta = getattr(doc, "metadata", None) or {}
                text = getattr(doc, "text", None)
                if text is None:
                    text = getattr(doc, "get_content", lambda: "")() or ""
                if not text or not str(text).strip():
                    continue
                doc_id = (
                    meta.get("file_name")
                    or meta.get("file_path")
                    or meta.get("source")
                    or "manual"
                )
                doc_type = meta.get("doc_type", "text")
                if builder.add_document(str(text), str(doc_id), doc_type):
                    ok = True
            return ok
        except Exception as e:  # noqa: BLE001 - 派生构建失败不应中断入库
            print(f"⚠️ 知识图谱派生构建失败: {e}")
            return False

    @staticmethod
    def _compute_file_hash(file_path: str) -> Optional[str]:
        """计算文件内容的 SHA-256 哈希（文件不存在或读取失败返回 None）。"""
        import hashlib
        try:
            path = Path(file_path)
            if not path.exists() or not path.is_file():
                return None
            h = hashlib.sha256()
            with open(path, "rb") as f:
                for block in iter(lambda: f.read(65536), b""):
                    h.update(block)
            return h.hexdigest()
        except Exception:
            return None

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

        # 存量补全：历史上文档只入向量库而未登记文件元数据，这里从向量库
        # 反向补登记，使 /file-list 等命令对已有知识库也能正确显示文件。
        self._backfill_file_metadata_from_vector_store()

        print("✅ 索引加载完成！")
        return self.index

    def _backfill_file_metadata_from_vector_store(self):
        """从 ChromaDB 反向补全缺失的文件元数据。

        仅登记尚未在元数据管理器中的文件，避免覆盖已有计数；按 file_path 聚合
        chunk 数（向量库中每条记录对应一个 chunk）。
        """
        if not self.metadata_manager:
            return
        try:
            data = self.chroma_collection.get(include=["metadatas"])
        except Exception as e:  # noqa: BLE001
            print(f"⚠️ 读取向量库元数据失败，跳过存量补全: {e}")
            return

        metadatas = (data or {}).get("metadatas") or []
        # 统计每个文件的 chunk 数
        chunk_counts: dict[str, int] = {}
        for meta in metadatas:
            if not meta:
                continue
            fp = meta.get("file_path") or meta.get("source")
            if fp:
                chunk_counts[str(fp)] = chunk_counts.get(str(fp), 0) + 1

        registered = 0
        for fp, chunk_count in chunk_counts.items():
            if self.metadata_manager.get_file_metadata(fp) is not None:
                continue  # 已登记，保留既有计数
            try:
                self.metadata_manager.add_file(
                    file_path=fp,
                    persistence_type=FilePersistenceType.PERMANENT,
                    file_hash=self._compute_file_hash(fp),
                )
                self.metadata_manager.update_file_metadata(fp, chunk_count=chunk_count)
                registered += 1
            except Exception as e:  # noqa: BLE001
                print(f"⚠️ 补登记文件元数据失败 {fp}: {e}")

        if registered:
            print(f"🔄 已为 {registered} 个既有文件补全元数据登记")

    def _setup_query_engine(self):
        """配置查询引擎"""
        if self.index is None:
            return
        self.query_engine = self.index.as_query_engine(
            similarity_top_k=TOP_K,
            response_mode="compact",
            node_postprocessors=[
                SimilarityPostprocessor(similarity_cutoff=SIMILARITY_CUTOFF),
            ],
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

        # 登记文件元数据（供 /file-list 等命令读取）
        self._register_file_metadata(documents, file_paths)

        # 派生构建知识图谱（图谱是文档入库的派生索引）
        self.last_graph_derived = self._derive_knowledge_graph(documents)

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
                    "content": node.node.get_content()[:500],
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
                f"- LLM 模型: {self.llm_model}\n"
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
            "llm_model": self.llm_model,
            "llm_num_ctx": self.llm_num_ctx,
            "llm_think": self.llm_think,
            "embed_model": EMBED_MODEL,
            "chunk_size": CHUNK_SIZE,
            "chunk_overlap": CHUNK_OVERLAP,
            "top_k": TOP_K,
        }

    # ==================== 文件删除 ====================

    def _chunk_metadatas_for_file(self, file_path: str) -> List[dict]:
        """向量库中属于该文件的全部 chunk 元数据（按 ``file_path`` 精确匹配）。"""
        try:
            data = self.chroma_collection.get(where={"file_path": file_path}, include=["metadatas"])
        except Exception as e:  # noqa: BLE001
            print(f"⚠️ 读取向量库元数据失败: {e}")
            return []
        return [m for m in ((data or {}).get("metadatas") or []) if m]

    def _other_files_share_basename(self, file_path: str, basename: str) -> bool:
        """库中是否还有其他 ``file_path`` 不同、但 basename 相同的文件（删除后判定）。"""
        try:
            data = self.chroma_collection.get(where={"file_name": basename}, include=["metadatas"])
        except Exception:  # noqa: BLE001
            return False
        for meta in (data or {}).get("metadatas") or []:
            if meta and str(meta.get("file_path") or "") != file_path:
                return True
        return False

    def remove_file(self, file_path: str) -> dict:
        """从知识库删除一个文件：向量库 chunk（含 docstore）→ 知识图谱 → 文件元数据。

        不删除磁盘上的原文件。图谱以 basename 作为 doc_id，若库中还有另一个同名
        basename 的文件（不同路径），则**不动图谱**，仅在 ``note`` 中提示。

        Returns:
            ``{"file_path", "chunks_deleted", "graph_updated", "graph": {...}, "note"}``
        """
        file_path = str(file_path or "").strip()
        if not file_path:
            raise ValueError("文件路径不能为空")

        metas = self._chunk_metadatas_for_file(file_path)
        registered = (
            self.metadata_manager.get_file_metadata(file_path) is not None
            if self.metadata_manager else False
        )
        if not metas and not registered:
            raise FileNotFoundError(f"文件不在知识库中: {file_path}")

        basename = Path(file_path).name
        for meta in metas:
            if meta.get("file_name"):
                basename = str(meta["file_name"])
                break

        # 1) 删除向量库 chunk（优先经索引删除，同时清理 docstore/index_struct）
        chunks_deleted = len(metas)
        ref_doc_ids = {
            str(m.get("document_id") or m.get("ref_doc_id") or m.get("doc_id") or "")
            for m in metas
        }
        ref_doc_ids.discard("")
        if metas:
            deleted_via_index = False
            if self.index is not None and ref_doc_ids:
                try:
                    for ref_id in ref_doc_ids:
                        self.index.delete_ref_doc(ref_id, delete_from_docstore=True)
                    deleted_via_index = True
                except Exception as e:  # noqa: BLE001
                    print(f"⚠️ 经索引删除失败，改为直接删除向量: {e}")
            if not deleted_via_index:
                self.chroma_collection.delete(where={"file_path": file_path})
            # 兜底：确保按 file_path 残留的 chunk 也被清掉
            try:
                leftover = self._chunk_metadatas_for_file(file_path)
                if leftover:
                    self.chroma_collection.delete(where={"file_path": file_path})
            except Exception:  # noqa: BLE001
                pass
            if self.index is not None:
                try:
                    self._persist_index()
                except Exception as e:  # noqa: BLE001
                    print(f"⚠️ 持久化索引失败: {e}")

        # 2) 知识图谱：仅当库中无其他同名 basename 文件时移除该文档贡献
        graph_result: dict = {}
        graph_updated = False
        note = ""
        if self._other_files_share_basename(file_path, basename):
            note = f"图谱保留：另有同名文件 {basename}"
        else:
            try:
                try:
                    from knowledge_graph import get_graph_builder
                except ImportError:  # pragma: no cover
                    from src.knowledge_graph import get_graph_builder  # type: ignore
                builder = get_graph_builder()
                if getattr(builder, "graph", None) is not None:
                    graph_result = builder.remove_document(basename)
                    graph_updated = any(graph_result.values())
                    if not graph_updated:
                        note = "图谱无该文件的贡献，未变更"
            except Exception as e:  # noqa: BLE001
                note = f"图谱更新失败: {e}"

        # 3) 文件元数据
        if self.metadata_manager:
            try:
                self.metadata_manager.remove_file(file_path)
            except Exception as e:  # noqa: BLE001
                print(f"⚠️ 移除文件元数据失败: {e}")

        print(f"🗑️  已删除文件 {basename}：{chunks_deleted} 个片段" + (f"（{note}）" if note else ""))
        return {
            "file_path": file_path,
            "file_name": basename,
            "chunks_deleted": chunks_deleted,
            "graph_updated": graph_updated,
            "graph": graph_result,
            "note": note,
        }

    def file_delete_preview(self, file_path: str) -> dict:
        """删除前预览：片段数、是否同名冲突、图谱中受影响的节点/边数。"""
        file_path = str(file_path or "").strip()
        metas = self._chunk_metadatas_for_file(file_path) if file_path else []
        basename = Path(file_path).name if file_path else ""
        for meta in metas:
            if meta.get("file_name"):
                basename = str(meta["file_name"])
                break
        shared = self._other_files_share_basename(file_path, basename) if file_path else False
        nodes = edges = 0
        if not shared and basename:
            try:
                try:
                    from knowledge_graph import get_graph_builder
                except ImportError:  # pragma: no cover
                    from src.knowledge_graph import get_graph_builder  # type: ignore
                g = getattr(get_graph_builder(), "graph", None)
                if g is not None:
                    nodes = sum(1 for _, d in g.nodes(data=True) if basename in (d.get("documents") or []))
                    edges = sum(1 for _, _, d in g.edges(data=True) if basename in (d.get("documents") or []))
            except Exception:  # noqa: BLE001
                pass
        registered = bool(
            self.metadata_manager and file_path
            and self.metadata_manager.get_file_metadata(file_path) is not None
        )
        return {
            "file_path": file_path,
            "file_name": basename,
            "exists": bool(metas) or registered,
            "chunk_count": len(metas),
            "graph_shared_basename": shared,
            "graph_nodes": nodes,
            "graph_edges": edges,
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
