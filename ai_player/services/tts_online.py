from __future__ import annotations

import base64
import datetime as _datetime
import hashlib
import hmac
import html
import json
import time
from pathlib import Path
from urllib.parse import quote, urlparse

import requests

from ai_player.core.config import AppConfig
from ai_player.services.tts_base import (
    BaseTTSProvider,
    TTSError,
    clean_message,
    clean_text,
    normalize_tts_provider,
    raise_for_tts_response,
    remove_tts_output,
    required_tts_api_key,
    required_tts_api_secret,
    response_json,
    tts_api_base,
    tts_model,
    tts_timeout,
    voice_language_code,
    write_tts_audio,
)
from ai_player.services.tts_voices import AMAZON_POLLY_VOICES, AZURE_TTS_VOICES, GOOGLE_TTS_VOICES, voice_gender

AZURE_TTS_DEFAULT_REGION = "eastus"
GOOGLE_TTS_API_BASE = "https://texttospeech.googleapis.com/v1/text:synthesize"


def compatible_online_voice_id(provider: str, voice_id: object) -> str:
    raw = str(voice_id or "").strip()
    normalized_provider = normalize_tts_provider(provider)
    voices = {
        "azure_tts": AZURE_TTS_VOICES,
        "google_tts": GOOGLE_TTS_VOICES,
        "amazon_polly": AMAZON_POLLY_VOICES,
    }.get(normalized_provider, AZURE_TTS_VOICES)
    available_ids = {voice.id for voice in voices}
    if raw in available_ids:
        return raw
    if raw and normalized_provider == "amazon_polly":
        return raw
    if raw.startswith(("vi-VN-", "en-US-", "en-GB-")) and normalized_provider in {"azure_tts", "google_tts"}:
        return raw
    gender = voice_gender(provider, raw)
    if gender == "male":
        return preferred_online_voice_id(provider, "male")
    return preferred_online_voice_id(provider, "female")


def preferred_online_voice_id(provider: str, gender: str) -> str:
    normalized_provider = normalize_tts_provider(provider)
    preferred = {
        "azure_tts": {"female": "vi-VN-HoaiMyNeural", "male": "vi-VN-NamMinhNeural"},
        "google_tts": {"female": "vi-VN-Neural2-A", "male": "vi-VN-Neural2-D"},
        "amazon_polly": {"female": "Joanna", "male": "Matthew"},
    }
    return preferred.get(normalized_provider, preferred["azure_tts"]).get(gender, preferred["azure_tts"]["female"])


class OnlineTTSProvider(BaseTTSProvider):
    def __init__(self, config: AppConfig, provider: str) -> None:
        self._config = config
        self._provider = normalize_tts_provider(provider)

    def synthesize(self, text: str, output_path: Path, voice: str | None = None) -> None:
        clean = clean_text(text)
        if not clean:
            raise TTSError(f"{self._provider} cannot read empty text.")
        output_path = Path(output_path)
        voice_id = compatible_online_voice_id(self._provider, voice or self._config.tts_voice)
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                audio = self._request_audio(clean, voice_id)
                write_tts_audio(output_path, audio)
                if output_path.exists() and output_path.stat().st_size > 0:
                    return
                raise TTSError(f"{self._provider} returned an empty audio file.")
            except Exception as exc:
                last_error = exc
                remove_tts_output(output_path)
                if attempt >= 2:
                    break
                time.sleep(0.4 * (attempt + 1))
        detail = clean_message(last_error) if last_error is not None else "unknown error"
        raise TTSError(f"{self._provider} failed for voice '{voice_id}': {detail}") from last_error

    def _request_audio(self, text: str, voice_id: str) -> bytes:
        if self._provider == "azure_tts":
            return self._request_azure(text, voice_id)
        if self._provider == "google_tts":
            return self._request_google(text, voice_id)
        if self._provider == "amazon_polly":
            return self._request_amazon_polly(text, voice_id)
        raise TTSError(f"Unsupported online TTS provider: {self._provider}")

    def _request_azure(self, text: str, voice_id: str) -> bytes:
        api_key = required_tts_api_key(self._config, "Azure TTS")
        region = str(getattr(self._config, "tts_api_region", "") or AZURE_TTS_DEFAULT_REGION).strip()
        api_base = tts_api_base(self._config)
        url = api_base or f"https://{region}.tts.speech.microsoft.com/cognitiveservices/v1"
        locale = voice_language_code(voice_id, default="vi-VN")
        escaped_text = html.escape(text, quote=False)
        escaped_voice = html.escape(voice_id, quote=True)
        ssml = (
            f"<speak version='1.0' xml:lang='{locale}' "
            f"xmlns='http://www.w3.org/2001/10/synthesis'>"
            f"<voice xml:lang='{locale}' name='{escaped_voice}'>{escaped_text}</voice>"
            "</speak>"
        )
        response = requests.post(
            url,
            data=ssml.encode("utf-8"),
            headers={
                "Ocp-Apim-Subscription-Key": api_key,
                "Content-Type": "application/ssml+xml",
                "X-Microsoft-OutputFormat": "audio-24khz-48kbitrate-mono-mp3",
                "User-Agent": "ai-player",
            },
            timeout=tts_timeout(self._config),
        )
        raise_for_tts_response(response, "Azure TTS")
        return response.content

    def _request_google(self, text: str, voice_id: str) -> bytes:
        api_key = required_tts_api_key(self._config, "Google Cloud TTS")
        url = _google_tts_url(tts_api_base(self._config) or GOOGLE_TTS_API_BASE, api_key)
        payload = {
            "input": {"text": text},
            "voice": {
                "languageCode": voice_language_code(voice_id, default="vi-VN"),
                "name": voice_id,
            },
            "audioConfig": {"audioEncoding": "MP3"},
        }
        response = requests.post(url, json=payload, timeout=tts_timeout(self._config))
        raise_for_tts_response(response, "Google Cloud TTS")
        data = response_json(response, "Google Cloud TTS")
        audio_content = str(data.get("audioContent") or "")
        if not audio_content:
            raise TTSError("Google Cloud TTS response did not include audioContent.")
        try:
            return base64.b64decode(audio_content)
        except Exception as exc:
            raise TTSError("Google Cloud TTS returned invalid base64 audioContent.") from exc

    def _request_amazon_polly(self, text: str, voice_id: str) -> bytes:
        access_key = required_tts_api_key(self._config, "Amazon Polly")
        secret_key = required_tts_api_secret(self._config, "Amazon Polly")
        region = str(getattr(self._config, "tts_api_region", "") or "us-east-1").strip()
        api_base = tts_api_base(self._config) or f"https://polly.{region}.amazonaws.com"
        url = _join_api_base(api_base, "/v1/speech")
        engine = tts_model(self._config, default="neural")
        payload = {
            "Engine": engine,
            "OutputFormat": "mp3",
            "Text": text,
            "TextType": "text",
            "VoiceId": voice_id,
        }
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        headers = _aws_sigv4_headers(
            method="POST",
            url=url,
            body=body,
            region=region,
            service="polly",
            access_key=access_key,
            secret_key=secret_key,
            content_type="application/json",
        )
        response = requests.post(url, data=body, headers=headers, timeout=tts_timeout(self._config))
        raise_for_tts_response(response, "Amazon Polly")
        return response.content


