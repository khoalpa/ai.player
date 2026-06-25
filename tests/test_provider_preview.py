from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

import pytest

from ai_player.core.config import AppConfig
from ai_player.services import provider_preview


def test_translation_preview_uses_configured_translator(monkeypatch) -> None:
    class FakeTranslator:
        def translate(self, text, source_language=None):
            assert source_language == "en"
            assert "provider preview" in text
            return "Ban dich mau"

    monkeypatch.setattr(provider_preview, "get_shared_vietnamese_translator", lambda _config: FakeTranslator())

    result = provider_preview.preview_provider("translation", AppConfig(translator_provider="none"))

    assert result.provider == "none"
    assert result.message == "Ban dich mau"


def test_cleanup_preview_enables_light_mode_when_cleanup_is_off(monkeypatch) -> None:
    seen_modes: list[str] = []

    class FakeCleaner:
        def __init__(self, config) -> None:
            seen_modes.append(config.transcript_cleanup_mode)

        def clean(self, text, source_language=None):
            assert text == provider_preview.CLEANUP_PREVIEW_INPUT
            assert source_language == "vi"
            return "OpenAI API nay da sach."

    monkeypatch.setattr(provider_preview, "TranscriptCleaner", FakeCleaner)

    result = provider_preview.preview_provider(
        "cleanup",
        AppConfig(transcript_cleanup_mode="off", transcript_cleanup_provider="openai"),
    )

    assert seen_modes == ["light"]
    assert result.provider == "openai"
    assert result.message == (
        f"Input: {provider_preview.CLEANUP_PREVIEW_INPUT}\n"
        "Output: OpenAI API nay da sach."
    )


def test_tts_preview_writes_audio_file(monkeypatch, tmp_path) -> None:
    class FakeTts:
        def synthesize(self, text, output_path, voice=None) -> None:
            output_path.write_bytes(b"fake-audio")

        def close(self) -> None:
            pass

    monkeypatch.setattr(provider_preview, "create_tts_provider", lambda _config: FakeTts())
    monkeypatch.setattr(provider_preview, "_preview_dir", lambda: tmp_path)

    result = provider_preview.preview_provider("tts", AppConfig(tts_provider="edge"))

    assert result.output_path.endswith(".mp3")
    assert "Input: Xin chao, day la ban nghe thu AI Player." in result.message
    assert "Provider: edge" in result.message
    assert "Voice: " in result.message
    assert f"Output: {tmp_path / 'tts-preview.mp3'}" in result.message
    assert "Duration: unknown" in result.message


def test_online_asr_preview_requires_api_key() -> None:
    with pytest.raises(provider_preview.ProviderPreviewError, match="API key"):
        provider_preview.preview_provider("asr", AppConfig(asr_provider="assemblyai", asr_api_key=""))


def test_assemblyai_preview_treats_missing_probe_transcript_as_auth_success(monkeypatch) -> None:
    class FakeResponse:
        status_code = 400
        text = '{"error": "Transcript lookup error, transcript id not found"}'

    calls = []

    def fake_get(url, **kwargs):
        calls.append((url, kwargs))
        return FakeResponse()

    monkeypatch.setattr(provider_preview.requests, "get", fake_get)

    result = provider_preview.preview_provider(
        "asr",
        AppConfig(asr_provider="assemblyai", asr_api_key="assembly-key"),
    )

    assert calls
    assert result.provider == "assemblyai"
    assert "accepted" in result.message


def test_speechmatics_preview_reports_auth_error_without_html(monkeypatch) -> None:
    class FakeResponse:
        status_code = 401
        text = "<html><body><h1>401 Authorization Required</h1><center>nginx</center></body></html>"

    monkeypatch.setattr(provider_preview.requests, "get", lambda *_args, **_kwargs: FakeResponse())

    with pytest.raises(provider_preview.ProviderPreviewError) as error:
        provider_preview.preview_provider(
            "asr",
            AppConfig(asr_provider="speechmatics", asr_api_key="speech-key"),
        )

    message = str(error.value)
    assert "rejected the API key or endpoint" in message
    assert "<html>" not in message


def test_preview_response_redacts_url_query_secrets() -> None:
    class FakeResponse:
        text = "request failed: https://speechmatics.test/v2/jobs?key=preview-secret&status=bad"

    message = provider_preview._preview_response_text(FakeResponse())

    assert "preview-secret" not in message
    assert "key=[redacted]" in message
    assert "status=bad" in message


def test_huggingface_speaker_gender_preview_checks_endpoint(monkeypatch) -> None:
    class FakeResponse:
        status_code = 200
        text = "{}"

    calls = []

    def fake_get(url, **kwargs):
        calls.append((url, kwargs))
        return FakeResponse()

    monkeypatch.setattr(provider_preview.requests, "get", fake_get)

    result = provider_preview.preview_provider(
        "speaker_gender",
        AppConfig(
            speaker_gender_provider="huggingface_gender",
            speaker_gender_api_key="hf-key",
            speaker_gender_model="audeering/wav2vec2-large-robust-6-ft-age-gender",
        ),
    )

    assert calls
    assert calls[0][1]["headers"]["Authorization"] == "Bearer hf-key"
    assert result.provider == "huggingface_gender"
    assert "accepted" in result.message


def test_local_speaker_gender_preview_shows_decision_details(monkeypatch, tmp_path) -> None:
    sample_path = tmp_path / "speaker-preview.wav"
    sample_path.write_bytes(b"audio")

    class FakeSelector:
        def __init__(self, _config) -> None:
            pass

        def select_voice(self, reference_path, *, provider, config):
            assert reference_path == sample_path
            assert provider == "edge"
            return SimpleNamespace(gender="female", confidence=0.87, voice="vi-VN-HoaiMyNeural", reason="ai:accepted")

    monkeypatch.setattr(provider_preview, "_sample_audio_path", lambda: sample_path)
    monkeypatch.setattr(provider_preview, "VoiceGenderSelector", FakeSelector)

    result = provider_preview.preview_provider(
        "speaker_gender",
        AppConfig(
            dubbing_auto_voice_gender_mode="ai",
            speaker_gender_provider="local",
            speaker_gender_model="models/speaker_gender/common-voice-gender-detection",
            tts_provider="edge",
        ),
    )

    assert result.provider == "local"
    assert f"Input: {sample_path}" in result.message
    assert "Detected: female (87%)" in result.message
    assert "Selected voice: vi-VN-HoaiMyNeural" in result.message
    assert "Mode: ai" in result.message
    assert "Reason: ai:accepted" in result.message


def test_local_asr_preview_loads_selected_model(monkeypatch) -> None:
    calls = []

    def fake_load(model, **kwargs):
        calls.append((model, kwargs))
        return object()

    monkeypatch.setattr(provider_preview, "get_shared_whisper_model", fake_load)
    config = replace(
        AppConfig(),
        asr_provider="faster_whisper",
        whisper_model="models/asr/demo",
        whisper_device="cpu",
        whisper_compute_type="int8",
    )

    result = provider_preview.preview_provider("asr", config)

    assert calls == [
        (
            "models/asr/demo",
            {"device": "cpu", "compute_type": "int8", "local_files_only": True},
        )
    ]
    assert result.provider == "faster_whisper"
