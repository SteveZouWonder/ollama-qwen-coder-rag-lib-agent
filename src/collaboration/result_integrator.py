"""
结果整合器 - 合并多个Agent的执行结果

在统计之上增加一次 LLM 综合，产出面向用户的 ``answer``；``summary`` 保留统计句。
LLM 不可用时 ``answer`` 回退为各子任务输出的拼接。竞争模式由 LLM 评审选优，
失败回退"最长成功输出"。
"""
from typing import List, Dict, Any, Optional, Callable
import logging
from agents.agent_types import AgentResult, AgentTask
from datetime import datetime
from .llm_helper import complete_json, complete_text, strip_think, truncate


INTEGRATE_PROMPT = """以下是多个 Agent 对同一请求的分工结果。写一段面向用户的最终回答：先给结论，再按子任务列要点；失败项如实说明。不要复述统计，不要编造结果里没有的内容。
请求：{request}
{subtask_outputs}"""

REVIEW_PROMPT = """同一任务有多个候选答案，选出最正确、完整、可执行的一个。只输出 JSON：{{"best": 序号, "reason": "一句话"}}
任务：{request}
{candidates}"""

# 整合 prompt 中每个子任务输出的字符预算（按子任务数均分，上下限见下）
INTEGRATE_TOTAL_CHARS = 6000
INTEGRATE_MIN_PER_TASK = 600
REVIEW_PER_CANDIDATE_CHARS = 1500


