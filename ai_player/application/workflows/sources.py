from __future__ import annotations

import re
import subprocess
from pathlib import Path

from ai_player.application.events import Event, Workflow
from ai_player.application.workflow_ports import SourcesDependencies
from ai_player.configuration import AppConfig
from ai_player.core.app_logging import get_logger
from ai_player.core.redaction import redact_secrets
from ai_player.domain.worker_values import selected_source_language

LOGGER = get_logger(__name__)


class RuntimeWarmupWorker(Workflow):
    status_changed = Event(str)
    finished_successfully = Event(object)
    failed = Event(str)

    def __init__(self, config: AppConfig, parent=None, *, dependencies: SourcesDependencies) -> None:
        super().__init__(parent, dependencies=dependencies)
        self._config = config
        self._stop_requested = False

    def stop(self) -> None:
        self._stop_requested = True
        self.requestInterruption()

    def run(self) -> None:
        try:
            timings = self.dependencies.warm_runtime_components(
                self._config,
                cancel_callback=lambda: self._stop_requested or self.isInterruptionRequested(),
                progress_callback=self.status_changed.emit,
            )
        except self.dependencies.RuntimeWarmupCancelled:
            return
        except Exception as exc:
            if not self._stop_requested and not self.isInterruptionRequested():
                LOGGER.exception("Runtime warmup worker failed.")
                self.failed.emit(redact_secrets(exc))
            return
        if not self._stop_requested and not self.isInterruptionRequested():
            self.finished_successfully.emit(timings)


class ProviderPreviewWorker(Workflow):
    ready = Event(object)
    failed = Event(str)

    def __init__(self, kind: str, config: AppConfig, parent=None, *, dependencies: SourcesDependencies) -> None:
        super().__init__(parent, dependencies=dependencies)
        self._kind = kind
        self._config = config
        self._stop_requested = False

    def stop(self) -> None:
        self._stop_requested = True
        self.requestInterruption()

    def run(self) -> None:
        try:
            result = self.dependencies.preview_provider(self._kind, self._config)
        except Exception as exc:
            if not self._stop_requested and not self.isInterruptionRequested():
                LOGGER.exception("Provider preview worker failed.")
                self.failed.emit(redact_secrets(exc))
            return
        if not self._stop_requested and not self.isInterruptionRequested():
            self.ready.emit(result)


class VideoSourceWorker(Workflow):
    resolved = Event(object)
    failed = Event(str)
    progress_changed = Event(object)
    stream_ready = Event(object)

    def __init__(
        self,
        url: str,
        playback_quality: str,
        full_cache: bool = True,
        cache_dir: str = "",
        play_after_cache_percent: int = 0,
        language_id: str | None = None,
        parent=None,
        *,
        dependencies: SourcesDependencies,
    ) -> None:
        super().__init__(parent, dependencies=dependencies)
        self._url = url
        self._playback_quality = playback_quality
        self._full_cache = full_cache
        self._cache_dir = cache_dir
        self._play_after_cache_percent = max(0, min(100, int(play_after_cache_percent or 0)))
        self._language_id = language_id
        self._stop_requested = False
        self._stream_source = None
        self._stream_ready_emitted = False

    def stop(self) -> None:
        self._stop_requested = True
        self.requestInterruption()

    def run(self) -> None:
        try:
            if self._full_cache and self._play_after_cache_percent > 0:
                self._prepare_stream_source()
            self.resolved.emit(
                self.dependencies.resolve_video_source(
                    self._url,
                    self._playback_quality,
                    full_cache=self._full_cache,
                    cache_dir=self._cache_dir,
                    progress_callback=self._progress_changed if self._full_cache else None,
                    cancel_callback=lambda: self._stop_requested or self.isInterruptionRequested(),
                    language_id=self._language_id,
                )
            )
        except Exception as exc:
            if not self._stop_requested and not self.isInterruptionRequested():
                if self._full_cache and self._stream_source is not None and _can_fallback_to_prepared_stream(exc):
                    LOGGER.info("Full video cache failed; falling back to prepared stream source.")
                    self.resolved.emit(self._stream_source)
                    return
                LOGGER.exception("Video source worker failed.")
                self.failed.emit(redact_secrets(exc))

    def _prepare_stream_source(self) -> None:
        try:
            self._stream_source = self.dependencies.resolve_video_source(
                self._url,
                self._playback_quality,
                full_cache=False,
                cache_dir=self._cache_dir,
                cancel_callback=lambda: self._stop_requested or self.isInterruptionRequested(),
                language_id=self._language_id,
            )
        except Exception:
            LOGGER.info("Could not prepare early stream URL while caching.", exc_info=True)

    def _progress_changed(self, data) -> None:
        self.progress_changed.emit(data)
        if self._stream_ready_emitted or self._stream_source is None:
            return
        if _download_percent(data) < self._play_after_cache_percent:
            return
        self._stream_ready_emitted = True
        self.stream_ready.emit(self._stream_source)


