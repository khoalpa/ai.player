from __future__ import annotations

from types import SimpleNamespace

from ai_player.core.config import AppConfig
from ai_player.ui import provider_preview_controller
from ai_player.ui.provider_preview_controller import ProviderPreviewController


class _FakeSignal:
    def __init__(self) -> None:
        self.callbacks = []

    def connect(self, callback) -> None:
        self.callbacks.append(callback)


class _FakeWorker:
    instances: list[_FakeWorker] = []

    def __init__(self, kind: str, config: AppConfig, parent=None) -> None:
        self.kind = kind
        self.config = config
        self.parent = parent
        self.ready = _FakeSignal()
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


class _FakeButton:
    def __init__(self) -> None:
        self.enabled = True

    def setEnabled(self, enabled: bool) -> None:
        self.enabled = bool(enabled)


class _FakeLabel:
    def __init__(self) -> None:
        self.text = ""

    def setText(self, text: str) -> None:
        self.text = text


class _FakeStatusBar:
    def __init__(self) -> None:
        self.message = ""

    def showMessage(self, message: str) -> None:
        self.message = message


class _FakeOwner:
    def __init__(self) -> None:
        self._status_bar = _FakeStatusBar()
        self._provider_preview_buttons = {"tts": _FakeButton(), "asr": _FakeButton()}
        self._provider_preview_statuses = {"tts": _FakeLabel(), "asr": _FakeLabel()}
        self._provider_preview_status = _FakeLabel()

    def _current_runtime_config(self) -> AppConfig:
        return AppConfig(tts_provider="edge")

    def _tr(self, key: str) -> str:
        return {
            "provider_preview_running": "Testing provider/model...",
            "provider_preview_success": "{provider} ready in {seconds}s",
            "provider_preview_failed": "Provider test failed: {detail}",
        }.get(key, key)

    def statusBar(self) -> _FakeStatusBar:
        return self._status_bar


def test_provider_preview_controller_starts_worker_and_stops_cleanly(monkeypatch) -> None:
    _FakeWorker.instances = []
    monkeypatch.setattr(provider_preview_controller, "ProviderPreviewWorker", _FakeWorker)
    owner = _FakeOwner()
    controller = ProviderPreviewController(owner)

    controller.start("tts")

    assert len(_FakeWorker.instances) == 1
    worker = _FakeWorker.instances[0]
    assert worker.kind == "tts"
    assert worker.started is True
    assert owner._provider_preview_buttons["tts"].enabled is False
    assert owner._provider_preview_buttons["asr"].enabled is False
    assert owner._provider_preview_statuses["tts"].text == "Testing provider/model..."

    assert controller.stop(wait_ms=25) is True
    assert worker.stopped is True
    assert worker.deleted is True
    assert owner._provider_preview_buttons["tts"].enabled is True
    assert owner._provider_preview_buttons["asr"].enabled is True


def test_provider_preview_controller_formats_success_and_failure() -> None:
    owner = _FakeOwner()
    controller = ProviderPreviewController(owner)

    controller.ready(
        SimpleNamespace(
            kind="tts",
            provider="edge",
            model="voice-model",
            elapsed_seconds=1.24,
            message="Audio preview created.",
        )
    )

    assert owner._provider_preview_statuses["tts"].text == "edge ready in 1.2s | voice-model | Audio preview created."
    assert owner.statusBar().message == owner._provider_preview_statuses["tts"].text

    controller.start = lambda _kind: None
    controller._kind = "asr"
    controller.failed(" line one\n\nline two " + ("x" * 700))

    assert owner._provider_preview_statuses["asr"].text.startswith("Provider test failed: line one line two")
    assert len(owner._provider_preview_statuses["asr"].text) < 540
