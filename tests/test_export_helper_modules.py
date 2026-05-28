from __future__ import annotations

import subprocess
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace

import pytest

from ai_player.core.config import AppConfig
from ai_player.workers import (
    aligned_audio,
    document_export_voice,
    export_media,
    export_worker,
    source_export_voice,
    staged_audio_stems,
    staged_export_utils,
    staged_target_voice,
    transcript_export_voice,
)


def test_media_mux_video_args_apply_export_range(tmp_path) -> None:
    quality = export_worker._video_quality_settings("balanced")
    args = export_media.mux_video_args(
        video_path="video.mp4",
        dubbed_audio=tmp_path / "dubbed.wav",
        target_path=tmp_path / "out.mp4",
        export_range=export_worker.ExportRange(10.0, 15.5),
        quality=quality,
    )

    assert args[:4] == ["-ss", "10.000", "-i", "video.mp4"]
    assert args[args.index("-t") + 1] == "5.500"
    assert args[-1] == str(tmp_path / "out.mp4")


def test_extract_source_audio_args_apply_range_and_mono_asr_format(tmp_path) -> None:
    args = export_media.extract_source_audio_args(
        "video.mp4",
        tmp_path / "source.wav",
        export_worker.ExportRange(1.25, 3.0),
    )

    assert args[:4] == ["-ss", "1.250", "-i", "video.mp4"]
    assert args[args.index("-t") + 1] == "1.750"
    assert "-vn" in args
    assert args[args.index("-ac") + 1] == "1"
    assert args[args.index("-ar") + 1] == "16000"
    assert args[-1] == str(tmp_path / "source.wav")


def test_full_quality_audio_args_preserve_stereo_pcm(tmp_path) -> None:
    args = export_media.full_quality_audio_args(
        "video.mp4",
        tmp_path / "source-full.wav",
        export_worker.ExportRange(0.0, None),
    )

    assert args[:2] == ["-i", "video.mp4"]
    assert "-t" not in args
    assert args[args.index("-map") + 1] == "0:a:0"
    assert "-sn" in args
    assert "-dn" in args
    assert args[args.index("-ac") + 1] == "2"
    assert args[args.index("-ar") + 1] == "48000"
    assert args[-1] == str(tmp_path / "source-full.wav")


def test_document_video_concat_extends_last_page_to_audio_duration(tmp_path) -> None:
    pages = [
        SimpleNamespace(duration_seconds=1.0),
        SimpleNamespace(duration_seconds=2.0),
    ]
    text = export_media.document_video_concat_lines(
        pages,
        [tmp_path / "one.png", tmp_path / "two.png"],
        audio_duration_seconds=5.5,
    )

    assert "duration 1.000" in text
    assert "duration 4.500" in text
    assert text.rstrip().endswith("two.png'")


def test_fast_background_stem_args_use_center_cancel_filter(tmp_path) -> None:
    source = tmp_path / "source.wav"
    output = tmp_path / "background.wav"

    args = export_media.fast_background_stem_args(source, output)

    assert args[:2] == ["-i", source]
    assert "pan=stereo|c0=0.70*c0-0.55*c1|c1=0.70*c1-0.55*c0" in args[args.index("-af") + 1]
    assert "volume=1.4" in args[args.index("-af") + 1]
    assert args[args.index("-ar") + 1] == 48000
    assert args[args.index("-ac") + 1] == 2
    assert args[-1] == output


def test_fast_voice_stem_args_use_center_extract_filter(tmp_path) -> None:
    source = tmp_path / "source.wav"
    output = tmp_path / "voice.wav"

    args = export_media.fast_voice_stem_args(source, output)

    assert args[:2] == ["-i", source]
    assert "pan=stereo|c0=0.5*c0+0.5*c1|c1=0.5*c0+0.5*c1" in args[args.index("-af") + 1]
    assert "alimiter=limit=0.95" in args[args.index("-af") + 1]
    assert args[args.index("-ar") + 1] == 48000
    assert args[args.index("-ac") + 1] == 2
    assert args[-1] == output