class ResultIntegrator:
    """结果整合器，负责合并多个Agent的执行结果"""
    
    def __init__(self, complete: Optional[Callable[[str], str]] = None,
                 use_llm: bool = True, llm_timeout: int = 120):
        """初始化结果整合器

        Args:
            complete: 可注入的 LLM 补全函数（测试用）；None 时用全局模型。
            use_llm: 是否调用 LLM 综合 answer / 评审候选；False 则只用回退逻辑。
            llm_timeout: LLM 调用超时（秒）。
        """
        self.logger = logging.getLogger("ResultIntegrator")
        self._complete = complete
        self.use_llm = use_llm
        self.llm_timeout = llm_timeout
        self.last_answer_method: str = "concat"
    
    def integrate(self, results: List[AgentResult], original_tasks: List[AgentTask] = None,
                  request: str = "") -> Dict[str, Any]:
        """
        整合多个Agent的执行结果
        
        Args:
            results: Agent执行结果列表
            original_tasks: 原始任务列表（可选，用于上下文）
            request: 用户原始请求（用于 LLM 综合）
            
        Returns:
            Dict[str, Any]: 整合后的结果（含 ``answer`` / ``sources``）
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
            "tasks": [
                {"task_id": t.task_id, "task_type": t.task_type, "description": t.description}
                for t in (original_tasks or [])
            ],
            "timestamp": datetime.now().isoformat(),
            "summary": self._generate_summary(results),
            "detailed_report": self._generate_detailed_report(results, original_tasks),
            "sources": self.merge_sources(results),
            "notices": self.merge_notices(results),
        }
        integrated_result["answer"] = self._synthesize_answer(results, original_tasks, request)
        integrated_result["answer_method"] = self.last_answer_method
        
        self.logger.info(
            f"Integration complete: {success_count}/{total_count} successful"
        )
        
        return integrated_result

    # ---------- 综合回答 ----------

    @staticmethod
    def merge_sources(results: List[AgentResult]) -> List[Dict[str, Any]]:
        """合并各子任务的结构化来源并按 (kind, file/url) 去重。"""
        merged: List[Dict[str, Any]] = []
        seen = set()
        for r in results:
            for src in getattr(r, "sources", None) or []:
                if not isinstance(src, dict):
                    continue
                key = (src.get("kind"), src.get("file") or src.get("url") or src.get("title"))
                if key in seen:
                    continue
                seen.add(key)
                item = dict(src)
                item.setdefault("agent_id", r.agent_id)
                merged.append(item)
        return merged

    @staticmethod
    def merge_notices(results: List[AgentResult]) -> List[Dict[str, Any]]:
        """合并各子任务（RAGAgent）透传的结构化提示，按 (code, text) 去重（F9 P0-5）。"""
        merged: List[Dict[str, Any]] = []
        seen = set()
        for r in results:
            meta = getattr(r, "metadata", None) or {}
            for n in meta.get("notices") or []:
                if not isinstance(n, dict):
                    continue
                key = (n.get("code"), n.get("text"))
                if key in seen:
                    continue
                seen.add(key)
                merged.append(dict(n))
        return merged

    @staticmethod
    def _task_desc(task_map: Dict[str, AgentTask], result: AgentResult, idx: int) -> str:
        task = task_map.get(result.task_id)
        if task is not None and task.description:
            return task.description
        return f"子任务 {idx}"

    def _format_subtask_outputs(self, results: List[AgentResult],
                                task_map: Dict[str, AgentTask]) -> str:
        per_task = max(INTEGRATE_MIN_PER_TASK, INTEGRATE_TOTAL_CHARS // max(1, len(results)))
        blocks = []
        for i, r in enumerate(results, 1):
            status = "成功" if r.success else f"失败（{r.error_message or '未知错误'}）"
            body = truncate((r.output or "").strip(), per_task) if r.success else ""
            blocks.append(
                f"[子任务 {i}] {self._task_desc(task_map, r, i)}\n执行者: {r.agent_id} · 状态: {status}"
                + (f"\n输出:\n{body}" if body else "")
            )
        return "\n\n".join(blocks)

    def _concat_answer(self, results: List[AgentResult], task_map: Dict[str, AgentTask]) -> str:
        """LLM 不可用时的回退：按子任务拼接输出，失败项如实标注。"""
        parts = []
        for i, r in enumerate(results, 1):
            desc = self._task_desc(task_map, r, i)
            if r.success:
                parts.append(f"**{desc}**（{r.agent_id}）\n\n{(r.output or '').strip()}")
            else:
                parts.append(f"**{desc}**（{r.agent_id}）❌ 失败：{r.error_message or '未知错误'}")
        return "\n\n".join(parts).strip()

    def _synthesize_answer(self, results: List[AgentResult],
                           original_tasks: Optional[List[AgentTask]], request: str) -> str:
        task_map = {t.task_id: t for t in (original_tasks or [])}
        self.last_answer_method = "concat"
        # 单一子任务且成功：直接采用其输出，省一次 LLM 往返
        if len(results) == 1 and results[0].success:
            self.last_answer_method = "direct"
            return (results[0].output or "").strip()
        if not self.use_llm:
            return self._concat_answer(results, task_map)
        prompt = INTEGRATE_PROMPT.format(
            request=truncate(request or "（未提供）", 800),
            subtask_outputs=self._format_subtask_outputs(results, task_map),
        )
        try:
            if self._complete is not None:
                text = self._complete(prompt)
            else:
                text = complete_text(prompt, num_predict=1024, timeout=self.llm_timeout)
            text = strip_think(text)
        except Exception as e:  # noqa: BLE001 - 回退拼接
            self.logger.warning(f"LLM 综合失败，回退拼接: {e}")
            text = ""
        if text.strip():
            self.last_answer_method = "llm"
            return text.strip()
        return self._concat_answer(results, task_map)
    
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
    
    def integrate_parallel(self, results: List[AgentResult], original_tasks: List[AgentTask] = None,
                           request: str = "") -> Dict[str, Any]:
        """并行整合：子任务彼此独立，按原顺序整合（与 ``integrate`` 相同的产出结构）。"""
        self.logger.info("Integrating results in parallel mode")
        result = self.integrate(results, original_tasks, request=request)
        result["mode"] = "parallel"
        return result
    
    def integrate_sequential(self, results: List[AgentResult], original_tasks: List[AgentTask] = None,
                             request: str = "") -> Dict[str, Any]:
        """
        顺序整合结果（考虑任务执行顺序）
        
        Args:
            results: Agent执行结果列表
            original_tasks: 原始任务列表
            request: 用户原始请求
            
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
        
        result = self.integrate(sorted_results, original_tasks, request=request)
        result["mode"] = "sequential"
        return result

    # ---------- 竞争评审 ----------

    def _review_candidates(self, candidates: List[AgentResult], request: str) -> Optional[Dict[str, Any]]:
        """LLM 评审候选，返回 ``{"best": idx, "reason": str}``；失败返回 None。"""
        if not self.use_llm or len(candidates) < 2:
            return None
        blocks = []
        for i, r in enumerate(candidates):
            blocks.append(f"[候选 {i}]（{r.agent_id}）\n{truncate((r.output or '').strip(), REVIEW_PER_CANDIDATE_CHARS)}")
        prompt = REVIEW_PROMPT.format(request=truncate(request or "（未提供）", 800),
                                      candidates="\n\n".join(blocks))
        data = complete_json(prompt, complete=self._complete, num_predict=128, timeout=self.llm_timeout)
        if not data:
            return None
        best = data.get("best")
        try:
            best = int(best)
        except (TypeError, ValueError):
            return None
        if not 0 <= best < len(candidates):
            return None
        return {"best": best, "reason": str(data.get("reason", "")).strip()}
    
    def integrate_competitive(self, results: List[AgentResult], request: str = "") -> Dict[str, Any]:
        """
        竞争整合结果：LLM 评审各候选选出最佳；评审失败回退"最长成功输出"。
        
        Args:
            results: Agent执行结果列表
            request: 用户原始请求（供评审）
            
        Returns:
            Dict[str, Any]: 整合后的结果（``best_result`` / ``all_results`` /
                ``selection_criteria`` / ``answer`` / ``sources``）
        """
        self.logger.info("Integrating results in competitive mode")
        
        if not results:
            return {
                "success": False,
                "error": "No results to integrate",
                "summary": "No results provided"
            }
        
        successful_results = [r for r in results if r.success]
        candidates = successful_results or list(results)

        review = self._review_candidates(candidates, request) if successful_results else None
        if review is not None:
            best_result = candidates[review["best"]]
            criteria = "LLM 评审选优" + (f"：{review['reason']}" if review.get("reason") else "")
        elif len(successful_results) == 1:
            best_result = successful_results[0]
            criteria = "唯一成功候选"
        elif successful_results:
            best_result = max(successful_results, key=lambda r: len(r.output or ""))
            criteria = "评审不可用，回退为成功候选中输出最完整（最长）者"
        else:
            # 全部失败：没有可比的输出，取错误信息最具体的一个
            best_result = max(results, key=lambda r: len(r.error_message or ""))
            criteria = "全部候选失败，展示错误信息最详细者"
        
        return {
            "success": best_result.success,
            "best_result": best_result.to_dict(),
            "all_results": [r.to_dict() for r in results],
            "results": [r.to_dict() for r in results],
            "selection_criteria": criteria,
            "answer": (best_result.output or "").strip() if best_result.success else "",
            "sources": self.merge_sources([best_result]),
            "notices": self.merge_notices([best_result]),
            "mode": "competitive",
            "timestamp": datetime.now().isoformat(),
            "summary": (
                f"{len(results)} 个 Agent 竞争执行，成功 {len(successful_results)} 个，"
                f"选用 {best_result.agent_id} 的结果（{criteria.split('：')[0]}）。"
            ),
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
