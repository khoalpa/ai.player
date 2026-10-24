from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from ai_player.adapters import workflow_bindings
from ai_player.adapters.media import demucs_separation
from ai_player.adapters.storage.media_cache import (
    playback_compat_cached_output_valid,
    remove_playback_compat_output,
    write_playback_compat_metadata,
)
from ai_player.application.workflows import sources as player_window_workers
from ai_player.ui.features.media import PlayerMediaFeature


class DummyMediaMixin(PlayerMediaFeature):
    def __init__(self):
        from tests.ui_context_helpers import context_for

        super().__init__(context_for(self))

    def _selected_source_filter_mode(self) -> str:
        return "fast"


def test_source_filter_cache_key_changes_when_source_file_changes(tmp_path) -> None:
    source = tmp_path / "demo.mp4"
    source.write_bytes(b"first")
    mixin = DummyMediaMixin()

    first_key = mixin._source_filter_cache_key(str(source))
    first_output = mixin._source_filter_output_path(str(source), "fast")

    source.write_bytes(b"second-version")

    assert mixin._source_filter_cache_key(str(source)) != first_key
    assert mixin._source_filter_output_path(str(source), "fast") != first_output


def test_playback_compat_cache_key_changes_when_source_file_changes(tmp_path) -> None:
    source = tmp_path / "demo.mp4"
    source.write_bytes(b"first")

    first_key = PlayerMediaFeature._playback_compat_cache_key(str(source))
    first_output = PlayerMediaFeature._playback_compat_output_path(str(source))

    source.write_bytes(b"second-version")

    assert PlayerMediaFeature._playback_compat_cache_key(str(source)) != first_key
    assert PlayerMediaFeature._playback_compat_output_path(str(source)) != first_output


def test_playback_compat_cache_requires_complete_metadata(tmp_path) -> None:
    source = tmp_path / "demo.mp4"
    output = tmp_path / "cached.mp4"
    source.write_bytes(b"source")
    output.write_bytes(b"partial")
    cache_key = PlayerMediaFeature._playback_compat_cache_key(str(source))

    assert not playback_compat_cached_output_valid(output, str(source), cache_key)

    write_playback_compat_metadata(output, str(source), cache_key)

    assert playback_compat_cached_output_valid(output, str(source), cache_key)

    remove_playback_compat_output(output)

    assert not output.exists()
    assert not output.with_suffix(".mp4.json").exists()


def test_playback_compat_worker_removes_partial_output_when_stopped(monkeypatch, tmp_path) -> None:
    source = tmp_path / "demo.mp4"
    output = tmp_path / "cached.mp4"
    source.write_bytes(b"source")
    worker = player_window_workers.PlaybackCompatibilityWorker(
        str(source), output, "cache-key", dependencies=workflow_bindings.sources()
    )

    class FakeProcess:
        def poll(self):
            return 0

        def wait(self):
            output.write_bytes(b"partial")
            output.with_suffix(".mp4.json").write_text("{}", encoding="utf-8")
            worker._stop_requested = True
            return 0

    monkeypatch.setattr("ai_player.adapters.media.ffmpeg.ffmpeg_executable", lambda: "ffmpeg")
    monkeypatch.setattr(player_window_workers.subprocess, "Popen", lambda _command: FakeProcess())

    worker.run()

    assert not output.exists()
    assert not output.with_suffix(".mp4.json").exists()


def test_playback_compat_worker_preserves_source_resolution(monkeypatch, tmp_path) -> None:
    source = tmp_path / "demo.mp4"
    output = tmp_path / "cached.mp4"
    source.write_bytes(b"source")
    captured_command = []
    worker = player_window_workers.PlaybackCompatibilityWorker(
        str(source), output, "cache-key", dependencies=workflow_bindings.sources()
    )

    class FakeProcess:
        def wait(self):
            output.write_bytes(b"cached")
            return 0

    def fake_popen(command):
        captured_command.extend(command)
        return FakeProcess()

    monkeypatch.setattr("ai_player.adapters.media.ffmpeg.ffmpeg_executable", lambda: "ffmpeg")
    monkeypatch.setattr(player_window_workers.subprocess, "Popen", fake_popen)

    worker.run()

    assert "-vf" not in captured_command
    assert "scale=-2:min(720\\,ih)" not in captured_command
    assert captured_command[captured_command.index("-crf") + 1] == "18"
    assert captured_command[captured_command.index("-level:v") + 1] == "5.1"
    assert captured_command[captured_command.index("-b:a") + 1] == "256k"


def test_ytdlp_cache_compatible_video_does_not_need_playback_transcode(monkeypatch, tmp_path) -> None:
    cache_root = tmp_path / "ai-player-sources"
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(tmp_path))
    source = cache_root / "example-provider" / "best" / "demo.mp4"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"demo")
    monkeypatch.setattr(PlayerMediaFeature, "_is_qt_compatible_local_video", staticmethod(lambda _path: True))

    assert not PlayerMediaFeature._needs_qt_playback_compat(str(source))


def test_ytdlp_cache_incompatible_video_still_needs_playback_transcode(monkeypatch, tmp_path) -> None:
    cache_root = tmp_path / "ai-player-sources"
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(tmp_path))
    source = cache_root / "example-provider" / "best" / "demo.mp4"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"demo")
    monkeypatch.setattr(PlayerMediaFeature, "_is_qt_compatible_local_video", staticmethod(lambda _path: False))

    assert PlayerMediaFeature._needs_qt_playback_compat(str(source))


def test_qt_compatible_probe_is_cached_until_file_changes(monkeypatch, tmp_path) -> None:
    source = tmp_path / "demo.mp4"
    source.write_bytes(b"first")
    calls = {"count": 0}

    def fake_probe(_path: str) -> bool:
        calls["count"] += 1
        return True

    monkeypatch.setattr(PlayerMediaFeature, "_probe_qt_compatible_local_video", staticmethod(fake_probe))

    assert PlayerMediaFeature._is_qt_compatible_local_video(str(source))
    assert PlayerMediaFeature._is_qt_compatible_local_video(str(source))
    assert calls["count"] == 1

    source.write_bytes(b"second-version")

    assert PlayerMediaFeature._is_qt_compatible_local_video(str(source))
    assert calls["count"] == 2


def test_frozen_demucs_command_uses_app_runner(monkeypatch) -> None:
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(Path("AI Player.exe")))
    monkeypatch.delenv("AI_PLAYER_DEMUCS_PATH", raising=False)

    assert demucs_separation.demucs_command() == [str(Path("AI Player.exe")), "--demucs-runner"]
