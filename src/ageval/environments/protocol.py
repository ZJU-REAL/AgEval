"""Environment (box) transport protocol — no vendor SDK, no kind branching.

The ``environment`` exclusive slot winner is the only object that knows how a
box is started, how files move in and out, and how a foreground process is
attached. Everything above it (``attempt``, ACP executor, task ``run.py``)
talks to this Protocol and never sees a container id, sandbox handle, or ssh
target.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable

# Capability names a kind may claim. ``requires.environment`` must be a subset.
CAPABILITY_NAMES: frozenset[str] = frozenset(
    {
        "exec",
        "upload",
        "download",
        "attach_stdio",
        "uid_gid",
        "path_views",
        "compose",
    }
)

# In-box path contract. Every kind maps these to its own storage.
WORKSPACE_PATH = "/attempt/workspace"
HOME_PATH = "/attempt/home"
ARTIFACTS_PATH = "/attempt/artifacts"
EVALUATION_PATH = "/attempt/evaluation"


@dataclass(frozen=True, slots=True)
class EnvironmentCapabilities:
    """What a kind can actually deliver. Declaring one it cannot is a bug."""

    exec: bool = False
    upload: bool = False
    download: bool = False
    attach_stdio: bool = False
    uid_gid: bool = False
    path_views: bool = False
    compose: bool = False

    def names(self) -> frozenset[str]:
        return frozenset(name for name in CAPABILITY_NAMES if getattr(self, name))

    def missing(self, required: Sequence[str]) -> list[str]:
        have = self.names()
        return sorted({str(name) for name in required} - have)


@dataclass(frozen=True, slots=True)
class Placement:
    """Where a foreground process attaches. Opaque to callers by design."""

    target_id: str
    user: str | None = None
    workdir: str = WORKSPACE_PATH
    home: str = HOME_PATH


@dataclass(frozen=True, slots=True)
class ExecResult:
    """Result of a completed in-box command."""

    exit_code: int
    stdout: str = ""
    stderr: str = ""
    truncated: bool = False

    @property
    def ok(self) -> bool:
        return self.exit_code == 0


@runtime_checkable
class StdioTransport(Protocol):
    """Live bidirectional pipe to a foreground process inside an open box."""

    stdin: object
    stdout: object
    stderr: object

    def terminate(self) -> None: ...

    def wait(self, timeout: float | None = None) -> int | None: ...


@runtime_checkable
class EnvironmentProvider(Protocol):
    """Exclusive slot ``environment``: the box for one Attempt."""

    kind: str
    capabilities: EnvironmentCapabilities
    # argv prefix that runs a Python module inside this box, e.g. ``("python3",)``.
    python_command: tuple[str, ...]

    async def preflight(self) -> None:
        """Fail closed at lock time when this box cannot be opened here."""
        ...

    async def start(self, *, force_build: bool = False) -> None: ...

    def placement(self) -> Placement:
        """Engine-issued attach facts for the open box (no vendor handle)."""
        ...

    async def exec(
        self,
        command: Sequence[str],
        *,
        cwd: str | None = None,
        env: Mapping[str, str] | None = None,
        timeout_sec: float | None = None,
        user: str | None = None,
        service: str | None = None,
    ) -> ExecResult: ...

    async def upload(self, source: Path, dest: str) -> None: ...

    async def download(self, source: str, dest: Path) -> None: ...

    async def attach_stdio(
        self,
        argv: Sequence[str],
        *,
        placement: Placement,
        env: Mapping[str, str] | None = None,
    ) -> StdioTransport: ...

    async def stop(self, *, delete: bool) -> None: ...


class EnvironmentFailure(Exception):
    """Box failure with a stable kind for evidence and exit mapping."""

    def __init__(self, kind: str, message: str) -> None:
        super().__init__(message)
        self.kind = kind
        self.message = message
