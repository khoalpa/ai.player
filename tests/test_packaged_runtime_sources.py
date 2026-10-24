import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


def test_isolated_runtime_sources_import_without_the_checkout(tmp_path):
    root = Path(__file__).resolve().parents[1]
    sources = json.loads((root / "scripts/vieneu_runtime_sources.json").read_text(encoding="utf-8"))
    assert len(sources) == len(set(sources))
    for relative in sources:
        source = root / "ai_player" / relative
        target = tmp_path / "ai_player" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    code = (
        "import sys; from pathlib import Path; "
        "from ai_player.adapters.tts import vieneu_tts_server as server; "
        "assert Path(server.__file__).resolve().is_relative_to(Path.cwd()); "
        "assert not {'PySide6', 'torch', 'vieneu'} & set(sys.modules)"
    )
    subprocess.run(
        [sys.executable, "-c", code],
        cwd=tmp_path,
        env={**os.environ, "PYTHONPATH": str(tmp_path)},
        check=True,
        capture_output=True,
        timeout=20,
    )
