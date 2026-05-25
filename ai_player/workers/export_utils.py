from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from ai_player.core.config import AppConfig
from ai_player.pipeline.export_plan import TranscriptCue
from ai_player.services.ffmpeg import concat_escape, probe_duration_seconds, safe_float
from ai_player.services.ffmpeg import make_silence as ffmpeg_make_silence
from ai_player.services.ffmpeg import to_wav as ffmpeg_to_wav
from ai_player.services.ffmpeg import trim_leading_silence as ffmpeg_trim_leading_silence
from ai_player.services.whisper_runtime import effective_whisper_device
from ai_player.workers.worker_values import (
    align_text_results,
    clean_message,
    duration_value,
    format_hhmmss,
    json_number,
    json_text,
    tts_disabled,
)


@dataclass(frozen=True)
class TranscriptExportItem:
    index: int
    entry: object
    original: str
    start_seconds: float
    end_seconds: float


@dataclass(frozen=True)
class SegmentExportItem:
    index: int
    original: str
    start_seconds: float
    duration_seconds: float


def _ffmpeg_escape(path: Path) -> str:
    return concat_escape(path)


def _make_silence(duration_seconds: float, output_path: Path) -> None:
    ffmpeg_make_silence(_duration_value(duration_seconds, default=0.0), output_path)


def _to_wav(input_path: Path, output_path: Path) -> None:
    ffmpeg_to_wav(input_path, output_path)


def _trim_leading_silence(audio_path: Path) -> Path:
    return ffmpeg_trim_leading_silence(audio_path)


def _duration_seconds(path: Path) -> float:
    return _probe_duration_seconds(path)


def _probe_duration_seconds(path: Path) -> float:
    return _duration_value(probe_duration_seconds(path), default=0.0)


def _safe_float(value: object) -> float | None:
    return safe_float(value)


def _duration_value(value: object, *, default: float, minimum: float = 0.0) -> float:
    return duration_value(value, default=default, minimum=minimum)


def _percent_value(value: object) -> int:
    return max(0, min(100, int(round(_duration_value(value, default=0.0)))))


def _entry_time_bounds(entry: object, segment_seconds: float) -> tuple[float, float]:
    start_seconds = _duration_value(getattr(entry, "start", 0.0), default=0.0)
    fallback_end = start_seconds + max(0.25, segment_seconds)
    end_value = getattr(entry, "end", None)
    end_seconds = fallback_end if end_value is None else _duration_value(end_value, default=fallback_end)
    return start_seconds, max(start_seconds + 0.25, end_seconds)


def _transcript_export_items(
    entries: list[object],
    *,
    segment_seconds: float,
    export_range: object,
    cleaner,
    source_language: str | None,
    should_abort: Callable[[], bool],
) -> list[TranscriptExportItem]:
    raw_items = []
    for index, entry in enumerate(entries):
        if should_abort():
            break
        entry_start, entry_end = _entry_time_bounds(entry, segment_seconds)
        if not export_range.overlaps(entry_start, entry_end):
            continue
        original = _json_text(getattr(entry, "text", ""), default="") or ""
        if original:
            raw_items.append((index, entry, original, entry_start, entry_end))
    cleaned_items = _clean_transcript_many(cleaner, [item[2] for item in raw_items], source_language)
    return [
        TranscriptExportItem(index, entry, original, entry_start, entry_end)
        for (index, entry, _raw, entry_start, entry_end), original in zip(raw_items, cleaned_items, strict=False)
        if original
    ]


def _segment_export_items(
    segments: list[object],
    *,
    cleaner,
    source_language: str | None,
    should_abort: Callable[[], bool],
) -> list[SegmentExportItem]:
    raw_items = []
    for index, segment in enumerate(segments):
        if should_abort():
            break
        original = _json_text(getattr(segment, "text", ""), default="") or ""
        if not original:
            continue
        start_seconds = max(0.0, _json_number(getattr(segment, "start", 0.0), default=0.0) or 0.0)
        end_value = _json_number(getattr(segment, "end", None), default=None)
        end_seconds = max(start_seconds + 0.25, end_value if end_value is not None else start_seconds + 0.25)
        raw_items.append((index, original, start_seconds, max(0.25, end_seconds - start_seconds)))
    cleaned_items = _clean_transcript_many(cleaner, [item[1] for item in raw_items], source_language)
    return [
        SegmentExportItem(index, original, start_seconds, duration_seconds)
        for (index, _raw, start_seconds, duration_seconds), original in zip(raw_items, cleaned_items, strict=False)
        if original
    ]


def _cue_time_bounds(cue: object) -> tuple[float, float]:
    start_seconds = _duration_value(getattr(cue, "start_seconds", 0.0), default=0.0)
    end_seconds = _duration_value(getattr(cue, "end_seconds", None), default=start_seconds + 0.25)
    return start_seconds, max(start_seconds + 0.25, end_seconds)


def _nonempty_file(path: Path) -> bool:
    try:
        return path.exists() and path.stat().st_size > 0
    except OSError:
        return False


def _format_hhmmss(value: object) -> str:
    return format_hhmmss(value)


