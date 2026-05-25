from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from ai_player.core.config import AppConfig
from ai_player.pipeline import export_plan, transcript_source
from ai_player.ui import player_window_export
from ai_player.workers import (
    export_worker,
)
from ai_player.workers.dubbing_worker import DubbingWorker, _segment_start_key


@pytest.mark.parametrize(
    ("quality", "crf", "copy"),
    [
        ("compact", 28, False),
        ("balanced", 23, False),
        ("high", 18, False),
        ("archival", 16, False),
        ("source", 18, False),
    ],
)
def test_video_quality_settings(quality: str, crf: int, copy: bool) -> None:
    settings = export_worker._video_quality_settings(quality)

    assert settings.crf == crf
    assert settings.copy_source_video is copy


@pytest.mark.parametrize(
    ("func", "needle"),
    [
        (export_worker._scale_filter, "force_original_aspect_ratio=decrease"),
        (export_worker._document_scale_filter, "pad="),
    ],
)
def test_scale_filters_contain_expected_operations(func, needle: str) -> None:
    assert needle in func(1280, 720)


def test_scale_filters_tolerate_invalid_dimensions() -> None:
    assert "min(1920\\,iw)" in export_worker._scale_filter("bad", 0)
    assert "pad=1920:1080" in export_worker._document_scale_filter(float("inf"), "bad")

@pytest.mark.parametrize(("value", "seconds"), [("00:00:01,500", 1.5), ("01:02:03.004", 3723.004)])
def test_parse_srt_time(value: str, seconds: float) -> None:
    assert export_worker._parse_srt_time(value) == seconds


def test_parse_srt_time_tolerates_pathological_digit_count() -> None:
    assert export_worker._parse_srt_time(f"{'9' * 5000}:00:00,000") == 0.0


def test_export_range_time_parser_rejects_non_finite_values() -> None:
    with pytest.raises(ValueError):
        player_window_export._parse_time("inf")
    assert player_window_export._format_time(float("inf")) == "00:00:00"


def test_transcript_source_time_helpers_tolerate_invalid_values() -> None:
    assert transcript_source.parse_timestamp("") is None
    huge_time = "9999999999999999999999999999999999999999999999999999999999999999:00"
    assert transcript_source.parse_timestamp(huge_time) is None
    assert transcript_source.format_hhmmss(float("inf")) == "00:00:00"
    assert transcript_source.parse_plain_transcript("one\ntwo", "bad") == [
        transcript_source.TranscriptEntry(0.0, 5.0, "one"),
        transcript_source.TranscriptEntry(5.0, 10.0, "two"),
    ]


def test_timed_transcript_sanitizes_missing_or_reversed_end() -> None:
    entries = transcript_source.parse_timed_transcript(
        "1\n00:00:02,000 --> 00:00:01,000\nHello\n\n"
        "2\n00:00:04,000 --> not-a-time\nWorld\n\n"
    )

    assert entries == [
        transcript_source.TranscriptEntry(2.0, 2.25, "Hello"),
        transcript_source.TranscriptEntry(4.0, 9.0, "World"),
    ]


def test_read_srt_cues_parses_multiline_text(tmp_path) -> None:
    path = tmp_path / "demo.srt"
    path.write_text("1\n00:00:00,000 --> 00:00:02,000\nHello\nworld\n\n", encoding="utf-8")

    cues = export_worker._read_srt_cues(path)

    assert cues == [export_worker.TranscriptCue(0.0, 2.0, "Hello world")]


def test_read_srt_cues_sanitizes_reversed_timing(tmp_path) -> None:
    path = tmp_path / "demo.srt"
    path.write_text("1\n00:00:02,000 --> 00:00:01,000\nHello\n\n", encoding="utf-8")

    cues = export_worker._read_srt_cues(path)

    assert cues == [export_worker.TranscriptCue(2.0, 2.25, "Hello")]


def test_write_srt_cues_round_trips_timing(tmp_path) -> None:
    path = tmp_path / "target.srt"

    export_plan.write_srt_cues(
        path,
        [
            export_worker.TranscriptCue(0.0, 0.5, ""),
            export_worker.TranscriptCue(1.25, 3.5, "Xin chao"),
        ],
    )

    text = path.read_text(encoding="utf-8")
    assert text.startswith("1\n00:00:01,250 --> 00:00:03,500")
    assert export_worker._read_srt_cues(path) == [export_worker.TranscriptCue(1.25, 3.5, "Xin chao")]


def test_write_srt_cues_sanitizes_text_and_timing(tmp_path) -> None:
    path = tmp_path / "target.srt"

    export_plan.write_srt_cues(
        path,
        [export_worker.TranscriptCue(2.0, 1.0, b"Hello\n\nworld")],
    )

    assert path.read_text(encoding="utf-8") == "1\n00:00:02,000 --> 00:00:02,250\nHello world\n"
    assert export_worker._read_srt_cues(path) == [export_worker.TranscriptCue(2.0, 2.25, "Hello world")]


def test_export_time_helpers_tolerate_nonfinite_values() -> None:
    export_range = export_worker.ExportRange(float("inf"), float("inf"))

    assert export_range.start_seconds == 0.0
    assert export_range.end_seconds is None
    assert export_plan.format_srt_time(float("inf")) == "00:00:00,000"
    assert export_plan.format_seconds_arg(float("nan")) == "0.000"
    assert export_range.shift(float("nan")) == 0.0


def test_export_timeline_helpers_tolerate_nonfinite_values(tmp_path) -> None:
    args = export_plan.timeline_mix_args([(tmp_path / "cue.wav", float("inf"))], tmp_path / "mixed.wav")

    assert "adelay=0:all=1" in args[args.index("-filter_complex") + 1]
    assert (
        export_plan.cues_end_seconds(
            [
                export_worker.ExportCue(
                    float("inf"),
                    "source",
                    "target",
                    tmp_path / "cue.wav",
                    duration_seconds=float("nan"),
                )
            ]
        )
        == 0.0
    )


def test_staged_background_voice_mix_ducks_background(tmp_path) -> None:
    args = export_worker._staged_background_voice_mix_args(
        tmp_path / "background.wav",
        tmp_path / "voice.wav",
        tmp_path / "final.wav",
        voice_volume_percent=85,
    )

    filter_complex = args[args.index("-filter_complex") + 1]
    assert "sidechaincompress" in filter_complex
    assert "volume=0.850" in filter_complex
    assert args[-1] == tmp_path / "final.wav"

