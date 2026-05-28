from __future__ import annotations

import queue

import pytest

from ai_player.core.config import AppConfig
from ai_player.services import tts, vieneu_tts_server


@pytest.mark.parametrize(("value", "expected"), [("edge-tts", "edge"), ("off", "none"), ("local", "vieneu")])
def test_normalize_tts_provider(value: str, expected: str) -> None:
    assert tts.normalize_tts_provider(value) == expected


@pytest.mark.parametrize(("value", "expected"), [("standard", "standard"), ("api", "remote"), ("cuda", "fast")])
def test_normalize_vieneu_mode(value: str, expected: str) -> None:
    assert tts.normalize_vieneu_mode(value) == expected


@pytest.mark.parametrize(("value", "expected"), [("gpu", "cuda"), ("cpu", "cpu"), ("weird", "auto")])
def test_normalize_vieneu_device(value: str, expected: str) -> None:
    assert tts.normalize_vieneu_device(value) == expected


@pytest.mark.parametrize(
    ("provider", "voice", "expected"),
    [
        ("edge", "vi-VN-NamMinhNeural", "male"),
        ("edge", "vi-VN-HoaiMyNeural", "female"),
        ("vieneu", "Binh", "male"),
        ("vieneu", "Doan", "female"),
        ("vieneu", "unknown", "unknown"),
    ],
)
def test_voice_gender(provider: str, voice: str, expected: str) -> None:
    assert tts.voice_gender(provider, voice) == expected


@pytest.mark.parametrize(
    ("voice", "expected"),
    [
        ("vi-VN-NamMinhNeural", "vi-VN-NamMinhNeural"),
        ("Binh", "vi-VN-NamMinhNeural"),
        ("Doan", "vi-VN-HoaiMyNeural"),
        ("", "vi-VN-HoaiMyNeural"),
    ],
)
def test_compatible_edge_voice_id_falls_back_by_gender(voice: str, expected: str) -> None:
    assert tts._compatible_edge_voice_id(voice) == expected


def test_vieneu_preferred_voice_fallbacks_use_southern_voices_first() -> None:
    turbo_config = AppConfig(vieneu_tts_mode="turbo")
    standard_config = AppConfig(vieneu_tts_mode="standard")

    assert tts._preferred_voice_ids("vieneu", turbo_config, "female")[0] == "Thục Đoan"
    assert tts._preferred_voice_ids("vieneu", turbo_config, "male")[0] == "Xuân Vĩnh"
    assert tts._preferred_voice_ids("vieneu", standard_config, "female")[0] == "Doan"
    assert tts._preferred_voice_ids("vieneu", standard_config, "male")[0] == "Vinh"


def test_remote_vieneu_fallback_stays_remote_only(monkeypatch) -> None:
    config = AppConfig(
        vieneu_tts_core="remote",
        vieneu_tts_mode="turbo",
        vieneu_tts_api_base="http://localhost:23333/v1",
        vieneu_tts_python="D:/missing/python.exe",
        vieneu_tts_runtime="subprocess",
    )
    monkeypatch.setattr(tts, "_runtime_has_cuda", lambda: True)

    assert tts._vieneu_fallback_configs(config) == [config]


def test_vieneu_subprocess_requires_valid_python() -> None:
    provider = tts.VieNeuTTSProvider(AppConfig(vieneu_tts_python="D:/missing/python.exe"))

    assert not provider._should_use_subprocess(provider._config)


def test_remote_vieneu_uses_standard_voice_catalog() -> None:
    config = AppConfig(vieneu_tts_core="remote", tts_voice="Thục Đoan")

    assert [voice.id for voice in tts.available_voices("vieneu", config)] == [
        "Binh",
        "Tuyen",
        "Ngoc",
        "Ly",
        "Vinh",
        "Doan",
    ]
    assert tts._compatible_vieneu_voice_id(config, "Thục Đoan") == "Doan"
    assert tts._compatible_vieneu_voice_id(config, "Xuân Vĩnh") == "Vinh"