def _render_text_page_image(title: str, text: str, output_path: Path) -> Path:
    from PIL import Image, ImageDraw

    image = Image.new("RGB", (1920, 1080), "#ffffff")
    draw = ImageDraw.Draw(image)
    title_font = _font(54, bold=True)
    body_font = _font(34)
    draw.rectangle((0, 0, 1919, 1079), outline="#d5dee8", width=4)
    draw.text((90, 72), title, fill="#0f172a", font=title_font)
    y = 170
    for line in _wrap_text(str(text or ""), body_font, 1700, draw)[:22]:
        draw.text((96, y), line, fill="#334155", font=body_font)
        y += 46
    image.save(output_path)
    return output_path


def _font(size: int, bold: bool = False):
    from PIL import ImageFont

    candidates = [
        "C:/Windows/Fonts/segoeuib.ttf" if bold else "C:/Windows/Fonts/segoeui.ttf",
        "C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf",
    ]
    for candidate in candidates:
        try:
            return ImageFont.truetype(candidate, size)
        except Exception:
            continue
    return ImageFont.load_default()


def _wrap_text(text: str, font, max_width: int, draw) -> list[str]:
    lines: list[str] = []
    current = ""
    for word in str(text or "").split():
        candidate = f"{current} {word}".strip()
        if draw.textbbox((0, 0), candidate, font=font)[2] <= max_width:
            current = candidate
            continue
        if current:
            lines.append(current)
        current = word
    if current:
        lines.append(current)
    return lines


def _segments_words_payload(
    segments: list[object],
    info: object,
) -> dict[str, object]:
    payload_segments: list[dict[str, object]] = []
    for segment in segments:
        words_payload: list[dict[str, object]] = []
        for word in getattr(segment, "words", None) or []:
            words_payload.append(
                {
                    "start": _json_number(getattr(word, "start", 0.0), default=0.0),
                    "end": _json_number(getattr(word, "end", 0.0), default=0.0),
                    "word": _json_text(getattr(word, "word", ""), default=""),
                    "probability": _json_number(getattr(word, "probability", 0.0), default=0.0),
                }
            )
        payload_segments.append(
            {
                "start": _json_number(getattr(segment, "start", 0.0), default=0.0),
                "end": _json_number(getattr(segment, "end", 0.0), default=0.0),
                "text": _json_text(getattr(segment, "text", ""), default=""),
                "words": words_payload,
            }
        )
    return {
        "language": _json_text(getattr(info, "language", None), default=None),
        "language_probability": _json_number(getattr(info, "language_probability", None), default=None),
        "segments": payload_segments,
    }


def _source_cues_from_segments(
    segments: list[object],
    cleaner,
    source_language: str | None,
) -> list[TranscriptCue]:
    raw_items: list[tuple[float, float, str]] = []
    for segment in segments:
        original = _json_text(getattr(segment, "text", ""), default="") or ""
        if not original:
            continue
        start_seconds = max(0.0, _json_number(getattr(segment, "start", 0.0), default=0.0) or 0.0)
        end_value = _json_number(getattr(segment, "end", None), default=None)
        end_seconds = max(start_seconds + 0.25, end_value if end_value is not None else start_seconds + 0.25)
        raw_items.append((start_seconds, end_seconds, original))
    cleaned = _clean_transcript_many(cleaner, [item[2] for item in raw_items], source_language)
    cues = []
    for (start_seconds, end_seconds, _raw), text in zip(raw_items, cleaned, strict=False):
        clean_text = _json_text(text, default="")
        if clean_text:
            cues.append(TranscriptCue(start_seconds, end_seconds, clean_text))
    return cues


def _json_number(value: object, *, default: float | None) -> float | None:
    return json_number(value, default=default)


def _json_text(value: object, *, default: str | None) -> str | None:
    return json_text(value, default=default)


def _clean_message(value: object) -> str:
    return clean_message(value)


def _clean_transcript_many(cleaner, texts: list[str], source_language: str | None) -> list[str]:
    fallback_texts = [_json_text(text, default="") or "" for text in texts]
    clean_many = getattr(cleaner, "clean_many", None)
    if callable(clean_many):
        return _align_text_results(fallback_texts, clean_many(texts, source_language))
    clean_one = getattr(cleaner, "clean", None)
    if callable(clean_one):
        return _align_text_results(fallback_texts, [clean_one(text, source_language) for text in texts])
    return fallback_texts


def _translate_texts(translator, texts: list[str], source_language: str | None) -> list[str]:
    fallback_texts = [_json_text(text, default="") or "" for text in texts]
    translate_many = getattr(translator, "translate_many", None)
    if callable(translate_many):
        return _align_text_results(fallback_texts, translate_many(fallback_texts, source_language))
    translate_one = getattr(translator, "translate", None)
    if callable(translate_one):
        return _align_text_results(fallback_texts, [translate_one(text, source_language) for text in fallback_texts])
    return fallback_texts


def _align_text_results(fallback_texts: list[str], results: object) -> list[str]:
    return align_text_results(fallback_texts, results)


def _tts_disabled(config: AppConfig) -> bool:
    return tts_disabled(config)


def _export_reference_audio_required(config: AppConfig) -> bool:
    return bool(_tts_disabled(config) or config.dubbing_auto_voice_gender or config.dubbing_auto_match_audio)


def _export_worker_count() -> int:
    configured = os.getenv("AI_PLAYER_EXPORT_WORKERS", "").strip()
    if configured:
        try:
            return max(1, min(16, int(configured)))
        except (OverflowError, ValueError):
            pass
    cpu_count = os.cpu_count() or 2
    return max(1, min(8, max(4, cpu_count // 2)))


def _effective_whisper_device(value: str) -> str:
    return effective_whisper_device(value)
