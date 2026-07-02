from __future__ import annotations

from types import SimpleNamespace

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

from ai_player.services.adult_extractors import AdultHostSupport
from ai_player.services.workflow_cache import clear_workflow_text_cache, get_text_result, put_text_result
from ai_player.ui import task_center
from ai_player.ui.background_task_controller import BackgroundTaskController
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


class _PlayingPlayer:
    def __init__(self, playing: bool) -> None:
        self._playing = playing

    def is_playing(self) -> bool:
        return self._playing


def _task(tasks, name: str):
    return next(item for item in tasks if item.name == name)


def test_task_center_formats_idle_state() -> None:
    owner = SimpleNamespace()

    tasks = task_center.collect_background_tasks(owner)

    assert tasks == ()
    assert task_center.format_background_tasks(tasks, idle_text="Idle") == "Idle"


def test_background_task_controller_records_and_clears_details() -> None:
    events = []
    refreshes = []

    class Owner:
        def _record_task_center_event(self, name, detail) -> None:
            events.append((name, detail))

        def _refresh_task_center(self) -> None:
            refreshes.append("refresh")

    controller = BackgroundTaskController(Owner())

    controller.set_detail("Export", "  Rendering   audio  ", log_detail="Started export")
    controller.clear_detail("Export")

    assert controller.details == {}
    assert events == [("Export", "Started export")]
    assert refreshes == ["refresh"]


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

        assert window._task_center_table.item(0, 0).text() == window._tr("task_center_group_running")
        assert window._task_center_table.item(1, 0).text() == "Realtime dubbing"
        assert window._task_center_table.item(2, 1).text() == window._tr("task_center_timeline_process")
        assert window._task_center_table.item(2, 2).text() == "Mock segment 1"
        assert "Realtime dubbing: Mock segment 1" in window._task_center_log_view.toPlainText()
        assert window._task_center_stop_button.isEnabled()
        window._dub_worker = None
        window._settings_save_timer.stop()
    finally:
        window._dub_worker = None
        window.close()


def test_task_drawer_hides_active_tasks_while_video_is_playing(qapp) -> None:
    window = PlayerWindow()
    original_player = window._player
    try:
        window._dub_worker = _RunningWorker(True)
        window._player = _PlayingPlayer(True)
        window._refresh_task_center()

        assert window._task_drawer.isHidden()

        window._player = _PlayingPlayer(False)
        window._refresh_task_center()

        assert not window._task_drawer.isHidden()
        window._settings_save_timer.stop()
    finally:
        window._dub_worker = None
        window._player = original_player
        window.close()


def test_task_center_shows_cache_activity_without_enabling_stop_all(qapp) -> None:
    clear_workflow_text_cache()
    put_text_result("translation", {"model": "demo"}, "hello", "xin chao", source_language="en")
    assert get_text_result("translation", {"model": "demo"}, "hello", source_language="en") == "xin chao"
    window = PlayerWindow()
    try:
        window._refresh_task_center()

        names = [window._task_center_table.item(row, 0).text() for row in range(window._task_center_table.rowCount())]
        assert window._tr("task_center_cache_name") in names
        assert not window._task_center_stop_button.isEnabled()
        row = names.index(window._tr("task_center_cache_name"))
        assert "text" in window._task_center_table.item(row, 2).text()
        window._settings_save_timer.stop()
    finally:
        window.close()
        clear_workflow_text_cache()


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
        assert window._task_center_table.item(2, 2).text() == "Preloading Whisper..."
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


def test_adult_host_open_button_uses_registry_open_url(qapp) -> None:
    opened = []
    window = PlayerWindow()
    try:
        window._open_adult_host_url = lambda url: opened.append(url)
        button = window._adult_host_open_button(
            AdultHostSupport(
                site_key="buomtv",
                domains=("buomtv.*", "*.buomtv.*"),
                description="demo",
                open_url="https://buomtv.net",
                mode="generic",
            )
        )

        assert button.isEnabled()
        assert button.toolTip() == "https://buomtv.net"

        QTest.mouseClick(button, Qt.MouseButton.LeftButton)

        assert opened == ["https://buomtv.net"]
        window._settings_save_timer.stop()
    finally:
        window.close()
