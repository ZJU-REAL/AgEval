"""Dataset-root ``profiles.yaml`` — the job document (``ageval.profiles/1``).

The job answers two questions the task must not answer:

* which box wins the ``environment`` exclusive slot;
* which Agent backend, model and credential locator bind each role slot the
  task declared.

A member ``task.yaml`` declares role slots only. ``api_key`` is an environment
variable *name* — never a value.
"""

from __future__ import annotations

import copy
import json
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import yaml

from ageval.config.errors import (
    ERROR_INVALID_FORMAT,
    ERROR_INVALID_PACKAGE,
    ERROR_INVALID_SCHEMA,
    ERROR_MISSING_BINDING,
    ConfigError,
)

PROFILES_FILENAME = "profiles.yaml"
PROFILES_FORMAT = "ageval.profiles/1"
DEFAULT_ENVIRONMENT = "docker"

# Keys allowed on one agent profile. ``agent_ref`` is provenance injected by the
# ``--agent`` projection — it names where a profile came from, never identity.
PROFILE_FIELD_KEYS = frozenset(
    {
        "executor",
        "model",
        "options",
        "api_key",
        "base_url",
        "extensions",
        "label",
        "agent_ref",
        "overlays",
    }
)

# Job binding fields a member task.yaml may never declare on a role slot.
BINDING_FIELD_KEYS = PROFILE_FIELD_KEYS

# Default profile for any role the job did not name explicitly.
WILDCARD_ROLE = "*"

_BINDING_OVERRIDE_LEAVES = frozenset({"model", "executor", "api_key", "base_url"})

# Plugin options are opaque, except these: they are entry-registry truth and
# never ride the job axis.
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
    }
)

_ROLE_ID_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]*$")


class JobDocument:
    """Parsed ``profiles.yaml``: the environment winner plus role profiles."""

    __slots__ = ("environment", "profiles", "source")

    def __init__(
        self,
        *,
        environment: str,
        profiles: dict[str, dict[str, Any]],
        source: str | None = None,
    ) -> None:
        self.environment = environment
        self.profiles = profiles
        self.source = source

    def profile_for(self, role_id: str, *, selected: str | None = None) -> dict[str, Any] | None:
        """Resolve one role: ``--profile`` selection, exact row, then wildcard."""
        if selected is not None:
            row = self.profiles.get(selected)
            return copy.deepcopy(row) if isinstance(row, Mapping) else None
        for key in (role_id, WILDCARD_ROLE):
            row = self.profiles.get(key)
            if isinstance(row, Mapping):
                return copy.deepcopy(row)
        return None


