from __future__ import annotations

from ai_player.configuration import AppConfig
from ai_player.ui.readiness_controller import ReadinessController, ReadinessProfile, provider_preview_kind


def test_readiness_controller_applies_profile_override() -> None:
    controller = ReadinessController(
        lambda: AppConfig(audio_source="original"),
        AppConfig(),
    )

    controller.select_profile("meeting_document")
    config = controller.profile_config()

    assert controller.selected_profile_key == "meeting_document"
    assert config.audio_source == "document_editor"


def test_readiness_controller_falls_back_when_current_config_fails() -> None:
    controller = ReadinessController(
        lambda: (_ for _ in ()).throw(RuntimeError("config unavailable")),
        AppConfig(asr_provider="assemblyai", asr_api_key=""),
        profiles=(ReadinessProfile("demo", "", "demo", "demo"),),
    )

    status = controller.status("demo")

    assert status.attention_count >= 1
    assert status.provider_preview_kind == "asr"
    assert "requires an API key" in status.text


def test_provider_preview_kind_prefers_first_attention_runtime_area() -> None:
    items = (
        type("Item", (), {"name": "Translation", "status": "ATTENTION"})(),
        type("Item", (), {"name": "TTS", "status": "ATTENTION"})(),
    )

    assert provider_preview_kind(items) == "translation"
