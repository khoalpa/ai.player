from __future__ import annotations

from ai_player.ui.features.base import Feature
from ai_player.ui.provider_preview_controller import ProviderPreviewController


class PlayerProviderPreviewFeature(Feature):
    def _init_provider_preview(self) -> None:
        self.context.provider_preview.controller = ProviderPreviewController(self.context)

    def _start_provider_preview(self, kind: str) -> None:
        self.context.provider_preview.controller.start(kind)

    def _stop_provider_preview(self, wait_ms: int = 5000) -> bool:
        return self.context.provider_preview.controller.stop(wait_ms=wait_ms)
