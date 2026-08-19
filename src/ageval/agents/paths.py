"""Local agent cache paths (design/14).

Mirrors the plugins cache: ``$AGEVAL_HOME/agents`` + ``index.json``.
"""

from __future__ import annotations

from pathlib import Path

from ageval.plugins.paths import ageval_home

AGENTS_DIRNAME = "agents"
INDEX_FILENAME = "index.json"


def agents_root() -> Path:
    return ageval_home() / AGENTS_DIRNAME


def index_path() -> Path:
    return agents_root() / INDEX_FILENAME


def package_dir(agent_id: str, version: str) -> Path:
    return agents_root() / agent_id / version