def test_staged_export_paths_define_manifest_artifacts(tmp_path) -> None:
    paths = staged_export_utils.StagedExportPaths.from_output_dir(tmp_path)

    assert paths.managed_dirs == (tmp_path / "audio", tmp_path / "subtitles", tmp_path / "tts", tmp_path / ".work")
    assert paths.managed_files == (
        tmp_path / "audio" / "source_full.wav",
        tmp_path / "subtitles" / "source.srt",
        tmp_path / "subtitles" / "source.words.json",
        tmp_path / "subtitles" / "target.srt",
        tmp_path / "audio" / "source_voice.wav",
        tmp_path / "audio" / "background_no_voice.wav",
        tmp_path / "audio" / "target_voice.wav",
        tmp_path / "audio" / "final_mix.wav",
        tmp_path / "dubbed_video.mp4",
        tmp_path / "manifest.json",
    )
    assert paths.artifacts() == {
        "source_full_wav": "audio/source_full.wav",
        "source_srt": "subtitles/source.srt",
        "source_words_json": "subtitles/source.words.json",
        "target_srt": "subtitles/target.srt",
        "source_voice_wav": "audio/source_voice.wav",
        "background_no_voice_wav": "audio/background_no_voice.wav",
        "target_voice_wav": "audio/target_voice.wav",
        "final_mix_wav": "audio/final_mix.wav",
        "dubbed_video_mp4": "dubbed_video.mp4",
    }


def test_staged_source_stems_copy_without_temp_dir_when_filter_disabled(tmp_path) -> None:
    source_audio = tmp_path / "source.wav"
    source_audio.write_bytes(b"source")
    background = tmp_path / "background.wav"
    voice = tmp_path / "voice.wav"

    backend = staged_audio_stems.create_source_audio_stems(
        config=AppConfig(original_audio_voice_filter=False),
        source_audio=source_audio,
        background_path=background,
        voice_path=voice,
        temp_dir=None,
        run_process=lambda *_args, **_kwargs: pytest.fail("disabled filter should not run Demucs"),
        run_ffmpeg=lambda _args: pytest.fail("disabled filter should not run FFmpeg"),
        to_wav=lambda *_args: pytest.fail("disabled filter should not convert stems"),
        cancel_callback=lambda: False,
        demucs_available=lambda: False,
        demucs_command=lambda: ["demucs"],
        temp_missing_message="missing temp",
    )

    assert backend == "disabled"
    assert background.read_bytes() == b"source"
    assert voice.read_bytes() == b"source"


def test_staged_source_stems_fast_mode_runs_filter_args(tmp_path) -> None:
    source_audio = tmp_path / "source.wav"
    source_audio.write_bytes(b"source")
    commands: list[list[object]] = []

    backend = staged_audio_stems.create_source_audio_stems(
        config=AppConfig(original_audio_voice_filter=True, original_audio_voice_filter_mode="fast"),
        source_audio=source_audio,
        background_path=tmp_path / "background.wav",
        voice_path=tmp_path / "voice.wav",
        temp_dir=None,
        run_process=lambda *_args, **_kwargs: pytest.fail("fast filter should not run Demucs"),
        run_ffmpeg=lambda args: commands.append(args),
        to_wav=lambda *_args: pytest.fail("fast filter should not convert Demucs stems"),
        cancel_callback=lambda: False,
        demucs_available=lambda: False,
        demucs_command=lambda: ["demucs"],
        temp_missing_message="missing temp",
    )

    assert backend == "fast"
    assert len(commands) == 2
    assert "0.70*c0-0.55*c1" in commands[0][commands[0].index("-af") + 1]
    assert "0.5*c0+0.5*c1" in commands[1][commands[1].index("-af") + 1]


