from __future__ import annotations

import sys
from typing import TextIO


def prefer_utf8_stdio(*streams: TextIO | None) -> None:
    targets = streams or (sys.stdout,)
    for stream in targets:
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8", errors="replace")
