"""Provider L0 architecture boundaries."""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SRC = REPO / "src"


def test_src_does_not_import_tests() -> None:
    offenders: list[str] = []
    for path in SRC.rglob("*.py"):
        for line in path.read_text(encoding="utf-8").splitlines():
            s = line.strip()
            if s.startswith("#"):
                continue
            if "from tests" in s or "import tests" in s:
                offenders.append(f"{path}:{s}")
    assert offenders == []


def test_composition_does_not_wire_provider_probe() -> None:
    text = (SRC / "bora" / "application" / "composition.py").read_text(encoding="utf-8")
    assert "LocalProcessProvider" not in text
    assert "run_provider_probe" not in text
    assert "provider_probe" not in text


def test_provider_helper_not_imported_from_src() -> None:
    for path in (SRC / "bora").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "provider_probe_child" not in text
