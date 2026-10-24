from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from ai_player.adapters.ai import translation
from ai_player.configuration import DEFAULT_PRESERVED_SOURCE_TERMS, AppConfig


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("off", "none"),
        ("offline auto", "nllb"),
        ("azure", "azure_translator"),
        ("google", "google_translate"),
        ("deepl", "deepl"),
        ("ct2", "nllb"),
        ("nllb", "nllb"),
        ("anything", "nllb"),
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


class FakeResponse:
    def __init__(self, payload, status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code
        self.text = str(payload)

    def json(self):
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            import requests

            raise requests.HTTPError(response=self)


def test_azure_translator_posts_batch(monkeypatch) -> None:
    calls = []

    def fake_request(method, url, **kwargs):
        calls.append((method, url, kwargs))
        return FakeResponse(
            [
                {"translations": [{"text": "Xin chao"}]},
                {"translations": [{"text": "The gioi"}]},
            ]
        )

    monkeypatch.setattr(translation.requests, "request", fake_request)
    translator = translation.OnlineTranslator(
        AppConfig(
            translator_provider="azure_translator",
            translator_api_key="azure-key",
            translator_api_region="eastus",
        )
    )

    assert translator.translate_many(["Hello", "World"], "en") == ["Xin chao", "The gioi"]
    method, url, kwargs = calls[0]
    assert method == "POST"
    assert url.endswith("/translate")
    assert kwargs["params"] == {"api-version": "3.0", "to": "vi", "from": "en"}
    assert kwargs["headers"]["Ocp-Apim-Subscription-Key"] == "azure-key"
    assert kwargs["headers"]["Ocp-Apim-Subscription-Region"] == "eastus"


def test_google_translate_posts_batch(monkeypatch) -> None:
    calls = []

    def fake_request(method, url, **kwargs):
        calls.append((method, url, kwargs))
        return FakeResponse({"data": {"translations": [{"translatedText": "Xin &amp; chao"}]}})

    monkeypatch.setattr(translation.requests, "request", fake_request)
    translator = translation.OnlineTranslator(
        AppConfig(translator_provider="google_translate", translator_api_key="google-key")
    )

    assert translator.translate_many(["Hello"], None) == ["Xin & chao"]
    _method, _url, kwargs = calls[0]
    assert kwargs["params"] == {"key": "google-key"}
    assert kwargs["json"] == {"q": ["Hello"], "target": "vi", "format": "text"}


def test_online_translation_error_uses_provider_message(monkeypatch) -> None:
    def fake_request(_method, _url, **_kwargs):
        return FakeResponse(
            {
                "error": {
                    "code": 400,
                    "message": "API key not valid. Please pass a valid API key.",
                    "errors": [{"reason": "badRequest"}],
                }
            },
            status_code=400,
        )

    monkeypatch.setattr(translation.requests, "request", fake_request)
    translator = translation.OnlineTranslator(
        AppConfig(translator_provider="google_translate", translator_api_key="bad-key")
    )

    with pytest.raises(translation.TranslationError) as error:
        translator.translate_many(["Hello"], "en")

    message = str(error.value)
    assert "API key not valid" in message
    assert "errors" not in message


def test_online_translation_error_redacts_response_text_secret(monkeypatch) -> None:
    def fake_request(_method, _url, **_kwargs):
        return FakeResponse(
            "failed https://translation.googleapis.com/language/translate/v2?key=bad-key",
            status_code=400,
        )

    monkeypatch.setattr(translation.requests, "request", fake_request)
    translator = translation.OnlineTranslator(
        AppConfig(translator_provider="google_translate", translator_api_key="bad-key")
    )

    with pytest.raises(translation.TranslationError) as error:
        translator.translate_many(["Hello"], "en")

    message = str(error.value)
    assert "bad-key" not in message
    assert "key=[redacted]" in message


def test_deepl_translate_posts_batch(monkeypatch) -> None:
    calls = []

    def fake_post(url, **kwargs):
        calls.append((url, kwargs))
        return FakeResponse({"translations": [{"text": "Hallo"}, {"text": "Welt"}]})

    monkeypatch.setattr(translation.requests, "post", fake_post)
    translator = translation.OnlineTranslator(
        AppConfig(translator_provider="deepl", translator_api_key="deepl-key", target_language="de")
    )

    assert translator.translate_many(["Hello", "World"], "en") == ["Hallo", "Welt"]
    url, kwargs = calls[0]
    assert url == "https://api-free.deepl.com/v2/translate"
    assert kwargs["headers"] == {"Authorization": "DeepL-Auth-Key deepl-key"}
    assert kwargs["data"] == {"text": ["Hello", "World"], "target_lang": "DE", "source_lang": "EN"}


def test_protect_and_restore_preserved_english_terms() -> None:
    config = AppConfig(preserve_english_terms=True, preserved_english_terms="AI, OpenAI")

    protected = translation._protect_english_terms("OpenAI builds AI tools.", config)
    restored = translation._restore_english_terms(protected.text.upper(), protected)

    assert "OpenAI" in restored
    assert "AI" in restored


def test_protect_and_restore_preserved_source_language_terms() -> None:
    config = AppConfig(preserve_source_terms=True, preserved_source_terms="先生, 오빠, OpenAI")

    protected = translation._protect_english_terms("先生 meets 오빠 at OpenAI.", config)
    restored = translation._restore_english_terms(protected.text.upper(), protected)

    assert "先生" in restored
    assert "오빠" in restored
    assert "OpenAI" in restored


def test_bilingual_glossary_restores_approved_vietnamese_term() -> None:
    config = AppConfig(
        preserve_source_terms=True,
        preserved_source_terms="人工智能 = trí tuệ nhân tạo\n师傅 => sư phụ",
        preserved_english_terms="",
    )

    protected = translation._protect_english_terms("人工智能由师傅讲解。", config)
    restored = translation._restore_english_terms(protected.text.upper(), protected)

    assert restored == "trí tuệ nhân tạo由sư phụ讲解。"


def test_glossary_prefers_longest_source_term() -> None:
    entries = translation._glossary_entries("人工=nhân công\n人工智能=trí tuệ nhân tạo")

    assert [entry.source for entry in entries] == ["人工智能", "人工"]


def test_chinese_to_vietnamese_translation_polishes_punctuation() -> None:
    assert (
        translation._polish_target_text("Xin chào ， thế giới！ （ thử nghiệm ）", "zh-CN", "vi")
        == "Xin chào, thế giới! (thử nghiệm)"
    )


def test_translation_polish_does_not_change_other_language_pairs() -> None:
    text = "Hello ， world！"

    assert translation._polish_target_text(text, "en", "vi") == text


def test_chinese_translation_protects_numbers_dates_and_percentages() -> None:
    config = AppConfig(preserve_source_terms=True, preserved_source_terms="", preserved_english_terms="")

    protected = translation._protect_english_terms("价格是 3.5 元，增长 15%，日期 2026.10.12。", config, "zh")
    restored = translation._restore_english_terms(protected.text.upper(), protected)

    assert "3.5" in restored
    assert "15%" in restored
    assert "2026.10.12" in restored


def test_legacy_english_terms_are_still_used_as_source_terms() -> None:
    config = AppConfig(
        preserve_source_terms=True,
        preserved_source_terms="",
        preserve_english_terms=True,
        preserved_english_terms="LegacyTerm",
    )

    protected = translation._protect_english_terms("LegacyTerm should stay.", config)

    assert protected.replacements == (("zxqterm0zxq", "LegacyTerm"),)


def test_source_terms_flag_is_canonical_over_legacy_english_terms_flag() -> None:
    config = AppConfig(
        preserve_source_terms=True,
        preserved_source_terms="OpenAI",
        preserve_english_terms=False,
        preserved_english_terms="OpenAI",
    )

    protected = translation._protect_english_terms("OpenAI should translate naturally.", config)

    assert protected.replacements == (("zxqterm0zxq", "OpenAI"),)


def test_preserved_source_default_does_not_include_single_cjk_terms() -> None:
    terms = translation._preserved_terms(DEFAULT_PRESERVED_SOURCE_TERMS)

    assert "道" not in terms
    assert "气" not in terms


def test_preserved_term_validator_requests_retry_for_broken_placeholder() -> None:
    config = AppConfig(preserve_source_terms=True, preserved_source_terms="OpenAI")
    protected = translation._protect_english_terms("OpenAI builds tools.", config)

    assert translation._needs_preserved_term_retry("zxqterm99zxq xây dựng công cụ.", protected)


def test_preserved_term_validator_requests_retry_for_missing_term() -> None:
    config = AppConfig(preserve_source_terms=True, preserved_source_terms="OpenAI")
    protected = translation._protect_english_terms("OpenAI builds tools.", config)

    assert translation._needs_preserved_term_retry("Công ty xây dựng công cụ.", protected)


def test_select_preserved_translation_prefers_valid_retry() -> None:
    config = AppConfig(preserve_source_terms=True, preserved_source_terms="OpenAI")
    protected = translation._protect_english_terms("OpenAI builds tools.", config)

    assert (
        translation._select_preserved_translation("Công ty xây dựng công cụ.", "OpenAI xây dựng công cụ.", protected)
        == "OpenAI xây dựng công cụ."
    )


def test_ctranslate2_model_path_detection(tmp_path) -> None:
    model = tmp_path / "custom-ct2"
    model.mkdir()
    (model / "model.bin").write_text("", encoding="utf-8")
    (model / "shared_vocabulary.json").write_text("{}", encoding="utf-8")

    assert translation.is_ctranslate2_model_path(model)
    assert translation._resolve_ctranslate2_model_path(Path("plain-nllb")).name.endswith("ct2-int8")


def test_effective_translator_provider_does_not_restore_removed_ct2_provider(tmp_path) -> None:
    model = tmp_path / "custom-ct2"
    model.mkdir()
    (model / "model.bin").write_text("", encoding="utf-8")
    (model / "shared_vocabulary.json").write_text("{}", encoding="utf-8")

    config = AppConfig(translator_provider="nllb", local_translation_model=str(model))

    assert translation.effective_translator_provider(config) == "nllb"


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


def test_ctranslate2_translator_sanitizes_invalid_numeric_config(monkeypatch) -> None:
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
            self.kwargs = None

        def translate_batch(self, _source_tokens_batch, **kwargs):
            self.kwargs = kwargs
            return [SimpleNamespace(hypotheses=[["vie_Latn", "Xin"]])]

    translator = translation.CTranslate2NllbTranslator(
        AppConfig(translation_num_beams="bad", translation_max_tokens=float("nan"))
    )
    fake_translator = FakeTranslator()

    def fake_load_model() -> None:
        translator._tokenizer = FakeTokenizer()
        translator._translator = fake_translator

    monkeypatch.setattr(translator, "_load_model", fake_load_model)

    assert translator.translate_many(["Hello"], "en") == ["Xin"]
    assert fake_translator.kwargs["beam_size"] == 2
    assert fake_translator.kwargs["max_decoding_length"] == 152


def test_ctranslate2_translator_retries_broken_preserved_terms(monkeypatch) -> None:
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
            joined = [" ".join(tokens) for tokens in source_tokens_batch]
            if any("zxqterm" in text for text in joined):
                return [SimpleNamespace(hypotheses=[["vie_Latn", "zxqterm99zxq", "xây", "dựng"]])]
            return [SimpleNamespace(hypotheses=[["vie_Latn", "OpenAI", "xây", "dựng"]])]

    translator = translation.CTranslate2NllbTranslator(
        AppConfig(preserve_source_terms=True, preserved_source_terms="OpenAI")
    )
    fake_translator = FakeTranslator()

    def fake_load_model() -> None:
        translator._tokenizer = FakeTokenizer()
        translator._translator = fake_translator

    monkeypatch.setattr(translator, "_load_model", fake_load_model)

    assert translator.translate_many(["OpenAI builds"], "en") == ["OpenAI xây dựng"]
    assert fake_translator.batches == [[["zxqterm0zxq builds"]], [["OpenAI builds"]]]
