from __future__ import annotations

import sys
from collections.abc import Iterator
from contextlib import contextmanager

UNNEEDED_TRANSFORMERS_OPTIONAL_IMPORTS = ("sklearn", "pandas", "pyarrow")


@contextmanager
def block_unneeded_transformers_optional_imports() -> Iterator[None]:
    previous = {}
    for module_name in UNNEEDED_TRANSFORMERS_OPTIONAL_IMPORTS:
        previous[module_name] = sys.modules.get(module_name, ...)
        sys.modules[module_name] = None
    try:
        yield
    finally:
        for module_name, module in previous.items():
            if module is ...:
                sys.modules.pop(module_name, None)
            else:
                sys.modules[module_name] = module


def install_unneeded_transformers_optional_import_blocks() -> None:
    for module_name in UNNEEDED_TRANSFORMERS_OPTIONAL_IMPORTS:
        sys.modules.setdefault(module_name, None)
