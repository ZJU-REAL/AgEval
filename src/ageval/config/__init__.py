"""Config Core: Dataset resolve + load_and_lock → immutable LockedTaskConfig."""

from ageval.config.dataset import (
    DatasetManifest,
    ResolvedTask,
    list_tasks,
    load_dataset_manifest,
    member_paths_for_digest,
    resolve_task,
)
from ageval.config.errors import ConfigError
from ageval.config.load_and_lock import ConfigCore
from ageval.config.model import LockedTaskConfig, LockSummary
from ageval.config.shared import validate_shared_layout

__all__ = [
    "ConfigCore",
    "ConfigError",
    "DatasetManifest",
    "LockSummary",
    "LockedTaskConfig",
    "ResolvedTask",
    "list_tasks",
    "load_dataset_manifest",
    "member_paths_for_digest",
    "resolve_task",
    "validate_shared_layout",
]
