from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import requests

from ai_player.configuration import RUNTIME_DIR, AppConfig
from ai_player.core.redaction import compact_redacted_text

ASSEMBLYAI_API_BASE = "https://api.assemblyai.com"
SPEECHMATICS_API_BASE = "https://asr.api.speechmatics.com/v2"
ONLINE_ASR_PROVIDERS = {"assemblyai", "speechmatics"}
LOCAL_ASR_PROVIDER = "faster_whisper"
AUTO_ASR_PROVIDER = "auto"


@dataclass(frozen=True)
class AsrProviderCapabilities:
    provider: str
    online: bool
    word_timestamps: bool
    language_detection: bool
    multilingual: bool
    diarization: bool
    custom_vocabulary: bool
    realtime: bool
    estimated_cost_per_hour: float | None = None


ASR_PROVIDER_CAPABILITIES: dict[str, AsrProviderCapabilities] = {
    LOCAL_ASR_PROVIDER: AsrProviderCapabilities(
        provider=LOCAL_ASR_PROVIDER,
        online=False,
        word_timestamps=True,
        language_detection=True,
        multilingual=True,
        diarization=False,
        custom_vocabulary=False,
        realtime=False,
    ),
    "assemblyai": AsrProviderCapabilities(
        provider="assemblyai",
        online=True,
        word_timestamps=True,
        language_detection=True,
        multilingual=True,
        diarization=True,
        custom_vocabulary=True,
        realtime=True,
        estimated_cost_per_hour=0.15,
    ),
    "speechmatics": AsrProviderCapabilities(
        provider="speechmatics",
        online=True,
        word_timestamps=True,
        language_detection=True,
        multilingual=True,
        diarization=True,
        custom_vocabulary=True,
        realtime=True,
        estimated_cost_per_hour=0.129,
    ),
}


class OnlineAsrError(RuntimeError):
    pass


@dataclass(frozen=True)
class AsrSegment:
    text: str
    start: float
    end: float
    words: tuple[object, ...] = ()
    provider: str = ""
    language: str | None = None
    confidence: float | None = None
    speaker: str | None = None


@dataclass(frozen=True)
class AsrWord:
    word: str
    start: float
    end: float
    confidence: float | None = None
    language: str | None = None
    speaker: str | None = None
    provider: str = ""

    @property
    def probability(self) -> float | None:
        return self.confidence


def normalize_asr_provider(value: str) -> str:
    provider = str(value or LOCAL_ASR_PROVIDER).strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "whisper": LOCAL_ASR_PROVIDER,
        "fasterwhisper": LOCAL_ASR_PROVIDER,
        "assembly_ai": "assemblyai",
        "assembly": "assemblyai",
        "speech": "speechmatics",
        "speechmatic": "speechmatics",
        "automatic": AUTO_ASR_PROVIDER,
    }
    return aliases.get(provider, provider or LOCAL_ASR_PROVIDER)


def is_online_asr_provider(value: str) -> bool:
    return normalize_asr_provider(value) in ONLINE_ASR_PROVIDERS


def is_auto_asr_provider(value: str) -> bool:
    return normalize_asr_provider(value) == AUTO_ASR_PROVIDER


def asr_provider_capabilities(value: str) -> AsrProviderCapabilities:
    provider = normalize_asr_provider(value)
    if provider == AUTO_ASR_PROVIDER:
        provider = LOCAL_ASR_PROVIDER
    return ASR_PROVIDER_CAPABILITIES.get(provider, ASR_PROVIDER_CAPABILITIES[LOCAL_ASR_PROVIDER])


def configured_language_hints(config: AppConfig) -> tuple[str, ...]:
    raw = str(getattr(config, "asr_language_hints", "") or "").replace(";", ",")
    hints = []
    for item in raw.split(","):
        hint = item.strip().lower().replace("_", "-")
        if hint and hint != "auto":
            hints.append(hint)
    return tuple(dict.fromkeys(hints))


def effective_asr_provider(config: AppConfig, *, language: str | None = None) -> str:
    provider = normalize_asr_provider(config.asr_provider)
    if provider != AUTO_ASR_PROVIDER:
        return provider
    if not str(config.asr_api_key or "").strip():
        return LOCAL_ASR_PROVIDER
    api_base = str(config.asr_api_base or "").strip().lower()
    if "assemblyai" in api_base:
        return "assemblyai"
    if "speechmatics" in api_base:
        return "speechmatics"
    if language is None or configured_language_hints(config):
        return "speechmatics"
    return "assemblyai"


def should_use_online_asr(config: AppConfig, *, language: str | None = None) -> bool:
    return effective_asr_provider(config, language=language) in ONLINE_ASR_PROVIDERS


