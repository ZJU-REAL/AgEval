"""Boxes for tests, built the way the engine builds them."""

from __future__ import annotations

from pathlib import Path

from ageval.environments.protocol import BoxSpec
from ageval.plugins.contrib.local.host import LocalHost


def box_spec(attempt_root: Path | str, *, task_root: Path | str | None = None) -> BoxSpec:
    root = Path(str(attempt_root))
    task = Path(str(task_root)) if task_root is not None else root
    return BoxSpec(attempt_root=root, task_root=task, repo_root=Path.cwd())


def local_box(attempt_root: Path | str, *, task_root: Path | str | None = None) -> LocalHost:
    return LocalHost(spec=box_spec(attempt_root, task_root=task_root))
