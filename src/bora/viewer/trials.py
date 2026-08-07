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
from bora.viewer.jobs import get_job, get_job_task, safe_id_segment

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
    ".ini",
    ".cfg",
    ".conf",
}


def _safe_run_id(run_id: str) -> str:
    return safe_id_segment(run_id, field="run_id")


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


def _assert_under_database(root: Path, path: Path, *, location: str) -> Path:
    """Resolve *path* and ensure it stays under Database *root*."""
    root_r = root.resolve(strict=False)
    cand = path.resolve(strict=False)
    try:
        cand.relative_to(root_r)
    except ValueError as exc:
        raise ConfigError(
            "invalid_package",
            "path escapes database sandbox",
            location=location,
        ) from exc
    return cand


def _evidence_matches_task(evidence: Path, task_id: str | None) -> bool:
    """If lock.json has task_id, require match; missing lock is ok without require."""
    if not task_id:
        return True
    lock = _read_json_object(evidence / "lock.json")
    if lock is None:
        # No lock: allow only when caller already scoped via suite membership.
        return True
    locked = lock.get("task_id")
    if locked is None:
        return True
    return str(locked) == task_id


def resolve_evidence_root(
    database_root: Path,
    run_id: str,
    *,
    task_id: str | None = None,
    require_task_match: bool = True,
) -> Path:
    """Locate Attempt evidence for *run_id* under the Database root sandbox.

    Lookup order:
    1. ``{database}/.bora/runs/{run_id}``
    2. ``{database}/{tasks_root}/{task_id}/.bora/runs/{run_id}`` when task_id given
    3. Scan ``{database}/tasks/*/.bora/runs/{run_id}`` (bounded)

    When *require_task_match* and *task_id* are set, lock.json ``task_id`` must match
    if present (fail closed on mismatch).
    """
    root = database_root.expanduser().resolve(strict=False)
    rid = _safe_run_id(run_id)
    tid = safe_id_segment(task_id, field="task_id") if task_id else None

    candidates: list[Path] = []
    primary = root / ".bora" / "runs" / rid
    if primary.is_dir():
        candidates.append(primary)

    tasks_root_name = "tasks"
    with contextlib.suppress(ConfigError):
        man = load_database_manifest(root)
        tasks_root_name = man.tasks_root or "tasks"
    # tasks_root may be multi-segment but must not escape (validated at load).
    if ".." in Path(tasks_root_name).parts or tasks_root_name.startswith(("/", "\\")):
        tasks_root_name = "tasks"

    if tid:
        task_local = root / tasks_root_name / tid / ".bora" / "runs" / rid
        if task_local.is_dir():
            candidates.append(task_local)

    # Bounded scan under tasks/*/.bora/runs (single-segment task ids only)
    tasks_dir = root / tasks_root_name
    if tasks_dir.is_dir():
        for child in tasks_dir.iterdir():
            if not child.is_dir():
                continue
            try:
                safe_id_segment(child.name, field="task_id")
            except ConfigError:
                continue
            cand = child / ".bora" / "runs" / rid
            if cand.is_dir():
                candidates.append(cand)

    seen: set[Path] = set()
    for cand in candidates:
        try:
            resolved = _assert_under_database(root, cand, location=str(cand))
        except ConfigError:
            continue
        if resolved in seen:
            continue
        seen.add(resolved)
        if require_task_match and tid and not _evidence_matches_task(resolved, tid):
            continue
        return resolved

    raise ConfigError(
        "unknown_task",
        f"evidence root not found for run_id={rid!r}" + (f" task_id={tid!r}" if tid else ""),
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
    try:
        if any(_has_any_file(p) for p in art_candidates):
            tabs.append("artifacts")
    except OSError:
        pass
    if (evidence / "lock.json").is_file():
        tabs.append("lock")
    # Runtime facts: effects / cleanup / summary (not agent trajectory, not artifacts)
    if (
        (evidence / "effects.jsonl").is_file()
        or (evidence / "cleanup.json").is_file()
        or (evidence / "summary.json").is_file()
        or (evidence / "agent.json").is_file()
        or (evidence / "harness.json").is_file()
    ):
        tabs.append("runtime")
    return tabs


# Known ACP registry entry ids — longest match first when stripping from profile ids.
_ACP_ENTRY_SUFFIXES = (
    "claude-code",
    "grok-build",
    "opencode",
    "codex",
    "grok",
    "pi",
)


def _profile_entry(profile: dict[str, Any]) -> str | None:
    opts = profile.get("options") if isinstance(profile.get("options"), dict) else {}
    entry = opts.get("entry") if isinstance(opts, dict) else None
    if isinstance(entry, str) and entry.strip():
        return entry.strip()
    pid = profile.get("id")
    if not isinstance(pid, str) or not pid:
        return None
    lower = pid.lower()
    for suf in _ACP_ENTRY_SUFFIXES:
        if lower == suf or lower.endswith("-" + suf) or lower.endswith("_" + suf):
            return suf
    return None


def _profile_role(profile_id: str, entry: str | None) -> str:
    """Role label: profile id with trailing entry suffix removed when present."""
    if entry:
        for sep in ("-", "_"):
            suffix = sep + entry
            if profile_id.lower().endswith(suffix.lower()) and len(profile_id) > len(suffix):
                return profile_id[: -len(suffix)]
    return profile_id


def _docker_label(result: dict[str, Any], summary: dict[str, Any]) -> str | None:
    """Short docker placement label when this Attempt used Docker/L1; else None."""
    runtime_kind = str(result.get("runtime_kind") or summary.get("runtime_kind") or "")
    assurance = str(result.get("assurance") or summary.get("assurance") or "")
    l1 = result.get("l1") if isinstance(result.get("l1"), dict) else None
    if l1 is None:
        l1 = summary.get("l1") if isinstance(summary.get("l1"), dict) else None
    is_docker = "docker" in runtime_kind.lower() or assurance.lower() == "l1" or l1 is not None
    if not is_docker:
        return None
    parts: list[str] = ["docker"]
    if isinstance(l1, dict):
        platform = l1.get("platform")
        if isinstance(platform, str) and platform:
            parts.append(platform)
        iso = l1.get("isolation") if isinstance(l1.get("isolation"), dict) else {}
        net = iso.get("network") if isinstance(iso, dict) else None
        if isinstance(net, str) and net:
            parts.append(net)
        loc = l1.get("execution_location")
        if isinstance(loc, str) and loc and loc not in parts:
            parts.append(loc)
    return " · ".join(parts)


def _read_terminal_usage(traj_path: Path) -> dict[str, Any] | None:
    """Last terminal.usage object from a trajectory.jsonl (fail-open)."""
    if not traj_path.is_file():
        return None
    last: dict[str, Any] | None = None
    try:
        with traj_path.open("r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                raw = line.strip()
                if not raw:
                    continue
                try:
                    obj = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if not isinstance(obj, dict):
                    continue
                if obj.get("type") != "terminal":
                    continue
                usage = obj.get("usage")
                if isinstance(usage, dict) and usage:
                    last = usage
    except OSError:
        return None
    return last


def _as_int(val: Any) -> int | None:
    if isinstance(val, bool):
        return None
    if isinstance(val, int):
        return val
    if isinstance(val, float) and val == int(val):
        return int(val)
    return None


def _usage_summary_for_actor(usage: dict[str, Any] | None) -> dict[str, Any] | None:
    """Normalize a terminal usage dict into viewer-facing summary fields (#27/#30).

    - Prefer normalized keys (input_tokens / output_tokens / cost / context).
    - Never treat legacy ``used`` (context occupancy) as tokens.
    - Cache hit rate only when input_tokens > 0 and cached_read_tokens present.
    - Observational only; not PASS authority.
    """
    if not isinstance(usage, dict) or not usage:
        return None

    inp = _as_int(
        usage.get("input_tokens") if "input_tokens" in usage else usage.get("inputTokens")
    )
    outp = _as_int(
        usage.get("output_tokens") if "output_tokens" in usage else usage.get("outputTokens")
    )
    cached_read = _as_int(
        usage.get("cached_read_tokens")
        if "cached_read_tokens" in usage
        else usage.get("cachedReadTokens")
    )
    total = _as_int(
        usage.get("total_tokens") if "total_tokens" in usage else usage.get("totalTokens")
    )

    cost_raw = usage.get("cost")
    cost_amount: float | int | None = None
    cost_currency: str | None = None
    if isinstance(cost_raw, dict):
        amt = cost_raw.get("amount")
        if isinstance(amt, (int, float)) and not isinstance(amt, bool):
            cost_amount = amt
        cur = cost_raw.get("currency")
        if isinstance(cur, str) and cur.strip():
            cost_currency = cur.strip()
    # Legacy flat cost is rare; ignore non-mapping.

    context_raw = usage.get("context") if isinstance(usage.get("context"), dict) else None
    context_used = _as_int(context_raw.get("used")) if isinstance(context_raw, dict) else None
    context_size = _as_int(context_raw.get("size")) if isinstance(context_raw, dict) else None
    # Old evidence: top-level used/size only — keep as context, never as tokens.
    if context_used is None:
        context_used = _as_int(usage.get("used"))
    if context_size is None:
        context_size = _as_int(usage.get("size"))

    # Hit rate only when cached_read is a share of input (0..1). Some vendors
    # report cumulative/session cached_read >> per-turn input — omit label then.
    cache_hit_rate: float | None = None
    if inp is not None and inp > 0 and cached_read is not None and cached_read <= inp:
        cache_hit_rate = cached_read / inp

    has_tokens = inp is not None or outp is not None
    has_cost = cost_amount is not None
    has_context = context_used is not None or context_size is not None
    if not has_tokens and not has_cost and not has_context:
        return None

    summary: dict[str, Any] = {
        "input_tokens": inp,
        "output_tokens": outp,
        "total_tokens": total,
        "cached_read_tokens": cached_read,
        "cache_hit_rate": cache_hit_rate,
        "cost_amount": cost_amount,
        "cost_currency": cost_currency,
        "context_used": context_used,
        "context_size": context_size,
        # Human label assembled server-side so SPA stays thin; observational.
        "label": _format_usage_label(
            input_tokens=inp,
            output_tokens=outp,
            cache_hit_rate=cache_hit_rate,
            cost_amount=cost_amount,
            cost_currency=cost_currency,
        ),
    }
    return summary


def _format_usage_label(
    *,
    input_tokens: int | None,
    output_tokens: int | None,
    cache_hit_rate: float | None,
    cost_amount: float | int | None,
    cost_currency: str | None,
) -> str | None:
    """Compact Usage column text, e.g. ``in 11.4K / out 140 · cache 75% · $0.012``."""
    parts: list[str] = []
    if input_tokens is not None or output_tokens is not None:
        in_s = _fmt_token_count(input_tokens) if input_tokens is not None else "-"
        out_s = _fmt_token_count(output_tokens) if output_tokens is not None else "-"
        parts.append(f"in {in_s} / out {out_s}")
    if cache_hit_rate is not None:
        parts.append(f"cache {cache_hit_rate * 100:.0f}%")
    if cost_amount is not None:
        cur = (cost_currency or "").upper()
        if cur in {"", "USD"}:
            parts.append(f"${_fmt_cost(cost_amount)}")
        else:
            parts.append(f"{_fmt_cost(cost_amount)} {cur}")
    if not parts:
        return None
    return " · ".join(parts)


def _fmt_token_count(n: int) -> str:
    if n >= 1_000_000:
        v = n / 1_000_000
        return f"{int(v)}M" if v == int(v) else f"{v:.1f}M"
    if n >= 1000:
        v = n / 1000
        return f"{int(v)}K" if v == int(v) else f"{v:.1f}K"
    return str(n)


def _fmt_cost(amount: float | int) -> str:
    if isinstance(amount, int) or float(amount) == int(amount):
        if float(amount) == 0:
            return "0"
        return f"{float(amount):.4g}"
    # Prefer up to 4 significant decimals for small USD amounts.
    return f"{float(amount):.4g}"


def _format_latency_ms(total_ms: float | None, invokes: int) -> str | None:
    if total_ms is None:
        return None
    seconds = total_ms / 1000.0
    if seconds >= 10:
        body = f"{seconds:.0f}s"
    elif seconds >= 1:
        body = f"{seconds:.1f}s".replace(".0s", "s")
    else:
        body = f"{total_ms:.0f}ms"
    if invokes > 0:
        return f"{body} ({invokes})"
    return body


def _provenance_surface(lock: dict[str, Any]) -> dict[str, Any]:
    """Project lock provenance for Attempt top bar (url only when present)."""
    prov = lock.get("provenance")
    if not isinstance(prov, dict):
        return {
            "provenance": None,
            "upstream_url": None,
            "upstream_name": None,
            "upstream_ref": None,
        }
    upstream = prov.get("upstream") if isinstance(prov.get("upstream"), dict) else {}
    url = upstream.get("url") if isinstance(upstream, dict) else None
    name = upstream.get("name") if isinstance(upstream, dict) else None
    ref = upstream.get("ref") if isinstance(upstream, dict) else None
    return {
        "provenance": prov,
        "upstream_url": url if isinstance(url, str) and url.strip() else None,
        "upstream_name": name if isinstance(name, str) and name.strip() else None,
        "upstream_ref": ref if isinstance(ref, str) and ref.strip() else None,
    }


def _agent_surface(
    evidence: Path,
    *,
    lock: dict[str, Any],
    result: dict[str, Any],
    summary: dict[str, Any],
) -> dict[str, Any]:
    """Deterministic agent surface from lock profiles + invocation metadata.

    Missing optional fields stay null; never invents values. Priority:
    lock.profiles for declared rows; invocation metadata overrides model when set.

    Per-profile Time / Usage (#27): sum latency_ms; take **last** invoke usage
    (session-cumulative tokens/cost — do not sum cumulative fields).
    """
    profiles_raw = [p for p in (lock.get("profiles") or []) if isinstance(p, dict)]
    by_id: dict[str, dict[str, Any]] = {}
    for p in profiles_raw:
        pid = p.get("id")
        if isinstance(pid, str) and pid:
            by_id[pid] = p

    # Order of appearance: first from invocations (actual use), else lock order.
    ordered_ids: list[str] = []
    inv_model: dict[str, str] = {}
    inv_executor: dict[str, str] = {}
    # Aggregation state per profile_id
    latency_sum: dict[str, float] = {}
    invoke_count: dict[str, int] = {}
    last_usage: dict[str, dict[str, Any]] = {}

    inv_root = evidence / "agent" / "invocations"
    if inv_root.is_dir():
        try:
            inv_dirs = sorted(p for p in inv_root.iterdir() if p.is_dir())
        except OSError:
            inv_dirs = []
        for inv in inv_dirs:
            meta = _read_json_object(inv / "metadata.json") or {}
            pid = meta.get("profile_id")
            if isinstance(pid, str) and pid:
                if pid not in ordered_ids:
                    ordered_ids.append(pid)
                mid = meta.get("model")
                if isinstance(mid, str) and mid:
                    inv_model[pid] = mid
                ek = meta.get("executor_kind")
                if isinstance(ek, str) and ek:
                    inv_executor[pid] = ek
                invoke_count[pid] = invoke_count.get(pid, 0) + 1
                lat = meta.get("latency_ms")
                if isinstance(lat, (int, float)) and not isinstance(lat, bool):
                    latency_sum[pid] = latency_sum.get(pid, 0.0) + float(lat)
                usage = _read_terminal_usage(inv / "trajectory.jsonl")
                if usage is not None:
                    # Last invoke wins (session cumulative semantics).
                    last_usage[pid] = usage
    if not ordered_ids:
        ordered_ids = [pid for pid in by_id]

    actors: list[dict[str, Any]] = []
    executors: list[str] = []
    for pid in ordered_ids:
        p = by_id.get(pid, {"id": pid})
        entry = _profile_entry(p)
        ex = p.get("executor") if isinstance(p.get("executor"), str) else None
        if not ex:
            ex = inv_executor.get(pid)
        if isinstance(ex, str) and ex and ex not in executors:
            executors.append(ex)
        caps_raw = p.get("capabilities")
        caps: dict[str, Any] = caps_raw if isinstance(caps_raw, dict) else {}
        if caps.get("execution_mode") == "acp-stdio" and "acp" not in executors:
            executors.append("acp")
        model = inv_model.get(pid) or (p.get("model") if isinstance(p.get("model"), str) else None)
        # agent column = ACP entry when known, else executor kind, else profile id
        agent_col = entry or ex or pid
        role_col = _profile_role(pid, entry) if entry else pid
        n_inv = invoke_count.get(pid, 0)
        lat_total = latency_sum.get(pid)
        usage_summary = _usage_summary_for_actor(last_usage.get(pid))
        actors.append(
            {
                "role": role_col,
                "agent": agent_col,
                "model": model,
                "profile_id": pid,
                "invokes": n_inv,
                "latency_ms_sum": lat_total,
                "time_label": _format_latency_ms(lat_total, n_inv),
                "usage": usage_summary,
                "usage_label": (
                    usage_summary.get("label") if isinstance(usage_summary, dict) else None
                ),
            }
        )

    # Framework: unified ACP client → "acp"; else first executor kind.
    if any(a.get("agent") in _ACP_ENTRY_SUFFIXES for a in actors) or "acp" in executors:
        framework = "acp"
    elif executors:
        framework = executors[0]
    else:
        framework = None

    docker = _docker_label(result, summary)
    prov = _provenance_surface(lock)

    return {
        "framework": framework,
        "docker": docker,
        "actors": actors,
        # Keep thin aliases for older clients / tests
        "agent_label": actors[0]["role"] if len(actors) == 1 else None,
        "model_label": actors[0]["model"] if len(actors) == 1 else None,
        "executor_kind": executors[0] if executors else None,
        "profiles": actors,
        "provenance": prov.get("provenance"),
        "upstream_url": prov.get("upstream_url"),
        "upstream_name": prov.get("upstream_name"),
        "upstream_ref": prov.get("upstream_ref"),
    }


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
    surface = _agent_surface(evidence, lock=lock, result=result, summary=summary)

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
        "framework": surface.get("framework"),
        "docker": surface.get("docker"),
        "actors": surface.get("actors") or [],
        "agent_label": surface.get("agent_label"),
        "model_label": surface.get("model_label"),
        "executor_kind": surface.get("executor_kind"),
        "profiles": surface.get("profiles") or [],
        "provenance": surface.get("provenance"),
        "upstream_url": surface.get("upstream_url"),
        "upstream_name": surface.get("upstream_name"),
        "upstream_ref": surface.get("upstream_ref"),
        "note": None,
    }


def list_task_trials(
    database_root: Path,
    job_id: str,
    task_id: str,
) -> dict[str, Any]:
    """List trials for a task within a suite job, enriched with local evidence when present."""
    root = database_root.expanduser().resolve(strict=False)
    job_id = safe_id_segment(job_id, field="job_id")
    task_id = safe_id_segment(task_id, field="task_id")
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
        "note": None,
    }


