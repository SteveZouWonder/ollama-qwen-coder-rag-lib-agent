#!/usr/bin/env python3
"""
知识库快照系统
- 自动在每次添加文档时创建快照
- 保存知识库状态和元数据
- 支持快速恢复和多版本管理
"""
import os
import json
import shutil
import logging
import warnings
from pathlib import Path
from typing import List, Dict, Optional
from dataclasses import dataclass, asdict
from datetime import datetime
import hashlib

# 禁用ChromaDB遥测
os.environ['ANONYMIZED_TELEMETRY'] = 'False'
os.environ['CHROMA_TELEMETRY'] = 'False'
logging.getLogger("chromadb").setLevel(logging.ERROR)
warnings.filterwarnings("ignore", message="urllib3 v2 only supports OpenSSL 1.1.1+")

import chromadb


# ==================== 数据模型 ====================

@dataclass
@dataclass
class DocumentSnapshot:
    """文档快照信息"""
    file_path: str
    file_name: str
    file_type: str
    chunk_count: int
    file_hash: str  # 文件内容哈希
    added_timestamp: str


@dataclass
class KnowledgeSnapshot:
    """知识库快照"""
    snapshot_id: str
    timestamp: str
    version: str
    documents: List[DocumentSnapshot]
    storage_paths: Dict[str, str]
    model_config: Dict[str, str]
    total_chunks: int
    metadata: Dict


# ==================== 快照管理器 ====================

