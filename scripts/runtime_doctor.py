from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ai_player.core.runtime_diagnostics import collect_runtime_diagnostics, format_runtime_diagnostics


def main() -> int:
    parser = argparse.ArgumentParser(description="Check AI Player runtime dependencies.")
    parser.add_argument("--ci", action="store_true", help="Skip checks that are noisy in CI.")
    parser.add_argument(
        "--profile",
        choices=("lite", "offline-ai"),
        default="offline-ai",
        help="Dependency profile to treat as required.",
    )
    args = parser.parse_args()
    report = collect_runtime_diagnostics(include_audio_devices=not args.ci, profile=args.profile)
    print(format_runtime_diagnostics(report))
    return 1 if report.failure_count else 0


if __name__ == "__main__":
    raise SystemExit(main())
