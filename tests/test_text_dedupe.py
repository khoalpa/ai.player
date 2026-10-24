from ai_player.domain.text_dedupe import collapse_repeated_phrases


def test_collapse_repeated_comma_clauses() -> None:
    text = "Tôi không biết, tôi không biết, tôi không biết, tôi không biết."

    assert collapse_repeated_phrases(text) == "Tôi không biết."


def test_collapse_repeated_full_token_sequence_without_commas() -> None:
    text = "tôi không biết tôi không biết tôi không biết"

    assert collapse_repeated_phrases(text) == "tôi không biết"


def test_collapse_repeated_phrases_keeps_short_double_repetition() -> None:
    text = "Không, không."

    assert collapse_repeated_phrases(text) == text
