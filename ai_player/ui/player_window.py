from __future__ import annotations

import time

from PySide6.QtCore import Qt, QThread, QTimer
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QMainWindow,
)

from ai_player.core.config import (
    AppConfig,
)
from ai_player.core.settings_store import load_app_config
from ai_player.services.translation import (
    configured_translation_backend,
)
from ai_player.ui.cache_progress_dialog import CacheProgressDialog
from ai_player.ui.export_progress_dialog import ExportProgressDialog
from ai_player.ui.media_player import VideoPlayer
from ai_player.ui.player_window_dubbing import PlayerDubbingMixin
from ai_player.ui.player_window_export import PlayerExportMixin
from ai_player.ui.player_window_layout import PlayerLayoutMixin
from ai_player.ui.player_window_lifecycle import PlayerLifecycleMixin
from ai_player.ui.player_window_media import PlayerMediaMixin
from ai_player.ui.player_window_meeting import PlayerMeetingMixin
from ai_player.ui.player_window_runtime import PlayerRuntimeMixin
from ai_player.ui.player_window_settings import PlayerSettingsMixin
from ai_player.ui.player_window_sources import PlayerSourceMixin
from ai_player.ui.player_window_transcript import PlayerTranscriptMixin
from ai_player.ui.player_window_ui import PlayerUiMixin
from ai_player.ui.user_guide import UserGuideMixin
from ai_player.workers.dubbing_worker import DubbingWorker
from ai_player.workers.meeting_worker import MeetingWorker
from ai_player.workers.player_window_workers import (
    PlaybackCompatibilityWorker,
    RuntimeWarmupWorker,
    SourceAudioFilterWorker,
    VideoSourceWorker,
)


class PlayerWindow(
    UserGuideMixin,
    PlayerRuntimeMixin,
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
        self._video_path: str | None = None
        self._media_frame: QFrame | None = None
        self._media_frame_parent = None
        self._media_frame_layout = None
        self._media_frame_index = -1
        self._media_frame_alignment = Qt.AlignmentFlag(0)
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
        self._clamping_to_screen = False
        self._dub_worker: DubbingWorker | None = None
        self._dub_worker_generation = 0
        self._export_worker: QThread | None = None
        self._meeting_worker: MeetingWorker | None = None
        self._meeting_elapsed = "00:00:00"
        self._url_worker: VideoSourceWorker | None = None
        self._runtime_warmup_worker: RuntimeWarmupWorker | None = None
        self._document_worker = None
        self._source_filter_worker: SourceAudioFilterWorker | None = None
        self._source_filter_worker_mode = self._config.original_audio_voice_filter_mode
        self._source_filter_restart_pending = False
        self._playback_compat_worker: PlaybackCompatibilityWorker | None = None
        self._sidebar_panel_hidden = False
        self._sidebar_panel_sizes: list[int] = [900, 460]
        self._source_filter_cache: dict[str, str] = {}
        self._playback_compat_cache: dict[str, str] = {}
        self._is_seeking = False
        self._video_delay_timer = QTimer(self)
        self._video_delay_timer.setSingleShot(True)
        self._video_delay_timer.timeout.connect(self._finish_delayed_video_playback)
        self._video_delay_active = False
        self._dubbing_ready = False
        self._export_dialog: ExportProgressDialog | None = None
        self._export_terminal = False
        self._cache_dialog: CacheProgressDialog | None = None
        self._dubbing_auto_enabled = self._config.dubbing_enabled_by_default
        self._settings_save_timer = QTimer(self)
        self._settings_save_timer.setSingleShot(True)
        self._settings_save_timer.setInterval(600)
        self._settings_save_timer.timeout.connect(self._save_settings)
        self._video_fullscreen = False
        self._runtime_last_wall = time.perf_counter()
        self._runtime_last_process = time.process_time()
        self._runtime_last_system_cpu = self._read_system_cpu_times()
        self._runtime_gpu_text = self._tr("status_checking_gpu")
        self._runtime_gpu_tick = 0
        self._runtime_media_path = ""
        self._runtime_media_info_path = ""
        self._runtime_media_info_text = self._tr("status_no_video")

        self._transcript_segments: list[tuple[str, str]] = []

        self._apply_theme()
        self._build_ui()
        self._retranslate_ui()
        self._player = VideoPlayer(self._video_widget)
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

        self.statusBar().showMessage(
            self._tr("status_translation_backend").format(
                backend=configured_translation_backend(self._config),
                voice=self._config.tts_voice,
            )
        )
        self._start_runtime_warmup()

    def _start_runtime_warmup(self) -> None:
        if not self._config.runtime_warmup_enabled:
            return
        app = QApplication.instance()
        if app is not None and app.platformName().lower() == "offscreen":
            return
        if self._runtime_warmup_worker is not None:
            return
        worker = RuntimeWarmupWorker(self._config, self)
        self._runtime_warmup_worker = worker
        worker.status_changed.connect(self.statusBar().showMessage)
        worker.failed.connect(lambda message: self.statusBar().showMessage(f"Runtime warm-up failed: {message}"))
        worker.finished.connect(lambda worker=worker: self._runtime_warmup_worker_finished(worker))
        worker.start()

    def _runtime_warmup_worker_finished(self, worker: RuntimeWarmupWorker) -> None:
        if self._runtime_warmup_worker is worker:
            self._runtime_warmup_worker = None
        worker.deleteLater()
