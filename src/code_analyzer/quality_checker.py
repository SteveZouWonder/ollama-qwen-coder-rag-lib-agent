#!/usr/bin/env python3
"""
代码质量检查器 - 集成多种静态分析工具
"""
import logging
import subprocess
import json
from pathlib import Path
from typing import List, Dict, Optional, Any
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class Severity(Enum):
    """问题严重程度"""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class QualityIssue:
    """代码质量问题"""
    file_path: str
    line_no: int
    column: int
    severity: Severity
    message: str
    source: str  # 来源工具
    rule_id: Optional[str] = None
    fix_suggestion: Optional[str] = None
    
    def to_dict(self) -> Dict:
        """转换为字典"""
        return {
            'file_path': self.file_path,
            'line_no': self.line_no,
            'column': self.column,
            'severity': self.severity.value,
            'message': self.message,
            'source': self.source,
            'rule_id': self.rule_id,
            'fix_suggestion': self.fix_suggestion
        }


@dataclass
class QualityMetrics:
    """代码质量指标"""
    total_issues: int = 0
    critical_issues: int = 0
    error_issues: int = 0
    warning_issues: int = 0
    info_issues: int = 0
    complexity_score: float = 0.0
    maintainability_index: float = 0.0
    test_coverage: float = 0.0
    
    def calculate_overall_score(self) -> float:
        """计算总体质量分数（0-100）"""
        # 基础分100
        score = 100.0
        
        # 根据问题严重程度扣分
        score -= self.critical_issues * 10
        score -= self.error_issues * 5
        score -= self.warning_issues * 2
        score -= self.info_issues * 1
        
        # 考虑复杂度
        if self.complexity_score > 20:
            score -= (self.complexity_score - 20) * 2
        
        # 考虑测试覆盖率
        if self.test_coverage < 80:
            score -= (80 - self.test_coverage) * 0.5
        
        return max(0.0, min(100.0, score))


@dataclass
class QualityReport:
    """代码质量报告"""
    file_path: str
    issues: List[QualityIssue] = field(default_factory=list)
    metrics: QualityMetrics = field(default_factory=QualityMetrics)
    summary: str = ""
    timestamp: str = ""
    
    def add_issue(self, issue: QualityIssue):
        """添加问题"""
        self.issues.append(issue)
        
        # 更新指标
        self.metrics.total_issues += 1
        if issue.severity == Severity.CRITICAL:
            self.metrics.critical_issues += 1
        elif issue.severity == Severity.ERROR:
            self.metrics.error_issues += 1
        elif issue.severity == Severity.WARNING:
            self.metrics.warning_issues += 1
        elif issue.severity == Severity.INFO:
            self.metrics.info_issues += 1
    
    def to_dict(self) -> Dict:
        """转换为字典"""
        return {
            'file_path': self.file_path,
            'issues': [issue.to_dict() for issue in self.issues],
            'metrics': {
                'total_issues': self.metrics.total_issues,
                'critical_issues': self.metrics.critical_issues,
                'error_issues': self.metrics.error_issues,
                'warning_issues': self.metrics.warning_issues,
                'info_issues': self.metrics.info_issues,
                'complexity_score': self.metrics.complexity_score,
                'maintainability_index': self.metrics.maintainability_index,
                'test_coverage': self.metrics.test_coverage,
                'overall_score': self.metrics.calculate_overall_score()
            },
            'summary': self.summary,
            'timestamp': self.timestamp
        }


