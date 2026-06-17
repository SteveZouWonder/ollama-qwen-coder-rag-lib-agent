#!/usr/bin/env python3
"""
实体提取器 - 从文本中提取实体和关系
"""
import re
import logging
from typing import List, Set, Dict, Tuple, Optional
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class EntityType(Enum):
    """实体类型"""
    PERSON = "person"
    ORGANIZATION = "organization"
    LOCATION = "location"
    CONCEPT = "concept"
    TECHNOLOGY = "technology"
    TOOL = "tool"
    LANGUAGE = "language"
    FRAMEWORK = "framework"
    OTHER = "other"


class RelationType(Enum):
    """关系类型"""
    IS_A = "is_a"
    PART_OF = "part_of"
    USES = "uses"
    IMPLEMENTS = "implements"
    EXTENDS = "extends"
    RELATED_TO = "related_to"
    DEFINES = "defines"
    EXAMPLES = "examples"
    SIMILAR_TO = "similar_to"
    OTHER = "other"


@dataclass
class Entity:
    """实体"""
    text: str
    entity_type: EntityType
    confidence: float = 1.0
    context: str = ""
    metadata: Dict = field(default_factory=dict)
    
    def __hash__(self):
        return hash((self.text.lower(), self.entity_type))
    
    def __eq__(self, other):
        if not isinstance(other, Entity):
            return False
        return (self.text.lower() == other.text.lower() and 
                self.entity_type == other.entity_type)
    
    def to_dict(self) -> Dict:
        """转换为字典"""
        return {
            'text': self.text,
            'entity_type': self.entity_type.value,
            'confidence': self.confidence,
            'context': self.context,
            'metadata': self.metadata
        }


@dataclass
class Relation:
    """关系"""
    source: Entity
    target: Entity
    relation_type: RelationType
    confidence: float = 1.0
    evidence: str = ""
    
    def __hash__(self):
        return hash((self.source, self.target, self.relation_type))
    
    def __eq__(self, other):
        if not isinstance(other, Relation):
            return False
        return (self.source == other.source and 
                self.target == other.target and 
                self.relation_type == other.relation_type)
    
    def to_dict(self) -> Dict:
        """转换为字典"""
        return {
            'source': self.source.to_dict(),
            'target': self.target.to_dict(),
            'relation_type': self.relation_type.value,
            'confidence': self.confidence,
            'evidence': self.evidence
        }


