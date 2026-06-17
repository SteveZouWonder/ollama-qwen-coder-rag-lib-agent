#!/usr/bin/env python3
"""
Git 分析器 - Git 历史分析、变更追踪
"""
import subprocess
import logging
from pathlib import Path
from typing import List, Dict, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime
import json

logger = logging.getLogger(__name__)


@dataclass
class ChangeInfo:
    """变更信息"""
    file_path: str
    change_type: str  # 'A' added, 'D' deleted, 'M' modified, 'R' renamed
    additions: int = 0
    deletions: int = 0
    old_path: Optional[str] = None  # 用于重命名
    
    def to_dict(self) -> Dict:
        """转换为字典"""
        return {
            'file_path': self.file_path,
            'change_type': self.change_type,
            'additions': self.additions,
            'deletions': self.deletions,
            'old_path': self.old_path
        }


@dataclass
class CommitInfo:
    """提交信息"""
    commit_hash: str
    author: str
    email: str
    date: str
    message: str
    changes: List[ChangeInfo] = field(default_factory=list)
    branch: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict:
        """转换为字典"""
        return {
            'commit_hash': self.commit_hash,
            'author': self.author,
            'email': self.email,
            'date': self.date,
            'message': self.message,
            'changes': [c.to_dict() for c in self.changes],
            'branch': self.branch,
            'tags': self.tags
        }


