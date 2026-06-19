from __future__ import annotations

import base64
import json
import queue

import pytest

from ai_player.core.config import AppConfig
from ai_player.services import tts, vieneu_tts_server


class _FakeResponse:
    def __init__(self, *, status_code=200, content=b"audio", payload=None, text="") -> None:
        self.status_code = status_code
        self.content = content
        self._payload = payload
        self.text = text

    def json(self):
        if self._payload is None:
            raise ValueError("not json")
        return self._payload


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("edge-tts", "edge"),
        ("off", "none"),
        ("local", "vieneu"),
        ("azure", "azure_tts"),
        ("google-cloud-tts", "google_tts"),
        ("polly", "amazon_polly"),
        ("elevenlabs", "elevenlabs_tts"),
    ],
)
def test_normalize_tts_provider(value: str, expected: str) -> None:
    assert tts.normalize_tts_provider(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [("standard", "standard"), ("api", "turbo"), ("remote", "turbo"), ("cuda", "fast")],
)
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
        ("azure_tts", "vi-VN-NamMinhNeural", "male"),
        ("google_tts", "vi-VN-Neural2-A", "female"),
        ("amazon_polly", "Matthew", "male"),
        ("elevenlabs_tts", "21m00Tcm4TlvDq8ikWAM", "female"),
        ("vieneu", "unknown", "unknown"),
    ],
)
def test_voice_gender(provider: str, voice: str, expected: str) -> None:
    assert tts.voice_gender(provider, voice) == expected


def test_online_tts_provider_options_include_confirmed_providers() -> None:
    assert {provider.id for provider in tts.available_tts_providers()} >= {
        "azure_tts",
        "google_tts",
        "amazon_polly",
        "elevenlabs_tts",
    }
    assert tts.is_online_tts_provider("azure")
    assert tts.tts_output_suffix("google_tts") == "mp3"


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


def test_removed_remote_vieneu_core_uses_local_fallbacks(monkeypatch) -> None:
    config = AppConfig(
        vieneu_tts_core="remote",
        vieneu_tts_mode="turbo",
        vieneu_tts_api_base="http://localhost:23333/v1",
        vieneu_tts_python="D:/missing/python.exe",
        vieneu_tts_runtime="subprocess",
    )
    monkeypatch.setattr(tts, "_runtime_has_cuda", lambda: True)

    candidates = tts._vieneu_fallback_configs(config)

    assert len(candidates) > 1
    assert all(
        tts.resolve_vieneu_effective_mode(
            candidate.vieneu_tts_core,
            candidate.vieneu_tts_mode,
            candidate.vieneu_tts_device,
        )
        != "remote"
        for candidate in candidates
    )


def test_vieneu_subprocess_requires_valid_python() -> None:
    provider = tts.VieNeuTTSProvider(AppConfig(vieneu_tts_python="D:/missing/python.exe"))

    assert not provider._should_use_subprocess(provider._config)


def test_removed_remote_vieneu_core_uses_turbo_voice_catalog() -> None:
    config = AppConfig(vieneu_tts_core="remote", tts_voice="Thục Đoan")

    assert [voice.id.split(" (", 1)[0] for voice in tts.available_voices("vieneu", config)] == [
        "Bích Ngọc",
        "Phạm Tuyên",
        "Thục Đoan",
        "Xuân Vĩnh",
    ]
    assert tts._compatible_vieneu_voice_id(config, "Thục Đoan").startswith("Thục Đoan")
    assert tts._compatible_vieneu_voice_id(config, "Xuân Vĩnh").startswith("Xuân Vĩnh")


def test_removed_remote_vieneu_core_rejects_empty_audio_as_local(monkeypatch, tmp_path) -> None:
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

    with pytest.raises(tts.TTSError, match="audio"):
        provider._synthesize_in_process(config, "xin chao", tmp_path / "out.wav", "Doan")


def test_removed_remote_vieneu_engine_kwargs_do_not_use_api_base() -> None:
    kwargs = tts._build_vieneu_engine_kwargs(
        mode=tts.normalize_vieneu_mode("remote"),
        api_base="http://localhost:23333/v1",
        model_name="pnnbao-ump/VieNeu-TTS",
        device="cuda",
        backend="native",
    )

    assert "api_base" not in kwargs
    assert "codec_repo" not in kwargs
    assert kwargs["backbone_repo"] == "pnnbao-ump/VieNeu-TTS"


