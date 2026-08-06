"""Load ``services/registry/.env`` into ``os.environ`` (stdlib only).

Does not override variables already set in the process environment.
Never logs secret values.
"""

from __future__ import annotations

import os
from pathlib import Path

_DEFAULT_ENV = Path(__file__).resolve().parent / ".env"


def load_env_file(path: Path | None = None) -> Path | None:
    """Parse KEY=VALUE lines; return path if loaded, else None."""
    env_path = path or _DEFAULT_ENV
    if not env_path.is_file():
        return None
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if not key:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        # Prefer already-exported env (CI / operator override).
        os.environ.setdefault(key, value)
    return env_path
