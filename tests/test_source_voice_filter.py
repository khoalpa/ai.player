from __future__ import annotations

import math
import shutil
import struct
import subprocess
import wave
from pathlib import Path

import pytest

from ai_player.services import source_voice_filter as filter_service
from ai_player.workers import player_window_workers
from ai_player.workers.player_window_workers import (
    SourceAudioFilterWorker,
    _format_process_exception,
    _process_executable_name,
)

FFMPEG = shutil.which("ffmpeg")
requires_ffmpeg = pytest.mark.skipif(FFMPEG is None, reason="ffmpeg is not available")


def test_normalize_source_voice_filter_mode_aliases() -> None:
    assert filter_service.normalize_source_voice_filter_mode("auto") == "fast"
    assert filter_service.normalize_source_voice_filter_mode("ffmpeg") == "fast"
    assert filter_service.normalize_source_voice_filter_mode("demucs") == "ai"
    assert filter_service.normalize_source_voice_filter_mode("unexpected") == "fast"


def test_fast_source_voice_filter_uses_ffmpeg(tmp_path) -> None:
    source = tmp_path / "demo.mp4"
    output = tmp_path / "filtered.mp4"
    source.write_bytes(b"source")
    commands: list[list[str]] = []

    def runner(command: list[str]) -> None:
        commands.append(command)
        Path(command[-1]).write_bytes(b"filtered")

    result = filter_service.apply_source_voice_filter(source, output, mode="fast", process_runner=runner)

    assert result.backend == "fast"
    assert output.exists()
    assert [command[0] for command in commands] == ["ffmpeg"]
    assert any("pan=stereo" in part for part in commands[0])


