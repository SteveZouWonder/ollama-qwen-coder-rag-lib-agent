"""
结果整合器 - 合并多个Agent的执行结果
"""
from typing import List, Dict, Any
import logging
from agents.agent_types import AgentResult, AgentTask
from datetime import datetime


class ResultIntegrator:
    """结果整合器，负责合并多个Agent的执行结果"""
    
    def __init__(self):
        """初始化结果整合器"""
        self.logger = logging.getLogger("ResultIntegrator")
    
    def integrate(self, results: List[AgentResult], original_tasks: List[AgentTask] = None) -> Dict[str, Any]:
        """
        整合多个Agent的执行结果
        
        Args:
            results: Agent执行结果列表
            original_tasks: 原始任务列表（可选，用于上下文）
            
        Returns:
            Dict[str, Any]: 整合后的结果
        """
        self.logger.info(f"Integrating {len(results)} results")
        
        if not results:
            return {
                "success": False,
                "error": "No results to integrate",
                "summary": "No results provided"
            }
        
        # 统计结果
        success_count = sum(1 for r in results if r.success)
        total_count = len(results)
        
        # 构建整合结果
        integrated_result = {
            "success": success_count == total_count,
            "total_results": total_count,
            "successful_results": success_count,
            "failed_results": total_count - success_count,
            "results": [r.to_dict() for r in results],
            "timestamp": datetime.now().isoformat(),
            "summary": self._generate_summary(results),
            "detailed_report": self._generate_detailed_report(results, original_tasks)
        }
        
        self.logger.info(
            f"Integration complete: {success_count}/{total_count} successful"
        )
        
        return integrated_result
    
    def _generate_summary(self, results: List[AgentResult]) -> str:
        """
        生成结果摘要
        
        Args:
            results: Agent执行结果列表
            
        Returns:
            str: 摘要文本
        """
        success_count = sum(1 for r in results if r.success)
        total_count = len(results)
        
        summary_parts = []
        summary_parts.append(f"执行了 {total_count} 个任务")
        summary_parts.append(f"成功 {success_count} 个")
        
        if success_count < total_count:
            summary_parts.append(f"失败 {total_count - success_count} 个")
        
        # 计算总执行时间
        total_time = sum(r.execution_time for r in results)
        summary_parts.append(f"总耗时 {total_time:.2f} 秒")
        
        return "，".join(summary_parts) + "。"
    
    def _generate_detailed_report(self, results: List[AgentResult], 
                                  original_tasks: List[AgentTask] = None) -> str:
        """
        生成详细报告
        
        Args:
            results: Agent执行结果列表
            original_tasks: 原始任务列表
            
        Returns:
            str: 详细报告
        """
        report_lines = []
        report_lines.append("=" * 60)
        report_lines.append("详细执行报告")
        report_lines.append("=" * 60)
        
        # 创建任务映射
        task_map = {}
        if original_tasks:
            task_map = {task.task_id: task for task in original_tasks}
        
        for i, result in enumerate(results, 1):
            report_lines.append(f"\n任务 {i}: {result.task_id}")
            report_lines.append(f"  执行Agent: {result.agent_id}")
            report_lines.append(f"  状态: {'成功' if result.success else '失败'}")
            report_lines.append(f"  执行时间: {result.execution_time:.2f} 秒")
            
            # 添加任务描述
            if result.task_id in task_map:
                task = task_map[result.task_id]
                report_lines.append(f"  任务描述: {task.description}")
            
            # 添加输出
            if result.output:
                output_preview = result.output[:200] + "..." if len(result.output) > 200 else result.output
                report_lines.append(f"  输出: {output_preview}")
            
            # 添加错误信息
            if not result.success and result.error_message:
                report_lines.append(f"  错误: {result.error_message}")
            
            # 添加元数据
            if result.metadata:
                report_lines.append(f"  元数据: {result.metadata}")
        
        # 添加统计信息
        report_lines.append("\n" + "=" * 60)
        report_lines.append("统计信息")
        report_lines.append("=" * 60)
        success_count = sum(1 for r in results if r.success)
        total_time = sum(r.execution_time for r in results)
        avg_time = total_time / len(results) if results else 0
        
        report_lines.append(f"成功率: {success_count}/{len(results)} ({success_count/len(results)*100:.1f}%)")
        report_lines.append(f"总执行时间: {total_time:.2f} 秒")
        report_lines.append(f"平均执行时间: {avg_time:.2f} 秒")
        
        return "\n".join(report_lines)
    
    integrate_parallel = integrate  # 并行整合与普通整合相同
    
    def integrate_sequential(self, results: List[AgentResult]) -> Dict[str, Any]:
        """
        顺序整合结果（考虑任务执行顺序）
        
        Args:
            results: Agent执行结果列表
            
        Returns:
            Dict[str, Any]: 整合后的结果
        """
        self.logger.info("Integrating results in sequential mode")
        
        # 按时间戳排序
        sorted_results = sorted(results, key=lambda r: r.timestamp)
        
        # 检查是否有失败的任务
        failed_index = -1
        for i, result in enumerate(sorted_results):
            if not result.success:
                failed_index = i
                break
        
        # 如果有失败的任务，后续任务可能未执行
        if failed_index >= 0:
            self.logger.warning(f"Task {failed_index} failed, stopping sequential integration")
            sorted_results = sorted_results[:failed_index + 1]
        
        return self.integrate(sorted_results)
    
    def integrate_competitive(self, results: List[AgentResult]) -> Dict[str, Any]:
        """
        竞争整合结果（选择最佳结果）
        
        Args:
            results: Agent执行结果列表
            
        Returns:
            Dict[str, Any]: 整合后的结果
        """
        self.logger.info("Integrating results in competitive mode")
        
        if not results:
            return {
                "success": False,
                "error": "No results to integrate",
                "summary": "No results provided"
            }
        
        # 选择成功的结果
        successful_results = [r for r in results if r.success]
        
        if not successful_results:
            # 如果都失败，选择执行时间最短的（可能是最接近完成的）
            best_result = min(results, key=lambda r: r.execution_time)
        else:
            # 选择执行时间最短的成功结果
            best_result = min(successful_results, key=lambda r: r.execution_time)
        
        return {
            "success": best_result.success,
            "best_result": best_result.to_dict(),
            "all_results": [r.to_dict() for r in results],
            "selection_criteria": "shortest execution time among successful results",
            "timestamp": datetime.now().isoformat(),
            "summary": f"从 {len(results)} 个结果中选择了最佳结果"
        }
    
    def integrate_hierarchical(self, results: List[AgentResult], 
                              task_hierarchy: Dict[str, List[str]] = None) -> Dict[str, Any]:
        """
        层级整合结果（考虑任务层级关系）
        
        Args:
            results: Agent执行结果列表
            task_hierarchy: 任务层级关系
            
        Returns:
            Dict[str, Any]: 整合后的结果
        """
        self.logger.info("Integrating results in hierarchical mode")
        
        # 如果没有层级信息，使用普通整合
        if not task_hierarchy:
            return self.integrate(results)
        
        # 按层级组织结果
        hierarchical_results = {}
        
        for result in results:
            # 简化的层级分配
            level = 0
            for level_name, task_ids in task_hierarchy.items():
                if result.task_id in task_ids:
                    level = int(level_name.replace("level_", ""))
                    break
            
            if level not in hierarchical_results:
                hierarchical_results[level] = []
            hierarchical_results[level].append(result)
        
        # 按层级整合
        integrated_levels = {}
        for level in sorted(hierarchical_results.keys()):
            level_results = hierarchical_results[level]
            integrated_levels[f"level_{level}"] = {
                "success": all(r.success for r in level_results),
                "result_count": len(level_results),
                "results": [r.to_dict() for r in level_results]
            }
        
        return {
            "success": all(data["success"] for data in integrated_levels.values()),
            "hierarchical_results": integrated_levels,
            "timestamp": datetime.now().isoformat(),
            "summary": f"整合了 {len(integrated_levels)} 个层级的结果"
        }
    
    def merge_outputs(self, outputs: List[str], mode: str = "concatenate") -> str:
        """
        合并多个输出文本
        
        Args:
            outputs: 输出文本列表
            mode: 合并模式 (concatenate, smart_merge)
            
        Returns:
            str: 合并后的文本
        """
        if not outputs:
            return ""
        
        if mode == "concatenate":
            return "\n\n".join(outputs)
        elif mode == "smart_merge":
            # 简化的智能合并
            return self._smart_merge_outputs(outputs)
        else:
            return "\n\n".join(outputs)
    
    def _smart_merge_outputs(self, outputs: List[str]) -> str:
        """智能合并输出"""
        # 去重
        unique_outputs = []
        seen = set()
        
        for output in outputs:
            output_hash = hash(output)
            if output_hash not in seen:
                seen.add(output_hash)
                unique_outputs.append(output)
        
        return "\n\n".join(unique_outputs)
