"""E2BHost — the ``e2b`` environment kind.

The same ``environment/Dockerfile`` a docker box builds becomes an e2b template
here, keyed by the recipe's own digest so a rebuilt recipe gets a new template
and an unchanged one is reused. Every mention of the vendor SDK, the template
alias and the sandbox id lives in this package.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from ageval.environments.protocol import (
    ARTIFACTS_PATH,
    HOME_PATH,
    WORKSPACE_PATH,
    BoxSpec,
    EnvironmentCapabilities,
    EnvironmentFailure,
    ExecResult,
    Placement,
)

API_KEY_ENV = "E2B_API_KEY"
BOX_ROOT = "/attempt"
_MAX_STREAM_BYTES = 256 * 1024


class E2BStdio:
    """Live pipe to a foreground command in the sandbox."""

    def __init__(self, handle: Any, stdin: Any, stdout: Any, stderr: Any) -> None:
        self._handle = handle
        self.stdin = stdin
        self.stdout = stdout
        self.stderr = stderr

    def terminate(self) -> None:
        kill = getattr(self._handle, "kill", None)
        if callable(kill):
            kill()

    def wait(self, timeout: float | None = None) -> int | None:
        del timeout
        wait = getattr(self._handle, "wait", None)
        if not callable(wait):
            return None
        result = wait()
        return int(getattr(result, "exit_code", 0) or 0)


class E2BHost:
    """An ephemeral cloud sandbox per Attempt.

    No shared filesystem with this machine, so files really move: upload writes
    bytes into the sandbox and download reads them back.
    """

    kind = "e2b"
    python_command = ("python3",)
    capabilities = EnvironmentCapabilities(
        exec=True,
        upload=True,
        download=True,
        attach_stdio=True,
        uid_gid=False,
        path_views=False,
        compose=False,
    )

    def __init__(
        self,
        *,
        spec: BoxSpec,
        options: Mapping[str, object] | None = None,
    ) -> None:
        opts = dict(options or {})
        self._task_root = spec.task_root
        self._dockerfile = spec.dockerfile
        self._declared_image = _text(opts.get("image") or opts.get("docker_image"))
        self._template_name = _text(opts.get("template")) or "ageval-attempt"
        self._timeout_seconds = _seconds(opts.get("timeout_seconds"), default=900)
        self._sandbox: Any = None
        self._started = False
        self._stopped = False

    # --- lifecycle -----------------------------------------------------------

    async def preflight(self) -> None:
        """No key, no sandbox — and no attempt to create one."""
        if not os.environ.get(API_KEY_ENV, "").strip():
            raise EnvironmentFailure(
                "environment_preflight_failed",
                f"{API_KEY_ENV} is not set; the e2b kind cannot open a sandbox",
            )
        _import_sdk()

    async def start(self, *, force_build: bool = False) -> None:
        if self._started:
            raise EnvironmentFailure("environment_already_started", "e2b sandbox already started")
        sdk = _import_sdk()
        template = await self._ensure_template(sdk, force_build=force_build)
        self._sandbox = await asyncio.to_thread(
            sdk.Sandbox.create,
            template=template,
            timeout=self._timeout_seconds,
        )
        self._started = True
        for path in (WORKSPACE_PATH, HOME_PATH, ARTIFACTS_PATH):
            await asyncio.to_thread(self._sandbox.files.make_dir, path)

    async def stop(self, *, delete: bool) -> None:
        # Ephemeral by nature: keeping it alive is not on offer, and evidence
        # records that plainly rather than pretending --keep-workspace worked.
        del delete
        if self._stopped or self._sandbox is None:
            return
        self._stopped = True
        await asyncio.to_thread(self._sandbox.kill)

    # --- transport -----------------------------------------------------------

    async def exec(
        self,
        command: Sequence[str],
        *,
        cwd: str | None = None,
        env: Mapping[str, str] | None = None,
        timeout_sec: float | None = None,
        user: str | None = None,
        service: str | None = None,
    ) -> ExecResult:
        self._assert_started()
        if user is not None:
            raise EnvironmentFailure(
                "environment_capability_missing",
                "e2b does not provide uid_gid; exec(user=…) is unavailable",
            )
        if service is not None:
            raise EnvironmentFailure(
                "environment_capability_missing",
                "e2b does not provide compose; exec(service=…) is unavailable",
            )
        argv = [str(part) for part in command]
        if not argv:
            raise EnvironmentFailure("environment_exec_invalid", "exec requires a command")
        result = await asyncio.to_thread(
            self._sandbox.commands.run,
            _shell_line(argv),
            cwd=cwd or WORKSPACE_PATH,
            envs=self._child_env(env),
            timeout=int(timeout_sec) if timeout_sec else 0,
        )
        return ExecResult(
            exit_code=int(getattr(result, "exit_code", 0) or 0),
            stdout=str(getattr(result, "stdout", "") or "")[:_MAX_STREAM_BYTES],
            stderr=str(getattr(result, "stderr", "") or "")[:_MAX_STREAM_BYTES],
        )

    async def upload(self, source: Path, dest: str) -> None:
        self._assert_started()
        src = Path(source).expanduser()
        if not src.exists():
            raise EnvironmentFailure(
                "environment_upload_missing",
                f"upload source does not exist: {source}",
            )
        for path, target in _walk_for_upload(src, dest):
            payload = path.read_bytes()
            await asyncio.to_thread(self._sandbox.files.write, target, payload)

    async def download(self, source: str, dest: Path) -> None:
        self._assert_started()
        target = Path(dest).expanduser()
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = await asyncio.to_thread(self._sandbox.files.read, source, "bytes")
        target.write_bytes(bytes(payload))

    async def attach_stdio(
        self,
        argv: Sequence[str],
        *,
        placement: Placement,
        env: Mapping[str, str] | None = None,
    ) -> E2BStdio:
        """Start a foreground command in the sandbox and hand back its streams."""
        self._assert_started()
        parts = [str(part) for part in argv]
        if not parts:
            raise EnvironmentFailure("environment_attach_invalid", "attach_stdio requires argv")
        handle = await asyncio.to_thread(
            self._sandbox.commands.run,
            _shell_line(parts),
            background=True,
            cwd=placement.workdir,
            envs={"HOME": placement.home, **self._child_env(env)},
            stdin=True,
            timeout=0,
        )
        return E2BStdio(
            handle,
            stdin=_SandboxStdin(handle),
            stdout=_SandboxStdout(handle),
            stderr=None,
        )

    # --- e2b specifics -------------------------------------------------------

    def placement(self) -> Placement:
        if self._sandbox is None:
            raise EnvironmentFailure("environment_not_started", "e2b sandbox is not started")
        return Placement(
            target_id=str(getattr(self._sandbox, "sandbox_id", "e2b")),
            user=None,
            workdir=WORKSPACE_PATH,
            home=HOME_PATH,
        )

    def visible_path(self, box_path: str) -> str:
        """The sandbox really owns ``/attempt``."""
        return box_path

    async def _ensure_template(self, sdk: Any, *, force_build: bool) -> str:
        """Reuse a template keyed by the recipe; build it only when new."""
        if self._declared_image is not None and self._dockerfile is None:
            return await self._build_template(
                sdk, from_image=self._declared_image, force=force_build
            )
        if self._dockerfile is None:
            raise EnvironmentFailure(
                "environment_image_unresolved",
                "the e2b kind needs environment/Dockerfile or an image option",
            )
        return await self._build_template(sdk, from_image=None, force=force_build)

    async def _build_template(self, sdk: Any, *, from_image: str | None, force: bool) -> str:
        alias = self._alias(from_image)
        if not force and await sdk.AsyncTemplate.alias_exists(alias):
            return alias
        context = str(self._task_root)
        builder = sdk.Template(file_context_path=context)
        template = (
            builder.from_image(from_image)
            if from_image is not None
            else builder.from_dockerfile(str(self._task_root / str(self._dockerfile)))
        )
        await sdk.AsyncTemplate.build(template, alias=alias)
        return alias

    def _alias(self, from_image: str | None) -> str:
        """``<name>__<recipe digest>``: a new recipe is a new template."""
        material = (
            from_image.encode("utf-8")
            if from_image is not None
            else (self._task_root / str(self._dockerfile)).read_bytes()
        )
        return f"{self._template_name}__{hashlib.sha256(material).hexdigest()[:12]}"

    def _child_env(self, env: Mapping[str, str] | None) -> dict[str, str]:
        """Only what the caller declared, plus this box's path publication."""
        out = {str(k): str(v) for k, v in (env or {}).items() if v}
        out.setdefault("AGEVAL_WORKSPACE", WORKSPACE_PATH)
        out.setdefault("AGEVAL_ARTIFACTS", ARTIFACTS_PATH)
        out.setdefault("AGEVAL_EVALUATION", f"{BOX_ROOT}/evaluation")
        return out

    def _assert_started(self) -> None:
        if not self._started or self._sandbox is None:
            raise EnvironmentFailure("environment_not_started", "e2b sandbox is not started")
        if self._stopped:
            raise EnvironmentFailure("environment_stopped", "e2b sandbox is already killed")