def test_staged_demucs_stems_capture_process_output(tmp_path) -> None:
    source_audio = tmp_path / "source.wav"
    source_audio.write_bytes(b"source")
    process_kwargs: dict[str, object] = {}

    def fake_process(command, **kwargs):
        process_kwargs.update(kwargs)
        stem_root = tmp_path / ".work" / "demucs" / "htdemucs" / source_audio.stem
        stem_root.mkdir(parents=True)
        (stem_root / "no_vocals.wav").write_bytes(b"background")
        (stem_root / "vocals.wav").write_bytes(b"voice")
        return SimpleNamespace(returncode=0)

    backend = staged_audio_stems.create_source_audio_stems(
        config=AppConfig(original_audio_voice_filter=True, original_audio_voice_filter_mode="ai"),
        source_audio=source_audio,
        background_path=tmp_path / "background.wav",
        voice_path=tmp_path / "voice.wav",
        temp_dir=tmp_path / ".work",
        run_process=fake_process,
        run_ffmpeg=lambda _args: pytest.fail("AI filter should not use fast FFmpeg stems"),
        to_wav=lambda input_path, output_path: Path(output_path).write_bytes(Path(input_path).read_bytes()),
        cancel_callback=lambda: False,
        demucs_available=lambda: True,
        demucs_command=lambda: ["demucs"],
        temp_missing_message="missing temp",
    )

    assert backend == "ai"
    assert process_kwargs["stdout"] == subprocess.PIPE
    assert process_kwargs["stderr"] == subprocess.PIPE
    assert process_kwargs["text"] is True
    assert process_kwargs["encoding"] == "utf-8"
    assert process_kwargs["errors"] == "replace"


def test_staged_target_voice_helper_replaces_non_speech_with_silence(tmp_path) -> None:
    final_paths: list[Path] = []

    audio_path = staged_target_voice.build_target_voice_cue(
        index=1,
        target_cue=export_worker.TranscriptCue(2.0, 2.1, "..."),
        reference_path=tmp_path / "reference.wav",
        voice="voice",
        tts_suffix="mp3",
        config=AppConfig(tts_provider="edge"),
        tts_dir=tmp_path,
        tts_provider=SimpleNamespace(
            synthesize=lambda *_args, **_kwargs: pytest.fail("non-speech should not be synthesized")
        ),
        tts_lock=nullcontext(),
        make_silence=lambda _duration, output_path: final_paths.append(output_path)
        or Path(output_path).write_bytes(b"silence"),
        trim_leading_silence=lambda path: path,
        to_wav=lambda *_args: pytest.fail("non-speech should not be matched"),
        match_to_reference=lambda **_kwargs: pytest.fail("non-speech should not be matched"),
        cancel_callback=lambda: False,
    )

    assert audio_path == tmp_path / "0002-aligned.wav"
    assert final_paths == [audio_path]
    assert audio_path.read_bytes() == b"silence"


def test_staged_target_voice_cues_extract_reference_and_select_voice(tmp_path) -> None:
    references: list[tuple[float, float, Path]] = []
    built: list[tuple[int, str, str, str]] = []
    progress: list[tuple[int, int, int, int]] = []
    emitted: list[tuple[str, str]] = []

    def fake_build(index, target_cue, reference_path, voice, suffix):
        built.append((index, target_cue.text, reference_path.name, f"{voice}.{suffix}"))
        audio_path = tmp_path / f"target-{index}.wav"
        audio_path.write_bytes(b"voice")
        return audio_path

    cues = staged_target_voice.build_target_voice_cues(
        config=AppConfig(tts_provider="edge", dubbing_auto_voice_gender=True),
        source_voice=tmp_path / "source-voice.wav",
        source_cues=[export_worker.TranscriptCue(1.0, 2.0, "hello")],
        target_cues=[export_worker.TranscriptCue(1.0, 2.5, "xin chao")],
        temp_dir=tmp_path,
        voice_selector=SimpleNamespace(select_voice=lambda *_args, **_kwargs: SimpleNamespace(voice="selected")),
        extract_audio_range=lambda _source, start, duration, path, **_kwargs: references.append(
            (start, duration, path)
        ),
        build_target_voice_cue=fake_build,
        probe_duration=lambda _path: 0.0,
        should_stop=lambda: False,
        set_range_progress=lambda *args: progress.append(args),
        emit_progress=lambda key, **kwargs: emitted.append((key, kwargs["time"])),
        cancel_callback=lambda: False,
    )

    assert references == [(1.0, 1.5, tmp_path / "reference-00000.wav")]
    assert built == [(0, "xin chao", "reference-00000.wav", "selected.mp3")]
    assert progress == [(62, 78, 0, 1)]
    assert emitted == [("export_progress_creating_voice_at", "00:00:01")]
    assert cues == [
        export_worker.ExportCue(
            1.0,
            "hello",
            "xin chao",
            tmp_path / "target-0.wav",
            duration_seconds=1.5,
        )
    ]