def _download_percent(data) -> int:
    if not isinstance(data, dict):
        return 0
    downloaded = data.get("downloaded_bytes")
    total = data.get("total_bytes")
    try:
        downloaded_value = float(downloaded)
        total_value = float(total)
    except (TypeError, ValueError):
        return 0
    if downloaded_value <= 0 or total_value <= 0:
        return 0
    return max(0, min(100, int(downloaded_value * 100 / total_value)))


def _can_fallback_to_prepared_stream(exc: Exception) -> bool:
    message = str(redact_secrets(exc)).casefold()
    return (
        "403" in message
        or "forbidden" in message
        or "requested format is not available" in message
        or "--list-formats" in message
    )


class DocumentTranscriptWorker(Workflow):
    ready = Event(object, bool)
    failed = Event(str)

    def __init__(
        self,
        path: str,
        start_dubbing: bool,
        seconds_per_segment: int = 6,
        language_id: str | None = None,
        parent=None,
        *,
        dependencies: SourcesDependencies,
    ) -> None:
        super().__init__(parent, dependencies=dependencies)
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
            transcript = self.dependencies.create_document_transcript(
                self._path,
                seconds_per_segment=self._seconds_per_segment,
                cancel_callback=lambda: self._stop_requested or self.isInterruptionRequested(),
                language_id=self._language_id,
            )
        except Exception as exc:
            if not self._stop_requested and not self.isInterruptionRequested():
                LOGGER.exception("Document transcript worker failed.")
                self.failed.emit(redact_secrets(exc))
            return
        if self._stop_requested or self.isInterruptionRequested():
            return
        self.ready.emit(transcript, self._start_dubbing)


