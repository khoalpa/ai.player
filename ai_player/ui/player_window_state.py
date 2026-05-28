from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class DocumentPlaybackState:
    mode: bool = False
    elapsed_ms: int = 0
    started_at: float | None = None
    audio_sync_active: bool = False
    duration_ms: int = 0
    pages: list[object] = field(default_factory=list)
    current_page_index: int = -1
    editor_active: bool = False


@dataclass
class SubtitleOverlayState:
    entries: list[object] = field(default_factory=list)
    entries_path: str = ""
    last_text: str = ""
    live_source_text: str = ""
    live_target_text: str = ""
    live_expires_at: float = 0.0
    live_entries: list[tuple[float, float, str, str]] = field(default_factory=list)
