from __future__ import annotations

from importlib import import_module
from types import ModuleType


def import_vieneu_utils(module_name: str) -> ModuleType:
    """Import bundled vieneu_utils both as an installed package and in-app package data."""
    try:
        return import_module(f"vieneu_utils.{module_name}")
    except ModuleNotFoundError as exc:
        if exc.name != "vieneu_utils":
            raise
        return import_module(f"..vieneu_utils.{module_name}", package=__package__)
