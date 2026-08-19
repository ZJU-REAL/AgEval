"""A leaky backend must not put a credential on disk."""

from __future__ import annotations

from pathlib import Path

from tests.helpers.agent_binding import ScriptedBinder

from ageval.attempt.ctx import AttemptCtx
from ageval.evidence.store import AttemptEvidenceStore
from ageval.plugins.agent_result import AgentResult
from ageval.runtime.parent_agent import ParentAgentService

SENTINEL = "SENTINEL_TOKEN_NOT_FOR_DISK"


class LeakyExecutor:
    """Tries every route out: text, structured, events, stderr, metadata."""

    kind = "leaky"

    def invoke(self, prompt: str, **kwargs: object) -> AgentResult:
        del prompt, kwargs
        return AgentResult(
            model="leaky-model",
            text=f"here it is: {SENTINEL}",
            structured={"token": SENTINEL},
            ok=True,
            error=None,
            stderr=f"trace {SENTINEL}",
            events=(
                {
                    "schema": "ageval.trajectory.event/1",
                    "seq": 1,
                    "source": "leaky",
                    "kind": "text",
                    "channel": "assistant",
                    "text": SENTINEL,
                },
            ),
            metadata={"executor_kind": "leaky", "note": SENTINEL},
        )

    def close(self) -> None:
        return None


def test_no_sealed_file_contains_the_sentinel(tmp_path: Path) -> None:
    store = AttemptEvidenceStore(
        root=tmp_path / "run",
        attempt_id="attempt_sec",
        run_id="run_sec",
        sentinels=[SENTINEL],
    )
    service = ParentAgentService(
        attempt_id="attempt_sec",
        binder=ScriptedBinder(LeakyExecutor()),
        agent_invocation_limit=1,
        evidence_store=store,
        offline_env="",
    )
    answer = service.invoke(session_id=_open(service), prompt="go")
    assert answer["ok"] is True

    _record(store)

    leaked = [
        path
        for path in store.root.rglob("*")
        if path.is_file() and SENTINEL in path.read_text(encoding="utf-8", errors="replace")
    ]
    assert leaked == [], f"sentinel reached {[p.name for p in leaked]}"


def _open(service: ParentAgentService) -> str:
    opened = service.open_session(profile_id="solver")
    assert opened["ok"], opened
    return str(opened["session_id"])


def _record(store: AttemptEvidenceStore) -> None:
    """Run the record phase against this store, as a real Attempt would."""
    import asyncio

    from ageval.attempt.phases import record

    ctx = AttemptCtx(
        run_id="run_sec",
        trial_id="trial_sec",
        attempt_id="attempt_sec",
        lock=None,  # type: ignore[arg-type] — record only reads evidence
        profile_id="solver",
        bindings=None,  # type: ignore[arg-type] — no chains bound
        services=None,  # type: ignore[arg-type]
        host=None,  # type: ignore[arg-type]
        evidence=store,
        cancellation=None,  # type: ignore[arg-type]
        task_root=store.root,
        dataset_root=store.root,
    )
    asyncio.run(record.run(ctx))
    assert (store.root / "trajectory.jsonl").is_file()
