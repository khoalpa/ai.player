from __future__ import annotations

import requests

from ai_player.core.config import AppConfig
from ai_player.services.asr import is_online_asr_provider, transcribe_online_asr


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
                        {"text": "Hello", "start": 0, "end": 250},
                        {"text": "world.", "start": 300, "end": 700},
                    ],
                }
            )
        raise AssertionError(f"unexpected request: {method} {url}")


class SpeechmaticsSession:
    def post(self, url: str, **kwargs):
        assert url.endswith("/jobs")
        assert "Bearer speech-key" in kwargs["headers"]["Authorization"]
        assert '"language": "multi"' in kwargs["data"]["config"]
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
                            "alternatives": [{"content": "Xin", "language": "vi"}],
                        },
                        {
                            "type": "word",
                            "start_time": 0.3,
                            "end_time": 0.6,
                            "alternatives": [{"content": "chao", "language": "vi"}],
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
    assert [(segment.text, segment.start, segment.end) for segment in segments] == [("Hello world.", 0.0, 0.7)]


def test_speechmatics_transcribe_returns_segments_and_detected_language(tmp_path) -> None:
    audio = tmp_path / "sample.wav"
    audio.write_bytes(b"wav")
    config = AppConfig(asr_provider="speechmatics", asr_api_key="speech-key")

    segments, info = transcribe_online_asr(config, audio, session=SpeechmaticsSession())

    assert info.language == "vi"
    assert [(segment.text, segment.start, segment.end) for segment in segments] == [("Xin chao.", 0.0, 0.6)]
