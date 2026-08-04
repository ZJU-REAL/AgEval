"""Provider L0 contracts: launch plan and grants."""

from __future__ import annotations

from collections.abc import Mapping
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

    def __post_init__(self) -> None:
        if not self.argv:
            raise ProviderError(ERROR_INVALID_PLAN, "argv must be non-empty")
        if self.timeout_seconds is not None and self.timeout_seconds <= 0:
            raise ProviderError(ERROR_INVALID_PLAN, "timeout_seconds must be positive")
        if self.max_stream_bytes <= 0:
            raise ProviderError(ERROR_INVALID_PLAN, "max_stream_bytes must be positive")
        object.__setattr__(self, "env", dict(self.env))