def transcribe_online_asr(
    config: AppConfig,
    audio_path: Path,
    *,
    language: str | None = None,
    session: requests.Session | None = None,
    provider: str | None = None,
) -> tuple[list[AsrSegment], object]:
    provider = normalize_asr_provider(provider or config.asr_provider)
    if provider == AUTO_ASR_PROVIDER:
        provider = effective_asr_provider(config, language=language)
    if provider == "assemblyai":
        return AssemblyAiTranscriber(_provider_config(config, provider), session=session).transcribe(
            audio_path,
            language=language,
        )
    if provider == "speechmatics":
        return SpeechmaticsTranscriber(_provider_config(config, provider), session=session).transcribe(
            audio_path,
            language=language,
        )
    raise OnlineAsrError(f"Unsupported online ASR provider: {config.asr_provider}")


def transcribe_asr(
    config: AppConfig,
    audio_path: Path,
    *,
    language: str | None,
    local_transcriber: Callable[[], tuple[list[object], object]],
    session: requests.Session | None = None,
    cache_details: dict[str, object] | None = None,
) -> tuple[list[object], object]:
    provider = effective_asr_provider(config, language=language)
    cached = _read_asr_cache(config, audio_path, provider=provider, language=language, details=cache_details)
    if cached is not None:
        return cached

    if provider not in ONLINE_ASR_PROVIDERS:
        result = local_transcriber()
        _write_asr_cache(config, audio_path, result, provider=provider, language=language, details=cache_details)
        return result
    try:
        result = transcribe_online_asr(config, audio_path, language=language, session=session, provider=provider)
        _write_asr_cache(config, audio_path, result, provider=provider, language=language, details=cache_details)
        return result
    except Exception:
        if bool(getattr(config, "asr_fallback_to_whisper", True)):
            fallback_provider = LOCAL_ASR_PROVIDER
            cached = _read_asr_cache(
                config,
                audio_path,
                provider=fallback_provider,
                language=language,
                details=cache_details,
            )
            if cached is not None:
                return cached
            result = local_transcriber()
            _write_asr_cache(
                config,
                audio_path,
                result,
                provider=fallback_provider,
                language=language,
                details=cache_details,
            )
            return result
        raise


_ASR_CACHE_LOCK = threading.Lock()
_ASR_CACHE_SCHEMA_VERSION = 1
_ASR_CACHE_STATS = {"hits": 0, "misses": 0, "writes": 0}


def clear_asr_transcript_cache() -> None:
    cache_dir = _asr_cache_dir()
    with _ASR_CACHE_LOCK:
        if cache_dir.exists():
            for path in cache_dir.glob("*.json"):
                try:
                    path.unlink()
                except OSError:
                    continue
        for key in _ASR_CACHE_STATS:
            _ASR_CACHE_STATS[key] = 0


def asr_transcript_cache_stats() -> dict[str, int]:
    with _ASR_CACHE_LOCK:
        return {**_ASR_CACHE_STATS, "entries": _asr_cache_entry_count()}


def _read_asr_cache(
    config: AppConfig,
    audio_path: Path,
    *,
    provider: str,
    language: str | None,
    details: dict[str, object] | None,
) -> tuple[list[object], object] | None:
    if details is None or not _asr_cache_enabled():
        return None
    cache_path = _asr_cache_path(config, audio_path, provider=provider, language=language, details=details)
    if cache_path is None:
        return None
    try:
        with _ASR_CACHE_LOCK:
            data = json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        with _ASR_CACHE_LOCK:
            _ASR_CACHE_STATS["misses"] += 1
        return None
    if data.get("schema_version") != _ASR_CACHE_SCHEMA_VERSION:
        with _ASR_CACHE_LOCK:
            _ASR_CACHE_STATS["misses"] += 1
        return None
    segments = [_segment_from_cache(item) for item in data.get("segments") or [] if isinstance(item, dict)]
    info_data = data.get("info") if isinstance(data.get("info"), dict) else {}
    with _ASR_CACHE_LOCK:
        _ASR_CACHE_STATS["hits"] += 1
    return segments, SimpleNamespace(
        language=_text(info_data.get("language")),
        language_probability=_optional_seconds_value(info_data.get("language_probability")),
        provider=_text(info_data.get("provider") or provider),
        from_cache=True,
    )


