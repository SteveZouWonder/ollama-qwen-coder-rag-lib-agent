#!/usr/bin/env python3
"""test_intent_router.py — F8 P3-1 入口智能路由：

- 规则优先：路径/代码围栏/命令式动词 → agent；疑问句/总结比较/"什么是"开头 → rag（中英文）；
- 模糊（冲突或无信号）→ 恰好一次 LLM 一词判定（``num_predict=4``、``timeout=5``）；
- LLM 异常/超时/乱输出 → 回退 rag；知识库不可用且模糊 → agent 且 0 次 LLM。
"""
import pytest

import intent_router as ir
from intent_router import RouteDecision, classify_intent


def _stub(answer=None, exc=None):
    """返回 (fn, calls)：fn 记录调用参数并返回 answer / 抛 exc。"""
    calls = []

    def fn(prompt, num_predict=None, timeout=None):
        calls.append({"prompt": prompt, "num_predict": num_predict, "timeout": timeout})
        if exc is not None:
            raise exc
        return answer

    return fn, calls


def _never(prompt, **kw):
    raise AssertionError("LLM 不应被调用")


# ==================== 规则：agent ====================

AGENT_CASES = [
    "修改 main.py 加日志",
    "帮我重构 src/query_interface.py 的 parse_command",
    "运行 ./run_tests.sh",
    "清理 ~/Downloads 里的临时文件",
    "把 *.log 全部删除",
    "在 /tmp/demo 目录下新建一个 README",
    "```python\nprint('hi')\n```\n跑一下这段代码",
    "写一个函数把列表去重",
    "安装 requests 依赖",
    "重命名 old_name.txt 为 new_name.txt",
    "实现一个 LRU 缓存",
    "修复登录接口的 500 错误",
    "提交当前改动并部署到测试环境",
    "create a script that parses nginx logs",
    "run the unit tests and fix failures",
    "refactor utils.py to remove duplication",
    "implement rate limiting for the API",
    "install black and format the repo",
    "delete the temp directory",
    "rename foo.txt to bar.txt",
    "write a small CLI to count words",
]


@pytest.mark.parametrize("text", AGENT_CASES)
def test_rule_agent(text):
    d = classify_intent(text, kb_available=True, complete=_never)
    assert d.mode == "agent"
    assert d.reason.startswith("规则：")


# ==================== 规则：rag ====================

RAG_CASES = [
    "什么是 RAG？",
    "RAG 和微调的区别是什么",
    "为什么向量检索需要 rerank",
    "如何理解注意力机制",
    "这份文档是否提到了退款政策",
    "DJI OSMO 360 多少钱",
    "请总结这份文档的要点",
    "比较 Redis 与 Memcached 的优缺点",
    "解释一下事务隔离级别",
    "介绍一下这个项目",
    "知识库里有哪些内容呢",
    "Python 的 GIL 是什么意思吗",
    "What is a vector database?",
    "Why does cosine similarity work for embeddings",
    "Explain the difference between BM25 and dense retrieval",
    "Summarize the onboarding document",
    "Compare PostgreSQL and MySQL",
    "Tell me about the refund policy",
]


@pytest.mark.parametrize("text", RAG_CASES)
def test_rule_rag(text):
    d = classify_intent(text, kb_available=True, complete=_never)
    assert d.mode == "rag"
    assert d.reason.startswith("规则：")


def test_url_path_not_treated_as_local_file():
    d = classify_intent("https://example.com/a/b.py 这个链接讲的是什么", complete=_never)
    assert d.mode == "rag"


def test_return_type_iterable_and_stable():
    d = classify_intent("什么是 RAG？", complete=_never)
    assert isinstance(d, RouteDecision)
    mode, reason = d
    assert mode == "rag" and isinstance(reason, str) and reason


def test_signal_helpers():
    assert ir.agent_signals("") == [] and ir.rag_signals("") == []
    assert any("代码围栏" in h for h in ir.agent_signals("```\nx\n```"))
    assert any("疑问句" in h for h in ir.rag_signals("行吗？"))


# ==================== 模糊 → LLM ====================

class TestAmbiguous:
    def test_no_signal_calls_llm_once_with_limits(self):
        fn, calls = _stub(answer="agent")
        d = classify_intent("你好啊", kb_available=True, complete=fn)
        assert d.mode == "agent" and "LLM 判定" in d.reason
        assert len(calls) == 1
        assert calls[0]["num_predict"] == 4 and calls[0]["timeout"] == 5
        assert "你好啊" in calls[0]["prompt"] and "rag 或 agent" in calls[0]["prompt"]

    def test_conflict_calls_llm_once(self):
        fn, calls = _stub(answer="rag")
        # 既有路径/动词又是疑问句 → 冲突
        d = classify_intent("为什么运行 main.py 会报错？", kb_available=True, complete=fn)
        assert d.mode == "rag" and "规则冲突" in d.reason
        assert len(calls) == 1

    def test_llm_output_case_and_whitespace_tolerant(self):
        fn, _ = _stub(answer="  Agent\n")
        assert classify_intent("helloworld", complete=fn).mode == "agent"
        fn2, _ = _stub(answer="<think>x</think>rag")
        assert classify_intent("helloworld", complete=fn2).mode == "rag"

    def test_llm_exception_falls_back_rag(self):
        fn, calls = _stub(exc=ConnectionError("down"))
        d = classify_intent("helloworld", kb_available=True, complete=fn)
        assert d.mode == "rag" and "默认 RAG" in d.reason
        assert len(calls) == 1

    def test_llm_timeout_falls_back_rag(self):
        import requests
        fn, _ = _stub(exc=requests.exceptions.Timeout("slow"))
        assert classify_intent("helloworld", complete=fn).mode == "rag"

    def test_llm_garbage_falls_back_rag(self):
        for junk in ("maybe", "", "不知道", "ragagent", None):
            fn, _ = _stub(answer=junk)
            assert classify_intent("helloworld", complete=fn).mode == "rag", junk

    def test_kb_unavailable_ambiguous_goes_agent_without_llm(self):
        fn, calls = _stub(answer="rag")
        d = classify_intent("你好啊", kb_available=False, complete=fn)
        assert d.mode == "agent" and "知识库不可用" in d.reason
        assert calls == []

    def test_kb_unavailable_but_clear_rag_rule_still_rag(self):
        d = classify_intent("什么是 RAG？", kb_available=False, complete=_never)
        assert d.mode == "rag"

    def test_default_llm_is_blocked_in_tests_and_falls_back(self):
        # conftest 全局拦截 → 默认调用抛异常 → 回退 rag
        assert classify_intent("helloworld", kb_available=True).mode == "rag"

    def test_default_llm_uses_complete_text(self, monkeypatch):
        import collaboration.llm_helper as helper
        seen = {}

        def fake(prompt, num_predict=512, timeout=None, temperature=0.2):
            seen.update(prompt=prompt, num_predict=num_predict, timeout=timeout)
            return "agent"

        monkeypatch.setattr(helper, "complete_text", fake)
        monkeypatch.setattr(ir, "_llm_complete", ir.default_llm_complete)
        assert ir.llm_classify("helloworld") == "agent"
        assert seen["num_predict"] == 4 and seen["timeout"] == 5


def test_parse_intent_word():
    assert ir.parse_intent_word("RAG") == "rag"
    assert ir.parse_intent_word("答案：agent。") == "agent"
    assert ir.parse_intent_word("") is None
    assert ir.parse_intent_word("unknown") is None
