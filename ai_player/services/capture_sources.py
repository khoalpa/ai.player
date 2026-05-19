from __future__ import annotations

import os
import re
import subprocess
import threading
import warnings
from pathlib import Path

import numpy as np
import soundfile as sf

CAPTURE_BACKENDS = {"auto", "soundcard", "ffmpeg"}


warnings.filterwarnings(
    "ignore",
    message=r"data discontinuity in recording",
)


def capture_microphone_audio(
    output_path: Path,
    duration_seconds: int,
    device_name: str = "",
    backend: str = "auto",
) -> None:
    backend = _normalize_capture_backend(backend)
    device = (
        device_name.strip()
        or os.getenv("AI_PLAYER_CAPTURE_MICROPHONE_DEVICE", "").strip()
        or os.getenv("AI_PLAYER_MICROPHONE_DEVICE", "").strip()
    )
    if backend in {"auto", "soundcard"} and _capture_soundcard_microphone(output_path, duration_seconds, device):
        return
    if backend == "soundcard":
        raise RuntimeError(
            "Soundcard khong capture duoc microphone. Thu Capture backend = Auto hoac FFmpeg DirectShow."
        )
    if not device:
        devices = list_dshow_audio_devices()
        if not devices:
            raise RuntimeError("Không tìm thấy microphone DirectShow nào. Kiểm tra quyền microphone của Windows.")
        device = devices[0]
    _capture_dshow_audio(device, output_path, duration_seconds, "microphone")


def capture_system_audio(
    output_path: Path,
    duration_seconds: int,
    device_name: str = "",
    backend: str = "auto",
) -> None:
    backend = _normalize_capture_backend(backend)
    device = (
        device_name.strip()
        or os.getenv("AI_PLAYER_CAPTURE_SYSTEM_DEVICE", "").strip()
        or os.getenv("AI_PLAYER_SYSTEM_AUDIO_DEVICE", "").strip()
    )
    if backend in {"auto", "soundcard"} and _capture_soundcard_loopback(output_path, duration_seconds, device):
        return
    if backend == "soundcard":
        raise RuntimeError(
            "Soundcard khong capture duoc am he thong. Thu Capture backend = Auto hoac FFmpeg DirectShow."
        )
    devices = list_dshow_audio_devices()
    if not device:
        device = _preferred_system_audio_device(devices)
    if not device:
        raise RuntimeError(
            "Không tìm thấy thiết bị âm hệ thống. Cài VB-CABLE/Screen Capture Recorder, "
            "bật Stereo Mix, hoặc đặt AI_PLAYER_SYSTEM_AUDIO_DEVICE đúng tên DirectShow."
        )
    _capture_dshow_audio(device, output_path, duration_seconds, "âm hệ thống")


def capture_meeting_audio_until_stopped(
    output_path: Path,
    stop_event: threading.Event,
    system_device_name: str = "",
    microphone_device_name: str = "",
    backend: str = "auto",
) -> None:
    backend = _normalize_capture_backend(backend)
    system_device_name = system_device_name or os.getenv("AI_PLAYER_CAPTURE_SYSTEM_DEVICE", "")
    microphone_device_name = microphone_device_name or os.getenv("AI_PLAYER_CAPTURE_MICROPHONE_DEVICE", "")
    if backend in {"auto", "soundcard"} and _capture_soundcard_meeting(
        output_path, stop_event, system_device_name, microphone_device_name
    ):
        return
    if backend == "soundcard":
        raise RuntimeError(
            "Soundcard khong capture duoc System + Micro. Thu Capture backend = Auto hoac FFmpeg DirectShow."
        )
    _capture_ffmpeg_meeting(output_path, stop_event, system_device_name, microphone_device_name)


def capture_system_microphone_audio(
    output_path: Path,
    duration_seconds: int,
    system_device_name: str = "",
    microphone_device_name: str = "",
    backend: str = "auto",
) -> None:
    stop_event = threading.Event()
    timer = threading.Timer(max(1, int(duration_seconds)), stop_event.set)
    timer.start()
    try:
        capture_meeting_audio_until_stopped(
            output_path,
            stop_event,
            system_device_name=system_device_name,
            microphone_device_name=microphone_device_name,
            backend=backend,
        )
    finally:
        stop_event.set()
        timer.cancel()


def list_capture_device_options() -> dict[str, list[str]]:
    dshow_devices = list_dshow_audio_devices()
    result = {
        "system": list(dict.fromkeys(dshow_devices)),
        "microphone": list(dict.fromkeys(dshow_devices)),
    }
    try:
        import soundcard as sc

        speakers = [speaker.name for speaker in sc.all_speakers()]
        microphones = [microphone.name for microphone in sc.all_microphones(include_loopback=False)]
        result["system"] = list(dict.fromkeys(speakers + result["system"]))
        result["microphone"] = list(dict.fromkeys(microphones + result["microphone"]))
    except Exception:
        pass
    return result


