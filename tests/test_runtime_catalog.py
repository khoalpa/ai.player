from __future__ import annotations

import json

import pytest

from ai_player.core import runtime_catalog as catalog
from ai_player.core.config import DEFAULT_PERFORMANCE_PRESET, AppConfig
from ai_player.services import tts
from scripts.compare_performance_presets import compare_presets


@pytest.mark.parametrize(("include_auto", "expected"), [(True, "auto"), (False, "vi")])
def test_available_language_options_include_expected_defaults(include_auto: bool, expected: str) -> None:
    options = catalog.available_language_options(include_auto=include_auto, language_id="missing")

    assert expected in {option.id for option in options}
    assert ("auto" in {option.id for option in options}) is include_auto


def test_available_dropdown_options_deduplicates_defaults() -> None:
    options = catalog.available_dropdown_options(
        "missing-folder",
        defaults=(("One", "a"), ("Duplicate", "a"), ("Two", "b")),
        language_id="missing",
    )

    assert [(option.label, option.value) for option in options] == [("One", "a"), ("Two", "b")]


def test_available_translation_provider_options_uses_language_pack_labels() -> None:
    english = catalog.available_translation_provider_options("en")
    vietnamese = catalog.available_translation_provider_options("vi")

    assert [option.id for option in english] == ["nllb_ct2", "nllb", "none"]
    assert english[-1].name == "No translation"
    assert vietnamese[-1].name == "Không dịch"


@pytest.mark.parametrize(
    ("data", "value", "label"),
    [
        ({"value": "x", "label": "Label X"}, "x", "Label X"),
        ({"id": "id-x", "name": "Name X"}, "id-x", "Name X"),
        ("plain", "plain", "plain"),
        (None, "9", "9"),
    ],
)
def test_dropdown_option_from_data_shapes(data, value: str, label: str) -> None:
    option = catalog._dropdown_option_from_data(data, fallback_value="9")

    assert option is not None
    assert option.value == value
    assert option.label == label


def test_load_gui_translations_has_fallback_language() -> None:
    translations = catalog.load_gui_translations()

    assert "vi" in translations
    assert isinstance(translations["vi"], dict)


def test_available_local_llm_options_skips_tts_gguf(monkeypatch, tmp_path) -> None:
    llm = tmp_path / "Qwen"
    llm.mkdir()
    (llm / "config.json").write_text("{}", encoding="utf-8")
    (llm / "tokenizer.json").write_text("{}", encoding="utf-8")
    (llm / "model.safetensors").write_text("", encoding="utf-8")
    tts = tmp_path / "tts" / "vieneu.gguf"
    tts.parent.mkdir()
    tts.write_text("", encoding="utf-8")
    monkeypatch.setattr(catalog, "TRANSCRIPT_CLEANUP_MODELS_PATH", tmp_path)

    options = catalog.available_local_llm_options()

    assert [option.name for option in options] == ["Qwen"]


def test_available_asr_models_scans_local_whisper_dirs(monkeypatch, tmp_path) -> None:
    model_dir = tmp_path / "faster-whisper-large-v3"
    model_dir.mkdir()
    (model_dir / "config.json").write_text("{}", encoding="utf-8")
    (model_dir / "model.bin").write_text("", encoding="utf-8")
    monkeypatch.setattr(catalog, "ASR_MODELS_PATH", tmp_path)

    options = catalog.available_asr_models()

    assert options == [catalog.RuntimeOption(str(model_dir.resolve()), "faster-whisper-large-v3")]


def test_available_ocr_models_scans_tessdata_dirs(monkeypatch, tmp_path) -> None:
    tessdata = tmp_path / "tessdata"
    tessdata.mkdir()
    (tessdata / "eng.traineddata").write_text("", encoding="utf-8")
    (tessdata / "vie.traineddata").write_text("", encoding="utf-8")
    monkeypatch.setattr(catalog, "_tessdata_candidates", lambda: [tessdata])

    options = catalog.available_ocr_models()

    assert options[0].id == str(tessdata.resolve())
    assert "en" in options[0].name
    assert "vi" in options[0].name


def test_read_dropdown_options_file_accepts_wrapped_options(tmp_path) -> None:
    path = tmp_path / "options.json"
    path.write_text(json.dumps({"options": [{"value": "a", "label": "A"}]}), encoding="utf-8")

    assert catalog._read_dropdown_options_file(path) == [catalog.DropdownOption("A", "a")]


def test_read_dropdown_options_file_ignores_invalid_json(tmp_path) -> None:
    path = tmp_path / "broken.json"
    path.write_text("{", encoding="utf-8")

    assert catalog._read_dropdown_options_file(path) == []


def test_resolve_preset_settings_expands_project_root_placeholder() -> None:
    settings = catalog._resolve_preset_settings(
        {
            "local_translation_model": "${PROJECT_ROOT}\\models\\translation\\demo",
            "vieneu_tts_model_name": "models\\tts\\demo.gguf",
            "tts_voice": "vi-VN-HoaiMyNeural",
        }
    )

    assert settings["local_translation_model"] == str(catalog.PROJECT_ROOT / "models" / "translation" / "demo")
    assert settings["vieneu_tts_model_name"] == str(catalog.PROJECT_ROOT / "models" / "tts" / "demo.gguf")
    assert settings["tts_voice"] == "vi-VN-HoaiMyNeural"


