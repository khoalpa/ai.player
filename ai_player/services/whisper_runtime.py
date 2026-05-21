from __future__ import annotations

import os
import threading
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ai_player.core.config import PROJECT_ROOT, AppConfig
from ai_player.core.gpu import ctranslate2_cuda_available, cuda_runtime_files_available


@dataclass(frozen=True)
class WhisperRuntimeKey:
    model_path: str
    device: str
    compute_type: str
    local_files_only: bool


class SharedWhisperModel:
    def __init__(self, model: Any, key: WhisperRuntimeKey) -> None:
        self._model = model
        self.key = key
        self._lock = threading.RLock()

    def transcribe(self, *args, **kwargs):
        with self._lock:
            segments, info = self._model.transcribe(*args, **kwargs)
            return _materialize_segments(segments), info


_WHISPER_MODEL_CACHE_LOCK = threading.Lock()
_WHISPER_MODEL_CACHE: dict[WhisperRuntimeKey, SharedWhisperModel] = {}


def get_shared_whisper_model(
    model_path: str,
    *,
    device: str,
    compute_type: str,
    local_files_only: bool,
) -> SharedWhisperModel:
    key = WhisperRuntimeKey(
        model_path=_normalize_model_path(model_path),
        device=str(device or "auto").strip().lower(),
        compute_type=str(compute_type or "").strip().lower() or "default",
        local_files_only=bool(local_files_only),
    )
    with _WHISPER_MODEL_CACHE_LOCK:
        cached = _WHISPER_MODEL_CACHE.get(key)
        if cached is not None:
            return cached
        model = _create_whisper_model(
            key.model_path,
            device=key.device,
            compute_type=key.compute_type,
            local_files_only=key.local_files_only,
        )
        cached = SharedWhisperModel(model, key)
        _WHISPER_MODEL_CACHE[key] = cached
        return cached


def get_shared_whisper_model_for_config(
    config: AppConfig,
    *,
    device: str | None = None,
    compute_type: str | None = None,
) -> SharedWhisperModel:
    resolved_device = device or effective_whisper_device(config.whisper_device)
    resolved_compute_type = compute_type or effective_whisper_compute_type(config.whisper_compute_type, resolved_device)
    return get_shared_whisper_model(
        config.whisper_model,
        device=resolved_device,
        compute_type=resolved_compute_type,
        local_files_only=config.whisper_offline,
    )


def clear_shared_whisper_models() -> None:
    with _WHISPER_MODEL_CACHE_LOCK:
        _WHISPER_MODEL_CACHE.clear()


def effective_whisper_device(value: str) -> str:
    device = str(value or "auto").strip().lower()
    if device == "cpu":
        return "cpu"
    if device == "cuda":
        return "cuda" if _cuda_runtime_available() else "cpu"
    if device == "auto":
        return "cuda" if _cuda_runtime_available() else "cpu"
    return device


def effective_whisper_compute_type(value: str, device: str) -> str:
    compute_type = str(value or "").strip().lower() or "float16"
    if str(device or "").lower() == "cpu" and compute_type in {"float16", "float32"}:
        return "int8"
    return compute_type


def effective_whisper_beam_size(value: object) -> int:
    try:
        return max(1, min(8, int(value)))
    except (TypeError, ValueError):
        return 1


def whisper_transcribe_kwargs(config: AppConfig, language: str | None) -> dict[str, object]:
    return {
        "beam_size": effective_whisper_beam_size(config.whisper_beam_size),
        "vad_filter": bool(config.whisper_vad_filter),
        "language": language,
    }


def _create_whisper_model(
    model_path: str,
    *,
    device: str,
    compute_type: str,
    local_files_only: bool,
):
    from faster_whisper import WhisperModel

    return WhisperModel(
        model_path,
        device=device,
        compute_type=compute_type,
        local_files_only=local_files_only,
        cpu_threads=_whisper_cpu_threads(),
        num_workers=_whisper_num_workers(),
    )


def _materialize_segments(segments: Iterable[Any]) -> list[Any]:
    return list(segments)


def _normalize_model_path(value: str) -> str:
    path = Path(str(value or "").strip())
    try:
        if path.exists():
            return str(path.resolve())
    except OSError:
        pass
    return str(value or "").strip()


def _cuda_runtime_available() -> bool:
    search_roots = [Path(value) for value in (os.environ.get("CUDA_PATH"),) if value]
    search_roots.append(PROJECT_ROOT / ".venv")
    return ctranslate2_cuda_available() or cuda_runtime_files_available(*search_roots)


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _whisper_cpu_threads() -> int:
    cpu_count = os.cpu_count() or 2
    return max(1, min(cpu_count, _env_int("AI_PLAYER_WHISPER_CPU_THREADS", max(4, cpu_count // 2))))


def _whisper_num_workers() -> int:
    return max(1, min(4, _env_int("AI_PLAYER_WHISPER_NUM_WORKERS", 2)))
