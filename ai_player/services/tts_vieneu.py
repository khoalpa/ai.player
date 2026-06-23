from __future__ import annotations

import atexit
import importlib.util
import inspect
import json
import os
import queue
import subprocess
import sys
import threading
import time
from dataclasses import replace
from pathlib import Path
from typing import Any

from ai_player.core.config import (
    INTERNAL_VIENEU_STANDARD_CODEC,
    INTERNAL_VIENEU_STANDARD_GGUF,
    INTERNAL_VIENEU_STANDARD_PATH,
    INTERNAL_VIENEU_TTS_PATH,
    INTERNAL_VIENEU_TURBO_DECODER,
    INTERNAL_VIENEU_TURBO_ENCODER,
    INTERNAL_VIENEU_TURBO_GGUF,
    INTERNAL_VIENEU_TURBO_PATH,
    PROJECT_ROOT,
    AppConfig,
)
from ai_player.core.offline_env import pop_hf_offline_environment, push_hf_offline_environment
from ai_player.services.tts_base import BaseTTSProvider, TTSError
from ai_player.services.tts_base import clean_message as _clean_message
from ai_player.services.tts_base import clean_text as _clean_text
from ai_player.services.tts_base import finite_float as _finite_float
from ai_player.services.tts_base import int_value as _int_value
from ai_player.services.tts_voices import (
    STANDARD_VIENEU_VOICES,
    TURBO_VIENEU_VOICES,
    VieNeuModelOption,
    VoiceOption,
    migrate_vieneu_legacy_voice_id,
    voice_gender,
)
from ai_player.services.tts_voices import normalize_voice_token as _normalize_voice_token
from ai_player.services.tts_voices import read_vieneu_voices as _read_vieneu_voices
from ai_player.services.tts_voices import vieneu_model_voices_path as _vieneu_model_voices_path

_VIENEU_ENGINE_LOCK = threading.Lock()
_VIENEU_ENGINE_CACHE: dict[tuple[str, ...], Any] = {}
_VIENEU_SERVER_CACHE_LOCK = threading.Lock()
_VIENEU_SERVER_CACHE: dict[tuple[str, ...], VieNeuServerClient] = {}
_VIENEU_REMOTE_CODEC_REPO = "neuphonic/neucodec-onnx-decoder-int8"

def available_vieneu_models(mode: str, config: AppConfig) -> list[VieNeuModelOption]:
    selected_mode = normalize_vieneu_mode(mode)
    if selected_mode == "remote":
        return [
            VieNeuModelOption(
                "pnnbao-ump/VieNeu-TTS",
                "VieNeu-TTS remote API",
                False,
            )
        ]
    if selected_mode == "standard":
        models = _local_vieneu_standard_models()
        models.extend(
            [
                VieNeuModelOption(
                    "pnnbao-ump/VieNeu-TTS-0.3B-q4-gguf",
                    "VieNeu-TTS 0.3B q4 GGUF (HF/cache)",
                    False,
                ),
                VieNeuModelOption(
                    "pnnbao-ump/VieNeu-TTS",
                    "VieNeu-TTS standard (HF/cache)",
                    False,
                ),
            ]
        )
        return _unique_vieneu_models(models)

    default_local = INTERNAL_VIENEU_TURBO_PATH / "vieneu-tts-v2-turbo.gguf"
    models = _local_vieneu_turbo_models()
    if default_local.exists():
        models.insert(
            0, VieNeuModelOption(str(default_local.resolve()), "VieNeu-TTS v2 Turbo GGUF (local offline)", True)
        )
    models.extend(
        [
            VieNeuModelOption(
                "pnnbao-ump/VieNeu-TTS-v2-Turbo-GGUF",
                "VieNeu-TTS v2 Turbo GGUF (HF/cache)",
                False,
            ),
        ]
    )
    return _unique_vieneu_models(models)