def test_mix_args_tolerate_invalid_numeric_options(tmp_path) -> None:
    timeline_args = export_plan.timeline_mix_args(
        [(tmp_path / "cue.wav", 0.0)],
        tmp_path / "timeline.wav",
        sample_rate="bad",
        channels=0,
    )
    staged_args = export_worker._staged_background_voice_mix_args(
        tmp_path / "background.wav",
        tmp_path / "voice.wav",
        tmp_path / "final.wav",
        sample_rate=float("inf"),
        channels="bad",
        voice_volume_percent="bad",
    )

    assert timeline_args[timeline_args.index("-ar") + 1] == "44100"
    assert timeline_args[timeline_args.index("-ac") + 1] == "2"
    assert staged_args[staged_args.index("-ar") + 1] == "48000"
    assert staged_args[staged_args.index("-ac") + 1] == "2"
    assert "volume=1.000" in staged_args[staged_args.index("-filter_complex") + 1]


def test_mix_args_keep_channel_layout_and_output_channels_consistent(tmp_path) -> None:
    args = export_plan.timeline_mix_args(
        [(tmp_path / "cue.wav", 0.0)],
        tmp_path / "timeline.wav",
        channels=6,
    )

    filter_complex = args[args.index("-filter_complex") + 1]
    assert "channel_layouts=stereo" in filter_complex
    assert args[args.index("-ac") + 1] == "2"


def test_staged_export_worker_writes_artifact_manifest(monkeypatch, tmp_path) -> None:
    config = AppConfig(audio_source="original", tts_provider="none", original_audio_voice_filter=False)
    worker = export_worker.StagedDubbingExportWorker("video.mp4", str(tmp_path), config)
    segment = SimpleNamespace(
        text=" hello ",
        start=0.0,
        end=1.0,
        words=[SimpleNamespace(start=0.0, end=0.4, word="hello", probability=0.9)],
    )
    tts_path = tmp_path / "tts" / "0001-aligned.wav"

    monkeypatch.setattr(export_worker, "create_tts_provider", lambda _config: SimpleNamespace(close=lambda: None))
    monkeypatch.setattr(
        export_worker,
        "get_shared_vietnamese_translator",
        lambda _config: SimpleNamespace(translate_many=lambda texts, _language: [f"{text}-vi" for text in texts]),
    )
    worker._validate_whisper_model = lambda: None
    worker._extract_full_quality_audio = lambda output_path: Path(output_path).write_bytes(b"source")
    worker._transcribe_staged = lambda _source_audio: ((item for item in [segment]), SimpleNamespace(language="en"))

    def fake_stems(_source_audio, background_path, voice_path):
        Path(background_path).write_bytes(b"background")
        Path(voice_path).write_bytes(b"voice")
        return "disabled"

    def fake_target_cues(_source_voice, source_cues, target_cues):
        tts_path.parent.mkdir(parents=True, exist_ok=True)
        tts_path.write_bytes(b"tts")
        return [
            export_worker.ExportCue(
                target_cues[0].start_seconds,
                source_cues[0].text,
                target_cues[0].text,
                tts_path,
                1.0,
            )
        ]

    worker._create_source_audio_stems = fake_stems
    worker._build_target_voice_cues = fake_target_cues
    worker._build_aligned_audio = lambda _cues, output_path: Path(output_path).write_bytes(b"target")
    worker._run_ffmpeg = lambda args, **_kwargs: Path(args[-1]).write_bytes(b"mix")
    worker._mux_video = lambda _audio, output_path=None, **_kwargs: Path(output_path).write_bytes(b"mp4")

    worker.run()

    manifest = tmp_path / "manifest.json"
    assert manifest.exists()
    manifest_data = json.loads(manifest.read_text(encoding="utf-8"))
    assert manifest_data["status"] == "complete"
    assert manifest_data["stage"] == "dubbed_video_ready"
    assert manifest_data["artifacts"]["source_full_wav"] == "audio/source_full.wav"
    assert manifest_data["artifacts"]["dubbed_video_mp4"] == "dubbed_video.mp4"
    assert all(not Path(path).is_absolute() for path in manifest_data["artifacts"].values())
    assert (tmp_path / "subtitles" / "source.srt").exists()
    words_payload = json.loads((tmp_path / "subtitles" / "source.words.json").read_text(encoding="utf-8"))
    assert words_payload["segments"][0]["words"][0]["word"] == "hello"
    assert (tmp_path / "subtitles" / "target.srt").read_text(encoding="utf-8").count("hello-vi") == 1
    assert (tmp_path / "audio" / "final_mix.wav").read_bytes() == b"mix"


def test_staged_manifest_writes_strict_json_for_nonfinite_range(tmp_path) -> None:
    config = AppConfig(audio_source="original")
    worker = export_worker.StagedDubbingExportWorker(
        tmp_path / "video.mp4",
        str(tmp_path),
        config,
        export_worker.ExportRange(0.0, float("inf")),
    )
    manifest_path = tmp_path / "manifest.json"

    worker._write_staged_manifest(
        manifest_path,
        {},
        status=b"running",
        stage=b"initialized",
        separation_backend=b"fast",
    )

    manifest_text = manifest_path.read_text(encoding="utf-8")
    assert "Infinity" not in manifest_text
    manifest = json.loads(manifest_text)
    assert manifest["status"] == "running"
    assert manifest["stage"] == "initialized"
    assert manifest["source_video"].endswith("video.mp4")
    assert manifest["range"]["end_seconds"] is None
    assert manifest["source_voice_filter"]["backend"] == "fast"


def test_staged_words_payload_serializes_backend_scalar_values() -> None:
    class FloatLike:
        def __init__(self, value: float) -> None:
            self.value = value

        def __float__(self) -> float:
            return self.value

    payload = export_worker._segments_words_payload(
        [
            SimpleNamespace(
                text=" hello ",
                start=FloatLike(0.25),
                end=float("nan"),
                words=[
                    SimpleNamespace(
                        start=FloatLike(0.25),
                        end=FloatLike(0.5),
                        word=b"hello",
                        probability=FloatLike(0.8),
                    )
                ],
            )
        ],
        SimpleNamespace(language=b"en", language_probability=FloatLike(0.95)),
    )

    json.dumps(payload, allow_nan=False)
    assert payload["language"] == "en"
    assert payload["language_probability"] == 0.95
    assert payload["segments"][0]["start"] == 0.25
    assert payload["segments"][0]["end"] == 0.0
    assert payload["segments"][0]["words"][0]["word"] == "hello"
    assert payload["segments"][0]["words"][0]["probability"] == 0.8


def test_staged_source_cues_tolerate_invalid_segment_timing(tmp_path) -> None:
    config = AppConfig(audio_source="original", transcript_cleanup_mode="off")
    worker = export_worker.StagedDubbingExportWorker("video.mp4", str(tmp_path), config)

    cues = worker._source_cues_from_segments(
        [SimpleNamespace(text=" hello ", start="not-a-time", end=float("inf"))],
        "en",
    )

    assert cues == [export_worker.TranscriptCue(0.0, 0.25, "hello")]


