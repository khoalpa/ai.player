from __future__ import annotations

import os
import sys

import pytest
from PySide6.QtWidgets import QApplication

SLOW_TEST_MODULES = {
    "test_player_window_smoke.py",
    "test_release_smoke.py",
    "test_ui_clickthrough_smoke.py",
    "test_workflow_ffmpeg_exports.py",
}
SMOKE_TEST_MODULES = {
    "test_player_window_smoke.py",
    "test_release_smoke.py",
    "test_ui_clickthrough_smoke.py",
    "test_workflow_smoke_check.py",
}


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        module_name = item.path.name
        is_slow = module_name in SLOW_TEST_MODULES or item.get_closest_marker("slow") is not None
        if module_name in SLOW_TEST_MODULES:
            item.add_marker(pytest.mark.slow)
        if not is_slow:
            item.add_marker(pytest.mark.fast)
        if module_name in SMOKE_TEST_MODULES:
            item.add_marker(pytest.mark.smoke)


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