def test_source_export_voice_helper_reuses_reference_when_tts_disabled(tmp_path) -> None:
    reference_path = tmp_path / "reference.wav"
    reference_path.write_bytes(b"reference")

    cue = source_export_voice.build_source_export_cue(
        index=0,
        original="hello",
        translated="xin chao",
        start_seconds=1.0,
        duration_seconds=2.0,
        reference_path=reference_path,
        voice="voice",
        tts_suffix="mp3",
        temp_dir=tmp_path,
        config=AppConfig(tts_provider="none"),
        tts_provider=SimpleNamespace(
            synthesize=lambda *_args, **_kwargs: pytest.fail("disabled TTS should not synthesize")
        ),
        tts_lock=nullcontext(),
        make_silence=lambda *_args: pytest.fail("disabled TTS should not create silence"),
        trim_leading_silence=lambda path: path,
        match_to_reference=lambda **_kwargs: pytest.fail("disabled TTS should not match audio"),
        cancel_callback=lambda: False,
    )

    assert cue == export_worker.ExportCue(
        1.0,
        "hello",
        "xin chao",
        reference_path,
        duration_seconds=2.0,
    )


def test_source_export_voice_helper_synthesizes_and_matches_trimmed_audio(tmp_path, monkeypatch) -> None:
    final_audio = tmp_path / "final.wav"
    final_audio.write_bytes(b"final")
    matched_calls: list[dict[str, object]] = []
    synthesized: list[tuple[str, Path, str]] = []
    trimmed: list[Path] = []
    monkeypatch.setattr(source_export_voice, "_probe_duration_seconds", lambda _path: 1.25)

    def fake_match_to_reference(**kwargs):
        matched_calls.append(kwargs)
        return final_audio

    cue = source_export_voice.build_source_export_cue(
        index=3,
        original="hello",
        translated="xin chao",
        start_seconds=4.0,
        duration_seconds=2.0,
        reference_path=tmp_path / "reference.wav",
        voice="voice-a",
        tts_suffix="mp3",
        temp_dir=tmp_path,
        config=AppConfig(tts_provider="edge"),
        tts_provider=SimpleNamespace(
            synthesize=lambda text, path, voice=None: synthesized.append((text, path, voice))
            or Path(path).write_bytes(b"tts")
        ),
        tts_lock=nullcontext(),
        make_silence=lambda *_args: pytest.fail("speech target should not create silence"),
        trim_leading_silence=lambda path: trimmed.append(path) or path.with_name("trimmed.mp3"),
        match_to_reference=fake_match_to_reference,
        cancel_callback=lambda: False,
    )

    assert synthesized == [("xin chao", tmp_path / "cue-00003.mp3", "voice-a")]
    assert trimmed == [tmp_path / "cue-00003.mp3"]
    assert matched_calls[0]["tts_path"] == tmp_path / "trimmed.mp3"
    assert matched_calls[0]["output_path"] == tmp_path / "cue-00003-matched.wav"
    assert cue.audio_path == final_audio
    assert cue.duration_seconds == 1.25


