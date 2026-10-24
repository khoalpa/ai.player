from __future__ import annotations

from collections.abc import Callable


class BackgroundTaskController:
    def __init__(
        self,
        *,
        record_event: Callable[[str, object], None],
        refresh: Callable[[], None],
    ) -> None:
        self._record_event = record_event
        self._refresh = refresh
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
        self._record_event(task_name, text if log_detail is None else log_detail)

    def clear_detail(self, name: str) -> None:
        self._details.pop(str(name), None)
        self._refresh()
