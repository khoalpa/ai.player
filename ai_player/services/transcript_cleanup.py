from __future__ import annotations

import importlib.util
import json
import logging
import math
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests

from ai_player.core.config import AppConfig
from ai_player.core.optional_imports import block_unneeded_transformers_optional_imports


class TranscriptCleanupError(RuntimeError):
    pass


class TranscriptCleanupBatchError(TranscriptCleanupError):
    pass


LOGGER = logging.getLogger(__name__)
_LOCAL_GGUF_CACHE: dict[str, Any] = {}
_LOCAL_TRANSFORMERS_CACHE: dict[str, tuple[Any, Any]] = {}
_MAX_CLEANUP_LENGTH_RATIO = 2.6
_MAX_CLEANUP_EXTRA_CHARS = 120


@dataclass(frozen=True)
class ProtectedTerm:
    canonical: str
    patterns: tuple[re.Pattern[str], ...]


@dataclass(frozen=True)
class CleanupContext:
    source_language: str | None = None
    previous_text: str = ""


_PROTECTED_TERMS = (
    ProtectedTerm(
        "NLLB",
        (
            re.compile(r"\bn\s*[-.]?\s*l\s*[-.]?\s*l\s*[-.]?\s*b\b", re.IGNORECASE),
            re.compile(r"\bnllb\b", re.IGNORECASE),
        ),
    ),
    ProtectedTerm(
        "OpenAI",
        (
            re.compile(r"\bopen\s*[-.]?\s*ai\b", re.IGNORECASE),
            re.compile(r"\bopenai\b", re.IGNORECASE),
        ),
    ),
    ProtectedTerm(
        "API",
        (
            re.compile(r"\ba\s*[-.]?\s*p\s*[-.]?\s*i\b", re.IGNORECASE),
            re.compile(r"\bapi\b", re.IGNORECASE),
        ),
    ),
)


class TranscriptCleaner:
    def __init__(self, config: AppConfig) -> None:
        self._config = config
        self._previous_text = ""
        self.last_error: str = ""
        self._warned_failure = False

    @property
    def enabled(self) -> bool:
        return _cleanup_mode(self._config.transcript_cleanup_mode) != "off"

    def clean(self, text: str, source_language: str | None = None) -> str:
        clean_text = " ".join(str(text or "").split())
        if not clean_text or not self.enabled:
            return clean_text
        clean_text = _normalize_protected_terms(clean_text)
        context = CleanupContext(source_language=source_language, previous_text=self._previous_text)
        try:
            result = _clean_with_provider(clean_text, context, self._config)
            self.last_error = ""
        except Exception as exc:
            self._record_failure(exc)
            result = clean_text
        result = _safe_cleanup_output(clean_text, result)
        self._previous_text = result
        return result

    def clean_many(self, texts: list[str], source_language: str | None = None) -> list[str]:
        clean_texts = [" ".join(str(text or "").split()) for text in texts]
        if not self.enabled:
            return clean_texts
        clean_texts = [_normalize_protected_terms(text) for text in clean_texts]
        indexed = [(index, text) for index, text in enumerate(clean_texts) if text]
        if not indexed:
            return clean_texts
        if len(indexed) == 1:
            index, text = indexed[0]
            clean_texts[index] = self.clean(text, source_language)
            return clean_texts

        context = CleanupContext(source_language=source_language, previous_text=self._previous_text)
        try:
            result = _clean_many_with_provider([text for _index, text in indexed], context, self._config)
            self.last_error = ""
        except TranscriptCleanupBatchError as exc:
            self._record_failure(exc)
            return self._clean_many_individually(clean_texts, indexed, source_language)
        except Exception as exc:
            self._record_failure(exc)
            return clean_texts
        if len(result) != len(indexed):
            self._record_failure(TranscriptCleanupBatchError("Cleanup batch returned an unexpected item count."))
            return self._clean_many_individually(clean_texts, indexed, source_language)
        for (index, original), cleaned in zip(indexed, result, strict=False):
            clean_texts[index] = _safe_cleanup_output(original, cleaned)
            self._previous_text = clean_texts[index]
        return clean_texts

    def _clean_many_individually(
        self,
        clean_texts: list[str],
        indexed: list[tuple[int, str]],
        source_language: str | None,
    ) -> list[str]:
        for index, text in indexed:
            clean_texts[index] = self.clean(text, source_language)
        return clean_texts

    def _record_failure(self, exc: Exception) -> None:
        self.last_error = str(exc)
        if self._warned_failure:
            return
        self._warned_failure = True
        LOGGER.warning("Transcript cleanup failed; using original transcript text. Error: %s", exc)


