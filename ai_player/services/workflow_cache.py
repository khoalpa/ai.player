from __future__ import annotations

import hashlib
import json
import os
import threading
import unicodedata
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class WorkflowTextCacheKey:
    namespace: str
    runtime_fingerprint: str
    source_language: str
    context: str
    text: str


_CACHE_LOCK = threading.Lock()
_TEXT_CACHE: OrderedDict[WorkflowTextCacheKey, str] = OrderedDict()
_TEXT_CACHE_STATS = {"hits": 0, "misses": 0, "writes": 0}


def workflow_text_cache_enabled() -> bool:
    return str(os.getenv("AI_PLAYER_WORKFLOW_TEXT_CACHE", "1")).strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }


def get_text_result(
    namespace: str,
    runtime_key: Any,
    text: object,
    *,
    source_language: object = "",
    context: object = "",
) -> str | None:
    if not workflow_text_cache_enabled():
        return None
    key = _text_cache_key(namespace, runtime_key, text, source_language=source_language, context=context)
    with _CACHE_LOCK:
        cached = _TEXT_CACHE.get(key)
        if cached is None:
            _TEXT_CACHE_STATS["misses"] += 1
            return None
        _TEXT_CACHE_STATS["hits"] += 1
        _TEXT_CACHE.move_to_end(key)
        return cached


def put_text_result(
    namespace: str,
    runtime_key: Any,
    text: object,
    result: object,
    *,
    source_language: object = "",
    context: object = "",
) -> str:
    clean_result = _normalize_result(result)
    if not workflow_text_cache_enabled():
        return clean_result
    key = _text_cache_key(namespace, runtime_key, text, source_language=source_language, context=context)
    with _CACHE_LOCK:
        _TEXT_CACHE[key] = clean_result
        _TEXT_CACHE.move_to_end(key)
        _TEXT_CACHE_STATS["writes"] += 1
        _trim_cache_locked()
    return clean_result


def clear_workflow_text_cache() -> None:
    with _CACHE_LOCK:
        _TEXT_CACHE.clear()
        for key in _TEXT_CACHE_STATS:
            _TEXT_CACHE_STATS[key] = 0


def workflow_text_cache_size() -> int:
    with _CACHE_LOCK:
        return len(_TEXT_CACHE)


def workflow_text_cache_stats() -> dict[str, int]:
    with _CACHE_LOCK:
        return {**_TEXT_CACHE_STATS, "entries": len(_TEXT_CACHE)}


def _text_cache_key(
    namespace: str,
    runtime_key: Any,
    text: object,
    *,
    source_language: object,
    context: object,
) -> WorkflowTextCacheKey:
    return WorkflowTextCacheKey(
        namespace=str(namespace or "").strip(),
        runtime_fingerprint=_runtime_fingerprint(runtime_key),
        source_language=_normalize_text(source_language),
        context=_normalize_text(context),
        text=_normalize_text(text),
    )


def _runtime_fingerprint(value: Any) -> str:
    try:
        payload = json.dumps(value, sort_keys=True, ensure_ascii=True, default=repr)
    except TypeError:
        payload = repr(value)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _normalize_text(value: object) -> str:
    text = " ".join(str(value or "").split())
    text = unicodedata.normalize("NFC", text)
    return "".join(ch for ch in text if unicodedata.category(ch) != "Cf")


def _normalize_result(value: object) -> str:
    return " ".join(str(value or "").split())


def _max_entries() -> int:
    try:
        return max(0, int(os.getenv("AI_PLAYER_WORKFLOW_TEXT_CACHE_ENTRIES", "4096")))
    except (TypeError, ValueError, OverflowError):
        return 4096


def _trim_cache_locked() -> None:
    max_entries = _max_entries()
    if max_entries <= 0:
        _TEXT_CACHE.clear()
        return
    while len(_TEXT_CACHE) > max_entries:
        _TEXT_CACHE.popitem(last=False)
