"""Single RegistryClient factory for results / list / org commands."""

from __future__ import annotations

import os

from ageval.config.errors import ConfigError
from ageval.registry.client import RegistryClient
from ageval.registry.credentials import load_credentials


def build_registry_client(
    *,
    registry_url: str | None = None,
    token: str | None = None,
    require_token: bool = True,
    accept_results_url: bool = False,
) -> RegistryClient:
    """Assemble a RegistryClient from flag, env, credentials, or the public default."""
    creds = load_credentials()
    url = (registry_url or "").rstrip("/")
    if not url and accept_results_url:
        url = (os.environ.get("AGEVAL_RESULTS_URL") or "").rstrip("/")
    if not url:
        url = creds.url
    resolved = (
        token if token is not None else (creds.token or os.environ.get("AGEVAL_REGISTRY_TOKEN"))
    )
    if require_token and not resolved:
        raise ConfigError(
            "unauthorized",
            "registry token required (ageval login, credentials file, or AGEVAL_REGISTRY_TOKEN)",
            location="registry",
        )
    return RegistryClient(url, token=resolved)
