"""ExecutableGrant must keep venv python symlinks (not follow to base CPython)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from bora.provider.contract import ExecutableGrant
from bora.provider.errors import ProviderError


def test_resolve_keeps_symlink_to_real_python(tmp_path: Path) -> None:
    target = Path(sys.executable).resolve()
    link = tmp_path / "bin" / "python3"
    link.parent.mkdir()
    link.symlink_to(target)
    granted = ExecutableGrant(path=link).resolve()
    assert granted == link
    assert granted.is_symlink()
    assert granted.resolve() == target


def test_resolve_relative_symlink(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    target = Path(sys.executable).resolve()
    monkeypatch.chdir(tmp_path)
    link = Path("python3")
    link.symlink_to(target)
    granted = ExecutableGrant(path=Path("python3")).resolve()
    assert granted == tmp_path / "python3"
    assert granted.is_symlink()


def test_resolve_missing_raises(tmp_path: Path) -> None:
    with pytest.raises(ProviderError) as ei:
        ExecutableGrant(path=tmp_path / "missing").resolve()
    assert ei.value.error_code == "undeclared_executable"
