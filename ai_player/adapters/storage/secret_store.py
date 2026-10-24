from __future__ import annotations

import base64
import ctypes
import sys
from ctypes import wintypes


class SecretStoreError(RuntimeError):
    pass


SCHEME_WIN32_DPAPI = "win32-dpapi"


def protect_text(value: str) -> dict[str, str]:
    text = str(value or "")
    return {
        "scheme": SCHEME_WIN32_DPAPI,
        "value": base64.b64encode(_crypt_protect(text.encode("utf-8"))).decode("ascii"),
    }


def reveal_text(payload: object) -> str:
    if not isinstance(payload, dict):
        return ""
    if str(payload.get("scheme") or "") != SCHEME_WIN32_DPAPI:
        return ""
    encoded = str(payload.get("value") or "")
    if not encoded:
        return ""
    try:
        encrypted = base64.b64decode(encoded)
    except Exception as exc:
        raise SecretStoreError("Secret payload is not valid base64.") from exc
    return _crypt_unprotect(encrypted).decode("utf-8")


def _crypt_protect(data: bytes) -> bytes:
    if sys.platform != "win32":
        raise SecretStoreError("Windows DPAPI is not available on this platform.")
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    input_blob, _input_buffer = _blob_from_bytes(data)
    output_blob = _DATA_BLOB()
    if not crypt32.CryptProtectData(
        ctypes.byref(input_blob),
        None,
        None,
        None,
        None,
        0,
        ctypes.byref(output_blob),
    ):
        raise SecretStoreError(f"CryptProtectData failed: {ctypes.GetLastError()}")
    try:
        return ctypes.string_at(output_blob.pbData, output_blob.cbData)
    finally:
        kernel32.LocalFree(output_blob.pbData)


def _crypt_unprotect(data: bytes) -> bytes:
    if sys.platform != "win32":
        raise SecretStoreError("Windows DPAPI is not available on this platform.")
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    input_blob, _input_buffer = _blob_from_bytes(data)
    output_blob = _DATA_BLOB()
    if not crypt32.CryptUnprotectData(
        ctypes.byref(input_blob),
        None,
        None,
        None,
        None,
        0,
        ctypes.byref(output_blob),
    ):
        raise SecretStoreError(f"CryptUnprotectData failed: {ctypes.GetLastError()}")
    try:
        return ctypes.string_at(output_blob.pbData, output_blob.cbData)
    finally:
        kernel32.LocalFree(output_blob.pbData)


class _DATA_BLOB(ctypes.Structure):
    _fields_ = (
        ("cbData", wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_byte)),
    )


def _blob_from_bytes(data: bytes) -> tuple[_DATA_BLOB, ctypes.Array]:
    buffer = ctypes.create_string_buffer(data)
    return _DATA_BLOB(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte))), buffer
