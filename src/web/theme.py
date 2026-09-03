"""Web 界面主题：多套主题色 + 运行时切换 + 全局样式。

设计要点
--------
- Gradio 的主题变量声明在 ``:root``（``--primary-500`` 等），而语义变量
  （``--button-primary-background-fill`` 等）在同一层级用 ``var(--primary-*)``
  引用；CSS 自定义属性在**声明处**求值，因此运行时只改 ``--primary-*`` 不会让
  语义变量跟着变。这里为每套主题同时覆写色阶与所有依赖主色的语义变量，挂在
  ``body[data-cb-theme=…]`` 上，切换主题即整页换色（含深色模式）。
- 主题选择持久化到 ``localStorage``，页面加载时由 ``<head>`` 内脚本尽早应用，
  避免闪烁；下拉框通过 ``app.load`` 的 JS 回读保持同步。
- 本模块不 import gradio（``make_gradio_theme`` 内部惰性导入），可独立测试。
"""
from __future__ import annotations

from typing import Dict, List, Tuple

# ==================== 主题色板（Tailwind 色阶）====================

_SHADES = ("50", "100", "200", "300", "400", "500", "600", "700", "800", "900", "950")

THEMES: Dict[str, Dict[str, object]] = {
    "blue": {
        "label": "活力蓝",
        "shades": ["#eff6ff", "#dbeafe", "#bfdbfe", "#93c5fd", "#60a5fa", "#3b82f6",
                   "#2563eb", "#1d4ed8", "#1e40af", "#1e3a8a", "#172554"],
    },
    "violet": {
        "label": "星空紫",
        "shades": ["#f5f3ff", "#ede9fe", "#ddd6fe", "#c4b5fd", "#a78bfa", "#8b5cf6",
                   "#7c3aed", "#6d28d9", "#5b21b6", "#4c1d95", "#2e1065"],
    },
    "teal": {
        "label": "湖水青",
        "shades": ["#f0fdfa", "#ccfbf1", "#99f6e4", "#5eead4", "#2dd4bf", "#14b8a6",
                   "#0d9488", "#0f766e", "#115e59", "#134e4a", "#042f2e"],
    },
    "emerald": {
        "label": "森林绿",
        "shades": ["#ecfdf5", "#d1fae5", "#a7f3d0", "#6ee7b7", "#34d399", "#10b981",
                   "#059669", "#047857", "#065f46", "#064e3b", "#022c22"],
    },
    "orange": {
        "label": "日落橙",
        "shades": ["#fff7ed", "#ffedd5", "#fed7aa", "#fdba74", "#fb923c", "#f97316",
                   "#ea580c", "#c2410c", "#9a3412", "#7c2d12", "#431407"],
    },
    "rose": {
        "label": "蔷薇红",
        "shades": ["#fff1f2", "#ffe4e6", "#fecdd3", "#fda4af", "#fb7185", "#f43f5e",
                   "#e11d48", "#be123c", "#9f1239", "#881337", "#4c0519"],
    },
}

DEFAULT_THEME = "blue"
STORAGE_KEY = "cerebro.theme"


def theme_choices() -> List[Tuple[str, str]]:
    """下拉选项 ``[(标签, 主题键), ...]``。"""
    return [(str(v["label"]), k) for k, v in THEMES.items()]


def normalize_theme(name: str) -> str:
    """把任意输入归一为合法主题键（非法值回落默认）。"""
    name = (name or "").strip().lower()
    return name if name in THEMES else DEFAULT_THEME


# ==================== 主题 CSS 生成 ====================

def _shade_vars(prefix: str, shades: List[str]) -> str:
    return " ".join(f"--{prefix}-{s}: {c};" for s, c in zip(_SHADES, shades))


