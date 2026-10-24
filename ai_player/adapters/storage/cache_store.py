"""Bounded artifact caches with process-local leases for active files."""

from __future__ import annotations

import os
import shutil
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

_LOCK = threading.RLock()
_LEASES: dict[Path, int] = {}


class ArtifactCache:
    def __init__(self, root: Path) -> None:
        self.root = Path(root).resolve()

    def _checked(self, path: Path) -> Path:
        path = Path(path).resolve()
        if path.parent != self.root:
            raise ValueError("Cache entry must be a direct child of its cache directory")
        return path

    @contextmanager
    def lease(self, path: Path) -> Iterator[Path]:
        path = self._checked(path)
        with _LOCK:
            _LEASES[path] = _LEASES.get(path, 0) + 1
        try:
            yield path
        finally:
            with _LOCK:
                _LEASES[path] -= 1
                if not _LEASES[path]:
                    del _LEASES[path]

    def publish(self, source: Path, destination: Path) -> None:
        destination = self._checked(destination)
        self.root.mkdir(parents=True, exist_ok=True)
        temporary = self.root / (uuid4().hex + ".tmp")
        try:
            shutil.copyfile(source, temporary)
            os.replace(temporary, destination)
        finally:
            temporary.unlink(missing_ok=True)

    def prune(self, *, max_bytes: int, max_age_seconds: float | None = None) -> int:
        """Remove oldest unused entries; never follow links out of the cache."""
        removed = 0
        with _LOCK:
            entries = []
            for path in self.root.glob("*"):
                if path.is_symlink() or not path.is_file() or path.suffix == ".tmp":
                    continue
                try:
                    stat = path.stat()
                    entries.append((stat.st_mtime, stat.st_size, path))
                except OSError:
                    continue
            total = sum(size for _, size, _ in entries)
            now = time.time()
            for modified, size, path in sorted(entries):
                expired = max_age_seconds is not None and now - modified > max_age_seconds
                if (total <= max(0, max_bytes) and not expired) or path in _LEASES:
                    continue
                try:
                    path.unlink()
                except OSError:
                    continue
                total -= size
                removed += 1
        return removed
