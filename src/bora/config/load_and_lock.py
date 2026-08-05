"""Config Core façade: load, merge, validate, canonicalize, digest, freeze.

This module is the only normative reader of member ``task.yaml``. It never imports or
executes package-local Python, never expands environment variables as experiment
semantics, and never starts an Attempt.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yaml

from bora.config.capabilities import CapabilityCatalog
from bora.config.errors import (
    ERROR_INVALID_FORMAT,
    ERROR_INVALID_OVERRIDE,
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
from bora.config.model import (
    LockedTaskConfig,
    ResolutionEntry,
    ResolutionRecord,
    freeze,
)
from bora.config.ports import PackageReader

# Package top-level allowlist (design/02). Unknown first-level paths fail closed.
ALLOWED_TOP_LEVEL_FILES = frozenset(
    {
        "README.md",
        "task.yaml",
        "harness.py",
        "evaluator.py",
        # Common non-runtime root files operators may keep without failing lock.
        ".gitignore",
        "pyproject.toml",
        "uv.lock",
        "requirements.txt",
    }
)
ALLOWED_TOP_LEVEL_DIRS = frozenset(
    {
        "prompts",
        "schemas",
        "environment",
        "evaluation",
        "data",
        "lib",
        "upstream",
        "solution",
    }
)

# JSON Pointers that CLI ``--set`` may override in v0.1.
ALLOWLISTED_OVERRIDE_POINTERS = frozenset(
    {
        "/parameters/seed",
        "/parameters/active_profile",
        "/limits/wall_time_seconds",
        "/limits/agent_invocations",
        "/limits/environment_actions",
        "/limits/memory_mb",
    }
)

# Explicit defaults applied after reading task.yaml, before variant/overrides.
# Every allowlisted override pointer leaf must exist after defaults so --set can set it.
DEFAULTS: dict[str, Any] = {
    "provider": {
        "kind": "local",
        "assurance": "l0",
    },
    "limits": {
        "wall_time_seconds": 300,
        "agent_invocations": 1,
        "environment_actions": 0,
        "memory_mb": 512,
    },
    "artifacts": {
        "publishable": [],
    },
    "agent_profiles": [],
    "environment": None,
}


class _UniqueKeyLoader(yaml.SafeLoader):
    """SafeLoader that rejects duplicate mapping keys (YAML normally overwrites)."""


def _construct_mapping(loader: yaml.SafeLoader, node: yaml.nodes.MappingNode, deep: bool = False):
    mapping: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)  # type: ignore[arg-type]
        if key in mapping:
            raise ConfigError(
                ERROR_INVALID_SCHEMA,
                f"duplicate key in YAML mapping: {key!r}",
                location="task.yaml",
            )
        mapping[key] = loader.construct_object(value_node, deep=deep)  # type: ignore[arg-type]
    return mapping


_UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_mapping,  # type: ignore[arg-type]
)


def _parse_yaml(text: str) -> Any:
    try:
        data = yaml.load(text, Loader=_UniqueKeyLoader)
    except ConfigError:
        raise
    except yaml.YAMLError as exc:
        raise ConfigError(
            ERROR_INVALID_SCHEMA, f"invalid YAML: {exc}", location="task.yaml"
        ) from exc
    if data is None:
        raise ConfigError(ERROR_INVALID_SCHEMA, "empty task.yaml", location="task.yaml")
    if not isinstance(data, dict):
        raise ConfigError(
            ERROR_INVALID_SCHEMA,
            "task.yaml root must be a mapping",
            location="task.yaml",
        )
    return data


def _deep_merge(base: dict[str, Any], overlay: Mapping[str, Any]) -> dict[str, Any]:
    """Deep-merge overlay onto base; mappings merge, other values replace."""
    result = copy.deepcopy(base)
    for key, value in overlay.items():
        existing = result.get(key)
        if isinstance(existing, dict) and isinstance(value, Mapping):
            result[key] = _deep_merge(existing, value)
        else:
            result[key] = copy.deepcopy(value)
    return result


_JSON_POINTER_RE = re.compile(r"^(/[^/]*)+$|^$")


def parse_set_override(raw: str) -> tuple[str, Any]:
    """Parse ``<JSON Pointer>=<JSON value>`` into a pointer and decoded value."""
    if "=" not in raw:
        raise ConfigError(
            ERROR_INVALID_OVERRIDE,
            "override must be <JSON Pointer>=<JSON value>",
            location=raw,
        )
    pointer, _, value_text = raw.partition("=")
    if not pointer.startswith("/"):
        raise ConfigError(
            ERROR_INVALID_OVERRIDE,
            "JSON Pointer must start with /",
            location=pointer,
        )
    if pointer not in ALLOWLISTED_OVERRIDE_POINTERS:
        raise ConfigError(
            ERROR_INVALID_OVERRIDE,
            f"pointer not allowlisted for override: {pointer}",
            location=pointer,
        )
    try:
        value = json.loads(value_text)
    except json.JSONDecodeError as exc:
        raise ConfigError(
            ERROR_INVALID_OVERRIDE,
            f"override value is not valid JSON: {value_text!r}",
            location=pointer,
        ) from exc
    return pointer, value


def apply_json_pointer(doc: dict[str, Any], pointer: str, value: Any) -> None:
    """Set an allowlisted leaf via JSON Pointer (no document-root structural replace)."""
    if pointer == "" or pointer == "/":
        raise ConfigError(ERROR_INVALID_OVERRIDE, "cannot replace document root", location=pointer)
    parts = [p for p in pointer.split("/") if p != ""]
    # Unescape JSON Pointer tokens (~1 → /, ~0 → ~).
    tokens = [p.replace("~1", "/").replace("~0", "~") for p in parts]
    cursor: Any = doc
    for token in tokens[:-1]:
        if not isinstance(cursor, dict) or token not in cursor:
            raise ConfigError(
                ERROR_INVALID_OVERRIDE,
                f"override path missing intermediate key: {token}",
                location=pointer,
            )
        cursor = cursor[token]
        if not isinstance(cursor, dict):
            raise ConfigError(
                ERROR_INVALID_OVERRIDE,
                "cannot descend into non-object for override",
                location=pointer,
            )
    leaf = tokens[-1]
    if not isinstance(cursor, dict):
        raise ConfigError(
            ERROR_INVALID_OVERRIDE, "override target parent is not an object", location=pointer
        )
    if leaf not in cursor:
        # Allow setting known leaves that defaults may have created; reject unknown structure.
        raise ConfigError(
            ERROR_INVALID_OVERRIDE,
            f"override target key does not exist: {leaf}",
            location=pointer,
        )
    # Refuse replacing entire objects/arrays via allowlisted leaf pointers with wrong types
    # only when the existing value is a mapping and new value tries full structure swap of roots.
    existing = cursor[leaf]
    if isinstance(existing, dict) and not isinstance(value, dict):
        raise ConfigError(
            ERROR_INVALID_OVERRIDE,
            "cannot replace object with non-object via override",
            location=pointer,
        )
    cursor[leaf] = value


def canonical_json_bytes(payload: Mapping[str, Any]) -> bytes:
    """UTF-8 canonical JSON: sorted object keys, arrays preserve order, no whitespace."""
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def digest_payload(payload: Mapping[str, Any]) -> str:
    """Return ``sha256:<64 lowercase hex>`` over the canonical payload."""
    digest = hashlib.sha256(canonical_json_bytes(payload)).hexdigest()
    return f"sha256:{digest}"


def normalize_package_relpath(path: str) -> str:
    """Normalize a package-relative path for stable digests (posix, no host abs)."""
    p = path.replace("\\", "/").strip()
    while p.startswith("./"):
        p = p[2:]
    if p.startswith("/") or p.startswith("..") or "/../" in f"/{p}/":
        raise ConfigError(
            ERROR_PATH_OUTSIDE_PACKAGE,
            f"path not package-relative: {path}",
            location=path,
        )
    return p


class ConfigCore:
    """Normative Config Core façade."""

    def __init__(self, package_reader: PackageReader) -> None:
        self._reader = package_reader

    def load_and_lock(
        self,
        package_root: Path,
        task_id: str,
        *,
        variant: Mapping[str, object] | None = None,
        overrides: Mapping[str, object] | None = None,
        capabilities: CapabilityCatalog,
    ) -> LockedTaskConfig:
        """Read, merge, validate, canonicalize, digest, and freeze a task package.

        Parameters
        ----------
        package_root:
            Directory containing ``task.yaml`` (Database member task root).
        task_id:
            Must equal ``task.yaml`` ``task_id`` (operator-selected task).
        variant:
            Optional Campaign variant overlay (merge step 2). CLI does not expose
            this in v0.1; tests exercise the merge order.
        overrides:
            Explicit overrides as a mapping of JSON Pointer → value (merge step 3).
        capabilities:
            Declaration-only catalog used for kind/format recognition.
        """
        try:
            root = self._reader.resolve_root(package_root)
        except (OSError, FileNotFoundError) as exc:
            raise ConfigError(
                ERROR_INVALID_PACKAGE,
                f"cannot open package root: {package_root}",
                location=str(package_root),
            ) from exc

        self._validate_top_level_layout(root)

        if not self._reader.exists(root, "task.yaml"):
            raise ConfigError(
                ERROR_INVALID_PACKAGE,
                "task.yaml not found",
                location="task.yaml",
            )

        try:
            text = self._reader.read_text(root, "task.yaml")
        except (OSError, ValueError) as exc:
            raise ConfigError(
                ERROR_INVALID_PACKAGE,
                f"cannot read task.yaml: {exc}",
                location="task.yaml",
            ) from exc

        # Reject env-style interpolation markers so experiment semantics stay in yaml.
        if "${" in text or "os.environ" in text:
            raise ConfigError(
                ERROR_INVALID_SCHEMA,
                "environment variable interpolation is not allowed in task.yaml",
                location="task.yaml",
            )

        raw = _parse_yaml(text)
        resolution: list[ResolutionEntry] = [
            ResolutionEntry(source="task.yaml", pointer="/", note="task document"),
        ]

        # Apply explicit defaults for missing top-level sections / known keys.
        merged = copy.deepcopy(raw)
        for key, default_value in DEFAULTS.items():
            if key not in merged or merged[key] is None:
                merged[key] = copy.deepcopy(default_value)
                resolution.append(
                    ResolutionEntry(source="default", pointer=f"/{key}", note="explicit default")
                )
            elif isinstance(default_value, dict) and isinstance(merged.get(key), dict):
                for d_key, d_val in default_value.items():
                    if d_key not in merged[key]:
                        merged[key][d_key] = copy.deepcopy(d_val)
                        resolution.append(
                            ResolutionEntry(
                                source="default",
                                pointer=f"/{key}/{d_key}",
                                note="explicit default",
                            )
                        )

        if variant:
            merged = _deep_merge(merged, dict(variant))
            resolution.append(
                ResolutionEntry(source="campaign-variant", pointer="/", note="variant overlay")
            )

        if overrides:
            for pointer, value in overrides.items():
                pointer_s = str(pointer)
                if pointer_s not in ALLOWLISTED_OVERRIDE_POINTERS:
                    raise ConfigError(
                        ERROR_INVALID_OVERRIDE,
                        f"pointer not allowlisted for override: {pointer_s}",
                        location=pointer_s,
                    )
                apply_json_pointer(merged, pointer_s, value)
                resolution.append(
                    ResolutionEntry(
                        source="cli-override", pointer=pointer_s, note="explicit override"
                    )
                )

        self._validate_document(merged, task_id=task_id, root=root, capabilities=capabilities)
        resolved_refs = self._collect_resolved_references(merged, root)

        # Freeze section views.
        format_id = str(merged["format"])
        locked_task_id = str(merged["task_id"])
        harness = freeze(merged["harness"])
        parameters = freeze(merged.get("parameters") or {})
        provider = freeze(merged["provider"])
        profiles_raw = merged.get("agent_profiles") or []
        if not isinstance(profiles_raw, list):
            raise ConfigError(
                ERROR_INVALID_SCHEMA, "agent_profiles must be a list", location="/agent_profiles"
            )
        agent_profiles = tuple(freeze(p) for p in profiles_raw)
        environment = (
            freeze(merged["environment"]) if merged.get("environment") is not None else None
        )
        limits = freeze(merged["limits"])
        artifacts = freeze(merged["artifacts"])
        evaluation = freeze(merged["evaluation"])
        resolution_record = ResolutionRecord(entries=tuple(resolution))
        resolved_references = freeze(resolved_refs)

        # Build digest over a stable payload without the digest field.
        provisional = LockedTaskConfig(
            format=format_id,
            task_id=locked_task_id,
            harness=harness,  # type: ignore[arg-type]
            parameters=parameters,  # type: ignore[arg-type]
            provider=provider,  # type: ignore[arg-type]
            agent_profiles=agent_profiles,  # type: ignore[arg-type]
            environment=environment,  # type: ignore[arg-type]
            limits=limits,  # type: ignore[arg-type]
            artifacts=artifacts,  # type: ignore[arg-type]
            evaluation=evaluation,  # type: ignore[arg-type]
            resolution=resolution_record,
            digest="",  # filled below
            resolved_references=resolved_references,  # type: ignore[arg-type]
        )
        payload = provisional.canonical_payload()
        digest = digest_payload(payload)

        return LockedTaskConfig(
            format=format_id,
            task_id=locked_task_id,
            harness=harness,  # type: ignore[arg-type]
            parameters=parameters,  # type: ignore[arg-type]
            provider=provider,  # type: ignore[arg-type]
            agent_profiles=agent_profiles,  # type: ignore[arg-type]
            environment=environment,  # type: ignore[arg-type]
            limits=limits,  # type: ignore[arg-type]
            artifacts=artifacts,  # type: ignore[arg-type]
            evaluation=evaluation,  # type: ignore[arg-type]
            resolution=resolution_record,
            digest=digest,
            resolved_references=resolved_references,  # type: ignore[arg-type]
        )

    def _validate_top_level_layout(self, root: Path) -> None:
        try:
            names = self._reader.list_top_level(root)
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

    def _validate_document(
        self,
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
            raise ConfigError(
                ERROR_INVALID_SCHEMA, "harness must be a mapping", location="/harness"
            )
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
        if not self._reader.exists(root, "harness.py"):
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
        self._assert_json_compatible(parameters, "/parameters")

        provider = doc.get("provider")
        if not isinstance(provider, dict):
            raise ConfigError(
                ERROR_INVALID_SCHEMA, "provider must be a mapping", location="/provider"
            )
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
            if not self._reader.exists(root, df_rel):
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

        profiles = doc.get("agent_profiles") or []
        if not isinstance(profiles, list):
            raise ConfigError(
                ERROR_INVALID_SCHEMA, "agent_profiles must be a list", location="/agent_profiles"
            )
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
                # Materialize lock-safe snapshot onto profile (mutates pre-freeze dict).
                profile["options"] = {
                    **{k: v for k, v in options.items() if k == "entry"},
                    "entry": entry.strip(),
                    "_acp_lock": desc.as_lock_snapshot(),
                }
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
                if not (
                    base_url.startswith("https://") or base_url.startswith("http://")
                ):
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
                raise ConfigError(
                    ERROR_INVALID_SCHEMA, "artifact.id required", location=f"{loc}/id"
                )
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
        if not self._reader.exists(root, "evaluator.py"):
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

    def _collect_resolved_references(self, doc: dict[str, Any], root: Path) -> dict[str, Any]:
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

    def _assert_json_compatible(self, value: Any, location: str) -> None:
        if value is None or isinstance(value, str | int | float | bool):
            return
        if isinstance(value, list):
            for i, item in enumerate(value):
                self._assert_json_compatible(item, f"{location}/{i}")
            return
        if isinstance(value, dict):
            for k, v in value.items():
                if not isinstance(k, str):
                    raise ConfigError(
                        ERROR_INVALID_SCHEMA,
                        "mapping keys must be strings",
                        location=location,
                    )
                self._assert_json_compatible(v, f"{location}/{k}")
            return
        raise ConfigError(
            ERROR_INVALID_SCHEMA,
            f"unsupported value type: {type(value).__name__}",
            location=location,
        )
