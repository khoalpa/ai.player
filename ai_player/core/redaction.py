from __future__ import annotations

import json
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

REDACTED = "[redacted]"
SENSITIVE_QUERY_KEYS = {
    "access_token",
    "apikey",
    "api-key",
    "api_key",
    "auth",
    "authorization",
    "client_secret",
    "code",
    "credential",
    "key",
    "password",
    "secret",
    "signature",
    "sig",
    "token",
    "x-goog-api-key",
}

_URL_RE = re.compile(r"https?://[^\s<>'\")\]]+")
_BEARER_RE = re.compile(r"(?i)\b(Bearer\s+)[A-Za-z0-9._~+/=-]+")
_AUTH_HEADER_RE = re.compile(
    r"(?i)\b("
    r"Authorization|Ocp-Apim-Subscription-Key|X-goog-api-key|api[-_]?key|key|access[-_]?token|"
    r"refresh[-_]?token|client[-_]?secret|password|secret"
    r")(\s*[:=]\s*)(['\"]?)([^,'\"\s}\]]+)(\3)"
)
_DEEPL_RE = re.compile(r"(?i)\b(DeepL-Auth-Key\s+)[A-Za-z0-9:_-]+")
_AWS_CREDENTIAL_RE = re.compile(r"(?i)\b(Credential=)[^,\s]+")
_JSON_SECRET_RE = re.compile(
    r"(?i)(['\"](?:authorization|ocp-apim-subscription-key|x-goog-api-key|api[-_]?key|key|access[-_]?token|"
    r"refresh[-_]?token|client[-_]?secret|password|secret|token)['\"]"
    r"\s*:\s*)(['\"])(.*?)(\2)"
)


def redact_secrets(value: object) -> str:
    text = _stringify(value)
    if not text:
        return text
    text = _URL_RE.sub(lambda match: _redact_url(match.group(0)), text)
    text = _BEARER_RE.sub(rf"\1{REDACTED}", text)
    text = _DEEPL_RE.sub(rf"\1{REDACTED}", text)
    text = _AWS_CREDENTIAL_RE.sub(rf"\1{REDACTED}", text)
    text = _JSON_SECRET_RE.sub(rf"\1\2{REDACTED}\4", text)
    text = _AUTH_HEADER_RE.sub(rf"\1\2\3{REDACTED}\5", text)
    return text


def compact_redacted_text(value: object, *, max_length: int = 500, strip_html: bool = False) -> str:
    text = _stringify(value)
    if strip_html:
        text = re.sub(r"<[^>]+>", " ", text)
    text = " ".join(text.split())
    text = redact_secrets(text)
    return text[:max_length]


def redacted_json_text(value: object, *, max_length: int = 500) -> str:
    try:
        text = json.dumps(value, ensure_ascii=False)
    except Exception:
        text = _stringify(value)
    return compact_redacted_text(text, max_length=max_length)


def _redact_url(url: str) -> str:
    try:
        parts = urlsplit(url)
    except Exception:
        return url
    if not parts.query:
        return url
    query = []
    for key, value in parse_qsl(parts.query, keep_blank_values=True):
        redacted = REDACTED if key.strip().lower() in SENSITIVE_QUERY_KEYS else value
        query.append((key, redacted))
    query_text = urlencode(query).replace("%5Bredacted%5D", REDACTED)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, query_text, parts.fragment))


def _stringify(value: object) -> str:
    if value is None:
        return ""
    return str(value)
