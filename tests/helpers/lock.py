"""Lock a fixture task the way the production use case does."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ageval.config.capabilities import DeclarationCapabilityCatalog
from ageval.config.dataset import load_dataset_manifest
from ageval.config.load_and_lock import ConfigCore
from ageval.config.model import LockedTaskConfig
from ageval.config.package_fs import LocalPackageReader
from ageval.config.profiles import JobDocument, parse_job_mapping, resolve_job_document

REPO = Path(__file__).resolve().parents[2]
FIXTURES = REPO / "tests" / "fixtures" / "datasets"
CONFIG_MIN = FIXTURES / "config-min"


def job_document(
    profiles: dict[str, dict[str, Any]],
    *,
    environment: str = "local",
    environment_options: dict[str, Any] | None = None,
    evaluate_host: dict[str, Any] | None = None,
) -> JobDocument:
    """A job document from an inline profile mapping."""
    raw: dict[str, Any] = {
        "format": "ageval.profiles/1",
        "environment": environment,
        "agent_profiles": profiles,
    }
    if environment_options:
        raw["environment_options"] = environment_options
    if evaluate_host:
        raw["evaluate_host"] = evaluate_host
    return parse_job_mapping(raw)


def lock_task(
    dataset_root: Path,
    task_id: str,
    *,
    job: JobDocument | None = None,
    profiles_path: Path | None = None,
    **kwargs: Any,
) -> LockedTaskConfig:
    """Lock one member task of a fixture dataset."""
    manifest = load_dataset_manifest(dataset_root)
    return ConfigCore(package_reader=LocalPackageReader()).load_and_lock(
        dataset_root / manifest.tasks_root / task_id,
        task_id,
        dataset_id=manifest.dataset_id,
        dataset_version=manifest.version,
        job=job or resolve_job_document(dataset_root, profiles_path=profiles_path),
        capabilities=DeclarationCapabilityCatalog(),
        **kwargs,
    )


def lock_standalone(
    task_root: Path,
    task_id: str,
    *,
    job: JobDocument,
    dataset_id: str = "test/standalone",
    dataset_version: str = "0.1.0",
    **kwargs: Any,
) -> LockedTaskConfig:
    """Lock a task directory written by the test itself (no dataset root)."""
    return ConfigCore(package_reader=LocalPackageReader()).load_and_lock(
        task_root,
        task_id,
        dataset_id=dataset_id,
        dataset_version=dataset_version,
        job=job,
        capabilities=DeclarationCapabilityCatalog(),
        **kwargs,
    )


def lock_with_profiles(
    task_root: Path,
    task_id: str,
    profiles: dict[str, dict[str, Any]],
    *,
    environment: str = "local",
    **kwargs: Any,
) -> LockedTaskConfig:
    """Lock a self-written task against an inline profile mapping."""
    return lock_standalone(
        task_root,
        task_id,
        job=job_document(profiles, environment=environment),
        **kwargs,
    )