def load_job_document(path: Path) -> JobDocument:
    """Load and validate one ``ageval.profiles/1`` document."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError(
            ERROR_INVALID_PACKAGE,
            f"cannot read profiles file: {exc}",
            location=str(path),
        ) from exc
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
    return parse_job_mapping(data, location=str(path))


def resolve_job_document(
    dataset_root: Path,
    *,
    profiles_path: Path | str | None = None,
) -> JobDocument:
    """Job document for this run: ``--profiles`` file, else the dataset root file."""
    if profiles_path is not None:
        path = Path(profiles_path).expanduser().resolve(strict=False)
        if not path.is_file():
            raise ConfigError(
                ERROR_INVALID_PACKAGE,
                f"profiles file not found: {profiles_path}",
                location=str(profiles_path),
            )
        return load_job_document(path)
    root = Path(dataset_root).expanduser().resolve(strict=False)
    path = root / PROFILES_FILENAME
    if not path.is_file():
        return JobDocument(environment=DEFAULT_ENVIRONMENT, profiles={}, source=None)
    return load_job_document(path)


def parse_job_mapping(raw: Mapping[str, Any], *, location: str = "profiles.yaml") -> JobDocument:
    """Validate a job document and return it."""
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

    unknown_top = set(raw) - {"format", "environment", "agent_profiles"}
    if unknown_top:
        raise ConfigError(
            ERROR_INVALID_SCHEMA,
            f"unknown profiles keys: {sorted(unknown_top)}",
            location=f"{location}:/",
        )

    env_raw = raw.get("environment", DEFAULT_ENVIRONMENT)
    if not isinstance(env_raw, str) or not env_raw.strip():
        raise ConfigError(
            ERROR_INVALID_SCHEMA,
            "environment must be the id of the box kind that wins the slot",
            location=f"{location}:/environment",
        )

    profiles_raw = raw.get("agent_profiles")
    if profiles_raw is None:
        raise ConfigError(
            ERROR_INVALID_SCHEMA,
            "profiles document requires agent_profiles mapping",
            location=f"{location}:/agent_profiles",
        )
    if not isinstance(profiles_raw, dict):
        raise ConfigError(
            ERROR_INVALID_SCHEMA,
            "agent_profiles must be a mapping of role id → profile",
            location=f"{location}:/agent_profiles",
        )

    out: dict[str, dict[str, Any]] = {}
    for role_id, profile in profiles_raw.items():
        if not isinstance(role_id, str) or not role_id.strip():
            raise ConfigError(
                ERROR_INVALID_SCHEMA,
                "profile role id must be a non-empty string",
                location=f"{location}:/agent_profiles",
            )
        rid = role_id.strip()
        if rid != WILDCARD_ROLE and not _ROLE_ID_RE.fullmatch(rid):
            raise ConfigError(
                ERROR_INVALID_SCHEMA,
                f"invalid profile role id: {rid!r}",
                location=f"{location}:/agent_profiles/{rid}",
            )
        if not isinstance(profile, dict):
            raise ConfigError(
                ERROR_INVALID_SCHEMA,
                "each profile must be a mapping",
                location=f"{location}:/agent_profiles/{rid}",
            )
        unknown = set(profile) - PROFILE_FIELD_KEYS
        if unknown:
            raise ConfigError(
                ERROR_INVALID_SCHEMA,
                f"unknown profile keys for {rid!r}: {sorted(unknown)}",
                location=f"{location}:/agent_profiles/{rid}",
            )
        out[rid] = copy.deepcopy(profile)
    return JobDocument(environment=env_raw.strip(), profiles=out, source=location)


def assert_slots_have_no_inline_binding(
    slots: list[Any],
    *,
    location_prefix: str = "/agent_profiles",
) -> None:
    """Fail closed if a member task.yaml embeds job binding on a role slot."""
    for idx, slot in enumerate(slots):
        if not isinstance(slot, dict):
            continue
        bad = sorted(k for k in BINDING_FIELD_KEYS if k in slot)
        if bad:
            raise ConfigError(
                ERROR_INVALID_SCHEMA,
                "task.yaml agent_profiles declares role slots only "
                f"(job binding fields {bad} belong in dataset {PROFILES_FILENAME})",
                location=f"{location_prefix}/{idx}",
            )


def merge_job_onto_slots(
    slots: list[Any],
    job: JobDocument,
    *,
    selected_profile: str | None = None,
    location_prefix: str = "/agent_profiles",
) -> list[dict[str, Any]]:
    """Bind every declared role slot; fail closed when a role has no profile."""
    if not slots:
        return []
    merged: list[dict[str, Any]] = []
    for idx, slot in enumerate(slots):
        loc = f"{location_prefix}/{idx}"
        if not isinstance(slot, dict):
            raise ConfigError(ERROR_INVALID_SCHEMA, "profile must be a mapping", location=loc)
        pid = slot.get("id")
        if not isinstance(pid, str) or not pid.strip():
            raise ConfigError(ERROR_INVALID_SCHEMA, "profile.id required", location=f"{loc}/id")
        role_id = pid.strip()
        profile = job.profile_for(role_id, selected=selected_profile)
        if profile is None:
            wanted = selected_profile or role_id
            raise ConfigError(
                ERROR_MISSING_BINDING,
                f"no agent profile for role {role_id!r} "
                f"(add agent_profiles.{wanted} in dataset {PROFILES_FILENAME} "
                "or pass --profiles / --profile)",
                location=f"{loc}/id",
            )
        row = {k: copy.deepcopy(v) for k, v in slot.items() if k not in BINDING_FIELD_KEYS}
        row["id"] = role_id
        for key, val in profile.items():
            if key == "id":
                continue
            row[key] = copy.deepcopy(val)
        merged.append(row)
    return merged


def apply_profile_override(job: JobDocument, pointer: str, value: Any) -> None:
    """Apply ``/agent_profiles/<role>/<leaf>`` override onto a job document."""
    prefix = "/agent_profiles/"
    if not pointer.startswith(prefix):
        raise ConfigError(
            ERROR_INVALID_SCHEMA,
            f"not a profile override pointer: {pointer}",
            location=pointer,
        )
    rest = pointer[len(prefix) :]
    role_id, _, field = rest.partition("/")
    if not role_id or not field:
        raise ConfigError(
            ERROR_INVALID_SCHEMA,
            "profile override must be /agent_profiles/<role_id>/<field>",
            location=pointer,
        )
    if not _is_allowlisted_profile_field(field):
        raise ConfigError(
            ERROR_INVALID_SCHEMA,
            f"profile field not allowlisted for override: {field}",
            location=pointer,
        )
    target = job.profiles.get(role_id)
    if target is None:
        # An override on an unnamed role starts from what that role would have
        # got anyway — the wildcard — so one --set does not blank the rest.
        wildcard = job.profiles.get(WILDCARD_ROLE)
        target = copy.deepcopy(wildcard) if isinstance(wildcard, Mapping) else {}
        job.profiles[role_id] = target
    if field.startswith("options/"):
        options = target.setdefault("options", {})
        if not isinstance(options, dict):
            raise ConfigError(
                ERROR_INVALID_SCHEMA,
                "profile options must be a mapping",
                location=pointer,
            )
        options[field[len("options/") :]] = value
        return
    target[field] = value


def is_profile_override_pointer(pointer: str) -> bool:
    """True when pointer is an allowlisted ``/agent_profiles/<role>/<leaf>`` form."""
    prefix = "/agent_profiles/"
    if not pointer.startswith(prefix):
        return False
    rest = pointer[len(prefix) :]
    role_id, _, field = rest.partition("/")
    if not role_id or not _ROLE_ID_RE.fullmatch(role_id):
        return False
    return _is_allowlisted_profile_field(field)


def _is_allowlisted_profile_field(field: str) -> bool:
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
    return {
        str(k): v
        for k, v in options.items()
        if str(k) not in _OPTIONS_DENYLIST and not str(k).startswith("_")
    }


def _secret_free_extension_row(item: Mapping[str, Any]) -> dict[str, Any]:
    out = {k: copy.deepcopy(v) for k, v in item.items() if k != "options"}
    cleaned = secret_free_options(
        item.get("options") if isinstance(item.get("options"), Mapping) else None
    )
    if cleaned:
        out["options"] = cleaned
    return out


def plugin_row_options(profile: Mapping[str, Any], plugin_id: str) -> dict[str, Any]:
    """Options for *plugin_id*: profile ``options`` then its extensions row."""
    found: dict[str, Any] = {}
    if str(profile.get("executor") or "").strip() == plugin_id:
        raw = profile.get("options")
        if isinstance(raw, Mapping):
            found.update(dict(raw))
    rows = profile.get("extensions")
    if isinstance(rows, Sequence) and not isinstance(rows, (str, bytes)):
        for item in rows:
            if not isinstance(item, Mapping):
                continue
            if str(item.get("plugin") or "").strip() != plugin_id:
                continue
            raw = item.get("options")
            if isinstance(raw, Mapping):
                found.update(dict(raw))
    return found


def executor_plugin_options(profile: Mapping[str, Any]) -> dict[str, Any]:
    """Options for the plugin that wins ``executor`` in this profile."""
    executor = str(profile.get("executor") or "").strip()
    return plugin_row_options(profile, executor) if executor else {}


def effective_profile(
    profiles: Mapping[str, Mapping[str, Any]],
    role_id: str,
) -> dict[str, Any] | None:
    """Resolve one role: exact row, else the wildcard row. ``None`` when neither."""
    for key in (role_id, WILDCARD_ROLE):
        row = profiles.get(key)
        if isinstance(row, Mapping):
            return copy.deepcopy(dict(row))
    return None


def acp_entry_from_profile(profile: Mapping[str, Any]) -> str | None:
    """ACP ``entry`` from profile options or the ``- plugin: acp`` row."""
    entry = plugin_row_options(profile, "acp").get("entry")
    if entry is not None and str(entry).strip():
        return str(entry).strip()
    return None


def display_agent_name(profile: Mapping[str, Any]) -> str:
    """Jobs / Hub agent axis: ``label`` → ACP ``entry`` → ``executor``."""
    label = profile.get("label")
    if isinstance(label, str) and label.strip():
        return label.strip()
    executor = str(profile.get("executor") or "").strip()
    if executor == "acp":
        return acp_entry_from_profile(profile) or executor
    return executor


def join_display_names(names: Sequence[str]) -> str:
    """Collapse identical names; join distinct ones with ``+``."""
    cleaned = [n.strip() for n in names if isinstance(n, str) and n.strip()]
    if not cleaned:
        return ""
    if len(set(cleaned)) == 1:
        return cleaned[0]
    return "+".join(cleaned)


def reasoning_effort_from_profile(profile: Mapping[str, Any] | None) -> str:
    """ACP ``options.reasoning_effort`` when set."""
    if not isinstance(profile, Mapping):
        return ""
    raw = plugin_row_options(profile, "acp").get("reasoning_effort")
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    return ""


def display_labels_from_overlay(overlay: Mapping[str, Any] | None) -> tuple[str, str]:
    """``(agent_label, model_label)`` from a secret-free ``job_overlay``."""
    profiles = _overlay_profiles(overlay)
    if not profiles:
        return "", ""
    agents: list[str] = []
    models: list[str] = []
    for raw in profiles.values():
        if not isinstance(raw, Mapping):
            continue
        agents.append(display_agent_name(raw))
        model = raw.get("model")
        models.append(model.strip() if isinstance(model, str) else "")
    return join_display_names(agents), join_display_names(models)


def reasoning_effort_from_overlay(overlay: Mapping[str, Any] | None) -> str:
    """Join distinct reasoning efforts across a ``job_overlay``."""
    found = [
        reasoning_effort_from_profile(raw)
        for raw in _overlay_profiles(overlay).values()
        if isinstance(raw, Mapping)
    ]
    return join_display_names([effort for effort in found if effort])


def environment_from_overlay(overlay: Mapping[str, Any] | None) -> str:
    """Box kind recorded in a ``job_overlay``."""
    if not isinstance(overlay, Mapping):
        return ""
    kind = overlay.get("environment")
    return kind.strip() if isinstance(kind, str) else ""


def _overlay_profiles(overlay: Mapping[str, Any] | None) -> Mapping[str, Any]:
    if not isinstance(overlay, Mapping):
        return {}
    profiles = overlay.get("agent_profiles")
    return profiles if isinstance(profiles, Mapping) else {}


def project_job_overlay(
    profiles: Mapping[str, Mapping[str, Any]],
    *,
    environment: str,
    role_ids: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Secret-free projection of the job used for this lock.

    Includes only locator *names* for ``api_key``, never values.
    """
    keys = list(role_ids) if role_ids is not None else sorted(profiles)
    out: dict[str, Any] = {}
    for rid in keys:
        raw = profiles.get(rid)
        if not isinstance(raw, Mapping):
            # A role the job did not name takes the wildcard profile whole.
            raw = profiles.get(WILDCARD_ROLE)
        if not isinstance(raw, Mapping):
            continue
        row: dict[str, Any] = {}
        for key in ("executor", "model", "base_url", "api_key", "label", "agent_ref", "overlays"):
            if raw.get(key) is not None:
                row[key] = copy.deepcopy(raw[key])
        options = secret_free_options(
            raw.get("options") if isinstance(raw.get("options"), Mapping) else None
        )
        if options:
            row["options"] = options
        extensions = raw.get("extensions")
        if isinstance(extensions, Sequence) and not isinstance(extensions, (str, bytes)):
            row["extensions"] = [
                _secret_free_extension_row(item)
                if isinstance(item, Mapping)
                else copy.deepcopy(item)
                for item in extensions
            ]
        if row:
            out[rid] = row
    return {"environment": environment, "agent_profiles": out}


