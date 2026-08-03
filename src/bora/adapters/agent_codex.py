"""Built-in Codex AgentExecutor.

Runs non-interactive ``codex exec --json`` so backend events (JSONL) are the
trajectory source. stdout/stderr are diagnostics only; credentials stay in the
executor child environment (host login / CODEX_* as provided by OS).
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class AgentResult:
    model: str
    text: str
    structured: dict[str, object] | None
    ok: bool
    error: str | None = None
    stderr: str = ""
    events: tuple[dict[str, Any], ...] = ()
    source_refs: tuple[dict[str, str], ...] = ()
    usage: dict[str, Any] | None = None


class CodexExecutor:
    """First-party Codex executor with JSONL event collection."""

    kind: str = "codex"

    def __init__(self, *, model: str = "gpt-5.4-mini", binary: str | None = None) -> None:
        self.model = model
        self.binary = binary or shutil.which("codex") or "codex"

    def invoke(
        self,
        prompt: str,
        *,
        timeout: float = 45.0,
        workdir: str | None = None,
        collect_dir: str | Path | None = None,
        redaction_sentinels: tuple[str, ...] | list[str] | None = None,
    ) -> AgentResult:
        # Tests/CI can force offline to avoid long-running network calls.
        if os.environ.get("BORA_OFFLINE_AGENT") == "1":
            return AgentResult(
                model=self.model,
                text="",
                structured=None,
                ok=False,
                error="offline_forced",
                events=(
                    {
                        "type": "lifecycle",
                        "phase": "skipped",
                        "reason": "offline_forced",
                        "source": "codex_adapter",
                    },
                ),
            )
        if shutil.which(self.binary) is None and self.binary == "codex":
            return AgentResult(
                model=self.model,
                text="",
                structured=None,
                ok=False,
                error="codex_binary_missing",
                events=(
                    {
                        "type": "lifecycle",
                        "phase": "failed",
                        "reason": "codex_binary_missing",
                        "source": "codex_adapter",
                    },
                ),
            )

        # Prefer --json event stream as trajectory source (not raw stdout prose).
        cmd = [
            self.binary,
            "exec",
            "--model",
            self.model,
            "--ephemeral",
            "--json",
            "--skip-git-repo-check",
            prompt,
        ]
        cwd = workdir if workdir else None
        collect_root: Path | None = None
        if collect_dir is not None:
            collect_root = Path(collect_dir)
            collect_root.mkdir(parents=True, exist_ok=True)

        try:
            proc = subprocess.run(
                cmd,
                check=False,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=os.environ.copy(),
                cwd=cwd,
            )
        except subprocess.TimeoutExpired as exc:
            stdout = _as_text(exc.stdout)
            stderr = _as_text(exc.stderr)
            events, structured, text, usage = _parse_codex_jsonl(stdout)
            events = events + (
                {
                    "type": "lifecycle",
                    "phase": "timeout",
                    "source": "codex_adapter",
                },
            )
            refs = _maybe_persist_raw(
                collect_root, stdout, stderr, extra_sentinels=redaction_sentinels
            )
            return AgentResult(
                model=self.model,
                text=text[-8000:],
                structured=structured,
                ok=False,
                error="TimeoutExpired",
                stderr=stderr[-8000:],
                events=events,
                source_refs=refs,
                usage=usage,
            )
        except OSError as exc:
            return AgentResult(
                model=self.model,
                text="",
                structured=None,
                ok=False,
                error=type(exc).__name__,
                events=(
                    {
                        "type": "lifecycle",
                        "phase": "crash",
                        "reason": type(exc).__name__,
                        "source": "codex_adapter",
                    },
                ),
            )

        events, structured, text, usage = _parse_codex_jsonl(proc.stdout or "")
        # If JSONL empty, fall back to stdout prose for diagnostics only.
        if not text and proc.stdout:
            text = proc.stdout
        if structured is None:
            structured = _try_parse_json_object(text)
        events = events + (
            {
                "type": "lifecycle",
                "phase": "terminal",
                "returncode": proc.returncode,
                "source": "codex_adapter",
            },
        )
        refs = _maybe_persist_raw(
            collect_root,
            proc.stdout or "",
            proc.stderr or "",
            extra_sentinels=redaction_sentinels,
        )
        return AgentResult(
            model=self.model,
            text=(text or "")[-8000:],
            structured=structured,
            ok=proc.returncode == 0,
            error=None if proc.returncode == 0 else f"exit_{proc.returncode}",
            stderr=(proc.stderr or "")[-8000:],
            events=events,
            source_refs=refs,
            usage=usage,
        )


def _as_text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def _maybe_persist_raw(
    collect_root: Path | None,
    stdout: str,
    stderr: str,
    *,
    extra_sentinels: tuple[str, ...] | list[str] | None = None,
) -> tuple[dict[str, str], ...]:
    """Persist backend raw under evidence only after redaction (fail-closed policy).

    Digest is over the redacted body so evidence never stores plain secrets.
    """
    if collect_root is None:
        return ()
    from bora.evidence.redaction import redact_text

    sent = tuple(s for s in (extra_sentinels or ()) if s)
    refs: list[dict[str, str]] = []
    for name, body in (("backend-stdout.jsonl", stdout), ("backend-stderr.txt", stderr)):
        if not body:
            continue
        cleaned = redact_text(body, extra_sentinels=sent)
        path = collect_root / name
        path.write_text(cleaned, encoding="utf-8")
        digest = hashlib.sha256(cleaned.encode("utf-8")).hexdigest()
        refs.append({"kind": name, "path": str(path), "digest": f"sha256:{digest}"})
    return tuple(refs)


def _parse_codex_jsonl(
    stdout: str,
) -> tuple[tuple[dict[str, Any], ...], dict[str, object] | None, str, dict[str, Any] | None]:
    """Parse ``codex exec --json`` JSONL into events + best-effort final text/structured."""
    events: list[dict[str, Any]] = []
    text_parts: list[str] = []
    structured: dict[str, object] | None = None
    usage: dict[str, Any] | None = None
    for line in (stdout or "").splitlines():
        raw = line.strip()
        if not raw:
            continue
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError:
            # Non-JSON diagnostic line — keep as opaque backend event.
            events.append({"type": "backend_raw_line", "line": raw[:2000], "source": "codex"})
            continue
        if not isinstance(obj, dict):
            events.append({"type": "backend_non_object", "value_type": type(obj).__name__})
            continue
        # Normalize type from common Codex event shapes.
        etype = str(obj.get("type") or obj.get("event") or obj.get("kind") or "backend")
        events.append({"type": etype, "payload": obj, "source": "codex"})
        # Best-effort extract message / usage from known shapes.
        msg = _extract_message(obj)
        if msg:
            text_parts.append(msg)
        maybe_struct = _extract_structured(obj)
        if maybe_struct is not None:
            structured = maybe_struct
        maybe_usage = obj.get("usage") if isinstance(obj.get("usage"), dict) else None
        if maybe_usage is None and isinstance(obj.get("payload"), dict):
            inner = obj["payload"]
            if isinstance(inner.get("usage"), dict):
                maybe_usage = inner["usage"]
        if isinstance(maybe_usage, dict):
            usage = maybe_usage
    text = "\n".join(text_parts).strip()
    if structured is None and text:
        structured = _try_parse_json_object(text)
    return tuple(events), structured, text, usage


def _extract_message(obj: dict[str, Any]) -> str | None:
    for key in ("message", "text", "content", "last_agent_message"):
        val = obj.get(key)
        if isinstance(val, str) and val.strip():
            return val
    item = obj.get("item")
    if isinstance(item, dict):
        for key in ("text", "content", "message"):
            val = item.get(key)
            if isinstance(val, str) and val.strip():
                return val
    return None


def _extract_structured(obj: dict[str, Any]) -> dict[str, object] | None:
    for key in ("structured_output", "structured", "output"):
        val = obj.get(key)
        if isinstance(val, dict):
            return val  # type: ignore[return-value]
    item = obj.get("item")
    if isinstance(item, dict):
        for key in ("structured_output", "structured", "output"):
            val = item.get(key)
            if isinstance(val, dict):
                return val  # type: ignore[return-value]
    return None


def _try_parse_json_object(text: str) -> dict[str, object] | None:
    text = text.strip()
    if not text:
        return None
    try:
        val = json.loads(text)
        return val if isinstance(val, dict) else None
    except json.JSONDecodeError:
        pass
    start = text.rfind("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        try:
            val = json.loads(text[start : end + 1])
            return val if isinstance(val, dict) else None
        except json.JSONDecodeError:
            return None
    return None
