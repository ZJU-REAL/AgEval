"""Full L1 Attempt orchestration (Spec 07).

Containment rules:
- Harness container: network none, filtered package (no evaluation/), no credentials.
- Agent Executor container: optional bridge network + credential projection only;
  workspace-only write; filtered package; never evaluation/.
- Clean evaluator container: staging only, network none, no package mount, no creds.
- assurance:l1 only when harness + agent (if any) + evaluator writers confirmed and
  isolation probes pass.

Helpers live in sibling modules: prepare · evaluator · evidence (chore #31).
"""

from __future__ import annotations

import contextlib
import shutil
from pathlib import Path
from typing import Any

from bora.application.run_l1_evidence import l1_error_result
from bora.runtime.identity import AttemptIdentity


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


async def run_l1_attempt(
    *,
    package_root: Path,
    lock: Any,
    run_dir: Path,
    agent_meta: dict[str, Any],
    allow_offline_agent: bool,
    keep_workspace: bool = False,
    attempt: AttemptIdentity | None = None,
    stage_ctx: Any | None = None,
) -> tuple[int, dict[str, Any], dict[str, Any]]:
    """Dispatch L1 SDK session path when agent_profiles is non-empty.

    Isolation (hidden gold, credential/network projection, writer-stop) is enforced
    by Provider prepare/run and the SDK session barrier — not by Application
    task_id/probe special cases. Provider contract tests live under tests/provider_l1/.
    """
    del package_root, allow_offline_agent, keep_workspace, attempt, stage_ctx
    task_id = str(lock.task_id)
    return l1_error_result(
        run_dir,
        "config",
        {"error": "l1_dispatch_unsupported", "task_id": task_id},
        agent_meta,
        0,
        kind="l1_dispatch_unsupported",
    )
