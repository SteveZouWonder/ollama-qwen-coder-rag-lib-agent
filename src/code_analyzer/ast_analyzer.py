#!/usr/bin/env python3
"""
AST 语法树分析器 - 深度代码结构分析
"""
import ast
import logging
from pathlib import Path
from typing import List, Dict, Optional, Set, Tuple
from dataclasses import dataclass, field
from collections import defaultdict

logger = logging.getLogger(__name__)


@dataclass
class CodeNode:
    """代码节点基类"""
    name: str
    node_type: str
    file_path: str
    line_no: int
    end_line_no: int
    docstring: Optional[str] = None
    metadata: Dict = field(default_factory=dict)


@dataclass
class FunctionInfo(CodeNode):
    """函数信息"""
    parameters: List[str] = field(default_factory=list)
    return_type: Optional[str] = None
    decorators: List[str] = field(default_factory=list)
    calls: Set[str] = field(default_factory=set)
    complexity: int = 1


@dataclass 
class ClassInfo(CodeNode):
    """类信息"""
    bases: List[str] = field(default_factory=list)
    methods: List[FunctionInfo] = field(default_factory=list)
    attributes: Set[str] = field(default_factory=set)
    decorators: List[str] = field(default_factory=list)


@dataclass
class ImportInfo:
    """导入信息"""
    module: str
    names: List[str]
    alias: Optional[str] = None
    line_no: int = 0
    is_from: bool = False


