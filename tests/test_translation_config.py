from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from ai_player.core.config import AppConfig
from ai_player.services import translation


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("off", "none"),
        ("offline auto", "nllb_ct2"),
        ("ct2", "nllb_ct2"),
        ("nllb", "nllb"),
        ("anything", "nllb_ct2"),
    ],
)
def test_normalize_translator_provider_aliases(value: str, expected: str) -> None:
    assert translation.normalize_translator_provider(value) == expected


@pytest.mark.parametrize(("source", "expected"), [("ja-JP", "jpn_Jpan"), ("unknown", "eng_Latn")])
def test_local_nllb_source_language_mapping(source: str, expected: str) -> None:
    assert translation.LocalNllbTranslator._source_language(source) == expected


@pytest.mark.parametrize(("target", "expected"), [("en-US", "eng_Latn"), ("xx", "vie_Latn")])
def test_local_nllb_target_language_mapping(target: str, expected: str) -> None:
    assert translation.LocalNllbTranslator(AppConfig(target_language=target))._target_language() == expected


def test_protect_and_restore_preserved_english_terms() -> None:
    config = AppConfig(preserve_english_terms=True, preserved_english_terms="AI, OpenAI")

    protected = translation._protect_english_terms("OpenAI builds AI tools.", config)
    restored = translation._restore_english_terms(protected.text.upper(), protected)

    assert "OpenAI" in restored
    assert "AI" in restored


def test_ctranslate2_model_path_detection(tmp_path) -> None:
    model = tmp_path / "custom-ct2"
    model.mkdir()
    (model / "model.bin").write_text("", encoding="utf-8")
    (model / "shared_vocabulary.json").write_text("{}", encoding="utf-8")

    assert translation.is_ctranslate2_model_path(model)
    assert translation._resolve_ctranslate2_model_path(Path("plain-nllb")).name.endswith("ct2-int8")


def test_effective_translator_provider_uses_ct2_for_ct2_model(tmp_path) -> None:
    model = tmp_path / "custom-ct2"
    model.mkdir()
    (model / "model.bin").write_text("", encoding="utf-8")
    (model / "shared_vocabulary.json").write_text("{}", encoding="utf-8")

    config = AppConfig(translator_provider="nllb", local_translation_model=str(model))

    assert translation.effective_translator_provider(config) == "nllb_ct2"


def test_ctranslate2_translator_preserves_empty_segments(monkeypatch) -> None:
    class FakeTokenizer:
        src_lang = ""

        def __call__(self, text, **_kwargs):
            return SimpleNamespace(input_ids=[[text]])

        def convert_ids_to_tokens(self, ids):
            return ids

        def convert_tokens_to_ids(self, tokens):
            return tokens

        def decode(self, tokens, skip_special_tokens=True):
            return " ".join(tokens)

    class FakeTranslator:
        def __init__(self) -> None:
            self.batches = []

        def translate_batch(self, source_tokens_batch, **_kwargs):
            self.batches.append(source_tokens_batch)
            return [
                SimpleNamespace(hypotheses=[["vie_Latn", "Xin", "chao"]]),
                SimpleNamespace(hypotheses=[["vie_Latn", "The", "gioi"]]),
            ]

    translator = translation.CTranslate2NllbTranslator(AppConfig())
    fake_translator = FakeTranslator()

    def fake_load_model() -> None:
        translator._tokenizer = FakeTokenizer()
        translator._translator = fake_translator

    monkeypatch.setattr(translator, "_load_model", fake_load_model)

    assert translator.translate_many(["Hello", "  ", "World"], "en") == ["Xin chao", "", "The gioi"]
    assert fake_translator.batches == [[["Hello"], ["World"]]]
