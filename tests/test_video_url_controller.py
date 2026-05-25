from __future__ import annotations

from ai_player.ui import video_url_controller
from ai_player.ui.video_url_controller import VideoUrlController


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
