"""Atomic verified Database cache under ``.bora/cache/databases/``."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path

from bora.registry.archive import extract_archive
from bora.registry.digest import compute_package_digest


def default_cache_root() -> Path:
    env = os.environ.get("BORA_CACHE_ROOT")
    if env:
        return Path(env).expanduser().resolve()
    return (Path.cwd() / ".bora" / "cache").resolve()


class PackageCache:
    """Filesystem cache: ``<root>/databases/<id>/<packageDigest>/``."""

    def __init__(self, cache_root: Path | None = None) -> None:
        self.root = (cache_root or default_cache_root()).resolve()

    def entry_dir(self, database_id: str, package_digest: str) -> Path:
        # database_id may contain '/'; encode as nested path is fine (validated charset).
        digest_key = package_digest.replace(":", "_")
        return self.root / "databases" / database_id / digest_key

    def lookup(self, database_id: str, package_digest: str) -> Path | None:
        """Return verified cache path or None if missing/corrupt."""
        entry = self.entry_dir(database_id, package_digest)
        marker = entry / ".bora-verified"
        if not marker.is_file():
            return None
        try:
            meta = json.loads(marker.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if meta.get("package_digest") != package_digest:
            return None
        if not (entry / "bora.yaml").is_file():
            return None
        # Re-hash on lookup is optional; v1 trusts marker + present root after write-time verify.
        return entry

    def publish_atomic(
        self,
        *,
        database_id: str,
        package_digest: str,
        archive: bytes,
        expected_blob_digest: str | None = None,
    ) -> Path:
        """Extract archive into a temp dir, verify packageDigest, then atomic rename."""
        import hashlib

        if expected_blob_digest is not None:
            actual = f"sha256:{hashlib.sha256(archive).hexdigest()}"
            if actual != expected_blob_digest:
                msg = f"blob digest mismatch: expected {expected_blob_digest}, got {actual}"
                raise ValueError(msg)

        final = self.entry_dir(database_id, package_digest)
        if self.lookup(database_id, package_digest) is not None:
            return final

        final.parent.mkdir(parents=True, exist_ok=True)
        tmp = Path(tempfile.mkdtemp(prefix=".bora-cache-tmp-", dir=str(final.parent)))
        try:
            extract_archive(archive, tmp)
            got = compute_package_digest(tmp)
            if got != package_digest:
                msg = f"package digest mismatch after extract: expected {package_digest}, got {got}"
                raise ValueError(msg)
            marker = {
                "package_digest": package_digest,
                "database_id": database_id,
                "schema": "bora.cache.verified/1",
            }
            (tmp / ".bora-verified").write_text(
                json.dumps(marker, sort_keys=True) + "\n", encoding="utf-8"
            )
            # Atomic publish: rename temp → final (replace if partial exists).
            if final.exists():
                shutil.rmtree(final)
            tmp.rename(final)
            return final
        except Exception:
            shutil.rmtree(tmp, ignore_errors=True)
            raise
