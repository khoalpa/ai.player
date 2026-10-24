from __future__ import annotations

import atexit
import inspect
import json
import os
import queue
import subprocess
import threading
import time
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Any

from ai_player.adapters.media.ffmpeg import ProcessCancelled
from ai_player.adapters.tts.tts_base import BaseTTSProvider, TTSError, check_tts_cancelled, tts_cancelable_lock
from ai_player.adapters.tts.tts_base import clean_message as _clean_message
from ai_player.adapters.tts.tts_base import clean_text as _clean_text
from ai_player.adapters.tts.tts_base import finite_float as _finite_float
from ai_player.adapters.tts.tts_base import int_value as _int_value
from ai_player.adapters.tts.tts_voices import (
    V3_VIENEU_VOICES,
    VieNeuModelOption,
    VoiceOption,
    migrate_vieneu_legacy_voice_id,
)
from ai_player.adapters.tts.tts_voices import read_vieneu_voices as _read_vieneu_voices
from ai_player.configuration import INTERNAL_VIENEU_V3_PATH, PACKAGE_ROOT, PROJECT_ROOT, AppConfig
from ai_player.runtime.vieneu_v3 import SDK_VERSION, engine_kwargs, validate_bundle

_VIENEU_ENGINE_LOCK = threading.Lock()
_VIENEU_ENGINE_CACHE: dict[tuple[str, ...], Any] = {}
_VIENEU_SERVER_CACHE_LOCK = threading.Lock()
_VIENEU_SERVER_CACHE: dict[tuple[str, ...], VieNeuServerClient] = {}


def available_vieneu_models(mode: str, config: AppConfig) -> list[VieNeuModelOption]:
    normalize_vieneu_mode(mode)
    return [VieNeuModelOption(str(INTERNAL_VIENEU_V3_PATH), "VieNeu-TTS v3 Turbo (offline)", True)]


def normalize_vieneu_mode(value: object) -> str:
    if str(value or "v3turbo").strip().lower() != "v3turbo":
        raise TTSError("AI Player chỉ hỗ trợ VieNeu-TTS v3 Turbo. Hãy chuyển cấu hình cũ sang v3turbo.")
    return "v3turbo"


def normalize_vieneu_device(value: object) -> str:
    raw = str(value or "auto").strip().lower()
    return {"gpu": "cuda", "cuda:0": "cuda"}.get(raw, raw if raw in {"auto", "cpu", "cuda"} else "auto")


def resolve_vieneu_runtime_device(value: object) -> str:
    # Auto detection belongs to the isolated runtime, not the host's Torch installation.
    return normalize_vieneu_device(value)


def normalize_vieneu_backend(value: object) -> str:
    raw = str(value or "auto").strip().lower()
    return raw if raw in {"auto", "onnx", "pytorch"} else "auto"


def resolve_vieneu_effective_mode(core: object, mode: object, device: object) -> str:
    if str(core or "local") != "local":
        raise TTSError("VieNeu v3 Turbo chạy tại máy; cấu hình remote cũ đã bị loại bỏ.")
    return normalize_vieneu_mode(mode)


def resolve_vieneu_runtime_backend(mode: object, model_name: object, device: object, backend: object) -> str:
    normalize_vieneu_mode(mode)
    selected = normalize_vieneu_backend(backend)
    if selected != "auto":
        return selected
    return "onnx" if normalize_vieneu_device(device) == "cpu" else "auto"