class QualityChecker:
    """代码质量检查器"""
    
    def __init__(self):
        self.logger = logger
        self._check_available_tools()
    
    def _check_available_tools(self):
        """检查可用的检查工具"""
        self._available_tools = {}
        
        # 检查 pylint
        self._available_tools['pylint'] = self._is_tool_available('pylint')
        
        # 检查 bandit (安全检查)
        self._available_tools['bandit'] = self._is_tool_available('bandit')
        
        # 检查 radon (复杂度分析)
        self._available_tools['radon'] = self._is_tool_available('radon')
        
        self.logger.info(f"可用工具: {list(self._available_tools.keys())}")
    
    def _is_tool_available(self, tool_name: str) -> bool:
        """检查工具是否可用"""
        try:
            result = subprocess.run(
                ['python', '-m', tool_name, '--version'],
                capture_output=True,
                timeout=5
            )
            return result.returncode == 0
        except Exception:
            return False
    
    def check_file(self, file_path: str, 
                  check_types: Optional[List[str]] = None) -> QualityReport:
        """检查单个文件"""
        file_path = Path(file_path)
        if not file_path.exists():
            self.logger.warning(f"文件不存在: {file_path}")
            return QualityReport(file_path=str(file_path))
        
        report = QualityReport(file_path=str(file_path))
        
        if check_types is None:
            check_types = ['basic', 'complexity']
        
        # 基础 AST 检查
        if 'basic' in check_types:
            self._basic_ast_check(file_path, report)
        
        # pylint 检查
        if 'pylint' in check_types and self._available_tools.get('pylint'):
            self._pylint_check(file_path, report)
        
        # 安全检查
        if 'security' in check_types and self._available_tools.get('bandit'):
            self._bandit_check(file_path, report)
        
        # 复杂度检查
        if 'complexity' in check_types:
            if self._available_tools.get('radon'):
                self._radon_check(file_path, report)
            else:
                # 使用内置 AST 复杂度分析
                self._ast_complexity_check(file_path, report)
        
        # 生成摘要
        report.summary = self._generate_summary(report)
        
        return report
    
    def _basic_ast_check(self, file_path: Path, report: QualityReport):
        """基础 AST 检查"""
        try:
            from .ast_analyzer import get_ast_analyzer
            
            analyzer = get_ast_analyzer()
            analysis = analyzer.analyze_file(str(file_path))
            
            # 检查函数复杂度
            for func in analysis.get('functions', []):
                if func.complexity > 10:
                    report.add_issue(QualityIssue(
                        file_path=str(file_path),
                        line_no=func.line_no,
                        column=0,
                        severity=Severity.WARNING if func.complexity < 20 else Severity.ERROR,
                        message=f"函数 '{func.name}' 复杂度过高 ({func.complexity})",
                        source='ast',
                        rule_id='high_complexity',
                        fix_suggestion="考虑将函数拆分为更小的函数"
                    ))
            
            # 检查类的大小
            for cls in analysis.get('classes', []):
                if len(cls.methods) > 20:
                    report.add_issue(QualityIssue(
                        file_path=str(file_path),
                        line_no=cls.line_no,
                        column=0,
                        severity=Severity.WARNING,
                        message=f"类 '{cls.name}' 方法过多 ({len(cls.methods)})",
                        source='ast',
                        rule_id='large_class',
                        fix_suggestion="考虑使用组合或继承来重构"
                    ))
            
        except Exception as e:
            self.logger.error(f"AST 检查失败: {e}")
    
    def _pylint_check(self, file_path: Path, report: QualityReport):
        """使用 pylint 检查"""
        try:
            result = subprocess.run(
                ['python', '-m', 'pylint', 
                 '--output-format=json',
                 '--disable=all',
                 '--enable=C,W,R',
                 str(file_path)],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.stdout:
                try:
                    pylint_results = json.loads(result.stdout)
                    for item in pylint_results:
                        severity = self._map_pylint_severity(item.get('type', ''))
                        report.add_issue(QualityIssue(
                            file_path=str(file_path),
                            line_no=item.get('line', 0),
                            column=item.get('column', 0),
                            severity=severity,
                            message=item.get('message', ''),
                            source='pylint',
                            rule_id=item.get('message-id', ''),
                            fix_suggestion=item.get('message', '')  # pylint 有时包含建议
                        ))
                except json.JSONDecodeError:
                    self.logger.warning("pylint 输出解析失败")
        
        except Exception as e:
            self.logger.warning(f"pylint 检查失败: {e}")
    
    def _bandit_check(self, file_path: Path, report: QualityReport):
        """使用 bandit 进行安全检查"""
        try:
            result = subprocess.run(
                ['python', '-m', 'bandit',
                 '-f', 'json',
                 str(file_path)],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.stdout:
                try:
                    bandit_results = json.loads(result.stdout)
                    for item in bandit_results.get('results', []):
                        severity = self._map_bandit_severity(item.get('issue_severity', ''))
                        report.add_issue(QualityIssue(
                            file_path=str(file_path),
                            line_no=item.get('line_number', 0),
                            column=0,
                            severity=severity,
                            message=item.get('issue_text', ''),
                            source='bandit',
                            rule_id=item.get('test_id', ''),
                            fix_suggestion=item.get('issue_text', '')
                        ))
                except json.JSONDecodeError:
                    self.logger.warning("bandit 输出解析失败")
        
        except Exception as e:
            self.logger.warning(f"bandit 检查失败: {e}")
    
    def _radon_check(self, file_path: Path, report: QualityReport):
        """使用 radon 进行复杂度分析"""
        try:
            result = subprocess.run(
                ['python', '-m', 'radon',
                 'cc',
                 str(file_path),
                 '-a'],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.stdout:
                # 解析 radon 输出
                lines = result.stdout.split('\n')
                for line in lines:
                    if '(' in line and 'C' in line:
                        try:
                            # radon 输出格式: filename (XX, YY, ZZ)
                            parts = line.split('(')[1].split(')')[0].split(',')
                            if len(parts) >= 3:
                                complexity = int(parts[2].strip())
                                if complexity > 10:
                                    report.metrics.complexity_score = max(
                                        report.metrics.complexity_score, complexity
                                    )
                        except (ValueError, IndexError):
                            continue
        
        except Exception as e:
            self.logger.warning(f"radon 检查失败: {e}")
    
    def _ast_complexity_check(self, file_path: Path, report: QualityReport):
        """使用 AST 进行复杂度分析"""
        try:
            from .ast_analyzer import get_ast_analyzer
            
            analyzer = get_ast_analyzer()
            analysis = analyzer.analyze_file(str(file_path))
            
            max_complexity = 0
            for func in analysis.get('functions', []):
                max_complexity = max(max_complexity, func.complexity)
            
            for cls in analysis.get('classes', []):
                for method in cls.methods:
                    max_complexity = max(max_complexity, method.complexity)
            
            report.metrics.complexity_score = float(max_complexity)
        
        except Exception as e:
            self.logger.error(f"AST 复杂度检查失败: {e}")
    
    def _map_pylint_severity(self, pylint_type: str) -> Severity:
        """映射 pylint 严重程度"""
        if pylint_type == 'error':
            return Severity.ERROR
        elif pylint_type == 'warning':
            return Severity.WARNING
        elif pylint_type == 'convention':
            return Severity.INFO
        elif pylint_type == 'refactor':
            return Severity.INFO
        else:
            return Severity.INFO
    
    def _map_bandit_severity(self, bandit_severity: str) -> Severity:
        """映射 bandit 严重程度"""
        if bandit_severity == 'HIGH':
            return Severity.CRITICAL
        elif bandit_severity == 'MEDIUM':
            return Severity.ERROR
        elif bandit_severity == 'LOW':
            return Severity.WARNING
        else:
            return Severity.INFO
    
    def _generate_summary(self, report: QualityReport) -> str:
        """生成质量报告摘要"""
        lines = []
        lines.append(f"文件: {report.file_path}")
        lines.append(f"总分: {report.metrics.calculate_overall_score():.1f}/100")
        lines.append(f"问题总数: {report.metrics.total_issues}")
        lines.append(f"  - 严重: {report.metrics.critical_issues}")
        lines.append(f"  - 错误: {report.metrics.error_issues}")
        lines.append(f"  - 警告: {report.metrics.warning_issues}")
        lines.append(f"  - 信息: {report.metrics.info_issues}")
        lines.append(f"复杂度: {report.metrics.complexity_score:.1f}")
        
        return "\n".join(lines)
    
    def check_project(self, project_path: str, 
                     pattern: str = "*.py") -> Dict[str, QualityReport]:
        """检查整个项目"""
        project_path = Path(project_path)
        if not project_path.exists():
            return {}
        
        reports = {}
        python_files = list(project_path.rglob(pattern))
        
        for file_path in python_files:
            # 跳过虚拟环境和测试目录
            if 'venv' in str(file_path) or '__pycache__' in str(file_path):
                continue
            
            report = self.check_file(str(file_path))
            reports[str(file_path)] = report
        
        return reports
    
    def get_project_summary(self, reports: Dict[str, QualityReport]) -> Dict:
        """获取项目质量摘要"""
        total_issues = sum(r.metrics.total_issues for r in reports.values())
        total_files = len(reports)
        
        if total_files == 0:
            return {}
        
        avg_score = sum(r.metrics.calculate_overall_score() for r in reports.values()) / total_files
        
        severity_counts = {
            'critical': sum(r.metrics.critical_issues for r in reports.values()),
            'error': sum(r.metrics.error_issues for r in reports.values()),
            'warning': sum(r.metrics.warning_issues for r in reports.values()),
            'info': sum(r.metrics.info_issues for r in reports.values())
        }
        
        return {
            'total_files': total_files,
            'total_issues': total_issues,
            'average_score': avg_score,
            'severity_breakdown': severity_counts,
            'files_with_issues': sum(1 for r in reports.values() if r.metrics.total_issues > 0)
        }


# 全局质量检查器实例
_quality_checker = None

def get_quality_checker() -> QualityChecker:
    """获取全局质量检查器实例"""
    global _quality_checker
    if _quality_checker is None:
        _quality_checker = QualityChecker()
    return _quality_checker
