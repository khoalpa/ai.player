from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from ai_player.services.whisper_runtime import SharedWhisperModel

WhisperState = Callable[[], str]
WhisperStatus = Callable[[str], None]
WhisperCpuSwitch = Callable[[Exception], SharedWhisperModel]


def transcribe_model_with_device_fallback(
    model: SharedWhisperModel,
    source_audio: Path,
    kwargs: dict[str, object],
    *,
    whisper_device: WhisperState,
    whisper_compute_type: WhisperState,
    emit_status: WhisperStatus,
    switch_whisper_to_cpu: WhisperCpuSwitch,
    passthrough_errors: tuple[type[BaseException], ...] = (),
    retry_cpu_compute: bool = True,
):
    try:
        return model.transcribe(str(source_audio), **kwargs)
    except passthrough_errors:
        raise
    except Exception as exc:
        device = whisper_device()
        compute_type = whisper_compute_type()
        if retry_cpu_compute and device == "cpu" and compute_type != "int8":
            emit_status("worker_whisper_cpu_compute_fallback")
            model = switch_whisper_to_cpu(exc)
            return model.transcribe(str(source_audio), **kwargs)
        if device == "cpu":
            raise
        emit_status("worker_whisper_cublas_fallback")
        model = switch_whisper_to_cpu(exc)
        return model.transcribe(str(source_audio), **kwargs)
