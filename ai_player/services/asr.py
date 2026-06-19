from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import requests

from ai_player.core.config import AppConfig

ASSEMBLYAI_API_BASE = "https://api.assemblyai.com"
SPEECHMATICS_API_BASE = "https://eu1.asr.api.speechmatics.com/v2"
ONLINE_ASR_PROVIDERS = {"assemblyai", "speechmatics"}


class OnlineAsrError(RuntimeError):
    pass


@dataclass(frozen=True)
class AsrSegment:
    text: str
    start: float
    end: float
    words: tuple[object, ...] = ()


@dataclass(frozen=True)
class AsrWord:
    word: str
    start: float
    end: float


def normalize_asr_provider(value: str) -> str:
    provider = str(value or "faster_whisper").strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "whisper": "faster_whisper",
        "fasterwhisper": "faster_whisper",
        "assembly_ai": "assemblyai",
        "assembly": "assemblyai",
    }
    return aliases.get(provider, provider or "faster_whisper")


def is_online_asr_provider(value: str) -> bool:
    return normalize_asr_provider(value) in ONLINE_ASR_PROVIDERS


def transcribe_online_asr(
    config: AppConfig,
    audio_path: Path,
    *,
    language: str | None = None,
    session: requests.Session | None = None,
) -> tuple[list[AsrSegment], object]:
    provider = normalize_asr_provider(config.asr_provider)
    if provider == "assemblyai":
        return AssemblyAiTranscriber(config, session=session).transcribe(audio_path, language=language)
    if provider == "speechmatics":
        return SpeechmaticsTranscriber(config, session=session).transcribe(audio_path, language=language)
    raise OnlineAsrError(f"Unsupported online ASR provider: {config.asr_provider}")


class AssemblyAiTranscriber:
    def __init__(self, config: AppConfig, *, session: requests.Session | None = None) -> None:
        self._config = config
        self._session = session or requests.Session()
        self._base_url = _normalized_base_url(config.asr_api_base, ASSEMBLYAI_API_BASE)
        self._timeout = _positive_timeout(config.asr_timeout_seconds)
        self._headers = {"authorization": _required_api_key(config)}

    def transcribe(self, audio_path: Path, *, language: str | None = None) -> tuple[list[AsrSegment], object]:
        upload_url = self._upload(audio_path)
        payload: dict[str, object] = {
            "audio_url": upload_url,
            "punctuate": True,
            "format_text": True,
        }
        if language:
            payload["language_code"] = language
        else:
            payload["language_detection"] = True
        response = self._request("POST", "/v2/transcript", json=payload)
        transcript_id = _json_text(response, "id")
        if not transcript_id:
            raise OnlineAsrError("AssemblyAI did not return a transcript id.")
        transcript = self._poll_transcript(transcript_id)
        words = [
            AsrWord(
                word=_text(item.get("text")),
                start=_millis_to_seconds(item.get("start")),
                end=_millis_to_seconds(item.get("end")),
            )
            for item in transcript.get("words") or []
            if isinstance(item, dict) and _text(item.get("text"))
        ]
        segments = _segments_from_words(words)
        if not segments:
            duration = _seconds_value(transcript.get("audio_duration"), default=0.0)
            segments = _single_segment(_text(transcript.get("text")), duration)
        detected_language = _text(transcript.get("language_code")) or language
        return segments, SimpleNamespace(language=detected_language)

    def _upload(self, audio_path: Path) -> str:
        with audio_path.open("rb") as audio_file:
            response = self._session.post(
                f"{self._base_url}/v2/upload",
                headers=self._headers,
                data=audio_file,
                timeout=min(120.0, self._timeout),
            )
        data = _response_json(response, "AssemblyAI upload failed")
        upload_url = _json_text(data, "upload_url")
        if not upload_url:
            raise OnlineAsrError("AssemblyAI did not return an upload URL.")
        return upload_url

    def _poll_transcript(self, transcript_id: str) -> dict[str, Any]:
        started = time.monotonic()
        while True:
            data = self._request("GET", f"/v2/transcript/{transcript_id}")
            status = _text(data.get("status")).lower()
            if status == "completed":
                return data
            if status == "error":
                raise OnlineAsrError(_text(data.get("error")) or "AssemblyAI transcription failed.")
            _raise_if_timeout(started, self._timeout, "AssemblyAI transcription timed out.")
            time.sleep(2.0)

    def _request(self, method: str, path: str, **kwargs: object) -> dict[str, Any]:
        response = self._session.request(
            method,
            f"{self._base_url}{path}",
            headers=self._headers,
            timeout=min(60.0, self._timeout),
            **kwargs,
        )
        return _response_json(response, "AssemblyAI request failed")


