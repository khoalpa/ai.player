import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_accepted_dependency_audit_vulnerabilities_are_documented() -> None:
    script = (PROJECT_ROOT / "scripts" / "audit_dependencies.ps1").read_text(encoding="utf-8")
    docs = (PROJECT_ROOT / "docs" / "dependency_audit.md").read_text(encoding="utf-8")

    accepted = set(re.findall(r"CVE-\d{4}-\d+", script))

    assert accepted
    assert accepted <= set(re.findall(r"CVE-\d{4}-\d+", docs))
