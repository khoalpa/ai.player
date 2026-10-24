from __future__ import annotations

import time
from functools import partial

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox

from ai_player.adapters.media.document_reader import is_supported_document_path
from ai_player.ui.features.base import Feature
from ai_player.ui.player_window_utils import (
    repair_mojibake as _repair_mojibake,
)
from ai_player.ui.player_window_utils import (
    safe_native_dubbing_config as _safe_native_dubbing_config,
)
from ai_player.workers.dubbing_worker import DubbingWorker


class PlayerDubbingFeature(Feature):
    def _play(self) -> None:
        if not self.context.channel_browser._video_path:
            if self.context.sources._url_is_opening():
                self.context.window.statusBar().showMessage(self.context.settings._tr("status_url_opening_wait"))
                return
            if self.context.settings._selected_audio_source() == "document_editor":
                self.context.media.playback.dubbing_auto_enabled = True
                self.context.layout._dub_button.setChecked(True)
            return
        if self.context.media.document.mode and not self.context.layout._dub_button.isChecked():
            self.context.media.playback.dubbing_auto_enabled = True
            self.context.layout._dub_button.setChecked(True)
            return
        if self.context.layout._dub_button.isChecked():
            if self.context.lifecycle.workers.dubbing_worker is None:
                self.context.dubbing._start_dubbing()
                return
            if not self.context.media.playback.dubbing_ready:
                self.context.media._pause_active_source()
                self.context.window.statusBar().showMessage(self.context.settings._tr("status_waiting_dubbing_ready"))
                return
        self.context.media._play_active_source()

    def _pause(self) -> None:
        self.context.media._pause_active_source()
        if (
            self.context.has("_subtitle_overlay")
            and not self.context.transcript.state.live_source_text
            and not self.context.transcript.state.live_target_text
        ):
            self.context.layout._subtitle_overlay.hide()

    def _stop(self) -> None:
        self.context.media._cancel_delayed_video_playback()
        if self.context.media.document.mode:
            self.context.media.document.elapsed_ms = 0
            self.context.media.document.started_at = None
        else:
            self.context.layout._player.stop()
        if self.context.has("_subtitle_overlay"):
            self.context.layout._subtitle_overlay.hide()
        self.context.meeting._stop_meeting(wait_ms=0)
        self.context.dubbing._stop_dubbing()

    def _reset_app(self) -> None:
        self.context.media.playback.dubbing_auto_enabled = False
        self.context.media._cancel_delayed_video_playback()
        self.context.meeting._stop_meeting(wait_ms=1500)
        if self.context.has("_dub_button"):
            self.context.layout._dub_button.setChecked(False)
        self.context.dubbing._stop_dubbing()
        self.context.sources._stop_video_url(wait_ms=1500)
        if self.context.lifecycle.workers.export_worker is not None:
            self.context.lifecycle._stop_worker_attr("_export_worker", wait_ms=1500)
            self.context.layout._export_button.setEnabled(True)
        self.context.media._exit_video_fullscreen()
        self.context.layout._player.stop()
        self.context.media.document.reset_for_video(reset_duration=True)
        self.context.media._set_document_mode(False)
        self.context.channel_browser._video_path = None
        self.context.channel_browser._video_source_http_headers = {}
        self.context.runtime.state.media_path = ""
        self.context.runtime.state.media_info_path = ""
        self.context.runtime.state.media_info_text = self.context.settings._tr("status_no_video")
        self.context.layout._media_stack.setCurrentWidget(self.context.layout._video_placeholder)
        self.context.layout._document_view.setReadOnly(True)
        self.context.layout._document_view.clear()
        self.context.transcript._clear_transcript()
        self.context.layout._transcript_path_edit.clear()
        self.context.layout._position_slider.setValue(0)
        self.context.layout._time_label.setText("00:00 / 00:00")
        self.context.settings._set_combo_data(self.context.layout._audio_source_combo, "original")
        self.context.sources._invalidate_subtitle_entries()
        self.context.ui._set_dubbing_ready(True)
        self.context.layout._source_label.setText(self.context.settings._tr("source_empty"))
        self.context.media._reset_panel_sizes(show_status=False)
        self.context.settings._save_settings()
        self.context.window.statusBar().showMessage(self.context.settings._tr("status_reset_done"))

    def _toggle_dubbing(self, checked: bool) -> None:
        self.context.media.playback.dubbing_auto_enabled = checked
        if checked:
            self.context.dubbing._start_dubbing()
        else:
            self.context.dubbing._stop_dubbing()

    def _start_dubbing_from_header(self) -> None:
        self.context.media.playback.dubbing_auto_enabled = True
        self.context.layout._dub_button.setChecked(True)
        self.context.dubbing._start_dubbing()

    def _start_dubbing(self) -> None:
        if self.context.get("_closing", False):
            return
        if self.context.settings._selected_audio_source() == "document_editor":
            if not self.context.sources._prepare_document_editor_source():
                return
        if not self.context.channel_browser._video_path:
            if self.context.sources._url_is_opening():
                self.context.window.statusBar().showMessage(self.context.settings._tr("status_url_opening_then_dub"))
                return
            self.context.layout._dub_button.setChecked(False)
            QMessageBox.information(
                self.context.window,
                self.context.settings._tr("app_title"),
                self.context.settings._tr("msg_open_source_first"),
            )
            return
        if self.context.media.document.mode and self.context.settings._selected_audio_source() != "document_editor":
            self.context.settings._set_combo_data(self.context.layout._audio_source_combo, "transcript")
        elif is_supported_document_path(self.context.channel_browser._video_path):
            self.context.sources._load_document(self.context.channel_browser._video_path, start_dubbing=False)
            if not self.context.media.document.mode:
                self.context.layout._dub_button.setChecked(False)
                return
        if (
            self.context.lifecycle.workers.dubbing_worker is not None
            and self.context.lifecycle.workers.dubbing_worker.isRunning()
        ):
            self.context.window.statusBar().showMessage(self.context.settings._tr("status_dubbing_running"))
            return

        self.context.layout._player.set_volume(self.context.layout._volume_slider.value())
        self.context.ui._set_dubbing_ready(False, self.context.settings._tr("status_dubbing_buffering"))
        self.context.settings._save_settings()
        dubbing_config = _safe_native_dubbing_config(self.context.config)
        if dubbing_config != self.context.config:
            self.context.window.statusBar().showMessage(self.context.settings._tr("status_safe_cpu_fallback"))
        if dubbing_config.audio_source in {"system", "microphone", "system_microphone"}:
            self.context.ui._set_dubbing_ready(True, self.context.settings._tr("status_live_capture"))
            self.context.media._play_active_source()
        self.context.lifecycle.workers.dubbing_worker_generation += 1
        self.context.dubbing._dubbing_stop_requested = False
        worker_generation = self.context.lifecycle.workers.dubbing_worker_generation
        get_time_ms = (
            self.context.media._document_time_ms
            if self.context.media.document.mode
            else self.context.layout._player.get_time_ms
        )
        is_playing = (
            self.context.media._document_is_playing
            if self.context.media.document.mode
            else self.context.media._source_is_playing_for_dubbing
        )
        self.context.lifecycle.workers.dubbing_worker = DubbingWorker(
            self.context.channel_browser._video_path,
            get_time_ms,
            is_playing,
            dubbing_config,
            source_http_headers=self.context.get("_video_source_http_headers", {}) or {},
            parent=self.context.window,
        )
        for signal, callback in (
            (
                self.context.lifecycle.workers.dubbing_worker.status_changed,
                self.context.dubbing._dubbing_status_changed,
            ),
            (
                self.context.lifecycle.workers.dubbing_worker.segment_ready,
                self.context.transcript._append_dubbing_segment,
            ),
            (
                self.context.lifecycle.workers.dubbing_worker.subtitle_ready,
                self.context.dubbing._set_timed_live_subtitle,
            ),
            (
                self.context.lifecycle.workers.dubbing_worker.audio_started,
                self.context.media._sync_document_to_audio_start,
            ),
            (
                self.context.lifecycle.workers.dubbing_worker.playback_pause_requested,
                self.context.media._pause_for_dubbing_buffer,
            ),
            (
                self.context.lifecycle.workers.dubbing_worker.playback_resume_requested,
                self.context.media._resume_after_dubbing_buffer,
            ),
            (self.context.lifecycle.workers.dubbing_worker.failed, self.context.dubbing._dubbing_failed),
        ):
            signal.connect(
                partial(self.context.dubbing._dispatch_dubbing_signal, worker_generation, callback),
                Qt.ConnectionType.QueuedConnection,
            )
        self.context.lifecycle.workers.dubbing_worker.finished.connect(
            lambda generation=worker_generation: self.context.dubbing._dubbing_worker_finished(generation)
        )
        self.context.lifecycle.workers.dubbing_worker.start()
        self.context.window.statusBar().showMessage(self.context.settings._tr("status_dubbing_starting"))

    def _dispatch_dubbing_signal(self, generation: int, callback, *args) -> None:
        if (
            generation != self.context.lifecycle.workers.dubbing_worker_generation
            or self.context.get("_dubbing_stop_requested", False)
            or self.context.get("_closing", False)
            or self.context.lifecycle.workers.dubbing_worker is None
        ):
            return
        callback(*args)

    def _stop_dubbing(self, wait_ms: int = 0) -> bool:
        self.context.media._cancel_delayed_video_playback()
        worker = self.context.lifecycle.workers.dubbing_worker
        if worker:
            self.context.dubbing._dubbing_stop_requested = True
            self.context.ui._set_dubbing_ready(not self.context.layout._dub_button.isChecked())
            worker.stop()
            if not worker.wait(wait_ms):
                return False
            self.context.lifecycle.workers.dubbing_worker = None
            worker.deleteLater()
        self.context.runtime._clear_background_task_detail("Realtime dubbing")
        self.context.ui._set_dubbing_ready(True)
        if not self.context.media.playback.dubbing_auto_enabled:
            self.context.layout._dub_button.setChecked(False)
        return True

    def _dubbing_worker_finished(self, generation: int) -> None:
        if generation == self.context.lifecycle.workers.dubbing_worker_generation:
            worker = self.context.lifecycle.workers.dubbing_worker
            self.context.lifecycle.workers.dubbing_worker = None
            if worker is not None:
                worker.deleteLater()
            self.context.runtime._clear_background_task_detail("Realtime dubbing")
            self.context.ui._set_dubbing_ready(
                self.context.get("_dubbing_stop_requested", False) or not self.context.layout._dub_button.isChecked()
            )

    def _dubbing_status_changed(self, message: str) -> None:
        clean = _repair_mojibake(message)
        self.context.runtime._set_background_task_detail("Realtime dubbing", clean)
        self.context.window.statusBar().showMessage(clean)

    def _dubbing_failed(self, message: str) -> None:
        self.context.media.playback.dubbing_auto_enabled = False
        self.context.dubbing._stop_dubbing()
        self.context.layout._dub_button.setChecked(False)
        self.context.ui._set_dubbing_ready(True)
        QMessageBox.warning(
            self.context.window, self.context.settings._tr("dubbing_unavailable_title"), _repair_mojibake(message)
        )
        self.context.window.statusBar().showMessage(self.context.settings._tr("status_dubbing_stopped"))

    def _set_live_subtitle(self, source_text: str, target_text: str = "") -> None:
        source_text = _repair_mojibake(str(source_text or "").strip())
        target_text = _repair_mojibake(str(target_text or "").strip())
        if not source_text and not target_text:
            return
        self.context.transcript.state.live_source_text = source_text
        self.context.transcript.state.live_target_text = target_text or source_text
        text_for_duration = (
            self.context.transcript.state.live_target_text or self.context.transcript.state.live_source_text
        )
        seconds = max(3.0, min(12.0, len(text_for_duration) / 16.0))
        self.context.transcript.state.live_expires_at = time.monotonic() + seconds
        if self.context.sources._selected_subtitle_mode() != "off":
            self.context.transcript.state.last_text = ""
            self.context.media._update_subtitle_overlay()

    def _set_timed_live_subtitle(
        self,
        start_seconds: float,
        duration_seconds: float,
        source_text: str,
        target_text: str = "",
    ) -> None:
        source_text = _repair_mojibake(str(source_text or "").strip())
        target_text = _repair_mojibake(str(target_text or "").strip())
        if not source_text and not target_text:
            return
        try:
            start = max(0.0, float(start_seconds))
        except (TypeError, ValueError, OverflowError):
            start = 0.0
        try:
            duration = max(0.25, float(duration_seconds))
        except (TypeError, ValueError, OverflowError):
            duration = 0.25
        text_for_duration = target_text or source_text
        readable_duration = max(1.0, min(12.0, len(text_for_duration) / 14.0))
        end = start + max(duration, readable_duration)
        entries = self.context.get("_live_subtitle_entries", [])
        key = (round(start, 3), source_text, target_text)
        entries = [entry for entry in entries if (round(entry[0], 3), entry[2], entry[3]) != key]
        entries.append((start, end, source_text, target_text or source_text))
        self.context.transcript.state.live_entries = sorted(entries, key=lambda entry: entry[0])[-200:]
        if self.context.sources._selected_subtitle_mode() != "off":
            self.context.transcript.state.last_text = ""
            self.context.media._update_subtitle_overlay()
