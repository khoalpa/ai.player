"""Adapt small pre-existing UI test doubles to the feature context contract.

Real windows are always exercised through their actual composed features.
This helper supplies only bindings already present on a test double.
"""

from __future__ import annotations

from ai_player.ui.features.context import BINDINGS

_MISSING = object()


class _Bindings:
    def __init__(self, owner, path=""):
        object.__setattr__(self, "_owner", owner)
        object.__setattr__(self, "_path", path)

    def __getattr__(self, name):
        path = f"{self._path}.{name}" if self._path else name
        if path == "window":
            return self._owner
        exact = [key for key, value in BINDINGS.items() if value == path]
        for key in exact:
            if hasattr(self._owner, key):
                return getattr(self._owner, key)
        for key, route in BINDINGS.items():
            if path.startswith(route + ".") and hasattr(self._owner, key):
                value = getattr(self._owner, key)
                for part in path[len(route) + 1 :].split("."):
                    value = getattr(value, part)
                return value
        if any(route.startswith(path + ".") for route in BINDINGS.values()):
            return _Bindings(self._owner, path)
        raise AttributeError(path)

    def __setattr__(self, name, value):
        path = f"{self._path}.{name}" if self._path else name
        matches = [key for key, route in BINDINGS.items() if route == path]
        if not matches:
            raise AttributeError(path)
        setattr(self._owner, matches[0], value)

    def get(self, name, default=_MISSING):
        if default is _MISSING:
            return getattr(self._owner, name)
        return getattr(self._owner, name, default)

    def has(self, name):
        return hasattr(self._owner, name)

    def set(self, name, value):
        setattr(self._owner, name, value)


def context_for(owner):
    return owner.features if hasattr(owner, "features") else _Bindings(owner)
