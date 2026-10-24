from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ai_player.ui.features.context import WindowContext

from typing import Any

from ai_player.core.redaction import compact_redacted_text
from ai_player.workers.player_window_workers import ProviderPreviewWorker


class ProviderPreviewController:
    def __init__(self, owner: WindowContext) -> None:
        self.context = owner
        self._worker: Any | None = None
        self._kind = ""

    def start(self, kind: str) -> None:
        if self._worker is not None:
            self.context.window.statusBar().showMessage(self.context.settings._tr("provider_preview_running"))
            return
        self._kind = str(kind or "")
        self._set_running(True, self._kind)
        set_retry = self.context.get("_set_task_center_retry", None)
        if callable(set_retry):
            set_retry(
                self.context.settings._tr("task_center_retry_provider").format(kind=self._kind),
                lambda kind=self._kind: self.start(kind),
            )
        worker = ProviderPreviewWorker(self._kind, self.context.settings._current_runtime_config(), self.context.window)
        self._worker = worker
        worker.ready.connect(self.ready)
        worker.failed.connect(self.failed)
        worker.finished.connect(lambda worker=worker: self._worker_finished(worker))
        worker.start()

    def stop(self, wait_ms: int = 5000) -> bool:
        worker = self._worker
        if worker is None:
            return True
        stop = getattr(worker, "stop", None)
        if callable(stop):
            stop()
        if hasattr(worker, "wait") and not worker.wait(wait_ms):
            return False
        if hasattr(worker, "deleteLater"):
            worker.deleteLater()
        self._worker = None
        self._set_running(False)
        return True

    def is_running(self) -> bool:
        worker = self._worker
        if worker is None:
            return False
        is_running = getattr(worker, "isRunning", None)
        return bool(is_running()) if callable(is_running) else True

    def task_detail(self) -> str:
        kind = self._kind or "provider"
        return f"Testing {kind} provider/model."

    def ready(self, result: object) -> None:
        message = self._format_result(result)
        kind = str(getattr(result, "kind", "") or self._kind)
        self._set_status(kind, message)
        self.context.window.statusBar().showMessage(message)

    def failed(self, detail: str) -> None:
        message = self.context.settings._tr("provider_preview_failed").format(detail=self._compact_detail(detail))
        self._set_status(self._kind, message)
        self.context.window.statusBar().showMessage(message)

    def _worker_finished(self, worker: Any) -> None:
        if self._worker is worker:
            self._worker = None
        self._set_running(False)
        worker.deleteLater()

    def _set_running(self, running: bool, kind: str = "") -> None:
        for button in self.context.get("_provider_preview_buttons", {}).values():
            button.setEnabled(not running)
        if running:
            message = self.context.settings._tr("provider_preview_running")
            self._set_status(kind, message)
            self.context.window.statusBar().showMessage(message)

    def _set_status(self, kind: str, message: str) -> None:
        set_detail = self.context.get("_set_background_task_detail", None)
        if callable(set_detail):
            set_detail("Provider preview", message)
        label = self.context.get("_provider_preview_statuses", {}).get(kind)
        if label is not None:
            label.setText(message)
        status = self.context.get("_provider_preview_status", None)
        if status is not None:
            status.setText(message)

    def _format_result(self, result: object) -> str:
        provider = str(getattr(result, "provider", "") or "")
        model = str(getattr(result, "model", "") or "")
        detail = str(getattr(result, "message", "") or "")
        elapsed = float(getattr(result, "elapsed_seconds", 0.0) or 0.0)
        prefix = self.context.settings._tr("provider_preview_success").format(
            provider=provider, seconds=f"{elapsed:.1f}"
        )
        parts = [prefix]
        if model:
            parts.append(model)
        if detail:
            parts.append(detail)
        return " | ".join(parts)

    @staticmethod
    def _compact_detail(detail: object) -> str:
        return compact_redacted_text(detail)