class TelegramChannelWorker(Workflow):
    videos_ready = Event(object)
    login_request_ready = Event(object)
    login_ready = Event(object)
    password_required = Event(object, str)
    progress_changed = Event(object)
    video_ready = Event(str)
    failed = Event(str)

    def __init__(
        self,
        operation: str,
        *,
        url: str = "",
        config: object | None = None,
        login_request: object | None = None,
        code: str = "",
        password: str = "",
        post_id: str = "",
        before_post_id: str = "",
        search: str = "",
        language_id: str | None = None,
        parent=None,
        dependencies: SourcesDependencies,
    ) -> None:
        super().__init__(parent, dependencies=dependencies)
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
                    self.dependencies.list_telegram_channel_items(
                        self._url,
                        before_post_id=self._before_post_id,
                        search=self._search,
                        language_id=self._language_id,
                    )
                )
            elif self.operation == "list_public_videos":
                self.videos_ready.emit(
                    self.dependencies.list_telegram_channel_videos(
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
                    self.dependencies.list_telegram_channel_items_authenticated(
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
                    self.dependencies.list_telegram_channel_videos_authenticated(
                        self._url,
                        self._config,
                        before_post_id=self._before_post_id,
                        search=self._search,
                        language_id=self._language_id,
                    )
                )
            elif self.operation in {"list_youtube", "list_youtube_more"}:
                self.videos_ready.emit(
                    self.dependencies.list_youtube_channel_items(
                        self._url,
                        continuation=self._before_post_id,
                        search=self._search,
                        language_id=self._language_id,
                    )
                )
            elif self.operation == "start_login":
                if self._config is None:
                    raise RuntimeError("Telegram login config is missing.")
                request = self.dependencies.start_telegram_login(self._config, language_id=self._language_id)
                if request is None:
                    self.login_ready.emit(self._config)
                else:
                    self.login_request_ready.emit(request)
            elif self.operation == "complete_login":
                if self._login_request is None:
                    raise RuntimeError("Telegram login request is missing.")
                try:
                    self.dependencies.complete_telegram_login(
                        self._login_request,
                        self._code,
                        password=self._password,
                        language_id=self._language_id,
                    )
                except self.dependencies.TelegramPasswordRequired:
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
                path = self.dependencies.download_telegram_channel_video(
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
                self.failed.emit(redact_secrets(exc))


class TelegramContentTranslationWorker(Workflow):
    ready = Event(object)
    failed = Event(str)

    def __init__(
        self,
        config: AppConfig,
        items: object,
        *,
        language_id: str | None = None,
        parent=None,
        dependencies: SourcesDependencies,
    ) -> None:
        super().__init__(parent, dependencies=dependencies)
        self._config = config
        self._language_id = language_id
        self._items = [
            (
                str(getattr(item, "post_id", "") or ""),
                str(getattr(item, "url", "") or ""),
                self.dependencies.telegram_channel_item_translation_text(item),
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
            translator = self.dependencies.get_shared_vietnamese_translator(self._config)
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
                self.failed.emit(redact_secrets(exc))


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


class SourceAudioFilterWorker(Workflow):
    ready = Event(str, str, str)
    failed = Event(str, str)
    warning = Event(str, str)

    def failure_arguments(self, error: Exception) -> tuple[str, ...]:
        return self._source_path, str(error)

    def __init__(
        self,
        source_path: str,
        output_path: Path,
        mode: str = "auto",
        model: str = "htdemucs",
        parent=None,
        *,
        dependencies: SourcesDependencies,
    ) -> None:
        super().__init__(parent, dependencies=dependencies)
        self._source_path = source_path
        self._output_path = output_path
        self._mode = mode
        self._model = model
        self._process: subprocess.Popen | None = None
        self._stop_requested = False

    def stop(self) -> None:
        self._stop_requested = True
        if self._process is not None and self._process.poll() is None:
            self.dependencies.terminate_process(self._process)

    def run(self) -> None:
        try:
            if self.dependencies.source_voice_filter_cached_output_valid(self._output_path, self._mode, self._model):
                backend = self.dependencies.read_source_voice_filter_backend(self._output_path) or self._mode
                self.ready.emit(self._source_path, str(self._output_path), backend)
                return
            self._output_path.parent.mkdir(parents=True, exist_ok=True)
            result = self.dependencies.apply_source_voice_filter(
                Path(self._source_path),
                self._output_path,
                mode=self._mode,
                model=self._model,
                process_runner=self._run_process,
            )
            self.dependencies.write_source_voice_filter_metadata(result)
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
            raise self.dependencies.SourceVoiceFilterCancelled("Voice filter stopped.")
        resolved_command = self.dependencies.resolve_source_voice_filter_command(command)
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
            raise self.dependencies.SourceVoiceFilterCancelled("Voice filter stopped.")
        if return_code != 0:
            raise subprocess.CalledProcessError(return_code, resolved_command, output=stdout, stderr=stderr)


class PlaybackCompatibilityWorker(Workflow):
    ready = Event(str, str)
    failed = Event(str, str)

    def failure_arguments(self, error: Exception) -> tuple[str, ...]:
        return self._source_path, str(error)

    def __init__(
        self,
        source_path: str,
        output_path: Path,
        cache_key: str = "",
        parent=None,
        *,
        dependencies: SourcesDependencies,
    ) -> None:
        super().__init__(parent, dependencies=dependencies)
        self._source_path = source_path
        self._output_path = output_path
        self._cache_key = cache_key
        self._process: subprocess.Popen | None = None
        self._stop_requested = False

    def stop(self) -> None:
        self._stop_requested = True
        if self._process is not None and self._process.poll() is None:
            self.dependencies.terminate_process(self._process)

    def run(self) -> None:
        try:
            if self.dependencies.playback_compat_cached_output_valid(
                self._output_path, self._source_path, self._cache_key
            ):
                self.ready.emit(self._source_path, str(self._output_path))
                return
            self.dependencies.remove_playback_compat_output(self._output_path)
            self._output_path.parent.mkdir(parents=True, exist_ok=True)
            command = [
                self.dependencies.ffmpeg_executable(),
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
                "5.1",
                "-crf",
                "18",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-b:a",
                "256k",
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
                self.dependencies.remove_playback_compat_output(self._output_path)
                return
            if return_code != 0:
                raise subprocess.CalledProcessError(return_code, command)
            self.dependencies.write_playback_compat_metadata(self._output_path, self._source_path, self._cache_key)
            self.ready.emit(self._source_path, str(self._output_path))
        except Exception as exc:
            self.dependencies.remove_playback_compat_output(self._output_path)
            if not self._stop_requested:
                LOGGER.exception("Playback compatibility worker failed.")
                self.failed.emit(self._source_path, redact_secrets(exc))
        finally:
            self._process = None


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
        message = redact_secrets(str(exc).strip() or exc.__class__.__name__)
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
    message = redact_secrets(" ".join(lines))
    if len(message) <= max_length:
        return message
    tail_budget = max(80, max_length - 20)
    return f"...{message[-tail_budget:]}"


def _process_executable_name(command: object) -> str:
    if isinstance(command, (list, tuple)) and command:
        command_parts = [str(part) for part in command]
        if "ai_player.adapters.media.demucs_runner" in command_parts:
            return "demucs"
        return str(command[0])
    return str(command or "process")