class _SandboxStdin:
    """Write side of an attached command."""

    def __init__(self, handle: Any) -> None:
        self._handle = handle

    def write(self, payload: bytes) -> int:
        self._handle.send_stdin(payload.decode("utf-8", errors="replace"))
        return len(payload)

    def flush(self) -> None:
        return None


class _SandboxStdout:
    """Read side of an attached command, exposed as a byte stream."""

    def __init__(self, handle: Any) -> None:
        self._iterator = iter(handle)
        self._buffer = b""

    def read(self, size: int = -1) -> bytes:
        while size < 0 or len(self._buffer) < size:
            chunk = self._next_chunk()
            if chunk is None:
                break
            self._buffer += chunk
        if size < 0:
            payload, self._buffer = self._buffer, b""
            return payload
        payload, self._buffer = self._buffer[:size], self._buffer[size:]
        return payload

    def readline(self) -> bytes:
        while b"\n" not in self._buffer:
            chunk = self._next_chunk()
            if chunk is None:
                break
            self._buffer += chunk
        line, _, rest = self._buffer.partition(b"\n")
        self._buffer = rest
        return line + b"\n" if rest or line else b""

    def _next_chunk(self) -> bytes | None:
        for event in self._iterator:
            text = _stdout_from_event(event)
            if text:
                return text.encode("utf-8") if isinstance(text, str) else bytes(text)
        return None


