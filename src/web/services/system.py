"""系统页：模型热切换 / 思考模式 / 运行环境信息。"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


def _code_chunking_env_text() -> str:
    """系统页「代码分块」一行：``启用 · max 1500 字 · tree-sitter-language-pack 1.16.2`` 或未启用原因。"""
    try:
        from code_chunker import availability_message, dependency_version, is_enabled
        import config as _cfg
    except ImportError:  # pragma: no cover
        return ""
    if is_enabled():
        return (
            f"启用 · max {getattr(_cfg, 'CODE_CHUNK_MAX_CHARS', '')} 字 · "
            f"tree-sitter-language-pack {dependency_version()}"
        )
    return f"未启用：{availability_message()}"


class SystemMixin:
    """模型管理与运行环境（对齐 CLI ``/model`` ``/config``）。"""

    # ---------- 模型管理（热切换）----------

    def list_models(self) -> List[str]:
        """可选模型名列表（失败返回空列表；openai 模式后端未提供列表时为 ``[当前模型]``）。"""
        try:
            return list(self._model_switcher_factory().list_installed_models())
        except BaseException:  # noqa: BLE001
            return []

    def models_notice(self) -> str:
        """模型列表不可用时的提示（空串表示正常）；openai 模式回退 ``[LLM_MODEL]`` 时非空（F10 P1-2-c）。"""
        try:
            switcher = self._model_switcher_factory()
            fn = getattr(switcher, "models_notice", None)
            return str(fn() or "") if callable(fn) else ""
        except BaseException:  # noqa: BLE001
            return ""

    def current_model(self) -> Dict[str, Any]:
        """当前模型概况：``model`` / ``num_ctx`` / ``think`` / ``loaded`` / ``size_bytes``。"""
        try:
            return dict(self._model_switcher_factory().current_model_info())
        except BaseException as exc:  # noqa: BLE001
            return {"model": "?", "num_ctx": 0, "think": False, "loaded": False,
                    "size_bytes": 0, "loaded_models": [], "error": str(exc)}

    def model_table(self) -> List[Dict[str, Any]]:
        """已安装模型清单（含"当前 / 已加载"标记），对齐 CLI ``/model list``。"""
        info = self.current_model()
        loaded = set(info.get("loaded_models") or [])
        current = info.get("model", "")
        names = self.list_models()
        if current and current not in names:
            names = [current] + names
        return [
            {"name": n, "current": n == current, "loaded": n in loaded}
            for n in names
        ]

    def switch_model(self, model: str) -> Dict[str, Any]:
        """热切换全局 LLM。

        同步 RAG 引擎（若已创建；未创建则下次惰性创建时自然读取新 config），
        更新全局 config（Web 端 ReActEngine / 多 Agent 每次对话新建，会自动跟随），
        并立即释放旧模型避免双驻留。返回 ``{ok, model, previous, num_ctx, message}``。
        """
        try:
            switcher = self._model_switcher_factory()
            result = switcher.switch_model(
                model,
                rag_engine=self._rag_engine,  # 仅同步已创建的实例，不触发惰性加载
                react_engine=None,
            )
            return {
                "ok": result.ok,
                "model": result.model,
                "previous": result.previous,
                "num_ctx": result.num_ctx,
                "unloaded_previous": result.unloaded_previous,
                "message": result.message,
            }
        except BaseException as exc:  # noqa: BLE001
            return {"ok": False, "model": "", "previous": "", "num_ctx": 0,
                    "unloaded_previous": False, "message": f"切换失败: {exc}"}

    def set_think(self, enabled: bool) -> Dict[str, Any]:
        """运行时开关思考模式。

        同步已创建的 RAG 引擎（重建 LLM）并更新全局 config（Web 端 ReActEngine
        每次对话新建，会自动跟随）。开启前校验当前模型是否支持 thinking。
        返回 ``{ok, enabled, changed, message}``。
        """
        try:
            result = self._model_switcher_factory().switch_think(
                bool(enabled), rag_engine=self._rag_engine, react_engine=None,
            )
            return {
                "ok": result.ok,
                "enabled": result.enabled,
                "changed": result.changed,
                "message": result.message,
            }
        except BaseException as exc:  # noqa: BLE001
            return {"ok": False, "enabled": False, "changed": False,
                    "message": f"设置失败: {exc}"}

    def env_info(self) -> Dict[str, Any]:
        """运行环境概览（对齐 CLI 启动横幅与 ``/model`` 的附加字段）。"""
        info: Dict[str, Any] = {}
        try:
            import config
            info.update({
                "ollama_url": getattr(config, "OLLAMA_BASE_URL", ""),
                "llm_provider": getattr(config, "LLM_PROVIDER", "ollama"),
                "llm_base_url": getattr(config, "LLM_BASE_URL", ""),
                "llm_api_key_set": bool(getattr(config, "LLM_API_KEY", "")),
                "llm_model": getattr(config, "LLM_MODEL", ""),
                "embed_model": getattr(config, "EMBED_MODEL", ""),
                "num_ctx": getattr(config, "LLM_NUM_CTX", ""),
                "think": bool(getattr(config, "LLM_THINK", False)),
                "auto_confirm_env": bool(getattr(getattr(config, "Config", None), "AUTO_CONFIRM", False)),
                "top_k": getattr(config, "TOP_K", ""),
                "chunk_size": getattr(config, "CHUNK_SIZE", ""),
                "chunk_overlap": getattr(config, "CHUNK_OVERLAP", ""),
                "code_chunking": _code_chunking_env_text(),
                "similarity_cutoff": getattr(config, "SIMILARITY_CUTOFF", ""),
                "kb_relevance_threshold": getattr(config, "KB_RELEVANCE_THRESHOLD", ""),
                "self_check": bool(getattr(config, "RAG_SELF_CHECK", False)),
                "data_dir": str(getattr(config, "DATA_DIR", "")),
                "index_dir": str(getattr(config, "INDEX_DIR", "")),
                "vector_db_path": str(getattr(config, "VECTOR_DB_PATH", "")),
                "session_storage": str(getattr(config, "SESSION_STORAGE_PATH", "")),
                "max_iterations": getattr(config, "MAX_ITERATIONS", ""),
                "timeout": getattr(config, "TIMEOUT", ""),
            })
        except BaseException as exc:  # noqa: BLE001
            info["error"] = str(exc)
        try:
            import os
            info["cwd"] = os.getcwd()
            info["app_version"] = os.environ.get("APP_VERSION", "") or "dev"
        except BaseException:  # noqa: BLE001
            pass
        # 路径边界（F10 P0-1-d）：读 / 写允许目录对用户可见，越界报错时才不至于困惑
        try:
            from agent_tools import read_allowed_dirs, write_allowed_dirs
            info["write_allowed_dirs"] = list(write_allowed_dirs())
            info["read_allowed_dirs"] = list(read_allowed_dirs())
        except BaseException:  # noqa: BLE001
            info["write_allowed_dirs"] = []
            info["read_allowed_dirs"] = []
        # LLM 后端（F10 P1-2-c）：provider 归一化（未识别值已回退）+ 健康探测（经 LLMClient.health）
        try:
            from llm_client import describe_backend
            backend = describe_backend(check_health=True)
            info["llm_provider"] = backend.get("provider", info.get("llm_provider", "ollama"))
            info["llm_base_url"] = backend.get("base_url", info.get("llm_base_url", ""))
            info["llm_api_key_set"] = bool(backend.get("api_key_set", info.get("llm_api_key_set", False)))
            info["backend_healthy"] = backend.get("healthy")
            # F10 P2-1-d：进程内 LLM 请求并发上限（OLLAMA_MAX_CONCURRENCY，0 = 不限制）
            info["max_concurrency"] = backend.get("max_concurrency")
        except BaseException:  # noqa: BLE001
            info["backend_healthy"] = None
        return info
