from __future__ import annotations

from PySide6.QtCore import QTimer

from ai_player.ui.player_window import PlayerWindow


def test_player_window_constructs_offscreen(qapp) -> None:
    window = PlayerWindow()
    try:
        assert window.windowTitle()
    finally:
        window.close()


def test_player_window_runtime_format_helpers(qapp) -> None:
    window = PlayerWindow()
    try:
        assert window._format_seconds(65) == "01:05"
        assert window._format_bytes(1024) == "1.0 KB"
    finally:
        window.close()


def test_player_window_event_loop_smoke(qapp) -> None:
    window = PlayerWindow()
    try:
        window.show()
        QTimer.singleShot(10, qapp.quit)
        assert qapp.exec() == 0
    finally:
        window.close()
