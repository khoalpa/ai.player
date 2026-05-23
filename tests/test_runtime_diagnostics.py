from __future__ import annotations

from pathlib import Path

import pytest

from ai_player.core import runtime_diagnostics as diag


def test_runtime_diagnostics_failure_count_counts_required_misses() -> None:
    report = diag.RuntimeDiagnostics(
        python="python",
        project_root=Path("x"),
        sections=(
            diag.DiagnosticSection(
                "section",
                (
                    diag.DiagnosticItem("required", "MISS", "", required=True),
                    diag.DiagnosticItem("optional", "MISS", "", required=False),
                ),
            ),
        ),
    )

    assert report.failure_count == 1


@pytest.mark.parametrize(("status", "display"), [("OK", "OK  "), ("WARN", "WARN")])
def test_display_status(status: str, display: str) -> None:
    assert diag._display_status(diag.DiagnosticItem("item", status, "")) == display


def test_package_section_marks_missing_required(monkeypatch) -> None:
    monkeypatch.setattr(diag, "PYTHON_PACKAGES", ("definitely_missing_package",))
    monkeypatch.setattr(diag.importlib.util, "find_spec", lambda _name: None)

    section = diag._package_section()

    assert section.items[0].status == "MISS"
    assert section.items[0].required is True


@pytest.mark.parametrize("candidate_index", [0, 1])
def test_first_tool_uses_path_candidates(monkeypatch, tmp_path, candidate_index: int) -> None:
    tool = tmp_path / "tool.exe"
    tool.write_text("", encoding="utf-8")
    candidates = ("missing", str(tool)) if candidate_index else (str(tool), "missing")
    monkeypatch.setattr(diag.shutil, "which", lambda _candidate: None)

    assert diag._first_tool(candidates) == str(tool)


def test_first_tool_rejects_unresolved_ffmpeg_fallback(monkeypatch) -> None:
    monkeypatch.setattr(diag, "ffmpeg_executable", lambda: "ffmpeg")
    monkeypatch.setattr(diag.shutil, "which", lambda _candidate: None)

    assert diag._first_tool(("ffmpeg",)) == ""


def test_first_tool_accepts_resolved_ffmpeg_path(monkeypatch, tmp_path) -> None:
    ffmpeg = tmp_path / "ffmpeg.exe"
    ffmpeg.write_text("", encoding="utf-8")
    monkeypatch.setattr(diag, "ffmpeg_executable", lambda: str(ffmpeg))
    monkeypatch.setattr(diag.shutil, "which", lambda _candidate: None)

    assert diag._first_tool(("ffmpeg",)) == str(ffmpeg)


@pytest.mark.parametrize("present", [False, True])
def test_model_section_reports_missing_required_files(monkeypatch, tmp_path, present: bool) -> None:
    model_dir = tmp_path / "model"
    model_dir.mkdir()
    if present:
        (model_dir / "config.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(diag, "MODEL_REQUIREMENTS", {"Demo": (model_dir, ("config.json",))})

    item = diag._model_section().items[0]

    assert item.status == ("OK" if present else "WARN")


@pytest.mark.parametrize(("langs", "status"), [(["eng", "osd", "vie"], "OK"), (["eng"], "WARN")])
def test_tessdata_section_requires_core_languages(monkeypatch, tmp_path, langs: list[str], status: str) -> None:
    for lang in langs:
        (tmp_path / f"{lang}.traineddata").write_text("", encoding="utf-8")
    monkeypatch.setattr(diag, "TESSDATA", tmp_path)

    assert diag._tessdata_section().items[0].status == status
