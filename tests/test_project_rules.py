"""仓库内置提示资产 prompts/ 的一致性校验：

- 文件存在、非空、长度在注入上限内；
- PROJECT_RULES 中列出的工具与参数名和 ``agent_tools.registry`` 一致；
- Skill frontmatter 合法、roles 在已知集合内；
- 不再引用已删除的 ``.devin/`` 路径或 ``read_system_prompt`` 工具；
- 与引擎组装后不触发截断。
"""
import re
from pathlib import Path

import pytest

import prompt_assets as pa
import react_engine
from agent_tools import registry
from conversation_context import estimate_tokens

ROOT = Path(__file__).resolve().parent.parent
PROMPTS = ROOT / "prompts"
RULES = PROMPTS / "system" / "PROJECT_RULES.md"
CORE_SKILL = PROMPTS / "skills" / "core" / "SKILL.md"

# PROJECT_RULES 「Parameter names」段里 `tool(a, b?, c)` 形式的声明
_SIG_RE = re.compile(r"\b([a-z_]+)\(([^)]*)\)")


@pytest.fixture(autouse=True)
def real_assets(monkeypatch):
    monkeypatch.delenv("AGENT_PROMPTS_DIR", raising=False)
    monkeypatch.delenv("CODE_AGENT_SKILLS", raising=False)
    monkeypatch.delenv("SKILL_MAX_CHARS", raising=False)


def _param_section(text: str) -> str:
    m = re.search(r"## Parameter names.*?(?=\n## |\Z)", text, re.DOTALL)
    assert m, "PROJECT_RULES.md 缺少 Parameter names 段"
    return m.group(0)


class TestFilesExist:
    def test_layout(self):
        assert RULES.is_file() and CORE_SKILL.is_file() and (PROMPTS / "README.md").is_file()
        assert pa.project_rules_path() == RULES

    def test_rules_within_injection_limit(self):
        text = RULES.read_text(encoding="utf-8")
        assert text.strip()
        assert len(text) <= react_engine.SYSTEM_PROMPT_EXTRA_MAX_CHARS, "PROJECT_RULES 超过注入上限会被截断"
        # 规范是补充而非完整提示：不能再带工具占位符
        assert "{tool_descriptions}" not in text

    def test_skills_within_limit(self):
        rendered = pa.render_skills("agent")
        assert rendered and "truncated" not in rendered
        assert len(rendered) <= pa.skill_max_chars()


class TestNoStaleReferences:
    @pytest.mark.parametrize("path", [RULES, CORE_SKILL, PROMPTS / "README.md"])
    def test_no_devin_or_removed_tool(self, path):
        text = path.read_text(encoding="utf-8")
        assert ".devin" not in text
        assert "read_system_prompt" not in text
        assert "todo_write" not in text

    def test_no_developer_process_in_prompts(self):
        """产品提示不得写开发者流程（覆盖率 / 读项目文档），否则诱导 Agent 读项目文件。"""
        for path in (RULES, CORE_SKILL):
            text = path.read_text(encoding="utf-8").lower()
            for banned in ("coverage", "覆盖率", "agents.md", "ai_knowledge_base", "changelog"):
                assert banned not in text, f"{path.name} 含开发者规范词 {banned!r}"


class TestRulesMatchRegistry:
    def test_tool_names_and_params_match_registry(self):
        section = _param_section(RULES.read_text(encoding="utf-8"))
        found = _SIG_RE.findall(section)
        assert found, "Parameter names 段未解析出任何工具签名"
        for tool, params in found:
            assert tool in registry.tools, f"PROJECT_RULES 引用了未注册工具 {tool}"
            declared = [p.strip().rstrip("?") for p in params.split(",") if p.strip()]
            actual = set(registry.tools[tool]["parameters"].keys())
            for p in declared:
                assert p in actual, f"{tool}: 参数 {p!r} 不在 registry 定义 {sorted(actual)} 中"
            # 必填参数必须全部列出
            required = {
                name for name, desc in registry.tools[tool]["parameters"].items() if "必填" in desc
            }
            assert required <= set(declared), f"{tool}: 缺少必填参数 {sorted(required - set(declared))}"

    def test_kb_markers_documented(self):
        text = RULES.read_text(encoding="utf-8")
        for marker in ("[知识库概览]", "[知识库命中]", "[知识库无相关内容]"):
            assert marker in text

    def test_skill_uses_registered_tool_names(self):
        text = CORE_SKILL.read_text(encoding="utf-8")
        mentioned = set(re.findall(r"\b([a-z]+_[a-z_]+)\b", text))
        # 只校验以工具命名风格出现且确实像工具名的 token
        known_prefixes = ("read_", "write_", "execute_", "list_", "search_", "query_", "add_",
                          "web_", "analyze_", "ast_", "database_", "knowledge_graph_")
        for name in mentioned:
            if name.startswith(known_prefixes) and not name.endswith("_*") and "_dirs" not in name:
                base = name.rstrip("*").rstrip("_")
                if base in ("database", "knowledge_graph"):
                    continue
                assert base in registry.tools, f"SKILL.md 提到未注册工具 {name}"


class TestSkillFrontmatter:
    def test_core_skill_frontmatter(self):
        meta, body = pa.parse_frontmatter(CORE_SKILL.read_text(encoding="utf-8"))
        assert meta.get("name") == "core"
        assert meta.get("description")
        assert pa._normalize_roles(meta.get("roles")) is None  # all
        assert body.lstrip().startswith("# ")

    def test_all_shipped_skills_have_valid_roles(self):
        for skill in pa.load_skills():
            if skill.roles is not None:
                assert skill.roles <= set(pa.ALL_ROLES), f"{skill.name}: 未知角色 {skill.roles - set(pa.ALL_ROLES)}"


class TestAssembledPrompt:
    def test_agent_prompt_layers_and_budget(self):
        prompt = react_engine.build_system_prompt(mode="append", role="agent")
        assert "=== Skills ===" in prompt and "=== 项目附加规范 ===" in prompt
        assert "已截断" not in prompt and "truncated" not in prompt
        assert estimate_tokens(prompt) <= 3500

    @pytest.mark.parametrize("role", ["code", "test", "doc", "audit"])
    def test_sub_roles_get_skills(self, role):
        prompt = react_engine.build_system_prompt(mode="builtin", role=role, extra="R")
        assert "=== Skills ===" in prompt and "Core Skill" in prompt
