from __future__ import annotations

import hashlib
import html
import json
import subprocess
import tempfile
import time
from pathlib import Path

from PySide6.QtCore import QEvent, QPoint, Qt, QTimer, QUrl
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QFrame

from ai_player.services.ffmpeg import ffprobe_executable
from ai_player.services.source_voice_filter import source_voice_filter_signature
from ai_player.services.video_source import _cleanup_cache_root
from ai_player.ui.player_window_utils import (
    is_ytdlp_source_cache as _is_ytdlp_source_cache,
)
from ai_player.ui.player_window_utils import (
    repair_mojibake as _repair_mojibake,
)
from ai_player.workers.dubbing_worker import _load_transcript_entries
from ai_player.workers.player_window_workers import PlaybackCompatibilityWorker, SourceAudioFilterWorker

_QT_COMPAT_VIDEO_CACHE: dict[tuple[str, int, int], bool] = {}


class PlayerMediaMixin:
    def _source_voice_filter_changed(self, checked: bool) -> None:
        self._queue_save_settings()
        if hasattr(self, "_sync_source_filter_controls"):
            self._sync_source_filter_controls()
        if self._document_mode or not self._video_path:
            return
        self._load_current_video_for_playback(preserve_state=True)
        state = self._tr("state_on") if checked else self._tr("state_off")
        self.statusBar().showMessage(self._tr("status_source_filter_changed").format(state=state))

    def _source_voice_filter_mode_changed(self, *_args) -> None:
        self._queue_save_settings()
        if hasattr(self, "_sync_source_filter_controls"):
            self._sync_source_filter_controls()
        if self._source_filter_check.isChecked() and not self._document_mode and self._video_path:
            if self._source_filter_worker is not None and self._source_filter_worker.isRunning():
                self._source_filter_restart_pending = True
                self._source_filter_worker.stop()
                self.statusBar().showMessage(self._tr("status_source_filter_preparing"))
                return
            self._load_current_video_for_playback(preserve_state=True)

    def _load_current_video_for_playback(self, preserve_state: bool = False) -> None:
        if not self._video_path:
            return
        if self._source_filter_check.isChecked() and self._can_filter_source_audio(self._video_path):
            filter_key = self._source_filter_cache_key(self._video_path)
            filtered_path = self._source_filter_cache.get(filter_key)
            if filtered_path and Path(filtered_path).exists():
                self._switch_player_source(filtered_path, preserve_state)
                return
            if self._needs_qt_playback_compat(self._video_path):
                self._player.stop()
                self.statusBar().showMessage(self._tr("status_compat_creating"))
            else:
                self._switch_player_source(self._video_path, preserve_state)
            self._start_source_audio_filter(self._video_path)
            return
        if self._needs_qt_playback_compat(self._video_path):
            compat_key = self._playback_compat_cache_key(self._video_path)
            compat_path = self._playback_compat_cache.get(compat_key)
            if compat_path and Path(compat_path).exists():
                self._switch_player_source(compat_path, preserve_state)
                return
            output_path = self._playback_compat_output_path(self._video_path)
            if output_path.exists() and output_path.stat().st_size > 0:
                self._playback_compat_cache[compat_key] = str(output_path)
                self._switch_player_source(str(output_path), preserve_state)
                return
            self._player.stop()
            self._start_playback_compat(self._video_path)
            return
        self._switch_player_source(self._video_path, preserve_state)

    def _switch_player_source(self, path: str, preserve_state: bool) -> None:
        was_playing = preserve_state and self._player.is_playing()
        current_ms = self._player.get_time_ms() if preserve_state else 0
        self._runtime_media_path = path
        self._runtime_media_info_text = self._runtime_media_info_text_current(force=True)
        self._player.load(path)
        self._player.set_volume(self._volume_slider.value())
        if preserve_state and current_ms > 0:
            self._player.set_time_ms(current_ms)
        if was_playing:
            self._player.play()

    def _start_source_audio_filter(self, source_path: str) -> None:
        if self._source_filter_worker is not None and self._source_filter_worker.isRunning():
            return
        mode = self._selected_source_filter_mode()
        model = self._selected_source_filter_model()
        output_path = self._source_filter_output_path(source_path, mode, model)
        self._source_filter_worker_mode = mode
        self._source_filter_worker_model = model
        self._source_filter_worker = SourceAudioFilterWorker(
            source_path,
            output_path,
            mode,
            model,
            self,
        )
        self._source_filter_worker.ready.connect(self._source_audio_filter_ready)
        self._source_filter_worker.failed.connect(self._source_audio_filter_failed)
        self._source_filter_worker.warning.connect(self._source_audio_filter_warning)
        self._source_filter_worker.finished.connect(self._source_audio_filter_finished)
        self._source_filter_worker.start()
        self.statusBar().showMessage(self._tr("status_source_filter_preparing"))

    def _source_audio_filter_ready(self, source_path: str, filtered_path: str, backend: str = "") -> None:
        worker_mode = getattr(self, "_source_filter_worker_mode", self._selected_source_filter_mode())
        worker_model = getattr(self, "_source_filter_worker_model", self._selected_source_filter_model())
        expected_output = self._source_filter_output_path(source_path, worker_mode, worker_model)
        if Path(filtered_path) != expected_output:
            return
        self._source_filter_cache[self._source_filter_cache_key(source_path, worker_mode, backend, worker_model)] = (
            filtered_path
        )
        if self._video_path == source_path and self._source_filter_check.isChecked() and not self._document_mode:
            filter_changed = (
                worker_mode != self._selected_source_filter_mode()
                or worker_model != self._selected_source_filter_model()
            )
            if filter_changed:
                self._source_filter_restart_pending = True
                return
            self._switch_player_source(filtered_path, preserve_state=True)
            self.statusBar().showMessage(self._tr("status_source_filter_ready"))

    def _source_audio_filter_failed(self, source_path: str, message: str) -> None:
        if self._video_path == source_path:
            detail = _repair_mojibake(message)
            self.statusBar().showMessage(self._tr("status_source_filter_failed").format(detail=detail))

    def _source_audio_filter_warning(self, source_path: str, message: str) -> None:
        if self._video_path == source_path:
            detail = _repair_mojibake(message)
            self.statusBar().showMessage(self._tr("status_source_filter_warning").format(detail=detail))

    def _source_audio_filter_finished(self) -> None:
        if self._source_filter_worker is not None:
            self._source_filter_worker.deleteLater()
            self._source_filter_worker = None
        if self._source_filter_restart_pending and self._video_path and self._source_filter_check.isChecked():
            self._source_filter_restart_pending = False
            self._start_source_audio_filter(self._video_path)

    def _start_playback_compat(self, source_path: str) -> None:
        if self._playback_compat_worker is not None and self._playback_compat_worker.isRunning():
            return
        output_path = self._playback_compat_output_path(source_path)
        self._playback_compat_worker = PlaybackCompatibilityWorker(source_path, output_path, self)
        self._playback_compat_worker.ready.connect(self._playback_compat_ready)
        self._playback_compat_worker.failed.connect(self._playback_compat_failed)
        self._playback_compat_worker.finished.connect(self._playback_compat_finished)
        self._playback_compat_worker.start()
        self.statusBar().showMessage(self._tr("status_playback_compat_preparing"))

    def _playback_compat_ready(self, source_path: str, compat_path: str) -> None:
        expected_output = self._playback_compat_output_path(source_path)
        if Path(compat_path) != expected_output:
            return
        self._playback_compat_cache[self._playback_compat_cache_key(source_path)] = compat_path
        if self._video_path == source_path and not self._document_mode:
            self._switch_player_source(compat_path, preserve_state=True)
            self.statusBar().showMessage(self._tr("status_playback_compat_ready"))

    def _playback_compat_failed(self, source_path: str, message: str) -> None:
        if self._video_path == source_path:
            detail = _repair_mojibake(message)
            self.statusBar().showMessage(self._tr("status_playback_compat_failed").format(detail=detail))

    def _playback_compat_finished(self) -> None:
        if self._playback_compat_worker is not None:
            self._playback_compat_worker.deleteLater()
            self._playback_compat_worker = None

    @staticmethod
    def _can_filter_source_audio(source_path: str) -> bool:
        source = QUrl(source_path)
        if source.scheme() in {"http", "https", "rtsp", "rtmp", "mms"}:
            return False
        return Path(source_path).exists()

    @staticmethod
    def _is_qt_unsafe_local_video(source_path: str) -> bool:
        source = QUrl(source_path)
        if source.scheme() in {"http", "https", "rtsp", "rtmp", "mms"}:
            return False
        if not Path(source_path).exists():
            return False
        ffprobe = ffprobe_executable()
        if not ffprobe:
            return False
        try:
            result = subprocess.run(
                [
                    ffprobe,
                    "-v",
                    "error",
                    "-select_streams",
                    "v:0",
                    "-show_entries",
                    "stream=codec_name",
                    "-of",
                    "default=noprint_wrappers=1:nokey=1",
                    source_path,
                ],
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
        except Exception:
            return False
        codec = (result.stdout or "").strip().lower()
        return codec in {"av1"}

    @staticmethod
    def _is_qt_compatible_local_video(source_path: str) -> bool:
        source = QUrl(source_path)
        if source.scheme() in {"http", "https", "rtsp", "rtmp", "mms"}:
            return False
        path = Path(source_path)
        if not path.exists() or path.suffix.lower() not in {".mp4", ".m4v", ".mov"}:
            return False
        cache_key = PlayerMediaMixin._local_video_cache_key(path)
        if cache_key is not None and cache_key in _QT_COMPAT_VIDEO_CACHE:
            return _QT_COMPAT_VIDEO_CACHE[cache_key]
        compatible = PlayerMediaMixin._probe_qt_compatible_local_video(source_path)
        if cache_key is not None:
            _QT_COMPAT_VIDEO_CACHE[cache_key] = compatible
        return compatible

    @staticmethod
    def _probe_qt_compatible_local_video(source_path: str) -> bool:
        ffprobe = ffprobe_executable()
        if not ffprobe:
            return False
        try:
            result = subprocess.run(
                [
                    ffprobe,
                    "-v",
                    "error",
                    "-show_entries",
                    "stream=codec_type,codec_name,pix_fmt",
                    "-of",
                    "json",
                    source_path,
                ],
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            if result.returncode != 0:
                return False
            data = json.loads(result.stdout or "{}")
        except Exception:
            return False
        streams = data.get("streams") if isinstance(data, dict) else None
        if not isinstance(streams, list):
            return False
        video_streams = [
            stream for stream in streams if isinstance(stream, dict) and stream.get("codec_type") == "video"
        ]
        audio_streams = [
            stream for stream in streams if isinstance(stream, dict) and stream.get("codec_type") == "audio"
        ]
        if not video_streams:
            return False
        video = video_streams[0]
        video_codec = str(video.get("codec_name") or "").lower()
        pixel_format = str(video.get("pix_fmt") or "").lower()
        if video_codec != "h264" or pixel_format not in {"", "yuv420p"}:
            return False
        return all(str(stream.get("codec_name") or "").lower() in {"aac", "mp3", "alac"} for stream in audio_streams)

    @staticmethod
    def _local_video_cache_key(path: Path) -> tuple[str, int, int] | None:
        try:
            stat = path.stat()
            resolved = path.resolve()
        except OSError:
            return None
        return (str(resolved), int(stat.st_mtime_ns), int(stat.st_size))

    @staticmethod
    def _needs_qt_playback_compat(source_path: str) -> bool:
        source = QUrl(source_path)
        if source.scheme() in {"http", "https", "rtsp", "rtmp", "mms"}:
            return False
        path = Path(source_path)
        if not path.exists():
            return False
        if _is_ytdlp_source_cache(path):
            return not PlayerMediaMixin._is_qt_compatible_local_video(source_path)
        return PlayerMediaMixin._is_qt_unsafe_local_video(source_path)

    @staticmethod
    def _source_filter_output_path(source_path: str, mode: str = "auto", model: str = "htdemucs") -> Path:
        stat_key = PlayerMediaMixin._source_stat_key(source_path)
        signature = source_voice_filter_signature(mode, model=model)
        digest = hashlib.sha1(
            f"{source_path}{stat_key}:source-filter:{signature}".encode("utf-8", errors="replace")
        ).hexdigest()[:16]
        root = Path(tempfile.gettempdir()) / "ai-player-source-filter"
        _cleanup_cache_root(root, max_bytes=10 * 1024 * 1024 * 1024)
        return root / f"{digest}.mp4"

    def _source_filter_cache_key(
        self,
        source_path: str,
        mode: str | None = None,
        backend: str | None = None,
        model: str | None = None,
    ) -> str:
        selected_mode = self._selected_source_filter_mode() if mode is None else mode
        if model is None and hasattr(self, "_selected_source_filter_model"):
            selected_model = self._selected_source_filter_model()
        else:
            selected_model = model
        selected_model = selected_model or "htdemucs"
        signature = source_voice_filter_signature(selected_mode, backend, selected_model)
        return f"{source_path}{self._source_stat_key(source_path)}:{signature}"

    @staticmethod
    def _playback_compat_output_path(source_path: str) -> Path:
        stat_key = PlayerMediaMixin._source_stat_key(source_path)
        digest = hashlib.sha1(
            f"{source_path}{stat_key}:qt-playback-main-h264-720p-v2".encode("utf-8", errors="replace")
        ).hexdigest()[:16]
        root = Path(tempfile.gettempdir()) / "ai-player-playback-cache"
        _cleanup_cache_root(root, max_bytes=10 * 1024 * 1024 * 1024)
        return root / f"{digest}.mp4"

    @staticmethod
    def _playback_compat_cache_key(source_path: str) -> str:
        return f"{source_path}{PlayerMediaMixin._source_stat_key(source_path)}:qt-playback-main-h264-720p-v2"

    @staticmethod
    def _source_stat_key(source_path: str) -> str:
        try:
            source_stat = Path(source_path).stat()
        except OSError:
            return ""
        return f":{source_stat.st_mtime_ns}:{source_stat.st_size}"

    def _set_document_mode(self, enabled: bool, duration_ms: int = 0, pages=None) -> None:
        self._document_mode = enabled
        self._document_elapsed_ms = 0
        self._document_started_at = None
        self._document_audio_sync_active = False
        self._document_duration_ms = max(0, int(duration_ms))
        self._document_pages = list(pages or [])
        self._document_current_page_index = -1
        if enabled:
            self._media_stack.setCurrentWidget(self._document_view)
            self._apply_media_aspect_ratio()
            self._position_slider.setValue(0)
            self._time_label.setText(f"00:00 / {self._format_ms(self._document_duration_ms)}")
            self._update_document_page(force=True)
        else:
            if hasattr(self, "_media_stack"):
                target = self._video_widget if self._video_path else self._video_placeholder
                self._media_stack.setCurrentWidget(target)
            self._apply_media_aspect_ratio()
            if hasattr(self, "_document_view"):
                self._document_view.clear()

    def _apply_media_aspect_ratio(self) -> None:
        if not self._media_frame:
            return
        if self._video_fullscreen:
            self._apply_fullscreen_media_size()
            return
        if self._sidebar_panel_hidden:
            self._media_frame.setMinimumSize(0, 0)
            self._media_frame.setMaximumSize(16777215, 16777215)
            self._position_subtitle_overlay()
            self._refresh_document_page_for_media_size()
            return
        panel = self._media_frame.parentWidget()
        if panel and panel.layout():
            margins = panel.layout().contentsMargins()
            spacing = panel.layout().spacing()
            controls_height = self._media_controls_height()
            max_width = max(160, panel.width() - margins.left() - margins.right())
            max_height = max(
                120,
                panel.height() - margins.top() - margins.bottom() - controls_height - spacing,
            )
        else:
            available = self._media_stack.size()
            max_width = max(160, available.width() - 4)
            max_height = max(120, available.height() - 4)
        if self._selected_video_aspect_ratio() == "9:16":
            ratio_width, ratio_height = 9, 16
        else:
            ratio_width, ratio_height = 16, 9
        width = max_width
        height = int(width * ratio_height / ratio_width)
        if height > max_height:
            height = max_height
            width = int(height * ratio_width / ratio_height)
        self._media_frame.setFixedSize(max(1, width), max(1, height))
        self._position_subtitle_overlay()
        self._refresh_document_page_for_media_size()

    def _refresh_document_page_for_media_size(self) -> None:
        if self._document_mode and self._document_pages:
            self._update_document_page(force=True)

    def _play_active_source(self) -> None:
        if self._document_mode:
            if self._document_started_at is None:
                self._document_started_at = time.monotonic()
            return
        if self._should_delay_video_playback():
            delay_ms = int(self._video_delay_slider.value()) * 1000
            self._video_delay_active = True
            self._video_delay_timer.start(delay_ms)
            self.statusBar().showMessage(
                self._tr("status_video_delay").format(seconds=self._video_delay_slider.value())
            )
            return
        self._player.play()

    def _pause_active_source(self) -> None:
        self._cancel_delayed_video_playback()
        if self._document_mode:
            self._document_elapsed_ms = self._document_time_ms()
            self._document_started_at = None
            return
        self._player.pause()

    def _should_delay_video_playback(self) -> bool:
        return (
            not self._video_delay_active
            and self._dub_button.isChecked()
            and self._dubbing_ready
            and int(self._video_delay_slider.value()) > 0
            and not self._player.is_playing()
        )

    def _source_is_playing_for_dubbing(self) -> bool:
        if self._document_mode:
            return self._document_is_playing()
        return self._player.is_playing() or self._video_delay_active

    def _finish_delayed_video_playback(self) -> None:
        if not self._video_delay_active:
            return
        self._video_delay_active = False
        if self._video_path and self._dub_button.isChecked():
            self._player.play()

    def _cancel_delayed_video_playback(self) -> None:
        if self._video_delay_timer.isActive():
            self._video_delay_timer.stop()
        self._video_delay_active = False

    def _document_time_ms(self) -> int:
        if not self._document_mode:
            return 0
        elapsed = self._document_elapsed_ms
        if self._document_started_at is not None and not self._document_audio_sync_active:
            elapsed += int((time.monotonic() - self._document_started_at) * 1000)
        if self._document_duration_ms:
            return min(elapsed, self._document_duration_ms)
        return elapsed

    def _document_is_playing(self) -> bool:
        return self._document_mode and self._document_started_at is not None

    def _update_document_page(self, force: bool = False) -> None:
        if not self._document_mode or not self._document_pages:
            return
        current_seconds = self._document_time_ms() / 1000.0
        page_index = 0
        for index, page in enumerate(self._document_pages):
            start = float(page.start_seconds)
            end = start + float(page.duration_seconds)
            if start <= current_seconds < end:
                page_index = index
                break
            if current_seconds >= end:
                page_index = index
        if not force and page_index == self._document_current_page_index:
            return
        self._document_current_page_index = page_index
        page = self._document_pages[page_index]
        title = html.escape(f"{page.title} / {len(self._document_pages)}")
        image_path = str(getattr(page, "image_path", "") or "").replace("\\", "/")
        if not image_path:
            body = html.escape(page.text).replace("\n", "<br>")
            self._document_view.setHtml(
                "<div style='color:#52657a; font-size:15px; font-weight:600; margin-bottom:16px;'>"
                f"{title}"
                "</div>"
                "<div style='color:#172033; font-size:24px; line-height:1.55; padding:36px 48px;'>"
                f"{body}</div>"
            )
            return
        width, height = self._fit_document_image_size(image_path)
        size_attr = f" width='{width}' height='{height}'" if width and height else ""
        self._document_view.setHtml(
            "<body style='margin:0; padding:0; overflow:hidden;'>"
            "<div style='height:26px; color:#52657a; font-size:15px; font-weight:600; "
            "line-height:22px; padding:0 4px;'>"
            f"{title}</div>"
            "<div style='text-align:center; overflow:hidden;'>"
            f"<img src='file:///{html.escape(image_path)}'{size_attr} />"
            "</div>"
            "</body>"
        )

    def _fit_document_image_size(self, image_path: str) -> tuple[int, int]:
        pixmap = QPixmap(image_path)
        if pixmap.isNull():
            return (0, 0)
        viewport = self._document_view.viewport().size()
        available_width = max(120, viewport.width() - 12)
        available_height = max(90, viewport.height() - 34)
        scale = min(
            available_width / max(1, pixmap.width()),
            available_height / max(1, pixmap.height()),
        )
        return (max(1, int(pixmap.width() * scale)), max(1, int(pixmap.height() * scale)))

    def _position_subtitle_overlay(self) -> None:
        if not hasattr(self, "_subtitle_overlay") or not self._media_frame:
            return
        width = max(1, self._media_frame.width())
        font_size = self._subtitle_font_size()
        height = min(
            max(80, int(font_size * 3.4)),
            max(48, int(self._media_frame.height() * 0.24)),
        )
        x = 0
        y = max(0, self._media_frame.height() - height)
        top_left = self._media_frame.mapToGlobal(QPoint(x, y))
        self._subtitle_overlay.setGeometry(top_left.x(), top_left.y(), width, height)

    def _subtitle_font_size(self) -> int:
        if hasattr(self, "_subtitle_size_combo"):
            value = self._subtitle_size_combo.currentData()
            if value:
                return int(value)
        return 24

    def _subtitle_color(self) -> str:
        if hasattr(self, "_subtitle_color_combo"):
            value = self._subtitle_color_combo.currentData()
            if value:
                return str(value)
        return "#ffffff"

    def _subtitle_background_color(self) -> str:
        if hasattr(self, "_subtitle_background_combo"):
            value = self._subtitle_background_combo.currentData()
            if value:
                return str(value)
        return "rgba(0, 0, 0, 0)"

    def _apply_subtitle_overlay_style(self) -> None:
        if not hasattr(self, "_subtitle_overlay"):
            return
        font_size = self._subtitle_font_size()
        color = self._subtitle_color()
        background_color = self._subtitle_background_color()
        if hasattr(self._subtitle_overlay, "setSubtitleBackgroundColor"):
            self._subtitle_overlay.setSubtitleBackgroundColor(background_color)
        self._subtitle_overlay.setStyleSheet(
            "background-color: transparent;"
            "border: none;"
            "outline: none;"
            f"color: {color};"
            f"font-size: {font_size}px;"
            "font-weight: 800;"
            "padding: 0;"
            "margin: 0;"
        )

    def _load_subtitle_entries_for_overlay(self) -> None:
        path = self._transcript_path_edit.text().strip()
        if not path or path == self._subtitle_entries_path:
            return
        try:
            self._subtitle_entries = _load_transcript_entries(
                path,
                max(1, int(self._config.segment_seconds)),
                self._config.gui_language,
            )
            self._subtitle_entries_path = path
        except Exception as exc:
            self._subtitle_entries = []
            self._subtitle_entries_path = ""
            self._last_subtitle_text = ""
            self._subtitle_overlay.hide()
            self.statusBar().showMessage(
                self._tr("status_subtitle_load_failed").format(detail=_repair_mojibake(str(exc)))
            )

    def _update_subtitle_overlay(self) -> None:
        mode = self._selected_subtitle_mode()
        if mode == "off":
            return
        self._load_subtitle_entries_for_overlay()
        current_seconds = (
            self._document_time_ms() / 1000.0 if self._document_mode else self._player.get_time_ms() / 1000.0
        )
        text = ""
        if self._subtitle_entries:
            for entry in self._subtitle_entries:
                end = entry.end if entry.end is not None else entry.start + max(1, self._config.segment_seconds)
                if float(entry.start) <= current_seconds < float(end):
                    text = _repair_mojibake(entry.text.strip())
                    break
        if not text and time.monotonic() <= self._live_subtitle_expires_at:
            text = self._live_subtitle_source_text if mode == "source" else self._live_subtitle_target_text
        if not text:
            self._last_subtitle_text = ""
            self._subtitle_overlay.hide()
            return
        if text != self._last_subtitle_text:
            self._subtitle_overlay.setText(text)
            self._last_subtitle_text = text
        self._apply_subtitle_overlay_style()
        self._position_subtitle_overlay()
        self._subtitle_overlay.show()
        self._subtitle_overlay.raise_()

    def _previous_document_page(self) -> None:
        if not self._document_mode or not self._document_pages:
            return
        self._jump_to_document_page(max(0, self._document_current_page_index - 1))

    def _next_document_page(self) -> None:
        if not self._document_mode or not self._document_pages:
            return
        self._jump_to_document_page(min(len(self._document_pages) - 1, self._document_current_page_index + 1))

    def _jump_to_document_page(self, page_index: int) -> None:
        page_index = max(0, min(page_index, len(self._document_pages) - 1))
        page = self._document_pages[page_index]
        self._document_audio_sync_active = False
        self._document_elapsed_ms = int(float(page.start_seconds) * 1000)
        self._document_started_at = None
        self._update_document_page(force=True)
        total = max(1, self._document_duration_ms)
        self._position_slider.setValue(int(self._document_elapsed_ms / total * 1000))
        self._time_label.setText(
            f"{self._format_ms(self._document_elapsed_ms)} / {self._format_ms(self._document_duration_ms)}"
        )
        self._stop_dubbing()
        self._dubbing_auto_enabled = True
        self._dub_button.setChecked(True)
        self._start_dubbing()

    def _sync_document_to_audio_start(self, start_seconds: float) -> None:
        if not self._document_mode:
            return
        was_playing = self._document_started_at is not None
        self._document_audio_sync_active = True
        self._document_elapsed_ms = max(0, int(float(start_seconds) * 1000))
        self._document_started_at = time.monotonic() if was_playing else None
        self._update_document_page(force=True)
        self._update_subtitle_overlay()

    def _pause_for_dubbing_buffer(self, message: str) -> None:
        self._set_dubbing_ready(False, message)
        self._pause_active_source()
        self.statusBar().showMessage(message)

    def _resume_after_dubbing_buffer(self, message: str) -> None:
        self._set_dubbing_ready(True, message)
        if self._dub_button.isChecked() and self._video_path:
            self._play_active_source()
        self.statusBar().showMessage(message)

    def _set_volume(self, value: int) -> None:
        self._player.set_volume(value)

    def _set_dub_volume_status(self, value: int) -> None:
        self.statusBar().showMessage(self._tr("status_dub_volume").format(value=value))

    def _toggle_video_fullscreen(self) -> None:
        self._set_video_fullscreen(not self._video_fullscreen)

    def _exit_video_fullscreen(self) -> None:
        if self._video_fullscreen:
            self._set_video_fullscreen(False)

    def _handle_escape_shortcut(self) -> None:
        if self._video_fullscreen:
            self._set_video_fullscreen(False)
        if self._sidebar_panel_hidden:
            self._set_sidebar_panel_visible(True)

    def _set_video_fullscreen(self, enabled: bool) -> None:
        if enabled == self._video_fullscreen:
            return
        if enabled:
            self._enter_media_fullscreen()
        else:
            self._leave_media_fullscreen()
        self._video_fullscreen_changed(enabled)

    def _enter_media_fullscreen(self) -> None:
        if not self._media_frame:
            return
        parent = self._media_frame.parentWidget()
        layout = parent.layout() if parent else None
        self._media_frame_parent = parent
        self._media_frame_layout = layout
        self._media_frame_index = -1
        self._media_frame_alignment = Qt.AlignmentFlag(0)
        if layout is not None:
            self._media_frame_index = layout.indexOf(self._media_frame)
            item = layout.itemAt(self._media_frame_index)
            if item is not None:
                self._media_frame_alignment = item.alignment()
            layout.removeWidget(self._media_frame)
        self._media_frame.setParent(None)
        self._media_frame.setWindowFlag(Qt.Window, True)
        self._media_frame.showFullScreen()
        self._media_frame.activateWindow()
        self._media_frame.raise_()
        self._media_frame.setFocus(Qt.ActiveWindowFocusReason)
        self._apply_fullscreen_media_size()

    def _leave_media_fullscreen(self) -> None:
        if not self._media_frame:
            return
        self._media_frame.hide()
        self._media_frame.showNormal()
        self._media_frame.setWindowFlag(Qt.Window, False)
        if self._media_frame_layout is not None and self._media_frame_parent is not None:
            self._media_frame.setParent(self._media_frame_parent)
            if self._media_frame_index >= 0:
                self._media_frame_layout.insertWidget(
                    self._media_frame_index,
                    self._media_frame,
                    1,
                    self._media_frame_alignment,
                )
            else:
                self._media_frame_layout.addWidget(self._media_frame, 1, self._media_frame_alignment)
        self._media_frame.show()
        self._media_frame_parent = None
        self._media_frame_layout = None
        self._media_frame_index = -1
        self._media_frame_alignment = Qt.AlignmentFlag(0)
        self._apply_media_aspect_ratio()

    def _apply_fullscreen_media_size(self) -> None:
        if not self._media_frame:
            return
        screen = self._media_frame.screen() or self.screen()
        if screen is None:
            return
        geometry = screen.geometry()
        self._media_frame.setFixedSize(geometry.size())
        self._media_frame.move(geometry.topLeft())
        self._position_subtitle_overlay()
        if self._document_mode and self._document_pages:
            self._update_document_page(force=True)

    def _video_fullscreen_changed(self, enabled: bool) -> None:
        self._video_fullscreen = enabled
        tooltip_key = "exit_fullscreen" if enabled else "fullscreen_tooltip"
        self._video_fullscreen_button.setText("")
        self._video_fullscreen_button.setToolTip(self._tr(tooltip_key))
        self._video_fullscreen_button.setProperty("i18n_tooltip_key", tooltip_key)
        self.statusBar().showMessage(
            self._tr("status_fullscreen_entered") if enabled else self._tr("status_fullscreen_exited")
        )

    def eventFilter(self, watched, event) -> bool:
        media_widgets = {
            self._video_widget,
            self._video_placeholder,
            self._document_view,
            self._media_stack,
            self._media_frame,
        }
        if watched in media_widgets:
            if event.type() == QEvent.Type.MouseButtonDblClick:
                self._toggle_video_fullscreen()
                return True
            if event.type() == QEvent.Type.KeyPress and event.key() in (Qt.Key.Key_Escape, Qt.Key.Key_F11):
                if event.key() == Qt.Key.Key_Escape:
                    self._handle_escape_shortcut()
                else:
                    self._toggle_video_fullscreen()
                return True
        return super().eventFilter(watched, event)

    def _toggle_sidebar_panel(self) -> None:
        self._set_sidebar_panel_visible(self._sidebar_panel_hidden)

    def _media_controls_height(self) -> int:
        if not hasattr(self, "_controls") or self._controls.isHidden():
            return 0
        return self._controls.sizeHint().height()

    def _set_header_controls_visible(self, visible: bool) -> None:
        for widget in getattr(self, "_header_controls", ()):
            widget.setVisible(visible)

    def _set_focus_media_property(self, enabled: bool) -> None:
        widgets = (
            getattr(self, "_video_panel", None),
            self._media_frame,
            getattr(self, "_video_placeholder", None),
            getattr(self, "_media_stack", None),
        )
        original_shapes = getattr(self, "_focus_media_frame_shapes", None)
        if original_shapes is None:
            original_shapes = {}
            self._focus_media_frame_shapes = original_shapes
        for widget in widgets:
            if widget is None:
                continue
            original_shape = None
            if isinstance(widget, QFrame):
                key = id(widget)
                original_shapes.setdefault(key, widget.frameShape())
                original_shape = original_shapes[key]
            widget.setProperty("focusMedia", enabled)
            style = widget.style()
            style.unpolish(widget)
            style.polish(widget)
            if original_shape is not None:
                widget.setFrameShape(QFrame.Shape.NoFrame if enabled else original_shape)
            widget.update()

    @staticmethod
    def _layout_margins(layout) -> tuple[int, int, int, int]:
        margins = layout.contentsMargins()
        return margins.left(), margins.top(), margins.right(), margins.bottom()

    @staticmethod
    def _set_layout_margins(layout, margins: tuple[int, int, int, int]) -> None:
        layout.setContentsMargins(*margins)

    def _focus_media_layout_state(self) -> dict[str, object]:
        state = getattr(self, "_focus_media_layout_state_cache", None)
        if state is None:
            state = {}
            if hasattr(self, "_root_layout"):
                state["root_margins"] = self._layout_margins(self._root_layout)
                state["root_spacing"] = self._root_layout.spacing()
            if hasattr(self, "_video_layout"):
                state["video_margins"] = self._layout_margins(self._video_layout)
                state["video_spacing"] = self._video_layout.spacing()
                if self._media_frame:
                    item = self._video_layout.itemAt(self._video_layout.indexOf(self._media_frame))
                    state["media_alignment"] = item.alignment() if item is not None else Qt.AlignCenter
            self._focus_media_layout_state_cache = state
        return state

    def _set_focus_media_chrome(self, enabled: bool) -> None:
        state = self._focus_media_layout_state()
        self._set_focus_media_property(enabled)
        if hasattr(self, "_root_layout"):
            if enabled:
                self._root_layout.setContentsMargins(0, 0, 0, 0)
            else:
                self._set_layout_margins(self._root_layout, state.get("root_margins", (14, 12, 14, 10)))
            self._root_layout.setSpacing(0 if enabled else int(state.get("root_spacing", 10)))
        if hasattr(self, "_video_layout"):
            if enabled:
                self._video_layout.setContentsMargins(0, 0, 0, 0)
            else:
                self._set_layout_margins(self._video_layout, state.get("video_margins", (12, 12, 12, 12)))
            self._video_layout.setSpacing(0 if enabled else int(state.get("video_spacing", 10)))
            if self._media_frame:
                self._video_layout.setAlignment(
                    self._media_frame,
                    Qt.AlignmentFlag(0) if enabled else state.get("media_alignment", Qt.AlignCenter),
                )
        self.statusBar().setVisible(not enabled)

    def _set_sidebar_panel_visible(self, visible: bool) -> None:
        if not hasattr(self, "_settings_scroll"):
            return
        if visible:
            self._set_focus_media_chrome(False)
            if hasattr(self, "_source_bar"):
                self._source_bar.show()
            self._settings_scroll.show()
            if hasattr(self, "_controls"):
                self._controls.show()
            self._set_header_controls_visible(True)
            self._sidebar_panel_hidden = False
            self._splitter.setSizes(self._sidebar_panel_sizes or [900, 460])
            self._panel_toggle_button.setText("")
            self._panel_toggle_button.setProperty("i18n_key", None)
            self.statusBar().showMessage(self._tr("status_panel_shown"))
        else:
            sizes = self._splitter.sizes()
            if len(sizes) >= 2 and sizes[1] > 0:
                self._sidebar_panel_sizes = sizes
            self._set_focus_media_chrome(True)
            if hasattr(self, "_source_bar"):
                self._source_bar.hide()
            self._settings_scroll.hide()
            if hasattr(self, "_controls"):
                self._controls.hide()
            self._set_header_controls_visible(False)
            self._sidebar_panel_hidden = True
            self._panel_toggle_button.setText("")
            self._panel_toggle_button.setProperty("i18n_key", None)
            self.statusBar().showMessage(self._tr("status_panel_hidden"))
        self._apply_media_aspect_ratio()
        QTimer.singleShot(0, self._apply_media_aspect_ratio)

    def _reset_panel_sizes(self, show_status: bool = True) -> None:
        self._set_focus_media_chrome(False)
        if hasattr(self, "_source_bar"):
            self._source_bar.show()
        if hasattr(self, "_settings_scroll"):
            self._settings_scroll.show()
        if hasattr(self, "_controls"):
            self._controls.show()
        self._set_header_controls_visible(True)
        self._sidebar_panel_hidden = False
        self._sidebar_panel_sizes = [900, 460]
        self._splitter.setSizes([900, 460])
        if hasattr(self, "_panel_toggle_button"):
            self._panel_toggle_button.setText("")
            self._panel_toggle_button.setProperty("i18n_key", None)
        self._apply_media_aspect_ratio()
        QTimer.singleShot(0, self._apply_media_aspect_ratio)
        if show_status:
            self.statusBar().showMessage(self._tr("status_panel_size_reset"))

    def _begin_seek(self) -> None:
        self._is_seeking = True

    def _end_seek(self) -> None:
        self._is_seeking = False
        if self._document_mode:
            self._document_audio_sync_active = False
            self._document_elapsed_ms = int(self._position_slider.value() / 1000.0 * self._document_duration_ms)
            if self._document_started_at is not None:
                self._document_started_at = time.monotonic()
        else:
            self._player.set_position(self._position_slider.value() / 1000.0)
        if self._dub_button.isChecked():
            self._stop_dubbing()
            self._dub_button.setChecked(True)
            self._start_dubbing()

    def _refresh_position(self) -> None:
        if self._document_mode:
            current = self._document_time_ms()
            total = self._document_duration_ms
            self._update_document_page()
            self._update_subtitle_overlay()
            if not self._is_seeking and total > 0:
                self._position_slider.setValue(int(current / total * 1000))
            self._time_label.setText(f"{self._format_ms(current)} / {self._format_ms(total)}")
            if total > 0 and current >= total and self._document_started_at is not None:
                self._document_elapsed_ms = total
                self._document_started_at = None
            return

        if not self._is_seeking:
            position = int(self._player.get_position() * 1000)
            if position >= 0:
                self._position_slider.setValue(position)

        current = self._player.get_time_ms()
        total = self._player.get_length_ms()
        self._update_subtitle_overlay()
        self._time_label.setText(f"{self._format_ms(current)} / {self._format_ms(total)}")

    @staticmethod
    def _format_ms(value: int) -> str:
        seconds = max(0, value // 1000)
        minutes, seconds = divmod(seconds, 60)
        hours, minutes = divmod(minutes, 60)
        if hours:
            return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        return f"{minutes:02d}:{seconds:02d}"
