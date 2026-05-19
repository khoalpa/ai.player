from __future__ import annotations

from ai_player.ui.player_window_media import PlayerMediaMixin


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
