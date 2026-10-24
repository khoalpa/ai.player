"""Apply the documented v3-only profile to the pinned upstream SDK installation.

The upstream 3.8.3 wheel still ships v1/v2 engines. Remove those engines, their
factory branches and unused base methods. Forward codec_dir to the ONNX engine
so a complete local bundle needs neither a Hub cache nor a network connection.
"""

from __future__ import annotations

import ast
import importlib.metadata
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ai_player.runtime.vieneu_profile import record_runtime_profile


def prepare() -> None:
    if importlib.metadata.version("vieneu") != "3.8.3":
        raise RuntimeError("This runtime profile requires vieneu==3.8.3")
    prefix = Path(sys.prefix).resolve()
    if prefix.name != ".venv-vieneu":
        raise RuntimeError("Only the dedicated .venv-vieneu environment may be modified")
    package = Path(importlib.metadata.distribution("vieneu").locate_file("vieneu")).resolve()
    if not package.is_relative_to(prefix):
        raise RuntimeError("SDK is outside the dedicated runtime")
    # Web demos and examples also contain legacy dispatch; this runtime only hosts the SDK.
    distribution = importlib.metadata.distribution("vieneu")
    for entry in distribution.files or ():
        if str(entry).replace("\\", "/").startswith(("apps/", "examples/")):
            target = Path(distribution.locate_file(entry)).resolve()
            if not target.is_relative_to(prefix):
                raise RuntimeError("Example file is outside the dedicated runtime")
            if target.is_file():
                target.unlink()
    for name in (
        "standard.py",
        "turbo.py",
        "fast.py",
        "remote.py",
        "core_xpu.py",
        "serve.py",
        "utils.py",
        "v3nano.py",
        "_v3_nano_engine",
        "assets/voices.json",
        "assets/samples",
        "__pycache__",
    ):
        target = (package / name).resolve()
        if not target.is_relative_to(package):
            raise RuntimeError("Invalid SDK cleanup target")
        if target.is_dir():
            shutil.rmtree(target)
        elif target.exists():
            target.unlink()
    # Keep the package entry point explicit: old mode strings are errors.
    (package / "factory.py").write_text(
        """def Vieneu(mode="v3turbo", **kwargs):
    if mode != "v3turbo":
        raise ValueError("AI Player supports only VieNeu v3 Turbo")
    from .v3turbo import V3TurboVieNeuTTS
    return V3TurboVieNeuTTS(**kwargs)
""",
        encoding="utf-8",
    )
    base_path = package / "base.py"
    source = base_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    removed = {
        "_load_codec",
        "_load_voices",
        "_load_voices_from_file",
        "_load_voices_from_repo",
        "encode_reference",
        "_decode",
        "_resolve_ref_voice",
        "_format_prompt",
    }
    lines = source.splitlines(keepends=True)
    for node in sorted(
        (n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name in removed),
        key=lambda n: n.lineno,
        reverse=True,
    ):
        del lines[node.lineno - 1 : node.end_lineno]
    source = "".join(lines).replace(
        'def __init__(self, codec_repo: Optional[str] = None, codec_device: str = "cpu"):', "def __init__(self):"
    )
    source = source.replace("        if codec_repo:\n            self._load_codec(codec_repo, codec_device)\n", "")
    base_path.write_text(source, encoding="utf-8")
    wrapper = package / "v3turbo.py"
    source = wrapper.read_text(encoding="utf-8")
    if 'codec_dir=kwargs.get("codec_dir")' not in source:
        needle = "                onnx_dir=onnx_dir,\n"
        if source.count(needle) != 1:
            raise RuntimeError("Unexpected v3 SDK wrapper; refusing to patch")
        source = source.replace(needle, needle + '                codec_dir=kwargs.get("codec_dir"),\n')
        wrapper.write_text(source, encoding="utf-8")
    record_runtime_profile(prefix, package)
    print("Prepared VieNeu 3.8.3: v3 Turbo only, local codec support")


if __name__ == "__main__":
    prepare()
