from __future__ import annotations

import os
import re
import sys
import threading
from dataclasses import dataclass
from pathlib import Path

from ai_player.core.config import (
    LOCAL_TRANSLATION_MODEL_13B_PATH,
    LOCAL_TRANSLATION_MODEL_PATH,
    TRANSLATION_MODELS_PATH,
    AppConfig,
)
from ai_player.core.gpu import configure_cuda_dll_paths, ctranslate2_cuda_available
from ai_player.core.offline_env import pop_hf_offline_environment, push_hf_offline_environment
from ai_player.core.optional_imports import block_unneeded_transformers_optional_imports


class TranslationError(RuntimeError):
    pass


WHISPER_TO_NLLB = {
    "ar": "arb_Arab",
    "de": "deu_Latn",
    "en": "eng_Latn",
    "es": "spa_Latn",
    "fr": "fra_Latn",
    "hi": "hin_Deva",
    "id": "ind_Latn",
    "it": "ita_Latn",
    "ja": "jpn_Jpan",
    "ko": "kor_Hang",
    "pt": "por_Latn",
    "ru": "rus_Cyrl",
    "th": "tha_Thai",
    "tr": "tur_Latn",
    "vi": "vie_Latn",
    "zh": "zho_Hans",
}

NLLB_CT2_MODEL_PATH = TRANSLATION_MODELS_PATH / "nllb-200-distilled-600M-ct2-int8"


@dataclass(frozen=True)
class TranslatorOption:
    id: str
    name: str


@dataclass(frozen=True)
class NllbModelOption:
    id: str
    name: str
    path: str


def available_translators() -> list[TranslatorOption]:
    return [
        TranslatorOption("nllb_ct2", "NLLB CTranslate2"),
        TranslatorOption("nllb", "NLLB Local"),
        TranslatorOption("none", "Không dịch"),
    ]


def available_nllb_models() -> list[NllbModelOption]:
    models = [
        NllbModelOption(
            "nllb-200-distilled-600M",
            "nllb-200-distilled-600M (tốc độ)",
            LOCAL_TRANSLATION_MODEL_PATH,
        ),
        NllbModelOption(
            "nllb-200-distilled-600M-ct2-int8",
            "nllb-200-distilled-600M-ct2-int8 (cân bằng)",
            str(NLLB_CT2_MODEL_PATH),
        ),
        NllbModelOption(
            "nllb-200-1.3B",
            "nllb-200-1.3B (chất lượng)",
            LOCAL_TRANSLATION_MODEL_13B_PATH,
        ),
    ]
    for path in sorted(TRANSLATION_MODELS_PATH.glob("nllb-*"), key=lambda item: item.name.lower()):
        if not path.is_dir():
            continue
        resolved = str(path.resolve())
        if any(Path(model.path).resolve() == path.resolve() for model in models):
            continue
        models.append(NllbModelOption(path.name, f"{path.name} (local)", resolved))
    return models


def available_translation_models(provider: object) -> list[NllbModelOption]:
    normalized = normalize_translator_provider(provider)
    if normalized == "nllb_ct2":
        models = [
            NllbModelOption(
                "nllb-200-distilled-600M-ct2-int8",
                "nllb-200-distilled-600M-ct2-int8 (CTranslate2 int8)",
                str(NLLB_CT2_MODEL_PATH),
            )
        ]
        for path in sorted(TRANSLATION_MODELS_PATH.glob("*ct2*"), key=lambda item: item.name.lower()):
            if path.is_dir() and path.resolve() != NLLB_CT2_MODEL_PATH.resolve():
                models.append(NllbModelOption(path.name, f"{path.name} (CTranslate2 local)", str(path.resolve())))
        return models
    if normalized == "nllb":
        return [
            model for model in available_nllb_models() if Path(model.path).resolve() != NLLB_CT2_MODEL_PATH.resolve()
        ]
    if normalized == "none":
        return [NllbModelOption("none", "Không dùng model", "")]
    return available_translation_models("nllb_ct2")


def is_ctranslate2_model_path(value: object) -> bool:
    path = Path(str(value or "").strip())
    if not str(path):
        return False
    if path.resolve() == NLLB_CT2_MODEL_PATH.resolve():
        return True
    return _looks_like_ctranslate2_model(path) or _has_ctranslate2_name_hint(path)


