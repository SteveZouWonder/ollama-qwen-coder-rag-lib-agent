#!/usr/bin/env python3
"""
知识图谱模块单元测试
"""
import pytest
from pathlib import Path
import tempfile
from unittest.mock import patch, MagicMock

# 导入被测试的模块
from knowledge_graph.entity_extractor import EntityExtractor, Entity, Relation, EntityType, RelationType
from knowledge_graph.graph_builder import KnowledgeGraphBuilder, GraphStatistics
from knowledge_graph.graph_query import GraphQuery, QueryResult


class TestEntityExtractor:
    """测试实体提取器"""
    
    def test_initialization(self):
        """测试初始化"""
        extractor = EntityExtractor()
        assert extractor is not None
        assert extractor.logger is not None
        assert isinstance(extractor.technology_patterns, dict)
    
    def test_extract_entities_from_text(self):
        """测试从文本提取实体"""
        extractor = EntityExtractor()
        text = "I use Python and TensorFlow for machine learning. React is a popular framework."
        
        entities = extractor.extract_entities(text)
        
        # 应该提取到一些技术术语
        tech_entities = [e for e in entities if e.entity_type in [EntityType.LANGUAGE, EntityType.FRAMEWORK]]
        assert len(tech_entities) > 0
    
    def test_extract_entities_from_code(self):
        """测试从代码提取实体"""
        extractor = EntityExtractor()
        code = """
import numpy as np
import pandas as pd

def process_data(data):
    result = data.mean()
    return result

class DataProcessor:
    def __init__(self):
        self.data = None
"""
        
        entities = extractor._extract_code_entities(code)
        
        # 应该提取到函数名和类名
        assert len(entities) >= 3
        entity_names = [e.text for e in entities]
        assert 'process_data' in entity_names
        assert 'DataProcessor' in entity_names
    
    def test_extract_relations_from_text(self):
        """测试从文本提取关系"""
        extractor = EntityExtractor()
        text = "React uses JavaScript. Django extends Python. TensorFlow implements machine learning."
        
        entities = extractor.extract_entities(text)
        relations = extractor.extract_relations(text, entities)
        
        assert len(relations) > 0
        # 应该提取到一些关系
        relation_types = [r.relation_type for r in relations]
        assert len(relation_types) > 0
    
    def test_extract_code_relations(self):
        """测试从代码提取关系"""
        extractor = EntityExtractor()
        code = """
import os
import sys

def function_a():
    return os.path

class ClassA:
    def method(self):
        pass

class ClassB(ClassA):
    pass
"""
        
        entities = extractor._extract_code_entities(code)
        relations = extractor.extract_code_relations(code, entities)
        
        # 应该提取到关系
        assert len(relations) > 0
    
    def test_extract_from_document(self):
        """测试从文档提取"""
        extractor = EntityExtractor()
        text = "Python is a programming language. It is used for data science."
        
        entities, relations = extractor.extract_from_document(text, "text")
        
        assert isinstance(entities, list)
        assert isinstance(relations, list)
        assert len(entities) > 0
    
    def test_entity_hash_and_equality(self):
        """测试实体的哈希和相等"""
        entity1 = Entity(
            text="Python",
            entity_type=EntityType.LANGUAGE
        )
        entity2 = Entity(
            text="python",  # 小写
            entity_type=EntityType.LANGUAGE
        )
        entity3 = Entity(
            text="Python",
            entity_type=EntityType.CONCEPT  # 不同类型
        )
        
        assert hash(entity1) == hash(entity2)
        assert entity1 == entity2
        assert entity1 != entity3
    
    def test_relation_hash_and_equality(self):
        """测试关系的哈希和相等"""
        entity1 = Entity("Python", EntityType.LANGUAGE)
        entity2 = Entity("Django", EntityType.FRAMEWORK)
        
        relation1 = Relation(entity1, entity2, RelationType.EXTENDS)
        relation2 = Relation(entity1, entity2, RelationType.EXTENDS)
        relation3 = Relation(entity1, entity2, RelationType.USES)
        
        assert hash(relation1) == hash(relation2)
        assert relation1 == relation2
        assert relation1 != relation3
    
    def test_entity_to_dict(self):
        """测试实体转换为字典"""
        entity = Entity(
            text="Python",
            entity_type=EntityType.LANGUAGE,
            confidence=0.9,
            context="test context"
        )
        
        entity_dict = entity.to_dict()
        
        assert entity_dict['text'] == "Python"
        assert entity_dict['entity_type'] == 'language'
        assert entity_dict['confidence'] == 0.9
    
    def test_relation_to_dict(self):
        """测试关系转换为字典"""
        entity1 = Entity("Python", EntityType.LANGUAGE)
        entity2 = Entity("Django", EntityType.FRAMEWORK)
        
        relation = Relation(entity1, entity2, RelationType.USES, confidence=0.8)
        
        relation_dict = relation.to_dict()
        
        assert relation_dict['source']['text'] == "Python"
        assert relation_dict['target']['text'] == "Django"
        assert relation_dict['relation_type'] == 'uses'