def _light_semantic(p: Dict[str, str]) -> str:
    return (
        f"--color-accent: {p['500']}; --color-accent-soft: {p['50']};"
        f" --border-color-accent: {p['300']}; --border-color-accent-subdued: {p['200']};"
        f" --link-text-color: {p['600']}; --link-text-color-hover: {p['700']};"
        f" --link-text-color-active: {p['600']}; --link-text-color-visited: {p['500']};"
        f" --block-label-background-fill: {p['100']}; --block-label-text-color: {p['600']};"
        f" --block-title-text-color: {p['600']};"
        f" --checkbox-background-color-selected: {p['600']}; --checkbox-border-color-focus: {p['500']};"
        f" --checkbox-border-color-selected: {p['600']}; --checkbox-label-background-fill-selected: {p['500']};"
        f" --input-border-color-focus: {p['400']}; --slider-color: {p['500']};"
        f" --stat-background-fill: {p['300']}; --loader-color: {p['500']};"
        f" --button-primary-background-fill: {p['600']}; --button-primary-background-fill-hover: {p['500']};"
        f" --button-primary-border-color: {p['600']}; --button-primary-border-color-hover: {p['500']};"
        f" --button-primary-text-color: #ffffff; --table-row-focus: {p['50']};"
        f" --cb-accent: {p['600']}; --cb-accent-hover: {p['500']}; --cb-accent-strong: {p['700']};"
        f" --cb-accent-soft: {p['50']}; --cb-accent-soft-2: {p['100']}; --cb-accent-border: {p['200']};"
        f" --cb-gradient: linear-gradient(135deg, {p['500']} 0%, {p['700']} 100%);"
    )


def _dark_semantic(p: Dict[str, str]) -> str:
    return (
        f"--color-accent: {p['400']}; --color-accent-soft: rgba(255,255,255,0.06);"
        f" --border-color-accent: {p['600']}; --border-color-accent-subdued: {p['800']};"
        f" --link-text-color: {p['400']}; --link-text-color-hover: {p['300']};"
        f" --link-text-color-active: {p['400']}; --link-text-color-visited: {p['500']};"
        f" --block-label-background-fill: {p['700']}; --block-label-text-color: {p['200']};"
        f" --block-title-text-color: {p['300']};"
        f" --checkbox-background-color-selected: {p['600']}; --checkbox-border-color-focus: {p['500']};"
        f" --checkbox-border-color-selected: {p['600']}; --checkbox-label-background-fill-selected: {p['600']};"
        f" --input-border-color-focus: {p['500']}; --slider-color: {p['500']};"
        f" --stat-background-fill: {p['500']}; --loader-color: {p['400']};"
        f" --button-primary-background-fill: {p['600']}; --button-primary-background-fill-hover: {p['500']};"
        f" --button-primary-border-color: {p['600']}; --button-primary-border-color-hover: {p['500']};"
        f" --button-secondary-background-fill-hover: {p['700']}; --table-row-focus: rgba(255,255,255,0.05);"
        f" --cb-accent: {p['400']}; --cb-accent-hover: {p['300']}; --cb-accent-strong: {p['200']};"
        f" --cb-accent-soft: rgba(255,255,255,0.06); --cb-accent-soft-2: rgba(255,255,255,0.10);"
        f" --cb-accent-border: {p['700']};"
        f" --cb-gradient: linear-gradient(135deg, {p['600']} 0%, {p['900']} 100%);"
    )


def build_theme_css() -> str:
    """为每套主题生成 ``body[data-cb-theme=…]`` 的变量覆写（含深色模式）。"""
    blocks = []
    for key, spec in THEMES.items():
        shades = list(spec["shades"])  # type: ignore[arg-type]
        p = dict(zip(_SHADES, shades))
        sel = f'body[data-cb-theme="{key}"]'
        blocks.append(
            f"{sel} {{ {_shade_vars('primary', shades)} {_shade_vars('secondary', shades)} "
            f"{_light_semantic(p)} }}"
        )
        blocks.append(
            f"{sel}.dark, .dark {sel}, html.dark {sel} {{ {_dark_semantic(p)} }}"
        )
    return "\n".join(blocks)


