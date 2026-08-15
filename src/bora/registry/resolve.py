"""Resolve PackageRef → local Database root (path or verified cache)."""

from __future__ import annotations

from pathlib import Path

from bora.config.errors import ConfigError
from bora.registry.cache import PackageCache
from bora.registry.client import RegistryClient, RegistryError
from bora.registry.credentials import load_credentials
from bora.registry.ref import parse_package_ref


def resolve_database_root(
    raw: str | Path,
    *,
    cwd: Path | None = None,
    cache: PackageCache | None = None,
    client: RegistryClient | None = None,
) -> Path:
    """Return a local filesystem Database root for *raw* path or registry ref."""
    ref = parse_package_ref(raw, cwd=cwd)
    if ref.kind == "path":
        assert ref.path is not None
        return ref.path

    pkg_cache = cache or PackageCache()
    assert ref.database_id is not None

    # Prefer cache hit before contacting registry.
    if ref.kind == "digest":
        assert ref.package_digest is not None
        hit = pkg_cache.lookup(ref.database_id, ref.package_digest)
        if hit is not None:
            return hit
    # For version refs we need metadata first (or cache index). version→digest map
    # lives on the registry; offline only works after a prior fetch.

    reg_client = client
    if reg_client is None:
        creds = load_credentials()
        if not creds.url:
            if ref.kind == "digest" and ref.package_digest:
                hit = pkg_cache.lookup(ref.database_id, ref.package_digest)
                if hit is not None:
                    return hit
            raise ConfigError(
                "registry_unavailable",
                "registry URL not configured (BORA_REGISTRY_URL or ~/.bora/credentials) "
                "and no verified cache hit",
                location=ref.display(),
            )
        reg_client = RegistryClient(creds.url, token=creds.token)

    try:
        if ref.kind == "digest":
            assert ref.package_digest is not None
            meta = reg_client.get_metadata(
                database_id=ref.database_id, package_digest=ref.package_digest
            )
        else:
            assert ref.version is not None
            meta = reg_client.get_metadata(database_id=ref.database_id, version=ref.version)
        hit = pkg_cache.lookup(meta.database_id, meta.package_digest)
        if hit is not None:
            return hit
        import tempfile

        with tempfile.TemporaryDirectory(prefix="bora-fetch-") as tmp:
            dest = Path(tmp) / "package.tar.gz"
            reg_client.fetch_content(
                database_id=meta.database_id,
                package_digest=meta.package_digest,
                dest=dest,
            )
            return pkg_cache.publish_atomic(
                database_id=meta.database_id,
                package_digest=meta.package_digest,
                archive=dest,
                expected_blob_digest=meta.blob_digest,
            )
    except RegistryError as exc:
        # Offline: digest ref may still hit cache (already checked); version cannot.
        if exc.code == "registry_unavailable" and ref.kind == "digest" and ref.package_digest:
            hit = pkg_cache.lookup(ref.database_id, ref.package_digest)
            if hit is not None:
                return hit
        raise ConfigError(exc.code, exc.message, location=ref.display()) from exc
    except ValueError as exc:
        raise ConfigError("invalid_package", str(exc), location=ref.display()) from exc


def resolve_ref(raw: str | Path, **kwargs: object) -> Path:
    """Alias used by application layer."""
    return resolve_database_root(raw, **kwargs)  # type: ignore[arg-type]
