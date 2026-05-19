import faulthandler
import logging
import os
import sys
import traceback

from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication

from ai_player.core.config import RUNTIME_DIR
from ai_player.core.optional_imports import install_unneeded_transformers_optional_import_blocks


def _block_unneeded_optional_imports() -> None:
    install_unneeded_transformers_optional_import_blocks()


_block_unneeded_optional_imports()

from ai_player.ui.player_window import PlayerWindow


def main() -> int:
    os.environ.setdefault("QT_LOGGING_RULES", "qt.multimedia.ffmpeg=false")
    _install_exception_logger()
    _install_native_crash_logger()
    _install_performance_logger()
    app = QApplication(sys.argv)
    app.setApplicationName("AI Player")
    app.setFont(_windows_ui_font())
    app.aboutToQuit.connect(lambda: _log_line("QApplication aboutToQuit"))

    window = PlayerWindow()
    _fit_window_to_screen(window, 1180, 760)
    window.showMaximized()

    return app.exec()


def _install_exception_logger() -> None:
    def excepthook(exc_type, exc, tb):
        log_path = RUNTIME_DIR / "ai-player-error.log"
        log_path.parent.mkdir(exist_ok=True)
        log_path.write_text(
            "".join(traceback.format_exception(exc_type, exc, tb)),
            encoding="utf-8",
        )
        sys.__excepthook__(exc_type, exc, tb)

    sys.excepthook = excepthook


def _install_native_crash_logger() -> None:
    log_path = RUNTIME_DIR / "ai-player-native-crash.log"
    log_path.parent.mkdir(exist_ok=True)
    handle = log_path.open("a", encoding="utf-8")
    faulthandler.enable(file=handle, all_threads=True)


def _install_performance_logger() -> None:
    if str(os.getenv("AI_PLAYER_PERF_LOG", "")).strip().lower() not in {"1", "true", "yes", "on"}:
        return
    log_path = RUNTIME_DIR / "ai-player-performance.log"
    log_path.parent.mkdir(exist_ok=True)
    handler = logging.FileHandler(log_path, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
    logger = logging.getLogger("ai_player.performance")
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)
    logger.propagate = False


def _log_line(message: str) -> None:
    log_path = RUNTIME_DIR / "ai-player-runtime.log"
    log_path.parent.mkdir(exist_ok=True)
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(message + "\n")


def _windows_ui_font() -> QFont:
    families = set(QFontDatabase.families())
    for family in ("Segoe UI Variable", "Segoe UI", "Arial"):
        if family in families:
            return QFont(family, 10)
    return QFont("Sans Serif", 10)


def _fit_window_to_screen(window: PlayerWindow, desired_width: int, desired_height: int) -> None:
    screen = QApplication.primaryScreen()
    if screen is None:
        window.resize(desired_width, desired_height)
        return

    available = screen.availableGeometry()
    width = min(desired_width, available.width())
    height = min(desired_height, available.height())
    window.setMinimumSize(min(640, width), min(480, height))
    window.resize(width, height)
    window.move(
        available.x() + max(0, (available.width() - width) // 2),
        available.y() + max(0, (available.height() - height) // 2),
    )
