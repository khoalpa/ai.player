from __future__ import annotations

from ai_player.core import runtime_privacy
from ai_player.core.config import AppConfig


def test_runtime_privacy_reports_offline_default() -> None:
    items = runtime_privacy.build_runtime_privacy(AppConfig())

    assert items == ()
    assert runtime_privacy.format_runtime_privacy(items, offline_text="Offline") == "Offline"


def test_runtime_privacy_reports_online_provider_data_types() -> None:
    config = AppConfig(
        asr_provider="assemblyai",
        translator_provider="deepl",
        tts_provider="edge",
        ocr_provider="google_vision",
        transcript_cleanup_mode="light",
        transcript_cleanup_provider="groq",
        dubbing_auto_voice_gender=True,
        dubbing_auto_voice_gender_mode="ai",
        speaker_gender_provider="huggingface_gender",
    )

    items = runtime_privacy.build_runtime_privacy(config)
    by_feature = {item.feature: item for item in items}

    assert by_feature["ASR"].data_type == "audio"
    assert by_feature["Translation"].data_type == "text"
    assert by_feature["TTS"].provider == "edge"
    assert by_feature["OCR"].data_type == "image"
    assert by_feature["Transcript cleanup"].provider == "groq"
    assert by_feature["Speaker gender"].data_type == "audio"

    summary = runtime_privacy.format_runtime_privacy(items, offline_text="Offline")
    assert "ASR: assemblyai (audio)" in summary
    assert "OCR: google_vision (image)" in summary


def test_runtime_privacy_ignores_disabled_cleanup_and_non_ai_speaker_gender() -> None:
    config = AppConfig(
        transcript_cleanup_mode="off",
        transcript_cleanup_provider="groq",
        dubbing_auto_voice_gender=True,
        dubbing_auto_voice_gender_mode="balanced",
        speaker_gender_provider="huggingface_gender",
    )

    items = runtime_privacy.build_runtime_privacy(config)

    assert all(item.feature != "Transcript cleanup" for item in items)
    assert all(item.feature != "Speaker gender" for item in items)
