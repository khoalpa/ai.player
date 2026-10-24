from __future__ import annotations

from ai_player.ui.media_start_panel import (
    auto_goal_profile,
    auto_goal_profile_reason_keys,
    preset_card_detail_key,
    recent_source_label,
    workflow_badge_key,
)


def test_auto_goal_profile_prefers_offline_for_ready_media_workflows() -> None:
    assert auto_goal_profile("video", offline_ready=True) == "offline"
    assert auto_goal_profile("url", offline_ready=True) == "offline"


def test_auto_goal_profile_uses_workflow_specific_profiles() -> None:
    assert auto_goal_profile("export", offline_ready=True) == "quality"
    assert auto_goal_profile("document", offline_ready=True) == "meeting_document"
    assert auto_goal_profile("meeting", offline_ready=False) == "meeting_document"
    assert auto_goal_profile("video", offline_ready=False) == "quick"


def test_auto_goal_profile_reason_keys_use_defaults_for_unknown_values() -> None:
    assert auto_goal_profile_reason_keys("export", "quality") == (
        "first_run_profile_quality",
        "auto_preset_reason_export",
    )
    assert auto_goal_profile_reason_keys("other", "other") == (
        "first_run_profile_auto",
        "auto_preset_reason_default",
    )


def test_preset_card_detail_key_maps_known_presets() -> None:
    assert preset_card_detail_key("balanced") == "preset_card_balanced"
    assert preset_card_detail_key("missing") == "preset_card_default"


def test_recent_source_label_uses_host_and_path_for_urls() -> None:
    assert recent_source_label("https://example.com/videos/demo.mp4?token=secret") == "example.com/videos/demo.mp4"


def test_recent_source_label_uses_filename_for_local_paths() -> None:
    assert recent_source_label(r"C:\Videos\demo clip.mp4") == "demo clip.mp4"


def test_recent_source_label_truncates_long_labels_from_the_left() -> None:
    assert (
        recent_source_label("https://example.com/very/long/source/path/demo.mp4", max_length=18) == "...e/path/demo.mp4"
    )


def test_workflow_badge_key_maps_workflows() -> None:
    assert workflow_badge_key("document") == "workflow_badge_document"
    assert workflow_badge_key("unknown") == "workflow_badge_default"
