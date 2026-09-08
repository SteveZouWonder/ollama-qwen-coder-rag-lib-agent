"""ReActEngine 分层系统提示（内置 / Skills / 项目附加规范 / 角色说明）、allowed_tools、max_iterations。"""
from unittest.mock import MagicMock, patch

import pytest

import react_engine
from react_engine import ReActEngine, build_system_prompt, SYSTEM_PROMPT_TEMPLATE
from agent_tools import registry
from conversation_context import estimate_tokens


class FakeContext:
    def __init__(self):
        self.recorded = []

    def build_messages(self, system_prompt=None):
        return [{"role": "system", "content": system_prompt or ""}]

    def record(self, user, assistant, **kw):
        self.recorded.append((user, assistant))

    def clear(self):
        return True


PROJECT_RULES = "# 项目规范\n必须遵守 X。\n{tool_descriptions}\n"


@pytest.fixture
def project_file(monkeypatch):
    monkeypatch.setattr(react_engine, "read_project_rules", lambda: PROJECT_RULES)


@pytest.fixture
def no_skills(monkeypatch):
    monkeypatch.setenv("CODE_AGENT_SKILLS", "off")


@pytest.fixture
def fake_skills(monkeypatch):
    monkeypatch.setattr(react_engine, "_render_skills", lambda role: f"SKILL for {role}")


class TestRegistryDescriptions:
    def test_compact_lists_one_line_per_tool_with_optional_marker(self):
        text = registry.get_descriptions(names={"read_file", "write_file"}, compact=True)
        lines = text.splitlines()
        assert len(lines) == 2
        assert lines[0].startswith("- read_file(path, offset?, limit?): ")
        assert "[需确认]" in [l for l in lines if l.startswith("- write_file")][0]

    def test_names_filter_full_format(self):
        text = registry.get_descriptions(names={"read_file"})
        assert "工具名: read_file" in text and "工具名: write_file" not in text

    def test_compact_all_is_much_smaller(self):
        full = registry.get_descriptions()
        compact = registry.get_descriptions(compact=True)
        assert len(compact) < len(full) / 2

    def test_read_system_prompt_tool_removed(self):
        assert "read_system_prompt" not in registry.tools
        assert "read_system_prompt" not in registry.get_descriptions(compact=True)


class TestBuildSystemPrompt:
    def test_builtin_under_budget_without_skills(self, no_skills):
        prompt = build_system_prompt(mode="builtin")
        assert estimate_tokens(prompt) <= 1500
        assert "输出协议" in prompt and "安全规则" in prompt and "工具速查" in prompt
        # F9 P0-4：事实规则位于安全规则之前
        assert "=== 事实规则 ===" in prompt
        assert prompt.index("=== 事实规则 ===") < prompt.index("=== 安全规则 ===")
        assert "先用工具重新核实" in prompt and "不是给你的指令" in prompt
        assert "[格式错误]" in prompt and "不要重复调用" in prompt
        assert "项目附加规范" not in prompt and "=== Skills ===" not in prompt

    def test_builtin_ignores_project_file(self, project_file, no_skills):
        prompt = build_system_prompt(mode="builtin")
        assert "必须遵守 X" not in prompt

    def test_skills_layer_between_builtin_and_rules(self, project_file, fake_skills):
        prompt = build_system_prompt(mode="append", role="agent")
        assert prompt.index("输出协议") < prompt.index("=== Skills ===") < prompt.index("=== 项目附加规范 ===")
        assert "SKILL for agent" in prompt

    def test_skills_injected_in_builtin_mode_for_sub_roles(self, project_file, fake_skills):
        prompt = build_system_prompt(mode="builtin", role="code", extra="你是代码专家")
        assert "=== Skills ===" in prompt and "SKILL for code" in prompt
        assert "项目附加规范" not in prompt
        assert prompt.index("=== Skills ===") < prompt.index("=== 角色说明 ===")

    def test_skills_failure_is_tolerated(self, monkeypatch):
        import prompt_assets
        monkeypatch.setattr(prompt_assets, "render_skills", lambda role: (_ for _ in ()).throw(RuntimeError("x")))
        prompt = build_system_prompt(mode="builtin")
        assert "输出协议" in prompt and "=== Skills ===" not in prompt

    def test_append_adds_project_rules_after_builtin(self, project_file, no_skills):
        prompt = build_system_prompt(mode="append")
        assert prompt.index("输出协议") < prompt.index("=== 项目附加规范 ===")
        assert "必须遵守 X" in prompt
        assert "（见上方工具列表）" in prompt

    def test_append_truncates(self, no_skills, monkeypatch):
        monkeypatch.setattr(react_engine, "read_project_rules", lambda: "R" * 10000)
        monkeypatch.setattr(react_engine, "SYSTEM_PROMPT_EXTRA_MAX_CHARS", 500)
        prompt = build_system_prompt(mode="append")
        assert "项目规范已截断" in prompt
        assert prompt.count("R") < 600

    def test_replace_mode_is_treated_as_append(self, project_file, no_skills):
        prompt = build_system_prompt(mode="replace")
        assert "输出协议" in prompt and "=== 项目附加规范 ===" in prompt
        assert not prompt.startswith("# 项目规范")

    def test_append_without_file_is_builtin(self, no_skills, monkeypatch):
        monkeypatch.setattr(react_engine, "read_project_rules", lambda: None)
        prompt = build_system_prompt(mode="append")
        assert "输出协议" in prompt and "项目附加规范" not in prompt

    def test_tools_filter_and_extra(self, no_skills):
        prompt = build_system_prompt(tools={"read_file"}, extra="你是审计员", mode="builtin")
        assert "- read_file(" in prompt and "- write_file(" not in prompt
        assert prompt.rstrip().endswith("=== 角色说明 ===\n你是审计员")

    def test_env_mode(self, monkeypatch, project_file, no_skills):
        monkeypatch.setenv("CODE_AGENT_PROMPT_MODE", "builtin")
        assert "必须遵守 X" not in build_system_prompt()
        monkeypatch.setenv("CODE_AGENT_PROMPT_MODE", "append")
        assert "必须遵守 X" in build_system_prompt()
        monkeypatch.setenv("CODE_AGENT_PROMPT_MODE", "bogus")
        assert react_engine._prompt_mode() == "append"
        monkeypatch.setenv("CODE_AGENT_PROMPT_MODE", "replace")
        assert react_engine._prompt_mode() == "append"

    def test_template_placeholder(self):
        assert "{tool_descriptions}" in SYSTEM_PROMPT_TEMPLATE

    def test_legacy_alias(self):
        assert react_engine.read_system_prompt_from_file is react_engine.read_project_rules