def test_staged_source_cues_normalize_bytes_text(tmp_path) -> None:
    config = AppConfig(audio_source="original", transcript_cleanup_mode="off")
    worker = export_worker.StagedDubbingExportWorker("video.mp4", str(tmp_path), config)

    cues = worker._source_cues_from_segments(
        [SimpleNamespace(text=b" hello   world ", start=0.0, end=1.0)],
        b"EN",
    )

    assert cues == [export_worker.TranscriptCue(0.0, 1.0, "hello world")]


def test_clean_transcript_many_keeps_items_when_batch_result_is_short_or_blank() -> None:
    cleaner = SimpleNamespace(clean_many=lambda _texts, _language: [" cleaned one ", ""])

    cleaned = export_worker._clean_transcript_many(cleaner, ["one", "two", "three"], "en")

    assert cleaned == ["cleaned one", "two", "three"]


def test_translate_texts_keeps_items_when_batch_result_is_short_or_blank() -> None:
    translator = SimpleNamespace(translate_many=lambda _texts, _language: [" mot ", ""])

    translated = export_worker._translate_texts(translator, ["one", "two", "three"], "en")

    assert translated == ["mot", "two", "three"]


def test_translate_texts_uses_single_item_translator_when_batch_is_missing() -> None:
    translator = SimpleNamespace(translate=lambda text, language: f"{language}:{text}")

    translated = export_worker._translate_texts(translator, ["one", "two"], "en")

    assert translated == ["en:one", "en:two"]


def test_text_batch_alignment_treats_string_result_as_invalid() -> None:
    assert export_worker._align_text_results(["one", "two"], "not a list") == ["one", "two"]


def test_text_batch_alignment_falls_back_for_non_text_items() -> None:
    assert export_worker._align_text_results(["one", "two"], [{"text": "mot"}, b"hai"]) == ["one", "hai"]


def test_staged_export_keep_partial_stops_at_checkpoint(monkeypatch, tmp_path) -> None:
    config = AppConfig(audio_source="original", tts_provider="none", original_audio_voice_filter=False)
    worker = export_worker.StagedDubbingExportWorker("video.mp4", str(tmp_path), config)
    partial_paths: list[str] = []
    worker.partial_finished.connect(partial_paths.append)

    monkeypatch.setattr(export_worker, "create_tts_provider", lambda _config: SimpleNamespace(close=lambda: None))
    monkeypatch.setattr(
        export_worker,
        "get_shared_vietnamese_translator",
        lambda _config: SimpleNamespace(translate_many=lambda texts, _language: texts),
    )
    worker._validate_whisper_model = lambda: None

    def fake_extract(output_path: Path) -> None:
        Path(output_path).write_bytes(b"source")
        worker.stop(keep_partial=True)

    worker._extract_full_quality_audio = fake_extract
    worker._transcribe_staged = lambda _source_audio: pytest.fail("keep partial should stop after the checkpoint")

    worker.run()

    assert partial_paths == [str(tmp_path)]
    manifest_data = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert manifest_data["status"] == "partial"
    assert manifest_data["stage"] == "source_audio_extracted"
    assert (tmp_path / "audio" / "source_full.wav").read_bytes() == b"source"
    assert not (tmp_path / "subtitles" / "source.srt").exists()


def test_staged_export_cancel_during_process_marks_manifest_partial(monkeypatch, tmp_path) -> None:
    config = AppConfig(audio_source="original", tts_provider="none", original_audio_voice_filter=False)
    worker = export_worker.StagedDubbingExportWorker("video.mp4", str(tmp_path), config)
    partial_paths: list[str] = []
    worker.partial_finished.connect(partial_paths.append)

    monkeypatch.setattr(export_worker, "create_tts_provider", lambda _config: SimpleNamespace(close=lambda: None))
    monkeypatch.setattr(
        export_worker,
        "get_shared_vietnamese_translator",
        lambda _config: SimpleNamespace(translate_many=lambda texts, _language: texts),
    )
    worker._validate_whisper_model = lambda: None

    def fake_extract(_output_path: Path) -> None:
        worker.stop(keep_partial=True)
        raise export_worker.ProcessCancelled("cancelled")

    worker._extract_full_quality_audio = fake_extract

    worker.run()

    assert partial_paths == [str(tmp_path)]
    manifest_data = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert manifest_data["status"] == "partial"
    assert manifest_data["stage"] == "initialized"


def test_staged_export_cancel_marks_manifest_cancelled(monkeypatch, tmp_path) -> None:
    config = AppConfig(audio_source="original", tts_provider="none", original_audio_voice_filter=False)
    worker = export_worker.StagedDubbingExportWorker("video.mp4", str(tmp_path), config)
    partial_paths: list[str] = []
    worker.partial_finished.connect(partial_paths.append)

    monkeypatch.setattr(export_worker, "create_tts_provider", lambda _config: SimpleNamespace(close=lambda: None))
    monkeypatch.setattr(
        export_worker,
        "get_shared_vietnamese_translator",
        lambda _config: SimpleNamespace(translate_many=lambda texts, _language: texts),
    )
    worker._validate_whisper_model = lambda: None

    def fake_extract(output_path: Path) -> None:
        Path(output_path).write_bytes(b"source")
        worker.stop()

    worker._extract_full_quality_audio = fake_extract
    worker._transcribe_staged = lambda _source_audio: pytest.fail("cancel should stop after the checkpoint")

    worker.run()

    assert partial_paths == []
    manifest_data = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert manifest_data["status"] == "cancelled"
    assert manifest_data["stage"] == "source_audio_extracted"


def test_staged_export_cancel_during_process_marks_manifest_cancelled(monkeypatch, tmp_path) -> None:
    config = AppConfig(audio_source="original", tts_provider="none", original_audio_voice_filter=False)
    worker = export_worker.StagedDubbingExportWorker("video.mp4", str(tmp_path), config)
    partial_paths: list[str] = []
    worker.partial_finished.connect(partial_paths.append)

    monkeypatch.setattr(export_worker, "create_tts_provider", lambda _config: SimpleNamespace(close=lambda: None))
    monkeypatch.setattr(
        export_worker,
        "get_shared_vietnamese_translator",
        lambda _config: SimpleNamespace(translate_many=lambda texts, _language: texts),
    )
    worker._validate_whisper_model = lambda: None

    def fake_extract(_output_path: Path) -> None:
        worker.stop()
        raise export_worker.ProcessCancelled("cancelled")

    worker._extract_full_quality_audio = fake_extract

    worker.run()

    assert partial_paths == []
    manifest_data = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert manifest_data["status"] == "cancelled"
    assert manifest_data["stage"] == "initialized"


