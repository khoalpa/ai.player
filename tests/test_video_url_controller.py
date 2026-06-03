from __future__ import annotations

from ai_player.ui import video_url_controller
from ai_player.ui.video_url_controller import (
    VideoUrlController,
    lower_playback_quality_value,
    video_url_failure_is_unrecoverable,
    video_url_open_kwargs,
    video_url_request_is_youtube_channel_item_failure,
    video_url_request_should_fallback_to_browser,
    video_url_retry_payload,
)


class _FakeSignal:
    def __init__(self) -> None:
        self.callbacks = []

    def connect(self, callback) -> None:
        self.callbacks.append(callback)


class _FakeWorker:
    instances: list[_FakeWorker] = []

    def __init__(
        self,
        url: str,
        playback_quality: str,
        *,
        full_cache: bool = True,
        language_id: str | None = None,
        parent=None,
    ) -> None:
        self.url = url
        self.playback_quality = playback_quality
        self.full_cache = full_cache
        self.language_id = language_id
        self.parent = parent
        self.progress_changed = _FakeSignal()
        self.resolved = _FakeSignal()
        self.failed = _FakeSignal()
        self.finished = _FakeSignal()
        self.started = False
        self.stopped = False
        self.deleted = False
        self.running = False
        self.instances.append(self)

    def start(self) -> None:
        self.started = True
        self.running = True

    def stop(self) -> None:
        self.stopped = True
        self.running = False

    def isRunning(self) -> bool:
        return self.running

    def wait(self, _wait_ms: int) -> bool:
        return True

    def deleteLater(self) -> None:
        self.deleted = True


class _FakeButton:
    def __init__(self) -> None:
        self.enabled = True

    def setEnabled(self, enabled: bool) -> None:
        self.enabled = enabled


class _FakeOwner:
    def __init__(self) -> None:
        self._open_url_button = _FakeButton()

    def _video_cache_progress_changed(self, _data) -> None:
        pass

    def _video_url_resolved(self, _source) -> None:
        pass

    def _video_url_failed(self, _message: str) -> None:
        pass


def test_video_url_controller_starts_and_finishes_worker(monkeypatch) -> None:
    _FakeWorker.instances = []
    monkeypatch.setattr(video_url_controller, "VideoSourceWorker", _FakeWorker)
    owner = _FakeOwner()
    controller = VideoUrlController(owner)

    assert controller.start("https://example.test/video.mp4", "720p", full_cache=False, language_id="en")

    worker = _FakeWorker.instances[0]
    assert worker.url == "https://example.test/video.mp4"
    assert worker.playback_quality == "720p"
    assert worker.full_cache is False
    assert worker.language_id == "en"
    assert worker.started is True
    assert owner._open_url_button.enabled is False

    controller.finished()

    assert worker.deleted is True
    assert owner._open_url_button.enabled is True
    assert controller.is_opening() is False


def test_video_url_controller_blocks_double_start_and_stops(monkeypatch) -> None:
    _FakeWorker.instances = []
    monkeypatch.setattr(video_url_controller, "VideoSourceWorker", _FakeWorker)
    owner = _FakeOwner()
    controller = VideoUrlController(owner)

    assert controller.start("https://example.test/one.mp4", "best", full_cache=True)
    assert not controller.start("https://example.test/two.mp4", "best", full_cache=True)
    assert len(_FakeWorker.instances) == 1

    worker = _FakeWorker.instances[0]
    assert controller.stop(wait_ms=25) is True
    assert worker.stopped is True
    assert worker.deleted is True
    assert owner._open_url_button.enabled is True


def test_video_url_retry_helpers_preserve_request_context() -> None:
    request = {
        "url": "https://www.youtube.com/watch?v=abc",
        "keep_telegram_context": True,
        "browser_fallback_on_unavailable": True,
    }

    assert video_url_retry_payload(request, full_cache=False) == {
        "url": "https://www.youtube.com/watch?v=abc",
        "keep_telegram_context": True,
        "full_cache": False,
        "browser_fallback_on_unavailable": True,
    }
    assert video_url_open_kwargs(request, full_cache=True) == {
        "keep_telegram_context": True,
        "full_cache_override": True,
        "browser_fallback_on_unavailable": True,
    }


def test_video_url_failure_helpers_classify_unrecoverable_and_browser_fallback() -> None:
    request = {
        "url": "https://www.youtube.com/watch?v=abc",
        "browser_fallback_on_unavailable": True,
    }

    assert video_url_failure_is_unrecoverable("ERROR: [youtube] abc: Private video")
    assert video_url_request_should_fallback_to_browser(
        request,
        "This video is not available",
        can_open_browser=lambda url: url.startswith("https://"),
    )
    assert not video_url_request_should_fallback_to_browser(
        request,
        "HTTP Error 429: Too Many Requests",
        can_open_browser=lambda _url: True,
    )


def test_video_url_helper_detects_youtube_channel_item_failure_and_lower_quality() -> None:
    request = {"keep_telegram_context": True}

    assert video_url_request_is_youtube_channel_item_failure(
        request,
        channel_provider="youtube",
        current_channel_item=object(),
    )
    assert not video_url_request_is_youtube_channel_item_failure(
        request,
        channel_provider="telegram",
        current_channel_item=object(),
    )
    assert lower_playback_quality_value("best") == "1080p"
    assert lower_playback_quality_value("720p") == "480p"
    assert lower_playback_quality_value("360p") == ""
    assert lower_playback_quality_value("unknown") == "480p"
