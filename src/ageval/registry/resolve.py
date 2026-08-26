"""Resolve PackageRef → local Dataset root (path or verified cache)."""

from __future__ import annotations

import shutil
from pathlib import Path

from ageval.config.dataset import load_dataset_manifest
from ageval.config.errors import ConfigError
from ageval.registry.cache import PackageCache
from ageval.registry.client import RegistryClient, RegistryError
from ageval.registry.credentials import load_credentials
from ageval.registry.digest import compute_package_digest
from ageval.registry.ref import PackageRef, parse_package_ref


def resolve_dataset_root(
    raw: str | Path,
    *,
    cwd: Path | None = None,
    cache: PackageCache | None = None,
    client: RegistryClient | None = None,
) -> Path:
    """Return a local filesystem Dataset root for *raw* path or registry ref."""
    ref = parse_package_ref(raw, cwd=cwd)
    if ref.kind == "path":
        assert ref.path is not None
        return ref.path

    pkg_cache = cache or PackageCache()
    assert ref.dataset_id is not None

    # Prefer cache hit before contacting registry.
    if ref.kind == "digest":
        assert ref.package_digest is not None
        hit = pkg_cache.lookup(ref.dataset_id, ref.package_digest)
        if hit is not None:
            return hit
    elif ref.kind == "version" and ref.version:
        hit = pkg_cache.lookup_version(ref.dataset_id, ref.version)
        if hit is not None:
            return hit
    # Version → digest otherwise lives on the registry; a prior fetch that
    # left a unique verified tree is enough for view / run without Hub.

    reg_client = client
    if reg_client is None:
        creds = load_credentials()
        if not creds.url:
            if ref.kind == "digest" and ref.package_digest:
                hit = pkg_cache.lookup(ref.dataset_id, ref.package_digest)
                if hit is not None:
                    return hit
            raise ConfigError(
                "registry_unavailable",
                "registry URL not configured (AGEVAL_REGISTRY_URL or ~/.ageval/credentials) "
                "and no verified cache hit",
                location=ref.display(),
            )
        reg_client = RegistryClient(creds.url, token=creds.token)

    try:
        if ref.kind == "digest":
            assert ref.package_digest is not None
            meta = reg_client.get_metadata(
                dataset_id=ref.dataset_id, package_digest=ref.package_digest
            )
        else:
            assert ref.version is not None
            meta = reg_client.get_metadata(dataset_id=ref.dataset_id, version=ref.version)
        hit = pkg_cache.lookup(meta.dataset_id, meta.package_digest)
        if hit is not None:
            return hit
        import tempfile

        with tempfile.TemporaryDirectory(prefix="ageval-fetch-") as tmp:
            dest = Path(tmp) / "package.tar.gz"
            reg_client.fetch_content(
                dataset_id=meta.dataset_id,
                package_digest=meta.package_digest,
                dest=dest,
            )
            return pkg_cache.publish_atomic(
                dataset_id=meta.dataset_id,
                package_digest=meta.package_digest,
                archive=dest,
                expected_blob_digest=meta.blob_digest,
            )
    except RegistryError as exc:
        # Offline: digest ref may still hit cache (already checked); version cannot.
        if exc.code == "registry_unavailable" and ref.kind == "digest" and ref.package_digest:
            hit = pkg_cache.lookup(ref.dataset_id, ref.package_digest)
            if hit is not None:
                return hit
        raise ConfigError(exc.code, exc.message, location=ref.display()) from exc
    except ValueError as exc:
        raise ConfigError("invalid_package", str(exc), location=ref.display()) from exc


def resolve_ref(raw: str | Path, **kwargs: object) -> Path:
    """Alias used by application layer."""
    return resolve_dataset_root(raw, **kwargs)  # type: ignore[arg-type]


def checkout_dataset(
    raw: str | Path,
    dest: str | Path,
    *,
    cwd: Path | None = None,
    cache: PackageCache | None = None,
    client: RegistryClient | None = None,
) -> Path:
    """Install a registry ref under *dest* and return the dataset root.

    ``--dir tmp`` looks at ``tmp/<dataset_id>/`` (``dataset_id`` may contain
    ``/``). Reuse that child if it already matches the ref; otherwise fetch
    into it. *dest* itself is the parent, not the dataset root.
    """
    ref = parse_package_ref(raw, cwd=cwd)
    if ref.kind == "path":
        raise ConfigError(
            "invalid_override",
            "--dir requires a registry ref (dataset_id@version or @sha256:…)",
            location="--dir",
        )
    assert ref.dataset_id is not None
    parent = _resolve_dir_path(dest, cwd=cwd)
    if parent.exists() and parent.is_file():
        raise ConfigError(
            "invalid_package",
            f"--dir path exists and is a file: {parent}",
            location="--dir",
        )
    dest_root = parent / Path(*Path(ref.dataset_id).parts)
    if dest_root.exists() and dest_root.is_file():
        raise ConfigError(
            "invalid_package",
            f"dataset path exists and is a file: {dest_root}",
            location="--dir",
        )
    if dest_root.is_dir() and (dest_root / "ageval.yaml").is_file():
        _assert_checkout_matches(dest_root, ref)
        return dest_root
    if dest_root.exists() and any(dest_root.iterdir()):
        raise ConfigError(
            "invalid_package",
            "directory exists but is not a dataset matching the ref",
            location=str(dest_root),
        )
    cached = resolve_dataset_root(raw, cwd=cwd, cache=cache, client=client)
    dest_root.parent.mkdir(parents=True, exist_ok=True)
    if dest_root.exists():
        dest_root.rmdir()
    shutil.copytree(cached, dest_root, ignore=shutil.ignore_patterns(".ageval-verified"))
    _assert_checkout_matches(dest_root, ref)
    return dest_root


def _resolve_dir_path(dest: str | Path, *, cwd: Path | None) -> Path:
    path = Path(dest).expanduser()
    if not path.is_absolute():
        path = (cwd or Path.cwd()) / path
    return path.resolve(strict=False)


def _assert_checkout_matches(root: Path, ref: PackageRef) -> None:
    manifest = load_dataset_manifest(root)
    if manifest.dataset_id != ref.dataset_id:
        raise ConfigError(
            "invalid_package",
            f"dataset at --dir is {manifest.dataset_id!r}, ref is {ref.dataset_id!r}",
            location=str(root),
        )
    if ref.kind == "version" and manifest.version != ref.version:
        raise ConfigError(
            "invalid_package",
            f"dataset at --dir is {manifest.dataset_id}@{manifest.version}, "
            f"ref is {ref.dataset_id}@{ref.version}",
            location=str(root),
        )
    if ref.kind == "digest":
        got = compute_package_digest(root)
        if got != ref.package_digest:
            raise ConfigError(
                "invalid_package",
                "dataset at --dir does not match the digest ref",
                location=str(root),
            )
