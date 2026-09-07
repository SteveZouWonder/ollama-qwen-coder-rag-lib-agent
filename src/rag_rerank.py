"""逐片段相关性筛选（rerank）：把 top-k 检索片段精筛为"真能回答问题"的子集。

背景：此前 ``judge_kb_relevance`` 只对整批片段给出一个词（relevant/irrelevant），
无法剔除混在真命中里的噪音片段，也无法解释为何保留。本模块提供两种实现：

- ``RERANKER=llm``（默认）：一次 LLM 调用（``think=False``、限 ``num_predict``），
  片段各截 400 字，输出 ``{"keep":[序号...],"notes":{"序号":"一句理由"}}``；
  解析失败/超时 → 回退 ``judge_kb_relevance`` 的整体判定（保守保留）。
- ``RERANKER=cross-encoder``：``sentence_transformers.CrossEncoder(RERANKER_MODEL)``
  逐对打分；依赖未安装时自动回退 llm 并通过 ``progress`` 提示。

设计约束：不依赖终端；进度通过 ``progress`` 回调（``rag_pipeline._emit`` 约定）；
任何失败都不会抛出到调用方，最差情况等价于旧的一词判定。
"""
from __future__ import annotations

import logging
import math
import os
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

ProgressCallback = Optional[Callable[[Dict[str, Any]], None]]
CompleteFn = Callable[[str], str]

# 每个片段送入 rerank prompt 的最大字符数
CHUNK_CHARS = 400
# LLM rerank 输出上限（keep 列表 + 短理由，足够）
NUM_PREDICT = 320
# 分数"高可信线"：最高分达到此值即认为整批明显相关，跳过 rerank 省一次调用
CONFIDENT_SCORE = 0.6
# cross-encoder 保留阈值（sigmoid 概率）
CE_KEEP_THRESHOLD = 0.3

_CE_MODEL_CACHE: Dict[str, Any] = {}


def _emit(cb: ProgressCallback, stage: str, message: str = "", **extra: Any) -> None:
    if cb is None:
        return
    try:
        event = {"stage": stage, "message": message}
        event.update(extra)
        cb(event)
    except Exception as e:  # noqa: BLE001
        logger.debug(f"progress callback error: {e}")


def _reranker_kind() -> str:
    try:
        import config as _cfg
        kind = str(getattr(_cfg, "RERANKER", "llm") or "llm")
    except Exception:  # noqa: BLE001
        kind = os.getenv("RERANKER", "llm")
    return kind.strip().lower() or "llm"


def _reranker_model() -> str:
    try:
        import config as _cfg
        return str(getattr(_cfg, "RERANKER_MODEL", "BAAI/bge-reranker-v2-m3"))
    except Exception:  # noqa: BLE001
        return os.getenv("RERANKER_MODEL", "BAAI/bge-reranker-v2-m3")


def _llm_complete(prompt: str) -> str:
    """默认 LLM 调用：全局唯一模型、``think=False``、限制输出长度。失败抛异常。"""
    from collaboration.llm_helper import complete_text
    return complete_text(prompt, num_predict=NUM_PREDICT)


def _top_score(sources: list) -> float:
    try:
        return max((float(s.get("score") or 0) for s in sources), default=0.0)
    except Exception:  # noqa: BLE001
        return 0.0


# ==================== LLM rerank ====================

def build_rerank_prompt(question: str, sources: list) -> str:
    """附录 A「逐片段相关性」提示词：每片段截 400 字，只要求输出 JSON。"""
    chunks = []
    for i, src in enumerate(sources, 1):
        content = " ".join(str(src.get("content") or "").split())[:CHUNK_CHARS]
        fname = src.get("file") or "未知文件"
        # 代码块附符号名，帮助模型判断"问 X 函数"与片段的对应关系
        label = f"{fname} · {src['symbol']}" if src.get("symbol") else fname
        chunks.append(f"[{i}]（{label}）{content}")
    return (
        "判断每个片段是否包含回答问题所需的信息。"
        '只输出 JSON：{"keep":[序号...],"notes":{"序号":"一句理由"}}；'
        "全部无关时 keep 为空数组。\n"
        f"问题：{question}\n"
        + "\n".join(chunks)
    )


def parse_rerank_output(text: str, n: int) -> Optional[Dict[str, Any]]:
    """把 LLM 输出解析为 ``{"keep": [int...], "notes": {int: str}}``。

    序号为 1-based，越界/重复/非整数项丢弃；``keep`` 缺失或非列表视为解析失败
    （返回 None，由调用方回退）。
    """
    from collaboration.llm_helper import parse_json_object

    data = parse_json_object(text or "")
    if not isinstance(data, dict) or not isinstance(data.get("keep"), list):
        return None
    keep: List[int] = []
    for item in data["keep"]:
        try:
            idx = int(str(item).strip())
        except (TypeError, ValueError):
            continue
        if 1 <= idx <= n and idx not in keep:
            keep.append(idx)
    notes: Dict[int, str] = {}
    raw_notes = data.get("notes")
    if isinstance(raw_notes, dict):
        for k, v in raw_notes.items():
            try:
                idx = int(str(k).strip())
            except (TypeError, ValueError):
                continue
            if 1 <= idx <= n and v is not None:
                notes[idx] = str(v).strip()
    return {"keep": keep, "notes": notes}


def llm_rerank(question: str, sources: list, complete: Optional[CompleteFn] = None) -> Optional[Dict[str, Any]]:
    """一次 LLM 调用逐片段判定。失败（网络/解析）返回 None。"""
    if not sources:
        return {"keep": [], "notes": {}}
    fn = complete or _llm_complete
    try:
        raw = fn(build_rerank_prompt(question, sources))
    except Exception as e:  # noqa: BLE001
        logger.warning(f"LLM rerank 调用失败: {e}")
        return None
    return parse_rerank_output(raw, len(sources))


