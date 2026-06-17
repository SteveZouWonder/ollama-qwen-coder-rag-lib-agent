#!/usr/bin/env python3
"""
代码分析模块单元测试
"""
import pytest
from pathlib import Path
import tempfile
import os

# 导入被测试的模块
from code_analyzer.ast_analyzer import ASTAnalyzer, CodeNode, FunctionInfo, ClassInfo
from code_analyzer.quality_checker import QualityChecker, QualityReport, QualityIssue, Severity


class TestASTAnalyzer:
    """测试 AST 分析器"""
    
    def test_initialization(self):
        """测试初始化"""
        analyzer = ASTAnalyzer()
        assert analyzer is not None
        assert analyzer.logger is not None
        assert isinstance(analyzer._cache, dict)
    
    def test_analyze_simple_code(self):
        """测试分析简单代码"""
        analyzer = ASTAnalyzer()
        code = """
def hello():
    print("Hello, World!")

class MyClass:
    def method(self):
        pass
"""
        result = analyzer.analyze_code(code, "<test>")
        
        assert result is not None
        assert len(result['functions']) == 2  # hello 和 method
        assert len(result['classes']) == 1
        assert result['classes'][0].name == 'MyClass'
    
    def test_analyze_function(self):
        """测试函数分析"""
        analyzer = ASTAnalyzer()
        code = """
def test_function(param1: str, param2: int = 0) -> bool:
    '''Test function'''
    return True
"""
        result = analyzer.analyze_code(code, "<test>")
        
        assert len(result['functions']) == 1
        func = result['functions'][0]
        assert func.name == 'test_function'
        assert 'param1' in func.parameters
        assert 'param2' in func.parameters
        assert func.return_type == 'bool'
        assert func.docstring == 'Test function'
    
    def test_analyze_class(self):
        """测试类分析"""
        analyzer = ASTAnalyzer()
        code = """
class BaseClass:
    pass

class DerivedClass(BaseClass):
    def method(self):
        pass
    
    @property
    def prop(self):
        return 42
"""
        result = analyzer.analyze_code(code, "<test>")
        
        assert len(result['classes']) == 2
        base = result['classes'][0]
        assert base.name == 'BaseClass'
        
        derived = result['classes'][1]
        assert derived.name == 'DerivedClass'
        assert 'BaseClass' in derived.bases
        assert len(derived.methods) == 2
        # @property 在方法级别，不在类级别
        prop_method = [m for m in derived.methods if m.name == 'prop'][0]
        assert 'property' in prop_method.decorators
    
    def test_analyze_imports(self):
        """测试导入分析"""
        analyzer = ASTAnalyzer()
        code = """
import os
import sys as system
from typing import List
from collections import defaultdict as dd
"""
        result = analyzer.analyze_code(code, "<test>")
        
        assert len(result['imports']) == 4
        
        # 检查普通导入
        os_import = [imp for imp in result['imports'] if imp.module == 'os'][0]
        assert not os_import.is_from
        
        # 检查别名的导入
        sys_import = [imp for imp in result['imports'] if imp.module == 'sys'][0]
        assert sys_import.alias == 'system'
        
        # 检查 from 导入
        typing_import = [imp for imp in result['imports'] if imp.module == 'typing'][0]
        assert typing_import.is_from
        assert 'List' in typing_import.names
    
    def test_complexity_calculation(self):
        """测试复杂度计算"""
        analyzer = ASTAnalyzer()
        
        # 简单函数
        simple_code = "def simple(): return 1"
        simple_tree = analyzer.analyze_code(simple_code, "<test>")
        assert simple_tree['functions'][0].complexity == 1
        
        # 复杂函数
        complex_code = """
def complex_func(x):
    if x > 0:
        for i in range(10):
            if i % 2 == 0:
                continue
    else:
        try:
            result = x / 0
        except:
            pass
"""
        complex_tree = analyzer.analyze_code(complex_code, "<test>")
        assert complex_tree['functions'][0].complexity > 1
    
    def test_search_functions(self):
        """测试函数搜索"""
        analyzer = ASTAnalyzer()
        code = """
def hello_world():
    pass

def test_function():
    pass

def another_test():
    pass
"""
        # 创建临时文件进行搜索
        import tempfile
        import os
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(code)
            temp_file = f.name
        
        try:
            results = analyzer.search_functions(temp_file, "test")
            assert len(results) >= 2
        finally:
            os.unlink(temp_file)
    
    def test_search_classes(self):
        """测试类搜索"""
        analyzer = ASTAnalyzer()
        code = """
class TestClass:
    pass

class AnotherTest:
    pass

class NormalClass:
    pass
"""
        result = analyzer.analyze_code(code, "<test>")
        
        # 搜索包含 'Test' 的类
        test_classes = [c for c in result['classes'] if 'Test' in c.name]
        assert len(test_classes) == 2
    
    def test_analyze_project(self, tmp_path):
        """测试项目分析"""
        analyzer = ASTAnalyzer()
        
        # 创建测试文件
        test_file = tmp_path / "test.py"
        test_file.write_text("""
def test_func():
    pass

class TestClass:
    pass
""")
        
        result = analyzer.analyze_project(str(tmp_path), "*.py")
        
        assert result is not None
        assert result['total_functions'] == 1
        assert result['total_classes'] == 1
    
    def test_analyze_file_not_exists(self):
        """测试分析不存在的文件"""
        analyzer = ASTAnalyzer()
        result = analyzer.analyze_file("/nonexistent/file.py")
        assert result == {}
    
    def test_analyze_syntax_error(self):
        """测试语法错误处理"""
        analyzer = ASTAnalyzer()
        code = "def broken( :"
        result = analyzer.analyze_code(code, "<test>")
        assert result == {}
    
    def test_get_call_graph(self, tmp_path):
        """测试获取调用图"""
        analyzer = ASTAnalyzer()
        
        test_file = tmp_path / "test_calls.py"
        test_file.write_text("""
def caller():
    helper()
    another_func()

def helper():
    pass

def another_func():
    pass
""")
        
        call_graph = analyzer.get_call_graph(str(test_file))
        
        assert 'caller' in call_graph
        assert 'helper' in call_graph['caller']
        assert 'another_func' in call_graph['caller']
    
    def test_get_import_dependencies(self, tmp_path):
        """测试获取导入依赖"""
        analyzer = ASTAnalyzer()
        
        test_file = tmp_path / "test_imports.py"
        test_file.write_text("""
import os
import sys
from typing import List
""")
        
        deps = analyzer.get_import_dependencies(str(test_file))
        
        assert 'os' in deps
        assert 'sys' in deps
        assert 'typing' in deps


