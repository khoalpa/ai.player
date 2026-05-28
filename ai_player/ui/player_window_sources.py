from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from ai_player.services.document_reader import (
    create_text_document_transcript,
    document_filter,
    is_supported_document_path,
)
from ai_player.services.telegram_channel import (
    TelegramChannelError,
    TelegramLoginConfig,
    delete_telegram_login_data,
    is_telegram_channel_url,
    load_telegram_login_config,
    validate_telegram_login_config,
)
from ai_player.services.video_source import is_supported_video_url
from ai_player.ui.cache_progress_dialog import CacheProgressDialog
from ai_player.ui.player_window_utils import repair_mojibake as _repair_mojibake
from ai_player.workers.player_window_workers import DocumentTranscriptWorker, TelegramChannelWorker


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
        self._document_worker = DocumentTranscriptWorker(
            path,
            start_dubbing,
            seconds_per_segment=6,
            language_id=self._config.gui_language,
            parent=self,
        )
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
        if self._url_is_opening():
            QMessageBox.information(self, self._tr("app_title"), self._tr("msg_url_opening"))
            return

        if is_telegram_channel_url(url):
            self._start_telegram_channel_flow(url)
            return

        self._open_resolved_video_url(url)

    def _open_resolved_video_url(self, url: str) -> None:
        forced_full_cache = self._source_filter_forces_video_url_full_cache()
        full_cache = self._effective_video_url_full_cache()
        self.statusBar().showMessage(
            self._tr("status_open_url_source_filter_cache")
            if forced_full_cache
            else self._tr("status_open_url_cache")
            if full_cache
            else self._tr("status_open_url_stream")
        )
        self._stop_dubbing()
        self._reset_document_state_for_video()
        self._save_settings()
        if self._cache_dialog is not None:
            self._cache_dialog.close()
            self._cache_dialog = None
        quality_label = self._combo_text(self._playback_quality_combo)
        if forced_full_cache:
            status_key = "status_open_url_source_filter_quality"
        elif full_cache:
            status_key = "status_open_url_quality"
        else:
            status_key = "status_open_url_stream_quality"
        self.statusBar().showMessage(self._tr(status_key).format(quality=quality_label))
        self._video_url.start(
            url,
            self._config.playback_video_quality,
            full_cache=full_cache,
            language_id=self._config.gui_language,
        )

    def _start_telegram_channel_flow(self, url: str) -> None:
        if self._telegram_is_busy():
            QMessageBox.information(self, self._tr("app_title"), self._tr("msg_url_opening"))
            return
        self._pending_telegram_url = url
        self._start_telegram_worker("list_public", url=url, status_key="status_telegram_channel_loading")

    def _start_telegram_worker(
        self,
        operation: str,
        *,
        url: str = "",
        config: TelegramLoginConfig | None = None,
        login_request=None,
        code: str = "",
        password: str = "",
        post_id: str = "",
        status_key: str = "",
        status_text: str = "",
    ) -> None:
        self._set_telegram_opening_controls(False)
        if status_text:
            self.statusBar().showMessage(status_text)
        elif status_key:
            self.statusBar().showMessage(self._tr(status_key))
        worker = TelegramChannelWorker(
            operation,
            url=url,
            config=config,
            login_request=login_request,
            code=code,
            password=password,
            post_id=post_id,
            language_id=self._config.gui_language,
            parent=self,
        )
        self._telegram_worker = worker
        worker.videos_ready.connect(self._telegram_videos_ready)
        worker.login_request_ready.connect(self._telegram_login_request_ready)
        worker.login_ready.connect(self._telegram_login_ready)
        worker.password_required.connect(self._telegram_password_required)
        worker.video_ready.connect(self._telegram_video_ready)
        worker.failed.connect(lambda message, op=operation: self._telegram_worker_failed(op, message))
        worker.finished.connect(lambda worker=worker: self._telegram_worker_finished(worker))
        worker.start()

    def _telegram_videos_ready(self, videos) -> None:
        selected = _TelegramVideoChoiceDialog.choose(videos, self._ui_language(), self)
        if selected is None:
            self.statusBar().showMessage(self._tr("status_telegram_channel_cancelled"))
            return
        self.statusBar().showMessage(self._tr("status_telegram_channel_selected").format(label=selected.title))
        if selected.authenticated:
            config = load_telegram_login_config()
            if config is None:
                config = self._telegram_login_config_dialog()
            if config is None:
                self.statusBar().showMessage(self._tr("status_telegram_login_cancelled"))
                return
            self._start_telegram_worker(
                "download",
                url=self._pending_telegram_url,
                config=config,
                post_id=selected.post_id,
                status_text=self._tr("status_telegram_video_downloading").format(label=selected.title),
            )
            return
        self._open_resolved_video_url(selected.url)

    def _telegram_video_ready(self, path: str) -> None:
        self._open_local_video_path(path)

    def _open_local_video_path(self, path: str) -> None:
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

    def _telegram_worker_failed(self, operation: str, message: str) -> None:
        detail = _repair_mojibake(message)
        if operation == "list_public" and self._confirm_telegram_login(detail):
            config = self._telegram_login_config_dialog()
            if config is None:
                self.statusBar().showMessage(self._tr("status_telegram_login_cancelled"))
                return
            self._start_telegram_worker("start_login", config=config, status_key="status_telegram_login_starting")
            return
        QMessageBox.warning(self, self._tr("open_url_error_title"), detail)
        self.statusBar().showMessage(self._tr("status_open_url_failed"))

    def _telegram_login_request_ready(self, request) -> None:
        code, ok = QInputDialog.getText(
            self,
            self._tr("telegram_login_code_title"),
            self._tr("telegram_login_code_label"),
        )
        if not ok:
            self.statusBar().showMessage(self._tr("status_telegram_login_cancelled"))
            return
        self._start_telegram_worker(
            "complete_login",
            login_request=request,
            code=code,
            status_key="status_telegram_login_completing",
        )

    def _telegram_password_required(self, request, code: str) -> None:
        password, ok = QInputDialog.getText(
            self,
            self._tr("telegram_login_password_title"),
            self._tr("telegram_login_password_label"),
            QLineEdit.EchoMode.Password,
        )
        if not ok:
            self.statusBar().showMessage(self._tr("status_telegram_login_cancelled"))
            return
        self._start_telegram_worker(
            "complete_login",
            login_request=request,
            code=code,
            password=password,
            status_key="status_telegram_login_completing",
        )

    def _telegram_login_ready(self, config: TelegramLoginConfig) -> None:
        self.statusBar().showMessage(self._tr("status_telegram_login_ready"))
        self._start_telegram_worker(
            "list_authenticated",
            url=self._pending_telegram_url,
            config=config,
            status_key="status_telegram_channel_loading_auth",
        )

    def _telegram_worker_finished(self, worker) -> None:
        worker.deleteLater()
        if self._telegram_worker is worker:
            self._telegram_worker = None
            if not self._url_is_opening():
                self._set_telegram_opening_controls(True)

    def _telegram_is_busy(self) -> bool:
        worker = getattr(self, "_telegram_worker", None)
        return worker is not None and worker.isRunning()

    def _set_telegram_opening_controls(self, enabled: bool) -> None:
        if hasattr(self, "_open_url_button"):
            self._open_url_button.setEnabled(enabled)

    def _confirm_telegram_login(self, public_error: str) -> bool:
        message = f"{_repair_mojibake(public_error)}\n\n{self._tr('telegram_login_prompt')}"
        return (
            QMessageBox.question(
                self,
                self._tr("telegram_login_title"),
                message,
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes,
            )
            == QMessageBox.Yes
        )

    def _telegram_login_config_dialog(self) -> TelegramLoginConfig | None:
        dialog = _TelegramLoginDialog(self._ui_language(), self)
        if dialog.exec() != QDialog.Accepted:
            return None
        try:
            return validate_telegram_login_config(
                dialog.api_id,
                dialog.api_hash,
                dialog.phone,
                self._config.gui_language,
            )
        except TelegramChannelError as exc:
            QMessageBox.warning(self, self._tr("telegram_login_title"), _repair_mojibake(str(exc)))
            return None

    def _effective_video_url_full_cache(self) -> bool:
        if self._selected_video_url_full_cache():
            return True
        return hasattr(self, "_source_filter_check") and self._source_filter_check.isChecked()

    def _source_filter_forces_video_url_full_cache(self) -> bool:
        return (
            not self._selected_video_url_full_cache()
            and hasattr(self, "_source_filter_check")
            and self._source_filter_check.isChecked()
        )

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
        detail = _repair_mojibake(message)
        if self._cache_dialog is not None:
            self._cache_dialog.mark_failed(detail)
        QMessageBox.warning(self, self._tr("open_url_error_title"), detail)
        self.statusBar().showMessage(self._tr("status_open_url_failed"))

    def _video_url_finished(self) -> None:
        self._video_url.finished()

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
        self._live_subtitle_entries = []
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
        return self._video_url.is_opening()

    def _stop_video_url(self, wait_ms: int = 5000) -> bool:
        return self._video_url.stop(wait_ms=wait_ms)


