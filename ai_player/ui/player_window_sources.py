from __future__ import annotations

from html import escape as html_escape
from pathlib import Path
from urllib.parse import urlparse

from PySide6.QtCore import QRect, QSignalBlocker, QSize, Qt, QTimer, QUrl
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest
from PySide6.QtWidgets import (
    QComboBox,
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
    QStyle,
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
    is_private_telegram_url,
    is_telegram_channel_url,
    load_telegram_login_config,
    telegram_channel_item_translation_text,
    telegram_private_available,
    validate_telegram_login_config,
)
from ai_player.services.video_source import inspect_video_url, is_supported_video_url
from ai_player.services.youtube_channel import (
    is_youtube_browse_url,
)
from ai_player.ui.cache_progress_dialog import CacheProgressDialog
from ai_player.ui.channel_browser import (
    channel_item_media_kind,
    channel_item_search_text,
    current_channel_provider,
    filter_channel_items,
    normalize_channel_filter,
    telegram_channel_key,
    telegram_post_id_from_url,
    youtube_video_id_from_url,
)
from ai_player.ui.player_window_utils import repair_mojibake as _repair_mojibake
from ai_player.workers.player_window_workers import (
    DocumentTranscriptWorker,
    TelegramChannelWorker,
    TelegramContentTranslationWorker,
)

