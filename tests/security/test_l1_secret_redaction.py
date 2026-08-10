"""L1 credential projection must not dump secrets into evidence JSON."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from bora.adapters.credential_projection import project_executor_credentials


def test_projection_locator_has_no_raw_secret_in_keys_list(tmp_path: Path) -> None:
    proj = project_executor_credentials(work_root=tmp_path)
    try:
        blob = json.dumps({"keys": proj.locator_keys})
        assert "sk-" not in blob
        # locator keys are path names only
        for k in proj.locator_keys:
            assert not k.startswith("sk-")
        # Scoped home for container — never host tree mount marker
        assert (proj.root / "home").is_dir()
        assert "home/" in proj.locator_keys
    finally:
        proj.cleanup()


def test_projection_copies_grok_auth_when_present(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """L1 must project host ~/.grok/auth.json for grok-build ACP (OAuth path)."""
    import bora.adapters.credential_projection as cp

    fake_home = tmp_path / "host-home"
    grok_auth = fake_home / ".grok" / "auth.json"
    grok_auth.parent.mkdir(parents=True)
    grok_auth.write_text('{"token":"test-not-a-real-secret"}\n', encoding="utf-8")
    monkeypatch.setattr(cp.Path, "home", lambda: fake_home)

    work = tmp_path / "work"
    work.mkdir()
    proj = project_executor_credentials(work_root=work)
    try:
        projected = proj.root / "grok_home" / "auth.json"
        assert projected.is_file()
        assert "grok_home/auth.json" in proj.locator_keys
        # Locator list must not embed the token value
        assert "test-not-a-real-secret" not in json.dumps(proj.locator_keys)
    finally:
        proj.cleanup()
