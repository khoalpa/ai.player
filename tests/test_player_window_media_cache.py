from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from ai_player.services import demucs_separation
from ai_player.services.media_cache import (
    playback_compat_cached_output_valid,
    remove_playback_compat_output,
    write_playback_compat_metadata,
)
from ai_player.ui.player_window_media import PlayerMediaMixin
from ai_player.workers import player_window_workers


class DummyMediaMixin(PlayerMediaMixin):
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

    first_key = PlayerMediaMixin._playback_compat_cache_key(str(source))
    first_output = PlayerMediaMixin._playback_compat_output_path(str(source))

    source.write_bytes(b"second-version")

    assert PlayerMediaMixin._playback_compat_cache_key(str(source)) != first_key
    assert PlayerMediaMixin._playback_compat_output_path(str(source)) != first_output


def test_playback_compat_cache_requires_complete_metadata(tmp_path) -> None:
    source = tmp_path / "demo.mp4"
    output = tmp_path / "cached.mp4"
    source.write_bytes(b"source")
    output.write_bytes(b"partial")
    cache_key = PlayerMediaMixin._playback_compat_cache_key(str(source))

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
    worker = player_window_workers.PlaybackCompatibilityWorker(str(source), output, "cache-key")

    class FakeProcess:
        def poll(self):
            return 0

        def wait(self):
            output.write_bytes(b"partial")
            output.with_suffix(".mp4.json").write_text("{}", encoding="utf-8")
            worker._stop_requested = True
            return 0

    monkeypatch.setattr(player_window_workers, "ffmpeg_executable", lambda: "ffmpeg")
    monkeypatch.setattr(player_window_workers.subprocess, "Popen", lambda _command: FakeProcess())

    worker.run()

    assert not output.exists()
    assert not output.with_suffix(".mp4.json").exists()


def test_ytdlp_cache_compatible_video_does_not_need_playback_transcode(monkeypatch, tmp_path) -> None:
    cache_root = tmp_path / "ai-player-sources"
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(tmp_path))
    source = cache_root / "buomtv" / "best" / "demo.mp4"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"demo")
    monkeypatch.setattr(PlayerMediaMixin, "_is_qt_compatible_local_video", staticmethod(lambda _path: True))

    assert not PlayerMediaMixin._needs_qt_playback_compat(str(source))


def test_ytdlp_cache_incompatible_video_still_needs_playback_transcode(monkeypatch, tmp_path) -> None:
    cache_root = tmp_path / "ai-player-sources"
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(tmp_path))
    source = cache_root / "buomtv" / "best" / "demo.mp4"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"demo")
    monkeypatch.setattr(PlayerMediaMixin, "_is_qt_compatible_local_video", staticmethod(lambda _path: False))

    assert PlayerMediaMixin._needs_qt_playback_compat(str(source))


def test_qt_compatible_probe_is_cached_until_file_changes(monkeypatch, tmp_path) -> None:
    source = tmp_path / "demo.mp4"
    source.write_bytes(b"first")
    calls = {"count": 0}

    def fake_probe(_path: str) -> bool:
        calls["count"] += 1
        return True

    monkeypatch.setattr(PlayerMediaMixin, "_probe_qt_compatible_local_video", staticmethod(fake_probe))

    assert PlayerMediaMixin._is_qt_compatible_local_video(str(source))
    assert PlayerMediaMixin._is_qt_compatible_local_video(str(source))
    assert calls["count"] == 1

    source.write_bytes(b"second-version")

    assert PlayerMediaMixin._is_qt_compatible_local_video(str(source))
    assert calls["count"] == 2


def test_frozen_demucs_command_uses_app_runner(monkeypatch) -> None:
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(Path("AI Player.exe")))
    monkeypatch.delenv("AI_PLAYER_DEMUCS_PATH", raising=False)

    assert demucs_separation.demucs_command() == [str(Path("AI Player.exe")), "--demucs-runner"]
