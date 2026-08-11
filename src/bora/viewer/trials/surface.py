"""Tabs, agent surface, and trial meta projection for viewer."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from bora.viewer.trials.paths import _read_json_object
from bora.viewer.trials.usage import (
    _format_latency_ms,
    _read_terminal_usage,
    _usage_summary_for_actor,
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
                # Spec 06: surface executor mechanism on actor rows (nooa/acp/…).
                "executor_kind": ex,
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
    # SPA must receive a string; structured errors (e.g. {phase: ...}) crash React.
    if error is not None and not isinstance(error, str):
        try:
            error = json.dumps(error, ensure_ascii=False, sort_keys=True)
        except (TypeError, ValueError):
            error = str(error)
    locked_task = lock.get("task_id") if isinstance(lock.get("task_id"), str) else None
    surface = _agent_surface(evidence, lock=lock, result=result, summary=summary)

    # Phase timing (#47 D): prefer result, then summary, then suite attempt row.
    phase_timing = None
    for src in (result, summary, suite_row):
        if isinstance(src, dict) and isinstance(src.get("phase_timing"), dict):
            phase_timing = src["phase_timing"]
            break
    duration = suite_row.get("duration") or result.get("duration") or summary.get("duration")
    if duration is None and isinstance(phase_timing, dict):
        total_ms = phase_timing.get("total_ms")
        if isinstance(total_ms, (int, float)) and not isinstance(total_ms, bool):
            from bora.application.phase_timing import format_duration_ms

            duration = format_duration_ms(float(total_ms))
    started = (
        summary.get("started_at")
        or (phase_timing or {}).get("started_at")
        or suite_row.get("started")
    )

    # Token breakdown from actors (observational; Harbor-style bar when present).
    token_timing = _token_bar_from_actors(surface.get("actors") or [])

    return {
        "trial_id": run_id,
        "run_id": run_id,
        "task_id": task_id or locked_task or suite_row.get("task_id"),
        "status": status,
        "score": score,
        "reward": score,
        "error": error,
        "exit_code": suite_row.get("exit_code") or result.get("exit_code"),
        "duration": duration,
        "started": started,
        "phase_timing": phase_timing,
        "token_timing": token_timing,
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


def _token_bar_from_actors(actors: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Aggregate last-invoke token fields across actors for a Harbor-like token bar."""
    cached = 0.0
    uncached = 0.0
    output = 0.0
    any_tok = False
    for a in actors:
        if not isinstance(a, dict):
            continue
        usage = a.get("usage")
        if not isinstance(usage, dict):
            continue
        inp = usage.get("input_tokens")
        out = usage.get("output_tokens")
        cached_read = usage.get("cached_read_tokens")
        if isinstance(out, (int, float)) and not isinstance(out, bool):
            output += float(out)
            any_tok = True
        if isinstance(inp, (int, float)) and not isinstance(inp, bool):
            any_tok = True
            cr = (
                float(cached_read)
                if isinstance(cached_read, (int, float)) and not isinstance(cached_read, bool)
                else 0.0
            )
            cached += cr
            uncached += max(0.0, float(inp) - cr)
        elif isinstance(cached_read, (int, float)) and not isinstance(cached_read, bool):
            cached += float(cached_read)
            any_tok = True
    if not any_tok:
        return None
    segments = [
        {"id": "cached_input", "label": "Cached Input", "tokens": int(round(cached))},
        {"id": "uncached_input", "label": "Uncached Input", "tokens": int(round(uncached))},
        {"id": "output", "label": "Output", "tokens": int(round(output))},
    ]
    total = sum(s["tokens"] for s in segments)
    return {"schema": "bora.token_timing/1", "segments": segments, "total_tokens": total}
