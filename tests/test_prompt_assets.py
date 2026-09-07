"""prompt_assets：prompts/ 三层解析、PROJECT_RULES 加载、Skill frontmatter / roles / 覆盖 / 截断 / 开关。"""
from pathlib import Path

import pytest

import prompt_assets as pa


def _write_skill(root: Path, name: str, body: str, frontmatter: str = "") -> Path:
    d = root / "skills" / name
    d.mkdir(parents=True, exist_ok=True)
    text = (f"---\n{frontmatter}\n---\n" if frontmatter else "") + body
    (d / "SKILL.md").write_text(text, encoding="utf-8")
    return d / "SKILL.md"


def _write_rules(root: Path, text: str) -> Path:
    d = root / "system"
    d.mkdir(parents=True, exist_ok=True)
    p = d / "PROJECT_RULES.md"
    p.write_text(text, encoding="utf-8")
    return p


@pytest.fixture
def layers(tmp_path, monkeypatch):
    """三层目录：builtin（resource_root）、user（user_data_dir）、extra（env）。"""
    builtin = tmp_path / "builtin" / "prompts"
    user = tmp_path / "user" / "prompts"
    extra = tmp_path / "extra"
    for d in (builtin, user, extra):
        d.mkdir(parents=True)
    import runtime_paths
    monkeypatch.setattr(runtime_paths, "resource_root", lambda: tmp_path / "builtin")
    monkeypatch.setattr(runtime_paths, "user_data_dir", lambda: tmp_path / "user")
    monkeypatch.setenv("AGENT_PROMPTS_DIR", str(extra))
    monkeypatch.delenv("CODE_AGENT_SKILLS", raising=False)
    monkeypatch.delenv("SKILL_MAX_CHARS", raising=False)
    return {"builtin": builtin, "user": user, "extra": extra}


class TestPromptDirs:
    def test_order_low_to_high_and_dedup(self, layers, tmp_path, monkeypatch):
        dirs = pa.prompt_dirs()
        assert dirs == [layers["builtin"], layers["user"], layers["extra"]]
        # 源码运行时 resource_root == user_data_dir → 去重
        import runtime_paths
        monkeypatch.setattr(runtime_paths, "user_data_dir", lambda: tmp_path / "builtin")
        dirs = pa.prompt_dirs()
        assert dirs == [layers["builtin"], layers["extra"]]

    def test_missing_dirs_are_skipped(self, layers):
        (layers["extra"]).rmdir()
        assert pa.prompt_dirs() == [layers["builtin"], layers["user"]]

    def test_extra_env_multiple_and_tilde(self, layers, tmp_path, monkeypatch):
        import os
        second = tmp_path / "second"
        second.mkdir()
        monkeypatch.setenv("AGENT_PROMPTS_DIR", os.pathsep.join([str(layers["extra"]), " ", str(second)]))
        assert pa.prompt_dirs()[-2:] == [layers["extra"], second]


class TestProjectRules:
    def test_none_when_absent(self, layers):
        assert pa.project_rules_path() is None
        assert pa.load_project_rules() is None

    def test_highest_layer_wins(self, layers):
        _write_rules(layers["builtin"], "builtin rules")
        assert pa.load_project_rules() == "builtin rules"
        _write_rules(layers["user"], "user rules")
        assert pa.load_project_rules() == "user rules"
        _write_rules(layers["extra"], "extra rules")
        assert pa.load_project_rules() == "extra rules"
        assert pa.project_rules_path() == layers["extra"] / "system" / "PROJECT_RULES.md"

    def test_blank_file_is_none(self, layers):
        _write_rules(layers["builtin"], "   \n")
        assert pa.load_project_rules() is None


class TestFrontmatter:
    def test_no_frontmatter(self):
        meta, body = pa.parse_frontmatter("# T\nbody")
        assert meta == {} and body == "# T\nbody"

    def test_scalars_inline_list_and_block_list(self):
        text = (
            "---\n"
            "name: core\n"
            "description: 'General rules'\n"
            "roles: [agent, code]\n"
            "tags:\n"
            "  - a\n"
            "  - \"b\"\n"
            "# comment\n"
            "empty: []\n"
            "---\n"
            "BODY\n"
        )
        meta, body = pa.parse_frontmatter(text)
        assert meta["name"] == "core"
        assert meta["description"] == "General rules"
        assert meta["roles"] == ["agent", "code"]
        assert meta["tags"] == ["a", "b"]
        assert meta["empty"] == []
        assert body == "BODY\n"

    def test_unterminated_frontmatter_is_body(self):
        meta, body = pa.parse_frontmatter("---\nname: x\nno end")
        assert meta == {} and body.startswith("---")

    @pytest.mark.parametrize("value,expected", [
        (None, None), ("all", None), ("*", None), ("", None), ([], None),
        ("code", {"code"}), (["Code", " test "], {"code", "test"}), (["all", "code"], None),
    ])
    def test_normalize_roles(self, value, expected):
        assert pa._normalize_roles(value) == expected


