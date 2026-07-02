from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlparse

from ai_player.workers.worker_values import finite_seconds, positive_int

DIRECT_HTTP_SOURCE_CACHE_SUFFIXES = {
    ".avi",
    ".m4v",
    ".mkv",
    ".mov",
    ".mp4",
    ".webm",
}
LIVE_CAPTURE_AUDIO_SOURCES = {"system", "microphone", "system_microphone"}
ASYNC_SEGMENT_AUDIO_SOURCES = {"original", "subtitle"}
TRANSCRIPT_AUDIO_SOURCES = {"transcript", "document_editor"}


def can_process_segments_async(audio_source: str) -> bool:
    return str(audio_source or "") in ASYNC_SEGMENT_AUDIO_SOURCES


def is_live_capture_source(audio_source: str) -> bool:
    return str(audio_source or "") in LIVE_CAPTURE_AUDIO_SOURCES


def segment_worker_count(
    *,
    audio_source: str,
    lookahead_segments: object,
    env_value: str | None = None,
    cpu_count: int | None = None,
) -> int:
    configured = str(os.getenv("AI_PLAYER_DUBBING_SEGMENT_WORKERS", "") if env_value is None else env_value).strip()
    if configured:
        try:
            return max(1, min(8, int(configured)))
        except (OverflowError, ValueError):
            pass
    if audio_source == "original":
        return 1
    available_cpus = cpu_count if cpu_count is not None else os.cpu_count()
    available_cpus = available_cpus or 2
    return max(1, min(4, available_cpus // 2, positive_int(lookahead_segments, default=1)))


def source_audio_cache_input(audio_source: str, source: str) -> str | None:
    if audio_source != "original":
        return None
    value = str(source or "").strip()
    if not value:
        return None
    if is_http_source(value):
        parsed = urlparse(value)
        suffix = Path(parsed.path).suffix.lower()
        if parsed.scheme.lower() in {"http", "https"} and suffix in DIRECT_HTTP_SOURCE_CACHE_SUFFIXES:
            return value
        return None
    source_path = Path(value)
    if source_path.exists() and source_path.is_file():
        return str(source_path)
    return None


def is_http_source(value: str) -> bool:
    return urlparse(str(value or "")).scheme.lower() in {"http", "https"}


def required_ready_ahead_seconds(
    *,
    audio_source: str,
    min_ready_ahead_seconds: object,
    segment_seconds: object,
    prebuffer_segments: object,
) -> float:
    if audio_source in TRANSCRIPT_AUDIO_SOURCES:
        return 0.5
    configured_ready_ahead = max(0.0, finite_seconds(min_ready_ahead_seconds, 0.0))
    segment_ready_ahead = max(
        0.5,
        max(0.25, finite_seconds(segment_seconds, 5.0)) * positive_int(prebuffer_segments, default=1),
    )
    return min(configured_ready_ahead, segment_ready_ahead)
