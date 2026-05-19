from __future__ import annotations

import asyncio
import importlib.util
import inspect
import json
import os
import queue
import subprocess
import sys
import threading
import time
import unicodedata
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import edge_tts

from ai_player.core.config import (
    INTERNAL_VIENEU_STANDARD_GGUF,
    INTERNAL_VIENEU_STANDARD_PATH,
    INTERNAL_VIENEU_TURBO_GGUF,
    INTERNAL_VIENEU_TURBO_PATH,
    PROJECT_ROOT,
    AppConfig,
)
from ai_player.core.offline_env import pop_hf_offline_environment, push_hf_offline_environment


@dataclass(frozen=True)
class VoiceOption:
    id: str
    name: str


@dataclass(frozen=True)
class VieNeuModelOption:
    id: str
    name: str
    offline: bool


class TTSError(RuntimeError):
    pass


EDGE_VOICES = [
    VoiceOption("vi-VN-HoaiMyNeural", "Hoài My (nữ, Việt Nam)"),
    VoiceOption("vi-VN-NamMinhNeural", "Nam Minh (nam, Việt Nam)"),
]

STANDARD_VIENEU_VOICES = [
    VoiceOption("Binh", "Bình (nam miền Bắc)"),
    VoiceOption("Tuyen", "Tuyên (nam miền Bắc)"),
    VoiceOption("Ngoc", "Ngọc (nữ miền Bắc)"),
    VoiceOption("Ly", "Ly (nữ miền Bắc)"),
    VoiceOption("Vinh", "Vĩnh (nam miền Nam)"),
    VoiceOption("Doan", "Đoan (nữ miền Nam)"),
]

TURBO_VIENEU_VOICES = [
    VoiceOption("Bích Ngọc", "Bích Ngọc (nữ miền Bắc)"),
    VoiceOption("Phạm Tuyên", "Phạm Tuyên (nam miền Bắc)"),
    VoiceOption("Thục Đoan", "Thục Đoan (nữ miền Nam)"),
    VoiceOption("Xuân Vĩnh", "Xuân Vĩnh (nam miền Nam)"),
]

_VIENEU_ENGINE_LOCK = threading.Lock()
_VIENEU_ENGINE_CACHE: dict[tuple[str, ...], Any] = {}


def available_tts_providers() -> list[VoiceOption]:
    return [
        VoiceOption("none", "Không TTS"),
        VoiceOption("vieneu", "VieNeu-TTS"),
        VoiceOption("edge", "Edge TTS"),
    ]


def available_vieneu_modes() -> list[VoiceOption]:
    return [
        VoiceOption("turbo", "Turbo"),
        VoiceOption("standard", "Standard"),
    ]


def available_vieneu_models(mode: str, config: AppConfig) -> list[VieNeuModelOption]:
    selected_mode = normalize_vieneu_mode(mode)
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


def available_voices(provider: str, config: AppConfig | None = None) -> list[VoiceOption]:
    normalized_provider = normalize_tts_provider(provider)
    if normalized_provider == "none":
        return [VoiceOption("none", "Không TTS")]
    if normalized_provider == "vieneu":
        return _vieneu_voices(config)
    return EDGE_VOICES


def select_voice_for_gender(provider: str, config: AppConfig, gender: str) -> str:
    requested_gender = str(gender or "unknown").strip().lower()
    if requested_gender not in {"male", "female"}:
        return config.tts_voice

    voices = available_voices(provider, config)
    available_ids = {voice.id for voice in voices}
    configured_voice = config.tts_male_voice if requested_gender == "male" else config.tts_female_voice
    if configured_voice in available_ids:
        return configured_voice
    migrated_voice = migrate_vieneu_legacy_voice_id(
        configured_voice,
        tuple((voice.name, voice.id) for voice in voices),
    )
    if migrated_voice in available_ids:
        return migrated_voice

    current_gender = voice_gender(provider, config.tts_voice)
    if current_gender == requested_gender:
        return config.tts_voice

    preferred = _preferred_voice_ids(provider, config, requested_gender)
    for voice_id in preferred:
        if voice_id in available_ids:
            return voice_id

    for voice in voices:
        if voice_gender(provider, voice.id) == requested_gender:
            return voice.id
    return config.tts_voice