class TestLoadSkills:
    def test_sorted_by_dirname_and_named_by_default(self, layers):
        _write_skill(layers["builtin"], "zeta", "Z")
        _write_skill(layers["builtin"], "alpha", "A")
        names = [s.name for s in pa.load_skills()]
        assert names == ["alpha", "zeta"]

    def test_frontmatter_name_and_roles(self, layers):
        p = _write_skill(layers["builtin"], "dir", "B", "name: custom\ndescription: d\nroles: [code]")
        (s,) = pa.load_skills()
        assert s.name == "custom" and s.description == "d" and s.roles == {"code"} and s.path == p
        assert s.applies_to("code") and not s.applies_to("agent") and not s.applies_to(None)

    def test_default_roles_apply_to_everyone(self, layers):
        _write_skill(layers["builtin"], "core", "C")
        (s,) = pa.load_skills()
        assert s.roles is None
        for role in pa.ALL_ROLES + (None, "unknown"):
            assert s.applies_to(role)

    def test_higher_layer_overrides_same_name_keeps_position(self, layers):
        _write_skill(layers["builtin"], "a", "A-builtin")
        _write_skill(layers["builtin"], "b", "B-builtin")
        _write_skill(layers["user"], "a", "A-user")
        _write_skill(layers["extra"], "c", "C-extra")
        skills = pa.load_skills()
        assert [(s.name, s.body) for s in skills] == [("a", "A-user"), ("b", "B-builtin"), ("c", "C-extra")]

    def test_empty_body_and_non_skill_dirs_ignored(self, layers):
        _write_skill(layers["builtin"], "empty", "   ")
        (layers["builtin"] / "skills" / "nodir.txt").write_text("x")
        (layers["builtin"] / "skills" / "nofile").mkdir()
        assert pa.load_skills() == []

    def test_unreadable_file_is_skipped(self, layers, monkeypatch):
        _write_skill(layers["builtin"], "a", "A")
        monkeypatch.setattr(pa, "_read_text", lambda p: None)
        assert pa.load_skills() == []
        assert pa.load_project_rules() is None


class TestRenderSkills:
    def test_joins_applicable_only(self, layers):
        _write_skill(layers["builtin"], "a", "for all")
        _write_skill(layers["builtin"], "b", "for code", "roles: [code]")
        assert pa.render_skills("agent") == "for all"
        assert pa.render_skills("code") == "for all\n\nfor code"
        assert pa.render_skills(None) == "for all"
        assert pa.render_skills("CODE") == "for all\n\nfor code"

    def test_empty_when_nothing(self, layers):
        assert pa.render_skills("agent") == ""

    def test_truncation(self, layers, monkeypatch):
        _write_skill(layers["builtin"], "a", "x" * 1000)
        monkeypatch.setenv("SKILL_MAX_CHARS", "300")
        out = pa.render_skills("agent")
        assert out.startswith("x" * 300) and out.endswith("…(skills truncated)")
        assert pa.render_skills("agent", max_chars=50).startswith("x" * 50)

    def test_max_chars_floor_and_invalid(self, monkeypatch):
        monkeypatch.setenv("SKILL_MAX_CHARS", "10")
        assert pa.skill_max_chars() == 200
        monkeypatch.setenv("SKILL_MAX_CHARS", "abc")
        assert pa.skill_max_chars() == pa.DEFAULT_SKILL_MAX_CHARS

    @pytest.mark.parametrize("value", ["off", "0", "false", "NO", " Off "])
    def test_disabled_by_env(self, layers, monkeypatch, value):
        _write_skill(layers["builtin"], "a", "A")
        monkeypatch.setenv("CODE_AGENT_SKILLS", value)
        assert pa.skills_enabled() is False
        assert pa.render_skills("agent") == ""

    def test_explicit_skills_bypass_switch(self, layers, monkeypatch):
        monkeypatch.setenv("CODE_AGENT_SKILLS", "off")
        s = pa.Skill(name="x", body="B", path=Path("x"))
        assert pa.render_skills("agent", skills=[s]) == "B"


class TestDescribe:
    def test_describe_shape(self, layers):
        _write_rules(layers["user"], "R")
        _write_skill(layers["builtin"], "core", "C", "description: d\nroles: [code, test]")
        info = pa.describe()
        assert info["dirs"] == [str(layers["builtin"]), str(layers["user"]), str(layers["extra"])]
        assert info["project_rules"].endswith("user/prompts/system/PROJECT_RULES.md")
        assert info["skills_enabled"] is True and info["skill_max_chars"] == 4000
        (s,) = info["skills"]
        assert s["name"] == "core" and s["roles"] == ["code", "test"] and s["chars"] == 1

    def test_describe_without_rules(self, layers):
        _write_skill(layers["builtin"], "core", "C")
        info = pa.describe()
        assert info["project_rules"] is None and info["skills"][0]["roles"] == "all"