class GitAnalyzer:
    """Git 分析器"""
    
    def __init__(self, repo_path: str = "."):
        self.repo_path = Path(repo_path).resolve()
        self.logger = logger
        self._validate_repo()
    
    def _validate_repo(self):
        """验证是否为 Git 仓库"""
        git_dir = self.repo_path / ".git"
        if not git_dir.exists():
            self.logger.warning(f"{self.repo_path} 不是 Git 仓库")
    
    def _run_git_command(self, command: List[str]) -> str:
        """运行 Git 命令"""
        try:
            result = subprocess.run(
                ['git'] + command,
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode != 0:
                self.logger.error(f"Git 命令失败: {command}")
                self.logger.error(f"错误: {result.stderr}")
                return ""
            
            return result.stdout.strip()
        except subprocess.TimeoutExpired:
            self.logger.error(f"Git 命令超时: {command}")
            return ""
        except Exception as e:
            self.logger.error(f"Git 命令执行异常: {e}")
            return ""
    
    def get_current_branch(self) -> Optional[str]:
        """获取当前分支"""
        branch = self._run_git_command(['rev-parse', '--abbrev-ref', 'HEAD'])
        return branch if branch and branch != "HEAD" else None
    
    def get_commit_history(self, max_count: int = 10) -> List[CommitInfo]:
        """获取提交历史"""
        # 使用 --pretty=format 获取格式化的提交信息
        format_str = "%H|%an|%ae|%ai|%s"
        output = self._run_git_command([
            'log',
            f'--pretty=format:{format_str}',
            f'-{max_count}'
        ])
        
        commits = []
        if not output:
            return commits
        
        for line in output.split('\n'):
            parts = line.split('|')
            if len(parts) >= 5:
                commit = CommitInfo(
                    commit_hash=parts[0],
                    author=parts[1],
                    email=parts[2],
                    date=parts[3],
                    message=parts[4]
                )
                commits.append(commit)
        
        # 获取每个提交的变更详情
        for commit in commits:
            commit.changes = self._get_commit_changes(commit.commit_hash)
            commit.branch = self.get_current_branch()
            commit.tags = self._get_commit_tags(commit.commit_hash)
        
        return commits
    
    def _get_commit_changes(self, commit_hash: str) -> List[ChangeInfo]:
        """获取提交的变更文件"""
        # 获取变更统计
        output = self._run_git_command([
            'show',
            '--numstat',
            '--pretty=format:',
            commit_hash
        ])
        
        changes = []
        for line in output.split('\n'):
            if not line or line.startswith(' '):
                continue
            
            parts = line.split()
            if len(parts) >= 3:
                additions = int(parts[0]) if parts[0].isdigit() else 0
                deletions = int(parts[1]) if parts[1].isdigit() else 0
                file_path = parts[2]
                
                # 确定变更类型
                change_type = 'M'  # 默认为修改
                if additions == 0 and deletions == 0:
                    change_type = 'R'  # 可能是重命名
                elif deletions == 0 and additions > 0:
                    change_type = 'A'  # 新增
                elif additions == 0 and deletions > 0:
                    change_type = 'D'  # 删除
                
                changes.append(ChangeInfo(
                    file_path=file_path,
                    change_type=change_type,
                    additions=additions,
                    deletions=deletions
                ))
        
        return changes
    
    def _get_commit_tags(self, commit_hash: str) -> List[str]:
        """获取提交的标签"""
        output = self._run_git_command([
            'tag',
            '--points-at',
            commit_hash
        ])
        
        return output.split('\n') if output else []
    
    def get_file_history(self, file_path: str, max_count: int = 10) -> List[CommitInfo]:
        """获取文件历史"""
        output = self._run_git_command([
            'log',
            f'--pretty=format:%H|%an|%ae|%ai|%s',
            f'-{max_count}',
            '--',
            file_path
        ])
        
        commits = []
        for line in output.split('\n'):
            parts = line.split('|')
            if len(parts) >= 5:
                commits.append(CommitInfo(
                    commit_hash=parts[0],
                    author=parts[1],
                    email=parts[2],
                    date=parts[3],
                    message=parts[4]
                ))
        
        return commits
    
    def get_branches(self) -> List[str]:
        """获取所有分支"""
        output = self._run_git_command(['branch', '--format=%(refname:short)'])
        return output.split('\n') if output else []
    
    def get_status(self) -> Dict[str, Any]:
        """获取 Git 状态"""
        status = {
            'branch': self.get_current_branch(),
            'staged': [],
            'unstaged': [],
            'untracked': [],
            'diverged': False,
            'ahead': 0,
            'behind': 0
        }
        
        # 获取状态信息
        output = self._run_git_command(['status', '--porcelain'])
        
        for line in output.split('\n'):
            if not line:
                continue
            
            status_char = line[0]
            file_path = line[3:]
            
            if status_char == ' ':
                status['untracked'].append(file_path)
            elif status_char == 'M':
                status['unstaged'].append(file_path)
            elif status_char in ['A', 'M', 'D']:
                status['staged'].append(file_path)
        
        # 检查分支差异
        branch = status['branch']
        if branch:
            ahead_behind = self._run_git_command(['rev-list', '--count', '--left-right', f'origin/{branch}...HEAD'])
            if ahead_behind:
                parts = ahead_behind.split()
                if len(parts) == 2:
                    status['behind'] = int(parts[0])
                    status['ahead'] = int(parts[1])
                    status['diverged'] = status['ahead'] > 0 or status['behind'] > 0
        
        return status
    
    def get_author_stats(self, max_count: int = 10) -> Dict[str, Dict[str, int]]:
        """获取作者统计"""
        output = self._run_git_command([
            'shortlog',
            '-sn',
            f'-{max_count}',
            '--no-merges'
        ])
        
        stats = {}
        for line in output.split('\n'):
            if not line:
                continue
            
            parts = line.split()
            if len(parts) >= 2:
                count = int(parts[0])
                author = ' '.join(parts[1:])
                stats[author] = {'commits': count}
        
        return stats
    
    def analyze_code_frequency(self, file_path: str, days: int = 30) -> Dict[str, int]:
        """分析代码变更频率"""
        since_date = datetime.now().replace(day=datetime.now().day - days).strftime('%Y-%m-%d')
        
        output = self._run_git_command([
            'log',
            f'--since={since_date}',
            '--pretty=format:%H',
            '--',
            file_path
        ])
        
        commits = output.split('\n') if output else []
        
        return {
            'file_path': file_path,
            'days': days,
            'commits': len(commits),
            'avg_commits_per_day': len(commits) / days if days > 0 else 0
        }


# 全局 Git 分析器实例
_git_analyzer = None

def get_git_analyzer(repo_path: str = ".") -> GitAnalyzer:
    """获取 Git 分析器实例"""
    global _git_analyzer
    if _git_analyzer is None or _git_analyzer.repo_path != Path(repo_path).resolve():
        _git_analyzer = GitAnalyzer(repo_path)
    return _git_analyzer