def _normalize_capture_backend(value: object) -> str:
    raw = str(value or "auto").strip().lower().replace("-", "_").replace(" ", "_")
    if raw in {"soundcard", "sc"}:
        return "soundcard"
    if raw in {"ffmpeg", "dshow", "directshow", "ffmpeg_dshow", "ffmpeg_directshow"}:
        return "ffmpeg"
    return "auto"


def list_dshow_audio_devices() -> list[str]:
    command = ["ffmpeg", "-hide_banner", "-f", "dshow", "-list_devices", "true", "-i", "dummy"]
    process = subprocess.run(command, capture_output=True, text=True, errors="replace")
    text = f"{process.stdout}\n{process.stderr}"
    devices: list[str] = []
    for line in text.splitlines():
        match = re.search(r'\[dshow @ [^\]]+\]\s+"(.+?)"\s+\(audio\)', line)
        if match:
            devices.append(match.group(1))
    return devices


def _preferred_system_audio_device(devices: list[str]) -> str:
    preferred_tokens = (
        "virtual-audio-capturer",
        "stereo mix",
        "what u hear",
        "wave out mix",
        "vb-audio",
        "cable output",
        "loopback",
    )
    for token in preferred_tokens:
        for device in devices:
            if token in device.casefold():
                return device
    return ""


def _capture_dshow_audio(device: str, output_path: Path, duration_seconds: int, label: str) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-f",
        "dshow",
        "-t",
        str(max(1, int(duration_seconds))),
        "-i",
        f"audio={device}",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-y",
        str(output_path),
    ]
    process = subprocess.run(command, capture_output=True, text=True, errors="replace")
    if process.returncode != 0:
        detail = (process.stderr or process.stdout or "").strip()
        raise RuntimeError(f"Khong capture duoc {label} tu '{device}'. {detail}")
    if not output_path.exists() or output_path.stat().st_size == 0:
        raise RuntimeError(f"Capture {label} không tạo được tệp audio.")


def _capture_soundcard_loopback(output_path: Path, duration_seconds: int, device_name: str) -> bool:
    try:
        import soundcard as sc

        speaker = _soundcard_speaker(sc, device_name)
        if speaker is None:
            return False
        microphone = sc.get_microphone(speaker.name, include_loopback=True)
        _record_soundcard_microphone(microphone, output_path, duration_seconds)
        return True
    except Exception:
        return False


def _capture_soundcard_microphone(output_path: Path, duration_seconds: int, device_name: str) -> bool:
    try:
        import soundcard as sc

        microphone = _soundcard_microphone(sc, device_name)
        if microphone is None:
            return False
        _record_soundcard_microphone(microphone, output_path, duration_seconds)
        return True
    except Exception:
        return False


def _soundcard_speaker(sc, device_name: str):
    if device_name:
        token = device_name.casefold()
        for speaker in sc.all_speakers():
            if token in speaker.name.casefold():
                return speaker
        return None
    return sc.default_speaker()


def _soundcard_microphone(sc, device_name: str):
    microphones = sc.all_microphones(include_loopback=False)
    if device_name:
        token = device_name.casefold()
        for microphone in microphones:
            if token in microphone.name.casefold():
                return microphone
        return None
    return sc.default_microphone()


def _record_soundcard_microphone(microphone, output_path: Path, duration_seconds: int) -> None:
    sample_rate = 16000
    frames = sample_rate * max(1, int(duration_seconds))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with microphone.recorder(samplerate=sample_rate, channels=1) as recorder:
        data = _soundcard_record_without_discontinuity_warning(recorder, frames)
    data = np.asarray(data, dtype=np.float32)
    if data.ndim > 1:
        data = data.mean(axis=1)
    sf.write(str(output_path), data, sample_rate)
    if not output_path.exists() or output_path.stat().st_size == 0:
        raise RuntimeError("Soundcard capture không tạo được file audio.")


def _soundcard_record_without_discontinuity_warning(recorder, frames: int):
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message=r"data discontinuity in recording",
        )
        return recorder.record(numframes=frames)