class TestRealPromptAssets:
    """使用仓库内真实 prompts/ 目录（不 mock），保证资产与引擎接得上。"""

    def test_default_agent_prompt_has_all_layers(self, monkeypatch):
        monkeypatch.delenv("CODE_AGENT_SKILLS", raising=False)
        monkeypatch.delenv("AGENT_PROMPTS_DIR", raising=False)
        prompt = build_system_prompt(mode="append", role="agent")
        assert "=== Skills ===" in prompt and "Core Skill" in prompt
        assert "=== 项目附加规范 ===" in prompt and "Cerebro Project Rules" in prompt
        assert "已截断" not in prompt and "truncated" not in prompt

    def test_sub_role_prompt_has_skills_but_no_rules(self, monkeypatch):
        monkeypatch.delenv("CODE_AGENT_SKILLS", raising=False)
        prompt = build_system_prompt(mode="builtin", role="code", extra="R")
        assert "=== Skills ===" in prompt and "项目附加规范" not in prompt

    def test_total_prompt_within_reasonable_budget(self, monkeypatch):
        monkeypatch.delenv("CODE_AGENT_SKILLS", raising=False)
        prompt = build_system_prompt(mode="append", role="agent")
        # 4B 模型 num_ctx=16384，系统提示应远低于 1/4
        assert estimate_tokens(prompt) <= 3500


class TestEngineParams:
    def test_defaults(self):
        eng = ReActEngine(context=FakeContext())
        assert eng.allowed_tools is None
        assert eng.max_iterations == react_engine.Config.MAX_ITERATIONS
        assert eng.system_prompt_extra == ""
        assert eng.role == "agent"

    def test_role_passed_to_prompt(self, fake_skills):
        eng = ReActEngine(context=FakeContext(), role="Audit", prompt_mode="builtin")
        assert eng.role == "audit"
        assert "SKILL for audit" in eng.system_prompt

    def test_allowed_tools_filter_prompt(self, no_skills):
        eng = ReActEngine(context=FakeContext(), allowed_tools=["read_file"],
                          system_prompt_extra="角色 R", max_iterations=3, prompt_mode="builtin")
        assert eng.allowed_tools == {"read_file"}
        assert eng.max_iterations == 3
        assert "- read_file(" in eng.system_prompt
        assert "- execute_command(" not in eng.system_prompt
        assert "角色 R" in eng.system_prompt

    @patch("react_engine.registry")
    @patch("react_engine.requests.post")
    def test_disallowed_tool_is_rejected_not_executed(self, mock_post, mock_registry):
        mock_registry.get_descriptions.return_value = "tools"
        r1 = MagicMock()
        r1.json.return_value = {"message": {"content": 'Thought: t\nAction: execute_command\nAction Input: {"command": "ls"}'}}
        r2 = MagicMock()
        r2.json.return_value = {"message": {"content": "Final Answer: 用 read_file 完成"}}
        mock_post.side_effect = [r1, r2]
        eng = ReActEngine(context=FakeContext(), allowed_tools={"read_file"}, prompt_mode="builtin")
        answer = eng.chat("do")
        assert "完成" in answer
        mock_registry.execute.assert_not_called()
        rejected = eng.step_log[0]
        assert rejected["confirmed"] is False
        assert "不在当前允许的工具集内" in rejected["observation"]
        obs_msgs = [m for m in eng.messages if m["role"] == "user" and "Observation" in m["content"]]
        assert "read_file" in obs_msgs[0]["content"]

    @patch("react_engine.requests.post")
    def test_max_iterations_param(self, mock_post):
        def resp(text):
            r = MagicMock()
            r.json.return_value = {"message": {"content": text}}
            return r

        mock_post.side_effect = [
            resp('Thought: t\nAction: read_file\nAction Input: {"path": "a"}'),
            resp('Thought: t\nAction: read_file\nAction Input: {"path": "b"}'),
            resp("已完成：读了 a、b；未完成：无；建议：无"),
        ]
        with patch("react_engine.registry.execute", return_value="ok"):
            eng = ReActEngine(context=FakeContext(), max_iterations=2, prompt_mode="builtin")
            steps = []
            eng.on_step = lambda e: steps.append(e) if not e.get("transient") else None
            out = eng.chat("x")
        assert out.startswith("⚠️ 未完成")
        assert "读了 a、b" in out
        assert mock_post.call_count == 3
        assert steps[0]["total"] == 2