def normalize_translator_provider(value: object) -> str:
    raw = str(value or "nllb_ct2").strip().lower().replace("-", "_").replace(" ", "_")
    if raw in {"none", "off", "passthrough", "no_translate", "khong_dich"}:
        return "none"
    if raw in {"nllb_ct2", "ctranslate2", "ct2", "nllb_ctranslate2"}:
        return "nllb_ct2"
    if raw in {"nllb", "local_nllb", "nllb_local"}:
        return "nllb"
    return "nllb_ct2"


def effective_translator_provider(config: AppConfig) -> str:
    provider = normalize_translator_provider(config.translator_provider)
    if provider == "nllb" and is_ctranslate2_model_path(config.local_translation_model):
        return "nllb_ct2"
    return provider


class PassthroughTranslator:
    def translate(self, text: str, source_language: str | None = None) -> str:
        return " ".join(str(text or "").split())

    def translate_many(self, texts: list[str], source_language: str | None = None) -> list[str]:
        return [self.translate(text, source_language) for text in texts]


class LocalNllbTranslator:
    def __init__(self, config: AppConfig) -> None:
        self._config = config
        self._tokenizer = None
        self._model = None

    def translate(self, text: str, source_language: str | None = None) -> str:
        return self.translate_many([text], source_language)[0]

    def translate_many(self, texts: list[str], source_language: str | None = None) -> list[str]:
        clean_texts = [" ".join(str(text or "").split()) for text in texts]
        if not clean_texts:
            return []
        src_lang = self._source_language(source_language)
        target_lang = self._target_language()
        if src_lang == target_lang:
            return clean_texts

        active_items = [(index, clean) for index, clean in enumerate(clean_texts) if clean]
        if not active_items:
            return clean_texts

        protected_items = [(index, _protect_english_terms(clean, self._config)) for index, clean in active_items]
        self._load_model()
        self._tokenizer.src_lang = src_lang
        encoded = self._tokenizer(
            [protected.text for _index, protected in protected_items],
            return_tensors="pt",
            padding=True,
            truncation=True,
        )
        encoded = {key: value.to(self._model.device) for key, value in encoded.items()}
        output = self._model.generate(
            **encoded,
            forced_bos_token_id=self._tokenizer.convert_tokens_to_ids(target_lang),
            max_new_tokens=self._config.translation_max_tokens,
            num_beams=self._config.translation_num_beams,
        )
        translated_batch = self._tokenizer.batch_decode(output, skip_special_tokens=True)
        results = list(clean_texts)
        for (index, protected), translated in zip(protected_items, translated_batch, strict=False):
            results[index] = _restore_english_terms(translated.strip(), protected)
        return results

    def _load_model(self) -> None:
        if self._model is not None and self._tokenizer is not None:
            return

        if self._config.local_translation_offline:
            model_path = Path(self._config.local_translation_model)
            if not model_path.exists():
                raise TranslationError(
                    "Thiếu model dịch NLLB offline. Chạy scripts\\download_translator_models.ps1 "
                    "để tải models\\translation\\nllb-200-distilled-600M."
                )

        optional_modules = _disable_unneeded_transformers_optional_imports()
        try:
            try:
                import torch
                from transformers import AutoModelForSeq2SeqLM, AutoTokenizer
                from transformers.utils import logging as transformers_logging

                transformers_logging.set_verbosity_error()
            except ImportError as exc:
                raise TranslationError(
                    "Thiếu thư viện dịch local. Hãy chạy: "
                    ".\\.venv\\Scripts\\python.exe -m pip install -r requirements.txt"
                ) from exc
        finally:
            _restore_optional_imports(optional_modules)

        offline_env = push_hf_offline_environment(self._config.local_translation_offline)
        try:
            with block_unneeded_transformers_optional_imports():
                self._tokenizer = AutoTokenizer.from_pretrained(
                    self._config.local_translation_model,
                    local_files_only=self._config.local_translation_offline,
                )
                self._model = AutoModelForSeq2SeqLM.from_pretrained(
                    self._config.local_translation_model,
                    local_files_only=self._config.local_translation_offline,
                )
        except Exception as exc:
            raise TranslationError(
                "Không tải được model dịch local. Chạy "
                "scripts\\download_translator_models.ps1 một lần, hoặc đặt "
                "AI_PLAYER_TRANSLATION_MODEL tới thư mục model NLLB đã tải."
            ) from exc
        finally:
            pop_hf_offline_environment(offline_env)

        device = self._config.local_translation_device
        if device == "auto":
            device = "cuda" if torch.cuda.is_available() else "cpu"
        try:
            self._model.to(device)
        except Exception:
            if device == "cpu":
                raise
            device = "cpu"
            self._model.to(device)
        self._model.eval()

    @staticmethod
    def _source_language(source_language: str | None) -> str:
        if not source_language:
            return "eng_Latn"
        normalized = source_language.lower().split("-")[0]
        return WHISPER_TO_NLLB.get(normalized, "eng_Latn")

    def _target_language(self) -> str:
        normalized = str(getattr(self._config, "target_language", "vi") or "vi").lower().split("-")[0]
        return WHISPER_TO_NLLB.get(normalized, "vie_Latn")


