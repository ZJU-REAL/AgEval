"""Application use case: run Core 2 lifecycle from a LockedTaskConfig.

Does not re-read bora.yaml. Stage implementations are injected by the caller
(tests inject doubles; later versions inject real stages via composition).
"""

from __future__ import annotations

from bora.config.model import LockedTaskConfig
from bora.runtime.cancellation import CancellationSignal, MonotonicClock, default_monotonic_clock
from bora.runtime.coordinator import LifecycleCoordinator, LifecycleStages
from bora.runtime.identity import AttemptIdentity, IdentityFactory
from bora.runtime.outcomes import AttemptRecord, RuntimeTerminalKind


async def run_lifecycle(
    lock: LockedTaskConfig,
    stages: LifecycleStages,
    *,
    attempt: AttemptIdentity | None = None,
    identity_factory: IdentityFactory | None = None,
    cancellation: CancellationSignal | None = None,
    clock: MonotonicClock | None = None,
    cleanup_wait_budget: float = 5.0,
    deadline_monotonic: float | None = None,
    retry_of: AttemptIdentity | None = None,
    previous_record: AttemptRecord | None = None,
) -> AttemptRecord:
    """Drive the Coordinator once with a caller-owned or freshly minted Attempt.

    Parameters
    ----------
    attempt:
        When set, use this identity and do not call ``IdentityFactory.new_run``.
        Production ``run_task`` always passes the single minted Attempt.
    retry_of:
        When *attempt* is omitted and this is set, create a new Attempt under
        the same Trial as *retry_of*, requiring *retry_of* to already be
        terminal (caller enforces). Tests use this when they omit *attempt*.
    """
    factory = identity_factory or IdentityFactory()
    cancel = cancellation or CancellationSignal()
    mono = clock or default_monotonic_clock

    if attempt is None and retry_of is not None:
        if previous_record is not None:
            assert_retryable(previous_record)
            if previous_record.attempt != retry_of:
                from bora.runtime.errors import ERROR_INVALID_RETRY, LifecycleError

                raise LifecycleError(
                    ERROR_INVALID_RETRY,
                    "previous_record.attempt must equal retry_of",
                )
        trial = retry_of.trial
        if trial.locked_config_digest != lock.digest:
            from bora.runtime.errors import ERROR_INVALID_RETRY, LifecycleError

            raise LifecycleError(
                ERROR_INVALID_RETRY,
                "retry Trial digest does not match current lock",
            )
        attempt = factory.new_attempt(trial, retry_of=retry_of)
    elif attempt is None:
        run = factory.new_run()
        trial = factory.new_trial(run, lock.digest)
        attempt = factory.new_attempt(trial)

    coordinator = LifecycleCoordinator(
        stages=stages,
        cancellation=cancel,
        clock=mono,
        cleanup_wait_budget=cleanup_wait_budget,
        deadline_monotonic=deadline_monotonic,
    )
    return await coordinator.run(attempt)


def assert_retryable(previous: AttemptRecord) -> None:
    """Ensure *previous* is terminal before retrying."""
    from bora.runtime.errors import ERROR_INVALID_RETRY, LifecycleError
    from bora.runtime.lifecycle import LifecycleState

    if previous.state != LifecycleState.TERMINAL or previous.terminal is None:
        raise LifecycleError(
            ERROR_INVALID_RETRY,
            "retry requires a terminal AttemptRecord",
        )
    # Any terminal kind is retryable at identity level; policy is application-level.
    _ = RuntimeTerminalKind  # keep import used for type documentation