def _clean_with_provider(text: str, context: CleanupContext, config: AppConfig) -> str:
    provider = _cleanup_provider(config.transcript_cleanup_provider)
    prompt = _build_prompt(text, context, config)
    return _call_cleanup_provider(prompt, provider, config)


def _clean_many_with_provider(texts: list[str], context: CleanupContext, config: AppConfig) -> list[str]:
    provider = _cleanup_provider(config.transcript_cleanup_provider)
    prompt = _build_batch_prompt(texts, context, config)
    response = _call_cleanup_provider(prompt, provider, config)
    return _parse_cleanup_batch_output(response)


def _call_cleanup_provider(prompt: str, provider: str, config: AppConfig) -> str:
    if provider == "openai":
        return _call_openai_compatible(prompt, config)
    if provider == "local":
        return _call_headless_local(prompt, config)
    return _call_ollama(prompt, config)


def _build_prompt(text: str, context: CleanupContext, config: AppConfig) -> str:
    mode = _cleanup_mode(config.transcript_cleanup_mode)
    strength = (
        "Sửa rất nhẹ: chỉ sửa lỗi nhận diện giọng nói rõ ràng, dấu câu, chính tả, thuật ngữ."
        if mode == "light"
        else (
            "Sửa mạnh hơn nhưng không thêm ý mới: phục hồi câu bị vỡ nhẹ bằng ngữ cảnh, chuẩn hóa dấu câu và thuật ngữ."
        )
    )
    language = context.source_language or config.source_language or "auto"
    previous = context.previous_text.strip()
    previous_block = f"\nNgữ cảnh trước đó: {previous}" if previous else ""
    return (
        "Bạn là bộ sửa lỗi transcript ASR.\n"
        f"Ngôn ngữ nguồn: {language}\n"
        f"{strength}\n"
        "Quy tắc bắt buộc:\n"
        "- Chỉ trả về transcript đã sửa, không giải thích.\n"
        "- Không dịch sang ngôn ngữ khác.\n"
        "- Không thêm thông tin không có trong câu gốc.\n"
        "- Giữ nguyên tên riêng, lệnh terminal, URL, API, OpenAI, NLLB, model, số liệu nếu không chắc.\n"
        "- Nếu câu quá nhiễu hoặc không chắc, trả về gần giống câu gốc nhất.\n"
        f"{previous_block}\n"
        f"Transcript thô: {text}\n"
        "Transcript đã sửa:"
    )


def _build_batch_prompt(texts: list[str], context: CleanupContext, config: AppConfig) -> str:
    mode = _cleanup_mode(config.transcript_cleanup_mode)
    language = context.source_language or config.source_language or "auto"
    previous = context.previous_text.strip()
    previous_block = f"\nNgữ cảnh trước đó: {previous}" if previous else ""
    items = "\n".join(f"{index + 1}. {text}" for index, text in enumerate(texts))
    strength = (
        "Sửa rất nhẹ: chỉ sửa lỗi nhận diện giọng nói rõ ràng, dấu câu, chính tả, thuật ngữ."
        if mode == "light"
        else "Sửa mạnh hơn nhưng không thêm ý mới: phục hồi câu bị vỡ nhẹ, chuẩn hóa dấu câu và thuật ngữ."
    )
    return (
        "Bạn là bộ sửa lỗi transcript ASR.\n"
        f"Ngôn ngữ nguồn: {language}\n"
        f"{strength}\n"
        "Quy tắc bắt buộc:\n"
        "- Chỉ trả về JSON array các chuỗi đã sửa, đúng số lượng và đúng thứ tự.\n"
        "- Không giải thích, không markdown, không dịch sang ngôn ngữ khác.\n"
        "- Không thêm thông tin không có trong câu gốc.\n"
        "- Giữ nguyên tên riêng, lệnh terminal, URL, API, OpenAI, NLLB, model, số liệu nếu không chắc.\n"
        "- Nếu câu quá nhiễu hoặc không chắc, giữ gần giống câu gốc nhất.\n"
        f"{previous_block}\n"
        "Transcript thô:\n"
        f"{items}\n"
        "JSON array:"
    )


