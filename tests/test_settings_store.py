from __future__ import annotations

import json

import pytest

from ai_player.core import settings_store
from ai_player.core.config import AppConfig


@pytest.mark.parametrize("content", [None, "{", "[]"])
def test_read_settings_returns_empty_for_missing_or_invalid(tmp_path, monkeypatch, content: str | None) -> None:
    settings_file = tmp_path / "settings.json"
    if content is not None:
        settings_file.write_text(content, encoding="utf-8")
    monkeypatch.setattr(settings_store, "SETTINGS_FILE", settings_file)

    assert settings_store._read_settings() == {}


@pytest.mark.parametrize(("value", "expected"), [("yes", True), ("0", False), (1, True)])
def test_coerce_value_for_bool(value, expected: bool) -> None:
    assert settings_store._coerce_value(value, False) is expected


def test_save_app_config_omits_secret_and_resets_session_fields(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(settings_store, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(settings_store, "SETTINGS_FILE", tmp_path / "settings.json")
    config = AppConfig(transcript_cleanup_api_key="secret", transcript_path="session.srt", audio_source="transcript")

    settings_store.save_app_config(config)
    data = json.loads((tmp_path / "settings.json").read_text(encoding="utf-8"))

    assert "transcript_cleanup_api_key" not in data
    assert data["transcript_path"] == ""
    assert data["audio_source"] == "original"


def test_load_app_config_ignores_unknown_secret_and_session_values(tmp_path, monkeypatch) -> None:
    settings_file = tmp_path / "settings.json"
    settings_file.write_text(
        json.dumps(
            {
                "unknown": "ignored",
                "transcript_cleanup_api_key": "secret",
                "transcript_path": "ignored.srt",
                "target_language": "en",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(settings_store, "SETTINGS_FILE", settings_file)

    config = settings_store.load_app_config(AppConfig(target_language="vi", transcript_path="base.srt"))

    assert config.target_language == "en"
    assert config.transcript_cleanup_api_key == ""
    assert config.transcript_path == "base.srt"


def test_load_app_config_coerces_numeric_values(tmp_path, monkeypatch) -> None:
    settings_file = tmp_path / "settings.json"
    settings_file.write_text(
        json.dumps({"translation_max_tokens": "42", "dubbing_speed_min": "0.85"}),
        encoding="utf-8",
    )
    monkeypatch.setattr(settings_store, "SETTINGS_FILE", settings_file)

    config = settings_store.load_app_config(AppConfig())

    assert config.translation_max_tokens == 42
    assert config.dubbing_speed_min == 0.85