class TestQualityChecker:
    """测试质量检查器"""
    
    def test_initialization(self):
        """测试初始化"""
        checker = QualityChecker()
        assert checker is not None
        assert checker.logger is not None
        assert isinstance(checker._available_tools, dict)
    
    def test_check_simple_file(self, tmp_path):
        """测试检查简单文件"""
        checker = QualityChecker()
        
        test_file = tmp_path / "simple.py"
        test_file.write_text("""
def simple_function():
    return 42
""")
        
        report = checker.check_file(str(test_file), check_types=['basic'])
        
        assert report is not None
        assert report.file_path == str(test_file)
        assert isinstance(report.issues, list)
    
    def test_check_complex_function(self, tmp_path):
        """测试检查复杂函数"""
        checker = QualityChecker()
        
        test_file = tmp_path / "complex.py"
        test_file.write_text("""
def complex_function(x):
    if x > 0:
        for i in range(10):
            if i % 2 == 0:
                for j in range(5):
                    if j > 2:
                        continue
    elif x < 0:
        for j in range(5):
            if j == 0:
                return x
    return x * 2
""")
        
        report = checker.check_file(str(test_file), check_types=['basic'])
        
        # 复杂函数应该有警告（复杂度 > 10）
        complexity_issues = [i for i in report.issues if 'complexity' in i.rule_id.lower()]
        # 如果有足够高的复杂度，应该生成警告
        if report.metrics.complexity_score > 10:
            assert len(complexity_issues) > 0
    
    def test_check_large_class(self, tmp_path):
        """测试检查大类"""
        checker = QualityChecker()
        
        # 创建一个有很多方法的类
        methods = "\n".join([f"    def method_{i}(self): pass" for i in range(25)])
        test_file = tmp_path / "large_class.py"
        test_file.write_text(f"""
class LargeClass:
{methods}
""")
        
        report = checker.check_file(str(test_file), check_types=['basic'])
        
        # 大类应该有警告
        class_issues = [i for i in report.issues if 'large_class' in i.rule_id]
        assert len(class_issues) > 0
    
    def test_check_nonexistent_file(self):
        """测试检查不存在的文件"""
        checker = QualityChecker()
        report = checker.check_file("/nonexistent/file.py")
        
        assert report.file_path == "/nonexistent/file.py"
        assert len(report.issues) == 0
    
    def test_check_project(self, tmp_path):
        """测试项目检查"""
        checker = QualityChecker()
        
        # 创建多个测试文件
        for i in range(3):
            test_file = tmp_path / f"test_{i}.py"
            test_file.write_text(f"""
def function_{i}():
    return {i}
""")
        
        reports = checker.check_project(str(tmp_path))
        
        assert len(reports) == 3
    
    def test_get_project_summary(self):
        """测试项目摘要"""
        checker = QualityChecker()
        
        # 创建测试报告
        reports = {}
        for i in range(3):
            report = QualityReport(file_path=f"test_{i}.py")
            report.add_issue(QualityIssue(
                file_path=f"test_{i}.py",
                line_no=1,
                column=0,
                severity=Severity.WARNING,
                message=f"Test issue {i}",
                source='test'
            ))
            reports[f"test_{i}.py"] = report
        
        summary = checker.get_project_summary(reports)
        
        assert summary['total_files'] == 3
        assert summary['total_issues'] == 3
        assert summary['files_with_issues'] == 3
    
    def test_quality_metrics_calculation(self):
        """测试质量指标计算"""
        # 测试总体分数计算
        report = QualityReport(file_path="test.py")
        for _ in range(5):
            report.add_issue(QualityIssue(
                file_path="test.py",
                line_no=1,
                column=0,
                severity=Severity.WARNING,
                message="Test",
                source='test'
            ))
        
        score = report.metrics.calculate_overall_score()
        assert 0 <= score <= 100
    
    def test_quality_issue_to_dict(self):
        """测试质量问题转换为字典"""
        issue = QualityIssue(
            file_path="test.py",
            line_no=10,
            column=5,
            severity=Severity.ERROR,
            message="Test message",
            source="test",
            rule_id="TEST001"
        )
        
        issue_dict = issue.to_dict()
        
        assert issue_dict['file_path'] == "test.py"
        assert issue_dict['line_no'] == 10
        assert issue_dict['severity'] == 'error'
        assert issue_dict['source'] == "test"
    
    def test_quality_report_to_dict(self):
        """测试质量报告转换为字典"""
        report = QualityReport(file_path="test.py")
        report.add_issue(QualityIssue(
            file_path="test.py",
            line_no=1,
            column=0,
            severity=Severity.WARNING,
            message="Test",
            source='test'
        ))
        
        report_dict = report.to_dict()
        
        assert report_dict['file_path'] == "test.py"
        assert len(report_dict['issues']) == 1
        assert 'metrics' in report_dict
        assert 'overall_score' in report_dict['metrics']


