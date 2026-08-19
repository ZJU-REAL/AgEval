"""Workspace plan validation tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from ageval.provider.errors import ProviderError
from ageval.provider.workspace_plan import WorkspacePlan
from ageval.runtime.identity import IdentityFactory


def _attempt():
    f = IdentityFactory()
    run = f.new_run()
    trial = f.new_trial(run, "sha256:" + "a" * 64)
    return f.new_attempt(trial)


def test_resolve_workdir(tmp_path: Path) -> None:
    plan = WorkspacePlan(attempt=_attempt(), base_dir=tmp_path, relative_workdir="ws")
    wd = plan.resolve_workdir()
    assert wd.parent == tmp_path.resolve()
    assert wd.name == "ws"


def test_escape_rejected(tmp_path: Path) -> None:
    plan = WorkspacePlan(attempt=_attempt(), base_dir=tmp_path, relative_workdir="../x")
    with pytest.raises(ProviderError) as ei:
        plan.resolve_workdir()
    assert ei.value.error_code == "outside_workdir"
