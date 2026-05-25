from __future__ import annotations

import math


def clean_message(value: object) -> str:
    return str(value or "").encode("utf-8", errors="replace").decode("utf-8", errors="replace")


def clean_text(value: object) -> str:
    return " ".join(clean_message(value).split())


def finite_float(value: object, *, default: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return default
    return number if math.isfinite(number) else default


def optional_float(value: object) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def int_value(value: object, *, default: int, minimum: int | None = None) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError, OverflowError):
        number = default
    return max(minimum, number) if minimum is not None else number


def optional_int(value: object) -> int | None:
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return None


def positive_int(value: object, *, default: int) -> int:
    return int_value(value, default=default, minimum=1)
