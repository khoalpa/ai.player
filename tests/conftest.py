from __future__ import annotations

import os
import sys

import pytest
from PySide6.QtWidgets import QApplication


@pytest.fixture(autouse=True)
def isolated_settings_file(tmp_path, monkeypatch) -> None:
    from ai_player.core import settings_store

    config_dir = tmp_path / "config"
    monkeypatch.setattr(settings_store, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(settings_store, "SETTINGS_FILE", config_dir / "settings.json")


@pytest.fixture(scope="session")
def qapp() -> QApplication:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv[:1])
    return app