class KnowledgeSnapshotManager:
    """知识库快照管理器"""
    
    def __init__(self, 
                 index_dir: str = "./index_storage",
                 snapshot_dir: str = "./.devin/knowledge/snapshots",
                 max_snapshots: int = 10):
        self.index_dir = Path(index_dir)
        self.snapshot_dir = Path(snapshot_dir)
        self.max_snapshots = max_snapshots
        
        self.chroma_path = str(self.index_dir / "chroma_db")
        self.llama_index_path = str(self.index_dir / "llama_index")
        
        self.snapshot_dir.mkdir(parents=True, exist_ok=True)
        
        self.logger = logging.getLogger(__name__)
        logging.basicConfig(level=logging.INFO)
    
    def create_snapshot(self, trigger: str = "manual") -> KnowledgeSnapshot:
        """创建知识库快照"""
        self.logger.info(f"创建知识库快照 (触发方式: {trigger})...")
        
        # 连接到ChromaDB
        chroma_client = chromadb.PersistentClient(path=self.chroma_path)
        collection = chroma_client.get_or_create_collection(name="rag_knowledge_base")
        
        # 获取所有文档信息
        all_data = collection.get(include=['metadatas', 'documents'])
        
        # 提取唯一文档
        unique_docs = {}
        for metadata, doc_content in zip(all_data['metadatas'], all_data['documents']):
            file_path = metadata.get('file_path')
            if file_path and file_path not in unique_docs:
                # 计算文件哈希
                file_hash = self._calculate_hash(doc_content)
                
                unique_docs[file_path] = DocumentSnapshot(
                    file_path=file_path,
                    file_name=metadata.get('file_name', Path(file_path).name),
                    file_type=metadata.get('file_type', ''),
                    chunk_count=0,  # 稍后计算
                    file_hash=file_hash,
                    added_timestamp=datetime.now().isoformat()
                )
        
        # 计算每个文档的chunk数量
        for metadata in all_data['metadatas']:
            file_path = metadata.get('file_path')
            if file_path in unique_docs:
                unique_docs[file_path].chunk_count += 1
        
        documents = list(unique_docs.values())
        total_chunks = collection.count()
        
        # 生成快照ID
        snapshot_id = self._generate_snapshot_id()
        timestamp = datetime.now().isoformat()
        
        # 获取模型配置
        model_config = self._get_model_config()
        
        # 创建快照对象
        snapshot = KnowledgeSnapshot(
            snapshot_id=snapshot_id,
            timestamp=timestamp,
            version="1.0",
            documents=documents,
            storage_paths={
                "chroma_db": self.chroma_path,
                "llama_index": self.llama_index_path
            },
            model_config=model_config,
            total_chunks=total_chunks,
            metadata={
                "trigger": trigger,
                "created_by": "system",
                "document_count": len(documents)
            }
        )
        
        # 保存快照
        self._save_snapshot(snapshot)
        
        # 清理旧快照
        self._cleanup_old_snapshots()
        
        self.logger.info(f"快照创建完成: {snapshot_id}")
        return snapshot
    
    def load_snapshot(self, snapshot_id: str) -> Optional[KnowledgeSnapshot]:
        """加载快照"""
        snapshot_file = self.snapshot_dir / f"{snapshot_id}.json"
        if not snapshot_file.exists():
            self.logger.error(f"快照不存在: {snapshot_id}")
            return None
        
        with open(snapshot_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # 重建DocumentSnapshot对象
        documents = [DocumentSnapshot(**doc) for doc in data['documents']]
        
        snapshot = KnowledgeSnapshot(
            snapshot_id=data['snapshot_id'],
            timestamp=data['timestamp'],
            version=data['version'],
            documents=documents,
            storage_paths=data['storage_paths'],
            model_config=data['model_config'],
            total_chunks=data['total_chunks'],
            metadata=data['metadata']
        )
        
        return snapshot
    
    def list_snapshots(self) -> List[Dict]:
        """列出所有快照"""
        snapshots = []
        
        for snapshot_file in sorted(self.snapshot_dir.glob("*.json"), reverse=True):
            try:
                with open(snapshot_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                snapshots.append({
                    "snapshot_id": data['snapshot_id'],
                    "timestamp": data['timestamp'],
                    "document_count": len(data['documents']),
                    "total_chunks": data['total_chunks'],
                    "trigger": data['metadata'].get('trigger', 'unknown'),
                    "file": str(snapshot_file)
                })
            except (json.JSONDecodeError, KeyError) as e:
                self.logger.warning(f"跳过损坏的快照文件 {snapshot_file.name}: {e}")
                # 可选：删除损坏的文件
                # snapshot_file.unlink()
                continue
        
        return snapshots
    
    def restore_snapshot(self, snapshot_id: str) -> bool:
        """恢复快照（主要用于验证，实际恢复需要重新处理文档）"""
        snapshot = self.load_snapshot(snapshot_id)
        if not snapshot:
            return False
        
        self.logger.info(f"恢复快照: {snapshot_id}")
        self.logger.info(f"文档数量: {len(snapshot.documents)}")
        self.logger.info(f"总chunk数: {snapshot.total_chunks}")
        
        # 注意：实际的向量数据库恢复需要重新处理原始文档
        # 这里主要是验证快照的完整性
        for doc in snapshot.documents:
            if Path(doc.file_path).exists():
                self.logger.info(f"  ✓ {doc.file_name} 存在")
            else:
                self.logger.warning(f"  ✗ {doc.file_name} 不存在")
        
        return True
    
    def delete_snapshot(self, snapshot_id: str) -> bool:
        """删除快照"""
        snapshot_file = self.snapshot_dir / f"{snapshot_id}.json"
        if not snapshot_file.exists():
            self.logger.error(f"快照不存在: {snapshot_id}")
            return False
        
        snapshot_file.unlink()
        self.logger.info(f"快照已删除: {snapshot_id}")
        return True
    
    def get_latest_snapshot(self) -> Optional[KnowledgeSnapshot]:
        """获取最新的快照"""
        snapshots = self.list_snapshots()
        if not snapshots:
            return None
        
        latest_snapshot_id = snapshots[0]['snapshot_id']
        return self.load_snapshot(latest_snapshot_id)
    
    def _generate_snapshot_id(self) -> str:
        """生成快照ID"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        random_hash = hashlib.md5(str(datetime.now().timestamp()).encode(), usedforsecurity=False).hexdigest()[:8]
        return f"{timestamp}_{random_hash}"
    
    def _calculate_hash(self, content: str) -> str:
        """计算内容哈希"""
        return hashlib.md5(content.encode('utf-8'), usedforsecurity=False).hexdigest()
    
    def _get_model_config(self) -> Dict[str, str]:
        """获取模型配置"""
        try:
            from config import LLM_MODEL, EMBED_MODEL, OLLAMA_BASE_URL
            return {
                "llm_model": LLM_MODEL,
                "embed_model": EMBED_MODEL,
                "ollama_base_url": OLLAMA_BASE_URL
            }
        except ImportError:
            return {
                "llm_model": "unknown",
                "embed_model": "unknown",
                "ollama_base_url": "unknown"
            }
    
    def _save_snapshot(self, snapshot: KnowledgeSnapshot):
        """保存快照到文件"""
        snapshot_file = self.snapshot_dir / f"{snapshot.snapshot_id}.json"
        
        # 转换为可序列化的格式
        data = {
            "snapshot_id": snapshot.snapshot_id,
            "timestamp": snapshot.timestamp,
            "version": snapshot.version,
            "documents": [asdict(doc) for doc in snapshot.documents],
            "storage_paths": snapshot.storage_paths,
            "model_config": snapshot.model_config,
            "total_chunks": snapshot.total_chunks,
            "metadata": snapshot.metadata
        }
        
        with open(snapshot_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    
    def _cleanup_old_snapshots(self):
        """清理旧快照，保留最近的max_snapshots个"""
        snapshots = sorted(self.snapshot_dir.glob("*.json"))
        
        if len(snapshots) > self.max_snapshots:
            for old_snapshot in snapshots[:-self.max_snapshots]:
                old_snapshot.unlink()
                self.logger.info(f"清理旧快照: {old_snapshot.name}")


# ==================== 自动快照触发器 ====================

class AutoSnapshotTrigger:
    """自动快照触发器"""
    
    def __init__(self, snapshot_manager: KnowledgeSnapshotManager):
        self.snapshot_manager = snapshot_manager
        self.logger = logging.getLogger(__name__)
    
    def on_document_added(self, file_path: str, chunk_count: int):
        """当文档添加时触发"""
        self.logger.info(f"检测到文档添加: {file_path} ({chunk_count} chunks)")
        try:
            snapshot = self.snapshot_manager.create_snapshot(trigger="document_added")
            self.logger.info(f"自动快照已创建: {snapshot.snapshot_id}")
            return snapshot
        except Exception as e:
            self.logger.error(f"自动快照创建失败: {e}")
            return None
    
    def on_documents_batch_added(self, file_paths: List[str]):
        """当批量添加文档时触发"""
        self.logger.info(f"检测到批量文档添加: {len(file_paths)} 个文件")
        try:
            snapshot = self.snapshot_manager.create_snapshot(trigger="batch_added")
            self.logger.info(f"自动快照已创建: {snapshot.snapshot_id}")
            return snapshot
        except Exception as e:
            self.logger.error(f"自动快照创建失败: {e}")
            return None


# ==================== 恢复助手 ====================

class RestoreHelper:
    """恢复助手"""
    
    def __init__(self, snapshot_manager: KnowledgeSnapshotManager):
        self.snapshot_manager = snapshot_manager
        self.logger = logging.getLogger(__name__)
    
    def generate_restore_script(self, snapshot_id: str, output_file: str = "restore_knowledge.py") -> str:
        """生成恢复脚本"""
        snapshot = self.snapshot_manager.load_snapshot(snapshot_id)
        if not snapshot:
            raise ValueError(f"快照不存在: {snapshot_id}")
        
        script_content = f'''#!/usr/bin/env python3
"""
知识库恢复脚本
快照ID: {snapshot.snapshot_id}
时间: {snapshot.timestamp}
文档数量: {len(snapshot.documents)}
"""
import sys
import os
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))

from document_loader import load_documents
from rag_engine import RAGEngine, build_knowledge_base

def restore_knowledge():
    """恢复知识库"""
    print("开始恢复知识库...")
    
    # 文档列表
    documents_to_add = [
'''
        
        for doc in snapshot.documents:
            script_content += f'        "{doc.file_path}",\n'
        
        script_content += f'''    ]
    
    # 检查文件是否存在
    missing_files = []
    for file_path in documents_to_add:
        if not Path(file_path).exists():
            missing_files.append(file_path)
    
    if missing_files:
        print("以下文件不存在，无法恢复:")
        for f in missing_files:
            print(f"  - {{f}}")
        return False
    
    # 加载文档
    print(f"加载 {{len(documents_to_add)}} 个文档...")
    documents = []
    for file_path in documents_to_add:
        try:
            docs = load_documents(file_path)
            documents.extend(docs)
            print(f"  ✓ {{Path(file_path).name}}")
        except Exception as e:
            print(f"  ✗ {{Path(file_path).name}}: {{e}}")
    
    if not documents:
        print("没有成功加载任何文档")
        return False
    
    # 构建知识库
    print("构建知识库...")
    engine = RAGEngine()
    engine.build_index(documents)
    
    print("知识库恢复完成！")
    print(f"总chunk数: {{len(documents)}}")
    return True

if __name__ == "__main__":
    restore_knowledge()
'''
        
        output_path = Path(output_file)
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(script_content)
        
        self.logger.info(f"恢复脚本已生成: {output_file}")
        return str(output_file)


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description='知识库快照管理工具')
    parser.add_argument('--index-dir', default='./index_storage', help='索引目录')
    parser.add_argument('--snapshot-dir', default='./.devin/knowledge/snapshots', help='快照目录')
    parser.add_argument('--max-snapshots', type=int, default=10, help='最大快照数量')
    parser.add_argument('--action', choices=['create', 'list', 'restore', 'delete', 'latest'], 
                       default='list', help='操作类型')
    parser.add_argument('--snapshot-id', help='快照ID')
    parser.add_argument('--generate-script', help='生成恢复脚本到指定文件')
    
    args = parser.parse_args()
    
    manager = KnowledgeSnapshotManager(
        index_dir=args.index_dir,
        snapshot_dir=args.snapshot_dir,
        max_snapshots=args.max_snapshots
    )
    
    if args.action == 'create':
        snapshot = manager.create_snapshot()
        print(f"快照创建完成: {snapshot.snapshot_id}")
    
    elif args.action == 'list':
        snapshots = manager.list_snapshots()
        print(f"\\n共有 {len(snapshots)} 个快照:\\n")
        for snap in snapshots:
            print(f"ID: {snap['snapshot_id']}")
            print(f"时间: {snap['timestamp']}")
            print(f"文档数: {snap['document_count']}")
            print(f"Chunk数: {snap['total_chunks']}")
            print(f"触发方式: {snap['trigger']}")
            print("-" * 40)
    
    elif args.action == 'latest':
        snapshot = manager.get_latest_snapshot()
        if snapshot:
            print(f"最新快照: {snapshot.snapshot_id}")
            print(f"时间: {snapshot.timestamp}")
            print(f"文档数: {len(snapshot.documents)}")
            print(f"Chunk数: {snapshot.total_chunks}")
        else:
            print("没有找到快照")
    
    elif args.action == 'restore':
        if not args.snapshot_id:
            print("错误: 需要指定 --snapshot-id")
            return
        
        if args.generate_script:
            helper = RestoreHelper(manager)
            script_file = helper.generate_restore_script(args.snapshot_id, args.generate_script)
            print(f"恢复脚本已生成: {script_file}")
        else:
            success = manager.restore_snapshot(args.snapshot_id)
            if success:
                print("快照恢复完成")
            else:
                print("快照恢复失败")
    
    elif args.action == 'delete':
        if not args.snapshot_id:
            print("错误: 需要指定 --snapshot-id")
            return
        
        success = manager.delete_snapshot(args.snapshot_id)
        if success:
            print("快照删除完成")
        else:
            print("快照删除失败")


if __name__ == "__main__":
    main()
