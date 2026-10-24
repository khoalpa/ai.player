from __future__ import annotations

import json
from pathlib import Path

import pytest

from ai_player.adapters import workflow_bindings
from ai_player.adapters.media import document_reader as docs
from ai_player.adapters.media.ffmpeg import probe_duration_seconds, run_ffmpeg
from ai_player.application.workflows import export as export_worker
from ai_player.configuration import AppConfig
from scripts import workflow_smoke_check


class _SilentTTSProvider:
    def synthesize(self, _text: str, output_path: Path, voice: str | None = None) -> None:
        run_ffmpeg(
            [
                "-f",
                "lavfi",
                "-i",
                "sine=frequency=440:duration=0.8",
                "-ar",
                48000,
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


def test_packaged_vieneu_v3_voice_metadata_replaces_old_runtime() -> None:
    catalog = json.loads(Path("ai_player/resources/tts/voices_v3_turbo.json").read_text(encoding="utf-8"))
    assert len(catalog["presets"]) == 25
    assert catalog["default_voice"] in catalog["presets"]
    assert all(entry["gender"] in {"male", "female"} for entry in catalog["presets"].values())
    assert not list(Path("ai_player/vieneu_tts").rglob("*.py"))


def test_release_smoke_tts_output_duration(tmp_path) -> None:
    expectations = _workflow_expectations()["tts"]
    output_path = tmp_path / "tts.wav"

    _SilentTTSProvider().synthesize(str(expectations["input_text"]), output_path)

    assert output_path.exists()
    assert probe_duration_seconds(output_path) >= float(expectations["min_output_duration_seconds"])


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
    monkeypatch.setattr("ai_player.adapters.tts.tts.create_tts_provider", lambda _config: _SilentTTSProvider())
    monkeypatch.setattr("ai_player.adapters.pipeline.export_utils._export_worker_count", lambda: 1)
    worker = export_worker.DubbingExportWorker(
        str(sample_video),
        str(output_path),
        export_kind,
        config,
        export_worker.ExportRange(0.0, 1.3),
        dependencies=workflow_bindings.export(),
    )
    failures: list[str] = []
    worker.failed.connect(failures.append)

    worker.run()

    assert failures == []
    assert output_path.exists()
    _assert_export_output_metrics(output_path, export_kind)


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
        dependencies=workflow_bindings.export(),
    )
    failures: list[str] = []
    finished: list[str] = []
    worker.failed.connect(failures.append)
    worker.export_finished.connect(finished.append)
    monkeypatch.setattr("ai_player.adapters.tts.tts.create_tts_provider", lambda _config: _SilentTTSProvider())
    monkeypatch.setattr(
        "ai_player.runtime.translation_runtime.get_shared_vietnamese_translator",
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
    words_payload = json.loads((tmp_path / "subtitles" / "source.words.json").read_text(encoding="utf-8"))
    asr_expectations = _workflow_expectations()["asr"]
    assert len(words_payload["segments"]) >= int(asr_expectations["min_segment_count"])
    _assert_export_output_metrics(tmp_path / "audio" / "final_mix.wav", "audio")
    _assert_export_output_metrics(tmp_path / "dubbed_video.mp4", "video")


def test_release_smoke_document_text_to_transcript_audio_export(monkeypatch, qapp, tmp_path) -> None:
    sample_video = Path("samples/demo-video.mp4")
    if not sample_video.exists():
        pytest.skip("sample video is not available")

    monkeypatch.setattr(docs, "CONFIG_DIR", tmp_path)
    transcript = docs.create_text_document_transcript(
        "AI Player document smoke. This creates a short transcript timeline.",
        title="Document smoke",
        seconds_per_segment=1,
    )
    output_path = tmp_path / "document-smoke.wav"
    config = AppConfig(
        audio_source="document_editor",
        transcript_path=str(transcript.transcript_path),
        translator_provider="none",
        local_translation_offline=False,
        tts_provider="vieneu",
        vieneu_tts_offline=False,
    )
    monkeypatch.setattr("ai_player.adapters.tts.tts.create_tts_provider", lambda _config: _SilentTTSProvider())
    monkeypatch.setattr("ai_player.adapters.pipeline.export_utils._export_worker_count", lambda: 1)
    worker = export_worker.DubbingExportWorker(
        str(sample_video),
        str(output_path),
        "audio",
        config,
        export_worker.ExportRange(0.0, 2.0),
        dependencies=workflow_bindings.export(),
    )
    failures: list[str] = []
    worker.failed.connect(failures.append)

    worker.run()

    assert failures == []
    assert transcript.segment_count >= 1
    _assert_export_output_metrics(output_path, "audio")


def _workflow_expectations() -> dict[str, dict[str, object]]:
    baseline = workflow_smoke_check.load_smoke_baseline()
    expectations = baseline.get("workflow_expectations")
    assert isinstance(expectations, dict)
    return expectations


def _assert_export_output_metrics(path: Path, export_kind: str) -> None:
    expectations = _workflow_expectations()["export"]
    metrics = workflow_smoke_check.media_sample_metrics(path)

    assert metrics["exists"] is True
    assert metrics["duration_seconds"] >= float(expectations["min_output_duration_seconds"])
    if export_kind == "audio":
        assert metrics["has_audio_stream"] is bool(expectations["audio_export_requires_audio_stream"])
    else:
        assert metrics["has_audio_stream"] is bool(expectations["video_export_requires_audio_stream"])
        assert metrics["has_video_stream"] is bool(expectations["video_export_requires_video_stream"])
