from __future__ import annotations

import hashlib
import html
import json
import math
import subprocess
import tempfile
import time
from pathlib import Path

from PySide6.QtCore import QEvent, QPoint, Qt, QTimer, QUrl
from PySide6.QtGui import QColor, QFont, QPalette, QPixmap
from PySide6.QtWidgets import QApplication, QFrame, QMainWindow, QStyle

from ai_player.adapters.media.ffmpeg import ffprobe_executable
from ai_player.adapters.media.source_voice_filter import source_voice_filter_signature
from ai_player.adapters.sources.video_source import _cleanup_cache_root
from ai_player.adapters.storage.media_cache import playback_compat_cached_output_valid
from ai_player.application.formats.transcript_source import load_transcript_entries as _load_transcript_entries
from ai_player.core.redaction import redact_secrets
from ai_player.ui.features.base import Feature
from ai_player.ui.player_window_utils import (
    is_ytdlp_source_cache as _is_ytdlp_source_cache,
)
from ai_player.ui.player_window_utils import (
    repair_mojibake as _repair_mojibake,
)
from ai_player.workers.player_window_workers import PlaybackCompatibilityWorker, SourceAudioFilterWorker

_QT_COMPAT_VIDEO_CACHE: dict[tuple[str, int, int], bool] = {}
DEFAULT_SIDEBAR_PANEL_WIDTH = 360
DEFAULT_SIDEBAR_PANEL_SIZES = (1500, DEFAULT_SIDEBAR_PANEL_WIDTH)
PLAYBACK_COMPAT_CACHE_SIGNATURE = "qt-playback-main-h264-source-v3"


def _is_offscreen_platform() -> bool:
    app = QApplication.instance()
    return bool(app is not None and app.platformName().lower() == "offscreen")


