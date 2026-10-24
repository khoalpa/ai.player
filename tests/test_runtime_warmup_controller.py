from __future__ import annotations

from ai_player.configuration import AppConfig
from ai_player.ui import runtime_warmup_controller
from ai_player.ui.runtime_warmup_controller import RuntimeWarmupController
from tests.ui_context_helpers import context_for


class _FakeSignal:
    def __init__(self) -> None:
        self.callbacks = []

    def connect(self, callback) -> None:
        self.callbacks.append(callback)


class _FakeWorker:
    instances: list[_FakeWorker] = []

    def __init__(self, config: AppConfig, parent=None) -> None:
        self.config = config
        self.parent = parent
        self.status_changed = _FakeSignal()
        self.finished_successfully = _FakeSignal()
        self.failed = _FakeSignal()
        self.finished = _FakeSignal()
        self.started = False
        self.stopped = False
        self.deleted = False
        self.instances.append(self)

    def start(self) -> None:
        self.started = True

    def stop(self) -> None:
        self.stopped = True

    def wait(self, _wait_ms: int) -> bool:
        return True

    def deleteLater(self) -> None:
        self.deleted = True


class _FakeApp:
    def platformName(self) -> str:
        return "windows"


class _FakeStatusBar:
    def __init__(self) -> None:
        self.message = ""

    def currentMessage(self) -> str:
        return self.message

    def showMessage(self, message: str) -> None:
        self.message = message


class _FakeOwner:
    def __init__(self) -> None:
        self._config = AppConfig(runtime_warmup_enabled=True)
        self._status_bar = _FakeStatusBar()
        self.background_details = []

    def statusBar(self) -> _FakeStatusBar:
        return self._status_bar

    def _tr(self, key: str) -> str:
        return {
            "warmup_loading_whisper": "Preloading Whisper...",
            "warmup_loading_translation": "Preloading translator...",
            "warmup_loading_transcript_cleanup": "Preloading transcript cleanup...",
            "warmup_loading_tts": "Preloading TTS...",
            "warmup_started_whisper": "Started preloading Whisper...",
            "warmup_started_translation": "Started preloading translator...",
            "warmup_started_transcript_cleanup": "Started preloading transcript cleanup...",
            "warmup_started_tts": "Started preloading TTS...",
            "warmup_loaded_whisper": "Preloaded Whisper in {seconds}s.",
            "warmup_loaded_translation": "Preloaded translator in {seconds}s.",
            "warmup_loaded_transcript_cleanup": "Preloaded transcript cleanup in {seconds}s.",
            "warmup_loaded_tts": "Preloaded TTS in {seconds}s.",
            "status_runtime_warmup_ready": "Runtime is ready.",
            "status_runtime_warmup_failed": "Runtime preloading failed: {detail}",
        }.get(key, key)

    def _runtime_startup_status_message(self) -> str:
        return "Startup status"

    def _set_background_task_detail(self, name: str, detail: object, *, log_detail: object | None = None) -> None:
        self.background_details.append((name, detail, log_detail))


def test_runtime_warmup_controller_starts_and_stops_worker(monkeypatch) -> None:
    _FakeWorker.instances = []
    monkeypatch.setattr(runtime_warmup_controller, "RuntimeWarmupWorker", _FakeWorker)
    monkeypatch.setattr(runtime_warmup_controller, "has_runtime_warmup_stage", lambda _config: True)
    monkeypatch.setattr(runtime_warmup_controller.QApplication, "instance", lambda: _FakeApp())
    controller = RuntimeWarmupController(context_for(_FakeOwner()))

    controller.start()

    assert len(_FakeWorker.instances) == 1
    worker = _FakeWorker.instances[0]
    assert worker.started is True

    assert controller.stop(wait_ms=25) is True
    assert worker.stopped is True
    assert worker.deleted is True


def test_runtime_warmup_controller_keeps_user_status() -> None:
    owner = _FakeOwner()
    owner.statusBar().showMessage("User opened a file")
    controller = RuntimeWarmupController(context_for(owner))

    controller.status_changed("Preloading translator...")
    controller.failed("boom")

    assert owner.statusBar().currentMessage() == "User opened a file"


def test_runtime_warmup_controller_logs_historical_events_separately() -> None:
    owner = _FakeOwner()
    controller = RuntimeWarmupController(context_for(owner))

    controller.status_changed("Preloading Whisper...")
    controller.status_changed("Preloaded Whisper in 0.2s.")

    assert owner.background_details[0] == (
        "Runtime preloading",
        "Preloading Whisper...",
        "Started preloading Whisper...",
    )
    assert owner.background_details[1] == (
        "Runtime preloading",
        "Preloaded Whisper in 0.2s.",
        "Preloaded Whisper in 0.2s.",
    )
