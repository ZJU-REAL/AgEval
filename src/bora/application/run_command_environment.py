"""L0 Environment Manager prepare helpers (postgresql resource-type only).

#71 C: after default seed/health, host awaits env multi handlers with a live
ctx (package_root, env_manager, handoff). Handlers do real work — Core does
not interpret free-form command dict rows.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from bora.config.model import thaw
from bora.evaluation.result_binding import FlatResult, bind_result
from bora.evidence.store import AttemptEvidenceStore


def split_sql_statements(sql_text: str) -> list[str]:
    """Split package seed.sql into single statements (strip comments/empties)."""
    stmts: list[str] = []
    buf: list[str] = []
    for line in sql_text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("--"):
            continue
        buf.append(line)
        if stripped.endswith(";"):
            stmt = "\n".join(buf).strip().rstrip(";").strip()
            if stmt:
                stmts.append(stmt)
            buf = []
    tail = "\n".join(buf).strip().rstrip(";").strip()
    if tail:
        stmts.append(tail)
    return stmts


def prepare_postgresql_environment(
    *,
    package_root: Path,
    lock: Any,
    run_dir: Path,
    run_id: str,
    params: dict[str, Any],
    agent_meta: dict[str, Any],
    evidence_store: AttemptEvidenceStore | None,
) -> tuple[
    Any | None,
    AttemptEvidenceStore | None,
    dict[str, Any],
    tuple[int, FlatResult, dict[str, Any]] | None,
]:
    """Open postgresql Environment Manager for an L0 Attempt.

    Returns ``(env_manager, evidence_store, env_meta, early_return)``.
    When *early_return* is not None, the caller must return it immediately.
    """
    from bora.environment.manager import EnvironmentManager

    env_manager = None
    env_meta: dict[str, Any] = {"resource": "postgresql", "manager": True}
    try:
        limits_map = thaw(lock.limits) if hasattr(lock, "limits") else {}
        action_limit = int(
            (limits_map or {}).get("environment_actions") or 10  # type: ignore[union-attr]
        )
        # Ensure §8.9 evidence root exists for effects.jsonl even without Agent Session.
        if evidence_store is None:
            evidence_store = AttemptEvidenceStore(
                root=run_dir,
                attempt_id=str(agent_meta.get("attempt_id") or run_id),
                run_id=run_id,
            )
        env_manager = EnvironmentManager(
            attempt_id=str(agent_meta.get("attempt_id") or run_id),
            action_limit=max(1, action_limit),
            evidence_store=evidence_store,
        )
        opened = env_manager.open_resource("postgresql", name=f"bora-env-{run_id[:10]}")
        if not opened.get("ok"):
            raise RuntimeError(opened.get("error") or "open_resource_failed")
        rid = str(opened["resource_id"])
        # Resource-type handoff only: container locator for package Tools.
        # No Benchmark/task/domain branch; package may ship environment/seed.sql.
        container = rid.split(":", 1)[-1] if ":" in rid else rid
        seed_file = package_root / "environment" / "seed.sql"
        seed_applied = False
        if seed_file.is_file():
            for stmt in split_sql_statements(seed_file.read_text(encoding="utf-8")):
                r = env_manager.action(rid, "execute", {"sql": stmt})
                if not r.get("ok"):
                    raise RuntimeError(f"environment seed failed: {r}")
            seed_applied = True
        # Generic readiness probe (resource protocol only — no package table names).
        health = env_manager.action(rid, "query", {"sql": "SELECT 1"})
        if not health.get("ok"):
            raise RuntimeError(f"environment health failed: {health}")
        snap = env_manager.freeze_snapshot(rid)
        # Optional Spec 15 public negative: undeclared/dangerous action before mutation.
        deny_probe: dict[str, Any] | None = None
        if str(params.get("probe_mode") or "") == "undeclared_action":
            # Unknown action id — Manager/Adapter must refuse before external effect.
            denied = env_manager.action(rid, "drop_schema", {"sql": "DROP TABLE x"})
            # Dangerous SQL on allowed execute surface — adapter fail closed.
            denied_sql = env_manager.action(
                rid, "execute", {"sql": "DROP TABLE IF EXISTS probe_denied_table"}
            )
            deny_probe = {
                "unknown_action": denied,
                "dangerous_sql": denied_sql,
                "denied_before_mutation": (
                    denied.get("ok") is False and denied_sql.get("ok") is False
                ),
                "mutation_executed": False,
            }
        # Connection recipe for Harness Tools — never gold / business answers.
        env_doc: dict[str, Any] = {
            "ok": True,
            "resource": "postgresql",
            "resource_id": rid,
            "container": container,
            "user": "bora",
            "password": "bora-attempt",
            "database": "bora",
            "seed_applied": seed_applied,
            "snapshot": snap,
            "action_count": env_manager._actions,
            "deny_probe": deny_probe,
        }

        # #71 C: live SPI — await multi handlers; they do work / rewrite handoff.
        from bora.application.extension_hooks import (
            hook_env_action,
            hook_env_inject,
            hook_env_prepare,
        )

        env_ctx = SimpleNamespace(
            attempt_id=str(agent_meta.get("attempt_id") or run_id),
            package_root=package_root,
            workdir=package_root,
            run_dir=run_dir,
            resource_id=rid,
            env_manager=env_manager,
            env_handoff=env_doc,
            lock=lock,
        )
        try:
            env_doc = hook_env_prepare(lock, env_doc, ctx=env_ctx, fail_closed=True)
            if not isinstance(env_doc, dict):
                raise RuntimeError("env_prepare_handler_must_return_handoff_dict")
            env_ctx.env_handoff = env_doc
            env_doc = hook_env_inject(lock, env_doc, ctx=env_ctx, fail_closed=True)
            if not isinstance(env_doc, dict):
                raise RuntimeError("env_inject_handler_must_return_handoff_dict")
            env_ctx.env_handoff = env_doc
            action_spi = hook_env_action(lock, {"op": "prepare", "resource_id": rid}, ctx=env_ctx)
            # Attach SPI object with check() as action gate; markers stay observational.
            if action_spi is not None and hasattr(action_spi, "check"):
                env_manager.action_gate = action_spi
                env_doc["env_action"] = {
                    "plugin": type(action_spi).__name__,
                    "gate": True,
                }
            elif isinstance(action_spi, dict):
                env_doc["env_action"] = action_spi
            else:
                env_doc["env_action"] = {"value": action_spi}
        except Exception as ext_exc:  # noqa: BLE001
            raise RuntimeError(f"env_extension_failed: {ext_exc}") from ext_exc

        env_doc["action_count"] = env_manager._actions
        (package_root / ".bora_env_result.json").write_text(
            json.dumps(env_doc, sort_keys=True, default=str) + "\n", encoding="utf-8"
        )
        env_meta.update(
            {
                "ok": True,
                "ready": True,
                "resource_id": rid,
                "container": container,
                "seed_applied": seed_applied,
                "extension_env": {
                    "post_setup": env_doc.get("post_setup"),
                    "env_action": env_doc.get("env_action"),
                },
            }
        )
    except Exception as exc:  # noqa: BLE001
        env_doc = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        (package_root / ".bora_env_result.json").write_text(
            json.dumps(env_doc, sort_keys=True) + "\n", encoding="utf-8"
        )
        env_meta.update({"ok": False, "error": str(exc)})
        flat = bind_result(
            evaluator_raw=None,
            harness_kind="failed",
            runtime_kind="local_l0",
            agent_invocations=0,
            evidence_path=str(run_dir),
            error_phase="environment",
        )
        summary = flat.as_dict()
        summary["assurance"] = "l0"
        summary["status"] = "ERROR"
        summary["error"] = {
            "phase": "environment",
            "kind": "environment_prepare_failed",
            "message": str(exc),
        }
        (run_dir / "result.json").write_text(
            json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        if env_manager is not None:
            import contextlib

            with contextlib.suppress(Exception):
                env_manager.close()
        return (
            None,
            evidence_store,
            env_meta,
            (2, flat, {"environment": env_meta, "assurance": "l0"}),
        )
    return env_manager, evidence_store, env_meta, None
