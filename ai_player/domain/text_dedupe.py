from __future__ import annotations

import re

_CLAUSE_RE = re.compile(r"([^,;.!?。！？，；]+)([,;.!?。！？，；]*\s*)")
_TOKEN_RE = re.compile(r"\w+", re.UNICODE)
_SPACE_BEFORE_PUNCT_RE = re.compile(r"\s+([,;.!?。！？，；])")


def collapse_repeated_phrases(text: object, *, min_repetitions: int = 3) -> str:
    value = str(text or "").strip()
    if not value:
        return ""
    collapsed = _collapse_repeated_clauses(value, min_repetitions=min_repetitions)
    if collapsed != value:
        return collapsed
    return _collapse_full_token_repetition(value, min_repetitions=min_repetitions)


def _collapse_repeated_clauses(text: str, *, min_repetitions: int) -> str:
    parts = [(match.group(1), match.group(2)) for match in _CLAUSE_RE.finditer(text)]
    if len(parts) < min_repetitions:
        return text

    result: list[str] = []
    index = 0
    changed = False
    while index < len(parts):
        clause, separator = parts[index]
        key = _normalized_phrase(clause)
        run_end = index + 1
        while run_end < len(parts) and key and _normalized_phrase(parts[run_end][0]) == key:
            run_end += 1

        run_length = run_end - index
        if key and _eligible_phrase(key) and run_length >= min_repetitions:
            final_separator = parts[run_end - 1][1]
            result.append(f"{clause.strip()}{final_separator or separator}")
            changed = True
        else:
            result.extend(
                f"{part_clause.strip()}{part_separator}" for part_clause, part_separator in parts[index:run_end]
            )
        index = run_end

    if not changed:
        return text
    return _cleanup_spacing(" ".join(part.strip() for part in result if part.strip()))


def _collapse_full_token_repetition(text: str, *, min_repetitions: int) -> str:
    tokens = _TOKEN_RE.findall(text)
    if len(tokens) < min_repetitions * 2:
        return text
    lowered = [token.casefold() for token in tokens]
    for phrase_len in range(2, (len(tokens) // min_repetitions) + 1):
        if len(tokens) % phrase_len:
            continue
        phrase = lowered[:phrase_len]
        if not _eligible_phrase(" ".join(phrase)):
            continue
        if all(lowered[start : start + phrase_len] == phrase for start in range(0, len(tokens), phrase_len)):
            suffix = "." if text.rstrip().endswith((".", "!", "?", "。", "！", "？")) else ""
            return _cleanup_spacing(f"{' '.join(tokens[:phrase_len])}{suffix}")
    return text


def _normalized_phrase(text: str) -> str:
    return " ".join(_TOKEN_RE.findall(text.casefold()))


def _eligible_phrase(normalized: str) -> bool:
    words = normalized.split()
    return len(words) >= 2 and len(normalized) >= 8


def _cleanup_spacing(text: str) -> str:
    return _SPACE_BEFORE_PUNCT_RE.sub(r"\1", " ".join(text.split()))
