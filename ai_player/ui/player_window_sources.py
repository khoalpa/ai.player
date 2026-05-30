from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

from PySide6.QtCore import QSize, Qt, QUrl
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest
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
    telegram_private_available,
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

        self._clear_active_telegram_channel_video()
        self._stop_dubbing()
        self._reset_document_state_for_video()
        self._video_path = path
        self._auto_select_video_aspect_ratio()
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
        self._clear_active_telegram_channel_video()
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
        if not is_telegram_channel_url(url):
            self._clear_active_telegram_channel_video()
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
        self._pending_telegram_post_id = self._telegram_post_id_from_url(url)
        self._show_telegram_channel_browser(url, self._tr("telegram_channel_browser_loading"))
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
        before_post_id: str = "",
        search: str = "",
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
            before_post_id=before_post_id,
            search=search,
            language_id=self._config.gui_language,
            parent=self,
        )
        self._telegram_worker = worker
        worker.videos_ready.connect(lambda videos, op=operation: self._telegram_items_ready(videos, op))
        worker.login_request_ready.connect(self._telegram_login_request_ready)
        worker.login_ready.connect(self._telegram_login_ready)
        worker.password_required.connect(self._telegram_password_required)
        worker.video_ready.connect(self._telegram_video_ready)
        worker.failed.connect(lambda message, op=operation: self._telegram_worker_failed(op, message))
        worker.finished.connect(lambda worker=worker: self._telegram_worker_finished(worker))
        worker.start()

    def _telegram_items_ready(self, items, operation: str = "") -> None:
        items = list(items)
        if operation.endswith("_more"):
            self._append_telegram_channel_items(items)
        else:
            self._set_telegram_channel_items(items)
        if operation in {"list_authenticated", "list_authenticated_more"}:
            self._telegram_channel_authenticated = True
            self.statusBar().showMessage(self._tr("status_telegram_login_ready"))
        else:
            self._telegram_channel_authenticated = False
            self.statusBar().showMessage(
                self._tr("telegram_channel_browser_ready").format(count=len(self._telegram_channel_all_items))
            )
        pending_direction = int(getattr(self, "_pending_telegram_navigation_direction", 0) or 0)
        if pending_direction and operation.endswith("_more"):
            self._pending_telegram_navigation_direction = 0
            self._open_adjacent_telegram_channel_video(pending_direction, allow_load_more=False)

    def _telegram_videos_ready(self, videos) -> None:
        self._telegram_items_ready(videos)

    def _show_telegram_channel_browser(self, url: str, status: str = "") -> None:
        self._clear_active_telegram_channel_video()
        self._stop_dubbing()
        self._player.stop()
        self._reset_document_state_for_video()
        self._video_path = None
        self._runtime_media_path = ""
        self._telegram_channel_items = []
        self._telegram_channel_all_items = []
        self._telegram_channel_authenticated = False
        self._telegram_channel_list.clear()
        self._telegram_channel_preview.clear()
        self._clear_telegram_channel_thumbnail()
        self._telegram_channel_title.setText(self._tr("telegram_channel_browser_title").format(url=url))
        self._telegram_channel_status.setText(status)
        self._telegram_channel_open_button.setEnabled(False)
        self._telegram_channel_login_button.setEnabled(telegram_private_available())
        self._telegram_channel_refresh_button.setEnabled(True)
        self._telegram_channel_load_more_button.setEnabled(True)
        self._media_stack.setCurrentWidget(self._telegram_channel_view)
        self._source_label.setText(url)
        self._sync_telegram_browser_button()
        self._apply_media_aspect_ratio()

    def _return_to_telegram_channel_browser(self) -> None:
        url = str(getattr(self, "_pending_telegram_url", "") or "")
        if not url:
            return
        self._telegram_browser_return_available = False
        self._stop_dubbing()
        self._player.stop()
        self._reset_document_state_for_video()
        self._video_path = None
        self._runtime_media_path = ""
        self._telegram_channel_title.setText(self._tr("telegram_channel_browser_title").format(url=url))
        self._telegram_channel_status.setText(
            self._tr("telegram_channel_browser_ready").format(count=len(self._telegram_channel_all_items))
        )
        current = self._current_telegram_channel_item_for_navigation()
        if current is not None:
            self._select_telegram_channel_item(current)
        self._media_stack.setCurrentWidget(self._telegram_channel_view)
        self._source_label.setText(url)
        self._sync_telegram_browser_button()
        self._apply_media_aspect_ratio()

    def _sync_telegram_browser_button(self) -> None:
        button = getattr(self, "_telegram_browser_button", None)
        if button is None:
            return
        visible = (
            bool(getattr(self, "_telegram_browser_return_available", False))
            and getattr(self, "_media_stack", None) is not None
            and self._media_stack.currentWidget() is getattr(self, "_video_widget", None)
        )
        button.setVisible(visible)
        button.setEnabled(visible and bool(getattr(self, "_telegram_channel_all_items", [])))

    def _populate_telegram_channel_browser(self, items) -> None:
        self._telegram_channel_items = list(items)
        self._telegram_channel_list.clear()
        for index, channel_item in enumerate(self._telegram_channel_items):
            label = self._telegram_channel_item_label(channel_item)
            item = QListWidgetItem(label)
            item.setToolTip(label)
            item.setSizeHint(QSize(0, self._telegram_channel_item_height(label)))
            item.setData(Qt.ItemDataRole.UserRole, index)
            self._set_telegram_item_thumbnail(item, channel_item, index)
            self._telegram_channel_list.addItem(item)
        if self._telegram_channel_items:
            target_row = self._telegram_target_row()
            self._telegram_channel_list.setCurrentRow(target_row if target_row >= 0 else 0)
        self._telegram_channel_status.setText(
            self._tr("telegram_channel_browser_ready").format(count=len(self._telegram_channel_all_items))
        )
        self._telegram_channel_login_button.setEnabled(telegram_private_available())

    def _telegram_channel_item_label(self, channel_item) -> str:
        return "\n".join(self._telegram_channel_item_lines(channel_item))

    def _telegram_channel_item_lines(self, channel_item) -> list[str]:
        kind_label = self._telegram_media_kind_label(channel_item)
        post_id = str(getattr(channel_item, "post_id", "") or "").strip()
        heading_parts = [kind_label]
        if post_id:
            heading_parts.append(self._tr("telegram_channel_item_post_id").format(post_id=post_id))
        lines = [" ".join(heading_parts)]

        text = str(getattr(channel_item, "text", "") or "").strip()
        title = str(getattr(channel_item, "title", "") or "").strip()
        if text:
            lines.append(text)
        elif title:
            lines.append(title)

        date = str(getattr(channel_item, "date", "") or "").strip()
        if date:
            lines.append(self._tr("telegram_channel_item_date").format(date=date))
        duration = str(getattr(channel_item, "duration", "") or "").strip()
        if duration:
            lines.append(self._tr("telegram_channel_item_duration").format(duration=duration))
        file_name = str(getattr(channel_item, "file_name", "") or "").strip()
        if file_name:
            lines.append(self._tr("telegram_channel_item_file_name").format(name=file_name))
        file_size = int(getattr(channel_item, "file_size", 0) or 0)
        if file_size:
            lines.append(self._tr("telegram_channel_item_file_size").format(size=self._format_bytes(file_size)))
        media_count = int(getattr(channel_item, "media_count", 0) or 0)
        if media_count > 1:
            lines.append(self._tr("telegram_channel_item_media_count").format(count=media_count))
        url = str(getattr(channel_item, "url", "") or "").strip()
        if url:
            lines.append(self._tr("telegram_channel_item_link").format(url=url))
        media_url = str(getattr(channel_item, "media_url", "") or "").strip()
        if media_url:
            lines.append(self._tr("telegram_channel_item_media_url").format(url=media_url))
        return lines

    @staticmethod
    def _telegram_channel_item_height(label: str) -> int:
        text = str(label or "")
        chars_per_line = 96
        line_count = 0
        for line in text.splitlines() or [""]:
            line_count += max(1, (len(line) + chars_per_line - 1) // chars_per_line)
        text_height = line_count * 18
        return max(104, text_height + 14)

    def _set_telegram_channel_items(self, items) -> None:
        self._telegram_channel_all_items = list(items)
        self._filter_telegram_channel_items()

    def _append_telegram_channel_items(self, items) -> None:
        existing = {str(getattr(item, "url", "") or "") for item in getattr(self, "_telegram_channel_all_items", [])}
        added = []
        for item in items:
            url = str(getattr(item, "url", "") or "")
            if url and url in existing:
                continue
            existing.add(url)
            added.append(item)
        self._telegram_channel_all_items = [*getattr(self, "_telegram_channel_all_items", []), *added]
        self._filter_telegram_channel_items()

    def _filter_telegram_channel_items(self, *_args) -> None:
        all_items = list(getattr(self, "_telegram_channel_all_items", []))
        media_filter = "all"
        if hasattr(self, "_telegram_channel_filter_combo"):
            media_filter = str(self._telegram_channel_filter_combo.currentData() or "all")
        query = ""
        if hasattr(self, "_telegram_channel_search"):
            query = " ".join(self._telegram_channel_search.text().lower().split())
        filtered = []
        for item in all_items:
            media_kind = self._telegram_media_kind(item)
            if media_filter != "all" and media_kind != media_filter:
                continue
            if query and query not in self._telegram_item_search_text(item):
                continue
            filtered.append(item)
        self._populate_telegram_channel_browser(filtered)

    def _telegram_item_search_text(self, channel_item) -> str:
        return " ".join(
            str(value or "")
            for value in (
                getattr(channel_item, "title", ""),
                getattr(channel_item, "text", ""),
                getattr(channel_item, "file_name", ""),
                getattr(channel_item, "duration", ""),
                getattr(channel_item, "url", ""),
                getattr(channel_item, "media_url", ""),
                self._telegram_media_kind(channel_item),
                getattr(channel_item, "post_id", ""),
                getattr(channel_item, "date", ""),
            )
        ).lower()

    def _telegram_target_row(self) -> int:
        target_post_id = str(getattr(self, "_pending_telegram_post_id", "") or "")
        if not target_post_id:
            return -1
        for index, item in enumerate(getattr(self, "_telegram_channel_items", [])):
            if str(getattr(item, "post_id", "") or "") == target_post_id:
                return index
        return -1

    @staticmethod
    def _telegram_post_id_from_url(url: str) -> str:
        parts = [part for part in urlparse(str(url or "").strip()).path.strip("/").split("/") if part]
        if len(parts) == 2 and parts[1].isdigit():
            return parts[1]
        return ""

    def _telegram_channel_selection_changed(self, current, _previous=None) -> None:
        channel_item = self._telegram_channel_item_from_list_item(current)
        if channel_item is None:
            self._telegram_channel_preview.clear()
            self._clear_telegram_channel_thumbnail()
            self._telegram_channel_open_button.setEnabled(False)
            return
        lines = self._telegram_channel_item_lines(channel_item)
        self._telegram_channel_preview.setPlainText("\n".join(lines))
        self._show_telegram_channel_thumbnail(channel_item)
        self._telegram_channel_open_button.setEnabled(bool(getattr(channel_item, "has_video", True)))

    def _set_telegram_item_thumbnail(self, item: QListWidgetItem, channel_item, index: int) -> None:
        thumbnail = str(getattr(channel_item, "thumbnail_url", "") or "").strip()
        if not thumbnail:
            return
        pixmap = self._telegram_thumbnail_pixmap(thumbnail)
        if not pixmap.isNull():
            item.setIcon(QIcon(pixmap))
            return
        self._request_telegram_thumbnail(thumbnail, index=index)

    def _show_telegram_channel_thumbnail(self, channel_item) -> None:
        thumbnail = str(getattr(channel_item, "thumbnail_url", "") or "").strip()
        if not thumbnail:
            self._clear_telegram_channel_thumbnail()
            return
        pixmap = self._telegram_thumbnail_pixmap(thumbnail)
        if not pixmap.isNull():
            self._set_telegram_channel_thumbnail_pixmap(pixmap)
            return
        self._clear_telegram_channel_thumbnail()
        self._request_telegram_thumbnail(thumbnail, index=-1)

    def _clear_telegram_channel_thumbnail(self) -> None:
        self._telegram_channel_thumbnail_source = QPixmap()
        self._telegram_channel_thumbnail.clear()
        self._telegram_channel_thumbnail.hide()

    def _set_telegram_channel_thumbnail_pixmap(self, pixmap: QPixmap) -> None:
        if pixmap.isNull():
            self._clear_telegram_channel_thumbnail()
            return
        self._telegram_channel_thumbnail_source = pixmap
        self._refresh_telegram_channel_thumbnail()
        self._telegram_channel_thumbnail.hide()

    def _refresh_telegram_channel_thumbnail(self) -> None:
        pixmap = getattr(self, "_telegram_channel_thumbnail_source", QPixmap())
        if pixmap.isNull():
            return
        size = self._telegram_channel_thumbnail.size()
        self._telegram_channel_thumbnail.setPixmap(
            pixmap.scaled(size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        )

    def _telegram_thumbnail_pixmap(self, thumbnail: str) -> QPixmap:
        path = Path(thumbnail)
        if path.exists() and path.is_file():
            return QPixmap(str(path))
        return QPixmap()

    def _request_telegram_thumbnail(self, thumbnail: str, *, index: int) -> None:
        if not thumbnail.lower().startswith(("http://", "https://")):
            return
        manager = self._telegram_thumbnail_network()
        request = QNetworkRequest(QUrl(thumbnail))
        reply = manager.get(request)
        reply.setProperty("telegram_thumbnail_index", index)
        reply.setProperty("telegram_thumbnail_url", thumbnail)
        reply.finished.connect(lambda reply=reply: self._telegram_thumbnail_loaded(reply))

    def _telegram_thumbnail_network(self) -> QNetworkAccessManager:
        manager = getattr(self, "_telegram_thumbnail_manager", None)
        if manager is None:
            manager = QNetworkAccessManager(self)
            self._telegram_thumbnail_manager = manager
        return manager

    def _telegram_thumbnail_loaded(self, reply) -> None:
        try:
            index = int(reply.property("telegram_thumbnail_index"))
            thumbnail = str(reply.property("telegram_thumbnail_url") or "")
            pixmap = QPixmap()
            pixmap.loadFromData(bytes(reply.readAll()))
            if pixmap.isNull():
                return
            if index >= 0:
                item = self._telegram_channel_list.item(index)
                if item is not None:
                    item.setIcon(QIcon(pixmap))
                return
            current = self._telegram_channel_item_from_list_item(self._telegram_channel_list.currentItem())
            if current is not None and str(getattr(current, "thumbnail_url", "") or "").strip() == thumbnail:
                self._set_telegram_channel_thumbnail_pixmap(pixmap)
        finally:
            reply.deleteLater()

    def _telegram_channel_item_activated(self, item) -> None:
        channel_item = self._telegram_channel_item_from_list_item(item)
        if channel_item is None:
            return
        if getattr(channel_item, "has_video", True):
            self._open_telegram_channel_item(channel_item)
        else:
            self.statusBar().showMessage(self._tr("telegram_channel_text_only"))

    def _telegram_media_kind(self, channel_item) -> str:
        media_kind = str(getattr(channel_item, "media_kind", "") or "").strip().lower()
        if media_kind:
            return media_kind
        return "video" if getattr(channel_item, "has_video", True) else "text"

    def _telegram_media_kind_label(self, channel_item) -> str:
        key = {
            "video": "telegram_channel_item_video",
            "photo": "telegram_channel_item_photo",
            "document": "telegram_channel_item_document",
            "audio": "telegram_channel_item_audio",
            "text": "telegram_channel_item_post",
        }.get(self._telegram_media_kind(channel_item), "telegram_channel_item_post")
        return self._tr(key)

    def _open_selected_telegram_channel_item(self) -> None:
        channel_item = self._telegram_channel_item_from_list_item(self._telegram_channel_list.currentItem())
        if channel_item is None:
            self.statusBar().showMessage(self._tr("telegram_channel_no_selection"))
            return
        if not getattr(channel_item, "has_video", True):
            self.statusBar().showMessage(self._tr("telegram_channel_text_only"))
            return
        self._open_telegram_channel_item(channel_item)

    def _open_telegram_channel_item(self, channel_item) -> None:
        self._set_active_telegram_channel_video(channel_item)
        self._telegram_browser_return_available = True
        self.statusBar().showMessage(self._tr("status_telegram_channel_selected").format(label=channel_item.title))
        if getattr(channel_item, "authenticated", False):
            self._download_telegram_channel_item(channel_item, prompt_for_config=True)
            return
        if self._download_telegram_channel_item(channel_item):
            return
        media_url = str(getattr(channel_item, "media_url", "") or "").strip()
        if media_url:
            self._open_resolved_video_url(media_url)
            return
        self._open_resolved_video_url(channel_item.url)

    def _download_telegram_channel_item(self, channel_item, *, prompt_for_config: bool = False) -> bool:
        config = load_telegram_login_config() if telegram_private_available() else None
        if config is None and prompt_for_config and telegram_private_available():
            config = self._telegram_login_config_dialog()
        if config is None:
            if prompt_for_config:
                self.statusBar().showMessage(self._tr("status_telegram_login_cancelled"))
            return False
        self._start_telegram_worker(
            "download",
            url=self._pending_telegram_url,
            config=config,
            post_id=channel_item.post_id,
            status_text=self._tr("status_telegram_video_downloading").format(label=channel_item.title),
        )
        return True

    def _set_active_telegram_channel_video(self, channel_item) -> None:
        self._current_telegram_channel_item = channel_item
        self._current_telegram_post_id = str(getattr(channel_item, "post_id", "") or "")
        self._current_telegram_url = str(getattr(channel_item, "url", "") or "")
        if self._current_telegram_post_id:
            self._pending_telegram_post_id = self._current_telegram_post_id
        self._select_telegram_channel_item(channel_item)

    def _clear_active_telegram_channel_video(self) -> None:
        self._current_telegram_channel_item = None
        self._current_telegram_post_id = ""
        self._current_telegram_url = ""
        self._pending_telegram_navigation_direction = 0
        self._pending_telegram_autoplay = False
        self._telegram_browser_return_available = False
        self._sync_telegram_browser_button()

    def _open_adjacent_telegram_channel_video(self, direction: int, *, allow_load_more: bool = True) -> bool:
        direction = -1 if direction < 0 else 1
        current = self._current_telegram_channel_item_for_navigation()
        if current is None:
            return False
        if self._telegram_is_busy() or self._url_is_opening():
            self.statusBar().showMessage(self._tr("msg_url_opening"))
            return True
        target = self._adjacent_telegram_channel_video(current, direction)
        if target is not None:
            self._pending_telegram_autoplay = True
            self._open_telegram_channel_item(target)
            return True
        if direction < 0 and allow_load_more and self._oldest_telegram_post_id():
            self._pending_telegram_navigation_direction = direction
            self._load_more_current_telegram_channel()
            return True
        self._pending_telegram_autoplay = False
        key = "telegram_channel_no_previous_video" if direction < 0 else "telegram_channel_no_next_video"
        self.statusBar().showMessage(self._tr(key))
        return True

    def _current_telegram_channel_item_for_navigation(self):
        current = getattr(self, "_current_telegram_channel_item", None)
        if current is not None:
            return current
        post_id = str(getattr(self, "_current_telegram_post_id", "") or "")
        url = str(getattr(self, "_current_telegram_url", "") or "")
        for item in getattr(self, "_telegram_channel_all_items", []):
            if post_id and str(getattr(item, "post_id", "") or "") == post_id:
                return item
            if url and str(getattr(item, "url", "") or "") == url:
                return item
        return None

    def _adjacent_telegram_channel_video(self, current, direction: int):
        videos = [item for item in getattr(self, "_telegram_channel_all_items", []) if getattr(item, "has_video", True)]
        current_post_id = self._telegram_numeric_post_id(current)
        numeric_items = [(self._telegram_numeric_post_id(item), item) for item in videos]
        numeric_items = [(post_id, item) for post_id, item in numeric_items if post_id >= 0]
        if current_post_id >= 0 and numeric_items:
            if direction < 0:
                candidates = [(post_id, item) for post_id, item in numeric_items if post_id < current_post_id]
                return max(candidates, default=(None, None), key=lambda pair: pair[0])[1]
            candidates = [(post_id, item) for post_id, item in numeric_items if post_id > current_post_id]
            return min(candidates, default=(None, None), key=lambda pair: pair[0])[1]

        current_url = str(getattr(current, "url", "") or "")
        current_post = str(getattr(current, "post_id", "") or "")
        current_index = -1
        for index, item in enumerate(videos):
            if current_post and str(getattr(item, "post_id", "") or "") == current_post:
                current_index = index
                break
            if current_url and str(getattr(item, "url", "") or "") == current_url:
                current_index = index
                break
        target_index = current_index + direction
        if current_index >= 0 and 0 <= target_index < len(videos):
            return videos[target_index]
        return None

    @staticmethod
    def _telegram_numeric_post_id(channel_item) -> int:
        post_id = str(getattr(channel_item, "post_id", "") or "")
        if not post_id.isdigit():
            return -1
        return int(post_id)

    def _select_telegram_channel_item(self, channel_item) -> None:
        if not hasattr(self, "_telegram_channel_list"):
            return
        target_post_id = str(getattr(channel_item, "post_id", "") or "")
        target_url = str(getattr(channel_item, "url", "") or "")
        for row, item in enumerate(getattr(self, "_telegram_channel_items", [])):
            if target_post_id and str(getattr(item, "post_id", "") or "") == target_post_id:
                self._telegram_channel_list.setCurrentRow(row)
                return
            if target_url and str(getattr(item, "url", "") or "") == target_url:
                self._telegram_channel_list.setCurrentRow(row)
                return

    def _select_adjacent_telegram_channel_video(self, direction: int) -> bool:
        if not hasattr(self, "_telegram_channel_list"):
            return False
        direction = -1 if direction < 0 else 1
        count = self._telegram_channel_list.count()
        if count <= 0:
            return False
        current_row = self._telegram_channel_list.currentRow()
        row = current_row + direction if current_row >= 0 else (count - 1 if direction < 0 else 0)
        while 0 <= row < count:
            item = self._telegram_channel_list.item(row)
            channel_item = self._telegram_channel_item_from_list_item(item)
            if channel_item is not None and getattr(channel_item, "has_video", True):
                self._telegram_channel_list.setCurrentRow(row)
                self._telegram_channel_list.scrollToItem(item)
                return True
            row += direction
        key = "telegram_channel_no_previous_video" if direction < 0 else "telegram_channel_no_next_video"
        self.statusBar().showMessage(self._tr(key))
        return True

    def _telegram_channel_item_from_list_item(self, item):
        if item is None:
            return None
        index = item.data(Qt.ItemDataRole.UserRole)
        try:
            return self._telegram_channel_items[int(index)]
        except (AttributeError, TypeError, ValueError, IndexError):
            return None

    def _telegram_login_for_current_channel(self) -> None:
        if not telegram_private_available():
            QMessageBox.warning(self, self._tr("open_url_error_title"), self._tr("telegram_login_private_unavailable"))
            return
        config = load_telegram_login_config()
        if config is None:
            config = self._telegram_login_config_dialog()
            if config is None:
                self.statusBar().showMessage(self._tr("status_telegram_login_cancelled"))
                return
            self._start_telegram_worker("start_login", config=config, status_key="status_telegram_login_starting")
            return
        self._start_telegram_worker(
            "list_authenticated",
            url=self._pending_telegram_url,
            config=config,
            search=self._telegram_current_search(),
            status_key="status_telegram_channel_loading_auth",
        )

    def _refresh_current_telegram_channel(self) -> None:
        if not self._pending_telegram_url:
            return
        self._show_telegram_channel_browser(self._pending_telegram_url, self._tr("telegram_channel_browser_loading"))
        config = load_telegram_login_config() if telegram_private_available() else None
        if config is not None and getattr(self, "_telegram_channel_authenticated", False):
            self._start_telegram_worker(
                "list_authenticated",
                url=self._pending_telegram_url,
                config=config,
                search=self._telegram_current_search(),
                status_key="status_telegram_channel_loading_auth",
            )
            return
        self._start_telegram_worker(
            "list_public",
            url=self._pending_telegram_url,
            search=self._telegram_current_search(),
            status_key="status_telegram_channel_loading",
        )

    def _load_more_current_telegram_channel(self) -> None:
        if not self._pending_telegram_url or self._telegram_is_busy():
            return
        before_post_id = self._oldest_telegram_post_id()
        if not before_post_id:
            return
        if getattr(self, "_telegram_channel_authenticated", False):
            config = load_telegram_login_config()
            if config is None:
                self._telegram_login_for_current_channel()
                return
            self._start_telegram_worker(
                "list_authenticated_more",
                url=self._pending_telegram_url,
                config=config,
                before_post_id=before_post_id,
                search=self._telegram_current_search(),
                status_key="status_telegram_channel_loading_auth",
            )
            return
        self._start_telegram_worker(
            "list_public_more",
            url=self._pending_telegram_url,
            before_post_id=before_post_id,
            search=self._telegram_current_search(),
            status_key="status_telegram_channel_loading",
        )

    def _oldest_telegram_post_id(self) -> str:
        post_ids = []
        for item in getattr(self, "_telegram_channel_all_items", []):
            post_id = str(getattr(item, "post_id", "") or "")
            if post_id.isdigit():
                post_ids.append(int(post_id))
        return str(min(post_ids)) if post_ids else ""

    def _telegram_current_search(self) -> str:
        if not hasattr(self, "_telegram_channel_search"):
            return ""
        return self._telegram_channel_search.text().strip()

    def _telegram_video_ready(self, path: str) -> None:
        self._open_local_video_path(path)

    def _open_local_video_path(self, path: str) -> None:
        self._stop_dubbing()
        self._reset_document_state_for_video()
        self._video_path = path
        self._auto_select_video_aspect_ratio()
        self._load_current_video_for_playback()
        self._media_stack.setCurrentWidget(self._video_widget)
        self._sync_telegram_browser_button()
        self._source_label.setText(path)
        self._save_settings()
        self.statusBar().showMessage(self._tr("status_opened_path").format(path=path))
        if self._dubbing_auto_enabled:
            self._dub_button.setChecked(True)
            self._start_dubbing()
        self._play_pending_telegram_navigation(source_path=path, require_runtime_match=True)

    def _play_pending_telegram_navigation(
        self,
        *,
        source_path: str = "",
        require_runtime_match: bool = False,
    ) -> None:
        if not getattr(self, "_pending_telegram_autoplay", False):
            return
        if source_path and self._video_path != source_path:
            return
        if require_runtime_match:
            runtime_path = str(getattr(self, "_runtime_media_path", "") or "")
            if not runtime_path or runtime_path != self._video_path:
                return
        self._pending_telegram_autoplay = False
        self._play_active_source()

    def _telegram_worker_failed(self, operation: str, message: str) -> None:
        detail = _repair_mojibake(message)
        if operation in {"list_public", "list_public_more"} and not telegram_private_available():
            QMessageBox.warning(self, self._tr("open_url_error_title"), self._tr("telegram_login_private_unavailable"))
            self.statusBar().showMessage(self._tr("status_open_url_failed"))
            return
        if operation in {"list_public", "list_public_more", "list_authenticated", "list_authenticated_more"} and (
            self._confirm_telegram_login(detail)
        ):
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
            search=self._telegram_current_search(),
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
        for widget_name in ("_telegram_channel_refresh_button", "_telegram_channel_load_more_button"):
            widget = getattr(self, widget_name, None)
            if widget is not None:
                widget.setEnabled(enabled)
        login_button = getattr(self, "_telegram_channel_login_button", None)
        if login_button is not None:
            login_button.setEnabled(enabled and telegram_private_available())

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
        self._auto_select_video_aspect_ratio(source)
        self._load_current_video_for_playback()
        self._media_stack.setCurrentWidget(self._video_widget)
        self._sync_telegram_browser_button()
        label = source.title if source.is_resolved else source.input_url
        self._source_label.setText(label)
        provider = f" ({source.provider})" if source.is_resolved else ""
        self.statusBar().showMessage(self._tr("status_opened_url").format(provider=provider, label=label))
        self._save_settings()
        if self._dubbing_auto_enabled:
            self._dub_button.setChecked(True)
            self._start_dubbing()
        self._play_pending_telegram_navigation(source_path=source.playback_url, require_runtime_match=True)

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