def _call_ollama(prompt: str, config: AppConfig) -> str:
    base = str(config.transcript_cleanup_api_base or "http://127.0.0.1:11434").rstrip("/")
    response = requests.post(
        f"{base}/api/generate",
        json={
            "model": config.transcript_cleanup_model or "llama3.1",
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.1},
        },
        timeout=_timeout_seconds(config.transcript_cleanup_timeout_seconds),
    )
    response.raise_for_status()
    data = _response_json_object(response, "Ollama")
    return str(data.get("response") or "")


def _call_openai_compatible(prompt: str, config: AppConfig) -> str:
    base = str(config.transcript_cleanup_api_base or "https://api.openai.com/v1").rstrip("/")
    headers = {"Content-Type": "application/json"}
    if config.transcript_cleanup_api_key:
        headers["Authorization"] = f"Bearer {config.transcript_cleanup_api_key}"
    response = requests.post(
        f"{base}/chat/completions",
        headers=headers,
        json={
            "model": config.transcript_cleanup_model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
        },
        timeout=_timeout_seconds(config.transcript_cleanup_timeout_seconds),
    )
    response.raise_for_status()
    data = _response_json_object(response, "OpenAI-compatible cleanup")
    return _chat_completion_content(data)


def _call_headless_local(prompt: str, config: AppConfig) -> str:
    model_value = str(config.transcript_cleanup_model or "").strip()
    if not model_value:
        raise TranscriptCleanupError("Chưa cấu hình Cleanup model cho Headless local.")
    model_path = Path(model_value)
    if model_path.is_file() and model_path.suffix.lower() == ".gguf":
        return _call_local_gguf(prompt, model_path, config)
    if model_path.is_dir():
        return _call_local_transformers(prompt, model_path, config)
    raise TranscriptCleanupError("Headless local cần Cleanup model là file .gguf hoặc thư mục model HuggingFace local.")


def _timeout_seconds(value: object) -> float:
    try:
        seconds = float(value)
    except (OverflowError, TypeError, ValueError):
        return 12.0
    if not math.isfinite(seconds):
        return 12.0
    return max(1.0, seconds)


def _response_json_object(response, provider_name: str) -> dict[str, Any]:
    try:
        data = response.json()
    except ValueError as exc:
        raise TranscriptCleanupError(f"{provider_name} trả về JSON không hợp lệ.") from exc
    if not isinstance(data, dict):
        raise TranscriptCleanupError(f"{provider_name} trả về dữ liệu không đúng định dạng.")
    return data


def _chat_completion_content(data: dict[str, Any]) -> str:
    try:
        choices = data["choices"]
        first_choice = choices[0] if isinstance(choices, list) else {}
        message = first_choice.get("message") if isinstance(first_choice, dict) else {}
        content = message.get("content") if isinstance(message, dict) else None
    except (IndexError, KeyError, TypeError) as exc:
        raise TranscriptCleanupError("OpenAI-compatible cleanup trả về dữ liệu không đúng định dạng.") from exc
    if content is None:
        raise TranscriptCleanupError("OpenAI-compatible cleanup trả về dữ liệu không đúng định dạng.")
    return str(content)