def test_removed_remote_vieneu_subprocess_kwargs_do_not_use_api_base() -> None:
    kwargs = vieneu_tts_server._engine_kwargs(
        mode=tts.normalize_vieneu_mode("remote"),
        api_base="http://localhost:23333/v1",
        model_name="pnnbao-ump/VieNeu-TTS",
        device="cuda",
        backend="native",
        decoder_path="",
        encoder_path="",
        standard_codec_path="",
    )

    assert "api_base" not in kwargs
    assert "codec_repo" not in kwargs
    assert kwargs["backbone_repo"] == "pnnbao-ump/VieNeu-TTS"


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


def test_azure_online_tts_posts_ssml(monkeypatch, tmp_path) -> None:
    calls = []

    def fake_post(url, **kwargs):
        calls.append((url, kwargs))
        return _FakeResponse(content=b"azure-audio")

    monkeypatch.setattr(tts.requests, "post", fake_post)
    provider = tts.OnlineTTSProvider(
        AppConfig(tts_provider="azure_tts", tts_api_key="key", tts_api_region="eastus"),
        "azure_tts",
    )

    provider.synthesize("Xin chao", tmp_path / "out.mp3", voice="vi-VN-HoaiMyNeural")

    assert calls[0][0] == "https://eastus.tts.speech.microsoft.com/cognitiveservices/v1"
    assert calls[0][1]["headers"]["Ocp-Apim-Subscription-Key"] == "key"
    assert b"vi-VN-HoaiMyNeural" in calls[0][1]["data"]
    assert (tmp_path / "out.mp3").read_bytes() == b"azure-audio"


def test_google_online_tts_decodes_audio_content(monkeypatch, tmp_path) -> None:
    calls = []

    def fake_post(url, **kwargs):
        calls.append((url, kwargs))
        return _FakeResponse(payload={"audioContent": base64.b64encode(b"google-audio").decode("ascii")})

    monkeypatch.setattr(tts.requests, "post", fake_post)
    provider = tts.OnlineTTSProvider(AppConfig(tts_api_key="google-key"), "google_tts")

    provider.synthesize("Xin chao", tmp_path / "out.mp3", voice="vi-VN-Neural2-A")

    assert "key=google-key" in calls[0][0]
    assert calls[0][1]["json"]["voice"]["name"] == "vi-VN-Neural2-A"
    assert calls[0][1]["json"]["audioConfig"]["audioEncoding"] == "MP3"
    assert (tmp_path / "out.mp3").read_bytes() == b"google-audio"


def test_amazon_polly_online_tts_signs_request(monkeypatch, tmp_path) -> None:
    calls = []

    def fake_post(url, **kwargs):
        calls.append((url, kwargs))
        return _FakeResponse(content=b"polly-audio")

    monkeypatch.setattr(tts.requests, "post", fake_post)
    provider = tts.OnlineTTSProvider(
        AppConfig(
            tts_api_key="access",
            tts_api_secret="secret",
            tts_api_region="us-east-1",
            tts_model="standard",
        ),
        "amazon_polly",
    )

    provider.synthesize("Hello", tmp_path / "out.mp3", voice="Joanna")

    assert calls[0][0] == "https://polly.us-east-1.amazonaws.com/v1/speech"
    headers = calls[0][1]["headers"]
    assert headers["Authorization"].startswith("AWS4-HMAC-SHA256 Credential=access/")
    payload = json.loads(calls[0][1]["data"].decode("utf-8"))
    assert payload["VoiceId"] == "Joanna"
    assert payload["Engine"] == "standard"
    assert (tmp_path / "out.mp3").read_bytes() == b"polly-audio"


def test_elevenlabs_online_tts_posts_voice_and_model(monkeypatch, tmp_path) -> None:
    calls = []

    def fake_post(url, **kwargs):
        calls.append((url, kwargs))
        return _FakeResponse(content=b"eleven-audio")

    monkeypatch.setattr(tts.requests, "post", fake_post)
    provider = tts.OnlineTTSProvider(
        AppConfig(tts_api_key="eleven-key", tts_model="eleven_flash_v2_5"),
        "elevenlabs_tts",
    )

    provider.synthesize("Xin chao", tmp_path / "out.mp3", voice="voice/id")

    assert calls[0][0].endswith("/text-to-speech/voice%2Fid?output_format=mp3_44100_128")
    assert calls[0][1]["headers"]["xi-api-key"] == "eleven-key"
    assert calls[0][1]["json"]["model_id"] == "eleven_flash_v2_5"
    assert (tmp_path / "out.mp3").read_bytes() == b"eleven-audio"
