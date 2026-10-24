from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from ai_player.configuration import RUNTIME_DIR
from ai_player.core.redaction import redact_secrets

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
    handler.addFilter(_RedactionFilter())
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logger = logging.getLogger("ai_player")
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)
    logger.propagate = True
    _LOGGING_CONFIGURED = True


class _RedactionFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact_secrets(record.msg)
        if record.args:
            if isinstance(record.args, dict):
                record.args = {key: _redact_log_arg(value) for key, value in record.args.items()}
            else:
                record.args = tuple(_redact_log_arg(value) for value in record.args)
        return True


def _redact_log_arg(value: object) -> object:
    if isinstance(value, str):
        return redact_secrets(value)
    if isinstance(value, Exception):
        return redact_secrets(value)
    if isinstance(value, Path):
        return value
    if isinstance(value, int | float | bool) or value is None:
        return value
    return redact_secrets(value)