class CTranslate2NllbTranslator(LocalNllbTranslator):
    def __init__(self, config: AppConfig) -> None:
        super().__init__(config)
        self._translator = None

    def translate(self, text: str, source_language: str | None = None) -> str:
        return self.translate_many([text], source_language)[0]

    def translate_many(self, texts: list[str], source_language: str | None = None) -> list[str]:
        clean_texts = [" ".join(str(text or "").split()) for text in texts]
        if not clean_texts:
            return []

        src_lang = self._source_language(source_language)
        target_lang = self._target_language()
        if src_lang == target_lang:
            return clean_texts

        active_items = [(index, clean) for index, clean in enumerate(clean_texts) if clean]
        if not active_items:
            return clean_texts

        protected_items = [(index, _protect_english_terms(clean, self._config)) for index, clean in active_items]
        self._load_model()
        self._tokenizer.src_lang = src_lang
        source_tokens_batch = []
        target_prefixes = []
        for _index, protected in protected_items:
            source_ids = self._tokenizer(protected.text, return_tensors="pt", truncation=True).input_ids[0]
            source_tokens_batch.append(self._tokenizer.convert_ids_to_tokens(source_ids))
            target_prefixes.append([target_lang])
        translate_kwargs = {
            "target_prefix": target_prefixes,
            "beam_size": max(1, int(self._config.translation_num_beams)),
            "max_decoding_length": max(32, int(self._config.translation_max_tokens)),
            "batch_type": "tokens",
            "max_batch_size": _translation_batch_size(self._config),
        }
        try:
            results = self._translator.translate_batch(source_tokens_batch, **translate_kwargs)
        except TypeError:
            translate_kwargs.pop("batch_type", None)
            translate_kwargs.pop("max_batch_size", None)
            results = self._translator.translate_batch(source_tokens_batch, **translate_kwargs)
        translated_texts = list(clean_texts)
        for (index, protected), result in zip(protected_items, results, strict=False):
            output_tokens = list(result.hypotheses[0])
            if output_tokens and output_tokens[0] == target_lang:
                output_tokens = output_tokens[1:]
            translated = self._tokenizer.decode(
                self._tokenizer.convert_tokens_to_ids(output_tokens),
                skip_special_tokens=True,
            ).strip()
            translated_texts[index] = _restore_english_terms(translated, protected)
        return translated_texts

    def _load_model(self) -> None:
        if self._translator is not None and self._tokenizer is not None:
            return
        model_path = _resolve_ctranslate2_model_path(self._config.local_translation_model)
        if not model_path.exists():
            raise TranslationError(
                "Thiếu model NLLB CTranslate2 offline. Chạy scripts\\download_translator_models.ps1 "
                f"hoặc chọn đúng thư mục model CT2.\nModel: {model_path}"
            )
        configure_cuda_dll_paths()
        try:
            import ctranslate2

            with block_unneeded_transformers_optional_imports():
                from transformers import AutoTokenizer
        except ImportError as exc:
            raise TranslationError(
                "Thiếu runtime CTranslate2. Hãy chạy: .\\.venv\\Scripts\\python.exe -m pip install ctranslate2"
            ) from exc

        tokenizer_path = _resolve_ctranslate2_tokenizer_path(model_path)
        with block_unneeded_transformers_optional_imports():
            self._tokenizer = AutoTokenizer.from_pretrained(
                str(tokenizer_path),
                local_files_only=True,
            )
        device = self._config.local_translation_device
        if device == "auto":
            device = "cuda" if ctranslate2_cuda_available() else "cpu"
        try:
            self._translator = _create_ctranslate2_translator(ctranslate2, model_path, device)
        except Exception:
            if device == "cpu":
                raise
            self._translator = _create_ctranslate2_translator(ctranslate2, model_path, "cpu")


