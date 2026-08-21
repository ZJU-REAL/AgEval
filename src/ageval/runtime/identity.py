"""Run / Trial / Attempt identity types and factories.

Identities are opaque, prefix-tagged UUIDv4 values. Parent-scope checks prevent
mixing facts across Runs, Trials, or Attempts.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass

from ageval.runtime.errors import (
    ERROR_INVALID_IDENTITY,
    ERROR_INVALID_RETRY,
    LifecycleError,
)

IdSource = Callable[[], str]


def default_id_source() -> str:
    """Production ID source: UUIDv4 hex without dashes."""
    return uuid.uuid4().hex


@dataclass(frozen=True, slots=True)
class RunIdentity:
    """Immutable Run identity: ``run_<uuid4 hex>``."""

    value: str

    def __post_init__(self) -> None:
        if not self.value.startswith("run_") or len(self.value) <= 4:
            raise LifecycleError(
                ERROR_INVALID_IDENTITY,
                f"invalid run identity: {self.value!r}",
            )


@dataclass(frozen=True, slots=True)
class TrialIdentity:
    """Immutable Trial identity bound to a parent Run and locked config digest."""

    value: str
    run: RunIdentity
    locked_config_digest: str

    def __post_init__(self) -> None:
        if not self.value.startswith("trial_") or len(self.value) <= 6:
            raise LifecycleError(
                ERROR_INVALID_IDENTITY,
                f"invalid trial identity: {self.value!r}",
            )
        if not self.locked_config_digest.startswith("sha256:"):
            raise LifecycleError(
                ERROR_INVALID_IDENTITY,
                "trial must bind a sha256 locked_config_digest",
            )


@dataclass(frozen=True, slots=True)
class AttemptIdentity:
    """Immutable Attempt identity bound to a Trial; optional retry parent."""

    value: str
    trial: TrialIdentity
    retry_of_attempt_id: str | None = None

    def __post_init__(self) -> None:
        if not self.value.startswith("attempt_") or len(self.value) <= 8:
            raise LifecycleError(
                ERROR_INVALID_IDENTITY,
                f"invalid attempt identity: {self.value!r}",
            )
        if self.retry_of_attempt_id is not None and not self.retry_of_attempt_id.startswith(
            "attempt_"
        ):
            raise LifecycleError(
                ERROR_INVALID_RETRY,
                f"retry_of must be an attempt id: {self.retry_of_attempt_id!r}",
            )


class IdentityFactory:
    """Create scoped identities. Tests may inject a deterministic ``id_source``."""

    def __init__(self, id_source: IdSource | None = None) -> None:
        self._id_source = id_source or default_id_source

    def new_run(self) -> RunIdentity:
        return RunIdentity(value=f"run_{self._id_source()}")

    def new_trial(self, run: RunIdentity, locked_config_digest: str) -> TrialIdentity:
        return TrialIdentity(
            value=f"trial_{self._id_source()}",
            run=run,
            locked_config_digest=locked_config_digest,
        )

    def new_attempt(
        self,
        trial: TrialIdentity,
        *,
        retry_of: AttemptIdentity | None = None,
    ) -> AttemptIdentity:
        if retry_of is not None and retry_of.trial != trial:
            raise LifecycleError(
                ERROR_INVALID_RETRY,
                "retry Attempt must share the same TrialIdentity",
            )
        return AttemptIdentity(
            value=f"attempt_{self._id_source()}",
            trial=trial,
            retry_of_attempt_id=retry_of.value if retry_of is not None else None,
        )
