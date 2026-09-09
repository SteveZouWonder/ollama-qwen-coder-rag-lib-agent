"""Web UI 处理器工厂（按页面拆分，F10 P2-2）。

每个 ``build_*_handlers(service)`` 返回一组绑定到 ``WebService`` 的处理器（键名 → 可调用），
处理器返回值均为已格式化的字符串 / 表格数据，不依赖 gradio，可独立单元测试；
``web.app.build_handlers`` 把五组合并为一个 dict（含 ``headers`` 表头表）供 ``web.ui`` 布局接线。
"""
from .chat import build_chat_handlers
from .graph import build_graph_handlers
from .knowledge import build_knowledge_handlers
from .system import build_system_handlers
from .tools import build_tools_handlers

__all__ = [
    "build_chat_handlers",
    "build_graph_handlers",
    "build_knowledge_handlers",
    "build_system_handlers",
    "build_tools_handlers",
]