def normalize_vieneu_mode(value: object) -> str:
    raw = str(value or "turbo").strip().lower().replace("-", "_")
    aliases = {
        "local": "turbo",
        "default": "turbo",
        "turbo": "turbo",
        "standard": "standard",
        "remote": "turbo",
        "api": "turbo",
        "remote_api": "turbo",
        "fast": "fast",
        "gpu": "fast",
        "cuda": "fast",
        "turbo_gpu": "turbo_gpu",
        "xpu": "xpu",
    }
    if raw in aliases:
        return aliases[raw]
    raise TTSError(f"VieNeu mode kh\u00f4ng h\u1ee3p l\u1ec7: {value!r}")


def normalize_vieneu_device(value: object) -> str:
    raw = str(value or "auto").strip().lower().replace("-", "_")
    aliases = {
        "auto": "auto",
        "default": "auto",
        "prefer_gpu": "auto",
        "gpu": "cuda",
        "cuda": "cuda",
        "cuda:0": "cuda",
        "cpu": "cpu",
    }
    if raw in aliases:
        return aliases[raw]
    return "auto"


def resolve_vieneu_runtime_device(value: object) -> str:
    device = normalize_vieneu_device(value)
    if device != "auto":
        return device
    try:
        import torch

        return "cuda" if torch.cuda.is_available() else "cpu"
    except Exception:
        return "cpu"


def normalize_vieneu_backend(value: object) -> str:
    raw = str(value or "auto").strip().lower().replace("-", "_")
    if raw in {"auto", "native", "lmdeploy"}:
        return raw
    return "auto"


def resolve_vieneu_effective_mode(core: object, mode: object, device: object) -> str:
    selected_mode = normalize_vieneu_mode(mode)
    return "standard" if selected_mode == "standard" else "turbo"


def resolve_vieneu_runtime_backend(mode: object, model_name: object, device: object, backend: object) -> str:
    requested = normalize_vieneu_backend(backend)
    resolved_mode = normalize_vieneu_mode(mode)
    resolved_device = resolve_vieneu_runtime_device(device)
    clean_model = str(model_name or "").strip().lower()
    supports_lmdeploy = resolved_mode == "standard" and resolved_device == "cuda"
    if "gguf" in clean_model or "turbo" in clean_model:
        supports_lmdeploy = False
    if requested == "native":
        return "native"
    if requested == "lmdeploy":
        return "lmdeploy" if supports_lmdeploy and importlib.util.find_spec("lmdeploy") else "native"
    if not supports_lmdeploy:
        return "native"
    return "lmdeploy" if importlib.util.find_spec("lmdeploy") else "native"

