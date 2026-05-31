from __future__ import annotations

import re
import subprocess
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from ai_player.core.app_logging import get_logger
from ai_player.core.config import AppConfig
from ai_player.services.document_reader import create_document_transcript
from ai_player.services.ffmpeg import ffmpeg_executable, terminate_process
from ai_player.services.media_cache import (
    playback_compat_cached_output_valid,
    remove_playback_compat_output,
    write_playback_compat_metadata,
)
from ai_player.services.runtime_warmup import RuntimeWarmupCancelled, warm_runtime_components
from ai_player.services.source_voice_filter import (
    SourceVoiceFilterCancelled,
    apply_source_voice_filter,
    read_source_voice_filter_backend,
    resolve_source_voice_filter_command,
    source_voice_filter_cached_output_valid,
    write_source_voice_filter_metadata,
)
from ai_player.services.telegram_channel import (
    TelegramLoginConfig,
    TelegramLoginRequest,
    TelegramPasswordRequired,
    complete_telegram_login,
    download_telegram_channel_video,
    list_telegram_channel_items,
    list_telegram_channel_items_authenticated,
    list_telegram_channel_videos,
    list_telegram_channel_videos_authenticated,
    start_telegram_login,
    telegram_channel_item_translation_text,
)
from ai_player.services.translation_runtime import get_shared_vietnamese_translator
from ai_player.services.video_source import resolve_video_source
from ai_player.workers.worker_values import selected_source_language

LOGGER = get_logger(__name__)


class RuntimeWarmupWorker(QThread):
    status_changed = Signal(str)
    finished_successfully = Signal(object)
    failed = Signal(str)

    def __init__(self, config: AppConfig, parent=None) -> None:
        super().__init__(parent)
        self._config = config
        self._stop_requested = False

    def stop(self) -> None:
        self._stop_requested = True
        self.requestInterruption()

    def run(self) -> None:
        try:
            timings = warm_runtime_components(
                self._config,
                cancel_callback=lambda: self._stop_requested or self.isInterruptionRequested(),
                progress_callback=self.status_changed.emit,
            )
        except RuntimeWarmupCancelled:
            return
        except Exception as exc:
            if not self._stop_requested and not self.isInterruptionRequested():
                LOGGER.exception("Runtime warmup worker failed.")
                self.failed.emit(str(exc))
            return
        if not self._stop_requested and not self.isInterruptionRequested():
            self.finished_successfully.emit(timings)


