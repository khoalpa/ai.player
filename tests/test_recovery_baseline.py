from pathlib import Path

from ai_player.core.config import DEFAULT_PERFORMANCE_PRESET, AppConfig
from ai_player.core.runtime_diagnostics import collect_runtime_diagnostics
from ai_player.services.document_reader import create_text_document_transcript, is_supported_document_path
from ai_player.services.translation import (
    PassthroughTranslator,
    configured_translation_backend,
    normalize_translator_provider,
)
from ai_player.services.tts import available_tts_providers, normalize_tts_provider
from ai_player.services.video_source import is_supported_video_url, resolve_video_source


def test_app_config_defaults_are_constructible(monkeypatch) -> None:
    monkeypatch.delenv("AI_PLAYER_PERFORMANCE_PRESET", raising=False)
    config = AppConfig.from_env()

    assert config.gui_language
    assert config.target_language
    assert config.performance_preset == DEFAULT_PERFORMANCE_PRESET == "balanced"


def test_runtime_diagnostics_collects_required_sections() -> None:
    report = collect_runtime_diagnostics(include_audio_devices=False)

    section_titles = [section.title for section in report.sections]
    assert "Python packages" in section_titles
    assert "External tools" in section_titles


def test_text_document_transcript_smoke(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("ai_player.services.document_reader.CONFIG_DIR", tmp_path)

    transcript = create_text_document_transcript("Hello AI Player recovery baseline.", seconds_per_segment=3)

    assert transcript.segment_count == 1
    assert transcript.transcript_path.exists()
    assert "Hello AI Player" in transcript.transcript_path.read_text(encoding="utf-8")


def test_document_extension_filter() -> None:
    assert is_supported_document_path("demo.pdf")
    assert is_supported_document_path(Path("demo.docx"))
    assert not is_supported_document_path("demo.exe")


def test_direct_video_url_resolution() -> None:
    source = resolve_video_source("https://example.com/video.mp4")

    assert is_supported_video_url(source.input_url)
    assert source.playback_url == "https://example.com/video.mp4"
    assert source.provider == "direct"


def test_translation_passthrough_and_provider_aliases() -> None:
    assert normalize_translator_provider("off") == "none"
    assert PassthroughTranslator().translate("  Hello   world  ", "en") == "Hello world"
    assert configured_translation_backend(AppConfig(translator_provider="none"))


def test_tts_provider_aliases_and_options() -> None:
    assert normalize_tts_provider("edge-tts") == "edge"
    assert normalize_tts_provider("off") == "none"
    assert {provider.id for provider in available_tts_providers()} >= {"vieneu", "edge", "none"}
