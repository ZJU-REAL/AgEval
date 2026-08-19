"""CLI credentials file: ``~/.ageval/credentials`` (mode 0600).

Wire format (JSON)::

    {
      "registry": {
        "url": "http://127.0.0.1:8700",
        "token": "ageval_…",
        "token_env": "AGEVAL_REGISTRY_TOKEN"   # optional locator; wins over token if set
      }
    }

Tokens never enter lock/evidence. Env ``AGEVAL_REGISTRY_URL`` overrides file URL.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class RegistryCredentials:
    url: str | None
    token: str | None


def default_credentials_path() -> Path:
    return Path.home() / ".ageval" / "credentials"


def load_credentials(path: Path | None = None) -> RegistryCredentials:
    """Load credentials; missing file → empty (env may still supply URL/token)."""
    cred_path = path or default_credentials_path()
    url: str | None = None
    token: str | None = None
    if cred_path.is_file():
        try:
            data = json.loads(cred_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = {}
        reg = data.get("registry") if isinstance(data, dict) else None
        if isinstance(reg, dict):
            raw_url = reg.get("url")
            if isinstance(raw_url, str) and raw_url.strip():
                url = raw_url.strip().rstrip("/")
            env_name = reg.get("token_env")
            if isinstance(env_name, str) and env_name:
                token = os.environ.get(env_name) or None
            if token is None:
                raw_tok = reg.get("token")
                if isinstance(raw_tok, str) and raw_tok:
                    token = raw_tok
    env_url = os.environ.get("AGEVAL_REGISTRY_URL")
    if env_url and env_url.strip():
        url = env_url.strip().rstrip("/")
    env_tok = os.environ.get("AGEVAL_REGISTRY_TOKEN")
    if env_tok:
        token = env_tok
    return RegistryCredentials(url=url, token=token)


def write_credentials(
    *,
    url: str,
    token: str,
    path: Path | None = None,
) -> Path:
    """Write credentials file with mode 0600 (operator/bootstrap helper)."""
    cred_path = path or default_credentials_path()
    cred_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"registry": {"url": url.rstrip("/"), "token": token}}
    cred_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    cred_path.chmod(0o600)
    return cred_path