def _call_local_gguf(prompt: str, model_path: Path, config: AppConfig) -> str:
    key = str(model_path.resolve())
    model = _LOCAL_GGUF_CACHE.get(key)
    if model is None:
        try:
            from llama_cpp import Llama
        except ImportError as exc:
            raise TranscriptCleanupError("Thiếu llama-cpp-python cho Headless local GGUF.") from exc
        model = Llama(
            model_path=key,
            n_ctx=2048,
            n_threads=max(1, min(8, os.cpu_count() or 4)),
            verbose=False,
        )
        _LOCAL_GGUF_CACHE[key] = model
    output = model(
        prompt,
        max_tokens=160,
        temperature=0.1,
        stop=["\n\n", "Transcript thô:", "Transcript đã sửa:"],
    )
    return str(output["choices"][0]["text"])


def _call_local_transformers(prompt: str, model_path: Path, config: AppConfig) -> str:
    key = str(model_path.resolve())
    cached = _LOCAL_TRANSFORMERS_CACHE.get(key)
    if cached is None:
        try:
            with block_unneeded_transformers_optional_imports():
                import torch
                from transformers import AutoModelForCausalLM, AutoTokenizer
        except ImportError as exc:
            raise TranscriptCleanupError("Thiếu torch/transformers cho Headless local.") from exc
        with block_unneeded_transformers_optional_imports():
            tokenizer = AutoTokenizer.from_pretrained(key, local_files_only=True)
        kwargs = _local_transformers_load_kwargs(torch)
        with block_unneeded_transformers_optional_imports():
            model = _load_local_transformers_model(AutoModelForCausalLM, key, kwargs)
        model.eval()
        cached = (tokenizer, model)
        _LOCAL_TRANSFORMERS_CACHE[key] = cached
    tokenizer, model = cached
    import torch

    if hasattr(tokenizer, "apply_chat_template"):
        try:
            prompt = tokenizer.apply_chat_template(
                [{"role": "user", "content": prompt}],
                tokenize=False,
                add_generation_prompt=True,
            )
        except Exception:
            pass
    encoded = tokenizer(prompt, return_tensors="pt", truncation=True, max_length=1800)
    device = _local_transformers_input_device(model, torch)
    encoded = {name: value.to(device) for name, value in encoded.items()}
    with torch.no_grad():
        output = model.generate(
            **encoded,
            max_new_tokens=160,
            do_sample=False,
            pad_token_id=tokenizer.eos_token_id,
        )
    generated = output[0][encoded["input_ids"].shape[-1] :]
    return tokenizer.decode(generated, skip_special_tokens=True)


def _local_transformers_load_kwargs(torch_module: Any) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "local_files_only": True,
        "dtype": torch_module.float16 if torch_module.cuda.is_available() else torch_module.float32,
    }
    if torch_module.cuda.is_available() and importlib.util.find_spec("accelerate") is not None:
        kwargs["device_map"] = "auto"
    return kwargs


def _load_local_transformers_model(model_cls: Any, model_path: str, kwargs: dict[str, Any]) -> Any:
    try:
        return model_cls.from_pretrained(model_path, **kwargs)
    except TypeError as exc:
        if "dtype" not in kwargs or "dtype" not in str(exc):
            raise
        legacy_kwargs = dict(kwargs)
        legacy_kwargs["torch_dtype"] = legacy_kwargs.pop("dtype")
        return model_cls.from_pretrained(model_path, **legacy_kwargs)


def _local_transformers_input_device(model: Any, torch_module: Any) -> Any:
    hf_device_map = getattr(model, "hf_device_map", None)
    if isinstance(hf_device_map, dict):
        for device in hf_device_map.values():
            device_text = str(device)
            if device_text and device_text != "disk":
                return device_text
    try:
        device = model.device
        if str(device) != "meta":
            return device
    except Exception:
        pass
    try:
        for parameter in model.parameters():
            device = getattr(parameter, "device", None)
            if device is not None and str(device) != "meta":
                return device
    except Exception:
        pass
    return "cuda" if torch_module.cuda.is_available() and importlib.util.find_spec("accelerate") is not None else "cpu"


