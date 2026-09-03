"""运行时 LLM 模型热切换（CLI ``/model <name>`` 与 Web 模型下拉共用）。

设计要点：

1. **校验**：目标模型必须已在本机 Ollama 安装（``/api/tags``），避免切到一个
   不存在的名字后所有请求静默失败。支持省略 tag 的宽松匹配（``qwen3.5`` →
   ``qwen3.5:latest`` 或唯一的 ``qwen3.5:*``）。
2. **同步所有引用点**：``config.set_llm_model``（模块级常量 + ``Config`` 类）、
   ``RAGEngine.set_model``（重建 ``Settings.llm`` 与 query_engine）、
   ``ReActEngine.set_model``（模型名 + num_ctx）。多 Agent 配置、提交信息生成、
   知识快照等在调用时读取 ``config.LLM_MODEL``，会自动跟随。
3. **卸载旧模型**：Ollama 调度器只在"新模型放不下"时才驱逐旧模型。macOS 上
   4B(3.7GB)+9B(5.7GB) 会被判定为"放得下"而**双驻留**，与 IDE 并行时直接换页
   卡顿。因此切换后主动对旧模型发 ``keep_alive: 0`` 立即释放。

本模块不 import gradio / rich，可被 CLI、Web 与测试直接复用。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class SwitchResult:
    ok: bool
    model: str = ""
    previous: str = ""
    num_ctx: int = 0
    unloaded_previous: bool = False
    message: str = ""
    candidates: List[str] = field(default_factory=list)


# --------------------------------------------------------------------------
# Ollama 查询/控制（薄封装，便于测试打桩）
# --------------------------------------------------------------------------

def _base_url() -> str:
    from config import OLLAMA_BASE_URL

    return OLLAMA_BASE_URL.rstrip("/")


def list_installed_models(timeout: float = 3.0) -> List[str]:
    """已安装模型名列表（复用 bootstrap 实现；失败返回空列表）。"""
    try:
        from bootstrap import list_installed_models as _impl

        return _impl(timeout=timeout)
    except Exception:  # noqa: BLE001
        return []


def list_loaded_models(timeout: float = 3.0) -> List[Dict[str, Any]]:
    """当前已加载到内存的模型（``/api/ps``），每项含 name/size/size_vram/context。

    失败返回空列表。``size`` 单位字节。
    """
    try:
        import requests

        resp = requests.get(f"{_base_url()}/api/ps", timeout=timeout)
        if resp.status_code != 200:
            return []
        models = resp.json().get("models", []) or []
        out = []
        for m in models:
            out.append(
                {
                    "name": m.get("name") or m.get("model") or "",
                    "size": int(m.get("size") or 0),
                    "size_vram": int(m.get("size_vram") or 0),
                    "context": int(m.get("context_length") or 0),
                }
            )
        return out
    except Exception:  # noqa: BLE001
        return []


def unload_model(model: str, timeout: float = 10.0) -> bool:
    """立即卸载指定模型（``keep_alive: 0``）。返回是否成功发出请求。"""
    model = (model or "").strip()
    if not model:
        return False
    try:
        import requests

        resp = requests.post(
            f"{_base_url()}/api/generate",
            json={"model": model, "keep_alive": 0},
            timeout=timeout,
        )
        return resp.status_code == 200
    except Exception:  # noqa: BLE001
        return False


# --------------------------------------------------------------------------
# 名称解析
# --------------------------------------------------------------------------

def resolve_model_name(requested: str, installed: List[str]) -> Optional[str]:
    """把用户输入解析为已安装的精确模型名。

    - 精确匹配（大小写不敏感）优先；
    - 未带 tag 时，优先 ``name:latest``，否则若只有一个 ``name:*`` 则取它；
    - 无法唯一确定返回 None。
    """
    req = (requested or "").strip()
    if not req or not installed:
        return None
    lower_map = {m.lower(): m for m in installed}
    if req.lower() in lower_map:
        return lower_map[req.lower()]
    if ":" not in req:
        latest = f"{req.lower()}:latest"
        if latest in lower_map:
            return lower_map[latest]
        prefix = req.lower() + ":"
        hits = [m for m in installed if m.lower().startswith(prefix)]
        if len(hits) == 1:
            return hits[0]
    return None


def suggest_models(requested: str, installed: List[str], limit: int = 5) -> List[str]:
    """给出与输入相近的已安装模型，用于报错提示。"""
    req = (requested or "").strip().lower()
    if not req:
        return installed[:limit]
    base = req.split(":")[0]
    hits = [m for m in installed if base in m.lower() or m.lower().split(":")[0] in req]
    return (hits or installed)[:limit]


# --------------------------------------------------------------------------
# 切换
# --------------------------------------------------------------------------

def switch_model(
    requested: str,
    rag_engine: Any = None,
    react_engine: Any = None,
    unload_previous: bool = True,
    require_installed: bool = True,
) -> SwitchResult:
    """切换全局 LLM 并同步各引擎；返回结构化结果供 CLI/Web 渲染。

    ``rag_engine`` / ``react_engine`` 可为 None（例如 Web 端 ReActEngine 是每次
    对话新建的，只需更新 config 即可）。
    """
    import config

    previous = config.LLM_MODEL
    req = (requested or "").strip()
    if not req:
        return SwitchResult(False, previous=previous, message="请指定模型名，例如 /model qwen3.5:9b")

    installed = list_installed_models() if require_installed else []
    if require_installed:
        if not installed:
            return SwitchResult(
                False,
                previous=previous,
                message="无法获取本机 Ollama 模型列表，请确认服务已启动: ollama serve",
            )
        target = resolve_model_name(req, installed)
        if target is None:
            cands = suggest_models(req, installed)
            prefix = req.lower().split(":")[0] + ":"
            same_family = [m for m in installed if m.lower().startswith(prefix)]
            if ":" not in req and len(same_family) > 1:
                # 省略 tag 且本机有多个同名不同规格的模型：要求用户指明
                return SwitchResult(
                    False,
                    previous=previous,
                    message=f"'{req}' 有多个已安装规格，请指明 tag: " + ", ".join(same_family),
                    candidates=same_family,
                )
            hint = ("，可选: " + ", ".join(cands)) if cands else ""
            return SwitchResult(
                False,
                previous=previous,
                message=f"模型 '{req}' 未安装{hint}。可用 `ollama pull {req}` 下载",
                candidates=cands,
            )
    else:
        target = req

    if target == previous:
        return SwitchResult(
            True,
            model=target,
            previous=previous,
            num_ctx=config.LLM_NUM_CTX,
            message=f"当前已是 {target}，无需切换",
        )

    # 1) 全局 config（多 Agent / 提交信息 / 快照等调用时读取）
    num_ctx = config.set_llm_model(target)

    # 2) 已 import 绑定常量的引擎
    errors: List[str] = []
    if rag_engine is not None and hasattr(rag_engine, "set_model"):
        try:
            rag_engine.set_model(target)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"RAG 引擎切换失败: {exc}")
    if react_engine is not None and hasattr(react_engine, "set_model"):
        try:
            react_engine.set_model(target)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"Agent 引擎切换失败: {exc}")

    # 3) 立即释放旧模型，避免新旧双驻留
    unloaded = False
    if unload_previous and previous and previous != target:
        unloaded = unload_model(previous)

    msg = f"已切换到 {target}（num_ctx={num_ctx}）"
    if unloaded:
        msg += f"，已释放 {previous}"
    if errors:
        msg += "；" + "；".join(errors)
    return SwitchResult(
        ok=not errors,
        model=target,
        previous=previous,
        num_ctx=num_ctx,
        unloaded_previous=unloaded,
        message=msg,
    )


def current_model_info() -> Dict[str, Any]:
    """当前模型概况：名称、num_ctx、思考模式、是否已加载及驻留大小。"""
    import config

    loaded = {m["name"]: m for m in list_loaded_models()}
    name = config.LLM_MODEL
    entry = loaded.get(name)
    return {
        "model": name,
        "num_ctx": config.LLM_NUM_CTX,
        "think": bool(getattr(config, "LLM_THINK", False)),
        "loaded": entry is not None,
        "size_bytes": entry["size"] if entry else 0,
        "loaded_models": list(loaded.keys()),
    }


def format_size(num_bytes: int) -> str:
    if not num_bytes:
        return "-"
    gb = num_bytes / (1024 ** 3)
    return f"{gb:.1f} GB" if gb >= 1 else f"{num_bytes / (1024 ** 2):.0f} MB"
