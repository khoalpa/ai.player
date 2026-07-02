from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse


def recent_source_label(source: str, *, max_length: int = 48) -> str:
    value = str(source or "").strip()
    parsed = urlparse(value)
    if parsed.netloc:
        label = f"{parsed.netloc}{parsed.path}"
    else:
        label = Path(value).name or value
    return label if len(label) <= max_length else f"...{label[-(max_length - 3):]}"
