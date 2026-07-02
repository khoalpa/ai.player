from __future__ import annotations

from ai_player.ui.media_start_panel import recent_source_label


def test_recent_source_label_uses_host_and_path_for_urls() -> None:
    assert recent_source_label("https://example.com/videos/demo.mp4?token=secret") == "example.com/videos/demo.mp4"


def test_recent_source_label_uses_filename_for_local_paths() -> None:
    assert recent_source_label(r"C:\Videos\demo clip.mp4") == "demo clip.mp4"


def test_recent_source_label_truncates_long_labels_from_the_left() -> None:
    assert (
        recent_source_label("https://example.com/very/long/source/path/demo.mp4", max_length=18)
        == "...e/path/demo.mp4"
    )