class SpeechmaticsTranscriber:
    def __init__(self, config: AppConfig, *, session: requests.Session | None = None) -> None:
        self._config = config
        self._session = session or requests.Session()
        self._base_url = _normalized_base_url(config.asr_api_base, SPEECHMATICS_API_BASE)
        self._timeout = _positive_timeout(config.asr_timeout_seconds)
        self._headers = {"Authorization": f"Bearer {_required_api_key(config)}"}

    def transcribe(self, audio_path: Path, *, language: str | None = None) -> tuple[list[AsrSegment], object]:
        job_id = self._create_job(audio_path, language=language)
        self._poll_job(job_id)
        transcript = self._request("GET", f"/jobs/{job_id}/transcript", params={"format": "json-v2"})
        words, detected_language = _speechmatics_words_and_language(transcript)
        segments = _segments_from_words(words)
        if not segments:
            segments = _single_segment(_speechmatics_text(transcript), 0.0)
        return segments, SimpleNamespace(language=detected_language or language)

    def _create_job(self, audio_path: Path, *, language: str | None) -> str:
        transcription_config: dict[str, object] = {"language": language or "multi", "enable_entities": False}
        if not language:
            transcription_config["model"] = "melia-1"
        config = {"type": "transcription", "transcription_config": transcription_config}
        with audio_path.open("rb") as audio_file:
            response = self._session.post(
                f"{self._base_url}/jobs",
                headers=self._headers,
                data={"config": _json_dumps(config)},
                files={"data_file": (audio_path.name, audio_file, "audio/wav")},
                timeout=min(120.0, self._timeout),
            )
        data = _response_json(response, "Speechmatics job creation failed")
        job_id = _json_text(data, "id") or _json_text(data.get("job"), "id")
        if not job_id:
            raise OnlineAsrError("Speechmatics did not return a job id.")
        return job_id

    def _poll_job(self, job_id: str) -> None:
        started = time.monotonic()
        while True:
            data = self._request("GET", f"/jobs/{job_id}")
            job = data.get("job") if isinstance(data.get("job"), dict) else data
            status = _text(job.get("status") if isinstance(job, dict) else "").lower()
            if status == "done":
                return
            if status in {"rejected", "failed", "deleted"}:
                raise OnlineAsrError(_speechmatics_error(job) or f"Speechmatics transcription {status}.")
            _raise_if_timeout(started, self._timeout, "Speechmatics transcription timed out.")
            time.sleep(2.0)

    def _request(self, method: str, path: str, **kwargs: object) -> dict[str, Any]:
        response = self._session.request(
            method,
            f"{self._base_url}{path}",
            headers=self._headers,
            timeout=min(60.0, self._timeout),
            **kwargs,
        )
        return _response_json(response, "Speechmatics request failed")


def _segments_from_words(words: list[AsrWord]) -> list[AsrSegment]:
    segments: list[AsrSegment] = []
    current: list[AsrWord] = []
    for word in words:
        if current and _should_break_segment(current, word):
            segments.append(_segment_from_words(current))
            current = []
        current.append(word)
    if current:
        segments.append(_segment_from_words(current))
    return segments


def _should_break_segment(current: list[AsrWord], word: AsrWord) -> bool:
    text = _join_word_text(current)
    gap = word.start - current[-1].end
    return gap > 1.0 or len(text) >= 160 or text.endswith((".", "?", "!", "。", "？", "！"))


