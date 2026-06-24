from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
import threading
import unicodedata
from pathlib import Path
from typing import Any

import requests

from ai_player.core.config import RUNTIME_DIR, AppConfig
from ai_player.core.redaction import compact_redacted_text, redact_secrets, redacted_json_text
from ai_player.core.value_utils import clean_message as _core_clean_message
from ai_player.core.value_utils import clean_text as _core_clean_text
from ai_player.core.value_utils import finite_float as _core_finite_float
from ai_player.core.value_utils import int_value as _core_int_value
from ai_player.services.tts_errors import friendly_tts_error
from ai_player.services.tts_voices import VoiceOption, available_tts_provider_options, available_vieneu_mode_options


class TTSError(RuntimeError):
    pass


class BaseTTSProvider:
    def synthesize(self, text: str, output_path: Path, voice: str | None = None) -> None:
        raise NotImplementedError

    def close(self) -> None:
        pass


class NoTTSProvider(BaseTTSProvider):
    def __init__(self, _config: AppConfig) -> None:
        pass

    def synthesize(self, text: str, output_path: Path, voice: str | None = None) -> None:
        raise TTSError("Không TTS không tạo audio mới.")


ONLINE_TTS_PROVIDERS = {"azure_tts", "google_tts", "amazon_polly"}
_TTS_CACHE_LOCK = threading.Lock()
_TTS_CACHE_KEY_LOCKS: dict[Path, threading.Lock] = {}
_TTS_CACHE_STATS = {"hits": 0, "misses": 0, "writes": 0}
_NON_SPEECH_TTS_TOKENS = {
    "a",
    "aa",
    "aaa",
    "ah",
    "aha",
    "aw",
    "e",
    "eh",
    "er",
    "err",
    "ha",
    "hah",
    "haha",
    "hahaha",
    "haiz",
    "hm",
    "hmm",
    "hmmm",
    "huh",
    "m",
    "mh",
    "mhm",
    "mm",
    "mmh",
    "mmm",
    "mmmm",
    "o",
    "oh",
    "oo",
    "ooh",
    "u",
    "uh",
    "uhh",
    "uhm",
    "um",
    "umm",
}


def normalize_tts_provider(value: object) -> str:
    raw = str(value or "").strip().lower().replace("-", "").replace("_", "").replace(" ", "")
    if raw in {"vieneu", "vieneutts", "vieneucore", "local", "offline"}:
        return "vieneu"
    if raw in {"edge", "edgetts", "edgecli"}:
        return "edge"
    if raw in {"azure", "azuretts", "microsofttts", "microsoftazuretts"}:
        return "azure_tts"
    if raw in {"google", "googletts", "googlecloudtts", "gcp", "gcptts"}:
        return "google_tts"
    if raw in {"amazon", "amazonpolly", "polly", "awspolly"}:
        return "amazon_polly"
    if raw in {"none", "off", "notts", "no_tts", "khongtts", "khong_tts"}:
        return "none"
    return "vieneu"


def available_tts_providers() -> list[VoiceOption]:
    return available_tts_provider_options()


def available_vieneu_modes() -> list[VoiceOption]:
    return available_vieneu_mode_options()


def tts_output_suffix(provider: object) -> str:
    return "wav" if normalize_tts_provider(provider) == "vieneu" else "mp3"


def is_online_tts_provider(provider: object) -> bool:
    return normalize_tts_provider(provider) in ONLINE_TTS_PROVIDERS


def clean_message(value: object) -> str:
    return redact_secrets(_core_clean_message(value))


def clean_text(value: object) -> str:
    return _core_clean_text(value)


def finite_float(value: object, *, default: float) -> float:
    return _core_finite_float(value, default=default)


def int_value(value: object, *, default: int, minimum: int) -> int:
    return _core_int_value(value, default=default, minimum=minimum)


def tts_api_base(config: AppConfig) -> str:
    return str(getattr(config, "tts_api_base", "") or "").strip().rstrip("/")


def tts_model(config: AppConfig, *, default: str) -> str:
    return str(getattr(config, "tts_model", "") or default).strip() or default


def tts_timeout(config: AppConfig) -> float:
    return max(1.0, finite_float(getattr(config, "tts_timeout_seconds", 30.0), default=30.0))


def required_tts_api_key(config: AppConfig, provider_name: str) -> str:
    api_key = str(getattr(config, "tts_api_key", "") or "").strip()
    if not api_key:
        raise TTSError(f"{provider_name} requires tts_api_key.")
    return api_key


def required_tts_api_secret(config: AppConfig, provider_name: str) -> str:
    api_secret = str(getattr(config, "tts_api_secret", "") or "").strip()
    if not api_secret:
        raise TTSError(f"{provider_name} requires tts_api_secret.")
    return api_secret


