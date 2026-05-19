from __future__ import annotations

import os
import subprocess
import threading
import wave
from pathlib import Path
from typing import Protocol

import numpy as np

from ai_player.services.ffmpeg import ffplay_executable


class AudioPlaybackHandle(Protocol):
    def poll(self) -> int | None:
        raise NotImplementedError

    def terminate(self) -> None:
        raise NotImplementedError

    def kill(self) -> None:
        raise NotImplementedError

    def wait(self, timeout: float | None = None) -> int:
        raise NotImplementedError


class ProcessAudioPlaybackHandle:
    def __init__(self, process: subprocess.Popen) -> None:
        self._process = process

    def poll(self) -> int | None:
        return self._process.poll()

    def terminate(self) -> None:
        self._process.terminate()

    def kill(self) -> None:
        self._process.kill()

    def wait(self, timeout: float | None = None) -> int:
        return self._process.wait(timeout=timeout)


class ThreadAudioPlaybackHandle:
    def __init__(self, thread: threading.Thread, stop_event: threading.Event) -> None:
        self._thread = thread
        self._stop_event = stop_event
        self._return_code: int | None = None

    def mark_finished(self, return_code: int) -> None:
        self._return_code = int(return_code)

    def poll(self) -> int | None:
        if self._thread.is_alive():
            return None
        return self._return_code if self._return_code is not None else 0

    def terminate(self) -> None:
        self._stop_event.set()

    def kill(self) -> None:
        self.terminate()

    def wait(self, timeout: float | None = None) -> int:
        self._thread.join(timeout=timeout)
        if self._thread.is_alive():
            raise TimeoutError("Audio playback thread did not stop before timeout.")
        return self.poll() or 0


def start_audio_playback(audio_path: Path, *, volume: int = 100) -> AudioPlaybackHandle:
    if _soundcard_playback_enabled() and audio_path.suffix.lower() == ".wav":
        handle = _start_soundcard_wav_playback(audio_path, volume=volume)
        if handle is not None:
            return handle
    return _start_ffplay(audio_path, volume=volume)


def _soundcard_playback_enabled() -> bool:
    return str(os.getenv("AI_PLAYER_SOUNDCARD_PLAYBACK", "1")).strip().lower() in {"1", "true", "yes", "on"}


def _start_soundcard_wav_playback(audio_path: Path, *, volume: int) -> ThreadAudioPlaybackHandle | None:
    if not _is_pcm_wav(audio_path):
        return None
    try:
        import soundcard as sc

        speaker = sc.default_speaker()
    except Exception:
        return None

    stop_event = threading.Event()
    handle_box: dict[str, ThreadAudioPlaybackHandle] = {}

    def run() -> None:
        return_code = 0
        try:
            _play_wav_with_soundcard(audio_path, volume=volume, stop_event=stop_event, speaker=speaker)
        except Exception:
            return_code = 1
        handle_box["handle"].mark_finished(return_code)

    thread = threading.Thread(target=run, name="ai-player-audio-playback", daemon=True)
    handle = ThreadAudioPlaybackHandle(thread, stop_event)
    handle_box["handle"] = handle
    thread.start()
    return handle


def _play_wav_with_soundcard(audio_path: Path, *, volume: int, stop_event: threading.Event, speaker) -> None:
    gain = max(0.0, min(1.0, float(volume) / 100.0))
    with wave.open(str(audio_path), "rb") as wav:
        sample_rate = wav.getframerate()
        channels = wav.getnchannels()
        sample_width = wav.getsampwidth()
        chunk_frames = max(256, min(sample_rate // 20 or 1024, 4096))
        with speaker.player(samplerate=sample_rate, channels=channels) as player:
            while not stop_event.is_set():
                frames = wav.readframes(chunk_frames)
                if not frames:
                    break
                data = _pcm_bytes_to_float32(frames, sample_width, channels)
                if gain != 1.0:
                    data *= gain
                player.play(data)


def _pcm_bytes_to_float32(frames: bytes, sample_width: int, channels: int) -> np.ndarray:
    if sample_width == 1:
        data = (np.frombuffer(frames, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
    elif sample_width == 2:
        data = np.frombuffer(frames, dtype="<i2").astype(np.float32) / 32768.0
    elif sample_width == 4:
        data = np.frombuffer(frames, dtype="<i4").astype(np.float32) / 2147483648.0
    else:
        raise ValueError(f"Unsupported WAV sample width: {sample_width}")
    if channels > 1:
        data = data.reshape(-1, channels)
    return np.clip(data, -1.0, 1.0)


def _is_pcm_wav(audio_path: Path) -> bool:
    try:
        with wave.open(str(audio_path), "rb") as wav:
            return wav.getcomptype() == "NONE" and wav.getsampwidth() in {1, 2, 4}
    except Exception:
        return False


def _start_ffplay(audio_path: Path, *, volume: int) -> ProcessAudioPlaybackHandle:
    command = [
        ffplay_executable(),
        "-nodisp",
        "-autoexit",
        "-loglevel",
        "quiet",
        "-volume",
        str(max(0, min(100, int(volume)))),
        str(audio_path),
    ]
    startupinfo = None
    if os.name == "nt":
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    process = subprocess.Popen(command, startupinfo=startupinfo)
    return ProcessAudioPlaybackHandle(process)