class VietnameseTranslator:
    def __init__(self, config: AppConfig) -> None:
        provider = effective_translator_provider(config)
        if provider == "none":
            self._translator = PassthroughTranslator()
        elif provider == "nllb_ct2":
            self._translator = CTranslate2NllbTranslator(config)
        else:
            self._translator = LocalNllbTranslator(config)
        self._cache: dict[tuple[str, str | None], str] = {}
        self._cache_lock = threading.Lock()

    def translate(self, text: str, source_language: str | None = None) -> str:
        return self.translate_many([text], source_language)[0]

    def translate_many(self, texts: list[str], source_language: str | None = None) -> list[str]:
        if not texts:
            return []

        results: list[str | None] = [None] * len(texts)
        missing_indexes: list[int] = []
        missing_texts: list[str] = []
        with self._cache_lock:
            for index, text in enumerate(texts):
                key = (" ".join(str(text or "").split()), source_language)
                cached = self._cache.get(key)
                if cached is None:
                    missing_indexes.append(index)
                    missing_texts.append(text)
                else:
                    results[index] = cached

        if missing_texts:
            if hasattr(self._translator, "translate_many"):
                translated_missing = self._translator.translate_many(missing_texts, source_language)
            else:
                translated_missing = [self._translator.translate(text, source_language) for text in missing_texts]
            with self._cache_lock:
                for index, original, translated in zip(
                    missing_indexes, missing_texts, translated_missing, strict=False
                ):
                    key = (" ".join(str(original or "").split()), source_language)
                    self._cache[key] = translated
                    results[index] = translated

        return [result or "" for result in results]


def configured_translation_backend(config: AppConfig) -> str:
    provider = effective_translator_provider(config)
    if provider == "none":
        return "Không dịch"
    if provider == "nllb_ct2":
        return f"NLLB CTranslate2 ({_resolve_ctranslate2_model_path(config.local_translation_model)})"
    mode = "offline" if config.local_translation_offline else "download-if-needed"
    return f"Local NLLB ({config.local_translation_model}, {mode})"


@dataclass(frozen=True)
class ProtectedTerms:
    text: str
    replacements: tuple[tuple[str, str], ...]


def _protect_english_terms(text: str, config: AppConfig) -> ProtectedTerms:
    if not config.preserve_english_terms:
        return ProtectedTerms(text=text, replacements=())

    terms = _preserved_terms(config.preserved_english_terms)
    if not terms:
        return ProtectedTerms(text=text, replacements=())

    replacements: list[tuple[str, str]] = []
    protected_text = text
    for term in terms:
        pattern = _term_pattern(term)
        if not pattern.search(protected_text):
            continue

        def replace_match(match: re.Match[str]) -> str:
            original = match.group(0)
            placeholder = f"zxqterm{len(replacements)}zxq"
            replacements.append((placeholder, original))
            return placeholder

        protected_text = pattern.sub(replace_match, protected_text)
    return ProtectedTerms(text=protected_text, replacements=tuple(replacements))


def _restore_english_terms(text: str, protected: ProtectedTerms) -> str:
    restored = text
    for placeholder, original in protected.replacements:
        match = re.fullmatch(r"zxqterm(\d+)zxq", placeholder, flags=re.IGNORECASE)
        if match:
            tolerant = rf"z\s*x\s*q\s*term\s*{match.group(1)}\s*z\s*x\s*q"
            restored = re.sub(tolerant, original, restored, flags=re.IGNORECASE)
        variants = {
            placeholder,
            placeholder.lower(),
            placeholder.replace("_", " "),
            placeholder.replace("_", "-"),
            placeholder.lower().replace("_", " "),
            placeholder.lower().replace("_", "-"),
        }
        for variant in variants:
            restored = re.sub(re.escape(variant), original, restored, flags=re.IGNORECASE)
    return " ".join(restored.split())


