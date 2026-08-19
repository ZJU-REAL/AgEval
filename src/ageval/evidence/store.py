"""Filesystem Attempt evidence store implementing design §8.9 layout."""

from __future__ import annotations

import hashlib
import json
import os
import threading
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ageval.evidence.locators import portable_run_locator
from ageval.evidence.redaction import (
    RedactionError,
    assert_clean,
    redact_and_assert,
    redact_text,
    redact_value,
)
from ageval.evidence.schema import (
    METADATA_SCHEMA_VERSION,
    SUMMARY_SCHEMA_VERSION,
    TERMINAL_STATUSES,
    invocation_dir_name,
    is_terminal_status,
    normalize_event,
)


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _atomic_write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".tmp.{os.getpid()}")
    raw = json.dumps(data, sort_keys=True, indent=2, ensure_ascii=False) + "\n"
    tmp.write_text(raw, encoding="utf-8")
    os.replace(tmp, path)


def _safe_relpath(root: Path, relative: str) -> Path:
    """Resolve a relative path under root; reject traversal and symlink escape."""
    if not relative or relative.startswith(("/", "\\")):
        raise ValueError("path must be relative")
    parts = Path(relative).parts
    if ".." in parts:
        raise ValueError("path traversal rejected")
    candidate = (root / relative).resolve()
    root_resolved = root.resolve()
    if not candidate.is_relative_to(root_resolved):
        raise ValueError("path escapes evidence root")
    return candidate


@dataclass
class InvocationHandle:
    """Mutable handle for one Agent invocation under an Attempt store."""

    store: AttemptEvidenceStore
    invocation_id: str
    seq: int
    directory: Path
    profile_id: str
    executor_kind: str
    model: str
    attempt_id: str
    started_at: str
    status: str = "running"
    sealed: bool = False
    _event_seq: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock)

    @property
    def relative_path(self) -> str:
        return f"agent/invocations/{self.directory.name}"

    def write_request(self, request: dict[str, Any]) -> None:
        """Write redacted request; on residual secret seal redaction_failed and re-raise."""
        try:
            self.store._write_invocation_json(self, "request.json", request)
        except RedactionError:
            finished = _utc_now()
            fail_meta = {
                "schema": METADATA_SCHEMA_VERSION,
                "invocation_id": self.invocation_id,
                "attempt_id": self.attempt_id,
                "profile_id": self.profile_id,
                "executor_kind": self.executor_kind,
                "model": self.model,
                "seq": self.seq,
                "started_at": self.started_at,
                "finished_at": finished,
                "status": "redaction_failed",
                "latency_ms": None,
                "error": "redaction_failed",
                "event_count": self._event_seq,
            }
            self.store._write_json_raw(
                self.directory / "request.json",
                {"redacted": True, "reason": "redaction_failed"},
            )
            self.store._write_json_raw(self.directory / "metadata.json", fail_meta)
            self.status = "redaction_failed"
            self.sealed = True
            raise

    def append_event(self, event: dict[str, Any]) -> None:
        with self._lock:
            if self.sealed:
                return
            self._event_seq += 1
            env = normalize_event(event, seq=self._event_seq)
            # Redact secrets/sentinels before append; never write plain secrets.
            cleaned = redact_value(env, extra_sentinels=self.store.sentinels)
            self.store._append_jsonl(self.directory / "events.jsonl", cleaned)
            # Mirror lifecycle markers into attempt-level agent index.
            self.store.append_agent_index(
                {
                    "type": "invocation_event",
                    "invocation_id": self.invocation_id,
                    "seq": self.seq,
                    "event_type": cleaned.get("type"),
                    "event_seq": cleaned["seq"],
                }
            )

    def write_stderr(self, text: str) -> None:
        cleaned = redact_text(text, extra_sentinels=self.store.sentinels)
        path = self.directory / "stderr.txt"
        path.write_text(cleaned, encoding="utf-8")

    def seal(
        self,
        *,
        status: str,
        final_response: dict[str, Any] | None = None,
        error: str | None = None,
        latency_ms: float | None = None,
        error_detail: str | None = None,
    ) -> None:
        """Atomically finalize metadata (+ optional final-response). Idempotent."""
        with self._lock:
            if self.sealed:
                return
            if status not in TERMINAL_STATUSES:
                raise ValueError(f"invalid terminal status: {status}")
            finished = _utc_now()
            meta = {
                "schema": METADATA_SCHEMA_VERSION,
                "invocation_id": self.invocation_id,
                "attempt_id": self.attempt_id,
                "profile_id": self.profile_id,
                "executor_kind": self.executor_kind,
                "model": self.model,
                "seq": self.seq,
                "started_at": self.started_at,
                "finished_at": finished,
                "status": status,
                "latency_ms": latency_ms,
                "error": error,
                "event_schema": "ageval.trajectory.event/1",
                "event_count": self._event_seq,
            }
            if error_detail:
                meta["error_detail"] = error_detail
            try:
                # Redact first; fail closed only on residual secrets after redaction.
                cleaned_meta = redact_value(meta, extra_sentinels=self.store.sentinels)
                assert_clean(cleaned_meta, extra_sentinels=self.store.sentinels)
                if final_response is not None and status == "completed":
                    cleaned_resp = redact_value(
                        final_response, extra_sentinels=self.store.sentinels
                    )
                    assert_clean(cleaned_resp, extra_sentinels=self.store.sentinels)
                    self.store._write_json_raw(self.directory / "final-response.json", cleaned_resp)
                elif final_response is not None and status != "completed":
                    # Partial: do not write final-response; append lifecycle under lock
                    # without re-entering append_event (non-reentrant lock).
                    self._event_seq += 1
                    partial = normalize_event(
                        {
                            "type": "partial_result",
                            "status": status,
                            "has_payload": True,
                        },
                        seq=self._event_seq,
                    )
                    cleaned_partial = redact_value(partial, extra_sentinels=self.store.sentinels)
                    self.store._append_jsonl(self.directory / "events.jsonl", cleaned_partial)
                self.store._write_json_raw(self.directory / "metadata.json", cleaned_meta)
                self.status = status
                self.sealed = True
                self.store.append_agent_index(
                    {
                        "type": "invocation_terminal",
                        "invocation_id": self.invocation_id,
                        "seq": self.seq,
                        "status": status,
                        "finished_at": finished,
                    }
                )
            except RedactionError as exc:
                fail_meta = {
                    "schema": METADATA_SCHEMA_VERSION,
                    "invocation_id": self.invocation_id,
                    "attempt_id": self.attempt_id,
                    "profile_id": self.profile_id,
                    "executor_kind": self.executor_kind,
                    "model": self.model,
                    "seq": self.seq,
                    "started_at": self.started_at,
                    "finished_at": finished,
                    "status": "redaction_failed",
                    "latency_ms": latency_ms,
                    "error": "redaction_failed",
                    "redaction_hits": exc.hits,
                    "event_count": self._event_seq,
                }
                # Fail closed: scrub unsealed files and backend_raw.
                for name in (
                    "request.json",
                    "events.jsonl",
                    "trajectory.jsonl",
                    "final-response.json",
                    "stderr.txt",
                ):
                    p = self.directory / name
                    if p.exists():
                        if name.endswith(".jsonl"):
                            p.write_text("", encoding="utf-8")
                        elif name.endswith(".txt"):
                            p.write_text("[REDACTED:secret]\n", encoding="utf-8")
                        else:
                            self.store._write_json_raw(
                                p, {"redacted": True, "reason": "redaction_failed"}
                            )
                backend_raw = self.directory / "backend_raw"
                if backend_raw.is_dir():
                    for p in backend_raw.rglob("*"):
                        if p.is_file():
                            p.write_text("[REDACTED:secret]\n", encoding="utf-8")
                self.store._write_json_raw(self.directory / "metadata.json", fail_meta)
                self.status = "redaction_failed"
                self.sealed = True
                raise


