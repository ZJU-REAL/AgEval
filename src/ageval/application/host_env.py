"""Host env bootstrap: load ``.env`` files as credential locators only.

Values are injected into ``os.environ`` for executor projection. Never written
into lock digests, package YAML, or evidence. Existing process env wins.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

_LINE_RE = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)\s*$")


def _strip_value(raw: str) -> str:
    text = raw.strip()
    if not text:
        return ""
    if text[0] in "\"'" and len(text) >= 2 and text[-1] == text[0]:
        return text[1:-1]
    # Inline comment without quotes: KEY=value # comment
    if " #" in text:
        text = text.split(" #", 1)[0].rstrip()
    return text


def apply_dotenv_file(path: Path, *, override: bool = False) -> int:
    """Apply one dotenv file. Returns number of keys newly set (or overridden)."""
    if not path.is_file():
        return 0
    count = 0
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return 0
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        m = _LINE_RE.match(line)
        if not m:
            continue
        key, raw_val = m.group(1), m.group(2)
        if not override and key in os.environ:
            continue
        os.environ[key] = _strip_value(raw_val)
        count += 1
    return count


def load_host_env_files(*, package_root: Path) -> list[str]:
    """Load package / cwd / repo ``.env`` without overriding existing env.

    Search order (first wins per key because later files skip set keys):
    1. process env (already set)
    2. ``package_root/.env``
    3. ``cwd/.env``
    4. walk parents until repo-like root (``pyproject.toml`` + ``src/ageval``) ``.env``
    """
    loaded: list[str] = []
    candidates: list[Path] = [
        package_root / ".env",
        Path.cwd() / ".env",
    ]
    root = package_root.resolve()
    for parent in [root, *root.parents]:
        if (parent / "pyproject.toml").is_file() and (parent / "src" / "ageval").is_dir():
            candidates.append(parent / ".env")
            break
        candidates.append(parent / ".env")

    seen: set[Path] = set()
    for path in candidates:
        try:
            resolved = path.resolve()
        except OSError:
            continue
        if resolved in seen:
            continue
        seen.add(resolved)
        apply_dotenv_file(resolved, override=False)
        if resolved.is_file():
            loaded.append(str(resolved))
    return loaded
