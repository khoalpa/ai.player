"""Speech generation use case shared by preview, playback and export."""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path
from uuid import uuid4

from ai_player.application.jobs import JobCancelled
from ai_player.application.ports import SpeechSynthesizer


class SpeechService:
    def __init__(self, provider: SpeechSynthesizer) -> None:
        self._provider = provider
        self._cancelled: Callable[[], bool] = lambda: False

    def set_cancel_callback(self, callback: Callable[[], bool]) -> None:
        self._cancelled = callback
        self._provider.set_cancel_callback(callback)

    def synthesize(self, text: str, output_path: Path, voice: str | None = None) -> None:
        self._check_cancelled()
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = output_path.with_name(f".{output_path.stem}.{uuid4().hex}{output_path.suffix}")
        try:
            self._provider.synthesize(text, temporary, voice=voice)
            self._check_cancelled()
            if not temporary.is_file() or temporary.stat().st_size == 0:
                raise RuntimeError("Speech provider did not produce audio")
            os.replace(temporary, output_path)
        finally:
            temporary.unlink(missing_ok=True)

    def _check_cancelled(self) -> None:
        if self._cancelled():
            raise JobCancelled("Speech generation cancelled")

    def close(self) -> None:
        self._provider.close()
