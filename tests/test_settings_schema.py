import json

import pytest

from ai_player.adapters.storage import settings_store
from ai_player.configuration import AppConfig
from ai_player.configuration.schema import CURRENT_SCHEMA_VERSION, UnsupportedSettingsVersion


def test_unversioned_settings_migrate_without_losing_preferences(tmp_path, monkeypatch):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"original_audio_volume": 37, "translation_max_tokens": 384}), encoding="utf-8")
    monkeypatch.setattr(settings_store, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(settings_store, "SETTINGS_FILE", path)

    config = settings_store.load_app_config()
    settings_store.save_app_config(config)

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == CURRENT_SCHEMA_VERSION
    assert settings_store.load_app_config().original_audio_volume == 37
    assert settings_store.load_app_config().translation_max_tokens == 384


def test_future_settings_are_not_overwritten_including_split_files(tmp_path, monkeypatch):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"schema_version": CURRENT_SCHEMA_VERSION + 1}), encoding="utf-8")
    split = tmp_path / "runtime.local.json"
    split.write_text('{"future_runtime": true}', encoding="utf-8")
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    monkeypatch.setattr(settings_store, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(settings_store, "SETTINGS_FILE", path)

    with pytest.raises(UnsupportedSettingsVersion):
        settings_store.save_app_config(AppConfig())

    assert {p.name: p.read_bytes() for p in tmp_path.iterdir()} == before
