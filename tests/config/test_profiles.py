"""Database profiles.yaml merge + fail-closed role binding (#59)."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from bora.adapters.package_fs import LocalPackageReader
from bora.config.capabilities import DeclarationCapabilityCatalog
from bora.config.errors import ConfigError
from bora.config.load_and_lock import ConfigCore
from bora.config.model import thaw
from bora.config.profiles import (
    assert_slots_have_no_inline_binding,
    load_profiles_document,
    merge_bindings_onto_slots,
    project_job_overlay,
)


def _write_task(tmp: Path, *, slots: list[dict], task_id: str = "t") -> Path:
    pkg = tmp / "pkg"
    pkg.mkdir()
    (pkg / "harness.py").write_text("async def run(ctx):\n    pass\n", encoding="utf-8")
    (pkg / "evaluator.py").write_text("def evaluate(i):\n    return {}\n", encoding="utf-8")
    doc = {
        "format": "bora.task/1",
        "task_id": task_id,
        "harness": {"runtime": "python", "entrypoint": "harness:run"},
        "parameters": {"models": {"default": slots[0]["id"]}} if slots else {},
        "provider": {"kind": "local", "assurance": "l0"},
        "agent_profiles": slots,
        "limits": {
            "wall_time_seconds": 60,
            "agent_invocations": 1,
            "environment_actions": 0,
        },
        "artifacts": {"publishable": []},
        "evaluation": {
            "runtime": "python",
            "entrypoint": "evaluator:evaluate",
            "network": "none",
            "inputs": [],
            "output": {"format": "json"},
        },
    }
    (pkg / "task.yaml").write_text(yaml.safe_dump(doc), encoding="utf-8")
    return pkg


def test_reject_inline_binding_in_task_yaml(tmp_path: Path) -> None:
    pkg = _write_task(
        tmp_path,
        slots=[{"id": "solver", "executor": "mock", "model": "none"}],
    )
    core = ConfigCore(package_reader=LocalPackageReader())
    with pytest.raises(ConfigError) as ei:
        core.load_and_lock(
            pkg,
            "t",
            capabilities=DeclarationCapabilityCatalog(),
            profile_bindings={"solver": {"executor": "mock", "model": "none"}},
        )
    assert ei.value.error_code == "invalid_schema"
    assert "role slots only" in str(ei.value).lower() or "job binding" in str(ei.value).lower()


def test_missing_binding_fail_closed(tmp_path: Path) -> None:
    pkg = _write_task(tmp_path, slots=[{"id": "solver"}])
    core = ConfigCore(package_reader=LocalPackageReader())
    with pytest.raises(ConfigError) as ei:
        core.load_and_lock(
            pkg,
            "t",
            capabilities=DeclarationCapabilityCatalog(),
            profile_bindings={},
        )
    assert ei.value.error_code == "missing_binding"


def test_merge_bindings_and_cli_override(tmp_path: Path) -> None:
    pkg = _write_task(tmp_path, slots=[{"id": "solver"}])
    core = ConfigCore(package_reader=LocalPackageReader())
    locked = core.load_and_lock(
        pkg,
        "t",
        capabilities=DeclarationCapabilityCatalog(),
        profile_bindings={
            "solver": {
                "executor": "acp",
                "options": {"entry": "codex"},
                "model": "gpt-5.4-mini",
            }
        },
        overrides={
            "/bindings/solver/options/entry": "pi",
            "/bindings/solver/model": "claude-haiku-4-5",
        },
    )
    profiles = thaw(locked.agent_profiles)
    assert profiles[0]["id"] == "solver"
    assert profiles[0]["executor"] == "acp"
    assert profiles[0]["options"]["entry"] == "pi"
    assert profiles[0]["model"] == "claude-haiku-4-5"
    assert locked.job_overlay is not None
    overlay = thaw(locked.job_overlay)
    assert overlay["bindings"]["solver"]["options"]["entry"] == "pi"


def test_empty_slots_need_no_bindings(tmp_path: Path) -> None:
    pkg = _write_task(tmp_path, slots=[])
    core = ConfigCore(package_reader=LocalPackageReader())
    locked = core.load_and_lock(
        pkg,
        "t",
        capabilities=DeclarationCapabilityCatalog(),
        profile_bindings=None,
    )
    assert thaw(locked.agent_profiles) == []
    assert locked.job_overlay is None


def test_profiles_document_parse(tmp_path: Path) -> None:
    path = tmp_path / "profiles.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "format": "bora.profiles/1",
                "bindings": {
                    "solver": {
                        "executor": "acp",
                        "options": {"entry": "codex"},
                        "model": "m",
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    bindings = load_profiles_document(path)
    assert "solver" in bindings
    assert bindings["solver"]["model"] == "m"


def test_assert_slots_helper() -> None:
    with pytest.raises(ConfigError):
        assert_slots_have_no_inline_binding([{"id": "x", "executor": "mock"}])
    assert_slots_have_no_inline_binding([{"id": "x"}])


def test_merge_helper() -> None:
    rows = merge_bindings_onto_slots(
        [{"id": "solver"}],
        {"solver": {"executor": "mock", "model": "none"}},
    )
    assert rows[0]["executor"] == "mock"


def test_job_overlay_omits_secrets() -> None:
    overlay = project_job_overlay(
        {
            "solver": {
                "executor": "acp",
                "options": {"entry": "pi"},
                "model": "m",
                "api_key": "MY_KEY_LOCATOR",
            }
        }
    )
    assert overlay["bindings"]["solver"]["api_key"] == "MY_KEY_LOCATOR"
    # values never present — locator only
    assert "sk-" not in str(overlay)


def test_job_overlay_to_profiles_roundtrip(tmp_path: Path) -> None:
    from bora.config.profiles import (
        job_overlay_to_profiles_document,
        load_profiles_document,
        write_profiles_yaml,
    )

    overlay = project_job_overlay(
        {
            "solver": {
                "executor": "acp",
                "options": {"entry": "pi"},
                "model": "m",
                "api_key": "LOC",
            }
        }
    )
    doc = job_overlay_to_profiles_document(overlay)
    path = tmp_path / "profiles.from-suite.yaml"
    write_profiles_yaml(path, doc)
    loaded = load_profiles_document(path)
    assert loaded["solver"]["options"]["entry"] == "pi"
    assert loaded["solver"]["api_key"] == "LOC"


def test_job_overlay_keeps_plugin_options() -> None:
    overlay = project_job_overlay(
        {
            "solver": {
                "executor": "nooa",
                "model": "openai/glm-5.2",
                "options": {
                    "agent": "lib.agents:JsonlAggAgent",
                    "method": "run",
                    "command": ["secret"],
                    "_acp_lock": {"entry_id": "x"},
                },
            }
        }
    )
    opts = overlay["bindings"]["solver"]["options"]
    assert opts["agent"] == "lib.agents:JsonlAggAgent"
    assert opts["method"] == "run"
    assert "command" not in opts
    assert "_acp_lock" not in opts