def test_remote_vieneu_rejects_empty_audio(monkeypatch, tmp_path) -> None:
    class FakeEngine:
        def get_preset_voice(self, voice_id):
            return {"id": voice_id}

        def infer(self, **_kwargs):
            return []

        def save(self, _audio, output_path):
            with open(output_path, "wb") as handle:
                handle.write(b"")

    config = AppConfig(vieneu_tts_core="remote", vieneu_tts_api_base="http://localhost:23333/v1")
    provider = tts.VieNeuTTSProvider(config)
    monkeypatch.setattr(tts, "_get_vieneu_engine", lambda _config: FakeEngine())

    with pytest.raises(tts.TTSError, match="remote API"):
        provider._synthesize_in_process(config, "xin chao", tmp_path / "out.wav", "Doan")


def test_remote_vieneu_engine_kwargs_use_lightweight_codec() -> None:
    kwargs = tts._build_vieneu_engine_kwargs(
        mode="remote",
        api_base="http://localhost:23333/v1",
        model_name="pnnbao-ump/VieNeu-TTS",
        device="cuda",
        backend="native",
    )

    assert kwargs["api_base"] == "http://localhost:23333/v1"
    assert kwargs["model_name"] == "pnnbao-ump/VieNeu-TTS"
    assert kwargs["codec_repo"] == "neuphonic/neucodec-onnx-decoder-int8"
    assert kwargs["codec_device"] == "cpu"


def test_remote_vieneu_subprocess_kwargs_use_lightweight_codec() -> None:
    kwargs = vieneu_tts_server._engine_kwargs(
        mode="remote",
        api_base="http://localhost:23333/v1",
        model_name="pnnbao-ump/VieNeu-TTS",
        device="cuda",
        backend="native",
        decoder_path="",
        encoder_path="",
        standard_codec_path="",
    )

    assert kwargs["codec_repo"] == "neuphonic/neucodec-onnx-decoder-int8"
    assert kwargs["codec_device"] == "cpu"


def test_vieneu_effective_paths_fall_back_to_bundled_files(monkeypatch, tmp_path) -> None:
    decoder = tmp_path / "vieneu_decoder.onnx"
    encoder = tmp_path / "vieneu_encoder.onnx"
    codec = tmp_path / "distill-neucodec"
    decoder.write_bytes(b"decoder")
    encoder.write_bytes(b"encoder")
    codec.mkdir()
    monkeypatch.setattr(tts, "INTERNAL_VIENEU_TURBO_DECODER", str(decoder))
    monkeypatch.setattr(tts, "INTERNAL_VIENEU_TURBO_ENCODER", str(encoder))
    monkeypatch.setattr(tts, "INTERNAL_VIENEU_STANDARD_CODEC", str(codec))
    config = AppConfig(
        vieneu_tts_decoder_path="D:/missing/decoder.onnx",
        vieneu_tts_encoder_path="D:/missing/encoder.onnx",
        vieneu_tts_standard_codec_path="D:/missing/codec",
    )

    assert tts._effective_vieneu_decoder_path(config) == str(decoder)
    assert tts._effective_vieneu_encoder_path(config) == str(encoder)
    assert tts._effective_vieneu_standard_codec_path(config) == str(codec)


def test_vieneu_import_root_falls_back_to_bundled_runtime(tmp_path) -> None:
    assert tts._vieneu_import_root(tmp_path).name == "vieneu_tts"


def test_tts_cache_text_normalizes_unicode_and_format_chars() -> None:
    assert tts._cache_text("Cafe\u0301\u200b") == "Caf\u00e9"


@pytest.mark.parametrize("value", ["Ah...", "ừm", "hmmm", "mm mm", "..."])
def test_non_speech_tts_text_detects_filler_sounds(value: str) -> None:
    assert tts.is_non_speech_tts_text(value)


@pytest.mark.parametrize("value", ["xin chào", "có", "AI Player"])
def test_non_speech_tts_text_keeps_spoken_words(value: str) -> None:
    assert not tts.is_non_speech_tts_text(value)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("\u4f55\u3067\u3059\u304b", ""),
        ("\u0110\u00e2y l\u00e0 \u5148\u8f29", "\u0110\u00e2y l\u00e0"),
        ("AI Player", "AI Player"),
        ("\u00ea \u00ea \u00ea", ""),
    ],
)
def test_prepare_tts_text_removes_source_script_residue(value: str, expected: str) -> None:
    assert tts.prepare_tts_text(value, "vi") == expected


