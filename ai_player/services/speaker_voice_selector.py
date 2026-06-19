from __future__ import annotations

import importlib.util
import logging
import os
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests

from ai_player.core.config import LOCAL_SPEAKER_GENDER_MODEL_PATH, RUNTIME_DIR, AppConfig
from ai_player.core.value_utils import finite_float as _finite_float
from ai_player.services.audio_matcher import AudioProfile, profile_reference_audio
from ai_player.services.tts import select_voice_for_gender

VOICE_GENDER_MODES = {"stable", "balanced", "sensitive", "ai"}
DEFAULT_VOICE_GENDER_MODE = "balanced"
SPEAKER_GENDER_PROVIDERS = {"local", "huggingface_gender"}
DEFAULT_SPEAKER_GENDER_PROVIDER = "local"
DEFAULT_HUGGINGFACE_GENDER_MODEL = "audeering/wav2vec2-large-robust-6-ft-age-gender"
HUGGINGFACE_GENDER_API_BASE = "https://api-inference.huggingface.co/models"
_LOGGER = logging.getLogger(__name__)
_TRANSFORMERS_MODEL_LOCK = threading.Lock()
_TRANSFORMERS_MODEL_CACHE: dict[str, tuple[Any, Any]] = {}


@dataclass(frozen=True)
class VoiceGenderDecision:
    gender: str
    confidence: float
    voice: str
    profile: AudioProfile | None
    reason: str


def normalize_voice_gender_mode(mode: object) -> str:
    value = str(mode or "").strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "": DEFAULT_VOICE_GENDER_MODE,
        "default": DEFAULT_VOICE_GENDER_MODE,
        "normal": DEFAULT_VOICE_GENDER_MODE,
        "conservative": "stable",
        "safe": "stable",
        "nhay": "sensitive",
        "balanced": "balanced",
        "ai_filter": "ai",
        "model": "ai",
    }
    value = aliases.get(value, value)
    return value if value in VOICE_GENDER_MODES else DEFAULT_VOICE_GENDER_MODE


def normalize_speaker_gender_provider(provider: object) -> str:
    value = str(provider or "").strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "": DEFAULT_SPEAKER_GENDER_PROVIDER,
        "default": DEFAULT_SPEAKER_GENDER_PROVIDER,
        "offline": "local",
        "model": "local",
        "transformers": "local",
        "hf": "huggingface_gender",
        "huggingface": "huggingface_gender",
        "huggingface_inference": "huggingface_gender",
        "huggingface_gender": "huggingface_gender",
    }
    value = aliases.get(value, value)
    return value if value in SPEAKER_GENDER_PROVIDERS else DEFAULT_SPEAKER_GENDER_PROVIDER


def is_online_speaker_gender_provider(provider: object) -> bool:
    return normalize_speaker_gender_provider(provider) == "huggingface_gender"


def select_voice_for_reference(
    reference_path: Path,
    *,
    provider: str,
    config: AppConfig,
    selector: VoiceGenderSelector | None = None,
) -> VoiceGenderDecision:
    if selector is None:
        selector = VoiceGenderSelector(config)
    return selector.select_voice(reference_path, provider=provider, config=config)


class VoiceGenderSelector:
    def __init__(self, config: AppConfig) -> None:
        self._mode = normalize_voice_gender_mode(config.dubbing_auto_voice_gender_mode)
        self._last_gender = "unknown"
        self._last_voice = config.tts_voice
        self._last_confidence = 0.0
        self._pending_gender = "unknown"
        self._pending_count = 0

    def reset(self) -> None:
        self._last_gender = "unknown"
        self._last_confidence = 0.0
        self._pending_gender = "unknown"
        self._pending_count = 0

    def select_voice(self, reference_path: Path, *, provider: str, config: AppConfig) -> VoiceGenderDecision:
        profile = _profile_for_mode(reference_path, self._mode, config=config)
        gender, confidence, reason = self._smooth(profile)
        voice = config.tts_voice
        if gender in {"male", "female"}:
            voice = select_voice_for_gender(provider, config, gender)
        elif self._last_gender in {"male", "female"} and self._last_voice:
            voice = self._last_voice
            reason = f"{reason}; hold-last"

        if gender in {"male", "female"}:
            self._last_gender = gender
            self._last_voice = voice
            self._last_confidence = confidence
        decision = VoiceGenderDecision(
            gender=gender,
            confidence=confidence,
            voice=voice,
            profile=profile,
            reason=reason,
        )
        _log_voice_gender_decision(
            reference_path,
            provider=provider,
            mode=self._mode,
            decision=decision,
        )
        return decision

    def _smooth(self, profile: AudioProfile) -> tuple[str, float, str]:
        raw_gender = profile.gender
        confidence = float(profile.gender_confidence)
        if raw_gender not in {"male", "female"}:
            return ("unknown", confidence, f"{profile.detector}:unknown")

        threshold = _mode_confidence_threshold(self._mode)
        if confidence < threshold:
            return ("unknown", confidence, f"{profile.detector}:low-confidence")

        required_repeats = _mode_required_repeats(self._mode, confidence)
        if required_repeats <= 1 or raw_gender == self._last_gender:
            self._pending_gender = "unknown"
            self._pending_count = 0
            return (raw_gender, confidence, f"{profile.detector}:accepted")

        if raw_gender == self._pending_gender:
            self._pending_count += 1
        else:
            self._pending_gender = raw_gender
            self._pending_count = 1

        if self._pending_count >= required_repeats:
            self._pending_gender = "unknown"
            self._pending_count = 0
            return (raw_gender, confidence, f"{profile.detector}:confirmed")
        return ("unknown", confidence, f"{profile.detector}:waiting")


