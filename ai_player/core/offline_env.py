from __future__ import annotations

import os
import threading
from dataclasses import dataclass

HF_OFFLINE_ENV_VARS = (
    "HF_HUB_OFFLINE",
    "TRANSFORMERS_OFFLINE",
    "HF_DATASETS_OFFLINE",
)

_LOCK = threading.RLock()
_DEPTH = 0
_SAVED_VALUES: dict[str, str | None] = {}


@dataclass(frozen=True)
class OfflineEnvironmentToken:
    enabled: bool


def push_hf_offline_environment(enabled: bool) -> OfflineEnvironmentToken:
    if not enabled:
        return OfflineEnvironmentToken(enabled=False)

    global _DEPTH, _SAVED_VALUES
    with _LOCK:
        if _DEPTH == 0:
            _SAVED_VALUES = {name: os.environ.get(name) for name in HF_OFFLINE_ENV_VARS}
        for name in HF_OFFLINE_ENV_VARS:
            os.environ[name] = "1"
        _DEPTH += 1
    return OfflineEnvironmentToken(enabled=True)


def pop_hf_offline_environment(token: OfflineEnvironmentToken) -> None:
    if not token.enabled:
        return

    global _DEPTH, _SAVED_VALUES
    with _LOCK:
        if _DEPTH <= 0:
            return
        _DEPTH -= 1
        if _DEPTH != 0:
            return
        for name, value in _SAVED_VALUES.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
        _SAVED_VALUES = {}