class TestKnowledgeGraphBuilder:
    """测试知识图谱构建器"""
    
    def test_initialization(self):
        """测试初始化"""
        builder = KnowledgeGraphBuilder()
        assert builder is not None
        assert builder.logger is not None
        assert builder.entity_extractor is not None
    
    def test_add_document(self):
        """测试添加文档"""
        builder = KnowledgeGraphBuilder()
        
        text = "Python is a programming language. TensorFlow is used for machine learning."
        success = builder.add_document(text, "doc1", "text")
        
        assert success
        assert builder.graph.number_of_nodes() > 0
    
    def test_add_entity(self):
        """测试添加实体"""
        builder = KnowledgeGraphBuilder()
        
        entity = Entity(text="Python", entity_type=EntityType.LANGUAGE)
        success = builder.add_entity(entity)
        
        assert success
        assert builder.graph.number_of_nodes() == 1
    
    def test_add_relation(self):
        """测试添加关系"""
        builder = KnowledgeGraphBuilder()
        
        entity1 = Entity("Python", EntityType.LANGUAGE)
        entity2 = Entity("Django", EntityType.FRAMEWORK)
        
        builder.add_entity(entity1)
        builder.add_entity(entity2)
        
        relation = Relation(entity1, entity2, RelationType.USES)
        success = builder.add_relation(relation)
        
        assert success
        assert builder.graph.number_of_edges() == 1
    
    def test_get_statistics(self):
        """测试获取统计信息"""
        builder = KnowledgeGraphBuilder()
        
        # 添加一些数据
        entity1 = Entity("Python", EntityType.LANGUAGE)
        entity2 = Entity("Django", EntityType.FRAMEWORK)
        entity3 = Entity("TensorFlow", EntityType.TOOL)
        
        builder.add_entity(entity1)
        builder.add_entity(entity2)
        builder.add_entity(entity3)
        
        relation = Relation(entity1, entity2, RelationType.USES)
        builder.add_relation(relation)
        
        stats = builder.get_statistics()
        
        assert stats.total_nodes == 3
        assert stats.total_edges == 1
        assert 'language' in stats.entity_types
        assert len(stats.entity_types) > 0
    
    def test_get_neighbors(self):
        """测试获取邻居"""
        builder = KnowledgeGraphBuilder()
        
        entity1 = Entity("Python", EntityType.LANGUAGE)
        entity2 = Entity("Django", EntityType.FRAMEWORK)
        entity3 = Entity("TensorFlow", EntityType.TOOL)
        
        builder.add_entity(entity1)
        builder.add_entity(entity2)
        builder.add_entity(entity3)
        
        relation1 = Relation(entity1, entity2, RelationType.USES)
        relation2 = Relation(entity2, entity3, RelationType.EXTENDS)
        
        builder.add_relation(relation1)
        builder.add_relation(relation2)
        
        neighbors = builder.get_neighbors(entity1)
        
        assert len(neighbors) == 1
        assert neighbors[0].text == "Django"
    
    def test_find_path(self):
        """测试查找路径"""
        builder = KnowledgeGraphBuilder()
        
        entity1 = Entity("Python", EntityType.LANGUAGE)
        entity2 = Entity("Django", EntityType.FRAMEWORK)
        entity3 = Entity("Flask", EntityType.FRAMEWORK)
        
        builder.add_entity(entity1)
        builder.add_entity(entity2)
        builder.add_entity(entity3)
        
        relation1 = Relation(entity1, entity2, RelationType.USES)
        relation2 = Relation(entity2, entity3, RelationType.EXTENDS)
        
        builder.add_relation(relation1)
        builder.add_relation(relation2)
        
        path = builder.find_path(entity1, entity3)
        
        assert path is not None
        assert len(path) == 3
    
    def test_save_and_load_graph(self, tmp_path):
        """测试保存和加载图谱"""
        builder = KnowledgeGraphBuilder()
        
        entity = Entity("Python", EntityType.LANGUAGE)
        builder.add_entity(entity)
        
        graph_file = tmp_path / "test_graph.json"
        save_success = builder.save_graph(str(graph_file))
        
        assert save_success
        assert graph_file.exists()
        
        builder.clear()
        assert builder.graph.number_of_nodes() == 0
        
        load_success = builder.load_graph(str(graph_file))
        
        assert load_success
        assert builder.graph.number_of_nodes() == 1
    
    def test_clear(self):
        """测试清空图谱"""
        builder = KnowledgeGraphBuilder()
        
        entity = Entity("Python", EntityType.LANGUAGE)
        builder.add_entity(entity)
        
        assert builder.graph.number_of_nodes() > 0
        
        builder.clear()
        
        assert builder.graph.number_of_nodes() == 0
    
    def test_get_entity_by_type(self):
        """测试按类型获取实体"""
        builder = KnowledgeGraphBuilder()
        
        entity1 = Entity("Python", EntityType.LANGUAGE)
        entity2 = Entity("Django", EntityType.FRAMEWORK)
        entity3 = Entity("React", EntityType.LANGUAGE)
        
        builder.add_entity(entity1)
        builder.add_entity(entity2)
        builder.add_entity(entity3)
        
        languages = builder.get_entity_by_type(EntityType.LANGUAGE)
        
        assert len(languages) == 2
    
    def test_get_entities_by_text(self):
        """测试按文本搜索实体"""
        builder = KnowledgeGraphBuilder()
        
        entity1 = Entity("Python", EntityType.LANGUAGE)
        entity2 = Entity("Django", EntityType.FRAMEWORK)
        entity3 = Entity("TensorFlow", EntityType.TOOL)
        
        builder.add_entity(entity1)
        builder.add_entity(entity2)
        builder.add_entity(entity3)
        
        results = builder.get_entities_by_text("Py")
        
        assert len(results) == 1
        assert results[0].text == "Python"
    
    def test_graph_statistics_to_dict(self):
        """测试统计信息转换为字典"""
        stats = GraphStatistics(
            total_nodes=5,
            total_edges=3,
            entity_types={'language': 2, 'framework': 3},
            relation_types={'uses': 2, 'extends': 1}
        )
        
        stats_dict = stats.to_dict()
        
        assert stats_dict['total_nodes'] == 5
        assert stats_dict['total_edges'] == 3
    
    def test_add_document_code_type(self):
        """测试添加代码类型文档"""
        builder = KnowledgeGraphBuilder()
        
        code = """
import os
def test_func():
    return os.path
"""
        
        success = builder.add_document(code, "code_doc", "code")
        
        assert success
        assert builder.graph.number_of_nodes() > 0
    
    def test_get_neighbors_max_distance(self):
        """测试多跳邻居查询"""
        builder = KnowledgeGraphBuilder()
        
        entity1 = Entity("Python", EntityType.LANGUAGE)
        entity2 = Entity("Django", EntityType.FRAMEWORK)
        entity3 = Entity("Flask", EntityType.FRAMEWORK)
        entity4 = Entity("SQL", EntityType.LANGUAGE)
        
        builder.add_entity(entity1)
        builder.add_entity(entity2)
        builder.add_entity(entity3)
        builder.add_entity(entity4)
        
        relation1 = Relation(entity1, entity2, RelationType.USES)
        relation2 = Relation(entity2, entity3, RelationType.EXTENDS)
        relation3 = Relation(entity3, entity4, RelationType.USES)
        
        builder.add_relation(relation1)
        builder.add_relation(relation2)
        builder.add_relation(relation3)
        
        neighbors = builder.get_neighbors(entity1, max_distance=2)
        
        assert len(neighbors) >= 2
    
    def test_add_relation_updates_existing_edge(self):
        """测试添加关系更新现有边"""
        builder = KnowledgeGraphBuilder()
        
        entity1 = Entity("Python", EntityType.LANGUAGE)
        entity2 = Entity("Django", EntityType.FRAMEWORK)
        
        builder.add_entity(entity1)
        builder.add_entity(entity2)
        
        relation1 = Relation(entity1, entity2, RelationType.USES, confidence=0.7)
        builder.add_relation(relation1)
        
        edge_count_1 = builder.graph.number_of_edges()
        
        relation2 = Relation(entity1, entity2, RelationType.USES, confidence=0.8)
        builder.add_relation(relation2)
        
        edge_count_2 = builder.graph.number_of_edges()
        
        assert edge_count_1 == edge_count_2
    
    def test_find_path_direct_connection(self):
        """测试直接连接的路径"""
        builder = KnowledgeGraphBuilder()
        
        entity1 = Entity("Python", EntityType.LANGUAGE)
        entity2 = Entity("Django", EntityType.FRAMEWORK)
        
        builder.add_entity(entity1)
        builder.add_entity(entity2)
        
        relation = Relation(entity1, entity2, RelationType.USES)
        builder.add_relation(relation)
        
        path = builder.find_path(entity1, entity2)
        
        assert path is not None
        assert len(path) == 2
    
    def test_get_statistics_empty_graph(self):
        """测试空图谱的统计信息"""
        builder = KnowledgeGraphBuilder()
        
        stats = builder.get_statistics()
        
        assert stats.total_nodes == 0
        assert stats.total_edges == 0
    
    def test_add_document_exception_handling(self):
        """测试add_document异常处理"""
        builder = KnowledgeGraphBuilder()
        
        # 模拟extractor失败的情况
        original_extractor = builder.entity_extractor
        
        class BrokenExtractor:
            def extract_from_document(self, text, doc_type):
                raise Exception("Intentional error")
        
        builder.entity_extractor = BrokenExtractor()
        
        success = builder.add_document("test", "doc1", "text")
        
        # 应该捕获异常并返回False
        assert not success
        
        builder.entity_extractor = original_extractor
    
    def test_add_entity_updates_metadata(self):
        """测试添加实体更新元数据"""
        builder = KnowledgeGraphBuilder()
        
        entity1 = Entity("Python", EntityType.LANGUAGE, confidence=0.8)
        builder.add_entity(entity1)
        
        entity2 = Entity("Python", EntityType.LANGUAGE, confidence=0.9)
        builder.add_entity(entity2)
        
        assert builder.graph.number_of_nodes() == 1
    
    def test_add_document_updates_existing_edge(self):
        """测试添加文档更新现有边的文档列表"""
        builder = KnowledgeGraphBuilder()
        
        # 第一次添加文档，创建边
        text1 = "Python uses Django for web development."
        builder.add_document(text1, "doc1", "text")
        
        # 第二次添加文档，相同的关系但不同的文档
        text2 = "I use Python with Django for my project."
        builder.add_document(text2, "doc2", "text")
        
        # 验证图谱有多个节点
        assert builder.graph.number_of_nodes() >= 2
    
    def test_add_document_updates_existing_node(self):
        """测试添加文档更新现有节点"""
        builder = KnowledgeGraphBuilder()
        
        text1 = "Python is a programming language."
        builder.add_document(text1, "doc1", "text")
        
        node_count_1 = builder.graph.number_of_nodes()
        
        text2 = "Python programming is popular worldwide."
        builder.add_document(text2, "doc2", "text")
        
        node_count_2 = builder.graph.number_of_nodes()
        
        # 节点数应该保持相同（实体去重）
        assert node_count_1 == node_count_2
    
    def test_graph_builder_without_networkx(self):
        """测试networkx不可用时的图谱构建器"""
        with patch('knowledge_graph.graph_builder.NETWORKX_AVAILABLE', False):
            builder = KnowledgeGraphBuilder()
            
            assert builder.graph is None
            
            # 测试add_entity在networkx不可用时返回False
            entity = Entity("Python", EntityType.LANGUAGE)
            result = builder.add_entity(entity)
            
            assert result is False
            
            # 测试add_relation在networkx不可用时返回False
            entity1 = Entity("Python", EntityType.LANGUAGE)
            entity2 = Entity("Django", EntityType.FRAMEWORK)
            relation = Relation(entity1, entity2, RelationType.USES)
            result = builder.add_relation(relation)
            
            assert result is False
    
    def test_add_document_without_networkx(self):
        """测试networkx不可用时的文档添加"""
        with patch('knowledge_graph.graph_builder.NETWORKX_AVAILABLE', False):
            builder = KnowledgeGraphBuilder()
            
            result = builder.add_document("Python is a language", "doc1", "text")
            
            assert result is False
    
    def test_get_statistics_without_networkx(self):
        """测试networkx不可用时的统计信息获取"""
        with patch('knowledge_graph.graph_builder.NETWORKX_AVAILABLE', False):
            builder = KnowledgeGraphBuilder()
            
            stats = builder.get_statistics()
            
            assert stats.total_nodes == 0
            assert stats.total_edges == 0
    
    def test_get_neighbors_without_networkx(self):
        """测试networkx不可用时的邻居获取"""
        with patch('knowledge_graph.graph_builder.NETWORKX_AVAILABLE', False):
            builder = KnowledgeGraphBuilder()
            
            entity = Entity("Python", EntityType.LANGUAGE)
            neighbors = builder.get_neighbors(entity)
            
            assert neighbors == []
    
    def test_find_path_without_networkx(self):
        """测试networkx不可用时的路径查找"""
        with patch('knowledge_graph.graph_builder.NETWORKX_AVAILABLE', False):
            builder = KnowledgeGraphBuilder()
            
            entity1 = Entity("Python", EntityType.LANGUAGE)
            entity2 = Entity("Django", EntityType.FRAMEWORK)
            path = builder.find_path(entity1, entity2)
            
            assert path is None
    
    def test_get_neighbors_invalid_distance(self):
        """测试无效距离参数"""
        builder = KnowledgeGraphBuilder()
        
        entity = Entity("Python", EntityType.LANGUAGE)
        builder.add_entity(entity)
        
        neighbors = builder.get_neighbors(entity, max_distance=-1)
        
        assert len(neighbors) == 0
    
    def test_find_path_node_not_exists(self):
        """测试节点不存在时的路径查找"""
        builder = KnowledgeGraphBuilder()
        
        entity1 = Entity("Python", EntityType.LANGUAGE)
        entity2 = Entity("Django", EntityType.FRAMEWORK)
        
        builder.add_entity(entity1)
        # entity2 没有添加
        
        path = builder.find_path(entity1, entity2)
        
        assert path is None
    
    def test_save_graph_failure(self):
        """测试保存图谱失败"""
        builder = KnowledgeGraphBuilder()
        
        # 使用无效的文件路径
        success = builder.save_graph("/invalid/path/that/does/not/exist/test.json")
        
        assert not success
    
    def test_load_graph_failure(self):
        """测试加载图谱失败"""
        builder = KnowledgeGraphBuilder()
        
        # 使用不存在的文件
        success = builder.load_graph("/nonexistent/file.json")
        
        assert not success
    
    def test_load_invalid_json(self, tmp_path):
        """测试加载无效的JSON文件"""
        builder = KnowledgeGraphBuilder()
        
        # 创建无效JSON文件
        invalid_file = tmp_path / "invalid.json"
        invalid_file.write_text("{invalid json content")
        
        success = builder.load_graph(str(invalid_file))
        
        assert not success