def _profile_for_mode(reference_path: Path, mode: str, *, config: AppConfig | None = None) -> AudioProfile:
    if normalize_voice_gender_mode(mode) == "ai":
        ai_profile = _ai_profile_reference_audio(reference_path, config=config)
        if ai_profile is not None:
            return ai_profile
    return profile_reference_audio(reference_path)


def _ai_profile_reference_audio(reference_path: Path, *, config: AppConfig | None = None) -> AudioProfile | None:
    if is_online_speaker_gender_provider(getattr(config, "speaker_gender_provider", "")):
        online_profile = _huggingface_profile_reference_audio(reference_path, config=config)
        if online_profile is not None:
            return online_profile

    model_source = _speaker_gender_ai_model_source(config)
    if not model_source:
        _LOGGER.debug("AI speaker-gender mode is enabled, but no local classifier is configured.")
        return None
    model_path = Path(model_source)
    if not model_path.exists() and not os.getenv("AI_PLAYER_ALLOW_REMOTE_AI_MODELS", "").strip():
        _LOGGER.warning("AI speaker-gender model path does not exist: %s", model_path)
        return None
    transformers_profile = _transformers_profile_reference_audio(reference_path, model_source)
    if transformers_profile is not None:
        return transformers_profile
    if importlib.util.find_spec("speechbrain") is None:
        _LOGGER.warning("AI speaker-gender model is configured, but speechbrain is not installed.")
        return None
    try:
        from speechbrain.inference.classifiers import EncoderClassifier

        savedir = RUNTIME_DIR / "speaker-gender-ai"
        classifier = EncoderClassifier.from_hparams(source=model_source, savedir=str(savedir))
        result = classifier.classify_file(str(reference_path))
        score = _speechbrain_score(result)
        label = _speechbrain_label(result)
        gender = _normalize_ai_gender(label)
        if gender not in {"male", "female"}:
            return None
        pitch_profile = profile_reference_audio(reference_path)
        return AudioProfile(
            gender=gender,
            median_pitch_hz=pitch_profile.median_pitch_hz,
            mean_volume_db=pitch_profile.mean_volume_db,
            duration_seconds=pitch_profile.duration_seconds,
            pitch_iqr_hz=pitch_profile.pitch_iqr_hz,
            voiced_ratio=pitch_profile.voiced_ratio,
            gender_confidence=max(0.0, min(0.98, score)),
            detector="ai",
        )
    except Exception:
        _LOGGER.exception("AI speaker-gender classifier failed; falling back to pitch detector.")
        return None


