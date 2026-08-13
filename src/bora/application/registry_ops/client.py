"""Single RegistryClient factory for results / list / org commands."""

from __future__ import annotations

import os

from bora.config.errors import ConfigError
from bora.registry.client import RegistryClient
from bora.registry.credentials import load_credentials


def build_registry_client(
    *,
    registry_url: str | None = None,
    token: str | None = None,
    require_token: bool = True,
    accept_results_url: bool = False,
) -> RegistryClient:
    """Assemble a RegistryClient from explicit URL, credentials, or env locators."""
    creds = load_credentials()
    url = (registry_url or "").rstrip("/")
    if not url and accept_results_url:
        url = (os.environ.get("BORA_RESULTS_URL") or "").rstrip("/")
    if not url:
        url = (creds.url or os.environ.get("BORA_REGISTRY_URL") or "").rstrip("/")
    if not url:
        raise ConfigError(
            "registry_unavailable",
            "registry URL required (BORA_REGISTRY_URL / BORA_RESULTS_URL or credentials)",
            location="registry",
        )
    resolved = (
        token if token is not None else (creds.token or os.environ.get("BORA_REGISTRY_TOKEN"))
    )
    if require_token and not resolved:
        raise ConfigError(
            "unauthorized",
            "registry token required (bora login, credentials file, or BORA_REGISTRY_TOKEN)",
            location="registry",
        )
    return RegistryClient(url, token=resolved)
