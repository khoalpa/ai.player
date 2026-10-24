from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

from PySide6.QtCore import QRect, QSignalBlocker, QSize, Qt, QTimer, QUrl
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest
from PySide6.QtWidgets import (
    QApplication,
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
    QVBoxLayout,
)

from ai_player.adapters.media.document_reader import (
    create_text_document_transcript,
    document_filter,
    is_supported_document_path,
)
from ai_player.adapters.sources.telegram_channel import (
    TelegramChannelError,
    TelegramLoginConfig,
    delete_telegram_login_data,
    is_telegram_channel_url,
    load_telegram_login_config,
    telegram_channel_item_translation_text,
    telegram_private_available,
    validate_telegram_login_config,
)
from ai_player.adapters.sources.video_source import inspect_video_url, is_supported_video_url
from ai_player.adapters.sources.youtube_channel import (
    is_youtube_browse_url,
)
from ai_player.application.formats.transcript_source import load_transcript_entries as _load_transcript_entries
from ai_player.core.redaction import redact_secrets
from ai_player.ui.channel_browser import (
    channel_item_detail_lines,
    channel_item_height,
    channel_item_html,
    channel_item_media_kind,
    channel_item_summary_lines,
    current_channel_provider,
    filter_channel_items,
    last_channel_filter_for_settings,
    last_channel_post_id_for_settings,
    last_channel_search_for_settings,
    last_channel_url_for_settings,
    normalize_channel_filter,
    oldest_telegram_post_id,
    summary_excerpt,
    target_channel_row,
    telegram_channel_key,
    telegram_post_id_from_url,
    youtube_video_id_from_url,
)
from ai_player.ui.features.base import Feature
from ai_player.ui.player_window_utils import repair_mojibake as _repair_mojibake
from ai_player.ui.video_url_controller import (
    lower_playback_quality_value,
    video_url_failure_is_unrecoverable,
    video_url_open_kwargs,
    video_url_request_is_youtube_channel_item_failure,
    video_url_request_should_fallback_to_browser,
    video_url_retry_payload,
)
from ai_player.workers.player_window_workers import (
    DocumentTranscriptWorker,
    TelegramContentTranslationWorker,
)

TELEGRAM_ITEM_HTML_ROLE = Qt.ItemDataRole.UserRole.value + 10
TELEGRAM_BLACKLIST_BUTTON_ROLE = Qt.ItemDataRole.UserRole.value + 11
TELEGRAM_BLACKLIST_BUTTON_WIDTH = 88
TELEGRAM_BLACKLIST_BUTTON_HEIGHT = 30
TELEGRAM_BLACKLIST_BUTTON_MARGIN = 10
TELEGRAM_TRANSLATION_COLOR = "#0f766e"
VIDEO_SUBTITLE_DIR_NAMES = ("subtitles", "subtitle", "subs")
VIDEO_SUBTITLE_LANGUAGE_SUFFIXES = ("vi", "en", "ja", "jp", "ko", "zh", "zh-Hans", "zh-Hant")
TRANSCRIPT_SOURCE_EXTENSIONS = {".srt", ".vtt", ".txt"}
VIDEO_SOURCE_EXTENSIONS = {".mp4", ".mkv", ".avi", ".mov", ".webm", ".m4v", ".mpg", ".mpeg", ".ts"}


def _video_subtitle_candidates(video_path: str | Path) -> list[Path]:
    video = Path(video_path)
    if not video.name:
        return []
    candidates: list[Path] = [video.with_suffix(".srt")]
    candidates.extend(video.with_name(f"{video.stem}.{suffix}.srt") for suffix in VIDEO_SUBTITLE_LANGUAGE_SUFFIXES)
    for dirname in VIDEO_SUBTITLE_DIR_NAMES:
        subtitle_dir = video.parent / dirname
        candidates.append(subtitle_dir / f"{video.stem}.srt")
        candidates.extend(subtitle_dir / f"{video.stem}.{suffix}.srt" for suffix in VIDEO_SUBTITLE_LANGUAGE_SUFFIXES)

    seen: set[Path] = set()
    existing: list[Path] = []
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except OSError:
            resolved = candidate
        if resolved in seen or candidate.suffix.lower() != ".srt":
            continue
        seen.add(resolved)
        if candidate.exists() and candidate.is_file():
            existing.append(candidate)
    return existing


