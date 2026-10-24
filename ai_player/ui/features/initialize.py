from __future__ import annotations

import time

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPixmap

from ai_player.ui.background_task_controller import BackgroundTaskController
from ai_player.ui.features.media import DEFAULT_SIDEBAR_PANEL_SIZES
from ai_player.ui.media_player import VideoPlayer
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
from ai_player.ui.runtime_tab_controller import RuntimeTabController
from ai_player.ui.runtime_warmup_controller import RuntimeWarmupController
from ai_player.ui.video_url_controller import VideoUrlController


def initialize_window(context) -> None:
    context.media.document = DocumentPlaybackState()
    context.transcript.state = SubtitleOverlayState()
    context.media.processing = MediaProcessingState(
        source_filter_worker_mode=context.config.original_audio_voice_filter_mode,
        source_filter_worker_model=context.config.original_audio_voice_filter_model,
    )
    context.runtime.state = RuntimeStatusState(
        last_wall=time.perf_counter(),
        last_process=time.process_time(),
        last_system_cpu=RuntimeTabController.read_system_cpu_times(),
        gpu_text=context.settings._tr("status_checking_gpu"),
        media_info_text=context.settings._tr("status_no_video"),
    )
    context.runtime.controller = RuntimeTabController(context, context.runtime.state)
    context.media.playback = PlaybackUiState(
        sidebar_panel_sizes=list(DEFAULT_SIDEBAR_PANEL_SIZES),
        dubbing_auto_enabled=context.config.dubbing_enabled_by_default,
    )
    context.media.frame = MediaFrameState(alignment=Qt.AlignmentFlag(0))
    context.lifecycle.workers = WorkerLifecycleState()
    context.sources.channel = TelegramChannelState(
        channel_thumbnail_source=QPixmap(),
        blacklisted_item_keys=set(context.config.telegram_blacklisted_item_keys),
        blacklisted_content_keys=set(context.config.telegram_blacklisted_content_keys),
    )
    context.channel_browser._video_path: str | None = None
    context.channel_browser._video_source_http_headers: dict[str, str] = {}
    context.media.document.mode = False
    context.media.document.elapsed_ms = 0
    context.media.document.started_at: float | None = None
    context.media.document.audio_sync_active = False
    context.media.document.duration_ms = 0
    context.media.document.pages = []
    context.media.document.current_page_index = -1
    context.media.document.editor_active = False
    context.transcript.state.entries = []
    context.transcript.state.entries_path = ""
    context.transcript.state.last_text = ""
    context.transcript.state.live_source_text = ""
    context.transcript.state.live_target_text = ""
    context.transcript.state.live_expires_at = 0.0
    context.transcript.state.live_entries: list[tuple[float, float, str, str]] = []
    context.task_center.details_controller = BackgroundTaskController(
        record_event=context.task_center._record_task_center_event,
        refresh=context.task_center._refresh_task_center,
    )
    context.lifecycle._clamping_to_screen = False
    context.sources.url_controller = VideoUrlController(context)
    context.runtime.warmup_controller = RuntimeWarmupController(context)
    context.provider_preview._init_provider_preview()
    context.layout._video_delay_timer = QTimer(context.window)
    context.layout._video_delay_timer.setSingleShot(True)
    context.layout._video_delay_timer.timeout.connect(context.media._finish_delayed_video_playback)
    context.layout._settings_save_timer = QTimer(context.window)
    context.layout._settings_save_timer.setSingleShot(True)
    context.layout._settings_save_timer.setInterval(600)
    context.layout._settings_save_timer.timeout.connect(context.settings._save_settings)

    context.transcript._transcript_segments: list[dict | tuple[str, str]] = []

    context.ui._apply_theme()
    context.layout._build_ui()
    context.settings._retranslate_ui()
    context.layout._player = VideoPlayer(context.layout._video_widget, context.window)
    context.layout._player.on_playback_state_changed(lambda *_args: context.task_center._refresh_task_center())
    context.layout._player.set_volume(context.layout._volume_slider.value())

    context.layout._timer = QTimer(context.window)
    context.layout._timer.setInterval(250)
    context.layout._timer.timeout.connect(context.media._refresh_position)
    context.layout._timer.start()

    context.layout._runtime_timer = QTimer(context.window)
    context.layout._runtime_timer.setInterval(2000)
    context.layout._runtime_timer.timeout.connect(context.runtime._refresh_runtime_tab)
    context.layout._runtime_timer.timeout.connect(context.task_center._refresh_task_center)
    context.layout._runtime_timer.start()
    context.runtime._refresh_runtime_tab()
    context.task_center._refresh_task_center()

    context.window.statusBar().showMessage(context.runtime._runtime_startup_status_message())
    context.runtime._start_runtime_warmup()
