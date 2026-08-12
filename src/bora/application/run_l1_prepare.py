"""L1 Attempt prepare helpers — image build, runtime, credential env projection."""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any

from bora.adapters.provider_docker import (
    DockerProvider,
    DockerRuntime,
    build_package_image,
    ensure_base_image,
    ensure_image_lock,
)
from bora.runtime.identity import IdentityFactory


def prepare_l1_runtime(
    package_root: Path, lock: Any, run_dir: Path, *, network_mode: str = "none"
) -> tuple[DockerProvider, DockerRuntime, dict[str, Any]]:
    from bora.application.extension_hooks import hook_prepare
    from bora.application.image_contribute_bake import (
        ImageContributeError,
        apply_image_contribute_bake,
    )
    from bora.config.model import thaw

    factory = IdentityFactory()
    run = factory.new_run()
    trial = factory.new_trial(run, lock.digest)
    attempt = factory.new_attempt(trial)
    package_root = package_root.resolve()
    provider = thaw(lock.provider) if hasattr(lock, "provider") else {}
    if not isinstance(provider, dict):
        provider = {}
    dockerfile_rel = str(provider.get("dockerfile") or "environment/Dockerfile")
    platform = str(provider.get("platform") or "linux/arm64")
    # Official base (FROM bora-attempt:l1) then package Dockerfile → Attempt image.
    ensure_base_image(Path.cwd())
    short = lock.digest.replace("sha256:", "")[:12]
    tag = f"bora-pkg:{lock.task_id}-{short}"
    pkg_image = build_package_image(
        package_root=package_root,
        dockerfile_rel=dockerfile_rel,
        platform=platform,
        tag=tag,
        repo_root=Path.cwd(),
    )
    # Lifecycle prepare + image_contribute consume (fail closed).
    hook_prepare(lock, {"phase": "l1_prepare", "package_image": pkg_image.image_tag})
    try:
        pkg_image, contribute_meta = apply_image_contribute_bake(
            lock=lock,
            base_image=pkg_image,
            platform=platform,
        )
    except ImageContributeError as exc:
        raise RuntimeError(f"{exc.kind}:{exc.message}") from exc

    lock_path = Path.cwd() / ".bora" / "runtime-images" / "provider-l1.json"
    if not lock_path.is_file():
        lock_path = ensure_image_lock(Path.cwd())
    docker = DockerProvider(image_lock_path=lock_path)
    work = run_dir / "l1-work"
    if work.exists():
        shutil.rmtree(work)
    runtime = docker.prepare(
        attempt,
        package_root=package_root,
        work_root=work,
        network_mode=network_mode,
        hide_evaluation=True,
        image_lock=pkg_image,
    )
    meta = {
        "containment": "full_l1_attempt",
        "image": runtime.image_lock.image_digest if runtime.image_lock else "",
        "image_tag": runtime.image_lock.image_tag if runtime.image_lock else "",
        "package_dockerfile": dockerfile_rel,
        "platform": runtime.image_lock.platform if runtime.image_lock else "",
        "attempt_id": attempt.value,
        "policy": dict(runtime.policy_digests),
        "image_contribute": contribute_meta,
    }
    return docker, runtime, meta


def seed_l1_workspace(
    *,
    package_root: Path,
    workspace_host: Path,
    allow_offline_agent: bool,
    l1_meta: dict[str, Any],
) -> None:
    """Seed Attempt workspace from package data/ and optional solution/."""
    workspace_host.mkdir(parents=True, exist_ok=True)
    data_dir = package_root / "data"
    if data_dir.is_dir():
        for src in data_dir.iterdir():
            if src.is_file():
                shutil.copy2(src, workspace_host / src.name)
    # Isolation / offline fixture: copy solution/* into workspace without Runtime invoke.
    if allow_offline_agent or os.environ.get("BORA_L1_USE_SOLUTION") == "1":
        solution_dir = package_root / "solution"
        if solution_dir.is_dir():
            for src in solution_dir.iterdir():
                if src.is_file():
                    shutil.copy2(src, workspace_host / src.name)
            l1_meta["solution_seed"] = True


