"""Attempt / trial evidence APIs for the local viewer (issue #26).

Resolves ``run_id`` → evidence root under the opened Database sandox and exposes
read-only meta, file tree, file preview, and trajectory steps. Tabs are derived
from files that exist — never fabricated. Trajectory is observational, not PASS.
"""

from __future__ import annotations

import contextlib
import json
import mimetypes
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs

from bora.config.database import load_database_manifest
from bora.config.errors import ConfigError
from bora.viewer.browse import commands_for
from bora.viewer.jobs import get_job, get_job_task

# Preview / enumeration caps (operator-facing local tool, not bulk export).
MAX_FILE_BYTES = 512 * 1024
MAX_TREE_ENTRIES = 800
MAX_TRAJECTORY_STEPS = 2_000
MAX_JSONL_LINE = 256 * 1024

_TEXT_SUFFIXES = {
    ".json",
    ".jsonl",
    ".txt",
    ".md",
    ".yaml",
    ".yml",
    ".toml",
    ".py",
    ".sh",
    ".log",
    ".csv",
    ".tsv",
    ".xml",
    ".html",
    ".css",
    ".js",
    ".ts",
    ".tsx",
    ".jsx",
    ".env",
    ".ini",
    ".cfg",
    ".conf",
}


def _safe_run_id(run_id: str) -> str:
    rid = (run_id or "").strip()
    if not rid or rid in {".", ".."} or "/" in rid or "\\" in rid or ".." in rid:
        raise ConfigError(
            "invalid_package",
            f"invalid run_id: {run_id!r}",
            location="run_id",
        )
    return rid


def _safe_under(root: Path, relative: str) -> Path:
    """Resolve *relative* under *root*; reject traversal and escape."""
    if not relative or relative.startswith(("/", "\\")):
        raise ConfigError(
            "invalid_package",
            "path must be relative",
            location=relative or ".",
        )
    parts = Path(relative).parts
    if ".." in parts:
        raise ConfigError(
            "invalid_package",
            "path traversal rejected",
            location=relative,
        )
    root_resolved = root.resolve(strict=False)
    candidate = (root / relative).resolve(strict=False)
    try:
        candidate.relative_to(root_resolved)
    except ValueError as exc:
        raise ConfigError(
            "invalid_package",
            "path escapes sandbox",
            location=relative,
        ) from exc
    return candidate


