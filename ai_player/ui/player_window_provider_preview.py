from __future__ import annotations

from ai_player.ui.provider_preview_controller import ProviderPreviewController


class PlayerProviderPreviewMixin:
    def _init_provider_preview(self) -> None:
        self._provider_preview = ProviderPreviewController(self)

    def _start_provider_preview(self, kind: str) -> None:
        self._provider_preview.start(kind)

    def _stop_provider_preview(self, wait_ms: int = 5000) -> bool:
        return self._provider_preview.stop(wait_ms=wait_ms)
