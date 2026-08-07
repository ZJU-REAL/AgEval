"""Config Core unit tests: merge, digest, immutability, failures."""

from __future__ import annotations

import copy
from pathlib import Path

import pytest

from bora.adapters.package_fs import LocalPackageReader
from bora.config.capabilities import DeclarationCapabilityCatalog
from bora.config.digest import digest_payload
from bora.config.errors import ConfigError
from bora.config.load_and_lock import ConfigCore
from bora.config.model import thaw
from bora.config.overrides import parse_set_override

REPO = Path(__file__).resolve().parents[2]
MINIMAL = REPO / "examples" / "core" / "tasks" / "config-minimal"
INVALID = REPO / "examples" / "core" / "tasks" / "config-invalid"


@pytest.fixture
def core() -> ConfigCore:
    return ConfigCore(package_reader=LocalPackageReader())


@pytest.fixture
def catalog() -> DeclarationCapabilityCatalog:
    return DeclarationCapabilityCatalog()


def test_lock_success_deterministic(
    core: ConfigCore, catalog: DeclarationCapabilityCatalog
) -> None:
    a = core.load_and_lock(MINIMAL, "config-minimal", capabilities=catalog)
    b = core.load_and_lock(MINIMAL, "config-minimal", capabilities=catalog)
    assert a.digest == b.digest
    assert a.canonical_payload() == b.canonical_payload()
    assert a.digest.startswith("sha256:")
    assert len(a.digest) == len("sha256:") + 64


def test_override_changes_digest(core: ConfigCore, catalog: DeclarationCapabilityCatalog) -> None:
    base = core.load_and_lock(MINIMAL, "config-minimal", capabilities=catalog)
    overridden = core.load_and_lock(
        MINIMAL,
        "config-minimal",
        overrides={"/parameters/seed": 7},
        capabilities=catalog,
    )
    assert overridden.digest != base.digest
    assert thaw(overridden.parameters)["seed"] == 7
    sources = [e.source for e in overridden.resolution.entries]
    assert "cli-override" in sources


def test_variant_merge_order(core: ConfigCore, catalog: DeclarationCapabilityCatalog) -> None:
    locked = core.load_and_lock(
        MINIMAL,
        "config-minimal",
        variant={"parameters": {"seed": 99}},
        overrides={"/parameters/seed": 3},
        capabilities=catalog,
    )
    assert thaw(locked.parameters)["seed"] == 3
    sources = [(e.source, e.pointer) for e in locked.resolution.entries]
    assert ("campaign-variant", "/") in sources
    assert ("cli-override", "/parameters/seed") in sources


def test_unknown_profile(core: ConfigCore, catalog: DeclarationCapabilityCatalog) -> None:
    with pytest.raises(ConfigError) as ei:
        core.load_and_lock(INVALID, "config-invalid", capabilities=catalog)
    assert ei.value.error_code == "unknown_profile"


def test_invalid_format(
    core: ConfigCore, catalog: DeclarationCapabilityCatalog, tmp_path: Path
) -> None:
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    yaml = (MINIMAL / "task.yaml").read_text(encoding="utf-8")
    yaml = yaml.replace("format: bora.task/1", "format: bora.task/999")
    (pkg / "task.yaml").write_text(yaml, encoding="utf-8")
    (pkg / "harness.py").write_text("#\n", encoding="utf-8")
    (pkg / "evaluator.py").write_text("#\n", encoding="utf-8")
    with pytest.raises(ConfigError) as ei:
        core.load_and_lock(pkg, "config-minimal", capabilities=catalog)
    assert ei.value.error_code == "invalid_format"


def test_unsupported_capability(
    core: ConfigCore, catalog: DeclarationCapabilityCatalog, tmp_path: Path
) -> None:
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    yaml = (MINIMAL / "task.yaml").read_text(encoding="utf-8")
    yaml = yaml.replace("kind: local", "kind: quantum-cloud")
    (pkg / "task.yaml").write_text(yaml, encoding="utf-8")
    (pkg / "harness.py").write_text("#\n", encoding="utf-8")
    (pkg / "evaluator.py").write_text("#\n", encoding="utf-8")
    with pytest.raises(ConfigError) as ei:
        core.load_and_lock(pkg, "config-minimal", capabilities=catalog)
    assert ei.value.error_code == "unsupported_capability"