TELEGRAM_ITEM_HTML_ROLE = Qt.ItemDataRole.UserRole.value + 10
TELEGRAM_BLACKLIST_BUTTON_ROLE = Qt.ItemDataRole.UserRole.value + 11
TELEGRAM_BLACKLIST_BUTTON_WIDTH = 88
TELEGRAM_BLACKLIST_BUTTON_HEIGHT = 30
TELEGRAM_BLACKLIST_BUTTON_MARGIN = 10
TELEGRAM_TRANSLATION_COLOR = "#0f766e"


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
        self._show_video_output()
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
        dialog = _VideoUrlDialog(
            self._video_url_recent_urls_for_settings(),
            full_cache=self._effective_video_url_full_cache(),
            force_full_cache=self._source_filter_forces_video_url_full_cache(),
            quality=self._combo_text(self._playback_quality_combo),
            language_id=self._ui_language(),
            parent=self,
        )
        if dialog.exec() != QDialog.Accepted:
            return
        url = dialog.url
        preflight = inspect_video_url(url)
        if not preflight.supported:
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
            self._remember_video_url(url)
            self._start_telegram_channel_flow(url)
            return
        if is_youtube_browse_url(url):
            self._remember_video_url(url)
            self._start_youtube_channel_flow(url)
            return

        self._open_resolved_video_url(url, full_cache_override=dialog.full_cache)

    def _open_url_from_browser(self, url: str) -> None:
        url = str(url or "").strip()
        if not url:
            return
        if self._url_is_opening() or self._telegram_is_busy():
            self.statusBar().showMessage(self._tr("msg_url_opening"))
            return
        if is_telegram_channel_url(url):
            self._start_telegram_channel_flow(url)
            return
        if is_youtube_browse_url(url):
            self._start_youtube_channel_flow(url)
            return
        if is_supported_video_url(url):
            self._open_resolved_video_url(url, browser_fallback_on_unavailable=True)

    def _open_resolved_video_url(
        self,
        url: str,
        *,
        keep_telegram_context: bool = False,
        full_cache_override: bool | None = None,
        browser_fallback_on_unavailable: bool = False,
    ) -> None:
        if not keep_telegram_context and not is_telegram_channel_url(url):
            self._clear_active_telegram_channel_video()
        self._remember_video_url(url)
        forced_full_cache = self._source_filter_forces_video_url_full_cache()
        full_cache = self._effective_video_url_full_cache()
        if full_cache_override is not None and not forced_full_cache:
            full_cache = bool(full_cache_override)
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
        self._last_video_url_request = {
            "url": url,
            "full_cache": full_cache,
            "quality": self._config.playback_video_quality,
            "keep_telegram_context": keep_telegram_context,
            "browser_fallback_on_unavailable": browser_fallback_on_unavailable,
        }
        self._video_url.start(
            url,
            self._config.playback_video_quality,
            full_cache=full_cache,
            language_id=self._config.gui_language,
        )

    def _remember_video_url(self, url: str) -> None:
        normalized = str(url or "").strip()
        if not normalized:
            return
        history = [item for item in self._video_url_recent_urls_for_settings() if item != normalized]
        self._video_url_recent_urls = tuple([normalized, *history][:20])

    def _video_url_recent_urls_for_settings(self) -> tuple[str, ...]:
        return tuple(getattr(self, "_video_url_recent_urls", self._config.video_url_recent_urls) or ())

    def _start_telegram_channel_flow(self, url: str) -> None:
        if self._telegram_is_busy():
            QMessageBox.information(self, self._tr("app_title"), self._tr("msg_url_opening"))
            return
        self._telegram_channel_provider = "telegram"
        self._pending_telegram_url = url
        self._pending_telegram_post_id = self._telegram_post_id_from_url(url)
        self._queue_save_settings()
        self._show_telegram_channel_browser(url, self._tr("telegram_channel_browser_loading"))
        if is_private_telegram_url(url):
            self._start_private_telegram_channel_flow(url)
            return
        self._start_telegram_worker("list_public", url=url, status_key="status_telegram_channel_loading")

    def _start_youtube_channel_flow(self, url: str) -> None:
        if self._telegram_is_busy():
            QMessageBox.information(self, self._tr("app_title"), self._tr("msg_url_opening"))
            return
        self._telegram_channel_provider = "youtube"
        self._pending_telegram_url = url
        self._pending_telegram_post_id = self._youtube_video_id_from_url(url)
        self._queue_save_settings()
        self._show_telegram_channel_browser(url, self._tr("youtube_channel_browser_loading"))
        self._start_telegram_worker("list_youtube", url=url, status_key="status_youtube_channel_loading")

    def _start_private_telegram_channel_flow(self, url: str) -> None:
        if not telegram_private_available():
            QMessageBox.warning(self, self._tr("open_url_error_title"), self._tr("telegram_login_private_unavailable"))
            self.statusBar().showMessage(self._tr("status_open_url_failed"))
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
            url=url,
            config=config,
            status_key="status_telegram_channel_loading_auth",
        )

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
        self._set_telegram_opening_controls(False, keep_browser_tools=operation == "download")
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
        worker.progress_changed.connect(self._telegram_download_progress_changed)
        worker.video_ready.connect(self._telegram_video_ready)
        worker.failed.connect(lambda message, op=operation: self._telegram_worker_failed(op, message))
        worker.finished.connect(lambda worker=worker: self._telegram_worker_finished(worker))
        worker.start()

    def _telegram_items_ready(self, items, operation: str = "") -> None:
        continuation = ""
        if hasattr(items, "items"):
            continuation = str(getattr(items, "continuation", "") or "")
            items = getattr(items, "items", [])
        items = list(items)
        if operation in {"list_youtube", "list_youtube_more"}:
            self._telegram_channel_provider = "youtube"
            self._telegram_channel_state.channel_continuation = continuation
        if operation.endswith("_more"):
            self._telegram_auto_load_pending_before_post_id = ""
            self._append_telegram_channel_items(items)
        else:
            self._telegram_auto_load_pending_before_post_id = ""
            self._set_telegram_channel_items(items)
        if operation in {"list_authenticated", "list_authenticated_more"}:
            self._telegram_channel_authenticated = True
            self.statusBar().showMessage(self._tr("status_telegram_login_ready"))
        elif operation in {"list_youtube", "list_youtube_more"}:
            self._telegram_channel_authenticated = False
            self.statusBar().showMessage(
                self._tr("youtube_channel_browser_ready").format(count=len(self._telegram_channel_all_items))
            )
        else:
            self._telegram_channel_authenticated = False
            self.statusBar().showMessage(
                self._tr("telegram_channel_browser_ready").format(count=len(self._telegram_channel_all_items))
            )
        pending_direction = int(getattr(self, "_pending_telegram_navigation_direction", 0) or 0)
        if pending_direction and operation.endswith("_more"):
            self._pending_telegram_navigation_direction = 0
            self._open_adjacent_telegram_channel_video(pending_direction, allow_load_more=False)
        self._maybe_auto_translate_telegram_channel()

    def _telegram_videos_ready(self, videos) -> None:
        self._telegram_items_ready(videos)

    def _show_telegram_channel_browser(self, url: str, status: str = "") -> None:
        self._clear_active_telegram_channel_video()
        self._stop_dubbing()
        self._player.stop()
        self._reset_document_state_for_video()
        self._video_path = None
        self._runtime_media_path = ""
        self._telegram_channel_state.reset_loaded_channel()
        self._telegram_channel_list.clear()
        self._telegram_channel_preview.clear()
        self._clear_telegram_channel_thumbnail()
        self._apply_telegram_browser_preferences(url)
        self._sync_channel_browser_texts()
        title_key = (
            "youtube_channel_browser_title"
            if self._current_channel_provider() == "youtube"
            else "telegram_channel_browser_title"
        )
        self._telegram_channel_title.setText(self._tr(title_key).format(url=url))
        self._telegram_channel_status.setText(status)
        self._telegram_channel_open_button.setEnabled(False)
        self._telegram_channel_login_button.setEnabled(
            self._current_channel_provider() == "telegram" and telegram_private_available()
        )
        self._telegram_channel_refresh_button.setEnabled(True)
        self._telegram_channel_load_more_button.setEnabled(True)
        self._telegram_channel_thumbnail.setText("")
        self._show_telegram_browser_media_output()
        self._media_stack.setCurrentWidget(self._telegram_channel_view)
        self._source_label.setText(url)
        self._sync_telegram_browser_button()
        self._sync_telegram_side_panel_toggle_button()
        self._set_telegram_side_panel_visible(self._telegram_side_panel_visible)
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
        title_key = (
            "youtube_channel_browser_title"
            if self._current_channel_provider() == "youtube"
            else "telegram_channel_browser_title"
        )
        ready_key = (
            "youtube_channel_browser_ready"
            if self._current_channel_provider() == "youtube"
            else "telegram_channel_browser_ready"
        )
        self._sync_channel_browser_texts()
        self._telegram_channel_title.setText(self._tr(title_key).format(url=url))
        self._telegram_channel_status.setText(
            self._tr(ready_key).format(count=len(self._telegram_channel_all_items))
        )
        current = self._current_telegram_channel_item_for_navigation()
        if current is not None:
            self._telegram_suppress_auto_open_selection = True
            try:
                self._select_telegram_channel_item(current)
            finally:
                self._telegram_suppress_auto_open_selection = False
        self._show_telegram_browser_media_output()
        self._media_stack.setCurrentWidget(self._telegram_channel_view)
        self._source_label.setText(url)
        self._sync_telegram_browser_button()
        self._sync_telegram_side_panel_toggle_button()
        self._apply_media_aspect_ratio()

    def _show_video_output(self) -> None:
        if self._should_embed_telegram_video_output():
            self._player.set_video_output(self._telegram_video_widget)
            self._telegram_channel_media_stack.setCurrentWidget(self._telegram_video_widget)
            self._media_stack.setCurrentWidget(self._telegram_channel_view)
        else:
            self._player.set_video_output(self._video_widget)
            self._media_stack.setCurrentWidget(self._video_widget)
        self._apply_media_aspect_ratio()

    def _show_telegram_browser_media_output(self) -> None:
        set_video_output = getattr(getattr(self, "_player", None), "set_video_output", None)
        if callable(set_video_output):
            set_video_output(self._video_widget)
        self._show_telegram_thumbnail_output()

    def _sync_channel_browser_texts(self) -> None:
        provider = self._current_channel_provider()
        search = getattr(self, "_telegram_channel_search", None)
        remote_search = getattr(self, "_telegram_channel_remote_search_button", None)
        if search is not None:
            search_key = "youtube_channel_search" if provider == "youtube" else "telegram_channel_search"
            search.setPlaceholderText(self._tr(search_key))
        if remote_search is not None:
            remote_key = (
                "youtube_channel_remote_search"
                if provider == "youtube"
                else "telegram_channel_remote_search"
            )
            remote_search.setText(self._tr(remote_key))

    def _should_embed_telegram_video_output(self) -> bool:
        return bool(
            getattr(self, "_current_telegram_channel_item", None) is not None
            and getattr(self, "_telegram_browser_return_available", False)
            and getattr(self, "_telegram_channel_view", None) is not None
        )

    def _show_telegram_thumbnail_output(self) -> None:
        telegram_stack = getattr(self, "_telegram_channel_media_stack", None)
        thumbnail = getattr(self, "_telegram_channel_thumbnail", None)
        if telegram_stack is not None and thumbnail is not None:
            telegram_stack.setCurrentWidget(thumbnail)

    def _video_widget_in_telegram_media(self) -> bool:
        telegram_stack = getattr(self, "_telegram_channel_media_stack", None)
        video_widget = getattr(self, "_telegram_video_widget", None)
        return bool(
            telegram_stack is not None
            and video_widget is not None
            and telegram_stack.currentWidget() is video_widget
        )

    def _telegram_video_output_is_visible(self) -> bool:
        telegram_stack = getattr(self, "_telegram_channel_media_stack", None)
        video_widget = getattr(self, "_telegram_video_widget", None)
        return bool(
            telegram_stack is not None
            and video_widget is not None
            and telegram_stack.currentWidget() is video_widget
            and self._media_stack.currentWidget() is self._telegram_channel_view
        )

    def _telegram_side_panel_toggled(self, visible: bool) -> None:
        self._set_telegram_side_panel_visible(visible)

    def _telegram_side_panel_splitter_moved(self, *_args) -> None:
        splitter = getattr(self, "_telegram_channel_splitter", None)
        side_panel = getattr(self, "_telegram_channel_side_panel", None)
        if splitter is None or side_panel is None or side_panel.isHidden():
            return
        sizes = splitter.sizes()
        if len(sizes) < 2:
            return
        visible = sizes[1] > 0
        self._telegram_side_panel_visible = visible
        if visible:
            self._telegram_side_panel_sizes = sizes[:2]
        self._sync_telegram_side_panel_toggle_button()
        self._queue_save_settings()

    def _set_telegram_side_panel_visible(self, visible: bool) -> None:
        splitter = getattr(self, "_telegram_channel_splitter", None)
        side_panel = getattr(self, "_telegram_channel_side_panel", None)
        if splitter is None or side_panel is None:
            return
        sizes = splitter.sizes()
        if len(sizes) < 2:
            sizes = [1, 1]
        visible = bool(visible)
        if visible:
            side_panel.setVisible(True)
            restore_sizes = list(getattr(self, "_telegram_side_panel_sizes", [1, 1]) or [1, 1])
            if len(restore_sizes) < 2 or restore_sizes[0] <= 0 or restore_sizes[1] <= 0:
                restore_sizes = [1, 1]
            splitter.setSizes(restore_sizes[:2])
        else:
            if not side_panel.isHidden() and sizes[1] > 0:
                self._telegram_side_panel_sizes = sizes[:2]
            side_panel.setVisible(False)
            splitter.setSizes([max(1, sum(sizes) or splitter.width() or 1), 0])
        self._telegram_side_panel_visible = visible
        self._sync_telegram_side_panel_toggle_button()
        self._apply_media_aspect_ratio()
        self._queue_save_settings()

    def _sync_telegram_side_panel_toggle_button(self) -> None:
        button = getattr(self, "_telegram_channel_side_toggle_button", None)
        if button is None:
            return
        visible = bool(getattr(self, "_telegram_side_panel_visible", True))
        icon = QStyle.StandardPixmap.SP_ArrowRight if visible else QStyle.StandardPixmap.SP_ArrowLeft
        button.setIcon(self.style().standardIcon(icon))
        tooltip_key = "telegram_channel_side_hide" if visible else "telegram_channel_side_show"
        button.setToolTip(self._tr(tooltip_key))
        button.setAccessibleName(self._tr(tooltip_key))
        was_blocked = button.blockSignals(True)
        button.setChecked(visible)
        button.blockSignals(was_blocked)

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
        self._telegram_channel_state.set_visible_items(items)
        list_widget = self._telegram_channel_list
        self._telegram_populating_browser = True
        blocker = QSignalBlocker(list_widget)
        try:
            list_widget.clear()
            for index, channel_item in enumerate(self._telegram_channel_items):
                label = self._telegram_channel_item_label(channel_item)
                item = QListWidgetItem(label)
                item.setToolTip(str(getattr(channel_item, "url", "") or "").strip())
                item.setSizeHint(QSize(0, self._telegram_channel_item_height(label)))
                item.setData(Qt.ItemDataRole.UserRole, index)
                item.setData(TELEGRAM_ITEM_HTML_ROLE, self._telegram_channel_item_html(channel_item, summary=True))
                button_key = (
                    "telegram_unblacklist_button"
                    if self._telegram_channel_state.is_blacklisted(channel_item)
                    else "telegram_blacklist_button"
                )
                item.setData(TELEGRAM_BLACKLIST_BUTTON_ROLE, self._tr(button_key))
                self._set_telegram_item_thumbnail(item, channel_item, index)
                list_widget.addItem(item)
            if self._telegram_channel_items:
                target_row = self._telegram_target_row()
                list_widget.setCurrentRow(target_row if target_row >= 0 else 0)
            self._telegram_channel_selection_changed(list_widget.currentItem(), None)
        finally:
            del blocker
            self._telegram_populating_browser = False
        ready_key = (
            "youtube_channel_browser_ready"
            if self._current_channel_provider() == "youtube"
            else "telegram_channel_browser_ready"
        )
        self._telegram_channel_status.setText(
            self._tr(ready_key).format(count=len(self._telegram_channel_all_items))
        )
        self._telegram_channel_login_button.setEnabled(
            self._current_channel_provider() == "telegram" and telegram_private_available()
        )

    def _telegram_channel_item_label(self, channel_item) -> str:
        return "\n".join(self._telegram_channel_item_summary_lines(channel_item))

    def _telegram_channel_item_summary_lines(self, channel_item) -> list[str]:
        kind_label = self._telegram_media_kind_label(channel_item)
        post_id = str(getattr(channel_item, "post_id", "") or "").strip()
        heading_parts = [kind_label]
        if post_id:
            heading_parts.append(self._tr("telegram_channel_item_post_id").format(post_id=post_id))
        status_label = self._telegram_item_status_label(channel_item)
        if status_label:
            heading_parts.append(status_label)
        lines = [" ".join(heading_parts)]

        source_text = telegram_channel_item_translation_text(channel_item)
        if source_text:
            lines.append(self._telegram_summary_excerpt(source_text))
        translated = self._telegram_channel_item_translation(channel_item)
        if translated and translated != source_text:
            lines.append(self._telegram_summary_excerpt(translated))

        details = []
        date = str(getattr(channel_item, "date", "") or "").strip()
        if date:
            details.append(date)
        duration = str(getattr(channel_item, "duration", "") or "").strip()
        if duration:
            details.append(duration)
        file_size = int(getattr(channel_item, "file_size", 0) or 0)
        if file_size:
            details.append(self._format_bytes(file_size))
        file_name = str(getattr(channel_item, "file_name", "") or "").strip()
        if file_name:
            details.append(self._telegram_summary_excerpt(file_name, max_chars=70))
        if details:
            lines.append(" | ".join(details))
        return lines

    def _telegram_channel_item_lines(self, channel_item) -> list[str]:
        kind_label = self._telegram_media_kind_label(channel_item)
        post_id = str(getattr(channel_item, "post_id", "") or "").strip()
        heading_parts = [kind_label]
        if post_id:
            heading_parts.append(self._tr("telegram_channel_item_post_id").format(post_id=post_id))
        status_label = self._telegram_item_status_label(channel_item)
        if status_label:
            heading_parts.append(status_label)
        lines = [" ".join(heading_parts)]

        text = str(getattr(channel_item, "text", "") or "").strip()
        title = str(getattr(channel_item, "title", "") or "").strip()
        if text:
            lines.append(text)
        elif title:
            lines.append(title)
        translated = self._telegram_channel_item_translation(channel_item)
        if translated and translated != telegram_channel_item_translation_text(channel_item):
            lines.append(translated)

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

    def _telegram_channel_item_html(self, channel_item, *, summary: bool = False) -> str:
        translated = self._telegram_channel_item_translation(channel_item)
        source_text = telegram_channel_item_translation_text(channel_item)
        html_lines = []
        lines = (
            self._telegram_channel_item_summary_lines(channel_item)
            if summary
            else self._telegram_channel_item_lines(channel_item)
        )
        translated_summary = self._telegram_summary_excerpt(translated) if translated else ""
        for line in lines:
            text = html_escape(str(line or ""))
            if translated and translated != source_text and line in {translated, translated_summary}:
                text = f'<span style="color:{TELEGRAM_TRANSLATION_COLOR};">{text}</span>'
            html_lines.append(text)
        return "<br>".join(html_lines)

    @staticmethod
    def _telegram_channel_item_height(label: str) -> int:
        text = str(label or "")
        chars_per_line = 96
        line_count = 0
        for line in text.splitlines() or [""]:
            line_count += max(1, (len(line) + chars_per_line - 1) // chars_per_line)
        text_height = line_count * 18
        return max(104, text_height + 14)

    @staticmethod
    def _telegram_summary_excerpt(value: str, *, max_chars: int = 220) -> str:
        text = " ".join(str(value or "").split())
        if len(text) <= max_chars:
            return text
        return f"{text[: max_chars - 1].rstrip()}..."

    def _set_telegram_channel_items(self, items) -> None:
        self._telegram_channel_state.replace_items(items)
        self._filter_telegram_channel_items()

    def _append_telegram_channel_items(self, items) -> None:
        self._telegram_channel_state.append_unique_items(items)
        self._filter_telegram_channel_items()

    def _filter_telegram_channel_items(self, *_args) -> None:
        all_items = list(getattr(self, "_telegram_channel_all_items", []))
        media_filter = "all"
        if hasattr(self, "_telegram_channel_filter_combo"):
            media_filter = str(self._telegram_channel_filter_combo.currentData() or "all")
        query = ""
        if hasattr(self, "_telegram_channel_search"):
            query = self._telegram_channel_search.text()
        filtered = filter_channel_items(
            all_items,
            media_filter=media_filter,
            query=query,
            is_blacklisted=self._telegram_channel_state.is_blacklisted,
            translation_for_item=self._telegram_channel_item_translation,
        )
        self._populate_telegram_channel_browser(filtered)

    def _telegram_search_changed(self, *_args) -> None:
        self._filter_telegram_channel_items()
        self._queue_save_settings()

    def _telegram_filter_changed(self, *_args) -> None:
        self._filter_telegram_channel_items()
        self._queue_save_settings()

    def _handle_telegram_blacklist_button_event(self, event, *, activate: bool) -> bool:
        list_widget = getattr(self, "_telegram_channel_list", None)
        if list_widget is None:
            return False
        position = event.position().toPoint() if hasattr(event, "position") else event.pos()
        list_item = list_widget.itemAt(position)
        if list_item is None:
            return False
        if not self._telegram_blacklist_button_rect(list_widget.visualItemRect(list_item)).contains(position):
            return False
        if activate:
            channel_item = self._telegram_channel_item_from_list_item(list_item)
            self._toggle_telegram_blacklist_item(channel_item)
        return True

    @staticmethod
    def _telegram_blacklist_button_rect(row_rect: QRect) -> QRect:
        x = row_rect.right() - TELEGRAM_BLACKLIST_BUTTON_WIDTH - TELEGRAM_BLACKLIST_BUTTON_MARGIN
        y = row_rect.top() + TELEGRAM_BLACKLIST_BUTTON_MARGIN
        return QRect(x, y, TELEGRAM_BLACKLIST_BUTTON_WIDTH, TELEGRAM_BLACKLIST_BUTTON_HEIGHT)

    def _toggle_telegram_blacklist_item(self, channel_item) -> None:
        if channel_item is None:
            return
        item_key = self._telegram_channel_item_key(channel_item)
        content_key = self._telegram_channel_state.content_key(channel_item)
        if not item_key and not content_key:
            return
        if self._telegram_channel_state.is_blacklisted(channel_item):
            if self._telegram_channel_state.unblacklist_item(channel_item):
                self.statusBar().showMessage(self._tr("status_telegram_unblacklisted"))
        elif self._telegram_channel_state.blacklist_item(channel_item):
            if self._telegram_channel_state.pending_open_item_key == item_key:
                self._telegram_channel_state.pending_open_item_key = ""
            self.statusBar().showMessage(self._tr("status_telegram_blacklisted"))
        self._queue_save_settings()
        self._filter_telegram_channel_items()

    def _telegram_item_search_text(self, channel_item) -> str:
        return channel_item_search_text(
            channel_item,
            translation_for_item=self._telegram_channel_item_translation,
        )

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
        return telegram_post_id_from_url(url)

    def _telegram_channel_selection_changed(self, current, _previous=None) -> None:
        channel_item = self._telegram_channel_item_from_list_item(current)
        if channel_item is None:
            self._telegram_channel_preview.clear()
            self._clear_telegram_channel_thumbnail()
            self._telegram_channel_open_button.setEnabled(False)
            return
        self._telegram_channel_preview.setHtml(self._telegram_channel_item_html(channel_item, summary=False))
        current_key = self._telegram_channel_item_key(channel_item)
        active_key = self._telegram_channel_item_key_values(self._current_telegram_post_id, self._current_telegram_url)
        active_video_visible = current_key and current_key == active_key and self._telegram_video_output_is_visible()
        if not active_video_visible:
            self._show_telegram_channel_thumbnail(channel_item)
        self._telegram_channel_open_button.setEnabled(bool(getattr(channel_item, "has_video", True)))
        if not getattr(channel_item, "has_video", True):
            if self._video_widget_in_telegram_media():
                self._player.stop()
            if self._telegram_is_busy() or self._url_is_opening():
                self._telegram_channel_state.pending_open_item_key = current_key
            return
        self._maybe_auto_open_telegram_video(channel_item)

    def _maybe_auto_open_telegram_video(self, channel_item) -> None:
        if not self._telegram_auto_open_enabled():
            return
        if getattr(self, "_telegram_populating_browser", False):
            return
        if getattr(self, "_telegram_suppress_auto_open_selection", False):
            return
        if getattr(self, "_telegram_selection_auto_opening", False):
            return
        if not getattr(channel_item, "has_video", True):
            return
        if self._telegram_channel_item_auto_open_blocked(channel_item):
            return
        if self._telegram_is_busy() or self._url_is_opening():
            self._queue_pending_telegram_channel_item(channel_item)
            return
        current_key = self._telegram_channel_item_key(channel_item)
        active_key = self._telegram_channel_item_key_values(self._current_telegram_post_id, self._current_telegram_url)
        if current_key and current_key == active_key and self._telegram_video_output_is_visible():
            return
        self._telegram_selection_auto_opening = True
        try:
            self._pending_telegram_autoplay = True
            self._open_telegram_channel_item(channel_item)
        finally:
            self._telegram_selection_auto_opening = False

    def _telegram_channel_item_auto_open_blocked(self, channel_item) -> bool:
        status = self._telegram_channel_state.item_status(channel_item)
        return status in {"failed", "loading", "queued"} or self._telegram_channel_state.is_blacklisted(channel_item)

    def _telegram_load_more_toggled(self, enabled: bool) -> None:
        if enabled:
            self._maybe_auto_load_more_telegram_channel()

    def _telegram_channel_scroll_changed(self, *_args) -> None:
        self._maybe_auto_load_more_telegram_channel()

    def _maybe_auto_load_more_telegram_channel(self) -> None:
        button = getattr(self, "_telegram_channel_load_more_button", None)
        if button is None or not button.isChecked():
            return
        if self._telegram_is_busy() or self._url_is_opening():
            return
        scroll_bar = self._telegram_channel_list.verticalScrollBar()
        if scroll_bar.maximum() <= 0:
            return
        threshold = max(24, scroll_bar.pageStep())
        if scroll_bar.value() < scroll_bar.maximum() - threshold:
            return
        cursor = (
            str(getattr(self._telegram_channel_state, "channel_continuation", "") or "")
            if self._current_channel_provider() == "youtube"
            else self._oldest_telegram_post_id()
        )
        if not cursor:
            return
        if cursor == getattr(self, "_telegram_auto_load_pending_before_post_id", ""):
            return
        self._telegram_auto_load_pending_before_post_id = cursor
        self._load_more_current_telegram_channel()

    def _telegram_translation_toggled(self, enabled: bool) -> None:
        if enabled:
            self._translate_current_telegram_channel()
            return
        worker = getattr(self, "_telegram_translation_worker", None)
        if worker is not None and worker.isRunning():
            worker.stop()

    def _maybe_auto_translate_telegram_channel(self) -> None:
        button = getattr(self, "_telegram_channel_translate_button", None)
        if button is not None and button.isChecked():
            self._translate_current_telegram_channel(auto=True)

    def _translate_current_telegram_channel(self, *args, auto: bool = False) -> None:
        if self._telegram_translation_worker is not None and self._telegram_translation_worker.isRunning():
            if not auto:
                self.statusBar().showMessage(self._tr("status_telegram_translation_loading"))
            return
        items = self._telegram_channel_items_to_translate()
        if not items:
            if not auto:
                self.statusBar().showMessage(self._tr("telegram_channel_no_text_to_translate"))
            return

        self.statusBar().showMessage(self._tr("status_telegram_translation_loading"))
        worker = TelegramContentTranslationWorker(
            self._current_runtime_config(),
            items,
            language_id=self._config.gui_language,
            parent=self,
        )
        self._telegram_translation_worker = worker
        worker.ready.connect(self._telegram_translation_ready)
        worker.failed.connect(self._telegram_translation_failed)
        worker.finished.connect(self._telegram_translation_worker_finished)
        worker.start()

    def _telegram_channel_items_to_translate(self) -> list[object]:
        return self._telegram_channel_state.items_to_translate(telegram_channel_item_translation_text)

    def _telegram_translation_ready(self, results) -> None:
        current_key = self._telegram_channel_item_key(
            self._telegram_channel_item_from_list_item(self._telegram_channel_list.currentItem())
        )
        count = 0
        for post_id, url, translated in list(results or []):
            if self._telegram_channel_state.store_translation(post_id, url, translated):
                count += 1
        self._filter_telegram_channel_items()
        if current_key:
            self._select_telegram_channel_item_key(current_key)
        self.statusBar().showMessage(self._tr("status_telegram_translation_ready").format(count=count))

    def _telegram_translation_failed(self, message: str) -> None:
        QMessageBox.warning(self, self._tr("open_url_error_title"), _repair_mojibake(str(message)))
        self.statusBar().showMessage(self._tr("status_telegram_translation_failed"))

    def _telegram_translation_worker_finished(self) -> None:
        worker = self.sender()
        if worker is not None:
            worker.deleteLater()
        if self._telegram_translation_worker is worker:
            self._telegram_translation_worker = None
            self._set_telegram_translation_controls(not self._telegram_is_busy() and not self._url_is_opening())

    def _set_telegram_translation_controls(self, enabled: bool) -> None:
        button = getattr(self, "_telegram_channel_translate_button", None)
        if button is not None:
            button.setEnabled(enabled)

    def _telegram_channel_item_translation(self, channel_item) -> str:
        return self._telegram_channel_state.item_translation(channel_item)

    def _telegram_auto_open_enabled(self) -> bool:
        checkbox = getattr(self, "_telegram_channel_auto_open_check", None)
        if checkbox is not None:
            return checkbox.isChecked()
        return bool(getattr(self._config, "telegram_auto_open_videos", True))

    def _select_telegram_channel_item_key(self, key: str) -> None:
        if not key:
            return
        for row, channel_item in enumerate(getattr(self, "_telegram_channel_items", [])):
            if self._telegram_channel_item_key(channel_item) == key:
                self._telegram_channel_list.setCurrentRow(row)
                return

    def _telegram_channel_item_key(self, channel_item) -> str:
        return self._telegram_channel_state.item_key(channel_item)

    def _telegram_channel_item_key_values(self, post_id: object, url: object) -> str:
        return self._telegram_channel_state.item_key_values(post_id, url)

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
        self._telegram_channel_thumbnail.show()
        self._show_telegram_thumbnail_output()

    def _set_telegram_channel_thumbnail_pixmap(self, pixmap: QPixmap) -> None:
        if pixmap.isNull():
            self._clear_telegram_channel_thumbnail()
            return
        self._telegram_channel_thumbnail_source = pixmap
        self._refresh_telegram_channel_thumbnail()
        self._telegram_channel_thumbnail.show()
        self._show_telegram_thumbnail_output()

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
            self._pending_telegram_autoplay = True
            self._open_telegram_channel_item(channel_item)
        else:
            self.statusBar().showMessage(self._tr("telegram_channel_text_only"))

    def _telegram_media_kind(self, channel_item) -> str:
        return channel_item_media_kind(channel_item)

    def _telegram_media_kind_label(self, channel_item) -> str:
        key = {
            "video": "telegram_channel_item_video",
            "photo": "telegram_channel_item_photo",
            "document": "telegram_channel_item_document",
            "audio": "telegram_channel_item_audio",
            "text": "telegram_channel_item_post",
        }.get(self._telegram_media_kind(channel_item), "telegram_channel_item_post")
        return self._tr(key)

    def _telegram_item_status_label(self, channel_item) -> str:
        status = self._telegram_channel_state.item_status(channel_item)
        key = {
            "loading": "telegram_channel_status_loading",
            "queued": "telegram_channel_status_queued",
            "current": "telegram_channel_status_current",
            "failed": "telegram_channel_status_failed",
            "opened": "telegram_channel_status_opened",
        }.get(status, "")
        return self._tr(key) if key else ""

    def _open_selected_telegram_channel_item(self) -> None:
        channel_item = self._telegram_channel_item_from_list_item(self._telegram_channel_list.currentItem())
        if channel_item is None:
            self.statusBar().showMessage(self._tr("telegram_channel_no_selection"))
            return
        if not getattr(channel_item, "has_video", True):
            self.statusBar().showMessage(self._tr("telegram_channel_text_only"))
            return
        self._pending_telegram_autoplay = True
        self._open_telegram_channel_item(channel_item)

    def _open_telegram_channel_item(self, channel_item) -> None:
        current_key = self._telegram_channel_state.mark_opening(channel_item)
        if self._telegram_channel_state.pending_open_item_key == current_key:
            self._telegram_channel_state.pending_open_item_key = ""
        self._set_active_telegram_channel_video(channel_item)
        self._telegram_browser_return_available = True
        self._refresh_telegram_channel_item_statuses()
        selected_key = (
            "status_youtube_channel_selected"
            if self._current_channel_provider() == "youtube"
            else "status_telegram_channel_selected"
        )
        self.statusBar().showMessage(self._tr(selected_key).format(label=channel_item.title))
        if getattr(channel_item, "authenticated", False):
            self._download_telegram_channel_item(channel_item, prompt_for_config=True)
            return
        if self._download_telegram_channel_item(channel_item):
            return
        media_url = str(getattr(channel_item, "media_url", "") or "").strip()
        if media_url:
            self._open_resolved_video_url(media_url, keep_telegram_context=True)
            return
        self._open_resolved_video_url(channel_item.url, keep_telegram_context=True)

    def _download_telegram_channel_item(self, channel_item, *, prompt_for_config: bool = False) -> bool:
        if str(getattr(channel_item, "provider", "telegram") or "telegram") != "telegram":
            return False
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
        self._queue_save_settings()

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
        key = self._no_adjacent_channel_video_key(direction)
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
                self._telegram_channel_list.scrollToItem(item)
                self._telegram_channel_list.setCurrentRow(row)
                return True
            row += direction
        key = self._no_adjacent_channel_video_key(direction)
        self.statusBar().showMessage(self._tr(key))
        return True

    def _no_adjacent_channel_video_key(self, direction: int) -> str:
        if self._current_channel_provider() == "youtube":
            return "youtube_channel_no_previous_video" if direction < 0 else "youtube_channel_no_next_video"
        return "telegram_channel_no_previous_video" if direction < 0 else "telegram_channel_no_next_video"

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
            status_key="status_telegram_channel_loading_auth",
        )

    def _refresh_current_telegram_channel(self) -> None:
        self._reload_current_telegram_channel(search="")

    def _search_current_telegram_channel_remote(self) -> None:
        self._reload_current_telegram_channel(
            search=self._telegram_current_search(),
            status_key="status_telegram_channel_searching",
        )

    def _reload_current_telegram_channel(self, *, search: str = "", status_key: str = "") -> None:
        if not self._pending_telegram_url:
            return
        if self._current_channel_provider() == "youtube":
            self._show_telegram_channel_browser(self._pending_telegram_url, self._tr("youtube_channel_browser_loading"))
            self._start_telegram_worker(
                "list_youtube",
                url=self._pending_telegram_url,
                search=search,
                status_key=status_key or "status_youtube_channel_searching",
            )
            return
        was_authenticated = bool(getattr(self, "_telegram_channel_authenticated", False))
        self._show_telegram_channel_browser(self._pending_telegram_url, self._tr("telegram_channel_browser_loading"))
        config = load_telegram_login_config() if telegram_private_available() else None
        if config is not None and was_authenticated:
            self._start_telegram_worker(
                "list_authenticated",
                url=self._pending_telegram_url,
                config=config,
                search=search,
                status_key=status_key or "status_telegram_channel_loading_auth",
            )
            return
        self._start_telegram_worker(
            "list_public",
            url=self._pending_telegram_url,
            search=search,
            status_key=status_key or "status_telegram_channel_loading",
        )

    def _load_more_current_telegram_channel(self) -> None:
        if not self._pending_telegram_url or self._telegram_is_busy():
            return
        if self._current_channel_provider() == "youtube":
            continuation = str(getattr(self._telegram_channel_state, "channel_continuation", "") or "")
            if not continuation:
                return
            self._start_telegram_worker(
                "list_youtube_more",
                url=self._pending_telegram_url,
                before_post_id=continuation,
                status_key="status_youtube_channel_loading",
            )
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
                status_key="status_telegram_channel_loading_auth",
            )
            return
        self._start_telegram_worker(
            "list_public_more",
            url=self._pending_telegram_url,
            before_post_id=before_post_id,
            status_key="status_telegram_channel_loading",
        )

    def _oldest_telegram_post_id(self) -> str:
        post_ids = []
        for item in getattr(self, "_telegram_channel_all_items", []):
            post_id = str(getattr(item, "post_id", "") or "")
            if post_id.isdigit():
                post_ids.append(int(post_id))
        return str(min(post_ids)) if post_ids else ""

    def _current_channel_provider(self) -> str:
        return current_channel_provider(
            getattr(self, "_telegram_channel_provider", ""),
            getattr(self, "_pending_telegram_url", ""),
        )

    @staticmethod
    def _youtube_video_id_from_url(url: str) -> str:
        return youtube_video_id_from_url(url)

    def _telegram_current_search(self) -> str:
        if not hasattr(self, "_telegram_channel_search"):
            return ""
        return self._telegram_channel_search.text().strip()

    def _telegram_current_filter(self) -> str:
        if not hasattr(self, "_telegram_channel_filter_combo"):
            return "all"
        return normalize_channel_filter(self._telegram_channel_filter_combo.currentData())

    def _telegram_last_url_for_settings(self) -> str:
        return str(getattr(self, "_pending_telegram_url", "") or self._config.telegram_last_url or "")

    def _telegram_last_post_id_for_settings(self) -> str:
        if not getattr(self, "_pending_telegram_url", ""):
            return str(self._config.telegram_last_post_id or "")
        return str(
            getattr(self, "_current_telegram_post_id", "")
            or getattr(self, "_pending_telegram_post_id", "")
            or self._config.telegram_last_post_id
            or ""
        )

    def _telegram_last_search_for_settings(self) -> str:
        if not getattr(self, "_pending_telegram_url", ""):
            return str(self._config.telegram_last_search or "")
        return self._telegram_current_search()

    def _telegram_last_filter_for_settings(self) -> str:
        if not getattr(self, "_pending_telegram_url", ""):
            return str(self._config.telegram_last_filter or "all")
        return self._telegram_current_filter()

    def _telegram_side_panel_sizes_for_settings(self) -> tuple[int, ...]:
        sizes = list(getattr(self, "_telegram_side_panel_sizes", []) or [])
        if len(sizes) < 2:
            sizes = list(getattr(self._config, "telegram_side_panel_sizes", (1, 1)) or (1, 1))
        sizes = [max(0, int(item or 0)) for item in sizes[:2]]
        return tuple(sizes) if len(sizes) == 2 else (1, 1)

    def _apply_telegram_browser_preferences(self, url: str) -> None:
        same_channel = self._telegram_channel_key(url) == self._telegram_channel_key(self._config.telegram_last_url)
        if same_channel:
            if not self._pending_telegram_post_id:
                self._pending_telegram_post_id = self._config.telegram_last_post_id
            self._telegram_side_panel_visible = self._config.telegram_side_panel_visible
            self._telegram_side_panel_sizes = list(self._config.telegram_side_panel_sizes)
            self._set_telegram_search_text(self._config.telegram_last_search)
            self._set_telegram_filter_value(self._config.telegram_last_filter)
            return
        self._telegram_side_panel_visible = True
        self._telegram_side_panel_sizes = [1, 1]
        self._set_telegram_search_text("")
        self._set_telegram_filter_value("all")

    def _set_telegram_search_text(self, text: str) -> None:
        if not hasattr(self, "_telegram_channel_search"):
            return
        was_blocked = self._telegram_channel_search.blockSignals(True)
        self._telegram_channel_search.setText(str(text or ""))
        self._telegram_channel_search.blockSignals(was_blocked)

    def _set_telegram_filter_value(self, value: str) -> None:
        if not hasattr(self, "_telegram_channel_filter_combo"):
            return
        index = self._telegram_channel_filter_combo.findData(value)
        was_blocked = self._telegram_channel_filter_combo.blockSignals(True)
        self._telegram_channel_filter_combo.setCurrentIndex(index if index >= 0 else 0)
        self._telegram_channel_filter_combo.blockSignals(was_blocked)

    @staticmethod
    def _telegram_channel_key(url: str) -> str:
        return telegram_channel_key(url)

    def _telegram_video_ready(self, path: str) -> None:
        if self._telegram_open_result_is_stale():
            return
        self._telegram_channel_state.mark_opened(self._current_telegram_channel_item)
        self._refresh_telegram_channel_item_statuses()
        self._close_cache_dialog()
        self._open_local_video_path(path)

    def _open_local_video_path(self, path: str) -> None:
        self._stop_dubbing()
        self._reset_document_state_for_video()
        self._video_path = path
        self._auto_select_video_aspect_ratio()
        self._load_current_video_for_playback()
        self._show_video_output()
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

    def _queue_pending_telegram_channel_item(self, channel_item) -> None:
        if self._telegram_channel_item_auto_open_blocked(channel_item):
            return
        self._telegram_channel_state.pending_open_item_key = self._telegram_channel_item_key(channel_item)
        self.statusBar().showMessage(self._tr("msg_url_opening"))

    def _open_pending_telegram_channel_item(self) -> None:
        if self._telegram_is_busy() or self._url_is_opening():
            return
        key = str(getattr(self._telegram_channel_state, "pending_open_item_key", "") or "")
        if not key:
            return
        self._telegram_channel_state.pending_open_item_key = ""
        channel_item = self._telegram_channel_item_by_key(key)
        if channel_item is None or not getattr(channel_item, "has_video", True):
            return
        if self._telegram_channel_item_auto_open_blocked(channel_item):
            return
        self._open_telegram_channel_item(channel_item)

    def _telegram_channel_item_by_key(self, key: str):
        for item in getattr(self, "_telegram_channel_all_items", []):
            if self._telegram_channel_item_key(item) == key:
                return item
        for item in getattr(self, "_telegram_channel_items", []):
            if self._telegram_channel_item_key(item) == key:
                return item
        return None

    def _telegram_open_result_is_stale(self) -> bool:
        loading_key = str(getattr(self._telegram_channel_state, "loading_item_key", "") or "")
        pending_key = str(getattr(self._telegram_channel_state, "pending_open_item_key", "") or "")
        return bool(loading_key and pending_key and pending_key != loading_key)

    def _telegram_worker_failed(self, operation: str, message: str) -> None:
        detail = _repair_mojibake(message)
        if operation.endswith("_more"):
            self._telegram_auto_load_pending_before_post_id = ""
        if operation == "download":
            self._telegram_channel_state.mark_failed(self._current_telegram_channel_item)
            self._refresh_telegram_channel_item_statuses()
            if self._cache_dialog is not None:
                self._cache_dialog.mark_failed(detail)
        if operation in {"list_public", "list_public_more"} and not telegram_private_available():
            QMessageBox.warning(
                self,
                self._tr("open_url_error_title"),
                f"{detail}\n\n{self._tr('telegram_channel_public_login_unavailable')}",
            )
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
            status_key="status_telegram_channel_loading_auth",
        )

    def _telegram_worker_finished(self, worker) -> None:
        worker.deleteLater()
        if self._telegram_worker is worker:
            self._telegram_worker = None
            if not self._url_is_opening():
                self._set_telegram_opening_controls(True)
            if getattr(worker, "operation", "") != "download":
                self._telegram_channel_state.loading_item_key = ""
            QTimer.singleShot(0, self._open_pending_telegram_channel_item)

    def _telegram_is_busy(self) -> bool:
        worker = getattr(self, "_telegram_worker", None)
        return worker is not None and worker.isRunning()

    def _set_telegram_opening_controls(self, enabled: bool, *, keep_browser_tools: bool = False) -> None:
        if hasattr(self, "_open_url_button"):
            self._open_url_button.setEnabled(enabled)
        for widget_name in (
            "_telegram_channel_refresh_button",
            "_telegram_channel_remote_search_button",
            "_telegram_channel_load_more_button",
            "_telegram_channel_translate_button",
            "_telegram_channel_auto_open_check",
        ):
            widget = getattr(self, widget_name, None)
            if widget is not None:
                if keep_browser_tools and widget_name in {
                    "_telegram_channel_load_more_button",
                    "_telegram_channel_translate_button",
                }:
                    continue
                widget.setEnabled(enabled)
        login_button = getattr(self, "_telegram_channel_login_button", None)
        if login_button is not None:
            login_button.setEnabled(
                enabled and self._current_channel_provider() == "telegram" and telegram_private_available()
            )

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
        self._show_cache_dialog(cancel_callback=self._cancel_video_url_open)
        if isinstance(data, dict):
            self._cache_dialog.update_cache(data)
            status = str(data.get("status") or "")
            if status in {"downloading", "starting"}:
                provider = data.get("provider") or ""
                quality = data.get("quality") or ""
                self.statusBar().showMessage(f"{self._tr('cache_status_downloading')} {provider} {quality}".strip())

    def _telegram_download_progress_changed(self, data) -> None:
        worker = getattr(self, "_telegram_worker", None)
        if (
            worker is not None
            and getattr(worker, "operation", "") == "download"
            and getattr(worker, "_stop_requested", False)
        ):
            return
        self._show_cache_dialog(cancel_callback=self._cancel_telegram_download)
        if isinstance(data, dict):
            progress = {"provider": "telegram", **data}
        else:
            progress = {"provider": "telegram", "status": "downloading", "filename": str(data or "")}
        self._cache_dialog.update_cache(progress)

    def _show_cache_dialog(self, *, cancel_callback=None) -> None:
        if self._cache_dialog is None:
            dialog = CacheProgressDialog(self._ui_language(), self)
            self._cache_dialog = dialog
            if callable(cancel_callback):
                dialog.rejected.connect(cancel_callback)
            dialog.finished.connect(lambda _result, dialog=dialog: self._cache_dialog_finished(dialog))
            dialog.show()
            dialog.raise_()

    def _cache_dialog_finished(self, dialog) -> None:
        if self._cache_dialog is dialog:
            self._cache_dialog = None

    def _close_cache_dialog(self) -> None:
        if self._cache_dialog is not None:
            self._cache_dialog.accept()
            self._cache_dialog = None

    def _cancel_telegram_download(self) -> None:
        worker = getattr(self, "_telegram_worker", None)
        if worker is None or getattr(worker, "operation", "") != "download":
            return
        stop = getattr(worker, "stop", None)
        if callable(stop):
            stop()
        self._telegram_channel_state.loading_item_key = ""
        self._cache_dialog = None
        self.statusBar().showMessage(self._tr("status_telegram_channel_cancelled"))

    def _cancel_video_url_open(self) -> None:
        if not self._url_is_opening():
            return
        self._stop_video_url(wait_ms=1000)
        self._cache_dialog = None
        self.statusBar().showMessage(self._tr("video_error_open_cancelled"))

    def _video_url_resolved(self, source) -> None:
        self._close_cache_dialog()
        if self._telegram_open_result_is_stale():
            self._telegram_channel_state.loading_item_key = ""
            QTimer.singleShot(0, self._open_pending_telegram_channel_item)
            return
        self._telegram_channel_state.mark_opened(self._current_telegram_channel_item)
        self._refresh_telegram_channel_item_statuses()
        self._reset_document_state_for_video()
        self._video_path = source.playback_url
        self._auto_select_video_aspect_ratio(source)
        self._load_current_video_for_playback()
        self._show_video_output()
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
        self._telegram_channel_state.mark_failed(self._current_telegram_channel_item)
        self._refresh_telegram_channel_item_statuses()
        detail = _repair_mojibake(message)
        if self._cache_dialog is not None:
            self._cache_dialog.mark_failed(detail)
        if self._youtube_channel_item_open_failed():
            if self._media_stack.currentWidget() is not self._telegram_channel_view:
                self._return_to_telegram_channel_browser()
            self._telegram_channel_status.setText(detail)
            self.statusBar().showMessage(
                self._tr("youtube_channel_browser_ready").format(count=len(self._telegram_channel_all_items))
            )
            QTimer.singleShot(0, self._open_pending_telegram_channel_item)
            return
        if self._browser_video_url_should_fallback(detail):
            self._open_video_url_in_browser(str(self._last_video_url_request.get("url") or ""))
            QTimer.singleShot(0, self._open_pending_telegram_channel_item)
            return
        self.statusBar().showMessage(self._tr("status_open_url_failed"))
        self._handle_video_url_failure_action(detail)
        QTimer.singleShot(0, self._open_pending_telegram_channel_item)

    def _youtube_channel_item_open_failed(self) -> bool:
        request = getattr(self, "_last_video_url_request", None)
        return bool(
            isinstance(request, dict)
            and request.get("keep_telegram_context")
            and self._current_channel_provider() == "youtube"
            and getattr(self, "_current_telegram_channel_item", None) is not None
        )

    def _browser_video_url_should_fallback(self, detail: str) -> bool:
        request = getattr(self, "_last_video_url_request", None)
        return bool(
            isinstance(request, dict)
            and request.get("browser_fallback_on_unavailable")
            and self._video_url_failure_is_unrecoverable(detail)
            and self._can_open_video_url_in_browser(str(request.get("url") or ""))
        )

    def _video_url_finished(self) -> None:
        retry = getattr(self, "_pending_video_url_retry", None)
        if isinstance(retry, dict):
            self._pending_video_url_retry = None
            kwargs = {
                "keep_telegram_context": bool(retry.get("keep_telegram_context")),
                "full_cache_override": bool(retry.get("full_cache")),
            }
            if retry.get("browser_fallback_on_unavailable"):
                kwargs["browser_fallback_on_unavailable"] = True
            self._open_resolved_video_url(str(retry.get("url") or ""), **kwargs)
            return
        QTimer.singleShot(0, self._open_pending_telegram_channel_item)

    def _handle_video_url_failure_action(self, detail: str) -> None:
        request = getattr(self, "_last_video_url_request", None)
        if not isinstance(request, dict) or not request.get("url"):
            QMessageBox.warning(self, self._tr("open_url_error_title"), detail)
            return
        action = self._prompt_video_url_failure_action(detail, request)
        if action == "retry":
            self._retry_last_video_url_request()
        elif action == "lower_quality":
            self._retry_last_video_url_request(lower_quality=True)
        elif action == "toggle_cache":
            self._retry_last_video_url_request(toggle_cache=True)
        elif action == "browser":
            if not self._open_video_url_in_browser(str(request.get("url") or "")):
                QMessageBox.warning(self, self._tr("open_url_error_title"), detail)

    def _prompt_video_url_failure_action(self, detail: str, request: dict) -> str:
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Warning)
        box.setWindowTitle(self._tr("open_url_error_title"))
        box.setText(detail)
        unrecoverable = self._video_url_failure_is_unrecoverable(detail)
        box.setInformativeText(
            self._tr("open_video_url_unavailable_prompt") if unrecoverable else self._tr("open_video_url_retry_prompt")
        )
        retry_button = None
        if not unrecoverable:
            retry_button = box.addButton(self._tr("open_video_url_retry"), QMessageBox.AcceptRole)
        lower_button = None
        if not unrecoverable and self._lower_playback_quality_value(str(request.get("quality") or "")):
            lower_button = box.addButton(self._tr("open_video_url_retry_lower_quality"), QMessageBox.ActionRole)
        toggle_button = None
        if not unrecoverable and not self._source_filter_forces_video_url_full_cache():
            toggle_key = (
                "open_video_url_retry_stream"
                if bool(request.get("full_cache"))
                else "open_video_url_retry_cache"
            )
            toggle_button = box.addButton(self._tr(toggle_key), QMessageBox.ActionRole)
        browser_button = None
        if self._can_open_video_url_in_browser(str(request.get("url") or "")):
            browser_button = box.addButton(self._tr("open_video_url_open_browser"), QMessageBox.ActionRole)
        close_button = box.addButton(self._tr("close"), QMessageBox.RejectRole)
        box.setDefaultButton(retry_button or browser_button or close_button)
        box.exec()
        clicked = box.clickedButton()
        if retry_button is not None and clicked is retry_button:
            return "retry"
        if lower_button is not None and clicked is lower_button:
            return "lower_quality"
        if toggle_button is not None and clicked is toggle_button:
            return "toggle_cache"
        if browser_button is not None and clicked is browser_button:
            return "browser"
        if clicked is close_button:
            return ""
        return ""

    @staticmethod
    def _video_url_failure_is_unrecoverable(detail: str) -> bool:
        normalized = " ".join(str(detail or "").casefold().split())
        return any(
            marker in normalized
            for marker in (
                "this video is not available",
                "video unavailable",
                "private video",
                "has been removed",
                "account associated with this video has been terminated",
            )
        )

    def _retry_last_video_url_request(self, *, lower_quality: bool = False, toggle_cache: bool = False) -> None:
        request = getattr(self, "_last_video_url_request", None)
        if not isinstance(request, dict):
            return
        url = str(request.get("url") or "")
        if not url:
            return
        if lower_quality:
            lower_quality_value = self._lower_playback_quality_value(str(request.get("quality") or ""))
            if lower_quality_value:
                self._set_combo_data(self._playback_quality_combo, lower_quality_value)
                self._save_settings()
        full_cache = bool(request.get("full_cache"))
        if toggle_cache and not self._source_filter_forces_video_url_full_cache():
            full_cache = not full_cache
        if self._url_is_opening():
            self._pending_video_url_retry = {
                "url": url,
                "keep_telegram_context": bool(request.get("keep_telegram_context")),
                "full_cache": full_cache,
            }
            if request.get("browser_fallback_on_unavailable"):
                self._pending_video_url_retry["browser_fallback_on_unavailable"] = True
            self.statusBar().showMessage(self._tr("status_open_url_retry_pending"))
            return
        kwargs = {
            "keep_telegram_context": bool(request.get("keep_telegram_context")),
            "full_cache_override": full_cache,
        }
        if request.get("browser_fallback_on_unavailable"):
            kwargs["browser_fallback_on_unavailable"] = True
        self._open_resolved_video_url(url, **kwargs)

    @staticmethod
    def _lower_playback_quality_value(value: str) -> str:
        order = ["best", "1080p", "720p", "480p", "360p"]
        current = str(value or "").strip().lower()
        if current not in order:
            current = "720p"
        index = order.index(current)
        return order[index + 1] if index + 1 < len(order) else ""

    def _can_open_video_url_in_browser(self, url: str) -> bool:
        parsed = urlparse(str(url or "").strip())
        return parsed.scheme.lower() in {"http", "https"} and callable(
            getattr(getattr(self, "_video_placeholder", None), "setUrl", None)
        )

    def _open_video_url_in_browser(self, url: str) -> bool:
        if not self._can_open_video_url_in_browser(url):
            return False
        self._stop_dubbing()
        self._player.stop()
        self._reset_document_state_for_video()
        self._clear_active_telegram_channel_video()
        self._video_path = None
        self._runtime_media_path = ""
        self._video_placeholder.setUrl(QUrl(url))
        self._media_stack.setCurrentWidget(self._video_placeholder)
        self._source_label.setText(url)
        self.statusBar().showMessage(self._tr("open_video_url_browser_opened"))
        self._sync_media_browser_state()
        return True

    def _refresh_telegram_channel_item_statuses(self) -> None:
        list_widget = getattr(self, "_telegram_channel_list", None)
        if list_widget is None:
            return
        current_key = self._telegram_channel_item_key(
            self._telegram_channel_item_from_list_item(list_widget.currentItem())
        )
        self._filter_telegram_channel_items()
        if current_key:
            self._telegram_suppress_auto_open_selection = True
            try:
                self._select_telegram_channel_item_key(current_key)
            finally:
                self._telegram_suppress_auto_open_selection = False

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


