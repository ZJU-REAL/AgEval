"""Versioned trajectory export — re-redact sealed Attempt evidence (Spec 16).

Export is a read-only copy; never mutates source evidence or evaluation score.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from bora.evidence.redaction import redact_value
from bora.evidence.store import parse_jsonl_recover

EXPORT_SCHEMA = "bora.trajectory.export/1"


@dataclass(frozen=True, slots=True)
class ExportResult:
    ok: bool
    export_path: str
    invocation_count: int
    error: str | None = None


def export_trajectory(
    evidence_root: Path,
    dest_dir: Path,
    *,
    extra_sentinels: list[str] | None = None,
) -> ExportResult:
    """Copy sealed invocation trees into a versioned export package."""
    evidence_root = evidence_root.resolve()
    if not evidence_root.is_dir():
        return ExportResult(False, "", 0, error="evidence_root_missing")
    dest_dir = dest_dir.resolve()
    if dest_dir.exists():
        shutil.rmtree(dest_dir)
    dest_dir.mkdir(parents=True)

    inv_src = evidence_root / "agent" / "invocations"
    inv_dirs = sorted(p for p in inv_src.iterdir() if p.is_dir()) if inv_src.is_dir() else []
    manifest_invocations: list[dict[str, Any]] = []
    for inv in inv_dirs:
        out_inv = dest_dir / "invocations" / inv.name
        out_inv.mkdir(parents=True)
        for name in ("metadata.json", "request.json", "final-response.json"):
            src = inv / name
            if not src.is_file():
                continue
            try:
                data = json.loads(src.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            cleaned = redact_value(data, extra_sentinels=extra_sentinels or ())
            (out_inv / name).write_text(
                json.dumps(cleaned, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
        # events.jsonl re-redacted line by line
        events_path = inv / "events.jsonl"
        if events_path.is_file():
            rows = parse_jsonl_recover(events_path)
            with (out_inv / "events.jsonl").open("w", encoding="utf-8") as fh:
                for row in rows:
                    cleaned = redact_value(row, extra_sentinels=extra_sentinels or ())
                    fh.write(json.dumps(cleaned, sort_keys=True, separators=(",", ":")) + "\n")
        meta_path = out_inv / "metadata.json"
        status = None
        if meta_path.is_file():
            status = json.loads(meta_path.read_text(encoding="utf-8")).get("status")
        manifest_invocations.append(
            {
                "dir": inv.name,
                "status": status,
                "source": str(inv.relative_to(evidence_root)),
            }
        )

    # effects export
    effects = parse_jsonl_recover(evidence_root / "effects.jsonl")
    with (dest_dir / "effects.jsonl").open("w", encoding="utf-8") as fh:
        for row in effects:
            cleaned = redact_value(row, extra_sentinels=extra_sentinels or ())
            fh.write(json.dumps(cleaned, sort_keys=True, separators=(",", ":")) + "\n")

    manifest = {
        "schema": EXPORT_SCHEMA,
        "source_evidence": str(evidence_root),
        "invocation_count": len(manifest_invocations),
        "invocations": manifest_invocations,
        "note": "export is a re-redacted copy; score authority remains evaluator binding",
    }
    (dest_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return ExportResult(
        ok=True,
        export_path=str(dest_dir),
        invocation_count=len(manifest_invocations),
    )
