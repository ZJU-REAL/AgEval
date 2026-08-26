"""Public Registry start is fail-closed without Postgres + S3."""

from __future__ import annotations

from pathlib import Path

import pytest
from services.registry.app import build_default_state, build_state_from_env
from services.registry.backend import (
    PublicBackendError,
    public_env_ready,
    require_public_backend,
)


def test_require_public_backend_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AGEVAL_REGISTRY_DATABASE_URL", raising=False)
    monkeypatch.delenv("AGEVAL_REGISTRY_S3_ENDPOINT", raising=False)
    assert public_env_ready() is False
    with pytest.raises(PublicBackendError, match="AGEVAL_REGISTRY_DATABASE_URL"):
        require_public_backend()


def test_require_public_backend_partial(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGEVAL_REGISTRY_DATABASE_URL", "postgresql://ageval:ageval@127.0.0.1/x")
    monkeypatch.delenv("AGEVAL_REGISTRY_S3_ENDPOINT", raising=False)
    with pytest.raises(PublicBackendError, match="S3"):
        require_public_backend()


def test_require_public_backend_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGEVAL_REGISTRY_DATABASE_URL", "postgresql://ageval:ageval@127.0.0.1/x")
    monkeypatch.setenv("AGEVAL_REGISTRY_S3_ENDPOINT", "http://127.0.0.1:9000")
    assert public_env_ready() is True
    url, endpoint = require_public_backend()
    assert url.startswith("postgresql://")
    assert endpoint.startswith("http://")


def test_build_state_from_env_fail_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("services.registry.app.load_env_file", lambda: None)
    monkeypatch.delenv("AGEVAL_REGISTRY_DATABASE_URL", raising=False)
    monkeypatch.delenv("AGEVAL_REGISTRY_S3_ENDPOINT", raising=False)
    monkeypatch.setenv("AGEVAL_REGISTRY_DATA_DIR", str(tmp_path / "data"))
    with pytest.raises(PublicBackendError):
        build_state_from_env(force_local=False, bootstrap_token="t")


def test_build_state_from_env_force_local(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGEVAL_REGISTRY_DATA_DIR", str(tmp_path / "data"))
    state, token = build_state_from_env(
        force_local=True, bootstrap_token="local-token", memory_blob=True
    )
    assert token == "local-token"
    assert state.max_upload > 0
    health_auth = state.auth.auth_for("local-token")
    assert "admin" in health_auth.scopes


def test_local_default_state_still_works(tmp_path: Path) -> None:
    state, token = build_default_state(tmp_path / "data", bootstrap_token="boot", memory_blob=True)
    assert token == "boot"
    assert state.upload_slots.limit >= 1