class _VideoUrlDialog(QDialog):
    def __init__(
        self,
        recent_urls,
        *,
        full_cache: bool,
        force_full_cache: bool,
        quality: str,
        language_id: str | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._language_id = language_id
        self._force_full_cache = bool(force_full_cache)
        self.setWindowTitle(self._tr("open_video_url_title"))
        self.resize(640, 260)

        self._url_combo = QComboBox(self)
        self._url_combo.setEditable(True)
        self._url_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self._url_combo.lineEdit().setPlaceholderText(self._tr("open_video_url_label"))
        for url in list(recent_urls or []):
            text = str(url or "").strip()
            if text:
                self._url_combo.addItem(text, text)
        self._url_combo.editTextChanged.connect(self._refresh_preview)

        self._cache_combo = QComboBox(self)
        self._cache_combo.addItem(self._tr("open_video_url_cache_mode_cache"), "cache")
        self._cache_combo.addItem(self._tr("open_video_url_cache_mode_stream"), "stream")
        self._cache_combo.setCurrentIndex(0 if full_cache or self._force_full_cache else 1)
        if self._force_full_cache:
            self._cache_combo.setEnabled(False)

        self._preview = QLabel("", self)
        self._preview.setWordWrap(True)
        self._cache_hint = QLabel("", self)
        self._cache_hint.setWordWrap(True)

        form = QFormLayout()
        form.addRow(self._tr("open_video_url_label"), self._url_combo)
        form.addRow(self._tr("open_video_url_cache_mode"), self._cache_combo)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self._preview)
        layout.addWidget(self._cache_hint)
        layout.addWidget(buttons)

        self._cache_hint.setText(
            self._tr("open_video_url_forced_cache_hint").format(quality=quality)
            if self._force_full_cache
            else self._tr("open_video_url_cache_hint").format(quality=quality)
        )
        self._refresh_preview(self.url)

    @property
    def url(self) -> str:
        return self._url_combo.currentText().strip()

    @property
    def full_cache(self) -> bool:
        return self._force_full_cache or self._cache_combo.currentData() == "cache"

    def _refresh_preview(self, text: str) -> None:
        preflight = inspect_video_url(text)
        if not preflight.url:
            self._preview.setText(self._tr("open_video_url_preview_empty"))
            return
        if not preflight.supported:
            self._preview.setText(self._tr("open_video_url_preview_invalid"))
            return
        kind_key = {
            "direct_media": "open_video_url_kind_direct",
            "page": "open_video_url_kind_page",
            "network_stream": "open_video_url_kind_stream",
            "telegram_web": "open_video_url_kind_telegram_web",
            "private_telegram": "open_video_url_kind_telegram_private",
        }.get(preflight.source_kind, "open_video_url_kind_stream")
        resolver = (
            self._tr("open_video_url_resolver_ytdlp")
            if preflight.requires_ytdlp
            else self._tr("open_video_url_resolver_direct")
        )
        self._preview.setText(
            self._tr("open_video_url_preview").format(
                provider=preflight.provider or "-",
                kind=self._tr(kind_key),
                resolver=resolver,
            )
        )

    def _tr(self, key: str) -> str:
        from ai_player.core.i18n import ui_text

        return ui_text(key, self._language_id)


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
