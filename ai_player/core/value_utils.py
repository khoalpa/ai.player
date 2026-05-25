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


def nonnegative_float(value: object, *, default: float) -> float:
    return max(0.0, finite_float(value, default=default))


def clamped_float(value: object, *, minimum: float, maximum: float, default: float | None = None) -> float:
    numeric = finite_float(value, default=minimum if default is None else default)
    return max(minimum, min(maximum, numeric))


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
