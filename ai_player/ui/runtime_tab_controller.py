from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ai_player.ui.features.context import WindowContext

import json
import os
import platform
import shutil
import subprocess
import time
from pathlib import Path

from PySide6.QtWidgets import QLabel, QPushButton, QWidget

from ai_player.adapters.media.ffmpeg import ffprobe_executable
from ai_player.core.redaction import redact_secrets
from ai_player.runtime.runtime_diagnostics import (
    collect_runtime_diagnostics,
    format_runtime_diagnostics_summary,
)
from ai_player.runtime.runtime_health import build_runtime_health, format_runtime_health
from ai_player.runtime.runtime_privacy import build_runtime_privacy, format_runtime_privacy
from ai_player.runtime.runtime_telemetry import RUNTIME_TELEMETRY, format_runtime_telemetry
from ai_player.ui.player_window_state import RuntimeStatusState
from ai_player.ui.player_window_utils import (
    float_value as _float_value,
)
from ai_player.ui.player_window_utils import (
    format_bitrate as _format_bitrate,
)
from ai_player.ui.player_window_utils import (
    format_rate as _format_rate,
)
from ai_player.ui.player_window_utils import (
    repair_mojibake as _repair_mojibake,
)
from ai_player.ui.runtime_doctor_onboarding import build_runtime_doctor_profile_summary
from ai_player.ui.runtime_metrics import (
    process_cpu_percent,
    process_memory_bytes,
    read_system_cpu_times,
    system_cpu_percent_from_times,
    system_memory,
)
from ai_player.ui.task_center import collect_background_tasks, format_background_tasks, stop_background_tasks


