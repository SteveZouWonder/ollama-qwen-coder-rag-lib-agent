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
                text=True, encoding="utf-8", errors="replace",
                timeout=30,
                stdin=subprocess.DEVNULL,  # 避免 shortlog 等命令在非 tty 下读 stdin 阻塞
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
    
    # ``git status --porcelain`` 状态码 → 中文标签（取 X/Y 两位中更有信息量的一位）
    STATUS_LABELS = {
        "?": "未跟踪", "M": "修改", "A": "新增", "D": "删除", "R": "重命名",
        "C": "复制", "U": "冲突", "T": "类型变更", "!": "忽略",
    }

    def is_repo(self) -> bool:
        """当前路径是否位于 Git 工作区内（含子目录）。"""
        return self._run_git_command(['rev-parse', '--is-inside-work-tree']) == "true"

    def get_overview(self, max_commits: int = 20) -> Dict[str, Any]:
        """仪表盘用的结构化概览（Web 工具页 / CLI ``/git-analyze`` 共用）。

        返回::

            {
              "is_repo": bool, "branch": str,
              "changed": [{"status": "M", "label": "修改", "path": "a.py"}, ...],
              "commits": [{"hash7", "author", "date", "subject"}, ...],   # 最近 max_commits
              "authors": [{"name", "commits"}, ...],                      # 按提交数降序
              "last_commit_at": "YYYY-MM-DD HH:MM:SS +ZZZZ" | "",
            }

        非 git 目录只返回 ``is_repo=False`` 与空集合；不抛异常。
        """
        empty: Dict[str, Any] = {
            "is_repo": False, "branch": "", "changed": [], "commits": [],
            "authors": [], "last_commit_at": "",
        }
        if not self.is_repo():
            return empty
        overview = dict(empty)
        overview["is_repo"] = True
        overview["branch"] = self.get_current_branch() or ""

        changed = []
        # porcelain 每行 ``XY<空格>path``；_run_git_command 会 strip 整体输出（首行前导空格丢失），
        # 故按"首个空格"切分状态码与路径，而非固定列位。
        for line in self._run_git_command(['status', '--porcelain']).split('\n'):
            xy, _, path = line.strip().partition(' ')
            path = path.lstrip()
            if not xy or not path:
                continue
            code = xy[:1]
            if ' -> ' in path:
                path = path.split(' -> ', 1)[1]
            changed.append({"status": xy, "label": self.STATUS_LABELS.get(code, code), "path": path})
        overview["changed"] = changed

        sep = "\x1f"
        raw = self._run_git_command([
            'log', f'-{int(max_commits)}', f'--pretty=format:%h{sep}%an{sep}%ad{sep}%s', '--date=short',
        ])
        commits = []
        for line in raw.split('\n'):
            parts = line.split(sep)
            if len(parts) == 4:
                commits.append({"hash7": parts[0], "author": parts[1], "date": parts[2], "subject": parts[3]})
        overview["commits"] = commits

        # 作者统计：用 git log 而非 shortlog（shortlog 无 revision 且 stdin 非 tty 时会读 stdin 阻塞）
        names = [n for n in self._run_git_command(['log', '--pretty=format:%an', '--no-merges']).split('\n') if n]
        counts: Dict[str, int] = {}
        for n in names:
            counts[n] = counts.get(n, 0) + 1
        overview["authors"] = [
            {"name": n, "commits": c} for n, c in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
        ]
        overview["last_commit_at"] = self._run_git_command(['log', '-1', '--format=%ci']) if commits else ""
        return overview

    def _run_git_full(self, command: List[str]) -> Dict[str, Any]:
        """运行 Git 命令并返回 ``{returncode, stdout, stderr}``（写操作需要看到 stderr）。"""
        try:
            result = subprocess.run(
                ['git'] + command, cwd=self.repo_path, capture_output=True, text=True, encoding="utf-8", errors="replace",
                timeout=30, stdin=subprocess.DEVNULL,
            )
            return {"returncode": result.returncode, "stdout": (result.stdout or "").strip(),
                    "stderr": (result.stderr or "").strip()}
        except subprocess.TimeoutExpired:
            return {"returncode": 124, "stdout": "", "stderr": f"Git 命令超时: {' '.join(command)}"}
        except Exception as e:  # noqa: BLE001
            return {"returncode": 1, "stdout": "", "stderr": str(e)}

    def get_commit_preview(self) -> Dict[str, Any]:
        """暂存区预览（Web「AI 生成提交信息」前置卡片 / 提交确认共用，F9 P3-3）。

        返回::

            {
              "is_repo": bool, "has_staged": bool,
              "staged_files": [{"status": "M", "label": "修改", "path": "a.py"}, ...],
              "diff_stat": "a.py | 2 +-\\n 1 file changed, ...",     # git diff --cached --stat
              "files_changed": int, "insertions": int, "deletions": int,
            }
        """
        preview: Dict[str, Any] = {
            "is_repo": False, "has_staged": False, "staged_files": [], "diff_stat": "",
            "files_changed": 0, "insertions": 0, "deletions": 0,
        }
        if not self.is_repo():
            return preview
        preview["is_repo"] = True
        staged = []
        for line in self._run_git_command(['diff', '--cached', '--name-status']).split('\n'):
            parts = line.strip().split('\t')
            if len(parts) < 2 or not parts[0]:
                continue
            code = parts[0][:1]
            path = parts[-1]  # 重命名 / 复制形如 ``R100\told\tnew``，取新路径
            staged.append({"status": parts[0], "label": self.STATUS_LABELS.get(code, code), "path": path})
        preview["staged_files"] = staged
        preview["has_staged"] = bool(staged)
        if not staged:
            return preview
        preview["diff_stat"] = self._run_git_command(['diff', '--cached', '--stat'])
        shortstat = self._run_git_command(['diff', '--cached', '--shortstat'])
        import re as _re
        for key, pat in (("files_changed", r"(\d+) files? changed"), ("insertions", r"(\d+) insertions?"),
                         ("deletions", r"(\d+) deletions?")):
            m = _re.search(pat, shortstat)
            preview[key] = int(m.group(1)) if m else 0
        return preview

    def commit(self, message: str) -> Dict[str, Any]:
        """执行 ``git commit -m <message>``（仅提交暂存区）。

        返回 ``{ok, hash7, subject, error}``；无暂存 / 空信息 / git 失败时 ``ok=False`` 并给出 ``error``。
        不触碰 ``git add``，不改 hooks / 配置。
        """
        message = (message or "").strip()
        if not message:
            return {"ok": False, "hash7": "", "subject": "", "error": "提交信息不能为空"}
        if not self.is_repo():
            return {"ok": False, "hash7": "", "subject": "", "error": "当前目录不是 Git 仓库"}
        if not self.get_commit_preview()["has_staged"]:
            return {"ok": False, "hash7": "", "subject": "", "error": "暂存区为空，请先 git add"}
        res = self._run_git_full(['commit', '-m', message])
        if res["returncode"] != 0:
            err = res["stderr"] or res["stdout"] or f"git commit 退出码 {res['returncode']}"
            return {"ok": False, "hash7": "", "subject": "", "error": err}
        hash7 = self._run_git_command(['rev-parse', '--short', 'HEAD'])
        subject = self._run_git_command(['log', '-1', '--format=%s'])
        return {"ok": True, "hash7": hash7, "subject": subject, "error": ""}
    
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