class ASTAnalyzer:
    """AST 语法树分析器"""
    
    def __init__(self):
        self.logger = logger
        self._cache: Dict[str, Dict] = {}
    
    def analyze_file(self, file_path: str) -> Dict:
        """分析单个文件"""
        file_path = Path(file_path)
        if not file_path.exists():
            self.logger.warning(f"文件不存在: {file_path}")
            return {}
        
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            
            return self.analyze_code(content, str(file_path))
        except Exception as e:
            self.logger.error(f"分析文件失败 {file_path}: {e}")
            return {}
    
    def analyze_code(self, code: str, file_path: str = "<string>") -> Dict:
        """分析代码字符串"""
        try:
            tree = ast.parse(code)
            
            result = {
                'file_path': file_path,
                'imports': [],
                'functions': [],
                'classes': [],
                'globals': set(),
                'complexity': 0
            }
            
            # 收集导入
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        result['imports'].append(ImportInfo(
                            module=alias.name,
                            names=[alias.asname] if alias.asname else [],
                            alias=alias.asname,
                            line_no=node.lineno,
                            is_from=False
                        ))
                elif isinstance(node, ast.ImportFrom):
                    module = node.module or ''
                    for alias in node.names:
                        result['imports'].append(ImportInfo(
                            module=module,
                            names=[alias.name],
                            alias=alias.asname,
                            line_no=node.lineno,
                            is_from=True
                        ))
            
            # 分析函数
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    func_info = self._analyze_function(node, file_path)
                    result['functions'].append(func_info)
                    result['complexity'] += func_info.complexity
            
            # 分析类
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    class_info = self._analyze_class(node, file_path)
                    result['classes'].append(class_info)
            
            # 收集全局变量
            for node in ast.walk(tree):
                if isinstance(node, ast.Assign):
                    for target in node.targets:
                        if isinstance(target, ast.Name):
                            result['globals'].add(target.id)
            
            return result
            
        except SyntaxError as e:
            self.logger.error(f"语法错误: {e}")
            return {}
        except Exception as e:
            self.logger.error(f"分析代码失败: {e}")
            return {}
    
    def _analyze_function(self, node: ast.FunctionDef, file_path: str) -> FunctionInfo:
        """分析函数"""
        # 提取参数
        parameters = []
        for arg in node.args.args:
            parameters.append(arg.arg)
        
        # 提取返回类型
        return_type = None
        if node.returns:
            return_type = ast.unparse(node.returns)
        
        # 提取装饰器
        decorators = []
        for decorator in node.decorator_list:
            decorators.append(ast.unparse(decorator))
        
        # 提取文档字符串
        docstring = ast.get_docstring(node)
        
        # 计算复杂度
        complexity = self._calculate_complexity(node)
        
        # 收集函数调用
        calls = self._collect_function_calls(node)
        
        return FunctionInfo(
            name=node.name,
            node_type='function',
            file_path=file_path,
            line_no=node.lineno,
            end_line_no=node.end_lineno or node.lineno,
            docstring=docstring,
            parameters=parameters,
            return_type=return_type,
            decorators=decorators,
            calls=calls,
            complexity=complexity,
            metadata={
                'is_async': isinstance(node, ast.AsyncFunctionDef),
                'is_method': False  # 在类分析时设置
            }
        )
    
    def _analyze_class(self, node: ast.ClassDef, file_path: str) -> ClassInfo:
        """分析类"""
        # 提取基类
        bases = []
        for base in node.bases:
            bases.append(ast.unparse(base))
        
        # 提取装饰器
        decorators = []
        for decorator in node.decorator_list:
            decorators.append(ast.unparse(decorator))
        
        # 提取文档字符串
        docstring = ast.get_docstring(node)
        
        # 分析方法
        methods = []
        attributes = set()
        
        for item in node.body:
            if isinstance(item, ast.FunctionDef):
                func_info = self._analyze_function(item, file_path)
                func_info.metadata['is_method'] = True
                methods.append(func_info)
            elif isinstance(item, ast.Assign):
                for target in item.targets:
                    if isinstance(target, ast.Name):
                        attributes.add(target.id)
        
        return ClassInfo(
            name=node.name,
            node_type='class',
            file_path=file_path,
            line_no=node.lineno,
            end_line_no=node.end_lineno or node.lineno,
            docstring=docstring,
            bases=bases,
            methods=methods,
            attributes=attributes,
            decorators=decorators,
            metadata={
                'method_count': len(methods),
                'attribute_count': len(attributes)
            }
        )
    
    def _calculate_complexity(self, node: ast.AST) -> int:
        """计算圈复杂度"""
        complexity = 1  # 基础复杂度
        
        for child in ast.walk(node):
            if isinstance(child, (ast.If, ast.While, ast.For, ast.AsyncFor)):
                complexity += 1
            elif isinstance(child, ast.ExceptHandler):
                complexity += 1
            elif isinstance(child, ast.BoolOp):
                complexity += len(child.values) - 1
            elif isinstance(child, (ast.And, ast.Or)):
                complexity += 1
        
        return complexity
    
    def _collect_function_calls(self, node: ast.AST) -> Set[str]:
        """收集函数调用"""
        calls = set()
        
        for child in ast.walk(node):
            if isinstance(child, ast.Call):
                func = child.func
                if isinstance(func, ast.Name):
                    calls.add(func.id)
                elif isinstance(func, ast.Attribute):
                    calls.add(ast.unparse(func))
        
        return calls
    
    def search_functions(self, file_path: str, pattern: str, 
                       search_by: str = 'name') -> List[FunctionInfo]:
        """搜索函数"""
        analysis = self.analyze_file(file_path)
        results = []
        
        for func in analysis.get('functions', []):
            match = False
            if search_by == 'name' and pattern in func.name:
                match = True
            elif search_by == 'parameter' and any(pattern in param for param in func.parameters):
                match = True
            elif search_by == 'return' and func.return_type and pattern in func.return_type:
                match = True
            
            if match:
                results.append(func)
        
        return results
    
    def search_classes(self, file_path: str, pattern: str,
                     search_by: str = 'name') -> List[ClassInfo]:
        """搜索类"""
        analysis = self.analyze_file(file_path)
        results = []
        
        for cls in analysis.get('classes', []):
            match = False
            if search_by == 'name' and pattern in cls.name:
                match = True
            elif search_by == 'base' and any(pattern in base for base in cls.bases):
                match = True
            elif search_by == 'method' and any(pattern in method.name for method in cls.methods):
                match = True
            
            if match:
                results.append(cls)
        
        return results
    
    def get_call_graph(self, file_path: str) -> Dict[str, Set[str]]:
        """获取函数调用图"""
        analysis = self.analyze_file(file_path)
        call_graph = defaultdict(set)
        
        for func in analysis.get('functions', []):
            for called_func in func.calls:
                call_graph[func.name].add(called_func)
        
        # 处理类方法
        for cls in analysis.get('classes', []):
            for method in cls.methods:
                for called_func in method.calls:
                    # 使用类名.方法名的格式
                    call_graph[f"{cls.name}.{method.name}"].add(called_func)
        
        return dict(call_graph)
    
    def get_import_dependencies(self, file_path: str) -> Dict[str, List[str]]:
        """获取导入依赖"""
        analysis = self.analyze_file(file_path)
        dependencies = defaultdict(list)
        
        for imp in analysis.get('imports', []):
            if imp.is_from:
                dependencies[imp.module].extend(imp.names)
            else:
                dependencies[imp.module] = []
        
        return dict(dependencies)
    
    def analyze_project(self, project_path: str, pattern: str = "*.py") -> Dict:
        """分析整个项目"""
        project_path = Path(project_path)
        if not project_path.exists():
            return {}
        
        results = {
            'project_path': str(project_path),
            'files': [],
            'total_functions': 0,
            'total_classes': 0,
            'total_complexity': 0,
            'import_graph': defaultdict(set),
            'call_graph': defaultdict(set)
        }
        
        # 收集所有 Python 文件
        python_files = list(project_path.rglob(pattern))
        
        for file_path in python_files:
            # 跳过虚拟环境和测试目录
            if 'venv' in str(file_path) or '__pycache__' in str(file_path):
                continue
            
            analysis = self.analyze_file(str(file_path))
            if not analysis:
                continue
            
            results['files'].append(analysis)
            results['total_functions'] += len(analysis.get('functions', []))
            results['total_classes'] += len(analysis.get('classes', []))
            results['total_complexity'] += analysis.get('complexity', 0)
            
            # 构建导入图
            for imp in analysis.get('imports', []):
                results['import_graph'][str(file_path)].add(imp.module)
        
        return results


# 全局 AST 分析器实例
_ast_analyzer = None

def get_ast_analyzer() -> ASTAnalyzer:
    """获取全局 AST 分析器实例"""
    global _ast_analyzer
    if _ast_analyzer is None:
        _ast_analyzer = ASTAnalyzer()
    return _ast_analyzer
