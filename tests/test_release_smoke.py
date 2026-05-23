from __future__ import annotations

import json
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


def test_packaged_vieneu_sample_asset_names_are_ascii() -> None:
    sample_dir = Path("ai_player/vieneu_tts/vieneu/assets/samples")
    sample_names = [path.name for path in sample_dir.iterdir() if path.is_file()]

    assert sample_names
    assert all(name.isascii() for name in sample_names)


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


def test_release_smoke_exports_staged_sample_media(monkeypatch, qapp, tmp_path) -> None:
    sample_video = Path("samples/demo-video.mp4")
    if not sample_video.exists():
        pytest.skip("sample video is not available")

    config = AppConfig(
        audio_source="original",
        translator_provider="none",
        local_translation_offline=False,
        tts_provider="vieneu",
        vieneu_tts_offline=False,
        original_audio_voice_filter=True,
        original_audio_voice_filter_mode="fast",
        export_video_quality="compact",
    )
    worker = export_worker.StagedDubbingExportWorker(
        str(sample_video),
        str(tmp_path),
        config,
        export_worker.ExportRange(0.0, 1.2),
    )
    failures: list[str] = []
    finished: list[str] = []
    worker.failed.connect(failures.append)
    worker.export_finished.connect(finished.append)
    monkeypatch.setattr(export_worker, "create_tts_provider", lambda _config: _SilentTTSProvider())
    monkeypatch.setattr(
        export_worker,
        "get_shared_vietnamese_translator",
        lambda _config: type("Translator", (), {"translate_many": lambda self, texts, _language: list(texts)})(),
    )
    worker._validate_whisper_model = lambda: None
    worker._transcribe_staged = lambda _source_audio: (
        [type("Segment", (), {"text": "hello", "start": 0.0, "end": 0.8, "words": []})()],
        type("Info", (), {"language": "en"})(),
    )

    worker.run()

    assert failures == []
    assert finished == [str(tmp_path)]
    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "complete"
    assert probe_duration_seconds(tmp_path / "audio" / "final_mix.wav") >= 0.5
    assert probe_duration_seconds(tmp_path / "dubbed_video.mp4") >= 0.5
