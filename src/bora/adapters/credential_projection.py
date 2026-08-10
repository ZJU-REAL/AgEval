"""Executor-only credential projection for L1 (no host secret in package/evidence)."""

from __future__ import annotations

import contextlib
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
    """Copy allowlisted credential *files* into an ephemeral mount tree.

    Never mounts the host ``$HOME``. Never writes secrets into evidence (this
    tree is attempt-private and mounted only into the Agent Executor container).
    """
    root = Path(tempfile.mkdtemp(prefix="bora-cred-", dir=str(work_root)))
    keys: list[str] = []
    has = False

    # Empty HOME for the container user (writable cache only; no host files).
    home = root / "home"
    home.mkdir(parents=True, exist_ok=True)
    keys.append("home/")

    # CODEX_HOME: copy allowlisted files only (not the whole directory tree).
    codex_home = os.environ.get("CODEX_HOME") or str(Path.home() / ".codex")
    src = Path(codex_home)
    dest = root / "codex_home"
    dest.mkdir(parents=True, exist_ok=True)
    if src.is_dir():
        for name in ("auth.json", "config.toml", "config.json"):
            f = src / name
            if f.is_file():
                shutil.copy2(f, dest / name)
                has = True
                keys.append(f"codex_home/{name}")
        (root / "locator.json").write_text(
            '{"kind":"codex_home","projected":true}\n', encoding="utf-8"
        )
    else:
        (root / "locator.json").write_text(
            '{"kind":"codex_home","projected":false}\n', encoding="utf-8"
        )
    keys.append("locator.json")

    # Optional allowlisted auth files for other CLIs (copy only if present).
    allowlisted_files: list[tuple[Path, str]] = [
        (Path.home() / ".pi" / "agent" / "auth.json", "pi_home/agent/auth.json"),
        (Path.home() / ".local" / "share" / "opencode" / "auth.json", "opencode/auth.json"),
        # Grok Build ACP (Mode 3) host OAuth / session store — not XAI_API_KEY alone.
        (Path.home() / ".grok" / "auth.json", "grok_home/auth.json"),
    ]
    for src_file, rel in allowlisted_files:
        if src_file.is_file():
            target = root / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_file, target)
            with contextlib.suppress(OSError):
                target.chmod(0o600)
            has = True
            keys.append(rel)

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
