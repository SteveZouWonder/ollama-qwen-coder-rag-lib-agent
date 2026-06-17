#!/usr/bin/env python3
"""
展示引擎 - 格式化推荐内容
"""
import logging
from typing import List, Optional, Dict, Any
from .types import Recommendation, RecommendationStrength, UserPreference

logger = logging.getLogger(__name__)


class DisplayFormatter:
    """展示格式化器 - 格式化推荐内容供显示"""
    
    def __init__(self, preference: Optional[UserPreference] = None):
        self.preference = preference or UserPreference()
    
    def format_recommendations(
        self,
        recommendations: List[Recommendation],
        use_rich: bool = True,
        show_hidden: bool = False
    ) -> str:
        """格式化推荐列表"""
        if not recommendations:
            return ""
        
        # 过滤隐藏的推荐
        if not show_hidden and self.preference:
            recommendations = [
                r for r in recommendations 
                if not self.preference.is_hidden(r.command)
            ]
        
        if not recommendations:
            return ""
        
        if use_rich:
            return self._format_rich(recommendations)
        else:
            return self._format_plain(recommendations)
    
    def _format_rich(self, recommendations: List[Recommendation]) -> str:
        """使用Rich库格式化"""
        try:
            from rich.console import Console
            from rich.panel import Panel
            from rich.table import Table
            from rich import box
            from rich.markdown import Markdown
            
            console = Console()
            
            # 创建标题
            title = "💡 智能推荐 (基于当前上下文)"
            
            # 创建表格
            table = Table(show_header=False, box=box.ROUNDED, padding=(0, 1))
            table.add_column("content", style="white")
            
            for i, rec in enumerate(recommendations[:self.preference.max_recommendations], 1):
                # 强度标签
                strength_emoji = self._get_strength_emoji(rec.strength)
                strength_text = self._get_strength_text(rec.strength)
                
                # 强度显示
                if self.preference.show_strength:
                    strength_line = f"[bold cyan]{strength_emoji} [{strength_text}][/bold cyan] [dim](建议强度: {rec.score:.1%})[/dim]"
                else:
                    strength_line = f"[bold cyan]{strength_emoji} [{strength_text}][/bold cyan]"
                
                # 命令和描述
                command_line = f"   [bold yellow]{rec.command}[/bold yellow]"
                desc_line = f"   [dim]描述: {rec.description}[/dim]"
                
                # 理由
                if self.preference.show_explanations and rec.reasons:
                    reason_text = "   [dim]理由: " + "; ".join(str(r) for r in rec.reasons[:2]) + "[/dim]"
                else:
                    reason_text = ""
                
                # 路径
                if self.preference.show_paths and rec.suggested_path:
                    path_text = "   [dim blue]📍 路径: " + " → ".join(rec.suggested_path) + "[/dim blue]"
                else:
                    path_text = ""
                
                # 组合内容
                content = f"{strength_line}\n{command_line}\n{desc_line}\n{reason_text}\n{path_text}"
                table.add_row(content)
                
                # 添加分隔符（除了最后一个）
                if i < len(recommendations):
                    table.add_row("")
            
            # 帮助提示
            help_text = "[dim]提示: 按 Tab 键执行第一个推荐，输入 h 隐藏推荐[/dim]"
            table.add_row(help_text)
            
            # 创建面板
            panel = Panel(
                table,
                title=title,
                border_style="cyan",
                padding=(1, 1)
            )
            
            # 渲染到字符串
            with console.capture() as capture:
                console.print(panel)
            
            return capture.get()
            
        except ImportError:
            logger.warning("Rich库不可用，使用纯文本格式")
            return self._format_plain(recommendations)
        except Exception as e:
            logger.error(f"格式化推荐时出错: {e}")
            return self._format_plain(recommendations)
    
    def _format_plain(self, recommendations: List[Recommendation]) -> str:
        """纯文本格式化"""
        lines = []
        lines.append("=" * 60)
        lines.append("💡 智能推荐 (基于当前上下文)")
        lines.append("=" * 60)
        
        for i, rec in enumerate(recommendations[:self.preference.max_recommendations], 1):
            strength_emoji = self._get_strength_emoji(rec.strength)
            strength_text = self._get_strength_text(rec.strength)
            
            lines.append(f"\n{strength_emoji} [{strength_text}] {rec.command}")
            lines.append(f"   描述: {rec.description}")
            
            if self.preference.show_strength:
                lines.append(f"   建议强度: {rec.score:.1%}")
            
            if self.preference.show_explanations and rec.reasons:
                reasons = "; ".join(str(r) for r in rec.reasons[:2])
                lines.append(f"   理由: {reasons}")
            
            if self.preference.show_paths and rec.suggested_path:
                path = " → ".join(rec.suggested_path)
                lines.append(f"   路径: {path}")
        
        lines.append("\n提示: 手动输入命令执行推荐")
        lines.append("=" * 60)
        
        return "\n".join(lines)
    
    def _get_strength_emoji(self, strength: RecommendationStrength) -> str:
        """获取强度对应的emoji"""
        emojis = {
            RecommendationStrength.VERY_STRONG: "🎯",
            RecommendationStrength.STRONG: "🔧",
            RecommendationStrength.MODERATE: "💭",
            RecommendationStrength.WEAK: "💡"
        }
        return emojis.get(strength, "💡")
    
    def _get_strength_text(self, strength: RecommendationStrength) -> str:
        """获取强度对应的文本"""
        texts = {
            RecommendationStrength.VERY_STRONG: "强烈推荐",
            RecommendationStrength.STRONG: "推荐",
            RecommendationStrength.MODERATE: "建议",
            RecommendationStrength.WEAK: "可能需要"
        }
        return texts.get(strength, "建议")
    
    def format_single_recommendation(self, recommendation: Recommendation, use_rich: bool = True) -> str:
        """格式化单个推荐"""
        if use_rich:
            strength_emoji = self._get_strength_emoji(recommendation.strength)
            strength_text = self._get_strength_text(recommendation.strength)
            
            return (
                f"[bold cyan]{strength_emoji} [{strength_text}][/bold cyan] "
                f"[bold yellow]{recommendation.command}[/bold yellow]\n"
                f"[dim]{recommendation.description}[/dim]"
            )
        else:
            strength_emoji = self._get_strength_emoji(recommendation.strength)
            strength_text = self._get_strength_text(recommendation.strength)
            
            return (
                f"{strength_emoji} [{strength_text}] {recommendation.command}\n"
                f"   {recommendation.description}"
            )
    
    def format_context_info(self, context_info: Dict[str, Any], use_rich: bool = True) -> str:
        """格式化上下文信息"""
        if use_rich:
            lines = [
                "[dim]当前会话信息:[/dim]",
                f"[dim]  会话时长: {context_info.get('session_duration', 0):.0f}秒[/dim]",
                f"[dim]  命令数量: {context_info.get('command_count', 0)}[/dim]",
                f"[dim]  当前模式: {context_info.get('current_mode', 'auto')}[/dim]",
                f"[dim]  RAG可用: {context_info.get('rag_available', False)}[/dim]",
                f"[dim]  知识库空: {context_info.get('knowledge_empty', True)}[/dim]"
            ]
            return "\n".join(lines)
        else:
            lines = [
                "当前会话信息:",
                f"  会话时长: {context_info.get('session_duration', 0):.0f}秒",
                f"  命令数量: {context_info.get('command_count', 0)}",
                f"  当前模式: {context_info.get('current_mode', 'auto')}",
                f"  RAG可用: {context_info.get('rag_available', False)}",
                f"  知识库空: {context_info.get('knowledge_empty', True)}"
            ]
            return "\n".join(lines)
    
    def format_learning_info(self, preference_info: Dict[str, Any], use_rich: bool = True) -> str:
        """格式化学习信息"""
        if not preference_info:
            return ""
        
        if use_rich:
            weights = preference_info.get('weights', {})
            lines = [
                "[dim]学习引擎状态:[/dim]",
                f"[dim]  工作流权重: {weights.get('workflow', 0.4):.2f}[/dim]",
                f"[dim]  状态权重: {weights.get('state', 0.3):.2f}[/dim]",
                f"[dim]  历史权重: {weights.get('history', 0.3):.2f}[/dim]",
                f"[dim]  隐藏推荐数: {preference_info.get('hidden_count', 0)}[/dim]"
            ]
            return "\n".join(lines)
        else:
            weights = preference_info.get('weights', {})
            lines = [
                "学习引擎状态:",
                f"  工作流权重: {weights.get('workflow', 0.4):.2f}",
                f"  状态权重: {weights.get('state', 0.3):.2f}",
                f"  历史权重: {weights.get('history', 0.3):.2f}",
                f"  隐藏推荐数: {preference_info.get('hidden_count', 0)}"
            ]
            return "\n".join(lines)
    
    def set_preference(self, preference: UserPreference):
        """设置用户偏好"""
        self.preference = preference