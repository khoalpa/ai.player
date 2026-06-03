from __future__ import annotations

from types import SimpleNamespace

from ai_player.ui.player_window_state import (
    MediaFrameState,
    MediaProcessingState,
    PlaybackUiState,
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


def test_playback_ui_state_uses_independent_sidebar_sizes() -> None:
    first = PlaybackUiState(sidebar_panel_sizes=[1500, 360])
    second = PlaybackUiState()

    first.sidebar_panel_sizes[1] = 480

    assert first.sidebar_panel_sizes == [1500, 480]
    assert second.sidebar_panel_sizes == []


def test_playback_ui_state_tracks_playback_and_dialog_values() -> None:
    dialog = object()
    cache_dialog = object()
    state = PlaybackUiState(
        seeking=True,
        top_panel_hidden=True,
        bottom_panel_hidden=True,
        sidebar_panel_hidden=True,
        sidebar_panel_sizes=[1200, 400],
        video_delay_active=True,
        dubbing_ready=True,
        dubbing_auto_enabled=True,
        export_dialog=dialog,
        export_terminal=True,
        cache_dialog=cache_dialog,
        video_fullscreen=True,
    )

    assert state.seeking is True
    assert state.top_panel_hidden is True
    assert state.bottom_panel_hidden is True
    assert state.sidebar_panel_hidden is True
    assert state.sidebar_panel_sizes == [1200, 400]
    assert state.video_delay_active is True
    assert state.dubbing_ready is True
    assert state.dubbing_auto_enabled is True
    assert state.export_dialog is dialog
    assert state.export_terminal is True
    assert state.cache_dialog is cache_dialog
    assert state.video_fullscreen is True


def test_media_frame_state_tracks_fullscreen_detach_values() -> None:
    frame = object()
    parent = object()
    layout = object()
    alignment = object()
    state = MediaFrameState(
        frame=frame,
        parent=parent,
        layout=layout,
        index=2,
        alignment=alignment,
        detached_for_fullscreen=True,
    )

    assert state.frame is frame
    assert state.parent is parent
    assert state.layout is layout
    assert state.index == 2
    assert state.alignment is alignment
    assert state.detached_for_fullscreen is True


def test_telegram_channel_state_uses_independent_collections() -> None:
    first = TelegramChannelState()
    second = TelegramChannelState()

    first.channel_items.append("visible")
    first.channel_all_items.append("all")
    first.channel_translations["post"] = "translation"
    first.blacklisted_item_keys.add("post")
    first.blacklisted_content_keys.add("same content")
    first.opened_item_keys.add("opened")
    first.failed_item_keys.add("failed")
    first.side_panel_sizes[0] = 3

    assert second.channel_items == []
    assert second.channel_all_items == []
    assert second.channel_translations == {}
    assert second.blacklisted_item_keys == set()
    assert second.blacklisted_content_keys == set()
    assert second.opened_item_keys == set()
    assert second.failed_item_keys == set()
    assert second.side_panel_sizes == [1, 1]


def test_telegram_channel_state_tracks_browser_navigation_values() -> None:
    item = object()
    thumbnail = object()
    state = TelegramChannelState(
        channel_items=[item],
        channel_all_items=[item],
        channel_authenticated=True,
        channel_translations={"101": "xin chao"},
        blacklisted_item_keys={"102"},
        blacklisted_content_keys={"same content"},
        opened_item_keys={"101"},
        failed_item_keys={"103"},
        pending_post_id="100",
        current_channel_item=item,
        current_post_id="101",
        current_url="https://t.me/demo/101",
        pending_navigation_direction=-1,
        pending_autoplay=True,
        loading_item_key="101",
        pending_open_item_key="102",
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
    assert state.blacklisted_item_keys == {"102"}
    assert state.blacklisted_content_keys == {"same content"}
    assert state.opened_item_keys == {"101"}
    assert state.failed_item_keys == {"103"}
    assert state.pending_post_id == "100"
    assert state.current_channel_item is item
    assert state.current_post_id == "101"
    assert state.current_url == "https://t.me/demo/101"
    assert state.pending_navigation_direction == -1
    assert state.pending_autoplay is True
    assert state.loading_item_key == "101"
    assert state.pending_open_item_key == "102"
    assert state.browser_return_available is True
    assert state.channel_thumbnail_source is thumbnail
    assert state.auto_load_pending_before_post_id == "99"
    assert state.side_panel_visible is False
    assert state.side_panel_sizes == [640, 360]


def test_telegram_channel_state_tracks_item_open_status() -> None:
    current = SimpleNamespace(post_id="100", url="https://t.me/demo/100")
    queued = SimpleNamespace(post_id="101", url="https://t.me/demo/101")
    failed = SimpleNamespace(post_id="102", url="https://t.me/demo/102")
    state = TelegramChannelState(current_channel_item=current, pending_open_item_key="101")

    assert state.mark_opening(current) == "100"
    assert state.item_status(current) == "loading"
    assert state.mark_opened(current) is True
    assert state.item_status(current) == "current"
    assert state.item_status(queued) == "queued"

    assert state.mark_failed(failed) is True
    assert state.item_status(failed) == "failed"
    state.current_channel_item = failed
    assert state.item_status(failed) == "failed"
    state.current_channel_item = None
    assert state.mark_opened(failed) is True
    assert state.item_status(failed) == "opened"


def test_telegram_channel_state_replaces_and_appends_unique_items() -> None:
    first = SimpleNamespace(url="https://t.me/demo/1")
    duplicate = SimpleNamespace(url="https://t.me/demo/1")
    second = SimpleNamespace(url="https://t.me/demo/2")
    no_url = SimpleNamespace(url="")
    state = TelegramChannelState()

    state.replace_items([first])
    state.append_unique_items([duplicate, second, no_url, no_url])

    assert state.channel_all_items == [first, second, no_url, no_url]


def test_telegram_channel_state_tracks_translations_by_post_id_or_url() -> None:
    translated = SimpleNamespace(post_id="100", url="https://t.me/demo/100", text="old")
    pending = SimpleNamespace(post_id="", url="https://t.me/demo/pending", text="hello")
    empty = SimpleNamespace(post_id="102", url="https://t.me/demo/102", text="")
    state = TelegramChannelState(channel_all_items=[translated, pending, empty])

    assert state.store_translation("100", "https://t.me/demo/100", "  xin   chao  ") is True
    assert state.store_translation("101", "https://t.me/demo/101", "   ") is False

    assert state.item_translation(translated) == "xin chao"
    assert state.items_to_translate(lambda item: bool(item.text)) == [pending]


def test_telegram_channel_state_tracks_blacklisted_items_by_post_id_or_url() -> None:
    post_item = SimpleNamespace(post_id="100", url="https://t.me/demo/100", text="")
    url_item = SimpleNamespace(post_id="", url="https://t.me/demo/pending", text="")
    empty_item = SimpleNamespace(post_id="", url="", text="")
    state = TelegramChannelState()

    assert state.blacklist_item(post_item) is True
    assert state.blacklist_item(url_item) is True
    assert state.blacklist_item(empty_item) is False

    assert state.is_blacklisted(post_item) is True
    assert state.is_blacklisted(url_item) is True
    assert state.unblacklist_item(post_item) is True
    assert state.unblacklist_item(post_item) is False
    assert state.is_blacklisted(post_item) is False
    assert state.is_blacklisted(url_item) is True


def test_telegram_channel_state_tracks_blacklisted_items_by_content() -> None:
    original = SimpleNamespace(post_id="100", url="https://t.me/demo/100", text="  Same   CONTENT  ", title="")
    duplicate = SimpleNamespace(post_id="101", url="https://t.me/demo/101", text="same content", title="")
    title_duplicate = SimpleNamespace(post_id="102", url="https://t.me/demo/102", text="", title="Same Content")
    different = SimpleNamespace(post_id="103", url="https://t.me/demo/103", text="other", title="")
    state = TelegramChannelState(channel_all_items=[original, duplicate, title_duplicate, different])

    assert state.blacklist_item(original) is True

    assert state.is_blacklisted(original) is True
    assert state.is_blacklisted(duplicate) is True
    assert state.is_blacklisted(title_duplicate) is True
    assert state.is_blacklisted(different) is False
    assert state.blacklisted_content_keys == {"same content"}

    assert state.unblacklist_item(duplicate) is True
    assert state.is_blacklisted(duplicate) is False
    assert state.is_blacklisted(original) is False
    assert state.is_blacklisted(title_duplicate) is False


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