def _sanitize_llm_output(text: str) -> str:
    value = str(text or "").strip()
    value = re.sub(r"^```(?:json|text)?\s*", "", value, flags=re.IGNORECASE)
    value = re.sub(r"\s*```$", "", value)
    value = re.sub(r"^Transcript đã sửa:\s*", "", value, flags=re.IGNORECASE)
    value = re.sub(r"^Transcript da sua:\s*", "", value, flags=re.IGNORECASE)
    value = re.sub(r"^Corrected transcript:\s*", "", value, flags=re.IGNORECASE)
    value = re.sub(r"^(?:Giải thích|Giai thich|Explanation)\s*:\s*.*?(?:\n|$)", "", value, flags=re.IGNORECASE)
    lines = [line.strip() for line in value.splitlines() if line.strip()]
    if len(lines) > 1:
        label_pattern = re.compile(r"^(?:transcript|corrected|kết quả|ket qua)\s*[:：]\s*(.+)$", re.IGNORECASE)
        for line in lines:
            match = label_pattern.match(line)
            if match:
                value = match.group(1)
                break
        else:
            value = lines[0]
    value = value.strip().strip('"').strip()
    return " ".join(value.split())


def _safe_cleanup_output(original: str, candidate: str) -> str:
    original = _normalize_protected_terms(original)
    cleaned = _normalize_protected_terms(_sanitize_llm_output(candidate))
    if not cleaned:
        return original
    if _looks_unsafe_cleanup(original, cleaned):
        return original
    return cleaned


def _looks_unsafe_cleanup(original: str, cleaned: str) -> bool:
    original_text = " ".join(str(original or "").split())
    cleaned_text = " ".join(str(cleaned or "").split())
    if not original_text or not cleaned_text:
        return False
    max_length = max(len(original_text) + _MAX_CLEANUP_EXTRA_CHARS, int(len(original_text) * _MAX_CLEANUP_LENGTH_RATIO))
    if len(cleaned_text) > max_length:
        return True
    if not _preserves_protected_terms(original_text, cleaned_text):
        return True
    lower = cleaned_text.casefold()
    unsafe_prefixes = (
        "giải thích:",
        "giai thich:",
        "explanation:",
        "i corrected",
        "here is",
        "dưới đây",
    )
    return lower.startswith(unsafe_prefixes)


def _normalize_protected_terms(text: str) -> str:
    value = str(text or "")
    if not value:
        return value
    for term in _PROTECTED_TERMS:
        for pattern in term.patterns:
            value = pattern.sub(term.canonical, value)
    return " ".join(value.split())


def _protected_terms_in(text: str) -> set[str]:
    value = str(text or "")
    return {term.canonical for term in _PROTECTED_TERMS if any(pattern.search(value) for pattern in term.patterns)}


def _preserves_protected_terms(original: str, cleaned: str) -> bool:
    required = _protected_terms_in(original)
    if not required:
        return True
    present = _protected_terms_in(cleaned)
    return required.issubset(present)


def _parse_cleanup_batch_output(text: str) -> list[str]:
    value = str(text or "").strip()
    value = re.sub(r"^```(?:json)?\s*", "", value, flags=re.IGNORECASE)
    value = re.sub(r"\s*```$", "", value)
    try:
        data = json.loads(value)
    except json.JSONDecodeError as exc:
        raise TranscriptCleanupBatchError("Cleanup batch did not return valid JSON.") from exc
    if not isinstance(data, list) or not all(isinstance(item, str) for item in data):
        raise TranscriptCleanupBatchError("Cleanup batch JSON must be an array of strings.")
    return [_sanitize_llm_output(item) for item in data]


def _cleanup_mode(value: object) -> str:
    raw = str(value or "off").strip().lower().replace("-", "_").replace(" ", "_")
    if raw in {"light", "nhe", "nhẹ"}:
        return "light"
    if raw in {"strong", "manh", "mạnh"}:
        return "strong"
    return "off"


def _cleanup_provider(value: object) -> str:
    raw = str(value or "ollama").strip().lower().replace("-", "_").replace(" ", "_")
    if raw in {"openai", "openai_compatible", "api"}:
        return "openai"
    if raw in {"local", "headless", "headless_local", "local_headless", "transformers", "llamacpp", "llama_cpp"}:
        return "local"
    return "ollama"
