"""系统页处理器：模型热切换 / 思考模式 / 网络缓存 / 运行环境 / 工具清单 / 模型表。"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

from ..formatters import (
    _fmt_result,
    format_env_info,
    format_model_chip,
    format_model_status,
    format_switch_result,
)
from ..services import WebService


def build_system_handlers(service: WebService) -> Dict[str, Any]:
    """系统页处理器：模型热切换 / 思考模式 / 网络缓存 / 运行环境 / 工具清单 / 模型表（由 ``app.build_handlers`` 汇总）。"""

    # ---------- 模型管理（热切换）----------

    def on_model_status() -> str:
        info = dict(service.current_model())
        notice = service.models_notice() if hasattr(service, "models_notice") else ""
        if notice:
            info["models_notice"] = notice
        return format_model_status(info)

    def on_model_chip() -> str:
        return format_model_chip(service.current_model())

    def on_model_choices() -> Tuple[List[str], str]:
        """返回 (可选模型列表, 当前模型)，供下拉框初始化/刷新。"""
        choices = service.list_models()
        current = service.current_model().get("model", "")
        if current and current not in choices:
            choices = [current] + choices
        return choices, current

    def on_switch_model(model: str) -> Tuple[str, str]:
        """切换模型；返回 (切换结果, 刷新后的状态行)。"""
        model = (model or "").strip()
        if not model:
            return "❌ 请选择模型", on_model_status()
        result = service.switch_model(model)
        return format_switch_result(result), on_model_status()

    def on_toggle_think(enabled: bool) -> Tuple[str, str, bool]:
        """开关思考模式；返回 (结果, 刷新后的状态行, 复选框应显示的实际值)。

        若当前模型不支持 thinking，服务层会拒绝开启，此时把复选框回弹为实际状态。
        """
        result = service.set_think(bool(enabled))
        return format_switch_result(result), on_model_status(), bool(result.get("enabled"))

    def on_web_cache_status() -> str:
        return _fmt_result(service.web_cache_status())

    def on_web_cache_clear() -> str:
        return _fmt_result(service.web_cache_clear())

    # ---------- 系统：环境 / 工具清单 / 模型表 ----------

    def on_env_info() -> str:
        return format_env_info(service.env_info())

    _TOOL_HEADERS = ["工具", "安全等级", "描述", "参数"]

    def on_tools_table() -> List[List[Any]]:
        return [
            [t.get("name", ""), "安全（只读）" if t.get("safe", True) else "需确认（会修改系统）",
             t.get("description", ""), ", ".join((t.get("parameters") or {}).keys())]
            for t in service.list_tools()
        ]

    _MODEL_HEADERS = ["模型", "当前", "已加载"]

    def on_model_table() -> List[List[Any]]:
        return [
            [m.get("name", ""), "✔" if m.get("current") else "", "✔" if m.get("loaded") else ""]
            for m in service.model_table()
        ]

    return {
        "on_model_status": on_model_status,
        "on_model_chip": on_model_chip,
        "on_model_choices": on_model_choices,
        "on_switch_model": on_switch_model,
        "on_toggle_think": on_toggle_think,
        "on_web_cache_status": on_web_cache_status,
        "on_web_cache_clear": on_web_cache_clear,
        "on_env_info": on_env_info,
        "on_tools_table": on_tools_table,
        "on_model_table": on_model_table,
        "headers": {
            "tools": _TOOL_HEADERS,
            "models": _MODEL_HEADERS,
        },
    }
