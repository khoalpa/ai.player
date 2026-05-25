from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_heavy_runtime_dependencies_stay_out_of_base_profile() -> None:
    pyproject = _load_pyproject()
    base_dependencies = _normalized_dependencies(pyproject["project"]["dependencies"])

    forbidden_base_packages = {
        "demucs",
        "onnxruntime-gpu",
        "nvidia-cublas-cu12",
        "nvidia-cudnn-cu12",
        "nvidia-cuda-nvrtc-cu12",
    }

    assert not (base_dependencies & forbidden_base_packages)


def test_heavy_runtime_dependencies_are_assigned_to_optional_profiles() -> None:
    pyproject = _load_pyproject()
    optional = pyproject["project"]["optional-dependencies"]

    gpu_dependencies = _normalized_dependencies(optional["gpu"])
    audio_separation_dependencies = _normalized_dependencies(optional["audio-separation"])

    assert {
        "onnxruntime-gpu",
        "nvidia-cublas-cu12",
        "nvidia-cudnn-cu12",
        "nvidia-cuda-nvrtc-cu12",
    } <= gpu_dependencies
    assert "demucs" in audio_separation_dependencies


def test_requirements_file_omits_gpu_and_audio_separation_extras() -> None:
    requirements = _normalized_dependencies(
        line
        for line in (PROJECT_ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    )

    assert "demucs" not in requirements
    assert "onnxruntime-gpu" not in requirements
    assert "nvidia-cublas-cu12" not in requirements
    assert "nvidia-cudnn-cu12" not in requirements
    assert "nvidia-cuda-nvrtc-cu12" not in requirements


def _load_pyproject() -> dict:
    try:
        import tomllib
    except ModuleNotFoundError:
        try:
            import tomli as tomllib
        except ModuleNotFoundError:
            from setuptools._vendor import tomli as tomllib

    return tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))


def _normalized_dependencies(dependencies) -> set[str]:
    names = set()
    for dependency in dependencies:
        name = str(dependency).split(";", 1)[0].strip()
        for separator in ("==", ">=", "<=", "~=", "!=", ">", "<", "["):
            name = name.split(separator, 1)[0].strip()
        if name:
            names.add(name.lower())
    return names