class _TelegramVideoChoiceDialog(QDialog):
    def __init__(self, videos, language_id: str | None = None, parent=None) -> None:
        super().__init__(parent)
        self._videos = list(videos)
        self._language_id = language_id
        self._list = QListWidget(self)
        self.setWindowTitle(self._tr("telegram_channel_choose_title"))
        self.resize(620, 420)

        label = QLabel(self._tr("telegram_channel_choose_label"), self)
        label.setWordWrap(True)
        for index, video in enumerate(self._videos):
            item = QListWidgetItem(f"{index + 1}. {video.title}")
            item.setData(Qt.ItemDataRole.UserRole, index)
            self._list.addItem(item)
        if self._videos:
            self._list.setCurrentRow(0)
        self._list.itemDoubleClicked.connect(lambda _item: self.accept())

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(label)
        layout.addWidget(self._list, 1)
        layout.addWidget(buttons)

    @classmethod
    def choose(cls, videos, language_id: str | None = None, parent=None):
        dialog = cls(videos, language_id, parent)
        if dialog.exec() != QDialog.Accepted:
            return None
        item = dialog._list.currentItem()
        if item is None:
            return None
        index = item.data(Qt.ItemDataRole.UserRole)
        try:
            return dialog._videos[int(index)]
        except (TypeError, ValueError, IndexError):
            return None

    def _tr(self, key: str, **kwargs: object) -> str:
        from ai_player.core.i18n import ui_text

        return ui_text(key, self._language_id, **kwargs)