class TestGraphQuery:
    """测试图谱查询器"""
    
    def test_initialization(self):
        """测试初始化"""
        query = GraphQuery()
        assert query is not None
        assert query.logger is not None
        assert query.graph_builder is not None
    
    def test_query_entity(self):
        """测试查询实体"""
        query = GraphQuery()
        builder = query.graph_builder
        entity = Entity("Python", EntityType.LANGUAGE)
        builder.add_entity(entity)
        
        result = query.query_entity("Python")
        
        assert result is not None
        assert len(result.entities) == 1
        assert result.entities[0].text == "Python"
    
    def test_query_by_type(self):
        """测试按类型查询"""
        query = GraphQuery()
        builder = query.graph_builder
        
        entity1 = Entity("Python", EntityType.LANGUAGE)
        entity2 = Entity("Django", EntityType.FRAMEWORK)
        
        builder.add_entity(entity1)
        builder.add_entity(entity2)
        
        result = query.query_by_type(EntityType.LANGUAGE)
        
        assert len(result.entities) == 1
        assert result.entities[0].entity_type == EntityType.LANGUAGE
    
    def test_query_relations(self):
        """测试查询关系"""
        query = GraphQuery()
        builder = query.graph_builder
        
        entity1 = Entity("Python", EntityType.LANGUAGE)
        entity2 = Entity("Django", EntityType.FRAMEWORK)
        
        builder.add_entity(entity1)
        builder.add_entity(entity2)
        
        relation = Relation(entity1, entity2, RelationType.USES)
        builder.add_relation(relation)
        
        result = query.query_relations("Python")
        
        assert len(result.relations) == 1
        # relation_type 应为 RelationType 枚举（与 entity_type 一致），
        # 而非字符串；否则下游 relation.relation_type.value 会报
        # 'str' object has no attribute 'value'
        assert result.relations[0].relation_type == RelationType.USES
        # 枚举具备 .value 属性，可被 agent_tools 安全格式化
        assert result.relations[0].relation_type.value == "uses"

    def test_query_entity_relations_are_enum(self):
        """回归：query_entity 返回的关系 relation_type 必须是枚举。

        历史 bug：图中存的是字符串，query_entity 直接把字符串塞进
        Relation.relation_type，导致 agent_tools 格式化时
        relation.relation_type.value 抛 'str' object has no attribute 'value'。
        """
        query = GraphQuery()
        builder = query.graph_builder
        e1 = Entity("DNS", EntityType.CONCEPT)
        e2 = Entity("Cloudflare", EntityType.TECHNOLOGY)
        builder.add_entity(e1)
        builder.add_entity(e2)
        builder.add_relation(Relation(e1, e2, RelationType.PART_OF))

        result = query.query_entity("DNS")
        assert len(result.relations) >= 1
        for rel in result.relations:
            # 必须是枚举且可取 .value（模拟 agent_tools 的格式化路径）
            assert isinstance(rel.relation_type, RelationType)
            _ = rel.relation_type.value  # 不应抛异常

    def test_agent_tools_knowledge_graph_query_no_crash(self):
        """回归：/graph-query 端到端不再因 .value 报错。"""
        from agent_tools import knowledge_graph_query

        query = GraphQuery()
        builder = query.graph_builder
        e1 = Entity("DNS", EntityType.CONCEPT)
        e2 = Entity("Cloudflare", EntityType.TECHNOLOGY)
        builder.add_entity(e1)
        builder.add_entity(e2)
        builder.add_relation(Relation(e1, e2, RelationType.PART_OF))

        # knowledge_graph_query 内部会重新获取全局 GraphQuery 单例，
        # 这里直接调用，确保格式化关系时不抛 'str' has no attribute 'value'。
        out = knowledge_graph_query("DNS", "entity")
        assert not out.startswith("[错误]"), out

    def test_query_neighbors(self):
        """测试查询邻居"""
        query = GraphQuery()
        builder = query.graph_builder
        
        entity1 = Entity("Python", EntityType.LANGUAGE)
        entity2 = Entity("Django", EntityType.FRAMEWORK)
        entity3 = Entity("Flask", EntityType.FRAMEWORK)
        
        builder.add_entity(entity1)
        builder.add_entity(entity2)
        builder.add_entity(entity3)
        
        relation = Relation(entity1, entity2, RelationType.USES)
        builder.add_relation(relation)
        
        result = query.query_neighbors("Python")
        
        assert len(result.entities) == 1
        assert result.entities[0].text == "Django"
    
    def test_query_path(self):
        """测试查询路径"""
        query = GraphQuery()
        builder = query.graph_builder
        
        entity1 = Entity("Python", EntityType.LANGUAGE)
        entity2 = Entity("Django", EntityType.FRAMEWORK)
        entity3 = Entity("Flask", EntityType.FRAMEWORK)
        
        builder.add_entity(entity1)
        builder.add_entity(entity2)
        builder.add_entity(entity3)
        
        relation1 = Relation(entity1, entity2, RelationType.USES)
        relation2 = Relation(entity2, entity3, RelationType.EXTENDS)
        
        builder.add_relation(relation1)
        builder.add_relation(relation2)
        
        result = query.query_path("Python", "Flask")
        
        assert result.confidence > 0
        assert len(result.entities) == 3
    
    def test_query_similar(self):
        """测试查询相似实体"""
        query = GraphQuery()
        builder = query.graph_builder
        
        entity1 = Entity("Python", EntityType.LANGUAGE)
        entity2 = Entity("Django", EntityType.FRAMEWORK)
        entity3 = Entity("Flask", EntityType.FRAMEWORK)
        
        builder.add_entity(entity1)
        builder.add_entity(entity2)
        builder.add_entity(entity3)
        
        relation1 = Relation(entity1, entity2, RelationType.USES)
        relation2 = Relation(entity1, entity3, RelationType.USES)
        
        builder.add_relation(relation1)
        builder.add_relation(relation2)
        
        result = query.query_similar("Django")
        
        assert result is not None
        assert isinstance(result.entities, list)
    
    def test_get_graph_summary(self):
        """测试获取图谱摘要"""
        query = GraphQuery()
        
        summary = query.get_graph_summary()
        
        assert summary is not None
        assert 'is_available' in summary
        assert 'statistics' in summary
    
    def test_query_result_to_dict(self):
        """测试查询结果转换为字典"""
        entity = Entity("Python", EntityType.LANGUAGE)
        result = QueryResult(
            entities=[entity],
            relations=[],
            confidence=0.9,
            explanation="Test result"
        )
        
        result_dict = result.to_dict()
        
        assert result_dict['entities'][0]['text'] == "Python"
        assert result_dict['confidence'] == 0.9
        assert result_dict['explanation'] == "Test result"
    
    def test_query_entity_not_found(self):
        """测试查询不存在的实体"""
        query = GraphQuery()
        builder = query.graph_builder
        entity = Entity("Test", EntityType.CONCEPT)
        builder.add_entity(entity)
        
        result = query.query_entity("NonExistentEntity")
        
        assert result is not None
        assert len(result.entities) == 0
        assert result.confidence == 0.0
    
    def test_query_relations_not_found(self):
        """测试查询不存在的实体关系"""
        query = GraphQuery()
        builder = query.graph_builder
        entity = Entity("Test", EntityType.CONCEPT)
        builder.add_entity(entity)
        
        result = query.query_relations("NonExistentEntity")
        
        assert len(result.entities) == 0
        assert result.confidence == 0.0
    
    def test_query_relations_with_relation_filter(self):
        """测试带关系类型过滤的关系查询"""
        query = GraphQuery()
        builder = query.graph_builder
        
        entity1 = Entity("Python", EntityType.LANGUAGE)
        entity2 = Entity("Django", EntityType.FRAMEWORK)
        entity3 = Entity("Flask", EntityType.FRAMEWORK)
        
        builder.add_entity(entity1)
        builder.add_entity(entity2)
        builder.add_entity(entity3)
        
        relation1 = Relation(entity1, entity2, RelationType.USES)
        relation2 = Relation(entity2, entity3, RelationType.EXTENDS)
        
        builder.add_relation(relation1)
        builder.add_relation(relation2)
        
        result = query.query_relations("Python", "uses")
        
        assert len(result.relations) >= 1
    
    def test_query_neighbors_not_found(self):
        """测试查询不存在的实体邻居"""
        query = GraphQuery()
        builder = query.graph_builder
        entity = Entity("Test", EntityType.CONCEPT)
        builder.add_entity(entity)
        
        result = query.query_neighbors("NonExistentEntity")
        
        assert len(result.entities) == 0
        assert result.confidence == 0.0
    
    def test_query_path_not_found(self):
        """测试查询不存在的路径"""
        query = GraphQuery()
        builder = query.graph_builder
        entity = Entity("Test", EntityType.CONCEPT)
        builder.add_entity(entity)
        
        result = query.query_path("NonExistent1", "NonExistent2")
        
        assert result.confidence == 0.0
    
    def test_query_similar_not_found(self):
        """测试查询不存在的相似实体"""
        query = GraphQuery()
        builder = query.graph_builder
        entity = Entity("Test", EntityType.CONCEPT)
        builder.add_entity(entity)
        
        result = query.query_similar("NonExistentEntity")
        
        assert len(result.entities) == 0
    
    def test_query_similar_no_common_neighbors(self):
        """测试没有共同邻居的相似实体查询"""
        query = GraphQuery()
        builder = query.graph_builder
        
        entity1 = Entity("Python", EntityType.LANGUAGE)
        entity2 = Entity("Django", EntityType.FRAMEWORK)
        entity3 = Entity("Flask", EntityType.FRAMEWORK)
        
        builder.add_entity(entity1)
        builder.add_entity(entity2)
        builder.add_entity(entity3)
        
        # 只连接 entity1 和 entity2
        relation = Relation(entity1, entity2, RelationType.USES)
        builder.add_relation(relation)
        
        result = query.query_similar("Django")
        
        assert result is not None
        assert isinstance(result.entities, list)
    
    def test_query_entity_with_existing_document(self):
        """测试查询已有文档的实体"""
        query = GraphQuery()
        builder = query.graph_builder
        
        text = "Python is a programming language."
        success = builder.add_document(text, "doc1", "text")
        
        assert success
        
        result = query.query_entity("Python")
        
        assert len(result.entities) == 1
    
    def test_query_by_type_multiple_entities(self):
        """测试按类型查询多个实体"""
        query = GraphQuery()
        builder = query.graph_builder
        
        entity1 = Entity("Python", EntityType.LANGUAGE)
        entity2 = Entity("Java", EntityType.LANGUAGE)
        entity3 = Entity("Django", EntityType.FRAMEWORK)
        
        builder.add_entity(entity1)
        builder.add_entity(entity2)
        builder.add_entity(entity3)
        
        result = query.query_by_type(EntityType.LANGUAGE)
        
        assert len(result.entities) == 2
        assert all(e.entity_type == EntityType.LANGUAGE for e in result.entities)
