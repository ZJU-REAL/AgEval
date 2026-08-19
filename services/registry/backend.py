"""Public vs local Registry backend selection.

Public start is fail-closed: Postgres URL + S3 endpoint are required.
``--local`` / ``--memory-blob`` remain the only SQLite / in-process paths.
"""

from __future__ import annotations

import os


class PublicBackendError(RuntimeError):
    """Raised when a public start is missing required backends."""


def postgres_url() -> str:
    return (os.environ.get("AGEVAL_REGISTRY_DATABASE_URL") or "").strip()


def s3_endpoint() -> str:
    return (os.environ.get("AGEVAL_REGISTRY_S3_ENDPOINT") or "").strip()


def public_env_ready() -> bool:
    return bool(postgres_url() and s3_endpoint())


def require_public_backend() -> tuple[str, str]:
    """Return ``(database_url, s3_endpoint)`` or raise ``PublicBackendError``."""
    database_url = postgres_url()
    endpoint = s3_endpoint()
    if not database_url or not endpoint:
        raise PublicBackendError(
            "public registry start requires AGEVAL_REGISTRY_DATABASE_URL and "
            "AGEVAL_REGISTRY_S3_ENDPOINT; use --local or --memory-blob for dev/test"
        )
    return database_url, endpoint
