#!/usr/bin/env python3
"""
知识库到Skill转化引擎
- 分析文档内容并提取主题
- 按主题合并多个文档生成Skill
- 智能分类通用型vs项目型
- 支持 OpenCode 和 Claude 平台
"""
import os
import re
import json
import logging
import warnings
from pathlib import Path
from typing import List, Dict, Optional, Set, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime
from collections import defaultdict
import hashlib

# 禁用ChromaDB遥测
os.environ['ANONYMIZED_TELEMETRY'] = 'False'
os.environ['CHROMA_TELEMETRY'] = 'False'
os.environ['DO_NOT_TRACK'] = 'true'
logging.getLogger("chromadb").setLevel(logging.ERROR)
logging.getLogger("chromadb.telemetry").setLevel(logging.CRITICAL)
warnings.filterwarnings("ignore", message="urllib3 v2 only supports OpenSSL 1.1.1+")

import chromadb
from document_loader import load_documents

# 导入内容安全扫描器
try:
    from content_security import ContentSecurityScanner, SkillSecurityFilter, ThreatLevel
    SECURITY_AVAILABLE = True
except ImportError:
    SECURITY_AVAILABLE = False


# ==================== 数据模型 ====================

@dataclass
class DocumentInfo:
    """文档信息"""
    file_path: str
    file_name: str
    file_type: str
    chunk_count: int
    content_preview: str
    topics: List[str]
    is_generic: bool  # True=通用型, False=项目专用型
    confidence: float  # 分类置信度


@dataclass
class TopicGroup:
    """主题分组"""
    topic_name: str
    documents: List[DocumentInfo]
    skill_name: str
    description: str
    platforms: List[str]  # ['opencode', 'claude']


@dataclass
class SkillConfig:
    """Skill配置"""
    name: str
    description: str
    argument_hint: str = ""
    allowed_tools: List[str] = None
    triggers: List[str] = None
    subagent: bool = False
    model: str = ""
    
    def __post_init__(self):
        if self.allowed_tools is None:
            self.allowed_tools = ["read", "grep", "glob", "exec"]
        if self.triggers is None:
            self.triggers = ["user", "model"]


# ==================== 文档内容分析器 ====================

