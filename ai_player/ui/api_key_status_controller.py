from __future__ import annotations

from typing import Any

from ai_player.services.asr import is_online_asr_provider
from ai_player.services.speaker_voice_selector import is_online_speaker_gender_provider
from ai_player.services.subtitle_ocr import is_online_ocr_provider, normalize_ocr_provider
from ai_player.services.translation import is_online_translation_provider
from ai_player.services.tts_base import is_online_tts_provider, normalize_tts_provider


class ApiKeyStatusController:
    REQUIRED_STATUS_WIDGETS = (
        "_asr_api_key_status",
        "_ocr_api_key_status",
        "_translator_api_key_status",
        "_transcript_cleanup_api_key_status",
        "_tts_api_key_status",
        "_tts_api_secret_status",
        "_speaker_gender_api_key_status",
    )

    def __init__(self, owner: Any) -> None:
        self._owner = owner

    def sync(self) -> None:
        owner = self._owner
        if not all(hasattr(owner, widget_name) for widget_name in self.REQUIRED_STATUS_WIDGETS):
            return

        self.set_api_key_status(
            owner._asr_api_key_status,
            required=is_online_asr_provider(owner._selected_asr_provider()),
            has_value=bool(owner._asr_api_key_edit.text().strip()),
        )

        ocr_provider = normalize_ocr_provider(owner._selected_ocr_provider())
        ocr_online = is_online_ocr_provider(ocr_provider)
        ocr_has_key = bool(owner._ocr_api_key_edit.text().strip())
        self.set_api_key_status(
            owner._ocr_api_key_status,
            required=ocr_online and (ocr_provider != "ocr_space" or ocr_has_key),
            has_value=ocr_has_key,
            demo=ocr_online and ocr_provider == "ocr_space" and not ocr_has_key,
        )

        self.set_api_key_status(
            owner._translator_api_key_status,
            required=is_online_translation_provider(owner._translator_combo.currentData()),
            has_value=bool(owner._translator_api_key_edit.text().strip()),
        )

        cleanup_provider = owner._selected_transcript_cleanup_provider()
        cleanup_enabled = owner._selected_transcript_cleanup_mode() != "off"
        cleanup_key_required = cleanup_enabled and cleanup_provider in owner._PRIMARY_TRANSCRIPT_CLEANUP_KEY_PROVIDERS
        self.set_api_key_status(
            owner._transcript_cleanup_api_key_status,
            required=cleanup_key_required,
            has_value=bool(owner._transcript_cleanup_api_key_edit.text().strip()),
        )

        tts_provider = normalize_tts_provider(owner._selected_tts_provider())
        self.set_api_key_status(
            owner._tts_api_key_status,
            required=is_online_tts_provider(tts_provider),
            has_value=bool(owner._tts_api_key_edit.text().strip()),
        )
        self.set_api_key_status(
            owner._tts_api_secret_status,
            required=tts_provider == "amazon_polly",
            has_value=bool(owner._tts_api_secret_edit.text().strip()),
            secret=True,
        )

        speaker_gender_required = (
            owner._auto_voice_gender_check.isChecked()
            and owner._selected_auto_voice_gender_mode() == "ai"
            and is_online_speaker_gender_provider(owner._selected_speaker_gender_provider())
        )
        self.set_api_key_status(
            owner._speaker_gender_api_key_status,
            required=speaker_gender_required,
            has_value=bool(owner._speaker_gender_api_key_edit.text().strip()),
        )
        self.refresh_model_status_strip()

    def refresh_model_status_strip(self) -> None:
        owner = self._owner
        labels = getattr(owner, "_model_status_labels", None)
        if not labels:
            return
        asr_provider = owner._selected_asr_provider()
        self.set_model_status_pill(
            "model_status_asr",
            owner._tr("model_status_asr"),
            self.provider_status_text(
                provider=asr_provider,
                required=is_online_asr_provider(asr_provider),
                has_value=bool(owner._asr_api_key_edit.text().strip()),
            ),
        )
        translator = owner._translator_combo.currentData()
        self.set_model_status_pill(
            "model_status_translation",
            owner._tr("model_status_translation"),
            self.provider_status_text(
                provider=translator,
                required=is_online_translation_provider(translator),
                has_value=bool(owner._translator_api_key_edit.text().strip()),
            ),
        )
        tts_provider = normalize_tts_provider(owner._selected_tts_provider())
        self.set_model_status_pill(
            "model_status_tts",
            owner._tr("model_status_tts"),
            self.provider_status_text(
                provider=tts_provider,
                required=is_online_tts_provider(tts_provider),
                has_value=bool(owner._tts_api_key_edit.text().strip()),
            ),
        )
        ocr_provider = normalize_ocr_provider(owner._selected_ocr_provider())
        ocr_required = is_online_ocr_provider(ocr_provider) and (
            ocr_provider != "ocr_space" or bool(owner._ocr_api_key_edit.text().strip())
        )
        self.set_model_status_pill(
            "model_status_ocr",
            owner._tr("model_status_ocr"),
            self.provider_status_text(
                provider=ocr_provider,
                required=ocr_required,
                has_value=bool(owner._ocr_api_key_edit.text().strip()),
                demo=is_online_ocr_provider(ocr_provider) and ocr_provider == "ocr_space" and not ocr_required,
            ),
        )
        cleanup_provider = owner._selected_transcript_cleanup_provider()
        cleanup_required = (
            owner._selected_transcript_cleanup_mode() != "off"
            and cleanup_provider in owner._PRIMARY_TRANSCRIPT_CLEANUP_KEY_PROVIDERS
        )
        self.set_model_status_pill(
            "model_status_cleanup",
            owner._tr("model_status_cleanup"),
            self.provider_status_text(
                provider=cleanup_provider,
                required=cleanup_required,
                has_value=bool(owner._transcript_cleanup_api_key_edit.text().strip()),
                disabled=owner._selected_transcript_cleanup_mode() == "off",
            ),
        )

    def provider_status_text(
        self,
        *,
        provider: object,
        required: bool,
        has_value: bool,
        demo: bool = False,
        disabled: bool = False,
    ) -> tuple[str, str]:
        owner = self._owner
        provider_text = str(provider or owner._tr("auto")).replace("_", " ")
        if disabled:
            return owner._tr("model_status_disabled").format(provider=provider_text), "muted"
        if demo:
            return owner._tr("model_status_demo").format(provider=provider_text), "warn"
        if required and not has_value:
            return owner._tr("model_status_missing_key").format(provider=provider_text), "warn"
        if required:
            return owner._tr("model_status_online_ready").format(provider=provider_text), "ok"
        return owner._tr("model_status_local_ready").format(provider=provider_text), "ok"

    def set_model_status_pill(self, key: str, title: str, status: tuple[str, str]) -> None:
        label = getattr(self._owner, "_model_status_labels", {}).get(key)
        if label is None:
            return
        detail, status_kind = status
        label.setText(f"{title}\n{detail}")
        label.setProperty("status", status_kind)
        label.style().unpolish(label)
        label.style().polish(label)

    def set_api_key_status(
        self,
        label: Any,
        *,
        required: bool,
        has_value: bool,
        demo: bool = False,
        secret: bool = False,
    ) -> None:
        if demo:
            key = "api_key_status_demo"
            color = "#b45309"
        elif not required:
            key = "api_secret_status_not_needed" if secret else "api_key_status_not_needed"
            color = "#667085"
        elif has_value:
            key = "api_secret_status_saved" if secret else "api_key_status_saved"
            color = "#237a57"
        else:
            key = "api_secret_status_missing" if secret else "api_key_status_missing"
            color = "#b42318"
        label.setText(self._owner._tr(key))
        label.setProperty("api_status_key", key)
        label.setStyleSheet(f"color: {color}; font-size: 8.5pt;")