def test_pathological_tts_duration_detects_short_text_that_runs_too_long() -> None:
    assert tts.is_pathological_tts_duration("l\u00e0 g\u00ec", 5.0, target_duration_seconds=1.0)
    assert not tts.is_pathological_tts_duration("l\u00e0 g\u00ec", 1.2, target_duration_seconds=1.0)


def test_pathological_tts_duration_ignores_invalid_durations() -> None:
    assert not tts.is_pathological_tts_duration("hello", "bad", target_duration_seconds=float("inf"))
    assert not tts.is_pathological_tts_duration("hello", float("nan"), target_duration_seconds="bad")


def test_vieneu_infer_kwargs_sanitize_invalid_numeric_values() -> None:
    kwargs = tts._build_vieneu_infer_kwargs(
        engine=object(),
        text="hello",
        voice="voice",
        temperature=float("nan"),
        max_chars="bad",
    )

    assert kwargs["temperature"] == 0.6
    assert kwargs["max_chars"] == 160


def test_tts_cache_path_sanitizes_invalid_vieneu_numeric_config(tmp_path) -> None:
    config = AppConfig(vieneu_tts_temperature=float("inf"), vieneu_tts_max_chars_chunk="bad")

    cache_path = tts._tts_cache_path("vieneu", config, "hello", "voice", tmp_path / "out.wav")

    assert cache_path.suffix == ".wav"


def test_vieneu_server_read_response_rejects_invalid_json_payload() -> None:
    class FakeProcess:
        def poll(self):
            return None

    client = tts.VieNeuServerClient.__new__(tts.VieNeuServerClient)
    client._process = FakeProcess()
    client._output_queue = queue.Queue()
    client._output_queue.put("AI_PLAYER_JSON:not-json\n")

    with pytest.raises(tts.TTSError, match="invalid JSON"):
        client._read_response(timeout_seconds=1)


def test_vieneu_server_read_response_requires_json_object() -> None:
    class FakeProcess:
        def poll(self):
            return None

    client = tts.VieNeuServerClient.__new__(tts.VieNeuServerClient)
    client._process = FakeProcess()
    client._output_queue = queue.Queue()
    client._output_queue.put("AI_PLAYER_JSON:[]\n")

    with pytest.raises(tts.TTSError, match="invalid JSON payload"):
        client._read_response(timeout_seconds=1)


def test_cached_tts_provider_reuses_cached_audio(monkeypatch, tmp_path) -> None:
    calls: list[str] = []
    cache_path = tmp_path / "cache.wav"

    class FakeProvider(tts.BaseTTSProvider):
        def synthesize(self, text, output_path, voice=None) -> None:
            calls.append(str(text))
            output_path.write_bytes(b"audio")

    monkeypatch.setattr(tts, "_tts_cache_path", lambda *_args, **_kwargs: cache_path)
    provider = tts.CachedTTSProvider(FakeProvider(), AppConfig(), "vieneu")

    provider.synthesize("hello", tmp_path / "first.wav", voice="Doan")
    provider.synthesize("hello", tmp_path / "second.wav", voice="Doan")

    assert calls == ["hello"]
    assert (tmp_path / "second.wav").read_bytes() == b"audio"


def test_edge_tts_provider_retries_empty_audio(monkeypatch, tmp_path) -> None:
    attempts = 0

    class FakeCommunicate:
        def __init__(self, text, voice) -> None:
            self.text = text
            self.voice = voice

        async def save(self, path) -> None:
            nonlocal attempts
            attempts += 1
            if attempts < 3:
                raise RuntimeError("No audio was received. Please verify that your parameters are correct.")
            assert self.text == "xin chao"
            assert self.voice == "vi-VN-HoaiMyNeural"
            with open(path, "wb") as handle:
                handle.write(b"audio")

    monkeypatch.setattr(tts.edge_tts, "Communicate", FakeCommunicate)
    monkeypatch.setattr(tts.time, "sleep", lambda _seconds: None)
    provider = tts.EdgeTTSProvider(AppConfig(tts_voice="Doan"))

    provider.synthesize(" xin chao ", tmp_path / "out.mp3")

    assert attempts == 3
    assert (tmp_path / "out.mp3").read_bytes() == b"audio"
