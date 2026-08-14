"""Database-root ``profiles.yaml`` — job agent/model binding overlay (#59).

Task identity (member ``task.yaml``) declares **role slots** only.
Job binding (executor / entry / model / key locator) lives in Database
``profiles.yaml`` (or CLI ``--profiles`` / binding overrides) and is merged by
Config Core at ``load_and_lock`` time. Secrets never appear here — only env
locator names.
"""

from __future__ import annotations

import copy
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import yaml

from bora.config.errors import (
    ERROR_INVALID_FORMAT,
    ERROR_INVALID_PACKAGE,
    ERROR_INVALID_SCHEMA,
    ERROR_MISSING_BINDING,
    ConfigError,
)

PROFILES_FILENAME = "profiles.yaml"
PROFILES_FORMAT = "bora.profiles/1"

# Fields that constitute job binding — forbidden on member task.yaml slots.
BINDING_FIELD_KEYS = frozenset(
    {"executor", "model", "options", "api_key", "base_url", "extensions", "label"}
)

# Allowlisted nested binding override leaves under /bindings/<role_id>/…
_BINDING_OVERRIDE_LEAVES = frozenset(
    {
        "model",
        "executor",
        "api_key",
        "base_url",
    }
)

# Plugin options are an opaque map. These keys never ride the job axis.
_OPTIONS_DENYLIST = frozenset(
    {
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
)

_ROLE_ID_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]*$")


