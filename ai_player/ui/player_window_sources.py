from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QFileDialog, QInputDialog, QMessageBox

from ai_player.services.document_reader import (
    create_text_document_transcript,
    document_filter,
    is_supported_document_path,
)
from ai_player.services.video_source import is_supported_video_url
from ai_player.ui.cache_progress_dialog import CacheProgressDialog
from ai_player.workers.player_window_workers import DocumentTranscriptWorker, VideoSourceWorker


class PlayerSourceMixin:
    def _open_video(self, *_args) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            self._tr("choose_video_title"),
            str(Path.home()),
            self._tr("video_file_filter"),
        )
        if not path:
            return
        if is_supported_document_path(path):
            self._load_document(path)
            return

        self._stop_dubbing()
        self._reset_document_state_for_video()
        self._video_path = path
        self._load_current_video_for_playback()
        self._media_stack.setCurrentWidget(self._video_widget)
        self._source_label.setText(path)
        self._save_settings()
        self.statusBar().showMessage(self._tr("status_opened_path").format(path=path))
        if self._dubbing_auto_enabled:
            self._dub_button.setChecked(True)
            self._start_dubbing()

    def _open_document(self, *_args) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            self._tr("choose_document_title"),
            str(Path.home()),
            document_filter(),
        )
        if not path:
            return
        self._load_document(path)

    def _load_document(self, path: str, start_dubbing: bool = True) -> None:
        if self._document_worker is not None and self._document_worker.isRunning():
            QMessageBox.information(self, self._tr("app_title"), self._tr("msg_document_opening"))
            return
        self._stop_dubbing()
        self._player.stop()
        self._document_editor_active = False
        self._document_view.setReadOnly(True)
        self._document_view.setPlainText(self._tr("status_open_document_loading"))
        self._media_stack.setCurrentWidget(self._document_view)
        self._source_label.setText(path)
        self._set_document_opening_controls(False)
        self.statusBar().showMessage(self._tr("status_open_document_loading"))
        self._document_worker = DocumentTranscriptWorker(path, start_dubbing, seconds_per_segment=6, parent=self)
        self._document_worker.ready.connect(self._document_transcript_ready)
        self._document_worker.failed.connect(self._document_transcript_failed)
        self._document_worker.finished.connect(self._document_worker_finished)
        self._document_worker.start()

    def _document_transcript_ready(self, transcript, start_dubbing: bool) -> None:
        self._apply_document_transcript(transcript, start_dubbing)

    def _apply_document_transcript(self, transcript, start_dubbing: bool = True) -> None:
        try:
            total_duration_ms = sum(page.duration_seconds for page in transcript.pages) * 1000
        except Exception as exc:
            QMessageBox.warning(self, self._tr("open_document_error_title"), str(exc))
            self.statusBar().showMessage(self._tr("status_open_document_failed"))
            return

        self._set_document_mode(True, total_duration_ms, transcript.pages)
        self._video_path = str(transcript.source_path)
        self._transcript_path_edit.setText(str(transcript.transcript_path))
        self._invalidate_subtitle_entries()
        self._set_combo_data(self._audio_source_combo, "transcript")
        self._clear_transcript()
        self._source_label.setText(str(transcript.source_path))
        self._save_settings()
        self.statusBar().showMessage(
            self._tr("status_opened_document").format(
                title=transcript.title,
                count=transcript.segment_count,
            )
        )
        if start_dubbing and self._dubbing_auto_enabled:
            self._dub_button.setChecked(True)
            self._start_dubbing()

    def _document_transcript_failed(self, message: str) -> None:
        QMessageBox.warning(self, self._tr("open_document_error_title"), message)
        self.statusBar().showMessage(self._tr("status_open_document_failed"))

    def _document_worker_finished(self) -> None:
        if self._document_worker is not None:
            self._document_worker.deleteLater()
            self._document_worker = None
        self._set_document_opening_controls(True)

    def _set_document_opening_controls(self, enabled: bool) -> None:
        if hasattr(self, "_open_file_button"):
            self._open_file_button.setEnabled(enabled)
        if hasattr(self, "_open_document_button"):
            self._open_document_button.setEnabled(enabled)

    def _open_video_url(self, *_args) -> None:
        url, ok = QInputDialog.getText(
            self,
            self._tr("open_video_url_title"),
            self._tr("open_video_url_label"),
        )
        url = url.strip()
        if not ok or not url:
            return
        if not is_supported_video_url(url):
            QMessageBox.warning(
                self,
                self._tr("app_title"),
                self._tr("msg_invalid_url"),
            )
            return
        if self._url_worker is not None and self._url_worker.isRunning():
            QMessageBox.information(self, self._tr("app_title"), self._tr("msg_url_opening"))
            return

        self.statusBar().showMessage(
            self._tr("status_open_url_cache")
            if self._config.video_url_full_cache
            else self._tr("status_open_url_stream")
        )
        self._stop_dubbing()
        self._reset_document_state_for_video()
        self._open_url_button.setEnabled(False)
        self._save_settings()
        if self._cache_dialog is not None:
            self._cache_dialog.close()
            self._cache_dialog = None
        quality_label = self._combo_text(self._playback_quality_combo)
        status_key = "status_open_url_quality" if self._config.video_url_full_cache else "status_open_url_stream_quality"
        self.statusBar().showMessage(self._tr(status_key).format(quality=quality_label))
        self._url_worker = VideoSourceWorker(
            url,
            self._config.playback_video_quality,
            self._config.video_url_full_cache,
            self,
        )
        self._url_worker.progress_changed.connect(self._video_cache_progress_changed)
        self._url_worker.resolved.connect(self._video_url_resolved)
        self._url_worker.failed.connect(self._video_url_failed)
        self._url_worker.finished.connect(self._video_url_finished)
        self._url_worker.start()

    def _video_cache_progress_changed(self, data) -> None:
        if self._cache_dialog is None:
            self._cache_dialog = CacheProgressDialog(self._ui_language(), self)
            self._cache_dialog.show()
            self._cache_dialog.raise_()
        if isinstance(data, dict):
            self._cache_dialog.update_cache(data)
            status = str(data.get("status") or "")
            if status in {"downloading", "starting"}:
                provider = data.get("provider") or ""
                quality = data.get("quality") or ""
                self.statusBar().showMessage(f"{self._tr('cache_status_downloading')} {provider} {quality}".strip())

    def _video_url_resolved(self, source) -> None:
        if self._cache_dialog is not None:
            self._cache_dialog.accept()
            self._cache_dialog = None
        self._reset_document_state_for_video()
        self._video_path = source.playback_url
        self._load_current_video_for_playback()
        self._media_stack.setCurrentWidget(self._video_widget)
        label = source.title if source.is_resolved else source.input_url
        self._source_label.setText(label)
        provider = f" ({source.provider})" if source.is_resolved else ""
        self.statusBar().showMessage(self._tr("status_opened_url").format(provider=provider, label=label))
        self._save_settings()
        if self._dubbing_auto_enabled:
            self._dub_button.setChecked(True)
            self._start_dubbing()

    def _reset_document_state_for_video(self) -> None:
        self._set_document_mode(False)
        self._document_editor_active = False
        self._document_view.setReadOnly(True)
        self._document_pages = []
        self._document_current_page_index = -1
        self._document_elapsed_ms = 0
        self._document_started_at = None
        self._document_audio_sync_active = False
        if self._selected_audio_source() in {"transcript", "document_editor"}:
            self._set_combo_data(self._audio_source_combo, "original")
        self._transcript_path_edit.clear()
        self._clear_transcript()
        self._invalidate_subtitle_entries()

    def _video_url_failed(self, message: str) -> None:
        if self._cache_dialog is not None:
            self._cache_dialog.mark_failed(message)
        QMessageBox.warning(self, self._tr("open_url_error_title"), message)
        self.statusBar().showMessage(self._tr("status_open_url_failed"))

    def _video_url_finished(self) -> None:
        if self._url_worker is not None:
            self._url_worker.deleteLater()
            self._url_worker = None
        self._open_url_button.setEnabled(True)

    def _save_transcript(self) -> None:
        text = self._transcript_text(self._selected_transcript_view(), self._selected_transcript_type())
        if not text:
            QMessageBox.information(self, self._tr("app_title"), self._tr("msg_no_transcript_save"))
            return

        path, _ = QFileDialog.getSaveFileName(
            self,
            self._tr("save_transcript_title"),
            str(Path.home() / "ai-player-transcript.txt"),
            self._tr("text_file_filter"),
        )
        if not path:
            return

        output = Path(path)
        if output.suffix.lower() != ".txt":
            output = output.with_suffix(".txt")
        output.write_text(text.rstrip() + "\n", encoding="utf-8")
        self.statusBar().showMessage(self._tr("status_saved_transcript").format(path=output))

    def _choose_transcript_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            self._tr("choose_transcript_title"),
            str(Path.home()),
            self._tr("transcript_file_filter"),
        )
        if not path:
            return
        self._transcript_path_edit.setText(path)
        self._invalidate_subtitle_entries()
        self._queue_save_settings()
        self.statusBar().showMessage(self._tr("status_selected_transcript").format(path=path))

    def _audio_source_changed(self, *_args) -> None:
        self._sync_audio_source_controls()
        if self._selected_audio_source() == "document_editor":
            self._enter_document_editor_source()
        self._queue_save_settings()
        if self._dub_button.isChecked() and self._dub_worker is not None:
            self._stop_dubbing()
            self._dub_button.setChecked(True)
            self._start_dubbing()

    def _sync_audio_source_controls(self) -> None:
        is_transcript = self._selected_audio_source() == "transcript"
        self._transcript_path_edit.setEnabled(is_transcript)
        self._transcript_file_button.setEnabled(is_transcript)

    def _enter_document_editor_source(self) -> None:
        if self._document_editor_active:
            return
        self._stop_dubbing()
        self._player.stop()
        self._set_document_mode(False)
        self._document_editor_active = True
        self._document_pages = []
        self._document_current_page_index = -1
        self._video_path = None
        self._transcript_path_edit.clear()
        self._invalidate_subtitle_entries()
        self._media_stack.setCurrentWidget(self._document_view)
        self._document_view.setReadOnly(False)
        self._document_view.clear()
        self._document_view.setPlaceholderText(self._tr("document_editor_placeholder"))
        self._source_label.setText(self._tr("document_editor"))
        self._time_label.setText("00:00 / 00:00")
        self._position_slider.setValue(0)
        self.statusBar().showMessage(self._tr("status_document_editor_hint"))

    def _prepare_document_editor_source(self) -> bool:
        text = self._document_view.toPlainText().strip()
        try:
            transcript = create_text_document_transcript(
                text,
                seconds_per_segment=max(2, int(self._config.segment_seconds)),
            )
        except Exception as exc:
            self._dub_button.setChecked(False)
            QMessageBox.information(self, self._tr("app_title"), str(exc))
            return False

        self._stop_dubbing()
        self._player.stop()
        self._document_editor_active = False
        self._document_view.setReadOnly(True)
        total_duration_ms = sum(page.duration_seconds for page in transcript.pages) * 1000
        self._set_document_mode(True, total_duration_ms, transcript.pages)
        self._video_path = str(transcript.transcript_path)
        self._transcript_path_edit.setText(str(transcript.transcript_path))
        self._invalidate_subtitle_entries()
        self._clear_transcript()
        self._source_label.setText(transcript.title)
        self.statusBar().showMessage(self._tr("status_document_editor_created").format(count=transcript.segment_count))
        return True

    def _subtitle_mode_changed(self, *_args) -> None:
        if self._selected_subtitle_mode() != "off":
            self._load_subtitle_entries_for_overlay()
            self._update_subtitle_overlay()
        else:
            self._last_subtitle_text = ""
            self._subtitle_overlay.hide()

    def _selected_subtitle_mode(self) -> str:
        if hasattr(self, "_subtitle_mode_combo"):
            value = self._subtitle_mode_combo.currentData()
            if value in {"off", "source", "target"}:
                return str(value)
        return "off"

    def _subtitle_size_changed(self, *_args) -> None:
        self._apply_subtitle_overlay_style()
        self._position_subtitle_overlay()

    def _invalidate_subtitle_entries(self, *_args) -> None:
        self._subtitle_entries = []
        self._subtitle_entries_path = ""
        self._last_subtitle_text = ""
        self._live_subtitle_source_text = ""
        self._live_subtitle_target_text = ""
        self._live_subtitle_expires_at = 0.0
        if hasattr(self, "_subtitle_overlay"):
            self._subtitle_overlay.hide()

    def _video_aspect_changed(self, *_args) -> None:
        self._apply_media_aspect_ratio()
        if self._document_mode and self._document_pages:
            self._update_document_page(force=True)
        self._queue_save_settings()

    def _playback_quality_changed(self, *_args) -> None:
        self._queue_save_settings()
        if self._video_path and not self._document_mode:
            self.statusBar().showMessage(self._tr("status_playback_quality_next_url"))

    def _url_is_opening(self) -> bool:
        return self._url_worker is not None and self._url_worker.isRunning()
