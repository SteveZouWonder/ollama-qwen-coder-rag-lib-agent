#!/usr/bin/env python3
"""
知识图谱模块 - 基于文档构建知识图谱，增强推理能力
"""
from .graph_builder import KnowledgeGraphBuilder, get_graph_builder
from .entity_extractor import EntityExtractor, Entity, Relation
from .graph_query import GraphQuery, get_graph_query

__all__ = [
    'KnowledgeGraphBuilder',
    'EntityExtractor',
    'Entity',
    'Relation',
    'GraphQuery',
    'get_graph_query',
    'get_graph_builder'
]