def load_profiles_document(path: Path) -> dict[str, dict[str, Any]]:
    """Load and validate a ``profiles.yaml`` (or alternate) file → bindings map."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError(
            ERROR_INVALID_PACKAGE,
            f"cannot read profiles file: {exc}",
            location=str(path),
        ) from exc

    from bora.config.checks import reject_env_interpolation

    reject_env_interpolation(text, what="profiles.yaml", location=str(path))

    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ConfigError(
            ERROR_INVALID_SCHEMA,
            f"invalid YAML: {exc}",
            location=str(path),
        ) from exc

    if data is None:
        raise ConfigError(ERROR_INVALID_SCHEMA, "empty profiles document", location=str(path))
    if not isinstance(data, dict):
        raise ConfigError(
            ERROR_INVALID_SCHEMA,
            "profiles document root must be a mapping",
            location=str(path),
        )
    return parse_profiles_mapping(data, location=str(path))


def load_database_profiles(database_root: Path) -> dict[str, dict[str, Any]]:
    """Load Database-root ``profiles.yaml`` when present; else empty bindings."""
    root = database_root.expanduser().resolve(strict=False)
    path = root / PROFILES_FILENAME
    if not path.is_file():
        return {}
    return load_profiles_document(path)


def resolve_profile_bindings(
    database_root: Path,
    *,
    profiles_path: Path | str | None = None,
) -> dict[str, dict[str, Any]]:
    """Resolve effective job bindings for a Database run.

    * ``profiles_path`` when set **replaces** Database-root ``profiles.yaml``
      entirely (alternate job overlay for the run).
    * Otherwise load Database-root ``profiles.yaml`` (may be empty).
    """
    if profiles_path is not None:
        path = Path(profiles_path).expanduser().resolve(strict=False)
        if not path.is_file():
            raise ConfigError(
                ERROR_INVALID_PACKAGE,
                f"profiles file not found: {profiles_path}",
                location=str(profiles_path),
            )
        return load_profiles_document(path)
    return load_database_profiles(database_root)


def parse_profiles_mapping(
    raw: Mapping[str, Any],
    *,
    location: str = "profiles.yaml",
) -> dict[str, dict[str, Any]]:
    """Validate profiles document and return ``{role_id: binding}``."""
    fmt = raw.get("format")
    if fmt is not None:
        if not isinstance(fmt, str) or not fmt:
            raise ConfigError(
                ERROR_INVALID_FORMAT,
                "missing or invalid format",
                location=f"{location}:/format",
            )
        if fmt != PROFILES_FORMAT:
            raise ConfigError(
                ERROR_INVALID_FORMAT,
                f"unsupported profiles format: {fmt}",
                location=f"{location}:/format",
            )

    bindings_raw = raw.get("bindings")
    if bindings_raw is None:
        raise ConfigError(
            ERROR_INVALID_SCHEMA,
            "profiles document requires bindings mapping",
            location=f"{location}:/bindings",
        )
    if not isinstance(bindings_raw, dict):
        raise ConfigError(
            ERROR_INVALID_SCHEMA,
            "bindings must be a mapping of role id → binding",
            location=f"{location}:/bindings",
        )

    allowed_top = {"format", "bindings"}
    unknown_top = set(raw) - allowed_top
    if unknown_top:
        raise ConfigError(
            ERROR_INVALID_SCHEMA,
            f"unknown profiles keys: {sorted(unknown_top)}",
            location=f"{location}:/",
        )

    out: dict[str, dict[str, Any]] = {}
    for role_id, binding in bindings_raw.items():
        if not isinstance(role_id, str) or not role_id.strip():
            raise ConfigError(
                ERROR_INVALID_SCHEMA,
                "binding role id must be a non-empty string",
                location=f"{location}:/bindings",
            )
        rid = role_id.strip()
        if not _ROLE_ID_RE.fullmatch(rid):
            raise ConfigError(
                ERROR_INVALID_SCHEMA,
                f"invalid binding role id: {rid!r}",
                location=f"{location}:/bindings/{rid}",
            )
        if not isinstance(binding, dict):
            raise ConfigError(
                ERROR_INVALID_SCHEMA,
                "each binding must be a mapping",
                location=f"{location}:/bindings/{rid}",
            )
        # Forbid embedding secrets; allow only known binding keys.
        unknown = set(binding) - BINDING_FIELD_KEYS
        if unknown:
            raise ConfigError(
                ERROR_INVALID_SCHEMA,
                f"unknown binding keys for {rid!r}: {sorted(unknown)}",
                location=f"{location}:/bindings/{rid}",
            )
        if "id" in binding:
            raise ConfigError(
                ERROR_INVALID_SCHEMA,
                "binding must not set id (role id is the map key)",
                location=f"{location}:/bindings/{rid}/id",
            )
        out[rid] = copy.deepcopy(binding)
    return out


def assert_slots_have_no_inline_binding(
    profiles: list[Any],
    *,
    location_prefix: str = "/agent_profiles",
) -> None:
    """Fail closed if member task.yaml embeds full job binding on a role slot."""
    if not isinstance(profiles, list):
        return
    for idx, profile in enumerate(profiles):
        if not isinstance(profile, dict):
            continue
        bad = sorted(k for k in BINDING_FIELD_KEYS if k in profile)
        if bad:
            raise ConfigError(
                ERROR_INVALID_SCHEMA,
                "task.yaml agent_profiles must declare role slots only "
                f"(no job binding fields {bad}); put executor/entry/model in "
                f"Database {PROFILES_FILENAME}",
                location=f"{location_prefix}/{idx}",
            )


def merge_bindings_onto_slots(
    slots: list[Any],
    bindings: Mapping[str, Mapping[str, Any]],
    *,
    location_prefix: str = "/agent_profiles",
) -> list[dict[str, Any]]:
    """Merge job bindings onto role slots; fail closed on missing required binding.

    Empty slots list → no bindings required. Non-empty slots each need a binding
    for their ``id``. Slot-only fields (e.g. future workspace constraints) are
    preserved; binding fields always come from *bindings*.
    """
    if not slots:
        return []

    merged_list: list[dict[str, Any]] = []
    for idx, slot in enumerate(slots):
        loc = f"{location_prefix}/{idx}"
        if not isinstance(slot, dict):
            raise ConfigError(
                ERROR_INVALID_SCHEMA,
                "profile must be a mapping",
                location=loc,
            )
        pid = slot.get("id")
        if not isinstance(pid, str) or not pid.strip():
            raise ConfigError(
                ERROR_INVALID_SCHEMA,
                "profile.id required",
                location=f"{loc}/id",
            )
        role_id = pid.strip()
        binding = bindings.get(role_id)
        if binding is None:
            raise ConfigError(
                ERROR_MISSING_BINDING,
                f"no job binding for role {role_id!r} "
                f"(add bindings.{role_id} in Database {PROFILES_FILENAME} "
                "or pass --profiles / binding overrides)",
                location=f"{loc}/id",
            )
        # Slot identity + non-binding fields, then binding fields on top.
        row = {k: copy.deepcopy(v) for k, v in slot.items() if k not in BINDING_FIELD_KEYS}
        row["id"] = role_id
        for key, val in binding.items():
            if key == "id":
                continue
            row[key] = copy.deepcopy(val)
        merged_list.append(row)
    return merged_list


def apply_binding_override(
    bindings: dict[str, dict[str, Any]],
    pointer: str,
    value: Any,
) -> None:
    """Apply ``/bindings/<role_id>/<leaf>`` override onto a mutable bindings map."""
    if not pointer.startswith("/bindings/"):
        raise ConfigError(
            ERROR_INVALID_SCHEMA,
            f"not a binding override pointer: {pointer}",
            location=pointer,
        )
    rest = pointer[len("/bindings/") :]
    if not rest or "/" not in rest:
        raise ConfigError(
            ERROR_INVALID_SCHEMA,
            "binding override must be /bindings/<role_id>/<field>",
            location=pointer,
        )
    role_id, _, field = rest.partition("/")
    if not role_id or not field:
        raise ConfigError(
            ERROR_INVALID_SCHEMA,
            "binding override must be /bindings/<role_id>/<field>",
            location=pointer,
        )
    if not _is_allowlisted_binding_field(field):
        raise ConfigError(
            ERROR_INVALID_SCHEMA,
            f"binding field not allowlisted for override: {field}",
            location=pointer,
        )
    if role_id not in bindings:
        # Create a partial binding so CLI can complete roles declared in profiles
        # after a base file load; merge still fail-closes if executor/model missing.
        bindings[role_id] = {}
    target = bindings[role_id]
    if field.startswith("options/"):
        opt_key = field[len("options/") :]
        options = target.get("options")
        if not isinstance(options, dict):
            options = {}
            target["options"] = options
        options[opt_key] = value
        return
    target[field] = value


def is_binding_override_pointer(pointer: str) -> bool:
    """True when pointer is an allowlisted ``/bindings/<role>/<leaf>`` form."""
    if not pointer.startswith("/bindings/"):
        return False
    rest = pointer[len("/bindings/") :]
    if "/" not in rest:
        return False
    role_id, _, field = rest.partition("/")
    if not role_id or not _ROLE_ID_RE.fullmatch(role_id):
        return False
    return _is_allowlisted_binding_field(field)


def _is_allowlisted_binding_field(field: str) -> bool:
    if field in _BINDING_OVERRIDE_LEAVES:
        return True
    if not field.startswith("options/"):
        return False
    key = field[len("options/") :]
    if not key or "/" in key or not _ROLE_ID_RE.fullmatch(key):
        return False
    return key not in _OPTIONS_DENYLIST


def secret_free_options(options: Mapping[str, Any] | None) -> dict[str, Any]:
    """Opaque plugin options minus denylisted / private keys."""
    if not isinstance(options, Mapping):
        return {}
    out: dict[str, Any] = {}
    for key, val in options.items():
        name = str(key)
        if name in _OPTIONS_DENYLIST or name.startswith("_"):
            continue
        out[name] = val
    return out


def display_agent_name(binding: Mapping[str, Any]) -> str:
    """Jobs / Hub agent axis. Never reads ``options.agent`` (plugin start path).

    Priority: binding ``label`` → ACP ``options.entry`` → ``executor``.
    """
    label = binding.get("label")
    if isinstance(label, str) and label.strip():
        return label.strip()
    executor = str(binding.get("executor") or "").strip()
    if executor == "acp":
        options = binding.get("options")
        if isinstance(options, Mapping):
            entry = options.get("entry")
            if entry is not None and str(entry).strip():
                return str(entry).strip()
        projected = binding.get("entry")
        if isinstance(projected, str) and projected.strip():
            return projected.strip()
        return executor
    return executor


def join_display_names(names: Sequence[str]) -> str:
    """Collapse identical names; join distinct ones with ``+`` (UI may shorten)."""
    cleaned = [n.strip() for n in names if isinstance(n, str) and n.strip()]
    if not cleaned:
        return ""
    if len(set(cleaned)) == 1:
        return cleaned[0]
    return "+".join(cleaned)


def display_labels_from_overlay(overlay: Mapping[str, Any] | None) -> tuple[str, str]:
    """``(agent_label, model_label)`` from secret-free ``job_overlay``."""
    if not isinstance(overlay, Mapping):
        return "", ""
    bindings = overlay.get("bindings")
    if not isinstance(bindings, Mapping) or not bindings:
        return "", ""
    agents: list[str] = []
    models: list[str] = []
    for raw in bindings.values():
        if not isinstance(raw, Mapping):
            continue
        agents.append(display_agent_name(raw))
        model = raw.get("model")
        models.append(model.strip() if isinstance(model, str) else "")
    return join_display_names(agents), join_display_names(models)


def attach_display_labels(doc: dict[str, Any], overlay: Mapping[str, Any] | None) -> None:
    """Write sealed ``agent_label`` / ``model_label`` onto result or summary."""
    agent, model = display_labels_from_overlay(overlay)
    if agent:
        doc["agent_label"] = agent
    if model:
        doc["model_label"] = model


def project_job_overlay(
    bindings: Mapping[str, Mapping[str, Any]],
    *,
    role_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Secret-free job overlay projection for lock summary / upload rehydration.

    Includes only locator names for ``api_key`` (never values).
    """
    keys = role_ids if role_ids is not None else sorted(bindings.keys())
    out: dict[str, Any] = {}
    for rid in keys:
        raw = bindings.get(rid)
        if not isinstance(raw, Mapping):
            continue
        row: dict[str, Any] = {}
        for k in ("executor", "model", "base_url", "api_key", "label"):
            if k in raw and raw[k] is not None:
                row[k] = raw[k]
        options = secret_free_options(
            raw.get("options") if isinstance(raw.get("options"), Mapping) else None
        )
        if options:
            row["options"] = options
        if row:
            out[rid] = row
    return {"bindings": out}


def job_overlay_to_profiles_document(overlay: Mapping[str, Any]) -> dict[str, Any]:
    """Turn a secret-free job_overlay into a ``bora.profiles/1`` document.

    Suitable for writing ``profiles.yaml`` and re-running with ``--profiles``.
    Never includes secret values — only locator names already in the overlay.
    """
    bindings_raw = overlay.get("bindings")
    if not isinstance(bindings_raw, Mapping):
        raise ConfigError(
            ERROR_INVALID_SCHEMA,
            "job_overlay.bindings must be a mapping",
            location="/job_overlay/bindings",
        )
    # Re-validate shape via parse so export stays lock-safe.
    return {
        "format": PROFILES_FORMAT,
        "bindings": parse_profiles_mapping(
            {"format": PROFILES_FORMAT, "bindings": dict(bindings_raw)},
            location="job_overlay",
        ),
    }


def write_profiles_yaml(path: Path, document: Mapping[str, Any]) -> None:
    """Write a profiles document as YAML (UTF-8)."""
    path = path.expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    text = yaml.safe_dump(dict(document), sort_keys=False, allow_unicode=True)
    path.write_text(text, encoding="utf-8")