def test_default_config_matches_default_performance_preset(monkeypatch) -> None:
    env_names = (
        "AI_PLAYER_AUDIO_SOURCE",
        "AI_PLAYER_DUBBING_AUTO_MATCH_AUDIO",
        "AI_PLAYER_DUBBING_OVERLAP_POLICY",
        "AI_PLAYER_DUBBING_AUTO_VOICE_GENDER",
        "AI_PLAYER_DUBBING_AUTO_VOICE_GENDER_MODE",
        "AI_PLAYER_DUBBING_LOOKAHEAD_SEGMENTS",
        "AI_PLAYER_DUBBING_MIN_READY_AHEAD_SECONDS",
        "AI_PLAYER_DUBBING_PREBUFFER_SEGMENTS",
        "AI_PLAYER_DUBBING_SPEED_MAX",
        "AI_PLAYER_DUBBING_SPEED_MIN",
        "AI_PLAYER_DUBBING_SPEED_PERCENT",
        "AI_PLAYER_DUBBING_START_DELAY_SECONDS",
        "AI_PLAYER_DUBBING_VOLUME_GAIN_MAX_DB",
        "AI_PLAYER_DUBBING_VOLUME_GAIN_MIN_DB",
        "AI_PLAYER_EXPORT_VIDEO_QUALITY",
        "AI_PLAYER_TRANSLATION_DEVICE",
        "AI_PLAYER_TRANSLATION_MODEL",
        "AI_PLAYER_TRANSLATION_OFFLINE",
        "AI_PLAYER_ORIGINAL_AUDIO_PLAYBACK_DELAY_SECONDS",
        "AI_PLAYER_ORIGINAL_AUDIO_VOICE_FILTER_MODE",
        "AI_PLAYER_SEGMENT_SECONDS",
        "AI_PLAYER_SOURCE_LANGUAGE",
        "AI_PLAYER_TARGET_LANGUAGE",
        "AI_PLAYER_TRANSLATION_MAX_TOKENS",
        "AI_PLAYER_TRANSLATION_BEAMS",
        "AI_PLAYER_TRANSLATOR_PROVIDER",
        "AI_PLAYER_TTS_PROVIDER",
        "AI_PLAYER_VIENEU_TTS_BACKEND",
        "AI_PLAYER_VIENEU_TTS_DEVICE",
        "AI_PLAYER_VIENEU_TTS_MAX_CHARS_CHUNK",
        "AI_PLAYER_VIENEU_TTS_MODE",
        "AI_PLAYER_VIENEU_TTS_MODEL_NAME",
        "AI_PLAYER_VIENEU_TTS_OFFLINE",
        "AI_PLAYER_VIENEU_TTS_RUNTIME",
        "AI_PLAYER_VIENEU_TTS_TEMPERATURE",
        "AI_PLAYER_WHISPER_COMPUTE",
        "AI_PLAYER_WHISPER_BEAM_SIZE",
        "AI_PLAYER_WHISPER_VAD_FILTER",
        "AI_PLAYER_WHISPER_DEVICE",
        "AI_PLAYER_WHISPER_OFFLINE",
        "AI_PLAYER_WHISPER_MODEL",
        "AI_PLAYER_ASR_PROVIDER",
        "AI_PLAYER_OCR_PROVIDER",
        "AI_PLAYER_OCR_MODEL",
        "AI_PLAYER_PERFORMANCE_PRESET",
    )
    for name in env_names:
        monkeypatch.delenv(name, raising=False)

    config = AppConfig.from_env()
    preset = catalog.load_performance_presets()[DEFAULT_PERFORMANCE_PRESET]
    matched_fields = tuple(key for key in preset if hasattr(config, key))

    assert config.performance_preset == DEFAULT_PERFORMANCE_PRESET
    assert {key: getattr(config, key) for key in matched_fields} == {key: preset[key] for key in matched_fields}


def test_performance_presets_default_to_female_voice() -> None:
    presets = catalog.load_performance_presets()

    for settings in presets.values():
        provider = str(settings["tts_provider"])
        voice = str(settings["tts_voice"])

        assert tts.voice_gender(provider, voice) == "female"


def test_vieneu_defaults_use_southern_voice() -> None:
    config = AppConfig()
    presets = catalog.load_performance_presets()

    assert config.tts_voice == "Thục Đoan"
    assert config.tts_female_voice == "Thục Đoan"
    assert config.tts_male_voice == "Xuân Vĩnh"
    assert presets["balanced"]["tts_voice"] == "Thục Đoan"
    assert presets["balanced"]["tts_female_voice"] == "Thục Đoan"
    assert presets["balanced"]["tts_male_voice"] == "Xuân Vĩnh"


def test_performance_preset_comparison_orders_latency_and_quality() -> None:
    rows = {row.preset: row for row in compare_presets("en")}

    assert set(rows) == {"low_latency", "offline_lite", "balanced", "quality"}
    assert rows["balanced"].quality_score > rows["low_latency"].quality_score
    assert rows["low_latency"].latency_score < rows["balanced"].latency_score
    assert rows["quality"].quality_score > rows["balanced"].quality_score
    assert rows["quality"].latency_score > rows["balanced"].latency_score