def test_fast_source_voice_filter_copies_safe_h264_video(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(filter_service, "_can_copy_video_stream", lambda _path: True)
    source = tmp_path / "demo.mp4"
    output = tmp_path / "filtered.mp4"
    source.write_bytes(b"source")
    commands: list[list[str]] = []

    def runner(command: list[str]) -> None:
        commands.append(command)
        Path(command[-1]).write_bytes(b"filtered")

    filter_service.apply_source_voice_filter(source, output, mode="fast", process_runner=runner)

    command = commands[0]
    assert command[command.index("-c:v") + 1] == "copy"
    assert "-vf" not in command


def test_old_auto_source_voice_filter_alias_uses_fast(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(filter_service, "demucs_available", lambda: True)
    source = tmp_path / "demo.mp4"
    output = tmp_path / "filtered.mp4"
    source.write_bytes(b"source")
    commands: list[list[str]] = []

    def runner(command: list[str]) -> None:
        commands.append(command)
        Path(command[-1]).write_bytes(b"filtered")

    result = filter_service.apply_source_voice_filter(source, output, mode="auto", process_runner=runner)

    assert result.backend == "fast"
    assert [command[0] for command in commands] == ["ffmpeg"]


def test_ai_source_voice_filter_does_not_fall_back_to_fast(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(filter_service, "demucs_available", lambda: True)
    source = tmp_path / "demo.mp4"
    output = tmp_path / "filtered.mp4"
    source.write_bytes(b"source")
    commands: list[list[str]] = []

    def runner(command: list[str]) -> None:
        commands.append(command)
        if command[0] == "demucs":
            output.write_bytes(b"partial")
            raise RuntimeError("demucs exploded")

    with pytest.raises(RuntimeError, match="demucs exploded"):
        filter_service.apply_source_voice_filter(source, output, mode="ai", process_runner=runner)

    assert [command[0] for command in commands] == ["ffmpeg", "demucs"]


def test_old_auto_mode_reuses_fast_cache(tmp_path, monkeypatch) -> None:
    output = tmp_path / "filtered.mp4"
    output.write_bytes(b"filtered")
    result = filter_service.SourceVoiceFilterResult(output_path=output, backend="fast", mode="fast")
    filter_service.write_source_voice_filter_metadata(result)

    monkeypatch.setattr(filter_service, "demucs_available", lambda: False)
    assert filter_service.read_source_voice_filter_backend(output) == "fast"
    assert filter_service.source_voice_filter_cached_output_valid(output, "auto")

    monkeypatch.setattr(filter_service, "demucs_available", lambda: True)
    assert filter_service.source_voice_filter_cached_output_valid(output, "auto")


def test_old_auto_ai_cache_is_not_reused_for_fast_mode(tmp_path, monkeypatch) -> None:
    output = tmp_path / "filtered.mp4"
    output.write_bytes(b"filtered")
    result = filter_service.SourceVoiceFilterResult(output_path=output, backend="ai", mode="auto")
    filter_service.write_source_voice_filter_metadata(result)

    monkeypatch.setattr(filter_service, "demucs_available", lambda: True)

    assert not filter_service.source_voice_filter_cached_output_valid(output, "auto")


def test_ai_source_voice_filter_runs_demucs_then_muxes_no_vocals(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(filter_service, "demucs_available", lambda: True)
    monkeypatch.setattr(filter_service, "_can_copy_video_stream", lambda _path: False)
    source = tmp_path / "demo.mp4"
    output = tmp_path / "filtered.mp4"
    source.write_bytes(b"source")
    commands: list[list[str]] = []

    def runner(command: list[str]) -> None:
        commands.append(command)
        if command[0] == "ffmpeg" and "pcm_s16le" in command:
            Path(command[-1]).write_bytes(b"wav")
        if command[0] == "demucs":
            output_root = Path(command[command.index("-o") + 1])
            demucs_input = Path(command[-1])
            no_vocals = (
                output_root / filter_service.SOURCE_VOICE_FILTER_DEMUCS_MODEL / demucs_input.stem / "no_vocals.wav"
            )
            no_vocals.parent.mkdir(parents=True, exist_ok=True)
            no_vocals.write_bytes(b"no vocals")
        if command[0] == "ffmpeg" and "pcm_s16le" not in command:
            Path(command[-1]).write_bytes(b"filtered")

    result = filter_service.apply_source_voice_filter(source, output, mode="ai", process_runner=runner)

    assert result.backend == "ai"
    assert [command[0] for command in commands] == ["ffmpeg", "demucs", "ffmpeg"]
    assert str(source) in commands[0]
    assert commands[1][-1].endswith("source-audio.wav")
    assert "1:a:0" in commands[2]


def test_ai_source_voice_filter_copies_safe_h264_video(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(filter_service, "demucs_available", lambda: True)
    monkeypatch.setattr(filter_service, "_can_copy_video_stream", lambda _path: True)
    source = tmp_path / "demo.mp4"
    output = tmp_path / "filtered.mp4"
    source.write_bytes(b"source")
    commands: list[list[str]] = []

    def runner(command: list[str]) -> None:
        commands.append(command)
        if command[0] == "demucs":
            output_root = Path(command[command.index("-o") + 1])
            demucs_input = Path(command[-1])
            no_vocals = (
                output_root / filter_service.SOURCE_VOICE_FILTER_DEMUCS_MODEL / demucs_input.stem / "no_vocals.wav"
            )
            no_vocals.parent.mkdir(parents=True, exist_ok=True)
            no_vocals.write_bytes(b"no vocals")
        if command[0] == "ffmpeg":
            Path(command[-1]).write_bytes(b"filtered")

    filter_service.apply_source_voice_filter(source, output, mode="ai", process_runner=runner)

    mux_command = commands[2]
    assert mux_command[mux_command.index("-c:v") + 1] == "copy"
    assert "-vf" not in mux_command


def test_video_copy_probe_is_cached_until_file_changes(tmp_path, monkeypatch) -> None:
    source = tmp_path / "demo.mp4"
    source.write_bytes(b"first")
    filter_service._VIDEO_COPY_CACHE.clear()
    calls = {"count": 0}

    def fake_probe(_path: Path) -> bool:
        calls["count"] += 1
        return True

    monkeypatch.setattr(filter_service, "_probe_can_copy_video_stream", fake_probe)

    assert filter_service._can_copy_video_stream(source)
    assert filter_service._can_copy_video_stream(source)
    assert calls["count"] == 1

    source.write_bytes(b"second-version")

    assert filter_service._can_copy_video_stream(source)
    assert calls["count"] == 2


def test_source_voice_filter_resolves_demucs_command(monkeypatch, tmp_path) -> None:
    demucs_path = tmp_path / "demucs.exe"
    demucs_path.write_bytes(b"")
    monkeypatch.setattr(filter_service, "demucs_command", lambda: [str(demucs_path)])

    command = filter_service.resolve_source_voice_filter_command(["demucs", "-n", "htdemucs"])

    assert command[:3] == [str(demucs_path), "-n", "htdemucs"]


def test_source_filter_worker_resolves_command_before_popen(monkeypatch, tmp_path, qapp) -> None:
    captured: dict[str, object] = {}
    resolved_command = [str(tmp_path / "demucs.exe"), "-n", "htdemucs"]

    def fake_resolve(command: list[str]) -> list[str]:
        captured["unresolved"] = command
        return resolved_command

    class FakeProcess:
        returncode = 0

        def __init__(self, command: list[str], **_kwargs: object) -> None:
            captured["popen"] = command

        def communicate(self) -> tuple[str, str]:
            return "", ""

        def poll(self) -> int:
            return self.returncode

    monkeypatch.setattr(player_window_workers, "resolve_source_voice_filter_command", fake_resolve)
    monkeypatch.setattr(player_window_workers.subprocess, "Popen", FakeProcess)
    worker = SourceAudioFilterWorker("source.mp4", tmp_path / "filtered.mp4", mode="ai")

    worker._run_process(["demucs", "-n", "htdemucs"])

    assert captured["unresolved"] == ["demucs", "-n", "htdemucs"]
    assert captured["popen"] == resolved_command


@requires_ffmpeg
def test_fast_source_voice_filter_integration_creates_cached_output(tmp_path) -> None:
    source = Path("samples/demo-video.mp4")
    if not source.exists():
        pytest.skip("sample video is not available")
    output = tmp_path / "filtered.mp4"

    result = filter_service.apply_source_voice_filter(source, output, mode="fast")
    filter_service.write_source_voice_filter_metadata(result)

    assert result.backend == "fast"
    assert output.exists()
    assert output.stat().st_size > 0
    assert filter_service.source_voice_filter_cached_output_valid(output, "fast")
    assert filter_service.read_source_voice_filter_backend(output) == "fast"


@requires_ffmpeg
def test_fast_source_voice_filter_reduces_center_voice_more_than_side_audio(tmp_path) -> None:
    source_wav = tmp_path / "center-and-side.wav"
    source_video = tmp_path / "center-and-side.mp4"
    filtered_video = tmp_path / "filtered.mp4"
    filtered_wav = tmp_path / "filtered.wav"
    _write_center_and_side_test_wav(source_wav)
    _mux_wav_to_test_video(source_wav, source_video)

    filter_service.apply_source_voice_filter(source_video, filtered_video, mode="fast")
    _decode_video_audio(filtered_video, filtered_wav)

    center_rms = _stereo_rms(filtered_wav, start_seconds=0.10, end_seconds=0.45)
    side_rms = _stereo_rms(filtered_wav, start_seconds=0.60, end_seconds=0.95)

    assert center_rms > 0
    assert side_rms > center_rms * 1.8


def test_source_filter_process_error_includes_stderr() -> None:
    error = subprocess.CalledProcessError(2, ["ffmpeg"], stderr="bad codec\nmore detail")

    message = _format_process_exception(error)

    assert "ffmpeg failed with exit code 2" in message
    assert "bad codec more detail" in message


def test_source_filter_process_error_keeps_tail_of_long_stderr() -> None:
    progress = "0%| progress noise " * 80
    error = subprocess.CalledProcessError(1, ["demucs"], stderr=f"{progress}\nRuntimeError: real failure")

    message = _format_process_exception(error, max_length=160)

    assert message.startswith("demucs failed with exit code 1")
    assert "RuntimeError: real failure" in message


def test_source_filter_process_error_names_demucs_wrapper() -> None:
    command = ["python", "-m", "ai_player.services.demucs_runner", "-n", "htdemucs"]

    assert _process_executable_name(command) == "demucs"


def _write_center_and_side_test_wav(path: Path, sample_rate: int = 44_100) -> None:
    frame_count = sample_rate
    frames = bytearray()
    for index in range(frame_count):
        t = index / sample_rate
        if index < frame_count // 2:
            left = right = 0.45 * math.sin(2.0 * math.pi * 440.0 * t)
        else:
            sample = 0.18 * math.sin(2.0 * math.pi * 880.0 * t)
            left = sample
            right = -sample
        frames.extend(struct.pack("<hh", _to_pcm16(left), _to_pcm16(right)))

    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(2)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(frames)


def _to_pcm16(value: float) -> int:
    value = max(-1.0, min(1.0, value))
    return int(value * 32767)


def _mux_wav_to_test_video(audio_path: Path, output_path: Path) -> None:
    subprocess.run(
        [
            FFMPEG or "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=black:s=32x32:d=1",
            "-i",
            str(audio_path),
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-shortest",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-y",
            str(output_path),
        ],
        check=True,
    )


def _decode_video_audio(video_path: Path, output_path: Path) -> None:
    subprocess.run(
        [
            FFMPEG or "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(video_path),
            "-ac",
            "2",
            "-ar",
            "44100",
            "-y",
            str(output_path),
        ],
        check=True,
    )


def _stereo_rms(path: Path, *, start_seconds: float, end_seconds: float) -> float:
    with wave.open(str(path), "rb") as wav_file:
        sample_rate = wav_file.getframerate()
        channels = wav_file.getnchannels()
        sample_width = wav_file.getsampwidth()
        assert channels == 2
        assert sample_width == 2
        start_frame = int(start_seconds * sample_rate)
        frame_count = int((end_seconds - start_seconds) * sample_rate)
        wav_file.setpos(start_frame)
        raw = wav_file.readframes(frame_count)
    samples = struct.unpack(f"<{len(raw) // 2}h", raw)
    if not samples:
        return 0.0
    return math.sqrt(sum((sample / 32768.0) ** 2 for sample in samples) / len(samples))
