"""Synchronous workflow events. UI dispatch belongs to the Qt adapter."""

from __future__ import annotations

from collections.abc import Callable
from threading import RLock

from ai_player.application.jobs import CancellationToken


class EventChannel:
    def __init__(self) -> None:
        self._listeners: list[Callable] = []
        self._lock = RLock()

    def connect(self, listener: Callable) -> None:
        with self._lock:
            self._listeners.append(listener)

    def disconnect(self, listener: Callable) -> None:
        with self._lock:
            self._listeners.remove(listener)

    def emit(self, *args: object) -> None:
        with self._lock:
            listeners = tuple(self._listeners)
        for listener in listeners:
            listener(*args)


class Event:
    """Declare an event without binding workflow code to a GUI framework."""

    def __init__(self, *argument_types: type) -> None:
        self.argument_types = argument_types
        self._name = ""

    def __set_name__(self, owner: type, name: str) -> None:
        self._name = "_event_" + name

    def __get__(self, instance, owner=None):
        if instance is None:
            return self
        if self._name not in instance.__dict__:
            instance.__dict__[self._name] = EventChannel()
        return instance.__dict__[self._name]


class Workflow:
    """Single-run workflow with cooperative cancellation and immutable config."""

    def __init__(self, parent=None, *, dependencies: object = None) -> None:
        self.cancellation = CancellationToken()
        self.dependencies = dependencies

    @property
    def _stop_requested(self) -> bool:
        return self.cancellation.cancelled

    @_stop_requested.setter
    def _stop_requested(self, value: bool) -> None:
        if value:
            self.cancellation.cancel()

    def requestInterruption(self) -> None:
        self.cancellation.cancel()

    def isInterruptionRequested(self) -> bool:
        return self.cancellation.cancelled

    def stop(self) -> None:
        self.cancellation.cancel()

    def failure_arguments(self, error: Exception) -> tuple[str, ...]:
        return (str(error),)