# ==================== 全局布局样式 ====================

BASE_CSS = """
/* ---- 全局 ---- */
:root, body[data-cb-theme] { --cb-radius: 12px; }
.gradio-container { max-width: 100% !important; }
footer { display: none !important; }
.cb-muted { opacity: .72; font-size: .92em; }
.cb-status { min-height: 1.8em; opacity: .9; }

/* ---- 顶栏 ---- */
.cb-header { align-items: center !important; padding: 6px 4px 2px; gap: 12px; }
.cb-brand { display: flex; align-items: baseline; gap: 12px; flex-wrap: wrap; }
.cb-brand h1 { margin: 0; font-size: 1.45rem; font-weight: 800; letter-spacing: .3px;
  color: var(--cb-accent) !important; line-height: 1.2; }
.cb-brand p { margin: 0; opacity: .7; font-size: .85rem; }
.cb-status-chip { display: inline-flex; align-items: center; gap: 8px; padding: 6px 12px;
  border-radius: 999px; background: var(--cb-accent-soft); border: 1px solid var(--cb-accent-border);
  font-size: .85rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 100%; }
.cb-status-chip .dot { width: 8px; height: 8px; border-radius: 50%; background: var(--cb-accent);
  box-shadow: 0 0 0 3px var(--cb-accent-soft-2); flex: none; }
.cb-status-chip .dot.off { background: #9ca3af; box-shadow: none; }
.cb-status-chip code { font-size: .82rem; }
.cb-theme-dd { min-width: 128px !important; }
.cb-theme-dd label > span { display: none; }

/* ---- 侧栏导航 ---- */
.cb-nav .wrap { flex-direction: column !important; gap: 4px !important; }
.cb-nav label { border: none !important; background: transparent !important; box-shadow: none !important;
  padding: 10px 12px !important; border-radius: var(--cb-radius) !important; font-weight: 600;
  cursor: pointer; transition: background .15s; }
.cb-nav label:hover { background: var(--cb-accent-soft) !important; }
.cb-nav label.selected { background: var(--cb-accent-soft-2) !important; color: var(--cb-accent-strong) !important; }
.cb-nav input { display: none !important; }
.cb-side-title { display: flex; align-items: center; justify-content: space-between; margin-top: 10px; }
.cb-side-title h3 { margin: 0; font-size: .82rem; letter-spacing: .06em; opacity: .65; font-weight: 700; }

/* ---- 按钮语义色：危险操作用红色系（Soft 主题默认把 stop 渲染成灰色）---- */
button.stop, .cb-confirm-wrap > button.stop { background: #fee2e2 !important; color: #b91c1c !important;
  border: 1px solid #fecaca !important; }
button.stop:hover { background: #fecaca !important; }
.dark button.stop, body.dark button.stop { background: rgba(239, 68, 68, .18) !important; color: #fca5a5 !important;
  border-color: rgba(239, 68, 68, .35) !important; }
.cb-confirm button.stop { background: #dc2626 !important; color: #fff !important; border-color: #dc2626 !important; }

/* ---- 行内表单：Gradio 会把相邻表单组件包进 .form，这里让其内联排布 ---- */
.cb-inline-actions .form, .cb-composer-toggles .form, .cb-session-actions .form {
  display: flex; gap: 8px; align-items: center; flex: 1 1 auto; background: transparent !important;
  border: none !important; box-shadow: none !important; }
.cb-inline-actions .form > * { flex: 1 1 auto; min-width: 0 !important; }
.cb-inline-actions .form > *:has(input[type=checkbox]),
.cb-inline-actions .form > *:has(input[type=number]) { flex: 0 0 auto !important; width: auto !important; }
.cb-inline-actions .form > *:has(input[type=number]) { max-width: 120px; }
.cb-inline-actions .form > *:has(input[type=number]) label > span { font-size: .75rem; }

/* ---- 侧栏会话列表 ---- */
.cb-session-list .wrap { flex-direction: column !important; gap: 2px !important; max-height: 38vh; overflow-y: auto; }
.cb-session-list label { border: none !important; background: transparent !important; box-shadow: none !important;
  padding: 8px 10px !important; border-radius: 10px !important; font-size: .88rem; cursor: pointer; }
.cb-session-list label > span { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; display: block; }
.cb-session-list label:hover { background: var(--cb-accent-soft) !important; }
.cb-session-list label.selected { background: var(--cb-accent-soft-2) !important; color: var(--cb-accent-strong) !important; }
.cb-session-list input { display: none !important; }
.cb-session-actions { gap: 6px !important; }
.cb-session-actions > * { flex: 1 1 0 !important; min-width: 0 !important; }

/* ---- 分段模式切换 ---- */
.cb-segment .wrap { gap: 0 !important; background: var(--background-fill-secondary); padding: 3px;
  border-radius: 999px; display: inline-flex; border: 1px solid var(--border-color-primary); }
.cb-segment label { border: none !important; background: transparent !important; box-shadow: none !important;
  border-radius: 999px !important; padding: 6px 16px !important; font-weight: 600; cursor: pointer; }
.cb-segment label.selected { background: var(--button-primary-background-fill) !important; color: #fff !important; }
.cb-segment input { display: none !important; }
.cb-toolbar { align-items: center !important; gap: 10px; flex-wrap: wrap; }

/* ---- 对话区 ---- */
#chatbot { overflow: hidden !important; display: flex !important; flex-direction: column; border-radius: var(--cb-radius); }
#chatbot > .wrapper { flex: 1 1 auto; min-height: 0; }
#chatbot .bubble-wrap, #chatbot .panel-wrap { overflow-y: auto; min-height: 0; }
.cb-composer { border-radius: var(--cb-radius) !important; border: 1px solid var(--border-color-primary) !important;
  background: var(--background-fill-primary) !important; padding: 6px 8px 8px !important; margin-top: 8px;
  box-shadow: 0 1px 2px rgba(0,0,0,.04); }
.cb-composer:focus-within { border-color: var(--cb-accent) !important; box-shadow: 0 0 0 3px var(--cb-accent-soft-2); }
.cb-composer .cb-composer { border: none !important; padding: 0 !important; margin: 0 !important; box-shadow: none !important; }
.cb-composer .styler, .cb-composer .form, .cb-composer .block, .cb-composer .wrap {
  border: none !important; box-shadow: none !important; background: transparent !important; }
.cb-composer textarea { font-size: 1rem; border: none !important; box-shadow: none !important; background: transparent !important; }
.cb-composer-bar { align-items: center !important; gap: 8px; padding: 0 4px; flex-wrap: nowrap !important; }
.cb-composer-bar > .row { width: auto !important; }
.cb-composer-toggles { flex: 1 1 auto !important; gap: 14px !important; align-items: center !important; flex-wrap: wrap; }
.cb-composer-toggles > * { flex: 0 0 auto !important; min-width: 0 !important; }
.cb-composer-actions { flex: 0 0 auto !important; gap: 8px !important; justify-content: flex-end; }
.cb-composer-actions > * { flex: 0 0 auto !important; min-width: 0 !important; }
.cb-approval { border: 1px solid #f59e0b; background: rgba(245, 158, 11, .10); border-radius: var(--cb-radius);
  padding: 10px 14px; align-items: center !important; gap: 10px; }
.cb-approval .cb-btn { flex: 0 0 auto !important; }
.cb-hint { align-items: center !important; padding: 6px 12px; border-radius: var(--cb-radius);
  background: var(--cb-accent-soft); border: 1px solid var(--cb-accent-border); gap: 8px; }
.cb-hint .cb-btn { flex: 0 0 auto !important; }
.cb-side-panel { gap: 10px !important; }
.cb-side-panel .accordion { border-radius: var(--cb-radius); }

/* ---- 内容页 ---- */
.cb-page-title h2 { margin: 0 0 2px; font-size: 1.15rem; }
.cb-page-title p { margin: 0 0 6px; opacity: .7; font-size: .88rem; }
.cb-cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 10px; }
.cb-card { padding: 12px 14px; border-radius: var(--cb-radius); background: var(--background-fill-secondary);
  border: 1px solid var(--border-color-primary); }
.cb-card .k { font-size: .75rem; opacity: .65; letter-spacing: .04em; }
.cb-card .v { font-size: 1.25rem; font-weight: 700; color: var(--cb-accent); margin-top: 2px;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.cb-card .v.small { font-size: .95rem; }
.cb-inline-actions { gap: 8px !important; flex-wrap: wrap; align-items: flex-end !important; }
.cb-inline-actions > .cb-btn { flex: 0 0 auto !important; }
.cb-confirm { border: 1px solid #ef4444; background: rgba(239, 68, 68, .08); border-radius: var(--cb-radius);
  padding: 8px 12px; align-items: center !important; gap: 8px; }
.cb-confirm .cb-btn { flex: 0 0 auto !important; }
.cb-result { min-height: 2em; }
.cb-result pre, .cb-code pre { max-height: 420px; overflow: auto; }
.cb-risk-low { color: #059669; font-weight: 700; }
.cb-risk-medium { color: #d97706; font-weight: 700; }
.cb-risk-high, .cb-risk-critical { color: #dc2626; font-weight: 700; }
.cb-empty { text-align: center; padding: 28px 12px; opacity: .8; }
.cb-empty h3 { margin: 0 0 6px; }
.cb-kv table { width: 100%; border-collapse: collapse; }
.cb-kv th, .cb-kv td { border: none !important; border-bottom: 1px solid var(--border-color-primary) !important;
  padding: 6px 10px !important; }
.cb-kv th { text-align: left; opacity: .6; font-size: .8rem; }
.cb-kv td:first-child { white-space: nowrap; opacity: .75; width: 32%; }

/* ---- 表格「⋯」操作列 / 选中行操作条 ---- */
.cb-more { display: inline-block; width: 100%; text-align: center; font-weight: 800; font-size: 1.1rem;
  line-height: 1; color: var(--cb-accent); cursor: pointer; letter-spacing: .05em; }
.cb-more:hover { color: var(--cb-accent-strong); }
.cb-action-bar { border: 1px solid var(--cb-accent-border); background: var(--cb-accent-soft);
  border-radius: var(--cb-radius); padding: 10px 12px; gap: 8px !important; margin-bottom: 8px; }
.cb-action-title { font-size: .95rem; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.cb-action-title code { font-size: .82rem; }
.cb-action-bar .cb-inline-actions { gap: 6px !important; flex-wrap: wrap; }
/* 操作条内展开确认时，确认气泡独占一整行、提示文案在上按钮在下，避免被挤成竖条 */
.cb-action-bar .cb-confirm-wrap:has(> .cb-confirm:not(.hidden)) { flex: 1 1 100% !important; width: 100%; }
.cb-action-bar .cb-confirm { flex-wrap: wrap; }
.cb-action-bar .cb-confirm > .block { flex: 1 1 100% !important; min-width: 0 !important; }
.cb-action-bar .cb-confirm > .cb-btn { flex: 1 1 0 !important; }
.cb-action-bar .cb-confirm code { word-break: break-all; }

/* ---- 知识图谱视图 ---- */
.cb-graph-controls { align-items: flex-end !important; gap: 10px !important; flex-wrap: wrap; }
.cb-graph-controls > .cb-segment, .cb-graph-controls > .cb-hops { flex: 0 0 auto !important; }
.cb-graph-controls .form { display: flex; gap: 10px; align-items: flex-end; flex: 1 1 auto; flex-wrap: nowrap;
  background: transparent !important; border: none !important; box-shadow: none !important; }
.cb-graph-controls .form > * { flex: 1 1 0 !important; min-width: 0 !important; max-width: none !important;
  width: auto !important; }
.cb-graph-controls .form > *:has(input[type=number]):not(:has(input[type=range])) { flex: 0 0 130px !important; }
.cb-graph-controls .form > .cb-segment, .cb-graph-controls .form > .cb-hops { flex: 0 0 auto !important; }
.cb-graph-controls .cb-hops .wrap { flex-wrap: nowrap; }
.cb-graph-controls .form > *:has(input[type=checkbox]) { flex: 0 0 auto !important; }
.cb-graph-controls .cb-btn { flex: 0 0 auto !important; }
.cb-graph-controls label > span { font-size: .75rem; }
.cb-graph-plot { border-radius: var(--cb-radius); border: 1px solid var(--border-color-primary);
  background: var(--background-fill-secondary); min-height: 560px; }
.cb-graph-plot .js-plotly-plot, .cb-graph-plot .plot-container { background: transparent !important; }

/* ---- 响应式 ---- */
@media (max-width: 1100px) {
  .cb-side-panel { min-width: 100% !important; }
}
@media (max-width: 768px) {
  .cb-header { flex-direction: column; align-items: flex-start !important; }
  .cb-segment label { padding: 6px 10px !important; }
}
"""


