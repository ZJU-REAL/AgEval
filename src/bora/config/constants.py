"""Config package layout allowlists, override allowlist, and explicit defaults."""

from __future__ import annotations

from typing import Any

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

# JSON Pointers that CLI ``--set`` may override (#59).
# Intent limits are pure task contract — never job-overridable.
# Agent entry/model binding uses /bindings/<role_id>/… (see profiles.is_binding_override_pointer).
ALLOWLISTED_OVERRIDE_POINTERS = frozenset(
    {
        "/parameters/seed",
        "/parameters/active_profile",
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
