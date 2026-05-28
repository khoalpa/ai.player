import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from ai_player.services import ffmpeg as ffmpeg_service
from ai_player.services.ffmpeg import concat_escape, concat_file_line, safe_float


def test_concat_escape_uses_forward_slashes_and_quotes() -> None:
    escaped = concat_escape(Path("C:/Video/Test O'Clock/demo.wav"))

    assert "/" in escaped
    assert "\\Users\\" not in escaped
    assert "O'\\''Clock" in escaped


def test_concat_file_line_format() -> None:
    line = concat_file_line(Path("demo.wav"))

    assert line.startswith("file '")
    assert line.endswith("'\n")


def test_safe_float() -> None:
    assert safe_float("1.25") == 1.25
    assert safe_float("N/A") is None
    assert safe_float("-1") is None
    assert safe_float("inf") is None
    assert safe_float("nan") is None


def test_probe_duration_seconds_caches_by_file_stat(monkeypatch, tmp_path) -> None:
    audio_path = tmp_path / "demo.wav"
    audio_path.write_bytes(b"fake")
    calls = []

    def fake_run_ffprobe(args, **_kwargs):
        calls.append(args)
        return SimpleNamespace(stdout="1.5\n")

    ffmpeg_service.clear_probe_duration_cache()
    monkeypatch.setattr(ffmpeg_service, "run_ffprobe", fake_run_ffprobe)

    try:
        assert ffmpeg_service.probe_duration_seconds(audio_path) == 1.5
        assert ffmpeg_service.probe_duration_seconds(audio_path) == 1.5
    finally:
        ffmpeg_service.clear_probe_duration_cache()

    assert len(calls) == 1


def test_audio_helpers_sanitize_non_finite_args(monkeypatch, tmp_path) -> None:
    calls: list[list[object]] = []
    monkeypatch.setattr(ffmpeg_service, "run_ffmpeg", lambda args, **_kwargs: calls.append(args))

    ffmpeg_service.make_silence(
        float("nan"),
        tmp_path / "silence.wav",
        sample_rate=float("inf"),
        channels="bad",
    )
    ffmpeg_service.to_wav(
        tmp_path / "in.wav",
        tmp_path / "out.wav",
        sample_rate="bad",
        channels=float("nan"),
    )
    ffmpeg_service.extract_audio_range(
        tmp_path / "source.wav",
        float("inf"),
        float("nan"),
        tmp_path / "range.wav",
        sample_rate="bad",
        channels="bad",
    )

    assert "sample_rate=44100" in calls[0][calls[0].index("-i") + 1]
    assert calls[0][calls[0].index("-t") + 1] == "0.000"
    assert calls[1][calls[1].index("-ar") + 1] == 44100
    assert calls[1][calls[1].index("-ac") + 1] == 2
    assert calls[2][calls[2].index("-ss") + 1] == "0.000"
    assert calls[2][calls[2].index("-t") + 1] == "0.050"
    assert calls[2][calls[2].index("-ac") + 1] == 1
    assert calls[2][calls[2].index("-ar") + 1] == 16000


def test_media_executable_prefers_configured_path(monkeypatch, tmp_path) -> None:
    executable = tmp_path / ffmpeg_service._executable_name("ffprobe")
    executable.write_bytes(b"fake")
    monkeypatch.setenv("AI_PLAYER_FFPROBE_PATH", str(executable))

    assert ffmpeg_service.ffprobe_executable() == str(executable)


def test_media_executable_candidates_include_chocolatey_real_binary(monkeypatch, tmp_path) -> None:
    chocolatey_root = tmp_path / "chocolatey"
    real_binary = (
        chocolatey_root / "lib" / "ffmpeg" / "tools" / "ffmpeg" / "bin" / ffmpeg_service._executable_name("ffprobe")
    )
    real_binary.parent.mkdir(parents=True)
    real_binary.write_bytes(b"fake")
    monkeypatch.delenv("AI_PLAYER_FFPROBE_PATH", raising=False)
    monkeypatch.setenv("ChocolateyInstall", str(chocolatey_root))

    candidates = ffmpeg_service._media_executable_candidates("ffprobe", "AI_PLAYER_FFPROBE_PATH")

    assert str(real_binary) in [str(path) for path in candidates]


def test_resolve_media_command_rewrites_ffmpeg(monkeypatch, tmp_path) -> None:
    executable = tmp_path / ffmpeg_service._executable_name("ffmpeg")
    executable.write_bytes(b"fake")
    monkeypatch.setenv("AI_PLAYER_FFMPEG_PATH", str(executable))

    command = ffmpeg_service.resolve_media_command(["ffmpeg", "-version"])

    assert command == [str(executable), "-version"]


def test_resolve_media_command_rewrites_ffplay(monkeypatch, tmp_path) -> None:
    executable = tmp_path / ffmpeg_service._executable_name("ffplay")
    executable.write_bytes(b"fake")
    monkeypatch.setenv("AI_PLAYER_FFPLAY_PATH", str(executable))

    command = ffmpeg_service.resolve_media_command(["ffplay", "-version"])

    assert command == [str(executable), "-version"]


def test_cancelable_quit_process_closes_stdin_on_normal_exit(monkeypatch) -> None:
    class FakeStdin:
        def __init__(self) -> None:
            self.closed = False

        def close(self) -> None:
            self.closed = True

    class FakeProcess:
        def __init__(self) -> None:
            self.stdin = FakeStdin()

        def poll(self) -> int:
            return 0

    created: list[FakeProcess] = []
    popen_kwargs: list[object] = []

    def fake_popen(_command, **kwargs):
        popen_kwargs.append(kwargs)
        process = FakeProcess()
        created.append(process)
        return process

    monkeypatch.setattr(ffmpeg_service.subprocess, "Popen", fake_popen)

    result = ffmpeg_service.run_cancelable_process(
        ["ffmpeg", "-version"],
        cancel_callback=lambda: False,
        cancel_strategy="quit",
    )

    assert result.returncode == 0
    assert popen_kwargs[0]["stdin"] == subprocess.PIPE
    assert created[0].stdin.closed


def test_cancelable_process_captures_pipe_output() -> None:
    result = ffmpeg_service.run_cancelable_process(
        [sys.executable, "-c", "import sys; sys.stdout.write('ok'); sys.stderr.write('warn')"],
        cancel_callback=lambda: False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    assert result.stdout == "ok"
    assert result.stderr == "warn"


def test_cancelable_process_error_includes_pipe_output() -> None:
    with pytest.raises(subprocess.CalledProcessError) as error:
        ffmpeg_service.run_cancelable_process(
            [sys.executable, "-c", "import sys; sys.stderr.write('real failure'); raise SystemExit(3)"],
            cancel_callback=lambda: False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

    assert error.value.returncode == 3
    assert error.value.stderr == "real failure"


def test_terminate_process_kills_after_terminate_timeout() -> None:
    class FakeProcess:
        def __init__(self) -> None:
            self.terminated = False
            self.killed = False

        def poll(self):
            return None

        def terminate(self) -> None:
            self.terminated = True

        def wait(self, timeout: float | None = None) -> None:
            if not self.killed:
                raise subprocess.TimeoutExpired("fake", timeout)

        def kill(self) -> None:
            self.killed = True

    process = FakeProcess()

    ffmpeg_service.terminate_process(process)

    assert process.terminated
    assert process.killed
