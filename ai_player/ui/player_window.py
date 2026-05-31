from __future__ import annotations

import time

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QMainWindow,
)

from ai_player.core.config import (
    AppConfig,
)
from ai_player.core.settings_store import load_app_config
from ai_player.services.translation import (
    configured_translation_backend,
)
from ai_player.ui.media_player import VideoPlayer
from ai_player.ui.player_window_dubbing import PlayerDubbingMixin
from ai_player.ui.player_window_export import PlayerExportMixin
from ai_player.ui.player_window_layout import PlayerLayoutMixin
from ai_player.ui.player_window_lifecycle import PlayerLifecycleMixin
from ai_player.ui.player_window_media import DEFAULT_SIDEBAR_PANEL_SIZES, PlayerMediaMixin
from ai_player.ui.player_window_meeting import PlayerMeetingMixin
from ai_player.ui.player_window_offline_models import PlayerOfflineModelsMixin
from ai_player.ui.player_window_runtime import PlayerRuntimeMixin
from ai_player.ui.player_window_settings import PlayerSettingsMixin
from ai_player.ui.player_window_sources import PlayerSourceMixin
from ai_player.ui.player_window_state import (
    DocumentPlaybackState,
    MediaFrameState,
    MediaProcessingState,
    PlaybackUiState,
    RuntimeStatusState,
    SubtitleOverlayState,
    TelegramChannelState,
    WorkerLifecycleState,
)
from ai_player.ui.player_window_transcript import PlayerTranscriptMixin
from ai_player.ui.player_window_ui import PlayerUiMixin
from ai_player.ui.runtime_warmup_controller import RuntimeWarmupController
from ai_player.ui.user_guide import UserGuideMixin
from ai_player.ui.video_url_controller import VideoUrlController


