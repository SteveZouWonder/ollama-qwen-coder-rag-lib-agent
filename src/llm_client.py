"""LLM 后端抽象层：Ollama 原生协议 / OpenAI 兼容协议（F10 P1-2）。

项目内所有"直接向对话模型发请求"的地方（ReAct 引擎、协作层 ``complete_text``、会话摘要、
提交信息生成、托盘预热）统一经 :func:`get_llm_client` 取得一个 :class:`LLMClient`，
由它决定走 Ollama ``/api/chat`` 还是 OpenAI 兼容 ``/v1/chat/completions``：

- :class:`OllamaClient`：请求体 ``{model, messages, stream, think, options}`` 与 P1-1 之前的
  直连调用**逐字节一致**（``options`` 原样透传，非流式不带 ``stream=`` 关键字），流式为 NDJSON。
- :class:`OpenAICompatClient`：``Authorization: Bearer``；``options`` 映射
  ``temperature→temperature``、``num_predict→max_tokens``，``num_ctx`` 由后端决定（忽略并 debug 日志一次）；
  ``think=False`` 映射为标准字段 ``reasoning_effort=LLM_REASONING_EFFORT``（默认 ``none``；后端返回 400 时自动去掉重试并记住），
  ``think=True`` 不发送任何字段；流式为 SSE ``data:`` 行。

两种 client 的 ``chat`` 都支持 ``on_token``（增量回调，受 ``Config.LLM_STREAM`` 控制）、
``should_stop``（取消检查）与 ``on_response``（拿到底层 ``requests.Response`` 以便另一线程
``abort_response``）。错误约定：网络类异常（``requests.exceptions.ConnectionError`` / ``Timeout``）
原样抛出，HTTP 4xx/5xx、流中 ``error``、响应非法 JSON 抛 :class:`LLMError`。

配置来自 ``config.LLM_PROVIDER`` / ``LLM_BASE_URL`` / ``LLM_API_KEY``；工厂按这三项缓存单例，
``config.set_llm_model`` 只改模型名，不影响 client（模型名在每次调用时读取 / 由调用方传入）。
"""
from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Protocol, Tuple

import requests

logger = logging.getLogger(__name__)

TokenCallback = Callable[[str], None]
StopCheck = Callable[[], bool]
ResponseHook = Callable[[Any], None]

OLLAMA_PROVIDER = "ollama"
OPENAI_PROVIDER = "openai"
PROVIDERS = (OLLAMA_PROVIDER, OPENAI_PROVIDER)

MODELS_UNAVAILABLE_NOTICE = "后端未提供模型列表，已回退当前模型"