def job_overlay_to_profiles_document(overlay: Mapping[str, Any]) -> dict[str, Any]:
    """Turn a secret-free job overlay back into an ``ageval.profiles/1`` document."""
    profiles_raw = overlay.get("agent_profiles")
    if not isinstance(profiles_raw, Mapping):
        raise ConfigError(
            ERROR_INVALID_SCHEMA,
            "job_overlay.agent_profiles must be a mapping",
            location="/job_overlay/agent_profiles",
        )
    profiles: dict[str, Any] = {}
    for role_id, raw in profiles_raw.items():
        if not isinstance(raw, Mapping):
            profiles[str(role_id)] = raw
            continue
        row = dict(raw)
        api_key = row.get("api_key")
        if isinstance(api_key, str) and api_key and not api_key.startswith("${"):
            row["api_key"] = f"${{{api_key}}}"
        profiles[str(role_id)] = row
    document = {
        "format": PROFILES_FORMAT,
        "environment": str(overlay.get("environment") or DEFAULT_ENVIRONMENT),
        "agent_profiles": profiles,
    }
    parse_job_mapping(document, location="job_overlay")
    return document


def write_profiles_yaml(path: Path, document: Mapping[str, Any]) -> None:
    """Write a job document as YAML (UTF-8)."""
    path = path.expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    text = yaml.safe_dump(dict(document), sort_keys=False, allow_unicode=True)
    path.write_text(text, encoding="utf-8")


def attach_display_labels(doc: dict[str, Any], overlay: Mapping[str, Any] | None) -> None:
    """Write sealed ``agent_label`` / ``model_label`` onto a result document."""
    agent, model_label = display_labels_from_overlay(overlay)
    if agent:
        doc["agent_label"] = agent
    if model_label:
        doc["model_label"] = model_label


def dumps_job(document: Mapping[str, Any]) -> str:
    """Deterministic JSON form (evidence / tests)."""
    return json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
