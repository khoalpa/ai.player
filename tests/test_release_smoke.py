from __future__ import annotations

from pathlib import Path

import pytest

from ai_player.core.config import AppConfig
from ai_player.services.ffmpeg import probe_duration_seconds, run_ffmpeg
from ai_player.workers import export_worker


class _SilentTTSProvider:
    def synthesize(self, _text: str, output_path: Path, voice: str | None = None) -> None:
        run_ffmpeg(
            [
                "-f",
                "lavfi",
                "-i",
                "sine=frequency=440:duration=0.8",
                "-ar",
                44100,
                "-ac",
                2,
                "-c:a",
                "pcm_s16le",
                "-y",
                Path(output_path),
            ]
        )

    def close(self) -> None:
        pass


@pytest.mark.parametrize("export_kind", ["audio", "video"])
def test_release_smoke_exports_sample_media_with_transcript_tts(monkeypatch, qapp, tmp_path, export_kind: str) -> None:
    sample_video = Path("samples/demo-video.mp4")
    if not sample_video.exists():
        pytest.skip("sample video is not available")

    transcript = tmp_path / "smoke.srt"
    transcript.write_text(
        "1\n00:00:00,000 --> 00:00:01,000\nHello AI Player smoke test.\n\n",
        encoding="utf-8",
    )
    output_path = tmp_path / ("smoke.wav" if export_kind == "audio" else "smoke.mp4")
    config = AppConfig(
        audio_source="transcript",
        transcript_path=str(transcript),
        translator_provider="none",
        local_translation_offline=False,
        tts_provider="vieneu",
        vieneu_tts_offline=False,
        export_video_quality="compact",
    )
    monkeypatch.setattr(export_worker, "create_tts_provider", lambda _config: _SilentTTSProvider())
    monkeypatch.setattr(export_worker, "_export_worker_count", lambda: 1)
    worker = export_worker.DubbingExportWorker(
        str(sample_video),
        str(output_path),
        export_kind,
        config,
        export_worker.ExportRange(0.0, 1.3),
    )
    failures: list[str] = []
    worker.failed.connect(failures.append)

    worker.run()

    assert failures == []
    assert output_path.exists()
    assert probe_duration_seconds(output_path) >= 0.5
