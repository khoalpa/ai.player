from __future__ import annotations

from typing import Any

from ai_player.workers.player_window_workers import VideoSourceWorker

UNRECOVERABLE_VIDEO_URL_MARKERS = (
    "this video is not available",
    "video unavailable",
    "private video",
    "has been removed",
    "account associated with this video has been terminated",
)


class VideoUrlController:
    def __init__(self, owner: Any) -> None:
        self._owner = owner
        self._worker: VideoSourceWorker | None = None

    def start(self, url: str, playback_quality: str, *, full_cache: bool, language_id: str | None = None) -> bool:
        if self.is_opening():
            return False
        self.set_opening_controls(False)
        worker = VideoSourceWorker(
            url,
            playback_quality,
            full_cache=full_cache,
            language_id=language_id,
            parent=self._owner,
        )
        self._worker = worker
        worker.progress_changed.connect(self._owner._video_cache_progress_changed)
        worker.resolved.connect(self._owner._video_url_resolved)
        worker.failed.connect(self._owner._video_url_failed)
        worker.finished.connect(self.finished)
        worker.start()
        return True

    def stop(self, wait_ms: int = 5000) -> bool:
        worker = self._worker
        if worker is None:
            self.set_opening_controls(True)
            return True
        stop = getattr(worker, "stop", None)
        if callable(stop):
            stop()
        else:
            worker.requestInterruption()
        if not worker.wait(wait_ms):
            return False
        worker.deleteLater()
        self._worker = None
        self.set_opening_controls(True)
        return True

    def is_opening(self) -> bool:
        return self._worker is not None and self._worker.isRunning()

    def finished(self) -> None:
        if self._worker is not None:
            self._worker.deleteLater()
            self._worker = None
        self.set_opening_controls(True)
        callback = getattr(self._owner, "_video_url_finished", None)
        if callable(callback):
            callback()

    def set_opening_controls(self, enabled: bool) -> None:
        button = getattr(self._owner, "_open_url_button", None)
        if button is not None:
            button.setEnabled(enabled)


def video_url_failure_is_unrecoverable(detail: object) -> bool:
    normalized = " ".join(str(detail or "").casefold().split())
    return any(marker in normalized for marker in UNRECOVERABLE_VIDEO_URL_MARKERS)


def lower_playback_quality_value(value: object) -> str:
    order = ["best", "1080p", "720p", "480p", "360p"]
    current = str(value or "").strip().lower()
    if current not in order:
        current = "720p"
    index = order.index(current)
    return order[index + 1] if index + 1 < len(order) else ""


def video_url_request_is_youtube_channel_item_failure(
    request: object,
    *,
    channel_provider: object,
    current_channel_item: object | None,
) -> bool:
    return bool(
        isinstance(request, dict)
        and request.get("keep_telegram_context")
        and str(channel_provider or "").strip().lower() == "youtube"
        and current_channel_item is not None
    )


def video_url_request_should_fallback_to_browser(
    request: object,
    detail: object,
    *,
    can_open_browser,
) -> bool:
    if not isinstance(request, dict) or not request.get("browser_fallback_on_unavailable"):
        return False
    url = str(request.get("url") or "")
    return bool(video_url_failure_is_unrecoverable(detail) and can_open_browser(url))


def video_url_retry_payload(request: dict, *, full_cache: bool) -> dict[str, object]:
    payload: dict[str, object] = {
        "url": str(request.get("url") or ""),
        "keep_telegram_context": bool(request.get("keep_telegram_context")),
        "full_cache": bool(full_cache),
    }
    if request.get("browser_fallback_on_unavailable"):
        payload["browser_fallback_on_unavailable"] = True
    return payload


def video_url_open_kwargs(request: dict, *, full_cache: bool) -> dict[str, object]:
    kwargs: dict[str, object] = {
        "keep_telegram_context": bool(request.get("keep_telegram_context")),
        "full_cache_override": bool(full_cache),
    }
    if request.get("browser_fallback_on_unavailable"):
        kwargs["browser_fallback_on_unavailable"] = True
    return kwargs