def test_staged_export_cancel_runtime_error_marks_manifest_cancelled(monkeypatch, tmp_path) -> None:
    config = AppConfig(audio_source="original", tts_provider="none", original_audio_voice_filter=False)
    worker = export_worker.StagedDubbingExportWorker("video.mp4", str(tmp_path), config)
    failures: list[str] = []
    worker.failed.connect(failures.append)

    monkeypatch.setattr(export_worker, "create_tts_provider", lambda _config: SimpleNamespace(close=lambda: None))
    monkeypatch.setattr(
        export_worker,
        "get_shared_vietnamese_translator",
        lambda _config: SimpleNamespace(translate_many=lambda texts, _language: texts),
    )
    worker._validate_whisper_model = lambda: None

    def fake_extract(_output_path: Path) -> None:
        worker.stop()
        raise RuntimeError("cancelled before process start")

    worker._extract_full_quality_audio = fake_extract

    worker.run()

    assert failures == []
    manifest_data = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert manifest_data["status"] == "cancelled"
    assert manifest_data["stage"] == "initialized"


def test_staged_export_keep_partial_runtime_error_marks_manifest_partial(monkeypatch, tmp_path) -> None:
    config = AppConfig(audio_source="original", tts_provider="none", original_audio_voice_filter=False)
    worker = export_worker.StagedDubbingExportWorker("video.mp4", str(tmp_path), config)
    partial_paths: list[str] = []
    worker.partial_finished.connect(partial_paths.append)

    monkeypatch.setattr(export_worker, "create_tts_provider", lambda _config: SimpleNamespace(close=lambda: None))
    monkeypatch.setattr(
        export_worker,
        "get_shared_vietnamese_translator",
        lambda _config: SimpleNamespace(translate_many=lambda texts, _language: texts),
    )
    worker._validate_whisper_model = lambda: None

    def fake_extract(_output_path: Path) -> None:
        worker.stop(keep_partial=True)
        raise RuntimeError("partial stop before process start")

    worker._extract_full_quality_audio = fake_extract

    worker.run()

    assert partial_paths == [str(tmp_path)]
    manifest_data = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert manifest_data["status"] == "partial"
    assert manifest_data["stage"] == "initialized"


def test_staged_translate_keeps_all_cues_when_batch_result_is_short(tmp_path) -> None:
    config = AppConfig(audio_source="original")
    worker = export_worker.StagedDubbingExportWorker("video.mp4", str(tmp_path), config)
    worker._translator = SimpleNamespace(translate_many=lambda _texts, _language: ["Mot", ""])
    segment_pairs: list[tuple[str, str]] = []
    worker.segment_ready.connect(lambda original, translated: segment_pairs.append((original, translated)))

    target_cues = worker._translate_source_cues(
        [
            export_worker.TranscriptCue(0.0, 1.0, "one"),
            export_worker.TranscriptCue(1.0, 2.0, "two"),
            export_worker.TranscriptCue(2.0, 3.0, "three"),
        ],
        "en",
    )

    assert [cue.text for cue in target_cues] == ["Mot", "two", "three"]
    assert segment_pairs == [("one", "Mot"), ("two", "two"), ("three", "three")]


def test_staged_export_clears_previous_managed_artifacts(tmp_path) -> None:
    config = AppConfig(audio_source="original")
    worker = export_worker.StagedDubbingExportWorker("video.mp4", str(tmp_path), config)
    for directory in ("audio", "subtitles", "tts", ".work"):
        managed = tmp_path / directory
        managed.mkdir()
        (managed / "stale.wav").write_bytes(b"stale")
    (tmp_path / "dubbed_video.mp4").write_bytes(b"old video")
    (tmp_path / "manifest.json").write_text("old manifest", encoding="utf-8")
    unrelated = tmp_path / "notes.txt"
    unrelated.write_text("keep me", encoding="utf-8")

    worker._temp_dir = tmp_path / ".work"
    worker._prepare_staged_output_dir(tmp_path / "dubbed_video.mp4", tmp_path / "manifest.json")

    assert unrelated.read_text(encoding="utf-8") == "keep me"
    assert not (tmp_path / "dubbed_video.mp4").exists()
    assert not (tmp_path / "manifest.json").exists()
    for directory in ("audio", "subtitles", "tts", ".work"):
        managed = tmp_path / directory
        assert managed.exists()
        assert list(managed.iterdir()) == []


def test_staged_source_filter_normalizes_mode_and_model(monkeypatch, tmp_path) -> None:
    config = AppConfig(
        audio_source="original",
        original_audio_voice_filter=True,
        original_audio_voice_filter_mode="demucs",
        original_audio_voice_filter_model="mdx",
    )
    worker = export_worker.StagedDubbingExportWorker("video.mp4", str(tmp_path), config)
    worker._temp_dir = tmp_path / ".work"
    worker._temp_dir.mkdir()
    source_audio = tmp_path / "source.wav"
    source_audio.write_bytes(b"source")
    commands: list[list[object]] = []

    monkeypatch.setattr(export_worker, "demucs_available", lambda: True)
    monkeypatch.setattr(export_worker, "demucs_command", lambda: ["demucs"])

    def fake_process(command, **_kwargs):
        commands.append(list(command))
        stem_root = worker._temp_dir / "demucs" / "mdx_extra" / source_audio.stem
        stem_root.mkdir(parents=True)
        (stem_root / "no_vocals.wav").write_bytes(b"background")
        (stem_root / "vocals.wav").write_bytes(b"voice")
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(export_worker, "run_cancelable_process", fake_process)
    worker._to_wav = lambda input_path, output_path: Path(output_path).write_bytes(Path(input_path).read_bytes())

    assert worker._create_source_audio_stems(source_audio, tmp_path / "background.wav", tmp_path / "voice.wav") == "ai"
    assert commands[0][commands[0].index("-n") + 1] == "mdx_extra"

def test_staged_demucs_source_filter_rejects_empty_no_vocals(monkeypatch, tmp_path) -> None:
    config = AppConfig(
        audio_source="original",
        original_audio_voice_filter=True,
        original_audio_voice_filter_mode="ai",
    )
    worker = export_worker.StagedDubbingExportWorker("video.mp4", str(tmp_path), config)
    worker._temp_dir = tmp_path / ".work"
    worker._temp_dir.mkdir()
    source_audio = tmp_path / "source.wav"
    source_audio.write_bytes(b"source")

    monkeypatch.setattr(export_worker, "demucs_available", lambda: True)
    monkeypatch.setattr(export_worker, "demucs_command", lambda: ["demucs"])

    def fake_process(command, **_kwargs):
        stem_root = worker._temp_dir / "demucs" / "htdemucs" / source_audio.stem
        stem_root.mkdir(parents=True)
        (stem_root / "no_vocals.wav").write_bytes(b"")
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(export_worker, "run_cancelable_process", fake_process)

    with pytest.raises(RuntimeError, match="Demucs did not create expected file"):
        worker._create_source_audio_stems(source_audio, tmp_path / "background.wav", tmp_path / "voice.wav")


