"""Document and package layout validation for Config Core."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from bora.config.capabilities import CapabilityCatalog
from bora.config.constants import ALLOWED_TOP_LEVEL_DIRS, ALLOWED_TOP_LEVEL_FILES
from bora.config.digest import normalize_package_relpath
from bora.config.errors import (
    ERROR_INVALID_FORMAT,
    ERROR_INVALID_PACKAGE,
    ERROR_INVALID_SCHEMA,
    ERROR_MISSING_REFERENCE,
    ERROR_PATH_OUTSIDE_PACKAGE,
    ERROR_UNKNOWN_PACKAGE_PATH,
    ERROR_UNKNOWN_PROFILE,
    ERROR_UNKNOWN_TASK,
    ERROR_UNSUPPORTED_CAPABILITY,
    ConfigError,
)
from bora.config.ports import PackageReader


def validate_top_level_layout(reader: PackageReader, root: Path) -> None:
    try:
        names = reader.list_top_level(root)
    except OSError as exc:
        raise ConfigError(
            ERROR_INVALID_PACKAGE,
            f"cannot list package root: {exc}",
            location=str(root),
        ) from exc

    for name in names:
        if name.startswith(".") or name == "__pycache__":
            # Hidden / interpreter caches are ignored (not package contract).
            continue
        path = root / name
        if path.is_dir():
            if name not in ALLOWED_TOP_LEVEL_DIRS:
                raise ConfigError(
                    ERROR_UNKNOWN_PACKAGE_PATH,
                    f"unknown top-level directory: {name}",
                    location=name,
                )
        else:
            if name not in ALLOWED_TOP_LEVEL_FILES:
                raise ConfigError(
                    ERROR_UNKNOWN_PACKAGE_PATH,
                    f"unknown top-level file: {name}",
                    location=name,
                )


def validate_document(
    reader: PackageReader,
    doc: dict[str, Any],
    *,
    task_id: str,
    root: Path,
    capabilities: CapabilityCatalog,
) -> None:
    fmt = doc.get("format")
    if not isinstance(fmt, str) or not fmt:
        raise ConfigError(ERROR_INVALID_FORMAT, "missing or invalid format", location="/format")
    if fmt == "bora.database/1":
        raise ConfigError(
            ERROR_INVALID_FORMAT,
            "task.yaml must use bora.task/1, not bora.database/1",
            location="/format",
        )
    if not capabilities.supports_format(fmt):
        raise ConfigError(
            ERROR_INVALID_FORMAT,
            f"unsupported format: {fmt}",
            location="/format",
        )

    yaml_task = doc.get("task_id")
    if not isinstance(yaml_task, str) or not yaml_task:
        raise ConfigError(ERROR_INVALID_SCHEMA, "missing task_id", location="/task_id")
    if yaml_task != task_id:
        raise ConfigError(
            ERROR_UNKNOWN_TASK,
            f"task_id mismatch: cli={task_id!r} yaml={yaml_task!r}",
            location="/task_id",
        )

    harness = doc.get("harness")
    if not isinstance(harness, dict):
        raise ConfigError(ERROR_INVALID_SCHEMA, "harness must be a mapping", location="/harness")
    runtime = harness.get("runtime")
    if not isinstance(runtime, str) or not capabilities.supports_harness_runtime(runtime):
        raise ConfigError(
            ERROR_UNSUPPORTED_CAPABILITY,
            f"unsupported harness.runtime: {runtime!r}",
            location="/harness/runtime",
        )
    entrypoint = harness.get("entrypoint")
    if not isinstance(entrypoint, str) or ":" not in entrypoint:
        raise ConfigError(
            ERROR_INVALID_SCHEMA,
            "harness.entrypoint must be module:function",
            location="/harness/entrypoint",
        )
    # Default package entry file is harness.py; only the file presence is checked.
    if not reader.exists(root, "harness.py"):
        raise ConfigError(
            ERROR_MISSING_REFERENCE,
            "harness.py not found for entrypoint",
            location="harness.py",
        )

    parameters = doc.get("parameters", {})
    if parameters is None:
        parameters = {}
    if not isinstance(parameters, dict):
        raise ConfigError(
            ERROR_INVALID_SCHEMA, "parameters must be a mapping", location="/parameters"
        )
    assert_json_compatible(parameters, "/parameters")

    provider = doc.get("provider")
    if not isinstance(provider, dict):
        raise ConfigError(ERROR_INVALID_SCHEMA, "provider must be a mapping", location="/provider")
    kind = provider.get("kind")
    if not isinstance(kind, str) or not capabilities.supports_provider_kind(kind):
        raise ConfigError(
            ERROR_UNSUPPORTED_CAPABILITY,
            f"unsupported provider.kind: {kind!r}",
            location="/provider/kind",
        )
    # L1 docker: package must ship environment/Dockerfile (or provider.dockerfile).
    if kind == "docker":
        df_raw = provider.get("dockerfile", "environment/Dockerfile")
        if not isinstance(df_raw, str) or not df_raw.strip():
            raise ConfigError(
                ERROR_INVALID_SCHEMA,
                "provider.dockerfile must be a non-empty relative path when set",
                location="/provider/dockerfile",
            )
        df_rel = df_raw.strip().lstrip("./")
        if df_rel.startswith("/") or ".." in Path(df_rel).parts:
            raise ConfigError(
                ERROR_PATH_OUTSIDE_PACKAGE,
                "provider.dockerfile must stay inside the package",
                location="/provider/dockerfile",
            )
        if not reader.exists(root, df_rel):
            raise ConfigError(
                ERROR_MISSING_REFERENCE,
                "docker L1 package requires Dockerfile at "
                f"{df_rel!r} (default environment/Dockerfile)",
                location=f"/provider/dockerfile:{df_rel}",
            )
        net = provider.get("network")
        if net is not None and net not in {"bridge", "none"}:
            raise ConfigError(
                ERROR_INVALID_SCHEMA,
                "provider.network must be bridge|none",
                location="/provider/network",
            )

    from bora.config.checks import require_agent_profiles_list

    profiles = require_agent_profiles_list(doc.get("agent_profiles") or [])
    profile_ids: set[str] = set()
    for idx, profile in enumerate(profiles):
        loc = f"/agent_profiles/{idx}"
        if not isinstance(profile, dict):
            raise ConfigError(ERROR_INVALID_SCHEMA, "profile must be a mapping", location=loc)
        pid = profile.get("id")
        if not isinstance(pid, str) or not pid:
            raise ConfigError(ERROR_INVALID_SCHEMA, "profile.id required", location=f"{loc}/id")
        if pid in profile_ids:
            raise ConfigError(
                ERROR_INVALID_SCHEMA, f"duplicate profile id: {pid}", location=f"{loc}/id"
            )
        profile_ids.add(pid)
        executor = profile.get("executor")
        if not isinstance(executor, str) or not capabilities.supports_executor_kind(executor):
            raise ConfigError(
                ERROR_UNSUPPORTED_CAPABILITY,
                f"unsupported executor: {executor!r}",
                location=f"{loc}/executor",
            )
        model = profile.get("model")
        if not isinstance(model, str) or not model:
            raise ConfigError(
                ERROR_INVALID_SCHEMA, "profile.model required", location=f"{loc}/model"
            )
        # Spec 19: executor: acp requires options.entry from static registry.
        # Packages must not override command/version/install.
        if executor == "acp":
            from bora.adapters.acp_registry import get_entry

            options = profile.get("options")
            if not isinstance(options, dict):
                raise ConfigError(
                    ERROR_INVALID_SCHEMA,
                    "executor acp requires options mapping with entry",
                    location=f"{loc}/options",
                )
            entry = options.get("entry")
            if not isinstance(entry, str) or not entry.strip():
                raise ConfigError(
                    ERROR_INVALID_SCHEMA,
                    "options.entry required for executor acp",
                    location=f"{loc}/options/entry",
                )
            for forbidden in (
                "command",
                "args",
                "detect_command",
                "install_command",
                "version",
                "acp_command",
                "engine_command",
                "acp_version",
                "credential_env_names",
            ):
                if forbidden in options:
                    raise ConfigError(
                        ERROR_INVALID_SCHEMA,
                        f"options.{forbidden} is not package-overridable for acp",
                        location=f"{loc}/options/{forbidden}",
                    )
            desc = get_entry(entry.strip())
            if desc is None:
                raise ConfigError(
                    ERROR_UNSUPPORTED_CAPABILITY,
                    f"unknown acp entry: {entry!r}",
                    location=f"{loc}/options/entry",
                )
            cleaned = {
                k: v
                for k, v in options.items()
                if k
                not in {
                    "command",
                    "args",
                    "detect_command",
                    "install_command",
                    "version",
                    "acp_command",
                    "engine_command",
                    "acp_version",
                    "credential_env_names",
                    "_acp_lock",
                }
            }
            cleaned["entry"] = entry.strip()
            profile["options"] = cleaned
        # Optional upstream routing (non-secret). api_key is an env *locator name*
        # only — values live in host/.env and are projected at invoke time.
        base_url = profile.get("base_url")
        if base_url is not None:
            if not isinstance(base_url, str) or not base_url.strip():
                raise ConfigError(
                    ERROR_INVALID_SCHEMA,
                    "profile.base_url must be a non-empty string when set",
                    location=f"{loc}/base_url",
                )
            if not (base_url.startswith("https://") or base_url.startswith("http://")):
                raise ConfigError(
                    ERROR_INVALID_SCHEMA,
                    "profile.base_url must start with http:// or https://",
                    location=f"{loc}/base_url",
                )
        api_key = profile.get("api_key")
        if api_key is not None:
            if not isinstance(api_key, str) or not api_key:
                raise ConfigError(
                    ERROR_INVALID_SCHEMA,
                    "profile.api_key must be a non-empty env locator name when set",
                    location=f"{loc}/api_key",
                )
            if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", api_key):
                raise ConfigError(
                    ERROR_INVALID_SCHEMA,
                    "profile.api_key must be an environment variable name "
                    "(locator only; never a secret value)",
                    location=f"{loc}/api_key",
                )
            # Fail closed on values that look like embedded secrets, not locators.
            if api_key.startswith("sk-") or len(api_key) > 64:
                raise ConfigError(
                    ERROR_INVALID_SCHEMA,
                    "profile.api_key looks like a secret value; use env var name only",
                    location=f"{loc}/api_key",
                )

    # L1 multi-actor logical topology (lock-safe only; no physical fields).
    if isinstance(provider, dict) and provider.get("agent_isolation") is not None:
        from bora.provider.isolation import validate_agent_isolation_in_provider

        validate_agent_isolation_in_provider(provider, profile_ids=profile_ids)

    # parameters.models.* must reference known profile ids when present.
    models = parameters.get("models") if isinstance(parameters, dict) else None
    if isinstance(models, dict):
        for key, ref in models.items():
            if not isinstance(ref, str):
                raise ConfigError(
                    ERROR_INVALID_SCHEMA,
                    "parameters.models values must be profile id strings",
                    location=f"/parameters/models/{key}",
                )
            if ref not in profile_ids:
                raise ConfigError(
                    ERROR_UNKNOWN_PROFILE,
                    f"unknown agent profile reference: {ref}",
                    location=f"/parameters/models/{key}",
                )

    environment = doc.get("environment")
    if environment is not None:
        if not isinstance(environment, dict):
            raise ConfigError(
                ERROR_INVALID_SCHEMA,
                "environment must be a mapping or null",
                location="/environment",
            )
        ekind = environment.get("kind")
        if not isinstance(ekind, str) or not capabilities.supports_environment_kind(ekind):
            raise ConfigError(
                ERROR_UNSUPPORTED_CAPABILITY,
                f"unsupported environment.kind: {ekind!r}",
                location="/environment/kind",
            )

    limits = doc.get("limits")
    if not isinstance(limits, dict):
        raise ConfigError(ERROR_INVALID_SCHEMA, "limits must be a mapping", location="/limits")
    for key in ("wall_time_seconds", "agent_invocations", "environment_actions", "memory_mb"):
        if key in limits:
            val = limits[key]
            if not isinstance(val, int) or isinstance(val, bool) or val < 0:
                raise ConfigError(
                    ERROR_INVALID_SCHEMA,
                    f"limits.{key} must be a non-negative integer",
                    location=f"/limits/{key}",
                )

    artifacts = doc.get("artifacts")
    if not isinstance(artifacts, dict):
        raise ConfigError(
            ERROR_INVALID_SCHEMA, "artifacts must be a mapping", location="/artifacts"
        )
    publishable = artifacts.get("publishable", [])
    if not isinstance(publishable, list):
        raise ConfigError(
            ERROR_INVALID_SCHEMA,
            "artifacts.publishable must be a list",
            location="/artifacts/publishable",
        )
    artifact_ids: set[str] = set()
    for idx, item in enumerate(publishable):
        loc = f"/artifacts/publishable/{idx}"
        if not isinstance(item, dict):
            raise ConfigError(
                ERROR_INVALID_SCHEMA, "artifact entry must be a mapping", location=loc
            )
        aid = item.get("id")
        if not isinstance(aid, str) or not aid:
            raise ConfigError(ERROR_INVALID_SCHEMA, "artifact.id required", location=f"{loc}/id")
        artifact_ids.add(aid)
        path = item.get("path")
        if not isinstance(path, str) or not path:
            raise ConfigError(
                ERROR_INVALID_SCHEMA, "artifact.path required", location=f"{loc}/path"
            )
        normalize_package_relpath(path)

    evaluation = doc.get("evaluation")
    if not isinstance(evaluation, dict):
        raise ConfigError(
            ERROR_INVALID_SCHEMA, "evaluation must be a mapping", location="/evaluation"
        )
    eruntime = evaluation.get("runtime")
    if not isinstance(eruntime, str) or not capabilities.supports_harness_runtime(eruntime):
        raise ConfigError(
            ERROR_UNSUPPORTED_CAPABILITY,
            f"unsupported evaluation.runtime: {eruntime!r}",
            location="/evaluation/runtime",
        )
    eentry = evaluation.get("entrypoint")
    if not isinstance(eentry, str) or ":" not in eentry:
        raise ConfigError(
            ERROR_INVALID_SCHEMA,
            "evaluation.entrypoint must be module:function",
            location="/evaluation/entrypoint",
        )
    if not reader.exists(root, "evaluator.py"):
        raise ConfigError(
            ERROR_MISSING_REFERENCE,
            "evaluator.py not found for evaluation.entrypoint",
            location="evaluator.py",
        )
    output = evaluation.get("output")
    if not isinstance(output, dict):
        raise ConfigError(
            ERROR_INVALID_SCHEMA, "evaluation.output required", location="/evaluation/output"
        )
    ofmt = output.get("format")
    if not isinstance(ofmt, str) or not capabilities.supports_evaluation_output_format(ofmt):
        raise ConfigError(
            ERROR_UNSUPPORTED_CAPABILITY,
            f"unsupported evaluation.output.format: {ofmt!r}",
            location="/evaluation/output/format",
        )
    inputs = evaluation.get("inputs", [])
    if not isinstance(inputs, list):
        raise ConfigError(
            ERROR_INVALID_SCHEMA,
            "evaluation.inputs must be a list",
            location="/evaluation/inputs",
        )
    for idx, inp in enumerate(inputs):
        loc = f"/evaluation/inputs/{idx}"
        if not isinstance(inp, dict):
            raise ConfigError(
                ERROR_INVALID_SCHEMA, "evaluation input must be a mapping", location=loc
            )
        if "artifact" in inp:
            ref = inp["artifact"]
            if ref not in artifact_ids:
                raise ConfigError(
                    ERROR_MISSING_REFERENCE,
                    f"evaluation input references unknown artifact: {ref}",
                    location=loc,
                )
        if "package_path" in inp:
            pp = inp["package_path"]
            if not isinstance(pp, str):
                raise ConfigError(
                    ERROR_INVALID_SCHEMA, "package_path must be a string", location=loc
                )
            rel = normalize_package_relpath(pp)
            # Ensure path stays inside package when present on disk; missing
            # optional files are still recorded as references for later phases.
            if ".." in Path(rel).parts:
                raise ConfigError(
                    ERROR_PATH_OUTSIDE_PACKAGE, f"path escapes package: {pp}", location=loc
                )


def collect_resolved_references(doc: dict[str, Any], root: Path) -> dict[str, Any]:
    """Collect logical, package-relative references for the lock summary."""
    refs: dict[str, Any] = {
        "harness_entrypoint": doc["harness"]["entrypoint"],
        "harness_module_file": "harness.py",
        "evaluation_entrypoint": doc["evaluation"]["entrypoint"],
        "evaluation_module_file": "evaluator.py",
        "artifacts": [],
        "evaluation_inputs": [],
    }
    for item in doc.get("artifacts", {}).get("publishable", []) or []:
        if isinstance(item, dict):
            refs["artifacts"].append(
                {
                    "id": item.get("id"),
                    "path": normalize_package_relpath(str(item.get("path", ""))),
                }
            )
    for inp in doc.get("evaluation", {}).get("inputs", []) or []:
        if not isinstance(inp, dict):
            continue
        entry: dict[str, Any] = {}
        if "artifact" in inp:
            entry["artifact"] = inp["artifact"]
        if "package_path" in inp:
            entry["package_path"] = normalize_package_relpath(str(inp["package_path"]))
        if "target" in inp:
            entry["target"] = str(inp["target"])
        refs["evaluation_inputs"].append(entry)
    # root is intentionally unused in the summary (no host absolute paths).
    _ = root
    return refs


def assert_json_compatible(value: Any, location: str) -> None:
    if value is None or isinstance(value, str | int | float | bool):
        return
    if isinstance(value, list):
        for i, item in enumerate(value):
            assert_json_compatible(item, f"{location}/{i}")
        return
    if isinstance(value, dict):
        for k, v in value.items():
            if not isinstance(k, str):
                raise ConfigError(
                    ERROR_INVALID_SCHEMA,
                    "mapping keys must be strings",
                    location=location,
                )
            assert_json_compatible(v, f"{location}/{k}")
        return
    raise ConfigError(
        ERROR_INVALID_SCHEMA,
        f"unsupported value type: {type(value).__name__}",
        location=location,
    )