class DocumentAnalyzer:
    """文档内容分析器"""
    
    # 通用型文档关键词
    GENERIC_KEYWORDS = {
        'cloudflare': ['cloudflare', 'tunnel', 'dns', '域名'],
        'networking': ['network', '网络', 'ssh', 'ftp', 'http', 'https'],
        'devops': ['docker', 'kubernetes', 'k8s', 'ci/cd', 'deploy', '部署'],
        'security': ['security', '安全', '加密', 'ssl', 'tls', 'auth'],
        'database': ['database', '数据库', 'mysql', 'postgres', 'mongodb', 'redis'],
        'linux': ['linux', 'ubuntu', 'centos', 'bash', 'shell', '命令'],
        'git': ['git', 'version control', '版本控制', 'commit', 'branch'],
        'monitoring': ['monitor', '监控', 'log', '日志', 'prometheus', 'grafana'],
    }
    
    # 项目专用型文档关键词
    PROJECT_SPECIFIC_KEYWORDS = {
        'project_structure': ['项目结构', 'architecture', '架构设计'],
        'business_logic': ['业务逻辑', '业务规则', 'workflow', '工作流'],
        'internal_config': ['内部配置', 'config', '配置文件', '环境变量'],
        'api_docs': ['api documentation', '接口文档', 'endpoint'],
        'team_process': ['团队流程', '开发规范', 'code review', '代码规范'],
    }
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    def analyze_document(self, file_path: str, chroma_client: chromadb.PersistentClient) -> DocumentInfo:
        """分析单个文档"""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"文件不存在: {file_path}")
        
        # 从ChromaDB获取文档信息
        collection = chroma_client.get_or_create_collection(name="rag_knowledge_base")
        
        # 获取该文件的所有chunks
        all_data = collection.get(include=['metadatas', 'documents'])
        
        file_chunks = []
        content_previews = []
        
        for metadata, doc in zip(all_data['metadatas'], all_data['documents']):
            if metadata.get('file_path') == str(path):
                file_chunks.append(doc)
                if len(content_previews) < 3:  # 只保存前3个chunk作为预览
                    content_previews.append(doc[:200])
        
        chunk_count = len(file_chunks)
        content_preview = "\n...\n".join(content_previews)
        
        # 分析主题
        topics = self._extract_topics(content_preview, path.name)
        
        # 分类通用型vs项目专用型
        is_generic, confidence = self._classify_generic_vs_project(content_preview, topics, path.name)
        
        return DocumentInfo(
            file_path=str(path),
            file_name=path.name,
            file_type=path.suffix,
            chunk_count=chunk_count,
            content_preview=content_preview,
            topics=topics,
            is_generic=is_generic,
            confidence=confidence
        )
    
    def _extract_topics(self, content: str, filename: str) -> List[str]:
        """从内容中提取主题"""
        topics = set()
        content_lower = content.lower()
        filename_lower = filename.lower()
        
        # 从通用关键词中提取主题
        for topic, keywords in self.GENERIC_KEYWORDS.items():
            for keyword in keywords:
                if keyword.lower() in content_lower or keyword.lower() in filename_lower:
                    topics.add(topic)
                    break
        
        # 从项目专用关键词中提取主题
        for topic, keywords in self.PROJECT_SPECIFIC_KEYWORDS.items():
            for keyword in keywords:
                if keyword.lower() in content_lower or keyword.lower() in filename_lower:
                    topics.add(topic)
                    break
        
        # 如果没有找到主题，使用文件名作为主题
        if not topics:
            base_name = Path(filename).stem
            topics.add(base_name.replace('-', '_').replace('_', ' '))
        
        return sorted(list(topics))
    
    def _classify_generic_vs_project(self, content: str, topics: List[str], filename: str) -> Tuple[bool, float]:
        """分类文档为通用型或项目专用型"""
        content_lower = content.lower()
        filename_lower = filename.lower()
        
        generic_score = 0
        project_score = 0
        
        # 计算通用型得分
        for topic, keywords in self.GENERIC_KEYWORDS.items():
            if topic in topics:
                generic_score += 2
            for keyword in keywords:
                if keyword.lower() in content_lower:
                    generic_score += 1
        
        # 计算项目专用型得分
        for topic, keywords in self.PROJECT_SPECIFIC_KEYWORDS.items():
            if topic in topics:
                project_score += 2
            for keyword in keywords:
                if keyword.lower() in content_lower:
                    project_score += 1
        
        # 检查文件名中的项目标识
        project_indicators = ['project', 'internal', 'team', 'company', 'proprietary']
        for indicator in project_indicators:
            if indicator in filename_lower:
                project_score += 3
        
        total_score = generic_score + project_score
        if total_score == 0:
            return True, 0.5  # 默认为通用型，中等置信度
        
        generic_ratio = generic_score / total_score
        confidence = abs(generic_ratio - 0.5) * 2  # 置信度：0到1
        
        is_generic = generic_ratio >= 0.5
        return is_generic, confidence


# ==================== 主题分类器 ====================

class TopicClassifier:
    """主题分类器 - 按主题合并文档"""
    
    def __init__(self, similarity_threshold: float = 0.3):
        self.similarity_threshold = similarity_threshold
        self.logger = logging.getLogger(__name__)
    
    def group_by_topic(self, documents: List[DocumentInfo]) -> List[TopicGroup]:
        """按主题分组文档"""
        # 按主题创建文档组
        topic_docs = defaultdict(list)
        
        for doc in documents:
            for topic in doc.topics:
                topic_docs[topic].append(doc)
        
        # 创建主题分组
        groups = []
        for topic, docs in topic_docs.items():
            skill_name = self._generate_skill_name(topic, docs)
            description = self._generate_description(topic, docs)
            platforms = self._determine_platforms(docs)
            
            group = TopicGroup(
                topic_name=topic,
                documents=docs,
                skill_name=skill_name,
                description=description,
                platforms=platforms
            )
            groups.append(group)
        
        return groups
    
    def _generate_skill_name(self, topic: str, documents: List[DocumentInfo]) -> str:
        """生成skill名称"""
        # 转换为kebab-case
        skill_name = topic.lower().replace(' ', '-').replace('_', '-')
        # 移除特殊字符
        skill_name = re.sub(r'[^a-z0-9-]', '', skill_name)
        # 限制长度
        if len(skill_name) > 30:
            skill_name = skill_name[:30]
        return skill_name
    
    def _generate_description(self, topic: str, documents: List[DocumentInfo]) -> str:
        """生成skill描述"""
        doc_names = [doc.file_name for doc in documents]
        if len(doc_names) > 2:
            doc_list = f"{', '.join(doc_names[:2])} 等{len(doc_names)}个文档"
        else:
            doc_list = ', '.join(doc_names)
        
        return f"{topic.capitalize()} 相关知识和操作指南 - 基于 {doc_list}"
    
    def _determine_platforms(self, documents: List[DocumentInfo]) -> List[str]:
        """确定支持的平台。

        无论通用型还是项目专用型文档，都统一生成 opencode + claude 两个平台的
        skill——生成内容本身与平台无关（见 SkillGenerator._format_skill），
        两平台仅输出目录不同。此前写死 devin（较小众）且项目型只出单平台，
        与“将知识库转化为 Skills（多平台）”的定位不符，故改为面向更主流的
        OpenCode 与 Claude，并始终返回全部平台。
        """
        return ['opencode', 'claude']


