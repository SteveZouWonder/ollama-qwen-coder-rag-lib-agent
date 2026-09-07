"""collaboration.presenter：CLI/Web 共用的多 Agent 结果渲染。"""
from collaboration.presenter import format_multi_agent_result, format_sources_md


def _res(agent, success=True, output="", err="", meta=None, task_id="t", et=1.2):
    return {"agent_id": agent, "success": success, "output": output, "error_message": err,
            "metadata": meta or {}, "task_id": task_id, "execution_time": et}


class TestFormat:
    def test_answer_agents_and_sources(self):
        result = {
            "success": True, "summary": "执行了 2 个任务，成功 2 个。",
            "answer": "快排已实现并通过测试。",
            "successful_results": 2, "total_results": 2,
            "tasks": [{"task_id": "a", "description": "写快排"}, {"task_id": "b", "description": "写测试"}],
            "results": [
                _res("code_agent_1", meta={"steps": 3, "tools": ["write_file", "execute_command"]}, task_id="a"),
                _res("test_agent_1", meta={"steps": 2, "tools": ["write_file"], "incomplete": True, "unverified": True}, task_id="b", et=0),
            ],
            "sources": [{"kind": "kb", "file": "a.md", "score": 0.7}, {"kind": "web", "title": "W", "url": "https://w"}],
        }
        md = format_multi_agent_result(result)
        assert md.startswith("快排已实现并通过测试。")
        assert "**✅ 执行了 2 个任务，成功 2 个。**" in md
        assert "成功 2 / 共 2" in md
        assert "✅ **code_agent_1** · 写快排（3 步，工具: write_file、execute_command，1.2s）" in md
        assert "✅ **test_agent_1** · 写测试（2 步，工具: write_file，未完成，⚠️ 未经验证）" in md
        assert "📄 a.md（相似度 0.700）" in md
        assert "[W](https://w)" in md
        # 有综合回答时不再逐条引用原始输出
        assert "> " not in md

    def test_no_answer_shows_outputs(self):
        result = {"success": True, "summary": "协作完成", "results": [
            _res("code", output="done"), _res("test", output="ok")]}
        md = format_multi_agent_result(result)
        assert "**✅ 协作完成**" in md and "> done" in md and "> ok" in md

    def test_success_no_results(self):
        assert "协作完成" in format_multi_agent_result({"success": True})

    def test_failure_with_details(self):
        result = {"success": False, "summary": "失败了", "error": "e", "answer": "部分结果",
                  "results": [_res("code", success=False, err="timeout")]}
        md = format_multi_agent_result(result)
        assert md.startswith("**❌ 失败了**")
        assert "e" in md and "部分结果" in md
        assert "❌ **code**" in md and "> 错误：timeout" in md

    def test_failure_default_summary(self):
        assert "协作失败" in format_multi_agent_result({"success": False})
        assert "协作失败" in format_multi_agent_result(None)

    def test_competitive_structure(self):
        best = _res("a2", output="B answer", meta={"steps": 1})
        result = {"success": True, "summary": "2 个 Agent 竞争执行", "answer": "B answer",
                  "best_result": best, "all_results": [_res("a1", output="A"), best],
                  "selection_criteria": "LLM 评审选优：更完整"}
        md = format_multi_agent_result(result)
        assert "🏆 选用：**a2** — LLM 评审选优：更完整" in md
        assert "其他候选：" in md and "**a1**" in md

    def test_sources_md(self):
        assert format_sources_md([]) == ""
        code = format_sources_md([{"kind": "kb", "file": "a.py", "score": 0.5, "symbol": "A.run", "start_line": 3, "end_line": 9}])
        assert "📄 a.py · `A.run` · L3-9（相似度 0.500）" in code
        md = format_sources_md([{"kind": "web", "title": "T"}, {"kind": "kb"}])
        assert "🌐 T" in md and "📄 未知" in md
