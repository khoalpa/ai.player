from __future__ import annotations

import time

from PySide6.QtWidgets import QMessageBox

from ai_player.core.settings_store import save_app_config
from ai_player.services.document_reader import is_supported_document_path
from ai_player.ui.player_window_utils import (
    repair_mojibake as _repair_mojibake,
)
from ai_player.ui.player_window_utils import (
    safe_native_dubbing_config as _safe_native_dubbing_config,
)
from ai_player.workers.dubbing_worker import DubbingWorker


class PlayerDubbingMixin:
    def _play(self) -> None:
        if not self._video_path:
            if self._url_is_opening():
                self.statusBar().showMessage(self._tr("status_url_opening_wait"))
                return
            if self._selected_audio_source() == "document_editor":
                self._dubbing_auto_enabled = True
                self._dub_button.setChecked(True)
            return
        if self._document_mode and not self._dub_button.isChecked():
            self._dubbing_auto_enabled = True
            self._dub_button.setChecked(True)
            return
        if self._dub_button.isChecked():
            if self._dub_worker is None:
                self._start_dubbing()
                return
            if not self._dubbing_ready:
                self._pause_active_source()
                self.statusBar().showMessage(self._tr("status_waiting_dubbing_ready"))
                return
        self._play_active_source()

    def _pause(self) -> None:
        self._pause_active_source()
        if (
            hasattr(self, "_subtitle_overlay")
            and not self._live_subtitle_source_text
            and not self._live_subtitle_target_text
        ):
            self._subtitle_overlay.hide()

    def _stop(self) -> None:
        self._cancel_delayed_video_playback()
        if self._document_mode:
            self._document_elapsed_ms = 0
            self._document_started_at = None
        else:
            self._player.stop()
        if hasattr(self, "_subtitle_overlay"):
            self._subtitle_overlay.hide()
        self._stop_meeting()
        self._stop_dubbing()

    def _reset_app(self) -> None:
        self._dubbing_auto_enabled = False
        self._cancel_delayed_video_playback()
        self._stop_meeting(wait_ms=1500)
        if hasattr(self, "_dub_button"):
            self._dub_button.setChecked(False)
        self._stop_dubbing()
        if self._url_worker is not None:
            self._stop_worker_attr("_url_worker", wait_ms=1500)
            self._open_url_button.setEnabled(True)
        if self._export_worker is not None:
            self._stop_worker_attr("_export_worker", wait_ms=1500)
            self._export_button.setEnabled(True)
        self._exit_video_fullscreen()
        self._player.stop()
        self._set_document_mode(False)
        self._document_editor_active = False
        self._document_pages = []
        self._document_current_page_index = -1
        self._document_elapsed_ms = 0
        self._document_started_at = None
        self._document_audio_sync_active = False
        self._document_duration_ms = 0
        self._video_path = None
        self._runtime_media_path = ""
        self._runtime_media_info_path = ""
        self._runtime_media_info_text = self._tr("status_no_video")
        self._media_stack.setCurrentWidget(self._video_placeholder)
        self._document_view.setReadOnly(True)
        self._document_view.clear()
        self._clear_transcript()
        self._transcript_path_edit.clear()
        self._position_slider.setValue(0)
        self._time_label.setText("00:00 / 00:00")
        self._set_combo_data(self._audio_source_combo, "original")
        self._invalidate_subtitle_entries()
        self._set_dubbing_ready(True)
        self._source_label.setText(self._tr("source_empty"))
        self._reset_panel_sizes(show_status=False)
        self._save_settings()
        self.statusBar().showMessage(self._tr("status_reset_done"))

    def _toggle_dubbing(self, checked: bool) -> None:
        self._dubbing_auto_enabled = checked
        if checked:
            self._start_dubbing()
        else:
            self._stop_dubbing()

    def _start_dubbing(self) -> None:
        if self._selected_audio_source() == "document_editor":
            if not self._prepare_document_editor_source():
                return
        if not self._video_path:
            if self._url_is_opening():
                self.statusBar().showMessage(self._tr("status_url_opening_then_dub"))
                return
            self._dub_button.setChecked(False)
            QMessageBox.information(self, self._tr("app_title"), self._tr("msg_open_source_first"))
            return
        if self._document_mode and self._selected_audio_source() != "document_editor":
            self._set_combo_data(self._audio_source_combo, "transcript")
        elif is_supported_document_path(self._video_path):
            self._load_document(self._video_path, start_dubbing=False)
            if not self._document_mode:
                self._dub_button.setChecked(False)
                return
        if self._dub_worker is not None and self._dub_worker.isRunning():
            self.statusBar().showMessage(self._tr("status_dubbing_running"))
            return

        self._player.set_volume(self._volume_slider.value())
        self._set_dubbing_ready(False, self._tr("status_dubbing_buffering"))
        self._save_settings()
        dubbing_config = _safe_native_dubbing_config(self._config)
        if dubbing_config != self._config:
            self._config = dubbing_config
            save_app_config(self._config)
            self._set_combo_data(self._translation_device_combo, dubbing_config.local_translation_device)
            self._set_combo_data(self._whisper_device_combo, dubbing_config.whisper_device)
            self._set_combo_data(self._whisper_compute_combo, dubbing_config.whisper_compute_type)
            self._set_combo_data(self._vieneu_device_combo, dubbing_config.vieneu_tts_device)
            self._set_combo_data(self._vieneu_backend_combo, dubbing_config.vieneu_tts_backend)
            self.statusBar().showMessage(self._tr("status_safe_cpu_fallback"))
        if dubbing_config.audio_source in {"system", "microphone", "system_microphone"}:
            self._set_dubbing_ready(True, self._tr("status_live_capture"))
            self._play_active_source()
        self._dub_worker_generation += 1
        worker_generation = self._dub_worker_generation
        get_time_ms = self._document_time_ms if self._document_mode else self._player.get_time_ms
        is_playing = self._document_is_playing if self._document_mode else self._source_is_playing_for_dubbing
        self._dub_worker = DubbingWorker(
            self._video_path,
            get_time_ms,
            is_playing,
            dubbing_config,
            self,
        )
        self._dub_worker.status_changed.connect(self.statusBar().showMessage)
        self._dub_worker.segment_ready.connect(self._append_segment)
        self._dub_worker.audio_started.connect(self._sync_document_to_audio_start)
        self._dub_worker.playback_pause_requested.connect(self._pause_for_dubbing_buffer)
        self._dub_worker.playback_resume_requested.connect(self._resume_after_dubbing_buffer)
        self._dub_worker.failed.connect(self._dubbing_failed)
        self._dub_worker.finished.connect(
            lambda generation=worker_generation: self._dubbing_worker_finished(generation)
        )
        self._dub_worker.start()
        self.statusBar().showMessage(self._tr("status_dubbing_starting"))

    def _stop_dubbing(self) -> bool:
        self._cancel_delayed_video_playback()
        worker = self._dub_worker
        if worker:
            self._dub_worker_generation += 1
            worker.stop()
            if not worker.wait(5000):
                return False
            self._dub_worker = None
            worker.deleteLater()
        self._set_dubbing_ready(False if self._dub_button.isChecked() else True)
        if not self._dubbing_auto_enabled:
            self._dub_button.setChecked(False)
        return True

    def _dubbing_worker_finished(self, generation: int) -> None:
        if generation == self._dub_worker_generation:
            self._dub_worker = None
            self._set_dubbing_ready(False if self._dub_button.isChecked() else True)

    def _dubbing_failed(self, message: str) -> None:
        self._dubbing_auto_enabled = False
        self._stop_dubbing()
        self._dub_button.setChecked(False)
        self._set_dubbing_ready(True)
        QMessageBox.warning(self, self._tr("dubbing_unavailable_title"), _repair_mojibake(message))
        self.statusBar().showMessage(self._tr("status_dubbing_stopped"))

    def _set_live_subtitle(self, source_text: str, target_text: str = "") -> None:
        source_text = _repair_mojibake(str(source_text or "").strip())
        target_text = _repair_mojibake(str(target_text or "").strip())
        if not source_text and not target_text:
            return
        self._live_subtitle_source_text = source_text
        self._live_subtitle_target_text = target_text or source_text
        text_for_duration = self._live_subtitle_target_text or self._live_subtitle_source_text
        seconds = max(3.0, min(12.0, len(text_for_duration) / 16.0))
        self._live_subtitle_expires_at = time.monotonic() + seconds
        if self._selected_subtitle_mode() != "off":
            self._last_subtitle_text = ""
            self._update_subtitle_overlay()
