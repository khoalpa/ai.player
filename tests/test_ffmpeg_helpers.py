from pathlib import Path
from types import SimpleNamespace

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
