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
    RAG_HYBRID,
    RAG_HYBRID_MAX_CHUNKS,
    CODE_CHUNK_MAX_CHARS,
)
from config import resolve_num_ctx as _resolve_num_ctx
from document_loader import load_documents
from code_chunker import (
    build_node_parser,
    status_text as code_chunking_status,
    strip_header as strip_chunk_header,
    summarize_nodes,
)

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
        # F9 P0-1：引擎只做检索（retriever + 相似度过滤），答案一律由
        # rag_pipeline.synthesize_prompt 单次综合生成；``retriever is not None``
        # 即"知识库已初始化"哨兵（``query_engine`` 为兼容别名）。
        self.retriever = None
        self.node_postprocessors: list = []
        # 最近一次入库时知识图谱是否成功派生构建（供 CLI 调整提示文案）
        self.last_graph_derived: bool = False
        # hybrid 召回：惰性构建的 BM25 索引（入库/删除/清空后置 None 失效）
        self._bm25 = None
        self._bm25_disabled_reason: Optional[str] = None
        self.hybrid_enabled: bool = bool(RAG_HYBRID)
        # 统一切分器（build / load / add 三条路径共用；F8 P4 代码感知分块）
        self._node_parser = None
        # 最近一次入库的按文件统计：path -> {chunk_count, symbol_count, chunk_strategy}
        self.last_ingest_stats: dict = {}
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
        provider = self._llm_provider()
        if provider == "openai":
            # F10 P1-2：OpenAI 兼容后端（vLLM / LM Studio / 内网网关）。num_ctx 由后端决定，
            # think 无对应字段；context_window 仍按模型名推导，用于历史 / 片段的 token 预算。
            from llama_index.llms.openai_like import OpenAILike
            from llm_client import describe_backend

            backend = describe_backend()
            base = str(backend.get("base_url", "")).rstrip("/")
            if not base.endswith("/v1"):
                base += "/v1"
            # 思考模式关闭时随请求发送 reasoning_effort（与 OpenAICompatClient 同一开关 LLM_REASONING_EFFORT），
            # 否则思考型模型会把输出预算全部用于 reasoning、综合回答为空
            extra = {}
            effort = self._reasoning_effort()
            if not self.llm_think and effort:
                extra["reasoning_effort"] = effort
            print(f"🤖 加载 LLM 模型: {self.llm_model} (后端 openai @ {base}, context_window={self.llm_num_ctx}, "
                  f"think={self.llm_think})")
            Settings.llm = OpenAILike(
                model=self.llm_model,
                api_base=base,
                api_key=self._openai_api_key() or "not-needed",
                is_chat_model=True,
                is_function_calling_model=False,
                timeout=120.0,
                temperature=0.1,
                context_window=self.llm_num_ctx,
                max_retries=1,
                additional_kwargs=extra,
            )
            return
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

    @staticmethod
    def _llm_provider() -> str:
        try:
            from llm_client import provider_name
            return provider_name()
        except Exception:  # noqa: BLE001
            return "ollama"

    @staticmethod
    def _reasoning_effort() -> str:
        try:
            from llm_client import reasoning_effort_setting
            return reasoning_effort_setting()
        except Exception:  # noqa: BLE001
            return "none"

    @staticmethod
    def _openai_api_key() -> str:
        try:
            import config as _cfg
            return str(getattr(_cfg, "LLM_API_KEY", "") or "")
        except Exception:  # noqa: BLE001
            return ""

    @property
    def query_engine(self):
        """兼容别名：历史上用 ``query_engine is not None`` 判断知识库是否已初始化。

        F9 P0-1 起引擎不再持有 LlamaIndex query engine（避免默认英文模板与双重
        生成），此属性直接映射到 ``retriever``。
        """
        return self.retriever

    @query_engine.setter
    def query_engine(self, value):
        self.retriever = value

    def set_think(self, enabled: bool) -> bool:
        """运行时开关思考模式（供 CLI ``/think`` 与 Web 复选框使用）。

        重建 ``Settings.llm`` 与缓存的检索器（原因同 ``set_model``）。
        """
        self._setup_llm(model=self.llm_model, num_ctx=self.llm_num_ctx, think=bool(enabled))
        self._setup_query_engine()
        return self.llm_think

    def set_model(self, model: str) -> int:
        """运行时切换 LLM（供 CLI ``/model <name>`` 与 Web 下拉使用）。

        重建 ``Settings.llm`` 并重建检索器（检索器/后处理器在 ``_setup_query_engine``
        内构造，随模型切换重建，保证方案与模型无关）。Embedding 与向量库不受影响。
        返回新 num_ctx。
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

    @property
    def node_parser(self):
        """统一切分器（惰性创建）：代码文件按函数/类切分，其余走 SentenceSplitter。"""
        if self._node_parser is None:
            self._node_parser = build_node_parser()
        return self._node_parser

    def _split_documents(self, documents: List[Document], progress_callback=None):
        """用统一切分器把文档切成节点，并按来源文件统计。

        返回 ``(nodes, per_file)``；切分异常时返回 ``(None, {})``，由调用方回退到
        LlamaIndex 内部切分路径。``per_file``：``path -> {chunk_count, symbol_count, chunk_strategy}``。
        """
        parser = self.node_parser
        nodes: List = []
        per_file: dict = {}
        total = len(documents)
        try:
            # 按来源文件分组，便于逐文件发进度与统计
            grouped: "dict[str, List[Document]]" = {}
            for doc in documents:
                meta = getattr(doc, "metadata", None) or {}
                fp = str(meta.get("file_path") or meta.get("source") or meta.get("file_name") or getattr(doc, "doc_id", "") or id(doc))
                grouped.setdefault(fp, []).append(doc)
            for i, (fp, docs) in enumerate(grouped.items(), 1):
                if progress_callback:
                    progress_callback({
                        "stage": "chunk",
                        "message": f"切分 {Path(fp).name} ({i}/{len(grouped)})",
                        "current": i,
                        "total": len(grouped),
                    })
                file_nodes = parser.get_nodes_from_documents(docs)
                nodes.extend(file_nodes)
                per_file[fp] = summarize_nodes(file_nodes)
            fallback = getattr(parser, "fallback_reasons", None) or {}
            for fp, reason in fallback.items():
                if fp in per_file and per_file[fp]["chunk_strategy"] == "text":
                    per_file[fp]["chunk_strategy"] = f"text(fallback:{reason})"
        except Exception as e:  # noqa: BLE001 - 切分失败回退 LlamaIndex 内部路径
            logging.getLogger(__name__).debug("统一切分失败，回退内部切分: %s", e)
            return None, {}
        self.last_ingest_stats = per_file
        if progress_callback and total:
            progress_callback({"stage": "chunk", "message": f"切分完成：{len(nodes)} 个片段", "current": total, "total": total})
        return nodes, per_file

    def build_index(
        self,
        documents: List[Document],
        persist: bool = True,
        file_paths: List[str] = None,
        progress_callback=None,
    ) -> VectorStoreIndex:
        """构建向量索引"""
        print(f"\n🏗️  构建索引中... (文档数: {len(documents)})")

        node_parser = self.node_parser
        Settings.node_parser = node_parser

        storage_context = StorageContext.from_defaults(
            vector_store=self.vector_store
        )

        # 先切分再建索引：切分结果同时用于文件元数据统计（chunk_count / 符号数 / 策略），
        # 避免此前"索引内部切一次、登记元数据再切一次"导致的计数不一致。
        nodes, per_file = self._split_documents(documents, progress_callback)
        if nodes is None:
            self.index = VectorStoreIndex.from_documents(
                documents,
                storage_context=storage_context,
                show_progress=True,
                transformations=[node_parser],
            )
        else:
            if progress_callback:
                progress_callback({"stage": "embed", "message": f"生成 {len(nodes)} 个片段的向量...", "current": 0, "total": len(nodes)})
            self.index = VectorStoreIndex(
                nodes=nodes,
                storage_context=storage_context,
                show_progress=True,
                transformations=[node_parser],
            )
            for doc in documents:
                try:
                    self.index.docstore.set_document_hash(doc.id_, doc.hash)
                except Exception:  # noqa: BLE001 - 仅影响去重哈希
                    pass
            if progress_callback:
                progress_callback({"stage": "embed", "message": "向量生成完成", "current": len(nodes), "total": len(nodes)})

        if persist:
            self._persist_index()

        self._setup_query_engine()
        self.invalidate_bm25()

        # 登记文件元数据（供 /file-list 等命令读取），复用上面的切分统计。
        self._register_file_metadata(documents, file_paths, per_file=per_file)

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
        per_file: Optional[dict] = None,
    ):
        """将本次入库的文件登记到文件元数据管理器。

        修复历史问题：文档仅写入向量库而从未登记元数据，导致 /file-list、
        /file-info、/file-stats 等命令永远显示“没有文件”。

        登记策略：
          - 优先按文档自带的 ``metadata['file_path']`` 分组统计 document_count；
          - 缺失时回退到传入的 ``file_paths``；
          - chunk_count / symbol_count / chunk_strategy 优先取 ``per_file``（本次入库
            实际切分结果），缺失时用统一切分器重新切一次估算；
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

            per_file = per_file or {}
            for fp, docs in grouped.items():
                document_count = len(docs)
                stats = per_file.get(fp)
                if stats is None:
                    # 未提供实际切分统计时，用统一切分器重切一次估算（与索引一致）
                    try:
                        stats = summarize_nodes(self.node_parser.get_nodes_from_documents(docs)) if docs else {}
                    except Exception:
                        stats = {}
                chunk_count = int(stats.get("chunk_count", document_count) or 0) if stats else document_count
                symbol_count = int(stats.get("symbol_count", 0) or 0) if stats else 0
                chunk_strategy = str(stats.get("chunk_strategy") or "text") if stats else "text"

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
                    symbol_count=symbol_count,
                    chunk_strategy=chunk_strategy,
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
        # 统一切分器：此前加载路径未设置 node_parser，"加载已有索引后追加文档"会落到
        # LlamaIndex 默认 SentenceSplitter(1024/200) 而非 .env 的 CHUNK_SIZE/CHUNK_OVERLAP。
        Settings.node_parser = self.node_parser
        try:
            self.index._transformations = [self.node_parser]
        except Exception:  # noqa: BLE001 - Mock/旧版本索引对象无此属性时忽略
            pass
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
        # 统计每个文件的 chunk 数、符号数与分块策略（代码块的 node metadata 带 symbol/chunk_strategy）
        chunk_counts: dict[str, int] = {}
        symbols: dict[str, set] = {}
        strategies: dict[str, str] = {}
        for meta in metadatas:
            if not meta:
                continue
            fp = meta.get("file_path") or meta.get("source")
            if fp:
                fp = str(fp)
                chunk_counts[fp] = chunk_counts.get(fp, 0) + 1
                if meta.get("symbol"):
                    symbols.setdefault(fp, set()).add(meta["symbol"])
                strat = str(meta.get("chunk_strategy") or "")
                if strat.startswith("code") or fp not in strategies:
                    strategies[fp] = strat or "text"

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
                self.metadata_manager.update_file_metadata(
                    fp,
                    chunk_count=chunk_count,
                    symbol_count=len(symbols.get(fp, ())),
                    chunk_strategy=strategies.get(fp, "text"),
                )
                registered += 1
            except Exception as e:  # noqa: BLE001
                print(f"⚠️ 补登记文件元数据失败 {fp}: {e}")

        if registered:
            print(f"🔄 已为 {registered} 个既有文件补全元数据登记")

    def _setup_query_engine(self):
        """配置检索器（F9 P0-1：检索-only，不再构造会生成答案的 query engine）。

        此前用 LlamaIndex 的 query engine（``response_mode="compact"``），它会用 LlamaIndex
        默认英文 QA 模板先生成一遍答案（不含任何忠实性条款、无编号引用），编排层
        再综合一遍——既浪费一次 LLM 调用，又在"快路径"下把这份无约束答案直接
        返给用户。现只保留 ``as_retriever`` + 相似度阈值后处理，答案统一由
        ``rag_pipeline.synthesize_prompt`` 单次生成。方法名保留以兼容调用方。
        """
        if self.index is None:
            return
        self.retriever = self.index.as_retriever(similarity_top_k=TOP_K)
        self.node_postprocessors = [SimilarityPostprocessor(similarity_cutoff=SIMILARITY_CUTOFF)]

    # 追加入库时每批嵌入的节点数（用于进度回调粒度）
    _INSERT_BATCH = 16

    def add_documents(self, documents: List[Document], file_paths: List[str] = None, progress_callback=None):
        """向现有索引添加新文档。

        ``progress_callback`` 接收字典：``stage`` 为 ``chunk``（按文件切分）或 ``embed``
        （按节点批次生成向量），带 ``message`` / ``current`` / ``total``；CLI 与 Web 共用。
        """
        if self.index is None:
            print("⚠️  索引不存在，将创建新索引")
            return self.build_index(documents, file_paths=file_paths, progress_callback=progress_callback)

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
        
        nodes, per_file = self._split_documents(documents, progress_callback)
        if nodes is None:
            # 切分异常：回退 LlamaIndex 内部逐文档插入（内部使用同一 node_parser）
            for doc in documents:
                self.index.insert(doc)
        else:
            total = len(nodes)
            for start in range(0, total, self._INSERT_BATCH):
                batch = nodes[start:start + self._INSERT_BATCH]
                if progress_callback:
                    progress_callback({
                        "stage": "embed",
                        "message": f"生成向量 {min(start + len(batch), total)}/{total}",
                        "current": min(start + len(batch), total),
                        "total": total,
                    })
                self.index.insert_nodes(batch)
            for doc in documents:
                try:
                    self.index.docstore.set_document_hash(doc.id_, doc.hash)
                except Exception:  # noqa: BLE001
                    pass

        self._persist_index()
        self.invalidate_bm25()
        print("✅ 文档添加完成！")

        # 登记文件元数据（供 /file-list 等命令读取），复用本次实际切分统计
        self._register_file_metadata(documents, file_paths, per_file=per_file)

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
        """查询知识库并返回答案文本（走共享编排层的忠实性 prompt，只用知识库）。"""
        if self.retriever is None:
            raise RuntimeError("索引未初始化，请先构建或加载索引")
        print(f"\n🔍 查询: {question}")
        from rag_pipeline import answer_question
        result = answer_question(self, question, enable_web_search=False, show_progress=False, kb_only=True)
        return str(result.get("answer") or "")

    def retrieve_nodes(self, question: str) -> list:
        """向量检索并应用相似度阈值后处理，返回 ``NodeWithScore`` 列表（不生成答案）。"""
        nodes = list(self.retriever.retrieve(question) or [])
        for pp in self.node_postprocessors or []:
            try:
                nodes = list(pp.postprocess_nodes(nodes, query_str=question) or [])
            except Exception as e:  # noqa: BLE001 - 后处理失败时保留原始召回
                logging.getLogger(__name__).debug(f"node postprocessor 失败，保留原始召回: {e}")
        return nodes

    # ==================== hybrid 召回：BM25 + RRF ====================

    # RRF 常数（Cormack et al. 推荐 60）
    RRF_K = 60
    # 片段去重/匹配用的内容前缀长度（与 sources 中 content[:500] 一致）
    _CONTENT_KEY_CHARS = 500

    @staticmethod
    def _bm25_tokenize(text: str) -> List[str]:
        """BM25 轻量分词：英文/数字按词（小写），中文按单字 + 相邻二字组。

        标识符额外拆分：``snake_case`` / ``camelCase`` / ``PascalCase`` 在保留原词的同时
        追加其子词（``_ensure_bm25`` → ``ensure``、``bm25``；``getUserName`` → ``get``、
        ``user``、``name``），使代码问答中"问 ensure bm25 命中 _ensure_bm25"成为可能。
        """
        import re
        if not text:
            return []
        words = re.findall(r"[a-zA-Z0-9_]+", text)
        tokens: List[str] = []
        for w in words:
            tokens.append(w.lower())
            parts = [p for p in w.split("_") if p]
            sub: List[str] = []
            for p in parts:
                sub.extend(re.findall(r"[A-Z]+[0-9]*(?![a-z])|[A-Z]?[a-z]+[0-9]*|[0-9]+", p))
            if len(sub) > 1 or (sub and sub[0] != w):
                tokens.extend(s.lower() for s in sub if s.lower() != w.lower())
        cjk = [ch for ch in text if "\u4e00" <= ch <= "\u9fff"]
        tokens.extend(cjk)
        tokens.extend(a + b for a, b in zip(cjk, cjk[1:]))
        return tokens

    @classmethod
    def _make_source(cls, text: str, meta: dict, score=None) -> dict:
        """由片段文本与 node metadata 构造 sources 项（dense 与 BM25 两路共用，保证去重键一致）。

        代码块的首行注释头（``# file · symbol · L1-L2``）在此剥离，位置信息改由
        ``symbol / start_line / end_line / language / chunk_strategy`` 字段透出。
        """
        meta = meta or {}
        content = strip_chunk_header(str(text or ""))[:cls._CONTENT_KEY_CHARS]
        src = {
            "content": content,
            "score": score,
            "file": meta.get("file_name", "未知"),
            "path": meta.get("file_path", ""),
        }
        strategy = str(meta.get("chunk_strategy") or "")
        if strategy:
            src["chunk_strategy"] = strategy
        if meta.get("symbol"):
            src["symbol"] = str(meta["symbol"])
        if meta.get("start_line") is not None:
            try:
                src["start_line"] = int(meta["start_line"])
                src["end_line"] = int(meta.get("end_line") or meta["start_line"])
            except (TypeError, ValueError):
                pass
        if meta.get("language"):
            src["language"] = str(meta["language"])
        if meta.get("part"):
            src["part"] = str(meta["part"])
        return src

    def invalidate_bm25(self) -> None:
        """入库/删除/清空后使 BM25 索引失效（下次查询按需重建）。"""
        self._bm25 = None
        self._bm25_disabled_reason = None

    def _ensure_bm25(self, progress_callback=None) -> bool:
        """惰性构建 BM25 索引。返回是否可用（依赖缺失/规模超限/读取失败均为 False）。"""
        if self._bm25 is not None:
            return True
        if self._bm25_disabled_reason:
            return False
        try:
            from rank_bm25 import BM25Okapi  # type: ignore
        except ImportError:
            self._bm25_disabled_reason = "rank_bm25 未安装"
            return False  # 静默回退 dense

        try:
            count = int(self.chroma_collection.count())
        except Exception:  # noqa: BLE001 - 无法统计时不做规模限制
            count = -1
        if count > RAG_HYBRID_MAX_CHUNKS:
            self._bm25_disabled_reason = f"文档块数 {count} 超过 {RAG_HYBRID_MAX_CHUNKS}"
            msg = f"⚠️ 文档块数 {count} > {RAG_HYBRID_MAX_CHUNKS}，已自动关闭 hybrid 召回（仅向量检索）"
            print(msg)
            if progress_callback:
                progress_callback({"phase": "hybrid_off", "message": msg})
            return False

        try:
            data = self.chroma_collection.get(include=["documents", "metadatas"]) or {}
            docs = data.get("documents") or []
            metas = data.get("metadatas") or []
            if not isinstance(docs, list) or not docs:
                self._bm25_disabled_reason = "向量库为空"
                return False
            entries = []
            corpus = []
            for i, text in enumerate(docs):
                text = str(text or "")
                meta = metas[i] if i < len(metas) and isinstance(metas[i], dict) else {}
                entry = self._make_source(text, meta)
                entry.pop("score", None)
                entries.append(entry)
                corpus.append(self._bm25_tokenize(text))
            self._bm25 = {"index": BM25Okapi(corpus), "entries": entries}
            return True
        except Exception as e:  # noqa: BLE001 - 构建失败静默回退 dense
            self._bm25_disabled_reason = f"BM25 构建失败: {e}"
            logging.getLogger(__name__).debug(self._bm25_disabled_reason)
            return False

    def _bm25_search(self, question: str, top_k: int) -> List[dict]:
        """BM25 检索前 top_k 条（分数 >0），返回 ``[{content, file, path, bm25_score}]``。"""
        if not self._bm25:
            return []
        tokens = self._bm25_tokenize(question)
        if not tokens:
            return []
        scores = self._bm25["index"].get_scores(tokens)
        ranked = sorted(range(len(scores)), key=lambda i: float(scores[i]), reverse=True)
        out = []
        for i in ranked[:top_k]:
            if float(scores[i]) <= 0:
                break
            item = dict(self._bm25["entries"][i])
            item["bm25_score"] = float(scores[i])
            out.append(item)
        return out

    @classmethod
    def rrf_fuse(cls, dense: List[dict], sparse: List[dict], top_k: int, k: int = None) -> List[dict]:
        """RRF 融合 dense 与 BM25 两路排序，取前 top_k。

        - 以 ``(path|file, start_line 或 content[:500])`` 作为同一片段的键（代码块用起始行，
          避免多个相似函数头的前 500 字相同而被误判为同一片段）；
        - 两路都命中的项保留 dense 分数、``retriever="hybrid"``；
        - 仅 dense 命中：保留原分数、``retriever="dense"``；
        - 仅 BM25 命中：``score`` 用 RRF 归一值（相对"两路均第 1 名"的理论最大值，
          故上限 0.5，能过 0.45 粗筛但不会触发 0.6 的"跳过 rerank"高可信线），
          ``retriever="bm25"``；
        - 每项附 ``rrf`` 原始融合分，按其降序排列。
        """
        k = cls.RRF_K if k is None else k

        def key_of(src: dict):
            where = src.get("path") or src.get("file") or ""
            if src.get("start_line") is not None:
                return (where, f"L{src.get('start_line')}")
            return (where, (src.get("content") or "")[:cls._CONTENT_KEY_CHARS])

        fused: dict = {}
        for rank, src in enumerate(dense, 1):
            key = key_of(src)
            item = fused.setdefault(key, {"src": dict(src), "rrf": 0.0, "in_dense": False, "in_sparse": False})
            item["rrf"] += 1.0 / (k + rank)
            item["in_dense"] = True
        for rank, src in enumerate(sparse, 1):
            key = key_of(src)
            item = fused.setdefault(key, {"src": dict(src), "rrf": 0.0, "in_dense": False, "in_sparse": False})
            item["rrf"] += 1.0 / (k + rank)
            item["in_sparse"] = True
            if item["in_dense"]:
                item["src"].setdefault("bm25_score", src.get("bm25_score"))

        max_possible = 2.0 / (k + 1)
        ordered = sorted(
            fused.values(),
            key=lambda it: (it["rrf"], float(it["src"].get("score") or 0)),
            reverse=True,
        )
        out = []
        for it in ordered[:top_k]:
            src = it["src"]
            src["rrf"] = round(it["rrf"], 6)
            if it["in_dense"] and it["in_sparse"]:
                src["retriever"] = "hybrid"
            elif it["in_dense"]:
                src["retriever"] = "dense"
            else:
                src["retriever"] = "bm25"
                src["score"] = round(it["rrf"] / max_possible, 4)
            out.append(src)
        return out

    def query_with_sources(self, question: str, progress_callback=None, hybrid: Optional[bool] = None) -> dict:
        """
        查询并返回来源信息
        
        Args:
            question: 查询问题
            progress_callback: 进度回调函数，接收字典参数：
                - phase: 当前阶段 (embedding|retrieving|scoring|hybrid|hybrid_off|generating)
                - message: 进度消息
                - current: 当前步骤（可选）
                - total: 总步骤（可选）
            hybrid: 是否启用 dense + BM25 hybrid 召回（RRF 融合）。None 时按
                ``RAG_HYBRID``（默认开启）；``rank_bm25`` 未安装或块数超限时自动回退 dense。

        Returns:
            ``{"answer": "", "sources": [...], "hybrid": bool}``；hybrid 生效时 sources
            各项带 ``retriever``（dense/bm25/hybrid）与 ``rrf``。F9 P0-1 起本方法
            **只检索不生成**（``answer`` 恒为空串，键保留以兼容），答案由
            ``rag_pipeline`` 用忠实性 prompt 单次综合。
        """
        if self.retriever is None:
            raise RuntimeError("索引未初始化")
        
        # 调用进度回调：开始生成查询向量
        if progress_callback:
            progress_callback({"phase": "embedding", "message": "正在生成查询向量..."})
        
        nodes = self.retrieve_nodes(question)
        
        # 调用进度回调：检索完成
        source_count = len(nodes)
        if progress_callback:
            progress_callback({"phase": "retrieving", "message": f"检索到 {source_count} 个相关文档"})

        sources = []
        for i, node in enumerate(nodes):
            # 调用进度回调：评分文档
            if progress_callback:
                progress_callback({
                    "phase": "scoring",
                    "message": f"评分文档 {i+1}/{source_count}",
                    "current": i+1,
                    "total": source_count
                })
            
            sources.append(self._make_source(
                node.node.get_content(),
                node.node.metadata,
                score=float(node.score) if getattr(node, "score", None) is not None else None,
            ))

        # hybrid：BM25 关键词召回与 dense 结果 RRF 融合（失败/不可用静默回退 dense）
        use_hybrid = self.hybrid_enabled if hybrid is None else bool(hybrid)
        hybrid_applied = False
        if use_hybrid:
            try:
                if self._ensure_bm25(progress_callback):
                    sparse = self._bm25_search(question, TOP_K)
                    if sparse:
                        sources = self.rrf_fuse(sources, sparse, TOP_K)
                        hybrid_applied = True
                        added = sum(1 for s in sources if s.get("retriever") == "bm25")
                        if progress_callback:
                            progress_callback({
                                "phase": "hybrid",
                                "message": f"hybrid 召回：BM25 补充 {added} 个关键词命中片段，RRF 融合后 {len(sources)} 个",
                                "added": added,
                            })
            except Exception as e:  # noqa: BLE001
                logging.getLogger(__name__).debug(f"hybrid 召回失败，回退 dense: {e}")

        return {
            "answer": "",
            "sources": sources,
            "hybrid": hybrid_applied,
        }

    # ==================== Agent 工具接口 ====================

    def query_tool(self, question: str) -> str:
        """
        供 Agent 调用的知识库查询工具（委托共享编排层 ``answer_question(kb_only=True)``，
        与 ``agent_tools.query_knowledge_base`` 同一条忠实性管道）。
        返回简洁的字符串，包含回答和来源。
        """
        if self.retriever is None:
            return "[错误] 知识库索引未初始化，请先添加文档构建索引。"
        try:
            from rag_pipeline import answer_question
            result = answer_question(self, question, enable_web_search=False, show_progress=False, kb_only=True)
            answer = result.get("answer") or ""
            sources = result.get("kb_sources") or []
            sources_info = ""
            if sources:
                sources_info = "\n\n[参考来源]\n"
                for i, src in enumerate(sources[:3], 1):
                    score = f"(相似度: {src['score']:.3f})" if src.get('score') else ""
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
                f"- 代码分块: {code_chunking_status()}\n"
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
            "code_chunking": code_chunking_status(),
            "code_chunk_max_chars": CODE_CHUNK_MAX_CHARS,
            "top_k": TOP_K,
            # F9 P2-1：LLM 自校验开关（运行时读取 config，随环境变量生效）
            "self_check": self._self_check_enabled(),
        }

    @staticmethod
    def _self_check_enabled() -> bool:
        try:
            import config as _cfg
            return bool(getattr(_cfg, "RAG_SELF_CHECK", False))
        except Exception:  # noqa: BLE001
            return False

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
        self.invalidate_bm25()
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
        self.retriever = None
        self.node_postprocessors = []
        self.invalidate_bm25()
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