def get_trial(
    database_root: Path,
    job_id: str,
    task_id: str,
    run_id: str,
) -> dict[str, Any]:
    root = database_root.expanduser().resolve(strict=False)
    job_id = safe_id_segment(job_id, field="job_id")
    task_id = safe_id_segment(task_id, field="task_id")
    rid = _safe_run_id(run_id)
    job_payload = get_job(root, job_id)
    job = job_payload["job"]
    suite_row: dict[str, Any] = {}
    for row in job_payload.get("tasks") or []:
        if row.get("task_id") == task_id and str(row.get("run_id") or "") == rid:
            suite_row = row
            break

    evidence: Path | None = None
    with contextlib.suppress(ConfigError):
        evidence = resolve_evidence_root(root, rid, task_id=task_id, require_task_match=True)

    result_preview: dict[str, Any] | None = None
    if evidence is None:
        if not suite_row:
            raise ConfigError(
                "unknown_task",
                f"trial {rid!r} not found for task {task_id!r} in job {job_id!r}",
                location=rid,
            )
        status = suite_row.get("status")
        meta = {
            "trial_id": rid,
            "run_id": rid,
            "task_id": task_id,
            "status": str(status).upper() if status else None,
            "score": suite_row.get("score"),
            "reward": suite_row.get("score"),
            "error": suite_row.get("error"),
            "exit_code": suite_row.get("exit_code"),
            "duration": suite_row.get("duration"),
            "started": suite_row.get("started") or job.get("started"),
            "evidence_relpath": None,
            "has_evidence": False,
            "available_tabs": [],
            "note": "no local evidence tree for this run_id",
        }
    else:
        meta = _trial_meta_from_evidence(evidence, run_id=rid, task_id=task_id, suite_row=suite_row)
        try:
            meta["evidence_relpath"] = str(evidence.resolve(strict=False).relative_to(root))
        except ValueError:
            meta["evidence_relpath"] = str(evidence)
        result_preview = _read_json_object(evidence / "result.json")
        if result_preview and "metrics" in result_preview:
            metrics = result_preview.get("metrics")
            if isinstance(metrics, dict) and len(json.dumps(metrics)) > 8_000:
                result_preview = {**result_preview, "metrics": {"_truncated": True}}

    listed = list_task_trials(root, job_id, task_id)
    sibling_ids = [str(t.get("run_id")) for t in listed["trials"] if t.get("run_id")]
    if rid not in sibling_ids:
        sibling_ids.insert(0, rid)
    try:
        idx = sibling_ids.index(rid)
    except ValueError:
        idx = -1
    prev_id = sibling_ids[idx - 1] if idx > 0 else None
    next_id = sibling_ids[idx + 1] if 0 <= idx < len(sibling_ids) - 1 else None
    cmds = commands_for(root, task_id=task_id)

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
    job_id: str,
    task_id: str,
    run_id: str,
    *,
    scope: str = "root",
) -> dict[str, Any]:
    root = database_root.expanduser().resolve(strict=False)
    safe_id_segment(job_id, field="job_id")
    task_id = safe_id_segment(task_id, field="task_id")
    rid = _safe_run_id(run_id)
    # Ensure job exists (sandbox + membership)
    get_job(root, job_id)
    evidence = resolve_evidence_root(root, rid, task_id=task_id, require_task_match=True)
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
        # Publishable / harness-produced product files — not root runtime bookkeeping.
        # Prefer package artifacts/ then harness/ subtree (e.g. terminal.json, published JSON).
        entries = []
        for sub in (
            evidence / "artifacts",
            evidence / "harness",
            evidence / "agent" / "artifacts",
        ):
            if sub.is_dir():
                entries.extend(
                    _walk_tree(evidence, sub, max_entries=MAX_TREE_ENTRIES - len(entries))
                )
            elif sub.is_file():
                with contextlib.suppress(OSError, ValueError):
                    entries.append(
                        {
                            "path": str(sub.relative_to(evidence)),
                            "name": sub.name,
                            "type": "file",
                            "size": sub.stat().st_size,
                        }
                    )
        return {
            "ok": True,
            "run_id": rid,
            "scope": "artifacts",
            "entries": entries[:MAX_TREE_ENTRIES],
            "truncated": len(entries) > MAX_TREE_ENTRIES,
            "note": "publishable outputs under artifacts/ and harness/; "
            "runtime bookkeeping is under Runtime tab",
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

    if scope_norm in {"runtime", "log"}:  # "log" accepted as alias
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
        return {
            "ok": True,
            "run_id": rid,
            "scope": "runtime",
            "entries": entries,
            "truncated": False,
        }

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

    # Agent scope: attach profile_id / group labels for virtual SPA folders (#27).
    groups: list[dict[str, Any]] | None = None
    if scope_norm == "agent":
        entries, groups = _annotate_agent_tree_profiles(evidence, entries)

    return {
        "ok": True,
        "run_id": rid,
        "scope": scope_norm,
        "entries": entries,
        "groups": groups,
        "truncated": len(entries) >= MAX_TREE_ENTRIES,
    }


def _annotate_agent_tree_profiles(
    evidence: Path,
    entries: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]] | None]:
    """Stamp profile_id on agent/invocations/* entries; build group list.

    Disk layout stays flat; groups are read-side only. Real relative paths
    are preserved for file preview.
    """
    inv_root = evidence / "agent" / "invocations"
    if not inv_root.is_dir():
        return entries, None

    inv_meta: dict[str, dict[str, Any]] = {}
    try:
        inv_dirs = sorted(p for p in inv_root.iterdir() if p.is_dir())
    except OSError:
        inv_dirs = []
    for inv in inv_dirs:
        meta = _read_json_object(inv / "metadata.json") or {}
        pid = meta.get("profile_id")
        inv_meta[inv.name] = {
            "profile_id": pid if isinstance(pid, str) else None,
            "model": meta.get("model") or meta.get("locked_model"),
            "dirname": inv.name,
        }

    if not inv_meta:
        return entries, None

    annotated: list[dict[str, Any]] = []
    for e in entries:
        path = str(e.get("path") or "")
        # agent/invocations/<dirname>/...
        parts = path.split("/")
        profile_id = None
        inv_dirname = None
        if len(parts) >= 3 and parts[0] == "agent" and parts[1] == "invocations":
            inv_dirname = parts[2]
            meta = inv_meta.get(inv_dirname) or {}
            profile_id = meta.get("profile_id")
        ne = dict(e)
        if profile_id:
            ne["profile_id"] = profile_id
        if inv_dirname:
            ne["invocation"] = inv_dirname
        annotated.append(ne)

    # Stable group order: first appearance in inv dir sort order.
    seen: list[str] = []
    groups: list[dict[str, Any]] = []
    for inv_name in sorted(inv_meta.keys()):
        meta = inv_meta[inv_name]
        pid = meta.get("profile_id")
        key = pid if isinstance(pid, str) and pid else inv_name
        if key in seen:
            continue
        seen.append(key)
        groups.append(
            {
                "key": key,
                "profile_id": pid if isinstance(pid, str) else None,
                "label": pid if isinstance(pid, str) else inv_name,
            }
        )
    return annotated, groups if groups else None


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
    job_id: str,
    task_id: str,
    run_id: str,
    *,
    relpath: str,
) -> dict[str, Any]:
    root = database_root.expanduser().resolve(strict=False)
    safe_id_segment(job_id, field="job_id")
    task_id = safe_id_segment(task_id, field="task_id")
    rid = _safe_run_id(run_id)
    get_job(root, job_id)
    evidence = resolve_evidence_root(root, rid, task_id=task_id, require_task_match=True)
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
    # Never preview env/secret-like basenames even if under evidence
    if path.name in {".env", ".env.local", ".env.production"} or path.name.startswith(".env."):
        return {
            "ok": True,
            "run_id": rid,
            "path": relpath,
            "name": path.name,
            "size": size,
            "media_type": mime,
            "encoding": "redacted",
            "truncated": False,
            "content": None,
            "note": "secret-like filename; content not shown",
        }
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
    job_id: str,
    task_id: str,
    run_id: str,
) -> dict[str, Any]:
    root = database_root.expanduser().resolve(strict=False)
    safe_id_segment(job_id, field="job_id")
    task_id = safe_id_segment(task_id, field="task_id")
    rid = _safe_run_id(run_id)
    get_job(root, job_id)
    evidence = resolve_evidence_root(root, rid, task_id=task_id, require_task_match=True)
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
            profile_id = inv_meta.get("profile_id")
            for step in inv_steps:
                if len(steps) >= MAX_TRAJECTORY_STEPS:
                    truncated = True
                    break
                steps.append(
                    {
                        **step,
                        "invocation": inv.name,
                        "invocation_id": inv_meta.get("invocation_id") or inv.name,
                        "profile_id": profile_id,
                        "model": inv_meta.get("model") or inv_meta.get("locked_model"),
                    }
                )
            invocations.append(
                {
                    "dirname": inv.name,
                    "invocation_id": inv_meta.get("invocation_id") or inv.name,
                    "profile_id": profile_id,
                    "executor_kind": inv_meta.get("executor_kind"),
                    "model": inv_meta.get("model") or inv_meta.get("locked_model"),
                    "status": inv_meta.get("status"),
                    "latency_ms": inv_meta.get("latency_ms"),
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
        "note": None,
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
