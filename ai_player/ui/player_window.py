from __future__ import annotations

from PySide6.QtWidgets import QMainWindow

from ai_player.bootstrap import ApplicationContext, create_application_context
from ai_player.ui.features.context import WindowContext
from ai_player.ui.features.initialize import initialize_window


class PlayerWindow(QMainWindow):
    """Qt shell. Features own widgets, state, actions and task lifecycles."""

    def __init__(self, context: ApplicationContext | None = None) -> None:
        super().__init__()
        application = context if context is not None else create_application_context()
        self.features = WindowContext(self, application)
        initialize_window(self.features)

    @property
    def job_manager(self):
        return self.features.jobs

    def closeEvent(self, event) -> None:
        self.features.lifecycle.closeEvent(event)

    def resizeEvent(self, event) -> None:
        self.features.lifecycle.resizeEvent(event)

    def eventFilter(self, watched, event):
        return self.features.media.eventFilter(watched, event)
