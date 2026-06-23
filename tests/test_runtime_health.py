from __future__ import annotations

from ai_player.core import runtime_health
from ai_player.core.config import AppConfig


def _item(items, name: str):
    return next(item for item in items if item.name == name)


def test_runtime_health_reports_missing_online_credentials(monkeypatch) -> None:
    monkeypatch.setattr(runtime_health, "_tool_exists", lambda _name: True)
    monkeypatch.setattr(runtime_health, "_executable_exists", lambda _value: True)
    config = AppConfig(
        asr_provider="assemblyai",
        asr_api_key="",
        translator_provider="google_translate",
        translator_api_key="",
        tts_provider="azure_tts",
        tts_api_key="",
        ocr_provider="google_vision",
        ocr_api_key="",
    )

    items = runtime_health.build_runtime_health(config)

    assert _item(items, "ASR").status == "ATTENTION"
    assert _item(items, "Translation").status == "ATTENTION"
    assert _item(items, "TTS").status == "ATTENTION"
    assert _item(items, "OCR").status == "ATTENTION"


def test_runtime_health_reports_local_model_paths_and_export_tools(monkeypatch, tmp_path) -> None:
    model = tmp_path / "model"
    model.mkdir()
    monkeypatch.setattr(runtime_health, "_tool_exists", lambda _name: True)
    monkeypatch.setattr(runtime_health, "_executable_exists", lambda _value: True)
    config = AppConfig(
        asr_provider="faster_whisper",
        whisper_model=str(model),
        translator_provider="nllb_ct2",
        local_translation_model=str(model),
        tts_provider="vieneu",
        vieneu_tts_model_name=str(model),
        ocr_provider="tesseract",
    )

    items = runtime_health.build_runtime_health(config)

    assert _item(items, "ASR").status == "READY"
    assert _item(items, "Translation").status == "READY"
    assert _item(items, "TTS").status == "READY"
    assert _item(items, "OCR").status == "READY"
    assert _item(items, "Export").status == "READY"


def test_runtime_health_formats_summary() -> None:
    items = (
        runtime_health.RuntimeHealthItem("ASR", "READY", "ok"),
        runtime_health.RuntimeHealthItem("TTS", "ATTENTION", "missing"),
    )

    assert runtime_health.format_runtime_health(items) == "ASR: READY - ok\nTTS: ATTENTION - missing"