def test_missing_reference(
    core: ConfigCore, catalog: DeclarationCapabilityCatalog, tmp_path: Path
) -> None:
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "task.yaml").write_text(
        (MINIMAL / "task.yaml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    # harness.py intentionally omitted
    (pkg / "evaluator.py").write_text("#\n", encoding="utf-8")
    with pytest.raises(ConfigError) as ei:
        core.load_and_lock(pkg, "config-minimal", capabilities=catalog)
    assert ei.value.error_code == "missing_reference"


def test_memory_mb_override(core: ConfigCore, catalog: DeclarationCapabilityCatalog) -> None:
    locked = core.load_and_lock(
        MINIMAL,
        "config-minimal",
        overrides={"/limits/memory_mb": 256},
        capabilities=catalog,
    )
    assert thaw(locked.limits)["memory_mb"] == 256


def test_unknown_task(core: ConfigCore, catalog: DeclarationCapabilityCatalog) -> None:
    with pytest.raises(ConfigError) as ei:
        core.load_and_lock(MINIMAL, "wrong-id", capabilities=catalog)
    assert ei.value.error_code == "unknown_task"


def test_unknown_top_level_path(
    core: ConfigCore, catalog: DeclarationCapabilityCatalog, tmp_path: Path
) -> None:
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "task.yaml").write_text(
        (MINIMAL / "task.yaml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (pkg / "harness.py").write_text("#\n", encoding="utf-8")
    (pkg / "evaluator.py").write_text("#\n", encoding="utf-8")
    (pkg / "helpers").mkdir()  # forbidden top-level name
    with pytest.raises(ConfigError) as ei:
        core.load_and_lock(pkg, "config-minimal", capabilities=catalog)
    assert ei.value.error_code == "unknown_package_path"


def test_path_escape_rejected(
    core: ConfigCore, catalog: DeclarationCapabilityCatalog, tmp_path: Path
) -> None:
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    yaml = (MINIMAL / "task.yaml").read_text(encoding="utf-8")
    yaml = yaml.replace("path: artifacts/result.json", "path: ../escape.json")
    (pkg / "task.yaml").write_text(yaml, encoding="utf-8")
    (pkg / "harness.py").write_text("#\n", encoding="utf-8")
    (pkg / "evaluator.py").write_text("#\n", encoding="utf-8")
    with pytest.raises(ConfigError) as ei:
        core.load_and_lock(pkg, "config-minimal", capabilities=catalog)
    assert ei.value.error_code == "path_outside_package"


def test_duplicate_key_rejected(
    core: ConfigCore, catalog: DeclarationCapabilityCatalog, tmp_path: Path
) -> None:
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "task.yaml").write_text(
        "format: bora.task/1\nformat: bora.task/1\ntask_id: config-minimal\n",
        encoding="utf-8",
    )
    (pkg / "harness.py").write_text("#\n", encoding="utf-8")
    (pkg / "evaluator.py").write_text("#\n", encoding="utf-8")
    with pytest.raises(ConfigError) as ei:
        core.load_and_lock(pkg, "config-minimal", capabilities=catalog)
    assert ei.value.error_code == "invalid_schema"


def test_immutability(core: ConfigCore, catalog: DeclarationCapabilityCatalog) -> None:
    locked = core.load_and_lock(MINIMAL, "config-minimal", capabilities=catalog)
    payload_before = copy.deepcopy(locked.canonical_payload())
    digest_before = locked.digest

    # Mutating the thawed view must not affect the lock.
    thawed = thaw(locked.parameters)
    thawed["seed"] = 999
    assert locked.digest == digest_before
    assert locked.canonical_payload() == payload_before

    # MappingProxyType should reject item assignment.
    with pytest.raises(TypeError):
        locked.parameters["seed"] = 123  # type: ignore[index]


def test_digest_independent_of_checkout_location(
    core: ConfigCore, catalog: DeclarationCapabilityCatalog, tmp_path: Path
) -> None:
    """Same logical package at two absolute locations → same digest."""
    for name in ("a", "b"):
        pkg = tmp_path / name
        pkg.mkdir()
        for fname in ("task.yaml", "harness.py", "evaluator.py"):
            (pkg / fname).write_text(
                (MINIMAL / fname).read_text(encoding="utf-8"),
                encoding="utf-8",
            )
    d1 = core.load_and_lock(tmp_path / "a", "config-minimal", capabilities=catalog).digest
    d2 = core.load_and_lock(tmp_path / "b", "config-minimal", capabilities=catalog).digest
    assert d1 == d2


def test_no_secret_or_host_paths_in_payload(
    core: ConfigCore, catalog: DeclarationCapabilityCatalog
) -> None:
    locked = core.load_and_lock(MINIMAL, "config-minimal", capabilities=catalog)
    blob = str(locked.canonical_payload()) + locked.digest
    assert "OPENAI" not in blob
    assert "sk-" not in blob
    # Digest/payload must not embed the absolute checkout path.
    assert str(MINIMAL.resolve()) not in blob


def test_parse_set_override_rejects_unknown_pointer() -> None:
    with pytest.raises(ConfigError) as ei:
        parse_set_override('/harness/entrypoint="x:y"')
    assert ei.value.error_code == "invalid_override"


def test_digest_payload_stable() -> None:
    a = digest_payload({"z": 1, "a": [2, 1]})
    b = digest_payload({"a": [2, 1], "z": 1})
    assert a == b


def test_does_not_import_harness_module(
    core: ConfigCore, catalog: DeclarationCapabilityCatalog
) -> None:
    import sys

    # Clear any accidental prior import.
    for key in list(sys.modules):
        if "harness" in key and "examples" in key:
            del sys.modules[key]
    core.load_and_lock(MINIMAL, "config-minimal", capabilities=catalog)
    assert not any(
        "examples.config_minimal" in k or k.endswith("config-minimal.harness") for k in sys.modules
    )
