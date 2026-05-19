from pathlib import Path

from ai_player.core.config import AppConfig
from ai_player.services import demucs_separation
from ai_player.services.audio_playback import _pcm_bytes_to_float32
from ai_player.services.runtime_warmup import RuntimeWarmupCancelled, warm_runtime_components
from ai_player.services.translation_runtime import (
    clear_shared_vietnamese_translators,
    get_shared_vietnamese_translator,
    translation_runtime_key,
)
from ai_player.services.tts import tts_output_suffix
from ai_player.services.whisper_runtime import (
    clear_shared_whisper_models,
    effective_whisper_compute_type,
    effective_whisper_device,
)


def test_whisper_runtime_cpu_compute_falls_back_to_int8() -> None:
    assert effective_whisper_compute_type("float16", "cpu") == "int8"
    assert effective_whisper_device("cpu") == "cpu"


def test_translation_runtime_passthrough_for_none_provider() -> None:
    clear_shared_vietnamese_translators()
    config = AppConfig(translator_provider="none")
    translator = get_shared_vietnamese_translator(config)

    assert translator.translate("  Hello   world  ", "en") == "Hello world"
    assert translation_runtime_key(AppConfig(translator_provider="none")).provider == "none"


def test_runtime_warmup_respects_disabled_flag() -> None:
    config = AppConfig(runtime_warmup_enabled=False)

    assert warm_runtime_components(config) == {}


def test_runtime_warmup_cancel_raises() -> None:
    config = AppConfig(runtime_warmup_enabled=True, runtime_warmup_whisper=True)

    try:
        warm_runtime_components(config, cancel_callback=lambda: True)
    except RuntimeWarmupCancelled:
        return
    raise AssertionError("expected RuntimeWarmupCancelled")


def test_tts_output_suffix() -> None:
    assert tts_output_suffix("edge") == "mp3"
    assert tts_output_suffix("vieneu") == "wav"


def test_audio_pcm_conversion_shape() -> None:
    data = _pcm_bytes_to_float32(b"\x00\x00\xff\x7f", sample_width=2, channels=1)

    assert data.shape == (2,)
    assert data[0] == 0


def test_demucs_unavailable_path(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(demucs_separation.shutil, "which", lambda _name: None)

    try:
        demucs_separation.separate_vocals(Path("input.wav"), tmp_path)
    except demucs_separation.DemucsSeparationError:
        return
    raise AssertionError("expected DemucsSeparationError")


def test_runtime_caches_clear_without_error() -> None:
    clear_shared_whisper_models()
    clear_shared_vietnamese_translators()
