from __future__ import annotations

import math

from ai_player.core.value_utils import clean_message as _clean_message
from ai_player.core.value_utils import int_value as _core_int_value
from ai_player.core.value_utils import positive_int as _core_positive_int
from ai_player.services.tts import normalize_tts_provider


def clean_message(value: object) -> str:
    return _clean_message(value)


def clean_worker_text(value: object) -> str:
    if isinstance(value, bytes):
        text = value.decode("utf-8", errors="replace")
    else:
        text = str(value or "")
    return " ".join(text.split())


def json_text(value: object, *, default: str | None) -> str | None:
    if value is None:
        return default
    text = clean_worker_text(value)
    return text or default


def align_text_results(fallback_texts: list[str], results: object) -> list[str]:
    if isinstance(results, str | bytes):
        result_items = []
    else:
        try:
            result_items = list(results)
        except TypeError:
            result_items = []
    aligned: list[str] = []
    for index, fallback in enumerate(fallback_texts):
        cleaned = result_items[index] if index < len(result_items) else fallback
        if isinstance(cleaned, bytes):
            cleaned = cleaned.decode("utf-8", errors="replace")
        elif not isinstance(cleaned, str):
            cleaned = fallback
        cleaned_text = json_text(cleaned, default="") or ""
        aligned.append(cleaned_text or fallback)
    return aligned


def clean_language(value: object) -> str | None:
    language = clean_worker_text(value).strip().lower()
    return language or None


def selected_source_language(config: object) -> str | None:
    language = str(getattr(config, "source_language", "auto") or "auto").strip().lower()
    return None if language in {"", "auto"} else language


def tts_disabled(config: object) -> bool:
    return normalize_tts_provider(getattr(config, "tts_provider", "")) == "none"


def voice_tts_suffix(config: object) -> str:
    return "wav" if normalize_tts_provider(getattr(config, "tts_provider", "")) == "vieneu" else "mp3"


def finite_seconds(value: object, default: float) -> float:
    try:
        seconds = float(value)
    except (TypeError, ValueError, OverflowError):
        return default
    if not math.isfinite(seconds):
        return default
    return seconds


def json_number(value: object, *, default: float | None) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return default
    if not math.isfinite(number):
        return default
    return number


def duration_value(value: object, *, default: float, minimum: float = 0.0) -> float:
    return max(minimum, finite_seconds(value, default))


def nonnegative_finite_seconds(value: object, default: float) -> float:
    return max(0.0, finite_seconds(value, default))


def format_hhmmss(value: object, *, round_seconds: bool = False) -> str:
    seconds_value = nonnegative_finite_seconds(value, 0.0)
    total_seconds = int(round(seconds_value)) if round_seconds else int(seconds_value)
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def int_value(value: object, default: int) -> int:
    return _core_int_value(value, default=default)


def positive_int(value: object, default: int) -> int:
    return _core_positive_int(value, default=default)


def clamped_int(value: object, *, default: int, minimum: int, maximum: int) -> int:
    return max(minimum, min(maximum, int_value(value, default=default)))


def segment_start_key(value: float) -> int:
    return int(round(finite_seconds(value, 0.0) * 1000))
