"""Provider L0 contracts: launch plan, grants, and termination policy."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path

from bora.provider.errors import ERROR_INVALID_PLAN, ERROR_UNDECLARED_EXECUTABLE, ProviderError
from bora.provider.workspace_plan import WorkspacePlan
from bora.runtime.identity import AttemptIdentity


@dataclass(frozen=True, slots=True)
class ExecutableGrant:
    """Explicit argv[0] executable the Provider may spawn."""

    path: Path

    def resolve(self) -> Path:
        exe = self.path.expanduser().resolve(strict=False)
        if not exe.exists() or not exe.is_file():
            raise ProviderError(
                ERROR_UNDECLARED_EXECUTABLE,
                f"executable not found: {self.path}",
            )
        return exe


@dataclass(frozen=True, slots=True)
class ProcessLaunchPlan:
    """Immutable L0 launch plan validated before spawn."""

    attempt: AttemptIdentity
    workspace: WorkspacePlan
    executable: ExecutableGrant
    argv: tuple[str, ...]
    env: Mapping[str, str] = field(default_factory=dict)
    timeout_seconds: float | None = 30.0
    max_stream_bytes: int = 64_000
    # Inherited descriptors for worker channels (socketpair endpoint).
    pass_fds: tuple[int, ...] = ()
    # stdin payload written once after spawn, then the pipe is closed.
    stdin_bytes: bytes | None = None

    def __post_init__(self) -> None:
        if not self.argv:
            raise ProviderError(ERROR_INVALID_PLAN, "argv must be non-empty")
        if self.timeout_seconds is not None and self.timeout_seconds <= 0:
            raise ProviderError(ERROR_INVALID_PLAN, "timeout_seconds must be positive")
        if self.max_stream_bytes <= 0:
            raise ProviderError(ERROR_INVALID_PLAN, "max_stream_bytes must be positive")
        for fd in self.pass_fds:
            if fd < 0:
                raise ProviderError(ERROR_INVALID_PLAN, "pass_fds must be non-negative")
        object.__setattr__(self, "env", dict(self.env))
        object.__setattr__(self, "pass_fds", tuple(self.pass_fds))


@dataclass(frozen=True, slots=True)
class TerminationPolicy:
    """Adapter teardown action plus an independent liveness probe.

    The Provider always runs its own process-group teardown; this policy is
    additive for runtimes whose real writer outlives the supervised process
    (a container survives the ``docker run`` client that spawned it).

    ``terminate`` returns the action name recorded on the outcome, or ``None``
    when it did nothing. ``is_alive`` must probe the real writer, never echo
    what ``terminate`` believes it accomplished.
    """

    terminate: Callable[[], str | None]
    is_alive: Callable[[], bool]
