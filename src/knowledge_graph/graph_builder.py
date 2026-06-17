#!/usr/bin/env python3
"""
知识图谱构建器 - 构建和管理知识图谱
"""
import logging
from typing import List, Dict, Set, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
import json

try:
    import networkx as nx
    NETWORKX_AVAILABLE = True
except ImportError:
    NETWORKX_AVAILABLE = False
    nx = None

from .entity_extractor import Entity, Relation, EntityType, get_entity_extractor

logger = logging.getLogger(__name__)


@dataclass
class GraphStatistics:
    """图谱统计信息"""
    total_nodes: int = 0
    total_edges: int = 0
    entity_types: Dict[str, int] = field(default_factory=dict)
    relation_types: Dict[str, int] = field(default_factory=dict)
    connected_components: int = 0
    average_degree: float = 0.0
    density: float = 0.0
    
    def to_dict(self) -> Dict:
        """转换为字典"""
        return {
            'total_nodes': self.total_nodes,
            'total_edges': self.total_edges,
            'entity_types': self.entity_types,
            'relation_types': self.relation_types,
            'connected_components': self.connected_components,
            'average_degree': self.average_degree,
            'density': self.density
        }


class KnowledgeGraphBuilder:
    """知识图谱构建器"""
    
    def __init__(self):
        self.logger = logger
        
        if not NETWORKX_AVAILABLE:
            self.logger.warning("networkx 未安装，知识图谱功能受限")
            self.graph = None
        else:
            self.graph = nx.DiGraph()
        
        self.entity_extractor = get_entity_extractor()
        self._node_id_counter = 0
    
    def _get_node_id(self, entity: Entity) -> str:
        """生成节点ID"""
        return f"{entity.entity_type.value}_{entity.text.lower().replace(' ', '_')}"
    
    def add_document(self, text: str, doc_id: str, doc_type: str = "text"):
        """添加文档到知识图谱"""
        if self.graph is None:
            self.logger.error("Graph 不可用（networkx 未安装）")
            return False
        
        try:
            entities, relations = self.entity_extractor.extract_from_document(text, doc_type)
            
            # 添加实体节点
            for entity in entities:
                node_id = self._get_node_id(entity)
                if node_id not in self.graph:
                    self.graph.add_node(
                        node_id,
                        text=entity.text,
                        entity_type=entity.entity_type.value,
                        confidence=entity.confidence,
                        context=entity.context,
                        documents=[doc_id],
                        metadata=entity.metadata
                    )
                else:
                    # 更新现有节点
                    if doc_id not in self.graph.nodes[node_id]['documents']:
                        self.graph.nodes[node_id]['documents'].append(doc_id)
            
            # 添加关系边
            for relation in relations:
                source_id = self._get_node_id(relation.source)
                target_id = self._get_node_id(relation.target)
                
                if source_id in self.graph and target_id in self.graph:
                    # 检查边是否已存在
                    if not self.graph.has_edge(source_id, target_id):
                        self.graph.add_edge(
                            source_id,
                            target_id,
                            relation_type=relation.relation_type.value,
                            confidence=relation.confidence,
                            evidence=relation.evidence,
                            documents=[doc_id]
                        )
                    else:
                        # 更新现有边
                        if doc_id not in self.graph[source_id][target_id]['documents']:
                            self.graph[source_id][target_id]['documents'].append(doc_id)
            
            self.logger.info(f"文档 {doc_id} 已添加到知识图谱")
            return True
            
        except Exception as e:
            self.logger.error(f"添加文档到知识图谱失败: {e}")
            return False
    
    def add_entity(self, entity: Entity):
        """添加单个实体"""
        if self.graph is None:
            return False
        
        node_id = self._get_node_id(entity)
        if node_id not in self.graph:
            self.graph.add_node(
                node_id,
                text=entity.text,
                entity_type=entity.entity_type.value,
                confidence=entity.confidence,
                context=entity.context,
                documents=[],
                metadata=entity.metadata
            )
        
        return True
    
    def add_relation(self, relation: Relation):
        """添加单个关系"""
        if self.graph is None:
            return False
        
        source_id = self._get_node_id(relation.source)
        target_id = self._get_node_id(relation.target)
        
        if source_id in self.graph and target_id in self.graph:
            if not self.graph.has_edge(source_id, target_id):
                self.graph.add_edge(
                    source_id,
                    target_id,
                    relation_type=relation.relation_type.value,
                    confidence=relation.confidence,
                    evidence=relation.evidence,
                    documents=[]
                )
        
        return True
    
    def get_statistics(self) -> GraphStatistics:
        """获取图谱统计信息"""
        if self.graph is None:
            return GraphStatistics()
        
        stats = GraphStatistics()
        stats.total_nodes = self.graph.number_of_nodes()
        stats.total_edges = self.graph.number_of_edges()
        
        # 统计实体类型
        for node_id, node_data in self.graph.nodes(data=True):
            entity_type = node_data.get('entity_type', 'other')
            stats.entity_types[entity_type] = stats.entity_types.get(entity_type, 0) + 1
        
        # 统计关系类型
        for _, _, edge_data in self.graph.edges(data=True):
            relation_type = edge_data.get('relation_type', 'other')
            stats.relation_types[relation_type] = stats.relation_types.get(relation_type, 0) + 1
        
        # 连通分量
        if NETWORKX_AVAILABLE:
            stats.connected_components = nx.number_weakly_connected_components(self.graph)
        
        # 平均度
        if stats.total_nodes > 0:
            stats.average_degree = sum(dict(self.graph.degree()).values()) / stats.total_nodes
        
        # 密度
        if stats.total_nodes > 1:
            stats.density = nx.density(self.graph)
        
        return stats
    
    def get_neighbors(self, entity: Entity, max_distance: int = 1) -> List[Entity]:
        """获取实体的邻居"""
        if self.graph is None:
            return []
        
        neighbors = []
        node_id = self._get_node_id(entity)
        
        if node_id not in self.graph:
            return neighbors
        
        if max_distance == 1:
            # 直接邻居
            for neighbor_id in self.graph.neighbors(node_id):
                neighbor_data = self.graph.nodes[neighbor_id]
                neighbors.append(Entity(
                    text=neighbor_data['text'],
                    entity_type=EntityType(neighbor_data['entity_type']),
                    confidence=neighbor_data.get('confidence', 1.0)
                ))
        else:
            # 多跳邻居
            for node_id in nx.single_source_shortest_path_length(
                self.graph, node_id, cutoff=max_distance
            ).keys():
                if node_id != self._get_node_id(entity):
                    neighbor_data = self.graph.nodes[node_id]
                    neighbors.append(Entity(
                        text=neighbor_data['text'],
                        entity_type=EntityType(neighbor_data['entity_type']),
                        confidence=neighbor_data.get('confidence', 1.0)
                    ))
        
        return neighbors
    
    def find_path(self, source: Entity, target: Entity) -> Optional[List[Entity]]:
        """查找实体间路径"""
        if self.graph is None:
            return None
        
        source_id = self._get_node_id(source)
        target_id = self._get_node_id(target)
        
        if source_id not in self.graph or target_id not in self.graph:
            return None
        
        try:
            path_ids = nx.shortest_path(self.graph, source_id, target_id)
            path_entities = []
            
            for node_id in path_ids:
                node_data = self.graph.nodes[node_id]
                path_entities.append(Entity(
                    text=node_data['text'],
                    entity_type=EntityType(node_data['entity_type']),
                    confidence=node_data.get('confidence', 1.0)
                ))
            
            return path_entities
        except nx.NetworkXNoPath:
            return None
    
    def save_graph(self, file_path: str):
        """保存图谱到文件"""
        if self.graph is None:
            return False
        
        try:
            # 转换为可序列化的格式
            graph_data = {
                'nodes': [],
                'edges': []
            }
            
            # 保存节点
            for node_id, node_data in self.graph.nodes(data=True):
                node_dict = {'id': node_id}
                node_dict.update(node_data)
                graph_data['nodes'].append(node_dict)
            
            # 保存边
            for source, target, edge_data in self.graph.edges(data=True):
                edge_dict = {
                    'source': source,
                    'target': target
                }
                edge_dict.update(edge_data)
                graph_data['edges'].append(edge_dict)
            
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(graph_data, f, ensure_ascii=False, indent=2)
            
            self.logger.info(f"图谱已保存到 {file_path}")
            return True
        except Exception as e:
            self.logger.error(f"保存图谱失败: {e}")
            return False
    
    def load_graph(self, file_path: str):
        """从文件加载图谱"""
        if self.graph is None:
            return False
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                graph_data = json.load(f)
            
            # 清空现有图谱
            self.graph.clear()
            
            # 添加节点
            for node_data in graph_data.get('nodes', []):
                node_id = node_data.pop('id')
                self.graph.add_node(node_id, **node_data)
            
            # 添加边
            for edge_data in graph_data.get('edges', []):
                source = edge_data.pop('source')
                target = edge_data.pop('target')
                self.graph.add_edge(source, target, **edge_data)
            
            self.logger.info(f"图谱已从 {file_path} 加载")
            return True
        except Exception as e:
            self.logger.error(f"加载图谱失败: {e}")
            return False
    
    def clear(self):
        """清空图谱"""
        if self.graph is not None:
            self.graph.clear()
            self.logger.info("知识图谱已清空")
    
    def get_entity_by_type(self, entity_type: EntityType) -> List[Entity]:
        """按类型获取实体"""
        if self.graph is None:
            return []
        
        entities = []
        type_str = entity_type.value
        
        for node_id, node_data in self.graph.nodes(data=True):
            if node_data.get('entity_type') == type_str:
                entities.append(Entity(
                    text=node_data['text'],
                    entity_type=EntityType(node_data['entity_type']),
                    confidence=node_data.get('confidence', 1.0)
                ))
        
        return entities
    
    def get_entities_by_text(self, text_pattern: str) -> List[Entity]:
        """按文本模式搜索实体"""
        if self.graph is None:
            return []
        
        entities = []
        pattern_lower = text_pattern.lower()
        
        for node_id, node_data in self.graph.nodes(data=True):
            if pattern_lower in node_data.get('text', '').lower():
                entities.append(Entity(
                    text=node_data['text'],
                    entity_type=EntityType(node_data['entity_type']),
                    confidence=node_data.get('confidence', 1.0)
                ))
        
        return entities


# 全局图谱构建器实例
_graph_builder = None

def get_graph_builder() -> KnowledgeGraphBuilder:
    """获取全局图谱构建器实例"""
    global _graph_builder
    if _graph_builder is None:
        _graph_builder = KnowledgeGraphBuilder()
    return _graph_builder