class VieNeuTTSProvider(BaseTTSProvider):
    def __init__(self, config: AppConfig) -> None:
        self._config = config
        self._server: VieNeuServerClient | None = None

    def synthesize(self, text: str, output_path: Path, voice: str | None = None) -> None:
        clean_text = _clean_text(text)
        if not clean_text:
            raise TTSError("VieNeu-TTS kh\u00f4ng th\u1ec3 \u0111\u1ecdc v\u0103n b\u1ea3n r\u1ed7ng.")

        voice_id = voice or self._config.tts_voice
        errors: list[str] = []
        for candidate in _vieneu_fallback_configs(self._config):
            try:
                self._synthesize_with_config(candidate, clean_text, output_path, voice_id)
                self._config = candidate
                return
            except Exception as exc:
                errors.append(f"{_vieneu_config_label(candidate)}: {_clean_message(exc)}")
                self._reset_server()

        details = "\n".join(errors[-4:])
        message = (
            "VieNeu-TTS kh\u00f4ng ch\u1ea1y \u0111\u01b0\u1ee3c sau khi t\u1ef1 h\u1ea1 c\u1ea5u h\u00ecnh."
        )
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
        )

    def _should_use_subprocess(self, config: AppConfig) -> bool:
        runtime = str(config.vieneu_tts_runtime or "auto").strip().lower()
        if runtime == "subprocess":
            return self._can_use_subprocess(config)
        return runtime == "auto" and self._can_use_subprocess(config)

    def _can_use_subprocess(self, config: AppConfig) -> bool:
        python = Path(config.vieneu_tts_python)
        return python.exists() and _vieneu_import_root(Path(config.vieneu_tts_path)).exists()

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
    ) -> None:
        with self._lock:
            self._ensure_started()
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
            if not response.get("ok"):
                raise TTSError(_clean_message(response.get("error") or "VieNeu subprocess failed."))

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
        script = Path(__file__).with_name("vieneu_tts_server.py")
        command = [
            str(Path(config.vieneu_tts_python)),
            str(script),
            "--root",
            str(Path(config.vieneu_tts_path)),
            "--mode",
            mode,
            "--api-base",
            str(config.vieneu_tts_api_base or ""),
            "--model-name",
            model_name,
            "--device",
            device,
            "--backend",
            backend,
        ]
        decoder_path = _effective_vieneu_decoder_path(config)
        encoder_path = _effective_vieneu_encoder_path(config)
        standard_codec_path = _effective_vieneu_standard_codec_path(config)
        if decoder_path:
            command.extend(["--decoder-path", str(Path(decoder_path))])
        if encoder_path:
            command.extend(["--encoder-path", str(Path(encoder_path))])
        if standard_codec_path:
            command.extend(["--standard-codec-path", str(Path(standard_codec_path))])
        if config.vieneu_tts_offline:
            command.append("--offline")
        env = os.environ.copy()
        if config.vieneu_tts_offline:
            env["HF_HUB_OFFLINE"] = "1"
            env["TRANSFORMERS_OFFLINE"] = "1"
            env["HF_DATASETS_OFFLINE"] = "1"
        import_root = _vieneu_import_root(Path(config.vieneu_tts_path))
        env["PYTHONPATH"] = str(import_root) + os.pathsep + env.get("PYTHONPATH", "")
        self._process = subprocess.Popen(
            command,
            cwd=str(PROJECT_ROOT),
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
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

        def read_stdout() -> None:
            stdout = self._process.stdout if self._process is not None else None
            if stdout is None:
                self._output_queue.put(None)
                return
            try:
                for raw_line in iter(stdout.readline, b""):
                    line = raw_line.decode("utf-8", errors="replace") if isinstance(raw_line, bytes) else raw_line
                    self._output_queue.put(line)
            finally:
                self._output_queue.put(None)

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
    candidates: list[AppConfig] = [config]
    requested_mode = normalize_vieneu_mode(config.vieneu_tts_mode)
    effective_mode = resolve_vieneu_effective_mode(
        config.vieneu_tts_core,
        config.vieneu_tts_mode,
        config.vieneu_tts_device,
    )
    if effective_mode == "remote":
        return candidates
    cuda_available = _runtime_has_cuda()

    if requested_mode == "standard":
        if cuda_available:
            candidates.extend(
                [
                    replace(
                        config,
                        vieneu_tts_mode="standard",
                        vieneu_tts_model_name=INTERNAL_VIENEU_STANDARD_GGUF,
                        vieneu_tts_device="cuda",
                        vieneu_tts_backend="lmdeploy",
                    ),
                    replace(
                        config,
                        vieneu_tts_mode="standard",
                        vieneu_tts_model_name=INTERNAL_VIENEU_STANDARD_GGUF,
                        vieneu_tts_device="cuda",
                        vieneu_tts_backend="native",
                    ),
                ]
            )
        candidates.append(
            replace(
                config,
                vieneu_tts_mode="standard",
                vieneu_tts_model_name=INTERNAL_VIENEU_STANDARD_GGUF,
                vieneu_tts_device="cpu",
                vieneu_tts_backend="native",
            )
        )

    if cuda_available:
        candidates.append(
            replace(
                config,
                vieneu_tts_mode="turbo",
                vieneu_tts_model_name=INTERNAL_VIENEU_TURBO_GGUF,
                vieneu_tts_device="cuda",
                vieneu_tts_backend="native",
            )
        )
    candidates.append(
        replace(
            config,
            vieneu_tts_mode="turbo",
            vieneu_tts_model_name=INTERNAL_VIENEU_TURBO_GGUF,
            vieneu_tts_device="cpu",
            vieneu_tts_backend="native",
        )
    )
    return _unique_vieneu_configs(candidates)


def _unique_vieneu_configs(configs: list[AppConfig]) -> list[AppConfig]:
    unique: list[AppConfig] = []
    seen: set[tuple[str, ...]] = set()
    for config in configs:
        key = _vieneu_server_config_key(config)
        if key in seen:
            continue
        seen.add(key)
        unique.append(config)
    return unique


def _vieneu_server_config_key(config: AppConfig) -> tuple[str, ...]:
    mode = resolve_vieneu_effective_mode(
        config.vieneu_tts_core,
        config.vieneu_tts_mode,
        config.vieneu_tts_device,
    )
    device = resolve_vieneu_runtime_device(config.vieneu_tts_device)
    model_name = _resolve_vieneu_model_name(config.vieneu_tts_model_name, mode)
    backend = resolve_vieneu_runtime_backend(mode, model_name, device, config.vieneu_tts_backend)
    return (
        mode,
        device,
        backend,
        model_name,
        str(config.vieneu_tts_api_base or ""),
        str(Path(_effective_vieneu_decoder_path(config))),
        str(Path(_effective_vieneu_encoder_path(config))),
        str(Path(_effective_vieneu_standard_codec_path(config))),
        str(config.vieneu_tts_runtime),
        str(config.vieneu_tts_offline),
    )


def _vieneu_config_label(config: AppConfig) -> str:
    mode = resolve_vieneu_effective_mode(
        config.vieneu_tts_core,
        config.vieneu_tts_mode,
        config.vieneu_tts_device,
    )
    device = resolve_vieneu_runtime_device(config.vieneu_tts_device)
    model_name = _resolve_vieneu_model_name(config.vieneu_tts_model_name, mode)
    backend = resolve_vieneu_runtime_backend(mode, model_name, device, config.vieneu_tts_backend)
    return f"mode={mode}, device={device}, backend={backend}"


def _compatible_vieneu_voice_id(config: AppConfig, voice_id: str) -> str:
    voices = vieneu_voices(config)
    choices = tuple((voice.name, voice.id) for voice in voices)
    migrated = migrate_vieneu_legacy_voice_id(voice_id, choices)
    available_ids = {voice.id for voice in voices}
    if migrated in available_ids:
        return migrated
    gender = voice_gender("vieneu", voice_id)
    if gender in {"male", "female"}:
        for preferred in _preferred_vieneu_voice_ids(config, gender):
            if preferred in available_ids:
                return preferred
        for voice in voices:
            if voice_gender("vieneu", voice.id) == gender:
                return voice.id
    return voices[0].id if voices else voice_id


def _runtime_has_cuda() -> bool:
    try:
        import torch

        return bool(torch.cuda.is_available())
    except Exception:
        return False


def _get_vieneu_engine(config: AppConfig):
    root = Path(config.vieneu_tts_path)
    import_root = _vieneu_import_root(root)
    if import_root.exists() and str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

    selected_mode = resolve_vieneu_effective_mode(
        config.vieneu_tts_core,
        config.vieneu_tts_mode,
        config.vieneu_tts_device,
    )
    device = resolve_vieneu_runtime_device(config.vieneu_tts_device)
    model_name = _resolve_vieneu_model_name(config.vieneu_tts_model_name, selected_mode)
    _validate_vieneu_local_files(config, selected_mode, model_name)
    backend = resolve_vieneu_runtime_backend(
        selected_mode,
        model_name,
        device,
        config.vieneu_tts_backend,
    )
    api_base = str(config.vieneu_tts_api_base or "").strip()
    if selected_mode != "remote":
        api_base = ""
    decoder_path = _effective_vieneu_decoder_path(config)
    encoder_path = _effective_vieneu_encoder_path(config)
    standard_codec_path = _effective_vieneu_standard_codec_path(config)

    cache_key = (
        str(root.resolve()) if root.exists() else str(root),
        selected_mode,
        api_base,
        model_name,
        str(Path(decoder_path)) if decoder_path else "",
        str(Path(encoder_path)) if encoder_path else "",
        str(Path(standard_codec_path)) if standard_codec_path else "",
        device,
        backend,
    )
    cached = _VIENEU_ENGINE_CACHE.get(cache_key)
    if cached is not None:
        return cached

    with _VIENEU_ENGINE_LOCK:
        cached = _VIENEU_ENGINE_CACHE.get(cache_key)
        if cached is not None:
            return cached

        try:
            from vieneu import Vieneu
        except ImportError as exc:
            raise TTSError(
                "Kh\u00f4ng import \u0111\u01b0\u1ee3c VieNeu-TTS n\u1ed9i b\u1ed9. Ch\u1ea1y "
                ".\\.venv\\Scripts\\python.exe -m pip install -r requirements.txt "
                "\u0111\u1ec3 c\u00e0i dependency, r\u1ed3i ch\u1ea1y "
                "scripts\\download_vieneu_tts_models.ps1 n\u1ebfu thi\u1ebfu model."
            ) from exc

        kwargs = _build_vieneu_engine_kwargs(
            mode=selected_mode,
            api_base=api_base,
            model_name=model_name,
            decoder_path=_effective_vieneu_decoder_path(config),
            encoder_path=_effective_vieneu_encoder_path(config),
            standard_codec_path=_effective_vieneu_standard_codec_path(config),
            device=device,
            backend=backend,
        )
        offline_env = push_hf_offline_environment(config.vieneu_tts_offline)
        try:
            engine = Vieneu(mode=selected_mode, **kwargs)
        except Exception as exc:
            raise TTSError(
                "Kh\u00f4ng kh\u1edfi t\u1ea1o \u0111\u01b0\u1ee3c VieNeu-TTS "
                f"(mode={selected_mode}, model={model_name}, device={device}, backend={backend}): {exc}"
            ) from exc
        finally:
            pop_hf_offline_environment(offline_env)
        _VIENEU_ENGINE_CACHE[cache_key] = engine
        return engine


def _build_vieneu_engine_kwargs(
    *,
    mode: str,
    api_base: str,
    model_name: str,
    device: str,
    backend: str,
    decoder_path: str = "",
    encoder_path: str = "",
    standard_codec_path: str = "",
) -> dict[str, Any]:
    kwargs: dict[str, Any] = {}
    if mode == "remote":
        if api_base:
            kwargs["api_base"] = api_base
        if model_name:
            kwargs["model_name"] = model_name
        kwargs["codec_repo"] = _VIENEU_REMOTE_CODEC_REPO
        kwargs["codec_device"] = "cpu"
        return kwargs

    if model_name:
        kwargs["backbone_repo"] = _resolve_local_gguf_if_dir(model_name)

    runtime_device = "cuda" if device == "cuda" else "cpu"
    if mode == "standard":
        kwargs["backbone_device"] = runtime_device
        kwargs["codec_device"] = runtime_device
        if standard_codec_path:
            kwargs["codec_repo"] = _resolve_existing_dir(standard_codec_path)
    else:
        if decoder_path:
            kwargs["decoder_repo"] = _resolve_existing_file(decoder_path)
        if encoder_path:
            kwargs["encoder_repo"] = _resolve_existing_file(encoder_path)
        kwargs["device"] = runtime_device
        if mode in {"fast", "turbo_gpu"} and backend:
            kwargs["backend"] = backend
    return kwargs


def _resolve_vieneu_model_name(value: object, mode: str) -> str:
    clean = str(value or "").strip()
    if clean:
        return clean
    if mode == "standard":
        return "pnnbao-ump/VieNeu-TTS"
    if mode == "remote":
        return "pnnbao-ump/VieNeu-TTS"
    return "pnnbao-ump/VieNeu-TTS-v2-Turbo-GGUF"


def _resolve_local_gguf_if_dir(model_name: str) -> str:
    path = Path(model_name)
    if not path.exists() or not path.is_dir():
        return model_name
    candidates = sorted(
        [item for item in path.iterdir() if item.is_file() and item.suffix.lower() == ".gguf"],
        key=lambda item: item.name.lower(),
    )
    return str(candidates[0].resolve()) if candidates else model_name


def _resolve_existing_file(value: str) -> str:
    path = Path(value)
    return str(path.resolve()) if path.exists() and path.is_file() else value


def _resolve_existing_dir(value: str) -> str:
    path = Path(value)
    return str(path.resolve()) if path.exists() and path.is_dir() else value


def _effective_vieneu_decoder_path(config: AppConfig) -> str:
    configured = str(config.vieneu_tts_decoder_path or "").strip()
    if configured and Path(configured).exists():
        return configured
    return INTERNAL_VIENEU_TURBO_DECODER if Path(INTERNAL_VIENEU_TURBO_DECODER).exists() else configured


def _effective_vieneu_encoder_path(config: AppConfig) -> str:
    configured = str(config.vieneu_tts_encoder_path or "").strip()
    if configured and Path(configured).exists():
        return configured
    return INTERNAL_VIENEU_TURBO_ENCODER if Path(INTERNAL_VIENEU_TURBO_ENCODER).exists() else configured


def _effective_vieneu_standard_codec_path(config: AppConfig) -> str:
    configured = str(config.vieneu_tts_standard_codec_path or "").strip()
    if configured and Path(configured).exists():
        return configured
    return INTERNAL_VIENEU_STANDARD_CODEC if Path(INTERNAL_VIENEU_STANDARD_CODEC).exists() else configured


def _local_vieneu_standard_models() -> list[VieNeuModelOption]:
    standard_dir = INTERNAL_VIENEU_STANDARD_PATH
    if not standard_dir.exists():
        return []
    models: list[VieNeuModelOption] = []
    for path in sorted(standard_dir.glob("*.gguf"), key=lambda item: item.name.lower()):
        models.append(VieNeuModelOption(str(path.resolve()), f"{path.stem} (local offline)", True))
    return models


def _local_vieneu_turbo_models() -> list[VieNeuModelOption]:
    turbo_dir = INTERNAL_VIENEU_TURBO_PATH
    if not turbo_dir.exists():
        return []
    return [
        VieNeuModelOption(str(path.resolve()), f"{path.stem} (local offline)", True)
        for path in sorted(turbo_dir.glob("*.gguf"), key=lambda item: item.name.lower())
    ]


def _unique_vieneu_models(models: list[VieNeuModelOption]) -> list[VieNeuModelOption]:
    seen: set[str] = set()
    unique: list[VieNeuModelOption] = []
    for model in models:
        if model.id in seen:
            continue
        seen.add(model.id)
        unique.append(model)
    return unique


def _validate_vieneu_local_files(config: AppConfig, mode: str, model_name: str) -> None:
    if mode == "remote" or not config.vieneu_tts_offline:
        return

    required = [("model", model_name)]
    if mode != "standard":
        required.extend(
            [
                ("decoder", _effective_vieneu_decoder_path(config)),
                ("encoder", _effective_vieneu_encoder_path(config)),
            ]
        )
    else:
        required.append(
            (
                "standard codec",
                str(Path(_effective_vieneu_standard_codec_path(config)) / "pytorch_model.bin"),
            )
        )

    missing = [f"{label}: {path}" for label, path in required if path and not Path(path).exists()]
    if missing:
        details = "\n".join(missing)
        raise TTSError(
            "Thi\u1ebfu file VieNeu-TTS offline. Ch\u1ea1y scripts\\download_vieneu_tts_models.ps1 "
            f"\u0111\u1ec3 t\u1ea3i \u0111\u1ea7y \u0111\u1ee7 model/cache.\n{details}"
        )


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
    mode = resolve_vieneu_effective_mode(
        config.vieneu_tts_core,
        config.vieneu_tts_mode,
        config.vieneu_tts_device,
    )
    if mode == "remote":
        api_base = str(config.vieneu_tts_api_base or "http://localhost:23333/v1")
        return f"VieNeu remote API kh\u00f4ng tr\u1ea3 v\u1ec1 audio. Ki\u1ec3m tra server/API t\u1ea1i {api_base}."
    return "VieNeu-TTS tr\u1ea3 v\u1ec1 audio r\u1ed7ng."


def _resolve_vieneu_preset_voice(engine: Any, voice_id: str) -> Any | None:
    raw = str(voice_id or "").strip()
    if not raw:
        return None
    try:
        return engine.get_preset_voice(raw)
    except Exception:
        pass

    try:
        available = tuple(engine.list_preset_voices() or ())
    except Exception:
        available = tuple()
    migrated = migrate_vieneu_legacy_voice_id(raw, available)
    if migrated and migrated != raw:
        return engine.get_preset_voice(migrated)

    normalized = _normalize_voice_token(raw)
    for label, preset_id in available:
        clean_id = str(preset_id or "").strip()
        clean_label = str(label or clean_id).strip()
        if normalized in {
            _normalize_voice_token(clean_id),
            _normalize_voice_token(clean_label),
            _normalize_voice_token(clean_label.split("(", 1)[0].strip()),
        }:
            return engine.get_preset_voice(clean_id)

    available_ids = ", ".join(str(preset_id) for _label, preset_id in available)
    empty_label = "(tr\u1ed1ng)"
    raise TTSError(
        f"Kh\u00f4ng t\u00ecm th\u1ea5y voice VieNeu {voice_id!r}. "
        f"C\u00e1c voice hi\u1ec7n c\u00f3: {available_ids or empty_label}"
    )

def _preferred_vieneu_voice_ids(config: AppConfig, gender: str) -> tuple[str, ...]:
    mode = resolve_vieneu_effective_mode(
        config.vieneu_tts_core,
        config.vieneu_tts_mode,
        config.vieneu_tts_device,
    )
    if mode in {"standard", "remote"}:
        return ("Vinh", "Binh", "Tuyen") if gender == "male" else ("Doan", "Ngoc", "Ly")
    return (
        ("Xu\u00e2n V\u0129nh", "Ph\u1ea1m Tuy\u00ean", "Xuan Vinh", "Pham Tuyen")
        if gender == "male"
        else ("Th\u1ee5c \u0110oan", "B\u00edch Ng\u1ecdc", "Thuc Doan", "Bich Ngoc")
    )

def _vieneu_import_root(root: Path) -> Path:
    if (root / "src" / "vieneu").exists():
        return root / "src"
    if (root / "vieneu").exists():
        return root
    bundled = Path(INTERNAL_VIENEU_TTS_PATH)
    if (bundled / "vieneu").exists():
        return bundled
    return root


def vieneu_voices(config: AppConfig | None) -> list[VoiceOption]:
    if config is None:
        return STANDARD_VIENEU_VOICES

    mode = resolve_vieneu_effective_mode(
        config.vieneu_tts_core,
        config.vieneu_tts_mode,
        config.vieneu_tts_device,
    )
    if mode == "remote":
        return STANDARD_VIENEU_VOICES
    model_voices_path = _vieneu_model_voices_path(config.vieneu_tts_model_name)
    if model_voices_path.is_file():
        voices = _read_vieneu_voices(model_voices_path)
        if voices:
            return voices

    if mode == "standard":
        import_root = _vieneu_import_root(Path(config.vieneu_tts_path))
        voices_path = import_root / "vieneu" / "assets" / "voices.json"
        if voices_path.is_file():
            voices = _read_vieneu_voices(voices_path)
            if voices:
                return voices

    return STANDARD_VIENEU_VOICES if mode in {"standard", "remote"} else TURBO_VIENEU_VOICES