def build_css() -> str:
    """完整 CSS（全局布局 + 各主题变量）。"""
    return BASE_CSS + "\n" + build_theme_css()


# ==================== 主题切换脚本 ====================

HEAD_HTML = f"""
<script>
(function () {{
  try {{
    var key = {STORAGE_KEY!r}, def = {DEFAULT_THEME!r};
    var apply = function () {{
      var v = null;
      try {{ v = localStorage.getItem(key); }} catch (e) {{}}
      if (document.body) document.body.dataset.cbTheme = v || def;
    }};
    if (document.body) apply(); else document.addEventListener('DOMContentLoaded', apply);
  }} catch (e) {{}}
}})();
</script>
"""

# 页面加载：回读持久化的主题键并应用到 body；返回值作为后端 ``normalize_theme`` 的入参，
# 再由后端把合法主题键写回下拉框（纯前端 js 直写下拉框在 Gradio 6 不生效）。
THEME_LOAD_JS = f"""
(current) => {{
  var key = {STORAGE_KEY!r}, def = {DEFAULT_THEME!r}, v = null;
  try {{ v = localStorage.getItem(key); }} catch (e) {{}}
  v = v || def;
  document.body.dataset.cbTheme = v;
  return [v];
}}
"""

# 下拉框变更：应用并持久化
THEME_CHANGE_JS = f"""
(v) => {{
  var key = {STORAGE_KEY!r}, def = {DEFAULT_THEME!r};
  v = v || def;
  document.body.dataset.cbTheme = v;
  try {{ localStorage.setItem(key, v); }} catch (e) {{}}
  return v;
}}
"""


def make_gradio_theme():  # pragma: no cover - 依赖 gradio
    """基线 Gradio 主题（与默认主题色一致，JS 未生效时也不违和）。"""
    import gradio as gr

    return gr.themes.Soft(
        primary_hue=gr.themes.colors.blue,
        secondary_hue=gr.themes.colors.blue,
        neutral_hue=gr.themes.colors.slate,
        radius_size=gr.themes.sizes.radius_lg,
        # 本地优先：只用系统字体，不从 Google Fonts 拉取
        font=("ui-sans-serif", "system-ui", "-apple-system", "Segoe UI",
              "PingFang SC", "Microsoft YaHei", "sans-serif"),
        font_mono=("ui-monospace", "SFMono-Regular", "Menlo", "Consolas", "monospace"),
    )