class PlayerSourceFeature(Feature):
    def _open_smart_source(self, *_args) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self.context.window,
            self.context.settings._tr("choose_source_title"),
            str(Path.home()),
            self.context.settings._tr("smart_open_file_filter"),
        )
        self.context.sources._open_smart_source_paths(paths)

    def _open_smart_source_prompt(self, *_args) -> None:
        text, accepted = QInputDialog.getText(
            self.context.window,
            self.context.settings._tr("choose_source_title"),
            self.context.settings._tr("smart_open_text_label"),
        )
        if accepted:
            self.context.sources._open_smart_source_text(text)

    def _open_smart_source_from_clipboard(self, *_args) -> None:
        clipboard = QApplication.clipboard()
        self.context.sources._open_smart_source_text(clipboard.text() if clipboard is not None else "")

    def _media_start_submit_quick_source(self, *_args) -> None:
        edit = self.context.get("_media_start_quick_source_edit", None)
        value = edit.text().strip() if edit is not None else ""
        if not value:
            self.context.window.statusBar().showMessage(self.context.settings._tr("media_start_quick_empty"))
            return
        self.context.sources._open_smart_source_text(value)
        if edit is not None:
            edit.clear()

    def _open_media_start_recent_source(self, source: str) -> None:
        value = str(source or "").strip()
        if value:
            self.context.sources._open_smart_source_text(value)

    def _media_start_mime_supported(self, mime_data) -> bool:
        if mime_data is None:
            return False
        if mime_data.hasUrls():
            for url in mime_data.urls():
                value = url.toLocalFile() if url.isLocalFile() else url.toString()
                if self.context.sources._smart_source_text_supported(value):
                    return True
        return bool(mime_data.hasText() and self.context.sources._smart_source_text_supported(mime_data.text()))

    def _open_media_start_mime_source(self, mime_data) -> bool:
        if mime_data is None:
            return False
        if mime_data.hasUrls():
            paths: list[str] = []
            text_sources: list[str] = []
            for url in mime_data.urls():
                value = url.toLocalFile() if url.isLocalFile() else url.toString()
                if not value:
                    continue
                if url.isLocalFile():
                    paths.append(value)
                else:
                    text_sources.append(value)
            if paths:
                self.context.sources._open_smart_source_paths(paths)
                return True
            if text_sources:
                self.context.sources._open_smart_source_text(text_sources[0])
                return True
        if mime_data.hasText():
            self.context.sources._open_smart_source_text(mime_data.text())
            return True
        return False

    def _smart_source_clipboard_text(self) -> str:
        clipboard = QApplication.clipboard()
        return str(clipboard.text() if clipboard is not None else "").strip()

    def _smart_source_text_supported(self, text: object) -> bool:
        value = str(text or "").strip().strip('"')
        if not value:
            return False
        if self.context.sources._smart_source_url_supported(value):
            return True
        return Path(value).expanduser().exists()

    def _smart_source_url_supported(self, text: str) -> bool:
        parsed = urlparse(str(text or "").strip())
        return parsed.scheme in {"http", "https", "tg"} and (
            is_supported_video_url(text) or is_telegram_channel_url(text) or is_youtube_browse_url(text)
        )

    def _open_smart_source_text(self, text: object) -> None:
        value = str(text or "").strip().strip('"')
        if not value:
            return
        if self.context.sources._smart_source_url_supported(value):
            self.context.layout._start_goal_workflow("url", lambda: self.context.sources._open_url_from_browser(value))
            return
        path = Path(value).expanduser()
        if path.exists():
            self.context.sources._open_smart_source_paths([str(path)])
            return
        QMessageBox.warning(
            self.context.window,
            self.context.settings._tr("app_title"),
            self.context.settings._tr("smart_open_unsupported"),
        )

    def _open_smart_source_paths(self, paths: list[str] | tuple[str, ...]) -> None:
        selected = [Path(path) for path in paths if str(path or "").strip()]
        selected = [path for path in selected if path.exists() and path.is_file()]
        if not selected:
            return

        timed_transcripts = [path for path in selected if path.suffix.lower() in {".srt", ".vtt"}]
        text_transcripts = [path for path in selected if path.suffix.lower() == ".txt"]
        transcript_candidates = [*timed_transcripts]
        if len(selected) > 1:
            transcript_candidates.extend(text_transcripts)

        transcript_path = transcript_candidates[0] if transcript_candidates else None
        documents = [
            path
            for path in selected
            if is_supported_document_path(path) and (path not in transcript_candidates or len(selected) == 1)
        ]
        videos = [
            path
            for path in selected
            if path not in documents
            and path not in transcript_candidates
            and (path.suffix.lower() in VIDEO_SOURCE_EXTENSIONS or not is_supported_document_path(path))
        ]

        if videos:
            video_path = videos[0]
            self.context.layout._start_goal_workflow(
                "video",
                lambda: self.context.sources._open_local_video_path(
                    str(video_path),
                    prompt_for_subtitle=transcript_path is None,
                    subtitle_path=transcript_path,
                ),
            )
            return

        if documents:
            document_path = documents[0]
            self.context.sources._pending_smart_transcript_path = (
                str(transcript_path) if transcript_path is not None else ""
            )
            self.context.layout._start_goal_workflow(
                "document", lambda: self.context.sources._load_document(str(document_path))
            )
            return

        if transcript_path is not None:
            self.context.sources._apply_transcript_path(transcript_path)

    def _open_video(self, *_args) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self.context.window,
            self.context.settings._tr("choose_video_title"),
            str(Path.home()),
            self.context.settings._tr("video_file_filter"),
        )
        if not path:
            return
        if is_supported_document_path(path):
            self.context.sources._load_document(path)
            return

        self.context.sources._open_local_video_path(path, prompt_for_subtitle=True)

    def _open_video_with_subtitle(self, *_args) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self.context.window,
            self.context.settings._tr("choose_video_title"),
            str(Path.home()),
            self.context.settings._tr("video_file_filter"),
        )
        if not path:
            return
        if is_supported_document_path(path):
            self.context.sources._load_document(path)
            return
        subtitle_path = self.context.sources._choose_video_subtitle_file(Path(path).parent)
        self.context.sources._open_local_video_path(path, prompt_for_subtitle=False, subtitle_path=subtitle_path)

    def _prompt_video_subtitle(self, video_path: Path) -> Path | None:
        candidates = _video_subtitle_candidates(video_path)
        if not candidates:
            return None
        return self.context.sources._confirm_video_subtitle_path(video_path, candidates)

    def _confirm_video_subtitle_path(self, video_path: Path, candidates: list[Path]) -> Path | None:
        subtitle_path = candidates[0]
        box = QMessageBox(self.context.window)
        box.setWindowTitle(self.context.settings._tr("video_subtitle_found_title"))
        box.setText(
            self.context.settings._tr("video_subtitle_found_message").format(
                video=video_path.name,
                subtitle=str(subtitle_path),
            )
        )
        use_button = box.addButton(self.context.settings._tr("video_subtitle_use_found"), QMessageBox.AcceptRole)
        choose_button = box.addButton(self.context.settings._tr("video_subtitle_choose_other"), QMessageBox.ActionRole)
        box.addButton(self.context.settings._tr("video_subtitle_skip"), QMessageBox.RejectRole)
        box.exec()
        clicked = box.clickedButton()
        if clicked == use_button:
            return subtitle_path
        if clicked == choose_button:
            return self.context.sources._choose_video_subtitle_file(video_path.parent)
        return None

    def _choose_video_subtitle_file(self, directory: Path | None = None) -> Path | None:
        start_dir = str(directory or Path.home())
        path, _ = QFileDialog.getOpenFileName(
            self.context.window,
            self.context.settings._tr("choose_video_subtitle_title"),
            start_dir,
            self.context.settings._tr("srt_file_filter"),
        )
        return Path(path) if path else None

    def _apply_video_subtitle_path(self, path: str | Path, *, save: bool = True) -> bool:
        subtitle_path = Path(path)
        if (
            subtitle_path.suffix.lower() not in TRANSCRIPT_SOURCE_EXTENSIONS
            or not subtitle_path.exists()
            or not subtitle_path.is_file()
        ):
            QMessageBox.warning(
                self.context.window,
                self.context.settings._tr("video_subtitle_invalid_title"),
                self.context.settings._tr("video_subtitle_invalid_message").format(path=subtitle_path),
            )
            return False
        try:
            entries = _load_transcript_entries(
                str(subtitle_path),
                max(1, int(self.context.config.segment_seconds)),
                self.context.config.gui_language,
            )
        except Exception as exc:
            QMessageBox.warning(
                self.context.window,
                self.context.settings._tr("video_subtitle_invalid_title"),
                self.context.settings._tr("video_subtitle_invalid_detail").format(
                    detail=_repair_mojibake(redact_secrets(exc))
                ),
            )
            return False
        if not entries:
            QMessageBox.warning(
                self.context.window,
                self.context.settings._tr("video_subtitle_invalid_title"),
                self.context.settings._tr("video_subtitle_empty_message").format(path=subtitle_path),
            )
            return False
        return self.context.sources._apply_transcript_path(subtitle_path, save=save, count=len(entries))

    def _apply_transcript_path(self, path: str | Path, *, save: bool = True, count: int | None = None) -> bool:
        transcript_path = Path(path)
        if transcript_path.suffix.lower() not in TRANSCRIPT_SOURCE_EXTENSIONS:
            return False
        self.context.layout._transcript_path_edit.setText(str(transcript_path))
        self.context.sources._invalidate_subtitle_entries()
        self.context.settings._set_combo_data(self.context.layout._audio_source_combo, "transcript")
        self.context.sources._sync_audio_source_controls()
        if save:
            self.context.settings._queue_save_settings()
        message_key = "status_video_subtitle_attached" if count is not None else "status_selected_transcript"
        message = (
            self.context.settings._tr(message_key).format(path=transcript_path, count=count)
            if count is not None
            else self.context.settings._tr(message_key).format(path=transcript_path)
        )
        self.context.window.statusBar().showMessage(message)
        if self.context.has("_refresh_next_action_panel"):
            self.context.transcript._refresh_next_action_panel()
        return True

    def _open_document(self, *_args) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self.context.window,
            self.context.settings._tr("choose_document_title"),
            str(Path.home()),
            document_filter(),
        )
        if not path:
            return
        self.context.sources._load_document(path)

    def _load_document(self, path: str, start_dubbing: bool = True) -> None:
        if (
            self.context.lifecycle.workers.document_worker is not None
            and self.context.lifecycle.workers.document_worker.isRunning()
        ):
            QMessageBox.information(
                self.context.window,
                self.context.settings._tr("app_title"),
                self.context.settings._tr("msg_document_opening"),
            )
            return
        self.context.sources._clear_active_telegram_channel_video()
        self.context.dubbing._stop_dubbing()
        self.context.layout._player.stop()
        self.context.media.document.editor_active = False
        self.context.layout._document_view.setReadOnly(True)
        self.context.layout._document_view.setPlainText(self.context.settings._tr("status_open_document_loading"))
        self.context.layout._media_stack.setCurrentWidget(self.context.layout._document_view)
        self.context.layout._source_label.setText(path)
        self.context.sources._set_document_opening_controls(False)
        self.context.window.statusBar().showMessage(self.context.settings._tr("status_open_document_loading"))
        worker = DocumentTranscriptWorker(
            path,
            start_dubbing,
            seconds_per_segment=6,
            language_id=self.context.config.gui_language,
            parent=self.context.window,
        )
        self.context.lifecycle.workers.begin_document(worker)
        worker.ready.connect(self.context.sources._document_transcript_ready)
        worker.failed.connect(self.context.sources._document_transcript_failed)
        worker.finished.connect(lambda worker=worker: self.context.sources._document_worker_finished(worker))
        worker.start()

    def _document_transcript_ready(self, transcript, start_dubbing: bool) -> None:
        self.context.sources._apply_document_transcript(transcript, start_dubbing)

    def _apply_document_transcript(self, transcript, start_dubbing: bool = True) -> None:
        try:
            total_duration_ms = sum(page.duration_seconds for page in transcript.pages) * 1000
        except Exception as exc:
            QMessageBox.warning(
                self.context.window, self.context.settings._tr("open_document_error_title"), redact_secrets(exc)
            )
            self.context.window.statusBar().showMessage(self.context.settings._tr("status_open_document_failed"))
            return

        self.context.media._set_document_mode(True, total_duration_ms, transcript.pages)
        self.context.channel_browser._video_path = str(transcript.source_path)
        self.context.channel_browser._video_source_http_headers = {}
        self.context.layout._transcript_path_edit.setText(str(transcript.transcript_path))
        self.context.sources._invalidate_subtitle_entries()
        self.context.settings._set_combo_data(self.context.layout._audio_source_combo, "transcript")
        pending_transcript = str(self.context.get("_pending_smart_transcript_path", "") or "")
        self.context.sources._pending_smart_transcript_path = ""
        if pending_transcript:
            self.context.sources._apply_transcript_path(pending_transcript, save=False)
        self.context.transcript._clear_transcript()
        self.context.layout._source_label.setText(str(transcript.source_path))
        self.context.settings._save_settings()
        self.context.window.statusBar().showMessage(
            self.context.settings._tr("status_opened_document").format(
                title=transcript.title,
                count=transcript.segment_count,
            )
        )
        if start_dubbing and self.context.media.playback.dubbing_auto_enabled:
            self.context.layout._dub_button.setChecked(True)
            self.context.dubbing._start_dubbing()

    def _document_transcript_failed(self, message: str) -> None:
        QMessageBox.warning(self.context.window, self.context.settings._tr("open_document_error_title"), message)
        self.context.window.statusBar().showMessage(self.context.settings._tr("status_open_document_failed"))

    def _document_worker_finished(self, worker=None) -> None:
        worker = worker or self.context.lifecycle.workers.document_worker
        if worker is not None and self.context.lifecycle.workers.finish_document(worker):
            self.context.lifecycle.workers.delete_worker(worker)
        self.context.sources._set_document_opening_controls(True)

    def _set_document_opening_controls(self, enabled: bool) -> None:
        if self.context.has("_open_file_button"):
            self.context.layout._open_file_button.setEnabled(enabled)
        if self.context.has("_open_document_button"):
            self.context.layout._open_document_button.setEnabled(enabled)
        if self.context.has("_sync_open_source_menu_enabled"):
            self.context.layout._sync_open_source_menu_enabled()

    def _open_video_url(self, *_args) -> None:
        dialog = _VideoUrlDialog(
            self.context.sources._video_url_recent_urls_for_settings(),
            full_cache=self.context.source_progress._effective_video_url_full_cache(),
            force_full_cache=self.context.source_progress._source_filter_forces_video_url_full_cache(),
            quality=self.context.user_guide._combo_text(self.context.layout._playback_quality_combo),
            language_id=self.context.settings._ui_language(),
            parent=self.context.window,
        )
        if dialog.exec() != QDialog.Accepted:
            return
        url = dialog.url
        preflight = inspect_video_url(url)
        if not preflight.supported:
            QMessageBox.warning(
                self.context.window,
                self.context.settings._tr("app_title"),
                self.context.settings._tr("msg_invalid_url"),
            )
            return
        if self.context.sources._url_is_opening():
            QMessageBox.information(
                self.context.window,
                self.context.settings._tr("app_title"),
                self.context.settings._tr("msg_url_opening"),
            )
            return

        if is_telegram_channel_url(url):
            self.context.sources._remember_video_url(url)
            self.context.channel_flow._start_telegram_channel_flow(url)
            return
        if is_youtube_browse_url(url):
            self.context.sources._remember_video_url(url)
            self.context.channel_flow._start_youtube_channel_flow(url)
            return

        self.context.sources._open_resolved_video_url(url, full_cache_override=dialog.full_cache)

    def _open_url_from_browser(self, url: str) -> None:
        url = str(url or "").strip()
        if not url:
            return
        if self.context.sources._url_is_opening() or self.context.sources._telegram_is_busy():
            self.context.window.statusBar().showMessage(self.context.settings._tr("msg_url_opening"))
            return
        if is_telegram_channel_url(url):
            self.context.channel_flow._start_telegram_channel_flow(url)
            return
        if is_youtube_browse_url(url):
            self.context.channel_flow._start_youtube_channel_flow(url)
            return
        if is_supported_video_url(url):
            self.context.sources._open_resolved_video_url(url, browser_fallback_on_unavailable=True)

    def _open_resolved_video_url(
        self,
        url: str,
        *,
        keep_telegram_context: bool = False,
        full_cache_override: bool | None = None,
        browser_fallback_on_unavailable: bool = False,
    ) -> None:
        if not keep_telegram_context and not is_telegram_channel_url(url):
            self.context.sources._clear_active_telegram_channel_video()
        self.context.sources._remember_video_url(url)
        forced_full_cache = self.context.source_progress._source_filter_forces_video_url_full_cache()
        full_cache = self.context.source_progress._effective_video_url_full_cache()
        if not full_cache and full_cache_override is None and inspect_video_url(url).requires_ytdlp:
            full_cache = True
        if full_cache_override is not None and not forced_full_cache:
            full_cache = bool(full_cache_override)
        self.context.window.statusBar().showMessage(
            self.context.settings._tr("status_open_url_source_filter_cache")
            if forced_full_cache
            else self.context.settings._tr("status_open_url_cache")
            if full_cache
            else self.context.settings._tr("status_open_url_stream")
        )
        self.context.dubbing._stop_dubbing()
        self.context.sources._reset_document_state_for_video()
        self.context.settings._save_settings()
        if self.context.media.playback.cache_dialog is not None:
            self.context.media.playback.cache_dialog.close()
            self.context.media.playback.cache_dialog = None
        quality_label = self.context.user_guide._combo_text(self.context.layout._playback_quality_combo)
        if forced_full_cache:
            status_key = "status_open_url_source_filter_quality"
        elif full_cache:
            status_key = "status_open_url_quality"
        else:
            status_key = "status_open_url_stream_quality"
        self.context.window.statusBar().showMessage(self.context.settings._tr(status_key).format(quality=quality_label))
        self.context.sources._last_video_url_request = {
            "url": url,
            "full_cache": full_cache,
            "quality": self.context.config.playback_video_quality,
            "keep_telegram_context": keep_telegram_context,
            "browser_fallback_on_unavailable": browser_fallback_on_unavailable,
        }
        self.context.sources._video_url_stream_source = None
        self.context.source_progress._set_cache_play_now_enabled(False)
        self.context.sources.url_controller.start(
            url,
            self.context.config.playback_video_quality,
            full_cache=full_cache,
            cache_dir=self.context.config.video_cache_dir,
            play_after_cache_percent=self.context.config.video_url_play_after_cache_percent if full_cache else 0,
            language_id=self.context.config.gui_language,
        )

    def _choose_video_cache_dir(self) -> None:
        current = (
            self.context.layout._video_cache_dir_edit.text().strip()
            if self.context.has("_video_cache_dir_edit")
            else ""
        )
        start_dir = current or str(Path.home())
        selected = QFileDialog.getExistingDirectory(
            self.context.window,
            self.context.settings._tr("video_cache_dir_choose"),
            start_dir,
        )
        if not selected or not self.context.has("_video_cache_dir_edit"):
            return
        self.context.layout._video_cache_dir_edit.setText(selected)
        self.context.settings._queue_save_settings()
        self.context.window.statusBar().showMessage(
            self.context.settings._tr("status_video_cache_dir_selected").format(path=selected)
        )

    def _reset_video_cache_dir(self) -> None:
        if not self.context.has("_video_cache_dir_edit"):
            return
        self.context.layout._video_cache_dir_edit.clear()
        self.context.settings._queue_save_settings()
        self.context.window.statusBar().showMessage(self.context.settings._tr("status_video_cache_dir_default"))

    def _remember_video_url(self, url: str) -> None:
        normalized = str(url or "").strip()
        if not normalized:
            return
        history = [item for item in self.context.sources._video_url_recent_urls_for_settings() if item != normalized]
        self.context.sources._video_url_recent_urls = tuple([normalized, *history][:20])
        if self.context.has("_refresh_media_start_context"):
            self.context.layout._refresh_media_start_context()

    def _video_url_recent_urls_for_settings(self) -> tuple[str, ...]:
        return tuple(self.context.get("_video_url_recent_urls", self.context.config.video_url_recent_urls) or ())

    def _populate_telegram_channel_browser(self, items) -> None:
        self.context.sources.channel.set_visible_items(items)
        list_widget = self.context.layout._telegram_channel_list
        self.context.sources._telegram_populating_browser = True
        blocker = QSignalBlocker(list_widget)
        try:
            list_widget.clear()
            for index, channel_item in enumerate(self.context.sources.channel.channel_items):
                label = self.context.sources._telegram_channel_item_label(channel_item)
                item = QListWidgetItem(label)
                item.setToolTip(str(getattr(channel_item, "url", "") or "").strip())
                item.setSizeHint(QSize(0, channel_item_height(label)))
                item.setData(Qt.ItemDataRole.UserRole, index)
                item.setData(
                    TELEGRAM_ITEM_HTML_ROLE,
                    self.context.sources._telegram_channel_item_html(channel_item, summary=True),
                )
                button_key = (
                    "telegram_unblacklist_button"
                    if self.context.sources.channel.is_blacklisted(channel_item)
                    else "telegram_blacklist_button"
                )
                item.setData(TELEGRAM_BLACKLIST_BUTTON_ROLE, self.context.settings._tr(button_key))
                self.context.sources._set_telegram_item_thumbnail(item, channel_item, index)
                list_widget.addItem(item)
            if self.context.sources.channel.channel_items:
                target_row = target_channel_row(
                    self.context.get("_telegram_channel_items", []),
                    self.context.get("_pending_telegram_post_id", ""),
                )
                list_widget.setCurrentRow(target_row if target_row >= 0 else 0)
            self.context.sources._telegram_channel_selection_changed(list_widget.currentItem(), None)
        finally:
            del blocker
            self.context.sources._telegram_populating_browser = False
        ready_key = (
            "youtube_channel_browser_ready"
            if self.context.sources._current_channel_provider() == "youtube"
            else "telegram_channel_browser_ready"
        )
        self.context.layout._telegram_channel_status.setText(
            self.context.settings._tr(ready_key).format(count=len(self.context.sources.channel.channel_all_items))
        )
        self.context.layout._telegram_channel_login_button.setEnabled(
            self.context.sources._current_channel_provider() == "telegram" and telegram_private_available()
        )

    def _telegram_channel_item_label(self, channel_item) -> str:
        return "\n".join(self.context.sources._telegram_channel_item_summary_lines(channel_item))

    def _telegram_channel_item_summary_lines(self, channel_item) -> list[str]:
        post_id = str(getattr(channel_item, "post_id", "") or "").strip()
        source_text = telegram_channel_item_translation_text(channel_item)
        translated = self.context.sources._telegram_channel_item_translation(channel_item)
        return channel_item_summary_lines(
            channel_item,
            kind_label=self.context.sources._telegram_media_kind_label(channel_item),
            post_id_label=self.context.settings._tr("telegram_channel_item_post_id").format(post_id=post_id)
            if post_id
            else "",
            status_label=self.context.sources._telegram_item_status_label(channel_item),
            source_text=source_text,
            translated_text=translated,
            format_bytes=self.context.runtime._format_bytes,
        )

    def _telegram_channel_item_lines(self, channel_item) -> list[str]:
        post_id = str(getattr(channel_item, "post_id", "") or "").strip()
        source_text = telegram_channel_item_translation_text(channel_item)
        return channel_item_detail_lines(
            channel_item,
            kind_label=self.context.sources._telegram_media_kind_label(channel_item),
            post_id_label=self.context.settings._tr("telegram_channel_item_post_id").format(post_id=post_id)
            if post_id
            else "",
            status_label=self.context.sources._telegram_item_status_label(channel_item),
            source_text=source_text,
            translated_text=self.context.sources._telegram_channel_item_translation(channel_item),
            format_bytes=self.context.runtime._format_bytes,
            format_line=lambda key, values: self.context.settings._tr(key).format(**values),
        )

    def _telegram_channel_item_html(self, channel_item, *, summary: bool = False) -> str:
        translated = self.context.sources._telegram_channel_item_translation(channel_item)
        source_text = telegram_channel_item_translation_text(channel_item)
        lines = (
            self.context.sources._telegram_channel_item_summary_lines(channel_item)
            if summary
            else self.context.sources._telegram_channel_item_lines(channel_item)
        )
        return channel_item_html(
            lines,
            translated_text=translated,
            source_text=source_text,
            translation_color=TELEGRAM_TRANSLATION_COLOR,
        )

    @staticmethod
    def _telegram_summary_excerpt(value: str, *, max_chars: int = 220) -> str:
        return summary_excerpt(value, max_chars=max_chars)

    def _set_telegram_channel_items(self, items) -> None:
        self.context.sources.channel.replace_items(items)
        self.context.sources._filter_telegram_channel_items()

    def _append_telegram_channel_items(self, items) -> None:
        self.context.sources.channel.append_unique_items(items)
        self.context.sources._filter_telegram_channel_items()

    def _filter_telegram_channel_items(self, *_args) -> None:
        all_items = list(self.context.get("_telegram_channel_all_items", []))
        media_filter = "all"
        if self.context.has("_telegram_channel_filter_combo"):
            media_filter = str(self.context.layout._telegram_channel_filter_combo.currentData() or "all")
        query = ""
        if self.context.has("_telegram_channel_search"):
            query = self.context.layout._telegram_channel_search.text()
        filtered = filter_channel_items(
            all_items,
            media_filter=media_filter,
            query=query,
            is_blacklisted=self.context.sources.channel.is_blacklisted,
            translation_for_item=self.context.sources._telegram_channel_item_translation,
        )
        self.context.sources._populate_telegram_channel_browser(filtered)

    def _telegram_search_changed(self, *_args) -> None:
        self.context.sources._filter_telegram_channel_items()
        self.context.settings._queue_save_settings()

    def _telegram_filter_changed(self, *_args) -> None:
        self.context.sources._filter_telegram_channel_items()
        self.context.settings._queue_save_settings()

    def _handle_telegram_blacklist_button_event(self, event, *, activate: bool) -> bool:
        list_widget = self.context.get("_telegram_channel_list", None)
        if list_widget is None:
            return False
        position = event.position().toPoint() if hasattr(event, "position") else event.pos()
        list_item = list_widget.itemAt(position)
        if list_item is None:
            return False
        if not self.context.sources._telegram_blacklist_button_rect(list_widget.visualItemRect(list_item)).contains(
            position
        ):
            return False
        if activate:
            channel_item = self.context.sources._telegram_channel_item_from_list_item(list_item)
            self.context.sources._toggle_telegram_blacklist_item(channel_item)
        return True

    @staticmethod
    def _telegram_blacklist_button_rect(row_rect: QRect) -> QRect:
        x = row_rect.right() - TELEGRAM_BLACKLIST_BUTTON_WIDTH - TELEGRAM_BLACKLIST_BUTTON_MARGIN
        y = row_rect.top() + TELEGRAM_BLACKLIST_BUTTON_MARGIN
        return QRect(x, y, TELEGRAM_BLACKLIST_BUTTON_WIDTH, TELEGRAM_BLACKLIST_BUTTON_HEIGHT)

    def _toggle_telegram_blacklist_item(self, channel_item) -> None:
        if channel_item is None:
            return
        item_key = self.context.sources._telegram_channel_item_key(channel_item)
        content_key = self.context.sources.channel.content_key(channel_item)
        if not item_key and not content_key:
            return
        if self.context.sources.channel.is_blacklisted(channel_item):
            if self.context.sources.channel.unblacklist_item(channel_item):
                self.context.window.statusBar().showMessage(self.context.settings._tr("status_telegram_unblacklisted"))
        elif self.context.sources.channel.blacklist_item(channel_item):
            if self.context.sources.channel.pending_open_item_key == item_key:
                self.context.sources.channel.pending_open_item_key = ""
            self.context.window.statusBar().showMessage(self.context.settings._tr("status_telegram_blacklisted"))
        self.context.settings._queue_save_settings()
        self.context.sources._filter_telegram_channel_items()

    @staticmethod
    def _telegram_post_id_from_url(url: str) -> str:
        return telegram_post_id_from_url(url)

    def _telegram_channel_selection_changed(self, current, _previous=None) -> None:
        channel_item = self.context.sources._telegram_channel_item_from_list_item(current)
        if channel_item is None:
            self.context.layout._telegram_channel_preview.clear()
            self.context.sources._clear_telegram_channel_thumbnail()
            self.context.layout._telegram_channel_open_button.setEnabled(False)
            return
        self.context.layout._telegram_channel_preview.setHtml(
            self.context.sources._telegram_channel_item_html(channel_item, summary=False)
        )
        current_key = self.context.sources._telegram_channel_item_key(channel_item)
        active_key = self.context.sources._telegram_channel_item_key_values(
            self.context.sources.channel.current_post_id, self.context.sources.channel.current_url
        )
        active_video_visible = (
            current_key
            and current_key == active_key
            and self.context.channel_browser._telegram_video_output_is_visible()
        )
        if not active_video_visible:
            self.context.sources._show_telegram_channel_thumbnail(channel_item)
        self.context.layout._telegram_channel_open_button.setEnabled(bool(getattr(channel_item, "has_video", True)))
        if not getattr(channel_item, "has_video", True):
            if self.context.channel_browser._video_widget_in_telegram_media():
                self.context.layout._player.stop()
            if self.context.sources._telegram_is_busy() or self.context.sources._url_is_opening():
                self.context.sources.channel.pending_open_item_key = current_key
            return
        self.context.sources._maybe_auto_open_telegram_video(channel_item)

    def _maybe_auto_open_telegram_video(self, channel_item) -> None:
        if not self.context.sources._telegram_auto_open_enabled():
            return
        if self.context.get("_telegram_populating_browser", False):
            return
        if self.context.get("_telegram_suppress_auto_open_selection", False):
            return
        if self.context.get("_telegram_selection_auto_opening", False):
            return
        if not getattr(channel_item, "has_video", True):
            return
        if self.context.sources._telegram_channel_item_auto_open_blocked(channel_item):
            return
        if self.context.sources._telegram_is_busy() or self.context.sources._url_is_opening():
            self.context.sources._queue_pending_telegram_channel_item(channel_item)
            return
        current_key = self.context.sources._telegram_channel_item_key(channel_item)
        active_key = self.context.sources._telegram_channel_item_key_values(
            self.context.sources.channel.current_post_id, self.context.sources.channel.current_url
        )
        if (
            current_key
            and current_key == active_key
            and self.context.channel_browser._telegram_video_output_is_visible()
        ):
            return
        self.context.sources._telegram_selection_auto_opening = True
        try:
            self.context.sources.channel.pending_autoplay = True
            self.context.sources._open_telegram_channel_item(channel_item)
        finally:
            self.context.sources._telegram_selection_auto_opening = False

    def _telegram_channel_item_auto_open_blocked(self, channel_item) -> bool:
        status = self.context.sources.channel.item_status(channel_item)
        return status in {"failed", "loading", "queued"} or self.context.sources.channel.is_blacklisted(channel_item)

    def _telegram_load_more_toggled(self, enabled: bool) -> None:
        if enabled:
            self.context.sources._maybe_auto_load_more_telegram_channel()

    def _telegram_channel_scroll_changed(self, *_args) -> None:
        self.context.sources._maybe_auto_load_more_telegram_channel()

    def _maybe_auto_load_more_telegram_channel(self) -> None:
        button = self.context.get("_telegram_channel_load_more_button", None)
        if button is None or not button.isChecked():
            return
        if self.context.sources._telegram_is_busy() or self.context.sources._url_is_opening():
            return
        scroll_bar = self.context.layout._telegram_channel_list.verticalScrollBar()
        if scroll_bar.maximum() <= 0:
            return
        threshold = max(24, scroll_bar.pageStep())
        if scroll_bar.value() < scroll_bar.maximum() - threshold:
            return
        cursor = (
            str(getattr(self.context.sources.channel, "channel_continuation", "") or "")
            if self.context.sources._current_channel_provider() == "youtube"
            else self.context.sources._oldest_telegram_post_id()
        )
        if not cursor:
            return
        if cursor == self.context.get("_telegram_auto_load_pending_before_post_id", ""):
            return
        self.context.sources.channel.auto_load_pending_before_post_id = cursor
        self.context.sources._load_more_current_telegram_channel()

    def _telegram_translation_toggled(self, enabled: bool) -> None:
        if enabled:
            self.context.sources._translate_current_telegram_channel()
            return
        worker = self.context.get("_telegram_translation_worker", None)
        if worker is not None and worker.isRunning():
            worker.stop()

    def _maybe_auto_translate_telegram_channel(self) -> None:
        button = self.context.get("_telegram_channel_translate_button", None)
        if button is not None and button.isChecked():
            self.context.sources._translate_current_telegram_channel(auto=True)

    def _translate_current_telegram_channel(self, *args, auto: bool = False) -> None:
        if (
            self.context.lifecycle.workers.telegram_translation_worker is not None
            and self.context.lifecycle.workers.telegram_translation_worker.isRunning()
        ):
            if not auto:
                self.context.window.statusBar().showMessage(
                    self.context.settings._tr("status_telegram_translation_loading")
                )
            return
        items = self.context.sources._telegram_channel_items_to_translate()
        if not items:
            if not auto:
                self.context.window.statusBar().showMessage(
                    self.context.settings._tr("telegram_channel_no_text_to_translate")
                )
            return

        self.context.window.statusBar().showMessage(self.context.settings._tr("status_telegram_translation_loading"))
        worker = TelegramContentTranslationWorker(
            self.context.settings._current_runtime_config(),
            items,
            language_id=self.context.config.gui_language,
            parent=self.context.window,
        )
        self.context.lifecycle.workers.telegram_translation_worker = worker
        worker.ready.connect(self.context.sources._telegram_translation_ready)
        worker.failed.connect(self.context.sources._telegram_translation_failed)
        worker.finished.connect(self.context.sources._telegram_translation_worker_finished)
        worker.start()

    def _telegram_channel_items_to_translate(self) -> list[object]:
        return self.context.sources.channel.items_to_translate(telegram_channel_item_translation_text)

    def _telegram_translation_ready(self, results) -> None:
        current_key = self.context.sources._telegram_channel_item_key(
            self.context.sources._telegram_channel_item_from_list_item(
                self.context.layout._telegram_channel_list.currentItem()
            )
        )
        count = 0
        for post_id, url, translated in list(results or []):
            if self.context.sources.channel.store_translation(post_id, url, translated):
                count += 1
        self.context.sources._filter_telegram_channel_items()
        if current_key:
            self.context.sources._select_telegram_channel_item_key(current_key)
        self.context.window.statusBar().showMessage(
            self.context.settings._tr("status_telegram_translation_ready").format(count=count)
        )

    def _telegram_translation_failed(self, message: str) -> None:
        QMessageBox.warning(
            self.context.window, self.context.settings._tr("open_url_error_title"), _repair_mojibake(str(message))
        )
        self.context.window.statusBar().showMessage(self.context.settings._tr("status_telegram_translation_failed"))

    def _telegram_translation_worker_finished(self) -> None:
        worker = self.context.window.sender()
        if worker is not None:
            worker.deleteLater()
        if self.context.lifecycle.workers.telegram_translation_worker is worker:
            self.context.lifecycle.workers.telegram_translation_worker = None
            self.context.sources._set_telegram_translation_controls(
                not self.context.sources._telegram_is_busy() and not self.context.sources._url_is_opening()
            )

    def _set_telegram_translation_controls(self, enabled: bool) -> None:
        button = self.context.get("_telegram_channel_translate_button", None)
        if button is not None:
            button.setEnabled(enabled)

    def _telegram_channel_item_translation(self, channel_item) -> str:
        return self.context.sources.channel.item_translation(channel_item)

    def _telegram_auto_open_enabled(self) -> bool:
        checkbox = self.context.get("_telegram_channel_auto_open_check", None)
        if checkbox is not None:
            return checkbox.isChecked()
        return bool(getattr(self.context.config, "telegram_auto_open_videos", True))

    def _select_telegram_channel_item_key(self, key: str) -> None:
        if not key:
            return
        for row, channel_item in enumerate(self.context.get("_telegram_channel_items", [])):
            if self.context.sources._telegram_channel_item_key(channel_item) == key:
                self.context.layout._telegram_channel_list.setCurrentRow(row)
                return

    def _telegram_channel_item_key(self, channel_item) -> str:
        return self.context.sources.channel.item_key(channel_item)

    def _telegram_channel_item_key_values(self, post_id: object, url: object) -> str:
        return self.context.sources.channel.item_key_values(post_id, url)

    def _set_telegram_item_thumbnail(self, item: QListWidgetItem, channel_item, index: int) -> None:
        thumbnail = str(getattr(channel_item, "thumbnail_url", "") or "").strip()
        if not thumbnail:
            return
        pixmap = self.context.sources._telegram_thumbnail_pixmap(thumbnail)
        if not pixmap.isNull():
            item.setIcon(QIcon(pixmap))
            return
        self.context.sources._request_telegram_thumbnail(thumbnail, index=index)

    def _show_telegram_channel_thumbnail(self, channel_item) -> None:
        thumbnail = str(getattr(channel_item, "thumbnail_url", "") or "").strip()
        if not thumbnail:
            self.context.sources._clear_telegram_channel_thumbnail()
            return
        pixmap = self.context.sources._telegram_thumbnail_pixmap(thumbnail)
        if not pixmap.isNull():
            self.context.sources._set_telegram_channel_thumbnail_pixmap(pixmap)
            return
        self.context.sources._clear_telegram_channel_thumbnail()
        self.context.sources._request_telegram_thumbnail(thumbnail, index=-1)

    def _clear_telegram_channel_thumbnail(self) -> None:
        self.context.sources.channel.channel_thumbnail_source = QPixmap()
        self.context.layout._telegram_channel_thumbnail.clear()
        self.context.layout._telegram_channel_thumbnail.show()
        self.context.channel_browser._show_telegram_thumbnail_output()

    def _set_telegram_channel_thumbnail_pixmap(self, pixmap: QPixmap) -> None:
        if pixmap.isNull():
            self.context.sources._clear_telegram_channel_thumbnail()
            return
        self.context.sources.channel.channel_thumbnail_source = pixmap
        self.context.sources._refresh_telegram_channel_thumbnail()
        self.context.layout._telegram_channel_thumbnail.show()
        self.context.channel_browser._show_telegram_thumbnail_output()

    def _refresh_telegram_channel_thumbnail(self) -> None:
        pixmap = self.context.get("_telegram_channel_thumbnail_source", QPixmap())
        if pixmap.isNull():
            return
        size = self.context.layout._telegram_channel_thumbnail.size()
        self.context.layout._telegram_channel_thumbnail.setPixmap(
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
        manager = self.context.sources._telegram_thumbnail_network()
        request = QNetworkRequest(QUrl(thumbnail))
        reply = manager.get(request)
        reply.setProperty("telegram_thumbnail_index", index)
        reply.setProperty("telegram_thumbnail_url", thumbnail)
        reply.finished.connect(lambda reply=reply: self.context.sources._telegram_thumbnail_loaded(reply))

    def _telegram_thumbnail_network(self) -> QNetworkAccessManager:
        manager = self.context.get("_telegram_thumbnail_manager", None)
        if manager is None:
            manager = QNetworkAccessManager(self.context.window)
            self.context.sources._telegram_thumbnail_manager = manager
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
                item = self.context.layout._telegram_channel_list.item(index)
                if item is not None:
                    item.setIcon(QIcon(pixmap))
                return
            current = self.context.sources._telegram_channel_item_from_list_item(
                self.context.layout._telegram_channel_list.currentItem()
            )
            if current is not None and str(getattr(current, "thumbnail_url", "") or "").strip() == thumbnail:
                self.context.sources._set_telegram_channel_thumbnail_pixmap(pixmap)
        finally:
            reply.deleteLater()

    def _telegram_channel_item_activated(self, item) -> None:
        channel_item = self.context.sources._telegram_channel_item_from_list_item(item)
        if channel_item is None:
            return
        if getattr(channel_item, "has_video", True):
            self.context.sources.channel.pending_autoplay = True
            self.context.sources._open_telegram_channel_item(channel_item)
        else:
            self.context.window.statusBar().showMessage(self.context.settings._tr("telegram_channel_text_only"))

    def _telegram_media_kind(self, channel_item) -> str:
        return channel_item_media_kind(channel_item)

    def _telegram_media_kind_label(self, channel_item) -> str:
        key = {
            "video": "telegram_channel_item_video",
            "photo": "telegram_channel_item_photo",
            "document": "telegram_channel_item_document",
            "audio": "telegram_channel_item_audio",
            "text": "telegram_channel_item_post",
        }.get(self.context.sources._telegram_media_kind(channel_item), "telegram_channel_item_post")
        return self.context.settings._tr(key)

    def _telegram_item_status_label(self, channel_item) -> str:
        status = self.context.sources.channel.item_status(channel_item)
        key = {
            "loading": "telegram_channel_status_loading",
            "queued": "telegram_channel_status_queued",
            "current": "telegram_channel_status_current",
            "failed": "telegram_channel_status_failed",
            "opened": "telegram_channel_status_opened",
        }.get(status, "")
        return self.context.settings._tr(key) if key else ""

    def _open_selected_telegram_channel_item(self) -> None:
        channel_item = self.context.sources._telegram_channel_item_from_list_item(
            self.context.layout._telegram_channel_list.currentItem()
        )
        if channel_item is None:
            self.context.window.statusBar().showMessage(self.context.settings._tr("telegram_channel_no_selection"))
            return
        if not getattr(channel_item, "has_video", True):
            self.context.window.statusBar().showMessage(self.context.settings._tr("telegram_channel_text_only"))
            return
        self.context.sources.channel.pending_autoplay = True
        self.context.sources._open_telegram_channel_item(channel_item)

    def _open_telegram_channel_item(self, channel_item) -> None:
        current_key = self.context.sources.channel.mark_opening(channel_item)
        if self.context.sources.channel.pending_open_item_key == current_key:
            self.context.sources.channel.pending_open_item_key = ""
        self.context.sources._set_active_telegram_channel_video(channel_item)
        self.context.sources.channel.browser_return_available = True
        self.context.sources._refresh_telegram_channel_item_statuses()
        selected_key = (
            "status_youtube_channel_selected"
            if self.context.sources._current_channel_provider() == "youtube"
            else "status_telegram_channel_selected"
        )
        self.context.window.statusBar().showMessage(
            self.context.settings._tr(selected_key).format(label=channel_item.title)
        )
        if getattr(channel_item, "authenticated", False):
            self.context.sources._download_telegram_channel_item(channel_item, prompt_for_config=True)
            return
        if self.context.sources._download_telegram_channel_item(channel_item):
            return
        media_url = str(getattr(channel_item, "media_url", "") or "").strip()
        if media_url:
            self.context.sources._open_resolved_video_url(media_url, keep_telegram_context=True)
            return
        self.context.sources._open_resolved_video_url(channel_item.url, keep_telegram_context=True)

    def _download_telegram_channel_item(self, channel_item, *, prompt_for_config: bool = False) -> bool:
        if str(getattr(channel_item, "provider", "telegram") or "telegram") != "telegram":
            return False
        config = load_telegram_login_config() if telegram_private_available() else None
        if config is None and prompt_for_config and telegram_private_available():
            config = self.context.sources._telegram_login_config_dialog()
        if config is None:
            if prompt_for_config:
                self.context.window.statusBar().showMessage(
                    self.context.settings._tr("status_telegram_login_cancelled")
                )
            return False
        self.context.channel_flow._start_telegram_worker(
            "download",
            url=self.context.lifecycle.workers.pending_telegram_url,
            config=config,
            post_id=channel_item.post_id,
            status_text=self.context.settings._tr("status_telegram_video_downloading").format(label=channel_item.title),
        )
        return True

    def _set_active_telegram_channel_video(self, channel_item) -> None:
        self.context.sources.channel.current_channel_item = channel_item
        self.context.sources.channel.current_post_id = str(getattr(channel_item, "post_id", "") or "")
        self.context.sources.channel.current_url = str(getattr(channel_item, "url", "") or "")
        if self.context.sources.channel.current_post_id:
            self.context.sources.channel.pending_post_id = self.context.sources.channel.current_post_id
        self.context.sources._select_telegram_channel_item(channel_item)
        self.context.settings._queue_save_settings()

    def _clear_active_telegram_channel_video(self) -> None:
        self.context.sources.channel.current_channel_item = None
        self.context.sources.channel.current_post_id = ""
        self.context.sources.channel.current_url = ""
        self.context.sources.channel.pending_navigation_direction = 0
        self.context.sources.channel.pending_autoplay = False
        self.context.sources.channel.browser_return_available = False
        self.context.channel_browser._sync_telegram_browser_button()

    def _open_adjacent_telegram_channel_video(self, direction: int, *, allow_load_more: bool = True) -> bool:
        direction = -1 if direction < 0 else 1
        current = self.context.sources._current_telegram_channel_item_for_navigation()
        if current is None:
            return False
        if self.context.sources._telegram_is_busy() or self.context.sources._url_is_opening():
            self.context.window.statusBar().showMessage(self.context.settings._tr("msg_url_opening"))
            return True
        target = self.context.sources._adjacent_telegram_channel_video(current, direction)
        if target is not None:
            self.context.sources.channel.pending_autoplay = True
            self.context.sources._open_telegram_channel_item(target)
            return True
        if direction < 0 and allow_load_more and self.context.sources._oldest_telegram_post_id():
            self.context.sources.channel.pending_navigation_direction = direction
            self.context.sources._load_more_current_telegram_channel()
            return True
        self.context.sources.channel.pending_autoplay = False
        key = self.context.sources._no_adjacent_channel_video_key(direction)
        self.context.window.statusBar().showMessage(self.context.settings._tr(key))
        return True

    def _current_telegram_channel_item_for_navigation(self):
        current = self.context.get("_current_telegram_channel_item", None)
        if current is not None:
            return current
        post_id = str(self.context.get("_current_telegram_post_id", "") or "")
        url = str(self.context.get("_current_telegram_url", "") or "")
        for item in self.context.get("_telegram_channel_all_items", []):
            if post_id and str(getattr(item, "post_id", "") or "") == post_id:
                return item
            if url and str(getattr(item, "url", "") or "") == url:
                return item
        return None

    def _adjacent_telegram_channel_video(self, current, direction: int):
        videos = [
            item for item in self.context.get("_telegram_channel_all_items", []) if getattr(item, "has_video", True)
        ]
        current_post_id = self.context.sources._telegram_numeric_post_id(current)
        numeric_items = [(self.context.sources._telegram_numeric_post_id(item), item) for item in videos]
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
        if not self.context.has("_telegram_channel_list"):
            return
        target_post_id = str(getattr(channel_item, "post_id", "") or "")
        target_url = str(getattr(channel_item, "url", "") or "")
        for row, item in enumerate(self.context.get("_telegram_channel_items", [])):
            if target_post_id and str(getattr(item, "post_id", "") or "") == target_post_id:
                self.context.layout._telegram_channel_list.setCurrentRow(row)
                return
            if target_url and str(getattr(item, "url", "") or "") == target_url:
                self.context.layout._telegram_channel_list.setCurrentRow(row)
                return

    def _select_adjacent_telegram_channel_video(self, direction: int) -> bool:
        if not self.context.has("_telegram_channel_list"):
            return False
        direction = -1 if direction < 0 else 1
        count = self.context.layout._telegram_channel_list.count()
        if count <= 0:
            return False
        current_row = self.context.layout._telegram_channel_list.currentRow()
        row = current_row + direction if current_row >= 0 else (count - 1 if direction < 0 else 0)
        while 0 <= row < count:
            item = self.context.layout._telegram_channel_list.item(row)
            channel_item = self.context.sources._telegram_channel_item_from_list_item(item)
            if channel_item is not None and getattr(channel_item, "has_video", True):
                self.context.layout._telegram_channel_list.scrollToItem(item)
                self.context.layout._telegram_channel_list.setCurrentRow(row)
                return True
            row += direction
        key = self.context.sources._no_adjacent_channel_video_key(direction)
        self.context.window.statusBar().showMessage(self.context.settings._tr(key))
        return True

    def _no_adjacent_channel_video_key(self, direction: int) -> str:
        if self.context.sources._current_channel_provider() == "youtube":
            return "youtube_channel_no_previous_video" if direction < 0 else "youtube_channel_no_next_video"
        return "telegram_channel_no_previous_video" if direction < 0 else "telegram_channel_no_next_video"

    def _telegram_channel_item_from_list_item(self, item):
        if item is None:
            return None
        index = item.data(Qt.ItemDataRole.UserRole)
        try:
            return self.context.sources.channel.channel_items[int(index)]
        except (AttributeError, TypeError, ValueError, IndexError):
            return None

    def _telegram_login_for_current_channel(self) -> None:
        if not telegram_private_available():
            QMessageBox.warning(
                self.context.window,
                self.context.settings._tr("open_url_error_title"),
                self.context.settings._tr("telegram_login_private_unavailable"),
            )
            return
        config = load_telegram_login_config()
        if config is None:
            config = self.context.sources._telegram_login_config_dialog()
            if config is None:
                self.context.window.statusBar().showMessage(
                    self.context.settings._tr("status_telegram_login_cancelled")
                )
                return
            self.context.channel_flow._start_telegram_worker(
                "start_login", config=config, status_key="status_telegram_login_starting"
            )
            return
        self.context.channel_flow._start_telegram_worker(
            "list_authenticated",
            url=self.context.lifecycle.workers.pending_telegram_url,
            config=config,
            status_key="status_telegram_channel_loading_auth",
        )

    def _refresh_current_telegram_channel(self) -> None:
        self.context.sources._reload_current_telegram_channel(search="")

    def _search_current_telegram_channel_remote(self) -> None:
        self.context.sources._reload_current_telegram_channel(
            search=self.context.sources._telegram_current_search(),
            status_key="status_telegram_channel_searching",
        )

    def _reload_current_telegram_channel(self, *, search: str = "", status_key: str = "") -> None:
        if not self.context.lifecycle.workers.pending_telegram_url:
            return
        if self.context.sources._current_channel_provider() == "youtube":
            self.context.channel_browser._show_telegram_channel_browser(
                self.context.lifecycle.workers.pending_telegram_url,
                self.context.settings._tr("youtube_channel_browser_loading"),
            )
            self.context.channel_flow._start_telegram_worker(
                "list_youtube",
                url=self.context.lifecycle.workers.pending_telegram_url,
                search=search,
                status_key=status_key or "status_youtube_channel_searching",
            )
            return
        was_authenticated = bool(self.context.get("_telegram_channel_authenticated", False))
        self.context.channel_browser._show_telegram_channel_browser(
            self.context.lifecycle.workers.pending_telegram_url,
            self.context.settings._tr("telegram_channel_browser_loading"),
        )
        config = load_telegram_login_config() if telegram_private_available() else None
        if config is not None and was_authenticated:
            self.context.channel_flow._start_telegram_worker(
                "list_authenticated",
                url=self.context.lifecycle.workers.pending_telegram_url,
                config=config,
                search=search,
                status_key=status_key or "status_telegram_channel_loading_auth",
            )
            return
        self.context.channel_flow._start_telegram_worker(
            "list_public",
            url=self.context.lifecycle.workers.pending_telegram_url,
            search=search,
            status_key=status_key or "status_telegram_channel_loading",
        )

    def _load_more_current_telegram_channel(self) -> None:
        if not self.context.lifecycle.workers.pending_telegram_url or self.context.sources._telegram_is_busy():
            return
        if self.context.sources._current_channel_provider() == "youtube":
            continuation = str(getattr(self.context.sources.channel, "channel_continuation", "") or "")
            if not continuation:
                return
            self.context.channel_flow._start_telegram_worker(
                "list_youtube_more",
                url=self.context.lifecycle.workers.pending_telegram_url,
                before_post_id=continuation,
                status_key="status_youtube_channel_loading",
            )
            return
        before_post_id = self.context.sources._oldest_telegram_post_id()
        if not before_post_id:
            return
        if self.context.get("_telegram_channel_authenticated", False):
            config = load_telegram_login_config()
            if config is None:
                self.context.sources._telegram_login_for_current_channel()
                return
            self.context.channel_flow._start_telegram_worker(
                "list_authenticated_more",
                url=self.context.lifecycle.workers.pending_telegram_url,
                config=config,
                before_post_id=before_post_id,
                status_key="status_telegram_channel_loading_auth",
            )
            return
        self.context.channel_flow._start_telegram_worker(
            "list_public_more",
            url=self.context.lifecycle.workers.pending_telegram_url,
            before_post_id=before_post_id,
            status_key="status_telegram_channel_loading",
        )

    def _oldest_telegram_post_id(self) -> str:
        return oldest_telegram_post_id(self.context.get("_telegram_channel_all_items", []))

    def _current_channel_provider(self) -> str:
        return current_channel_provider(
            self.context.get("_telegram_channel_provider", ""),
            self.context.get("_pending_telegram_url", ""),
        )

    @staticmethod
    def _youtube_video_id_from_url(url: str) -> str:
        return youtube_video_id_from_url(url)

    def _telegram_current_search(self) -> str:
        if not self.context.has("_telegram_channel_search"):
            return ""
        return self.context.layout._telegram_channel_search.text().strip()

    def _telegram_current_filter(self) -> str:
        if not self.context.has("_telegram_channel_filter_combo"):
            return "all"
        return normalize_channel_filter(self.context.layout._telegram_channel_filter_combo.currentData())

    def _telegram_last_url_for_settings(self) -> str:
        return last_channel_url_for_settings(
            self.context.get("_pending_telegram_url", ""),
            self.context.config.telegram_last_url,
        )

    def _telegram_last_post_id_for_settings(self) -> str:
        return last_channel_post_id_for_settings(
            self.context.get("_pending_telegram_url", ""),
            current_post_id=self.context.get("_current_telegram_post_id", ""),
            pending_post_id=self.context.get("_pending_telegram_post_id", ""),
            configured_post_id=self.context.config.telegram_last_post_id,
        )

    def _telegram_last_search_for_settings(self) -> str:
        return last_channel_search_for_settings(
            self.context.get("_pending_telegram_url", ""),
            current_search=self.context.sources._telegram_current_search(),
            configured_search=self.context.config.telegram_last_search,
        )

    def _telegram_last_filter_for_settings(self) -> str:
        return last_channel_filter_for_settings(
            self.context.get("_pending_telegram_url", ""),
            current_filter=self.context.sources._telegram_current_filter(),
            configured_filter=self.context.config.telegram_last_filter,
        )

    def _telegram_side_panel_sizes_for_settings(self) -> tuple[int, ...]:
        sizes = list(self.context.get("_telegram_side_panel_sizes", []) or [])
        if len(sizes) < 2:
            sizes = list(getattr(self.context.config, "telegram_side_panel_sizes", (1, 1)) or (1, 1))
        sizes = [max(0, int(item or 0)) for item in sizes[:2]]
        return tuple(sizes) if len(sizes) == 2 else (1, 1)

    def _apply_telegram_browser_preferences(self, url: str) -> None:
        same_channel = self.context.sources._telegram_channel_key(url) == self.context.sources._telegram_channel_key(
            self.context.config.telegram_last_url
        )
        if same_channel:
            if not self.context.sources.channel.pending_post_id:
                self.context.sources.channel.pending_post_id = self.context.config.telegram_last_post_id
            self.context.sources.channel.side_panel_visible = self.context.config.telegram_side_panel_visible
            self.context.sources.channel.side_panel_sizes = list(self.context.config.telegram_side_panel_sizes)
            self.context.sources._set_telegram_search_text(self.context.config.telegram_last_search)
            self.context.sources._set_telegram_filter_value(self.context.config.telegram_last_filter)
            return
        self.context.sources.channel.side_panel_visible = True
        self.context.sources.channel.side_panel_sizes = [1, 1]
        self.context.sources._set_telegram_search_text("")
        self.context.sources._set_telegram_filter_value("all")

    def _set_telegram_search_text(self, text: str) -> None:
        if not self.context.has("_telegram_channel_search"):
            return
        was_blocked = self.context.layout._telegram_channel_search.blockSignals(True)
        self.context.layout._telegram_channel_search.setText(str(text or ""))
        self.context.layout._telegram_channel_search.blockSignals(was_blocked)

    def _set_telegram_filter_value(self, value: str) -> None:
        if not self.context.has("_telegram_channel_filter_combo"):
            return
        index = self.context.layout._telegram_channel_filter_combo.findData(value)
        was_blocked = self.context.layout._telegram_channel_filter_combo.blockSignals(True)
        self.context.layout._telegram_channel_filter_combo.setCurrentIndex(index if index >= 0 else 0)
        self.context.layout._telegram_channel_filter_combo.blockSignals(was_blocked)

    @staticmethod
    def _telegram_channel_key(url: str) -> str:
        return telegram_channel_key(url)

    def _telegram_video_ready(self, path: str) -> None:
        if self.context.sources._telegram_open_result_is_stale():
            return
        self.context.sources.channel.mark_opened(self.context.sources.channel.current_channel_item)
        self.context.sources._refresh_telegram_channel_item_statuses()
        self.context.source_progress._close_cache_dialog()
        self.context.sources._open_local_video_path(
            path,
            clear_telegram_channel=False,
            play_pending_navigation=True,
        )

    def _open_local_video_path(
        self,
        path: str,
        *,
        prompt_for_subtitle: bool = False,
        subtitle_path: str | Path | None = None,
        clear_telegram_channel: bool = True,
        play_pending_navigation: bool = False,
    ) -> None:
        if clear_telegram_channel:
            self.context.sources._clear_active_telegram_channel_video()
        self.context.dubbing._stop_dubbing()
        self.context.sources._reset_document_state_for_video()
        self.context.channel_browser._video_path = path
        self.context.channel_browser._video_source_http_headers = {}
        self.context.media._auto_select_video_aspect_ratio()
        self.context.media._load_current_video_for_playback()
        self.context.channel_browser._show_video_output()
        self.context.channel_browser._sync_telegram_browser_button()
        self.context.layout._source_label.setText(path)
        subtitle_attached = False
        selected_subtitle = Path(subtitle_path) if subtitle_path else None
        if selected_subtitle is None and prompt_for_subtitle:
            selected_subtitle = self.context.sources._prompt_video_subtitle(Path(path))
        if selected_subtitle is not None:
            subtitle_attached = self.context.sources._apply_video_subtitle_path(selected_subtitle, save=False)
        self.context.settings._save_settings()
        if not subtitle_attached:
            self.context.window.statusBar().showMessage(
                self.context.settings._tr("status_opened_path").format(path=path)
            )
        if self.context.media.playback.dubbing_auto_enabled:
            self.context.layout._dub_button.setChecked(True)
            self.context.dubbing._start_dubbing()
        if play_pending_navigation:
            self.context.sources._play_pending_telegram_navigation(source_path=path, require_runtime_match=True)

    def _play_pending_telegram_navigation(
        self,
        *,
        source_path: str = "",
        require_runtime_match: bool = False,
    ) -> None:
        if not self.context.get("_pending_telegram_autoplay", False):
            return
        if source_path and self.context.channel_browser._video_path != source_path:
            return
        if require_runtime_match:
            runtime_path = str(self.context.get("_runtime_media_path", "") or "")
            if not runtime_path or runtime_path != self.context.channel_browser._video_path:
                return
        self.context.sources.channel.pending_autoplay = False
        self.context.media._play_active_source()

    def _queue_pending_telegram_channel_item(self, channel_item) -> None:
        if self.context.sources._telegram_channel_item_auto_open_blocked(channel_item):
            return
        self.context.sources.channel.pending_open_item_key = self.context.sources._telegram_channel_item_key(
            channel_item
        )
        self.context.window.statusBar().showMessage(self.context.settings._tr("msg_url_opening"))

    def _open_pending_telegram_channel_item(self) -> None:
        if self.context.sources._telegram_is_busy() or self.context.sources._url_is_opening():
            return
        key = str(getattr(self.context.sources.channel, "pending_open_item_key", "") or "")
        if not key:
            return
        self.context.sources.channel.pending_open_item_key = ""
        channel_item = self.context.sources._telegram_channel_item_by_key(key)
        if channel_item is None or not getattr(channel_item, "has_video", True):
            return
        if self.context.sources._telegram_channel_item_auto_open_blocked(channel_item):
            return
        self.context.sources._open_telegram_channel_item(channel_item)

    def _telegram_channel_item_by_key(self, key: str):
        for item in self.context.get("_telegram_channel_all_items", []):
            if self.context.sources._telegram_channel_item_key(item) == key:
                return item
        for item in self.context.get("_telegram_channel_items", []):
            if self.context.sources._telegram_channel_item_key(item) == key:
                return item
        return None

    def _telegram_open_result_is_stale(self) -> bool:
        loading_key = str(getattr(self.context.sources.channel, "loading_item_key", "") or "")
        pending_key = str(getattr(self.context.sources.channel, "pending_open_item_key", "") or "")
        return bool(loading_key and pending_key and pending_key != loading_key)

    def _telegram_worker_failed(self, operation: str, message: str) -> None:
        detail = _repair_mojibake(message)
        if operation.endswith("_more"):
            self.context.sources.channel.auto_load_pending_before_post_id = ""
        if operation == "download":
            self.context.sources.channel.mark_failed(self.context.sources.channel.current_channel_item)
            self.context.sources._refresh_telegram_channel_item_statuses()
            if self.context.media.playback.cache_dialog is not None:
                self.context.media.playback.cache_dialog.mark_failed(detail)
        if operation in {"list_public", "list_public_more"} and not telegram_private_available():
            QMessageBox.warning(
                self.context.window,
                self.context.settings._tr("open_url_error_title"),
                f"{detail}\n\n{self.context.settings._tr('telegram_channel_public_login_unavailable')}",
            )
            self.context.window.statusBar().showMessage(self.context.settings._tr("status_open_url_failed"))
            return
        if operation in {"list_public", "list_public_more", "list_authenticated", "list_authenticated_more"} and (
            self.context.sources._confirm_telegram_login(detail)
        ):
            config = self.context.sources._telegram_login_config_dialog()
            if config is None:
                self.context.window.statusBar().showMessage(
                    self.context.settings._tr("status_telegram_login_cancelled")
                )
                return
            self.context.channel_flow._start_telegram_worker(
                "start_login", config=config, status_key="status_telegram_login_starting"
            )
            return
        QMessageBox.warning(self.context.window, self.context.settings._tr("open_url_error_title"), detail)
        self.context.window.statusBar().showMessage(self.context.settings._tr("status_open_url_failed"))

    def _telegram_login_request_ready(self, request) -> None:
        code, ok = QInputDialog.getText(
            self.context.window,
            self.context.settings._tr("telegram_login_code_title"),
            self.context.settings._tr("telegram_login_code_label"),
        )
        if not ok:
            self.context.window.statusBar().showMessage(self.context.settings._tr("status_telegram_login_cancelled"))
            return
        self.context.channel_flow._start_telegram_worker(
            "complete_login",
            login_request=request,
            code=code,
            status_key="status_telegram_login_completing",
        )

    def _telegram_password_required(self, request, code: str) -> None:
        password, ok = QInputDialog.getText(
            self.context.window,
            self.context.settings._tr("telegram_login_password_title"),
            self.context.settings._tr("telegram_login_password_label"),
            QLineEdit.EchoMode.Password,
        )
        if not ok:
            self.context.window.statusBar().showMessage(self.context.settings._tr("status_telegram_login_cancelled"))
            return
        self.context.channel_flow._start_telegram_worker(
            "complete_login",
            login_request=request,
            code=code,
            password=password,
            status_key="status_telegram_login_completing",
        )

    def _telegram_login_ready(self, config: TelegramLoginConfig) -> None:
        self.context.window.statusBar().showMessage(self.context.settings._tr("status_telegram_login_ready"))
        self.context.channel_flow._start_telegram_worker(
            "list_authenticated",
            url=self.context.lifecycle.workers.pending_telegram_url,
            config=config,
            status_key="status_telegram_channel_loading_auth",
        )

    def _telegram_worker_finished(self, worker) -> None:
        self.context.lifecycle.workers.delete_worker(worker)
        if self.context.lifecycle.workers.finish_telegram(worker):
            if not self.context.sources._url_is_opening():
                self.context.sources._set_telegram_opening_controls(True)
            if getattr(worker, "operation", "") != "download":
                self.context.sources.channel.loading_item_key = ""
            QTimer.singleShot(0, self.context.sources._open_pending_telegram_channel_item)

    def _telegram_is_busy(self) -> bool:
        worker = self.context.get("_telegram_worker", None)
        return worker is not None and worker.isRunning()

    def _set_telegram_opening_controls(self, enabled: bool, *, keep_browser_tools: bool = False) -> None:
        if self.context.has("_open_url_button"):
            self.context.layout._open_url_button.setEnabled(enabled)
        if self.context.has("_sync_open_source_menu_enabled"):
            self.context.layout._sync_open_source_menu_enabled()
        for widget_name in (
            "_telegram_channel_refresh_button",
            "_telegram_channel_remote_search_button",
            "_telegram_channel_load_more_button",
            "_telegram_channel_translate_button",
            "_telegram_channel_auto_open_check",
        ):
            widget = self.context.get(widget_name, None)
            if widget is not None:
                if keep_browser_tools and widget_name in {
                    "_telegram_channel_load_more_button",
                    "_telegram_channel_translate_button",
                }:
                    continue
                widget.setEnabled(enabled)
        login_button = self.context.get("_telegram_channel_login_button", None)
        if login_button is not None:
            login_button.setEnabled(
                enabled
                and self.context.sources._current_channel_provider() == "telegram"
                and telegram_private_available()
            )

    def _confirm_telegram_login(self, public_error: str) -> bool:
        message = f"{_repair_mojibake(public_error)}\n\n{self.context.settings._tr('telegram_login_prompt')}"
        return (
            QMessageBox.question(
                self.context.window,
                self.context.settings._tr("telegram_login_title"),
                message,
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes,
            )
            == QMessageBox.Yes
        )

    def _telegram_login_config_dialog(self) -> TelegramLoginConfig | None:
        dialog = _TelegramLoginDialog(self.context.settings._ui_language(), self.context.window)
        if dialog.exec() != QDialog.Accepted:
            return None
        try:
            return validate_telegram_login_config(
                dialog.api_id,
                dialog.api_hash,
                dialog.phone,
                self.context.config.gui_language,
            )
        except TelegramChannelError as exc:
            QMessageBox.warning(
                self.context.window,
                self.context.settings._tr("telegram_login_title"),
                _repair_mojibake(redact_secrets(exc)),
            )
            return None

    def _video_url_resolved(self, source) -> None:
        self.context.source_progress._close_cache_dialog()
        self.context.source_progress._set_cache_status_visible(False)
        self.context.sources._video_url_stream_source = None
        self.context.source_progress._set_cache_play_now_enabled(False)
        if self.context.sources._telegram_open_result_is_stale():
            self.context.sources.channel.loading_item_key = ""
            QTimer.singleShot(0, self.context.sources._open_pending_telegram_channel_item)
            return
        self.context.sources.channel.mark_opened(self.context.sources.channel.current_channel_item)
        self.context.sources._refresh_telegram_channel_item_statuses()
        self.context.sources._reset_document_state_for_video()
        self.context.channel_browser._video_path = source.playback_url
        self.context.channel_browser._video_source_http_headers = self.context.sources._http_headers_for_video_source(
            source
        )
        self.context.media._auto_select_video_aspect_ratio(source)
        self.context.media._load_current_video_for_playback()
        self.context.channel_browser._show_video_output()
        self.context.channel_browser._sync_telegram_browser_button()
        label = source.title if source.is_resolved else source.input_url
        self.context.layout._source_label.setText(label)
        provider = f" ({source.provider})" if source.is_resolved else ""
        self.context.window.statusBar().showMessage(
            self.context.settings._tr("status_opened_url").format(provider=provider, label=label)
        )
        parsed_playback_url = urlparse(str(source.playback_url or "").strip())
        playback_is_local = parsed_playback_url.scheme.lower() not in {"http", "https"}
        if bool(self.context.get("_last_video_url_request", {}).get("full_cache")) and playback_is_local:
            self.context.sources._url_cache_completed_count = (
                int(self.context.get("_url_cache_completed_count", 0) or 0) + 1
            )
            if self.context.has("_set_background_task_detail"):
                self.context.runtime._set_background_task_detail(
                    "URL/cache loading", self.context.settings._tr("task_center_url_cached")
                )
        self.context.settings._save_settings()
        if self.context.media.playback.dubbing_auto_enabled:
            self.context.layout._dub_button.setChecked(True)
            self.context.dubbing._start_dubbing()
        self.context.sources._play_pending_telegram_navigation(
            source_path=source.playback_url, require_runtime_match=True
        )

    def _video_url_stream_ready(self, source) -> None:
        if self.context.sources._telegram_open_result_is_stale():
            return
        self.context.sources._video_url_stream_source = source
        self.context.source_progress._set_cache_play_now_enabled(True)

    def _play_video_url_stream_now(self) -> None:
        source = self.context.get("_video_url_stream_source", None)
        if source is None:
            return
        self.context.source_progress._set_cache_play_now_enabled(False)
        self.context.sources._reset_document_state_for_video()
        self.context.channel_browser._video_path = source.playback_url
        self.context.channel_browser._video_source_http_headers = self.context.sources._http_headers_for_video_source(
            source
        )
        self.context.media._auto_select_video_aspect_ratio(source)
        self.context.media._load_current_video_for_playback()
        self.context.channel_browser._show_video_output()
        self.context.channel_browser._sync_telegram_browser_button()
        label = source.title if source.is_resolved else source.input_url
        self.context.layout._source_label.setText(label)
        self.context.window.statusBar().showMessage(self.context.settings._tr("cache_playing_stream_while_caching"))
        self.context.media._play_active_source()

    @staticmethod
    def _http_headers_for_video_source(source) -> dict[str, str]:
        headers = dict(getattr(source, "http_headers", {}) or {})
        if headers:
            return headers
        playback_url = str(getattr(source, "playback_url", "") or "").strip()
        input_url = str(getattr(source, "input_url", "") or "").strip()
        playback_scheme = urlparse(playback_url).scheme.lower()
        input_scheme = urlparse(input_url).scheme.lower()
        if playback_scheme in {"http", "https"} and input_scheme in {"http", "https"} and input_url != playback_url:
            return {
                "Accept": "*/*",
                "Accept-Language": "en-US,en;q=0.9",
                "Referer": input_url,
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/125 Safari/537.36"
                ),
            }
        return {}

    def _reset_document_state_for_video(self) -> None:
        self.context.media.document.reset_for_video()
        self.context.media._set_document_mode(False)
        self.context.layout._document_view.setReadOnly(True)
        if self.context.settings._selected_audio_source() in {"transcript", "document_editor"}:
            self.context.settings._set_combo_data(self.context.layout._audio_source_combo, "original")
        self.context.layout._transcript_path_edit.clear()
        self.context.transcript._clear_transcript()
        self.context.sources._invalidate_subtitle_entries()

    def _video_url_failed(self, message: str) -> None:
        self.context.sources.channel.mark_failed(self.context.sources.channel.current_channel_item)
        self.context.sources._refresh_telegram_channel_item_statuses()
        detail = _repair_mojibake(message)
        if self.context.media.playback.cache_dialog is not None:
            self.context.media.playback.cache_dialog.mark_failed(detail)
        if self.context.sources._youtube_channel_item_open_failed():
            if self.context.layout._media_stack.currentWidget() is not self.context.layout._telegram_channel_view:
                self.context.channel_browser._return_to_telegram_channel_browser()
            self.context.layout._telegram_channel_status.setText(detail)
            self.context.window.statusBar().showMessage(
                self.context.settings._tr("youtube_channel_browser_ready").format(
                    count=len(self.context.sources.channel.channel_all_items)
                )
            )
            QTimer.singleShot(0, self.context.sources._open_pending_telegram_channel_item)
            return
        if self.context.sources._browser_video_url_should_fallback(detail):
            if self.context.sources._open_video_url_in_browser(
                str(self.context.sources._last_video_url_request.get("url") or "")
            ):
                QTimer.singleShot(0, self.context.sources._open_pending_telegram_channel_item)
                return
        self.context.window.statusBar().showMessage(self.context.settings._tr("status_open_url_failed"))
        self.context.sources._handle_video_url_failure_action(detail)
        QTimer.singleShot(0, self.context.sources._open_pending_telegram_channel_item)

    def _youtube_channel_item_open_failed(self) -> bool:
        return video_url_request_is_youtube_channel_item_failure(
            self.context.get("_last_video_url_request", None),
            channel_provider=self.context.sources._current_channel_provider(),
            current_channel_item=self.context.get("_current_telegram_channel_item", None),
        )

    def _browser_video_url_should_fallback(self, detail: str) -> bool:
        return video_url_request_should_fallback_to_browser(
            self.context.get("_last_video_url_request", None),
            detail,
            can_open_browser=lambda url: urlparse(str(url or "")).scheme.lower() in {"http", "https"},
        )

    def _video_url_finished(self) -> None:
        retry = self.context.get("_pending_video_url_retry", None)
        if isinstance(retry, dict):
            self.context.sources._pending_video_url_retry = None
            kwargs = video_url_open_kwargs(retry, full_cache=bool(retry.get("full_cache")))
            self.context.sources._open_resolved_video_url(str(retry.get("url") or ""), **kwargs)
            return
        QTimer.singleShot(0, self.context.sources._open_pending_telegram_channel_item)

    def _handle_video_url_failure_action(self, detail: str) -> None:
        request = self.context.get("_last_video_url_request", None)
        if not isinstance(request, dict) or not request.get("url"):
            QMessageBox.warning(self.context.window, self.context.settings._tr("open_url_error_title"), detail)
            return
        action = self.context.sources._prompt_video_url_failure_action(detail, request)
        if action == "retry":
            self.context.sources._retry_last_video_url_request()
        elif action == "lower_quality":
            self.context.sources._retry_last_video_url_request(lower_quality=True)
        elif action == "toggle_cache":
            self.context.sources._retry_last_video_url_request(toggle_cache=True)
        elif action == "browser":
            if not self.context.sources._open_video_url_in_browser(str(request.get("url") or "")):
                QMessageBox.warning(self.context.window, self.context.settings._tr("open_url_error_title"), detail)

    def _prompt_video_url_failure_action(self, detail: str, request: dict) -> str:
        box = QMessageBox(self.context.window)
        box.setIcon(QMessageBox.Warning)
        box.setWindowTitle(self.context.settings._tr("open_url_error_title"))
        box.setText(detail)
        unrecoverable = self.context.sources._video_url_failure_is_unrecoverable(detail)
        box.setInformativeText(
            self.context.settings._tr("open_video_url_unavailable_prompt")
            if unrecoverable
            else self.context.settings._tr("open_video_url_retry_prompt")
        )
        retry_button = None
        if not unrecoverable:
            retry_button = box.addButton(self.context.settings._tr("open_video_url_retry"), QMessageBox.AcceptRole)
        lower_button = None
        if (
            not unrecoverable
            and not self.context.sources._video_url_failure_is_forbidden(detail)
            and self.context.sources._lower_playback_quality_value(str(request.get("quality") or ""))
        ):
            lower_button = box.addButton(
                self.context.settings._tr("open_video_url_retry_lower_quality"), QMessageBox.ActionRole
            )
        toggle_button = None
        if not unrecoverable and not self.context.source_progress._source_filter_forces_video_url_full_cache():
            toggle_key = (
                "open_video_url_retry_stream" if bool(request.get("full_cache")) else "open_video_url_retry_cache"
            )
            toggle_button = box.addButton(self.context.settings._tr(toggle_key), QMessageBox.ActionRole)
        browser_button = None
        if self.context.sources._can_open_video_url_in_browser(str(request.get("url") or "")):
            browser_button = box.addButton(
                self.context.settings._tr("open_video_url_open_browser"), QMessageBox.ActionRole
            )
        close_button = box.addButton(self.context.settings._tr("close"), QMessageBox.RejectRole)
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
        return video_url_failure_is_unrecoverable(detail)

    @staticmethod
    def _video_url_failure_is_forbidden(detail: str) -> bool:
        normalized = " ".join(str(detail or "").casefold().split())
        return "403" in normalized or "forbidden" in normalized

    def _retry_last_video_url_request(self, *, lower_quality: bool = False, toggle_cache: bool = False) -> None:
        request = self.context.get("_last_video_url_request", None)
        if not isinstance(request, dict):
            return
        url = str(request.get("url") or "")
        if not url:
            return
        if lower_quality:
            lower_quality_value = self.context.sources._lower_playback_quality_value(str(request.get("quality") or ""))
            if lower_quality_value:
                self.context.settings._set_combo_data(self.context.layout._playback_quality_combo, lower_quality_value)
                self.context.settings._save_settings()
        full_cache = bool(request.get("full_cache"))
        if toggle_cache and not self.context.source_progress._source_filter_forces_video_url_full_cache():
            full_cache = not full_cache
        if self.context.sources._url_is_opening():
            self.context.sources._pending_video_url_retry = video_url_retry_payload(request, full_cache=full_cache)
            self.context.window.statusBar().showMessage(self.context.settings._tr("status_open_url_retry_pending"))
            return
        kwargs = video_url_open_kwargs(request, full_cache=full_cache)
        self.context.sources._open_resolved_video_url(url, **kwargs)

    @staticmethod
    def _lower_playback_quality_value(value: str) -> str:
        return lower_playback_quality_value(value)

    def _can_open_video_url_in_browser(self, url: str) -> bool:
        parsed = urlparse(str(url or "").strip())
        return parsed.scheme.lower() in {"http", "https"} and callable(
            getattr(self.context.get("_video_placeholder", None), "setUrl", None)
        )

    def _open_video_url_in_browser(self, url: str) -> bool:
        if not self.context.sources._can_open_video_url_in_browser(url):
            return False
        self.context.dubbing._stop_dubbing()
        self.context.layout._player.stop()
        self.context.sources._reset_document_state_for_video()
        self.context.sources._clear_active_telegram_channel_video()
        self.context.channel_browser._video_path = None
        self.context.channel_browser._video_source_http_headers = {}
        self.context.runtime.state.media_path = ""
        self.context.layout._video_placeholder.setUrl(QUrl(url))
        self.context.layout._media_stack.setCurrentWidget(self.context.layout._video_placeholder)
        self.context.layout._source_label.setText(url)
        self.context.window.statusBar().showMessage(self.context.settings._tr("open_video_url_browser_opened"))
        self.context.media_browser._sync_media_browser_state()
        return True

    def _refresh_telegram_channel_item_statuses(self) -> None:
        list_widget = self.context.get("_telegram_channel_list", None)
        if list_widget is None:
            return
        current_key = self.context.sources._telegram_channel_item_key(
            self.context.sources._telegram_channel_item_from_list_item(list_widget.currentItem())
        )
        self.context.sources._filter_telegram_channel_items()
        if current_key:
            self.context.channel_browser._telegram_suppress_auto_open_selection = True
            try:
                self.context.sources._select_telegram_channel_item_key(current_key)
            finally:
                self.context.channel_browser._telegram_suppress_auto_open_selection = False

    def _save_transcript(self) -> None:
        text = self.context.transcript._transcript_text(
            self.context.transcript._selected_transcript_view(), self.context.transcript._selected_transcript_type()
        )
        if not text:
            QMessageBox.information(
                self.context.window,
                self.context.settings._tr("app_title"),
                self.context.settings._tr("msg_no_transcript_save"),
            )
            return

        path, _ = QFileDialog.getSaveFileName(
            self.context.window,
            self.context.settings._tr("save_transcript_title"),
            str(Path.home() / "ai-player-transcript.txt"),
            self.context.settings._tr("text_file_filter"),
        )
        if not path:
            return

        output = Path(path)
        if output.suffix.lower() != ".txt":
            output = output.with_suffix(".txt")
        output.write_text(text.rstrip() + "\n", encoding="utf-8")
        self.context.window.statusBar().showMessage(
            self.context.settings._tr("status_saved_transcript").format(path=output)
        )

    def _choose_transcript_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self.context.window,
            self.context.settings._tr("choose_transcript_title"),
            str(Path.home()),
            self.context.settings._tr("transcript_file_filter"),
        )
        if not path:
            return
        self.context.layout._transcript_path_edit.setText(path)
        self.context.sources._invalidate_subtitle_entries()
        self.context.settings._queue_save_settings()
        self.context.window.statusBar().showMessage(
            self.context.settings._tr("status_selected_transcript").format(path=path)
        )
        if self.context.has("_refresh_next_action_panel"):
            self.context.transcript._refresh_next_action_panel()

    def _audio_source_changed(self, *_args) -> None:
        self.context.sources._sync_audio_source_controls()
        if self.context.settings._selected_audio_source() == "document_editor":
            self.context.sources._enter_document_editor_source()
        self.context.settings._queue_save_settings()
        if self.context.layout._dub_button.isChecked() and self.context.lifecycle.workers.dubbing_worker is not None:
            self.context.dubbing._stop_dubbing()
            self.context.layout._dub_button.setChecked(True)
            self.context.dubbing._start_dubbing()

    def _sync_audio_source_controls(self) -> None:
        is_transcript = self.context.settings._selected_audio_source() == "transcript"
        self.context.layout._transcript_path_edit.setEnabled(is_transcript)
        self.context.layout._transcript_file_button.setEnabled(is_transcript)
        if self.context.has("_refresh_next_action_panel"):
            self.context.transcript._refresh_next_action_panel()

    def _enter_document_editor_source(self) -> None:
        if self.context.media.document.editor_active:
            return
        self.context.dubbing._stop_dubbing()
        self.context.layout._player.stop()
        self.context.media.document.enter_editor()
        self.context.media._set_document_mode(False)
        self.context.media.document.editor_active = True
        self.context.channel_browser._video_path = None
        self.context.channel_browser._video_source_http_headers = {}
        self.context.layout._transcript_path_edit.clear()
        self.context.sources._invalidate_subtitle_entries()
        self.context.layout._media_stack.setCurrentWidget(self.context.layout._document_view)
        self.context.layout._document_view.setReadOnly(False)
        self.context.layout._document_view.clear()
        self.context.layout._document_view.setPlaceholderText(self.context.settings._tr("document_editor_placeholder"))
        self.context.layout._source_label.setText(self.context.settings._tr("document_editor"))
        self.context.layout._time_label.setText("00:00 / 00:00")
        self.context.layout._position_slider.setValue(0)
        self.context.window.statusBar().showMessage(self.context.settings._tr("status_document_editor_hint"))

    def _prepare_document_editor_source(self) -> bool:
        text = self.context.layout._document_view.toPlainText().strip()
        try:
            transcript = create_text_document_transcript(
                text,
                seconds_per_segment=max(2, int(self.context.config.segment_seconds)),
            )
        except Exception as exc:
            self.context.layout._dub_button.setChecked(False)
            QMessageBox.information(self.context.window, self.context.settings._tr("app_title"), redact_secrets(exc))
            return False

        self.context.dubbing._stop_dubbing()
        self.context.layout._player.stop()
        self.context.media.document.editor_active = False
        self.context.layout._document_view.setReadOnly(True)
        total_duration_ms = sum(page.duration_seconds for page in transcript.pages) * 1000
        self.context.media._set_document_mode(True, total_duration_ms, transcript.pages)
        self.context.channel_browser._video_path = str(transcript.transcript_path)
        self.context.channel_browser._video_source_http_headers = {}
        self.context.layout._transcript_path_edit.setText(str(transcript.transcript_path))
        self.context.sources._invalidate_subtitle_entries()
        self.context.transcript._clear_transcript()
        self.context.layout._source_label.setText(transcript.title)
        self.context.window.statusBar().showMessage(
            self.context.settings._tr("status_document_editor_created").format(count=transcript.segment_count)
        )
        return True

    def _subtitle_mode_changed(self, *_args) -> None:
        if self.context.sources._selected_subtitle_mode() != "off":
            self.context.media._load_subtitle_entries_for_overlay()
            self.context.media._update_subtitle_overlay()
        else:
            self.context.transcript.state.last_text = ""
            self.context.layout._subtitle_overlay.hide()

    def _selected_subtitle_mode(self) -> str:
        if self.context.has("_subtitle_mode_combo"):
            value = self.context.layout._subtitle_mode_combo.currentData()
            if value in {"off", "source", "target"}:
                return str(value)
        return "off"

    def _subtitle_size_changed(self, *_args) -> None:
        self.context.media._apply_subtitle_overlay_style()
        self.context.media._position_subtitle_overlay()

    def _invalidate_subtitle_entries(self, *_args) -> None:
        self.context.transcript.state.entries = []
        self.context.transcript.state.entries_path = ""
        self.context.transcript.state.last_text = ""
        self.context.transcript.state.live_source_text = ""
        self.context.transcript.state.live_target_text = ""
        self.context.transcript.state.live_expires_at = 0.0
        self.context.transcript.state.live_entries = []
        if self.context.has("_subtitle_overlay"):
            self.context.layout._subtitle_overlay.hide()

    def _video_aspect_changed(self, *_args) -> None:
        self.context.media._apply_media_aspect_ratio()
        if self.context.media.document.mode and self.context.media.document.pages:
            self.context.media._update_document_page(force=True)
        self.context.settings._queue_save_settings()

    def _playback_quality_changed(self, *_args) -> None:
        self.context.settings._queue_save_settings()
        if self.context.channel_browser._video_path and not self.context.media.document.mode:
            self.context.window.statusBar().showMessage(self.context.settings._tr("status_playback_quality_next_url"))

    def _url_is_opening(self) -> bool:
        return self.context.sources.url_controller.is_opening()

    def _stop_video_url(self, wait_ms: int = 5000) -> bool:
        return self.context.sources.url_controller.stop(wait_ms=wait_ms)


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
