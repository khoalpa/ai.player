from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import requests

from ai_player.core.config import AppConfig
from ai_player.core.value_utils import clean_message as _core_clean_message
from ai_player.core.value_utils import clean_text as _core_clean_text
from ai_player.core.value_utils import finite_float as _core_finite_float
from ai_player.core.value_utils import int_value as _core_int_value
from ai_player.services.tts_errors import friendly_tts_error


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


def clean_message(value: object) -> str:
    return _core_clean_message(value)


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
            raise TTSError(f"{provider_name} request failed with HTTP {response.status_code}: {friendly}")
        detail = json.dumps(data, ensure_ascii=False)[:500]
    except TTSError:
        raise
    except Exception:
        detail = str(getattr(response, "text", "") or "")[:500]
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
