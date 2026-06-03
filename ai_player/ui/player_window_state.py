from __future__ import annotations

from collections.abc import Callable, Iterable
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
    top_panel_hidden: bool = False
    bottom_panel_hidden: bool = False
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
    blacklisted_item_keys: set[str] = field(default_factory=set)
    blacklisted_content_keys: set[str] = field(default_factory=set)
    opened_item_keys: set[str] = field(default_factory=set)
    failed_item_keys: set[str] = field(default_factory=set)
    pending_post_id: str = ""
    current_channel_item: object | None = None
    current_post_id: str = ""
    current_url: str = ""
    pending_navigation_direction: int = 0
    pending_autoplay: bool = False
    loading_item_key: str = ""
    pending_open_item_key: str = ""
    browser_return_available: bool = False
    channel_thumbnail_source: object | None = None
    auto_load_pending_before_post_id: str = ""
    channel_continuation: str = ""
    side_panel_visible: bool = True
    side_panel_sizes: list[int] = field(default_factory=lambda: [1, 1])

    def reset_loaded_channel(self) -> None:
        self.channel_items = []
        self.channel_all_items = []
        self.channel_authenticated = False
        self.channel_translations.clear()
        self.opened_item_keys.clear()
        self.failed_item_keys.clear()
        self.auto_load_pending_before_post_id = ""
        self.channel_continuation = ""

    def replace_items(self, items: Iterable[object] | None) -> None:
        self.channel_all_items = list(items or [])

    def append_unique_items(self, items: Iterable[object] | None) -> None:
        existing = {str(getattr(item, "url", "") or "") for item in self.channel_all_items}
        added = []
        for item in list(items or []):
            url = str(getattr(item, "url", "") or "")
            if url and url in existing:
                continue
            existing.add(url)
            added.append(item)
        self.channel_all_items = [*self.channel_all_items, *added]

    def set_visible_items(self, items: Iterable[object] | None) -> None:
        self.channel_items = list(items or [])

    def item_key(self, channel_item: object | None) -> str:
        if channel_item is None:
            return ""
        return self.item_key_values(
            str(getattr(channel_item, "post_id", "") or ""),
            str(getattr(channel_item, "url", "") or ""),
        )

    @staticmethod
    def item_key_values(post_id: object, url: object) -> str:
        post_id_text = str(post_id or "").strip()
        url_text = str(url or "").strip()
        return post_id_text or url_text

    def item_translation(self, channel_item: object | None) -> str:
        return self.channel_translations.get(self.item_key(channel_item), "")

    def mark_opening(self, channel_item: object | None) -> str:
        key = self.item_key(channel_item)
        if key:
            self.loading_item_key = key
            self.failed_item_keys.discard(key)
        return key

    def mark_opened(self, channel_item: object | None = None) -> bool:
        key = self.item_key(channel_item) or self.loading_item_key
        if not key:
            return False
        self.opened_item_keys.add(key)
        self.failed_item_keys.discard(key)
        if self.loading_item_key == key:
            self.loading_item_key = ""
        return True

    def mark_failed(self, channel_item: object | None = None) -> bool:
        key = self.item_key(channel_item) or self.loading_item_key
        if not key:
            return False
        self.failed_item_keys.add(key)
        if self.loading_item_key == key:
            self.loading_item_key = ""
        return True

    def item_status(self, channel_item: object | None) -> str:
        key = self.item_key(channel_item)
        if not key:
            return ""
        if key == self.loading_item_key:
            return "loading"
        if key == self.pending_open_item_key:
            return "queued"
        if key in self.failed_item_keys:
            return "failed"
        if key and key == self.item_key(self.current_channel_item):
            return "current"
        if key in self.opened_item_keys:
            return "opened"
        return ""

    def content_key(self, channel_item: object | None) -> str:
        if channel_item is None:
            return ""
        text = str(getattr(channel_item, "text", "") or "").strip()
        title = str(getattr(channel_item, "title", "") or "").strip()
        content = text or title
        return " ".join(content.casefold().split())

    def is_blacklisted(self, channel_item: object | None) -> bool:
        key = self.item_key(channel_item)
        content_key = self.content_key(channel_item)
        return bool(
            (key and key in self.blacklisted_item_keys)
            or (content_key and content_key in self.blacklisted_content_keys)
        )

    def blacklist_item(self, channel_item: object | None) -> bool:
        key = self.item_key(channel_item)
        content_key = self.content_key(channel_item)
        if not key and not content_key:
            return False
        if key:
            self.blacklisted_item_keys.add(key)
        if content_key:
            self.blacklisted_content_keys.add(content_key)
        return True

    def unblacklist_item(self, channel_item: object | None) -> bool:
        key = self.item_key(channel_item)
        content_key = self.content_key(channel_item)
        removed = False
        if key and key in self.blacklisted_item_keys:
            self.blacklisted_item_keys.discard(key)
            removed = True
        if content_key and content_key in self.blacklisted_content_keys:
            self.blacklisted_content_keys.discard(content_key)
            removed = True
        if content_key:
            for item in self.channel_all_items:
                if self.content_key(item) != content_key:
                    continue
                item_key = self.item_key(item)
                if item_key and item_key in self.blacklisted_item_keys:
                    self.blacklisted_item_keys.discard(item_key)
                    removed = True
        return removed

    def store_translation(self, post_id: object, url: object, text: object) -> bool:
        normalized = " ".join(str(text or "").split())
        if not normalized:
            return False
        self.channel_translations[self.item_key_values(post_id, url)] = normalized
        return True

    def items_to_translate(self, has_text: Callable[[object], object]) -> list[object]:
        pending = []
        for item in self.channel_all_items:
            if not has_text(item):
                continue
            if self.item_translation(item):
                continue
            pending.append(item)
        return pending


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
