"""Executor-only credential projection for L1 (no host secret in package/evidence)."""

from __future__ import annotations

import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path


@dataclass
class CredentialProjection:
    """Ephemeral directory mounted only into the Agent Executor container."""

    root: Path
    locator_keys: list[str]
    has_material: bool

    def cleanup(self) -> None:
        if self.root.exists():
            shutil.rmtree(self.root, ignore_errors=True)


def project_executor_credentials(*, work_root: Path) -> CredentialProjection:
    """Copy non-secret locators + optional CODEX_HOME tree into an ephemeral dir.

    Never writes secret *values* into evidence; only creates a private mount tree
    for the Executor container. Harness containers must not mount this path.
    """
    root = Path(tempfile.mkdtemp(prefix="bora-cred-", dir=str(work_root)))
    keys: list[str] = []
    has = False
    # Project CODEX_HOME / config dir by bind-friendly copy of *paths* only.
    codex_home = os.environ.get("CODEX_HOME") or str(Path.home() / ".codex")
    src = Path(codex_home)
    dest = root / "codex_home"
    if src.is_dir():
        # Shallow link strategy: copy only auth.json / config if present (files).
        dest.mkdir(parents=True, exist_ok=True)
        for name in ("auth.json", "config.toml", "config.json"):
            f = src / name
            if f.is_file():
                shutil.copy2(f, dest / name)
                has = True
                keys.append(f"codex_home/{name}")
        # Marker that projection existed (no secret content).
        (root / "locator.json").write_text(
            '{"kind":"codex_home","projected":true}\n', encoding="utf-8"
        )
        keys.append("locator.json")
    else:
        (root / "locator.json").write_text(
            '{"kind":"codex_home","projected":false}\n', encoding="utf-8"
        )
        keys.append("locator.json")
    # Optional OPENAI_API_KEY as file only (not printed); empty if absent.
    key = os.environ.get("OPENAI_API_KEY", "")
    key_path = root / "openai_api_key"
    if key:
        key_path.write_text(key, encoding="utf-8")
        key_path.chmod(0o600)
        has = True
        keys.append("openai_api_key")
    else:
        key_path.write_text("", encoding="utf-8")
    return CredentialProjection(root=root, locator_keys=keys, has_material=has)