def _segment_from_words(words: list[AsrWord]) -> AsrSegment:
    return AsrSegment(
        text=_join_word_text(words),
        start=max(0.0, words[0].start),
        end=max(words[-1].end, words[0].start + 0.25),
        words=tuple(words),
    )


def _join_word_text(words: list[AsrWord]) -> str:
    text = ""
    for word in words:
        token = word.word.strip()
        if not token:
            continue
        if not text or token in {".", ",", "?", "!", ":", ";", "%", ")", "]", "}"}:
            text += token
        elif token.startswith(("'", "-")):
            text += token
        else:
            text += f" {token}"
    return text.strip()


def _single_segment(text: str, duration: float) -> list[AsrSegment]:
    text = text.strip()
    if not text:
        return []
    return [AsrSegment(text=text, start=0.0, end=max(0.25, duration))]


def _speechmatics_words_and_language(data: dict[str, Any]) -> tuple[list[AsrWord], str | None]:
    words: list[AsrWord] = []
    language = None
    for item in data.get("results") or []:
        if not isinstance(item, dict):
            continue
        alternatives = item.get("alternatives") or []
        alternative = alternatives[0] if alternatives and isinstance(alternatives[0], dict) else {}
        content = _text(alternative.get("content"))
        if not content:
            continue
        language = language or _text(alternative.get("language")) or None
        start = _seconds_value(item.get("start_time"), default=words[-1].end if words else 0.0)
        end = _seconds_value(item.get("end_time"), default=start)
        if item.get("type") == "punctuation" and words:
            previous = words[-1]
            words[-1] = AsrWord(word=f"{previous.word}{content}", start=previous.start, end=max(previous.end, end))
            continue
        if item.get("type") == "word":
            words.append(AsrWord(word=content, start=start, end=max(end, start + 0.01)))
    return words, language


def _speechmatics_text(data: dict[str, Any]) -> str:
    if isinstance(data.get("metadata"), dict):
        text = _text(data["metadata"].get("transcript"))
        if text:
            return text
    words, _language = _speechmatics_words_and_language(data)
    return _join_word_text(words)


def _speechmatics_error(job: Any) -> str:
    if not isinstance(job, dict):
        return ""
    errors = job.get("errors")
    if isinstance(errors, list):
        messages = [_text(item.get("message")) for item in errors if isinstance(item, dict)]
        return "; ".join(message for message in messages if message)
    return _text(job.get("error"))


def _response_json(response: requests.Response, context: str) -> dict[str, Any]:
    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        raise OnlineAsrError(f"{context}: HTTP {response.status_code} {_response_text(response)}") from exc
    try:
        data = response.json()
    except ValueError as exc:
        raise OnlineAsrError(f"{context}: invalid JSON response") from exc
    if not isinstance(data, dict):
        raise OnlineAsrError(f"{context}: unexpected response")
    return data


def _response_text(response: requests.Response) -> str:
    return str(getattr(response, "text", "") or "").strip()[:500]


def _required_api_key(config: AppConfig) -> str:
    key = str(config.asr_api_key or "").strip()
    if not key:
        raise OnlineAsrError("Online ASR provider requires an API key.")
    return key


def _normalized_base_url(value: str, default: str) -> str:
    return str(value or default).strip().rstrip("/")


def _positive_timeout(value: object) -> float:
    timeout = _seconds_value(value, default=600.0)
    return max(30.0, timeout)


def _raise_if_timeout(started: float, timeout: float, message: str) -> None:
    if time.monotonic() - started > timeout:
        raise OnlineAsrError(message)


def _millis_to_seconds(value: object) -> float:
    return _seconds_value(value, default=0.0) / 1000.0


def _seconds_value(value: object, *, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError, OverflowError):
        return default


def _json_text(data: Any, key: str) -> str:
    if not isinstance(data, dict):
        return ""
    return _text(data.get(key))


def _text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace").strip()
    return str(value).strip()


def _json_dumps(value: object) -> str:
    import json

    return json.dumps(value, ensure_ascii=False)
