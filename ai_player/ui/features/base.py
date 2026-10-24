from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ai_player.ui.features.context import WindowContext


class Feature:
    def __init__(self, context: WindowContext) -> None:
        self.context = context