def cli_env_for_container(
    kind: str, *, api_key_env: str | None, base_url: str | None
) -> dict[str, str]:
    """Project host credentials into docker ``-e`` (values never logged).

    Never copy host ``PATH`` / ``HOME`` / ``XDG_*`` — those are macOS/Linux host
    paths and break in-container engines (e.g. opencode ``mkdir /Users``).
    Callers set container ``HOME`` / ``PATH`` after this returns.
    """
    from bora.adapters.child_env import project_cli_child_env

    if kind in {"codex"}:
        env: dict[str, str] = {}
        if api_key_env and os.environ.get(api_key_env):
            env[api_key_env] = os.environ[api_key_env]
            env.setdefault("OPENAI_API_KEY", os.environ[api_key_env])
        elif os.environ.get("OPENAI_API_KEY"):
            env["OPENAI_API_KEY"] = os.environ["OPENAI_API_KEY"]
        if base_url:
            env["OPENAI_BASE_URL"] = base_url
        return env
    projected = project_cli_child_env(
        kind if kind != "claude" else "claude-code",
        api_key_env=api_key_env,
        base_url=base_url,
    )
    # Credential + terminal locale only — no host filesystem path env.
    keep_prefixes = (
        "ZAI_",
        "ZHIPU",
        "OPENAI_",
        "ANTHROPIC_",
        "OPENCODE_",
        "XAI_",
        "LANG",
        "TERM",
        "LC_",
    )
    host_path_denylist = {
        "PATH",
        "HOME",
        "XDG_DATA_HOME",
        "XDG_CONFIG_HOME",
        "XDG_CACHE_HOME",
        "XDG_STATE_HOME",
        "TMPDIR",
        "TEMP",
        "TMP",
    }
    out = {
        k: v
        for k, v in projected.items()
        if v
        and k not in host_path_denylist
        and (k.startswith(keep_prefixes) or (api_key_env and k == api_key_env))
    }
    return out


