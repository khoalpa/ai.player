from __future__ import annotations

from types import SimpleNamespace

import pytest
import requests

from ai_player.core.config import AppConfig
from ai_player.services.asr import (
    OnlineAsrError,
    configured_language_hints,
    effective_asr_provider,
    is_online_asr_provider,
    transcribe_asr,
    transcribe_online_asr,
)


class FakeResponse:
    def __init__(self, payload: dict[str, object], status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code
        self.text = str(payload)

    def json(self) -> dict[str, object]:
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(response=self)


class AssemblyAiSession:
    def post(self, url: str, **_kwargs):
        assert url.endswith("/v2/upload")
        return FakeResponse({"upload_url": "https://upload.example/audio.wav"})

    def request(self, method: str, url: str, **kwargs):
        if method == "POST" and url.endswith("/v2/transcript"):
            assert kwargs["json"]["language_code"] == "en"
            return FakeResponse({"id": "transcript-id"})
        if method == "GET" and url.endswith("/v2/transcript/transcript-id"):
            return FakeResponse(
                {
                    "status": "completed",
                    "language_code": "en",
                    "words": [
                        {"text": "Hello", "start": 0, "end": 250, "confidence": 0.9, "speaker": "A"},
                        {"text": "world.", "start": 300, "end": 700, "confidence": 0.7, "speaker": "A"},
                    ],
                }
            )
        raise AssertionError(f"unexpected request: {method} {url}")


class SpeechmaticsSession:
    def __init__(self) -> None:
        self.job_config = ""

    def post(self, url: str, **kwargs):
        assert url.endswith("/jobs")
        assert "Bearer speech-key" in kwargs["headers"]["Authorization"]
        self.job_config = kwargs["data"]["config"]
        assert '"language": "multi"' in self.job_config
        return FakeResponse({"job": {"id": "job-id"}})

    def request(self, method: str, url: str, **_kwargs):
        if method == "GET" and url.endswith("/jobs/job-id"):
            return FakeResponse({"job": {"status": "done"}})
        if method == "GET" and url.endswith("/jobs/job-id/transcript"):
            return FakeResponse(
                {
                    "results": [
                        {
                            "type": "word",
                            "start_time": 0.0,
                            "end_time": 0.2,
                            "alternatives": [{"content": "Xin", "language": "vi", "confidence": 0.8}],
                        },
                        {
                            "type": "word",
                            "start_time": 0.3,
                            "end_time": 0.6,
                            "alternatives": [{"content": "chao", "language": "vi", "confidence": 0.6}],
                        },
                        {
                            "type": "punctuation",
                            "start_time": 0.6,
                            "end_time": 0.6,
                            "alternatives": [{"content": ".", "language": "vi"}],
                        },
                    ]
                }
            )
        raise AssertionError(f"unexpected request: {method} {url}")


def test_assemblyai_transcribe_returns_whisper_like_segments(tmp_path) -> None:
    audio = tmp_path / "sample.wav"
    audio.write_bytes(b"wav")
    config = AppConfig(asr_provider="assemblyai", asr_api_key="assembly-key")

    segments, info = transcribe_online_asr(config, audio, language="en", session=AssemblyAiSession())

    assert is_online_asr_provider("assembly_ai")
    assert info.language == "en"
    assert info.provider == "assemblyai"
    assert [(segment.text, segment.start, segment.end) for segment in segments] == [("Hello world.", 0.0, 0.7)]
    assert segments[0].provider == "assemblyai"
    assert segments[0].language == "en"
    assert segments[0].speaker == "A"
    assert segments[0].confidence == pytest.approx(0.8)
    assert segments[0].words[0].confidence == pytest.approx(0.9)


def test_speechmatics_transcribe_returns_segments_and_detected_language(tmp_path) -> None:
    audio = tmp_path / "sample.wav"
    audio.write_bytes(b"wav")
    config = AppConfig(asr_provider="speechmatics", asr_api_key="speech-key")

    session = SpeechmaticsSession()

    segments, info = transcribe_online_asr(config, audio, session=session)

    assert info.language == "vi"
    assert info.provider == "speechmatics"
    assert [(segment.text, segment.start, segment.end) for segment in segments] == [("Xin chao.", 0.0, 0.6)]
    assert segments[0].provider == "speechmatics"
    assert segments[0].language == "vi"
    assert segments[0].confidence == pytest.approx(0.7)
    assert [word.language for word in segments[0].words] == ["vi", "vi"]
    assert '"model": "melia-1"' in session.job_config


def test_speechmatics_transcribe_sends_language_hints_when_auto_language(tmp_path) -> None:
    audio = tmp_path / "sample.wav"
    audio.write_bytes(b"wav")
    session = SpeechmaticsSession()
    config = AppConfig(
        asr_provider="speechmatics",
        asr_api_key="speech-key",
        asr_language_hints="vi, en;vi",
    )

    transcribe_online_asr(config, audio, session=session)

    assert configured_language_hints(config) == ("vi", "en")
    assert '"language_hints": ["vi", "en"]' in session.job_config


def test_auto_asr_provider_routes_by_key_language_and_endpoint() -> None:
    assert effective_asr_provider(AppConfig(asr_provider="auto", asr_api_key=""), language=None) == "faster_whisper"
    assert effective_asr_provider(AppConfig(asr_provider="auto", asr_api_key="key"), language=None) == "speechmatics"
    assert effective_asr_provider(AppConfig(asr_provider="auto", asr_api_key="key"), language="en") == "assemblyai"
    assert (
        effective_asr_provider(
            AppConfig(asr_provider="auto", asr_api_key="key", asr_api_base="https://asr.api.speechmatics.com/v2"),
            language="en",
        )
        == "speechmatics"
    )


def test_online_asr_falls_back_to_local_transcriber(tmp_path) -> None:
    class FailingSession:
        def post(self, *_args, **_kwargs):
            raise OnlineAsrError("network down")

    audio = tmp_path / "sample.wav"
    audio.write_bytes(b"wav")
    local_calls = []

    segments, info = transcribe_asr(
        AppConfig(asr_provider="speechmatics", asr_api_key="speech-key"),
        audio,
        language=None,
        session=FailingSession(),
        local_transcriber=lambda: local_calls.append(True) or ([], SimpleNamespace(language="local")),
    )

    assert local_calls == [True]
    assert segments == []
    assert info.language == "local"


def test_online_asr_can_disable_local_fallback(tmp_path) -> None:
    class FailingSession:
        def post(self, *_args, **_kwargs):
            raise OnlineAsrError("network down")

    audio = tmp_path / "sample.wav"
    audio.write_bytes(b"wav")

    with pytest.raises(OnlineAsrError, match="network down"):
        transcribe_asr(
            AppConfig(asr_provider="speechmatics", asr_api_key="speech-key", asr_fallback_to_whisper=False),
            audio,
            language=None,
            session=FailingSession(),
            local_transcriber=lambda: pytest.fail("fallback should be disabled"),
        )
