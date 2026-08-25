"""Locked ``dataset_id@version`` from a finished record. No yaml fallback."""

from __future__ import annotations

from typing import Any

from ageval.config.errors import ConfigError


def dataset_identity(doc: Any, *, location: str) -> tuple[str, str]:
    """``dataset_id`` + ``dataset_version`` from lock.json or suite summary.json."""
    if not isinstance(doc, dict):
        raise ConfigError(
            "invalid_schema",
            "missing dataset_id@version",
            location=location,
        )
    dataset_id = doc.get("dataset_id")
    dataset_version = doc.get("dataset_version")
    if (
        not isinstance(dataset_id, str)
        or not dataset_id.strip()
        or not isinstance(dataset_version, str)
        or not dataset_version.strip()
    ):
        raise ConfigError(
            "invalid_schema",
            "missing dataset_id@version",
            location=location,
        )
    return dataset_id.strip(), dataset_version.strip()


def dataset_ref(dataset_id: str, dataset_version: str) -> str:
    return f"{dataset_id}@{dataset_version}"