# ==================== Skill生成器 ====================

class SkillGenerator:
    """Skill生成器"""
    
    def __init__(self, platform: str = 'opencode', skill_filter=None):
        self.platform = platform
        self.skill_filter = skill_filter
        self.logger = logging.getLogger(__name__)
    
    def generate_skill(self, group: TopicGroup, chroma_client: chromadb.PersistentClient) -> str:
        """生成skill内容"""
        config = self._generate_config(group)
        content = self._generate_content(group, chroma_client)
        
        return self._format_skill(config, content)
    
    def _generate_config(self, group: TopicGroup) -> SkillConfig:
        """生成skill配置"""
        return SkillConfig(
            name=group.skill_name,
            description=group.description,
            allowed_tools=["read", "grep", "glob", "exec"],
            triggers=["user", "model"]
        )
    
    def _generate_content(self, group: TopicGroup, chroma_client: chromadb.PersistentClient) -> str:
        """生成skill内容"""
        collection = chroma_client.get_or_create_collection(name="rag_knowledge_base")
        
        # 获取所有相关文档的内容
        all_content = []
        
        for doc in group.documents:
            all_data = collection.get(include=['metadatas', 'documents'])
            
            doc_chunks = []
            for metadata, doc_content in zip(all_data['metadatas'], all_data['documents']):
                if metadata.get('file_path') == doc.file_path:
                    doc_chunks.append(doc_content)
            
            if doc_chunks:
                all_content.append(f"## {doc.file_name}\n")
                all_content.extend(doc_chunks[:5])  # 每个文档最多5个chunk
                all_content.append("\n")
        
        # 生成skill内容模板
        content = f"""# {group.topic_name.capitalize()} 专家助手

你是{group.topic_name}领域的专家助手。基于以下知识库内容提供帮助：

## 知识库内容

{chr(10).join(all_content[:20])}  # 限制总长度

## 你的职责

当用户询问关于{group.topic_name}的问题时，请：

1. **问题分析**：理解用户的具体需求和问题类型
2. **知识检索**：从上述知识库中查找相关信息
3. **方案提供**：基于知识库内容提供具体的解决方案
4. **操作指导**：如果需要，提供具体的命令和配置示例
5. **原理解释**：解释操作原理和注意事项

## 注意事项

- 优先使用知识库中的信息
- 如果知识库中没有相关信息，明确告知用户
- 提供的命令和配置要经过验证
- 对于危险操作，给出明确的警告
"""
        
        # 安全过滤
        if self.skill_filter:
            safe_content, is_allowed, issues = self.skill_filter.filter_skill_content(
                content, f"{group.skill_name}"
            )
            if not is_allowed:
                self.logger.error(f"skill内容包含严重安全问题，已拒绝生成")
                return f"# 安全警告\n\n此skill因为安全问题被拒绝生成。\n\n检测到的问题：\n" + \
                       "\n".join(f"- {issue.description}" for issue in issues[:5])
            return safe_content
        
        return content
    
    def _format_skill(self, config: SkillConfig, content: str) -> str:
        """格式化为skill文件"""
        frontmatter = f"""---
name: {config.name}
description: {config.description}
argument-hint: {config.argument_hint}
allowed-tools:
{chr(10).join(f'  - {tool}' for tool in config.allowed_tools)}
triggers:
{chr(10).join(f'  - {trigger}' for trigger in config.triggers)}
---

"""
        return frontmatter + content