class EntityExtractor:
    """实体提取器"""
    
    def __init__(self):
        self.logger = logger
        self._init_patterns()
    
    def _init_patterns(self):
        """初始化提取模式"""
        # 技术术语模式
        self.technology_patterns = {
            EntityType.TECHNOLOGY: [
                r'\b(?:AI|artificial intelligence|machine learning|deep learning)\b',
                r'\b(?:blockchain|cryptocurrency)\b',
                r'\b(?:cloud computing|big data)\b',
            ],
            EntityType.LANGUAGE: [
                r'\b(?:Python|Java|JavaScript|C\+\+|Go|Rust|TypeScript)\b',
                r'\b(?:HTML|CSS|SQL|NoSQL)\b',
            ],
            EntityType.FRAMEWORK: [
                r'\b(?:React|Vue|Angular|Django|Flask|Spring)\b',
                r'\b(?:TensorFlow|PyTorch|scikit-learn)\b',
                r'\b(?:Express|FastAPI|Docker)\b',
            ],
            EntityType.TOOL: [
                r'\b(?:Git|Docker|Kubernetes|Jenkins)\b',
                r'\b(?:Linux|Unix|Windows)\b',
                r'\b(?:Ollama|LlamaIndex)\b',
            ]
        }
        
        # 关系模式
        self.relation_patterns = [
            (r'(\w+)\s+is\s+a\s+(\w+)', RelationType.IS_A),
            (r'(\w+)\s+uses\s+(\w+)', RelationType.USES),
            (r'(\w+)\s+extends\s+(\w+)', RelationType.EXTENDS),
            (r'(\w+)\s+implements\s+(\w+)', RelationType.IMPLEMENTS),
            (r'(\w+)\s+is\s+part\s+of\s+(\w+)', RelationType.PART_OF),
            (r'(\w+)\s+related\s+to\s+(\w+)', RelationType.RELATED_TO),
        ]
    
    def extract_entities(self, text: str) -> List[Entity]:
        """从文本中提取实体"""
        entities = []
        text_lower = text.lower()
        
        # 基于规则的实体提取
        for entity_type, patterns in self.technology_patterns.items():
            for pattern in patterns:
                matches = re.finditer(pattern, text, re.IGNORECASE)
                for match in matches:
                    entity_text = match.group()
                    # 避免重复
                    if not any(e.text.lower() == entity_text.lower() for e in entities):
                        entity = Entity(
                            text=entity_text,
                            entity_type=entity_type,
                            confidence=0.8,
                            context=text[max(0, match.start()-50):match.end()+50]
                        )
                        entities.append(entity)
        
        # 提取专有名词（大写开头的词）
        proper_nouns = re.findall(r'\b([A-Z][a-zA-Z]+)\b', text)
        for noun in set(proper_nouns):  # 去重
            # 排除已提取的技术术语
            if not any(e.text == noun for e in entities):
                entity = Entity(
                    text=noun,
                    entity_type=EntityType.CONCEPT,
                    confidence=0.6,
                    context=""
                )
                entities.append(entity)
        
        return entities
    
    def extract_relations(self, text: str, entities: List[Entity]) -> List[Relation]:
        """从文本中提取关系"""
        relations = []
        entity_names = {e.text.lower(): e for e in entities}
        
        # 基于模式的关系提取
        for pattern, relation_type in self.relation_patterns:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                source_text = match.group(1)
                target_text = match.group(2)
                
                source = entity_names.get(source_text.lower())
                target = entity_names.get(target_text.lower())
                
                if source and target and source != target:
                    relation = Relation(
                        source=source,
                        target=target,
                        relation_type=relation_type,
                        confidence=0.7,
                        evidence=match.group(0)
                    )
                    relations.append(relation)
        
        # 基于共现的关系提取
        sentences = re.split(r'[.!?]', text)
        for sentence in sentences:
            sentence_entities = []
            for entity in entities:
                if entity.text.lower() in sentence.lower():
                    sentence_entities.append(entity)
            
            # 如果句子中包含多个实体，添加 RELATED_TO 关系
            if len(sentence_entities) > 1:
                for i, entity1 in enumerate(sentence_entities):
                    for entity2 in sentence_entities[i+1:]:
                        relation = Relation(
                            source=entity1,
                            target=entity2,
                            relation_type=RelationType.RELATED_TO,
                            confidence=0.5,
                            evidence=sentence.strip()
                        )
                        relations.append(relation)
        
        return relations
    
    def extract_code_relations(self, code: str, entities: List[Entity]) -> List[Relation]:
        """从代码中提取关系"""
        relations = []
        
        # 提取导入关系 (USES)
        import_pattern = r'(?:import|from)\s+(\w+)'
        for match in re.finditer(import_pattern, code):
            imported_module = match.group(1)
            imported_entity = None
            for entity in entities:
                if entity.text.lower() == imported_module.lower():
                    imported_entity = entity
                    break
            
            if imported_entity:
                # 找到函数或类作为源实体
                function_pattern = r'def\s+(\w+)'
                class_pattern = r'class\s+(\w+)'
                
                for func_match in re.finditer(function_pattern, code):
                    func_name = func_match.group(1)
                    func_entity = None
                    for entity in entities:
                        if entity.text == func_name:
                            func_entity = entity
                            break
                    
                    if func_entity:
                        relation = Relation(
                            source=func_entity,
                            target=imported_entity,
                            relation_type=RelationType.USES,
                            confidence=0.9,
                            evidence=func_match.group(0)
                        )
                        relations.append(relation)
        
        # 提取继承关系 (EXTENDS)
        class_pattern = r'class\s+(\w+)\s*(?:\(([^)]+)\))?'
        for match in re.finditer(class_pattern, code):
            class_name = match.group(1)
            class_entity = None
            for entity in entities:
                if entity.text == class_name:
                    class_entity = entity
                    break
            
            if class_entity and match.group(2):  # 有继承
                parents = match.group(2).split(',')
                for parent in parents:
                    parent = parent.strip()
                    parent_entity = None
                    for entity in entities:
                        if entity.text == parent:
                            parent_entity = entity
                            break
                    
                    if parent_entity:
                        relation = Relation(
                            source=class_entity,
                            target=parent_entity,
                            relation_type=RelationType.EXTENDS,
                            confidence=0.9,
                            evidence=match.group(0)
                        )
                        relations.append(relation)
        
        return relations
    
    def extract_from_document(self, text: str, doc_type: str = "text") -> Tuple[List[Entity], List[Relation]]:
        """从文档中提取实体和关系"""
        entities = []
        relations = []
        
        if doc_type == "code":
            # 从代码中提取
            entities = self._extract_code_entities(text)
            relations = self.extract_code_relations(text, entities)
        else:
            # 从文本中提取
            entities = self.extract_entities(text)
            relations = self.extract_relations(text, entities)
        
        return entities, relations
    
    def _extract_code_entities(self, code: str) -> List[Entity]:
        """从代码中提取实体"""
        entities = []
        
        # 提取函数名
        function_pattern = r'def\s+(\w+)'
        for match in re.finditer(function_pattern, code):
            entities.append(Entity(
                text=match.group(1),
                entity_type=EntityType.CONCEPT,
                confidence=0.9,
                context=match.group(0)
            ))
        
        # 提取类名
        class_pattern = r'class\s+(\w+)'
        for match in re.finditer(class_pattern, code):
            entities.append(Entity(
                text=match.group(1),
                entity_type=EntityType.CONCEPT,
                confidence=0.9,
                context=match.group(0)
            ))
        
        # 提取导入的模块
        import_pattern = r'(?:import|from)\s+(\w+)'
        for match in re.finditer(import_pattern, code):
            imported = match.group(1)
            entities.append(Entity(
                text=imported,
                entity_type=EntityType.TOOL,
                confidence=0.8,
                context=match.group(0)
            ))
        
        return entities


# 全局实体提取器实例
_entity_extractor = None

def get_entity_extractor() -> EntityExtractor:
    """获取全局实体提取器实例"""
    global _entity_extractor
    if _entity_extractor is None:
        _entity_extractor = EntityExtractor()
    return _entity_extractor
