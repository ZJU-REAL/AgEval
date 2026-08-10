"""Package provenance field validation, lock inclusion, Database→task merge (#18)."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from bora.adapters.package_fs import LocalPackageReader
from bora.config.capabilities import DeclarationCapabilityCatalog
from bora.config.database import load_database_manifest
from bora.config.errors import ConfigError
from bora.config.load_and_lock import ConfigCore
from bora.config.model import thaw
from bora.config.provenance import merge_provenance, validate_provenance

REPO = Path(__file__).resolve().parents[2]
MINIMAL = REPO / "examples" / "core" / "tasks" / "config-minimal"
MOCK_BINDINGS = {"mock-default": {"executor": "mock", "model": "none"}}


def _minimal_task_yaml(*, extra: str = "", task_id: str = "config-minimal") -> str:
    base = (MINIMAL / "task.yaml").read_text(encoding="utf-8")
    if not extra:
        return base
    # Append provenance (or other) block after task document.
    return base.rstrip() + "\n\n" + textwrap.dedent(extra).lstrip() + "\n"


def _write_task_pkg(tmp: Path, *, yaml_text: str, task_id: str = "config-minimal") -> Path:
    pkg = tmp / task_id
    pkg.mkdir(parents=True)
    (pkg / "task.yaml").write_text(yaml_text, encoding="utf-8")
    (pkg / "harness.py").write_text("#\n", encoding="utf-8")
    (pkg / "evaluator.py").write_text("#\n", encoding="utf-8")
    return pkg


@pytest.fixture
def core() -> ConfigCore:
    return ConfigCore(package_reader=LocalPackageReader())


@pytest.fixture
def catalog() -> DeclarationCapabilityCatalog:
    return DeclarationCapabilityCatalog()


def test_validate_original_minimal() -> None:
    out = validate_provenance({"kind": "original"})
    assert out == {"kind": "original"}


def test_validate_port_requires_url_and_pin() -> None:
    with pytest.raises(ConfigError) as ei:
        validate_provenance({"kind": "port"})
    assert ei.value.error_code == "invalid_schema"

    with pytest.raises(ConfigError):
        validate_provenance(
            {
                "kind": "port",
                "upstream": {"url": "https://github.com/example/repo"},
            }
        )

    ok = validate_provenance(
        {
            "kind": "port",
            "upstream": {
                "name": "tau-bench",
                "url": "https://github.com/example/tau-bench",
                "commit": "abc123def",
                "task_id": "airline-001",
            },
            "parity": {"claims": ["protocol"], "known_gaps": ["tool names"]},
        }
    )
    assert ok["kind"] == "port"
    assert ok["upstream"]["commit"] == "abc123def"
    assert ok["parity"]["claims"] == ["protocol"]


def test_merge_task_overrides_database() -> None:
    db = {"kind": "port", "upstream": {"url": "https://a.example", "ref": "v1"}}
    task = {"kind": "original"}
    assert merge_provenance(database=db, task=task) == task
    assert merge_provenance(database=db, task=None) == db
    assert merge_provenance(database=None, task=None) is None


def test_lock_includes_task_provenance(
    core: ConfigCore, catalog: DeclarationCapabilityCatalog, tmp_path: Path
) -> None:
    yaml = _minimal_task_yaml(
        extra="""
        provenance:
          kind: original
        """
    )
    pkg = _write_task_pkg(tmp_path, yaml_text=yaml)
    locked = core.load_and_lock(
        pkg,
        "config-minimal",
        capabilities=catalog,
        profile_bindings=MOCK_BINDINGS,
    )
    assert thaw(locked.provenance) == {"kind": "original"}
    assert "provenance" in locked.canonical_payload()
    # Digest changes vs no-provenance baseline from examples/core
    base = core.load_and_lock(
        MINIMAL,
        "config-minimal",
        capabilities=catalog,
        profile_bindings=MOCK_BINDINGS,
    )
    assert locked.digest != base.digest


def test_database_default_applied(
    core: ConfigCore, catalog: DeclarationCapabilityCatalog, tmp_path: Path
) -> None:
    pkg = _write_task_pkg(tmp_path, yaml_text=_minimal_task_yaml())
    locked = core.load_and_lock(
        pkg,
        "config-minimal",
        capabilities=catalog,
        profile_bindings=MOCK_BINDINGS,
        database_provenance={
            "kind": "wrapper",
            "upstream": {
                "url": "https://github.com/example/suite",
                "ref": "v0.2.0",
            },
        },
    )
    prov = thaw(locked.provenance)
    assert prov["kind"] == "wrapper"
    assert prov["upstream"]["ref"] == "v0.2.0"
    sources = [e.source for e in locked.resolution.entries]
    assert "database" in sources


def test_task_provenance_overrides_database(
    core: ConfigCore, catalog: DeclarationCapabilityCatalog, tmp_path: Path
) -> None:
    yaml = _minimal_task_yaml(
        extra="""
        provenance:
          kind: original
        """
    )
    pkg = _write_task_pkg(tmp_path, yaml_text=yaml)
    locked = core.load_and_lock(
        pkg,
        "config-minimal",
        capabilities=catalog,
        profile_bindings=MOCK_BINDINGS,
        database_provenance={
            "kind": "port",
            "upstream": {
                "url": "https://github.com/example/x",
                "commit": "deadbeef",
            },
        },
    )
    assert thaw(locked.provenance) == {"kind": "original"}


def test_invalid_port_fails_lock(
    core: ConfigCore, catalog: DeclarationCapabilityCatalog, tmp_path: Path
) -> None:
    yaml = _minimal_task_yaml(
        extra="""
        provenance:
          kind: port
          upstream:
            name: incomplete
        """
    )
    pkg = _write_task_pkg(tmp_path, yaml_text=yaml)
    with pytest.raises(ConfigError) as ei:
        core.load_and_lock(
            pkg,
            "config-minimal",
            capabilities=catalog,
            profile_bindings=MOCK_BINDINGS,
        )
    assert ei.value.error_code == "invalid_schema"


def test_database_manifest_accepts_provenance(tmp_path: Path) -> None:
    root = tmp_path / "db"
    root.mkdir()
    (root / "bora.yaml").write_text(
        textwrap.dedent(
            """
            format: bora.database/1
            database_id: test/prov-db
            version: "0.1.0"
            tasks:
              root: tasks
            provenance:
              kind: original
            """
        ).lstrip(),
        encoding="utf-8",
    )
    (root / "tasks" / "alpha").mkdir(parents=True)
    (root / "tasks" / "alpha" / "task.yaml").write_text(
        textwrap.dedent(
            """
            format: bora.task/1
            task_id: alpha
            harness:
              runtime: python
              entrypoint: harness:run
            provider:
              kind: local
            agent_profiles: []
            limits:
              wall_time_seconds: 60
              agent_invocations: 0
              environment_actions: 0
              memory_mb: 256
            artifacts:
              publishable: []
            evaluation:
              runtime: python
              entrypoint: evaluator:evaluate
              network: none
              inputs: []
              output:
                format: json
            """
        ).lstrip(),
        encoding="utf-8",
    )
    (root / "tasks" / "alpha" / "harness.py").write_text("#\n", encoding="utf-8")
    (root / "tasks" / "alpha" / "evaluator.py").write_text("#\n", encoding="utf-8")

    man = load_database_manifest(root)
    assert man.provenance is not None
    assert man.provenance["kind"] == "original"
