from __future__ import annotations

import math

OVERLAP_POLICY_STRICT_START = "strict_start"
OVERLAP_POLICY_AVOID_OVERLAP = "avoid_overlap"
OVERLAP_POLICY_SMART = "smart"
OVERLAP_POLICIES = {
    OVERLAP_POLICY_STRICT_START,
    OVERLAP_POLICY_AVOID_OVERLAP,
    OVERLAP_POLICY_SMART,
}
SMART_OVERLAP_TOLERANCE_SECONDS = 0.35
SMART_MAX_START_DELAY_SECONDS = 0.75


def normalize_overlap_policy(value: object) -> str:
    policy = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    if policy in {"strict", "source_start", "source"}:
        return OVERLAP_POLICY_STRICT_START
    if policy in {"avoid", "sequential", "no_overlap"}:
        return OVERLAP_POLICY_AVOID_OVERLAP
    if policy in OVERLAP_POLICIES:
        return policy
    return OVERLAP_POLICY_SMART


def schedule_timeline_start(
    *,
    source_start_seconds: float,
    duration_seconds: float,
    scheduled_until_seconds: float,
    policy: object,
    force_avoid_overlap: bool = False,
) -> tuple[float, float]:
    source_start = max(0.0, _finite_seconds(source_start_seconds, 0.0))
    duration = max(0.05, _finite_seconds(duration_seconds, 0.05))
    scheduled_until = max(0.0, _finite_seconds(scheduled_until_seconds, 0.0))
    normalized_policy = normalize_overlap_policy(policy)

    if force_avoid_overlap or normalized_policy == OVERLAP_POLICY_AVOID_OVERLAP:
        scheduled_start = max(source_start, scheduled_until)
    elif normalized_policy == OVERLAP_POLICY_STRICT_START:
        scheduled_start = source_start
    else:
        overlap = scheduled_until - source_start
        if overlap <= SMART_OVERLAP_TOLERANCE_SECONDS:
            scheduled_start = source_start
        else:
            scheduled_start = min(scheduled_until, source_start + SMART_MAX_START_DELAY_SECONDS)

    return scheduled_start, max(scheduled_until, scheduled_start + duration)


def _finite_seconds(value: object, default: float) -> float:
    try:
        seconds = float(value)
    except (TypeError, ValueError, OverflowError):
        return default
    return seconds if math.isfinite(seconds) else default
