"""Static ACP entry registry (Spec 19).

Descriptors are data only. Runtime never fetches remote registries or runs
``install_command``. Digest is stable over logical fields (no host PATH).
"""

from __future__ import annotations

import hashlib
import json
import platform
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from functools import lru_cache
from importlib import resources
from pathlib import Path
from typing import Any, Final, Literal

from ageval.adapters.path_probe import probe_commands

IntegrationMode = Literal[1, 2, 3]
ModelBinding = Literal["config-option", "entry-default-only"]
Readiness = Literal[
    "ready",
    "engine-missing",
    "adapter-missing",
    "entry-missing",
    "unsupported-platform",
]

_REGISTRY_RESOURCE = "acp_entries.json"
_SECRET_FIELD_DENYLIST: Final[frozenset[str]] = frozenset(
    {
        "api_key",
        "token",
        "password",
        "secret",
        "authorization",
        "cookie",
        "auth_file",
        "credential",
    }
)


@dataclass(frozen=True, slots=True)
class AcpEntryDescriptor:
    entry_id: str
    integration_mode: IntegrationMode
    execution_mode: str
    engine_command: str
    engine_detect_commands: tuple[str, ...]
    engine_package: str | None
    engine_version: str | None
    acp_command: tuple[str, ...]
    acp_detect_commands: tuple[str, ...]
    acp_package: str | None
    acp_version: str
    install_command: str
    credential_env_names: tuple[str, ...]
    keyless_auth: bool
    model_binding: ModelBinding
    platforms: tuple[str, ...]
    fixed_env: Mapping[str, str]
    descriptor_digest: str

    def as_lock_snapshot(self) -> dict[str, Any]:
        """Fields safe for lock/evidence (no absolute PATH, no secrets)."""
        return {
            "entry_id": self.entry_id,
            "integration_mode": self.integration_mode,
            "execution_mode": self.execution_mode,
            "engine_command": self.engine_command,
            "engine_package": self.engine_package,
            "engine_version": self.engine_version,
            "acp_command": list(self.acp_command),
            "acp_package": self.acp_package,
            "acp_version": self.acp_version,
            "model_binding": self.model_binding,
            "credential_env_names": list(self.credential_env_names),
            "keyless_auth": self.keyless_auth,
            "descriptor_digest": self.descriptor_digest,
            "platforms": list(self.platforms),
        }

    def as_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["acp_command"] = list(self.acp_command)
        d["engine_detect_commands"] = list(self.engine_detect_commands)
        d["acp_detect_commands"] = list(self.acp_detect_commands)
        d["credential_env_names"] = list(self.credential_env_names)
        d["keyless_auth"] = bool(self.keyless_auth)
        d["platforms"] = list(self.platforms)
        d["fixed_env"] = dict(self.fixed_env)
        return d