def _has_broken_placeholders(text: str) -> bool:
    return bool(re.search(r"\b[sz]xq\w*|\w*zxq\b|aiterm|term\d+keep", text, re.IGNORECASE))


def _preserved_terms(value: str) -> list[str]:
    terms = [item.strip() for item in re.split(r"[,;\n]+", str(value or "")) if item.strip()]
    return sorted(dict.fromkeys(terms), key=len, reverse=True)


def _term_pattern(term: str) -> re.Pattern[str]:
    escaped = re.escape(term)
    if re.search(r"^[A-Za-z0-9][A-Za-z0-9 ._+-]*[A-Za-z0-9]$", term):
        return re.compile(rf"(?<![A-Za-z0-9]){escaped}(?![A-Za-z0-9])", re.IGNORECASE)
    return re.compile(escaped, re.IGNORECASE)


def _resolve_ctranslate2_model_path(value: object) -> Path:
    selected = Path(str(value or "").strip())
    if _looks_like_ctranslate2_model(selected) or _has_ctranslate2_name_hint(selected):
        return selected
    return NLLB_CT2_MODEL_PATH


def _resolve_ctranslate2_tokenizer_path(model_path: Path) -> Path:
    if (model_path / "tokenizer.json").exists() or (model_path / "tokenizer_config.json").exists():
        return model_path
    if model_path.resolve() == NLLB_CT2_MODEL_PATH.resolve():
        return Path(LOCAL_TRANSLATION_MODEL_PATH)

    candidates = _ctranslate2_tokenizer_candidates(model_path)
    for candidate in candidates:
        if (candidate / "tokenizer.json").exists() or (candidate / "tokenizer_config.json").exists():
            return candidate
    return Path(LOCAL_TRANSLATION_MODEL_PATH)


def _ctranslate2_tokenizer_candidates(model_path: Path) -> list[Path]:
    name = model_path.name
    suffixes = (
        "-ct2-int8",
        "-ct2-float16",
        "-ct2-float32",
        "-ct2",
        "_ct2_int8",
        "_ct2_float16",
        "_ct2_float32",
        "_ct2",
    )
    candidates: list[Path] = []
    for suffix in suffixes:
        if name.endswith(suffix):
            candidates.append(model_path.with_name(name[: -len(suffix)]))
    candidates.append(model_path.parent / "nllb-200-distilled-600M")
    return candidates


def _looks_like_ctranslate2_model(path: Path) -> bool:
    return (
        path.is_dir()
        and (path / "model.bin").exists()
        and (
            (path / "shared_vocabulary.json").exists()
            or (path / "source_vocabulary.json").exists()
            or (path / "target_vocabulary.json").exists()
        )
    )


def _has_ctranslate2_name_hint(path: Path) -> bool:
    name = path.name.lower()
    return bool(name) and ("ct2" in name or "ctranslate2" in name)


def _create_ctranslate2_translator(ctranslate2, model_path: Path, device: str):
    cpu_count = os.cpu_count() or 2
    inter_threads = _env_int("AI_PLAYER_CT2_INTER_THREADS", 2 if device == "cuda" else min(4, cpu_count))
    intra_threads = _env_int("AI_PLAYER_CT2_INTRA_THREADS", max(1, cpu_count // max(1, inter_threads)))
    kwargs = {
        "device": device,
        "inter_threads": max(1, inter_threads),
        "intra_threads": max(1, intra_threads),
    }
    try:
        return ctranslate2.Translator(str(model_path), **kwargs)
    except TypeError:
        return ctranslate2.Translator(str(model_path), device=device)


def _translation_batch_size(config: AppConfig) -> int:
    default = 8 if str(config.local_translation_device).strip().lower() == "cuda" else 4
    return max(1, min(64, _env_int("AI_PLAYER_TRANSLATION_BATCH_SIZE", default)))


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _disable_unneeded_transformers_optional_imports() -> dict[str, object]:
    previous = {}
    for module_name in ("sklearn", "pandas", "pyarrow"):
        previous[module_name] = sys.modules.get(module_name, ...)
        sys.modules[module_name] = None
    return previous


def _restore_optional_imports(previous: dict[str, object]) -> None:
    for module_name, module in previous.items():
        if module is ...:
            sys.modules.pop(module_name, None)
        else:
            sys.modules[module_name] = module
