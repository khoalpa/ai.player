from __future__ import annotations

import json

import pytest

from ai_player.core import runtime_catalog as catalog


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