# ==================== 主转化引擎 ====================

class KnowledgeToSkillsEngine:
    """知识库到Skill转化引擎"""
    
    def __init__(self, index_dir: str = None, enable_security: bool = True):
        # 路径必须与 /add 写入端（config.VECTOR_DB_PATH / INDEX_DIR）保持一致。
        # 历史 bug：这里写死相对路径 "./index_storage"，按运行时 cwd 解析；而写入端
        # 用的是 config 的绝对路径。当 cwd 不是项目根（打包运行 / 用过 /cd / 从别处
        # 启动）时，两者指向不同目录，读取端被 chromadb 静默新建为空库，导致误报
        # “没有找到可分析的文档”。默认改用 config.INDEX_DIR 消除该不一致。
        if index_dir is None:
            try:
                from config import INDEX_DIR as _INDEX_DIR
            except ImportError:
                from src.config import INDEX_DIR as _INDEX_DIR  # type: ignore
            self.index_dir = Path(_INDEX_DIR)
        else:
            self.index_dir = Path(index_dir)
        self.chroma_path = str(self.index_dir / "chroma_db")
        self.chroma_client = chromadb.PersistentClient(path=self.chroma_path)
        
        self.analyzer = DocumentAnalyzer()
        self.classifier = TopicClassifier()
        
        # 创建生成器实例（在安全扫描器初始化之后）
        self.opencode_generator = None
        self.claude_generator = None
        
        # 安全扫描器
        self.enable_security = enable_security
        self.security_scanner = None
        self.skill_filter = None
        if SECURITY_AVAILABLE and enable_security:
            self.security_scanner = ContentSecurityScanner()
            self.skill_filter = SkillSecurityFilter(self.security_scanner)
            print("🔒 内容安全扫描器已启用")
        
        # 在安全扫描器初始化后创建生成器实例
        self.opencode_generator = SkillGenerator(platform='opencode', skill_filter=self.skill_filter)
        self.claude_generator = SkillGenerator(platform='claude', skill_filter=self.skill_filter)
        
        self.logger = logging.getLogger(__name__)
        logging.basicConfig(level=logging.INFO)
    
    def convert(self, output_dir: str = None) -> Dict[str, any]:
        """执行转化"""
        # 默认输出统一以 App 数据目录为基准，与 cwd 解耦（/cd 不影响写入位置）。
        try:
            from runtime_paths import user_data_dir
        except ImportError:
            from src.runtime_paths import user_data_dir  # type: ignore
        # data_root 为 App 数据目录基准根（源码=项目根，打包=用户数据目录）。
        data_root = user_data_dir()
        if output_dir is None:
            output_path = data_root / ".opencode" / "skills"
        else:
            output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        self.logger.info("开始分析知识库文档...")
        self.logger.info(f"读取向量库: {self.chroma_path}")

        # 1. 读取向量库集合。用 get_collection 而非 get_or_create_collection：
        #    集合不存在时应明确提示“路径错配/尚未入库”，而非静默新建空库，把
        #    “目录不对”伪装成“没有可分析的文档”。
        try:
            collection = self.chroma_client.get_collection(name="rag_knowledge_base")
        except Exception:  # noqa: BLE001 - chromadb 在集合不存在时抛异常
            self.logger.warning(
                f"未找到向量库集合 'rag_knowledge_base'（路径: {self.chroma_path}）。"
                "请确认已通过 /add 入库，且运行目录与写入路径一致。"
            )
            return {}

        all_data = collection.get(include=['metadatas'])
        metadatas = all_data.get('metadatas') or []
        if not metadatas:
            self.logger.warning(
                f"向量库为空（路径: {self.chroma_path}）。请先用 /add 添加文档。"
            )
            return {}

        unique_files = set()
        for metadata in metadatas:
            if metadata and 'file_path' in metadata:
                unique_files.add(metadata['file_path'])

        if not unique_files:
            self.logger.warning(
                f"向量库中有 {len(metadatas)} 个片段，但均缺少 file_path 元数据，无法分析。"
            )
            return {}

        documents = []
        for file_path in unique_files:
            try:
                doc_info = self.analyzer.analyze_document(file_path, self.chroma_client)
                documents.append(doc_info)
                self.logger.info(f"已分析: {doc_info.file_name} - 主题: {doc_info.topics}")
            except Exception as e:
                self.logger.error(f"分析文档失败 {file_path}: {e}")
        
        if not documents:
            self.logger.warning("没有找到可分析的文档")
            return {}
        
        # 2. 按主题分组
        self.logger.info("按主题分组文档...")
        topic_groups = self.classifier.group_by_topic(documents)
        
        # 3. 生成skills
        results = {}
        for group in topic_groups:
            self.logger.info(f"生成skill: {group.skill_name} ({group.platforms})")
            
            # 为每个平台生成skill
            for platform in group.platforms:
                generator = self.claude_generator if platform == 'claude' else self.opencode_generator
                
                # 确定输出目录
                if group.documents[0].is_generic:
                    # 通用型：写入各工具约定的全局技能目录，与 App 数据目录无关。
                    # - opencode: ~/.config/opencode/skills
                    # - claude:   ~/.claude/skills（Claude Code 全局技能约定位置）
                    if platform == 'claude':
                        skill_dir = Path.home() / '.claude' / 'skills' / group.skill_name
                    else:
                        skill_dir = Path.home() / '.config' / 'opencode' / 'skills' / group.skill_name
                else:
                    # 项目专用型：统一落到 App 数据目录基准（data_root），
                    # 不再用 Path.cwd()（受工作目录影响，/cd 后会漂移到别处）。
                    subdir = '.claude' if platform == 'claude' else '.opencode'
                    skill_dir = data_root / subdir / 'skills' / group.skill_name
                
                skill_dir.mkdir(parents=True, exist_ok=True)
                
                # 生成skill内容
                skill_content = generator.generate_skill(group, self.chroma_client)
                
                # 写入文件
                skill_file = skill_dir / 'SKILL.md'
                with open(skill_file, 'w', encoding='utf-8') as f:
                    f.write(skill_content)
                
                results[f"{platform}/{group.skill_name}"] = str(skill_file)
                self.logger.info(f"  已生成: {skill_file}")
        
        return results
    
    def get_document_summary(self) -> List[Dict]:
        """获取文档摘要"""
        all_data = self.chroma_client.get_or_create_collection(name="rag_knowledge_base").get(include=['metadatas'])
        unique_files = set()
        
        for metadata in all_data['metadatas']:
            if 'file_path' in metadata:
                unique_files.add(metadata['file_path'])
        
        summary = []
        for file_path in unique_files:
            try:
                doc_info = self.analyzer.analyze_document(file_path, self.chroma_client)
                summary.append({
                    'file_name': doc_info.file_name,
                    'file_path': doc_info.file_path,
                    'topics': doc_info.topics,
                    'is_generic': doc_info.is_generic,
                    'confidence': doc_info.confidence,
                    'chunk_count': doc_info.chunk_count
                })
            except Exception as e:
                self.logger.error(f"分析文档失败 {file_path}: {e}")
        
        return summary


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description='知识库到Skill转化工具')
    # 默认 None：走引擎内部统一的 App 数据目录基准（与 /add 写入路径一致），
    # 不再写死相对 cwd 的路径。用户仍可显式覆盖。
    parser.add_argument('--index-dir', default=None, help='索引目录（默认：App 数据目录/index_storage）')
    parser.add_argument('--output-dir', default=None, help='输出目录（默认：App 数据目录/.opencode/skills）')
    parser.add_argument('--summary', action='store_true', help='只显示文档摘要')
    
    args = parser.parse_args()
    
    engine = KnowledgeToSkillsEngine(args.index_dir)
    
    if args.summary:
        summary = engine.get_document_summary()
        print(json.dumps(summary, indent=2, ensure_ascii=False))
    else:
        results = engine.convert(args.output_dir)
        print(f"\n转化完成！生成 {len(results)} 个skill:")
        for key, path in results.items():
            print(f"  {key}: {path}")


if __name__ == "__main__":
    main()
