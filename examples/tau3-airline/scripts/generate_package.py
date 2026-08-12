#!/usr/bin/env python3
"""Generate BORA task members from upstream airline tasks.json (shared.lib.*)."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TASKS_JSON = ROOT / "shared" / "assets" / "tasks.json"
TASKS_DIR = ROOT / "tasks"
POLICY = ROOT / "shared" / "assets" / "policy.md"

TASK_YAML = """\
format: bora.task/1
task_id: {task_id}
provenance:
  kind: port
  upstream:
    name: tau2-bench
    url: https://github.com/sierra-research/tau2-bench
    ref: v1.0.1
    commit: fc0055dc4e0a316c3f83133267fbd6faaa770992
    task_id: "{upstream_id}"
    paper: https://arxiv.org/abs/2506.07982
  parity:
    claims:
      - protocol
      - scoring
    known_gaps:
      - "BORA ACP dual-agent loop; not tau2 litellm runner"
      - "Host must provide tau2==1.0.1 for tools/DB when package-local data omitted"
harness:
  runtime: python
  entrypoint: harness:run
parameters:
  upstream_task_id: "{upstream_id}"
  harness_timeout_seconds: 1200
  max_user_turns: 12
  max_service_steps: 40
  roles:
    user: user
    service: service
  models:
    default: service
provider:
  kind: local
  assurance: l0
agent_profiles:
  - id: user
  - id: service
limits:
  wall_time_seconds: 1200
  agent_invocations: 80
  environment_actions: 0
artifacts:
  publishable:
    - id: simulation
      producer: harness
      path: artifacts/simulation.json
      media_type: application/json
evaluation:
  runtime: python
  entrypoint: evaluator:evaluate
  network: none
  inputs:
    - artifact: simulation
      target: artifacts/simulation.json
  output:
    format: json
"""

HARNESS_PY = '''\
"""Thin task entry — orchestration in Dataset shared/lib (#65)."""

from __future__ import annotations

from pathlib import Path

from bora_sdk import HarnessContext, HarnessTerminal
from shared.lib.harness_core import run as _run

_TASK = Path(__file__).resolve().parent
UPSTREAM_TASK_ID = "{upstream_id}"


async def run(ctx: HarnessContext) -> HarnessTerminal:
    view = ctx.params
    if hasattr(view, "as_mapping"):
        data = dict(view.as_mapping())
        if not data.get("upstream_task_id"):
            data["upstream_task_id"] = UPSTREAM_TASK_ID

            class _P:
                def as_mapping(self):
                    return data

                def get(self, path, default=None):
                    cur = data
                    for part in str(path).split("."):
                        if not isinstance(cur, dict) or part not in cur:
                            return default
                        cur = cur[part]
                    return cur

            ctx.params = _P()  # type: ignore[misc]
    return await _run(ctx, task_dir=_TASK)
'''

EVALUATOR_PY = '''\
"""Thin task evaluator — scoring in Dataset shared/lib (#65)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from shared.lib.evaluator_core import evaluate as _evaluate

_TASK = Path(__file__).resolve().parent
UPSTREAM_TASK_ID = "{upstream_id}"


def evaluate(inputs: dict[str, Any]) -> dict[str, Any]:
    return _evaluate(
        inputs,
        task_dir=_TASK,
        upstream_task_id=UPSTREAM_TASK_ID,
    )
'''


def member_id(upstream_id: str) -> str:
    if re.fullmatch(r"\d+", upstream_id):
        return f"airline-{int(upstream_id):02d}"
    safe = re.sub(r"[^a-zA-Z0-9_-]+", "-", upstream_id).strip("-").lower()
    return f"airline-{safe}"


def generate(ids: list[str] | None, all_tasks: bool) -> None:
    tasks = json.loads(TASKS_JSON.read_text(encoding="utf-8"))
    by_id = {str(t["id"]): t for t in tasks}
    if all_tasks:
        selected = [str(t["id"]) for t in tasks]
    else:
        selected = [str(i) for i in (ids or [])]
        missing = [i for i in selected if i not in by_id]
        if missing:
            raise SystemExit(f"unknown task ids: {missing}")

    TASKS_DIR.mkdir(parents=True, exist_ok=True)
    for uid in selected:
        mid = member_id(uid)
        tdir = TASKS_DIR / mid
        (tdir / "data").mkdir(parents=True, exist_ok=True)
        (tdir / "evaluation").mkdir(parents=True, exist_ok=True)
        task = by_id[uid]
        (tdir / "data" / "user_scenario.json").write_text(
            json.dumps(task.get("user_scenario") or {}, indent=2, ensure_ascii=False)
            + "\n",
            encoding="utf-8",
        )
        if POLICY.is_file():
            (tdir / "data" / "policy.md").write_text(
                POLICY.read_text(encoding="utf-8"),
                encoding="utf-8",
            )
        (tdir / "evaluation" / "task.json").write_text(
            json.dumps(task, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        (tdir / "task.yaml").write_text(
            TASK_YAML.format(task_id=mid, upstream_id=uid),
            encoding="utf-8",
        )
        (tdir / "harness.py").write_text(
            HARNESS_PY.format(upstream_id=uid), encoding="utf-8"
        )
        (tdir / "evaluator.py").write_text(
            EVALUATOR_PY.format(upstream_id=uid), encoding="utf-8"
        )
        # No per-task lib/ — Database root on path; thin entries import shared.lib.*.
        purpose = ""
        desc = task.get("description")
        if isinstance(desc, dict):
            purpose = str(desc.get("purpose") or "")[:200]
        (tdir / "README.md").write_text(
            f"# {mid}\n\nUpstream task id: `{uid}`\n\n{purpose}\n",
            encoding="utf-8",
        )
        print(f"wrote {mid} (upstream {uid})")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--ids", type=str, default="")
    p.add_argument("--all", action="store_true")
    args = p.parse_args()
    ids = [x.strip() for x in args.ids.split(",") if x.strip()] if args.ids else []
    if not args.all and not ids:
        raise SystemExit("pass --ids 0,1,2 or --all")
    generate(ids, args.all)


if __name__ == "__main__":
    main()