def _write_asr_cache(
    config: AppConfig,
    audio_path: Path,
    result: tuple[list[object], object],
    *,
    provider: str,
    language: str | None,
    details: dict[str, object] | None,
) -> None:
    if details is None or not _asr_cache_enabled():
        return
    segments, info = result
    payload = {
        "schema_version": _ASR_CACHE_SCHEMA_VERSION,
        "provider": provider,
        "language": language,
        "segments": [_segment_to_cache(segment) for segment in segments],
        "info": {
            "language": _text(getattr(info, "language", language)),
            "language_probability": _optional_seconds_value(getattr(info, "language_probability", None)),
            "provider": _text(getattr(info, "provider", provider)),
        },
    }
    cache_path = _asr_cache_path(config, audio_path, provider=provider, language=language, details=details)
    if cache_path is None:
        return
    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = cache_path.with_suffix(".tmp")
        with _ASR_CACHE_LOCK:
            temp_path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True), encoding="utf-8")
            temp_path.replace(cache_path)
            _ASR_CACHE_STATS["writes"] += 1
    except OSError:
        return


def _asr_cache_enabled() -> bool:
    return str(os.getenv("AI_PLAYER_ASR_CACHE", "1")).strip().lower() not in {"0", "false", "no", "off"}


def _asr_cache_dir() -> Path:
    return RUNTIME_DIR / "asr-cache"


def _asr_cache_entry_count() -> int:
    try:
        return sum(1 for _path in _asr_cache_dir().glob("*.json"))
    except OSError:
        return 0


def _asr_cache_path(
    config: AppConfig,
    audio_path: Path,
    *,
    provider: str,
    language: str | None,
    details: dict[str, object] | None,
) -> Path | None:
    try:
        audio_hash = _file_digest(audio_path)
    except OSError:
        return None
    fingerprint = {
        "schema_version": _ASR_CACHE_SCHEMA_VERSION,
        "audio_hash": audio_hash,
        "provider": provider,
        "language": language or "",
        "details": details or {},
        "config": {
            "asr_provider": normalize_asr_provider(config.asr_provider),
            "asr_api_base": _normalized_base_url(config.asr_api_base, ""),
            "asr_language_hints": configured_language_hints(config),
            "whisper_model": str(config.whisper_model),
            "whisper_offline": bool(config.whisper_offline),
            "whisper_device": str(config.whisper_device),
            "whisper_compute_type": str(config.whisper_compute_type),
            "whisper_beam_size": int(config.whisper_beam_size),
            "whisper_vad_filter": bool(config.whisper_vad_filter),
        },
    }
    encoded = json.dumps(fingerprint, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    return _asr_cache_dir() / f"{hashlib.sha256(encoded).hexdigest()}.json"


def _file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _segment_to_cache(segment: object) -> dict[str, object]:
    return {
        "text": _text(getattr(segment, "text", "")),
        "start": _seconds_value(getattr(segment, "start", 0.0), default=0.0),
        "end": _seconds_value(getattr(segment, "end", 0.0), default=0.0),
        "provider": _text(getattr(segment, "provider", "")),
        "language": _text(getattr(segment, "language", "")),
        "confidence": _optional_seconds_value(getattr(segment, "confidence", None)),
        "speaker": _text(getattr(segment, "speaker", "")),
        "words": [_word_to_cache(word) for word in getattr(segment, "words", ()) or ()],
    }


def _word_to_cache(word: object) -> dict[str, object]:
    return {
        "word": _text(getattr(word, "word", getattr(word, "text", ""))),
        "start": _seconds_value(getattr(word, "start", 0.0), default=0.0),
        "end": _seconds_value(getattr(word, "end", 0.0), default=0.0),
        "confidence": _optional_seconds_value(
            getattr(word, "confidence", getattr(word, "probability", None)),
        ),
        "language": _text(getattr(word, "language", "")),
        "speaker": _text(getattr(word, "speaker", "")),
        "provider": _text(getattr(word, "provider", "")),
    }


def _segment_from_cache(data: dict[str, object]) -> AsrSegment:
    words = tuple(_word_from_cache(item) for item in data.get("words") or [] if isinstance(item, dict))
    return AsrSegment(
        text=_text(data.get("text")),
        start=_seconds_value(data.get("start"), default=0.0),
        end=_seconds_value(data.get("end"), default=0.0),
        words=words,
        provider=_text(data.get("provider")),
        language=_text(data.get("language")) or None,
        confidence=_optional_seconds_value(data.get("confidence")),
        speaker=_text(data.get("speaker")) or None,
    )


def _word_from_cache(data: dict[str, object]) -> AsrWord:
    return AsrWord(
        word=_text(data.get("word")),
        start=_seconds_value(data.get("start"), default=0.0),
        end=_seconds_value(data.get("end"), default=0.0),
        confidence=_optional_seconds_value(data.get("confidence")),
        language=_text(data.get("language")) or None,
        speaker=_text(data.get("speaker")) or None,
        provider=_text(data.get("provider")),
    )


def _provider_config(config: AppConfig, provider: str) -> AppConfig:
    return replace(config, asr_provider=provider)


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
                confidence=_optional_seconds_value(item.get("confidence")),
                language=_text(item.get("language") or transcript.get("language_code")) or None,
                speaker=_speaker_text(item),
                provider="assemblyai",
            )
            for item in transcript.get("words") or []
            if isinstance(item, dict) and _text(item.get("text"))
        ]
        detected_language = _text(transcript.get("language_code")) or language
        segments = _segments_from_words(words, provider="assemblyai", language=detected_language)
        if not segments:
            duration = _seconds_value(transcript.get("audio_duration"), default=0.0)
            segments = _single_segment(
                _text(transcript.get("text")),
                duration,
                provider="assemblyai",
                language=detected_language,
            )
        return segments, SimpleNamespace(language=detected_language, provider="assemblyai")

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
        segments = _segments_from_words(words, provider="speechmatics", language=language)
        if not segments:
            segments = _single_segment(
                _speechmatics_text(transcript),
                0.0,
                provider="speechmatics",
                language=detected_language or language,
            )
        return segments, SimpleNamespace(language=detected_language or language, provider="speechmatics")

    def _create_job(self, audio_path: Path, *, language: str | None) -> str:
        transcription_config: dict[str, object] = {"language": language or "multi", "enable_entities": False}
        if not language:
            transcription_config["model"] = "melia-1"
        hints = configured_language_hints(self._config)
        if hints and not language:
            transcription_config["language_hints"] = list(hints)
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