class PlayerWindow(
    UserGuideMixin,
    PlayerRuntimeMixin,
    PlayerOfflineModelsMixin,
    PlayerTranscriptMixin,
    PlayerSettingsMixin,
    PlayerMediaMixin,
    PlayerUiMixin,
    PlayerLayoutMixin,
    PlayerSourceMixin,
    PlayerExportMixin,
    PlayerMeetingMixin,
    PlayerDubbingMixin,
    PlayerLifecycleMixin,
    QMainWindow,
):
    def __init__(self) -> None:
        super().__init__()

        self._config = load_app_config(AppConfig.from_env())
        self._document_state = DocumentPlaybackState()
        self._subtitle_state = SubtitleOverlayState()
        self._media_processing_state = MediaProcessingState(
            source_filter_worker_mode=self._config.original_audio_voice_filter_mode,
            source_filter_worker_model=self._config.original_audio_voice_filter_model,
        )
        self._runtime_state = RuntimeStatusState(
            last_wall=time.perf_counter(),
            last_process=time.process_time(),
            last_system_cpu=self._read_system_cpu_times(),
            gpu_text=self._tr("status_checking_gpu"),
            media_info_text=self._tr("status_no_video"),
        )
        self._playback_ui_state = PlaybackUiState(
            sidebar_panel_sizes=list(DEFAULT_SIDEBAR_PANEL_SIZES),
            dubbing_auto_enabled=self._config.dubbing_enabled_by_default,
        )
        self._media_frame_state = MediaFrameState(alignment=Qt.AlignmentFlag(0))
        self._worker_lifecycle_state = WorkerLifecycleState()
        self._telegram_channel_state = TelegramChannelState(
            channel_thumbnail_source=QPixmap(),
            blacklisted_item_keys=set(self._config.telegram_blacklisted_item_keys),
            blacklisted_content_keys=set(self._config.telegram_blacklisted_content_keys),
        )
        self._video_path: str | None = None
        self._document_mode = False
        self._document_elapsed_ms = 0
        self._document_started_at: float | None = None
        self._document_audio_sync_active = False
        self._document_duration_ms = 0
        self._document_pages = []
        self._document_current_page_index = -1
        self._document_editor_active = False
        self._subtitle_entries = []
        self._subtitle_entries_path = ""
        self._last_subtitle_text = ""
        self._live_subtitle_source_text = ""
        self._live_subtitle_target_text = ""
        self._live_subtitle_expires_at = 0.0
        self._live_subtitle_entries: list[tuple[float, float, str, str]] = []
        self._clamping_to_screen = False
        self._video_url = VideoUrlController(self)
        self._runtime_warmup = RuntimeWarmupController(self)
        self._video_delay_timer = QTimer(self)
        self._video_delay_timer.setSingleShot(True)
        self._video_delay_timer.timeout.connect(self._finish_delayed_video_playback)
        self._settings_save_timer = QTimer(self)
        self._settings_save_timer.setSingleShot(True)
        self._settings_save_timer.setInterval(600)
        self._settings_save_timer.timeout.connect(self._save_settings)

        self._transcript_segments: list[tuple[str, str]] = []

        self._apply_theme()
        self._build_ui()
        self._retranslate_ui()
        self._player = VideoPlayer(self._video_widget, self)
        self._player.set_volume(self._volume_slider.value())

        self._timer = QTimer(self)
        self._timer.setInterval(250)
        self._timer.timeout.connect(self._refresh_position)
        self._timer.start()

        self._runtime_timer = QTimer(self)
        self._runtime_timer.setInterval(2000)
        self._runtime_timer.timeout.connect(self._refresh_runtime_tab)
        self._runtime_timer.start()
        self._refresh_runtime_tab()

        self.statusBar().showMessage(self._runtime_startup_status_message())
        self._start_runtime_warmup()

    @property
    def _document_mode(self) -> bool:
        return self._document_state.mode

    @_document_mode.setter
    def _document_mode(self, value: bool) -> None:
        self._document_state.mode = bool(value)

    @property
    def _document_elapsed_ms(self) -> int:
        return self._document_state.elapsed_ms

    @_document_elapsed_ms.setter
    def _document_elapsed_ms(self, value: int) -> None:
        self._document_state.elapsed_ms = int(value or 0)

    @property
    def _document_started_at(self) -> float | None:
        return self._document_state.started_at

    @_document_started_at.setter
    def _document_started_at(self, value: float | None) -> None:
        self._document_state.started_at = value

    @property
    def _document_audio_sync_active(self) -> bool:
        return self._document_state.audio_sync_active

    @_document_audio_sync_active.setter
    def _document_audio_sync_active(self, value: bool) -> None:
        self._document_state.audio_sync_active = bool(value)

    @property
    def _document_duration_ms(self) -> int:
        return self._document_state.duration_ms

    @_document_duration_ms.setter
    def _document_duration_ms(self, value: int) -> None:
        self._document_state.duration_ms = max(0, int(value or 0))

    @property
    def _document_pages(self) -> list[object]:
        return self._document_state.pages

    @_document_pages.setter
    def _document_pages(self, value: list[object]) -> None:
        self._document_state.pages = list(value or [])

    @property
    def _document_current_page_index(self) -> int:
        return self._document_state.current_page_index

    @_document_current_page_index.setter
    def _document_current_page_index(self, value: int) -> None:
        self._document_state.current_page_index = int(value or 0)

    @property
    def _document_editor_active(self) -> bool:
        return self._document_state.editor_active

    @_document_editor_active.setter
    def _document_editor_active(self, value: bool) -> None:
        self._document_state.editor_active = bool(value)

    @property
    def _subtitle_entries(self) -> list[object]:
        return self._subtitle_state.entries

    @_subtitle_entries.setter
    def _subtitle_entries(self, value: list[object]) -> None:
        self._subtitle_state.entries = list(value or [])

    @property
    def _subtitle_entries_path(self) -> str:
        return self._subtitle_state.entries_path

    @_subtitle_entries_path.setter
    def _subtitle_entries_path(self, value: str) -> None:
        self._subtitle_state.entries_path = str(value or "")

    @property
    def _last_subtitle_text(self) -> str:
        return self._subtitle_state.last_text

    @_last_subtitle_text.setter
    def _last_subtitle_text(self, value: str) -> None:
        self._subtitle_state.last_text = str(value or "")

    @property
    def _live_subtitle_source_text(self) -> str:
        return self._subtitle_state.live_source_text

    @_live_subtitle_source_text.setter
    def _live_subtitle_source_text(self, value: str) -> None:
        self._subtitle_state.live_source_text = str(value or "")

    @property
    def _live_subtitle_target_text(self) -> str:
        return self._subtitle_state.live_target_text

    @_live_subtitle_target_text.setter
    def _live_subtitle_target_text(self, value: str) -> None:
        self._subtitle_state.live_target_text = str(value or "")

    @property
    def _live_subtitle_expires_at(self) -> float:
        return self._subtitle_state.live_expires_at

    @_live_subtitle_expires_at.setter
    def _live_subtitle_expires_at(self, value: float) -> None:
        self._subtitle_state.live_expires_at = float(value or 0.0)

    @property
    def _live_subtitle_entries(self) -> list[tuple[float, float, str, str]]:
        return self._subtitle_state.live_entries

    @_live_subtitle_entries.setter
    def _live_subtitle_entries(self, value: list[tuple[float, float, str, str]]) -> None:
        self._subtitle_state.live_entries = list(value or [])

    @property
    def _source_filter_worker(self) -> object | None:
        return self._media_processing_state.source_filter_worker

    @_source_filter_worker.setter
    def _source_filter_worker(self, value: object | None) -> None:
        self._media_processing_state.source_filter_worker = value

    @property
    def _source_filter_worker_mode(self) -> str:
        return self._media_processing_state.source_filter_worker_mode

    @_source_filter_worker_mode.setter
    def _source_filter_worker_mode(self, value: str) -> None:
        self._media_processing_state.source_filter_worker_mode = str(value or "")

    @property
    def _source_filter_worker_model(self) -> str:
        return self._media_processing_state.source_filter_worker_model

    @_source_filter_worker_model.setter
    def _source_filter_worker_model(self, value: str) -> None:
        self._media_processing_state.source_filter_worker_model = str(value or "")

    @property
    def _source_filter_restart_pending(self) -> bool:
        return self._media_processing_state.source_filter_restart_pending

    @_source_filter_restart_pending.setter
    def _source_filter_restart_pending(self, value: bool) -> None:
        self._media_processing_state.source_filter_restart_pending = bool(value)

    @property
    def _playback_compat_worker(self) -> object | None:
        return self._media_processing_state.playback_compat_worker

    @_playback_compat_worker.setter
    def _playback_compat_worker(self, value: object | None) -> None:
        self._media_processing_state.playback_compat_worker = value

    @property
    def _source_filter_cache(self) -> dict[str, str]:
        return self._media_processing_state.source_filter_cache

    @_source_filter_cache.setter
    def _source_filter_cache(self, value: dict[str, str]) -> None:
        self._media_processing_state.source_filter_cache = dict(value or {})

    @property
    def _playback_compat_cache(self) -> dict[str, str]:
        return self._media_processing_state.playback_compat_cache

    @_playback_compat_cache.setter
    def _playback_compat_cache(self, value: dict[str, str]) -> None:
        self._media_processing_state.playback_compat_cache = dict(value or {})

    @property
    def _media_frame(self) -> object | None:
        return self._media_frame_state.frame

    @_media_frame.setter
    def _media_frame(self, value: object | None) -> None:
        self._media_frame_state.frame = value

    @property
    def _media_frame_parent(self) -> object | None:
        return self._media_frame_state.parent

    @_media_frame_parent.setter
    def _media_frame_parent(self, value: object | None) -> None:
        self._media_frame_state.parent = value

    @property
    def _media_frame_layout(self) -> object | None:
        return self._media_frame_state.layout

    @_media_frame_layout.setter
    def _media_frame_layout(self, value: object | None) -> None:
        self._media_frame_state.layout = value

    @property
    def _media_frame_index(self) -> int:
        return self._media_frame_state.index

    @_media_frame_index.setter
    def _media_frame_index(self, value: int) -> None:
        self._media_frame_state.index = int(value or 0)

    @property
    def _media_frame_alignment(self) -> object | None:
        return self._media_frame_state.alignment

    @_media_frame_alignment.setter
    def _media_frame_alignment(self, value: object | None) -> None:
        self._media_frame_state.alignment = value

    @property
    def _media_frame_detached_for_fullscreen(self) -> bool:
        return self._media_frame_state.detached_for_fullscreen

    @_media_frame_detached_for_fullscreen.setter
    def _media_frame_detached_for_fullscreen(self, value: bool) -> None:
        self._media_frame_state.detached_for_fullscreen = bool(value)

    @property
    def _is_seeking(self) -> bool:
        return self._playback_ui_state.seeking

    @_is_seeking.setter
    def _is_seeking(self, value: bool) -> None:
        self._playback_ui_state.seeking = bool(value)

    @property
    def _top_panel_hidden(self) -> bool:
        return self._playback_ui_state.top_panel_hidden

    @_top_panel_hidden.setter
    def _top_panel_hidden(self, value: bool) -> None:
        self._playback_ui_state.top_panel_hidden = bool(value)

    @property
    def _bottom_panel_hidden(self) -> bool:
        return self._playback_ui_state.bottom_panel_hidden

    @_bottom_panel_hidden.setter
    def _bottom_panel_hidden(self, value: bool) -> None:
        self._playback_ui_state.bottom_panel_hidden = bool(value)

    @property
    def _sidebar_panel_hidden(self) -> bool:
        return self._playback_ui_state.sidebar_panel_hidden

    @_sidebar_panel_hidden.setter
    def _sidebar_panel_hidden(self, value: bool) -> None:
        self._playback_ui_state.sidebar_panel_hidden = bool(value)

    @property
    def _sidebar_panel_sizes(self) -> list[int]:
        return self._playback_ui_state.sidebar_panel_sizes

    @_sidebar_panel_sizes.setter
    def _sidebar_panel_sizes(self, value: list[int]) -> None:
        self._playback_ui_state.sidebar_panel_sizes = [int(item or 0) for item in list(value or [])]

    @property
    def _video_delay_active(self) -> bool:
        return self._playback_ui_state.video_delay_active

    @_video_delay_active.setter
    def _video_delay_active(self, value: bool) -> None:
        self._playback_ui_state.video_delay_active = bool(value)

    @property
    def _dubbing_ready(self) -> bool:
        return self._playback_ui_state.dubbing_ready

    @_dubbing_ready.setter
    def _dubbing_ready(self, value: bool) -> None:
        self._playback_ui_state.dubbing_ready = bool(value)

    @property
    def _dubbing_auto_enabled(self) -> bool:
        return self._playback_ui_state.dubbing_auto_enabled

    @_dubbing_auto_enabled.setter
    def _dubbing_auto_enabled(self, value: bool) -> None:
        self._playback_ui_state.dubbing_auto_enabled = bool(value)

    @property
    def _export_dialog(self) -> object | None:
        return self._playback_ui_state.export_dialog

    @_export_dialog.setter
    def _export_dialog(self, value: object | None) -> None:
        self._playback_ui_state.export_dialog = value

    @property
    def _export_terminal(self) -> bool:
        return self._playback_ui_state.export_terminal

    @_export_terminal.setter
    def _export_terminal(self, value: bool) -> None:
        self._playback_ui_state.export_terminal = bool(value)

    @property
    def _cache_dialog(self) -> object | None:
        return self._playback_ui_state.cache_dialog

    @_cache_dialog.setter
    def _cache_dialog(self, value: object | None) -> None:
        self._playback_ui_state.cache_dialog = value

    @property
    def _video_fullscreen(self) -> bool:
        return self._playback_ui_state.video_fullscreen

    @_video_fullscreen.setter
    def _video_fullscreen(self, value: bool) -> None:
        self._playback_ui_state.video_fullscreen = bool(value)

    @property
    def _dub_worker(self) -> object | None:
        return self._worker_lifecycle_state.dubbing_worker

    @_dub_worker.setter
    def _dub_worker(self, value: object | None) -> None:
        self._worker_lifecycle_state.dubbing_worker = value

    @property
    def _dub_worker_generation(self) -> int:
        return self._worker_lifecycle_state.dubbing_worker_generation

    @_dub_worker_generation.setter
    def _dub_worker_generation(self, value: int) -> None:
        self._worker_lifecycle_state.dubbing_worker_generation = int(value or 0)

    @property
    def _export_worker(self) -> object | None:
        return self._worker_lifecycle_state.export_worker

    @_export_worker.setter
    def _export_worker(self, value: object | None) -> None:
        self._worker_lifecycle_state.export_worker = value

    @property
    def _meeting_worker(self) -> object | None:
        return self._worker_lifecycle_state.meeting_worker

    @_meeting_worker.setter
    def _meeting_worker(self, value: object | None) -> None:
        self._worker_lifecycle_state.meeting_worker = value

    @property
    def _meeting_elapsed(self) -> str:
        return self._worker_lifecycle_state.meeting_elapsed

    @_meeting_elapsed.setter
    def _meeting_elapsed(self, value: str) -> None:
        self._worker_lifecycle_state.meeting_elapsed = str(value or "")

    @property
    def _telegram_worker(self) -> object | None:
        return self._worker_lifecycle_state.telegram_worker

    @_telegram_worker.setter
    def _telegram_worker(self, value: object | None) -> None:
        self._worker_lifecycle_state.telegram_worker = value

    @property
    def _telegram_translation_worker(self) -> object | None:
        return self._worker_lifecycle_state.telegram_translation_worker

    @_telegram_translation_worker.setter
    def _telegram_translation_worker(self, value: object | None) -> None:
        self._worker_lifecycle_state.telegram_translation_worker = value

    @property
    def _pending_telegram_url(self) -> str:
        return self._worker_lifecycle_state.pending_telegram_url

    @_pending_telegram_url.setter
    def _pending_telegram_url(self, value: str) -> None:
        self._worker_lifecycle_state.pending_telegram_url = str(value or "")

    @property
    def _document_worker(self) -> object | None:
        return self._worker_lifecycle_state.document_worker

    @_document_worker.setter
    def _document_worker(self, value: object | None) -> None:
        self._worker_lifecycle_state.document_worker = value

    @property
    def _telegram_channel_items(self) -> list[object]:
        return self._telegram_channel_state.channel_items

    @_telegram_channel_items.setter
    def _telegram_channel_items(self, value: list[object]) -> None:
        self._telegram_channel_state.channel_items = list(value or [])

    @property
    def _telegram_channel_all_items(self) -> list[object]:
        return self._telegram_channel_state.channel_all_items

    @_telegram_channel_all_items.setter
    def _telegram_channel_all_items(self, value: list[object]) -> None:
        self._telegram_channel_state.channel_all_items = list(value or [])

    @property
    def _telegram_channel_authenticated(self) -> bool:
        return self._telegram_channel_state.channel_authenticated

    @_telegram_channel_authenticated.setter
    def _telegram_channel_authenticated(self, value: bool) -> None:
        self._telegram_channel_state.channel_authenticated = bool(value)

    @property
    def _telegram_channel_translations(self) -> dict[str, str]:
        return self._telegram_channel_state.channel_translations

    @_telegram_channel_translations.setter
    def _telegram_channel_translations(self, value: dict[str, str]) -> None:
        self._telegram_channel_state.channel_translations = dict(value or {})

    @property
    def _pending_telegram_post_id(self) -> str:
        return self._telegram_channel_state.pending_post_id

    @_pending_telegram_post_id.setter
    def _pending_telegram_post_id(self, value: str) -> None:
        self._telegram_channel_state.pending_post_id = str(value or "")

    @property
    def _current_telegram_channel_item(self) -> object | None:
        return self._telegram_channel_state.current_channel_item

    @_current_telegram_channel_item.setter
    def _current_telegram_channel_item(self, value: object | None) -> None:
        self._telegram_channel_state.current_channel_item = value

    @property
    def _current_telegram_post_id(self) -> str:
        return self._telegram_channel_state.current_post_id

    @_current_telegram_post_id.setter
    def _current_telegram_post_id(self, value: str) -> None:
        self._telegram_channel_state.current_post_id = str(value or "")

    @property
    def _current_telegram_url(self) -> str:
        return self._telegram_channel_state.current_url

    @_current_telegram_url.setter
    def _current_telegram_url(self, value: str) -> None:
        self._telegram_channel_state.current_url = str(value or "")

    @property
    def _pending_telegram_navigation_direction(self) -> int:
        return self._telegram_channel_state.pending_navigation_direction

    @_pending_telegram_navigation_direction.setter
    def _pending_telegram_navigation_direction(self, value: int) -> None:
        self._telegram_channel_state.pending_navigation_direction = int(value or 0)

    @property
    def _pending_telegram_autoplay(self) -> bool:
        return self._telegram_channel_state.pending_autoplay

    @_pending_telegram_autoplay.setter
    def _pending_telegram_autoplay(self, value: bool) -> None:
        self._telegram_channel_state.pending_autoplay = bool(value)

    @property
    def _telegram_browser_return_available(self) -> bool:
        return self._telegram_channel_state.browser_return_available

    @_telegram_browser_return_available.setter
    def _telegram_browser_return_available(self, value: bool) -> None:
        self._telegram_channel_state.browser_return_available = bool(value)

    @property
    def _telegram_channel_thumbnail_source(self) -> object | None:
        return self._telegram_channel_state.channel_thumbnail_source

    @_telegram_channel_thumbnail_source.setter
    def _telegram_channel_thumbnail_source(self, value: object | None) -> None:
        self._telegram_channel_state.channel_thumbnail_source = value

    @property
    def _telegram_auto_load_pending_before_post_id(self) -> str:
        return self._telegram_channel_state.auto_load_pending_before_post_id

    @_telegram_auto_load_pending_before_post_id.setter
    def _telegram_auto_load_pending_before_post_id(self, value: str) -> None:
        self._telegram_channel_state.auto_load_pending_before_post_id = str(value or "")

    @property
    def _telegram_side_panel_visible(self) -> bool:
        return self._telegram_channel_state.side_panel_visible

    @_telegram_side_panel_visible.setter
    def _telegram_side_panel_visible(self, value: bool) -> None:
        self._telegram_channel_state.side_panel_visible = bool(value)

    @property
    def _telegram_side_panel_sizes(self) -> list[int]:
        return self._telegram_channel_state.side_panel_sizes

    @_telegram_side_panel_sizes.setter
    def _telegram_side_panel_sizes(self, value: list[int]) -> None:
        self._telegram_channel_state.side_panel_sizes = [int(item or 0) for item in list(value or [])]

    @property
    def _runtime_last_wall(self) -> float:
        return self._runtime_state.last_wall

    @_runtime_last_wall.setter
    def _runtime_last_wall(self, value: float) -> None:
        self._runtime_state.last_wall = float(value or 0.0)

    @property
    def _runtime_last_process(self) -> float:
        return self._runtime_state.last_process

    @_runtime_last_process.setter
    def _runtime_last_process(self, value: float) -> None:
        self._runtime_state.last_process = float(value or 0.0)

    @property
    def _runtime_last_system_cpu(self) -> object | None:
        return self._runtime_state.last_system_cpu

    @_runtime_last_system_cpu.setter
    def _runtime_last_system_cpu(self, value: object | None) -> None:
        self._runtime_state.last_system_cpu = value

    @property
    def _runtime_gpu_text(self) -> str:
        return self._runtime_state.gpu_text

    @_runtime_gpu_text.setter
    def _runtime_gpu_text(self, value: str) -> None:
        self._runtime_state.gpu_text = str(value or "")

    @property
    def _runtime_gpu_tick(self) -> int:
        return self._runtime_state.gpu_tick

    @_runtime_gpu_tick.setter
    def _runtime_gpu_tick(self, value: int) -> None:
        self._runtime_state.gpu_tick = int(value or 0)

    @property
    def _runtime_media_path(self) -> str:
        return self._runtime_state.media_path

    @_runtime_media_path.setter
    def _runtime_media_path(self, value: str) -> None:
        self._runtime_state.media_path = str(value or "")

    @property
    def _runtime_media_info_path(self) -> str:
        return self._runtime_state.media_info_path

    @_runtime_media_info_path.setter
    def _runtime_media_info_path(self, value: str) -> None:
        self._runtime_state.media_info_path = str(value or "")

    @property
    def _runtime_media_info_text(self) -> str:
        return self._runtime_state.media_info_text

    @_runtime_media_info_text.setter
    def _runtime_media_info_text(self, value: str) -> None:
        self._runtime_state.media_info_text = str(value or "")

    def _start_runtime_warmup(self) -> None:
        self._runtime_warmup.start()

    def _runtime_warmup_status_changed(self, message: str) -> None:
        self._runtime_warmup.status_changed(message)

    def _runtime_warmup_finished_successfully(self, timings: object) -> None:
        self._runtime_warmup.finished_successfully(timings)

    def _runtime_warmup_failed(self, message: str) -> None:
        self._runtime_warmup.failed(message)

    def _show_runtime_warmup_status(self, message: str) -> None:
        self._runtime_warmup.show_status(message)

    def _can_replace_status_with_runtime_warmup(self) -> bool:
        return self._runtime_warmup.can_replace_status()

    def _runtime_startup_status_message(self) -> str:
        return self._tr("status_translation_backend").format(
            backend=configured_translation_backend(self._config),
            voice=self._config.tts_voice,
        )

    def _stop_runtime_warmup(self, wait_ms: int = 5000) -> bool:
        return self._runtime_warmup.stop(wait_ms=wait_ms)
