from __future__ import annotations

from ai_player.ui.player_window_state import (
    MediaProcessingState,
    RuntimeStatusState,
    TelegramChannelState,
    WorkerLifecycleState,
)


def test_media_processing_state_uses_independent_cache_maps() -> None:
    first = MediaProcessingState()
    second = MediaProcessingState()

    first.source_filter_cache["source"] = "filtered.wav"
    first.playback_compat_cache["source"] = "compat.mp4"

    assert second.source_filter_cache == {}
    assert second.playback_compat_cache == {}


def test_media_processing_state_tracks_worker_runtime_flags() -> None:
    state = MediaProcessingState(
        source_filter_worker_mode="fast",
        source_filter_worker_model="htdemucs",
        source_filter_restart_pending=True,
    )

    assert state.source_filter_worker_mode == "fast"
    assert state.source_filter_worker_model == "htdemucs"
    assert state.source_filter_restart_pending is True


def test_runtime_status_state_keeps_runtime_tab_values() -> None:
    state = RuntimeStatusState(
        last_wall=1.5,
        last_process=0.25,
        last_system_cpu=(10, 20),
        gpu_text="GPU ready",
        gpu_tick=3,
        media_path="demo.mp4",
        media_info_path="demo.mp4",
        media_info_text="duration 4s",
    )

    assert state.last_wall == 1.5
    assert state.last_process == 0.25
    assert state.last_system_cpu == (10, 20)
    assert state.gpu_text == "GPU ready"
    assert state.gpu_tick == 3
    assert state.media_path == "demo.mp4"
    assert state.media_info_path == "demo.mp4"
    assert state.media_info_text == "duration 4s"


def test_telegram_channel_state_uses_independent_collections() -> None:
    first = TelegramChannelState()
    second = TelegramChannelState()

    first.channel_items.append("visible")
    first.channel_all_items.append("all")
    first.channel_translations["post"] = "translation"
    first.side_panel_sizes[0] = 3

    assert second.channel_items == []
    assert second.channel_all_items == []
    assert second.channel_translations == {}
    assert second.side_panel_sizes == [1, 1]


def test_telegram_channel_state_tracks_browser_navigation_values() -> None:
    item = object()
    thumbnail = object()
    state = TelegramChannelState(
        channel_items=[item],
        channel_all_items=[item],
        channel_authenticated=True,
        channel_translations={"101": "xin chao"},
        pending_post_id="100",
        current_channel_item=item,
        current_post_id="101",
        current_url="https://t.me/demo/101",
        pending_navigation_direction=-1,
        pending_autoplay=True,
        browser_return_available=True,
        channel_thumbnail_source=thumbnail,
        auto_load_pending_before_post_id="99",
        side_panel_visible=False,
        side_panel_sizes=[640, 360],
    )

    assert state.channel_items == [item]
    assert state.channel_all_items == [item]
    assert state.channel_authenticated is True
    assert state.channel_translations == {"101": "xin chao"}
    assert state.pending_post_id == "100"
    assert state.current_channel_item is item
    assert state.current_post_id == "101"
    assert state.current_url == "https://t.me/demo/101"
    assert state.pending_navigation_direction == -1
    assert state.pending_autoplay is True
    assert state.browser_return_available is True
    assert state.channel_thumbnail_source is thumbnail
    assert state.auto_load_pending_before_post_id == "99"
    assert state.side_panel_visible is False
    assert state.side_panel_sizes == [640, 360]


def test_worker_lifecycle_state_tracks_worker_references_and_flags() -> None:
    worker = object()
    state = WorkerLifecycleState(
        dubbing_worker=worker,
        dubbing_worker_generation=2,
        export_worker=worker,
        meeting_worker=worker,
        meeting_elapsed="00:00:02",
        telegram_worker=worker,
        telegram_translation_worker=worker,
        pending_telegram_url="https://t.me/demo",
        document_worker=worker,
    )

    assert state.dubbing_worker is worker
    assert state.dubbing_worker_generation == 2
    assert state.export_worker is worker
    assert state.meeting_worker is worker
    assert state.meeting_elapsed == "00:00:02"
    assert state.telegram_worker is worker
    assert state.telegram_translation_worker is worker
    assert state.pending_telegram_url == "https://t.me/demo"
    assert state.document_worker is worker
