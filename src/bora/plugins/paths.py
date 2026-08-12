"""Local plugin cache paths (constitution §7.1B).

BORA_HOME defaults to ``~/.bora``; plugins live under ``$BORA_HOME/plugins``.
"""

from __future__ import annotations

import os
from pathlib import Path

ENV_BORA_HOME = "BORA_HOME"
PLUGINS_DIRNAME = "plugins"
INDEX_FILENAME = "index.json"


def bora_home() -> Path:
    raw = os.environ.get(ENV_BORA_HOME, "").strip()
    if raw:
        return Path(raw).expanduser().resolve(strict=False)
    return (Path.home() / ".bora").resolve(strict=False)


def plugins_root() -> Path:
    return bora_home() / PLUGINS_DIRNAME


def index_path() -> Path:
    return plugins_root() / INDEX_FILENAME


def package_dir(plugin_id: str, version_or_digest: str) -> Path:
    return plugins_root() / plugin_id / version_or_digest