def voice_language_code(voice_id: str, *, default: str) -> str:
    parts = str(voice_id or "").strip().split("-")
    if len(parts) >= 2 and len(parts[0]) == 2 and len(parts[1]) == 2:
        return f"{parts[0]}-{parts[1]}"
    return default


def response_json(response: requests.Response, provider_name: str) -> dict[str, Any]:
    try:
        data = response.json()
    except Exception as exc:
        raise TTSError(f"{provider_name} returned invalid JSON.") from exc
    if not isinstance(data, dict):
        raise TTSError(f"{provider_name} returned an invalid JSON payload.")
    return data


def raise_for_tts_response(response: requests.Response, provider_name: str) -> None:
    if response.status_code < 400:
        return
    detail = ""
    try:
        data = response.json()
        friendly = friendly_tts_error(data)
        if friendly:
            raise TTSError(
                f"{provider_name} request failed with HTTP {response.status_code}: {compact_redacted_text(friendly)}"
            )
        detail = redacted_json_text(data)
    except TTSError:
        raise
    except Exception:
        detail = compact_redacted_text(getattr(response, "text", ""))
    raise TTSError(f"{provider_name} request failed with HTTP {response.status_code}: {detail}")


def write_tts_audio(output_path: Path, audio: bytes) -> None:
    if not audio:
        raise TTSError("TTS provider returned empty audio.")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(audio)


def remove_tts_output(path: Path) -> None:
    try:
        Path(path).unlink(missing_ok=True)
    except Exception:
        pass


def is_non_speech_tts_text(value: object) -> bool:
    text = clean_text(value)
    if not text:
        return True

    normalized = unicodedata.normalize("NFD", text.lower())
    normalized = "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")
    normalized = normalized.replace("\u0111", "d")
    tokens = re.findall(r"[a-z0-9]+", normalized)
    if not tokens:
        return True
    if len(tokens) > 4 or any(any(ch.isdigit() for ch in token) for token in tokens):
        return False
    return all(token in _NON_SPEECH_TTS_TOKENS or _looks_like_drawn_out_vocalization(token) for token in tokens)


def prepare_tts_text(value: object, target_language: object = "vi") -> str:
    text = clean_text(value)
    if not text:
        return ""
    if _target_uses_latin_script(target_language):
        text = _strip_non_latin_source_script(text)
    return "" if is_non_speech_tts_text(text) else text


def is_pathological_tts_duration(
    text: object,
    duration_seconds: float,
    target_duration_seconds: float | None = None,
) -> bool:
    duration = _finite_duration(duration_seconds)
    if duration <= 0:
        return False
    clean = prepare_tts_text(text)
    if not clean:
        return True

    normalized = unicodedata.normalize("NFD", clean.lower())
    normalized = "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")
    tokens = re.findall(r"[a-z0-9]+", normalized)
    letter_count = sum(1 for ch in normalized if ch.isalpha())
    token_count = len(tokens)
    target_duration = _finite_duration(target_duration_seconds)

    if letter_count <= 12:
        short_ceiling = max(3.0, target_duration * 2.5)
        return duration > short_ceiling

    estimated_natural_duration = max(1.0, token_count * 0.45 + letter_count * 0.065)
    ceiling = max(8.0, estimated_natural_duration * 2.8, target_duration * 2.8)
    return duration > ceiling


class CachedTTSProvider(BaseTTSProvider):
    def __init__(self, inner: BaseTTSProvider, config: AppConfig, provider: str) -> None:
        self._inner = inner
        self._config = config
        self._provider = normalize_tts_provider(provider)

    def synthesize(self, text: str, output_path: Path, voice: str | None = None) -> None:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if not _tts_cache_enabled():
            self._inner.synthesize(text, output_path, voice=voice)
            return

        cache_path = _tts_cache_path(self._provider, self._config, text, voice or self._config.tts_voice, output_path)
        cache_lock = _tts_cache_lock_for(cache_path)
        with cache_lock:
            if cache_path.exists() and cache_path.stat().st_size > 0:
                _record_tts_cache_stat("hits")
                shutil.copyfile(cache_path, output_path)
                return

            _record_tts_cache_stat("misses")
            self._inner.synthesize(text, output_path, voice=voice)
            if not output_path.exists() or output_path.stat().st_size <= 0:
                return

            cache_path.parent.mkdir(parents=True, exist_ok=True)
            temp_cache_path = cache_path.with_name(f"{cache_path.name}.tmp")
            if cache_path.exists() and cache_path.stat().st_size > 0:
                return
            shutil.copyfile(output_path, temp_cache_path)
            temp_cache_path.replace(cache_path)
            _record_tts_cache_stat("writes")

    def close(self) -> None:
        self._inner.close()


