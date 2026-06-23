from __future__ import annotations

import asyncio
import threading
import time
from pathlib import Path

import edge_tts

from ai_player.core.config import AppConfig
from ai_player.services.tts_base import BaseTTSProvider, TTSError, clean_message, clean_text, remove_tts_output
from ai_player.services.tts_voices import EDGE_VOICES, voice_gender

_EDGE_TTS_LOCK = threading.Lock()


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
        for attempt in range(3):
            try:
                with _EDGE_TTS_LOCK:
                    asyncio.run(self._synthesize(clean, output_path, voice_id))
                if output_path.exists() and output_path.stat().st_size > 0:
                    return
                raise TTSError("Edge TTS returned an empty audio file.")
            except Exception as exc:
                last_error = exc
                remove_tts_output(output_path)
                if attempt >= 2:
                    break
                time.sleep(0.4 * (attempt + 1))
        detail = clean_message(last_error) if last_error is not None else "unknown error"
        raise TTSError(f"Edge TTS failed for voice '{voice_id}': {detail}") from last_error

    async def _synthesize(self, text: str, output_path: Path, voice: str) -> None:
        communicate = edge_tts.Communicate(text, voice)
        await communicate.save(str(output_path))