def _huggingface_profile_reference_audio(
    reference_path: Path,
    *,
    config: AppConfig | None = None,
) -> AudioProfile | None:
    api_key = str(getattr(config, "speaker_gender_api_key", "") or "").strip()
    if not api_key:
        _LOGGER.warning("Hugging Face speaker-gender provider is enabled, but no API key is configured.")
        return None
    model_source = _speaker_gender_online_model_source(config)
    api_base = str(getattr(config, "speaker_gender_api_base", "") or HUGGINGFACE_GENDER_API_BASE).strip().rstrip("/")
    url = _huggingface_gender_url(api_base, model_source)
    try:
        audio = Path(reference_path).read_bytes()
        response = requests.post(
            url,
            data=audio,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": _audio_content_type(reference_path),
            },
            timeout=_speaker_gender_timeout(config),
        )
        if response.status_code >= 400:
            _LOGGER.warning(
                "Hugging Face speaker-gender request failed with HTTP %s: %s",
                response.status_code,
                str(getattr(response, "text", "") or "")[:300],
            )
            return None
        gender, confidence = _huggingface_gender_from_response(response.json())
        if gender not in {"male", "female"}:
            return None
        pitch_profile = profile_reference_audio(reference_path)
        return AudioProfile(
            gender=gender,
            median_pitch_hz=pitch_profile.median_pitch_hz,
            mean_volume_db=pitch_profile.mean_volume_db,
            duration_seconds=pitch_profile.duration_seconds,
            pitch_iqr_hz=pitch_profile.pitch_iqr_hz,
            voiced_ratio=pitch_profile.voiced_ratio,
            gender_confidence=max(0.0, min(0.98, confidence)),
            detector="huggingface",
        )
    except Exception:
        _LOGGER.exception("Hugging Face speaker-gender classifier failed; falling back to local/pitch detector.")
        return None


def _speaker_gender_ai_model_source(config: AppConfig | None = None) -> str:
    configured_from_config = str(getattr(config, "speaker_gender_model", "") or "").strip()
    if configured_from_config:
        return configured_from_config
    configured = os.getenv("AI_PLAYER_SPEAKER_GENDER_AI_MODEL", "").strip()
    if configured:
        return configured
    if LOCAL_SPEAKER_GENDER_MODEL_PATH.exists():
        return str(LOCAL_SPEAKER_GENDER_MODEL_PATH)
    return ""


def _speaker_gender_online_model_source(config: AppConfig | None = None) -> str:
    configured = str(getattr(config, "speaker_gender_model", "") or "").strip()
    if configured and not _looks_like_local_model_path(configured):
        return configured
    return DEFAULT_HUGGINGFACE_GENDER_MODEL


def _looks_like_local_model_path(value: str) -> bool:
    path = Path(value)
    return path.exists() or "\\" in value or ":" in value or value.startswith((".", "/"))


def _huggingface_gender_url(api_base: str, model_source: str) -> str:
    if "{model}" in api_base:
        return api_base.replace("{model}", quote(model_source, safe=""))
    if api_base.rstrip("/").endswith(quote(model_source, safe="")):
        return api_base
    return f"{api_base.rstrip('/')}/{quote(model_source, safe='')}"


def _audio_content_type(path: Path) -> str:
    suffix = Path(path).suffix.lower()
    if suffix == ".mp3":
        return "audio/mpeg"
    if suffix == ".flac":
        return "audio/flac"
    if suffix in {".ogg", ".opus"}:
        return "audio/ogg"
    return "audio/wav"


def _speaker_gender_timeout(config: AppConfig | None) -> float:
    return max(1.0, _finite_float(getattr(config, "speaker_gender_timeout_seconds", 20.0), default=20.0))


def _huggingface_gender_from_response(data: object) -> tuple[str, float]:
    candidates = _flatten_huggingface_scores(data)
    scored: dict[str, float] = {}
    for item in candidates:
        if not isinstance(item, dict):
            continue
        label = str(item.get("label") or item.get("entity") or "").strip()
        gender = _normalize_ai_gender(label)
        if gender not in {"male", "female"}:
            continue
        try:
            score = float(item.get("score", 0.0))
        except (TypeError, ValueError, OverflowError):
            score = 0.0
        scored[gender] = max(scored.get(gender, 0.0), score)
    if not scored:
        return ("unknown", 0.0)
    gender, confidence = max(scored.items(), key=lambda item: item[1])
    return (gender, confidence)


def _flatten_huggingface_scores(data: object) -> list[object]:
    if isinstance(data, list):
        if data and all(isinstance(item, list) for item in data):
            return [entry for group in data for entry in group]
        return list(data)
    if isinstance(data, dict):
        for key in ("outputs", "predictions", "scores"):
            value = data.get(key)
            if isinstance(value, list):
                return _flatten_huggingface_scores(value)
    return []


