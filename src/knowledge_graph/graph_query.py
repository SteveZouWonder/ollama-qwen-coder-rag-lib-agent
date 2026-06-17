#!/usr/bin/env python3
"""
图谱查询 - 知识图谱查询和推理
"""
import logging
from typing import List, Dict, Optional, Set, Any
from dataclasses import dataclass

from .graph_builder import get_graph_builder
from .entity_extractor import Entity, EntityType, Relation

logger = logging.getLogger(__name__)


@dataclass
class QueryResult:
    """查询结果"""
    entities: List[Entity]
    relations: List[Relation]
    confidence: float = 1.0
    explanation: str = ""
    metadata: Dict = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}
    
    def to_dict(self) -> Dict:
        """转换为字典"""
        return {
            'entities': [e.to_dict() for e in self.entities],
            'relations': [r.to_dict() for r in self.relations],
            'confidence': self.confidence,
            'explanation': self.explanation,
            'metadata': self.metadata
        }


class GraphQuery:
    """图谱查询器"""
    
    def __init__(self):
        self.logger = logger
        self.graph_builder = get_graph_builder()
    
    def query_entity(self, entity_text: str) -> QueryResult:
        """查询实体"""
        builder = self.graph_builder
        if builder.graph is None:
            return QueryResult(
                entities=[],
                relations=[],
                confidence=0.0,
                explanation="Graph 不可用（networkx 未安装）"
            )
        
        # 搜索匹配的实体
        entities = builder.get_entities_by_text(entity_text)
        
        # 获取相关关系
        relations = []
        for entity in entities:
            node_id = builder._get_node_id(entity)
            if node_id in builder.graph:
                # 获取该实体的所有关系
                for source, target, edge_data in builder.graph.edges(node_id, data=True):
                    # 构建关系对象
                    source_data = builder.graph.nodes[source]
                    target_data = builder.graph.nodes[target]
                    
                    relation = Relation(
                        source=Entity(
                            text=source_data['text'],
                            entity_type=EntityType(source_data['entity_type']),
                            confidence=source_data.get('confidence', 1.0)
                        ),
                        target=Entity(
                            text=target_data['text'],
                            entity_type=EntityType(target_data['entity_type']),
                            confidence=target_data.get('confidence', 1.0)
                        ),
                        relation_type=edge_data.get('relation_type', 'related_to'),
                        confidence=edge_data.get('confidence', 1.0),
                        evidence=edge_data.get('evidence', '')
                    )
                    relations.append(relation)
        
        explanation = f"找到 {len(entities)} 个实体和 {len(relations)} 个关系"
        
        return QueryResult(
            entities=entities,
            relations=relations,
            confidence=0.8 if entities else 0.0,
            explanation=explanation
        )
    
    def query_by_type(self, entity_type: EntityType) -> QueryResult:
        """按类型查询实体"""
        builder = self.graph_builder
        if builder.graph is None:
            return QueryResult(
                entities=[],
                relations=[],
                confidence=0.0,
                explanation="Graph 不可用"
            )
        
        entities = builder.get_entity_by_type(entity_type)
        
        explanation = f"找到 {len(entities)} 个 {entity_type.value} 类型的实体"
        
        return QueryResult(
            entities=entities,
            relations=[],
            confidence=1.0,
            explanation=explanation
        )
    
    def query_relations(self, entity_text: str, relation_type: str = None) -> QueryResult:
        """查询实体关系"""
        builder = self.graph_builder
        if builder.graph is None:
            return QueryResult(
                entities=[],
                relations=[],
                confidence=0.0,
                explanation="Graph 不可用"
            )
        
        # 找到实体
        entities = builder.get_entities_by_text(entity_text)
        if not entities:
            return QueryResult(
                entities=[],
                relations=[],
                confidence=0.0,
                explanation=f"未找到实体 '{entity_text}'"
            )
        
        # 获取关系
        all_relations = []
        for entity in entities:
            node_id = builder._get_node_id(entity)
            if node_id in builder.graph:
                for source, target, edge_data in builder.graph.edges(node_id, data=True):
                    if relation_type is None or edge_data.get('relation_type') == relation_type:
                        source_data = builder.graph.nodes[source]
                        target_data = builder.graph.nodes[target]
                        
                        relation = Relation(
                            source=Entity(
                                text=source_data['text'],
                                entity_type=EntityType(source_data['entity_type']),
                                confidence=source_data.get('confidence', 1.0)
                            ),
                            target=Entity(
                                text=target_data['text'],
                                entity_type=EntityType(target_data['entity_type']),
                                confidence=target_data.get('confidence', 1.0)
                            ),
                            relation_type=edge_data.get('relation_type', 'related_to'),
                            confidence=edge_data.get('confidence', 1.0),
                            evidence=edge_data.get('evidence', '')
                        )
                        all_relations.append(relation)
        
        explanation = f"找到 {len(all_relations)} 个关系"
        
        return QueryResult(
            entities=entities,
            relations=all_relations,
            confidence=0.8 if all_relations else 0.0,
            explanation=explanation
        )
    
    def query_neighbors(self, entity_text: str, max_distance: int = 1) -> QueryResult:
        """查询实体邻居"""
        builder = self.graph_builder
        if builder.graph is None:
            return QueryResult(
                entities=[],
                relations=[],
                confidence=0.0,
                explanation="Graph 不可用"
            )
        
        # 找到实体
        entities = builder.get_entities_by_text(entity_text)
        if not entities:
            return QueryResult(
                entities=[],
                relations=[],
                confidence=0.0,
                explanation=f"未找到实体 '{entity_text}'"
            )
        
        # 获取邻居
        target_entity = entities[0]
        neighbors = builder.get_neighbors(target_entity, max_distance)
        
        explanation = f"找到 {len(neighbors)} 个邻居实体"
        
        return QueryResult(
            entities=neighbors,
            relations=[],
            confidence=0.9,
            explanation=explanation
        )
    
    def query_path(self, source_text: str, target_text: str) -> QueryResult:
        """查询实体间路径"""
        builder = self.graph_builder
        if builder.graph is None:
            return QueryResult(
                entities=[],
                relations=[],
                confidence=0.0,
                explanation="Graph 不可用"
            )
        
        # 找到实体
        source_entities = builder.get_entities_by_text(source_text)
        target_entities = builder.get_entities_by_text(target_text)
        
        if not source_entities or not target_entities:
            return QueryResult(
                entities=[],
                relations=[],
                confidence=0.0,
                explanation=f"未找到源或目标实体"
            )
        
        # 查找路径
        path = builder.find_path(source_entities[0], target_entities[0])
        
        if path:
            explanation = f"找到路径，跳数: {len(path) - 1}"
        else:
            explanation = "未找到路径"
        
        return QueryResult(
            entities=path if path else [],
            relations=[],
            confidence=0.7 if path else 0.0,
            explanation=explanation
        )
    
    def query_similar(self, entity_text: str) -> QueryResult:
        """查询相似实体"""
        builder = self.graph_builder
        if builder.graph is None:
            return QueryResult(
                entities=[],
                relations=[],
                confidence=0.0,
                explanation="Graph 不可用"
            )
        
        # 找到目标实体
        target_entities = builder.get_entities_by_text(entity_text)
        if not target_entities:
            return QueryResult(
                entities=[],
                relations=[],
                confidence=0.0,
                explanation=f"未找到实体 '{entity_text}'"
            )
        
        target = target_entities[0]
        target_id = builder._get_node_id(target)
        
        # 获取相似实体（有共同邻居的实体）
        similar_entities = []
        
        if target_id in builder.graph:
            # 获取目标实体的邻居
            target_neighbors = set(builder.graph.neighbors(target_id))
            
            # 找到有共同邻居的实体
            for node_id in builder.graph.nodes():
                if node_id != target_id:
                    neighbors = set(builder.graph.neighbors(node_id))
                    common = target_neighbors & neighbors
                    if len(common) > 0:
                        node_data = builder.graph.nodes[node_id]
                        similar_entities.append(Entity(
                            text=node_data['text'],
                            entity_type=EntityType(node_data['entity_type']),
                            confidence=len(common) / len(target_neighbors),
                            context=f"共同邻居: {len(common)}"
                        ))
        
        # 按相似度排序
        similar_entities.sort(key=lambda e: e.confidence, reverse=True)
        
        explanation = f"找到 {len(similar_entities)} 个相似实体"
        
        return QueryResult(
            entities=similar_entities[:10],  # 限制数量
            relations=[],
            confidence=0.6,
            explanation=explanation
        )
    
    def get_graph_summary(self) -> Dict[str, Any]:
        """获取图谱摘要"""
        builder = self.graph_builder
        stats = builder.get_statistics()
        
        return {
            'is_available': builder.graph is not None,
            'statistics': stats.to_dict(),
            'entity_types': list(stats.entity_types.keys()) if stats else [],
            'relation_types': list(stats.relation_types.keys()) if stats else []
        }


# 全局图谱查询器实例
_graph_query = None

def get_graph_query() -> GraphQuery:
    """获取全局图谱查询器实例"""
    global _graph_query
    if _graph_query is None:
        _graph_query = GraphQuery()
    return _graph_query
