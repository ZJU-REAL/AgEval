"""One Run / Trial / Attempt identity per Attempt, minted by the engine only."""

from __future__ import annotations

import asyncio
import shutil
from pathlib import Path

from ageval.application.run import run_attempt
from ageval.runtime.identity import IdentityFactory

REPO = Path(__file__).resolve().parents[2]
CORE = REPO / "examples" / "datasets" / "minimal-demo"


class CountingIdentityFactory(IdentityFactory):
    """Records how often each identity was minted."""

    def __init__(self) -> None:
        super().__init__()
        self.runs = 0
        self.trials = 0
        self.attempts = 0

    def new_run(self):  # type: ignore[no-untyped-def]
        self.runs += 1
        return super().new_run()

    def new_trial(self, run, digest):  # type: ignore[no-untyped-def]
        self.trials += 1
        return super().new_trial(run, digest)

    def new_attempt(self, trial):  # type: ignore[no-untyped-def]
        self.attempts += 1
        return super().new_attempt(trial)


def test_one_attempt_mints_one_run(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("AGEVAL_OFFLINE_AGENT", "1")
    # Evidence lands under the dataset root, so run against a copy.
    dataset = shutil.copytree(
        CORE, tmp_path / "minimal-demo", ignore=shutil.ignore_patterns(".ageval", ".env")
    )
    factory = CountingIdentityFactory()

    code, result = asyncio.run(run_attempt(dataset, "terminal-jsonl-agg", identity_factory=factory))

    assert (factory.runs, factory.trials, factory.attempts) == (1, 1, 1)
    # Offline refuses the invoke, so the verdict is never PASS.
    assert code != 0
    assert result.status != "PASS"
    assert result.evidence_path.startswith(".ageval/runs/attempt_")
