from __future__ import annotations

from ai_player.ui.runtime_metrics import process_cpu_percent, system_cpu_percent_from_times


def test_process_cpu_percent_accounts_for_elapsed_time_and_cpu_count() -> None:
    assert (
        process_cpu_percent(
            previous_wall=10.0,
            previous_process=2.0,
            current_wall=12.0,
            current_process=3.0,
            cpu_count=4,
        )
        == 12.5
    )


def test_process_cpu_percent_clamps_negative_process_delta() -> None:
    assert (
        process_cpu_percent(
            previous_wall=10.0,
            previous_process=3.0,
            current_wall=12.0,
            current_process=2.0,
            cpu_count=4,
        )
        == 0.0
    )


def test_system_cpu_percent_from_times_uses_idle_delta() -> None:
    assert system_cpu_percent_from_times((50, 100), (60, 200)) == 90.0


def test_system_cpu_percent_from_times_handles_missing_or_non_positive_delta() -> None:
    assert system_cpu_percent_from_times(None, (60, 200)) is None
    assert system_cpu_percent_from_times((50, 100), (60, 100)) is None
