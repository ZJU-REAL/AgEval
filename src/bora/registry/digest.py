"""Suite packageDigest: sorted paths + per-file sha256 + outer sha256.

Algorithm (Spec 21 Phase 0 freeze):

1. Enumerate files via ``member_paths_for_digest`` (stable order; includes root
   ``bora.yaml``, optional ``shared/**``, files named by binding ``overlays:``,
   and every non-hidden member file except ``__pycache__`` / ``*.pyc``).
2. For each path, compute ``sha256`` of raw file bytes.
3. Build canonical text (UTF-8, LF only)::

       <hex64>  <posix-relative-path>\\n

4. ``packageDigest = "sha256:" + sha256(canonical_text).hexdigest()``.

Paths are package-relative posix strings; no host absolute paths enter the digest.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from bora.config.database import member_paths_for_digest


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def compute_package_digest(database_root: Path) -> str:
    """Return ``sha256:<64 hex>`` over the canonical package tree."""
    root = database_root.expanduser().resolve(strict=False)
    lines: list[str] = []
    for rel in member_paths_for_digest(root):
        abs_path = root / rel
        if not abs_path.is_file():
            continue
        digest = file_sha256(abs_path)
        lines.append(f"{digest}  {rel}\n")
    blob = "".join(lines).encode("utf-8")
    return f"sha256:{hashlib.sha256(blob).hexdigest()}"
