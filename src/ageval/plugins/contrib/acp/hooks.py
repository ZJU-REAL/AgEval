"""ACP ``after_environment_ready`` hook: probe the box, install only if missing.

The recipe comes from ``acp_entries.json``. Nothing here hardcodes a package
manager: if the box image already baked the entry, the probe hits and this hook
does nothing.
"""

from __future__ import annotations

from typing import Any

from ageval.environments.protocol import EnvironmentFailure
from ageval.plugins.contrib.acp.child_env import entry_credentials_missing
from ageval.plugins.contrib.acp.registry import AcpEntryDescriptor, get_entry
from ageval.plugins.errors import ExtensionMaterializeError
from ageval.plugins.protocol import NextFn

# Runs before the task's own setup.sh (500) and after cheaper box preparation.
ENSURE_RUNTIME_PRIORITY = 100


def ensure_runtime(**kwargs: Any) -> Any:
    """Factory: bind the entry and its credential locator, return the handler."""
    options = dict(kwargs.get("options") or {})
    entry_id = str(options.get("entry") or "").strip()
    if not entry_id:
        raise ExtensionMaterializeError(
            "acp_entry_required",
            kind="extension_materialize_failed",
        )
    descriptor = get_entry(entry_id)
    if descriptor is None:
        raise ExtensionMaterializeError(
            f"unknown acp entry: {entry_id!r}",
            kind="extension_materialize_failed",
        )
    api_key_env = kwargs.get("api_key")

    async def _handler(ctx: Any, value: Any, nxt: NextFn) -> Any:
        await _prepare_attempt_home(ctx, descriptor, api_key_env=api_key_env)
        await _ensure_entry_present(ctx, descriptor)
        return await nxt(value)

    return _handler


async def _prepare_attempt_home(
    ctx: Any,
    descriptor: AcpEntryDescriptor,
    *,
    api_key_env: str | None,
) -> None:
    """Give the entry its own HOME, and refuse to run it with no credential.

    An entry authenticates either from a file it declared (BYOA) or from a host
    env name it declared (BYOK). With neither, this fails once here — before any
    Agent effect — instead of letting the entry start and time out on auth.
    """
    from ageval.plugins.contrib.acp.home import prepare_home

    prepared = await prepare_home(
        ctx.host,
        descriptor,
        timeout_sec=ctx.remaining_seconds(),
    )
    auth_files = prepared["auth_files"]
    ctx.record_fact(
        "acp_home_prepared",
        {"entry": descriptor.entry_id, "auth_files": auth_files},
    )
    if not auth_files and entry_credentials_missing(
        descriptor.credential_env_names,
        api_key_env=api_key_env,
    ):
        raise EnvironmentFailure(
            "acp_credentials_missing",
            f"acp entry {descriptor.entry_id!r} has neither a declared auth file on this "
            f"host nor any of {list(descriptor.credential_env_names)} set",
        )


async def _ensure_entry_present(ctx: Any, descriptor: AcpEntryDescriptor) -> None:
    host = ctx.host
    wanted = _needed_commands(descriptor)
    missing = [name for name in wanted if not await _present(host, name, ctx=ctx)]
    ctx.record_fact(
        "acp_runtime_probe",
        {"entry": descriptor.entry_id, "wanted": wanted, "missing": missing},
    )
    if not missing:
        return
    if not descriptor.install_command:
        raise EnvironmentFailure(
            "acp_runtime_missing",
            f"acp entry {descriptor.entry_id!r} needs {missing} in the box and "
            "declares no install command",
        )
    result = await host.exec(
        ["bash", "-lc", descriptor.install_command],
        timeout_sec=ctx.remaining_seconds(),
    )
    ctx.record_fact(
        "acp_runtime_install",
        {"entry": descriptor.entry_id, "exit_code": result.exit_code},
    )
    if result.exit_code != 0:
        raise EnvironmentFailure(
            "acp_runtime_install_failed",
            f"installing acp entry {descriptor.entry_id!r} exited "
            f"{result.exit_code}: {result.stderr.strip()[-500:]}",
        )
    still_missing = [name for name in missing if not await _present(host, name, ctx=ctx)]
    if still_missing:
        raise EnvironmentFailure(
            "acp_runtime_missing",
            f"acp entry {descriptor.entry_id!r} still missing {still_missing} after install",
        )


def _needed_commands(descriptor: AcpEntryDescriptor) -> list[str]:
    """First detect command of each family the entry needs inside the box."""
    names: list[str] = []
    if descriptor.integration_mode == 1 and descriptor.engine_detect_commands:
        names.append(descriptor.engine_detect_commands[0])
    if descriptor.acp_detect_commands:
        names.append(descriptor.acp_detect_commands[0])
    seen: set[str] = set()
    out: list[str] = []
    for name in names:
        token = name.strip().split()[0] if name.strip() else ""
        if token and token not in seen:
            seen.add(token)
            out.append(token)
    return out


async def _present(host: Any, command: str, *, ctx: Any) -> bool:
    result = await host.exec(
        ["bash", "-lc", f"command -v {command}"],
        timeout_sec=ctx.remaining_seconds(),
    )
    return result.exit_code == 0
