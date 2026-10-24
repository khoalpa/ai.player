from __future__ import annotations

import threading
import time

import pytest
from PySide6.QtCore import QThread, QTimer, Signal
from PySide6.QtTest import QTest

from ai_player.ui.features import dubbing as player_window_dubbing
from ai_player.ui.features.channel_flow import PlayerChannelFlowFeature
from ai_player.ui.features.runtime import PlayerRuntimeFeature
from ai_player.ui.player_window import PlayerWindow


class _SlowDubbingWorker(QThread):
    status_changed = Signal(str)
    segment_ready = Signal(str, str)
    subtitle_ready = Signal(float, float, str, str)
    audio_started = Signal(float)
    playback_pause_requested = Signal(str)
    playback_resume_requested = Signal(str)
    failed = Signal(str)

    def __init__(self, *_args, parent=None, **_kwargs):
        super().__init__(parent)
        self.started_work = threading.Event()
        self.stopping = threading.Event()
        self.release = threading.Event()
        self.waits: list[int] = []

    def run(self) -> None:
        self.started_work.set()
        self.release.wait(5)

    def stop(self) -> None:
        self.stopping.set()

    def wait(self, milliseconds: int = 0) -> bool:
        self.waits.append(milliseconds)
        return super().wait(milliseconds)


def _wait_until(predicate) -> None:
    deadline = time.monotonic() + 3
    while not predicate() and time.monotonic() < deadline:
        QTest.qWait(10)
    assert predicate()


@pytest.fixture
def dubbing_window(qapp, monkeypatch):
    monkeypatch.setattr(PlayerRuntimeFeature, "_start_runtime_warmup", lambda self: None)
    monkeypatch.setattr(PlayerChannelFlowFeature, "_start_telegram_worker", lambda self, *args, **kwargs: None)
    monkeypatch.setattr(player_window_dubbing, "DubbingWorker", _SlowDubbingWorker)
    window = PlayerWindow()
    window.features.channel_browser._video_path = "test.mp4"
    resumed = []
    monkeypatch.setattr(window.features.media, "_resume_after_dubbing_buffer", resumed.append)
    window.features.layout._dub_button.setChecked(True)
    window.features.dubbing._start_dubbing()
    worker = window.features.lifecycle.workers.dubbing_worker
    assert worker.started_work.wait(1)
    window.show()
    try:
        yield window, worker, resumed
    finally:
        worker.release.set()
        # The C++ thread may already have been deleted by the finished handler.
        try:
            worker.wait(2000)
        except RuntimeError:
            pass
        window.close()
        _wait_until(lambda: not window.isVisible())


def test_stop_keeps_gui_responsive_and_reaps_worker_after_delayed_finish(dubbing_window) -> None:
    window, worker, resumed = dubbing_window
    worker.playback_resume_requested.emit("queued before stop")
    started = time.monotonic()
    assert window.features.dubbing._stop_dubbing() is False
    assert time.monotonic() - started < 0.25
    assert worker.stopping.is_set()
    assert worker.waits == [0]
    assert window.features.lifecycle.workers.dubbing_worker is worker
    assert not window.features.layout._play_button.isEnabled()

    ticks = []
    QTimer.singleShot(0, lambda: ticks.append(True))
    QTest.qWait(30)
    assert ticks == [True]
    assert resumed == []
    worker.playback_resume_requested.emit("queued after stop")
    worker.status_changed.emit("late status")
    QTest.qWait(30)
    assert resumed == []
    assert window.statusBar().currentMessage() != "late status"

    worker.release.set()
    _wait_until(lambda: window.features.lifecycle.workers.dubbing_worker is None)
    assert "Realtime dubbing" not in window.features.task_center.details_controller.details
    assert window.features.layout._play_button.isEnabled()
    assert window.isVisible()


def test_close_waits_asynchronously_and_does_not_restart_dubbing(dubbing_window) -> None:
    window, worker, resumed = dubbing_window
    started = time.monotonic()
    assert window.close() is False
    assert time.monotonic() - started < 0.5
    assert window.isVisible()
    assert window.features.lifecycle._closing
    assert not window.centralWidget().isEnabled()
    assert worker.stopping.is_set()
    worker.playback_resume_requested.emit("late resume during close")
    window.features.dubbing._start_dubbing()
    assert window.features.lifecycle.workers.dubbing_worker is worker

    ticks = []
    QTimer.singleShot(10, lambda: ticks.append(True))
    QTest.qWait(150)
    assert ticks == [True]
    assert resumed == []
    assert worker.waits and set(worker.waits) == {0}
    worker.release.set()
    _wait_until(lambda: not window.isVisible())
    assert window.features.lifecycle.workers.dubbing_worker is None
    assert window.features.layout._player._disposed


def test_stop_all_polls_until_worker_finishes(dubbing_window) -> None:
    window, worker, _resumed = dubbing_window
    started = time.monotonic()
    window.features.task_center._stop_task_center_tasks()
    assert time.monotonic() - started < 0.5
    assert worker.stopping.is_set()
    assert window.features.task_center._task_stop_timer.isActive()
    worker.release.set()
    _wait_until(lambda: not window.features.task_center._task_stop_timer.isActive())
    assert window.features.lifecycle.workers.dubbing_worker is None
    assert window.statusBar().currentMessage() == window.features.settings._tr("runtime_tasks_stopped").format(count=1)


def test_stale_worker_signals_cannot_control_a_new_session(dubbing_window) -> None:
    window, _worker, _resumed = dubbing_window
    messages = []
    generation = window.features.lifecycle.workers.dubbing_worker_generation
    window.features.dubbing._dispatch_dubbing_signal(generation - 1, messages.append, "old worker")
    window.features.dubbing._dispatch_dubbing_signal(generation, messages.append, "current worker")
    assert messages == ["current worker"]


def test_current_worker_signals_are_delivered_to_gui(dubbing_window) -> None:
    _window, worker, resumed = dubbing_window
    sender = threading.Thread(target=lambda: worker.playback_resume_requested.emit("ready to play"))
    sender.start()
    sender.join(timeout=1)
    _wait_until(lambda: resumed == ["ready to play"])
