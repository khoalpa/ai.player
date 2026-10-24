from __future__ import annotations

import re
from collections.abc import Callable

from ai_player.domain.text_dedupe import collapse_repeated_phrases
from ai_player.domain.worker_values import clean_worker_text

_NUMBER_RE = re.compile(r"\d+(?:[.,]\d+)*")


def translation_needs_retry(source: object, translated: object) -> bool:
    original = clean_worker_text(source)
    candidate = clean_worker_text(translated)
    if not original:
        return False
    if not candidate:
        return True
    ratio = len(candidate) / max(1, len(original))
    if ratio < 0.35 or ratio > 2.5:
        return True
    source_numbers = {_normalize_number(value) for value in _NUMBER_RE.findall(original)}
    translated_numbers = {_normalize_number(value) for value in _NUMBER_RE.findall(candidate)}
    return bool(source_numbers - translated_numbers)


def translate_with_quality_guard(
    translate: Callable[[str, str | None], object],
    text: object,
    source_language: str | None,
    *,
    retries: int = 1,
    on_retry: Callable[[], None] | None = None,
    on_fallback: Callable[[], None] | None = None,
) -> str:
    original = clean_worker_text(text)
    if not original:
        return ""
    best = ""
    attempts = max(1, retries + 1)
    for _attempt in range(attempts):
        try:
            candidate = collapse_repeated_phrases(clean_worker_text(translate(original, source_language)))
        except Exception:
            candidate = ""
        if candidate:
            best = candidate
        if not translation_needs_retry(original, candidate):
            return candidate
        if _attempt + 1 < attempts and on_retry is not None:
            on_retry()
    if not best and on_fallback is not None:
        on_fallback()
    return best or original


def _normalize_number(value: str) -> str:
    return value.replace(",", ".")