def voice_gender(provider: str, voice_id: object) -> str:
    normalized = _normalize_voice_token(voice_id)
    if normalize_tts_provider(provider) == "edge":
        if "namminh" in normalized or "nam minh" in normalized:
            return "male"
        if "hoai my" in normalized or "hoaimy" in normalized:
            return "female"

    female_tokens = {
        "doan",
        "thuc doan",
        "ngoc",
        "bich ngoc",
        "ly",
        "hoai my",
        "hoaimy",
    }
    male_tokens = {
        "binh",
        "tuyen",
        "pham tuyen",
        "vinh",
        "xuan vinh",
        "nam minh",
        "namminh",
    }
    if normalized in female_tokens or any(token in normalized for token in female_tokens):
        return "female"
    if normalized in male_tokens or any(token in normalized for token in male_tokens):
        return "male"
    return "unknown"


def create_tts_provider(config: AppConfig) -> BaseTTSProvider:
    provider = normalize_tts_provider(config.tts_provider)
    if provider == "none":
        return NoTTSProvider(config)
    if provider == "vieneu":
        return VieNeuTTSProvider(config)
    return EdgeTTSProvider(config)


def normalize_tts_provider(value: object) -> str:
    raw = str(value or "").strip().lower().replace("-", "").replace("_", "").replace(" ", "")
    if raw in {"vieneu", "vieneutts", "vieneucore", "local", "offline"}:
        return "vieneu"
    if raw in {"edge", "edgetts", "edgecli"}:
        return "edge"
    if raw in {"none", "off", "notts", "no_tts", "khongtts", "khong_tts"}:
        return "none"
    return "vieneu"


def normalize_vieneu_mode(value: object) -> str:
    raw = str(value or "turbo").strip().lower().replace("-", "_")
    aliases = {
        "local": "turbo",
        "default": "turbo",
        "turbo": "turbo",
        "standard": "standard",
        "remote": "remote",
        "api": "remote",
        "remote_api": "remote",
        "fast": "fast",
        "gpu": "fast",
        "cuda": "fast",
        "turbo_gpu": "turbo_gpu",
        "xpu": "xpu",
    }
    if raw in aliases:
        return aliases[raw]
    raise TTSError(f"VieNeu mode không hợp lệ: {value!r}")


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
    selected_core = str(core or "local").strip().lower().replace("-", "_").replace(" ", "_")
    selected_mode = normalize_vieneu_mode(mode)
    if selected_core in {"remote", "remote_api", "api", "remoteapi"}:
        return "remote"
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


class EdgeTTSProvider(BaseTTSProvider):
    def __init__(self, config: AppConfig) -> None:
        self._voice = config.tts_voice

    def synthesize(self, text: str, output_path: Path, voice: str | None = None) -> None:
        asyncio.run(self._synthesize(text, output_path, voice or self._voice))

    async def _synthesize(self, text: str, output_path: Path, voice: str) -> None:
        communicate = edge_tts.Communicate(text, voice)
        await communicate.save(str(output_path))


