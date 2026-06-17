#!/usr/bin/env python3
"""
提交信息生成器 - 利用 AI 模型生成高质量的 Git 提交信息
"""
import logging
import subprocess
from typing import List, Dict, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class CommitSuggestion:
    """提交建议"""
    title: str
    body: str
    conventional_type: Optional[str] = None  # feat, fix, docs, etc.
    
    def to_dict(self) -> Dict:
        """转换为字典"""
        return {
            'title': self.title,
            'body': self.body,
            'conventional_type': self.conventional_type
        }


class CommitMessageGenerator:
    """提交信息生成器"""
    
    def __init__(self, repo_path: str = ".", ollama_base_url: str = "http://localhost:11434"):
        self.repo_path = repo_path
        self.ollama_base_url = ollama_base_url
        self.logger = logger
    
    def get_staged_changes(self) -> str:
        """获取暂存的变更"""
        try:
            # 获取暂存的文件变更
            result = subprocess.run(
                ['git', 'diff', '--staged', '--stat'],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            # 获取详细的变更内容
            diff_result = subprocess.run(
                ['git', 'diff', '--staged'],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            return result.stdout + "\n" + diff_result.stdout
        except Exception as e:
            self.logger.error(f"获取暂存变更失败: {e}")
            return ""
    
    def generate_commit_message(self, use_ai: bool = True) -> CommitSuggestion:
        """生成提交信息"""
        changes = self.get_staged_changes()
        
        if not changes:
            return CommitSuggestion(
                title="No changes staged",
                body="Please stage some changes first using 'git add'"
            )
        
        if use_ai:
            return self._generate_ai_commit_message(changes)
        else:
            return self._generate_simple_commit_message(changes)
    
    def _generate_simple_commit_message(self, changes: str) -> CommitSuggestion:
        """生成简单的提交信息（不使用 AI）"""
        # 分析变更类型
        lines = changes.split('\n')
        changed_files = []
        added_files = []
        deleted_files = []
        
        for line in lines:
            if line.endswith('.py') or line.endswith('.md') or line.endswith('.txt'):
                if 'new file' in line.lower():
                    added_files.append(line)
                elif 'deleted' in line.lower():
                    deleted_files.append(line)
                else:
                    changed_files.append(line)
        
        # 生成提交标题
        if added_files:
            title = f"Add {len(added_files)} new file(s)"
        elif deleted_files:
            title = f"Remove {len(deleted_files)} file(s)"
        elif changed_files:
            title = f"Update {len(changed_files)} file(s)"
        else:
            title = "Update code"
        
        # 生成提交正文
        body_lines = []
        if added_files:
            body_lines.append(f"Added files:")
            body_lines.extend([f"  - {f.strip()}" for f in added_files[:5]])
        if deleted_files:
            body_lines.append(f"Deleted files:")
            body_lines.extend([f"  - {f.strip()}" for f in deleted_files[:5]])
        if changed_files:
            body_lines.append(f"Modified files:")
            body_lines.extend([f"  - {f.strip()}" for f in changed_files[:5]])
        
        body = "\n".join(body_lines)
        
        return CommitSuggestion(title=title, body=body)
    
    def _generate_ai_commit_message(self, changes: str) -> CommitSuggestion:
        """使用 AI 生成提交信息"""
        try:
            # 构建提示
            prompt = f"""Generate a concise and meaningful Git commit message for the following changes:

Changes:
{changes}

Please follow the Conventional Commits format:
- Start with a type: feat, fix, docs, style, refactor, test, or chore
- Provide a short description (50 characters or less)
- Provide a more detailed body if needed
- Use imperative mood

Output format:
type: short description

detailed description (if needed)"""

            # 调用 Ollama API
            import requests
            
            response = requests.post(
                f"{self.ollama_base_url}/api/generate",
                json={
                    "model": "qwen2.5-coder:7b",
                    "prompt": prompt,
                    "stream": False
                },
                timeout=60
            )
            
            if response.status_code == 200:
                result = response.json()
                message = result.get('response', '').strip()
                
                # 解析响应
                return self._parse_ai_response(message)
            else:
                self.logger.warning(f"AI 生成失败，使用简单方法")
                return self._generate_simple_commit_message(changes)
                
        except Exception as e:
            self.logger.error(f"AI 生成提交信息失败: {e}")
            return self._generate_simple_commit_message(changes)
    
    def _parse_ai_response(self, response: str) -> CommitSuggestion:
        """解析 AI 响应"""
        lines = response.split('\n')
        
        if not lines:
            return CommitSuggestion(title="Update code", body=response)
        
        # 第一行作为标题
        title = lines[0].strip()
        
        # 其余作为正文
        body = '\n'.join(lines[1:]).strip()
        
        # 检查是否包含 Conventional Commits 类型
        conventional_types = ['feat:', 'fix:', 'docs:', 'style:', 'refactor:', 'test:', 'chore:']
        conv_type = None
        for t in conventional_types:
            if title.lower().startswith(t):
                conv_type = t.rstrip(':')
                # 从标题中移除类型前缀用于显示
                # 但保留原始格式
                break
        
        return CommitSuggestion(
            title=title,
            body=body,
            conventional_type=conv_type
        )
    
    def suggest_commit_message(self, max_suggestions: int = 3) -> List[CommitSuggestion]:
        """生成多个提交建议"""
        suggestions = []
        
        # 主要建议（AI 生成）
        main_suggestion = self.generate_commit_message(use_ai=True)
        suggestions.append(main_suggestion)
        
        # 备用建议（简单生成）
        simple_suggestion = self.generate_commit_message(use_ai=False)
        if simple_suggestion.title != main_suggestion.title:
            suggestions.append(simple_suggestion)
        
        return suggestions[:max_suggestions]


# 全局提交信息生成器实例
_commit_generator = None

def get_commit_generator(repo_path: str = ".", ollama_base_url: str = "http://localhost:11434") -> CommitMessageGenerator:
    """获取提交信息生成器实例"""
    global _commit_generator
    if _commit_generator is None:
        _commit_generator = CommitMessageGenerator(repo_path, ollama_base_url)
    return _commit_generator
