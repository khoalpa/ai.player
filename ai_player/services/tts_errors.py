from __future__ import annotations


def friendly_tts_error(data: object) -> str:
    if not isinstance(data, dict):
        return ""
    error = data.get("error")
    if isinstance(error, dict):
        message = str(error.get("message") or "").strip()
        if message:
            return message
    detail = data.get("detail")
    if isinstance(detail, dict):
        message = str(detail.get("message") or "").strip()
        if message:
            return message
    return str(data.get("message") or "").strip()