def test_prepare_source_export_items_extracts_reference_and_selects_voice(tmp_path) -> None:
    item = SimpleNamespace(index=2, start_seconds=3.0, duration_seconds=1.5)
    extracted: list[tuple[float, float, Path]] = []
    selected: list[Path] = []

    prepared = source_export_voice.prepare_source_export_items(
        items=[item],
        source_audio=tmp_path / "source.wav",
        temp_dir=tmp_path,
        config=AppConfig(dubbing_auto_voice_gender=True, tts_provider="edge"),
        voice_selector=SimpleNamespace(
            select_voice=lambda reference_path, **_kwargs: selected.append(reference_path)
            or SimpleNamespace(voice="selected")
        ),
        extract_audio_range=lambda _source, start, duration, path, **_kwargs: extracted.append(
            (start, duration, path)
        ),
        should_stop=lambda: False,
        cancel_callback=lambda: False,
    )

    reference_path = tmp_path / "cue-00002-ref.wav"
    assert extracted == [(3.0, 1.5, reference_path)]
    assert selected == [reference_path]
    assert prepared == [source_export_voice.PreparedSourceExportItem(item, reference_path, "selected")]


def test_prepare_source_export_items_reuses_source_when_reference_unused(tmp_path) -> None:
    source_audio = tmp_path / "source.wav"
    item = SimpleNamespace(index=0, start_seconds=0.0, duration_seconds=1.0)
    config = AppConfig(
        dubbing_auto_match_audio=False,
        dubbing_auto_voice_gender=False,
        tts_provider="vieneu",
    )

    prepared = source_export_voice.prepare_source_export_items(
        items=[item],
        source_audio=source_audio,
        temp_dir=tmp_path,
        config=config,
        voice_selector=SimpleNamespace(select_voice=lambda *_args, **_kwargs: pytest.fail("voice selector unused")),
        extract_audio_range=lambda *_args, **_kwargs: pytest.fail("reference extraction unused"),
        should_stop=lambda: False,
        cancel_callback=lambda: False,
    )

    assert prepared == [source_export_voice.PreparedSourceExportItem(item, source_audio, config.tts_voice)]


def test_translate_export_items_emits_ready_segments() -> None:
    emitted: list[tuple[str, str]] = []
    items = [
        SimpleNamespace(original="one"),
        SimpleNamespace(original="two"),
        SimpleNamespace(original="three"),
    ]
    translator = SimpleNamespace(translate_many=lambda _texts, _language: ["mot", ""])

    translated = source_export_voice.translate_export_items(
        items=items,
        translator=translator,
        source_language="en",
        emit_segment=lambda original, target: emitted.append((original, target)),
    )

    assert translated == ["mot", "two", "three"]
    assert emitted == [("one", "mot"), ("two", "two"), ("three", "three")]


def test_build_prepared_source_export_cues_reports_progress_and_sorts(tmp_path) -> None:
    progress: list[tuple[int, int, int, int]] = []
    emitted: list[tuple[str, str]] = []
    prepared_items = [
        source_export_voice.PreparedSourceExportItem(
            SimpleNamespace(index=1, original="second", start_seconds=2.0, duration_seconds=1.0),
            tmp_path / "second-ref.wav",
            "voice-b",
        ),
        source_export_voice.PreparedSourceExportItem(
            SimpleNamespace(index=0, original="first", start_seconds=0.0, duration_seconds=1.0),
            tmp_path / "first-ref.wav",
            "voice-a",
        ),
    ]

    def fake_build(index, original, translated, start_seconds, duration_seconds, reference_path, voice, suffix):
        return export_worker.ExportCue(
            start_seconds,
            original,
            f"{translated}:{voice}:{suffix}",
            reference_path,
            duration_seconds=duration_seconds,
        )

    cues = source_export_voice.build_prepared_source_export_cues(
        prepared_items=prepared_items,
        translated_items=["hai", "mot"],
        tts_suffix="mp3",
        max_workers=1,
        build_source_export_cue=fake_build,
        should_stop=lambda: False,
        set_range_progress=lambda *args: progress.append(args),
        emit_progress=lambda key, **kwargs: emitted.append((key, kwargs["time"])),
    )

    assert progress == [(35, 74, 0, 2), (35, 74, 1, 2)]
    assert emitted == [
        ("export_progress_creating_voice_at", "00:00:02"),
        ("export_progress_creating_voice_at", "00:00:00"),
    ]
    assert [cue.original for cue in cues] == ["first", "second"]
    assert [cue.translated for cue in cues] == ["mot:voice-a:mp3", "hai:voice-b:mp3"]