class VieNeuTTSProvider(BaseTTSProvider):
    def __init__(self, config: AppConfig) -> None:
        self._config = config
        self._server: VieNeuServerClient | None = None

    def synthesize(self, text: str, output_path: Path, voice: str | None = None) -> None:
        self._check_cancelled()
        clean_text = _clean_text(text)
        if not clean_text:
            raise TTSError("VieNeu-TTS kh\u00f4ng th\u1ec3 \u0111\u1ecdc v\u0103n b\u1ea3n r\u1ed7ng.")

        voice_id = voice or self._config.tts_voice
        errors: list[str] = []
        for candidate in _vieneu_fallback_configs(self._config):
            self._check_cancelled()
            try:
                self._synthesize_with_config(candidate, clean_text, output_path, voice_id)
                self._config = candidate
                return
            except ProcessCancelled:
                # The shared client has already cancelled its own request. Do
                # not close it here: another caller may now hold its lock.
                raise
            except Exception as exc:
                errors.append(f"{_vieneu_config_label(candidate)}: {_clean_message(exc)}")
                self._reset_server()

        details = "\n".join(errors[-4:])
        message = "VieNeu-TTS kh\u00f4ng ch\u1ea1y \u0111\u01b0\u1ee3c sau khi t\u1ef1 h\u1ea1 c\u1ea5u h\u00ecnh."
        raise TTSError(f"{message}\n{details}")

    def _synthesize_with_config(
        self,
        config: AppConfig,
        text: str,
        output_path: Path,
        voice_id: str,
    ) -> None:
        voice_id = _compatible_vieneu_voice_id(config, voice_id)
        if self._should_use_subprocess(config):
            self._synthesize_subprocess(config, text, output_path, voice_id)
            return

        try:
            self._synthesize_in_process(config, text, output_path, voice_id)
        except ProcessCancelled:
            raise
        except Exception:
            if self._can_use_subprocess(config):
                self._synthesize_subprocess(config, text, output_path, voice_id)
                return
            raise

    def _synthesize_in_process(
        self,
        config: AppConfig,
        text: str,
        output_path: Path,
        voice_id: str,
    ) -> None:
        engine = _get_vieneu_engine(config)
        voice = _resolve_vieneu_preset_voice(engine, voice_id)
        infer_kwargs = _build_vieneu_infer_kwargs(
            engine=engine,
            text=text,
            voice=voice,
            temperature=config.vieneu_tts_temperature,
            max_chars=config.vieneu_tts_max_chars_chunk,
        )
        try:
            audio = engine.infer(**infer_kwargs)
            if _empty_vieneu_audio(audio):
                raise TTSError(_vieneu_empty_audio_message(config))
            output_path.parent.mkdir(parents=True, exist_ok=True)
            engine.save(audio, str(output_path))
            if not output_path.exists() or output_path.stat().st_size <= 44:
                raise TTSError(_vieneu_empty_audio_message(config))
        except Exception as exc:
            raise TTSError(
                "VieNeu-TTS kh\u00f4ng t\u1ea1o \u0111\u01b0\u1ee3c audio "
                f"(mode={config.vieneu_tts_mode}, "
                f"voice={voice_id}, "
                f"device={config.vieneu_tts_device}): {exc}"
            ) from exc

    def _synthesize_subprocess(
        self,
        config: AppConfig,
        text: str,
        output_path: Path,
        voice_id: str,
    ) -> None:
        if self._server is None or self._server.config_key != _vieneu_server_config_key(config):
            self._server = _get_shared_vieneu_server(config)
        self._server.synthesize(
            text=text,
            voice=voice_id,
            output_path=output_path,
            temperature=config.vieneu_tts_temperature,
            max_chars=config.vieneu_tts_max_chars_chunk,
            cancel_callback=getattr(self, "_cancel_callback", None),
        )

    def _should_use_subprocess(self, config: AppConfig) -> bool:
        runtime = str(config.vieneu_tts_runtime or "auto").strip().lower()
        if runtime in {"subprocess", "auto"}:
            return True
        raise TTSError("VieNeu v3 Turbo yêu cầu tiến trình TTS riêng (subprocess).")

    def _can_use_subprocess(self, config: AppConfig) -> bool:
        python = Path(config.vieneu_tts_python)
        return python.is_file()

    def close(self) -> None:
        self._server = None

    def _reset_server(self) -> None:
        if self._server is not None:
            _discard_shared_vieneu_server(self._server)
            self._server = None