def _segments_from_words(
    words: list[AsrWord],
    *,
    provider: str = "",
    language: str | None = None,
) -> list[AsrSegment]:
    segments: list[AsrSegment] = []
    current: list[AsrWord] = []
    for word in words:
        if current and _should_break_segment(current, word):
            segments.append(_segment_from_words(current, provider=provider, language=language))
            current = []
        current.append(word)
    if current:
        segments.append(_segment_from_words(current, provider=provider, language=language))
    return segments


def _should_break_segment(current: list[AsrWord], word: AsrWord) -> bool:
    text = _join_word_text(current)
    gap = word.start - current[-1].end
    return gap > 1.0 or len(text) >= 160 or text.endswith((".", "?", "!", "。", "？", "！"))


def _segment_from_words(words: list[AsrWord], *, provider: str = "", language: str | None = None) -> AsrSegment:
    confidence_values = [word.confidence for word in words if word.confidence is not None]
    return AsrSegment(
        text=_join_word_text(words),
        start=max(0.0, words[0].start),
        end=max(words[-1].end, words[0].start + 0.25),
        words=tuple(words),
        provider=provider,
        language=language or _dominant_word_value(words, "language"),
        confidence=(sum(confidence_values) / len(confidence_values)) if confidence_values else None,
        speaker=_dominant_word_value(words, "speaker"),
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


def _single_segment(
    text: str,
    duration: float,
    *,
    provider: str = "",
    language: str | None = None,
) -> list[AsrSegment]:
    text = text.strip()
    if not text:
        return []
    return [AsrSegment(text=text, start=0.0, end=max(0.25, duration), provider=provider, language=language)]


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
            words[-1] = replace(previous, word=f"{previous.word}{content}", end=max(previous.end, end))
            continue
        if item.get("type") == "word":
            words.append(
                AsrWord(
                    word=content,
                    start=start,
                    end=max(end, start + 0.01),
                    confidence=_optional_seconds_value(alternative.get("confidence")),
                    language=_text(alternative.get("language")) or None,
                    speaker=_speaker_text(item) or _speaker_text(alternative),
                    provider="speechmatics",
                )
            )
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
        return compact_redacted_text("; ".join(message for message in messages if message))
    return compact_redacted_text(_text(job.get("error")))


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
    return compact_redacted_text(getattr(response, "text", ""))


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


def _optional_seconds_value(value: object) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number


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


def _speaker_text(data: Any) -> str | None:
    if not isinstance(data, dict):
        return None
    for key in ("speaker", "speaker_label", "speaker_id"):
        value = _text(data.get(key))
        if value:
            return value
    return None


def _dominant_word_value(words: list[AsrWord], field_name: str) -> str | None:
    counts: dict[str, int] = {}
    for word in words:
        value = _text(getattr(word, field_name, None))
        if value:
            counts[value] = counts.get(value, 0) + 1
    if not counts:
        return None
    return max(counts.items(), key=lambda item: item[1])[0]


def _json_dumps(value: object) -> str:
    import json

    return json.dumps(value, ensure_ascii=False)
