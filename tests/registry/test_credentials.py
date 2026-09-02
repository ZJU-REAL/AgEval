"""CLI registry URL default vs env / credentials file."""

from __future__ import annotations

from pathlib import Path

import pytest

from ageval.registry.credentials import (
    DEFAULT_REGISTRY_URL,
    REGISTRY_URL_ENV,
    load_credentials,
    write_credentials,
)


def test_load_credentials_defaults_to_public_origin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv(REGISTRY_URL_ENV, raising=False)
    monkeypatch.delenv("AGEVAL_REGISTRY_TOKEN", raising=False)
    creds = load_credentials()
    assert creds.url == DEFAULT_REGISTRY_URL
    assert creds.token is None


def test_env_overrides_default_and_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    write_credentials(url="http://from-file.example", token="file-tok")
    monkeypatch.setenv(REGISTRY_URL_ENV, "http://from-env.example/")
    monkeypatch.delenv("AGEVAL_REGISTRY_TOKEN", raising=False)
    creds = load_credentials()
    assert creds.url == "http://from-env.example"
    assert creds.token == "file-tok"


def test_credentials_file_overrides_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv(REGISTRY_URL_ENV, raising=False)
    monkeypatch.delenv("AGEVAL_REGISTRY_TOKEN", raising=False)
    write_credentials(url="http://127.0.0.1:8080", token="local-tok")
    creds = load_credentials()
    assert creds.url == "http://127.0.0.1:8080"
    assert creds.token == "local-tok"
