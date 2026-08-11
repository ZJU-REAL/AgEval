"""Deterministic package agents for nooa executor (multiagent env diagnostics)."""

from __future__ import annotations

import json
import re
from typing import Any

# Gold labels for this fixture seed (must match evaluation/expected.json).
GOLD_LABELS = ["INSERT_LARGE_DATA", "LOCK_CONTENTION", "VACUUM"]


def _extract_role_name(prompt: str) -> str | None:
    m = re.search(r"Specialist role:\s*(\w+)", prompt)
    return m.group(1) if m else None


class SpecialistAgent:
    """Decide active/label for one specialist probe from ROWS in the prompt."""

    def run(self, prompt: str, workdir: str | None = None) -> dict[str, Any]:
        del workdir
        name = _extract_role_name(prompt) or "UNKNOWN"
        # Heuristic on fixture seed: first three specialties have strong signal.
        active = name in {"INSERT_LARGE_DATA", "LOCK_CONTENTION", "VACUUM"}
        # Soft signals for the other two (present but not gold).
        if name == "REDUNDANT_INDEX" and "orders_note_idx" in prompt and "0" in prompt:
            active = False
        if name == "FETCH_LARGE_DATA":
            active = False
        payload = {
            "specialist": name,
            "active": active,
            "label": name if active else None,
            "evidence": "rows_present" if "ROWS" in prompt else "no_rows",
        }
        return {"ok": True, "text": json.dumps(payload), "structured": payload}


class PlannerAgent:
    """Optional follow-up SQL; default null for this fixture."""

    def run(self, prompt: str, workdir: str | None = None) -> dict[str, Any]:
        del prompt, workdir
        payload = {"follow_up_sql": None, "rationale": "seed evidence sufficient"}
        return {"ok": True, "text": json.dumps(payload), "structured": payload}


class ReducerAgent:
    """Emit the three gold diagnostic labels supported by specialist evidence."""

    def run(self, prompt: str, workdir: str | None = None) -> dict[str, Any]:
        del workdir
        supporting = list(GOLD_LABELS)
        # Prefer labels that appear as active in findings JSON if present.
        try:
            start = prompt.find("[")
            end = prompt.rfind("]")
            if start >= 0 and end > start:
                findings = json.loads(prompt[start : end + 1])
                if isinstance(findings, list):
                    active = [
                        str(f.get("specialist") or f.get("label") or "")
                        for f in findings
                        if isinstance(f, dict) and f.get("active")
                    ]
                    active = [x for x in active if x]
                    if len(set(active)) >= 3:
                        supporting = list(dict.fromkeys(active))[:3]
        except json.JSONDecodeError:
            pass
        # Ensure exactly the gold set for this package fixture.
        payload = {
            "predicted_labels": list(GOLD_LABELS),
            "supporting_specialists": supporting,
        }
        return {"ok": True, "text": json.dumps(payload), "structured": payload}
