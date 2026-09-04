"""Cerebro Web 界面（Gradio）。

本包提供一个基于 Gradio 的本地 Web 界面，作为 CLI / 桌面托盘之外的第三种交互
入口。设计遵循分层原则：

- ``services``：服务层，持有核心引擎单例、把引擎回调转成可迭代的流式事件、编排
  业务逻辑。这是唯一与核心引擎交互的层，也是单元测试的重点。
- ``app``：薄 UI 层，仅负责 Gradio 组件布局与事件绑定。

详见 ``docs/features/f7-web-ui/DESIGN.md``。
"""

from .services import WebService, get_web_service

__all__ = ["WebService", "get_web_service"]
