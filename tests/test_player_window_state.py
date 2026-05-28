from __future__ import annotations

from ai_player.ui.player_window_state import MediaProcessingState, RuntimeStatusState, WorkerLifecycleState


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


def test_worker_lifecycle_state_tracks_worker_references_and_flags() -> None:
    worker = object()
    state = WorkerLifecycleState(
        dubbing_worker=worker,
        dubbing_worker_generation=2,
        export_worker=worker,
        meeting_worker=worker,
        meeting_elapsed="00:00:02",
        telegram_worker=worker,
        pending_telegram_url="https://t.me/demo",
        document_worker=worker,
    )

    assert state.dubbing_worker is worker
    assert state.dubbing_worker_generation == 2
    assert state.export_worker is worker
    assert state.meeting_worker is worker
    assert state.meeting_elapsed == "00:00:02"
    assert state.telegram_worker is worker
    assert state.pending_telegram_url == "https://t.me/demo"
    assert state.document_worker is worker
