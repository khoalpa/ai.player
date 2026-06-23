from __future__ import annotations

import logging

from ai_player.core.app_logging import _RedactionFilter
from ai_player.core.redaction import REDACTED, compact_redacted_text, redact_secrets, redacted_json_text
from ai_player.services import tts_base
from ai_player.workers import worker_values


def test_redact_secrets_hides_query_keys_in_urls() -> None:
    message = (
        "GET https://translation.googleapis.com/language/translate/v2?"
        "key=google-secret&q=hello&access_token=token-secret failed"
    )

    redacted = redact_secrets(message)

    assert "google-secret" not in redacted
    assert "token-secret" not in redacted
    assert f"key={REDACTED}" in redacted
    assert f"access_token={REDACTED}" in redacted
    assert "q=hello" in redacted


def test_redact_secrets_hides_common_header_and_body_tokens() -> None:
    message = (
        "Authorization: Bearer bearer-secret "
        "DeepL-Auth-Key deepl-secret "
        "Ocp-Apim-Subscription-Key=azure-secret "
        '{"api_key": "json-secret", "message": "bad key"} '
        "{'Ocp-Apim-Subscription-Key': 'dict-azure-secret', 'key': 'dict-key-secret'} "
        "Authorization=AWS4-HMAC-SHA256 Credential=aws-access/20260623/us-east-1/polly/aws4_request"
    )

    redacted = redact_secrets(message)

    assert "bearer-secret" not in redacted
    assert "deepl-secret" not in redacted
    assert "azure-secret" not in redacted
    assert "json-secret" not in redacted
    assert "dict-azure-secret" not in redacted
    assert "dict-key-secret" not in redacted
    assert "aws-access" not in redacted
    assert redacted.count(REDACTED) >= 7


def test_compact_redacted_text_strips_html_and_limits_detail() -> None:
    text = "<html><body>bad key=google-secret</body></html>" + (" x" * 300)

    redacted = compact_redacted_text(text, max_length=80, strip_html=True)

    assert "google-secret" not in redacted
    assert "key=[redacted]" in redacted
    assert "<html>" not in redacted
    assert len(redacted) == 80


def test_redacted_json_text_redacts_nested_secret_values() -> None:
    redacted = redacted_json_text({"error": {"message": "failed", "token": "secret-token"}})

    assert "secret-token" not in redacted
    assert f'"token": "{REDACTED}"' in redacted


def test_logging_filter_redacts_exception_args_and_message() -> None:
    record = logging.LogRecord(
        "ai_player.test",
        logging.ERROR,
        __file__,
        1,
        "Request failed for %s: %s",
        (
            "https://example.test/path?key=url-secret",
            RuntimeError("Authorization: Bearer exception-secret"),
        ),
        None,
    )

    _RedactionFilter().filter(record)
    message = record.getMessage()

    assert "url-secret" not in message
    assert "exception-secret" not in message
    assert REDACTED in message


def test_worker_and_tts_message_helpers_redact_exceptions() -> None:
    exc = RuntimeError("request failed https://example.test/path?key=helper-secret")

    worker_message = worker_values.clean_message(exc)
    tts_message = tts_base.clean_message(exc)

    assert "helper-secret" not in worker_message
    assert "helper-secret" not in tts_message
    assert "key=[redacted]" in worker_message
    assert "key=[redacted]" in tts_message
