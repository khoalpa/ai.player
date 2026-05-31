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
    assert data.get("transcript_cleanup_api_key_secret", {}).get("value") != "secret"
    assert data["transcript_path"] == ""
    assert data["audio_source"] == "original"


def test_save_and_load_app_config_round_trips_secret_payload(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(settings_store, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(settings_store, "SETTINGS_FILE", tmp_path / "settings.json")
    monkeypatch.setattr(
        settings_store,
        "protect_text",
        lambda value: {"scheme": "test", "value": f"protected:{value}"},
    )
    monkeypatch.setattr(
        settings_store,
        "reveal_text",
        lambda payload: str(payload.get("value", "")).removeprefix("protected:")
        if isinstance(payload, dict)
        else "",
    )

    settings_store.save_app_config(AppConfig(transcript_cleanup_api_key="cleanup-secret"))
    data = json.loads((tmp_path / "settings.json").read_text(encoding="utf-8"))
    config = settings_store.load_app_config(AppConfig(transcript_cleanup_api_key=""))

    assert "transcript_cleanup_api_key" not in data
    assert data["transcript_cleanup_api_key_secret"] == {"scheme": "test", "value": "protected:cleanup-secret"}
    assert config.transcript_cleanup_api_key == "cleanup-secret"


def test_load_app_config_keeps_env_secret_over_saved_secret(tmp_path, monkeypatch) -> None:
    settings_file = tmp_path / "settings.json"
    settings_file.write_text(
        json.dumps({"transcript_cleanup_api_key_secret": {"scheme": "test", "value": "saved-secret"}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(settings_store, "SETTINGS_FILE", settings_file)
    monkeypatch.setattr(settings_store, "reveal_text", lambda _payload: "saved-secret")

    config = settings_store.load_app_config(AppConfig(transcript_cleanup_api_key="env-secret"))

    assert config.transcript_cleanup_api_key == "env-secret"


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


def test_save_and_load_app_config_round_trips_telegram_blacklist(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(settings_store, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(settings_store, "SETTINGS_FILE", tmp_path / "settings.json")

    settings_store.save_app_config(
        AppConfig(
            telegram_blacklisted_item_keys=("102", "https://t.me/demo/pending"),
            telegram_blacklisted_content_keys=("same content",),
            telegram_auto_open_videos=False,
            telegram_last_url="https://t.me/demo",
            telegram_last_post_id="101",
            telegram_last_search="needle",
            telegram_last_filter="video",
            telegram_side_panel_visible=False,
            telegram_side_panel_sizes=(640, 360),
            video_url_recent_urls=("https://example.test/a.mp4", "https://youtu.be/demo"),
        )
    )
    config = settings_store.load_app_config(AppConfig())

    assert config.telegram_blacklisted_item_keys == ("102", "https://t.me/demo/pending")
    assert config.telegram_blacklisted_content_keys == ("same content",)
    assert config.telegram_auto_open_videos is False
    assert config.telegram_last_url == "https://t.me/demo"
    assert config.telegram_last_post_id == "101"
    assert config.telegram_last_search == "needle"
    assert config.telegram_last_filter == "video"
    assert config.telegram_side_panel_visible is False
    assert config.telegram_side_panel_sizes == (640, 360)
    assert config.video_url_recent_urls == ("https://example.test/a.mp4", "https://youtu.be/demo")


def test_load_app_config_preserves_saved_tts_warmup(tmp_path, monkeypatch) -> None:
    settings_file = tmp_path / "settings.json"
    settings_file.write_text(json.dumps({"runtime_warmup_tts": True}), encoding="utf-8")
    monkeypatch.setattr(settings_store, "SETTINGS_FILE", settings_file)
    monkeypatch.setattr(settings_store, "read_preserved_source_terms_file", lambda: "OpenAI")
    monkeypatch.delenv("AI_PLAYER_PREWARM_TTS", raising=False)

    config = settings_store.load_app_config(AppConfig(runtime_warmup_tts=False))

    assert config.runtime_warmup_tts is True


def test_load_app_config_allows_env_to_enable_tts_warmup(tmp_path, monkeypatch) -> None:
    settings_file = tmp_path / "settings.json"
    settings_file.write_text(json.dumps({"runtime_warmup_tts": False}), encoding="utf-8")
    monkeypatch.setattr(settings_store, "SETTINGS_FILE", settings_file)
    monkeypatch.setattr(settings_store, "read_preserved_source_terms_file", lambda: "OpenAI")
    monkeypatch.setenv("AI_PLAYER_PREWARM_TTS", "1")

    config = settings_store.load_app_config(AppConfig.from_env())

    assert config.runtime_warmup_tts is True


def test_load_app_config_migrates_old_default_vieneu_voices_to_southern(tmp_path, monkeypatch) -> None:
    settings_file = tmp_path / "settings.json"
    settings_file.write_text(
        json.dumps(
            {
                "tts_provider": "vieneu",
                "tts_voice": "Bích Ngọc",
                "tts_female_voice": "Bích Ngọc",
                "tts_male_voice": "Phạm Tuyên",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(settings_store, "SETTINGS_FILE", settings_file)
    monkeypatch.setattr(settings_store, "read_preserved_source_terms_file", lambda: "OpenAI")

    config = settings_store.load_app_config(AppConfig())

    assert config.tts_voice == "Thục Đoan"
    assert config.tts_female_voice == "Thục Đoan"
    assert config.tts_male_voice == "Xuân Vĩnh"


def test_load_app_config_migrates_ascii_old_default_vieneu_voices_to_southern(tmp_path, monkeypatch) -> None:
    settings_file = tmp_path / "settings.json"
    settings_file.write_text(
        json.dumps(
            {
                "tts_provider": "vieneu",
                "tts_voice": "Bich Ngoc",
                "tts_female_voice": "Bich Ngoc",
                "tts_male_voice": "Pham Tuyen",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(settings_store, "SETTINGS_FILE", settings_file)
    monkeypatch.setattr(settings_store, "read_preserved_source_terms_file", lambda: "OpenAI")

    config = settings_store.load_app_config(AppConfig())

    assert config.tts_voice == "Thục Đoan"
    assert config.tts_female_voice == "Thục Đoan"
    assert config.tts_male_voice == "Xuân Vĩnh"


def test_load_app_config_keeps_custom_vieneu_voice(tmp_path, monkeypatch) -> None:
    settings_file = tmp_path / "settings.json"
    settings_file.write_text(
        json.dumps({"tts_provider": "vieneu", "tts_voice": "Ngọc"}, ensure_ascii=False),
        encoding="utf-8",
    )
    monkeypatch.setattr(settings_store, "SETTINGS_FILE", settings_file)
    monkeypatch.setattr(settings_store, "read_preserved_source_terms_file", lambda: "OpenAI")

    config = settings_store.load_app_config(AppConfig())

    assert config.tts_voice == "Ngọc"


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


def test_load_app_config_ignores_non_finite_float_values(tmp_path, monkeypatch) -> None:
    settings_file = tmp_path / "settings.json"
    settings_file.write_text(
        json.dumps({"dubbing_speed_min": "nan", "vieneu_tts_temperature": "inf"}),
        encoding="utf-8",
    )
    monkeypatch.setattr(settings_store, "SETTINGS_FILE", settings_file)

    config = settings_store.load_app_config(AppConfig())

    assert config.dubbing_speed_min == AppConfig().dubbing_speed_min
    assert config.vieneu_tts_temperature == AppConfig().vieneu_tts_temperature


def test_load_app_config_reads_preserved_source_terms_from_file_not_settings(tmp_path, monkeypatch) -> None:
    settings_file = tmp_path / "settings.json"
    terms_file = tmp_path / "preserved_source_terms.txt"
    terms_file.write_text("OpenAI\n先生\n", encoding="utf-8")
    settings_file.write_text(
        json.dumps(
            {
                "preserve_source_terms": True,
                "preserved_source_terms": "STALE",
                "preserved_english_terms": "LEGACY_STALE",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(settings_store, "SETTINGS_FILE", settings_file)
    monkeypatch.setattr(
        settings_store,
        "read_preserved_source_terms_file",
        lambda: terms_file.read_text(encoding="utf-8").strip(),
    )

    config = settings_store.load_app_config(AppConfig())

    assert config.preserved_source_terms == "OpenAI\n先生"
    assert config.preserved_english_terms == "OpenAI\n先生"


def test_load_app_config_refreshes_preserved_source_terms_from_file_without_settings(tmp_path, monkeypatch) -> None:
    settings_file = tmp_path / "missing-settings.json"
    monkeypatch.setattr(settings_store, "SETTINGS_FILE", settings_file)
    monkeypatch.setattr(settings_store, "read_preserved_source_terms_file", lambda: "OpenAI\nNLLB")

    config = settings_store.load_app_config(AppConfig(preserved_source_terms="STALE"))

    assert config.preserved_source_terms == "OpenAI\nNLLB"
    assert config.preserved_english_terms == "OpenAI\nNLLB"


def test_load_app_config_migrates_legacy_english_terms_flag_to_source_flag(tmp_path, monkeypatch) -> None:
    settings_file = tmp_path / "settings.json"
    settings_file.write_text(json.dumps({"preserve_english_terms": False}), encoding="utf-8")
    monkeypatch.setattr(settings_store, "SETTINGS_FILE", settings_file)
    monkeypatch.setattr(settings_store, "read_preserved_source_terms_file", lambda: "OpenAI")

    config = settings_store.load_app_config(AppConfig())

    assert config.preserve_source_terms is False
    assert config.preserve_english_terms is False


def test_save_app_config_writes_term_flags_but_not_term_content(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(settings_store, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(settings_store, "SETTINGS_FILE", tmp_path / "settings.json")
    config = AppConfig(
        preserve_source_terms=True,
        preserved_source_terms="OpenAI\n오빠",
        preserve_english_terms=False,
        preserved_english_terms="legacy",
    )

    settings_store.save_app_config(config)
    data = json.loads((tmp_path / "settings.json").read_text(encoding="utf-8"))

    assert data["preserve_source_terms"] is True
    assert data["preserve_english_terms"] is True
    assert data["preserved_source_terms"] == ""
    assert data["preserved_english_terms"] == ""


def test_load_app_config_migrates_removed_translation_provider_and_models(tmp_path, monkeypatch) -> None:
    settings_file = tmp_path / "settings.json"
    settings_file.write_text(
        json.dumps(
            {
                "translator_provider": "auto",
                "local_translation_model": r"D:\project\ai.player\models\translation\marian\en-vi",
                "transcript_cleanup_model": r"D:\project\ai.player\models\transcript_cleanup\Qwen2.5-7B-Instruct",
                "original_audio_voice_filter_mode": "auto",
            }
        ),
        encoding="utf-8",
    )
    cleanup_model = tmp_path / "Qwen2.5-3B-Instruct"
    cleanup_model.mkdir()
    monkeypatch.setattr(settings_store, "SETTINGS_FILE", settings_file)
    monkeypatch.setattr(settings_store, "LOCAL_TRANSCRIPT_CLEANUP_MODEL_PATH", cleanup_model)

    config = settings_store.load_app_config(AppConfig())

    assert config.translator_provider == "nllb_ct2"
    assert config.local_translation_model == settings_store.LOCAL_TRANSLATION_MODEL_CT2_INT8_PATH
    assert config.transcript_cleanup_model == str(cleanup_model)
    assert config.original_audio_voice_filter_mode == "fast"
