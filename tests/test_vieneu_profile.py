import pytest

from ai_player.runtime.vieneu_profile import PATCHED_FILES, record_runtime_profile, validate_runtime_profile


def test_runtime_patch_manifest_detects_changed_sdk_file(tmp_path):
    package = tmp_path / "site-packages/vieneu"
    package.mkdir(parents=True)
    for name in PATCHED_FILES:
        (package / name).write_text("# pinned SDK\n", encoding="utf-8")
    record_runtime_profile(tmp_path, package)
    validate_runtime_profile(tmp_path, package)
    (package / "factory.py").write_text("# replaced\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="missing or modified"):
        validate_runtime_profile(tmp_path, package)


def test_profile_rejects_package_outside_runtime(tmp_path):
    with pytest.raises(ValueError, match="dedicated runtime"):
        record_runtime_profile(tmp_path / "runtime", tmp_path / "outside")
