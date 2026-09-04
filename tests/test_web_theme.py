#!/usr/bin/env python3
"""test_web_theme.py — Web 多主题色模块（不依赖 gradio）。"""
import re

from web import theme


HEX = re.compile(r"^#[0-9a-f]{6}$")


class TestPalettes:
    def test_each_theme_has_eleven_valid_shades_and_label(self):
        for key, spec in theme.THEMES.items():
            assert spec["label"]
            shades = spec["shades"]
            assert len(shades) == 11, key
            assert all(HEX.match(c) for c in shades), key

    def test_default_theme_exists(self):
        assert theme.DEFAULT_THEME in theme.THEMES

    def test_theme_choices_labels_and_keys(self):
        choices = theme.theme_choices()
        assert [k for _, k in choices] == list(theme.THEMES)
        assert all(label for label, _ in choices)

    def test_normalize(self):
        assert theme.normalize_theme("violet") == "violet"
        assert theme.normalize_theme(" Rose ") == "rose"
        assert theme.normalize_theme("nope") == theme.DEFAULT_THEME
        assert theme.normalize_theme("") == theme.DEFAULT_THEME
        assert theme.normalize_theme(None) == theme.DEFAULT_THEME


class TestCss:
    def test_theme_css_covers_every_theme_light_and_dark(self):
        css = theme.build_theme_css()
        for key in theme.THEMES:
            assert f'body[data-cb-theme="{key}"] {{' in css
            assert f'body[data-cb-theme="{key}"].dark' in css

    def test_semantic_vars_overridden(self):
        css = theme.build_theme_css()
        for var in ("--button-primary-background-fill", "--color-accent", "--checkbox-background-color-selected",
                    "--link-text-color", "--cb-accent", "--cb-gradient", "--primary-500", "--secondary-500"):
            assert var in css

    def test_build_css_includes_layout(self):
        css = theme.build_css()
        assert ".cb-nav" in css and ".cb-composer" in css and "@media" in css
        assert "button.stop" in css


class TestScripts:
    def test_scripts_reference_storage_key_and_default(self):
        for script in (theme.HEAD_HTML, theme.THEME_LOAD_JS, theme.THEME_CHANGE_JS):
            assert theme.STORAGE_KEY in script
            assert theme.DEFAULT_THEME in script
            assert "cbTheme" in script

    def test_load_js_returns_list_for_backend(self):
        assert "return [v];" in theme.THEME_LOAD_JS
