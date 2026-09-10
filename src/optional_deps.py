"""可选模块探测：区分"确实没装"与"装了但导入出错"（F10 P3-2 待办 #1）。

历史写法 ``try: import x … except ImportError: X_AVAILABLE = False`` 会把目标模块**内部**抛出的任何
ImportError（拼错名字、漏装其某个第三方依赖）一并吞成"未安装"，用户只看到"模块未安装"的提示，
明明装了却无从排查。这里只把 ``ModuleNotFoundError`` 且缺失的正是目标模块（或其子模块）判为
"未安装"；其他导入异常记 WARNING（CLI 默认在终端可见）并同样返回不可用，避免启动崩溃。
"""
from __future__ import annotations

import importlib
import logging

logger = logging.getLogger(__name__)


def _is_missing_target(exc: ModuleNotFoundError, module: str) -> bool:
    """``exc`` 缺失的是否就是 ``module`` 本身或它的子模块（而非它依赖的第三方包）。"""
    name = getattr(exc, "name", None) or ""
    return name == module or name.startswith(module + ".")


def probe_modules(*modules: str, feature: str = "") -> bool:
    """依次导入 ``modules``，全部成功返回 True。

    - 目标模块本身不存在 → ``False``，只记 DEBUG（属正常的"可选功能未安装"）。
    - 导入过程中出现其他异常（目标模块依赖的包缺失、模块内部报错）→ ``False``，
      记 WARNING 带原始异常，提示这不是"未安装"而是"损坏"。

    Args:
        modules: 顶层模块名（如 ``"command_recommender"``）。
        feature: 功能名，只用于日志文案。
    """
    label = feature or ", ".join(modules)
    for module in modules:
        try:
            importlib.import_module(module)
        except ModuleNotFoundError as e:
            if _is_missing_target(e, module):
                logger.debug("可选模块 %s 未安装（%s 不可用）", module, label)
            else:
                logger.warning(
                    "可选功能「%s」不可用：模块 %s 已存在但导入时缺少依赖 %r（%s）",
                    label, module, e.name, e,
                )
            return False
        except Exception as e:  # noqa: BLE001 - 模块内部任何错误都不应让入口崩溃，但必须可见
            logger.warning("可选功能「%s」不可用：导入 %s 失败（非缺失）: %r", label, module, e)
            return False
    return True