class RuntimeTabController:
    def __init__(self, owner: WindowContext, state: RuntimeStatusState) -> None:
        self.context = owner
        self._state = state
        self._labels: dict[str, QLabel] = {}
        self._stop_tasks_button: QPushButton | None = None
        self._tab_widget: QWidget | None = None

    def bind(
        self,
        *,
        labels: dict[str, QLabel],
        stop_tasks_button: QPushButton | None,
        tab_widget: QWidget,
    ) -> None:
        self._labels = labels
        self._stop_tasks_button = stop_tasks_button
        self._tab_widget = tab_widget

    def refresh(self) -> None:
        if not self._labels:
            return

        now = time.perf_counter()
        process_now = time.process_time()
        process_cpu = process_cpu_percent(
            previous_wall=self._state.last_wall,
            previous_process=self._state.last_process,
            current_wall=now,
            current_process=process_now,
            cpu_count=os.cpu_count(),
        )
        self._state.last_wall = now
        self._state.last_process = process_now

        system_cpu = self.system_cpu_percent()
        process_memory = self.process_memory_bytes()
        memory = self.system_memory()

        self._state.gpu_tick += 1
        runtime_tab_active = self.is_active()
        if runtime_tab_active and (self._state.gpu_tick == 1 or self._state.gpu_tick % 5 == 0):
            self._state.gpu_text = self.gpu_status_text()

        self._labels["process_cpu"].setText(f"{process_cpu:.1f}%")
        self._labels["process_memory"].setText(
            self.context.runtime._format_bytes(process_memory) if process_memory else self._tr("runtime_unavailable")
        )
        self._labels["system_cpu"].setText(
            f"{system_cpu:.1f}%" if system_cpu is not None else self._tr("runtime_unavailable")
        )
        if memory:
            used, total, percent = memory
            self._labels["system_memory"].setText(
                f"{self.context.runtime._format_bytes(used)} / "
                f"{self.context.runtime._format_bytes(total)} ({percent:.1f}%)"
            )
        else:
            self._labels["system_memory"].setText(self._tr("runtime_unavailable"))
        self._labels["media"].setText(self.media_info_text_current())
        self._labels["health"].setText(self.health_summary())
        self._labels["privacy"].setText(self.privacy_summary())
        tasks = collect_background_tasks(self.context)
        self._labels["tasks"].setText(self.task_summary(tasks))
        if not self._state.doctor_profile_text or (runtime_tab_active and self._state.gpu_tick % 10 == 0):
            self._state.doctor_profile_text = self.doctor_profile_summary()
        self._labels["doctor_profiles"].setText(self._state.doctor_profile_text)
        if self._stop_tasks_button is not None:
            self._stop_tasks_button.setEnabled(bool(tasks))
        if runtime_tab_active or self.context.get("_settings_tabs", None) is None:
            self._labels["gpu_runtime"].setText(self.gpu_runtime_text())
        else:
            self._labels["gpu_runtime"].setText(self.gpu_runtime_config_text())
        self._labels["gpu"].setText(self._state.gpu_text)
        self._labels["python"].setText(platform.python_version())
        self._labels["platform"].setText(platform.platform())
        self._labels["pid"].setText(str(os.getpid()))
        if runtime_tab_active and (self._state.gpu_tick == 1 or self._state.gpu_tick % 10 == 0):
            self._labels["diagnostics"].setText(self.diagnostics_summary())

    def tab_changed(self, index: int) -> None:
        tabs = self.context.get("_settings_tabs", None)
        if self._tab_widget is None or tabs is None:
            return
        if self.context.runtime._settings_tab_contains(tabs.widget(index), self._tab_widget):
            self._state.gpu_tick = 0
            self._state.media_info_text = self.media_info_text_current(force=True)
            self.refresh()

    def is_active(self) -> bool:
        tabs = self.context.get("_settings_tabs", None)
        return bool(
            tabs is not None
            and self._tab_widget is not None
            and self.context.runtime._settings_tab_contains(tabs.currentWidget(), self._tab_widget)
        )

    def media_info_text_current(self, force: bool = False) -> str:
        source_path = self._state.media_path or (self.context.get("_video_path", "") or "")
        if self.context.media.document.mode:
            return self.document_runtime_info()
        if not source_path:
            self._state.media_info_path = ""
            self._state.media_info_text = self._tr("status_no_video")
            return self._state.media_info_text
        if not force and source_path == self._state.media_info_path:
            return self._state.media_info_text
        self._state.media_info_path = source_path
        self._state.media_info_text = self.probe_media_info(source_path)
        return self._state.media_info_text

    def document_runtime_info(self) -> str:
        if not self.context.media.document.pages:
            return self._tr("runtime_document_no_page")
        total_seconds = self.context.media.document.duration_ms / 1000.0
        current_seconds = self.context.media._document_time_ms() / 1000.0
        image_pages = sum(1 for page in self.context.media.document.pages if page.image_path)
        return "\n".join(
            [
                self._tr("runtime_source_document"),
                self._tr("runtime_pages").format(count=len(self.context.media.document.pages), image_count=image_pages),
                self._tr("runtime_duration").format(duration=self.context.runtime._format_seconds(total_seconds)),
                self._tr("runtime_position").format(position=self.context.runtime._format_seconds(current_seconds)),
                self._tr("runtime_transcript").format(
                    path=self.context.layout._transcript_path_edit.text().strip() or self._tr("runtime_none")
                ),
            ]
        )

    def probe_media_info(self, source_path: str) -> str:
        if source_path.lower().startswith(("http://", "https://", "rtsp://", "rtmp://", "mms://")):
            return self._tr("runtime_stream_source").format(source=source_path)
        path = Path(source_path)
        if not path.exists():
            return self._tr("runtime_missing_file").format(source=source_path)
        ffprobe = ffprobe_executable()
        if not ffprobe:
            return self._tr("runtime_missing_ffprobe").format(path=path)
        command = [
            ffprobe,
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            str(path),
        ]
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=5.0,
            )
        except Exception as exc:
            return self._tr("runtime_probe_failed").format(detail=_repair_mojibake(redact_secrets(exc)), path=path)
        if result.returncode != 0:
            detail = _repair_mojibake(redact_secrets(result.stderr.strip())) or self._tr("runtime_empty_ffprobe_error")
            return self._tr("runtime_probe_failed").format(detail=detail, path=path)
        try:
            data = json.loads(result.stdout or "{}")
        except Exception as exc:
            return self._tr("runtime_json_failed").format(detail=_repair_mojibake(redact_secrets(exc)), path=path)
        return self.format_media_probe(path, data)

    def format_media_probe(self, path: Path, data: dict) -> str:
        streams = data.get("streams") if isinstance(data, dict) else []
        streams = streams if isinstance(streams, list) else []
        streams = [item for item in streams if isinstance(item, dict)]
        fmt = data.get("format") if isinstance(data, dict) else {}
        fmt = fmt if isinstance(fmt, dict) else {}
        video = next((item for item in streams if item.get("codec_type") == "video"), {})
        audio_streams = [item for item in streams if item.get("codec_type") == "audio"]
        subtitle_count = sum(1 for item in streams if item.get("codec_type") == "subtitle")
        unknown = self._tr("runtime_unknown")
        try:
            file_size = path.stat().st_size
        except OSError:
            file_size = None

        lines = [
            f"File: {path.name}",
            self._tr("runtime_folder").format(folder=path.parent),
            self._tr("runtime_container").format(
                container=fmt.get("format_long_name") or fmt.get("format_name") or path.suffix.lstrip(".") or unknown
            ),
            self._tr("runtime_size").format(size=self.context.runtime._format_bytes(file_size)),
            self._tr("runtime_duration").format(
                duration=self.context.runtime._format_seconds(_float_value(fmt.get("duration")))
            ),
            self._tr("runtime_total_bitrate").format(bitrate=_format_bitrate(fmt.get("bit_rate"), unknown)),
        ]
        if video:
            lines.extend(
                [
                    self._tr("runtime_video_codec").format(
                        codec=video.get("codec_long_name") or video.get("codec_name") or unknown
                    ),
                    self._tr("runtime_resolution").format(
                        width=video.get("width") or "?",
                        height=video.get("height") or "?",
                    ),
                    f"FPS: {_format_rate(video.get('avg_frame_rate') or video.get('r_frame_rate'), unknown)}",
                    self._tr("runtime_pixel_format").format(format=video.get("pix_fmt") or unknown),
                    self._tr("runtime_video_bitrate").format(bitrate=_format_bitrate(video.get("bit_rate"), unknown)),
                ]
            )
        else:
            lines.append(self._tr("runtime_no_video_stream"))
        if audio_streams:
            for index, audio in enumerate(audio_streams, 1):
                lines.append(
                    self._tr("runtime_audio_stream").format(
                        index=index,
                        codec=audio.get("codec_long_name") or audio.get("codec_name") or unknown,
                        rate=audio.get("sample_rate") or "?",
                        channels=audio.get("channels") or "?",
                        bitrate=_format_bitrate(audio.get("bit_rate"), unknown),
                    )
                )
        else:
            lines.append(self._tr("runtime_no_audio_stream"))
        lines.append(self._tr("runtime_subtitle_streams").format(count=subtitle_count))
        return "\n".join(lines)

    def system_cpu_percent(self) -> float | None:
        current = read_system_cpu_times()
        previous = self._state.last_system_cpu
        self._state.last_system_cpu = current
        return system_cpu_percent_from_times(previous, current)

    @staticmethod
    def read_system_cpu_times() -> tuple[int, int] | None:
        return read_system_cpu_times()

    @staticmethod
    def process_memory_bytes() -> int | None:
        return process_memory_bytes()

    @staticmethod
    def system_memory() -> tuple[int, int, float] | None:
        return system_memory()

    def gpu_status_text(self) -> str:
        nvidia_smi = shutil.which("nvidia-smi")
        if not nvidia_smi:
            return self._tr("runtime_no_nvidia")
        command = [
            nvidia_smi,
            "--query-gpu=index,name,utilization.gpu,memory.used,memory.total",
            "--format=csv,noheader,nounits",
        ]
        try:
            startupinfo = None
            if os.name == "nt":
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=1.0,
                startupinfo=startupinfo,
            )
        except Exception as exc:
            return self._tr("runtime_gpu_failed").format(detail=_repair_mojibake(redact_secrets(exc)))
        if result.returncode != 0:
            detail = _repair_mojibake(redact_secrets(result.stderr.strip())) or self._tr("runtime_nvidia_error")
            return self._tr("runtime_gpu_failed").format(detail=detail)
        lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        if not lines:
            return self._tr("runtime_no_gpu_info")
        formatted = []
        for line in lines:
            parts = [part.strip() for part in line.split(",")]
            if len(parts) >= 5:
                index, name, util, used, total = parts[:5]
                formatted.append(f"GPU {index}: {name} | {util}% | {used}/{total} MB")
            else:
                formatted.append(line)
        return "\n".join(formatted)

    def gpu_runtime_text(self) -> str:
        lines = [self.gpu_runtime_config_text()]
        try:
            import torch

            lines.append(f"Torch: {getattr(torch, '__version__', '?')} | CUDA={torch.cuda.is_available()}")
        except Exception as exc:
            lines.append(self._tr("runtime_torch_failed").format(detail=_repair_mojibake(redact_secrets(exc))))
        try:
            import ctranslate2

            version = getattr(ctranslate2, "__version__", "?")
            cuda_count = ctranslate2.get_cuda_device_count()
            lines.append(f"CTranslate2: {version} | CUDA devices={cuda_count}")
        except Exception as exc:
            lines.append(self._tr("runtime_ctranslate_failed").format(detail=_repair_mojibake(redact_secrets(exc))))
        return "\n".join(lines)

    def gpu_runtime_config_text(self) -> str:
        return self._tr("runtime_config_line").format(
            whisper=(
                f"{self.context.settings._selected_whisper_device()}/"
                f"{self.context.settings._selected_whisper_compute()} "
                f"b{int(self.context.layout._whisper_beam_slider.value())}"
            ),
            translator=self.context.settings._selected_translation_device(),
            vieneu=self.context.settings._selected_vieneu_device(),
        )

    def diagnostics_summary(self) -> str:
        try:
            report = collect_runtime_diagnostics(include_audio_devices=False)
            return format_runtime_diagnostics_summary(report)
        except Exception as exc:
            return self._tr("runtime_diagnostics_failed").format(detail=_repair_mojibake(redact_secrets(exc)))

    def health_summary(self) -> str:
        try:
            config = self.context.settings._current_runtime_config()
            health = format_runtime_health(build_runtime_health(config))
            telemetry = format_runtime_telemetry(
                RUNTIME_TELEMETRY.snapshot(),
                getattr(config, "gui_language", "vi"),
            )
            return f"{health}\n{telemetry}"
        except Exception as exc:
            return self._tr("runtime_health_failed").format(detail=_repair_mojibake(redact_secrets(exc)))

    def privacy_summary(self) -> str:
        try:
            return format_runtime_privacy(
                build_runtime_privacy(self.context.settings._current_runtime_config()),
                offline_text=self._tr("runtime_privacy_offline"),
                translate=self._tr,
            )
        except Exception as exc:
            return self._tr("runtime_privacy_failed").format(detail=_repair_mojibake(redact_secrets(exc)))

    def task_summary(self, tasks: tuple[object, ...] | None = None) -> str:
        try:
            if tasks is None:
                tasks = collect_background_tasks(self.context)
            return format_background_tasks(
                tasks,
                idle_text=self._tr("runtime_tasks_idle"),
            )
        except Exception as exc:
            return self._tr("runtime_tasks_failed").format(detail=_repair_mojibake(redact_secrets(exc)))

    def doctor_profile_summary(self) -> str:
        try:
            return build_runtime_doctor_profile_summary()
        except Exception as exc:
            return self._tr("runtime_diagnostics_failed").format(detail=_repair_mojibake(redact_secrets(exc)))

    def stop_background_tasks(self) -> None:
        summary = stop_background_tasks(self.context)
        self.refresh()
        if summary.failed:
            message = self._tr("runtime_tasks_stop_partial").format(failed=", ".join(summary.failed))
        else:
            message = self._tr("runtime_tasks_stopped").format(count=summary.stopped)
        self.context.window.statusBar().showMessage(message)

    def _tr(self, key: str) -> str:
        return self.context.settings._tr(key)
