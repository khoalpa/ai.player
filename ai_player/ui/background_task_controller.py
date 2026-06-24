from __future__ import annotations

from typing import Any


class BackgroundTaskController:
    def __init__(self, owner: Any) -> None:
        self._owner = owner
        self._details: dict[str, str] = {}

    @property
    def details(self) -> dict[str, str]:
        return self._details

    @details.setter
    def details(self, value: object) -> None:
        self._details = dict(value) if isinstance(value, dict) else {}

    def set_detail(self, name: str, detail: object, *, log_detail: object | None = None) -> None:
        text = " ".join(str(detail or "").split())
        if not text:
            return
        task_name = str(name)
        self._details[task_name] = text[:500]
        record_task = getattr(self._owner, "_record_task_center_event", None)
        if callable(record_task):
            record_task(task_name, text if log_detail is None else log_detail)

    def clear_detail(self, name: str) -> None:
        self._details.pop(str(name), None)
        refresh_task_center = getattr(self._owner, "_refresh_task_center", None)
        if callable(refresh_task_center):
            refresh_task_center()