def make_l1_target_executor_factory(
    *,
    ledger: Any,
    profiles: list[dict[str, Any]],
    workspace_host: Path | None = None,
    package_root: Path | None = None,
) -> Any:
    """Build ``make_target_executor`` closed over prepare ledger + profiles.

    - ``acp``: docker exec into Attempt container (coding-agent path).
    - ``nooa``: docker exec baked ``bora-executor-nooa`` worker (L1 Ready).
      Parent host SPI is **not** an L1 success path.
    """
    del workspace_host, package_root  # L1 nooa uses container package mount only.

    def make_target_executor(binding: Any) -> Any:
        from bora.adapters.acp import AcpExecutor
        from bora.adapters.acp_registry import get_entry
        from bora.adapters.agent_container import effective_run_gid
        from bora.adapters.nooa_container import NooaContainerExecutor

        actor_id = binding.actor_id
        if not actor_id:
            raise RuntimeError("actor_id_required")
        phys = ledger.actors.get(actor_id)
        if phys is None:
            raise RuntimeError("unknown_actor")
        target = ledger.targets.get(phys.target_id)
        if target is None or target.state != "ready" or not target.container_id:
            raise RuntimeError("target_dead")
        if binding.generation is not None and binding.generation != target.generation:
            raise RuntimeError("generation_mismatch")
        if binding.target_id and binding.target_id != target.target_id:
            raise RuntimeError("target_mismatch")

        profile = next((p for p in profiles if p.get("id") == binding.profile_id), {})
        api_key_env = (
            str(profile.get("api_key")).strip()
            if isinstance(profile.get("api_key"), str) and profile.get("api_key")
            else None
        )
        base_url = (
            str(profile.get("base_url")).strip()
            if isinstance(profile.get("base_url"), str) and profile.get("base_url")
            else None
        )
        kind = str(binding.executor_kind)

        # nooa L1 Ready = in-container worker (never parent SPI success).
        if kind == "nooa":
            if os.environ.get("BORA_NOOA_HOST_IN_CONTAINER") == "1":
                raise RuntimeError(
                    "nooa_host_in_container_removed: "
                    "L1 Ready is in-container worker only; "
                    "unset BORA_NOOA_HOST_IN_CONTAINER"
                )
            opts: dict[str, Any] = {}
            raw_opts = profile.get("options") if isinstance(profile, dict) else None
            if isinstance(raw_opts, dict):
                opts = raw_opts
            graph = getattr(binding, "extension_graph", None)
            if graph is not None:
                providers = getattr(graph, "providers", None) or {}
                pref = providers.get("executor")
                impl = getattr(pref, "impl", None) if pref is not None else None
                impl_opts = getattr(impl, "options", None) if impl is not None else None
                if isinstance(impl_opts, dict):
                    opts = {**opts, **impl_opts}
                agent_from_impl = getattr(impl, "agent_ref", None) if impl is not None else None
                method_from_impl = getattr(impl, "method", None) if impl is not None else None
            else:
                agent_from_impl = None
                method_from_impl = None
            agent_ref = str(agent_from_impl or opts.get("agent") or "").strip()
            if not agent_ref:
                raise RuntimeError("nooa_options_agent_required")
            method = str(method_from_impl or opts.get("method") or "run").strip() or "run"
            run_gid = effective_run_gid(phys)
            return NooaContainerExecutor(
                container_id=str(target.container_id),
                agent_ref=agent_ref,
                method=method,
                model=str(getattr(binding, "model", None) or "nooa"),
                uid=int(phys.uid),
                gid=int(run_gid),
            )

        # L1 coding-agent path is ACP only — no private CLI scrape residual.
        if kind != "acp":
            raise RuntimeError(
                f"migrated_to_acp: L1 executor {kind!r} requires executor: acp + options.entry "
                f"(or nooa in-container Ready after image_contribute bake)"
            )
        entry_id = getattr(binding, "acp_entry_id", None)
        if not entry_id:
            options = profile.get("options") if isinstance(profile, dict) else {}
            if isinstance(options, dict):
                entry_id = options.get("entry")
        if not entry_id:
            raise RuntimeError("acp_entry_required")
        desc = get_entry(str(entry_id))
        if desc is None:
            raise RuntimeError("unknown_acp_entry")
        child_env = cli_env_for_container(str(entry_id), api_key_env=api_key_env, base_url=base_url)
        home = phys.home_container
        child_env["HOME"] = home
        child_env["CODEX_HOME"] = f"{home}/.codex"
        # Force container PATH (projection never carries host PATH after fix).
        child_env["PATH"] = "/usr/local/bin:/usr/bin:/bin"
        child_env.setdefault("TERM", "xterm")
        child_env["NO_BROWSER"] = "1"
        child_env.setdefault("XDG_CONFIG_HOME", f"{home}/.config")
        child_env.setdefault("XDG_CACHE_HOME", f"{home}/.cache")
        child_env.setdefault("XDG_STATE_HOME", f"{home}/.local/state")
        child_env.setdefault("XDG_DATA_HOME", f"{home}/.local/share")
        for k, v in desc.fixed_env.items():
            child_env.setdefault(str(k), str(v))
        workdir = "/attempt/workspace"
        run_gid = effective_run_gid(phys)
        docker_cmd: list[str] = [
            "docker",
            "exec",
            "-i",
            "-u",
            f"{phys.uid}:{run_gid}",
            "-w",
            workdir,
        ]
        for ek, ev in child_env.items():
            if str(ek).upper() in {"DOCKER_HOST", "DOCKER_SOCK"}:
                continue
            docker_cmd.extend(["-e", f"{ek}={ev}"])
        docker_cmd.append(str(target.container_id))
        # shared_write collaboration: group-writable new files under shared GID.
        acp_argv = list(desc.acp_command)
        if phys.shared_gid is not None and phys.shared_write:
            docker_cmd.extend(["sh", "-c", 'umask 002; exec "$@"', "bora-actor", *acp_argv])
        else:
            docker_cmd.extend(acp_argv)
        return AcpExecutor(
            entry_id=str(entry_id),
            model=str(binding.model),
            descriptor=desc,
            workdir=workdir,
            api_key_env=api_key_env,
            base_url=base_url,
            command_override=docker_cmd,
        )

    return make_target_executor
