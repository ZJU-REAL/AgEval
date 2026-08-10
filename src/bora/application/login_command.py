"""Application use case for ``bora login`` (GitHub Device Flow)."""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import TextIO

from bora.config.errors import ConfigError
from bora.registry.client import RegistryClient, RegistryError
from bora.registry.credentials import load_credentials, write_credentials


def login_registry(
    *,
    registry_url: str | None = None,
    credentials_path: Path | None = None,
    poll_timeout: float = 900.0,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> dict[str, object]:
    """Run device flow against Registry; write ``~/.bora/credentials`` on success."""
    del stdout  # reserved for machine output if CLI needs it later
    err = stderr or sys.stderr
    creds = load_credentials(credentials_path)
    url = (registry_url or creds.url or "").rstrip("/")
    if not url:
        raise ConfigError(
            "registry_unavailable",
            "registry URL required (BORA_REGISTRY_URL, --registry-url, or credentials file)",
            location="registry",
        )

    client = RegistryClient(url, token=None)
    try:
        code_payload = client.device_code()
    except RegistryError as exc:
        raise ConfigError("login_failed", exc.message, location="registry") from exc

    user_code = str(code_payload.get("user_code") or "")
    verification_uri = str(
        code_payload.get("verification_uri") or "https://github.com/login/device"
    )
    device_code = str(code_payload.get("device_code") or "")
    interval = int(code_payload.get("interval") or 5)
    if not user_code or not device_code:
        raise ConfigError(
            "login_failed",
            "incomplete device code response",
            location="registry",
        )

    # GitHub does not auto-fill user_code from URL query params; print code clearly.
    err.write(
        f"1) Open {verification_uri}\n2) Enter code:  {user_code}\nWaiting for authorization…\n"
    )
    err.flush()

    deadline = time.monotonic() + poll_timeout
    while time.monotonic() < deadline:
        try:
            result = client.device_poll(device_code)
        except RegistryError as exc:
            if exc.status == 202 or exc.code in {"authorization_pending", "slow_down"}:
                time.sleep(max(interval, 1))
                continue
            raise ConfigError("login_failed", exc.message, location="registry") from exc

        if result.get("status") == "authorization_pending":
            time.sleep(max(interval, 1))
            continue

        token = result.get("token")
        if not isinstance(token, str) or not token:
            raise ConfigError("login_failed", "no token in response", location="registry")
        path = write_credentials(url=url, token=token, path=credentials_path)
        github_user = result.get("github_user")
        err.write(f"Logged in as {github_user or 'user'}; credentials written to {path}\n")
        return {
            "ok": True,
            "registry_url": url,
            "credentials_path": str(path),
            "github_user": github_user,
            "scopes": result.get("scopes") or [],
        }

    raise ConfigError(
        "login_failed",
        "timed out waiting for GitHub authorization",
        location="registry",
    )