def test_transcript_export_voice_helper_creates_silence_for_disabled_tts(tmp_path) -> None:
    silences: list[tuple[float, Path]] = []

    cue = transcript_export_voice.build_transcript_export_cue(
        index=2,
        original="hello",
        translated="xin chao",
        entry_start=4.0,
        entry_end=6.0,
        tts_suffix="mp3",
        temp_dir=tmp_path,
        export_range=export_worker.ExportRange(3.0, 8.0),
        config=AppConfig(tts_provider="none"),
        tts_provider=SimpleNamespace(
            synthesize=lambda *_args, **_kwargs: pytest.fail("disabled TTS should not synthesize")
        ),
        tts_lock=nullcontext(),
        make_silence=lambda duration, output_path: silences.append((duration, output_path))
        or Path(output_path).write_bytes(b"silence"),
        trim_leading_silence=lambda path: path,
        to_wav=lambda *_args: pytest.fail("disabled TTS should not convert audio"),
    )

    assert silences == [(2.0, tmp_path / "transcript-cue-00002.wav")]
    assert cue == export_worker.ExportCue(
        1.0,
        "hello",
        "xin chao",
        tmp_path / "transcript-cue-00002.wav",
        duration_seconds=2.0,
    )


def test_build_prepared_transcript_export_cues_reports_progress_and_sorts(tmp_path) -> None:
    progress: list[tuple[int, int, int, int]] = []
    emitted: list[tuple[str, str]] = []
    items = [
        SimpleNamespace(index=1, entry=object(), original="second", start_seconds=2.0, end_seconds=3.0),
        SimpleNamespace(index=0, entry=object(), original="first", start_seconds=0.0, end_seconds=1.0),
    ]

    def fake_build(index, _entry, original, translated, start_seconds, entry_end, suffix):
        return export_worker.ExportCue(
            start_seconds,
            original,
            f"{translated}:{suffix}",
            tmp_path / f"{index}.wav",
            duration_seconds=entry_end - start_seconds,
        )

    cues = transcript_export_voice.build_prepared_transcript_export_cues(
        items=items,
        translated_items=["hai", "mot"],
        tts_suffix="wav",
        max_workers=1,
        build_transcript_export_cue=fake_build,
        set_range_progress=lambda *args: progress.append(args),
        emit_progress=lambda key, **kwargs: emitted.append((key, kwargs["time"])),
    )

    assert progress == [(18, 74, 0, 2), (18, 74, 1, 2)]
    assert emitted == [
        ("export_progress_creating_voice_at", "00:00:02"),
        ("export_progress_creating_voice_at", "00:00:00"),
    ]
    assert [cue.original for cue in cues] == ["first", "second"]
    assert [cue.translated for cue in cues] == ["mot:wav", "hai:wav"]


def test_aligned_timeline_inputs_prepares_audio_in_source_order(tmp_path) -> None:
    source_a = tmp_path / "a.wav"
    source_b = tmp_path / "b.wav"
    prepared: list[tuple[int, str]] = []
    progress: list[tuple[int, int, int, int]] = []

    inputs = aligned_audio.aligned_timeline_inputs(
        [
            export_worker.ExportCue(1.0, "second", "hai", source_b, duration_seconds=1.0),
            export_worker.ExportCue(0.0, "first", "mot", source_a, duration_seconds=3.0),
        ],
        progress_start=76,
        progress_end=88,
        overlap_policy="smart",
        force_avoid_overlap=False,
        should_abort=lambda: False,
        set_range_progress=lambda *args: progress.append(args),
        timeline_audio_path=lambda index, cue: prepared.append((index, cue.original)) or cue.audio_path,
        duration_seconds=lambda cue, _path: cue.duration_seconds or 0.25,
    )

    assert prepared == [(0, "first"), (1, "second")]
    assert progress == [(76, 88, 0, 2), (76, 88, 1, 2)]
    assert inputs == [(source_a, 0.0), (source_b, 1.75)]


