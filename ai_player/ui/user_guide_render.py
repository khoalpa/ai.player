"""Small render helpers for trusted User Guide HTML fragments."""

from __future__ import annotations

from collections.abc import Iterable, Sequence


def html_items(items: Iterable[str]) -> str:
    return "".join(f"<li>{item}</li>" for item in items)


def html_list(items: Iterable[str], *, ordered: bool = False) -> str:
    tag = "ol" if ordered else "ul"
    return f"<{tag}>{html_items(items)}</{tag}>"


def table_rows(rows: Iterable[Sequence[str]]) -> str:
    return "\n".join(
        "<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>"
        for row in rows
    )
