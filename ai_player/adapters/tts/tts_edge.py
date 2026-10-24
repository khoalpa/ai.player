from __future__ import annotations

import asyncio
import threading
import time
from pathlib import Path

import edge_tts

from ai_player.adapters.tts.tts_base import BaseTTSProvider, TTSError, clean_message, clean_text, remove_tts_output
from ai_player.adapters.tts.tts_voices import EDGE_VOICES, voice_gender
from ai_player.configuration import AppConfig

_EDGE_TTS_LOCK = threading.Lock()
_DEFAULT_ATTEMPTS = 3
_EMPTY_AUDIO_ATTEMPTS = 5


def _is_empty_audio_error(error: Exception) -> bool:
    message = str(error or "").strip().lower()
    return "no audio was received" in message or "empty audio" in message


def compatible_edge_voice_id(voice_id: object) -> str:
    raw = str(voice_id or "").strip()
    available_ids = {voice.id for voice in EDGE_VOICES}
    if raw in available_ids:
        return raw
    gender = voice_gender("edge", raw)
    if gender == "male":
        return "vi-VN-NamMinhNeural"
    return "vi-VN-HoaiMyNeural"


class EdgeTTSProvider(BaseTTSProvider):
    def __init__(self, config: AppConfig) -> None:
        self._voice = compatible_edge_voice_id(config.tts_voice)

    def synthesize(self, text: str, output_path: Path, voice: str | None = None) -> None:
        clean = clean_text(text)
        if not clean:
            raise TTSError("Edge TTS cannot read empty text.")
        output_path = Path(output_path)
        voice_id = compatible_edge_voice_id(voice or self._voice)
        last_error: Exception | None = None
        attempt = 0
        max_attempts = _DEFAULT_ATTEMPTS
        while attempt < max_attempts:
            try:
                with _EDGE_TTS_LOCK:
                    asyncio.run(self._synthesize(clean, output_path, voice_id))
                if output_path.exists() and output_path.stat().st_size > 0:
                    return
                raise TTSError("Edge TTS returned an empty audio file.")
            except Exception as exc:
                last_error = exc
                remove_tts_output(output_path)
                if _is_empty_audio_error(exc):
                    max_attempts = _EMPTY_AUDIO_ATTEMPTS
                attempt += 1
                if attempt >= max_attempts:
                    break
                time.sleep(min(0.75 * (2 ** (attempt - 1)), 6.0))
        detail = clean_message(last_error) if last_error is not None else "unknown error"
        raise TTSError(f"Edge TTS failed for voice '{voice_id}': {detail}") from last_error

    async def _synthesize(self, text: str, output_path: Path, voice: str) -> None:
        communicate = edge_tts.Communicate(text, voice)
        await communicate.save(str(output_path))