class _TelegramLoginDialog(QDialog):
    def __init__(self, language_id: str | None = None, parent=None) -> None:
        super().__init__(parent)
        self._language_id = language_id
        self.setWindowTitle(self._tr("telegram_login_title"))

        cached = load_telegram_login_config()
        self._api_id_edit = QLineEdit(str(cached.api_id) if cached else "", self)
        self._api_hash_edit = QLineEdit(cached.api_hash if cached else "", self)
        self._phone_edit = QLineEdit(cached.phone if cached else "", self)

        form = QFormLayout()
        form.addRow(self._tr("telegram_login_api_id"), self._api_id_edit)
        form.addRow(self._tr("telegram_login_api_hash"), self._api_hash_edit)
        form.addRow(self._tr("telegram_login_phone"), self._phone_edit)

        warning = QLabel(self._tr("telegram_login_storage_warning"), self)
        warning.setWordWrap(True)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        self._forget_button = QPushButton(self._tr("telegram_login_forget"), self)
        self._forget_button.setEnabled(cached is not None)
        buttons.addButton(self._forget_button, QDialogButtonBox.ActionRole)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        self._forget_button.clicked.connect(self._forget_saved_login)

        layout = QVBoxLayout(self)
        layout.addWidget(warning)
        layout.addLayout(form)
        layout.addWidget(buttons)

    @property
    def api_id(self) -> str:
        return self._api_id_edit.text()

    @property
    def api_hash(self) -> str:
        return self._api_hash_edit.text()

    @property
    def phone(self) -> str:
        return self._phone_edit.text()

    def _forget_saved_login(self) -> None:
        if (
            QMessageBox.question(
                self,
                self._tr("telegram_login_forget_title"),
                self._tr("telegram_login_forget_confirm"),
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            != QMessageBox.Yes
        ):
            return
        delete_telegram_login_data()
        self._api_id_edit.clear()
        self._api_hash_edit.clear()
        self._phone_edit.clear()
        self._forget_button.setEnabled(False)

    def _tr(self, key: str, **kwargs: object) -> str:
        from ai_player.core.i18n import ui_text

        return ui_text(key, self._language_id, **kwargs)