def _transformers_profile_reference_audio(reference_path: Path, model_source: str) -> AudioProfile | None:
    if importlib.util.find_spec("transformers") is None:
        return None
    model_path = Path(model_source)
    if model_path.exists() and not (model_path / "config.json").is_file():
        return None
    try:
        import librosa
        import torch

        processor, model = _get_transformers_gender_classifier(model_source)
        samples, sample_rate = librosa.load(str(reference_path), sr=16_000, mono=True)
        inputs = processor(samples, sampling_rate=sample_rate, return_tensors="pt", padding=True)
        with torch.no_grad():
            logits = model(**inputs).logits
            probabilities = torch.nn.functional.softmax(logits, dim=-1).squeeze(0)
        score, index = torch.max(probabilities, dim=0)
        label = _transformers_label(model, int(index.item()))
        gender = _normalize_ai_gender(label)
        if gender not in {"male", "female"}:
            return None
        pitch_profile = profile_reference_audio(reference_path)
        return AudioProfile(
            gender=gender,
            median_pitch_hz=pitch_profile.median_pitch_hz,
            mean_volume_db=pitch_profile.mean_volume_db,
            duration_seconds=pitch_profile.duration_seconds,
            pitch_iqr_hz=pitch_profile.pitch_iqr_hz,
            voiced_ratio=pitch_profile.voiced_ratio,
            gender_confidence=max(0.0, min(0.98, float(score.item()))),
            detector="transformers",
        )
    except Exception:
        _LOGGER.exception("Transformers speaker-gender classifier failed; trying next AI backend.")
        return None


def _transformers_label(model: object, index: int) -> str:
    config = getattr(model, "config", None)
    id2label = getattr(config, "id2label", {}) if config is not None else {}
    for key in (index, str(index)):
        if key in id2label:
            return str(id2label[key])
    return str(index)


def _get_transformers_gender_classifier(model_source: str) -> tuple[Any, Any]:
    cached = _TRANSFORMERS_MODEL_CACHE.get(model_source)
    if cached is not None:
        return cached

    with _TRANSFORMERS_MODEL_LOCK:
        cached = _TRANSFORMERS_MODEL_CACHE.get(model_source)
        if cached is not None:
            return cached

        from transformers import AutoFeatureExtractor, AutoModelForAudioClassification

        model_path = Path(model_source)
        local_only = model_path.exists()
        processor = AutoFeatureExtractor.from_pretrained(model_source, local_files_only=local_only)
        model = AutoModelForAudioClassification.from_pretrained(model_source, local_files_only=local_only)
        model.eval()
        cached = (processor, model)
        _TRANSFORMERS_MODEL_CACHE[model_source] = cached
        return cached


def _log_voice_gender_decision(
    reference_path: Path,
    *,
    provider: str,
    mode: str,
    decision: VoiceGenderDecision,
) -> None:
    profile = decision.profile
    if profile is None:
        _LOGGER.info(
            "Auto voice decision: mode=%s provider=%s gender=%s confidence=%.3f voice=%s reason=%s reference=%s",
            mode,
            provider,
            decision.gender,
            decision.confidence,
            decision.voice,
            decision.reason,
            reference_path,
        )
        return

    _LOGGER.info(
        "Auto voice decision: mode=%s provider=%s detector=%s gender=%s confidence=%.3f "
        "voice=%s reason=%s pitch=%.1fHz duration=%.3fs voiced=%.2f iqr=%.1fHz reference=%s",
        mode,
        provider,
        profile.detector,
        decision.gender,
        decision.confidence,
        decision.voice,
        decision.reason,
        profile.median_pitch_hz,
        profile.duration_seconds,
        profile.voiced_ratio,
        profile.pitch_iqr_hz,
        reference_path,
    )


def _speechbrain_score(result: object) -> float:
    try:
        candidate = result[1] if isinstance(result, (tuple, list)) and len(result) > 1 else result
        if hasattr(candidate, "item"):
            return float(candidate.item())
        return float(candidate)
    except Exception:
        return 0.72


def _speechbrain_label(result: object) -> str:
    try:
        candidate = result[3] if isinstance(result, (tuple, list)) and len(result) > 3 else result
        if isinstance(candidate, (tuple, list)):
            candidate = candidate[0]
        return str(candidate or "")
    except Exception:
        return ""


def _normalize_ai_gender(label: object) -> str:
    value = str(label or "").strip().lower()
    if "female" in value or value in {"f", "woman", "nu", "nữ"}:
        return "female"
    if "male" in value or value in {"m", "man", "nam"}:
        return "male"
    return "unknown"


def _mode_confidence_threshold(mode: str) -> float:
    normalized = normalize_voice_gender_mode(mode)
    if normalized == "stable":
        return 0.76
    if normalized == "sensitive":
        return 0.48
    if normalized == "ai":
        return 0.58
    return 0.62


def _mode_required_repeats(mode: str, confidence: float) -> int:
    normalized = normalize_voice_gender_mode(mode)
    if normalized == "sensitive" or confidence >= 0.88:
        return 1
    if normalized == "stable":
        return 2
    return 1