def test_staged_ai_source_filter_does_not_fall_back_to_fast(monkeypatch, tmp_path) -> None:
    config = AppConfig(
        audio_source="original",
        original_audio_voice_filter=True,
        original_audio_voice_filter_mode="ai",
    )
    worker = export_worker.StagedDubbingExportWorker("video.mp4", str(tmp_path), config)
    source_audio = tmp_path / "source.wav"
    source_audio.write_bytes(b"source")

    monkeypatch.setattr(export_worker, "demucs_available", lambda: False)
    worker._create_fast_stems = lambda *_args: pytest.fail("AI mode should not silently fall back to fast filtering")

    with pytest.raises(export_worker.DemucsSeparationError):
        worker._create_source_audio_stems(source_audio, tmp_path / "background.wav", tmp_path / "voice.wav")


def test_staged_target_voice_cue_always_writes_wav_artifact(monkeypatch, tmp_path) -> None:
    config = AppConfig(
        audio_source="original",
        tts_provider="edge",
        dubbing_auto_match_audio=False,
        dubbing_speed_percent=0,
    )
    worker = export_worker.StagedDubbingExportWorker("video.mp4", str(tmp_path), config)
    worker._tts_dir.mkdir(parents=True)
    worker._tts_provider = SimpleNamespace(
        synthesize=lambda _text, output_path, **_kwargs: Path(output_path).write_bytes(b"raw mp3")
    )
    worker._trim_leading_silence = lambda path: path
    worker._to_wav = lambda input_path, output_path: Path(output_path).write_bytes(Path(input_path).read_bytes())

    def fake_match_tts_to_reference(*, tts_path, output_path, **_kwargs):
        assert not Path(output_path).exists()
        return tts_path

    monkeypatch.setattr(export_worker, "match_tts_to_reference", fake_match_tts_to_reference)

    audio_path = worker._build_target_voice_cue(
        0,
        export_worker.TranscriptCue(0.0, 1.0, "Xin chao"),
        tmp_path / "reference.wav",
        "voice",
        "mp3",
    )

    assert audio_path == tmp_path / "tts" / "0001-aligned.wav"
    assert audio_path.read_bytes() == b"raw mp3"

def test_export_range_filters_and_shifts_transcript_cues(monkeypatch, tmp_path) -> None:
    transcript = tmp_path / "demo.srt"
    transcript.write_text(
        "1\n00:00:00,000 --> 00:00:02,000\nskip\n\n"
        "2\n00:00:05,000 --> 00:00:07,000\nkeep\n\n",
        encoding="utf-8",
    )
    config = AppConfig(audio_source="transcript", transcript_path=str(transcript), tts_provider="none")
    worker = export_worker.DubbingExportWorker(
        "video.mp4",
        str(tmp_path / "out.mp4"),
        "video",
        config,
        export_worker.ExportRange(4.0, 8.0),
    )
    worker._temp_dir = tmp_path
    worker._translator = SimpleNamespace(translate_many=lambda texts, _language: [f"{text}-vi" for text in texts])
    monkeypatch.setattr(export_worker, "_export_worker_count", lambda: 1)

    cues = worker._build_transcript_cues()

    assert [cue.original for cue in cues] == ["keep"]
    assert cues[0].start_seconds == 1.0


def test_video_mux_applies_export_range(tmp_path) -> None:
    config = AppConfig(export_video_quality="balanced")
    worker = export_worker.DubbingExportWorker(
        "video.mp4",
        str(tmp_path / "out.mp4"),
        "video",
        config,
        export_worker.ExportRange(10.0, 15.5),
    )
    captured: dict[str, list[object]] = {}
    worker._run_ffmpeg = lambda args, **_kwargs: captured.setdefault("args", args)

    worker._mux_video(tmp_path / "dubbed.wav")

    args = captured["args"]
    assert args[:4] == ["-ss", "10.000", "-i", "video.mp4"]
    assert args[args.index("-t") + 1] == "5.500"


def test_source_export_voice_selector_runs_before_parallel_cue_build(monkeypatch, tmp_path) -> None:
    config = AppConfig(dubbing_auto_voice_gender=True, dubbing_auto_voice_gender_mode="stable")
    worker = export_worker.DubbingExportWorker("video.mp4", str(tmp_path / "out.wav"), "audio", config)
    worker._temp_dir = tmp_path
    worker._translator = SimpleNamespace(translate_many=lambda texts, _language: [f"{text}-vi" for text in texts])
    worker._transcript_cleaner = SimpleNamespace(clean=lambda text, _language: text)
    worker._transcribe_with_fallback = lambda _source_audio: (
        [
            SimpleNamespace(text="first", start=0.0, end=1.0),
            SimpleNamespace(text="second", start=1.0, end=2.0),
        ],
        SimpleNamespace(language="en"),
    )
    calls: list[str] = []

    def fake_extract(_source_audio, _start, _duration, reference_path: Path, **_kwargs) -> None:
        reference_path.write_bytes(b"ref")

    class FakeSelector:
        def select_voice(self, reference_path: Path, *, provider: str, config: AppConfig):
            calls.append(reference_path.stem)
            return SimpleNamespace(voice=f"voice-{reference_path.stem}")

    def fake_build(index, original, translated, start_seconds, duration_seconds, reference_path, voice, tts_suffix):
        return export_worker.ExportCue(
            start_seconds=start_seconds,
            original=original,
            translated=translated,
            audio_path=reference_path,
            duration_seconds=duration_seconds,
        )

    monkeypatch.setattr(export_worker, "extract_audio_range", fake_extract)
    monkeypatch.setattr(export_worker, "_export_worker_count", lambda: 2)
    worker._voice_selector = FakeSelector()
    worker._build_source_export_cue = fake_build

    cues = worker._build_cues(tmp_path / "source.wav")

    assert calls == ["cue-00000-ref", "cue-00001-ref"]
    assert [cue.original for cue in cues] == ["first", "second"]