def test_aligned_timeline_inputs_returns_none_when_aborted(tmp_path) -> None:
    calls = 0

    def should_abort() -> bool:
        nonlocal calls
        calls += 1
        return calls > 1

    inputs = aligned_audio.aligned_timeline_inputs(
        [
            export_worker.ExportCue(0.0, "first", "mot", tmp_path / "a.wav", duration_seconds=1.0),
            export_worker.ExportCue(1.0, "second", "hai", tmp_path / "b.wav", duration_seconds=1.0),
        ],
        progress_start=76,
        progress_end=88,
        overlap_policy="strict_start",
        force_avoid_overlap=False,
        should_abort=should_abort,
        set_range_progress=lambda *_args: None,
        timeline_audio_path=lambda _index, cue: cue.audio_path,
        duration_seconds=lambda cue, _path: cue.duration_seconds or 0.25,
    )

    assert inputs is None


def test_document_export_voice_helper_sanitizes_invalid_cue_timing(tmp_path) -> None:
    silences: list[tuple[float, Path]] = []

    cue = document_export_voice.build_document_export_cue(
        index=4,
        cue=export_worker.TranscriptCue(float("inf"), float("nan"), "hello"),
        original="hello",
        translated="xin chao",
        tts_suffix="mp3",
        temp_dir=tmp_path,
        config=AppConfig(tts_provider="none"),
        tts_provider=SimpleNamespace(
            synthesize=lambda *_args, **_kwargs: pytest.fail("disabled TTS should not synthesize")
        ),
        tts_lock=nullcontext(),
        make_silence=lambda duration, output_path: silences.append((duration, output_path))
        or Path(output_path).write_bytes(b"silence"),
        trim_leading_silence=lambda path: path,
        to_wav=lambda *_args: pytest.fail("disabled TTS should not convert audio"),
    )

    assert silences == [(0.25, tmp_path / "document-cue-00004.wav")]
    assert cue.start_seconds == 0.0
    assert cue.duration_seconds == 0.25
    assert cue.audio_path == tmp_path / "document-cue-00004.wav"


def test_build_prepared_document_export_cues_reports_progress_and_sorts(tmp_path) -> None:
    progress: list[tuple[int, int, int, int]] = []
    emitted: list[tuple[str, str]] = []
    items = [
        (1, export_worker.TranscriptCue(2.0, 3.0, "second"), "second"),
        (0, export_worker.TranscriptCue(0.0, 1.0, "first"), "first"),
    ]

    def fake_build(index, cue, original, translated, suffix):
        return export_worker.ExportCue(
            cue.start_seconds,
            original,
            f"{translated}:{suffix}",
            tmp_path / f"{index}.wav",
            duration_seconds=cue.end_seconds - cue.start_seconds,
        )

    cues = document_export_voice.build_prepared_document_export_cues(
        items=items,
        translated_items=["hai", "mot"],
        tts_suffix="wav",
        max_workers=1,
        build_document_export_cue=fake_build,
        should_stop=lambda: False,
        set_range_progress=lambda *args: progress.append(args),
        emit_progress=lambda key, **kwargs: emitted.append((key, kwargs["time"])),
    )

    assert progress == [(18, 74, 0, 2), (18, 74, 1, 2)]
    assert emitted == [
        ("document_export_progress_creating_voice_at", "00:00:02"),
        ("document_export_progress_creating_voice_at", "00:00:00"),
    ]
    assert [cue.original for cue in cues] == ["first", "second"]
    assert [cue.translated for cue in cues] == ["mot:wav", "hai:wav"]
