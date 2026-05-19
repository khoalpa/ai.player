from __future__ import annotations

import logging
import os
import time
from collections.abc import Iterator
from contextlib import contextmanager

_LOGGER = logging.getLogger("ai_player.performance")


def performance_logging_enabled() -> bool:
    return str(os.getenv("AI_PLAYER_PERF_LOG", "")).strip().lower() in {"1", "true", "yes", "on"}


@contextmanager
def measure_stage(worker: str, stage: str, **details: object) -> Iterator[None]:
    started = time.perf_counter()
    try:
        yield
    finally:
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        if performance_logging_enabled():
            suffix = " ".join(f"{key}={value}" for key, value in details.items() if value is not None)
            _LOGGER.info("%s.%s %.1fms %s", worker, stage, elapsed_ms, suffix)