def _canonical_digest(payload: Mapping[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _validate_raw_entry(raw: Mapping[str, Any], *, index: int) -> None:
    loc = f"/entries/{index}"
    required = (
        "entry_id",
        "integration_mode",
        "execution_mode",
        "engine_detect_commands",
        "acp_command",
        "acp_detect_commands",
        "acp_version",
        "install_command",
        "credential_env_names",
        "model_binding",
        "platforms",
    )
    for key in required:
        if key not in raw:
            raise ValueError(f"{loc}: missing required field {key!r}")
    entry_id = raw["entry_id"]
    if not isinstance(entry_id, str) or not entry_id.strip():
        raise ValueError(f"{loc}/entry_id: non-empty string required")
    mode = raw["integration_mode"]
    if mode not in (1, 2, 3):
        raise ValueError(f"{loc}/integration_mode: must be 1|2|3")
    if raw["execution_mode"] != "acp-stdio":
        raise ValueError(f"{loc}/execution_mode: must be acp-stdio")
    cmd = raw["acp_command"]
    if not isinstance(cmd, list) or not cmd or not all(isinstance(c, str) and c for c in cmd):
        raise ValueError(f"{loc}/acp_command: non-empty string list required")
    if any(tok == "npx" and "latest" in " ".join(cmd) for tok in cmd):
        raise ValueError(f"{loc}/acp_command: floating npx latest forbidden")
    if "npx" in cmd and not any("@" in c for c in cmd):
        # bare npx without pin is forbidden
        raise ValueError(f"{loc}/acp_command: unpinned npx forbidden")
    for field in raw:
        low = str(field).lower()
        if (
            low in _SECRET_FIELD_DENYLIST or low.endswith("_secret") or low.endswith("_token")
        ) and field not in {"credential_env_names"}:
            raise ValueError(f"{loc}: secret-bearing field name forbidden: {field}")
    binding = raw["model_binding"]
    if binding not in ("config-option", "entry-default-only"):
        raise ValueError(f"{loc}/model_binding: invalid")
    platforms = raw["platforms"]
    if not isinstance(platforms, list) or not platforms:
        raise ValueError(f"{loc}/platforms: non-empty list required")


def _parse_entry(raw: Mapping[str, Any], *, index: int) -> AcpEntryDescriptor:
    _validate_raw_entry(raw, index=index)
    engine_detect = tuple(str(x) for x in raw["engine_detect_commands"])
    acp_detect = tuple(str(x) for x in raw["acp_detect_commands"])
    acp_command = tuple(str(x) for x in raw["acp_command"])
    fixed_env_raw = raw.get("fixed_env") or {}
    if not isinstance(fixed_env_raw, dict):
        raise ValueError(f"/entries/{index}/fixed_env: must be object")
    fixed_env = {str(k): str(v) for k, v in fixed_env_raw.items()}
    digest_payload = {
        "entry_id": raw["entry_id"],
        "integration_mode": raw["integration_mode"],
        "execution_mode": raw["execution_mode"],
        "engine_command": raw.get("engine_command"),
        "engine_detect_commands": list(engine_detect),
        "engine_package": raw.get("engine_package"),
        "engine_version": raw.get("engine_version"),
        "acp_command": list(acp_command),
        "acp_detect_commands": list(acp_detect),
        "acp_package": raw.get("acp_package"),
        "acp_version": raw["acp_version"],
        "model_binding": raw["model_binding"],
        "credential_env_names": list(raw["credential_env_names"]),
        "keyless_auth": bool(raw.get("keyless_auth", False)),
        "platforms": list(raw["platforms"]),
        "fixed_env": fixed_env,
    }
    return AcpEntryDescriptor(
        entry_id=str(raw["entry_id"]),
        integration_mode=int(raw["integration_mode"]),  # type: ignore[arg-type]
        execution_mode=str(raw["execution_mode"]),
        engine_command=str(
            raw.get("engine_command") or (engine_detect[0] if engine_detect else "")
        ),
        engine_detect_commands=engine_detect,
        engine_package=(
            str(raw["engine_package"]) if raw.get("engine_package") is not None else None
        ),
        engine_version=(
            str(raw["engine_version"]) if raw.get("engine_version") is not None else None
        ),
        acp_command=acp_command,
        acp_detect_commands=acp_detect,
        acp_package=str(raw["acp_package"]) if raw.get("acp_package") is not None else None,
        acp_version=str(raw["acp_version"]),
        install_command=str(raw["install_command"]),
        credential_env_names=tuple(str(x) for x in raw["credential_env_names"]),
        keyless_auth=bool(raw.get("keyless_auth", False)),
        model_binding=str(raw["model_binding"]),  # type: ignore[arg-type]
        platforms=tuple(str(x) for x in raw["platforms"]),
        fixed_env=fixed_env,
        descriptor_digest=_canonical_digest(digest_payload),
    )


def load_registry_document(path: Path | None = None) -> dict[str, Any]:
    if path is not None:
        return json.loads(path.read_text(encoding="utf-8"))
    try:
        ref = resources.files("ageval.plugins.contrib.acp").joinpath(_REGISTRY_RESOURCE)
        with ref.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    except (FileNotFoundError, ModuleNotFoundError, TypeError, AttributeError):
        # Editable / source tree fallback.
        local = Path(__file__).with_name(_REGISTRY_RESOURCE)
        return json.loads(local.read_text(encoding="utf-8"))


@lru_cache(maxsize=4)
def load_acp_entries(path: str | None = None) -> dict[str, AcpEntryDescriptor]:
    doc = load_registry_document(Path(path) if path else None)
    if not isinstance(doc, dict) or "entries" not in doc:
        raise ValueError("acp_entries.json: top-level object with entries required")
    entries_raw = doc["entries"]
    if not isinstance(entries_raw, list) or not entries_raw:
        raise ValueError("acp_entries.json: entries must be a non-empty list")
    out: dict[str, AcpEntryDescriptor] = {}
    for idx, raw in enumerate(entries_raw):
        if not isinstance(raw, dict):
            raise ValueError(f"/entries/{idx}: must be object")
        desc = _parse_entry(raw, index=idx)
        if desc.entry_id in out:
            raise ValueError(f"duplicate entry_id: {desc.entry_id}")
        out[desc.entry_id] = desc
    return out


def get_entry(entry_id: str, *, path: str | None = None) -> AcpEntryDescriptor | None:
    return load_acp_entries(path).get(entry_id)


def list_entry_ids(*, path: str | None = None) -> list[str]:
    return sorted(load_acp_entries(path))


def current_platform_token() -> str:
    return platform.system().lower()


def readiness_for(
    desc: AcpEntryDescriptor,
    *,
    which: Any | None = None,
    platform_token: str | None = None,
) -> dict[str, Any]:
    """Compute inventory readiness without starting models or reading secrets."""
    plat = platform_token or current_platform_token()
    # Map common aliases
    plat_norm = {"macos": "darwin", "osx": "darwin"}.get(plat, plat)
    supported = plat_norm in {p.lower() for p in desc.platforms} or any(
        p.lower() in {plat_norm, "any", "*"} for p in desc.platforms
    )
    if not supported:
        return {
            "entry_id": desc.entry_id,
            "engine_ready": False,
            "acp_entry_ready": False,
            "readiness": "unsupported-platform",
            "engine_binary": None,
            "engine_path": None,
            "acp_binary": None,
            "acp_path": None,
        }

    eng_name, eng_path = probe_commands(desc.engine_detect_commands, which=which)
    acp_name, acp_path = probe_commands(desc.acp_detect_commands, which=which)
    engine_ready = eng_path is not None
    acp_ready = acp_path is not None

    readiness: Readiness
    if desc.integration_mode == 1:
        if engine_ready and acp_ready:
            readiness = "ready"
        elif engine_ready and not acp_ready:
            readiness = "adapter-missing"
        elif not engine_ready and acp_ready:
            readiness = "engine-missing"
        else:
            readiness = "engine-missing"
    else:
        # Mode 2/3: single entry command family.
        readiness = "ready" if acp_ready else "entry-missing"
        # engine_ready tracks optional detect for Mode 3.
        if desc.integration_mode == 2:
            engine_ready = acp_ready

    return {
        "entry_id": desc.entry_id,
        "engine_ready": engine_ready,
        "acp_entry_ready": acp_ready,
        "readiness": readiness,
        "engine_binary": eng_name
        if eng_path
        else (desc.engine_detect_commands[0] if desc.engine_detect_commands else None),
        "engine_path": eng_path,
        "acp_binary": acp_name if acp_path else (desc.acp_command[0] if desc.acp_command else None),
        "acp_path": acp_path,
    }


def clear_registry_cache() -> None:
    load_acp_entries.cache_clear()