def test_source_export_tolerates_invalid_segment_timing(monkeypatch, tmp_path) -> None:
    config = AppConfig(tts_provider="none")
    worker = export_worker.DubbingExportWorker("video.mp4", str(tmp_path / "out.wav"), "audio", config)
    worker._temp_dir = tmp_path
    worker._translator = SimpleNamespace(translate_many=lambda texts, _language: texts)
    worker._transcript_cleaner = SimpleNamespace(clean_many=lambda texts, _language: texts)
    worker._transcribe_with_fallback = lambda _source_audio: (
        [SimpleNamespace(text="hello", start="not-a-time", end=float("inf"))],
        SimpleNamespace(language="en"),
    )
    worker._make_silence = lambda _duration, output_path: Path(output_path).write_bytes(b"silence")
    monkeypatch.setattr(export_worker, "extract_audio_range", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(export_worker, "_export_worker_count", lambda: 1)

    cues = worker._build_cues(tmp_path / "source.wav")

    assert len(cues) == 1
    assert cues[0].start_seconds == 0.0
    assert cues[0].duration_seconds == 0.25


def test_source_export_normalizes_bytes_text_and_missing_language(monkeypatch, tmp_path) -> None:
    config = AppConfig(tts_provider="none", transcript_cleanup_mode="off")
    worker = export_worker.DubbingExportWorker("video.mp4", str(tmp_path / "out.wav"), "audio", config)
    worker._temp_dir = tmp_path
    translated_calls: list[tuple[list[str], str | None]] = []
    worker._translator = SimpleNamespace(
        translate_many=lambda texts, language: translated_calls.append((list(texts), language)) or texts
    )
    worker._transcript_cleaner = SimpleNamespace(clean_many=lambda texts, _language: texts)
    worker._transcribe_with_fallback = lambda _source_audio: (
        [SimpleNamespace(text=b" hello   world ", start=0.5, end=1.0)],
        SimpleNamespace(),
    )
    monkeypatch.setattr(export_worker, "extract_audio_range", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(export_worker, "_export_worker_count", lambda: 1)

    cues = worker._build_cues(tmp_path / "source.wav")

    assert translated_calls == [(["hello world"], None)]
    assert cues[0].original == "hello world"


def test_source_export_replaces_non_speech_target_with_silence(tmp_path) -> None:
    config = AppConfig(tts_provider="vieneu")
    worker = export_worker.DubbingExportWorker("video.mp4", str(tmp_path / "out.wav"), "audio", config)
    worker._temp_dir = tmp_path
    worker._tts_provider = SimpleNamespace(
        synthesize=lambda *_args, **_kwargs: pytest.fail("filler sounds should not be sent to TTS")
    )
    worker._make_silence = lambda _duration, output_path: Path(output_path).write_bytes(b"silence")

    cue = worker._build_source_export_cue(
        0,
        "uh",
        "ừm",
        1.0,
        0.5,
        tmp_path / "reference.wav",
        "Doan",
        "wav",
    )

    assert cue.audio_path.read_bytes() == b"silence"
    assert cue.duration_seconds == 0.5

def test_export_duration_helpers_reject_non_finite_probe(monkeypatch, tmp_path) -> None:
    captured: list[float] = []
    audio_path = tmp_path / "target.wav"
    audio_path.write_bytes(b"wav")
    monkeypatch.setattr(export_worker, "probe_duration_seconds", lambda _path: float("inf"))
    monkeypatch.setattr(export_worker, "ffmpeg_make_silence", lambda duration, _path: captured.append(duration))

    assert export_worker._probe_duration_seconds(audio_path) == 0.0

    export_worker._make_silence(float("nan"), audio_path)

    assert captured == [0.0]


def test_export_progress_percent_rejects_non_finite_values() -> None:
    assert export_worker._percent_value(float("nan")) == 0
    assert export_worker._percent_value(float("inf")) == 0
    assert export_worker._percent_value(120.2) == 100


def test_export_json_number_rejects_overflow_values() -> None:
    assert export_worker._json_number("1e9999", default=None) is None


def test_export_worker_count_ignores_overflow_env(monkeypatch) -> None:
    monkeypatch.setenv("AI_PLAYER_EXPORT_WORKERS", "1e9999")

    assert export_worker._export_worker_count() >= 1


def test_transcript_export_sanitizes_entry_timing_and_text(monkeypatch, tmp_path) -> None:
    config = AppConfig(tts_provider="none", segment_seconds=float("nan"), transcript_cleanup_mode="off")
    worker = export_worker.DubbingExportWorker("video.mp4", str(tmp_path / "out.wav"), "audio", config)
    worker._temp_dir = tmp_path
    worker._translator = SimpleNamespace(translate_many=lambda texts, _language: texts)
    worker._transcript_cleaner = SimpleNamespace(clean_many=lambda texts, _language: texts)
    silences: list[float] = []
    worker._make_silence = lambda duration, output_path: silences.append(duration) or Path(output_path).write_bytes(
        b"silence"
    )
    monkeypatch.setattr(
        export_worker,
        "_load_transcript_entries",
        lambda _path, segment_seconds, _language: [
            SimpleNamespace(start=float("inf"), end=float("nan"), text=b" hello   world ")
        ],
    )
    monkeypatch.setattr(export_worker, "_export_worker_count", lambda: 1)

    cues = worker._build_transcript_cues()

    assert silences == [5.0]
    assert cues == [
        export_worker.ExportCue(
            0.0,
            "hello world",
            "hello world",
            tmp_path / "transcript-cue-00000.wav",
            duration_seconds=5.0,
        )
    ]

def test_source_export_skips_reference_extract_when_unused(monkeypatch, tmp_path) -> None:
    config = AppConfig(
        dubbing_auto_match_audio=False,
        dubbing_auto_voice_gender=False,
        tts_provider="vieneu",
    )
    worker = export_worker.DubbingExportWorker("video.mp4", str(tmp_path / "out.wav"), "audio", config)
    worker._temp_dir = tmp_path
    worker._translator = SimpleNamespace(translate_many=lambda texts, _language: [f"{text}-vi" for text in texts])
    worker._transcript_cleaner = SimpleNamespace(clean=lambda text, _language: text)
    worker._transcribe_with_fallback = lambda _source_audio: (
        [SimpleNamespace(text="first", start=0.0, end=1.0)],
        SimpleNamespace(language="en"),
    )
    source_audio = tmp_path / "source.wav"
    seen_references: list[Path] = []

    def fail_extract(*_args, **_kwargs) -> None:
        raise AssertionError("reference audio should not be extracted")

    def fake_build(index, original, translated, start_seconds, duration_seconds, reference_path, voice, tts_suffix):
        seen_references.append(reference_path)
        return export_worker.ExportCue(
            start_seconds=start_seconds,
            original=original,
            translated=translated,
            audio_path=reference_path,
            duration_seconds=duration_seconds,
        )

    monkeypatch.setattr(export_worker, "extract_audio_range", fail_extract)
    monkeypatch.setattr(export_worker, "_export_worker_count", lambda: 1)
    worker._build_source_export_cue = fake_build

    cues = worker._build_cues(source_audio)

    assert seen_references == [source_audio]
    assert [cue.original for cue in cues] == ["first"]


def test_export_aligned_audio_mixes_cues_at_source_starts(tmp_path) -> None:
    config = AppConfig(dubbing_overlap_policy="strict_start")
    worker = export_worker.DubbingExportWorker("video.mp4", str(tmp_path / "out.wav"), "audio", config)
    worker._temp_dir = tmp_path
    captured: dict[str, list[object]] = {}
    source_a = tmp_path / "a.wav"
    source_b = tmp_path / "b.wav"
    source_a.write_bytes(b"a")
    source_b.write_bytes(b"b")

    def fake_to_wav(_input_path: Path, output_path: Path) -> None:
        output_path.write_bytes(b"wav")

    worker._to_wav = fake_to_wav
    worker._run_ffmpeg = lambda args, **_kwargs: captured.setdefault("args", args)

    worker._build_aligned_audio(
        [
            export_worker.ExportCue(0.0, "first", "mot", source_a, duration_seconds=3.0),
            export_worker.ExportCue(1.0, "second", "hai", source_b, duration_seconds=1.0),
        ],
        tmp_path / "mixed.wav",
    )

    args = captured["args"]
    filter_complex = args[args.index("-filter_complex") + 1]
    assert "adelay=0:all=1" in filter_complex
    assert "adelay=1000:all=1" in filter_complex
    assert "amix=inputs=2" in filter_complex
    assert "-f" not in args


def test_export_aligned_audio_uses_smart_overlap_policy(tmp_path) -> None:
    config = AppConfig(dubbing_overlap_policy="smart")
    worker = export_worker.DubbingExportWorker("video.mp4", str(tmp_path / "out.wav"), "audio", config)
    worker._temp_dir = tmp_path
    captured: dict[str, list[object]] = {}
    source_a = tmp_path / "a.wav"
    source_b = tmp_path / "b.wav"
    source_a.write_bytes(b"a")
    source_b.write_bytes(b"b")

    worker._to_wav = lambda _input_path, output_path: Path(output_path).write_bytes(b"wav")
    worker._run_ffmpeg = lambda args, **_kwargs: captured.setdefault("args", args)

    worker._build_aligned_audio(
        [
            export_worker.ExportCue(0.0, "first", "mot", source_a, duration_seconds=3.0),
            export_worker.ExportCue(1.0, "second", "hai", source_b, duration_seconds=1.0),
        ],
        tmp_path / "mixed.wav",
    )

    args = captured["args"]
    filter_complex = args[args.index("-filter_complex") + 1]
    assert "adelay=0:all=1" in filter_complex
    assert "adelay=1750:all=1" in filter_complex

def test_dubbing_worker_queues_audio_at_source_start_even_when_previous_audio_extends(qapp, tmp_path) -> None:
    config = AppConfig(audio_source="original", dubbing_overlap_policy="strict_start")
    worker = DubbingWorker("video.mp4", lambda: 0, lambda: False, config)
    worker._scheduled_audio_until = 10.0
    audio_path = tmp_path / "target.wav"

    worker._queue_pending_audio(2.0, 1.0, audio_path, "hello", "xin chao")

    assert worker._pending_audio == [(2.0, 2.0, audio_path, "hello", "xin chao")]
    assert worker._scheduled_audio_until == 10.0


def test_dubbing_worker_smart_policy_pushes_large_overlap_only_briefly(qapp, tmp_path) -> None:
    config = AppConfig(audio_source="original", dubbing_overlap_policy="smart")
    worker = DubbingWorker("video.mp4", lambda: 0, lambda: False, config)
    worker._scheduled_audio_until = 10.0
    audio_path = tmp_path / "target.wav"

    worker._queue_pending_audio(2.0, 1.0, audio_path, "hello", "xin chao")

    assert worker._pending_audio == [(2.75, 2.0, audio_path, "hello", "xin chao")]
    assert worker._scheduled_audio_until == 10.0


def test_dubbing_worker_avoid_overlap_policy_queues_after_previous_audio(qapp, tmp_path) -> None:
    config = AppConfig(audio_source="original", dubbing_overlap_policy="avoid_overlap")
    worker = DubbingWorker("video.mp4", lambda: 0, lambda: False, config)
    worker._scheduled_audio_until = 10.0
    audio_path = tmp_path / "target.wav"

    worker._queue_pending_audio(2.0, 1.0, audio_path, "hello", "xin chao")

    assert worker._pending_audio == [(10.0, 2.0, audio_path, "hello", "xin chao")]
    assert worker._scheduled_audio_until == 11.0


def test_dubbing_worker_keeps_document_audio_sequential(qapp, tmp_path) -> None:
    config = AppConfig(audio_source="document_editor", dubbing_overlap_policy="strict_start")
    worker = DubbingWorker("document.txt", lambda: 0, lambda: False, config)
    worker._scheduled_audio_until = 10.0
    audio_path = tmp_path / "target.wav"

    worker._queue_pending_audio(2.0, 1.0, audio_path, "hello", "xin chao")

    assert worker._pending_audio == [(10.0, 2.0, audio_path, "hello", "xin chao")]
    assert worker._scheduled_audio_until == 11.0


def test_dubbing_worker_sanitizes_non_finite_pending_audio_times(qapp, tmp_path) -> None:
    config = AppConfig(audio_source="original", dubbing_overlap_policy="strict_start")
    worker = DubbingWorker("video.mp4", lambda: 0, lambda: False, config)
    audio_path = tmp_path / "target.wav"

    worker._queue_pending_audio(float("inf"), float("nan"), audio_path, "hello", "xin chao")

    assert worker._pending_audio == [(0.0, 0.0, audio_path, "hello", "xin chao")]
    assert worker._scheduled_audio_until == 0.05
    assert _segment_start_key(float("inf")) == 0


def test_dubbing_worker_sanitizes_invalid_speed_and_volume(monkeypatch, qapp, tmp_path) -> None:
    config = AppConfig(
        audio_source="original",
        dubbing_overlap_policy="strict_start",
        performance_preset="low_latency",
        dubbing_auto_match_audio=False,
        dubbing_speed_percent=float("nan"),
        dubbing_voice_volume=float("inf"),
    )
    worker = DubbingWorker("video.mp4", lambda: 0, lambda: False, config)
    audio_path = tmp_path / "target.wav"
    audio_path.write_bytes(b"wav")
    commands: list[list[str]] = []

    class FakeProcess:
        def poll(self):
            return 0

    monkeypatch.setattr("ai_player.workers.dubbing_worker.ffplay_executable", lambda: "ffplay")
    monkeypatch.setattr(
        "ai_player.workers.dubbing_worker.subprocess.Popen",
        lambda command, **_kwargs: commands.append(command) or FakeProcess(),
    )

    assert worker._skip_tts_postprocess()
    worker._queue_pending_audio(0.0, 1.0, audio_path, "hello", "xin chao")
    assert worker._launch_due_audio(0.0)

    assert commands[0][commands[0].index("-volume") + 1] == "100"


def test_dubbing_worker_sanitizes_transcript_entry_timing(qapp, tmp_path) -> None:
    config = AppConfig(audio_source="transcript", tts_provider="none", segment_seconds=float("nan"))
    worker = DubbingWorker("video.mp4", lambda: 0, lambda: False, config)
    worker._temp_dir = tmp_path
    worker._translator = SimpleNamespace(translate=lambda text, _language: f"vi {text}")

    worker._prepare_transcript_entry(
        transcript_source.TranscriptEntry(float("inf"), float("nan"), "hello"),
        0,
    )

    assert worker._scheduled_audio_until == 5.0


def test_dubbing_worker_normalizes_asr_bytes_text_and_language(qapp, tmp_path) -> None:
    config = AppConfig(tts_provider="none", transcript_cleanup_mode="off")
    worker = DubbingWorker("video.mp4", lambda: 0, lambda: False, config)
    worker._temp_dir = tmp_path
    worker._model = object()
    translated_calls: list[tuple[str, str | None]] = []
    ready_segments: list[tuple[str, str]] = []
    worker.segment_ready.connect(lambda original, translated: ready_segments.append((original, translated)))
    worker._extract_audio = lambda *_args, **_kwargs: None
    worker._translator = SimpleNamespace(
        translate=lambda text, language: translated_calls.append((text, language)) or "xin chao"
    )
    worker._transcribe_with_fallback = lambda _wav_path: (
        [SimpleNamespace(text=b" hello   world ", start=0.25, end=0.75)],
        SimpleNamespace(language=b"EN"),
    )

    worker._process_segment(1.0)

    assert translated_calls == [("hello world", "en")]
    assert ready_segments == [("hello world", "xin chao")]


def test_document_review_export_cue_uses_initialized_tts_lock(tmp_path) -> None:
    config = AppConfig(tts_provider="vieneu")
    worker = export_worker.DocumentReviewExportWorker("document.srt", [], str(tmp_path / "out.mp4"), config)
    worker._temp_dir = tmp_path
    worker._tts_provider = SimpleNamespace(synthesize=lambda _text, path, voice=None: Path(path).write_bytes(b"tts"))
    worker._to_wav = lambda _input_path, output_path: Path(output_path).write_bytes(b"wav")
    worker._trim_leading_silence = lambda audio_path: audio_path

    cue = worker._build_document_export_cue(
        0,
        export_worker.TranscriptCue(0.0, 1.0, "hello"),
        "hello",
        "xin chao",
        "wav",
    )

    assert cue.audio_path.exists()


def test_document_export_sanitizes_invalid_cue_timing(tmp_path) -> None:
    config = AppConfig(tts_provider="none")
    worker = export_worker.DocumentReviewExportWorker("document.srt", [], str(tmp_path / "out.mp4"), config)
    worker._temp_dir = tmp_path
    silences: list[float] = []
    worker._make_silence = lambda duration, output_path: silences.append(duration) or Path(output_path).write_bytes(
        b"silence"
    )

    cue = worker._build_document_export_cue(
        0,
        export_worker.TranscriptCue(float("inf"), float("nan"), "hello"),
        "hello",
        "xin chao",
        "wav",
    )

    assert silences == [0.25]
    assert cue.start_seconds == 0.0
    assert cue.duration_seconds == 0.25

def test_dubbing_worker_advances_async_segments_in_timeline_order(qapp) -> None:
    config = AppConfig(segment_seconds=4, dubbing_lookahead_segments=2)
    worker = DubbingWorker("video.mp4", lambda: 0, lambda: False, config)
    worker._covered_until = 0.0

    worker._completed_segment_starts.add(_segment_start_key(4.0))
    worker._advance_covered_until()
    assert worker._covered_until == 0.0

    worker._completed_segment_starts.add(_segment_start_key(0.0))
    worker._advance_covered_until()
    assert worker._covered_until == 8.0


def test_dubbing_worker_prebuffer_does_not_wait_for_full_target_ready_ahead(qapp) -> None:
    config = AppConfig(
        segment_seconds=12,
        dubbing_prebuffer_segments=2,
        dubbing_min_ready_ahead_seconds=40,
    )
    worker = DubbingWorker("video.mp4", lambda: 0, lambda: False, config)
    resumed: list[str] = []
    worker._launch_due_audio = lambda _current: False
    worker._request_resume = resumed.append
    worker._covered_until = 24.0
    worker._prepared_segments = 2
    worker._buffering = True

    worker._resume_if_buffer_ready(0.0)

    assert not worker._buffering
    assert resumed


def test_dubbing_worker_prebuffer_still_requires_prebuffer_ready_ahead(qapp) -> None:
    config = AppConfig(
        segment_seconds=12,
        dubbing_prebuffer_segments=2,
        dubbing_min_ready_ahead_seconds=40,
    )
    worker = DubbingWorker("video.mp4", lambda: 0, lambda: False, config)
    worker._launch_due_audio = lambda _current: False
    worker._request_resume = lambda _message: None
    worker._covered_until = 12.0
    worker._prepared_segments = 2
    worker._buffering = True

    worker._resume_if_buffer_ready(0.0)

    assert worker._buffering


def test_dubbing_worker_skips_local_cleanup_for_realtime_sources(qapp, tmp_path) -> None:
    config = AppConfig(
        audio_source="original",
        transcript_cleanup_mode="light",
        transcript_cleanup_provider="local",
        transcript_cleanup_model=str(tmp_path),
    )
    worker = DubbingWorker("video.mp4", lambda: 0, lambda: False, config)
    statuses: list[str] = []
    worker.status_changed.connect(statuses.append)
    worker._transcript_cleaner.clean = lambda *_args, **_kwargs: pytest.fail("local cleanup should be skipped")

    assert worker._clean_transcript_text("  hello   world  ", "en") == "hello world"
    assert statuses


def test_dubbing_worker_keeps_nonlocal_cleanup_for_realtime_sources(qapp) -> None:
    config = AppConfig(
        audio_source="original",
        transcript_cleanup_mode="light",
        transcript_cleanup_provider="ollama",
    )
    worker = DubbingWorker("video.mp4", lambda: 0, lambda: False, config)
    worker._transcript_cleaner.clean = lambda text, _language=None: f"cleaned {text.strip()}"

    assert worker._clean_transcript_text(" hello ", "en") == "cleaned hello"
