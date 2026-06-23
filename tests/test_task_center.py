from __future__ import annotations

from types import SimpleNamespace

import pytest

from ai_player.ui import task_center
from ai_player.ui.player_window import PlayerWindow


@pytest.fixture(autouse=True)
def disable_task_center_background_startups(monkeypatch) -> None:
    monkeypatch.setattr(PlayerWindow, "_start_runtime_warmup", lambda self: None)
    monkeypatch.setattr(PlayerWindow, "_start_telegram_worker", lambda self, *args, **kwargs: None)


class _RunningWorker:
    def __init__(self, running: bool = True) -> None:
        self._running = running

    def isRunning(self) -> bool:
        return self._running


class _RunningController:
    def __init__(self, running: bool = True, detail: str = "") -> None:
        self._running = running
        self._detail = detail

    def is_running(self) -> bool:
        return self._running

    def task_detail(self) -> str:
        return self._detail


class _VideoUrl:
    def __init__(self, opening: bool) -> None:
        self._opening = opening

    def is_opening(self) -> bool:
        return self._opening


def _task(tasks, name: str):
    return next(item for item in tasks if item.name == name)


def test_task_center_formats_idle_state() -> None:
    owner = SimpleNamespace()

    tasks = task_center.collect_background_tasks(owner)

    assert tasks == ()
    assert task_center.format_background_tasks(tasks, idle_text="Idle") == "Idle"


def test_task_center_collects_active_controllers_and_workers() -> None:
    owner = SimpleNamespace(
        _provider_preview=_RunningController(True, "Testing tts provider/model."),
        _runtime_warmup=_RunningController(False),
        _video_url=_VideoUrl(True),
        _dub_worker=_RunningWorker(True),
        _export_worker=_RunningWorker(False),
        _background_task_details={"URL/cache loading": "Downloading youtube 720p"},
    )

    tasks = task_center.collect_background_tasks(owner)

    assert _task(tasks, "Provider preview").detail == "Testing tts provider/model."
    assert _task(tasks, "URL/cache loading").detail == "Downloading youtube 720p"
    assert _task(tasks, "Realtime dubbing").detail == "_RunningWorker"
    assert all(task.name != "Runtime preloading" for task in tasks)
    assert all(task.name != "Export" for task in tasks)


def test_task_center_reports_meeting_source_filter_and_offline_model_details() -> None:
    owner = SimpleNamespace(
        _meeting_worker=_RunningWorker(True),
        _meeting_elapsed="00:01:23",
        _source_filter_worker=_RunningWorker(True),
        _source_filter_worker_mode="fast",
        _source_filter_worker_model="htdemucs",
        _offline_model_process=object(),
        _offline_model_running_key="all",
        _background_task_details={
            "Source voice filter": "Preparing filtered audio",
            "Offline model download": "Running queued task 1/2: Whisper",
        },
    )

    tasks = task_center.collect_background_tasks(owner)

    assert _task(tasks, "Meeting recorder").detail == "Elapsed 00:01:23"
    assert _task(tasks, "Source voice filter").detail == "Preparing filtered audio"
    assert _task(tasks, "Offline model download").detail == "Running queued task 1/2: Whisper"


def test_task_center_formats_only_running_tasks() -> None:
    tasks = (
        task_center.BackgroundTask("Active", "RUNNING", "busy"),
        task_center.BackgroundTask("Idle", "IDLE", "quiet"),
    )

    assert task_center.format_background_tasks(tasks, idle_text="Idle") == "Active: RUNNING - busy"


def test_task_center_stops_active_tasks() -> None:
    calls = []

    class Owner:
        _provider_preview = _RunningController(True)
        _runtime_warmup = _RunningController(False)
        _video_url = _VideoUrl(True)
        _dub_worker = _RunningWorker(True)
        _export_worker = _RunningWorker(True)

        def _stop_provider_preview(self, wait_ms: int = 0) -> bool:
            calls.append(("preview", wait_ms))
            return True

        def _stop_video_url(self, wait_ms: int = 0) -> bool:
            calls.append(("url", wait_ms))
            return True

        def _stop_dubbing(self) -> bool:
            calls.append(("dubbing", None))
            return True

        def _stop_worker_attr(self, attr_name: str, wait_ms: int = 0) -> bool:
            calls.append((attr_name, wait_ms))
            return attr_name != "_export_worker"

    summary = task_center.stop_background_tasks(Owner(), wait_ms=25)

    assert summary.stopped == 3
    assert summary.failed == ("Export",)
    assert ("preview", 25) in calls
    assert ("url", 25) in calls
    assert ("dubbing", None) in calls
    assert ("_export_worker", 25) in calls


def test_task_center_dashboard_logs_and_lists_active_tasks(qapp) -> None:
    window = PlayerWindow()
    try:
        window._dub_worker = _RunningWorker(True)
        window._set_background_task_detail("Realtime dubbing", "Mock segment 1")
        window._refresh_task_center()

        assert window._task_center_table.item(0, 0).text() == "Realtime dubbing"
        assert window._task_center_table.item(0, 2).text() == "Mock segment 1"
        assert "Realtime dubbing: Mock segment 1" in window._task_center_log_view.toPlainText()
        assert window._task_center_stop_button.isEnabled()
        window._dub_worker = None
        window._settings_save_timer.stop()
    finally:
        window.close()


def test_task_center_dashboard_can_log_historical_detail_separately(qapp) -> None:
    window = PlayerWindow()
    original_runtime_warmup = window._runtime_warmup
    try:
        window._runtime_warmup = _RunningController(True, "Preloading Whisper...")
        window._set_background_task_detail(
            "Runtime preloading",
            "Preloading Whisper...",
            log_detail="Started preloading Whisper...",
        )
        window._refresh_task_center()

        assert window._background_task_details["Runtime preloading"] == "Preloading Whisper..."
        assert window._task_center_table.item(0, 2).text() == "Preloading Whisper..."
        assert "Runtime preloading: Started preloading Whisper..." in window._task_center_log_view.toPlainText()
        window._runtime_warmup = original_runtime_warmup
        window._settings_save_timer.stop()
    finally:
        window._runtime_warmup = original_runtime_warmup
        window.close()


def test_task_center_dashboard_retry_action(qapp) -> None:
    calls = []
    window = PlayerWindow()
    try:
        window._set_task_center_retry("Retry demo", lambda: calls.append("retry"))
        window._retry_task_center_action()

        assert calls == ["retry"]
        assert window.statusBar().currentMessage() == window._tr("task_center_retry_started")
        window._settings_save_timer.stop()
    finally:
        window.close()