@dataclass
class AttemptEvidenceStore:
    """Attempt-owned filesystem store for §8.9 evidence tree."""

    root: Path
    attempt_id: str
    run_id: str | None = None
    database_root: Path | None = None
    sentinels: list[str] = field(default_factory=list)
    _seq: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _invocations: dict[str, InvocationHandle] = field(default_factory=dict)
    _sealed_summary: bool = False

    def __post_init__(self) -> None:
        self.root = Path(self.root)
        if self.database_root is not None:
            self.database_root = Path(self.database_root)
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / "agent" / "invocations").mkdir(parents=True, exist_ok=True)
        (self.root / "evaluation").mkdir(parents=True, exist_ok=True)
        (self.root / "harness").mkdir(parents=True, exist_ok=True)
        # Touch empty JSONL skeletons.
        for rel in ("agent/events.jsonl", "effects.jsonl"):
            p = self.root / rel
            if not p.exists():
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text("", encoding="utf-8")

    @property
    def locator(self) -> str:
        """Portable sealed locator (``.ageval/runs/<run_id>``), never host abs (#70)."""
        return portable_run_locator(self.root, database_root=self.database_root)

    def path(self, relative: str) -> Path:
        return _safe_relpath(self.root, relative)

    def write_lock_summary(self, lock_doc: dict[str, Any]) -> None:
        cleaned = redact_and_assert(lock_doc, extra_sentinels=self.sentinels)
        _atomic_write_json(self.root / "lock.json", cleaned)

    def append_effect(self, decision: dict[str, Any]) -> None:
        cleaned = redact_and_assert(decision, extra_sentinels=self.sentinels)
        self._append_jsonl(self.root / "effects.jsonl", cleaned)

    def append_agent_index(self, event: dict[str, Any]) -> None:
        cleaned = redact_and_assert(event, extra_sentinels=self.sentinels)
        self._append_jsonl(self.root / "agent" / "events.jsonl", cleaned)

    def write_harness_terminal(self, terminal: dict[str, Any]) -> None:
        cleaned = redact_and_assert(terminal, extra_sentinels=self.sentinels)
        _atomic_write_json(self.root / "harness" / "terminal.json", cleaned)

    def write_evaluation(self, name: str, doc: dict[str, Any]) -> None:
        if ".." in name or "/" in name or "\\" in name:
            raise ValueError("evaluation name must be a simple file stem")
        cleaned = redact_and_assert(doc, extra_sentinels=self.sentinels)
        _atomic_write_json(self.root / "evaluation" / f"{name}.json", cleaned)

    def write_cleanup(self, cleanup: dict[str, Any]) -> None:
        cleaned = redact_and_assert(cleanup, extra_sentinels=self.sentinels)
        _atomic_write_json(self.root / "cleanup.json", cleaned)

    def write_summary(self, summary: dict[str, Any]) -> None:
        doc = {
            "schema": SUMMARY_SCHEMA_VERSION,
            "attempt_id": self.attempt_id,
            "run_id": self.run_id,
            "evidence_root": self.locator,
            **summary,
        }
        cleaned = redact_and_assert(doc, extra_sentinels=self.sentinels)
        _atomic_write_json(self.root / "summary.json", cleaned)
        self._sealed_summary = True

    def begin_invocation(
        self,
        *,
        profile_id: str,
        executor_kind: str,
        model: str,
        invocation_id: str | None = None,
    ) -> InvocationHandle:
        with self._lock:
            self._seq += 1
            seq = self._seq
            inv_id = invocation_id or f"inv_{uuid.uuid4().hex[:16]}"
            dirname = invocation_dir_name(seq, inv_id)
            directory = self.root / "agent" / "invocations" / dirname
            directory.mkdir(parents=True, exist_ok=False)
            started = _utc_now()
            handle = InvocationHandle(
                store=self,
                invocation_id=inv_id,
                seq=seq,
                directory=directory,
                profile_id=profile_id,
                executor_kind=executor_kind,
                model=model,
                attempt_id=self.attempt_id,
                started_at=started,
            )
            meta = {
                "schema": METADATA_SCHEMA_VERSION,
                "invocation_id": inv_id,
                "attempt_id": self.attempt_id,
                "profile_id": profile_id,
                "executor_kind": executor_kind,
                "model": model,
                "seq": seq,
                "started_at": started,
                "finished_at": None,
                "status": "running",
                "latency_ms": None,
                "error": None,
                "event_schema": "ageval.trajectory.event/1",
                "event_count": 0,
            }
            _atomic_write_json(directory / "metadata.json", meta)
            # Empty events file for append-only contract.
            (directory / "events.jsonl").write_text("", encoding="utf-8")
            self._invocations[inv_id] = handle
            self.append_agent_index(
                {
                    "type": "invocation_begin",
                    "invocation_id": inv_id,
                    "seq": seq,
                    "profile_id": profile_id,
                    "executor_kind": executor_kind,
                    "started_at": started,
                }
            )
            return handle

    def list_invocations(self) -> list[Path]:
        base = self.root / "agent" / "invocations"
        if not base.is_dir():
            return []
        return sorted(p for p in base.iterdir() if p.is_dir())

    def digest_file(self, relative: str) -> str:
        path = self.path(relative)
        h = hashlib.sha256()
        h.update(path.read_bytes())
        return f"sha256:{h.hexdigest()}"

    # --- internal I/O ---

    def _write_invocation_json(
        self, handle: InvocationHandle, name: str, data: dict[str, Any]
    ) -> None:
        if handle.sealed:
            return
        cleaned = redact_and_assert(data, extra_sentinels=self.sentinels)
        _atomic_write_json(handle.directory / name, cleaned)

    def _write_json_raw(self, path: Path, data: Any) -> None:
        _atomic_write_json(path, data)

    def _append_jsonl(self, path: Path, obj: dict[str, Any]) -> None:
        """Append one complete JSON line (crash-safe: incomplete tail discarded by readers)."""
        path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        # Open append + fsync for durability of committed lines.
        with path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
            fh.flush()
            os.fsync(fh.fileno())


def parse_jsonl_recover(path: Path) -> list[dict[str, Any]]:
    """Read JSONL discarding an incomplete final line (crash recovery)."""
    if not path.is_file():
        return []
    text = path.read_text(encoding="utf-8")
    out: list[dict[str, Any]] = []
    for line in text.splitlines():
        raw = line.strip()
        if not raw:
            continue
        try:
            val = json.loads(raw)
        except json.JSONDecodeError:
            # Incomplete or corrupt line — skip (do not rewrite file).
            continue
        if isinstance(val, dict):
            out.append(val)
    return out


def is_sealed_invocation(directory: Path) -> bool:
    meta_path = directory / "metadata.json"
    if not meta_path.is_file():
        return False
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return False
    return is_terminal_status(str(meta.get("status") or ""))
