"""Web 服务层：核心引擎的编排与流式桥接（包入口）。

``WebService`` 由 ``base.WebServiceBase`` 与六个功能 mixin 组合而成（F10 P2-2 拆包），
对外公开名与拆包前的单文件 ``web/services.py`` 完全一致：
``from web.services import WebService, StreamEvent, get_web_service, ...`` 路径不变。

各模块职责：

- ``base``：引擎工厂 ``_default_*``、``ScratchContext``、``StreamEvent``、``WebServiceBase``
  （状态 / 取消 / 交互式确认 / ``_bridge`` 心跳桥接 / 惰性单例）
- ``chat``：会话上下文、RAG / 单 Agent / 自动路由 / 多 Agent 流式对话、会话管理
- ``knowledge``：入库 / 统计 / 文件管理 / 摘要与技能 / 快照
- ``tools``：registry 工具命令、代码助手 / 符号 / 质量、Git、AI 解读、Shell / 文件 / 工作区
- ``db``：SQLite 连接 / 查询 / 写操作 / 自然语言 → SQL
- ``graph``：知识图谱查询 / 构建 / 可视化数据
- ``system``：模型热切换 / 思考模式 / 运行环境信息
"""
from __future__ import annotations

from typing import Optional

from .base import (  # noqa: F401 - 重导出：保持拆包前的公开名
    ScratchContext,
    StreamEvent,
    WebServiceBase,
    _DONE,
    _default_collaboration_mode,
    _default_complete_text,
    _default_graph_query_factory,
    _default_load_documents,
    _default_model_switcher,
    _default_orchestrator_factory,
    _default_rag_factory,
    _default_react_factory,
    _default_session_manager_factory,
    _default_set_rag_engine,
    logger,
)
from .chat import ChatMixin
from .db import DatabaseMixin
from .graph import GraphMixin
from .knowledge import KnowledgeMixin, _describe_chunking  # noqa: F401
from .system import SystemMixin, _code_chunking_env_text  # noqa: F401
from .tools import ToolsMixin


class WebService(
    ChatMixin, KnowledgeMixin, ToolsMixin, DatabaseMixin, GraphMixin, SystemMixin, WebServiceBase,
):
    """Web 界面服务层。

    通过依赖注入接收各引擎的工厂函数，便于在不启动真实 Ollama/ChromaDB 的情况下
    进行单元测试。方法按功能面分布在各 mixin 中（见模块文档）。
    """


# ==================== 模块级单例 ====================

_web_service_singleton: Optional[WebService] = None


def get_web_service(**kwargs) -> WebService:
    """获取进程内共享的 WebService 单例。

    仅在首次创建时使用传入的工厂参数；后续调用忽略参数返回既有实例。
    """
    global _web_service_singleton
    if _web_service_singleton is None:
        _web_service_singleton = WebService(**kwargs)
    return _web_service_singleton


def reset_web_service() -> None:
    """重置单例（主要供测试使用）。"""
    global _web_service_singleton
    _web_service_singleton = None