class VideoSourceWorker(QThread):
    resolved = Signal(object)
    failed = Signal(str)
    progress_changed = Signal(object)

    def __init__(
        self,
        url: str,
        playback_quality: str,
        full_cache: bool = True,
        language_id: str | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._url = url
        self._playback_quality = playback_quality
        self._full_cache = full_cache
        self._language_id = language_id
        self._stop_requested = False

    def stop(self) -> None:
        self._stop_requested = True
        self.requestInterruption()

    def run(self) -> None:
        try:
            self.resolved.emit(
                resolve_video_source(
                    self._url,
                    self._playback_quality,
                    full_cache=self._full_cache,
                    progress_callback=self.progress_changed.emit if self._full_cache else None,
                    cancel_callback=lambda: self._stop_requested or self.isInterruptionRequested(),
                    language_id=self._language_id,
                )
            )
        except Exception as exc:
            if not self._stop_requested and not self.isInterruptionRequested():
                LOGGER.exception("Video source worker failed.")
                self.failed.emit(str(exc))


class DocumentTranscriptWorker(QThread):
    ready = Signal(object, bool)
    failed = Signal(str)

    def __init__(
        self,
        path: str,
        start_dubbing: bool,
        seconds_per_segment: int = 6,
        language_id: str | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._path = path
        self._start_dubbing = start_dubbing
        self._seconds_per_segment = seconds_per_segment
        self._language_id = language_id
        self._stop_requested = False

    def stop(self) -> None:
        self._stop_requested = True
        self.requestInterruption()

    def run(self) -> None:
        try:
            transcript = create_document_transcript(
                self._path,
                seconds_per_segment=self._seconds_per_segment,
                cancel_callback=lambda: self._stop_requested or self.isInterruptionRequested(),
                language_id=self._language_id,
            )
        except Exception as exc:
            if not self._stop_requested and not self.isInterruptionRequested():
                LOGGER.exception("Document transcript worker failed.")
                self.failed.emit(str(exc))
            return
        if self._stop_requested or self.isInterruptionRequested():
            return
        self.ready.emit(transcript, self._start_dubbing)


class TelegramChannelWorker(QThread):
    videos_ready = Signal(object)
    login_request_ready = Signal(object)
    login_ready = Signal(object)
    password_required = Signal(object, str)
    progress_changed = Signal(object)
    video_ready = Signal(str)
    failed = Signal(str)

    def __init__(
        self,
        operation: str,
        *,
        url: str = "",
        config: TelegramLoginConfig | None = None,
        login_request: TelegramLoginRequest | None = None,
        code: str = "",
        password: str = "",
        post_id: str = "",
        before_post_id: str = "",
        search: str = "",
        language_id: str | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.operation = operation
        self._url = url
        self._config = config
        self._login_request = login_request
        self._code = code
        self._password = password
        self._post_id = post_id
        self._before_post_id = before_post_id
        self._search = search
        self._language_id = language_id
        self._stop_requested = False

    def stop(self) -> None:
        self._stop_requested = True
        self.requestInterruption()

    def run(self) -> None:
        try:
            if self.operation in {"list_public", "list_public_more"}:
                self.videos_ready.emit(
                    list_telegram_channel_items(
                        self._url,
                        before_post_id=self._before_post_id,
                        search=self._search,
                        language_id=self._language_id,
                    )
                )
            elif self.operation == "list_public_videos":
                self.videos_ready.emit(
                    list_telegram_channel_videos(
                        self._url,
                        before_post_id=self._before_post_id,
                        search=self._search,
                        language_id=self._language_id,
                    )
                )
            elif self.operation in {"list_authenticated", "list_authenticated_more"}:
                if self._config is None:
                    raise RuntimeError("Telegram login config is missing.")
                self.videos_ready.emit(
                    list_telegram_channel_items_authenticated(
                        self._url,
                        self._config,
                        before_post_id=self._before_post_id,
                        search=self._search,
                        language_id=self._language_id,
                    )
                )
            elif self.operation == "list_authenticated_videos":
                if self._config is None:
                    raise RuntimeError("Telegram login config is missing.")
                self.videos_ready.emit(
                    list_telegram_channel_videos_authenticated(
                        self._url,
                        self._config,
                        before_post_id=self._before_post_id,
                        search=self._search,
                        language_id=self._language_id,
                    )
                )
            elif self.operation == "start_login":
                if self._config is None:
                    raise RuntimeError("Telegram login config is missing.")
                request = start_telegram_login(self._config, language_id=self._language_id)
                if request is None:
                    self.login_ready.emit(self._config)
                else:
                    self.login_request_ready.emit(request)
            elif self.operation == "complete_login":
                if self._login_request is None:
                    raise RuntimeError("Telegram login request is missing.")
                try:
                    complete_telegram_login(
                        self._login_request,
                        self._code,
                        password=self._password,
                        language_id=self._language_id,
                    )
                except TelegramPasswordRequired:
                    self.password_required.emit(self._login_request, self._code)
                    return
                self.login_ready.emit(self._login_request.config)
            elif self.operation == "download":
                if self._config is None:
                    raise RuntimeError("Telegram login config is missing.")
                self.progress_changed.emit(
                    {
                        "status": "starting",
                        "provider": "telegram",
                        "filename": f"telegram-{self._post_id}".strip("-"),
                    }
                )
                path = download_telegram_channel_video(
                    self._url,
                    self._post_id,
                    self._config,
                    progress_callback=self.progress_changed.emit,
                    cancel_callback=lambda: self._stop_requested or self.isInterruptionRequested(),
                    language_id=self._language_id,
                )
                if self._stop_requested or self.isInterruptionRequested():
                    return
                self.progress_changed.emit(
                    {
                        "status": "finished",
                        "provider": "telegram",
                        "filename": path,
                    }
                )
                self.video_ready.emit(path)
            else:
                raise RuntimeError(f"Unknown Telegram operation: {self.operation}")
        except Exception as exc:
            if not self._stop_requested and not self.isInterruptionRequested():
                LOGGER.exception("Telegram channel worker failed.")
                self.failed.emit(str(exc))


class TelegramContentTranslationWorker(QThread):
    ready = Signal(object)
    failed = Signal(str)

    def __init__(
        self,
        config: AppConfig,
        items: object,
        *,
        language_id: str | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._config = config
        self._language_id = language_id
        self._items = [
            (
                str(getattr(item, "post_id", "") or ""),
                str(getattr(item, "url", "") or ""),
                telegram_channel_item_translation_text(item),
            )
            for item in list(items or [])
        ]
        self._stop_requested = False

    def stop(self) -> None:
        self._stop_requested = True
        self.requestInterruption()

    def run(self) -> None:
        try:
            active_items = [(post_id, url, text) for post_id, url, text in self._items if text.strip()]
            if not active_items:
                self.ready.emit([])
                return
            source_language = selected_source_language(self._config) or _infer_telegram_content_language(
                [text for _post_id, _url, text in active_items]
            )
            translator = get_shared_vietnamese_translator(self._config)
            translated = translator.translate_many([text for _post_id, _url, text in active_items], source_language)
            if self._stop_requested or self.isInterruptionRequested():
                return
            self.ready.emit(
                [
                    (post_id, url, translated_text)
                    for (post_id, url, _text), translated_text in zip(active_items, translated, strict=False)
                ]
            )
        except Exception as exc:
            if not self._stop_requested and not self.isInterruptionRequested():
                LOGGER.exception("Telegram content translation worker failed.")
                self.failed.emit(str(exc))


def _infer_telegram_content_language(texts: list[str]) -> str | None:
    text = "\n".join(str(item or "") for item in texts)
    if re.search(r"[\u4e00-\u9fff]", text):
        return "zh"
    if re.search(r"[\u3040-\u30ff]", text):
        return "ja"
    if re.search(r"[\uac00-\ud7af]", text):
        return "ko"
    if re.search(r"[\u0e00-\u0e7f]", text):
        return "th"
    if re.search(r"[\u0600-\u06ff]", text):
        return "ar"
    if re.search(r"[\u0400-\u04ff]", text):
        return "ru"
    return None


class SourceAudioFilterWorker(QThread):
    ready = Signal(str, str, str)
    failed = Signal(str, str)
    warning = Signal(str, str)

    def __init__(
        self,
        source_path: str,
        output_path: Path,
        mode: str = "auto",
        model: str = "htdemucs",
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._source_path = source_path
        self._output_path = output_path
        self._mode = mode
        self._model = model
        self._process: subprocess.Popen | None = None
        self._stop_requested = False

    def stop(self) -> None:
        self._stop_requested = True
        if self._process is not None and self._process.poll() is None:
            _terminate_process(self._process)

    def run(self) -> None:
        try:
            if source_voice_filter_cached_output_valid(self._output_path, self._mode, self._model):
                backend = read_source_voice_filter_backend(self._output_path) or self._mode
                self.ready.emit(self._source_path, str(self._output_path), backend)
                return
            self._output_path.parent.mkdir(parents=True, exist_ok=True)
            result = apply_source_voice_filter(
                Path(self._source_path),
                self._output_path,
                mode=self._mode,
                model=self._model,
                process_runner=self._run_process,
            )
            write_source_voice_filter_metadata(result)
            if self._stop_requested:
                return
            if result.warning:
                self.warning.emit(self._source_path, result.warning)
            self.ready.emit(self._source_path, str(self._output_path), result.backend)
        except Exception as exc:
            if not self._stop_requested:
                LOGGER.exception("Source audio filter worker failed.")
                self.failed.emit(self._source_path, _format_process_exception(exc))
        finally:
            self._process = None

    def _run_process(self, command: list[str]) -> None:
        if self._stop_requested:
            raise SourceVoiceFilterCancelled("Voice filter stopped.")
        resolved_command = resolve_source_voice_filter_command(command)
        self._process = subprocess.Popen(
            resolved_command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        stdout, stderr = self._process.communicate()
        return_code = self._process.returncode
        if self._stop_requested:
            raise SourceVoiceFilterCancelled("Voice filter stopped.")
        if return_code != 0:
            raise subprocess.CalledProcessError(return_code, resolved_command, output=stdout, stderr=stderr)


class PlaybackCompatibilityWorker(QThread):
    ready = Signal(str, str)
    failed = Signal(str, str)

    def __init__(self, source_path: str, output_path: Path, cache_key: str = "", parent=None) -> None:
        super().__init__(parent)
        self._source_path = source_path
        self._output_path = output_path
        self._cache_key = cache_key
        self._process: subprocess.Popen | None = None
        self._stop_requested = False

    def stop(self) -> None:
        self._stop_requested = True
        if self._process is not None and self._process.poll() is None:
            _terminate_process(self._process)

    def run(self) -> None:
        try:
            if playback_compat_cached_output_valid(self._output_path, self._source_path, self._cache_key):
                self.ready.emit(self._source_path, str(self._output_path))
                return
            remove_playback_compat_output(self._output_path)
            self._output_path.parent.mkdir(parents=True, exist_ok=True)
            command = [
                ffmpeg_executable(),
                "-hide_banner",
                "-loglevel",
                "error",
                "-i",
                self._source_path,
                "-map",
                "0:v:0?",
                "-map",
                "0:a:0?",
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-profile:v",
                "main",
                "-level:v",
                "4.0",
                "-crf",
                "23",
                "-pix_fmt",
                "yuv420p",
                "-vf",
                "scale=-2:min(720\\,ih)",
                "-c:a",
                "aac",
                "-b:a",
                "160k",
                "-ac",
                "2",
                "-ar",
                "44100",
                "-movflags",
                "+faststart",
                "-y",
                str(self._output_path),
            ]
            self._process = subprocess.Popen(command)
            return_code = self._process.wait()
            if self._stop_requested:
                remove_playback_compat_output(self._output_path)
                return
            if return_code != 0:
                raise subprocess.CalledProcessError(return_code, command)
            write_playback_compat_metadata(self._output_path, self._source_path, self._cache_key)
            self.ready.emit(self._source_path, str(self._output_path))
        except Exception as exc:
            remove_playback_compat_output(self._output_path)
            if not self._stop_requested:
                LOGGER.exception("Playback compatibility worker failed.")
                self.failed.emit(self._source_path, str(exc))
        finally:
            self._process = None


_terminate_process = terminate_process


def _format_process_exception(exc: Exception, max_length: int = 500) -> str:
    if isinstance(exc, subprocess.CalledProcessError):
        executable = _process_executable_name(exc.cmd)
        prefix = f"{executable} failed with exit code {exc.returncode}"
        detail = _compact_process_detail(exc.stderr or exc.output or "", max_length=max_length - len(prefix) - 2)
        if detail:
            message = f"{prefix}: {detail}"
        else:
            message = prefix
    else:
        message = str(exc).strip() or exc.__class__.__name__
        message = " ".join(message.split())
    if len(message) > max_length:
        return f"{message[: max_length - 3]}..."
    return message


def _compact_process_detail(detail: object, *, max_length: int = 500) -> str:
    text = str(detail or "").replace("\r", "\n")
    lines = [" ".join(line.split()) for line in text.splitlines()]
    lines = [line for line in lines if line]
    if not lines:
        return ""
    message = " ".join(lines)
    if len(message) <= max_length:
        return message
    tail_budget = max(80, max_length - 20)
    return f"...{message[-tail_budget:]}"


def _process_executable_name(command: object) -> str:
    if isinstance(command, (list, tuple)) and command:
        command_parts = [str(part) for part in command]
        if "ai_player.services.demucs_runner" in command_parts:
            return "demucs"
        return str(command[0])
    return str(command or "process")