def _stdout_from_event(event: Any) -> str | bytes | None:
    """Background ``commands.run`` yields ``(stdout, stderr, _)`` tuples."""
    if isinstance(event, tuple):
        return event[0] if event else None
    text = getattr(event, "stdout", None)
    return text if text else None


def _import_sdk() -> Any:
    try:
        import e2b  # type: ignore[import-not-found]
    except ImportError as exc:  # pragma: no cover — depends on the install extra
        raise EnvironmentFailure(
            "environment_preflight_failed",
            "the e2b kind needs the e2b extra: uv sync --extra e2b",
        ) from exc
    return e2b


def _walk_for_upload(source: Path, dest: str) -> list[tuple[Path, str]]:
    """File-by-file plan; a sandbox has no shared filesystem to copy into."""
    if source.is_file():
        return [(source, dest)]
    plan: list[tuple[Path, str]] = []
    for path in sorted(source.rglob("*")):
        if path.is_file():
            plan.append((path, f"{dest}/{path.relative_to(source).as_posix()}"))
    return plan


def _shell_line(argv: Sequence[str]) -> str:
    import shlex

    return " ".join(shlex.quote(str(part)) for part in argv)


def _seconds(raw: object, *, default: int) -> int:
    try:
        value = int(str(raw))
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


def _text(raw: object) -> str | None:
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    return None


__all__ = ["API_KEY_ENV", "E2BHost", "E2BStdio"]