class LLMError(RuntimeError):
    """LLM 后端返回的错误（HTTP 4xx/5xx、流中 ``error``、响应非法 JSON）。

    ``status_code`` 为 HTTP 状态码（非 HTTP 错误时为 None）。
    """

    def __init__(self, message: str, *, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code


class LLMClient(Protocol):
    """对话后端的最小协议（§2 P1-2-a）。

    ``chat`` 除需求签名的四个关键字外，另接受可选的 ``should_stop`` / ``on_response`` / ``timeout``。
    """

    provider: str
    base_url: str

    def chat(self, messages: List[Dict[str, str]], *, model: Optional[str] = None,
             options: Optional[Dict[str, Any]] = None, think: bool = False,
             on_token: Optional[TokenCallback] = None,
             should_stop: Optional[StopCheck] = None,
             on_response: Optional[ResponseHook] = None,
             timeout: Optional[float] = None) -> str:
        ...

    def list_models(self) -> List[str]:
        ...

    def health(self) -> bool:
        ...


# ---------------------------------------------------------------------------
# 共用工具
# ---------------------------------------------------------------------------

def _stream_enabled() -> bool:
    try:
        from config import Config
        return bool(getattr(Config, "LLM_STREAM", True))
    except Exception:  # noqa: BLE001
        return True


def _default_timeout() -> float:
    try:
        from config import Config
        return float(Config.TIMEOUT)
    except Exception:  # noqa: BLE001
        return 300.0


def reasoning_effort_setting() -> str:
    """``config.LLM_REASONING_EFFORT``（openai 模式 think=False 时发送的 ``reasoning_effort``；空串表示不发送）。"""
    try:
        import config as _cfg
        return str(getattr(_cfg, "LLM_REASONING_EFFORT", "none") or "").strip().lower()
    except Exception:  # noqa: BLE001
        return "none"


def _current_model() -> str:
    try:
        import config as _cfg
        return str(getattr(_cfg, "LLM_MODEL", "") or "")
    except Exception:  # noqa: BLE001
        return ""


def abort_response(resp) -> None:
    """从另一线程中止一个正在流式读取的 ``requests.Response``（F10 P1-1）。

    仅 ``close()`` 在 macOS / Linux 上不会唤醒阻塞在 ``recv`` 的读线程（要等下一段数据到达
    才报错）；先对底层 socket ``shutdown(SHUT_RDWR)`` 可让读线程立刻退出，服务端也随即
    感知连接断开而停止生成。所有步骤尽力而为，失败静默。
    """
    if resp is None:
        return
    try:
        import socket as _socket

        sock = resp.raw._fp.fp.raw._sock  # urllib3 HTTPResponse → http.client → socket
        sock.shutdown(_socket.SHUT_RDWR)
    except Exception:  # noqa: BLE001 - 结构随库版本变化，拿不到就只做 close
        pass
    try:
        resp.close()
    except Exception:  # noqa: BLE001
        pass


def _error_detail(resp) -> str:
    """从错误响应里尽力提取可读原因（Ollama ``{"error": str}`` / OpenAI ``{"error": {"message"}}``）。"""
    data = None
    try:
        data = resp.json()
    except Exception:  # noqa: BLE001
        data = None
    if isinstance(data, dict):
        err = data.get("error")
        if isinstance(err, dict):
            return str(err.get("message") or err)
        if err:
            return str(err)
    try:
        text = resp.text
    except Exception:  # noqa: BLE001
        text = ""
    return text[:200].strip() if isinstance(text, str) else ""


def _check_status(resp, *, provider: str) -> None:
    """HTTP 状态 ≥400 抛 :class:`LLMError`（Mock 响应无整型 status_code 时跳过）。"""
    status = getattr(resp, "status_code", None)
    if not isinstance(status, int) or status < 400:
        return
    detail = _error_detail(resp)
    if status == 401:
        hint = "认证失败（HTTP 401），请检查 LLM_API_KEY" if provider == OPENAI_PROVIDER else "认证失败（HTTP 401）"
    elif status == 404:
        hint = "接口不存在（HTTP 404），请确认 LLM_BASE_URL 与模型名"
    elif status >= 500:
        hint = f"后端错误（HTTP {status}）"
    else:
        hint = f"请求被拒绝（HTTP {status}）"
    raise LLMError(f"{hint}{': ' + detail if detail else ''}", status_code=status)


def _parse_json(resp) -> Dict[str, Any]:
    try:
        data = resp.json()
    except (ValueError, TypeError) as exc:
        raise LLMError(f"响应不是合法 JSON: {exc}") from exc
    return data if isinstance(data, dict) else {}


def consume_ndjson_stream(resp, on_token: TokenCallback,
                          should_stop: Optional[StopCheck] = None) -> str:
    """逐行解析 Ollama ``/api/chat`` 的 NDJSON 流并回调增量，返回累积文本（F10 P1-1）。

    ``should_stop()`` 为真时停止读取、不再回调并关闭响应（返回已累积部分）；流中出现
    ``{"error": ...}`` 抛 :class:`LLMError`（``RuntimeError`` 子类）。响应总会被关闭。
    """
    parts: List[str] = []
    try:
        for line in resp.iter_lines():
            if should_stop is not None and should_stop():
                break
            if not line:
                continue
            try:
                data = json.loads(line)
            except (ValueError, TypeError):
                continue
            if not isinstance(data, dict):
                continue
            if data.get("error"):
                raise LLMError(str(data["error"]))
            delta = (data.get("message") or {}).get("content") or ""
            if delta:
                parts.append(delta)
                on_token(delta)
            if data.get("done"):
                break
    except LLMError:
        raise
    except Exception:
        if not (should_stop is not None and should_stop()):
            raise
    finally:
        try:
            resp.close()
        except Exception:  # noqa: BLE001
            pass
    return "".join(parts)


def consume_sse_stream(resp, on_token: TokenCallback,
                       should_stop: Optional[StopCheck] = None) -> str:
    """解析 OpenAI 兼容 ``/v1/chat/completions`` 的 SSE 流（``data:`` 行），返回累积文本。

    - ``data: [DONE]`` 结束；每个 chunk 取 ``choices[0].delta.content``；
    - 非 ``data:`` 行 / 非 JSON 行忽略；``{"error": ...}``（带或不带 ``data:`` 前缀）抛 :class:`LLMError`；
    - ``should_stop()`` 为真即停止回调并关闭响应。响应总会被关闭。
    """
    parts: List[str] = []
    try:
        for raw in resp.iter_lines():
            if should_stop is not None and should_stop():
                break
            if not raw:
                continue
            line = raw.decode("utf-8", "replace") if isinstance(raw, (bytes, bytearray)) else str(raw)
            line = line.strip()
            if line.startswith("data:"):
                payload = line[5:].strip()
            elif line.startswith("{"):
                payload = line  # 部分后端把错误对象直接写成一行 JSON
            else:
                continue  # event:/id:/注释行
            if payload == "[DONE]":
                break
            try:
                data = json.loads(payload)
            except (ValueError, TypeError):
                continue
            if not isinstance(data, dict):
                continue
            err = data.get("error")
            if err:
                raise LLMError(str(err.get("message") or err) if isinstance(err, dict) else str(err))
            choices = data.get("choices") or []
            if not choices or not isinstance(choices[0], dict):
                continue
            delta = (choices[0].get("delta") or {}).get("content") or ""
            if delta:
                parts.append(delta)
                on_token(delta)
    except LLMError:
        raise
    except Exception:
        if not (should_stop is not None and should_stop()):
            raise
    finally:
        try:
            resp.close()
        except Exception:  # noqa: BLE001
            pass
    return "".join(parts)


# ---------------------------------------------------------------------------
# Ollama
# ---------------------------------------------------------------------------

class OllamaClient:
    """Ollama 原生协议：``/api/chat``（对话）、``/api/tags``（模型列表 / 健康）、``/api/generate``（卸载）。"""

    provider = OLLAMA_PROVIDER

    def __init__(self, base_url: str, timeout: Optional[float] = None):
        self.base_url = (base_url or "").rstrip("/")
        self._timeout = timeout

    def _url(self, path: str) -> str:
        return self.base_url + path

    def chat(self, messages: List[Dict[str, str]], *, model: Optional[str] = None,
             options: Optional[Dict[str, Any]] = None, think: bool = False,
             on_token: Optional[TokenCallback] = None,
             should_stop: Optional[StopCheck] = None,
             on_response: Optional[ResponseHook] = None,
             timeout: Optional[float] = None) -> str:
        streaming = on_token is not None and _stream_enabled()
        payload: Dict[str, Any] = {
            "model": model or _current_model(),
            "messages": list(messages),
            "stream": streaming,
            # 对支持思考模式的模型（qwen3.5 等）显式传 think；不支持的模型 Ollama 会忽略该字段
            "think": bool(think),
            "options": dict(options or {}),
        }
        t = timeout if timeout is not None else (self._timeout if self._timeout is not None else _default_timeout())
        url = self._url("/api/chat")
        if streaming:
            resp = requests.post(url, json=payload, timeout=t, stream=True)
            _check_status(resp, provider=self.provider)
            if on_response is not None:
                on_response(resp)
            return consume_ndjson_stream(resp, on_token, should_stop)
        # 非流式：不带 stream= 关键字，与 P1-2 之前的直连请求形态完全一致
        resp = requests.post(url, json=payload, timeout=t)
        _check_status(resp, provider=self.provider)
        data = _parse_json(resp)
        text = (data.get("message") or {}).get("content") or ""
        text = text if isinstance(text, str) else str(text)
        if on_token is not None:
            # LLM_STREAM=false：退化为一次性回调完整文本
            on_token(text)
        return text

    def list_models(self) -> List[str]:
        """已安装模型名列表；服务不可达 / 非 200 抛异常（调用方决定回退）。"""
        resp = requests.get(self._url("/api/tags"), timeout=3.0)
        _check_status(resp, provider=self.provider)
        data = _parse_json(resp)
        return [str(m.get("name", "")) for m in (data.get("models") or []) if isinstance(m, dict)]

    def health(self) -> bool:
        try:
            resp = requests.get(self._url("/api/tags"), timeout=2.0)
            return getattr(resp, "status_code", None) == 200
        except Exception:  # noqa: BLE001
            return False

    # ---- Ollama 专有 ----

    def unload(self, model: str, timeout: float = 10.0) -> bool:
        """立即卸载指定模型（``keep_alive: 0``）。返回是否成功发出请求。"""
        model = (model or "").strip()
        if not model:
            return False
        try:
            resp = requests.post(self._url("/api/generate"),
                                 json={"model": model, "keep_alive": 0}, timeout=timeout)
            return getattr(resp, "status_code", None) == 200
        except Exception:  # noqa: BLE001
            return False


# ---------------------------------------------------------------------------
# OpenAI 兼容
# ---------------------------------------------------------------------------

class OpenAICompatClient:
    """OpenAI 兼容协议：``/v1/chat/completions``（对话）、``/v1/models``（模型列表 / 健康）。

    ``base_url`` 可带或不带 ``/v1`` 后缀（``http://host:1234`` 与 ``http://host:1234/v1`` 等价）。
    """

    provider = OPENAI_PROVIDER
    # 仅提示一次：num_ctx 是 Ollama 特有参数，OpenAI 协议无对应字段，上下文窗口由后端决定
    _warned_num_ctx = False

    def __init__(self, base_url: str, api_key: str = "", timeout: Optional[float] = None):
        base = (base_url or "").rstrip("/")
        if base.endswith("/v1"):
            base = base[:-3].rstrip("/")
        self.base_url = base
        self.api_key = api_key or ""
        self._timeout = timeout
        # 后端对 reasoning_effort 返回 400 后置 True（见 chat）
        self._reasoning_effort_unsupported = False

    def _url(self, path: str) -> str:
        return f"{self.base_url}/v1{path}"

    def _headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    @classmethod
    def map_options(cls, options: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """Ollama ``options`` → OpenAI 请求字段：``temperature`` 直传、``num_predict→max_tokens``；
        ``num_ctx`` 忽略（debug 日志一次）；其余未知键忽略。"""
        out: Dict[str, Any] = {}
        for key, value in (options or {}).items():
            if key == "temperature":
                out["temperature"] = value
            elif key == "num_predict":
                try:
                    out["max_tokens"] = int(value)
                except (TypeError, ValueError):
                    pass
            elif key == "num_ctx":
                if not cls._warned_num_ctx:
                    logger.debug("LLM_PROVIDER=openai：忽略 options.num_ctx=%s，上下文窗口由后端决定", value)
                    cls._warned_num_ctx = True
            else:
                logger.debug("LLM_PROVIDER=openai：忽略不支持的 option %s", key)
        return out

    def chat(self, messages: List[Dict[str, str]], *, model: Optional[str] = None,
             options: Optional[Dict[str, Any]] = None, think: bool = False,
             on_token: Optional[TokenCallback] = None,
             should_stop: Optional[StopCheck] = None,
             on_response: Optional[ResponseHook] = None,
             timeout: Optional[float] = None) -> str:
        streaming = on_token is not None and _stream_enabled()
        payload: Dict[str, Any] = {
            "model": model or _current_model(),
            "messages": list(messages),
            "stream": streaming,
        }
        payload.update(self.map_options(options))
        # OpenAI 协议没有 Ollama 的 think 字段。思考型模型（qwen3.5 等）在兼容端点上默认开启思考，
        # 会把 max_tokens 预算全部花在 reasoning 上、content 为空——工具调用 / 摘要 / 提交信息全部失效。
        # 因此 think=False 时映射为标准字段 reasoning_effort="none"（Ollama /v1 与 OpenAI 均识别）；
        # 后端不认识该字段而返回 400 时自动去掉重试一次，并记住此后不再发送。think=True 不发送，由后端默认。
        effort = reasoning_effort_setting()
        if not think and effort and not self._reasoning_effort_unsupported:
            payload["reasoning_effort"] = effort
        t = timeout if timeout is not None else (self._timeout if self._timeout is not None else _default_timeout())
        try:
            return self._send(payload, streaming, on_token, should_stop, on_response, t)
        except LLMError as exc:
            if exc.status_code == 400 and "reasoning_effort" in payload:
                retry = {k: v for k, v in payload.items() if k != "reasoning_effort"}
                result = self._send(retry, streaming, on_token, should_stop, on_response, t)
                # 去掉字段后成功 → 确认是后端不支持 reasoning_effort，后续请求不再发送
                self._reasoning_effort_unsupported = True
                logger.info("LLM 后端 %s 不支持 reasoning_effort，已停用（思考模式由后端默认决定）", self.base_url)
                return result
            raise

    def _send(self, payload: Dict[str, Any], streaming: bool,
              on_token: Optional[TokenCallback], should_stop: Optional[StopCheck],
              on_response: Optional[ResponseHook], timeout: float) -> str:
        url = self._url("/chat/completions")
        if streaming:
            resp = requests.post(url, json=payload, headers=self._headers(), timeout=timeout, stream=True)
            _check_status(resp, provider=self.provider)
            if on_response is not None:
                on_response(resp)
            return consume_sse_stream(resp, on_token, should_stop)
        resp = requests.post(url, json=payload, headers=self._headers(), timeout=timeout)
        _check_status(resp, provider=self.provider)
        data = _parse_json(resp)
        choices = data.get("choices") or []
        if not choices or not isinstance(choices[0], dict):
            raise LLMError("响应缺少 choices，后端可能不兼容 OpenAI 协议")
        text = (choices[0].get("message") or {}).get("content") or ""
        text = text if isinstance(text, str) else str(text)
        if on_token is not None:
            on_token(text)
        return text

    def list_models(self) -> List[str]:
        """``GET /v1/models`` 的 ``data[].id``；失败抛异常（调用方回退 ``[LLM_MODEL]``）。"""
        resp = requests.get(self._url("/models"), headers=self._headers(), timeout=3.0)
        _check_status(resp, provider=self.provider)
        data = _parse_json(resp)
        items = data.get("data") or []
        return [str(m.get("id", "")) for m in items if isinstance(m, dict) and m.get("id")]

    def health(self) -> bool:
        try:
            resp = requests.get(self._url("/models"), headers=self._headers(), timeout=2.0)
            return getattr(resp, "status_code", None) == 200
        except Exception:  # noqa: BLE001
            return False


# ---------------------------------------------------------------------------
# 工厂 / 配置读取
# ---------------------------------------------------------------------------

def _read_backend_config() -> Tuple[str, str, str]:
    """返回 ``(provider, base_url, api_key)``；未识别的 provider 回退 ollama 并 warning 一次。"""
    try:
        import config as _cfg
        provider = str(getattr(_cfg, "LLM_PROVIDER", OLLAMA_PROVIDER) or OLLAMA_PROVIDER).strip().lower()
        ollama_url = str(getattr(_cfg, "OLLAMA_BASE_URL", "http://localhost:11434") or "")
        base_url = str(getattr(_cfg, "LLM_BASE_URL", "") or "").strip() or ollama_url
        api_key = str(getattr(_cfg, "LLM_API_KEY", "") or "")
    except Exception:  # noqa: BLE001
        provider, base_url, api_key = OLLAMA_PROVIDER, "http://localhost:11434", ""
    if provider not in PROVIDERS:
        global _warned_provider
        if _warned_provider != provider:
            logger.warning("LLM_PROVIDER=%r 无法识别（可选 %s），已回退 ollama", provider, "/".join(PROVIDERS))
            _warned_provider = provider
        provider = OLLAMA_PROVIDER
    return provider, base_url, api_key


_warned_provider: Optional[str] = None
_lock = threading.RLock()
_client: Optional[Any] = None
_client_key: Optional[Tuple[str, str, str]] = None
_host_clients: Dict[str, OllamaClient] = {}


def make_client(provider: str, base_url: str, api_key: str = "") -> Any:
    """按参数构造 client（不缓存）。"""
    if provider == OPENAI_PROVIDER:
        return OpenAICompatClient(base_url, api_key=api_key)
    return OllamaClient(base_url)


def get_llm_client() -> Any:
    """进程内缓存的 :class:`LLMClient`；``LLM_PROVIDER`` / ``LLM_BASE_URL`` / ``LLM_API_KEY`` 变化时重建。"""
    global _client, _client_key
    key = _read_backend_config()
    with _lock:
        if _client is None or _client_key != key:
            _client = make_client(*key)
            _client_key = key
        return _client


def reset_llm_client() -> None:
    """清空缓存（测试用）。"""
    global _client, _client_key
    with _lock:
        _client = None
        _client_key = None
        _host_clients.clear()


def client_for_host(host: Optional[str]) -> Any:
    """兼容显式 ``host`` 参数（``ReActEngine(host=…)`` / 托盘配置）的 client 选择。

    provider 为 ollama 且 ``host`` 非空、与全局地址不同 → 该地址的专用 :class:`OllamaClient`（缓存）；
    其余情况（未给 host / 与全局一致 / openai 模式）→ 全局 client。
    """
    client = get_llm_client()
    host = (host or "").strip().rstrip("/")
    if not host or client.provider != OLLAMA_PROVIDER or host == client.base_url:
        return client
    with _lock:
        if host not in _host_clients:
            _host_clients[host] = OllamaClient(host)
        return _host_clients[host]


def ollama_client() -> OllamaClient:
    """始终指向 ``OLLAMA_BASE_URL`` 的 Ollama client（嵌入模型检查 / 卸载等 Ollama 专有操作用）。"""
    try:
        import config as _cfg
        url = str(getattr(_cfg, "OLLAMA_BASE_URL", "http://localhost:11434") or "")
    except Exception:  # noqa: BLE001
        url = "http://localhost:11434"
    client = get_llm_client()
    if client.provider == OLLAMA_PROVIDER and client.base_url == url.rstrip("/"):
        return client
    with _lock:
        key = url.rstrip("/")
        if key not in _host_clients:
            _host_clients[key] = OllamaClient(key)
        return _host_clients[key]


def provider_name() -> str:
    return _read_backend_config()[0]


def connection_error_hint() -> str:
    """连接失败时给用户的下一步提示（按 provider 区分）。"""
    provider, base_url, _ = _read_backend_config()
    if provider == OPENAI_PROVIDER:
        return f"无法连接到 LLM 后端 {base_url}（LLM_PROVIDER=openai），请确认服务已启动且 LLM_BASE_URL 正确"
    return "无法连接到 Ollama，请确认服务已启动: ollama serve"


@dataclass
class ModelList:
    """模型列表查询结果：``fallback`` 为真表示后端未提供列表、``names`` 为 ``[LLM_MODEL]``。"""

    names: List[str] = field(default_factory=list)
    fallback: bool = False
    notice: str = ""


def available_models(client: Any = None) -> ModelList:
    """经 ``LLMClient.list_models`` 取模型列表；失败时 ollama 返回空列表 + 提示，
    openai 回退 ``[LLM_MODEL]`` 并提示"后端未提供模型列表"（§2 P1-2-c）。"""
    client = client or get_llm_client()
    try:
        names = [n for n in client.list_models() if n]
        return ModelList(names=names)
    except Exception as exc:  # noqa: BLE001
        if client.provider == OPENAI_PROVIDER:
            current = _current_model()
            return ModelList(names=[current] if current else [], fallback=True,
                             notice=f"{MODELS_UNAVAILABLE_NOTICE} {current}（{exc}）".strip())
        return ModelList(names=[], fallback=True,
                         notice="无法获取模型列表，请确认 Ollama 已启动: ollama serve")


def describe_backend(check_health: bool = False) -> Dict[str, Any]:
    """供 CLI ``/config`` / ``/model`` 与 Web「系统」页展示的后端概览。"""
    provider, base_url, api_key = _read_backend_config()
    info: Dict[str, Any] = {
        "provider": provider,
        "base_url": base_url,
        "api_key_set": bool(api_key),
        "embed_via_ollama": True,
    }
    try:
        import config as _cfg
        info["ollama_url"] = str(getattr(_cfg, "OLLAMA_BASE_URL", "") or "")
    except Exception:  # noqa: BLE001
        info["ollama_url"] = ""
    if check_health:
        try:
            info["healthy"] = bool(get_llm_client().health())
        except Exception:  # noqa: BLE001
            info["healthy"] = False
    return info
