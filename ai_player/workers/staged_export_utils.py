from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from ai_player.core.config import AppConfig
from ai_player.pipeline.export_plan import ExportRange
from ai_player.services.source_voice_filter import (
    normalize_source_voice_filter_mode,
    normalize_source_voice_filter_model,
)
from ai_player.workers.export_utils import _json_number, _json_text


@dataclass(frozen=True)
class StagedExportPaths:
    output_dir: Path
    work_dir: Path
    audio_dir: Path
    subtitle_dir: Path
    tts_dir: Path
    source_full: Path
    source_srt: Path
    words_json: Path
    target_srt: Path
    source_voice: Path
    background: Path
    target_voice: Path
    final_mix: Path
    final_video: Path
    manifest: Path

    @classmethod
    def from_output_dir(cls, output_dir: Path) -> StagedExportPaths:
        audio_dir = output_dir / "audio"
        subtitle_dir = output_dir / "subtitles"
        tts_dir = output_dir / "tts"
        return cls(
            output_dir=output_dir,
            work_dir=output_dir / ".work",
            audio_dir=audio_dir,
            subtitle_dir=subtitle_dir,
            tts_dir=tts_dir,
            source_full=audio_dir / "source_full.wav",
            source_srt=subtitle_dir / "source.srt",
            words_json=subtitle_dir / "source.words.json",
            target_srt=subtitle_dir / "target.srt",
            source_voice=audio_dir / "source_voice.wav",
            background=audio_dir / "background_no_voice.wav",
            target_voice=audio_dir / "target_voice.wav",
            final_mix=audio_dir / "final_mix.wav",
            final_video=output_dir / "dubbed_video.mp4",
            manifest=output_dir / "manifest.json",
        )

    @property
    def managed_dirs(self) -> tuple[Path, Path, Path, Path]:
        return (self.audio_dir, self.subtitle_dir, self.tts_dir, self.work_dir)

    @property
    def managed_files(self) -> tuple[Path, ...]:
        return (
            self.source_full,
            self.source_srt,
            self.words_json,
            self.target_srt,
            self.source_voice,
            self.background,
            self.target_voice,
            self.final_mix,
            self.final_video,
            self.manifest,
        )

    def artifacts(self) -> dict[str, str]:
        return staged_artifacts(
            self.output_dir,
            source_full=self.source_full,
            source_srt=self.source_srt,
            words_json=self.words_json,
            target_srt=self.target_srt,
            source_voice=self.source_voice,
            background=self.background,
            target_voice=self.target_voice,
            final_mix=self.final_mix,
            final_video=self.final_video,
        )


def staged_manifest_payload(
    *,
    video_path: str,
    export_range: ExportRange,
    artifacts: dict[str, str],
    config: AppConfig,
    status: object,
    stage: object,
    separation_backend: object = "",
) -> dict[str, object]:
    return {
        "version": 1,
        "status": _json_text(status, default=""),
        "stage": _json_text(stage, default=""),
        "source_video": _json_text(video_path, default=""),
        "range": {
            "start_seconds": _json_number(export_range.start_seconds, default=0.0),
            "end_seconds": _json_number(export_range.end_seconds, default=None),
        },
        "artifacts": artifacts,
        "source_voice_filter": {
            "enabled": bool(config.original_audio_voice_filter),
            "mode": normalize_source_voice_filter_mode(config.original_audio_voice_filter_mode),
            "model": normalize_source_voice_filter_model(config.original_audio_voice_filter_model),
            "backend": _json_text(separation_backend, default=""),
        },
    }


def write_staged_manifest(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")


def prepare_staged_output_dir(
    output_dir: Path,
    *,
    managed_dirs: Iterable[Path],
    managed_files: Iterable[Path],
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    managed_dir_list = list(managed_dirs)
    for file_path in managed_files:
        remove_managed_path(output_dir, file_path)
    for directory in managed_dir_list:
        directory.mkdir(parents=True, exist_ok=True)


def staged_artifacts(
    output_dir: Path,
    *,
    source_full: Path,
    source_srt: Path,
    words_json: Path,
    target_srt: Path,
    source_voice: Path,
    background: Path,
    target_voice: Path,
    final_mix: Path,
    final_video: Path,
) -> dict[str, str]:
    return {
        "source_full_wav": manifest_relative_path(output_dir, source_full),
        "source_srt": manifest_relative_path(output_dir, source_srt),
        "source_words_json": manifest_relative_path(output_dir, words_json),
        "target_srt": manifest_relative_path(output_dir, target_srt),
        "source_voice_wav": manifest_relative_path(output_dir, source_voice),
        "background_no_voice_wav": manifest_relative_path(output_dir, background),
        "target_voice_wav": manifest_relative_path(output_dir, target_voice),
        "final_mix_wav": manifest_relative_path(output_dir, final_mix),
        "dubbed_video_mp4": manifest_relative_path(output_dir, final_video),
    }


def manifest_relative_path(output_dir: Path, path: Path) -> str:
    return Path(path).resolve().relative_to(output_dir.resolve()).as_posix()


def remove_managed_path(output_dir: Path, path: Path) -> None:
    try:
        path.resolve().relative_to(output_dir.resolve())
    except (OSError, ValueError):
        return
    if not path.exists() and not path.is_symlink():
        return
    if path.is_symlink() or path.is_file():
        try:
            path.unlink(missing_ok=True)
        except OSError:
            return