def _google_tts_url(api_base: str, api_key: str) -> str:
    separator = "&" if "?" in api_base else "?"
    return f"{api_base}{separator}key={quote(api_key, safe='')}"


def _join_api_base(api_base: str, path: str) -> str:
    base = str(api_base or "").strip().rstrip("/")
    clean_path = "/" + str(path or "").lstrip("/")
    return f"{base}{clean_path}"


def _aws_sigv4_headers(
    *,
    method: str,
    url: str,
    body: bytes,
    region: str,
    service: str,
    access_key: str,
    secret_key: str,
    content_type: str,
) -> dict[str, str]:
    parsed = urlparse(url)
    host = parsed.netloc
    canonical_uri = parsed.path or "/"
    canonical_querystring = parsed.query
    now = _datetime.datetime.now(_datetime.timezone.utc)
    amz_date = now.strftime("%Y%m%dT%H%M%SZ")
    date_stamp = now.strftime("%Y%m%d")
    payload_hash = hashlib.sha256(body).hexdigest()
    canonical_headers = (
        f"content-type:{content_type}\n"
        f"host:{host}\n"
        f"x-amz-content-sha256:{payload_hash}\n"
        f"x-amz-date:{amz_date}\n"
    )
    signed_headers = "content-type;host;x-amz-content-sha256;x-amz-date"
    canonical_request = "\n".join(
        [
            method.upper(),
            canonical_uri,
            canonical_querystring,
            canonical_headers,
            signed_headers,
            payload_hash,
        ]
    )
    algorithm = "AWS4-HMAC-SHA256"
    credential_scope = f"{date_stamp}/{region}/{service}/aws4_request"
    string_to_sign = "\n".join(
        [
            algorithm,
            amz_date,
            credential_scope,
            hashlib.sha256(canonical_request.encode("utf-8")).hexdigest(),
        ]
    )
    signing_key = _aws_signature_key(secret_key, date_stamp, region, service)
    signature = hmac.new(signing_key, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()
    authorization = (
        f"{algorithm} Credential={access_key}/{credential_scope}, "
        f"SignedHeaders={signed_headers}, Signature={signature}"
    )
    return {
        "Authorization": authorization,
        "Content-Type": content_type,
        "Host": host,
        "X-Amz-Content-Sha256": payload_hash,
        "X-Amz-Date": amz_date,
    }


def _aws_signature_key(secret_key: str, date_stamp: str, region: str, service: str) -> bytes:
    key_date = hmac.new(("AWS4" + secret_key).encode("utf-8"), date_stamp.encode("utf-8"), hashlib.sha256).digest()
    key_region = hmac.new(key_date, region.encode("utf-8"), hashlib.sha256).digest()
    key_service = hmac.new(key_region, service.encode("utf-8"), hashlib.sha256).digest()
    return hmac.new(key_service, b"aws4_request", hashlib.sha256).digest()
