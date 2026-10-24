from pathlib import Path

from ai_player.adapters.media import ffmpeg
from ai_player.adapters.pipeline.export_utils import _duration_value


def _make_silence(duration_seconds: float, output_path: Path) -> None:
    ffmpeg.make_silence(_duration_value(duration_seconds, default=0.0), output_path)


def _duration_seconds(path: Path) -> float:
    return _probe_duration_seconds(path)


def _probe_duration_seconds(path: Path) -> float:
    return _duration_value(ffmpeg.probe_duration_seconds(path), default=0.0)