class PlayerMediaFeature(Feature):
    def _source_voice_filter_changed(self, checked: bool) -> None:
        self.context.settings._queue_save_settings()
        if self.context.has("_sync_source_filter_controls"):
            self.context.settings._sync_source_filter_controls()
        if self.context.media.document.mode or not self.context.channel_browser._video_path:
            return
        self.context.media._load_current_video_for_playback(preserve_state=True)
        state = self.context.settings._tr("state_on") if checked else self.context.settings._tr("state_off")
        self.context.window.statusBar().showMessage(
            self.context.settings._tr("status_source_filter_changed").format(state=state)
        )

    def _source_voice_filter_mode_changed(self, *_args) -> None:
        self.context.settings._queue_save_settings()
        if self.context.has("_sync_source_filter_controls"):
            self.context.settings._sync_source_filter_controls()
        if (
            self.context.layout._source_filter_check.isChecked()
            and not self.context.media.document.mode
            and self.context.channel_browser._video_path
        ):
            if (
                self.context.media.processing.source_filter_worker is not None
                and self.context.media.processing.source_filter_worker.isRunning()
            ):
                self.context.media.processing.source_filter_restart_pending = True
                self.context.media.processing.source_filter_worker.stop()
                self.context.window.statusBar().showMessage(self.context.settings._tr("status_source_filter_preparing"))
                return
            self.context.media._load_current_video_for_playback(preserve_state=True)

    def _load_current_video_for_playback(self, preserve_state: bool = False) -> None:
        if not self.context.channel_browser._video_path:
            return
        if self.context.layout._source_filter_check.isChecked() and self.context.media._can_filter_source_audio(
            self.context.channel_browser._video_path
        ):
            filter_key = self.context.media._source_filter_cache_key(self.context.channel_browser._video_path)
            filtered_path = self.context.media.processing.source_filter_cache.get(filter_key)
            if filtered_path and Path(filtered_path).exists():
                self.context.media._switch_player_source(filtered_path, preserve_state)
                return
            if self.context.media._needs_qt_playback_compat(self.context.channel_browser._video_path):
                self.context.layout._player.stop()
                self.context.window.statusBar().showMessage(self.context.settings._tr("status_compat_creating"))
            else:
                self.context.media._switch_player_source(self.context.channel_browser._video_path, preserve_state)
            self.context.media._start_source_audio_filter(self.context.channel_browser._video_path)
            return
        if self.context.media._needs_qt_playback_compat(self.context.channel_browser._video_path):
            compat_key = self.context.media._playback_compat_cache_key(self.context.channel_browser._video_path)
            compat_path = self.context.media.processing.playback_compat_cache.get(compat_key)
            if compat_path and Path(compat_path).exists():
                self.context.media._switch_player_source(compat_path, preserve_state)
                return
            output_path = self.context.media._playback_compat_output_path(self.context.channel_browser._video_path)
            if playback_compat_cached_output_valid(output_path, self.context.channel_browser._video_path, compat_key):
                self.context.media.processing.playback_compat_cache[compat_key] = str(output_path)
                self.context.media._switch_player_source(str(output_path), preserve_state)
                return
            self.context.layout._player.stop()
            self.context.media._start_playback_compat(self.context.channel_browser._video_path)
            return
        self.context.media._switch_player_source(self.context.channel_browser._video_path, preserve_state)

    def _switch_player_source(self, path: str, preserve_state: bool) -> None:
        was_playing = preserve_state and self.context.layout._player.is_playing()
        current_ms = self.context.layout._player.get_time_ms() if preserve_state else 0
        self.context.runtime.state.media_path = path
        self.context.runtime.state.media_info_text = self.context.runtime._runtime_media_info_text_current(force=True)
        self.context.layout._player.load(path)
        self.context.layout._player.set_volume(self.context.layout._volume_slider.value())
        if preserve_state and current_ms > 0:
            self.context.layout._player.set_time_ms(current_ms)
        if was_playing:
            self.context.layout._player.play()

    def _start_source_audio_filter(self, source_path: str) -> None:
        if (
            self.context.media.processing.source_filter_worker is not None
            and self.context.media.processing.source_filter_worker.isRunning()
        ):
            return
        mode = self.context.settings._selected_source_filter_mode()
        model = self.context.settings._selected_source_filter_model()
        output_path = self.context.media._source_filter_output_path(source_path, mode, model)
        worker = SourceAudioFilterWorker(
            source_path,
            output_path,
            mode,
            model,
            self.context.window,
        )
        self.context.media.processing.begin_source_filter(worker, mode=mode, model=model)
        worker.ready.connect(self.context.media._source_audio_filter_ready)
        worker.failed.connect(self.context.media._source_audio_filter_failed)
        worker.warning.connect(self.context.media._source_audio_filter_warning)
        worker.finished.connect(lambda worker=worker: self.context.media._source_audio_filter_finished(worker))
        worker.start()
        message = self.context.settings._tr("status_source_filter_preparing")
        self.context.runtime._set_background_task_detail("Source voice filter", message)
        self.context.window.statusBar().showMessage(message)

    def _source_audio_filter_ready(self, source_path: str, filtered_path: str, backend: str = "") -> None:
        worker_mode = self.context.get(
            "_source_filter_worker_mode", self.context.settings._selected_source_filter_mode()
        )
        worker_model = self.context.get(
            "_source_filter_worker_model", self.context.settings._selected_source_filter_model()
        )
        expected_output = self.context.media._source_filter_output_path(source_path, worker_mode, worker_model)
        if Path(filtered_path) != expected_output:
            return
        self.context.media.processing.source_filter_cache[
            self.context.media._source_filter_cache_key(source_path, worker_mode, backend, worker_model)
        ] = filtered_path
        if (
            self.context.channel_browser._video_path == source_path
            and self.context.layout._source_filter_check.isChecked()
            and not self.context.media.document.mode
        ):
            filter_changed = (
                worker_mode != self.context.settings._selected_source_filter_mode()
                or worker_model != self.context.settings._selected_source_filter_model()
            )
            if filter_changed:
                self.context.media.processing.source_filter_restart_pending = True
                return
            self.context.media._switch_player_source(filtered_path, preserve_state=True)
            self.context.runtime._clear_background_task_detail("Source voice filter")
            self.context.window.statusBar().showMessage(self.context.settings._tr("status_source_filter_ready"))
            if self.context.has("_play_pending_telegram_navigation"):
                self.context.sources._play_pending_telegram_navigation(source_path=source_path)

    def _source_audio_filter_failed(self, source_path: str, message: str) -> None:
        if self.context.channel_browser._video_path == source_path:
            detail = _repair_mojibake(message)
            self.context.runtime._set_background_task_detail("Source voice filter", detail)
            self.context.window.statusBar().showMessage(
                self.context.settings._tr("status_source_filter_failed").format(detail=detail)
            )

    def _source_audio_filter_warning(self, source_path: str, message: str) -> None:
        if self.context.channel_browser._video_path == source_path:
            detail = _repair_mojibake(message)
            self.context.runtime._set_background_task_detail("Source voice filter", detail)
            self.context.window.statusBar().showMessage(
                self.context.settings._tr("status_source_filter_warning").format(detail=detail)
            )

    def _source_audio_filter_finished(self, worker=None) -> None:
        worker = worker or self.context.media.processing.source_filter_worker
        if worker is not None and self.context.media.processing.finish_source_filter(worker):
            self.context.lifecycle.workers.delete_worker(worker)
        if (
            self.context.media.processing.source_filter_restart_pending
            and self.context.channel_browser._video_path
            and self.context.layout._source_filter_check.isChecked()
        ):
            self.context.media.processing.source_filter_restart_pending = False
            self.context.media._start_source_audio_filter(self.context.channel_browser._video_path)

    def _start_playback_compat(self, source_path: str) -> None:
        if (
            self.context.media.processing.playback_compat_worker is not None
            and self.context.media.processing.playback_compat_worker.isRunning()
        ):
            return
        output_path = self.context.media._playback_compat_output_path(source_path)
        cache_key = self.context.media._playback_compat_cache_key(source_path)
        worker = PlaybackCompatibilityWorker(source_path, output_path, cache_key, self.context.window)
        self.context.media.processing.begin_playback_compat(worker)
        worker.ready.connect(self.context.media._playback_compat_ready)
        worker.failed.connect(self.context.media._playback_compat_failed)
        worker.finished.connect(lambda worker=worker: self.context.media._playback_compat_finished(worker))
        worker.start()
        message = self.context.settings._tr("status_playback_compat_preparing")
        self.context.runtime._set_background_task_detail("Playback compatibility", message)
        self.context.window.statusBar().showMessage(message)

    def _playback_compat_ready(self, source_path: str, compat_path: str) -> None:
        expected_output = self.context.media._playback_compat_output_path(source_path)
        if Path(compat_path) != expected_output:
            return
        self.context.media.processing.playback_compat_cache[
            self.context.media._playback_compat_cache_key(source_path)
        ] = compat_path
        if self.context.channel_browser._video_path == source_path and not self.context.media.document.mode:
            self.context.media._switch_player_source(compat_path, preserve_state=True)
            self.context.runtime._clear_background_task_detail("Playback compatibility")
            self.context.window.statusBar().showMessage(self.context.settings._tr("status_playback_compat_ready"))
            if self.context.has("_play_pending_telegram_navigation"):
                self.context.sources._play_pending_telegram_navigation(source_path=source_path)

    def _playback_compat_failed(self, source_path: str, message: str) -> None:
        if self.context.channel_browser._video_path == source_path:
            detail = _repair_mojibake(message)
            self.context.runtime._set_background_task_detail("Playback compatibility", detail)
            self.context.window.statusBar().showMessage(
                self.context.settings._tr("status_playback_compat_failed").format(detail=detail)
            )

    def _playback_compat_finished(self, worker=None) -> None:
        worker = worker or self.context.media.processing.playback_compat_worker
        if worker is not None and self.context.media.processing.finish_playback_compat(worker):
            self.context.lifecycle.workers.delete_worker(worker)

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
        cache_key = PlayerMediaFeature._local_video_cache_key(path)
        if cache_key is not None and cache_key in _QT_COMPAT_VIDEO_CACHE:
            return _QT_COMPAT_VIDEO_CACHE[cache_key]
        compatible = PlayerMediaFeature._probe_qt_compatible_local_video(source_path)
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
            return not PlayerMediaFeature._is_qt_compatible_local_video(source_path)
        return PlayerMediaFeature._is_qt_unsafe_local_video(source_path)

    @staticmethod
    def _source_filter_output_path(source_path: str, mode: str = "auto", model: str = "htdemucs") -> Path:
        stat_key = PlayerMediaFeature._source_stat_key(source_path)
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
        selected_mode = self.context.settings._selected_source_filter_mode() if mode is None else mode
        if model is None and self.context.has("_selected_source_filter_model"):
            selected_model = self.context.settings._selected_source_filter_model()
        else:
            selected_model = model
        selected_model = selected_model or "htdemucs"
        signature = source_voice_filter_signature(selected_mode, backend, selected_model)
        return f"{source_path}{self.context.media._source_stat_key(source_path)}:{signature}"

    @staticmethod
    def _playback_compat_output_path(source_path: str) -> Path:
        stat_key = PlayerMediaFeature._source_stat_key(source_path)
        digest = hashlib.sha1(
            f"{source_path}{stat_key}:{PLAYBACK_COMPAT_CACHE_SIGNATURE}".encode("utf-8", errors="replace")
        ).hexdigest()[:16]
        root = Path(tempfile.gettempdir()) / "ai-player-playback-cache"
        _cleanup_cache_root(root, max_bytes=10 * 1024 * 1024 * 1024)
        return root / f"{digest}.mp4"

    @staticmethod
    def _playback_compat_cache_key(source_path: str) -> str:
        return f"{source_path}{PlayerMediaFeature._source_stat_key(source_path)}:{PLAYBACK_COMPAT_CACHE_SIGNATURE}"

    @staticmethod
    def _source_stat_key(source_path: str) -> str:
        try:
            source_stat = Path(source_path).stat()
        except OSError:
            return ""
        return f":{source_stat.st_mtime_ns}:{source_stat.st_size}"

    def _set_document_mode(self, enabled: bool, duration_ms: int = 0, pages=None) -> None:
        if enabled:
            self.context.media.document.enter_document(duration_ms=duration_ms, pages=pages)
        else:
            self.context.media.document.reset_for_video(reset_duration=True)
        if enabled:
            self.context.layout._media_stack.setCurrentWidget(self.context.layout._document_view)
            self.context.media._apply_media_aspect_ratio()
            self.context.layout._position_slider.setValue(0)
            self.context.layout._time_label.setText(
                f"00:00 / {self.context.media._format_ms(self.context.media.document.duration_ms)}"
            )
            self.context.media._update_document_page(force=True)
        else:
            if self.context.has("_media_stack"):
                if self.context.channel_browser._video_path and self.context.has("_show_video_output"):
                    self.context.channel_browser._show_video_output()
                else:
                    set_video_output = getattr(self.context.get("_player", None), "set_video_output", None)
                    if callable(set_video_output) and self.context.has("_video_widget"):
                        set_video_output(self.context.layout._video_widget)
                    self.context.layout._media_stack.setCurrentWidget(self.context.layout._video_placeholder)
            self.context.media._apply_media_aspect_ratio()
            if self.context.has("_document_view"):
                self.context.layout._document_view.clear()

    def _auto_select_video_aspect_ratio(self, source: object | None = None) -> None:
        if self.context.media.document.mode or not self.context.has("_aspect_combo"):
            return
        width, height = self.context.media._video_dimensions_from_source_metadata(source)
        if not width and not height and self.context.channel_browser._video_path:
            width, height = self.context.media._probe_video_dimensions(self.context.channel_browser._video_path)
        aspect = self.context.media._video_aspect_for_dimensions(width, height)
        if not aspect:
            return
        current = self.context.layout._aspect_combo.currentData()
        if current != aspect and self.context.has("_set_combo_data"):
            self.context.settings._set_combo_data(self.context.layout._aspect_combo, aspect)
            return
        self.context.media._apply_media_aspect_ratio()

    @staticmethod
    def _video_dimensions_from_source_metadata(source: object | None) -> tuple[int, int]:
        if source is None:
            return 0, 0
        return (
            PlayerMediaFeature._positive_video_dimension(getattr(source, "width", 0)),
            PlayerMediaFeature._positive_video_dimension(getattr(source, "height", 0)),
        )

    @staticmethod
    def _video_aspect_for_dimensions(width: int, height: int) -> str:
        width = PlayerMediaFeature._positive_video_dimension(width)
        height = PlayerMediaFeature._positive_video_dimension(height)
        if not width or not height:
            return ""
        return "9:16" if height > width else "16:9"

    @staticmethod
    def _probe_video_dimensions(source_path: str) -> tuple[int, int]:
        source = QUrl(source_path)
        if source.scheme() in {"http", "https", "rtsp", "rtmp", "mms"}:
            return 0, 0
        path = Path(source_path)
        if not path.exists():
            return 0, 0
        ffprobe = ffprobe_executable()
        if not ffprobe:
            return 0, 0
        try:
            result = subprocess.run(
                [
                    ffprobe,
                    "-v",
                    "error",
                    "-select_streams",
                    "v:0",
                    "-show_entries",
                    "stream=width,height:stream_tags=rotate:stream_side_data=rotation",
                    "-of",
                    "json",
                    source_path,
                ],
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=3.0,
            )
            if result.returncode != 0:
                return 0, 0
            data = json.loads(result.stdout or "{}")
        except Exception:
            return 0, 0
        streams = data.get("streams") if isinstance(data, dict) else None
        if not isinstance(streams, list) or not streams:
            return 0, 0
        stream = streams[0] if isinstance(streams[0], dict) else {}
        width = PlayerMediaFeature._positive_video_dimension(stream.get("width"))
        height = PlayerMediaFeature._positive_video_dimension(stream.get("height"))
        if width and height and PlayerMediaFeature._stream_rotation_is_vertical(stream):
            return height, width
        return width, height

    @staticmethod
    def _stream_rotation_is_vertical(stream: dict) -> bool:
        candidates = []
        tags = stream.get("tags")
        if isinstance(tags, dict):
            candidates.append(tags.get("rotate"))
        side_data = stream.get("side_data_list")
        if isinstance(side_data, list):
            candidates.extend(item.get("rotation") for item in side_data if isinstance(item, dict))
        for value in candidates:
            try:
                rotation = int(float(str(value or "").strip())) % 180
            except (OverflowError, TypeError, ValueError):
                continue
            if rotation == 90:
                return True
        return False

    @staticmethod
    def _positive_video_dimension(value: object) -> int:
        try:
            parsed = int(float(str(value or "").strip()))
        except (OverflowError, TypeError, ValueError):
            return 0
        return parsed if parsed > 0 else 0

    def _apply_media_aspect_ratio(self) -> None:
        if not self.context.media.frame.frame:
            return
        if self.context.media.playback.video_fullscreen:
            self.context.media._apply_fullscreen_media_size()
            return
        if self.context.media.playback.sidebar_panel_hidden:
            self.context.media.frame.frame.setMinimumSize(0, 0)
            self.context.media.frame.frame.setMaximumSize(16777215, 16777215)
            self.context.media._position_subtitle_overlay()
            self.context.media._refresh_document_page_for_media_size()
            return
        panel = self.context.media.frame.frame.parentWidget()
        if panel and panel.layout():
            margins = panel.layout().contentsMargins()
            spacing = panel.layout().spacing()
            controls_height = self.context.media._media_controls_height()
            max_width = max(160, panel.width() - margins.left() - margins.right())
            max_height = max(
                120,
                panel.height() - margins.top() - margins.bottom() - controls_height - spacing,
            )
        else:
            available = self.context.layout._media_stack.size()
            max_width = max(160, available.width() - 4)
            max_height = max(120, available.height() - 4)
        if self.context.layout._media_stack.currentWidget() is self.context.get("_media_start_page", None):
            self.context.media.frame.frame.setFixedSize(max_width, max_height)
            self.context.media._position_subtitle_overlay()
            return
        if self.context.layout._media_stack.currentWidget() is self.context.get("_telegram_channel_view", None):
            self.context.media.frame.frame.setFixedSize(max_width, max_height)
            self.context.media._position_subtitle_overlay()
            self.context.media._refresh_document_page_for_media_size()
            if self.context.has("_refresh_telegram_channel_thumbnail"):
                self.context.sources._refresh_telegram_channel_thumbnail()
            return
        if self.context.settings._selected_video_aspect_ratio() == "9:16":
            ratio_width, ratio_height = 9, 16
        else:
            ratio_width, ratio_height = 16, 9
        width = max_width
        height = int(width * ratio_height / ratio_width)
        if height > max_height:
            height = max_height
            width = int(height * ratio_width / ratio_height)
        self.context.media.frame.frame.setFixedSize(max(1, width), max(1, height))
        self.context.media._position_subtitle_overlay()
        self.context.media._refresh_document_page_for_media_size()

    def _refresh_document_page_for_media_size(self) -> None:
        if self.context.media.document.mode and self.context.media.document.pages:
            self.context.media._update_document_page(force=True)

    def _play_active_source(self) -> None:
        if self.context.media.document.mode:
            if self.context.media.document.started_at is None:
                self.context.media.document.started_at = time.monotonic()
            return
        if self.context.media._should_delay_video_playback():
            delay_ms = int(self.context.layout._video_delay_slider.value()) * 1000
            self.context.media.playback.video_delay_active = True
            self.context.layout._video_delay_timer.start(delay_ms)
            self.context.window.statusBar().showMessage(
                self.context.settings._tr("status_video_delay").format(
                    seconds=self.context.layout._video_delay_slider.value()
                )
            )
            return
        self.context.layout._player.play()

    def _pause_active_source(self) -> None:
        self.context.media._cancel_delayed_video_playback()
        if self.context.media.document.mode:
            self.context.media.document.elapsed_ms = self.context.media._document_time_ms()
            self.context.media.document.started_at = None
            return
        self.context.layout._player.pause()

    def _should_delay_video_playback(self) -> bool:
        return (
            not self.context.media.playback.video_delay_active
            and self.context.layout._dub_button.isChecked()
            and self.context.media.playback.dubbing_ready
            and int(self.context.layout._video_delay_slider.value()) > 0
            and not self.context.layout._player.is_playing()
        )

    def _source_is_playing_for_dubbing(self) -> bool:
        if self.context.media.document.mode:
            return self.context.media._document_is_playing()
        return self.context.layout._player.is_playing() or self.context.media.playback.video_delay_active

    def _finish_delayed_video_playback(self) -> None:
        if not self.context.media.playback.video_delay_active:
            return
        self.context.media.playback.video_delay_active = False
        if self.context.channel_browser._video_path and self.context.layout._dub_button.isChecked():
            self.context.layout._player.play()

    def _cancel_delayed_video_playback(self) -> None:
        if self.context.layout._video_delay_timer.isActive():
            self.context.layout._video_delay_timer.stop()
        self.context.media.playback.video_delay_active = False

    def _document_time_ms(self) -> int:
        if not self.context.media.document.mode:
            return 0
        elapsed = self.context.media.document.elapsed_ms
        if self.context.media.document.started_at is not None and not self.context.media.document.audio_sync_active:
            elapsed += int((time.monotonic() - self.context.media.document.started_at) * 1000)
        if self.context.media.document.duration_ms:
            return min(elapsed, self.context.media.document.duration_ms)
        return elapsed

    def _document_is_playing(self) -> bool:
        return self.context.media.document.mode and self.context.media.document.started_at is not None

    def _update_document_page(self, force: bool = False) -> None:
        if not self.context.media.document.mode or not self.context.media.document.pages:
            return
        current_seconds = self.context.media._document_time_ms() / 1000.0
        page_index = 0
        for index, page in enumerate(self.context.media.document.pages):
            start = _document_seconds_value(page.start_seconds)
            end = start + _document_seconds_value(page.duration_seconds)
            if start <= current_seconds < end:
                page_index = index
                break
            if current_seconds >= end:
                page_index = index
        if not force and page_index == self.context.media.document.current_page_index:
            return
        self.context.media.document.current_page_index = page_index
        page = self.context.media.document.pages[page_index]
        title = html.escape(f"{page.title} / {len(self.context.media.document.pages)}")
        image_path = str(getattr(page, "image_path", "") or "").replace("\\", "/")
        if not image_path:
            body = html.escape(page.text).replace("\n", "<br>")
            self.context.layout._document_view.setHtml(
                "<div style='color:#52657a; font-size:15px; font-weight:600; margin-bottom:16px;'>"
                f"{title}"
                "</div>"
                "<div style='color:#172033; font-size:24px; line-height:1.55; padding:36px 48px;'>"
                f"{body}</div>"
            )
            return
        width, height = self.context.media._fit_document_image_size(image_path)
        size_attr = f" width='{width}' height='{height}'" if width and height else ""
        self.context.layout._document_view.setHtml(
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
        viewport = self.context.layout._document_view.viewport().size()
        available_width = max(120, viewport.width() - 12)
        available_height = max(90, viewport.height() - 34)
        scale = min(
            available_width / max(1, pixmap.width()),
            available_height / max(1, pixmap.height()),
        )
        return (max(1, int(pixmap.width() * scale)), max(1, int(pixmap.height() * scale)))

    def _position_subtitle_overlay(self) -> None:
        if not self.context.has("_subtitle_overlay") or not self.context.media.frame.frame:
            return
        if self.context.layout._subtitle_overlay.parentWidget() is not None:
            self.context.layout._subtitle_overlay.setParent(None)
            self.context.layout._subtitle_overlay.setWindowFlags(
                Qt.Tool
                | Qt.FramelessWindowHint
                | Qt.NoDropShadowWindowHint
                | Qt.BypassWindowManagerHint
                | Qt.WindowDoesNotAcceptFocus
                | Qt.WindowStaysOnTopHint
            )
        width = max(1, self.context.media.frame.frame.width())
        font_size = self.context.media._subtitle_font_size()
        height = min(
            max(80, int(font_size * 3.4)),
            max(48, int(self.context.media.frame.frame.height() * 0.24)),
        )
        x = 0
        y = max(0, self.context.media.frame.frame.height() - height)
        top_left = self.context.media.frame.frame.mapToGlobal(QPoint(x, y))
        self.context.layout._subtitle_overlay.setGeometry(top_left.x(), top_left.y(), width, height)
        self.context.layout._subtitle_overlay.raise_()

    def _subtitle_font_size(self) -> int:
        if self.context.has("_subtitle_size_combo"):
            value = self.context.layout._subtitle_size_combo.currentData()
            if value:
                return int(value)
        return 24

    def _subtitle_color(self) -> str:
        if self.context.has("_subtitle_color_combo"):
            value = self.context.layout._subtitle_color_combo.currentData()
            if value:
                return str(value)
        return "#ffffff"

    def _subtitle_background_color(self) -> str:
        if self.context.has("_subtitle_background_combo"):
            value = self.context.layout._subtitle_background_combo.currentData()
            if value:
                return str(value)
        return "rgba(0, 0, 0, 0)"

    def _apply_subtitle_overlay_style(self) -> None:
        if not self.context.has("_subtitle_overlay"):
            return
        font_size = self.context.media._subtitle_font_size()
        color = self.context.media._subtitle_color()
        background_color = self.context.media._subtitle_background_color()
        if hasattr(self.context.layout._subtitle_overlay, "setSubtitleBackgroundColor"):
            self.context.layout._subtitle_overlay.setSubtitleBackgroundColor(background_color)
        self.context.layout._subtitle_overlay.setFrameShape(QFrame.Shape.NoFrame)
        self.context.layout._subtitle_overlay.setLineWidth(0)
        self.context.layout._subtitle_overlay.setMidLineWidth(0)
        self.context.layout._subtitle_overlay.setAutoFillBackground(False)
        self.context.layout._subtitle_overlay.setAttribute(Qt.WA_StyledBackground, False)
        self.context.layout._subtitle_overlay.setStyleSheet("")
        font = QFont(self.context.layout._subtitle_overlay.font())
        font.setPixelSize(font_size)
        font.setWeight(QFont.Weight.ExtraBold)
        self.context.layout._subtitle_overlay.setFont(font)
        palette = self.context.layout._subtitle_overlay.palette()
        text_color = QColor(color)
        palette.setColor(QPalette.ColorRole.WindowText, text_color if text_color.isValid() else QColor("#ffffff"))
        self.context.layout._subtitle_overlay.setPalette(palette)

    def _load_subtitle_entries_for_overlay(self) -> None:
        path = self.context.layout._transcript_path_edit.text().strip()
        if not path or path == self.context.transcript.state.entries_path:
            return
        try:
            self.context.transcript.state.entries = _load_transcript_entries(
                path,
                max(1, int(self.context.config.segment_seconds)),
                self.context.config.gui_language,
            )
            self.context.transcript.state.entries_path = path
        except Exception as exc:
            self.context.transcript.state.entries = []
            self.context.transcript.state.entries_path = ""
            self.context.transcript.state.last_text = ""
            self.context.layout._subtitle_overlay.hide()
            self.context.window.statusBar().showMessage(
                self.context.settings._tr("status_subtitle_load_failed").format(
                    detail=_repair_mojibake(redact_secrets(exc))
                )
            )

    def _update_subtitle_overlay(self) -> None:
        mode = self.context.sources._selected_subtitle_mode()
        if mode == "off":
            return
        self.context.media._load_subtitle_entries_for_overlay()
        current_seconds = (
            self.context.media._document_time_ms() / 1000.0
            if self.context.media.document.mode
            else self.context.layout._player.get_time_ms() / 1000.0
        )
        text = ""
        if self.context.transcript.state.entries:
            for entry in self.context.transcript.state.entries:
                end = entry.end if entry.end is not None else entry.start + max(1, self.context.config.segment_seconds)
                if float(entry.start) <= current_seconds < float(end):
                    text = _repair_mojibake(entry.text.strip())
                    break
        if not text:
            live_entries = self.context.get("_live_subtitle_entries", [])
            if live_entries:
                stale_before = max(0.0, current_seconds - max(30.0, float(self.context.config.segment_seconds) * 4.0))
                self.context.transcript.state.live_entries = [
                    entry for entry in live_entries if entry[1] >= stale_before
                ]
                mode_text_index = 2 if mode == "source" else 3
                for start, end, source_text, target_text in self.context.transcript.state.live_entries:
                    if float(start) <= current_seconds < float(end):
                        selected = source_text if mode_text_index == 2 else target_text
                        text = _repair_mojibake(str(selected or source_text).strip())
                        break
        if not text and time.monotonic() <= self.context.transcript.state.live_expires_at:
            text = (
                self.context.transcript.state.live_source_text
                if mode == "source"
                else self.context.transcript.state.live_target_text
            )
        if not text:
            self.context.transcript.state.last_text = ""
            self.context.layout._subtitle_overlay.hide()
            return
        if text != self.context.transcript.state.last_text:
            self.context.layout._subtitle_overlay.setText(text)
            self.context.transcript.state.last_text = text
        self.context.media._apply_subtitle_overlay_style()
        self.context.media._position_subtitle_overlay()
        self.context.layout._subtitle_overlay.show()
        self.context.layout._subtitle_overlay.raise_()

    def _previous_document_page(self) -> None:
        if not self.context.media.document.mode or not self.context.media.document.pages:
            return
        self.context.media._jump_to_document_page(max(0, self.context.media.document.current_page_index - 1))

    def _next_document_page(self) -> None:
        if not self.context.media.document.mode or not self.context.media.document.pages:
            return
        self.context.media._jump_to_document_page(
            min(len(self.context.media.document.pages) - 1, self.context.media.document.current_page_index + 1)
        )

    def _previous_media_item(self) -> None:
        if self.context.media.document.mode:
            self.context.media._previous_document_page()
            return
        if self.context.has("_open_adjacent_telegram_channel_video"):
            self.context.sources._open_adjacent_telegram_channel_video(-1)

    def _next_media_item(self) -> None:
        if self.context.media.document.mode:
            self.context.media._next_document_page()
            return
        if self.context.has("_open_adjacent_telegram_channel_video"):
            self.context.sources._open_adjacent_telegram_channel_video(1)

    def _jump_to_document_page(self, page_index: int) -> None:
        page_index = max(0, min(page_index, len(self.context.media.document.pages) - 1))
        page = self.context.media.document.pages[page_index]
        self.context.media.document.audio_sync_active = False
        self.context.media.document.elapsed_ms = _document_ms_value(page.start_seconds)
        self.context.media.document.started_at = None
        self.context.media._update_document_page(force=True)
        total = max(1, self.context.media.document.duration_ms)
        self.context.layout._position_slider.setValue(int(self.context.media.document.elapsed_ms / total * 1000))
        self.context.layout._time_label.setText(
            f"{self.context.media._format_ms(self.context.media.document.elapsed_ms)} / "
            f"{self.context.media._format_ms(self.context.media.document.duration_ms)}"
        )
        self.context.dubbing._stop_dubbing()
        self.context.media.playback.dubbing_auto_enabled = True
        self.context.layout._dub_button.setChecked(True)
        self.context.dubbing._start_dubbing()

    def _sync_document_to_audio_start(self, start_seconds: float) -> None:
        if not self.context.media.document.mode:
            return
        was_playing = self.context.media.document.started_at is not None
        self.context.media.document.audio_sync_active = True
        self.context.media.document.elapsed_ms = _document_ms_value(start_seconds)
        self.context.media.document.started_at = time.monotonic() if was_playing else None
        self.context.media._update_document_page(force=True)
        self.context.media._update_subtitle_overlay()

    def _pause_for_dubbing_buffer(self, message: str) -> None:
        self.context.ui._set_dubbing_ready(False, message)
        self.context.media._pause_active_source()
        self.context.window.statusBar().showMessage(message)

    def _resume_after_dubbing_buffer(self, message: str) -> None:
        self.context.ui._set_dubbing_ready(True, message)
        if self.context.layout._dub_button.isChecked() and self.context.channel_browser._video_path:
            self.context.media._play_active_source()
        self.context.window.statusBar().showMessage(message)

    def _set_volume(self, value: int) -> None:
        self.context.layout._player.set_volume(value)

    def _set_dub_volume_status(self, value: int) -> None:
        self.context.window.statusBar().showMessage(self.context.settings._tr("status_dub_volume").format(value=value))

    def _toggle_video_fullscreen(self) -> None:
        self.context.media._set_video_fullscreen(not self.context.media.playback.video_fullscreen)

    def _toggle_focus_media(self, *_args) -> None:
        self.context.media._set_focus_media_mode(not bool(self.context.get("_focus_media_enabled", False)))

    def _set_focus_media_mode(self, enabled: bool) -> None:
        enabled = bool(enabled)
        if enabled == bool(self.context.get("_focus_media_enabled", False)):
            return
        self.context.media._focus_media_enabled = enabled
        if enabled:
            self.context.media._focus_media_panel_state = {
                "top": not self.context.media.playback.top_panel_hidden,
                "bottom": not self.context.media.playback.bottom_panel_hidden,
                "sidebar": not self.context.media.playback.sidebar_panel_hidden,
                "drawer": bool(self.context.get("_task_drawer", None) and self.context.layout._task_drawer.isVisible()),
            }
            if self.context.has("_source_bar"):
                self.context.layout._source_bar.hide()
            if self.context.has("_settings_scroll"):
                sizes = self.context.layout._splitter.sizes()
                if len(sizes) >= 2 and sizes[1] > 0:
                    self.context.media.playback.sidebar_panel_sizes = sizes
                self.context.layout._settings_scroll.hide()
            if self.context.has("_task_drawer"):
                self.context.layout._task_drawer.hide()
            if self.context.has("_display_options_panel"):
                self.context.layout._display_options_panel.hide()
            self.context.media.playback.top_panel_hidden = True
            self.context.media.playback.bottom_panel_hidden = False
            self.context.media.playback.sidebar_panel_hidden = True
            self.context.media._set_focus_media_chrome(True)
            self.context.window.statusBar().showMessage(self.context.settings._tr("status_focus_media_enabled"))
        else:
            state = self.context.get("_focus_media_panel_state", {})
            if self.context.has("_source_bar"):
                self.context.layout._source_bar.setVisible(bool(state.get("top", True)))
            if self.context.has("_settings_scroll"):
                self.context.layout._settings_scroll.setVisible(bool(state.get("sidebar", True)))
                if bool(state.get("sidebar", True)):
                    self.context.layout._splitter.setSizes(
                        self.context.media.playback.sidebar_panel_sizes or list(DEFAULT_SIDEBAR_PANEL_SIZES)
                    )
            if self.context.has("_task_drawer"):
                self.context.layout._task_drawer.setVisible(bool(state.get("drawer", False)))
            self.context.media.playback.top_panel_hidden = not bool(state.get("top", True))
            self.context.media.playback.bottom_panel_hidden = not bool(state.get("bottom", True))
            self.context.media.playback.sidebar_panel_hidden = not bool(state.get("sidebar", True))
            self.context.media._set_focus_media_chrome(False)
            self.context.window.statusBar().showMessage(self.context.settings._tr("status_focus_media_disabled"))
        for widget in (self.context.get("_focus_media_button", None), self.context.get("_focus_media_action", None)):
            if widget is not None and hasattr(widget, "setChecked"):
                widget.setChecked(enabled)
        self.context.media._sync_panel_visibility_buttons()
        self.context.media._apply_media_aspect_ratio()
        QTimer.singleShot(0, self.context.media._apply_media_aspect_ratio)

    def _exit_video_fullscreen(self) -> None:
        if self.context.media.playback.video_fullscreen:
            self.context.media._set_video_fullscreen(False)

    def _handle_escape_shortcut(self) -> None:
        if self.context.get("_focus_media_enabled", False):
            self.context.media._set_focus_media_mode(False)
            return
        if self.context.media.playback.video_fullscreen:
            self.context.media._set_video_fullscreen(False)
        restoring_panels = (
            self.context.media.playback.top_panel_hidden
            or self.context.media.playback.bottom_panel_hidden
            or self.context.media.playback.sidebar_panel_hidden
        )
        if self.context.media.playback.top_panel_hidden:
            self.context.media._set_top_panel_visible(True)
        if self.context.media.playback.bottom_panel_hidden:
            self.context.media._set_bottom_panel_visible(True)
        if self.context.media.playback.sidebar_panel_hidden:
            self.context.media._set_sidebar_panel_visible(True)
        if restoring_panels:
            self.context.media._set_focus_media_chrome(False)

    def _set_video_fullscreen(self, enabled: bool) -> None:
        if enabled == self.context.media.playback.video_fullscreen:
            return
        if enabled:
            self.context.media._enter_media_fullscreen()
        else:
            self.context.media._leave_media_fullscreen()
        self.context.media._video_fullscreen_changed(enabled)

    def _enter_media_fullscreen(self) -> None:
        if not self.context.media.frame.frame:
            return
        self.context.media.frame.detached_for_fullscreen = False
        if _is_offscreen_platform():
            self.context.media.frame.frame.setFocus(Qt.ActiveWindowFocusReason)
            return
        parent = self.context.media.frame.frame.parentWidget()
        layout = parent.layout() if parent else None
        self.context.media.frame.parent = parent
        self.context.media.frame.layout = layout
        self.context.media.frame.index = -1
        self.context.media.frame.alignment = Qt.AlignmentFlag(0)
        if layout is not None:
            self.context.media.frame.index = layout.indexOf(self.context.media.frame.frame)
            item = layout.itemAt(self.context.media.frame.index)
            if item is not None:
                self.context.media.frame.alignment = item.alignment()
            layout.removeWidget(self.context.media.frame.frame)
        self.context.media.frame.frame.setParent(None)
        self.context.media.frame.frame.setWindowFlag(Qt.Window, True)
        self.context.media.frame.frame.showFullScreen()
        self.context.media.frame.frame.activateWindow()
        self.context.media.frame.frame.raise_()
        self.context.media.frame.frame.setFocus(Qt.ActiveWindowFocusReason)
        self.context.media.frame.detached_for_fullscreen = True
        self.context.media._apply_fullscreen_media_size()

    def _leave_media_fullscreen(self) -> None:
        if not self.context.media.frame.frame:
            return
        if not self.context.get("_media_frame_detached_for_fullscreen", False):
            self.context.media.frame.detached_for_fullscreen = False
            self.context.media._apply_media_aspect_ratio()
            return
        self.context.media.frame.frame.hide()
        self.context.media.frame.frame.showNormal()
        self.context.media.frame.frame.setWindowFlag(Qt.Window, False)
        if self.context.media.frame.layout is not None and self.context.media.frame.parent is not None:
            self.context.media.frame.frame.setParent(self.context.media.frame.parent)
            if self.context.media.frame.index >= 0:
                self.context.media.frame.layout.insertWidget(
                    self.context.media.frame.index,
                    self.context.media.frame.frame,
                    1,
                    self.context.media.frame.alignment,
                )
            else:
                self.context.media.frame.layout.addWidget(
                    self.context.media.frame.frame, 1, self.context.media.frame.alignment
                )
        self.context.media.frame.frame.show()
        self.context.media.frame.parent = None
        self.context.media.frame.layout = None
        self.context.media.frame.index = -1
        self.context.media.frame.alignment = Qt.AlignmentFlag(0)
        self.context.media.frame.detached_for_fullscreen = False
        self.context.media._apply_media_aspect_ratio()

    def _apply_fullscreen_media_size(self) -> None:
        if not self.context.media.frame.frame:
            return
        screen = self.context.media.frame.frame.screen() or self.context.window.screen()
        if screen is None:
            return
        geometry = screen.geometry()
        self.context.media.frame.frame.setFixedSize(geometry.size())
        self.context.media.frame.frame.move(geometry.topLeft())
        self.context.media._position_subtitle_overlay()
        if self.context.media.document.mode and self.context.media.document.pages:
            self.context.media._update_document_page(force=True)

    def _video_fullscreen_changed(self, enabled: bool) -> None:
        self.context.media.playback.video_fullscreen = enabled
        tooltip_key = "exit_fullscreen" if enabled else "fullscreen_tooltip"
        self.context.layout._video_fullscreen_button.setText("")
        self.context.layout._video_fullscreen_button.setToolTip(self.context.settings._tr(tooltip_key))
        self.context.layout._video_fullscreen_button.setProperty("i18n_tooltip_key", tooltip_key)
        self.context.window.statusBar().showMessage(
            self.context.settings._tr("status_fullscreen_entered")
            if enabled
            else self.context.settings._tr("status_fullscreen_exited")
        )

    def eventFilter(self, watched, event) -> bool:
        telegram_thumbnail = self.context.get("_telegram_channel_thumbnail", None)
        if watched is telegram_thumbnail and event.type() == QEvent.Type.Resize:
            if self.context.has("_refresh_telegram_channel_thumbnail"):
                self.context.sources._refresh_telegram_channel_thumbnail()
            return False
        telegram_widgets = {
            self.context.get("_telegram_channel_view", None),
            self.context.get("_telegram_channel_list", None),
            self.context.get("_telegram_channel_preview", None),
            telegram_thumbnail,
        }
        telegram_list = self.context.get("_telegram_channel_list", None)
        telegram_list_viewport = telegram_list.viewport() if telegram_list is not None else None
        if watched in {telegram_list, telegram_list_viewport}:
            if (
                event.type() == QEvent.Type.MouseButtonPress
                and event.button() == Qt.MouseButton.LeftButton
                and self.context.has("_handle_telegram_blacklist_button_event")
            ):
                return self.context.sources._handle_telegram_blacklist_button_event(event, activate=False)
            if (
                event.type() == QEvent.Type.MouseButtonRelease
                and event.button() == Qt.MouseButton.LeftButton
                and self.context.has("_handle_telegram_blacklist_button_event")
            ):
                return self.context.sources._handle_telegram_blacklist_button_event(event, activate=True)
        if watched in telegram_widgets and event.type() == QEvent.Type.KeyPress:
            if event.key() == Qt.Key.Key_Up and self.context.has("_select_adjacent_telegram_channel_video"):
                return self.context.sources._select_adjacent_telegram_channel_video(-1)
            if event.key() == Qt.Key.Key_Down and self.context.has("_select_adjacent_telegram_channel_video"):
                return self.context.sources._select_adjacent_telegram_channel_video(1)
        media_widgets = {
            self.context.get("_video_widget", None),
            self.context.get("_video_placeholder", None),
            self.context.get("_document_view", None),
            self.context.get("_media_stack", None),
            self.context.get("_media_frame", None),
            self.context.get("_media_start_page", None),
            self.context.get("_media_start_overlay", None),
            self.context.get("_media_start_content", None),
            self.context.get("_media_start_drop_zone", None),
        }
        if watched in media_widgets:
            if event.type() in (QEvent.Type.DragEnter, QEvent.Type.DragMove):
                supports_drop = self.context.get("_media_start_mime_supported", None)
                if callable(supports_drop) and supports_drop(event.mimeData()):
                    event.acceptProposedAction()
                    return True
            if event.type() == QEvent.Type.Drop:
                open_drop = self.context.get("_open_media_start_mime_source", None)
                if callable(open_drop) and open_drop(event.mimeData()):
                    event.acceptProposedAction()
                    return True
            if (
                watched is self.context.get("_video_placeholder", None)
                and event.type() == QEvent.Type.MouseButtonRelease
                and event.button() == Qt.MouseButton.LeftButton
            ):
                page_getter = getattr(watched, "page", None)
                page = page_getter() if callable(page_getter) else None
                open_hovered = getattr(page, "_open_hovered_supported_url", None)
                if not callable(open_hovered):
                    open_hovered = getattr(page, "_open_hovered_telegram_url", None)
                if callable(open_hovered) and open_hovered():
                    return True
            if event.type() == QEvent.Type.MouseButtonDblClick:
                self.context.media._toggle_video_fullscreen()
                return True
            if event.type() == QEvent.Type.KeyPress and event.key() in (Qt.Key.Key_Escape, Qt.Key.Key_F11):
                if event.key() == Qt.Key.Key_Escape:
                    self.context.media._handle_escape_shortcut()
                else:
                    self.context.media._toggle_video_fullscreen()
                return True
        return QMainWindow.eventFilter(self.context.window, watched, event)

    def _toggle_sidebar_panel(self) -> None:
        self.context.media._set_sidebar_panel_visible(self.context.media.playback.sidebar_panel_hidden)

    def _toggle_top_panel(self) -> None:
        self.context.media._set_top_panel_visible(self.context.media.playback.top_panel_hidden)

    def _toggle_bottom_panel(self) -> None:
        self.context.media._set_bottom_panel_visible(self.context.media.playback.bottom_panel_hidden)

    def _set_top_panel_visible(self, visible: bool) -> None:
        source_bar = self.context.get("_source_bar", None)
        if source_bar is None:
            return
        source_bar.setVisible(visible)
        self.context.media.playback.top_panel_hidden = not visible
        self.context.media._sync_panel_visibility_buttons()
        self.context.media._apply_media_aspect_ratio()
        QTimer.singleShot(0, self.context.media._apply_media_aspect_ratio)
        key = "status_top_panel_shown" if visible else "status_top_panel_hidden"
        self.context.window.statusBar().showMessage(self.context.settings._tr(key))

    def _set_bottom_panel_visible(self, visible: bool) -> None:
        controls = self.context.get("_controls", None)
        if controls is None:
            return
        controls.setVisible(visible)
        self.context.media.playback.bottom_panel_hidden = not visible
        self.context.media._sync_panel_visibility_buttons()
        self.context.media._apply_media_aspect_ratio()
        QTimer.singleShot(0, self.context.media._apply_media_aspect_ratio)
        key = "status_bottom_panel_shown" if visible else "status_bottom_panel_hidden"
        self.context.window.statusBar().showMessage(self.context.settings._tr(key))

    def _set_panel_toggle_icon(self, *, panel_visible: bool) -> None:
        if not self.context.has("_panel_toggle_button"):
            return
        icon = (
            QStyle.StandardPixmap.SP_TitleBarShadeButton
            if panel_visible
            else QStyle.StandardPixmap.SP_TitleBarUnshadeButton
        )
        self.context.layout._panel_toggle_button.setIcon(self.context.window.style().standardIcon(icon))

    def _sync_panel_visibility_buttons(self) -> None:
        if self.context.has("_top_panel_toggle_button"):
            self.context.media._sync_visibility_button(
                self.context.layout._top_panel_toggle_button,
                panel_visible=not self.context.media.playback.top_panel_hidden,
                hide_icon=QStyle.StandardPixmap.SP_ArrowUp,
                show_icon=QStyle.StandardPixmap.SP_ArrowDown,
                hide_tooltip_key="top_panel_hide_tooltip",
                show_tooltip_key="top_panel_show_tooltip",
            )
        if self.context.has("_bottom_panel_toggle_button"):
            self.context.media._sync_visibility_button(
                self.context.layout._bottom_panel_toggle_button,
                panel_visible=not self.context.media.playback.bottom_panel_hidden,
                hide_icon=QStyle.StandardPixmap.SP_ArrowDown,
                show_icon=QStyle.StandardPixmap.SP_ArrowUp,
                hide_tooltip_key="bottom_panel_hide_tooltip",
                show_tooltip_key="bottom_panel_show_tooltip",
            )
        if self.context.has("_right_panel_toggle_button"):
            self.context.media._sync_visibility_button(
                self.context.layout._right_panel_toggle_button,
                panel_visible=not self.context.media.playback.sidebar_panel_hidden,
                hide_icon=QStyle.StandardPixmap.SP_ArrowRight,
                show_icon=QStyle.StandardPixmap.SP_ArrowLeft,
                hide_tooltip_key="right_panel_hide_tooltip",
                show_tooltip_key="right_panel_show_tooltip",
            )
        if self.context.has("_panel_toggle_button"):
            self.context.media._sync_visibility_button(
                self.context.layout._panel_toggle_button,
                panel_visible=not self.context.media.playback.sidebar_panel_hidden,
                hide_icon=QStyle.StandardPixmap.SP_TitleBarShadeButton,
                show_icon=QStyle.StandardPixmap.SP_TitleBarUnshadeButton,
                hide_tooltip_key="right_panel_hide_tooltip",
                show_tooltip_key="right_panel_show_tooltip",
            )

    def _sync_visibility_button(
        self,
        button,
        *,
        panel_visible: bool,
        hide_icon: QStyle.StandardPixmap,
        show_icon: QStyle.StandardPixmap,
        hide_tooltip_key: str,
        show_tooltip_key: str,
    ) -> None:
        tooltip_key = hide_tooltip_key if panel_visible else show_tooltip_key
        icon = hide_icon if panel_visible else show_icon
        button.setText("")
        button.setIcon(self.context.window.style().standardIcon(icon))
        button.setToolTip(self.context.settings._tr(tooltip_key))
        button.setProperty("i18n_tooltip_key", tooltip_key)

    def _expand_sidebar_panel(self) -> None:
        if not self.context.has("_splitter"):
            return
        if self.context.media.playback.sidebar_panel_hidden:
            self.context.media._set_sidebar_panel_visible(True)
        sizes = self.context.layout._splitter.sizes()
        if len(sizes) < 2:
            return
        total = sum(sizes)
        if total <= 0:
            return
        step = 120
        min_video_width = 320
        current_sidebar = max(0, sizes[1])
        max_sidebar = max(DEFAULT_SIDEBAR_PANEL_WIDTH, total - min_video_width)
        target_sidebar = min(max_sidebar, max(DEFAULT_SIDEBAR_PANEL_WIDTH, current_sidebar) + step)
        target_video = max(0, total - target_sidebar)
        if self.context.has("_settings_scroll"):
            self.context.layout._settings_scroll.setMinimumWidth(target_sidebar)
        self.context.media.playback.sidebar_panel_sizes = [target_video, target_sidebar]
        self.context.layout._splitter.setSizes(self.context.media.playback.sidebar_panel_sizes)
        applied_sizes = self.context.layout._splitter.sizes()
        if len(applied_sizes) >= 2 and applied_sizes[1] <= current_sidebar and target_sidebar > current_sidebar:
            self.context.window.resize(
                self.context.window.width() + target_sidebar - current_sidebar, self.context.window.height()
            )
            QTimer.singleShot(
                0,
                lambda sizes=list(self.context.media.playback.sidebar_panel_sizes): (
                    self.context.layout._splitter.setSizes(sizes)
                ),
            )
        self.context.media._apply_media_aspect_ratio()
        sidebar_percent = int(round(target_sidebar / total * 100))
        video_percent = max(0, 100 - sidebar_percent)
        self.context.window.statusBar().showMessage(
            self.context.settings._tr("status_panel_ratio").format(video=video_percent, sidebar=sidebar_percent)
        )

    def _collapse_sidebar_panel(self) -> None:
        if not self.context.has("_splitter"):
            return
        if self.context.media.playback.sidebar_panel_hidden:
            self.context.media._set_sidebar_panel_visible(True)
            return
        sizes = self.context.layout._splitter.sizes()
        if len(sizes) < 2:
            return
        total = sum(sizes)
        if total <= 0:
            return
        step = 120
        current_sidebar = max(0, sizes[1])
        target_sidebar = max(DEFAULT_SIDEBAR_PANEL_WIDTH, current_sidebar - step)
        target_video = max(0, total - target_sidebar)
        if self.context.has("_settings_scroll"):
            self.context.layout._settings_scroll.setMinimumWidth(DEFAULT_SIDEBAR_PANEL_WIDTH)
        self.context.media.playback.sidebar_panel_sizes = [target_video, target_sidebar]
        self.context.layout._splitter.setSizes(self.context.media.playback.sidebar_panel_sizes)
        self.context.media._apply_media_aspect_ratio()
        sidebar_percent = int(round(target_sidebar / total * 100))
        video_percent = max(0, 100 - sidebar_percent)
        self.context.window.statusBar().showMessage(
            self.context.settings._tr("status_panel_ratio").format(video=video_percent, sidebar=sidebar_percent)
        )

    def _media_controls_height(self) -> int:
        if not self.context.has("_controls") or self.context.layout._controls.isHidden():
            return 0
        return self.context.layout._controls.sizeHint().height()

    def _set_header_controls_visible(self, visible: bool) -> None:
        for widget in self.context.get("_header_controls", ()):
            widget.setVisible(visible)

    def _set_focus_media_property(self, enabled: bool) -> None:
        widgets = (
            self.context.get("_video_panel", None),
            self.context.media.frame.frame,
            self.context.get("_video_placeholder", None),
            self.context.get("_media_stack", None),
        )
        original_shapes = self.context.get("_focus_media_frame_shapes", None)
        if original_shapes is None:
            original_shapes = {}
            self.context.media._focus_media_frame_shapes = original_shapes
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
        state = self.context.get("_focus_media_layout_state_cache", None)
        if state is None:
            state = {}
            if self.context.has("_root_layout"):
                state["root_margins"] = self.context.media._layout_margins(self.context.layout._root_layout)
                state["root_spacing"] = self.context.layout._root_layout.spacing()
            if self.context.has("_video_layout"):
                state["video_margins"] = self.context.media._layout_margins(self.context.layout._video_layout)
                state["video_spacing"] = self.context.layout._video_layout.spacing()
                if self.context.media.frame.frame:
                    item = self.context.layout._video_layout.itemAt(
                        self.context.layout._video_layout.indexOf(self.context.media.frame.frame)
                    )
                    state["media_alignment"] = item.alignment() if item is not None else Qt.AlignCenter
            self.context.media._focus_media_layout_state_cache = state
        return state

    def _set_focus_media_chrome(self, enabled: bool) -> None:
        state = self.context.media._focus_media_layout_state()
        self.context.media._set_focus_media_property(enabled)
        if self.context.has("_root_layout"):
            if enabled:
                self.context.layout._root_layout.setContentsMargins(0, 0, 0, 0)
            else:
                self.context.media._set_layout_margins(
                    self.context.layout._root_layout, state.get("root_margins", (14, 12, 14, 10))
                )
            self.context.layout._root_layout.setSpacing(0 if enabled else int(state.get("root_spacing", 10)))
        if self.context.has("_video_layout"):
            if enabled:
                self.context.layout._video_layout.setContentsMargins(0, 0, 0, 0)
            else:
                self.context.media._set_layout_margins(
                    self.context.layout._video_layout, state.get("video_margins", (12, 12, 12, 12))
                )
            self.context.layout._video_layout.setSpacing(0 if enabled else int(state.get("video_spacing", 10)))
            if self.context.media.frame.frame:
                self.context.layout._video_layout.setAlignment(
                    self.context.media.frame.frame,
                    Qt.AlignmentFlag(0) if enabled else state.get("media_alignment", Qt.AlignCenter),
                )
        self.context.window.statusBar().setVisible(True)

    def _set_sidebar_panel_visible(self, visible: bool) -> None:
        if not self.context.has("_settings_scroll"):
            return
        if visible:
            self.context.layout._settings_scroll.show()
            self.context.media.playback.sidebar_panel_hidden = False
            self.context.layout._splitter.setSizes(
                self.context.media.playback.sidebar_panel_sizes or list(DEFAULT_SIDEBAR_PANEL_SIZES)
            )
            self.context.window.statusBar().showMessage(self.context.settings._tr("status_panel_shown"))
        else:
            sizes = self.context.layout._splitter.sizes()
            if len(sizes) >= 2 and sizes[1] > 0:
                self.context.media.playback.sidebar_panel_sizes = sizes
            self.context.layout._settings_scroll.hide()
            self.context.media.playback.sidebar_panel_hidden = True
            sizes = self.context.layout._splitter.sizes()
            total = (
                sum(sizes)
                if sizes
                else sum(self.context.media.playback.sidebar_panel_sizes or DEFAULT_SIDEBAR_PANEL_SIZES)
            )
            if total > 0:
                self.context.layout._splitter.setSizes([total, 0])
        self.context.media._sync_panel_visibility_buttons()
        self.context.media._apply_media_aspect_ratio()
        QTimer.singleShot(0, self.context.media._apply_media_aspect_ratio)

    def _reset_panel_sizes(self, show_status: bool = True) -> None:
        self.context.media._set_focus_media_chrome(False)
        if self.context.has("_source_bar"):
            self.context.layout._source_bar.show()
        if self.context.has("_settings_scroll"):
            self.context.layout._settings_scroll.show()
            self.context.layout._settings_scroll.setMinimumWidth(DEFAULT_SIDEBAR_PANEL_WIDTH)
        if self.context.has("_controls"):
            self.context.layout._controls.show()
        self.context.media._set_header_controls_visible(True)
        self.context.media.playback.top_panel_hidden = False
        self.context.media.playback.bottom_panel_hidden = False
        self.context.media.playback.sidebar_panel_hidden = False
        self.context.media.playback.sidebar_panel_sizes = list(DEFAULT_SIDEBAR_PANEL_SIZES)
        self.context.layout._splitter.setSizes(list(DEFAULT_SIDEBAR_PANEL_SIZES))
        self.context.media._sync_panel_visibility_buttons()
        self.context.media._apply_media_aspect_ratio()
        QTimer.singleShot(0, self.context.media._apply_media_aspect_ratio)
        if show_status:
            self.context.window.statusBar().showMessage(self.context.settings._tr("status_panel_size_reset"))

    def _begin_seek(self) -> None:
        self.context.media.playback.seeking = True

    def _end_seek(self) -> None:
        self.context.media.playback.seeking = False
        if self.context.media.document.mode:
            self.context.media.document.audio_sync_active = False
            self.context.media.document.elapsed_ms = int(
                self.context.layout._position_slider.value() / 1000.0 * self.context.media.document.duration_ms
            )
            if self.context.media.document.started_at is not None:
                self.context.media.document.started_at = time.monotonic()
        else:
            self.context.layout._player.set_position(self.context.layout._position_slider.value() / 1000.0)
        if self.context.layout._dub_button.isChecked():
            worker = self.context.lifecycle.workers.dubbing_worker
            if worker is not None and worker.isRunning():
                request_resync = getattr(worker, "request_resync", None)
                if callable(request_resync):
                    request_resync()
                    self.context.ui._set_dubbing_ready(
                        False, self.context.settings._tr("worker_resyncing_target_voice")
                    )
                    return
            self.context.dubbing._start_dubbing()

    def _refresh_position(self) -> None:
        if self.context.media.document.mode:
            current = self.context.media._document_time_ms()
            total = self.context.media.document.duration_ms
            self.context.media._update_document_page()
            self.context.media._update_subtitle_overlay()
            if not self.context.media.playback.seeking and total > 0:
                self.context.layout._position_slider.setValue(int(current / total * 1000))
            self.context.layout._time_label.setText(
                f"{self.context.media._format_ms(current)} / {self.context.media._format_ms(total)}"
            )
            if total > 0 and current >= total and self.context.media.document.started_at is not None:
                self.context.media.document.elapsed_ms = total
                self.context.media.document.started_at = None
            return

        if not self.context.media.playback.seeking:
            position = int(self.context.layout._player.get_position() * 1000)
            if position >= 0:
                self.context.layout._position_slider.setValue(position)

        current = self.context.layout._player.get_time_ms()
        total = self.context.layout._player.get_length_ms()
        self.context.media._update_subtitle_overlay()
        self.context.layout._time_label.setText(
            f"{self.context.media._format_ms(current)} / {self.context.media._format_ms(total)}"
        )

    @staticmethod
    def _format_ms(value: int) -> str:
        seconds = max(0, value // 1000)
        minutes, seconds = divmod(seconds, 60)
        hours, minutes = divmod(minutes, 60)
        if hours:
            return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        return f"{minutes:02d}:{seconds:02d}"


def _document_ms_value(value: object) -> int:
    return int(_document_seconds_value(value) * 1000)


def _document_seconds_value(value: object) -> float:
    try:
        seconds = float(value)
    except (OverflowError, TypeError, ValueError):
        return 0.0
    if not math.isfinite(seconds):
        return 0.0
    return max(0.0, seconds)
