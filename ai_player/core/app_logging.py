from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from ai_player.core.config import RUNTIME_DIR

_LOGGING_CONFIGURED = False


def get_logger(name: str) -> logging.Logger:
    _configure_logging()
    return logging.getLogger(name)


def _configure_logging() -> None:
    global _LOGGING_CONFIGURED
    if _LOGGING_CONFIGURED:
        return
    log_path = RUNTIME_DIR / "ai-player-runtime.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(log_path, maxBytes=2_000_000, backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logger = logging.getLogger("ai_player")
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)
    logger.propagate = True
    _LOGGING_CONFIGURED = True
