from __future__ import annotations

from dataclasses import dataclass

from ai_player.core.redaction import redact_secrets
from ai_player.core.value_utils import clean_message

MODEL_NOT_FOUND = "MODEL_NOT_FOUND"
FFMPEG_FAILED = "FFMPEG_FAILED"
TTS_PROVIDER_FAILED = "TTS_PROVIDER_FAILED"
ASR_RUNTIME_FAILED = "ASR_RUNTIME_FAILED"
EXPORT_OUTPUT_MISSING = "EXPORT_OUTPUT_MISSING"


@dataclass(slots=True)
class RuntimeErrorInfo:
    code: str
    message: str
    detail: str = ""


class CodedRuntimeError(RuntimeError):
    def __init__(self, code: str, message: str, *, detail: object = "") -> None:
        self.code = str(code or "").strip() or "RUNTIME_ERROR"
        self.user_message = clean_message(message)
        self.detail = clean_message(detail)
        super().__init__(self.user_message)


def coded_error_info(exc: BaseException) -> RuntimeErrorInfo | None:
    if not isinstance(exc, CodedRuntimeError):
        return None
    return RuntimeErrorInfo(
        code=exc.code,
        message=redact_secrets(exc.user_message),
        detail=redact_secrets(exc.detail),
    )


def coded_user_message(exc: BaseException, *, fallback: object = "") -> str:
    info = coded_error_info(exc)
    if info is None:
        return redact_secrets(clean_message(fallback or exc))
    return f"{info.message} [{info.code}]"