class VieNeuServerClient:
    def __init__(self, config: AppConfig) -> None:
        self._config = config
        self.config_key = _vieneu_server_config_key(config)
        self._process: subprocess.Popen | None = None
        self._lock = threading.Lock()
        self._output_queue: queue.Queue[str | None] = queue.Queue()
        self._reader_thread: threading.Thread | None = None

    def synthesize(
        self,
        *,
        text: str,
        voice: str,
        output_path: Path,
        temperature: float,
        max_chars: int,
        cancel_callback: Callable[[], bool] | None = None,
    ) -> None:
        with tts_cancelable_lock(self._lock, cancel_callback):
            self._cancel_callback = cancel_callback
            try:
                self._ensure_started()
                check_tts_cancelled(cancel_callback)
                assert self._process is not None
                payload = {
                    "op": "synthesize",
                    "text": text,
                    "voice": voice,
                    "output": str(output_path),
                    "temperature": temperature,
                    "max_chars": max_chars,
                }
                self._write_payload(payload)
                response = self._read_response()
                check_tts_cancelled(cancel_callback)
                if not response.get("ok"):
                    raise TTSError(_clean_message(response.get("error") or "VieNeu subprocess failed."))
            except ProcessCancelled:
                self._terminate_current_process()
                raise
            finally:
                self._cancel_callback = None

    def _ensure_started(self) -> None:
        if self._process is not None and self._process.poll() is None:
            return

        config = self._config
        mode = resolve_vieneu_effective_mode(
            config.vieneu_tts_core,
            config.vieneu_tts_mode,
            config.vieneu_tts_device,
        )
        device = resolve_vieneu_runtime_device(config.vieneu_tts_device)
        model_name = _resolve_vieneu_model_name(config.vieneu_tts_model_name, mode)
        backend = resolve_vieneu_runtime_backend(mode, model_name, device, config.vieneu_tts_backend)
        _validate_vieneu_local_files(config, mode, model_name)
        if not Path(config.vieneu_tts_python).is_file():
            raise TTSError("Chưa cài VieNeu v3 Turbo. Chạy scripts/setup_vieneu_runtime.ps1.")
        command = [
            str(Path(config.vieneu_tts_python)),
            "-X",
            "utf8",
            "-m",
            "ai_player.adapters.tts.vieneu_tts_server",
            "--mode",
            mode,
            "--model-name",
            model_name,
            "--device",
            device,
            "--backend",
            backend,
            "--offline",
        ]
        env = os.environ.copy()
        env.update(
            HF_HUB_OFFLINE="1",
            TRANSFORMERS_OFFLINE="1",
            HF_DATASETS_OFFLINE="1",
            AI_PLAYER_PROJECT_ROOT=str(PROJECT_ROOT),
            PYTHONUTF8="1",
        )
        source_root = str(PACKAGE_ROOT.parent)
        env["PYTHONPATH"] = source_root
        self._process = subprocess.Popen(
            command,
            cwd=str(PROJECT_ROOT),
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        self._start_stdout_reader()
        response = self._read_response(timeout_seconds=300)
        if not response.get("ok"):
            raise TTSError(_clean_message(response.get("error") or "VieNeu subprocess init failed."))

    def _write_payload(self, payload: dict[str, Any]) -> None:
        assert self._process is not None
        assert self._process.stdin is not None
        if "text" in payload:
            payload = {**payload, "text": _clean_text(payload["text"])}
        line = json.dumps(payload, ensure_ascii=True) + "\n"
        self._process.stdin.write(line.encode("utf-8", errors="replace"))
        self._process.stdin.flush()

    def _read_response(self, timeout_seconds: float = 180) -> dict[str, Any]:
        assert self._process is not None
        deadline = time.monotonic() + timeout_seconds
        last_line = ""
        while time.monotonic() < deadline:
            check_tts_cancelled(getattr(self, "_cancel_callback", None))
            remaining = max(0.01, deadline - time.monotonic())
            try:
                line = self._output_queue.get(timeout=min(0.25, remaining))
            except queue.Empty:
                if self._process.poll() is not None:
                    raise TTSError(
                        f"VieNeu subprocess exited early. Last output: {_clean_message(last_line.strip())}"
                    ) from None
                continue
            if not line:
                if self._process.poll() is not None:
                    raise TTSError(f"VieNeu subprocess exited early. Last output: {_clean_message(last_line.strip())}")
                continue
            last_line = line
            marker = "AI_PLAYER_JSON:"
            clean_line = line.replace("\x00", "")
            marker_index = clean_line.find(marker)
            if marker_index >= 0:
                payload_text = clean_line[marker_index + len(marker) :]
                try:
                    payload = json.loads(payload_text)
                except (TypeError, ValueError) as exc:
                    raise TTSError(
                        f"VieNeu subprocess returned invalid JSON. Last output: {_clean_message(last_line.strip())}"
                    ) from exc
                if not isinstance(payload, dict):
                    raise TTSError(
                        "VieNeu subprocess returned invalid JSON payload. "
                        f"Last output: {_clean_message(last_line.strip())}"
                    )
                return payload
        self._terminate_current_process()
        raise TTSError(f"Timeout waiting for VieNeu subprocess. Last output: {_clean_message(last_line.strip())}")

    def _start_stdout_reader(self) -> None:
        assert self._process is not None
        assert self._process.stdout is not None
        self._output_queue = queue.Queue()
        process_stdout = self._process.stdout
        output_queue = self._output_queue

        def read_stdout() -> None:
            try:
                for raw_line in iter(process_stdout.readline, b""):
                    line = raw_line.decode("utf-8", errors="replace") if isinstance(raw_line, bytes) else raw_line
                    output_queue.put(line)
            finally:
                output_queue.put(None)

        self._reader_thread = threading.Thread(target=read_stdout, daemon=True)
        self._reader_thread.start()

    def _terminate_current_process(self) -> None:
        process = self._process
        self._process = None
        if process is None or process.poll() is not None:
            return
        try:
            process.terminate()
            process.wait(timeout=5)
        except Exception:
            try:
                process.kill()
            except Exception:
                pass

    def close(self) -> None:
        process = self._process
        self._process = None
        if process is None or process.poll() is not None:
            return
        try:
            if process.stdin is not None:
                line = json.dumps({"op": "shutdown"}, ensure_ascii=True) + "\n"
                process.stdin.write(line.encode("utf-8"))
                process.stdin.flush()
            process.wait(timeout=5)
        except Exception:
            try:
                process.terminate()
                process.wait(timeout=2)
            except Exception:
                try:
                    process.kill()
                except Exception:
                    pass


def _get_shared_vieneu_server(config: AppConfig) -> VieNeuServerClient:
    key = _vieneu_server_config_key(config)
    with _VIENEU_SERVER_CACHE_LOCK:
        server = _VIENEU_SERVER_CACHE.get(key)
        if server is None:
            server = VieNeuServerClient(config)
            _VIENEU_SERVER_CACHE[key] = server
        return server


def _discard_shared_vieneu_server(server: VieNeuServerClient) -> None:
    with _VIENEU_SERVER_CACHE_LOCK:
        for key, cached in list(_VIENEU_SERVER_CACHE.items()):
            if cached is server:
                _VIENEU_SERVER_CACHE.pop(key, None)
    server.close()


def _close_shared_vieneu_servers() -> None:
    with _VIENEU_SERVER_CACHE_LOCK:
        servers = list(_VIENEU_SERVER_CACHE.values())
        _VIENEU_SERVER_CACHE.clear()
    for server in servers:
        server.close()


atexit.register(_close_shared_vieneu_servers)


def _vieneu_fallback_configs(config: AppConfig) -> list[AppConfig]:
    resolve_vieneu_effective_mode(config.vieneu_tts_core, config.vieneu_tts_mode, config.vieneu_tts_device)
    candidates = [config]
    if config.vieneu_tts_device != "cpu" or config.vieneu_tts_backend not in {"auto", "onnx"}:
        candidates.append(replace(config, vieneu_tts_device="cpu", vieneu_tts_backend="onnx"))
    return candidates


def _vieneu_server_config_key(config: AppConfig) -> tuple[str, ...]:
    return (
        SDK_VERSION,
        config.vieneu_tts_python,
        config.vieneu_tts_mode,
        config.vieneu_tts_model_name,
        config.vieneu_tts_device,
        config.vieneu_tts_backend,
        config.vieneu_tts_runtime,
        str(config.vieneu_tts_offline),
    )


def _vieneu_config_label(config: AppConfig) -> str:
    return f"v3turbo/{config.vieneu_tts_device}/{config.vieneu_tts_backend}"


def _compatible_vieneu_voice_id(config: AppConfig, voice_id: str) -> str:
    voices = vieneu_voices(config)
    migrated = migrate_vieneu_legacy_voice_id(voice_id, tuple((v.name, v.id) for v in voices))
    if migrated in {v.id for v in voices}:
        return migrated
    return "Thục Đoan"


def _get_vieneu_engine(config: AppConfig):
    from ai_player.adapters.tts.vieneu_tts_server import create_engine

    key = _vieneu_server_config_key(config)
    with _VIENEU_ENGINE_LOCK:
        if key not in _VIENEU_ENGINE_CACHE:
            normalize_vieneu_mode(config.vieneu_tts_mode)
            _VIENEU_ENGINE_CACHE[key] = create_engine(
                config.vieneu_tts_model_name, config.vieneu_tts_device, config.vieneu_tts_backend
            )
        return _VIENEU_ENGINE_CACHE[key]


def _build_vieneu_engine_kwargs(*, mode: str, model_name: str, device: str, backend: str) -> dict[str, Any]:
    normalize_vieneu_mode(mode)
    return engine_kwargs(Path(model_name), device, backend)


def _resolve_vieneu_model_name(value: object, mode: str) -> str:
    normalize_vieneu_mode(mode)
    return str(value or INTERNAL_VIENEU_V3_PATH)


def _validate_vieneu_local_files(config: AppConfig, mode: str, model_name: str) -> None:
    normalize_vieneu_mode(mode)
    try:
        validate_bundle(Path(model_name))
    except (ValueError, OSError) as exc:
        raise TTSError(str(exc)) from exc


def _build_vieneu_infer_kwargs(
    *,
    engine: Any,
    text: str,
    voice: Any,
    temperature: float,
    max_chars: int,
) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "text": text,
        "voice": voice,
        "temperature": _finite_float(temperature, default=0.6),
        "max_chars": _int_value(max_chars, default=160, minimum=1),
    }
    infer = getattr(engine, "infer", None)
    try:
        signature = inspect.signature(infer) if callable(infer) else None
    except (TypeError, ValueError):
        signature = None
    if signature is None:
        return {key: value for key, value in kwargs.items() if value is not None}
    if any(param.kind == inspect.Parameter.VAR_KEYWORD for param in signature.parameters.values()):
        return {key: value for key, value in kwargs.items() if value is not None}
    return {key: value for key, value in kwargs.items() if key in signature.parameters and value is not None}


def _empty_vieneu_audio(audio: object) -> bool:
    size = getattr(audio, "size", None)
    if size is not None:
        try:
            return int(size) <= 0
        except (TypeError, ValueError, OverflowError):
            pass
    try:
        return len(audio) <= 0  # type: ignore[arg-type]
    except Exception:
        return audio is None


def _vieneu_empty_audio_message(config: AppConfig) -> str:
    return "VieNeu-TTS v3 Turbo trả về audio rỗng."


def _resolve_vieneu_preset_voice(engine: Any, voice_id: str) -> Any:
    return engine.get_preset_voice(voice_id or None)


def _preferred_vieneu_voice_ids(config: AppConfig, gender: str) -> tuple[str, ...]:
    return ("Minh Triết", "Thái Sơn", "Hải Đăng") if gender == "male" else ("Thục Đoan", "Thùy Dung", "Trúc Ly")


def vieneu_voices(config: AppConfig | None) -> list[VoiceOption]:
    if config is not None:
        path = Path(config.vieneu_tts_model_name) / "model" / "voices_v3_turbo.json"
        if path.is_file():
            voices = _read_vieneu_voices(path)
            if voices:
                return voices
    return V3_VIENEU_VOICES