def _read_json_object(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None
    return data if isinstance(data, dict) else None


def resolve_evidence_root(
    database_root: Path,
    run_id: str,
    *,
    task_id: str | None = None,
) -> Path:
    """Locate Attempt evidence for *run_id* under the Database root sandbox.

    Lookup order:
    1. ``{database}/.bora/runs/{run_id}``
    2. ``{database}/{tasks_root}/{task_id}/.bora/runs/{run_id}`` when task_id given
    3. Scan ``{database}/**/ .bora/runs/{run_id}`` (depth-limited)
    """
    root = database_root.expanduser().resolve(strict=False)
    rid = _safe_run_id(run_id)

    primary = root / ".bora" / "runs" / rid
    if primary.is_dir():
        return primary

    tasks_root_name = "tasks"
    with contextlib.suppress(ConfigError):
        man = load_database_manifest(root)
        tasks_root_name = man.tasks_root or "tasks"

    if task_id:
        tid = task_id.strip()
        if tid and ".." not in tid and "/" not in tid and "\\" not in tid:
            task_local = root / tasks_root_name / tid / ".bora" / "runs" / rid
            if task_local.is_dir():
                return task_local

    # Bounded scan: only under tasks/*/.bora/runs and root .bora/runs (already checked).
    tasks_dir = root / tasks_root_name
    if tasks_dir.is_dir():
        for child in tasks_dir.iterdir():
            if not child.is_dir():
                continue
            cand = child / ".bora" / "runs" / rid
            if cand.is_dir():
                return cand

    raise ConfigError(
        "unknown_task",
        f"evidence root not found for run_id={rid!r}",
        location=str(primary),
    )


def _has_any_file(path: Path) -> bool:
    if not path.exists():
        return False
    if path.is_file():
        return True
    try:
        for p in path.rglob("*"):
            if p.is_file():
                return True
    except OSError:
        return False
    return False


def _available_tabs(evidence: Path) -> list[str]:
    tabs: list[str] = []
    # Trajectory: any trajectory.jsonl under agent/invocations
    inv = evidence / "agent" / "invocations"
    has_traj = False
    if inv.is_dir():
        try:
            has_traj = any(p.name == "trajectory.jsonl" for p in inv.rglob("trajectory.jsonl"))
        except OSError:
            has_traj = False
    if has_traj:
        tabs.append("trajectory")
    if (evidence / "agent").is_dir() and _has_any_file(evidence / "agent"):
        tabs.append("agent")
    if (
        _has_any_file(evidence / "evaluation")
        or _has_any_file(evidence / "eval_staging")
        or (evidence / "result.json").is_file()
    ):
        tabs.append("verifier")
    # Artifacts: harness publish tree or common artifact dirs
    art_candidates = [
        evidence / "harness",
        evidence / "artifacts",
        evidence / "agent" / "artifacts",
    ]
    # Prefer a dedicated tab only when files exist under artifact-ish trees
    if any(
        p.is_dir() and any(x.is_file() for x in p.rglob("*") if x.is_file())
        for p in art_candidates
        if p.exists()
    ):
        tabs.append("artifacts")
    if (evidence / "lock.json").is_file():
        tabs.append("lock")
    if (
        (evidence / "effects.jsonl").is_file()
        or (evidence / "cleanup.json").is_file()
        or (evidence / "summary.json").is_file()
    ):
        tabs.append("log")
    return tabs


def _trial_meta_from_evidence(
    evidence: Path,
    *,
    run_id: str,
    task_id: str | None,
    suite_row: dict[str, Any] | None = None,
) -> dict[str, Any]:
    result = _read_json_object(evidence / "result.json") or {}
    summary = _read_json_object(evidence / "summary.json") or {}
    lock = _read_json_object(evidence / "lock.json") or {}
    suite_row = suite_row or {}

    status = suite_row.get("status") or result.get("status") or summary.get("status") or None
    if isinstance(status, str):
        status = status.upper()
    score = suite_row.get("score")
    if score is None:
        score = result.get("score")
    if score is None:
        score = summary.get("score")
    error = suite_row.get("error") or result.get("error") or summary.get("error")
    locked_task = lock.get("task_id") if isinstance(lock.get("task_id"), str) else None

    return {
        "trial_id": run_id,
        "run_id": run_id,
        "task_id": task_id or locked_task or suite_row.get("task_id"),
        "status": status,
        "score": score,
        "reward": score,
        "error": error,
        "exit_code": suite_row.get("exit_code") or result.get("exit_code"),
        "duration": suite_row.get("duration"),
        "started": summary.get("started_at") or suite_row.get("started"),
        "evidence_relpath": None,  # filled by caller
        "has_evidence": True,
        "available_tabs": _available_tabs(evidence),
        "agent_invocations": result.get("agent_invocations") or summary.get("agent_invocations"),
        "harness_kind": result.get("harness_kind") or summary.get("harness_kind"),
        "note": "trajectory and harness status are not PASS; PASS is per-task evaluator only",
    }


def list_task_trials(
    database_root: Path,
    job_id: str,
    task_id: str,
) -> dict[str, Any]:
    """List trials for a task within a suite job, enriched with local evidence when present."""
    root = database_root.expanduser().resolve(strict=False)
    task_payload = get_job_task(root, job_id, task_id)
    job = task_payload["job"]
    suite_trials = list(task_payload.get("trials") or [])

    by_run: dict[str, dict[str, Any]] = {}
    for tr in suite_trials:
        rid = tr.get("run_id") or tr.get("trial_id")
        if not rid:
            continue
        rid_s = str(rid)
        by_run[rid_s] = {
            "trial_id": rid_s,
            "run_id": rid_s,
            "task_id": task_id,
            "status": tr.get("status"),
            "score": tr.get("score") if tr.get("score") is not None else tr.get("reward"),
            "reward": tr.get("reward") if tr.get("reward") is not None else tr.get("score"),
            "error": tr.get("error"),
            "exit_code": tr.get("exit_code"),
            "duration": tr.get("duration"),
            "started": tr.get("started") or job.get("started"),
            "has_evidence": False,
            "available_tabs": [],
            "note": "from suite summary",
        }

    # Scan database-level and task-local runs matching this task_id via lock.json
    candidates: list[Path] = []
    db_runs = root / ".bora" / "runs"
    if db_runs.is_dir():
        candidates.extend(p for p in db_runs.iterdir() if p.is_dir())
    tasks_root_name = "tasks"
    with contextlib.suppress(ConfigError):
        man = load_database_manifest(root)
        tasks_root_name = man.tasks_root or "tasks"
    task_runs = root / tasks_root_name / task_id / ".bora" / "runs"
    if task_runs.is_dir():
        candidates.extend(p for p in task_runs.iterdir() if p.is_dir())

    for run_dir in candidates:
        rid = run_dir.name
        lock = _read_json_object(run_dir / "lock.json") or {}
        locked_task = lock.get("task_id")
        # Enrich suite-listed runs always; only *add* new runs when lock matches task.
        if rid not in by_run and locked_task != task_id:
            continue
        suite_row = by_run.get(rid, {})
        meta = _trial_meta_from_evidence(
            run_dir,
            run_id=rid,
            task_id=task_id,
            suite_row=suite_row,
        )
        try:
            rel = str(run_dir.resolve(strict=False).relative_to(root))
        except ValueError:
            rel = str(run_dir)
        meta["evidence_relpath"] = rel
        meta["started"] = meta.get("started") or suite_row.get("started") or job.get("started")
        by_run[rid] = meta

    trials = sorted(
        by_run.values(),
        key=lambda t: (t.get("started") or "", t.get("run_id") or ""),
        reverse=True,
    )
    cmds = commands_for(root, task_id=task_id)
    return {
        "ok": True,
        "job": job,
        "task": task_payload["task"],
        "trials": trials,
        "count": len(trials),
        "commands": cmds,
        "run_command": cmds.get("run_task") or cmds.get("run_suite"),
        "breadcrumb": [
            {"label": "Jobs", "href": "/"},
            {"label": job_id, "href": f"/jobs/{job_id}"},
            {"label": task_id, "href": f"/jobs/{job_id}/tasks/{task_id}"},
            {"label": "trials", "href": None},
        ],
        "note": "per-task evaluator verdicts only; trajectory is not PASS",
    }


def get_trial(
    database_root: Path,
    job_id: str,
    task_id: str,
    run_id: str,
) -> dict[str, Any]:
    root = database_root.expanduser().resolve(strict=False)
    rid = _safe_run_id(run_id)
    job_payload = get_job(root, job_id)
    job = job_payload["job"]
    suite_row: dict[str, Any] = {}
    for row in job_payload.get("tasks") or []:
        if row.get("task_id") == task_id and str(row.get("run_id") or "") == rid:
            suite_row = row
            break

    evidence = resolve_evidence_root(root, rid, task_id=task_id)
    meta = _trial_meta_from_evidence(evidence, run_id=rid, task_id=task_id, suite_row=suite_row)
    try:
        meta["evidence_relpath"] = str(evidence.resolve(strict=False).relative_to(root))
    except ValueError:
        meta["evidence_relpath"] = str(evidence)

    # Sibling runs for prev/next navigation
    listed = list_task_trials(root, job_id, task_id)
    sibling_ids = [str(t.get("run_id")) for t in listed["trials"] if t.get("run_id")]
    try:
        idx = sibling_ids.index(rid)
    except ValueError:
        idx = -1
    prev_id = sibling_ids[idx - 1] if idx > 0 else None
    next_id = sibling_ids[idx + 1] if 0 <= idx < len(sibling_ids) - 1 else None

    cmds = commands_for(root, task_id=task_id)
    result_preview = _read_json_object(evidence / "result.json")
    # Strip huge nested blobs if any
    if result_preview and "metrics" in result_preview:
        metrics = result_preview.get("metrics")
        if isinstance(metrics, dict) and len(json.dumps(metrics)) > 8_000:
            result_preview = {**result_preview, "metrics": {"_truncated": True}}

    return {
        "ok": True,
        "job": job,
        "task_id": task_id,
        "trial": meta,
        "result": result_preview,
        "prev_run_id": prev_id,
        "next_run_id": next_id,
        "sibling_run_ids": sibling_ids,
        "commands": cmds,
        "run_command": cmds.get("run_task") or cmds.get("run_suite"),
        "breadcrumb": [
            {"label": "Jobs", "href": "/"},
            {"label": job_id, "href": f"/jobs/{job_id}"},
            {"label": task_id, "href": f"/jobs/{job_id}/tasks/{task_id}"},
            {"label": rid, "href": None},
        ],
        "note": meta.get("note"),
    }


def _scope_base(evidence: Path, scope: str) -> Path:
    scope = (scope or "root").strip().lower()
    mapping = {
        "root": evidence,
        "agent": evidence / "agent",
        "eval": evidence / "evaluation",
        "evaluation": evidence / "evaluation",
        "verifier": evidence / "evaluation",
        "artifacts": evidence / "harness",
        "harness": evidence / "harness",
        "lock": evidence,  # single file handled by caller
    }
    if scope not in mapping:
        raise ConfigError(
            "invalid_package",
            f"unknown tree scope: {scope!r}",
            location="scope",
        )
    return mapping[scope]


def trial_tree(
    database_root: Path,
    job_id: str,  # noqa: ARG001 — reserved for auth/scoping consistency
    task_id: str,
    run_id: str,
    *,
    scope: str = "root",
) -> dict[str, Any]:
    root = database_root.expanduser().resolve(strict=False)
    rid = _safe_run_id(run_id)
    evidence = resolve_evidence_root(root, rid, task_id=task_id)
    scope_norm = (scope or "root").strip().lower()

    # Special multi-root scopes for verifier
    if scope_norm in {"verifier", "eval", "evaluation"}:
        entries: list[dict[str, Any]] = []
        for sub in (
            evidence / "evaluation",
            evidence / "eval_staging",
            evidence / "result.json",
        ):
            if sub.is_file():
                st = sub.stat()
                rel = sub.name if sub.parent == evidence else str(sub.relative_to(evidence))
                entries.append(
                    {
                        "path": rel,
                        "name": sub.name,
                        "type": "file",
                        "size": st.st_size,
                    }
                )
            elif sub.is_dir():
                remain = MAX_TREE_ENTRIES - len(entries)
                entries.extend(_walk_tree(evidence, sub, max_entries=remain))
        return {
            "ok": True,
            "run_id": rid,
            "scope": "verifier",
            "entries": entries[:MAX_TREE_ENTRIES],
            "truncated": len(entries) > MAX_TREE_ENTRIES,
        }

    if scope_norm == "artifacts":
        entries = []
        for sub_name in ("harness", "artifacts"):
            sub = evidence / sub_name
            if sub.is_dir():
                entries.extend(
                    _walk_tree(evidence, sub, max_entries=MAX_TREE_ENTRIES - len(entries))
                )
        return {
            "ok": True,
            "run_id": rid,
            "scope": "artifacts",
            "entries": entries[:MAX_TREE_ENTRIES],
            "truncated": len(entries) > MAX_TREE_ENTRIES,
        }

    if scope_norm == "lock":
        lock_path = evidence / "lock.json"
        entries = []
        if lock_path.is_file():
            entries.append(
                {
                    "path": "lock.json",
                    "name": "lock.json",
                    "type": "file",
                    "size": lock_path.stat().st_size,
                }
            )
        return {"ok": True, "run_id": rid, "scope": "lock", "entries": entries, "truncated": False}

    if scope_norm == "log":
        entries = []
        for name in ("effects.jsonl", "cleanup.json", "summary.json", "agent.json", "harness.json"):
            p = evidence / name
            if p.is_file():
                entries.append(
                    {
                        "path": name,
                        "name": name,
                        "type": "file",
                        "size": p.stat().st_size,
                    }
                )
        return {"ok": True, "run_id": rid, "scope": "log", "entries": entries, "truncated": False}

    base = _scope_base(evidence, scope_norm)
    if not base.exists():
        return {
            "ok": True,
            "run_id": rid,
            "scope": scope_norm,
            "entries": [],
            "truncated": False,
            "note": f"no files under scope {scope_norm!r}",
        }
    if base.is_file():
        entries = [
            {
                "path": str(base.relative_to(evidence)),
                "name": base.name,
                "type": "file",
                "size": base.stat().st_size,
            }
        ]
    else:
        entries = _walk_tree(evidence, base, max_entries=MAX_TREE_ENTRIES)
    return {
        "ok": True,
        "run_id": rid,
        "scope": scope_norm,
        "entries": entries,
        "truncated": len(entries) >= MAX_TREE_ENTRIES,
    }


def _walk_tree(evidence: Path, base: Path, *, max_entries: int) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if max_entries <= 0:
        return out
    try:
        paths = sorted(base.rglob("*"), key=lambda p: str(p).lower())
    except OSError:
        return out
    for p in paths:
        if len(out) >= max_entries:
            break
        try:
            rel = str(p.relative_to(evidence))
            if p.is_dir():
                out.append({"path": rel, "name": p.name, "type": "dir", "size": None})
            elif p.is_file():
                out.append(
                    {
                        "path": rel,
                        "name": p.name,
                        "type": "file",
                        "size": p.stat().st_size,
                    }
                )
        except (OSError, ValueError):
            continue
    return out


def trial_file(
    database_root: Path,
    job_id: str,  # noqa: ARG001
    task_id: str,
    run_id: str,
    *,
    relpath: str,
) -> dict[str, Any]:
    root = database_root.expanduser().resolve(strict=False)
    rid = _safe_run_id(run_id)
    evidence = resolve_evidence_root(root, rid, task_id=task_id)
    path = _safe_under(evidence, relpath)
    if not path.is_file():
        raise ConfigError(
            "unknown_task",
            f"file not found: {relpath}",
            location=relpath,
        )
    size = path.stat().st_size
    mime, _ = mimetypes.guess_type(str(path))
    mime = mime or "application/octet-stream"
    suffix = path.suffix.lower()
    is_text = (
        suffix in _TEXT_SUFFIXES
        or mime.startswith("text/")
        or mime in {"application/json", "application/xml", "application/x-yaml"}
    )
    if not is_text:
        return {
            "ok": True,
            "run_id": rid,
            "path": relpath,
            "name": path.name,
            "size": size,
            "media_type": mime,
            "encoding": "binary",
            "truncated": False,
            "content": None,
            "note": "binary file; preview not shown",
        }
    if size > MAX_FILE_BYTES:
        raw = path.read_bytes()[:MAX_FILE_BYTES]
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            text = raw.decode("utf-8", errors="replace")
        return {
            "ok": True,
            "run_id": rid,
            "path": relpath,
            "name": path.name,
            "size": size,
            "media_type": mime,
            "encoding": "utf-8",
            "truncated": True,
            "content": text,
            "note": f"truncated to first {MAX_FILE_BYTES} bytes",
        }
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        text = path.read_text(encoding="utf-8", errors="replace")
    return {
        "ok": True,
        "run_id": rid,
        "path": relpath,
        "name": path.name,
        "size": size,
        "media_type": mime,
        "encoding": "utf-8",
        "truncated": False,
        "content": text,
    }


def trial_trajectory(
    database_root: Path,
    job_id: str,  # noqa: ARG001
    task_id: str,
    run_id: str,
) -> dict[str, Any]:
    root = database_root.expanduser().resolve(strict=False)
    rid = _safe_run_id(run_id)
    evidence = resolve_evidence_root(root, rid, task_id=task_id)
    inv_root = evidence / "agent" / "invocations"
    steps: list[dict[str, Any]] = []
    invocations: list[dict[str, Any]] = []
    truncated = False

    if inv_root.is_dir():
        inv_dirs = sorted(
            [p for p in inv_root.iterdir() if p.is_dir()],
            key=lambda p: p.name,
        )
        for inv in inv_dirs:
            inv_meta = _read_json_object(inv / "metadata.json") or {}
            traj_path = inv / "trajectory.jsonl"
            inv_steps: list[dict[str, Any]] = []
            if traj_path.is_file():
                inv_steps = _parse_trajectory_jsonl(traj_path)
            for step in inv_steps:
                if len(steps) >= MAX_TRAJECTORY_STEPS:
                    truncated = True
                    break
                steps.append(
                    {
                        **step,
                        "invocation": inv.name,
                        "invocation_id": inv_meta.get("invocation_id") or inv.name,
                    }
                )
            invocations.append(
                {
                    "dirname": inv.name,
                    "invocation_id": inv_meta.get("invocation_id") or inv.name,
                    "profile_id": inv_meta.get("profile_id"),
                    "executor_kind": inv_meta.get("executor_kind"),
                    "model": inv_meta.get("model") or inv_meta.get("locked_model"),
                    "status": inv_meta.get("status"),
                    "step_count": len(inv_steps),
                    "has_trajectory": traj_path.is_file(),
                }
            )
            if truncated:
                break

    return {
        "ok": True,
        "run_id": rid,
        "task_id": task_id,
        "steps": steps,
        "step_count": len(steps),
        "invocations": invocations,
        "truncated": truncated,
        "note": "trajectory is observational evidence; not PASS",
    }


def _parse_trajectory_jsonl(path: Path) -> list[dict[str, Any]]:
    steps: list[dict[str, Any]] = []
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            for line_no, line in enumerate(fh, start=1):
                if len(steps) >= MAX_TRAJECTORY_STEPS:
                    break
                raw = line.strip()
                if not raw:
                    continue
                if len(raw) > MAX_JSONL_LINE:
                    raw = raw[:MAX_JSONL_LINE]
                try:
                    obj = json.loads(raw)
                except json.JSONDecodeError:
                    steps.append(
                        {
                            "type": "parse_error",
                            "line": line_no,
                            "content": raw[:500],
                        }
                    )
                    continue
                if not isinstance(obj, dict):
                    steps.append({"type": "raw", "line": line_no, "content": str(obj)[:500]})
                    continue
                role = obj.get("role")
                step_type = obj.get("type") or ("turn" if role else "event")
                content = obj.get("content")
                if content is not None and not isinstance(content, str):
                    try:
                        content = json.dumps(content, ensure_ascii=False)
                    except (TypeError, ValueError):
                        content = str(content)
                if isinstance(content, str) and len(content) > 8_000:
                    content = content[:8_000] + "…[truncated]"
                steps.append(
                    {
                        "type": step_type,
                        "role": role,
                        "content": content,
                        "turn_index": obj.get("turn_index"),
                        "source": obj.get("source"),
                        "stop_reason": obj.get("stop_reason"),
                        "ok": obj.get("ok"),
                        "error": obj.get("error"),
                        "usage": obj.get("usage") if isinstance(obj.get("usage"), dict) else None,
                        "metadata": obj.get("metadata")
                        if isinstance(obj.get("metadata"), dict)
                        else None,
                        "line": line_no,
                    }
                )
    except OSError:
        return steps
    return steps


def parse_query(query: str) -> dict[str, str]:
    """Parse URL query string into first-value map."""
    qs = parse_qs(query or "", keep_blank_values=False)
    return {k: v[0] for k, v in qs.items() if v}
