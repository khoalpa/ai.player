from __future__ import annotations

import math
import threading
from collections import Counter, defaultdict, deque
from dataclasses import dataclass


@dataclass(frozen=True)
class RuntimeTelemetrySnapshot:
    counters: dict[str, int]
    stage_p95_ms: dict[str, float]


class RuntimeTelemetry:
    def __init__(self, *, sample_limit: int = 100) -> None:
        self._sample_limit = max(1, int(sample_limit))
        self._counters: Counter[str] = Counter()
        self._stage_samples: dict[str, deque[float]] = defaultdict(lambda: deque(maxlen=self._sample_limit))
        self._lock = threading.Lock()

    def increment(self, name: object, amount: int = 1) -> None:
        key = str(name or "").strip()
        if not key:
            return
        with self._lock:
            self._counters[key] += max(0, int(amount))

    def observe_stage(self, worker: object, stage: object, elapsed_ms: object) -> None:
        key = ".".join(part for part in (str(worker or "").strip(), str(stage or "").strip()) if part)
        try:
            value = float(elapsed_ms)
        except (TypeError, ValueError, OverflowError):
            return
        if not key or not math.isfinite(value) or value < 0:
            return
        with self._lock:
            self._stage_samples[key].append(value)

    def snapshot(self) -> RuntimeTelemetrySnapshot:
        with self._lock:
            counters = dict(self._counters)
            samples = {key: tuple(values) for key, values in self._stage_samples.items()}
        return RuntimeTelemetrySnapshot(
            counters=counters,
            stage_p95_ms={key: _percentile_95(values) for key, values in samples.items() if values},
        )

    def reset(self) -> None:
        with self._lock:
            self._counters.clear()
            self._stage_samples.clear()


def _percentile_95(values: tuple[float, ...]) -> float:
    ordered = sorted(values)
    index = max(0, math.ceil(len(ordered) * 0.95) - 1)
    return ordered[index]


RUNTIME_TELEMETRY = RuntimeTelemetry()


def format_runtime_telemetry(snapshot: RuntimeTelemetrySnapshot, language_id: object = "vi") -> str:
    counters = snapshot.counters
    latencies = snapshot.stage_p95_ms
    language = str(language_id or "vi").lower()
    is_vietnamese = language.startswith("vi") or "vietnam" in language
    underruns = counters.get("dubbing.buffer_underrun", 0)
    fallbacks = sum(value for key, value in counters.items() if key.endswith("fallback"))
    labels = (
        ("Pipeline", "khựng", "dự phòng", "P95") if is_vietnamese else ("Pipeline", "underruns", "fallbacks", "P95")
    )
    slowest = sorted(latencies.items(), key=lambda item: item[1], reverse=True)[:3]
    latency_text = ", ".join(f"{key} {value:.0f} ms" for key, value in slowest) or "—"
    return f"{labels[0]}: {labels[1]} {underruns}, {labels[2]} {fallbacks}; {labels[3]}: {latency_text}"