def _finite_duration(value: object) -> float:
    try:
        duration = float(value or 0.0)
    except (TypeError, ValueError, OverflowError):
        return 0.0
    if not math.isfinite(duration):
        return 0.0
    return max(0.0, duration)


def _looks_like_drawn_out_vocalization(token: str) -> bool:
    if len(token) < 2 or len(token) > 10:
        return False
    if len(set(token)) == 1 and token[0] in {"a", "e", "h", "m", "o", "u"}:
        return True
    return bool(re.fullmatch(r"h*m+h*", token) or re.fullmatch(r"[auo]+h*", token))


def _target_uses_latin_script(target_language: object) -> bool:
    normalized = str(target_language or "vi").strip().lower().split("-", 1)[0]
    return normalized in {"vi", "en", "de", "es", "fr", "id", "it", "pt", "tr"}


def _strip_non_latin_source_script(value: str) -> str:
    text = re.sub(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uac00-\ud7af]+", " ", value)
    text = re.sub(r"[\u0400-\u04ff\u0590-\u05ff\u0600-\u06ff\u0e00-\u0e7f]+", " ", text)
    text = re.sub(r"\s+([,.!?;:])", r"\1", text)
    return " ".join(text.split()).strip(" ,.;:!?")


def _tts_cache_enabled() -> bool:
    return str(os.getenv("AI_PLAYER_TTS_CACHE", "1")).strip().lower() not in {"0", "false", "no", "off"}


def tts_cache_stats() -> dict[str, int]:
    with _TTS_CACHE_LOCK:
        return {**_TTS_CACHE_STATS, "entries": _tts_cache_entry_count()}


def clear_tts_cache() -> None:
    cache_dir = RUNTIME_DIR / "tts-cache"
    with _TTS_CACHE_LOCK:
        if cache_dir.exists():
            for path in cache_dir.glob("*"):
                if not path.is_file():
                    continue
                try:
                    path.unlink()
                except OSError:
                    continue
        for key in _TTS_CACHE_STATS:
            _TTS_CACHE_STATS[key] = 0


def _record_tts_cache_stat(name: str) -> None:
    with _TTS_CACHE_LOCK:
        if name in _TTS_CACHE_STATS:
            _TTS_CACHE_STATS[name] += 1


def _tts_cache_entry_count() -> int:
    try:
        return sum(1 for path in (RUNTIME_DIR / "tts-cache").glob("*") if path.is_file())
    except OSError:
        return 0


def _tts_cache_lock_for(cache_path: Path) -> threading.Lock:
    normalized_path = cache_path.absolute()
    with _TTS_CACHE_LOCK:
        lock = _TTS_CACHE_KEY_LOCKS.get(normalized_path)
        if lock is None:
            lock = threading.Lock()
            _TTS_CACHE_KEY_LOCKS[normalized_path] = lock
        return lock


def _tts_cache_path(provider: str, config: AppConfig, text: str, voice: str, output_path: Path) -> Path:
    suffix = output_path.suffix.lower() or f".{tts_output_suffix(provider)}"
    payload = {
        "version": 1,
        "provider": normalize_tts_provider(provider),
        "text": _cache_text(text),
        "voice": str(voice or ""),
        "tts_api_base": str(getattr(config, "tts_api_base", "")),
        "tts_api_region": str(getattr(config, "tts_api_region", "")),
        "tts_model": str(getattr(config, "tts_model", "")),
        "tts_timeout": finite_float(getattr(config, "tts_timeout_seconds", 30.0), default=30.0),
        "vieneu_core": str(config.vieneu_tts_core),
        "vieneu_mode": str(config.vieneu_tts_mode),
        "vieneu_model": str(config.vieneu_tts_model_name),
        "vieneu_decoder": str(config.vieneu_tts_decoder_path),
        "vieneu_encoder": str(config.vieneu_tts_encoder_path),
        "vieneu_codec": str(config.vieneu_tts_standard_codec_path),
        "vieneu_device": str(config.vieneu_tts_device),
        "vieneu_backend": str(config.vieneu_tts_backend),
        "vieneu_temperature": finite_float(config.vieneu_tts_temperature, default=0.6),
        "vieneu_max_chars": int_value(config.vieneu_tts_max_chars_chunk, default=160, minimum=1),
    }
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=True).encode("utf-8")).hexdigest()
    return RUNTIME_DIR / "tts-cache" / f"{digest}{suffix}"


def _cache_text(value: object) -> str:
    text = clean_text(value)
    text = unicodedata.normalize("NFC", text)
    return "".join(ch for ch in text if unicodedata.category(ch) != "Cf")
