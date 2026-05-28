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


@dataclass
class MediaProcessingState:
    source_filter_worker: object | None = None
    source_filter_worker_mode: str = ""
    source_filter_worker_model: str = ""
    source_filter_restart_pending: bool = False
    playback_compat_worker: object | None = None
    source_filter_cache: dict[str, str] = field(default_factory=dict)
    playback_compat_cache: dict[str, str] = field(default_factory=dict)


@dataclass
class RuntimeStatusState:
    last_wall: float = 0.0
    last_process: float = 0.0
    last_system_cpu: object | None = None
    gpu_text: str = ""
    gpu_tick: int = 0
    media_path: str = ""
    media_info_path: str = ""
    media_info_text: str = ""


@dataclass
class WorkerLifecycleState:
    dubbing_worker: object | None = None
    dubbing_worker_generation: int = 0
    export_worker: object | None = None
    meeting_worker: object | None = None
    meeting_elapsed: str = "00:00:00"
    telegram_worker: object | None = None
    pending_telegram_url: str = ""
    document_worker: object | None = None
