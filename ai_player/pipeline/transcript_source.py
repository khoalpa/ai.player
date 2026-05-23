from __future__ import annotations

import math
import re
from dataclasses import dataclass
from pathlib import Path

from ai_player.core.i18n import ui_text

_MAX_TRANSCRIPT_SECONDS = 30 * 24 * 60 * 60


@dataclass(frozen=True)
class TranscriptEntry:
    start: float
    end: float | None
    text: str


def load_transcript_entries(
    path_value: str,
    segment_seconds: int,
    language_id: str | None = None,
) -> list[TranscriptEntry]:
    path = Path(str(path_value or "").strip())
    if not path.exists() or not path.is_file():
        raise RuntimeError(ui_text("transcript_error_choose_file", language_id))
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    suffix = path.suffix.lower()
    if suffix in {".srt", ".vtt"} or "-->" in text:
        return parse_timed_transcript(text)
    entries = parse_bracket_timed_transcript(text)
    if entries:
        return entries
    return parse_plain_transcript(text, segment_seconds)


def parse_timed_transcript(text: str) -> list[TranscriptEntry]:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    blocks = re.split(r"\n\s*\n", normalized)
    entries: list[TranscriptEntry] = []
    for block in blocks:
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if not lines:
            continue
        time_index = next((index for index, line in enumerate(lines) if "-->" in line), -1)
        if time_index < 0:
            continue
        start_text, end_text = [part.strip() for part in lines[time_index].split("-->", 1)]
        start = parse_timestamp(start_text)
        raw_end = parse_timestamp(end_text)
        body = " ".join(lines[time_index + 1 :]).strip()
        body = re.sub(r"<[^>]+>", "", body).strip()
        if start is not None and body:
            end = max(start + 0.25, raw_end if raw_end is not None else start + 5.0)
            entries.append(TranscriptEntry(start=start, end=end, text=body))
    return entries


def parse_bracket_timed_transcript(text: str) -> list[TranscriptEntry]:
    entries: list[TranscriptEntry] = []
    for line in text.splitlines():
        match = re.match(r"\s*\[?(\d{1,2}:\d{2}(?::\d{2})?(?:[,.]\d{1,3})?)\]?\s+(.+?)\s*$", line)
        if not match:
            continue
        start = parse_timestamp(match.group(1))
        body = match.group(2).strip()
        if start is not None and body:
            entries.append(TranscriptEntry(start=start, end=None, text=body))
    return fill_missing_transcript_ends(entries)


def parse_plain_transcript(text: str, segment_seconds: int) -> list[TranscriptEntry]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    step = max(1.0, _finite_seconds(segment_seconds, default=5.0))
    return [TranscriptEntry(start=index * step, end=(index + 1) * step, text=line) for index, line in enumerate(lines)]


def fill_missing_transcript_ends(entries: list[TranscriptEntry]) -> list[TranscriptEntry]:
    filled: list[TranscriptEntry] = []
    for index, entry in enumerate(entries):
        start = _finite_seconds(entry.start, default=0.0)
        next_start = (
            _finite_seconds(entries[index + 1].start, default=start + 5.0)
            if index + 1 < len(entries)
            else start + 5.0
        )
        filled.append(TranscriptEntry(start=start, end=max(start + 0.25, next_start), text=entry.text))
    return filled


def parse_timestamp(value: str) -> float | None:
    tokens = str(value or "").strip().split()
    if not tokens:
        return None
    head = tokens[0].replace(",", ".")
    parts = head.split(":")
    try:
        if len(parts) == 2:
            minutes = float(parts[0])
            seconds = float(parts[1])
            return _finite_seconds(minutes * 60 + seconds, default=None)
        if len(parts) == 3:
            hours = float(parts[0])
            minutes = float(parts[1])
            seconds = float(parts[2])
            return _finite_seconds(hours * 3600 + minutes * 60 + seconds, default=None)
    except (ValueError, OverflowError):
        return None
    return None


def format_hhmmss(value: object) -> str:
    seconds_value = _finite_seconds(value, default=0.0)
    total_seconds = int(seconds_value)
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def _finite_seconds(value: object, *, default: float | None) -> float | None:
    try:
        seconds = float(value)
    except (TypeError, ValueError, OverflowError):
        return default
    if not math.isfinite(seconds):
        return default
    if seconds > _MAX_TRANSCRIPT_SECONDS:
        return default
    return max(0.0, seconds)