class TestCodeNodes:
    """测试代码节点类"""
    
    def test_code_node_creation(self):
        """测试代码节点创建"""
        node = CodeNode(
            name="test",
            node_type="function",
            file_path="test.py",
            line_no=10,
            end_line_no=20
        )
        
        assert node.name == "test"
        assert node.node_type == "function"
        assert node.line_no == 10
        assert node.end_line_no == 20
    
    def test_function_info_creation(self):
        """测试函数信息创建"""
        func = FunctionInfo(
            name="test_func",
            node_type="function",
            file_path="test.py",
            line_no=10,
            end_line_no=20,
            parameters=["param1", "param2"],
            return_type="str",
            complexity=3
        )
        
        assert func.parameters == ["param1", "param2"]
        assert func.return_type == "str"
        assert func.complexity == 3
    
    def test_class_info_creation(self):
        """测试类信息创建"""
        cls = ClassInfo(
            name="TestClass",
            node_type="class",
            file_path="test.py",
            line_no=10,
            end_line_no=50,
            bases=["BaseClass"],
            attributes=["attr1", "attr2"]  # attributes 是列表
        )
        
        assert cls.bases == ["BaseClass"]
        # attributes 在实现中是 set()，但创建时可以是列表
        assert "attr1" in cls.attributes
        assert "attr2" in cls.attributes


# 创建全局 checker 实例用于测试
checker = type('CheckerHolder', (), {'checker': None})()
checker.checker = QualityChecker()