class VieNeuTTSProvider(BaseTTSProvider):
    def __init__(self, config: AppConfig) -> None:
        self._config = config
        self._server: VieNeuServerClient | None = None

    def synthesize(self, text: str, output_path: Path, voice: str | None = None) -> None:
        clean_text = _clean_text(text)
        if not clean_text:
            raise TTSError("VieNeu-TTS không thể đọc văn bản rỗng.")

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
        raise TTSError(f"VieNeu-TTS không chạy được sau khi tự hạ cấu hình.\n{details}")

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
            output_path.parent.mkdir(parents=True, exist_ok=True)
            engine.save(audio, str(output_path))
        except Exception as exc:
            raise TTSError(
                "VieNeu-TTS không tạo được audio "
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
            self._reset_server()
            self._server = VieNeuServerClient(config)
        self._server.synthesize(
            text=text,
            voice=voice_id,
            output_path=output_path,
            temperature=config.vieneu_tts_temperature,
            max_chars=config.vieneu_tts_max_chars_chunk,
        )

    def _should_use_subprocess(self, config: AppConfig) -> bool:
        runtime = str(config.vieneu_tts_runtime or "auto").strip().lower()
        return runtime == "subprocess" or (runtime == "auto" and self._can_use_subprocess(config))

    def _can_use_subprocess(self, config: AppConfig) -> bool:
        python = Path(config.vieneu_tts_python)
        return python.exists() and _vieneu_import_root(Path(config.vieneu_tts_path)).exists()

    def close(self) -> None:
        self._reset_server()

    def _reset_server(self) -> None:
        if self._server is not None:
            self._server.close()
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
        if config.vieneu_tts_decoder_path:
            command.extend(["--decoder-path", str(Path(config.vieneu_tts_decoder_path))])
        if config.vieneu_tts_encoder_path:
            command.extend(["--encoder-path", str(Path(config.vieneu_tts_encoder_path))])
        if config.vieneu_tts_standard_codec_path:
            command.extend(["--standard-codec-path", str(Path(config.vieneu_tts_standard_codec_path))])
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
                return json.loads(clean_line[marker_index + len(marker) :])
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


def _vieneu_fallback_configs(config: AppConfig) -> list[AppConfig]:
    candidates: list[AppConfig] = [config]
    requested_mode = normalize_vieneu_mode(config.vieneu_tts_mode)
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
        str(Path(config.vieneu_tts_decoder_path)),
        str(Path(config.vieneu_tts_encoder_path)),
        str(Path(config.vieneu_tts_standard_codec_path)),
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
    voices = available_voices("vieneu", config)
    choices = tuple((voice.name, voice.id) for voice in voices)
    migrated = migrate_vieneu_legacy_voice_id(voice_id, choices)
    available_ids = {voice.id for voice in voices}
    if migrated in available_ids:
        return migrated
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

    cache_key = (
        str(root.resolve()) if root.exists() else str(root),
        selected_mode,
        api_base,
        model_name,
        str(Path(config.vieneu_tts_decoder_path)) if config.vieneu_tts_decoder_path else "",
        str(Path(config.vieneu_tts_encoder_path)) if config.vieneu_tts_encoder_path else "",
        str(Path(config.vieneu_tts_standard_codec_path)) if config.vieneu_tts_standard_codec_path else "",
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
                "Không import được VieNeu-TTS nội bộ. Chạy scripts\\setup_vieneu_tts.ps1 "
                "để cài dependency cho module ai_player\\vieneu_tts."
            ) from exc

        kwargs = _build_vieneu_engine_kwargs(
            mode=selected_mode,
            api_base=api_base,
            model_name=model_name,
            decoder_path=config.vieneu_tts_decoder_path,
            encoder_path=config.vieneu_tts_encoder_path,
            standard_codec_path=config.vieneu_tts_standard_codec_path,
            device=device,
            backend=backend,
        )
        offline_env = push_hf_offline_environment(config.vieneu_tts_offline)
        try:
            engine = Vieneu(mode=selected_mode, **kwargs)
        except Exception as exc:
            raise TTSError(
                "Không khởi tạo được VieNeu-TTS "
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
                ("decoder", config.vieneu_tts_decoder_path),
                ("encoder", config.vieneu_tts_encoder_path),
            ]
        )
    else:
        required.append(
            (
                "standard codec",
                str(Path(config.vieneu_tts_standard_codec_path) / "pytorch_model.bin"),
            )
        )

    missing = [f"{label}: {path}" for label, path in required if path and not Path(path).exists()]
    if missing:
        details = "\n".join(missing)
        raise TTSError(
            "Thiếu file VieNeu-TTS offline. Chạy scripts\\download_vieneu_tts_models.ps1 "
            f"để tải đầy đủ model/cache.\n{details}"
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
        "temperature": float(temperature),
        "max_chars": max(1, int(max_chars)),
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
    raise TTSError(f"Không tìm thấy voice VieNeu {voice_id!r}. Các voice hiện có: {available_ids or '(trống)'}")


def migrate_vieneu_legacy_voice_id(
    voice_id: object,
    available_choices: list[tuple[str, str]] | tuple[tuple[str, str], ...],
) -> str:
    raw = str(voice_id or "").strip()
    normalized = _normalize_voice_token(raw)
    if not normalized:
        return raw

    entries = []
    for label, preset_id in tuple(available_choices or ()):
        clean_id = str(preset_id or "").strip()
        clean_label = str(label or clean_id).strip()
        if clean_id:
            entries.append((clean_id, _normalize_voice_token(clean_id), _normalize_voice_token(clean_label)))

    for clean_id, norm_id, norm_label in entries:
        if normalized in {norm_id, norm_label, _normalize_voice_token(norm_label.split("(", 1)[0])}:
            return clean_id

    hints = {
        "binh": ("binh", "nam", "bac"),
        "tuyen": ("tuyen", "nam", "bac"),
        "ngoc": ("ngoc", "nu", "bac"),
        "ly": ("ly", "nu", "bac"),
        "vinh": ("vinh", "nam", "nam"),
        "doan": ("doan", "nu", "nam"),
    }.get(normalized)
    if not hints:
        return raw

    ranked: list[tuple[int, str]] = []
    for clean_id, norm_id, norm_label in entries:
        haystack = f"{norm_id} {norm_label}"
        score = sum(1 for hint in hints if hint in haystack)
        if score:
            ranked.append((score, clean_id))
    if ranked:
        ranked.sort(key=lambda item: (-item[0], item[1]))
        return ranked[0][1]
    return raw


def _strip_accents(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    return "".join(ch for ch in text if not unicodedata.combining(ch))


def _preferred_voice_ids(provider: str, config: AppConfig, gender: str) -> tuple[str, ...]:
    if normalize_tts_provider(provider) == "edge":
        return ("vi-VN-NamMinhNeural",) if gender == "male" else ("vi-VN-HoaiMyNeural",)

    mode = resolve_vieneu_effective_mode(
        config.vieneu_tts_core,
        config.vieneu_tts_mode,
        config.vieneu_tts_device,
    )
    if mode == "standard":
        return ("Binh", "Tuyen", "Vinh") if gender == "male" else ("Doan", "Ngoc", "Ly")
    return (
        ("Phạm Tuyên", "Xuân Vĩnh", "Pham Tuyen", "Xuan Vinh")
        if gender == "male"
        else ("Thục Đoan", "Bích Ngọc", "Thuc Doan", "Bich Ngoc")
    )


def _normalize_voice_token(value: object) -> str:
    text = _strip_accents(value).replace("đ", "d").replace("Đ", "D")
    return " ".join(text.strip().lower().split())


def _clean_message(value: object) -> str:
    return str(value or "").encode("utf-8", errors="replace").decode("utf-8", errors="replace")


def _clean_text(value: object) -> str:
    text = str(value or "").encode("utf-8", errors="replace").decode("utf-8", errors="replace")
    return " ".join(text.split())


def _vieneu_import_root(root: Path) -> Path:
    if (root / "src" / "vieneu").exists():
        return root / "src"
    return root


def _vieneu_voices(config: AppConfig | None) -> list[VoiceOption]:
    if config is None:
        return STANDARD_VIENEU_VOICES

    mode = resolve_vieneu_effective_mode(
        config.vieneu_tts_core,
        config.vieneu_tts_mode,
        config.vieneu_tts_device,
    )
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

    return STANDARD_VIENEU_VOICES if mode == "standard" else TURBO_VIENEU_VOICES


def _vieneu_model_voices_path(model_name: str) -> Path:
    model_path = Path(str(model_name or ""))
    if model_path.exists() and model_path.is_dir():
        return model_path / "voices.json"
    if model_path.exists() and model_path.is_file():
        return model_path.parent / "voices.json"
    return Path()


def _read_vieneu_voices(voices_path: Path) -> list[VoiceOption]:
    try:
        data = json.loads(voices_path.read_text(encoding="utf-8-sig"))
        presets = data.get("presets", {})
        return [
            VoiceOption(str(voice_id), str(preset.get("description") or voice_id))
            for voice_id, preset in presets.items()
            if isinstance(preset, dict)
        ]
    except Exception:
        return []
