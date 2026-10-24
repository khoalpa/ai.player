from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

AUTO_PROFILE_TITLE_KEYS = {
    "quick": "first_run_profile_quick",
    "offline": "first_run_profile_offline",
    "quality": "first_run_profile_quality",
    "meeting_document": "first_run_profile_meeting_document",
}
AUTO_PROFILE_REASON_KEYS = {
    "export": "auto_preset_reason_export",
    "document": "auto_preset_reason_document",
    "meeting": "auto_preset_reason_meeting",
    "url": "auto_preset_reason_url",
    "video": "auto_preset_reason_video",
}
PRESET_CARD_DETAIL_KEYS = {
    "low_latency": "preset_card_low_latency",
    "offline_lite": "preset_card_offline_lite",
    "balanced": "preset_card_balanced",
    "quality": "preset_card_quality",
}
WORKFLOW_BADGE_KEYS = {
    "video": "workflow_badge_video",
    "url": "workflow_badge_url",
    "document": "workflow_badge_document",
    "meeting": "workflow_badge_meeting",
}


def auto_goal_profile(workflow: str, *, offline_ready: bool) -> str:
    workflow_key = str(workflow or "").strip().lower()
    if workflow_key == "export":
        return "quality"
    if workflow_key in {"document", "meeting"}:
        return "meeting_document"
    if workflow_key in {"video", "url"} and offline_ready:
        return "offline"
    return "quick"


def auto_goal_profile_reason_keys(workflow: str, profile_key: str) -> tuple[str, str]:
    workflow_key = str(workflow or "").strip().lower()
    return (
        AUTO_PROFILE_TITLE_KEYS.get(profile_key, "first_run_profile_auto"),
        AUTO_PROFILE_REASON_KEYS.get(workflow_key, "auto_preset_reason_default"),
    )


def preset_card_detail_key(preset_id: str) -> str:
    return PRESET_CARD_DETAIL_KEYS.get(str(preset_id or ""), "preset_card_default")


def recent_source_label(source: str, *, max_length: int = 48) -> str:
    value = str(source or "").strip()
    parsed = urlparse(value)
    if parsed.netloc:
        label = f"{parsed.netloc}{parsed.path}"
    else:
        label = Path(value).name or value
    return label if len(label) <= max_length else f"...{label[-(max_length - 3) :]}"


def workflow_badge_key(workflow: str) -> str:
    return WORKFLOW_BADGE_KEYS.get(str(workflow or "").strip().lower(), "workflow_badge_default")