# ==================== cross-encoder rerank ====================

def _load_cross_encoder(model_name: str):
    """惰性加载并缓存 CrossEncoder；依赖缺失抛 ImportError。"""
    if model_name in _CE_MODEL_CACHE:
        return _CE_MODEL_CACHE[model_name]
    from sentence_transformers import CrossEncoder  # type: ignore
    model = CrossEncoder(model_name)
    _CE_MODEL_CACHE[model_name] = model
    return model


def _to_probability(score: float) -> float:
    """bge-reranker 输出 logit；已在 [0,1] 内的分数视为概率直接返回。"""
    if 0.0 <= score <= 1.0:
        return score
    try:
        return 1.0 / (1.0 + math.exp(-score))
    except OverflowError:
        return 0.0 if score < 0 else 1.0


def cross_encoder_rerank(question: str, sources: list, model_name: Optional[str] = None) -> List[dict]:
    """用 CrossEncoder 逐对打分，保留概率 ≥ 阈值的片段并按分数降序。

    依赖缺失抛 ``ImportError``（调用方回退 llm）；其他异常同样抛出。
    """
    model = _load_cross_encoder(model_name or _reranker_model())
    pairs = [(question, str(s.get("content") or "")[:CHUNK_CHARS * 2]) for s in sources]
    scores = model.predict(pairs)
    kept = []
    for src, raw in zip(sources, list(scores)):
        prob = _to_probability(float(raw))
        if prob >= CE_KEEP_THRESHOLD:
            item = dict(src)
            item["rerank_score"] = round(prob, 4)
            kept.append(item)
    kept.sort(key=lambda s: s.get("rerank_score", 0), reverse=True)
    return kept


# ==================== 统一入口 ====================

def _fallback_judge(question: str, sources: list, progress: ProgressCallback, reason: str) -> List[dict]:
    """回退到整体一词判定（保守保留）。"""
    _emit(progress, "rerank_fallback", f"⚠️ 逐片段筛选不可用（{reason}），回退整体判定", reason=reason)
    try:
        from rag_pipeline import judge_kb_relevance
        keep_all = judge_kb_relevance(question, sources)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"回退判定失败，保守保留: {e}")
        keep_all = True
    return list(sources) if keep_all else []


def rerank(question: str, sources: list, progress: ProgressCallback = None,
           complete: Optional[CompleteFn] = None, kind: Optional[str] = None) -> List[dict]:
    """对通过阈值粗筛的片段做逐片段相关性筛选，返回保留的片段（保持原顺序或按分排序）。

    - 最高分 ≥ ``CONFIDENT_SCORE`` 时整批保留、不调模型（与旧逻辑一致）；
    - ``kind`` 为 None 时读取配置 ``RERANKER``；
    - 保留项附带 ``rerank_note``（llm）或 ``rerank_score``（cross-encoder）；
    - 返回空列表表示"全部无关"，调用方应视为知识库未命中。
    """
    if not sources:
        return []
    if _top_score(sources) >= CONFIDENT_SCORE:
        _emit(progress, "rerank", f"✅ 片段相关度高（{_top_score(sources):.2f}），跳过逐片段筛选", skipped=True)
        return list(sources)

    kind = (kind or _reranker_kind()).strip().lower()

    if kind == "cross-encoder":
        _emit(progress, "rerank", f"🔎 cross-encoder 逐片段打分（{len(sources)} 个片段）...")
        try:
            kept = cross_encoder_rerank(question, sources)
            _emit(progress, "rerank_done", f"🧹 保留 {len(kept)}/{len(sources)} 个相关片段",
                  kept=len(kept), total=len(sources), method="cross-encoder")
            return kept
        except ImportError:
            _emit(progress, "rerank_fallback",
                  "⚠️ 未安装 sentence-transformers，cross-encoder 不可用，已回退 llm rerank"
                  "（pip install sentence-transformers 可启用）", reason="missing_dependency")
            kind = "llm"
        except Exception as e:  # noqa: BLE001
            logger.warning(f"cross-encoder rerank 失败，回退 llm: {e}")
            _emit(progress, "rerank_fallback", f"⚠️ cross-encoder 失败（{e}），已回退 llm rerank", reason=str(e))
            kind = "llm"

    _emit(progress, "rerank", f"🔎 逐片段校验相关性（{len(sources)} 个片段，模型判定）...")
    parsed = llm_rerank(question, sources, complete=complete)
    if parsed is None:
        return _fallback_judge(question, sources, progress, "解析失败或超时")

    # 按原检索顺序保留（分数序），避免编号引用与检索排序脱节
    kept: List[dict] = []
    for idx in sorted(parsed["keep"]):
        item = dict(sources[idx - 1])
        note = parsed["notes"].get(idx)
        if note:
            item["rerank_note"] = note
        kept.append(item)
    dropped = len(sources) - len(kept)
    if kept:
        symbols = [k.get("symbol") for k in kept if k.get("symbol")]
        sym_text = ""
        if symbols:
            shown = ", ".join(f"`{x}`" for x in symbols[:3])
            sym_text = f"（{shown}" + (f" 等 {len(symbols)} 个符号）" if len(symbols) > 3 else "）")
        _emit(progress, "rerank_done", f"🧹 保留 {len(kept)}/{len(sources)} 个相关片段"
              + (f"，剔除 {dropped} 个" if dropped else "") + sym_text,
              kept=len(kept), total=len(sources), method="llm", notes=parsed["notes"], symbols=symbols)
    else:
        _emit(progress, "rerank_done", "🧹 模型判定所有片段均与问题无关",
              kept=0, total=len(sources), method="llm", notes=parsed["notes"])
    return kept
