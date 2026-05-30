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
class PlaybackUiState:
    seeking: bool = False
    sidebar_panel_hidden: bool = False
    sidebar_panel_sizes: list[int] = field(default_factory=list)
    video_delay_active: bool = False
    dubbing_ready: bool = False
    dubbing_auto_enabled: bool = False
    export_dialog: object | None = None
    export_terminal: bool = False
    cache_dialog: object | None = None
    video_fullscreen: bool = False


@dataclass
class MediaFrameState:
    frame: object | None = None
    parent: object | None = None
    layout: object | None = None
    index: int = -1
    alignment: object | None = None
    detached_for_fullscreen: bool = False


@dataclass
class TelegramChannelState:
    channel_items: list[object] = field(default_factory=list)
    channel_all_items: list[object] = field(default_factory=list)
    channel_authenticated: bool = False
    channel_translations: dict[str, str] = field(default_factory=dict)
    pending_post_id: str = ""
    current_channel_item: object | None = None
    current_post_id: str = ""
    current_url: str = ""
    pending_navigation_direction: int = 0
    pending_autoplay: bool = False
    browser_return_available: bool = False
    channel_thumbnail_source: object | None = None
    auto_load_pending_before_post_id: str = ""
    side_panel_visible: bool = True
    side_panel_sizes: list[int] = field(default_factory=lambda: [1, 1])


@dataclass
class WorkerLifecycleState:
    dubbing_worker: object | None = None
    dubbing_worker_generation: int = 0
    export_worker: object | None = None
    meeting_worker: object | None = None
    meeting_elapsed: str = "00:00:00"
    telegram_worker: object | None = None
    telegram_translation_worker: object | None = None
    pending_telegram_url: str = ""
    document_worker: object | None = None