def _capture_soundcard_meeting(
    output_path: Path,
    stop_event: threading.Event,
    system_device_name: str,
    microphone_device_name: str,
) -> bool:
    try:
        import soundcard as sc

        speaker = _soundcard_speaker(sc, system_device_name.strip())
        microphone = _soundcard_microphone(sc, microphone_device_name.strip())
        if speaker is None or microphone is None:
            return False
        loopback = sc.get_microphone(speaker.name, include_loopback=True)
        system_chunks: list[np.ndarray] = []
        micro_chunks: list[np.ndarray] = []
        errors: list[Exception] = []
        sample_rate = 16000
        chunk_frames = sample_rate // 2

        def record_source(source, chunks: list[np.ndarray]) -> None:
            try:
                with source.recorder(samplerate=sample_rate, channels=1) as recorder:
                    while not stop_event.is_set():
                        chunk = np.asarray(
                            _soundcard_record_without_discontinuity_warning(recorder, chunk_frames),
                            dtype=np.float32,
                        )
                        if chunk.ndim > 1:
                            chunk = chunk.mean(axis=1)
                        chunks.append(chunk)
            except Exception as exc:
                errors.append(exc)

        threads = [
            threading.Thread(target=record_source, args=(loopback, system_chunks), daemon=True),
            threading.Thread(target=record_source, args=(microphone, micro_chunks), daemon=True),
        ]
        for thread in threads:
            thread.start()
        while not stop_event.is_set():
            stop_event.wait(0.2)
        for thread in threads:
            thread.join(timeout=2.0)
        if errors and not system_chunks and not micro_chunks:
            return False
        _write_mixed_audio(output_path, system_chunks, micro_chunks, sample_rate)
        return True
    except Exception:
        return False


def _capture_ffmpeg_meeting(
    output_path: Path,
    stop_event: threading.Event,
    system_device_name: str,
    microphone_device_name: str,
) -> None:
    import tempfile

    devices = list_dshow_audio_devices()
    system_device = system_device_name.strip() or os.getenv("AI_PLAYER_SYSTEM_AUDIO_DEVICE", "").strip()
    microphone_device = microphone_device_name.strip() or os.getenv("AI_PLAYER_MICROPHONE_DEVICE", "").strip()
    if not system_device:
        system_device = _preferred_system_audio_device(devices)
    if not microphone_device:
        microphone_device = devices[0] if devices else ""
    if not system_device or not microphone_device:
        raise RuntimeError("Không tìm thấy đủ thiết bị System và Micro để ghi meeting.")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="ai-player-meeting-") as temp_name:
        temp_dir = Path(temp_name)
        system_path = temp_dir / "system.wav"
        micro_path = temp_dir / "microphone.wav"
        processes = [
            _start_dshow_recording(system_device, system_path),
            _start_dshow_recording(microphone_device, micro_path),
        ]
        while not stop_event.is_set():
            stop_event.wait(0.2)
        for process in processes:
            if process.poll() is None:
                process.terminate()
        for process in processes:
            try:
                process.wait(timeout=5.0)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2.0)
        _mix_audio_files(system_path, micro_path, output_path)


def _start_dshow_recording(device: str, output_path: Path) -> subprocess.Popen:
    command = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-f",
        "dshow",
        "-i",
        f"audio={device}",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-y",
        str(output_path),
    ]
    startupinfo = None
    if os.name == "nt":
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    return subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, startupinfo=startupinfo)


def _mix_audio_files(system_path: Path, micro_path: Path, output_path: Path) -> None:
    inputs = [path for path in (system_path, micro_path) if path.exists() and path.stat().st_size > 0]
    if not inputs:
        raise RuntimeError("Meeting không tạo được audio System/Micro.")
    if len(inputs) == 1:
        command = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(inputs[0]),
            "-ac",
            "1",
            "-ar",
            "16000",
            "-y",
            str(output_path),
        ]
    else:
        command = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(inputs[0]),
            "-i",
            str(inputs[1]),
            "-filter_complex",
            "amix=inputs=2:duration=longest:normalize=0,volume=0.5",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-y",
            str(output_path),
        ]
    subprocess.run(command, check=True)
    if not output_path.exists() or output_path.stat().st_size == 0:
        raise RuntimeError("Meeting không tạo được tệp audio.")


def _write_mixed_audio(
    output_path: Path,
    system_chunks: list[np.ndarray],
    micro_chunks: list[np.ndarray],
    sample_rate: int,
) -> None:
    sources = []
    for chunks in (system_chunks, micro_chunks):
        if chunks:
            sources.append(np.concatenate(chunks).astype(np.float32))
    if not sources:
        raise RuntimeError("Meeting không ghi được audio.")
    max_len = max(len(source) for source in sources)
    padded = []
    for source in sources:
        if len(source) < max_len:
            source = np.pad(source, (0, max_len - len(source)))
        padded.append(source)
    mixed = np.mean(np.vstack(padded), axis=0).astype(np.float32)
    mixed = np.clip(mixed, -1.0, 1.0)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(output_path), mixed, sample_rate)
    if not output_path.exists() or output_path.stat().st_size == 0:
        raise RuntimeError("Meeting không tạo được tệp audio.")
