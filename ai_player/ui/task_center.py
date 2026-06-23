from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class BackgroundTask:
    name: str
    status: str
    detail: str


def collect_background_tasks(owner: Any) -> tuple[BackgroundTask, ...]:
    tasks = [
        _controller_task(owner, "Provider preview", "_provider_preview"),
        _controller_task(owner, "Runtime preloading", "_runtime_warmup"),
        _video_url_task(owner),
        _worker_task(owner, "Realtime dubbing", "_dub_worker"),
        _worker_task(owner, "Export", "_export_worker"),
        _meeting_task(owner),
        _worker_task(owner, "Telegram", "_telegram_worker"),
        _worker_task(owner, "Telegram translation", "_telegram_translation_worker"),
        _worker_task(owner, "Document import", "_document_worker"),
        _source_filter_task(owner),
        _worker_task(owner, "Playback compatibility", "_playback_compat_worker"),
        _offline_model_task(owner),
    ]
    return tuple(task for task in tasks if task is not None)


@dataclass(frozen=True)
class BackgroundTaskStopSummary:
    stopped: int
    failed: tuple[str, ...] = ()


def stop_background_tasks(owner: Any, *, wait_ms: int = 1500) -> BackgroundTaskStopSummary:
    active_names = {task.name for task in collect_background_tasks(owner)}
    stopped = 0
    failed: list[str] = []
    for name, stop in _task_stoppers(owner, wait_ms):
        if name not in active_names:
            continue
        if stop():
            stopped += 1
        else:
            failed.append(name)
    return BackgroundTaskStopSummary(stopped=stopped, failed=tuple(failed))


def format_background_tasks(tasks: tuple[BackgroundTask, ...], *, idle_text: str) -> str:
    active = [task for task in tasks if task.status == "RUNNING"]
    if not active:
        return idle_text
    return "\n".join(f"{task.name}: {task.status} - {task.detail}" for task in active)


def _controller_task(owner: Any, name: str, attr_name: str) -> BackgroundTask | None:
    controller = getattr(owner, attr_name, None)
    is_running = getattr(controller, "is_running", None)
    if not callable(is_running) or not is_running():
        return None
    detail = _controller_detail(controller) or _stored_task_detail(owner, name) or "Background worker is active."
    return BackgroundTask(name, "RUNNING", detail)


def _video_url_task(owner: Any) -> BackgroundTask | None:
    controller = getattr(owner, "_video_url", None)
    is_opening = getattr(controller, "is_opening", None)
    if not callable(is_opening) or not is_opening():
        return None
    detail = _stored_task_detail(owner, "URL/cache loading") or "Resolving or caching a media URL."
    return BackgroundTask("URL/cache loading", "RUNNING", detail)


def _meeting_task(owner: Any) -> BackgroundTask | None:
    worker = getattr(owner, "_meeting_worker", None)
    if not _worker_running(worker):
        return None
    elapsed = str(getattr(owner, "_meeting_elapsed", "") or "").strip()
    detail = _stored_task_detail(owner, "Meeting recorder")
    detail = detail or (f"Elapsed {elapsed}" if elapsed else _worker_detail(worker))
    return BackgroundTask("Meeting recorder", "RUNNING", detail)


def _source_filter_task(owner: Any) -> BackgroundTask | None:
    worker = getattr(owner, "_source_filter_worker", None)
    if not _worker_running(worker):
        return None
    mode = str(getattr(owner, "_source_filter_worker_mode", "") or "").strip()
    model = str(getattr(owner, "_source_filter_worker_model", "") or "").strip()
    detail = _stored_task_detail(owner, "Source voice filter")
    detail = detail or " / ".join(part for part in (mode, model) if part) or _worker_detail(worker)
    return BackgroundTask("Source voice filter", "RUNNING", detail)


def _offline_model_task(owner: Any) -> BackgroundTask | None:
    process = getattr(owner, "_offline_model_process", None)
    if process is None:
        return None
    key = str(getattr(owner, "_offline_model_running_key", "") or "").strip()
    detail = _stored_task_detail(owner, "Offline model download")
    detail = detail or (f"Downloading {key}" if key else "Download script is running.")
    return BackgroundTask("Offline model download", "RUNNING", detail)


def _worker_task(owner: Any, name: str, attr_name: str) -> BackgroundTask | None:
    worker = getattr(owner, attr_name, None)
    if not _worker_running(worker):
        return None
    return BackgroundTask(name, "RUNNING", _stored_task_detail(owner, name) or _worker_detail(worker))


def _worker_running(worker: Any) -> bool:
    if worker is None:
        return False
    is_running = getattr(worker, "isRunning", None)
    if callable(is_running):
        return bool(is_running())
    return True


def _worker_detail(worker: Any) -> str:
    name = type(worker).__name__
    return name if name and name != "SimpleNamespace" else "Background worker is active."


def _controller_detail(controller: Any) -> str:
    detail = getattr(controller, "task_detail", None)
    if not callable(detail):
        return ""
    return " ".join(str(detail() or "").split())


def _stored_task_detail(owner: Any, name: str) -> str:
    details = getattr(owner, "_background_task_details", {})
    if not isinstance(details, dict):
        return ""
    return " ".join(str(details.get(name) or "").split())


def _task_stoppers(owner: Any, wait_ms: int):
    return (
        ("Provider preview", lambda: _call_owner_stop(owner, "_stop_provider_preview", wait_ms=wait_ms)),
        ("Runtime preloading", lambda: _call_owner_stop(owner, "_stop_runtime_warmup", wait_ms=wait_ms)),
        ("URL/cache loading", lambda: _call_owner_stop(owner, "_stop_video_url", wait_ms=wait_ms)),
        ("Realtime dubbing", lambda: _call_owner_stop(owner, "_stop_dubbing")),
        ("Export", lambda: _call_owner_stop(owner, "_stop_worker_attr", "_export_worker", wait_ms=wait_ms)),
        ("Meeting recorder", lambda: _call_owner_stop(owner, "_stop_meeting", wait_ms=wait_ms)),
        ("Telegram", lambda: _call_owner_stop(owner, "_stop_worker_attr", "_telegram_worker", wait_ms=wait_ms)),
        (
            "Telegram translation",
            lambda: _call_owner_stop(owner, "_stop_worker_attr", "_telegram_translation_worker", wait_ms=wait_ms),
        ),
        ("Document import", lambda: _call_owner_stop(owner, "_stop_worker_attr", "_document_worker", wait_ms=wait_ms)),
        (
            "Source voice filter",
            lambda: _call_owner_stop(owner, "_stop_worker_attr", "_source_filter_worker", wait_ms=wait_ms),
        ),
        (
            "Playback compatibility",
            lambda: _call_owner_stop(owner, "_stop_worker_attr", "_playback_compat_worker", wait_ms=wait_ms),
        ),
        ("Offline model download", lambda: _call_owner_stop(owner, "_stop_offline_model_process", wait_ms=wait_ms)),
    )


def _call_owner_stop(owner: Any, method_name: str, *args: object, wait_ms: int | None = None) -> bool:
    method = getattr(owner, method_name, None)
    if not callable(method):
        return False
    try:
        if wait_ms is None:
            return bool(method(*args))
        return bool(method(*args, wait_ms=wait_ms))
    except Exception:
        return False
