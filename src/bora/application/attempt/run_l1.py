"""Full L1 Attempt orchestration (Spec 07).

Containment rules:
- Harness container: network none, filtered package (no evaluation/), no credentials.
- Agent Executor container: optional bridge network + credential projection only;
  workspace-only write; filtered package; never evaluation/.
- Clean evaluator container: staging only, no package mount, no creds;
  network from evaluation.network (omit ≡ none).
- assurance:l1 only when harness + agent (if any) + evaluator writers confirmed and
  isolation probes pass.

Helpers live in sibling modules: prepare · evaluator · evidence (chore #31).
"""

from __future__ import annotations

import contextlib
import shutil
from pathlib import Path
from typing import Any


def _database_root_for_run(run_dir: Path) -> Path | None:
    """Infer Database root when run_dir is ``…/.bora/runs/<run_id>``."""
    from bora.evidence.attempt_record import infer_database_root_from_run_dir

    return infer_database_root_from_run_dir(run_dir)


def drop_l1_work(run_dir: Path, *, keep_workspace: bool = False) -> None:
    """Remove host sandbox residual at ``run_dir/l1-work`` unless retained for debug.

    Layout stays under the run dir during the Attempt; default policy is curated
    Hub-facing evidence only — full workspace / package_view are not retained.
    """
    if keep_workspace:
        return
    work = Path(run_dir) / "l1-work"
    if work.exists():
        with contextlib.suppress(OSError):
            shutil.rmtree(work)


def _l1_host_cleanup(
    docker: Any,
    runtime: Any,
    cred: Any | None,
    run_dir: Path,
    *,
    keep_workspace: bool,
) -> None:
    """Stop containers/networks, drop credentials, then drop host ``l1-work``.

    Idempotent: ``DockerProvider.cleanup`` no-ops when ``runtime.cleaned``;
    a second call (Coordinator + leftover path) must not raise on ``docker rm``.
    Missing handles are a no-op so stages can run cleanup before prepare.
    """
    if docker is not None and runtime is not None:
        with contextlib.suppress(Exception):
            docker.cleanup(runtime)
    if cred is not None:
        with contextlib.suppress(Exception):
            cred.cleanup()
    drop_l1_work(run_dir, keep_workspace=keep_workspace)
