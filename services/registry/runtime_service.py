"""Derived Runtime plaza over official public Leaderboard suites.

Nobody stores a Runtime row. Reduce is here; HTTP stays thin.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from services.registry.dataset import BOUND_RELEASE
from services.registry.errors import RegistryAppError
from services.registry.official import official_dataset_ids
from services.registry.store import TokenInfo

from bora.config.runtime_identity import (
    appearance_entry,
    binding_options,
    harness_display_name,
    harness_fingerprint,
    runtime_refs_from_overlay,
)


def attach_runtime_refs(payload: dict[str, Any], official_ids: frozenset[str]) -> dict[str, Any]:
    """Add ``runtime_refs`` only on public official board-shaped suite rows."""
    if (
        payload.get("visibility") == "public"
        and bool(payload.get("complete"))
        and payload.get("bound_kind") == BOUND_RELEASE
        and str(payload.get("database_id") or "") in official_ids
    ):
        refs = runtime_refs_from_overlay(
            payload.get("job_overlay") if isinstance(payload.get("job_overlay"), Mapping) else None
        )
        if refs:
            payload["runtime_refs"] = refs
    return payload


class RuntimeService:
    def __init__(self, meta: Any, results: Any) -> None:
        self.meta = meta
        self.results = results

    def list_runtimes(self, auth: TokenInfo) -> dict[str, Any]:
        cards, _appearances = self._reduce(auth)
        items = sorted(cards.values(), key=lambda c: (c["display_name"], c["runtime_id"]))
        return {"items": items}

    def get_runtime(self, *, runtime_id: str, auth: TokenInfo) -> dict[str, Any]:
        want = (runtime_id or "").strip()
        cards, grouped = self._reduce(auth)
        card = cards.get(want)
        rows = grouped.get(want)
        if card is None or not rows:
            raise RegistryAppError("not_found", "runtime not found", http_status=404)
        appearances = sorted(
            rows,
            key=lambda a: (a["database_id"], -float(a["created_at"] or 0), a["role"]),
        )
        return {**card, "appearances": appearances}

    def _reduce(
        self, auth: TokenInfo
    ) -> tuple[dict[str, dict[str, Any]], dict[str, list[dict[str, Any]]]]:
        official = official_dataset_ids(self.meta.list_releases(include_private=True))
        listed = self.results.list_suites(auth=auth, database_id=None)
        cards: dict[str, dict[str, Any]] = {}
        grouped: dict[str, list[dict[str, Any]]] = {}
        datasets: dict[str, set[str]] = {}
        named_from_label: dict[str, bool] = {}
        for suite in listed.get("items") or []:
            if not isinstance(suite, Mapping):
                continue
            if suite.get("visibility") != "public":
                continue
            if not suite.get("complete") or suite.get("bound_kind") != BOUND_RELEASE:
                continue
            database_id = str(suite.get("database_id") or "")
            if database_id not in official:
                continue
            for appearance, binding in _appearances_from_suite(suite):
                rid = appearance["runtime_id"]
                grouped.setdefault(rid, []).append(appearance)
                datasets.setdefault(rid, set()).add(database_id)
                if rid not in cards or (_has_label(binding) and not named_from_label.get(rid)):
                    cards[rid] = _card_from_binding(rid, binding)
                    named_from_label[rid] = _has_label(binding)
        for rid, card in cards.items():
            card["n_datasets"] = len(datasets.get(rid) or ())
            card["n_appearances"] = len(grouped.get(rid) or ())
        return cards, grouped


def _has_label(binding: Mapping[str, Any]) -> bool:
    label = binding.get("label")
    return isinstance(label, str) and bool(label.strip())


def _card_from_binding(runtime_id: str, binding: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "runtime_id": runtime_id,
        "display_name": harness_display_name(binding),
        "executor": str(binding.get("executor") or "").strip(),
        "entry": appearance_entry(binding),
        "options": binding_options(binding),
        "n_datasets": 0,
        "n_appearances": 0,
    }


def _appearances_from_suite(
    suite: Mapping[str, Any],
) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    overlay = suite.get("job_overlay")
    if not isinstance(overlay, Mapping):
        return []
    bindings = overlay.get("bindings")
    if not isinstance(bindings, Mapping) or not bindings:
        return []
    teammates_all: list[dict[str, str]] = []
    valid: list[tuple[str, Mapping[str, Any]]] = []
    for role, raw in bindings.items():
        if not isinstance(raw, Mapping):
            continue
        role_id = str(role).strip()
        if not role_id or not harness_fingerprint(raw):
            continue
        valid.append((role_id, raw))
        teammates_all.append(
            {
                "role": role_id,
                "executor": str(raw.get("executor") or "").strip(),
                "entry": appearance_entry(raw),
                "display_name": harness_display_name(raw),
            }
        )
    if not valid:
        return []
    metrics = suite.get("metrics")
    metrics_out = dict(metrics) if isinstance(metrics, Mapping) else {}
    model_default = ""
    out: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for role_id, raw in valid:
        model = raw.get("model")
        out.append(
            (
                {
                    "runtime_id": harness_fingerprint(raw),
                    "database_id": str(suite.get("database_id") or ""),
                    "suite_run_id": str(suite.get("suite_run_id") or ""),
                    "role": role_id,
                    "model": model.strip() if isinstance(model, str) else model_default,
                    "pass_rate": suite.get("pass_rate"),
                    "mean_score": suite.get("mean_score"),
                    "metrics": metrics_out,
                    "uploaded_by": str(suite.get("uploaded_by") or ""),
                    "created_at": suite.get("created_at"),
                    "teammates": [t for t in teammates_all if t["role"] != role_id],
                },
                raw,
            )
        )
    return out
